"""
world_state.py — Shared live picture of every unit on the channel.

Single source of truth for all agents (dispatch + officers + player).
Thread-safe, in-process singleton for solo play.

FiveM path: wrap `world_state` in a FastAPI WebSocket endpoint.
The data model here does NOT change — only the transport layer is added.
"""

import threading
import time
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
class EmotionalState:
    """
    Live emotional snapshot for one officer.
    Feeds into GPT system prompts AND ElevenLabs voice settings so the
    language model and the voice model agree on how the officer feels.

    arousal     — 0.0 = calm/bored → 1.0 = full adrenaline (pursuit, shots)
    frustration — 0.0 = fine       → 1.0 = fed up (long domestic, bad subject)
    fatigue     — accumulates over shift; decays very slowly
    mood        — coarse label consumed by the GPT prompt builder
    """
    arousal:     float = 0.0
    frustration: float = 0.0
    fatigue:     float = 0.0
    mood:        str   = "neutral"
    # Valid moods: neutral, focused, tense, wired, relieved, frustrated, bored, tired


@dataclass
class Unit:
    callsign:  str
    name:      str
    status:    UnitStatus    = UnitStatus.AVAILABLE
    location:  str           = "Patrol"
    incident:  Optional[str] = None
    is_player: bool          = False
    emotion:   EmotionalState = field(default_factory=EmotionalState)

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

    # Emotion trigger → field deltas.  "mood" is set directly; numerics are clamped [0,1].
    _EMOTION_TRIGGERS: dict[str, dict] = {
        "pursuit_start":      {"arousal": +0.90, "mood": "wired"},
        "shots_fired":        {"arousal": +1.00, "mood": "tense"},
        "robbery":            {"arousal": +0.75, "mood": "tense"},
        "backup_requested":   {"arousal": +0.50, "mood": "focused"},
        "domestic_prolonged": {"frustration": +0.40, "mood": "frustrated"},
        "welfare_bad":        {"arousal": +0.35, "mood": "tense"},
        "clear_tense":        {"arousal": -0.60, "mood": "relieved"},
        "clear_routine":      {"arousal": -0.10, "fatigue": +0.05},
        "routine_stop":       {"arousal": -0.05, "mood": "bored"},
        "long_wait":          {"fatigue": +0.10, "mood": "tired"},
    }

    def __init__(self):
        self._lock  = threading.RLock()
        self._units: dict[str, Unit] = {}
        # Arousal decay: every 3 minutes, arousal drops 0.15 naturally
        t = threading.Thread(target=self._decay_loop, daemon=True, name="emotion_decay")
        t.start()

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

    def update_emotion(self, callsign: str, trigger: str):
        """
        Apply an event trigger to one officer's emotional state.
        Numeric fields are clamped to [0.0, 1.0].
        Mood field is set directly.

        Example:
            world_state.update_emotion("King-3", "pursuit_start")
            # → arousal += 0.9, mood = "wired"
        """
        delta = self._EMOTION_TRIGGERS.get(trigger, {})
        if not delta:
            return
        with self._lock:
            u = self._units.get(callsign)
            if not u or u.is_player:
                return
            e = u.emotion
            for k, v in delta.items():
                if k == "mood":
                    e.mood = v
                else:
                    current = getattr(e, k, 0.0)
                    setattr(e, k, max(0.0, min(1.0, current + v)))

    def _decay_loop(self):
        """
        Background thread: adrenaline fades naturally over time.
        Every 3 minutes, arousal drops 0.15 for every officer.
        Fatigue decays very slowly (0.02 per 10 min) — simulates a long shift
        but won't fully reset during a session.
        """
        while True:
            time.sleep(180)   # 3-minute tick
            with self._lock:
                for u in self._units.values():
                    if u.is_player:
                        continue
                    e = u.emotion
                    e.arousal = max(0.0, e.arousal - 0.15)
                    # Fatigue decays once every 10 minutes (every ~3.3 ticks)
                    e.fatigue = max(0.0, e.fatigue - 0.02)
                    # If arousal and frustration both drop low, drift back to neutral
                    if e.arousal < 0.15 and e.frustration < 0.15 and e.mood not in ("bored", "tired", "neutral"):
                        e.mood = "neutral"

    def snapshot(self) -> dict:
        """
        Return a lightweight dict snapshot of the world — safe to read outside the lock.
        Used by radio_officers._build_officer_system_prompt to get the active incident list.
        """
        with self._lock:
            incidents = []
            for cs, u in self._units.items():
                if u.incident and not u.is_player:
                    # incident strings are stored as "<type> at <location>"
                    if " at " in u.incident:
                        inc_type, inc_loc = u.incident.split(" at ", 1)
                    else:
                        inc_type, inc_loc = u.incident, u.location
                    incidents.append({
                        "assigned_to": cs,
                        "type": inc_type,
                        "location": inc_loc,
                    })
            return {"active_incidents": incidents}

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
