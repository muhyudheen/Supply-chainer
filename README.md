# Supplychainer: Context-Aware Agentic Routing Engine

> **An NLP-driven Risk Assessment API & Executive Command Dashboard for Dynamic Supply Chain Graph Routing.**

Traditional supply chain routing algorithms (like Dijkstra or A*) rely on static distances. But in the real world, supply chains are disrupted by dynamic **Black Swan events**—hurricanes, worker strikes, and geopolitical blockades. 

**Supplychainer** is a dual-component platform:
1. **Agentic AI Backend**: Intercepts root requests, scores the risks on the path, apply logical context filters, calculates the **p50/p85/p95 percentile delay**, plans each persona with a quantile of the delay model: **FASTEST p50, BALANCED p85, SAFEST p95**. 
2. **Executive Command Dashboard**: A high-performance, multimodal React frontend to visualize risks, trigger live simulations (like a Suez blockage), and perform comparative intelligence auditing.

---

##  Key Features

* **Live Weather & Disruption Scenarios**: Pulls current weather for every hub from Open-Meteo at start-up and simulates real crises (Suez blockage, Red Sea conflict, Hormuz closure, Chennai flood). A closed chokepoint is removed from the network, so routes really go around it.
* **NLP Threat Scoring, Ready for News Feeds**: A MiniLM-based engine turns a news text into a 0–1 threat score and filters out reports about other transport modes (CARF). Connecting a live news feed to it is the next step.
* **Context-Aware Relevance Filter (CARF)**: Eliminates false positives (e.g., ignoring a seaport strike if the transport mode is Rail).
* **Quantile ML Risk Assessment**: Uses a Gradient Boosting Regressor trained on 50,000+ simulated legs from real route graph resembling global incidents to predict the **worst-case p85 scenario buffer**, not just the mean delay.
* **Executive Dashboard**: A Dashboard for viewing different personas, for getting best option by testing how different modes of transport, incidents, constraints reacts.
* **Live weather pull** : Live weather from **Open-Meteo** to analyze delays due to storm or rain.

---

##  The Architecture Pipeline

Our system decouples sensory data from mathematical risk using a 4-stage pipeline:

1. **The Targeted Fetch:** The routing algorithm requests a path (e.g., Shanghai to Rotterdam). The API evaluates the Origin, Destination, and dynamic Choke Points.
2. **The Sensory Brain (Contrastive NLP):** We utilize a `SentenceTransformer` (`all-MiniLM-L6-v2`) with **Contrastive Semantic Anchoring**. It reads the scenario text, splits them via semantic chunking, and calculates a pure "Threat Margin" against a multi-domain matrix of Disasters vs. Safe baseline scenarios.
3. **The Logic Gate - CARF System:** The **CARF** prevents hallucinated delays. If the news reports a *sinking ship*, but the transport mode is an *EV Delivery Van*, CARF zeroes out the threat. It ensures spatial and modal relevance.
4. **The Decision Brain - Quantile ML:** The context-filtered NLP score, combined with tabular operational data, is fed into three **HistGradientBoostingRegressor(`Loss = Quantile Loss`)** models: p50/p85/p95 to predict the delays.
5. **Risk-aware Routing**: For each leg, the router adds the delay at its persona's own quantile (p50 for FASTEST, p85 for BALANCED, p95 for SAFEST) and finds the best route with Dijkstra's algorithm. SHAP then explains which factors, such as terminal dwell, canal queues or weather, make up that route's predicted delay.

---

##  Project Structure

