"""
BlueLineDispatchPro — Main Entry Point
Bootstraps all services and launches the UI.
"""
import os
import sys
import logging

# Ensure project root is on path (works for both script and .exe)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import (
    load_settings, setup_logging, load_audio_map,
    AUDIO_DIR, APP_DATA_DIR, PLATE_DATA_FILE,
    PED_DATA_FILE, ACTIVE_CALLS_FILE, UNIT_STATUS_FILE, BOLOS_FILE,
)
from core.cad_engine import CADEngine
from core.audio_player import AudioPlayer
from core.keyword_listener import KeywordListener
from core.api_server import APIServer
from core.file_watcher import FileWatcher
from core.scanner_mode import ScannerMode
from core.hotkey_manager import HotkeyManager
from ui.app import BlueLineApp


def main() -> None:
    # ── Load settings & setup logging ────────────────────────────────────────
    settings = load_settings()
    setup_logging(settings)
    logger = logging.getLogger("main")
    logger.info("=" * 60)
    logger.info("BlueLineDispatchPro v1.0 starting...")
    logger.info(f"AppData: {APP_DATA_DIR}")
    logger.info(f"Audio:   {AUDIO_DIR}")

    audio_map = load_audio_map()

    # ── Core services ────────────────────────────────────────────────────────
    cad = CADEngine(settings)
    audio = AudioPlayer(settings)
    audio.start()

    # ── Keyword Listener ─────────────────────────────────────────────────────
    def on_keyword(category: str, phrase: str, text: str) -> None:
        """Called when a keyword is detected. Play audio and log."""
        cad.log(f"[KEYWORD] '{phrase}' detected → category '{category}'  (heard: \"{text}\")", "system")
        played = audio.play_category(AUDIO_DIR, category)
        if not played:
            audio.play_category(AUDIO_DIR, audio_map.get("fallback_category", "acknowledgment"))

    def on_transcript(text: str) -> None:
        if app_ref[0]:
            app_ref[0].update_transcript(text)

    listener = KeywordListener(settings, audio_map, on_keyword=on_keyword, on_transcript=on_transcript)

    # ── Scanner Mode ─────────────────────────────────────────────────────────
    scanner = ScannerMode(
        audio_player=audio,
        audio_dir=AUDIO_DIR,
        settings=settings,
        get_active_call_count=lambda: len(cad.get_active_calls()),
    )
    scanner.start()

    # ── API Server (receives data from FiveM companion) ───────────────────────
    def on_plate(data):
        cad.set_plate_data(data)
        # Auto-trigger plate response audio
        if audio_map.get("categories", {}).get("plate"):
            audio.play_category(AUDIO_DIR, "plate")

    def on_ped(data):
        cad.set_ped_data(data)

    def on_call(data):
        if data.get("_update"):
            cad.update_call(data.get("call_id", ""), data)
        else:
            cad.add_call(data)
            audio.play_category(AUDIO_DIR, "callout")

    def on_unit(data):
        cad.upsert_unit(data)

    def on_bolo(data):
        cad.add_bolo(data)

    def on_panic(data):
        uid = data.get("unit_id", "UNKNOWN")
        cad.trigger_panic(uid)
        audio.play_category(AUDIO_DIR, "panic")

    def on_ping(data):
        cad.set_companion_connected(True)
        cad.upsert_unit({
            "unit_id": data.get("unit_id", "COMPANION"),
            "name": data.get("name", "In-Game Unit"),
            "department": data.get("department", "LSPD"),
            "status": "available",
        })

    api_server = APIServer(
        settings=settings,
        on_plate=on_plate,
        on_ped=on_ped,
        on_call=on_call,
        on_unit=on_unit,
        on_bolo=on_bolo,
        on_panic=on_panic,
        on_ping=on_ping,
    )
    api_server.start()

    # ── File Watcher (fallback for direct file writes) ────────────────────────
    file_watcher = FileWatcher(APP_DATA_DIR, settings)
    file_watcher.register("plate_data.json",   lambda d: cad.set_plate_data(d))
    file_watcher.register("ped_data.json",     lambda d: cad.set_ped_data(d))
    file_watcher.register("active_calls.json", lambda d: [cad.add_call(c) for c in d.get("calls", [])])
    file_watcher.register("unit_status.json",  lambda d: [cad.upsert_unit(u) for u in d.get("units", [])])
    file_watcher.register("bolos.json",        lambda d: [cad.add_bolo(b) for b in d.get("bolos", [])])
    file_watcher.start()

    # ── Hotkey Manager ────────────────────────────────────────────────────────
    app_ref = [None]

    def toggle_listening():
        if app_ref[0]:
            app_ref[0]._toggle_listening()

    def do_panic():
        if app_ref[0]:
            app_ref[0]._trigger_panic()

    def toggle_scanner():
        if app_ref[0]:
            app_ref[0]._toggle_scanner()

    def toggle_mute():
        muted = audio.toggle_mute()
        if app_ref[0]:
            app_ref[0].update_audio_mute(muted)

    hotkeys = HotkeyManager(
        settings=settings,
        on_toggle_listening=toggle_listening,
        on_panic=do_panic,
        on_toggle_scanner=toggle_scanner,
        on_mute=toggle_mute,
    )
    hotkeys.start()

    # ── Launch UI ─────────────────────────────────────────────────────────────
    cad.log("[SYSTEM] BlueLineDispatchPro v1.0 started", "system")
    cad.log(f"[SYSTEM] API server: http://{settings.get('api_server',{}).get('host','127.0.0.1')}:{settings.get('api_server',{}).get('port',7623)}", "system")
    cad.log(f"[SYSTEM] Watching: {APP_DATA_DIR}", "system")

    app = BlueLineApp(
        cad_engine=cad,
        keyword_listener=listener,
        audio_player=audio,
        scanner_mode=scanner,
        hotkey_manager=hotkeys,
        settings=settings,
        audio_dir=AUDIO_DIR,
    )
    app_ref[0] = app

    try:
        app.run()
    finally:
        logger.info("Shutting down...")
        listener.stop()
        scanner.stop()
        hotkeys.stop()
        audio.stop()
        file_watcher.stop()
        logger.info("BlueLineDispatchPro shut down cleanly.")


if __name__ == "__main__":
    main()
