"""
BlueLineDispatchPro — Config Package
Handles loading/saving settings and resolving paths.
"""
import os
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# ── Path Resolution ────────────────────────────────────────────────────────────
def _get_base_dir() -> Path:
    """Get base directory of the application (handles both script and .exe)."""
    import sys
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent

BASE_DIR = _get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
AUDIO_DIR = BASE_DIR / "audio"
MODELS_DIR = BASE_DIR / "models"

# AppData directory for runtime data files from companion
APP_DATA_DIR = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / "BlueLineDispatchPro"
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Log directory
LOG_DIR = APP_DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = CONFIG_DIR / "settings.json"
AUDIO_MAP_FILE = CONFIG_DIR / "audio_map.json"

# Runtime data files (written by companion, read by desktop)
PLATE_DATA_FILE    = APP_DATA_DIR / "plate_data.json"
PED_DATA_FILE      = APP_DATA_DIR / "ped_data.json"
ACTIVE_CALLS_FILE  = APP_DATA_DIR / "active_calls.json"
UNIT_STATUS_FILE   = APP_DATA_DIR / "unit_status.json"
BOLOS_FILE         = APP_DATA_DIR / "bolos.json"


def _deep_merge(base: Dict, override: Dict) -> Dict:
    """Recursively merge override into base dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_settings() -> Dict[str, Any]:
    """Load settings from disk, falling back to defaults."""
    defaults: Dict[str, Any] = {}
    default_path = CONFIG_DIR / "settings.json"

    if default_path.exists():
        try:
            with open(default_path, "r", encoding="utf-8") as f:
                defaults = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load default settings: {e}")

    # Load user overrides from AppData
    user_settings_file = APP_DATA_DIR / "settings_user.json"
    if user_settings_file.exists():
        try:
            with open(user_settings_file, "r", encoding="utf-8") as f:
                user = json.load(f)
            defaults = _deep_merge(defaults, user)
        except Exception as e:
            logger.warning(f"Failed to load user settings: {e}")

    return defaults


def save_settings(settings: Dict[str, Any]) -> bool:
    """Save user settings to AppData."""
    user_settings_file = APP_DATA_DIR / "settings_user.json"
    try:
        with open(user_settings_file, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        return False


def load_audio_map() -> Dict[str, Any]:
    """Load audio category mappings."""
    if AUDIO_MAP_FILE.exists():
        try:
            with open(AUDIO_MAP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load audio map: {e}")
    return {}


def setup_logging(settings: Dict[str, Any]) -> None:
    """Configure application-wide logging."""
    level = getattr(logging, settings.get("app", {}).get("log_level", "INFO"), logging.INFO)
    log_file = LOG_DIR / "bldp.log"
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    logger.info(f"BlueLineDispatchPro logging initialized. Log: {log_file}")
