"""
BlueLineDispatchPro — Live Map Tab
Canvas-based map showing unit positions and active call locations.
GTA V San Andreas coordinate system mapped to canvas.
"""
import math
import tkinter as tk
from typing import Dict, List, Optional, Tuple

from ui.components import theme as T

# GTA V San Andreas world bounds (approximate)
WORLD_MIN_X = -4000.0
WORLD_MAX_X =  4500.0
WORLD_MIN_Y = -4000.0
WORLD_MAX_Y =  8000.0

# Unit status → shape
UNIT_SHAPES = {
    "available":       ("triangle",    T.ACCENT_GREEN),
    "busy":            ("triangle",    T.ACCENT_ORANGE),
    "on-scene":        ("triangle",    T.ACCENT_BLUE),
    "code-6":          ("triangle",    "#9B59B6"),
    "out-of-service":  ("triangle",    T.ACCENT_RED),
}
CALL_PRIORITY_COLORS = {1: T.ACCENT_RED, 2: T.ACCENT_ORANGE, 3: T.ACCENT_YELLOW, 4: T.ACCENT_BLUE, 5: T.TEXT_MUTED}


def _world_to_canvas(wx: float, wy: float, canvas_w: int, canvas_h: int,
                     margin: int = 20) -> Tuple[int, int]:
    """Convert GTA world coordinates to canvas pixel coordinates."""
    norm_x = (wx - WORLD_MIN_X) / (WORLD_MAX_X - WORLD_MIN_X)
    norm_y = 1.0 - (wy - WORLD_MIN_Y) / (WORLD_MAX_Y - WORLD_MIN_Y)  # flip Y
    cx = int(margin + norm_x * (canvas_w - 2 * margin))
    cy = int(margin + norm_y * (canvas_h - 2 * margin))
    return cx, cy


