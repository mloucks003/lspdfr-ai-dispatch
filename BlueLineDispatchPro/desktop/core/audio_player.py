"""
BlueLineDispatchPro — Audio Player with Radio Effects
Loads WAV files, applies professional radio processing, plays on selected device.
"""
import io
import logging
import os
import queue
import random
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Optional imports — degrade gracefully if missing
try:
    from pydub import AudioSegment
    from scipy import signal
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logger.warning("pydub/scipy not available — radio effects disabled")

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False
    logger.warning("sounddevice not available — audio playback disabled")


def _apply_radio_fx(audio: "AudioSegment", intensity: float, squelch: bool) -> "AudioSegment":
    """Apply realistic police radio effects to an AudioSegment."""
    audio = audio.set_channels(1)
    original_rate = audio.frame_rate
    samples = np.array(audio.get_array_of_samples(), dtype=np.float64)
    max_val = np.max(np.abs(samples))
    if max_val == 0:
        return audio
    samples = samples / max_val

    # Bandpass filter: 300–3400 Hz (radio frequency range)
    nyquist = original_rate / 2.0
    low = max(300.0 / nyquist, 0.01)
    high = min(3400.0 / nyquist, 0.99)
    b, a = signal.butter(4, [low, high], btype="band")
    samples = signal.lfilter(b, a, samples)

    # Subtle harmonic distortion (warm radio crunch)
    if intensity > 0.3:
        samples = np.tanh(samples * (1.0 + intensity * 1.5))

    # Static/noise overlay
    if intensity > 0:
        noise = np.random.normal(0, 0.012 * intensity, len(samples))
        samples = samples + noise

    # Soft clip
    samples = np.clip(samples, -0.92, 0.92)

    # Normalize
    peak = np.max(np.abs(samples))
    if peak > 0:
        samples = samples / peak * 0.88

    processed = (samples * 32767).astype(np.int16)

    result = AudioSegment(
        processed.tobytes(),
        frame_rate=original_rate,
        sample_width=2,
        channels=1,
    )

    # Squelch click: brief noise burst at start
    if squelch and intensity > 0.2:
        click_dur = 45  # ms
        click_samples = int(original_rate * click_dur / 1000)
        t = np.linspace(0, click_dur / 1000, click_samples)
        noise = np.random.normal(0, 1, click_samples)
        envelope = np.exp(-t * 35) * 0.35 * intensity
        click = (noise * envelope * 32767).astype(np.int16)
        click_seg = AudioSegment(
            click.tobytes(), frame_rate=original_rate, sample_width=2, channels=1
        )
        result = click_seg + result

    return result


