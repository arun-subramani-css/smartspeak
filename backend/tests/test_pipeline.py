import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import cv2
import numpy as np
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.db.mongodb import MongoDB
from app.services.file_validator import validate_container_header
from app.services.video_processor import process_video_session
from app.models.session import SessionStatus


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


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.mark.asyncio
async def test_file_validator_container_header():
    # Valid MP4 header sample with 'ftyp' atom
    mp4_header = b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2avc1mp41"
    assert validate_container_header(mp4_header, "test.mp4") is True

    # Valid AVI header sample with 'RIFF' and 'AVI '
    avi_header = b"RIFF\x00\x00\x00\x00AVI LIST\x00\x00\x00\x00hdrl"
    assert validate_container_header(avi_header, "test.avi") is True

    # Invalid TXT header sample
    txt_header = b"This is a plain text file pretending to be a video."
    assert validate_container_header(txt_header, "fake.mp4") is False


def test_upload_invalid_extension(client):
    response = client.post(
        "/api/v1/upload",
        files={"video": ("document.txt", b"Hello world text content", "text/plain")}
    )
    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["detail"]


def test_upload_fake_mp4_container(client):
    response = client.post(
        "/api/v1/upload",
        files={"video": ("fake_video.mp4", b"Plain text disguised as mp4 video file content", "video/mp4")}
    )
    assert response.status_code == 400
    assert "Invalid video container or corrupted file header" in response.json()["detail"]


def test_upload_oversized_file(client, monkeypatch):
    # Temporarily set max upload size to 1MB for testing
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    large_dummy_bytes = b"0" * (2 * 1024 * 1024)  # 2MB
    
    mp4_header = b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2avc1mp41"
    content = mp4_header + large_dummy_bytes

    response = client.post(
        "/api/v1/upload",
        files={"video": ("large.mp4", content, "video/mp4")}
    )
    assert response.status_code == 413
    assert "exceeds maximum allowed size" in response.json()["detail"]


def test_upload_valid_mp4_header_returns_session(client):
    # Create valid minimal MP4 header
    mp4_header = b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 100
    response = client.post(
        "/api/v1/upload",
        files={"video": ("speech_test.mp4", mp4_header, "video/mp4")}
    )
    assert response.status_code == 201
    data = response.json()
    assert "session_id" in data
    assert data["status"] == "uploaded"
    assert data["original_filename"] == "speech_test.mp4"


@pytest.mark.asyncio
async def test_corrupted_video_marks_status_failed(mock_mongodb):
    session_id = "test-corrupted-session-123"
    fake_file = settings.staging_dir / f"{session_id}.mp4"
    fake_file.write_bytes(b"ftypisomCorruptedUnplayableData")

    doc = {
        "session_id": session_id,
        "original_filename": "bad.mp4",
        "upload_timestamp": datetime.now(timezone.utc),
        "file_size": 100,
        "content_type": "video/mp4",
        "status": SessionStatus.UPLOADED,
        "file_path": str(fake_file)
    }
    await mock_mongodb.insert_one(doc)

    success = await process_video_session(session_id)
    assert success is False

    updated_doc = await mock_mongodb.find_one({"session_id": session_id})
    assert updated_doc["status"] == SessionStatus.FAILED
    assert updated_doc["error_reason"] is not None
    
    if fake_file.exists():
        fake_file.unlink()
