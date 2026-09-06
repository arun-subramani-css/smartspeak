import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.db.database import Database
from app.db.mongodb import MongoDB
from app.models.session import (
    SessionDocument,
    SessionStatus,
    FusionReportResult,
)
from app.services.fusion_engine import (
    correlate_events,
    detect_mistakes,
    compute_composite_scores,
    generate_fusion_report_sync,
    process_fusion_session,
)


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
                if doc.get(key) == val["$ne"]:
                    return None
            elif doc.get(key) != val:
                return None
        return doc.copy()

    async def update_one(self, query, update):
        session_id = query.get("session_id")
        if session_id in self.docs:
            if "$set" in update:
                self.docs[session_id].update(update["$set"])
            return MagicMock(modified_count=1)
        return MagicMock(modified_count=0)


@pytest.fixture(autouse=True)
def mock_mongodb(monkeypatch):
    mock_col = MockMongoDBCollection()
    monkeypatch.setattr("app.db.database.Database.get_collection", lambda name="sessions": mock_col)
    monkeypatch.setattr(MongoDB, "get_collection", lambda name="sessions": mock_col)
    async def mock_connect():
        pass
    monkeypatch.setattr("app.db.database.Database.connect", mock_connect)
    return mock_col


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Unit Tests for Event Correlation
# ---------------------------------------------------------------------------

def test_timestamp_correlation_detects_overlaps():
    speech_analysis = {
        "filler_words": [
            {"word": "um", "timestamp": 3.0, "confidence": 0.9}
        ],
        "long_pauses": [
            {"start_time": 10.0, "end_time": 13.0, "duration": 3.0}
        ],
        "repetitions": [
            {"phrase": "we need to", "count": 2, "timestamp": 20.0}
        ]
    }

    visual_analysis = {
        "eye_contact": {
            "looking_away_ranges": [
                # Overlaps with filler at 3.0 within ±1.0s window [2.5, 4.0]
                {"start_time": 2.5, "end_time": 4.0, "category": "looking_down", "duration": 1.5}
            ]
        },
        "posture": {
            "poor_posture_ranges": [
                # Overlaps with pause [10.0, 13.0]
                {"start_time": 12.0, "end_time": 15.0, "duration": 3.0}
            ]
        },
        "head_movement": {
            # Far outside correlation window
            "excessive_movement_timestamps": [35.0]
        }
    }

    compound, unassigned_speech, unassigned_visual = correlate_events(speech_analysis, visual_analysis, window_seconds=1.0)

    # We should have 2 compound events:
    # 1. filler 'um' (3.0) + looking_down (2.5-4.0)
    # 2. pause (10.0-13.0) + poor_posture (12.0-15.0)
    assert len(compound) == 2
    assert compound[0]["type"] == "compound"
    assert any("filler_word: um" in label for label in compound[0]["events"])
    assert any("looking_down" in label for label in compound[0]["events"])

    assert compound[1]["type"] == "compound"
    assert any("pause: 3.0s" in label for label in compound[1]["events"])
    assert any("poor_posture" in label for label in compound[1]["events"])

    # Standalone speech event: repetition at 20.0
    assert len(unassigned_speech) == 1
    assert unassigned_speech[0]["type"] == "repetition"

    # Standalone visual event: head movement at 35.0
    assert len(unassigned_visual) == 1
    assert unassigned_visual[0]["type"] == "head_movement"


def test_compound_event_deduplication():
    # Mocked data with 1 speech event (filler at 2.0) and 4 overlapping
    # same-type visual events within the ±1.0s correlation window
    speech_analysis = {
        "filler_words": [
            {"word": "um", "timestamp": 2.0}
        ],
        "long_pauses": [],
        "repetitions": []
    }

    visual_analysis = {
        "eye_contact": {"looking_away_ranges": []},
        "posture": {"poor_posture_ranges": []},
        "head_movement": {
            "excessive_movement_timestamps": [1.5, 1.8, 2.1, 2.5]
        }
    }

    mistakes = detect_mistakes(speech_analysis, visual_analysis)
    assert len(mistakes) >= 1
    compound_mistakes = [m for m in mistakes if m.category == "compound"]
    assert len(compound_mistakes) == 1

    events = compound_mistakes[0].events
    # Confirm the resulting mistake's events list contains no duplicate consecutive entries
    for i in range(len(events) - 1):
        assert events[i] != events[i + 1]

    # Confirm no duplicate entries overall
    assert len(events) == len(set(events))

    # Verify head movement is collapsed into one entry noting the count (x4)
    head_entries = [e for e in events if "excessive_head_movement" in e]
    assert len(head_entries) == 1
    assert "excessive_head_movement (x4)" in head_entries[0]


