# Live Map / XAI Route Visualization — Implementation Report

**Date:** 2026-09-06
**Scope:** operations map route rendering, request-type semantics, XAI data integrity,
selection wiring, and evidence-based performance work.
**Explicitly out of scope (unchanged):** A-DMFE, DMFE, OR-Tools, compatibility
scoring, batching, driver/vehicle selection, assignment, pipeline, simulation,
provider logic, database schema, and every backend API contract.

---

## 1. Root causes found

### 1.1 What the system actually considers the authoritative route

`grep -i "polyline|geometry|osrm|geojson"` over `backend/app/` returns one
docstring and nothing else: **the backend produces no route geometry at all.**

What OR-Tools produces (`RouteOptimizer.optimize_trip` →
`OptimizedRoute.stop_order`) is an **ordered stop sequence**
`(request_id, action, arrival_min)`, persisted to `trips.stop_order_json`
*without coordinates* (`driver_selection.create_assignment`). Coordinates are
re-attached server-side in `xai_service._build_trip_link` from the
`SimulationRequest` rows. The depot handed to the solver is the assigned
driver's current location, falling back to the vehicle's
(`optimizer.optimize_trip`, "Depot = driver location → vehicle location").

Verified against the live database (`dmfe_dev.db`: 3,886 requests, 2,628 trips,
1,255 of them shared), e.g. `BATCH-3881-3887`:

```
[{3887,pickup,8.5}, {3881,pickup,11.7}, {3887,drop,26.9}, {3881,drop,53.6}]
```

**Therefore the authoritative operational route is:**

```
driver/vehicle position  →  stop_order[0] → … → stop_order[n]
```

Road geometry is a *display* concern only. The map fetching it client-side is
architecturally correct and duplicates nothing — the backend never computes a
shape, only a distance/duration matrix for the solver.

**Classification of the reported defect: (C) — a simplified endpoint route,
produced by silent degradation, with a permanent cache poisoning it.**

### 1.2 The two mechanisms that produced straight lines

**(a) StrictMode-cancelled fetch — deterministic, fires on every first
highlight.** `useRoadRoute` guarded its effect with `lastKeyRef`. React 19
StrictMode (enabled in `main.jsx`) mounts every effect twice in development:
run 1 set the ref and started the fetch, cleanup set `cancelled = true`, run 2
saw an unchanged ref and returned **without fetching**. The result was
discarded and no retry ever happened. Because the hook seeded its state with
the raw waypoints, the user was left looking at a straight-line polyline
permanently. Reproduced in a headless browser: `/live-map?xai=3887` issued one
OSRM request and rendered **zero** route paths for 31 s.

**(b) Permanently cached failure.** `routeUtils.fetchRoadRoute` fell back to the
raw waypoints when both providers failed and stored that fallback in
`_routeCache` **forever**. A single OSRM timeout (8 s) or outage replaced a
trip's road route with straight lines for the lifetime of the tab, with no
retry, no error state and nothing in the UI to distinguish it from a real
route.

### 1.3 Other root causes

| # | Severity | Finding |
|---|----------|---------|
| 1 | **Blocker** | `xai_service._generate_explanation_for_request` bound `confidence` only inside the `result is None` branch. In **static DMFE mode** (`admfe.mode = static`, the Phase 9 research baseline) `result` is present and `decision_confidence` is None → `UnboundLocalError` → `/api/xai/explanations` returned 500 for the entire baseline configuration. Reproduced under pytest. |
| 2 | **Critical** | `TripDetailsPanel` declared `{ request, onClose }`; `LiveSimulationMap` passed `{ selectedRequest, xaiHighlight, xaiLoading, xaiError, onCloseTrip, onDismissXai }`. The Live Map inspector was permanently stuck on its placeholder and `/live-map?xai=` rendered no explanation at all. |
| 3 | **Critical** | Fabricated values on screen — see §3. |
| 4 | **High** | Six mutually contradictory request-type palettes. The live marker layer (`MARKER_COLORS`) painted **food and parcel identical purple** and ride orange, while `XAIHighlightLayer` on the *same map* used ride-blue / food-orange / parcel-purple. Markers carried no type glyph, so type rested on colour alone. `TYPE_META`, `PICKUP_COLOR`, `DROP_COLOR` in `XAIHighlightLayer` were declared and never used. |
| 5 | **High** | Pickup and drop-off used the identical icon and colour, and no stop carried a sequence number — the vehicle→P1→P2→D1→D2 flow was invisible even though the ordering data was correct. |
| 6 | **Medium** | `LiveMapContainer` re-ran `fitBounds` on every `xaiHighlight` *object identity* change, i.e. every 2.5 s poll, snapping the viewport back while the operator panned. |
| 7 | **Medium** | `useRoadRoute` recomputed its waypoints three times per render; every marker icon (`L.divIcon` / data-URI SVG) was rebuilt on every poll tick; `get_explanations` built the A-DMFE context and scanned all 2,628 trips on every call even when every explanation was a cache hit. |

