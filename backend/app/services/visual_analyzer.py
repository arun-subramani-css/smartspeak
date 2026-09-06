import asyncio
from datetime import datetime, timezone
import logging
import math
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
        model_path = Path("d:/project/smart speak/models/confidence_model.pkl")
        if not model_path.exists():
            model_path = Path(__file__).resolve().parents[3] / "models" / "confidence_model.pkl"
        
        if model_path.exists():
            logger.info(f"Loading Confidence Model from {model_path}...")
            _confidence_model_cache = joblib.load(str(model_path))
        else:
            logger.warning(f"Confidence Model not found at {model_path}. Visual analysis will run without it.")
    return _confidence_model_cache


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


def analyze_eye_contact_and_head_pose_sync(video_path: Path) -> Tuple[EyeContactData, HeadMovementData]:
    """
    Decodes raw video at EYE_CONTACT_SAMPLING_FPS on demand, evaluates eye contact and head pose,
    and returns aggregated EyeContactData and HeadMovementData.
    Reuses head pose angles computed during this 5fps pass for head movement analysis.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.warning(f"Could not open video at {video_path} for eye contact pass.")
        return (
            EyeContactData(eye_contact_percentage=100.0, looking_away_count=0, looking_down_count=0, looking_away_ranges=[]),
            HeadMovementData(head_movement_score=100.0, excessive_movement_timestamps=[], excessive_movement_count=0)
        )

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0

    sampling_fps = settings.EYE_CONTACT_SAMPLING_FPS
    step = max(1, int(round(fps / sampling_fps)))

    has_solutions = hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh")
    face_mesh = None
    face_detection = None
    if has_solutions:
        face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        if hasattr(mp.solutions, "face_detection"):
            face_detection = mp.solutions.face_detection.FaceDetection(
                min_detection_confidence=0.5
            )

    frame_records = []  # (timestamp, category)
    head_pose_list = []  # (timestamp, pitch, yaw, roll)
    face_confidences = []
    fallback_face_count = 0
    no_detection_face_count = 0

    current_frame = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if current_frame % step == 0:
            timestamp = round(current_frame / fps, 2)
            h, w, _ = frame.shape
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            face_found = False

            if face_detection is not None:
                det_results = face_detection.process(rgb_frame)
                if det_results.detections:
                    det_score = float(det_results.detections[0].score[0])
                    
                    if face_mesh is not None:
                        mesh_results = face_mesh.process(rgb_frame)
                        if mesh_results.multi_face_landmarks:
                            face_found = True
                            face_confidences.append(det_score)
                            landmarks = mesh_results.multi_face_landmarks[0].landmark
                            pitch, yaw, roll = _estimate_head_pose_from_landmarks(landmarks, w, h)
                            head_pose_list.append((timestamp, pitch, yaw, roll))

                            if pitch < -12.0:
                                category = "looking_down"
                            elif abs(yaw) > 15.0 or abs(pitch) > 15.0:
                                category = "looking_away"
                            else:
                                category = "eye_contact"

                            frame_records.append((timestamp, category))

            if not face_found:
                # Use OpenCV Face & Eye Cascade fallback
                faces = FACE_CASCADE.detectMultiScale(gray_frame, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
                if len(faces) > 0:
                    face_found = True
                    fallback_face_count += 1
                    (fx, fy, fw, fh) = max(faces, key=lambda b: b[2] * b[3])
                    roi_gray = gray_frame[fy:fy + fh, fx:fx + fw]
                    eyes = EYE_CASCADE.detectMultiScale(roi_gray, scaleFactor=1.1, minNeighbors=3, minSize=(15, 15))

                    # Calculate head orientation estimate from face box center
                    face_center_x = fx + fw / 2.0
                    face_center_y = fy + fh / 2.0
                    yaw_est = (face_center_x - w / 2.0) / (w / 2.0) * 30.0
                    pitch_est = (face_center_y - h / 2.0) / (h / 2.0) * 30.0
                    head_pose_list.append((timestamp, pitch_est, yaw_est, 0.0))

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

                    frame_records.append((timestamp, category))
                else:
                    no_detection_face_count += 1

            # If face not detected (e.g. person turned away completely or out of frame),
            # frame is skipped gracefully without counting as false looking away.

        current_frame += 1

    cap.release()
    if face_mesh is not None:
        face_mesh.close()
    if face_detection is not None:
        face_detection.close()

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

    # --- Head Movement Analysis (Reusing head_pose_list from 5fps pass) ---
    excessive_timestamps: List[float] = []
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


def analyze_posture_and_gestures_sync(frames_dir: Path, confidence_results: list = None) -> Tuple[PostureData, GestureData]:
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

    confidence_scores = []
    predicted_labels = []
    confidence_model = _get_confidence_model()

    for idx, frame_path in enumerate(frame_paths):
        timestamp = float(idx)
        image = cv2.imread(str(frame_path))
        if image is None:
            continue

        h, w, _ = image.shape
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        pose_checked = False

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
                shoulder_tilt = abs(math.atan2(dy, dx) * 180.0 / math.pi)

                shoulder_mid_x = (l_shoulder.x + r_shoulder.x) / 2.0
                shoulder_mid_y = (l_shoulder.y + r_shoulder.y) / 2.0
                hip_mid_x = (l_hip.x + r_hip.x) / 2.0
                hip_mid_y = (l_hip.y + r_hip.y) / 2.0

                spine_dx = shoulder_mid_x - hip_mid_x
                spine_dy = shoulder_mid_y - hip_mid_y
                spine_angle = abs(math.atan2(spine_dx, -spine_dy) * 180.0 / math.pi)

                if shoulder_tilt > shoulder_threshold or spine_angle > spine_threshold:
                    posture_records.append((timestamp, "poor"))
                else:
                    posture_records.append((timestamp, "good"))

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

        # 2. Hand Gesture Evaluation
        hand_checked = False
        if hands_detector is not None:
            hands_res = hands_detector.process(rgb_image)
            if hands_res.multi_hand_landmarks:
                hand_checked = True
                
                # Check if hands are actually moving to qualify as gesturing
                current_landmarks = []
                for hand_landmarks in hands_res.multi_hand_landmarks:
                    for l_idx in [0, 5, 17]:
                        lm = hand_landmarks.landmark[l_idx]
                        current_landmarks.append((lm.x, lm.y, lm.z))
                
                is_moving = False
                if prev_hand_landmarks and len(prev_hand_landmarks) == len(current_landmarks):
                    displacements = [
                        math.sqrt((c[0]-p[0])**2 + (c[1]-p[1])**2 + (c[2]-p[2])**2)
                        for c, p in zip(current_landmarks, prev_hand_landmarks)
                    ]
                    avg_disp = sum(displacements) / len(displacements)
                    if avg_disp > 0.015:  # threshold of ~1.5% screen distance
                        is_moving = True
                else:
                    is_moving = True
                
                prev_hand_landmarks = current_landmarks
                if is_moving:
                    active_hand_frames += 1
                
                # Record Hands detection confidence
                if hands_res.multi_handedness:
                    scores = [h.classification[0].score for h in hands_res.multi_handedness]
                    hand_conf = sum(scores) / len(scores) if scores else 1.0
                else:
                    hand_conf = 1.0
                hand_confidences.append(hand_conf)
            else:
                prev_hand_landmarks = None

        if not hand_checked:
            prev_hand_landmarks = None
            # OpenCV Motion / Hand Activity Fallback between consecutive frames
            fallback_hand_found = False
            if prev_frame_gray is not None:
                diff = cv2.absdiff(gray_image, prev_frame_gray)
                # Increase diff threshold to 35 to reject minor light/sensor fluctuations
                _, thresh = cv2.threshold(diff, 35, 255, cv2.THRESH_BINARY)
                # Count motion pixels in lower 2/3 of frame (torso / hand region)
                lower_roi = thresh[int(h * 0.3):, :]
                motion_count = cv2.countNonZero(lower_roi)
                # Increase motion percentage threshold to 6% of the frame to ignore minor shake
                if motion_count > (w * h * 0.06):
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
    logger.info(f"[{session_id}] Starting Visual Analysis worker...")
    eye_contact, head_movement = analyze_eye_contact_and_head_pose_sync(raw_video_path)
    
    confidence_container = []
    posture, gesture = analyze_posture_and_gestures_sync(frames_dir, confidence_results=confidence_container)

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
