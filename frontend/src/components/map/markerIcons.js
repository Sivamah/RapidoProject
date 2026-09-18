/**
 * Operational marker glyphs for the A-DMFE map.
 * =============================================
 *
 * Every marker encodes FOUR independent channels, so meaning never rests on
 * colour alone:
 *
 *   SHAPE   → role      teardrop = pickup, rounded square = drop-off,
 *                       circle+arrow = vehicle origin
 *   COLOUR  → request   ride blue / food orange / parcel purple
 *             type      (from `requestSemantics`, never the route colour)
 *   GLYPH   → request   person / plate / parcel-box drawn inside the marker
 *             type
 *   NUMBER  → order     the stop's position in the OR-Tools sequence
 *
 * Icons are built once per (role, colour, sequence, size) and memoised: the
 * XAI dashboard re-renders on a 2.5 s poll, and rebuilding every data-URI and
 * every Leaflet DivIcon on each tick made Leaflet tear down and re-create the
 * whole marker layer four times a second.
 */

import L from 'leaflet';
import { VEHICLE_COLOR } from '../../utils/requestSemantics';

// ── Type glyphs, drawn in a local 24×24 space, fill-only for small sizes ─────

const GLYPHS = {
  ride: '<circle cx="12" cy="8" r="3.7"/><path d="M4.4 20.5c0-4.2 3.4-7.2 7.6-7.2s7.6 3 7.6 7.2Z"/>',
  food: '<path d="M3 10.6h18a9 9 0 0 1-18 0Z"/><rect x="2.2" y="18.4" width="19.6" height="2.4" rx="1.2"/>',
  parcel: '<rect x="3" y="6.6" width="18" height="14" rx="1.8"/><rect x="10.6" y="6.6" width="2.8" height="14" fill="#fff" fill-opacity="0.85"/><rect x="3" y="11.8" width="18" height="2.6" fill="#fff" fill-opacity="0.85"/>',
  other: '<circle cx="12" cy="12" r="6.2"/>',
  vehicle: '<path d="M12 2.2 21.4 21 12 16.6 2.6 21 12 2.2Z"/>',
  // Fleet glyphs — silhouettes rather than dots, so vehicle type is readable
  // at marker size without relying on colour.
  bike: '<circle cx="5.4" cy="17.2" r="3.4"/><circle cx="18.6" cy="17.2" r="3.4"/><path d="M8.6 8.2h4.1l3.4 6.1-1.9 1.1-3-5.4H9.9l-2.6 5.6-2-.9 3.3-6.5Z"/><path d="M13.4 4.6h3.9v2h-3.9z"/>',
  auto: '<path d="M3.4 15.6c0-4.9 3.8-8.6 8.6-8.6s8.6 3.7 8.6 8.6v1.9H3.4v-1.9Z"/><circle cx="6.6" cy="19.1" r="2.2"/><circle cx="17.4" cy="19.1" r="2.2"/><path d="M9.2 3.6h5.6v2.2H9.2z"/>',
  truck: '<path d="M2.2 7.4h11v9.2h-11z"/><path d="M13.2 10.4h4.2l3.4 3.5v2.7h-7.6z"/><circle cx="6.4" cy="18.4" r="2.3"/><circle cx="17.2" cy="18.4" r="2.3"/>',
  car: '<path d="M3.4 13.6 5.6 8.2c.3-.8 1-1.2 1.9-1.2h9c.8 0 1.6.4 1.9 1.2l2.2 5.4v4.2H3.4v-4.2Z"/><circle cx="7.2" cy="18.6" r="1.9" fill="#fff" fill-opacity="0.9"/><circle cx="16.8" cy="18.6" r="1.9" fill="#fff" fill-opacity="0.9"/>',
};

function glyph(typeKey, cx, cy, scale, color) {
  const body = GLYPHS[typeKey] || GLYPHS.other;
  const s = scale / 24;
  return (
    `<g transform="translate(${cx - scale / 2} ${cy - scale / 2}) scale(${s})" ` +
    `fill="${color}">${body}</g>`
  );
}

function seqBadge(seq, color) {
  if (seq === null || seq === undefined) return '';
  return (
    `<circle cx="35" cy="9" r="8.5" fill="#0A0F1A" stroke="${color}" stroke-width="2"/>` +
    `<text x="35" y="12.8" text-anchor="middle" font-family="system-ui,sans-serif" ` +
    `font-size="10.5" font-weight="700" fill="#ffffff">${seq}</text>`
  );
}

