"""LSPDFR AI Dispatch — All-in-one launcher.

Starts the FastAPI backend server and the dispatch radio with wake word
detection using Vosk (offline speech recognition). Say "dispatch" to
activate, speak your command, silence ends the session.
"""

import asyncio
import base64
import configparser
import json as json_mod
import logging
import os
import queue
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("launcher")

CONFIG_FILE = "config.ini"
VERSION = "0.2.0"

# Audio constants — OpenAI Realtime uses 24kHz PCM16
MIC_RATE = 24000
MIC_CHANNELS = 1
MIC_CHUNK = 4800  # 200ms chunks at 24kHz
PLAYBACK_RATE = 24000


def load_config():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
    else:
        config["General"] = {
            "OpenAIApiKey": "",
            "ApiKey": "dispatch-secret",
            "OfficerCallsign": "1-Adam-12",
            "Port": "8000",
        }
        config["Audio"] = {
            "SilenceTimeout": "4.0",
            "WakeWord": "dispatch",
        }
        with open(CONFIG_FILE, "w") as f:
            config.write(f)
        logger.info("Created default %s", CONFIG_FILE)
    return config


def set_env_from_config(config):
    general = config["General"] if "General" in config else {}
    os.environ.setdefault("DISPATCH_DB_BACKEND", "sqlite")
    os.environ.setdefault("DISPATCH_SQLITE_PATH",
                          os.path.join(os.path.dirname(os.path.abspath(__file__)), "dispatch.db"))
    os.environ.setdefault("DISPATCH_API_KEY", general.get("ApiKey", "dispatch-secret"))
    os.environ.setdefault("DISPATCH_OPENAI_API_KEY", general.get("OpenAIApiKey", ""))
    os.environ.setdefault("DISPATCH_DEFAULT_CALLSIGN", general.get("OfficerCallsign", "1-Adam-12"))


def start_backend_server(port: int):
    import uvicorn
    from backend.main import app

    def _run():
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

    t = threading.Thread(target=_run, daemon=True, name="backend-server")
    t.start()
    logger.info("Backend server starting on http://127.0.0.1:%d", port)
    time.sleep(2)
    return t


def download_vosk_model():
    """Download the small Vosk model if not present."""
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vosk-model-small-en-us-0.15")
    if os.path.exists(model_path):
        return model_path

    logger.info("Downloading Vosk speech model (first run only, ~40MB)...")
    import urllib.request
    import zipfile
    url = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    zip_path = model_path + ".zip"
    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(os.path.dirname(model_path))
    os.remove(zip_path)
    logger.info("Vosk model downloaded to %s", model_path)
    return model_path


