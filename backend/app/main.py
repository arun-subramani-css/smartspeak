from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db.database import Database
from app.routers import fusion, sessions, speech_analysis, upload, visual_analysis
from app.services.retention import start_retention_scheduler, stop_retention_scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("smartspeak")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events."""
    logger.info("Initializing SmartSpeak backend services...")
    # Ensure storage paths exist
    settings.staging_dir.mkdir(parents=True, exist_ok=True)
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize MongoDB connection (raises startup error if MONGODB_URI missing)
    try:
        await Database.connect()
    except Exception as e:
        logger.error(f"MongoDB startup connection error: {e}")
        raise e

    # Start retention cleanup scheduler
    try:
        start_retention_scheduler()
    except Exception as e:
        logger.warning(f"Scheduler start warning: {e}")

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

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure base storage directory exists before mounting static files
settings.base_storage_path.mkdir(parents=True, exist_ok=True)
app.mount("/data", StaticFiles(directory=str(settings.base_storage_path)), name="data")

# Include API routers
app.include_router(upload.router)
app.include_router(sessions.router)
app.include_router(speech_analysis.router)
app.include_router(visual_analysis.router)
app.include_router(fusion.router)


@app.get("/")
async def root():
    return {
        "app": "SmartSpeak API",
        "version": "1.0.0",
        "status": "online",
        "docs_url": "/docs"
    }
