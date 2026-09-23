import os
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from app.config import settings

# Load .env variables from current directory or parent directory
load_dotenv()

logger = logging.getLogger(__name__)


def get_mongodb_uri() -> str:
    """
    Retrieve MONGODB_URI from environment variables or settings if present.
    Retained for backward compatibility with existing tests.
    """
    uri = os.getenv("MONGODB_URI") or settings.MONGODB_URI
    if not uri or not uri.strip():
        raise ValueError(
            "MONGODB_URI environment variable is missing. "
            "Please set MONGODB_URI in your environment or .env file."
        )
    return uri.strip()


class LocalAsyncCursor:
    """Async cursor representing a filtered set of documents."""

    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs
        self._iter = None

    def sort(self, key_or_list: Any, direction: int = 1):
        """Sort documents by key and direction (1 for ASC, -1 for DESC)."""
        if isinstance(key_or_list, str):
            key = key_or_list
            reverse = direction == -1
            self._docs.sort(key=lambda d: str(d.get(key, "")), reverse=reverse)
        elif isinstance(key_or_list, list) and key_or_list:
            key, direction = key_or_list[0]
            reverse = direction == -1
            self._docs.sort(key=lambda d: str(d.get(key, "")), reverse=reverse)
        return self

    def skip(self, count: int):
        self._docs = self._docs[count:]
        return self

    def limit(self, count: int):
        self._docs = self._docs[:count]
        return self

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        if length is not None:
            return self._docs[:length]
        return self._docs

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except (StopIteration, TypeError):
            raise StopAsyncIteration


class LocalAsyncCollection:
    """
    100% self-contained local persistent document store matching the PyMongo/Motor
    async collection interface. Stores sessions in JSON format locally.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        if storage_path is None:
            storage_path = settings.base_storage_path / "sessions.json"
            fallback_path = settings.base_storage_path / "db_fallback.json"
            # Seamless migration: if sessions.json doesn't exist but db_fallback.json does, copy it
            if not storage_path.exists() and fallback_path.exists():
                try:
                    storage_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(fallback_path, storage_path)
                    logger.info(f"Migrated legacy database fallback data to {storage_path}")
                except Exception as e:
                    logger.warning(f"Failed to copy legacy fallback file: {e}")

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
                logger.warning(f"Failed to load local DB from {self._storage_file}: {e}")
                self._store = {}
        else:
            self._store = {}

    def _save_to_disk(self):
        """Atomic write to prevent file corruption during parallel writes."""
        tmp_file = self._storage_file.with_suffix(".tmp")
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self._store, f, indent=2, default=str)
            tmp_file.replace(self._storage_file)
        except Exception as e:
            logger.warning(f"Failed to persist local DB to {self._storage_file}: {e}")
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except Exception:
                    pass

    async def create_index(self, keys, **kwargs):
        """No-op for local storage compatibility."""
        pass

    async def insert_one(self, doc: Dict[str, Any]):
        session_id = doc.get("session_id")
        if session_id:
            self._store[session_id] = doc.copy()
            self._save_to_disk()
        return type("InsertResult", (), {"inserted_id": session_id})()

    def _matches_query(self, doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
        for k, v in query.items():
            doc_val = doc.get(k)
            if isinstance(v, dict):
                if "$ne" in v and doc_val == v["$ne"]:
                    return False
                if "$in" in v and doc_val not in v["$in"]:
                    return False
                if "$lt" in v:
                    target = v["$lt"]
                    if doc_val is None:
                        return False
                    if isinstance(target, datetime) and isinstance(doc_val, str):
                        try:
                            parsed = datetime.fromisoformat(doc_val)
                            if target.tzinfo and parsed.tzinfo is None:
                                parsed = parsed.replace(tzinfo=timezone.utc)
                            doc_val = parsed
                        except Exception:
                            pass
                    try:
                        if doc_val >= target:
                            return False
                    except Exception:
                        return False
                if "$gt" in v:
                    target = v["$gt"]
                    if doc_val is None:
                        return False
                    if isinstance(target, datetime) and isinstance(doc_val, str):
                        try:
                            parsed = datetime.fromisoformat(doc_val)
                            if target.tzinfo and parsed.tzinfo is None:
                                parsed = parsed.replace(tzinfo=timezone.utc)
                            doc_val = parsed
                        except Exception:
                            pass
                    try:
                        if doc_val <= target:
                            return False
                    except Exception:
                        return False
            elif doc_val != v:
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
            target_id = matched_doc.get("session_id")
            if target_id and target_id in self._store:
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

    def find(self, query: Optional[Dict[str, Any]] = None) -> LocalAsyncCursor:
        self._load_from_disk()
        if not query:
            matched = [doc.copy() for doc in self._store.values()]
        else:
            matched = [doc.copy() for doc in self._store.values() if self._matches_query(doc, query)]
        return LocalAsyncCursor(matched)

    async def count_documents(self, query: Optional[Dict[str, Any]] = None) -> int:
        self._load_from_disk()
        if not query:
            return len(self._store)
        return len([doc for doc in self._store.values() if self._matches_query(doc, query)])


# Aliases for backward compatibility
FallbackAsyncCursor = LocalAsyncCursor
FallbackAsyncCollection = LocalAsyncCollection


class Database:
    """
    Central database interface providing local persistent document storage.
    Eliminates external database dependencies, connection lag, and network timeouts.
    """

    client: Optional[Any] = None
    db: Optional[Any] = None
    collection: Optional[LocalAsyncCollection] = None
    fallback_collection: Optional[LocalAsyncCollection] = None

    @classmethod
    async def connect(cls):
        """Initialize local persistent document store."""
        if cls.collection is None:
            cls.collection = LocalAsyncCollection()
            cls.fallback_collection = cls.collection
            logger.info("Local document database initialized successfully (offline & self-contained).")

    @classmethod
    async def close(cls):
        """Cleanly close database connections."""
        if cls.collection:
            cls.collection._save_to_disk()
        cls.collection = None
        cls.fallback_collection = None
        cls.client = None
        cls.db = None
        logger.info("Local database closed.")

    @classmethod
    def get_collection(cls, name: str = "sessions") -> LocalAsyncCollection:
        """
        Return the local async collection instance.
        """
        if cls.collection is None:
            cls.collection = LocalAsyncCollection()
            cls.fallback_collection = cls.collection
        return cls.collection

