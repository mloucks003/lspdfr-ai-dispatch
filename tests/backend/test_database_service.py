"""Unit tests for DatabaseService – connection management, indexes, and write queue."""

import asyncio
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from backend.services.database import DatabaseService, WRITE_RETRY_INTERVAL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db():
    """Return a mock AsyncIOMotorDatabase with collection stubs."""
    db = MagicMock()
    for coll_name in ("calls", "persons", "vehicles", "warrants", "citations", "audit_log"):
        coll = MagicMock()
        coll.create_indexes = AsyncMock()
        coll.create_index = AsyncMock()
        db.__getitem__ = MagicMock(side_effect=lambda name, _db=db: getattr(_db, name))
        setattr(db, coll_name, coll)
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDatabaseServiceStartStop:
    """Verify lifecycle: start creates client, verifies connection, creates indexes."""

    @pytest.mark.asyncio
    async def test_start_sets_connected(self):
        svc = DatabaseService(mongodb_uri="mongodb://localhost:27017", mongodb_database="test_db")

        mock_db = _make_mock_db()
        mock_client = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_client.admin.command = AsyncMock(return_value={"ok": 1})
        mock_client.close = MagicMock()

        with patch("backend.services.database.AsyncIOMotorClient", return_value=mock_client):
            await svc.start()

        assert svc.connected is True
        assert svc.db is mock_db
        assert svc.client is mock_client

        await svc.stop()
        assert svc.connected is False

    @pytest.mark.asyncio
    async def test_start_calls_ping(self):
        svc = DatabaseService(mongodb_uri="mongodb://localhost:27017", mongodb_database="test_db")

        mock_db = _make_mock_db()
        mock_client = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_client.admin.command = AsyncMock(return_value={"ok": 1})
        mock_client.close = MagicMock()

        with patch("backend.services.database.AsyncIOMotorClient", return_value=mock_client):
            await svc.start()

        mock_client.admin.command.assert_awaited_once_with("ping")
        await svc.stop()


class TestIndexCreation:
    """Verify that _ensure_indexes creates the correct indexes."""

    @pytest.mark.asyncio
    async def test_indexes_created_on_start(self):
        svc = DatabaseService(mongodb_uri="mongodb://localhost:27017", mongodb_database="test_db")

        mock_db = _make_mock_db()
        mock_client = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=mock_db)
        mock_client.admin.command = AsyncMock(return_value={"ok": 1})
        mock_client.close = MagicMock()

        with patch("backend.services.database.AsyncIOMotorClient", return_value=mock_client):
            await svc.start()

        # Each collection should have had create_indexes called
        mock_db.calls.create_indexes.assert_awaited_once()
        mock_db.persons.create_indexes.assert_awaited_once()
        mock_db.vehicles.create_indexes.assert_awaited_once()
        mock_db.warrants.create_indexes.assert_awaited_once()
        mock_db.citations.create_indexes.assert_awaited_once()
        mock_db.audit_log.create_indexes.assert_awaited_once()

        # vehicles also gets a separate text index
        mock_db.vehicles.create_index.assert_awaited_once()

        await svc.stop()


class TestWriteQueue:
    """Verify queue-and-retry logic for writes when MongoDB is unavailable."""

    @pytest.mark.asyncio
    async def test_enqueue_write_executes_immediately_when_connected(self):
        svc = DatabaseService()
        svc._connected = True
        svc._db = MagicMock()

        executed = []
        async def write_fn():
            executed.append(True)

        await svc.enqueue_write(write_fn)
        assert len(executed) == 1
        assert len(svc._write_queue) == 0

    @pytest.mark.asyncio
    async def test_enqueue_write_queues_when_disconnected(self):
        svc = DatabaseService()
        svc._connected = False

        async def write_fn():
            pass

        await svc.enqueue_write(write_fn)
        assert len(svc._write_queue) == 1

    @pytest.mark.asyncio
    async def test_enqueue_write_queues_on_connection_failure(self):
        from pymongo.errors import ConnectionFailure

        svc = DatabaseService()
        svc._connected = True

        async def failing_write():
            raise ConnectionFailure("gone")

        await svc.enqueue_write(failing_write)
        assert svc._connected is False
        assert len(svc._write_queue) == 1

    @pytest.mark.asyncio
    async def test_queue_drains_when_connection_restored(self):
        """Simulate the queue processor draining queued writes."""
        svc = DatabaseService()
        svc._connected = False

        results = []
        async def write_fn():
            results.append("done")

        svc._write_queue.append(write_fn)
        svc._write_queue.append(write_fn)

        # Simulate connection restored
        svc._connected = True

        # Manually drain (same logic as _process_write_queue inner loop)
        while svc._write_queue:
            fn = svc._write_queue[0]
            await fn()
            svc._write_queue.popleft()

        assert len(results) == 2
        assert len(svc._write_queue) == 0