```
Smart_Supply_Chain/
├── uv.lock
├── pyproject.toml
├── backend/
│   ├── main.py                  # FastAPI app + all HTTP/WebSocket routes (the real entry point)
│   ├── data/
│   │   ├── canonical_hubs.json       # 439 hubs in 83 countries: ports, airports, rail yards, distribution hubs, 14 chokepoints
│   │   ├── canonical_locations.json  # city -> per-mode hub lookup
│   │   ├── suppliers.json          # sample supplier records for Supplier Intelligence
│   │   └── sea_network.json        # sea basins, chokepoint gates and trunk lanes (round 2)
│   ├── ml/                         # round 7: the delay model
│   │   ├── features.py             # leg_features(): one feature function for training and the router
│   │   ├── dataset.py              # seeded builder: 50,000 simulated legs from the real graph
│   │   ├── train.py                # trains p50/p85/p95 models, group split by route, metrics
│   │   ├── predictor.py            # batch prediction + SHAP delay drivers for the router
│   │   └── artifacts/              # delay_models.joblib + metrics.json (committed, no training needed)
│   ├── tests/                      # pytest, rounds 1–8 (one file per round of fixes)
│   └── engine/
│       ├── multimodal_network.py     # builds the routable graph from canonical_hubs.json
│       ├── route_recommender.py      # Dijkstra routing + persona weighting (the core solver)
│       ├── threat_intelligence.py    # NLP threat scoring + CARF filter + ML quantile predictor
│       ├── news_ingestion.py         # Google News RSS fetcher (feedparser); built but not yet called by the router
│       ├── scenario_manager.py       # the 6 scripted disruption scenarios
│       ├── supplier_scorer.py        # supplier ranking + procurement advice
│       ├── node_resolver.py          # resolves a city/hub name to a graph entry node
│       └── (baseline.py, graph_model.py, simulator.py, optimizer.py, evaluator.py,
│            benchmark_runner.py, or_baseline.py, weather_integration.py, live_routing.py)
│            — an earlier, US-only prototype pipeline. Not used by the live app — see below.
├── Execution/
│   ├── risk_model.pkl             # trained Gradient Boosting quantile regressor
│   ├── label_encoders.pkl         # categorical encoders for the model above
│   ├── nlp_anchors.pt             # precomputed disaster/safe embedding anchors
│   ├── calibration_profiles.json  # per-mode floor/cap delay calibration
│   └── api.py                     # an older, standalone prototype API — not used by main.py
└── frontend/
    ├── package.json, vite.config.js
    └── src/
        ├── App.jsx                   # top-level view switcher
        ├── RouteRecommender.jsx      # main routing dashboard (calls /api/recommend)
        ├── SupplierIntelligence.jsx  # supplier ranking dashboard (calls /api/suppliers)
        └── BenchmarkCharts.jsx       # static, hardcoded benchmark charts — not live-wired
```

**Two things that look like the main entry point but aren't, so you don't lose time in the wrong file:**
- `Execution/api.py` is an older, standalone prototype with its own `/predict_route_risk`
  endpoint. The real, live API is `backend/main.py`.
- The following files under `backend/engine/` belong to an earlier, US-only prototype and are
  **not** wired into `main.py`'s actual request path: `baseline.py`, `graph_model.py`,
  `simulator.py`, `optimizer.py`, `evaluator.py`, `benchmark_runner.py`, `or_baseline.py`,
  `weather_integration.py`, `live_routing.py`. The live system is the `RouteRecommender` /
  `ThreatIntelligencePredictor` / `multimodal_network` pipeline described above — that's where
  your time is best spent.

---

##  Decision Superiority Benchmarks

Supplychainer shifts logistics from geometric shortest paths to optimal business decisions:
* **Suez Canal Failure**: The `SUEZ_BLOCK` scenario closes the canal (it is removed from the network, and the response lists it in `closed_hubs`), so every route goes around the Cape of Good Hope. Shanghai → Piraeus: 463.5 h via Suez becomes 811.9 h via the Cape (typical ETA; cost $2,123 → $3,887).
* **Paying for Certainty**: Under the Red Sea scenario, FASTEST still sails through Bab-el-Mandeb (threat 0.85), while SAFEST, which plans with the p95 delay, goes around the Cape: +86.2 h typical and $778 more, but its p95 bad-case ETA is 159.5 h lower than FASTEST's.
* **Fast Enough for Interactive Use**: A route request (three personas, 4,222 legs with predicted delays) takes about 0.1–0.2 s after warm-up; loading the delay model and predicting every leg takes 0.3 s at start-up.

---

##  How to Run Locally

### 1. Backend Service (FastAPI)

Run the commands from the repo root: `backend.main:app` and `backend.ml.train` are package paths, so Python has to start where the `backend/` folder is. Data and model files are found from each file's own location, so nothing else depends on the working folder.

