import React, { useEffect, useState } from 'react';
import {
  GitCompare, TrendingUp, TrendingDown, Minus, X, Crosshair, CheckCircle2, ArrowRight, AlertTriangle,
} from 'lucide-react';

/**
 * SessionCompare — side-by-side comparison of two completed sessions.
 *
 * Score delta front and center, then one row per metric with old → new
 * values and a color-coded improved/regressed/same chip, plus the older
 * session's focus-goal progress between the two takes. Data comes from the
 * compare endpoint; the component only renders presentation.
 */

const fmtTime = (s) => (Number.isFinite(Number(s))
  ? `${Number(s).toFixed(1)}${s.unit || ''}`
  : '–');

function DirectionChip({ direction }) {
  if (direction === 'improved') {
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        background: '#ecfdf5', color: '#059669', border: '1px solid #a7f3d0',
        borderRadius: 999, padding: '2px 10px', fontSize: '0.72rem', fontWeight: 700,
      }}>
        <TrendingUp size={12} /> improved
      </span>
    );
  }
  if (direction === 'regressed') {
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        background: '#fef2f2', color: '#dc2626', border: '1px solid #fecaca',
        borderRadius: 999, padding: '2px 10px', fontSize: '0.72rem', fontWeight: 700,
      }}>
        <TrendingDown size={12} /> regressed
      </span>
    );
  }
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      background: '#f1f5f9', color: '#64748b', border: '1px solid #e2e8f0',
      borderRadius: 999, padding: '2px 10px', fontSize: '0.72rem', fontWeight: 700,
    }}>
      <Minus size={12} /> same
    </span>
  );
}

const fmtVal = (d, which) => {
  const v = d[which];
  if (v == null) return '–';
  const unit = d.unit || '';
  if (d.metric === 'wpm') return `${Math.round(v)}${unit}`;
  if (d.metric === 'longest_pause') return `${Number(v).toFixed(1)}${unit}`;
  if (d.metric === 'filler_ratio' || d.metric === 'eye_contact' || d.metric === 'posture' || d.metric === 'head_movement') {
    return `${Math.round(v)}${unit}`;
  }
  return `${v}`;
};

