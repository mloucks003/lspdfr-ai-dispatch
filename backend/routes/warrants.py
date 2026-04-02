"""REST API endpoints for warrants (Req 12.2, 12.4, 12.5, 12.6, 14.2)."""

from datetime import datetime, timezone
from typing import List, Optional

try:
    from bson import ObjectId
except ImportError:
    ObjectId = None
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.models.enums import WarrantStatus
from backend.models.warrant import Warrant

router = APIRouter(prefix="/api/warrants", tags=["warrants"])


def _get_db_service():
    """Lazy import to avoid circular dependency with backend.main."""
    from backend.main import db_service
    return db_service


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class WarrantCreateIn(BaseModel):
    """Payload for POST /api/warrants."""
    person_name: str
    charge: str
    issuing_authority: str
    date_issued: str  # ISO datetime string


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=List[Warrant])
async def list_warrants(
    active: Optional[bool] = Query(None, description="Filter by active status"),
    person_name: Optional[str] = Query(None, description="Filter by person name"),
    charge: Optional[str] = Query(None, description="Filter by charge"),
):
    """List warrants with optional filtering (Req 12.5)."""
    db = _get_db_service()

    query: dict = {}
    if active is True:
        query["status"] = WarrantStatus.ACTIVE.value
    if person_name:
        query["person_name"] = {"$regex": person_name, "$options": "i"}
    if charge:
        query["charge"] = {"$regex": charge, "$options": "i"}

    cursor = db.db.warrants.find(query)
    results: list[dict] = await cursor.to_list(length=1000)
    return [Warrant(**doc) for doc in results]


@router.post("", response_model=Warrant, status_code=201)
async def create_warrant(body: WarrantCreateIn):
    """Create a warrant and flag the person record (Req 12.4)."""
    db = _get_db_service()

    doc = {
        "person_name": body.person_name,
        "charge": body.charge,
        "issuing_authority": body.issuing_authority,
        "date_issued": body.date_issued,
        "status": WarrantStatus.ACTIVE.value,
        "date_served": None,
    }

    inserted_id = await db.audited_insert(
        "warrants",
        doc,
        details={"person_name": body.person_name, "charge": body.charge},
    )

    # Flag the person record with the new warrant (Req 12.4)
    person_doc = await db.db.persons.find_one({"name": body.person_name})
    if person_doc:
        await db.audited_update(
            "persons",
            {"_id": person_doc["_id"]},
            {"$push": {"active_warrants": inserted_id}},
            details={"added_warrant": str(inserted_id)},
        )

    created = await db.db.warrants.find_one({"_id": inserted_id})
    return Warrant(**created)


@router.put("/{warrant_id}/serve", response_model=Warrant)
async def serve_warrant(warrant_id: str):
    """Mark a warrant as served (Req 12.6)."""
    if ObjectId is not None and not ObjectId.is_valid(warrant_id):
        raise HTTPException(status_code=400, detail="Invalid warrant ID")

    oid = warrant_id
    db = _get_db_service()

    result = await db.audited_update(
        "warrants",
        {"_id": oid},
        {
            "$set": {
                "status": WarrantStatus.SERVED.value,
                "date_served": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        },
        details={"action": "serve_warrant"},
    )

    if result is None:
        raise HTTPException(status_code=404, detail="Warrant not found")

    doc = await db.db.warrants.find_one({"_id": oid})
    return Warrant(**doc)
