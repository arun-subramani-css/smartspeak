import pytest
import math
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from app.main import app
from app.db.database import Database
from app.models.session import SessionStatus
from app.services.visual_analyzer import (
    analyze_posture_and_gestures_sync,
    dist_2d,
    get_head_direction,
    get_arm_position,
    get_posture_class,
    _get_confidence_model,
)

class MockLandmark:
    def __init__(self, x, y, visibility=1.0):
        self.x = x
        self.y = y
        self.visibility = visibility

def test_feature_derivation_confident():
    # Setup landmarks for confident posture: open arms, upright shoulders, looking straight
    landmarks = [None] * 33
    landmarks[0] = MockLandmark(0.5, 0.2)      # nose
    landmarks[2] = MockLandmark(0.44, 0.18)    # l_eye
    landmarks[5] = MockLandmark(0.56, 0.18)    # r_eye
    landmarks[11] = MockLandmark(0.3, 0.4)     # l_shoulder
    landmarks[12] = MockLandmark(0.7, 0.4)     # r_shoulder
    landmarks[15] = MockLandmark(0.1, 0.6)     # l_wrist (open arms)
    landmarks[16] = MockLandmark(0.9, 0.6)     # r_wrist (open arms)
    landmarks[23] = MockLandmark(0.3, 0.8)     # l_hip
    landmarks[24] = MockLandmark(0.7, 0.8)     # r_hip

    # Derive features manually
    sh_span = dist_2d(landmarks[11], landmarks[12])
    sh_y_diff = abs(landmarks[11].y - landmarks[12].y)
    wrist_dist_x = abs(landmarks[15].x - landmarks[16].x)
    wrist_sh_ratio = wrist_dist_x / sh_span
    nose_offset_x = landmarks[0].x - (landmarks[2].x + landmarks[5].x) / 2.0
    eye_dist = dist_2d(landmarks[2], landmarks[5])
    eye_dist_ratio = eye_dist / sh_span
    h_tilt = math.atan2(landmarks[5].y - landmarks[2].y, landmarks[5].x - landmarks[2].x) * 180.0 / math.pi

    # Categorical classification asserts
    head_dir = get_head_direction(nose_offset_x, eye_dist_ratio, h_tilt)
    arm_pos = get_arm_position(wrist_sh_ratio, wrist_dist_x, sh_y_diff)
    posture_cls = get_posture_class(sh_y_diff)

    assert head_dir == "Looking Straight"
    assert arm_pos == "Open Arms"
    assert posture_cls == "Upright"

    # Test prediction through cached model pipeline
    model = _get_confidence_model()
    assert model is not None, "Confidence model must be trained and cached."

    # Pack into expected dictionary
    frame_features = {
        'eye_shoulder_y_ratio': ((landmarks[2].y + landmarks[5].y) / 2.0 - (landmarks[11].y + landmarks[12].y) / 2.0) / sh_span,
        'shoulder_y_diff': sh_y_diff,
        'wrist_distance_x': wrist_dist_x,
        'wrist_shoulder_ratio': wrist_sh_ratio,
        'nose_eye_center_offset_x': nose_offset_x,
        'shoulder_span': sh_span,
        'hip_shoulder_y_diff': ((landmarks[23].y + landmarks[24].y) / 2.0 - (landmarks[11].y + landmarks[12].y) / 2.0) / sh_span,
        'body_lean_x': 0.0,
        'shoulder_center_x': 0.5,
        'hip_center_x': 0.5,
        'spine_angle': 90.0,
        'eye_distance': eye_dist,
        'head_tilt_angle': h_tilt,
        'eye_distance_ratio': eye_dist_ratio,
        'shoulder_slope': sh_y_diff,
        'head_direction': head_dir,
        'arm_position': arm_pos,
        'posture': posture_cls
    }

    import pandas as pd
    df_row = pd.DataFrame([frame_features])
    probs = model.predict_proba(df_row)[0]
    pred_class = model.predict(df_row)[0]

    # Target classes: 0 = Low, 1 = Neutral, 2 = Confident
    # Confident sample should predict Confident class (2) or lean heavily towards Confident/Neutral
    assert probs[2] > probs[0], "Confident posture should have higher probability for Confident than Low."


