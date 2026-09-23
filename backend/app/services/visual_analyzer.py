import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="google.protobuf")

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import logging
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import cv2
import numpy as np
import mediapipe as mp
import joblib
import pandas as pd

from app.config import settings

_confidence_model_cache = None

def _get_confidence_model():
    global _confidence_model_cache
    if _confidence_model_cache is None:
        model_path = settings.models_dir / "confidence_model.pkl"

        if model_path.exists():
            logger.info(f"Loading Confidence Model from {model_path}...")
            _confidence_model_cache = joblib.load(str(model_path))
        else:
            logger.warning(f"Confidence Model not found at {model_path}. Visual analysis will run without it.")
    return _confidence_model_cache


_posture_model_cache = None


def _get_posture_model():
    """Load the trained posture classifier (sklearn Pipeline, 4 geometric features).

    Trained on human-verified labels (see models/posture_model_report.md) with a
    group-aware split by subject. Expected feature schema (training units):
      shoulder_tilt (deg), spine_angle (deg), shoulder_y_diff (normalized 0-1),
      shoulder_span (px).
    Returns None when unavailable so callers fall back to fixed thresholds.
    """
    global _posture_model_cache
    if _posture_model_cache is None:
        model_path = settings.models_dir / "posture_model.pkl"
        if model_path.exists():
            try:
                logger.info(f"Loading Posture Model from {model_path}...")
                _posture_model_cache = joblib.load(str(model_path))
            except Exception as exc:
                logger.warning(f"Posture Model failed to load ({exc}); using fixed thresholds.")
                _posture_model_cache = False  # sentinel: do not retry every frame
        else:
            logger.warning(f"Posture Model not found at {model_path}; using fixed thresholds.")
            _posture_model_cache = False
    return _posture_model_cache or None


def get_head_direction(nose_offset, eye_dist_ratio, tilt):
    if nose_offset <= 0.03:
        if eye_dist_ratio <= 0.26:
            if nose_offset <= -0.03:
                return 'Looking Right'
            else:
                return 'Center'
        else:
            if nose_offset <= -0.03:
                return 'Looking Right'
            else:
                return 'Looking Straight'
    else:
        if tilt <= 91.45:
            return 'Looking Left'
        else:
            return 'Center'


def get_arm_position(wrist_sh_ratio, wrist_dist_x, sh_slope):
    if wrist_sh_ratio <= 1.50:
        if wrist_sh_ratio <= 1.09:
            return 'Closed Arms'
        else:
            return 'Partially Open'
    else:
        if wrist_sh_ratio <= 1.51:
            if sh_slope <= 0.03:
                return 'Open Arms'
            else:
                return 'Partially Open'
        else:
            return 'Open Arms'


def get_posture_class(sh_y_diff):
    if sh_y_diff <= 0.03:
        return 'Upright'
    elif sh_y_diff <= 0.08:
        return 'Stiff'
    else:
        return 'Slouched'
from app.db.database import Database
from app.models.session import (
    EyeContactData,
    EyeContactRange,
    GestureData,
    HeadMovementData,
    PostureData,
    PostureRange,
    SessionStatus,
    VisualAnalysisResult,
)

logger = logging.getLogger(__name__)

# Load OpenCV cascades for robust fallback face and eye detection
FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
EYE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')


def _estimate_head_pose_from_landmarks(landmarks, img_w: int, img_h: int) -> Tuple[float, float, float]:
    """Estimate pitch, yaw, roll from MediaPipe FaceMesh landmarks."""
    image_points = np.array([
        (landmarks[1].x * img_w, landmarks[1].y * img_h),
        (landmarks[152].x * img_w, landmarks[152].y * img_h),
        (landmarks[33].x * img_w, landmarks[33].y * img_h),
        (landmarks[263].x * img_w, landmarks[263].y * img_h),
        (landmarks[61].x * img_w, landmarks[61].y * img_h),
        (landmarks[291].x * img_w, landmarks[291].y * img_h),
    ], dtype=np.float64)

    model_points = np.array([
        (0.0, 0.0, 0.0),             # Nose tip
        (0.0, -330.0, -65.0),        # Chin
        (-225.0, 170.0, -135.0),     # Left eye corner
        (225.0, 170.0, -135.0),      # Right eye corner
        (-150.0, -150.0, -125.0),    # Left mouth corner
        (150.0, -150.0, -125.0)      # Right mouth corner
    ], dtype=np.float64)

    focal_length = img_w
    center = (img_w / 2, img_h / 2)
    camera_matrix = np.array([
        [focal_length, 0, center[0]],
        [0, focal_length, center[1]],
        [0, 0, 1]
    ], dtype=np.float64)

    dist_coeffs = np.zeros((4, 1), dtype=np.float64)

    success, rotation_vector, translation_vector = cv2.solvePnP(
        model_points, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
    )

    if not success:
        return 0.0, 0.0, 0.0

    rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
    proj_matrix = np.hstack((rotation_matrix, translation_vector))
    euler_angles = cv2.decomposeProjectionMatrix(proj_matrix)[6]

    pitch = float(euler_angles[0][0])
    yaw = float(euler_angles[1][0])
    roll = float(euler_angles[2][0])

    return pitch, yaw, roll


