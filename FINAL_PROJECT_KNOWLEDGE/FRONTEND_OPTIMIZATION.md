# Frontend Optimization Audit

**Scope audited:** `frontend/src/` — `App.jsx`, `main.jsx`, `context/AuthContext.jsx`, all 3 files in `hooks/`, all 14 files in `pages/` (the task brief said 13; the directory actually contains 14), `services/api.js`, all 5 files in `utils/`, `components/AdminLayout.jsx`, `components/ProtectedRoute.jsx`, and every file under `components/{analytics,dmfe,map,notifications,playback,ui,xai}/`. `frontend/package.json` was read to confirm which npm packages actually exist.

**Method:** every file in scope was read in full. Every `import … from '…'` path in every page and in `App.jsx` was cross-checked against the actual file listing (`find`/`ls`) to catch broken imports — this is how the dominant finding below was discovered. Every `setInterval`, `useEffect`, and `onClick` in scope was inspected for cleanup, dependency correctness, and whether it does what its label claims.

## Summary

**Total files inspected: 60** (100% of the specified scope: `package.json` + 59 files under `frontend/src/`).

| Classification | Count |
|---|---|
| CRITICAL | 7 |
| HIGH | 2 |
| MEDIUM | 4 |
| LOW | 3 |
| **Total findings** | **16** |

The single dominant issue is structural, not a subtle performance bug: **7 of the 14 pages (half the application) import components that do not exist anywhere in the repository**, including `App.jsx` itself. This is a mismatched refactor — pages and their imports were written/kept for a component tree (`components/drivers/`, `components/config/`, most of `components/analytics/`, most of `components/dmfe/`, most of `components/notifications/`, most of `components/playback/`, `components/ui/AnimatedBackground`) that was never committed or was deleted. Everything below the CRITICAL section describes the code quality of what *does* exist, which — aside from a couple of missing-debounce bugs and some dead files — is genuinely well engineered: the polling, caching, memoization and map-rendering code shows deliberate, documented performance work (see "Categories With No Findings").

## Findings

---

### CRITICAL — App fails to load entirely: `App.jsx` imports a component that does not exist

**FILE:** `frontend/src/App.jsx`
**COMPONENT/FUNCTION:** `App` (top-level, eagerly-imported, not lazy)
**PROBLEM:** `App.jsx` statically imports `./components/ui/AnimatedBackground`, but no file of that name exists anywhere in `frontend/src`.
**EVIDENCE:**
```
7  import AnimatedBackground from './components/ui/AnimatedBackground';
...
36        <AnimatedBackground />
```
`ls frontend/src/components/ui/` → `AnimatedNumber.jsx`, `PageHeader.jsx`, `StatusBadge.jsx` only. `grep -r AnimatedBackground frontend/src` matches only this one line in `App.jsx`.
**CLASSIFICATION:** CRITICAL
**IMPACT:** Unlike the page-level findings below (which are `lazy()`-loaded and only break when a user navigates to that route), this import is at the top of `App.jsx` and is not lazy. Vite/ESM cannot resolve it, so the module graph fails to build — every route, including `/login`, fails to render. This is not a "some pages are broken" bug; as shipped, the application does not start at all.
**RECOMMENDED FIX:** Either restore the missing `AnimatedBackground` component, or remove the import and the `<AnimatedBackground />` usage from `App.jsx` if the ambient background is no longer wanted.

---

### CRITICAL — `/analytics` route is completely broken: 5 missing component imports