---

## 2. Files changed

### Backend (1 file)

| File | Change |
|------|--------|
| `app/services/xai_service.py` | Bind `confidence` on every path (crash fix); make the A-DMFE context and the trip index lazy. |

### Frontend — new

| File | Purpose |
|------|---------|
| `src/utils/requestSemantics.js` | Single source of truth for type colour + icon + label, route colours, state colours, stop roles. |
| `src/utils/operationalRoute.js` | Reconstructs the authoritative stop sequence (origin + OR-Tools order) and its stable coordinate fingerprint. |
| `src/hooks/useOperationalRoute.js` | Resolves that sequence into drawable geometry with an explicit status. |
| `src/components/map/markerIcons.js` | Memoised operational + queue marker icons (shape/colour/glyph/number) for both map modes. |

### Frontend — modified

`src/utils/routeUtils.js` (rewritten), `src/utils/xaiMap.js`,
`src/components/map/XAIHighlightLayer.jsx` (rewritten),
`src/components/map/TripDetailsPanel.jsx` (rewritten),
`src/components/map/LiveMapContainer.jsx`, `src/components/map/RequestMarkers.jsx`,
`src/components/map/MarkerPopup.jsx`, `src/components/map/KpiBar.jsx`,
`src/components/map/ActivityBar.jsx`, `src/components/xai/DecisionCard.jsx`,
`src/components/xai/XaiMapPanel.jsx`, `src/pages/ExplanationDashboard.jsx`,
`src/index.css`.

### Tests — new

`backend/tests/test_xai_static_mode.py` — regression cover for the static-mode crash.

---

## 3. Functional changes

**Route rendering.** The map now draws the operational sequence built by
`buildOperationalRoute`: the assigned vehicle's position (included **only** when
a trip was actually dispatched) followed by the OR-Tools `stop_order`, verbatim
and never reordered. Road geometry is requested for that waypoint list and
rendered as the cyan active route. When no provider can route the stops the
layer switches to a **dashed, muted, thin** line and states
*"Road geometry unavailable — stops shown as a direct connection."* A
straight-line approximation is never presented as the physical trip.

**Request-type semantics.** Every surface now reads from
`requestSemantics.js`: ride = blue + person, food = orange + plate,
parcel = purple + parcel-box, unknown types = neutral slate keeping their own
label. Markers encode four independent channels — shape (pickup pin / drop
square / vehicle circle), colour (type), glyph (type), number (position in the
OR-Tools sequence) — plus a text label in the tooltip and panels, so meaning
never rests on colour alone. The **active route stays cyan regardless of request
type**, keeping "what kind of operation is this?" and "which route is selected?"
as separate questions.

**Selection wiring.** `TripDetailsPanel` now matches the props
`LiveSimulationMap` passes, restoring the Live Map inspector and the
`/live-map?xai=` deep link. Existing state management was reused; no second
selection system was introduced.

**Fabricated values removed.**

| Site | Was | Now |
|------|-----|-----|
| `XaiMapPanel:58-59` | `'8.4 km'`/`'3.2 km'`, `'24 min'`/`'12 min'` — and since the XAI schema has no `estimated_time_min` field, the ETA was **always** one of the two constants | real `estimated_distance_km`; trip time = final stop's `arrival_min` from the optimizer's own stop order; `—` when absent |
| `TripDetailsPanel:20,42` | `Math.random()` A-DMFE score and vehicle ID | removed |
| `TripDetailsPanel:90,96` | `'3.2 km'` / `'12 min'` | real values or `—` |
| `TripDetailsPanel:108-119` | three hardcoded XAI bullets ("adding only 1.2km detour") | the engine's own `key_reasons`, or an explicit "no rationale recorded" |
| `XAIHighlightLayer:171-186` | hardcoded fallback reasons | same as above |
| `XAIHighlightLayer:155,158` | default text "Compatible for Batching"; compatibility score **labelled "Confidence"** | the engine's decision; compatibility and confidence shown as separate, correctly-labelled figures |
| `ExplanationDashboard:258-259` | `\|\| 85` / `\|\| 90` (which also swallowed a genuine 0) | `?? … ?? 0` |
| `DecisionCard:16` | `confidence_score \|\| 90` | real value or `—` |

