import React from 'react';
import { Maximize2, Minimize2, Target, Plus, Minus, Compass } from 'lucide-react';

export default function MapControls({
  onFitBounds,
  onRecenter,
  onZoomIn,
  onZoomOut,
  isFullscreen,
  onToggleFullscreen,
}) {
  const baseBtn =
    'flex items-center justify-center gap-1.5 rounded-lg text-white/50 hover:text-white hover:bg-white/10 transition-colors';
  return (
    <div className="flex flex-col gap-1 bg-[#0A0F1A]/70 backdrop-blur-xl border border-white/10 rounded-xl p-1.5 shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
      <button
        onClick={onFitBounds}
        className={`${baseBtn} h-8 px-2 text-[10px] font-semibold text-[#00F0FF] bg-[#00F0FF]/10 hover:bg-[#00F0FF]/20 border border-[#00F0FF]/20`}
        title="Fit All Markers"
      >
        <Target className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">FIT</span>
      </button>

      <button onClick={onRecenter} className={`${baseBtn} h-8 w-8`} title="Recenter Map to Coimbatore">
        <Compass className="h-4 w-4" />
      </button>

      <div className="h-px bg-white/10 my-0.5 mx-1" />

      <button onClick={onZoomIn} className={`${baseBtn} h-8 w-8`} title="Zoom In">
        <Plus className="h-4 w-4" />
      </button>
      <button onClick={onZoomOut} className={`${baseBtn} h-8 w-8`} title="Zoom Out">
        <Minus className="h-4 w-4" />
      </button>

      {onToggleFullscreen && (
        <button onClick={onToggleFullscreen} className={`${baseBtn} h-8 w-8`} title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}>
          {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
        </button>
      )}
    </div>
  );
}