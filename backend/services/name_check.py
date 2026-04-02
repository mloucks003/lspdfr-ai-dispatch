"""Name check lookup service.

Queries the persons collection by name and returns the full person record
including name, DOB, physical description, prior offenses, warrants, and
license status.

Requirements: 3.2, 3.4, 9.4
"""

import logging
import re
from typing import Any, Dict

from backend.services.database import DatabaseService

logger = logging.getLogger(__name__)

NO_RECORD_RESPONSE: Dict[str, Any] = {"status": "no_record"}


class NameCheckService:
    """Looks up person records by name."""

    def __init__(self, db: DatabaseService) -> None:
        self._db = db

    async def check_name(self, name: str) -> Dict[str, Any]:
        """Query the persons collection by name (case-insensitive).

        Args:
            name: The person's name to look up.

        Returns:
            The full person document (name, DOB, physical description,
            prior offenses, active warrants, license status) if found,
            otherwise ``{"status": "no_record"}``.
        """
        escaped = re.escape(name.strip())
        doc = await self._db.db.persons.find_one(
            {"name": {"$regex": f"^{escaped}$", "$options": "i"}}
        )

        if doc is None:
            logger.info("Name check for %r: no record on file", name)
            return dict(NO_RECORD_RESPONSE)

        logger.info("Name check for %r: found person %s", name, doc.get("_id"))
        return doc
