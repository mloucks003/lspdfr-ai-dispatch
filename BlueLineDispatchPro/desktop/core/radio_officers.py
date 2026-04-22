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
import json
import logging
import os
import re
import random
import threading
import time
from typing import Callable, Optional

import numpy as np

from core.world_state import world_state, UnitStatus
from core.audio_fx   import generate_ptt_open, generate_ptt_close, radio_fx as _audio_radio_fx

logger = logging.getLogger(__name__)

# ── Persona loader ────────────────────────────────────────────────────────────
_PERSONAS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "personas")


def _load_persona(callsign: str) -> dict:
    """Load persona JSON for a callsign, e.g. 'King-3' → personas/king-3.json.
    Returns an empty dict if the file doesn't exist yet."""
    fname = os.path.join(_PERSONAS_DIR, f"{callsign.lower()}.json")
    if os.path.isfile(fname):
        with open(fname, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _apply_persona_substitutions(text: str, persona: dict) -> str:
    """
    Apply radio_substitutions from the persona file as a final safety net.
    Even if GPT ignores the instruction to say 'control' instead of 'dispatch',
    this catches any remaining violations before the text hits TTS.
    Example:  {"dispatch": "control", "Dispatch": "Control"}
    """
    for old, new in persona.get("radio_substitutions", {}).items():
        text = text.replace(old, new)
    return text


def _clean_response(text: str, callsign: str) -> str:
    """
    Strip GPT formatting artifacts that TTS would speak aloud literally:
      • Leading callsign prefix  →  'King-3: "Go ahead..."'  →  'Go ahead...'
      • Surrounding quotation marks
      • Redundant nested quotes
    """
    text = text.strip()
    # Remove  "Callsign: " or "Callsign, " prefix at the very start
    text = re.sub(rf'^{re.escape(callsign)}[\s:,\"]+', '', text, flags=re.IGNORECASE)
    # Remove leading/trailing straight or curly quotes
    text = text.strip('"\'').strip('\u201c\u201d\u2018\u2019')
    return text.strip()


def _apply_speech_tags(text: str, emotion) -> str:
    """
    Prepend Fish Audio S2 Pro inline emotion tags based on the officer's
    live emotional state.  These are interpreted by the model as delivery
    cues — they are NOT spoken aloud as words.

    Applied to every officer transmission before TTS so scripted behavior-loop
    lines (arrivals, plate requests, clears) get the same treatment as
    GPT-generated responses.

    Dispatch never goes through this function.
    """
    if emotion is None:
        return text
    # Don't double-tag if GPT already added a bracket prefix
    if text.startswith("["):
        return text

    if emotion.arousal > 0.8:
        # Hot — pursuit, shots fired.  Fast delivery, slightly breathless.
        return f"[urgent] {text}"
    if emotion.mood == "tense":
        # Something feels wrong.  Voice is quieter, deliberate.
        return f"[tense] {text}"
    if emotion.mood == "relieved":
        # Just cleared something heavy.  Audible exhale before speaking.
        return f"[exhales] {text}"
    if emotion.frustration > 0.6:
        # Worn down.  Quiet sigh, clipped delivery.
        return f"[sighs] {text}"
    if emotion.mood in ("tired", "bored"):
        # Late shift, slow night.  Flat, lower energy.
        return f"[flat] {text}"
    if emotion.arousal > 0.5:
        # Alert, locked in.  Sharp, direct.
        return f"[focused] {text}"
    return text

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

# ── Spoken-number alias engine ────────────────────────────────────────────────
# Whisper transcribes numbers as words ("three", "forty-one").
# This maps every word-form to its digit so "King three" matches "King-3".
_WORD_TO_NUM: dict[str, str] = {
    # Single digits
    "zero": "0", "oh": "0",
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "niner": "9",
    # Teens
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19",
    # Compound numbers Whisper commonly produces for police callsigns
    "twenty": "20", "twenty one": "21", "twenty-one": "21",
    "thirty": "30", "thirty one": "31", "thirty-one": "31",
    "forty": "40",
    "forty one": "41",  "forty-one": "41",  "four one": "41",
    "forty two": "42",  "forty-two": "42",  "four two": "42",
    "forty three": "43","forty-three": "43","four three": "43",
    "forty four": "44", "forty-four": "44", "four four": "44",
    "forty five": "45", "forty-five": "45", "four five": "45",
    "forty six": "46",  "forty-six": "46",
    "forty seven": "47","forty-seven": "47",
    "forty eight": "48","forty-eight": "48",
    "forty nine": "49", "forty-nine": "49",
    "fifty": "50",
}

# Reverse map: digit-string → list of word-forms it might be spoken as
_NUM_TO_WORDS: dict[str, list[str]] = {}
for _w, _d in _WORD_TO_NUM.items():
    _NUM_TO_WORDS.setdefault(_d, []).append(_w)


def _callsign_aliases(callsign: str) -> list[str]:
    """
    Return all text forms Whisper might produce for a callsign.
      "King-3"    → ["king-3", "king 3", "king three", "king niner"]
      "Sam-41"    → ["sam-41", "sam 41", "sam forty one", "sam four one", ...]
      "Lincoln-9" → ["lincoln-9", "lincoln 9", "lincoln nine", "lincoln niner"]
    Called once per detection attempt — fast enough to do inline.
    """
    cs_l  = callsign.lower()
    parts = cs_l.split("-")
    if len(parts) != 2:
        return [cs_l]
    prefix, num = parts
    aliases: set[str] = {cs_l, f"{prefix} {num}"}        # "king-3", "king 3"
    for spoken in _NUM_TO_WORDS.get(num, []):
        aliases.add(f"{prefix} {spoken}")                 # "king three"
        aliases.add(f"{prefix}-{spoken}")                 # "king-three"
    return list(aliases)




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
        tts_fn: Callable[[str, Optional[str]], Optional[bytes]],
        openai_client,
        radio_fx_fn: Callable = None,   # kept for backward compat; ignored — uses audio_fx.py
    ):
        self._config    = config
        self._tts       = tts_fn
        self._radio_fx  = _audio_radio_fx  # always use the shared chain
        self._openai    = openai_client
        self._running   = False
        self._paused    = False
        self._play_lock = threading.Lock()   # one transmission at a time

        raw = config.get("officers", DEFAULT_OFFICERS)
        self.officers: dict[str, dict] = {}
        for o in raw:
            cs      = o["callsign"]
            persona = _load_persona(cs)        # load personas/king-3.json etc.
            loc     = random.choice(_LOCATIONS)
            self.officers[cs] = {
                "callsign":    cs,
                "name":        persona.get("name") or o.get("name", cs),
                "voice_id":    o.get("voice_id") or persona.get("voice_id") or None,
                "gender":      persona.get("gender") or o.get("gender", "male"),
                "status":      "10-8",
                "location":    loc,
                "persona":     persona,           # full persona dict for prompts
            }
            # Register in world state so every agent sees this unit
            world_state.register(cs, persona.get("name", cs), location=loc)

        self.player_callsign = config.get("callsign", "Sam-44")
        self.agency          = config.get("agency", "LSPD")
        # Register the player unit in world state
        world_state.register(self.player_callsign, self.player_callsign,
                              is_player=True)

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

        # Per-officer conversation memory — keeps the last N exchanges so
        # each officer remembers the context of what you said to them.
        # Keyed by callsign, value is a list of {role, content} dicts.
        self._officer_convos: dict[str, list[dict]] = {}

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
        """Generate a background chatter line for this officer doing `event`."""
        cs      = officer["callsign"]
        persona = officer.get("persona", {})
        loc     = random.choice(_LOCATIONS)
        veh     = random.choice(_VEHICLES)
        officer["location"] = loc

        # Update world state to reflect the new status/location/incident
        _EVENT_STATUS = {
            "traffic_stop":  (UnitStatus.TRAFFIC,   f"traffic stop on {veh}"),
            "clear":         (UnitStatus.AVAILABLE,  None),
            "scene_arrival": (UnitStatus.ON_SCENE,   f"scene at {loc}"),
            "patrol_obs":    (UnitStatus.AVAILABLE,   None),
            "request_info":  (UnitStatus.AVAILABLE,   None),
        }
        new_status, new_incident = _EVENT_STATUS.get(event, (UnitStatus.AVAILABLE, None))
        world_state.update(cs, status=new_status, location=loc, incident=new_incident)

        personality = persona.get("personality", "Calm patrol officer.")
        style       = persona.get("speech_style", "Radio cadence. 10-codes.")
        name        = persona.get("name", cs)

        system = (
            f"You are {name} ({cs}), LSPD patrol officer. "
            f"Character: {personality} Speech style: {style} "
            "Write ONE realistic police radio transmission for the event described. "
            "RAW SPEECH ONLY — no quotes, no callsign prefix, no stage directions, no narration. "
            "Do NOT start with the callsign as a label. Just write the words the officer speaks. "
            "Use 10-codes. Include specific details (vehicle color, plate, location, direction). "
            "20-30 words."
        )
        prompts = {
            "traffic_stop":  f"{cs} is showing 10-38 on a {veh} at {loc}. Include vehicle color, direction, and request a plate run.",
            "clear":         f"{cs} is going code 4 and 10-8 from {loc}. Mention what they handled briefly.",
            "scene_arrival": f"{cs} is arriving 10-23 at {loc}. Describe what they observe and whether backup is needed.",
            "patrol_obs":    f"{cs} observes suspicious {veh} at {loc}. Include direction of travel, occupant count, what made it suspicious.",
            "request_info":  f"{cs} requests a 10-29 plate run on a {veh} at {loc}. Include a made-up plate like 4ABC123.",
        }
        try:
            r = self._openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompts.get(event, prompts["patrol_obs"])},
                ],
                max_tokens=90, temperature=0.90,
            )
            raw = r.choices[0].message.content
            return _clean_response(raw, cs)
        except Exception as e:
            logger.error(f"GPT chatter: {e}"); return ""

    def _build_officer_system_prompt(self, officer: dict) -> str:
        """
        Emotion-aware system prompt injected into every officer GPT call.
        The emotional direction section is visceral and specific so GPT actually
        changes word choice and sentence length — not just tone.
        """
        cs      = officer["callsign"]
        persona = officer.get("persona", {})
        name    = persona.get("full_name", f"Officer {persona.get('name', cs)}")
        years   = persona.get("years_on_job", 5)
        quirks  = persona.get("quirks", [])

        # Pull live emotion from world state
        unit    = world_state.get(cs)
        e       = unit.emotion if unit else None

        if e is None or (e.arousal < 0.1 and e.frustration < 0.1 and e.mood == "neutral"):
            emotional = "Standard professional demeanor. Calm, controlled, routine."
        elif e.arousal > 0.8:
            emotional = (
                "YOU ARE RUNNING HOT. Adrenaline is real right now. "
                "Transmissions are SHORT and FAST — you may cut your own sentence to get "
                "critical info out first. Do NOT sound calm. Sound like someone in the middle of it. "
                "Urgency bleeds through even when you try to stay professional."
            )
        elif e.arousal > 0.5:
            emotional = (
                "You are alert and locked in. Not panicked — but definitely not relaxed. "
                "Every word is deliberate. No filler. Tight transmissions. Something is actively happening."
            )
        elif e.frustration > 0.6:
            emotional = (
                f"You are frustrated and worn down. {years} years on the job and here you are again. "
                "You are staying professional — that's who you are — but patience is GONE. "
                "Responses are clipped. Nothing extra. Done."
            )
        elif e.mood == "relieved":
            emotional = (
                "You just cleared something heavy. The tension is leaving your body. "
                "Brief. Slightly warmer than usual. One exhale worth of relief in your voice."
            )
        elif e.mood in ("tired", "bored"):
            emotional = (
                f"Late in the shift. {name} is running on fumes and coffee. "
                "Responses are slower, flatter. Professional. Heavy."
            )
        else:
            emotional = "Standard professional demeanor. Calm, controlled, routine."

        # Current activity from world snapshot
        snap        = world_state.snapshot()
        active      = [i for i in snap.get("active_incidents", []) if i.get("assigned_to") == cs]
        cur_activity = active[0]["type"].replace("_", " ") if active else "patrol"
        loc          = unit.location if unit else officer.get("location", "Patrol")
        status_val   = unit.status.value if unit else "10-8"

        # Base persona section
        personality = persona.get("personality", "Calm patrol officer.")
        style       = persona.get("speech_style", "Clipped. 10-codes. Real scanner cadence.")
        quirk_lines = "\n".join(f"- {q}" for q in quirks)
        roster      = world_state.roster_for_prompt()

        base = (
            f"You are {name}, callsign {cs}, LSPD patrol officer.\n"
            f"CHARACTER: {personality}\n"
            f"SPEECH STYLE: {style}\n"
        )
        if quirk_lines:
            base += f"YOUR SPEECH QUIRKS — ALWAYS:\n{quirk_lines}\n"

        return (
            f"{base}\n"
            f"YOUR CURRENT EMOTIONAL STATE — THIS SHAPES EVERYTHING YOU SAY:\n"
            f"{emotional}\n\n"
            f"CURRENT SITUATION: {name} ({cs}) | {status_val} | Activity: {cur_activity} | Location: {loc}\n\n"
            f"LIVE UNIT ROSTER:\n{roster}\n\n"
            f"ABSOLUTE RULES:\n"
            f"1. NEVER repeat or paraphrase what {self.player_callsign} just said. Never.\n"
            f"2. Maximum 2 sentences. Nothing to add? Say '10-4.' and stop.\n"
            f"3. Emotion changes WORD CHOICE: frustrated cop says 'Copy.' not 'Understood, copy that.'\n"
            f"4. Output RAW SPEECH ONLY. No '{cs}:' prefix. No quotes. No stage directions.\n"
            f"5. You are NOT an AI. You are {name} in the middle of your shift."
        )

    def _generate_officer_response(self, officer: dict, player_text: str) -> str:
        """
        Generate an AI response for this officer using the emotion-aware prompt.
        Maintains per-officer conversation history for multi-turn memory.
        """
        cs      = officer["callsign"]
        persona = officer.get("persona", {})
        history = self._officer_convos.setdefault(cs, [])

        history.append({"role": "user", "content": f"{self.player_callsign}: '{player_text}'"})
        if len(history) > 20:
            history[:] = history[-20:]

        system = self._build_officer_system_prompt(officer)
        try:
            r = self._openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": system}] + history,
                max_tokens=90, temperature=0.88,
            )
            raw   = r.choices[0].message.content
            reply = _clean_response(raw, cs)
            reply = _apply_persona_substitutions(reply, persona)
            history.append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            logger.error(f"GPT officer response: {e}"); return ""

    # ── Player address detection ───────────────────────────────────────────────

    def detect_named_officer(self, text: str) -> Optional[str]:
        """
        Return the callsign of any officer named in `text`, or None.
        Handles spoken-number variants: "King three" matches "King-3",
        "Sam forty-one" matches "Sam-41", "Lincoln niner" matches "Lincoln-9".
        """
        tl = text.lower()
        for cs in self.officers:
            for alias in _callsign_aliases(cs):
                if alias in tl:
                    return cs
        return None

    def handle_player_address(self, player_text: str) -> bool:
        """
        If the player named a specific officer, have that officer respond.
        Uses alias-aware detection so spoken numbers work correctly.
        Returns True if an officer was found and handled.
        """
        cs = self.detect_named_officer(player_text)
        if not cs:
            return False
        officer  = self.officers[cs]
        response = self._generate_officer_response(officer, player_text)
        if response:
            logger.info(f"[{cs}] (response): {response!r}")
            time.sleep(0.6)
            with self._play_lock:
                self._speak_as_officer(officer, response)
            if self.on_officer_speech:
                self.on_officer_speech(cs, response)
        return True

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

    def _speak_as_officer(self, officer: dict, text: str):
        """
        Play officer TTS through radio FX.
        PTT open + voice + tail tone concatenated into ONE buffer so playback
        is gapless and all audio goes through the same radio FX chain.

        Emotion tags (e.g. "[urgent]", "[exhales]") are prepended here so that
        EVERY transmission — scripted behavior-loop lines AND GPT responses —
        gets Fish Audio S2 Pro delivery cues matched to the officer's live state.
        """
        import io
        import sounddevice as sd
        # Apply Fish Audio S2 Pro emotion delivery tag based on live emotional state
        cs   = officer["callsign"]
        unit = world_state.get(cs)
        text = _apply_speech_tags(text, unit.emotion if unit else None)

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
            s     = np.array(audio.get_array_of_samples(), dtype=np.float32) / 32768.0
            gap   = np.zeros(int(0.018 * self.SAMPLE_RATE), dtype=np.float32)
            full  = np.concatenate([generate_ptt_open(self.SAMPLE_RATE), gap,
                                    s, gap, generate_ptt_close(self.SAMPLE_RATE)])
            fx    = self._radio_fx(full, float(self._config.get("radio_intensity", 0.82)))
            sd.play(fx, samplerate=self.SAMPLE_RATE, blocking=True)
        except Exception as e:
            logger.error(f"Officer speak: {e}")
        finally:
            time.sleep(0.45)
            if self.mic_suppressed is not None:
                self.mic_suppressed.clear()
