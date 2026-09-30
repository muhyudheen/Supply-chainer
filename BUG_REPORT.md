# Supplychainer: Bug Report

TatHack '26 prelim · 29 Sep 2026 · team muhyudheen

**How we found these.** We ran the app (dashboard and `/api/recommend`) on a CPU-only Windows laptop, read every file on the live code path plus the model-training scripts, and re-ran the NLP scorer, the route graph and the shipped model in scripts to measure the numbers below. Every claim here was either reproduced by running code or read directly from the cited lines. The full per-file list, with 130 entries (126 from inspection, 4 found while fixing), is in `BUG_LIST.md`; the IDs in brackets refer to it.

**AI use.** Code reading, the measurement scripts and the drafting of this report were done with Claude Code. The team ran the tests and reviewed every finding (Rule 6).

## Summary

None of these bugs crashes the backend: it keeps "running fine" while the numbers and decisions are wrong. There are ten root problems.

| # | Problem | Visible effect | Severity |
|---|---|---|---|
| 1 | The NLP threat engine never produces a real threat | Threat is 0 everywhere; the dashboard's "RISK FLOOR 5%" is a default | Critical |
| 2 | Disruption scenarios don't change routes | Routes sail through a closed Suez Canal; Red Sea and Hormuz do nothing | Critical |
| 3 | The route graph's geography is wrong | Trucks cross the North Sea, ships cross continents, Europe → Asia by sea is impossible | Critical |
| 4 | The audit trace and totals don't add up | Scenario delay counted twice; surcharge missing from the total | High |
| 5 | Explanation text is invented | "Reduces landed cost by 11225%", "7 strategic transfers" for 2 | High |
| 6 | The p85 delay model can't be used as shipped | Never called; unknown places become "Atlanta"; trained on a leaked feature | High |
| 7 | The training data isn't real | Random data labelled "Real Historical"; weather and destination have no effect | High |
| 8 | Dashboard hides data and makes false claims | Audit shows only card 1; "TRUTH AUDIT VERIFIED" is hardcoded; the Supplier page likely crashes | High |
| 9 | Supplier scoring errors | Negative cost scores; a 50% penalty where the comment says 10% | Medium |
| 10 | API robustness, dead code, startup cost | Errors returned as HTTP 200; shared scenario state; graph built twice | Medium |

## 1. The NLP threat engine never produces a real threat (Critical)

**Symptom.** In every run, transit legs have threat 0 and transfer legs 0.05 [T21]. The startup log says `[NLP ENGINE] Warmup failed…` and then `[WARMUP] Unified Calibration Complete.` [T20]. Every leg's reason is a generic sentence labelled FALLBACK [T22].

**Root causes, in the order a threat passes through them:**
1. **The model never loads on CPU.** `threat_intelligence.py:157` calls `torch.load` without `map_location`, and the anchors were saved on a GPU [TI1].
2. **The failure is swallowed.** `threat_intelligence.py:164–166` only prints it, so `route_recommender.py:38–59` reports success and `/ws` says FULLY OPERATIONAL [TI2, R3, M9]. The dashboard never shows that status anyway [F10].
3. **The noise-floor check is inverted.** `threat_intelligence.py:177` uses `>=` where it should use `<`. A real disaster headline (Ever Given, margin 0.567) scores **0.000**, while noise (margin 0.018) scores 0.006 [TI3].
4. **CARF is inverted.** `threat_intelligence.py:191–194` zeroes a sea threat exactly when the news is about the sea: the sea fallback scores 0.930 → **0** [TI7]. Matching uses `.split()`, so "…the Suez canal" scores 0.0 but "…the Suez canal." scores 1.0 [TI8]. Rail and road are never checked [TI9].
5. **The score scale isn't calibrated.** `margin × 0.35` tops out around 0.2, while the original prototype's 3.5 rates routine congestion 0.93 [TI4]. The margin mixes the best match from different chunks, so calm text cancels a disaster [TI5].
6. **There's no live news.** The warm-up scores one fallback sentence per mode for all ~4,000 edges, so threat is one constant per mode, and `get_latest_news` is never called [R4, W2]. The fallback sentences themselves describe disruptions, so fixing the NLP alone would put a fake threat on every edge [W1].
7. **Transfers never get scored.** Transfer edges are skipped and fall back to a hardcoded 0.05 [R5].

**Reproduce.** Start the backend on a machine without CUDA and read the log. In Python, `ContrastiveNLPEngine().get_semantic_score("Container ship Ever Given runs aground in the Suez Canal, blocking all traffic in both directions.")` returns 0.0.

**Fix.**
- Load with `map_location="cpu"` and make the warm-up failure set `warmup_failed`.
- Flip the noise-floor comparison.
- Rewrite CARF as "drop only if the news is about another mode", with word-boundary matching.
- Fit the margin → threat mapping on a small labelled headline set.
- Make "no news" mean no threat.
- Fetch news per hub, with a cache, a timeout and a saved snapshot for demos.

