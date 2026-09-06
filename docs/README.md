# SmartSpeak — AI Public Speaking Coach

SmartSpeak is an AI-powered public speaking coach. This repository contains:
- **Module 1 (Video Upload)**: Video stream ingestion, format & container signature validation, and staging.
- **Module 2 (Audio & Video Processing)**: FFmpeg 16kHz mono WAV audio extraction & OpenCV 1 FPS frame sampling.
- **Speech Analysis Module**: OpenAI Whisper transcription with word timestamps, contextual filler word detection via spaCy, overall & rolling WPM calculation, long pause detection ($\ge 2.0$s), and word/phrase repetition detection.

---

## Architecture Overview

### Speech Analysis Pipeline (`/backend/app/services/speech_analyzer.py`)
1. **STT Transcription**:
   - Runs OpenAI Whisper (`whisper.load_model("base")`) with `word_timestamps=True`, `initial_prompt="Um, uh, so, like, you know, basically..."`, and `condition_on_previous_text=False`.
   - Executed inside a thread pool executor (`asyncio.get_running_loop().run_in_executor`) to prevent event loop blocking.
   - Outputs full text transcript and word-level timestamp array (`{word, start, end, probability}`).
2. **Filler Word Classification**:
   - **ALWAYS_FILLER** (`["um", "uh"]`): Flagged on any match, no exceptions.
   - **CONTEXTUAL_FILLER** (`["like", "actually", "basically", "you know"]`): Evaluated via `classify_filler_context()` and spaCy POS-tagging (`en_core_web_sm`).
     - *"I like your project"* ➔ `"like"` is tagged as `VERB` ➔ NOT flagged as filler.
     - *"It was, like, really good"* ➔ `"like"` is set off by commas / discourse marker ➔ Flagged as filler with start timestamp.
3. **Speaking Speed (WPM)**:
   - Overall WPM calculated based on actual speech duration (excluding long silences).
   - Rolling WPM calculated over 15-second sliding windows (stepping by 5s) to track speed fluctuations over time.
4. **Long Pause Detection**:
   - Identifies gaps between consecutive spoken words $\ge 2.0$ seconds.
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
- **OpenAI Whisper & PyTorch**: `pip install openai-whisper torch spacy`
- **spaCy English Model**: `python -m spacy download en_core_web_sm`

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

## Environment Setup & MongoDB Configuration

Create a `.env` file in the `backend` root with your own `MONGODB_URI` — see `.env.example` for the format. **Never commit your `.env` file.**

```env
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-url>/?appName=<app>
MONGODB_DB_NAME=smartspeak
```

---

## Visual Analysis Pipeline (`/backend/app/services/visual_analyzer.py`)

1. **Eye Contact & Head Pose (5 FPS Raw Video Pass)**:
   - OpenCV decodes raw video at 5 FPS on demand without storing frames to disk.
   - MediaPipe Face Mesh (`refine_landmarks=True`) estimates gaze vector & SolvePnP 3D head pose angles.
   - Classifies frames into `eye_contact`, `looking_away`, or `looking_down`.
2. **Head Movement Analysis**:
   - Reuses head pose angles from 5 FPS pass to measure angular velocity/deltas without extra model passes.
3. **Posture Analysis (1 FPS Frame Pass)**:
   - MediaPipe Pose evaluates shoulder tilt ($\le 10.0^\circ$) and spine alignment ($\le 15.0^\circ$).
4. **Hand Gesture Analysis (1 FPS Frame Pass)**:
   - MediaPipe Hands tracks active hand presence percentage (`too_few`, `average`, `too_many`).

---

## MediaPipe Installation & Performance

```bash
pip install mediapipe opencv-python-headless
```

### Expected Visual Analysis Processing Time
| Video Length | Device | Expected Visual Analysis Time |
| :--- | :--- | :--- |
| **1 Minute** | CPU | 3 – 6 seconds |
| **1 Minute** | NVIDIA GPU (CUDA) | 1 – 2 seconds |
| **5 Minutes** | CPU | 15 – 25 seconds |
| **5 Minutes** | NVIDIA GPU (CUDA) | 5 – 10 seconds |

---

## API Reference

### 1. GET Session Speech Analysis
- **URL**: `GET /api/v1/sessions/{session_id}/speech-analysis`
- **Response**: JSON containing transcript, filler words, WPM metrics, pauses, repetitions.

### 2. GET Session Visual Analysis
- **URL**: `GET /api/v1/sessions/{session_id}/visual-analysis`
- **Response**: JSON containing eye contact percentage, looking away ranges, posture score, poor posture ranges, gesture frequency, and head movement metrics.

