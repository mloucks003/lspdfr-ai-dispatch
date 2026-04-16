"""
BlueLineDispatchPro — Person Lookup Tab
Displays real ped/person data from LSPDFR companion.
"""
import tkinter as tk
from typing import Dict, Optional

from ui.components import theme as T


class PersonLookupTab(tk.Frame):
    def __init__(self, parent, cad_engine, **kwargs):
        super().__init__(parent, bg=T.BG_PRIMARY, **kwargs)
        self.cad = cad_engine
        self._build()
        self.cad.on("ped_updated", self._on_ped_updated)

    def _build(self) -> None:
        header = tk.Frame(self, bg=T.BG_HEADER, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="PERSON / PED LOOKUP", bg=T.BG_HEADER,
                 fg=T.TEXT_PRIMARY, font=T.FONT_SUBTITLE, padx=T.PAD_MD).pack(side=tk.LEFT, pady=T.PAD_SM)
        self._live_badge = tk.Label(header, text="● AWAITING DATA", bg=T.BG_HEADER,
                                    fg=T.TEXT_MUTED, font=(T.FONT_FAMILY, 9, "bold"))
        self._live_badge.pack(side=tk.LEFT)

        info = tk.Frame(self, bg=T.BG_TERTIARY, height=28)
        info.pack(fill=tk.X)
        info.pack_propagate(False)
        tk.Label(info, text="Auto-populates when you scan/run a ped in LSPDFR or FivePD.",
                 bg=T.BG_TERTIARY, fg=T.TEXT_MUTED, font=T.FONT_SMALL,
                 padx=T.PAD_MD).pack(side=tk.LEFT, pady=4)

        # Two-column layout
        content = tk.Frame(self, bg=T.BG_PRIMARY)
        content.pack(fill=tk.BOTH, expand=True, padx=T.PAD_SM, pady=T.PAD_SM)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        self._id_panel = self._make_panel(content, "IDENTITY")
        self._id_panel.grid(row=0, column=0, sticky="nsew", padx=(0, T.PAD_SM))

        self._record_panel = self._make_panel(content, "CRIMINAL RECORD & STATUS")
        self._record_panel.grid(row=0, column=1, sticky="nsew", padx=(T.PAD_SM, 0))

        self._render_empty()

    def _make_panel(self, parent, title: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=T.BG_SECONDARY)
        tk.Label(frame, text=title, bg=T.BG_SECONDARY, fg=T.TEXT_SECONDARY,
                 font=T.FONT_HEADER, padx=T.PAD_MD, pady=T.PAD_SM).pack(anchor="w")
        tk.Frame(frame, bg=T.BORDER_COLOR, height=1).pack(fill=tk.X, padx=T.PAD_SM)
        content = tk.Frame(frame, bg=T.BG_SECONDARY)
        content.pack(fill=tk.BOTH, expand=True, padx=T.PAD_MD, pady=T.PAD_MD)
        frame._content = content
        return frame

    def _render_empty(self) -> None:
        for panel in [self._id_panel, self._record_panel]:
            for w in panel._content.winfo_children():
                w.destroy()
            tk.Label(panel._content, text="No data — scan a ped in-game",
                     bg=T.BG_SECONDARY, fg=T.TEXT_MUTED, font=T.FONT_BODY).pack(expand=True)

    def _on_ped_updated(self, data: Dict) -> None:
        try:
            self.after(0, lambda: self._render_data(data))
        except tk.TclError:
            pass

    def _render_data(self, data: Dict) -> None:
        self._live_badge.configure(text="● LIVE DATA", fg=T.ACCENT_GREEN)
        self._render_identity(data)
        self._render_record(data)

    def _render_identity(self, data: Dict) -> None:
        content = self._id_panel._content
        for w in content.winfo_children():
            w.destroy()

        full_name = f"{data.get('first_name','')} {data.get('last_name','')}".strip()
        name_frame = tk.Frame(content, bg=T.BG_TERTIARY, pady=T.PAD_MD)
        name_frame.pack(fill=tk.X, pady=(0, T.PAD_MD))
        tk.Label(name_frame, text=full_name, bg=T.BG_TERTIARY,
                 fg=T.TEXT_PRIMARY, font=(T.FONT_FAMILY, 16, "bold")).pack()
        gender = data.get("gender", "")
        dob = data.get("dob", "")
        tk.Label(name_frame, text=f"{gender}  •  DOB: {dob}",
                 bg=T.BG_TERTIARY, fg=T.TEXT_MUTED, font=T.FONT_SMALL).pack()

        fields = [
            ("Ethnicity",   data.get("ethnicity", "")),
            ("Height",      f"{data.get('height_cm', '')} cm"),
            ("Weight",      f"{data.get('weight_kg', '')} kg"),
            ("Hair",        data.get("hair_color", "")),
            ("Eyes",        data.get("eye_color", "")),
            ("Address",     data.get("address", "")),
            ("Phone",       data.get("phone", "")),
        ]
        for label, value in fields:
            self._row(content, label, value)

        lic = data.get("license_status", "unknown")
        lic_color = T.ACCENT_GREEN if lic == "valid" else T.ACCENT_RED
        tk.Frame(content, bg=T.BORDER_COLOR, height=1).pack(fill=tk.X, pady=T.PAD_SM)
        self._row(content, "License", f"{lic.upper()} — Class {data.get('license_class','?')}", lic_color)
        self._row(content, "Expires", data.get("license_expiry", ""))

    def _render_record(self, data: Dict) -> None:
        content = self._record_panel._content
        for w in content.winfo_children():
            w.destroy()

        warrants = data.get("warrants", False)
        felony = data.get("felony_warrants", False)
        wanted = data.get("wanted", False)
        probation = data.get("probation", False)
        parole = data.get("parole", False)
        gang = data.get("gang_affiliated", False)

        def alert(text, color):
            f = tk.Frame(content, bg=color + "33", pady=4)
            f.pack(fill=tk.X, pady=2)
            tk.Label(f, text=text, bg=color + "33", fg=color,
                     font=(T.FONT_FAMILY, 9, "bold"), padx=T.PAD_SM).pack(anchor="w")

        if felony:
            alert("⚠  ACTIVE FELONY WARRANTS — USE CAUTION", T.ACCENT_RED)
        elif warrants:
            alert("⚑  ACTIVE MISDEMEANOR WARRANTS", T.ACCENT_ORANGE)
        if wanted:
            alert("🔴  SUBJECT IS WANTED — DETAIN ON SIGHT", T.ACCENT_RED)
        if probation:
            alert("📋  SUBJECT ON PROBATION", T.ACCENT_ORANGE)
        if parole:
            alert("📋  SUBJECT ON PAROLE", T.ACCENT_ORANGE)
        if gang:
            alert(f"⚑  GANG MEMBER — {data.get('gang_name','')}", T.ACCENT_ORANGE)

        if not any([felony, warrants, wanted, probation, parole, gang]):
            alert("✓  NO ACTIVE FLAGS", T.ACCENT_GREEN)

        tk.Frame(content, bg=T.BORDER_COLOR, height=1).pack(fill=tk.X, pady=T.PAD_SM)
        self._row(content, "Priors", str(data.get("priors", 0)))

        priors_list = data.get("prior_offenses", [])
        if priors_list:
            tk.Label(content, text="Prior Offenses:", bg=T.BG_SECONDARY,
                     fg=T.TEXT_MUTED, font=T.FONT_SMALL, anchor="w").pack(fill=tk.X)
            for offense in priors_list[:10]:
                tk.Label(content, text=f"  • {offense}", bg=T.BG_SECONDARY,
                         fg=T.TEXT_SECONDARY, font=T.FONT_SMALL, anchor="w").pack(fill=tk.X)

        notes = data.get("notes", "")
        if notes:
            tk.Frame(content, bg=T.BORDER_COLOR, height=1).pack(fill=tk.X, pady=T.PAD_SM)
            tk.Label(content, text="Notes:", bg=T.BG_SECONDARY, fg=T.TEXT_MUTED,
                     font=T.FONT_SMALL, anchor="w").pack(fill=tk.X)
            tk.Label(content, text=notes, bg=T.BG_TERTIARY, fg=T.TEXT_SECONDARY,
                     font=T.FONT_SMALL, wraplength=280, justify=tk.LEFT,
                     padx=T.PAD_SM, pady=T.PAD_SM).pack(fill=tk.X, pady=2)

    def _row(self, parent, label: str, value: str, color: str = T.TEXT_PRIMARY) -> None:
        f = tk.Frame(parent, bg=T.BG_SECONDARY)
        f.pack(fill=tk.X, pady=1)
        tk.Label(f, text=f"{label}:", bg=T.BG_SECONDARY, fg=T.TEXT_MUTED,
                 font=T.FONT_SMALL, width=12, anchor="e").pack(side=tk.LEFT)
        tk.Label(f, text=str(value), bg=T.BG_SECONDARY, fg=color,
                 font=T.FONT_BODY, anchor="w", wraplength=240).pack(side=tk.LEFT, padx=T.PAD_XS)
