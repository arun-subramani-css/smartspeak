from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    SPEECH_ANALYSIS_COMPLETE = "speech_analysis_complete"
    VISUAL_ANALYSIS_COMPLETE = "visual_analysis_complete"
    READY_FOR_FUSION = "ready_for_fusion"
    FUSION_COMPLETE = "fusion_complete"
    FAILED = "failed"


# --- Speech Analysis Models ---

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
    average_transcription_confidence: float | None = None


# --- Visual Analysis Models ---

class EyeContactRange(BaseModel):
    start_time: float
    end_time: float
    duration: float
    category: str = "looking_away"  # "looking_away" or "looking_down"


class EyeContactData(BaseModel):
    eye_contact_percentage: float
    looking_away_count: int
    looking_down_count: int = 0
    looking_away_ranges: list[EyeContactRange] = []
    average_detection_confidence: float | None = None
    fallback_frame_count: int = 0
    no_detection_frame_count: int = 0


class PostureRange(BaseModel):
    start_time: float
    end_time: float
    duration: float


class PostureData(BaseModel):
    posture_score: float
    poor_posture_ranges: list[PostureRange] = []
    total_frames_analyzed: int = 0
    good_posture_count: int = 0
    average_detection_confidence: float | None = None
    fallback_frame_count: int = 0
    no_detection_frame_count: int = 0


class GestureData(BaseModel):
    gesture_frequency_count: int
    active_hand_percentage: float
    gesture_usage_classification: str  # "too_few", "average", "too_many"
    average_detection_confidence: float | None = None
    fallback_frame_count: int = 0
    no_detection_frame_count: int = 0


class HeadMovementData(BaseModel):
    head_movement_score: float
    excessive_movement_timestamps: list[float] = []
    excessive_movement_count: int = 0


class VisualAnalysisResult(BaseModel):
    eye_contact: EyeContactData
    posture: PostureData
    gesture: GestureData
    head_movement: HeadMovementData
    analyzed_at: datetime


class ConfidenceAnalysisResult(BaseModel):
    confidence_score: float
    label_distribution: str
    frames_analyzed: int
    frames_skipped: int


class ConfidenceAnalysisResponse(BaseModel):
    session_id: str
    status: SessionStatus
    confidence_analysis: ConfidenceAnalysisResult


# --- Fusion & Mistake Detection Models ---

class MistakeItem(BaseModel):
    timestamp: float
    category: str  # "speech", "visual", "compound"
    description: str
    severity: str  # "minor", "medium", "high"
    events: list[str] | None = None


class FusionReportResult(BaseModel):
    mistakes: list[MistakeItem] = []
    smartspeak_index: float
    grade: str  # "Needs Practice", "Competent", "Polished", "Executive"
    verbal_score: float
    non_verbal_score: float
    ml_confidence_score: float
    analyzed_at: datetime


# --- Session Base & Document Models ---

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
    visual_analysis: VisualAnalysisResult | None = None
    confidence_analysis: ConfidenceAnalysisResult | None = None
    fusion_report: FusionReportResult | None = None


# --- Response Models ---

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
    has_visual_analysis: bool = False
    has_fusion_report: bool = False


class SpeechAnalysisResponse(BaseModel):
    session_id: str
    status: SessionStatus
    speech_analysis: SpeechAnalysisResult


class VisualAnalysisResponse(BaseModel):
    session_id: str
    status: SessionStatus
    visual_analysis: VisualAnalysisResult


class FusionReportResponse(BaseModel):
    session_id: str
    status: SessionStatus
    fusion_report: FusionReportResult

