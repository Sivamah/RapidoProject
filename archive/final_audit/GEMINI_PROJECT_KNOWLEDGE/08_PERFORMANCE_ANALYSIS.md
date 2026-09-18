# Performance Analysis

| Issue | Severity | Location | Problem | Safe Optimization | Risk |
|---|---|---|---|---|---|
| N+1 Queries | CRITICAL | `driver_selection.py` / Evaluator | Loading vehicles/drivers iteratively | Use SQLAlchemy `.joinedload()` or bulk fetching | Low |
| Repeated Haversine | HIGH | `score_engine.py` | Repeated distance calculations for the same pairs | Memoize or cache distance lookups in a session | Low |
| Sync Processing | HIGH | `pipeline.py` | Entire DMFE run is synchronous and blocks the API thread | Move DMFE execution to Celery/BackgroundTasks | Medium |
| Frontend Polling | MEDIUM | UI Dashboards | Polling active trips rapidly | Implement WebSockets or SSE for trip updates | Medium |

