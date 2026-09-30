# Handoff: where we are, what's next

TatHack '26 prelim, problem statement 6 (Supplychainer). Team: **muhyudheen** (repo owner: backend and model) and **abeltjoseph2005-art** (frontend). Updated 30 Sep 2026, 17:30 IST. Rounds 1–8 are done; see the status note below and `BUG_REPORT.md` → Progress.

If you are a Claude Code session: `CLAUDE.md` (loaded automatically) has the working rules. Read this file next, then `BUG_REPORT.md` (root causes, and a Progress table at the end). `BUG_LIST.md` has all 130 findings with IDs. If you run in the cloud, read §8 before doing anything.

## 1. Deadline and today's plan

- **Submission: 30 Sep 2026, 6:30 PM IST.** The owner set this; confirm it against the official submission link. The prelim runs 28–30 Sep.
- **Hard stop on feature work at 16:00.** 16:00–18:30 is for the README, `AI_USAGE.md`, merging the teammate's work, a full demo run, and submitting.

| Time (IST) | Task |
|---|---|
| 07:00–09:30 | Round 7 step 1: the new dataset (§3) |
| 09:30–12:00 | Step 2: train p50/p85/p95 and evaluate |
| **12:00** | **Checkpoint.** If the model isn't trained and tested, drop everything after step 3 except the README |
| 12:00–14:00 | Step 3: wire the model into the router, SHAP, ETA ranges on the cards |
| 14:00–16:00 | Enhancements in §4 order (cargo rules, case-study demo, demo robustness, small graph repair) |
| 16:00–18:30 | README honesty (DOC1–4), `AI_USAGE.md`, merge frontend, demo run end to end, **submit** |

## 2. Where we are

### Backend (owner): rounds 1–6 done
All 133 backend tests (123 fast, 10 slow) and 30 frontend tests pass. Every round has a failing-tests commit, then one commit per fix. The commit list is in `BUG_REPORT.md` → Progress.

| Round | Fixed |
|---|---|
| 1 NLP engine | TI1 anchors load on CPU · TI2/R3 warm-up failure reported · TI3 noise floor and linear 0–1 threat scale (`score_from_margin`: margin ≤ 0.04 → 0, ≥ 0.6 → 1) · TI5 per-chunk margin · TI7–TI9 CARF drops threats only for other modes · W1 no live news → threat 0 |
| 2 Route graph | N7 links work both ways · N9/N4 sea basins, gate chokepoints and trunk lanes with waypoints (`backend/data/sea_network.json`) · N11 no roads across water · N10 no self-loops, 5 km minimum leg · L1 trips start and end in any mode (virtual `__SOURCE__`/`__DEST__` nodes) |
| 3 Scenarios | R9 threat 1.0 closes the hub (response lists `closed_hubs`) · S2 a scenario hits only its own mode · S3 Dubai 48h · M7 unknown scenario is an error · M14 no shared scenario state (`ScenarioManager.get_disruptions(id)`; `activate_scenario` was removed) |
| 4 Audit and API | R10 delay counted once · R11 surcharge in `total_cost` · R12 baseline risk taken before the scenario · M13 errors are 400 (bad input) or 404 (no route), and "établi" is gone |
| 5 Explanations | R18 explanations compare the real routes (no invented %) · R17 shared routes are named in `also_best_for` · S4 Red Sea text doesn't claim rerouting |
| 6 Suppliers | P1 a disruption adds its full delay (Suez +10 days, Hormuz +7) · P2 cost score = cheapest ÷ cost, always 0–1 |
| 7 Model | New simulated dataset, p50/p85/p95 models, wired into routing with ETA ranges and SHAP drivers, live weather (R2, DS1–DS11, MR2–MR6, TI10–TI15). **The §7 manual-check ETAs below predate round 7**: each ETA now includes the model's p50 delay (check 1 is 618.6 h, not 545.1 h, with weather 0) |
| 8 Cargo | N1 cargo rules enforced, R6 validation and `cargo_rules` in the response, N2 priority weights BALANCED's time |

Infrastructure: `node_modules` untracked (`5091a1f`), uv project (`5e8d58a`), plain `pytest` finds `backend` (`919ba0d`).

