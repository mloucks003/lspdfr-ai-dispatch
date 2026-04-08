"""Plate check lookup service.

Queries the vehicles collection by plate number. If not found,
auto-generates a realistic vehicle record so dispatch always has
data to report back.
"""

import logging
import random
import re
from datetime import datetime, timezone
from typing import Any, Dict

from backend.services import DatabaseService

logger = logging.getLogger(__name__)

GTA_MAKES = ["Albany", "Benefactor", "Bravado", "Canis", "Cheval", "Coil",
             "Declasse", "Dewbauchee", "Dinka", "Dundreary", "Emperor",
             "Enus", "Gallivanter", "Grotti", "Imponte", "Karin", "Lampadati",
             "Maibatsu", "Obey", "Ocelot", "Pegassi", "Pfister", "Ubermacht",
             "Vapid", "Vulcar", "Weeny", "Western"]

GTA_MODELS = {
    "Albany": ["Cavalcade", "Emperor", "Presidente", "Washington"],
    "Benefactor": ["Schafter", "Schwartzer", "Serrano", "XLS"],
    "Bravado": ["Buffalo", "Gauntlet", "Gresley"],
    "Declasse": ["Granger", "Premier", "Rancher", "Vigero"],
    "Dinka": ["Blista", "Jester", "Sugoi"],
    "Enus": ["Cognoscenti", "Huntley", "Windsor"],
    "Karin": ["Asterope", "Futo", "Intruder", "Sultan"],
    "Obey": ["Rocoto", "Tailgater"],
    "Ubermacht": ["Oracle", "Sentinel", "Zion"],
    "Vapid": ["Bullet", "Dominator", "Interceptor", "Stanier"],
}

COLORS = ["Black", "White", "Silver", "Gray", "Red", "Blue", "Dark Blue",
          "Green", "Yellow", "Orange", "Brown", "Beige", "Maroon"]

FIRST_NAMES = ["James", "Michael", "Robert", "David", "John", "Maria",
               "Jennifer", "Linda", "Patricia", "Elizabeth", "Carlos",
               "Miguel", "Wei", "Kenji", "Andre", "Tyrone", "Sarah"]

LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia",
              "Miller", "Davis", "Rodriguez", "Martinez", "Anderson",
              "Taylor", "Thomas", "Jackson", "White", "Harris", "Clark"]

FLAGS = ["", "", "", "", "", "stolen", "expired_registration", "bolo",
         "suspended_registration"]


class PlateCheckService:
    def __init__(self, db: DatabaseService) -> None:
        self._db = db

    async def check_plate(self, plate: str) -> Dict[str, Any]:
        clean = plate.strip().upper()
        # Remove spaces/dashes that speech recognition might insert
        normalized = re.sub(r"[\s\-]+", "", clean)
        logger.info("Plate check requested: raw=%r, normalized=%r", plate, normalized)

        # 1. Exact match (case-insensitive)
        escaped = re.escape(normalized)
        doc = await self._db.db.vehicles.find_one(
            {"plate": {"$regex": f"^{escaped}$", "$options": "i"}}
        )
        if doc is not None:
            logger.info("Plate check for %r: exact match found — %s %s %s",
                        normalized, doc.get("color"), doc.get("make"), doc.get("model"))
            return doc

        # 2. Partial/fuzzy match — plate might be a substring or vice versa
        #    Search all vehicles and find the best match
        all_vehicles = await self._db.db.vehicles.find().to_list(1000)
        if all_vehicles:
            best_match = None
            best_score = 0
            for v in all_vehicles:
                v_plate = re.sub(r"[\s\-]+", "", (v.get("plate") or "").upper())
                if not v_plate:
                    continue
                # Check if one contains the other
                if normalized in v_plate or v_plate in normalized:
                    score = len(v_plate)
                    if score > best_score:
                        best_score = score
                        best_match = v
                # Check character overlap ratio
                else:
                    common = sum(1 for a, b in zip(normalized, v_plate) if a == b)
                    max_len = max(len(normalized), len(v_plate))
                    if max_len > 0 and common / max_len > 0.6:
                        if common > best_score:
                            best_score = common
                            best_match = v

            if best_match:
                logger.info("Plate check for %r: fuzzy match to %r — %s %s %s",
                            normalized, best_match.get("plate"),
                            best_match.get("color"), best_match.get("make"),
                            best_match.get("model"))
                return best_match

        # 3. No match at all — tell the officer
        logger.info("Plate check for %r: no record found in database", normalized)
        return {"status": "no_record", "plate": normalized,
                "message": "No record on file for that plate."}

    def _generate_vehicle(self, plate: str) -> Dict[str, Any]:
        rng = random.Random(hash(plate))
        make = rng.choice(GTA_MAKES)
        models = GTA_MODELS.get(make, ["Unknown"])
        model = rng.choice(models)
        color = rng.choice(COLORS)
        owner = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        flag = rng.choice(FLAGS)
        now = datetime.now(timezone.utc)

        return {
            "plate": plate,
            "make": make,
            "model": model,
            "color": color,
            "registered_owner": owner,
            "flags": [flag] if flag else [],
            "created_at": now,
            "updated_at": now,
        }
