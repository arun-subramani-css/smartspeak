"""Tests for the phone-camera pairing API (Practice mode "Use phone camera").

Covers the spec'd behaviours: token create/expire/single-use, clear 404/410
errors for invalid/expired/reused tokens, the uploaded session link, LAN URL
construction (never localhost), and that the pairing upload reuses the exact
format/size validation of POST /api/v1/upload.
"""
import logging

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from app.config import settings
from app.db.mongodb import MongoDB
from app.main import app
from app.services import pairing as pairing_svc


# --- Same DB mock pattern as test_pipeline.py -------------------------------

class MockMongoDBCollection:
    def __init__(self):
        self.docs = {}

    async def insert_one(self, doc):
        self.docs[doc["session_id"]] = doc
        return MagicMock(inserted_id=doc["session_id"])

    async def find_one(self, query):
        return self.docs.get(query.get("session_id"))

    async def update_one(self, query, update):
        session_id = query.get("session_id")
        if session_id in self.docs and "$set" in update:
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
    monkeypatch.setattr("app.db.database.Database.get_collection", lambda name="sessions": mock_col)
    monkeypatch.setattr(MongoDB, "get_collection", lambda name="sessions": mock_col)

    async def mock_connect():
        pass

    monkeypatch.setattr("app.db.database.Database.connect", mock_connect)
    return mock_col


@pytest.fixture(autouse=True)
def fake_pipeline(monkeypatch):
    """Skip the real ffmpeg/Whisper pipeline — dispatch itself is covered by
    test_pipeline.py; here we only assert the token↔session link."""
    monkeypatch.setattr("app.services.ingest.process_video_session", lambda session_id: None)


@pytest.fixture(autouse=True)
def clean_store():
    pairing_svc._store.clear()
    yield
    pairing_svc._store.clear()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def make_token(client) -> str:
    res = client.post("/api/v1/pairing")
    assert res.status_code == 201
    return res.json()["token"]


MP4_HEADER = b"\x00\x00\x00\x1cftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 100


# --- Create ------------------------------------------------------------------

def test_create_returns_token_and_lan_phone_url(client, monkeypatch):
    monkeypatch.setattr(settings, "LAN_BASE_URL", "http://192.168.7.4:5173")
    res = client.post("/api/v1/pairing")
    assert res.status_code == 201
    data = res.json()
    assert data["token"]
    assert data["status"] == "waiting"
    assert data["expires_in"] == settings.PAIRING_TOKEN_TTL_SECONDS
    assert data["phone_url"] == f"http://192.168.7.4:5173/pair/{data['token']}"
    assert "localhost" not in data["phone_url"]


def test_create_phone_url_null_when_machine_not_lan_reachable(client, monkeypatch):
    monkeypatch.setattr(settings, "LAN_BASE_URL", None)
    monkeypatch.setattr(pairing_svc, "detect_lan_ip", lambda: None)
    data = client.post("/api/v1/pairing").json()
    assert data["token"]  # pairing still works; the laptop UI warns instead of QR
    assert data["phone_url"] is None


def test_loopback_override_is_never_encoded(monkeypatch):
    monkeypatch.setattr(settings, "LAN_BASE_URL", "http://localhost:5173")
    assert pairing_svc.phone_base_url() is None
    monkeypatch.setattr(settings, "LAN_BASE_URL", "http://127.0.0.1:5173")
    assert pairing_svc.phone_base_url() is None


def test_create_never_logs_full_token(client, caplog):
    with caplog.at_level(logging.INFO):
        token = make_token(client)
    assert token, "sanity"
    for record in caplog.records:
        assert token not in record.getMessage()


# --- Status & lifecycle ------------------------------------------------------

def test_status_unknown_token_is_404(client):
    res = client.get("/api/v1/pairing/definitely-not-a-real-token")
    assert res.status_code == 404
    assert "Unknown" in res.json()["detail"]


def test_status_expires_with_410_then_cleans_up(client):
    token = make_token(client)
    assert client.get(f"/api/v1/pairing/{token}").status_code == 200

    # Age the record past its TTL.
    pairing_svc._store[token].created_at -= settings.PAIRING_TOKEN_TTL_SECONDS + 1

    res = client.get(f"/api/v1/pairing/{token}")
    assert res.status_code == 410
    assert "expired" in res.json()["detail"].lower()
    # First lookup reports 410 and removes the entry; the next is unknown.
    assert client.get(f"/api/v1/pairing/{token}").status_code == 404


def test_expired_tokens_swept_when_new_one_is_created(client):
    old = make_token(client)
    pairing_svc._store[old].created_at -= settings.PAIRING_TOKEN_TTL_SECONDS + 1
    make_token(client)  # any create sweeps stale entries
    assert old not in pairing_svc._store


def test_cancel_is_idempotent_and_invalidates_token(client):
    token = make_token(client)
    assert client.delete(f"/api/v1/pairing/{token}").status_code == 204
    assert client.delete(f"/api/v1/pairing/{token}").status_code == 204
    assert client.get(f"/api/v1/pairing/{token}").status_code == 404
    upload = client.post(
        f"/api/v1/pairing/{token}/upload",
        files={"video": ("take.mp4", MP4_HEADER, "video/mp4")},
    )
    assert upload.status_code == 404


# --- Upload: link, single-use, validation reuse ------------------------------