/**
 * Build the raw SVG string for one operational marker.
 *
 * @param {'pickup'|'drop'|'origin'} role
 * @param {string} color     request-type colour (ignored for `origin`)
 * @param {string} typeKey   'ride' | 'food' | 'parcel' | 'other'
 * @param {number|null} seq  position in the OR-Tools stop sequence
 * @param {boolean} dimmed   de-emphasised (investigation mode)
 * @param {boolean} rejected marker belongs to a rejected/infeasible decision —
 *                           draws a red ring in place of the seq badge instead
 *                           of implying the stop is part of a real dispatch.
 */
export function buildMarkerSvg(role, color, typeKey, seq, dimmed = false, rejected = false) {
  // DIMMED MUST NOT RECOLOUR. Request type is carried by `color`, so replacing
  // it with slate when the marker recedes deletes the type channel — a food
  // request stops being orange the moment anything else is selected. Recede
  // with opacity and by dropping the glow instead; ride stays blue, food
  // orange, parcel purple in every state.
  const fill = color;
  const opacity = dimmed ? 0.45 : 1;
  const glow = dimmed ? 'none' : `drop-shadow(0 0 7px ${fill})`;
  // Rejection is a state overlay, not a recolour — the pin keeps its request
  // type colour, but a red outline ring marks it as evaluated-and-declined
  // rather than an active stop, and no sequence number is drawn since a
  // rejected pairing has no real OR-Tools position.
  const rejectRing = rejected
    ? '<circle cx="35" cy="9" r="8.5" fill="#0A0F1A" stroke="#EF4444" stroke-width="2.4"/>' +
      '<path d="M31.6 5.6 38.4 12.4M38.4 5.6 31.6 12.4" stroke="#EF4444" stroke-width="1.8" stroke-linecap="round"/>'
    : '';

  let body;
  if (role === 'origin') {
    body =
      `<circle cx="22" cy="22" r="15" fill="${VEHICLE_COLOR}" stroke="#ffffff" stroke-width="2.4"/>` +
      glyph('vehicle', 22, 22, 17, '#0A0F1A');
  } else if (role === 'drop') {
    body =
      `<rect x="7" y="7" width="30" height="30" rx="9" fill="${fill}" stroke="#ffffff" stroke-width="2.4"/>` +
      `<rect x="11.5" y="11.5" width="21" height="21" rx="6" fill="#ffffff" fill-opacity="0.92"/>` +
      glyph(typeKey, 22, 22, 15, fill) +
      (rejected ? rejectRing : seqBadge(seq, fill));
  } else {
    body =
      `<path d="M22 50C22 50 6 32.5 6 20.5a16 16 0 0 1 32 0C38 32.5 22 50 22 50Z" ` +
      `fill="${fill}" stroke="#ffffff" stroke-width="2.4"/>` +
      `<circle cx="22" cy="20" r="10.5" fill="#ffffff" fill-opacity="0.94"/>` +
      glyph(typeKey, 22, 20, 15, fill) +
      (rejected ? rejectRing : seqBadge(seq, fill));
  }

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="52" viewBox="0 0 44 52" ` +
    `opacity="${opacity}" style="filter:${glow}">${body}</svg>`
  );
}

// ── Memoised icon factories ─────────────────────────────────────────────────

const _googleIcons = new Map();
const _leafletIcons = new Map();

function iconKey(role, color, typeKey, seq, dimmed, size, rejected) {
  return `${role}|${color}|${typeKey}|${seq}|${dimmed ? 1 : 0}|${size}|${rejected ? 1 : 0}`;
}

/** Anchor: pins hang from their tip, badges/circles sit on their centre. */
function anchorFor(role, size) {
  const h = size * (52 / 44);
  return role === 'pickup' ? [size / 2, h] : [size / 2, h / 2];
}

/**
 * Google Maps icon descriptor.  Requires `window.google.maps` to be loaded —
 * callers only render Google markers inside a loaded <GoogleMap>.
 */
export function googleMarkerIcon(role, color, typeKey, seq, dimmed = false, size = 40, rejected = false) {
  const key = iconKey(role, color, typeKey, seq, dimmed, size, rejected);
  let cached = _googleIcons.get(key);
  if (!cached) {
    const svg = buildMarkerSvg(role, color, typeKey, seq, dimmed, rejected);
    cached = {
      url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
      _size: size,
      _anchor: anchorFor(role, size),
    };
    _googleIcons.set(key, cached);
  }
  // Size/Point are Google SDK objects and cannot be built before the SDK
  // loads, so they are attached lazily on first use and then reused.
  if (!cached.scaledSize) {
    cached.scaledSize = new window.google.maps.Size(size, size * (52 / 44));
    cached.anchor = new window.google.maps.Point(cached._anchor[0], cached._anchor[1]);
  }
  return cached;
}

/** Leaflet DivIcon wrapping the same SVG, so both map modes look identical. */
export function leafletMarkerIcon(role, color, typeKey, seq, dimmed = false, size = 40, rejected = false) {
  const key = iconKey(role, color, typeKey, seq, dimmed, size, rejected);
  let icon = _leafletIcons.get(key);
  if (!icon) {
    const h = size * (52 / 44);
    const svg = buildMarkerSvg(role, color, typeKey, seq, dimmed, rejected);
    icon = L.divIcon({
      className: 'admfe-marker',
      html: `<div style="width:${size}px;height:${h}px;line-height:0">${svg.replace('width="44" height="52"', `width="${size}" height="${h}"`)}</div>`,
      iconSize: [size, h],
      iconAnchor: anchorFor(role, size),
    });
    _leafletIcons.set(key, icon);
  }
  return icon;
}

// ── Queue markers (background layer: pending requests on the live map) ───────

/**
 * Compact request marker for the live-queue layer.  Smaller and flatter than
 * an operational stop marker so the selected trip's route stays dominant, but
 * it carries the same colour + glyph pairing so type stays readable.
 */
export function buildQueueMarkerSvg(color, typeKey, dimmed = false) {
  // As above: the request-type colour survives dimming. A receded marker is
  // the SAME hue at lower opacity, with a thinner ring and no glow, and drawn
  // slightly smaller by the caller — hierarchy without losing semantics.
  const fill = color;
  const stroke = dimmed ? 'rgba(255,255,255,0.35)' : '#ffffff';
  const glow = dimmed
    ? 'none'
    : `drop-shadow(0 0 6px ${fill}) drop-shadow(0 2px 4px rgba(0,0,0,0.6))`;
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" viewBox="0 0 30 30" ` +
    `opacity="${dimmed ? 0.45 : 1}" style="filter:${glow}">` +
    `<circle cx="15" cy="15" r="12" fill="${fill}" stroke="${stroke}" ` +
    `stroke-width="${dimmed ? 1.2 : 2}"/>` +
    glyph(typeKey, 15, 15, 15, '#0A0F1A') +
    '</svg>'
  );
}

