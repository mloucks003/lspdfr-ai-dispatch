"""LSPDFR AI Dispatch Radio — Desktop companion application entry point.

Run directly: python -m dispatch_radio.main
Or as packaged exe: DispatchRadio.exe
"""

import argparse
import base64
import logging
import sys
import time

from dispatch_radio.audio_capture import AudioCapture, SimpleEnergyWakeWordDetector
from dispatch_radio.audio_playback import AudioPlayback
from dispatch_radio.session_manager import SessionManager, SessionState
from dispatch_radio.websocket_client import RadioWebSocketClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dispatch_radio")


def main():
    parser = argparse.ArgumentParser(description="LSPDFR AI Dispatch Radio")
    parser.add_argument("--backend", default="ws://localhost:8000/ws/radio",
                        help="Backend WebSocket URL")
    parser.add_argument("--api-key", default="changeme",
                        help="API key for backend authentication")
    parser.add_argument("--callsign", default="1-Adam-12",
                        help="Officer callsign")
    parser.add_argument("--silence-timeout", type=float, default=2.0,
                        help="Seconds of silence before ending active session")
    parser.add_argument("--wake-threshold", type=float, default=2000.0,
                        help="RMS energy threshold for wake word detection")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════╗
║     LSPDFR AI Dispatch Radio v0.1.0      ║
║                                          ║
║  Callsign: {args.callsign:<28s} ║
║  Backend:  {args.backend:<28s} ║
║                                          ║
║  Say "dispatch" to activate.             ║
║  Press Ctrl+C to quit.                   ║
╚══════════════════════════════════════════╝
""")

    # --- Audio playback (with squelch effects) ---
    playback = AudioPlayback(apply_squelch=True)

    # --- WebSocket client ---
    ws_client = RadioWebSocketClient(
        backend_url=args.backend,
        api_key=args.api_key,
        on_audio_response=lambda pcm: playback.play(pcm),
        on_call_announcement=lambda call: logger.info(
            "📻 DISPATCH: %s at %s (Priority %s)",
            call.get("type", "Unknown"),
            call.get("location", {}).get("street", "Unknown"),
            call.get("priority", "?"),
        ),
        on_status_ack=lambda msg: logger.info(
            "✓ Status acknowledged: %s %s",
            msg.get("callsign", ""),
            msg.get("status", ""),
        ),
    )

    # --- Session manager ---
    def on_session_start():
        logger.info("🎙️  ACTIVE — Listening for command...")
        ws_client.send_status_update("active")

    def on_session_end():
        logger.info("🔇 PASSIVE — Waiting for wake word...")
        ws_client.send_status_update("listening")

    session = SessionManager(
        silence_timeout=args.silence_timeout,
        on_session_start=on_session_start,
        on_session_end=on_session_end,
    )

    # --- Audio capture with wake word detection ---
    detector = SimpleEnergyWakeWordDetector(threshold=args.wake_threshold)

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

    # --- Start everything ---
    ws_client.start()
    capture.start()
    logger.info("Dispatch Radio started. Listening...")

    try:
        while True:
            time.sleep(0.1)
            # Check session timeout periodically
            if session.state == SessionState.ACTIVE:
                session.check_timeout()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        capture.stop()
        ws_client.stop()
        logger.info("Dispatch Radio stopped.")


if __name__ == "__main__":
    main()
