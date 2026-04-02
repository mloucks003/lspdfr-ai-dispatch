"""REST API endpoints for citations (Req 12.1, 12.3, 14.2)."""

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.models.citation import Citation

router = APIRouter(prefix="/api/citations", tags=["citations"])


def _get_db_service():
    """Lazy import to avoid circular dependency with backend.main."""
    from backend.main import db_service
    return db_service


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class CitationCreateIn(BaseModel):
    """Payload for POST /api/citations."""
    person_name: str
    violation_type: str
    location: str
    date: str  # ISO datetime string
    officer_callsign: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=Citation, status_code=201)
async def create_citation(body: CitationCreateIn):
    """Create a citation and link it to the person record (Req 12.3)."""
    db = _get_db_service()

    # Look up person by name to get person_id
    person_doc = await db.db.persons.find_one({"name": body.person_name})
    person_id = person_doc["_id"] if person_doc else None

    doc = {
        "person_name": body.person_name,
        "person_id": person_id,
        "violation_type": body.violation_type,
        "location": body.location,
        "date": body.date,
        "officer_callsign": body.officer_callsign,
    }

    inserted_id = await db.audited_insert(
        "citations",
        doc,
        details={"person_name": body.person_name, "violation_type": body.violation_type},
    )

    created = await db.db.citations.find_one({"_id": inserted_id})
    return Citation(**created)
