import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import telegraph_client  # noqa: E402
from telegraph_client import (DOWNPROOF_MINER_ID, MissingApiKeyError,  # noqa: E402
                              agent_spend, ask_telegraph, escrow_balance)

TEST_KEY = "anjoman_test-key-not-a-real-secret"
ENGINE_PAYLOAD = {"answer": {"is_up": False}, "receipt": "rcpt-1", "cost_usdc": 0.01}


@contextlib.contextmanager
def engine_env(**overrides):
    """Patch os.environ; TELEGRAPH_ENGINE_URL is absent unless overridden."""
    with mock.patch.dict(os.environ, overrides):
        if "TELEGRAPH_ENGINE_URL" not in overrides:
            os.environ.pop("TELEGRAPH_ENGINE_URL", None)
        yield


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class StubbedHttp:
    """Patches urllib.request.urlopen and records every Request sent.

    Also redirects the client's attempts log to a throwaway temp file
    (exposed as .attempts_path) so live-ask tests never write fake
    entries into the real attempts.json.
    """

    def __init__(self, payload=ENGINE_PAYLOAD):
        self.payload = payload
        self.requests = []
        self.attempts_path = None

    def __enter__(self):
        def fake_urlopen(req, timeout=None):
            self.requests.append(req)
            return FakeResponse(self.payload)

        self._patch = mock.patch.object(urllib.request, "urlopen", fake_urlopen)
        self._patch.start()
        fd, self.attempts_path = tempfile.mkstemp(suffix="-attempts.json")
        os.close(fd)
        os.unlink(self.attempts_path)  # the client starts from a missing log
        self._log_patch = mock.patch.object(telegraph_client, "ATTEMPTS_PATH",
                                            self.attempts_path)
        self._log_patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        self._log_patch.stop()
        if self.attempts_path and os.path.exists(self.attempts_path):
            os.unlink(self.attempts_path)
        return False


class TestLiveAsk(unittest.TestCase):
    def test_targeted_ask_url_body_and_result(self):
        with engine_env(ANJOMAN_API_KEY=TEST_KEY,
                        TELEGRAPH_ENGINE_URL="https://engine.example"), StubbedHttp() as http:
            result = ask_telegraph("SERVER_UPTIME_MONITOR_GENERAL",
                                   {"url": "https://x.example"}, miner_id=DOWNPROOF_MINER_ID)
        self.assertEqual(len(http.requests), 1)
        req = http.requests[0]
        self.assertEqual(req.full_url, "https://engine.example/engine/ask/23112026")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(json.loads(req.data),
                         {"intent": "SERVER_UPTIME_MONITOR_GENERAL",
                          "params": {"url": "https://x.example"}})
        self.assertEqual(result["mode"], "LIVE")
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["response"], ENGINE_PAYLOAD)  # reply carried as-is
        self.assertEqual(result["receipt"], "rcpt-1")
        self.assertEqual(result["cost_usdc"], 0.01)
        self.assertNotIn(TEST_KEY, json.dumps(result))  # the key never leaks into output

    def test_routed_ask_uses_default_base(self):
        with engine_env(ANJOMAN_API_KEY=TEST_KEY), StubbedHttp() as http:
            result = ask_telegraph("SLA_COMPLIANCE_GENERAL", {"url": "https://x.example"})
        self.assertEqual(http.requests[0].full_url,
                         "https://backend.telegraphprotocol.com/engine/ask")
        self.assertIsNone(result["miner_id"])

    def test_bearer_header_sent(self):
        with engine_env(ANJOMAN_API_KEY=TEST_KEY), StubbedHttp() as http:
            ask_telegraph("SERVER_UPTIME_MONITOR_GENERAL", {"url": "https://x.example"})
        req = http.requests[0]
        self.assertEqual(req.get_header("Authorization"), f"Bearer {TEST_KEY}")
        self.assertEqual(req.get_header("Content-type"), "application/json")

    def test_missing_key_raises_before_any_http(self):
        urlopen = mock.Mock(side_effect=AssertionError("urlopen must not be called"))
        with engine_env(), mock.patch.object(urllib.request, "urlopen", urlopen):
            os.environ.pop("ANJOMAN_API_KEY", None)
            with self.assertRaises(MissingApiKeyError) as ctx:
                ask_telegraph("SERVER_UPTIME_MONITOR_GENERAL",
                              {"url": "https://x.example"}, miner_id=DOWNPROOF_MINER_ID)
            with self.assertRaises(MissingApiKeyError):
                ask_telegraph("SERVER_UPTIME_MONITOR_GENERAL",
                              {"url": "https://x.example"}, live=True)
            with self.assertRaises(MissingApiKeyError):
                escrow_balance()
        self.assertIn("ANJOMAN_API_KEY", str(ctx.exception))
        urlopen.assert_not_called()

    def test_escrow_balance_and_agent_spend_gets(self):
        with engine_env(ANJOMAN_API_KEY=TEST_KEY), StubbedHttp({"balance_usdc": 1.0}) as http:
            balance = escrow_balance()
            spend = agent_spend()
        self.assertEqual(balance, {"balance_usdc": 1.0})
        self.assertEqual(spend, {"balance_usdc": 1.0})
        self.assertTrue(http.requests[0].full_url.endswith("/engine/escrow/balance"))
        self.assertTrue(http.requests[1].full_url.endswith("/agent/spend"))
        for req in http.requests:
            self.assertEqual(req.get_method(), "GET")
            self.assertEqual(req.get_header("Authorization"), f"Bearer {TEST_KEY}")


