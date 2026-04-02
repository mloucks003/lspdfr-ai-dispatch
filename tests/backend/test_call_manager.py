"""Unit tests for CallManager, OfficerStatusService, BOLOService, and WarrantService.

Covers tasks 6.1, 6.3, 6.5, 6.7, 6.9.
Requirements: 4.1, 4.3, 5.1, 5.3, 5.6, 6.1, 6.2, 6.3, 8.3
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from backend.models.enums import BOLOStatus, CallStatus, WarrantStatus
from backend.services.call_manager import CallManager, CRIME_PRIORITY_MAP, DEFAULT_PRIORITY
from backend.services.officer_status import OfficerStatusService, VALID_STATUS_CODES
from backend.services.bolo_service import BOLOService
from backend.services.warrant_service import WarrantService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db() -> MagicMock:
    """Create a mock DatabaseService with common async methods."""
    db = MagicMock()
    db.db = MagicMock()
    db.audited_insert = AsyncMock(return_value=ObjectId())
    db.audited_update = AsyncMock(return_value=ObjectId())
    return db


def _mock_hub() -> MagicMock:
    """Create a mock WebSocketHub."""
    hub = MagicMock()
    hub.send_to = AsyncMock()
    hub.broadcast = AsyncMock()
    return hub


def _make_911_event(
    crime_type: str = "robbery",
    street: str = "Vinewood Blvd",
    landmark: str | None = "near Vinewood Sign",
    peds: list | None = None,
    caller_desc: str = "Female caller reports a robbery in progress",
) -> dict:
    """Build a 911 call event dict."""
    return {
        "crime_type": crime_type,
        "location": {"street": street, "landmark": landmark, "x": 100.0, "y": 200.0, "z": 30.0},
        "involved_peds": peds or [{"name": "John Doe", "description": "White male, red shirt"}],
        "caller_description": caller_desc,
    }


# ===========================================================================
# Task 6.1 — CallManager
# ===========================================================================


class TestCallManagerPriorityMapping:
    """Crime type → priority mapping."""

    def test_robbery_is_priority_1(self):
        cm = CallManager(_mock_db(), _mock_hub())
        assert cm._map_priority("robbery") == 1

    def test_traffic_stop_is_priority_3(self):
        cm = CallManager(_mock_db(), _mock_hub())
        assert cm._map_priority("traffic_stop") == 3

    def test_domestic_disturbance_is_priority_2(self):
        cm = CallManager(_mock_db(), _mock_hub())
        assert cm._map_priority("domestic_disturbance") == 2

    def test_unknown_type_gets_default_priority(self):
        cm = CallManager(_mock_db(), _mock_hub())
        assert cm._map_priority("alien_invasion") == DEFAULT_PRIORITY

    def test_case_insensitive(self):
        cm = CallManager(_mock_db(), _mock_hub())
        assert cm._map_priority("ROBBERY") == 1
        assert cm._map_priority("Traffic_Stop") == 3


class TestCallManagerCreateCall:
    """create_call_from_911 converts events to CAD calls."""

    @pytest.mark.asyncio
    async def test_creates_call_with_correct_fields(self):
        db = _mock_db()
        hub = _mock_hub()
        # Mock counter for call number
        db.db.counters.find_one_and_update = AsyncMock(return_value={"seq": 1})
        cm = CallManager(db, hub)

        event = _make_911_event()
        call = await cm.create_call_from_911(event)

        assert call["type"] == "robbery"
        assert call["priority"] == 1
        assert call["status"] == CallStatus.PENDING.value
        assert call["location"]["street"] == "Vinewood Blvd"
        assert call["suspect_description"] is not None
        assert call["assigned_units"] == []
        assert call["call_number"].endswith("-0001")
        db.audited_insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_auto_increments_call_numbers(self):
        db = _mock_db()
        hub = _mock_hub()
        seq = {"seq": 0}

        async def fake_counter(*args, **kwargs):
            seq["seq"] += 1
            return {"seq": seq["seq"]}

        db.db.counters.find_one_and_update = AsyncMock(side_effect=fake_counter)
        cm = CallManager(db, hub)

        c1 = await cm.create_call_from_911(_make_911_event())
        c2 = await cm.create_call_from_911(_make_911_event(crime_type="theft"))

        assert c1["call_number"] != c2["call_number"]
        assert c1["call_number"].endswith("-0001")
        assert c2["call_number"].endswith("-0002")

    @pytest.mark.asyncio
    async def test_broadcasts_to_radio_and_cad(self):
        db = _mock_db()
        hub = _mock_hub()
        db.db.counters.find_one_and_update = AsyncMock(return_value={"seq": 5})
        cm = CallManager(db, hub)

        await cm.create_call_from_911(_make_911_event())

        # Should send to both radio and cad
        assert hub.send_to.await_count == 2
        call_types = [call.args[0] for call in hub.send_to.await_args_list]
        assert "radio" in call_types
        assert "cad" in call_types

        # Verify message structure
        for call in hub.send_to.await_args_list:
            msg = call.args[1]
            assert msg["type"] == "call_update"
            assert "call" in msg

    @pytest.mark.asyncio
    async def test_handles_event_with_no_peds(self):
        db = _mock_db()
        hub = _mock_hub()
        db.db.counters.find_one_and_update = AsyncMock(return_value={"seq": 1})
        cm = CallManager(db, hub)

        event = {
            "crime_type": "theft",
            "location": {"street": "Grove St"},
            "involved_peds": [],
            "caller_description": "Theft reported",
        }
        call = await cm.create_call_from_911(event)

        assert call["suspect_description"] is None

    @pytest.mark.asyncio
    async def test_handles_event_with_missing_location_coords(self):
        db = _mock_db()
        hub = _mock_hub()
        db.db.counters.find_one_and_update = AsyncMock(return_value={"seq": 1})
        cm = CallManager(db, hub)

        event = {
            "crime_type": "theft",
            "location": {"street": "Grove St"},
            "involved_peds": [],
            "caller_description": "Theft reported",
        }
        call = await cm.create_call_from_911(event)

        assert call["location"]["street"] == "Grove St"
        assert call["location"]["coordinates"] is None

    @pytest.mark.asyncio
    async def test_priority_range_is_1_to_3(self):
        db = _mock_db()
        hub = _mock_hub()
        db.db.counters.find_one_and_update = AsyncMock(return_value={"seq": 1})
        cm = CallManager(db, hub)

        for crime_type in list(CRIME_PRIORITY_MAP.keys()) + ["unknown_type"]:
            event = _make_911_event(crime_type=crime_type)
            call = await cm.create_call_from_911(event)
            assert 1 <= call["priority"] <= 3


# ===========================================================================
# Task 6.3 — OfficerStatusService
# ===========================================================================


class TestOfficerStatusUpdate:
    """update_status persists and broadcasts officer status."""

    @pytest.mark.asyncio
    async def test_updates_status_in_db(self):
        db = _mock_db()
        hub = _mock_hub()
        db.db.units.update_one = AsyncMock()
        db.db.units.find_one = AsyncMock(return_value={
            "callsign": "1-Adam-12", "status": "10-76",
        })
        svc = OfficerStatusService(db, hub)

        result = await svc.update_status("1-Adam-12", "10-76")

        db.db.units.update_one.assert_awaited_once()
        assert result["status"] == "10-76"

    @pytest.mark.asyncio
    async def test_broadcasts_status_to_cad(self):
        db = _mock_db()
        hub = _mock_hub()
        db.db.units.update_one = AsyncMock()
        db.db.units.find_one = AsyncMock(return_value={
            "callsign": "2-Tom-7", "status": "10-97",
        })
        svc = OfficerStatusService(db, hub)

        await svc.update_status("2-Tom-7", "10-97")

        hub.send_to.assert_awaited_once_with("cad", {
            "type": "status_update",
            "unit": "2-Tom-7",
            "status": "10-97",
        })

    @pytest.mark.asyncio
    async def test_rejects_invalid_status_code(self):
        svc = OfficerStatusService(_mock_db(), _mock_hub())
        with pytest.raises(ValueError, match="Invalid status code"):
            await svc.update_status("1-Adam-12", "10-99")

    @pytest.mark.asyncio
    async def test_all_valid_codes_accepted(self):
        db = _mock_db()
        hub = _mock_hub()
        db.db.units.update_one = AsyncMock()
        db.db.units.find_one = AsyncMock(return_value={"callsign": "X", "status": ""})
        svc = OfficerStatusService(db, hub)

        for code in VALID_STATUS_CODES:
            await svc.update_status("1-Adam-12", code)


class TestOfficerGetStatus:
    """get_status retrieves the current unit document."""

    @pytest.mark.asyncio
    async def test_returns_unit_doc(self):
        db = _mock_db()
        expected = {"callsign": "1-Adam-12", "status": "10-8"}
        db.db.units.find_one = AsyncMock(return_value=expected)
        svc = OfficerStatusService(db, _mock_hub())

        result = await svc.get_status("1-Adam-12")
        assert result == expected

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown(self):
        db = _mock_db()
        db.db.units.find_one = AsyncMock(return_value=None)
        svc = OfficerStatusService(db, _mock_hub())

        result = await svc.get_status("unknown-unit")
        assert result is None


class TestCallAssignment:
    """assign_call adds callsign to call and sets officer to 10-76."""

    @pytest.mark.asyncio
    async def test_assigns_officer_to_call(self):
        db = _mock_db()
        hub = _mock_hub()
        call_id = ObjectId()
        db.audited_update = AsyncMock(return_value=call_id)
        db.db.calls.find_one = AsyncMock(return_value={
            "_id": call_id,
            "call_number": "2024-0001",
            "type": "robbery",
            "priority": 1,
            "location": {"street": "Vinewood Blvd"},
            "assigned_units": ["1-Adam-12"],
            "status": CallStatus.DISPATCHED.value,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        db.db.units.update_one = AsyncMock()
        db.db.units.find_one = AsyncMock(return_value={
            "callsign": "1-Adam-12", "status": "10-76",
        })
        svc = OfficerStatusService(db, hub)

        result = await svc.assign_call(call_id, "1-Adam-12")

        # Call should have been updated with $addToSet
        db.audited_update.assert_awaited_once()
        update_args = db.audited_update.call_args
        assert update_args[0][0] == "calls"
        update_ops = update_args[0][2]
        assert "$addToSet" in update_ops
        assert update_ops["$addToSet"]["assigned_units"] == "1-Adam-12"

        # Officer status should be 10-76
        db.db.units.update_one.assert_awaited()

    @pytest.mark.asyncio
    async def test_broadcasts_call_update_to_cad(self):
        db = _mock_db()
        hub = _mock_hub()
        call_id = ObjectId()
        db.audited_update = AsyncMock(return_value=call_id)
        db.db.calls.find_one = AsyncMock(return_value={
            "_id": call_id,
            "call_number": "2024-0001",
            "type": "robbery",
            "priority": 1,
            "location": {"street": "Vinewood Blvd"},
            "assigned_units": ["1-Adam-12"],
            "status": CallStatus.DISPATCHED.value,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        db.db.units.update_one = AsyncMock()
        db.db.units.find_one = AsyncMock(return_value={
            "callsign": "1-Adam-12", "status": "10-76",
        })
        svc = OfficerStatusService(db, hub)

        await svc.assign_call(call_id, "1-Adam-12")

        # Should broadcast status_update (from update_status) and call_update
        cad_calls = [c for c in hub.send_to.await_args_list if c.args[0] == "cad"]
        msg_types = [c.args[1]["type"] for c in cad_calls]
        assert "call_update" in msg_types
        assert "status_update" in msg_types

    @pytest.mark.asyncio
    async def test_raises_for_missing_call(self):
        db = _mock_db()
        hub = _mock_hub()
        db.audited_update = AsyncMock(return_value=None)
        svc = OfficerStatusService(db, hub)

        with pytest.raises(ValueError, match="not found"):
            await svc.assign_call(ObjectId(), "1-Adam-12")

    @pytest.mark.asyncio
    async def test_accepts_string_call_id(self):
        db = _mock_db()
        hub = _mock_hub()
        call_id = ObjectId()
        db.audited_update = AsyncMock(return_value=call_id)
        db.db.calls.find_one = AsyncMock(return_value={
            "_id": call_id,
            "call_number": "2024-0001",
            "type": "theft",
            "priority": 2,
            "location": {"street": "Grove St"},
            "assigned_units": ["1-Adam-12"],
            "status": CallStatus.DISPATCHED.value,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        db.db.units.update_one = AsyncMock()
        db.db.units.find_one = AsyncMock(return_value={
            "callsign": "1-Adam-12", "status": "10-76",
        })
        svc = OfficerStatusService(db, hub)

        # Pass string ID — should be converted to ObjectId
        result = await svc.assign_call(str(call_id), "1-Adam-12")
        assert result is not None


# ===========================================================================
# Task 6.5 — Backup Request
# ===========================================================================


class TestBackupRequest:
    """request_backup creates a high-priority call and broadcasts."""

    @pytest.mark.asyncio
    async def test_creates_priority_1_call(self):
        db = _mock_db()
        hub = _mock_hub()
        db.db.counters.find_one_and_update = AsyncMock(return_value={"seq": 10})
        svc = OfficerStatusService(db, hub)

        location = {"street": "Del Perro Blvd", "landmark": "Pier", "coordinates": {"x": 1, "y": 2, "z": 3}}
        call = await svc.request_backup(location, "Officer needs assistance")

        assert call["priority"] == 1
        assert call["type"] == "backup_request"
        assert call["status"] == CallStatus.PENDING.value
        assert call["location"]["street"] == "Del Perro Blvd"
        db.audited_insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcasts_to_all_units(self):
        db = _mock_db()
        hub = _mock_hub()
        db.db.counters.find_one_and_update = AsyncMock(return_value={"seq": 11})
        svc = OfficerStatusService(db, hub)

        await svc.request_backup({"street": "Main St"})

        hub.broadcast.assert_awaited_once()
        msg = hub.broadcast.await_args.args[0]
        assert msg["type"] == "call_update"
        assert msg["call"]["priority"] == 1

    @pytest.mark.asyncio
    async def test_call_number_auto_increments(self):
        db = _mock_db()
        hub = _mock_hub()
        db.db.counters.find_one_and_update = AsyncMock(return_value={"seq": 42})
        svc = OfficerStatusService(db, hub)

        call = await svc.request_backup({"street": "Elm St"})
        assert call["call_number"].endswith("-0042")


# ===========================================================================
# Task 6.7 — BOLOService
# ===========================================================================


class TestBOLOService:
    """create_bolo persists and broadcasts BOLO alerts."""

    @pytest.mark.asyncio
    async def test_creates_active_bolo(self):
        db = _mock_db()
        hub = _mock_hub()
        svc = BOLOService(db, hub)

        bolo = await svc.create_bolo(
            description="White sedan, broken taillight",
            issuing_officer="1-Adam-12",
            suspect_description="Male, 6ft, black hoodie",
            vehicle_description="2015 white Honda Civic",
        )

        assert bolo["status"] == BOLOStatus.ACTIVE.value
        assert bolo["description"] == "White sedan, broken taillight"
        assert bolo["suspect_description"] == "Male, 6ft, black hoodie"
        assert bolo["vehicle_description"] == "2015 white Honda Civic"
        assert bolo["issuing_officer"] == "1-Adam-12"
        db.audited_insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcasts_bolo_alert_to_cad(self):
        db = _mock_db()
        hub = _mock_hub()
        svc = BOLOService(db, hub)

        await svc.create_bolo(
            description="Suspect on foot",
            issuing_officer="2-Tom-7",
        )

        hub.send_to.assert_awaited_once()
        args = hub.send_to.await_args
        assert args.args[0] == "cad"
        msg = args.args[1]
        assert msg["type"] == "bolo_alert"
        bolo = msg["bolo"]
        assert bolo["description"] == "Suspect on foot"
        assert bolo["issuing_officer"] == "2-Tom-7"
        assert bolo["status"] == "active"
        assert bolo["suspect_description"] is None
        assert bolo["vehicle_description"] is None
        assert "_id" in bolo
        assert "created_at" in bolo
        assert "updated_at" in bolo

    @pytest.mark.asyncio
    async def test_bolo_alert_message_structure(self):
        db = _mock_db()
        hub = _mock_hub()
        svc = BOLOService(db, hub)

        await svc.create_bolo(description="Test BOLO", issuing_officer="Unit-1")

        hub.send_to.assert_awaited_once()
        args = hub.send_to.await_args
        assert args.args[0] == "cad"
        msg = args.args[1]
        assert msg["type"] == "bolo_alert"
        assert "bolo" in msg
        assert msg["bolo"]["status"] == "active"

    @pytest.mark.asyncio
    async def test_optional_fields_default_to_none(self):
        db = _mock_db()
        hub = _mock_hub()
        svc = BOLOService(db, hub)

        bolo = await svc.create_bolo(
            description="Minimal BOLO",
            issuing_officer="Unit-1",
        )

        assert bolo["suspect_description"] is None
        assert bolo["vehicle_description"] is None


# ===========================================================================
# Task 6.9 — WarrantService
# ===========================================================================


class _FakeCursor:
    """Minimal async cursor mock."""

    def __init__(self, docs: list):
        self._docs = docs

    async def to_list(self, length: int = 100):
        return self._docs[:length]


class TestWarrantService:
    """check_warrants queries active warrants by person name."""

    @pytest.mark.asyncio
    async def test_returns_active_warrants(self):
        db = _mock_db()
        warrants = [
            {"_id": ObjectId(), "person_name": "John Doe", "charge": "Assault", "status": "active"},
            {"_id": ObjectId(), "person_name": "John Doe", "charge": "Theft", "status": "active"},
        ]
        db.db.warrants.find = MagicMock(return_value=_FakeCursor(warrants))
        svc = WarrantService(db)

        result = await svc.check_warrants("John Doe")

        assert len(result) == 2
        assert all(w["status"] == "active" for w in result)

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_warrants(self):
        db = _mock_db()
        db.db.warrants.find = MagicMock(return_value=_FakeCursor([]))
        svc = WarrantService(db)

        result = await svc.check_warrants("Jane Smith")
        assert result == []

    @pytest.mark.asyncio
    async def test_queries_with_case_insensitive_regex(self):
        db = _mock_db()
        captured_query = {}

        def fake_find(query):
            captured_query.update(query)
            return _FakeCursor([])

        db.db.warrants.find = MagicMock(side_effect=fake_find)
        svc = WarrantService(db)

        await svc.check_warrants("John Doe")

        assert "person_name" in captured_query
        assert captured_query["person_name"]["$options"] == "i"
        assert captured_query["status"] == WarrantStatus.ACTIVE.value

    @pytest.mark.asyncio
    async def test_escapes_special_regex_chars(self):
        db = _mock_db()
        captured_query = {}

        def fake_find(query):
            captured_query.update(query)
            return _FakeCursor([])

        db.db.warrants.find = MagicMock(side_effect=fake_find)
        svc = WarrantService(db)

        await svc.check_warrants("John (Doe)")

        # The parentheses should be escaped
        regex = captured_query["person_name"]["$regex"]
        assert "\\(" in regex
        assert "\\)" in regex
