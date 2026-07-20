import React, { useEffect, useState } from 'react';
import { 
  RefreshCw, CheckCircle2, Clock, AlertTriangle, Music, Image as ImageIcon, 
  Copy, Check, FileVideo, Layers, ArrowLeft, Volume2, ShieldCheck, Play 
} from 'lucide-react';

export function StatusTracker({ sessionId, onReset }) {
  const [statusData, setStatusData] = useState(null);
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
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!sessionId) return;

    fetchStatus();
    // Poll every 2 seconds if status is uploaded or processing
    const interval = setInterval(() => {
      if (statusData && (statusData.status === 'processed' || statusData.status === 'failed')) {
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
        return <span className="status-pill status-uploaded">Staged & Queued</span>;
      case 'processing':
        return (
          <span className="status-pill status-processing">
            <RefreshCw size={12} className="animate-spin" /> Processing Pipeline
          </span>
        );
      case 'processed':
        return (
          <span className="status-pill status-processed">
            <CheckCircle2 size={12} /> Pipeline Complete
          </span>
        );
      case 'failed':
        return (
          <span className="status-pill status-failed">
            <AlertTriangle size={12} /> Processing Failed
          </span>
        );
      default:
        return <span className="status-pill">{status}</span>;
    }
  };

  // Generate frame list preview array for processed session
  const frameList = statusData?.frame_count
    ? Array.from({ length: Math.min(statusData.frame_count, 12) }, (_, i) => {
        const frameNum = String(i + 1).padStart(4, '0');
        return `/data/processed/${sessionId}/frames/frame_${frameNum}.jpg`;
      })
    : [];

  return (
    <div className="pro-card">
      {/* Header */}
      <div className="pro-card-header">
        <div>
          <h2 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#ffffff' }}>
            Preprocessing Status & Multimodal Metrics
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
            Real-time pipeline monitoring for audio track extraction and posture frame sampling
          </p>
        </div>

        <button
          onClick={onReset}
          className="btn-secondary"
          style={{ padding: '8px 14px', fontSize: '0.82rem' }}
        >
          <ArrowLeft size={16} />
          <span>Upload Another Video</span>
        </button>
      </div>

      <div className="pro-card-body">
        {/* Session Metadata Banner */}
        <div style={{
          background: 'var(--bg-surface-elevated)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          padding: '20px',
          marginBottom: '28px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '16px'
        }}>
          <div>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700 }}>
              Session Identifier (UUID)
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '4px' }}>
              <code style={{ fontFamily: 'var(--font-mono)', fontSize: '1rem', fontWeight: 600, color: 'var(--primary-400)' }}>
                {sessionId}
              </code>
              <button
                onClick={copySessionId}
                style={{
                  background: 'rgba(99, 102, 241, 0.12)',
                  border: '1px solid rgba(99, 102, 241, 0.25)',
                  color: 'var(--primary-400)',
                  padding: '4px 10px',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '0.75rem',
                  fontWeight: 600
                }}
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                <span>{copied ? 'Copied' : 'Copy UUID'}</span>
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '24px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            <div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', display: 'block', textTransform: 'uppercase', fontWeight: 700 }}>
                Original File
              </span>
              <strong style={{ color: 'var(--text-primary)' }}>{statusData?.original_filename || '...'}</strong>
            </div>

            <div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', display: 'block', textTransform: 'uppercase', fontWeight: 700 }}>
                File Size
              </span>
              <strong style={{ color: 'var(--text-primary)' }}>
                {statusData?.file_size ? `${(statusData.file_size / (1024 * 1024)).toFixed(2)} MB` : '...'}
              </strong>
            </div>

            <div>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', display: 'block', textTransform: 'uppercase', fontWeight: 700 }}>
                Upload Timestamp
              </span>
              <span style={{ color: 'var(--text-secondary)' }}>
                {statusData?.upload_timestamp ? new Date(statusData.upload_timestamp).toLocaleTimeString() : '...'}
              </span>
            </div>
          </div>
        </div>

        {/* Loading Spinner */}
        {loading && !statusData && (
          <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-secondary)' }}>
            <RefreshCw size={36} className="animate-spin" style={{ color: 'var(--primary-400)', marginBottom: '12px' }} />
            <p style={{ fontWeight: 500 }}>Connecting to session telemetry...</p>
          </div>
        )}

        {statusData && (
          <div>
            {/* Stepper Timeline */}
            <div className="stepper-container">
              <div className={`step-item ${statusData.status !== 'failed' ? 'completed' : 'active'}`}>
                <div className="step-icon">
                  <CheckCircle2 size={18} />
                </div>
                <span className="step-label">1. Video Uploaded</span>
              </div>

              <div className={`step-item ${statusData.status === 'processing' ? 'active' : statusData.status === 'processed' ? 'completed' : ''}`}>
                <div className="step-icon">
                  <RefreshCw size={18} className={statusData.status === 'processing' ? 'animate-spin' : ''} />
                </div>
                <span className="step-label">2. FFmpeg & OpenCV Processing</span>
              </div>

              <div className={`step-item ${statusData.status === 'processed' ? 'completed' : ''}`}>
                <div className="step-icon">
                  <ShieldCheck size={18} />
                </div>
                <span className="step-label">3. Ready for Analysis</span>
              </div>
            </div>

            {/* Current Status Pill Bar */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '16px 20px',
              background: 'rgba(15, 23, 42, 0.4)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              marginBottom: '24px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Status:</span>
                {getStatusBadge(statusData.status)}
              </div>

              {statusData.status === 'processing' && (
                <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <RefreshCw size={14} className="animate-spin" color="var(--primary-400)" />
                  <span>Polling status every 2 seconds...</span>
                </div>
              )}
            </div>

            {/* Failed Error Diagnostic */}
            {statusData.status === 'failed' && (
              <div style={{
                padding: '20px',
                background: 'var(--status-danger-bg)',
                border: '1px solid var(--status-danger-border)',
                borderRadius: 'var(--radius-lg)',
                color: 'var(--status-danger)',
                marginBottom: '24px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', fontWeight: 700, fontSize: '1rem', marginBottom: '8px' }}>
                  <AlertTriangle size={22} />
                  <span>Pipeline Execution Failed</span>
                </div>
                <p style={{ fontSize: '0.88rem', color: '#fca5a5', lineHeight: 1.5, marginBottom: '14px' }}>
                  Reason: {statusData.error_reason || 'Video container or stream decoding error encountered during processing.'}
                </p>
                <button
                  onClick={onReset}
                  className="btn-secondary"
                  style={{ background: 'rgba(239, 68, 68, 0.15)', color: '#ffffff', borderColor: 'rgba(239, 68, 68, 0.3)' }}
                >
                  <span>Re-upload Video</span>
                </button>
              </div>
            )}

            {/* Processed Artifacts Dashboard */}
            {statusData.status === 'processed' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                {/* Metrics Cards Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                  {/* Audio Card */}
                  <div style={{
                    background: 'var(--bg-surface-elevated)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '24px'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ background: 'rgba(16, 185, 129, 0.15)', padding: '10px', borderRadius: '10px', color: 'var(--accent-emerald)' }}>
                          <Music size={22} />
                        </div>
                        <div>
                          <h4 style={{ fontSize: '1rem', fontWeight: 600, color: '#ffffff' }}>Extracted Audio Track</h4>
                          <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Whisper Compliant • 16kHz Mono</p>
                        </div>
                      </div>
                      <span className="status-pill status-processed" style={{ fontSize: '0.7rem' }}>WAV PCM</span>
                    </div>

                    <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '16px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>Format:</span>
                        <strong style={{ color: 'var(--text-primary)' }}>PCM 16-bit Mono (16,000 Hz)</strong>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>Target Consumer:</span>
                        <strong style={{ color: 'var(--accent-emerald)' }}>Speech-to-Text / Whisper</strong>
                      </div>
                    </div>

                    {/* Audio Preview Element */}
                    <div style={{ background: 'rgba(0, 0, 0, 0.3)', padding: '10px', borderRadius: 'var(--radius-md)' }}>
                      <audio controls style={{ width: '100%', height: '36px' }} src={`/data/${statusData.audio_path}`} />
                    </div>
                  </div>

                  {/* Video Frames Card */}
                  <div style={{
                    background: 'var(--bg-surface-elevated)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '24px'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ background: 'rgba(139, 92, 246, 0.15)', padding: '10px', borderRadius: '10px', color: 'var(--accent-violet)' }}>
                          <ImageIcon size={22} />
                        </div>
                        <div>
                          <h4 style={{ fontSize: '1rem', fontWeight: 600, color: '#ffffff' }}>Extracted Video Frames</h4>
                          <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>OpenCV Sampling • 1 FPS</p>
                        </div>
                      </div>
                      <span className="status-pill" style={{ background: 'rgba(139, 92, 246, 0.15)', color: 'var(--accent-violet)', border: '1px solid rgba(139, 92, 246, 0.3)', fontSize: '0.7rem' }}>
                        {statusData.frame_count} Frames Saved
                      </span>
                    </div>

                    <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>Sampling Rate:</span>
                        <strong style={{ color: 'var(--text-primary)' }}>1 frame / second</strong>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span>Downstream Module:</span>
                        <strong style={{ color: 'var(--accent-violet)' }}>Eye Contact & Posture Sampling</strong>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Frame Image Gallery */}
                {frameList.length > 0 && (
                  <div style={{
                    background: 'var(--bg-surface-elevated)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-lg)',
                    padding: '20px'
                  }}>
                    <h4 style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Film size={16} color="var(--primary-400)" />
                      <span>Extracted Frame Previews (First {frameList.length} Frames)</span>
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
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
