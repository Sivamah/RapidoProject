# Optimization Roadmap

**This is a planning document only. Nothing in this roadmap has been implemented as part of this task.** Every item below is synthesized from the evidence-based findings in `BACKEND_OPTIMIZATION.md`, `FRONTEND_OPTIMIZATION.md`, `FRONTEND_BACKEND_CONNECTION_MATRIX.md`, `REVIEWER_AUDIT.md`, and `FINAL_CLEANUP_RECOMMENDATIONS.md` — see those files for full citations and line numbers. Ranking reflects severity/impact as classified by the underlying audits, not a separate invented score.

---

## P0 — Critical (blocks basic functionality or reviewer-submission integrity)

### P0-1. `App.jsx` imports a component that does not exist — the application does not build/start
- **Problem:** `frontend/src/App.jsx` statically (not lazily) imports `./components/ui/AnimatedBackground`, which does not exist anywhere in the repository.
- **Current location:** `frontend/src/App.jsx:7,36`
- **Evidence:** `FRONTEND_OPTIMIZATION.md`, first CRITICAL finding; corroborated independently by `FINAL_CLEANUP_RECOMMENDATIONS.md`'s "Files NOT Checked" anomaly note and a matching reference in `docs/reports/OPERATIONS_MAP_REBUILD_REPORT.md:170`.
- **Suggested change:** Either restore `AnimatedBackground.jsx` or remove the import/usage from `App.jsx`.
- **Expected benefit:** The application builds and every route becomes reachable again.
- **Risk:** None identified — this is a pure prerequisite for the app to run at all.
- **Testing required:** `npm run build` / `vite build` must succeed; manually load every route once fixed.

### P0-2. Six of fourteen pages import entire component directories that were never committed
- **Problem:** `AnalyticsDashboard.jsx` (5 missing), `DMFEDashboard.jsx` (3 missing), `DriverDashboard.jsx` (whole `components/drivers/`, 6 missing), `SystemConfiguration.jsx` (whole `components/config/`, 7 missing), `NotificationCenter.jsx` (3 missing), `ScenarioDashboard.jsx` (3 missing) all reference components that do not exist.
- **Current location:** see `FRONTEND_OPTIMIZATION.md` CRITICAL findings 2–7 for exact file/line citations.
- **Suggested change:** Rebuild or restore each missing component directory from source control history if available, or scope each page down to only the sub-components that do exist until the rest can be rebuilt.
- **Expected benefit:** Restores the Analytics, Requests (DMFE), Fleet (Drivers), Settings (Config), Activity Center (Notifications), and Reports (Playback/Scenario) surfaces of the product — roughly half the application's navigable surface.
- **Risk:** Rebuilding six component trees is substantial UI work; should be scoped and prioritized by the project owner, not done piecemeal.
- **Testing required:** Manual navigation to each of the 6 routes post-fix; `npm run build` must stay green.

### P0-3. Two of five reviewer-response experiments (R1.4, R2.1) are cited in `REVIEWER_EVIDENCE_REPORT.md` with data that does not exist in the repository
- **Problem:** The committed `per_service_breakdown.py` and `time_window_sensitivity_r21.py` scripts are written to sweep multiple workloads and write `r14_per_service_all.json` / `r21_time_window_all.json`; neither output file exists. `REVIEWER_EVIDENCE_REPORT.md`'s tables for R1.4 (N=50/100/250/500, up to 91.2% batching) and R2.1 (N=50/N=100 sweep) cite numbers that cannot be traced to any artifact in the repo — only single-workload (N=60) results exist under different filenames.
- **Current location:** `backend/evaluation/per_service_breakdown.py`, `backend/evaluation/time_window_sensitivity_r21.py`, `backend/evaluation/REVIEWER_EVIDENCE_REPORT.md`.
- **Evidence:** `REVIEWER_AUDIT.md`, R1.4 and R2.1 sections ("PAPER CLAIM COMPATIBILITY — MISMATCH FOUND").
- **Suggested change:** Either (a) re-run the current multi-workload scripts and commit the resulting `_all.json` files so the report's tables are backed by real data, or (b) rewrite `REVIEWER_EVIDENCE_REPORT.md`'s R1.4/R2.1 sections to describe only the single N=60 evidence that is actually present.
- **Expected benefit:** Removes a reviewer-facing document from citing unverifiable numbers before submission.
- **Risk:** Re-running the sweeps changes the specific figures quoted in the report; a reviewer who already saw a draft with the old numbers would need the discrepancy explained.
- **Testing required:** After re-running, `check_results_consistency.py` (documented in `docs/METRIC_DEFINITIONS.md`) should be run to verify the new result files reconcile.

---

## P1 — High