The ML model (`risk_model.pkl`) and categorical encoders (`label_encoders.pkl`) are pre-trained and included in `Execution/`. You **do not** need the proprietary CSV dataset to run the API.

```bash
pip install uv                        # once, if uv isn't installed
uv sync --compile-bytecode            # creates .venv and installs pinned dependencies (CPU-only torch)
uv run uvicorn backend.main:app --port 8000
```
*Wait for `[WARMUP] Unified Calibration Complete.` in the log before testing. The first start downloads the MiniLM language model (about 90 MB) and fetches live weather from Open-Meteo (no API key; weather is 0 and marked "offline" if unreachable). API docs: `http://127.0.0.1:8000/docs`.*

Optional:
```bash
uv run python -m backend.ml.dataset   # regenerate the simulated dataset CSV (git-ignored)
uv run python -m backend.ml.train     # retrain the delay models (~5 s on CPU); the trained model is already committed
```
```
*The first boot may take 10-20 seconds to load the HuggingFace transformer weights into memory. API Docs available at `http://127.0.0.1:8000/docs`.*

### 2. Executive Frontend (React/Vite)

```bash
npm ci --prefix frontend
npm run dev --prefix frontend
```
*Access the dashboard at `http://localhost:5173` (or the port specified by Vite).*

### 3. Tests

```bash
uv run pytest -q -m "not slow"        # 123 backend tests, about 20 s
uv run pytest -q                      # all 133: the 10 slow ones load the MiniLM model (about 1 GB RAM)
npm test --prefix frontend            # 30 frontend tests (Node's built-in runner, no extra packages)
```
*One test file per round of fixes (`backend/tests/test_round1.py` … `test_round8.py`, plus `test_dataset.py` and `test_train.py` for the delay model). Each round's tests were committed failing first, then one commit per fix.*

---

##  API Usage Example

**Endpoint:** `POST /api/recommend`
*(this is what the Executive Frontend actually calls — see `frontend/src/RouteRecommender.jsx`)*

**Payload:**
```json
{
  "source": "Shanghai",
  "destination": "Rotterdam",
  "cargo_type": "general",
  "priority": "normal",
  "transport_preference": "any",
  "routing_policy": "STRICT",
  "scenario": "SUEZ_BLOCK"
}
```

**Response** (abbreviated — `recommendations` holds up to 3 persona-optimized routes, each with a full multi-leg `legs` array and `audit_trace`):
**Request** (`POST /api/recommend`):
```json
{"source": "PORT-SHANGHAI", "destination": "PORT-ROTTERDAM", "transport_preference": "sea", "scenario": "SUEZ_BLOCK"}
```

**Response** (trimmed):
```json
{
  "origin": "PORT-SHANGHAI",
  "destination": "PORT-ROTTERDAM",
  "active_scenario": "Suez Canal Blockage",
  "closed_hubs": ["CHOKE-SUEZ"],
  "cargo_rules": {"cargo_type": "general", "excluded_modes": [], "priority": "normal", "balanced_time_weight": 0.3},
  "recommendations": [
    {
      "persona": "SAFEST",
      "legs": [
        {"from": "PORT-SHANGHAI", "to_name": "Cai Mep International Terminal", "mode": "SEA", "eta": 82.5, "cost": 412.03,
         "threat": 0.05, "delay": {"p50": 4.1, "p85": 9.4, "p95": 16.0}, "cargo_handled": false},
        {"from": "PORT-DURBAN", "to_name": "Cape of Good Hope", "mode": "SEA", "eta": 45.8, "cost": 229.35,
         "threat": 0.05, "delay": {"p50": 2.1, "p85": 6.3, "p95": 9.0}, "cargo_handled": false},
        {"from": "PORT-LUANDA", "to_name": "Port of Rotterdam", "mode": "SEA", "eta": 240.1, "cost": 1021.2,
         "threat": 0.05, "delay": {"p50": 45.6, "p85": 126.0, "p95": 196.7}, "cargo_handled": true}
      ],
      "adjusted_eta": 776.8,
      "eta_range": {"p50": 776.8, "p85": 899.7, "p95": 1006.2},
      "total_cost": 3700.51,
      "threat_level": 0.05,
      "audit_trace": {
        "eta": {"transit": 704.9, "transfer": 0, "scenario": 0, "predicted_delay": 72.0},
        "delay_drivers": {"quantile": "p95", "calm_transit_h": 141.74, "total_h": 301.3,
          "drivers": [{"label": "terminal dwell", "hours": 158.16}, {"label": "chokepoint risk", "hours": 1.39}]}
      }
    }
  ]
}
```
*Real response from the current code (weather 0, no live news), trimmed: 3 of 8 legs and 2 of 5 delay drivers shown. Suez is closed, so the route sails around the Cape of Good Hope. Transit 704.9 h + predicted delay 72.0 h = the 776.8 h ETA.*
*(Captured from a real run against the trained model and canonical hub graph — not illustrative placeholder data.)*

