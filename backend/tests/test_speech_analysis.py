from datetime import datetime, timezone
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import settings
from app.db.mongodb import MongoDB
from app.models.session import SessionStatus, WordTimestamp
from app.services.speech_analyzer import (
    calculate_wpm_data,
    detect_filler_words,
    detect_long_pauses,
    detect_repetitions,
    process_speech_analysis_session,
)


class MockMongoDBCollection:
    def __init__(self):
        self.docs = {}

    async def insert_one(self, doc):
        self.docs[doc["session_id"]] = doc
        return MagicMock(inserted_id=doc["session_id"])

    async def find_one(self, query):
        session_id = query.get("session_id")
        return self.docs.get(session_id)

    async def update_one(self, query, update):
        session_id = query.get("session_id")
        if session_id in self.docs:
            if "$set" in update:
                self.docs[session_id].update(update["$set"])
        return MagicMock(modified_count=1)

    async def delete_one(self, query):
        session_id = query.get("session_id")
        if session_id in self.docs:
            del self.docs[session_id]
        return MagicMock(deleted_count=1)

    def create_index(self, *args, **kwargs):
        pass


@pytest.fixture(autouse=True)
def mock_mongodb(monkeypatch):
    mock_col = MockMongoDBCollection()
    monkeypatch.setattr(MongoDB, "get_collection", lambda name="sessions": mock_col)
    return mock_col


def test_detect_filler_words():
    words = [
        WordTimestamp(word="Hello", start=0.0, end=0.5),
        WordTimestamp(word="um", start=0.6, end=0.9),
        WordTimestamp(word="today", start=1.0, end=1.3),
        WordTimestamp(word="you", start=1.5, end=1.7),
        WordTimestamp(word="know", start=1.8, end=2.0),
        WordTimestamp(word="we", start=2.1, end=2.3),
        WordTimestamp(word="like", start=2.4, end=2.6),
        WordTimestamp(word="started", start=2.7, end=3.0),
    ]
    fillers, count = detect_filler_words(words, settings.FILLER_WORDS)

    assert count == 3
    detected_words = [f.word for f in fillers]
    assert "um" in detected_words
    assert "you know" in detected_words
    assert "like" in detected_words
    assert fillers[0].timestamp == 0.6
    assert fillers[1].timestamp == 1.5


def test_calculate_wpm_data():
    # 30 words over 12 seconds = (30 / (12 / 60)) = 150 WPM
    words = [
        WordTimestamp(word=f"word_{i}", start=i * 0.4, end=i * 0.4 + 0.3)
        for i in range(30)
    ]
    wpm_data = calculate_wpm_data(words, window_seconds=15.0, step_seconds=5.0)

    assert wpm_data.total_words == 30
    assert 140.0 <= wpm_data.overall_wpm <= 160.0
    assert len(wpm_data.windowed_wpm) >= 1
    assert wpm_data.windowed_wpm[0].wpm > 0.0


def test_detect_long_pauses():
    words = [
        WordTimestamp(word="First", start=0.0, end=1.0),
        # Gap of 3.5 seconds (1.0 to 4.5)
        WordTimestamp(word="Second", start=4.5, end=5.5),
        # Gap of 1.0 second (5.5 to 6.5)
        WordTimestamp(word="Third", start=6.5, end=7.5),
    ]
    pauses = detect_long_pauses(words, threshold=3.0)

    assert len(pauses) == 1
    assert pauses[0].start_time == 1.0
    assert pauses[0].end_time == 4.5
    assert pauses[0].duration == 3.5


def test_detect_repetitions():
    words = [
        WordTimestamp(word="the", start=0.0, end=0.3),
        WordTimestamp(word="the", start=0.4, end=0.7),  # Immediate repetition
        WordTimestamp(word="project", start=0.8, end=1.2),
        WordTimestamp(word="I", start=2.0, end=2.2),
        WordTimestamp(word="think", start=2.3, end=2.5),
        WordTimestamp(word="I", start=3.0, end=3.2),
        WordTimestamp(word="think", start=3.3, end=3.5),  # Phrase repetition
    ]
    reps = detect_repetitions(words)

    phrases = [r.phrase for r in reps]
    assert "the" in phrases
    assert "i think" in phrases


def test_silent_audio_handling():
    words = []
    fillers, count = detect_filler_words(words, settings.FILLER_WORDS)
    wpm_data = calculate_wpm_data(words)
    pauses = detect_long_pauses(words)
    reps = detect_repetitions(words)

    assert count == 0
    assert wpm_data.overall_wpm == 0.0
    assert len(pauses) == 0
    assert len(reps) == 0


@pytest.mark.asyncio
async def test_speech_analysis_overwrite_on_rerun(mock_mongodb, monkeypatch):
    session_id = "test-rerun-overwrite-session"
    audio_file = settings.processed_dir / session_id / "audio.wav"
    audio_file.parent.mkdir(parents=True, exist_ok=True)
    audio_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

    initial_doc = {
        "session_id": session_id,
        "original_filename": "speech.mp4",
        "upload_timestamp": datetime.now(timezone.utc),
        "file_size": 1000,
        "content_type": "video/mp4",
        "status": SessionStatus.PROCESSED,
        "audio_path": f"processed/{session_id}/audio.wav",
        "speech_analysis": {
            "transcript_text": "Old transcript version 1",
            "words": [],
            "filler_words": [],
            "filler_word_count": 0,
            "wpm_data": {"overall_wpm": 100.0, "total_words": 5, "total_speaking_duration_seconds": 3.0, "windowed_wpm": []},
            "long_pauses": [],
            "repetitions": [],
            "analyzed_at": datetime.now(timezone.utc).isoformat()
        }
    }
    await mock_mongodb.insert_one(initial_doc)

    # Mock transcribe_audio_sync to return new updated transcript
    mock_words = [
        WordTimestamp(word="New", start=0.0, end=0.4),
        WordTimestamp(word="transcript", start=0.5, end=1.0),
        WordTimestamp(word="version", start=1.1, end=1.5),
        WordTimestamp(word="two", start=1.6, end=2.0)
    ]
    monkeypatch.setattr(
        "app.services.speech_analyzer.transcribe_audio_sync",
        lambda audio_path, model_name: ("New transcript version two", mock_words)
    )

    success = await process_speech_analysis_session(session_id)
    assert success is True

    updated_doc = await mock_mongodb.find_one({"session_id": session_id})
    assert updated_doc["status"] == SessionStatus.SPEECH_ANALYSIS_COMPLETE
    assert updated_doc["speech_analysis"]["transcript_text"] == "New transcript version two"
    assert len(updated_doc["speech_analysis"]["words"]) == 4

    # Cleanup temp audio file
    if audio_file.exists():
        audio_file.unlink()
