import React, { useEffect, useMemo, useState } from 'react';
import { LineChart, TrendingUp } from 'lucide-react';

function scoreColor(v) {
  if (v == null) return '#64748b';
  if (v >= 70) return '#10b981';
  if (v >= 40) return '#f59e0b';
  return '#ef4444';
}

const METRICS = [
  { key: 'smartspeak_index', label: 'SmartSpeak Score', color: '#7c3aed' },
  { key: 'eye_contact_rate', label: 'Eye Contact', color: '#0369a1' },
  { key: 'posture_score', label: 'Posture', color: '#10b981' },
];

const GOAL_LABELS = {
  wpm: 'Pace', fillers: 'Fillers', pauses: 'Pauses', repetitions: 'Repeats',
  eye_contact: 'Eye contact', posture: 'Posture', gestures: 'Gestures', head_movement: 'Head',
};

/**
 * ScoreTrendChart — progress-over-time line chart of the most recent
 * completed sessions. Pure SVG, no chart library. Renders only when
 * there are at least 2 completed sessions to compare.
 */
export function ScoreTrendChart() {
  const [sessions, setSessions] = useState(null);
  const [hidden, setHidden] = useState(() => new Set());

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/v1/sessions/history?limit=12&completed_only=true');
        if (!res.ok) throw new Error(`history request failed (${res.status})`);
        const data = await res.json();
        if (!cancelled) setSessions((data.sessions || []).slice().reverse()); // oldest → newest
      } catch {
        if (!cancelled) setSessions([]); // hide silently when unreachable
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const series = useMemo(() => {
    if (!sessions) return null;
    const w = 640, h = 200, padX = 38, padY = 24;
    const n = sessions.length;
    const x = (i) => (n === 1 ? w / 2 : padX + (i * (w - padX * 2)) / (n - 1));
    const y = (v) => h - padY - (Math.max(0, Math.min(100, v)) / 100) * (h - padY * 2);
    return {
      w, h, x, y,
      dates: sessions.map((s) => new Date(s.upload_timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })),
      lines: METRICS.filter((m) => !hidden.has(m.key)).map((m) => ({
        ...m,
        points: sessions.map((s, i) => ({ i, v: s[m.key] })).filter((p) => p.v != null),
      })),
      dots: sessions.map((s, i) => ({ i, v: s.smartspeak_index })),
      sessionIds: sessions.map((s) => s.session_id),
      filenames: sessions.map((s) => s.original_filename),
    };
  }, [sessions, hidden]);

  if (!sessions || sessions.length < 2) return null;

  const toggle = (key) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  return (
    <div className="pro-card animate-fade-in" style={{ marginTop: 24 }}>
      <div className="pro-card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <TrendingUp size={18} color="var(--primary-purple)" />
          <h3 style={{ fontSize: '1rem', fontWeight: 800, margin: 0 }}>Progress Over Time</h3>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            last {sessions.length} sessions, oldest → newest
          </span>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {METRICS.map((m) => {
            const off = hidden.has(m.key);
            return (
              <button
                key={m.key}
                type="button"
                onClick={() => toggle(m.key)}
                aria-pressed={!off}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  border: `1px solid ${off ? 'var(--border-subtle)' : `${m.color}55`}`,
                  background: off ? '#ffffff' : `${m.color}14`,
                  color: off ? 'var(--text-muted)' : m.color,
                  borderRadius: 999, padding: '3px 12px',
                  fontSize: '0.72rem', fontWeight: 700, cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: off ? '#cbd5e1' : m.color }} />
                {m.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="pro-card-body" style={{ paddingTop: 18 }}>
        {series && (
          <svg viewBox={`0 0 ${series.w} ${series.h}`} style={{ width: '100%', height: 'auto', display: 'block' }} role="img"
            aria-label="Line chart of your scores across recent sessions">
            {/* horizontal gridlines */}
            {[0, 25, 50, 75, 100].map((g) => (
              <g key={g}>
                <line x1={series.x(0) - 20} x2={series.w - 8} y1={series.y(g)} y2={series.y(g)}
                  stroke="#e2e8f0" strokeWidth="1" strokeDasharray={g === 0 ? undefined : '3 5'} />
                <text x={series.x(0) - 26} y={series.y(g) + 4} textAnchor="end" fontSize="9" fill="#94a3b8">{g}</text>
              </g>
            ))}

            {/* lines */}
            {series.lines.map((line) => {
              if (line.points.length === 0) return null;
              const d = line.points.map((p, j) => `${j === 0 ? 'M' : 'L'} ${series.x(p.i)} ${series.y(p.v)}`).join(' ');
              return (
                <g key={line.key}>
                  <path d={d} fill="none" stroke={line.color} strokeWidth="2.5"
                    strokeLinecap="round" strokeLinejoin="round" opacity="0.9" />
                  {line.points.map((p) => (
                    <circle key={`${line.key}-${p.i}`} cx={series.x(p.i)} cy={series.y(p.v)} r="3.5"
                      fill="#ffffff" stroke={line.color} strokeWidth="2">
                      <title>{`${line.label}: ${Math.round(p.v)} — ${series.filenames[p.i] || ''} (${series.dates[p.i]})`}</title>
                    </circle>
                  ))}
                </g>
              );
            })}

            {/* x labels */}
            {series.dates.map((d, i) => (
              <text key={i} x={series.x(i)} y={series.h - 6} textAnchor="middle" fontSize="9" fill="#94a3b8">
                {series.dates.length > 8 && i % 2 === 1 ? '' : d}
              </text>
            ))}

            {/* Focus-goal markers: what each session set out to work on */}
            {sessions.map((s, i) => {
              const goal = s.focus_goal;
              if (!goal || hidden.has('smartspeak_index')) return null;
              const y = series.y(s.smartspeak_index ?? 0);
              return (
                <g key={`goal-${i}`}>
                  <circle cx={series.x(i)} cy={y} r="8.5" fill="none" stroke="#d97706" strokeWidth="1.6" strokeDasharray="2.5 2.5">
                    <title>{`Focus goal: ${GOAL_LABELS[goal] || goal} — ${series.filenames[i] || ''} (${series.dates[i]})`}</title>
                  </circle>
                </g>
              );
            })}
          </svg>
        )}

        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 10, marginBottom: 0 }}>
          <LineChart size={12} style={{ verticalAlign: '-2px' }} /> Hover any point for session details. Click a legend chip to focus on one metric. Dashed rings mark each session's focus goal.
        </p>
      </div>
    </div>
  );
}

export default ScoreTrendChart;
