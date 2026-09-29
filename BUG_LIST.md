# Supplychainer: running bug list

Dictated by the team during inspection on 28 Sep 2026 and saved by Claude Code. Nothing here is fixed yet.

**Impact** is a first guess, used to decide what to fix first. High means judges will see it, or it changes a routing decision.

## A. From testing (T)

### Test runs

| Run | Input |
|---|---|
| Startup log | `uv run uvicorn backend.main:app --port 8000` |
| Dashboard 1 | Port of Shanghai → Port of Rotterdam, Unconstrained, Operational Normal |
| Dashboard 2 | Same as 1, with Suez Canal Blockage |
| Dashboard 3 | Port of Shanghai → Port of Rotterdam, SEA + STRICT, Suez Canal Blockage |
| Dashboard 4 | Same as 3, with Operational Normal |
| API Suez | `POST /api/recommend` with `{"source": "Shanghai", "destination": "Rotterdam", "scenario": "SUEZ_BLOCK"}` |
| API Red Sea / Hormuz | Same body, with `RED_SEA_CONFLICT` / `HORMUZ_CLOSURE` |
| API Reverse | `{"source": "Rotterdam", "destination": "Shanghai", "scenario": "HORMUZ_CLOSURE"}`, all modes |
| Pending | Reverse again, with `"transport_preference": "sea"` and no scenario |

"Shanghai" in the API starts at `HUB-SHANGHAI`, while "Port of Shanghai" in the dashboard starts at `PORT-SHANGHAI`. That's why their routes differ.

### Findings

| # | Area | Issue | Evidence | Impact |
|---|---|---|---|---|
| T1 | Scenarios | Red Sea and Hormuz closures change nothing | API Red Sea / Hormuz: BALANCED is identical to the normal run (409.9h, $2,603.67, no scenario leg). Yet the ship sails Jebel Ali → Suez, which in reality passes both straits. | High |
| T2 | Scenarios | A Hormuz closure doesn't affect a voyage that starts inside the Gulf | API Reverse: Jebel Ali → Shanghai by sea with threat 0 while Hormuz is closed | High |
| T3 | Scenarios | A Suez blockage never forces a reroute | Dashboard 3 FASTEST (653.4h) and API Suez BALANCED (649.9h) sail through the blocked canal (threat 1). Only SAFEST avoided it (695.4h via Durban). This contradicts the dashboard text "Auto-bypass enabled for verified chokepoints". | High |
| T4 | Audit | ETA breakdown counts the scenario delay twice | API Suez: 625.9 + 24 + 240 = 889.9h, but `adjusted_eta` is 649.9h. Dashboard 3: 625.4 + 28 + 240 = 893.4h vs 653.4h. Normal-run transit is 385.4h, so the 240h is already inside transit. | High |
| T5 | Audit | Scenario premium is missing from the total | API Suez: 2,043.67 + 560 + 34.82 = 2,638.49, but `total_cost` is 2,603.67. Dashboard 3: $2,023.15 + $500 = $2,523.15, without the $34.82 premium. | Medium |
| T6 | Audit | Baseline risk includes the scenario | API Suez: `risk.baseline` is 1 | Low |
| T7 | Audit | Raw unrounded numbers in the audit panel | Dashboard 1: "16.95663775053027h", "$133,350.252" | Low |
| T8 | Explanations | Impossible savings percentages | 387% (Dashboard 1), 391% (Red Sea / Hormuz), 396% (API Suez), 11225% (Reverse). Each is always 15% of the route's own cost. | High |
| T9 | Explanations | "Reduce transit time by X h vs pure surface transport" | 2.6h, 3.3h, 3.4h, 77.1h, 125.1h. Each is always 20% of the route's own transit time, and the text appears even on all-sea routes. | Medium |
| T10 | Explanations | Wrong transfer count | "3 strategic transfers" on a route with 2 transfers (API FASTEST); "7" on routes with 2 handoffs (Dashboards 3–4). The number is transfer hours ÷ 4. | Medium |
| T11 | Explanations | "Reduces risk exposure by 95%" | Dashboard 3 SAFEST. The 95% is just 100% minus the 5% default threat. | Medium |
| T12 | Explanations | "TRUTH AUDIT VERIFIED", "0ms co-location miracles detected" | Contradicted by T13 | Medium |
| T13 | Network | Two different hubs at the same location | Shanghai Railway Freight Terminal ↔ Port of Shanghai by rail takes 0h and costs $0 (API Suez, API Reverse) | Medium |
| T14 | Network | A truck crosses the North Sea | Felixstowe (UK) → Rotterdam Distripark by ROAD in 2.7h (API FASTEST) | High |
| T15 | Network | Sea legs are straight lines over land | Busan → Jebel Ali takes 201.5h, about 7,050 km at 35 km/h: a straight line over China and India. A real ship covers about 11,000 km via Singapore. Jebel Ali → Suez (66.3h) cuts across Saudi Arabia. The route even sails Shanghai → Busan first, the wrong direction, to use this shortcut. | High |
| T16 | Network | Loop at the port | Dashboard 1 BALANCED leaves Port of Shanghai by road for the rail terminal, then comes back by rail. Rail→ship handling (8h, $180) is cheaper than road→ship (14h, $250, seen in Dashboard 4). | Medium |
| T17 | Network | The Europe → Asia "economic" route costs 29× the reverse direction | API Reverse BALANCED costs $74,836, of which a $72,660 Frankfurt → Dubai flight is 97%. Asia → Europe is all-sea at $2,604. This suggests there is no sea path from Europe to Asia; confirm with the pending sea-only run. | High |
| T18 | Network | The fastest reverse route adds an extra flight | A $5,487, 0.5h Amsterdam → Frankfurt flight before Frankfurt → Shanghai, so there's no direct link | Low |
| T19 | Personas | Never 3 options | Dashboard 1: FASTEST + BALANCED. Dashboard 3: FASTEST + SAFEST. Dashboard 4: FASTEST only. API: always FASTEST + BALANCED. | High |
| T20 | Threat/NLP | A failure is reported as success | Startup log: "[NLP ENGINE] Warmup failed…" followed by "[WARMUP] Unified Calibration Complete." | High |
| T21 | Threat/NLP | Threat never varies | In every test and every region, transit legs have threat 0 and transfer legs 0.05. The dashboard's "RISK FLOOR 5%" is that untouched default. | High |
| T22 | Threat/NLP | No live news anywhere | Every leg's "reason" is one generic sentence per transport mode, labelled FALLBACK | High |
| T23 | Startup | The network is built twice | "928 virtual nodes, 4912 edges" is printed twice in the startup log | Low |