### Frontend (teammate), as of 30 Sep 00:30
- **Done on his laptop, not pushed yet:** F7 (supplier page crash), F2 (real override inputs plus a `closed_hubs` banner), F1 (selectable cards; the audit panel follows the selection). He tests with `npm test --prefix frontend` (Node's built-in runner) and builds into a scratch folder, because `frontend/dist` is tracked.
- **In progress:** F4 (per-leg details), F5 (remove hardcoded claims), F10 (show engine status), F3 (hub search).
- **F8 approved:** replace the fake "Risk Score" with Reliability (`audit_trace.scores.reliability`), the disruption penalty (`audit_trace.penalties.risk_inflation`) and the decision score. No backend change needed.
- **`AI_USAGE.md`:** he creates it with a `## Frontend (abeltjoseph2005-art)` section. The backend adds `## Backend (muhyudheen)` **after** his push. Don't create the file before then, or both of you add the same new file and git reports a conflict.
- He was told to re-clone outside OneDrive: the Vite dev server there misses file saves.

## 3. Next goal: round 7, the model rebuild (headline feature)

The owner may call this "round 6"; in the commits it's round 7, because round 6 was suppliers.

**Why:** the shipped model (`Execution/risk_model.pkl`, from `Code/real_dataset_builder.py` + `Code/ML_Model_Real.py`) is never called by the router (R2). It was trained on a feature leaked from the target (DS4), knows only 16 made-up place names (TI10/TI11/MR3), and was never evaluated (MR2). Its data is simulated but labelled "Real Historical" (DS1). Leave these old files untouched as the "before".

### Design
- **One shared feature function:** `backend/ml/features.py` has `leg_features(...)`, used by both the dataset builder and the router. Training and serving then can't disagree about what a feature means, which is exactly what broke the old model.
- **New files:** `backend/ml/__init__.py`, `backend/ml/features.py`, `backend/ml/dataset.py` (seeded builder), `backend/ml/train.py`, and the artifacts in `backend/ml/artifacts/`.
- **Features (all must be available in the live app for any hub):**
  - mode
  - leg distance in km
  - origin and destination hub type and importance
  - passes a chokepoint (yes/no)
  - region or sea basin
  - weather severity 0–1
  - news severity 0–1, on the same scale as the fixed NLP (`score_from_margin`)
  - no hub names or IDs
- **Rows come from our real graph:** sample transit edges of `create_multimodal_network()` (439 hubs, real distances), not a hand-typed list.

### Dataset rules (each fixes a finding)
| Finding | Rule |
|---|---|
| DS4 leakage | Draw the disruption and news severity **first**; the delay depends on it. On calm rows the news score is small noise that doesn't depend on the delay. Never compute a feature from the delay. |
| DS5 weather | Weather severity raises the delay (stormy sea > clear sea). |
| DS6 | Longer legs have more delay spread; chokepoint legs get congestion. |
| DS3 | Fit the gamma **shape and scale** so both the stated median and p90 of each anchor are matched. |
| DS9 | Incident rate about 4–5% (it was 0.4%). |
| DS1/DS2 | Say plainly in the file and the README: *simulated, anchored to published dwell-time medians*, with a source note per anchor. |
| DS11 | Paths relative to the file, not the current folder. `*.csv` is git-ignored, so the CSV is regenerated from the seed, not committed. |

### Tests first: `backend/tests/test_dataset.py`
1. No leakage: on rows without an incident, the correlation between news score and delay is about 0.
2. Weather matters: stormy p85 > clear p85 for sea.
3. Distance matters: long legs have a higher p85 than short ones.
4. Each anchor's simulated median and p90 are within 10% of the stated values.
5. At least 3% of rows have an incident.
6. Every feature column comes from `leg_features()`.
7. Same seed, same dataset.

### Step 2: training (`backend/ml/train.py`)
- **Models:** three quantile models, p50, p85 and p95. Use `HistGradientBoostingRegressor(loss="quantile")` if `shap.TreeExplainer` supports it in the installed shap version (check first). Otherwise use `GradientBoostingRegressor(loss="quantile")`.
- **Split:** hold out whole routes with a group split by origin–destination pair (MR4), not random rows.
- **Report:** coverage per mode (p85 should cover about 85%), pinball loss, and that p50 ≤ p85 ≤ p95. Write them to `backend/ml/artifacts/metrics.json` for the README.
- **Save:** the models go to `backend/ml/artifacts/delay_models.joblib`, with metadata (feature list, seed, row count, sklearn version) (MR6). Commit the artifact so the demo doesn't need training. Don't touch `Execution/risk_model.pkl`.
- **Calibration:** recompute it from the same data (TI12), or drop it if the quantiles are already calibrated.
- **Unknown inputs:** raise an error, never fall back silently (TI10, TI14).
- **CPU only:** it's sklearn on about 50k rows, so it takes minutes. No Kaggle needed.

### Step 3: wiring
- In `route_recommender.py`, FASTEST uses p50, BALANCED p85 and SAFEST p95 as the delay estimate per leg (R2).
- Each card gets an ETA range (e.g. "545h, likely 520–610h").
- SHAP gives the top 2–3 features per route, e.g. "weather +12h, chokepoint +8h".
- Make paths independent of the working folder (TI15).

### Open decisions: ask the owner before starting
1. **Weather:** use live weather in the app via the existing Open-Meteo provider (`backend/engine/weather_integration.py`: free, no key), falling back to 0 when offline? Recommended: yes.
2. **Add `shap`:** `uv add shap`. It isn't installed, and step 3 needs it.

## 4. After the model, in priority order
1. **ETA range on the cards:** comes with step 3.
2. **README honesty:**
   - fix DOC1 (live RSS claim), DOC2 ("50,000 real incidents"), and DOC3/DOC4 (auto-reroute claim and a sample response showing old bugs)
   - add one setup command, the test count and the model metrics
3. **Enforce cargo type and priority** (R6/N1): hazardous goods can't fly, perishables can't go by sea, urgent shipments weigh time more.
4. **Case-study demo:** replay Ever Given (Suez 2021) and the Red Sea crisis (2024) with the existing scenarios.
5. **Demo robustness:**
   - R19: say "warming up" instead of serving stale threats
   - M5: the graph is built twice
   - M9/M10: status values are hardcoded
6. **Small graph repair:** N8 (34 links point to hubs that don't exist, e.g. `AIR-CHENNAI`) and N12 (rename the duplicate `HUB-CHICAGO`). Every new sea hub also needs a basin in `sea_network.json`, and the round 2 tests must still pass.
7. Skip unless time is left: live news (R4/W2/R5; venue Wi-Fi is a risk), a CI badge, big graph expansion.

## 5. Known open issues
- **R20, a 5-minute first task:** `_explain` in `route_recommender.py` makes SAFEST say "Avoids FASTEST's peak threat of X" even when its own threat is also X (manual case 10: both 0.75). Say the threat is the same instead, and add a test in `test_round5.py`.
- **R19:** requests during the warm-up get threat 0.05 / "Standard conditions". Wait for `[WARMUP] Unified Calibration Complete.` before manual testing.
- **N12:** the duplicate `HUB-CHICAGO` is only guarded in the road auto-wire.
- **`scratch/procurement_attack_suite.py`** (organizers' scratch script) still calls the removed `activate_scenario`. It isn't part of the app; fix it or leave it.
- **Still open from the list:** R2, R4/W2/R5, R6/N1, M2 (`PREFERRED` does nothing), N5, N8, M5, M9/M10, M12, R13–R16, TI4, DOC1–DOC4, and the frontend F-items not yet pushed.
- **`BUG_LIST.pdf`** in the owner's OneDrive folder predates S4, R19, R20 and N12. It's a local copy, not in the repo; regenerate it if it's needed for the submission.

## 6. The system now (what changed for API users)
- **Endpoints** (`backend/main.py`): `POST /api/recommend`, `POST /api/suppliers`, `GET /api/scenarios`, `/api/hubs`, `/api/hubs/search`, `/api/cities`, `/api/network`, `/api/status`, and the `/ws` websocket.
- **`/api/recommend` response:**
  - top level: `origin`, `destination`, `active_scenario`, **`closed_hubs`**, `recommendations[]`
  - each card: `persona`, `legs[]`, `adjusted_eta`, `total_cost`, `threat_level`, `audit_trace` {eta, cost, risk buckets that add up}, `explanation`, **`also_best_for`**, `override_applied`
  - each leg: `from`, `to`, `to_name`, `mode`, `type`, `eta`, `cost`, `threat`, `reason`, `intel_source` (`"SCENARIO"` when a scenario hit it)
- **Overrides:** `{avoid_chokepoints: [hub ids], cost_ceiling: USD, max_delay: days}`. `max_delay` is compared to the whole trip time (R13).
- **Errors:** `{"error": ...}` with HTTP 400 (unknown hub or scenario) or 404 (no route).
- **Scenario data:** each disruption carries a `mode`. Use `ScenarioManager.get_disruptions(scenario_id)`.

## 7. Manual checks with expected outputs (at `fb7959a`)
Run `uv run uvicorn backend.main:app --port 8000`, wait for the warm-up line, and use http://localhost:8000/docs. Before retesting, **restart the server**: without `--reload` it keeps serving old code, which fooled us once. Also check nothing old is holding port 8000. Bodies use `transport_preference: "sea"` unless noted.

| # | Request | Expected |
|---|---|---|
| 1 | Shanghai → Rotterdam (`PORT-SHANGHAI` → `PORT-ROTTERDAM`) | One card, FASTEST, `also_best_for` [SAFEST, BALANCED]. **545.1 h**, $2,861.91. Chokepoints Malacca → Bab-el-Mandeb → Suez → Gibraltar → Dover. `audit_trace.eta.transfer` 0 |
| 2 | Rotterdam → Shanghai | 545.1 h, same chokepoints reversed |
| 3 | `PORT-BAKU` → Rotterdam | **404**, "No valid multimodal route found under the current constraints." |
| 4 | `PORT-JEBEL` → Shanghai | 290.6 h via Hormuz, Malacca |
| 5 | Shanghai → `PORT-PIRAEUS` | FASTEST 404.4 h via Suez; BALANCED 404.8 h |
| 6 | 5 + `SUEZ_BLOCK` | `closed_hubs` ["CHOKE-SUEZ"]; **740.4 h** via Malacca, Cape of Good Hope, Gibraltar |
| 7 | 4 + `HORMUZ_CLOSURE` | `closed_hubs` ["CHOKE-HORMUZ"]; 295.8 h, first leg ROAD (truck to Sohar), 1 transfer |
| 8 | 1 + `RED_SEA_CONFLICT` | FASTEST 617.1 h, $2,922.63, threat 0.85, Bab-el-Mandeb leg `SCENARIO`, trace transit 545.1 + scenario 72. SAFEST 704.7 h via the Cape, "+87.6h and $777 more than FASTEST" |
| 9 | `PORT-SINGAPORE` → `PORT-CHENNAI` + `CHENNAI_FLOOD` | 99.7 h, the same as without it; no SCENARIO legs |
| 10 | `PORT-CHENNAI` → `HUB-CHENNAI`, `transport_preference: "road"`, + `CHENNAI_FLOOD` | 48.6 h (0.6 h without), scenario leg `HUB-CHENNAI`, trace scenario 48. SAFEST text shows R20 |
| 11 | `GET /api/scenarios` | `DUBAI_AIR_CONGESTION` delay_hours 48 |
| 12 | 1 with scenario `SUEZ_BLOK`; source `NOWHERE` | **400** "Unknown scenario…"; **400** "Entry point unavailable for NOWHERE" |
| 13 | `POST /api/suppliers` {"category":"Semiconductors","scenario":"NOPE"} | **400** "Unknown scenario 'NOPE'" |
| 14 | `POST /api/suppliers` {"category":"Electronics"} | EuroCore 0.89, Resilient Circuits 0.88, Desert Tech 0.86 (8 d), Global Dynamics 0.84 (14 d). With Hormuz: Desert Tech 15 d, 0.67, last. With Suez: Global Dynamics 24 d, 0.62. Raw Materials cost scores 0.92 and 1.0 (never negative) |
| 15 | NLP, after the warm-up | Transit legs: threat 0.0, "No live news for this corridor". Ever Given text ≈ 0.62, calm port text 0.0. CARF on "Airport runway closed after snowstorm" (0.9): sea 0.0, air 0.9 |

## 8. Working in Claude Code on the web (cloud)

### What a cloud session cannot see or do
- **This conversation.** A fresh cloud session knows only what's in the repo: this file, `CLAUDE.md`, `BUG_REPORT.md`, `BUG_LIST.md`.
- **Anything not pushed:**
  - the owner's uncommitted lines in `backend/main.py`: two comments on lines 41 and 43
  - the teammate's unpushed frontend commits
- **Files outside the repo:**
  - the owner's OneDrive hackathon folder: the rules PDF, problem-statement images, `TatHack26_Ranking_CrossCheck.md`, `BUG_LIST.pdf`, `ML_FILES_WALKTHROUGH.pdf`
  - the local scratch folder (`%TEMP%\tathack26`: PDF scripts, measurement scripts)

  The problem statement's asks are in `README.md`, and the rules that matter are summarised in `CLAUDE.md`.
- **Desktop-only tools:** the in-app browser pane (dashboard preview), computer use, Claude in Chrome, the owner's terminal. The cloud session can run uvicorn and query it with `curl` or `TestClient`, but clicking through the dashboard happens on a laptop after `git pull`.
- **A GPU:** there isn't one, and none is needed.

### Setup in the cloud
- Run `pip install uv` if uv is missing, then `uv sync`. That needs network access to PyPI and **download.pytorch.org** (CPU torch). If the environment's network is restricted, allow those or use full access.
- The 9 slow tests download the MiniLM model from **huggingface.co** the first time. If that's blocked, run `uv run pytest -m "not slow"` and leave the slow tests to the laptop.
- The CSV dataset is git-ignored. Regenerate it with the seeded builder; don't commit it.

### Git in the cloud
The cloud session may work on its own branch. First `git pull origin main`, because the teammate pushes frontend commits to `main`. Then commit per fix as usual and push; the owner merges into `main`. On the laptop, before `git pull`, **commit or stash the local `main.py` comments**, or git refuses to pull if they touch the same file.

### Cost (the cloud runs on the owner's $100 cloud credit)
- Start fresh sessions from this file rather than long conversations: every step re-reads the whole conversation.
- Batch requests ("do steps 1 and 2"), keep outputs short (`--tb=line`, `| tail`), and run slow tests only before commits that could affect them.
- Use a cheaper model for routine edits (README, merges) and keep the strongest one for the model work and debugging.
- The teammate must use his own account; sharing the owner's burns the same budget.

## 9. Who owns which files
| Owner | Files |
|---|---|
| **Owner's session (backend + model)** | `backend/**` (engine, `main.py`, data, tests, the new `backend/ml/`), `BUG_*.md`, `HANDOFF.md`, `CLAUDE.md`, `pyproject.toml`, `uv.lock`, `README.md` |
| **Teammate (frontend)** | `frontend/**`, and his own section of `AI_USAGE.md` |

If you need a change in the other person's files, ask first.

## 10. Setup on a new device (teammate or laptop)
1. The GitHub invite for `abeltjoseph2005-art` is at https://github.com/muhyudheen/Supply-chainer/invitations. The repo is private until submission.
2. Run Claude Code under **your own account** (claude.ai/code on the web, or the desktop app or CLI). Don't share a login.
3. `gh auth login` (GitHub.com, HTTPS, web browser), then `gh auth setup-git`. Set `git config --global user.name` and `user.email` to your GitHub identity.
4. Clone **outside OneDrive or Dropbox**, then install. This needs Python 3.12–3.13, `uv` and Node 22:
   ```
   git clone https://github.com/muhyudheen/Supply-chainer.git
   cd Supply-chainer
   uv sync --compile-bytecode
   npm ci --prefix frontend
   ```
5. Run, in two terminals from the repo root: `uv run uvicorn backend.main:app --port 8000` and `npm run dev --prefix frontend`. The dashboard is at http://localhost:5173 and the API docs at http://127.0.0.1:8000/docs.
