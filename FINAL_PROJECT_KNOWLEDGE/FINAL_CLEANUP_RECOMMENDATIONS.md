# Final Cleanup Recommendations

Read-only evidence-based dead-code / cleanup audit of A-DMFE (backend + frontend).
Method: real `grep` tracing of imports/routes/dynamic references across
`backend/app`, `backend/tests`, `backend/scripts`, `backend/evaluation`,
`backend/migrations`, `frontend/src`, and the repo's own docs/README as
corroborating (not sole) evidence. No files were modified, moved, or deleted.

## Summary

**Total files classified: 116**

| Classification | Count |
|---|---|
| ACTIVE | 103 |
| CONFIRMED DEAD | 9 (includes `app/engine/explainability.py`) |
| LEGACY | 1 (`frontend/src/components/map/MapFilters.jsx`; `app/engine/explainability.py` is also discussed under LEGACY as a cross-reference but is counted once, under CONFIRMED DEAD) |
| DUPLICATE | 2 (`frontend/src/components/xai/CompatibilityGauge.jsx`, `frontend/src/components/map/ActivityBar.jsx`) |
| PROBABLY DEAD | 1 (`backend/seed_users.py`) |
| UNCERTAIN | 0 |

Backend files checked (66): `app/engine/*` (4), `app/api/routes/*` (12, via
`main.py` mount check), `scripts/*` (11), `evaluation/*` top-level `.py`
(17), `migrations/*` (1), `seed_users.py` (1), `e2e_test.py` (1, repo root),
`tests/*` (12 — `conftest.py` + 11 `test_*.py` files), plus targeted spot
checks of `app/dmfe/optimizer.py`, `app/main.py`, and DB/migration wiring.

Frontend files checked (57): all 14 files in `pages/`, all 28 components
under `components/**`, `App.jsx`'s own routing wiring, 3 hooks, 6 utils
(incl. `services/api.js`), and `context/AuthContext.jsx`. (`setupTests.js`,
`main.jsx`, `index.css` were out of scope — see "Files NOT Checked".)

---

## Findings

### ACTIVE

**Backend — engine (core distance/optimizer utilities still imported everywhere):**

FILE: backend/app/engine/__init__.py
CLASSIFICATION: ACTIVE
EVIDENCE: Package marker required for `app.engine.*` imports (see below) to resolve. `app.engine.distance` and `app.engine.optimizer` are imported from 12+ call sites across `app/dmfe/*`, `app/api/routes/*`, `app/services/mock_adapters.py`, and `evaluation/*`.
RECOMMENDED ACTION: KEEP

FILE: backend/app/engine/distance.py
CLASSIFICATION: ACTIVE
EVIDENCE: `from app.engine.distance import haversine` found in: `app/api/routes/orchestration.py`, `app/api/routes/dmfe_v2.py`, `app/services/mock_adapters.py`, `app/dmfe/driver_selection.py`, `app/dmfe/decision_engine.py`, `app/dmfe/score_engine.py`, `app/dmfe/optimizer.py`, `app/dmfe/batch_generator.py`, `app/dmfe/compatibility.py`, `app/dmfe/adaptive/context.py`, `app/dmfe/adaptive/matrix.py`, `evaluation/framework.py`, `evaluation/joint_optimization_worker.py`, `evaluation/joint_optimization_baseline.py`. This is the single canonical haversine implementation the whole DMFE pipeline depends on — no duplicate exists elsewhere.
RECOMMENDED ACTION: KEEP

FILE: backend/app/engine/optimizer.py
CLASSIFICATION: **CORRECTED 2026-09-13 — DELETED, entry below is stale.** The file (legacy `AIOrchestrator`) has since been removed and `POST /api/orchestration/optimize` now unconditionally returns HTTP 410 with an explanatory comment (see `docs/reports/FINAL_RELIABILITY_IMPROVEMENT_PLAN.md` §"Five separate internal audit documents assert `app/engine/optimizer.py`/`AIOrchestrator` is still ACTIVE/mounted/KEEP"). The ACTIVE/KEEP finding below predates that deletion and must not be used to justify recreating or "fixing" this file.
~~EVIDENCE (stale, retained for history): `from app.engine.optimizer import AIOrchestrator` in `app/api/routes/orchestration.py:9`. `orchestration.router` is mounted in `main.py:82` (`app.include_router(orchestration.router, prefix="/api/orchestration", ...)`). Distinct from `app/dmfe/optimizer.py` (OR-Tools VRP route optimizer used by DMFE) — the two are different modules serving different route files (`orchestration.py` vs `dmfe_engine.py`/`driver_selection.py`), not duplicates.~~
RECOMMENDED ACTION: ~~KEEP~~ — already deleted; no action needed.

FILE: backend/app/engine/explainability.py
CLASSIFICATION: CONFIRMED DEAD
EVIDENCE: Its only public function `generate_explanation()` has zero call sites anywhere in `backend/app`, `backend/tests`, `backend/scripts`, or `backend/evaluation` — `grep -rn "generate_explanation\|from app.engine.explainability\|engine import explainability"` across the whole repo returns nothing except the definition itself. Functionally superseded: the live XAI explanation pipeline is `app/services/xai_service.py::_generate_explanation_for_request`, which IS imported and tested (`backend/tests/test_xai_static_mode.py`, `backend/tests/test_xai_map_link.py`) and is the function backing the mounted `/api/xai` router. `explainability.py`'s hard-coded `WEIGHTS` dict (route_similarity/delay_impact/capacity_fit/environmental/driver_workload) also does not match the current 5-factor DMFE compatibility scoring model in `app/dmfe/compatibility.py`, confirming it predates the current engine.
RECOMMENDED ACTION: DELETE CANDIDATE — see also "LEGACY" note below; this is functionally superseded by `app/services/xai_service.py`, not merely unreferenced.

