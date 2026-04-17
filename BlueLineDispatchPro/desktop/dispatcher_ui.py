"""
BlueLineDispatchPro — Police Radio UI
Dark hardware-style radio interface with LCD display, LED indicators,
animated signal bars, speaker grille and physical-feel buttons.
"""
import tkinter as tk
from collections import deque
from datetime import datetime
from typing import Callable, Optional

# ── Radio color palette ───────────────────────────────────────────────────────
BODY      = "#1A1A1A"      # radio housing
BODY_LT   = "#242424"      # lighter panel section
DISP_BG   = "#050D05"      # LCD screen bg
DISP_GRN  = "#00E64D"      # phosphor green text
DISP_DIM  = "#003D14"      # dim/inactive green
AMBER     = "#FFB300"
LED_GRN   = "#00FF5A"
LED_RED   = "#FF2424"
LED_YLW   = "#FFD700"
LED_OFF   = "#1C1C1C"
CHROME    = "#7A7A7A"
BTN_FACE  = "#2C2C2C"
BTN_HI    = "#3C3C3C"
BTN_SHD   = "#0A0A0A"
FONT_LCD  = "Courier New"
FONT_UI   = "Segoe UI"

WIN_W, WIN_H = 500, 740


class DispatcherWindow:
    def __init__(self, config: dict):
        self.config     = config
        self._log       = deque(maxlen=60)
        self._state_key = "idle"
        self._blink     = False
        self._blink_job = None

        self.on_manual_trigger: Optional[Callable] = None
        self.on_clear_history:  Optional[Callable] = None
        self.on_quit:           Optional[Callable] = None

        self._build()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        self.root = tk.Tk()
        self.root.title("BlueLineDispatchPro")
        self.root.geometry(f"{WIN_W}x{WIN_H}")
        self.root.resizable(False, False)
        self.root.configure(bg=BODY)
        self.root.protocol("WM_DELETE_WINDOW", self._quit)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{WIN_W}x{WIN_H}+{(sw-WIN_W)//2}+{(sh-WIN_H)//2}")

        self._build_badge()
        self._build_display()
        self._build_indicators()
        self._build_speaker()
        self._build_transcript()
        self._build_buttons()
        self._build_statusbar()
        self._start_clock()
        self._start_blink()

    def _build_badge(self):
        """Top agency strip."""
        agency   = self.config.get("agency", "DISPATCH").upper()
        callsign = self.config.get("callsign", "UNIT 1").upper()
        bar = tk.Frame(self.root, bg="#0D0D0D", height=34)
        bar.pack(fill=tk.X); bar.pack_propagate(False)
        tk.Label(bar, text="★  LSPD  ★", bg="#0D0D0D", fg="#4A90D9",
                 font=(FONT_UI, 8, "bold")).pack(side=tk.LEFT, padx=10)
        tk.Label(bar, text=agency, bg="#0D0D0D", fg="#666",
                 font=(FONT_UI, 8)).pack(side=tk.LEFT)
        tk.Label(bar, text=f"UNIT: {callsign}", bg="#0D0D0D", fg="#4A90D9",
                 font=(FONT_UI, 8, "bold")).pack(side=tk.RIGHT, padx=10)

    def _build_display(self):
        """Main LCD screen panel."""
        outer = tk.Frame(self.root, bg=BODY, padx=10, pady=8)
        outer.pack(fill=tk.X)
        bezel = tk.Frame(outer, bg="#0A0A0A", bd=4, relief=tk.SUNKEN)
        bezel.pack(fill=tk.X)
        scr = tk.Frame(bezel, bg=DISP_BG, padx=10, pady=8)
        scr.pack(fill=tk.X)

        top = tk.Frame(scr, bg=DISP_BG)
        top.pack(fill=tk.X)
        tk.Label(top, text="CH 1  ·  LSPD DISPATCH", bg=DISP_BG, fg=DISP_DIM,
                 font=(FONT_LCD, 8)).pack(side=tk.LEFT)
        self._clock_var = tk.StringVar(value="00:00:00")
        tk.Label(top, textvariable=self._clock_var, bg=DISP_BG, fg=DISP_GRN,
                 font=(FONT_LCD, 9, "bold")).pack(side=tk.RIGHT)

        tk.Frame(scr, bg=DISP_DIM, height=1).pack(fill=tk.X, pady=4)

        self._main_var = tk.StringVar(value="MONITORING...")
        tk.Label(scr, textvariable=self._main_var, bg=DISP_BG, fg=DISP_GRN,
                 font=(FONT_LCD, 14, "bold"), anchor="w").pack(fill=tk.X)
        self._sub_var = tk.StringVar(value="SAY CALLSIGN TO TRANSMIT")
        tk.Label(scr, textvariable=self._sub_var, bg=DISP_BG, fg=DISP_DIM,
                 font=(FONT_LCD, 8), anchor="w").pack(fill=tk.X)

    def _build_indicators(self):
        """LED status lights + signal strength bars + decorative knob."""
        row = tk.Frame(self.root, bg=BODY_LT, pady=8)
        row.pack(fill=tk.X, padx=10, pady=(0, 4))

        # LEDs
        leds = tk.Frame(row, bg=BODY_LT)
        leds.pack(side=tk.LEFT, padx=10)
        self._leds = {}
        for label, key, color in [("RX", "rx", LED_GRN), ("TX", "tx", LED_RED), ("BUSY", "busy", LED_YLW)]:
            col = tk.Frame(leds, bg=BODY_LT); col.pack(side=tk.LEFT, padx=8)
            c = tk.Canvas(col, width=16, height=16, bg=BODY_LT, highlightthickness=0); c.pack()
            ov = c.create_oval(1, 1, 15, 15, fill=LED_OFF, outline="#2A2A2A", width=1)
            tk.Label(col, text=label, bg=BODY_LT, fg="#4A4A4A",
                     font=(FONT_UI, 6, "bold")).pack()
            self._leds[key] = (c, ov, color)

        tk.Frame(row, bg="#333", width=1).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        # Signal bars
        sig = tk.Frame(row, bg=BODY_LT); sig.pack(side=tk.LEFT)
        tk.Label(sig, text="SIG", bg=BODY_LT, fg="#4A4A4A",
                 font=(FONT_UI, 6, "bold")).pack(side=tk.LEFT, padx=(0, 4))
        self._sig_cv = tk.Canvas(sig, width=64, height=16, bg=BODY_LT, highlightthickness=0)
        self._sig_cv.pack(side=tk.LEFT)
        self._sig_bars = []
        for i in range(8):
            h = 3 + i * 1.5; x = 2 + i * 8
            b = self._sig_cv.create_rectangle(x, 16-h, x+5, 16, fill="#1A3A1A", outline="")
            self._sig_bars.append(b)

        # Decorative knob
        kf = tk.Frame(row, bg=BODY_LT); kf.pack(side=tk.RIGHT, padx=12)
        kc = tk.Canvas(kf, width=34, height=34, bg=BODY_LT, highlightthickness=0); kc.pack()
        kc.create_oval(2, 2, 32, 32, fill="#1E1E1E", outline=CHROME, width=2)
        kc.create_oval(11, 5, 15, 9, fill=CHROME, outline="")
        tk.Label(kf, text="VOL", bg=BODY_LT, fg="#444", font=(FONT_UI, 6)).pack()

    def _build_speaker(self):
        """Dot-matrix speaker grille."""
        g = tk.Canvas(self.root, bg=BODY, height=26, highlightthickness=0)
        g.pack(fill=tk.X, padx=10, pady=(0, 4))
        for x in range(0, WIN_W - 20, 7):
            for y in range(4, 22, 7):
                g.create_oval(x, y, x+2, y+2, fill="#2C2C2C", outline="")

    def _build_transcript(self):
        """Radio log with green-on-black LCD style."""
        outer = tk.Frame(self.root, bg=BODY, padx=10)
        outer.pack(fill=tk.BOTH, expand=True)
        tk.Label(outer, text="▌ RADIO LOG", bg=BODY, fg="#3A3A3A",
                 font=(FONT_UI, 7, "bold")).pack(anchor="w")
        bezel = tk.Frame(outer, bg="#0A0A0A", bd=3, relief=tk.SUNKEN)
        bezel.pack(fill=tk.BOTH, expand=True)
        inner = tk.Frame(bezel, bg="#060E06"); inner.pack(fill=tk.BOTH, expand=True)
        sb = tk.Scrollbar(inner, orient=tk.VERTICAL, bg="#111", troughcolor="#060E06")
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tx_text = tk.Text(
            inner, bg="#060E06", fg=DISP_GRN,
            font=(FONT_LCD, 9), relief=tk.FLAT, state=tk.DISABLED,
            yscrollcommand=sb.set, padx=8, pady=6,
            spacing1=3, spacing3=3, wrap=tk.WORD,
            selectbackground="#0A3A0A",
        )
        self._tx_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.configure(command=self._tx_text.yview)
        self._tx_text.tag_configure("time",   foreground=DISP_DIM,   font=(FONT_LCD, 8))
        self._tx_text.tag_configure("label_d",foreground="#00BB44",   font=(FONT_LCD, 9, "bold"))
        self._tx_text.tag_configure("text_d", foreground=DISP_GRN,   font=(FONT_LCD, 9))
        self._tx_text.tag_configure("label_u",foreground="#44CCFF",   font=(FONT_LCD, 9, "bold"))
        self._tx_text.tag_configure("text_u", foreground="#88DDFF",   font=(FONT_LCD, 9))

    def _build_buttons(self):
        """Physical-looking radio buttons."""
        row = tk.Frame(self.root, bg=BODY, pady=8)
        row.pack(fill=tk.X, padx=12)
        self._make_btn(row, "▶  CALL DISPATCH", "#0D2A0D", "#00AA33",
                       lambda: self.on_manual_trigger and self.on_manual_trigger()
                       ).pack(side=tk.LEFT, padx=(0, 10))
        self._make_btn(row, "✕  CLEAR LOG", "#2A0D0D", "#AA2200",
                       lambda: self.on_clear_history and self.on_clear_history()
                       ).pack(side=tk.LEFT)

    def _make_btn(self, parent, text, bg, fg, cmd):
        wrap = tk.Frame(parent, bg=BTN_SHD, bd=1)
        tk.Button(wrap, text=text, bg=bg, fg=fg, activebackground=BTN_HI,
                  activeforeground=fg, font=(FONT_UI, 9, "bold"),
                  relief=tk.RAISED, bd=3, cursor="hand2",
                  padx=14, pady=8, command=cmd).pack(padx=1, pady=1)
        return wrap

    def _build_statusbar(self):
        sb = tk.Frame(self.root, bg="#0A0A0A", height=20)
        sb.pack(fill=tk.X, side=tk.BOTTOM); sb.pack_propagate(False)
        tk.Label(sb, text="BlueLineDispatchPro  ·  Vosk  ·  Whisper  ·  GPT-4o-mini  ·  Fish Audio",
                 bg="#0A0A0A", fg="#2A2A2A", font=(FONT_UI, 7)).pack(side=tk.LEFT, padx=8)

    # ── Animation ─────────────────────────────────────────────────────────────

    def _start_clock(self):
        def _tick():
            self._clock_var.set(datetime.now().strftime("%H:%M:%S"))
            self.root.after(1000, _tick)
        _tick()

    def _start_blink(self):
        def _blink():
            self._blink = not self._blink
            self._update_leds()
            self._blink_job = self.root.after(500, _blink)
        _blink()

    def _update_leds(self):
        s = self._state_key
        on_rx   = s in ("session_wait", "listening") and self._blink
        on_tx   = s in ("acknowledging", "responding") and self._blink
        on_busy = s == "processing"
        for key, active in [("rx", on_rx), ("tx", on_tx), ("busy", on_busy)]:
            c, ov, col = self._leds[key]
            c.itemconfig(ov, fill=col if active else LED_OFF)
        bars = 6 if s != "idle" else 2
        clrs = [LED_GRN, LED_GRN, LED_GRN, AMBER, AMBER, LED_RED, LED_RED, LED_RED]
        for i, bar in enumerate(self._sig_bars):
            fill = clrs[min(i, len(clrs)-1)] if i < bars and s != "idle" else "#1A3A1A"
            self._sig_cv.itemconfig(bar, fill=fill)

    # ── State display map ──────────────────────────────────────────────────────

    _DISPLAY = {
        "idle":          ("MONITORING...",   "SAY CALLSIGN TO TRANSMIT"),
        "acknowledging": ("CHANNEL OPEN",    "OPENING CHANNEL..."),
        "session_wait":  ("STANDING BY...",  "WAITING FOR TRANSMISSION"),
        "listening":     ("RECEIVING...",    "RECORDING — GO QUIET WHEN DONE"),
        "processing":    ("PROCESSING...",   "RUNNING CHECKS / COMPOSING"),
        "responding":    ("DISPATCHING...",  "DISPATCHER RESPONDING"),
    }

    # ── Public API ─────────────────────────────────────────────────────────────

    def set_ai_state(self, state_key: str, label: str = "", color: str = "") -> None:
        self._state_key = state_key
        def _apply():
            main, sub = self._DISPLAY.get(state_key, ("...", ""))
            self._main_var.set(main)
            self._sub_var.set(sub)
        self._safe(_apply)

    def append_transcript(self, role: str, text: str) -> None:
        ts     = datetime.now().strftime("%H:%M:%S")
        ltag   = "label_d" if role == "dispatch" else "label_u"
        ttag   = "text_d"  if role == "dispatch" else "text_u"
        prefix = "DISP" if role == "dispatch" else "YOU "
        def _insert():
            self._tx_text.configure(state=tk.NORMAL)
            self._tx_text.insert(tk.END, f"\n[{ts}] ", "time")
            self._tx_text.insert(tk.END, f"{prefix}  ", ltag)
            self._tx_text.insert(tk.END, text, ttag)
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
        if self._blink_job:
            try: self.root.after_cancel(self._blink_job)
            except Exception: pass
        if self.on_quit:
            self.on_quit()
        try:
            self.root.quit(); self.root.destroy()
        except Exception:
            pass

    def run(self) -> None:
        self.root.mainloop()