def analyze_eye_contact_and_head_pose_sync(video_path: Path, progress_cb=None) -> Tuple[EyeContactData, HeadMovementData]:
    """
    Decodes raw video at EYE_CONTACT_SAMPLING_FPS on demand, evaluates eye contact and head pose,
    and returns aggregated EyeContactData and HeadMovementData.
    Reuses head pose angles computed during this 5fps pass for head movement analysis.

    Performance: sampled frames are extracted once with the FFmpeg CLI (its
    decoder is several times faster than per-frame OpenCV reads on long
    videos), then MediaPipe inference runs over the extracted JPEGs in
    parallel workers. Falls back to sequential OpenCV decoding if FFmpeg
    extraction fails.
    """
    probe = cv2.VideoCapture(str(video_path))
    if not probe.isOpened():
        logger.warning(f"Could not open video at {video_path} for eye contact pass.")
        return (
            EyeContactData(eye_contact_percentage=100.0, looking_away_count=0, looking_down_count=0, looking_away_ranges=[]),
            HeadMovementData(head_movement_score=100.0, excessive_movement_timestamps=[], excessive_movement_count=0)
        )

    fps = probe.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0
    total_frames = int(probe.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    probe.release()

    sampling_fps = settings.EYE_CONTACT_SAMPLING_FPS
    step = max(1, int(round(fps / sampling_fps)))

    frame_records = []  # (timestamp, category)
    head_pose_list = []  # (timestamp, pitch, yaw, roll)
    face_confidences = []
    fallback_face_count = 0
    no_detection_face_count = 0

    has_solutions = hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh")

    def _make_models():
        """Create private FaceMesh/FaceDetection instances (one set per worker)."""
        face_mesh = None
        face_detection = None
        if has_solutions:
            face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=False,  # head pose needs only the base 468 landmarks
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5
            )
            if hasattr(mp.solutions, "face_detection"):
                face_detection = mp.solutions.face_detection.FaceDetection(
                    min_detection_confidence=0.5
                )
        return face_mesh, face_detection

    def _make_cascades():
        """Private Haar cascades per worker (thread-safe detection)."""
        return (
            cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'),
            cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml'),
        )

    def _prepare_frame(frame):
        h, w, _ = frame.shape
        if w > 640:
            scale = 640.0 / float(w)
            pw, ph = 640, int(h * scale)
            proc_frame = cv2.resize(frame, (pw, ph), interpolation=cv2.INTER_AREA)
        else:
            proc_frame = frame
            pw, ph = w, h
        return proc_frame, pw, ph, w, h

    def _analyze_frame(proc_frame, pw, ph, w, h, timestamp, face_mesh, face_detection,
                       face_cascade, eye_cascade, state):
        """Classify one sampled frame; mutates state lists/counters in place."""
        rgb_frame = cv2.cvtColor(proc_frame, cv2.COLOR_BGR2RGB)
        gray_frame = cv2.cvtColor(proc_frame, cv2.COLOR_BGR2GRAY)

        face_found = False

        if face_detection is not None:
            det_results = face_detection.process(rgb_frame)
            if det_results.detections:
                det_score = float(det_results.detections[0].score[0])
                if face_mesh is not None:
                    mesh_results = face_mesh.process(rgb_frame)
                    if mesh_results.multi_face_landmarks:
                        face_found = True
                        state["confidences"].append(det_score)
                        landmarks = mesh_results.multi_face_landmarks[0].landmark
                        pitch, yaw, roll = _estimate_head_pose_from_landmarks(landmarks, pw, ph)
                        state["head_pose"].append((timestamp, pitch, yaw, roll))

                        if pitch < -12.0:
                            category = "looking_down"
                        elif abs(yaw) > 15.0 or abs(pitch) > 15.0:
                            category = "looking_away"
                        else:
                            category = "eye_contact"

                        state["records"].append((timestamp, category))

        if not face_found:
            # Use OpenCV Face & Eye Cascade fallback
            faces = face_cascade.detectMultiScale(gray_frame, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
            if len(faces) > 0:
                face_found = True
                state["fallback"] += 1
                (fx, fy, fw, fh) = max(faces, key=lambda b: b[2] * b[3])
                roi_gray = gray_frame[fy:fy + fh, fx:fx + fw]
                eyes = eye_cascade.detectMultiScale(roi_gray, scaleFactor=1.1, minNeighbors=3, minSize=(15, 15))

                # Calculate head orientation estimate from face box center
                face_center_x = fx + fw / 2.0
                face_center_y = fy + fh / 2.0
                yaw_est = (face_center_x - w / 2.0) / (w / 2.0) * 30.0
                pitch_est = (face_center_y - h / 2.0) / (h / 2.0) * 30.0
                state["head_pose"].append((timestamp, pitch_est, yaw_est, 0.0))

                if len(eyes) == 0:
                    category = "looking_away"
                else:
                    # Check eyes vertical center within face
                    eye_cy = sum(ey + eh / 2 for (ex, ey, ew, eh) in eyes) / len(eyes)
                    if eye_cy > fh * 0.55:
                        category = "looking_down"
                    elif abs(yaw_est) > 18.0 or abs(pitch_est) > 18.0:
                        category = "looking_away"
                    else:
                        category = "eye_contact"

                state["records"].append((timestamp, category))
            else:
                state["no_face"] += 1

            # If face not detected (e.g. person turned away completely or out of frame),
            # frame is skipped gracefully without counting as false looking away.

    def _new_state():
        return {"records": [], "head_pose": [], "confidences": [], "fallback": 0, "no_face": 0}

    def _extract_sampled_frames_ffmpeg():
        """Extract sampled frames with the FFmpeg CLI (much faster than OpenCV decode).

        Returns (samples, temp_dir) where samples is a list of
        (timestamp, jpeg_path) in temporal order, or None on failure.
        """
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            try:
                import imageio_ffmpeg
                ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                ffmpeg = None
        if not ffmpeg:
            return None

        out_dir = video_path.parent / f".eye_frames_{video_path.stem}"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            for old in out_dir.glob("f*.jpg"):
                old.unlink()
        except OSError as exc:
            logger.warning(f"Eye-frame temp dir unavailable: {exc}")
            return None

        # Keep one frame every `step` frames. Output sequence number k maps to
        # source frame index (k-1)*step, matching the OpenCV frame numbering.
        cmd = [
            ffmpeg, "-y", "-loglevel", "error", "-nostdin",
            "-i", str(video_path),
            "-vf", f"select='not(mod(n\\,{step}))'",
            "-vsync", "0",
            "-q:v", "3",
            str(out_dir / "f%06d.jpg"),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=900)
        except Exception as exc:
            logger.warning(f"FFmpeg eye-frame extraction error: {exc}")
            return None
        if res.returncode != 0:
            logger.warning(
                "FFmpeg eye-frame extraction failed: "
                f"{res.stderr.decode(errors='replace')[-300:]}"
            )
            return None

        samples: List[Tuple[float, str]] = []
        for jpg in sorted(out_dir.glob("f*.jpg")):
            m = re.match(r"f(\d+)\.jpg$", jpg.name)
            if m:
                seq = int(m.group(1))
                samples.append((round((seq - 1) * step / fps, 2), str(jpg)))
        if not samples:
            return None
        return samples, out_dir

    def _run_parallel_inference(samples: List[Tuple[float, str]]) -> dict:
        """Run MediaPipe over extracted JPEGs with parallel inference workers."""
        workers = max(1, min(settings.EYE_CONTACT_MAX_WORKERS, os.cpu_count() or 1, len(samples)))

        def work(bucket):
            face_mesh, face_detection = _make_models()
            face_cascade, eye_cascade = _make_cascades()
            acc = _new_state()
            try:
                for timestamp, path in bucket:
                    frame = cv2.imread(path)
                    if frame is None:
                        acc["no_face"] += 1
                        continue
                    proc_frame, pw, ph, w, h = _prepare_frame(frame)
                    _analyze_frame(proc_frame, pw, ph, w, h, timestamp, face_mesh, face_detection,
                                   face_cascade, eye_cascade, acc)
            finally:
                if face_mesh is not None:
                    face_mesh.close()
                if face_detection is not None:
                    face_detection.close()
            return acc

        buckets = [samples[i::workers] for i in range(workers)]
        merged = _new_state()
        done = 0
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="eye-infer") as executor:
            for acc in executor.map(work, buckets):
                merged["records"].extend(acc["records"])
                merged["head_pose"].extend(acc["head_pose"])
                merged["confidences"].extend(acc["confidences"])
                merged["fallback"] += acc["fallback"]
                merged["no_face"] += acc["no_face"]
                done += len(acc["records"]) + acc["no_face"]
                if progress_cb:
                    progress_cb(min(95.0, 100.0 * done / max(1, len(samples))), "running frame inference")

        merged["records"].sort(key=lambda item: item[0])
        merged["head_pose"].sort(key=lambda item: item[0])
        return merged

    def _process_sequential() -> dict:
        """Fallback when the container has no reliable frame metadata: decode the
        whole stream once in a single worker, keeping only sampled frames."""
        state = _new_state()
        face_mesh, face_detection = _make_models()
        face_cascade, eye_cascade = _make_cascades()
        cap = None
        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                return state
            current_frame = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if current_frame % step == 0:
                    timestamp = round(current_frame / fps, 2)
                    proc_frame, pw, ph, w, h = _prepare_frame(frame)
                    _analyze_frame(proc_frame, pw, ph, w, h, timestamp, face_mesh, face_detection,
                                   face_cascade, eye_cascade, state)
                current_frame += 1
        finally:
            if cap is not None:
                cap.release()
            if face_mesh is not None:
                face_mesh.close()
            if face_detection is not None:
                face_detection.close()
        return state

    # Preferred path: FFmpeg fast extraction + parallel MediaPipe inference.
    state = None
    extraction = _extract_sampled_frames_ffmpeg()
    if extraction:
        samples, tmp_dir = extraction
        try:
            state = _run_parallel_inference(samples)
        except Exception as exc:
            logger.warning(f"Parallel eye inference failed; falling back to sequential decode: {exc}")
            state = None
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    if state is None:
        state = _process_sequential()

    frame_records = state["records"]
    head_pose_list = state["head_pose"]
    face_confidences = state["confidences"]
    fallback_face_count = state["fallback"]
    no_detection_face_count = state["no_face"]

    # Baseline-relative eye-contact calibration. Absolute solvePnP head angles
    # are biased by camera placement: a webcam below/above eye level shifts
    # every frame past the absolute cutoffs, so an entire session reads as
    # "looking away" (observed: 0-7% eye contact across ~90 stored sessions).
    # When enabled, head pose is measured as deviation from the speaker's own
    # median pose for this session instead of absolute angles. records and
    # head_pose are appended 1:1 per analyzed frame, so index pairing holds.
    baseline = None
    if settings.EYE_CONTACT_BASELINE_RELATIVE and head_pose_list:
        med_pitch = float(np.median([p for _, p, _, _ in head_pose_list]))
        med_yaw = float(np.median([y for _, _, y, _ in head_pose_list]))
        baseline = {"pitch": med_pitch, "yaw": med_yaw}
        logger.info(
            f"Eye-contact baseline calibration: median pitch={med_pitch:.2f} deg, yaw={med_yaw:.2f} deg "
            f"over {len(head_pose_list)} pose samples."
        )
        recalibrated: List[Tuple[float, str]] = []
        yaw_tol = settings.EYE_CONTACT_YAW_TOLERANCE_DEG
        pitch_tol = settings.EYE_CONTACT_PITCH_DOWN_TOLERANCE_DEG
        for (ts, _old_cat), (_ts2, pitch, yaw, _roll) in zip(frame_records, head_pose_list):
            d_yaw = yaw - baseline["yaw"]
            d_pitch = pitch - baseline["pitch"]
            if d_pitch < -pitch_tol:
                cat = "looking_down"
            elif abs(d_yaw) > yaw_tol or d_pitch > pitch_tol:
                cat = "looking_away"
            else:
                cat = "eye_contact"
            recalibrated.append((ts, cat))
        frame_records = recalibrated

    total_face_frames = len(frame_records)
    if total_face_frames == 0:
        return (
            EyeContactData(
                eye_contact_percentage=100.0,
                looking_away_count=0,
                looking_down_count=0,
                looking_away_ranges=[],
                average_detection_confidence=None,
                fallback_frame_count=fallback_face_count,
                no_detection_frame_count=no_detection_face_count
            ),
            HeadMovementData(head_movement_score=100.0, excessive_movement_timestamps=[], excessive_movement_count=0)
        )

    eye_contact_count = sum(1 for _, cat in frame_records if cat == "eye_contact")
    eye_contact_pct = round((eye_contact_count / total_face_frames) * 100.0, 2)

    # Aggregate continuous looking_away / looking_down ranges >= min duration (2.0s)
    looking_away_ranges: List[EyeContactRange] = []
    looking_down_count = 0
    min_duration = settings.LOOKING_AWAY_MIN_DURATION_SECONDS

    range_start: Optional[float] = None
    last_ts: float = 0.0
    current_cat: Optional[str] = None

    for ts, cat in frame_records:
        if cat in ("looking_away", "looking_down"):
            if range_start is None:
                range_start = ts
                current_cat = cat
            elif cat == "looking_down":
                current_cat = "looking_down"
            last_ts = ts
        else:
            if range_start is not None:
                duration = round(last_ts - range_start + (1.0 / sampling_fps), 2)
                if duration >= min_duration:
                    cat_val = current_cat or "looking_away"
                    looking_away_ranges.append(
                        EyeContactRange(start_time=range_start, end_time=last_ts, duration=duration, category=cat_val)
                    )
                    if cat_val == "looking_down":
                        looking_down_count += 1
                range_start = None
                current_cat = None

    if range_start is not None:
        duration = round(last_ts - range_start + (1.0 / sampling_fps), 2)
        if duration >= min_duration:
            cat_val = current_cat or "looking_away"
            looking_away_ranges.append(
                EyeContactRange(start_time=range_start, end_time=last_ts, duration=duration, category=cat_val)
            )
            if cat_val == "looking_down":
                looking_down_count += 1

    avg_face_confidence = round(sum(face_confidences) / len(face_confidences), 4) if face_confidences else None

    eye_contact_data = EyeContactData(
        eye_contact_percentage=eye_contact_pct,
        looking_away_count=len(looking_away_ranges),
        looking_down_count=looking_down_count,
        looking_away_ranges=looking_away_ranges,
        average_detection_confidence=avg_face_confidence,
        fallback_frame_count=fallback_face_count,
        no_detection_frame_count=no_detection_face_count
    )

    # --- Head Movement Analysis (Reusing head_pose_list from 2.5fps pass) ---
    # Raw per-sample angle deltas over-flag natural motion at 2.5 fps sampling
    # (any glance between samples looks like a >15 deg jump). When velocity
    # mode is enabled, the pose series is median-smoothed to remove landmark
    # jitter and triggers are based on angular velocity (deg/second).
    excessive_timestamps: List[float] = []

    if head_pose_list and settings.HEAD_MOVEMENT_USE_VELOCITY:
        window = max(1, settings.HEAD_MOVEMENT_SMOOTHING_WINDOW)

        def _median_smooth(values: List[float]) -> List[float]:
            half = window // 2
            out = []
            for i in range(len(values)):
                lo, hi = max(0, i - half), min(len(values), i + half + 1)
                out.append(float(np.median(values[lo:hi])))
            return out

        sm_p = _median_smooth([p for _, p, _, _ in head_pose_list])
        sm_y = _median_smooth([y for _, _, y, _ in head_pose_list])
        sm_r = _median_smooth([r for _, _, _, r in head_pose_list])
        vel_threshold = settings.HEAD_MOVEMENT_VELOCITY_THRESHOLD_DEG_S

        for i in range(1, len(head_pose_list)):
            ts_i, ts_prev = head_pose_list[i][0], head_pose_list[i - 1][0]
            dt = max(1e-6, ts_i - ts_prev)
            delta_angle = math.sqrt(
                (sm_p[i] - sm_p[i - 1]) ** 2
                + (sm_y[i] - sm_y[i - 1]) ** 2
                + (sm_r[i] - sm_r[i - 1]) ** 2
            )
            if (delta_angle / dt) > vel_threshold:
                excessive_timestamps.append(ts_i)
    else:
        head_threshold = settings.HEAD_MOVEMENT_ANGLE_THRESHOLD
        for i in range(1, len(head_pose_list)):
            ts, p2, y2, r2 = head_pose_list[i]
            _, p1, y1, r1 = head_pose_list[i - 1]
            delta_angle = math.sqrt((p2 - p1) ** 2 + (y2 - y1) ** 2 + (r2 - r1) ** 2)

            if delta_angle > head_threshold:
                excessive_timestamps.append(ts)

    total_pose_frames = len(head_pose_list)
    excessive_count = len(excessive_timestamps)

    if total_pose_frames > 0:
        head_score = max(0.0, round(100.0 - (excessive_count / total_pose_frames) * 100.0, 2))
    else:
        head_score = 100.0

    head_movement_data = HeadMovementData(
        head_movement_score=head_score,
        excessive_movement_timestamps=excessive_timestamps,
        excessive_movement_count=excessive_count
    )

    return eye_contact_data, head_movement_data