# ---------------------------------------------------------------------------
# Unit Tests for Severity Thresholds
# ---------------------------------------------------------------------------

def test_severity_thresholds():
    # Test speech pause severity: <4 minor, 4-6 medium, >=6 high
    speech_data = {
        "filler_words": [{"word": "like", "timestamp": 1.0}],
        "long_pauses": [
            {"start_time": 5.0, "end_time": 7.5, "duration": 2.5},   # minor
            {"start_time": 15.0, "end_time": 19.5, "duration": 4.5},  # medium
            {"start_time": 25.0, "end_time": 32.0, "duration": 7.0},  # high
        ],
        "repetitions": [
            {"phrase": "you know", "count": 2, "timestamp": 40.0},     # minor
            {"phrase": "I think", "count": 4, "timestamp": 50.0},      # medium
        ]
    }

    visual_data = {
        "eye_contact": {
            "looking_away_ranges": [
                {"start_time": 60.0, "end_time": 62.5, "duration": 2.5, "category": "looking_away"},  # minor
                {"start_time": 70.0, "end_time": 74.5, "duration": 4.5, "category": "looking_away"},  # medium
                {"start_time": 80.0, "end_time": 87.0, "duration": 7.0, "category": "looking_away"},  # high
            ]
        },
        "posture": {
            "poor_posture_ranges": [
                {"start_time": 90.0, "end_time": 92.5, "duration": 2.5},  # minor
                {"start_time": 100.0, "end_time": 104.5, "duration": 4.5}, # medium
                {"start_time": 110.0, "end_time": 117.0, "duration": 7.0}, # high
            ]
        },
        "head_movement": {
            "excessive_movement_timestamps": [120.0]  # minor
        }
    }

    mistakes = detect_mistakes(speech_data, visual_data)
    mistake_map = {m.description: m.severity for m in mistakes}

    # Verify filler
    assert mistake_map["Used filler word 'like'"] == "minor"
    # Verify pauses
    assert mistake_map["Brief pause (2.5s)"] == "minor"
    assert mistake_map["Noticeable hesitation pause (4.5s)"] == "medium"
    assert mistake_map["Extended awkward silence (7.0s)"] == "high"
    # Verify repetitions
    assert mistake_map["Repeated phrase 'you know' (2x)"] == "minor"
    assert mistake_map["Repeated phrase 'I think' (4x)"] == "medium"
    # Verify eye contact
    assert mistake_map["Brief gaze shift (looking away for 2.5s)"] == "minor"
    assert mistake_map["Looking away from audience (looking away for 4.5s)"] == "medium"
    assert mistake_map["Sustained eye contact loss (looking away for 7.0s)"] == "high"
    # Verify posture
    assert mistake_map["Brief posture deviation (2.5s)"] == "minor"
    assert mistake_map["Noticeable poor posture (4.5s)"] == "medium"
    assert mistake_map["Sustained slouching or torso lean (7.0s)"] == "high"
    # Verify head movement
    assert mistake_map["Excessive or abrupt head movement detected"] == "minor"


# ---------------------------------------------------------------------------
# Unit Tests for Composite Scoring Formulas & SmartSpeak Index
# ---------------------------------------------------------------------------

