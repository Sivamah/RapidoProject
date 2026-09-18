# Backend Optimization Audit

**Scope:** A-DMFE backend — `app/api/routes/*` (11 files), `app/dmfe/*` + `app/dmfe/adaptive/*` (core engine), `app/services/*`, `app/db/{database,models}.py`, `app/core/*`, `app/engine/*`, `app/main.py`. `backend/tests/*` and `backend/evaluation/*` were read only to understand call patterns, per instructions. `backend/.env` was never opened.

**Method:** Read-only inspection (no code changed). Every finding below is anchored to real lines in the mirrored repository at `/mnt/user-data/uploads/rapidoproject/`. Where a category has no supporting evidence in the audited scope, that is stated explicitly rather than omitted.

## Summary

**Files actually inspected: 40**
(11 route files; `dmfe/`: compatibility, scoring, score_engine, decision_engine, optimizer, driver_selection, pipeline, batch_generator, serializers, models — 10 files; `dmfe/adaptive/`: batching, context, decision, factors, learning, matrix, weights, xai, _util — 9 files, of which xai.py and _util.py were skimmed and contributed no findings; `services/`: config_service, driver_service, mock_adapters, notification_service, playback_service, simulation_service, xai_service — 7 files; `db/`: database, models — 2 files; `core/`: config, security, middleware, json_utils, coimbatore — 5 files; `engine/`: distance, explainability, optimizer — 3 files; `main.py` — 1 file. `app/api/deps.py` and `app/schemas/*` were read for context but carry no findings of their own.)

**Findings by severity:**
- Critical: 0
- High: 3
- Medium: 5
- Low: 3

**Total findings: 11**

Overall impression: the DMFE core (`compatibility.py`, `batch_generator.py`, `driver_selection.py`, `optimizer.py`, `pipeline.py`) already carries extensive, well-documented optimization work from prior passes (TTL config caching, per-run memoization, grouped-query `DriverPool`, spatial bucketing instead of O(n²) pair scans, single-query bulk updates in `complete_stale_trips`). The findings below are the gaps that remain, concentrated in three areas: (1) the adaptive-mode context/learning-state stack is rebuilt or re-read redundantly within a single request, (2) a few list/read endpoints in `driver_service.py` and `xai_service.py` re-query data they could reuse or fetch once, and (3) several write paths commit or query per-row inside a loop instead of batching.

---

## Findings

### 1. Duplicate `ContextAwarenessEngine.build()` call per DMFE run (adaptive mode)

FILE: `backend/app/dmfe/decision_engine.py`
FUNCTION: `DecisionEngine.run_analysis`
PROBLEM: In adaptive mode, the full context profile is built once to compute the effective threshold for logging, then built again inside `generate_candidates()` for the actual batching — each build re-runs the same ~6 DB queries and an O(n²) haversine congestion scan.
EVIDENCE:
```
# decision_engine.py, lines 561-570
mode = resolve_mode(db)
context_profile_dict = None
if mode == "adaptive":
    from app.dmfe.adaptive.context import ContextAwarenessEngine
    from app.dmfe.adaptive.decision import effective_threshold
    context = ContextAwarenessEngine().build(db, pending)
    context_profile_dict = context.to_dict()
    threshold = effective_threshold(threshold, context)
...
# decision_engine.py, line 588-590
candidate_groups: List[CandidateGroup] = self._generator.generate_candidates(
    pending, db
)
```
`generate_candidates` (batch_generator.py, lines 329-346) independently does, for the same `pending` list and the same DB state:
```
context = ContextAwarenessEngine().build(db, pending_requests)
learning_state = LearningEngine.load_state(db)
weights = AdaptiveWeightGenerator(mode="adaptive").generate(
    db, context, LearningEngine.weight_corrections(db)
)
threshold = effective_threshold(_get_threshold(db), context)
```
`ContextAwarenessEngine.build()` itself (`context.py` lines 119-199, 232-307) issues, per call: `get_config_value` (1 query), a `SimulationScenario` query, `Driver.count()`, `Driver.filter(status=="Available").all()`, a `Vehicle` query, and `LearningEngine.learned_signals()` (which itself loads and JSON-decodes the full learning-state blob — see Finding 2) — plus an O(n²) haversine congestion scan over the pending pool (`context.py` lines 240-256).

