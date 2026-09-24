import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { Video, VideoOff, Volume2, VolumeX, Play, Pause } from 'lucide-react';

/**
 * Report video: a provider that owns the <video> element reference and
 * exposes seekTo(seconds) + hasVideo via context, plus a player UI component
 * that can be placed anywhere inside the provider's subtree.
 *
 * StatusTracker wraps the whole report in the provider so every annotation
 * (filler chips, pause rows, mistake markers, timeline markers, transcript
 * highlights) can seek the video. When the session's video file is gone
 * (old/retention-cleaned sessions) the player UI renders nothing and seekTo
 * is a safe no-op, so annotation code needs no conditional plumbing.
 */

const ReportVideoContext = createContext({
  seekTo: () => {},
  hasVideo: false,
  videoSrc: null,
  setVideoEl: () => {},
});

export function useReportVideo() {
  return useContext(ReportVideoContext);
}

const fmt = (s) => {
  if (!Number.isFinite(s)) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
};

export function ReportVideoProvider({ sessionId, children }) {
  const videoRef = useRef(null);
  const [state, setState] = useState('loading'); // loading | ready | unavailable | error
  const [videoSrc, setVideoSrc] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setState('loading');
    setVideoSrc(null);
    (async () => {
      try {
        const res = await fetch(`/api/v1/sessions/${sessionId}/video/status`);
        if (!res.ok) throw new Error(`status ${res.status}`);
        const data = await res.json();
        if (cancelled) return;
        if (data.available && data.url) {
          setVideoSrc(data.url);
          setState('ready');
        } else {
          setState('unavailable');
        }
      } catch {
        if (!cancelled) setState('unavailable');
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId]);

  const setVideoEl = (el) => { videoRef.current = el; };

  const seekTo = (seconds) => {
    const v = videoRef.current;
    if (!v || state !== 'ready') return;
    try {
      v.currentTime = Math.max(0, Number(seconds) || 0);
      v.play().catch(() => {});
    } catch {
      /* seeking before metadata is loaded is fine to ignore */
    }
  };

  const ctx = { seekTo, hasVideo: state === 'ready', videoSrc, setVideoEl };

  return (
    <ReportVideoContext.Provider value={ctx}>
      {state === 'error' && (
        <div style={{
          background: '#fef2f2', border: '1px solid #fecaca', color: '#b91c1c',
          borderRadius: 'var(--radius-lg)', padding: '12px 18px', fontSize: '0.85rem', marginBottom: 24,
          display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <VideoOff size={16} />
          The video file exists but could not be played in the browser.
        </div>
      )}
      {children}
    </ReportVideoContext.Provider>
  );
}

/**
 * ReportVideoPlayer — the dark player shell. Render it anywhere inside the
 * provider; it renders nothing when no video is available.
 */
export function ReportVideoPlayer() {
  const { videoSrc, setVideoEl } = useReportVideo();
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);

  if (!videoSrc) return null;

  const togglePlay = () => {
    const v = document.querySelector('video[data-report-video="1"]');
    if (!v) return;
    if (v.paused) v.play().catch(() => {});
    else v.pause();
  };

  return (
    <div className="animate-fade-in print-break-avoid" style={{
      background: '#0f172a',
      borderRadius: 'var(--radius-lg)',
      padding: '16px',
      marginBottom: 24,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
        <span style={{ color: '#e2e8f0', fontSize: '0.85rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Video size={16} color="#a78bfa" />
          Session Video
          <span style={{ fontWeight: 400, color: '#94a3b8', fontSize: '0.75rem' }}>
            — click any highlighted moment below to jump here
          </span>
        </span>
        <button
          type="button"
          className="no-print"
          onClick={() => {
            const v = document.querySelector('video[data-report-video="1"]');
            if (v) { v.muted = !v.muted; setMuted(v.muted); }
          }}
          style={{
            background: 'rgba(255,255,255,0.08)', color: '#cbd5e1', border: '1px solid rgba(255,255,255,0.15)',
            borderRadius: 6, padding: '3px 10px', fontSize: '0.75rem', cursor: 'pointer',
            display: 'inline-flex', alignItems: 'center', gap: 5,
          }}
          aria-label={muted ? 'Unmute video' : 'Mute video'}
        >
          {muted ? <VolumeX size={14} /> : <Volume2 size={14} />}
          {muted ? 'Muted' : 'Sound on'}
        </button>
      </div>

      <video
        data-report-video="1"
        ref={setVideoEl}
        src={videoSrc}
        controls
        preload="metadata"
        playsInline
        style={{ width: '100%', maxHeight: '440px', borderRadius: 'var(--radius-md)', background: '#000', display: 'block' }}
        onLoadedMetadata={(e) => setDuration(e.target.duration || 0)}
        onTimeUpdate={(e) => setCurrent(e.target.currentTime)}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
      />

      {/* Custom quick-seek bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 10 }}>
        <button
          type="button"
          onClick={togglePlay}
          className="no-print"
          style={{
            background: 'rgba(255,255,255,0.1)', color: '#fff', border: 'none', borderRadius: '50%',
            width: 34, height: 34, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}
          aria-label={playing ? 'Pause' : 'Play'}
        >
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <span style={{ color: '#94a3b8', fontSize: '0.72rem', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
          {fmt(current)} / {fmt(duration)}
        </span>
        <div
          className="no-print"
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
            const v = document.querySelector('video[data-report-video="1"]');
            if (v && duration) { v.currentTime = frac * duration; }
          }}
          style={{ flex: 1, height: 8, background: 'rgba(255,255,255,0.12)', borderRadius: 4, cursor: 'pointer', position: 'relative' }}
          role="slider"
          aria-label="Seek bar"
          aria-valuemin={0}
          aria-valuemax={Math.round(duration)}
          aria-valuenow={Math.round(current)}
        >
          <div style={{
            width: duration ? `${(current / duration) * 100}%` : '0%',
            height: '100%', background: 'linear-gradient(90deg, #7c3aed, #a78bfa)', borderRadius: 4,
            transition: 'width 0.15s linear', pointerEvents: 'none',
          }} />
        </div>
      </div>
    </div>
  );
}

export default ReportVideoProvider;
