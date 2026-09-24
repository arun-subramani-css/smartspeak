import React, { useEffect, useState } from 'react';
import {
  RefreshCw, CheckCircle2, Clock, AlertTriangle, Music, Image as ImageIcon,
  Copy, Check, ArrowLeft, Film, MessageSquare, Gauge, AlertOctagon, Repeat, Sparkles, Volume2, Award, TrendingUp, Download, MousePointerClick
} from 'lucide-react';
import { TimelineChart } from './TimelineChart';
import { ReportVideoProvider, ReportVideoPlayer, useReportVideo } from './ReportVideoPlayer';
import { InteractiveTranscript } from './InteractiveTranscript';

function scoreColor(v) {
  if (v >= 70) return '#10b981';
  if (v >= 40) return '#f59e0b';
  return '#ef4444';
}

/** Thin colored progress bar under a metric value. */
function MetricBar({ value, color }) {
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  const c = color || scoreColor(v);
  return (
    <div style={{ height: '5px', background: 'var(--border-subtle)', borderRadius: '3px', overflow: 'hidden', marginTop: '10px' }}>
      <div style={{
        width: `${v}%`,
        height: '100%',
        background: `linear-gradient(90deg, ${c}, ${c}aa)`,
        borderRadius: '3px',
        transition: 'width 0.6s ease',
      }} />
    </div>
  );
}

/**
 * Seekable — wraps any timestamped annotation. When the session video is
 * available, clicking it seeks the video to `t`; otherwise it renders as a
 * normal non-clickable element.
 */
function Seekable({ t, children, style, as: El = 'span', ...rest }) {
  const { seekTo, hasVideo } = useReportVideo();
  return (
    <El
      onClick={hasVideo ? () => seekTo(t) : undefined}
      title={hasVideo ? 'Click to watch this moment' : undefined}
      style={{ ...style, ...(hasVideo ? { cursor: 'pointer' } : {}) }}
      {...rest}
    >
      {children}
    </El>
  );
}

/** Passes the video seek callback into the timeline chart. */
function TimelineWithSeek(props) {
  const { seekTo } = useReportVideo();
  return <TimelineChart {...props} onSeek={seekTo} />;
}

