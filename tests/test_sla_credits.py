import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from sla_credits import claim_deadline, credit_for, normalise_provider  # noqa: E402
from datetime import datetime, timezone


class TestSlaCredits(unittest.TestCase):
    def test_aws_ec2_tiers(self):
        self.assertEqual(credit_for("AWS EC2", 99.5, 1000)["credit_pct"], 10)
        self.assertEqual(credit_for("AWS EC2", 99.5, 1000)["credit_usd"], 100)
        self.assertEqual(credit_for("aws-ec2", 98.0, 1000)["credit_pct"], 30)
        self.assertEqual(credit_for("aws-ec2", 98.0, 1000)["credit_usd"], 300)
        self.assertEqual(credit_for("aws-ec2", 94.0, 1000)["credit_pct"], 100)
        self.assertEqual(credit_for("aws-ec2", 99.99, 1000)["credit_pct"], 0)

    def test_aws_s3_tiers(self):
        self.assertEqual(credit_for("aws-s3", 99.5, 200)["credit_usd"], 20)  # 10%
        self.assertEqual(credit_for("aws-s3", 98.0, 200)["credit_pct"], 25)
        self.assertEqual(credit_for("aws-s3", 94.0, 200)["credit_pct"], 100)

    def test_azure_tiers(self):
        self.assertEqual(credit_for("azure-vm", 99.5, 1000)["credit_pct"], 10)
        self.assertEqual(credit_for("azure-vm", 98.0, 1000)["credit_pct"], 25)
        self.assertEqual(credit_for("azure-vm", 94.0, 1000)["credit_pct"], 100)

    def test_gcp_and_cloudflare(self):
        self.assertEqual(credit_for("gcp-compute", 98.0, 1000)["credit_pct"], 25)
        self.assertEqual(credit_for("gcp-compute", 94.0, 1000)["credit_pct"], 100)
        self.assertEqual(credit_for("cloudflare-workers", 99.95, 1000)["credit_pct"], 10)
        self.assertEqual(credit_for("cloudflare-workers", 98.0, 1000)["credit_pct"], 25)
        self.assertEqual(credit_for("cloudflare-workers", 94.0, 1000)["credit_pct"], 50)

    def test_digitalocean_spaces(self):
        self.assertEqual(credit_for("digitalocean-spaces", 98.0, 400)["credit_usd"], 100)  # 25%

    def test_unknown_provider_is_none_not_a_guess(self):
        self.assertIsNone(credit_for("Some Random Host", 98.0, 1000))
        self.assertIsNone(normalise_provider("Some Random Host"))

    def test_claim_deadline(self):
        checked = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(claim_deadline(checked, 60), "2027-01-21")
        self.assertIsNone(claim_deadline(checked, None))


if __name__ == "__main__":
    unittest.main()