export function SessionCompare({ olderId, newerId, onOpenSession, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    (async () => {
      try {
        const res = await fetch(`/api/v1/sessions/compare?older=${encodeURIComponent(olderId)}&newer=${encodeURIComponent(newerId)}`);
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || `Comparison failed (HTTP ${res.status})`);
        if (!cancelled) setData(body);
      } catch (e) {
        if (!cancelled) setError(e.message || 'Could not load the comparison.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [olderId, newerId]);

  if (loading) {
    return (
      <div className="pro-card animate-fade-in" style={{ marginBottom: 24 }}>
        <div className="pro-card-body" style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
          <GitCompare size={22} style={{ marginBottom: 8 }} />
          <p style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>Building comparison…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="pro-card animate-fade-in" style={{ marginBottom: 24 }}>
        <div className="pro-card-body">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#dc2626', fontWeight: 700, marginBottom: 6 }}>
            <AlertTriangle size={18} /> Comparison unavailable
          </div>
          <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', marginBottom: 12 }}>{error}</p>
          {onClose && <button className="btn-light" onClick={onClose}>Close</button>}
        </div>
      </div>
    );
  }

  if (!data) return null;

  const { older, newer, score_delta, score_direction, deltas, focus_goal_progress } = data;
  const dirColor = score_direction === 'improved' ? '#059669' : score_direction === 'regressed' ? '#dc2626' : '#64748b';

  return (
    <div className="pro-card animate-fade-in print-break-avoid" style={{ marginBottom: 24 }}>
      <div className="pro-card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <GitCompare size={18} color="var(--primary-purple)" />
          <h3 style={{ fontSize: '1rem', fontWeight: 800, margin: 0 }}>Session Comparison</h3>
        </div>
        {onClose && (
          <button className="btn-light no-print" onClick={onClose} aria-label="Close comparison">
            <X size={15} /> Close
          </button>
        )}
      </div>

      <div className="pro-card-body">
        {/* Score delta front and center */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 18, flexWrap: 'wrap',
          background: 'linear-gradient(135deg, #1e1b4b 0%, #312e81 60%, #4338ca 100%)',
          borderRadius: 'var(--radius-lg)', padding: '20px 24px', color: '#fff', marginBottom: 18,
        }}>
          <button
            type="button"
            onClick={() => onOpenSession && onOpenSession(older.session_id)}
            style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 10, padding: '8px 14px', color: '#e2e8f0', cursor: 'pointer', textAlign: 'center' }}
            title="Open this report"
          >
            <div style={{ fontSize: '1.6rem', fontWeight: 800, lineHeight: 1.1 }}>{Math.round(older.smartspeak_index ?? 0)}</div>
            <div style={{ fontSize: '0.68rem', opacity: 0.75, maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {older.original_filename}
            </div>
          </button>

          <div style={{ textAlign: 'center' }}>
            <ArrowRight size={22} color="#a78bfa" />
            <div style={{
              fontSize: '1.5rem', fontWeight: 800, color: score_direction === 'same' ? '#cbd5e1' : dirColor === '#059669' ? '#6ee7b7' : '#fca5a5',
            }}>
              {score_delta > 0 ? '+' : ''}{score_delta}
            </div>
            <div style={{
              fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em',
              color: score_direction === 'improved' ? '#6ee7b7' : score_direction === 'regressed' ? '#fca5a5' : '#cbd5e1',
            }}>
              {score_direction}
            </div>
          </div>

          <button
            type="button"
            onClick={() => onOpenSession && onOpenSession(newer.session_id)}
            style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 10, padding: '8px 14px', color: '#e2e8f0', cursor: 'pointer', textAlign: 'center' }}
            title="Open this report"
          >
            <div style={{ fontSize: '1.6rem', fontWeight: 800, lineHeight: 1.1 }}>{Math.round(newer.smartspeak_index ?? 0)}</div>
            <div style={{ fontSize: '0.68rem', opacity: 0.75, maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {newer.original_filename}
            </div>
          </button>
        </div>

        {/* Focus-goal progress between the two sessions */}
        {focus_goal_progress && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
            background: focus_goal_progress.improved ? '#ecfdf5' : '#fffbeb',
            border: `1px solid ${focus_goal_progress.improved ? '#a7f3d0' : '#fde68a'}`,
            borderRadius: 'var(--radius-md)', padding: '9px 14px', marginBottom: 14, fontSize: '0.85rem',
          }}>
            {focus_goal_progress.improved
              ? <CheckCircle2 size={15} color="#059669" style={{ flexShrink: 0 }} />
              : <Crosshair size={15} color="#d97706" style={{ flexShrink: 0 }} />}
            <span style={{ color: '#065f46' }}>
              <strong>Focus goal was {focus_goal_progress.goal_label.toLowerCase()}:</strong> {focus_goal_progress.summary}
            </span>
          </div>
        )}

        {/* Metric rows */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {deltas.map((d) => (
            <div key={d.metric} style={{
              display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap',
              background: 'var(--bg-subtle)', border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)', padding: '10px 14px',
            }}>
              <strong style={{ fontSize: '0.88rem', color: 'var(--text-primary)', minWidth: 130 }}>{d.label}</strong>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontFamily: 'var(--font-mono)', fontSize: '0.88rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>{fmtVal(d, 'older')}</span>
                <ArrowRight size={13} color="#94a3b8" />
                <span style={{
                  fontWeight: 700,
                  color: d.direction === 'improved' ? '#059669' : d.direction === 'regressed' ? '#dc2626' : 'var(--text-primary)',
                }}>
                  {fmtVal(d, 'newer')}
                </span>
              </span>
              <DirectionChip direction={d.direction} />
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>{d.verdict}</span>
            </div>
          ))}
          {deltas.length === 0 && (
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textAlign: 'center', padding: '8px 0' }}>
              No comparable metrics — one of these sessions is missing analysis data.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export default SessionCompare;
