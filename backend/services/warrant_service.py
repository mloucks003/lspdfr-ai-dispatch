"""Warrant check query service.

Queries the warrants collection for active warrants by person name.

Requirements: 6.3
"""

import logging
from typing import Any, Dict, List

from backend.models.enums import WarrantStatus
from backend.services.database import DatabaseService

logger = logging.getLogger(__name__)


class WarrantService:
    """Queries active warrants from MongoDB."""

    def __init__(self, db: DatabaseService) -> None:
        self._db = db

    async def check_warrants(self, name: str) -> List[Dict[str, Any]]:
        """Return all active warrants for the given person name.

        Args:
            name: The person's name to search for (case-insensitive).

        Returns:
            A list of active warrant documents, or an empty list.
        """
        cursor = self._db.db.warrants.find({
            "person_name": {"$regex": f"^{_escape_regex(name)}$", "$options": "i"},
            "status": WarrantStatus.ACTIVE.value,
        })
        warrants = await cursor.to_list(length=100)
        logger.info("Warrant check for %r: %d active warrant(s)", name, len(warrants))
        return warrants


def _escape_regex(text: str) -> str:
    """Escape special regex characters in *text* for safe use in $regex."""
    import re
    return re.escape(text)