class TestAttemptsLog(unittest.TestCase):
    """Live asks append to attempts.json: successes with their
    receipt, failures with the engine's error. LOCAL-DEMO never logs."""

    def _read_log(self, path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)["attempts"]

    def test_success_shaped_reply_is_logged_with_receipt(self):
        payload = {
            "result": {"miner_id": "23112026", "miner_name": "downproof-uptime",
                       "cost_usd": 0.01, "result": {"compliant": True}},
            "receipt": {"receipt_hash": "0xdeadbeef", "rail": "escrow"},
        }
        with engine_env(ANJOMAN_API_KEY=TEST_KEY), StubbedHttp(payload) as http:
            ask_telegraph("SLA_COMPLIANCE_GENERAL",
                          {"service": "https://www.google.com", "period": "30 days"},
                          miner_id=DOWNPROOF_MINER_ID)
            attempts = self._read_log(http.attempts_path)
        self.assertEqual(len(attempts), 1)
        entry = attempts[0]
        self.assertEqual(entry["status"], "success")
        self.assertEqual(entry["http_status"], 200)
        self.assertEqual(entry["intent"], "SLA_COMPLIANCE_GENERAL")
        self.assertEqual(entry["miner_id"], 23112026)
        self.assertEqual(entry["miner_name"], "downproof-uptime")
        self.assertEqual(entry["target"], "https://www.google.com")
        self.assertEqual(entry["cost_usdc"], 0.01)
        self.assertEqual(entry["receipt_id"], "0xdeadbeef")
        self.assertIsNone(entry["error"])
        self.assertTrue(entry["date"].endswith("Z"))

    def test_failure_shaped_reply_is_logged_with_error(self):
        body = {"error": "upstream call failed",
                "message": "upstream call failed: status 500"}

        def failing_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {},
                                         io.BytesIO(json.dumps(body).encode()))

        fd, path = tempfile.mkstemp(suffix="-attempts.json")
        os.close(fd)
        os.unlink(path)
        try:
            with engine_env(ANJOMAN_API_KEY=TEST_KEY), \
                    mock.patch.object(urllib.request, "urlopen", failing_urlopen), \
                    mock.patch.object(telegraph_client, "ATTEMPTS_PATH", path):
                result = ask_telegraph("SLA_COMPLIANCE_GENERAL",
                                       {"service": "https://www.google.com",
                                        "period": "30 days"},
                                       miner_id=DOWNPROOF_MINER_ID)
            self.assertEqual(result["status"], 500)
            attempts = self._read_log(path)
        finally:
            if os.path.exists(path):
                os.unlink(path)
        self.assertEqual(len(attempts), 1)
        entry = attempts[0]
        self.assertEqual(entry["status"], "failed")
        self.assertEqual(entry["http_status"], 500)
        self.assertIn("upstream call failed", entry["error"])
        self.assertIsNone(entry["receipt_id"])
        self.assertEqual(entry["cost_usdc"], 0)

    def test_fallback_shaped_reply_is_logged_as_fallback(self):
        payload = {"result": {"miner_id": "openai", "delivery": "last_resort",
                              "cost_usd": 0},
                   "receipt": None}
        with engine_env(ANJOMAN_API_KEY=TEST_KEY), StubbedHttp(payload) as http:
            ask_telegraph("SERVER_UPTIME_MONITOR_GENERAL",
                          {"url": "https://x.example"})
            attempts = self._read_log(http.attempts_path)
        self.assertEqual(len(attempts), 1)
        entry = attempts[0]
        self.assertEqual(entry["status"], "fallback")
        self.assertIsNone(entry["receipt_id"])
        self.assertEqual(entry["cost_usdc"], 0)


class FakeCheckResult:
    def to_dict(self):
        return {"url": "https://x.example", "is_up": True, "summary": "up"}


class TestLocalDemo(unittest.TestCase):
    def test_local_demo_unaffected_by_engine_update(self):
        urlopen = mock.Mock(side_effect=AssertionError("local demo must not use HTTP"))
        with engine_env(), mock.patch.object(urllib.request, "urlopen", urlopen), \
                mock.patch.object(telegraph_client, "check_url",
                                  lambda url, timeout_s=5: FakeCheckResult()), \
                mock.patch.object(telegraph_client, "sla_verdict",
                                  lambda result, max_latency_ms=1000: {"breached": False}):
            os.environ.pop("ANJOMAN_API_KEY", None)
            for intent in ("SERVER_UPTIME_MONITOR", "SERVER_UPTIME_MONITOR_GENERAL"):
                result = ask_telegraph(intent, {"url": "https://x.example"})
                self.assertEqual(result["mode"], "LOCAL-DEMO (not a Telegraph purchase)")
                self.assertEqual(result["receipt"], "LOCAL-DEMO")
                self.assertEqual(result["cost_usdc"], 0.0)
                self.assertFalse(result["answer"]["sla"]["breached"])
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
