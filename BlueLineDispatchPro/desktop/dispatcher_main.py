"""
BlueLineDispatchPro — AI Dispatcher Mode

Say your callsign (e.g. "Sam-44") → dispatcher acknowledges →
you speak your transmission → Whisper STT → GPT-4o-mini → ElevenLabs voice response.

Run:  python dispatcher_main.py
"""
import json
import logging
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dispatcher")

CONFIG_PATH = os.path.join(BASE_DIR, "config", "ai_config.json")


def load_ai_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(
            f"ai_config.json not found at:\n{CONFIG_PATH}\n"
            "Copy config/ai_config.json and fill in your API keys."
        )
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    missing = [k for k in ("openai_api_key", "elevenlabs_api_key")
               if not cfg.get(k) or "PASTE" in cfg.get(k, "")]
    if missing:
        raise ValueError(
            f"Missing API keys in ai_config.json: {missing}\n"
            f"Open {CONFIG_PATH} and fill in your keys."
        )
    return cfg


def main() -> None:
    try:
        config = load_ai_config()
    except (FileNotFoundError, ValueError) as e:
        logger.error(str(e))
        input("Press Enter to exit...")
        sys.exit(1)

    logger.info(f"Callsign: {config['callsign']}  |  Agency: {config.get('agency','LSPD')}")

    from core.ai_dispatcher import AIDispatcher
    from dispatcher_ui import DispatcherWindow

    dispatcher = AIDispatcher(config)
    ui = DispatcherWindow(config)

    # ── Wire dispatcher → UI ──────────────────────────────────────────────────
    def on_state(state_key: str, label: str, color: str) -> None:
        ui.set_ai_state(label, color)

    def on_user_speech(text: str) -> None:
        ui.append_transcript("officer", text)

    def on_dispatcher_speech(text: str) -> None:
        ui.append_transcript("dispatch", text)

    def on_error(msg: str) -> None:
        logger.error(f"Dispatcher error: {msg}")
        ui.show_error(msg)

    dispatcher.on_state_change      = on_state
    dispatcher.on_user_speech       = on_user_speech
    dispatcher.on_dispatcher_speech = on_dispatcher_speech
    dispatcher.on_error             = on_error

    # ── Wire UI → dispatcher ──────────────────────────────────────────────────
    ui.on_manual_trigger = dispatcher.manual_trigger
    ui.on_clear_history  = dispatcher.clear_history
    ui.on_quit           = dispatcher.stop

    # ── Start ─────────────────────────────────────────────────────────────────
    dispatcher.start()
    logger.info(f"Listening for callsign: '{config['callsign']}'")
    ui.run()


if __name__ == "__main__":
    main()
