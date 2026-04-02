"""Unit tests for OpenAI Realtime API integration modules.

Covers:
- SystemPromptBuilder (Task 9.4)
- FunctionRegistry (Task 9.2)
- calculate_backoff (Task 9.6)
- OpenAIRealtimeClient basics (Task 9.1)
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.function_registry import FunctionRegistry, TOOL_DEFINITIONS
from backend.services.openai_client import OpenAIRealtimeClient, calculate_backoff
from backend.services.system_prompt import SystemPromptBuilder


# ======================================================================
# SystemPromptBuilder tests (Task 9.4)
# ======================================================================


class TestSystemPromptBuilder:
    """Tests for SystemPromptBuilder."""

    def setup_method(self):
        self.builder = SystemPromptBuilder()

    def test_prompt_contains_10_codes(self):
        prompt = self.builder.build(callsign="1-Adam-12")
        assert "10-code" in prompt.lower() or "10-" in prompt

    def test_prompt_contains_radio_brevity(self):
        prompt = self.builder.build(callsign="1-Adam-12")
        assert "brevity" in prompt.lower()

    def test_prompt_contains_dispatcher_tone(self):
        prompt = self.builder.build(callsign="1-Adam-12")
        assert "dispatcher" in prompt.lower() or "professional" in prompt.lower()

    def test_prompt_contains_callsign(self):
        prompt = self.builder.build(callsign="2-Lincoln-30")
        assert "2-Lincoln-30" in prompt

    def test_prompt_contains_gta_v_awareness(self):
        prompt = self.builder.build(callsign="1-Adam-12")
        assert "Los Santos" in prompt
        assert "GTA V" in prompt or "GTA" in prompt

    def test_prompt_includes_location_context(self):
        prompt = self.builder.build(
            callsign="1-Adam-12",
            location_context="Vinewood Boulevard",
        )
        assert "Vinewood Boulevard" in prompt

    def test_prompt_without_location_context(self):
        prompt = self.builder.build(callsign="1-Adam-12")
        # Should not crash and should still be a valid prompt
        assert len(prompt) > 100

    def test_prompt_mentions_function_calling(self):
        prompt = self.builder.build(callsign="1-Adam-12")
        assert "plate_check" in prompt or "function" in prompt.lower()


# ======================================================================
# FunctionRegistry tests (Task 9.2)
# ======================================================================


class TestFunctionRegistry:
    """Tests for FunctionRegistry tool definitions and dispatch."""

    def setup_method(self):
        self.plate_svc = MagicMock()
        self.name_svc = MagicMock()
        self.warrant_svc = MagicMock()
        self.officer_svc = MagicMock()
        self.bolo_svc = MagicMock()

        self.registry = FunctionRegistry(
            plate_check_service=self.plate_svc,
            name_check_service=self.name_svc,
            warrant_service=self.warrant_svc,
            officer_status_service=self.officer_svc,
            bolo_service=self.bolo_svc,
            default_callsign="1-Adam-12",
        )

    def test_tool_definitions_has_all_functions(self):
        defs = FunctionRegistry.get_tool_definitions()
        names = {d["name"] for d in defs}
        expected = {
            "plate_check",
            "name_check",
            "warrant_check",
            "update_officer_status",
            "request_backup",
            "create_bolo",
            "assign_call",
        }
        assert names == expected

    def test_tool_definitions_have_required_fields(self):
        for defn in TOOL_DEFINITIONS:
            assert "type" in defn
            assert "name" in defn
            assert "description" in defn
            assert "parameters" in defn
            assert defn["type"] == "function"

    @pytest.mark.asyncio
    async def test_dispatch_plate_check(self):
        self.plate_svc.check_plate = AsyncMock(return_value={"plate": "ABC123"})
        result = await self.registry.dispatch("plate_check", {"plate": "ABC123"})
        self.plate_svc.check_plate.assert_awaited_once_with("ABC123")
        assert result == {"plate": "ABC123"}

    @pytest.mark.asyncio
    async def test_dispatch_name_check(self):
        self.name_svc.check_name = AsyncMock(return_value={"name": "John Doe"})
        result = await self.registry.dispatch("name_check", {"name": "John Doe"})
        self.name_svc.check_name.assert_awaited_once_with("John Doe")
        assert result == {"name": "John Doe"}

    @pytest.mark.asyncio
    async def test_dispatch_warrant_check(self):
        self.warrant_svc.check_warrants = AsyncMock(return_value=[])
        result = await self.registry.dispatch("warrant_check", {"name": "Jane Doe"})
        self.warrant_svc.check_warrants.assert_awaited_once_with("Jane Doe")
        assert result == []

    @pytest.mark.asyncio
    async def test_dispatch_update_officer_status(self):
        self.officer_svc.update_status = AsyncMock(return_value={"status": "10-8"})
        result = await self.registry.dispatch(
            "update_officer_status",
            {"callsign": "1-Adam-12", "status_code": "10-8"},
        )
        self.officer_svc.update_status.assert_awaited_once_with("1-Adam-12", "10-8")
        assert result == {"status": "10-8"}

    @pytest.mark.asyncio
    async def test_dispatch_request_backup(self):
        self.officer_svc.request_backup = AsyncMock(return_value={"call_number": "2025-0001"})
        result = await self.registry.dispatch(
            "request_backup",
            {"location": "Vinewood Blvd", "details": "Shots fired"},
        )
        self.officer_svc.request_backup.assert_awaited_once_with(
            {"street": "Vinewood Blvd"},
            "Shots fired",
        )
        assert result["call_number"] == "2025-0001"

    @pytest.mark.asyncio
    async def test_dispatch_create_bolo(self):
        self.bolo_svc.create_bolo = AsyncMock(return_value={"status": "active"})
        result = await self.registry.dispatch(
            "create_bolo",
            {"description": "Red sedan", "suspect_desc": "Male, 6ft"},
        )
        self.bolo_svc.create_bolo.assert_awaited_once_with(
            description="Red sedan",
            issuing_officer="1-Adam-12",
            suspect_description="Male, 6ft",
            vehicle_description=None,
        )
        assert result == {"status": "active"}

    @pytest.mark.asyncio
    async def test_dispatch_assign_call(self):
        self.officer_svc.assign_call = AsyncMock(return_value={"status": "dispatched"})
        result = await self.registry.dispatch(
            "assign_call",
            {"call_id": "abc123", "callsign": "1-Adam-12"},
        )
        self.officer_svc.assign_call.assert_awaited_once_with("abc123", "1-Adam-12")
        assert result == {"status": "dispatched"}

    @pytest.mark.asyncio
    async def test_dispatch_unknown_function_raises(self):
        with pytest.raises(ValueError, match="Unknown function"):
            await self.registry.dispatch("nonexistent", {})


# ======================================================================
# Exponential backoff tests (Task 9.6)
# ======================================================================


class TestExponentialBackoff:
    """Tests for calculate_backoff."""

    def test_zero_failures(self):
        assert calculate_backoff(0) == 1  # 2^0 = 1

    def test_one_failure(self):
        assert calculate_backoff(1) == 2  # 2^1 = 2

    def test_two_failures(self):
        assert calculate_backoff(2) == 4  # 2^2 = 4

    def test_five_failures(self):
        assert calculate_backoff(5) == 32  # 2^5 = 32

    def test_six_failures_hits_cap(self):
        assert calculate_backoff(6) == 60  # 2^6 = 64, capped at 60

    def test_large_failure_count_capped(self):
        assert calculate_backoff(100) == 60

    def test_backoff_is_monotonically_nondecreasing(self):
        values = [calculate_backoff(n) for n in range(20)]
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]


# ======================================================================
# OpenAIRealtimeClient tests (Task 9.1)
# ======================================================================


class TestOpenAIRealtimeClient:
    """Tests for OpenAIRealtimeClient."""

    def setup_method(self):
        self.hub = MagicMock()
        self.hub.send_to = AsyncMock()
        self.registry = MagicMock(spec=FunctionRegistry)
        self.registry.get_tool_definitions = MagicMock(return_value=[])
        self.registry.dispatch = AsyncMock(return_value={"ok": True})
        self.prompt_builder = SystemPromptBuilder()

        self.client = OpenAIRealtimeClient(
            api_key="test-key",
            hub=self.hub,
            function_registry=self.registry,
            prompt_builder=self.prompt_builder,
            callsign="1-Adam-12",
        )

    def test_initial_state(self):
        assert not self.client.connected
        assert self.client.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_send_audio_when_not_connected(self):
        """send_audio should not raise when not connected."""
        await self.client.send_audio("base64data")
        # No exception means success — it just logs a warning

    @pytest.mark.asyncio
    async def test_handle_audio_delta_forwards_to_radio(self):
        message = {
            "type": "response.audio.delta",
            "delta": "base64audiodata",
        }
        await self.client._handle_message(message)
        self.hub.send_to.assert_awaited_once_with("radio", {
            "type": "audio_response",
            "data": "base64audiodata",
        })

    @pytest.mark.asyncio
    async def test_handle_function_call(self):
        self.client._ws = AsyncMock()
        self.client._connected = True

        message = {
            "type": "response.function_call_arguments.done",
            "call_id": "call_123",
            "name": "plate_check",
            "arguments": '{"plate": "ABC123"}',
        }
        await self.client._handle_message(message)

        self.registry.dispatch.assert_awaited_once_with("plate_check", {"plate": "ABC123"})
        # Should have sent two messages: function result + response.create
        assert self.client._ws.send.await_count == 2

    @pytest.mark.asyncio
    async def test_handle_function_call_error(self):
        """Function call errors should be sent back as error results."""
        self.client._ws = AsyncMock()
        self.client._connected = True
        self.registry.dispatch = AsyncMock(side_effect=ValueError("bad input"))

        message = {
            "type": "response.function_call_arguments.done",
            "call_id": "call_456",
            "name": "plate_check",
            "arguments": '{"plate": "XYZ"}',
        }
        await self.client._handle_message(message)

        # Should still send the error result back
        sent_data = self.client._ws.send.call_args_list[0][0][0]
        parsed = json.loads(sent_data)
        assert "error" in parsed["item"]["output"]

    @pytest.mark.asyncio
    async def test_disconnect(self):
        self.client._ws = AsyncMock()
        self.client._connected = True
        await self.client.disconnect()
        assert not self.client.connected