def dist_2d(p1, p2):
    return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)


def analyze_posture_and_gestures_sync(frames_dir: Path, confidence_results: list = None, progress_cb=None) -> Tuple[PostureData, GestureData]:
    """
    Runs MediaPipe Pose / Hands (or vision posture/hand fallback) on the 1fps extracted frames.
    """
    frame_paths = sorted(list(frames_dir.glob("frame_*.jpg")))
    total_frames = len(frame_paths)

    if total_frames == 0:
        return (
            PostureData(
                posture_score=100.0,
                poor_posture_ranges=[],
                total_frames_analyzed=0,
                good_posture_count=0,
                average_detection_confidence=None,
                fallback_frame_count=0,
                no_detection_frame_count=0
            ),
            GestureData(
                gesture_frequency_count=0,
                active_hand_percentage=0.0,
                gesture_usage_classification="too_few",
                average_detection_confidence=None,
                fallback_frame_count=0,
                no_detection_frame_count=0
            )
        )

    has_solutions = hasattr(mp, "solutions")
    pose_detector = mp.solutions.pose.Pose(static_image_mode=True, min_detection_confidence=0.5) if (has_solutions and hasattr(mp.solutions, "pose")) else None
    hands_detector = mp.solutions.hands.Hands(static_image_mode=True, max_num_hands=2, min_detection_confidence=0.5) if (has_solutions and hasattr(mp.solutions, "hands")) else None

    posture_records = []  # (timestamp, "good" | "poor")
    active_hand_frames = 0

    shoulder_threshold = settings.POSTURE_SHOULDER_TILT_THRESHOLD
    spine_threshold = settings.POSTURE_SPINE_ANGLE_THRESHOLD
    min_duration = settings.LOOKING_AWAY_MIN_DURATION_SECONDS

    prev_frame_gray: Optional[np.ndarray] = None

    pose_confidences = []
    fallback_pose_count = 0
    no_detection_pose_count = 0

    hand_confidences = []
    fallback_hand_count = 0
    no_detection_hand_count = 0
    prev_hand_landmarks = None
    prev_l_rel = None
    prev_r_rel = None
    prev_hands_centroids = {}

    confidence_scores = []
    predicted_labels = []
    confidence_model = _get_confidence_model()
    posture_model = _get_posture_model() if settings.POSTURE_USE_MODEL else None

    for idx, frame_path in enumerate(frame_paths):
        timestamp = float(idx)
        image = cv2.imread(str(frame_path))
        if image is None:
            continue

        h, w, _ = image.shape
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        pose_checked = False
        pose_res = None
        faces = None

        # 1. Posture Evaluation
        if pose_detector is not None:
            pose_res = pose_detector.process(rgb_image)
            if pose_res.pose_landmarks:
                pose_checked = True
                landmarks = pose_res.pose_landmarks.landmark
                
                # --- Confidence Model Feature Extraction ---
                if confidence_model is not None:
                    try:
                        nose_lm = landmarks[0]
                        l_eye_lm = landmarks[2]
                        r_eye_lm = landmarks[5]
                        l_shoulder_lm = landmarks[11]
                        r_shoulder_lm = landmarks[12]
                        l_wrist_lm = landmarks[15]
                        r_wrist_lm = landmarks[16]
                        l_hip_lm = landmarks[23]
                        r_hip_lm = landmarks[24]

                        sh_span = dist_2d(l_shoulder_lm, r_shoulder_lm)
                        
                        if sh_span > 0:
                            eye_y_avg = (l_eye_lm.y + r_eye_lm.y) / 2.0
                            sh_y_avg = (l_shoulder_lm.y + r_shoulder_lm.y) / 2.0
                            eye_sh_y_ratio = (eye_y_avg - sh_y_avg) / sh_span
                            
                            sh_y_diff = abs(l_shoulder_lm.y - r_shoulder_lm.y)
                            wrist_dist_x = abs(l_wrist_lm.x - r_wrist_lm.x)
                            wrist_sh_ratio = wrist_dist_x / sh_span
                            nose_offset_x = nose_lm.x - (l_eye_lm.x + r_eye_lm.x) / 2.0
                            
                            hip_y_avg = (l_hip_lm.y + r_hip_lm.y) / 2.0
                            hip_sh_y_diff = (hip_y_avg - sh_y_avg) / sh_span
                            
                            sh_center_x = (l_shoulder_lm.x + r_shoulder_lm.x) / 2.0
                            h_center_x = (l_hip_lm.x + r_hip_lm.x) / 2.0
                            body_lean = sh_center_x - h_center_x
                            
                            sp_angle = math.atan2(hip_y_avg - sh_y_avg, sh_center_x - h_center_x) * 180.0 / math.pi
                            eye_dist = dist_2d(l_eye_lm, r_eye_lm)
                            h_tilt = math.atan2(r_eye_lm.y - l_eye_lm.y, r_eye_lm.x - l_eye_lm.x) * 180.0 / math.pi
                            eye_dist_ratio = eye_dist / sh_span
                            sh_slope = sh_y_diff

                            # Derive categorical features
                            head_dir = get_head_direction(nose_offset_x, eye_dist_ratio, h_tilt)
                            arm_pos = get_arm_position(wrist_sh_ratio, wrist_dist_x, sh_slope)
                            confidence_model_posture_class = get_posture_class(sh_y_diff)

                            frame_features = {
                                'eye_shoulder_y_ratio': eye_sh_y_ratio,
                                'shoulder_y_diff': sh_y_diff,
                                'wrist_distance_x': wrist_dist_x,
                                'wrist_shoulder_ratio': wrist_sh_ratio,
                                'nose_eye_center_offset_x': nose_offset_x,
                                'shoulder_span': sh_span,
                                'hip_shoulder_y_diff': hip_sh_y_diff,
                                'body_lean_x': body_lean,
                                'shoulder_center_x': sh_center_x,
                                'hip_center_x': h_center_x,
                                'spine_angle': sp_angle,
                                'eye_distance': eye_dist,
                                'head_tilt_angle': h_tilt,
                                'eye_distance_ratio': eye_dist_ratio,
                                'shoulder_slope': sh_slope,
                                'head_direction': head_dir,
                                'arm_position': arm_pos,
                                'posture': confidence_model_posture_class
                            }

                            df_row = pd.DataFrame([frame_features])
                            probs = confidence_model.predict_proba(df_row)[0]
                            f_score = probs[2] * 100.0 + probs[1] * 50.0
                            confidence_scores.append(f_score)
                            
                            class_names = ['Low', 'Neutral', 'Confident']
                            pred_label = class_names[np.argmax(probs)]
                            predicted_labels.append(pred_label)
                    except Exception as e:
                        logger.warning(f"Error running confidence prediction for frame {idx}: {e}")

                # Record Pose landmark visibility
                visibilities = [lm.visibility for lm in landmarks]
                pose_conf = sum(visibilities) / len(visibilities) if visibilities else 0.0
                pose_confidences.append(pose_conf)

                l_shoulder = landmarks[mp.solutions.pose.PoseLandmark.LEFT_SHOULDER]
                r_shoulder = landmarks[mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER]
                l_hip = landmarks[mp.solutions.pose.PoseLandmark.LEFT_HIP]
                r_hip = landmarks[mp.solutions.pose.PoseLandmark.RIGHT_HIP]

                dx = r_shoulder.x - l_shoulder.x
                dy = r_shoulder.y - l_shoulder.y
                shoulder_tilt = abs(math.atan2(dy, abs(dx)) * 180.0 / math.pi)

                shoulder_mid_x = (l_shoulder.x + r_shoulder.x) / 2.0
                shoulder_mid_y = (l_shoulder.y + r_shoulder.y) / 2.0
                hip_mid_x = (l_hip.x + r_hip.x) / 2.0
                hip_mid_y = (l_hip.y + r_hip.y) / 2.0

                spine_dx = shoulder_mid_x - hip_mid_x
                spine_dy = shoulder_mid_y - hip_mid_y
                spine_angle = abs(math.atan2(spine_dx, -spine_dy) * 180.0 / math.pi)

                # Trained posture classifier (human-verified labels) replaces the
                # brittle fixed thresholds when available; falls back to them on
                # any prediction failure.
                posture_verdict = None
                if posture_model is not None:
                    try:
                        sh_y_diff_model = abs(l_shoulder.y - r_shoulder.y)
                        span_px = math.hypot(
                            (r_shoulder.x - l_shoulder.x) * w,
                            (r_shoulder.y - l_shoulder.y) * h,
                        )
                        posture_row = pd.DataFrame([{
                            "shoulder_tilt": shoulder_tilt,
                            "spine_angle": spine_angle,
                            "shoulder_y_diff": sh_y_diff_model,
                            "shoulder_span": span_px,
                        }])
                        pred = int(posture_model.predict(posture_row)[0])
                        # 0 = Poor Posture, 1 = Good Posture, 2 = Best Posture
                        posture_verdict = "poor" if pred == 0 else "good"
                    except Exception as exc:
                        logger.warning(f"Posture model prediction failed on frame {idx}: {exc}")
                        posture_verdict = None
                if posture_verdict is None:
                    posture_verdict = "poor" if (shoulder_tilt > shoulder_threshold or spine_angle > spine_threshold) else "good"
                posture_records.append((timestamp, posture_verdict))

        if not pose_checked:
            # OpenCV Fallback Posture Alignment Check
            faces = FACE_CASCADE.detectMultiScale(gray_image, scaleFactor=1.1, minNeighbors=4)
            if len(faces) > 0:
                fallback_pose_count += 1
                (fx, fy, fw, fh) = max(faces, key=lambda b: b[2] * b[3])
                # Center of head alignment relative to frame width
                head_center_x = fx + fw / 2.0
                tilt_offset = abs(head_center_x - w / 2.0) / (w / 2.0) * 100.0

                if tilt_offset > spine_threshold:
                    posture_records.append((timestamp, "poor"))
                else:
                    posture_records.append((timestamp, "good"))
            else:
                no_detection_pose_count += 1

        # 2. Hand Gesture & Movement Evaluation (Pose Kinematics + Hands Articulation)
        hand_checked = False
        is_gesturing = False
        hand_motion_detected = False

        # Run MediaPipe Hands if initialized
        hands_res = None
        if hands_detector is not None:
            hands_res = hands_detector.process(rgb_image)
            if hands_res and hands_res.multi_hand_landmarks:
                hand_checked = True
                if hands_res.multi_handedness:
                    scores = [h.classification[0].score for h in hands_res.multi_handedness]
                    hand_conf = sum(scores) / len(scores) if scores else 1.0
                else:
                    hand_conf = 1.0
                hand_confidences.append(hand_conf)

                cur_hands = {}
                for idx, h_lms in enumerate(hands_res.multi_hand_landmarks):
                    label = f"hand_{idx}"
                    if hands_res.multi_handedness and idx < len(hands_res.multi_handedness):
                        c_item = hands_res.multi_handedness[idx].classification[0]
                        label = getattr(c_item, "label", f"hand_{idx}")
                    cx = sum(lm.x for lm in h_lms.landmark) / 21.0
                    cy = sum(lm.y for lm in h_lms.landmark) / 21.0
                    cur_hands[label] = (cx, cy)
                    if label in prev_hands_centroids:
                        pcx, pcy = prev_hands_centroids[label]
                        disp = math.hypot(cx - pcx, cy - pcy)
                        if disp >= 0.04:
                            hand_motion_detected = True
                prev_hands_centroids = cur_hands
            else:
                prev_hands_centroids = {}

        # Primary source: Pose Arm Kinematics
        if pose_res and pose_res.pose_landmarks:
            lm = pose_res.pose_landmarks.landmark
            l_w, r_w = lm[15], lm[16]  # Wrists
            l_s, r_s = lm[11], lm[12]  # Shoulders
            l_h, r_h = lm[23], lm[24]  # Hips

            # Scale normalization via shoulder span
            sh_span = math.hypot(l_s.x - r_s.x, l_s.y - r_s.y)
            if sh_span < 0.03:
                sh_span = 0.2

            sh_y = (l_s.y + r_s.y) / 2.0

            # Hip level reference line vs seated/webcam framing
            if l_h.visibility > 0.3 and r_h.visibility > 0.3:
                hip_y = (l_h.y + r_h.y) / 2.0
                in_webcam_mode = False
            else:
                # Seated or close webcam framing where hips are not visible
                hip_y = sh_y + 1.2 * sh_span
                in_webcam_mode = True

            desk_y = sh_y + 0.65 * sh_span if in_webcam_mode else hip_y

            # Hand elevation: active gesture zone is above hip/desk line
            l_in_zone = (l_w.visibility > 0.25) and (l_w.y < desk_y)
            r_in_zone = (r_w.visibility > 0.25) and (r_w.y < desk_y)

            # Torso-relative coordinates normalized by body width
            cur_l_rel = ((l_w.x - l_s.x) / sh_span, (l_w.y - l_s.y) / sh_span) if l_w.visibility > 0.25 else None
            cur_r_rel = ((r_w.x - r_s.x) / sh_span, (r_w.y - r_s.y) / sh_span) if r_w.visibility > 0.25 else None

            # Relative velocity / displacement between frames
            delta_l = math.hypot(cur_l_rel[0] - prev_l_rel[0], cur_l_rel[1] - prev_l_rel[1]) if (cur_l_rel and prev_l_rel) else 0.0
            delta_r = math.hypot(cur_r_rel[0] - prev_r_rel[0], cur_r_rel[1] - prev_r_rel[1]) if (cur_r_rel and prev_r_rel) else 0.0

            # Detect clasped resting hands (both wrists close together near waist)
            wrist_dist = math.hypot(l_w.x - r_w.x, l_w.y - r_w.y) / sh_span if (l_w.visibility > 0.25 and r_w.visibility > 0.25) else 1.0
            is_clasped_low = (wrist_dist < 0.45) and (l_w.y > hip_y - 0.35 * sh_span)

            if not is_clasped_low:
                # Dynamic gesturing in active zone
                if (l_in_zone and delta_l >= 0.12) or (r_in_zone and delta_r >= 0.12):
                    is_gesturing = True
                elif (l_w.visibility > 0.3 and l_w.y < sh_y + 0.35 * sh_span and delta_l >= 0.08):
                    is_gesturing = True
                elif (r_w.visibility > 0.3 and r_w.y < sh_y + 0.35 * sh_span and delta_r >= 0.08):
                    is_gesturing = True
                elif hand_motion_detected and (l_in_zone or r_in_zone):
                    is_gesturing = True

            prev_l_rel = cur_l_rel
            prev_r_rel = cur_r_rel
            hand_checked = True
        else:
            if hand_motion_detected:
                is_gesturing = True
                hand_checked = True
            elif hand_checked:
                # MediaPipe Hands checked hands, but no movement was detected
                pass
            prev_l_rel = None
            prev_r_rel = None

        if is_gesturing:
            active_hand_frames += 1

        if progress_cb and (idx % 25 == 0 or idx == len(frame_paths) - 1):
            progress_cb(min(95.0, 100.0 * (idx + 1) / max(1, len(frame_paths))), f"frame {idx + 1}/{len(frame_paths)}")

        if not hand_checked:
            prev_frame_gray_local = prev_frame_gray
            fallback_hand_found = False

            # If faces was not computed earlier, detect face for torso bounding box
            if faces is None:
                faces = FACE_CASCADE.detectMultiScale(gray_image, scaleFactor=1.1, minNeighbors=4)

            if prev_frame_gray_local is not None and len(faces) > 0:
                (fx, fy, fw, fh) = max(faces, key=lambda b: b[2] * b[3])
                roi_y1 = min(h - 1, fy + fh)
                roi_y2 = min(h, fy + int(3.5 * fh))
                roi_x1 = max(0, fx - int(0.8 * fw))
                roi_x2 = min(w, fx + int(1.8 * fw))
                if roi_y2 > roi_y1 and roi_x2 > roi_x1:
                    diff = cv2.absdiff(gray_image, prev_frame_gray_local)
                    _, thresh = cv2.threshold(diff, 35, 255, cv2.THRESH_BINARY)
                    torso_roi = thresh[roi_y1:roi_y2, roi_x1:roi_x2]
                    roi_area = (roi_y2 - roi_y1) * (roi_x2 - roi_x1)
                    motion_count = cv2.countNonZero(torso_roi)
                    if motion_count > (roi_area * 0.08):
                        active_hand_frames += 1
                        fallback_hand_count += 1
                        fallback_hand_found = True

            if not fallback_hand_found:
                no_detection_hand_count += 1

        prev_frame_gray = gray_image.copy()

    if pose_detector is not None:
        pose_detector.close()
    if hands_detector is not None:
        hands_detector.close()

    # Aggregate Posture Data
    analyzed_pose_count = len(posture_records)
    good_count = sum(1 for _, status in posture_records if status == "good")
    posture_score = round((good_count / analyzed_pose_count) * 100.0, 2) if analyzed_pose_count > 0 else 100.0

    poor_posture_ranges: List[PostureRange] = []
    p_start: Optional[float] = None
    p_last: float = 0.0

    for ts, status in posture_records:
        if status == "poor":
            if p_start is None:
                p_start = ts
            p_last = ts
        else:
            if p_start is not None:
                duration = round(p_last - p_start + 1.0, 2)
                if duration >= min_duration:
                    poor_posture_ranges.append(PostureRange(start_time=p_start, end_time=p_last, duration=duration))
                p_start = None

    if p_start is not None:
        duration = round(p_last - p_start + 1.0, 2)
        if duration >= min_duration:
            poor_posture_ranges.append(PostureRange(start_time=p_start, end_time=p_last, duration=duration))

    avg_pose_confidence = round(sum(pose_confidences) / len(pose_confidences), 4) if pose_confidences else None

    posture_data = PostureData(
        posture_score=posture_score,
        poor_posture_ranges=poor_posture_ranges,
        total_frames_analyzed=analyzed_pose_count,
        good_posture_count=good_count,
        average_detection_confidence=avg_pose_confidence,
        fallback_frame_count=fallback_pose_count,
        no_detection_frame_count=no_detection_pose_count
    )

    # Aggregate Gesture Data
    active_pct = round((active_hand_frames / total_frames) * 100.0, 2)
    if active_pct < settings.GESTURE_TOO_FEW_THRESHOLD_PCT:
        gesture_usage = "too_few"
    elif active_pct > settings.GESTURE_TOO_MANY_THRESHOLD_PCT:
        gesture_usage = "too_many"
    else:
        gesture_usage = "average"

    avg_hand_confidence = round(sum(hand_confidences) / len(hand_confidences), 4) if hand_confidences else None

    gesture_data = GestureData(
        gesture_frequency_count=active_hand_frames,
        active_hand_percentage=active_pct,
        gesture_usage_classification=gesture_usage,
        average_detection_confidence=avg_hand_confidence,
        fallback_frame_count=fallback_hand_count,
        no_detection_frame_count=no_detection_hand_count
    )

    if confidence_results is not None:
        if confidence_scores:
            mean_score = float(np.mean(confidence_scores))
            total_analyzed = len(confidence_scores)
            
            c_confident = predicted_labels.count('Confident')
            c_neutral = predicted_labels.count('Neutral')
            c_low = predicted_labels.count('Low')
            
            conf_pct = (c_confident / total_analyzed) * 100.0
            neut_pct = (c_neutral / total_analyzed) * 100.0
            low_pct = (c_low / total_analyzed) * 100.0
            
            label_dist_str = f"{round(conf_pct)}% frames Confident, {round(neut_pct)}% Neutral, {round(low_pct)}% Low"
            
            confidence_analysis_dict = {
                'confidence_score': round(mean_score, 2),
                'label_distribution': label_dist_str,
                'frames_analyzed': total_analyzed,
                'frames_skipped': no_detection_pose_count
            }
        else:
            confidence_analysis_dict = {
                'confidence_score': 0.0,
                'label_distribution': "0% frames Confident, 0% Neutral, 0% Low",
                'frames_analyzed': 0,
                'frames_skipped': no_detection_pose_count
            }
        confidence_results.append(confidence_analysis_dict)

    return posture_data, gesture_data


