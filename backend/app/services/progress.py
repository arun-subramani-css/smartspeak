"""Live analysis progress reporting for the processing pipeline.

The pipeline runs long stages (Whisper transcription, MediaPipe passes) in
background threads while the frontend polls the session status endpoint.
This module publishes lightweight progress snapshots to the session document
so the status page can show real progress instead of a static spinner.

Design notes:
- Writes use flat top-level fields (speech_progress / visual_progress /
  progress_stage) so they never require read-modify-write merges; speech and
  visual stages run in parallel and each only touches its own field.
- Reports are throttled per (session, field) because the local JSON document
  store rewrites its file on every update.
- Safe to call from async functions (schedules a task on the running loop) or
  from worker threads (schedules onto the captured startup loop).
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.db.mongodb import MongoDB

logger = logging.getLogger(__name__)

_main_loop: Optional[asyncio.AbstractEventLoop] = None
_last_report: dict = {}


def set_event_loop(loop: Optional[asyncio.AbstractEventLoop]) -> None:
    """Capture the app's main event loop so worker threads can report progress."""
    global _main_loop
    _main_loop = loop


def _should_report(session_id: str, field: str, percent: float) -> bool:
    key = (session_id, field)
    now = time.monotonic()
    last_percent, last_time = _last_report.get(key, (-1.0, 0.0))
    # Report on >=5% change or >=3s since the last write, whichever first.
    if (percent - last_percent) >= 5.0 or (now - last_time) >= 3.0:
        _last_report[key] = (percent, now)
        return True
    return False


async def _write(session_id: str, field: str, percent: float, detail: str) -> None:
    try:
        col = MongoDB.get_collection("sessions")
        await col.update_one(
            {"session_id": session_id},
            {"$set": {field: {"percent": round(float(percent), 1), "detail": detail,
                              "updated_at": datetime.now(timezone.utc)}}},
        )
    except Exception as exc:  # never let progress reporting break analysis
        logger.debug(f"[{session_id}] progress write failed: {exc}")


def report_progress(session_id: str, field: str, percent: float, detail: str = "",
                    force: bool = False) -> None:
    """Report progress for one pipeline stage field ('speech_progress'/'visual_progress').

    Throttled unless force=True. Callable from sync worker threads.
    """
    percent = max(0.0, min(100.0, float(percent)))
    if not force and not _should_report(session_id, field, percent):
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_write(session_id, field, percent, detail))
        return
    except RuntimeError:
        pass
    if _main_loop is not None and _main_loop.is_running():
        asyncio.run_coroutine_threadsafe(_write(session_id, field, percent, detail), _main_loop)


def clear_progress(session_id: str, fields=("speech_progress", "visual_progress")) -> None:
    """Clear stage progress fields (called when the pipeline completes)."""
    for field in fields:
        async def _clear(f=field):
            try:
                col = MongoDB.get_collection("sessions")
                await col.update_one({"session_id": session_id}, {"$set": {f: None}})
            except Exception:
                pass
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_clear())
        except RuntimeError:
            if _main_loop is not None and _main_loop.is_running():
                asyncio.run_coroutine_threadsafe(_clear(), _main_loop)


def set_stage(session_id: str, stage: str) -> None:
    """Set the coarse pipeline stage ('processing'/'analyzing'/'fusion'/'done')."""
    async def _write_stage():
        try:
            col = MongoDB.get_collection("sessions")
            await col.update_one({"session_id": session_id}, {"$set": {"progress_stage": stage}})
        except Exception:
            pass
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_write_stage())
    except RuntimeError:
        if _main_loop is not None and _main_loop.is_running():
            asyncio.run_coroutine_threadsafe(_write_stage(), _main_loop)