There's a second, older prototype endpoint, `POST /predict_route_risk` in `Execution/api.py`. It is **not** part of the live app (nothing imports or serves it from `backend/main.py`) — it's a standalone leftover from an earlier iteration and isn't wired to the frontend.

---

## 💻 Tech Stack

* **Frontend**: React, Vite, Vanilla CSS (Executive Dark-Mode Aesthetic)
* **Backend**: FastAPI, Python, Uvicorn
* **Machine Learning**: scikit-learn `HistGradientBoostingRegressor` with quantile loss (three models: p50, p85, p95), SciPy (gamma fits for the simulated dataset)
* **Explainability**: SHAP (exact Shapley values per route, checked against `shap.TreeExplainer`)
* **NLP**: HuggingFace Sentence-Transformers (all-MiniLM-L6-v2, CPU)
* **Weather**: Open-Meteo API (current weather per hub, free, no API key)
* **Routing & Data**: NetworkX (Dijkstra on the multimodal graph), Pandas, NumPy, joblib
* **Tooling & Tests**: uv (Python environments), pytest, Node's built-in test runner

---

## What We Fixed

The starter code ran without errors but quietly produced wrong numbers and wrong decisions. We logged 130 findings with IDs in [`BUG_LIST.md`](BUG_LIST.md) (root causes in [`BUG_REPORT.md`](BUG_REPORT.md)), then fixed them in rounds: each round's tests were committed failing first, then one commit per fix.

| Round | Area | What was wrong → what it does now |
|---|---|---|
| 1 | NLP threat engine | Threat was 0 everywhere: the anchors only loaded on GPU (TI1). Warm-up failures were hidden (TI2/R3); the noise floor was inverted (TI3); one calm text chunk could cancel an alarming one (TI5); CARF dropped sea threats and ignored rail/road (TI7–TI9); every edge was scored against an invented "congestion" sentence (W1). Now threats are real 0–1 scores, and no news means threat 0. |
| 2 | Route graph | Links worked one way only (N7); ships sailed across land and chokepoints were unreachable (N9/N4); trucks drove across the sea (N11); self-loops and zero-length legs (N10); trips paid for needless mode changes (L1). Now: two-way links, sea basins with real chokepoint gates, lanes around land. |
| 3 | Scenarios | A closed canal only slowed ships down, so routes still sailed through it (R9); a road flood delayed ships (S2); Dubai used 24 h instead of its announced 48 h (S3); a misspelled scenario silently meant "none" (M7); requests shared scenario state (M14). |
| 4 | Audit maths & API | The scenario delay was counted twice (R10); the surcharge never reached the total cost (R11); "baseline" risk already included the scenario (R12); errors came back as HTTP 200 (M13). Now the audit trace adds up to the ETA and cost. |
| 5 | Explanations | Explanations used invented percentages like "396% cheaper" (R18); personas sharing a route were silently dropped (R17); the Red Sea text claimed rerouting (S4); SAFEST claimed to avoid a threat equal to its own (R20). Now every number is a real comparison between routes. |
| 6 | Suppliers | A disruption's delay wasn't fully added to lead time (P1); cost scores could go negative (P2). |
| 7 | Delay model | The router never called the model (R2). It was trained on a leaked feature (DS4), on data labelled "real" that was simulated (DS1), knew 16 place names (TI10), and was never evaluated (MR2). Now: a leak-free simulated dataset from our real graph, p50/p85/p95 models tested on unseen routes, wired into routing, with SHAP delay drivers and live weather. |
| 8 | Cargo & priority | `cargo_type` and `priority` were accepted and ignored (R6, N1, N2). Now hazardous waste never flies, perishables never sail, oversize loads never go by road, and urgent priority makes BALANCED weigh time more. |
| Frontend | Dashboard | Supplier page crash (F7); fake override inputs (F2); audit panel ignored the selected card (F1); hardcoded claims like "TRUTH AUDIT VERIFIED" (F5); a derived fake "risk score" (F8); plus per-leg details (F4), engine status (F10), hub search (F3). Now it also shows the model's ETA range, delay drivers and cargo rules. |
| Docs | README | Claims of live RSS monitoring (DOC1), "50,000 real incidents" (DOC2), and a sample response showing the old bugs (DOC3/DOC4) were corrected. |

