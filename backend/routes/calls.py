"""REST API endpoints for CAD calls (Req 10.1, 10.4, 10.5, 14.2)."""

from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.models.cad_call import CADCall
from backend.models.enums import CallStatus

router = APIRouter(prefix="/api/calls", tags=["calls"])


def _get_db_service():
    """Lazy import to avoid circular dependency with backend.main."""
    from backend.main import db_service
    return db_service


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class CallNoteIn(BaseModel):
    """Payload for adding a note to a call."""
    text: str
    author: str


class CallUpdateIn(BaseModel):
    """Payload for PUT /api/calls/{id}."""
    note: Optional[CallNoteIn] = None
    disposition: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=List[CADCall])
async def list_active_calls():
    """Return all non-closed calls sorted by priority ascending (1 first)."""
    db = _get_db_service()
    cursor = db.db.calls.find(
        {"status": {"$ne": CallStatus.CLOSED.value}},
    ).sort("priority", 1)
    results: list[dict] = await cursor.to_list(length=1000)
    return [CADCall(**doc) for doc in results]


@router.get("/{call_id}", response_model=CADCall)
async def get_call(call_id: str):
    """Return a single call by its ObjectId."""
    if not ObjectId.is_valid(call_id):
        raise HTTPException(status_code=400, detail="Invalid call ID")

    db = _get_db_service()
    doc = await db.db.calls.find_one({"_id": ObjectId(call_id)})
    if doc is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return CADCall(**doc)


@router.put("/{call_id}", response_model=CADCall)
async def update_call(call_id: str, body: CallUpdateIn):
    """Update call notes and/or disposition."""
    if not ObjectId.is_valid(call_id):
        raise HTTPException(status_code=400, detail="Invalid call ID")

    oid = ObjectId(call_id)
    db = _get_db_service()

    set_fields: dict = {"updated_at": datetime.now(timezone.utc)}
    push_fields: dict = {}

    if body.disposition is not None:
        set_fields["disposition"] = body.disposition

    if body.note is not None:
        push_fields["notes"] = {
            "text": body.note.text,
            "author": body.note.author,
            "timestamp": datetime.now(timezone.utc),
        }

    update_ops: dict = {"$set": set_fields}
    if push_fields:
        update_ops["$push"] = push_fields

    details = {}
    if body.note is not None:
        details["added_note"] = body.note.text
    if body.disposition is not None:
        details["disposition"] = body.disposition

    result = await db.audited_update(
        "calls",
        {"_id": oid},
        update_ops,
        details=details,
    )

    if result is None:
        raise HTTPException(status_code=404, detail="Call not found")

    doc = await db.db.calls.find_one({"_id": oid})
    return CADCall(**doc)
