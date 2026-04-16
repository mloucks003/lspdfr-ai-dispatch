"""
BlueLineDispatchPro — AI Dispatcher UI

Shows live AI state, conversation transcript, and manual controls.
"""
import tkinter as tk
from collections import deque
from datetime import datetime
from typing import Callable, Optional

# ── Inline theme (no external dependency) ────────────────────────────────────
BG        = "#1A1A2E"
BG2       = "#16213E"
BG3       = "#0F3460"
FG        = "#E0E0E0"
FG_MUTED  = "#888888"
ACCENT    = "#2471A3"
GREEN     = "#1E8449"
RED       = "#C0392B"
FONT      = "Segoe UI"
MONO      = "Consolas"

WIN_W, WIN_H = 580, 680


class DispatcherWindow:
    """AI Dispatcher window — shows live state, transcript, controls."""

    def __init__(self, config: dict):
        self.config = config
        self._log: deque = deque(maxlen=60)

        # Callbacks wired by dispatcher_main.py
        self.on_manual_trigger: Optional[Callable] = None
        self.on_clear_history:  Optional[Callable] = None
        self.on_quit:           Optional[Callable] = None

        self._build()

    def _build(self) -> None:
        self.root = tk.Tk()
        self.root.title("BlueLineDispatchPro — AI Dispatcher")
        self.root.geometry(f"{WIN_W}x{WIN_H}")
        self.root.resizable(True, True)
        self.root.minsize(440, 520)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)

        # Center window
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{WIN_W}x{WIN_H}+{(sw-WIN_W)//2}+{(sh-WIN_H)//2}")

        self._build_header()
        self._build_state_bar()
        self._build_controls()
        self._build_transcript()
        self._build_statusbar()

    def _build_header(self) -> None:
        hdr = tk.Frame(self.root, bg=BG2, height=52)
        hdr.pack(fill=tk.X)
        hdr.pack_propagate(False)
        agency   = self.config.get("agency", "Los Santos Police Department")
        callsign = self.config.get("callsign", "Unit 1")
        tk.Label(hdr, text="🚔  BlueLineDispatchPro  — AI Dispatcher",
                 bg=BG2, fg=FG, font=(FONT, 13, "bold"), padx=10).pack(side=tk.LEFT, pady=8)
        tk.Label(hdr, text=f"{agency}  |  {callsign}",
                 bg=BG2, fg=FG_MUTED, font=(FONT, 9)).pack(side=tk.LEFT)

    def _build_state_bar(self) -> None:
        """Large live-state indicator — changes color per dispatcher state."""
        self._state_var   = tk.StringVar(value="🎙  Listening for callsign...")
        self._state_color = tk.StringVar(value="#3A3A5A")

        self._state_lbl = tk.Label(
            self.root, textvariable=self._state_var,
            bg="#3A3A5A", fg=FG,
            font=(FONT, 12, "bold"), pady=14, padx=12, anchor="w",
        )
        self._state_lbl.pack(fill=tk.X, padx=8, pady=(8, 0))

    def _build_controls(self) -> None:
        row = tk.Frame(self.root, bg=BG, pady=6)
        row.pack(fill=tk.X, padx=8)

        tk.Button(
            row, text="📞  Manual Trigger",
            bg=ACCENT, fg=FG, font=(FONT, 10, "bold"),
            relief=tk.FLAT, cursor="hand2", pady=8, padx=16,
            command=lambda: self.on_manual_trigger and self.on_manual_trigger(),
        ).pack(side=tk.LEFT, padx=(0, 6))

        tk.Button(
            row, text="🗑  Clear History",
            bg=BG3, fg=FG_MUTED, font=(FONT, 10),
            relief=tk.FLAT, cursor="hand2", pady=8, padx=12,
            command=lambda: self.on_clear_history and self.on_clear_history(),
        ).pack(side=tk.LEFT)

        tk.Label(row, text="Say your callsign to activate the dispatcher",
                 bg=BG, fg=FG_MUTED, font=(FONT, 9)).pack(side=tk.RIGHT, padx=4)

    def _build_transcript(self) -> None:
        tf = tk.Frame(self.root, bg=BG)
        tf.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        tk.Label(tf, text="CONVERSATION", bg=BG, fg=FG_MUTED,
                 font=(FONT, 8, "bold")).pack(anchor="w")

        log_frame = tk.Frame(tf, bg=BG2)
        log_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(log_frame, orient=tk.VERTICAL, bg=BG2)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._tx_text = tk.Text(
            log_frame, bg=BG2, fg=FG,
            font=(MONO, 10), relief=tk.FLAT, state=tk.DISABLED,
            yscrollcommand=scrollbar.set,
            padx=10, pady=8, spacing1=4, spacing3=4,
            wrap=tk.WORD,
        )
        self._tx_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.configure(command=self._tx_text.yview)

        self._tx_text.tag_configure("time",     foreground=FG_MUTED, font=(MONO, 8))
        self._tx_text.tag_configure("officer",  foreground="#85C1E9", font=(MONO, 10, "bold"))
        self._tx_text.tag_configure("dispatch", foreground="#82E0AA", font=(MONO, 10))

    def _build_statusbar(self) -> None:
        sb = tk.Frame(self.root, bg=BG2, height=22)
        sb.pack(fill=tk.X, side=tk.BOTTOM)
        sb.pack_propagate(False)
        tk.Label(sb, text="Powered by Vosk · OpenAI Whisper · GPT-4o-mini · ElevenLabs",
                 bg=BG2, fg=FG_MUTED, font=(FONT, 7)).pack(side=tk.LEFT, padx=8)

    # ── Public update methods ─────────────────────────────────────────────────

    def set_ai_state(self, label: str, color: str) -> None:
        def _apply():
            self._state_var.set(label)
            self._state_lbl.configure(bg=color)
        self._safe(_apply)

    def append_transcript(self, role: str, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = "YOU  " if role == "officer" else "DISP "

        def _insert():
            self._tx_text.configure(state=tk.NORMAL)
            self._tx_text.insert(tk.END, f"\n[{ts}] ", "time")
            self._tx_text.insert(tk.END, f"{prefix}  {text}", role)
            self._tx_text.configure(state=tk.DISABLED)
            self._tx_text.see(tk.END)
        self._safe(_insert)

    def show_error(self, msg: str) -> None:
        import tkinter.messagebox as mb
        self._safe(lambda: mb.showerror("BlueLineDispatchPro", msg))

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
