"""MongoDB database service with connection management, index creation, and write queue."""

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel, TEXT
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from backend.config import settings
from backend.models.enums import AuditOperation

logger = logging.getLogger(__name__)

# Retry interval for queued writes when MongoDB is unavailable (seconds).
WRITE_RETRY_INTERVAL = 5


class DatabaseService:
    """Manages the Motor async MongoDB client, index bootstrapping, and a
    write-retry queue for resilience when the database is temporarily down."""

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        mongodb_database: Optional[str] = None,
    ) -> None:
        self._uri = mongodb_uri or settings.mongodb_uri
        self._db_name = mongodb_database or settings.mongodb_database
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None

        # Write queue: each item is an async callable that performs a write op.
        self._write_queue: deque[Callable[[], Coroutine[Any, Any, Any]]] = deque()
        self._queue_processor_task: Optional[asyncio.Task] = None
        self._connected: bool = False

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def client(self) -> AsyncIOMotorClient:
        assert self._client is not None, "DatabaseService not started"
        return self._client

    @property
    def db(self) -> AsyncIOMotorDatabase:
        assert self._db is not None, "DatabaseService not started"
        return self._db

    @property
    def connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Create the Motor client, verify the connection, bootstrap indexes,
        and start the background write-queue processor."""
        self._client = AsyncIOMotorClient(self._uri)
        self._db = self._client[self._db_name]

        # Verify connectivity (Req 14.3)
        await self._verify_connection()

        # Create collections and indexes (Req 14.3)
        await self._ensure_indexes()

        # Start background queue processor (Req 14.4)
        self._queue_processor_task = asyncio.create_task(self._process_write_queue())

        logger.info("DatabaseService started – connected to %s/%s", self._uri, self._db_name)

    async def stop(self) -> None:
        """Drain the write queue (best-effort) and close the client."""
        if self._queue_processor_task is not None:
            self._queue_processor_task.cancel()
            try:
                await self._queue_processor_task
            except asyncio.CancelledError:
                pass

        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None
            self._connected = False

        logger.info("DatabaseService stopped")

    # ------------------------------------------------------------------
    # Write queue helpers (Req 14.4)
    # ------------------------------------------------------------------

    async def enqueue_write(self, write_fn: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        """Execute *write_fn* immediately if connected, otherwise queue it."""
        if self._connected:
            try:
                await write_fn()
                return
            except (ConnectionFailure, ServerSelectionTimeoutError):
                self._connected = False
                logger.warning("MongoDB write failed – queuing operation for retry")

        self._write_queue.append(write_fn)

    async def _process_write_queue(self) -> None:
        """Background loop: retry queued writes every WRITE_RETRY_INTERVAL seconds."""
        while True:
            await asyncio.sleep(WRITE_RETRY_INTERVAL)

            if not self._write_queue:
                continue

            # Check if MongoDB is reachable again
            if not self._connected:
                try:
                    await self._verify_connection()
                except Exception:
                    logger.debug("MongoDB still unavailable – will retry queued writes later")
                    continue

            # Drain the queue
            while self._write_queue:
                write_fn = self._write_queue[0]
                try:
                    await write_fn()
                    self._write_queue.popleft()
                except (ConnectionFailure, ServerSelectionTimeoutError):
                    self._connected = False
                    logger.warning("MongoDB went away while draining queue – will retry later")
                    break

    # ------------------------------------------------------------------
    # Connection verification
    # ------------------------------------------------------------------

    async def _verify_connection(self) -> None:
        """Ping MongoDB to confirm the connection is alive."""
        assert self._client is not None
        await self._client.admin.command("ping")
        self._connected = True
        logger.info("MongoDB connection verified")

    # ------------------------------------------------------------------
    # Index bootstrapping (Req 14.3)
    # ------------------------------------------------------------------

    async def _ensure_indexes(self) -> None:
        """Create required collections and indexes if they don't already exist."""
        db = self.db

        # calls: compound index on (status, priority)
        await db.calls.create_indexes([
            IndexModel([("status", ASCENDING), ("priority", ASCENDING)]),
        ])

        # persons: text index on name, regular index on date_of_birth
        await db.persons.create_indexes([
            IndexModel([("name", TEXT)]),
            IndexModel([("date_of_birth", ASCENDING)]),
        ])

        # vehicles: unique index on plate, text index on (make, model)
        await db.vehicles.create_indexes([
            IndexModel([("plate", ASCENDING)], unique=True),
        ])
        # Text index must be created separately (only one text index per collection)
        # We use create_index for the compound text index.
        try:
            await db.vehicles.create_index([("make", TEXT), ("model", TEXT)])
        except Exception:
            # Text index may already exist; ignore duplicate key errors.
            pass

        # warrants: compound index on (status, person_name)
        await db.warrants.create_indexes([
            IndexModel([("status", ASCENDING), ("person_name", ASCENDING)]),
        ])

        # citations: index on person_id
        await db.citations.create_indexes([
            IndexModel([("person_id", ASCENDING)]),
        ])

        # audit_log: index on timestamp
        await db.audit_log.create_indexes([
            IndexModel([("timestamp", ASCENDING)]),
        ])

        logger.info("Database indexes ensured")

    # ------------------------------------------------------------------
    # Audit logging (Req 14.5)
    # ------------------------------------------------------------------

    async def _log_audit(
        self,
        collection: str,
        operation: AuditOperation,
        document_id: ObjectId,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Write an audit log entry. Failures are logged as warnings and
        never block the caller."""
        try:
            entry = {
                "collection": collection,
                "operation": operation.value,
                "document_id": document_id,
                "timestamp": datetime.now(timezone.utc),
                "details": details or {},
            }
            await self.db.audit_log.insert_one(entry)
        except Exception:
            logger.warning(
                "Failed to write audit log entry for %s on %s/%s",
                operation.value,
                collection,
                document_id,
                exc_info=True,
            )

    async def audited_insert(
        self,
        collection: str,
        document: Dict[str, Any],
        details: Optional[Dict[str, Any]] = None,
    ) -> ObjectId:
        """Insert *document* into *collection* and create an audit log entry."""
        result = await self.db[collection].insert_one(document)
        doc_id = result.inserted_id
        await self._log_audit(collection, AuditOperation.INSERT, doc_id, details)
        return doc_id

    async def audited_update(
        self,
        collection: str,
        filter_: Dict[str, Any],
        update: Dict[str, Any],
        details: Optional[Dict[str, Any]] = None,
    ) -> Optional[ObjectId]:
        """Update a document in *collection* and create an audit log entry.

        Returns the ``_id`` of the matched document, or ``None`` if no
        document matched the filter.
        """
        result = await self.db[collection].update_one(filter_, update)
        if result.matched_count == 0:
            return None
        # Retrieve the _id of the matched document
        doc = await self.db[collection].find_one(filter_, {"_id": 1})
        doc_id = doc["_id"] if doc else filter_.get("_id", ObjectId())
        await self._log_audit(collection, AuditOperation.UPDATE, doc_id, details)
        return doc_id

    async def audited_delete(
        self,
        collection: str,
        filter_: Dict[str, Any],
        details: Optional[Dict[str, Any]] = None,
    ) -> Optional[ObjectId]:
        """Delete a document from *collection* and create an audit log entry.

        Returns the ``_id`` of the deleted document, or ``None`` if no
        document matched the filter.
        """
        # Grab the _id before deleting
        doc = await self.db[collection].find_one(filter_, {"_id": 1})
        if doc is None:
            return None
        doc_id = doc["_id"]
        await self.db[collection].delete_one({"_id": doc_id})
        await self._log_audit(collection, AuditOperation.DELETE, doc_id, details)
        return doc_id
