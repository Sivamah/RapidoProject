# Master Project Context

**Read this document first.** It is the single entry point for any AI (Claude, Gemini, DeepSeek, or other) picking up work on this project after this audit. Everything stated here is evidence-based and cross-referenced to the other documents in this package, which carry full citations (file paths, line numbers, quoted code).

## 1. Project purpose

A-DMFE (Adaptive Dynamic Multi-Service Feasibility Engine) is a final-year academic/research project: an admin dashboard and backend engine that simulates and dispatches ride/food/parcel requests, batching compatible requests into shared trips where a 5-factor compatibility model and an adaptive (learning-driven) decision engine judge them feasible, then optimizing routes with OR-Tools and explaining every decision through an XAI (explainable AI) layer. It is paired with an IEEE-paper-track research/evaluation effort (`backend/evaluation/`) that produces reviewer-response evidence for specific reviewer critique points.

## 2. Architecture

See `FINAL_ARCHITECTURE.md` for the full current-state architecture diagram and layout. In one paragraph: React 19 + Vite + Tailwind frontend talks to a FastAPI + SQLAlchemy + SQLite backend over 12 mounted routers; the core pipeline is Request → Compatibility scoring → (optionally adaptive) Batching → Decision engine → OR-Tools route optimization → Driver/vehicle selection → Trip → Analytics → XAI explanation → Live map highlight, orchestrated end-to-end by `dmfe/pipeline.py::PipelineRunner.run()`, invoked both by manual API triggers and automatically by a background simulator thread.

## 3. Tech stack

- **Backend:** Python, FastAPI, SQLAlchemy, SQLite (dev), Pydantic, OR-Tools (`ortools.constraint_solver`), bcrypt/JWT auth, pytest.
- **Frontend:** React 19, Vite, Tailwind CSS 4, `@react-google-maps/api`, `react-leaflet`/Leaflet, recharts, axios, react-router-dom 7, framer-motion, lucide-react, react-hot-toast. Lint via `oxlint`; no frontend test runner currently wired (`package.json` has no `test` script and no test files exist under `frontend/src`).
- **External services:** Google Maps Distance Matrix API (synchronous call from `dmfe/optimizer.py`).

## 4. A-DMFE / DMFE algorithms (protected core — see Section 12)

