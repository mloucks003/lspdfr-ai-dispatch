"""Tests for dispatch_radio.audio_playback module."""

import struct

import pytest

from dispatch_radio.audio_playback import (
    apply_squelch_effect,
    generate_click_on,
    generate_click_off,
    generate_static,
    CLICK_ON_DURATION,
    CLICK_OFF_DURATION,
    STATIC_DURATION,
    CLICK_AMPLITUDE,
    STATIC_AMPLITUDE,
    AudioPlayback,
)
from dispatch_radio.audio_capture import RATE, FORMAT_WIDTH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_voice(duration: float = 0.5, rate: int = RATE) -> bytes:
    """Create a simple voice-like PCM buffer (sine-ish constant tone)."""
    n_samples = int(duration * rate)
    return struct.pack(f"<{n_samples}h", *([3000] * n_samples))


# ---------------------------------------------------------------------------
# Squelch effect generation tests
# ---------------------------------------------------------------------------

class TestSquelchGeneration:
    def test_click_on_length(self):
        data = generate_click_on()
        expected_samples = int(CLICK_ON_DURATION * RATE)
        assert len(data) == expected_samples * FORMAT_WIDTH

    def test_click_off_length(self):
        data = generate_click_off()
        expected_samples = int(CLICK_OFF_DURATION * RATE)
        assert len(data) == expected_samples * FORMAT_WIDTH

    def test_static_length(self):
        data = generate_static()
        expected_samples = int(STATIC_DURATION * RATE)
        assert len(data) == expected_samples * FORMAT_WIDTH

    def test_click_on_amplitude_within_bounds(self):
        data = generate_click_on()
        n = len(data) // FORMAT_WIDTH
        samples = struct.unpack(f"<{n}h", data)
        for s in samples:
            assert -CLICK_AMPLITUDE <= s <= CLICK_AMPLITUDE

    def test_static_amplitude_within_bounds(self):
        data = generate_static()
        n = len(data) // FORMAT_WIDTH
        samples = struct.unpack(f"<{n}h", data)
        for s in samples:
            assert -STATIC_AMPLITUDE <= s <= STATIC_AMPLITUDE


# ---------------------------------------------------------------------------
# apply_squelch_effect tests
# ---------------------------------------------------------------------------

class TestApplySquelchEffect:
    def test_output_longer_than_input(self):
        voice = _make_voice()
        result = apply_squelch_effect(voice)
        assert len(result) > len(voice)

    def test_voice_audio_present_in_output(self):
        voice = _make_voice()
        result = apply_squelch_effect(voice)
        assert voice in result

    def test_structure_click_on_then_static_then_voice_then_click_off(self):
        voice = _make_voice(duration=0.1)
        result = apply_squelch_effect(voice)

        click_on_len = int(CLICK_ON_DURATION * RATE) * FORMAT_WIDTH
        static_len = int(STATIC_DURATION * RATE) * FORMAT_WIDTH
        click_off_len = int(CLICK_OFF_DURATION * RATE) * FORMAT_WIDTH

        expected_len = click_on_len + static_len + len(voice) + click_off_len
        assert len(result) == expected_len

        # Voice should start after click_on + static
        voice_start = click_on_len + static_len
        voice_end = voice_start + len(voice)
        assert result[voice_start:voice_end] == voice

    def test_empty_voice_returns_only_effects(self):
        # Empty voice → still get click-on + static + click-off
        result = apply_squelch_effect(b"")
        click_on_len = int(CLICK_ON_DURATION * RATE) * FORMAT_WIDTH
        static_len = int(STATIC_DURATION * RATE) * FORMAT_WIDTH
        click_off_len = int(CLICK_OFF_DURATION * RATE) * FORMAT_WIDTH
        assert len(result) == click_on_len + static_len + click_off_len


# ---------------------------------------------------------------------------
# AudioPlayback tests
# ---------------------------------------------------------------------------

class TestAudioPlayback:
    def test_play_empty_audio_is_noop(self):
        """Playing empty audio should not raise."""
        playback = AudioPlayback(apply_squelch=True)
        playback.play(b"")  # should not raise

    def test_play_with_squelch_disabled(self):
        """When squelch is disabled, audio should be passed through as-is."""
        played: list[bytes] = []

        playback = AudioPlayback(apply_squelch=False)
        # Monkey-patch _play_raw to capture output
        playback._play_raw = lambda data: played.append(data)

        voice = _make_voice(duration=0.1)
        playback.play(voice)

        assert len(played) == 1
        assert played[0] == voice

    def test_play_with_squelch_enabled(self):
        """When squelch is enabled, output should be longer than input."""
        played: list[bytes] = []

        playback = AudioPlayback(apply_squelch=True)
        playback._play_raw = lambda data: played.append(data)

        voice = _make_voice(duration=0.1)
        playback.play(voice)

        assert len(played) == 1
        assert len(played[0]) > len(voice)
        # Voice should be embedded in the output
        assert voice in played[0]
