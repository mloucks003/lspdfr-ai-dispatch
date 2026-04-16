"""
BlueLineDispatchPro — Active Calls Tab
Displays and manages active calls with filtering, status updates, and unit assignment.
"""
import tkinter as tk
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

try:
    import customtkinter as ctk
except ImportError:
    import tkinter as ctk

from ui.components import theme as T


class ActiveCallsTab(tk.Frame):
    def __init__(self, parent, cad_engine, on_assign_unit: Optional[Callable] = None, **kwargs):
        super().__init__(parent, bg=T.BG_PRIMARY, **kwargs)
        self.cad = cad_engine
        self.on_assign_unit = on_assign_unit
        self._filter_var = tk.StringVar(value="all")
        self._calls_data: List[Dict] = []
        self._selected_call_id: Optional[str] = None
        self._build()
        self.cad.on("calls_updated", self._on_calls_updated)

    def _build(self) -> None:
        # ── Header bar ──────────────────────────────────────────────────────
        header = tk.Frame(self, bg=T.BG_HEADER, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(header, text="ACTIVE CALLS", bg=T.BG_HEADER, fg=T.TEXT_PRIMARY,
                 font=T.FONT_SUBTITLE, padx=T.PAD_MD).pack(side=tk.LEFT, pady=T.PAD_SM)

        self._call_count_label = tk.Label(header, text="0 calls", bg=T.BG_HEADER,
                                          fg=T.TEXT_MUTED, font=T.FONT_SMALL)
        self._call_count_label.pack(side=tk.LEFT, pady=T.PAD_SM)

        # Filter buttons
        filter_frame = tk.Frame(header, bg=T.BG_HEADER)
        filter_frame.pack(side=tk.RIGHT, padx=T.PAD_MD, pady=T.PAD_SM)
        for label, value in [("All", "all"), ("Priority 1-2", "urgent"), ("Open", "open")]:
            tk.Radiobutton(
                filter_frame, text=label, variable=self._filter_var,
                value=value, command=self._refresh_table,
                bg=T.BG_HEADER, fg=T.TEXT_SECONDARY,
                selectcolor=T.BG_SECONDARY, activebackground=T.BG_HEADER,
                font=T.FONT_SMALL, indicatoron=0, padx=8, pady=2,
                relief=tk.FLAT, bd=0,
            ).pack(side=tk.LEFT, padx=2)

        # ── Main content: calls list + detail panel ──────────────────────────
        content = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=T.BORDER_COLOR,
                                  sashwidth=4, sashrelief=tk.FLAT)
        content.pack(fill=tk.BOTH, expand=True, padx=T.PAD_SM, pady=T.PAD_SM)

        # Calls list (left)
        list_frame = tk.Frame(content, bg=T.BG_SECONDARY)
        content.add(list_frame, width=600, minsize=300)
        self._build_call_list(list_frame)

        # Detail panel (right)
        detail_frame = tk.Frame(content, bg=T.BG_SECONDARY)
        content.add(detail_frame, minsize=280)
        self._build_detail_panel(detail_frame)

    def _build_call_list(self, parent: tk.Frame) -> None:
        cols = ("ID", "Priority", "Type", "Location", "Status", "Units", "Time")
        col_widths = [60, 60, 130, 180, 90, 60, 70]

        # Column headers
        header_row = tk.Frame(parent, bg=T.BG_TERTIARY, height=30)
        header_row.pack(fill=tk.X)
        header_row.pack_propagate(False)
        for col, width in zip(cols, col_widths):
            tk.Label(header_row, text=col, bg=T.BG_TERTIARY, fg=T.TEXT_SECONDARY,
                     font=T.FONT_SMALL, width=width//8, anchor="w").pack(
                side=tk.LEFT, padx=T.PAD_XS, pady=4)

        # Scrollable list area
        scroll_canvas = tk.Canvas(parent, bg=T.BG_SECONDARY, highlightthickness=0)
        scrollbar = tk.Scrollbar(parent, orient=tk.VERTICAL, command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._list_container = tk.Frame(scroll_canvas, bg=T.BG_SECONDARY)
        self._list_window = scroll_canvas.create_window((0, 0), window=self._list_container, anchor="nw")
        self._list_container.bind("<Configure>", lambda e: scroll_canvas.configure(
            scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.bind("<Configure>", lambda e: scroll_canvas.itemconfig(
            self._list_window, width=e.width))
        self._scroll_canvas = scroll_canvas

    def _build_detail_panel(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="CALL DETAILS", bg=T.BG_SECONDARY, fg=T.TEXT_SECONDARY,
                 font=T.FONT_HEADER, padx=T.PAD_MD, pady=T.PAD_SM).pack(anchor="w")

        sep = tk.Frame(parent, bg=T.BORDER_COLOR, height=1)
        sep.pack(fill=tk.X, padx=T.PAD_SM)

        self._detail_frame = tk.Frame(parent, bg=T.BG_SECONDARY)
        self._detail_frame.pack(fill=tk.BOTH, expand=True, padx=T.PAD_MD, pady=T.PAD_SM)
        self._show_empty_detail()

        # Action buttons
        btn_frame = tk.Frame(parent, bg=T.BG_SECONDARY, pady=T.PAD_SM)
        btn_frame.pack(fill=tk.X, padx=T.PAD_MD, pady=(0, T.PAD_SM))

        self._btn_close = tk.Button(
            btn_frame, text="Close Call", bg=T.ACCENT_RED, fg=T.TEXT_PRIMARY,
            font=T.FONT_BODY_BOLD, relief=tk.FLAT, cursor="hand2",
            command=self._close_selected_call, state=tk.DISABLED,
        )
        self._btn_close.pack(fill=tk.X, pady=2)

        self._btn_assign = tk.Button(
            btn_frame, text="Assign Unit", bg=T.ACCENT_BLUE, fg=T.TEXT_PRIMARY,
            font=T.FONT_BODY_BOLD, relief=tk.FLAT, cursor="hand2",
            command=self._assign_unit_dialog, state=tk.DISABLED,
        )
        self._btn_assign.pack(fill=tk.X, pady=2)

        self._btn_update = tk.Button(
            btn_frame, text="Update Status", bg=T.BG_TERTIARY, fg=T.TEXT_PRIMARY,
            font=T.FONT_BODY, relief=tk.FLAT, cursor="hand2",
            command=self._update_status_dialog, state=tk.DISABLED,
        )
        self._btn_update.pack(fill=tk.X, pady=2)

    def _show_empty_detail(self) -> None:
        for w in self._detail_frame.winfo_children():
            w.destroy()
        tk.Label(self._detail_frame, text="Select a call to view details",
                 bg=T.BG_SECONDARY, fg=T.TEXT_MUTED, font=T.FONT_BODY,
                 wraplength=240).pack(expand=True)

    def _show_call_detail(self, call: Dict) -> None:
        for w in self._detail_frame.winfo_children():
            w.destroy()

        priority = int(call.get("priority", 3))
        pcolor = T.get_priority_color(priority)

        def row(label: str, value: str, color: str = T.TEXT_PRIMARY):
            f = tk.Frame(self._detail_frame, bg=T.BG_SECONDARY)
            f.pack(fill=tk.X, pady=1)
            tk.Label(f, text=f"{label}:", bg=T.BG_SECONDARY, fg=T.TEXT_MUTED,
                     font=T.FONT_SMALL, width=12, anchor="e").pack(side=tk.LEFT)
            tk.Label(f, text=str(value), bg=T.BG_SECONDARY, fg=color,
                     font=T.FONT_BODY, anchor="w", wraplength=180).pack(side=tk.LEFT, padx=T.PAD_XS)

        row("Call ID", call.get("call_id", ""), T.TEXT_ACCENT)
        row("Type", call.get("type", ""), T.TEXT_PRIMARY)
        row("Priority", f"P{priority}", pcolor)
        row("Status", call.get("status", "").upper(), T.get_call_status_color(call.get("status", "")))
        row("Location", call.get("location", ""))
        row("Description", call.get("description", ""))
        row("Caller", call.get("caller", ""))
        row("Code", call.get("code", ""))
        units = ", ".join(call.get("assigned_units", [])) or "Unassigned"
        row("Units", units, T.ACCENT_BLUE if units != "Unassigned" else T.ACCENT_ORANGE)
        row("Source", call.get("source", ""))

        # Timestamp
        ts = call.get("timestamp", "")
        if ts:
            try:
                from dateutil import parser
                dt = parser.parse(ts)
                ts_display = dt.strftime("%H:%M:%S")
            except Exception:
                ts_display = ts[:19]
            row("Time", ts_display)

        notes = call.get("notes", "")
        if notes:
            tk.Label(self._detail_frame, text="Notes:", bg=T.BG_SECONDARY,
                     fg=T.TEXT_MUTED, font=T.FONT_SMALL, anchor="w").pack(fill=tk.X, pady=(T.PAD_SM, 0))
            tk.Label(self._detail_frame, text=notes, bg=T.BG_TERTIARY,
                     fg=T.TEXT_SECONDARY, font=T.FONT_SMALL,
                     wraplength=240, justify=tk.LEFT, padx=T.PAD_SM, pady=T.PAD_SM,
                     anchor="w").pack(fill=tk.X, pady=2)

    def _on_calls_updated(self, calls: List[Dict]) -> None:
        self._calls_data = calls
        try:
            self.after(0, self._refresh_table)
        except tk.TclError:
            pass

    def _get_filtered_calls(self) -> List[Dict]:
        f = self._filter_var.get()
        calls = self._calls_data
        if f == "urgent":
            calls = [c for c in calls if int(c.get("priority", 5)) <= 2]
        elif f == "open":
            calls = [c for c in calls if c.get("status") not in ("closed",)]
        return calls

    def _refresh_table(self) -> None:
        for w in self._list_container.winfo_children():
            w.destroy()

        calls = self._get_filtered_calls()
        open_calls = [c for c in calls if c.get("status") != "closed"]
        self._call_count_label.configure(text=f"{len(open_calls)} active call{'s' if len(open_calls) != 1 else ''}")

        for call in calls:
            self._build_call_row(call)

    def _build_call_row(self, call: Dict) -> None:
        cid = call.get("call_id", "")
        priority = int(call.get("priority", 3))
        pcolor = T.get_priority_color(priority)
        status_color = T.get_call_status_color(call.get("status", ""))
        is_selected = cid == self._selected_call_id
        bg = T.BG_TERTIARY if is_selected else T.BG_SECONDARY

        row_frame = tk.Frame(self._list_container, bg=bg, cursor="hand2", pady=2)
        row_frame.pack(fill=tk.X, padx=2, pady=1)

        # Priority indicator strip
        strip = tk.Frame(row_frame, bg=pcolor, width=4)
        strip.pack(side=tk.LEFT, fill=tk.Y)
        strip.pack_propagate(False)

        content = tk.Frame(row_frame, bg=bg)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=T.PAD_SM, pady=4)

        top = tk.Frame(content, bg=bg)
        top.pack(fill=tk.X)

        tk.Label(top, text=f"#{cid}", bg=bg, fg=T.TEXT_ACCENT,
                 font=T.FONT_MONO_BODY).pack(side=tk.LEFT)
        tk.Label(top, text=f"  P{priority}", bg=bg, fg=pcolor,
                 font=(T.FONT_FAMILY, 9, "bold")).pack(side=tk.LEFT)
        tk.Label(top, text=f"  {call.get('type','')}", bg=bg, fg=T.TEXT_PRIMARY,
                 font=T.FONT_BODY_BOLD).pack(side=tk.LEFT)
        status_lbl = tk.Label(top, text=call.get("status","").upper(), bg=bg,
                               fg=status_color, font=T.FONT_SMALL)
        status_lbl.pack(side=tk.RIGHT, padx=T.PAD_SM)

        bottom = tk.Frame(content, bg=bg)
        bottom.pack(fill=tk.X, pady=1)
        tk.Label(bottom, text=call.get("location", ""), bg=bg, fg=T.TEXT_SECONDARY,
                 font=T.FONT_SMALL, anchor="w").pack(side=tk.LEFT)

        # Bind click events
        def on_click(e, call_id=cid, call_data=call):
            self._selected_call_id = call_id
            self._show_call_detail(call_data)
            self._btn_close.configure(state=tk.NORMAL if call_data.get("status") != "closed" else tk.DISABLED)
            self._btn_assign.configure(state=tk.NORMAL)
            self._btn_update.configure(state=tk.NORMAL)
            self._refresh_table()

        for widget in [row_frame, content, top, bottom]:
            widget.bind("<Button-1>", on_click)

    def _close_selected_call(self) -> None:
        if self._selected_call_id:
            self.cad.close_call(self._selected_call_id)
            self._selected_call_id = None
            self._show_empty_detail()
            self._btn_close.configure(state=tk.DISABLED)
            self._btn_assign.configure(state=tk.DISABLED)
            self._btn_update.configure(state=tk.DISABLED)

    def _assign_unit_dialog(self) -> None:
        if not self._selected_call_id:
            return
        dialog = tk.Toplevel(self)
        dialog.title("Assign Unit")
        dialog.geometry("300x180")
        dialog.configure(bg=T.BG_SECONDARY)
        dialog.grab_set()

        tk.Label(dialog, text="Unit ID:", bg=T.BG_SECONDARY, fg=T.TEXT_PRIMARY,
                 font=T.FONT_BODY).pack(pady=(T.PAD_LG, T.PAD_SM))
        entry = tk.Entry(dialog, bg=T.BG_TERTIARY, fg=T.TEXT_PRIMARY,
                         font=T.FONT_BODY, insertbackground=T.TEXT_PRIMARY, width=20)
        entry.pack(pady=T.PAD_SM)
        entry.focus()

        def confirm():
            uid = entry.get().strip()
            if uid and self._selected_call_id:
                for call in self.cad.active_calls:
                    if call["call_id"] == self._selected_call_id:
                        units = call.get("assigned_units", [])
                        if uid not in units:
                            units.append(uid)
                        call["assigned_units"] = units
                        self.cad.emit("calls_updated", self.cad.active_calls)
                        self.cad.log(f"Unit {uid} assigned to call #{self._selected_call_id}", "assignment")
                        break
            dialog.destroy()

        tk.Button(dialog, text="Assign", bg=T.ACCENT_BLUE, fg=T.TEXT_PRIMARY,
                  font=T.FONT_BODY_BOLD, relief=tk.FLAT, command=confirm).pack(pady=T.PAD_SM)

    def _update_status_dialog(self) -> None:
        if not self._selected_call_id:
            return
        statuses = ["pending", "dispatched", "on-scene", "clearing", "closed"]
        dialog = tk.Toplevel(self)
        dialog.title("Update Call Status")
        dialog.geometry("280x200")
        dialog.configure(bg=T.BG_SECONDARY)
        dialog.grab_set()

        tk.Label(dialog, text="Select New Status:", bg=T.BG_SECONDARY, fg=T.TEXT_PRIMARY,
                 font=T.FONT_BODY).pack(pady=(T.PAD_LG, T.PAD_SM))

        var = tk.StringVar(value="dispatched")
        for s in statuses:
            tk.Radiobutton(dialog, text=s.upper(), variable=var, value=s,
                           bg=T.BG_SECONDARY, fg=T.TEXT_PRIMARY,
                           selectcolor=T.BG_TERTIARY, font=T.FONT_SMALL,
                           activebackground=T.BG_SECONDARY).pack(anchor="w", padx=T.PAD_LG)

        def confirm():
            self.cad.update_call(self._selected_call_id, {"status": var.get()})
            dialog.destroy()

        tk.Button(dialog, text="Update", bg=T.ACCENT_BLUE, fg=T.TEXT_PRIMARY,
                  font=T.FONT_BODY_BOLD, relief=tk.FLAT, command=confirm).pack(pady=T.PAD_SM)
