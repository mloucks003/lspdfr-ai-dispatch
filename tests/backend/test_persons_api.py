"""Unit tests for the persons REST API endpoints (Req 11.1, 11.3, 14.2)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_person_doc(
    *,
    name: str = "John Smith",
    date_of_birth: str = "1990-05-15",
    _id: ObjectId | None = None,
) -> dict:
    """Build a raw MongoDB person document."""
    return {
        "_id": _id or ObjectId(),
        "name": name,
        "date_of_birth": date_of_birth,
        "physical_description": {
            "gender": "Male",
            "race": "White",
            "height": "6'0",
            "weight": "180",
            "hair_color": "Brown",
            "distinguishing_marks": None,
        },
        "prior_offenses": [],
        "active_warrants": [],
        "license_status": "valid",
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
    """Return a patch context manager that replaces _get_db_service in the persons module."""
    fake_svc = MagicMock()
    fake_svc.db = mock_db
    return patch("backend.routes.persons._get_db_service", return_value=fake_svc), fake_svc


# ---------------------------------------------------------------------------
# GET /api/persons?q=
# ---------------------------------------------------------------------------

class TestSearchPersons:
    """GET /api/persons?q= searches persons by name or DOB."""

    @pytest.mark.asyncio
    async def test_search_by_name_uses_text_search(self):
        docs = [_make_person_doc(name="John Smith")]
        captured_query = {}

        def fake_find(query):
            captured_query.update(query)
            return _FakeCursor(docs)

        mock_db = MagicMock()
        mock_db.persons.find = MagicMock(side_effect=fake_find)

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/persons", params={"q": "John"})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "John Smith"
        # Verify text search was used
        assert "$text" in captured_query

    @pytest.mark.asyncio
    async def test_search_by_dob_uses_exact_match(self):
        docs = [_make_person_doc(date_of_birth="1990-05-15")]
        captured_query = {}

        def fake_find(query):
            captured_query.update(query)
            return _FakeCursor(docs)

        mock_db = MagicMock()
        mock_db.persons.find = MagicMock(side_effect=fake_find)

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/persons", params={"q": "1990-05-15"})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        # Verify exact date match was used (not text search)
        assert "date_of_birth" in captured_query

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty_list(self):
        mock_db = MagicMock()

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/persons", params={"q": ""})

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
                resp = await client.get("/api/persons")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_no_results_returns_empty_list(self):
        mock_db = MagicMock()
        mock_db.persons.find = MagicMock(return_value=_FakeCursor([]))

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/persons", params={"q": "Nobody"})

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_returns_full_person_record(self):
        """Verify the response includes all person fields (Req 11.4)."""
        oid = ObjectId()
        doc = _make_person_doc(_id=oid, name="Jane Doe", date_of_birth="1985-03-22")
        doc["prior_offenses"] = [{"offense": "Speeding", "date": "2023-01-01", "disposition": "Fine"}]
        doc["license_status"] = "suspended"

        mock_db = MagicMock()
        mock_db.persons.find = MagicMock(return_value=_FakeCursor([doc]))

        patcher, _ = _patch_db_service(mock_db)
        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get("/api/persons", params={"q": "Jane"})

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        person = data[0]
        assert person["name"] == "Jane Doe"
        assert person["date_of_birth"] == "1985-03-22"
        assert person["physical_description"]["gender"] == "Male"
        assert len(person["prior_offenses"]) == 1
        assert person["license_status"] == "suspended"
