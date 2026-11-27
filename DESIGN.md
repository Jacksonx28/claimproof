# DownProof: verification observatory

This redesign makes the specialist miner's job visible: probe a service, compare the observation, and prepare evidence. The public checker, provider directory, filing guide, paid proof ledger, and historical watchlist share one responsive visual system.

## Direction and references

- [Fine-log](https://fine-log.vercel.app/#library): deliberate typography, restrained navigation, quiet dashboard surfaces.
- [21st.dev](https://21st.dev/): layered controls, clear hover/focus/pressed states, compact composition.
- [assistant-ui](https://www.assistant-ui.com/): understandable run progress and expandable raw evidence.
- [shadcn/ui](https://ui.shadcn.com/): familiar form, disclosure, and state patterns.
- [Godly](https://godly.design/) and [Lapa Ninja](https://www.lapa.ninja/): infrastructure-focused art direction and dimensional technical imagery.
- Public Mobbin material was consulted; Refero was not accessible enough to use as a source. No reference site assets or proprietary component implementations were copied.

The original SVG observatory uses layered metallic geometry, orbit paths, moving signal packets, a floating miner, and a scanning highlight. It is explicitly an illustration, not a live transaction or telemetry feed. All looping movement respects the user's reduced-motion preference.

## Interaction and data

The existing Python miner, API contract, provider credit tables, and Telegraph purchase records remain the source of truth. New static asset routes use an exact allowlist. The watchlist reads the repository's dated `watch_results.json` record.

- Persistent dark/light theme; responsive navigation with Escape dismissal.
- Native page transitions where supported, button press feedback, and animated result changes.
- Free direct checks with controlled test presets, provider suggestions, optional monthly inputs, raw evidence, copy, Markdown, and JSON exports.
- Searchable provider policies and paid purchases; expandable receipts and attempt filters.
- Interactive filing checklist and dated watch history.

A failed probe is described as a threshold breach. The UI does not treat a short probe as proof of monthly SLA eligibility. Credit amounts use separately supplied monthly inputs and remain estimates. Paid Telegraph receipts are distinguished from free browser checks and free watch runs.

## Validation

- `python3 -m unittest discover -s tests -v`: 56 passing tests, including six public-asset/data route checks.
- JavaScript syntax and Git whitespace checks pass.
- All five page routes inspected at 320, 768, and 1440 px widths without horizontal document overflow.
- Desktop and phone visual review in both themes, including the SVG illustration.
- Browser controls exercised: healthy HTTP 200 check, controlled HTTP 503 check, unresolved-host failure, optional credit estimate, raw evidence, record copy, JSON download, provider search, purchase search, fallback filter, guide checklist, disclosures, mobile menu, Escape, and theme persistence.

No new runtime library or build system is required. Google Fonts retain system fallbacks. Page transitions progressively enhance normal navigation.
