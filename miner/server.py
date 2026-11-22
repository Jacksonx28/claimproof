"""ClaimProof Miner — a Telegraph miner for SERVER_UPTIME_MONITOR.

Run:  python3 miner/server.py   (listens on :8080, override with PORT)
POST /query  {"url": "https://example.com", "max_latency_ms": 1000}
GET  /health
GET  /telegraph.yaml  (the config you pin when registering on Telegraph)
Stdlib only — judges can run this with zero installs.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from monitor import check_url, sla_verdict

YAML = """\
name: claimproof-uptime
description: Deterministic server uptime and SLA compliance checks.
intents:
  - SERVER_UPTIME_MONITOR
  - SLA_COMPLIANCE
api:
  base_url: https://YOUR-PUBLIC-URL.example  # replace after deploying
  endpoints:
    - path: /query
      method: POST
pricing:
  amount_usdc: 0.01
  model: per_request
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict | str, ctype: str = "application/json"):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "miner": "claimproof-uptime", "intents": ["SERVER_UPTIME_MONITOR", "SLA_COMPLIANCE"]})
        elif self.path == "/telegraph.yaml":
            self._send(200, YAML, "text/yaml")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/query":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            self._send(400, {"error": "invalid JSON body"})
            return
        url = payload.get("url", "")
        if not url:
            self._send(400, {"error": "missing 'url'"})
            return
        result = check_url(url, timeout_s=float(payload.get("timeout_s", 5)))
        out = result.to_dict()
        out["sla"] = sla_verdict(result, max_latency_ms=int(payload.get("max_latency_ms", 1000)))
        self._send(200, out)

    def log_message(self, *args):  # keep logs quiet
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"ClaimProof miner listening on :{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
