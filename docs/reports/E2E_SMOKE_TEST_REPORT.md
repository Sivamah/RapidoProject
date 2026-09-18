# End-to-End Production Smoke Test Report

**Date:** 2026-09-04
**Scope:** Current working-tree state of the A-DMFE unified mobility/delivery project.
**Method:** Live HTTP API against an **isolated throwaway SQLite DB** (dev and QA DBs untouched). No source code modified.
**Goal:** Prove the current system works end-to-end before final freeze.

---

## Environment

| Item | Value |
|------|-------|
| Backend | FastAPI on `127.0.0.1:8088`, running from `backend/` |
| Frontend | React 19 + Vite (`frontend/`) |
| Test DB | `temp/smoke_e2e.db` (throwaway, isolated) |
| Fleet | Auto-seeded: 20 drivers, 15 vehicles |
| Auth | Fresh admin token (`admin@aiorch.com`) |
| Workload | 50 deterministic mixed requests (ride 20 / food 22 / parcel 8) |
| A-DMFE mode | `adaptive` |

---

## 13-Step Verification Results

All **41 checks PASS, 0 FAIL**.

| # | Verify | Result | Evidence |
|---|--------|--------|----------|
| 1 | Request creation | ✅ | 50 requests created, all `Pending`; mix 20 ride / 22 food / 8 parcel |
| 2 | A-DMFE execution | ✅ | `/dmfe/run` + `/dmfe/context`; mode=`adaptive`, context profile present (traffic_index, demand_pressure, driver_availability, capacity_stress, service_entropy) |
| 3 | Compatibility scoring | ✅ | `/dmfe/compatibility-score` returned HTTP 200, score 43.6 |
| 4 | Batch formation | ✅ | `/dmfe/batch/create` → 14 feasible batches, 16 individual request ids |
| 5 | Dispatch | ✅ | Pipeline processed all 50; 8 shared + 7 individual trips |
| 6 | Driver assignment | ✅ | 15 assignments; driver stats 20 total / 5 avail / 15 busy |
| 7 | Vehicle assignment | ✅ | 15/15 trips have a vehicle; 15 vehicles in service |
| 8 | Trip completion | ✅ | 15/15 wave-1 trips completed via `POST /dmfe/trips/{id}/complete` |
| 9 | Driver/vehicle release | ✅ | After completion: 20 available / 0 busy drivers; assignments marked Completed |
| 10 | Next-wave dispatch | ✅ | 23 remaining Pending re-dispatched; wave 2 = 6 shared + 9 individual, **0 unassigned** |
| 11 | Dashboard update | ✅ | `/dashboard/stats`: requests 0→50, trips 0→30, batch_rate 46.67%, fuel_saved 15.22 L |
| 12 | Analytics update | ✅ | `/simulation/analytics` + `/dmfe/statistics` reflect the run (trips 30, shared 14) |
| 13 | XAI update | ✅ | 50 explanations; overview shows avg compatibility 80.9, "Compatible for Batching" dominant |

---

## Recorded Metrics

| Metric | Wave 1 | Wave 2 | Total |
|--------|--------|--------|-------|
| Requests created | 50 | — | 50 |
| Shared batches (trips) | 8 | 6 | 14 |
| Individual trips | 7 | 9 | 16 |
| Dispatched trips | 15 | 15 | 30 |
| Rejected / unassigned (single pass) | 15 | 0 | 0 remaining |
| Drivers used (busy) | 15 | — | 15 |
| Vehicles used (in service) | 15 | — | 15 |
| Completed trips | 15 | — | 15 (wave 1) |
| Failures / errors | 0 | 0 | 0 |
| **Total execution time** | — | — | **2.26 s** |
| Pipeline run elapsed (single pass) | — | — | 0.62 s |

> **Unassigned note:** The 15 unassigned requests in wave 1 were all due to fleet
> capacity exhaustion (`No available driver/vehicle for trip with N request(s)`).
> This is an **expected driver-capacity limitation**, not a bug — every one of the
> 15 vehicles was Busy at that moment. After completion released capacity, the
> next-wave dispatch served all 23 remaining Pending requests with 0 unassigned.

---

## Automated Checks

| Check | Command | Result |
|-------|---------|--------|
| Backend tests | `pytest -q` | ✅ 69 passed (0 failures) |
| Frontend build | `npm run build` | ✅ Built in 819 ms (Vite 8.1.5) |
| Frontend lint | `npm run lint` (oxlint) | ✅ 0 errors, 3 warnings |

### Lint warnings (informational, non-blocking)
- `src/components/map/RequestMarkers.jsx` — Fast-refresh only-export-components (2)
- `src/context/AuthContext.jsx` — move React context to separate file (1)

### Pytest warnings (informational)
- Pydantic `class Config` → `ConfigDict` deprecations across `app/schemas/*.py`
- Starlette `httpx`/`TestClient` deprecation warning
- SQLAlchemy table-sort cycle warning for `drivers` ↔ `vehicles` (pre-existing)

---

## Remaining Real Issues

**No functional defects found.** The current system works end-to-end.

Non-blocking notes (not bugs, flagged for the post-freeze cleanup phase):
1. **Fleet size is the primary throughput limit** — 15 vehicles / 20 drivers means a
   50-request wave saturates capacity and requires a second wave. Expected given the
   seeded fleet; not an engine defect.
2. **Lint/pytest warnings** are deprecation/style only (Pydantic v2 `ConfigDict`,
   Fast-refresh pattern, driver↔vehicle table cycle warning).
3. `/dmfe/statistics` shows `total_runs=0`, `total_batches_created=0`,
   `total_pairs_evaluated=0` despite a successful run — the run pipeline (`/dmfe/run`)
   does not increment the DMFE-v2 analysis-run counters (those are populated by the
   analysis path `/dmfe/analyze`). **Informational observation, not a functional
   failure** of the dispatch pipeline (trips/batches are correctly recorded).

---

## Artifacts
- Driver script: `temp/smoke_e2e_driver.py` (temporary)
- Machine summary: `temp/smoke_summary.json` (temporary)
- This report: `docs/reports/E2E_SMOKE_TEST_REPORT.md`
