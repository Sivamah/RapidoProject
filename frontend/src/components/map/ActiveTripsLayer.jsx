import React, { useEffect, useMemo, useState } from 'react';
import { Polyline as GooglePolyline } from '@react-google-maps/api';
import { Polyline as LeafletPolyline } from 'react-leaflet';
import { ROUTE_BACKGROUND_COLOR } from '../../utils/requestSemantics';
import { fetchRoadRoute } from '../../utils/routeUtils';
import { waypointKey } from '../../utils/operationalRoute';

/**
 * Background layer: the corridors currently being driven.
 *
 * Source: `/api/dmfe/trips?status=Active`, whose `stop_order` is the OR-Tools
 * sequence verbatim; coordinates are resolved against the request feed by
 * `useOperationalNetwork` and a stop whose request is outside the current
 * window is dropped rather than guessed at. Stop order is never re-derived
 * here.
 *
 * These are deliberately NOT drawn in the active-route cyan: they are context,
 * and the selected route must stay unambiguous. They are thin, desaturated
 * teal, below every marker in the layer stack.
 *
 * Geometry is fetched through the same cache/dedup path as the selected route,
 * so N trips sharing a corridor cost one request each at most, and a routing
 * failure degrades to the stop polyline instead of disappearing.
 */
function useTripGeometries(trips, enabled) {
  const [paths, setPaths] = useState({});

  // Fingerprint the whole layer's geometry so the effect re-runs when the set
  // of active corridors changes — not on every poll tick that returns the same
  // trips with fresh object identities.
  const specs = useMemo(() => trips.map((t) => ({
    id: t.id,
    waypoints: (t.resolvedStops || []).map((s) => ({ lat: s.lat, lng: s.lng })),
  })).filter((t) => t.waypoints.length >= 2), [trips]);

  const key = useMemo(
    () => specs.map((t) => `${t.id}:${waypointKey(t.waypoints)}`).join('||'),
    [specs],
  );

  useEffect(() => {
    if (!enabled || specs.length === 0) { setPaths({}); return undefined; }
    let cancelled = false;
    Promise.all(specs.map((t) =>
      fetchRoadRoute(t.waypoints).then((res) => [t.id, res.path]),
    )).then((entries) => {
      if (cancelled) return;
      setPaths(Object.fromEntries(entries));
    });
    return () => { cancelled = true; };
    // `specs` is excluded on purpose: `key` is its stable fingerprint.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled]);

  // Until geometry resolves, fall back to the stop polyline so an active
  // corridor is never silently missing from the network picture.
  return useMemo(() => specs.map((t) => ({
    id: t.id,
    path: paths[t.id] && paths[t.id].length > 1 ? paths[t.id] : t.waypoints,
  })), [specs, paths]);
}

export default function ActiveTripsLayer({
  trips = [],
  variant = 'leaflet',
  excludeTripIds = [],
  withGeometry = true,
  dimmed = false,
}) {
  const excluded = useMemo(() => new Set(excludeTripIds), [excludeTripIds]);
  const visible = useMemo(() => trips.filter((t) => !excluded.has(t.id)), [trips, excluded]);
  const geometries = useTripGeometries(visible, withGeometry);

  const opacity = dimmed ? 0.18 : 0.42;

  return (
    <>
      {geometries.map(({ id, path }) => {
        if (!path || path.length < 2) return null;
        if (variant === 'google') {
          return (
            <GooglePolyline
              key={`trip-${id}`}
              path={path}
              options={{
                strokeColor: ROUTE_BACKGROUND_COLOR,
                strokeOpacity: opacity,
                strokeWeight: 3,
                geodesic: false,
                zIndex: 20,
              }}
            />
          );
        }
        return (
          <LeafletPolyline
            key={`trip-${id}`}
            positions={path.map((p) => [p.lat, p.lng])}
            pathOptions={{
              color: ROUTE_BACKGROUND_COLOR,
              weight: 3,
              opacity,
              lineCap: 'round',
              lineJoin: 'round',
            }}
          />
        );
      })}
    </>
  );
}
