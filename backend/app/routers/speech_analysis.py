import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from app.db.mongodb import MongoDB
from app.models.session import SpeechAnalysisResponse, SpeechAnalysisResult
from app.services.speech_analyzer import process_speech_analysis_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["Speech Analysis"])


@router.get("/{session_id}/speech-analysis", response_model=SpeechAnalysisResponse)
async def get_speech_analysis(session_id: str):
    """
    Returns the complete structured speech analysis result JSON for a session.
    """
    sessions_col = MongoDB.get_collection("sessions")
    session = await sessions_col.find_one({"session_id": session_id})

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' was not found."
        )

    speech_analysis_data = session.get("speech_analysis")
    if not speech_analysis_data:
        current_status = session.get("status", "unknown")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Speech analysis not complete yet for session '{session_id}'. Current status is '{current_status}'."
        )

    return SpeechAnalysisResponse(
        session_id=session["session_id"],
        status=session["status"],
        speech_analysis=SpeechAnalysisResult(**speech_analysis_data)
    )


@router.post("/{session_id}/analyze-speech", status_code=status.HTTP_202_ACCEPTED)
async def trigger_speech_analysis(session_id: str, background_tasks: BackgroundTasks):
    """
    Internal/retry endpoint to manually re-run speech analysis for a session.
    """
    sessions_col = MongoDB.get_collection("sessions")
    session = await sessions_col.find_one({"session_id": session_id})

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' was not found."
        )

    background_tasks.add_task(process_speech_analysis_session, session_id)
    return {
        "session_id": session_id,
        "message": "Speech analysis task queued successfully.",
        "status": "processing"
    }