def test_feature_derivation_low():
    # Setup landmarks for low confidence posture: crossed arms close together, asymmetric shoulders, tilted head
    landmarks = [None] * 33
    landmarks[0] = MockLandmark(0.53, 0.22)     # nose (shifted)
    landmarks[2] = MockLandmark(0.48, 0.20)     # l_eye
    landmarks[5] = MockLandmark(0.58, 0.20)     # r_eye
    landmarks[11] = MockLandmark(0.32, 0.42)    # l_shoulder
    landmarks[12] = MockLandmark(0.68, 0.38)    # r_shoulder (right higher)
    landmarks[15] = MockLandmark(0.48, 0.55)    # l_wrist (crossed/closed arms)
    landmarks[16] = MockLandmark(0.52, 0.55)    # r_wrist (crossed/closed arms)
    landmarks[23] = MockLandmark(0.3, 0.8)      # l_hip
    landmarks[24] = MockLandmark(0.7, 0.8)      # r_hip

    # Derive features manually
    sh_span = dist_2d(landmarks[11], landmarks[12])
    sh_y_diff = abs(landmarks[11].y - landmarks[12].y)
    wrist_dist_x = abs(landmarks[15].x - landmarks[16].x)
    wrist_sh_ratio = wrist_dist_x / sh_span
    nose_offset_x = landmarks[0].x - (landmarks[2].x + landmarks[5].x) / 2.0
    eye_dist = dist_2d(landmarks[2], landmarks[5])
    eye_dist_ratio = eye_dist / sh_span
    h_tilt = math.atan2(landmarks[5].y - landmarks[2].y, landmarks[5].x - landmarks[2].x) * 180.0 / math.pi

    # Categorical classification asserts
    arm_pos = get_arm_position(wrist_sh_ratio, wrist_dist_x, sh_y_diff)
    posture_cls = get_posture_class(sh_y_diff)

    assert arm_pos == "Closed Arms"
    assert posture_cls == "Stiff"

    # Test prediction
    model = _get_confidence_model()
    assert model is not None

    frame_features = {
        'eye_shoulder_y_ratio': ((landmarks[2].y + landmarks[5].y) / 2.0 - (landmarks[11].y + landmarks[12].y) / 2.0) / sh_span,
        'shoulder_y_diff': sh_y_diff,
        'wrist_distance_x': wrist_dist_x,
        'wrist_shoulder_ratio': wrist_sh_ratio,
        'nose_eye_center_offset_x': nose_offset_x,
        'shoulder_span': sh_span,
        'hip_shoulder_y_diff': ((landmarks[23].y + landmarks[24].y) / 2.0 - (landmarks[11].y + landmarks[12].y) / 2.0) / sh_span,
        'body_lean_x': 0.0,
        'shoulder_center_x': 0.5,
        'hip_center_x': 0.5,
        'spine_angle': 90.0,
        'eye_distance': eye_dist,
        'head_tilt_angle': h_tilt,
        'eye_distance_ratio': eye_dist_ratio,
        'shoulder_slope': sh_y_diff,
        'head_direction': 'Looking Straight',
        'arm_position': arm_pos,
        'posture': posture_cls
    }

    import pandas as pd
    df_row = pd.DataFrame([frame_features])
    probs = model.predict_proba(df_row)[0]

    # Target classes: 0 = Low, 1 = Neutral, 2 = Confident
    # Low confidence sample should have a higher probability for Low/Neutral than Confident
    assert probs[0] > probs[2], "Low confidence posture should have higher probability for Low than Confident."


# MongoDB Mocking for Endpoint Testing
class MockMongoDBCollection:
    def __init__(self):
        self.sessions = {}

    async def find_one(self, query):
        session_id = query.get("session_id")
        return self.sessions.get(session_id)

    async def insert_one(self, doc):
        session_id = doc.get("session_id")
        self.sessions[session_id] = doc

@pytest.fixture
def mock_mongodb(monkeypatch):
    mock_col = MockMongoDBCollection()
    monkeypatch.setattr(Database, "get_collection", lambda name="sessions": mock_col)
    return mock_col

def test_get_confidence_analysis_endpoint(mock_mongodb):
    client = TestClient(app)
    session_id = "test-session-xyz"
    
    # Save a mock session with confidence analysis result in the DB
    mock_doc = {
        "session_id": session_id,
        "original_filename": "speech.mp4",
        "upload_timestamp": datetime.now(timezone.utc).isoformat(),
        "file_size": 2048,
        "content_type": "video/mp4",
        "status": SessionStatus.VISUAL_ANALYSIS_COMPLETE,
        "confidence_analysis": {
            "confidence_score": 85.5,
            "label_distribution": "75% frames Confident, 20% Neutral, 5% Low",
            "frames_analyzed": 100,
            "frames_skipped": 5
        }
    }
    
    # Insert mock document into our fake MongoDB
    import asyncio
    asyncio.run(mock_mongodb.insert_one(mock_doc))

    response = client.get(f"/api/v1/sessions/{session_id}/confidence-analysis")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["status"] == "visual_analysis_complete"
    assert data["confidence_analysis"]["confidence_score"] == 85.5
    assert "Confident" in data["confidence_analysis"]["label_distribution"]
    assert data["confidence_analysis"]["frames_analyzed"] == 100
    assert data["confidence_analysis"]["frames_skipped"] == 5
