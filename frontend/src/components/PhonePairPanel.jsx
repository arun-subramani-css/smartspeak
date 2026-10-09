import React, { useCallback, useEffect, useRef, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, Smartphone, X } from 'lucide-react';
import { apiFetch, APIError } from '../api/client';

/**
 * PhonePairPanel — laptop side of the "Use phone camera" flow (Step 2).
 *
 * Creates a single-use pairing token, renders the phone URL as a QR code
 * (with the URL also shown as text), polls status every ~1.5s, and hands
 * the session_id back through onSessionReady so the existing report flow
 * takes over. Cancel and Regenerate are always available.
 *
 * The QR prefers window.location.origin when the app itself was opened
 * over the LAN (self-corrects a wrong interface guess by the backend);
 * otherwise it uses the backend-computed phone_url. When neither exists —
 * a localhost-only machine — no QR is drawn at all: a warning explains
 * what to do instead (localhost must never be encoded).
 *
 * The token is deliberately NOT deleted on unmount: React StrictMode
 * double-invokes effects in dev, and an abandoned token is already
 * bounded by its 10-minute TTL (swept server-side). Explicit Cancel and
 * Regenerate both DELETE the token.
 */

const DEFAULT_POLL_MS = 1500;

function isLoopbackOrigin(origin) {
  try {
    const host = new URL(origin).hostname;
    return host === 'localhost' || host === '127.0.0.1' || host === '[::1]';
  } catch {
    return true;
  }
}

const cardStyle = {
  background: 'var(--bg-subtle)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 'var(--radius-lg)',
  padding: '28px 24px',
  textAlign: 'center',
};

