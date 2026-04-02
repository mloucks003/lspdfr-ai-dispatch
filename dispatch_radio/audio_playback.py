"""AudioPlayback module - Output device management with squelch effect pipeline.

Buffers incoming audio chunks and applies squelch effect only once per
complete response (not per chunk).
"""

from __future__ import annotations

import random
import struct
import threading
import time
from typing import Callable

from dispatch_radio.audio_capture import RATE, CHANNELS, FORMAT_WIDTH


# ---------------------------------------------------------------------------
# Squelch effect constants (durations in seconds)
# ---------------------------------------------------------------------------
CLICK_ON_DURATION = 0.05   # 50 ms click-on burst
STATIC_DURATION = 0.15     # 150 ms low-level static
CLICK_OFF_DURATION = 0.05  # 50 ms click-off burst

CLICK_AMPLITUDE = 12000    # amplitude for click bursts
STATIC_AMPLITUDE = 1500    # amplitude for background static

# OpenAI Realtime API sends audio at 24kHz
PLAYBACK_RATE = 24000

# How long to wait for more chunks before considering the response complete
RESPONSE_GAP_TIMEOUT = 0.4  # 400ms of no new chunks = response is done


# ---------------------------------------------------------------------------
# Squelch effect generation helpers
# ---------------------------------------------------------------------------

def _generate_noise(duration: float, amplitude: int, rate: int = RATE) -> bytes:
    """Generate random noise PCM bytes at the given amplitude."""
    n_samples = int(duration * rate)
    samples = [random.randint(-amplitude, amplitude) for _ in range(n_samples)]
    return struct.pack(f"<{n_samples}h", *samples)


def generate_click_on(rate: int = RATE) -> bytes:
    return _generate_noise(CLICK_ON_DURATION, CLICK_AMPLITUDE, rate)


def generate_static(rate: int = RATE) -> bytes:
    return _generate_noise(STATIC_DURATION, STATIC_AMPLITUDE, rate)


def generate_click_off(rate: int = RATE) -> bytes:
    return _generate_noise(CLICK_OFF_DURATION, CLICK_AMPLITUDE, rate)


def apply_squelch_effect(voice_audio: bytes, rate: int = RATE) -> bytes:
    """Wrap *voice_audio* with the squelch effect pipeline.
    Output order: click-on → static → voice → click-off
    """
    click_on = generate_click_on(rate)
    static = generate_static(rate)
    click_off = generate_click_off(rate)
    return click_on + static + voice_audio + click_off


# ---------------------------------------------------------------------------
# AudioPlayback with response buffering
# ---------------------------------------------------------------------------

class AudioPlayback:
    """Plays audio through the configured output device with squelch effects.

    Buffers incoming audio chunks and applies squelch only once per complete
    dispatcher response, not per individual chunk. This prevents the
    click-click-click effect from rapid small chunks.
    """

    def __init__(
        self,
        pyaudio_instance: object | None = None,
        apply_squelch: bool = True,
        rate: int = PLAYBACK_RATE,
    ) -> None:
        self._pa = pyaudio_instance
        self._apply_squelch = apply_squelch
        self._rate = rate
        self._lock = threading.Lock()
        self._stream = None

        # Response buffering
        self._buffer = bytearray()
        self._last_chunk_time = 0.0
        self._playing = False
        self._flush_thread: threading.Thread | None = None
        self._started_response = False

    def play(self, voice_audio: bytes) -> None:
        """Buffer an incoming audio chunk. Playback happens when the
        response is complete (no new chunks for RESPONSE_GAP_TIMEOUT)."""
        if not voice_audio:
            return

        with self._lock:
            # If this is the first chunk of a new response, play click-on immediately
            if not self._started_response:
                self._started_response = True
                if self._apply_squelch:
                    self._play_raw_immediate(generate_click_on(self._rate))
                    self._play_raw_immediate(generate_static(self._rate))

            # Buffer the voice audio and play it immediately (streaming)
            self._play_raw_immediate(voice_audio)
            self._last_chunk_time = time.monotonic()

        # Start/restart the flush timer to detect end of response
        if self._flush_thread is None or not self._flush_thread.is_alive():
            self._flush_thread = threading.Thread(target=self._watch_for_end, daemon=True)
            self._flush_thread.start()

    def _watch_for_end(self) -> None:
        """Background thread that waits for a gap in chunks, then plays click-off."""
        while True:
            time.sleep(0.1)
            with self._lock:
                if self._last_chunk_time == 0:
                    return
                elapsed = time.monotonic() - self._last_chunk_time
                if elapsed >= RESPONSE_GAP_TIMEOUT and self._started_response:
                    # Response is done — play click-off
                    if self._apply_squelch:
                        self._play_raw_immediate(generate_click_off(self._rate))
                    self._started_response = False
                    self._last_chunk_time = 0
                    self._close_stream()
                    return

    def _ensure_stream(self):
        """Open a persistent output stream if not already open."""
        if self._stream is not None:
            return
        try:
            import pyaudio as _pa
            if self._pa is None:
                self._pa = _pa.PyAudio()
            self._stream = self._pa.open(
                format=_pa.paInt16,
                channels=CHANNELS,
                rate=self._rate,
                output=True,
            )
        except Exception:
            self._stream = None

    def _close_stream(self):
        """Close the output stream."""
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _play_raw_immediate(self, pcm_data: bytes) -> None:
        """Write PCM data to the output stream immediately."""
        try:
            self._ensure_stream()
            if self._stream is not None:
                self._stream.write(pcm_data)
        except Exception:
            self._close_stream()

    # Keep the old _play_raw for compatibility with tests
    def _play_raw(self, pcm_data: bytes) -> None:
        with self._lock:
            self._play_raw_immediate(pcm_data)
