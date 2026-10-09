"""Shared video ingest: validate → stage → record → dispatch.

Used by both POST /api/v1/upload (laptop file/practice uploads) and the
phone-pairing upload endpoint, so format/size validation, the staging path,
the MongoDB session record, and background processing stay byte-for-byte
identical between the two entry points.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, HTTPException, status, UploadFile

from app.config import settings
from app.db.mongodb import MongoDB
from app.models.session import SessionDocument, SessionStatus
from app.services.file_validator import validate_upload_file
from app.services.video_processor import process_video_session

logger = logging.getLogger(__name__)


async def ingest_video_upload(
    background_tasks: BackgroundTasks, video: UploadFile
) -> tuple[str, int, datetime]:
    """Validate and persist one uploaded video, then schedule analysis.

    Returns (session_id, file_size, upload_timestamp).
    Raises HTTPException 400 (bad format/header), 413 (too large) or 500
    (write failure) — the exact same errors as before the helper existed.
    """
    # 1. Validate extension and container header
    ext = await validate_upload_file(video)

    # 2. Generate UUID session ID
    session_id = str(uuid.uuid4())
    staging_file_path = settings.staging_dir / f"{session_id}{ext}"

    # 3. Save file stream to staging directory with strict size enforcement
    file_size = 0
    chunk_size = 1024 * 1024  # 1MB chunks

    try:
        with open(staging_file_path, "wb") as out_file:
            while chunk := await video.read(chunk_size):
                file_size += len(chunk)
                if file_size > settings.max_upload_size_bytes:
                    # Cleanup partial file
                    out_file.close()
                    if staging_file_path.exists():
                        staging_file_path.unlink()
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB.",
                    )
                out_file.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        if staging_file_path.exists():
            staging_file_path.unlink()
        logger.exception("File upload streaming failed.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write uploaded file to disk: {str(exc)}",
        ) from exc

    # 4. Insert metadata record in MongoDB
    upload_now = datetime.now(timezone.utc)
    session_doc = SessionDocument(
        session_id=session_id,
        original_filename=video.filename,
        upload_timestamp=upload_now,
        file_size=file_size,
        content_type=video.content_type or f"video/{ext.lstrip('.')}",
        status=SessionStatus.UPLOADED,
        file_path=str(staging_file_path),
    )

    sessions_col = MongoDB.get_collection("sessions")
    await sessions_col.insert_one(session_doc.model_dump())

    # 5. Dispatch async background processing task (Module 2)
    background_tasks.add_task(process_video_session, session_id)

    logger.info(
        "Successfully uploaded video '%s' as session %s (%d bytes).",
        video.filename, session_id, file_size,
    )
    return session_id, file_size, upload_now
