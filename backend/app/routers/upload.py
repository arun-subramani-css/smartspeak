from fastapi import APIRouter, BackgroundTasks, File, HTTPException, status, UploadFile

from app.models.session import SessionStatus, UploadResponse
from app.services.ingest import ingest_video_upload

router = APIRouter(prefix="/api/v1", tags=["Video Upload"])


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(..., description="Video file to upload (.mp4, .avi, .mov)")
):
    """
    Accepts video file upload via POST (multipart/form-data), validates size and format,
    stores in staging directory with UUID filename, records metadata in MongoDB, and triggers processing.

    All ingest work lives in app.services.ingest so this endpoint and the
    phone-pairing upload share one validation/processing path.
    """
    if not video or not video.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided or empty filename.",
        )

    session_id, file_size, upload_now = await ingest_video_upload(background_tasks, video)

    return UploadResponse(
        session_id=session_id,
        status=SessionStatus.UPLOADED,
        message="Video uploaded successfully. Processing started.",
        original_filename=video.filename,
        file_size=file_size,
        upload_timestamp=upload_now
    )