def test_composite_scoring_formulas():
    # 5 fillers in 100 words -> 5% ratio -> score = 100 - (0.05 * 300) = 85.0
    # WPM: 145 (optimal 130-160) -> 100.0
    # Pauses: one 3s pause (-5) -> 95.0
    # Verbal = 0.40 * 85.0 + 0.30 * 100.0 + 0.30 * 95.0 = 34.0 + 30.0 + 28.5 = 92.5
    speech_data = {
        "wpm_data": {
            "total_words": 100,
            "overall_wpm": 145.0,
            "total_speaking_duration_seconds": 41.4
        },
        "filler_word_count": 5,
        "long_pauses": [{"duration": 3.0}],
        "repetitions": []
    }

    # Visual:
    # eye contact = 80.0 (35%)
    # posture = 90.0 (30%)
    # gesture = average -> 100.0 (20%)
    # head = 90.0 (15%)
    # Non-Verbal = 0.35*80 + 0.30*90 + 0.20*100 + 0.15*90 = 28 + 27 + 20 + 13.5 = 88.5
    visual_data = {
        "eye_contact": {"eye_contact_percentage": 80.0},
        "posture": {"total_frames_analyzed": 50, "posture_score": 90.0},
        "gesture": {"gesture_usage_classification": "average"},
        "head_movement": {"head_movement_score": 90.0}
    }

    # ML Confidence = 82.0 (20%)
    confidence_data = {
        "confidence_score": 82.0
    }

    scores = compute_composite_scores(speech_data, visual_data, confidence_data)
    assert scores["verbal_score"] == 92.5
    assert scores["non_verbal_score"] == 88.5
    assert scores["ml_confidence_score"] == 82.0

    # SmartSpeak Index = 0.40 * 92.5 + 0.40 * 88.5 + 0.20 * 82.0
    # = 37.0 + 35.4 + 16.4 = 88.8
    assert scores["smartspeak_index"] == 88.8
    assert scores["grade"] == "Executive"


# ---------------------------------------------------------------------------
# Unit Tests for Grade Boundaries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("verbal, non_verbal, conf, expected_grade", [
    (90.0, 90.0, 90.0, "Executive"),       # 90.0 >= 85
    (85.0, 85.0, 85.0, "Executive"),       # 85.0 boundary
    (84.9, 84.9, 84.9, "Polished"),        # 84.9 upper boundary
    (75.0, 75.0, 75.0, "Polished"),        # 75.0
    (70.0, 70.0, 70.0, "Polished"),        # 70.0 boundary
    (69.9, 69.9, 69.9, "Competent"),       # 69.9 upper boundary
    (55.0, 55.0, 55.0, "Competent"),       # 55.0
    (50.0, 50.0, 50.0, "Competent"),       # 50.0 boundary
    (49.9, 49.9, 49.9, "Needs Practice"),  # 49.9 upper boundary
    (20.0, 20.0, 20.0, "Needs Practice"),  # 20.0
])
def test_grade_mapping(verbal, non_verbal, conf, expected_grade):
    speech_data = {
        "wpm_data": {"total_words": 100, "overall_wpm": 145.0, "total_speaking_duration_seconds": 40.0},
        "filler_word_count": 0,
        "long_pauses": [],
        "repetitions": []
    }
    # Mock scores by controlling inputs or directly testing compute_composite_scores
    res = compute_composite_scores(
        speech_analysis=None,
        visual_analysis=None,
        confidence_analysis={"confidence_score": verbal}
    )
    # When only confidence is provided, Index equals conf
    assert res["smartspeak_index"] == verbal
    assert res["grade"] == expected_grade


# ---------------------------------------------------------------------------
# Missing / Null Data Resilience
# ---------------------------------------------------------------------------

def test_fusion_handles_missing_confidence_data():
    speech_data = {
        "wpm_data": {"total_words": 100, "overall_wpm": 145.0, "total_speaking_duration_seconds": 40.0},
        "filler_word_count": 0,  # filler score 100.0
        "long_pauses": [],
        "repetitions": []
    }  # verbal = 100.0

    visual_data = {
        "eye_contact": {"eye_contact_percentage": 80.0},
        "posture": {"total_frames_analyzed": 50, "posture_score": 80.0},
        "gesture": {"gesture_usage_classification": "average"},  # 100.0
        "head_movement": {"head_movement_score": 80.0}
    }  # non_verbal = 0.35*80 + 0.30*80 + 0.20*100 + 0.15*80 = 28 + 24 + 20 + 12 = 84.0

    # confidence_analysis is None
    scores = compute_composite_scores(speech_data, visual_data, None)
    
    assert scores["verbal_score"] == 100.0
    assert scores["non_verbal_score"] == 84.0
    assert scores["ml_confidence_score"] == 0.0
    
    # Dynamic proportional redistribution:
    # Verbal (0.40) and Non-Verbal (0.40) out of total 0.80 -> 50% each
    # Index = (0.40 * 100.0 + 0.40 * 84.0) / 0.80 = (40.0 + 33.6) / 0.80 = 73.6 / 0.80 = 92.0
    assert scores["smartspeak_index"] == 92.0
    assert scores["grade"] == "Executive"