---

## 4. Performance optimizations, and why each is justified

Only changes backed by a measurement or a reproduced defect were made.

### 4.1 Backend — lazy A-DMFE context and trip index

*Evidence (live dev DB, `limit=200`, fresh Session per call, warm cache):*

| | before | after |
|---|---|---|
| `_build_compute_kwargs` | 44 ms | 0 ms (not called) |
| `db.query(Trip).all()` (2,628 rows) | 22 ms | 0 ms (not called) |
| **warm poll total** | **77–97 ms** | **6–8 ms** |

86% of a warm poll was spent building inputs that every cache hit discarded.
Both are now built at most once per call, on the first cache miss.

*Research integrity:* identical inputs, identical computation, merely deferred.
Proven by generating 40 explanations through both paths and comparing the full
serialized payloads — **byte-identical, 0 field differences.**

### 4.2 Route requests — honest cache + in-flight dedup + coordinate keying

Successful geometry is cached indefinitely (a dispatched trip's stop sequence is
immutable, so its shape is too); **failures are cached for 30 s only**, so a
transient outage no longer poisons a route permanently. Concurrent callers share
one in-flight promise. The hook keys on the waypoint *fingerprint*, not object
identity.

*Measured:* `/live-map?xai=3887` held open for 31 s (≈12 queue-poll cycles) —
**1 routing request total, 0 during 5 idle poll cycles.**

### 4.3 Viewport stability

`fitBounds` now keys on the coordinate fingerprint. *Measured:* after panning,
the viewport transform is unchanged across 4 poll cycles (`translate3d(-300px,
-200px, 0px)` before and after); previously it re-fit ~24×/minute.

### 4.4 Marker icon memoisation

Icons are cached by `(role, colour, type, sequence, dimmed, size)`. Previously
every data-URI SVG and every `L.divIcon` was rebuilt on each 2.5 s tick, which
made Leaflet tear down and re-create the whole marker layer.

### 4.5 Redundant work removed

`useOperationalRoute` computes its waypoints once per render via `useMemo`
(was: three times — initial state, effect body, dependency array).

---

## 5. Intentionally NOT changed

- **A-DMFE / DMFE / OR-Tools / compatibility / batching / driver selection /
  assignment / pipeline / simulation / provider logic** — untouched. No
  objective, constraint, weight, threshold or feasibility rule was altered.
- **Backend API contracts and the database schema** — unchanged. The only
  backend edit is inside `xai_service`, and its output is byte-identical apart
  from the previously-crashing static-mode path.
- **No routing decision was moved to the frontend.** The client fetches a
  *shape* for stops the backend already chose and ordered; `optimizeWaypoints`
  stays pinned to `false` so Google can never re-solve the OR-Tools sequence.
- **`XAIFactors` / `XAIExplanationItem` schema defaults** (`85.0`, `89.5`,
  `90.0`, `"Compatible for Batching"`) were left in place — every field is set
  explicitly by the service today, so changing them is a schema change with no
  behavioural benefit. Flagged as a residual risk in §8.
- **The 2.5 s polling interval** and the existing `api.js` GET cache — no
  evidence they are a bottleneck now that the warm poll costs 6–8 ms.
- **`normalizeXaiHighlight`'s synthesis of a pickup→drop leg** for
  un-dispatched requests — the coordinates are real; it is now *flagged* and the
  UI labels it "Planned leg — no vehicle dispatched for this request yet".
- **The 15 remaining lint warnings** — all unused imports in files unrelated to
  this work (`Dashboard.jsx` and friends). Left for the planned cleanup pass.

---

## 6. Validation performed

**Static.** `pytest`: **73 passed** (71 baseline + 2 new). `oxlint`: **0 errors**,
warnings **37 → 15**, and **zero** warnings in any file touched here.
`vite build`: clean.