*(Full detail on `explainability.py` repeated under LEGACY below since it is both dead-by-reference and clearly superseded.)*

**Backend — API routes (all 12 route modules are mounted in `main.py`):**

FILE: backend/app/api/routes/auth.py
CLASSIFICATION: ACTIVE
EVIDENCE: `app.include_router(auth.router, prefix="/api/auth", ...)` in `main.py:79`.
RECOMMENDED ACTION: KEEP

FILE: backend/app/api/routes/providers.py
CLASSIFICATION: ACTIVE
EVIDENCE: `app.include_router(providers.router, prefix="/api/providers", ...)` in `main.py:80`.
RECOMMENDED ACTION: KEEP

FILE: backend/app/api/routes/dashboard.py
CLASSIFICATION: ACTIVE
EVIDENCE: `app.include_router(dashboard.router, prefix="/api/dashboard", ...)` in `main.py:81`.
RECOMMENDED ACTION: KEEP

FILE: backend/app/api/routes/orchestration.py
CLASSIFICATION: ACTIVE
EVIDENCE: `app.include_router(orchestration.router, prefix="/api/orchestration", ...)` in `main.py:82`.
RECOMMENDED ACTION: KEEP

FILE: backend/app/api/routes/simulation.py
CLASSIFICATION: ACTIVE
EVIDENCE: `app.include_router(simulation.router, prefix="/api/simulation", ...)` in `main.py:83`.
RECOMMENDED ACTION: KEEP

FILE: backend/app/api/routes/xai.py
CLASSIFICATION: ACTIVE
EVIDENCE: `app.include_router(xai.router, prefix="/api/xai", ...)` in `main.py:84`.
RECOMMENDED ACTION: KEEP

FILE: backend/app/api/routes/notifications.py
CLASSIFICATION: ACTIVE
EVIDENCE: `app.include_router(notifications.router, prefix="/api/notifications", ...)` in `main.py:85`.
RECOMMENDED ACTION: KEEP

FILE: backend/app/api/routes/drivers.py
CLASSIFICATION: ACTIVE
EVIDENCE: `app.include_router(drivers.router, ...)` in `main.py:86`.
RECOMMENDED ACTION: KEEP

FILE: backend/app/api/routes/config.py
CLASSIFICATION: ACTIVE
EVIDENCE: `app.include_router(config.router, ...)` in `main.py:87`. Distinct from `app/core/config.py` (pydantic `Settings`) — `routes/config.py` imports `app.schemas.config` and `app.services.config_service`, `core/config.py` imports `pydantic_settings`; same name, different purpose, not a duplicate.
RECOMMENDED ACTION: KEEP

FILE: backend/app/api/routes/playback.py
CLASSIFICATION: ACTIVE
EVIDENCE: `app.include_router(playback.router, ...)` in `main.py:88`.
RECOMMENDED ACTION: KEEP

FILE: backend/app/api/routes/dmfe_v2.py
CLASSIFICATION: ACTIVE
EVIDENCE: `app.include_router(dmfe_v2.router, ...)` in `main.py:89`. Docstrings in both this file and `dmfe_engine.py` explicitly state the two are additive/complementary (`dmfe_v2` = analyze/batches/history/statistics; `dmfe_engine` = full pipeline/queue/trips/assignments) — not duplicates of each other.
RECOMMENDED ACTION: KEEP

FILE: backend/app/api/routes/dmfe_engine.py
CLASSIFICATION: ACTIVE
EVIDENCE: `app.include_router(dmfe_engine.router, ...)` in `main.py:90`. Imports `route_optimizer` from `app.dmfe.optimizer` and `app.dmfe.pipeline` (also used by `app/services/simulation_service.py`, `backend/tests/test_qa_controlled.py`, `backend/tests/test_pipeline_accounting.py`, `backend/scripts/verify_all.py`, `backend/evaluation/framework.py`, `backend/evaluation/verify_admfe.py`).
RECOMMENDED ACTION: KEEP

**Backend — scripts (documented manual entry points, actively run):**

FILE: backend/scripts/run_dev.sh
CLASSIFICATION: ACTIVE
EVIDENCE: Standard dev-boot wrapper around `uvicorn app.main:app`; referenced as the intended dev launcher in its own header comment and the natural counterpart to `render.yaml`/`Procfile`'s `uvicorn app.main:app` start command.
RECOMMENDED ACTION: KEEP

FILE: backend/scripts/run_qa.sh
CLASSIFICATION: ACTIVE
EVIDENCE: Launches the backend against an isolated QA DB (`qa_test.db`); `backend/tests/test_qa_controlled.py` exists specifically to exercise this QA-DB path, corroborating the script is a real part of the QA workflow.
RECOMMENDED ACTION: KEEP

FILE: backend/scripts/check_results_consistency.py
CLASSIFICATION: ACTIVE
EVIDENCE: `docs/METRIC_DEFINITIONS.md:87` — `python scripts/check_results_consistency.py     # must exit 0`, with accompanying description of the four invariants it enforces at `docs/METRIC_DEFINITIONS.md:90`.
RECOMMENDED ACTION: KEEP

