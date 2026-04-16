"""
BlueLineDispatchPro — Scanner Mode
Plays background dispatch chatter at configurable random intervals.
"""
import logging
import random
import threading
import time
from pathlib import Path
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ScannerMode:
    """
    Continuously plays random scanner/dispatch audio in the background.
    Interval adapts based on active call count for realism.
    """

    def __init__(self, audio_player, audio_dir: Path, settings: Dict,
                 get_active_call_count: Optional[Callable[[], int]] = None):
        self.audio_player = audio_player
        self.audio_dir = audio_dir
        self.settings = settings
        self.get_active_call_count = get_active_call_count or (lambda: 0)

        self._active = False
        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._next_play_event = threading.Event()

    @property
    def scanner_settings(self) -> Dict:
        return self.settings.get("scanner_mode", {})

    @property
    def interval_min(self) -> float:
        return float(self.scanner_settings.get("interval_min_seconds", 25))

    @property
    def interval_max(self) -> float:
        return float(self.scanner_settings.get("interval_max_seconds", 90))

    @property
    def active_call_multiplier(self) -> float:
        """When active calls exist, reduce interval by this factor."""
        return float(self.scanner_settings.get("active_call_multiplier", 0.6))

    @property
    def pause_during_response(self) -> bool:
        return bool(self.scanner_settings.get("pause_during_response", True))

    def start(self) -> None:
        """Start the scanner background thread."""
        self._running = True
        self._active = bool(self.scanner_settings.get("enabled", False))
        self._thread = threading.Thread(
            target=self._scanner_loop, daemon=True, name="ScannerMode"
        )
        self._thread.start()
        logger.info(f"ScannerMode started ({'active' if self._active else 'standby'})")

    def stop(self) -> None:
        self._running = False
        self._next_play_event.set()  # unblock sleep
        if self._thread:
            self._thread.join(timeout=3)

    def set_active(self, active: bool) -> None:
        """Toggle scanner on/off."""
        self._active = active
        if active:
            self._next_play_event.set()  # trigger immediate evaluation
        logger.info(f"ScannerMode {'enabled' if active else 'disabled'}")

    @property
    def is_active(self) -> bool:
        return self._active

    def pause(self) -> None:
        """Pause scanner (e.g., during keyword response)."""
        self._paused = True

    def resume(self) -> None:
        """Resume scanner after pause."""
        self._paused = False

    def trigger_now(self) -> None:
        """Force an immediate scanner audio play (useful for testing)."""
        self._next_play_event.set()

    def _get_interval(self) -> float:
        """Calculate sleep interval based on active calls."""
        base = random.uniform(self.interval_min, self.interval_max)
        call_count = self.get_active_call_count()
        if call_count > 0:
            base = base * self.active_call_multiplier
        # Add slight jitter
        jitter = random.uniform(-2.0, 2.0)
        return max(5.0, base + jitter)

    def _pick_category(self) -> str:
        """Pick a scanner audio category weighted by call state."""
        call_count = self.get_active_call_count()
        if call_count > 2:
            # More urgent traffic when many active calls
            return random.choice(["scanner", "backup", "callout", "general", "chase"])
        elif call_count > 0:
            return random.choice(["scanner", "general", "acknowledgment", "scene", "callout"])
        else:
            return random.choice(["scanner", "general", "acknowledgment"])

    def _scanner_loop(self) -> None:
        """Main scanner loop: wait, then play random audio."""
        # Initial delay before first play
        self._next_play_event.wait(timeout=random.uniform(5, 15))
        self._next_play_event.clear()

        while self._running:
            if self._active and not self._paused:
                category = self._pick_category()
                played = self.audio_player.play_category(self.audio_dir, category)
                if not played:
                    # Fallback to scanner folder
                    self.audio_player.play_category(self.audio_dir, "scanner")

                interval = self._get_interval()
                logger.debug(f"ScannerMode: played '{category}', next in {interval:.1f}s")
            else:
                interval = 2.0  # Poll while inactive

            self._next_play_event.wait(timeout=interval)
            self._next_play_event.clear()
