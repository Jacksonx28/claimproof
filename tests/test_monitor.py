import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "miner"))
from monitor import check_url, sla_verdict, sla_compliance_fields, UptimeResult  # noqa: E402


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

    # SLA_COMPLIANCE_GENERAL published response fields (devnode intent record,
    # format_version 4): service, uptime_pct, sla_target_pct, compliant, period.
    def test_compliance_fields_up_and_met(self):
        r = UptimeResult("https://x", True, 200, 120, None, "up")
        f = sla_compliance_fields(r, sla_verdict(r, max_latency_ms=1000))
        self.assertEqual(f["service"], "https://x")
        self.assertEqual(f["uptime_pct"], 100.0)
        self.assertTrue(f["compliant"])
        self.assertEqual(f["period"], "instant (single live check)")

    def test_compliance_fields_default_target_when_none_supplied(self):
        # The engine's canonical SLA input schema sends no target, so the
        # mission default 99.9 is applied, never left null. The response
        # carries only the canonical fields: an extra sla_target_note key
        # broke the engine's strict adapter (upstream 500s), so it is gone.
        r = UptimeResult("https://x", True, 200, 120, None, "up")
        f = sla_compliance_fields(r, sla_verdict(r, max_latency_ms=1000))
        self.assertEqual(f["sla_target_pct"], 99.9)
        self.assertNotIn("sla_target_note", f)
        self.assertTrue(f["compliant"])  # 100.0 >= 99.9

    def test_compliance_fields_down(self):
        r = UptimeResult("https://x", False, None, 10, "DNS", "down")
        f = sla_compliance_fields(r, sla_verdict(r))
        self.assertEqual(f["uptime_pct"], 0.0)
        self.assertFalse(f["compliant"])
        self.assertEqual(f["sla_target_pct"], 99.9)  # default applied, not null

    def test_compliance_fields_target_echoed_and_applied(self):
        r = UptimeResult("https://x", True, 200, 120, None, "up")
        f = sla_compliance_fields(r, sla_verdict(r, max_latency_ms=1000), sla_target_pct=99.9)
        self.assertEqual(f["sla_target_pct"], 99.9)
        self.assertNotIn("sla_target_note", f)  # response never carries the note key
        self.assertTrue(f["compliant"])  # 100.0 >= 99.9 and latency within SLA

    def test_compliance_fields_latency_breach_still_noncompliant(self):
        r = UptimeResult("https://x", True, 200, 2500, None, "up")
        f = sla_compliance_fields(r, sla_verdict(r, max_latency_ms=1000), sla_target_pct=99.0)
        self.assertFalse(f["compliant"])  # availability fine, latency SLA breached


if __name__ == "__main__":
    unittest.main()
