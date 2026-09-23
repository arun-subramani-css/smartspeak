import React, { useMemo, useState } from 'react';
import { Activity } from 'lucide-react';

/**
 * TimelineChart — unified session timeline rendered as pure SVG (no chart deps).
 *
 * Layers (toggleable via the legend):
 *  - WPM pacing curve with the ideal 110-160 WPM band
 *  - Long pauses (blue spans)
 *  - Looking away / down (amber spans)
 *  - Poor posture (orange spans)
 *  - Head-movement triggers (red ticks)
 *  - Gesture-active segments (green spans)
 *  - Filler words (amber diamonds) & repetitions (purple diamonds)
 *  - Compound mistakes from the fusion report (dark red diamonds)
 */

const W = 1000; // viewBox width
const CURVE_H = 96; // WPM plot height
const LANE_H = 14; // each band lane height
const LANE_GAP = 6;
const PAD_L = 44;
const PAD_R = 12;
const TOP_PAD = 8;

const LAYERS = [
  { key: 'wpm', label: 'WPM Pacing', color: '#7c3aed' },
  { key: 'pauses', label: 'Long Pauses', color: '#2563eb' },
  { key: 'eye', label: 'Looking Away', color: '#d97706' },
  { key: 'posture', label: 'Poor Posture', color: '#ea580c' },
  { key: 'head', label: 'Head Jerks', color: '#dc2626' },
  { key: 'gesture', label: 'Gestures', color: '#059669' },
  { key: 'fillers', label: 'Fillers / Reps', color: '#a16207' },
  { key: 'mistakes', label: 'Mistakes', color: '#991b1b' },
];

const fmt = (s) => {
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m > 0 ? `${m}m${String(sec).padStart(2, '0')}s` : `${sec}s`;
};