**FILE:** `frontend/src/pages/AnalyticsDashboard.jsx`
**COMPONENT/FUNCTION:** `AnalyticsDashboard`
**PROBLEM:** Imports `AnalyticsFilters`, `AnalyticsCharts`, `RequestAnalytics`, `ProviderAnalytics`, and `ReportExport` from `../components/analytics/`, none of which exist — that directory only contains `KPICards.jsx` and `TimeAnalytics.jsx`.
**EVIDENCE:**
```
4  import AnalyticsFilters from '../components/analytics/AnalyticsFilters';
5  import KPICards from '../components/analytics/KPICards';
6  import AnalyticsCharts from '../components/analytics/AnalyticsCharts';
7  import RequestAnalytics from '../components/analytics/RequestAnalytics';
8  import ProviderAnalytics from '../components/analytics/ProviderAnalytics';
9  import TimeAnalytics from '../components/analytics/TimeAnalytics';
10 import ReportExport from '../components/analytics/ReportExport';
```
Directory listing confirms only `KPICards.jsx` and `TimeAnalytics.jsx` exist; the other five are used in JSX at lines 107, 113, 130, 133, 136 but have no source file.
**CLASSIFICATION:** CRITICAL
**IMPACT:** The `/analytics` route (lazy-loaded, "Analytics" nav item) throws a module-resolution error the moment a user navigates to it, producing a blank/crashed view (there is no error boundary around the router — see the related note in the Login/routing section below). The whole "Intelligence → Analytics" surface of the product is non-functional.
**RECOMMENDED FIX:** Restore the five missing component files, or remove the imports/usages and inline simplified replacements if that functionality was intentionally retired.

---

### CRITICAL — `/dmfe` route is completely broken: 3 missing component imports

**FILE:** `frontend/src/pages/DMFEDashboard.jsx`
**COMPONENT/FUNCTION:** `DMFEDashboard`
**PROBLEM:** Imports `DMFEStatisticsBar`, `PendingQueuePanel`, and `RejectedRequestsPanel` from `../components/dmfe/`, none of which exist — that directory only contains `BatchesPanel.jsx`, `CandidateBatchCard.jsx`, `CompatibilityGauge.jsx`, `FactorBreakdown.jsx`.
**EVIDENCE:**
```
8  import DMFEStatisticsBar from '../components/dmfe/DMFEStatisticsBar';
9  import PendingQueuePanel from '../components/dmfe/PendingQueuePanel';
10 import BatchesPanel from '../components/dmfe/BatchesPanel';
11 import RejectedRequestsPanel from '../components/dmfe/RejectedRequestsPanel';
```
Used in JSX at lines 262, 272, 322. Only `BatchesPanel` (imported at line 10) actually resolves.
**CLASSIFICATION:** CRITICAL
**IMPACT:** The `/dmfe` route ("Requests" nav item — the Feasibility Engine dashboard, described as core to the product) fails to render. This is one of the primary operational pages of the dispatch-batching system.
**RECOMMENDED FIX:** Restore the three missing components, or strip the page down to what `BatchesPanel` alone can support until they are rebuilt.

---

### CRITICAL — `/drivers` route is completely broken: the entire `components/drivers/` directory is missing

**FILE:** `frontend/src/pages/DriverDashboard.jsx`
**COMPONENT/FUNCTION:** `DriverDashboard`
**PROBLEM:** Imports six components — `DriverStatistics`, `VehicleStatistics`, `DriverTable`, `VehicleTable`, `AssignmentHistory`, `VehicleLocationMap` — from `../components/drivers/`. That directory does not exist anywhere in the repository.
**EVIDENCE:**
```
9  import DriverStatistics from '../components/drivers/DriverStatistics';
10 import VehicleStatistics from '../components/drivers/VehicleStatistics';
11 import DriverTable from '../components/drivers/DriverTable';
12 import VehicleTable from '../components/drivers/VehicleTable';
13 import AssignmentHistory from '../components/drivers/AssignmentHistory';
14 import VehicleLocationMap from '../components/drivers/VehicleLocationMap';
```
`find frontend/src -iname '*driver*'` returns only `pages/DriverDashboard.jsx` itself and a mention in `pages/SystemConfiguration.jsx`'s search string — no `components/drivers/` directory exists at all.
**CLASSIFICATION:** CRITICAL
**IMPACT:** The `/drivers` route ("Fleet" nav item) fails to render entirely. All six UI sections of this page (driver roster, vehicle fleet, fleet-locations map, assignment history) are unreachable.
**RECOMMENDED FIX:** Rebuild `components/drivers/` from scratch (it appears never to have existed in this checkout) or reduce the page to only what can be supported until it is built.

