import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { GoogleMap, useJsApiLoader } from '@react-google-maps/api';
import { MapContainer, TileLayer, Marker as LeafletMarker, Popup as LeafletPopup, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import RequestMarkers from './RequestMarkers';
import MarkerPopup from './MarkerPopup';
import MapControls from './MapControls';
import XAIHighlightLayer from './XAIHighlightLayer';
import FleetLayer from './FleetLayer';
import ActiveTripsLayer from './ActiveTripsLayer';
import { requestTypeMeta } from '../../utils/requestSemantics';
import { leafletQueueIcon } from './markerIcons';
import 'leaflet/dist/leaflet.css';

import { COIMBATORE_CENTER } from '../../utils/coimbatore';
const DEFAULT_ZOOM = 12;

/**
 * Basemap source — configurable, because deployments differ in what tile
 * provider (and key) they have available.
 *
 * Default is the plain, unfiltered OpenStreetMap "Carto" palette — the same
 * familiar light basemap look as Google Maps' default style (tan land,
 * white/yellow roads, light-blue water). Point VITE_MAP_TILE_URL at a
 * different provider to swap the source; a previous revision of this file
 * shipped a CSS filter that tinted these tiles dark navy (VITE_MAP_TILE_
 * TREATMENT=osm-dark still applies it, for anyone who wants that look back),
 * but that is no longer the default.
 */
const TILE_URL = import.meta.env.VITE_MAP_TILE_URL
  || 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const TILE_ATTRIBUTION = import.meta.env.VITE_MAP_TILE_ATTRIBUTION
  || '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const TILE_SUBDOMAINS = import.meta.env.VITE_MAP_TILE_SUBDOMAINS || 'abc';
/** 'native' (default) leaves the OSM tiles in their normal light colors;
 *  'osm-dark' re-applies the old CSS darkening filter, for opt-in use. */
const TILE_TREATMENT = import.meta.env.VITE_MAP_TILE_TREATMENT || 'native';

const containerStyle = { width: '100%', height: '100%', borderRadius: '0.75rem' };

/**
 * Map modes — the three pages are the same engine with different intent.
 *
 *   network    (Overview)        whole-network picture: active corridors and
 *                                the working fleet, no single-trip inspector.
 *   operations (Live Operations) full detail: every vehicle, every pending
 *                                request, active corridors, selection focus.
 *   decision   (AI Insights)     one decision: its route and stops dominate,
 *                                everything else recedes hard.
 */
const MODE_CONFIG = {
  network:    { fleetDensity: 'active', showQueue: true,  showTrips: true,  baseDim: false, tripGeometry: true,  clusterFleet: true },
  operations: { fleetDensity: 'all',    showQueue: true,  showTrips: true,  baseDim: false, tripGeometry: true,  clusterFleet: true },
  decision:   { fleetDensity: 'active', showQueue: true,  showTrips: false, baseDim: true,  tripGeometry: false, clusterFleet: true },
};

// Google basemap: no custom `styles` array is passed to <GoogleMap> below, so
// it renders Google's own default light styling — the "normal map like
// Google" look — for any deployment that configures VITE_GOOGLE_MAPS_API_KEY.

// Leaflet queue markers reuse the shared, memoised icon factory so the fallback
// map encodes request type exactly like the Google map does (colour + glyph,
// never colour alone) and identical icons are not rebuilt on every poll tick.

function LeafletBoundsFitter({ requests, trigger }) {
  const map = useMap();
  useEffect(() => {
    if (trigger > 0 && requests && requests.length > 0) {
      const validPoints = requests.filter(r => r.pickup_lat && r.pickup_lng);
      if (validPoints.length > 0) {
        map.fitBounds(L.latLngBounds(validPoints.map(r => [r.pickup_lat, r.pickup_lng])), { padding: [40, 40] });
      }
    }
  }, [trigger, requests, map]);
  return null;
}

// Keeps the Leaflet viewport in sync with its container size — sidebar toggles,
// fullscreen and window resizes otherwise leave the tile grid stale.
function LeafletResizeWatcher() {
  const map = useMap();
  useEffect(() => {
    const el = map.getContainer();
    if (!el) return;
    let raf = 0;
    const invalidate = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => map.invalidateSize());
    };
    const ro = new ResizeObserver(invalidate);
    ro.observe(el);
    document.addEventListener('fullscreenchange', invalidate);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      document.removeEventListener('fullscreenchange', invalidate);
    };
  }, [map]);
  return null;
}

/** Reports the Leaflet zoom upward so the fleet layer can size its clusters. */
function LeafletZoomWatcher({ onZoom }) {
  const map = useMapEvents({ zoomend: () => onZoom(map.getZoom()) });
  useEffect(() => { onZoom(map.getZoom()); }, [map, onZoom]);
  return null;
}