## B. From reading `backend/main.py` (M)

| # | Lines | Finding | Kind | Impact | Found by |
|---|---|---|---|---|---|
| M1 | 41 | `budget_sensitivity` is declared in `RecommendRequest` but used nowhere. It isn't passed to `recommend()` (lines 155–164), the dashboard doesn't send it, and the engine never reads it. | Dead code | Low | You |
| M2 | 43 | `routing_policy` accepts `STRICT` or `PREFERRED`, but only `STRICT` is checked anywhere (`route_recommender.py:98`). So `PREFERRED` behaves the same as no transport preference. The dashboard still offers it as "PREFERRED (Soft Bias)" (`RouteRecommender.jsx:173`). | Advertised option with no code | Medium | You |
| M3 | 11–15, 22–25 | The old US-only prototype is imported and built on every startup: the road graph, the simulator with its weather provider, and the baseline router. The live routing never uses any of it. | Dead code, slower startup | Low | Walkthrough |
| M4 | 3, 6, 16 | `List`, `random` and `get_city_capabilities` are imported but never used | Dead code | Low | Walkthrough |
| M5 | 28, 31 | The route graph is built twice (the cause of T23). The recommender keeps `multimodal_net` only as an unused "legacy" field. `/api/network` serves this unused copy, while routing and the warm-up's threat values use the other copy, so the two can drift apart. | Waste, consistency risk | Medium | Walkthrough |
| M6 | 24 | The p85 model is loaded at import time rather than when first needed. This is the step that hung on a slow PC. | Performance | Low | Walkthrough |
| M7 | 36–45 | Request fields are free strings with no allowed-values check. An unknown scenario ID silently means "no scenario", and a typo like `"Sea"` is accepted. `overrides` is an untyped dict whose keys (`avoid_chokepoints`, `cost_ceiling`, `max_delay`) aren't documented anywhere. | Missing validation | Medium | Walkthrough |
| M8 | 54–59 | The NLP warm-up runs in a background thread after the server has started. Requests in the first ~17 s see half-updated threat values. The background task's reference isn't kept, which Python's docs warn against. | Race, robustness | Low | Walkthrough |
| M9 | 121–142 | `/ws` keeps reporting "FULLY OPERATIONAL" after the NLP warm-up failed (T20). The status only becomes "WARM-UP FAILED" if the warm-up crashes outright; the cause is in `route_recommender.py` / `threat_intelligence.py`. `"ml_trained": True` and `"hub_registry": "Synchronized"` are hardcoded, and `tick` never changes. | Misleading status | High | Walkthrough |
| M10 | 110–119 | `/api/status` values are hardcoded (`ml_trained`, `is_supplychainer`, `geo_scope`). `active_trips` and `tick` come from the old simulator, which never runs, so they're always 0. | Misleading status | Medium | Walkthrough |
| M11 | 81–92 | Hub search has no result limit or ranking: typing "a" returns almost every hub. It also assumes every hub has `aliases` and `country`; a hub missing either would cause a 500 error. | Robustness | Low | Walkthrough |
| M12 | 94–108 | `/api/network` de-duplicates edges by their sorted endpoints, so edge direction is lost. This hides the one-way links suspected in T17. Mode and cost aren't sent either. | Data loss | Medium | Walkthrough |
| M13 | 153–165 | "No route found" comes back as `{"error": ...}` with HTTP 200 (success). The message also contains a stray French word, "établi" (`route_recommender.py:212`). | API contract | Medium | Walkthrough |
| M14 | 153–182 | The endpoints are plain `def`, so FastAPI runs them in parallel threads that all share one `scenario_mgr`. Two users with different scenarios can get each other's scenario. `/api/suppliers` (line 172) also switches that shared scenario, and doesn't reset it when no scenario is sent. | Concurrency, shared state | Medium | Walkthrough |
| M15 | 176 | The restocking advice ignores the active scenario | Design gap | Low | Walkthrough |

