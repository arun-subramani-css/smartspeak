# SmartSpeak — AI Public Speaking Coach

Upload a recording of a speech and get a full coaching report: pacing, filler words, long pauses,
repetitions, eye contact, posture, hand gestures, head movement — plus a fusion engine that
correlates what you said with what your body was doing.

## How it works

```
Upload (.mp4/.avi/.mov, ≤500 MB)
   │  extension + container-header validation
   ▼
FFmpeg extraction ──► audio (16 kHz mono WAV) + 1 fps frames
   │
   ├──► Speech analysis   Whisper (faster-whisper by default) → transcript, WPM windows,
   │                      filler words, long pauses, repetitions, STT confidence
   ├──► Visual analysis    MediaPipe FaceMesh/Pose/Hands → eye contact (baseline-calibrated),
   │                      posture (trained Random Forest classifier), gestures + ranges,
   │                      head-movement velocity
   ▼
Fusion engine ──► SmartSpeak Index (0–100), grade, correlated mistakes,
                  gesture ↔ speech insights, session timeline data
```

Processing runs in background threads with live per-stage progress; the UI polls and shows
progress bars per stage. Everything is stored locally (JSON document store) with a 30-day
retention scheduler.

## Report features

- **SmartSpeak Index** — weighted composite (verbal 40% / non-verbal 40% / confidence 20%) with grade
- **Session timeline** — interactive SVG chart: WPM curve with ideal 110–160 band, pause /
  looking-away / posture / gesture lanes, mistake markers
- **Recent Reports** — reopen any past session from the landing page, with trend deltas
- **Progress over time** — line chart of scores across sessions
- **Download PDF** — print-optimized export of the full report

## Running

```bash
# Backend (FastAPI) — http://localhost:8000  (Swagger at /docs)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (Vite + React) — http://localhost:5173 (proxies /api → :8000)
cd frontend
npm install
npm run dev
```

Models (Whisper, spaCy, MediaPipe, posture classifier) are prewarmed at startup so the first
upload doesn't pay load latency.

## Configuration (`backend/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `MONGODB_URI` | local fallback store | Mongo connection (falls back to atomic JSON store) |
| `WHISPER_ENGINE` | `faster` | `faster` (faster-whisper, ~2.6× faster, int8) or `openai` |
| `WHISPER_MODEL` | `base` | Whisper size — `small` is affordable with the faster engine |
| `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | `cpu` / `int8` | faster-whisper device + quantization |
| `MAX_UPLOAD_SIZE_MB` | `500` | Upload cap (enforced while streaming) |
| `CORS_ALLOW_ORIGINS` | localhost dev origins | Comma-separated list; use your deploy URL in production |
| `RETENTION_DAYS` | `30` | Auto-deletion window for processed sessions |
| `FRAME_SAMPLE_FPS` etc. | see `backend/app/config.py` | Sampling rates and detection thresholds |

See `backend/.env.example` and `frontend/.env.example` for the full list.

## Testing

```bash
cd backend  && python -m pytest tests/ -q   # 47 tests — pipeline, fusion, analyzers, confidence
cd frontend && npm test                     # 12 tests — TimelineChart + RecentReports (vitest)
```

## Project layout

```
backend/
  app/
    routers/        upload, sessions (status/history/report endpoints)
    services/       speech_analyzer, visual_analyzer, fusion_engine,
                    video_processor, file_validator, retention, progress
    db/             MongoDB client + atomic JSON fallback
    models/         session document schemas
  scripts/          posture classifier training (human-verified labels)
models/             posture_model.pkl + training report
frontend/
  src/components/   VideoUploader, StatusTracker, TimelineChart,
                    RecentReports, ScoreTrendChart, Header
```

## Privacy

Video, audio, frames, and reports stay on your machine. Nothing is sent to third-party services;
the only network calls during analysis are local.