## 2. Disruption scenarios don't change routes (Critical)

**Symptom.**
- Under SUEZ_BLOCK, FASTEST (sea only, 653.4h) and BALANCED (649.9h) still sail through the blocked canal with threat 1.0 [T3].
- RED_SEA_CONFLICT and HORMUZ_CLOSURE return routes identical to the normal run [T1]. A sea voyage starting at Jebel Ali, inside the Gulf, is untouched by a Hormuz closure [T2].
- The README promises "Reroutes automatically via Cape of Good Hope" [DOC3], and the dashboard says "Auto-bypass enabled for verified chokepoints" [F2].

**Root causes:**
- **A closed chokepoint is only a penalty.** In `route_recommender.py:106–132`, FASTEST ignores threat entirely, SAFEST multiplies the leg by 13, and BALANCED adds at most 8 points, worth about 27 hours of travel. A closed canal wins whenever the detour is longer [R9].
- **12 of the 14 chokepoints can't be entered.** Malacca, Hormuz, Bab-el-Mandeb, Gibraltar, Dover, the Cape of Good Hope and others have no incoming edge in the graph. Only Suez and Panama can be reached, so the Red Sea and Hormuz scenarios can never touch any route [N9, S1]. The Supplier screen does react to Hormuz (Desert Tech: 8 → 11.5 days), so the two screens contradict each other [S1].
- **Scenario `mode` is ignored.** A road flood also delays ships at the port [S2].
- **The dashboard can't send overrides.** "Strategic Overrides" is fixed text, not an input [F2].

**Reproduce.** `POST /api/recommend` with `{"source":"Shanghai","destination":"Rotterdam","scenario":"SUEZ_BLOCK"}`: BALANCED lists a leg to "Suez Canal" with threat 1. The same request with `RED_SEA_CONFLICT` is identical to the normal run.

**Fix.**
- Treat threat ≥ 0.95 as closed by removing the edge, and make the penalty meaningful otherwise.
- Add incoming sea links so ships pass through the chokepoints.
- Honour the scenario's mode.
- Turn "Strategic Overrides" into a real input.

## 3. The route graph's geography is wrong (Critical)

**Symptom.**
- A truck drives Felixstowe (UK) → Rotterdam in 2.7h [T14].
- Busan → Jebel Ali "by sea" takes 201.5h, the straight line over China and India [T15].
- Rotterdam → Shanghai by sea returns "No valid route". The Europe → Asia "economic" route costs $74,836, 29× the reverse direction, because it has to fly half the way [T17].
- A rail leg Shanghai Railway Terminal → Port of Shanghai takes 0h and costs $0 [T13].
- BALANCED leaves Port of Shanghai by road and returns by rail [T16].

**Root causes** (`multimodal_network.py`, `canonical_hubs.json`):
- **One-way links.** Transit edges are added in one direction only; 726 of 3,181 connections have no reverse [N7].
- **Straight-line distances for every mode**, with no sea lanes or land masks [N4].
- **Roads across water.** The <200 km road auto-wire ignores water and borders [N11].
- **Co-located hubs.** 9 hub pairs share identical coordinates, creating 29 zero-length edges including self-loops [N10].
- **Dead links.** 34 connections point to hubs that don't exist [N8].
- **Uneven handoff costs.** A rail↔ship handoff costs less than road↔ship [N5]. Every request starts and ends on a road node, so port-to-port trips pay +28h and +$500 in handoffs [L1].

**Fix.**
- Add reverse edges, except where a link is genuinely one-way.
- Use sea-lane distances (e.g. the `searoute` package).
- Only auto-wire roads within the same landmass.
- Fix the duplicate coordinates and the dangling links.
- Let port-to-port trips start and end on the sea node.

## 4. The audit trace and totals don't add up (High)

**Symptom.**
- Under SUEZ_BLOCK the ETA parts sum to 625.9 + 24 + 240 = **889.9h**, while the card says **649.9h** [T4].
- The cost parts sum to 2,638.49, while the total is 2,603.67 [T5].
- `risk.baseline` = 1 [T6].
- The audit panel shows raw floats such as "16.95663775053027h" [T7].

**Root causes** (`route_recommender.py`):
- The delay is added to the leg's hours (line 159) and to the scenario bucket (line 163), and those hours then also go into transit (line 171) [R10].
- The 10% scenario surcharge (line 165) never reaches `total_cost` (line 176) [R11].
- Baseline risk is recorded after the scenario threat has been applied (lines 160, 173) [R12].

**Fix.** Keep the base hours and the scenario hours separate. Add the surcharge to the total, or drop it. Record baseline risk before applying the scenario. Round values in the UI. Add a test that asserts the breakdown sums to the total.