def run_full_visual_analysis_sync(session_id: str, raw_video_path: Path, frames_dir: Path) -> Tuple[VisualAnalysisResult, dict]:
    """
    Synchronous worker combining 5fps raw video eye contact & head pose pass
    with 1fps frames posture & hand gesture pass, plus Confidence Model prediction.
    """
    logger.info(f"[{session_id}] Starting Visual Analysis worker (eye-contact and posture passes in parallel)...")

    # The two passes are independent (raw video vs. extracted frames), so run them
    # concurrently. OpenCV decode and MediaPipe inference release the GIL, so this
    # gives a near-2x wall-clock reduction on multi-core machines.
    from app.services import progress as progress_svc
    confidence_container = []

    def _run_posture_pass():
        return analyze_posture_and_gestures_sync(
            frames_dir,
            confidence_results=confidence_container,
            progress_cb=lambda pct, msg: progress_svc.report_progress(session_id, "visual_progress", pct, msg),
        )

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="visual-pass") as executor:
        eye_future = executor.submit(
            analyze_eye_contact_and_head_pose_sync,
            raw_video_path,
            lambda pct, msg: progress_svc.report_progress(session_id, "visual_progress", pct, "eye contact: " + msg),
        )
        posture_future = executor.submit(_run_posture_pass)
        eye_contact, head_movement = eye_future.result()
        posture, gesture = posture_future.result()

    visual_result = VisualAnalysisResult(
        eye_contact=eye_contact,
        posture=posture,
        gesture=gesture,
        head_movement=head_movement,
        analyzed_at=datetime.now(timezone.utc)
    )
    
    confidence_data = confidence_container[0] if confidence_container else {
        'confidence_score': 0.0,
        'label_distribution': "0% frames Confident, 0% Neutral, 0% Low",
        'frames_analyzed': 0,
        'frames_skipped': 0
    }

    return visual_result, confidence_data