The identical pattern repeats in `backend/app/dmfe/pipeline.py`, `PipelineRunner.run` (lines 190-208), which builds context once for the logged threshold and then calls `self._generator.create_feasible_batches(pending, db)` (line 212), whose adaptive path (`batch_generator.py`, `_create_adaptive_batches`, lines 263-308) builds context a second time. `PipelineRunner.run` is invoked from `POST /api/dmfe/run` **and** from the live simulation background loop (`simulation_service.py` line 654, fired roughly every third tick, i.e. every 9-15 seconds while the simulator is running), so this duplicate work runs continuously, not just on manual triggers.
SEVERITY: High
EXPECTED BENEFIT: Removes one full `ContextAwarenessEngine.build()` invocation (≈6 SQL queries + one O(n²) haversine pass over the pending pool, e.g. ~20k haversine calls at 200 pending requests) from every `/api/dmfe/analyze` and `/api/dmfe/run` call, and from every dispatch-triggering simulation tick.
RISK: The two build() calls currently happen at slightly different points in the same request, so in principle DB state could change between them (e.g. another thread completing a trip) and produce a marginally different context; sharing one context object removes that (already negligible) skew but should be verified against `test_pipeline_accounting.py` / `test_scoring_unified.py` before merging, since the persisted `DMFEAnalysisRun.threshold_used` and batch `context_profile` fields are user/dashboard-visible.
RECOMMENDED FIX: Thread the already-built `context` (and, where available, `weights`/`learning_state`) through to `generate_candidates` / `create_feasible_batches` as optional parameters, falling back to building it internally only when not supplied — mirroring the `precomputed`/`request_metrics` parameters `CompatibilityCalculator.compute()` already accepts for the same purpose.

---

### 2. `LearningEngine.load_state()` re-read and re-parsed multiple times per adaptive batching call

FILE: `backend/app/dmfe/batch_generator.py`
FUNCTION: `BatchGenerator._create_adaptive_batches` (and the structurally identical adaptive branch of `BatchGenerator.generate_candidates`)
PROBLEM: The same immutable-for-the-duration-of-the-call learning-state document is fetched from `SystemConfig` and JSON-deserialized three separate times within a few lines, instead of being loaded once and passed down.
EVIDENCE:
```
# batch_generator.py, lines 286-291 (_create_adaptive_batches)
rules = _get_ai_rules(db)
context = ContextAwarenessEngine().build(db, pending_requests)     # → learned_signals() → load_state()  [load #1]
learning_state = LearningEngine.load_state(db)                     # [load #2]
weights = AdaptiveWeightGenerator(mode="adaptive").generate(
    db, context, LearningEngine.weight_corrections(db)             # weight_corrections() → load_state() [load #3]
)
```
`learning.py`, `weight_corrections` (lines 746-754) and `learned_signals` (lines 809-833) each independently call `state = LearningEngine.load_state(db)` (definition at lines 147-162), which runs `db.flush()`, a `SystemConfig` SELECT, and `json.loads()` of the whole state document (residual ring buffers up to 200 entries × 4 tags, driver summaries up to 500 entries, corridor maps up to 200 entries — `RESIDUAL_BUFFER_SIZE`, `DRIVER_SUMMARY_CAP`, `QUALITY_CAP` in `learning.py` lines 83-94). None of these three call sites cache the result — contrast with `driver_selection.py`'s `_learned_proximity_bump` (lines 478-484), which wraps the same call in the module's session-scoped `_cached()` helper and is the only call site that avoids the repeat read. The identical triple-load pattern is duplicated verbatim in `generate_candidates` (`batch_generator.py` lines 341-346).
SEVERITY: High
EXPECTED BENEFIT: Cuts 3 redundant `SystemConfig` reads + JSON parses of a potentially multi-KB document down to 1 per adaptive batching call — compounds with Finding 1 since each duplicated `ContextAwarenessEngine.build()` also triggers its own `learned_signals()` load.
RISK: `load_state` starts with `db.flush()` to see pending in-session writes before reading; a shared/cached state must still be loaded after any write that happens between the context build and the weight generation in the same call (none currently occurs in this code path, but a future edit that writes learning state mid-call could silently see stale data if caching is added carelessly).
RECOMMENDED FIX: Load the state once at the top of `_create_adaptive_batches`/`generate_candidates` and pass it into both `ContextAwarenessEngine.build()` (as an optional parameter, avoiding the internal `learned_signals()` re-read) and `AdaptiveWeightGenerator.generate()` (deriving `weight_corrections` from the already-loaded dict instead of calling the DB-backed helper).

