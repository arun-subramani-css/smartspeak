from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    SPEECH_ANALYSIS_COMPLETE = "speech_analysis_complete"
    FAILED = "failed"


class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float
    probability: float | None = None


class FillerWordItem(BaseModel):
    word: str
    timestamp: float


class PauseItem(BaseModel):
    start_time: float
    end_time: float
    duration: float


class RepetitionItem(BaseModel):
    phrase: str
    timestamp: float
    count: int


class WindowedWPM(BaseModel):
    window_start: float
    window_end: float
    wpm: float


class WPMData(BaseModel):
    overall_wpm: float
    total_words: int
    total_speaking_duration_seconds: float
    windowed_wpm: list[WindowedWPM] = []


class SpeechAnalysisResult(BaseModel):
    transcript_text: str
    words: list[WordTimestamp] = []
    filler_words: list[FillerWordItem] = []
    filler_word_count: int = 0
    wpm_data: WPMData
    long_pauses: list[PauseItem] = []
    repetitions: list[RepetitionItem] = []
    analyzed_at: datetime


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
    speech_analysis: SpeechAnalysisResult | None = None


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
    has_speech_analysis: bool = False


class SpeechAnalysisResponse(BaseModel):
    session_id: str
    status: SessionStatus
    speech_analysis: SpeechAnalysisResult
