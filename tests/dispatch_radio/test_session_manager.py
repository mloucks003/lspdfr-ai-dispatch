"""Tests for dispatch_radio.session_manager module."""

import struct
import time
from unittest.mock import MagicMock

import pytest

from dispatch_radio.session_manager import SessionManager, SessionState
from dispatch_radio.audio_capture import CHUNK, FORMAT_WIDTH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pcm(amplitude: int, n_samples: int = CHUNK) -> bytes:
    return struct.pack(f"<{n_samples}h", *([amplitude] * n_samples))


def _silent_pcm() -> bytes:
    return _make_pcm(0)


def _loud_pcm() -> bytes:
    return _make_pcm(5000)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSessionManager:
    def test_initial_state_is_passive(self):
        sm = SessionManager()
        assert sm.state == SessionState.PASSIVE

    def test_activate_transitions_to_active(self):
        sm = SessionManager()
        sm.activate()
        assert sm.state == SessionState.ACTIVE

    def test_activate_fires_callback(self):
        cb = MagicMock()
        sm = SessionManager(on_session_start=cb)
        sm.activate()
        cb.assert_called_once()

    def test_activate_when_already_active_is_noop(self):
        cb = MagicMock()
        sm = SessionManager(on_session_start=cb)
        sm.activate()
        sm.activate()  # second call should be ignored
        cb.assert_called_once()

    def test_silence_timeout_transitions_to_passive(self):
        end_cb = MagicMock()
        sm = SessionManager(
            silence_timeout=0.1,
            silence_threshold=500.0,
            on_session_end=end_cb,
        )
        sm.activate()
        assert sm.state == SessionState.ACTIVE

        # Feed silence and wait for timeout
        time.sleep(0.15)
        sm.feed_audio(_silent_pcm())

        assert sm.state == SessionState.PASSIVE
        end_cb.assert_called_once()

    def test_voice_resets_silence_timer(self):
        sm = SessionManager(silence_timeout=0.2, silence_threshold=500.0)
        sm.activate()

        # Feed voice – should keep session alive
        time.sleep(0.1)
        sm.feed_audio(_loud_pcm())

        # Still active because voice was detected
        assert sm.state == SessionState.ACTIVE

    def test_check_timeout_returns_true_when_expired(self):
        sm = SessionManager(silence_timeout=0.05)
        sm.activate()
        time.sleep(0.1)
        assert sm.check_timeout() is True
        assert sm.state == SessionState.PASSIVE

    def test_check_timeout_returns_false_when_not_expired(self):
        sm = SessionManager(silence_timeout=10.0)
        sm.activate()
        assert sm.check_timeout() is False
        assert sm.state == SessionState.ACTIVE

    def test_reset_forces_passive(self):
        sm = SessionManager()
        sm.activate()
        assert sm.state == SessionState.ACTIVE
        sm.reset()
        assert sm.state == SessionState.PASSIVE

    def test_feed_audio_in_passive_is_noop(self):
        sm = SessionManager()
        # Should not raise
        sm.feed_audio(_loud_pcm())
        assert sm.state == SessionState.PASSIVE

    def test_configurable_silence_timeout(self):
        sm = SessionManager(silence_timeout=5.0)
        assert sm.silence_timeout == 5.0

    def test_session_end_callback_fires_on_timeout(self):
        end_cb = MagicMock()
        sm = SessionManager(
            silence_timeout=0.05,
            on_session_end=end_cb,
        )
        sm.activate()
        time.sleep(0.1)
        sm.check_timeout()
        end_cb.assert_called_once()
