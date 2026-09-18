import React, { useMemo } from 'react';
import { Marker as GoogleMarker } from '@react-google-maps/api';
import { Marker as LeafletMarker, Tooltip as LeafletTooltip } from 'react-leaflet';
import { vehicleStatusMeta, vehicleTypeMeta } from '../../utils/requestSemantics';
import {
  googleVehicleIcon, leafletVehicleIcon,
  googleClusterIcon, leafletClusterIcon,
} from './markerIcons';

/**
 * Fleet layer — every vehicle whose position the system actually holds.
 *
 * Source: `/api/vehicles/locations`. Vehicles without a recorded coordinate are
 * omitted server-side rather than placed on a stand-in landmark, so every
 * marker here is a position the platform genuinely has.
 *
 * `density`:
 *   'all'    — the whole fleet (Live Operations)
 *   'active' — only vehicles currently on a trip (Overview / decision views,
 *              where the working fleet is the point and idle vehicles are noise)
 *
 * CLUSTERING. The fleet parks many vehicles on near-identical coordinates, so
 * at network zoom 110 individual markers render as one unreadable glowing
 * blob. Co-located vehicles are therefore grouped into a counted badge whose
 * ring takes the dominant status colour. Nothing is dropped — the counts are
 * exact and zooming in splits clusters back into individual vehicles — and the
 * cell size is derived from zoom so clustering disappears at street level.
 *
 * Vehicles are dimmed rather than removed when something else is selected, so
 * the selection dominates without losing operational context.
 */

/** Cell size in degrees for the current zoom (~1 km at z12, ~60 m at z16). */
function cellSizeForZoom(zoom) {
  const z = Number.isFinite(zoom) ? zoom : 12;
  return 360 / Math.pow(2, z + 3);
}

function buildGroups(vehicles, zoom, enabled) {
  if (!enabled) {
    return vehicles.map((v) => ({ key: `v-${v.vehicle_id}`, members: [v], lat: v.lat, lng: v.lng }));
  }
  const cell = cellSizeForZoom(zoom);
  const buckets = new Map();
  vehicles.forEach((v) => {
    const gx = Math.round(v.lat / cell);
    const gy = Math.round(v.lng / cell);
    const k = `${gx}:${gy}`;
    if (!buckets.has(k)) buckets.set(k, []);
    buckets.get(k).push(v);
  });
  return [...buckets.entries()].map(([k, members]) => ({
    key: k,
    members,
    // Cluster sits at the mean of its members, so the badge is where the
    // vehicles actually are rather than on an arbitrary representative.
    lat: members.reduce((a, v) => a + v.lat, 0) / members.length,
    lng: members.reduce((a, v) => a + v.lng, 0) / members.length,
  }));
}

/** The status that most members share — drives the cluster ring colour. */
function dominantStatus(members) {
  const counts = {};
  members.forEach((v) => {
    const k = String(v.status || 'Unknown');
    counts[k] = (counts[k] || 0) + 1;
  });
  const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
  return vehicleStatusMeta(top ? top[0] : null);
}

function vehicleLabel(v) {
  const status = vehicleStatusMeta(v.status);
  const type = vehicleTypeMeta(v.vehicle_type);
  return (
    `${type.label} ${v.vehicle_name || `#${v.vehicle_id}`} — ${status.label}` +
    (v.driver_name && v.driver_name !== 'Unassigned' ? ` · ${v.driver_name}` : '') +
    (v.registration_number ? ` · ${v.registration_number}` : '')
  );
}

function clusterLabel(members) {
  const counts = {};
  members.forEach((v) => {
    const m = vehicleStatusMeta(v.status);
    counts[m.label] = (counts[m.label] || 0) + 1;
  });
  const parts = Object.entries(counts).map(([k, n]) => `${n} ${k.toLowerCase()}`);
  return `${members.length} vehicles — ${parts.join(', ')}`;
}

export default function FleetLayer({
  vehicles = [],
  variant = 'leaflet',
  density = 'all',
  dimmed = false,
  cluster = true,
  zoom = 12,
  selectedVehicleId = null,
  onSelectVehicle,
  onZoomToCluster,
}) {
  const shown = useMemo(() => {
    const usable = vehicles.filter((v) => Number.isFinite(v.lat) && Number.isFinite(v.lng));
    if (density === 'active') {
      return usable.filter((v) => String(v.status || '').toLowerCase() === 'busy');
    }
    return usable;
  }, [vehicles, density]);

  // A selected vehicle is always drawn individually, never folded into a badge.
  const groups = useMemo(
    () => buildGroups(shown, zoom, cluster),
    [shown, zoom, cluster],
  );

  return (
    <>
      {groups.map((g) => {
        const hasSelected = selectedVehicleId != null
          && g.members.some((v) => v.vehicle_id === selectedVehicleId);

        if (g.members.length > 1 && !hasSelected) {
          const status = dominantStatus(g.members);
          const label = clusterLabel(g.members);
          if (variant === 'google') {
            return (
              <GoogleMarker
                key={`cl-${g.key}`}
                position={{ lat: g.lat, lng: g.lng }}
                icon={googleClusterIcon(g.members.length, status.color, dimmed)}
                zIndex={dimmed ? 2 : 28}
                title={label}
                onClick={onZoomToCluster ? () => onZoomToCluster(g) : undefined}
              />
            );
          }
          return (
            <LeafletMarker
              key={`cl-${g.key}`}
              position={[g.lat, g.lng]}
              icon={leafletClusterIcon(g.members.length, status.color, dimmed)}
              zIndexOffset={dimmed ? -200 : 90}
              eventHandlers={onZoomToCluster ? { click: () => onZoomToCluster(g) } : undefined}
            >
              <LeafletTooltip direction="top" offset={[0, -16]} opacity={1} className="admfe-tooltip">
                {label}
              </LeafletTooltip>
            </LeafletMarker>
          );
        }

        return g.members.map((v) => {
          const status = vehicleStatusMeta(v.status);
          const type = vehicleTypeMeta(v.vehicle_type);
          const isSelected = selectedVehicleId === v.vehicle_id;
          const isDimmed = dimmed && !isSelected;
          if (variant === 'google') {
            return (
              <GoogleMarker
                key={`veh-${v.vehicle_id}`}
                position={{ lat: v.lat, lng: v.lng }}
                icon={googleVehicleIcon(type.key, status.color, isDimmed, isSelected)}
                zIndex={isSelected ? 45 : isDimmed ? 2 : 30}
                title={vehicleLabel(v)}
                onClick={onSelectVehicle ? () => onSelectVehicle(v) : undefined}
              />
            );
          }
          return (
            <LeafletMarker
              key={`veh-${v.vehicle_id}`}
              position={[v.lat, v.lng]}
              icon={leafletVehicleIcon(type.key, status.color, isDimmed, isSelected)}
              zIndexOffset={isSelected ? 300 : isDimmed ? -200 : 100}
              eventHandlers={onSelectVehicle ? { click: () => onSelectVehicle(v) } : undefined}
            >
              {/* Labels on hover only — labelling 100+ vehicles at once would
                  bury the map in text. */}
              <LeafletTooltip direction="top" offset={[0, -14]} opacity={1} className="admfe-tooltip">
                {vehicleLabel(v)}
              </LeafletTooltip>
            </LeafletMarker>
          );
        });
      })}
    </>
  );
}
