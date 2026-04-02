"""WebSocket hub managing connections for radio, plugin, and CAD clients.

Handles connection registration, broadcast, targeted send, disconnect
handling with pending message queuing, and reconnection delivery.

Requirements: 13.1, 13.3, 13.4
"""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Valid client types that the hub accepts.
CLIENT_TYPES = {"radio", "plugin", "cad"}


class WebSocketHub:
    """Manages WebSocket connections for radio, plugin, and CAD clients.

    Features:
    - Register / unregister connections by client type
    - Broadcast messages to all connected clients (with optional exclusion)
    - Send messages to a specific client type
    - Queue pending messages for disconnected client types
    - Deliver queued messages on reconnection
    """

    def __init__(self) -> None:
        # client_type -> set of active WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        # client_type -> list of pending messages (queued while disconnected)
        self._pending: Dict[str, list] = defaultdict(list)
        # Lock to protect connection mutations
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_type: str) -> None:
        """Register a WebSocket connection for the given client type.

        Delivers any pending messages that were queued while the client
        type had no active connections.
        """
        if client_type not in CLIENT_TYPES:
            raise ValueError(f"Invalid client type: {client_type!r}. Must be one of {CLIENT_TYPES}")

        async with self._lock:
            self._connections[client_type].add(websocket)
            logger.info("Client connected: type=%s (total %d)", client_type, len(self._connections[client_type]))

            # Deliver any pending messages queued during disconnection (Req 13.4)
            pending = self._pending.pop(client_type, [])

        for msg in pending:
            try:
                await websocket.send_text(msg if isinstance(msg, str) else json.dumps(msg))
            except Exception:
                logger.warning("Failed to deliver pending message to %s", client_type, exc_info=True)

    async def disconnect(self, websocket: WebSocket, client_type: str) -> None:
        """Unregister a WebSocket connection and log the disconnection."""
        async with self._lock:
            self._connections[client_type].discard(websocket)
            remaining = len(self._connections[client_type])
        logger.info("Client disconnected: type=%s (remaining %d)", client_type, remaining)

    async def broadcast(self, message: Any, exclude_type: Optional[str] = None) -> None:
        """Send a message to all connected clients.

        Args:
            message: The message payload (dict or string).
            exclude_type: Optional client type to exclude from the broadcast.

        Messages are queued for any client type that has no active connections
        so they can be delivered on reconnection (Req 13.4).
        """
        text = message if isinstance(message, str) else json.dumps(message)

        async with self._lock:
            targets = {
                ctype: set(self._connections.get(ctype, set()))
                for ctype in CLIENT_TYPES
                if ctype != exclude_type
            }

        for ctype, sockets in targets.items():
            if not sockets:
                # No active connections for this type — queue the message (Req 13.4)
                async with self._lock:
                    self._pending[ctype].append(text)
                continue
            for ws in sockets:
                try:
                    await ws.send_text(text)
                except Exception:
                    logger.warning("Failed to send broadcast to %s client", ctype, exc_info=True)

    async def send_to(self, client_type: str, message: Any) -> None:
        """Send a message to all connections of a specific client type.

        If no connections exist for the type, the message is queued for
        delivery on reconnection.
        """
        text = message if isinstance(message, str) else json.dumps(message)

        async with self._lock:
            sockets = set(self._connections.get(client_type, set()))

        if not sockets:
            async with self._lock:
                self._pending[client_type].append(text)
            logger.debug("No %s clients connected — message queued", client_type)
            return

        for ws in sockets:
            try:
                await ws.send_text(text)
            except Exception:
                logger.warning("Failed to send to %s client", client_type, exc_info=True)

    @property
    def connection_counts(self) -> Dict[str, int]:
        """Return a snapshot of connection counts by client type."""
        return {ctype: len(sockets) for ctype, sockets in self._connections.items()}

    def has_connections(self, client_type: str) -> bool:
        """Check whether any connections exist for the given client type."""
        return bool(self._connections.get(client_type))

    def pending_count(self, client_type: str) -> int:
        """Return the number of pending messages for a client type."""
        return len(self._pending.get(client_type, []))
