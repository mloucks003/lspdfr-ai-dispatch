"""LSPDFR AI Dispatch — All-in-one launcher.

Starts the FastAPI backend server and the dispatch radio in one process.
This is what gets packaged as DispatchRadio.exe for end users.
"""

import argparse
import asyncio
import configparser
import logging
import os
import signal
import sys
import threading
import time

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("launcher")

CONFIG_FILE = "config.ini"
VERSION = "0.1.0"


def load_config():
    """Load settings from config.ini, creating defaults if missing."""
    config = configparser.ConfigParser()

    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
    else:
        # Create default config
        config["General"] = {
            "OpenAIApiKey": "",
            "ApiKey": "dispatch-secret",
            "OfficerCallsign": "1-Adam-12",
            "Port": "8000",
        }
        config["Audio"] = {
            "WakeThreshold": "2000",
            "SilenceTimeout": "2.0",
        }
        with open(CONFIG_FILE, "w") as f:
            config.write(f)
        logger.info("Created default %s — edit it to add your OpenAI API key.", CONFIG_FILE)

    return config


def set_env_from_config(config):
    """Push config.ini values into environment variables for the backend."""
    general = config["General"] if "General" in config else {}
    os.environ.setdefault("DISPATCH_DB_BACKEND", "sqlite")
    os.environ.setdefault("DISPATCH_SQLITE_PATH",
                          os.path.join(os.path.dirname(os.path.abspath(__file__)), "dispatch.db"))
    os.environ.setdefault("DISPATCH_API_KEY", general.get("ApiKey", "dispatch-secret"))
    os.environ.setdefault("DISPATCH_OPENAI_API_KEY", general.get("OpenAIApiKey", ""))
    os.environ.setdefault("DISPATCH_DEFAULT_CALLSIGN", general.get("OfficerCallsign", "1-Adam-12"))
    os.environ.setdefault("DISPATCH_PORT", general.get("Port", "8000"))


def start_backend_server(port: int):
    """Run the FastAPI backend in a background thread."""
    import uvicorn
    from backend.main import app

    def _run():
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

    t = threading.Thread(target=_run, daemon=True, name="backend-server")
    t.start()
    logger.info("Backend server starting on http://127.0.0.1:%d", port)
    # Give it a moment to start
    time.sleep(1.5)
    return t


def start_dispatch_radio(config, port: int):
    """Run the dispatch radio (audio capture + WebSocket client)."""
    from dispatch_radio.audio_capture import AudioCapture, SimpleEnergyWakeWordDetector
    from dispatch_radio.audio_playback import AudioPlayback
    from dispatch_radio.session_manager import SessionManager, SessionState
    from dispatch_radio.websocket_client import RadioWebSocketClient

    general = config["General"] if "General" in config else {}
    audio_cfg = config["Audio"] if "Audio" in config else {}

    api_key = general.get("ApiKey", "dispatch-secret")
    callsign = general.get("OfficerCallsign", "1-Adam-12")
    wake_threshold = float(audio_cfg.get("WakeThreshold", "2000"))
    silence_timeout = float(audio_cfg.get("SilenceTimeout", "2.0"))

    backend_url = f"ws://127.0.0.1:{port}/ws/radio"

    playback = AudioPlayback(apply_squelch=True)

    ws_client = RadioWebSocketClient(
        backend_url=backend_url,
        api_key=api_key,
        on_audio_response=lambda pcm: playback.play(pcm),
        on_call_announcement=lambda call: logger.info(
            "DISPATCH: %s at %s (Priority %s)",
            call.get("type", "?"), call.get("location", {}).get("street", "?"),
            call.get("priority", "?"),
        ),
        on_status_ack=lambda msg: logger.info(
            "Status ACK: %s %s", msg.get("callsign", ""), msg.get("status", ""),
        ),
    )

    session = SessionManager(
        silence_timeout=silence_timeout,
        on_session_start=lambda: ws_client.send_status_update("active"),
        on_session_end=lambda: ws_client.send_status_update("listening"),
    )

    detector = SimpleEnergyWakeWordDetector(threshold=wake_threshold)

    def on_wake_word(chunk):
        session.activate()

    def on_audio_chunk(chunk):
        if session.state == SessionState.ACTIVE:
            ws_client.send_audio_chunk(chunk)
            session.feed_audio(chunk)
        session.check_timeout()

    capture = AudioCapture(
        wake_word_detector=detector,
        on_wake_word=on_wake_word,
        on_audio_chunk=on_audio_chunk,
    )

    ws_client.start()
    capture.start()

    return ws_client, capture


def main():
    config = load_config()
    set_env_from_config(config)

    general = config["General"] if "General" in config else {}
    port = int(general.get("Port", "8000"))
    callsign = general.get("OfficerCallsign", "1-Adam-12")
    openai_key = general.get("OpenAIApiKey", "")

    port_str = str(port)
    openai_status = "Configured" if openai_key else "NOT SET — edit config.ini"
    print(f"""
 ╔══════════════════════════════════════════════╗
 ║      LSPDFR AI Dispatch Radio v{VERSION}        ║
 ║                                              ║
 ║  Callsign:  {callsign:<32s} ║
 ║  Backend:   http://127.0.0.1:{port_str:<15s} ║
 ║  CAD:       http://127.0.0.1:{port_str:<15s} ║
 ║  OpenAI:    {openai_status:<32s} ║
 ║                                              ║
 ║  Say "dispatch" to talk to your dispatcher.  ║
 ║  Open the CAD URL in your browser.           ║
 ║  Press Ctrl+C to quit.                       ║
 ╚══════════════════════════════════════════════╝
""")

    if not openai_key:
        print("  WARNING: No OpenAI API key set in config.ini!")
        print("  Voice dispatch will not work until you add your key.\n")

    # Start backend
    start_backend_server(port)

    # Start radio
    ws_client, capture = start_dispatch_radio(config, port)

    logger.info("All systems online. Listening for wake word...")

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        capture.stop()
        ws_client.stop()
        logger.info("Dispatch Radio stopped.")


if __name__ == "__main__":
    main()
