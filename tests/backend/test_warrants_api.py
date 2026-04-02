"""Unit tests for the warrants REST API endpoints (Req 12.2, 12.4, 12.5, 12.6, 14.2)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from backend.models.enums import WarrantStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_warrant_doc(
    *,
    person_name: str = "John Smith",
    person_id: ObjectId | None = None,
    charge: str = "Grand Theft Auto",
    issuing_authority: str = "Los Santos Superior Court",
    status: str = WarrantStatus.ACTIVE.value,
    date_served: datetime | None = None,
    _id: ObjectId | None = None,
) -> dict:
    """Build a raw MongoDB warrant document."""
    return {
        "_id": _id or ObjectId(),
        "person_name": person_name,
        "person_id": person_id,
        "charge": charge,
        "issuing_authority": issuing_authority,
        "date_issued": "2024-01-10T08:00:00",
        "status": status,
        "date_served": date_served,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def _make_person_doc(
    *,
    name: str = "John Smith",
    active_warrants: list | None = None,
    _id: ObjectId | None = None,
) -> dict:
    """Build a minimal person document for lookup."""
    return {
        "_id": _id or ObjectId(),
        "name": name,
        "active_warrants": active_warrants or [],
    }


class _FakeCursor:
    """Minimal async cursor mock that supports .to_list()."""

    def __init__(self, docs: list[dict]):
        self._docs = docs

    async def to_list(self, length: int = 1000):
        return self._docs[:length]


def _patch_db_service(mock_db):
    """Return a patch context manager that replaces _get_db_service in the warrants module."""
    fake_svc = MagicMock()
    fake_svc.db = mock_db
    fake_svc.audited_insert = AsyncMock()
    fake_svc.audited_update = AsyncMock()
    return patch("backend.routes.warrants._get_db_service", return_value=fake_svc), fake_svc


# ---------------------------------------------------------------------------
# GET /api/warrants
# ---------------------------------------------------------------------------

class TestListWarrants:
    """GET /api/warrants lists warrants with optional filtering."""

    @pytest.mark.asyncio
    async def test_list_all_warrants(self):
        docs = [
            _make_warrant_doc(person_name="John Smith"),
            _make_warrant_doc(person_name="Jane Doe", charge="Assault"),
        ]

        mock_db = MagicMock()
        mock_db.warrants.find = MagicMock(return_value=_FakeCursor(docs))

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/warrants")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_filter_active_warrants(self):
        captured_query = {}

        def fake_find(query):
            captured_query.update(query)
            return _FakeCursor([_make_warrant_doc()])

        mock_db = MagicMock()
        mock_db.warrants.find = MagicMock(side_effect=fake_find)

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/warrants", params={"active": "true"})

        assert resp.status_code == 200
        assert captured_query.get("status") == "active"

    @pytest.mark.asyncio
    async def test_filter_by_person_name(self):
        captured_query = {}

        def fake_find(query):
            captured_query.update(query)
            return _FakeCursor([_make_warrant_doc(person_name="John Smith")])

        mock_db = MagicMock()
        mock_db.warrants.find = MagicMock(side_effect=fake_find)

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/warrants", params={"person_name": "John"})

        assert resp.status_code == 200
        assert "person_name" in captured_query
        assert captured_query["person_name"]["$regex"] == "John"

    @pytest.mark.asyncio
    async def test_filter_by_charge(self):
        captured_query = {}

        def fake_find(query):
            captured_query.update(query)
            return _FakeCursor([_make_warrant_doc(charge="Grand Theft Auto")])

        mock_db = MagicMock()
        mock_db.warrants.find = MagicMock(side_effect=fake_find)

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/warrants", params={"charge": "Theft"})

        assert resp.status_code == 200
        assert "charge" in captured_query
        assert captured_query["charge"]["$regex"] == "Theft"

    @pytest.mark.asyncio
    async def test_combined_filters(self):
        captured_query = {}

        def fake_find(query):
            captured_query.update(query)
            return _FakeCursor([])

        mock_db = MagicMock()
        mock_db.warrants.find = MagicMock(side_effect=fake_find)

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/api/warrants",
                    params={"active": "true", "person_name": "John", "charge": "Theft"},
                )

        assert resp.status_code == 200
        assert captured_query.get("status") == "active"
        assert "person_name" in captured_query
        assert "charge" in captured_query

    @pytest.mark.asyncio
    async def test_empty_results(self):
        mock_db = MagicMock()
        mock_db.warrants.find = MagicMock(return_value=_FakeCursor([]))

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/warrants", params={"active": "true"})

        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /api/warrants
# ---------------------------------------------------------------------------

class TestCreateWarrant:
    """POST /api/warrants creates a warrant and flags the person record."""

    @pytest.mark.asyncio
    async def test_creates_warrant_and_flags_person(self):
        person_oid = ObjectId()
        warrant_oid = ObjectId()
        person_doc = _make_person_doc(name="John Smith", _id=person_oid)
        warrant_doc = _make_warrant_doc(_id=warrant_oid, person_name="John Smith")

        mock_db = MagicMock()
        mock_db.persons.find_one = AsyncMock(return_value=person_doc)
        mock_db.warrants.find_one = AsyncMock(return_value=warrant_doc)

        patcher, fake_svc = _patch_db_service(mock_db)
        fake_svc.audited_insert = AsyncMock(return_value=warrant_oid)
        fake_svc.audited_update = AsyncMock(return_value=person_oid)

        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/warrants",
                    json={
                        "person_name": "John Smith",
                        "charge": "Grand Theft Auto",
                        "issuing_authority": "Los Santos Superior Court",
                        "date_issued": "2024-01-10T08:00:00",
                    },
                )

        assert resp.status_code == 201
        data = resp.json()
        assert data["person_name"] == "John Smith"
        assert data["status"] == "active"

        # Verify audited_insert was called for the warrant
        fake_svc.audited_insert.assert_awaited_once()
        insert_args = fake_svc.audited_insert.call_args
        assert insert_args[0][0] == "warrants"
        inserted_doc = insert_args[0][1]
        assert inserted_doc["status"] == "active"

        # Verify audited_update was called to flag the person
        fake_svc.audited_update.assert_awaited_once()
        update_args = fake_svc.audited_update.call_args
        assert update_args[0][0] == "persons"
        assert update_args[0][1] == {"_id": person_oid}
        assert "$push" in update_args[0][2]
        assert update_args[0][2]["$push"]["active_warrants"] == warrant_oid

    @pytest.mark.asyncio
    async def test_creates_warrant_without_person_match(self):
        """When person is not found, warrant is still created but person is not flagged."""
        warrant_oid = ObjectId()
        warrant_doc = _make_warrant_doc(_id=warrant_oid, person_name="Unknown Person")

        mock_db = MagicMock()
        mock_db.persons.find_one = AsyncMock(return_value=None)
        mock_db.warrants.find_one = AsyncMock(return_value=warrant_doc)

        patcher, fake_svc = _patch_db_service(mock_db)
        fake_svc.audited_insert = AsyncMock(return_value=warrant_oid)

        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/warrants",
                    json={
                        "person_name": "Unknown Person",
                        "charge": "Assault",
                        "issuing_authority": "Los Santos Superior Court",
                        "date_issued": "2024-02-01T09:00:00",
                    },
                )

        assert resp.status_code == 201
        # audited_update should NOT have been called (no person to flag)
        fake_svc.audited_update.assert_not_awaited()


# ---------------------------------------------------------------------------
# PUT /api/warrants/{id}/serve
# ---------------------------------------------------------------------------

class TestServeWarrant:
    """PUT /api/warrants/{id}/serve marks a warrant as served."""

    @pytest.mark.asyncio
    async def test_marks_warrant_as_served(self):
        oid = ObjectId()
        served_doc = _make_warrant_doc(
            _id=oid,
            status=WarrantStatus.SERVED.value,
            date_served=datetime.now(timezone.utc),
        )

        mock_db = MagicMock()
        mock_db.warrants.find_one = AsyncMock(return_value=served_doc)

        patcher, fake_svc = _patch_db_service(mock_db)
        fake_svc.audited_update = AsyncMock(return_value=oid)

        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.put(f"/api/warrants/{oid}/serve")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "served"
        assert data["date_served"] is not None

        # Verify audited_update was called with correct fields
        fake_svc.audited_update.assert_awaited_once()
        call_args = fake_svc.audited_update.call_args
        assert call_args[0][0] == "warrants"
        update_ops = call_args[0][2]
        assert update_ops["$set"]["status"] == "served"
        assert "date_served" in update_ops["$set"]

    @pytest.mark.asyncio
    async def test_returns_404_for_missing_warrant(self):
        mock_db = MagicMock()

        patcher, fake_svc = _patch_db_service(mock_db)
        fake_svc.audited_update = AsyncMock(return_value=None)

        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.put(f"/api/warrants/{ObjectId()}/serve")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_id(self):
        mock_db = MagicMock()

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.put("/api/warrants/bad-id/serve")

        assert resp.status_code == 400
