import React from 'react';
import { Activity, Zap, Waves, RotateCcw } from 'lucide-react';

/**
 * DeliveryDynamics — surfaces the higher-order delivery metrics computed by
 * the fusion engine's delivery_dynamics module: energy-curve peak placement,
 * rhythm variety (Shannon entropy of speech/breath alternation), and momentum
 * recovery after long pauses. Renders nothing for legacy/short sessions.
 */

const PART_ICONS = { 'Energy curve': Zap, 'Rhythm variety': Waves, 'Momentum recovery': RotateCcw };

const scoreColor = (v) => {
  if (v >= 70) return '#059669';
  if (v >= 40) return '#d97706';
  return '#dc2626';
};

function MiniSparkline({ curve }) {
  if (!curve || curve.length < 2) return null;
  const w = 120, h = 30, pad = 2;
  const max = Math.max(...curve, 1);
  const pts = curve
    .map((v, i) => `${pad + (i * (w - 2 * pad)) / (curve.length - 1)},${h - pad - (v / max) * (h - 2 * pad)}`)
    .join(' ');
  const peakIdx = curve.indexOf(Math.max(...curve));
  const peakX = pad + (peakIdx * (w - 2 * pad)) / (curve.length - 1);
  return (
    <svg width={w} height={h} style={{ flexShrink: 0 }} aria-hidden="true">
      <polyline points={pts} fill="none" stroke="#7c3aed" strokeWidth="2" strokeLinejoin="round" />
      <circle cx={peakX} cy={pad + 2} r="3" fill="#7c3aed" />
    </svg>
  );
}

export function DeliveryDynamics({ fusionReport }) {
  const dd = fusionReport?.delivery_dynamics;
  if (!dd || !dd.parts || dd.parts.length === 0) return null;

  const energy = dd.energy_curve;

  return (
    <div className="pro-card print-break-avoid animate-fade-in" style={{ marginBottom: 24 }}>
      <div className="pro-card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Activity size={18} color="var(--primary-purple)" />
          <h3 style={{ fontSize: '1rem', fontWeight: 800, margin: 0 }}>Delivery Dynamics</h3>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            how your delivery moves over time — not just what it averaged
          </span>
        </div>
        <strong style={{ fontSize: '0.95rem', color: scoreColor(dd.overall) }}>
          {dd.overall}
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}> /100</span>
        </strong>
      </div>
      <div className="pro-card-body" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {dd.parts.map((part) => {
          const Icon = PART_ICONS[part.name] || Activity;
          return (
            <div key={part.name} style={{
              display: 'flex', alignItems: 'flex-start', gap: 12,
              background: 'var(--bg-subtle)', border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)', padding: '10px 14px',
            }}>
              <Icon size={16} color={scoreColor(part.score)} style={{ flexShrink: 0, marginTop: 2 }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                  <strong style={{ fontSize: '0.88rem' }}>{part.name}</strong>
                  <strong style={{ fontSize: '0.8rem', color: scoreColor(part.score) }}>{part.score}</strong>
                </div>
                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: '2px 0 0', lineHeight: 1.5 }}>
                  {part.verdict}
                </p>
              </div>
            </div>
          );
        })}
        {energy && energy.curve && energy.curve.length >= 2 && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap',
            background: 'var(--bg-subtle)', border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)', padding: '10px 14px',
          }}>
            <MiniSparkline curve={energy.curve} />
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              Speaking-energy envelope across the talk — the dot marks where your energy peaked
              ({Math.round((energy.peak_fraction ?? 0) * 100)}% through).
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export default DeliveryDynamics;
