import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from app.db.database import Database
from app.models.session import (
    FusionReportResponse,
    FusionReportResult,
    SessionStatus,
)
from app.services.fusion_engine import (
    generate_fusion_report_sync,
    process_fusion_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["Feature Fusion"])


@router.get("/{session_id}/fusion-report", response_model=FusionReportResponse)
async def get_fusion_report(session_id: str, recompute: bool = False):
    """
    Returns the complete structured Feature Fusion and Mistake Detection report for a session.
    """
    sessions_col = Database.get_collection("sessions")
    session = await sessions_col.find_one({"session_id": session_id})

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' was not found."
        )

    fusion_data = session.get("fusion_report")
    if fusion_data and not recompute:
        return FusionReportResponse(
            session_id=session["session_id"],
            status=session["status"],
            fusion_report=FusionReportResult(**fusion_data)
        )

    # If fusion report is not yet saved, check if session is ready for fusion
    speech_data = session.get("speech_analysis")
    visual_data = session.get("visual_analysis")
    conf_data = session.get("confidence_analysis")

    if speech_data is not None and visual_data is not None:
        # Dynamically compute, store, and return
        fusion_result = generate_fusion_report_sync(speech_data, visual_data, conf_data)
        fusion_dict = fusion_result.model_dump(mode="json")
        await sessions_col.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "fusion_report": fusion_dict,
                    "status": SessionStatus.FUSION_COMPLETE,
                    "error_reason": None
                }
            }
        )
        return FusionReportResponse(
            session_id=session["session_id"],
            status=SessionStatus.FUSION_COMPLETE,
            fusion_report=fusion_result
        )

    current_status = session.get("status", "unknown")
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Fusion report not available for session '{session_id}'. "
            f"Current status is '{current_status}'. Both speech and visual analysis must complete first."
        )
    )


@router.post("/{session_id}/fuse", status_code=status.HTTP_202_ACCEPTED)
async def trigger_fusion_analysis(session_id: str, background_tasks: BackgroundTasks):
    """
    Internal/retry endpoint to manually trigger or re-run Feature Fusion for a session.
    """
    sessions_col = Database.get_collection("sessions")
    session = await sessions_col.find_one({"session_id": session_id})

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' was not found."
        )

    background_tasks.add_task(process_fusion_session, session_id)
    return {
        "session_id": session_id,
        "status": "processing",
        "message": "Feature Fusion analysis triggered."
    }
