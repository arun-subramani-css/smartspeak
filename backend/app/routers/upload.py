from datetime import datetime, timezone
import logging
from pathlib import Path
import uuid
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, status, UploadFile
from app.config import settings
from app.db.mongodb import MongoDB
from app.models.session import SessionDocument, SessionStatus, UploadResponse
from app.services.file_validator import validate_upload_file
from app.services.video_processor import process_video_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Video Upload"])


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(..., description="Video file to upload (.mp4, .avi, .mov)")
):
    """
    Accepts video file upload via POST (multipart/form-data), validates size and format,
    stores in staging directory with UUID filename, records metadata in MongoDB, and triggers processing.
    """
    if not video or not video.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided or empty filename."
        )

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
                        detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB."
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
            detail=f"Failed to write uploaded file to disk: {str(exc)}"
        )

    # 4. Insert metadata record in MongoDB
    upload_now = datetime.now(timezone.utc)
    session_doc = SessionDocument(
        session_id=session_id,
        original_filename=video.filename,
        upload_timestamp=upload_now,
        file_size=file_size,
        content_type=video.content_type or f"video/{ext.lstrip('.')}",
        status=SessionStatus.UPLOADED,
        file_path=str(staging_file_path)
    )

    sessions_col = MongoDB.get_collection("sessions")
    await sessions_col.insert_one(session_doc.model_dump())

    # 5. Dispatch async background processing task (Module 2)
    background_tasks.add_task(process_video_session, session_id)

    logger.info(f"Successfully uploaded video '{video.filename}' as session {session_id} ({file_size} bytes).")

    return UploadResponse(
        session_id=session_id,
        status=SessionStatus.UPLOADED,
        message="Video uploaded successfully. Processing started.",
        original_filename=video.filename,
        file_size=file_size,
        upload_timestamp=upload_now
    )