def test_fusion_handles_zero_word_count():
    speech_data = {
        "wpm_data": {
            "total_words": 0,
            "overall_wpm": 0.0,
            "total_speaking_duration_seconds": 0.0
        },
        "filler_word_count": 0,
        "long_pauses": [],
        "repetitions": []
    }
    visual_data = {
        "eye_contact": {"eye_contact_percentage": 100.0},
        "posture": {"total_frames_analyzed": 10, "posture_score": 100.0},
        "gesture": {"gesture_usage_classification": "average"},
        "head_movement": {"head_movement_score": 100.0}
    }
    # Should not raise ZeroDivisionError
    scores = compute_composite_scores(speech_data, visual_data, None)
    assert scores["verbal_score"] == 100.0
    assert scores["smartspeak_index"] == 100.0
    assert scores["grade"] == "Executive"


def test_fusion_handles_missing_posture_frames():
    visual_data = {
        "eye_contact": {"eye_contact_percentage": 80.0},
        "posture": {"total_frames_analyzed": 0, "posture_score": None},
        "gesture": {"gesture_usage_classification": "average"},  # 100.0
        "head_movement": {"head_movement_score": 60.0}
    }
    scores = compute_composite_scores(None, visual_data, None)
    # Posture weight (0.30) redistributed over 0.70:
    # (0.35 * 80 + 0.20 * 100 + 0.15 * 60) / 0.70 = (28 + 20 + 9) / 0.70 = 57 / 0.70 = 81.4
    assert scores["non_verbal_score"] == 81.4
    assert scores["smartspeak_index"] == 81.4
    assert scores["grade"] == "Polished"


# ---------------------------------------------------------------------------
# API Endpoint Tests
# ---------------------------------------------------------------------------

def test_get_fusion_report_404_not_found(client):
    response = client.get("/api/v1/sessions/non-existent-session-id/fusion-report")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_fusion_report_400_not_ready(client, mock_mongodb):
    session_id = "session-not-ready-123"
    mock_mongodb.docs[session_id] = {
        "session_id": session_id,
        "status": SessionStatus.PROCESSING,
        "speech_analysis": None,
        "visual_analysis": None
    }
    response = client.get(f"/api/v1/sessions/{session_id}/fusion-report")
    assert response.status_code == 400
    assert "not available" in response.json()["detail"].lower()


def test_get_fusion_report_computes_and_returns(client, mock_mongodb):
    session_id = "session-ready-for-fusion"
    mock_mongodb.docs[session_id] = {
        "session_id": session_id,
        "status": SessionStatus.READY_FOR_FUSION,
        "speech_analysis": {
            "wpm_data": {"total_words": 100, "overall_wpm": 140.0, "total_speaking_duration_seconds": 42.0},
            "filler_word_count": 2,
            "long_pauses": [],
            "repetitions": []
        },
        "visual_analysis": {
            "eye_contact": {"eye_contact_percentage": 95.0, "looking_away_ranges": []},
            "posture": {"total_frames_analyzed": 50, "posture_score": 90.0, "poor_posture_ranges": []},
            "gesture": {"gesture_usage_classification": "average"},
            "head_movement": {"head_movement_score": 90.0, "excessive_movement_timestamps": []}
        },
        "confidence_analysis": {
            "confidence_score": 85.0
        }
    }

    response = client.get(f"/api/v1/sessions/{session_id}/fusion-report")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    assert data["status"] == SessionStatus.FUSION_COMPLETE
    report = data["fusion_report"]
    assert report["smartspeak_index"] > 0
    assert report["grade"] in ["Executive", "Polished"]
    assert isinstance(report["mistakes"], list)

    # Verify document was updated in database
    doc_in_db = mock_mongodb.docs[session_id]
    assert doc_in_db["status"] == SessionStatus.FUSION_COMPLETE
    assert "fusion_report" in doc_in_db


def test_trigger_fusion_analysis_endpoint(client, mock_mongodb):
    session_id = "session-to-fuse"
    mock_mongodb.docs[session_id] = {
        "session_id": session_id,
        "status": SessionStatus.READY_FOR_FUSION
    }
    response = client.post(f"/api/v1/sessions/{session_id}/fuse")
    assert response.status_code == 202
    data = response.json()
    assert data["session_id"] == session_id
    assert data["status"] == "processing"