def test_upload_links_session_and_token_is_single_use(client, mock_mongodb):
    token = make_token(client)
    res = client.post(
        f"/api/v1/pairing/{token}/upload",
        files={"video": ("phone-take.mp4", MP4_HEADER, "video/mp4")},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "uploaded"
    session_id = body["session_id"]

    # The session document exists and the poll returns the same id.
    assert session_id in mock_mongodb.docs
    status_res = client.get(f"/api/v1/pairing/{token}")
    assert status_res.status_code == 200
    assert status_res.json() == {"status": "uploaded", "session_id": session_id}

    # Reuse is refused with 410, not a second session.
    reuse = client.post(
        f"/api/v1/pairing/{token}/upload",
        files={"video": ("again.mp4", MP4_HEADER, "video/mp4")},
    )
    assert reuse.status_code == 410
    assert "already used" in reuse.json()["detail"]


def test_upload_unknown_token_is_404(client):
    res = client.post(
        "/api/v1/pairing/unknown-token/upload",
        files={"video": ("take.mp4", MP4_HEADER, "video/mp4")},
    )
    assert res.status_code == 404


def test_upload_rejects_bad_extension_and_token_stays_retryable(client):
    token = make_token(client)
    res = client.post(
        f"/api/v1/pairing/{token}/upload",
        files={"video": ("notes.txt", b"hello world", "text/plain")},
    )
    assert res.status_code == 400
    assert "Unsupported file format" in res.json()["detail"]

    # Failure reverted the token to waiting, so a corrected retry works.
    assert client.get(f"/api/v1/pairing/{token}").json()["status"] == "waiting"
    retry = client.post(
        f"/api/v1/pairing/{token}/upload",
        files={"video": ("take.mp4", MP4_HEADER, "video/mp4")},
    )
    assert retry.status_code == 201


def test_upload_rejects_forged_container_header(client):
    token = make_token(client)
    res = client.post(
        f"/api/v1/pairing/{token}/upload",
        files={"video": ("fake.mp4", b"plain text pretending to be mp4", "video/mp4")},
    )
    assert res.status_code == 400
    assert "Invalid video container" in res.json()["detail"]
    assert client.get(f"/api/v1/pairing/{token}").json()["status"] == "waiting"


def test_upload_enforces_size_cap_and_stays_retryable(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_MB", 1)
    token = make_token(client)
    res = client.post(
        f"/api/v1/pairing/{token}/upload",
        files={"video": ("big.mp4", MP4_HEADER + b"0" * (2 * 1024 * 1024), "video/mp4")},
    )
    assert res.status_code == 413
    assert "exceeds maximum allowed size" in res.json()["detail"]
    assert client.get(f"/api/v1/pairing/{token}").json()["status"] == "waiting"


# --- Token scrubbing in server-level logs -----------------------------------

def test_scrub_tokens_in_text_replaces_tokens_with_digests():
    token = "D9nx1JpQdl2iAovQLR679jiKZVhqTJIm6Fp-7N89J-Y"
    digest = pairing_svc.token_log_prefix(token)
    line = (
        f'127.0.0.1:55078 - "GET /api/v1/pairing/{token} HTTP/1.1" 200 OK'
    )
    scrubbed = pairing_svc.scrub_tokens_in_text(line)
    assert token not in scrubbed
    assert f"/api/v1/pairing/{digest}" in scrubbed
    # Non-pairing lines pass through untouched.
    assert pairing_svc.scrub_tokens_in_text(
        '127.0.0.1:5000 - "GET /api/v1/sessions/abc HTTP/1.1" 200 OK'
    ) == '127.0.0.1:5000 - "GET /api/v1/sessions/abc HTTP/1.1" 200 OK'


def test_access_log_filter_scrubs_uvicorn_records():
    """The uvicorn access log prints request paths, which for pairing status
    polls and uploads embed the token — the scrub filter must rewrite them
    before the line reaches any handler."""
    token = "D9nx1JpQdl2iAovQLR679jiKZVhqTJIm6Fp-7N89J-Y"
    flt = pairing_svc.PairingTokenScrubFilter()
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %s',
        args=(
            "127.0.0.1:55078",
            "GET",
            f"/api/v1/pairing/{token}",
            "1.1",
            "200 OK",
        ),
        exc_info=None,
    )
    assert flt.filter(record) is True
    # Args keep their 5-tuple shape (uvicorn's AccessFormatter unpacks them).
    assert len(record.args) == 5
    message = record.getMessage()
    assert token not in message
    assert f"/api/v1/pairing/{pairing_svc.token_log_prefix(token)}" in message


def test_scrubbed_access_record_formats_with_uvicorn_formatter():
    """Regression: clearing record.args made uvicorn's AccessFormatter crash
    ("not enough values to unpack"), silently dropping the log line. The
    scrub must leave the record formattable by uvicorn itself."""
    from uvicorn.logging import AccessFormatter

    token = "D9nx1JpQdl2iAovQLR679jiKZVhqTJIm6Fp-7N89J-Y"
    flt = pairing_svc.PairingTokenScrubFilter()
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %s',
        args=(
            "127.0.0.1:55078",
            "GET",
            f"/api/v1/pairing/{token}",
            "1.1",
            "200",  # uvicorn passes the bare code; the formatter adds the phrase
        ),
        exc_info=None,
    )
    flt.filter(record)
    # use_colors=False skips the record attrs colourized formatting needs;
    # formatMessage builds client_addr/request_line/status_code itself.
    formatted = AccessFormatter(use_colors=False).format(record)
    assert token not in formatted
    assert pairing_svc.token_log_prefix(token) in formatted
