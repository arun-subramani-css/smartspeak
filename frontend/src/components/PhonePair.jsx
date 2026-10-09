import React, { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Camera, CheckCircle2, Image, Loader2, RefreshCw, Square, Smartphone, Upload } from 'lucide-react';
import { apiFetch, APIError } from '../api/client';

/**
 * PhonePair — Step 3, the phone side of the QR flow. Minimal mobile-first
 * page (no nav, no dashboard) rendered at /pair/<token>.
 *
 * Progressive enhancement:
 *  - Secure context + MediaRecorder → in-page recorder (front camera,
 *    720p constraints); the take is confirmed on a review screen before
 *    it is uploaded so a mis-tap doesn't burn analysis time.
 *  - Otherwise (plain-HTTP LAN is not a secure context — exactly what
 *    window.isSecureContext reports — or no camera permission): a large
 *    <input capture> button that opens the OS camera app. That needs no
 *    browser permission at all.
 *
 * Shows upload progress, success, retry-on-failure, and clear messages
 * for expired/invalid pairing codes. The video stays on the local network:
 * the upload target is a relative URL (same origin as this page).
 */

const MAX_SIZE_MB = 500;
const ALLOWED_EXTENSIONS = ['.mp4', '.avi', '.mov', '.webm'];

/** Best container the browser can actually record (mirrors PracticeRecorder). */
function pickMimeType() {
  const candidates = [
    'video/webm;codecs=vp9,opus',
    'video/webm;codecs=vp8,opus',
    'video/webm',
    'video/mp4', // Safari / recent Chrome
  ];
  for (const type of candidates) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(type)) return type;
  }
  return '';
}

function supportsInPageRecording() {
  return Boolean(
    window.isSecureContext &&
    navigator.mediaDevices &&
    navigator.mediaDevices.getUserMedia &&
    typeof window.MediaRecorder !== 'undefined'
  );
}