export function TimelineChart({ speechAnalysis, visualAnalysis, fusionReport }) {
  const [hidden, setHidden] = useState(new Set());

  const toggle = (key) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const data = useMemo(() => {
    const s = speechAnalysis || {};
    const v = visualAnalysis || {};
    const f = fusionReport || {};

    const windowed = s.wpm_data?.windowed_wpm || [];
    const pauses = s.long_pauses || [];
    const fillers = s.filler_words || [];
    const reps = s.repetitions || [];
    const eyeRanges = v.eye_contact?.looking_away_ranges || [];
    const postureRanges = v.posture?.poor_posture_ranges || [];
    const headTicks = v.head_movement?.excessive_movement_timestamps || [];
    const gestureRanges = v.gesture?.gesture_active_ranges || [];
    const mistakes = (f.mistakes || []).filter((m) => m.category === 'compound');

    const ends = [
      ...windowed.map((w) => Number(w.window_end) || 0),
      ...pauses.map((p) => Number(p.end_time) || 0),
      ...eyeRanges.map((r) => Number(r.end_time) || 0),
      ...postureRanges.map((r) => Number(r.end_time) || 0),
      ...headTicks.map((t) => Number(t) || 0),
      ...gestureRanges.map((r) => Number(r.end_time) || 0),
      ...mistakes.map((m) => Number(m.timestamp) || 0),
      ...reps.map((r) => Number(r.timestamp) || 0),
      Number(s.wpm_data?.total_speaking_duration_seconds) || 0,
    ];
    const duration = Math.max(10, ...ends);

    const maxWpm = Math.max(180, ...windowed.map((w) => Number(w.wpm) || 0)) * 1.08;
    const innerW = W - PAD_L - PAD_R;

    const lanes = [
      { key: 'pauses', visible: pauses.length > 0 },
      { key: 'eye', visible: eyeRanges.length > 0 },
      { key: 'posture', visible: postureRanges.length > 0 },
      { key: 'gesture', visible: gestureRanges.length > 0 },
    ].filter((l) => l.visible);

    const bandStart = TOP_PAD + CURVE_H + 14;
    const bandHeight = lanes.length * (LANE_H + LANE_GAP);
    const totalH = bandStart + bandHeight + 22;

    const x = (t) => PAD_L + ((Number(t) || 0) / duration) * innerW;
    const yWpm = (w) => TOP_PAD + CURVE_H - ((Number(w) || 0) / maxWpm) * CURVE_H;

    return {
      duration, windowed, pauses, fillers, reps, eyeRanges, postureRanges,
      headTicks, gestureRanges, mistakes, maxWpm, innerW, lanes, bandStart, totalH,
      x, yWpm,
    };
  }, [speechAnalysis, visualAnalysis, fusionReport]);

  const isVisible = (key) => !hidden.has(key);
  const show = (...keys) => keys.some(isVisible);

  const {
    duration, windowed, pauses, fillers, reps, eyeRanges, postureRanges,
    headTicks, gestureRanges, mistakes, maxWpm, innerW, lanes, bandStart, totalH,
    x, yWpm,
  } = data;

  // Lane Y positions
  const laneY = {};
  lanes.forEach((lane, i) => {
    laneY[lane.key] = bandStart + i * (LANE_H + LANE_GAP);
  });

  // WPM polyline points (start each window at its start, drop at its end)
  const wpmPoints = [];
  windowed.forEach((w) => {
    wpmPoints.push(`${x(w.window_start)},${yWpm(w.wpm)}`);
    wpmPoints.push(`${x(w.window_end)},${yWpm(w.wpm)}`);
  });

  const idealTop = yWpm(160);
  const idealBottom = yWpm(110);

  const timeTicks = [];
  const step = duration <= 60 ? 10 : duration <= 180 ? 30 : duration <= 600 ? 60 : 120;
  for (let t = 0; t <= duration; t += step) timeTicks.push(t);

  return (
    <div className="animate-fade-in" style={{
      background: '#ffffff',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--radius-lg)',
      padding: '20px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6, flexWrap: 'wrap', gap: 8 }}>
        <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 8, margin: 0 }}>
          <Activity size={18} color="var(--primary-purple)" />
          <span>Session Timeline</span>
        </h4>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          {fmt(duration)} · hover any marker for details · click legend to filter
        </span>
      </div>

      <svg viewBox={`0 0 ${W} ${totalH}`} style={{ width: '100%', height: 'auto', display: 'block' }} role="img" aria-label="Session timeline chart">
        {/* Ideal WPM band */}
        {isVisible('wpm') && (
          <g>
            <rect x={PAD_L} y={idealTop} width={innerW} height={Math.max(2, idealBottom - idealTop)} fill="#10b981" opacity="0.08" />
            <line x1={PAD_L} y1={idealTop} x2={W - PAD_R} y2={idealTop} stroke="#10b981" strokeWidth="1" strokeDasharray="3 4" opacity="0.5" />
            <line x1={PAD_L} y1={idealBottom} x2={W - PAD_R} y2={idealBottom} stroke="#10b981" strokeWidth="1" strokeDasharray="3 4" opacity="0.5" />
            <text x={PAD_L - 6} y={(idealTop + idealBottom) / 2 + 3} textAnchor="end" fontSize="9" fill="#059669" fontWeight="600">ideal</text>
          </g>
        )}

        {/* WPM area + curve */}
        {isVisible('wpm') && wpmPoints.length > 0 && (
          <g>
            <polygon
              points={`${PAD_L},${TOP_PAD + CURVE_H} ${wpmPoints.join(' ')} ${W - PAD_R},${TOP_PAD + CURVE_H}`}
              fill="#7c3aed" opacity="0.07"
            />
            <polyline points={wpmPoints.join(' ')} fill="none" stroke="#7c3aed" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
            {windowed.map((w, i) => (
              <circle key={i} cx={x((Number(w.window_start) + Number(w.window_end)) / 2)} cy={yWpm(w.wpm)} r="3.2" fill="#7c3aed">
                <title>{`WPM ${w.wpm} (${fmt(Number(w.window_start))}–${fmt(Number(w.window_end))})`}</title>
              </circle>
            ))}
          </g>
        )}

        {/* Head-movement trigger ticks across the curve area */}
        {isVisible('head') && headTicks.map((t, i) => (
          <line key={i} x1={x(t)} y1={TOP_PAD} x2={x(t)} y2={TOP_PAD + CURVE_H} stroke="#dc2626" strokeWidth="1.4" opacity="0.55">
            <title>{`Rapid head movement @ ${fmt(Number(t))}`}</title>
          </line>
        ))}

        {/* Fillers (diamonds) & repetitions */}
        {isVisible('fillers') && fillers.map((f, i) => {
          const cx = x(f.timestamp);
          const cy = yWpm(Math.min(maxWpm, 9999)) + 12; // sit just under the top edge
          const py = TOP_PAD + 10;
          return (
            <polygon key={i} points={`${cx},${py - 5} ${cx + 4.4},${py} ${cx},${py + 5} ${cx - 4.4},${py}`}
              fill="#f59e0b" stroke="#92400e" strokeWidth="0.8">
              <title>{`Filler "${f.word}" @ ${fmt(Number(f.timestamp))}`}</title>
            </polygon>
          );
        })}
        {isVisible('fillers') && reps.map((r, i) => {
          const cx = x(r.timestamp);
          const py = TOP_PAD + 22;
          return (
            <polygon key={i} points={`${cx},${py - 5} ${cx + 4.4},${py} ${cx},${py + 5} ${cx - 4.4},${py}`}
              fill="#8b5cf6" stroke="#5b21b6" strokeWidth="0.8">
              <title>{`Repetition "${r.phrase}" ×${r.count} @ ${fmt(Number(r.timestamp))}`}</title>
            </polygon>
          );
        })}

        {/* Compound mistakes from fusion */}
        {isVisible('mistakes') && mistakes.map((m, i) => {
          const cx = x(m.timestamp);
          const py = TOP_PAD + CURVE_H + 6;
          return (
            <polygon key={i} points={`${cx},${py - 5.5} ${cx + 5},${py} ${cx},${py + 5.5} ${cx - 5},${py}`}
              fill={m.severity === 'high' ? '#dc2626' : '#991b1b'} opacity="0.92">
              <title>{`${m.description} @ ${fmt(Number(m.timestamp))}`}</title>
            </polygon>
          );
        })}

        {/* Band lanes */}
        {lanes.map((lane) => {
          const y = laneY[lane.key];
          if (!isVisible(lane.key)) return null;
          let ranges = [];
          let fill = '#2563eb';
          let label = '';
          if (lane.key === 'pauses') { ranges = pauses; fill = '#2563eb'; label = 'Pauses'; }
          if (lane.key === 'eye') { ranges = eyeRanges; fill = '#d97706'; label = 'Looking away'; }
          if (lane.key === 'posture') { ranges = postureRanges; fill = '#ea580c'; label = 'Poor posture'; }
          if (lane.key === 'gesture') { ranges = gestureRanges; fill = '#059669'; label = 'Gesturing'; }
          return (
            <g key={lane.key}>
              <text x={PAD_L - 8} y={y + LANE_H - 3} textAnchor="end" fontSize="9.5" fill="var(--text-muted, #64748b)" fontWeight="600">{label}</text>
              <line x1={PAD_L} y1={y + LANE_H / 2} x2={W - PAD_R} y2={y + LANE_H / 2} stroke="#e2e8f0" strokeWidth="1" />
              {ranges.map((r, i) => {
                const rx = x(r.start_time);
                const rw = Math.max(2.5, x(r.end_time) - rx);
                return (
                  <rect key={i} x={rx} y={y} width={rw} height={LANE_H} rx="3" fill={fill} opacity="0.75">
                    <title>{`${label}: ${fmt(Number(r.start_time))} – ${fmt(Number(r.end_time))} (${(Number(r.duration) || 0).toFixed(1)}s)`}</title>
                  </rect>
                );
              })}
            </g>
          );
        })}

        {/* Time axis */}
        <line x1={PAD_L} y1={totalH - 14} x2={W - PAD_R} y2={totalH - 14} stroke="#cbd5e1" strokeWidth="1" />
        {timeTicks.map((t) => (
          <g key={t}>
            <line x1={x(t)} y1={totalH - 14} x2={x(t)} y2={totalH - 10} stroke="#cbd5e1" strokeWidth="1" />
            <text x={x(t)} y={totalH - 1} textAnchor="middle" fontSize="9.5" fill="#64748b">{fmt(t)}</text>
          </g>
        ))}
      </svg>

      {/* Legend */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
        {LAYERS.map((l) => {
          const off = hidden.has(l.key);
          return (
            <button
              key={l.key}
              type="button"
              onClick={() => toggle(l.key)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                padding: '3px 10px', borderRadius: 999, fontSize: '0.72rem', fontWeight: 600,
                cursor: 'pointer', transition: 'opacity .15s ease',
                border: `1px solid ${off ? '#e2e8f0' : l.color + '55'}`,
                background: off ? '#f8fafc' : l.color + '14',
                color: off ? '#94a3b8' : l.color,
                textDecoration: off ? 'line-through' : 'none',
              }}
            >
              <span style={{ width: 8, height: 8, borderRadius: 2, background: off ? '#cbd5e1' : l.color }} />
              {l.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default TimelineChart;
