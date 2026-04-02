"""WebSocket client for radio ↔ backend communication."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Default reconnection interval in seconds.
RECONNECT_INTERVAL = 10.0


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------

def make_audio_chunk_message(pcm_data: bytes) -> str:
    """Build a JSON message for an audio chunk."""
    return json.dumps({
        "type": "audio_chunk",
        "data": base64.b64encode(pcm_data).decode("ascii"),
    })


def make_status_update_message(status: str) -> str:
    """Build a JSON message for a status update ('listening' or 'active')."""
    return json.dumps({
        "type": "status_update",
        "status": status,
    })


def parse_server_message(raw: str) -> dict[str, Any]:
    """Parse a JSON message received from the backend."""
    return json.loads(raw)


# ---------------------------------------------------------------------------
# RadioWebSocketClient
# ---------------------------------------------------------------------------

class RadioWebSocketClient:
    """Manages the WebSocket connection to the backend ``/ws/radio`` endpoint.

    Parameters
    ----------
    backend_url:
        Full WebSocket URL, e.g. ``ws://localhost:8000/ws/radio``.
    api_key:
        Shared API key appended as ``?api_key=<key>`` query parameter.
    on_audio_response:
        Callback receiving decoded PCM bytes from an ``audio_response`` msg.
    on_call_announcement:
        Callback receiving the call dict from a ``call_announcement`` msg.
    on_status_ack:
        Callback receiving the full message dict from a ``status_ack`` msg.
    reconnect_interval:
        Seconds between reconnection attempts (default 10).
    """

    def __init__(
        self,
        backend_url: str = "ws://localhost:8000/ws/radio",
        api_key: str = "",
        on_audio_response: Callable[[bytes], None] | None = None,
        on_call_announcement: Callable[[dict], None] | None = None,
        on_status_ack: Callable[[dict], None] | None = None,
        reconnect_interval: float = RECONNECT_INTERVAL,
    ) -> None:
        self._backend_url = backend_url
        self._api_key = api_key
        self._on_audio_response = on_audio_response
        self._on_call_announcement = on_call_announcement
        self._on_status_ack = on_status_ack
        self._reconnect_interval = reconnect_interval

        self._ws: Any = None  # websockets connection object
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._connected = False

    # -- properties ---------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def url(self) -> str:
        sep = "&" if "?" in self._backend_url else "?"
        return f"{self._backend_url}{sep}api_key={self._api_key}"

    # -- public API ---------------------------------------------------------

    def start(self) -> None:
        """Start the WebSocket client in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the client to disconnect and stop."""
        self._running = False
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def send_audio_chunk(self, pcm_data: bytes) -> None:
        """Queue an audio chunk to be sent to the backend."""
        self._schedule_send(make_audio_chunk_message(pcm_data))

    def send_status_update(self, status: str) -> None:
        """Queue a status update message ('listening' or 'active')."""
        self._schedule_send(make_status_update_message(status))

    # -- internals ----------------------------------------------------------

    def _schedule_send(self, message: str) -> None:
        if self._loop is not None and self._ws is not None:
            asyncio.run_coroutine_threadsafe(self._send(message), self._loop)

    async def _send(self, message: str) -> None:
        try:
            if self._ws is not None:
                await self._ws.send(message)
        except Exception:
            logger.warning("Failed to send message; connection may be lost.")
            self._connected = False

    def _run_loop(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_loop())

    async def _connect_loop(self) -> None:
        import websockets

        while self._running:
            try:
                async with websockets.connect(self.url) as ws:
                    self._ws = ws
                    self._connected = True
                    logger.info("Connected to backend at %s", self._backend_url)
                    await self._receive_loop(ws)
            except Exception as exc:
                logger.warning("WebSocket error: %s – reconnecting in %ss", exc, self._reconnect_interval)
                self._connected = False
                self._ws = None
                if self._running:
                    await asyncio.sleep(self._reconnect_interval)

    async def _receive_loop(self, ws: Any) -> None:
        try:
            async for raw_message in ws:
                self._handle_message(raw_message)
        except Exception:
            logger.warning("Connection lost during receive.")
        finally:
            self._connected = False
            self._ws = None

    def _handle_message(self, raw: str) -> None:
        try:
            msg = parse_server_message(raw)
        except json.JSONDecodeError:
            logger.warning("Received non-JSON message from backend.")
            return

        msg_type = msg.get("type")

        if msg_type == "audio_response":
            if self._on_audio_response is not None:
                pcm = base64.b64decode(msg.get("data", ""))
                self._on_audio_response(pcm)

        elif msg_type == "call_announcement":
            if self._on_call_announcement is not None:
                self._on_call_announcement(msg.get("call", {}))

        elif msg_type == "status_ack":
            if self._on_status_ack is not None:
                self._on_status_ack(msg)

        else:
            logger.debug("Unknown message type: %s", msg_type)