const fmt = (s) => {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${String(m).padStart(2, '0')}:${sec.toFixed(1).padStart(4, '0')}`;
};

const bigButton = {
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  width: '100%', minHeight: 56, padding: '14px 18px', borderRadius: 12,
  fontSize: '1rem', fontWeight: 700, cursor: 'pointer', border: 'none',
};

const cardStyle = {
  background: 'var(--bg-subtle)',
  border: '1px solid var(--border-subtle)',
  borderRadius: 'var(--radius-lg)',
  padding: '24px 18px',
};

export function PhonePair({ token }) {
  // phases: checking | ready | recording | review | uploading | success | invalid | expired | error
  const [phase, setPhase] = useState('checking');
  const [mode, setMode] = useState(() => (supportsInPageRecording() ? 'recorder' : 'native'));
  const [file, setFile] = useState(null);
  const [progress, setProgress] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');
  const [elapsed, setElapsed] = useState(0);

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const startedAtRef = useRef(null);
  const phaseRef = useRef(phase);
  const checkedRef = useRef(false);       // StrictMode: validate once
  const cameraActiveRef = useRef(false);
  const cameraPendingRef = useRef(false); // StrictMode: one getUserMedia at a time

  phaseRef.current = phase;

  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // Token validity check — also reused by the error screen's Try again.
  const checkToken = useCallback(async () => {
    setPhase('checking');
    setErrorMsg('');
    try {
      const res = await apiFetch(`/api/v1/pairing/${encodeURIComponent(token)}`);
      if (res.status === 'uploaded') {
        setPhase('success'); // page reloaded after a completed upload
      } else {
        setPhase('ready');
      }
    } catch (err) {
      if (err instanceof APIError && err.status === 404) setPhase('invalid');
      else if (err instanceof APIError && err.status === 410) setPhase('expired');
      else {
        setErrorMsg(err?.message || 'Could not reach the SmartSpeak server.');
        setPhase('error');
      }
    }
  }, [token]);

  useEffect(() => {
    if (checkedRef.current) return undefined;
    checkedRef.current = true;
    checkToken();
    return undefined;
  }, [checkToken]);

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      // The user may have moved on (stop, unmount) while permission sat
      // pending — don't leak a live camera.
      if (phaseRef.current !== 'ready') {
        stream.getTracks().forEach((t) => t.stop());
        return;
      }
      streamRef.current = stream;
      cameraActiveRef.current = true;
      if (videoRef.current) videoRef.current.srcObject = stream;
    } catch {
      // Permission denied or no camera: fall back to the OS camera app
      // (works without any browser permission).
      cameraActiveRef.current = false;
      stopStream();
      setMode('native');
    }
  }, [stopStream]);

  // Start the preview when the recorder screen is shown.
  useEffect(() => {
    if (phase === 'ready' && mode === 'recorder' && !cameraActiveRef.current && !cameraPendingRef.current) {
      cameraPendingRef.current = true;
      startCamera().finally(() => { cameraPendingRef.current = false; });
    }
  }, [phase, mode, startCamera]);

  // Any non-camera screen releases the camera.
  useEffect(() => {
    if (phase !== 'ready' && phase !== 'recording') {
      stopStream();
      cameraActiveRef.current = false;
    }
  }, [phase, stopStream]);

  // Unmount safety net.
  useEffect(() => () => { stopStream(); }, [stopStream]);

  const startRecording = () => {
    const stream = streamRef.current;
    if (!stream) return;
    const mimeType = pickMimeType();
    let recorder;
    try {
      recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    } catch {
      try {
        recorder = new MediaRecorder(stream);
      } catch {
        setMode('native');
        return;
      }
    }
    recorderRef.current = recorder;
    chunksRef.current = [];

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onerror = () => {
      stopStream();
      setMode('native');
    };
    recorder.onstop = () => {
      const actualMime = recorder.mimeType || mimeType || 'video/webm';
      const ext = actualMime.includes('mp4') ? 'mp4' : 'webm';
      const blob = new Blob(chunksRef.current, { type: actualMime });
      const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      chunksRef.current = [];
      stopStream();
      cameraActiveRef.current = false;
      setFile(new File([blob], `phone-take-${stamp}.${ext}`, { type: actualMime }));
      setErrorMsg('');
      setPhase('review');
    };

    recorder.start(1000);
    startedAtRef.current = Date.now();
    setElapsed(0);
    setPhase('recording');
    timerRef.current = setInterval(() => {
      setElapsed((Date.now() - startedAtRef.current) / 1000);
    }, 250);
  };

  const stopRecording = () => {
    const r = recorderRef.current;
    if (r && r.state !== 'inactive') r.stop();
  };

  const validatePickedFile = (picked) => {
    const ext = '.' + picked.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      setErrorMsg(`'${ext}' isn't a supported video format. Use .mp4, .mov, or .webm.`);
      return false;
    }
    if (picked.size > MAX_SIZE_MB * 1024 * 1024) {
      setErrorMsg(
        `That video is ${(picked.size / (1024 * 1024)).toFixed(0)} MB — the limit is ${MAX_SIZE_MB} MB. Record a shorter take.`,
      );
      return false;
    }
    return true;
  };

  const handleNativeFile = (e) => {
    const picked = e.target.files && e.target.files[0];
    e.target.value = ''; // allow re-picking the same file
    if (!picked) return;
    setErrorMsg('');
    if (!validatePickedFile(picked)) return;
    setFile(picked);
    setPhase('review');
  };

  const startUpload = (fileToUpload) => {
    const f = fileToUpload || file;
    if (!f) return;
    setPhase('uploading');
    setProgress(0);
    setErrorMsg('');

    const formData = new FormData();
    formData.append('video', f);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `/api/v1/pairing/${encodeURIComponent(token)}/upload`);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        setProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status === 201 || xhr.status === 200) {
        setPhase('success');
        return;
      }
      if (xhr.status === 404) { setPhase('invalid'); return; }
      if (xhr.status === 410) { setPhase('expired'); return; }
      let msg = `Upload failed (HTTP ${xhr.status}).`;
      try {
        const res = JSON.parse(xhr.responseText);
        if (res && res.detail) msg = res.detail;
      } catch { /* non-JSON body */ }
      if (xhr.status === 429) {
        msg = 'Too many uploads from this device — wait a few minutes, then retry.';
      }
      setErrorMsg(msg);
      setPhase('error');
    };

    xhr.onerror = () => {
      setErrorMsg('Connection lost. Make sure this phone is on the same network as the laptop, then retry.');
      setPhase('error');
    };

    xhr.send(formData);
  };

  const handleDiscard = () => {
    setFile(null);
    setErrorMsg('');
    setPhase('ready');
  };

  const handleRetry = () => {
    if (file) startUpload(file);
    else checkToken();
  };

  const isBusy = phase === 'checking' || phase === 'uploading';

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '32px 16px 48px' }}>
      <div style={{ textAlign: 'center', marginBottom: 20 }}>
        <div style={{
          width: 52, height: 52, borderRadius: '50%', background: 'var(--primary-purple-light)',
          color: 'var(--primary-purple)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Smartphone size={24} />
        </div>
        <h1 style={{ fontSize: '1.3rem', fontWeight: 800, marginTop: 10 }}>SmartSpeak</h1>
        <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Record your practice take on this phone</p>
      </div>

      <div style={{ ...cardStyle, width: '100%', maxWidth: 460 }} aria-live="polite">
        {phase === 'checking' && (
          <p style={{ display: 'flex', gap: 8, justifyContent: 'center', alignItems: 'center', fontSize: '0.92rem', color: 'var(--text-secondary)', padding: '12px 0' }}>
            <Loader2 size={16} className="animate-spin" /> Checking your pairing code…
          </p>
        )}

        {(phase === 'invalid' || phase === 'expired') && (
          <div style={{ textAlign: 'center', padding: '8px 0' }}>
            <AlertTriangle size={34} color="#d97706" style={{ marginBottom: 10 }} />
            <h2 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: 6 }}>
              {phase === 'expired' ? 'This pairing code has expired' : 'This pairing code is no longer valid'}
            </h2>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              {phase === 'expired'
                ? 'Codes last 10 minutes. On the laptop, tap "Regenerate QR" and scan the new code.'
                : 'The code was cancelled or already used. On the laptop, tap "Regenerate QR" and scan the new code.'}
            </p>
          </div>
        )}

        {phase === 'success' && (
          <div style={{ textAlign: 'center', padding: '12px 0' }}>
            <CheckCircle2 size={40} color="#10b981" style={{ marginBottom: 10 }} />
            <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 6 }}>Uploaded!</h2>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              You can close this page — your report is opening on the laptop.
            </p>
          </div>
        )}

        {phase === 'error' && (
          <div style={{ textAlign: 'center', padding: '8px 0' }}>
            <AlertTriangle size={30} color="#dc2626" style={{ marginBottom: 10 }} />
            <p role="alert" style={{ fontSize: '0.9rem', color: '#dc2626', marginBottom: 16 }}>{errorMsg}</p>
            <button type="button" style={{ ...bigButton, background: 'var(--primary-purple)', color: '#fff' }} onClick={handleRetry}>
              <RefreshCw size={17} />
              Retry
            </button>
          </div>
        )}

        {(phase === 'ready' || phase === 'recording') && mode === 'recorder' && (
          <div style={{ background: '#0f172a', borderRadius: 14, padding: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <span style={{ color: '#e2e8f0', fontSize: '0.85rem', fontWeight: 700, display: 'flex', gap: 8, alignItems: 'center' }}>
                {phase === 'recording' && (
                  <span className="animate-pulse-soft" style={{ width: 9, height: 9, borderRadius: '50%', background: '#ef4444', display: 'inline-block' }} />
                )}
                {phase === 'recording' ? 'Recording…' : 'Front camera ready'}
              </span>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: '0.95rem', fontWeight: 700,
                color: phase === 'recording' ? '#f87171' : '#94a3b8',
                background: 'rgba(255,255,255,0.08)', padding: '2px 10px', borderRadius: 6,
              }}>
                {fmt(elapsed)}
              </span>
            </div>

            <video
              ref={videoRef}
              autoPlay
              muted
              playsInline
              style={{ width: '100%', borderRadius: 10, background: '#000', display: 'block', transform: 'scaleX(-1)' }}
            />

            <div style={{ marginTop: 12 }}>
              {phase === 'ready' ? (
                <button type="button" style={{ ...bigButton, background: 'var(--primary-purple)', color: '#fff' }} onClick={startRecording}>
                  <Camera size={19} />
                  Start recording
                </button>
              ) : (
                <button type="button" style={{ ...bigButton, background: '#dc2626', color: '#fff' }} onClick={stopRecording}>
                  <Square size={17} />
                  Stop
                </button>
              )}
            </div>

            <p style={{ textAlign: 'center', color: '#94a3b8', fontSize: '0.75rem', margin: '10px 4px 2px' }}>
              Nothing uploads until you stop and tap Upload.
            </p>
          </div>
        )}

        {(phase === 'ready') && mode === 'native' && (
          <div>
            <label
              htmlFor="phone-capture"
              style={{ ...bigButton, background: 'var(--primary-purple)', color: '#fff' }}
            >
              <Camera size={20} />
              Record with your camera
            </label>
            <input
              id="phone-capture"
              type="file"
              accept="video/*"
              capture="user"
              onChange={handleNativeFile}
              style={{ display: 'none' }}
            />

            <label
              htmlFor="phone-gallery"
              style={{ ...bigButton, background: '#fff', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', marginTop: 10 }}
            >
              <Image size={19} />
              Choose an existing video
            </label>
            <input
              id="phone-gallery"
              type="file"
              accept="video/*"
              onChange={handleNativeFile}
              style={{ display: 'none' }}
            />

            {errorMsg && (
              <p role="alert" style={{ fontSize: '0.85rem', color: '#dc2626', marginTop: 12 }}>{errorMsg}</p>
            )}

            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 14, textAlign: 'center', lineHeight: 1.5 }}>
              Opens your camera app — no browser permission needed. You'll confirm
              before anything uploads. Keep takes under a few minutes (500 MB limit).
            </p>
          </div>
        )}

        {phase === 'review' && file && (
          <div>
            <p style={{ fontSize: '0.92rem', fontWeight: 700, marginBottom: 10 }}>Ready to upload</p>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px',
              background: 'var(--bg-subtle)', border: '1px solid var(--border-subtle)',
              borderRadius: 10, marginBottom: 12,
            }}>
              <Camera size={20} color="var(--primary-purple)" />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: '0.88rem', fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {file.name}
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  {(file.size / (1024 * 1024)).toFixed(1)} MB
                </div>
              </div>
            </div>

            {errorMsg && (
              <p role="alert" style={{ fontSize: '0.85rem', color: '#dc2626', marginBottom: 10 }}>{errorMsg}</p>
            )}

            <button type="button" style={{ ...bigButton, background: 'var(--primary-purple)', color: '#fff' }} onClick={() => startUpload(file)}>
              <Upload size={18} />
              Upload video
            </button>
            <button
              type="button"
              style={{ ...bigButton, background: '#fff', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)', marginTop: 10 }}
              onClick={handleDiscard}
            >
              <RefreshCw size={17} />
              Discard and try again
            </button>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 12, textAlign: 'center', lineHeight: 1.5 }}>
              The video stays on your local network — it goes straight to the laptop.
            </p>
          </div>
        )}

        {phase === 'uploading' && (
          <div style={{ padding: '10px 0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.88rem', marginBottom: 8 }}>
              <span style={{ display: 'flex', gap: 8, alignItems: 'center', color: 'var(--text-secondary)' }}>
                <Loader2 size={16} className="animate-spin" color="var(--primary-purple)" />
                Uploading to the laptop…
              </span>
              <strong>{progress}%</strong>
            </div>
            <div style={{ background: 'var(--border-subtle)', borderRadius: 999, height: 10, overflow: 'hidden' }}>
              <div style={{
                width: `${progress}%`, height: '100%', borderRadius: 999,
                background: 'var(--primary-purple)', transition: 'width 0.2s ease',
              }} />
            </div>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 10, textAlign: 'center' }}>
              Keep this page open until it finishes.
            </p>
          </div>
        )}
      </div>

      {isBusy && <span aria-hidden="true" style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden' }} />}
    </div>
  );
}

export default PhonePair;