const _googleQueueIcons = new Map();
const _leafletQueueIcons = new Map();

export function googleQueueIcon(color, typeKey, dimmed = false, size = 30) {
  const key = `${color}|${typeKey}|${dimmed ? 1 : 0}|${size}`;
  let cached = _googleQueueIcons.get(key);
  if (!cached) {
    const svg = buildQueueMarkerSvg(color, typeKey, dimmed);
    cached = { url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`, _size: size };
    _googleQueueIcons.set(key, cached);
  }
  if (!cached.scaledSize) {
    cached.scaledSize = new window.google.maps.Size(size, size);
    cached.anchor = new window.google.maps.Point(size / 2, size / 2);
  }
  return cached;
}

export function leafletQueueIcon(color, typeKey, dimmed = false, size = 30) {
  const key = `${color}|${typeKey}|${dimmed ? 1 : 0}|${size}`;
  let icon = _leafletQueueIcons.get(key);
  if (!icon) {
    const svg = buildQueueMarkerSvg(color, typeKey, dimmed)
      .replace('width="30" height="30"', `width="${size}" height="${size}"`);
    icon = L.divIcon({
      className: 'admfe-queue-marker',
      html: `<div style="width:${size}px;height:${size}px;line-height:0">${svg}</div>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
    _leafletQueueIcons.set(key, icon);
  }
  return icon;
}


// ── Fleet markers ───────────────────────────────────────────────────────────

/**
 * Vehicle marker: a compact rounded-square chassis carrying the vehicle-type
 * glyph, wrapped in a status ring.
 *
 *   SHAPE  → it is a vehicle (distinct from request pins and drop squares)
 *   GLYPH  → vehicle type (bike / auto / truck / car)
 *   RING   → operational status (on trip / available / maintenance / offline)
 *
 * Kept deliberately smaller and flatter than an operational stop marker so a
 * fleet of 100+ reads as texture while the selected trip stays dominant.
 */
export function buildVehicleMarkerSvg(typeKey, statusColor, dimmed = false, selected = false) {
  // Vehicle blue and the status ring colour are semantics too, so they also
  // survive dimming; only opacity and glow recede.
  const body = VEHICLE_COLOR;
  const ring = statusColor;
  const glow = dimmed ? 'none' : `drop-shadow(0 0 ${selected ? 9 : 5}px ${ring})`;
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 28 28" ` +
    `opacity="${dimmed ? 0.4 : 1}" style="filter:${glow}">` +
    `<circle cx="14" cy="14" r="12.4" fill="none" stroke="${ring}" stroke-width="${selected ? 2.6 : 1.8}"/>` +
    `<rect x="4.4" y="4.4" width="19.2" height="19.2" rx="6" fill="${body}"/>` +
    glyph(typeKey, 14, 14, 15, '#06121F') +
    '</svg>'
  );
}

