import React from 'react';
import { Activity } from 'lucide-react';
import { engineStatusView } from './uiLogic.js';

const TONE_COLORS = { ok: '#10b981', warn: '#f59e0b', error: '#ef4444', muted: '#64748b' };

// Header badge showing the backend engine status from /ws (F10).
export default function EngineStatus({ status }) {
  const view = engineStatusView(status);
  const color = TONE_COLORS[view.tone];
  return (
    <div role="status" title={view.hint}
      style={{display: 'flex', alignItems: 'center', gap: '6px', padding: '0.4rem 0.75rem', borderRadius: '999px',
        border: `1px solid ${color}`, color, fontSize: '0.65rem', fontWeight: 800, letterSpacing: '0.05em'}}>
      <Activity size={12} /> {view.label}
    </div>
  );
}
