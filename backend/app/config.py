import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables or defaults."""

    MONGODB_URI: str | None = None
    MONGODB_DB_NAME: str = "smartspeak"
    STORAGE_DIR: str = "./data"
    MAX_UPLOAD_SIZE_MB: int = 500
    ALLOWED_EXTENSIONS: list[str] = [".mp4", ".avi", ".mov"]
    FRAME_SAMPLE_RATE_FPS: float = 1.0
    RETENTION_DAYS: int = 30
    CLEANUP_INTERVAL_HOURS: int = 24
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Speech Analysis Configuration
    WHISPER_MODEL: str = "base"
    ALWAYS_FILLER: list[str] = ["um", "uh"]
    CONTEXTUAL_FILLER: list[str] = ["like", "actually", "basically", "you know"]
    FILLER_WORDS: list[str] = ["um", "uh", "like", "you know", "actually", "basically"]
    LONG_PAUSE_THRESHOLD_SECONDS: float = 2.0
    WPM_WINDOW_SECONDS: float = 15.0
    WPM_WINDOW_STEP_SECONDS: float = 5.0

    # Visual Analysis Configuration
    EYE_CONTACT_SAMPLING_FPS: float = 5.0
    LOOKING_AWAY_MIN_DURATION_SECONDS: float = 2.0
    POSTURE_SHOULDER_TILT_THRESHOLD: float = 10.0
    POSTURE_SPINE_ANGLE_THRESHOLD: float = 15.0
    GESTURE_TOO_FEW_THRESHOLD_PCT: float = 15.0
    GESTURE_TOO_MANY_THRESHOLD_PCT: float = 60.0
    HEAD_MOVEMENT_ANGLE_THRESHOLD: float = 15.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

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
