import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="google.protobuf")

import asyncio
from contextlib import asynccontextmanager
import logging
import threading
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db.database import Database
from app.middleware import RateLimiterMiddleware, SecurityHeadersMiddleware
from app.routers import fusion, pairing, sessions, speech_analysis, upload, visual_analysis
from app.services.retention import start_retention_scheduler, stop_retention_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("smartspeak")

# Pairing tokens must never appear in logs in full — including uvicorn's
# access log, which prints raw request paths (status polls carry the token).
from app.services.pairing import PairingTokenScrubFilter, scrub_tokens_in_text as pairing_scrub  # noqa: E402

for _handler in logging.getLogger("uvicorn").handlers + logging.getLogger("uvicorn.access").handlers:
    _handler.addFilter(PairingTokenScrubFilter())
logging.getLogger("uvicorn.access").addFilter(PairingTokenScrubFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events."""
    logger.info("Initializing SmartSpeak backend services...")
    # Ensure storage paths exist
    settings.staging_dir.mkdir(parents=True, exist_ok=True)
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize persistent local document database
    try:
        await Database.connect()
    except Exception as e:
        logger.error(f"Database startup initialization error: {e}")
        raise e

    # Start retention cleanup scheduler
    try:
        start_retention_scheduler()
    except Exception as e:
        logger.warning(f"Scheduler start warning: {e}")

    # Prewarm heavy ML models in the background so the first upload does not
    # pay the multi-second model-load latency (Whisper + spaCy + classifier).
    if settings.PREWARM_MODELS:
        def _prewarm_models():
            try:
                from app.services.speech_analyzer import _get_faster_model, get_spacy_nlp
                from app.services.visual_analyzer import _get_confidence_model, _get_posture_model
                from app.config import settings as _s
                if _s.WHISPER_ENGINE == "faster":
                    _get_faster_model(_s.WHISPER_MODEL)
                else:
                    from app.services.speech_analyzer import _get_whisper_model
                    _get_whisper_model(_s.WHISPER_MODEL)
                get_spacy_nlp()
                _get_confidence_model()
                _get_posture_model()
                # Rewrite model (~900MB one-time download) is fetched/loaded in
                # this background thread so the first fusion report never pays
                # the load latency. Its own try/except keeps a rewrite-model
                # failure from spoiling the Whisper/spaCy/classifier prewarm.
                from app.services.rewrite_engine import _get_rewrite_model
                if _s.REWRITES_ENABLED and _s.REWRITE_PREWARM:
                    try:
                        _get_rewrite_model()
                    except Exception as rw_exc:
                        logger.warning(f"Rewrite model prewarm failed (lazily retried on first use): {rw_exc}")
                logger.info("Model prewarm complete: Whisper, spaCy, and confidence/posture classifiers are in memory.")
            except Exception as e:
                logger.warning(f"Model prewarm skipped/failed (first request will load lazily): {e}")

        threading.Thread(target=_prewarm_models, name="model-prewarm", daemon=True).start()

    # Capture the main event loop so sync worker threads can report progress.
    from app.services import progress as _progress
    _progress.set_event_loop(asyncio.get_running_loop())

    logger.info("SmartSpeak backend ready.")
    
    yield
    
    logger.info("Shutting down SmartSpeak backend services...")
    stop_retention_scheduler()
    await Database.close()
    logger.info("SmartSpeak backend shutdown complete.")


app = FastAPI(
    title="SmartSpeak API",
    description="Backend services for SmartSpeak - AI-powered public speaking coach (Video Ingestion, Audio/Video Processing, Speech Analysis, and Visual Analysis).",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimiterMiddleware)
# Compress JSON report payloads (history lists, fusion reports) in transit.
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Enable CORS for React frontend (origins configurable via CORS_ALLOW_ORIGINS)
_origins = [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure base storage directory exists before mounting static files
settings.base_storage_path.mkdir(parents=True, exist_ok=True)
app.mount("/data", StaticFiles(directory=str(settings.base_storage_path)), name="data")

# Include API routers
app.include_router(upload.router)
# Phone-camera pairing (Practice mode QR flow) — reuses upload's ingest path.
app.include_router(pairing.router)
app.include_router(sessions.router)
app.include_router(speech_analysis.router)
app.include_router(visual_analysis.router)
app.include_router(fusion.router)

# Media streaming (session video with HTTP range support)
from app.routers import media as media_router  # noqa: E402
app.include_router(media_router.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log the full traceback server-side; return a generic 500 to clients."""
    logger.exception("Unhandled error on %s %s", request.method, pairing_scrub(request.url.path))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )


@app.get("/health", tags=["System"])
async def health():
    """Liveness probe for load balancers and uptime monitors."""
    return {"status": "ok", "app": "SmartSpeak API"}


@app.get("/version", tags=["System"])
async def version():
    """Build/version information for deployment verification."""
    return {
        "app": "SmartSpeak API",
        "version": "1.0.0",
    }


@app.get("/")
async def root():
    return {
        "app": "SmartSpeak API",
        "version": "1.0.0",
        "status": "online",
        "docs_url": "/docs"
    }
