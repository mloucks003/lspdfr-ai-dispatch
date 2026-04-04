"""Name check lookup service.

Queries the persons collection by name. If not found, auto-generates
a realistic criminal history record so dispatch always has data.
"""

import logging
import random
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from backend.services import DatabaseService

logger = logging.getLogger(__name__)

GENDERS = ["Male", "Female"]
RACES = ["White", "Black", "Hispanic", "Asian"]
HAIR_COLORS = ["Black", "Brown", "Blonde", "Red", "Gray", "Bald"]
HEIGHTS = ["5'4\"", "5'6\"", "5'8\"", "5'10\"", "6'0\"", "6'2\""]
WEIGHTS = ["120 lbs", "140 lbs", "160 lbs", "175 lbs", "190 lbs", "210 lbs", "230 lbs"]
LICENSE_STATUSES = ["valid", "valid", "valid", "valid", "suspended", "revoked", "none"]

OFFENSES = ["Petty Theft", "Grand Theft Auto", "Assault", "Battery", "DUI",
            "Possession of Controlled Substance", "Burglary", "Vandalism",
            "Trespassing", "Disorderly Conduct", "Reckless Driving",
            "Evading Police", "Robbery", "Fraud", "Domestic Violence"]

DISPOSITIONS = ["Convicted", "Acquitted", "Dismissed", "Pled Guilty", "Probation"]


class NameCheckService:
    def __init__(self, db: DatabaseService) -> None:
        self._db = db

    async def check_name(self, name: str) -> Dict[str, Any]:
        escaped = re.escape(name.strip())
        doc = await self._db.db.persons.find_one(
            {"name": {"$regex": f"^{escaped}$", "$options": "i"}}
        )

        if doc is not None:
            logger.info("Name check for %r: found existing record", name)
            return doc

        # Auto-generate a person record with criminal history
        doc = self._generate_person(name.strip())
        doc_id = await self._db.audited_insert("persons", doc)
        doc["_id"] = doc_id
        logger.info("Name check for %r: generated new record", name)
        return doc

    def _generate_person(self, name: str) -> Dict[str, Any]:
        rng = random.Random(hash(name.lower()))
        now = datetime.now(timezone.utc)
        today = now.date()

        # Generate DOB (18-65 years ago)
        age_days = rng.randint(18 * 365, 65 * 365)
        dob = today - timedelta(days=age_days)

        gender = rng.choice(GENDERS)
        race = rng.choice(RACES)

        # Generate 0-4 prior offenses
        num_priors = rng.choices([0, 1, 2, 3, 4], weights=[40, 25, 20, 10, 5])[0]
        priors = []
        for _ in range(num_priors):
            offense_date = today - timedelta(days=rng.randint(30, 3650))
            priors.append({
                "offense": rng.choice(OFFENSES),
                "date": offense_date.strftime("%Y-%m-%d"),
                "disposition": rng.choice(DISPOSITIONS),
            })

        return {
            "name": name,
            "date_of_birth": dob.strftime("%Y-%m-%d"),
            "physical_description": {
                "gender": gender,
                "race": race,
                "height": rng.choice(HEIGHTS),
                "weight": rng.choice(WEIGHTS),
                "hair_color": rng.choice(HAIR_COLORS),
                "distinguishing_marks": None,
            },
            "prior_offenses": priors,
            "active_warrants": [],
            "license_status": rng.choice(LICENSE_STATUSES),
            "created_at": now,
            "updated_at": now,
        }
