# Supplychainer (TatHack '26 prelim, PS6)

Team: muhyudheen (repo owner: backend and model), abeltjoseph2005-art (frontend). **Submission deadline: 30 Sep 2026, 6:30 PM IST.**

**Start of every session:** read `HANDOFF.md` (status, next goal, plan, manual checks, cloud notes). Then read `BUG_REPORT.md` (root causes, and a Progress table at the end). `BUG_LIST.md` has all findings by ID (TI, N, R, S, M, P, F, DS, MR, DOC…). Use those IDs in commits and answers.

## What the judges score (README "TatHack Prelim Challenge")
Fixing the planted logic bugs, and building features that are "genuinely useful, correctly wired end-to-end (not just a UI mockup)", with trade-offs we can explain. Not the number of features. The model plan follows README "Where You Can Take This": wire the model into routing, p50/p85/p95, SHAP surfaced through `audit_trace`. The original repo had no tests; ours has 66.

## Rules of work (the owner set these; keep them)
- **Test first.** For each round, commit failing tests first ("Add round N tests for …"). Then **one commit per fix**, e.g. `Fix R9: a closed chokepoint is removed from the graph, not just slowed`, with a short body saying why.
- End every commit Claude wrote or co-wrote with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (hackathon Rule 6: AI disclosure).
- After each fix, give the owner: the code change, a plain-English explanation, and a **one-line version** for the team's doc.
- **Don't** push, delete files, or add dependencies without the owner's go-ahead. Committing is expected.
- **Never** draft, template or edit the team's minutes document. It's human-written only.
- `AI_USAGE.md` belongs partly to the teammate. Add the backend section only after his version is on `main` (see `HANDOFF.md` §2).
- Stay in your lane: backend, model and docs are the owner's; `frontend/**` is the teammate's (`HANDOFF.md` §9).
- Other rules: Rule 11 lists the contributors (both team members). Rule 14 is the technical defence: every change must be explainable line by line, so keep fixes small and readable.
- Match the surrounding code style. Don't overclaim in docs or UI text: every number shown must come from real computation.

## Commands (repo root)
- Install: `uv sync --compile-bytecode`. torch comes from the CPU index at download.pytorch.org.
- Fast tests: `uv run pytest -q -m "not slow"`. All tests: `uv run pytest -q` (the slow ones load MiniLM, about 1 GB RAM and about 1 minute).
- API: `uv run uvicorn backend.main:app --port 8000`, then http://localhost:8000/docs. Wait for `[WARMUP] Unified Calibration Complete.` Restart after code changes: without `--reload` it serves old code.
- Frontend: `npm ci --prefix frontend`, then `npm run dev --prefix frontend` (http://localhost:5173).

## Gotchas
- `*.csv` is git-ignored. Datasets are regenerated from seeded builders, not committed.
- `Execution/risk_model.pkl` and `Code/*` are the organizers' originals: the "before" picture. Don't overwrite them. The new model lives in `backend/ml/`.
- Importing `backend.main` takes about 20 s. Tests that need it are marked `slow`.
- Keep outputs short to save the budget: `--tb=line`, `| tail`, targeted reads.
