import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables or defaults."""

    MONGODB_URL: str = "mongodb://localhost:27017"
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
