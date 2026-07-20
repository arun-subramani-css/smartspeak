# SmartSpeak — Video Upload & Audio/Video Processing Modules

SmartSpeak is an AI-powered public speaking coach. This repository contains **Module 1 (Video Upload)** and **Module 2 (Audio & Video Processing)**.

---

## Architecture Overview

1. **Module 1 (Video Upload)**:
   - FastAPI endpoint `POST /api/v1/upload` accepting `.mp4`, `.avi`, `.mov`.
   - Validates file size (configurable max 500MB, returns HTTP 413 if exceeded).
   - Validates both file extension and binary container MIME signature.
   - Saves uploaded video to a staging directory using a generated UUID as filename.
   - Stores session metadata (`session_id`, `original_filename`, `upload_timestamp`, `file_size`, `content_type`, `status`) in MongoDB `sessions` collection.

2. **Module 2 (Audio & Video Processing)**:
   - Async background video processing pipeline.
   - Extracts audio track as **16kHz mono WAV** file (`/processed/{session_id}/audio.wav`) using FFmpeg.
   - Samples video frames at **1 frame per second** using OpenCV (`/processed/{session_id}/frames/frame_0001.jpg`, `frame_0002.jpg`, etc.).
   - Updates session status in MongoDB (`uploaded` ➔ `processing` ➔ `processed` / `failed`).
   - Endpoint `GET /api/v1/sessions/{session_id}/status` returning processing state and metrics.

3. **Data Retention**:
   - Built-in background cleanup scheduler (APScheduler) purging 30-day-old session records and associated staging/processed files from disk.

---

## Prerequisites

- **Python**: 3.11 or higher
- **Node.js**: 18.x or higher
- **MongoDB**: Local MongoDB instance (`mongodb://localhost:27017`) or Docker MongoDB service.
- **FFmpeg**: System binary installed and accessible on system `PATH`.

---

## Installing FFmpeg

FFmpeg is required for extracting the 16kHz mono audio track from uploaded videos.

### Windows
```cmd
winget install FFmpeg.FFmpeg
```
*Or download from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) and add the `bin` folder to your System PATH.*

### macOS
```bash
brew install ffmpeg
```

### Linux (Ubuntu/Debian)
```bash
sudo apt update && sudo apt install -y ffmpeg
```

*Verify installation:*
```bash
ffmpeg -version
```

---

## Local Environment Setup & Run Instructions

### 1. Environment Configuration
Copy `.env.example` in `/backend` to `.env`:
```bash
cd backend
cp .env.example .env
```

Default configuration variables:
```env
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=smartspeak
STORAGE_DIR=./data
MAX_UPLOAD_SIZE_MB=500
FRAME_SAMPLE_RATE_FPS=1.0
RETENTION_DAYS=30
CLEANUP_INTERVAL_HOURS=24
PORT=8000
HOST=0.0.0.0
```

---

### 2. Backend Setup & Running

```bash
cd backend

# Create Python virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI dev server
uvicorn app.main:app --reload --port 8000
```

The FastAPI backend will run at `http://localhost:8000`. Interactive API docs (Swagger UI) are available at `http://localhost:8000/docs`.

---

### 3. Frontend Setup & Running

```bash
cd frontend

# Install Node dependencies
npm install

# Start Vite dev server
npm run dev
```

The React frontend will be available at `http://localhost:5173`.

---

## API Reference

### 1. Video Upload
- **URL**: `POST /api/v1/upload`
- **Content-Type**: `multipart/form-data`
- **Field Name**: `video`
- **Allowed Formats**: `.mp4`, `.avi`, `.mov`
- **Max File Size**: 500MB (HTTP 413 if exceeded)

#### Example Request (`curl`)
```bash
curl -X POST "http://localhost:8000/api/v1/upload" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "video=@/path/to/presentation.mp4"
```

#### Example Response (201 Created)
```json
{
  "session_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "status": "uploaded",
  "message": "Video uploaded successfully. Processing started.",
  "original_filename": "presentation.mp4",
  "file_size": 15482910,
  "upload_timestamp": "2026-07-20T20:40:00.000Z"
}
```

---

### 2. Session Status Check
- **URL**: `GET /api/v1/sessions/{session_id}/status`

#### Example Response (Processed State)
```json
{
  "session_id": "c9bf9e57-1685-4c89-bafb-ff5af830be8a",
  "status": "processed",
  "original_filename": "presentation.mp4",
  "upload_timestamp": "2026-07-20T20:40:00.000Z",
  "file_size": 15482910,
  "content_type": "video/mp4",
  "error_reason": null,
  "processed_at": "2026-07-20T20:40:05.000Z",
  "audio_path": "processed/c9bf9e57-1685-4c89-bafb-ff5af830be8a/audio.wav",
  "frame_count": 30
}
```

---

## Unit & Integration Testing

To run the automated backend test suite:

```bash
cd backend
pytest -v
```
