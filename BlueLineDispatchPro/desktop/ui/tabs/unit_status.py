"""
BlueLineDispatchPro — Unit Status Tab
Roster of all units with real-time status, position, and call assignment.
"""
import tkinter as tk
from typing import Dict, List, Optional

from ui.components import theme as T


class UnitStatusTab(tk.Frame):
    def __init__(self, parent, cad_engine, **kwargs):
        super().__init__(parent, bg=T.BG_PRIMARY, **kwargs)
        self.cad = cad_engine
        self._units_data: List[Dict] = []
        self._selected_unit: Optional[str] = None
        self._build()
        self.cad.on("units_updated", self._on_units_updated)

    def _build(self) -> None:
        # Header
        header = tk.Frame(self, bg=T.BG_HEADER, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="UNIT STATUS", bg=T.BG_HEADER,
                 fg=T.TEXT_PRIMARY, font=T.FONT_SUBTITLE, padx=T.PAD_MD).pack(side=tk.LEFT, pady=T.PAD_SM)
        self._unit_count_label = tk.Label(header, text="0 units", bg=T.BG_HEADER,
                                          fg=T.TEXT_MUTED, font=T.FONT_SMALL)
        self._unit_count_label.pack(side=tk.LEFT)

        # Add unit button
        tk.Button(header, text="+ Add Unit", bg=T.ACCENT_BLUE, fg=T.TEXT_PRIMARY,
                  font=T.FONT_BODY, relief=tk.FLAT, cursor="hand2",
                  padx=T.PAD_MD, command=self._add_unit_dialog).pack(side=tk.RIGHT, padx=T.PAD_MD, pady=8)

        # Content
        content = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=T.BORDER_COLOR, sashwidth=4)
        content.pack(fill=tk.BOTH, expand=True, padx=T.PAD_SM, pady=T.PAD_SM)

        list_frame = tk.Frame(content, bg=T.BG_SECONDARY)
        content.add(list_frame, width=520, minsize=300)
        self._build_unit_list(list_frame)

        detail_frame = tk.Frame(content, bg=T.BG_SECONDARY)
        content.add(detail_frame, minsize=260)
        self._build_detail_panel(detail_frame)

    def _build_unit_list(self, parent: tk.Frame) -> None:
        # Column headers
        cols = [("Unit ID", 100), ("Name", 130), ("Status", 100), ("Location", 150), ("Call", 70)]
        header_row = tk.Frame(parent, bg=T.BG_TERTIARY, height=30)
        header_row.pack(fill=tk.X)
        header_row.pack_propagate(False)
        for col, width in cols:
            tk.Label(header_row, text=col, bg=T.BG_TERTIARY, fg=T.TEXT_SECONDARY,
                     font=T.FONT_SMALL, width=width//8, anchor="w").pack(side=tk.LEFT, padx=T.PAD_XS, pady=4)

        # Scrollable list
        canvas = tk.Canvas(parent, bg=T.BG_SECONDARY, highlightthickness=0)
        scrollbar = tk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._list_container = tk.Frame(canvas, bg=T.BG_SECONDARY)
        win = canvas.create_window((0, 0), window=self._list_container, anchor="nw")
        self._list_container.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))

    def _build_detail_panel(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="UNIT DETAILS", bg=T.BG_SECONDARY, fg=T.TEXT_SECONDARY,
                 font=T.FONT_HEADER, padx=T.PAD_MD, pady=T.PAD_SM).pack(anchor="w")
        tk.Frame(parent, bg=T.BORDER_COLOR, height=1).pack(fill=tk.X, padx=T.PAD_SM)

        self._detail_content = tk.Frame(parent, bg=T.BG_SECONDARY)
        self._detail_content.pack(fill=tk.BOTH, expand=True, padx=T.PAD_MD, pady=T.PAD_MD)

        tk.Label(self._detail_content, text="Select a unit",
                 bg=T.BG_SECONDARY, fg=T.TEXT_MUTED, font=T.FONT_BODY).pack(expand=True)

        # Status update buttons
        btn_frame = tk.Frame(parent, bg=T.BG_SECONDARY, pady=T.PAD_SM)
        btn_frame.pack(fill=tk.X, padx=T.PAD_MD, pady=(0, T.PAD_SM))

        status_opts = [
            ("10-8 Available", "available", T.ACCENT_GREEN),
            ("10-6 Busy",      "busy",      T.ACCENT_ORANGE),
            ("10-23 On Scene", "on-scene",  T.ACCENT_BLUE),
            ("Code 6",         "code-6",    "#9B59B6"),
            ("OOS",            "out-of-service", T.ACCENT_RED),
        ]
        tk.Label(btn_frame, text="Set Status:", bg=T.BG_SECONDARY, fg=T.TEXT_MUTED,
                 font=T.FONT_SMALL).pack(anchor="w", pady=(0, T.PAD_XS))
        for label, status, color in status_opts:
            tk.Button(
                btn_frame, text=label, bg=color, fg=T.TEXT_PRIMARY,
                font=T.FONT_SMALL, relief=tk.FLAT, cursor="hand2",
                command=lambda s=status: self._set_unit_status(s),
            ).pack(fill=tk.X, pady=1)

    def _set_unit_status(self, status: str) -> None:
        if not self._selected_unit:
            return
        self.cad.upsert_unit({"unit_id": self._selected_unit, "status": status})

    def _on_units_updated(self, units: List[Dict]) -> None:
        self._units_data = units
        try:
            self.after(0, self._refresh_list)
        except tk.TclError:
            pass

    def _refresh_list(self) -> None:
        for w in self._list_container.winfo_children():
            w.destroy()
        self._unit_count_label.configure(text=f"{len(self._units_data)} unit{'s' if len(self._units_data) != 1 else ''}")

        for unit in sorted(self._units_data, key=lambda u: u.get("unit_id", "")):
            self._build_unit_row(unit)

    def _build_unit_row(self, unit: Dict) -> None:
        uid = unit.get("unit_id", "")
        status = unit.get("status", "available")
        status_text, status_color = T.get_status_display(status)
        is_selected = uid == self._selected_unit
        bg = T.BG_TERTIARY if is_selected else T.BG_SECONDARY

        row = tk.Frame(self._list_container, bg=bg, cursor="hand2", pady=3)
        row.pack(fill=tk.X, padx=2, pady=1)

        strip = tk.Frame(row, bg=status_color, width=4)
        strip.pack(side=tk.LEFT, fill=tk.Y)
        strip.pack_propagate(False)

        content = tk.Frame(row, bg=bg)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=T.PAD_SM, pady=2)

        top = tk.Frame(content, bg=bg)
        top.pack(fill=tk.X)
        tk.Label(top, text=uid, bg=bg, fg=T.TEXT_ACCENT,
                 font=(T.FONT_MONO, 10, "bold"), width=12, anchor="w").pack(side=tk.LEFT)
        tk.Label(top, text=unit.get("name", ""), bg=bg, fg=T.TEXT_PRIMARY,
                 font=T.FONT_BODY, width=16, anchor="w").pack(side=tk.LEFT)
        tk.Label(top, text=status_text, bg=bg, fg=status_color,
                 font=(T.FONT_FAMILY, 8, "bold"), width=14, anchor="w").pack(side=tk.LEFT)
        call = unit.get("call_assigned", "")
        if call:
            tk.Label(top, text=f"#{call}", bg=bg, fg=T.ACCENT_BLUE,
                     font=T.FONT_SMALL).pack(side=tk.RIGHT, padx=T.PAD_SM)

        bottom = tk.Frame(content, bg=bg)
        bottom.pack(fill=tk.X)
        tk.Label(bottom, text=unit.get("location", "No location"), bg=bg,
                 fg=T.TEXT_MUTED, font=T.FONT_SMALL, anchor="w").pack(side=tk.LEFT)
        tk.Label(bottom, text=unit.get("vehicle", ""), bg=bg,
                 fg=T.TEXT_MUTED, font=T.FONT_SMALL).pack(side=tk.RIGHT, padx=T.PAD_SM)

        def on_click(e, unit_id=uid, unit_data=unit):
            self._selected_unit = unit_id
            self._show_detail(unit_data)
            self._refresh_list()

        for w in [row, content, top, bottom]:
            w.bind("<Button-1>", on_click)

    def _show_detail(self, unit: Dict) -> None:
        for w in self._detail_content.winfo_children():
            w.destroy()

        def row(label, value, color=T.TEXT_PRIMARY):
            f = tk.Frame(self._detail_content, bg=T.BG_SECONDARY)
            f.pack(fill=tk.X, pady=1)
            tk.Label(f, text=f"{label}:", bg=T.BG_SECONDARY, fg=T.TEXT_MUTED,
                     font=T.FONT_SMALL, width=13, anchor="e").pack(side=tk.LEFT)
            tk.Label(f, text=str(value), bg=T.BG_SECONDARY, fg=color,
                     font=T.FONT_BODY, anchor="w").pack(side=tk.LEFT, padx=T.PAD_XS)

        status = unit.get("status", "")
        _, sc = T.get_status_display(status)
        row("Unit ID",    unit.get("unit_id", ""), T.TEXT_ACCENT)
        row("Name",       unit.get("name", ""))
        row("Badge",      unit.get("badge", ""))
        row("Rank",       unit.get("rank", ""))
        row("Department", unit.get("department", ""))
        row("Status",     status.upper(), sc)
        row("10-Code",    unit.get("status_code", ""))
        row("Location",   unit.get("location", ""))
        row("Vehicle",    unit.get("vehicle", ""))
        row("Call",       unit.get("call_assigned", "None"), T.ACCENT_BLUE)
        row("Last Update",unit.get("last_update", "")[:19])

    def _add_unit_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Add / Update Unit")
        dialog.geometry("340x420")
        dialog.configure(bg=T.BG_SECONDARY)
        dialog.grab_set()

        fields = [
            ("Unit ID",     "unit_id",     "1-ADAM-12"),
            ("Name",        "name",        ""),
            ("Badge #",     "badge",       ""),
            ("Rank",        "rank",        "Officer"),
            ("Department",  "department",  "LSPD"),
            ("Vehicle",     "vehicle",     ""),
        ]
        entries = {}
        for label, key, default in fields:
            f = tk.Frame(dialog, bg=T.BG_SECONDARY)
            f.pack(fill=tk.X, padx=T.PAD_LG, pady=3)
            tk.Label(f, text=f"{label}:", bg=T.BG_SECONDARY, fg=T.TEXT_SECONDARY,
                     font=T.FONT_SMALL, width=12, anchor="e").pack(side=tk.LEFT)
            e = tk.Entry(f, bg=T.BG_TERTIARY, fg=T.TEXT_PRIMARY, font=T.FONT_BODY,
                         insertbackground=T.TEXT_PRIMARY, width=20)
            e.insert(0, default)
            e.pack(side=tk.LEFT, padx=T.PAD_XS)
            entries[key] = e

        def confirm():
            data = {k: e.get().strip() for k, e in entries.items()}
            if data.get("unit_id"):
                self.cad.upsert_unit(data)
            dialog.destroy()

        tk.Button(dialog, text="Add / Update Unit", bg=T.ACCENT_BLUE, fg=T.TEXT_PRIMARY,
                  font=T.FONT_BODY_BOLD, relief=tk.FLAT, command=confirm).pack(pady=T.PAD_MD)
