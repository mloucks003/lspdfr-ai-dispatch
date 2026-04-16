"""
BlueLineDispatchPro — File Watcher
Uses watchdog to monitor AppData JSON files from the companion resource.
"""
import json
import logging
import os
import time
from pathlib import Path
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    logger.warning("watchdog not available — file watching disabled")


class _JsonFileHandler(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """Handles file modification events for JSON data files."""

    def __init__(self, watch_dir: Path, callbacks: Dict[str, Callable]):
        if WATCHDOG_AVAILABLE:
            super().__init__()
        self.watch_dir = watch_dir
        self.callbacks = callbacks  # filename.json → callback(data)
        self._last_modified: Dict[str, float] = {}
        self._debounce_ms = 200

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        filename = path.name

        # Debounce — ignore rapid duplicate events
        now = time.time() * 1000
        last = self._last_modified.get(filename, 0)
        if (now - last) < self._debounce_ms:
            return
        self._last_modified[filename] = now

        if filename in self.callbacks:
            self._load_and_dispatch(path, self.callbacks[filename])

    def _load_and_dispatch(self, path: Path, callback: Callable) -> None:
        """Read JSON file and call the callback with parsed data."""
        retries = 3
        for attempt in range(retries):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                callback(data)
                return
            except json.JSONDecodeError as e:
                if attempt < retries - 1:
                    time.sleep(0.05)
                else:
                    logger.warning(f"JSON parse error in {path.name}: {e}")
            except PermissionError:
                time.sleep(0.05)
            except Exception as e:
                logger.error(f"File watcher dispatch error ({path.name}): {e}")
                return


class FileWatcher:
    """
    Watches a directory for JSON file changes and fires callbacks.
    Used to receive live data from the FiveM companion resource.
    """

    def __init__(self, watch_dir: Path, settings: Dict):
        self.watch_dir = watch_dir
        self.settings = settings
        self._callbacks: Dict[str, Callable] = {}
        self._observer: Optional[object] = None
        self._handler: Optional[_JsonFileHandler] = None

    @property
    def fw_settings(self) -> Dict:
        return self.settings.get("file_watcher", {})

    def register(self, filename: str, callback: Callable) -> None:
        """Register a callback for a specific JSON filename."""
        self._callbacks[filename] = callback
        logger.debug(f"FileWatcher: registered handler for {filename}")

    def start(self) -> bool:
        """Start watching the directory."""
        if not WATCHDOG_AVAILABLE:
            logger.error("watchdog library not installed — file watching disabled")
            return False
        if not self.fw_settings.get("enabled", True):
            logger.info("File watcher disabled in settings")
            return False

        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self._handler = _JsonFileHandler(self.watch_dir, self._callbacks)
        self._observer = Observer()
        self._observer.schedule(self._handler, str(self.watch_dir), recursive=False)
        self._observer.start()
        logger.info(f"FileWatcher: watching {self.watch_dir}")

        # Immediately load any existing files
        self._load_existing_files()
        return True

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=3)
        logger.info("FileWatcher stopped")

    def _load_existing_files(self) -> None:
        """On startup, load existing JSON files to populate the CAD."""
        for filename, callback in self._callbacks.items():
            filepath = self.watch_dir / filename
            if filepath.exists():
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    callback(data)
                    logger.info(f"FileWatcher: loaded existing {filename}")
                except Exception as e:
                    logger.warning(f"Could not load existing {filename}: {e}")

    def write_json(self, filename: str, data: dict) -> bool:
        """Write a JSON file to the watch directory (for desktop → companion direction)."""
        filepath = self.watch_dir / filename
        try:
            import json as _json
            with open(filepath, "w", encoding="utf-8") as f:
                _json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"FileWatcher write error ({filename}): {e}")
            return False
