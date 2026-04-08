"""REST API endpoints for the LSPDFR plugin to POST game data.

These replace the WebSocket plugin connection with simple HTTP POST
endpoints that work reliably from RPH's AppDomain.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/plugin", tags=["plugin"])
logger = logging.getLogger(__name__)


class NearbyPed(BaseModel):
    name: str = ""
    description: str = ""
    wanted_level: int = 0

class NearbyVehicle(BaseModel):
    plate: str = ""
    make: str = ""
    model: str = ""
    color: str = ""

class OfficerLocation(BaseModel):
    street: str = "Unknown"
    landmark: Optional[str] = None
    x: float = 0
    y: float = 0
    z: float = 0

class GameStateIn(BaseModel):
    nearby_peds: List[NearbyPed] = []
    nearby_vehicles: List[NearbyVehicle] = []
    officer_location: Optional[OfficerLocation] = None

class CallLocation(BaseModel):
    street: str = "Unknown"
    landmark: Optional[str] = None
    x: float = 0
    y: float = 0
    z: float = 0

class InvolvedPed(BaseModel):
    name: str = ""
    description: str = ""

class NineOneOneCallIn(BaseModel):
    crime_type: str = "unknown"
    location: Optional[CallLocation] = None
    involved_peds: List[InvolvedPed] = []
    caller_description: str = ""


def _get_game_state_service():
    from backend.main import game_state_service
    return game_state_service

def _get_call_manager():
    from backend.main import call_manager
    return call_manager


@router.post("/gamestate")
async def receive_game_state(body: GameStateIn):
    """Receive game state from the LSPDFR plugin via HTTP POST."""
    gs = _get_game_state_service()

    for ped in body.nearby_peds:
        if ped.name:
            await gs.upsert_person({"name": ped.name, "description": ped.description})

    for vehicle in body.nearby_vehicles:
        if vehicle.plate:
            await gs.upsert_vehicle({
                "plate": vehicle.plate,
                "make": vehicle.make,
                "model": vehicle.model,
                "color": vehicle.color,
            })

    logger.debug("Game state received: %d peds, %d vehicles",
                 len(body.nearby_peds), len(body.nearby_vehicles))
    for v in body.nearby_vehicles:
        if v.plate:
            logger.info("Plugin vehicle: plate=%s make=%s model=%s color=%s",
                        v.plate, v.make, v.model, v.color)
    return {"status": "ok"}


@router.post("/911call")
async def receive_911_call(body: NineOneOneCallIn):
    """Receive a 911 call event from the LSPDFR plugin via HTTP POST."""
    cm = _get_call_manager()

    event = {
        "crime_type": body.crime_type,
        "location": {
            "street": body.location.street if body.location else "Unknown",
            "landmark": body.location.landmark if body.location else None,
            "x": body.location.x if body.location else 0,
            "y": body.location.y if body.location else 0,
            "z": body.location.z if body.location else 0,
        },
        "involved_peds": [{"name": p.name, "description": p.description} for p in body.involved_peds],
        "caller_description": body.caller_description,
    }

    call = await cm.create_call_from_911(event)
    logger.info("911 call from plugin: %s at %s", body.crime_type,
                body.location.street if body.location else "Unknown")
    return {"status": "ok", "call_number": call.get("call_number")}
