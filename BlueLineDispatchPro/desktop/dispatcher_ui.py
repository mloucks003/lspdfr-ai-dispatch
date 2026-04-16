"""
BlueLineDispatchPro — Dispatcher-Only UI
Minimal focused window: mic status, scanner, transcript, trigger log.
"""
import tkinter as tk
from collections import deque
from typing import Callable, Optional

from ui.components import theme as T

# ── Compact layout constants ──────────────────────────────────────────────────
WIN_W, WIN_H = 560, 640
INDICATOR_ON  = ("● ", T.ACCENT_GREEN)
INDICATOR_OFF = ("● ", T.TEXT_MUTED)


class DispatcherWindow:
    """Lightweight dispatcher-only window. No tabs, no CAD overhead."""

    def __init__(self, settings: dict):
        self.settings = settings
        self._trigger_log: deque = deque(maxlen=30)
        self._listener_active = False
        self._scanner_active = False
        self._muted = False
        self._panic_active = False

        # Callbacks wired by dispatcher_main.py after init
        self.on_toggle_listen:  Optional[Callable] = None
        self.on_toggle_scanner: Optional[Callable] = None
        self.on_panic:          Optional[Callable] = None
        self.on_mute:           Optional[Callable] = None
        self.on_quit:           Optional[Callable] = None

        self._build()

    def _build(self) -> None:
        T.configure_ctk_theme()
        self.root = tk.Tk()
        self.root.title("BlueLineDispatchPro — Dispatcher")
        self.root.geometry(f"{WIN_W}x{WIN_H}")
        self.root.resizable(True, True)
        self.root.minsize(420, 500)
        self.root.configure(bg=T.BG_PRIMARY)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

        # Center window
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{WIN_W}x{WIN_H}+{(sw-WIN_W)//2}+{(sh-WIN_H)//2}")

        self._build_header()
        self._build_controls()
        self._build_transcript()
        self._build_log()
        self._build_statusbar()

    def _build_header(self) -> None:
        hdr = tk.Frame(self.root, bg=T.BG_HEADER, height=52)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)

        tk.Label(hdr, text="🚔  BlueLineDispatchPro",
                 bg=T.BG_HEADER, fg=T.TEXT_PRIMARY,
                 font=(T.FONT_FAMILY, 13, "bold"), padx=T.PAD_MD).pack(side=tk.LEFT, pady=T.PAD_SM)

        agency = self.settings.get("cad", {}).get("agency_name", "Los Santos Police Department")
        unit   = self.settings.get("cad", {}).get("unit_id", "1-ADAM-12")
        tk.Label(hdr, text=f"{agency}  |  {unit}",
                 bg=T.BG_HEADER, fg=T.TEXT_MUTED,
                 font=T.FONT_SMALL).pack(side=tk.LEFT)

    def _build_controls(self) -> None:
        ctrl = tk.Frame(self.root, bg=T.BG_SECONDARY, pady=T.PAD_MD)
        ctrl.pack(fill=tk.X, padx=T.PAD_SM, pady=(T.PAD_SM, 0))

        # Big MIC toggle
        self._mic_btn = tk.Button(
            ctrl, text="🎙  START LISTENING  (F8)",
            bg=T.BG_TERTIARY, fg=T.TEXT_MUTED,
            font=(T.FONT_FAMILY, 12, "bold"),
            relief=tk.FLAT, cursor="hand2", pady=14,
            command=lambda: self.on_toggle_listen and self.on_toggle_listen(),
        )
        self._mic_btn.pack(fill=tk.X, padx=T.PAD_MD, pady=(0, T.PAD_SM))

        # Row 2: Scanner + Mute + Panic
        row2 = tk.Frame(ctrl, bg=T.BG_SECONDARY)
        row2.pack(fill=tk.X, padx=T.PAD_MD)

        self._scanner_btn = tk.Button(
            row2, text="📡  SCANNER: OFF  (F10)",
            bg=T.BG_TERTIARY, fg=T.TEXT_MUTED,
            font=T.FONT_BODY, relief=tk.FLAT, cursor="hand2", pady=8,
            command=lambda: self.on_toggle_scanner and self.on_toggle_scanner(),
        )
        self._scanner_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, T.PAD_XS))

        self._mute_btn = tk.Button(
            row2, text="🔊  (F11)",
            bg=T.BG_TERTIARY, fg=T.TEXT_MUTED,
            font=T.FONT_BODY, relief=tk.FLAT, cursor="hand2", pady=8,
            command=lambda: self.on_mute and self.on_mute(), width=10,
        )
        self._mute_btn.pack(side=tk.LEFT, padx=T.PAD_XS)

        self._panic_btn = tk.Button(
            row2, text="🚨 PANIC (F9)",
            bg=T.ACCENT_RED, fg=T.TEXT_PRIMARY,
            font=(T.FONT_FAMILY, 10, "bold"), relief=tk.FLAT, cursor="hand2", pady=8,
            command=lambda: self.on_panic and self.on_panic(), width=14,
        )
        self._panic_btn.pack(side=tk.LEFT, padx=(T.PAD_XS, 0))

    def _build_transcript(self) -> None:
        tf = tk.Frame(self.root, bg=T.BG_PRIMARY)
        tf.pack(fill=tk.X, padx=T.PAD_SM, pady=(T.PAD_SM, 0))

        tk.Label(tf, text="LAST HEARD", bg=T.BG_PRIMARY,
                 fg=T.TEXT_MUTED, font=T.FONT_SMALL).pack(anchor="w")

        self._transcript_var = tk.StringVar(value="Waiting for speech...")
        transcript_lbl = tk.Label(
            tf, textvariable=self._transcript_var,
            bg=T.BG_SECONDARY, fg=T.TEXT_SECONDARY,
            font=(T.FONT_MONO, 10), anchor="w",
            padx=T.PAD_SM, pady=T.PAD_SM,
            wraplength=WIN_W - 40, justify=tk.LEFT,
        )
        transcript_lbl.pack(fill=tk.X)

        # Last trigger highlight
        self._trigger_var = tk.StringVar(value="No keyword triggered yet.")
        tk.Label(
            tf, textvariable=self._trigger_var,
            bg=T.BG_TERTIARY, fg=T.ACCENT_BLUE_GLOW,
            font=(T.FONT_FAMILY, 10, "bold"),
            anchor="w", padx=T.PAD_SM, pady=6,
        ).pack(fill=tk.X, pady=(T.PAD_XS, 0))

    def _build_log(self) -> None:
        lf = tk.Frame(self.root, bg=T.BG_PRIMARY)
        lf.pack(fill=tk.BOTH, expand=True, padx=T.PAD_SM, pady=T.PAD_SM)

        tk.Label(lf, text="TRIGGER LOG", bg=T.BG_PRIMARY,
                 fg=T.TEXT_MUTED, font=T.FONT_SMALL).pack(anchor="w")

        log_frame = tk.Frame(lf, bg=T.BG_SECONDARY)
        log_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(log_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._log_text = tk.Text(
            log_frame,
            bg=T.BG_SECONDARY, fg=T.TEXT_PRIMARY,
            font=(T.FONT_MONO, 9),
            relief=tk.FLAT, state=tk.DISABLED,
            yscrollcommand=scrollbar.set,
            padx=T.PAD_SM, pady=T.PAD_SM,
            spacing1=2, spacing3=2,
        )
        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.configure(command=self._log_text.yview)

        # Text tags
        self._log_text.tag_configure("time",     foreground=T.TEXT_MUTED)
        self._log_text.tag_configure("phrase",   foreground=T.ACCENT_BLUE_GLOW)
        self._log_text.tag_configure("category", foreground=T.ACCENT_GREEN)
        self._log_text.tag_configure("panic",    foreground=T.ACCENT_RED, font=(T.FONT_MONO, 9, "bold"))

    def _build_statusbar(self) -> None:
        sb = tk.Frame(self.root, bg=T.BG_HEADER, height=26)
        sb.pack(fill=tk.X, side=tk.BOTTOM)
        sb.pack_propagate(False)

        self._status_mic_lbl = tk.Label(sb, text="● MIC OFF",
            bg=T.BG_HEADER, fg=T.TEXT_MUTED, font=(T.FONT_FAMILY, 8, "bold"), padx=T.PAD_SM)
        self._status_mic_lbl.pack(side=tk.LEFT)

        self._status_scan_lbl = tk.Label(sb, text="● SCANNER OFF",
            bg=T.BG_HEADER, fg=T.TEXT_MUTED, font=(T.FONT_FAMILY, 8, "bold"), padx=T.PAD_SM)
        self._status_scan_lbl.pack(side=tk.LEFT)

        hints = "[F8] Listen   [F9] Panic   [F10] Scanner   [F11] Mute"
        tk.Label(sb, text=hints, bg=T.BG_HEADER, fg=T.TEXT_MUTED,
                 font=(T.FONT_FAMILY, 7)).pack(side=tk.RIGHT, padx=T.PAD_SM)

    # ── Public update methods (called from dispatcher_main.py) ────────────────

    def set_listener_state(self, active: bool) -> None:
        self._listener_active = active
        self._safe(lambda: self._apply_listener_state(active))

    def _apply_listener_state(self, active: bool) -> None:
        if active:
            self._mic_btn.configure(text="🎙  LISTENING... (F8 to stop)",
                                    bg=T.ACCENT_GREEN, fg=T.TEXT_PRIMARY)
            self._status_mic_lbl.configure(text="● MIC LIVE", fg=T.ACCENT_GREEN)
        else:
            self._mic_btn.configure(text="🎙  START LISTENING  (F8)",
                                    bg=T.BG_TERTIARY, fg=T.TEXT_MUTED)
            self._status_mic_lbl.configure(text="● MIC OFF", fg=T.TEXT_MUTED)
            self._transcript_var.set("Waiting for speech...")

    def set_scanner_state(self, active: bool) -> None:
        self._scanner_active = active
        self._safe(lambda: self._apply_scanner_state(active))

    def _apply_scanner_state(self, active: bool) -> None:
        if active:
            self._scanner_btn.configure(text="📡  SCANNER: ON  (F10 to stop)",
                                         bg=T.ACCENT_BLUE, fg=T.TEXT_PRIMARY)
            self._status_scan_lbl.configure(text="● SCANNER ON", fg=T.ACCENT_BLUE)
        else:
            self._scanner_btn.configure(text="📡  SCANNER: OFF  (F10)",
                                         bg=T.BG_TERTIARY, fg=T.TEXT_MUTED)
            self._status_scan_lbl.configure(text="● SCANNER OFF", fg=T.TEXT_MUTED)

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        self._safe(lambda: self._mute_btn.configure(
            text="🔇  MUTED (F11)" if muted else "🔊  (F11)",
            fg=T.ACCENT_RED if muted else T.TEXT_MUTED,
        ))

    def set_transcript(self, text: str) -> None:
        if text:
            self._safe(lambda: self._transcript_var.set(f'🎙  "{text}"'))

    def log_trigger(self, phrase: str, category: str) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        is_panic = category == "panic"

        def _insert():
            self._log_text.configure(state=tk.NORMAL)
            self._log_text.insert("1.0", "\n")
            cat_tag = "panic" if is_panic else "category"
            self._log_text.insert("1.0", f"  [{category.upper()}]", cat_tag)
            self._log_text.insert("1.0", f"  \"{phrase}\"", "phrase")
            self._log_text.insert("1.0", f"[{ts}]", "time")
            self._log_text.configure(state=tk.DISABLED)
            self._trigger_var.set(f'⚡ Last: "{phrase}" → [{category.upper()}]')

        self._safe(_insert)

    def flash_panic(self) -> None:
        if self._panic_active:
            return
        self._panic_active = True

        def _flash():
            overlay = tk.Toplevel(self.root)
            overlay.attributes("-topmost", True)
            overlay.attributes("-alpha", 0.85)
            overlay.overrideredirect(True)
            sw = overlay.winfo_screenwidth()
            sh = overlay.winfo_screenheight()
            overlay.geometry(f"{sw}x{sh}+0+0")
            overlay.configure(bg=T.ACCENT_RED)
            tk.Label(overlay, text="🚨  PANIC — OFFICER NEEDS ASSISTANCE  🚨",
                     bg=T.ACCENT_RED, fg="white",
                     font=(T.FONT_FAMILY, 26, "bold")).pack(expand=True)
            tk.Label(overlay, text="Click anywhere to dismiss",
                     bg=T.ACCENT_RED, fg="white", font=T.FONT_BODY).pack()

            def dismiss(e=None):
                self._panic_active = False
                overlay.destroy()

            overlay.bind("<Button-1>", dismiss)
            overlay.after(5000, dismiss)

        self._safe(_flash)

    def show_error(self, msg: str) -> None:
        self._safe(lambda: __import__("tkinter.messagebox", fromlist=["showerror"])
                   .showerror("BlueLineDispatchPro", msg))

    def _safe(self, fn) -> None:
        try:
            self.root.after(0, fn)
        except tk.TclError:
            pass

    def _quit(self) -> None:
        if self.on_quit:
            self.on_quit()
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def run(self) -> None:
        self.root.mainloop()
