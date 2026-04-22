"""
audio_fx.py — Shared audio processing for BlueLineDispatchPro.

Provides PTT click generation and the radio FX chain.
Imported by ai_dispatcher.py (dispatch voice) AND radio_officers.py (officer
voices) so EVERY transmission — dispatch, officers, background chatter —
goes through an identical signal path and sounds like the same radio.

PTT integration pattern (used in both _speak and _speak_as_officer):
    open_click = generate_ptt_open(SAMPLE_RATE)
    close_tone = generate_ptt_close(SAMPLE_RATE)
    gap        = np.zeros(int(0.018 * SAMPLE_RATE), dtype=np.float32)
    full       = np.concatenate([open_click, gap, speech, gap, close_tone])
    fx         = radio_fx(full, intensity, SAMPLE_RATE)
    sd.play(fx, samplerate=SAMPLE_RATE, blocking=True)
Concatenating into a single buffer guarantees gapless playback and applies
the same bandpass / saturation to the clicks as to the voice.
"""

import numpy as np
from scipy import signal as sp

SAMPLE_RATE = 16000


def generate_ptt_open(sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """
    PTT key-up click: the hard squelch-break at the START of every transmission.

    Character: 800-1200 Hz bandpass noise burst — sounds like a relay closing.
    Shape:     2 ms sharp attack → 8 ms hold → 5 ms decay  (~15 ms total)
    Volume:    60 % of full scale — present and clear, not harsh.
    """
    dur   = 0.015
    n     = int(dur * sample_rate)
    t     = np.linspace(0, dur, n, endpoint=False)
    nyq   = sample_rate / 2

    noise = np.random.default_rng().standard_normal(n).astype(np.float32)
    b, a  = sp.butter(4, [800 / nyq, 1200 / nyq], btype="band")
    noise = sp.lfilter(b, a, noise).astype(np.float32)

    attack  = int(0.002 * sample_rate)
    decay   = int(0.005 * sample_rate)
    hold    = max(n - attack - decay, 1)
    env     = np.concatenate([
        np.linspace(0.0, 1.0, attack),
        np.ones(hold),
        np.linspace(1.0, 0.0, decay),
    ])[:n].astype(np.float32)

    return np.clip(noise * env * 0.60, -1.0, 1.0).astype(np.float32)


def generate_ptt_close(sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """
    PTT key-down tail tone: the short "bwip" at the END of every transmission.

    Character: 1800 Hz sine — the relay releasing.
    Shape:     5 ms fade-in → 20 ms hold → 15 ms fade-out  (~40 ms total)
    Volume:    60 % of full scale.
    """
    dur  = 0.040
    n    = int(dur * sample_rate)
    t    = np.linspace(0, dur, n, endpoint=False)
    tone = np.sin(2 * np.pi * 1800 * t).astype(np.float32)

    fade_in  = int(0.005 * sample_rate)
    fade_out = int(0.015 * sample_rate)
    hold     = max(n - fade_in - fade_out, 1)
    env      = np.concatenate([
        np.linspace(0.0, 1.0, fade_in),
        np.ones(hold),
        np.linspace(1.0, 0.0, fade_out),
    ])[:n].astype(np.float32)

    return np.clip(tone * env * 0.60, -1.0, 1.0).astype(np.float32)


def radio_fx(samples: np.ndarray, intensity: float = 0.82,
             sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """
    Police radio audio chain — applied to the full concatenated buffer
    (PTT open + speech + PTT close) so clicks and voice sound identical.

    Real police radio = filtered telephone + light compression + subtle hiss.

      1. Bandpass   300-3200 Hz, 4th-order Butterworth.
                    4th-order is gentler than 6th — no ringing on MP3 audio.
      2. Normalize  consistent level before soft-limiting.
      3. Soft-clip  tanh drive=1.3 — barely audible warmth, no harshness.
      4. Hiss       subtle noise floor, scales with intensity slider.
    """
    if intensity <= 0:
        return samples.astype(np.float32)

    s   = samples.astype(np.float64)
    nyq = sample_rate / 2

    b, a = sp.butter(4, [300 / nyq, 3200 / nyq], btype="band")
    s    = sp.lfilter(b, a, s)

    peak = np.max(np.abs(s)) + 1e-9
    s    = s / peak * 0.80

    drive = 1.3
    s     = np.tanh(s * drive) / float(np.tanh(np.array([drive]))[0]) * 0.80

    s += np.random.normal(0, 0.003 * intensity, len(s))

    return np.clip(s, -1.0, 1.0).astype(np.float32)
