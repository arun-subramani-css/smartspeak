import React, { useEffect, useRef, useState } from 'react';
import { Video, Square, AlertCircle, CameraOff, Radio } from 'lucide-react';

/**
 * PracticeRecorder — in-browser recording via MediaRecorder (no dependencies).
 *
 * Flow: request webcam+mic → live preview with running timer → stop →
 * hand the recording to the parent as a normal File so the existing upload
 * flow (validation, progress, pipeline, report) runs completely unchanged.
 *
 * Friendly handling for: unsupported browsers (no MediaRecorder/getUserMedia),
 * permission denied / dismissed, camera-in-use, and mid-recording stream loss.
 */

const fmt = (s) => {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${String(m).padStart(2, '0')}:${sec.toFixed(1).padStart(4, '0')}`;
};

/** Picks the best container MIME the browser can actually record. */
function pickMimeType() {
  const candidates = [
    'video/webm;codecs=vp9,opus',
    'video/webm;codecs=vp8,opus',
    'video/webm',
    'video/mp4', // Safari
  ];
  for (const type of candidates) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(type)) return type;
  }
  return '';
}

export function PracticeRecorder({ onRecordingReady, onCancel }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const startedAtRef = useRef(null);

  const [phase, setPhase] = useState('idle'); // idle | denied | unsupported | error
  const [errorMsg, setErrorMsg] = useState('');
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  const stopStream = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) videoRef.current.srcObject = null;
  };

  useEffect(() => () => { // full cleanup on unmount
    stopStream();
    if (timerRef.current) clearInterval(timerRef.current);
  }, []);

  const showError = (msg) => {
    stopStream();
    setErrorMsg(msg);
    setPhase('error');
  };

  const startCamera = async () => {
    setErrorMsg('');

    // Unsupported browser checks
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || typeof window.MediaRecorder === 'undefined') {
      setPhase('unsupported');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setPhase('ready'); // preview is live; waiting for the user to hit record
    } catch (err) {
      if (err && (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError' || err.name === 'SecurityError')) {
        setPhase('denied');
      } else if (err && (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError' || err.name === 'OverconstrainedError')) {
        showError('We couldn\'t find a usable camera or microphone. Connect one (or check it isn\'t disabled) and try again.');
      } else if (err && (err.name === 'NotReadableError' || err.name === 'TrackStartError')) {
        showError('Your camera is being used by another app. Close it and try again.');
      } else {
        showError('Couldn\'t start the camera. You can still upload a video file instead.');
      }
    }
  };

  const startRecording = () => {
    const stream = streamRef.current;
    if (!stream) return;

    const mimeType = pickMimeType();
    let recorder;
    try {
      recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
    } catch {
      try {
        recorder = new MediaRecorder(stream); // fall back to browser default
      } catch (e2) {
        showError('Recording isn\'t supported in this browser. Try Chrome, Edge, or Firefox.');
        return;
      }
    }
    recorderRef.current = recorder;
    chunksRef.current = [];

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
    };

    recorder.onerror = () => {
      setRecording(false);
      if (timerRef.current) clearInterval(timerRef.current);
      showError('Recording failed unexpectedly. Please try again.');
    };

    recorder.onstop = () => {
      if (timerRef.current) clearInterval(timerRef.current);
      const actualMimeType = recorder.mimeType || mimeType || 'video/webm';
      const ext = actualMimeType.includes('mp4') ? 'mp4' : 'webm';
      const blob = new Blob(chunksRef.current, { type: actualMimeType });
      const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      const file = new File([blob], `practice-take-${stamp}.${ext}`, {
        type: actualMimeType,
      });
      chunksRef.current = [];
      stopStream();
      setRecording(false);
      if (onRecordingReady) onRecordingReady(file);
    };

    recorder.start(1000); // gather data each second for a clean stop
    startedAtRef.current = Date.now();
    setElapsed(0);
    setRecording(true);
    timerRef.current = setInterval(() => {
      setElapsed((Date.now() - startedAtRef.current) / 1000);
    }, 100);
  };

  const stopRecording = () => {
    const r = recorderRef.current;
    if (r && r.state !== 'inactive') r.stop();
  };

  const cancel = () => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') recorderRef.current.stop();
    stopStream();
    if (onCancel) onCancel();
  };

  // ---------- Idle / terminal states ----------
  if (phase !== 'ready') {
    return (
      <div style={{
        background: 'var(--bg-subtle)', border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-lg)', padding: '28px 24px', textAlign: 'center',
      }}>
        {phase === 'idle' && (
          <>
            <div style={{
              width: 56, height: 56, borderRadius: '50%', background: 'var(--primary-purple-light)',
              color: 'var(--primary-purple)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 14px',
            }}>
              <Video size={26} />
            </div>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: 6 }}>Practice now</h3>
            <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', maxWidth: 460, margin: '0 auto 16px' }}>
              Record yourself speaking straight from your browser — no file juggling.
              Your take goes through the same analysis pipeline as an upload.
            </p>
            <button className="btn-purple" onClick={startCamera}>
              <Radio size={17} />
              <span>Start camera &amp; record</span>
            </button>
            {onCancel && (
              <button className="btn-light" onClick={onCancel} style={{ marginLeft: 8 }}>
                Cancel
              </button>
            )}
          </>
        )}

        {phase === 'unsupported' && (
          <>
            <CameraOff size={30} color="#64748b" style={{ marginBottom: 10 }} />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: 6 }}>Recording isn't available here</h3>
            <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', maxWidth: 460, margin: '0 auto 16px' }}>
              Your browser doesn't support in-browser recording. Recent versions of Chrome, Edge, or Firefox
              work best — or you can simply upload a video file instead.
            </p>
            {onCancel && <button className="btn-light" onClick={onCancel}>Back to upload</button>}
          </>
        )}

        {phase === 'denied' && (
          <>
            <CameraOff size={30} color="#d97706" style={{ marginBottom: 10 }} />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: 6 }}>Camera access was blocked</h3>
            <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', maxWidth: 480, margin: '0 auto 8px' }}>
              To practice, allow camera and microphone access in your browser's address bar
              (the icon near the URL), then try again.
            </p>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', maxWidth: 480, margin: '0 auto 16px' }}>
              Nothing is uploaded until you stop the recording — and your video never leaves your machine.
            </p>
            <button className="btn-purple" onClick={startCamera}>
              <Radio size={17} />
              <span>Try again</span>
            </button>
            {onCancel && (
              <button className="btn-light" onClick={onCancel} style={{ marginLeft: 8 }}>
                Back to upload
              </button>
            )}
          </>
        )}

        {phase === 'error' && (
          <>
            <AlertCircle size={30} color="#dc2626" style={{ marginBottom: 10 }} />
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: 6 }}>Something went wrong</h3>
            <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', maxWidth: 460, margin: '0 auto 16px' }}>
              {errorMsg}
            </p>
            <button className="btn-purple" onClick={startCamera}>
              <Radio size={17} />
              <span>Try again</span>
            </button>
            {onCancel && (
              <button className="btn-light" onClick={onCancel} style={{ marginLeft: 8 }}>
                Back to upload
              </button>
            )}
          </>
        )}
      </div>
    );
  }

  // ---------- Live preview / recording ----------
  return (
    <div style={{
      background: '#0f172a', borderRadius: 'var(--radius-lg)', padding: 16,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
        <span style={{ color: '#e2e8f0', fontSize: '0.85rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
          {recording && <span className="animate-pulse-soft" style={{ width: 9, height: 9, borderRadius: '50%', background: '#ef4444' }} />}
          {recording ? 'Recording…' : 'Camera ready'}
        </span>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: '1rem', fontWeight: 700,
          color: recording ? '#f87171' : '#94a3b8',
          background: 'rgba(255,255,255,0.08)', padding: '2px 12px', borderRadius: 6,
        }}>
          {fmt(elapsed)}
        </span>
      </div>

      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        style={{ width: '100%', maxHeight: 440, borderRadius: 'var(--radius-md)', background: '#000', display: 'block', transform: 'scaleX(-1)' }}
      />

      <div style={{ display: 'flex', gap: 10, marginTop: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
        {!recording ? (
          <button className="btn-purple" onClick={startRecording}>
            <Radio size={17} />
            <span>Start recording</span>
          </button>
        ) : (
          <button
            className="btn-purple"
            onClick={stopRecording}
            style={{ background: '#dc2626' }}
            onMouseEnter={(e) => { e.currentTarget.style.background = '#b91c1c'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = '#dc2626'; }}
          >
            <Square size={16} />
            <span>Stop &amp; analyze</span>
          </button>
        )}
        <button
          className="btn-light no-print"
          onClick={cancel}
          style={{ background: 'rgba(255,255,255,0.08)', color: '#cbd5e1', borderColor: 'rgba(255,255,255,0.15)' }}
        >
          Cancel
        </button>
      </div>

      <p style={{ textAlign: 'center', color: '#94a3b8', fontSize: '0.75rem', margin: '10px 0 0' }}>
        Recording stays on your machine until you stop — then it flows through the normal analysis pipeline.
      </p>
    </div>
  );
}

export default PracticeRecorder;
