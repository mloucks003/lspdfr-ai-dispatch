"""REST API endpoints for vehicle search (Req 11.2, 11.3, 14.2)."""

from typing import List

from fastapi import APIRouter, Query

from backend.models.vehicle import Vehicle

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


def _get_db_service():
    """Lazy import to avoid circular dependency with backend.main."""
    from backend.main import db_service
    return db_service


@router.get("", response_model=List[Vehicle])
async def search_vehicles(q: str = Query("", description="Search by plate, make, or model")):
    """Search vehicles by plate (exact match first) then text search on make/model.

    Returns results within 2 seconds (Req 11.3).
    """
    db = _get_db_service()

    if not q.strip():
        return []

    query = q.strip()

    # Try exact plate match first
    plate_doc = await db.db.vehicles.find_one({"plate": query.upper()})
    if plate_doc is not None:
        return [Vehicle(**plate_doc)]

    # Fall back to text search on make/model
    cursor = db.db.vehicles.find({"$text": {"$search": query}})
    results: list[dict] = await cursor.to_list(length=50)
    return [Vehicle(**doc) for doc in results]
