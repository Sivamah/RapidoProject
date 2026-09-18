import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MapPin, Flag, BrainCircuit, User, Truck, Info,
  AlertTriangle, Route as RouteIcon, Check, X, Users, IndianRupee, Map as MapIcon,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList,
} from 'recharts';
import {
  requestTypeMeta, decisionStateMeta,
} from '../../utils/requestSemantics';
import { buildOperationalRoute, describeSequenceNumbered } from '../../utils/operationalRoute';

/**
 * RIGHT-hand XAI decision detail panel for the AI Insights 3-column layout.
 *
 * Content and structure deliberately mirror `TripDetailsPanel`'s
 * `DecisionCardPanel` (the same detail already shown for a Live Operations
 * `/live-map?xai=` deep link) rather than inventing a second rendering of the
 * same explanation — the two differ only in the operational-sequence format
 * (numbered list here) and the addition of a classification line, a
 * combined-trip breakdown and a compatibility-factor bar list. Everything
 * rendered here comes straight from the normalized highlight object; a
 * field the payload did not carry renders as "—", never a fabricated
 * placeholder.
 *
 * Section order follows the spec for this panel: decision → compatibility
 * score / confidence → why this decision (key reasons) → compatibility
 * factors → driver / vehicle / pickup / drop / related requests → OR-Tools
 * stop sequence for shared batches.
 */

function fmt(value, digits, suffix) {
  return Number.isFinite(value) ? `${value.toFixed(digits)}${suffix}` : '—';
}

