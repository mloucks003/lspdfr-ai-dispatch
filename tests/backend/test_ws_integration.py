"""Integration tests for WebSocket endpoint wiring (Tasks 16.1–16.4).

Validates that incoming WebSocket messages on /ws/plugin and /ws/radio
are correctly parsed and routed to the appropriate backend services.

- 16.1: game_state → GameStateService upsert
- 16.2: 911_call → CallManager.create_call_from_911 → broadcast
- 16.3: audio_chunk → OpenAIRealtimeClient.send_audio
- 16.4: status/call assignment propagation via existing services
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.ws.endpoints import _handle_plugin_message, _handle_radio_message


# ======================================================================
# Task 16.1 — Plugin game state flow
# ======================================================================


class TestPluginGameStateFlow:
    """game_state messages upsert peds and vehicles via GameStateService."""

    @pytest.mark.asyncio
    async def test_game_state_upserts_peds(self):
        mock_gs = MagicMock()
        mock_gs.upsert_person = AsyncMock()
        mock_gs.upsert_vehicle = AsyncMock()

        msg = json.dumps({
            "type": "game_state",
            "data": {
                "nearby_peds": [
                    {"name": "John Smith", "description": "Male, white shirt"},
                    {"name": "Jane Doe", "description": "Female, red dress"},
                ],
                "nearby_vehicles": [],
                "officer_location": {"street": "Vinewood Blvd", "x": 0, "y": 0, "z": 0},
            },
        })

        with patch("backend.ws.endpoints._get_game_state_service", return_value=mock_gs):
            await _handle_plugin_message(msg)

        assert mock_gs.upsert_person.await_count == 2
        mock_gs.upsert_person.assert_any_await(
            {"name": "John Smith", "description": "Male, white shirt"}
        )
        mock_gs.upsert_person.assert_any_await(
            {"name": "Jane Doe", "description": "Female, red dress"}
        )

    @pytest.mark.asyncio
    async def test_game_state_upserts_vehicles(self):
        mock_gs = MagicMock()
        mock_gs.upsert_person = AsyncMock()
        mock_gs.upsert_vehicle = AsyncMock()

        msg = json.dumps({
            "type": "game_state",
            "data": {
                "nearby_peds": [],
                "nearby_vehicles": [
                    {"plate": "ABC123", "make": "Vapid", "model": "Crown Victoria", "color": "Black"},
                ],
                "officer_location": {"street": "Davis Ave"},
            },
        })

        with patch("backend.ws.endpoints._get_game_state_service", return_value=mock_gs):
            await _handle_plugin_message(msg)

        mock_gs.upsert_vehicle.assert_awaited_once_with(
            {"plate": "ABC123", "make": "Vapid", "model": "Crown Victoria", "color": "Black"}
        )

    @pytest.mark.asyncio
    async def test_game_state_skips_peds_without_name(self):
        mock_gs = MagicMock()
        mock_gs.upsert_person = AsyncMock()
        mock_gs.upsert_vehicle = AsyncMock()

        msg = json.dumps({
            "type": "game_state",
            "data": {
                "nearby_peds": [{"name": "", "description": "Unknown"}],
                "nearby_vehicles": [],
            },
        })

        with patch("backend.ws.endpoints._get_game_state_service", return_value=mock_gs):
            await _handle_plugin_message(msg)

        mock_gs.upsert_person.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_game_state_skips_vehicles_without_plate(self):
        mock_gs = MagicMock()
        mock_gs.upsert_person = AsyncMock()
        mock_gs.upsert_vehicle = AsyncMock()

        msg = json.dumps({
            "type": "game_state",
            "data": {
                "nearby_peds": [],
                "nearby_vehicles": [{"plate": "", "make": "Vapid"}],
            },
        })

        with patch("backend.ws.endpoints._get_game_state_service", return_value=mock_gs):
            await _handle_plugin_message(msg)

        mock_gs.upsert_vehicle.assert_not_awaited()


# ======================================================================
# Task 16.2 — 911 call flow
# ======================================================================


class TestPlugin911CallFlow:
    """911_call messages create CAD calls via CallManager."""

    @pytest.mark.asyncio
    async def test_911_call_creates_cad_call(self):
        mock_cm = MagicMock()
        mock_cm.create_call_from_911 = AsyncMock(return_value={"call_number": "2025-0001"})

        event_data = {
            "crime_type": "robbery",
            "location": {"street": "Strawberry Ave", "x": 100, "y": 200, "z": 0},
            "involved_peds": [{"name": "Suspect", "description": "Male, hoodie"}],
            "caller_description": "Female caller reports robbery in progress",
        }
        msg = json.dumps({"type": "911_call", "data": event_data})

        with patch("backend.ws.endpoints._get_call_manager", return_value=mock_cm):
            await _handle_plugin_message(msg)

        mock_cm.create_call_from_911.assert_awaited_once_with(event_data)

    @pytest.mark.asyncio
    async def test_911_call_with_minimal_data(self):
        mock_cm = MagicMock()
        mock_cm.create_call_from_911 = AsyncMock(return_value={"call_number": "2025-0002"})

        msg = json.dumps({
            "type": "911_call",
            "data": {"crime_type": "traffic_stop"},
        })

        with patch("backend.ws.endpoints._get_call_manager", return_value=mock_cm):
            await _handle_plugin_message(msg)

        mock_cm.create_call_from_911.assert_awaited_once_with({"crime_type": "traffic_stop"})


# ======================================================================
# Task 16.3 — Voice command flow (radio → OpenAI)
# ======================================================================


class TestRadioAudioFlow:
    """audio_chunk messages are forwarded to OpenAIRealtimeClient."""

    @pytest.mark.asyncio
    async def test_audio_chunk_forwarded_to_openai(self):
        mock_oai = MagicMock()
        mock_oai.send_audio = AsyncMock()

        msg = json.dumps({"type": "audio_chunk", "data": "base64encodedaudio=="})

        with patch("backend.ws.endpoints._get_openai_client", return_value=mock_oai):
            await _handle_radio_message(msg)

        mock_oai.send_audio.assert_awaited_once_with("base64encodedaudio==")

    @pytest.mark.asyncio
    async def test_audio_chunk_empty_data_not_forwarded(self):
        mock_oai = MagicMock()
        mock_oai.send_audio = AsyncMock()

        msg = json.dumps({"type": "audio_chunk", "data": ""})

        with patch("backend.ws.endpoints._get_openai_client", return_value=mock_oai):
            await _handle_radio_message(msg)

        mock_oai.send_audio.assert_not_awaited()


# ======================================================================
# Task 16.4 — Status update flow
# ======================================================================


class TestRadioStatusFlow:
    """status_update messages from radio are logged (no crash)."""

    @pytest.mark.asyncio
    async def test_status_update_logged(self):
        msg = json.dumps({"type": "status_update", "status": "listening"})
        # Should not raise
        await _handle_radio_message(msg)

    @pytest.mark.asyncio
    async def test_status_update_active(self):
        msg = json.dumps({"type": "status_update", "status": "active"})
        await _handle_radio_message(msg)


# ======================================================================
# Edge cases
# ======================================================================


class TestEdgeCases:
    """Malformed or unknown messages are handled gracefully."""

    @pytest.mark.asyncio
    async def test_plugin_non_json_message(self):
        await _handle_plugin_message("not json at all")

    @pytest.mark.asyncio
    async def test_radio_non_json_message(self):
        await _handle_radio_message("not json at all")

    @pytest.mark.asyncio
    async def test_plugin_unknown_type(self):
        msg = json.dumps({"type": "unknown_type", "data": {}})
        await _handle_plugin_message(msg)

    @pytest.mark.asyncio
    async def test_radio_unknown_type(self):
        msg = json.dumps({"type": "unknown_type"})
        await _handle_radio_message(msg)

    @pytest.mark.asyncio
    async def test_plugin_missing_data_field(self):
        mock_gs = MagicMock()
        mock_gs.upsert_person = AsyncMock()
        mock_gs.upsert_vehicle = AsyncMock()

        msg = json.dumps({"type": "game_state"})

        with patch("backend.ws.endpoints._get_game_state_service", return_value=mock_gs):
            await _handle_plugin_message(msg)

        # No peds or vehicles to upsert
        mock_gs.upsert_person.assert_not_awaited()
        mock_gs.upsert_vehicle.assert_not_awaited()
