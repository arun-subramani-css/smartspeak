import asyncio
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import shutil
import cv2

from app.config import settings
from app.db.mongodb import MongoDB
from app.models.session import SessionStatus

logger = logging.getLogger(__name__)


def get_ffmpeg_binary() -> str:
    """Find system ffmpeg binary or fallback to imageio_ffmpeg bundled binary."""
    binary = shutil.which("ffmpeg")
    if binary:
        return binary
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception as e:
        logger.warning(f"Could not load imageio_ffmpeg: {e}")
    return "ffmpeg"


async def process_video_session(session_id: str) -> bool:
    """
    Background worker task to extract audio (16kHz mono WAV) and video frames (1 fps) for a session.
    Updates MongoDB session document with progress and completion status.
    """
    sessions_col = MongoDB.get_collection("sessions")

    # Fetch session record
    session_doc = await sessions_col.find_one({"session_id": session_id})
    if not session_doc:
        logger.error(f"Session {session_id} not found in database.")
        return False

    # Update status to processing
    await sessions_col.update_one(
        {"session_id": session_id},
        {"$set": {"status": SessionStatus.PROCESSING}}
    )

    try:
        staging_file = Path(session_doc.get("file_path", ""))
        if not staging_file.exists():
            # Try searching in staging directory by session_id prefix
            matches = list(settings.staging_dir.glob(f"{session_id}.*"))
            if matches:
                staging_file = matches[0]
            else:
                raise FileNotFoundError(f"Staged video file for session '{session_id}' not found.")

        # Create output directory structure: /processed/{session_id}/
        session_processed_dir = settings.processed_dir / session_id
        frames_dir = session_processed_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        audio_path = session_processed_dir / "audio.wav"

        # Step 1: Extract Audio using FFmpeg (16kHz mono WAV)
        ffmpeg_bin = get_ffmpeg_binary()
        logger.info(f"[{session_id}] Extracting audio with FFmpeg ({ffmpeg_bin})...")
        ffmpeg_cmd = [
            ffmpeg_bin,
            "-y",
            "-i", str(staging_file),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(audio_path)
        ]

        proc = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr.decode(errors="replace")
            logger.error(f"[{session_id}] FFmpeg audio extraction failed: {err_msg}")
            raise RuntimeError(f"FFmpeg audio extraction failed: {err_msg[-300:]}")

        # Step 2: Extract Video Frames using OpenCV (1 fps default)
        logger.info(f"[{session_id}] Extracting frames with OpenCV...")
        cap = cv2.VideoCapture(str(staging_file))
        if not cap.isOpened():
            raise ValueError("OpenCV failed to open video file. Video may be corrupted or codec unsupported.")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        if fps <= 0 or total_frames <= 0:
            cap.release()
            raise ValueError("Corrupted video file: invalid frame rate or frame count.")

        # Calculate sampling step (frames to skip per saved frame)
        sample_rate = max(0.1, settings.FRAME_SAMPLE_RATE_FPS)
        step = max(1, int(round(fps / sample_rate)))

        saved_count = 0
        current_frame = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if current_frame % step == 0:
                saved_count += 1
                frame_name = f"frame_{saved_count:04d}.jpg"
                frame_path = frames_dir / frame_name
                success = cv2.imwrite(str(frame_path), frame)
                if not success:
                    logger.warning(f"Failed to write frame file {frame_path}")

            current_frame += 1

        cap.release()

        if saved_count == 0:
            raise ValueError("No frames could be extracted from video.")

        logger.info(f"[{session_id}] Successfully extracted {saved_count} frames and audio track.")

        # Step 3: Update session status to PROCESSED in MongoDB
        now = datetime.now(timezone.utc)
        await sessions_col.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": SessionStatus.PROCESSED,
                    "processed_at": now,
                    "audio_path": str(audio_path.relative_to(settings.base_storage_path)),
                    "frame_count": saved_count,
                    "error_reason": None
                }
            }
        )
        return True

    except Exception as exc:
        err_reason = str(exc)
        logger.exception(f"[{session_id}] Video processing failed: {err_reason}")
        await sessions_col.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": SessionStatus.FAILED,
                    "error_reason": err_reason
                }
            }
        )
        return False
