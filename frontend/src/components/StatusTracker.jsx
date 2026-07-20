import React, { useEffect, useState } from 'react';
import { RefreshCw, CheckCircle2, Clock, AlertTriangle, Music, Image as ImageIcon, Copy, Check } from 'lucide-react';

export function StatusTracker({ sessionId, onReset }) {
  const [statusData, setStatusData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  const fetchStatus = async () => {
    try {
      const res = await fetch(`/api/v1/sessions/${sessionId}/status`);
      if (!res.ok) {
        throw new Error(`Failed to fetch status (HTTP ${res.status})`);
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
        return <span className="badge badge-uploaded">Uploaded</span>;
      case 'processing':
        return <span className="badge badge-processing"><RefreshCw size={12} className="spin" /> Processing</span>;
      case 'processed':
        return <span className="badge badge-processed"><CheckCircle2 size={12} /> Processed</span>;
      case 'failed':
        return <span className="badge badge-failed"><AlertTriangle size={12} /> Failed</span>;
      default:
        return <span className="badge">{status}</span>;
    }
  };

  return (
    <div className="glass-card" style={{ padding: '28px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '4px' }}>
            Processing Status & Metrics
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            Real-time tracking of audio extraction and frame sampling
          </p>
        </div>
        <button
          onClick={onReset}
          style={{
            background: 'rgba(255, 255, 255, 0.05)',
            border: '1px solid var(--border-color)',
            color: 'var(--text-main)',
            padding: '8px 14px',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
            fontSize: '0.85rem'
          }}
        >
          Upload Another Video
        </button>
      </div>

      {/* Session ID Banner */}
      <div style={{
        background: 'rgba(15, 23, 42, 0.6)',
        border: '1px solid var(--border-color)',
        borderRadius: 'var(--radius-md)',
        padding: '16px',
        marginBottom: '24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}>
        <div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Session ID (UUID)
          </span>
          <p style={{ fontFamily: 'monospace', fontSize: '1rem', fontWeight: 600, color: 'var(--accent-cyan)', marginTop: '2px' }}>
            {sessionId}
          </p>
        </div>
        <button
          onClick={copySessionId}
          style={{
            background: 'rgba(99, 102, 241, 0.15)',
            border: '1px solid rgba(99, 102, 241, 0.3)',
            color: 'var(--primary)',
            padding: '8px 12px',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '0.85rem'
          }}
        >
          {copied ? <Check size={16} /> : <Copy size={16} />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>

      {/* Loading State */}
      {loading && !statusData && (
        <div style={{ textAlign: 'center', padding: '30px 0', color: 'var(--text-muted)' }}>
          <RefreshCw size={32} className="spin" style={{ color: 'var(--primary)', marginBottom: '10px' }} />
          <p>Fetching session status...</p>
        </div>
      )}

      {/* Status Details */}
      {statusData && (
        <div>
          {/* Status Stepper */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '16px',
            background: 'rgba(15, 23, 42, 0.4)',
            borderRadius: 'var(--radius-md)',
            marginBottom: '20px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>Current Status:</span>
              {getStatusBadge(statusData.status)}
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Clock size={14} />
              <span>Uploaded: {new Date(statusData.upload_timestamp).toLocaleTimeString()}</span>
            </div>
          </div>

          {/* Failed Alert */}
          {statusData.status === 'failed' && (
            <div style={{
              padding: '16px',
              background: 'var(--danger-bg)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--danger)',
              marginBottom: '20px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, marginBottom: '6px' }}>
                <AlertTriangle size={20} />
                <span>Processing Failed</span>
              </div>
              <p style={{ fontSize: '0.9rem', color: '#fca5a5' }}>
                Reason: {statusData.error_reason || 'Unknown video decoding or processing error.'}
              </p>
            </div>
          )}

          {/* Processed Metrics Cards */}
          {statusData.status === 'processed' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginTop: '16px' }}>
              {/* Audio Card */}
              <div style={{
                background: 'rgba(15, 23, 42, 0.6)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                padding: '20px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                  <div style={{ background: 'rgba(16, 185, 129, 0.15)', padding: '8px', borderRadius: '8px', color: 'var(--success)' }}>
                    <Music size={20} />
                  </div>
                  <div>
                    <h4 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Audio Track Extracted</h4>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Whisper format compliant</p>
                  </div>
                </div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  <p>• File: <code style={{ color: 'var(--text-main)' }}>audio.wav</code></p>
                  <p>• Format: 16kHz Mono WAV</p>
                  <p>• Path: <span style={{ color: 'var(--accent-cyan)' }}>{statusData.audio_path}</span></p>
                </div>
              </div>

              {/* Frames Card */}
              <div style={{
                background: 'rgba(15, 23, 42, 0.6)',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                padding: '20px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
                  <div style={{ background: 'rgba(168, 85, 247, 0.15)', padding: '8px', borderRadius: '8px', color: 'var(--accent-purple)' }}>
                    <ImageIcon size={20} />
                  </div>
                  <div>
                    <h4 style={{ fontSize: '0.95rem', fontWeight: 600 }}>Video Frames Extracted</h4>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Eye-contact / Posture sampling</p>
                  </div>
                </div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                  <p>• Total Extracted: <strong style={{ color: 'var(--accent-purple)' }}>{statusData.frame_count} frames</strong></p>
                  <p>• Sample Rate: 1 frame/sec</p>
                  <p>• Pattern: <code style={{ color: 'var(--text-main)' }}>frame_0001.jpg</code> ...</p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
