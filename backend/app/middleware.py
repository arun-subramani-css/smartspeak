"""HTTP middleware for SmartSpeak: security headers and upload rate limiting.

SecurityHeadersMiddleware adds the standard hardening headers to every
response (CSP, frame protection, MIME sniffing protection, referrer policy).
On localhost, CSP connect-src also permits ws://localhost:* so the Vite dev
server's HMR websocket keeps working behind the dev proxy.

RateLimiterMiddleware is a lightweight in-memory sliding-window limiter for
expensive endpoints (video upload/analysis). Single-process only: sufficient
for the single-node deployment this service runs in; swap for a Redis-backed
limiter before scaling beyond one worker.
"""
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

# ----------------------------- Security headers -----------------------------

_CSP_DEV = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "connect-src 'self' https: ws://localhost:* http://localhost:*; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self)")
        response.headers.setdefault(
            "Content-Security-Policy",
            _CSP_DEV,
        )
        if request.url.hostname in ("localhost", "127.0.0.1"):
            # Plain HTTP locally; HSTS on plain HTTP makes browsers refuse the
            # site, so only send it when we are not localhost.
            pass
        else:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


# ----------------------------- Rate limiting --------------------------------


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Sliding-window per-IP limiter for expensive endpoints.

    Applies to POST /api/v1/upload (each request consumes minutes of CPU).
    GETs are cheap and stay unlimited; global limits belong at the reverse
    proxy once one exists.

    Memory: stale per-IP windows are pruned opportunistically and the map is
    hard-capped (oldest activity evicted) so a flood of spoofed/unique IPs
    cannot grow it without bound.

    Identity: X-Forwarded-For is only honored when TRUST_X_FORWARDED_FOR is
    enabled (i.e. a trusted reverse proxy actually sits in front). Otherwise
    the raw socket peer is used, so clients cannot rotate a spoofed header to
    obtain a fresh rate-limit bucket.
    """

    _MAX_TRACKED_IPS = 10_000
    _PRUNE_INTERVAL_SECONDS = 600.0

    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque] = defaultdict(deque)
        self._limit = settings.RATE_LIMIT_UPLOAD_PER_HOUR
        self._window = 3600.0
        self._last_prune = 0.0

    def _client_ip(self, request) -> str:
        if settings.TRUST_X_FORWARDED_FOR:
            fwd = request.headers.get("x-forwarded-for")
            if fwd:
                return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _prune(self, now: float) -> None:
        """Drop fully-expired and empty entries; hard-cap the map by evicting
        the least recently active IPs. Called at most every
        _PRUNE_INTERVAL_SECONDS."""
        if now - self._last_prune < self._PRUNE_INTERVAL_SECONDS:
            return
        self._last_prune = now
        # An entry whose NEWEST hit is older than the window can never block
        # anyone again — drop it wholesale (its deque would be emptied by the
        # window loop only if that IP sent another request).
        expired = [
            ip for ip, hits in self._hits.items()
            if not hits or now - hits[-1] > self._window
        ]
        for ip in expired:
            del self._hits[ip]
        if len(self._hits) > self._MAX_TRACKED_IPS:
            # deque is chronological per IP; ordering by last hit approximates
            # least-recently-active without a second index.
            by_latest = sorted(
                self._hits.items(), key=lambda kv: kv[1][-1] if kv[1] else 0.0
            )
            for ip, _ in by_latest[: len(self._hits) - self._MAX_TRACKED_IPS]:
                del self._hits[ip]

    async def dispatch(self, request, call_next):
        if request.method == "POST" and request.url.path == "/api/v1/upload":
            ip = self._client_ip(request)
            now = time.monotonic()
            hits = self._hits[ip]
            while hits and now - hits[0] > self._window:
                hits.popleft()
            if len(hits) >= self._limit:
                retry_after = int(self._window - (now - hits[0])) + 1
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Upload limit reached ({self._limit}/hour). Try again later."},
                    headers={"Retry-After": str(retry_after)},
                )
            hits.append(now)
            self._prune(now)
        return await call_next(request)
