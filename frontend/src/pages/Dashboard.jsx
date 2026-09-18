import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Inbox, Route as RouteIcon, User, Truck, Gauge, Fuel, Cloud, CheckCircle2,
  ArrowUpRight, Layers, Activity, BrainCircuit, HeartPulse, Trophy,
  Server, Radio, AlertTriangle,
} from 'lucide-react';
import api from '../services/api';
import useOperationalNetwork from '../hooks/useOperationalNetwork';
import { REQUEST_TYPE_META, vehicleStatusMeta } from '../utils/requestSemantics';
import ActivityTimeline from '../components/notifications/ActivityTimeline';
import PageHeader from '../components/ui/PageHeader';
import StatusBadge from '../components/ui/StatusBadge';
import AnimatedNumber from '../components/ui/AnimatedNumber';

/**
 * OVERVIEW — data-only administration dashboard.
 *
 * No map lives here. The map is Live Operations' job (/live-map); Overview
 * answers "how is the network doing" in numbers, not in markers. Every figure
 * below comes from a real endpoint — /dashboard/stats, /dmfe/statistics,
 * /dmfe/trips, /vehicles/*, /simulation/queue|status, /notifications/timeline,
 * /xai/overview, /health — and a value the API did not supply renders as "—",
 * never as a plausible-looking placeholder.
 */

const fmtInt = (v) => (Number.isFinite(v) ? Math.round(v).toLocaleString() : '—');
const fmt1 = (v) => (Number.isFinite(v) ? v.toFixed(1) : '—');

// ── Top KPI card ─────────────────────────────────────────────────────────────

const TONES = {
  cyan:   { text: 'text-[#22D3EE]', bg: 'bg-[#22D3EE]/10', border: 'border-[#22D3EE]/25' },
  blue:   { text: 'text-brand-primary', bg: 'bg-brand-primary/10', border: 'border-brand-primary/25' },
  green:  { text: 'text-brand-success', bg: 'bg-brand-success/10', border: 'border-brand-success/25' },
  amber:  { text: 'text-brand-warning', bg: 'bg-brand-warning/10', border: 'border-brand-warning/25' },
  purple: { text: 'text-[#A855F7]', bg: 'bg-[#A855F7]/10', border: 'border-[#A855F7]/25' },
};

function KpiCard({ icon: Icon, label, value, unit, tone = 'cyan', sub }) {
  const t = TONES[tone] || TONES.cyan;
  const isNumeric = typeof value === 'number' && Number.isFinite(value);
  return (
    <div className="glass-card rounded-[20px] p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="section-label truncate">{label}</p>
          <div className="flex items-baseline gap-1.5 mt-2">
            <span className="text-[24px] font-display font-semibold text-white tabular-nums tracking-tight">
              {isNumeric ? <AnimatedNumber value={value} format={(v) => Math.round(v).toLocaleString()} /> : (value ?? '—')}
            </span>
            {unit && <span className="text-[12px] text-brand-text-muted">{unit}</span>}
          </div>
          {sub && <p className="text-[10.5px] text-brand-text-muted mt-1 truncate">{sub}</p>}
        </div>
        <div className={`h-9 w-9 rounded-xl border flex items-center justify-center shrink-0 ${t.bg} ${t.border}`}>
          <Icon className={`h-4 w-4 ${t.text}`} />
        </div>
      </div>
    </div>
  );
}

// ── Section shell ────────────────────────────────────────────────────────────

