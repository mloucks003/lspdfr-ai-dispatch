"""
officer_behavior.py — OfficerBehaviorLoop for BlueLineDispatchPro.

After IncidentEngine dispatches a call, one OfficerBehaviorLoop instance
autonomously runs the assigned officer through the full radio lifecycle.

Traffic stop  →  arrive  →  plate run  →  plate return  →  clear
Other call    →  arrive  →  (mid-update)  →  clear
Pursuit       →  4 update transmissions  →  caught or lost

All officer transmissions go through _speak_as_officer (TTS + PTT + radio FX).
All dispatch transmissions go through the shared _speak TTS pipeline.
The loop pauses while a player session is active so there's no conflict.
"""

import logging
import random
import threading
import time
from typing import Callable, Optional

from core.world_state import world_state, UnitStatus

logger = logging.getLogger(__name__)

_FIRST = ["Michael","James","David","Robert","Sarah","Maria","John","Lisa",
          "Anthony","Karen","Marcus","Denise","Derek","Sandra","Chris","Ryan"]
_LAST  = ["Johnson","Williams","Brown","Garcia","Martinez","Davis","Wilson",
          "Anderson","Taylor","Moore","Harris","Jackson","White","Lewis"]
_MAKES = ["Toyota","Honda","Ford","Chevrolet","Dodge","Nissan","Hyundai",
          "GMC","Kia","Mazda","Subaru","Volkswagen"]
_STREETS = ["Forum Drive","Olympic Freeway","Del Perro Freeway","Route 68",
            "Strawberry Avenue","Alta Street","Davis Avenue","Power Street",
            "Maze Bank Avenue","Capital Boulevard","Vinewood Hills Drive"]

_PURSUIT_LINES = [
    "{unit}, vehicle now {speed} mph, approaching {street}.",
    "{unit}, still in pursuit — {speed} mph northbound on {street}.",
    "{unit}, requesting spike strips at {street}. Suspect not stopping.",
    "{unit}, vehicle cut through a lot — now eastbound on {street}.",
]

_CLEAR = {
    "traffic_stop":     ["{unit}, 10-98. Warning issued. 10-8.",
                         "{unit}, 10-98. Subject cited. 10-8, available.",
                         "{unit}, subject in custody. 10-15. Need transport."],
    "disturbance":      ["{unit}, 10-98. Parties separated. No further. 10-8.",
                         "{unit}, code 4. Subjects GOA. 10-8."],
    "suspicious":       ["{unit}, code 4. Subject released, no wants. 10-8.",
                         "{unit}, suspicious vehicle departed prior to arrival. 10-8."],
    "traffic_accident": ["{unit}, 10-98. Parties exchanged info. No injuries. 10-8.",
                         "{unit}, code 4. One towed, minor injury — EMS advised. 10-8."],
    "welfare_check":    ["{unit}, code 4. Subject contacted, no injuries. 10-8.",
                         "{unit}, 10-98. Subject transported voluntarily. 10-8."],
    "burglary":         ["{unit}, code 4. No suspect on premises. Report taken. 10-8.",
                         "{unit}, 10-98. Detectives notified. 10-8."],
    "robbery":          ["{unit}, code 4. No suspect in area. Victim treated. 10-8.",
                         "{unit}, 10-98. Suspect detained. Need transport at {location}."],
}


