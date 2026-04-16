"""
BlueLineDispatchPro — Vehicle Lookup Tab
Displays real plate/vehicle data received from LSPDFR via companion resource.
"""
import tkinter as tk
from typing import Dict, Optional

from ui.components import theme as T


class VehicleLookupTab(tk.Frame):
    def __init__(self, parent, cad_engine, **kwargs):
        super().__init__(parent, bg=T.BG_PRIMARY, **kwargs)
        self.cad = cad_engine
        self._current_data: Optional[Dict] = None
        self._build()
        self.cad.on("plate_updated", self._on_plate_updated)

    def _build(self) -> None:
        # Header
        header = tk.Frame(self, bg=T.BG_HEADER, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="VEHICLE / PLATE LOOKUP", bg=T.BG_HEADER,
                 fg=T.TEXT_PRIMARY, font=T.FONT_SUBTITLE, padx=T.PAD_MD).pack(side=tk.LEFT, pady=T.PAD_SM)
        self._live_badge = tk.Label(header, text="● AWAITING DATA", bg=T.BG_HEADER,
                                    fg=T.TEXT_MUTED, font=(T.FONT_FAMILY, 9, "bold"))
        self._live_badge.pack(side=tk.LEFT, pady=T.PAD_SM)

        # Info bar
        info = tk.Frame(self, bg=T.BG_TERTIARY, height=28)
        info.pack(fill=tk.X)
        info.pack_propagate(False)
        tk.Label(info, text="Data auto-populates when you run a plate in LSPDFR/FivePD. "
                             "Requires companion resource to be installed and connected.",
                 bg=T.BG_TERTIARY, fg=T.TEXT_MUTED, font=T.FONT_SMALL,
                 padx=T.PAD_MD).pack(side=tk.LEFT, pady=4)

        # Content area — 2 panels
        content = tk.Frame(self, bg=T.BG_PRIMARY)
        content.pack(fill=tk.BOTH, expand=True, padx=T.PAD_SM, pady=T.PAD_SM)
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        # Vehicle info panel (left)
        self._vehicle_panel = self._make_panel(content, "VEHICLE INFORMATION")
        self._vehicle_panel.grid(row=0, column=0, sticky="nsew", padx=(0, T.PAD_SM))

        # Owner info panel (right)
        self._owner_panel = self._make_panel(content, "REGISTERED OWNER")
        self._owner_panel.grid(row=0, column=1, sticky="nsew", padx=(T.PAD_SM, 0))

        self._render_empty()

    def _make_panel(self, parent, title: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=T.BG_SECONDARY, bd=1, relief=tk.FLAT)
        tk.Label(frame, text=title, bg=T.BG_SECONDARY, fg=T.TEXT_SECONDARY,
                 font=T.FONT_HEADER, padx=T.PAD_MD, pady=T.PAD_SM).pack(anchor="w")
        tk.Frame(frame, bg=T.BORDER_COLOR, height=1).pack(fill=tk.X, padx=T.PAD_SM)
        content = tk.Frame(frame, bg=T.BG_SECONDARY)
        content.pack(fill=tk.BOTH, expand=True, padx=T.PAD_MD, pady=T.PAD_MD)
        frame._content = content
        return frame

    def _render_empty(self) -> None:
        for panel in [self._vehicle_panel, self._owner_panel]:
            for w in panel._content.winfo_children():
                w.destroy()
            tk.Label(panel._content, text="No data — run a plate in-game",
                     bg=T.BG_SECONDARY, fg=T.TEXT_MUTED, font=T.FONT_BODY).pack(expand=True)

    def _on_plate_updated(self, data: Dict) -> None:
        self._current_data = data
        try:
            self.after(0, lambda: self._render_data(data))
        except tk.TclError:
            pass

    def _render_data(self, data: Dict) -> None:
        self._live_badge.configure(text="● LIVE DATA", fg=T.ACCENT_GREEN)
        self._render_vehicle(data)
        self._render_owner(data)

    def _render_vehicle(self, data: Dict) -> None:
        content = self._vehicle_panel._content
        for w in content.winfo_children():
            w.destroy()

        plate = data.get("plate", "???")
        stolen = data.get("stolen", False)
        flagged = data.get("flagged", False)
        vehicle = data.get("vehicle", {})
        reg = data.get("registration", {})

        # Big plate display
        plate_frame = tk.Frame(content, bg=T.BG_TERTIARY, pady=T.PAD_MD)
        plate_frame.pack(fill=tk.X, pady=(0, T.PAD_MD))
        tk.Label(plate_frame, text=plate, bg=T.BG_TERTIARY,
                 fg=T.ACCENT_BLUE_GLOW if not stolen else T.ACCENT_RED,
                 font=(T.FONT_MONO, 28, "bold")).pack()
        tk.Label(plate_frame, text=data.get("state", "SAN ANDREAS"),
                 bg=T.BG_TERTIARY, fg=T.TEXT_MUTED, font=T.FONT_SMALL).pack()

        # Alert banners
        if stolen:
            self._alert_banner(content, "⚠  VEHICLE REPORTED STOLEN", T.ACCENT_RED)
        if flagged:
            self._alert_banner(content, "⚑  VEHICLE FLAGGED", T.ACCENT_ORANGE)

        # Vehicle details
        fields = [
            ("Make", vehicle.get("make", "")),
            ("Model", vehicle.get("model", "")),
            ("Year", str(vehicle.get("year", ""))),
            ("Color", vehicle.get("color", "")),
            ("Type", vehicle.get("type", "").title()),
            ("VIN", vehicle.get("vin", "")),
        ]
        for label, value in fields:
            self._detail_row(content, label, value)

        # Registration
        tk.Frame(content, bg=T.BORDER_COLOR, height=1).pack(fill=tk.X, pady=T.PAD_SM)
        reg_status = reg.get("status", "unknown")
        reg_color = T.ACCENT_GREEN if reg_status == "valid" else T.ACCENT_RED
        self._detail_row(content, "Registration", reg_status.upper(), reg_color)
        self._detail_row(content, "Expires", reg.get("expiry", ""))
        ins = reg.get("insurance", "unknown")
        ins_color = T.ACCENT_GREEN if ins == "valid" else T.ACCENT_RED
        self._detail_row(content, "Insurance", ins.upper(), ins_color)
        self._detail_row(content, "Source", data.get("source", ""))

    def _render_owner(self, data: Dict) -> None:
        content = self._owner_panel._content
        for w in content.winfo_children():
            w.destroy()

        owner = data.get("owner", {})
        if not owner:
            tk.Label(content, text="No owner data", bg=T.BG_SECONDARY,
                     fg=T.TEXT_MUTED, font=T.FONT_BODY).pack(expand=True)
            return

        warrants = owner.get("warrants", False)
        felony = owner.get("felony_warrants", False)
        wanted = owner.get("wanted", False)

        # Name display
        name_frame = tk.Frame(content, bg=T.BG_TERTIARY, pady=T.PAD_MD)
        name_frame.pack(fill=tk.X, pady=(0, T.PAD_MD))
        full_name = f"{owner.get('first_name','')} {owner.get('last_name','')}".strip()
        tk.Label(name_frame, text=full_name, bg=T.BG_TERTIARY,
                 fg=T.TEXT_PRIMARY, font=(T.FONT_FAMILY, 16, "bold")).pack()

        # Alert banners
        if felony:
            self._alert_banner(content, "⚠  ACTIVE FELONY WARRANTS — APPROACH WITH CAUTION", T.ACCENT_RED)
        elif warrants:
            self._alert_banner(content, "⚑  ACTIVE MISDEMEANOR WARRANTS", T.ACCENT_ORANGE)
        if wanted:
            self._alert_banner(content, "🔴  SUBJECT IS WANTED", T.ACCENT_RED)
        if owner.get("gang_affiliated"):
            self._alert_banner(content, f"⚑  GANG AFFILIATED — {owner.get('gang_name','')}", T.ACCENT_ORANGE)

        # Owner fields
        lic_status = owner.get("license_status", "unknown")
        lic_color = T.ACCENT_GREEN if lic_status == "valid" else T.ACCENT_RED
        fields = [
            ("DOB", owner.get("dob", "")),
            ("Address", owner.get("address", "")),
            ("Phone", owner.get("phone", "")),
            ("License", lic_status.upper(), lic_color),
            ("Lic. Class", owner.get("license_class", "")),
            ("Priors", str(owner.get("priors", 0))),
        ]
        for item in fields:
            if len(item) == 3:
                self._detail_row(content, item[0], item[1], item[2])
            else:
                self._detail_row(content, item[0], item[1])

        notes = owner.get("notes", "")
        if notes:
            tk.Frame(content, bg=T.BORDER_COLOR, height=1).pack(fill=tk.X, pady=T.PAD_SM)
            tk.Label(content, text="Notes:", bg=T.BG_SECONDARY, fg=T.TEXT_MUTED,
                     font=T.FONT_SMALL, anchor="w").pack(fill=tk.X)
            tk.Label(content, text=notes, bg=T.BG_TERTIARY, fg=T.TEXT_SECONDARY,
                     font=T.FONT_SMALL, wraplength=280, justify=tk.LEFT,
                     padx=T.PAD_SM, pady=T.PAD_SM).pack(fill=tk.X, pady=2)

    def _alert_banner(self, parent, text: str, color: str) -> None:
        banner = tk.Frame(parent, bg=color + "33", pady=4)
        banner.pack(fill=tk.X, pady=2)
        tk.Label(banner, text=text, bg=color + "33", fg=color,
                 font=(T.FONT_FAMILY, 9, "bold"), padx=T.PAD_SM).pack(anchor="w")

    def _detail_row(self, parent, label: str, value: str, color: str = T.TEXT_PRIMARY) -> None:
        f = tk.Frame(parent, bg=T.BG_SECONDARY)
        f.pack(fill=tk.X, pady=1)
        tk.Label(f, text=f"{label}:", bg=T.BG_SECONDARY, fg=T.TEXT_MUTED,
                 font=T.FONT_SMALL, width=13, anchor="e").pack(side=tk.LEFT)
        tk.Label(f, text=str(value), bg=T.BG_SECONDARY, fg=color,
                 font=T.FONT_BODY, anchor="w").pack(side=tk.LEFT, padx=T.PAD_XS)
