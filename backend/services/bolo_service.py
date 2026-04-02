"""BOLO (Be On the Lookout) service.

Creates BOLO records, persists them in MongoDB, and broadcasts alerts.

Requirements: 6.2
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.models.enums import BOLOStatus
from backend.services.database import DatabaseService
from backend.ws.hub import WebSocketHub

logger = logging.getLogger(__name__)


class BOLOService:
    """Manages BOLO creation and broadcast."""

    def __init__(self, db: DatabaseService, hub: WebSocketHub) -> None:
        self._db = db
        self._hub = hub

    async def create_bolo(
        self,
        description: str,
        issuing_officer: str,
        suspect_description: Optional[str] = None,
        vehicle_description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a BOLO record, persist it, and broadcast to CAD.

        Returns:
            The created BOLO document.
        """
        now = datetime.now(timezone.utc)

        bolo_doc = {
            "description": description,
            "suspect_description": suspect_description,
            "vehicle_description": vehicle_description,
            "issuing_officer": issuing_officer,
            "status": BOLOStatus.ACTIVE.value,
            "created_at": now,
            "updated_at": now,
        }

        doc_id = await self._db.audited_insert("bolos", bolo_doc)
        bolo_doc["_id"] = doc_id

        # Broadcast BOLO alert to CAD (Req 6.2)
        serialised = {**bolo_doc}
        serialised["_id"] = str(serialised["_id"])
        for key in ("created_at", "updated_at"):
            if key in serialised and isinstance(serialised[key], datetime):
                serialised[key] = serialised[key].isoformat()

        await self._hub.send_to("cad", {"type": "bolo_alert", "bolo": serialised})

        logger.info("BOLO created: %s (officer: %s)", doc_id, issuing_officer)
        return bolo_doc