FILE: backend/scripts/verify_all.py
CLASSIFICATION: ACTIVE
EVIDENCE: `docs/reports/FINAL_CLEANUP_REPORT.md:39` documents it as a 24-check manual verification suite with a recorded PASS result (`24/24`), run as part of the project's own verification process. Also imports `app.dmfe.pipeline` (a live module).
RECOMMENDED ACTION: KEEP

FILE: backend/scripts/verify_demo.py
CLASSIFICATION: ACTIVE
EVIDENCE: `docs/reports/FINAL_CLEANUP_REPORT.md:42` records `verify_demo.py | PASS | PASS`. Also referenced by name in a comment in `app/api/routes/dmfe_v2.py:266`.
RECOMMENDED ACTION: KEEP

FILE: backend/scripts/verify_xai_map.py
CLASSIFICATION: ACTIVE
EVIDENCE: `docs/reports/FINAL_CLEANUP_REPORT.md:43` records `verify_xai_map.py | PASS | PASS` as part of the documented manual verification run.
RECOMMENDED ACTION: KEEP

**Backend — evaluation (research/experiment entry points, all run manually and documented):**

FILE: backend/evaluation/framework.py
CLASSIFICATION: ACTIVE
EVIDENCE: `evaluation/verify_unified_scoring.py:9` does `import framework`. Also described as "Evaluation framework" in `evaluation/ADMFE_EXPERIMENT_REPORT.md:249` and cited in `docs/PROJECT_FILE_CODE_AUDIT.md:32`.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/run_admfe_experiments.py
CLASSIFICATION: ACTIVE
EVIDENCE: Documented run command in `docs/METRIC_DEFINITIONS.md:84` and `docs/11_ADMFE_Experimental_Evaluation.md:53`; also referenced inside `evaluation/make_admfe_report.py:603` as the companion runner to invoke first.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/make_admfe_report.py
CLASSIFICATION: ACTIVE
EVIDENCE: Documented run command `python evaluation/make_admfe_report.py` in `docs/METRIC_DEFINITIONS.md:85`; described as "Report generator" in `evaluation/ADMFE_EXPERIMENT_REPORT.md:251`.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/verify_admfe.py
CLASSIFICATION: ACTIVE
EVIDENCE: Described as "Verification suite" in `evaluation/ADMFE_EXPERIMENT_REPORT.md:250`; also imported by `backend/app/api/routes/dmfe_engine.py`'s sibling test coverage path (`backend/tests/test_pipeline_accounting.py` exercises the same pipeline it verifies) and listed in `docs/11_ADMFE_Experimental_Evaluation.md:53`.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/final_validation.py
CLASSIFICATION: ACTIVE
EVIDENCE: Documented run command `python evaluation/final_validation.py` in `docs/METRIC_DEFINITIONS.md:86`.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/verify_unified_scoring.py
CLASSIFICATION: ACTIVE
EVIDENCE: Recorded result `unified scoring | evaluation/verify_unified_scoring.py | unified_validation.json regenerated, exit=0` in `docs/reports/BACKEND_WORKING_PERCENTAGE.md:36`; itself imports `framework` (evidence above).
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/acceptance_r15.py
CLASSIFICATION: ACTIVE
EVIDENCE: `evaluation/DEBUG_REPORT.md:23` — `evaluation/acceptance_r15.py | R1.5 | ✅ compiled + ran, simulation`.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/exact_matching_baseline.py
CLASSIFICATION: ACTIVE
EVIDENCE: `evaluation/DEBUG_REPORT.md:20` — `evaluation/exact_matching_baseline.py | R1.3 | ✅ compiled + ran, stdlib-only`.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/per_service_breakdown.py
CLASSIFICATION: ACTIVE
EVIDENCE: `evaluation/DEBUG_REPORT.md:19` — `evaluation/per_service_breakdown.py | R1.4 | ✅ compiled + ran, reconciled`.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/robustness_r11.py
CLASSIFICATION: ACTIVE
EVIDENCE: `evaluation/DEBUG_REPORT.md:21` and `docs/reports/FINAL_PROJECT_AUDIT.md:31` — cited as the R1.1 pairwise-compatibility robustness check with recorded results.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/time_window_sensitivity_r21.py
CLASSIFICATION: ACTIVE
EVIDENCE: `evaluation/DEBUG_REPORT.md:22` — `evaluation/time_window_sensitivity_r21.py | R2.1 | ✅ compiled + ran, knob verified`.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/joint_optimization_baseline.py
CLASSIFICATION: ACTIVE
EVIDENCE: Invokes `evaluation/joint_optimization_worker.py` as a subprocess at runtime (`joint_optimization_baseline.py:127-173`, `worker = os.path.join(EVAL_DIR, "joint_optimization_worker.py")` then `subprocess.run([_py, worker, ...])`) — a real dynamic reference, not a static import.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/joint_optimization_worker.py
CLASSIFICATION: ACTIVE
EVIDENCE: Confirmed as the subprocess target launched by `joint_optimization_baseline.py` (see above) to run an isolated, wall-clock-bounded OR-Tools solve. Not imported anywhere as a Python module — it is designed to run as a standalone worker process, which is the expected shape for this pattern.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/analyze_unified.py
CLASSIFICATION: ACTIVE
EVIDENCE: `docs/Reproducibility_Guide.md` mentions `analyze_unified.py` was modified alongside other evaluation scripts as part of an R3/R4 correction pass, indicating it is part of the maintained evaluation toolchain; also reads `evaluation/results/unified_validation.json`, the output file produced by `verify_unified_scoring.py` (ACTIVE, above) — a real data-flow link.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/benchmark_scalability.py
CLASSIFICATION: ACTIVE
EVIDENCE: Listed in `docs/METRIC_DEFINITIONS.md` and `docs/13_Final_Freeze_Report.md` as part of the evaluation suite; its own header documents it as a read-only scalability benchmark against `backend/` at 100/150/250-request workloads.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/phase8_validation.py
CLASSIFICATION: ACTIVE
EVIDENCE: `docs/METRIC_DEFINITIONS.md:80` — `| 3 | phase8_validation | learning_validation.md, xai_validation.md |` — documented as producing named validation artifacts.
RECOMMENDED ACTION: KEEP

