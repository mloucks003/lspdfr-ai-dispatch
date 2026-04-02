"""Unit tests for the calls REST API endpoints (Req 10.1, 10.4, 10.5, 14.2)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from backend.models.enums import CallStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_call_doc(
    *,
    priority: int = 2,
    status: str = CallStatus.PENDING.value,
    call_number: str = "2024-001",
    call_type: str = "robbery",
    notes: list | None = None,
    disposition: str | None = None,
    _id: ObjectId | None = None,
) -> dict:
    """Build a raw MongoDB call document."""
    return {
        "_id": _id or ObjectId(),
        "call_number": call_number,
        "type": call_type,
        "priority": priority,
        "location": {"street": "Vinewood Blvd", "landmark": None, "coordinates": None},
        "description": "Test call",
        "suspect_description": None,
        "assigned_units": [],
        "status": status,
        "notes": notes or [],
        "disposition": disposition,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


class _FakeCursor:
    """Minimal async cursor mock that supports .sort() and .to_list()."""

    def __init__(self, docs: list[dict]):
        self._docs = docs

    def sort(self, key, direction):
        self._docs.sort(key=lambda d: d.get(key, 0), reverse=(direction == -1))
        return self

    async def to_list(self, length: int = 1000):
        return self._docs[:length]


def _patch_db_service(mock_db):
    """Return a patch context manager that replaces _get_db_service in the calls module."""
    fake_svc = MagicMock()
    fake_svc.db = mock_db
    fake_svc.audited_update = AsyncMock()
    return patch("backend.routes.calls._get_db_service", return_value=fake_svc), fake_svc


# ---------------------------------------------------------------------------
# GET /api/calls
# ---------------------------------------------------------------------------

class TestListActiveCalls:
    """GET /api/calls returns non-closed calls sorted by priority ascending."""

    @pytest.mark.asyncio
    async def test_returns_active_calls_sorted_by_priority(self):
        docs = [
            _make_call_doc(priority=3, call_number="C-003"),
            _make_call_doc(priority=1, call_number="C-001"),
            _make_call_doc(priority=2, call_number="C-002"),
        ]

        mock_db = MagicMock()
        mock_db.calls.find = MagicMock(return_value=_FakeCursor(docs))

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/calls")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        priorities = [c["priority"] for c in data]
        assert priorities == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_active_calls(self):
        mock_db = MagicMock()
        mock_db.calls.find = MagicMock(return_value=_FakeCursor([]))

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/calls")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_excludes_closed_calls(self):
        """The find filter should exclude closed status — verified via the query arg."""
        captured_filter = {}

        def fake_find(query):
            captured_filter.update(query)
            return _FakeCursor([])

        mock_db = MagicMock()
        mock_db.calls.find = MagicMock(side_effect=fake_find)

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/api/calls")

        assert captured_filter == {"status": {"$ne": "closed"}}


# ---------------------------------------------------------------------------
# GET /api/calls/{id}
# ---------------------------------------------------------------------------

class TestGetCall:
    """GET /api/calls/{id} returns a single call or appropriate error."""

    @pytest.mark.asyncio
    async def test_returns_call_by_id(self):
        oid = ObjectId()
        doc = _make_call_doc(_id=oid)

        mock_db = MagicMock()
        mock_db.calls.find_one = AsyncMock(return_value=doc)

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(f"/api/calls/{oid}")

        assert resp.status_code == 200
        assert resp.json()["_id"] == str(oid)

    @pytest.mark.asyncio
    async def test_returns_404_for_missing_call(self):
        mock_db = MagicMock()
        mock_db.calls.find_one = AsyncMock(return_value=None)

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(f"/api/calls/{ObjectId()}")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_id(self):
        mock_db = MagicMock()

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/calls/not-an-objectid")

        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# PUT /api/calls/{id}
# ---------------------------------------------------------------------------

class TestUpdateCall:
    """PUT /api/calls/{id} updates notes and/or disposition."""

    @pytest.mark.asyncio
    async def test_add_note_to_call(self):
        oid = ObjectId()
        updated_doc = _make_call_doc(
            _id=oid,
            notes=[{"text": "Suspect fled", "author": "1-Adam-12", "timestamp": datetime.now(timezone.utc).isoformat()}],
        )

        mock_db = MagicMock()
        mock_db.calls.find_one = AsyncMock(return_value=updated_doc)

        patcher, fake_svc = _patch_db_service(mock_db)
        fake_svc.audited_update = AsyncMock(return_value=oid)

        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.put(
                    f"/api/calls/{oid}",
                    json={"note": {"text": "Suspect fled", "author": "1-Adam-12"}},
                )

        assert resp.status_code == 200
        fake_svc.audited_update.assert_awaited_once()
        call_args = fake_svc.audited_update.call_args
        # Verify $push was used for the note
        update_ops = call_args[0][2]  # third positional arg
        assert "$push" in update_ops
        assert "notes" in update_ops["$push"]

    @pytest.mark.asyncio
    async def test_update_disposition(self):
        oid = ObjectId()
        updated_doc = _make_call_doc(_id=oid, disposition="report_filed")

        mock_db = MagicMock()
        mock_db.calls.find_one = AsyncMock(return_value=updated_doc)

        patcher, fake_svc = _patch_db_service(mock_db)
        fake_svc.audited_update = AsyncMock(return_value=oid)

        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.put(
                    f"/api/calls/{oid}",
                    json={"disposition": "report_filed"},
                )

        assert resp.status_code == 200
        call_args = fake_svc.audited_update.call_args
        update_ops = call_args[0][2]
        assert update_ops["$set"]["disposition"] == "report_filed"

    @pytest.mark.asyncio
    async def test_update_both_note_and_disposition(self):
        oid = ObjectId()
        updated_doc = _make_call_doc(_id=oid, disposition="arrest", notes=[{"text": "Cuffed", "author": "1-Adam-12", "timestamp": datetime.now(timezone.utc).isoformat()}])

        mock_db = MagicMock()
        mock_db.calls.find_one = AsyncMock(return_value=updated_doc)

        patcher, fake_svc = _patch_db_service(mock_db)
        fake_svc.audited_update = AsyncMock(return_value=oid)

        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.put(
                    f"/api/calls/{oid}",
                    json={
                        "note": {"text": "Cuffed", "author": "1-Adam-12"},
                        "disposition": "arrest",
                    },
                )

        assert resp.status_code == 200
        call_args = fake_svc.audited_update.call_args
        update_ops = call_args[0][2]
        assert "$push" in update_ops
        assert update_ops["$set"]["disposition"] == "arrest"

    @pytest.mark.asyncio
    async def test_returns_404_when_call_not_found(self):
        mock_db = MagicMock()

        patcher, fake_svc = _patch_db_service(mock_db)
        fake_svc.audited_update = AsyncMock(return_value=None)

        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.put(
                    f"/api/calls/{ObjectId()}",
                    json={"disposition": "closed"},
                )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_id(self):
        mock_db = MagicMock()

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.put(
                    "/api/calls/bad-id",
                    json={"disposition": "closed"},
                )

        assert resp.status_code == 400