class LiveMapTab(tk.Frame):
    def __init__(self, parent, cad_engine, **kwargs):
        super().__init__(parent, bg=T.BG_PRIMARY, **kwargs)
        self.cad = cad_engine
        self._units: List[Dict] = []
        self._calls: List[Dict] = []
        self._show_units = tk.BooleanVar(value=True)
        self._show_calls = tk.BooleanVar(value=True)
        self._show_labels = tk.BooleanVar(value=True)
        self._zoom = 1.0
        self._trails: Dict[str, List[Tuple[int, int]]] = {}
        self._build()
        self.cad.on("units_updated", self._on_units)
        self.cad.on("calls_updated", self._on_calls)
        self._redraw_timer()

    def _build(self) -> None:
        # Header
        header = tk.Frame(self, bg=T.BG_HEADER, height=44)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="LIVE MAP", bg=T.BG_HEADER,
                 fg=T.TEXT_PRIMARY, font=T.FONT_SUBTITLE, padx=T.PAD_MD).pack(side=tk.LEFT, pady=T.PAD_SM)

        # Controls
        ctrl_frame = tk.Frame(header, bg=T.BG_HEADER)
        ctrl_frame.pack(side=tk.RIGHT, padx=T.PAD_MD, pady=T.PAD_SM)

        for label, var in [("Units", self._show_units), ("Calls", self._show_calls), ("Labels", self._show_labels)]:
            tk.Checkbutton(ctrl_frame, text=label, variable=var, command=self._redraw,
                           bg=T.BG_HEADER, fg=T.TEXT_SECONDARY, selectcolor=T.BG_SECONDARY,
                           activebackground=T.BG_HEADER, font=T.FONT_SMALL).pack(side=tk.LEFT, padx=T.PAD_XS)

        tk.Button(ctrl_frame, text="Zoom +", bg=T.BG_TERTIARY, fg=T.TEXT_PRIMARY,
                  font=T.FONT_SMALL, relief=tk.FLAT, cursor="hand2",
                  command=lambda: self._zoom_in()).pack(side=tk.LEFT, padx=2)
        tk.Button(ctrl_frame, text="Zoom −", bg=T.BG_TERTIARY, fg=T.TEXT_PRIMARY,
                  font=T.FONT_SMALL, relief=tk.FLAT, cursor="hand2",
                  command=lambda: self._zoom_out()).pack(side=tk.LEFT, padx=2)
        tk.Button(ctrl_frame, text="Reset", bg=T.BG_TERTIARY, fg=T.TEXT_MUTED,
                  font=T.FONT_SMALL, relief=tk.FLAT, cursor="hand2",
                  command=lambda: self._zoom_reset()).pack(side=tk.LEFT, padx=2)

        # Map canvas
        map_frame = tk.Frame(self, bg=T.BG_SECONDARY)
        map_frame.pack(fill=tk.BOTH, expand=True, padx=T.PAD_SM, pady=T.PAD_SM)

        self._canvas = tk.Canvas(map_frame, bg="#0A1020", highlightthickness=0, cursor="crosshair")
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.bind("<Configure>", lambda e: self._redraw())
        self._canvas.bind("<Motion>", self._on_mouse_move)

        # Coords display
        self._coord_label = tk.Label(self, text="X: 0  Y: 0", bg=T.BG_HEADER,
                                     fg=T.TEXT_MUTED, font=T.FONT_SMALL)
        self._coord_label.pack(side=tk.BOTTOM, anchor="e", padx=T.PAD_MD)

        # Legend
        self._build_legend()

    def _build_legend(self) -> None:
        legend = tk.Frame(self._canvas, bg="#0A1020", pady=4)
        legend.place(relx=0.0, rely=1.0, anchor="sw", x=10, y=-10)
        tk.Label(legend, text="LEGEND", bg="#0A1020", fg=T.TEXT_MUTED,
                 font=(T.FONT_FAMILY, 7, "bold")).pack(anchor="w")
        items = [
            ("▲ Available Unit", T.ACCENT_GREEN),
            ("▲ Busy Unit",      T.ACCENT_ORANGE),
            ("▲ On Scene",       T.ACCENT_BLUE),
            ("● P1 Call",        T.ACCENT_RED),
            ("● P2 Call",        T.ACCENT_ORANGE),
            ("● P3+ Call",       T.ACCENT_YELLOW),
        ]
        for text, color in items:
            tk.Label(legend, text=text, bg="#0A1020", fg=color,
                     font=(T.FONT_FAMILY, 7)).pack(anchor="w")

    def _on_units(self, units: List[Dict]) -> None:
        self._units = units
        # Update trails
        for unit in units:
            uid = unit.get("unit_id", "")
            coords = unit.get("coords", {})
            if coords.get("x") is not None and coords.get("y") is not None:
                if uid not in self._trails:
                    self._trails[uid] = []
                trail = self._trails[uid]
                trail.append((float(coords["x"]), float(coords["y"])))
                if len(trail) > 10:
                    trail.pop(0)

    def _on_calls(self, calls: List[Dict]) -> None:
        self._calls = calls

    def _redraw(self) -> None:
        c = self._canvas
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10 or h < 10:
            return
        c.delete("dynamic")

        # Draw grid lines
        for i in range(0, 100, 10):
            x = int(w * i / 100)
            y = int(h * i / 100)
            c.create_line(x, 0, x, h, fill="#0D1525", tags="dynamic")
            c.create_line(0, y, w, y, fill="#0D1525", tags="dynamic")

        # Draw San Andreas outline (very simplified rectangular outline)
        margin = 20
        c.create_rectangle(margin, margin, w - margin, h - margin,
                           outline=T.BORDER_COLOR, width=1, tags="dynamic")

        # Label compass
        c.create_text(w // 2, margin + 8, text="N ↑", fill=T.TEXT_MUTED,
                      font=(T.FONT_FAMILY, 7), tags="dynamic")

        # Draw call markers
        if self._show_calls.get():
            for call in self._calls:
                if call.get("status") == "closed":
                    continue
                coords = call.get("coords", {})
                if not coords.get("x") and not coords.get("y"):
                    continue
                cx, cy = _world_to_canvas(float(coords.get("x", 0)), float(coords.get("y", 0)), w, h)
                priority = int(call.get("priority", 3))
                color = CALL_PRIORITY_COLORS.get(priority, T.TEXT_MUTED)
                r = 8
                c.create_oval(cx - r, cy - r, cx + r, cy + r,
                              fill=color + "88", outline=color, width=2, tags="dynamic")
                c.create_oval(cx - 3, cy - 3, cx + 3, cy + 3,
                              fill=color, outline="", tags="dynamic")
                if self._show_labels.get():
                    ctype = call.get("type", "")[:10]
                    c.create_text(cx, cy - r - 6, text=ctype,
                                 fill=color, font=(T.FONT_FAMILY, 7), tags="dynamic")

        # Draw unit markers
        if self._show_units.get():
            for unit in self._units:
                coords = unit.get("coords", {})
                if not coords.get("x") and not coords.get("y"):
                    continue
                ux, uy = _world_to_canvas(float(coords.get("x", 0)), float(coords.get("y", 0)), w, h)
                status = unit.get("status", "available")
                _, color = UNIT_SHAPES.get(status, ("triangle", T.TEXT_SECONDARY))

                # Draw trail
                uid = unit.get("unit_id", "")
                trail = self._trails.get(uid, [])
                if len(trail) > 1:
                    for i in range(1, len(trail)):
                        tx1, ty1 = _world_to_canvas(trail[i-1][0], trail[i-1][1], w, h)
                        tx2, ty2 = _world_to_canvas(trail[i][0], trail[i][1], w, h)
                        alpha = int(255 * i / len(trail))
                        c.create_line(tx1, ty1, tx2, ty2, fill=color + "44",
                                     width=1, tags="dynamic")

                # Triangle pointing up
                s = 10
                points = [ux, uy - s, ux - s, uy + s, ux + s, uy + s]
                c.create_polygon(points, fill=color, outline=T.BG_PRIMARY, width=1, tags="dynamic")

                if self._show_labels.get():
                    label = unit.get("unit_id", "")
                    c.create_text(ux, uy - s - 8, text=label,
                                 fill=color, font=(T.FONT_FAMILY, 7, "bold"), tags="dynamic")

    def _redraw_timer(self) -> None:
        """Auto-refresh map every 2 seconds."""
        try:
            self._redraw()
            self.after(2000, self._redraw_timer)
        except tk.TclError:
            pass

    def _on_mouse_move(self, event) -> None:
        """Show world coordinates under cursor."""
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        margin = 20
        if w < 10 or h < 10:
            return
        norm_x = (event.x - margin) / max(w - 2 * margin, 1)
        norm_y = (event.y - margin) / max(h - 2 * margin, 1)
        wx = WORLD_MIN_X + norm_x * (WORLD_MAX_X - WORLD_MIN_X)
        wy = WORLD_MAX_Y - norm_y * (WORLD_MAX_Y - WORLD_MIN_Y)
        self._coord_label.configure(text=f"X: {wx:.0f}  Y: {wy:.0f}")

    def _zoom_in(self) -> None:
        self._zoom = min(self._zoom * 1.25, 5.0)

    def _zoom_out(self) -> None:
        self._zoom = max(self._zoom / 1.25, 0.5)

    def _zoom_reset(self) -> None:
        self._zoom = 1.0
