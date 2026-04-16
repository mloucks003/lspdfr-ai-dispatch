"""
BlueLineDispatchPro — Dispatch Log Tab
Full chronological log of all CAD events with filtering and export.
"""
import tkinter as tk
from datetime import datetime, timezone
from typing import Dict, List

from ui.components import theme as T

CATEGORY_COLORS = {
    "call":       T.ACCENT_BLUE,
    "close":      T.TEXT_MUTED,
    "plate":      T.ACCENT_YELLOW,
    "ped":        T.ACCENT_YELLOW,
    "panic":      T.ACCENT_RED,
    "bolo":       T.ACCENT_ORANGE,
    "assignment": T.ACCENT_GREEN,
    "system":     T.TEXT_SECONDARY,
    "update":     T.ACCENT_BLUE,
    "general":    T.TEXT_PRIMARY,
}

CATEGORY_ICONS = {
    "call":       "📞",
    "close":      "✅",
    "plate":      "🚗",
    "ped":        "👤",
    "panic":      "🚨",
    "bolo":       "⚑",
    "assignment": "📋",
    "system":     "⚙",
    "update":     "🔄",
    "general":    "•",
}


class DispatchLogTab(tk.Frame):
    def __init__(self, parent, cad_engine, **kwargs):
        super().__init__(parent, bg=T.BG_PRIMARY, **kwargs)
        self.cad = cad_engine
        self._all_entries: List[Dict] = []
        self._filter_category = tk.StringVar(value="all")
        self._search_var = tk.StringVar()
        self._search_var.trace("w", lambda *args: self._refresh())
        self._build()
        self.cad.on("log_updated", self._on_log_updated)

    def _build(self) -> None:
        # Header
        header = tk.Frame(self, bg=T.BG_HEADER, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="DISPATCH LOG", bg=T.BG_HEADER,
                 fg=T.TEXT_PRIMARY, font=T.FONT_SUBTITLE, padx=T.PAD_MD).pack(side=tk.LEFT, pady=T.PAD_SM)

        # Export button
        tk.Button(header, text="Export Log", bg=T.BG_TERTIARY, fg=T.TEXT_PRIMARY,
                  font=T.FONT_SMALL, relief=tk.FLAT, cursor="hand2",
                  padx=T.PAD_SM, command=self._export_log).pack(side=tk.RIGHT, padx=T.PAD_MD, pady=10)

        # Clear button
        tk.Button(header, text="Clear", bg=T.BG_TERTIARY, fg=T.ACCENT_RED,
                  font=T.FONT_SMALL, relief=tk.FLAT, cursor="hand2",
                  padx=T.PAD_SM, command=self._clear_log).pack(side=tk.RIGHT, pady=10)

        # Filter / search bar
        filter_bar = tk.Frame(self, bg=T.BG_SECONDARY, height=38)
        filter_bar.pack(fill=tk.X, padx=T.PAD_SM, pady=(T.PAD_SM, 0))
        filter_bar.pack_propagate(False)

        tk.Label(filter_bar, text="Filter:", bg=T.BG_SECONDARY, fg=T.TEXT_MUTED,
                 font=T.FONT_SMALL, padx=T.PAD_SM).pack(side=tk.LEFT, pady=T.PAD_SM)

        categories = ["all", "call", "plate", "ped", "panic", "bolo", "system", "update"]
        for cat in categories:
            color = CATEGORY_COLORS.get(cat, T.TEXT_PRIMARY)
            tk.Radiobutton(
                filter_bar, text=cat.upper(), variable=self._filter_category,
                value=cat, command=self._refresh,
                bg=T.BG_SECONDARY, fg=color, selectcolor=T.BG_TERTIARY,
                activebackground=T.BG_SECONDARY, font=(T.FONT_FAMILY, 8),
                indicatoron=0, padx=6, pady=2, relief=tk.FLAT,
            ).pack(side=tk.LEFT, padx=1, pady=6)

        # Search box
        search_frame = tk.Frame(filter_bar, bg=T.BG_TERTIARY)
        search_frame.pack(side=tk.RIGHT, padx=T.PAD_MD, pady=6)
        tk.Label(search_frame, text="🔍", bg=T.BG_TERTIARY, fg=T.TEXT_MUTED).pack(side=tk.LEFT, padx=4)
        tk.Entry(search_frame, textvariable=self._search_var, bg=T.BG_TERTIARY,
                 fg=T.TEXT_PRIMARY, font=T.FONT_SMALL, insertbackground=T.TEXT_PRIMARY,
                 width=20, relief=tk.FLAT).pack(side=tk.LEFT, padx=4, pady=4)

        # Log area (monospaced for readability)
        log_frame = tk.Frame(self, bg=T.BG_SECONDARY)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=T.PAD_SM, pady=T.PAD_SM)

        scrollbar = tk.Scrollbar(log_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._log_text = tk.Text(
            log_frame,
            bg=T.BG_SECONDARY,
            fg=T.TEXT_PRIMARY,
            font=T.FONT_MONO_BODY,
            relief=tk.FLAT,
            wrap=tk.WORD,
            state=tk.DISABLED,
            yscrollcommand=scrollbar.set,
            selectbackground=T.ACCENT_BLUE_DARK,
            padx=T.PAD_SM,
            pady=T.PAD_SM,
            spacing1=2,
            spacing3=2,
        )
        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.configure(command=self._log_text.yview)

        # Configure text tags for colors
        for cat, color in CATEGORY_COLORS.items():
            self._log_text.tag_configure(cat, foreground=color)
        self._log_text.tag_configure("timestamp", foreground=T.TEXT_MUTED)
        self._log_text.tag_configure("icon", foreground=T.TEXT_SECONDARY)
        self._log_text.tag_configure("panic_line", background=T.ACCENT_RED + "33")

    def _on_log_updated(self, entry: Dict) -> None:
        self._all_entries.insert(0, entry)
        try:
            self.after(0, lambda e=entry: self._append_entry(e))
        except tk.TclError:
            pass

    def _append_entry(self, entry: Dict) -> None:
        """Append a single entry to the top of the log (most recent first)."""
        if not self._matches_filter(entry):
            return
        self._log_text.configure(state=tk.NORMAL)
        cat = entry.get("category", "general")
        ts = entry.get("timestamp", "")
        ts_display = ts[11:19] if len(ts) >= 19 else ts
        icon = CATEGORY_ICONS.get(cat, "•")
        msg = entry.get("message", "")

        # Insert at top
        self._log_text.insert("1.0", "\n")
        self._log_text.insert("1.0", f"  {msg}", cat if cat != "panic" else "")
        if cat == "panic":
            line_start = self._log_text.index("1.0")
            self._log_text.tag_add("panic_line", "1.0", "1.end")
        self._log_text.insert("1.0", f" {icon} ", "icon")
        self._log_text.insert("1.0", f"[{ts_display}]", "timestamp")
        self._log_text.configure(state=tk.DISABLED)

    def _matches_filter(self, entry: Dict) -> bool:
        cat_filter = self._filter_category.get()
        if cat_filter != "all" and entry.get("category") != cat_filter:
            return False
        search = self._search_var.get().strip().lower()
        if search and search not in entry.get("message", "").lower():
            return False
        return True

    def _refresh(self) -> None:
        """Rebuild the entire log view from cached entries (after filter change)."""
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state=tk.DISABLED)
        for entry in self._all_entries:
            self._append_entry(entry)

    def _clear_log(self) -> None:
        self._all_entries.clear()
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.configure(state=tk.DISABLED)

    def _export_log(self) -> None:
        """Export dispatch log to a text file."""
        import tkinter.filedialog as fd
        from config import APP_DATA_DIR
        filepath = fd.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
            initialdir=str(APP_DATA_DIR),
            initialfile=f"dispatch_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            title="Export Dispatch Log",
        )
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write("=== BlueLineDispatchPro Dispatch Log ===\n")
                    f.write(f"Exported: {datetime.now().isoformat()}\n\n")
                    for entry in reversed(self._all_entries):
                        ts = entry.get("timestamp", "")[:19]
                        cat = entry.get("category", "").upper()
                        msg = entry.get("message", "")
                        f.write(f"[{ts}] [{cat}] {msg}\n")
            except Exception as e:
                tk.messagebox.showerror("Export Error", str(e))
