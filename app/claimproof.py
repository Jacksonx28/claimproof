"""ClaimProof — Mission 15: Consumer Automation (Telegraph Season II)

Give it a service URL and its SLA. It buys uptime + SLA intelligence,
and if the SLA is breached it drafts a compensation claim with the
receipts and a cost line attached — the exact artefact Mission 15 asks for.

Usage:
  python3 app/claimproof.py --url https://example.com --provider "Example ISP" \
      --max-latency-ms 1000 --out examples/
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from telegraph_client import ask_telegraph


def build_claim(url: str, provider: str, max_latency_ms: int, customer: str = "A ClaimProof user") -> dict:
    uptime = ask_telegraph("SERVER_UPTIME_MONITOR", {"url": url, "max_latency_ms": max_latency_ms})
    answer = uptime["answer"]
    sla = answer.get("sla", {})
    breached = bool(sla.get("breached"))
    total_cost = uptime["cost_usdc"]
    claim_text = None
    if breached:
        claim_text = f"""To: {provider} — Support / SLA Claims
From: {customer}
Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
Subject: SLA compensation claim for {url}

Dear {provider} team,

An independent uptime check at the time above found your service in breach
of its SLA: {sla.get('summary')}

Evidence (verifiable, bought through Telegraph):
- Check: {answer.get('summary')}
- Mode: {uptime['mode']}
- Receipt: {uptime['receipt']}
- Cost of intelligence: ${total_cost:.2f}

Please credit the account per the SLA compensation terms and confirm in writing.

— Generated automatically by ClaimProof"""
    return {"url": url, "provider": provider, "checked_at": datetime.now(timezone.utc).isoformat(),
            "mode": uptime["mode"], "answer": answer, "breached": breached,
            "receipt": uptime["receipt"], "total_cost_usdc": total_cost, "claim_text": claim_text}


def main() -> None:
    ap = argparse.ArgumentParser(description="ClaimProof — SLA breach claim agent")
    ap.add_argument("--url", required=True)
    ap.add_argument("--provider", default="Service provider")
    ap.add_argument("--max-latency-ms", type=int, default=1000)
    ap.add_argument("--out", default=".")
    args = ap.parse_args()

    result = build_claim(args.url, args.provider, args.max_latency_ms)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "result.json"), "w") as f:
        json.dump(result, f, indent=2)
    if result["claim_text"]:
        with open(os.path.join(args.out, "claim.md"), "w") as f:
            f.write("# SLA compensation claim\n\n```\n" + result["claim_text"] + "\n```\n")
        print(f"SLA BREACHED — claim drafted to {args.out}/claim.md | cost ${result['total_cost_usdc']:.2f} | receipt {result['receipt']}")
    else:
        print(f"SLA MET — no claim needed | {result['answer'].get('summary')} | cost ${result['total_cost_usdc']:.2f}")


if __name__ == "__main__":
    main()
