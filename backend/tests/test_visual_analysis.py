import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import cv2
import numpy as np
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import Database, get_mongodb_uri
from app.db.mongodb import MongoDB
from app.main import app
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
from app.services.visual_analyzer import (
    analyze_eye_contact_and_head_pose_sync,
    analyze_posture_and_gestures_sync,
    process_visual_analysis_session,
    run_full_visual_analysis_sync,
)
from app.services.speech_analyzer import process_speech_analysis_session


class MockMongoDBCollection:
    def __init__(self):
        self.docs = {}

    async def insert_one(self, doc):
        self.docs[doc["session_id"]] = doc.copy()
        return MagicMock(inserted_id=doc["session_id"])

    async def find_one(self, query):
        session_id = query.get("session_id")
        if not session_id or session_id not in self.docs:
            return None
        doc = self.docs[session_id]

        for key, val in query.items():
            if key == "session_id":
                continue
            if isinstance(val, dict) and "$ne" in val:
                target_ne = val["$ne"]
                if doc.get(key) == target_ne:
                    return None
            elif doc.get(key) != val:
                return None

        return doc.copy()

    async def update_one(self, query, update):
        matched_doc = await self.find_one(query)
        if not matched_doc:
            return MagicMock(modified_count=0)

        session_id = matched_doc["session_id"]
        if "$set" in update:
            self.docs[session_id].update(update["$set"])
        return MagicMock(modified_count=1)


@pytest.fixture(autouse=True)
def mock_mongodb(monkeypatch):
    mock_col = MockMongoDBCollection()
    monkeypatch.setattr(Database, "get_collection", lambda name="sessions": mock_col)
    monkeypatch.setattr(MongoDB, "get_collection", lambda name="sessions": mock_col)
    async def mock_connect():
        pass
    monkeypatch.setattr(Database, "connect", mock_connect)
    # Ensure MONGODB_URI is set for tests
    monkeypatch.setenv("MONGODB_URI", "mongodb://localhost:27017/smartspeak_test")
    return mock_col


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_mongodb_uri_missing_raises_error(monkeypatch):
    monkeypatch.delenv("MONGODB_URI", raising=False)
    monkeypatch.setattr(settings, "MONGODB_URI", None)
    with pytest.raises(ValueError) as exc_info:
        get_mongodb_uri()
    assert "MONGODB_URI environment variable is missing" in str(exc_info.value)


def test_no_face_detected_handles_gracefully(tmp_path):
    # Create a 2-second dummy black video with no face
    video_file = tmp_path / "black.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_file), fourcc, 10.0, (320, 240))
    black_frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for _ in range(20):
        out.write(black_frame)
    out.release()

    eye_contact, head_movement = analyze_eye_contact_and_head_pose_sync(video_file)

    assert isinstance(eye_contact, EyeContactData)
    assert isinstance(head_movement, HeadMovementData)
    assert eye_contact.eye_contact_percentage == 100.0
    assert eye_contact.looking_away_count == 0
    assert head_movement.head_movement_score == 100.0


def test_posture_and_gesture_analysis_on_empty_frames(tmp_path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()

    # Create 3 white image frames
    white_img = np.ones((240, 320, 3), dtype=np.uint8) * 255
    for i in range(1, 4):
        cv2.imwrite(str(frames_dir / f"frame_{i:04d}.jpg"), white_img)

    posture, gesture = analyze_posture_and_gestures_sync(frames_dir)

    assert isinstance(posture, PostureData)
    assert isinstance(gesture, GestureData)
    assert gesture.gesture_usage_classification == "too_few"


@pytest.mark.asyncio
async def test_visual_analysis_pipeline_execution(mock_mongodb, tmp_path, monkeypatch):
    session_id = "test-visual-session-123"
    video_file = settings.staging_dir / f"{session_id}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_file), fourcc, 10.0, (320, 240))
    black_frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for _ in range(20):
        out.write(black_frame)
    out.release()

    frames_dir = settings.processed_dir / session_id / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(frames_dir / "frame_0001.jpg"), black_frame)

    initial_doc = {
        "session_id": session_id,
        "original_filename": "test.mp4",
        "upload_timestamp": datetime.now(timezone.utc),
        "file_size": 1000,
        "content_type": "video/mp4",
        "status": SessionStatus.PROCESSED,
        "file_path": str(video_file)
    }
    await mock_mongodb.insert_one(initial_doc)

    success = await process_visual_analysis_session(session_id)
    assert success is True

    doc = await mock_mongodb.find_one({"session_id": session_id})
    assert doc["status"] == SessionStatus.VISUAL_ANALYSIS_COMPLETE
    assert "visual_analysis" in doc
    assert doc["visual_analysis"]["eye_contact"]["eye_contact_percentage"] == 100.0

    if video_file.exists():
        video_file.unlink()


