/**
 * Request / operational semantics — the SINGLE source of truth for how the
 * operations map and the XAI surface encode meaning as colour + icon + label.
 *
 * Why this file exists
 * --------------------
 * Before this module the same three request types were painted with six
 * mutually contradictory palettes (RequestMarkers.MARKER_COLORS,
 * XAIHighlightLayer inline literals, TripDetailsPanel.TYPE_META,
 * MarkerPopup.TYPE_META, DecisionCard.TYPE_META, KpiBar/ActivityBar).  Most
 * damagingly, the live-map marker layer painted FOOD and PARCEL the identical
 * purple while the XAI highlight layer on the SAME map painted ride blue /
 * food orange / parcel purple.  Type was therefore unreadable.
 *
 * Rules encoded here
 * ------------------
 *  1. REQUEST TYPE and ACTIVE ROUTE are separate channels.  A food request is
 *     orange; the active route for that food request is still cyan.  Type
 *     colour never leaks into route colour.
 *  2. Meaning is never carried by colour alone — every type and every state
 *     ships an icon and a text label alongside its colour.
 *  3. Types come from the application data (`request.request_type`).  Unknown
 *     types degrade to a neutral slate identity that echoes the raw string
 *     rather than being silently mislabelled as "ride".
 */

import { User, Utensils, Package, Circle, MapPin, Flag, Navigation, Truck } from 'lucide-react';

// ── Request type channel ────────────────────────────────────────────────────

export const REQUEST_TYPE_META = {
  ride: {
    key: 'ride',
    label: 'Ride',
    longLabel: 'Passenger',
    color: '#3B82F6',      // blue
    Icon: User,
    chipClass: 'bg-[#3B82F6]/15 text-[#3B82F6] border-[#3B82F6]/40',
  },
  food: {
    key: 'food',
    label: 'Food',
    longLabel: 'Food delivery',
    color: '#F97316',      // orange
    Icon: Utensils,
    chipClass: 'bg-[#F97316]/15 text-[#F97316] border-[#F97316]/40',
  },
  parcel: {
    key: 'parcel',
    label: 'Parcel',
    longLabel: 'Parcel delivery',
    color: '#A855F7',      // purple
    Icon: Package,
    chipClass: 'bg-[#A855F7]/15 text-[#A855F7] border-[#A855F7]/40',
  },
};

/** Neutral identity for any request type the system starts emitting later. */
const UNKNOWN_TYPE_META = {
  key: 'other',
  label: 'Other',
  longLabel: 'Other request',
  color: '#94A3B8',        // slate
  Icon: Circle,
  chipClass: 'bg-white/10 text-white/70 border-white/20',
};

/**
 * Resolve the semantic identity of a request type string coming from the API.
 * Unknown values keep their own label instead of being disguised as a ride.
 *
 * @param {string|null|undefined} rawType  `request_type` as stored/served
 * @returns {{key:string,label:string,longLabel:string,color:string,Icon:Function,chipClass:string}}
 */
export function requestTypeMeta(rawType) {
  const key = String(rawType || '').trim().toLowerCase();
  if (REQUEST_TYPE_META[key]) return REQUEST_TYPE_META[key];
  if (!key) return UNKNOWN_TYPE_META;
  return {
    ...UNKNOWN_TYPE_META,
    label: key.charAt(0).toUpperCase() + key.slice(1),
    longLabel: key.charAt(0).toUpperCase() + key.slice(1),
  };
}

export function requestTypeColor(rawType) {
  return requestTypeMeta(rawType).color;
}

// ── Route channel (deliberately independent of request type) ────────────────

/** The SELECTED operational route. Always cyan, never type-coloured. */
export const ROUTE_ACTIVE_COLOR = '#00F0FF';
/** Other dispatched trips running right now — present but subordinate, so the
 *  selected route stays unambiguous. */
