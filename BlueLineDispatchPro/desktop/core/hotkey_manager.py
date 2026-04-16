"""
BlueLineDispatchPro — Global Hotkey Manager
Registers and handles system-wide hotkeys (F8/F9/F10/F11).
"""
import logging
import threading
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False
    logger.warning("keyboard library not available — hotkeys disabled")


class HotkeyManager:
    """
    Registers global hotkeys and fires callbacks.
    Designed to work even when the app window is not focused.
    """

    def __init__(self, settings: Dict,
                 on_toggle_listening: Optional[Callable] = None,
                 on_panic: Optional[Callable] = None,
                 on_toggle_scanner: Optional[Callable] = None,
                 on_mute: Optional[Callable] = None):
        self.settings = settings
        self.on_toggle_listening = on_toggle_listening
        self.on_panic = on_panic
        self.on_toggle_scanner = on_toggle_scanner
        self.on_mute = on_mute

        self._registered: Dict[str, object] = {}
        self._running = False
        self._lock = threading.Lock()

    @property
    def hk_settings(self) -> Dict:
        return self.settings.get("hotkeys", {})

    def start(self) -> bool:
        if not KEYBOARD_AVAILABLE:
            logger.error("keyboard library not installed. Hotkeys disabled.")
            return False

        self._running = True
        self._register_all()
        logger.info("HotkeyManager started")
        return True

    def stop(self) -> None:
        if KEYBOARD_AVAILABLE:
            try:
                keyboard.unhook_all()
            except Exception as e:
                logger.warning(f"Error unhooking hotkeys: {e}")
        self._running = False
        logger.info("HotkeyManager stopped")

    def _register_all(self) -> None:
        """Register all configured hotkeys."""
        bindings = [
            (self.hk_settings.get("toggle_listening", "F8"), self._handle_toggle_listening),
            (self.hk_settings.get("panic_button",      "F9"), self._handle_panic),
            (self.hk_settings.get("toggle_scanner",    "F10"), self._handle_toggle_scanner),
            (self.hk_settings.get("mute_audio",        "F11"), self._handle_mute),
        ]
        for hotkey, handler in bindings:
            self._register(hotkey, handler)

    def _register(self, hotkey: str, handler: Callable) -> None:
        """Register a single hotkey, suppressing it from other apps."""
        if not KEYBOARD_AVAILABLE or not hotkey:
            return
        try:
            with self._lock:
                if hotkey in self._registered:
                    keyboard.remove_hotkey(self._registered[hotkey])
                hook = keyboard.add_hotkey(hotkey, handler, suppress=False)
                self._registered[hotkey] = hook
            logger.debug(f"Hotkey registered: {hotkey}")
        except Exception as e:
            logger.error(f"Failed to register hotkey '{hotkey}': {e}")

    def update_hotkey(self, name: str, new_key: str) -> None:
        """Update a hotkey binding at runtime."""
        handler_map = {
            "toggle_listening": self._handle_toggle_listening,
            "panic_button": self._handle_panic,
            "toggle_scanner": self._handle_toggle_scanner,
            "mute_audio": self._handle_mute,
        }
        handler = handler_map.get(name)
        if handler and new_key:
            # Remove old binding if it exists
            old_key = self.hk_settings.get(name, "")
            if old_key and old_key in self._registered and KEYBOARD_AVAILABLE:
                try:
                    keyboard.remove_hotkey(self._registered.pop(old_key))
                except Exception:
                    pass
            self._register(new_key, handler)

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_toggle_listening(self) -> None:
        logger.info("Hotkey: Toggle Listening (F8)")
        if self.on_toggle_listening:
            self.on_toggle_listening()

    def _handle_panic(self) -> None:
        logger.warning("Hotkey: PANIC BUTTON (F9)")
        if self.on_panic:
            self.on_panic()

    def _handle_toggle_scanner(self) -> None:
        logger.info("Hotkey: Toggle Scanner (F10)")
        if self.on_toggle_scanner:
            self.on_toggle_scanner()

    def _handle_mute(self) -> None:
        logger.info("Hotkey: Toggle Mute (F11)")
        if self.on_mute:
            self.on_mute()

    @staticmethod
    def get_available_keys() -> list:
        """Return common keys that can be used as hotkeys."""
        return [
            "F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12",
            "insert","delete","home","end","page up","page down",
            "ctrl+F1","ctrl+F2","ctrl+F3","ctrl+F4","ctrl+F5",
            "alt+F1","alt+F2","alt+F3","alt+F4","alt+F5",
        ]
