"""Unit tests for lookup services: plate check, name check, criminal history,
and game state upsert.

Covers tasks 7.1, 7.3, 7.5, 7.7.
"""

import random
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from backend.services.plate_check import PlateCheckService
from backend.services.name_check import NameCheckService
from backend.services.criminal_history import CriminalHistoryService
from backend.services.game_state import GameStateService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db():
    """Return a mock DatabaseService with collection stubs."""
    db = MagicMock()
    db.db = MagicMock()
    db.db.vehicles = MagicMock()
    db.db.persons = MagicMock()
    db.audited_insert = AsyncMock(return_value="generated_id_123")
    return db


def _sample_vehicle_doc(plate="ABC1234"):
    return {
        "_id": "abc123",
        "plate": plate,
        "make": "Vapid",
        "model": "Crown Victoria",
        "color": "Black",
        "registered_owner": "John Doe",
        "registration_status": "valid",
        "insurance_status": "current",
        "flags": ["stolen"],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def _sample_person_doc(name="Jane Smith"):
    return {
        "_id": "def456",
        "name": name,
        "date_of_birth": "1990-05-15",
        "physical_description": {
            "gender": "Female",
            "race": "White",
            "height": "5'6\"",
            "weight": "130 lbs",
            "hair_color": "Brown",
            "distinguishing_marks": None,
        },
        "prior_offenses": [
            {"offense": "Petty Theft", "date": "2021-03-10", "disposition": "Convicted"}
        ],
        "active_warrants": [],
        "license_status": "valid",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


# ===================================================================
# Task 7.1 – PlateCheckService
# ===================================================================

class TestPlateCheckService:
    """Tests for PlateCheckService (Req 3.1, 3.4)."""

    @pytest.mark.asyncio
    async def test_returns_vehicle_doc_when_found(self):
        db = _mock_db()
        vehicle = _sample_vehicle_doc("XYZ9999")
        db.db.vehicles.find_one = AsyncMock(return_value=vehicle)

        svc = PlateCheckService(db)
        result = await svc.check_plate("XYZ9999")

        assert result["plate"] == "XYZ9999"
        assert result["make"] == "Vapid"
        assert result["model"] == "Crown Victoria"
        assert result["color"] == "Black"
        assert result["registered_owner"] == "John Doe"
        assert "stolen" in result["flags"]

    @pytest.mark.asyncio
    async def test_auto_generates_when_not_found(self):
        """When plate not found, auto-generate a vehicle record."""
        db = _mock_db()
        db.db.vehicles.find_one = AsyncMock(return_value=None)

        svc = PlateCheckService(db)
        result = await svc.check_plate("UNKNOWN")

        # Should have generated a record with all required fields
        assert result["plate"] == "UNKNOWN"
        assert "make" in result
        assert "model" in result
        assert "color" in result
        assert "registered_owner" in result
        assert "registration_status" in result
        assert "insurance_status" in result
        assert "flags" in result
        db.audited_insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_case_insensitive_query(self):
        db = _mock_db()
        vehicle = _sample_vehicle_doc("abc1234")
        db.db.vehicles.find_one = AsyncMock(return_value=vehicle)

        svc = PlateCheckService(db)
        result = await svc.check_plate("ABC1234")

        call_args = db.db.vehicles.find_one.call_args
        query = call_args[0][0]
        assert "$options" in query["plate"]
        assert query["plate"]["$options"] == "i"

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_plate(self):
        db = _mock_db()
        db.db.vehicles.find_one = AsyncMock(return_value=_sample_vehicle_doc())

        svc = PlateCheckService(db)
        await svc.check_plate("  ABC1234  ")

        call_args = db.db.vehicles.find_one.call_args
        query = call_args[0][0]
        assert "  " not in query["plate"]["$regex"]

    @pytest.mark.asyncio
    async def test_generated_vehicle_has_registration_and_insurance(self):
        """Auto-generated vehicles should include registration and insurance status."""
        db = _mock_db()
        db.db.vehicles.find_one = AsyncMock(return_value=None)

        svc = PlateCheckService(db)
        result = await svc.check_plate("TEST123")

        assert result["registration_status"] in ("valid", "expired", "suspended")
        assert result["insurance_status"] in ("current", "lapsed", "none")

    @pytest.mark.asyncio
    async def test_generated_vehicle_is_deterministic(self):
        """Same plate should generate the same vehicle (seeded RNG)."""
        db = _mock_db()
        db.db.vehicles.find_one = AsyncMock(return_value=None)

        svc = PlateCheckService(db)
        r1 = await svc.check_plate("SEED1")
        r2 = await svc.check_plate("SEED1")

        assert r1["make"] == r2["make"]
        assert r1["model"] == r2["model"]
        assert r1["color"] == r2["color"]
        assert r1["registered_owner"] == r2["registered_owner"]


# ===================================================================
# Task 7.3 – NameCheckService
# ===================================================================

class TestNameCheckService:
    """Tests for NameCheckService (Req 3.2, 3.4, 9.4)."""

    @pytest.mark.asyncio
    async def test_returns_full_person_record(self):
        db = _mock_db()
        person = _sample_person_doc("Jane Smith")
        db.db.persons.find_one = AsyncMock(return_value=person)

        svc = NameCheckService(db)
        result = await svc.check_name("Jane Smith")

        assert result["name"] == "Jane Smith"
        assert result["date_of_birth"] == "1990-05-15"
        assert "gender" in result["physical_description"]
        assert len(result["prior_offenses"]) == 1
        assert result["license_status"] == "valid"

    @pytest.mark.asyncio
    async def test_auto_generates_when_not_found(self):
        """When name not found, auto-generate a person record."""
        db = _mock_db()
        db.db.persons.find_one = AsyncMock(return_value=None)

        svc = NameCheckService(db)
        result = await svc.check_name("Nobody Here")

        assert result["name"] == "Nobody Here"
        assert "date_of_birth" in result
        assert "physical_description" in result
        assert "license_status" in result
        assert "prior_offenses" in result
        assert "active_warrants" in result
        db.audited_insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_case_insensitive_query(self):
        db = _mock_db()
        db.db.persons.find_one = AsyncMock(return_value=_sample_person_doc())

        svc = NameCheckService(db)
        await svc.check_name("jane smith")

        call_args = db.db.persons.find_one.call_args
        query = call_args[0][0]
        assert query["name"]["$options"] == "i"

    @pytest.mark.asyncio
    async def test_strips_whitespace_from_name(self):
        db = _mock_db()
        db.db.persons.find_one = AsyncMock(return_value=_sample_person_doc())

        svc = NameCheckService(db)
        await svc.check_name("  Jane Smith  ")

        call_args = db.db.persons.find_one.call_args
        query = call_args[0][0]
        assert "  " not in query["name"]["$regex"]


# ===================================================================
# Task 7.5 – CriminalHistoryService
# ===================================================================

class TestCriminalHistoryService:
    """Tests for CriminalHistoryService (Req 9.3, 9.5)."""

    @pytest.mark.asyncio
    async def test_returns_existing_record_if_found(self):
        db = _mock_db()
        existing = _sample_person_doc("John Doe")
        db.db.persons.find_one = AsyncMock(return_value=existing)

        svc = CriminalHistoryService(db)
        result = await svc.get_or_create("John Doe", {"gender": "Male", "race": "White",
                                                        "height": "6'0\"", "weight": "180 lbs",
                                                        "hair_color": "Black"})

        assert result["name"] == "John Doe"
        db.audited_insert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_generates_new_record_when_not_found(self):
        db = _mock_db()
        db.db.persons.find_one = AsyncMock(return_value=None)
        new_id = "new_id_abc"
        db.audited_insert = AsyncMock(return_value=new_id)

        phys = {
            "gender": "Male",
            "race": "White",
            "height": "5'10\"",
            "weight": "170 lbs",
            "hair_color": "Brown",
        }

        svc = CriminalHistoryService(db, rng=random.Random(42))
        result = await svc.get_or_create("New Ped", phys)

        assert result["name"] == "New Ped"
        assert result["_id"] == new_id
        assert result["physical_description"] == phys
        db.audited_insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generated_dob_is_valid_format(self):
        db = _mock_db()
        db.db.persons.find_one = AsyncMock(return_value=None)
        db.audited_insert = AsyncMock(return_value="id_123")

        svc = CriminalHistoryService(db, rng=random.Random(99))
        result = await svc.get_or_create("Test Ped", {
            "gender": "Female", "race": "Hispanic",
            "height": "5'4\"", "weight": "120 lbs", "hair_color": "Black",
        })

        dob = result["date_of_birth"]
        parts = dob.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4
        datetime.strptime(dob, "%Y-%m-%d")

    @pytest.mark.asyncio
    async def test_generated_license_status_is_valid(self):
        db = _mock_db()
        db.db.persons.find_one = AsyncMock(return_value=None)
        db.audited_insert = AsyncMock(return_value="id_456")

        svc = CriminalHistoryService(db, rng=random.Random(7))
        result = await svc.get_or_create("Status Ped", {
            "gender": "Male", "race": "Black",
            "height": "6'2\"", "weight": "200 lbs", "hair_color": "Bald",
        })

        assert result["license_status"] in ("valid", "suspended", "revoked", "none")

    @pytest.mark.asyncio
    async def test_generated_priors_are_list(self):
        db = _mock_db()
        db.db.persons.find_one = AsyncMock(return_value=None)
        db.audited_insert = AsyncMock(return_value="id_789")

        svc = CriminalHistoryService(db, rng=random.Random(123))
        result = await svc.get_or_create("Prior Ped", {
            "gender": "Male", "race": "Asian",
            "height": "5'8\"", "weight": "150 lbs", "hair_color": "Black",
        })

        assert isinstance(result["prior_offenses"], list)
        for prior in result["prior_offenses"]:
            assert "offense" in prior
            assert "date" in prior
            assert "disposition" in prior

    @pytest.mark.asyncio
    async def test_deterministic_with_same_seed(self):
        """Same RNG seed should produce the same profile."""
        db = _mock_db()
        db.db.persons.find_one = AsyncMock(return_value=None)
        db.audited_insert = AsyncMock(return_value="id_det")

        phys = {"gender": "Male", "race": "White",
                "height": "5'11\"", "weight": "175 lbs", "hair_color": "Blond"}

        svc1 = CriminalHistoryService(db, rng=random.Random(42))
        svc2 = CriminalHistoryService(db, rng=random.Random(42))

        r1 = await svc1.get_or_create("Seed Ped", phys)
        r2 = await svc2.get_or_create("Seed Ped", phys)

        assert r1["date_of_birth"] == r2["date_of_birth"]
        assert r1["license_status"] == r2["license_status"]
        assert r1["prior_offenses"] == r2["prior_offenses"]


# ===================================================================
# Task 7.7 – GameStateService
# ===================================================================

class TestGameStateService:
    """Tests for GameStateService upsert logic (Req 11.6)."""

    @pytest.mark.asyncio
    async def test_upsert_person_creates_new_record(self):
        db = _mock_db()
        new_id = "new_ped_id"
        mock_result = MagicMock()
        mock_result.upserted_id = new_id
        db.db.persons.update_one = AsyncMock(return_value=mock_result)
        expected_doc = {"_id": new_id, "name": "New Ped", "updated_at": datetime.now(timezone.utc)}
        db.db.persons.find_one = AsyncMock(return_value=expected_doc)

        svc = GameStateService(db)
        result = await svc.upsert_person({"name": "New Ped", "physical_description": {"gender": "Male"}})

        assert result["name"] == "New Ped"
        db.db.persons.update_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upsert_person_updates_existing_record(self):
        db = _mock_db()
        existing_id = "existing_ped_id"
        mock_result = MagicMock()
        mock_result.upserted_id = None
        db.db.persons.update_one = AsyncMock(return_value=mock_result)
        db.db.persons.find_one = AsyncMock(return_value={
            "_id": existing_id, "name": "Existing Ped",
            "physical_description": {"gender": "Female"},
        })

        svc = GameStateService(db)
        result = await svc.upsert_person({
            "name": "Existing Ped",
            "physical_description": {"gender": "Female"},
        })

        assert result["_id"] == existing_id

    @pytest.mark.asyncio
    async def test_upsert_person_uses_case_insensitive_match(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.upserted_id = "new_id"
        db.db.persons.update_one = AsyncMock(return_value=mock_result)
        db.db.persons.find_one = AsyncMock(return_value={"_id": "some_id", "name": "Test"})

        svc = GameStateService(db)
        await svc.upsert_person({"name": "Test"})

        call_args = db.db.persons.update_one.call_args
        filter_arg = call_args[0][0]
        assert "$options" in filter_arg["name"]
        assert filter_arg["name"]["$options"] == "i"

    @pytest.mark.asyncio
    async def test_upsert_vehicle_creates_new_record(self):
        db = _mock_db()
        new_id = "new_veh_id"
        mock_result = MagicMock()
        mock_result.upserted_id = new_id
        db.db.vehicles.update_one = AsyncMock(return_value=mock_result)
        db.db.vehicles.find_one = AsyncMock(return_value={
            "_id": new_id, "plate": "NEW123", "make": "Vapid", "model": "Interceptor",
        })

        svc = GameStateService(db)
        result = await svc.upsert_vehicle({
            "plate": "NEW123", "make": "Vapid", "model": "Interceptor",
            "color": "White", "registered_owner": "Nobody",
        })

        assert result["plate"] == "NEW123"
        db.db.vehicles.update_one.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upsert_vehicle_updates_existing_record(self):
        db = _mock_db()
        existing_id = "existing_veh_id"
        mock_result = MagicMock()
        mock_result.upserted_id = None
        db.db.vehicles.update_one = AsyncMock(return_value=mock_result)
        db.db.vehicles.find_one = AsyncMock(return_value={
            "_id": existing_id, "plate": "OLD456", "color": "Red",
        })

        svc = GameStateService(db)
        result = await svc.upsert_vehicle({"plate": "OLD456", "color": "Red"})

        assert result["_id"] == existing_id

    @pytest.mark.asyncio
    async def test_upsert_vehicle_uses_case_insensitive_match(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.upserted_id = "new_id"
        db.db.vehicles.update_one = AsyncMock(return_value=mock_result)
        db.db.vehicles.find_one = AsyncMock(return_value={"_id": "some_id", "plate": "abc"})

        svc = GameStateService(db)
        await svc.upsert_vehicle({"plate": "ABC"})

        call_args = db.db.vehicles.update_one.call_args
        filter_arg = call_args[0][0]
        assert filter_arg["plate"]["$options"] == "i"

    @pytest.mark.asyncio
    async def test_upsert_person_sets_created_at_only_on_insert(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.upserted_id = "new_id"
        db.db.persons.update_one = AsyncMock(return_value=mock_result)
        db.db.persons.find_one = AsyncMock(return_value={"_id": "some_id", "name": "Test"})

        svc = GameStateService(db)
        await svc.upsert_person({"name": "Test"})

        call_args = db.db.persons.update_one.call_args
        update_doc = call_args[0][1]
        assert "created_at" in update_doc["$setOnInsert"]
        assert "created_at" not in update_doc["$set"]

    @pytest.mark.asyncio
    async def test_upsert_vehicle_sets_created_at_only_on_insert(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.upserted_id = "new_id"
        db.db.vehicles.update_one = AsyncMock(return_value=mock_result)
        db.db.vehicles.find_one = AsyncMock(return_value={"_id": "some_id", "plate": "X"})

        svc = GameStateService(db)
        await svc.upsert_vehicle({"plate": "X"})

        call_args = db.db.vehicles.update_one.call_args
        update_doc = call_args[0][1]
        assert "created_at" in update_doc["$setOnInsert"]
        assert "created_at" not in update_doc["$set"]
