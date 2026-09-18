/**
 * Operational route assembly — what the map is allowed to draw.
 * =============================================================
 *
 * What the backend actually owns
 * ------------------------------
 * The A-DMFE backend produces NO route geometry.  `RouteOptimizer` (OR-Tools
 * PDP) produces `OptimizedRoute.stop_order` — an ORDERED stop sequence
 * `(request_id, action, arrival_min)` — persisted to `trips.stop_order_json`
 * (coordinates are re-attached server-side in `xai_service._build_trip_link`
 * from the request rows).  The depot handed to OR-Tools is the assigned
 * driver's current location, falling back to the vehicle's.
 *
 * So the AUTHORITATIVE route in this system is:
 *
 *     depot (driver/vehicle position)  →  stop_order[0] → … → stop_order[n]
 *
 * This module reconstructs exactly that sequence and nothing else.  It never
 * reorders stops, never invents a stop, and never substitutes a stop the
 * assignment result did not contain.  Road geometry for those waypoints is a
 * separate, display-only concern (see `routeUtils.js`) and is deliberately not
 * mixed in here.
 */

/** A coordinate is usable only if it is a finite non-zero pair. */
function isUsableCoord(lat, lng) {
  return (
    Number.isFinite(lat) && Number.isFinite(lng) &&
    !(lat === 0 && lng === 0)
  );
}

/**
 * Build the operational stop sequence for one XAI highlight.
 *
 * @param {object|null} highlight  Output of `normalizeXaiHighlight`
 * @returns {{
 *   stops: Array<{role:'origin'|'pickup'|'drop', requestId:number|null,
 *                 lat:number, lng:number, arrivalMin:number|null, seq:number}>,
 *   waypoints: Array<{lat:number,lng:number}>,
 *   hasOrigin: boolean,
 *   originSource: 'driver'|'vehicle'|null,
 *   isDispatched: boolean,
 *   isPlanned: boolean,
 *   droppedStops: number,
 * }}
 */
export function buildOperationalRoute(highlight) {
  const empty = {
    stops: [], waypoints: [], hasOrigin: false, originSource: null,
    isDispatched: false, isPlanned: false, droppedStops: 0,
  };
  if (!highlight) return empty;

  // A trip exists only when the assignment actually produced one.  Its
  // presence is what distinguishes a real dispatched route from a request
  // that has merely been evaluated.
  const isDispatched = Boolean(highlight.tripCode);

  const stops = [];

  // 1. Origin — the vehicle/driver position the optimizer used as its depot.
  //    Included ONLY for a dispatched trip: for an un-dispatched request there
  //    is no assigned vehicle, so drawing one would be an invention.
  let originSource = null;
  if (isDispatched) {
    const driver = highlight.driver;
    const vehicle = highlight.vehicle;
    if (driver && isUsableCoord(driver.lat, driver.lng)) {
      originSource = 'driver';
      stops.push({ role: 'origin', requestId: null, lat: driver.lat, lng: driver.lng, arrivalMin: 0, seq: null });
    } else if (vehicle && isUsableCoord(vehicle.lat, vehicle.lng)) {
      originSource = 'vehicle';
      stops.push({ role: 'origin', requestId: null, lat: vehicle.lat, lng: vehicle.lng, arrivalMin: 0, seq: null });
    }
  }

  // 2. The OR-Tools stop order, verbatim.  Order is preserved exactly as the
  //    optimizer emitted it — including batched interleavings such as
  //    pickup A → pickup B → drop B → drop A.
  let dropped = 0;
  (highlight.routeStops || []).forEach((s) => {
    if (!s) return;
    const lat = Number(s.lat);
    const lng = Number(s.lng);
    if (!isUsableCoord(lat, lng)) { dropped += 1; return; }
    stops.push({
      role: s.action === 'drop' ? 'drop' : 'pickup',
      requestId: s.request_id ?? null,
      lat,
      lng,
      arrivalMin: Number.isFinite(Number(s.arrival_min)) ? Number(s.arrival_min) : null,
      seq: null,
    });
  });

  // Number the SERVICE stops 1..n.  The vehicle origin keeps `seq: null` so
  // stop 1 is always the first pickup, whether or not a vehicle is attached —
  // otherwise an un-dispatched request would start counting at a different
  // number from a dispatched one.
  let n = 0;
  stops.forEach((st) => { if (st.role !== 'origin') { n += 1; st.seq = n; } });

  return {
    stops,
    waypoints: stops.map((s) => ({ lat: s.lat, lng: s.lng })),
    hasOrigin: originSource !== null,
    originSource,
    isDispatched,
    // "Planned" = the request has pickup/drop points but no dispatched trip,
    // so the sequence shown is the request's own leg, not an optimizer result.
    isPlanned: !isDispatched && stops.length > 0,
    droppedStops: dropped,
  };
}