- **Compatibility scoring** (`dmfe/compatibility.py`): a 5-factor model — pickup proximity, route/destination similarity, time-window compatibility, vehicle capacity fit, priority — producing an `overall_compatibility_score` gated against a configurable `min_compatibility_score` threshold (real production default 70, per `REVIEWER_AUDIT.md`'s R1.5 analysis).
- **Batching** (`dmfe/batch_generator.py`): greedy disjoint pairing over the compatibility graph in "static" mode; in "adaptive" mode, context-aware and learning-adjusted thresholds/weights (`dmfe/adaptive/*`) modulate the same underlying scorer.
- **Adaptive layer** (`dmfe/adaptive/`): `context.py` (demand/congestion/time-of-day context awareness), `learning.py` (a persisted learning-state document in `SystemConfig` — residual buffers, driver-quality summaries, corridor maps — feeding `weights.py`'s adaptive weight generation and `decision.py`'s effective-threshold logic).
- **Route optimization** (`dmfe/optimizer.py`): OR-Tools Pickup-and-Delivery-Problem solver for multi-request batches; single-request trips bypass the solver via a documented fast path ("OR-Tools ... is pure overhead here").
- **Driver/vehicle selection & dispatch** (`dmfe/driver_selection.py`): `dispatch_trip()`, `complete_trip()`, `complete_stale_trips()` (bulk-updates stale trips in one query).
- **Decision engine** (`dmfe/decision_engine.py`): `DecisionEngine.run_analysis()`, the entry point for the manual "Run Analysis" trigger.

## 5. Database

SQLite (`backend/dmfe_dev.db`, `backend/qa_test.db`), SQLAlchemy ORM. Key models (`db/models.py`, `dmfe/models.py`): `User`, `Provider`, `Driver`, `Vehicle`, `SimulationRequest`, `DMFEBatch`, `Trip`, `DriverAssignment`, `DriverAssignmentHistory`, `SystemConfig` (also stores adaptive-learning state as JSON), `SystemNotification`, `Dataset`, `SimulationScenario`. A manual migration (`backend/migrations/001_dmfe_batch_predicted_utilization.py`) exists specifically for non-SQLite production targets, since the dev-DB auto-sync in `main.py` is SQLite-only.

## 6. APIs

12 routers mounted under `/api/*` in `main.py` (`auth`, `providers`, `dashboard`, `orchestration`, `simulation`, `xai`, `notifications`, `drivers`, `config`, `dmfe_v2`, `dmfe_engine`). Full endpoint-by-endpoint frontend↔backend tracing is in `FRONTEND_BACKEND_CONNECTION_MATRIX.md` — notably, `dmfe_engine.py`'s granular per-stage pipeline endpoints (compatibility-score, context, batch/create, optimize/route, assign/driver, `/run`, trip complete) are fully implemented and backend-tested but **never called by the frontend**, which instead uses the coarser `dmfe_v2.py::/analyze` endpoint for its "Run Analysis" button and relies on the background simulator for actual dispatch.

## 7. Frontend

14 lazy-loaded pages under `AuthProvider` → `ProtectedRoute` → `AdminLayout`. **As found, the application does not build**: `App.jsx` imports a nonexistent `components/ui/AnimatedBackground`, and 6 of the 14 pages import from component directories that were never committed (`components/drivers/`, `components/config/`, and most of `components/analytics/`, `components/dmfe/`, `components/notifications/`, `components/playback/`). This is documented in full, with every missing file named, in `FRONTEND_OPTIMIZATION.md`'s CRITICAL findings — it is the single most important fact in this package for anyone about to write frontend code. The code that does exist (the map stack, the XAI panels, the shared `api.js` client, the polling/caching hooks) was independently assessed as well-engineered.

## 8. Maps and XAI

Live map: Leaflet + `@react-google-maps/api` via `components/map/LiveMapContainer.jsx` and its layer children, with memoized marker icons and coordinate-fingerprint-keyed effects specifically engineered to avoid re-fetch/re-render storms under polling (see `FRONTEND_OPTIMIZATION.md`'s "Categories With No Findings"). XAI: `services/xai_service.py` generates per-request explanations including real trip-economics fields (`trip_cost_inr`, `separate_cost_inr`, `solo_profit_inr`, `driver_profit_inr`) derived from the same revenue/fuel-cost formula throughout, normalized on the frontend by the single shared `utils/xaiMap.js::normalizeXaiHighlight()` function. The XAI→map same-tab click-through is fully wired; a separate `/live-map?xai=<id>` deep link is implemented and backend-tested but has no in-app control that ever constructs its URL (Partial in the connection matrix).

## 9. Experiments / reviewer evidence

`backend/evaluation/` is a separate toolchain producing IEEE-reviewer-response evidence for five specific critique points (R1.1, R1.3, R1.4, R1.5, R2.1), all verified in `REVIEWER_AUDIT.md` to exercise the real production pipeline (not a reimplementation) via a shared `framework.py::WorkloadRunner` harness. Three of five (R1.1, R1.3, R1.5) are fully verified and consistent end-to-end. Two (R1.4, R2.1) have a real, honestly-labeled single-workload result on disk, but the reviewer-facing roll-up document (`REVIEWER_EVIDENCE_REPORT.md`) cites a broader multi-workload table that has no corresponding data file anywhere in the repository — see `REVIEWER_AUDIT.md` for the exact numbers and `OPTIMIZATION_ROADMAP.md` item P0-3 for the recommended fix.

## 10. Tests

Backend: 11 real `test_*.py` files under `backend/tests/` (pytest-discovered), covering compatibility, scoring, driver selection, three learning-engine phases, pipeline accounting, QA-controlled runs, XAI (static mode + map linkage), and dataset upload. Not covered: authentication, dashboard/analytics aggregate queries, notification CRUD. Reported 73/0 fail per `docs/reports/FINAL_CLEANUP_REPORT.md` (not independently re-executed this session — see Section 14). Frontend: **no automated test files exist** (`setupTests.js` is present as a scaffold, but zero `*.test.jsx` files were found).

## 11. Performance findings summary

Backend: 11 findings (0 Critical / 3 High / 5 Medium / 3 Low) — no correctness bugs, all are efficiency opportunities (duplicated context/state loads in adaptive mode, some full-table scans, some per-row commits). Frontend: 16 findings (7 Critical / 2 High / 4 Medium / 3 Low) — the 7 Critical findings are the missing-files build failures described in Section 7, not runtime performance bugs; the code that does run has no debounce on two search inputs and carries a handful of dead/duplicate component files. Full detail: `BACKEND_OPTIMIZATION.md`, `FRONTEND_OPTIMIZATION.md`, `OPTIMIZATION_ROADMAP.md`.

## 12. Known issues (highest-signal, see roadmap for full list)

1. Frontend does not build (`App.jsx` missing import) — **P0**.
2. 6 of 14 pages missing entire component directories — **P0**.
3. Two reviewer-response tables (R1.4, R2.1) cite data not present in the repo — **P0**.
4. Adaptive-mode context/learning-state rebuilt redundantly per DMFE run — **P1**.
5. XAI explanation generation re-queries the same partner pool per request — **P1**.
6. Two pages have no-debounce search inputs (latent until P0-2 is fixed) — **P1**.
7. Several backend list/config endpoints do more DB work than needed — **P2**.
8. 9 confirmed-dead files + 2 duplicates + 1 legacy file across backend/frontend — **P2**.
9. Auth, dashboard/analytics, and notifications have no automated backend tests; frontend has none at all — **P2/testing gap**.

## 13. Cleanup candidates

See `FINAL_CLEANUP_RECOMMENDATIONS.md` for the full file-by-file classification (116 files checked: 103 ACTIVE, 9 CONFIRMED DEAD, 2 DUPLICATE, 1 LEGACY, 1 PROBABLY DEAD, 0 UNCERTAIN). Nothing has been deleted, moved, or archived as part of this task.

## 14. Optimization priorities

See `OPTIMIZATION_ROADMAP.md` for the full P0–P3 ranked backlog with Problem/Location/Evidence/Suggested change/Expected benefit/Risk/Testing-required for every item.

## 15. Research limitations (verbatim — do not strengthen these)

- **R1.1:** synthetic robustness sweep.
- **R1.3:** pairing sub-problem only.
- **R1.5:** simulation, not human study.
- **R2.1:** max_allowed_delay_min configuration sweep.
- **R1.4:** (no fixed verbatim wording was specified for this point) — a post-hoc per-service-type re-aggregation of an existing pipeline metric (batching rate/dispatch outcome), not an independent new experiment or a claim about service-differentiated scoring logic; as-shipped it reflects one deterministic N=60 workload, not the multi-workload sweep the current script is written to produce (see Section 9).

These characterizations came directly from the user's own task specification and/or the evaluation scripts' own documented `limitations` fields (verified in `REVIEWER_AUDIT.md`) and must be preserved verbatim in any future paper/report text — do not let a future AI pass "strengthen" them into a more impressive-sounding claim than the evidence supports.

## 16. Protected core areas — do not modify without explicit, scoped approval

```
backend/app/dmfe/compatibility.py
backend/app/dmfe/scoring.py
backend/app/dmfe/score_engine.py
backend/app/dmfe/decision_engine.py
backend/app/dmfe/optimizer.py
backend/app/dmfe/driver_selection.py
backend/app/dmfe/pipeline.py
backend/app/dmfe/batch_generator.py
backend/app/dmfe/serializers.py
backend/app/dmfe/models.py
backend/app/dmfe/adaptive/*.py
backend/app/db/models.py        (schema)
backend/app/core/security.py    (auth)
```
Frontend/UI changes, and narrowly-scoped backend config/schema-exposure additions that don't touch the above (the pattern already used successfully earlier in this project to add `trip_cost_inr`/`separate_cost_inr`/`solo_profit_inr` as new read-only fields), are the intended surface for future work — but even those should be asked about first unless already explicitly approved for that category of change.

---

## RULES FOR FUTURE AI WORK

1. Inspect before modifying.
2. Preserve working behavior.
3. Never fabricate.
4. Do not modify research logic merely to improve metrics.
5. Keep experiments separate from production.
6. Make minimal changes.
7. Run regression tests after changes.
8. Preserve reproducibility.
9. Never delete uncertain files automatically.
10. Verify frontend/backend integration before claiming success.
