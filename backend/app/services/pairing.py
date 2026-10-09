"""Phone-camera pairing tokens for Practice mode ("Use phone camera").

The laptop creates a short-lived, single-use token, encodes the phone URL
into a QR code, and polls status until the phone's upload lands; the
resulting session id is handed back to the normal report flow.

Design:
- In-memory store: single-process, mirroring the stance documented on
  RateLimiterMiddleware (swap for Redis before running multiple workers).
- 32-byte URL-safe random tokens. Full tokens are never logged (only a
  SHA-256 digest prefix) and never persisted to the database.
- Expiry is lazy: entries are swept whenever the store is touched, so no
  background janitor runs. A token looked up *after* expiry still reports
  "expired" (410) instead of silently degrading to "unknown" (404).
"""
from __future__ import annotations

import hashlib
import ipaddress
import logging
import re
import secrets
import socket
import time
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)

STATUS_WAITING = "waiting"
STATUS_UPLOADING = "uploading"
STATUS_UPLOADED = "uploaded"

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass
class PairingRecord:
    token: str
    created_at: float
    status: str = STATUS_WAITING  # waiting | uploading | uploaded
    session_id: str | None = None


_store: dict[str, PairingRecord] = {}


def _now() -> float:
    return time.time()


def is_expired(rec: PairingRecord, now: float | None = None) -> bool:
    ts = now if now is not None else _now()
    return ts >= rec.created_at + settings.PAIRING_TOKEN_TTL_SECONDS


def _sweep(exclude: str | None = None) -> None:
    """Drop expired entries. `exclude` keeps the record the caller is about
    to answer for (so it can return 410, not 404)."""
    now = _now()
    for token in [t for t, r in _store.items() if t != exclude and is_expired(r, now)]:
        del _store[token]


def token_log_prefix(token: str) -> str:
    """Non-reversible digest for log lines — never log the full token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:10]


# Pairing tokens are URL-safe base64 path segments; match them wherever they
# appear in free text (uvicorn access lines, exception logs).
_TOKEN_IN_TEXT_RE = re.compile(r"(/api/v1/pairing/)([A-Za-z0-9_-]{16,})")


def scrub_tokens_in_text(text: str) -> str:
    """Replace any pairing token embedded in a path/URL with its digest
    prefix. Idempotent; non-pairing text is returned unchanged."""
    return _TOKEN_IN_TEXT_RE.sub(
        lambda m: m.group(1) + token_log_prefix(m.group(2)), text
    )


class PairingTokenScrubFilter(logging.Filter):
    """Keep full pairing tokens out of uvicorn's access log.

    uvicorn logs the raw request path ("GET /api/v1/pairing/<token>") — the
    laptop's status poll and the phone's upload both embed the token there.
    The application's own loggers already use digest prefixes; this filter
    extends the same guarantee to server-level request logging.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Scrub in place, preserving structure: uvicorn's AccessFormatter
        # unpacks record.args as a fixed 5-tuple, so replacing msg/clearing
        # args would crash it. Scrub the message template and each string
        # argument instead.
        record.msg = scrub_tokens_in_text(str(record.msg))
        if isinstance(record.args, tuple):
            record.args = tuple(
                scrub_tokens_in_text(a) if isinstance(a, str) else a
                for a in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                k: scrub_tokens_in_text(v) if isinstance(v, str) else v
                for k, v in record.args.items()
            }
        return True


def create_pairing() -> PairingRecord:
    _sweep()
    rec = PairingRecord(token=secrets.token_urlsafe(32), created_at=_now())
    _store[rec.token] = rec
    logger.info("Pairing created (%s).", token_log_prefix(rec.token))
    return rec


def get_pairing(token: str) -> PairingRecord | None:
    """Raw lookup (expired records are still returned so the router can
    answer 410); unrelated expired entries are swept as a side effect."""
    rec = _store.get(token)
    _sweep(exclude=token)
    return rec


def mark_uploading(rec: PairingRecord) -> bool:
    """Claim the token for an upload. False when it is already used or an
    upload is in flight. No await between check and set: safe under
    asyncio's single-threaded concurrency."""
    if rec.status != STATUS_WAITING:
        return False
    rec.status = STATUS_UPLOADING
    return True


def release_upload(rec: PairingRecord) -> None:
    """Upload failed before a session existed (validation/size/IO error) —
    return the token to `waiting` so the phone can retry."""
    if rec.status == STATUS_UPLOADING:
        rec.status = STATUS_WAITING


def mark_uploaded(rec: PairingRecord, session_id: str) -> None:
    rec.status = STATUS_UPLOADED
    rec.session_id = session_id


def delete_pairing(token: str) -> bool:
    return _store.pop(token, None) is not None


# --- Phone URL ---------------------------------------------------------------

def detect_lan_ip() -> str | None:
    """Best-effort LAN IPv4 for this machine; never loopback/link-local.

    1. A UDP "connect" asks the routing table which source address a packet
       to the internet would use — no packets are actually sent.
    2. Hostname resolution as fallback (no default route, resolvable LAN IP).

    Private (RFC1918) addresses win so a VPN/public interface can't hijack
    the QR code; `LAN_BASE_URL` overrides the whole guess.
    """
    candidates: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            candidates.append(sock.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.append(info[4][0])
    except OSError:
        pass

    def usable(ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return addr.version == 4 and not addr.is_loopback and not addr.is_link_local

    unique = list(dict.fromkeys(ip for ip in candidates if usable(ip)))
    for ip in unique:
        if ipaddress.ip_address(ip).is_private:
            return ip
    return unique[0] if unique else None


def _host_of(base: str) -> str:
    return base.split("://", 1)[-1].split("/")[0].split(":")[0]


def phone_base_url() -> str | None:
    """Base URL the phone opens (the frontend origin), or None when this
    machine isn't reachable. Localhost is never encoded."""
    if settings.LAN_BASE_URL:
        base = settings.LAN_BASE_URL.rstrip("/")
        if _host_of(base) in _LOOPBACK_HOSTS:
            return None
        return base
    ip = detect_lan_ip()
    if not ip:
        return None
    return f"http://{ip}:{settings.FRONTEND_PORT}"


def phone_path(token: str) -> str:
    return f"/pair/{token}"


def phone_url(token: str) -> str | None:
    base = phone_base_url()
    if not base:
        return None
    return base + phone_path(token)
