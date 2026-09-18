import { useState, useEffect, useMemo } from 'react';
import { buildOperationalRoute, waypointKey } from '../utils/operationalRoute';
import { fetchRoadRoute } from '../utils/routeUtils';

/**
 * Resolve the operational route for an XAI highlight into something drawable.
 *
 * Returns the OR-Tools stop sequence (never reordered) plus, when a routing
 * provider could supply it, the road-following geometry between those stops.
 *
 * Geometry status is explicit so the caller can render an honest state
 * instead of passing straight lines off as a physical route:
 *
 *   'empty'    — fewer than two usable stops; nothing to draw.
 *   'loading'  — a routing request is in flight; no geometry yet.
 *   'road'     — `path` is real road geometry from `source`.
 *   'unrouted' — no provider could route these stops; `path` is the stop list
 *                itself and must be drawn as a clearly-marked direct
 *                connection, not as the trip.
 *
 * Two things this hook must NOT do, both of which were live defects:
 *
 *  1. It must not guard the effect body with a "same key as last time" ref.
 *     `key` is already the dependency, so React re-runs the effect only when
 *     the coordinates change — EXCEPT under StrictMode, which deliberately
 *     mounts, unmounts and re-mounts every effect once in development.  With a
 *     ref guard the first run started the fetch and was then cancelled by the
 *     cleanup, while the second run saw an unchanged ref and returned without
 *     fetching.  The result never arrived and the layer stayed in 'loading'
 *     forever for the first highlight opened on a page — which is precisely
 *     why the live map appeared to draw no road route at all.  Re-running is
 *     cheap: `fetchRoadRoute` dedupes in-flight requests and caches results.
 *
 *  2. It must not seed state with the raw waypoints.  Painting the stop list
 *     first and swapping in road geometry later is what made a straight-line
 *     approximation look like the delivered route.
 *
 * Polling note: the effect is keyed on the waypoint COORDINATES, not on object
 * identity, so the dashboard's 2.5 s poll (which rebuilds the highlight object
 * every tick with identical coordinates) issues no repeat routing requests.
 */
export default function useOperationalRoute(highlight) {
  const route = useMemo(() => buildOperationalRoute(highlight), [highlight]);
  const key = useMemo(() => waypointKey(route.waypoints), [route.waypoints]);
  const count = route.waypoints.length;

  const [geometry, setGeometry] = useState({ status: 'empty', path: [], source: null });

  useEffect(() => {
    if (!key || count < 2) {
      setGeometry({ status: 'empty', path: [], source: null });
      return undefined;
    }

    let cancelled = false;
    setGeometry((prev) => (prev.status === 'loading' ? prev : { status: 'loading', path: [], source: null }));

    // `key` is the coordinate fingerprint, so re-deriving the waypoints here
    // keeps the effect dependent on the fingerprint alone rather than on the
    // array identity that the poll cycle rebuilds every tick.
    const waypoints = key.split('|').map((pair) => {
      const [lat, lng] = pair.split(',').map(Number);
      return { lat, lng };
    });

    fetchRoadRoute(waypoints).then((res) => {
      if (cancelled) return;
      setGeometry({
        status: res.ok ? 'road' : 'unrouted',
        path: res.path,
        source: res.source,
      });
    });

    return () => { cancelled = true; };
  }, [key, count]);

  return { ...route, geometry };
}