async def process_visual_analysis_session(session_id: str) -> bool:
    """
    Background async task to run visual analysis for a session.
    Offloads sync MediaPipe / OpenCV processing to thread pool executor.
    Performs atomic symmetric status update upon completion.
    """
    sessions_col = Database.get_collection("sessions")
    session_doc = await sessions_col.find_one({"session_id": session_id})
    if not session_doc:
        matches = list(settings.staging_dir.glob(f"{session_id}.*"))
        if matches:
            staging_file = matches[0]
            ext = staging_file.suffix
            session_doc = {
                "session_id": session_id,
                "original_filename": f"video{ext}",
                "upload_timestamp": datetime.now(timezone.utc),
                "file_size": staging_file.stat().st_size,
                "content_type": f"video/{ext.lstrip('.')}",
                "status": SessionStatus.PROCESSING,
                "file_path": str(staging_file)
            }
            await sessions_col.insert_one(session_doc)
            logger.info(f"Auto-recovered visual session document in DB for {session_id}")
        else:
            logger.error(f"[{session_id}] Session not found for visual analysis.")
            return False

    raw_video_path = Path(session_doc.get("file_path", ""))
    if not raw_video_path.exists():
        matches = list(settings.staging_dir.glob(f"{session_id}.*"))
        if matches:
            raw_video_path = matches[0]
        else:
            logger.error(f"[{session_id}] Staged video file not found for visual analysis.")
            return False

    frames_dir = settings.processed_dir / session_id / "frames"

    loop = asyncio.get_running_loop()
    try:
        visual_result, confidence_dict = await loop.run_in_executor(
            None, run_full_visual_analysis_sync, session_id, raw_video_path, frames_dir
        )

        visual_dict = visual_result.model_dump(mode="json")

        # Atomic symmetric update: check if speech_analysis is already present in DB
        res = await sessions_col.update_one(
            {
                "session_id": session_id,
                "speech_analysis": {"$ne": None}
            },
            {
                "$set": {
                    "visual_analysis": visual_dict,
                    "confidence_analysis": confidence_dict,
                    "status": SessionStatus.READY_FOR_FUSION
                }
            }
        )

        if res.modified_count == 0:
            # Speech analysis is not completed yet, set status to VISUAL_ANALYSIS_COMPLETE
            await sessions_col.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "visual_analysis": visual_dict,
                        "confidence_analysis": confidence_dict,
                        "status": SessionStatus.VISUAL_ANALYSIS_COMPLETE
                    }
                }
            )

        logger.info(
            f"[{session_id}] Visual analysis successfully saved to database.\n"
            f"  -> Eye Contact Confidence: {visual_result.eye_contact.average_detection_confidence if visual_result.eye_contact.average_detection_confidence is not None else 'N/A'}\n"
            f"  -> Posture Confidence: {visual_result.posture.average_detection_confidence if visual_result.posture.average_detection_confidence is not None else 'N/A'}\n"
            f"  -> Gesture Confidence: {visual_result.gesture.average_detection_confidence if visual_result.gesture.average_detection_confidence is not None else 'N/A'}"
        )
        return True

    except Exception as exc:
        logger.exception(f"[{session_id}] Visual analysis failed: {exc}")
        await sessions_col.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": SessionStatus.FAILED,
                    "error_reason": f"Visual analysis failed: {str(exc)}"
                }
            }
        )
        return False
