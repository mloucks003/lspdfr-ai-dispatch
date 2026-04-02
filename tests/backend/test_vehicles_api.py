"""Unit tests for the vehicles REST API endpoints (Req 11.2, 11.3, 14.2)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vehicle_doc(
    *,
    plate: str = "ABC1234",
    make: str = "Vapid",
    model: str = "Crown Victoria",
    color: str = "Black",
    registered_owner: str = "John Smith",
    flags: list[str] | None = None,
    _id: ObjectId | None = None,
) -> dict:
    """Build a raw MongoDB vehicle document."""
    return {
        "_id": _id or ObjectId(),
        "plate": plate,
        "make": make,
        "model": model,
        "color": color,
        "registered_owner": registered_owner,
        "flags": flags or [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


class _FakeCursor:
    """Minimal async cursor mock that supports .to_list()."""

    def __init__(self, docs: list[dict]):
        self._docs = docs

    async def to_list(self, length: int = 50):
        return self._docs[:length]


def _patch_db_service(mock_db):
    """Return a patch context manager that replaces _get_db_service in the vehicles module."""
    fake_svc = MagicMock()
    fake_svc.db = mock_db
    return patch("backend.routes.vehicles._get_db_service", return_value=fake_svc), fake_svc


# ---------------------------------------------------------------------------
# GET /api/vehicles?q=
# ---------------------------------------------------------------------------

class TestSearchVehicles:
    """GET /api/vehicles?q= searches vehicles by plate, make, or model."""

    @pytest.mark.asyncio
    async def test_exact_plate_match_returns_vehicle(self):
        doc = _make_vehicle_doc(plate="ABC1234")

        mock_db = MagicMock()
        mock_db.vehicles.find_one = AsyncMock(return_value=doc)

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/vehicles", params={"q": "abc1234"})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["plate"] == "ABC1234"
        # Verify find_one was called with uppercased plate
        mock_db.vehicles.find_one.assert_awaited_once_with({"plate": "ABC1234"})

    @pytest.mark.asyncio
    async def test_text_search_fallback_when_no_plate_match(self):
        """When plate exact match fails, fall back to text search on make/model."""
        doc = _make_vehicle_doc(make="Vapid", model="Crown Victoria")
        captured_query = {}

        def fake_find(query):
            captured_query.update(query)
            return _FakeCursor([doc])

        mock_db = MagicMock()
        mock_db.vehicles.find_one = AsyncMock(return_value=None)
        mock_db.vehicles.find = MagicMock(side_effect=fake_find)

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/vehicles", params={"q": "Vapid"})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["make"] == "Vapid"
        # Verify text search was used
        assert "$text" in captured_query

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty_list(self):
        mock_db = MagicMock()

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/vehicles", params={"q": ""})

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_no_query_param_returns_empty_list(self):
        mock_db = MagicMock()

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/vehicles")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_no_results_returns_empty_list(self):
        mock_db = MagicMock()
        mock_db.vehicles.find_one = AsyncMock(return_value=None)
        mock_db.vehicles.find = MagicMock(return_value=_FakeCursor([]))

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/vehicles", params={"q": "Nonexistent"})

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_returns_full_vehicle_record(self):
        """Verify the response includes all vehicle fields (Req 11.5)."""
        oid = ObjectId()
        doc = _make_vehicle_doc(
            _id=oid,
            plate="XYZ9999",
            make="Benefactor",
            model="Schafter",
            color="Silver",
            registered_owner="Jane Doe",
            flags=["stolen", "bolo"],
        )

        mock_db = MagicMock()
        mock_db.vehicles.find_one = AsyncMock(return_value=doc)

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/vehicles", params={"q": "XYZ9999"})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        vehicle = data[0]
        assert vehicle["plate"] == "XYZ9999"
        assert vehicle["make"] == "Benefactor"
        assert vehicle["model"] == "Schafter"
        assert vehicle["color"] == "Silver"
        assert vehicle["registered_owner"] == "Jane Doe"
        assert vehicle["flags"] == ["stolen", "bolo"]
