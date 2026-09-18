/**
 * Road-following DISPLAY geometry for an ordered waypoint list.
 * =============================================================
 *
 * Scope — read this before changing anything here
 * -----------------------------------------------
 * This module is PURELY a visualization concern.  It answers "which shape do I
 * paint between these stops", never "which stops, in which order, for which
 * vehicle".  Stop selection, stop ordering, vehicle assignment and feasibility
 * are owned by the backend (A-DMFE / DMFE / OR-Tools) and arrive here already
 * decided.  Waypoints are therefore passed to the routing provider in the
 * EXACT order received, and Google's `optimizeWaypoints` is pinned to false so
 * the provider can never silently re-solve the OR-Tools sequence.
 *
 * Providers, in order:
 *   1. Google Maps DirectionsService — only when the SDK is loaded.
 *   2. OSRM public API               — primary in Leaflet mode, no key needed.
 *
 * Honest failure
 * --------------
 * The previous implementation returned the raw waypoints when both providers
 * failed AND cached that result permanently, so a single transient OSRM
 * timeout permanently replaced a trip's road route with straight lines, with
 * nothing in the UI to say so.  Now:
 *
 *   * the result carries `ok` and `source`, so callers can render a visibly
 *     different "geometry unavailable" state instead of passing straight lines
 *     off as a road route;
 *   * only SUCCESSFUL geometry is cached indefinitely — failures are cached
 *     for FAILURE_TTL_MS only, so the next poll retries;
 *   * concurrent callers asking for the same waypoints share one in-flight
 *     request instead of issuing duplicates.
 */

/** Successful geometry: key → { path, source }.  Never expires (the OR-Tools
 *  stop sequence is immutable for a dispatched trip, so its shape is too). */
const _routeCache = new Map();
/** Failed lookups: key → expiry timestamp.  Short-lived, so failures retry. */
const _failureCache = new Map();
/** In-flight requests: key → Promise, so N components issue one network call. */
const _inFlight = new Map();

const FAILURE_TTL_MS = 30_000;
const MAX_CACHE_ENTRIES = 300;
const OSRM_TIMEOUT_MS = 8000;

/** Build a stable string key from a waypoint list. */
function _cacheKey(waypoints) {
  return waypoints.map((w) => `${w.lat.toFixed(6)},${w.lng.toFixed(6)}`).join('|');
}

/**
 * Google Maps DirectionsService.
 * @returns {Promise<Array<{lat:number,lng:number}>|null>} null on any failure.
 */
async function _fetchGoogleRoute(waypoints) {
  if (!window.google?.maps?.DirectionsService) return null;

  return new Promise((resolve) => {
    const service = new window.google.maps.DirectionsService();

    // Interior stops become "via" waypoints; first/last are origin/destination.
    const via = waypoints.slice(1, -1).map((w) => ({
      location: new window.google.maps.LatLng(w.lat, w.lng),
      stopover: true,
    }));

    try {
      service.route(
        {
          origin: new window.google.maps.LatLng(waypoints[0].lat, waypoints[0].lng),
          destination: new window.google.maps.LatLng(
            waypoints[waypoints.length - 1].lat,
            waypoints[waypoints.length - 1].lng,
          ),
          waypoints: via,
          // CRITICAL: never let Google reorder stops — OR-Tools owns the order.
          optimizeWaypoints: false,
          travelMode: window.google.maps.TravelMode.DRIVING,
        },
        (result, status) => {
          if (status !== 'OK' || !result?.routes?.[0]?.overview_path) {
            resolve(null);
            return;
          }
          const path = result.routes[0].overview_path.map((p) => ({
            lat: p.lat(),
            lng: p.lng(),
          }));
          resolve(path.length > 1 ? path : null);
        },
      );
    } catch {
      resolve(null);
    }
  });
}

/**
 * OSRM public routing API — full GeoJSON road geometry, no API key.
 * @returns {Promise<Array<{lat:number,lng:number}>|null>} null on any failure.
 */
async function _fetchOsrmRoute(waypoints) {
  // OSRM expects lng,lat order (GeoJSON convention), separated by semicolons.
  const coordStr = waypoints
    .map((w) => `${w.lng.toFixed(6)},${w.lat.toFixed(6)}`)
    .join(';');

  const url =
    `https://router.project-osrm.org/route/v1/driving/${coordStr}` +
    '?overview=full&geometries=geojson';

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), OSRM_TIMEOUT_MS);

  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) return null;

    const data = await res.json();
    if (data.code !== 'Ok' || !data.routes?.[0]?.geometry?.coordinates) return null;

    // GeoJSON coordinates are [lng, lat] — convert to {lat, lng}.
    const path = data.routes[0].geometry.coordinates.map(([lng, lat]) => ({ lat, lng }));
    return path.length > 1 ? path : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

function _prune(map) {
  if (map.size > MAX_CACHE_ENTRIES) map.clear();
}

/**
 * Fetch road-following display geometry for an ordered waypoint list.
 *
 * @param {Array<{lat:number,lng:number}>} waypoints  Ordered stop coordinates
 * @returns {Promise<{path:Array<{lat:number,lng:number}>, source:'google'|'osrm'|'direct', ok:boolean}>}
 *   `ok:true`  — `path` is real road geometry from `source`.
 *   `ok:false` — no provider could route these stops; `path` is the raw stop
 *                list and MUST be presented as an unrouted direct connection,
 *                never as the physical trip.
 */
export async function fetchRoadRoute(waypoints) {
  if (!waypoints || waypoints.length === 0) {
    return { path: [], source: 'direct', ok: false };
  }
  if (waypoints.length === 1) {
    return { path: waypoints, source: 'direct', ok: false };
  }

  const key = _cacheKey(waypoints);

  const hit = _routeCache.get(key);
  if (hit) return { path: hit.path, source: hit.source, ok: true };

  const failedUntil = _failureCache.get(key);
  if (failedUntil !== undefined) {
    if (Date.now() < failedUntil) {
      return { path: waypoints, source: 'direct', ok: false };
    }
    _failureCache.delete(key);
  }

  const pending = _inFlight.get(key);
  if (pending) return pending;

  const task = (async () => {
    // Strategy 1 — Google Directions (auto-skipped when the SDK is absent).
    let path = await _fetchGoogleRoute(waypoints);
    let source = 'google';

    // Strategy 2 — OSRM (primary in Leaflet mode, fallback under Google).
    if (!path) {
      path = await _fetchOsrmRoute(waypoints);
      source = 'osrm';
    }

    if (path) {
      _prune(_routeCache);
      _routeCache.set(key, { path, source });
      _failureCache.delete(key);
      return { path, source, ok: true };
    }

    // No provider could route these stops.  Record the failure with a SHORT
    // TTL so the next poll retries, and tell the caller the geometry is not
    // real so it can render an explicit unrouted state.
    _prune(_failureCache);
    _failureCache.set(key, Date.now() + FAILURE_TTL_MS);
    return { path: waypoints, source: 'direct', ok: false };
  })().finally(() => {
    _inFlight.delete(key);
  });

  _inFlight.set(key, task);
  return task;
}

/** Test/diagnostic helper — drops every cached route and failure marker. */
export function clearRouteCache() {
  _routeCache.clear();
  _failureCache.clear();
  _inFlight.clear();
}
