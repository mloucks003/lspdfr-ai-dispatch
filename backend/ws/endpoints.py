"""WebSocket endpoint handlers for /ws/radio, /ws/plugin, /ws/cad.

Each endpoint authenticates via API key query parameter, then registers
with the WebSocketHub for the duration of the connection.  Incoming
messages are parsed and routed to the appropriate backend services.

Requirements: 7.4, 11.6, 5.2, 5.3, 8.2, 8.3, 1.3, 2.1, 15.3, 15.4,
              15.5, 4.1, 4.2, 4.3, 5.6, 13.1, 13.5
"""

import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


# ---------------------------------------------------------------------------
# Lazy imports to avoid circular dependency with backend.main
# ---------------------------------------------------------------------------

def _get_hub():
    from backend.main import ws_hub
    return ws_hub


def _get_game_state_service():
    from backend.main import game_state_service
    return game_state_service


def _get_call_manager():
    from backend.main import call_manager
    return call_manager


def _get_openai_client():
    from backend.main import openai_client
    return openai_client


# ---------------------------------------------------------------------------
# Plugin message handler (Tasks 16.1, 16.2)
# ---------------------------------------------------------------------------

async def _handle_plugin_message(raw: str) -> None:
    """Parse and route a message from the LSPDFR plugin.

    Supported message types:
    - ``game_state`` → upsert peds/vehicles via GameStateService
    - ``911_call``   → create CAD call via CallManager
    """
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Plugin sent non-JSON message: %s", raw[:120])
        return

    msg_type = msg.get("type")
    data = msg.get("data", {})

    if msg_type == "game_state":
        gs = _get_game_state_service()
        # Upsert each nearby ped (Req 11.6)
        for ped in data.get("nearby_peds", []):
            if ped.get("name"):
                await gs.upsert_person(ped)
        # Upsert each nearby vehicle (Req 11.6)
        for vehicle in data.get("nearby_vehicles", []):
            if vehicle.get("plate"):
                await gs.upsert_vehicle(vehicle)
        logger.debug("Processed game_state update")

    elif msg_type == "911_call":
        cm = _get_call_manager()
        await cm.create_call_from_911(data)
        logger.info("Processed 911_call event")

    else:
        logger.debug("Unhandled plugin message type: %s", msg_type)


# ---------------------------------------------------------------------------
# Radio message handler (Tasks 16.3, 16.4)
# ---------------------------------------------------------------------------

async def _handle_radio_message(raw: str) -> None:
    """Parse and route a message from the dispatch radio.

    Supported message types:
    - ``audio_chunk``    → forward audio to OpenAI Realtime API
    - ``status_update``  → log the radio state change
    """
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Radio sent non-JSON message: %s", raw[:120])
        return

    msg_type = msg.get("type")

    if msg_type == "audio_chunk":
        oai = _get_openai_client()
        audio_data = msg.get("data", "")
        if audio_data:
            await oai.send_audio(audio_data)

    elif msg_type == "status_update":
        radio_status = msg.get("status", "unknown")
        logger.info("Radio status update: %s", radio_status)

    else:
        logger.debug("Unhandled radio message type: %s", msg_type)


# ---------------------------------------------------------------------------
# Shared authenticated handler
# ---------------------------------------------------------------------------

async def _authenticated_ws_handler(
    websocket: WebSocket,
    client_type: str,
    api_key: str,
    message_handler=None,
) -> None:
    """Authenticate, register, listen for messages, and clean up."""
    # Validate API key before accepting (Req 13.5)
    if api_key != settings.api_key:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid API key")
        logger.warning("Rejected %s WebSocket connection: invalid API key", client_type)
        return

    await websocket.accept()
    hub = _get_hub()
    await hub.connect(websocket, client_type)

    try:
        while True:
            data = await websocket.receive_text()
            logger.debug("Received from %s: %s", client_type, data[:120])
            if message_handler is not None:
                try:
                    await message_handler(data)
                except Exception:
                    logger.exception("Error handling %s message", client_type)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(websocket, client_type)


# ---------------------------------------------------------------------------
# Endpoint definitions
# ---------------------------------------------------------------------------

@router.websocket("/ws/radio")
async def ws_radio(websocket: WebSocket, api_key: str = Query(...)):
    """Dispatch Radio WebSocket endpoint."""
    await _authenticated_ws_handler(websocket, "radio", api_key, _handle_radio_message)


@router.websocket("/ws/plugin")
async def ws_plugin(websocket: WebSocket, api_key: str = Query(...)):
    """LSPDFR Plugin WebSocket endpoint."""
    await _authenticated_ws_handler(websocket, "plugin", api_key, _handle_plugin_message)


@router.websocket("/ws/cad")
async def ws_cad(websocket: WebSocket, api_key: str = Query(...)):
    """CAD System WebSocket endpoint."""
    await _authenticated_ws_handler(websocket, "cad", api_key)
