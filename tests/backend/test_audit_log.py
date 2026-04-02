"""Unit tests for audit logging in DatabaseService (Req 14.5)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from backend.models.enums import AuditOperation
from backend.services.database import DatabaseService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service_with_mock_db():
    """Return a started-enough DatabaseService with a mocked Motor database."""
    svc = DatabaseService(mongodb_uri="mongodb://localhost:27017", mongodb_database="test_db")
    svc._connected = True

    mock_db = MagicMock()

    # audit_log collection
    audit_coll = MagicMock()
    audit_coll.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    mock_db.audit_log = audit_coll

    # Generic collection accessor — returns a mock collection per name
    _collections: dict = {"audit_log": audit_coll}

    def _get_collection(name):
        if name not in _collections:
            coll = MagicMock()
            coll.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
            coll.update_one = AsyncMock(return_value=MagicMock(matched_count=1, modified_count=1))
            coll.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
            coll.find_one = AsyncMock(return_value={"_id": ObjectId()})
            _collections[name] = coll
        return _collections[name]

    mock_db.__getitem__ = MagicMock(side_effect=_get_collection)
    svc._db = mock_db
    return svc, mock_db, _collections


# ---------------------------------------------------------------------------
# _log_audit
# ---------------------------------------------------------------------------

class TestLogAudit:
    """Verify the internal _log_audit helper."""

    @pytest.mark.asyncio
    async def test_writes_entry_to_audit_log_collection(self):
        svc, mock_db, _ = _make_service_with_mock_db()
        doc_id = ObjectId()

        await svc._log_audit("calls", AuditOperation.INSERT, doc_id, {"key": "val"})

        mock_db.audit_log.insert_one.assert_awaited_once()
        entry = mock_db.audit_log.insert_one.call_args[0][0]
        assert entry["collection"] == "calls"
        assert entry["operation"] == "insert"
        assert entry["document_id"] == doc_id
        assert isinstance(entry["timestamp"], datetime)
        assert entry["details"] == {"key": "val"}

    @pytest.mark.asyncio
    async def test_defaults_details_to_empty_dict(self):
        svc, mock_db, _ = _make_service_with_mock_db()

        await svc._log_audit("persons", AuditOperation.UPDATE, ObjectId())

        entry = mock_db.audit_log.insert_one.call_args[0][0]
        assert entry["details"] == {}

    @pytest.mark.asyncio
    async def test_does_not_raise_on_failure(self):
        """Audit logging failure must not propagate — only a warning is logged."""
        svc, mock_db, _ = _make_service_with_mock_db()
        mock_db.audit_log.insert_one = AsyncMock(side_effect=Exception("db down"))

        # Should NOT raise
        await svc._log_audit("calls", AuditOperation.DELETE, ObjectId())


# ---------------------------------------------------------------------------
# audited_insert
# ---------------------------------------------------------------------------

class TestAuditedInsert:
    """Verify audited_insert performs the insert and logs it."""

    @pytest.mark.asyncio
    async def test_inserts_document_and_returns_id(self):
        svc, mock_db, colls = _make_service_with_mock_db()
        expected_id = ObjectId()
        # Pre-create the collection mock with a known inserted_id
        coll = MagicMock()
        coll.insert_one = AsyncMock(return_value=MagicMock(inserted_id=expected_id))
        colls["warrants"] = coll
        mock_db.__getitem__ = MagicMock(side_effect=lambda n: colls.get(n, colls.setdefault(n, MagicMock())))

        result = await svc.audited_insert("warrants", {"charge": "speeding"})

        assert result == expected_id
        coll.insert_one.assert_awaited_once_with({"charge": "speeding"})

    @pytest.mark.asyncio
    async def test_creates_audit_entry_after_insert(self):
        svc, mock_db, _ = _make_service_with_mock_db()

        await svc.audited_insert("calls", {"type": "robbery"}, details={"source": "911"})

        mock_db.audit_log.insert_one.assert_awaited_once()
        entry = mock_db.audit_log.insert_one.call_args[0][0]
        assert entry["collection"] == "calls"
        assert entry["operation"] == "insert"
        assert entry["details"] == {"source": "911"}

    @pytest.mark.asyncio
    async def test_insert_succeeds_even_if_audit_fails(self):
        svc, mock_db, colls = _make_service_with_mock_db()
        mock_db.audit_log.insert_one = AsyncMock(side_effect=Exception("audit fail"))

        expected_id = ObjectId()
        coll = MagicMock()
        coll.insert_one = AsyncMock(return_value=MagicMock(inserted_id=expected_id))
        colls["vehicles"] = coll

        result = await svc.audited_insert("vehicles", {"plate": "ABC123"})
        assert result == expected_id


# ---------------------------------------------------------------------------
# audited_update
# ---------------------------------------------------------------------------

class TestAuditedUpdate:
    """Verify audited_update performs the update and logs it."""

    @pytest.mark.asyncio
    async def test_updates_document_and_creates_audit_entry(self):
        svc, mock_db, colls = _make_service_with_mock_db()
        doc_id = ObjectId()
        coll = MagicMock()
        coll.update_one = AsyncMock(return_value=MagicMock(matched_count=1))
        coll.find_one = AsyncMock(return_value={"_id": doc_id})
        colls["calls"] = coll

        result = await svc.audited_update(
            "calls",
            {"_id": doc_id},
            {"$set": {"status": "closed"}},
            details={"field": "status"},
        )

        assert result == doc_id
        coll.update_one.assert_awaited_once()
        mock_db.audit_log.insert_one.assert_awaited_once()
        entry = mock_db.audit_log.insert_one.call_args[0][0]
        assert entry["operation"] == "update"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_match(self):
        svc, mock_db, colls = _make_service_with_mock_db()
        coll = MagicMock()
        coll.update_one = AsyncMock(return_value=MagicMock(matched_count=0))
        colls["persons"] = coll

        result = await svc.audited_update("persons", {"name": "nobody"}, {"$set": {"x": 1}})

        assert result is None
        # No audit entry should be created for a no-op
        mock_db.audit_log.insert_one.assert_not_awaited()


# ---------------------------------------------------------------------------
# audited_delete
# ---------------------------------------------------------------------------

class TestAuditedDelete:
    """Verify audited_delete performs the delete and logs it."""

    @pytest.mark.asyncio
    async def test_deletes_document_and_creates_audit_entry(self):
        svc, mock_db, colls = _make_service_with_mock_db()
        doc_id = ObjectId()
        coll = MagicMock()
        coll.find_one = AsyncMock(return_value={"_id": doc_id})
        coll.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
        colls["bolos"] = coll

        result = await svc.audited_delete("bolos", {"_id": doc_id}, details={"reason": "cancelled"})

        assert result == doc_id
        coll.delete_one.assert_awaited_once_with({"_id": doc_id})
        mock_db.audit_log.insert_one.assert_awaited_once()
        entry = mock_db.audit_log.insert_one.call_args[0][0]
        assert entry["operation"] == "delete"
        assert entry["details"] == {"reason": "cancelled"}

    @pytest.mark.asyncio
    async def test_returns_none_when_document_not_found(self):
        svc, mock_db, colls = _make_service_with_mock_db()
        coll = MagicMock()
        coll.find_one = AsyncMock(return_value=None)
        coll.delete_one = AsyncMock()
        colls["citations"] = coll

        result = await svc.audited_delete("citations", {"_id": ObjectId()})

        assert result is None
        coll.delete_one.assert_not_awaited()
        mock_db.audit_log.insert_one.assert_not_awaited()
