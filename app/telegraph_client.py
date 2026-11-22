"""Telegraph access for DownProof.

Two modes, labelled honestly in every output (hackathon rules require
accurate claims about what was actually verified):

- LIVE: TELEGRAPH_ENGINE_URL is set -> POST {engine}/engine/v1/ask
  (auto-routed; this is the only path that counts as a real Telegraph
  purchase and as miner volume). Receipts come from the engine response.
- LOCAL_DEMO: no engine configured -> call our own miner directly.
  Receipts are marked LOCAL-DEMO. This proves the workflow end-to-end
  before you have a funded Telegraph account, and must never be
  presented to judges as a Telegraph purchase.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "miner"))
from monitor import check_url, sla_verdict  # noqa: E402

PRICE_USDC = 0.01  # per request, matches miner/telegraph.yaml


def ask_telegraph(intent: str, payload: dict) -> dict:
    engine = os.environ.get("TELEGRAPH_ENGINE_URL", "").rstrip("/")
    if engine:
        body = json.dumps({"intent": intent, "params": payload}).encode()
        req = urllib.request.Request(f"{engine}/engine/v1/ask", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return {"mode": "LIVE", "intent": intent, "answer": data.get("answer", data),
                "receipt": data.get("receipt") or data.get("transaction") or "see engine response",
                "cost_usdc": data.get("cost_usdc", PRICE_USDC)}
    # Local demo fallback
    if intent in ("SERVER_UPTIME_MONITOR", "SLA_COMPLIANCE"):
        result = check_url(payload["url"], timeout_s=float(payload.get("timeout_s", 5)))
        answer = result.to_dict()
        answer["sla"] = sla_verdict(result, max_latency_ms=int(payload.get("max_latency_ms", 1000)))
        return {"mode": "LOCAL-DEMO (not a Telegraph purchase)", "intent": intent,
                "answer": answer, "receipt": "LOCAL-DEMO", "cost_usdc": 0.0}
    raise ValueError(f"Intent {intent} not served by the local demo miner")
