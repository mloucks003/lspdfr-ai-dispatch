"""
BlueLineDispatchPro — Keyword Listener
Offline speech recognition via Vosk. Detects keywords and triggers dispatcher audio.
"""
import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    logger.warning("PyAudio not available — keyword listener disabled")

try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    logger.warning("Vosk not available — keyword listener disabled")


class KeywordListener:
    """
    Listens to a microphone or virtual audio cable using Vosk offline STT.
    Detects configured keywords and fires callbacks with the matched category.
    """

    SAMPLE_RATE = 16000
    CHUNK_SIZE = 4096

    def __init__(self, settings: Dict, audio_map: Dict, on_keyword: Optional[Callable] = None,
                 on_transcript: Optional[Callable] = None):
        self.settings = settings
        self.audio_map = audio_map
        self.on_keyword = on_keyword        # callback(category: str, phrase: str, text: str)
        self.on_transcript = on_transcript  # callback(text: str)

        self._running = False
        self._active = False
        self._thread: Optional[threading.Thread] = None
        self._model: Optional[Any] = None
        self._recognizer: Optional[Any] = None
        self._cooldowns: Dict[str, float] = {}  # category → last trigger time

        # Build keyword index: lowercase phrase → category name
        self._keyword_index: List[tuple] = []
        self._build_keyword_index()

    @property
    def ls_settings(self) -> Dict:
        return self.settings.get("keyword_listener", {})

    @property
    def model_path(self) -> str:
        from config import BASE_DIR
        mp = self.ls_settings.get("model_path", "models/vosk-model-en-us")
        p = Path(mp)
        if not p.is_absolute():
            p = BASE_DIR / p
        return str(p)

    @property
    def confidence_threshold(self) -> float:
        return float(self.ls_settings.get("confidence_threshold", 0.65))

    @property
    def global_cooldown(self) -> float:
        return float(self.ls_settings.get("cooldown_seconds", 4.0))

    @property
    def input_device_index(self) -> Optional[int]:
        idx = self.settings.get("audio", {}).get("input_device_index")
        return int(idx) if idx is not None else None

    def _build_keyword_index(self) -> None:
        """Build sorted keyword index from audio_map categories (longest phrase first)."""
        categories = self.audio_map.get("categories", {})
        entries = []
        for cat_name, cat_data in categories.items():
            cooldown = cat_data.get("cooldown_override_seconds", None)
            priority = int(cat_data.get("priority", 5))
            for trigger in cat_data.get("triggers", []):
                entries.append((trigger.lower(), cat_name, priority, cooldown))
        # Also include global keywords from settings
        global_kw = self.ls_settings.get("keywords", [])
        fallback = self.audio_map.get("fallback_category", "acknowledgment")
        for kw in global_kw:
            entries.append((kw.lower(), fallback, 6, None))
        # Sort by phrase length descending (longest match first)
        entries.sort(key=lambda x: (-len(x[0]), x[2]))
        self._keyword_index = entries
        logger.info(f"KeywordListener: {len(self._keyword_index)} keyword entries loaded")

    def _load_model(self) -> bool:
        """Load the Vosk model. Returns True on success."""
        if not VOSK_AVAILABLE:
            logger.error("Vosk library not installed. Run: pip install vosk")
            return False
        mp = self.model_path
        if not Path(mp).exists():
            logger.error(
                f"Vosk model not found at: {mp}\n"
                "Download from https://alphacephei.com/vosk/models and unzip to that path."
            )
            return False
        try:
            import vosk
            vosk.SetLogLevel(-1)
            self._model = Model(mp)
            self._recognizer = KaldiRecognizer(self._model, self.SAMPLE_RATE)
            self._recognizer.SetWords(True)
            logger.info(f"Vosk model loaded from: {mp}")
            return True
        except Exception as e:
            logger.error(f"Failed to load Vosk model: {e}")
            return False

    def start(self) -> bool:
        """Start the listener thread. Returns True if started successfully."""
        if self._running:
            return True
        if not self._load_model():
            return False
        self._running = True
        self._active = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="KeywordListener")
        self._thread.start()
        logger.info("KeywordListener started")
        return True

    def stop(self) -> None:
        self._running = False
        self._active = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("KeywordListener stopped")

    def set_active(self, active: bool) -> None:
        """Toggle listening without stopping the thread."""
        self._active = active
        logger.info(f"Keyword listening {'enabled' if active else 'paused'}")

    @property
    def is_active(self) -> bool:
        return self._running and self._active

    def _listen_loop(self) -> None:
        """Main loop: open microphone stream and process audio."""
        if not PYAUDIO_AVAILABLE:
            logger.error("PyAudio not available. Cannot start listener.")
            return

        p = pyaudio.PyAudio()
        stream = None
        try:
            kwargs = {
                "format": pyaudio.paInt16,
                "channels": 1,
                "rate": self.SAMPLE_RATE,
                "input": True,
                "frames_per_buffer": self.CHUNK_SIZE,
            }
            if self.input_device_index is not None:
                kwargs["input_device_index"] = self.input_device_index

            stream = p.open(**kwargs)
            logger.info("Audio stream opened")

            while self._running:
                if not self._active:
                    time.sleep(0.1)
                    continue
                try:
                    data = stream.read(self.CHUNK_SIZE, exception_on_overflow=False)
                    if self._recognizer.AcceptWaveform(data):
                        result = json.loads(self._recognizer.Result())
                        text = result.get("text", "").strip()
                        if text:
                            self._process_text(text)
                    else:
                        partial = json.loads(self._recognizer.PartialResult())
                        partial_text = partial.get("partial", "").strip()
                        if partial_text and self.on_transcript:
                            self.on_transcript(partial_text)
                except OSError as e:
                    logger.error(f"Audio stream error: {e}")
                    time.sleep(0.5)
        except Exception as e:
            logger.error(f"Listener loop error: {e}")
        finally:
            if stream:
                stream.stop_stream()
                stream.close()
            p.terminate()
            logger.info("Audio stream closed")

    def _process_text(self, text: str) -> None:
        """Check recognized text for keywords and fire callbacks."""
        if self.on_transcript:
            self.on_transcript(text)
        logger.debug(f"Recognized: '{text}'")

        text_lower = text.lower()
        now = time.time()

        for phrase, category, priority, cooldown_override in self._keyword_index:
            match_mode = self.audio_map.get("keyword_match_mode", "contains")
            if match_mode == "contains":
                matched = phrase in text_lower
            else:
                matched = text_lower.startswith(phrase) or text_lower.endswith(phrase)

            if matched:
                cd = cooldown_override if cooldown_override is not None else self.global_cooldown
                last = self._cooldowns.get(category, 0.0)
                if (now - last) >= cd:
                    self._cooldowns[category] = now
                    logger.info(f"Keyword match: '{phrase}' → category '{category}'")
                    if self.on_keyword:
                        self.on_keyword(category, phrase, text)
                    break  # Fire only highest-priority match per utterance

    def reload_keywords(self) -> None:
        """Reload keyword index after settings change."""
        self._build_keyword_index()
        logger.info("Keyword index reloaded")
