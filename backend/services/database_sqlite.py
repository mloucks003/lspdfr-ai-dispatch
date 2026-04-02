"""SQLite database service — zero-install replacement for MongoDB.

Provides the same public interface as the original DatabaseService so all
existing services (call_manager, plate_check, etc.) work without changes.
Uses aiosqlite for async access and stores data as JSON blobs per collection.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional

import aiosqlite

from backend.config import settings
from backend.models.enums import AuditOperation

logger = logging.getLogger(__name__)


def _new_id() -> str:
    """Generate a unique ID (replaces MongoDB ObjectId)."""
    return uuid.uuid4().hex[:24]


class _Collection:
    """Mimics a MongoDB collection interface backed by a SQLite table.

    Each 'collection' is a table with columns: _id TEXT PK, data JSON.
    Supports find, find_one, insert_one, update_one, delete_one, and
    basic query operators ($ne, $regex, $text, $push, $set, $addToSet, etc.).
    """

    def __init__(self, db: aiosqlite.Connection, name: str):
        self._db = db
        self._name = name

    async def _ensure_table(self):
        await self._db.execute(
            f"CREATE TABLE IF NOT EXISTS [{self._name}] "
            f"(_id TEXT PRIMARY KEY, data TEXT NOT NULL)"
        )
        await self._db.commit()

    # -- insert_one --------------------------------------------------------

    async def insert_one(self, document: Dict[str, Any]):
        doc = dict(document)
        if "_id" not in doc or doc["_id"] is None:
            doc["_id"] = _new_id()
        doc_id = doc["_id"]
        await self._db.execute(
            f"INSERT INTO [{self._name}] (_id, data) VALUES (?, ?)",
            (str(doc_id), json.dumps(doc, default=str)),
        )
        await self._db.commit()

        class _Result:
            inserted_id = doc_id
        return _Result()

    # -- find_one ----------------------------------------------------------

    async def find_one(self, filter_: Optional[Dict] = None, projection=None):
        rows = await self._find_rows(filter_, limit=1)
        return rows[0] if rows else None

    # -- find --------------------------------------------------------------

    def find(self, filter_: Optional[Dict] = None):
        return _Cursor(self, filter_)

    # -- update_one --------------------------------------------------------

    async def update_one(self, filter_: Dict, update: Dict, upsert: bool = False):
        doc = await self.find_one(filter_)
        matched = 0
        modified = 0
        upserted_id = None

        if doc is None and upsert:
            new_doc = {"_id": _new_id()}
            # Apply $setOnInsert
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
            # Apply $set
            if "$set" in update:
                new_doc.update(update["$set"])
            # Apply filter fields as defaults
            for k, v in filter_.items():
                if k not in new_doc and isinstance(v, (str, int, float, bool)):
                    new_doc[k] = v
            await self._db.execute(
                f"INSERT INTO [{self._name}] (_id, data) VALUES (?, ?)",
                (str(new_doc["_id"]), json.dumps(new_doc, default=str)),
            )
            await self._db.commit()
            upserted_id = new_doc["_id"]
            matched = 0
        elif doc is not None:
            matched = 1
            updated_doc = dict(doc)
            if "$set" in update:
                updated_doc.update(update["$set"])
            if "$push" in update:
                for field, value in update["$push"].items():
                    if field not in updated_doc:
                        updated_doc[field] = []
                    if isinstance(updated_doc[field], list):
                        updated_doc[field].append(value)
            if "$addToSet" in update:
                for field, value in update["$addToSet"].items():
                    if field not in updated_doc:
                        updated_doc[field] = []
                    if isinstance(updated_doc[field], list) and value not in updated_doc[field]:
                        updated_doc[field].append(value)
            if "$inc" in update:
                for field, value in update["$inc"].items():
                    updated_doc[field] = updated_doc.get(field, 0) + value
            await self._db.execute(
                f"UPDATE [{self._name}] SET data = ? WHERE _id = ?",
                (json.dumps(updated_doc, default=str), str(doc["_id"])),
            )
            await self._db.commit()
            modified = 1

        class _Result:
            pass
        r = _Result()
        r.matched_count = matched
        r.modified_count = modified
        r.upserted_id = upserted_id
        return r

    # -- find_one_and_update -----------------------------------------------

    async def find_one_and_update(self, filter_, update, upsert=False, return_document=None):
        result = await self.update_one(filter_, update, upsert=upsert)
        if result.upserted_id:
            return await self.find_one({"_id": result.upserted_id})
        return await self.find_one(filter_)

    # -- delete_one --------------------------------------------------------

    async def delete_one(self, filter_: Dict):
        doc = await self.find_one(filter_)
        if doc is None:
            class _R:
                deleted_count = 0
            return _R()
        await self._db.execute(
            f"DELETE FROM [{self._name}] WHERE _id = ?", (str(doc["_id"]),)
        )
        await self._db.commit()
        class _R:
            deleted_count = 1
        return _R()

    # -- create_indexes (no-op for SQLite) ---------------------------------

    async def create_indexes(self, indexes):
        pass  # SQLite doesn't need explicit index creation for our use case

    async def create_index(self, keys, **kwargs):
        pass

    # -- internal query engine ---------------------------------------------

    async def _find_rows(self, filter_: Optional[Dict], limit: int = 10000) -> List[Dict]:
        async with self._db.execute(
            f"SELECT data FROM [{self._name}]"
        ) as cursor:
            rows = await cursor.fetchall()

        results = []
        for (raw,) in rows:
            doc = json.loads(raw)
            if filter_ is None or self._matches(doc, filter_):
                results.append(doc)
                if len(results) >= limit:
                    break
        return results

    @staticmethod
    def _matches(doc: Dict, filter_: Dict) -> bool:
        for key, condition in filter_.items():
            val = doc.get(key)
            if isinstance(condition, dict):
                if "$ne" in condition and val == condition["$ne"]:
                    return False
                if "$regex" in condition:
                    import re
                    flags = re.IGNORECASE if condition.get("$options") == "i" else 0
                    if val is None or not re.search(condition["$regex"], str(val), flags):
                        return False
                if "$text" in condition:
                    # Simple text search: check if search term is in any string field
                    search = condition["$text"].get("$search", "").lower()
                    found = False
                    for v in doc.values():
                        if isinstance(v, str) and search in v.lower():
                            found = True
                            break
                    if not found:
                        return False
            elif "$text" == key:
                search = condition.get("$search", "").lower()
                found = False
                for v in doc.values():
                    if isinstance(v, str) and search in v.lower():
                        found = True
                        break
                if not found:
                    return False
            else:
                if val != condition:
                    return False
        return True


class _Cursor:
    """Async cursor that supports .sort() and .to_list()."""

    def __init__(self, collection: _Collection, filter_: Optional[Dict]):
        self._collection = collection
        self._filter = filter_
        self._sort_key = None
        self._sort_dir = 1

    def sort(self, key, direction=1):
        self._sort_key = key
        self._sort_dir = direction
        return self

    async def to_list(self, length: int = 10000) -> List[Dict]:
        rows = await self._collection._find_rows(self._filter, limit=length)
        if self._sort_key:
            reverse = self._sort_dir == -1
            rows.sort(key=lambda d: d.get(self._sort_key, 0), reverse=reverse)
        return rows[:length]


class _DB:
    """Mimics a MongoDB database — attribute access returns _Collection objects."""

    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn
        self._collections: Dict[str, _Collection] = {}

    def __getattr__(self, name: str) -> _Collection:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    def __getitem__(self, name: str) -> _Collection:
        if name not in self._collections:
            self._collections[name] = _Collection(self._conn, name)
        return self._collections[name]


class DatabaseService:
    """SQLite-backed database service with the same interface as the
    MongoDB version. Zero external dependencies — just a local file."""

    def __init__(self, db_path: Optional[str] = None, **kwargs):
        self._db_path = db_path or getattr(settings, "sqlite_path", "dispatch.db")
        self._conn: Optional[aiosqlite.Connection] = None
        self._db: Optional[_DB] = None
        self._connected = False

    @property
    def db(self):
        assert self._db is not None, "DatabaseService not started"
        return self._db

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        self._conn = await aiosqlite.connect(self._db_path)
        self._db = _DB(self._conn)
        self._connected = True
        # Create tables for all known collections
        for name in ("calls", "persons", "vehicles", "citations",
                      "warrants", "bolos", "audit_log", "counters", "units"):
            await self._db[name]._ensure_table()
        logger.info("SQLite DatabaseService started — %s", self._db_path)

    async def stop(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None
            self._db = None
            self._connected = False
        logger.info("SQLite DatabaseService stopped")

    # -- Audit logging (same interface as MongoDB version) -----------------

    async def _log_audit(self, collection: str, operation: AuditOperation,
                         document_id: Any, details: Optional[Dict] = None):
        try:
            entry = {
                "collection": collection,
                "operation": operation.value,
                "document_id": str(document_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "details": details or {},
            }
            await self.db.audit_log.insert_one(entry)
        except Exception:
            logger.warning("Failed to write audit log", exc_info=True)

    async def audited_insert(self, collection: str, document: Dict,
                             details: Optional[Dict] = None) -> str:
        result = await self.db[collection].insert_one(document)
        doc_id = result.inserted_id
        await self._log_audit(collection, AuditOperation.INSERT, doc_id, details)
        return doc_id

    async def audited_update(self, collection: str, filter_: Dict,
                             update: Dict, details: Optional[Dict] = None) -> Optional[str]:
        result = await self.db[collection].update_one(filter_, update)
        if result.matched_count == 0:
            return None
        doc = await self.db[collection].find_one(filter_)
        doc_id = doc["_id"] if doc else filter_.get("_id", _new_id())
        await self._log_audit(collection, AuditOperation.UPDATE, doc_id, details)
        return doc_id

    async def audited_delete(self, collection: str, filter_: Dict,
                             details: Optional[Dict] = None) -> Optional[str]:
        doc = await self.db[collection].find_one(filter_)
        if doc is None:
            return None
        doc_id = doc["_id"]
        await self.db[collection].delete_one({"_id": doc_id})
        await self._log_audit(collection, AuditOperation.DELETE, doc_id, details)
        return doc_id

    async def enqueue_write(self, write_fn):
        """Execute immediately — SQLite is always available locally."""
        await write_fn()