export function PhonePairPanel({ onSessionReady, onCancel, pollIntervalMs = DEFAULT_POLL_MS }) {
  const [pair, setPair] = useState(null); // { token, phone_url, expires_in, status }
  const [phase, setPhase] = useState('creating');
  // phases: creating | waiting | uploading | uploaded | expired | invalid | no-lan | error
  const [errorMsg, setErrorMsg] = useState('');
  const createdRef = useRef(false);
  const inFlightRef = useRef(false);
  const pollRef = useRef(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const createPair = useCallback(async () => {
    stopPolling();
    setPair(null);
    setErrorMsg('');
    setPhase('creating');
    try {
      const data = await apiFetch('/api/v1/pairing', { method: 'POST' });
      setPair(data);
      const originReachable = !isLoopbackOrigin(window.location.origin);
      setPhase(data.phone_url || originReachable ? 'waiting' : 'no-lan');
    } catch (err) {
      setErrorMsg(err?.message || 'Could not reach the SmartSpeak server.');
      setPhase('error');
    }
  }, [stopPolling]);

  // Create exactly once per mount (ref guard: StrictMode's second effect
  // invocation must not mint an orphan token).
  useEffect(() => {
    if (createdRef.current) return undefined;
    createdRef.current = true;
    createPair();
    return stopPolling;
  }, [createPair, stopPolling]);

  // Status polling while the phone is expected to act.
  useEffect(() => {
    if (!pair || (phase !== 'waiting' && phase !== 'uploading')) return undefined;

    const tick = async () => {
      if (inFlightRef.current) return;
      inFlightRef.current = true;
      try {
        const res = await apiFetch(`/api/v1/pairing/${pair.token}`);
        if (res.status === 'uploaded' && res.session_id) {
          stopPolling();
          setPhase('uploaded');
          onSessionReady(res.session_id);
        } else if (res.status === 'uploading') {
          setPhase((p) => (p === 'waiting' ? 'uploading' : p));
        } else {
          setPhase((p) => (p === 'uploading' ? 'waiting' : p));
        }
      } catch (err) {
        if (err instanceof APIError && err.status === 404) {
          stopPolling();
          setPhase('invalid');
        } else if (err instanceof APIError && err.status === 410) {
          stopPolling();
          setPhase('expired');
        } else if (err instanceof APIError && err.status !== 0) {
          stopPolling();
          setErrorMsg(err.message);
          setPhase('error');
        }
        // Timeout (status 0) and network failures are transient — keep polling.
      } finally {
        inFlightRef.current = false;
      }
    };

    pollRef.current = setInterval(tick, pollIntervalMs);
    return stopPolling;
  }, [pair, phase, pollIntervalMs, onSessionReady, stopPolling]);

  const handleCancel = async () => {
    stopPolling();
    if (pair) {
      try {
        await apiFetch(`/api/v1/pairing/${pair.token}`, { method: 'DELETE' });
      } catch { /* idempotent — the code is dead either way */ }
    }
    if (onCancel) onCancel();
  };

  const handleRegenerate = async () => {
    stopPolling();
    if (pair) {
      try {
        await apiFetch(`/api/v1/pairing/${pair.token}`, { method: 'DELETE' });
      } catch { /* old code may already be gone */ }
    }
    await createPair();
  };

  const originReachable = pair && !isLoopbackOrigin(window.location.origin);
  const effectiveUrl = pair && (originReachable
    ? `${window.location.origin}/pair/${pair.token}`
    : pair.phone_url);

  const cancelButton = (
    <button type="button" className="btn-light" onClick={handleCancel}>
      <X size={15} />
      <span>Cancel</span>
    </button>
  );

  return (
    <div role="region" aria-label="Pair your phone camera" style={cardStyle}>
      <div style={{
        width: 56, height: 56, borderRadius: '50%', background: 'var(--primary-purple-light)',
        color: 'var(--primary-purple)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        margin: '0 auto 14px',
      }}>
        <Smartphone size={26} />
      </div>

      <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: 6 }}>
        Practice with your phone
      </h3>

      {phase === 'creating' && (
        <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', display: 'flex', gap: 8, justifyContent: 'center', alignItems: 'center' }}>
          <Loader2 size={16} className="animate-spin" /> Generating QR code…
        </p>
      )}

      {phase === 'error' && (
        <>
          <p style={{ fontSize: '0.88rem', color: '#dc2626', maxWidth: 460, margin: '0 auto 16px' }}>
            {errorMsg}
          </p>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
            <button type="button" className="btn-purple" onClick={createPair}>
              <RefreshCw size={15} />
              <span>Try again</span>
            </button>
            {cancelButton}
          </div>
        </>
      )}

      {phase === 'no-lan' && (
        <>
          <AlertTriangle size={30} color="#d97706" style={{ marginBottom: 10 }} />
          <h4 style={{ fontSize: '0.98rem', fontWeight: 700, marginBottom: 6 }}>
            This computer isn't reachable from your phone
          </h4>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', maxWidth: 480, margin: '0 auto 8px' }}>
            No LAN address was found, so a QR code would lead nowhere. Connect this
            computer to Wi-Fi (or start a phone hotspot), and make sure the dev
            server runs with <code>vite --host</code>.
          </p>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', maxWidth: 480, margin: '0 auto 16px' }}>
            On the same network, restart the dev server and open this page via the
            Network URL Vite prints (e.g. http://192.168.x.x:5173).
          </p>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
            <button type="button" className="btn-purple" onClick={createPair}>
              <RefreshCw size={15} />
              <span>Try again</span>
            </button>
            {cancelButton}
          </div>
        </>
      )}

      {(phase === 'expired' || phase === 'invalid') && (
        <>
          <AlertTriangle size={30} color="#d97706" style={{ marginBottom: 10 }} />
          <h4 style={{ fontSize: '0.98rem', fontWeight: 700, marginBottom: 6 }}>
            {phase === 'expired' ? 'This pairing code expired' : 'This pairing code is no longer valid'}
          </h4>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', maxWidth: 460, margin: '0 auto 16px' }}>
            {phase === 'expired'
              ? 'Pairing codes last 10 minutes. Generate a fresh one and scan it again.'
              : 'The code was cancelled or already used. Generate a fresh one and scan it again.'}
          </p>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
            <button type="button" className="btn-purple" onClick={handleRegenerate}>
              <RefreshCw size={15} />
              <span>New QR code</span>
            </button>
            {cancelButton}
          </div>
        </>
      )}

      {(phase === 'waiting' || phase === 'uploading' || phase === 'uploaded') && effectiveUrl && (
        <>
          <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', maxWidth: 460, margin: '0 auto 14px' }}>
            Scan with your phone's camera to record there — the take flows into this
            machine's normal analysis pipeline.
          </p>

          <div style={{
            display: 'inline-block', background: '#ffffff', padding: 14,
            borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)',
            lineHeight: 0,
          }}>
            <QRCodeSVG value={effectiveUrl} size={176} level="M" bgColor="#ffffff" fgColor="#0f172a" />
          </div>

          <p style={{
            fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--text-muted)',
            wordBreak: 'break-all', maxWidth: 460, margin: '10px auto 14px',
            userSelect: 'all',
          }}>
            {effectiveUrl}
          </p>

          <p
            aria-live="polite"
            style={{
              fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-primary)',
              display: 'flex', gap: 8, justifyContent: 'center', alignItems: 'center',
              minHeight: 24, marginBottom: 16,
            }}
          >
            {phase === 'waiting' && (
              <>
                <span className="animate-pulse-soft" style={{ width: 9, height: 9, borderRadius: '50%', background: '#f59e0b', display: 'inline-block' }} />
                Waiting for your phone…
              </>
            )}
            {phase === 'uploading' && (
              <>
                <Loader2 size={16} className="animate-spin" color="var(--primary-purple)" />
                Uploading from your phone…
              </>
            )}
            {phase === 'uploaded' && (
              <>
                <CheckCircle2 size={16} color="#10b981" />
                Upload received — opening your report…
              </>
            )}
          </p>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
            <button type="button" className="btn-light" onClick={handleRegenerate}>
              <RefreshCw size={15} />
              <span>Regenerate QR</span>
            </button>
            {cancelButton}
          </div>
        </>
      )}
    </div>
  );
}

export default PhonePairPanel;