export function StatusTracker({ sessionId, onReset }) {
  const [statusData, setStatusData] = useState(null);
  const [speechAnalysis, setSpeechAnalysis] = useState(null);
  const [visualAnalysis, setVisualAnalysis] = useState(null);
  const [fusionReport, setFusionReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const [showAllFrames, setShowAllFrames] = useState(false);
  const [selectedFrameSrc, setSelectedFrameSrc] = useState(null);

  const fetchStatus = async () => {
    try {
      const res = await fetch(`/api/v1/sessions/${sessionId}/status`);
      if (!res.ok) {
        throw new Error(`Session status request failed (HTTP ${res.status})`);
      }
      const data = await res.json();
      setStatusData(data);
      setError(null);

      if (
        data.has_speech_analysis ||
        data.status === 'speech_analysis_complete' ||
        data.status === 'ready_for_fusion' ||
        data.status === 'fusion_complete'
      ) {
        fetchSpeechAnalysis();
      }

      if (
        data.has_visual_analysis ||
        data.status === 'visual_analysis_complete' ||
        data.status === 'ready_for_fusion' ||
        data.status === 'fusion_complete'
      ) {
        fetchVisualAnalysis();
      }

      if (
        data.has_fusion_report ||
        data.status === 'ready_for_fusion' ||
        data.status === 'fusion_complete' ||
        (data.has_speech_analysis && data.has_visual_analysis)
      ) {
        fetchFusionReport();
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchSpeechAnalysis = async () => {
    try {
      const res = await fetch(`/api/v1/sessions/${sessionId}/speech-analysis`);
      if (res.ok) {
        const data = await res.json();
        setSpeechAnalysis(data.speech_analysis);
      }
    } catch (e) {
      console.error("Failed to fetch speech analysis details:", e);
    }
  };

  const fetchVisualAnalysis = async () => {
    try {
      const res = await fetch(`/api/v1/sessions/${sessionId}/visual-analysis`);
      if (res.ok) {
        const data = await res.json();
        setVisualAnalysis(data.visual_analysis);
      }
    } catch (e) {
      console.error("Failed to fetch visual analysis details:", e);
    }
  };

  const fetchFusionReport = async () => {
    try {
      const res = await fetch(`/api/v1/sessions/${sessionId}/fusion-report`);
      if (res.ok) {
        const data = await res.json();
        setFusionReport(data.fusion_report);
      }
    } catch (e) {
      console.error("Failed to fetch fusion report details:", e);
    }
  };

  useEffect(() => {
    if (!sessionId) return;

    fetchStatus();
    const interval = setInterval(() => {
      if (statusData && (statusData.status === 'fusion_complete' || (statusData.has_fusion_report && fusionReport) || statusData.status === 'failed')) {
        clearInterval(interval);
        return;
      }
      fetchStatus();
    }, 2000);

    return () => clearInterval(interval);
  }, [sessionId, statusData?.status, Boolean(fusionReport)]);

  const copySessionId = () => {
    navigator.clipboard.writeText(sessionId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'uploaded':
        return <span className="badge-pill" style={{ background: '#eff6ff', color: '#2563eb' }}>Staged & Queued</span>;
      case 'processing':
        return (
          <span className="badge-pill" style={{ background: '#fef3c7', color: '#d97706' }}>
            <RefreshCw size={12} className="animate-spin" /> Processing
          </span>
        );
      case 'processed':
        return (
          <span className="badge-pill" style={{ background: '#ecfdf5', color: '#059669' }}>
            <CheckCircle2 size={12} /> Audio & Frames Processed
          </span>
        );
      case 'speech_analysis_complete':
        return (
          <span className="badge-pill" style={{ background: '#f3e8ff', color: '#7c3aed', border: '1px solid #e9d5ff' }}>
            <Sparkles size={12} /> Speech Analysis Complete
          </span>
        );
      case 'visual_analysis_complete':
        return (
          <span className="badge-pill" style={{ background: '#e0f2fe', color: '#0369a1', border: '1px solid #bae6fd' }}>
            <ImageIcon size={12} /> Visual Analysis Complete
          </span>
        );
      case 'ready_for_fusion':
        return (
          <span className="badge-pill" style={{ background: '#ecfdf5', color: '#047857', border: '1px solid #a7f3d0' }}>
            <CheckCircle2 size={12} /> Speech & Visual Complete (Ready for Fusion)
          </span>
        );
      case 'fusion_complete':
        return (
          <span className="badge-pill" style={{ background: '#ecfdf5', color: '#059669', border: '1px solid #a7f3d0', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <CheckCircle2 size={12} /> Complete Coaching Analysis Ready
          </span>
        );
      case 'failed':
        return (
          <span className="badge-pill" style={{ background: '#fef2f2', color: '#dc2626' }}>
            <AlertTriangle size={12} /> Processing Failed
          </span>
        );
      default:
        return <span className="badge-pill">{status}</span>;
    }
  };

  const totalFrames = statusData?.frame_count || 0;
  const displayedCount = showAllFrames ? totalFrames : Math.min(totalFrames, 12);
  const frameList = totalFrames > 0
    ? Array.from({ length: displayedCount }, (_, i) => {
      const frameNum = String(i + 1).padStart(4, '0');
      return `/data/processed/${sessionId}/frames/frame_${frameNum}.jpg`;
    })
    : [];

  const isProcessedOrAnalyzed = statusData?.status === 'processed' || statusData?.status === 'speech_analysis_complete' || statusData?.status === 'visual_analysis_complete' || statusData?.status === 'ready_for_fusion' || statusData?.status === 'fusion_complete' || statusData?.has_speech_analysis || statusData?.has_visual_analysis || statusData?.has_fusion_report || Boolean(fusionReport);

  return (
    <div className="pro-card">
      {/* Hidden print-only report header */}
      <div className="print-show" style={{ display: 'none', padding: '4px 0 18px', borderBottom: '2px solid #e2e8f0', marginBottom: '8px' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 800, margin: 0 }}>SmartSpeak Coaching Report</h1>
        <p style={{ fontSize: '0.85rem', color: '#475569', margin: '4px 0 0' }}>
          {statusData?.original_filename || 'Session'} · generated {new Date().toLocaleString()}
        </p>
      </div>

      <div className="pro-card-header">
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)' }}>
            Processing Status & Metrics
          </h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '2px' }}>
            Real-time pipeline monitoring & speech analysis report
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          {fusionReport && (
            <button onClick={() => window.print()} className="btn-purple no-print" style={{ padding: '8px 16px', fontSize: '0.875rem' }}>
              <Download size={16} />
              <span>Download PDF</span>
            </button>
          )}
          <button onClick={onReset} className="btn-light no-print">
            <ArrowLeft size={16} />
            <span>Upload Another Video</span>
          </button>
        </div>
      </div>

      <div className="pro-card-body">
        <ReportVideoProvider sessionId={sessionId}>
        {/* Session Metadata Banner — compact while processing */}
        <div className="no-print" style={{
          background: 'var(--bg-subtle)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: '14px 20px',
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '16px'
        }}>
          <div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700 }}>
              Session Identifier (UUID)
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '4px' }}>
              <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.95rem', fontWeight: 700, color: 'var(--primary-purple)' }}>
                {sessionId}
              </code>
              <button
                onClick={copySessionId}
                className="btn-light"
                style={{ padding: '3px 8px', fontSize: '0.75rem' }}
              >
                {copied ? <Check size={14} color="#059669" /> : <Copy size={14} />}
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '20px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            <div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase', fontWeight: 700 }}>
                File
              </span>
              <strong style={{ color: 'var(--text-primary)' }}>{statusData?.original_filename || '...'}</strong>
            </div>

            <div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase', fontWeight: 700 }}>
                Size
              </span>
              <strong style={{ color: 'var(--text-primary)' }}>
                {statusData?.file_size ? `${(statusData.file_size / (1024 * 1024)).toFixed(2)} MB` : '...'}
              </strong>
            </div>

            <div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase', fontWeight: 700 }}>
                Timestamp
              </span>
              <span>
                {statusData?.upload_timestamp ? new Date(statusData.upload_timestamp).toLocaleTimeString() : '...'}
              </span>
            </div>
          </div>
        </div>

        {/* Loading Skeleton */}
        {loading && !statusData && (
          <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)' }}>
            <RefreshCw size={32} className="animate-spin" style={{ color: 'var(--primary-purple)', marginBottom: '12px' }} />
            <p style={{ fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 4 }}>Loading your report…</p>
            <p style={{ fontSize: '0.82rem' }}>Fetching the latest session state.</p>
          </div>
        )}

        {statusData && (
          <div>
            {/* Session banner stays visible while processing; metadata only once done */}
            {statusData.status === 'processing' && (() => {
              const stageLabels = {
                processing: 'Extracting audio & video frames...',
                analyzing: 'Running speech & visual analysis...',
                fusion: 'Building your fusion report...',
              };
              const bars = [
                { key: 'speech_progress', label: 'Speech', data: statusData.speech_progress },
                { key: 'visual_progress', label: 'Visual', data: statusData.visual_progress },
              ].filter((b) => b.data && typeof b.data.percent === 'number');
              return (
                <div style={{
                  background: 'var(--bg-subtle)',
                  border: '1px solid var(--border-subtle)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '18px 20px',
                  marginBottom: '24px'
                }}>
                  <div style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: bars.length ? '12px' : '0' }}>
                    <RefreshCw size={16} className="animate-spin" color="var(--primary-purple)" />
                    <span>{stageLabels[statusData.progress_stage] || 'Processing your video...'}</span>
                  </div>
                  {bars.map(({ key, label, data }) => (
                    <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
                      <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-secondary)', width: '52px' }}>{label}</span>
                      <div style={{ flex: 1, height: '6px', background: 'var(--border-subtle)', borderRadius: '3px', overflow: 'hidden' }}>
                        <div style={{
                          width: `${Math.min(100, Math.max(2, data.percent))}%`,
                          height: '100%',
                          background: 'linear-gradient(90deg, var(--primary-purple), #a78bfa)',
                          borderRadius: '3px',
                          transition: 'width 0.6s ease',
                        }} />
                      </div>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', minWidth: '110px' }}>
                        {Math.round(data.percent)}%{data.detail ? ` — ${data.detail}` : ''}
                      </span>
                    </div>
                  ))}
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '6px' }}>
                    You can keep this tab open — the report will appear here automatically.
                  </div>
                </div>
              );
            })()}

            {/* Status Bar */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '14px 18px',
              background: '#ffffff',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              marginBottom: '24px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Status:</span>
                {getStatusBadge(statusData.status)}
              </div>
            </div>

            {/* Session Video — hidden entirely when the file is gone */}
            <ReportVideoPlayer />

            {/* Error Banner */}
            {statusData.status === 'failed' && (
              <div style={{
                padding: '18px',
                background: '#fef2f2',
                border: '1px solid #fecaca',
                borderRadius: 'var(--radius-lg)',
                color: '#dc2626',
                marginBottom: '24px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '0.95rem', marginBottom: '4px' }}>
                  <AlertTriangle size={20} />
                  <span>Processing Failed</span>
                </div>
                <p style={{ fontSize: '0.875rem', color: '#991b1b', marginBottom: '12px' }}>
                  Reason: {statusData.error_reason || 'Unknown decoding or speech analysis error.'}
                </p>
                <button onClick={onReset} className="btn-light" style={{ background: '#ffffff', borderColor: '#fca5a5' }}>
                  <span>Try Uploading Again</span>
                </button>
              </div>
            )}

            {/* Overall Performance & SmartSpeak Index Hero Card */}
            {fusionReport && (
              <div style={{
                background: 'linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%)',
                color: '#ffffff',
                borderRadius: 'var(--radius-xl, 16px)',
                padding: '24px 28px',
                marginBottom: '24px',
                boxShadow: '0 10px 25px -5px rgba(67, 56, 202, 0.3)',
                position: 'relative',
                overflow: 'hidden'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '20px' }}>
                  {/* Left: Overall Score and Grade */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '22px' }}>
                    <div style={{
                      width: '88px',
                      height: '88px',
                      borderRadius: '50%',
                      background: 'rgba(255, 255, 255, 0.12)',
                      border: '3px solid rgba(255, 255, 255, 0.35)',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0
                    }}>
                      <span style={{ fontSize: '1.9rem', fontWeight: 800, lineHeight: 1 }}>
                        {Math.round(fusionReport.smartspeak_index)}
                      </span>
                      <span style={{ fontSize: '0.65rem', textTransform: 'uppercase', letterSpacing: '0.08em', opacity: 0.8, marginTop: '2px' }}>
                        Score / 100
                      </span>
                    </div>

                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <h3 style={{ fontSize: '1.4rem', fontWeight: 800, margin: 0, letterSpacing: '-0.01em' }}>
                          Overall Performance Score
                        </h3>
                        <span style={{
                          padding: '4px 12px',
                          borderRadius: '20px',
                          fontSize: '0.78rem',
                          fontWeight: 700,
                          letterSpacing: '0.04em',
                          textTransform: 'uppercase',
                          background: fusionReport.grade === 'Executive' ? '#10b981' :
                                      fusionReport.grade === 'Polished' ? '#3b82f6' :
                                      fusionReport.grade === 'Competent' ? '#8b5cf6' : '#f59e0b',
                          color: '#ffffff'
                        }}>
                          {fusionReport.grade}
                        </span>
                      </div>
                      <p style={{ margin: '6px 0 0 0', fontSize: '0.88rem', color: 'rgba(255, 255, 255, 0.82)' }}>
                        Composite SmartSpeak Index evaluating verbal pacing, physical presence & confidence
                      </p>
                    </div>
                  </div>

                  {/* Right: Sub-Score Badges */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
                    <div style={{
                      background: 'rgba(255, 255, 255, 0.08)',
                      backdropFilter: 'blur(8px)',
                      border: '1px solid rgba(255, 255, 255, 0.15)',
                      borderRadius: '12px',
                      padding: '10px 16px',
                      textAlign: 'center',
                      minWidth: '105px'
                    }}>
                      <span style={{ display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'rgba(255, 255, 255, 0.7)' }}>
                        Verbal (40%)
                      </span>
                      <strong style={{ fontSize: '1.25rem', fontWeight: 800, color: '#a7f3d0' }}>
                        {fusionReport.verbal_score}%
                      </strong>
                    </div>

                    <div style={{
                      background: 'rgba(255, 255, 255, 0.08)',
                      backdropFilter: 'blur(8px)',
                      border: '1px solid rgba(255, 255, 255, 0.15)',
                      borderRadius: '12px',
                      padding: '10px 16px',
                      textAlign: 'center',
                      minWidth: '105px'
                    }}>
                      <span style={{ display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'rgba(255, 255, 255, 0.7)' }}>
                        Non-Verbal (40%)
                      </span>
                      <strong style={{ fontSize: '1.25rem', fontWeight: 800, color: '#bfdbfe' }}>
                        {fusionReport.non_verbal_score}%
                      </strong>
                    </div>

                    <div style={{
                      background: 'rgba(255, 255, 255, 0.08)',
                      backdropFilter: 'blur(8px)',
                      border: '1px solid rgba(255, 255, 255, 0.15)',
                      borderRadius: '12px',
                      padding: '10px 16px',
                      textAlign: 'center',
                      minWidth: '105px'
                    }}>
                      <span style={{ display: 'block', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'rgba(255, 255, 255, 0.7)' }}>
                        Confidence (20%)
                      </span>
                      <strong style={{ fontSize: '1.25rem', fontWeight: 800, color: '#ddd6fe' }}>
                        {fusionReport.ml_confidence_score}%
                      </strong>
                    </div>
                  </div>
                </div>

                {/* Behavioral Cues & Feedback */}
                {fusionReport.mistakes && fusionReport.mistakes.length > 0 && (
                  <div style={{
                    marginTop: '18px',
                    paddingTop: '16px',
                    borderTop: '1px solid rgba(255, 255, 255, 0.15)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px'
                  }}>
                    <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'rgba(255, 255, 255, 0.75)', fontWeight: 700 }}>
                      Key Behavioral Feedback ({fusionReport.mistakes.length} moments identified)
                    </span>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>                        {fusionReport.mistakes.slice(0, 5).map((m, idx) => (
                          <Seekable key={idx} t={m.timestamp} as="div" style={{
                            background: 'rgba(0, 0, 0, 0.25)',
                            borderRadius: '8px',
                            padding: '6px 12px',
                            fontSize: '0.8rem',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            border: '1px solid rgba(255, 255, 255, 0.1)',
                            transition: 'background 0.15s ease'
                          }}>
                            <span style={{
                              width: '8px',
                              height: '8px',
                              borderRadius: '50%',
                              background: m.severity === 'high' ? '#f87171' : m.severity === 'medium' ? '#fbbf24' : '#60a5fa',
                              flexShrink: 0
                            }} />
                            <span>{m.description}</span>
                            <span style={{ opacity: 0.6, fontSize: '0.72rem' }}>@{Number(m.timestamp).toFixed(1)}s</span>
                          </Seekable>
                      ))}
                    </div>
                  </div>
                )}

                {/* Gesture ↔ Speech Correlation Insights */}
                {fusionReport.speech_gesture_correlation && fusionReport.speech_gesture_correlation.length > 0 && (
                  <div style={{
                    marginTop: '14px',
                    paddingTop: '14px',
                    borderTop: '1px solid rgba(255, 255, 255, 0.15)'
                  }}>
                    <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'rgba(255, 255, 255, 0.75)', fontWeight: 700 }}>
                      Gesture ↔ Speech Correlation ({fusionReport.speech_gesture_correlation.length})
                    </span>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '8px' }}>
                      {fusionReport.speech_gesture_correlation.slice(0, 6).map((c, i) => (
                        <Seekable key={i} t={c.timestamp} as="div" style={{
                          background: 'rgba(0, 0, 0, 0.25)',
                          border: '1px solid rgba(255, 255, 255, 0.1)',
                          borderRadius: '8px',
                          padding: '6px 12px',
                          fontSize: '0.8rem',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          transition: 'background 0.15s ease'
                        }}>
                          <span style={{
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            flexShrink: 0,
                            background: c.events?.includes('fluent') ? '#34d399' : (c.severity === 'medium' ? '#fbbf24' : '#60a5fa')
                          }} />
                          <span>{c.description}</span>
                          <span style={{ opacity: 0.6, fontSize: '0.72rem' }}>@{Number(c.timestamp).toFixed(1)}s</span>
                        </Seekable>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Processed Audio & Frame Cards */}
            {isProcessedOrAnalyzed && (
              <div className="stagger" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  {/* Audio Card */}
                  <div style={{
                    background: 'var(--bg-subtle)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '20px'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                      <div style={{ background: 'var(--primary-purple-light)', padding: '8px', borderRadius: '8px', color: 'var(--primary-purple)' }}>
                        <Music size={20} />
                      </div>
                      <div>
                        <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)' }}>Audio Track Extracted</h4>
                        <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Whisper Compliant • 16kHz Mono</p>
                      </div>
                    </div>

                    <div style={{ background: '#ffffff', padding: '10px', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                      <audio controls style={{ width: '100%', height: '36px' }} src={`/data/${statusData.audio_path}`} />
                    </div>
                  </div>

                  {/* Frames Card */}
                  <div style={{
                    background: 'var(--bg-subtle)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '20px'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                      <div style={{ background: 'var(--primary-purple-light)', padding: '8px', borderRadius: '8px', color: 'var(--primary-purple)' }}>
                        <ImageIcon size={20} />
                      </div>
                      <div>
                        <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)' }}>Video Frames Extracted</h4>
                        <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>1 FPS Sampling • Posture Analysis</p>
                      </div>
                    </div>

                    <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                      <p>• Total Frames Extracted: <strong style={{ color: 'var(--primary-purple)' }}>{statusData.frame_count || 0} frames</strong></p>
                      <p>• Output Quality: JPEG format</p>
                    </div>
                  </div>
                </div>

                {/* Frame Thumbnails Grid */}
                {frameList.length > 0 && (
                  <div style={{
                    background: 'var(--bg-subtle)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '18px'
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
                      <h4 style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px', margin: 0 }}>
                        <Film size={16} color="var(--primary-purple)" />
                        <span>Extracted Frame Previews ({displayedCount} of {totalFrames} frames)</span>
                      </h4>
                      {totalFrames > 12 && (
                        <button
                          type="button"
                          onClick={() => setShowAllFrames(!showAllFrames)}
                          style={{
                            background: showAllFrames ? 'var(--primary-purple)' : 'rgba(109, 40, 217, 0.08)',
                            color: showAllFrames ? '#ffffff' : 'var(--primary-purple)',
                            border: '1px solid var(--primary-purple)',
                            borderRadius: '6px',
                            padding: '4px 12px',
                            fontSize: '0.8rem',
                            fontWeight: 700,
                            cursor: 'pointer',
                            transition: 'all 0.2s ease',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px'
                          }}
                        >
                          {showAllFrames ? `Show Preview (12 Frames)` : `View All ${totalFrames} Frames`}
                        </button>
                      )}
                    </div>

                    <div className="frames-grid" style={{ maxHeight: showAllFrames ? '480px' : 'none', overflowY: showAllFrames ? 'auto' : 'visible', paddingRight: showAllFrames ? '6px' : '0' }}>
                      {frameList.map((src, idx) => (
                        <div
                          key={idx}
                          className="frame-thumb"
                          onClick={() => setSelectedFrameSrc(src)}
                          title={`Click to enlarge frame #${idx + 1}`}
                          style={{ cursor: 'pointer' }}
                        >
                          <img
                            src={src}
                            alt={`Frame ${idx + 1}`}
                            loading="lazy"
                            onError={(e) => { e.target.style.display = 'none'; }}
                          />
                          <span className="frame-badge">#{String(idx + 1).padStart(4, '0')}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Lightbox Modal for Enlarged Frame */}
                {selectedFrameSrc && (
                  <div
                    onClick={() => setSelectedFrameSrc(null)}
                    style={{
                      position: 'fixed',
                      top: 0,
                      left: 0,
                      right: 0,
                      bottom: 0,
                      backgroundColor: 'rgba(15, 23, 42, 0.88)',
                      backdropFilter: 'blur(4px)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      zIndex: 9999,
                      padding: '24px',
                      cursor: 'pointer'
                    }}
                  >
                    <div
                      onClick={(e) => e.stopPropagation()}
                      style={{
                        position: 'relative',
                        maxWidth: '92vw',
                        maxHeight: '88vh',
                        background: '#000000',
                        borderRadius: '12px',
                        overflow: 'hidden',
                        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7)',
                        border: '1px solid #334155'
                      }}
                    >
                      <button
                        type="button"
                        onClick={() => setSelectedFrameSrc(null)}
                        style={{
                          position: 'absolute',
                          top: '10px',
                          right: '10px',
                          background: 'rgba(15, 23, 42, 0.8)',
                          color: '#ffffff',
                          border: '1px solid rgba(255, 255, 255, 0.2)',
                          borderRadius: '50%',
                          width: '32px',
                          height: '32px',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: '18px',
                          cursor: 'pointer',
                          lineHeight: 1,
                          zIndex: 10
                        }}
                      >
                        ✕
                      </button>
                      <img
                        src={selectedFrameSrc}
                        alt="Enlarged preview"
                        style={{
                          display: 'block',
                          maxWidth: '90vw',
                          maxHeight: '82vh',
                          objectFit: 'contain'
                        }}
                      />
                    </div>
                  </div>
                )}

                {/* SESSION TIMELINE OVERVIEW */}
                {speechAnalysis && visualAnalysis && (
                  <div className="print-break-avoid">
                    <TimelineWithSeek
                      speechAnalysis={speechAnalysis}
                      visualAnalysis={visualAnalysis}
                      fusionReport={fusionReport}
                    />
                  </div>
                )}

                {/* SPEECH ANALYSIS DASHBOARD RESULTS */}
                {speechAnalysis && (
                  <div style={{
                    borderTop: '2px dashed #e2e8f0',
                    paddingTop: '28px',
                    marginTop: '8px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '20px'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                      <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Sparkles size={20} color="var(--primary-purple)" />
                        <span>Speech Analysis Insights</span>
                      </h3>
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                        {speechAnalysis.average_transcription_confidence !== undefined && speechAnalysis.average_transcription_confidence !== null && (
                          <span className="badge-pill" style={{ background: '#f0fdf4', color: '#166534', border: '1px solid #bbf7d0', fontSize: '0.75rem', fontWeight: 600 }}>
                            STT Conf: {(speechAnalysis.average_transcription_confidence * 100).toFixed(1)}%
                          </span>
                        )}
                        <span className="badge-purple-hero">Whisper Base STT</span>
                      </div>
                    </div>

                    {/* Transcript Card */}
                    <div style={{
                      background: '#ffffff',
                      border: '1px solid var(--border-subtle)',
                      borderRadius: 'var(--radius-lg)',
                      padding: '20px'
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px', flexWrap: 'wrap', gap: 6 }}>
                        <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <MessageSquare size={18} color="var(--primary-purple)" />
                          <span>Speech Transcript</span>
                        </h4>
                        <span className="badge-pill">
                          {speechAnalysis.wpm_data?.total_words || 0} Total Words
                        </span>
                      </div>

                      <InteractiveTranscript speechAnalysis={speechAnalysis} />
                    </div>

                    {/* Metrics Grid: Filler Words, WPM, Long Pauses, Repetitions */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                      {/* Filler Words Card */}
                      <div style={{
                        background: '#ffffff',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-lg)',
                        padding: '20px'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                          <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <AlertOctagon size={18} color="#d97706" />
                            <span>Filler Words</span>
                          </h4>
                          <span className="badge-pill" style={{ background: speechAnalysis.filler_word_count > 0 ? '#fffbebfb' : '#ecfdf5', color: speechAnalysis.filler_word_count > 0 ? '#b45309' : '#059669' }}>
                            {speechAnalysis.filler_word_count} Detected
                          </span>
                        </div>

                        {speechAnalysis.filler_words && speechAnalysis.filler_words.length > 0 ? (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', maxHeight: '140px', overflowY: 'auto' }}>
                            {speechAnalysis.filler_words.map((item, idx) => (
                              <Seekable key={idx} t={item.timestamp} style={{
                                background: '#fef3c7',
                                color: '#92400e',
                                border: '1px solid #fde68a',
                                padding: '4px 10px',
                                borderRadius: 'var(--radius-sm)',
                                fontSize: '0.78rem',
                                fontWeight: 600
                              }}>
                                "{item.word}" @ {item.timestamp}s
                              </Seekable>
                            ))}
                          </div>
                        ) : (
                          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                            No filler words ("um", "uh", "like", "you know") detected. Great fluency!
                          </p>
                        )}
                      </div>

                      {/* Speaking Speed WPM Card */}
                      <div style={{
                        background: '#ffffff',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-lg)',
                        padding: '20px'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                          <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Gauge size={18} color="var(--primary-purple)" />
                            <span>Speaking Speed (WPM)</span>
                          </h4>
                          <strong style={{ fontSize: '1.1rem', color: 'var(--primary-purple)' }}>
                            {speechAnalysis.wpm_data?.overall_wpm || 0} WPM
                          </strong>
                        </div>

                        <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '12px' }}>
                          <span>Speaking Duration: <strong>{speechAnalysis.wpm_data?.total_speaking_duration_seconds || 0}s</strong></span>
                        </div>

                        {/* Windowed WPM Timeline Bars */}
                        {speechAnalysis.wpm_data?.windowed_wpm && speechAnalysis.wpm_data.windowed_wpm.length > 0 && (
                          <div>
                            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', marginBottom: '6px', fontWeight: 700, textTransform: 'uppercase' }}>
                              Rolling 15s WPM Pacing
                            </span>
                            <div style={{ display: 'flex', gap: '6px', overflowX: 'auto', paddingBottom: '4px' }}>
                              {speechAnalysis.wpm_data.windowed_wpm.map((win, idx) => (
                                <div key={idx} style={{
                                  background: 'var(--bg-subtle)',
                                  border: '1px solid var(--border-subtle)',
                                  padding: '4px 8px',
                                  borderRadius: '6px',
                                  fontSize: '0.72rem',
                                  textAlign: 'center',
                                  flexShrink: 0
                                }}>
                                  <div style={{ fontWeight: 700, color: win.wpm >= 110 && win.wpm <= 160 ? '#059669' : (win.wpm > 0 ? '#d97706' : 'var(--text-muted)') }}>{win.wpm}</div>
                                  <div style={{ color: 'var(--text-muted)', fontSize: '0.65rem' }}>{win.window_start}s-{win.window_end}s</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Long Pauses Card */}
                      <div style={{
                        background: '#ffffff',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-lg)',
                        padding: '20px'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                          <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Clock size={18} color="#2563eb" />
                            <span>Long Pauses</span>
                          </h4>
                          <span className="badge-pill">
                            {speechAnalysis.long_pauses?.length || 0} Pauses
                          </span>
                        </div>

                        {speechAnalysis.long_pauses && speechAnalysis.long_pauses.length > 0 ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '140px', overflowY: 'auto' }}>
                            {speechAnalysis.long_pauses.map((pause, idx) => (
                              <Seekable key={idx} t={pause.start_time} as="div" style={{
                                background: '#eff6ff',
                                border: '1px solid #bfdbfe',
                                color: '#1e40af',
                                padding: '6px 12px',
                                borderRadius: 'var(--radius-sm)',
                                fontSize: '0.8rem',
                                display: 'flex',
                                justifyContent: 'space-between'
                              }}>
                                <span>Gap: {pause.start_time}s ➔ {pause.end_time}s</span>
                                <strong>{pause.duration}s pause</strong>
                              </Seekable>
                            ))}
                          </div>
                        ) : (
                          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                            No long pauses (≥ 3.0 seconds) detected. Good speech flow!
                          </p>
                        )}
                      </div>

                      {/* Repetitions Card */}
                      <div style={{
                        background: '#ffffff',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-lg)',
                        padding: '20px'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
                          <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Repeat size={18} color="#7c3aed" />
                            <span>Repetitions</span>
                          </h4>
                          <span className="badge-pill">
                            {speechAnalysis.repetitions?.length || 0} Detected
                          </span>
                        </div>

                        {speechAnalysis.repetitions && speechAnalysis.repetitions.length > 0 ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '140px', overflowY: 'auto' }}>
                            {speechAnalysis.repetitions.map((rep, idx) => (
                              <Seekable key={idx} t={rep.timestamp} as="div" style={{
                                background: '#f3e8ff',
                                border: '1px solid #e9d5ff',
                                color: '#6b21a8',
                                padding: '6px 12px',
                                borderRadius: 'var(--radius-sm)',
                                fontSize: '0.8rem',
                                display: 'flex',
                                justifyContent: 'space-between'
                              }}>
                                <span>"{rep.phrase}"</span>
                                <span>@{rep.timestamp}s ({rep.count}x)</span>
                              </Seekable>
                            ))}
                          </div>
                        ) : (
                          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                            No word or phrase repetitions detected.
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                )}

                {/* VISUAL ANALYSIS DASHBOARD RESULTS */}
                {visualAnalysis && (
                  <div style={{
                    borderTop: '2px dashed #e2e8f0',
                    paddingTop: '28px',
                    marginTop: '8px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '20px'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <ImageIcon size={20} color="#0369a1" />
                        <span>Visual Analysis Insights</span>
                      </h3>
                      <span className="badge-pill" style={{ background: '#e0f2fe', color: '#0369a1', border: '1px solid #bae6fd' }}>
                        MediaPipe 5FPS Eye & 1FPS Body
                      </span>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                      {/* Eye Contact Card */}
                      <div style={{ background: '#ffffff', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', padding: '20px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                          <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)' }}>Eye Contact Rate</h4>
                          <strong style={{ fontSize: '1.1rem', color: '#0369a1' }}>
                            {visualAnalysis.eye_contact?.eye_contact_percentage}%
                          </strong>
                        </div>
                        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between', margin: 0 }}>
                          <span>Looking Away Events: <strong>{visualAnalysis.eye_contact?.looking_away_count}</strong></span>
                          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                            Conf: {visualAnalysis.eye_contact?.average_detection_confidence != null
                              ? `${(visualAnalysis.eye_contact.average_detection_confidence * 100).toFixed(0)}%`
                              : 'N/A'}
                          </span>
                        </p>
                        <MetricBar value={visualAnalysis.eye_contact?.eye_contact_percentage} color="#0369a1" />
                      </div>

                      {/* Posture Card */}
                      <div style={{ background: '#ffffff', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', padding: '20px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                          <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)' }}>Posture Score</h4>
                          <strong style={{ fontSize: '1.1rem', color: '#059669' }}>
                            {visualAnalysis.posture?.posture_score}%
                          </strong>
                        </div>
                        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between', margin: 0 }}>
                          <span>Good Posture: <strong>{visualAnalysis.posture?.good_posture_count} / {visualAnalysis.posture?.total_frames_analyzed} frames</strong></span>
                          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                            Conf: {visualAnalysis.posture?.average_detection_confidence != null
                              ? `${(visualAnalysis.posture.average_detection_confidence * 100).toFixed(0)}%`
                              : 'N/A'}
                          </span>
                        </p>
                        <MetricBar value={visualAnalysis.posture?.posture_score} color="#059669" />
                      </div>

                      {/* Gesture Usage Card */}
                      <div style={{ background: '#ffffff', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', padding: '20px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                          <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)' }}>Hand Gestures</h4>
                          <span className="badge-pill" style={{ textTransform: 'capitalize' }}>
                            {visualAnalysis.gesture?.gesture_usage_classification?.replace('_', ' ')}
                          </span>
                        </div>
                        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'flex', justifyContent: 'space-between', margin: 0 }}>
                          <span>Active Hand: <strong>{visualAnalysis.gesture?.active_hand_percentage}%</strong></span>
                          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
                            Conf: {visualAnalysis.gesture?.average_detection_confidence != null
                              ? `${(visualAnalysis.gesture.average_detection_confidence * 100).toFixed(0)}%`
                              : 'N/A'}
                          </span>
                        </p>
                        <MetricBar
                          value={visualAnalysis.gesture?.active_hand_percentage}
                          color={visualAnalysis.gesture?.gesture_usage_classification === 'average' ? '#059669' : '#f59e0b'}
                        />
                      </div>

                      {/* Head Movement Card */}
                      <div style={{ background: '#ffffff', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', padding: '20px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                          <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)' }}>Head Movement</h4>
                          <strong style={{ fontSize: '1.1rem', color: '#7c3aed' }}>
                            {visualAnalysis.head_movement?.head_movement_score}%
                          </strong>
                        </div>
                        <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                          Rapid Movement Triggers: <strong>{visualAnalysis.head_movement?.excessive_movement_count}</strong>
                        </p>
                        <MetricBar value={visualAnalysis.head_movement?.head_movement_score} color="#7c3aed" />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        </ReportVideoProvider>
      </div>
    </div>
  );
}
