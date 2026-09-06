# SmartSpeak — AI Public Speaking Coach

SmartSpeak is an AI-powered public speaking coach built with FastAPI (backend) and React (frontend).

## Environment Setup & MongoDB Configuration

Create a `.env` file in the `backend` root (or project root) with your own `MONGODB_URI` — see `.env.example` for the format. **Never commit your `.env` file.**

```env
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-url>/?appName=<app>
MONGODB_DB_NAME=smartspeak
```

If `MONGODB_URI` is missing upon backend startup, the server will raise a clear startup error to prevent silent fallbacks or unexpected behavior.

---

## Visual Analysis Module

The Visual Analysis module uses **MediaPipe** (Face Mesh, Pose, Hands) and OpenCV to evaluate non-verbal communication metrics:

1. **Eye Contact Detection & Head Pose**:
   - Decodes the original uploaded video on demand at a configurable sampling rate (default `EYE_CONTACT_SAMPLING_FPS = 5.0`).
   - Runs MediaPipe Face Mesh (`refine_landmarks=True`) to track iris position and estimate 3D head pose angles (pitch, yaw, roll).
   - Classifies frames as `eye_contact`, `looking_away`, or `looking_down`. Continuous looking-away ranges $\ge 2.0$ seconds are timestamped.
   - Non-detected face frames are skipped gracefully.

2. **Head Movement Analysis**:
   - Reuses head pose rotation angles computed during the 5fps Eye Contact pass (no duplicate Face Mesh pass).
   - Detects rapid/excessive head movements exceeding `HEAD_MOVEMENT_ANGLE_THRESHOLD` (15° delta between frames).

3. **Posture Analysis**:
   - Processes Module 2's 1fps extracted frames using MediaPipe Pose.
   - Measures shoulder tilt and spine vertical alignment against configurable thresholds (`POSTURE_SHOULDER_TILT_THRESHOLD = 10.0°`, `POSTURE_SPINE_ANGLE_THRESHOLD = 15.0°`).

4. **Hand Gesture Analysis**:
   - Processes 1fps frames using MediaPipe Hands.
   - Measures active hand usage percentage across frames and classifies gesture frequency as `too_few` (< 15%), `average` (15% - 60%), or `too_many` (> 60%).

---

## MediaPipe Installation & Performance

### Installation
```bash
pip install mediapipe opencv-python-headless
```

### Expected Processing Time (Visual Analysis)
| Video Length | Sampling Rate | Device | Expected Visual Analysis Time |
| :--- | :--- | :--- | :--- |
| **1 Minute** | 5 FPS (Eye/Head) + 1 FPS (Pose/Hands) | CPU | 3 – 6 seconds |
| **1 Minute** | 5 FPS (Eye/Head) + 1 FPS (Pose/Hands) | GPU | 1 – 2 seconds |
| **5 Minutes** | 5 FPS (Eye/Head) + 1 FPS (Pose/Hands) | CPU | 15 – 25 seconds |
| **5 Minutes** | 5 FPS (Eye/Head) + 1 FPS (Pose/Hands) | GPU | 5 – 10 seconds |

---

## API Endpoints

- `GET /api/v1/sessions/{session_id}/status`: Check session processing status. Reaches `ready_for_fusion` once BOTH speech analysis and visual analysis complete.
- `GET /api/v1/sessions/{session_id}/speech-analysis`: Retrieve speech analysis results.
- `GET /api/v1/sessions/{session_id}/visual-analysis`: Retrieve visual analysis results.
