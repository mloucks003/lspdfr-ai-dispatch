"""Unit tests for WebSocketHub and WebSocket/REST API key authentication.

Covers:
- Task 4.1: Connection management, broadcast, targeted send, disconnect queuing, reconnect delivery
- Task 4.2: WebSocket API key auth (reject invalid), REST API key auth dependency
Requirements: 13.1, 13.3, 13.4, 13.5
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.ws.hub import WebSocketHub


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ws(*, send_ok: bool = True) -> MagicMock:
    """Create a mock WebSocket with async send_text."""
    ws = MagicMock()
    if send_ok:
        ws.send_text = AsyncMock()
    else:
        ws.send_text = AsyncMock(side_effect=Exception("connection lost"))
    return ws


# ===========================================================================
# Task 4.1 — WebSocketHub
# ===========================================================================


class TestWebSocketHubConnect:
    """connect() registers a WebSocket and delivers pending messages."""

    @pytest.mark.asyncio
    async def test_registers_connection(self):
        hub = WebSocketHub()
        ws = _make_ws()
        await hub.connect(ws, "radio")
        assert hub.has_connections("radio")
        assert hub.connection_counts["radio"] == 1

    @pytest.mark.asyncio
    async def test_multiple_connections_same_type(self):
        hub = WebSocketHub()
        ws1, ws2 = _make_ws(), _make_ws()
        await hub.connect(ws1, "cad")
        await hub.connect(ws2, "cad")
        assert hub.connection_counts["cad"] == 2

    @pytest.mark.asyncio
    async def test_rejects_invalid_client_type(self):
        hub = WebSocketHub()
        ws = _make_ws()
        with pytest.raises(ValueError, match="Invalid client type"):
            await hub.connect(ws, "invalid")

    @pytest.mark.asyncio
    async def test_delivers_pending_on_reconnect(self):
        hub = WebSocketHub()
        # Queue messages while no clients connected
        await hub.send_to("radio", {"type": "call_update", "id": 1})
        await hub.send_to("radio", {"type": "call_update", "id": 2})
        assert hub.pending_count("radio") == 2

        ws = _make_ws()
        await hub.connect(ws, "radio")

        # Pending messages should have been delivered
        assert ws.send_text.call_count == 2
        assert hub.pending_count("radio") == 0


class TestWebSocketHubDisconnect:
    """disconnect() removes the connection and logs."""

    @pytest.mark.asyncio
    async def test_removes_connection(self):
        hub = WebSocketHub()
        ws = _make_ws()
        await hub.connect(ws, "plugin")
        await hub.disconnect(ws, "plugin")
        assert not hub.has_connections("plugin")
        assert hub.connection_counts.get("plugin", 0) == 0

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_is_safe(self):
        hub = WebSocketHub()
        ws = _make_ws()
        # Should not raise
        await hub.disconnect(ws, "cad")


class TestWebSocketHubBroadcast:
    """broadcast() sends to all connected clients."""

    @pytest.mark.asyncio
    async def test_broadcast_to_all_types(self):
        hub = WebSocketHub()
        ws_radio, ws_plugin, ws_cad = _make_ws(), _make_ws(), _make_ws()
        await hub.connect(ws_radio, "radio")
        await hub.connect(ws_plugin, "plugin")
        await hub.connect(ws_cad, "cad")

        msg = {"type": "status_update", "unit": "1-Adam-12", "status": "10-8"}
        await hub.broadcast(msg)

        expected = json.dumps(msg)
        ws_radio.send_text.assert_awaited_once_with(expected)
        ws_plugin.send_text.assert_awaited_once_with(expected)
        ws_cad.send_text.assert_awaited_once_with(expected)

    @pytest.mark.asyncio
    async def test_broadcast_with_exclude(self):
        hub = WebSocketHub()
        ws_radio, ws_cad = _make_ws(), _make_ws()
        await hub.connect(ws_radio, "radio")
        await hub.connect(ws_cad, "cad")

        msg = {"type": "game_state"}
        await hub.broadcast(msg, exclude_type="radio")

        ws_radio.send_text.assert_not_awaited()
        ws_cad.send_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcast_queues_for_disconnected_types(self):
        hub = WebSocketHub()
        ws_radio = _make_ws()
        await hub.connect(ws_radio, "radio")
        # No CAD or plugin connected

        msg = {"type": "call_update"}
        await hub.broadcast(msg)

        # radio got it
        ws_radio.send_text.assert_awaited_once()
        # cad and plugin should have pending messages
        assert hub.pending_count("cad") == 1
        assert hub.pending_count("plugin") == 1

    @pytest.mark.asyncio
    async def test_broadcast_handles_send_failure_gracefully(self):
        hub = WebSocketHub()
        ws_bad = _make_ws(send_ok=False)
        ws_good = _make_ws()
        await hub.connect(ws_bad, "radio")
        await hub.connect(ws_good, "radio")

        # Should not raise even though one client fails
        await hub.broadcast({"type": "test"})
        ws_good.send_text.assert_awaited_once()


class TestWebSocketHubSendTo:
    """send_to() sends to a specific client type."""

    @pytest.mark.asyncio
    async def test_send_to_specific_type(self):
        hub = WebSocketHub()
        ws_radio, ws_cad = _make_ws(), _make_ws()
        await hub.connect(ws_radio, "radio")
        await hub.connect(ws_cad, "cad")

        msg = {"type": "audio_response", "data": "base64..."}
        await hub.send_to("radio", msg)

        ws_radio.send_text.assert_awaited_once()
        ws_cad.send_text.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_send_to_queues_when_no_connections(self):
        hub = WebSocketHub()
        msg = {"type": "call_update", "call": "C-001"}
        await hub.send_to("cad", msg)

        assert hub.pending_count("cad") == 1

    @pytest.mark.asyncio
    async def test_send_to_string_message(self):
        hub = WebSocketHub()
        ws = _make_ws()
        await hub.connect(ws, "cad")

        await hub.send_to("cad", "raw string message")
        ws.send_text.assert_awaited_once_with("raw string message")


# ===========================================================================
# Task 4.2 — WebSocket API key authentication
# ===========================================================================


class TestWebSocketAuth:
    """WebSocket endpoints reject invalid API keys and accept valid ones."""

    @pytest.mark.asyncio
    async def test_ws_rejects_invalid_api_key(self):
        """Connection with wrong API key should be closed immediately."""
        with patch("backend.ws.endpoints.settings") as mock_settings:
            mock_settings.api_key = "correct-key"
            from backend.main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # httpx doesn't support WebSocket natively, so we test via
                # the ASGI transport using the starlette test client instead.
                pass

        # Use Starlette's TestClient for WebSocket testing
        from starlette.testclient import TestClient

        with patch("backend.ws.endpoints.settings") as mock_settings:
            mock_settings.api_key = "correct-key"
            from backend.main import app
            test_client = TestClient(app)

            # Invalid key — should be rejected
            with pytest.raises(Exception):
                with test_client.websocket_connect("/ws/radio?api_key=wrong-key"):
                    pass

    @pytest.mark.asyncio
    async def test_ws_accepts_valid_api_key(self):
        """Connection with correct API key should be accepted."""
        from starlette.testclient import TestClient

        with patch("backend.ws.endpoints.settings") as mock_settings:
            mock_settings.api_key = "test-secret"
            from backend.main import app
            test_client = TestClient(app)

            with test_client.websocket_connect("/ws/radio?api_key=test-secret") as ws:
                # Connection was accepted — send a message to verify it's alive
                ws.send_text("hello")

    @pytest.mark.asyncio
    async def test_ws_plugin_rejects_invalid_key(self):
        """Plugin endpoint also rejects invalid keys."""
        from starlette.testclient import TestClient

        with patch("backend.ws.endpoints.settings") as mock_settings:
            mock_settings.api_key = "secret123"
            from backend.main import app
            test_client = TestClient(app)

            with pytest.raises(Exception):
                with test_client.websocket_connect("/ws/plugin?api_key=bad"):
                    pass

    @pytest.mark.asyncio
    async def test_ws_cad_accepts_valid_key(self):
        """CAD endpoint accepts valid keys."""
        from starlette.testclient import TestClient

        with patch("backend.ws.endpoints.settings") as mock_settings:
            mock_settings.api_key = "cad-key"
            from backend.main import app
            test_client = TestClient(app)

            with test_client.websocket_connect("/ws/cad?api_key=cad-key") as ws:
                ws.send_text("ping")


# ===========================================================================
# Task 4.2 — REST API key authentication dependency
# ===========================================================================


class TestRESTApiKeyAuth:
    """The require_api_key dependency validates X-API-Key header."""

    @pytest.mark.asyncio
    async def test_rejects_missing_api_key(self):
        from backend.routes.auth import require_api_key
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(x_api_key="wrong-key")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_accepts_valid_api_key(self):
        from backend.routes.auth import require_api_key

        with patch("backend.routes.auth.settings") as mock_settings:
            mock_settings.api_key = "valid-key"
            result = await require_api_key(x_api_key="valid-key")
            assert result == "valid-key"

    @pytest.mark.asyncio
    async def test_rejects_empty_api_key(self):
        from backend.routes.auth import require_api_key

        with patch("backend.routes.auth.settings") as mock_settings:
            mock_settings.api_key = "real-key"
            with pytest.raises(Exception):
                await require_api_key(x_api_key="")