Still open, and why, is listed under [Honest Limits and Known Issues](#honest-limits-and-known-issues).

## The Delay Model

**Why:** the original model was never called by the router (R2), was trained on a feature computed from its own answer (DS4), knew only 16 place names (TI10), and was never evaluated (MR2).

**Data (simulated, stated plainly):** 50,000 legs sampled from our real route graph (`backend/ml/dataset.py`). A leg's delay = dwell where cargo is handled (gamma fitted to the organizers' median and p90 per mode; the Suez figure for canals) + an en-route share of travel time (5% typical, 15% on a bad day, raised by weather) + incidents (4.3% of legs). Weather, incidents and news are drawn before the delay, so no input leaks the answer. Every assumed number is labelled in the file.

**Model:** three scikit-learn `HistGradientBoostingRegressor` models with quantile loss: p50 (typical), p85 (bad day), p95 (very bad day). The same `leg_features()` function builds the inputs in training and in the router. Categories are one-hot encoded, and 20% of routes (origin–destination pairs) are held out for testing.

**Results on held-out routes** (`backend/ml/artifacts/metrics.json`):

| Mode | Coverage p50 / p85 / p95 | Pinball loss p50 / p85 / p95 (constant baseline) |
|---|---|---|
| Sea | 49.3 / 84.4 / 94.7% | 11.19 (16.62) / 9.35 (16.30) / 5.12 (8.58) |
| Air | 51.3 / 84.7 / 94.5% | 2.77 (4.80) / 2.15 (4.55) / 1.09 (2.30) |
| Rail | 53.6 / 86.6 / 95.7% | 3.92 (8.29) / 2.90 (6.15) / 1.41 (2.94) |
| Road | 52.1 / 86.5 / 95.6% | 1.45 (2.50) / 1.26 (3.04) / 0.66 (1.79) |
| **All** | **51.5 / 85.5 / 95.1%** | **5.03 (8.32) / 4.08 (7.78) / 2.16 (4.04)** |

**In routing:** FASTEST plans with p50, BALANCED with p85, SAFEST with p95. Every card shows its p50 ETA and the full range. SHAP splits each route's delay into calm transit + terminal dwell + canal queue + chokepoint risk + weather + news (exact Shapley values against the same legs in calm conditions). Example: Red Sea scenario, SAFEST goes around the Cape: +86.2 h typical and $778 more, but a p95 159.5 h lower than FASTEST's.

## Cargo and Priority Rules

The organizers' `MODE_PROFILES` table is now enforced: hazardous waste never flies, perishable urgent cargo never sails, oversize loads never go by road, and each rule comes with its reason. Urgent priority raises BALANCED's time weight from 0.3 to 0.43 (low: 0.25). An unknown cargo type or a forbidden mode returns 400; a trip no mode can serve returns 404 naming the rule. These are the organizers' simplified rules, not real dangerous-goods regulations.

## Honest Limits and Known Issues

* The training data is simulated: the scores show the model learned our simulator and generalises to unseen routes, not real-world accuracy.
* The ETA range adds up per-leg quantiles, so a route's p85/p95 are on the cautious side.
* Weather is fetched once at start-up; live news is not connected to the router yet (news input is 0).
* Dwell during route search is an estimate: on about 8% of trips, FASTEST's shown ETA is 0.4–6.5 h above another card's.
* Still open: R19 (warm-up message), M5 (graph built twice), M9 (hardcoded /ws values), N8 (34 links to missing hubs), N12 (duplicate HUB-CHICAGO), M2 (PREFERRED policy does nothing).

