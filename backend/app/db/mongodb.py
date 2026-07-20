import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import settings

logger = logging.getLogger(__name__)


class FallbackAsyncCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        if length is not None:
            return self._docs[:length]
        return self._docs


class FallbackAsyncCollection:
    """In-memory collection fallback used when a live MongoDB server is not running."""

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    async def create_index(self, keys, **kwargs):
        pass

    async def insert_one(self, doc: Dict[str, Any]):
        session_id = doc.get("session_id")
        if session_id:
            self._store[session_id] = doc.copy()
        return type("InsertResult", (), {"inserted_id": session_id})()

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        session_id = query.get("session_id")
        if session_id and session_id in self._store:
            return self._store[session_id].copy()

        for doc in self._store.values():
            match = True
            for k, v in query.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return doc.copy()
        return None

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]):
        session_id = query.get("session_id")
        doc = await self.find_one(query)
        if doc and "$set" in update:
            target_id = doc["session_id"]
            self._store[target_id].update(update["$set"])
            return type("UpdateResult", (), {"modified_count": 1})()
        return type("UpdateResult", (), {"modified_count": 0})()

    async def delete_one(self, query: Dict[str, Any]):
        doc = await self.find_one(query)
        if doc and "session_id" in doc:
            session_id = doc["session_id"]
            if session_id in self._store:
                del self._store[session_id]
                return type("DeleteResult", (), {"deleted_count": 1})()
        return type("DeleteResult", (), {"deleted_count": 0})()

    def find(self, query: Dict[str, Any]) -> FallbackAsyncCursor:
        matched = []
        for doc in self._store.values():
            match = True
            for k, v in query.items():
                if k == "upload_timestamp" and isinstance(v, dict):
                    lt_val = v.get("$lt")
                    doc_ts = doc.get("upload_timestamp")
                    if lt_val and doc_ts and doc_ts >= lt_val:
                        match = False
                elif doc.get(k) != v:
                    match = False
            if match:
                matched.append(doc.copy())
        return FallbackAsyncCursor(matched)


class MongoDB:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None
    fallback_collection: Optional[FallbackAsyncCollection] = None

    @classmethod
    async def connect(cls):
        """Establish MongoDB connection or use local fallback if server is unreachable."""
        if cls.client is None and cls.fallback_collection is None:
            logger.info(f"Connecting to MongoDB at {settings.MONGODB_URL}...")
            try:
                test_client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=2000)
                await test_client.admin.command('ping')
                cls.client = test_client
                cls.db = cls.client[settings.MONGODB_DB_NAME]

                sessions_col = cls.db["sessions"]
                await sessions_col.create_index("session_id", unique=True)
                await sessions_col.create_index("upload_timestamp")
                await sessions_col.create_index("status")
                logger.info("MongoDB connection established and indexes verified.")
            except Exception as e:
                logger.warning(f"MongoDB server unreachable at {settings.MONGODB_URL} ({e}). Using local in-memory storage fallback.")
                cls.fallback_collection = FallbackAsyncCollection()

    @classmethod
    async def close(cls):
        """Close MongoDB connection."""
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("MongoDB connection closed.")
        cls.fallback_collection = None

    @classmethod
    def get_collection(cls, name: str = "sessions"):
        """Return live collection or fallback collection instance."""
        if cls.fallback_collection is not None:
            return cls.fallback_collection
        if cls.db is not None:
            return cls.db[name]
        # Return fallback if not connected yet
        cls.fallback_collection = FallbackAsyncCollection()
        return cls.fallback_collection
