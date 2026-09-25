import React, { useMemo } from 'react';
import { MessageSquare, MousePointerClick } from 'lucide-react';
import { useReportVideo } from './ReportVideoPlayer';

/**
 * InteractiveTranscript — renders the transcript with fillers, repetitions,
 * and long pauses highlighted inline. Click any token to seek the video.
 *
 * Positioning strategy: word-level timings from Whisper (`speech_analysis.words`,
 * shape { word, start, end, probability }) are the anchor. Filler/repetition
 * entries carry an absolute timestamp, so each is matched to the first word
 * whose timing window covers (or is nearest to) it. When word timings are
 * missing entirely (very old sessions), we fall back to proportional
 * positioning across the transcript text from the same timestamps.
 */

const fmt = (s) => {
  const n = Number(s) || 0;
  return n >= 60 ? `${Math.floor(n / 60)}:${String(Math.round(n % 60)).padStart(2, '0')}` : `${Math.round(n)}s`;
};

const norm = (w) => String(w || '').toLowerCase().replace(/[.,!?;:"']/g, '').trim();

// Build a normalized version of every word with its char span in a joined string.
function buildNormalizedWords(words) {
  let cursor = 0;
  return words.map((w) => {
    const raw = String(w.word ?? w);
    const clean = norm(raw);
    const start = cursor;
    cursor += raw.length + 1; // +1 for the joining space
    return { ...w, raw, clean, charStart: start, charEnd: start + raw.length };
  });
}

function matchTimestampToWordIndex(words, timestamp) {
  if (!words.length) return -1;
  // Prefer the word whose [start, end] window contains the timestamp
  const containing = words.findIndex((w) => {
    const s = Number(w.start);
    const e = Number(w.end);
    return Number.isFinite(s) && Number.isFinite(e) && timestamp >= s - 0.05 && timestamp <= e + 0.15;
  });
  if (containing !== -1) return containing;
  // Otherwise nearest by |midpoint - timestamp|
  let best = -1;
  let bestDist = Infinity;
  words.forEach((w, i) => {
    const s = Number(w.start);
    const e = Number(w.end);
    const mid = Number.isFinite(s) && Number.isFinite(e) ? (s + e) / 2 : NaN;
    const d = Number.isFinite(mid) ? Math.abs(mid - timestamp) : Infinity;
    if (d < bestDist) { bestDist = d; best = i; }
  });
  return best;
}

export function InteractiveTranscript({ speechAnalysis }) {
  const { seekTo, hasVideo } = useReportVideo();
  const sa = speechAnalysis || {};

  const model = useMemo(() => {
    const transcript = String(sa.transcript_text || '');
    if (!transcript) return null;

    const words = Array.isArray(sa.words) && sa.words.length
      ? sa.words.filter((w) => String(w.word ?? w).trim())
      : null;
    const fillers = sa.filler_words || [];
    const reps = sa.repetitions || [];
    const pauses = sa.long_pauses || [];

    // --- Word-timing path ---
    if (words) {
      const nw = buildNormalizedWords(words);
      const fillerAt = new Map(); // word index -> { kind, label }
      const repAt = new Map();

      fillers.forEach((f) => {
        const idx = matchTimestampToWordIndex(nw, Number(f.timestamp));
        if (idx >= 0) fillerAt.set(idx, { kind: 'filler', label: f.word });
      });
      reps.forEach((r) => {
        const idx = matchTimestampToWordIndex(nw, Number(r.timestamp));
        if (idx >= 0 && !fillerAt.has(idx)) repAt.set(idx, { kind: 'rep', label: r.phrase });
      });

      return { mode: 'words', nw, fillerAt, repAt, pauses, transcript };
    }

    // --- Proportional fallback (no word timings) ---
    const totalChars = transcript.length || 1;
    const estDuration = Math.max(
      ...pauses.map((p) => Number(p.end_time) || 0),
      ...fillers.map((f) => Number(f.timestamp) || 0),
      ...reps.map((r) => Number(r.timestamp) || 0),
      Number(sa.wpm_data?.total_speaking_duration_seconds) || 0,
      1
    );
    const spans = [];
    fillers.forEach((f) => {
      const t = Number(f.timestamp);
      if (!Number.isFinite(t)) return;
      const at = Math.min(totalChars - 1, Math.round((t / estDuration) * totalChars));
      spans.push({ kind: 'filler', label: f.word, charStart: at, charEnd: at + String(f.word).length });
    });
    reps.forEach((r) => {
      const t = Number(r.timestamp);
      if (!Number.isFinite(t)) return;
      const at = Math.min(totalChars - 1, Math.round((t / estDuration) * totalChars));
      spans.push({ kind: 'rep', label: r.phrase, charStart: at, charEnd: at + String(r.phrase).length });
    });
    return { mode: 'proportional', transcript, spans, pauses, totalChars };
  }, [sa]);

  if (!model) return null;

  const legend = (sa.filler_words?.length > 0 || sa.repetitions?.length > 0 || sa.long_pauses?.length > 0) ? (
    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 10, marginBottom: 0, display: 'flex', alignItems: 'flex-start', gap: 5 }}>
      <MousePointerClick size={13} style={{ flexShrink: 0, marginTop: 2 }} />
      <span>
        <span style={{ background: '#fef3c7', padding: '0 4px', borderRadius: 3, borderBottom: '2px solid #f59e0b', color: '#92400e', fontWeight: 700 }}>amber</span>
        {' '}= filler · <span style={{ background: '#f3e8ff', padding: '0 4px', borderRadius: 3, borderBottom: '2px solid #8b5cf6', color: '#6b21a8', fontWeight: 700 }}>purple</span> = repetition · ⏸ = long pause
        {hasVideo ? ' — click any highlight to watch that moment' : ''}
      </span>
    </p>
  ) : null;

  const handleSeek = (t, label) => {
    if (hasVideo) seekTo(Math.max(0, Number(t) || 0));
  };

  // ---------- Word-timed rendering ----------
  if (model.mode === 'words') {
    const { nw, fillerAt, repAt, pauses } = model;
    const pauseByWord = new Map();
    pauses.forEach((p) => {
      const idx = matchTimestampToWordIndex(nw, Number(p.start_time));
      if (idx >= 0) pauseByWord.set(idx, p);
    });

    const out = [];
    let key = 0;
    for (let i = 0; i < nw.length; i++) {
      const w = nw[i];
      const mark = fillerAt.get(i) || repAt.get(i);
      const pause = pauseByWord.get(i);

      if (pause) {
        out.push(
          <span
            key={`pause-${key++}`}
            title={hasVideo ? `Long pause ${fmt(pause.start_time)}–${fmt(pause.end_time)} — click to watch` : `Long pause (${Number(pause.duration).toFixed(1)}s)`}
            onClick={() => handleSeek(pause.start_time, 'pause')}
            style={{
              display: 'inline-flex', alignItems: 'center', margin: '0 4px', padding: '0 8px',
              background: '#eff6ff', border: '1px solid #bfdbfe', color: '#1e40af',
              borderRadius: 999, fontSize: '0.72rem', fontWeight: 700, cursor: hasVideo ? 'pointer' : 'default',
              verticalAlign: 'middle', lineHeight: '20px',
            }}
          >
            ⏸ {Number(pause.duration).toFixed(1)}s
          </span>
        );
      }

      const isFiller = mark?.kind === 'filler';
      const isRep = mark?.kind === 'rep';
      out.push(
        <span
          key={`w-${key++}`}
          title={isFiller || isRep
            ? (hasVideo ? `"${mark.label}" — click to watch (${fmt(Number(nw[i].start))})` : `"${mark.label}"`)
            : undefined}
          onClick={() => {
            if ((isFiller || isRep) && hasVideo) seekTo(Math.max(0, Number(nw[i].start) || 0));
          }}
          style={{
            ...(isFiller ? {
              background: '#fef3c7', borderBottom: '2px solid #f59e0b', color: '#92400e',
              fontWeight: 700, borderRadius: 3, padding: '0 3px', cursor: hasVideo ? 'pointer' : 'default',
            } : {}),
            ...(isRep ? {
              background: '#f3e8ff', borderBottom: '2px solid #8b5cf6', color: '#6b21a8',
              fontWeight: 700, borderRadius: 3, padding: '0 3px', cursor: hasVideo ? 'pointer' : 'default',
            } : {}),
          }}
        >
          {w.raw}
        </span>,
        ' '
      );
    }

    return (
      <>
        <div style={{
          background: 'var(--bg-subtle)', border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-md)', padding: 16, fontSize: '0.92rem', lineHeight: 1.9,
          color: 'var(--text-primary)', maxHeight: 260, overflowY: 'auto',
        }}>
          {out}
        </div>
        {legend}
      </>
    );
  }

  // ---------- Proportional fallback rendering ----------
  const { transcript, spans } = model;
  const pieces = [];
  let cursor = 0;
  spans
    .slice()
    .sort((a, b) => a.charStart - b.charStart)
    .forEach((sp, i) => {
      const start = Math.max(cursor, sp.charStart);
      const end = Math.min(transcript.length, Math.max(start, sp.charEnd));
      if (start > cursor) pieces.push(<span key={`t${i}`}>{transcript.slice(cursor, start)}</span>);
      const tsMatch = (sp.kind === 'filler' && (sa.filler_words || []).find((f) => f.word === sp.label)) ||
                      (sp.kind === 'rep' && (sa.repetitions || []).find((r) => r.phrase === sp.label));
      const t = Number(tsMatch?.timestamp) || 0;
      pieces.push(
        <mark
          key={`m${i}`}
          onClick={() => handleSeek(t, sp.label)}
          title={hasVideo ? `"${sp.label}" — click to watch` : `"${sp.label}"`}
          style={{
            background: sp.kind === 'filler' ? '#fef3c7' : '#f3e8ff',
            color: sp.kind === 'filler' ? '#92400e' : '#6b21a8',
            borderBottom: `2px solid ${sp.kind === 'filler' ? '#f59e0b' : '#8b5cf6'}`,
            fontWeight: 700, borderRadius: 3, padding: '0 3px', cursor: hasVideo ? 'pointer' : 'default',
          }}
        >
          {transcript.slice(start, end)}
        </mark>
      );
      cursor = end;
    });
  if (cursor < transcript.length) pieces.push(<span key="tail">{transcript.slice(cursor)}</span>);

  return (
    <>
      <div style={{
        background: 'var(--bg-subtle)', border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-md)', padding: 16, fontSize: '0.92rem', lineHeight: 1.9,
        color: 'var(--text-primary)', maxHeight: 260, overflowY: 'auto',
      }}>
        {pieces}
      </div>
      {legend}
    </>
  );
}

export default InteractiveTranscript;
