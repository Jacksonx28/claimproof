"""SERVER_UPTIME_MONITOR core logic.

Deterministic on purpose: Telegraph evaluators score this Intent by
comparing our answer against ground truth, so there is no LLM here.
We fetch the URL, measure latency, and return structured fields only.
"""
from __future__ import annotations

import time
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict


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


def check_url(url: str, timeout_s: float = 5.0) -> UptimeResult:
    if not url.startswith(("http://", "https://")):
        return UptimeResult(url, False, None, 0, "url must start with http:// or https://",
                             f"{url} is DOWN: invalid URL scheme")
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "SLAWitness-Miner/0.1"})
    start = time.perf_counter()
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
        return UptimeResult(url, False, None, latency, str(e)[:200],
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
