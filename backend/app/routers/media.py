import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.background import BackgroundTask

from app.config import settings
from app.db.mongodb import MongoDB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["Media"])

CHUNK_SIZE = 1024 * 1024          # 1 MiB generator chunks for streaming
RANGE_HEADER_RE = re.compile(r"bytes=(\d*)-(\d*)$")

VIDEO_EXTENSIONS = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}


def _find_session_video(session_id: str) -> Path | None:
    """
    Locates the stored video for a session, preferring the processed copy
    (survives staging cleanup) and falling back to the staging upload.
    Only returns files whose container type the browser can play natively.
    """
    processed_dir = settings.base_storage_path / "processed" / session_id
    candidates: list[Path] = []
    if processed_dir.is_dir():
        candidates.extend(p for p in processed_dir.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS)
    if settings.staging_dir.is_dir():
        candidates.extend(
            p for p in settings.staging_dir.glob(f"{session_id}.*")
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
        )
    if not candidates:
        return None
    # Prefer mp4 (universally playable), then largest file
    candidates.sort(key=lambda p: (p.suffix.lower() != ".mp4", -p.stat().st_size))
    return candidates[0]


def _parse_range_header(range_header: str, file_size: int) -> tuple[int, int]:
    """Parses a single-range `bytes=start-end` header into (start, end) inclusive."""
    match = RANGE_HEADER_RE.match(range_header.strip())
    if not match:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail="Malformed Range header."
        )
    start_str, end_str = match.group(1), match.group(2)

    if start_str == "":
        # suffix form: bytes=-N → last N bytes
        length = int(end_str)
        if length == 0:
            raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid range.")
        start = max(0, file_size - length)
        end = file_size - 1
    else:
        start = int(start_str)
        end = int(end_str) if end_str else file_size - 1

    if start >= file_size or start > end:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            detail=f"Requested range not satisfiable for file of size {file_size}."
        )
    return start, min(end, file_size - 1)


def _file_chunk_generator(path: Path, start: int, end: int):
    """Yields file bytes [start, end] in bounded chunks so streams close promptly."""
    with path.open("rb") as f:
        f.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = f.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/{session_id}/video")
async def stream_session_video(session_id: str, request: Request):
    """
    Streams the session's stored video with HTTP range support so the browser
    can seek arbitrarily. Returns 404 when the video file no longer exists
    (old sessions or retention-cleaned sessions).
    """
    sessions_col = MongoDB.get_collection("sessions")
    session = await sessions_col.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' was not found.")

    video_path = _find_session_video(session_id)
    if video_path is None or not video_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file is not available for this session.")

    file_size = video_path.stat().st_size
    media_type = VIDEO_EXTENSIONS[video_path.suffix.lower()]

    range_header = request.headers.get("range")
    if range_header:
        start, end = _parse_range_header(range_header, file_size)
        content_length = end - start + 1
        return StreamingResponse(
            _file_chunk_generator(video_path, start, end),
            status_code=206,
            media_type=media_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Cache-Control": "private, max-age=3600",
            },
        )

    # Full-file response (still chunked off disk; no memory blow-up)
    return StreamingResponse(
        _file_chunk_generator(video_path, 0, file_size - 1),
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/{session_id}/video/status")
async def session_video_status(session_id: str):
    """
    Lightweight probe so the UI can decide whether to mount the video player:
    returns whether the file exists, its size, and its content type.
    """
    sessions_col = MongoDB.get_collection("sessions")
    session = await sessions_col.find_one({"session_id": session_id})
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' was not found.")

    video_path = _find_session_video(session_id)
    if video_path is None or not video_path.exists():
        return JSONResponse({"available": False, "url": None, "size_bytes": None, "content_type": None})

    return JSONResponse({
        "available": True,
        "url": f"/api/v1/sessions/{session_id}/video",
        "size_bytes": video_path.stat().st_size,
        "content_type": VIDEO_EXTENSIONS[video_path.suffix.lower()],
    })
