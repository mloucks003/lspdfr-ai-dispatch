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

# Distinct squelch-click frequencies per unit (Hz).
# Listeners learn to recognise each officer by their key-up tone.
_OFFICER_SQUELCH_HZ = {
    "Sam-41":    680,
    "Lincoln-9": 820,
    "King-3":    960,
}

_DISPATCH_ACKS = {
    "traffic_stop":  [
        "Copy {cs}, showing you 10-38 at your location. Running that plate now, stand by.",
        "10-4 {cs}, 10-38 noted. I'll run that plate for you. Stand by one.",
        "Copy {cs}, you're code 6 on that stop. Stand by for the return.",
    ],
    "clear":         [
        "10-4 {cs}, showing you 10-8. You're available.",
        "Copy {cs}, code 4. Return to service. I'll advise on any calls in your area.",
        "10-4 {cs}, you're clear. Stand by for calls.",
    ],
    "scene_arrival": [
        "Copy {cs}, 10-23 noted. Keep me advised. Backup is standing by if needed.",
        "10-4 {cs}, you're on scene. I'll hold the channel. Advise when code 4.",
        "Copy {cs}, on scene. Additional units are available. Keep the radio open.",
    ],
    "patrol_obs":    [
        "10-4 {cs}. All units in the area — {cs} has a suspicious vehicle. Be advised.",
        "Copy {cs}, noted. All units copy the observation. {cs}, keep me advised.",
        "10-4 {cs}, I'll advise all units. Anyone in that area, assist {cs} as needed.",
    ],
    "request_info":  [
        "Copy {cs}, I'll run that for you right now. Stand by for the return.",
        "10-4 {cs}, checking that registration now. Stand by one.",
        "Copy {cs}, querying that plate. Stand by.",
    ],
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

        # Natural radio gap between transmissions
        time.sleep(random.uniform(1.0, 2.2))
        if self._paused:
            return

        # Dispatch acknowledges with a substantive response
        ack_tmpl = random.choice(_DISPATCH_ACKS.get(event, ["10-4 {cs}."]))
        ack = ack_tmpl.format(cs=officer["callsign"])
        if self._dispatch_speak_fn:
            with self._play_lock:
                self._dispatch_speak_fn(ack)
        if self.on_dispatch_ack:
            self.on_dispatch_ack(ack)

        # For traffic stops and plate requests, continue into a full plate-return exchange
        if event in ("traffic_stop", "request_info"):
            threading.Thread(
                target=self._do_plate_return_followup,
                args=(officer,),
                daemon=True,
                name=f"plate_return_{officer['callsign']}",
            ).start()

    def _do_plate_return_followup(self, officer: dict):
        """
        Simulate the realistic 2-step plate-return exchange that happens after
        every traffic stop: dispatch runs the plate, then reads back the result,
        then the officer acknowledges.  Creates the multi-turn conversation the
        player hears on a real scanner.
        """
        cs = officer["callsign"]

        # Simulate the plate being run (realistic 5-10 second wait)
        delay = random.uniform(5.0, 10.0)
        step  = 0.2
        for _ in range(int(delay / step)):
            if not self._running or self._paused:
                return
            time.sleep(step)

        if self._paused:
            return

        # Generate a realistic plate return
        first_names = ["Michael", "James", "David", "Robert", "Sarah",
                       "Maria", "John", "Lisa", "Anthony", "Karen"]
        last_names  = ["Johnson", "Williams", "Brown", "Garcia",
                       "Martinez", "Davis", "Wilson", "Anderson", "Taylor"]
        plates      = ["4ABC123", "7XYZ891", "2DEF456", "9GHI234",
                       "6JKL567", "3MNO890", "8PQR345", "1STU678"]
        years       = list(range(2005, 2024))
        makes       = ["Toyota", "Honda", "Ford", "Chevrolet",
                       "Dodge", "Nissan", "Hyundai", "GMC"]

        owner     = f"{random.choice(first_names)} {random.choice(last_names)}"
        plate     = random.choice(plates)
        year      = random.choice(years)
        make      = random.choice(makes)
        has_warrant = random.random() < 0.15   # 15 % chance — realistic hit rate

        if has_warrant:
            warrant_str = "ACTIVE FELONY WARRANT ON FILE. Use caution."
        else:
            warrant_str = "returns negative, no wants or warrants."

        return_text = (
            f"{cs}, 10-29 return on plate {plate} — "
            f"registered to {owner}, {year} {make}. "
            f"{warrant_str}"
        )
        logger.info(f"[DISPATCH→{cs}] plate return: {return_text!r}")
        if self._dispatch_speak_fn:
            with self._play_lock:
                self._dispatch_speak_fn(return_text)
        if self.on_dispatch_ack:
            self.on_dispatch_ack(return_text)

        # Officer confirms after hearing the return
        time.sleep(random.uniform(1.2, 2.5))
        if self._paused:
            return

        if has_warrant:
            confirm = (
                f"{cs}, copy — FELONY warrant. Requesting backup at my location. "
                f"Detaining the subject now."
            )
        else:
            confirm = (
                f"{cs}, copy — 10-29 negative. Continuing the stop. Advise when complete."
            )
        logger.info(f"[{cs}] (plate confirm): {confirm!r}")
        with self._play_lock:
            self._speak_as_officer(officer, confirm)
        if self.on_officer_speech:
            self.on_officer_speech(cs, confirm)

    # ── GPT helpers ───────────────────────────────────────────────────────────

    def _generate_officer_line(self, officer: dict, event: str) -> str:
        cs  = officer["callsign"]
        loc = random.choice(_LOCATIONS)
        veh = random.choice(_VEHICLES)
        officer["location"] = loc

        prompts = {
            "traffic_stop":  (
                f"Write ONE police radio transmission: Officer {cs} is showing themselves on a traffic stop. "
                f"Vehicle: {veh}. Location: {loc}. Include the vehicle color and direction of travel. "
                f"Request a plate run. 20-30 words. Callsign first. Use 10-codes like 10-38."
            ),
            "clear":         (
                f"Write ONE police radio transmission: Officer {cs} is going code 4 and returning to service from {loc}. "
                f"Mention what they handled. 15-20 words. Callsign first. Use 10-codes."
            ),
            "scene_arrival": (
                f"Write ONE police radio transmission: Officer {cs} is arriving on scene at {loc}. "
                f"Describe what they observe — people, vehicles, activity. Request backup if needed. "
                f"20-28 words. Callsign first. Use 10-23."
            ),
            "patrol_obs":    (
                f"Write ONE police radio transmission: Officer {cs} advises dispatch of a suspicious {veh} at {loc}. "
                f"Include direction of travel, occupant count, and what made it suspicious. "
                f"20-30 words. Callsign first."
            ),
            "request_info":  (
                f"Write ONE police radio transmission: Officer {cs} requests a plate/registration run on a {veh} at {loc}. "
                f"Include a plausible plate number (e.g. 4ABC123) and ask for wants and warrants. "
                f"20-28 words. Callsign first."
            ),
        }
        try:
            r = self._openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": (
                        "You write realistic LSPD police radio transmissions that sound exactly like a real scanner. "
                        "Raw speech only — no quotes, no narration, no stage directions. "
                        "Use 10-codes naturally. Include specific details: locations, vehicle descriptions, "
                        "plate numbers, suspect descriptions, directions of travel. "
                        "Always start with the officer's callsign. Match the length and detail of real dispatch recordings."
                    )},
                    {"role": "user",   "content": prompts.get(event, prompts["patrol_obs"])},
                ],
                max_tokens=80, temperature=0.88,
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
                    {"role": "system", "content": (
                        f"You are LSPD officer {cs} on a radio channel. "
                        f"Reply to {self.player_callsign}'s transmission. "
                        "Respond like a real officer on a scanner — include your current location, "
                        "what you're doing, your ETA if relevant, and any tactical details. "
                        "Use 10-codes naturally. 15-25 words. Start with your callsign. "
                        "No filler. No pleasantries. Raw radio speech only."
                    )},
                    {"role": "user",   "content": f"{self.player_callsign}: '{player_text}'"},
                ],
                max_tokens=70, temperature=0.78,
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
        """Play officer TTS through radio FX at correct sample rate — no pitch shift, no speed tricks."""
        import io
        import sounddevice as sd
        cs = officer["callsign"]
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

            self._officer_squelch(cs, release=False)          # key-up click
            sd.play(fx, samplerate=self.SAMPLE_RATE, blocking=True)
            self._officer_squelch(cs, release=True)           # key-down click
        except Exception as e:
            logger.error(f"Officer speak: {e}")
        finally:
            time.sleep(0.45)
            if self.mic_suppressed is not None:
                self.mic_suppressed.clear()
