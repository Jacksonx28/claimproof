"""The public UI route allowlist must not expose arbitrary repository files."""
import io
import json
import unittest
from unittest.mock import patch

from api import index


class TestWebAssets(unittest.TestCase):
    def request(self, path, method="GET"):
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = dict(headers)

        body = b"".join(index.app({
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "wsgi.input": io.BytesIO(),
        }, start_response))
        return captured["status"], captured["headers"], body

    def test_asset_routes_preserve_bytes_and_use_browser_mime_types(self):
        expected = {
            "/design.css": ("design.css", "text/css; charset=utf-8"),
            "/design.js": ("design.js", "text/javascript; charset=utf-8"),
            "/checker.js": ("checker.js", "text/javascript; charset=utf-8"),
            "/network.svg": ("network.svg", "image/svg+xml"),
        }
        for path, (filename, mime) in expected.items():
            with self.subTest(path=path), patch.object(index, "_web_bytes", return_value=b"test \xe2\x9c\x93") as read:
                status, headers, body = self.request(path)
                self.assertEqual(status, "200 OK")
                self.assertEqual(headers["Content-Type"], mime)
                self.assertEqual(body, b"test \xe2\x9c\x93")
                self.assertEqual(int(headers["Content-Length"]), len(body))
                read.assert_called_once_with(filename)

    def test_missing_allowlisted_asset_is_a_404(self):
        with patch.object(index, "_web_bytes", return_value=None):
            status, headers, body = self.request("/network.svg")
        self.assertEqual(status, "404 Not Found")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(json.loads(body), {"error": "not found"})

    def test_unknown_and_traversal_paths_do_not_read_files(self):
        for path in ("/README.md", "/api/index.py", "/web/design.css", "/../design.css", "/%2e%2e/design.css", "/design.css/../README.md"):
            with self.subTest(path=path), patch.object(index, "_web_bytes") as read:
                status, _, _ = self.request(path)
                self.assertEqual(status, "404 Not Found")
                read.assert_not_called()

    def test_assets_are_get_only(self):
        with patch.object(index, "_web_bytes") as read:
            status, _, _ = self.request("/design.js", "POST")
        self.assertEqual(status, "404 Not Found")
        read.assert_not_called()

    def test_watch_results_are_read_from_the_public_record(self):
        record = '{"checked_at":"2026-11-26T00:00:00Z","results":[]}'
        with patch.object(index, "_root_file", return_value=record) as read:
            status, headers, body = self.request("/watch_results.json")
        self.assertEqual(status, "200 OK")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(body.decode(), record)
        read.assert_called_once_with("watch_results.json")

    def test_missing_watch_results_is_a_404(self):
        with patch.object(index, "_root_file", return_value=None):
            status, _, _ = self.request("/watch_results.json")
        self.assertEqual(status, "404 Not Found")


if __name__ == "__main__":
    unittest.main()
