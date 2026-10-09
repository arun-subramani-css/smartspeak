"""Response models for phone-camera pairing (Practice mode)."""
from pydantic import BaseModel


class PairingCreateResponse(BaseModel):
    token: str
    # Frontend origin the phone should open (never localhost), or None when
    # this machine has no LAN-reachable address — the laptop UI then shows
    # a warning instead of a QR code.
    phone_url: str | None
    expires_in: int  # token lifetime in seconds
    status: str      # "waiting"


class PairingStatusResponse(BaseModel):
    status: str                    # waiting | uploading | uploaded
    session_id: str | None = None  # present once status == "uploaded"


class PairingUploadResponse(BaseModel):
    session_id: str
    status: str  # "uploaded"
