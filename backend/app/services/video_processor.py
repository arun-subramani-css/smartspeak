import asyncio
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import shutil
import subprocess
import cv2

from app.config import settings
from app.db.mongodb import MongoDB
from app.models.session import SessionStatus
from app.services import progress as progress_svc
from app.services.speech_analyzer import process_speech_analysis_session
from app.services.visual_analyzer import process_visual_analysis_session
from app.services.fusion_engine import process_fusion_session

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


def _handle_task_completion(task: asyncio.Task, session_id: str, task_name: str):
    """
    Done callback for auto-chained background analysis tasks.
    Catches unhandled exceptions and updates MongoDB status to 'failed' to prevent silent hangs.
    """
    try:
        task.result()
    except asyncio.CancelledError:
        logger.warning(f"[{session_id}] Task {task_name} was cancelled during event loop shutdown.")
    except Exception as exc:
        err_msg = f"Auto-chained {task_name} analysis failed: {str(exc)}"
        logger.exception(f"[{session_id}] {err_msg}")
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                Database.get_collection("sessions").update_one(
                    {"session_id": session_id},
                    {"$set": {"status": SessionStatus.FAILED, "error_reason": err_msg}}
                )
            )
        except Exception as e:
            logger.error(f"[{session_id}] Failed to set DB status to failed: {e}")


