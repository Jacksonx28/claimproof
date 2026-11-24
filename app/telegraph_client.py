"""Telegraph access for DownProof.

Two modes, labelled honestly in every output (hackathon rules require
accurate claims about what was actually verified):

- LIVE: an Anjoman API key is available (env ANJOMAN_API_KEY), or a
  live ask is explicitly requested, or a target miner id is given.
  Asks go to the Telegraph engine backend (default
  https://backend.telegraphprotocol.com, override with
  TELEGRAPH_ENGINE_URL) as POST /engine/ask (auto-routed) or
  POST /engine/ask/<miner_id> (targeted at one miner), with header
  "Authorization: Bearer anjoman_<key>". Payment defaults to the
  account escrow. This is the only path that counts as a real
  Telegraph purchase and as miner volume. Receipts come from the
  engine response. Every live ask, success or failure, is appended
  to attempts.json at the repo root (see _log_attempt).
- LOCAL_DEMO: no key and no live request -> call our own miner
  directly. Receipts are marked LOCAL-DEMO and the cost is 0. This
  proves the workflow end-to-end before a funded Telegraph account
  exists, and must never be presented to judges as a Telegraph
  purchase.

The API key is read from the environment only. It is never printed,
logged, or included in any returned value or error message.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "miner"))
from monitor import check_url, sla_verdict  # noqa: E402

PRICE_USDC = 0.01  # per request, matches miner/telegraph.yaml
DEFAULT_ENGINE_URL = "https://backend.telegraphprotocol.com"
DOWNPROOF_MINER_ID = "23112026"  # our registered miner (slug: downproof)
LOCAL_INTENTS = ("SERVER_UPTIME_MONITOR", "SERVER_UPTIME_MONITOR_GENERAL",
                 "SLA_COMPLIANCE", "SLA_COMPLIANCE_GENERAL")
ATTEMPTS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "attempts.json"))


class MissingApiKeyError(RuntimeError):
    """A live engine ask was attempted without ANJOMAN_API_KEY set."""


def _engine_base() -> str:
    return os.environ.get("TELEGRAPH_ENGINE_URL", "").rstrip("/") or DEFAULT_ENGINE_URL


def _api_key() -> str | None:
    return os.environ.get("ANJOMAN_API_KEY") or None


def _require_key() -> str:
    key = _api_key()
    if not key:
        raise MissingApiKeyError(
            "ANJOMAN_API_KEY is not set. A live Telegraph engine ask needs "
            "an Anjoman API key in the ANJOMAN_API_KEY environment variable. "
            "Set it and retry, or run without a live request to use the "
            "LOCAL-DEMO miner instead.")
    return key


def _engine_request(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    """One authenticated engine call. Returns (http_status, parsed_body).

    The parsed body is returned as-is; its field names are the
    engine's, not ours. A non-JSON body comes back as {"raw": text}.
    HTTP error statuses are returned the same way, not raised, so the
    caller sees exactly what the engine said.
    """
    key = _require_key()
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"Bearer {key}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{_engine_base()}{path}", data=data,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, text = resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, text = e.code, e.read().decode("utf-8", "replace")
    try:
        return status, json.loads(text)
    except ValueError:
        return status, {"raw": text}


def _attempt_entry(intent: str, params: dict, miner_id: str | None,
                   status: int, data: object) -> dict:
    """Build one attempts.json entry from a live engine reply.

    The engine body is read defensively, the same way ask_telegraph
    derives its convenience fields: a 200 with a receipt is a success,
    a 200 whose result is marked as a last-resort delivery is a
    fallback (a general model answered, no miner, no receipt), and
    anything else is a failure carrying the engine's error text.
    """
    body = data if isinstance(data, dict) else {}
    result = body.get("result") if isinstance(body.get("result"), dict) else {}
    receipt = body.get("receipt")
    entry = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "intent": intent,
        "miner_id": int(miner_id) if miner_id and str(miner_id).isdigit() else None,
        "miner_name": None,
        "target": params.get("url") or params.get("service") or "",
        "status": "failed",
        "http_status": status,
        "cost_usdc": 0,
        "receipt_id": None,
        "error": None,
        "note": "Engine ask failed; failed asks are not billed.",
    }
    if status == 200 and receipt:
        entry["status"] = "success"
        entry["receipt_id"] = (receipt.get("receipt_hash") if isinstance(receipt, dict)
                               else str(receipt))
        cost = result.get("cost_usd", body.get("cost_usdc"))
        entry["cost_usdc"] = cost if isinstance(cost, (int, float)) else PRICE_USDC
        entry["miner_name"] = result.get("miner_name")
        entry["note"] = "Engine ask succeeded and was receipted."
    elif status == 200 and result.get("delivery") == "last_resort":
        entry["status"] = "fallback"
        entry["note"] = ("No miner took the routed ask, so a general model "
                          "answered; no receipt was issued.")
    elif status == 200:
        entry["status"] = "success"
        entry["miner_name"] = result.get("miner_name")
        entry["note"] = "Engine ask succeeded; the reply carried no receipt."
    else:
        error = body.get("message") or body.get("error")
        entry["error"] = str(error) if error else f"HTTP {status}"
    return entry


def _log_attempt(entry: dict) -> None:
    """Append one entry to attempts.json at the repo root.

    The log is the public record of every live ask, failures
    included. A logging problem must never break the ask itself, so
    write errors are swallowed; a missing or unreadable log file
    simply starts a fresh one.
    """
    try:
        try:
            with open(ATTEMPTS_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {"attempts": []}
        if not isinstance(data, dict) or not isinstance(data.get("attempts"), list):
            data = {"attempts": []}
        data["attempts"].append(entry)
        with open(ATTEMPTS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
    except OSError:
        pass


def ask_telegraph(intent: str, params: dict, miner_id: str | None = None,
                  live: bool | None = None) -> dict:
    """Ask the Telegraph engine (live) or the local demo miner.

    Live mode is used when `live` is True, when a target `miner_id` is
    given, or when ANJOMAN_API_KEY is set. A live ask without a key
    raises MissingApiKeyError. Otherwise the local demo miner answers,
    labelled LOCAL-DEMO at zero cost.

    A live result carries the engine reply exactly as sent under
    "response", plus the HTTP "status". The "answer", "receipt" and
    "cost_usdc" fields are convenience derivations for existing
    consumers (the CLI claim builder), filled defensively from
    whatever the engine returned.
    """
    if live is None:
        live = miner_id is not None or _api_key() is not None
    if live:
        path = f"/engine/ask/{miner_id}" if miner_id is not None else "/engine/ask"
        status, data = _engine_request("POST", path, {"intent": intent, "params": params})
        result = {"mode": "LIVE", "intent": intent, "miner_id": miner_id,
                  "status": status, "response": data}
        if isinstance(data, dict):
            result["answer"] = data.get("answer", data)
            result["receipt"] = data.get("receipt") or data.get("transaction") or "see engine response"
            result["cost_usdc"] = data.get("cost_usdc", PRICE_USDC)
        else:
            result["answer"] = data
            result["receipt"] = "see engine response"
            result["cost_usdc"] = PRICE_USDC
        _log_attempt(_attempt_entry(intent, params, miner_id, status, data))
        return result
    # Local demo fallback. Accepts the canonical _GENERAL intents
    # (what registration and the engine use) as well as the bare prefixes.
    if intent in LOCAL_INTENTS:
        result = check_url(params["url"], timeout_s=float(params.get("timeout_s", 5)))
        answer = result.to_dict()
        answer["sla"] = sla_verdict(result, max_latency_ms=int(params.get("max_latency_ms", 1000)))
        return {"mode": "LOCAL-DEMO (not a Telegraph purchase)", "intent": intent,
                "answer": answer, "receipt": "LOCAL-DEMO", "cost_usdc": 0.0}
    raise ValueError(f"Intent {intent} not served by the local demo miner")


def escrow_balance() -> object:
    """GET /engine/escrow/balance on the engine backend (authenticated).

    Returns the parsed JSON exactly as the engine sent it. Raises
    MissingApiKeyError when ANJOMAN_API_KEY is not set.
    """
    _status, data = _engine_request("GET", "/engine/escrow/balance")
    return data


def agent_spend() -> object:
    """GET /agent/spend on the engine backend (authenticated).

    Returns the parsed JSON exactly as the engine sent it. Raises
    MissingApiKeyError when ANJOMAN_API_KEY is not set.
    """
    _status, data = _engine_request("GET", "/agent/spend")
    return data
