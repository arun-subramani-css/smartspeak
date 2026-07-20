from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class SessionBase(BaseModel):
    session_id: str
    original_filename: str
    upload_timestamp: datetime
    file_size: int
    content_type: str


class SessionDocument(SessionBase):
    status: SessionStatus = SessionStatus.UPLOADED
    error_reason: str | None = None
    processed_at: datetime | None = None
    audio_path: str | None = None
    frame_count: int | None = None
    file_path: str | None = None


class UploadResponse(BaseModel):
    session_id: str
    status: SessionStatus
    message: str
    original_filename: str
    file_size: int
    upload_timestamp: datetime


class StatusResponse(BaseModel):
    session_id: str
    status: SessionStatus
    original_filename: str
    upload_timestamp: datetime
    file_size: int
    content_type: str
    error_reason: str | None = None
    processed_at: datetime | None = None
    audio_path: str | None = None
    frame_count: int | None = None
