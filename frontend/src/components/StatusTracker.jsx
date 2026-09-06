import React, { useEffect, useState } from 'react';
import {
  RefreshCw, CheckCircle2, Clock, AlertTriangle, Music, Image as ImageIcon,
  Copy, Check, ArrowLeft, Film, MessageSquare, Gauge, AlertOctagon, Repeat, Sparkles, Volume2
} from 'lucide-react';

export function StatusTracker({ sessionId, onReset }) {
  const [statusData, setStatusData] = useState(null);
  const [speechAnalysis, setSpeechAnalysis] = useState(null);
  const [visualAnalysis, setVisualAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  const fetchStatus = async () => {
    try {
      const res = await fetch(`/api/v1/sessions/${sessionId}/status`);
      if (!res.ok) {
        throw new Error(`Session status request failed (HTTP ${res.status})`);
      }
      const data = await res.json();
      setStatusData(data);
      setError(null);

      if (data.status === 'speech_analysis_complete' || data.status === 'visual_analysis_complete' || data.status === 'ready_for_fusion' || data.has_speech_analysis || data.has_visual_analysis) {
        fetchSpeechAnalysis();
        fetchVisualAnalysis();
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

  useEffect(() => {
    if (!sessionId) return;

    fetchStatus();
    const interval = setInterval(() => {
      if (statusData && (statusData.status === 'ready_for_fusion' || statusData.status === 'failed')) {
        clearInterval(interval);
        return;
      }
      fetchStatus();
    }, 2000);

    return () => clearInterval(interval);
  }, [sessionId, statusData?.status]);

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

  const frameList = statusData?.frame_count
    ? Array.from({ length: Math.min(statusData.frame_count, 12) }, (_, i) => {
      const frameNum = String(i + 1).padStart(4, '0');
      return `/data/processed/${sessionId}/frames/frame_${frameNum}.jpg`;
    })
    : [];

  const isProcessedOrAnalyzed = statusData?.status === 'processed' || statusData?.status === 'speech_analysis_complete' || statusData?.status === 'visual_analysis_complete' || statusData?.status === 'ready_for_fusion' || statusData?.has_speech_analysis || statusData?.has_visual_analysis;

  return (
    <div className="pro-card">
      <div className="pro-card-header">
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)' }}>
            Processing Status & Metrics
          </h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '2px' }}>
            Real-time pipeline monitoring & speech analysis report
          </p>
        </div>

        <button onClick={onReset} className="btn-light">
          <ArrowLeft size={16} />
          <span>Upload Another Video</span>
        </button>
      </div>

      <div className="pro-card-body">
        {/* Session Metadata Banner */}
        <div style={{
          background: 'var(--bg-subtle)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: '18px 20px',
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

        {/* Loading Spinner */}
        {loading && !statusData && (
          <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-muted)' }}>
            <RefreshCw size={32} className="animate-spin" style={{ color: 'var(--primary-purple)', marginBottom: '8px' }} />
            <p style={{ fontWeight: 500 }}>Fetching status telemetry...</p>
          </div>
        )}

        {statusData && (
          <div>
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

              {statusData.status === 'processing' && (
                <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <RefreshCw size={14} className="animate-spin" color="var(--primary-purple)" />
                  <span>Processing audio extraction & Whisper STT speech analysis...</span>
                </div>
              )}
            </div>

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

            {/* Processed Audio & Frame Cards */}
            {isProcessedOrAnalyzed && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
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
                    <h4 style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <Film size={16} color="var(--primary-purple)" />
                      <span>Extracted Frame Previews</span>
                    </h4>

                    <div className="frames-grid">
                      {frameList.map((src, idx) => (
                        <div key={idx} className="frame-thumb">
                          <img
                            src={src}
                            alt={`Frame ${idx + 1}`}
                            onError={(e) => { e.target.style.display = 'none'; }}
                          />
                          <span className="frame-badge">#{String(idx + 1).padStart(4, '0')}</span>
                        </div>
                      ))}
                    </div>
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
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <Sparkles size={20} color="var(--primary-purple)" />
                        <span>Speech Analysis Insights</span>
                      </h3>
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
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
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                        <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                          <MessageSquare size={18} color="var(--primary-purple)" />
                          <span>Speech Transcript</span>
                        </h4>
                        <span className="badge-pill">
                          {speechAnalysis.wpm_data?.total_words || 0} Total Words
                        </span>
                      </div>

                      <div style={{
                        background: 'var(--bg-subtle)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-md)',
                        padding: '16px',
                        fontSize: '0.92rem',
                        lineHeight: 1.6,
                        color: 'var(--text-primary)',
                        maxHeight: '180px',
                        overflowY: 'auto'
                      }}>
                        {speechAnalysis.transcript_text ? (
                          <p>"{speechAnalysis.transcript_text}"</p>
                        ) : (
                          <em style={{ color: 'var(--text-muted)' }}>No spoken words detected in audio.</em>
                        )}
                      </div>
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
                              <span key={idx} style={{
                                background: '#fef3c7',
                                color: '#92400e',
                                border: '1px solid #fde68a',
                                padding: '4px 10px',
                                borderRadius: 'var(--radius-sm)',
                                fontSize: '0.78rem',
                                fontWeight: 600
                              }}>
                                "{item.word}" @ {item.timestamp}s
                              </span>
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
                                  <div style={{ fontWeight: 700, color: 'var(--primary-purple)' }}>{win.wpm}</div>
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
                            <span>Long Pauses </span>
                          </h4>
                          <span className="badge-pill">
                            {speechAnalysis.long_pauses?.length || 0} Pauses
                          </span>
                        </div>

                        {speechAnalysis.long_pauses && speechAnalysis.long_pauses.length > 0 ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '140px', overflowY: 'auto' }}>
                            {speechAnalysis.long_pauses.map((pause, idx) => (
                              <div key={idx} style={{
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
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                            No long pauses ($\ge 3.0$ seconds) detected. Good speech flow!
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
                              <div key={idx} style={{
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
                              </div>
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
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
