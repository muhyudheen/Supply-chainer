# AI usage (Rule 6)

## Frontend (abeltjoseph2005-art)

- F7 (`f105042`): Claude Code wrote the supplier-page input fix, the `parseCount` helper and its tests, and checked it against the live backend.
- F2 (`7641e6b`): Claude Code wrote the Strategic Overrides inputs, the `buildOverrides`/`hubNames` helpers, the closed-hubs banner and their tests.
- F1 (`28ef7e5`): Claude Code wrote the selectable route cards, the `pickSelected` helper, the audit-panel change and their tests.
- F4 (`ead968e`): Claude Code wrote the per-leg time/cost/threat line, the scenario-reason line, the route threat badge, the `legFacts` helper and their tests.
- F5 (`5c2a97b`): Claude Code removed the hardcoded claims, wrote the response-based scenario banner and Risk Exposure box, the `scenarioLegCount` helper and their tests.
- F10 (`3f22d5e`): Claude Code wrote the `EngineStatus` header badge, the `engineStatusView` helper, the /ws reconnect in `App.jsx` and their tests.
- F3 (`732d728`): Claude Code wrote the debounced, encoded hub search with stale-reply protection, the `hubSearchUrl`/`debounce`/`createRequestGate`/`endpointFor` helpers and their tests.
- F8 (`b4e760b`): Claude Code replaced the derived "Risk Score" with reliability, disruption penalties and the decision score from the audit trace, wrote the `supplierFacts` helper and their tests.
- M13 follow-up (`e840b1a`): Claude Code wrote the `apiError` helper so both pages show the backend's 400/404 `{error}` messages, and its tests.
- Round 7 dashboard (`ae1d264`, `9a28ec6`): the frontend teammate's session had ended, so Claude Code in the backend session wrote the ETA range, delay drivers, per-leg delay and model-status display, the helpers and their tests, and checked them in a headless browser against the real backend.
- Round 8 dashboard (`2a93455`, `431e15e`): Claude Code wrote the cargo type and priority dropdowns, the cargo-rules banner, the `cargoRulesView` helper and their tests.
- `aadc9a9`: Claude Code corrected the F7/F2/F1 hashes above (they pointed to commits from before the last rebase) and added the missing ones.

## Backend (muhyudheen)

Claude Code (Claude Opus 5.5) was used in a local session (rounds 1–6, 28–29 Sep) and a cloud session (30 Sep). Every commit Claude wrote or co-wrote ends with `Co-Authored-By: Claude Opus 5.5`.

**Done by hand (muhyudheen):**
- Explored the repo and README, ran the scenarios through the dashboard and the Swagger docs, and reviewed the ML files (`threat_intelligence.py`, `real_dataset_builder.py`, the `Execution/` artifacts) manually.
- Design decisions for the delay model: dwell only where cargo is handled, not scaled by distance; the organizers' Suez anchor for canals only; the Shanghai → Rotterdam sanity check (p50 delay under 25% of the voyage); distribution hubs count as terminals; canal legs keep the normal incident rate; SHAP against the same leg in calm conditions; p50 as every card's ETA; live weather with 0 when offline; documenting the dwell estimate as a known limit.
- Round 8 N1 fix (`05529a2`): typed by hand from Claude's instructions (the rule table, `CARGO_REASONS`, and the mode filter in routing).
- The README rewrite (`163f217`), from Claude's edit guide and draft sections.
- The development minutes: hand-written, no AI.

**Written by Claude Code:**
- `BUG_LIST.md` and `BUG_REPORT.md`: a surface sweep of the code for bugs, then the report built from the team's manual API and dashboard test results.
- Rounds 1–6 (NLP engine, route graph, scenarios, audit maths, explanations, suppliers): the failing tests and one commit per fix, listed in `BUG_REPORT.md` → Progress. R20 (`63419e9`, `432a7e2`).
- Round 7, the delay model: `backend/ml/features.py`, `dataset.py`, `train.py`, `predictor.py`, the trained artifact and metrics, the router wiring (R2), the Open-Meteo batch fetch, TI15, the status endpoint (M10 part), and all their tests.
- Round 8: the tests (`d722582`, corrected in `516baff`), R6 (`ca7d773`) and N2 (`7c6b337`).
- `HANDOFF.md`, `CLAUDE.md` and the uv project setup.
