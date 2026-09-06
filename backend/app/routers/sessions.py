import logging
from fastapi import APIRouter, HTTPException, status
from app.db.mongodb import MongoDB
from app.models.session import StatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["Sessions"])


@router.get("/{session_id}/status", response_model=StatusResponse)
async def get_session_status(session_id: str):
    """
    Returns the processing status and metadata for a given session_id.
    """
    sessions_col = MongoDB.get_collection("sessions")
    session = await sessions_col.find_one({"session_id": session_id})

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' was not found."
        )

    has_speech = "speech_analysis" in session and session["speech_analysis"] is not None
    has_visual = "visual_analysis" in session and session["visual_analysis"] is not None

    return StatusResponse(
        session_id=session["session_id"],
        status=session["status"],
        original_filename=session["original_filename"],
        upload_timestamp=session["upload_timestamp"],
        file_size=session["file_size"],
        content_type=session.get("content_type", "video/mp4"),
        error_reason=session.get("error_reason"),
        processed_at=session.get("processed_at"),
        audio_path=session.get("audio_path"),
        frame_count=session.get("frame_count"),
        has_speech_analysis=has_speech,
        has_visual_analysis=has_visual
    )
