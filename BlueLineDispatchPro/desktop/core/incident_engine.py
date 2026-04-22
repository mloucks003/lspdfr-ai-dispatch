"""
incident_engine.py — Background incident generator for BlueLineDispatchPro.

Fires realistic LSPD radio calls to available AI officers every 2-6 minutes,
making the radio feel alive even when the player says nothing.

Every call goes through the dispatch TTS pipeline (_speak) so it sounds
exactly like real scanner traffic.  After voicing the call, it hands off
to OfficerBehaviorLoop to run the full lifecycle (en route → on scene →
plate run → clear).
"""

import logging
import random
import threading
import time
from typing import Callable, Optional

from core.world_state import world_state, UnitStatus

logger = logging.getLogger(__name__)

# ── Data pools ────────────────────────────────────────────────────────────────
_LOCATIONS = [
    "Burton Boulevard", "Strawberry Avenue", "Forum Drive", "Alta Street",
    "Grove Street", "Chamberlain Hills", "Davis Avenue", "Innocence Boulevard",
    "Vinewood Boulevard", "Rockford Hills", "Mirror Park Boulevard",
    "Del Perro Freeway", "Olympic Freeway", "Power Street",
    "Maze Bank Avenue", "Capital Boulevard", "Sinner Street",
]
_VEHICLES = [
    "black Dodge Charger", "silver Honda Civic", "blue Ford F-150",
    "red Chevy Silverado", "white Toyota Camry", "grey BMW 3 Series",
    "dark green Nissan Altima", "maroon GMC Sierra", "gold Cadillac Escalade",
    "tan Honda Accord", "brown Ford Explorer", "orange Dodge Challenger",
]
_PLATES = [
    "4ABC123", "7XYZ891", "2DEF456", "9GHI234",
    "6JKL567", "3MNO890", "8PQR345", "1STU678",
]
_CALL_TYPES   = ["traffic_stop", "disturbance", "suspicious", "traffic_accident",
                 "welfare_check", "burglary", "robbery", "pursuit"]
_CALL_WEIGHTS = [35, 18, 16, 12, 8, 6, 3, 2]
_CALL_CODES   = {
    "traffic_stop": "10-38", "disturbance": "10-16", "suspicious": "10-35",
    "traffic_accident": "10-50", "welfare_check": "10-52", "burglary": "10-30",
    "robbery": "10-11", "pursuit": "10-80",
}
_CALL_PRIORITY = {
    "traffic_stop": "routine", "disturbance": "urgent", "suspicious": "routine",
    "traffic_accident": "urgent", "welfare_check": "routine",
    "burglary": "urgent", "robbery": "emergency", "pursuit": "emergency",
}
_DETAIL_POOL = {
    "disturbance":      ["Caller reports loud argument. No weapons mentioned.",
                         "Neighbor complaint — unknown subjects inside.", ],
    "suspicious":       ["Two males casing vehicles in the parking lot.",
                         "Vehicle parked 4 hours, engine running, occupant not visible.", ],
    "traffic_accident": ["Two-vehicle, unknown injuries. Traffic backing up.",
                         "Single vehicle into barrier — airbags deployed.", ],
    "welfare_check":    ["Subject lying on the sidewalk, not responding.",
                         "Caller reports elderly male walking in traffic.", ],
    "burglary":         ["Alarm activation. Unknown if suspect still on premises.",
                         "Residential — door forced open, occupant returning home.", ],
    "robbery":          ["Armed robbery at a convenience store. Suspect fled north on foot.",
                         "Vehicle carjacking in progress. Suspect armed.", ],
}


def _build_dispatch_call(call_type: str, unit: str) -> tuple[str, dict]:
    """Return (dispatch_text, incident_dict) for this call type and unit."""
    loc   = random.choice(_LOCATIONS)
    veh   = random.choice(_VEHICLES)
    plate = random.choice(_PLATES)
    code  = _CALL_CODES.get(call_type, "10-35")

    incident = {
        "type": call_type, "unit": unit, "location": loc,
        "vehicle": veh, "plate": plate,
        "priority": _CALL_PRIORITY.get(call_type, "routine"),
    }

    if call_type == "traffic_stop":
        text = f"{unit}, {code} on a {veh} at {loc}. Running plate {plate}."
    elif call_type == "pursuit":
        text = (f"All units, {code} — {unit} in pursuit of a {veh} "
                f"northbound on {loc}. All units be advised.")
    elif call_type in _DETAIL_POOL:
        detail   = random.choice(_DETAIL_POOL[call_type])
        code_str = "Code 3" if incident["priority"] == "emergency" else "Code 2"
        text = f"{unit}, respond to a {code} at {loc}. {detail} {code_str}."
    else:
        text = f"{unit}, respond to a {code} at {loc}. Code 2."

    return text, incident


class IncidentEngine:
    """
    Daemon thread that generates radio calls to available AI officers.
    dispatch_callback(text)      → plays dispatch TTS
    behavior_callback(incident)  → starts OfficerBehaviorLoop lifecycle
    session_active               → threading.Event; if set, holds fire until clear
    """

    def __init__(
        self,
        dispatch_callback:  Callable[[str], None],
        behavior_callback:  Callable[[dict], None],
        player_callsign:    str = "Sam-44",
        session_active:     Optional[threading.Event] = None,
        min_interval: float = 90.0,
        max_interval: float = 270.0,
    ):
        self._dispatch_cb   = dispatch_callback
        self._behavior_cb   = behavior_callback
        self._player_cs     = player_callsign
        self._session_active = session_active
        self._min_interval  = min_interval
        self._max_interval  = max_interval
        self._running       = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread  = threading.Thread(
            target=self._loop, daemon=True, name="incident_engine")
        self._thread.start()
        logger.info("IncidentEngine started")

    def stop(self):
        self._running = False

    def _loop(self):
        time.sleep(random.uniform(20, 45))   # startup grace period
        while self._running:
            try:
                self._fire_incident()
            except Exception as e:
                logger.error(f"IncidentEngine: {e}")
            interval = random.uniform(self._min_interval, self._max_interval)
            for _ in range(int(interval * 10)):
                if not self._running:
                    return
                time.sleep(0.1)

    def _fire_incident(self):
        # Wait out any active player session before transmitting
        if self._session_active and self._session_active.is_set():
            return

        available = world_state.available_units(exclude=self._player_cs)
        if not available:
            logger.debug("IncidentEngine: no available units — skipping")
            return

        unit      = random.choice(available)
        call_type = random.choices(_CALL_TYPES, weights=_CALL_WEIGHTS, k=1)[0]
        text, incident = _build_dispatch_call(call_type, unit)

        logger.info(f"[INCIDENT] {call_type} → {unit}: {text!r}")
        world_state.update(unit, status=UnitStatus.ENROUTE,
                           incident=f"{call_type} at {incident['location']}")

        # Set emotional state immediately so the officer's en-route voice sounds right
        _EMOTION_MAP = {
            "pursuit":          "pursuit_start",
            "robbery":          "robbery",
            "burglary":         "backup_requested",
            "disturbance":      "backup_requested",
            "welfare_check":    "welfare_bad",
            "traffic_stop":     "routine_stop",
            "suspicious":       "routine_stop",
            "traffic_accident": "backup_requested",
        }
        trigger = _EMOTION_MAP.get(call_type, "routine_stop")
        world_state.update_emotion(unit, trigger)

        self._dispatch_cb(text)

        def _delayed():
            time.sleep(2.5)
            if self._running:
                self._behavior_cb(incident)

        threading.Thread(target=_delayed, daemon=True,
                         name=f"behavior_{unit}").start()
