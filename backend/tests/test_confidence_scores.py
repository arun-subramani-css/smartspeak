import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from datetime import datetime, timezone
import cv2
import numpy as np

# Import mediapipe globally
import mediapipe as mp

from app.models.session import (
    WordTimestamp,
    SessionStatus,
    EyeContactData,
    PostureData,
    GestureData,
)
from app.services.speech_analyzer import process_speech_analysis_session
from app.services.visual_analyzer import (
    analyze_eye_contact_and_head_pose_sync,
    analyze_posture_and_gestures_sync,
)
from app.config import settings
from app.db.mongodb import MongoDB
from app.db.database import Database


# --- Mock MongoDB Classes ---

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
    return mock_col


# --- Mock Classes for MediaPipe Outputs ---

class MockLandmark:
    def __init__(self, x=0.0, y=0.0, z=0.0, visibility=0.9):
        self.x = x
        self.y = y
        self.z = z
        self.visibility = visibility


class MockPoseLandmarks:
    def __init__(self, visibility=0.9):
        self.landmark = [MockLandmark(visibility=visibility) for _ in range(33)]


class MockPoseResults:
    def __init__(self, has_pose=True, visibility=0.9):
        self.pose_landmarks = MockPoseLandmarks(visibility=visibility) if has_pose else None


class MockClassification:
    def __init__(self, score=0.95):
        self.score = score


class MockHand:
    def __init__(self, score=0.95):
        self.classification = [MockClassification(score=score)]


class MockHandResults:
    def __init__(self, has_hands=True, score=0.95):
        if has_hands:
            self.multi_hand_landmarks = [MagicMock(landmark=[MockLandmark() for _ in range(21)])]
        else:
            self.multi_hand_landmarks = None
        self.multi_handedness = [MockHand(score=score)] if has_hands else None


class MockDetection:
    def __init__(self, score=0.98):
        self.score = [score]


class MockDetectionResults:
    def __init__(self, has_face=True, score=0.98):
        self.detections = [MockDetection(score=score)] if has_face else None


class MockFaceMeshResults:
    def __init__(self, has_face=True):
        if has_face:
            self.multi_face_landmarks = [MagicMock(landmark=[MockLandmark() for _ in range(468)])]
        else:
            self.multi_face_landmarks = None


# --- Helper to create a dummy video file ---
def create_dummy_video(path: Path, frames_count: int = 5):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(path), fourcc, 5.0, (160, 120))
    for _ in range(frames_count):
        out.write(np.zeros((120, 160, 3), dtype=np.uint8))
    out.release()


# --- Helper to create a dummy frames directory ---
def create_dummy_frames_dir(path: Path, frames_count: int = 3):
    path.mkdir(parents=True, exist_ok=True)
    img = np.zeros((120, 160, 3), dtype=np.uint8)
    for i in range(1, frames_count + 1):
        cv2.imwrite(str(path / f"frame_{i:04d}.jpg"), img)


# --- Speech Analysis Tests ---

@pytest.mark.asyncio
async def test_speech_confidence_clean(mock_mongodb, monkeypatch):
    session_id = "clean-speech-session"
    
    audio_file = settings.processed_dir / session_id / "audio.wav"
    audio_file.parent.mkdir(parents=True, exist_ok=True)
    audio_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

    initial_doc = {
        "session_id": session_id,
        "original_filename": "clean.mp4",
        "upload_timestamp": datetime.now(timezone.utc),
        "file_size": 100,
        "content_type": "video/mp4",
        "status": SessionStatus.PROCESSED,
        "audio_path": f"processed/{session_id}/audio.wav"
    }
    await mock_mongodb.insert_one(initial_doc)

    mock_words = [
        WordTimestamp(word="This", start=0.0, end=0.3, probability=0.99),
        WordTimestamp(word="is", start=0.4, end=0.6, probability=0.98),
        WordTimestamp(word="clear", start=0.7, end=1.1, probability=0.97),
        WordTimestamp(word="speech", start=1.2, end=1.6, probability=0.95),
    ]
    monkeypatch.setattr(
        "app.services.speech_analyzer.transcribe_audio_sync",
        lambda path, model: ("This is clear speech", mock_words)
    )

    success = await process_speech_analysis_session(session_id)
    assert success is True

    doc = await mock_mongodb.find_one({"session_id": session_id})
    assert doc is not None
    assert doc["speech_analysis"]["average_transcription_confidence"] == 0.9725
    assert doc["speech_analysis"]["words"][0]["probability"] == 0.99

    if audio_file.exists():
        audio_file.unlink()


