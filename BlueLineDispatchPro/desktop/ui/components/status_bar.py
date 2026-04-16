"""
BlueLineDispatchPro — Bottom Status Bar
Shows real-time status: listener state, companion connection, scanner, audio.
"""
import tkinter as tk
from typing import Dict, Optional

try:
    import customtkinter as ctk
    CTK_AVAILABLE = True
except ImportError:
    CTK_AVAILABLE = False

from ui.components import theme as T


class StatusBar(tk.Frame):
    """
    Bottom status bar showing system state indicators.
    Uses standard tkinter for compatibility with CTk root window.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            bg=T.BG_HEADER,
            height=28,
            **kwargs
        )
        self.pack_propagate(False)
        self._labels: Dict[str, tk.Label] = {}
        self._build()

    def _build(self) -> None:
        # Left side: status indicators
        left_frame = tk.Frame(self, bg=T.BG_HEADER)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=T.PAD_SM)

        self._labels["listener"] = self._make_indicator(
            left_frame, "● MIC OFF", T.TEXT_MUTED
        )
        self._labels["scanner"] = self._make_indicator(
            left_frame, "● SCANNER OFF", T.TEXT_MUTED
        )
        self._labels["companion"] = self._make_indicator(
            left_frame, "● CAD OFFLINE", T.ACCENT_RED
        )
        self._labels["audio"] = self._make_indicator(
            left_frame, "🔊 AUDIO ON", T.ACCENT_GREEN
        )

        # Separator
        tk.Label(self, text="|", bg=T.BG_HEADER, fg=T.BORDER_COLOR,
                 font=T.FONT_SMALL).pack(side=tk.LEFT)

        # Center: last transcript
        self._labels["transcript"] = tk.Label(
            self,
            text="Listening for keywords...",
            bg=T.BG_HEADER,
            fg=T.TEXT_MUTED,
            font=T.FONT_SMALL,
            anchor="w",
        )
        self._labels["transcript"].pack(side=tk.LEFT, fill=tk.X, expand=True, padx=T.PAD_SM)

        # Right side: hotkey hints + version
        right_frame = tk.Frame(self, bg=T.BG_HEADER)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=T.PAD_SM)

        hints = [
            ("F8", "Listen"),
            ("F9", "PANIC"),
            ("F10", "Scanner"),
            ("F11", "Mute"),
        ]
        for key, label in hints:
            tk.Label(
                right_frame,
                text=f"[{key}]",
                bg=T.BG_HEADER,
                fg=T.ACCENT_BLUE,
                font=(T.FONT_MONO, 8, "bold"),
            ).pack(side=tk.LEFT, padx=1)
            tk.Label(
                right_frame,
                text=f"{label}  ",
                bg=T.BG_HEADER,
                fg=T.TEXT_MUTED,
                font=T.FONT_SMALL,
            ).pack(side=tk.LEFT)

        # Version
        tk.Label(
            right_frame,
            text="BlueLineDispatchPro v1.0",
            bg=T.BG_HEADER,
            fg=T.TEXT_MUTED,
            font=T.FONT_SMALL,
        ).pack(side=tk.LEFT, padx=(T.PAD_LG, T.PAD_SM))

    def _make_indicator(self, parent, text: str, color: str) -> tk.Label:
        label = tk.Label(
            parent,
            text=text,
            bg=T.BG_HEADER,
            fg=color,
            font=(T.FONT_FAMILY, 8, "bold"),
            padx=T.PAD_SM,
        )
        label.pack(side=tk.LEFT)
        return label

    # ── Public Update Methods ─────────────────────────────────────────────────

    def set_listener_state(self, active: bool) -> None:
        if active:
            self._set("listener", "● MIC LIVE", T.ACCENT_GREEN)
        else:
            self._set("listener", "● MIC OFF", T.TEXT_MUTED)

    def set_scanner_state(self, active: bool) -> None:
        if active:
            self._set("scanner", "● SCANNER ON", T.ACCENT_BLUE)
        else:
            self._set("scanner", "● SCANNER OFF", T.TEXT_MUTED)

    def set_companion_state(self, connected: bool) -> None:
        if connected:
            self._set("companion", "● CAD ONLINE", T.ACCENT_GREEN)
        else:
            self._set("companion", "● CAD OFFLINE", T.ACCENT_RED)

    def set_audio_muted(self, muted: bool) -> None:
        if muted:
            self._set("audio", "🔇 MUTED", T.ACCENT_RED)
        else:
            self._set("audio", "🔊 AUDIO ON", T.ACCENT_GREEN)

    def set_transcript(self, text: str) -> None:
        truncated = text[:80] + "..." if len(text) > 80 else text
        self._set("transcript", f"🎙 \"{truncated}\"", T.TEXT_SECONDARY)

    def _set(self, key: str, text: str, color: str) -> None:
        label = self._labels.get(key)
        if label:
            try:
                label.configure(text=text, fg=color)
            except tk.TclError:
                pass
