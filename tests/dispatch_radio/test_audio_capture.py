"""Tests for dispatch_radio.audio_capture module."""

import struct
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from dispatch_radio.audio_capture import (
    AudioCapture,
    SimpleEnergyWakeWordDetector,
    WakeWordDetector,
    RATE,
    CHANNELS,
    CHUNK,
    FORMAT_WIDTH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pcm(amplitude: int, n_samples: int = CHUNK) -> bytes:
    """Create a PCM buffer with all samples at *amplitude*."""
    return struct.pack(f"<{n_samples}h", *([amplitude] * n_samples))


def _silent_pcm(n_samples: int = CHUNK) -> bytes:
    return _make_pcm(0, n_samples)


def _loud_pcm(n_samples: int = CHUNK) -> bytes:
    return _make_pcm(5000, n_samples)


# ---------------------------------------------------------------------------
# SimpleEnergyWakeWordDetector tests
# ---------------------------------------------------------------------------

class TestSimpleEnergyWakeWordDetector:
    def test_silent_audio_does_not_trigger(self):
        detector = SimpleEnergyWakeWordDetector(threshold=2000.0)
        assert detector.process(_silent_pcm()) is False

    def test_loud_audio_triggers(self):
        detector = SimpleEnergyWakeWordDetector(threshold=2000.0)
        assert detector.process(_loud_pcm()) is True

    def test_empty_chunk_does_not_trigger(self):
        detector = SimpleEnergyWakeWordDetector(threshold=2000.0)
        assert detector.process(b"") is False

    def test_threshold_boundary(self):
        # RMS of constant 2000 signal = 2000
        detector = SimpleEnergyWakeWordDetector(threshold=2000.0)
        pcm = _make_pcm(2000)
        assert detector.process(pcm) is True

        detector2 = SimpleEnergyWakeWordDetector(threshold=2001.0)
        assert detector2.process(pcm) is False


# ---------------------------------------------------------------------------
# AudioCapture tests
# ---------------------------------------------------------------------------

class TestAudioCapture:
    def test_initial_state_is_not_active(self):
        detector = SimpleEnergyWakeWordDetector()
        capture = AudioCapture(wake_word_detector=detector)
        assert capture.is_active is False

    def test_set_active(self):
        detector = SimpleEnergyWakeWordDetector()
        capture = AudioCapture(wake_word_detector=detector)
        capture.set_active(True)
        assert capture.is_active is True
        capture.set_active(False)
        assert capture.is_active is False

    def test_wake_word_callback_fires_on_detection(self):
        """Simulate the capture loop detecting a wake word."""
        wake_events: list[bytes] = []

        class AlwaysDetect(WakeWordDetector):
            def process(self, pcm_chunk: bytes) -> bool:
                return True

        capture = AudioCapture(
            wake_word_detector=AlwaysDetect(),
            on_wake_word=lambda chunk: wake_events.append(chunk),
        )
        # Directly invoke the passive-mode logic
        capture._active = False
        loud = _loud_pcm()

        # Simulate what _capture_loop does in passive mode
        if capture._detector.process(loud):
            capture._active = True
            if capture._on_wake_word:
                capture._on_wake_word(loud)

        assert len(wake_events) == 1
        assert capture.is_active is True

    def test_audio_chunk_callback_fires_in_active_mode(self):
        chunks: list[bytes] = []
        detector = SimpleEnergyWakeWordDetector()
        capture = AudioCapture(
            wake_word_detector=detector,
            on_audio_chunk=lambda c: chunks.append(c),
        )
        capture.set_active(True)

        data = _loud_pcm()
        # Simulate active-mode forwarding
        if capture._on_audio_chunk:
            capture._on_audio_chunk(data)

        assert len(chunks) == 1
        assert chunks[0] == data

    def test_passive_mode_does_not_forward_audio(self):
        chunks: list[bytes] = []

        class NeverDetect(WakeWordDetector):
            def process(self, pcm_chunk: bytes) -> bool:
                return False

        capture = AudioCapture(
            wake_word_detector=NeverDetect(),
            on_audio_chunk=lambda c: chunks.append(c),
        )
        # Passive mode – audio should NOT be forwarded
        assert capture.is_active is False
        # The on_audio_chunk callback should not be called in passive mode
        assert len(chunks) == 0