@pytest.mark.asyncio
async def test_speech_confidence_noisy(mock_mongodb, monkeypatch):
    session_id = "noisy-speech-session"
    
    audio_file = settings.processed_dir / session_id / "audio.wav"
    audio_file.parent.mkdir(parents=True, exist_ok=True)
    audio_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

    initial_doc = {
        "session_id": session_id,
        "original_filename": "noisy.mp4",
        "upload_timestamp": datetime.now(timezone.utc),
        "file_size": 100,
        "content_type": "video/mp4",
        "status": SessionStatus.PROCESSED,
        "audio_path": f"processed/{session_id}/audio.wav"
    }
    await mock_mongodb.insert_one(initial_doc)

    mock_words = [
        WordTimestamp(word="mumble", start=0.0, end=0.5, probability=0.35),
        WordTimestamp(word="noise", start=0.6, end=1.2, probability=0.20),
    ]
    monkeypatch.setattr(
        "app.services.speech_analyzer.transcribe_audio_sync",
        lambda path, model: ("mumble noise", mock_words)
    )

    success = await process_speech_analysis_session(session_id)
    assert success is True

    doc = await mock_mongodb.find_one({"session_id": session_id})
    assert doc is not None
    assert doc["speech_analysis"]["average_transcription_confidence"] == 0.2750

    if audio_file.exists():
        audio_file.unlink()


# --- Visual Analysis Tests ---

def test_visual_confidence_clean(tmp_path, monkeypatch):
    video_file = tmp_path / "clean_video.mp4"
    create_dummy_video(video_file, frames_count=10)

    frames_dir = tmp_path / "clean_frames"
    create_dummy_frames_dir(frames_dir, frames_count=3)

    # Setup local mock solutions inside the test function context
    class DummySolutions:
        pass

    solutions_mock = DummySolutions()
    solutions_mock.face_mesh = MagicMock()
    solutions_mock.face_detection = MagicMock()
    solutions_mock.pose = MagicMock()
    solutions_mock.hands = MagicMock()

    class DummyPoseLandmark:
        LEFT_SHOULDER = 11
        RIGHT_SHOULDER = 12
        LEFT_HIP = 23
        RIGHT_HIP = 24

    solutions_mock.pose.PoseLandmark = DummyPoseLandmark

    monkeypatch.setattr(mp, "solutions", solutions_mock, raising=False)
    monkeypatch.setattr("app.services.visual_analyzer.mp", mp)

    # 1. Mock Face Mesh & Face Detection to succeed with high score (0.95)
    mock_face_mesh_inst = MagicMock()
    mock_face_mesh_inst.process.return_value = MockFaceMeshResults(has_face=True)
    
    mock_face_det_inst = MagicMock()
    mock_face_det_inst.process.return_value = MockDetectionResults(has_face=True, score=0.95)

    # 2. Mock Pose to succeed with high landmark visibility (0.98)
    mock_pose_inst = MagicMock()
    mock_pose_inst.process.return_value = MockPoseResults(has_pose=True, visibility=0.98)

    # 3. Mock Hands to succeed with high classification score (0.92)
    mock_hands_inst = MagicMock()
    mock_hands_inst.process.return_value = MockHandResults(has_hands=True, score=0.92)

    # Patch constructors
    monkeypatch.setattr(solutions_mock.face_mesh, "FaceMesh", lambda *args, **kwargs: mock_face_mesh_inst)
    monkeypatch.setattr(solutions_mock.face_detection, "FaceDetection", lambda *args, **kwargs: mock_face_det_inst)
    monkeypatch.setattr(solutions_mock.pose, "Pose", lambda *args, **kwargs: mock_pose_inst)
    monkeypatch.setattr(solutions_mock.hands, "Hands", lambda *args, **kwargs: mock_hands_inst)

    # Run the analysis
    eye_contact, head_movement = analyze_eye_contact_and_head_pose_sync(video_file)
    posture, gesture = analyze_posture_and_gestures_sync(frames_dir)

    # Assertions for clean video
    assert eye_contact.average_detection_confidence == 0.95
    assert eye_contact.fallback_frame_count == 0
    assert eye_contact.no_detection_frame_count == 0

    assert posture.average_detection_confidence == 0.98
    assert posture.fallback_frame_count == 0
    assert posture.no_detection_frame_count == 0

    assert gesture.average_detection_confidence == 0.92
    assert gesture.fallback_frame_count == 0
    assert gesture.no_detection_frame_count == 0


