import React, { useMemo } from 'react';
import {
  Marker as GoogleMarker,
  InfoWindow,
  Polyline as GooglePolyline,
} from '@react-google-maps/api';
import {
  Marker as LeafletMarker,
  Popup as LeafletPopup,
  Polyline as LeafletPolyline,
} from 'react-leaflet';
import { BrainCircuit, Check, X, AlertTriangle, Loader2, Route as RouteIcon } from 'lucide-react';
import useOperationalRoute from '../../hooks/useOperationalRoute';
import useSeparateRoutes from '../../hooks/useSeparateRoutes';
import { describeSequence } from '../../utils/operationalRoute';
import {
  requestTypeMeta,
  decisionStateMeta,
  ROUTE_ACTIVE_COLOR,
  ROUTE_FALLBACK_COLOR,
} from '../../utils/requestSemantics';
import { googleMarkerIcon, leafletMarkerIcon } from './markerIcons';

/**
 * XAI highlight layer — the visual half of the A-DMFE decision explanation.
 *
 * What it draws, and where each part comes from:
 *
 *   ACTIVE ROUTE   road geometry between the OR-Tools stops, fetched for
 *                  DISPLAY ONLY (see utils/routeUtils).  Always cyan,
 *                  independent of request type.  When no routing provider can
 *                  supply geometry the layer switches to a dashed, muted
 *                  "unrouted" line and says so — it never presents a
 *                  straight-line approximation as the physical trip.
 *   STOPS          the trip's `stop_order` exactly as the optimizer emitted
 *                  it, numbered in sequence, prefixed by the vehicle's own
 *                  position when the trip is dispatched.
 *   MARKERS        shape = pickup/drop/vehicle, colour + glyph = request type.
 *   POPUP          the engine's own decision, score, confidence and factor
 *                  values.  No placeholder numbers and no invented reasons.
 *
 * VIEW MODE (`viewMode` prop, 'combined' default): for a request the DMFE
 * actually batched into a shared trip (`highlight.isShared`), 'separate'
 * draws each request's own pickup→drop leg independently (via
 * `useSeparateRoutes`) instead of the one interleaved OR-Tools sequence —
 * the "before" picture a caller can show alongside the "after". For any
 * other decision the two modes render identically, since there is nothing
 * to separate.
 */

// ── Popup ───────────────────────────────────────────────────────────────────

function num(value, digits = 1, suffix = '') {
  return Number.isFinite(value) ? `${value.toFixed(digits)}${suffix}` : '—';
}

