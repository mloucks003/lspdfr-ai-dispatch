"""CallManager — creates CAD calls from 911 events and manages call lifecycle.

Requirements: 5.1, 5.3, 8.3
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.models.enums import CallStatus
from backend.services import DatabaseService
from backend.ws.hub import WebSocketHub

logger = logging.getLogger(__name__)

# Map crime types to priority levels (1=high, 2=medium, 3=low)
CRIME_PRIORITY_MAP: Dict[str, int] = {
    "robbery": 1,
    "shooting": 1,
    "assault": 1,
    "homicide": 1,
    "officer_down": 1,
    "pursuit": 1,
    "domestic_disturbance": 2,
    "burglary": 2,
    "theft": 2,
    "suspicious_person": 2,
    "disturbance": 2,
    "traffic_stop": 3,
    "noise_complaint": 3,
    "trespassing": 3,
    "parking_violation": 3,
}

DEFAULT_PRIORITY = 2


class CallManager:
    """Creates and manages CAD calls from 911 events.

    Accepts DatabaseService and WebSocketHub as dependencies.
    """

    def __init__(self, db: DatabaseService, hub: WebSocketHub) -> None:
        self._db = db
        self._hub = hub

    async def _next_call_number(self) -> str:
        """Auto-increment call number using a MongoDB counter document."""
        result = await self._db.db.counters.find_one_and_update(
            {"_id": "call_number"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=True,
        )
        seq = result["seq"]
        year = datetime.now(timezone.utc).year
        return f"{year}-{seq:04d}"

    def _map_priority(self, crime_type: str) -> int:
        """Map a crime type string to a priority level (1-3)."""
        return CRIME_PRIORITY_MAP.get(crime_type.lower(), DEFAULT_PRIORITY)

    async def create_call_from_911(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a 911 call event into a CAD call, persist it, and broadcast.

        Expected event shape::

            {
                "crime_type": str,
                "location": {"street": str, "landmark": str|None, "x": float, "y": float, "z": float},
                "involved_peds": [{"name": str, "description": str}, ...],
                "caller_description": str,
            }

        Returns the created CAD call document.
        """
        crime_type = event.get("crime_type", "unknown")
        location_data = event.get("location", {})
        involved_peds = event.get("involved_peds", [])

        # Build suspect description from involved peds
        suspect_desc = "; ".join(
            p.get("description", p.get("name", ""))
            for p in involved_peds
            if p.get("description") or p.get("name")
        ) or None

        # Build location sub-document
        coordinates = None
        if any(k in location_data for k in ("x", "y", "z")):
            coordinates = {
                "x": location_data.get("x", 0.0),
                "y": location_data.get("y", 0.0),
                "z": location_data.get("z", 0.0),
            }

        location = {
            "street": location_data.get("street", "Unknown"),
            "landmark": location_data.get("landmark"),
            "coordinates": coordinates,
        }

        call_number = await self._next_call_number()
        now = datetime.now(timezone.utc)

        call_doc = {
            "call_number": call_number,
            "type": crime_type,
            "priority": self._map_priority(crime_type),
            "location": location,
            "description": event.get("caller_description", f"911 report: {crime_type}"),
            "suspect_description": suspect_desc,
            "assigned_units": [],
            "status": CallStatus.PENDING.value,
            "notes": [],
            "disposition": None,
            "created_at": now,
            "updated_at": now,
        }

        doc_id = await self._db.audited_insert("calls", call_doc)
        call_doc["_id"] = doc_id

        # Broadcast to radio and CAD (Req 5.3)
        await self._broadcast_call_update(call_doc)

        logger.info("Created CAD call %s (priority %d) from 911 event", call_number, call_doc["priority"])
        return call_doc

    async def _broadcast_call_update(self, call_doc: Dict[str, Any]) -> None:
        """Broadcast a call_update message to radio and CAD."""
        # Serialise ObjectId for JSON
        serialised = {**call_doc}
        if "_id" in serialised:
            serialised["_id"] = str(serialised["_id"])
        if "created_at" in serialised and isinstance(serialised["created_at"], datetime):
            serialised["created_at"] = serialised["created_at"].isoformat()
        if "updated_at" in serialised and isinstance(serialised["updated_at"], datetime):
            serialised["updated_at"] = serialised["updated_at"].isoformat()

        msg = {"type": "call_update", "call": serialised}
        await self._hub.send_to("radio", msg)
        await self._hub.send_to("cad", msg)
