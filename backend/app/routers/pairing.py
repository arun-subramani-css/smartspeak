"""Phone-camera pairing endpoints: create a token, poll status, upload.

Flow: the laptop POSTs /pairing, shows the returned phone URL as a QR
code, and polls GET /pairing/{token}. The phone opens /pair/{token} on the
frontend, records, and POSTs the video here. The resulting session id is
handed back to the laptop, which enters the normal report flow.

Tokens are single-use for uploads, expire after
settings.PAIRING_TOKEN_TTL_SECONDS, and are never logged in full.
"""
import logging

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Response, UploadFile, status

from app.config import settings
from app.models.pairing import (
    PairingCreateResponse,
    PairingStatusResponse,
    PairingUploadResponse,
)
from app.services import pairing
from app.services.ingest import ingest_video_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Pairing"])


def _require_valid(token: str) -> pairing.PairingRecord:
    """Resolve a token to a live record or raise the documented error:
    404 for unknown/cancelled tokens, 410 for expired ones."""
    rec = pairing.get_pairing(token)
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown or cancelled pairing code.",
        )
    if pairing.is_expired(rec):
        pairing.delete_pairing(token)
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This pairing code has expired. Generate a new QR code on the laptop.",
        )
    return rec


@router.post("/pairing", response_model=PairingCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_pairing():
    """Create a single-use pairing token (10-minute expiry) and the phone URL.

    phone_url is null when this machine isn't reachable on the LAN — the
    laptop UI must then show a warning instead of a QR code (localhost is
    never encoded).
    """
    rec = pairing.create_pairing()
    url = pairing.phone_url(rec.token)
    if url is None:
        logger.warning(
            "Pairing %s has no LAN-reachable base URL (localhost-only machine?).",
            pairing.token_log_prefix(rec.token),
        )
    return PairingCreateResponse(
        token=rec.token,
        phone_url=url,
        expires_in=settings.PAIRING_TOKEN_TTL_SECONDS,
        status=rec.status,
    )


@router.get("/pairing/{token}", response_model=PairingStatusResponse)
async def pairing_status(token: str):
    """Laptop-side poll: waiting | uploading | uploaded (+ session_id)."""
    rec = _require_valid(token)
    return PairingStatusResponse(status=rec.status, session_id=rec.session_id)


@router.delete("/pairing/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_pairing(token: str):
    """Laptop-side Cancel. Idempotent: already-gone codes still return 204
    so a double-clicked Cancel never surfaces a scary error."""
    if pairing.delete_pairing(token):
        logger.info("Pairing %s cancelled.", pairing.token_log_prefix(token))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/pairing/{token}/upload", response_model=PairingUploadResponse, status_code=status.HTTP_201_CREATED)
async def pairing_upload(
    background_tasks: BackgroundTasks,
    token: str,
    video: UploadFile = File(..., description="Video file recorded on the phone (.mp4, .mov, .webm)"),
):
    """Phone-side upload. Reuses the exact validation, size cap, staging,
    MongoDB record, rate limiting and processing pipeline as
    POST /api/v1/upload — the only difference is the token link."""
    rec = _require_valid(token)
    if rec.status == pairing.STATUS_UPLOADED:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This pairing code was already used. Generate a new QR code on the laptop.",
        )
    if not pairing.mark_uploading(rec):
        # Another upload for this code is already streaming.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An upload for this pairing code is already in progress.",
        )
    try:
        session_id, file_size, _ts = await ingest_video_upload(background_tasks, video)
    except BaseException:
        # Validation/size/IO failure — nothing was linked, so the phone may
        # retry with the same token. BaseException also covers cancellation
        # so the record can never be stranded in 'uploading'.
        pairing.release_upload(rec)
        raise
    pairing.mark_uploaded(rec, session_id)
    logger.info(
        "Pairing %s linked session %s (%d bytes).",
        pairing.token_log_prefix(token), session_id, file_size,
    )
    return PairingUploadResponse(session_id=session_id, status=pairing.STATUS_UPLOADED)
