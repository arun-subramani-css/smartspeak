import React from 'react';
import { Target, Crosshair, CheckCircle2 } from 'lucide-react';

/**
 * ImprovementPlan — turns the report from descriptive to prescriptive.
 *
 * Rendered above the hero score card. Shows:
 *  - the ranked 2–3 action plan computed by the fusion engine (drills cite
 *    this session's real numbers)
 *  - a banner with the previous session's focus goal and this session's
 *    standing against it (gap to target, or "met" when the target is reached)
 *
 * The component renders nothing when there is no plan and no previous goal,
 * so legacy reports and flawless sessions stay clean.
 */

const LABELS = {
  wpm: 'Speaking pace',
  fillers: 'Filler words',
  pauses: 'Long pauses',
  repetitions: 'Repeated phrases',
  eye_contact: 'Eye contact',
  posture: 'Posture',
  gestures: 'Hand gestures',
  head_movement: 'Head movement',
};

const TARGETS = {
  wpm: { min: 130, max: 160, higherIsBetter: false, band: true },
  fillers: { min: 0, max: 0, higherIsBetter: false },
  pauses: { min: 0, max: 3, higherIsBetter: false },
  repetitions: { min: 0, max: 0, higherIsBetter: false },
  eye_contact: { min: 60, max: 100, higherIsBetter: true },
  posture: { min: 90, max: 100, higherIsBetter: true },
  gestures: { min: 15, max: 60, higherIsBetter: false, band: true },
  head_movement: { min: 80, max: 100, higherIsBetter: true },
};

const fmtValue = (metric, v) => {
  if (v == null || Number.isNaN(Number(v))) return '–';
  if (metric === 'wpm') return `${Math.round(Number(v))} WPM`;
  if (metric === 'fillers' || metric === 'repetitions') return `${Math.round(Number(v))}`;
  if (metric === 'pauses') return `${Number(v).toFixed(1)}s`;
  return `${Math.round(Number(v))}%`;
};

const gapToTarget = (metric, value) => {
  const t = TARGETS[metric];
  if (!t || value == null) return null;
  const v = Number(value);
  if (t.band) {
    if (v < t.min) return t.min - v;   // below band
    if (v > t.max) return v - t.max;   // above band
    return 0;
  }
  if (t.higherIsBetter) return Math.max(0, t.min - v);
  return Math.max(0, v - t.max);
};

/** Previous focus goal banner: shows this session's standing against it. */
function FocusGoalBanner({ previousGoal, plan }) {
  if (!previousGoal) return null;
  const label = LABELS[previousGoal] || previousGoal;
  const action = (plan || []).find((a) => a.metric === previousGoal);

  let status;
  let tone; // 'good' | 'warn'
  if (!action) {
    tone = 'good';
    status = (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: '#059669', fontWeight: 700 }}>
        <CheckCircle2 size={14} />
        {previousGoal === 'gestures' || previousGoal === 'wpm'
          ? 'now within the healthy range'
          : 'target met this session'}
      </span>
    );
  } else {
    const gap = gapToTarget(previousGoal, action.current_value);
    tone = 'warn';
    status = (
      <span style={{ color: '#b45309', fontWeight: 700 }}>
        still {gap != null ? `~${Math.round(gap)}${previousGoal === 'wpm' ? ' WPM' : previousGoal === 'pauses' ? 's' : '%'}` : ''} away — keep working on it below
      </span>
    );
  }

  return (
    <div className="animate-fade-in print-break-avoid" style={{
      display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
      background: tone === 'good' ? '#ecfdf5' : '#fffbeb',
      border: `1px solid ${tone === 'good' ? '#a7f3d0' : '#fde68a'}`,
      borderRadius: 'var(--radius-md)',
      padding: '10px 16px',
      marginBottom: 12,
      fontSize: '0.85rem',
      color: '#065f46',
    }}>
      <Crosshair size={16} color={tone === 'good' ? '#059669' : '#d97706'} style={{ flexShrink: 0 }} />
      <span>
        <strong>Last session's focus:</strong> {label} —{' '}
      </span>
      {status}
    </div>
  );
}

export function ImprovementPlan({ fusionReport }) {
  const plan = fusionReport?.improvement_plan || [];
  const previousGoal = fusionReport?.previous_focus_goal || null;

  if (!plan.length && !previousGoal) return null;

  return (
    <div className="print-break-avoid" style={{ marginBottom: 24 }}>
      <FocusGoalBanner previousGoal={previousGoal} plan={plan} />

      {plan.length > 0 && (
        <div className="animate-fade-in" style={{
          background: 'linear-gradient(135deg, #ffffff 0%, #faf7ff 100%)',
          border: '1px solid var(--primary-purple-border)',
          borderRadius: 'var(--radius-lg)',
          padding: '20px 22px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <Target size={18} color="var(--primary-purple)" />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 800, margin: 0 }}>
              Your improvement plan
            </h3>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
              ranked by impact on your score
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 12 }}>
            {plan.map((a, i) => (
              <div key={a.metric} style={{
                display: 'flex', gap: 12, alignItems: 'flex-start',
                background: '#ffffff',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                padding: '12px 14px',
              }}>
                <div style={{
                  width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
                  background: i === 0 ? 'var(--primary-purple)' : 'var(--primary-purple-light)',
                  color: i === 0 ? '#ffffff' : 'var(--primary-purple)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontWeight: 800, fontSize: '0.85rem',
                }}>
                  {i + 1}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
                    <strong style={{ fontSize: '0.92rem', color: 'var(--text-primary)' }}>{a.title}</strong>
                    <span className="badge-pill" style={{ fontSize: '0.65rem', padding: '1px 8px' }}>
                      {LABELS[a.metric] || a.metric}
                    </span>
                  </div>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', margin: '4px 0 0', lineHeight: 1.5 }}>
                    {a.drill}
                  </p>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>now</div>
                  <strong style={{ fontSize: '0.9rem', color: '#b45309' }}>
                    {fmtValue(a.metric, a.current_value)}
                  </strong>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default ImprovementPlan;