class OfficerBehaviorLoop:
    def __init__(
        self,
        officers:           dict,
        officer_speak_fn:   Callable,
        dispatch_speak_fn:  Callable,
        session_active:     Optional[threading.Event] = None,
    ):
        self._officers      = officers
        self._officer_speak = officer_speak_fn
        self._dispatch      = dispatch_speak_fn
        self._session_active = session_active

    def handle_incident(self, incident: dict):
        unit    = incident["unit"]
        officer = self._officers.get(unit)
        if not officer:
            return
        routes = {
            "traffic_stop": self._traffic_stop,
            "pursuit":      self._pursuit,
        }
        target = routes.get(incident["type"], self._generic)
        threading.Thread(target=target, args=(officer, incident),
                         daemon=True, name=f"lifecycle_{unit}").start()

    def _pause_sleep(self, seconds: float):
        """Sleep, pausing the countdown while a player session is active."""
        remaining = seconds
        while remaining > 0:
            time.sleep(0.1)
            if not (self._session_active and self._session_active.is_set()):
                remaining -= 0.1

    def _tx(self, officer: dict, text: str):
        logger.info(f"[{officer['callsign']}] (behavior): {text!r}")
        self._officer_speak(officer, text)

    def _traffic_stop(self, officer: dict, incident: dict):
        unit  = officer["callsign"]
        loc   = incident["location"]
        plate = incident.get("plate", "4ABC123")
        try:
            self._pause_sleep(random.uniform(25, 45))
            world_state.update(unit, status=UnitStatus.ON_SCENE,
                               incident=f"traffic stop at {loc}")
            self._tx(officer, f"{unit}, 10-97 at {loc}.")

            self._pause_sleep(random.uniform(30, 55))
            self._tx(officer, f"{unit}, run a 10-29 on plate {plate}.")

            self._pause_sleep(random.uniform(8, 20))
            owner = f"{random.choice(_FIRST)} {random.choice(_LAST)}"
            year  = str(random.randint(2004, 2023))
            make  = random.choice(_MAKES)
            r     = random.random()
            if r < 0.80:
                warrant = "Returns negative, no wants or warrants."
            elif r < 0.95:
                warrant = "Returns with a misdemeanor warrant. Use caution."
            else:
                warrant = "RETURNS WITH AN ACTIVE FELONY WARRANT. Use extreme caution."
            self._dispatch(
                f"{unit}, 10-29 return on plate {plate} — registered to {owner}, "
                f"{year} {make}. {warrant}"
            )

            self._pause_sleep(random.uniform(90, 300))
            clear = random.choice(_CLEAR.get("traffic_stop", ["{unit}, 10-98. 10-8."]))
            self._tx(officer, clear.format(unit=unit, location=loc))
            world_state.update(unit, status=UnitStatus.AVAILABLE, incident=None)
        except Exception as e:
            logger.error(f"traffic_stop lifecycle {unit}: {e}")
            world_state.update(unit, status=UnitStatus.AVAILABLE, incident=None)

    def _generic(self, officer: dict, incident: dict):
        unit      = officer["callsign"]
        call_type = incident["type"]
        loc       = incident["location"]
        try:
            self._pause_sleep(random.uniform(60, 180))
            world_state.update(unit, status=UnitStatus.ON_SCENE,
                               incident=f"{call_type} at {loc}")
            self._tx(officer, f"{unit}, 10-97 at {loc}.")
            call_dur = random.uniform(120, 400)
            if call_dur > 240:
                self._pause_sleep(call_dur * 0.5)
                self._tx(officer, f"{unit}, still 10-6 at {loc}.")
                self._pause_sleep(call_dur * 0.5)
            else:
                self._pause_sleep(call_dur)
            clear = random.choice(_CLEAR.get(call_type, ["{unit}, 10-98. 10-8."]))
            self._tx(officer, clear.format(unit=unit, location=loc))
            world_state.update(unit, status=UnitStatus.AVAILABLE, incident=None)
        except Exception as e:
            logger.error(f"generic lifecycle {unit}: {e}")
            world_state.update(unit, status=UnitStatus.AVAILABLE, incident=None)

    def _pursuit(self, officer: dict, incident: dict):
        unit = officer["callsign"]
        try:
            world_state.update(unit, status=UnitStatus.ON_CALL,
                               incident=f"pursuit on {incident['location']}")
            updates = random.sample(_PURSUIT_LINES, min(4, len(_PURSUIT_LINES)))
            for tmpl in updates:
                self._pause_sleep(random.uniform(20, 40))
                self._tx(officer, tmpl.format(
                    unit=unit,
                    street=random.choice(_STREETS),
                    speed=random.choice(["55", "70", "80", "90"]),
                ))
            self._pause_sleep(random.uniform(15, 30))
            if random.random() < 0.65:
                end = f"{unit}, suspect in custody at {random.choice(_STREETS)}. Code 4."
            else:
                end = f"{unit}, pursuit terminated — lost sight near {random.choice(_STREETS)}. 10-8."
            self._tx(officer, end)
            world_state.update(unit, status=UnitStatus.AVAILABLE, incident=None)
        except Exception as e:
            logger.error(f"pursuit lifecycle {unit}: {e}")
            world_state.update(unit, status=UnitStatus.AVAILABLE, incident=None)
