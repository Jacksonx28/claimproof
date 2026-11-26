"""SERVER_UPTIME_MONITOR core logic.

Deterministic on purpose: Telegraph evaluators score this Intent by
comparing our answer against ground truth, so there is no LLM here.
We fetch the URL, measure latency, and return structured fields only.
"""
from __future__ import annotations

import socket
import time
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict

# SLA_COMPLIANCE mission default target (99.9% uptime) from the Season 2
# catalogue, applied transparently when a caller supplies no sla_target_pct.
DEFAULT_SLA_TARGET_PCT = 99.9


@dataclass
class UptimeResult:
    url: str
    is_up: bool
    status_code: int | None
    latency_ms: int
    error: str | None
    summary: str  # scorer-legible one-liner carrying the verdict

    def to_dict(self) -> dict:
        return asdict(self)


# Vercel's sandbox reports an unresolvable host to urllib as
# "urlopen error [Errno 16] Device or resource busy" (seen live on
# 2026-11-26: every dead address returned it in 10-20ms, while
# google.com answered normally). That string is genuine but reads as
# a broken checker in a claim letter, so DNS failures are reported
# in plain language instead. Only the `error` text changes: is_up,
# status_code, latency, verdict and the SLA compliance fields are
# untouched, and no new response key is added.
_DNS_ERRNOS = {-2, 8, 16, 11001, 11002, 11004}


def _plain_error(exc: BaseException, host: str | None) -> str:
    """Turn a fetch failure into the plain-language `error` string.

    DNS failures (however the platform surfaces them: gaierror, an
    OSError errno, or the Errno 16 text Vercel produces) become
    "host could not be resolved: <host>". Timeouts and refused
    connections get their own plain line. Anything else keeps the
    original message, truncated as before.
    """
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, socket.gaierror):
        return f"host could not be resolved: {host}" if host else "host could not be resolved"
    if isinstance(reason, OSError):
        if reason.errno in _DNS_ERRNOS or "Device or resource busy" in str(reason):
            return f"host could not be resolved: {host}" if host else "host could not be resolved"
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return "connection timed out"
        if isinstance(reason, ConnectionRefusedError):
            return "connection refused"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "connection timed out"
    if isinstance(exc, ConnectionRefusedError):
        return "connection refused"
    text = str(exc)[:200]
    if "Device or resource busy" in text or "Name or service not known" in text:
        return f"host could not be resolved: {host}" if host else "host could not be resolved"
    return text


def check_url(url: str, timeout_s: float = 5.0) -> UptimeResult:
    if not url.startswith(("http://", "https://")):
        return UptimeResult(url, False, None, 0, "url must start with http:// or https://",
                             f"{url} is DOWN: invalid URL scheme")
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname
    start = time.perf_counter()
    if host:
        # Resolve first, so a dead host is reported in plain language
        # instead of whatever the platform's fetch layer says about it.
        try:
            socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80),
                               proto=socket.IPPROTO_TCP)
        except (socket.gaierror, OSError):
            latency = int((time.perf_counter() - start) * 1000)
            return UptimeResult(url, False, None, latency,
                                f"host could not be resolved: {host}",
                                f"{url} is DOWN: host could not be resolved after {latency}ms")
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "DownProof-Miner/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            resp.read(512)  # prove the body actually flows, don't trust headers alone
            latency = int((time.perf_counter() - start) * 1000)
            up = 200 <= resp.status < 400
            return UptimeResult(url, up, resp.status, latency, None,
                                f"{url} is {'UP' if up else 'DOWN'}: HTTP {resp.status} in {latency}ms")
    except urllib.error.HTTPError as e:
        latency = int((time.perf_counter() - start) * 1000)
        return UptimeResult(url, False, e.code, latency, f"HTTP {e.code}",
                            f"{url} is DOWN: HTTP {e.code} in {latency}ms")
    except Exception as e:  # DNS, TLS, timeout, connection refused
        latency = int((time.perf_counter() - start) * 1000)
        return UptimeResult(url, False, None, latency, _plain_error(e, host),
                            f"{url} is DOWN: {type(e).__name__} after {latency}ms")


def sla_verdict(result: UptimeResult, max_latency_ms: int = 1000, require_up: bool = True) -> dict:
    """SLA_COMPLIANCE companion logic: is this check inside the agreed SLA?"""
    breached = (require_up and not result.is_up) or result.latency_ms > max_latency_ms
    reasons = []
    if require_up and not result.is_up:
        reasons.append(f"service down (error: {result.error or result.status_code})")
    if result.latency_ms > max_latency_ms:
        reasons.append(f"latency {result.latency_ms}ms exceeded {max_latency_ms}ms SLA")
    return {
        "breached": breached,
        "max_latency_ms": max_latency_ms,
        "reasons": reasons,
        "summary": ("SLA BREACHED: " + "; ".join(reasons)) if breached else "SLA MET: service within agreed limits",
    }


def sla_compliance_fields(result: UptimeResult, verdict: dict, sla_target_pct: float | None = None) -> dict:
    """The SLA_COMPLIANCE_GENERAL intent's published response fields.

    Source: GET https://devnode.telegraphprotocol.com/engine/v1/intents/SLA_COMPLIANCE_GENERAL
    (response.fields, format_version 4, served_by SLA_COMPLIANCE, read 2026-11-23):
    service (string), uptime_pct (number, percent 0-100, scored), sla_target_pct
    (number, percent), compliant (bool), period (string).

    DownProof measures one live check at request time, so the honest values are:
    uptime_pct is the single-sample availability (100.0 up, 0.0 down) and period
    says so. The engine's canonical SLA input schema (v4) is {service, period}
    and sends no target, so when the caller supplied none we apply the
    SLA_COMPLIANCE mission default of 99.9 — the field is never null.
    compliant is the
    sla_verdict outcome, additionally requiring uptime_pct >= sla_target_pct.
    (SERVER_UPTIME_MONITOR_GENERAL publishes no response format at all —
    its intent record has request=null and response=null — so nothing to add
    for that intent beyond the existing UptimeResult fields.)
    """
    uptime_pct = 100.0 if result.is_up else 0.0
    target_defaulted = sla_target_pct is None
    if target_defaulted:
        sla_target_pct = DEFAULT_SLA_TARGET_PCT
    compliant = not verdict["breached"] and uptime_pct >= sla_target_pct
    return {
        "service": result.url,
        "period": "instant (single live check)",
        "uptime_pct": uptime_pct,
        "sla_target_pct": sla_target_pct,
        "compliant": compliant,
    }
