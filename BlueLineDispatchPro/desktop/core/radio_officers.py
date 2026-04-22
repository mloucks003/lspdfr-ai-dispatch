"""
BlueLineDispatchPro — RadioOfficerManager

Manages a roster of AI officer units that live on the radio channel:
  • Background chatter: officers call dispatch every 35-100 seconds
  • Backup confirms: when dispatch sends a unit, that unit acknowledges
  • Player address: if player names an officer, that officer responds
  • Each officer has its own Fish Audio voice_id for a unique voice

Configure officers in settings.json under "officers" or ai_config.json.
Set voice_id to a Fish Audio reference ID (find them at fish.audio/voices).
Leave voice_id null to use Fish Audio's platform default voice.
"""
import logging
import random
import threading
import time
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── GTA V / Los Santos locations ─────────────────────────────────────────────
_LOCATIONS = [
    "Strawberry Avenue", "Forum Drive", "Elgin Avenue", "Adam Avenue",
    "Grove Street", "Rockford Hills", "Vinewood Boulevard", "Mirror Park",
    "Del Perro Freeway", "Olympic Freeway", "Route 68", "Paleto Bay",
    "Sandy Shores", "Grapeseed", "Davis Avenue", "Alta Street",
    "Power Street", "Innocence Boulevard", "Brouge Avenue", "Crusade Road",
    "Maze Bank Avenue", "Capital Boulevard", "Bay City Avenue", "Sinner Street",
    "Chamberlain Hills", "Burton", "Little Seoul", "Cypress Flats",
]

_VEHICLES = [
    "blue Honda Civic", "black SUV", "red pickup truck", "white sedan",
    "silver Dodge Charger", "dark green minivan", "grey BMW coupe",
    "gold Cadillac", "maroon Lincoln", "beige Toyota Camry",
    "orange Chevy pickup", "two-door brown Ford", "tan Nissan Altima",
]

# ── Default officer roster ────────────────────────────────────────────────────
# voice_id: Fish Audio reference_id string, or null to use platform default.
# Add your own from https://fish.audio/voices/
DEFAULT_OFFICERS = [
    {
        "callsign": "Sam-41",
        "name":     "Officer Reyes",
        "voice_id": None,   # <-- paste a Fish Audio voice ID here for a unique voice
        "gender":   "male",
    },
    {
        "callsign": "Lincoln-9",
        "name":     "Officer Chen",
        "voice_id": None,
        "gender":   "male",
    },
    {
        "callsign": "King-3",
        "name":     "Officer Davis",
        "voice_id": None,
        "gender":   "female",
    },
]

_CHATTER_EVENTS = [
    ("traffic_stop",  35),
    ("clear",         25),
    ("scene_arrival", 20),
    ("patrol_obs",    15),
    ("request_info",   5),
]
_EVENT_LABELS   = [e[0] for e in _CHATTER_EVENTS]
_EVENT_WEIGHTS  = [e[1] for e in _CHATTER_EVENTS]

# Per-officer pitch factor (resample multiplier applied before playback).
# > 1.0 → stretch audio → lower pitch.  < 1.0 → compress → higher pitch.
# This makes officers distinguishable even when voice_id is not configured.
_OFFICER_PITCH = {
    "Sam-41":   1.10,   # deeper male voice
    "Lincoln-9": 0.96,  # slightly higher male
    "King-3":   0.88,   # notably higher — female officer
}

# Distinct squelch-click frequencies per unit (Hz).
# Listeners learn to recognise each officer by their key-up tone.
_OFFICER_SQUELCH_HZ = {
    "Sam-41":    680,
    "Lincoln-9": 820,
    "King-3":    960,
}

_DISPATCH_ACKS = {
    "traffic_stop":  ["Copy {cs}, showing you 10-38.", "10-4 {cs}, 10-38 noted at your location."],
    "clear":         ["10-4 {cs}, return to service.", "Copy {cs}, you're 10-8."],
    "scene_arrival": ["10-4 {cs}, 10-23 noted.", "Copy {cs}, on scene."],
    "patrol_obs":    ["10-4 {cs}. All units copy.", "Copy {cs}, units are advised."],
    "request_info":  ["10-4 {cs}, stand by.", "Copy {cs}, checking that now."],
}


