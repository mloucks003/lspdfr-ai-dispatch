"""
BlueLineDispatchPro — Main Application Window
Orchestrates all UI tabs, status bar, tray icon, and panic overlay.
"""
import logging
import tkinter as tk
from pathlib import Path
from typing import Dict, Optional

try:
    import customtkinter as ctk
    CTK = True
except ImportError:
    CTK = False

from ui.components import theme as T
from ui.components.status_bar import StatusBar
from ui.components.tray_icon import TrayIconManager
from ui.tabs.active_calls import ActiveCallsTab
from ui.tabs.unit_status import UnitStatusTab
from ui.tabs.vehicle_lookup import VehicleLookupTab
from ui.tabs.person_lookup import PersonLookupTab
from ui.tabs.bolos import BOLOsTab
from ui.tabs.dispatch_log import DispatchLogTab
from ui.tabs.live_map import LiveMapTab
from ui.tabs.settings_tab import SettingsTab

logger = logging.getLogger(__name__)


class BlueLineApp:
    """Main application window — the top-level orchestrator."""

    TABS = [
        ("🚨 Active Calls",     "calls"),
        ("👥 Unit Status",      "units"),
        ("🚗 Vehicle Lookup",   "vehicle"),
        ("👤 Person Lookup",    "person"),
        ("⚑  BOLOs",           "bolos"),
        ("📋 Dispatch Log",     "log"),
        ("🗺  Live Map",        "map"),
        ("⚙  Settings",        "settings"),
    ]

    def __init__(self, cad_engine, keyword_listener, audio_player, scanner_mode,
                 hotkey_manager, settings: Dict, audio_dir: Path):
        self.cad = cad_engine
        self.listener = keyword_listener
        self.audio = audio_player
        self.scanner = scanner_mode
        self.hotkeys = hotkey_manager
        self.settings = settings
        self.audio_dir = audio_dir

        self._panic_active = False
        self._tab_frames: Dict[str, tk.Frame] = {}
        self._active_tab = "calls"

        T.configure_ctk_theme()
        self._build_root()
        self._build_ui()
        self._connect_callbacks()
        self._setup_tray()

    def _build_root(self) -> None:
        self.root = tk.Tk()
        self.root.title("BlueLineDispatchPro — Professional Police CAD")
        w = self.settings.get("app", {}).get("window_width", 1280)
        h = self.settings.get("app", {}).get("window_height", 800)
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(1024, 640)
        self.root.configure(bg=T.BG_PRIMARY)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Center on screen
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self) -> None:
        # ── Title bar ────────────────────────────────────────────────────────
        title_bar = tk.Frame(self.root, bg=T.BG_HEADER, height=50)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)

        tk.Label(
            title_bar,
            text="🚔  BlueLineDispatchPro",
            bg=T.BG_HEADER,
            fg=T.TEXT_PRIMARY,
            font=(T.FONT_FAMILY, 14, "bold"),
            padx=T.PAD_MD,
        ).pack(side=tk.LEFT, pady=T.PAD_SM)

        agency = self.settings.get("cad", {}).get("agency_name", "Los Santos Police Department")
        tk.Label(title_bar, text=f"| {agency}", bg=T.BG_HEADER,
                 fg=T.TEXT_MUTED, font=T.FONT_BODY).pack(side=tk.LEFT, pady=T.PAD_SM)

        # Panic button in title bar
        self._panic_btn = tk.Button(
            title_bar,
            text="🚨  PANIC",
            bg=T.ACCENT_RED,
            fg=T.TEXT_PRIMARY,
            font=(T.FONT_FAMILY, 11, "bold"),
            relief=tk.FLAT,
            cursor="hand2",
            padx=T.PAD_LG,
            command=self._trigger_panic,
        )
        self._panic_btn.pack(side=tk.RIGHT, padx=T.PAD_MD, pady=8)

        # Listener toggle
        self._listen_btn = tk.Button(
            title_bar,
            text="🎙 LISTEN: OFF",
            bg=T.BG_TERTIARY,
            fg=T.TEXT_MUTED,
            font=T.FONT_BODY,
            relief=tk.FLAT,
            cursor="hand2",
            padx=T.PAD_MD,
            command=self._toggle_listening,
        )
        self._listen_btn.pack(side=tk.RIGHT, padx=T.PAD_SM, pady=8)

        # Scanner toggle
        self._scanner_btn = tk.Button(
            title_bar,
            text="📡 SCANNER: OFF",
            bg=T.BG_TERTIARY,
            fg=T.TEXT_MUTED,
            font=T.FONT_BODY,
            relief=tk.FLAT,
            cursor="hand2",
            padx=T.PAD_MD,
            command=self._toggle_scanner,
        )
        self._scanner_btn.pack(side=tk.RIGHT, padx=T.PAD_SM, pady=8)

        # ── Tab navigation bar ────────────────────────────────────────────────
        tab_bar = tk.Frame(self.root, bg=T.BG_SECONDARY, height=38)
        tab_bar.pack(fill=tk.X)
        tab_bar.pack_propagate(False)

        self._tab_buttons: Dict[str, tk.Button] = {}
        for label, tab_id in self.TABS:
            btn = tk.Button(
                tab_bar,
                text=label,
                bg=T.BG_SECONDARY,
                fg=T.TEXT_SECONDARY,
                font=T.FONT_SMALL,
                relief=tk.FLAT,
                cursor="hand2",
                padx=T.PAD_MD,
                pady=6,
                command=lambda tid=tab_id: self._switch_tab(tid),
            )
            btn.pack(side=tk.LEFT)
            self._tab_buttons[tab_id] = btn

        # ── Content area ──────────────────────────────────────────────────────
        self._content_frame = tk.Frame(self.root, bg=T.BG_PRIMARY)
        self._content_frame.pack(fill=tk.BOTH, expand=True)

        # Build all tab frames
        self._tab_frames["calls"]    = ActiveCallsTab(self._content_frame, self.cad)
        self._tab_frames["units"]    = UnitStatusTab(self._content_frame, self.cad)
        self._tab_frames["vehicle"]  = VehicleLookupTab(self._content_frame, self.cad)
        self._tab_frames["person"]   = PersonLookupTab(self._content_frame, self.cad)
        self._tab_frames["bolos"]    = BOLOsTab(self._content_frame, self.cad)
        self._tab_frames["log"]      = DispatchLogTab(self._content_frame, self.cad)
        self._tab_frames["map"]      = LiveMapTab(self._content_frame, self.cad)
        self._tab_frames["settings"] = SettingsTab(
            self._content_frame, self.settings, self.audio, on_save=self._on_settings_saved
        )

        for frame in self._tab_frames.values():
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        # ── Status bar ────────────────────────────────────────────────────────
        self._status_bar = StatusBar(self.root)
        self._status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # Show initial tab
        self._switch_tab("calls")

    def _connect_callbacks(self) -> None:
        """Wire up CAD engine events to status bar and UI state."""
        self.cad.on("companion_status", lambda c: self._safe(
            lambda: self._status_bar.set_companion_state(c)))
        self.cad.on("panic", lambda d: self._safe(self._show_panic_overlay))

    def _switch_tab(self, tab_id: str) -> None:
        """Switch visible tab."""
        self._active_tab = tab_id
        for tid, frame in self._tab_frames.items():
            frame.lower()
        self._tab_frames[tab_id].lift()

        for tid, btn in self._tab_buttons.items():
            if tid == tab_id:
                btn.configure(bg=T.BG_TERTIARY, fg=T.ACCENT_BLUE_GLOW,
                              font=(T.FONT_FAMILY, 9, "bold"))
            else:
                btn.configure(bg=T.BG_SECONDARY, fg=T.TEXT_SECONDARY,
                              font=T.FONT_SMALL)

    def _toggle_listening(self) -> None:
        if self.listener.is_active:
            self.listener.set_active(False)
            self.cad.listener_active = False
            self._listen_btn.configure(text="🎙 LISTEN: OFF", bg=T.BG_TERTIARY, fg=T.TEXT_MUTED)
            self._status_bar.set_listener_state(False)
        else:
            if not self.listener._running:
                ok = self.listener.start()
                if not ok:
                    self._show_error("Keyword Listener", "Failed to start Vosk listener.\nCheck model path in Settings.")
                    return
            self.listener.set_active(True)
            self.cad.listener_active = True
            self._listen_btn.configure(text="🎙 LISTEN: ON", bg=T.ACCENT_GREEN, fg=T.TEXT_PRIMARY)
            self._status_bar.set_listener_state(True)

    def _toggle_scanner(self) -> None:
        new_state = not self.scanner.is_active
        self.scanner.set_active(new_state)
        self.cad.scanner_active = new_state
        if new_state:
            self._scanner_btn.configure(text="📡 SCANNER: ON", bg=T.ACCENT_BLUE, fg=T.TEXT_PRIMARY)
            self._status_bar.set_scanner_state(True)
        else:
            self._scanner_btn.configure(text="📡 SCANNER: OFF", bg=T.BG_TERTIARY, fg=T.TEXT_MUTED)
            self._status_bar.set_scanner_state(False)

    def _trigger_panic(self) -> None:
        self.cad.trigger_panic()
        self.audio.play_category(self.audio_dir, "panic")

    def _show_panic_overlay(self) -> None:
        """Flash red panic overlay."""
        if self._panic_active:
            return
        self._panic_active = True
        overlay = tk.Toplevel(self.root)
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.88)
        overlay.overrideredirect(True)
        sw = overlay.winfo_screenwidth()
        sh = overlay.winfo_screenheight()
        overlay.geometry(f"{sw}x{sh}+0+0")
        overlay.configure(bg=T.ACCENT_RED)

        tk.Label(overlay, text="🚨 PANIC — OFFICER NEEDS ASSISTANCE 🚨",
                 bg=T.ACCENT_RED, fg=T.TEXT_PRIMARY,
                 font=(T.FONT_FAMILY, 28, "bold")).pack(expand=True)
        tk.Label(overlay, text="Click anywhere to dismiss",
                 bg=T.ACCENT_RED, fg=T.TEXT_PRIMARY, font=T.FONT_BODY).pack()

        def dismiss(e=None):
            self._panic_active = False
            overlay.destroy()

        overlay.bind("<Button-1>", dismiss)
        overlay.after(5000, dismiss)  # Auto-dismiss after 5 seconds

    def _on_settings_saved(self, new_settings: Dict) -> None:
        self.settings.update(new_settings)
        agency = self.settings.get("cad", {}).get("agency_name", "LSPD")
        self.root.title(f"BlueLineDispatchPro — {agency}")

    def _setup_tray(self) -> None:
        self._tray = TrayIconManager(
            on_show=self._show_window,
            on_quit=self._quit,
            on_toggle_listen=self._toggle_listening,
            on_toggle_scanner=self._toggle_scanner,
            on_panic=self._trigger_panic,
        )
        self._tray.start()

    def _show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _on_close(self) -> None:
        if self.settings.get("app", {}).get("minimize_to_tray", True):
            self.root.withdraw()
            self._tray.show_notification("BlueLineDispatchPro", "Running in system tray. Right-click tray icon to quit.")
        else:
            self._quit()

    def _quit(self) -> None:
        self._tray.stop()
        self.listener.stop()
        self.scanner.stop()
        self.hotkeys.stop()
        self.audio.stop()
        self.root.quit()
        self.root.destroy()

    def update_transcript(self, text: str) -> None:
        """Called by keyword listener with partial transcriptions."""
        self._safe(lambda: self._status_bar.set_transcript(text))

    def update_audio_mute(self, muted: bool) -> None:
        self._safe(lambda: self._status_bar.set_audio_muted(muted))

    def _safe(self, fn) -> None:
        """Run fn safely on the Tkinter main thread."""
        try:
            self.root.after(0, fn)
        except tk.TclError:
            pass

    def _show_error(self, title: str, message: str) -> None:
        import tkinter.messagebox as mb
        mb.showerror(title, message)

    def run(self) -> None:
        """Start the Tkinter event loop."""
        if self.settings.get("app", {}).get("start_minimized", False):
            self.root.withdraw()
        logger.info("BlueLineDispatchPro UI started")
        self.root.mainloop()
