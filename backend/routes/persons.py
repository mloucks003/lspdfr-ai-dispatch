"""REST API endpoints for person search (Req 11.1, 11.3, 14.2)."""

import re
from typing import List

from fastapi import APIRouter, Query

from backend.models.person import Person

router = APIRouter(prefix="/api/persons", tags=["persons"])


def _get_db_service():
    """Lazy import to avoid circular dependency with backend.main."""
    from backend.main import db_service
    return db_service


# Regex: looks like a date if it matches YYYY-MM-DD or contains digits and dashes
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@router.get("", response_model=List[Person])
async def search_persons(q: str = Query("", description="Search by name or DOB")):
    """Search persons by name (text search) or date of birth (exact/regex).

    If *q* looks like a date (YYYY-MM-DD), search on ``date_of_birth``.
    Otherwise, use MongoDB text search on the ``name`` field.
    Returns results within 2 seconds (Req 11.3).
    """
    db = _get_db_service()

    if not q.strip():
        return []

    query = q.strip()

    if _DATE_PATTERN.match(query):
        # Exact match on date_of_birth
        cursor = db.db.persons.find({"date_of_birth": query})
    else:
        # Text search on name (text index exists)
        cursor = db.db.persons.find({"$text": {"$search": query}})

    results: list[dict] = await cursor.to_list(length=50)
    return [Person(**doc) for doc in results]
