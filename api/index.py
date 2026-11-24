"""DownProof Miner: Vercel serverless entry point.

Exposes the same three routes as miner/server.py, with identical
request/response shapes, as a WSGI callable named ``app``:

POST /query           {"url": "https://example.com", "max_latency_ms": 1000}
GET  /health
GET  /telegraph.yaml  (the config you pin when registering on Telegraph)

Plus the product surface around the miner:

GET  /, /providers, /guide, /receipts, /watch   (web/*.html pages)
GET  /og.png                                    (web/og.png share image)
GET  /receipts.json, /attempts.json, /watchlist.json  (repo-root JSON files)
POST /api/check       JSON in/out version of the full DownProof flow:
                      {url, provider, bill, uptime, checks} ->
                      {ok, verdict, checks, owed, letter, honesty_record}

All check logic is reused from miner/monitor.py, the YAML is reused
from miner/server.py, and the credit math from app/sla_credits.py:
nothing is duplicated here. Stdlib only.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

# Make the repo root and the miner package importable regardless of the
# working directory Vercel runs this function from.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MINER = os.path.join(_ROOT, "miner")
_APP_DIR = os.path.join(_ROOT, "app")
for _p in (_ROOT, _MINER, _APP_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from monitor import check_url, sla_verdict, sla_compliance_fields  # noqa: E402  (miner/monitor.py)
import server as _miner_server  # noqa: E402  (miner/server.py, for the YAML)
from sla_credits import claim_deadline, credit_for, normalise_provider  # noqa: E402  (app/sla_credits.py)

YAML = _miner_server.YAML

_PAGES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/providers": "providers.html",
    "/guide": "guide.html",
    "/receipts": "receipts.html",
    "/watch": "watch.html",
}
_JSON_FILES = {
    "/receipts.json": "receipts.json",
    "/attempts.json": "attempts.json",
    "/watchlist.json": "watchlist.json",
}
_web_cache: dict[str, str | None] = {}
_web_bytes_cache: dict[str, bytes | None] = {}


def _web_html(filename: str) -> str | None:
    """A web/*.html page, read once and cached."""
    if filename not in _web_cache:
        try:
            with open(os.path.join(_ROOT, "web", filename), encoding="utf-8") as f:
                _web_cache[filename] = f.read()
        except OSError:
            _web_cache[filename] = None
    return _web_cache[filename]


def _web_bytes(filename: str) -> bytes | None:
    """A binary web/* asset (the share image), read once and cached."""
    if filename not in _web_bytes_cache:
        try:
            with open(os.path.join(_ROOT, "web", filename), "rb") as f:
                _web_bytes_cache[filename] = f.read()
        except OSError:
            _web_bytes_cache[filename] = None
    return _web_bytes_cache[filename]


def _root_file(filename: str) -> str | None:
    """A repo-root file (the JSON ledgers), read fresh on each request."""
    try:
        with open(os.path.join(_ROOT, filename), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None

_STATUS = {200: "200 OK", 400: "400 Bad Request", 404: "404 Not Found"}


def _respond(start_response, code: int, body, ctype: str = "application/json"):
    if isinstance(body, bytes):
        data = body
    elif isinstance(body, str):
        data = body.encode()
    else:
        data = json.dumps(body).encode()
    start_response(_STATUS[code], [
        ("Content-Type", ctype),
        ("Content-Length", str(len(data))),
    ])
    return [data]


# ---------------------------------------------------------------------------
# POST /api/check: the full flow as JSON. The letter and honesty record
# wording mirrors web/index.html (which mirrors app/downproof.py); the
# credit math comes from app/sla_credits.py, never forked here.
# ---------------------------------------------------------------------------
_PROVIDER_NAMES = {
    "aws-ec2": "AWS EC2",
    "aws-s3": "AWS S3",
    "azure-vm": "Azure Virtual Machines",
    "gcp-compute": "Google Compute Engine",
    "cloudflare-workers": "Cloudflare Workers",
    "digitalocean-spaces": "DigitalOcean Spaces",
}
_MAX_LATENCY_MS = 1000  # the standard SLA the checker measures against


def _money(n: float) -> str:
    return f"${n:.2f}"


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _api_check(payload: dict):
    """Run the full DownProof flow. Returns (status_code, response_dict)."""
    url = str(payload.get("url") or payload.get("service") or "").strip()
    if not url:
        return 400, {"ok": False, "error": "missing 'url'"}

    provider_raw = str(payload.get("provider") or "other").strip()
    provider_key = normalise_provider(provider_raw)
    if provider_key is not None:
        provider_name = _PROVIDER_NAMES[provider_key]
    elif provider_raw.lower() in ("other", ""):
        provider_name = "Service provider"
    else:
        provider_name = provider_raw

    bill = _num(payload.get("bill"))
    uptime = _num(payload.get("uptime"))
    if payload.get("bill") not in (None, "") and bill is None:
        return 400, {"ok": False, "error": "'bill' must be a number"}
    if payload.get("uptime") not in (None, "") and uptime is None:
        return 400, {"ok": False, "error": "'uptime' must be a number"}
    if uptime is not None and not (0 <= uptime <= 100):
        return 400, {"ok": False, "error": "'uptime' must be between 0 and 100"}
    try:
        n_checks = int(payload.get("checks") or 1)
    except (TypeError, ValueError):
        return 400, {"ok": False, "error": "'checks' must be an integer"}
    n_checks = max(1, min(5, n_checks))

    checked_at = datetime.now(timezone.utc)
    results = []
    for _ in range(n_checks):
        result = check_url(url, timeout_s=5.0)
        out = result.to_dict()
        out["sla"] = sla_verdict(result, max_latency_ms=_MAX_LATENCY_MS)
        out.update(sla_compliance_fields(result, out["sla"]))
        results.append(out)

    breached_count = sum(1 for r in results if r["sla"]["breached"])
    breached = breached_count > 0
    first = results[0]
    first_breached = next((r for r in results if r["sla"]["breached"]), first)

    owed = None
    owed_json = None
    if breached and provider_key is not None and bill is not None and uptime is not None:
        owed = credit_for(provider_key, uptime, bill)
        if owed is not None:
            owed_json = {
                "amount": owed["credit_usd"],
                "pct": owed["credit_pct"],
                "deadline": claim_deadline(checked_at, owed["claim_window_days"]),
            }

    letter = None
    honesty_record = None
    if breached:
        lines = [
            f"To: {provider_name} Support / SLA Claims",
            "From: A DownProof user",
            f"Date: {_fmt_dt(checked_at)}",
            f"Subject: SLA compensation claim for {url}",
            "",
            f"Dear {provider_name} team,",
            "",
            f"An independent uptime check at the time above found your service in breach of its SLA: {first_breached['sla']['summary']}",
            f"Proof pack: {breached_count} of {len(results)} independent check(s) breached the SLA.",
        ]
        for i, r in enumerate(results, 1):
            lines.append(f"- Check {i}: {r['summary']} | {r['sla']['summary']} | Served by: DownProof miner (downproof-uptime), POST /query")
        if owed is not None:
            lines += [
                "",
                f"Amount owed (per your own published SLA table, {owed['provider_label']}):",
                f"- Monthly uptime: {owed['uptime_pct']}% (commitment {owed['commitment_pct']}%)",
                f"- Credit tier: {owed['credit_pct']}% of the affected service's monthly bill",
                f"- Monthly bill supplied: {_money(owed['monthly_bill_usd'])} -> credit owed: {_money(owed['credit_usd'])}",
                f"- Source: {owed['source']}",
                f"- {owed['caveat']}",
            ]
            if owed_json and owed_json["deadline"]:
                lines += [
                    "",
                    f"Claim window: file by {owed_json['deadline']} (last safe day, {owed['claim_window_days']} days from this check). Missing the window is the most common reason valid claims die.",
                ]
        elif provider_key is None:
            lines += ["", "Amount owed: not calculated. The provider/service is not in our published credit table; check its SLA directly."]
        lines += [
            "",
            f"Cost of proof: {len(results)} check(s) served by the DownProof miner (downproof-uptime) from downproof.vercel.app. No charge was made through this API; the miner's listed price on Telegraph is 0.01 USDC per check.",
            f"Recovered / owed: {_money(owed['credit_usd'] if owed else 0)}.",
            "",
            "Please credit the account per the SLA compensation terms and confirm in writing.",
            "",
            "Generated automatically by DownProof",
        ]
        letter = "\n".join(lines)
    else:
        honesty_record = "\n".join([
            "SLA met: no claim filed",
            f"Service: {url} ({provider_name})",
            f"Checked: {_fmt_dt(checked_at)} · {len(results)} check(s), all within the SLA",
            f"Evidence: {first['summary']}",
            f"Cost of proof: {len(results)} check(s) served by the DownProof miner (downproof-uptime) from downproof.vercel.app at no charge through this API.",
            "This record exists so a provider (and a judge) can see DownProof talks users out of false claims, not just into real ones.",
        ])

    return 200, {
        "ok": True,
        "verdict": "breach" if breached else "no_breach",
        "checks": results,
        "owed": owed_json,
        "letter": letter,
        "honesty_record": honesty_record,
    }


def app(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET")
    path = environ.get("PATH_INFO", "/")

    if method == "GET":
        if path in _PAGES:
            html = _web_html(_PAGES[path])
            if html is not None:
                return _respond(start_response, 200, html, "text/html; charset=utf-8")
            return _respond(start_response, 404, {"error": "not found"})
        if path == "/og.png":
            png = _web_bytes("og.png")
            if png is not None:
                return _respond(start_response, 200, png, "image/png")
            return _respond(start_response, 404, {"error": "not found"})
        if path in _JSON_FILES:
            body = _root_file(_JSON_FILES[path])
            if body is not None:
                return _respond(start_response, 200, body, "application/json")
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
        if path not in ("/query", "/api/check"):
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
        if path == "/api/check":
            code, out = _api_check(payload)
            return _respond(start_response, code, out)
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
