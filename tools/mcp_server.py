"""DownProof MCP server (minimal, stdlib only).

Speaks MCP over stdio (newline-delimited JSON-RPC) and exposes one tool:

  downproof_check {url, provider?, bill?, uptime?, checks?}

which calls POST {DOWNPROOF_BASE_URL}/api/check on the deployed
DownProof app and returns its JSON verdict: breach or no breach, the
per-check miner results, any credit owed from the provider's published
SLA table, and the claim letter or honesty record.

Base URL defaults to https://downproof.vercel.app and can be overridden
with the DOWNPROOF_BASE_URL environment variable (e.g. a local server).

Run:  python3 tools/mcp_server.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.error

BASE_URL = os.environ.get("DOWNPROOF_BASE_URL", "https://downproof.vercel.app").rstrip("/")
PROTOCOL_VERSION = "2024-11-05"

TOOL = {
    "name": "downproof_check",
    "description": (
        "Run a DownProof SLA check: live uptime checks against a service URL, "
        "a breach or no-breach verdict, the credit owed from the provider's "
        "published SLA table when bill and uptime are supplied, and a drafted "
        "claim letter (or an honesty record when the SLA was met)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Service URL to check, e.g. https://example.com"},
            "provider": {"type": "string", "description": "Provider key or name: aws-ec2, aws-s3, azure-vm, gcp-compute, cloudflare-workers, digitalocean-spaces, or other"},
            "bill": {"type": "number", "description": "Monthly bill in USD for the affected service (optional)"},
            "uptime": {"type": "number", "description": "Measured monthly uptime percent, 0 to 100 (optional, never guess it)"},
            "checks": {"type": "integer", "description": "Number of independent checks, 1 to 5 (default 1)"},
        },
        "required": ["url"],
    },
}


def call_api_check(args: dict) -> dict:
    payload = {"url": args.get("url", "")}
    for key in ("provider", "bill", "uptime", "checks"):
        if args.get(key) is not None:
            payload[key] = args[key]
    body = json.dumps(payload).encode()
    req = urllib.request.Request(BASE_URL + "/api/check", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def result(id_, value) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": value}


def error(id_, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}


def handle(msg: dict) -> dict | None:
    method = msg.get("method", "")
    id_ = msg.get("id")
    if method == "initialize":
        return result(id_, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "downproof", "version": "0.1.0"},
        })
    if method.startswith("notifications/"):
        return None  # notifications get no response
    if method == "ping":
        return result(id_, {})
    if method == "tools/list":
        return result(id_, {"tools": [TOOL]})
    if method == "tools/call":
        params = msg.get("params") or {}
        if params.get("name") != "downproof_check":
            return error(id_, -32602, f"unknown tool: {params.get('name')}")
        try:
            data = call_api_check(params.get("arguments") or {})
            return result(id_, {"content": [{"type": "text", "text": json.dumps(data, indent=2)}],
                                "isError": not data.get("ok", False)})
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8")[:500]
            except Exception:
                detail = ""
            return result(id_, {"content": [{"type": "text", "text": f"DownProof API error: HTTP {e.code} {detail}"}],
                                "isError": True})
        except Exception as e:
            return result(id_, {"content": [{"type": "text", "text": f"DownProof API unreachable: {e}"}],
                                "isError": True})
    return error(id_, -32601, f"method not found: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps(error(None, -32700, "parse error")) + "\n")
            sys.stdout.flush()
            continue
        response = handle(msg)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
