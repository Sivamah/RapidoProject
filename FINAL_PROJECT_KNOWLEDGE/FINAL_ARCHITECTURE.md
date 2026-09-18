# Final Architecture (Current State)

This document describes the **current, as-built architecture** of A-DMFE (Adaptive Dynamic Multi-Service Feasibility Engine) exactly as found during the read-only audit on 2026-09-11. It is descriptive, not aspirational — nothing here is a recommendation. Optimization opportunities live in `OPTIMIZATION_ROADMAP.md`; the frontend-rendering defects noted below are documented in full in `FRONTEND_OPTIMIZATION.md`.

## 1. High-level pipeline

```
Request generation (mock_adapters.py, simulator or dataset upload)
        │
        ▼
SimulationRequest (DB) ──► Compatibility scoring (dmfe/compatibility.py, 5-factor)
        │                          │
        │                          ▼
        │                 Adaptive context/weights (dmfe/adaptive/*)
        │                  [only in "adaptive" mode; "static" mode skips this]
        │                          │
        ▼                          ▼
Batch generation (dmfe/batch_generator.py) ──► Decision engine (dmfe/decision_engine.py)
        │
        ▼
Route optimization (dmfe/optimizer.py — OR-Tools PDP solver, single-request fast path bypasses solver)
        │
        ▼
Driver/vehicle selection (dmfe/driver_selection.py) ──► Trip (DB) + DriverAssignment (DB)
        │
        ▼
Trip completion (driver_selection.complete_trip / complete_stale_trips)
        │
        ▼
Analytics (services/simulation_service.py, api/routes/dashboard.py)
        │
        ▼
XAI explanation (services/xai_service.py) ──► Frontend XAI panel + Live Map highlight
```

`dmfe/pipeline.py::PipelineRunner.run()` is the single real orchestrator that walks pending requests through batching → routing → dispatch in one call. It is invoked from two places: the `POST /api/dmfe/run`-style manual trigger paths in `dmfe_engine.py`, and — the actual path a running system uses — the background simulator tick in `services/simulation_service.py` (`SimulationEngine._run_loop`), which calls it automatically once `pending_count >= 6` every third tick.

## 2. Backend layout (FastAPI + SQLAlchemy + SQLite)

