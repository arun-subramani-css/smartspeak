# SmartSpeak — AI Public Speaking Coach

SmartSpeak is an AI-powered public speaking coach. This repository contains:
- **Module 1 (Video Upload)**: Video stream ingestion, format & container signature validation, and staging.
- **Module 2 (Audio & Video Processing)**: FFmpeg 16kHz mono WAV audio extraction & OpenCV 1 FPS frame sampling.
- **Speech Analysis Module**: OpenAI Whisper transcription with word timestamps, filler word detection, overall & rolling WPM calculation, long pause detection ($\ge 3.0$s), and word/phrase repetition detection.

---

## Architecture Overview

### Speech Analysis Pipeline (`/backend/app/services/speech_analyzer.py`)
1. **STT Transcription**:
   - Runs OpenAI Whisper (`whisper.load_model("base")`) with `word_timestamps=True`.
   - Executed inside a thread pool executor (`asyncio.get_running_loop().run_in_executor`) to prevent event loop blocking.
   - Outputs full text transcript and word-level timestamp array (`{word, start, end, probability}`).
2. **Filler Word Detection**:
   - Matches single-word (`um`, `uh`, `like`, `actually`, `basically`) and multi-word phrases (`you know`) against word timestamps.
   - Returns list of `{word, timestamp}` occurrences and total count.
3. **Speaking Speed (WPM)**:
   - Overall WPM calculated based on actual speech duration (excluding long silences).
   - Rolling WPM calculated over 15-second sliding windows (stepping by 5s) to track speed fluctuations over time.
4. **Long Pause Detection**:
   - Identifies gaps between consecutive spoken words $\ge 3.0$ seconds.
   - Returns list of `{start_time, end_time, duration}`.
5. **Repeated Word / Phrase Detection**:
   - Identifies immediate single word repetitions (e.g. "the the") and 2-4 word repeated sequences (e.g. "I think... I think").
6. **MongoDB Storage**:
   - Sub-document `speech_analysis` stored under session document. Overwrites on re-run without duplicating data.
   - Status transitions: `uploaded` ➔ `processing` ➔ `processed` ➔ `speech_analysis_complete`.

---

## Prerequisites

- **Python**: 3.11 or higher
- **FFmpeg**: System binary installed on PATH or bundled via `imageio_ffmpeg`.
- **OpenAI Whisper & PyTorch**: `pip install openai-whisper torch`

---

## Performance & Benchmark

### Expected Processing Times (Whisper `base` Model)
| Audio Length | Device | Expected Speech Analysis Time |
| :--- | :--- | :--- |
| **1 Minute** | CPU | 2 – 5 seconds |
| **1 Minute** | NVIDIA GPU (CUDA) | < 1 second |
| **5 Minutes** | CPU | 10 – 20 seconds |
| **5 Minutes** | NVIDIA GPU (CUDA) | 2 – 4 seconds |

---

## API Reference

### 1. GET Session Speech Analysis
- **URL**: `GET /api/v1/sessions/{session_id}/speech-analysis`
- **Response**: JSON containing full transcript, word timestamps, filler words, WPM metrics, pauses, and repetitions.

#### Example Response (200 OK)
```json
{
  "session_id": "6ad7eed3-abd5-45f6-b728-39b558d55b7d",
  "status": "speech_analysis_complete",
  "speech_analysis": {
    "transcript_text": "Hello everyone. Um, today I want to talk about, like, our project. We need to, you know, deliver results.",
    "words": [
      { "word": "Hello", "start": 0.5, "end": 0.8, "probability": 0.95 },
      { "word": "everyone.", "start": 0.85, "end": 1.2, "probability": 0.98 },
      { "word": "Um,", "start": 1.5, "end": 1.8, "probability": 0.92 }
    ],
    "filler_words": [
      { "word": "um", "timestamp": 1.5 },
      { "word": "like", "timestamp": 3.1 },
      { "word": "you know", "timestamp": 5.4 }
    ],
    "filler_word_count": 3,
    "wpm_data": {
      "overall_wpm": 135.5,
      "total_words": 18,
      "total_speaking_duration_seconds": 8.0,
      "windowed_wpm": [
        { "window_start": 0.0, "window_end": 15.0, "wpm": 72.0 }
      ]
    },
    "long_pauses": [
      { "start_time": 8.5, "end_time": 12.0, "duration": 3.5 }
    ],
    "repetitions": [
      { "phrase": "We need to", "timestamp": 4.2, "count": 2 }
    ],
    "analyzed_at": "2026-07-21T06:20:00.000Z"
  }
}
```

---

### 2. POST Re-Run Speech Analysis (Internal / Retry)
- **URL**: `POST /api/v1/sessions/{session_id}/analyze-speech`
- **Response**: `202 Accepted`
```json
{
  "session_id": "6ad7eed3-abd5-45f6-b728-39b558d55b7d",
  "message": "Speech analysis task queued successfully.",
  "status": "processing"
}
```
