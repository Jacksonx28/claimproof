"""DownProof Miner — a Telegraph miner for SERVER_UPTIME_MONITOR.

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

from monitor import check_url, sla_verdict, sla_compliance_fields

# Telegraph Miner Standard v1 (https://anjoman.ai/docs/miners/yaml-config).
# The registered intents are the canonical _GENERAL children: the bare names
# SERVER_UPTIME_MONITOR / SLA_COMPLIANCE are prefixes and are refused.
# id and slug were checked unused against the live registry
# (GET https://devnode.telegraphprotocol.com/api/miners) on 2026-11-23.
YAML = """\
version: "1"
kind: miner
id: 23112026
slug: downproof
protocol: generic
name: downproof-uptime
description: "Deterministic server uptime and SLA compliance checks. Probes a URL live at request time and returns its status, latency and an SLA verdict. No AI in the measurement."
base_url: https://downproof.vercel.app
docs:
  website: https://downproof.vercel.app
  repository: https://github.com/Jacksonx28/downproof
rate_limit_per_sec: 5
cache_ttl_sec: 0
circuit_threshold: 5
circuit_cooldown_seconds: 30
input_schema:
  type: object
  required: [url]
  properties:
    url: {type: string}
    max_latency_ms: {type: integer}
    timeout_s: {type: number}
    sla_target_pct: {type: number, minimum: 0, maximum: 100}
    period: {type: string}
output_schema:
  type: object
  properties:
    url: {type: string}
    is_up: {type: boolean}
    status_code: {type: ["integer", "null"]}
    latency_ms: {type: integer}
    error: {type: ["string", "null"]}
    summary: {type: string}
    service: {type: string}
    period: {type: string}
    uptime_pct: {type: number}
    compliant: {type: boolean}
    sla_target_pct: {type: number}
endpoints:
  - path: /query
    external_path: /query
    method: POST
    description: "Probe one URL now and report whether it is up, its HTTP status and latency, and whether it meets its SLA. Serves SERVER_UPTIME_MONITOR_GENERAL (is the service up?) and SLA_COMPLIANCE_GENERAL (did it meet the SLA?). The verdict breaches when the service is down or slower than max_latency_ms; when sla_target_pct is supplied, the single-check availability (100 when up, 0 when down) is also compared with that target. The answer carries the SLA_COMPLIANCE response fields service, period, uptime_pct, compliant and, when supplied, sla_target_pct."
    intents: [SERVER_UPTIME_MONITOR_GENERAL, SLA_COMPLIANCE_GENERAL]
    params:
      body:
        required:
          - name: url
            type: string
            intents: ["*"]
            description: "The service to check, as a full URL including the scheme, e.g. https://example.com. A bare service name is not enough: it must be a reachable URL."
        optional:
          - name: max_latency_ms
            type: integer
            intents: ["*"]
            description: "Latency SLA limit in milliseconds. The check breaches its SLA when latency exceeds this. Defaults to 1000."
          - name: timeout_s
            type: number
            intents: ["*"]
            description: "Per-check timeout in seconds. Defaults to 5."
          - name: sla_target_pct
            type: number
            intents: [SLA_COMPLIANCE_GENERAL]
            description: "Optional SLA availability target in percent, 0 to 100. When supplied it is echoed as sla_target_pct and the single-check availability (100 when up, 0 when down) is compared against it for the compliant verdict."
          - name: period
            type: string
            intents: [SLA_COMPLIANCE_GENERAL]
            description: "Accepted for SLA_COMPLIANCE requests. DownProof measures at the instant of the call, so the response always reports period 'instant (single live check)' rather than a historical window."
semantics:
  signal_mapping:
    label_field: summary
  supported_intents:
    - SERVER_UPTIME_MONITOR_GENERAL
    - SLA_COMPLIANCE_GENERAL
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
            self._send(200, {"ok": True, "miner": "downproof-uptime", "intents": ["SERVER_UPTIME_MONITOR", "SLA_COMPLIANCE"]})
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
        url = payload.get("url") or payload.get("service") or ""
        if not url:
            self._send(400, {"error": "missing 'url'"})
            return
        result = check_url(url, timeout_s=float(payload.get("timeout_s", 5)))
        out = result.to_dict()
        out["sla"] = sla_verdict(result, max_latency_ms=int(payload.get("max_latency_ms", 1000)))
        target = payload.get("sla_target_pct")
        try:
            target = float(target) if target is not None else None
        except (TypeError, ValueError):
            target = None
        out.update(sla_compliance_fields(result, out["sla"], sla_target_pct=target))
        self._send(200, out)

    def log_message(self, *args):  # keep logs quiet
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"DownProof miner listening on :{port}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
