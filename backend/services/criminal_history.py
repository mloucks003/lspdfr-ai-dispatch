"""Criminal history generation service.

When a ped has no existing record, generates a randomised criminal history
profile (DOB, license status, prior offenses) and persists it so that
subsequent queries return consistent data.

Requirements: 9.3, 9.5
"""

import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from backend.models.enums import LicenseStatus
from backend.services.database import DatabaseService

logger = logging.getLogger(__name__)

# Weighted license status distribution: mostly valid
_LICENSE_WEIGHTS: List[tuple] = [
    (LicenseStatus.VALID, 50),
    (LicenseStatus.SUSPENDED, 25),
    (LicenseStatus.REVOKED, 15),
    (LicenseStatus.NONE_, 10),
]

_COMMON_OFFENSES: List[str] = [
    "Petty Theft",
    "Grand Theft Auto",
    "Assault",
    "Battery",
    "DUI",
    "Possession of Controlled Substance",
    "Burglary",
    "Vandalism",
    "Trespassing",
    "Disorderly Conduct",
    "Reckless Driving",
    "Evading Police",
    "Robbery",
    "Fraud",
    "Domestic Violence",
]

_DISPOSITIONS: List[str] = [
    "Convicted",
    "Acquitted",
    "Dismissed",
    "Pled Guilty",
    "Probation",
]


class CriminalHistoryService:
    """Generates and persists criminal history profiles for new peds."""

    def __init__(self, db: DatabaseService, rng: Optional[random.Random] = None) -> None:
        self._db = db
        self._rng = rng or random.Random()

    async def get_or_create(
        self,
        name: str,
        physical_description: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Return the existing person record or generate a new one.

        Args:
            name: The ped's full name.
            physical_description: Dict with gender, race, height, weight,
                hair_color, and optional distinguishing_marks.

        Returns:
            The person document (existing or newly created).
        """
        import re
        escaped = re.escape(name.strip())
        existing = await self._db.db.persons.find_one(
            {"name": {"$regex": f"^{escaped}$", "$options": "i"}}
        )
        if existing is not None:
            logger.info("Criminal history for %r: existing record found", name)
            return existing

        # Generate new profile
        profile = self._generate_profile(name, physical_description)
        doc_id = await self._db.audited_insert("persons", profile)
        profile["_id"] = doc_id
        logger.info("Criminal history for %r: new record generated (%s)", name, doc_id)
        return profile

    # ------------------------------------------------------------------
    # Generation helpers
    # ------------------------------------------------------------------

    def _generate_profile(
        self, name: str, physical_description: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build a randomised person document."""
        now = datetime.now(timezone.utc)
        return {
            "name": name,
            "date_of_birth": self._random_dob(),
            "physical_description": physical_description,
            "prior_offenses": self._random_priors(),
            "active_warrants": [],
            "license_status": self._random_license_status().value,
            "created_at": now,
            "updated_at": now,
        }

    def _random_dob(self) -> str:
        """Generate a random DOB between 18 and 65 years ago."""
        today = datetime.now(timezone.utc).date()
        min_age_days = 18 * 365
        max_age_days = 65 * 365
        age_days = self._rng.randint(min_age_days, max_age_days)
        dob = today - timedelta(days=age_days)
        return dob.strftime("%Y-%m-%d")

    def _random_license_status(self) -> LicenseStatus:
        """Pick a license status using weighted random selection."""
        statuses = [s for s, _ in _LICENSE_WEIGHTS]
        weights = [w for _, w in _LICENSE_WEIGHTS]
        return self._rng.choices(statuses, weights=weights, k=1)[0]

    def _random_priors(self) -> List[Dict[str, str]]:
        """Generate 0-5 random prior offenses."""
        count = self._rng.randint(0, 5)
        priors = []
        today = datetime.now(timezone.utc).date()
        for _ in range(count):
            offense_date = today - timedelta(days=self._rng.randint(30, 3650))
            priors.append({
                "offense": self._rng.choice(_COMMON_OFFENSES),
                "date": offense_date.strftime("%Y-%m-%d"),
                "disposition": self._rng.choice(_DISPOSITIONS),
            })
        return priors
