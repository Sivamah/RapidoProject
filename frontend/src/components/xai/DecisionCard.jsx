import React from 'react';
import { requestTypeMeta } from '../../utils/requestSemantics';

/** Batched / Individual / Rejected — the same three-way split the outcome
 *  filter tabs use (ExplanationDashboard's explanationOutcome), derived
 *  purely from fields the payload already carries. Kept local so the card
 *  never depends on which tab is currently selected. */
function outcomeMeta(explanation) {
  const decision = String(explanation?.decision || '').toLowerCase();
  if (decision.includes('compatible for batching')) {
    return { label: 'Batched', color: '#00F0FF' };
  }
  if ((explanation?.batched_with_request_ids || []).length > 0) {
    return { label: 'Rejected', color: '#EF4444' };
  }
  return { label: 'Individual', color: '#38BDF8' };
}

function formatTime(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/**
 * Compact LEFT-column decision row for the AI Insights 3-column layout.
 * Only what's needed to scan the list at a glance: request ID, outcome,
 * compatibility score, confidence, a one-line reason, and a timestamp when
 * the payload carries one. Full detail (factors, route, economics) lives in
 * the RIGHT panel once a card is selected — this card does not repeat it.
 */
export default function DecisionCard({ explanation, isSelected, onSelect }) {
  if (!explanation) return null;

  const typeMeta = requestTypeMeta(explanation.request_type);
  const outcome = outcomeMeta(explanation);
  const confidence = explanation.confidence_score;
  const hasConfidence = Number.isFinite(confidence);
  const compatScore = explanation.factors?.overall_compatibility_score;
  const hasCompat = Number.isFinite(compatScore);
  const time = formatTime(explanation.created_at);
  const reasonLine = explanation.reason || explanation.decision_summary || '';

  return (
    <div
      onClick={onSelect}
      className={`bg-[#0A0F1A]/70 border rounded-lg px-3 py-2.5 cursor-pointer transition-colors ${
        isSelected
          ? 'border-[#00F0FF]/50 ring-1 ring-[#00F0FF]/25 bg-[#0A0F1A]/90'
          : 'border-white/10 hover:border-white/20 hover:bg-[#0A0F1A]/85'
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <typeMeta.Icon className="h-3.5 w-3.5 shrink-0" style={{ color: typeMeta.color }} />
          <span className="font-mono font-bold text-white text-[12.5px] shrink-0">#{explanation.request_id}</span>
          <span
            className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase tracking-wide border shrink-0"
            style={{ color: outcome.color, borderColor: `${outcome.color}4D`, background: `${outcome.color}14` }}
          >
            {outcome.label}
          </span>
        </div>
        {time && <span className="text-[10px] text-white/35 font-mono shrink-0">{time}</span>}
      </div>

      {reasonLine && (
        <p className="text-[11px] text-white/55 truncate mb-1.5" title={reasonLine}>{reasonLine}</p>
      )}

      <div className="flex items-center gap-3 text-[10.5px]">
        <span className="text-white/40">
          Compat <span className="text-[#00F0FF] font-mono font-semibold">{hasCompat ? `${compatScore}%` : '—'}</span>
        </span>
        <span className="text-white/40">
          Conf <span className="text-white/75 font-mono font-semibold">{hasConfidence ? `${confidence}%` : '—'}</span>
        </span>
      </div>
    </div>
  );
}
