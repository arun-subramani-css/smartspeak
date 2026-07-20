import React, { useEffect, useState } from 'react';
import { 
  RefreshCw, CheckCircle2, Clock, AlertTriangle, Music, Image as ImageIcon, 
  Copy, Check, FileVideo, ArrowLeft, Volume2, ShieldCheck, Film 
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
            <CheckCircle2 size={12} /> Pipeline Complete
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

  return (
    <div className="pro-card">
      <div className="pro-card-header">
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)' }}>
            Processing Status & Metrics
          </h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '2px' }}>
            Real-time pipeline monitoring & extracted artifact preview
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
                  <span>Processing video frames & audio...</span>
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
                  Reason: {statusData.error_reason || 'Unknown decoding error.'}
                </p>
                <button onClick={onReset} className="btn-light" style={{ background: '#ffffff', borderColor: '#fca5a5' }}>
                  <span>Try Uploading Again</span>
                </button>
              </div>
            )}

            {/* Processed Cards */}
            {statusData.status === 'processed' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
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
                      <p>• Total Frames Extracted: <strong style={{ color: 'var(--primary-purple)' }}>{statusData.frame_count} frames</strong></p>
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
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
