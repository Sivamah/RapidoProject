import { useState, useEffect, useMemo } from 'react';
import { buildSeparateRoutes, waypointKey } from '../utils/operationalRoute';
import { fetchRoadRoute } from '../utils/routeUtils';

/**
 * Resolve each request associated with an XAI highlight into its own,
 * independent pickup→drop road route — the data behind the "separate trips"
 * map view. Mirrors `useOperationalRoute`'s geometry-fetch pattern exactly
 * (same cache-aware `fetchRoadRoute`, same coordinate-fingerprint effect
 * key), just applied per-leg instead of to one combined sequence, so a
 * batched pair can be shown as the two standalone trips they would have been
 * before the DMFE combined them.
 *
 * Pass `null` instead of a highlight to skip building/fetching entirely
 * (e.g. while the combined view is the one on screen) — callers still get a
 * stable `[]` back rather than needing a separate guard.
 */
export default function useSeparateRoutes(highlight) {
  const legs = useMemo(() => buildSeparateRoutes(highlight), [highlight]);
  const key = useMemo(
    () => legs.map((l) => `${l.requestId}:${waypointKey(l.waypoints)}`).join('||'),
    [legs],
  );

  const [geometryByRequest, setGeometryByRequest] = useState({});

  useEffect(() => {
    if (!key) {
      setGeometryByRequest({});
      return undefined;
    }

    let cancelled = false;

    legs.forEach((leg) => {
      setGeometryByRequest((prev) => (
        prev[leg.requestId]?.status === 'road'
          ? prev
          : { ...prev, [leg.requestId]: { status: 'loading', path: [], source: null } }
      ));
      fetchRoadRoute(leg.waypoints).then((res) => {
        if (cancelled) return;
        setGeometryByRequest((prev) => ({
          ...prev,
          [leg.requestId]: { status: res.ok ? 'road' : 'unrouted', path: res.path, source: res.source },
        }));
      });
    });

    return () => { cancelled = true; };
    // `key` is the fingerprint of every leg's coordinates; `legs` itself is
    // deliberately not a dependency for the same reason `useOperationalRoute`
    // excludes `route.waypoints` — polling rebuilds it every tick with
    // identical coordinates, and re-running per tick would issue no new
    // requests (fetchRoadRoute dedupes/caches) but would still needlessly
    // reset in-flight legs back to 'loading'.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return legs.map((leg) => ({
    ...leg,
    geometry: geometryByRequest[leg.requestId] || { status: 'empty', path: [], source: null },
  }));
}
