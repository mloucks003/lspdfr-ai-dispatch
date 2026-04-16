"""
BlueLineDispatchPro — Theme & Color System
Professional dark police-themed color palette and font constants.
"""

# ── Color Palette ─────────────────────────────────────────────────────────────
BG_PRIMARY       = "#0D0F14"   # Main window background
BG_SECONDARY     = "#141820"   # Panel / card background
BG_TERTIARY      = "#1C2230"   # Input fields, secondary panels
BG_HEADER        = "#0A0C10"   # Tab header, title bar

ACCENT_BLUE      = "#1E6FD9"   # Primary action blue (LSPD blue)
ACCENT_BLUE_DARK = "#154FA3"   # Darker blue for hover
ACCENT_BLUE_GLOW = "#2080FF"   # Glow effect / active states
ACCENT_RED       = "#D92B2B"   # Priority / alert / panic
ACCENT_RED_DARK  = "#A31E1E"   # Darker red
ACCENT_ORANGE    = "#E07B1A"   # Warning / medium priority
ACCENT_GREEN     = "#1EA35A"   # Available / code 4 / clear
ACCENT_YELLOW    = "#D4B84A"   # Caution / pending

TEXT_PRIMARY     = "#E8EDF5"   # Main text
TEXT_SECONDARY   = "#7B8BA0"   # Secondary / muted text
TEXT_MUTED       = "#4A5568"   # Very muted text, placeholders
TEXT_ACCENT      = "#5BA3FF"   # Highlighted / link text

BORDER_COLOR     = "#252D40"   # Panel borders
BORDER_ACTIVE    = "#1E6FD9"   # Active/focused border
DIVIDER          = "#1A2030"   # Subtle dividers

# Status colors
STATUS_AVAILABLE = ACCENT_GREEN
STATUS_BUSY      = ACCENT_ORANGE
STATUS_SCENE     = ACCENT_BLUE
STATUS_CODE6     = "#9B59B6"   # Purple — out of service
STATUS_OOS       = ACCENT_RED

# Priority colors
PRIORITY_COLORS  = {
    1: ACCENT_RED,
    2: ACCENT_ORANGE,
    3: ACCENT_YELLOW,
    4: ACCENT_BLUE,
    5: TEXT_SECONDARY,
}

# ── Font Definitions ──────────────────────────────────────────────────────────
FONT_FAMILY      = "Segoe UI"
FONT_MONO        = "Consolas"

FONT_TITLE       = (FONT_FAMILY, 18, "bold")
FONT_SUBTITLE    = (FONT_FAMILY, 13, "bold")
FONT_HEADER      = (FONT_FAMILY, 11, "bold")
FONT_BODY        = (FONT_FAMILY, 11)
FONT_BODY_BOLD   = (FONT_FAMILY, 11, "bold")
FONT_SMALL       = (FONT_FAMILY, 9)
FONT_MONO_BODY   = (FONT_MONO, 10)
FONT_MONO_LARGE  = (FONT_MONO, 12, "bold")

# ── Spacing & Sizing ──────────────────────────────────────────────────────────
PAD_XS   = 4
PAD_SM   = 8
PAD_MD   = 12
PAD_LG   = 16
PAD_XL   = 24

CORNER_RADIUS = 8
BORDER_WIDTH  = 1

# ── Status Code Mappings ──────────────────────────────────────────────────────
STATUS_DISPLAY = {
    "available": ("10-8 AVAILABLE", STATUS_AVAILABLE),
    "busy":      ("10-6 BUSY",      STATUS_BUSY),
    "on-scene":  ("10-23 ON SCENE", STATUS_SCENE),
    "code-6":    ("CODE 6",         STATUS_CODE6),
    "out-of-service": ("OOS",       STATUS_OOS),
}

CALL_STATUS_COLORS = {
    "pending":    ACCENT_YELLOW,
    "dispatched": ACCENT_BLUE,
    "on-scene":   ACCENT_GREEN,
    "clearing":   ACCENT_ORANGE,
    "closed":     TEXT_MUTED,
}


def get_priority_color(priority: int) -> str:
    return PRIORITY_COLORS.get(int(priority), TEXT_SECONDARY)


def get_status_display(status: str):
    return STATUS_DISPLAY.get(status.lower(), (status.upper(), TEXT_SECONDARY))


def get_call_status_color(status: str) -> str:
    return CALL_STATUS_COLORS.get(status.lower(), TEXT_SECONDARY)


def configure_ctk_theme() -> None:
    """Apply custom colors to CustomTkinter."""
    try:
        import customtkinter as ctk
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
    except Exception:
        pass