/**
 * Build one independent 2-stop pickup→drop leg per request associated with
 * this highlight — itself, plus the XAI-evaluated partner and/or the real
 * trip members `requestPoints` already carries — instead of the single
 * interleaved OR-Tools sequence `buildOperationalRoute` produces.
 *
 * This is what the "separate trips" map view draws: a batched pair shown as
 * the two standalone trips they would have been before the DMFE combined
 * them. It never re-derives stop order or invents a vehicle depot — each leg
 * is just that one request's own pickup and drop, the same shape
 * `buildOperationalRoute` already uses for a standalone un-dispatched
 * request (`isPlanned`), just applied to every associated request instead of
 * one.
 *
 * @param {object|null} highlight  Output of `normalizeXaiHighlight`
 * @returns {Array<{requestId:number, requestType:string, stops:Array, waypoints:Array}>}
 */
export function buildSeparateRoutes(highlight) {
  if (!highlight) return [];

  const legs = [];
  const seen = new Set();

  const pushLeg = (requestId, requestType, pLat, pLng, dLat, dLng) => {
    if (requestId == null || seen.has(requestId)) return;
    if (!isUsableCoord(pLat, pLng) || !isUsableCoord(dLat, dLng)) return;
    seen.add(requestId);
    legs.push({
      requestId,
      requestType,
      stops: [
        { role: 'pickup', requestId, lat: pLat, lng: pLng, arrivalMin: null, seq: 1 },
        { role: 'drop', requestId, lat: dLat, lng: dLng, arrivalMin: null, seq: 2 },
      ],
      waypoints: [{ lat: pLat, lng: pLng }, { lat: dLat, lng: dLng }],
    });
  };

  // This request's own leg first — it is the trip the decision is about.
  pushLeg(
    highlight.requestId, highlight.requestType,
    highlight.pickupLat, highlight.pickupLng, highlight.dropLat, highlight.dropLng,
  );

  // Every other request associated with this decision (the XAI-evaluated
  // partner and/or the other real dispatched-trip members) gets its own leg.
  (highlight.requestPoints || []).forEach((p) => {
    if (p.relation === 'self') return;
    pushLeg(p.id, p.request_type, p.pickup_lat, p.pickup_lng, p.drop_lat, p.drop_lng);
  });

  return legs;
}

/**
 * Stable identity for a waypoint list — used as a cache/effect key so that
 * re-renders caused purely by polling (new object identity, same coordinates)
 * neither refetch geometry nor re-fit the viewport.
 */
export function waypointKey(waypoints) {
  if (!waypoints || waypoints.length === 0) return '';
  return waypoints.map((w) => `${w.lat.toFixed(6)},${w.lng.toFixed(6)}`).join('|');
}

/**
 * Human-readable operational summary of the sequence, e.g.
 * "Vehicle → Pickup #12 → Pickup #15 → Drop #15 → Drop #12".
 * Built from the real stops only; returns [] when there are none.
 */
export function describeSequence(stops) {
  return (stops || []).map((s) => {
    if (s.role === 'origin') return 'Vehicle';
    return `${s.role === 'drop' ? 'Drop' : 'Pickup'} #${s.requestId ?? '?'}`;
  });
}

/**
 * Same sequence as `describeSequence`, formatted as numbered lines for a
 * detail panel, e.g. "1. Pickup Request #12" / "2. Pickup Request #15" /
 * "3. Drop Request #15" / "4. Drop Request #12". The vehicle origin (if
 * present) is not numbered — it precedes stop 1, matching how `seq` is
 * assigned in `buildOperationalRoute`. Built from the real stops only.
 */
export function describeSequenceNumbered(stops) {
  return (stops || [])
    .filter((s) => s.role !== 'origin')
    .map((s) => `${s.seq}. ${s.role === 'drop' ? 'Drop' : 'Pickup'} Request #${s.requestId ?? '?'}`);
}
