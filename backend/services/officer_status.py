"""Officer status tracking service.

Handles status updates (10-codes), call assignment, and backup requests.

Requirements: 4.1, 4.3, 5.6, 6.1
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.models.enums import CallStatus
from backend.services import DatabaseService
from backend.ws.hub import WebSocketHub

logger = logging.getLogger(__name__)

# Valid 10-codes for officer status
VALID_STATUS_CODES = {"10-76", "10-97", "10-98", "10-8", "10-7"}

# Human-readable labels (for logging / broadcast)
STATUS_LABELS = {
    "10-76": "en route",
    "10-97": "on scene",
    "10-98": "clear",
    "10-8": "in service",
    "10-7": "out of service",
}


class OfficerStatusService:
    """Tracks officer status in MongoDB and broadcasts changes via WebSocket."""

    def __init__(self, db: DatabaseService, hub: WebSocketHub) -> None:
        self._db = db
        self._hub = hub

    async def update_status(self, callsign: str, status_code: str) -> Dict[str, Any]:
        """Update an officer's status and broadcast the change.

        Args:
            callsign: The officer's unit callsign (e.g. "1-Adam-12").
            status_code: A valid 10-code string.

        Returns:
            The updated unit document.

        Raises:
            ValueError: If *status_code* is not in VALID_STATUS_CODES.
        """
        if status_code not in VALID_STATUS_CODES:
            raise ValueError(f"Invalid status code: {status_code!r}. Must be one of {VALID_STATUS_CODES}")

        now = datetime.now(timezone.utc)

        # Upsert the unit record in the units collection
        await self._db.db.units.update_one(
            {"callsign": callsign},
            {
                "$set": {
                    "callsign": callsign,
                    "status": status_code,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

        unit_doc = await self._db.db.units.find_one({"callsign": callsign})

        # Broadcast status change to CAD (Req 4.3)
        await self._hub.send_to("cad", {
            "type": "status_update",
            "unit": callsign,
            "status": status_code,
        })

        logger.info("Officer %s status updated to %s (%s)", callsign, status_code, STATUS_LABELS.get(status_code, ""))
        return unit_doc

    async def get_status(self, callsign: str) -> Optional[Dict[str, Any]]:
        """Return the current unit document for *callsign*, or None."""
        return await self._db.db.units.find_one({"callsign": callsign})

    async def assign_call(self, call_id: Any, callsign: str) -> Dict[str, Any]:
        """Assign an officer to a call.

        - Adds callsign to the call's ``assigned_units``
        - Sets the call status to ``dispatched``
        - Sets the officer status to ``10-76`` (en route)
        - Broadcasts updates

        Returns:
            The updated call document.

        Raises:
            ValueError: If the call is not found.
        """
        # Accept string IDs directly (SQLite mode uses string IDs)
        if isinstance(call_id, str):
            pass  # already a string, which works for both backends

        now = datetime.now(timezone.utc)

        # Update the call
        result = await self._db.audited_update(
            "calls",
            {"_id": call_id},
            {
                "$addToSet": {"assigned_units": callsign},
                "$set": {
                    "status": CallStatus.DISPATCHED.value,
                    "updated_at": now,
                },
            },
        )
        if result is None:
            raise ValueError(f"Call {call_id} not found")

        # Set officer status to 10-76 (en route)
        await self.update_status(callsign, "10-76")

        # Fetch and broadcast updated call
        call_doc = await self._db.db.calls.find_one({"_id": call_id})

        # Broadcast call update to CAD
        serialised = _serialise_call(call_doc)
        await self._hub.send_to("cad", {"type": "call_update", "call": serialised})

        logger.info("Assigned %s to call %s", callsign, call_id)
        return call_doc

    async def request_backup(self, location: Dict[str, Any], details: str = "Backup requested") -> Dict[str, Any]:
        """Create a high-priority backup call at the given location.

        Args:
            location: Location dict with street, landmark, coordinates.
            details: Description text for the call.

        Returns:
            The created CAD call document.
        """
        now = datetime.now(timezone.utc)

        # Ensure location has required structure
        loc = {
            "street": location.get("street", "Unknown"),
            "landmark": location.get("landmark"),
            "coordinates": location.get("coordinates"),
        }

        # Auto-increment call number via counters collection
        result = await self._db.db.counters.find_one_and_update(
            {"_id": "call_number"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=True,
        )
        seq = result["seq"]
        year = now.year
        call_number = f"{year}-{seq:04d}"

        call_doc = {
            "call_number": call_number,
            "type": "backup_request",
            "priority": 1,  # Always high priority (Req 6.1)
            "location": loc,
            "description": details,
            "suspect_description": None,
            "assigned_units": [],
            "status": CallStatus.PENDING.value,
            "notes": [],
            "disposition": None,
            "created_at": now,
            "updated_at": now,
        }

        doc_id = await self._db.audited_insert("calls", call_doc)
        call_doc["_id"] = doc_id

        # Broadcast to all connected units (Req 6.1)
        serialised = _serialise_call(call_doc)
        await self._hub.broadcast({"type": "call_update", "call": serialised})

        logger.info("Backup request created: call %s", call_number)
        return call_doc


def _serialise_call(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Serialise a call document for JSON broadcast."""
    out = {**doc}
    if "_id" in out:
        out["_id"] = str(out["_id"])
    for key in ("created_at", "updated_at"):
        if key in out and isinstance(out[key], datetime):
            out[key] = out[key].isoformat()
    return out