function SectionCard({ icon: Icon, title, action, children, className = '' }) {
  return (
    <div className={`glass-card rounded-[22px] p-5 flex flex-col ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[13px] font-bold text-white flex items-center gap-2">
          <Icon className="h-4 w-4 text-brand-primary" />
          {title}
        </h3>
        {action}
      </div>
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  );
}

function ProgressRow({ label, count, total, color, Icon }) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="flex items-center gap-1.5 text-[12px] text-brand-text-secondary">
          {Icon && <Icon className="h-3.5 w-3.5" style={{ color }} />}
          {label}
        </span>
        <span className="text-[12px] font-mono text-white tabular-nums">{count}</span>
      </div>
      <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: color, opacity: 0.85 }} />
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const navigate = useNavigate();

  const [dashboardStats, setDashboardStats] = useState(null);
  const [dmfeStats, setDmfeStats] = useState(null);
  const [trips, setTrips] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [xaiOverview, setXaiOverview] = useState(null);
  const [engineStatus, setEngineStatus] = useState(null);
  const [healthOk, setHealthOk] = useState(null);
  const aggPollRef = useRef(null);

  // Fleet + queue + active-trip positions — the same shared feed Live
  // Operations uses, so the two pages never disagree with each other.
  const { vehicles, stats: net, lastUpdated, error: netError } =
    useOperationalNetwork({ intervalMs: 8000 });

  const fetchAggregates = useCallback(async () => {
    const [
      statsRes, dmfeRes, tripsRes, tlRes, xaiRes, statusRes, healthRes,
    ] = await Promise.allSettled([
      api.get('/dashboard/stats'),
      api.get('/dmfe/statistics'),
      api.get('/dmfe/trips?limit=500'),
      api.get('/notifications/timeline?limit=10'),
      api.get('/xai/overview'),
      api.get('/simulation/status'),
      api.get('/health'),
    ]);
    if (statsRes.status === 'fulfilled') setDashboardStats(statsRes.value.data);
    if (dmfeRes.status === 'fulfilled') setDmfeStats(dmfeRes.value.data);
    if (tripsRes.status === 'fulfilled') setTrips(Array.isArray(tripsRes.value.data) ? tripsRes.value.data : []);
    if (tlRes.status === 'fulfilled') setTimeline(tlRes.value.data || []);
    if (xaiRes.status === 'fulfilled') setXaiOverview(xaiRes.value.data);
    if (statusRes.status === 'fulfilled') setEngineStatus(statusRes.value.data);
    setHealthOk(healthRes.status === 'fulfilled' && healthRes.value.data?.status === 'ok');
  }, []);

  useEffect(() => {
    fetchAggregates();
    aggPollRef.current = setInterval(() => {
      if (document.visibilityState === 'visible') fetchAggregates();
    }, 20000);
    return () => clearInterval(aggPollRef.current);
  }, [fetchAggregates]);

  // ── Derived: trip status + shared/individual + top vehicles ────────────────
  // All derived from the same /dmfe/trips rows — real rows, client-aggregated,
  // exactly like the request-type and fleet-status breakdowns already do.
  const tripBreakdown = useMemo(() => {
    if (!trips) return null;
    const byStatus = {};
    let shared = 0;
    const byVehicle = new Map();
    trips.forEach((t) => {
      const st = t.status || 'Unknown';
      byStatus[st] = (byStatus[st] || 0) + 1;
      if (t.is_shared) shared += 1;
      if (t.vehicle_id != null) {
        const key = t.vehicle_id;
        const row = byVehicle.get(key) || {
          vehicleId: key,
          name: t.vehicle_name || `Vehicle #${key}`,
          trips: 0,
          distanceSavedKm: 0,
          co2SavedKg: 0,
        };
        row.trips += 1;
        row.distanceSavedKm += Number(t.distance_saved_km) || 0;
        row.co2SavedKg += Number(t.co2_saved_kg) || 0;
        byVehicle.set(key, row);
      }
    });
    const topVehicles = [...byVehicle.values()]
      .sort((a, b) => b.trips - a.trips || b.distanceSavedKm - a.distanceSavedKm)
      .slice(0, 5);
    return {
      total: trips.length,
      byStatus,
      shared,
      individual: trips.length - shared,
      completed: byStatus.Completed || 0,
      topVehicles,
    };
  }, [trips]);

  const vehicleUtilizationPct = useMemo(() => {
    const total = net.fleetTotal;
    const busy = net.byVehicleStatus?.Busy;
    if (!Number.isFinite(total) || total <= 0 || !Number.isFinite(busy)) return null;
    return (busy / total) * 100;
  }, [net]);

  const requestTypeRows = [
    ['ride', REQUEST_TYPE_META.ride],
    ['food', REQUEST_TYPE_META.food],
    ['parcel', REQUEST_TYPE_META.parcel],
  ];

  const fleetEntries = Object.entries(net.byVehicleStatus || {}).sort((a, b) => b[1] - a[1]);

  const tripStatusOrder = ['Active', 'Completed', 'Planned', 'Cancelled'];
  const tripStatusColor = { Active: '#22D3EE', Completed: '#22C55E', Planned: '#F59E0B', Cancelled: '#EF4444' };

  const engineLabel = engineStatus
    ? (engineStatus.running && !engineStatus.paused ? 'Running' : engineStatus.paused ? 'Paused' : 'Stopped')
    : '—';
  const engineTone = engineStatus?.running && !engineStatus?.paused ? 'success' : engineStatus?.paused ? 'warning' : 'neutral';

  const feedFresh = Boolean(lastUpdated) && !netError;
  const initialLoading = !dashboardStats && !lastUpdated;

  if (initialLoading) {
    return (
      <div className="flex items-center justify-center h-[70vh]">
        <div className="flex flex-col items-center gap-4">
          <div className="h-12 w-12 rounded-full border-2 border-white/10 border-t-brand-primary animate-spin" />
          <p className="text-[12px] font-medium text-brand-primary uppercase tracking-widest">Loading operational network…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-10 max-w-[1500px] mx-auto">
      <PageHeader
        eyebrow="Overview"
        live
        title="Operational Overview"
        description="Network-wide totals — demand, fleet, trips and AI decisions. For the live map and per-trip inspection, open Live Operations."
        actions={
          <div className="flex items-center gap-2.5">
            <StatusBadge
              tone={feedFresh ? 'success' : 'danger'}
              label={feedFresh ? 'Live feed connected' : 'Feed unavailable'}
              pulse={feedFresh}
            />
            <button onClick={() => navigate('/live-map')} className="btn-primary">
              Live Operations <ArrowUpRight className="h-3.5 w-3.5" />
            </button>
          </div>
        }
      />

      {/* ── TOP KPIs ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-4">
        <KpiCard icon={Inbox} label="Active Requests" tone="cyan"
                 value={net.activeRequests} sub={`${fmtInt(net.pending)} queued · ${fmtInt(net.inFlightRequests)} in flight`} />
        <KpiCard icon={RouteIcon} label="Shared Trips" tone="blue"
                 value={dmfeStats ? dmfeStats.total_shared_trips : undefined}
                 sub={dmfeStats ? `${fmt1(dmfeStats.batch_rate_pct)}% batch rate` : undefined} />
        <KpiCard icon={User} label="Individual Trips" tone="purple"
                 value={dmfeStats ? dmfeStats.total_trips - dmfeStats.total_shared_trips : undefined} />
        <KpiCard icon={Truck} label="Vehicles" tone="blue"
                 value={net.fleetTotal} sub={net.fleetAvailable === null ? undefined : `${fmtInt(net.fleetAvailable)} available`} />
        <KpiCard icon={Gauge} label="Vehicle Utilization" tone="green" unit="%"
                 value={vehicleUtilizationPct === null ? undefined : Math.round(vehicleUtilizationPct)}
                 sub={net.fleetTotal ? `${fmtInt(net.byVehicleStatus?.Busy || 0)} of ${fmtInt(net.fleetTotal)} deployed` : undefined} />
        <KpiCard icon={Fuel} label="Fuel Saved" tone="amber" unit="L"
                 value={dashboardStats && Number.isFinite(dashboardStats.fuel_saved) ? Math.round(dashboardStats.fuel_saved) : undefined} />
        <KpiCard icon={Cloud} label="CO₂ Reduction" tone="green" unit="kg"
                 value={dashboardStats && Number.isFinite(dashboardStats.co2_reduction) ? Math.round(dashboardStats.co2_reduction) : undefined} />
        <KpiCard icon={CheckCircle2} label="Completed Trips" tone="cyan"
                 value={tripBreakdown ? tripBreakdown.completed : undefined}
                 sub={tripBreakdown ? `of ${fmtInt(tripBreakdown.total)} total` : undefined} />
      </div>

      {/* ── Service demand / Fleet status / Trip status ─────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <SectionCard icon={Activity} title="Service Demand">
          {net.pending === 0 ? (
            <p className="text-[12px] text-brand-text-muted italic">No pending requests in the network.</p>
          ) : (
            <div className="space-y-3">
              {requestTypeRows.map(([key, meta]) => (
                <ProgressRow key={key} label={meta.label} Icon={meta.Icon} color={meta.color}
                             count={net.byType[key] || 0} total={net.pending} />
              ))}
            </div>
          )}
        </SectionCard>

        <SectionCard icon={Layers} title="Fleet Status">
          {fleetEntries.length === 0 ? (
            <p className="text-[12px] text-brand-text-muted italic">No vehicle positions reported.</p>
          ) : (
            <div className="space-y-3">
              {fleetEntries.map(([status, n]) => {
                const meta = vehicleStatusMeta(status);
                return (
                  <ProgressRow key={status} label={meta.label} color={meta.color}
                               count={n} total={vehicles.length} />
                );
              })}
            </div>
          )}
        </SectionCard>

        <SectionCard icon={RouteIcon} title="Trip Status">
          {!tripBreakdown || tripBreakdown.total === 0 ? (
            <p className="text-[12px] text-brand-text-muted italic">No dispatched trips recorded yet.</p>
          ) : (
            <div className="space-y-3">
              {tripStatusOrder
                .filter((s) => tripBreakdown.byStatus[s])
                .map((s) => (
                  <ProgressRow key={s} label={s} color={tripStatusColor[s] || '#94A3B8'}
                               count={tripBreakdown.byStatus[s]} total={tripBreakdown.total} />
                ))}
              <div className="pt-2 mt-1 border-t border-white/[0.06] flex items-center justify-between text-[11px] text-brand-text-muted">
                <span>{tripBreakdown.shared} shared · {tripBreakdown.individual} individual</span>
              </div>
            </div>
          )}
        </SectionCard>
      </div>

      {/* ── Recent activity / Top vehicles ──────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SectionCard
          icon={Activity}
          title="Recent Activity"
          action={<button onClick={() => navigate('/notifications')} className="btn-ghost !text-brand-primary !px-2 !py-1">View all</button>}
        >
          <ActivityTimeline timeline={timeline} />
        </SectionCard>

        <SectionCard icon={Trophy} title="Top Performing Vehicles">
          {!tripBreakdown || tripBreakdown.topVehicles.length === 0 ? (
            <p className="text-[12px] text-brand-text-muted italic">No completed trips to rank yet.</p>
          ) : (
            <div className="space-y-2.5">
              {tripBreakdown.topVehicles.map((v, i) => (
                <div key={v.vehicleId} className="flex items-center gap-3 surface-well rounded-xl px-3 py-2.5">
                  <span className="h-6 w-6 rounded-lg bg-brand-primary/15 border border-brand-primary/30 text-brand-primary text-[11px] font-bold flex items-center justify-center shrink-0">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[12.5px] font-semibold text-white truncate">{v.name}</p>
                    <p className="text-[10.5px] text-brand-text-muted">{v.trips} trip{v.trips === 1 ? '' : 's'}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-[11.5px] font-mono text-brand-success tabular-nums">{v.distanceSavedKm.toFixed(1)} km</p>
                    <p className="text-[10px] text-brand-text-muted">saved</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      </div>

      {/* ── AI Insights / System Health ──────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SectionCard
          icon={BrainCircuit}
          title="AI Insights"
          action={<button onClick={() => navigate('/xai')} className="btn-ghost !text-brand-primary !px-2 !py-1">Open <ArrowUpRight className="h-3 w-3" /></button>}
        >
          {!xaiOverview || xaiOverview.total_explanations === 0 ? (
            <p className="text-[12px] text-brand-text-muted italic">No decisions evaluated yet.</p>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <div className="surface-well rounded-xl px-3 py-2.5">
                  <p className="text-[9.5px] uppercase tracking-wider text-brand-text-muted font-bold">Decisions</p>
                  <p className="text-[16px] font-semibold text-white tabular-nums mt-0.5">{fmtInt(xaiOverview.total_explanations)}</p>
                </div>
                <div className="surface-well rounded-xl px-3 py-2.5">
                  <p className="text-[9.5px] uppercase tracking-wider text-brand-text-muted font-bold">Avg Compat</p>
                  <p className="text-[16px] font-semibold text-[#22D3EE] tabular-nums mt-0.5">{fmt1(xaiOverview.avg_compatibility_score)}%</p>
                </div>
                <div className="surface-well rounded-xl px-3 py-2.5">
                  <p className="text-[9.5px] uppercase tracking-wider text-brand-text-muted font-bold">Avg Confidence</p>
                  <p className="text-[16px] font-semibold text-brand-warning tabular-nums mt-0.5">{fmt1(xaiOverview.avg_confidence_score)}%</p>
                </div>
              </div>
              <div className="flex items-center justify-between text-[12px] pt-1">
                <span className="text-brand-text-muted">Most common outcome</span>
                <span className="text-white font-semibold">{xaiOverview.most_common_decision}</span>
              </div>
            </div>
          )}
        </SectionCard>

        <SectionCard icon={HeartPulse} title="System Health">
          <div className="space-y-2.5">
            <div className="flex items-center justify-between surface-well rounded-xl px-3.5 py-2.5">
              <span className="flex items-center gap-2 text-[12px] text-brand-text-secondary">
                <Server className="h-3.5 w-3.5" /> API
              </span>
              <StatusBadge tone={healthOk === null ? 'neutral' : healthOk ? 'success' : 'danger'}
                            label={healthOk === null ? 'Checking…' : healthOk ? 'Operational' : 'Unreachable'} pulse={Boolean(healthOk)} />
            </div>
            <div className="flex items-center justify-between surface-well rounded-xl px-3.5 py-2.5">
              <span className="flex items-center gap-2 text-[12px] text-brand-text-secondary">
                <Radio className="h-3.5 w-3.5" /> Live feed
              </span>
              <StatusBadge tone={feedFresh ? 'success' : 'danger'}
                            label={feedFresh ? `Updated ${lastUpdated?.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}` : 'Stale'}
                            pulse={feedFresh} />
            </div>
            <div className="flex items-center justify-between surface-well rounded-xl px-3.5 py-2.5">
              <span className="flex items-center gap-2 text-[12px] text-brand-text-secondary">
                <Activity className="h-3.5 w-3.5" /> Simulation engine
              </span>
              <StatusBadge tone={engineTone} label={engineLabel} pulse={engineTone === 'success'} />
            </div>
            {netError && (
              <div className="flex items-center gap-2 text-[11px] text-brand-warning px-1 pt-1">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" /> {netError}
              </div>
            )}
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
