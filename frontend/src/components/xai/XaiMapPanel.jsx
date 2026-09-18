import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { X, Loader2, Info, Split, Combine } from 'lucide-react';
import api from '../../services/api';
import LiveMapContainer from '../map/LiveMapContainer';
import { normalizeXaiHighlight } from '../../utils/xaiMap';
import { requestTypeMeta, decisionStateMeta } from '../../utils/requestSemantics';

export default function XaiMapPanel({ explanation, open = true, onToggle }) {
  const [queue, setQueue] = useState([]);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [selectedRequest, setSelectedRequest] = useState(null);
  // Default view for a request the DMFE actually batched: separate trips
  // first (what the two requests would have looked like on their own), so
  // the button then reveals the combined trip the engine produced from them.
  const [viewMode, setViewMode] = useState('separate');
  const pollRef = useRef(null);

  const highlight = useMemo(() => normalizeXaiHighlight(explanation), [explanation]);

  // A newly opened decision starts back at the "separate trips" view rather
  // than carrying over whichever mode the previous decision was left in.
  useEffect(() => {
    setViewMode('separate');
  }, [explanation?.request_id]);

  // Background layer: live simulation queue
  const fetchLiveData = useCallback(async () => {
    try {
      const queueRes = await api.get('/simulation/queue?limit=120');
      setQueue(queueRes.data.items || []);
      setLastUpdated(new Date());
    } catch {
      // Silently ignore poll errors
    }
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    fetchLiveData();
    pollRef.current = setInterval(() => {
      if (document.visibilityState === 'visible') fetchLiveData();
    }, 2500);
    return () => clearInterval(pollRef.current);
  }, [open, fetchLiveData]);

  const highlightRequestIds = useMemo(
    () => new Set(highlight?.requestIds || []),
    [highlight],
  );

  const filteredRequests = useMemo(
    () => queue.filter((item) => !highlightRequestIds.has(item.id)),
    [queue, highlightRequestIds],
  );

  if (!explanation) {
    return (
      <div className="glass-panel rounded-[22px] p-16 text-center text-brand-text-muted h-full flex flex-col justify-center border border-white/5 bg-[#0A0F1A]/50">
        <Info className="h-10 w-10 mx-auto mb-3 opacity-40 text-[#00F0FF]" />
        <p className="text-[14px] font-semibold text-white">Select a Decision Card</p>
        <p className="text-[12px] text-white/40 mt-1">
          Click any decision card on the left to inspect its journey on the live map.
        </p>
      </div>
    );
  }

  const typeMeta = requestTypeMeta(highlight.requestType);
  const state = decisionStateMeta(highlight.status, highlight.decision);

  return (
    <div className="relative w-full h-full min-h-[750px] bg-[#0A0F1A] rounded-[22px] overflow-hidden border border-white/10 shadow-[0_12px_40px_rgba(0,0,0,0.5)]">

      {/* ── Base Map Canvas — the dominant element; detail lives in the RIGHT
           panel now, not floated on top of the map. ── */}
      <LiveMapContainer
        mode="decision"
        requests={filteredRequests}
        selectedRequest={selectedRequest}
        onSelectRequest={(req) => setSelectedRequest(req)}
        onClosePopup={() => setSelectedRequest(null)}
        xaiHighlight={highlight}
        xaiViewMode={viewMode}
        className="absolute inset-0 w-full h-full"
      />

      {/* ── Compact top identity strip (single line, matches the Live
           Operations KpiBar convention — no oversized panels over the map) ── */}
      <div className="absolute top-4 left-4 right-4 z-20 flex items-start justify-between pointer-events-none">
        <div className="pointer-events-auto bg-[#0A0F1A]/80 backdrop-blur-xl border border-white/10 rounded-2xl px-4 py-2.5 shadow-[0_8px_32px_rgba(0,0,0,0.4)] inline-flex items-center gap-3 flex-wrap">
          <span className="text-[12px] font-bold text-white font-mono">#{highlight.requestId}</span>
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider rounded-md border ${typeMeta.chipClass}`}>
            <typeMeta.Icon className="h-3 w-3" /> {typeMeta.label}
          </span>
          <span
            className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider rounded-md border"
            style={{ color: state.color, borderColor: `${state.color}4D`, background: `${state.color}1A` }}
          >
            {highlight.decision || 'No decision recorded'}
          </span>
          <span className="text-[#00F0FF] text-[11px] font-medium">
            {Number.isFinite(highlight.score) ? `${highlight.score.toFixed(1)}%` : '—'}
          </span>

          {/* Separate-trips / combined-trip toggle — only meaningful for a
              request the DMFE actually batched into a shared trip. */}
          {highlight.isShared && (
            <button
              onClick={() => setViewMode((m) => (m === 'separate' ? 'combined' : 'separate'))}
              className="flex items-center gap-1.5 pl-2.5 ml-1 border-l border-white/10 text-[10.5px] font-semibold text-white/70 hover:text-white transition-colors"
              title={viewMode === 'separate' ? 'Show the combined shared trip' : 'Show the two trips separately'}
            >
              {viewMode === 'separate'
                ? <><Combine className="h-3.5 w-3.5 text-[#00F0FF]" /> Show combined trip</>
                : <><Split className="h-3.5 w-3.5 text-[#00F0FF]" /> Show separate trips</>}
            </button>
          )}
        </div>

        {/* Close/Toggle button */}
        <button
          onClick={onToggle}
          className="pointer-events-auto flex items-center justify-center h-9 w-9 rounded-xl bg-white/5 border border-white/10 text-white/50 hover:bg-white/10 hover:text-white transition-colors backdrop-blur-md shrink-0"
          title="Close Map View"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Background loading state — unobtrusive, bottom-left */}
      {!lastUpdated && (
        <div className="absolute bottom-4 left-4 z-20 glass-panel-strong rounded-lg px-3 py-1.5 backdrop-blur-xl text-[10px] text-white/50 flex items-center gap-1.5 pointer-events-none">
          <Loader2 className="h-3 w-3 animate-spin text-[#00F0FF]" /> Loading environment...
        </div>
      )}
    </div>
  );
}