class AudioPlayer:
    """Queue-based audio player with radio effect processing."""

    def __init__(self, settings: Dict):
        self.settings = settings
        self._queue: queue.Queue = queue.Queue()
        self._play_obj: Optional[object] = None
        self._lock = threading.Lock()
        self._running = False
        self._muted = False
        self._worker_thread: Optional[threading.Thread] = None
        self._last_play_time: float = 0.0
        self._cache: Dict[str, bytes] = {}  # processed audio cache

    @property
    def audio_settings(self) -> Dict:
        return self.settings.get("audio", {})

    @property
    def intensity(self) -> float:
        return float(self.audio_settings.get("radio_effect_intensity", 0.75))

    @property
    def volume(self) -> float:
        return float(self.audio_settings.get("volume", 0.85))

    @property
    def min_gap_ms(self) -> int:
        return int(self.audio_settings.get("min_gap_between_audio_ms", 1500))

    @property
    def muted(self) -> bool:
        return self._muted

    def start(self) -> None:
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker, daemon=True, name="AudioWorker")
        self._worker_thread.start()
        logger.info("AudioPlayer started")

    def stop(self) -> None:
        self._running = False
        self._queue.put(None)  # sentinel
        if self._worker_thread:
            self._worker_thread.join(timeout=3)

    def toggle_mute(self) -> bool:
        self._muted = not self._muted
        logger.info(f"Audio {'muted' if self._muted else 'unmuted'}")
        return self._muted

    def play_file(self, filepath: str, priority: int = 5) -> None:
        """Queue a file for playback."""
        if self._muted:
            return
        self._queue.put((priority, filepath))

    def play_category(self, audio_dir: Path, category: str) -> bool:
        """Pick a random file from the category folder and queue it."""
        folder = audio_dir / category
        if not folder.exists():
            logger.debug(f"Audio folder not found: {folder}")
            return False
        wav_files = list(folder.glob("*.wav")) + list(folder.glob("*.mp3"))
        if not wav_files:
            logger.debug(f"No audio files in: {folder}")
            return False
        chosen = random.choice(wav_files)
        self.play_file(str(chosen))
        return True

    def _worker(self) -> None:
        """Background thread: dequeue and play audio files."""
        while self._running:
            try:
                item = self._queue.get(timeout=1.0)
                if item is None:
                    break
                _, filepath = item

                # Enforce minimum gap between plays
                elapsed = (time.time() - self._last_play_time) * 1000
                if elapsed < self.min_gap_ms:
                    time.sleep((self.min_gap_ms - elapsed) / 1000.0)

                self._play(filepath)
                self._last_play_time = time.time()
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"AudioPlayer worker error: {e}")

    def _play(self, filepath: str) -> None:
        """Load, process, and play an audio file."""
        if not SOUNDDEVICE_AVAILABLE:
            logger.debug(f"Would play: {filepath}")
            return

        try:
            # Check cache
            if filepath in self._cache:
                raw = self._cache[filepath]
            else:
                raw = self._process_file(filepath)
                if raw:
                    self._cache[filepath] = raw

            if not raw:
                return

            # Play via sounddevice (numpy array, 44100 Hz, mono int16)
            samples = np.frombuffer(raw, dtype=np.int16)
            with self._lock:
                self._play_obj = True  # flag: playing
            sd.play(samples, samplerate=44100, blocking=True)
            with self._lock:
                self._play_obj = None

        except Exception as e:
            logger.error(f"Playback error ({filepath}): {e}")

    def _process_file(self, filepath: str) -> Optional[bytes]:
        """Apply radio FX and return raw PCM bytes at 44100 Hz mono int16."""
        if not PYDUB_AVAILABLE:
            # Fallback: return raw bytes if pydub unavailable
            try:
                with open(filepath, "rb") as f:
                    return f.read()[44:]  # skip WAV header approx
            except Exception:
                return None

        try:
            audio = AudioSegment.from_file(filepath)
            if self.intensity > 0:
                squelch = bool(self.audio_settings.get("squelch_click", True))
                audio = _apply_radio_fx(audio, self.intensity, squelch)
            # Apply volume
            if self.volume != 1.0:
                db_change = 20 * np.log10(max(self.volume, 0.01))
                audio = audio + db_change
            # Resample to 44100 for simpleaudio compatibility
            audio = audio.set_frame_rate(44100).set_channels(1).set_sample_width(2)
            return audio.raw_data
        except Exception as e:
            logger.error(f"Audio processing error ({filepath}): {e}")
            return None

    def get_available_devices(self) -> List[Dict]:
        """Return list of available audio output devices."""
        devices = []
        try:
            if SOUNDDEVICE_AVAILABLE:
                for i, d in enumerate(sd.query_devices()):
                    if d["max_output_channels"] > 0:
                        devices.append({"index": i, "name": d["name"]})
        except Exception as e:
            logger.warning(f"Could not enumerate audio devices: {e}")
        return devices

    def get_available_input_devices(self) -> List[Dict]:
        """Return list of available audio input devices."""
        devices = []
        try:
            if SOUNDDEVICE_AVAILABLE:
                for i, d in enumerate(sd.query_devices()):
                    if d["max_input_channels"] > 0:
                        devices.append({"index": i, "name": d["name"]})
        except Exception as e:
            logger.warning(f"Could not enumerate input devices: {e}")
        return devices
