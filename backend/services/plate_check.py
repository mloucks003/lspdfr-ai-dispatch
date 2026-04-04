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

REGISTRATION_STATUSES = ["valid", "valid", "valid", "valid", "valid",
                         "expired", "suspended"]
INSURANCE_STATUSES = ["current", "current", "current", "current",
                      "lapsed", "none"]


class PlateCheckService:
    def __init__(self, db: DatabaseService) -> None:
        self._db = db

    async def check_plate(self, plate: str) -> Dict[str, Any]:
        escaped = re.escape(plate.strip())
        doc = await self._db.db.vehicles.find_one(
            {"plate": {"$regex": f"^{escaped}$", "$options": "i"}}
        )

        if doc is not None:
            # Fill in any missing fields (e.g. record came from plugin
            # game state which only has plate/make/model/color)
            doc = await self._enrich_vehicle(doc)
            logger.info("Plate check for %r: found existing record", plate)
            return doc

        # Auto-generate a full vehicle record
        doc = self._generate_vehicle(plate.strip().upper())
        doc_id = await self._db.audited_insert("vehicles", doc)
        doc["_id"] = doc_id
        logger.info("Plate check for %r: generated new record", plate)
        return doc

    async def _enrich_vehicle(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Fill in missing dispatch fields on a vehicle record.

        The plugin only sends plate/make/model/color from the game.
        When an officer runs a plate we need owner, registration, insurance,
        and flags — generate those deterministically from the plate and
        persist them so subsequent checks are consistent.
        """
        plate = doc.get("plate", "")
        rng = random.Random(hash(plate.upper()))

        updates: Dict[str, Any] = {}

        if not doc.get("registered_owner"):
            updates["registered_owner"] = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        else:
            # Advance RNG to keep subsequent values stable
            rng.choice(FIRST_NAMES)
            rng.choice(LAST_NAMES)

        if not doc.get("registration_status"):
            updates["registration_status"] = rng.choice(REGISTRATION_STATUSES)
        else:
            rng.choice(REGISTRATION_STATUSES)

        if not doc.get("insurance_status"):
            updates["insurance_status"] = rng.choice(INSURANCE_STATUSES)
        else:
            rng.choice(INSURANCE_STATUSES)

        if "flags" not in doc or doc.get("flags") is None:
            flag = rng.choice(FLAGS)
            updates["flags"] = [flag] if flag else []

        if updates:
            await self._db.db.vehicles.update_one(
                {"_id": doc["_id"]},
                {"$set": updates},
            )
            doc.update(updates)
            logger.info("Enriched vehicle record for plate %r with %s",
                        plate, list(updates.keys()))

        return doc

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
            "registration_status": rng.choice(REGISTRATION_STATUSES),
            "insurance_status": rng.choice(INSURANCE_STATUSES),
            "flags": [flag] if flag else [],
            "created_at": now,
            "updated_at": now,
        }
