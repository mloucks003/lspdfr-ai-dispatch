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
import queue
import threading
import time
import wave

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

        self._state      = "idle"
        self._in_session = False   # True when channel is open
        self._running    = False
        self._stream     = None
        self._audio_q: queue.Queue = queue.Queue(maxsize=200)
        self._conversation: list   = []

        # Public callbacks — wired by dispatcher_main.py
        self.on_state_change      = None
        self.on_user_speech       = None
        self.on_dispatcher_speech = None
        self.on_error             = None

        from openai import OpenAI
        self._openai   = OpenAI(api_key=config["openai_api_key"])
        self._vosk_rec = self._load_vosk()

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
        # Single dedicated thread owns all audio consumption
        threading.Thread(target=self._main_loop, daemon=True,
                         name="dispatcher").start()
        logger.info(f"AIDispatcher started — listening for '{self.callsign}'")

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()

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
        self._vosk_rec.AcceptWaveform(chunk.tobytes())
        partial = json.loads(self._vosk_rec.PartialResult()).get("partial", "")
        if partial and any(v in partial.lower() for v in self._variants):
            self._vosk_rec.Result()  # reset
            self._set_state("acknowledging")
            # Hand off to session — runs in main_loop thread inline
            self._run_session()

    # ── Session — full conversation loop ──────────────────────────────────────

    def _run_session(self):
        """
        Opens a radio channel. Acknowledges, then loops:
          listen → process → respond → listen → ...
        until SESSION_TIMEOUT seconds of silence, then returns to idle.
        """
        self._in_session = True
        try:
            # Opening acknowledgment
            ack = f"{self.callsign}, go ahead."
            self._speak(ack)
            if self.on_dispatcher_speech:
                self.on_dispatcher_speech(ack)

            while self._running:
                # Pause + flush after speaking so mic doesn't catch playback
                time.sleep(0.35)
                self._flush_queue()

                self._set_state("session_wait")
                audio = self._wait_for_speech_then_record()

                if audio is None:
                    logger.info("Session timed out — returning to idle")
                    break

                self._set_state("processing")
                text = self._transcribe(audio)
                logger.info(f"[{self.callsign}]: {text!r}")

                if not text or len(text.strip()) < 3:
                    reply = f"Say again {self.callsign}?"
                    self._set_state("responding")
                    if self.on_dispatcher_speech:
                        self.on_dispatcher_speech(reply)
                    self._speak(reply)
                    continue

                if self.on_user_speech:
                    self.on_user_speech(text)

                ai_text = self._get_ai_response(text)
                logger.info(f"[DISPATCH]: {ai_text!r}")

                self._set_state("responding")
                if self.on_dispatcher_speech:
                    self.on_dispatcher_speech(ai_text)
                self._speak(ai_text)

                # Close session if officer signed off
                if self._is_closing_transmission(text):
                    logger.info("Officer went clear — closing session")
                    break

        except Exception as e:
            logger.error(f"Session error: {e}")
            if self.on_error:
                self.on_error(str(e))
        finally:
            self._in_session = False
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
        MIN_ONSET  = 2          # consecutive loud chunks needed to confirm speech
        PRE_ROLL   = 4          # chunks to prepend before onset (avoids clipped starts)

        pre_buf       = []      # rolling window before speech starts
        onset_count   = 0
        buffer        = []
        speech_heard  = False
        silent_chunks = 0
        timeout_count = 0

        while self._running:
            try:
                chunk = self._audio_q.get(timeout=0.5)
            except queue.Empty:
                if not self._running:
                    return None
                continue

            rms = int(np.sqrt(np.mean(chunk.astype(np.float32) ** 2)))

            if not speech_heard:
                pre_buf.append(chunk)
                if len(pre_buf) > PRE_ROLL:
                    pre_buf.pop(0)

                if rms >= self._speech_thresh:
                    onset_count += 1
                    if onset_count >= MIN_ONSET:
                        # Confirmed speech — prepend pre-roll
                        speech_heard = True
                        buffer = list(pre_buf)
                        self._set_state("listening")
                else:
                    onset_count = 0
                    timeout_count += 1
                    if timeout_count >= self._session_timeout_chunks:
                        return None   # timed out — close session
            else:
                buffer.append(chunk)
                if rms >= self._silence_thresh:
                    silent_chunks = 0
                else:
                    silent_chunks += 1
                    if silent_chunks >= self._silence_end_chunks:
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
        cs = self.callsign
        return f"""You are a police radio dispatcher for {self.agency}. \
You are talking to unit {cs} over the radio.

VOICE AND TONE:
You are calm, clipped, and professional. Real dispatchers do not have warm personalities \
on the radio — they are efficient and precise. No "stay safe", no "always here for you", \
no emotional language. Short sentences. Radio cadence.

RESPONSE LENGTH:
1 to 2 sentences maximum. Under 20 words preferred. Never more than 35 words.

10-CODES TO USE NATURALLY:
10-4 (copy/acknowledged), 10-8 (in service/available), 10-23 (arrived on scene), \
10-38 (traffic stop), 10-33 (emergency/officer needs help), 10-78 (need assistance), \
10-22 (disregard), 10-20 (location), 10-29 (check for wants/warrants).

PLATE AND NAME RUNS — CRITICAL RULE:
NEVER output brackets, placeholders, or template text like [PLATE], [YEAR], [COLOR].
ALWAYS generate completely fictional but realistic data.

When {cs} gives you a plate or name to run, respond like this real example:
"10-4 {cs}, running Adam-Charlie-7. Stand by... Adam-Charlie-7 comes back to a \
2017 silver Toyota Camry, registered to Marcus T. Webb of 4421 Innocence Boulevard, \
Los Santos. Registration valid, insurance valid. No wants or warrants. \
Anything further, {cs}?"

Randomize results: 75% clean, 15% minor issue (expired reg or lapsed insurance), \
10% warrant on file or vehicle reported stolen. Generate real-sounding names, \
addresses, years, colors, makes, models every time.

COMMON RESPONSES:
- Traffic stop: "Copy {cs}, showing you 10-38 at [location they gave or 'your location']."
- On scene / arrived / 10-23: "Copy {cs}, showing you 10-23."
- Backup / 10-33: "All units, 10-33 at {cs}'s location. Respond code 3."
- Pursuit: "Copy {cs}, broadcasting pursuit. Air support notified. Spike strips authorized."
- Shots fired: "Copy {cs}. EMS and supervisors en route. Additional units responding."
- Code 4 / going clear / 10-8: "Copy {cs}, return to service." (nothing more)
- Can't understand: "Say again {cs}?"
- Non-police statements or random words: respond only "10-4." and nothing else.

YOU ARE THE DISPATCHER. Never break character. Never acknowledge being an AI."""

    def _get_ai_response(self, user_text: str) -> str:
        self._conversation.append({"role": "user", "content": user_text})
        history = self._conversation[-20:]
        try:
            resp = self._openai.chat.completions.create(
                model=self.config.get("gpt_model", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    *history,
                ],
                max_tokens=250,
                temperature=0.72,
            )
            ai_text = resp.choices[0].message.content.strip()
            self._conversation.append({"role": "assistant", "content": ai_text})
            return ai_text
        except Exception as e:
            logger.error(f"GPT error: {e}")
            return f"Say again {self.callsign}?"

    # ── TTS + Radio FX ────────────────────────────────────────────────────────

    def _speak(self, text: str):
        """ElevenLabs TTS → radio FX → play (blocking)."""
        vid       = self.config.get("elevenlabs_voice_id", "21m00Tcm4TlvDq8ikWAM")
        api_key   = self.config["elevenlabs_api_key"]
        intensity = float(self.config.get("radio_intensity", 0.82))
        try:
            resp = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
                headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_turbo_v2_5",
                      "voice_settings": {"stability": 0.50, "similarity_boost": 0.75,
                                         "style": 0.08, "use_speaker_boost": True}},
                timeout=15,
            )
            if resp.status_code != 200:
                logger.error(f"ElevenLabs {resp.status_code}: {resp.text[:200]}"); return
            from pydub import AudioSegment
            audio = (AudioSegment.from_mp3(io.BytesIO(resp.content))
                     .set_channels(1).set_frame_rate(SAMPLE_RATE).set_sample_width(2))
            s = np.array(audio.get_array_of_samples(), dtype=np.float32) / 32768.0
            sd.play(self._radio_fx(s, intensity), samplerate=SAMPLE_RATE, blocking=True)
        except Exception as e:
            logger.error(f"Speak: {e}")

    def _radio_fx(self, samples: np.ndarray, intensity: float) -> np.ndarray:
        """Bandpass filter + soft clip distortion + static noise."""
        if intensity <= 0:
            return samples
        nyq = SAMPLE_RATE / 2
        b, a = sp.butter(4, [300 / nyq, 3400 / nyq], btype="band")
        samples = sp.lfilter(b, a, samples)
        thresh = 0.55
        samples = np.where(
            np.abs(samples) > thresh,
            np.sign(samples) * (thresh + (np.abs(samples) - thresh) * 0.25),
            samples,
        )
        samples += np.random.normal(0, 0.005 * intensity, len(samples))
        return np.clip(samples, -1.0, 1.0).astype(np.float32)

    # ── State ─────────────────────────────────────────────────────────────────

    def _set_state(self, state: str):
        self._state = state
        if self.on_state_change:
            label, color = self.STATES.get(state, ("?", "#666"))
            self.on_state_change(state, label, color)
