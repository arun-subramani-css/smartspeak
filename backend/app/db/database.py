import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import settings

# Load .env variables from current directory or parent directory
load_dotenv()

logger = logging.getLogger(__name__)


def get_mongodb_uri() -> str:
    """
    Retrieve MONGODB_URI from environment variables or settings.
    Raises ValueError if MONGODB_URI is not set.
    """
    uri = os.getenv("MONGODB_URI") or settings.MONGODB_URI
    if not uri or not uri.strip():
        raise ValueError(
            "MONGODB_URI environment variable is missing. "
            "Please set MONGODB_URI in your environment or .env file."
        )
    return uri.strip()


class FallbackAsyncCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        if length is not None:
            return self._docs[:length]
        return self._docs


class FallbackAsyncCollection:
    """Persistent local JSON storage fallback used when a live MongoDB server is unreachable."""

    def __init__(self, storage_path: Optional[Path] = None):
        if storage_path is None:
            storage_path = settings.base_storage_path / "db_fallback.json"
        self._storage_file = storage_path.resolve()
        self._storage_file.parent.mkdir(parents=True, exist_ok=True)
        self._store: Dict[str, Dict[str, Any]] = {}
        self._load_from_disk()

    def _load_from_disk(self):
        if self._storage_file.exists():
            try:
                with open(self._storage_file, "r", encoding="utf-8") as f:
                    self._store = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load local DB fallback from {self._storage_file}: {e}")
                self._store = {}

    def _save_to_disk(self):
        try:
            with open(self._storage_file, "w", encoding="utf-8") as f:
                json.dump(self._store, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to persist local DB fallback to {self._storage_file}: {e}")

    async def create_index(self, keys, **kwargs):
        pass

    async def insert_one(self, doc: Dict[str, Any]):
        session_id = doc.get("session_id")
        if session_id:
            self._store[session_id] = doc.copy()
            self._save_to_disk()
        return type("InsertResult", (), {"inserted_id": session_id})()

    def _matches_query(self, doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
        for k, v in query.items():
            if isinstance(v, dict) and "$ne" in v:
                target_ne = v["$ne"]
                if doc.get(k) == target_ne:
                    return False
            elif isinstance(v, dict) and "$lt" in v:
                doc_val = doc.get(k)
                if doc_val is None or doc_val >= v["$lt"]:
                    return False
            elif doc.get(k) != v:
                return False
        return True

    async def find_one(self, query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self._load_from_disk()
        session_id = query.get("session_id")
        if session_id and len(query) == 1 and session_id in self._store:
            return self._store[session_id].copy()

        for doc in self._store.values():
            if self._matches_query(doc, query):
                return doc.copy()
        return None

    async def update_one(self, query: Dict[str, Any], update: Dict[str, Any]):
        matched_doc = await self.find_one(query)
        if matched_doc and "$set" in update:
            target_id = matched_doc["session_id"]
            if target_id in self._store:
                self._store[target_id].update(update["$set"])
                self._save_to_disk()
                return type("UpdateResult", (), {"modified_count": 1})()
        return type("UpdateResult", (), {"modified_count": 0})()

    async def delete_one(self, query: Dict[str, Any]):
        matched_doc = await self.find_one(query)
        if matched_doc and "session_id" in matched_doc:
            session_id = matched_doc["session_id"]
            if session_id in self._store:
                del self._store[session_id]
                self._save_to_disk()
                return type("DeleteResult", (), {"deleted_count": 1})()
        return type("DeleteResult", (), {"deleted_count": 0})()

    def find(self, query: Dict[str, Any]) -> FallbackAsyncCursor:
        self._load_from_disk()
        matched = [doc.copy() for doc in self._store.values() if self._matches_query(doc, query)]
        return FallbackAsyncCursor(matched)


class Database:
    """Single shared MongoDB client and database connection instance with persistent fallback."""
    
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None
    fallback_collection: Optional[FallbackAsyncCollection] = None

    @classmethod
    async def connect(cls):
        """Establish MongoDB connection using MONGODB_URI."""
        if cls.client is None and cls.fallback_collection is None:
            uri = get_mongodb_uri()
            logger.info("Connecting to MongoDB Atlas / cluster...")
            try:
                test_client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2000)
                await test_client.admin.command("ping")
                cls.client = test_client
                cls.db = cls.client[settings.MONGODB_DB_NAME]

                sessions_col = cls.db["sessions"]
                await sessions_col.create_index("session_id", unique=True)
                await sessions_col.create_index("upload_timestamp")
                await sessions_col.create_index("status")
                logger.info("MongoDB connection established and indexes verified.")
            except Exception as e:
                logger.warning(
                    f"MongoDB connection to Atlas failed ({e}). "
                    "Using local persistent storage fallback (data/db_fallback.json)."
                )
                cls.fallback_collection = FallbackAsyncCollection()

    @classmethod
    async def close(cls):
        """Close shared MongoDB connection."""
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("MongoDB connection closed.")
        cls.fallback_collection = None

    @classmethod
    def get_collection(cls, name: str = "sessions"):
        """
        Return collection instance from shared database connection or persistent fallback storage.
        """
        if cls.db is not None:
            return cls.db[name]
        if cls.fallback_collection is not None:
            return cls.fallback_collection
        # Initialize fallback if not connected yet
        cls.fallback_collection = FallbackAsyncCollection()
        return cls.fallback_collection
