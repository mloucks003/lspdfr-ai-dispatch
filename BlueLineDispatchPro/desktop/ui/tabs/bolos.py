"""
BlueLineDispatchPro — BOLOs & Warrants Tab
Manage Be-On-Lookout entries, active warrants, and stolen vehicles.
"""
import tkinter as tk
from typing import Dict, List, Optional

from ui.components import theme as T


class BOLOsTab(tk.Frame):
    def __init__(self, parent, cad_engine, **kwargs):
        super().__init__(parent, bg=T.BG_PRIMARY, **kwargs)
        self.cad = cad_engine
        self._bolo_data: List[Dict] = []
        self._build()
        self.cad.on("bolos_updated", self._on_bolos_updated)

    def _build(self) -> None:
        header = tk.Frame(self, bg=T.BG_HEADER, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="BOLOs & WARRANTS", bg=T.BG_HEADER,
                 fg=T.TEXT_PRIMARY, font=T.FONT_SUBTITLE, padx=T.PAD_MD).pack(side=tk.LEFT, pady=T.PAD_SM)
        self._count_label = tk.Label(header, text="0 active", bg=T.BG_HEADER,
                                     fg=T.TEXT_MUTED, font=T.FONT_SMALL)
        self._count_label.pack(side=tk.LEFT)
        tk.Button(header, text="+ Issue BOLO", bg=T.ACCENT_ORANGE, fg=T.TEXT_PRIMARY,
                  font=T.FONT_BODY, relief=tk.FLAT, cursor="hand2",
                  padx=T.PAD_MD, command=self._issue_bolo_dialog).pack(
            side=tk.RIGHT, padx=T.PAD_MD, pady=8)

        # Column headers
        cols = [("Type", 70), ("Priority", 65), ("Subject", 180), ("Reason", 120), ("Description", 200), ("Issued", 70)]
        header_row = tk.Frame(self, bg=T.BG_TERTIARY, height=30)
        header_row.pack(fill=tk.X, padx=T.PAD_SM)
        header_row.pack_propagate(False)
        for col, width in cols:
            tk.Label(header_row, text=col, bg=T.BG_TERTIARY, fg=T.TEXT_SECONDARY,
                     font=T.FONT_SMALL, width=width//7, anchor="w").pack(side=tk.LEFT, padx=T.PAD_XS, pady=4)

        # Scrollable list
        canvas = tk.Canvas(self, bg=T.BG_SECONDARY, highlightthickness=0)
        scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, T.PAD_SM), pady=T.PAD_SM)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=T.PAD_SM, pady=T.PAD_SM)

        self._list_container = tk.Frame(canvas, bg=T.BG_SECONDARY)
        win = canvas.create_window((0, 0), window=self._list_container, anchor="nw")
        self._list_container.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))

    def _on_bolos_updated(self, bolos: List[Dict]) -> None:
        self._bolo_data = bolos
        try:
            self.after(0, self._refresh)
        except tk.TclError:
            pass

    def _refresh(self) -> None:
        for w in self._list_container.winfo_children():
            w.destroy()
        active = [b for b in self._bolo_data if b.get("active", True)]
        self._count_label.configure(text=f"{len(active)} active")
        for bolo in active:
            self._build_bolo_row(bolo)

    def _build_bolo_row(self, bolo: Dict) -> None:
        priority = int(bolo.get("priority", 2))
        pcolor = T.get_priority_color(priority)
        btype = bolo.get("type", "person").upper()
        type_color = {
            "VEHICLE": T.ACCENT_BLUE,
            "PERSON": T.ACCENT_RED,
            "PROPERTY": T.ACCENT_ORANGE,
        }.get(btype, T.TEXT_SECONDARY)

        row = tk.Frame(self._list_container, bg=T.BG_SECONDARY, pady=3, cursor="hand2")
        row.pack(fill=tk.X, padx=2, pady=1)

        strip = tk.Frame(row, bg=pcolor, width=4)
        strip.pack(side=tk.LEFT, fill=tk.Y)
        strip.pack_propagate(False)

        content = tk.Frame(row, bg=T.BG_SECONDARY)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=T.PAD_SM, pady=2)

        top = tk.Frame(content, bg=T.BG_SECONDARY)
        top.pack(fill=tk.X)
        tk.Label(top, text=f"[{btype}]", bg=T.BG_SECONDARY, fg=type_color,
                 font=(T.FONT_FAMILY, 9, "bold"), width=9, anchor="w").pack(side=tk.LEFT)
        tk.Label(top, text=f"P{priority}", bg=T.BG_SECONDARY, fg=pcolor,
                 font=(T.FONT_FAMILY, 9, "bold"), width=4, anchor="w").pack(side=tk.LEFT)
        tk.Label(top, text=bolo.get("subject", ""), bg=T.BG_SECONDARY, fg=T.TEXT_PRIMARY,
                 font=T.FONT_BODY_BOLD, anchor="w").pack(side=tk.LEFT, padx=T.PAD_SM)
        tk.Label(top, text=bolo.get("reason", "").upper(), bg=T.BG_SECONDARY,
                 fg=T.ACCENT_ORANGE, font=T.FONT_SMALL).pack(side=tk.RIGHT, padx=T.PAD_SM)

        bottom = tk.Frame(content, bg=T.BG_SECONDARY)
        bottom.pack(fill=tk.X)
        desc = bolo.get("description", "")
        plate = bolo.get("plate", "")
        full_desc = f"{desc}  {f'PLATE: {plate}' if plate else ''}".strip()
        tk.Label(bottom, text=full_desc, bg=T.BG_SECONDARY, fg=T.TEXT_SECONDARY,
                 font=T.FONT_SMALL, anchor="w").pack(side=tk.LEFT)

        # Cancel button
        bid = bolo.get("bolo_id", "")
        tk.Button(
            row, text="✕", bg=T.BG_TERTIARY, fg=T.TEXT_MUTED,
            font=T.FONT_SMALL, relief=tk.FLAT, cursor="hand2",
            command=lambda b=bid: self._cancel_bolo(b),
        ).pack(side=tk.RIGHT, padx=T.PAD_SM)

    def _cancel_bolo(self, bolo_id: str) -> None:
        for bolo in self._bolo_data:
            if bolo.get("bolo_id") == bolo_id:
                bolo["active"] = False
                self.cad.log(f"[BOLO] Cancelled: {bolo.get('subject','')}", "bolo")
                self.cad.emit("bolos_updated", self._bolo_data)
                break

    def _issue_bolo_dialog(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Issue BOLO")
        dialog.geometry("380x420")
        dialog.configure(bg=T.BG_SECONDARY)
        dialog.grab_set()

        tk.Label(dialog, text="ISSUE NEW BOLO", bg=T.BG_SECONDARY,
                 fg=T.TEXT_PRIMARY, font=T.FONT_SUBTITLE, pady=T.PAD_MD).pack()

        fields = [
            ("Type",        "type",        "person"),
            ("Subject",     "subject",     ""),
            ("Description", "description", ""),
            ("Reason",      "reason",      "warrant"),
            ("Plate",       "plate",       ""),
            ("Issued By",   "issued_by",   "Dispatch"),
        ]
        entries = {}
        for label, key, default in fields:
            f = tk.Frame(dialog, bg=T.BG_SECONDARY)
            f.pack(fill=tk.X, padx=T.PAD_LG, pady=3)
            tk.Label(f, text=f"{label}:", bg=T.BG_SECONDARY, fg=T.TEXT_SECONDARY,
                     font=T.FONT_SMALL, width=13, anchor="e").pack(side=tk.LEFT)
            e = tk.Entry(f, bg=T.BG_TERTIARY, fg=T.TEXT_PRIMARY, font=T.FONT_BODY,
                         insertbackground=T.TEXT_PRIMARY, width=22)
            e.insert(0, default)
            e.pack(side=tk.LEFT, padx=T.PAD_XS)
            entries[key] = e

        priority_var = tk.IntVar(value=2)
        pf = tk.Frame(dialog, bg=T.BG_SECONDARY)
        pf.pack(fill=tk.X, padx=T.PAD_LG, pady=3)
        tk.Label(pf, text="Priority:", bg=T.BG_SECONDARY, fg=T.TEXT_SECONDARY,
                 font=T.FONT_SMALL, width=13, anchor="e").pack(side=tk.LEFT)
        for p in range(1, 6):
            tk.Radiobutton(pf, text=str(p), variable=priority_var, value=p,
                           bg=T.BG_SECONDARY, fg=T.TEXT_PRIMARY,
                           selectcolor=T.BG_TERTIARY, font=T.FONT_SMALL).pack(side=tk.LEFT)

        def confirm():
            data = {k: e.get().strip() for k, e in entries.items()}
            data["priority"] = priority_var.get()
            if data.get("subject"):
                self.cad.add_bolo(data)
            dialog.destroy()

        tk.Button(dialog, text="Issue BOLO", bg=T.ACCENT_ORANGE, fg=T.TEXT_PRIMARY,
                  font=T.FONT_BODY_BOLD, relief=tk.FLAT, command=confirm).pack(pady=T.PAD_MD)
