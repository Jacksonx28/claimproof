# DownProof: Telegraph Hackathon Season II

**Track 03 (Apps & Agents), Mission 15: Consumer Automation** + **Track 01 (Miners)**
Intents: `SERVER_UPTIME_MONITOR`, `SLA_COMPLIANCE`, both deterministic, both shared by 2 missions.

## The problem
Refunds go unclaimed because proving a disruption is tedious. DownProof proves it for you.

## What it does
1. You give it a service URL, its provider, and its SLA (e.g. max 1000ms, must be up).
2. It buys an uptime/SLA check through Telegraph (engine-routed, receipted, cost line shown).
3. If the SLA is breached, it drafts a ready-to-send compensation claim with the
   Telegraph receipt attached as proof. If the SLA is met, it says so, no fake claim.

## Run it (zero installs, Python 3.10+ stdlib only)
```bash
# App, local demo mode (calls our miner directly, labelled LOCAL-DEMO)
python3 app/downproof.py --url https://example.com --provider "Example ISP" --out examples/up
python3 app/downproof.py --url https://nonexistent.invalid --provider "Example ISP" --out examples/down

# Miner, the same logic as a callable Telegraph miner service
python3 miner/server.py            # :8080
curl -X POST localhost:8080/query -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com","max_latency_ms":1000}'

# Tests
python3 -m unittest discover -s tests
```

## Deploy the miner (public HTTPS URL)

**Vercel (primary, free Hobby tier, no card):** import this GitHub repo at
vercel.com/new, no build settings needed, root directory = repo root.
`vercel.json` routes every path to `api/index.py`, a stdlib WSGI adapter that
serves the same `/query`, `/health` and `/telegraph.yaml` as `miner/server.py`.
Your deployment URL (e.g. `https://<project>.vercel.app`) is the miner's public URL.
The root of that URL also serves a one-page web UI (`web/index.html`, via
`api/index.py`): a visitor enters a service URL and provider, the page runs live
checks against the miner's `/query`, shows the verdict, calculates any credit
owed from the provider's published SLA tiers, and drafts the claim letter,
the same flow as the CLI, in a browser.

**Render (alternative):** `render.yaml` in the repo root defines the
`downproof-miner` service running `miner/server.py` directly.

## Go LIVE on Telegraph (required for a real submission)
Local demo is *not* a Telegraph purchase and is never claimed as one.
1. Register for Season II at hackathon.telegraphprotocol.com and pick Mission 15.
2. Star github.com/telegraphprotocol/bounties (required for every track).
3. Deploy `miner/server.py` at a public HTTPS URL; put that URL in `miner/server.py`'s
   `/telegraph.yaml` output (`api.base_url`).
4. Register the miner via Telegraph's integration flow, pinning the YAML.
   Registration is on-chain and the YAML hash is pinned, edit the YAML *before* registering.
5. Fund a Telegraph account/escrow, set `TELEGRAPH_ENGINE_URL`, rerun the app.
   Only auto-routed `POST /engine/v1/ask` counts as a purchase / miner volume.
6. Record the 2–5 min demo: real input → breach → claim with receipt + cost line.
7. Submit through the H2 website by **1 Dec 2026, 23:59 UTC**.

## Failure cases judges can test
- Down/unreachable host → breach + claim (try `https://nonexistent.invalid`)
- Invalid URL scheme → clean DOWN verdict, no crash
- Slow service → latency breach (set `--max-latency-ms 10` against any real site)
- SLA met → correctly produces *no* claim

## Why this can win
- Deterministic intents score well: evaluators compare against ground truth, no LLM variance.
- One codebase, two tracks: the miner (Track 01) is consumed by the app (Track 03).
- Mission 15's example build #1 is literally this product, demand is pre-validated.
- 20/100 judging points are for education/growth: see `GROWTH.md`.