---

### CRITICAL — `/config` route is completely broken: the entire `components/config/` directory is missing

**FILE:** `frontend/src/pages/SystemConfiguration.jsx`
**COMPONENT/FUNCTION:** `SystemConfiguration`
**PROBLEM:** Imports seven components — `SimulationSettings`, `ProviderConfiguration`, `VehicleRules`, `AIRules`, `SystemPreferences`, `BackupRestore`, `AuditLog` — from `../components/config/`. That directory does not exist anywhere in the repository.
**EVIDENCE:**
```
8  import SimulationSettings from '../components/config/SimulationSettings';
9  import ProviderConfiguration from '../components/config/ProviderConfiguration';
10 import VehicleRules from '../components/config/VehicleRules';
11 import AIRules from '../components/config/AIRules';
12 import SystemPreferences from '../components/config/SystemPreferences';
13 import BackupRestore from '../components/config/BackupRestore';
14 import AuditLog from '../components/config/AuditLog';
```
`find frontend/src -iname '*config*'` returns only `pages/SystemConfiguration.jsx` — no `components/config/` directory exists.
**CLASSIFICATION:** CRITICAL
**IMPACT:** The `/config` route ("Settings" nav item) fails to render. All seven configuration tabs (simulation, provider rules, vehicle rules, AI rules, preferences, backup/restore, audit log) are unreachable — administrators cannot configure the system through the UI at all.
**RECOMMENDED FIX:** Rebuild `components/config/` or remove the tab navigation for sections that are not going to be restored soon.

---

### CRITICAL — `/notifications` route is completely broken: 3 missing component imports