def run_dispatch_radio(port: int, api_key: str, wake_word: str, silence_timeout: float):
    """Main dispatch radio loop with Vosk wake word detection."""
    import pyaudio
    from vosk import Model, KaldiRecognizer
    from dispatch_radio.audio_playback import AudioPlayback

    # Download/load Vosk model
    model_path = download_vosk_model()
    model = Model(model_path)
    recognizer = KaldiRecognizer(model, MIC_RATE)
    recognizer.SetWords(True)

    # Audio playback
    playback = AudioPlayback(apply_squelch=True, rate=PLAYBACK_RATE)
    is_playing = threading.Event()

    # WebSocket connections
    import websockets.sync.client as ws_sync

    ws_send = None  # For sending audio to backend
    ws_recv = None  # For receiving audio from backend

    def connect_send():
        nonlocal ws_send
        url = f"ws://127.0.0.1:{port}/ws/radio?api_key={api_key}"
        ws_send = ws_sync.connect(url)
        logger.info("Radio sender connected")

    def connect_recv():
        nonlocal ws_recv
        url = f"ws://127.0.0.1:{port}/ws/radio?api_key={api_key}"
        ws_recv = ws_sync.connect(url)
        logger.info("Radio receiver connected")

    # Receiver thread — plays audio responses
    def receiver_loop():
        nonlocal ws_recv
        while True:
            try:
                if ws_recv is None:
                    connect_recv()
                msg_raw = ws_recv.recv(timeout=0.1)
                msg = json_mod.loads(msg_raw)
                if msg.get("type") == "audio_response":
                    audio_b64 = msg.get("data", "")
                    if audio_b64:
                        is_playing.set()
                        pcm = base64.b64decode(audio_b64)
                        playback.play(pcm)
                elif msg.get("type") == "call_announcement":
                    call = msg.get("call", {})
                    logger.info("📻 DISPATCH: %s at %s (Priority %s)",
                               call.get("type", "?"),
                               call.get("location", {}).get("street", "?"),
                               call.get("priority", "?"))
                elif msg.get("type") == "status_ack":
                    logger.info("✓ %s: %s", msg.get("callsign", ""), msg.get("status", ""))
            except TimeoutError:
                # Check if playback finished
                if is_playing.is_set() and not playback._started_response:
                    is_playing.clear()
                continue
            except Exception as e:
                logger.warning("Receiver error: %s", e)
                ws_recv = None
                time.sleep(2)

    recv_thread = threading.Thread(target=receiver_loop, daemon=True, name="receiver")
    recv_thread.start()

    # Open microphone
    pa = pyaudio.PyAudio()
    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=MIC_CHANNELS,
            rate=MIC_RATE,
            input=True,
            frames_per_buffer=MIC_CHUNK,
        )
    except Exception as e:
        logger.error("Failed to open microphone: %s", e)
        return

    logger.info("🎙️  Microphone open. Say '%s' to activate.", wake_word)

    # Connect sender
    try:
        connect_send()
    except Exception as e:
        logger.error("Failed to connect sender: %s", e)
        return

    # State machine
    STATE_PASSIVE = "passive"
    STATE_ACTIVE = "active"
    state = STATE_PASSIVE
    last_voice_time = 0
    wake_word_lower = wake_word.lower()

    while True:
        try:
            data = stream.read(MIC_CHUNK, exception_on_overflow=False)
        except Exception:
            time.sleep(0.1)
            continue

        # Don't process while dispatcher is talking
        if is_playing.is_set():
            continue

        if state == STATE_PASSIVE:
            # Feed audio to Vosk for wake word detection
            if recognizer.AcceptWaveform(data):
                result = json_mod.loads(recognizer.Result())
                text = result.get("text", "").lower()
                if wake_word_lower in text:
                    state = STATE_ACTIVE
                    last_voice_time = time.monotonic()
                    logger.info("🎙️  ACTIVE — '%s' detected! Listening for command...", wake_word)
                    # Send the wake word audio too in case it's part of the command
                    try:
                        b64 = base64.b64encode(data).decode("ascii")
                        ws_send.send('{"type":"audio_chunk","data":"' + b64 + '"}')
                    except:
                        pass
            else:
                # Check partial results too for faster response
                partial = json_mod.loads(recognizer.PartialResult())
                partial_text = partial.get("partial", "").lower()
                if wake_word_lower in partial_text:
                    state = STATE_ACTIVE
                    last_voice_time = time.monotonic()
                    logger.info("🎙️  ACTIVE — '%s' detected! Listening...", wake_word)
                    recognizer.Reset()

        elif state == STATE_ACTIVE:
            # Stream audio to backend → OpenAI
            try:
                b64 = base64.b64encode(data).decode("ascii")
                ws_send.send('{"type":"audio_chunk","data":"' + b64 + '"}')
            except Exception as e:
                logger.warning("Send error: %s", e)
                try:
                    connect_send()
                except:
                    pass

            # Check for silence to end session
            # Simple energy check
            n_samples = len(data) // 2
            if n_samples > 0:
                samples = struct.unpack(f"<{n_samples}h", data[:n_samples * 2])
                rms = (sum(s * s for s in samples) / n_samples) ** 0.5
                if rms > 300:  # Lower threshold to keep session alive
                    last_voice_time = time.monotonic()

            if time.monotonic() - last_voice_time > silence_timeout:
                state = STATE_PASSIVE
                logger.info("🔇 PASSIVE — Silence timeout. Waiting for '%s'...", wake_word)
                recognizer.Reset()
                # Send a commit signal so OpenAI processes what it has
                try:
                    ws_send.send('{"type":"audio_chunk","data":""}')
                except:
                    pass


def main():
    config = load_config()
    set_env_from_config(config)

    general = config["General"] if "General" in config else {}
    audio_cfg = config["Audio"] if "Audio" in config else {}
    port = int(general.get("Port", "8000"))
    callsign = general.get("OfficerCallsign", "1-Adam-12")
    openai_key = general.get("OpenAIApiKey", "")
    api_key = general.get("ApiKey", "dispatch-secret")
    wake_word = audio_cfg.get("WakeWord", "dispatch")
    silence_timeout = float(audio_cfg.get("SilenceTimeout", "4.0"))

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
 ║  Wake Word: "{wake_word}"                          ║
 ║                                              ║
 ║  Say "{wake_word}" to talk to your dispatcher.   ║
 ║  Open the CAD URL in your browser.           ║
 ║  Press Ctrl+C to quit.                       ║
 ╚══════════════════════════════════════════════╝
""")

    if not openai_key:
        print("  WARNING: No OpenAI API key set in config.ini!\n")

    start_backend_server(port)

    try:
        run_dispatch_radio(port, api_key, wake_word, silence_timeout)
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
