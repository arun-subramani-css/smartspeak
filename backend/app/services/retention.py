from datetime import datetime, timedelta, timezone
import logging
import os
import shutil
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import settings
from app.db.mongodb import MongoDB

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def cleanup_expired_sessions() -> int:
    """
    Finds sessions older than RETENTION_DAYS (default 30 days),
    deletes associated staging/processed files, and removes DB records.
    """
    logger.info("Running scheduled data retention cleanup...")
    try:
        sessions_col = MongoDB.get_collection("sessions")
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=settings.RETENTION_DAYS)

        # Query expired session records
        expired_cursor = sessions_col.find({"upload_timestamp": {"$lt": cutoff_date}})
        expired_sessions = await expired_cursor.to_list(length=1000)

        cleaned_count = 0
        for session in expired_sessions:
            session_id = session.get("session_id")
            if not session_id:
                continue

            logger.info(f"Purging expired session {session_id} uploaded at {session.get('upload_timestamp')}")

            # Delete staging video files
            for staging_file in settings.staging_dir.glob(f"{session_id}.*"):
                try:
                    if staging_file.is_file():
                        staging_file.unlink()
                except Exception as e:
                    logger.error(f"Failed to delete staging file {staging_file}: {e}")

            # Delete processed folder (/processed/{session_id})
            processed_session_dir = settings.processed_dir / session_id
            if processed_session_dir.exists() and processed_session_dir.is_dir():
                try:
                    shutil.rmtree(processed_session_dir)
                except Exception as e:
                    logger.error(f"Failed to delete processed folder {processed_session_dir}: {e}")

            # Delete record from MongoDB
            await sessions_col.delete_one({"session_id": session_id})
            cleaned_count += 1

        logger.info(f"Retention cleanup finished. Purged {cleaned_count} expired session(s).")
        return cleaned_count

    except Exception as exc:
        logger.error(f"Error during retention cleanup: {exc}")
        return 0


def start_retention_scheduler():
    """Start APScheduler background job for automatic periodic retention cleanup."""
    if not scheduler.running:
        scheduler.add_job(
            cleanup_expired_sessions,
            "interval",
            hours=settings.CLEANUP_INTERVAL_HOURS,
            id="retention_cleanup_job",
            replace_existing=True
        )
        scheduler.start()
        logger.info(f"Retention scheduler started (runs every {settings.CLEANUP_INTERVAL_HOURS} hours).")


def stop_retention_scheduler():
    """Stop APScheduler background job."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Retention scheduler stopped.")