def test_visual_confidence_noisy_and_no_detection(tmp_path, monkeypatch):
    video_file = tmp_path / "noisy_video.mp4"
    create_dummy_video(video_file, frames_count=10)

    frames_dir = tmp_path / "noisy_frames"
    create_dummy_frames_dir(frames_dir, frames_count=3)

    # Setup local mock solutions inside the test function context
    class DummySolutions:
        pass

    solutions_mock = DummySolutions()
    solutions_mock.face_mesh = MagicMock()
    solutions_mock.face_detection = MagicMock()
    solutions_mock.pose = MagicMock()
    solutions_mock.hands = MagicMock()

    class DummyPoseLandmark:
        LEFT_SHOULDER = 11
        RIGHT_SHOULDER = 12
        LEFT_HIP = 23
        RIGHT_HIP = 24

    solutions_mock.pose.PoseLandmark = DummyPoseLandmark

    monkeypatch.setattr(mp, "solutions", solutions_mock, raising=False)
    monkeypatch.setattr("app.services.visual_analyzer.mp", mp)

    # 1. Mock Face Mesh & Face Detection to FAIL
    mock_face_mesh_inst = MagicMock()
    mock_face_mesh_inst.process.return_value = MockFaceMeshResults(has_face=False)
    
    mock_face_det_inst = MagicMock()
    mock_face_det_inst.process.return_value = MockDetectionResults(has_face=False)

    # 2. Mock Pose to FAIL
    mock_pose_inst = MagicMock()
    mock_pose_inst.process.return_value = MockPoseResults(has_pose=False)

    # 3. Mock Hands to FAIL
    mock_hands_inst = MagicMock()
    mock_hands_inst.process.return_value = MockHandResults(has_hands=False)

    # Patch constructors
    monkeypatch.setattr(solutions_mock.face_mesh, "FaceMesh", lambda *args, **kwargs: mock_face_mesh_inst)
    monkeypatch.setattr(solutions_mock.face_detection, "FaceDetection", lambda *args, **kwargs: mock_face_det_inst)
    monkeypatch.setattr(solutions_mock.pose, "Pose", lambda *args, **kwargs: mock_pose_inst)
    monkeypatch.setattr(solutions_mock.hands, "Hands", lambda *args, **kwargs: mock_hands_inst)

    # Patch OpenCV cascades to return empty detections
    monkeypatch.setattr(cv2.CascadeClassifier, "detectMultiScale", lambda self, *args, **kwargs: ())

    # Run the analysis
    eye_contact, head_movement = analyze_eye_contact_and_head_pose_sync(video_file)
    posture, gesture = analyze_posture_and_gestures_sync(frames_dir)

    # Assertions for noisy video
    assert eye_contact.average_detection_confidence is None
    assert eye_contact.fallback_frame_count == 0
    assert eye_contact.no_detection_frame_count > 0

    assert posture.average_detection_confidence is None
    assert posture.fallback_frame_count == 0
    assert posture.no_detection_frame_count == 3

    assert gesture.average_detection_confidence is None
    assert gesture.fallback_frame_count == 0
    assert gesture.no_detection_frame_count == 3
