"""Nightly watchlist recheck for DownProof.

Reads watchlist.json at the repo root, checks every listed service
against the public DownProof miner (POST https://downproof.vercel.app/query),
and appends one dated result entry per service to watch_results.json
at the repo root.

Honesty note: this talks to the public miner directly, which is free.
It is NOT a paid Telegraph engine purchase, and its results must never
be presented as engine purchases. Paid purchases live in receipts.json
and on the /receipts page. Python stdlib only.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MINER_QUERY_URL = os.environ.get("DOWNPROOF_QUERY_URL", "https://downproof.vercel.app/query")
MAX_LATENCY_MS = 1000


def check_service(service: dict, checked_at: str) -> dict:
    url = service.get("url", "")
    entry = {
        "checked_at": checked_at,
        "url": url,
        "provider": service.get("provider", "Other"),
        "source": "public miner (free, not a paid engine purchase)",
    }
    body = json.dumps({"url": url, "max_latency_ms": MAX_LATENCY_MS}).encode()
    req = urllib.request.Request(MINER_QUERY_URL, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        sla = data.get("sla") or {}
        entry.update({
            "is_up": data.get("is_up"),
            "status_code": data.get("status_code"),
            "latency_ms": data.get("latency_ms"),
            "breached": bool(sla.get("breached")),
            "summary": data.get("summary"),
            "sla_summary": sla.get("summary"),
        })
    except Exception as e:  # the check itself failed; record that honestly
        entry.update({"is_up": None, "breached": None, "error": str(e)[:200]})
    return entry


def main() -> int:
    with open(os.path.join(ROOT, "watchlist.json"), encoding="utf-8") as f:
        services = json.load(f).get("services", [])
    results_path = os.path.join(ROOT, "watch_results.json")
    try:
        with open(results_path, encoding="utf-8") as f:
            log = json.load(f)
    except (OSError, ValueError):
        log = {"results": []}
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for service in services:
        entry = check_service(service, checked_at)
        log.setdefault("results", []).append(entry)
        print(f"{entry['url']}: up={entry.get('is_up')} breached={entry.get('breached')}")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)
        f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