- **`app/main.py`** — FastAPI app factory, mounts 11 routers under `/api/*`, runs `sync_schema_columns()` (idempotent SQLite dev-DB column sync) at startup.
- **`app/api/routes/*.py`** (11 files) — HTTP boundary. `auth`, `providers`, `dashboard`, `orchestration`, `simulation`, `xai`, `notifications`, `drivers`, `config`, `dmfe_v2` (the endpoint the UI's "Run Analysis" actually calls: analyze/batches/history/statistics), `dmfe_engine` (a separate, more granular per-stage pipeline API — compatibility-score/context/batch-create/optimize-route/assign-driver/run/trip-complete — implemented and tested but **not called by any frontend file**, confirmed by `FRONTEND_BACKEND_CONNECTION_MATRIX.md`).
- **`app/dmfe/*.py` + `app/dmfe/adaptive/*.py`** — the protected DMFE/A-DMFE core: `compatibility.py` (5-factor scorer), `scoring.py`/`score_engine.py`, `decision_engine.py`, `batch_generator.py`, `optimizer.py` (OR-Tools PDP + Google Distance Matrix fallback), `driver_selection.py` (dispatch, driver/vehicle pick, trip completion), `pipeline.py` (orchestrator), `serializers.py`. `adaptive/` adds context-awareness (`context.py`), a learning engine with a persisted residual/driver/corridor state (`learning.py`), adaptive weight generation (`weights.py`), and adaptive threshold logic (`decision.py`, `factors.py`, `matrix.py`).
- **`app/engine/*.py`** — a smaller, older module set. `distance.py` (the one canonical haversine implementation, imported by both `app/dmfe/*` and `app/engine/*`) is live. `optimizer.py` (the legacy `AIOrchestrator`) is **CORRECTED 2026-09-13: DELETED** — `POST /api/orchestration/optimize` now unconditionally returns HTTP 410; the "still actively mounted" claim below is stale and superseded. `explainability.py` is dead code (zero references anywhere — see `FINAL_CLEANUP_RECOMMENDATIONS.md`), superseded by `app/services/xai_service.py`.
- **`app/services/*.py`** — `mock_adapters.py` (synthetic request/fleet generation), `simulation_service.py` (the background `SimulationEngine` thread: generates demand, calls `pipeline_runner.run()`, completes stale trips, computes analytics), `xai_service.py` (explanation generation, `_trip_metrics()` cost/profit derivation), `driver_service.py`, `config_service.py`, `notification_service.py`, `playback_service.py`.
- **`app/db/models.py`** — SQLAlchemy models: `User`, `Provider`, `Driver`, `Vehicle`, `SimulationRequest`, `DMFEBatch`, `Trip`, `DriverAssignment`, `DriverAssignmentHistory`, `SystemConfig`, `SystemNotification`, `Dataset`, `SimulationScenario`, plus adaptive-learning state persisted inside `SystemConfig` as JSON documents.
- **`app/schemas/*.py`** — Pydantic request/response contracts (notably `schemas/xai.py::XAIExplanationItem`, extended this session with `trip_cost_inr`/`separate_cost_inr`/`solo_profit_inr`).
- **`app/core/*.py`** — `config.py` (pydantic Settings), `security.py` (bcrypt/JWT), `middleware.py`, `coimbatore.py` (city seed geodata), `json_utils.py`.

## 3. Frontend layout (React 19 + Vite + Tailwind)

- **`App.jsx`** — router root; 14 pages are `lazy()`-loaded and routed under `AuthProvider` → `ProtectedRoute` → `AdminLayout`. **`App.jsx` itself statically imports `./components/ui/AnimatedBackground`, a file that does not exist anywhere in the repository** — this is a build-breaking defect, not a lazy-loaded page issue; see `FRONTEND_OPTIMIZATION.md`'s first CRITICAL finding.
- **14 pages** (`pages/*.jsx`): `Login`, `Dashboard`, `AIDashboard`, `DMFEDashboard`, `AnalyticsDashboard`, `DriverDashboard`, `SystemConfiguration`, `NotificationCenter`, `ScenarioDashboard`, `ExplanationDashboard`, `LiveSimulationMap`, `SimulationMonitoring`, `DatasetManagement`, `ProviderManagement`. Of these, **6 fail to render** because they import components from directories that were never committed or were deleted (`components/drivers/`, `components/config/`, most of `components/analytics/`, most of `components/dmfe/`, most of `components/notifications/`, most of `components/playback/`) — see `FRONTEND_OPTIMIZATION.md` for the full file-by-file breakdown.
- **`services/api.js`** — single shared axios client; deliberately implements a 2s response cache + in-flight dedup + blanket cache invalidation on mutation (confirmed well-engineered by the audit).
- **`components/map/*`** — Leaflet/Google-Maps live map stack (`LiveMapContainer`, `XAIHighlightLayer`, `ActiveTripsLayer`, `FleetLayer`, `RequestMarkers`, `MapControls`, `MarkerPopup`, `KpiBar`, `MapFilterPanel`, `markerIcons.js`), all confirmed actively wired and free of the performance anti-patterns the audit checked for.
- **`components/xai/*`** — `DecisionCard`, `XaiDecisionPanel`, `XaiMapPanel` (the live 3-column AI Insights UI built earlier in this session); `ScoreBreakdown.jsx`, `ExplanationFilters.jsx`, and a duplicate `CompatibilityGauge.jsx` are dead code left over from the pre-redesign page (see `FINAL_CLEANUP_RECOMMENDATIONS.md`).
- **`utils/xaiMap.js`** — `normalizeXaiHighlight()`, the single shared normalizer feeding both the inline XAI map panel and the `/live-map?xai=<id>` deep link (the deep link itself is implemented and backend-tested but has no in-app control that ever constructs its URL — see connection-matrix feature 12).
- **`hooks/{useOperationalNetwork,useOperationalRoute,useSeparateRoutes}.js`** — polling/route-geometry hooks, confirmed to key their effects on coordinate fingerprints rather than object identity specifically to avoid re-fetch storms under polling.

## 4. Data flow: XAI → Map

`xai_service.get_explanations()` (backend) returns `XAIExplanationItem` rows already carrying `related_requests`, `trip` (driver/vehicle/route_stops), `factors`, and the cost/profit fields. The frontend's `normalizeXaiHighlight()` (`utils/xaiMap.js`) is the single translation layer from that API shape into what `XaiMapPanel`/`XAIHighlightLayer` render — used identically whether the explanation arrives via the same-tab click-through (`ExplanationDashboard.jsx` → `XaiMapPanel.jsx`, no extra network call) or the standalone `/live-map?xai=<id>` deep link (`LiveSimulationMap.jsx`, one extra `GET`). Only the first path is currently reachable from any UI control.

## 5. Evaluation / research layer

`backend/evaluation/` is a separate toolchain (not imported by the running app) that exercises the real `dmfe/`/`dmfe/adaptive/` code through a shared `framework.py::WorkloadRunner` harness to produce IEEE-reviewer-response evidence (R1.1/R1.3/R1.4/R1.5/R2.1 — see `REVIEWER_AUDIT.md`) and broader research artifacts (`results/*.json`, `results/*.md`, `ieee_tables.md/.tex`). All five reviewer scripts were confirmed to call the real production pipeline, not a reimplementation.

## 6. External services

- **Google Maps Distance Matrix API** — called synchronously from `dmfe/optimizer.py::_google_distance_matrix` (sync `def` route handlers, so this runs in FastAPI's thread pool, not on the event loop).
- **OR-Tools (`ortools.constraint_solver`)** — the PDP solver in `dmfe/optimizer.py`; single-request trips bypass the solver entirely via a documented fast path.
- **SQLite** — the only database in this checkout (`backend/dmfe_dev.db`, `backend/qa_test.db`); `migrations/001_dmfe_batch_predicted_utilization.py` exists specifically for non-SQLite (e.g. Postgres) production targets, since `main.py`'s own `sync_schema_columns()` is explicitly SQLite-only.

## 7. Protected core (per this project's standing rule)

The following are the DMFE/A-DMFE "hard-stop" files — compatibility scoring, batching, the decision engine, OR-Tools optimization, driver selection/assignment, adaptive threshold formulas, and the DB schema/auth/API contracts they depend on. Any future AI work must not modify these without explicit, scoped approval (see Rule 1 and Rule 4 in `MASTER_PROJECT_CONTEXT.md`):

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
backend/app/dmfe/adaptive/*.py  (batching, context, decision, factors, learning, matrix, weights, xai, _util)
backend/app/db/models.py        (schema)
backend/app/core/security.py    (auth)
```