## C. From reading `backend/engine/route_recommender.py` (R)

| # | Lines | Finding | Explains | Kind | Impact | Found by |
|---|---|---|---|---|---|---|
| R1 | 2, 4–6 | Unused imports: `math`, `List`, `Dict`, `Any`, `Optional`, `MODE_PROFILES`, `ThreatIntelligencePredictor` | – | Dead code | Low | Walkthrough |
| R2 | 17–19, 42 | `network` and `simulator` are stored but never used. `predictor` is only warmed up: its p85 prediction (`predict_worst_case_delay`) is never called anywhere. | README feature ask | Missing feature | High | Walkthrough |
| R3 | 38–59 | The NLP failure is caught inside `nlp.warmup()`, so this code never sees it. It prints "Unified Calibration Complete", and `warmup_failed` stays False, so `/ws` reports FULLY OPERATIONAL. | T20, M9 | Misleading status | High | Walkthrough |
| R4 | 46–53 | Every edge of a mode is scored with the same fallback sentence, so threat is one constant per mode. Live news (`get_latest_news`) is never called. The same 4 sentences are also re-scored once per edge, about 4,000 embedding runs. | T21, T22 | Wrong design, performance | High | Walkthrough |
| R5 | 48, 115, 154 | The warm-up skips transfer edges, so they fall back to a hardcoded 0.05 threat. The graph's own transfer `risk` values (0.02–0.08) are never read. | T21 ("RISK FLOOR 5%") | Hidden default | Medium | Walkthrough |
| R6 | 61–63 | `cargo_type` and `priority` are accepted but never used. The cargo restrictions and priority multipliers in `multimodal_network.py` are never applied either (N1, N2). | – | Dead parameters | Medium | Walkthrough |
| R7 | 66 | `t0` is recorded but never used | – | Dead code | Low | Walkthrough |
| R8 | 90 | The whole graph is copied three times per request, once per persona | – | Performance | Low | Walkthrough |
| R9 | 106–132 | A closed chokepoint never actually closes. FASTEST ignores threat entirely, SAFEST multiplies the leg by 13, and BALANCED adds at most 8 points (worth about 27 hours of travel). Routes sail through a closed canal whenever the detour is longer. | T3 | Wrong decision | High | Walkthrough |
| R10 | 159, 163, 171 | The scenario delay is added to the leg's hours and to the "scenario" bucket, then the leg's hours also go into "transit", so the delay is counted twice | T4 | Wrong number | High | Walkthrough |
| R11 | 165, 176 | The 10% scenario surcharge goes into the audit's "scenario" cost but never into `total_cost` | T5 | Wrong number | Medium | Walkthrough |
| R12 | 160, 173 | "Baseline" risk is recorded after the scenario threat has already been applied | T6 | Wrong number | Low | Walkthrough |
| R13 | 192 | A persona over the cost ceiling or max delay is dropped without telling the user why. `max_delay` is in days, while every other time is in hours. | – | UX, units | Low | Walkthrough |
| R14 | 196 | `primary_mode` is always "MULTIMODAL", even for one-mode routes | – | Misleading field | Low | Walkthrough |
| R15 | 203 | `override_applied` ignores the `max_delay` override | – | Wrong flag | Low | Walkthrough |
| R16 | 206–209 | Any routing error is printed to the terminal and the persona is silently skipped | – | Hidden errors | Low | Walkthrough |
| R17 | 214–221 | When two personas pick the same stops, the later card is dropped without a note, so the user is never told "the fastest route is also the safest". The duplicate check compares stops only, not modes. | T19 | UX | High | Walkthrough |
| R18 | 229–242 | The explanation numbers are formulas on the route's own values, not comparisons: 20% of transit hours, transfer hours ÷ 4, (1 − threat) × 100, and 15% of cost. `eta` (line 233) is computed and never used. | T8–T11 | Invented metrics | High | Walkthrough |

