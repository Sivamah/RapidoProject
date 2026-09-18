# Operations Map — Architecture, Data Integrity and Page Separation

**Date:** 2026-09-06
**Scope:** Overview / Live Operations / AI Insights map surfaces, the operational
data they consume, request + fleet semantics, route rendering, and
evidence-backed performance work.
**Untouched:** A-DMFE, DMFE, OR-Tools, compatibility rules, batching, vehicle
assignment, provider logic, simulation logic. No decision, weight, threshold or
constraint was altered.

> The three screenshots referenced in the brief did not arrive with the message
> (the upload folder held only this session's own staged files). Every finding
> below was therefore reproduced directly — in the DOM of the running
> application, against the live database — rather than read off an image.

---

## 1. Architecture findings

| Page | Route | Component | What it actually rendered |
|------|-------|-----------|---------------------------|
| Overview | `/dashboard` | `Dashboard.jsx` | full-bleed `LiveMapContainer` + KPI strip + activity ticker |
| Live Operations | `/live-map` | `LiveSimulationMap.jsx` | full-bleed `LiveMapContainer` + KPI bar + filters + inspector |
| AI Insights | `/xai` | `ExplanationDashboard.jsx` → `XaiMapPanel` → `LiveMapContainer` | decision cards + map |

All three mounted the **same** `LiveMapContainer` fed by the **same single
endpoint** — `/api/simulation/queue`, i.e. pending requests only.

Data flow, as built:

```
mock_adapters (synthetic demand)
   └─ SimulationRequest ──┬─ /simulation/queue ──────────► every map (only feed used)
                          ├─ CompatibilityCalculator ─► DecisionEngine ─► BatchGenerator
                          │      └─ RouteOptimizer (OR-Tools PDP) ─► stop_order
                          │             └─ Trip.stop_order_json  (NO coordinates)
                          ├─ /api/dmfe/trips     ──────► (unused by any map)
                          ├─ /api/vehicles/locations ──► (unused by any map)
                          └─ xai_service ─► /api/xai/explanations ─► XaiMapPanel
```

Road geometry is a **display-only** concern fetched client-side (Google
Directions when a key is present, otherwise OSRM). The backend produces no
geometry — only the OR-Tools stop *sequence* and a distance/duration matrix.

---

## 2. Root causes

### 2.1 "Map layered over old dashboard UI" — a stacking-context defect

**ROOT CAUSE.** The `LiveMapContainer` wrapper computed to
`position:absolute; z-index:auto; isolation:auto` (measured via
`getComputedStyle` in the running app). It established **no stacking context**,
so Leaflet's internal panes — `marker-pane 600`, `tooltip-pane 650`,
`popup-pane 700` — competed with the page's own `z-10/20/30` overlays inside the
**same** context and won.

**IMPACT.** Map panes painted through and over the floating glass panels,
producing the "remnants underneath the map" appearance.

**FIX.** `isolation: isolate` on the wrapper, confining Leaflet's 200–700 range
to that subtree. Nothing was hidden with opacity; no component was stale or
double-mounted.

**REGRESSION TEST.** The DOM probe asserts `isolation === "isolate"` on all
three pages.

### 2.2 One genuinely broken remnant: the Overview activity feed

**ROOT CAUSE.** `Dashboard.jsx` rendered `event.type` and `event.message`.
`/api/notifications/timeline` returns
`{id, time_str, title, description, category, request_id, created_at}` —
neither field exists.

**IMPACT.** The ticker rendered timestamps followed by empty strings: ghost text
under the map.

**FIX.** Bound to the real fields (`time_str`, `title`, `description`), with an
explicit empty state.

**REGRESSION TEST.** Validation asserts `/Request #\d+ created/` appears in the
Overview DOM.

### 2.3 A regression I introduced in the previous session

**ROOT CAUSE.** I changed `TripDetailsPanel`'s prop contract for the Live Map
without auditing every call site. `Dashboard.jsx` still passed the old
`request={…}` signature.

**IMPACT.** Overview's inspector rendered its "nothing selected" placeholder
permanently.

**FIX.** Overview must not be a single-trip inspector at all, so the panel was
removed from that page rather than re-patched; Live Operations keeps it with the
correct contract.

### 2.4 The maps were structurally incapable of showing the network

**ROOT CAUSE.** Only `/simulation/queue` was ever fetched. `/api/vehicles/locations`
(115 vehicles) and `/api/dmfe/trips` (active trips with full `stop_order`)
existed and were unused.

**IMPACT.** Measured before the change: Overview and Live Operations each
rendered **5 markers, 0 vehicles, 0 trips, 0 routes**.

**FIX.** New `useOperationalNetwork` hook fetching fleet + active trips + queue,
plus `FleetLayer` and `ActiveTripsLayer`.

### 2.5 Active trips could never be drawn — a data-join defect

**ROOT CAUSE.** `trips.stop_order_json` stores `(request_id, action,
arrival_min)` with **no coordinates**. My first `ActiveTripsLayer` resolved them
client-side against `/simulation/queue` — which by definition contains only
*pending* requests, while a dispatched trip's requests are Assigned. Verified
against live data: the active trip referenced request **3855**; the queue held
**3890–3894**. Zero overlap, by construction.

**IMPACT.** Zero active corridors could ever render, on any page.

**FIX.** Resolve server-side in `serializers.resolve_stop_coordinates`, the same
pattern `xai_service._build_trip_link` already used. Purely additive — `lat`,
`lng` and `request_type` are added to each stop; ordering untouched; an
unresolvable stop keeps its original shape with no invented coordinates. One
indexed `IN` lookup per response.

**REGRESSION TEST.** Validation asserts every stop of every active trip carries
coordinates and that corridors render on both network pages.

### 2.6 Viewport drifted during polling — but only with a popup open

**ROOT CAUSE.** Leaflet `Popup` defaults to `autoPan: true` and re-runs its
auto-pan whenever an open popup re-renders. The queue poll rebuilds request
objects every few seconds, so an open popup nudged the viewport on every tick.

**IMPACT.** The map crept away from where the operator had panned it.

**FIX.** `autoPan={false}` on both Leaflet popups. The viewport now moves only
when the selected route's geography changes or the operator presses
Fit / Recenter.

**REGRESSION TEST.** A probe pans the map, then samples
`.leaflet-map-pane` transform across ~3 poll cycles, with and without an open
popup. Isolated deliberately: with no selection the map was already stable, so
the defect was popup-specific.

### 2.7 Basemap too dark to verify route alignment

**ROOT CAUSE.** Leaflet filter `brightness(0.62) contrast(0.92)`; Google style
painted roads `#0f172a` on a `#0A0F1A` ground — roughly 2% apart.

**IMPACT.** A cyan route could not be checked against the street it claimed to
follow, which defeats the purpose of road-following geometry.

**FIX.** Ground stays dark navy; roads lifted to `#26334A`, arterials `#33425E`,
highways `#3E5175`; Leaflet filter retuned to
`brightness(0.82) contrast(1.06)`. Labels stay muted so overlays remain
brightest.

### 2.8 Fabricated operational values

| Site | Was | Now |
|------|-----|-----|
| `driver_service.get_vehicle_locations` | `v.current_lat or SAMPLE_COORDINATES[i % 6]` — a vehicle with no recorded position placed on a canned landmark, indistinguishable from a real one on the operations map | vehicles without a usable coordinate are **omitted** and the count logged |
| same | `registration_number or f"TN-37-{v.id}"` | reported as-is, empty when unknown → UI shows "—" |
| `VehicleTable.jsx` | new-vehicle form pre-filled `TN-37-X-${Math.random()}` | blank; the operator types the real plate |

Deliberately left alone: `mock_adapters.py` (the synthetic demand generator —
that is the research methodology, not a displayed value) and
`AnimatedBackground.jsx` (decorative particles).

---

## 3. Files modified

**Backend (3)** — `app/services/driver_service.py`,
`app/dmfe/serializers.py`, `app/api/routes/dmfe_engine.py`.

**Frontend — new (4)** — `hooks/useOperationalNetwork.js`,
`components/map/FleetLayer.jsx`, `components/map/ActiveTripsLayer.jsx`,
plus fleet/cluster icon factories in `components/map/markerIcons.js`.

**Frontend — modified (10)** — `pages/Dashboard.jsx` (rewritten),
`pages/LiveSimulationMap.jsx`, `components/map/LiveMapContainer.jsx` (rewritten),
`components/map/TripDetailsPanel.jsx`, `components/map/XAIHighlightLayer.jsx`,
`components/map/KpiBar.jsx`, `components/xai/XaiMapPanel.jsx`,
`components/drivers/VehicleTable.jsx`, `utils/requestSemantics.js`,
`utils/xaiMap.js`, `index.css`.

---

## 4. Correctness fixes and design

**Page separation** is expressed as a `mode` on one map engine, not three
divergent copies:

| mode | page | fleet | corridors | dimming |
|------|------|-------|-----------|---------|
| `network` | Overview | deployed only | all, with geometry | off |
| `operations` | Live Operations | whole fleet, clustered | all, with geometry | on selection |
| `decision` | AI Insights | deployed only | off (selected route owns the map) | always |

Overview has **no single-trip inspector** and no selection handlers.

**Semantics** — one authoritative source (`utils/requestSemantics.js`):
ride = blue + passenger, food = orange + plate, parcel = purple + parcel-box,
unknown types keep their own label in neutral slate. Every marker encodes four
channels — shape (pickup pin / drop square / vehicle chassis / cluster badge),
colour (type), glyph (type), number (position in the OR-Tools sequence) — plus a
text label in tooltips and panels. **Never colour alone.** Fleet status rides a
separate ring: on-trip green, available cyan, maintenance amber, offline red.

**Route vs type stay separate.** The selected route is cyan at every time, for
every request type: 4.5 px core, single 13 px halo, round caps and joins, arrows
every 110 px. Other active corridors are thin desaturated teal (`#2A7A8C`) so
they read as context. When no provider can route the stops, the layer draws a
**dashed slate line** and says *"Road geometry unavailable"* — a straight-line
approximation is never presented as the trip.

**Layer order** implemented: basemap → active corridors (z20) → fleet (z28–30) →
requests (z10–20) → route halo (z40) → route core (z42) → arrows (z43) →
operational stops (z55–60) → selection → popups.

**Fleet clustering.** The seeded fleet parks many vehicles on near-identical
coordinates; at network zoom 110 markers rendered as one unreadable glow.
Co-located vehicles now group into an exact counted badge coloured by dominant
status; clicking zooms in and splits them. Nothing is hidden — counts sum to the
full fleet — and clustering dissolves at street level.

---

## 5. Performance work, and why each was needed

| Change | Evidence it was needed | Result |
|--------|------------------------|--------|
| Coordinate-fingerprint keys for route fetch and viewport fit | route fetches previously re-issued on object identity | **0 route requests across 5 idle poll cycles** (measured) |
| `autoPan={false}` on popups | viewport drifted `-180px → -100px` across 3 polls with a popup open | transform **identical** across 3 polls |
| Memoised marker/cluster/vehicle icons keyed by visual identity | every data-URI and DivIcon was rebuilt each poll tick, forcing Leaflet to re-create the marker layer | icons built once per distinct appearance |
| Shared `useOperationalNetwork` through the existing `api.js` GET cache | three layers mounting at once would otherwise issue three copies of each request | one call per endpoint per tick |
| Server-side stop-coordinate resolution | replaced an impossible client-side join with one indexed `IN` query | corridors render; no per-trip client lookups |
| Fleet clustering | 115 individual markers at network zoom | 115 vehicles drawn as **13 map objects**, all still represented |

Carried over from the previous session and re-verified: lazy A-DMFE context and
lazy trip index in `xai_service` (warm `/api/xai/explanations?limit=200`:
**77–97 ms → 6–8 ms**, output proven byte-identical over 40 explanations).

No research-critical optimization behaviour was changed.

---

## 6. Validation results

Run against the real backend and a copy of the live database, with the routing
provider stubbed two ways so both branches are deterministic: `road` returns
multi-vertex geometry that deliberately deviates from the straight line, `fail`
returns 503. Active trips were produced by **running the real A-DMFE + OR-Tools
dispatch pipeline** (`POST /api/dmfe/run`), not by hand-editing rows.

| Check | Result |
|-------|--------|
| No duplicate/obsolete layers; stacking fixed | `isolation: isolate` on all three pages ✓ |
| Overview ≠ Live Operations | network: 4 corridors + deployed only, no inspector · operations: 4 corridors + full fleet + inspector ✓ |
| Map populated from real data | 115 vehicles (13 objects after clustering), 4 active trips, 6 pending requests ✓ |
| Request semantics | 4×`#3B82F6` ride, 1×`#A855F7` parcel, 1×`#F97316` food — matches API `{ride:4, parcel:1, food:1}` ✓ |
| Batched stop order (mixed ride+parcel `BATCH-3899-3900`) | `org · pin1 blue · pin2 purple · sqr3 purple · sqr4 blue` — matches `stop_order` `[(3900,pickup),(3899,pickup),(3899,drop),(3900,drop)]` exactly ✓ |
| Batched food batch, individual trip, standalone | correct sequence and colours in each ✓ |
| Road-following geometry | cyan 4.5 px core + 13 px halo, round caps, **39–69 vertices** — provider geometry, not the stop list ✓ |
| Routing failure | single dashed `#64748B` 3 px `4 10` line, vertex count = stop count, **no cyan route**, UI states geometry unavailable ✓ |
| Missing coordinates | vehicles without a position omitted; unresolvable stops dropped, none invented ✓ |
| Selection focus | unrelated request markers drop to opacity 0.5, selected stays 1.0 ✓ |
| Inspector footprint | mounts only when something is selected ✓ |
| Viewport during polling | transform identical across 3 poll cycles after panning ✓ |
| Route requests when idle | 0 across 5 poll cycles ✓ |
| Invalid request (`xai=999999`) | clean error state with Dismiss ✓ |
| Fabricated-value sweep (11 strings, all three pages) | all absent ✓ |
| Page errors | none ✓ |
| Static | pytest **73 passed** · oxlint **0 errors** (37 → 1 warning) · vite build clean |

The single remaining lint warning is `react(only-export-components)` in
`context/AuthContext.jsx`, untouched by this work.

---

## 7. Remaining risks

1. **OSRM is a public best-effort service.** Failure now degrades visibly and
   retries after 30 s, but geometry still depends on a third party. Set
   `VITE_GOOGLE_MAPS_API_KEY` to switch to Google Directions, or self-host OSRM,
   if road shape matters for the evaluation.
2. **Fleet positions are static.** Nothing in `app/` writes `current_lat`/`current_lng`
   after seeding, so "vehicle position" is the depot the optimizer used. Correct
   for this dataset; revisit if live tracking is added.
3. **Traffic and feasibility overlays are specified in the layer hierarchy but
   not implemented** — no endpoint supplies either, and inventing them would
   violate the data-integrity rule. The z-order leaves room at 25 and 30.
4. **`XAIFactors` Pydantic defaults** (85.0 / 89.5 / 90.0) remain. Unreachable
   today because the service sets every field, but a future field added without
   an explicit assignment would inherit a flattering constant. Recommend
   switching to `0.0`/`""` in a dedicated change.
5. **Compatibility scores drift between polls** (e.g. 77.5% → 77.7%) because the
   A-DMFE learning engine adapts and explanations cache for 30 s. Genuine engine
   behaviour, but worth noting before quoting a single figure in the paper.
6. **`/api/vehicles/locations` may now return fewer rows** than before for
   deployments where vehicles lack coordinates. This is the fabrication fix
   working as intended; fleet composition still comes from `/api/vehicles`.
7. **Line endings.** The working tree still shows near-universal CRLF/LF churn
   from the Windows checkout. Add `.gitattributes` before committing so the real
   diff stays readable.

---

# Addendum — audit follow-up (basemap, dimming, popups, Overview KPIs)

## Files changed

| File | Change |
|------|--------|
| `frontend/src/components/map/LiveMapContainer.jsx` | Basemap source made configurable (`VITE_MAP_TILE_*`); dimmed queue markers drawn smaller |
| `frontend/src/index.css` | Basemap treatment replaced (measured); Leaflet popup chrome restyled to A-DMFE dark glass |
| `frontend/src/components/map/markerIcons.js` | Semantic colour preserved under dimming (stop, queue, vehicle and cluster markers) |
| `frontend/src/components/map/RequestMarkers.jsx` | Dimmed markers drawn smaller |
| `frontend/src/hooks/useOperationalNetwork.js` | Fleet composition fetch + KPI derivations |
| `frontend/src/pages/Dashboard.jsx` | Six KPI cards; "CO₂ saved" reverted to "CO₂ Reduction" |
| `frontend/.env.example` | Basemap override documented |

No backend file was touched in this round.

## KPI sources and calculations

| Card | Source | Calculation |
|------|--------|-------------|
| **Combined Vehicles** | `GET /api/vehicles/stats` → `total_vehicles` | `COUNT(Vehicle.id)` — the whole registered fleet, every status, whether or not it currently reports a position. Deliberately NOT the length of `/vehicles/locations`, which excludes vehicles without a coordinate; that figure is shown as the "reporting position" sub-label. |
| **Available Vehicles** | `GET /api/vehicles/stats` → `available_vehicles` | `COUNT` where `lower(status) = 'available'` |
| **Active Requests** | `/api/simulation/queue` + `/api/dmfe/trips?status=Active` | `len(queue) + |{request_id on an Active trip}|`. Stop lists name each request twice (pickup + drop), so ids are deduplicated. = requests the network holds and has not completed. |
| **Ongoing Rides** | `/api/dmfe/trips?status=Active` | deduplicated in-flight requests with `request_type = 'ride'` |
| **Deliveries** | `/api/dmfe/trips?status=Active` | deduplicated in-flight requests with `request_type ∈ {food, parcel}` |
| **CO₂ Reduction** | `GET /api/dashboard/stats` → `co2_reduction` | `SUM(Trip.co2_saved_kg)` |

Verified against the API in the same session: 115 / 101 / 25 / 6 / 16 / 1,850 kg — card values matched exactly.

## Basemap — requirement only PARTIALLY met

Three options were measured on real data, not assumed.

1. **CARTO dark_all / dark_nolabels — REJECTED.** Every anonymous tile is stamped
   "API KEY REQUIRED" diagonally across the image (confirmed visually on three
   separate tiles). It cannot ship without a key.
2. **Filtered OpenStreetMap — SHIPPED, with a known ceiling.** `invert()` flips
   OSM's polarity: OSM draws roads *lighter* than land, so inverting makes them
   *darker* than land. Eleven filter variants were measured against OSM Carto's
   documented palette; minor roads never exceeded ~1.3:1 against land. That
   ceiling is inherent to filtering a light basemap into a dark one.
3. **Navy tint via `mix-blend-mode: color` — TRIED AND REJECTED.** On an isolated
   bench it worked (land rgb(37,50,76), road ladder intact). Measured *inside
   Leaflet's actual tile pane* it blended against the pane backdrop instead of
   the tiles and flattened every road class to ~1.1:1. Not shipped.

**Shipped:** `invert(1) hue-rotate(185deg) brightness(1.32) contrast(0.74) saturate(0.5)`
— a shadow *lift* rather than a crush.

| | minor | primary | motorway | water | land |
|---|---|---|---|---|---|
| previously shipped | 1.07 | 1.15 | 1.78 | 1.27 | rgb(20,19,17) |
| intermediate attempt | 1.04 | 1.17 | 2.25 | 1.35 | rgb(7,6,3) |
| **now** | **1.24** | **1.40** | **3.03** | **1.72** | not crushed |

Major roads are now clearly distinguishable from minor ones. The ground reads as
a cool dark slate rather than deep navy, and minor roads remain the weak step.

**The real fix is a native dark tileset**, which needs a (free) key. The source is
now configurable, so switching is one line in `.env` and no code change:

```
VITE_MAP_TILE_URL=https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png?api_key=YOUR_KEY
VITE_MAP_TILE_SUBDOMAINS=abcd
VITE_MAP_TILE_TREATMENT=native      # bypasses the filter entirely
```

## Validation

| Check | Result |
|---|---|
| KPI cards vs API | 115 / 101 / 25 / 6 / 16 / 1,850 kg — exact match ✓ |
| Ride/Food/Parcel colour when DIMMED | `#3B82F6 / #F97316 / #A855F7` at opacity 0.45, 24px; **0 markers turned slate** ✓ |
| Ride/Food/Parcel colour when SELECTED | type colour at opacity 1.0, 34px ✓ |
| AI Insights background markers | keep type colour (were uniformly slate) ✓ |
| Popup chrome | `rgba(10,15,26,0.92)`, text `rgb(230,236,245)`, 16px radius, 18px blur ✓ |
| Popup z-index | pane still 700, confined by the map wrapper's `isolation: isolate` ✓ |
| Active route | `#00F0FF`, 4.5px core + 13px halo, round caps ✓ |
| Basemap filter applied to base layer only | tile-pane filter `none`; base layer carries the treatment ✓ |
| Backend tests | 73 passed ✓ |
| Frontend build | clean ✓ |
| Lint | exit 0 (no errors); 1 pre-existing warning in `context/AuthContext.jsx` ✓ |
| Page errors | none ✓ |

Note: `tests/test_datasets_upload.py` errors when run from the Windows-mounted
folder with `sqlite3.OperationalError: disk I/O error` on `PRAGMA journal_mode=WAL`.
That is the FUSE mount refusing WAL, not a code fault — the same test passes on a
native filesystem.

## Not done, deliberately

Traffic and feasibility overlays — the audit confirmed no data source exists for
either, and inventing one would breach the data-integrity rule. The layer stack
leaves room at z 25 and 30.
