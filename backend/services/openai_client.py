"""OpenAI Realtime API WebSocket client.

Establishes a WebSocket connection to the OpenAI Realtime API, forwards
audio between the dispatch radio and OpenAI, handles function call
invocations, and reconnects with exponential backoff on disconnect.

Requirements: 15.1, 15.3, 15.4, 15.7
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import websockets
from websockets.exceptions import ConnectionClosed, InvalidURI

from backend.services.function_registry import FunctionRegistry
from backend.services.system_prompt import SystemPromptBuilder
from backend.ws.hub import WebSocketHub

logger = logging.getLogger(__name__)

OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"
DEFAULT_MODEL = "gpt-4o-realtime-preview"


def calculate_backoff(consecutive_failures: int) -> float:
    """Return the reconnection delay in seconds: min(2^N, 60).

    Args:
        consecutive_failures: Number of consecutive connection failures (N >= 0).

    Returns:
        Delay in seconds, capped at 60.
    """
    return min(2 ** consecutive_failures, 60)


class OpenAIRealtimeClient:
    """Manages the WebSocket connection to the OpenAI Realtime API.

    Responsibilities:
    - Connect with API key in headers
    - Send audio chunks received from the radio
    - Receive audio responses and forward to radio via WebSocketHub
    - Handle function call invocations from OpenAI
    - Reconnect with exponential backoff on disconnect
    """

    def __init__(
        self,
        api_key: str,
        hub: WebSocketHub,
        function_registry: FunctionRegistry,
        prompt_builder: SystemPromptBuilder,
        callsign: str = "1-Adam-12",
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._api_key = api_key
        self._hub = hub
        self._registry = function_registry
        self._prompt_builder = prompt_builder
        self._callsign = callsign
        self._model = model

        self._ws: Optional[Any] = None
        self._connected = False
        self._consecutive_failures = 0
        self._listen_task: Optional[asyncio.Task] = None
        self._should_run = False

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish the WebSocket connection to OpenAI Realtime API."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        url = f"{OPENAI_REALTIME_URL}?model={self._model}"

        self._ws = await websockets.connect(url, additional_headers=headers)
        self._connected = True
        self._consecutive_failures = 0
        logger.info("Connected to OpenAI Realtime API")

        # Send session configuration with system prompt and tools
        await self._configure_session()

    async def disconnect(self) -> None:
        """Close the WebSocket connection gracefully."""
        self._should_run = False
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._connected = False
        logger.info("Disconnected from OpenAI Realtime API")

    async def start(self) -> None:
        """Connect and start the receive loop with auto-reconnect."""
        self._should_run = True
        while self._should_run:
            try:
                await self.connect()
                await self._receive_loop()
            except (ConnectionClosed, InvalidURI, OSError) as exc:
                self._connected = False
                self._consecutive_failures += 1
                delay = calculate_backoff(self._consecutive_failures)
                logger.warning(
                    "OpenAI connection lost (%s). Reconnecting in %.1fs (attempt %d)",
                    exc,
                    delay,
                    self._consecutive_failures,
                )
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                break
            except Exception:
                self._connected = False
                self._consecutive_failures += 1
                delay = calculate_backoff(self._consecutive_failures)
                logger.exception(
                    "Unexpected error in OpenAI client. Reconnecting in %.1fs",
                    delay,
                )
                await asyncio.sleep(delay)

        await self.disconnect()

    # ------------------------------------------------------------------
    # Audio forwarding
    # ------------------------------------------------------------------

    async def send_audio(self, audio_base64: str) -> None:
        """Forward an audio chunk from the radio to OpenAI.

        Args:
            audio_base64: Base64-encoded PCM audio data.
        """
        if not self._connected or not self._ws:
            logger.warning("Cannot send audio — not connected to OpenAI")
            return

        event = {
            "type": "input_audio_buffer.append",
            "audio": audio_base64,
        }
        await self._ws.send(json.dumps(event))

    # ------------------------------------------------------------------
    # Internal: session configuration
    # ------------------------------------------------------------------

    async def _configure_session(self) -> None:
        """Send session.update with system prompt and tool definitions."""
        system_prompt = self._prompt_builder.build(self._callsign)
        tools = self._registry.get_tool_definitions()

        session_config = {
            "type": "session.update",
            "session": {
                "instructions": system_prompt,
                "tools": tools,
            },
        }
        await self._ws.send(json.dumps(session_config))
        logger.info("Session configured with system prompt and %d tools", len(tools))

    # ------------------------------------------------------------------
    # Internal: receive loop
    # ------------------------------------------------------------------

    async def _receive_loop(self) -> None:
        """Listen for messages from OpenAI and handle them."""
        async for raw_message in self._ws:
            if not self._should_run:
                break
            try:
                message = json.loads(raw_message)
                await self._handle_message(message)
            except json.JSONDecodeError:
                logger.warning("Received non-JSON message from OpenAI")
            except Exception:
                logger.exception("Error handling OpenAI message")

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Route an incoming OpenAI event to the appropriate handler."""
        msg_type = message.get("type", "")

        if msg_type == "response.audio.delta":
            # Forward audio delta to radio
            audio_data = message.get("delta", "")
            if audio_data:
                await self._hub.send_to("radio", {
                    "type": "audio_response",
                    "data": audio_data,
                })

        elif msg_type == "response.function_call_arguments.done":
            await self._handle_function_call(message)

        elif msg_type == "error":
            logger.error("OpenAI error: %s", message.get("error", {}))

        # Other event types are logged at debug level
        else:
            logger.debug("OpenAI event: %s", msg_type)

    async def _handle_function_call(self, message: Dict[str, Any]) -> None:
        """Execute a function call from OpenAI and return the result."""
        call_id = message.get("call_id", "")
        function_name = message.get("name", "")
        raw_args = message.get("arguments", "{}")

        try:
            arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            arguments = {}

        logger.info("Function call from OpenAI: %s(%s)", function_name, arguments)

        try:
            result = await self._registry.dispatch(function_name, arguments)
            # Serialise result for JSON
            result_str = json.dumps(result, default=str)
        except Exception as exc:
            logger.exception("Function call %s failed", function_name)
            result_str = json.dumps({"error": str(exc)})

        # Send function call result back to OpenAI
        response_event = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": result_str,
            },
        }
        await self._ws.send(json.dumps(response_event))

        # Trigger OpenAI to continue generating a response
        await self._ws.send(json.dumps({"type": "response.create"}))