### P1-1. Adaptive-mode context is built twice per DMFE run
- **Problem/Location/Evidence:** `backend/app/dmfe/decision_engine.py::DecisionEngine.run_analysis` and `backend/app/dmfe/pipeline.py::PipelineRunner.run` each build `ContextAwarenessEngine` once for logging, then `batch_generator.py` builds it again internally — full detail and line numbers in `BACKEND_OPTIMIZATION.md` Finding 1. Runs on every `/api/dmfe/analyze`/`/api/dmfe/run` call **and** every simulation tick that triggers dispatch.
- **Suggested change:** Thread the already-built `context` through to `generate_candidates`/`create_feasible_batches` as an optional parameter.
- **Expected benefit:** Removes ~6 SQL queries + one O(n²) haversine congestion pass per call.
- **Risk:** Low, but must be checked against `test_pipeline_accounting.py`/`test_scoring_unified.py` since persisted `context_profile` fields are dashboard-visible.
- **Testing required:** Existing pipeline/scoring test suite; manual diff of `DMFEAnalysisRun.threshold_used` before/after.

### P1-2. `LearningEngine.load_state()` re-read 3× per adaptive batching call
- **Problem/Location/Evidence:** `backend/app/dmfe/batch_generator.py` — see `BACKEND_OPTIMIZATION.md` Finding 2 for the three call sites and line numbers.
- **Suggested change:** Load state once, pass into `ContextAwarenessEngine.build()` and `AdaptiveWeightGenerator.generate()`.
- **Expected benefit:** 3 redundant `SystemConfig` reads + JSON parses collapsed to 1; compounds with P1-1.
- **Risk:** Low — `load_state()`'s `db.flush()`-then-read semantics must be preserved if caching is added.
- **Testing required:** `test_learning_engine.py`, `test_learning_phase4*.py`.

### P1-3. XAI explanation generation re-queries the same partner pool per request
- **Problem/Location/Evidence:** `backend/app/services/xai_service.py::_generate_explanation_for_request` — see `BACKEND_OPTIMIZATION.md` Finding 3.
- **Suggested change:** Fetch one candidate-partner pool per `get_explanations()` call; filter in memory per request.
- **Expected benefit:** Up to N (≤100) fewer `SimulationRequest` queries per `/api/xai/explanations` cache-miss call.
- **Risk:** Medium — must replicate exact "exclude self, newest 20" semantics to keep explanations byte-identical.
- **Testing required:** `test_xai_static_mode.py`, `test_xai_map_link.py`; before/after diff of explanation output for a fixed dataset.

### P1-4. Search inputs on two pages trigger a full multi-endpoint refetch per keystroke, no debounce
- **Problem/Location/Evidence:** `frontend/src/pages/DriverDashboard.jsx` (7 endpoints/keystroke) and `frontend/src/pages/ScenarioDashboard.jsx` (3 endpoints/keystroke) — see `FRONTEND_OPTIMIZATION.md` HIGH findings 1–2. Currently unreachable in production because both pages fail to render (P0-2), but the defect is independent and will surface immediately once those pages are restored.
- **Suggested change:** Debounce the search input (300–500ms) before it participates in the `fetchData` dependency array.
- **Expected benefit:** Eliminates up to 6× duplicate request bursts for a 6-character search term.
- **Risk:** Low.
- **Testing required:** Manual — type into the search box and confirm request count via browser devtools network tab.

---

## P2 — Medium