class RadioOfficerManager:
    """
    Manages AI officer voices on the radio channel.

    Callers must provide:
      tts_fn(text, voice_id) -> Optional[bytes]  — returns MP3 bytes
      radio_fx_fn(samples, intensity) -> np.ndarray
      openai_client — OpenAI client instance
    """

    SAMPLE_RATE = 16000

    def __init__(
        self,
        config: dict,
        tts_fn:     Callable[[str, Optional[str]], Optional[bytes]],
        radio_fx_fn: Callable,
        openai_client,
    ):
        self._config    = config
        self._tts       = tts_fn
        self._radio_fx  = radio_fx_fn
        self._openai    = openai_client
        self._running   = False
        self._paused    = False
        self._play_lock = threading.Lock()   # one transmission at a time

        raw = config.get("officers", DEFAULT_OFFICERS)
        self.officers: dict[str, dict] = {}
        for o in raw:
            cs = o["callsign"]
            self.officers[cs] = {
                "callsign": cs,
                "name":     o.get("name", cs),
                "voice_id": o.get("voice_id") or None,
                "gender":   o.get("gender", "male"),
                "status":   "10-8",
                "location": random.choice(_LOCATIONS),
            }

        self.player_callsign = config.get("callsign", "Sam-44")
        self.agency          = config.get("agency", "LSPD")

        self._min_interval = float(config.get("chatter_min_seconds", 40))
        self._max_interval = float(config.get("chatter_max_seconds", 100))

        # Callbacks — wired by ai_dispatcher
        self.on_officer_speech:  Optional[Callable[[str, str], None]] = None
        self.on_dispatch_ack:    Optional[Callable[[str], None]]      = None
        self._dispatch_speak_fn: Optional[Callable[[str], None]]      = None

        # Shared mic-suppression event from AIDispatcher.
        # When set, the VAD in the dispatcher ignores audio queue chunks.
        # We set it before playing any officer audio and clear it after.
        self.mic_suppressed: Optional[threading.Event] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def set_dispatch_speak(self, fn: Callable[[str], None]):
        """Wire in dispatcher's ALLE speak function so dispatch can ack officers."""
        self._dispatch_speak_fn = fn

    def start(self):
        self._running = True
        t = threading.Thread(target=self._chatter_loop, daemon=True, name="radio_chatter")
        t.start()
        logger.info("RadioOfficerManager: background chatter started")

    def stop(self):
        self._running = False

    def pause(self):
        """Call when the player opens a session — freeze background chatter."""
        self._paused = True

    def resume(self):
        """Call when the player session closes."""
        self._paused = False

    def random_callsign(self) -> str:
        return random.choice(list(self.officers.keys()))

    # ── Background chatter loop ───────────────────────────────────────────────

    def _chatter_loop(self):
        time.sleep(random.uniform(12, 25))   # initial quiet period
        while self._running:
            interval = random.uniform(self._min_interval, self._max_interval)
            time.sleep(interval)
            if self._running and not self._paused:
                try:
                    self._fire_random_chatter()
                except Exception as e:
                    logger.error(f"[CHATTER] {e}")

    def _fire_random_chatter(self):
        officer = random.choice(list(self.officers.values()))
        event   = random.choices(_EVENT_LABELS, weights=_EVENT_WEIGHTS, k=1)[0]
        text    = self._generate_officer_line(officer, event)
        if not text:
            return

        logger.info(f"[{officer['callsign']}] (chatter): {text!r}")
        with self._play_lock:
            self._speak_as_officer(officer, text)
        if self.on_officer_speech:
            self.on_officer_speech(officer["callsign"], text)

        time.sleep(random.uniform(0.7, 1.6))

        if self._paused:
            return
        ack_tmpl = random.choice(_DISPATCH_ACKS.get(event, ["10-4 {cs}."]))
        ack = ack_tmpl.format(cs=officer["callsign"])
        if self._dispatch_speak_fn:
            with self._play_lock:
                self._dispatch_speak_fn(ack)
        if self.on_dispatch_ack:
            self.on_dispatch_ack(ack)

    # ── GPT helpers ───────────────────────────────────────────────────────────

    def _generate_officer_line(self, officer: dict, event: str) -> str:
        cs  = officer["callsign"]
        loc = random.choice(_LOCATIONS)
        veh = random.choice(_VEHICLES)
        officer["location"] = loc

        prompts = {
            "traffic_stop":  f"ONE radio transmission: officer {cs} calls dispatch showing them on a traffic stop of a {veh} at {loc}. Under 20 words. Start with callsign.",
            "clear":         f"ONE radio transmission: officer {cs} calls dispatch to say code 4 and returning to service from {loc}. Under 15 words. Start with callsign.",
            "scene_arrival": f"ONE radio transmission: officer {cs} calls dispatch saying 10-23 at {loc}. Under 15 words. Start with callsign.",
            "patrol_obs":    f"ONE radio transmission: officer {cs} notes a suspicious {veh} at {loc}. Under 20 words. Start with callsign.",
            "request_info":  f"ONE radio transmission: officer {cs} asks dispatch to run a plate on a {veh} at {loc}. Under 20 words. Start with callsign.",
        }
        try:
            r = self._openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Write realistic, brief police radio speech. No quotes or narration. Raw radio text only. Always start with the officer callsign."},
                    {"role": "user",   "content": prompts.get(event, prompts["patrol_obs"])},
                ],
                max_tokens=60, temperature=0.88,
            )
            return r.choices[0].message.content.strip().strip('"').strip("'")
        except Exception as e:
            logger.error(f"GPT chatter: {e}"); return ""

    def _generate_officer_response(self, officer: dict, player_text: str) -> str:
        cs = officer["callsign"]
        try:
            r = self._openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"You are police officer {cs}. Reply to a radio transmission from {self.player_callsign}. 1-2 sentences, under 25 words, 10-codes, police radio style. Start with your callsign on first contact."},
                    {"role": "user",   "content": f"{self.player_callsign} just said: '{player_text}'"},
                ],
                max_tokens=80, temperature=0.78,
            )
            return r.choices[0].message.content.strip().strip('"').strip("'")
        except Exception as e:
            logger.error(f"GPT officer response: {e}"); return ""

    # ── Player address detection ───────────────────────────────────────────────

    def handle_player_address(self, player_text: str) -> bool:
        """If the player named a specific officer, have them respond. Returns True if handled."""
        tl = player_text.lower()
        for cs, officer in self.officers.items():
            if cs.lower() in tl or cs.lower().replace("-", " ") in tl:
                response = self._generate_officer_response(officer, player_text)
                if response:
                    logger.info(f"[{cs}] (response): {response!r}")
                    time.sleep(0.6)
                    with self._play_lock:
                        self._speak_as_officer(officer, response)
                    if self.on_officer_speech:
                        self.on_officer_speech(cs, response)
                return True
        return False

    def detect_named_officer(self, text: str) -> Optional[str]:
        """Return callsign if a specific officer is named in text, else None."""
        tl = text.lower()
        for cs in self.officers:
            if cs.lower() in tl or cs.lower().replace("-", " ") in tl:
                return cs
        return None

    def officer_confirm_backup(self, callsign: str, delay: float = 2.0):
        """Have the named officer confirm backup assignment over radio."""
        officer = self.officers.get(callsign)
        if not officer:
            return
        time.sleep(delay)
        text = f"{callsign}, copy. 10-76 to {self.player_callsign}'s location."
        logger.info(f"[BACKUP] {callsign}: {text!r}")
        with self._play_lock:
            self._speak_as_officer(officer, text)
        if self.on_officer_speech:
            self.on_officer_speech(callsign, text)

    # ── TTS playback ──────────────────────────────────────────────────────────

    def _make_officer_click(self, callsign: str, release: bool = False) -> np.ndarray:
        """
        Build a PTT click for a specific officer.
        Each callsign has a unique tone frequency mixed into bandpass noise
        so listeners can immediately identify who is transmitting.
        release=True → softer, slower-decay key-down version.
        """
        from scipy import signal as sp_sig
        freq = _OFFICER_SQUELCH_HZ.get(callsign, 750)
        dur  = 0.10 if not release else 0.08
        t    = np.linspace(0, dur, int(dur * self.SAMPLE_RATE), endpoint=False)
        nyq  = self.SAMPLE_RATE / 2

        # Bandpass noise body
        noise = np.random.normal(0, 0.45, len(t)).astype(np.float32)
        b, a  = sp_sig.butter(4, [380 / nyq, 3400 / nyq], btype="band")
        noise = sp_sig.lfilter(b, a, noise).astype(np.float32)

        # Officer ID tone + envelope
        decay = 42 if not release else 26
        env   = np.exp(-t * decay).astype(np.float32)
        tone  = np.sin(2 * np.pi * freq * t).astype(np.float32) * env * 0.45
        click = (noise * env + tone) * 0.70
        return np.clip(click, -0.85, 0.85).astype(np.float32)

    def _officer_squelch(self, callsign: str, release: bool = False):
        """Play a PTT click for the given officer (key-up or key-down)."""
        import sounddevice as sd
        try:
            click = self._make_officer_click(callsign, release=release)
            sd.play(click, samplerate=self.SAMPLE_RATE, blocking=True)
        except Exception:
            pass

    def _speak_as_officer(self, officer: dict, text: str):
        import io
        import sounddevice as sd
        from scipy import signal as sp_sig
        cs = officer["callsign"]
        # Suppress dispatcher mic so the officer audio is never captured by VAD
        if self.mic_suppressed is not None:
            self.mic_suppressed.set()
        try:
            mp3 = self._tts(text, officer.get("voice_id"))
            if not mp3:
                return
            from pydub import AudioSegment
            audio = (AudioSegment.from_mp3(io.BytesIO(mp3))
                     .set_channels(1)
                     .set_frame_rate(self.SAMPLE_RATE)
                     .set_sample_width(2))
            s  = np.array(audio.get_array_of_samples(), dtype=np.float32) / 32768.0
            fx = self._radio_fx(s, float(self._config.get("radio_intensity", 0.82)))

            # ── Pitch shift: resample to change perceived vocal pitch ──────────
            factor = float(officer.get("pitch", _OFFICER_PITCH.get(cs, 1.0)))
            if abs(factor - 1.0) > 0.01:
                target_len = int(len(fx) * factor)
                fx = sp_sig.resample(fx, target_len).astype(np.float32)

            self._officer_squelch(cs, release=False)                  # key-up
            sd.play(fx, samplerate=self.SAMPLE_RATE, blocking=True)
            self._officer_squelch(cs, release=True)                   # key-down
        except Exception as e:
            logger.error(f"Officer speak: {e}")
        finally:
            time.sleep(0.45)
            if self.mic_suppressed is not None:
                self.mic_suppressed.clear()