**FILE:** `frontend/src/pages/NotificationCenter.jsx`
**COMPONENT/FUNCTION:** `NotificationCenter`
**PROBLEM:** Imports `NotificationStatistics`, `NotificationFilters`, and `NotificationCard` from `../components/notifications/`, none of which exist — that directory only contains `ActivityTimeline.jsx`.
**EVIDENCE:**
```
6  import NotificationStatistics from '../components/notifications/NotificationStatistics';
7  import NotificationFilters from '../components/notifications/NotificationFilters';
8  import NotificationCard from '../components/notifications/NotificationCard';
9  import ActivityTimeline from '../components/notifications/ActivityTimeline';
```
Used in JSX at lines 131, 134, 180. Only `ActivityTimeline` (line 9) resolves.
**CLASSIFICATION:** CRITICAL
**IMPACT:** The `/notifications` route ("Activity Center", also linked from the bell icon in `AdminLayout.jsx`'s header on every page) fails to render.
**RECOMMENDED FIX:** Restore the three missing components, or fall back to rendering only the `ActivityTimeline` tab until they exist.

---

### CRITICAL — `/playback` route is completely broken: 3 missing component imports

**FILE:** `frontend/src/pages/ScenarioDashboard.jsx`
**COMPONENT/FUNCTION:** `ScenarioDashboard`
**PROBLEM:** Imports `ScenarioDashboardOverview`, `SimulationReplayPlayer`, and `ScenarioManager` from `../components/playback/`, none of which exist — that directory only contains `SavedSimulationsTable.jsx` and `ScenarioComparison.jsx`.
**EVIDENCE:**
```
7  import ScenarioDashboardOverview from '../components/playback/ScenarioDashboardOverview';
8  import SavedSimulationsTable from '../components/playback/SavedSimulationsTable';
9  import SimulationReplayPlayer from '../components/playback/SimulationReplayPlayer';
10 import ScenarioComparison from '../components/playback/ScenarioComparison';
11 import ScenarioManager from '../components/playback/ScenarioManager';
```
Used in JSX at lines 186, 281, 291. Only `SavedSimulationsTable` and `ScenarioComparison` resolve.
**CLASSIFICATION:** CRITICAL
**IMPACT:** The `/playback` route ("Reports" nav item) fails to render entirely.
**RECOMMENDED FIX:** Restore the three missing components, or cut the page down to the Saved Simulations and Comparison tabs (the two that already have real components) until the rest is rebuilt.

---

### HIGH — Search box triggers a full 7-endpoint refetch on every keystroke, no debounce

**FILE:** `frontend/src/pages/DriverDashboard.jsx`
**COMPONENT/FUNCTION:** `DriverDashboard` — the inline search `<input>` and `fetchData`
**PROBLEM:** The search input calls `setSearch(e.target.value)` directly on every keystroke. `fetchData` is a `useCallback` with `[search, filters]` as dependencies, and a `useEffect` re-runs `fetchData()` (and resets the 2.5 s poll timer) whenever `fetchData`'s identity changes — i.e. on every keystroke. `fetchData` itself issues 7 parallel API calls via `Promise.all`.
**EVIDENCE:**
```
36  const fetchData = useCallback(async () => {
...
48    const [dListRes, dStatsRes, vListRes, vStatsRes, pListRes, locRes, histRes] = await Promise.all([
49      api.get(`/drivers?${dParams.toString()}`),
50      api.get('/drivers/stats'),
51      api.get(`/vehicles?${vParams.toString()}`),
52      api.get('/vehicles/stats'),
53      api.get('/providers'),
54      api.get('/vehicles/locations'),
55      api.get('/drivers/assignments/history?limit=100'),
56    ]);
...
68  }, [search, filters]);
69
70  useEffect(() => {
71    fetchData();
72    pollRef.current = setInterval(() => { if (document.visibilityState === 'visible') fetchData(); }, 2500);
73    return () => clearInterval(pollRef.current);
74  }, [fetchData]);
...
181  <input ... value={search} onChange={(e) => setSearch(e.target.value)} ... />
```
No debounce utility exists anywhere in the codebase (`grep -r debounce frontend/src` → no matches).
**CLASSIFICATION:** HIGH
**IMPACT:** Typing a 6-character search term ("driver") fires 6 immediate rounds of 7 parallel requests each (42 requests) in addition to restarting the 2.5 s poll timer 6 times. `services/api.js`'s 2 s cache cannot help here because each keystroke changes the query string, so every request is a fresh cache key. (This bug is currently unreachable in production because the page cannot render at all — see the CRITICAL `/drivers` finding above — but it is a real, independent defect in the fetch wiring that will manifest the moment the missing `components/drivers/` files are restored.)
**RECOMMENDED FIX:** Debounce the search input (e.g. 300–500 ms) before it feeds into `fetchData`'s dependency, or split search into local UI state that only propagates to the fetch-triggering state after a delay / on Enter.

---

### HIGH — Search box triggers a 3-endpoint refetch on every keystroke, no debounce

**FILE:** `frontend/src/pages/ScenarioDashboard.jsx`
**COMPONENT/FUNCTION:** `ScenarioDashboard` — the inline search `<input>` and `fetchData`
**PROBLEM:** Same pattern as `DriverDashboard.jsx`: the search input directly sets `search` state on every keystroke; `fetchData` (a `useCallback` depending on `[search, filterScenario]`) issues `Promise.all` of 3 requests and is called from a `useEffect` keyed on `fetchData`'s identity.
**EVIDENCE:**
```
31  const fetchData = useCallback(async () => {
...
37    const [overviewRes, simListRes, scenRes] = await Promise.all([
38      api.get('/simulation/saved/dashboard'),
39      api.get(`/simulation/saved?${params.toString()}`),
40      api.get('/scenarios'),
41    ]);
...
49  }, [search, filterScenario]);
50
51  useEffect(() => {
52    fetchData();
53  }, [fetchData]);
...
195  <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} .../>
```
**CLASSIFICATION:** HIGH
**IMPACT:** Every character typed into "Search saved runs by name or scenario…" fires a fresh round of 3 API calls. This page has no auto-poll interval, so the blast radius is smaller than `DriverDashboard`'s, but it is still an unbounded-per-keystroke API cost with a real user-facing input. (Also currently unreachable due to the CRITICAL `/playback` finding above, but independent and will surface once that is fixed.)
**RECOMMENDED FIX:** Same as above — debounce the search input before it participates in `fetchData`'s dependency array.

---

### MEDIUM — Same no-debounce fetch pattern present in `NotificationCenter.jsx` (currently masked by missing components)

**FILE:** `frontend/src/pages/NotificationCenter.jsx`
**COMPONENT/FUNCTION:** `NotificationCenter` — `fetchData`
**PROBLEM:** `fetchData` is a `useCallback` with `[search, filters]` dependencies feeding a `useEffect`/`setInterval(2500)` identical in shape to the two HIGH findings above. The search `<input>` itself lives inside the (currently missing) `NotificationFilters` component, so this cannot be independently confirmed to fire per-keystroke today, but the page-level fetch wiring has the identical defect shape.
**EVIDENCE:**
```
29  const fetchData = useCallback(async () => {
...
37    const [listRes, statsRes, timelineRes] = await Promise.all([
38      api.get(`/notifications?${params.toString()}`),
39      api.get('/notifications/stats'),
40      api.get('/notifications/timeline?limit=100'),
41    ]);
...
49  }, [search, filters]);
50
51  // Polling: 2.5s
52  useEffect(() => {
53    fetchData();
54    pollRef.current = setInterval(() => { if (document.visibilityState === 'visible') fetchData(); }, 2500);
55    return () => clearInterval(pollRef.current);
56  }, [fetchData]);
```
**CLASSIFICATION:** MEDIUM (downgraded from HIGH relative to the other two findings only because the search input itself is in a component that does not exist, so the exact keystroke behavior can't be observed directly — but the page-level cause is identical and confirmed)
**IMPACT:** Once `components/notifications/NotificationFilters.jsx` is rebuilt (required for the CRITICAL `/notifications` finding above), unless its search box is debounced internally, every keystroke will restart a 2.5 s poll and fire 3 parallel requests, same as the other two pages.
**RECOMMENDED FIX:** When rebuilding `NotificationFilters`, debounce its search callback before it reaches `setSearch` in the parent, or debounce inside `NotificationCenter.jsx`'s `fetchData` dependency the same way as the other two pages.

---

### MEDIUM — Dead components: `MapFilters.jsx` and `ActivityBar.jsx` are never imported anywhere

**FILE:** `frontend/src/components/map/MapFilters.jsx`, `frontend/src/components/map/ActivityBar.jsx`
**COMPONENT/FUNCTION:** `MapFilters`, `ActivityBar`
**PROBLEM:** Neither component appears in any `import` statement anywhere in the codebase.
**EVIDENCE:** `grep -rn "MapFilters|ActivityBar" frontend/src` returns only each file's own `export default function …` line and one unrelated code-comment mention (`utils/requestSemantics.js:10`, a comment listing historical palette sources) — no import site for either.
**CLASSIFICATION:** MEDIUM
**IMPACT:** No functional impact (nothing renders them), but `MapFilters.jsx` duplicates functionality that live pages actually use split across `MapFilterPanel.jsx` (dropdowns) and `KpiBar.jsx` (search box) — a future maintainer editing filters is likely to edit the wrong (dead) file and wonder why nothing changes on screen. `ActivityBar.jsx` duplicates a "recent queue items" strip that isn't wired into `LiveSimulationMap.jsx`'s current layout.
**RECOMMENDED FIX:** Delete both files, or wire `ActivityBar` into `LiveSimulationMap.jsx` if the bottom activity strip it implements was intended to ship.

---

### MEDIUM — Dead components in `components/xai/`, one shipping hardcoded fake data

**FILE:** `frontend/src/components/xai/ExplanationFilters.jsx`, `frontend/src/components/xai/ScoreBreakdown.jsx`, `frontend/src/components/xai/CompatibilityGauge.jsx`
**COMPONENT/FUNCTION:** `ExplanationFilters`, `ScoreBreakdown`, `CompatibilityGauge` (the `xai/` one, not the separate, actually-used `dmfe/CompatibilityGauge.jsx`)
**PROBLEM:** None of these three components is imported by `ExplanationDashboard.jsx` (which only uses `DecisionCard`, `XaiMapPanel`, `XaiDecisionPanel`) or anywhere else.
**EVIDENCE:** `grep -rn "ScoreBreakdown|ExplanationFilters|xai/CompatibilityGauge" frontend/src` matches only each file's own definition — no import site.
Additionally, `xai/CompatibilityGauge.jsx` defaults its props to fabricated-looking numbers:
```
4  export default function CompatibilityGauge({ score = 89.5, confidence = 92 }) {
```
which directly contradicts this codebase's otherwise-consistent, explicitly documented rule (seen throughout `utils/xaiMap.js`, `TripDetailsPanel.jsx`, etc.) of rendering "—" instead of a fabricated placeholder when a real value is absent.
**CLASSIFICATION:** MEDIUM
**IMPACT:** No current functional impact since nothing renders these three files. The risk is latent: if a future developer wires `xai/CompatibilityGauge` into a page (its name is identical to the component that *is* used, in `dmfe/`, inviting exactly this mistake), it would silently display a fake "89.5%" score for any request whose real score is temporarily unavailable, undermining the honest-data guarantee the rest of the app is careful to uphold.
**RECOMMENDED FIX:** Delete the three dead files (or merge any wanted functionality into the live `dmfe/CompatibilityGauge.jsx` / `ExplanationDashboard.jsx`), and if `xai/CompatibilityGauge.jsx` is kept, remove the fabricated default prop values so a missing score renders as "—" like everywhere else.

---

### MEDIUM — Fleet list endpoints fetched with no `limit`/pagination, polled every 2.5s

**FILE:** `frontend/src/pages/DriverDashboard.jsx`
**COMPONENT/FUNCTION:** `DriverDashboard` — `fetchData`
**PROBLEM:** `/drivers` and `/vehicles` are called with only `search`/`provider_id`/`status`/`vehicle_type` query params — no `limit` or pagination cursor — unlike every other list-fetching page in scope (`/dmfe/batches?...&limit=50`, `/simulation/queue?limit=200`, `/xai/explanations?...&limit=200`, `/notifications/timeline?limit=100`, etc., all of which cap the response).
**EVIDENCE:**
```
48  const [dListRes, dStatsRes, vListRes, vStatsRes, pListRes, locRes, histRes] = await Promise.all([
49    api.get(`/drivers?${dParams.toString()}`),
...
51    api.get(`/vehicles?${vParams.toString()}`),
```
`dParams`/`vParams` (lines 38–46) only ever append `search`, `provider_id`, `status`, `vehicle_type` — never `limit`.
**CLASSIFICATION:** MEDIUM
**IMPACT:** As the driver/vehicle roster grows, every 2.5 s poll pulls the entire unfiltered table with no client-side pagination UI to bound what's rendered either (`DriverTable`/`VehicleTable` render whatever the API returns). This can't be observed running today because the page fails to import (see the CRITICAL `/drivers` finding), but it's a real latent scaling issue in the fetch design that will need addressing when the page is restored.
**RECOMMENDED FIX:** Add a `limit`/pagination param to both requests (matching the convention already used elsewhere in this codebase) and add pagination controls to whichever of the missing `DriverTable`/`VehicleTable` components get rebuilt.

---

### LOW — Dead component: `AnimatedNumber.jsx` is never imported anywhere

**FILE:** `frontend/src/components/ui/AnimatedNumber.jsx`
**COMPONENT/FUNCTION:** `AnimatedNumber`
**PROBLEM:** A count-up animation component with no import site anywhere in the codebase.
**EVIDENCE:** `grep -rn AnimatedNumber frontend/src` matches only its own `export default function AnimatedNumber(...)` declaration.
**CLASSIFICATION:** LOW
**IMPACT:** No functional impact; a well-written, reduced-motion-aware component sitting unused. Every KPI number across the dashboards (`Dashboard.jsx`'s `KpiCard`, `KPICards.jsx`, etc.) renders as a static value instead of using this animation, which may or may not have been the intent.
**RECOMMENDED FIX:** Either wire `AnimatedNumber` into the KPI cards it appears to have been built for, or delete it if the animated-counter treatment was deliberately dropped.

---

### LOW — `AuthContext` Provider value is a new object on every render; `token` state is exposed but never consumed

**FILE:** `frontend/src/context/AuthContext.jsx`
**COMPONENT/FUNCTION:** `AuthProvider`
**PROBLEM:** (1) `<AuthContext.Provider value={{ user, token, login, logout, loading }}>` constructs a new object literal on every render of `AuthProvider`, so every consumer (`Login.jsx`, `ProtectedRoute.jsx`, `AdminLayout.jsx`) re-renders whenever `AuthProvider` re-renders, even if the fields they actually read are unchanged. (2) The `token` state value is set on login/logout but no consumer in the codebase destructures it — auth state everywhere else (the axios interceptor in `services/api.js`) reads `localStorage.getItem('access_token')` directly instead.
**EVIDENCE:**
```
7   const [user, setUser]       = useState(null);
8   const [token, setToken]     = useState(localStorage.getItem('access_token'));
...
48  return (
49    <AuthContext.Provider value={{ user, token, login, logout, loading }}>
```
`grep -n "useContext(AuthContext)" frontend/src -r` shows only `{ user, login }`, `{ user, loading }`, and `{ user, logout }` destructured at the three call sites — `token` is never read.
**CLASSIFICATION:** LOW
**IMPACT:** `AuthProvider` re-renders rarely (only on login/logout/initial profile fetch), so the un-memoized context value is a theoretical rather than a measured hot-path cost. The unused `token` state is dead weight but harmless.
**RECOMMENDED FIX:** Wrap the context value in `useMemo(() => ({ user, token, login, logout, loading }), [user, token, loading])` for correctness/future-proofing, and remove the `token` state entirely if nothing is ever meant to consume it (or start actually using it instead of reading `localStorage` directly in `services/api.js`).

---

### LOW — Two separate, overlapping mechanisms both fetch `/simulation/status` in the same page

**FILE:** `frontend/src/pages/LiveSimulationMap.jsx`
**COMPONENT/FUNCTION:** `LiveSimulationMap` — `fetchLiveData` vs. the dedicated status-poll `useEffect`
**PROBLEM:** `fetchLiveData` (lines 109–117) fetches `/simulation/status` and then calls `refreshNetwork()`, but it is only ever invoked from `handleStartResume`/`handleStop` — it is never used to drive the interval. A second, independent `useEffect` (lines 119–132) separately fetches `/simulation/status` on its own 5000 ms timer via an inline `tick()` function.
**EVIDENCE:**
```
109  const fetchLiveData = useCallback(async () => {
110    try {
111      const statusRes = await api.get('/simulation/status');
112      setStatus(statusRes.data);
113    } catch { /* Silently ignore poll errors */ }
114    refreshNetwork();
115  }, [refreshNetwork]);
116
119  useEffect(() => {
120    let cancelled = false;
121    const tick = async () => {
122      try {
123        const res = await api.get('/simulation/status');
124        if (!cancelled) setStatus(res.data);
125      } catch { /* poll errors are non-fatal */ }
126    };
127    tick();
128    pollRef.current = setInterval(() => {
129      if (document.visibilityState === 'visible') tick();
130    }, 5000);
131    return () => { cancelled = true; clearInterval(pollRef.current); };
132  }, []);
```
**CLASSIFICATION:** LOW
**IMPACT:** No duplicate network calls occur in steady state (only the `tick()` effect actually polls `/simulation/status`; `fetchLiveData` only fires on button click, and the `services/api.js` cache would dedupe the two if they ever landed within the same 2 s window anyway). This is a code-clarity/maintenance issue, not a live performance bug — two functions doing near-identical work make it easy for a future edit to only update one of them and introduce drift.
**RECOMMENDED FIX:** Consolidate to one function (e.g. have the poll effect call `fetchLiveData`, or have `handleStartResume`/`handleStop` call the same `tick`-style helper the poll uses) so there is a single source of truth for "refresh simulation status."

---

## Categories With No Findings

The following categories from the audit brief were checked against every file in scope and found **no evidence of a problem** — several are, in fact, unusually well-engineered relative to typical dashboards of this kind, with comments in the source explicitly documenting past bugs that were fixed:

- **Excessive/uncleaned polling.** Every single `setInterval` found in scope (across `useOperationalNetwork.js`, `AdminLayout.jsx`, `Dashboard.jsx`, `DatasetManagement.jsx`, `DMFEDashboard.jsx`, `AnalyticsDashboard.jsx`, `ExplanationDashboard.jsx`, `SimulationMonitoring.jsx`, `LiveSimulationMap.jsx`, `XaiMapPanel.jsx`) is (a) guarded with `if (document.visibilityState === 'visible')` so a backgrounded tab stops polling, and (b) cleared in its `useEffect` cleanup function. No leaked timers were found.
- **Duplicate/redundant API calls.** `services/api.js` implements a deliberate 2 s response cache plus in-flight request deduplication for all GETs, with `structuredClone` used on both write and read so callers can't mutate the shared cache entry, a bounded cache size (`MAX_CACHE_ENTRIES = 200`), and a blanket cache-invalidation on every POST/PUT/PATCH/DELETE so a refetch right after a mutation can't be served stale pre-mutation data. This directly covers the "several map layers mounting at once cost one network call" and "refetch after mutation" concerns called out in the audit brief.
- **Map/XAI marker and icon performance.** `components/map/markerIcons.js` memoizes every Google/Leaflet icon (queue, vehicle, cluster, operational-stop) in module-level `Map`s keyed by their visual parameters, with an explicit comment noting this was added because rebuilding icons every poll tick "made Leaflet tear down and re-create the whole marker layer four times a second." `FleetLayer.jsx` and `ActiveTripsLayer.jsx` correctly wrap their derived groups/geometry in `useMemo`.
- **Effect re-fetch storms from polling.** `useOperationalRoute.js`, `useSeparateRoutes.js`, and `ActiveTripsLayer.jsx`'s `useTripGeometries` all key their route-geometry-fetching effects on a stable coordinate fingerprint (`waypointKey`/`key`) rather than on object identity, specifically so that polling (which rebuilds request/trip objects every tick with the same coordinates) does not re-trigger a network fetch or reset an in-progress "loading" state. `utils/routeUtils.js`'s `fetchRoadRoute` additionally dedupes concurrent in-flight requests for identical waypoints and caches successes indefinitely / failures for only 30 s (so a transient timeout doesn't permanently downgrade a route to straight lines).
- **Map viewport fighting the user.** `LiveMapContainer.jsx` explicitly keys its `fitBounds` effect on a coordinate fingerprint rather than object identity, with a code comment noting the previous behavior "re-ran fitBounds ~24×/minute and yanked the viewport back mid-pan."
- **Broken navigation.** Every `NavLink`/route reference found (`AdminLayout.jsx`'s `NAV_GROUPS`, `SimulationMonitoring.jsx`'s link to `/live-map`) matches a path actually registered in `App.jsx`'s `<Routes>`. No dead links found.
- **Non-functional buttons.** Every `onClick` handler inspected in the files that exist calls a real, defined function that performs a genuine action (an API call, state update, or navigation) — none are empty, `console.log`-only, or reference an undefined function.
- **Broken filters that are set but never applied.** `SimulationMonitoring.jsx` and `LiveSimulationMap.jsx` both correctly thread their filter/search state into a `useMemo`-derived filtered list that is what actually gets rendered.
- **Unused npm dependencies / missing-dependency false positives.** Every third-party import seen (`@react-google-maps/api`, `react-leaflet`, `leaflet`, `recharts`, `framer-motion`, `lucide-react`, `axios`, `react-hot-toast`, `react-router-dom`) is declared in `frontend/package.json`. The only "missing module" problems found are the first-party component files documented above, not missing npm packages.
- **Unused imports.** No genuinely unused top-level imports were found in any file that exists (icons/utilities imported by every page and component are all referenced in their JSX).
