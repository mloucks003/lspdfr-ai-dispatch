"""
BlueLineDispatchPro — AI Dispatcher Engine

Flow:
  IDLE: Vosk watches for callsign
  SESSION: Full back-and-forth conversation — no callsign needed
    → dispatcher speaks → auto-listens → officer speaks → repeat
    → session closes after SESSION_TIMEOUT seconds of silence
"""
import io
import json
import logging
import os
import queue
import threading
import time
import wave

from core.world_state import world_state, UnitStatus

import numpy as np
import requests
import sounddevice as sd
from scipy import signal as sp

logger = logging.getLogger(__name__)

SAMPLE_RATE     = 16000
CHUNK_FRAMES    = 3200   # 200 ms per chunk
SESSION_TIMEOUT = 20.0   # seconds of silence before session closes


class AIDispatcher:

    STATES = {
        "idle":          ("🎙  Listening for callsign...",          "#2C2C4A"),
        "acknowledging": ("📡  Opening channel...",                 "#1A4A7A"),
        "listening":     ("🔴  Listening — go quiet when done",     "#7A1A1A"),
        "processing":    ("⚙   Processing...",                     "#7A3A00"),
        "responding":    ("📻  Dispatcher responding...",           "#1A5C2E"),
        "session_wait":  ("🟡  Channel open — speak when ready",    "#4A3A00"),
    }

    def __init__(self, config: dict):
        self.config    = config
        self.callsign  = config.get("callsign", "Unit 1")
        self.agency    = config.get("agency",   "LSPD")
        self._variants = [v.lower() for v in
                          config.get("callsign_variants",
                                     [self.callsign.lower().replace("-", " ")])]

        # VAD tuning
        self._speech_thresh      = int(config.get("speech_threshold",   300))
        self._silence_thresh     = int(config.get("silence_threshold",  200))
        self._silence_end_chunks = int(
            float(config.get("silence_end_seconds", 1.5)) * SAMPLE_RATE / CHUNK_FRAMES)
        self._max_record_chunks  = int(
            float(config.get("max_record_seconds", 20)) * SAMPLE_RATE / CHUNK_FRAMES)
        self._session_timeout_chunks = int(
            SESSION_TIMEOUT * SAMPLE_RATE / CHUNK_FRAMES)

        self._vosk_gate  = 40      # updated by _calibrate_mic at startup
        self._state      = "idle"
        self._in_session = False
        self._running    = False
        self._stream     = None
        self._audio_q: queue.Queue = queue.Queue(maxsize=200)
        self._conversation: list   = []

        # ── Mic suppression during playback ───────────────────────────────────
        # When set, _wait_for_speech_then_record discards all incoming audio.
        # Prevents speaker bleed being picked up as user speech.
        self._mic_suppressed = threading.Event()   # SET = suppress, CLEAR = listen

        # ── Address-routing state ──────────────────────────────────────────────
        # Tracks who the player last explicitly addressed.
        # Subsequent transmissions without a new address go to the same entity.
        self._last_addressee: str = "dispatch"

        # Public callbacks — wired by dispatcher_main.py
        self.on_state_change      = None
        self.on_user_speech       = None
        self.on_dispatcher_speech = None
        self.on_error             = None

        from openai import OpenAI
        self._openai   = OpenAI(api_key=config["openai_api_key"])
        self._vosk_rec = self._load_vosk()

        # LSPDFR plate bridge (optional — only active when plugin is running)
        from core.plate_checker import PlateChecker
        bridge_path = config.get(
            "lspdfr_bridge_path",
            os.path.join(os.environ.get("LOCALAPPDATA", "C:/temp"), "BlueLineDispatch"),
        )
        self._plate_checker = PlateChecker(bridge_path,
                                           timeout=config.get("plate_timeout", 6.0))
        # Cache last plate result so ID checks return the same person
        self._last_plate_data: dict = {}

        # AI officer unit roster — other units on the radio channel
        from core.radio_officers import RadioOfficerManager
        self._officers = RadioOfficerManager(
            config=config,
            tts_fn=self._tts_with_voice,
            radio_fx_fn=self._radio_fx,
            openai_client=self._openai,
        )
        self._officers.set_dispatch_speak(self._speak)
        self._officers.on_officer_speech  = self._on_officer_chatter
        self._officers.on_dispatch_ack    = self._on_dispatch_ack
        # Share the suppression event so officer audio also silences the mic
        self._officers.mic_suppressed     = self._mic_suppressed

    # ── Vosk ──────────────────────────────────────────────────────────────────

    def _load_vosk(self):
        from vosk import Model, KaldiRecognizer
        path = self.config.get("vosk_model_path", "models/vosk-model-en-us")
        logger.info(f"Loading Vosk from: {path}")
        rec = KaldiRecognizer(Model(path), SAMPLE_RATE)
        rec.SetWords(False)
        return rec

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._stream  = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1,
            dtype="int16", blocksize=CHUNK_FRAMES,
            callback=self._audio_callback,
        )
        self._stream.start()
        self._calibrate_mic()
        threading.Thread(target=self._main_loop, daemon=True,
                         name="dispatcher").start()
        self._officers.start()
        logger.info(f"AIDispatcher started — listening for '{self.callsign}'")

    def _calibrate_mic(self):
        """
        Measure 2s of ambient noise and auto-set speech/silence thresholds.
        Prints live levels so the user can see their mic is working.
        """
        print("\n🎙  Calibrating mic — stay quiet for 2 seconds...\n")
        samples = []
        for _ in range(int(2.0 * SAMPLE_RATE / CHUNK_FRAMES)):
            try:
                chunk = self._audio_q.get(timeout=1.0)
                rms = int(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
                samples.append(rms)
            except queue.Empty:
                pass

        if not samples:
            print("⚠  No audio detected during calibration — check your mic in Windows Sound Settings\n")
            return

        ambient  = int(np.mean(samples))
        peak     = max(samples)
        # Speech threshold = 3× ambient (triggers recording mid-sentence)
        # Silence threshold = 1.5× ambient (hysteresis band)
        # Vosk gate = 1.5× ambient (filters game noise, passes normal voice)
        auto_speech  = max(ambient * 3, 60)
        auto_silence = max(int(ambient * 1.5), 40)
        self._vosk_gate = max(int(ambient * 1.5), 40)

        if self.config.get("auto_calibrate", True):
            self._speech_thresh  = auto_speech
            self._silence_thresh = auto_silence

        print(f"   Ambient RMS : {ambient}")
        print(f"   Peak RMS    : {peak}")
        print(f"   Vosk gate   : {self._vosk_gate}  (callsign detection)")
        print(f"   Speech thr  : {self._speech_thresh}  (recording trigger)")
        print(f"   Silence thr : {self._silence_thresh}  (recording end)")
        print(f"\n   ✅ Mic calibrated. Say your callsign at normal volume to begin.\n")

    def stop(self):
        self._running = False
        self._officers.stop()
        if self._stream:
            self._stream.stop()
            self._stream.close()

    # ── Officer chatter callbacks ─────────────────────────────────────────────

    def _on_officer_chatter(self, callsign: str, text: str):
        """Forwarded to UI for display."""
        if self.on_user_speech:   # reuse UI hook to show in log (prefixed with callsign)
            pass  # UI wires this separately if desired
        logger.info(f"[{callsign}]: {text!r}")

    def _on_dispatch_ack(self, text: str):
        if self.on_dispatcher_speech:
            self.on_dispatcher_speech(text)

    def manual_trigger(self):
        """Button fallback — open a session as if callsign was heard."""
        if self._state == "idle":
            threading.Thread(target=self._run_session,
                             daemon=True).start()

    def clear_history(self):
        self._conversation.clear()
        logger.info("Conversation history cleared")

    # ── Audio ─────────────────────────────────────────────────────────────────

    def _audio_callback(self, indata, frames, time_info, status):
        try:
            self._audio_q.put_nowait(indata.copy().flatten())
        except queue.Full:
            pass  # drop chunk if queue is backed up

    def _flush_queue(self):
        while not self._audio_q.empty():
            try:
                self._audio_q.get_nowait()
            except queue.Empty:
                break

    # ── Main loop — THE only consumer of audio ────────────────────────────────

    def _main_loop(self):
        """
        Single thread owns the audio queue.
        In idle mode:  feeds chunks to Vosk for callsign detection.
        In session:    runs the full conversation loop inline.
        """
        while self._running:
            try:
                chunk = self._audio_q.get(timeout=0.5)
                if self._state == "idle":
                    self._vosk_feed(chunk)
                # All other states: chunks are consumed by _read_chunk_session()
                # which is called from within the session loop below.
                # We only reach here in idle, so non-idle chunks are handled there.
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Main loop: {e}")

    def _vosk_feed(self, chunk: np.ndarray):
        rms = int(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
        # Energy gate — skip quiet chunks so game audio doesn't confuse Vosk.
        # This means only actual speech reaches the recognizer.
        if rms < self._vosk_gate:
            return
        self._vosk_rec.AcceptWaveform(chunk.tobytes())
        partial = json.loads(self._vosk_rec.PartialResult()).get("partial", "")
        if partial and any(v in partial.lower() for v in self._variants):
            self._vosk_rec.Result()  # reset
            self._set_state("acknowledging")
            self._run_session()

    # ── Session — full conversation loop ──────────────────────────────────────

    _BACKUP_PHRASES = [
        "additional unit", "backup", "10-33", "10-78", "assistance",
        "roll a unit", "send a unit", "need help", "officer down",
        "code 3", "respond to", "another unit",
    ]

    # Words that mean the player is explicitly addressing dispatch.
    # Checked BEFORE officer name matching so "Sam-44 county to King-3" → dispatch.
    _DISPATCH_ADDRESS = [
        "county", "dispatch", "control", "lspd", "all units",
        "supervisor", "comm", "communications", "sergeant", "watch commander",
        "radio", "central", "base", "command",
    ]

    def _is_backup_request(self, text: str) -> bool:
        t = text.lower()
        return any(p in t for p in self._BACKUP_PHRASES)

    def _detect_addressee(self, text: str) -> str:
        """
        Return 'dispatch', an officer callsign, or '' (no explicit address — keep last).

        Priority (first match wins):
          1. Explicit dispatch keyword ("county", "dispatch", …)
          2. Officer callsign — uses full spoken-number alias engine so
             "King three", "Sam forty-one", "Lincoln niner" all work.
          3. '' → caller decides what last addressee was
        """
        t = text.lower()
        if any(w in t for w in self._DISPATCH_ADDRESS):
            return "dispatch"
        named = self._officers.detect_named_officer(text)
        if named:
            return named
        return ""   # no explicit address — session keeps using last addressee

    def _run_session(self):
        """
        Opens a radio channel, then loops: listen → route → respond → listen ...
        until SESSION_TIMEOUT silence or the officer explicitly clears.

        Address routing:
          • "[callsign] county / dispatch / LSPD / control …"  → dispatch
          • "[callsign] to [officer callsign] …"               → that officer only
          • No explicit address                                 → same as last turn
        """
        self._in_session  = True
        self._officers.pause()   # freeze background chatter while player talks
        try:
            # Opening acknowledgment from dispatch (always — player said their callsign)
            ack = f"{self.callsign}, go ahead."
            self._speak(ack)
            if self.on_dispatcher_speech:
                self.on_dispatcher_speech(ack)

            while self._running:
                self._set_state("session_wait")
                audio = self._wait_for_speech_then_record()

                if audio is None:
                    logger.info("Session timed out — returning to idle")
                    break

                self._set_state("processing")
                text = self._transcribe(audio)
                logger.info(f"[{self.callsign}]: {text!r}")

                # Reject bleed/short noise
                SHORT_COMMANDS = {
                    "code 4", "code four", "10-4", "negative", "affirmative",
                    "10-8", "copy", "go ahead", "stand by", "standby", "clear",
                }
                words = text.strip().split()
                if not text or (len(words) < 4 and not any(sc in text.lower() for sc in SHORT_COMMANDS)):
                    logger.info(f"Ignoring short/bleed: {text!r}")
                    continue

                if self.on_user_speech:
                    self.on_user_speech(text)

                # ── Determine who the player is talking to ────────────────────
                addressee = self._detect_addressee(text)
                if addressee:
                    self._last_addressee = addressee
                else:
                    addressee = self._last_addressee  # continue with last entity

                # ── Route the transmission ────────────────────────────────────
                if addressee == "dispatch":
                    # Normal dispatch flow
                    ai_text = self._get_ai_response(text)
                    logger.info(f"[DISPATCH]: {ai_text!r}")
                    self._set_state("responding")
                    if self.on_dispatcher_speech:
                        self.on_dispatcher_speech(ai_text)
                    self._speak(ai_text)

                    # Backup? → assigned unit confirms after dispatch responds
                    if self._is_backup_request(text):
                        named    = self._officers.detect_named_officer(text)
                        assigned = named or self._officers.random_callsign()
                        threading.Thread(
                            target=self._officers.officer_confirm_backup,
                            args=(assigned, 1.8),
                            daemon=True,
                        ).start()

                else:
                    # Player is talking to a specific officer — dispatch stays silent
                    logger.info(f"[ROUTE] Player → {addressee}")
                    self._set_state("responding")
                    self._officers.handle_player_address(text)   # blocking — plays inline

                # Close session if officer signed off
                if self._is_closing_transmission(text):
                    logger.info("Officer went clear — closing session")
                    break

        except Exception as e:
            logger.error(f"Session error: {e}")
            if self.on_error:
                self.on_error(str(e))
        finally:
            self._in_session  = False
            self._last_addressee = "dispatch"   # reset for next session
            self._officers.resume()
            self._set_state("idle")
            self._flush_queue()

    # ── VAD — wait for speech onset, then record until silence ───────────────

    def _wait_for_speech_then_record(self) -> np.ndarray | None:
        """
        Phase 1: wait up to SESSION_TIMEOUT for sustained speech to start.
          - Requires MIN_ONSET_CHUNKS consecutive loud chunks to avoid
            false triggers from game audio or brief noise.
          - Keeps a small pre-roll buffer so the start of speech isn't clipped.
        Phase 2: record until SILENCE_END_CHUNKS of silence after speech.
        Returns int16 array, or None if session timed out.
        """
        MIN_ONSET    = 1        # chunks above threshold to confirm speech onset
        PRE_ROLL     = 4        # pre-roll chunks to avoid clipped starts
        LOG_EVERY    = 5        # print RMS every N chunks so user can see mic level

        pre_buf       = []
        onset_count   = 0
        buffer        = []
        speech_heard  = False
        silent_chunks = 0
        timeout_count = 0
        chunk_count   = 0

        while self._running:
            try:
                chunk = self._audio_q.get(timeout=0.5)
            except queue.Empty:
                if not self._running:
                    return None
                continue

            # ── Mic suppression guard ─────────────────────────────────────────
            # Drop this chunk if dispatch/officer audio is currently playing.
            # Prevents speaker bleed from triggering VAD or reaching Whisper.
            if self._mic_suppressed.is_set():
                continue

            rms = int(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))
            chunk_count += 1

            if not speech_heard:
                pre_buf.append(chunk)
                if len(pre_buf) > PRE_ROLL:
                    pre_buf.pop(0)

                # Live RMS readout so user can tune threshold
                if chunk_count % LOG_EVERY == 0:
                    bar = "█" * min(int(rms / 50), 30)
                    print(f"  [MIC] RMS: {rms:>5}  thresh: {self._speech_thresh}  |{bar}")

                if rms >= self._speech_thresh:
                    onset_count += 1
                    if onset_count >= MIN_ONSET:
                        print(f"  [MIC] ✅ Speech detected at RMS {rms} — recording")
                        speech_heard = True
                        buffer = list(pre_buf)
                        self._set_state("listening")
                else:
                    onset_count = 0
                    timeout_count += 1
                    if timeout_count >= self._session_timeout_chunks:
                        print("  [MIC] Session timed out — no speech detected")
                        return None
            else:
                buffer.append(chunk)
                if rms >= self._silence_thresh:
                    silent_chunks = 0
                else:
                    silent_chunks += 1
                    if silent_chunks >= self._silence_end_chunks:
                        print(f"  [MIC] ✅ End of speech — sending to Whisper")
                        break
                if len(buffer) >= self._max_record_chunks:
                    break

        return np.concatenate(buffer).astype(np.int16) if buffer else None

    # ── Session close detection ───────────────────────────────────────────────

    _CLOSE_PHRASES = [
        "code 4", "code four", "10-8", "ten eight",
        "going clear", "out of service", "show me clear",
        "i'm clear", "we're clear", "that'll be all",
    ]

    def _is_closing_transmission(self, text: str) -> bool:
        t = text.lower()
        return any(p in t for p in self._CLOSE_PHRASES)

    # ── Whisper STT ───────────────────────────────────────────────────────────

    def _transcribe(self, audio: np.ndarray) -> str:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        buf.seek(0); buf.name = "tx.wav"
        try:
            return self._openai.audio.transcriptions.create(
                model="whisper-1", file=buf, language="en").text.strip()
        except Exception as e:
            logger.error(f"Whisper: {e}"); return ""

    # ── AI response ───────────────────────────────────────────────────────────

    def _system_prompt(self) -> str:
        cs      = self.callsign
        roster  = world_state.roster_for_prompt()
        return f"""You are a police radio dispatcher for {self.agency}. \
You are talking to officer {cs} over the radio channel.

LIVE UNIT STATUS — you track all of these in real time:
{roster}
Use this to assign backup from available units, reference unit locations, and give realistic ETAs. \
Never say a unit is unavailable if the roster shows them 10-8.

VOICE AND TONE:
You are an LSPD radio dispatcher — professional, calm, zero emotion, zero filler.
No "stay safe", no "of course", no "absolutely". Pure radio cadence.
Speak exactly how LAPD or NYPD dispatch sounds on a real scanner recording.

RESPONSE LENGTH:
Match what a real dispatcher actually says — not artificially short, not wordy.
- Simple ack: 5-10 words. "10-4 {cs}, copy your 10-38."
- Operational response: 20-35 words. Include cross streets, ETAs, unit assignments.
- Plate/ID return: Full read-back with owner name, DOB, status, wants.
- Emergency: Full broadcast. All units, location, nature, responding units, EMS.

RESPONSE STYLE — MATCH THESE EXACTLY:
Traffic stop copy:
  "Copy {cs}, showing you 10-38 on the [vehicle description] at [location], cross street [street]. I show you code 6 at this time."
Backup request:
  "[Unit], respond to {cs}'s 10-20 at [location]. Code 2. {cs}, backup is en route from [area], ETA approximately 2 minutes."
On scene:
  "Copy {cs}, showing you 10-23 at [address]. Keep me advised. [Unit] is available in your area if needed."
Pursuit:
  "Copy {cs}, broadcasting pursuit. All units, vehicle pursuit active [direction] on [street]. Air support notified. Spike strips authorized at [location]."
Shots fired:
  "All units, shots fired at {cs}'s location — [address]. EMS code 3. Sergeant is en route. [Unit], respond to assist."
10-33 / officer needs help:
  "ALL UNITS, 10-33 at {cs}'s location, [address]. [Unit] and [unit], respond code 3. EMS is being dispatched."
Plate return: Use ONLY the data provided in the system message. Read it all back.
Code 4 / clear: "Copy {cs}, code 4. Show you 10-8 and available."
Can't understand: "Say again {cs}, you're broken."
Off-topic / not police-related: respond only "10-4." — nothing more.
If {cs} asks to speak with another unit: say "{cs}, go ahead and reach out to [unit] directly on channel."
Never say another officer is "unavailable" or "not on this channel" — all listed units are on this channel.

10-CODES (use naturally):
10-4 copy, 10-8 available, 10-20 location, 10-23 on scene, 10-29 wants/warrants,
10-33 emergency, 10-38 traffic stop, 10-76 en route, 10-78 need assistance,
10-99 officer down, code 2 urgent no lights/sirens, code 3 lights and sirens.

PLATE AND ID RUNS:
When plate/ID data is provided in a system message, read ALL of it back clearly.
Owner name spelled out. DOB. Vehicle. Wants and warrants status. License status.
Never invent data. If no system message data, say "Stand by, running that now."

YOU ARE THE DISPATCHER ONLY. Never break character. Never acknowledge being AI."""

    def _get_ai_response(self, user_text: str) -> str:
        from core.plate_checker import is_plate_request, is_id_request, extract_plate

        extra_context = ""

        # ── Plate lookup ──────────────────────────────────────────────────────
        if is_plate_request(user_text):
            plate = extract_plate(user_text)
            if plate:
                logger.info(f"[PLATE] Running: {plate}")
                ack = f"10-4 {self.callsign}, running {plate}. Stand by."
                self._speak(ack)
                if self.on_dispatcher_speech:
                    self.on_dispatcher_speech(ack)
                data = self._plate_checker.query(plate)
                self._last_plate_data = data   # cache for follow-up ID check
                extra_context = self._plate_checker.format_for_gpt(data, plate)

        # ── Driver ID / 28 check — return the same person as the plate ────────
        elif is_id_request(user_text) and self._last_plate_data:
            data = self._last_plate_data
            owner = data.get("owner", "Unknown")
            dob   = data.get("dob", "Unknown")
            lic   = "valid" if data.get("license_valid", True) else "SUSPENDED"
            wanted = "ACTIVE WARRANT ON FILE" if data.get("wanted") else "no wants or warrants"
            logger.info(f"[ID] Returning cached owner: {owner}")
            ack = f"10-4 {self.callsign}, running the subject. Stand by."
            self._speak(ack)
            if self.on_dispatcher_speech:
                self.on_dispatcher_speech(ack)
            extra_context = (
                "ID CHECK DATA (read this back, do not add or change anything):\n"
                "Subject: " + owner + "\n"
                "DOB: " + dob + "\n"
                "Driver license: " + lic + "\n"
                "Status: " + wanted
            )

        # ── Build messages ────────────────────────────────────────────────────
        self._conversation.append({"role": "user", "content": user_text})
        messages = [{"role": "system", "content": self._system_prompt()}]
        if extra_context:
            messages.append({"role": "system", "content": extra_context})
        messages += self._conversation[-20:]

        try:
            resp = self._openai.chat.completions.create(
                model=self.config.get("gpt_model", "gpt-4o-mini"),
                messages=messages,
                max_tokens=250, temperature=0.60,
            )
            ai_text = resp.choices[0].message.content.strip()
            self._conversation.append({"role": "assistant", "content": ai_text})
            return ai_text
        except Exception as e:
            logger.error(f"GPT error: {e}")
            return f"Say again {self.callsign}?"

    # ── TTS + Radio FX ────────────────────────────────────────────────────────

    def _radio_click(self, release: bool = False):
        """
        Generate and play a realistic PTT click.
        key-up  (release=False): sharper, brighter — sounds like button press
        key-down (release=True): slightly lower, slower decay — button release
        """
        try:
            dur  = 0.11 if not release else 0.09
            t    = np.linspace(0, dur, int(dur * SAMPLE_RATE), endpoint=False)
            nyq  = SAMPLE_RATE / 2

            # Main click body — bandpass filtered noise burst
            noise = np.random.normal(0, 0.5, len(t)).astype(np.float32)
            lo = 380 / nyq;  hi = 3400 / nyq
            b, a = sp.butter(4, [lo, hi], btype="band")
            noise = sp.lfilter(b, a, noise).astype(np.float32)

            # Envelope: instant attack, exponential decay
            decay = 45 if not release else 28
            env   = np.exp(-t * decay).astype(np.float32)
            click = noise * env

            # Dispatch console has a slight low-mid character (~520 Hz)
            tone = np.sin(2 * np.pi * 520 * t).astype(np.float32) * env * 0.30
            click = np.clip((click + tone) * 0.72, -0.85, 0.85).astype(np.float32)

            sd.play(click, samplerate=SAMPLE_RATE, blocking=True)
        except Exception:
            pass

    def _squelch_click(self):
        """Dispatch key-up click (called before speech)."""
        self._radio_click(release=False)

    def _squelch_release(self):
        """Dispatch key-down click (called after speech ends)."""
        self._radio_click(release=True)

    # Sentinel — passed to _tts_fishaudio by _speak() so it uses the configured dispatch voice
    _DISPATCH_VOICE_SENTINEL = "__dispatch__"

    def _speak(self, text: str):
        """Dispatch voice (ALLE). Suppresses mic for full duration to prevent mic bleed."""
        intensity = float(self.config.get("radio_intensity", 0.82))
        self._mic_suppressed.set()
        try:
            mp3_bytes = self._tts_fishaudio(text, self._DISPATCH_VOICE_SENTINEL)
            if not mp3_bytes:
                return
            from pydub import AudioSegment
            audio = (AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
                     .set_channels(1).set_frame_rate(SAMPLE_RATE).set_sample_width(2))
            s  = np.array(audio.get_array_of_samples(), dtype=np.float32) / 32768.0
            fx = self._radio_fx(s, intensity)
            self._squelch_click()
            sd.play(fx, samplerate=SAMPLE_RATE, blocking=True)
            self._squelch_release()
        except Exception as e:
            logger.error(f"Speak: {e}")
        finally:
            time.sleep(0.45)
            self._flush_queue()
            self._mic_suppressed.clear()

    def _tts_with_voice(self, text: str, voice_id: str = None) -> bytes | None:
        """
        Used by RadioOfficerManager for officer voices.
        voice_id = None   → Fish Audio platform default (NOT ALLE — different voice)
        voice_id = "abc"  → specific Fish Audio reference voice
        """
        provider = self.config.get("tts_provider", "fishaudio").lower()
        if provider == "fishaudio":
            return self._tts_fishaudio(text, voice_id)   # None stays None
        return self._tts_elevenlabs(text)

    def _tts_fishaudio(self, text: str, voice_id: str = None) -> bytes | None:
        try:
            from fishaudio import FishAudio
            client = FishAudio(api_key=self.config["fishaudio_api_key"])
            # Sentinel → dispatch configured voice (ALLE)
            # Specific string → that exact voice
            # None → Fish Audio platform default (sounds different from ALLE)
            if voice_id == self._DISPATCH_VOICE_SENTINEL:
                ref_id = self.config.get("fishaudio_voice_id") or None
            else:
                ref_id = voice_id   # could be None (platform default) or a real ID
            return client.tts.convert(
                text=text,
                reference_id=ref_id,
                latency="balanced",
                format="mp3",
            )
        except Exception as e:
            logger.error(f"Fish Audio TTS: {e}"); return None

    def _tts_elevenlabs(self, text: str) -> bytes | None:
        try:
            vid = self.config.get("elevenlabs_voice_id", "21m00Tcm4TlvDq8ikWAM")
            resp = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
                headers={"xi-api-key": self.config["elevenlabs_api_key"],
                         "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_turbo_v2_5",
                      "voice_settings": {"stability": 0.50, "similarity_boost": 0.75,
                                         "style": 0.08, "use_speaker_boost": True}},
                timeout=15,
            )
            if resp.status_code != 200:
                logger.error(f"ElevenLabs {resp.status_code}: {resp.text[:200]}"); return None
            return resp.content
        except Exception as e:
            logger.error(f"ElevenLabs TTS: {e}"); return None

    def _radio_fx(self, samples: np.ndarray, intensity: float = 0.82) -> np.ndarray:
        """
        Police radio audio chain — clean, realistic processing.

        Real police radio sounds like a filtered telephone with light compression
        and subtle hiss. NOT heavily distorted or saturated.

          1. Bandpass  — 300-3200 Hz telephone voice band, 4th-order Butterworth.
                         4th-order has gentler rolloff than 6th — far less ringing
                         on already-compressed MP3 audio.
          2. Normalize — bring level to consistent headroom.
          3. Soft clip — very gentle tanh (drive 1.3), barely audible warmth.
          4. Noise     — subtle hiss floor (radio character, not static).
        """
        if intensity <= 0:
            return samples
        s   = samples.astype(np.float64)
        nyq = SAMPLE_RATE / 2

        # 1. Bandpass — 4th-order, telephone voice band
        b, a = sp.butter(4, [300 / nyq, 3200 / nyq], btype="band")
        s    = sp.lfilter(b, a, s)

        # 2. Normalize to consistent level
        peak = np.max(np.abs(s)) + 1e-9
        s    = s / peak * 0.80

        # 3. Very gentle soft limiter — just takes the edge off peaks
        drive = 1.3
        s     = np.tanh(s * drive) / np.tanh(np.array([drive]))[0] * 0.80

        # 4. Subtle noise floor — radio hiss, not static
        s += np.random.normal(0, 0.003 * intensity, len(s))

        return np.clip(s, -1.0, 1.0).astype(np.float32)

    # ── State ─────────────────────────────────────────────────────────────────

    def _set_state(self, state: str):
        self._state = state
        if self.on_state_change:
            label, color = self.STATES.get(state, ("?", "#666"))
            self.on_state_change(state, label, color)
