"""
BlueLineDispatchPro — DISPATCHER ONLY MODE
Runs JUST the keyword listener + radio audio playback.
No CAD, no API server, no companion needed.

Run this instead of main.py when you only want the dispatcher.
"""
import os
import sys
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import load_settings, setup_logging, load_audio_map, AUDIO_DIR
from core.audio_player import AudioPlayer
from core.keyword_listener import KeywordListener
from core.scanner_mode import ScannerMode
from core.hotkey_manager import HotkeyManager
from dispatcher_ui import DispatcherWindow


def main() -> None:
    settings = load_settings()
    setup_logging(settings)
    logger = logging.getLogger("dispatcher")
    logger.info("BlueLineDispatchPro — Dispatcher Mode starting...")

    audio_map = load_audio_map()

    # ── Audio Player ──────────────────────────────────────────────────────────
    audio = AudioPlayer(settings)
    audio.start()

    # ── Dispatcher UI (created before callbacks so we can reference it) ───────
    ui = DispatcherWindow(settings)

    # ── Keyword Listener ──────────────────────────────────────────────────────
    def on_keyword(category: str, phrase: str, text: str) -> None:
        logger.info(f"[KEYWORD] '{phrase}' → {category}")
        played = audio.play_category(AUDIO_DIR, category)
        if not played:
            fallback = audio_map.get("fallback_category", "acknowledgment")
            audio.play_category(AUDIO_DIR, fallback)
        # Update UI
        ui.log_trigger(phrase, category)
        if category == "panic":
            ui.flash_panic()

    def on_transcript(text: str) -> None:
        ui.set_transcript(text)

    listener = KeywordListener(
        settings, audio_map,
        on_keyword=on_keyword,
        on_transcript=on_transcript,
    )

    # ── Scanner Mode ──────────────────────────────────────────────────────────
    scanner = ScannerMode(audio_player=audio, audio_dir=AUDIO_DIR, settings=settings)
    scanner.start()

    # ── Hotkeys ───────────────────────────────────────────────────────────────
    def toggle_listen():
        if listener.is_active:
            listener.set_active(False)
            ui.set_listener_state(False)
        else:
            if not listener._running:
                ok = listener.start()
                if not ok:
                    ui.show_error("Vosk model not found.\nCheck Settings → Model Path and DOWNLOAD_MODEL.txt")
                    return
            listener.set_active(True)
            ui.set_listener_state(True)

    def do_panic():
        audio.play_category(AUDIO_DIR, "panic")
        ui.flash_panic()
        logger.warning("PANIC triggered via hotkey")

    def toggle_scanner():
        new = not scanner.is_active
        scanner.set_active(new)
        ui.set_scanner_state(new)

    def toggle_mute():
        muted = audio.toggle_mute()
        ui.set_muted(muted)

    hotkeys = HotkeyManager(
        settings=settings,
        on_toggle_listening=toggle_listen,
        on_panic=do_panic,
        on_toggle_scanner=toggle_scanner,
        on_mute=toggle_mute,
    )
    hotkeys.start()

    # ── Wire UI callbacks ─────────────────────────────────────────────────────
    ui.on_toggle_listen  = toggle_listen
    ui.on_toggle_scanner = toggle_scanner
    ui.on_panic          = do_panic
    ui.on_mute           = toggle_mute
    ui.on_quit = lambda: (
        listener.stop(), scanner.stop(),
        hotkeys.stop(), audio.stop()
    )

    # ── Run ───────────────────────────────────────────────────────────────────
    logger.info(f"Audio folder: {AUDIO_DIR}")
    logger.info("Ready. Press F8 to start listening.")
    ui.run()


if __name__ == "__main__":
    main()
