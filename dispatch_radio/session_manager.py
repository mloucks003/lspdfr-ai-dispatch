"""SessionManager - Tracks active/passive listening state with silence timeout."""

from __future__ import annotations

import enum
import struct
import time
import threading
from typing import Callable

from dispatch_radio.audio_capture import FORMAT_WIDTH


class SessionState(enum.Enum):
    PASSIVE = "passive"
    ACTIVE = "active"


class SessionManager:
    """Simple state machine: PASSIVE → ACTIVE (on wake word) → PASSIVE (on silence).

    Parameters
    ----------
    silence_timeout:
        Seconds of silence before an active session ends (default 2.0).
    silence_threshold:
        RMS energy below which audio is considered silence.
    on_session_start:
        Callback fired when transitioning to ACTIVE.
    on_session_end:
        Callback fired when transitioning back to PASSIVE.
    """

    def __init__(
        self,
        silence_timeout: float = 2.0,
        silence_threshold: float = 500.0,
        on_session_start: Callable[[], None] | None = None,
        on_session_end: Callable[[], None] | None = None,
    ) -> None:
        self._silence_timeout = silence_timeout
        self._silence_threshold = silence_threshold
        self._on_session_start = on_session_start
        self._on_session_end = on_session_end

        self._state = SessionState.PASSIVE
        self._last_voice_time: float | None = None
        self._lock = threading.Lock()

    # -- properties ---------------------------------------------------------

    @property
    def state(self) -> SessionState:
        with self._lock:
            return self._state

    @property
    def silence_timeout(self) -> float:
        return self._silence_timeout

    # -- public API ---------------------------------------------------------

    def activate(self) -> None:
        """Transition to ACTIVE state (called when wake word detected)."""
        with self._lock:
            if self._state == SessionState.PASSIVE:
                self._state = SessionState.ACTIVE
                self._last_voice_time = time.monotonic()
                if self._on_session_start is not None:
                    self._on_session_start()

    def feed_audio(self, pcm_chunk: bytes) -> None:
        """Feed an audio chunk while in ACTIVE state.

        Updates the last-voice timestamp if the chunk contains speech.
        If silence has exceeded the timeout, transitions back to PASSIVE.
        """
        with self._lock:
            if self._state != SessionState.ACTIVE:
                return

            if self._chunk_has_voice(pcm_chunk):
                self._last_voice_time = time.monotonic()
            else:
                if self._last_voice_time is not None:
                    elapsed = time.monotonic() - self._last_voice_time
                    if elapsed >= self._silence_timeout:
                        self._state = SessionState.PASSIVE
                        self._last_voice_time = None
                        if self._on_session_end is not None:
                            self._on_session_end()

    def check_timeout(self) -> bool:
        """Explicitly check whether the silence timeout has been exceeded.

        Returns True if the session was ended by this check.
        """
        with self._lock:
            if self._state != SessionState.ACTIVE:
                return False
            if self._last_voice_time is None:
                return False
            elapsed = time.monotonic() - self._last_voice_time
            if elapsed >= self._silence_timeout:
                self._state = SessionState.PASSIVE
                self._last_voice_time = None
                if self._on_session_end is not None:
                    self._on_session_end()
                return True
            return False

    def reset(self) -> None:
        """Force-reset to PASSIVE state."""
        with self._lock:
            self._state = SessionState.PASSIVE
            self._last_voice_time = None

    # -- internals ----------------------------------------------------------

    def _chunk_has_voice(self, pcm_chunk: bytes) -> bool:
        if len(pcm_chunk) < FORMAT_WIDTH:
            return False
        n_samples = len(pcm_chunk) // FORMAT_WIDTH
        samples = struct.unpack(f"<{n_samples}h", pcm_chunk[: n_samples * FORMAT_WIDTH])
        rms = (sum(s * s for s in samples) / n_samples) ** 0.5
        return rms >= self._silence_threshold
