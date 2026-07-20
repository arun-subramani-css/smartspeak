from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db.mongodb import MongoDB
from app.routers import sessions, upload
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
    
    # Initialize MongoDB connection
    try:
        await MongoDB.connect()
    except Exception as e:
        logger.warning(f"MongoDB connection failed on startup: {e}. (Will retry when needed)")

    # Start retention cleanup scheduler
    try:
        start_retention_scheduler()
    except Exception as e:
        logger.warning(f"Scheduler start warning: {e}")

    logger.info("SmartSpeak backend ready.")
    
    yield
    
    logger.info("Shutting down SmartSpeak backend services...")
    stop_retention_scheduler()
    await MongoDB.close()
    logger.info("SmartSpeak backend shutdown complete.")


app = FastAPI(
    title="SmartSpeak API",
    description="Backend services for SmartSpeak - AI-powered public speaking coach (Video Upload & Audio/Video Processing modules).",
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


@app.get("/")
async def root():
    return {
        "app": "SmartSpeak API",
        "version": "1.0.0",
        "status": "online",
        "docs_url": "/docs"
    }
