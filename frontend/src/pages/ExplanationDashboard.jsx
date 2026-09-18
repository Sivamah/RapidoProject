import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  BrainCircuit, RefreshCw, Search, LayoutGrid, CheckCircle2, XCircle,
  Route as RouteIcon, ChevronDown, X,
} from 'lucide-react';
import api from '../services/api';

import PageHeader from '../components/ui/PageHeader';
import StatusBadge from '../components/ui/StatusBadge';

import DecisionCard from '../components/xai/DecisionCard';
import XaiMapPanel from '../components/xai/XaiMapPanel';
import XaiDecisionPanel from '../components/xai/XaiDecisionPanel';
import { normalizeXaiHighlight } from '../utils/xaiMap';

// ── Decision outcome grouping (Batched / Individual / Rejected) ────────────
// The engine only ever emits two `decision` strings — "Compatible for
// Batching" and "Standalone Direct Routing" — but "Standalone Direct
// Routing" actually covers two different situations that the backend's own
// `reason` text already distinguishes (xai_service.py): a candidate partner
// was evaluated and scored below the compatibility threshold ("Rejected
// from batching: …"), or no candidate partner existed to evaluate at all
// ("No nearby request…"). `batched_with_request_ids` (empty vs not) is the
// same signal in structured form, so splitting on it recovers that
// distinction for the filter tabs below without inventing any new engine
// state or touching the DMFE decision logic itself.
function explanationOutcome(exp) {
  const decision = String(exp?.decision || '').toLowerCase();
  if (decision.includes('compatible for batching')) return 'batched';
  if ((exp?.batched_with_request_ids || []).length > 0) return 'rejected';
  return 'individual';
}

const OUTCOME_TABS = [
  { id: 'all', label: 'All', icon: LayoutGrid },
  { id: 'batched', label: 'Batched', icon: CheckCircle2 },
  { id: 'individual', label: 'Individual', icon: RouteIcon },
  { id: 'rejected', label: 'Rejected', icon: XCircle },
];

