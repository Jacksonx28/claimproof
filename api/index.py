"""DownProof Miner — Vercel serverless entry point.

Exposes the same three routes as miner/server.py, with identical
request/response shapes, as a WSGI callable named ``app``:

POST /query           {"url": "https://example.com", "max_latency_ms": 1000}
GET  /health
GET  /telegraph.yaml  (the config you pin when registering on Telegraph)

All check logic is reused from miner/monitor.py and the YAML is reused
from miner/server.py — nothing is duplicated here. Stdlib only.
"""
from __future__ import annotations

import json
import os
import sys

# Make the repo root and the miner package importable regardless of the
# working directory Vercel runs this function from.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MINER = os.path.join(_ROOT, "miner")
for _p in (_ROOT, _MINER):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from monitor import check_url, sla_verdict, sla_compliance_fields  # noqa: E402  (miner/monitor.py)
import server as _miner_server  # noqa: E402  (miner/server.py, for the YAML)

YAML = _miner_server.YAML

_WEB_INDEX = os.path.join(_ROOT, "web", "index.html")
_web_html: str | None = None


def _index_html() -> str | None:
    """The DownProof web UI (web/index.html), read once and cached."""
    global _web_html
    if _web_html is None:
        try:
            with open(_WEB_INDEX, encoding="utf-8") as f:
                _web_html = f.read()
        except OSError:
            return None
    return _web_html

_STATUS = {200: "200 OK", 400: "400 Bad Request", 404: "404 Not Found"}


def _respond(start_response, code: int, body, ctype: str = "application/json"):
    data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
    start_response(_STATUS[code], [
        ("Content-Type", ctype),
        ("Content-Length", str(len(data))),
    ])
    return [data]


def app(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/")

    if method == "GET":
        if path in ("/", "/index.html"):
            html = _index_html()
            if html is not None:
                return _respond(start_response, 200, html, "text/html; charset=utf-8")
            return _respond(start_response, 404, {"error": "not found"})
        if path == "/health":
            return _respond(start_response, 200, {
                "ok": True,
                "miner": "downproof-uptime",
                "intents": ["SERVER_UPTIME_MONITOR", "SLA_COMPLIANCE"],
            })
        if path == "/telegraph.yaml":
            return _respond(start_response, 200, YAML, "text/yaml")
        return _respond(start_response, 404, {"error": "not found"})

    if method == "POST":
        if path != "/query":
            return _respond(start_response, 404, {"error": "not found"})
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except (TypeError, ValueError):
            length = 0
        raw = environ["wsgi.input"].read(length) if length > 0 else b""
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            return _respond(start_response, 400, {"error": "invalid JSON body"})
        url = payload.get("url") or payload.get("service") or ""
        if not url:
            return _respond(start_response, 400, {"error": "missing 'url'"})
        result = check_url(url, timeout_s=float(payload.get("timeout_s", 5)))
        out = result.to_dict()
        out["sla"] = sla_verdict(result, max_latency_ms=int(payload.get("max_latency_ms", 1000)))
        target = payload.get("sla_target_pct")
        try:
            target = float(target) if target is not None else None
        except (TypeError, ValueError):
            target = None
        out.update(sla_compliance_fields(result, out["sla"], sla_target_pct=target))
        return _respond(start_response, 200, out)

    return _respond(start_response, 404, {"error": "not found"})