function fmtInr(value) {
  return Number.isFinite(value)
    ? `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
    : '—';
}

function AddressRow({ Icon, tone, label, value }) {
  return (
    <div className="flex items-start gap-3 bg-white/[0.02] border border-white/5 rounded-xl p-3">
      <div
        className="h-6 w-6 rounded-full flex items-center justify-center shrink-0 mt-0.5 border"
        style={{ background: `${tone}22`, borderColor: `${tone}4D` }}
      >
        <Icon className="h-3 w-3" style={{ color: tone }} />
      </div>
      <div className="min-w-0 flex-1">
        <span className="text-[10px] uppercase tracking-wider text-white/40 font-bold block mb-0.5">{label}</span>
        <span className="text-[12px] text-white/90 font-medium truncate block">{value || '—'}</span>
      </div>
    </div>
  );
}

/** Batched / Individual / Rejected — derived from fields the payload
 *  already carries, never a new backend classification. Same three-way
 *  split the LEFT-panel filter tabs use. */
function classify(highlight, isRejected) {
  if (isRejected) return { label: 'Rejected', color: '#EF4444' };
  if (highlight.tripCode) {
    return highlight.isShared
      ? { label: 'Batched · Shared trip', color: '#00F0FF' }
      : { label: 'Individual · Dispatched', color: '#38BDF8' };
  }
  return { label: 'Individual · Planned', color: '#94A3B8' };
}

export default function XaiDecisionPanel({ highlight }) {
  // Hooks must run unconditionally, before the "nothing selected" early
  // return below.
  const navigate = useNavigate();

  if (!highlight) {
    return (
      <div className="bg-[#0A0F1A]/75 rounded-2xl p-6 backdrop-blur-xl border border-white/10 shadow-[0_8px_24px_rgba(0,0,0,0.35)] w-full h-full flex flex-col items-center justify-center text-center">
        <Info className="h-8 w-8 mb-3 opacity-40 text-[#00F0FF]" />
        <p className="text-[13px] font-semibold text-white">No decision selected</p>
        <p className="text-[11px] text-white/45 mt-1 leading-relaxed">
          Select a decision card to inspect its route and factor attribution.
        </p>
      </div>
    );
  }

  const meta = requestTypeMeta(highlight.requestType);
  const state = decisionStateMeta(highlight.status, highlight.decision);
  const isRejected = state.tone === 'danger';
  const route = buildOperationalRoute(highlight);
  const sequence = describeSequenceNumbered(route.stops);
  const classification = classify(highlight, isRejected);
  const f = highlight.factors || {};
  const related = (highlight.requestPoints || []).filter((p) => p.relation !== 'self');

  // Solo vs combined profit — both figures come straight from the backend
  // (driver_profit_inr for the trip as actually dispatched, solo_profit_inr
  // for the same revenue/fuel-cost formula applied to the pre-batching
  // distance). For a request that was never batched the two are equal, so
  // the chart honestly shows 0% rather than a forced "increase".
  // Restores the AI Insights → Live Operations Map deep link. The consumer
  // side (`LiveSimulationMap.jsx` reading `?xai=`) and the backend
  // (`GET /api/xai/explanations/{id}`) were already wired and tested — this
  // producer-side control was the only missing piece.
  const handleViewOnMap = () => navigate(`/live-map?xai=${highlight.requestId}`);

  const hasProfitCompare = Number.isFinite(highlight.driverProfitInr) && Number.isFinite(highlight.soloProfitInr);
  const profitChartData = hasProfitCompare
    ? [
      { name: 'Solo', value: highlight.soloProfitInr },
      { name: 'Combined', value: highlight.driverProfitInr },
    ]
    : [];
  const profitPct = hasProfitCompare && highlight.soloProfitInr > 0
    ? ((highlight.driverProfitInr - highlight.soloProfitInr) / highlight.soloProfitInr) * 100
    : 0;

  return (
    <div className="bg-[#0A0F1A]/75 rounded-2xl p-4 backdrop-blur-xl border border-white/10 shadow-[0_8px_24px_rgba(0,0,0,0.35)] w-full max-h-full overflow-y-auto custom-scrollbar">
      {/* Header: request id, type, classification (= Decision: Batched / Individual / Rejected) */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-bold border shrink-0 uppercase tracking-wide ${meta.chipClass}`}>
            <meta.Icon className="h-3.5 w-3.5" /> {meta.label}
          </span>
          <span className="text-white font-mono text-[14px] font-bold truncate">#{highlight.requestId}</span>
        </div>
        <button
          type="button"
          onClick={handleViewOnMap}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10.5px] font-bold border border-[#00F0FF]/30 bg-[#00F0FF]/10 text-[#00F0FF] hover:bg-[#00F0FF]/20 transition-colors shrink-0"
          title="Open this decision's route on the Live Operations Map"
        >
          <MapIcon className="h-3.5 w-3.5" /> View on Map
        </button>
      </div>

      <span
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wide border mb-3"
        style={{ color: classification.color, borderColor: `${classification.color}4D`, background: `${classification.color}14` }}
      >
        {classification.label}
      </span>

      {/* Decision */}
      <div className="rounded-xl border p-3 mb-3" style={{ borderColor: `${state.color}44`, background: `${state.color}12` }}>
        <span className="flex items-center gap-1.5 text-[9.5px] uppercase tracking-wider font-bold mb-1 text-[#00F0FF]">
          <BrainCircuit className="h-3.5 w-3.5" /> A-DMFE decision
        </span>
        <p className="text-[13px] font-bold" style={{ color: state.color }}>
          {highlight.decision || 'No decision recorded'}
        </p>
        {highlight.reason && (
          <p className="text-[11px] text-white/55 mt-1 leading-relaxed">{highlight.reason}</p>
        )}
      </div>

      {/* Compatibility Score / Confidence */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        {[
          ['Compatibility', fmt(highlight.score, 1, '%')],
          ['Confidence', fmt(highlight.confidence, 1, '%')],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border border-white/10 bg-white/[0.03] px-2.5 py-2">
            <span className="block text-[9px] uppercase tracking-wider text-white/40 font-bold">{label}</span>
            <span className="text-[16px] font-semibold text-white tabular-nums">{value}</span>
          </div>
        ))}
      </div>

      {/* Why this decision? — key reasons, straight from the engine */}
      <div className="mb-3">
        <span className="text-[9px] uppercase tracking-wider text-white/40 font-bold block mb-1.5">Why this decision?</span>
        {(highlight.keyReasons || []).length > 0 ? (
          <ul className="space-y-1">
            {highlight.keyReasons.slice(0, 5).map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-[10.5px] text-white/70">
                {isRejected
                  ? <X className="h-3 w-3 text-[#EF4444] shrink-0 mt-0.5" />
                  : <Check className="h-3 w-3 text-[#22C55E] shrink-0 mt-0.5" />}
                <span className="leading-relaxed">{r}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[10.5px] text-white/35 italic">
            No factor rationale recorded for this decision.
          </p>
        )}
      </div>

      {/* Compatibility factors — the real weighted factors the DMFE scoring
          engine computes. A bar only fills for a value the backend actually
          returned; a missing factor shows "—" rather than an empty-looking
          bar drawn as zero. */}
      {highlight.factors && (
        <div className="mb-3 border-t border-white/10 pt-3">
          <span className="text-[9px] uppercase tracking-wider text-white/40 font-bold block mb-2">Compatibility factors</span>
          <div className="space-y-2">
            {[
              ['Pickup proximity', f.pickup_distance_score],
              ['Route similarity', f.destination_similarity],
              ['Time compatibility', f.estimated_delay_score],
              ['Vehicle capacity', f.vehicle_capacity_score],
              ['Priority', f.priority_score],
            ].map(([label, value]) => {
              const has = Number.isFinite(value);
              const pct = has ? Math.min(100, Math.max(0, value)) : 0;
              return (
                <div key={label}>
                  <div className="flex items-center justify-between text-[10.5px] mb-0.5">
                    <span className="text-white/55">{label}</span>
                    <span className="text-white/80 font-mono">{has ? `${Math.round(value)}%` : '—'}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
                    {has && <div className="h-full rounded-full bg-[#00F0FF]/70" style={{ width: `${pct}%` }} />}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Driver / vehicle */}
      {(highlight.driver || highlight.vehicle) && (
        <div className="flex items-center gap-4 bg-white/5 border border-white/10 rounded-xl p-3 mb-3 text-[11px]">
          {highlight.driver && (
            <span className="flex items-center gap-1.5 min-w-0">
              <User className="h-3.5 w-3.5 text-[#38BDF8] shrink-0" />
              <span className="text-white/75 truncate">{highlight.driver.name}</span>
            </span>
          )}
          {highlight.vehicle && (
            <span className="flex items-center gap-1.5 min-w-0">
              <Truck className="h-3.5 w-3.5 text-[#38BDF8] shrink-0" />
              <span className="text-white/75 truncate">
                {highlight.vehicle.name}{highlight.vehicle.type ? ` · ${highlight.vehicle.type}` : ''}
              </span>
            </span>
          )}
        </div>
      )}

      {/* Pickup / drop — only shown standalone when this request was NOT
          combined into a shared trip. When it was, the "Combined trip"
          block below already shows this request's own pickup/drop (tagged
          "this request") alongside its partner's, so repeating it here
          would be pure duplication. */}
      {!highlight.isShared && (
        <div className="space-y-2 mb-3">
          <AddressRow Icon={MapPin} tone="#22C55E" label="Pickup" value={highlight.pickupAddress} />
          <AddressRow Icon={Flag} tone="#EF4444" label="Drop-off" value={highlight.dropAddress} />
        </div>
      )}

      {/* Combined trip — this request was actually batched into a shared
          vehicle with another request, possibly of a different service
          type (food/parcel/ride). Each request line is tagged with its own
          type badge so it's visually obvious WHAT was combined; the "Why
          combined" note below is the engine's own compatibility-vs-
          threshold text, not a synthesized explanation. */}
      {highlight.isShared && related.length > 0 && (
        <div className="mb-3 rounded-xl border p-3" style={{ borderColor: '#00F0FF33', background: '#00F0FF0D' }}>
          <span className="flex items-center gap-1.5 text-[9px] uppercase tracking-wider text-[#00F0FF] font-bold mb-2.5">
            <Users className="h-3 w-3" /> Combined trip · {1 + related.length} requests sharing this vehicle
          </span>
          <div className="space-y-2.5">
            <div>
              <span className="inline-flex items-center gap-1 text-[10.5px] font-bold text-white/80 font-mono">
                <meta.Icon className="h-3 w-3 shrink-0" style={{ color: meta.color }} />
                #{highlight.requestId} <span className="font-sans font-normal text-white/40">({meta.label} · this request)</span>
              </span>
              <div className="mt-1 space-y-1">
                <span className="flex items-center gap-1.5 text-[10.5px] text-white/65 truncate">
                  <MapPin className="h-2.5 w-2.5 text-[#22C55E] shrink-0" /> {highlight.pickupAddress || '—'}
                </span>
                <span className="flex items-center gap-1.5 text-[10.5px] text-white/65 truncate">
                  <Flag className="h-2.5 w-2.5 text-[#EF4444] shrink-0" /> {highlight.dropAddress || '—'}
                </span>
              </div>
            </div>
            {related.map((p) => {
              const pMeta = requestTypeMeta(p.request_type);
              return (
                <div key={p.id}>
                  <span className="inline-flex items-center gap-1 text-[10.5px] font-bold text-white/80 font-mono">
                    <pMeta.Icon className="h-3 w-3 shrink-0" style={{ color: pMeta.color }} />
                    #{p.id} <span className="font-sans font-normal text-white/40">
                      ({pMeta.label} · {p.relation === 'partner' ? 'matched partner' : 'trip member'})
                    </span>
                  </span>
                  <div className="mt-1 space-y-1">
                    <span className="flex items-center gap-1.5 text-[10.5px] text-white/65 truncate">
                      <MapPin className="h-2.5 w-2.5 text-[#22C55E] shrink-0" /> {p.pickup_address || '—'}
                    </span>
                    <span className="flex items-center gap-1.5 text-[10.5px] text-white/65 truncate">
                      <Flag className="h-2.5 w-2.5 text-[#EF4444] shrink-0" /> {p.drop_address || '—'}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
          {highlight.decisionSummary && (
            <div className="mt-2.5 pt-2.5 border-t border-white/10">
              <span className="block text-[9px] uppercase tracking-wider text-white/40 font-bold mb-1">Why combined</span>
              <p className="text-[11px] text-white/75 leading-relaxed">{highlight.decisionSummary}</p>
            </div>
          )}
        </div>
      )}

      {/* Related requests — the XAI-evaluated candidate pool. Only shown
          when the request was NOT actually combined into a shared trip;
          when it was, the "Combined trip" block above already covers this
          ground with pickup/drop for both requests instead of pickup alone. */}
      {related.length > 0 && !highlight.isShared && (
        <div className="mb-3">
          <span className="flex items-center gap-1.5 text-[9px] uppercase tracking-wider text-white/40 font-bold mb-1.5">
            <Users className="h-3 w-3" /> Related requests
          </span>
          <div className="space-y-1">
            {related.map((p) => {
              const rMeta = requestTypeMeta(p.request_type);
              return (
                <div key={p.id} className="flex items-center gap-2 text-[10.5px]">
                  <rMeta.Icon className="h-3 w-3 shrink-0" style={{ color: rMeta.color }} />
                  <span className="text-white/70 font-mono">#{p.id}</span>
                  <span className="text-white/40 truncate">{p.pickup_address?.split(',')[0] || '—'}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Trip economics — real ₹ comparison between this trip's actual cost
          (combined when shared, individual otherwise) and what running
          these same requests as separate individual trips would have cost
          at the same per-km rate the optimizer used. Shown whenever the
          request was dispatched (tripCode set); every figure is copied
          straight from the backend, never estimated in the browser. */}
      {highlight.tripCode && (
        <div className="mb-3 rounded-xl border border-white/10 bg-white/[0.03] p-3">
          <span className="flex items-center gap-1.5 text-[9px] uppercase tracking-wider text-white/40 font-bold mb-2.5">
            <IndianRupee className="h-3 w-3" /> Trip economics
          </span>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-lg border border-white/10 bg-white/[0.02] px-2.5 py-2">
              <span className="block text-[9px] uppercase tracking-wider text-white/40 font-bold">This trip cost</span>
              <span className="text-[15px] font-semibold text-white tabular-nums">{fmtInr(highlight.tripCostInr)}</span>
            </div>
            <div className="rounded-lg border border-white/10 bg-white/[0.02] px-2.5 py-2">
              <span className="block text-[9px] uppercase tracking-wider text-white/40 font-bold">If run separately</span>
              <span className="text-[15px] font-semibold text-white tabular-nums">{fmtInr(highlight.separateCostInr)}</span>
            </div>
          </div>
          {highlight.isShared && Number.isFinite(highlight.tripCostInr) && Number.isFinite(highlight.separateCostInr) && (
            <p className="mt-2 text-[11px] text-[#22C55E] font-semibold">
              Saved {fmtInr(highlight.separateCostInr - highlight.tripCostInr)} by combining
              {Number.isFinite(highlight.distanceSavedKm) && highlight.distanceSavedKm > 0 && ` · ${fmt(highlight.distanceSavedKm, 1, ' km')}`}
              {Number.isFinite(highlight.fuelSavedL) && highlight.fuelSavedL > 0 && ` · ${fmt(highlight.fuelSavedL, 2, ' L')} fuel`}
              {Number.isFinite(highlight.co2SavedKg) && highlight.co2SavedKg > 0 && ` · ${fmt(highlight.co2SavedKg, 2, ' kg')} CO₂`}
            </p>
          )}
          <div className="mt-2 pt-2 border-t border-white/10 flex items-center justify-between">
            <span className="text-[10px] text-white/45">Driver profit (this trip)</span>
            <span className="text-[11px] text-white/85 font-mono tabular-nums">{fmtInr(highlight.driverProfitInr)}</span>
          </div>

          {/* Profit graph — solo vs combined, same real numbers as above,
              plotted so the difference reads at a glance instead of as two
              numbers to compare by eye. */}
          {hasProfitCompare && (
            <div className="mt-2 pt-2 border-t border-white/10">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[9px] uppercase tracking-wider text-white/40 font-bold">Profit: solo vs combined</span>
                <span className={`text-[11px] font-bold font-mono ${
                  profitPct > 0 ? 'text-[#22C55E]' : profitPct < 0 ? 'text-[#F59E0B]' : 'text-white/50'
                }`}>
                  {profitPct > 0 ? '+' : ''}{profitPct.toFixed(1)}%
                </span>
              </div>
              <div className="h-[110px] -ml-1">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={profitChartData} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
                    <XAxis
                      dataKey="name"
                      tick={{ fill: 'rgba(255,255,255,0.45)', fontSize: 10 }}
                      axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
                      tickLine={false}
                    />
                    <YAxis hide domain={[0, (max) => max * 1.25]} />
                    <Tooltip
                      cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                      contentStyle={{ background: '#0A0F1A', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8, fontSize: 11 }}
                      labelStyle={{ color: 'rgba(255,255,255,0.6)' }}
                      itemStyle={{ color: '#fff' }}
                      formatter={(value) => [fmtInr(value), 'Profit']}
                    />
                    <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={56}>
                      {profitChartData.map((entry) => (
                        <Cell key={entry.name} fill={entry.name === 'Combined' ? '#00F0FF' : '#94A3B8'} />
                      ))}
                      <LabelList
                        dataKey="value"
                        position="top"
                        formatter={fmtInr}
                        style={{ fill: 'rgba(255,255,255,0.75)', fontSize: 10, fontWeight: 600 }}
                      />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </div>
      )}

      {/* OR-Tools stop order — numbered, only for a real (non-rejected) sequence */}
      {!isRejected && sequence.length > 0 && (
        <div className="mb-1">
          <span className="flex items-center gap-1.5 text-[9px] uppercase tracking-wider text-white/40 font-bold mb-1.5">
            <RouteIcon className="h-3 w-3" /> OR-Tools stop order
          </span>
          <ol className="space-y-1">
            {sequence.map((line) => (
              <li key={line} className="text-[10.5px] text-white/75 font-mono leading-relaxed">{line}</li>
            ))}
          </ol>
          {route.isPlanned && (
            <p className="text-[10px] text-[#F59E0B] mt-1.5 flex items-start gap-1.5">
              <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" />
              Planned leg — no vehicle dispatched for this request yet.
            </p>
          )}
        </div>
      )}
      {isRejected && (
        <div className="flex items-start gap-1.5 text-[10.5px] text-[#EF4444]">
          <X className="h-3 w-3 shrink-0 mt-0.5" />
          <span>Rejected pairing — no route drawn on the map.</span>
        </div>
      )}

      {highlight.tripCode && (
        <p className="mt-3 pt-3 border-t border-white/10 text-[10px] text-[#00F0FF] font-mono">
          {highlight.tripCode}{highlight.isShared ? ' · shared trip' : ' · individual trip'}
        </p>
      )}
    </div>
  );
}