export function HighlightPopup({ highlight, route }) {
  if (!highlight) return null;

  const state = decisionStateMeta(highlight.status, highlight.decision);
  const isRejected = state.tone === 'danger';
  const type = requestTypeMeta(highlight.requestType);
  const f = highlight.factors || {};
  const reasons = highlight.keyReasons || [];
  const sequence = describeSequence(route?.stops || []);

  // A rejected pairing never had a real trip — showing its route as "planned"
  // would misrepresent an evaluated-and-declined pair as one still awaiting
  // dispatch, so the route note takes priority over the ordinary geometry
  // status for this decision state.
  const geometryNote = isRejected
    ? 'Rejected pairing — no route drawn.'
    : ({
        road: null,
        loading: 'Resolving road geometry…',
        unrouted: 'Road geometry unavailable — stops shown as a direct connection.',
        empty: 'No usable stop coordinates for this request.',
      }[route?.geometry?.status] ?? null);

  return (
    <div className="bg-[#0A0F1A]/95 backdrop-blur-2xl border border-white/15 rounded-2xl shadow-[0_20px_60px_rgba(0,0,0,0.8)] w-[300px] p-5 font-sans relative overflow-hidden">
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-[#00F0FF] to-transparent" />

      {/* Header: decision identity */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <BrainCircuit className="h-4 w-4 text-[#00F0FF]" />
          <h3 className="text-[11px] font-bold text-white tracking-[0.14em] uppercase">A-DMFE Decision</h3>
        </div>
        <span
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[9px] font-bold uppercase tracking-wider border"
          style={{ color: type.color, borderColor: `${type.color}66`, background: `${type.color}1A` }}
        >
          <type.Icon className="h-3 w-3" /> {type.label}
        </span>
      </div>

      {/* The engine's decision, verbatim */}
      <div className="mb-4">
        <span className="text-[14px] font-bold leading-snug block" style={{ color: state.color }}>
          {highlight.decision || 'No decision recorded'}
        </span>
        {highlight.decisionSummary && (
          <span className="text-[10.5px] text-white/50 leading-relaxed block mt-1">
            {highlight.decisionSummary}
          </span>
        )}
      </div>

      {/* Compatibility and confidence are separate quantities — labelled as such */}
      <div className="grid grid-cols-2 gap-2 mb-4">
        <div className="rounded-xl border border-white/10 bg-white/[0.03] px-2.5 py-2">
          <span className="block text-[8.5px] uppercase tracking-wider text-white/40 font-bold">Compatibility</span>
          <span className="text-[15px] font-semibold text-white tabular-nums">{num(highlight.score, 1, '%')}</span>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/[0.03] px-2.5 py-2">
          <span className="block text-[8.5px] uppercase tracking-wider text-white/40 font-bold">Confidence</span>
          <span className="text-[15px] font-semibold text-white tabular-nums">{num(highlight.confidence, 1, '%')}</span>
        </div>
      </div>

      {/* Engine factor values — shown only when the payload carried them */}
      {highlight.factors && (
        <div className="space-y-1 mb-4 text-[10.5px]">
          {[
            ['Pickup distance', num(f.pickup_distance_km, 2, ' km')],
            ['Route similarity', num(f.route_similarity_pct, 1, '%')],
            ['Estimated delay', num(f.estimated_delay_min, 1, ' min')],
            ['Time difference', num(f.time_difference_min, 1, ' min')],
          ].map(([label, value]) => (
            <div key={label} className="flex items-center justify-between">
              <span className="text-white/45">{label}</span>
              <span className="text-white/85 font-mono tabular-nums">{value}</span>
            </div>
          ))}
        </div>
      )}

      {/* Reasons produced by the engine.  Never substituted when empty. */}
      <div className="space-y-1.5">
        {reasons.slice(0, 5).map((r, i) => (
          <div key={i} className="flex items-start gap-2 text-[10.5px]">
            {/^(rejected|not |insufficient|exceeds)/i.test(r)
              ? <X className="h-3 w-3 text-[#EF4444] shrink-0 mt-0.5" />
              : <Check className="h-3 w-3 text-[#22C55E] shrink-0 mt-0.5" />}
            <span className="text-white/75 leading-relaxed">{r}</span>
          </div>
        ))}
        {reasons.length === 0 && (
          <p className="text-[10.5px] text-white/35 italic">
            No factor rationale recorded for this decision.
          </p>
        )}
      </div>

      {/* Operational sequence, straight from the assignment result */}
      {sequence.length > 1 && (
        <div className="mt-4 pt-3 border-t border-white/10">
          <span className="flex items-center gap-1.5 text-[8.5px] uppercase tracking-wider text-white/40 font-bold mb-1.5">
            <RouteIcon className="h-3 w-3" /> Operational sequence
          </span>
          <p className="text-[10px] text-white/70 leading-relaxed font-mono">
            {sequence.join(' → ')}
          </p>
          {route?.isPlanned && (
            <p className="text-[9.5px] text-[#F59E0B] mt-1.5">
              Planned leg — no vehicle dispatched for this request yet.
            </p>
          )}
        </div>
      )}

      {geometryNote && (
        <p className={`mt-3 flex items-start gap-1.5 text-[9.5px] ${isRejected ? 'text-[#EF4444]' : 'text-[#F59E0B]'}`}>
          {isRejected
            ? <X className="h-3 w-3 shrink-0 mt-0.5" />
            : route.geometry.status === 'loading'
              ? <Loader2 className="h-3 w-3 animate-spin shrink-0 mt-0.5" />
              : <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" />}
          <span>{geometryNote}</span>
        </p>
      )}

      <div className="mt-4 pt-3 border-t border-white/10 flex items-center gap-2 flex-wrap">
        <span className="text-[9px] text-white/35 uppercase tracking-wider font-bold">Req</span>
        <span className="text-[10.5px] text-white font-mono bg-white/10 px-1.5 py-0.5 rounded">#{highlight.requestId}</span>
        {highlight.tripCode && (
          <span className="text-[10px] text-[#00F0FF] font-mono bg-[#00F0FF]/10 border border-[#00F0FF]/25 px-1.5 py-0.5 rounded">
            {highlight.tripCode}{highlight.isShared ? ' · shared' : ''}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Shared derivation ───────────────────────────────────────────────────────

/**
 * Resolve each operational stop to the request-type identity of the request it
 * belongs to, so a batched trip paints stop 1 in (say) food orange and stop 2
 * in ride blue while the route between them stays cyan.
 */
function useDecoratedStops(highlight, route) {
  return useMemo(() => {
    const typeById = new Map(
      (highlight.requestPoints || []).map((p) => [p.id, p.request_type]),
    );
    return route.stops.map((s) => ({
      ...s,
      type: requestTypeMeta(
        s.requestId != null ? typeById.get(s.requestId) : highlight.requestType,
      ),
    }));
  }, [highlight, route.stops]);
}

function stopTitle(stop) {
  if (stop.role === 'origin') return 'Assigned vehicle — trip origin';
  const role = stop.role === 'drop' ? 'Drop-off' : 'Pickup';
  const eta = Number.isFinite(stop.arrivalMin) ? ` · arrives ${stop.arrivalMin.toFixed(1)} min` : '';
  return `Stop ${stop.seq}: ${role} — ${stop.type.label} request #${stop.requestId}${eta}`;
}

function isUsableCoord(lat, lng) {
  return Number.isFinite(lat) && Number.isFinite(lng) && !(lat === 0 && lng === 0);
}

/** Attach type/colour metadata to one `buildSeparateRoutes` leg's stops —
 *  every stop in a leg belongs to the same request, so this is the single-
 *  request equivalent of `useDecoratedStops`. */
function decorateLegStops(leg) {
  const type = requestTypeMeta(leg.requestType);
  return leg.stops.map((s) => ({ ...s, type }));
}

// ── Google Maps highlight ───────────────────────────────────────────────────

/** One route's polyline(s) + stop markers — the combined OR-Tools route and
 *  each "separate trips" leg are both drawn with this, so the two view modes
 *  never diverge in how a route actually looks on the map. */
function GoogleRouteSegment({ keyPrefix, status, path, stops, isRejected }) {
  return (
    <>
      {/* ACTIVE ROUTE — real road geometry. One cyan core at 4.5 px with a
          single soft halo, not a stack of neon strokes: the route has to read
          as a road being followed, and the underlying street has to stay
          checkable through it. Direction arrows are spaced widely so they
          inform rather than decorate. */}
      {!isRejected && status === 'road' && path.length > 1 && (
        <>
          <GooglePolyline path={path} options={{ strokeColor: ROUTE_ACTIVE_COLOR, strokeOpacity: 0.16, strokeWeight: 13, geodesic: false, zIndex: 40 }} />
          <GooglePolyline path={path} options={{ strokeColor: ROUTE_ACTIVE_COLOR, strokeOpacity: 0.95, strokeWeight: 4.5, geodesic: false, zIndex: 42 }} />
          <GooglePolyline
            path={path}
            options={{
              strokeColor: ROUTE_ACTIVE_COLOR, strokeOpacity: 0, strokeWeight: 4.5, geodesic: false, zIndex: 43,
              icons: [{
                icon: {
                  path: window.google.maps.SymbolPath.FORWARD_CLOSED_ARROW,
                  scale: 2.2, fillColor: '#EAFDFF', fillOpacity: 0.95,
                  strokeColor: ROUTE_ACTIVE_COLOR, strokeWeight: 1,
                },
                offset: '0%', repeat: '110px',
              }],
            }}
          />
        </>
      )}

      {/* UNROUTED — deliberately NOT the active-route styling, so a direct
          connection can never be mistaken for a road-following trip. */}
      {!isRejected && status === 'unrouted' && path.length > 1 && (
        <GooglePolyline
          path={path}
          options={{
            strokeColor: ROUTE_FALLBACK_COLOR, strokeOpacity: 0, strokeWeight: 3,
            geodesic: false, zIndex: 39,
            icons: [{
              icon: { path: 'M 0,-1 0,1', strokeOpacity: 0.85, strokeColor: ROUTE_FALLBACK_COLOR, scale: 3 },
              offset: '0', repeat: '14px',
            }],
          }}
        />
      )}

      {stops.map((s) => (
        <GoogleMarker
          key={`${keyPrefix}-stop-${s.seq}-${s.role}-${s.requestId ?? 'origin'}`}
          position={{ lat: s.lat, lng: s.lng }}
          icon={googleMarkerIcon(s.role, s.type.color, s.type.key, s.role === 'origin' ? null : s.seq, false, 40, isRejected && s.role !== 'origin')}
          zIndex={s.role === 'origin' ? 55 : 60}
          title={isRejected ? `${stopTitle(s)} — rejected pairing` : stopTitle(s)}
        />
      ))}
    </>
  );
}

function GoogleHighlight({ highlight, viewMode = 'combined' }) {
  const route = useOperationalRoute(highlight);
  const stops = useDecoratedStops(highlight, route);
  const { status, path } = route.geometry;
  // A rejected pairing has no real trip — the pickup→drop leg `xaiMap.js`
  // synthesizes for any un-dispatched request would otherwise be drawn as a
  // "planned" line, implying dispatch is still pending. It is not: suppress
  // the route for this decision state and mark the stops as rejected instead.
  const isRejected = decisionStateMeta(highlight.status, highlight.decision).tone === 'danger';

  // "Separate trips" only means something for a request that was actually
  // combined into a shared trip — for anything else there is nothing to
  // separate, so the combined (ordinary) rendering below is used regardless
  // of the requested view mode.
  const showSeparate = viewMode === 'separate' && highlight.isShared;
  const separateLegs = useSeparateRoutes(showSeparate ? highlight : null);

  // The popup anchors on this request's own pickup — a stable point that
  // exists whichever view is on screen, rather than "whatever the combined
  // route's first stop happens to be" (which, for a batched pair, may be the
  // partner's pickup depending on OR-Tools' interleaving).
  const anchorPos = isUsableCoord(highlight.pickupLat, highlight.pickupLng)
    ? { lat: highlight.pickupLat, lng: highlight.pickupLng }
    : (stops.find((s) => s.role !== 'origin') || stops[0]);

  return (
    <>
      {showSeparate ? (
        separateLegs.map((leg) => (
          <GoogleRouteSegment
            key={leg.requestId}
            keyPrefix={`leg-${leg.requestId}`}
            status={leg.geometry.status}
            path={leg.geometry.path}
            stops={decorateLegStops(leg)}
            isRejected={false}
          />
        ))
      ) : (
        <GoogleRouteSegment keyPrefix="combined" status={status} path={path} stops={stops} isRejected={isRejected} />
      )}

      {anchorPos && (
        <InfoWindow
          position={{ lat: anchorPos.lat, lng: anchorPos.lng }}
          options={{ zIndex: 100, pixelOffset: new window.google.maps.Size(0, -34) }}
        >
          <HighlightPopup highlight={highlight} route={route} />
        </InfoWindow>
      )}
    </>
  );
}

// ── Leaflet highlight ───────────────────────────────────────────────────────

/** Leaflet equivalent of `GoogleRouteSegment` — one route's polyline(s) +
 *  stop markers. `popupStop` (matched by requestId+role, not array position)
 *  is the one marker that carries the decision popup as a child, since
 *  Leaflet attaches popups to markers rather than to a free-floating window. */
function LeafletRouteSegment({ keyPrefix, status, path, stops, isRejected, highlight, route, popupStop }) {
  const positions = useMemo(() => path.map((p) => [p.lat, p.lng]), [path]);

  return (
    <>
      {!isRejected && status === 'road' && positions.length > 1 && (
        <>
          {/* soft halo, then a single 4.5 px cyan core with round caps/joins */}
          <LeafletPolyline
            positions={positions}
            pathOptions={{ color: ROUTE_ACTIVE_COLOR, weight: 13, opacity: 0.16, lineCap: 'round', lineJoin: 'round' }}
          />
          <LeafletPolyline
            positions={positions}
            pathOptions={{ color: ROUTE_ACTIVE_COLOR, weight: 4.5, opacity: 0.95, lineCap: 'round', lineJoin: 'round' }}
          />
        </>
      )}

      {!isRejected && status === 'unrouted' && positions.length > 1 && (
        <LeafletPolyline
          positions={positions}
          pathOptions={{ color: ROUTE_FALLBACK_COLOR, weight: 3, opacity: 0.8, dashArray: '4 10', lineCap: 'round', lineJoin: 'round' }}
        />
      )}

      {stops.map((s) => (
        <LeafletMarker
          key={`${keyPrefix}-stop-${s.seq}-${s.role}-${s.requestId ?? 'origin'}`}
          position={[s.lat, s.lng]}
          icon={leafletMarkerIcon(s.role, s.type.color, s.type.key, s.role === 'origin' ? null : s.seq, false, 40, isRejected && s.role !== 'origin')}
          zIndexOffset={s.role === 'origin' ? 400 : 500}
          title={isRejected ? `${stopTitle(s)} — rejected pairing` : stopTitle(s)}
        >
          {popupStop && s.role === popupStop.role && s.requestId === popupStop.requestId && (
            <LeafletPopup className="xai-decision-popup" autoPan={false}>
              <HighlightPopup highlight={highlight} route={route} />
            </LeafletPopup>
          )}
        </LeafletMarker>
      ))}
    </>
  );
}

function LeafletHighlight({ highlight, viewMode = 'combined' }) {
  const route = useOperationalRoute(highlight);
  const stops = useDecoratedStops(highlight, route);
  const { status, path } = route.geometry;
  const isRejected = decisionStateMeta(highlight.status, highlight.decision).tone === 'danger';

  const showSeparate = viewMode === 'separate' && highlight.isShared;
  const separateLegs = useSeparateRoutes(showSeparate ? highlight : null);

  // Popup always attaches to this request's own pickup, wherever that stop
  // ends up rendered (combined sequence or its own separate leg) — see the
  // matching note on the Google side for why this is more reliable than
  // "the combined route's first stop".
  const popupStop = { role: 'pickup', requestId: highlight.requestId };

  return (
    <>
      {showSeparate ? (
        separateLegs.map((leg) => (
          <LeafletRouteSegment
            key={leg.requestId}
            keyPrefix={`leg-${leg.requestId}`}
            status={leg.geometry.status}
            path={leg.geometry.path}
            stops={decorateLegStops(leg)}
            isRejected={false}
            highlight={highlight}
            route={route}
            popupStop={leg.requestId === highlight.requestId ? popupStop : null}
          />
        ))
      ) : (
        <LeafletRouteSegment
          keyPrefix="combined"
          status={status}
          path={path}
          stops={stops}
          isRejected={isRejected}
          highlight={highlight}
          route={route}
          popupStop={popupStop}
        />
      )}
    </>
  );
}

export default function XAIHighlightLayer({ highlight, variant = 'google', viewMode = 'combined' }) {
  if (!highlight) return null;
  if (variant === 'leaflet') return <LeafletHighlight highlight={highlight} viewMode={viewMode} />;
  return <GoogleHighlight highlight={highlight} viewMode={viewMode} />;
}
