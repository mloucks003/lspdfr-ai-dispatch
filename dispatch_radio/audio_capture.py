"""AudioCapture module - Continuous mic input with wake word detection."""

from __future__ import annotations

import abc
import struct
import threading
import time
from typing import Callable, Protocol


# ---------------------------------------------------------------------------
# Audio constants
# ---------------------------------------------------------------------------
RATE = 16000  # 16 kHz sample rate
CHANNELS = 1
CHUNK = 1024  # frames per buffer (~64 ms at 16 kHz)
FORMAT_WIDTH = 2  # 16-bit PCM → 2 bytes per sample


# ---------------------------------------------------------------------------
# Wake-word detector interface
# ---------------------------------------------------------------------------
class WakeWordDetector(abc.ABC):
    """Abstract interface for wake-word detection backends."""

    @abc.abstractmethod
    def process(self, pcm_chunk: bytes) -> bool:
        """Return *True* when the wake word is detected in *pcm_chunk*."""
        ...


class SimpleEnergyWakeWordDetector(WakeWordDetector):
    """Minimal energy-threshold detector used as a default / fallback.

    This is a *placeholder* implementation.  In production you would swap in
    pvporcupine or another keyword-spotting engine.  The detector fires when
    the RMS energy of a chunk exceeds *threshold*.
    """

    def __init__(self, threshold: float = 2000.0) -> None:
        self.threshold = threshold

    def process(self, pcm_chunk: bytes) -> bool:
        if len(pcm_chunk) < FORMAT_WIDTH:
            return False
        n_samples = len(pcm_chunk) // FORMAT_WIDTH
        samples = struct.unpack(f"<{n_samples}h", pcm_chunk[: n_samples * FORMAT_WIDTH])
        rms = (sum(s * s for s in samples) / n_samples) ** 0.5
        return rms >= self.threshold


# ---------------------------------------------------------------------------
# Callback type
# ---------------------------------------------------------------------------
OnAudioChunk = Callable[[bytes], None]


# ---------------------------------------------------------------------------
# AudioCapture
# ---------------------------------------------------------------------------
class AudioCapture:
    """Continuously captures audio from the default microphone.

    Parameters
    ----------
    wake_word_detector:
        Pluggable detector that decides when the wake word is spoken.
    on_wake_word:
        Called (with the triggering chunk) when the wake word is detected.
    on_audio_chunk:
        Called with every raw PCM chunk while in *active* mode so the
        caller can forward audio to the backend.
    pyaudio_instance:
        An optional ``pyaudio.PyAudio`` instance (for dependency injection /
        testing).  If *None*, one will be created internally.
    retry_interval:
        Seconds between retries when the microphone is unavailable.
    """

    def __init__(
        self,
        wake_word_detector: WakeWordDetector,
        on_wake_word: Callable[[bytes], None] | None = None,
        on_audio_chunk: OnAudioChunk | None = None,
        pyaudio_instance: object | None = None,
        retry_interval: float = 5.0,
    ) -> None:
        self._detector = wake_word_detector
        self._on_wake_word = on_wake_word
        self._on_audio_chunk = on_audio_chunk
        self._pa = pyaudio_instance
        self._retry_interval = retry_interval

        self._stream: object | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._active = False  # True while in active command-processing mode

    # -- public API ---------------------------------------------------------

    @property
    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = active

    def start(self) -> None:
        """Start capturing in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the capture loop to stop and wait for the thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._close_stream()

    # -- internals ----------------------------------------------------------

    def _open_stream(self) -> bool:
        """Try to open a PyAudio input stream.  Returns True on success."""
        try:
            import pyaudio as _pa

            if self._pa is None:
                self._pa = _pa.PyAudio()

            self._stream = self._pa.open(  # type: ignore[union-attr]
                format=_pa.paInt16,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
            )
            return True
        except Exception:
            return False

    def _close_stream(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop_stream()  # type: ignore[union-attr]
                self._stream.close()  # type: ignore[union-attr]
            except Exception:
                pass
            self._stream = None

    def _capture_loop(self) -> None:
        while self._running:
            # Ensure we have an open stream; retry on failure.
            if self._stream is None:
                if not self._open_stream():
                    time.sleep(self._retry_interval)
                    continue

            try:
                data: bytes = self._stream.read(CHUNK, exception_on_overflow=False)  # type: ignore[union-attr]
            except Exception:
                self._close_stream()
                continue

            if self._active:
                # Forward audio while in active mode.
                if self._on_audio_chunk is not None:
                    self._on_audio_chunk(data)
            else:
                # Passive mode – check for wake word.
                if self._detector.process(data):
                    self._active = True
                    if self._on_wake_word is not None:
                        self._on_wake_word(data)