async def process_video_session(session_id: str) -> bool:
    """
    Background worker task to extract audio (16kHz mono WAV) and video frames (1 fps) for a session.
    Upon completion, auto-chains into Speech Analysis and Visual Analysis in parallel.
    """
    sessions_col = MongoDB.get_collection("sessions")

    # Fetch session record
    session_doc = await sessions_col.find_one({"session_id": session_id})
    if not session_doc:
        matches = list(settings.staging_dir.glob(f"{session_id}.*"))
        if matches:
            staging_file = matches[0]
            file_size = staging_file.stat().st_size
            ext = staging_file.suffix
            session_doc = {
                "session_id": session_id,
                "original_filename": f"video{ext}",
                "upload_timestamp": datetime.now(timezone.utc),
                "file_size": file_size,
                "content_type": f"video/{ext.lstrip('.')}",
                "status": SessionStatus.PROCESSING,
                "file_path": str(staging_file)
            }
            await sessions_col.insert_one(session_doc)
            logger.info(f"Auto-recovered session document in DB for {session_id}")
        else:
            logger.error(f"Session {session_id} not found in database or staging directory.")
            return False

    # Update status to processing
    await sessions_col.update_one(
        {"session_id": session_id},
        {"$set": {"status": SessionStatus.PROCESSING}}
    )

    try:
        staging_file = Path(session_doc.get("file_path", ""))
        if not staging_file.exists():
            matches = list(settings.staging_dir.glob(f"{session_id}.*"))
            if matches:
                staging_file = matches[0]
            else:
                raise FileNotFoundError(f"Staged video file for session '{session_id}' not found.")

        session_processed_dir = settings.processed_dir / session_id
        frames_dir = session_processed_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        audio_path = session_processed_dir / "audio.wav"

        # Step 1: Extract Audio using FFmpeg (16kHz mono WAV, voice-optimized enhancement chain)
        ffmpeg_bin = get_ffmpeg_binary()
        logger.info(f"[{session_id}] Extracting audio with FFmpeg ({ffmpeg_bin})...")

        # Voice-focused filter chain:
        #   1. highpass       -> removes low-frequency rumble (AC hum, desk thumps, wind, mic booms)
        #   2. afftdn         -> FFT-based broadband noise reduction (fans, AC units, room hiss)
        #   3. lowpass        -> removes high-frequency hiss/sibilance noise above the voice band
        #   4. loudnorm       -> normalizes speech loudness so quiet speakers decode reliably
        # Kept intentionally lightweight (no model download) and always-on for consistency.
        audio_filters = [
            f"highpass=f={settings.AUDIO_HIGH_PASS_HZ}",
            f"afftdn=nr={settings.AUDIO_NOISE_REDUCTION_DB}:nf=-25",
            f"lowpass=f={settings.AUDIO_LOW_PASS_HZ}",
            "loudnorm=I=-16:TP=-1.5:LRA=11",
        ]
        filter_chain = ",".join(audio_filters)
        logger.info(f"[{session_id}] Audio enhancement chain: {filter_chain}")

        ffmpeg_cmd_enhanced = [
            ffmpeg_bin,
            "-y",
            "-i", str(staging_file),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-af", filter_chain,
            "-c:a", "pcm_s16le",
            str(audio_path)
        ]

        # Fallback chain without denoiser for older ffmpeg builds lacking afftdn
        ffmpeg_cmd_norm = [
            ffmpeg_bin,
            "-y",
            "-i", str(staging_file),
            "-vn",
            "-ac", "1",
            "-ar", "16000",
            "-af", f"highpass=f={settings.AUDIO_HIGH_PASS_HZ},loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "pcm_s16le",
            str(audio_path)
        ]

        def _run_audio_ffmpeg():
            res = subprocess.run(ffmpeg_cmd_enhanced, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0:
                logger.warning(f"[{session_id}] Enhanced audio chain failed; retrying without denoiser. stderr: {res.stderr.decode(errors='replace')[-200:]}")
                # Fallback to high-pass + loudness normalization only (skips afftdn)
                res = subprocess.run(ffmpeg_cmd_norm, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode != 0:
                logger.warning(f"[{session_id}] Filtered audio chain failed; falling back to plain extraction. stderr: {res.stderr.decode(errors='replace')[-200:]}")
                # Final fallback: plain 16kHz mono extraction with no filters at all
                ffmpeg_cmd_basic = [
                    ffmpeg_bin,
                    "-y",
                    "-i", str(staging_file),
                    "-vn",
                    "-ac", "1",
                    "-ar", "16000",
                    "-c:a", "pcm_s16le",
                    str(audio_path)
                ]
                res = subprocess.run(ffmpeg_cmd_basic, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return res.returncode, res.stderr.decode(errors="replace")

        loop = asyncio.get_running_loop()
        returncode, err_msg = await loop.run_in_executor(None, _run_audio_ffmpeg)

        if returncode != 0:
            logger.error(f"[{session_id}] FFmpeg audio extraction failed: {err_msg}")
            raise RuntimeError(f"FFmpeg audio extraction failed: {err_msg[-300:]}")

        # Step 2: Extract Video Frames (FFmpeg fast extraction with OpenCV fallback)
        sample_rate = max(0.1, settings.FRAME_SAMPLE_RATE_FPS)
        logger.info(f"[{session_id}] Extracting frames with FFmpeg at {sample_rate} fps...")
        frame_pattern = str(frames_dir / "frame_%04d.jpg")
        ffmpeg_frames_cmd = [
            ffmpeg_bin,
            "-y",
            "-i", str(staging_file),
            "-vf", f"fps={sample_rate},scale='min(1280,iw)':-2",
            "-q:v", "3",
            frame_pattern
        ]

        def _run_frames_ffmpeg():
            res = subprocess.run(ffmpeg_frames_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return res.returncode

        await loop.run_in_executor(None, _run_frames_ffmpeg)
        saved_count = len(list(frames_dir.glob("frame_*.jpg")))

        if saved_count == 0:
            logger.info(f"[{session_id}] FFmpeg frame extraction returned 0 frames; falling back to OpenCV...")
            cap = cv2.VideoCapture(str(staging_file))
            if not cap.isOpened():
                raise ValueError("OpenCV failed to open video file. Video may be corrupted or codec unsupported.")

            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            if fps <= 0 or total_frames <= 0:
                cap.release()
                raise ValueError("Corrupted video file: invalid frame rate or frame count.")

            step = max(1, int(round(fps / sample_rate)))
            current_frame = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if current_frame % step == 0:
                    saved_count += 1
                    frame_name = f"frame_{saved_count:04d}.jpg"
                    frame_path = frames_dir / frame_name
                    cv2.imwrite(str(frame_path), frame)

                current_frame += 1

            cap.release()

        if saved_count == 0:
            raise ValueError("No frames could be extracted from video.")

        logger.info(f"[{session_id}] Audio & frame extraction completed. Updating DB and auto-chaining speech & visual analysis concurrently...")

        now = datetime.now(timezone.utc)
        await sessions_col.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": SessionStatus.PROCESSED,
                    "processed_at": now,
                    "audio_path": str(audio_path.relative_to(settings.base_storage_path)),
                    "frame_count": saved_count,
                    "error_reason": None,
                    "progress_stage": "analyzing"
                },
                "$unset": {"speech_progress": "", "visual_progress": ""}
            }
        )

        # Auto-chain Speech Analysis and Visual Analysis in parallel and await completion
        speech_task = asyncio.create_task(process_speech_analysis_session(session_id))
        speech_task.add_done_callback(lambda t: _handle_task_completion(t, session_id, "speech"))

        visual_task = asyncio.create_task(process_visual_analysis_session(session_id))
        visual_task.add_done_callback(lambda t: _handle_task_completion(t, session_id, "visual"))

        await asyncio.gather(speech_task, visual_task, return_exceptions=True)

        # Auto-chain Feature Fusion analysis if ready
        doc = await sessions_col.find_one({"session_id": session_id})
        if doc and doc.get("status") == SessionStatus.READY_FOR_FUSION:
            logger.info(f"[{session_id}] Auto-chaining Feature Fusion analysis...")
            progress_svc.set_stage(session_id, "fusion")
            await process_fusion_session(session_id)

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