## 5. Explanation text is invented (High)

**Symptom.** "Reduces total landed cost by 387% / 396% / 11225%", "reduce transit time by 3.3h vs pure surface transport" on an air route that's ~380h faster, "7 strategic transfers" on a route with 2 handoffs, "reduces risk exposure by 95%" [T8–T11].

**Root cause.** `route_recommender.py:229–242` plugs the route's own numbers into templates: 15% of its own cost, 20% of its own transit hours, transfer hours ÷ 4, and (1 − threat) × 100. Nothing is compared [R18]. The dashboard adds more fixed claims: "0ms co-location miracles detected", "TRUTH AUDIT VERIFIED" and "ACTIVE GLOBAL DISRUPTION DETECTED" [T12, F5, F11].

**Fix.** Compute real comparisons between the persona routes, e.g. "BALANCED saves $136,733 (98%) versus FASTEST and takes 381h longer". Count actual transfer legs. Remove the hardcoded badges or back them with real checks.

## 6. The p85 delay model can't be used as shipped (High)

**Symptom.** The README's headline model is loaded but never called by the router [R2].

**Root causes:**
- **Unknown places silently become "Atlanta".** The model knows 16 place names; any other place is encoded as "Atlanta Air Hub", and "Sea" becomes "air". Every live hub is predicted as Atlanta → Atlanta: "Shanghai → Rotterdam" and "PORT-SHANGHAI → PORT-ROTTERDAM" both give 24.2h [TI10, MR3].
- **Its inputs don't exist in the live app.** It needs a weather flag the router doesn't have, and an NLP score on the training data's scale [TI11].
- **It depends on a leaked feature.** On held-out rows it covers 85.1% of delays. With the NLP score at 0, which is what the live app sends, coverage drops to **46.4%** and pinball loss triples (2.08 → 6.91) [MR1].
- **It was never evaluated.** The training script splits off a test set and never uses it [MR2]. A random row split can't show performance on new places [MR4]. Only p85 exists, so there's no confidence band [MR5].
- **Its calibration comes from the wrong dataset.** The floor and cap were computed from the other generator's data: sea p5/p95 is 20.6 / 1,169.9h, versus 4.6 / 83.7h in the model's own training data [TI12, MR6].
- **Errors look like the safest answer.** On an inference error the model returns "0 delay" [TI14].

**Fix.**
- Retrain on features every hub has: mode, distance, chokepoints, region, hub type.
- Remove the leak by simulating a hidden disruption that drives both the news score and the delay.
- Train p50/p85/p95 and hold out whole routes to measure coverage and pinball loss.
- Refit the calibration on the same data.
- Wire the model into the router's weight function: FASTEST → p50, BALANCED → p85, SAFEST → p95.

## 7. The training data isn't real (High)

**Symptom.** It's labelled "Real Historical Dataset"; the README says "trained on 50,000+ real-world historical incidents" [DS1, DOC2].

**Root causes** (`Code/real_dataset_builder.py`):
- **Every row is random.** A seeded random generator invents the rows, and every category is uniform: 25% per mode, 33% per weather type [DS1, DS7].
- **The "real" input is 16 typed-in median/p90 pairs** with no citations, describing port dwell time rather than route delay [DS2].
- **The stated figures aren't reproduced.** It claims to fit median and p90 but uses only the median: Rotterdam's p90 of 90h comes out as 53.4h, and Suez's 144h as 28.4h [DS3].
- **The NLP score is computed from the delay itself** (target leakage) [DS4].
- **Weather is never used** [DS5], and **destination and distance have no effect** [DS6].
- **Incidents barely exist.** Only 191 of 50,000 rows (0.4%) have one, and "Red Sea Security 2024" can never fire: it was drawn 457 times and applied 0 times [DS9].

**Fix.** Rename the dataset and state that it's synthetic. Rebuild it with distance, weather and disruption effects, and a news signal generated from a hidden disruption rather than from the delay. Fit each anchor's distribution to both its median and its p90.

## 8. Dashboard hides data and makes false claims (High)

- **The audit panel only ever shows card #1**, the fastest. BALANCED's and SAFEST's audits can't be seen, and cards can't be selected [F1].
- **SAFEST or BALANCED silently disappear** when they pick the same stops as another persona. We never saw all three options in any test [T19, R17].
- **The Supplier page likely crashes when an inventory box is cleared.** `parseInt('')` is NaN, which is sent as null; the backend replies 422, and `suppliers.map` fails [F7, likely: confirm by clearing the box].
- **Hub search is fragile.** Queries aren't URL-encoded, every keystroke sends a request so older replies can overwrite newer ones, and editing the box after picking a hub keeps the old hub [F3].
- **The routes can't be explained from the UI.** Cards show no threat, per-leg time or cost, or scenario reason [F4].
- **The Supplier "Risk Score" is mislabelled.** It's just 1 − the ranking score [F8].
- **Some inputs have no controls.** Cargo type, priority and demand forecast are fixed, and `budget_sensitivity` and `routing_policy: PREFERRED` do nothing in the backend [F6, F9, M1, M2, R6].
- **Two screens are unreachable** (System Console, Benchmarks), and they hold hardcoded claims such as "ML Accuracy: 91%" and "No synthetic fallback active" [F11].

