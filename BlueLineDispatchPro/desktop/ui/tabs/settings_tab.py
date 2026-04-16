"""
BlueLineDispatchPro — Settings Tab
Full settings panel: audio devices, keywords, hotkeys, API, scanner, CAD options.
"""
import tkinter as tk
from typing import Callable, Dict, List, Optional

from ui.components import theme as T


class SettingsTab(tk.Frame):
    def __init__(self, parent, settings: Dict, audio_player, on_save: Optional[Callable] = None, **kwargs):
        super().__init__(parent, bg=T.BG_PRIMARY, **kwargs)
        self.settings = settings
        self.audio_player = audio_player
        self.on_save = on_save
        self._vars: Dict[str, tk.Variable] = {}
        self._build()

    def _build(self) -> None:
        # Header
        header = tk.Frame(self, bg=T.BG_HEADER, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="SETTINGS", bg=T.BG_HEADER,
                 fg=T.TEXT_PRIMARY, font=T.FONT_SUBTITLE, padx=T.PAD_MD).pack(side=tk.LEFT, pady=T.PAD_SM)
        tk.Button(header, text="Save Settings", bg=T.ACCENT_GREEN, fg=T.TEXT_PRIMARY,
                  font=T.FONT_BODY_BOLD, relief=tk.FLAT, cursor="hand2",
                  padx=T.PAD_MD, command=self._save).pack(side=tk.RIGHT, padx=T.PAD_MD, pady=8)
        tk.Button(header, text="Restore Defaults", bg=T.BG_TERTIARY, fg=T.TEXT_MUTED,
                  font=T.FONT_SMALL, relief=tk.FLAT, cursor="hand2",
                  padx=T.PAD_SM, command=self._restore_defaults).pack(side=tk.RIGHT, pady=8)

        # Scrollable content
        canvas = tk.Canvas(self, bg=T.BG_PRIMARY, highlightthickness=0)
        scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._content = tk.Frame(canvas, bg=T.BG_PRIMARY)
        win = canvas.create_window((0, 0), window=self._content, anchor="nw")
        self._content.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        # Build sections
        self._build_audio_section()
        self._build_listener_section()
        self._build_scanner_section()
        self._build_hotkeys_section()
        self._build_api_section()
        self._build_cad_section()

    def _section(self, title: str) -> tk.Frame:
        """Create a section panel and return its content frame."""
        outer = tk.Frame(self._content, bg=T.BG_SECONDARY)
        outer.pack(fill=tk.X, padx=T.PAD_MD, pady=(T.PAD_SM, 0))
        tk.Label(outer, text=title, bg=T.BG_SECONDARY, fg=T.ACCENT_BLUE,
                 font=T.FONT_HEADER, padx=T.PAD_MD, pady=T.PAD_SM).pack(anchor="w")
        tk.Frame(outer, bg=T.BORDER_COLOR, height=1).pack(fill=tk.X, padx=T.PAD_SM)
        content = tk.Frame(outer, bg=T.BG_SECONDARY)
        content.pack(fill=tk.X, padx=T.PAD_MD, pady=T.PAD_SM)
        return content

    def _row(self, parent, label: str, widget_factory: Callable, hint: str = "") -> tk.Widget:
        f = tk.Frame(parent, bg=T.BG_SECONDARY)
        f.pack(fill=tk.X, pady=3)
        tk.Label(f, text=label, bg=T.BG_SECONDARY, fg=T.TEXT_SECONDARY,
                 font=T.FONT_BODY, width=28, anchor="e").pack(side=tk.LEFT)
        widget = widget_factory(f)
        widget.pack(side=tk.LEFT, padx=T.PAD_SM)
        if hint:
            tk.Label(f, text=hint, bg=T.BG_SECONDARY, fg=T.TEXT_MUTED,
                     font=T.FONT_SMALL).pack(side=tk.LEFT, padx=T.PAD_XS)
        return widget

    def _entry(self, parent, key_path: str, default: str = "", width: int = 30) -> tk.Entry:
        var = tk.StringVar(value=self._get(key_path, default))
        self._vars[key_path] = var
        e = tk.Entry(parent, textvariable=var, bg=T.BG_TERTIARY, fg=T.TEXT_PRIMARY,
                     font=T.FONT_BODY, insertbackground=T.TEXT_PRIMARY,
                     width=width, relief=tk.FLAT)
        return e

    def _scale(self, parent, key_path: str, from_: float, to: float,
               default: float = 0.5, resolution: float = 0.01) -> tk.Scale:
        var = tk.DoubleVar(value=float(self._get(key_path, default)))
        self._vars[key_path] = var
        s = tk.Scale(parent, variable=var, from_=from_, to=to, resolution=resolution,
                     orient=tk.HORIZONTAL, bg=T.BG_SECONDARY, fg=T.TEXT_PRIMARY,
                     troughcolor=T.BG_TERTIARY, highlightthickness=0,
                     activebackground=T.ACCENT_BLUE, length=200, sliderlength=16)
        return s

    def _checkbox(self, parent, key_path: str, default: bool = True) -> tk.Checkbutton:
        var = tk.BooleanVar(value=bool(self._get(key_path, default)))
        self._vars[key_path] = var
        cb = tk.Checkbutton(parent, variable=var, bg=T.BG_SECONDARY,
                            fg=T.TEXT_PRIMARY, selectcolor=T.BG_TERTIARY,
                            activebackground=T.BG_SECONDARY)
        return cb

    def _get(self, key_path: str, default):
        """Get nested setting value by dot-delimited path."""
        parts = key_path.split(".")
        obj = self.settings
        for p in parts:
            if isinstance(obj, dict) and p in obj:
                obj = obj[p]
            else:
                return default
        return obj

    # ── Section Builders ──────────────────────────────────────────────────────

    def _build_audio_section(self) -> None:
        p = self._section("🔊  AUDIO")

        # Input device dropdown
        input_devices = self.audio_player.get_available_input_devices()
        input_names = ["default"] + [d["name"] for d in input_devices]
        current_in = self._get("audio.input_device_name", "default")
        in_var = tk.StringVar(value=current_in)
        self._vars["audio.input_device_name"] = in_var

        def mk_in_dropdown(parent):
            om = tk.OptionMenu(parent, in_var, *input_names)
            om.configure(bg=T.BG_TERTIARY, fg=T.TEXT_PRIMARY, font=T.FONT_BODY,
                        activebackground=T.BG_SECONDARY, relief=tk.FLAT, width=34)
            om["menu"].configure(bg=T.BG_TERTIARY, fg=T.TEXT_PRIMARY)
            return om
        self._row(p, "Input Device (Mic / VAC):", mk_in_dropdown)

        # Output device dropdown
        output_devices = self.audio_player.get_available_devices()
        output_names = ["default"] + [d["name"] for d in output_devices]
        current_out = self._get("audio.output_device_name", "default")
        out_var = tk.StringVar(value=current_out)
        self._vars["audio.output_device_name"] = out_var

        def mk_out_dropdown(parent):
            om = tk.OptionMenu(parent, out_var, *output_names)
            om.configure(bg=T.BG_TERTIARY, fg=T.TEXT_PRIMARY, font=T.FONT_BODY,
                        activebackground=T.BG_SECONDARY, relief=tk.FLAT, width=34)
            om["menu"].configure(bg=T.BG_TERTIARY, fg=T.TEXT_PRIMARY)
            return om
        self._row(p, "Output Device:", mk_out_dropdown)

        self._row(p, "Radio Effect Intensity:", lambda f: self._scale(f, "audio.radio_effect_intensity", 0.0, 1.0, 0.75), "0=off, 1=max")
        self._row(p, "Volume:", lambda f: self._scale(f, "audio.volume", 0.0, 1.0, 0.85))
        self._row(p, "Squelch Click Effect:", lambda f: self._checkbox(f, "audio.squelch_click", True))
        self._row(p, "Static Overlay:", lambda f: self._checkbox(f, "audio.static_overlay", True))
        self._row(p, "Prevent Audio Overlap:", lambda f: self._checkbox(f, "audio.prevent_overlap", True))
        self._row(p, "Min Gap Between Audio (ms):", lambda f: self._entry(f, "audio.min_gap_between_audio_ms", "1500", 8), "ms")

    def _build_listener_section(self) -> None:
        p = self._section("🎙  KEYWORD LISTENER")
        self._row(p, "Vosk Model Path:", lambda f: self._entry(f, "keyword_listener.model_path", "models/vosk-model-en-us", 40))
        self._row(p, "Confidence Threshold:", lambda f: self._scale(f, "keyword_listener.confidence_threshold", 0.0, 1.0, 0.65, 0.05), "0=low, 1=high")
        self._row(p, "Keyword Cooldown (sec):", lambda f: self._entry(f, "keyword_listener.cooldown_seconds", "4.0", 8))
        self._row(p, "Sample Rate:", lambda f: self._entry(f, "keyword_listener.sample_rate", "16000", 8), "Hz (16000 recommended)")

        # Keywords text area
        f = tk.Frame(p, bg=T.BG_SECONDARY)
        f.pack(fill=tk.X, pady=3)
        tk.Label(f, text="Keywords (one per line):", bg=T.BG_SECONDARY, fg=T.TEXT_SECONDARY,
                 font=T.FONT_BODY, anchor="e", width=28).pack(side=tk.LEFT, anchor="n")
        kw_frame = tk.Frame(f, bg=T.BG_TERTIARY)
        kw_frame.pack(side=tk.LEFT, padx=T.PAD_SM)
        kw_scroll = tk.Scrollbar(kw_frame, orient=tk.VERTICAL)
        kw_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._kw_text = tk.Text(kw_frame, bg=T.BG_TERTIARY, fg=T.TEXT_PRIMARY,
                                font=T.FONT_MONO_BODY, width=40, height=8,
                                relief=tk.FLAT, yscrollcommand=kw_scroll.set,
                                insertbackground=T.TEXT_PRIMARY)
        self._kw_text.pack(side=tk.LEFT)
        kw_scroll.configure(command=self._kw_text.yview)
        kws = self._get("keyword_listener.keywords", [])
        self._kw_text.insert("1.0", "\n".join(kws))

    def _build_scanner_section(self) -> None:
        p = self._section("📡  SCANNER MODE")
        self._row(p, "Start Scanner on Launch:", lambda f: self._checkbox(f, "scanner_mode.enabled", False))
        self._row(p, "Min Interval (seconds):", lambda f: self._entry(f, "scanner_mode.interval_min_seconds", "25", 8))
        self._row(p, "Max Interval (seconds):", lambda f: self._entry(f, "scanner_mode.interval_max_seconds", "90", 8))
        self._row(p, "Pause During Keyword Response:", lambda f: self._checkbox(f, "scanner_mode.pause_during_response", True))
        self._row(p, "Active Call Speed Multiplier:", lambda f: self._entry(f, "scanner_mode.active_call_multiplier", "0.6", 8), "<1 = faster")

    def _build_hotkeys_section(self) -> None:
        p = self._section("⌨  HOTKEYS")
        self._row(p, "Toggle Listening:", lambda f: self._entry(f, "hotkeys.toggle_listening", "F8", 10))
        self._row(p, "Panic Button:", lambda f: self._entry(f, "hotkeys.panic_button", "F9", 10))
        self._row(p, "Toggle Scanner:", lambda f: self._entry(f, "hotkeys.toggle_scanner", "F10", 10))
        self._row(p, "Mute Audio:", lambda f: self._entry(f, "hotkeys.mute_audio", "F11", 10))
        tk.Label(p, text="Restart the app after changing hotkeys for them to take effect.",
                 bg=T.BG_SECONDARY, fg=T.TEXT_MUTED, font=T.FONT_SMALL).pack(anchor="w", pady=T.PAD_XS)

    def _build_api_section(self) -> None:
        p = self._section("🌐  COMPANION API SERVER")
        self._row(p, "Enable API Server:", lambda f: self._checkbox(f, "api_server.enabled", True))
        self._row(p, "Host:", lambda f: self._entry(f, "api_server.host", "127.0.0.1", 20))
        self._row(p, "Port:", lambda f: self._entry(f, "api_server.port", "7623", 8), "Must match companion config.lua")
        self._row(p, "API Key (optional):", lambda f: self._entry(f, "api_server.api_key", "", 30), "Leave blank to disable auth")
        self._row(p, "Log API Requests:", lambda f: self._checkbox(f, "api_server.log_requests", True))

    def _build_cad_section(self) -> None:
        p = self._section("🚔  CAD / AGENCY")
        self._row(p, "Agency Name:", lambda f: self._entry(f, "cad.agency_name", "Los Santos Police Department", 40))
        self._row(p, "Agency Short:", lambda f: self._entry(f, "cad.agency_short", "LSPD", 10))
        self._row(p, "Your Unit ID:", lambda f: self._entry(f, "cad.unit_id", "1-ADAM-12", 20))
        self._row(p, "Default Call Priority:", lambda f: self._entry(f, "cad.default_priority", "2", 5))
        self._row(p, "Auto-Clear Calls After (min):", lambda f: self._entry(f, "cad.auto_clear_calls_after_minutes", "120", 8))
        self._row(p, "Max Log Entries:", lambda f: self._entry(f, "cad.max_log_entries", "500", 8))
        self._row(p, "Start Minimized to Tray:", lambda f: self._checkbox(f, "app.start_minimized", False))
        self._row(p, "Minimize to Tray on Close:", lambda f: self._checkbox(f, "app.minimize_to_tray", True))

    # ── Save / Load ───────────────────────────────────────────────────────────

    def _collect_settings(self) -> Dict:
        """Collect current values from all bound variables."""
        updates = {}
        for key_path, var in self._vars.items():
            try:
                updates[key_path] = var.get()
            except Exception:
                pass

        # Keywords from text area
        kw_text = self._kw_text.get("1.0", tk.END).strip()
        kws = [k.strip() for k in kw_text.splitlines() if k.strip()]
        updates["keyword_listener.keywords"] = kws

        return updates

    def _apply_to_settings(self, updates: Dict) -> None:
        """Apply dot-path updates to the nested settings dict."""
        for key_path, value in updates.items():
            parts = key_path.split(".")
            obj = self.settings
            for p in parts[:-1]:
                obj = obj.setdefault(p, {})
            # Type coercion
            existing = obj.get(parts[-1])
            if isinstance(existing, int):
                try:
                    value = int(float(value)) if not isinstance(value, int) else value
                except (ValueError, TypeError):
                    pass
            elif isinstance(existing, float):
                try:
                    value = float(value) if not isinstance(value, float) else value
                except (ValueError, TypeError):
                    pass
            obj[parts[-1]] = value

    def _save(self) -> None:
        from config import save_settings
        updates = self._collect_settings()
        self._apply_to_settings(updates)
        if save_settings(self.settings):
            self._flash_saved()
        if self.on_save:
            self.on_save(self.settings)

    def _flash_saved(self) -> None:
        """Brief visual confirmation."""
        try:
            import tkinter.messagebox as mb
            mb.showinfo("Settings Saved", "Settings saved successfully!\n\nSome changes (hotkeys, API port, model path) require a restart to take effect.")
        except Exception:
            pass

    def _restore_defaults(self) -> None:
        import tkinter.messagebox as mb
        if mb.askyesno("Restore Defaults", "Reset all settings to defaults? This cannot be undone."):
            from config import CONFIG_DIR, APP_DATA_DIR
            user_file = APP_DATA_DIR / "settings_user.json"
            if user_file.exists():
                user_file.unlink()
            mb.showinfo("Defaults Restored", "Default settings restored. Please restart the application.")