### P2-1. Backend read-path inefficiencies (5 findings)
Driver/vehicle/provider full-table scans on every list call (`driver_service.py` — `BACKEND_OPTIMIZATION.md` Finding 4), per-key `SystemConfig` queries in `config_service.update_configs` (Finding 5), per-notification commits inside simulation loops (Finding 6), duplicate `Trip` query in `get_advanced_analytics` (Finding 7), and the deliberately-tradeoffed per-trip commit pattern in `PipelineRunner.run` (Finding 8, flagged as an intentional correctness-vs-throughput choice — see that finding's RISK note before changing it). **Suggested change / benefit / risk:** see each finding's own entry in `BACKEND_OPTIMIZATION.md`. **Testing required:** existing backend test suite (73/0 fail per `docs/reports/FINAL_CLEANUP_REPORT.md`, not independently re-executed by this audit) plus manual verification of unaffected endpoints.

### P2-2. Frontend dead/duplicate components with one live data-integrity risk
`MapFilters.jsx`, `ActivityBar.jsx` (dead, `FRONTEND_OPTIMIZATION.md` MEDIUM), `ExplanationFilters.jsx`, `ScoreBreakdown.jsx`, and — notably — `components/xai/CompatibilityGauge.jsx`, which defaults its props to fabricated-looking numbers (`score = 89.5, confidence = 92`), contradicting this codebase's otherwise-consistent "never fabricate a missing value" convention. **Suggested change:** delete the dead files (see `FINAL_CLEANUP_RECOMMENDATIONS.md` for the full, cross-referenced list including backend equivalents); if `xai/CompatibilityGauge.jsx` is kept for any reason, remove its fabricated defaults first. **Risk:** none — none of these files are imported anywhere. **Testing required:** `npm run build` after removal; grep to reconfirm zero importers.

### P2-3. `NotificationCenter.jsx` carries the same no-debounce fetch pattern as P1-4
Currently masked because its own filter component is among the missing files from P0-2. **Suggested change:** when `NotificationFilters` is rebuilt, debounce its search callback. **Testing required:** manual, post-rebuild.

### P2-4. Fleet list endpoints have no pagination while polled every 2.5s
`DriverDashboard.jsx`'s `/drivers` and `/vehicles` calls carry no `limit` param, unlike every other list-fetching page in the codebase. **Suggested change:** add a `limit`/pagination param matching the convention used elsewhere. **Risk:** low. **Testing required:** manual, post P0-2 rebuild, with a large seeded fleet.

### P2-5. Confirmed dead code (9 files) and 2 duplicates ready for archival
Backend: `app/engine/explainability.py` (superseded by `xai_service.py`), `scripts/api_test.py`, `check_status.py`, `debug_stale.py`, `test_stale_release.py`, `verify_fix.py` (all one-off debugging scripts, none wired into CI/docs). Frontend: `AnimatedNumber.jsx`, `ScoreBreakdown.jsx`, `ExplanationFilters.jsx` (CONFIRMED DEAD), plus `xai/CompatibilityGauge.jsx` and `map/ActivityBar.jsx` (DUPLICATE) and `map/MapFilters.jsx` (LEGACY). Full evidence and recommended action per file in `FINAL_CLEANUP_RECOMMENDATIONS.md`. **Suggested change:** archive (not delete) pending team sign-off, per the standing "never delete anything automatically" rule. **Testing required:** repo-wide grep re-confirmation immediately before any archival action.

### P2-6. R1.1 is missing from `REVIEWER_EVIDENCE_REPORT.md`'s own coverage roll-up
R1.1's script and result are complete and internally consistent, but the document whose purpose is to summarize reviewer-point coverage omits it entirely (covers only R1.3/R1.4/R1.5/R2.1). **Suggested change:** add an R1.1 row to the roll-up table. **Risk:** none. **Testing required:** none (documentation-only change).

### P2-7. Untested backend surfaces
No dedicated test file exists for authentication (`test_auth*`), dashboard/analytics aggregate SQL (`test_dashboard*`/`test_analytics*`), or the notification CRUD path (`test_notification*`) — confirmed by both `FINAL_CLEANUP_RECOMMENDATIONS.md`'s test-directory inventory and the per-feature Risk column in `FRONTEND_BACKEND_CONNECTION_MATRIX.md`. **Suggested change:** add coverage for these three areas. **Testing required:** n/a (this item is itself a testing-coverage gap).

---

## P3 — Low

- ~~**P3-1.** `AIOrchestrator._mark_optimized` issues one UPDATE per request instead of a bulk `IN (...)` update (`app/engine/optimizer.py` — `BACKEND_OPTIMIZATION.md` Finding 9).~~ **CORRECTED 2026-09-13: moot — `app/engine/optimizer.py` has been deleted and `POST /api/orchestration/optimize` now returns HTTP 410.**
- ~~**P3-2.** `AIOrchestrator._provider_map()` queries the full `Provider` table twice per `run()` (Finding 10).~~ **CORRECTED 2026-09-13: moot — same deletion as P3-1.**
- **P3-3.** Driver/vehicle create & update endpoints re-run the full list query (with its own Finding-4 full-table scans) just to re-serialize the one row they already hold (`app/api/routes/drivers.py` — Finding 11).
- **P3-4.** `AuthContext.jsx`'s provider value is a new object on every render (unmemoized); its `token` state is set but never consumed anywhere (`FRONTEND_OPTIMIZATION.md` LOW finding).
- **P3-5.** `LiveSimulationMap.jsx` has two separate, overlapping mechanisms that both fetch `/simulation/status` (one dead-on-interval, one live) — a maintainability risk, not a live duplicate-network-call bug (`FRONTEND_OPTIMIZATION.md` LOW finding).
- **P3-6.** `backend/seed_users.py` is PROBABLY DEAD (no references anywhere in code or docs) but not provably unreachable — recommend asking the team before archiving (`FINAL_CLEANUP_RECOMMENDATIONS.md`).

---

## Explicitly out of scope for this roadmap

Per the audits' own "Categories With No Findings" sections, the following were checked and found to already be well-implemented — **do not** "optimize" these without new evidence: OR-Tools solver invocation (no duplicates found), the `dmfe/serializers.py` batch-serialization layer (already prefetches to avoid per-row re-query), async/blocking-call separation (no `async def` route does blocking work), polling cleanup (every `setInterval` found is visibility-gated and cleaned up), the `services/api.js` request cache/dedup layer, and map marker/icon memoization (already using module-level caches keyed by visual parameters). See `BACKEND_OPTIMIZATION.md` and `FRONTEND_OPTIMIZATION.md`'s respective "Categories With No Findings" sections for full detail.
