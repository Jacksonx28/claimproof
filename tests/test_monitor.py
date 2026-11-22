import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "miner"))
from monitor import check_url, sla_verdict, UptimeResult  # noqa: E402


class TestMonitor(unittest.TestCase):
    def test_invalid_scheme_is_down(self):
        r = check_url("ftp://example.com")
        self.assertFalse(r.is_up)
        self.assertIn("DOWN", r.summary)

    def test_unreachable_host_is_down(self):
        r = check_url("https://nonexistent.invalid", timeout_s=3)
        self.assertFalse(r.is_up)
        self.assertIsNotNone(r.error)

    def test_sla_breach_on_down(self):
        v = sla_verdict(UptimeResult("https://x", False, None, 10, "DNS", "down"))
        self.assertTrue(v["breached"])

    def test_sla_breach_on_slow(self):
        v = sla_verdict(UptimeResult("https://x", True, 200, 2500, None, "up"), max_latency_ms=1000)
        self.assertTrue(v["breached"])

    def test_sla_met(self):
        v = sla_verdict(UptimeResult("https://x", True, 200, 120, None, "up"), max_latency_ms=1000)
        self.assertFalse(v["breached"])


if __name__ == "__main__":
    unittest.main()