## D. From reading `backend/engine/multimodal_network.py` and `backend/data/canonical_hubs.json` (N)

| # | Lines | Finding | Explains | Kind | Impact | Found by |
|---|---|---|---|---|---|---|
| N1 | 7–12 | The per-mode `cargo_restrictions` are defined but never enforced | R6 | Dead config | Medium | Walkthrough |
| N2 | 14–18 | `PRIORITY_MULTIPLIERS` is never used | R6 | Dead config | Low | Walkthrough |
| N3 | 5, 144–158 | Unused imports (`List`, `Dict`, `Any`). `get_city_capabilities` is never called; `main.py` only imports it. | M4 | Dead code | Low | Walkthrough |
| N4 | 20–26, 118, 130 | Every distance is a straight line (great-circle) for every mode, so sea legs cross land and roads cross water | T14, T15 | Wrong geography | High | Walkthrough |
| N5 | 47–54, 93–95 | At a port, any pairing with rail (even road↔rail) gets `port_to_rail` (8h, $180), while road↔sea costs 14h and $250, so going via the rail terminal is cheaper. `road_to_rail` and `rail_to_road` are never chosen. | T16 | Wrong costs, dead config | Medium | Walkthrough |
| N6 | 99–104 | Transfer edges store a `risk` value that nothing reads | R5 | Dead data | Low | Walkthrough |
| N7 | 106–123 | Transit edges are added in one direction only: 726 of 3,181 connections have no reverse, so Europe → Asia by sea is impossible | T17, T18 | Missing edges | High | Walkthrough |
| N8 | 116 | Connections to hubs that don't exist are silently skipped: 34 of them, e.g. five airports link to a missing `AIR-CHENNAI` | – | Data integrity | Medium | Walkthrough |
| N9 | data, 106–123 | 12 of the 14 chokepoints have no incoming edge (Malacca, Hormuz, Bab-el-Mandeb, Gibraltar, Dover, Cape of Good Hope, …). Only Suez and Panama can ever be entered, so the Red Sea and Hormuz scenarios can never affect any route, from anywhere. | T1, T2 | Wrong topology | High | Walkthrough |
| N10 | data | 9 pairs of hubs share identical coordinates (Port/Rail Shanghai, Port/Rail Rotterdam, Hub/Rail Chicago, …). This creates 29 transit edges of 0 km, including self-loops such as Port of Singapore → itself. | T13 | Data integrity | Medium | Walkthrough |
| N11 | 125–139 | The road auto-wire links every road-capable pair of hubs under 200 km apart, in both directions, ignoring water and borders | T14 | Wrong geography | High | Walkthrough |

Sections E–J come from a skim for important issues only (28–29 Sep night), to be reviewed by the team.

## E. From `backend/engine/scenario_manager.py` (S)

