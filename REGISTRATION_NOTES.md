# DownProof miner — registration notes

Prepared 2026-11-23. The miner is live at https://downproof.vercel.app and the
YAML below is served at https://downproof.vercel.app/telegraph.yaml (once the
updated code is pushed/deployed — Vercel auto-deploys on push).

## The YAML (Telegraph Miner Standard v1)

Rewritten 2026-11-23 to the current schema
(https://anjoman.ai/docs/miners/yaml-config). The old YAML (top-level
`api{}` / `pricing{}` blocks, bare intent names) would have been rejected:
the schema requires exactly the top-level fields `version`, `kind`, `id`,
`slug`, `name`, `base_url` (everything else optional, unknown keys refused),
and the bare names `SERVER_UPTIME_MONITOR` / `SLA_COMPLIANCE` are prefixes,
not intents ("a prefix is not an intent").

Identity chosen:

- `id`: **23112026** (numeric; the registration date, easy to recognise)
- `slug`: **downproof**
- `name`: `downproof-uptime`
- `base_url`: https://downproof.vercel.app

Both `id` and `slug` were checked unused against the live registry
(`GET https://devnode.telegraphprotocol.com/api/miners`, 2,189 miners) on
2026-11-23. **Re-check both immediately before registering** — registration
is on-chain and cannot be edited.

Registered intents (canonical, confirmed live on the devnode):

- `SERVER_UPTIME_MONITOR_GENERAL`
- `SLA_COMPLIANCE_GENERAL`

One endpoint, `POST /query` (external_path `/query`), serves both, with a
full `params` contract (`url` required; `max_latency_ms`, `timeout_s`,
`sla_target_pct`, `period` optional) so the node's request builder does not
have to guess field names.

**SHA-256 of the exact served YAML bytes:**
`0x6ba5798a42145df8051e36b6a0634cbe4db51afc25aa3b268da2303851f7e651`

Any edit to the YAML changes this hash — recompute after any change and
never register a stale copy. (The hash was computed over the exact string
served by both `miner/server.py` and `api/index.py`; both were verified to
serve byte-identical content.)

## Intent response formats (from the live devnode intent records)

- `SLA_COMPLIANCE_GENERAL` publishes a response format (format_version 4,
  served_by `SLA_COMPLIANCE`): fields `service` (string), `uptime_pct`
  (number, percent 0–100, scored), `sla_target_pct` (number, percent),
  `compliant` (bool), `period` (string). Its request params are `service`
  and `period`, both required.
  `/query` now returns all five fields (additively — every pre-existing
  field is unchanged). Because DownProof measures one live check at request
  time, `uptime_pct` is the single-sample availability (100.0 up, 0.0 down)
  and `period` is reported honestly as `instant (single live check)`.
  `sla_target_pct` is echoed only when the caller supplies one — never
  invented. `/query` also accepts `service` as an alias for `url`, matching
  the intent's request param name.
- `SERVER_UPTIME_MONITOR_GENERAL` publishes **no** request or response
  format (its intent record has `request: null`, `response: null`), so
  nothing was added for it; the existing `UptimeResult` fields stand.

`/health` still lists the bare intent names. The docs do not cover
`/health`; it is our own endpoint, not a registered artefact. Flagged as an
open question below rather than changed unilaterally.

## Remaining registration steps

1. Push the updated code to GitHub (`miner/server.py`, `miner/monitor.py`,
   `api/index.py`, tests) so Vercel redeploys; confirm
   https://downproof.vercel.app/telegraph.yaml serves the new YAML and the
   hash above.
2. Re-check `id` 23112026 and `slug` `downproof` are still unused
   (`GET https://devnode.telegraphprotocol.com/api/miners`).
3. In a browser: open the Earn interface at
   https://anjoman.ai/dashboard/earn and connect an Ethereum wallet
   (Israel's MetaMask — he connects it himself).
4. Make sure the wallet is on **Ethereum Sepolia** and holds some Sepolia
   ETH (free from the Anjoman faucet) for gas.
5. Paste the YAML into the Earn interface. It sandbox-tests every declared
   endpoint against the live API before registering — read any `warnings`.
6. Confirm the registration in the interface. The miner bond is reportedly
   unset on the current Diamond (Addresses page, 2026-11-19) — **confirm
   this in the interface** before signing; if a bond is demanded, stop and
   reassess.
7. After registering, verify the miner appears in
   `GET https://devnode.telegraphprotocol.com/api/miners` (and
   `GET /api/miners/{registrationId}`) with both `_GENERAL` intents, and
   that `GET /engine/v1/ask/{id}` routing reaches the miner.

Fallback (manual) route, per the docs: `cast` against the Diamond
`0x72a70e949362670Bf8bceAd24eFC5b8f950aa08b` on Ethereum Sepolia
(RPC https://ethereum-sepolia-rpc.publicnode.com), passing the same
supported intents to `registerMiner` as the YAML lists.

## Open questions

- `intent_mapping` was deliberately **not** added. It is optional; without
  it the node reads our answers with its parser model, and our answers carry
  the intent's exact field names. Adding a mapping later could make reads
  exact, but a malformed mapping is rejected at registration — decide after
  the first live `ask` results are seen.
- Should `/health` list the `_GENERAL` intent names too? It is not part of
  the registered YAML; left unchanged for now.
- Pricing is no longer in the YAML (the v1 schema has no pricing block;
  the old `amount_usdc: 0.01` declaration is gone). How per-call price is
  set/discovered under the current standard needs confirming in the Earn
  interface at registration time.
