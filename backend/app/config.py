import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables or defaults."""

    MONGODB_URI: str | None = None
    MONGODB_DB_NAME: str = "smartspeak"
    STORAGE_DIR: str = "./data"
    MODELS_DIR: str | None = None
    MAX_UPLOAD_SIZE_MB: int = 500
    ALLOWED_EXTENSIONS: list[str] = [".mp4", ".avi", ".mov"]
    FRAME_SAMPLE_RATE_FPS: float = 1.0
    RETENTION_DAYS: int = 30
    CLEANUP_INTERVAL_HOURS: int = 24
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    # Prewarm heavy ML models (Whisper, spaCy, confidence classifier) in a
    # background thread at startup so the first upload doesn't pay load latency.
    PREWARM_MODELS: bool = True

    # Audio Enhancement for Speech-to-Text Accuracy
    # FFmpeg filter chain applied to the extracted WAV before Whisper runs.
    AUDIO_ENABLE_DENOISE: bool = True
    AUDIO_NOISE_REDUCTION_DB: float = 12.0   # afftdn noise-reduction strength (dB)
    AUDIO_HIGH_PASS_HZ: float = 80.0         # cuts rumble/hum below the human voice band
    AUDIO_LOW_PASS_HZ: float = 8000.0        # cuts hiss/sibilance above the voice band

    # Speech Analysis Configuration
    WHISPER_MODEL: str = "base"
    # beam_size=1 (greedy) is ~3.5x faster than beam_size=5 with near-identical
    # accuracy when the audio is denoised upstream; raise it only for very noisy
    # recordings. Keep WHISPER_CONDITION_ON_PREVIOUS_TEXT=False to avoid
    # repetition loops on noisy audio.
    WHISPER_BEAM_SIZE: int = 1
    WHISPER_CONDITION_ON_PREVIOUS_TEXT: bool = False
    ALWAYS_FILLER: list[str] = ["um", "uh"]
    CONTEXTUAL_FILLER: list[str] = ["like", "actually", "basically", "you know"]
    FILLER_WORDS: list[str] = ["um", "uh", "like", "you know", "actually", "basically"]
    LONG_PAUSE_THRESHOLD_SECONDS: float = 2.0
    WPM_WINDOW_SECONDS: float = 15.0
    WPM_WINDOW_STEP_SECONDS: float = 5.0

    # Visual Analysis Configuration
    EYE_CONTACT_SAMPLING_FPS: float = 2.5
    # Parallel workers for the eye-contact/head-pose pass (each worker gets its
    # own VideoCapture + MediaPipe instances; capped at CPU count).
    EYE_CONTACT_MAX_WORKERS: int = 3
    LOOKING_AWAY_MIN_DURATION_SECONDS: float = 2.0
    POSTURE_SHOULDER_TILT_THRESHOLD: float = 10.0
    POSTURE_SPINE_ANGLE_THRESHOLD: float = 15.0
    GESTURE_TOO_FEW_THRESHOLD_PCT: float = 15.0
    GESTURE_TOO_MANY_THRESHOLD_PCT: float = 60.0
    HEAD_MOVEMENT_ANGLE_THRESHOLD: float = 15.0

    # Baseline-relative eye-contact calibration. Absolute solvePnP head angles
    # are biased by camera height/placement (a laptop webcam below eye level
    # shifts every frame past the +/-15 deg cutoffs, systematically reporting
    # ~0% eye contact). When enabled, head pose is measured as deviation from
    # the speaker's own median pose for the session instead of absolute angles.
    EYE_CONTACT_BASELINE_RELATIVE: bool = True
    EYE_CONTACT_YAW_TOLERANCE_DEG: float = 8.0          # deviation from baseline counted as looking away
    EYE_CONTACT_PITCH_DOWN_TOLERANCE_DEG: float = 10.0  # deviation below baseline counted as looking down

    # Head-movement scoring: raw per-sample angle deltas over-flag natural
    # motion at 2.5 fps sampling (any glance between samples looks like a 15 deg
    # jump). When enabled, the pose series is median-smoothed and triggers are
    # based on angular velocity (deg/second) between consecutive samples.
    HEAD_MOVEMENT_USE_VELOCITY: bool = True
    HEAD_MOVEMENT_SMOOTHING_WINDOW: int = 5             # samples (~2s at 2.5 fps)
    HEAD_MOVEMENT_VELOCITY_THRESHOLD_DEG_S: float = 45.0

    # Use the trained posture classifier (models/posture_model.pkl) instead of
    # fixed shoulder/spine angle thresholds. Falls back to thresholds when the
    # model file is missing or fails to load.
    POSTURE_USE_MODEL: bool = True

    # Transcription engine: "faster" (faster-whisper/CTranslate2, int8 CPU) or
    # "openai" (openai-whisper, PyTorch). Falls back to openai-whisper when the
    # faster-whisper package is unavailable.
    WHISPER_ENGINE: str = "faster"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def models_dir(self) -> Path:
        """Resolve the directory holding trained model artifacts (.pkl files).

        Priority: explicit MODELS_DIR environment setting, otherwise the
        repository-root ``models/`` directory. The fallback is resolved
        relative to this source file (backend/app/config.py -> parents[2] is
        the repository root), so it is independent of the working directory
        and portable across machines.
        """
        if self.MODELS_DIR:
            return Path(self.MODELS_DIR).expanduser().resolve()
        return (Path(__file__).resolve().parents[2] / "models").resolve()

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def base_storage_path(self) -> Path:
        return Path(self.STORAGE_DIR).resolve()

    @property
    def staging_dir(self) -> Path:
        path = self.base_storage_path / "staging"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def processed_dir(self) -> Path:
        path = self.base_storage_path / "processed"
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