| # | Lines | Finding | Explains | Kind | Impact | Found by |
|---|---|---|---|---|---|---|
| S1 | 19–27, 55–63 | RED_SEA_CONFLICT and HORMUZ_CLOSURE target chokepoints that no route can enter (N9), so neither scenario ever changes a route. The Supplier screen does react to Hormuz (Desert Tech's lead time goes 8 → 11.5 days, score 0.74 → 0.58), so the two screens disagree about the same event. | T1, T2, N9 | Wrong decision, inconsistency | High | Walkthrough |
| S2 | 17, 26, 35, 44, 53, 62 | Each scenario's `mode` field is never used. The router delays any leg that enters an affected hub, so a road flood (CHENNAI_FLOOD) also delays ships and trains at the port, and a port strike delays trucks too. | – | Missing logic | Medium | Walkthrough |
| S3 | 49–52 | DUBAI_AIR_CONGESTION's reason says "48h clearance backlog", but only 24h is applied | – | Text vs number | Low | Walkthrough |

## F. From `backend/engine/node_resolver.py` and `backend/data/canonical_locations.json` (L)

| # | Lines | Finding | Explains | Kind | Impact | Found by |
|---|---|---|---|---|---|---|
| L1 | 34–51 | Every request starts and ends on a hub's road node, and a city resolves to its road hub. So even a port-to-port sea request pays a truck↔ship handoff at both ends: +28h and +$500 (Dashboard 4). | Dashboard 4 | Wrong numbers | Medium | Walkthrough |
| L2 | 34 | City names must match exactly and are case-sensitive, and the hubs' aliases are ignored. For example, "shanghai" fails with "Entry point unavailable". | – | Robustness | Low | Walkthrough |

## G. From `backend/engine/news_ingestion.py` (W)

| # | Lines | Finding | Explains | Kind | Impact | Found by |
|---|---|---|---|---|---|---|
| W1 | 18–23 | All four fallback sentences describe disruptions (congestion, backlogs, surcharges, maintenance). Once the NLP works, every edge of a mode will carry a threat from this invented news; the sea sentence scores 0.93 with the original multiplier. "No news" should mean "no threat". | T21 | Wrong design | High | Walkthrough |
| W2 | 25–62 | `get_latest_news` is never called (R4). Three problems to fix before wiring it in: it searches with whatever string it's given, and hub IDs like "PORT-SHANGHAI" make poor queries; line 46 changes the timeout for every network connection in the whole server, not just this request; and feedparser doesn't raise on network errors, so failures fall silently to the fallback. | T22, R4 | Latent bugs | Medium | Walkthrough |

## H. From `backend/engine/supplier_scorer.py` and `backend/data/suppliers.json` (P)

| # | Lines | Finding | Explains | Kind | Impact | Found by |
|---|---|---|---|---|---|---|
| P1 | 40–43 | The comment says the lead-time penalty is "10% of delay hours converted to days", but the code uses 50% (`* 0.5`). A Suez blockage adds 5 days instead of 1: Global Dynamics goes from 14 to 19 days. | – | Comment vs code | Medium | Walkthrough |
| P2 | 30 | The cost score goes negative above $1,000: Steel-Core scores −0.2 and Northern Mining −0.1 (Raw Materials) | – | Wrong number | Medium | Walkthrough |
| P3 | data | Chemicals has only one supplier, so its ranking can never change, and no scenario affects it | – | Thin data | Low | Walkthrough |

## I. From the frontend (F)

| # | Where | Finding | Explains | Kind | Impact | Found by |
|---|---|---|---|---|---|---|
| F1 | `RouteRecommender.jsx` 266–286 | The audit panel always shows the first (fastest) card, never the one you're looking at, and there's no way to pick a card. BALANCED's and SAFEST's audits are never visible, which is why Dashboard 2 looked unchanged. | – | Hidden data | High | Walkthrough |
| F2 | `RouteRecommender.jsx` 185–190 | "Strategic Overrides" is fixed text, not an input. The dashboard can never send `overrides` (avoid hubs, cost ceiling, max delay), and "Auto-bypass enabled for verified chokepoints" is false (T3). | T3 | False claim, missing feature | High | Walkthrough |
| F3 | `RouteRecommender.jsx` 76–98 | Hub search problems: the text isn't URL-encoded (M11); every keystroke sends a request, and a slow older reply can overwrite a newer one; editing the box after picking a hub keeps the old hub, so the route can use a different hub than the box shows; and typing a name without clicking a suggestion sends an empty origin. | M11 | UX bugs | Medium | Walkthrough |
| F4 | `RouteRecommender.jsx` 211–259 | Route cards show neither the threat nor per-leg time, cost or scenario reason, so users can't see why a route was chosen | – | Missing explainability | Medium | Walkthrough |
| F5 | `RouteRecommender.jsx` 199–207, 282–285, 294–299 | Hardcoded claims: "ACTIVE GLOBAL DISRUPTION DETECTED" appears as soon as you pick a scenario, and "0ms co-location miracles detected" and "TRUTH AUDIT VERIFIED" are always shown, even before any route exists | T12 | False claims | Medium | Walkthrough |
| F6 | `RouteRecommender.jsx` 16–17 | Cargo type and priority have no controls and are always "general" and "normal". The backend ignores them anyway (R6). | R6 | Dead UI state | Low | Walkthrough |
| F7 | `SupplierIntelligence.jsx` 29–31, 84–85 | Clearing an inventory box sends `null` (`parseInt('')` is NaN). The backend rejects it with a 422, `suppliers` becomes undefined, and the page most likely crashes to a blank screen. Confirm by clearing the Inventory box. | – | Crash (likely) | High | Walkthrough |
| F8 | `SupplierIntelligence.jsx` 128, 135–138 | The "Risk Score" column is just 1 − decision score, which mixes in cost and lead time, so a cheap but unreliable supplier shows a low "risk". The code comment admits there is no real risk score. | – | Mislabelled metric | Medium | Walkthrough |
| F9 | `SupplierIntelligence.jsx` 12 | Demand forecast has no input and is always 800 | – | Missing control | Low | Walkthrough |
| F10 | `App.jsx` 8, 20–23 | The engine status from `/ws` is stored but never displayed, so users never see that the NLP warm-up failed (M9, R3) | M9, R3 | Hidden status | Medium | Walkthrough |
| F11 | `App.jsx` 28–108, `BenchmarkCharts.jsx` | The "System Console" and "Benchmarks" screens can't be reached, because no button leads there, yet `App.jsx` still downloads the whole network on every load for them. They also contain false claims ("Live RSS Ingestion Active", "Real-world historical metrics… No synthetic fallback active", "ML Accuracy: 91%"), and every benchmark number is hardcoded. | – | Dead UI, false claims | Low | Walkthrough |

## J. README claims vs reality (DOC)

| # | Where in README | Claim vs reality | Explains | Kind | Impact | Found by |
|---|---|---|---|---|---|---|
| DOC1 | Key Features | "Monitors global RSS feeds to detect local disruptions", but live news is never fetched (R4, W2) | T22 | False claim | High | Walkthrough |
| DOC2 | Key Features | "Trained on 50,000+ real-world historical incidents", but the training data is simulated (to cover in tomorrow's ML review), and the router never calls the model (R2) | R2 | False claim | High | Walkthrough |
| DOC3 | Decision Superiority Benchmarks | "Suez Canal Failure: Reroutes automatically via Cape of Good Hope", but FASTEST and BALANCED sail through the blocked canal (T3, R9) | T3 | False claim | High | Walkthrough |
| DOC4 | API Usage Example | The sample response, labelled "captured from a real run", already shows the bugs: BALANCED through the blocked canal (threat 1.0) and "reduces total landed cost by 396%" | T3, T8 | Evidence | Medium | Walkthrough |

## K. From `backend/engine/threat_intelligence.py` (TI)

| # | Lines | Finding | Explains | Kind | Impact | Found by |
|---|---|---|---|---|---|---|
| TI1 | 157 | `torch.load` has no `map_location`. The anchors were saved on a GPU, so on a CPU machine the NLP never starts (confirmed by running it). | T20 | Silent crash | High | Walkthrough |
| TI2 | 162–166 | Both failure paths are silent to the rest of the app. A missing anchors file sets `_ready = False` with no message, and any exception is only printed, so the router's warm-up never finds out (R3). | T20, R3 | Hidden failure | High | Walkthrough |
| TI3 | 177 | The noise-floor check is inverted (`>=` should be `<`). Real threats return 0, noise passes, and negative margins give negative scores. Measured: Ever Given 0.567 → 0.000, road 0.018 → 0.006, air −0.155 → −0.054. | T21 | Wrong number | High | Walkthrough |
| TI4 | 145, 178 | The score scale isn't calibrated. `margin × 0.35` tops out around 0.2: a real canal blockage scores 0.198 once TI3 is fixed. The original prototype's 3.5 saturates instead: routine congestion scores 0.93, almost the same as a blockage at 1.0. Neither value is fitted to labelled data. | – | Calibration | Medium | Walkthrough |
| TI5 | 176 | The margin takes the best disaster match over all chunks minus the best safe match over all chunks. The two can come from different chunks, so one calm chunk cancels one alarming chunk. The original prototype computed the margin per chunk and took the maximum (`Code/nlp_engine.py:48–55`), which catches a disaster buried in good news. | – | Wrong logic | Medium | Walkthrough |
| TI6 | 172 | Text is cut every 256 characters, which can split words and sentences; the original split by sentence | – | Quality | Low | Walkthrough |
| TI7 | 191–194 | CARF is inverted: a sea threat is zeroed exactly when the news is about the sea (the sea fallback goes 0.930 → 0 once TI3 is fixed), and the same happens for air. The intended rule, as in `Code/nlp_engine.py:64–82`, is to drop the threat only when the news is about another mode and not this one. | T21 | Wrong logic | High | Walkthrough |
| TI8 | 190 | Words are matched after `.split()`, so punctuation and plurals break matching. "…the Suez canal" scores 0.0 but "…the Suez canal." scores 1.0, and "ports" never matches "port". | – | Wrong logic | Medium | Walkthrough |
| TI9 | 183–194 | `relevance_map` is never used; the filter retypes shorter lists instead. Rail and road are never checked. "terminal" sits in the air list although it's also a port word. The original's place check (was the origin or destination named in the news?) was dropped. | – | Missing logic | Medium | Walkthrough |
| TI10 | 62–69, 27–34 | Unknown inputs are silently encoded as the first class: any unknown place becomes "Atlanta Air Hub", a mode spelled differently ("Sea") becomes "air", and weather "Stormy" becomes "Clear". The model knows only 16 place names. `hub_map` covers 19 old US/Indian city names, 9 of which aren't in the model either, while the model's Shanghai, Rotterdam, Singapore and Dubai have no entry. So every live hub is predicted as Atlanta → Atlanta: "Shanghai → Rotterdam" and "PORT-SHANGHAI → PORT-ROTTERDAM" both give 24.2h. | R2 | Wrong input | High | Walkthrough |
| TI11 | 71–73, 99–100 | Even with correct names, the model's inputs don't exist in the live app. The router has no weather (and the training data ignores weather anyway, DS5). The NLP score on the model's training scale (about 0.5 × delay ÷ p90, DS4) has nothing to do with the live NLP score (margin × multiplier). | DS4, DS5 | Feature mismatch | High | Walkthrough |
| TI12 | 105–115, 120–122 | The calibration applied to the model's output was computed from a different dataset, the geo generator's, not the model's training data. p5 floor / p95 for sea: 20.6 / 1,169.9h vs 4.6 / 83.7h in the training data; for road: 2.6 / 68.2 vs 0.7 / 9.6. So the "Historical p5/p95" in the reason text quotes the wrong dataset, the floor pushes short predictions up, and the cap is too loose to stop the NLP-driven blow-up (259h at NLP 1.0). | – | Wrong calibration source | High | Walkthrough |
| TI13 | 77–89 | Before the model loads, it returns fixed guesses (road 2.5h, sea 48h, …) that are still labelled `p_quantile: 0.85` and `is_defensible: True` | – | Misleading output | Low | Walkthrough |
| TI14 | 136–138 | Any inference error returns a delay of 0 ("no delay") with most keys missing. A caller reading `raw_model_prediction` would crash, and a failure looks like the safest possible answer. | – | Dangerous default | Medium | Walkthrough |
| TI15 | 11–14 | Model and anchor paths are relative to the current folder (`./Execution/...`), so the app only works when started from the repo root. The other modules build paths from their own file location. | – | Robustness | Medium | Walkthrough |
| TI16 | 4–8, 197–198 | `time`, `Optional` and `Tuple` are imported but never used. `torch` is imported at the top only for one `torch.load`, which costs 2.7s at startup. `max_pool_threats` is never called. | – | Dead code, startup | Low | Walkthrough |

## L. From `Code/real_dataset_builder.py`, the training data of the shipped model (DS)

| # | Lines | Finding | Explains | Kind | Impact | Found by |
|---|---|---|---|---|---|---|
| DS1 | 6–9, 59–121 | Not real data: 50,000 rows are generated by a seeded random generator, and no records are read. The file name "Real_Historical" (line 126), the printed "Source Anchors: UNCTAD, World Bank CPPI, STB Rail Reports, IATA" (line 130) and the README (DOC2) all overstate it. | DOC2 | Misleading | High | Walkthrough |
| DS2 | 13–44 | The only "real" input is 16 typed-in median/p90 pairs. They carry source labels but no citations. They describe dwell time in port or terminal (line 14), not route delay, yet the column is `Delay_Hours` and the model is presented as predicting worst-case delay. | – | Unverifiable source | Medium | Walkthrough |
| DS3 | 91–99 | The comment says "fit median and p90", but only the median is used and the shape is fixed at 2. The generated p90s miss the stated ones (Rotterdam 90 → 53.4h, Los Angeles 240 → 84.9h, Suez 144 → 28.4h), and the generated medians come out about 16% low. | – | Wrong fit | Medium | Walkthrough |
| DS4 | 109–111 | Target leakage: NLP severity is computed from the row's own delay (0.5 × delay ÷ p90 + noise). It carries 47% of the model's feature importance, with a correlation of 0.56 to the delay. Dividing by the typed-in p90 also means the same delay gives a different "severity" at different hubs. | TI11 | Leakage | High | Walkthrough |
| DS5 | 87 | Weather is drawn at random and never used, so it has no effect (sea p85: 56.5h clear vs 55.3h stormy), yet the model and the API accept it | TI11 | Dead feature | Medium | Walkthrough |
| DS6 | 64–85 | The delay depends only on the origin's anchor (lines 69, 75, 81). Destination and distance play no part, so Shanghai → Singapore and Shanghai → Rotterdam get the same delay distribution. | – | Missing signal | High | Walkthrough |
| DS7 | 61, 64–87 | Every category is drawn uniformly at random: 25% per mode, 33% per weather type, and any port to any port. That includes "Suez Canal" as an origin port, and "Houston Port" listed as a rail hub. | – | Unrealistic | Low | Walkthrough |
| DS8 | 82–85 | Every road row is "Regional Hub" → "Local Terminal", so the model can learn nothing place-specific for road | – | Thin data | Low | Walkthrough |
| DS9 | 101–107 | Incidents barely exist: only 191 of 50,000 rows (0.4%) got one, because the 5% draw only applies when mode and location happen to match. "Red Sea Security 2024" was drawn 457 times and applied 0 times: its location, "Dubai Logistics Hub", is an air hub and never a sea port, so it can never fire. The incident years are unused, and the Canada port strike is attached to Shanghai (line 50). | – | Dead logic | Medium | Walkthrough |
| DS10 | 88 | `Leg_Type` is derived from the mode (sea/air → Global_Freight, everything else → Last_Mile), so it adds no information | – | Redundant feature | Low | Walkthrough |
| DS11 | 126–127 | The script writes to `Execution/...csv` relative to the current folder without creating it, so it only runs from the repo root. `*.csv` is git-ignored, so the training data isn't in the repo; it can be regenerated because the seed is fixed. | – | Reproducibility | Low | Walkthrough |

## M. From `Code/ML_Model_Real.py`, the script that trained the shipped model (MR)

| # | Lines | Finding | Explains | Kind | Impact | Found by |
|---|---|---|---|---|---|---|
| MR1 | 25, 41 | The model is trained with the leaked NLP column (DS4) and depends on it. On its own held-out rows it covers 85.1% of delays. With the NLP score set to 0, which is what the live app sends, coverage falls to **46.4%** and pinball loss triples (2.08 → 6.91), so without the leak it isn't a p85 model. | DS4, TI11 | Leakage | High | Walkthrough |
| MR2 | 28–42 | A test set is split off (line 28) but never used. No coverage or pinball loss is reported, and the imported `mean_absolute_error` and `r2_score` are never called, so the "p85" claim was never checked by the script. | – | No evaluation | High | Walkthrough |
| MR3 | 19–22 | Place names are label-encoded into integers 0–15 in alphabetical order ("Atlanta Air Hub" = 0, "Chicago Rail Hub" = 1, …), and the trees split on them as if they were ordered numbers. With 16 names, one-hot or native categorical handling would be correct. The fixed vocabulary is also what makes every unknown live hub become "Atlanta" (TI10). | TI10 | Encoding | Medium | Walkthrough |
| MR4 | 28 | A random row split puts the same origin/destination pairs in both train and test, so the held-out score can't show how the model does on new places, which is exactly the live situation | – | Evaluation design | Medium | Walkthrough |
| MR5 | 32–39 | Only one quantile (0.85) is trained, with fixed untuned settings (400 trees, depth 6) and no early stopping. There are no p50/p95 models, so no confidence band is possible. | README feature ask | Missing feature | Medium | Walkthrough |
| MR6 | 48–49 | The script overwrites `Execution/risk_model.pkl` and `label_encoders.pkl`, and so does `ML_Model_Geo.py`. Nothing records which script or dataset produced the shipped files; we identified it only from the tree count (400) and the 16 place names. The calibration file comes from the other dataset (TI12). | TI12 | Provenance | Medium | Walkthrough |
| MR7 | 12 | It reads the CSV from a path relative to the current folder, so it only runs from the repo root after `real_dataset_builder.py` has been run there | DS11 | Reproducibility | Low | Walkthrough |