FILE: backend/evaluation/run_feedforward.py
CLASSIFICATION: ACTIVE
EVIDENCE: Referenced in `docs/METRIC_DEFINITIONS.md` and `docs/13_Final_Freeze_Report.md`; header identifies it as "Phase 4.1 — Step 5: Feed-forward verification," a documented, deliberately-run controlled experiment (not an ad hoc debug script).
RECOMMENDED ACTION: KEEP

**Backend — migrations, seed, e2e:**

FILE: backend/migrations/001_dmfe_batch_predicted_utilization.py
CLASSIFICATION: ACTIVE
EVIDENCE: The file's own docstring documents it as a deliberate, still-needed manual/CI migration path: "the ORM model change plus `sync_schema_columns()` at startup already migrates SQLite dev DBs, so this script exists for manual/CI migration of existing environments" (i.e., PostgreSQL prod DBs, which `main.py`'s `sync_schema_columns()` explicitly does NOT cover — see `main.py:15`, "idempotent legacy dev-DB column sync (SQLite only)"). Listed in the project tree in `docs/PROJECT_FILE_CODE_AUDIT.md` and `docs/reports/BACKEND_WORKING_PERCENTAGE.md`.
RECOMMENDED ACTION: KEEP

FILE: e2e_test.py (repo root, not backend/e2e_test.py)
CLASSIFICATION: ACTIVE
EVIDENCE: Confirmed location is `/mnt/user-data/uploads/rapidoproject/e2e_test.py` (repo root), not under `backend/`. Documented in `README.md:154` — "API smoke test: Run `python e2e_test.py` from the repo root" — and its PASS result is recorded in `docs/FINAL_PROJECT_VERIFICATION_REPORT.md:29-34`.
RECOMMENDED ACTION: KEEP (note: path differs from the task's assumed `backend/e2e_test.py` — it actually lives at repo root)

**Backend — tests (all follow `test_*.py` pytest discovery convention; `backend/pytest.ini` sets `testpaths = tests`, so every file directly in `backend/tests/` is collected and run regardless of whether anything imports it):**

FILE: backend/tests/conftest.py
CLASSIFICATION: ACTIVE
EVIDENCE: Standard pytest fixture file, auto-loaded by pytest for every test in `backend/tests/` per `testpaths = tests` in `backend/pytest.ini`.
RECOMMENDED ACTION: KEEP

FILE: backend/tests/test_compatibility.py, test_datasets_upload.py, test_driver_selection.py, test_learning_engine.py, test_learning_phase4.py, test_learning_phase4_1.py, test_pipeline_accounting.py, test_qa_controlled.py, test_scoring_unified.py, test_xai_map_link.py, test_xai_static_mode.py
CLASSIFICATION: ACTIVE
EVIDENCE: All match pytest's `test_*.py` discovery pattern and sit directly under `backend/tests/`, the directory named in `backend/pytest.ini`'s `testpaths = tests`. `docs/reports/FINAL_CLEANUP_REPORT.md:38` records `pytest | 73 / 0 fail` confirming the suite is actually executed. Tests are entry points, not import targets — absence of cross-references does not indicate dead code here.
RECOMMENDED ACTION: KEEP

---

### CONFIRMED DEAD

FILE: backend/app/engine/explainability.py
CLASSIFICATION: CONFIRMED DEAD
EVIDENCE: No references found via grep for `generate_explanation` / `from app.engine.explainability` / `engine import explainability` across `backend/app`, `backend/tests`, `backend/scripts`, `backend/evaluation`. See also LEGACY note: functionally superseded by `app/services/xai_service.py::_generate_explanation_for_request`.
RECOMMENDED ACTION: DELETE CANDIDATE

FILE: backend/scripts/api_test.py
CLASSIFICATION: CONFIRMED DEAD
EVIDENCE: No references found via grep for `api_test` across the repo (code or docs). File's own docstring: "Comprehensive API test — correct endpoint paths based on actual router definitions" — a one-off manual script hitting `http://localhost:8000` directly with `httpx`, not registered with pytest (not under `backend/tests/`, not matching `testpaths`), not referenced by `run_dev.sh`/`run_qa.sh`, not mentioned in any doc.
RECOMMENDED ACTION: ARCHIVE

FILE: backend/scripts/check_status.py
CLASSIFICATION: CONFIRMED DEAD
EVIDENCE: No references found via grep for `check_status` across the repo (code or docs). Docstring: "Step 1 verification: DB status distributions and stale trip check" — a one-off ad hoc DB inspection script tied to a specific debugging session ("Step 1"), not wired into any run/test/deploy path.
RECOMMENDED ACTION: ARCHIVE

FILE: backend/scripts/debug_stale.py
CLASSIFICATION: CONFIRMED DEAD
EVIDENCE: No references found via grep for `debug_stale` across the repo. Docstring: "Debug: check what complete_stale_trips sees when called directly" — explicitly a throwaway debug script.
RECOMMENDED ACTION: ARCHIVE

FILE: backend/scripts/test_stale_release.py
CLASSIFICATION: CONFIRMED DEAD
EVIDENCE: Named `test_*.py` but lives in `backend/scripts/`, not `backend/tests/`, and `backend/pytest.ini` sets `testpaths = tests` — pytest run from `backend/` will NOT discover this file (confirmed by reading `pytest.ini`; testpaths restricts collection to the `tests` directory only). No other references found via grep for `test_stale_release` across the repo. Docstring: "Step 3.6 definitive test: in-process stale trip auto-release via run_analysis()" — a one-off manual verification tied to a specific historical debugging step, not a live test.
RECOMMENDED ACTION: ARCHIVE

FILE: backend/scripts/verify_fix.py
CLASSIFICATION: CONFIRMED DEAD
EVIDENCE: No references found via grep for `verify_fix` across the repo (code or docs) — notably absent from the verification results table in `docs/reports/FINAL_CLEANUP_REPORT.md` that DOES list `verify_all.py`, `verify_admfe.py`, `verify_unified_scoring.py`, `verify_demo.py`, and `verify_xai_map.py` by name. Docstring: "Step 3 verification script -- exercises the DMFE engine via API and direct DB. Covers Step 3 items #3 through #6" — a one-off script for a specific historical step, superseded by the currently-documented verify_* scripts.
RECOMMENDED ACTION: ARCHIVE

FILE: frontend/src/components/ui/AnimatedNumber.jsx
CLASSIFICATION: CONFIRMED DEAD
EVIDENCE: No references found via grep for `AnimatedNumber` anywhere in `frontend/src` other than its own definition (`export default function AnimatedNumber(...)`). No page or component imports it.
RECOMMENDED ACTION: DELETE CANDIDATE

FILE: frontend/src/components/xai/ScoreBreakdown.jsx
CLASSIFICATION: CONFIRMED DEAD
EVIDENCE: No references found via grep for `ScoreBreakdown` (the xai one) anywhere in `frontend/src` other than its own file. Its natural consumer, `frontend/src/components/xai/XaiDecisionPanel.jsx`, does not import it (checked its full import list) — that panel appears to render its own inline breakdown instead. Distinct from `frontend/src/components/dmfe/FactorBreakdown.jsx`, which IS actively imported.
RECOMMENDED ACTION: DELETE CANDIDATE

FILE: frontend/src/components/xai/ExplanationFilters.jsx
CLASSIFICATION: CONFIRMED DEAD
EVIDENCE: No references found via grep for `ExplanationFilters` anywhere in `frontend/src` other than its own file. Its natural consumer, `frontend/src/pages/ExplanationDashboard.jsx`, does not import it (checked its full import list — imports `DecisionCard`, `XaiMapPanel`, `XaiDecisionPanel`, `xaiMap` util, `PageHeader`, `StatusBadge`, but not `ExplanationFilters`).
RECOMMENDED ACTION: DELETE CANDIDATE

---

### LEGACY

FILE: backend/app/engine/explainability.py
CLASSIFICATION: LEGACY
EVIDENCE: Same file as the CONFIRMED DEAD entry above — listed again under LEGACY because the evidence supports both angles: it is (a) zero-reference dead code, and (b) a superseded predecessor implementation. Its hard-coded `WEIGHTS` (route_similarity 0.30 / delay_impact 0.25 / capacity_fit 0.15 / environmental 0.20 / driver_workload 0.10) reflect an older, simpler explanation model than the current 5-factor Compatibility Score system in `app/dmfe/compatibility.py` and the live `app/services/xai_service.py::_generate_explanation_for_request`, which is what the mounted `/api/xai` router (`app/api/routes/xai.py`, active) and both XAI tests (`test_xai_static_mode.py`, `test_xai_map_link.py`) actually exercise.
RECOMMENDED ACTION: DELETE CANDIDATE (treat the two entries above as one file, one recommendation)

---

### DUPLICATE

FILE: frontend/src/components/xai/CompatibilityGauge.jsx
CLASSIFICATION: DUPLICATE (of frontend/src/components/dmfe/CompatibilityGauge.jsx)
EVIDENCE: Two components share the exact name `CompatibilityGauge` in different folders. Explicit grep for import statements (`from.*CompatibilityGauge`) across `frontend/src` finds exactly one real import: `frontend/src/components/dmfe/CandidateBatchCard.jsx:3` — `import CompatibilityGauge from './CompatibilityGauge';` — a relative import that resolves only to the `dmfe/` copy. No file imports `components/xai/CompatibilityGauge.jsx` (its own `export default function CompatibilityGauge({ score = 89.5, confidence = 92 })` is the only occurrence of its identifier in any xai-folder consumer). The `dmfe/` version (`export default function CompatibilityGauge({ score = 0, size = 120 })`) is the one actually rendered in `CandidateBatchCard.jsx:67`.
RECOMMENDED ACTION: DELETE CANDIDATE (remove `components/xai/CompatibilityGauge.jsx`; keep `components/dmfe/CompatibilityGauge.jsx`)

FILE: frontend/src/components/map/ActivityBar.jsx
CLASSIFICATION: DUPLICATE (functionally superseded by frontend/src/components/map/KpiBar.jsx)
EVIDENCE: No references found via grep for `ActivityBar` anywhere in `frontend/src` other than its own file. `KpiBar.jsx`'s own doc comment (lines 4-13) explicitly describes the history: "the previous version of this bar also carried a live-count badge per request type ... plus a clock, which read as cluttered next to the map. Those counts are still computed by the page ... they are just no longer duplicated here as a row of badges." This describes exactly the kind of live per-type activity display `ActivityBar.jsx` implements (it renders `queue` items with `requestTypeMeta` from `utils/requestSemantics`). `KpiBar.jsx` IS actively imported (`frontend/src/pages/LiveSimulationMap.jsx`, `frontend/src/components/xai/XaiMapPanel.jsx`), while `ActivityBar.jsx` has zero importers.
RECOMMENDED ACTION: DELETE CANDIDATE

---

### PROBABLY DEAD

FILE: backend/seed_users.py
CLASSIFICATION: PROBABLY DEAD
EVIDENCE: No references found via grep for `seed_users` anywhere in the repo — not in any doc, README, script, or CI config, and unlike `e2e_test.py` (documented in `README.md:154`) or the `verify_*.py` scripts (documented in `docs/reports/FINAL_CLEANUP_REPORT.md`), it has no corroborating mention anywhere. It is a small standalone manual utility (`sys.path.append('backend'); ... creates Customer/Driver test users`) that a developer could still run ad hoc (`python seed_users.py` from repo root, given its `sys.path.append('backend')`), so it is not provably unreachable the way the `scripts/*` debug files above are — hence PROBABLY DEAD rather than CONFIRMED DEAD.
RECOMMENDED ACTION: UNCERTAIN — ask the team whether this manual seeding step is still part of anyone's workflow before archiving.

---

### ACTIVE — remaining frontend pages, components, hooks, utils, context

All of the following were checked via the same method (grep for the component/hook/util identifier as an import target across `frontend/src`) and have at least one confirmed real importer. Grouped here for brevity since each has a single clear evidence line; none showed ambiguity.

**Pages** — each is `lazy(() => import('./pages/<Name>'))`'d in `frontend/src/App.jsx` (lines 9-22) AND wired to a `<Route>` in the router (lines 55-70):

FILE: frontend/src/pages/Login.jsx, AnalyticsDashboard.jsx, DMFEDashboard.jsx, Dashboard.jsx, DatasetManagement.jsx, DriverDashboard.jsx, ExplanationDashboard.jsx, LiveSimulationMap.jsx, NotificationCenter.jsx, ProviderManagement.jsx, ScenarioDashboard.jsx, SimulationMonitoring.jsx, SystemConfiguration.jsx, AIDashboard.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: Each has a matching `const X = lazy(() => import('./pages/X'))` line and a corresponding `<Route path="..." element={<X />} />` in `frontend/src/App.jsx` (e.g. `AIDashboard` → line 22 lazy import, line 70 route `ai-orchestration`; `DMFEDashboard` → line 17 / line 65 route `dmfe`, etc.). All 14 top-level pages are reachable from the router.
RECOMMENDED ACTION: KEEP

**Components / context / hooks / utils** — each confirmed by at least one real `import ... from '...'` line found via grep:

FILE: frontend/src/components/AdminLayout.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: `frontend/src/App.jsx:5` — `import AdminLayout from './components/AdminLayout';`, used as the layout element wrapping all authenticated routes (`App.jsx:56`).
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/ProtectedRoute.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: `frontend/src/App.jsx:6` — `import ProtectedRoute from './components/ProtectedRoute';`, wraps `AdminLayout` at `App.jsx:56`.
RECOMMENDED ACTION: KEEP

FILE: frontend/src/context/AuthContext.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: Imported by `frontend/src/App.jsx:4` (`AuthProvider`), `frontend/src/components/AdminLayout.jsx:3` and `frontend/src/components/ProtectedRoute.jsx:3` (`AuthContext`).
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/analytics/KPICards.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: `frontend/src/pages/AnalyticsDashboard.jsx:5` — `import KPICards from '../components/analytics/KPICards';`
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/analytics/TimeAnalytics.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: `frontend/src/pages/AnalyticsDashboard.jsx:9` — `import TimeAnalytics from '../components/analytics/TimeAnalytics';`
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/dmfe/BatchesPanel.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: `frontend/src/pages/DMFEDashboard.jsx:10` — `import BatchesPanel from '../components/dmfe/BatchesPanel';`
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/dmfe/CandidateBatchCard.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: `frontend/src/components/dmfe/BatchesPanel.jsx:3` — `import CandidateBatchCard from './CandidateBatchCard';`
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/dmfe/CompatibilityGauge.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: `frontend/src/components/dmfe/CandidateBatchCard.jsx:3` — `import CompatibilityGauge from './CompatibilityGauge';`, rendered at `CandidateBatchCard.jsx:67`. This is the surviving copy — see DUPLICATE entry for `components/xai/CompatibilityGauge.jsx` below.
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/dmfe/FactorBreakdown.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: `frontend/src/components/dmfe/CandidateBatchCard.jsx:4` — `import FactorBreakdown from './FactorBreakdown';`
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/map/LiveMapContainer.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: Imported by `frontend/src/components/xai/XaiMapPanel.jsx:4`, `frontend/src/pages/Dashboard.jsx:8`, and `frontend/src/pages/LiveSimulationMap.jsx:7`.
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/map/ActiveTripsLayer.jsx, FleetLayer.jsx, MapControls.jsx, RequestMarkers.jsx, XAIHighlightLayer.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: All imported directly by `frontend/src/components/map/LiveMapContainer.jsx` (lines 5, 7, 8, 9, 10 respectively — `import RequestMarkers from './RequestMarkers'`, `import MapControls from './MapControls'`, `import XAIHighlightLayer from './XAIHighlightLayer'`, `import FleetLayer from './FleetLayer'`, `import ActiveTripsLayer from './ActiveTripsLayer'`), which is itself ACTIVE (above).
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/map/MarkerPopup.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: Imported by `frontend/src/components/map/RequestMarkers.jsx:3` and `frontend/src/components/map/LiveMapContainer.jsx:6`.
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/map/MapFilterPanel.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: Confirmed imported by `frontend/src/pages/LiveSimulationMap.jsx` (found alongside `KpiBar` in the grep pass for both identifiers).
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/map/KpiBar.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: Imported by `frontend/src/pages/LiveSimulationMap.jsx` and `frontend/src/components/xai/XaiMapPanel.jsx` (confirmed via `grep -rln "KpiBar"`).
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/map/TripDetailsPanel.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: `frontend/src/pages/LiveSimulationMap.jsx:10` — `import TripDetailsPanel from '../components/map/TripDetailsPanel';`
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/map/markerIcons.js
CLASSIFICATION: ACTIVE
EVIDENCE: Imported by `frontend/src/components/map/XAIHighlightLayer.jsx:22`, `frontend/src/components/map/RequestMarkers.jsx:5`, and `frontend/src/components/map/FleetLayer.jsx:8`.
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/notifications/ActivityTimeline.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: `frontend/src/pages/NotificationCenter.jsx:9` — `import ActivityTimeline from '../components/notifications/ActivityTimeline';`
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/playback/SavedSimulationsTable.jsx, ScenarioComparison.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: Both imported by `frontend/src/pages/ScenarioDashboard.jsx` (lines 8 and 10).
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/ui/StatusBadge.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: Imported by at least `NotificationCenter.jsx`, `AnalyticsDashboard.jsx`, `ExplanationDashboard.jsx`, and `DriverDashboard.jsx`.
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/ui/PageHeader.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: Imported by 11 page files including `NotificationCenter.jsx`, `AIDashboard.jsx`, `ScenarioDashboard.jsx`, `DatasetManagement.jsx`, `AnalyticsDashboard.jsx`, `SimulationMonitoring.jsx`, `ExplanationDashboard.jsx`, `ProviderManagement.jsx`, `SystemConfiguration.jsx`, `DriverDashboard.jsx`, `DMFEDashboard.jsx`.
RECOMMENDED ACTION: KEEP

FILE: frontend/src/components/xai/DecisionCard.jsx, XaiDecisionPanel.jsx, XaiMapPanel.jsx
CLASSIFICATION: ACTIVE
EVIDENCE: All three imported by `frontend/src/pages/ExplanationDashboard.jsx` (lines 11, 13, 12 respectively).
RECOMMENDED ACTION: KEEP

FILE: frontend/src/hooks/useOperationalNetwork.js
CLASSIFICATION: ACTIVE
EVIDENCE: Imported by `frontend/src/pages/Dashboard.jsx:9` and `frontend/src/pages/LiveSimulationMap.jsx:12`.
RECOMMENDED ACTION: KEEP

FILE: frontend/src/hooks/useOperationalRoute.js, useSeparateRoutes.js
CLASSIFICATION: ACTIVE
EVIDENCE: Both imported by `frontend/src/components/map/XAIHighlightLayer.jsx` (lines 13-14); `useSeparateRoutes.js` also itself imports `useOperationalRoute` internally.
RECOMMENDED ACTION: KEEP

FILE: frontend/src/services/api.js
CLASSIFICATION: ACTIVE
EVIDENCE: Imported by numerous files including `frontend/src/components/AdminLayout.jsx:10` and `frontend/src/components/xai/XaiMapPanel.jsx:3`, plus every page that makes API calls (confirmed present across the pages/ directory during the audit).
RECOMMENDED ACTION: KEEP

FILE: frontend/src/utils/coimbatore.js
CLASSIFICATION: ACTIVE
EVIDENCE: `frontend/src/components/map/LiveMapContainer.jsx:15` — `import { COIMBATORE_CENTER } from '../../utils/coimbatore';`
RECOMMENDED ACTION: KEEP

FILE: frontend/src/utils/operationalRoute.js
CLASSIFICATION: ACTIVE
EVIDENCE: Imported by `components/xai/XaiDecisionPanel.jsx`, `components/map/XAIHighlightLayer.jsx`, `components/map/TripDetailsPanel.jsx`, `components/map/ActiveTripsLayer.jsx`, `hooks/useOperationalRoute.js`, `hooks/useSeparateRoutes.js`.
RECOMMENDED ACTION: KEEP

FILE: frontend/src/utils/requestSemantics.js
CLASSIFICATION: ACTIVE
EVIDENCE: Imported by `components/xai/DecisionCard.jsx:2`, `components/xai/XaiMapPanel.jsx:6`, `components/xai/XaiDecisionPanel.jsx:11`, plus `components/map/XAIHighlightLayer.jsx`, `TripDetailsPanel.jsx`, `markerIcons.js`, `RequestMarkers.jsx`, `ActiveTripsLayer.jsx`, `MarkerPopup.jsx`, `FleetLayer.jsx`, `ActivityBar.jsx` (dead component still referencing it — does not affect this file's own active status since 10+ other live components also import it), `LiveMapContainer.jsx`, and `pages/Dashboard.jsx`.
RECOMMENDED ACTION: KEEP

FILE: frontend/src/utils/routeUtils.js
CLASSIFICATION: ACTIVE
EVIDENCE: Imported by `components/map/XAIHighlightLayer.jsx`, `components/map/ActiveTripsLayer.jsx`, `hooks/useOperationalRoute.js`, `hooks/useSeparateRoutes.js`.
RECOMMENDED ACTION: KEEP

FILE: frontend/src/utils/xaiMap.js
CLASSIFICATION: ACTIVE
EVIDENCE: Imported by `components/xai/XaiMapPanel.jsx`, `pages/ExplanationDashboard.jsx:14`, `pages/LiveSimulationMap.jsx`.
RECOMMENDED ACTION: KEEP

---

### LEGACY (continued)

FILE: frontend/src/components/map/MapFilters.jsx
CLASSIFICATION: LEGACY
EVIDENCE: No references found via grep for `MapFilters` (as an import) anywhere in `frontend/src`. `frontend/src/components/map/MapFilterPanel.jsx`'s doc comment explicitly narrates the supersession: "The ID/provider/address search box that used to live here now sits in the top control bar (KpiBar) instead, so it is not duplicated on screen; this panel keeps the Type/Provider/Priority dropdowns." `MapFilterPanel.jsx` (search moved to `KpiBar.jsx`, dropdowns kept here) together replace what `MapFilters.jsx` (combined search + Type/Provider/Priority dropdowns in one component) used to do. Both `MapFilterPanel.jsx` and `KpiBar.jsx` are confirmed ACTIVE (imported by `LiveSimulationMap.jsx`/`XaiMapPanel.jsx`); `MapFilters.jsx` has zero importers.
RECOMMENDED ACTION: DELETE CANDIDATE

---

## Files NOT Checked

- **`backend/app/dmfe/*.py` and `backend/app/dmfe/adaptive/*.py`** — per task instructions, treated as ACTIVE/KEEP by default and not individually re-verified file-by-file, since they are the core DMFE/A-DMFE engine. (Spot checks were still done incidentally while tracing `app.engine` vs `app.dmfe` references — e.g. confirming `app/dmfe/optimizer.py`, `app/dmfe/pipeline.py`, `app/dmfe/driver_selection.py`, `app/dmfe/compatibility.py`, `app/dmfe/decision_engine.py`, `app/dmfe/score_engine.py`, `app/dmfe/batch_generator.py`, and `app/dmfe/adaptive/context.py` / `matrix.py` all import `app.engine.distance.haversine` and are themselves imported elsewhere — all consistent with ACTIVE.)
- **`backend/app/services/*.py`, `backend/app/schemas/*.py`, `backend/app/db/*.py`, `backend/app/core/*.py`** — not in the task's priority list; a quick naming-pattern sweep (`*_old*`, `*backup*`, `*deprecated*`, `*_v1*`, `*copy*`, `*unused*`) across `backend/app` and `frontend/src` found nothing suspicious, so these were not individually traced.
- **`backend/evaluation/results/`** — explicitly out of scope per task instructions (data/output directory, not scripts).
- **`backend/evaluation/*.md` files** (`ADMFE_EXPERIMENT_REPORT.md`, `DEBUG_REPORT.md`, `README.md`, `REVIEWER_EVIDENCE_REPORT.md`) — used only as corroborating evidence for classifying the `.py` scripts next to them; not classified themselves (they are documentation, not source code in scope).
- **`frontend/src/services/api.js`, `frontend/src/context/AuthContext.jsx`, `frontend/src/setupTests.js`, `frontend/src/main.jsx`, `frontend/src/index.css`** — not individually itemized; `AuthContext.jsx` is imported by `App.jsx` (confirmed ACTIVE), `services/api.js` is imported broadly across pages (confirmed present in multiple import lists during the audit), and `main.jsx`/`setupTests.js`/`index.css` are standard Vite/CRA entry-point files outside the "component/page/util/hook" scope the task asked to prioritize.
- **`frontend/src/components/ui/AnimatedBackground.jsx`** — **not a "not checked" omission, but an anomaly worth flagging separately from the classification scheme**: `frontend/src/App.jsx` imports it (`import AnimatedBackground from './components/ui/AnimatedBackground';`, line 7, used at line 36) and it is also referenced in `docs/reports/OPERATIONS_MAP_REBUILD_REPORT.md:170` ("`AnimatedBackground.jsx` (decorative particles)"), but **no such file exists anywhere in the mirrored `frontend/src` tree** (confirmed via `find frontend -iname "*animatedbackground*"`, which found nothing under `frontend/src`, and via a full-repo grep for the string, which found only the two references above). This is not classifiable as a source file (there is nothing to classify) but is worth surfacing: either the file was deleted without updating `App.jsx`, or it did not make it into this mirror — either way, as mirrored, `App.jsx`'s import would fail to resolve at build time.
