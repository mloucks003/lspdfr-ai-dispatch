"""Unit tests for the citations REST API endpoints (Req 12.1, 12.3, 14.2)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_citation_doc(
    *,
    person_name: str = "John Smith",
    person_id: ObjectId | None = None,
    violation_type: str = "Speeding",
    location: str = "Vinewood Blvd",
    date: str = "2024-01-15T10:30:00",
    officer_callsign: str = "1-Adam-12",
    _id: ObjectId | None = None,
) -> dict:
    """Build a raw MongoDB citation document."""
    return {
        "_id": _id or ObjectId(),
        "person_name": person_name,
        "person_id": person_id,
        "violation_type": violation_type,
        "location": location,
        "date": date,
        "officer_callsign": officer_callsign,
        "created_at": datetime.now(timezone.utc),
    }


def _make_person_doc(
    *,
    name: str = "John Smith",
    _id: ObjectId | None = None,
) -> dict:
    """Build a minimal person document for lookup."""
    return {
        "_id": _id or ObjectId(),
        "name": name,
    }


def _patch_db_service(mock_db):
    """Return a patch context manager that replaces _get_db_service in the citations module."""
    fake_svc = MagicMock()
    fake_svc.db = mock_db
    fake_svc.audited_insert = AsyncMock()
    return patch("backend.routes.citations._get_db_service", return_value=fake_svc), fake_svc


# ---------------------------------------------------------------------------
# POST /api/citations
# ---------------------------------------------------------------------------

class TestCreateCitation:
    """POST /api/citations creates a citation and links to person record."""

    @pytest.mark.asyncio
    async def test_creates_citation_with_person_link(self):
        person_oid = ObjectId()
        citation_oid = ObjectId()
        person_doc = _make_person_doc(name="John Smith", _id=person_oid)
        citation_doc = _make_citation_doc(
            _id=citation_oid,
            person_name="John Smith",
            person_id=person_oid,
        )

        mock_db = MagicMock()
        mock_db.persons.find_one = AsyncMock(return_value=person_doc)
        mock_db.citations.find_one = AsyncMock(return_value=citation_doc)

        patcher, fake_svc = _patch_db_service(mock_db)
        fake_svc.audited_insert = AsyncMock(return_value=citation_oid)

        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/citations",
                    json={
                        "person_name": "John Smith",
                        "violation_type": "Speeding",
                        "location": "Vinewood Blvd",
                        "date": "2024-01-15T10:30:00",
                        "officer_callsign": "1-Adam-12",
                    },
                )

        assert resp.status_code == 201
        data = resp.json()
        assert data["person_name"] == "John Smith"
        assert data["person_id"] == str(person_oid)
        assert data["violation_type"] == "Speeding"

        # Verify audited_insert was called with person_id set
        fake_svc.audited_insert.assert_awaited_once()
        insert_args = fake_svc.audited_insert.call_args
        inserted_doc = insert_args[0][1]
        assert inserted_doc["person_id"] == person_oid

    @pytest.mark.asyncio
    async def test_creates_citation_without_person_match(self):
        """When person is not found, person_id should be None."""
        citation_oid = ObjectId()
        citation_doc = _make_citation_doc(
            _id=citation_oid,
            person_name="Unknown Person",
            person_id=None,
        )

        mock_db = MagicMock()
        mock_db.persons.find_one = AsyncMock(return_value=None)
        mock_db.citations.find_one = AsyncMock(return_value=citation_doc)

        patcher, fake_svc = _patch_db_service(mock_db)
        fake_svc.audited_insert = AsyncMock(return_value=citation_oid)

        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/citations",
                    json={
                        "person_name": "Unknown Person",
                        "violation_type": "Running Red Light",
                        "location": "Del Perro Blvd",
                        "date": "2024-02-20T14:00:00",
                        "officer_callsign": "2-Adam-14",
                    },
                )

        assert resp.status_code == 201
        data = resp.json()
        assert data["person_name"] == "Unknown Person"
        assert data["person_id"] is None

        # Verify audited_insert was called with person_id=None
        insert_args = fake_svc.audited_insert.call_args
        inserted_doc = insert_args[0][1]
        assert inserted_doc["person_id"] is None

    @pytest.mark.asyncio
    async def test_uses_audited_insert(self):
        """Verify the citation is created via audited_insert for audit logging."""
        citation_oid = ObjectId()
        citation_doc = _make_citation_doc(_id=citation_oid)

        mock_db = MagicMock()
        mock_db.persons.find_one = AsyncMock(return_value=None)
        mock_db.citations.find_one = AsyncMock(return_value=citation_doc)

        patcher, fake_svc = _patch_db_service(mock_db)
        fake_svc.audited_insert = AsyncMock(return_value=citation_oid)

        with patcher:
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.post(
                    "/api/citations",
                    json={
                        "person_name": "John Smith",
                        "violation_type": "Speeding",
                        "location": "Vinewood Blvd",
                        "date": "2024-01-15T10:30:00",
                        "officer_callsign": "1-Adam-12",
                    },
                )

        fake_svc.audited_insert.assert_awaited_once()
        call_args = fake_svc.audited_insert.call_args
        assert call_args[0][0] == "citations"
