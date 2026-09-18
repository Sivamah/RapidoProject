import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import api from '../services/api';

/**
 * The operational network, assembled from the endpoints that already exist.
 * ========================================================================
 *
 * Before this hook every map on the platform rendered exactly one feed —
 * `/simulation/queue`, i.e. the handful of *pending* requests — so an
 * operations map showed 5 markers while the system was tracking 115 vehicles
 * and 4 active trips. Nothing here is generated: each field maps 1:1 onto a
 * real endpoint.
 *
 *   `/api/vehicles/locations`      → fleet positions, type, status, driver
 *   `/api/dmfe/trips?status=Active`→ dispatched trips + OR-Tools `stop_order`
 *   `/api/simulation/queue`        → pending (not yet dispatched) requests
 *
 * A vehicle with no recorded position is omitted server-side rather than
 * placed on a stand-in coordinate, so everything that reaches the map is a
 * position the system actually holds.
 *
 * @param {object}  opts
 * @param {boolean} opts.vehicles   fetch fleet positions (default true)
 * @param {boolean} opts.trips      fetch active trips (default true)
 * @param {boolean} opts.queue      fetch the pending queue (default true)
 * @param {number}  opts.intervalMs poll period; 0 disables polling
 */
export default function useOperationalNetwork({
  vehicles: wantVehicles = true,
  trips: wantTrips = true,
  queue: wantQueue = true,
  intervalMs = 5000,
} = {}) {
  const [vehicles, setVehicles] = useState([]);
  const [fleet, setFleet] = useState(null);
  const [trips, setTrips] = useState([]);
  const [queue, setQueue] = useState([]);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);

  const fetchAll = useCallback(async () => {
    // Every request goes through `services/api.js`, which deduplicates
    // in-flight GETs and caches responses briefly — so several map layers
    // mounting at once cost one network call each, not one per consumer.
    const jobs = [];
    if (wantVehicles) {
      jobs.push(['vehicles', api.get('/vehicles/locations')]);
      // Fleet COMPOSITION (every registered vehicle) is a different question
      // from fleet POSITIONS (only vehicles with a recorded coordinate), so it
      // comes from its own authoritative endpoint rather than being inferred
      // from the length of the location feed.
      jobs.push(['fleet', api.get('/vehicles/stats')]);
    }
    if (wantTrips) jobs.push(['trips', api.get('/dmfe/trips?status=Active&limit=200')]);
    if (wantQueue) jobs.push(['queue', api.get('/simulation/queue?limit=200')]);

    const settled = await Promise.allSettled(jobs.map(([, pr]) => pr));
    let failed = 0;

    settled.forEach((res, i) => {
      const key = jobs[i][0];
      if (res.status !== 'fulfilled') { failed += 1; return; }
      const data = res.value.data;
      if (key === 'vehicles') setVehicles(Array.isArray(data) ? data : []);
      if (key === 'fleet') setFleet(data || null);
      if (key === 'trips') setTrips(Array.isArray(data) ? data : []);
      if (key === 'queue') setQueue(data?.items || []);
    });

    if (failed === jobs.length && jobs.length > 0) {
      setError('Operational data feed unavailable.');
    } else {
      setError(null);
      setLastUpdated(new Date());
    }
  }, [wantVehicles, wantTrips, wantQueue]);

  useEffect(() => {
    fetchAll();
    if (!intervalMs) return undefined;
    timerRef.current = setInterval(() => {
      // Do not poll a tab nobody is looking at.
      if (document.visibilityState === 'visible') fetchAll();
    }, intervalMs);
    return () => clearInterval(timerRef.current);
  }, [fetchAll, intervalMs]);

  /**
   * Trip stops arrive with coordinates already attached by the API.
   *
   * They deliberately are NOT joined client-side against the request feed:
   * `stop_order_json` stores request ids only, and a dispatched trip's requests
   * are no longer pending, so joining against `/simulation/queue` resolved zero
   * stops for every active trip — which is exactly why no active corridor could
   * be drawn. The backend now resolves them next to the data that owns them
   * (see `serializers.resolve_stop_coordinates`).
   *
   * A stop the backend could not resolve arrives without lat/lng and is
   * dropped here rather than given a substitute position.
   */
  const activeTrips = useMemo(() => trips.map((t) => ({
    ...t,
    resolvedStops: (t.stop_order || [])
      .filter((s) => Number.isFinite(s?.lat) && Number.isFinite(s?.lng))
      .map((s) => ({
        requestId: s.request_id,
        action: s.action,
        requestType: s.request_type ?? null,
        lat: s.lat,
        lng: s.lng,
        arrivalMin: s.arrival_min ?? null,
      })),
  })), [trips]);

  /**
   * Derived counts. Every figure below is a count of real rows from a real
   * endpoint — nothing is estimated, weighted or defaulted.
   *
   *   pending          — requests still in the queue (/simulation/queue)
   *   inFlight*        — requests attached to an ACTIVE trip, deduplicated by
   *                      request id (a stop list contains each request twice,
   *                      once for pickup and once for drop)
   *   activeRequests   — pending + in-flight, i.e. every request the network is
   *                      currently carrying and has not completed
   *   ongoingRides     — in-flight requests of type `ride`
   *   deliveries       — in-flight requests of type `food` or `parcel`
   *   fleetTotal       — /vehicles/stats.total_vehicles = COUNT(Vehicle.id):
   *                      the whole registered fleet, every status, whether or
   *                      not it reports a position
   *   fleetAvailable   — /vehicles/stats.available_vehicles
   *   reportingVehicles— vehicles with a usable coordinate (what the map draws)
   */
  const stats = useMemo(() => {
    const byType = { ride: 0, food: 0, parcel: 0, other: 0 };
    queue.forEach((r) => {
      const k = String(r.request_type || '').toLowerCase();
      if (k in byType) byType[k] += 1; else byType.other += 1;
    });

    const byVehicleStatus = {};
    vehicles.forEach((v) => {
      const k = v.status || 'Unknown';
      byVehicleStatus[k] = (byVehicleStatus[k] || 0) + 1;
    });

    // Deduplicate: a trip's stop list names each request twice.
    const inFlightType = new Map();
    trips.forEach((t) => {
      (t.stop_order || []).forEach((st) => {
        if (st?.request_id == null) return;
        if (!inFlightType.has(st.request_id)) {
          inFlightType.set(st.request_id, String(st.request_type || '').toLowerCase());
        }
      });
    });
    const inFlight = [...inFlightType.values()];
    const ongoingRides = inFlight.filter((t) => t === 'ride').length;
    const deliveries = inFlight.filter((t) => t === 'food' || t === 'parcel').length;

    return {
      pending: queue.length,
      byType,
      vehicles: vehicles.length,
      reportingVehicles: vehicles.length,
      byVehicleStatus,
      activeTrips: trips.length,
      sharedTrips: trips.filter((t) => t.is_shared).length,
      inFlightRequests: inFlight.length,
      activeRequests: queue.length + inFlight.length,
      ongoingRides,
      deliveries,
      fleetTotal: Number.isFinite(fleet?.total_vehicles) ? fleet.total_vehicles : null,
      fleetAvailable: Number.isFinite(fleet?.available_vehicles) ? fleet.available_vehicles : null,
      fleetInService: Number.isFinite(fleet?.vehicles_in_service) ? fleet.vehicles_in_service : null,
      fleetMaintenance: Number.isFinite(fleet?.maintenance_vehicles) ? fleet.maintenance_vehicles : null,
    };
  }, [queue, vehicles, trips, fleet]);

  return { vehicles, fleet, trips, activeTrips, queue, stats, lastUpdated, error, refresh: fetchAll };
}
