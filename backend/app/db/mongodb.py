import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import settings

logger = logging.getLogger(__name__)


class MongoDB:
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None

    @classmethod
    async def connect(cls):
        """Establish MongoDB connection and create required collection indexes."""
        if cls.client is None:
            logger.info(f"Connecting to MongoDB at {settings.MONGODB_URL}...")
            cls.client = AsyncIOMotorClient(settings.MONGODB_URL)
            cls.db = cls.client[settings.MONGODB_DB_NAME]
            
            # Ensure indexes on 'sessions' collection
            sessions_col = cls.db["sessions"]
            await sessions_col.create_index("session_id", unique=True)
            await sessions_col.create_index("upload_timestamp")
            await sessions_col.create_index("status")
            logger.info("MongoDB connection established and indexes verified.")

    @classmethod
    async def close(cls):
        """Close MongoDB connection."""
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("MongoDB connection closed.")

    @classmethod
    def get_collection(cls, name: str = "sessions"):
        """Return collection instance."""
        if cls.db is None:
            raise RuntimeError("Database connection is not initialized. Call connect() first.")
        return cls.db[name]
