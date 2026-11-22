# Growth plan — the 20 points most builders ignore

Judging: 20/100 for content/education (5), ease of adoption (5), organic
distribution (5), community activation (5). Needs 3+ original updates on
separate dates, a tutorial another dev can follow, and ideally one
independent dev reproducing a Telegraph request through your work.

## Post 1 — today (announce)
Building SLAWitness for @Telegraphprotoc Season II, Mission 15: an agent
that buys a verified uptime/SLA check and auto-drafts your compensation
claim — receipt attached — when a provider breaches its SLA. Refunds go
unclaimed because proving disruption is tedious. Not anymore. https://github.com/Jacksonx28/slawitness
#TelegraphProtocol — entering the hackathon for the prize, building in public.

## Post 2 — when the miner is live on Telegraph
SLAWitness's miner is live: SERVER_UPTIME_MONITOR + SLA_COMPLIANCE,
deterministic, ~$0.01/request. First real engine-routed purchase: [receipt].
What I learned registering a miner (YAML hash pinning will bite you): [thread]

## Post 3 — demo week
Demo: I pointed SLAWitness at a dead URL and a slow one. It bought proof,
called the breach, and drafted the claim in seconds. 2-min video: [link]
Try it yourself — repo README runs with zero installs. If you reproduce a
request, tell me and I'll link your run here.

## Tutorial outline (publish on GitHub/Dev.to, link from repo)
1. What an Intent is, in one paragraph, with SERVER_UPTIME_MONITOR as the example
2. Wrap any deterministic check as a miner (our server.py, ~80 lines)
3. Register + pin the YAML — and the hash mistake to avoid
4. Buy your own miner through /engine/v1/ask and read the receipt
5. Turn the answer into a finished artefact (the claim letter)
6. Honest limitations: single-region checks, no historical uptime yet
