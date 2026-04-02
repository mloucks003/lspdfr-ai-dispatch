"""AudioPlayback module - Output device management with squelch effect pipeline."""

from __future__ import annotations

import os
import random
import struct
import threading
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


# ---------------------------------------------------------------------------
# Squelch effect generation helpers
# ---------------------------------------------------------------------------

def _generate_noise(duration: float, amplitude: int, rate: int = RATE) -> bytes:
    """Generate random noise PCM bytes at the given amplitude."""
    n_samples = int(duration * rate)
    samples = [random.randint(-amplitude, amplitude) for _ in range(n_samples)]
    return struct.pack(f"<{n_samples}h", *samples)


def generate_click_on(rate: int = RATE) -> bytes:
    """Generate the click-on burst (short noise burst)."""
    return _generate_noise(CLICK_ON_DURATION, CLICK_AMPLITUDE, rate)


def generate_static(rate: int = RATE) -> bytes:
    """Generate low-level static noise."""
    return _generate_noise(STATIC_DURATION, STATIC_AMPLITUDE, rate)


def generate_click_off(rate: int = RATE) -> bytes:
    """Generate the click-off burst (short noise burst)."""
    return _generate_noise(CLICK_OFF_DURATION, CLICK_AMPLITUDE, rate)


def apply_squelch_effect(voice_audio: bytes, rate: int = RATE) -> bytes:
    """Wrap *voice_audio* with the squelch effect pipeline.

    Output order: click-on → static → voice → click-off

    The returned buffer is always longer than *voice_audio* (assuming
    voice_audio is non-empty) because of the prepended and appended frames.
    """
    click_on = generate_click_on(rate)
    static = generate_static(rate)
    click_off = generate_click_off(rate)
    return click_on + static + voice_audio + click_off


# ---------------------------------------------------------------------------
# AudioPlayback
# ---------------------------------------------------------------------------

class AudioPlayback:
    """Plays audio through the configured output device with squelch effects.

    Parameters
    ----------
    pyaudio_instance:
        An optional ``pyaudio.PyAudio`` instance (for DI / testing).
    apply_squelch:
        Whether to apply the squelch effect pipeline to played audio.
    rate:
        Sample rate (default 16 kHz).
    """

    def __init__(
        self,
        pyaudio_instance: object | None = None,
        apply_squelch: bool = True,
        rate: int = RATE,
    ) -> None:
        self._pa = pyaudio_instance
        self._apply_squelch = apply_squelch
        self._rate = rate
        self._lock = threading.Lock()

    def play(self, voice_audio: bytes) -> None:
        """Play *voice_audio* through the output device.

        If squelch is enabled the audio is wrapped with click-on, static,
        and click-off frames before playback.
        """
        if not voice_audio:
            return

        audio = apply_squelch_effect(voice_audio, self._rate) if self._apply_squelch else voice_audio
        self._play_raw(audio)

    def _play_raw(self, pcm_data: bytes) -> None:
        """Write raw PCM data to a PyAudio output stream."""
        try:
            import pyaudio as _pa

            with self._lock:
                if self._pa is None:
                    self._pa = _pa.PyAudio()

                stream = self._pa.open(  # type: ignore[union-attr]
                    format=_pa.paInt16,
                    channels=CHANNELS,
                    rate=self._rate,
                    output=True,
                )
                try:
                    stream.write(pcm_data)
                finally:
                    stream.stop_stream()
                    stream.close()
        except Exception:
            # Output device unavailable – silently skip.
            pass