function LeafletMapBridge({ onReady }) {
  const map = useMap();
  useEffect(() => {
    onReady(map);
    return () => onReady(null);
  }, [map, onReady]);
  return null;
}

function LeafletHighlightFitter({ points, trigger }) {
  const map = useMap();
  useEffect(() => {
    if (trigger > 0 && points && points.length > 0) {
      map.fitBounds(L.latLngBounds(points), { padding: [56, 56] });
    }
  }, [trigger, points, map]);
  return null;
}

export default function LiveMapContainer({
  requests = [],
  vehicles = [],
  activeTrips = [],
  selectedRequest,
  onSelectRequest,
  onClosePopup,
  selectedVehicleId = null,
  onSelectVehicle,
  xaiHighlight = null,
  xaiViewMode = 'combined',
  mode = 'operations',
  className = 'relative w-full h-[600px] rounded-xl overflow-hidden shadow-2xl border border-white/[0.08] bg-white/[0.02]',
}) {
  const cfg = MODE_CONFIG[mode] || MODE_CONFIG.operations;

  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '';
  const isGoogleKeyPresent = Boolean(apiKey && apiKey !== 'your_google_maps_api_key_here');

  const { isLoaded, loadError } = useJsApiLoader({
    googleMapsApiKey: isGoogleKeyPresent ? apiKey : '',
    id: 'google-map-script',
  });

  const mapRef = useRef(null);
  const leafletMapRef = useRef(null);
  const wrapperRef = useRef(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [leafletFitTrigger, setLeafletFitTrigger] = useState(0);
  const [leafletHighlightFitTrigger, setLeafletHighlightFitTrigger] = useState(0);
  const [zoom, setZoom] = useState(DEFAULT_ZOOM);

  const setLeafletMap = useCallback((map) => { leafletMapRef.current = map; }, []);
  const handleZoomChange = useCallback((z) => {
    setZoom((prev) => (prev === z ? prev : z));
  }, []);

  /** Clicking a fleet cluster zooms to it rather than opening 100 popups. */
  const handleZoomToCluster = useCallback((group) => {
    const target = Math.min((leafletMapRef.current?.getZoom?.() ?? mapRef.current?.getZoom?.() ?? DEFAULT_ZOOM) + 3, 18);
    if (mapRef.current && window.google) {
      mapRef.current.panTo({ lat: group.lat, lng: group.lng });
      mapRef.current.setZoom(target);
    } else if (leafletMapRef.current) {
      leafletMapRef.current.setView([group.lat, group.lng], target);
    }
  }, []);
  const onLoad = useCallback((map) => {
    mapRef.current = map;
    map.addListener('zoom_changed', () => setZoom(map.getZoom()));
  }, []);
  const onUnmount = useCallback(() => { mapRef.current = null; }, []);

  const handleFitBounds = useCallback(() => {
    const pts = [];
    requests.forEach(r => { if (r.pickup_lat && r.pickup_lng) pts.push([r.pickup_lat, r.pickup_lng]); });
    vehicles.forEach(v => { if (v.lat && v.lng) pts.push([v.lat, v.lng]); });
    if (pts.length === 0) return;
    if (mapRef.current && window.google) {
      const bounds = new window.google.maps.LatLngBounds();
      pts.forEach(([lat, lng]) => bounds.extend({ lat, lng }));
      mapRef.current.fitBounds(bounds);
    } else {
      setLeafletFitTrigger(prev => prev + 1);
    }
  }, [requests, vehicles]);

  const handleRecenter = useCallback(() => {
    if (mapRef.current && window.google) {
      mapRef.current.panTo(COIMBATORE_CENTER);
      mapRef.current.setZoom(DEFAULT_ZOOM);
    } else if (leafletMapRef.current) {
      leafletMapRef.current.panTo([COIMBATORE_CENTER.lat, COIMBATORE_CENTER.lng]);
      leafletMapRef.current.setZoom(DEFAULT_ZOOM);
    }
  }, []);

  const handleZoomIn = useCallback(() => {
    if (mapRef.current && window.google) mapRef.current.setZoom(mapRef.current.getZoom() + 1);
    else if (leafletMapRef.current) leafletMapRef.current.setZoom(leafletMapRef.current.getZoom() + 1);
  }, []);

  const handleZoomOut = useCallback(() => {
    if (mapRef.current && window.google) mapRef.current.setZoom(mapRef.current.getZoom() - 1);
    else if (leafletMapRef.current) leafletMapRef.current.setZoom(leafletMapRef.current.getZoom() - 1);
  }, []);

  const toggleFullscreen = useCallback(() => {
    if (!wrapperRef.current) return;
    if (!document.fullscreenElement) wrapperRef.current.requestFullscreen().catch(() => {});
    else document.exitFullscreen().catch(() => {});
  }, []);

  useEffect(() => {
    const onFullscreenChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  // Google Maps caches its viewport too: re-trigger resize on container change.
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el) return;
    let raf = 0;
    const invalidate = () => {
      const map = mapRef.current;
      if (!map) return;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        if (window.google?.maps?.event) window.google.maps.event.trigger(map, 'resize');
      });
    };
    const ro = new ResizeObserver(invalidate);
    ro.observe(el);
    document.addEventListener('fullscreenchange', invalidate);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      document.removeEventListener('fullscreenchange', invalidate);
    };
  }, []);

  const canUseGoogleMap = isGoogleKeyPresent && isLoaded && !loadError;

  // Investigation mode: when a decision or a trip is in focus, unrelated
  // objects recede so the selection is unambiguous.
  const hasFocus = Boolean(selectedRequest || xaiHighlight || selectedVehicleId);
  const dimUnrelated = hasFocus || cfg.baseDim;

  // Requests already drawn by the highlight layer are excluded from the queue
  // layer so they are not painted twice at different sizes.
  const highlightRequestIds = useMemo(
    () => new Set(xaiHighlight?.requestIds || []),
    [xaiHighlight],
  );
  const queueRequests = useMemo(
    () => (cfg.showQueue ? requests.filter(r => !highlightRequestIds.has(r.id)) : []),
    [requests, highlightRequestIds, cfg.showQueue],
  );

  // ── XAI highlight bounds ──────────────────────────────────────────────────
  const highlightPoints = useMemo(() => {
    if (!xaiHighlight) return [];
    const pts = [];
    (xaiHighlight.requestPoints || []).forEach(p => {
      if (p.pickup_lat && p.pickup_lng) pts.push([p.pickup_lat, p.pickup_lng]);
      if (p.drop_lat && p.drop_lng) pts.push([p.drop_lat, p.drop_lng]);
    });
    (xaiHighlight.routeStops || []).forEach(s => {
      if (s && s.lat && s.lng) pts.push([s.lat, s.lng]);
    });
    if (xaiHighlight.driver?.lat && xaiHighlight.driver?.lng) pts.push([xaiHighlight.driver.lat, xaiHighlight.driver.lng]);
    if (xaiHighlight.vehicle?.lat && xaiHighlight.vehicle?.lng) pts.push([xaiHighlight.vehicle.lat, xaiHighlight.vehicle.lng]);
    return pts;
  }, [xaiHighlight]);

  // Stable fingerprint of the framed coordinates. Polling rebuilds the
  // highlight object every tick, so keying the refit on object identity re-ran
  // fitBounds ~24×/minute and yanked the viewport back mid-pan. The viewport
  // now moves only when the SELECTED ROUTE's geography actually changes, or
  // when the operator presses Fit / Recenter.
  const highlightBoundsKey = useMemo(
    () => highlightPoints.map(([lat, lng]) => `${lat.toFixed(5)},${lng.toFixed(5)}`).join('|'),
    [highlightPoints],
  );

  useEffect(() => {
    if (!highlightBoundsKey) return;
    if (mapRef.current && window.google) {
      const bounds = new window.google.maps.LatLngBounds();
      highlightPoints.forEach(([lat, lng]) => bounds.extend({ lat, lng }));
      mapRef.current.fitBounds(bounds);
    } else {
      setLeafletHighlightFitTrigger(t => t + 1);
    }
    // `highlightPoints` is deliberately not a dependency: `highlightBoundsKey`
    // is its stable coordinate fingerprint.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightBoundsKey, canUseGoogleMap]);

  const excludeTripIds = useMemo(
    () => (xaiHighlight?.tripId ? [xaiHighlight.tripId] : []),
    [xaiHighlight],
  );

  return (
    // `isolation: isolate` is load-bearing, not cosmetic. Leaflet gives its
    // internal panes z-index 200–700; without a stacking context here those
    // panes compete with the page's own z-10/20/30 overlays in the SAME
    // context, so the marker (600), tooltip (650) and popup (700) panes paint
    // straight through the floating glass panels. Isolating the map confines
    // Leaflet's z-indices to this subtree.
    <div ref={wrapperRef} className={className} style={{ isolation: 'isolate' }}>
      {canUseGoogleMap ? (
        <GoogleMap
          mapContainerStyle={containerStyle}
          center={COIMBATORE_CENTER}
          zoom={DEFAULT_ZOOM}
          onLoad={onLoad}
          onUnmount={onUnmount}
          options={{
            disableDefaultUI: false,
            zoomControl: false,
            mapTypeControl: false,
            streetViewControl: false,
            fullscreenControl: false,
          }}
        >
          {/* Layer order below matches the operational hierarchy:
              basemap → active corridors → fleet → requests → selected route. */}
          {cfg.showTrips && (
            <ActiveTripsLayer
              trips={activeTrips}
              variant="google"
              excludeTripIds={excludeTripIds}
              withGeometry={cfg.tripGeometry}
              dimmed={dimUnrelated}
            />
          )}
          <FleetLayer
            vehicles={vehicles}
            variant="google"
            density={cfg.fleetDensity}
            dimmed={dimUnrelated}
            cluster={cfg.clusterFleet}
            zoom={zoom}
            selectedVehicleId={selectedVehicleId}
            onSelectVehicle={onSelectVehicle}
            onZoomToCluster={handleZoomToCluster}
          />
          <RequestMarkers
            requests={queueRequests}
            selectedRequest={selectedRequest}
            onSelectRequest={onSelectRequest}
            onClosePopup={onClosePopup}
            dimmed={dimUnrelated}
          />
          {xaiHighlight && <XAIHighlightLayer highlight={xaiHighlight} variant="google" viewMode={xaiViewMode} />}
        </GoogleMap>
      ) : (
        /* Leaflet / OpenStreetMap fallback when no Google Maps key is present */
        <MapContainer
          center={[COIMBATORE_CENTER.lat, COIMBATORE_CENTER.lng]}
          zoom={DEFAULT_ZOOM}
          className={TILE_TREATMENT === 'native' ? 'leaflet-native-dark' : 'leaflet-dark'}
          style={{ width: '100%', height: '100%', borderRadius: '0.75rem' }}
          zoomControl={false}
        >
          <TileLayer
            className="admfe-base-tiles"
            attribution={TILE_ATTRIBUTION}
            url={TILE_URL}
            subdomains={TILE_SUBDOMAINS}
            maxZoom={20}
          />

          <LeafletBoundsFitter requests={requests} trigger={leafletFitTrigger} />
          <LeafletResizeWatcher />
          <LeafletMapBridge onReady={setLeafletMap} />
          <LeafletZoomWatcher onZoom={handleZoomChange} />
          <LeafletHighlightFitter points={highlightPoints} trigger={leafletHighlightFitTrigger} />

          {cfg.showTrips && (
            <ActiveTripsLayer
              trips={activeTrips}
              variant="leaflet"
              excludeTripIds={excludeTripIds}
              withGeometry={cfg.tripGeometry}
              dimmed={dimUnrelated}
            />
          )}

          <FleetLayer
            vehicles={vehicles}
            variant="leaflet"
            density={cfg.fleetDensity}
            dimmed={dimUnrelated}
            cluster={cfg.clusterFleet}
            zoom={zoom}
            selectedVehicleId={selectedVehicleId}
            onSelectVehicle={onSelectVehicle}
            onZoomToCluster={handleZoomToCluster}
          />

          {queueRequests.map((req) => {
            if (!req.pickup_lat || !req.pickup_lng) return null;
            const meta = requestTypeMeta(req.request_type);
            const isSelected = req.id === selectedRequest?.id;
            const isDimmed = dimUnrelated && !isSelected;
            return (
              <LeafletMarker
                key={req.id}
                position={[req.pickup_lat, req.pickup_lng]}
                icon={leafletQueueIcon(meta.color, meta.key, isDimmed, isSelected ? 34 : isDimmed ? 24 : 30)}
                zIndexOffset={isSelected ? 500 : isDimmed ? -100 : 200}
                eventHandlers={{ click: () => onSelectRequest?.(req) }}
              >
                {/* autoPan MUST stay off. Leaflet re-runs its auto-pan every
                    time an open popup re-renders, and the queue poll rebuilds
                    the request objects every few seconds — so an open popup
                    dragged the viewport a little on every tick, fighting the
                    operator. The map moves only when the selected route's
                    geography changes or the operator presses Fit/Recenter. */}
                <LeafletPopup autoPan={false} closeButton={false}>
                  <MarkerPopup request={req} />
                </LeafletPopup>
              </LeafletMarker>
            );
          })}

          {xaiHighlight && <XAIHighlightLayer highlight={xaiHighlight} variant="leaflet" viewMode={xaiViewMode} />}
        </MapContainer>
      )}

      <div className="absolute bottom-24 right-6 z-20">
        <MapControls
          onFitBounds={handleFitBounds}
          onRecenter={handleRecenter}
          onZoomIn={handleZoomIn}
          onZoomOut={handleZoomOut}
          isFullscreen={isFullscreen}
          onToggleFullscreen={toggleFullscreen}
        />
      </div>
    </div>
  );
}