## 9. Supplier scoring errors (Medium)

- **Wrong penalty size.** The comment says the lead-time penalty is "10% of delay hours", but the code applies 50%, so a Suez blockage adds 5 days instead of 1 [P1].
- **Negative cost scores.** The cost score goes negative above $1,000: Steel-Core scores −0.2 [P2].
- **Thin data.** Chemicals has a single supplier, so its ranking can never change [P3].
- **Restock advice ignores the scenario** [M15].

## 10. API robustness, dead code, startup cost (Medium/Low)

- **Errors return HTTP 200.** "No route" comes back as `{"error": ...}` with a success status, including the stray French word "établi" [M13].
- **The scenario is shared between requests.** It's global state, so concurrent requests can take each other's scenario [M14].
- **Inputs aren't validated.** An unknown scenario silently means "none" [M7]. City names must match exactly and are case-sensitive [L2].
- **`/api/network` drops edge direction** [M12]. `/api/status` values are hardcoded [M10].
- **Paths only work from the repo root** [TI15, DS11, MR7].
- **Startup does unnecessary work.** The route graph is built twice [T23, M5]. The old US-only prototype is built on every start [M3]. torch is imported at the top only for one call [TI16]. The graph is copied three times per request [R8]. There are unused imports and parameters throughout [M4, R1, R6, R7, N1–N3].
- **Environment issues.** The original `requirements.txt` fails on Windows (`uvloop`), and the committed `node_modules` held Linux-only binaries. Both are fixed in our commits `5091a1f` and `5e8d58a`.

## Fix plan

We fix in this order, one bug per commit, each with a test that fails before the fix and passes after it.

1. **NLP pipeline:** TI1, TI2/R3, TI3, TI7, TI8.
2. **Audit arithmetic:** R10, R11, R12.
3. **Graph:** N7 reverse edges, N9 chokepoint links, N11 road auto-wire, N10 duplicate coordinates.
4. **Scenarios:** R9 treats a closed chokepoint as closed, S2 honours the scenario mode.
5. **Explanations and dashboard:** R18, F1, F2, F5, R17.
6. **Supplier bugs:** P1, P2, F7.
7. **Model rebuild (feature work):** a leak-free, hub-agnostic, multi-quantile model, wired into routing with SHAP explanations.

## Progress

We worked in a different order from the plan above: the graph had to be fixed before scenarios and audit numbers could be tested on real routes. Each round starts with a commit of failing tests, then one commit per fix. Status as of 30 Sep 2026, 00:45 IST (`fb7959a`): 66 tests, all passing (57 fast, 9 slow).

| Round | Scope | Tests | Fixes (commit) |
|---|---|---|---|
| 1 | NLP threat engine (§1) | `test_round1.py` (`fae0127`) | TI1 `683d04a`, TI2/R3 `a460c64`, TI3 `b83716f`, TI5 `ae2df38`, TI7–TI9 `fdaf10f`, W1 `f090f34` |
| 2 | Route graph (§3) | `test_round2.py` (`fa6835b`) | N7 `e9360d7`, N9/N4/N11 `035f392`, N10 `1feb6ff`, L1 `3469764` |
| 3 | Scenarios (§2) | `test_round3.py` (`58ee39d`) | R9 `7c4adfe`, S2 `a13326f`, S3 `8f28e3c`, M7 `923d47a`, M14 `ed80422` |
| 4 | Audit arithmetic and API errors (§4, §10) | `test_round4.py` (`7bdcc58`) | R10 `67b2c80`, R11 `77dfc62`, R12 `6329bc3`, M13 `4a7c433` |
| 5 | Explanations and persona cards (§5) | `test_round5.py` (`98d6998`) | R18 `60031f7`, R17 `23cdd2a`, S4 `6fad6d2` |
| 6 | Supplier scoring (§9) | `test_round6.py` (`3eee1f2`) | P1 `3be38e9`, P2 `fb7959a` |
| 7 | Model rebuild (§6, §7) | next | see `HANDOFF.md` §3 |

The frontend fixes (§8: F1–F10) are done by the teammate in `frontend/` and are tracked in `HANDOFF.md`. S1 (scenarios never reached a route) is resolved by the round 2 graph fix; the round 3 tests cover it.
