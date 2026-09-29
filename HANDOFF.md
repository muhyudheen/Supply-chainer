# Handoff for the second session (frontend + model)

TatHack '26 prelim, problem statement 6 (Supplychainer). Team: muhyudheen (backend), abeltjoseph2005-art (frontend + model). Written 29 Sep 2026.

If you are a Claude Code session reading this, read `BUG_REPORT.md` first, then this file. `BUG_LIST.md` has all 126 findings with IDs.

## 1. Set up on the second device

1. **Accept the GitHub invite** as `abeltjoseph2005-art`, at https://github.com/muhyudheen/Supply-chainer/invitations. The repo is private until submission.
2. **Pick one way to run Claude Code.**
   - **Web (no install):** go to https://claude.ai/code, sign in, connect GitHub as `abeltjoseph2005-art`, and choose `muhyudheen/Supply-chainer`. The session works on a cloud copy and pushes to GitHub.
   - **Desktop app or CLI:** install from https://claude.com/code, sign in, and open the cloned folder (steps 3–5).
3. **Authenticate git.** Run `gh auth login` and choose GitHub.com, HTTPS, and "Login with a web browser". Then run `gh auth setup-git`.
4. **Set your commit identity.** Use the email on your GitHub account so the commits count as yours.
   ```
   git config --global user.name "abeltjoseph2005-art"
   git config --global user.email "<your GitHub email>"
   ```
5. **Clone and install.** This needs Python 3.13, `uv` and Node 22. Keep the folder outside OneDrive or Dropbox.
   ```
   git clone https://github.com/muhyudheen/Supply-chainer.git
   cd Supply-chainer
   uv sync --compile-bytecode
   npm ci --prefix frontend
   ```
6. **Run it.** Use two terminals, both started in the repo root.
   ```
   uv run uvicorn backend.main:app --port 8000
   npm run dev --prefix frontend
   ```
   The dashboard is at http://localhost:5173 and the API docs at http://127.0.0.1:8000/docs.

## 2. Who owns which files

To avoid merge conflicts, only edit files you own. If you need a change in someone else's file, ask first.

| Owner | Files |
|---|---|
| **Backend (muhyudheen's session)** | `backend/engine/threat_intelligence.py`, `route_recommender.py`, `multimodal_network.py`, `scenario_manager.py`, `node_resolver.py`, `news_ingestion.py`, `backend/main.py`, `backend/data/*`, `backend/tests/test_round*.py` |
| **Frontend + model (this session)** | `frontend/src/*`, `Code/*` (new files only; don't overwrite the originals), new notebooks, new `Execution/*_v2*` artifacts, `backend/tests/test_frontend*` / `test_model*` |

## 3. Status (29 Sep, 5 PM)

- Two infrastructure commits: node_modules untracked, and the uv project added.
- Bug list and bug report committed (`4699d1e`).
- **Round 1 is done** (NLP engine, `BUG_REPORT.md` §1). All 13 tests in `backend/tests/test_round1.py` pass. The fixes, one commit each: TI1 CPU load, TI2/R3 warm-up failure reported, TI3 inverted floor plus a linear score scale (margin ≤ 0.04 → 0, margin ≥ 0.6 → 1, via `score_from_margin`), TI5 per-chunk margin, TI7–TI9 CARF rewrite, and W1 (no live news means threat 0). The NLP threat score is now 0–1 on that linear scale; the model rebuild should use the same scale for its news-severity feature.
- **Next for the backend:** round 2, the graph (N7, N9, N10, N11, L1). Then round 3, scenarios (R9, S2).

## 4. Your tasks, in order

### A. Frontend fixes (`BUG_REPORT.md` §8)

| ID | File | What to do |
|---|---|---|
| F7 | `SupplierIntelligence.jsx` | Clearing an inventory box sends `null`, the backend replies 422, and `suppliers.map` crashes. Keep the previous number when the input is empty, and guard `data.suppliers ?? []`. |
| F1 | `RouteRecommender.jsx` 266–286 | The audit panel always shows `recommendations[0]`. Make cards selectable and show the selected card's audit. |
| F5 | `RouteRecommender.jsx` 199–207, 282–285, 294–299 | Remove the hardcoded "TRUTH AUDIT VERIFIED", "0ms co-location miracles detected" and "DISRUPTION DETECTED". Show real facts instead, e.g. the active scenario name and the number of legs affected. |
| F10 | `App.jsx` 8, 20–23 | The `/ws` status is stored but never shown. Pass it down and show the engine status, including "WARM-UP FAILED", in the header. |
| F8 | `SupplierIntelligence.jsx` 128–138 | "Risk Score" is really 1 − decision score. Rename it to "Decision score", or show the backend's `audit_trace` reliability and penalties. |
| F4 | `RouteRecommender.jsx` 211–259 | Show per-leg time, cost, threat and the scenario reason; the data is already in the response. |
| F3 | `RouteRecommender.jsx` 76–98 | Use `encodeURIComponent` on the query, debounce the search, and clear the chosen hub when the text is edited. |
| F2 | `RouteRecommender.jsx` 185–190 | **Wait for backend round 3.** It turns "Strategic Overrides" into real inputs (hubs to avoid, cost ceiling). Coordinate with the backend first. |

### B. Model rebuild, the headline feature (`BUG_REPORT.md` §6–7)

The shipped model is unusable: it depends on a leaked feature (46.4% coverage when NLP = 0), knows only 16 place names, and was never evaluated. Build a new one next to it, and don't overwrite `Execution/risk_model.pkl` until it's wired in.

1. **New data generator**, `Code/dataset_generator_v2.py`. Draw a hidden disruption severity first, then generate both the delay and a noisy news score from it; never compute the news score from the delay (fixes DS4). Delay should depend on mode, distance, chokepoints passed, weather and disruption (fixes DS5, DS6). Use features every live hub has: mode, great-circle distance, chokepoint flag, region, hub type, condition, news severity (0–1, the same scale as the fixed NLP). Fix the seed, and state clearly in the file that the data is synthetic.
2. **Train p50, p85 and p95.** Use scikit-learn `HistGradientBoostingRegressor(loss="quantile")` or LightGBM, and pin `scikit-learn==1.8.0` on Kaggle to match the app. Hold out whole routes, not random rows. Report coverage per mode (p85 should cover about 85% of delays) and pinball loss. Keep the three quantiles in order.
3. **Calibration and explainability.** Recompute p5/p95 calibration from the same data (fixes TI12), and add SHAP top features per prediction.
4. **Save** the models as `Execution/delay_models_v2.joblib`, and commit the notebook or script plus a short results table.
5. **Wiring into the router** (FASTEST → p50, BALANCED → p85, SAFEST → p95) happens after backend round 3, in `route_recommender.py`, coordinated with the backend.

## 5. How we work

- **Every fix gets a test.** Write the test, watch it fail, fix, watch it pass, then commit once with the bug ID in the message, e.g. `Fix F7: supplier page crash on empty input`.
- **AI disclosure (Rule 6).** When Claude wrote or suggested the change, end the commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`, and log it in `AI_USAGE.md`. The minutes document is written by humans only; Claude does not draft or edit it.
- **Git habits.** Run `git pull --rebase` before starting and before every push. Keep commits small and push often.
- **Tests.**
  - Quick: `uv run python -m pytest -m "not slow" --tb=no -rf`
  - Full, which loads the NLP model (~1 GB RAM): `uv run python -m pytest --tb=no -rf`
  - Frontend: `npm run build --prefix frontend` must succeed.
- **Defense (Rule 14).** Whoever commits a fix must be able to explain it line by line.
