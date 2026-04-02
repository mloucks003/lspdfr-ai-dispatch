"""Game state upsert service.

Upserts ped and vehicle data received from the LSPDFR plugin so the
database stays current with the game world.  Idempotent: upserting the
same data twice results in exactly one record.

Requirements: 11.6
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.services.database import DatabaseService

logger = logging.getLogger(__name__)


class GameStateService:
    """Upserts ped and vehicle records from plugin game state updates."""

    def __init__(self, db: DatabaseService) -> None:
        self._db = db

    async def upsert_person(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert a person/ped record, matching on name (case-insensitive).

        Args:
            data: Dict with at least ``name``.  May also contain
                ``physical_description`` and other person fields.

        Returns:
            The upserted document.
        """
        name = data["name"]
        now = datetime.now(timezone.utc)

        set_on_insert: Dict[str, Any] = {"created_at": now}
        set_fields: Dict[str, Any] = {"updated_at": now}

        # Copy all provided fields except name and timestamps
        for key, value in data.items():
            if key in ("name", "created_at", "updated_at", "_id"):
                continue
            set_fields[key] = value

        import re
        escaped = re.escape(name.strip())
        result = await self._db.db.persons.update_one(
            {"name": {"$regex": f"^{escaped}$", "$options": "i"}},
            {
                "$set": {**set_fields, "name": name},
                "$setOnInsert": set_on_insert,
            },
            upsert=True,
        )

        # Fetch and return the document
        doc = await self._db.db.persons.find_one(
            {"name": {"$regex": f"^{escaped}$", "$options": "i"}}
        )

        if result.upserted_id:
            logger.info("Upserted new person record: %s (%s)", name, result.upserted_id)
        else:
            logger.info("Updated existing person record: %s", name)

        return doc

    async def upsert_vehicle(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert a vehicle record, matching on plate (case-insensitive).

        Args:
            data: Dict with at least ``plate``.  May also contain
                ``make``, ``model``, ``color``, ``registered_owner``, ``flags``.

        Returns:
            The upserted document.
        """
        plate = data["plate"]
        now = datetime.now(timezone.utc)

        set_on_insert: Dict[str, Any] = {"created_at": now}
        set_fields: Dict[str, Any] = {"updated_at": now}

        for key, value in data.items():
            if key in ("plate", "created_at", "updated_at", "_id"):
                continue
            set_fields[key] = value

        import re
        escaped = re.escape(plate.strip())
        result = await self._db.db.vehicles.update_one(
            {"plate": {"$regex": f"^{escaped}$", "$options": "i"}},
            {
                "$set": {**set_fields, "plate": plate},
                "$setOnInsert": set_on_insert,
            },
            upsert=True,
        )

        doc = await self._db.db.vehicles.find_one(
            {"plate": {"$regex": f"^{escaped}$", "$options": "i"}}
        )

        if result.upserted_id:
            logger.info("Upserted new vehicle record: %s (%s)", plate, result.upserted_id)
        else:
            logger.info("Updated existing vehicle record: %s", plate)

        return doc
