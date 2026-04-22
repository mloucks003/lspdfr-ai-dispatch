"""
world_state.py — Shared live picture of every unit on the channel.

Single source of truth for all agents (dispatch + officers + player).
Thread-safe, in-process singleton for solo play.

FiveM path: wrap `world_state` in a FastAPI WebSocket endpoint.
The data model here does NOT change — only the transport layer is added.
"""

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class UnitStatus(str, Enum):
    AVAILABLE = "10-8"    # Available for calls
    ON_CALL   = "10-6"    # Busy / occupied
    ENROUTE   = "10-76"   # En route to a call
    ON_SCENE  = "10-23"   # On scene
    TRAFFIC   = "10-38"   # Traffic stop
    OUT       = "10-7"    # Out of service


@dataclass
class Unit:
    callsign:  str
    name:      str
    status:    UnitStatus   = UnitStatus.AVAILABLE
    location:  str          = "Patrol"
    incident:  Optional[str] = None
    is_player: bool          = False

    def brief(self) -> str:
        """
        One-line status line injected into GPT prompts.
        Example: "King-3 (Torres) — 10-38 at Burton Blvd, handling: traffic stop on blue Honda"
        """
        inc    = f", handling: {self.incident}" if self.incident else ""
        marker = " ← (you)" if self.is_player else ""
        return f"{self.callsign} ({self.name}){marker} — {self.status.value} at {self.location}{inc}"


class WorldState:
    """
    Thread-safe live unit roster.

    Injected into every GPT system prompt so each agent always knows
    what every other unit is doing.  Eliminates the "context-free chatbot"
    problem — King-3 knows Sam-41 is on a stop, dispatch knows who's free.

    Usage:
        from core.world_state import world_state
        world_state.register("King-3", "Torres")
        world_state.update("King-3", status=UnitStatus.TRAFFIC, location="Burton Blvd")
        prompt += world_state.roster_for_prompt()
    """

    def __init__(self):
        self._lock  = threading.RLock()
        self._units: dict[str, Unit] = {}

    def register(self, callsign: str, name: str,
                 location: str = "Patrol", is_player: bool = False):
        """Add a unit to the world.  Call once per session per unit."""
        with self._lock:
            self._units[callsign] = Unit(
                callsign=callsign,
                name=name,
                location=location,
                is_player=is_player,
            )

    def update(self, callsign: str, **kwargs):
        """
        Update any Unit field by name.
        world_state.update("King-3", status=UnitStatus.TRAFFIC, incident="traffic stop")
        """
        with self._lock:
            u = self._units.get(callsign)
            if u:
                for k, v in kwargs.items():
                    setattr(u, k, v)

    def get(self, callsign: str) -> Optional[Unit]:
        with self._lock:
            return self._units.get(callsign)

    def roster_for_prompt(self) -> str:
        """
        Multi-line status block ready to embed in any GPT system prompt.

        Example output:
          King-3 (Torres) — 10-38 at Burton Blvd, handling: traffic stop on blue Honda
          Sam-41 (Reyes)  — 10-8  at Strawberry Ave
          Sam-44 (you)    — 10-8  at Vinewood Hills  ← (you)
        """
        with self._lock:
            if not self._units:
                return "  (no units registered)"
            return "\n".join(f"  {u.brief()}" for u in self._units.values())

    def available_units(self, exclude: str = "") -> list[str]:
        """Return callsigns of units that are 10-8 (available), excluding `exclude`."""
        with self._lock:
            return [
                cs for cs, u in self._units.items()
                if u.status == UnitStatus.AVAILABLE and cs != exclude
            ]


# Module-level singleton — import anywhere:
#   from core.world_state import world_state, UnitStatus
world_state = WorldState()