@pytest.mark.asyncio
async def test_parallel_auto_chaining_reaches_ready_for_fusion(mock_mongodb, monkeypatch):
    """
    Test that simulates both speech analysis and visual analysis completing in parallel.
    Confirms that whichever finishes second triggers the atomic status update to ready_for_fusion.
    """
    session_id = "test-fusion-session-999"

    doc = {
        "session_id": session_id,
        "original_filename": "dual_test.mp4",
        "upload_timestamp": datetime.now(timezone.utc),
        "file_size": 2000,
        "content_type": "video/mp4",
        "status": SessionStatus.PROCESSED,
    }
    await mock_mongodb.insert_one(doc)

    # Mock Whisper transcription for speech analysis
    monkeypatch.setattr(
        "app.services.speech_analyzer.transcribe_audio_sync",
        lambda path, model: ("Hello world test", [])
    )
    # Create fake audio file
    audio_file = settings.processed_dir / session_id / "audio.wav"
    audio_file.parent.mkdir(parents=True, exist_ok=True)
    audio_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

    # Create fake video & frames for visual analysis
    video_file = settings.staging_dir / f"{session_id}.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_file), fourcc, 10.0, (160, 120))
    for _ in range(5):
        out.write(np.zeros((120, 160, 3), dtype=np.uint8))
    out.release()

    frames_dir = settings.processed_dir / session_id / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(frames_dir / "frame_0001.jpg"), np.zeros((120, 160, 3), dtype=np.uint8))

    # Launch both tasks concurrently
    task_speech = asyncio.create_task(process_speech_analysis_session(session_id))
    task_visual = asyncio.create_task(process_visual_analysis_session(session_id))

    res_speech, res_visual = await asyncio.gather(task_speech, task_visual)
    assert res_speech is True
    assert res_visual is True

    final_doc = await mock_mongodb.find_one({"session_id": session_id})
    assert final_doc["status"] == SessionStatus.READY_FOR_FUSION
    assert final_doc["speech_analysis"] is not None
    assert final_doc["visual_analysis"] is not None

    # Cleanup
    if audio_file.exists():
        audio_file.unlink()
    if video_file.exists():
        video_file.unlink()


def test_get_visual_analysis_endpoint(client, mock_mongodb):
    session_id = "endpoint-test-session"
    doc = {
        "session_id": session_id,
        "original_filename": "test.mp4",
        "upload_timestamp": datetime.now(timezone.utc),
        "file_size": 1000,
        "content_type": "video/mp4",
        "status": SessionStatus.VISUAL_ANALYSIS_COMPLETE,
        "visual_analysis": {
            "eye_contact": {
                "eye_contact_percentage": 92.5,
                "looking_away_count": 1,
                "looking_down_count": 0,
                "looking_away_ranges": [
                    {"start_time": 4.0, "end_time": 6.5, "duration": 2.5, "category": "looking_away"}
                ]
            },
            "posture": {
                "posture_score": 88.0,
                "poor_posture_ranges": [],
                "total_frames_analyzed": 10,
                "good_posture_count": 8
            },
            "gesture": {
                "gesture_frequency_count": 4,
                "active_hand_percentage": 40.0,
                "gesture_usage_classification": "average"
            },
            "head_movement": {
                "head_movement_score": 95.0,
                "excessive_movement_timestamps": [12.5],
                "excessive_movement_count": 1
            },
            "analyzed_at": datetime.now(timezone.utc).isoformat()
        }
    }
    asyncio.run(mock_mongodb.insert_one(doc))

    response = client.get(f"/api/v1/sessions/{session_id}/visual-analysis")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["visual_analysis"]["eye_contact"]["eye_contact_percentage"] == 92.5
    assert data["visual_analysis"]["gesture"]["gesture_usage_classification"] == "average"
