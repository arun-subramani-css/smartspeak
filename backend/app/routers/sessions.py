import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from app.db.mongodb import MongoDB
from app.models.session import (
    StatusResponse,
    SessionHistoryResponse,
    SessionSummary,
    SessionCompareResponse,
)
from app.services.compare_service import (
    build_metric_snapshot,
    build_metric_delta,
    build_focus_goal_progress,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["Sessions"])


@router.get("/history", response_model=SessionHistoryResponse)
async def list_session_history(
    limit: int = 25,
    completed_only: bool = False,
    filename: Optional[str] = None,
):
    """
    Lists recent sessions for the history view, newest first.

    - limit: max number of sessions to return (default 25)
    - completed_only: only sessions with a fusion report
    - filename: case-insensitive substring filter on the original filename
    """
    sessions_col = MongoDB.get_collection("sessions")
    cursor = sessions_col.find({}).sort("upload_timestamp", -1).limit(max(1, min(limit, 100)))
    docs = await cursor.to_list(None)

    summaries = []
    needle = (filename or "").lower()
    for doc in docs:
        if needle and needle not in str(doc.get("original_filename", "")).lower():
            continue
        has_fusion = doc.get("fusion_report") is not None
        if completed_only and not has_fusion:
            continue
        fusion = doc.get("fusion_report") or {}
        summaries.append(SessionSummary(
            session_id=doc.get("session_id", ""),
            original_filename=doc.get("original_filename", ""),
            upload_timestamp=doc.get("upload_timestamp"),
            status=doc.get("status", "unknown"),
            file_size=int(doc.get("file_size") or 0),
            content_type=doc.get("content_type", "video/mp4"),
            has_fusion_report=has_fusion,
            smartspeak_index=fusion.get("smartspeak_index"),
            grade=fusion.get("grade"),
            focus_goal=fusion.get("focus_goal"),
        ))

    return SessionHistoryResponse(sessions=summaries, total=len(summaries))


@router.get("/compare", response_model=SessionCompareResponse)
async def compare_sessions(
    older: str,
    newer: str,
):
    """
    Side-by-side comparison of two completed sessions with per-metric deltas.

    - older: session_id of the earlier session
    - newer: session_id of the later session
    Both sessions must exist and have a fusion report.
    """
    if older == newer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pick two different sessions to compare."
        )

    sessions_col = MongoDB.get_collection("sessions")

    doc_older = await sessions_col.find_one({"session_id": older})
    doc_newer = await sessions_col.find_one({"session_id": newer})

    if not doc_older:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Session '{older}' was not found.")
    if not doc_newer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Session '{newer}' was not found.")

    if doc_older.get("fusion_report") is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Session '{older}' has no completed analysis yet.")
    if doc_newer.get("fusion_report") is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Session '{newer}' has no completed analysis yet.")

    snap_older = build_metric_snapshot(doc_older)
    snap_newer = build_metric_snapshot(doc_newer)

    # Order the pair chronologically by upload time when the caller mixed them up.
    ts_old = doc_older.get("upload_timestamp") or ""
    ts_new = doc_newer.get("upload_timestamp")
    if ts_new and str(ts_new) < str(ts_old):
        snap_older, snap_newer = snap_newer, snap_older

    deltas = []
    for metric in ("smartspeak_index", "eye_contact", "posture", "head_movement",
                   "wpm", "filler_ratio", "repetition_count", "long_pause_count", "longest_pause"):
        d = build_metric_delta(
            metric,
            getattr(snap_older, metric, None),
            getattr(snap_newer, metric, None)
        )
        if d:
            deltas.append(d)

    return SessionCompareResponse(
        older=snap_older,
        newer=snap_newer,
        score_delta=round((snap_newer.smartspeak_index or 0) - (snap_older.smartspeak_index or 0), 1),
        score_direction=(
            "same" if abs((snap_newer.smartspeak_index or 0) - (snap_older.smartspeak_index or 0)) < 0.05
            else "improved" if (snap_newer.smartspeak_index or 0) > (snap_older.smartspeak_index or 0)
            else "regressed"
        ),
        deltas=deltas,
        focus_goal_progress=build_focus_goal_progress(snap_older, snap_newer),
    )


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
    has_fusion = "fusion_report" in session and session["fusion_report"] is not None

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
        has_visual_analysis=has_visual,
        has_fusion_report=has_fusion,
        progress_stage=session.get("progress_stage"),
        speech_progress=session.get("speech_progress") or None,
        visual_progress=session.get("visual_progress") or None
    )