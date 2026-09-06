import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from app.db.database import Database
from app.models.session import (
    VisualAnalysisResponse,
    VisualAnalysisResult,
    ConfidenceAnalysisResponse,
    ConfidenceAnalysisResult,
)
from app.services.visual_analyzer import process_visual_analysis_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["Visual Analysis"])


@router.get("/{session_id}/visual-analysis", response_model=VisualAnalysisResponse)
async def get_visual_analysis(session_id: str):
    """
    Returns the complete structured visual analysis result JSON for a session.
    """
    sessions_col = Database.get_collection("sessions")
    session = await sessions_col.find_one({"session_id": session_id})

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' was not found."
        )

    visual_analysis_data = session.get("visual_analysis")
    if not visual_analysis_data:
        current_status = session.get("status", "unknown")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Visual analysis not complete yet for session '{session_id}'. Current status is '{current_status}'."
        )

    return VisualAnalysisResponse(
        session_id=session["session_id"],
        status=session["status"],
        visual_analysis=VisualAnalysisResult(**visual_analysis_data)
    )


@router.post("/{session_id}/analyze-visual", status_code=status.HTTP_202_ACCEPTED)
async def trigger_visual_analysis(session_id: str, background_tasks: BackgroundTasks):
    """
    Internal/retry endpoint to manually re-run visual analysis for a session.
    """
    sessions_col = Database.get_collection("sessions")
    session = await sessions_col.find_one({"session_id": session_id})

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' was not found."
        )

    background_tasks.add_task(process_visual_analysis_session, session_id)
    return {
        "session_id": session_id,
        "message": "Visual analysis task queued successfully.",
        "status": "processing"
    }


@router.get("/{session_id}/confidence-analysis", response_model=ConfidenceAnalysisResponse)
async def get_confidence_analysis(session_id: str):
    """
    Returns the structured confidence analysis result JSON for a session.
    """
    sessions_col = Database.get_collection("sessions")
    session = await sessions_col.find_one({"session_id": session_id})

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' was not found."
        )

    confidence_analysis_data = session.get("confidence_analysis")
    if not confidence_analysis_data:
        current_status = session.get("status", "unknown")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Confidence analysis not complete yet for session '{session_id}'. Current status is '{current_status}'."
        )

    return ConfidenceAnalysisResponse(
        session_id=session["session_id"],
        status=session["status"],
        confidence_analysis=ConfidenceAnalysisResult(**confidence_analysis_data)
    )