**Runtime.** The real backend + frontend were run against a copy of the live
`dmfe_dev.db` and driven headlessly. The routing provider was stubbed so both
branches could be exercised deterministically — `road` returns multi-vertex
geometry that deliberately deviates from the straight line, `fail` returns 503.

| Check | Result |
|-------|--------|
| Road geometry rendered | 3 cyan polylines, 36–72 vertices — provider geometry, not the 5-point stop list ✓ |
| Provider unavailable | 1 slate `#64748B` polyline, `stroke-dasharray 4 10`, 3 px, 5 vertices; **no cyan route drawn**; UI states geometry unavailable ✓ |
| Batched stop order | `BATCH-3881-3887` → `org · pin1 #F97316 · pin2 #A855F7 · sqr3 #F97316 · sqr4 #A855F7`, matching `stop_order_json` exactly ✓ |
| Mixed ride+food batch (`#3876`) | `org · pin1 orange · pin2 blue · sqr3 orange · sqr4 blue` ✓ |
| Individual parcel trip (`#3888`) | `org · pin1 purple · sqr2 purple`; real "Standalone Direct Routing" with the engine's rejection rationale (CS 47.4% vs θ_eff 61.1%, BQS 0.47 vs θ_bqs 0.57) ✓ |
| No dispatched trip (`#3893`) | **no vehicle marker invented**; stops numbered 1,2; "Planned leg" notice shown ✓ |
| Invalid request (`999999`) | clean error state with Dismiss; no page errors ✓ |
| Card ↔ map correspondence | selecting `#3887` drives header, markers, route, panel and popup to the same request ✓ |
| Operational sequence text | `Vehicle → Pickup #3887 → Pickup #3881 → Drop #3887 → Drop #3881` ✓ |
| Fabricated-value sweep | all 10 banned strings absent from the rendered DOM ✓ |
| Viewport stability | unchanged across 4 poll cycles after panning ✓ |
| Routing requests when idle | 0 across 5 poll cycles ✓ |
| Page errors | none ✓ |

---

## 7. Behavioural change requiring sign-off

**BEFORE** — when no routing provider could serve a trip, the map drew a
straight-line polyline styled identically to a real route, and cached it
permanently.
**AFTER** — it draws a dashed, muted line and states that geometry is
unavailable.
**WHY** — the previous behaviour silently misrepresented the physical route,
which is the defect under investigation.
**TRADE-OFF** — operators will occasionally see an explicitly-degraded route
where they previously saw a confident-looking wrong one.
**VALIDATION** — both branches exercised headlessly with a stubbed provider
(§6).

No other change alters system behaviour: the backend fix converts a crash into
the documented fallback, and every other edit is presentational or a
verified-equivalent deferral of work.

---

## 8. Remaining risks

1. **OSRM is a public best-effort service.** Rate limiting or an outage now
   degrades visibly and retries after 30 s rather than failing silently — but
   geometry still depends on a third party. If road shape matters for the
   evaluation, consider a self-hosted OSRM or a Google Directions key.
   `VITE_GOOGLE_MAPS_API_KEY` already switches the map to Google Directions.
2. **`XAIFactors` schema defaults** (`85.0` / `89.5` / `90.0` /
   `"Compatible for Batching"`) remain as Pydantic defaults. They are unreachable
   today because the service sets every field, but a future field added without
   an explicit assignment would silently inherit a flattering constant.
   Recommend switching them to `0.0` / `""` in a dedicated change.
3. **Driver and vehicle positions are static.** Nothing in `app/` writes
   `current_lat`/`current_lng` after seeding, so the "vehicle origin" is the
   depot the optimizer used, not a live position. Correct for this dataset;
   it will need revisiting if live tracking is added.
4. **The compatibility score drifts between polls** (e.g. 77.5% → 77.7%) because
   the A-DMFE learning engine adapts and the explanation cache has a 30 s TTL.
   This is genuine engine behaviour, not a UI artifact, but it is worth noting
   before quoting a single figure in the paper.
5. **Line endings.** The working tree shows nearly every file as modified due to
   a pre-existing CRLF/LF mismatch from the Windows checkout. Content diffs are
   confined to the files listed in §2; consider a `.gitattributes` before the
   next commit so the real diff stays readable.
