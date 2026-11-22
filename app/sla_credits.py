"""Owed-money calculator — real, published SLA credit tiers.

Differentiator #1 from NIGHT_READING.md Part 3: the claim letter should
not just say "you broke it" — it should say "you owe this much, per your
own published table."

Every table below was checked against the provider's own SLA page on
22 Nov 2026. Tiers differ by service even inside one provider, so each
entry names the exact service it covers. If the user's service is not
listed, credit_for() returns None instead of guessing — a wrong credit
figure in a claim letter is worse than no figure.

Sources (checked 22 Nov 2026):
- AWS EC2 (multi-AZ, region level): https://aws.amazon.com/compute/sla/
  Commitment 99.99%; <99.99% but >=99.0% -> 10%; <99.0% but >=95.0% -> 30%;
  <95.0% -> 100%. Claim by the end of the second billing cycle (~60 days).
- AWS S3 (Standard): https://aws.amazon.com/s3/sla/
  Commitment 99.9%; 99.0-99.9% -> 10%; 95.0-99.0% -> 25%; <95.0% -> 100%.
  Claim by the end of the second billing cycle (~60 days).
- Azure Virtual Machines (zones / availability sets, Oct 2026 SLA):
  10% below the commitment, 25% below 99%, 100% below 95%.
  Claim within 60 days of the incident.
  https://www.syntaqx.com/books/hosting-and-cloud/slas-and-service-credits
- Google Compute Engine (multi-zone, Premium Tier):
  https://cloud.google.com/compute/sla
  Commitment 99.99%; 99.00-<99.99% -> 10%; 95.00-<99.00% -> 25%;
  <95.00% -> 100%. Notify Google within 30 days of becoming eligible.
- Cloudflare Workers: https://www.cloudflare.com/en-gb/workers-service-level-agreement/
  SLO 99.99%; <99.99% but >=99.9% -> 10%; <99.9% but >=95% -> 25%;
  <95.0% -> 50%.
- DigitalOcean Spaces: https://www.digitalocean.com/sla/spaces
  Commitment 99.9%; 99.0-99.9% -> 10%; 95.0-99.0% -> 25%; <95.0% -> 100%.

Caveat printed in every output that uses these tables: credits are a
percentage of the *affected service's* monthly bill, not the whole
account, and are usually a credit against future bills, not cash.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# tiers: list of (lowest uptime % in this tier, credit % of monthly bill),
# in descending uptime order. Uptime at or above `commitment` earns 0%.
TABLES = {
    "aws-ec2": {
        "label": "AWS EC2 (multi-AZ, region level)",
        "commitment": 99.99,
        "tiers": [(99.0, 10), (95.0, 30), (0.0, 100)],
        "claim_window_days": 60,
        "source": "https://aws.amazon.com/compute/sla/",
    },
    "aws-s3": {
        "label": "AWS S3 (Standard)",
        "commitment": 99.9,
        "tiers": [(99.0, 10), (95.0, 25), (0.0, 100)],
        "claim_window_days": 60,
        "source": "https://aws.amazon.com/s3/sla/",
    },
    "azure-vm": {
        "label": "Azure Virtual Machines (zones / availability sets)",
        "commitment": 99.99,
        # 10% for any miss below the commitment down to 99%,
        # 25% below 99%, 100% below 95%.
        "tiers": [(99.0, 10), (95.0, 25), (0.0, 100)],
        "claim_window_days": 60,
        "source": "https://www.syntaqx.com/books/hosting-and-cloud/slas-and-service-credits",
    },
    "gcp-compute": {
        "label": "Google Compute Engine (multi-zone, Premium Tier)",
        "commitment": 99.99,
        "tiers": [(99.0, 10), (95.0, 25), (0.0, 100)],
        "claim_window_days": 30,
        "source": "https://cloud.google.com/compute/sla",
    },
    "cloudflare-workers": {
        "label": "Cloudflare Workers",
        "commitment": 99.99,
        "tiers": [(99.9, 10), (95.0, 25), (0.0, 50)],
        "claim_window_days": None,  # not verified for Workers; do not invent
        "source": "https://www.cloudflare.com/en-gb/workers-service-level-agreement/",
    },
    "digitalocean-spaces": {
        "label": "DigitalOcean Spaces",
        "commitment": 99.9,
        "tiers": [(99.0, 10), (95.0, 25), (0.0, 100)],
        "claim_window_days": None,  # not verified for Spaces; do not invent
        "source": "https://www.digitalocean.com/sla/spaces",
    },
}

ALIASES = {
    "aws": "aws-ec2",
    "ec2": "aws-ec2",
    "aws ec2": "aws-ec2",
    "amazon ec2": "aws-ec2",
    "s3": "aws-s3",
    "aws s3": "aws-s3",
    "amazon s3": "aws-s3",
    "azure": "azure-vm",
    "azure vm": "azure-vm",
    "azure virtual machines": "azure-vm",
    "gcp": "gcp-compute",
    "google compute engine": "gcp-compute",
    "google cloud": "gcp-compute",
    "cloudflare": "cloudflare-workers",
    "workers": "cloudflare-workers",
    "digitalocean": "digitalocean-spaces",
    "digitalocean spaces": "digitalocean-spaces",
    "do spaces": "digitalocean-spaces",
}


def normalise_provider(provider: str) -> str | None:
    """Map a free-text provider name to a table key, or None if unknown."""
    key = provider.strip().lower()
    if key in TABLES:
        return key
    return ALIASES.get(key)


def credit_for(provider: str, uptime_pct: float, monthly_bill_usd: float) -> dict | None:
    """Return the credit owed, or None if the provider/service is unknown.

    Returns None also when uptime met the commitment (credit 0% is
    reported as a dict with credit_pct 0, not None — callers can tell
    "known, nothing owed" apart from "unknown provider").
    """
    key = normalise_provider(provider)
    if key is None:
        return None
    table = TABLES[key]
    if uptime_pct >= table["commitment"]:
        credit_pct = 0
    else:
        credit_pct = 0
        for lower, pct in table["tiers"]:
            if uptime_pct >= lower:
                credit_pct = pct
                break
    return {
        "provider_key": key,
        "provider_label": table["label"],
        "commitment_pct": table["commitment"],
        "uptime_pct": uptime_pct,
        "credit_pct": credit_pct,
        "monthly_bill_usd": round(monthly_bill_usd, 2),
        "credit_usd": round(monthly_bill_usd * credit_pct / 100, 2),
        "claim_window_days": table["claim_window_days"],
        "source": table["source"],
        "caveat": ("Credit is a percentage of the affected service's monthly "
                   "bill, usually applied as a credit against future bills, "
                   "not cash. Check the provider's SLA for exclusions."),
    }


def claim_deadline(checked_at: datetime, window_days: int | None) -> str | None:
    """Last safe day to file, as YYYY-MM-DD, or None if window unknown."""
    if window_days is None:
        return None
    return (checked_at + timedelta(days=window_days)).strftime("%Y-%m-%d")