const _googleVehicleIcons = new Map();
const _leafletVehicleIcons = new Map();

export function googleVehicleIcon(typeKey, statusColor, dimmed = false, selected = false, size = 28) {
  const key = `${typeKey}|${statusColor}|${dimmed ? 1 : 0}|${selected ? 1 : 0}|${size}`;
  let cached = _googleVehicleIcons.get(key);
  if (!cached) {
    const svg = buildVehicleMarkerSvg(typeKey, statusColor, dimmed, selected);
    cached = { url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}` };
    _googleVehicleIcons.set(key, cached);
  }
  if (!cached.scaledSize) {
    cached.scaledSize = new window.google.maps.Size(size, size);
    cached.anchor = new window.google.maps.Point(size / 2, size / 2);
  }
  return cached;
}

export function leafletVehicleIcon(typeKey, statusColor, dimmed = false, selected = false, size = 28) {
  const key = `${typeKey}|${statusColor}|${dimmed ? 1 : 0}|${selected ? 1 : 0}|${size}`;
  let icon = _leafletVehicleIcons.get(key);
  if (!icon) {
    const svg = buildVehicleMarkerSvg(typeKey, statusColor, dimmed, selected)
      .replace('width="28" height="28"', `width="${size}" height="${size}"`);
    icon = L.divIcon({
      className: 'admfe-vehicle-marker',
      html: `<div style="width:${size}px;height:${size}px;line-height:0">${svg}</div>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
    _leafletVehicleIcons.set(key, icon);
  }
  return icon;
}


// ── Fleet cluster markers ───────────────────────────────────────────────────

/**
 * Cluster badge for co-located vehicles.
 *
 * The seeded fleet parks many vehicles on near-identical coordinates, so at
 * network zoom 110 individual markers collapse into one unreadable glowing
 * blob. Clustering keeps every vehicle represented — the count is exact and
 * the ring takes the colour of the dominant status — while letting the
 * selected route stay the brightest thing on the map. Nothing is hidden:
 * zooming in splits the cluster back into individual vehicles.
 */
export function buildClusterSvg(count, statusColor, dimmed = false) {
  const size = count >= 100 ? 44 : count >= 10 ? 38 : 32;
  const r = size / 2 - 2;
  // The cluster ring carries the dominant fleet status, so it keeps its colour
  // when dimmed as well.
  const ring = statusColor;
  const fill = 'rgba(10,18,32,0.92)';
  const fontSize = count >= 100 ? 13 : 12;
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" ` +
    `opacity="${dimmed ? 0.4 : 1}" style="filter:${dimmed ? 'none' : `drop-shadow(0 0 7px ${ring})`}">` +
    `<circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="${fill}" stroke="${ring}" stroke-width="2.2"/>` +
    `<circle cx="${size / 2}" cy="${size / 2}" r="${r - 4}" fill="none" stroke="${ring}" stroke-opacity="0.3" stroke-width="1"/>` +
    `<text x="${size / 2}" y="${size / 2 + fontSize * 0.36}" text-anchor="middle" ` +
    `font-family="system-ui,sans-serif" font-size="${fontSize}" font-weight="700" fill="#EAF6FF">${count}</text>` +
    '</svg>'
  );
}

const _googleClusterIcons = new Map();
const _leafletClusterIcons = new Map();

export function googleClusterIcon(count, statusColor, dimmed = false) {
  const key = `${count}|${statusColor}|${dimmed ? 1 : 0}`;
  let cached = _googleClusterIcons.get(key);
  if (!cached) {
    const size = count >= 100 ? 44 : count >= 10 ? 38 : 32;
    cached = {
      url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(buildClusterSvg(count, statusColor, dimmed))}`,
      _size: size,
    };
    _googleClusterIcons.set(key, cached);
  }
  if (!cached.scaledSize) {
    cached.scaledSize = new window.google.maps.Size(cached._size, cached._size);
    cached.anchor = new window.google.maps.Point(cached._size / 2, cached._size / 2);
  }
  return cached;
}

export function leafletClusterIcon(count, statusColor, dimmed = false) {
  const key = `${count}|${statusColor}|${dimmed ? 1 : 0}`;
  let icon = _leafletClusterIcons.get(key);
  if (!icon) {
    const size = count >= 100 ? 44 : count >= 10 ? 38 : 32;
    icon = L.divIcon({
      className: 'admfe-cluster-marker',
      html: `<div style="width:${size}px;height:${size}px;line-height:0">${buildClusterSvg(count, statusColor, dimmed)}</div>`,
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
    });
    _leafletClusterIcons.set(key, icon);
  }
  return icon;
}