export default function ExplanationDashboard() {
  const [search, setSearch] = useState('');
  const [explanations, setExplanations] = useState([]);
  const [timestamp, setTimestamp] = useState(null);
  const [selectedExp, setSelectedExp] = useState(null);
  const [loading, setLoading] = useState(true);
  const [mapOpen, setMapOpen] = useState(true);
  const [outcomeTab, setOutcomeTab] = useState('all');
  // Mobile-only: LEFT list collapses behind a toggle so the map gets the
  // screen; RIGHT panel becomes a slide-in drawer (below) instead of
  // pushing the map out of view.
  const [leftOpen, setLeftOpen] = useState(true);

  const pollRef = useRef(null);

  // Card click → same-tab map interaction:
  //   * new card    → select it and make sure the map panel is open
  //   * same card   → toggle the map panel open/closed (collapse control)
  const handleCardClick = (exp) => {
    const isSame = selectedExp && selectedExp.request_id === exp.request_id;
    if (isSame) {
      setMapOpen((o) => !o);
      return;
    }
    setSelectedExp(exp);
    setMapOpen(true);
  };

  // Fetch XAI explanations — search is the only server-side filter the
  // redesigned LEFT panel exposes; the Batched/Individual/Rejected/All split
  // is applied client-side below so switching tabs never re-hits the API.
  const fetchData = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (search) params.append('search', search);
      params.append('limit', '200');

      const listRes = await api.get(`/xai/explanations?${params.toString()}`);
      const items = listRes.data || [];
      setExplanations(items);
      setTimestamp(new Date().toISOString());

      // Keep selected item updated or pick first
      if (items.length > 0) {
        setSelectedExp((prev) => {
          if (!prev) return items[0];
          const match = items.find((i) => i.request_id === prev.request_id);
          return match || items[0];
        });
      } else {
        setSelectedExp(null);
      }
    } catch (err) {
      console.error('Failed to fetch XAI data:', err);
    } finally {
      setLoading(false);
    }
  }, [search]);

  // Polling: 2.5s
  useEffect(() => {
    fetchData();
    pollRef.current = setInterval(() => { if (document.visibilityState === 'visible') fetchData(); }, 2500);
    return () => clearInterval(pollRef.current);
  }, [fetchData]);

  // Grouped once per fetch so the four tab counts and the filtered list stay
  // in lockstep — recomputing per-render would be wasted work on every poll.
  const explanationsByOutcome = useMemo(() => {
    const groups = { batched: [], individual: [], rejected: [] };
    explanations.forEach((exp) => {
      groups[explanationOutcome(exp)].push(exp);
    });
    return groups;
  }, [explanations]);

  const filteredExplanations = outcomeTab === 'all' ? explanations : (explanationsByOutcome[outcomeTab] || []);

  // Normalized once here so the RIGHT details panel and XaiMapPanel's
  // internal highlight (computed the same way from the same `selectedExp`)
  // stay in lockstep without either owning the other's state.
  const highlight = useMemo(() => normalizeXaiHighlight(selectedExp), [selectedExp]);

  return (
    <div className="space-y-4 pb-6 max-w-[1700px] mx-auto">
      <PageHeader
        eyebrow="AI Insights"
        live
        title="Explainable Decisions"
        description="Inspect how the feasibility engine scores pairings — decision, factor attribution and route, side by side."
        actions={
          <div className="flex items-center gap-2.5">
            <StatusBadge tone="success" label="Auto-refresh 2.5s" pulse />
            <button onClick={fetchData} className="btn-glass">
              <RefreshCw className="h-3.5 w-3.5" /> Refresh
            </button>
          </div>
        }
      />

      {loading && !timestamp ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-indigo-500" />
        </div>
      ) : (
        // ── 3-column layout — LEFT (decisions) / CENTER (map, the dominant
        // element) / RIGHT (selected decision detail) ─────────────────────
        <div className="flex flex-col lg:flex-row gap-4 items-stretch lg:h-[calc(100vh-220px)] lg:min-h-[600px]">
          {/* LEFT: AI Decisions — compact scrollable list with quick filters */}
          <div className="w-full lg:w-[300px] shrink-0 flex flex-col gap-3 lg:h-full lg:overflow-hidden">
            <button
              onClick={() => setLeftOpen((o) => !o)}
              className="lg:hidden w-full flex items-center justify-between glass-panel rounded-xl px-3.5 py-2.5 text-[13px] font-semibold text-white"
            >
              <span className="flex items-center gap-1.5">
                <BrainCircuit className="h-4 w-4 text-[#00F0FF]" /> AI Decisions
                <span className="text-white/40 font-mono text-[11px]">({filteredExplanations.length})</span>
              </span>
              <ChevronDown className={`h-4 w-4 transition-transform ${leftOpen ? 'rotate-180' : ''}`} />
            </button>

            <div className={`${leftOpen ? 'flex' : 'hidden'} lg:flex flex-col gap-3 min-h-0 lg:flex-1`}>
              {/* Search */}
              <div className="relative shrink-0">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/30" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search by ID, provider, reason…"
                  className="w-full pl-8 pr-3 py-2 bg-white/[0.03] border border-white/10 rounded-lg text-[12px] text-white placeholder-white/30 focus:outline-none focus:ring-1 focus:ring-[#00F0FF]/40"
                />
              </div>

              {/* All / Batched / Individual / Rejected */}
              <div className="glass-panel rounded-[14px] p-1.5 flex items-center gap-1.5 overflow-x-auto custom-scrollbar shrink-0">
                {OUTCOME_TABS.map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setOutcomeTab(tab.id)}
                    className={`tab-pill shrink-0 ${outcomeTab === tab.id ? 'tab-pill-active' : ''}`}
                  >
                    <tab.icon className="h-3.5 w-3.5" />
                    {tab.label}
                    <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                      outcomeTab === tab.id ? 'bg-white/15 text-white' : 'bg-white/[0.06] text-brand-text-muted'
                    }`}>
                      {tab.id === 'all' ? explanations.length : explanationsByOutcome[tab.id].length}
                    </span>
                  </button>
                ))}
              </div>

              {/* Decision list */}
              {filteredExplanations.length === 0 ? (
                <div className="bg-[#0A0F1A]/70 border border-white/10 rounded-xl p-8 text-center text-white/35">
                  <BrainCircuit className="h-8 w-8 mx-auto mb-2 opacity-40" />
                  <p className="text-[13px] font-medium">
                    No {OUTCOME_TABS.find((t) => t.id === outcomeTab)?.label.toLowerCase()} decisions
                  </p>
                  <p className="text-[11px] text-white/25 mt-1">Start the simulation engine or check another tab</p>
                </div>
              ) : (
                <div className="space-y-2 overflow-y-auto pr-1 custom-scrollbar lg:flex-1 max-h-[520px] lg:max-h-none">
                  {filteredExplanations.map((exp) => (
                    <DecisionCard
                      key={exp.id || exp.request_id}
                      explanation={exp}
                      isSelected={selectedExp?.request_id === exp.request_id}
                      onSelect={() => handleCardClick(exp)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* CENTER: Live map — the largest element on screen */}
          <div className="flex-1 min-w-0 lg:h-full">
            <XaiMapPanel
              explanation={selectedExp}
              open={mapOpen}
              onToggle={() => setMapOpen((o) => !o)}
            />
          </div>

          {/* RIGHT: Selected XAI decision detail. Desktop: a static column.
              Mobile: a slide-in drawer over the map with a backdrop, so it
              never pushes the map out of view. */}
          {selectedExp && mapOpen && (
            <>
              <div
                className="lg:hidden fixed inset-0 bg-black/60 z-40"
                onClick={() => setMapOpen(false)}
              />
              <div className="fixed inset-y-0 right-0 z-50 w-[88%] max-w-[360px] p-3 lg:p-0 lg:static lg:z-auto lg:w-[300px] lg:max-w-none lg:shrink-0 lg:h-full overflow-y-auto lg:overflow-visible">
                <button
                  onClick={() => setMapOpen(false)}
                  className="lg:hidden mb-2 flex items-center gap-1.5 text-[11px] text-white/50 hover:text-white"
                >
                  <X className="h-3.5 w-3.5" /> Close
                </button>
                <div className="lg:h-full">
                  <XaiDecisionPanel highlight={highlight} />
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