## Team and AI Usage

Muhammed Muhyudheen T (backend, model, docs) and Abel T Joseph (frontend). Claude Code (Claude Opus 5.5) was used throughout; what it wrote is listed in [`AI_USAGE.md`](AI_USAGE.md). Our development minutes are hand-written.

---

##  TatHack Prelim Challenge

This repository is your starting point. There are two things to work on, and you're free to
lean into either or both:

**1. Fix what's broken.** The codebase has a handful of intentionally introduced issues. None
of them crash the app or throw a visible error — they're logic bugs that quietly produce the
wrong number or the wrong decision while everything still "runs fine." Don't trust that a
feature works just because it doesn't error out: test it against a real scenario (for example,
activate the `SUEZ_BLOCK` scenario in the dashboard and check whether the reported threat and
delay actually reflect it) and check the numbers, not just the absence of a crash.

**2. Build what's missing.** Pick one or more ideas from the list below — or bring your own —
and extend the platform. We're not scoring on how many features you bolt on; we're scoring on
whether what you build is genuinely useful, correctly wired end-to-end (not just a UI mockup),
and whether you can explain the trade-offs you made.

---

##  Where You Can Take This

Supplychainer is a working prototype, not a finished product. Here's where the biggest
opportunities are if you want to push it toward something a real logistics team could rely on
— pick what's interesting, you don't need to attempt all of it:

### Smarter AI/ML
- **Wire the trained ML model into live routing.** `ThreatIntelligencePredictor.predict_worst_case_delay()`
  — the p85 quantile model — is loaded and warmed up at startup but never actually called by
  `RouteRecommender.recommend()` today. Only the NLP+CARF semantic score currently feeds route
  weighting. Connecting the model's real delay prediction into the routing decision is one of
  the most meaningful upgrades available in this codebase.
- Predict multiple quantiles (p50 / p85 / p95) instead of a single point estimate, for a
  confidence band instead of one number.
- Add real explainability (e.g. SHAP or permutation importance) to the model's predictions,
  surfaced through the existing `audit_trace`.
- Generalize `CARFFilter` to rail and road with the same rigor it already applies to air/sea —
  it defines relevance keywords for all four modes but only enforces two of them today.
- Categorize threat *type* (strike / weather / geopolitical / infrastructure), not just
  magnitude, so downstream logic can react differently to different kinds of disruption.

### Product & Experience
- Replace the placeholder map text in `App.jsx`'s default view with a real interactive map
  (Leaflet/Mapbox) driven by the existing `/api/network` endpoint.
- Route history — persist and compare past recommendations instead of losing them on refresh.
- Export a route's full audit trail as PDF/CSV for a "boardroom-ready" report.
- Real-time alerts when a newly activated scenario affects a route you've already generated.
- A mobile-responsive layout — the current dashboard assumes a wide desktop screen.

### Global Reach & Data Coverage
- Expand beyond the current ~300 canonical hubs to more regions and secondary ports/airports.
- Multi-language UI — the dashboard is English-only right now.
- Multi-currency cost display instead of a single implicit currency.
- Replace or augment Google News RSS with a richer, more verifiable disruption signal (e.g.
  structured event feeds, AIS vessel tracking, region-specific weather alerts).
- Accessibility: keyboard navigation, screen-reader labels, color-contrast-safe risk indicators.

### Reliability & Scale
- Persist state in a real database instead of in-memory Python objects — right now a restart
  wipes everything, and there's no per-user or per-company data isolation.
- Add authentication and basic multi-tenancy.
- Add automated tests — there currently aren't any, for either the backend or the frontend.
- Cache or pre-compute more of the graph-weighting work so the engine scales past a few
  hundred nodes without the per-request cost growing with it.

### Integrations
- A webhook or export format a real TMS/ERP system could actually consume.
- An API key / rate-limiting layer, if this were ever exposed publicly.

*In association with Arvind and TatHack Team.*
