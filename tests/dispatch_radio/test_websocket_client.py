"""Tests for dispatch_radio.websocket_client module."""

import base64
import json

import pytest

from dispatch_radio.websocket_client import (
    RadioWebSocketClient,
    make_audio_chunk_message,
    make_status_update_message,
    parse_server_message,
)


# ---------------------------------------------------------------------------
# Message helper tests
# ---------------------------------------------------------------------------

class TestMessageHelpers:
    def test_make_audio_chunk_message(self):
        pcm = b"\x00\x01\x02\x03"
        msg = json.loads(make_audio_chunk_message(pcm))
        assert msg["type"] == "audio_chunk"
        assert base64.b64decode(msg["data"]) == pcm

    def test_make_status_update_listening(self):
        msg = json.loads(make_status_update_message("listening"))
        assert msg["type"] == "status_update"
        assert msg["status"] == "listening"

    def test_make_status_update_active(self):
        msg = json.loads(make_status_update_message("active"))
        assert msg["type"] == "status_update"
        assert msg["status"] == "active"

    def test_parse_server_message_audio_response(self):
        raw = json.dumps({"type": "audio_response", "data": base64.b64encode(b"hello").decode()})
        msg = parse_server_message(raw)
        assert msg["type"] == "audio_response"
        assert base64.b64decode(msg["data"]) == b"hello"

    def test_parse_server_message_call_announcement(self):
        call = {"call_number": "42", "type": "robbery", "priority": 1}
        raw = json.dumps({"type": "call_announcement", "call": call})
        msg = parse_server_message(raw)
        assert msg["type"] == "call_announcement"
        assert msg["call"]["call_number"] == "42"

    def test_parse_server_message_status_ack(self):
        raw = json.dumps({"type": "status_ack", "callsign": "1-Adam-12", "status": "10-76"})
        msg = parse_server_message(raw)
        assert msg["type"] == "status_ack"
        assert msg["callsign"] == "1-Adam-12"

    def test_parse_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            parse_server_message("not json")


# ---------------------------------------------------------------------------
# RadioWebSocketClient tests
# ---------------------------------------------------------------------------

class TestRadioWebSocketClient:
    def test_url_construction_with_api_key(self):
        client = RadioWebSocketClient(
            backend_url="ws://localhost:8000/ws/radio",
            api_key="test-key-123",
        )
        assert client.url == "ws://localhost:8000/ws/radio?api_key=test-key-123"

    def test_url_construction_with_existing_query_param(self):
        client = RadioWebSocketClient(
            backend_url="ws://localhost:8000/ws/radio?foo=bar",
            api_key="key",
        )
        assert client.url == "ws://localhost:8000/ws/radio?foo=bar&api_key=key"

    def test_initial_state_not_connected(self):
        client = RadioWebSocketClient()
        assert client.connected is False

    def test_handle_audio_response_message(self):
        received: list[bytes] = []
        client = RadioWebSocketClient(
            on_audio_response=lambda pcm: received.append(pcm),
        )
        pcm_data = b"\x00\x01\x02\x03"
        raw = json.dumps({
            "type": "audio_response",
            "data": base64.b64encode(pcm_data).decode(),
        })
        client._handle_message(raw)
        assert len(received) == 1
        assert received[0] == pcm_data

    def test_handle_call_announcement_message(self):
        received: list[dict] = []
        client = RadioWebSocketClient(
            on_call_announcement=lambda call: received.append(call),
        )
        call = {"call_number": "7", "type": "traffic_stop"}
        raw = json.dumps({"type": "call_announcement", "call": call})
        client._handle_message(raw)
        assert len(received) == 1
        assert received[0]["call_number"] == "7"

    def test_handle_status_ack_message(self):
        received: list[dict] = []
        client = RadioWebSocketClient(
            on_status_ack=lambda msg: received.append(msg),
        )
        raw = json.dumps({"type": "status_ack", "callsign": "1-Adam-12", "status": "10-8"})
        client._handle_message(raw)
        assert len(received) == 1
        assert received[0]["callsign"] == "1-Adam-12"

    def test_handle_unknown_message_type(self):
        """Unknown message types should not raise."""
        client = RadioWebSocketClient()
        raw = json.dumps({"type": "unknown_type", "data": "foo"})
        client._handle_message(raw)  # should not raise

    def test_handle_invalid_json(self):
        """Non-JSON messages should be handled gracefully."""
        client = RadioWebSocketClient()
        client._handle_message("not json at all")  # should not raise

    def test_reconnect_interval_default(self):
        client = RadioWebSocketClient()
        assert client._reconnect_interval == 10.0

    def test_reconnect_interval_custom(self):
        client = RadioWebSocketClient(reconnect_interval=5.0)
        assert client._reconnect_interval == 5.0
