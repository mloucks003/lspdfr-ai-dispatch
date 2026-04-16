"""
BlueLineDispatchPro — System Tray Icon
Manages the Windows system tray presence.
"""
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    import pystray
    from pystray import MenuItem as TrayItem, Menu as TrayMenu
    from PIL import Image, ImageDraw
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False
    logger.warning("pystray/Pillow not available — system tray disabled")


def _create_icon_image(size: int = 64) -> "Image.Image":
    """Generate a simple police badge icon programmatically."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark background circle
    draw.ellipse([2, 2, size - 2, size - 2], fill="#0D0F14", outline="#1E6FD9", width=3)

    # Blue star-badge shape (simplified as circle with star points)
    cx, cy = size // 2, size // 2
    r = size // 3
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#1E6FD9")

    # White center
    r2 = size // 6
    draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill="#E8EDF5")

    return img


class TrayIconManager:
    """Manages the system tray icon and context menu."""

    def __init__(self,
                 on_show: Optional[Callable] = None,
                 on_quit: Optional[Callable] = None,
                 on_toggle_listen: Optional[Callable] = None,
                 on_toggle_scanner: Optional[Callable] = None,
                 on_panic: Optional[Callable] = None):
        self.on_show = on_show
        self.on_quit = on_quit
        self.on_toggle_listen = on_toggle_listen
        self.on_toggle_scanner = on_toggle_scanner
        self.on_panic = on_panic
        self._icon: Optional[object] = None
        self._thread: Optional[threading.Thread] = None

        self._listening = False
        self._scanning = False

    def start(self) -> bool:
        if not PYSTRAY_AVAILABLE:
            logger.warning("System tray not available")
            return False

        icon_image = _create_icon_image(64)
        menu = self._build_menu()

        self._icon = pystray.Icon(
            name="BlueLineDispatchPro",
            icon=icon_image,
            title="BlueLineDispatchPro",
            menu=menu,
        )

        self._thread = threading.Thread(
            target=self._icon.run, daemon=True, name="TrayIcon"
        )
        self._thread.start()
        logger.info("System tray icon started")
        return True

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    def _build_menu(self) -> "TrayMenu":
        return TrayMenu(
            TrayItem("BlueLineDispatchPro", None, enabled=False),
            TrayMenu.SEPARATOR,
            TrayItem("Show Window",         self._show),
            TrayMenu.SEPARATOR,
            TrayItem(
                lambda item: f"{'Disable' if self._listening else 'Enable'} Listening",
                self._toggle_listen,
            ),
            TrayItem(
                lambda item: f"{'Stop' if self._scanning else 'Start'} Scanner",
                self._toggle_scanner,
            ),
            TrayMenu.SEPARATOR,
            TrayItem("🚨 PANIC",            self._panic),
            TrayMenu.SEPARATOR,
            TrayItem("Quit",               self._quit),
        )

    def _show(self, icon=None, item=None) -> None:
        if self.on_show:
            self.on_show()

    def _quit(self, icon=None, item=None) -> None:
        if self.on_quit:
            self.on_quit()

    def _toggle_listen(self, icon=None, item=None) -> None:
        if self.on_toggle_listen:
            self.on_toggle_listen()

    def _toggle_scanner(self, icon=None, item=None) -> None:
        if self.on_toggle_scanner:
            self.on_toggle_scanner()

    def _panic(self, icon=None, item=None) -> None:
        if self.on_panic:
            self.on_panic()

    def update_states(self, listening: bool, scanning: bool) -> None:
        """Update internal state for menu label toggling."""
        self._listening = listening
        self._scanning = scanning
        if self._icon:
            try:
                self._icon.update_menu()
            except Exception:
                pass

    def show_notification(self, title: str, message: str) -> None:
        """Show a Windows toast notification from the tray icon."""
        if self._icon and PYSTRAY_AVAILABLE:
            try:
                self._icon.notify(message, title)
            except Exception as e:
                logger.debug(f"Tray notification error: {e}")
