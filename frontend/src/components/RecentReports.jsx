import React, { useEffect, useState } from 'react';
import { History, ChevronRight, TrendingUp, TrendingDown, Minus } from 'lucide-react';

const GRADE_COLORS = {
  Executive: '#10b981',
  Polished: '#3b82f6',
  Competent: '#8b5cf6',
  'Needs Practice': '#f59e0b',
};

function scoreColor(v) {
  if (v == null) return '#64748b';
  if (v >= 70) return '#10b981';
  if (v >= 40) return '#f59e0b';
  return '#ef4444';
}

/** Difference vs the previous (older) session in the list. */
function TrendDelta({ current, previous }) {
  if (current?.smartspeak_index == null) return null;
  if (previous?.smartspeak_index == null) {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: '0.72rem', color: '#64748b' }}>
        <Minus size={12} /> baseline
      </span>
    );
  }
  const delta = current.smartspeak_index - previous.smartspeak_index;
  if (Math.abs(delta) < 0.5) {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, fontSize: '0.72rem', color: '#64748b' }}>
        <Minus size={12} /> steady
      </span>
    );
  }
  const up = delta > 0;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      fontSize: '0.72rem', fontWeight: 700, color: up ? '#059669' : '#dc2626',
    }}>
      {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
      {up ? '+' : ''}{delta.toFixed(1)} vs prev
    </span>
  );
}

/**
 * RecentReports — landing-page list of recently analyzed sessions.
 * Click any row to reopen its full report. Hidden entirely when the
 * backend has no completed sessions or cannot be reached.
 */
export function RecentReports({ onOpenSession }) {
  const [sessions, setSessions] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/v1/sessions/history?limit=8&completed_only=true');
        if (!res.ok) throw new Error(`history request failed (${res.status})`);
        const data = await res.json();
        if (!cancelled) setSessions(data.sessions || []);
      } catch (e) {
        console.error('Failed to load session history:', e);
        if (!cancelled) setFailed(true);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (failed || !sessions || sessions.length === 0) return null;

  return (
    <div className="animate-fade-in" style={{
      maxWidth: 680, margin: '32px auto 0',
      background: '#ffffff',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-lg)',
      padding: '18px 20px',
      textAlign: 'left',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <History size={17} color="var(--primary-purple)" />
        <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
          Recent Reports
        </h3>
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>
          click to reopen
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {sessions.map((s, i) => (
          <button
            key={s.session_id}
            type="button"
            onClick={() => onOpenSession(s.session_id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 12, width: '100%',
              padding: '10px 12px', textAlign: 'left',
              background: '#ffffff', border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)', cursor: 'pointer',
              transition: 'background 0.15s ease, border-color 0.15s ease',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-subtle)'; e.currentTarget.style.borderColor = 'var(--border-strong)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = '#ffffff'; e.currentTarget.style.borderColor = 'var(--border-subtle)'; }}
          >
            {/* Score ring */}
            <div style={{
              width: 44, height: 44, borderRadius: '50%', flexShrink: 0,
              display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
              border: `2px solid ${scoreColor(s.smartspeak_index)}`,
              background: `${scoreColor(s.smartspeak_index)}12`,
            }}>
              <strong style={{ fontSize: '0.85rem', lineHeight: 1, color: scoreColor(s.smartspeak_index) }}>
                {s.smartspeak_index != null ? Math.round(s.smartspeak_index) : '–'}
              </strong>
            </div>

            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {s.original_filename}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2, flexWrap: 'wrap' }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  {new Date(s.upload_timestamp).toLocaleString()}
                </span>
                {s.grade && (
                  <span className="badge-pill" style={{
                    fontSize: '0.65rem', padding: '1px 8px',
                    background: `${(GRADE_COLORS[s.grade] || '#64748b')}18`,
                    color: GRADE_COLORS[s.grade] || '#64748b',
                    border: `1px solid ${(GRADE_COLORS[s.grade] || '#64748b')}40`,
                  }}>
                    {s.grade}
                  </span>
                )}
                <TrendDelta current={s} previous={sessions[i + 1]} />
              </div>
            </div>

            <ChevronRight size={16} color="#94a3b8" style={{ flexShrink: 0 }} />
          </button>
        ))}
      </div>
    </div>
  );
}

export default RecentReports;