export const ROUTE_BACKGROUND_COLOR = '#2A7A8C';
/** A route drawn from stops only, because road geometry was unavailable. */
export const ROUTE_FALLBACK_COLOR = '#64748B';
/** Vehicle / driver marker. */
export const VEHICLE_COLOR = '#38BDF8';

// ── Fleet channel ───────────────────────────────────────────────────────────

/**
 * Vehicle status → state colour + label. Colours come from the operational
 * state channel below (green = serving, amber = idle-but-usable, red = out of
 * service) so fleet state reads the same way as feasibility state.
 */
export const VEHICLE_STATUS_META = {
  busy:        { key: 'busy',        label: 'On trip',     color: '#22C55E' },
  available:   { key: 'available',   label: 'Available',   color: '#38BDF8' },
  maintenance: { key: 'maintenance', label: 'Maintenance', color: '#F59E0B' },
  offline:     { key: 'offline',     label: 'Offline',     color: '#EF4444' },
};

export function vehicleStatusMeta(status) {
  const k = String(status || '').trim().toLowerCase();
  return VEHICLE_STATUS_META[k] || {
    key: 'unknown',
    label: status ? String(status) : 'Unknown',
    color: '#94A3B8',
  };
}

/** Vehicle type → glyph key. Unknown types fall back to a generic vehicle. */
export function vehicleTypeMeta(vehicleType) {
  const t = String(vehicleType || '').toLowerCase();
  if (t.includes('bike') || t.includes('scooter')) return { key: 'bike', label: vehicleType || 'Bike', Icon: Truck };
  if (t.includes('auto') || t.includes('rick')) return { key: 'auto', label: vehicleType || 'Auto', Icon: Truck };
  if (t.includes('truck') || t.includes('van')) return { key: 'truck', label: vehicleType || 'Truck', Icon: Truck };
  return { key: 'car', label: vehicleType || 'Vehicle', Icon: Truck };
}

// ── Operational state channel ───────────────────────────────────────────────

export const STATE_META = {
  feasible:   { label: 'Feasible',   color: '#22C55E', tone: 'success' },
  assigned:   { label: 'Assigned',   color: '#22C55E', tone: 'success' },
  completed:  { label: 'Completed',  color: '#22C55E', tone: 'success' },
  warning:    { label: 'Warning',    color: '#F59E0B', tone: 'warning' },
  infeasible: { label: 'Infeasible', color: '#EF4444', tone: 'danger'  },
  critical:   { label: 'Critical',   color: '#EF4444', tone: 'danger'  },
  neutral:    { label: 'Evaluated',  color: '#94A3B8', tone: 'neutral' },
};

/**
 * Map an A-DMFE explanation `status`/`decision` pair onto the state channel.
 * Uses only values the engine actually emits ("Compatible" / "Incompatible" /
 * "Pending" / "Evaluated", "Compatible for Batching" / "Standalone Direct
 * Routing"); anything else stays neutral rather than being guessed at.
 */
export function decisionStateMeta(status, decision) {
  const s = String(status || '').toLowerCase();
  const d = String(decision || '').toLowerCase();
  if (s === 'compatible' || d.includes('compatible for batching')) return STATE_META.feasible;
  if (d.includes('standalone')) return STATE_META.warning;
  if (s === 'incompatible') return STATE_META.warning;
  if (s === 'rejected' || d.includes('reject') || d.includes('infeasible')) return STATE_META.infeasible;
  return STATE_META.neutral;
}

// ── Stop role channel (pickup vs drop vs origin) ────────────────────────────

export const STOP_ROLE_META = {
  origin: { label: 'Vehicle',  Icon: Navigation, color: VEHICLE_COLOR },
  pickup: { label: 'Pickup',   Icon: MapPin,     color: '#22C55E' },
  drop:   { label: 'Drop-off', Icon: Flag,       color: '#EF4444' },
};

export function stopRoleMeta(role) {
  return STOP_ROLE_META[role] || STOP_ROLE_META.pickup;
}