---

### 3. XAI explanation list re-queries the same partner pool once per request instead of once per call

FILE: `backend/app/services/xai_service.py`
FUNCTION: `_generate_explanation_for_request` (called from `XAIService.get_explanations`)
PROBLEM: For every request being explained (up to `limit`, default 100) that is not already cache-hit, a fresh SQL query re-fetches "the 20 most recent other requests" — a set that is almost identical across calls within the same `get_explanations()` invocation (it only excludes the current request's own id) — instead of being computed once from the `requests` list already loaded by the caller.
EVIDENCE:
```
# xai_service.py, lines 245-252 (_generate_explanation_for_request)
partners = (
    db.query(SimulationRequest)
    .filter(SimulationRequest.id != req_id)
    .order_by(SimulationRequest.created_at.desc())
    .limit(_MAX_PARTNERS)
    .all()
)
result = _best_partner(calculator, db, req, partners, compute_kwargs)
```
called from the loop in `get_explanations`:
```
# xai_service.py, lines 551-561
for req in requests:
    ...
    else:
        exp = _generate_explanation_for_request(
            db, self._calculator, req, pname, threshold,
            _compute_kwargs(), _trip_index(),
        )
```
`requests` (line 515, `query.all()`) is already ordered `created_at.desc()` — the same ordering the partner query re-derives from scratch per row. `_best_partner` (lines 40-67) then runs `calculator.compute([req, other], db, ...)` for up to 20 partners per request, so a full cache-miss call over 100 requests issues up to 100 extra partner queries plus up to 2000 `compute()` evaluations that could largely be served from the `requests` list already in memory.
SEVERITY: High
EXPECTED BENEFIT: Eliminates up to N (≤100) duplicate `SimulationRequest` queries per `/api/xai/explanations` or `/api/xai/overview` call on a cache miss (e.g. right after the simulator seeds new requests, when the 30s explanation cache — `_EXPLANATION_CACHE_TTL`, line 36 — is cold for most rows).
RISK: The current per-request partner query naturally excludes the request itself and always returns up to 20 rows even if `requests` (the caller's list) is shorter than 20; a shared-list version must replicate the exact "exclude self, most-recent 20" semantics (e.g. take the newest 21 from `requests` and drop `req_id`) to keep explanations byte-identical, and must still query for partners when a request's true self-batch partner falls outside the caller's own `limit`-bounded list.
RECOMMENDED FIX: Fetch a single "candidate partner pool" (the newest `_MAX_PARTNERS + limit` or so `SimulationRequest` rows) once per `get_explanations()` call, then have `_generate_explanation_for_request` filter that in-memory list per request instead of issuing a new query.

---

### 4. `driver_service.get_drivers` / `get_vehicles` / `get_vehicle_locations` full-scan Provider/Vehicle/Driver on every call

FILE: `backend/app/services/driver_service.py`
FUNCTION: `DriverService.get_drivers`, `DriverService.get_vehicles`, `DriverService.get_vehicle_locations`
PROBLEM: Each of these list endpoints loads the *entire* `Provider` table (and, for vehicles/locations, the entire `Driver` or `Vehicle` table) into a Python dict on every call, purely to look up display names for the already `limit`-bounded primary result set — the lookup dicts are not scoped to the ids actually present in that result set.
EVIDENCE:
```
# driver_service.py, lines 153-157 (get_drivers)
drivers = query.order_by(Driver.created_at.desc()).limit(limit).all()
providers = {p.id: p.name for p in db.query(Provider).all()}
vehicles = {v.id: v.name for v in db.query(Vehicle).all()}
```
```
# driver_service.py, lines 218-221 (get_vehicles)
vehicles = query.order_by(Vehicle.created_at.desc()).limit(limit).all()
providers = {p.id: p.name for p in db.query(Provider).all()}
drivers = {d.id: d.name for d in db.query(Driver).all()}
```
```
# driver_service.py, lines 259-261 (get_vehicle_locations)
vehicles = db.query(Vehicle).all()
providers = {p.id: p.name for p in db.query(Provider).all()}
drivers = {d.id: d.name for d in db.query(Driver).all()}
```
Contrast with `app/api/routes/simulation.py`'s `_provider_name_map` (lines 37-42), which scopes the same kind of lookup to only the ids actually referenced: `db.query(Provider.id, Provider.name).filter(Provider.id.in_(ids)).all()`.
SEVERITY: Medium
EXPECTED BENEFIT: Replaces 2-3 unbounded full-table scans per call with `IN`-filtered queries scoped to the ≤`limit` ids actually returned (e.g. `limit=100` drivers needing at most 100 distinct provider/vehicle ids, versus every row in those tables regardless of size).
RISK: Low — this is a pure read-path optimization; the only behavioral risk is a lookup miss if a referenced provider/vehicle/driver id was deleted after the fact, which the current full-table version already tolerates via `.get(id, "Unassigned"/"None")` and an `IN`-scoped version would tolerate identically.
RECOMMENDED FIX: Build the provider/vehicle/driver name maps from `Provider.id.in_({d.provider_id for d in drivers})`-style filtered queries (as `simulation.py` already does), scoped to the ids present in the just-fetched primary result set.

---

### 5. `config_service.update_configs` issues one `SystemConfig` query per key instead of one batched query

FILE: `backend/app/services/config_service.py`
FUNCTION: `ConfigService.update_configs`
PROBLEM: A single `PATCH /api/config` call with N settings performs N separate single-row `SystemConfig` lookups inside a loop instead of one query fetching all N rows.
EVIDENCE:
```
# config_service.py, lines 110-121
def update_configs(self, db: Session, settings: Dict[str, Any], user_email: str = "admin@antigravity.ai") -> int:
    self.seed_defaults_if_needed(db)
    updated_count = 0
    for key, new_val in settings.items():
        cfg = db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if not cfg:
            continue
```
This is invoked by `PATCH /api/config` (`config.py` route, `update_configurations`), by `import_config` (which flattens every category's settings into one dict and calls `update_configs` once — `config_service.py` lines 186-194), and by `reset_to_defaults` (which passes all `DEFAULT_CONFIG_DEFS` keys at once — currently ~26 keys, lines 204-206). A config import or a factory reset therefore issues one query per config key.
SEVERITY: Medium
EXPECTED BENEFIT: Reduces N single-row SELECTs to 1 `WHERE key IN (...)` SELECT per `update_configs` call — for `reset_to_defaults`/`import_config` that is roughly 26 queries collapsed to 1.
RISK: Low. `SystemConfig.key` is unique-indexed (`db/models.py` line 260), so an `IN`-query returns exactly the same rows the loop would have found one at a time; ordering/iteration semantics of the surrounding loop (audit-log construction, `updated_count`) are unaffected as long as the fetched rows are re-keyed into a dict before the loop that builds `ConfigAuditLog` entries.
RECOMMENDED FIX: Replace the per-key `.filter(SystemConfig.key == key).first()` with one `db.query(SystemConfig).filter(SystemConfig.key.in_(settings.keys())).all()`, index the results by key, and iterate `settings.items()` against that in-memory dict.

---

### 6. `log_system_notification` commits (and refreshes) on every call, including inside loops

FILE: `backend/app/services/notification_service.py`
FUNCTION: `log_system_notification`
PROBLEM: The helper unconditionally calls `db.commit()` and `db.refresh()` on every invocation. It is called from inside loops in the simulation background thread, turning what could be one commit per tick into one commit per generated request and one commit per completed trip.
EVIDENCE:
```
# notification_service.py, lines 21-34
def log_system_notification(...):
    try:
        notif = SystemNotification(...)
        db.add(notif)
        db.commit()
        db.refresh(notif)
        return notif
```
Call sites inside loops, both in the simulation engine's background tick (`simulation_service.py`):
```
# simulation_service.py, lines 626-641 — once per generated request in the burst (1-3 per tick)
for req in generated:
    ...
    log_system_notification(db, title=f"New {r_type} Request Generated", ...)
```
```
# simulation_service.py, lines 698-711 — once per trip released in this tick
for t in due_trips:
    completed = complete_trip(db, t.id, commit=False)
    log_system_notification(db, title="Trip Completed", ...)
```
SEVERITY: Medium
EXPECTED BENEFIT: Collapses up to `burst_size` (1-3) + `len(due_trips)` separate SQLite transactions per simulation tick into a single commit at the end of the tick (the surrounding `_run_loop` already does a final `db.commit()` at line 713 for `due_trips`, so the per-notification commits inside the loop are redundant with it).
RISK: `log_system_notification` currently rolls back only its own insert on failure (`except Exception: db.rollback()`, lines 35-37) and returns `None` — if commits are batched, a later failure in the same tick (e.g. a `complete_trip` error) would need its own try/except so it does not also roll back notifications that were meant to survive; the function is also called from several one-off request handlers (`providers.py`, `drivers.py`) where an immediate commit is appropriate and should be preserved via an optional `commit: bool = True` parameter rather than removed outright.
RECOMMENDED FIX: Add an optional `commit: bool = True` parameter (mirroring the pattern already used by `AssignmentEngine.create_assignment` and `complete_trip`), pass `commit=False` from the two loop call sites in `simulation_service.py`, and rely on the loop's existing trailing `db.commit()`.

---

### 7. `simulation_service.get_advanced_analytics` queries completed `Trip` rows twice

FILE: `backend/app/services/simulation_service.py`
FUNCTION: `QueueManager.get_advanced_analytics`
PROBLEM: The same `Trip` rows (all trips with a non-null `completed_at`) are fetched from the database twice within one function call — once indirectly via `completed_at_map(db)`, and once directly a few lines later — instead of being fetched once and reused.
EVIDENCE:
```
# simulation_service.py, line 250 (get_advanced_analytics)
completed_map = completed_at_map(db)
```
`completed_at_map` (lines 31-43) internally runs:
```
for trip in db.query(Trip).filter(Trip.completed_at.isnot(None)).all():
    ...
```
Then, 29 lines later in the same function:
```
# simulation_service.py, lines 278-286
completion_times = []
for t in db.query(Trip).filter(Trip.completed_at.isnot(None)).all():
    if t.created_at and t.completed_at:
        ...
```
Both loops scan the identical predicate (`Trip.completed_at IS NOT NULL`) over the same table within the same request.
SEVERITY: Medium
EXPECTED BENEFIT: Removes one full re-scan of completed trips per `/api/simulation/advanced-analytics` call (this endpoint also feeds `playback_service.save_current_simulation_snapshot`, which calls `completed_at_map(db)` again separately for its own waiting-time calculation).
RISK: Low — purely a read-path dedup; the two loops derive different aggregates (a request-id→timestamp map vs. a list of completion durations) from the same rows, so merging them only requires computing both aggregates from one fetched list.
RECOMMENDED FIX: Fetch `db.query(Trip).filter(Trip.completed_at.isnot(None)).all()` once at the top of `get_advanced_analytics`, derive `completed_map` from it locally (same logic as `completed_at_map`) instead of calling the helper, and reuse the same list for the `completion_times` loop.

---

### 8. `PipelineRunner.run` commits once per dispatched trip

FILE: `backend/app/dmfe/pipeline.py`
FUNCTION: `PipelineRunner.run`
PROBLEM: Inside both the shared-trip and individual-trip dispatch loops, `db.commit()` is called once per successfully dispatched trip (in addition to the commit already performed inside `dispatch_trip` → `AssignmentEngine.create_assignment`), rather than batching all dispatch records into one commit after the loop.
EVIDENCE:
```
# pipeline.py, lines 274-286 (shared-trip loop)
result.shared_trips += 1
result.assignments_created += 1
_record_dispatch(batch, outcome)
# dispatch_trip() already committed the Trip; commit the dispatch
# record with it so a later iteration's db.rollback() cannot
# discard it. ...
db.commit()
driver_pool.drivers = [d for d in driver_pool.drivers if d.id != outcome["driver"].id]
driver_pool.vehicles = [v for v in driver_pool.vehicles if v.id != outcome["vehicle"].id]
```
The identical pattern repeats for individual trips at lines 329-336. For a pipeline run dispatching, say, 30 requests as a mix of shared/individual trips, this is up to 30 additional `db.commit()` calls (each an SQLite WAL flush) beyond the ones `dispatch_trip` already performs.
SEVERITY: Medium
EXPECTED BENEFIT: Would reduce N per-trip commits to 1 trailing commit per pipeline run if batched — but see RISK below, which is why this is flagged rather than paired with a batching recommendation as strongly as Finding 6.
RISK: This pattern is deliberate and documented in the code: an exception in a later iteration triggers `db.rollback()` (lines 249-251, 264-266, 308-311, 320-322), and without the per-iteration commit that rollback would silently discard the `_record_dispatch` reason line and the `details["predicted"]` snapshot for every earlier successful dispatch in the same run — data the comment states the learning engine depends on to recover the dispatch-time prediction later. Removing the per-trip commit without also removing the per-trip `db.rollback()` (or replacing it with a savepoint) would reintroduce the exact data-loss bug this code was written to fix.
RECOMMENDED FIX: Not a plain "move the commit outside the loop" — evaluate whether SQLAlchemy `SAVEPOINT`s (`db.begin_nested()`) around each trip's dispatch would let a single failure roll back only that trip while still allowing one outer commit for the whole run; otherwise, this trade-off (correctness under partial failure vs. commit-per-row throughput) should be treated as an intentional, already-justified design choice and left as documentation for a future reviewer rather than changed casually.

---

### 9. `AIOrchestrator._mark_optimized` issues one UPDATE per request instead of a bulk update

FILE: `backend/app/engine/optimizer.py`
FUNCTION: `AIOrchestrator._build_results` / `AIOrchestrator._mark_optimized`
PROBLEM: After building each batch's result dict, the code loops over the batch's requests and issues one single-row `UPDATE` per request to mark it `Optimized`, instead of one bulk `UPDATE ... WHERE id IN (...)` for all requests across all batches.
EVIDENCE:
```
# engine/optimizer.py, lines 239-243 (_build_results)
for r in batch_reqs:
    self._mark_optimized(r["id"])
self.db.commit()
```
```
# engine/optimizer.py, lines 245-248 (_mark_optimized)
def _mark_optimized(self, request_id: int) -> None:
    self.db.query(SimulationRequest).filter(
        SimulationRequest.id == request_id
    ).update({"status": "Optimized"}, synchronize_session=False)
```
**CORRECTED 2026-09-13:** `app/engine/optimizer.py` (the legacy `AIOrchestrator`) has since been deleted and `POST /api/orchestration/optimize` now unconditionally returns HTTP 410. This finding and the "not dead code" claim below are stale and do not apply to the current codebase — no further optimization work is needed here.
~~This module (`app/engine/optimizer.py`, the legacy `AIOrchestrator`) is not dead code — it is actively imported and used by `POST /api/orchestration/optimize` (`app/api/routes/orchestration.py` line 9, `run_optimization` at lines 79-90).~~
SEVERITY: Low (moot — file deleted)
EXPECTED BENEFIT: Collapses up to N single-row UPDATE statements (N = total requests across all OR-Tools-produced batches in one `/api/orchestration/optimize` call) into a single `UPDATE ... WHERE id IN (...)`.
RISK: Low — `synchronize_session=False` is already used, so switching to one `.filter(SimulationRequest.id.in_(all_ids)).update(...)` call preserves the same session-sync semantics; the only behavior change is that all requests are marked in one statement instead of possibly-interleaved per-row statements (no ordering dependency exists between them).
RECOMMENDED FIX: Collect all `request_id`s across every batch in `_build_results` and issue one `self.db.query(SimulationRequest).filter(SimulationRequest.id.in_(ids)).update({"status": "Optimized"}, synchronize_session=False)` before the trailing `self.db.commit()`, mirroring the bulk-update pattern already used in `driver_selection.complete_stale_trips` (`driver_selection.py` lines 936-943).

---

### 10. `AIOrchestrator._provider_map` re-queries the full `Provider` table twice per `run()`

FILE: `backend/app/engine/optimizer.py`
FUNCTION: `AIOrchestrator.run` (via `_fetch_requests` and `_build_vehicle_configs`)
PROBLEM: `_provider_map()` (`db.query(Provider).all()`) is called independently by `_fetch_requests()` and `_build_vehicle_configs()`, both of which run unconditionally inside every `run()` call, so the full `Provider` table is fetched twice per `/api/orchestration/optimize` request.
EVIDENCE:
```
# engine/optimizer.py, lines 39-42
def _provider_map(self) -> Dict[int, Optional[Provider]]:
    """One query for all providers instead of one per request/vehicle."""
    rows = self.db.query(Provider).all()
    return {p.id: p for p in rows}
```
Called from `_fetch_requests` (line 23: `providers = self._provider_map()`) and again from `_build_vehicle_configs` (line 46: `providers = self._provider_map()`), both invoked from `run()` (lines 62-72: `requests = self._fetch_requests()` then `vehicle_configs = self._build_vehicle_configs()`).
SEVERITY: Low
EXPECTED BENEFIT: Removes one redundant full-table `Provider` scan per `/api/orchestration/optimize` call (the docstring's own stated goal — "one query for all providers instead of one per request/vehicle" — is only half achieved, since it's still one query per *caller*, not one per run).
RISK: None beyond ensuring the passed-in map does not go stale between the two uses (it cannot, within a single synchronous `run()` call).
RECOMMENDED FIX: Compute `providers = self._provider_map()` once in `run()` and pass it as a parameter into `_fetch_requests(providers)` and `_build_vehicle_configs(providers)`.

---

### 11. Driver/vehicle create & update endpoints re-run the full list query to return the object they just wrote

FILE: `backend/app/api/routes/drivers.py`
FUNCTION: `create_driver`, `update_driver`, `create_vehicle`, `update_vehicle`
PROBLEM: After creating or updating a `Driver`/`Vehicle` row (and already holding the fully up-to-date ORM object via `db.refresh()`), each handler re-invokes the corresponding `driver_service.get_drivers`/`get_vehicles` list method — which itself carries the full-table Provider/Vehicle/Driver scan described in Finding 4 — just to re-serialize the single row it already has in hand.
EVIDENCE:
```
# drivers.py, lines 47-61 (create_driver)
driver = Driver(**data.model_dump())
db.add(driver)
db.commit()
db.refresh(driver)
log_system_notification(...)
return driver_service.get_drivers(db, search=str(driver.id), limit=1)[0]
```
The same pattern recurs at line 101 (`update_driver`), line 174 (`create_vehicle`), and line 189 (`update_vehicle`) in the same file.
SEVERITY: Low
EXPECTED BENEFIT: Avoids re-running the filtered `get_drivers`/`get_vehicles` query (plus its own Provider/Vehicle full-table lookups, Finding 4) on every single create/update call, when the caller already holds the just-written row.
RISK: `get_drivers`/`get_vehicles` compute derived display fields (`provider_name`, `assigned_vehicle_name` / `current_driver_name`) that the raw ORM object does not carry directly — a direct-serialization replacement must look up those same one or two names itself (e.g. via the already-loaded `provider`/`assigned_vehicle` relationship) rather than dropping them from the response.
RECOMMENDED FIX: Factor the per-row dict-building logic in `get_drivers`/`get_vehicles` (the `providers.get(...)`/`vehicles.get(...)` lookups and field mapping) into a small single-row helper that both the list method and the create/update handlers can call directly on the one object they already have, instead of routing every mutation response through the full list query.

---

### Note: `app/engine/explainability.py` appears unused

FILE: `backend/app/engine/explainability.py`
A repository-wide search found no import of this module from anywhere in `backend/app` (the string "explainability" appears elsewhere only in docstrings/comments of unrelated files — `dmfe/compatibility.py`, `dmfe/adaptive/learning.py`, `dmfe/adaptive/factors.py`, `dmfe/adaptive/context.py` — none of which import `app.engine.explainability`). By contrast, `app/engine/optimizer.py` (the legacy `AIOrchestrator`) **is** actively used by `app/api/routes/orchestration.py`, and `app/engine/distance.py` is used throughout the DMFE core. This is noted here per the audit's scope instructions; full dead-code classification and removal analysis is left to a separate dead-code audit and is not treated as a performance finding above.

---

## Categories With No Findings

- **Unnecessary or duplicate OR-Tools solver invocations** — not found. `RouteOptimizer.optimize_trip` (`dmfe/optimizer.py`) already special-cases the single-request case to skip the solver entirely (`_build_single_route`, lines 339-349, with an explicit comment: "OR-Tools (model build + 4s search) is pure overhead here"), and `_solve_pdp` builds its arc-cost/time matrices once before the search rather than recomputing per-callback. No code path was found calling `_solve_pdp` or `SolveWithParameters` more than once for the same trip outside its documented single retry-on-infeasible-time-dimension fallback (lines 762-772), which is a deliberate graceful-degradation retry, not a redundant duplicate call.
- **Excessive/inefficient serialization (redundant `.dict()`/`.json()` calls)** — not found as a distinct issue. `app/dmfe/serializers.py` is explicitly structured as a single-source-of-truth serialization layer, and callers that iterate batches (`dmfe_v2.list_batches`) already prefetch and pass a `request_by_id` map into `batch_to_dict` specifically to avoid re-serializing/re-querying per row (lines 156-171 of `dmfe_v2.py`).
- **Blocking/synchronous work inside `async def` FastAPI route handlers** — not found. Every route handler across the 11 audited route files is declared `def`, not `async def` (FastAPI runs sync `def` handlers in a thread pool automatically), including the ones that do blocking work such as `bcrypt.checkpw` (`auth.py`) and the outbound `requests.get(...)` call to the Google Maps Distance Matrix API (`dmfe/optimizer.py`, `_google_distance_matrix`, called synchronously from `optimize_trip`). No `async def` route was found performing blocking I/O directly on the event loop.
- **Missing indexes implied by query patterns** — not found as a distinct gap beyond what's already indexed. The columns most frequently filtered on in hot paths (`SimulationRequest.status`, `Driver.status`, `Vehicle.status`, `Trip.status`, `SystemConfig.key`) are either unique-indexed (`SystemConfig.key`) or plain String columns without a dedicated index; given this is a SQLite development database (`db/database.py`) sized for a demo/research workload rather than a specified production row-count target, no evidence in the audited scope (e.g. an explicit slow-query report or table-size assumption) supports recommending specific new indexes — flagging this without such evidence would violate the "no fabricated numbers" standard this audit follows.
