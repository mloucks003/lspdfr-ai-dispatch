"""Plate check lookup service.

Queries the vehicles collection by plate number and returns the full vehicle
record including make, model, color, registered owner, and flags.

Requirements: 3.1, 3.4
"""

import logging
import re
from typing import Any, Dict

from backend.services.database import DatabaseService

logger = logging.getLogger(__name__)

NO_RECORD_RESPONSE: Dict[str, Any] = {"status": "no_record"}


class PlateCheckService:
    """Looks up vehicle records by plate number."""

    def __init__(self, db: DatabaseService) -> None:
        self._db = db

    async def check_plate(self, plate: str) -> Dict[str, Any]:
        """Query the vehicles collection by plate (case-insensitive).

        Args:
            plate: The license plate string to look up.

        Returns:
            The full vehicle document if found, otherwise
            ``{"status": "no_record"}``.
        """
        escaped = re.escape(plate.strip())
        doc = await self._db.db.vehicles.find_one(
            {"plate": {"$regex": f"^{escaped}$", "$options": "i"}}
        )

        if doc is None:
            logger.info("Plate check for %r: no record on file", plate)
            return dict(NO_RECORD_RESPONSE)

        logger.info("Plate check for %r: found vehicle %s", plate, doc.get("_id"))
        return doc
