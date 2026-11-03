"""audiokit.py -- InkPixel numpy-only audio toolkit (binding surface: ASSET_SPEC.md section 8).

    import audiokit as ak
    x = ak.apply_env(ak.osc_pulse(ak.note_freq("A4"), 0.3, duty=0.25), ak.env_decay(ak.samples(0.3), 0.08))
    ak.save_sfx("/path/Audio/Sfx/Accept.wav", x)

Conventions (spec section 6):
  * Sample rate SR = 44100 everywhere. Signals are float64 numpy arrays in -1..1: mono `(n,)`
    or stereo `(n, 2)`. Every function accepts both unless stated otherwise.
  * SFX  -> `<audio_root>/Sfx/<Name>.wav`  PascalCase, mono, 16-bit, peak -1 dBFS, no DC,
    <= 2.0 s, trimmed (no leading silence), 2 ms fades.  Use `finalize_sfx` / `save_sfx`.
  * Music -> `<audio_root>/Music/<Name>.ogg` PascalCase, stereo, OGG Vorbis q6, seamless
    loops of exactly round(bars*beats_per_bar*60/bpm*SR) samples.  Use `Sequencer` +
    `render_loop_safe` + `save_music`.  WAV masters belong in the build's tmp_dir only.
  * Everything is deterministic: noise uses either an explicit `seed` or the module RNG, which
    `seed(n)` resets (build_all reseeds before every generator; call `ak.seed(...)` yourself at
    the top of `build()` if you want independence from other generators). Instruments derive
    their own noise seeds from (freq, dur, vel), so a note sounds the same wherever it is used.

Instruments are callables `(freq, dur, vel=1.0) -> mono array` (they may return a longer array
than `dur` seconds: the natural release/ring).  Unpitched hits (`taiko`, `gong`, `wood_block`,
`shaker`, drums) are plain functions with their own arguments; wrap them with
`instrument(fn, **fixed)` to use them in a `Sequencer` track (the Sequencer does this for you).
"""
from __future__ import annotations

import inspect
import json
import math
import os
import re
import shutil
import struct
import subprocess
import tempfile
import wave
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np

__all__ = [
    # constants / helpers
    "SR", "SFX_PEAK_DB", "MUSIC_PEAK_DB", "SFX_MAX_SECONDS", "seed", "samples", "seconds",
    "time_axis", "db_to_amp", "amp_to_db", "is_stereo", "to_stereo", "to_mono", "widen",
    # oscillators / noise
    "osc_pulse", "osc_square", "osc_tri", "osc_saw", "osc_sine", "noise", "nes_noise",
    "additive", "freq_curve", "sweep", "vibrato", "portamento", "arpeggio",
    # envelopes
    "env_adsr", "env_decay", "env_points", "apply_env", "env_note",
    # filters / effects
    "lowpass", "highpass", "lowpass_var", "biquad_lowpass", "biquad_highpass",
    "biquad_bandpass", "fft_convolve", "bitcrush", "delay", "echo", "reverb", "soft_clip",
    "clip", "remove_dc", "normalize", "trim_silence", "fade", "pad", "pad_to", "mix", "concat",
    "resample_len",
    # music theory
    "NOTE_NAMES", "PENTATONIC_MODES", "CHORD_QUALITIES", "note_to_midi", "midi_to_note",
    "note_freq", "midi_to_freq", "freq_to_midi", "transpose", "scale", "pentatonic", "chord",
    "to_freq",
    # sequencing
    "Sequencer", "parse_pattern", "bar", "shift_pattern", "repeat_pattern", "merge_patterns",
    "transpose_pattern", "pattern_length", "instrument",
    # instruments
    "nes_lead", "nes_bass_tri", "nes_noise_drum", "pluck", "pad", "bell", "zither", "flute",
    "erhu", "taiko", "gong", "temple_bell", "wood_block", "shaker", "INSTRUMENTS",
    # i/o + spec helpers
    "write_wav", "read_wav", "write_ogg", "read_ogg", "ffprobe_info", "measure", "finalize_sfx",
    "save_sfx", "save_music", "sfx_path", "music_path", "is_pascal_case", "check_sfx",
    "check_music", "loop_samples",
]

SR = 44100
SFX_PEAK_DB = -1.0
MUSIC_PEAK_DB = -1.5          # headroom for Vorbis overshoot so decoded peak stays <= -1 dBFS
SFX_MAX_SECONDS = 2.0
_PASCAL_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")

Signal = np.ndarray
FreqLike = Union[float, int, np.ndarray, Sequence[float]]

# ------------------------------------------------------------------------------------------
# Randomness (deterministic)
# ------------------------------------------------------------------------------------------
_RNG = np.random.default_rng(0)


def seed(n: int = 0) -> None:
    """Reset the module random generator (used by `noise()` when no seed is given)."""
    global _RNG
    _RNG = np.random.default_rng(int(n))


def _rng(seed_value: Optional[int]) -> np.random.Generator:
    if seed_value is None:
        return _RNG
    return np.random.default_rng(int(seed_value) & 0xFFFFFFFF)


def _hash_seed(*parts) -> int:
    """Stable small-int seed from numbers/strings (no Python hash randomisation)."""
    h = 2166136261
    for p in parts:
        if isinstance(p, float):
            p = round(p, 4)
        for ch in str(p).encode("utf-8"):
            h ^= ch
            h = (h * 16777619) & 0xFFFFFFFF
    return h


# ------------------------------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------------------------------
def samples(dur: float, sr: int = SR) -> int:
    """Seconds -> sample count (rounded)."""
    return int(round(float(dur) * sr))


def seconds(n: int, sr: int = SR) -> float:
    return float(n) / sr


def time_axis(dur_or_n: Union[float, int], sr: int = SR) -> np.ndarray:
    """Time vector in seconds; argument is seconds (float) or a sample count (int)."""
    n = dur_or_n if isinstance(dur_or_n, (int, np.integer)) else samples(dur_or_n, sr)
    return np.arange(int(n), dtype=np.float64) / sr


def db_to_amp(db: float) -> float:
    return float(10.0 ** (db / 20.0))


def amp_to_db(amp: float) -> float:
    amp = float(amp)
    return -200.0 if amp <= 0.0 else float(20.0 * math.log10(amp))


def is_stereo(x: Signal) -> bool:
    return x.ndim == 2


def _as_signal(x) -> np.ndarray:
    a = np.asarray(x, dtype=np.float64)
    if a.ndim == 0:
        a = a.reshape(1)
    if a.ndim == 2 and a.shape[1] == 1:
        a = a[:, 0]
    if a.ndim > 2 or (a.ndim == 2 and a.shape[1] != 2):
        raise ValueError("signal must be mono (n,) or stereo (n,2); got shape %r" % (a.shape,))
    return a


def to_stereo(x: Signal, pan: float = 0.0) -> np.ndarray:
    """Mono -> stereo with constant-power panning (pan -1 = left .. +1 = right).
    A stereo input gets a balance adjustment instead."""
    x = _as_signal(x)
    pan = float(np.clip(pan, -1.0, 1.0))
    theta = (pan + 1.0) * 0.25 * math.pi
    gl, gr = math.cos(theta), math.sin(theta)
    if x.ndim == 1:
        out = np.empty((len(x), 2), dtype=np.float64)
        out[:, 0] = x * gl
        out[:, 1] = x * gr
        return out
    out = x.copy()
    out[:, 0] *= gl * math.sqrt(2.0)
    out[:, 1] *= gr * math.sqrt(2.0)
    return out


def to_mono(x: Signal) -> np.ndarray:
    x = _as_signal(x)
    return x if x.ndim == 1 else x.mean(axis=1)


def widen(x: Signal, ms: float = 10.0, amount: float = 0.5, sr: int = SR) -> np.ndarray:
    """Cheap stereo widening (Haas): the right channel gets a slightly delayed copy of the
    left mixed in, `amount` 0..1."""
    x = _as_signal(x)
    x = to_stereo(x) if x.ndim == 1 else x.copy()
    d = max(1, samples(ms / 1000.0, sr))
    delayed = np.zeros(len(x))
    delayed[d:] = x[:-d, 0]
    a = float(np.clip(amount, 0.0, 1.0))
    x[:, 1] = x[:, 1] * (1.0 - 0.5 * a) + delayed * 0.5 * a
    return x


def _channel_map(fn: Callable[[np.ndarray], np.ndarray], x: np.ndarray) -> np.ndarray:
    """Apply a mono function to each channel of a stereo signal."""
    x = _as_signal(x)
    if x.ndim == 1:
        return fn(x)
    l, r = fn(x[:, 0]), fn(x[:, 1])
    n = min(len(l), len(r))
    return np.stack([l[:n], r[:n]], axis=1)


def resample_len(curve: np.ndarray, n: int) -> np.ndarray:
    """Stretch/shrink a 1-D curve to exactly n points by linear interpolation."""
    curve = np.asarray(curve, dtype=np.float64)
    if len(curve) == n:
        return curve
    if len(curve) == 0:
        return np.zeros(n)
    if len(curve) == 1 or n == 1:
        return np.full(n, float(curve[0]))
    src = np.linspace(0.0, 1.0, len(curve))
    dst = np.linspace(0.0, 1.0, n)
    return np.interp(dst, src, curve)


# ------------------------------------------------------------------------------------------
# Oscillators (freq may be a scalar or a frequency curve array)
# ------------------------------------------------------------------------------------------
def _freq_and_n(freq: FreqLike, dur: Optional[float], sr: int) -> Tuple[np.ndarray, int]:
    if np.isscalar(freq):
        if dur is None:
            raise ValueError("dur is required when freq is a scalar")
        n = samples(dur, sr)
        return np.full(n, float(freq)), n
    f = np.asarray(freq, dtype=np.float64).reshape(-1)
    n = len(f) if dur is None else samples(dur, sr)
    return resample_len(f, n), n


def _phase(freq: FreqLike, dur: Optional[float], sr: int, phase: float = 0.0) -> Tuple[np.ndarray, np.ndarray]:
    """Return (phase in cycles [0..), per-sample frequency)."""
    f, n = _freq_and_n(freq, dur, sr)
    if n == 0:
        return np.zeros(0), f
    inc = f / sr
    ph = phase + np.cumsum(inc) - inc           # phase at sample 0 == `phase`
    return ph, f


def _polyblep(t: np.ndarray, dt: np.ndarray) -> np.ndarray:
    """Polynomial band-limited step correction for discontinuities at t == 0 (t in 0..1)."""
    out = np.zeros_like(t)
    dt = np.maximum(dt, 1e-9)
    m = t < dt
    tt = t[m] / dt[m]
    out[m] = tt + tt - tt * tt - 1.0
    m2 = t > 1.0 - dt
    tt = (t[m2] - 1.0) / dt[m2]
    out[m2] = tt * tt + tt + tt + 1.0
    return out


def osc_sine(freq: FreqLike, dur: Optional[float] = None, sr: int = SR, phase: float = 0.0) -> np.ndarray:
    ph, _ = _phase(freq, dur, sr, phase)
    return np.sin(2.0 * math.pi * ph)


def osc_tri(freq: FreqLike, dur: Optional[float] = None, sr: int = SR, phase: float = 0.0) -> np.ndarray:
    """Triangle starting at 0 and rising."""
    ph, _ = _phase(freq, dur, sr, phase)
    frac = np.mod(ph + 0.25, 1.0)
    return 1.0 - 4.0 * np.abs(frac - 0.5)


def osc_saw(freq: FreqLike, dur: Optional[float] = None, sr: int = SR, phase: float = 0.0,
            blep: bool = True) -> np.ndarray:
    """Rising sawtooth (starts at 0). `blep=False` gives the raw aliasing chip version."""
    ph, f = _phase(freq, dur, sr, phase)
    frac = np.mod(ph + 0.5, 1.0)
    y = 2.0 * frac - 1.0
    if blep and len(y):
        y -= _polyblep(frac, np.abs(f) / sr)
    return y


def osc_pulse(freq: FreqLike, dur: Optional[float] = None, duty: float = 0.5, sr: int = SR,
              phase: float = 0.0, blep: bool = True) -> np.ndarray:
    """Pulse wave with the given duty cycle (0.125 / 0.25 / 0.5 for NES flavours)."""
    ph, f = _phase(freq, dur, sr, phase)
    duty = float(np.clip(duty, 0.01, 0.99))
    frac = np.mod(ph, 1.0)
    y = np.where(frac < duty, 1.0, -1.0)
    if blep and len(y):
        dt = np.abs(f) / sr
        y += _polyblep(frac, dt)
        y -= _polyblep(np.mod(frac + 1.0 - duty, 1.0), dt)
    return y


def osc_square(freq: FreqLike, dur: Optional[float] = None, sr: int = SR, phase: float = 0.0,
               blep: bool = True) -> np.ndarray:
    return osc_pulse(freq, dur, 0.5, sr, phase, blep)


_WAVES = {
    "pulse": lambda f, d, duty, sr: osc_pulse(f, d, duty, sr),
    "square": lambda f, d, duty, sr: osc_pulse(f, d, 0.5, sr),
    "tri": lambda f, d, duty, sr: osc_tri(f, d, sr),
    "triangle": lambda f, d, duty, sr: osc_tri(f, d, sr),
    "saw": lambda f, d, duty, sr: osc_saw(f, d, sr),
    "sine": lambda f, d, duty, sr: osc_sine(f, d, sr),
    "sin": lambda f, d, duty, sr: osc_sine(f, d, sr),
}


def _osc(wave: str, freq: FreqLike, dur: Optional[float], duty: float, sr: int) -> np.ndarray:
    try:
        return _WAVES[wave](freq, dur, duty, sr)
    except KeyError:
        raise ValueError("unknown wave %r (pulse, square, tri, saw, sine)" % wave)


def additive(freq: FreqLike, dur: float, partials: Sequence[Tuple[float, float, float]],
             sr: int = SR, seed_value: Optional[int] = None) -> np.ndarray:
    """Sum of sine partials: each (ratio, amplitude, decay_tau_seconds); tau <= 0 = no decay."""
    f, n = _freq_and_n(freq, dur, sr)
    t = np.arange(n) / sr
    out = np.zeros(n)
    for ratio, amp, tau in partials:
        y = osc_sine(f * ratio, None, sr) * amp
        if tau and tau > 0:
            y *= np.exp(-t / tau)
        out += y
    return out


# ------------------------------------------------------------------------------------------
# Noise
# ------------------------------------------------------------------------------------------
def noise(dur: float, color: str = "white", sr: int = SR, seed: Optional[int] = None) -> np.ndarray:
    """White / pink (1/f) / brown (1/f^2) noise, peak-normalised to 1."""
    n = samples(dur, sr)
    if n <= 0:
        return np.zeros(0)
    w = _rng(seed).uniform(-1.0, 1.0, n)
    color = color.lower()
    if color == "white":
        y = w
    elif color in ("pink", "brown", "red"):
        spec = np.fft.rfft(w)
        freqs = np.fft.rfftfreq(n, 1.0 / sr)
        gain = np.zeros_like(freqs)
        nz = freqs > 0
        gain[nz] = 1.0 / np.sqrt(freqs[nz]) if color == "pink" else 1.0 / freqs[nz]
        y = np.fft.irfft(spec * gain, n)
        y = y - np.mean(y)
    else:
        raise ValueError("noise color must be white, pink or brown")
    peak = np.max(np.abs(y))
    return y / peak if peak > 0 else y


_LFSR_CACHE: Dict[str, np.ndarray] = {}
NES_NOISE_PERIODS = (4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068)
NES_CPU_HZ = 1789773.0


def _lfsr_sequence(mode: str) -> np.ndarray:
    if mode in _LFSR_CACHE:
        return _LFSR_CACHE[mode]
    tap = 6 if mode == "short" else 1
    state = 1
    out = []
    seen = {}
    while state not in seen:
        seen[state] = len(out)
        out.append(-1.0 if (state & 1) else 1.0)   # NES mutes when bit 0 is set
        fb = (state & 1) ^ ((state >> tap) & 1)
        state = (state >> 1) | (fb << 14)
    seq = np.array(out[seen[state]:], dtype=np.float64)
    _LFSR_CACHE[mode] = seq
    return seq


def nes_noise(dur: float, rate_hz: Optional[float] = None, mode: str = "long",
              period: Optional[int] = None, sr: int = SR) -> np.ndarray:
    """NES APU style LFSR noise (+-1).  `period` = 0..15 index into the NES period table,
    or `rate_hz` = shift-register clock; default clocks every output sample.
    mode 'long' (32767-step) or 'short' (93-step metallic buzz)."""
    n = samples(dur, sr)
    if period is not None:
        rate_hz = NES_CPU_HZ / NES_NOISE_PERIODS[int(np.clip(period, 0, 15))]
    if rate_hz is None:
        rate_hz = float(sr)
    seq = _lfsr_sequence("short" if mode == "short" else "long")
    steps = np.floor(np.arange(n) * (float(rate_hz) / sr)).astype(np.int64)
    return seq[steps % len(seq)]


# ------------------------------------------------------------------------------------------
# Frequency curves: sweeps, vibrato, portamento, arpeggio
# ------------------------------------------------------------------------------------------
def freq_curve(f0: float, f1: float, dur: float, curve: str = "exp", sr: int = SR) -> np.ndarray:
    """Frequency curve from f0 to f1 over dur seconds ('exp' = constant cents/sec, 'lin')."""
    n = samples(dur, sr)
    if n <= 0:
        return np.zeros(0)
    u = np.linspace(0.0, 1.0, n, endpoint=False) if n > 1 else np.zeros(1)
    if curve == "exp" and f0 > 0 and f1 > 0:
        return f0 * (f1 / f0) ** u
    if curve == "exp":
        raise ValueError("exp curve needs positive frequencies")
    return f0 + (f1 - f0) * u


def sweep(f0: float, f1: float, dur: float, wave: str = "pulse", duty: float = 0.5,
          curve: str = "exp", sr: int = SR) -> np.ndarray:
    """Pitch sweep rendered with the given waveform ('pulse','square','tri','saw','sine')."""
    return _osc(wave, freq_curve(f0, f1, dur, curve, sr), None, duty, sr)


def vibrato(freq: FreqLike, dur: Optional[float], rate: float = 5.5, depth: float = 0.3,
            sr: int = SR, onset: float = 0.0, ramp: float = 0.15, unit: str = "semitones",
            shape: str = "sine") -> np.ndarray:
    """Frequency curve with vibrato.  `freq` scalar or curve; `depth` in semitones (default),
    'cents', 'hz' or 'ratio'.  Vibrato is silent until `onset` seconds then fades in over `ramp`."""
    f, n = _freq_and_n(freq, dur, sr)
    if n == 0:
        return f
    t = np.arange(n) / sr
    lfo = np.sin(2.0 * math.pi * rate * t) if shape == "sine" else osc_tri(rate, n / sr, sr)
    env = np.clip((t - onset) / max(ramp, 1e-6), 0.0, 1.0) if (onset > 0 or ramp > 0) else np.ones(n)
    lfo = lfo * env
    if unit == "semitones":
        return f * 2.0 ** (depth * lfo / 12.0)
    if unit == "cents":
        return f * 2.0 ** (depth * lfo / 1200.0)
    if unit == "hz":
        return f + depth * lfo
    if unit == "ratio":
        return f * (1.0 + depth * lfo)
    raise ValueError("unit must be semitones, cents, hz or ratio")


def portamento(f0: float, f1: float, dur: float, glide: float = 0.08, curve: str = "exp",
               sr: int = SR) -> np.ndarray:
    """Frequency curve gliding from f0 to f1 over `glide` seconds then holding f1."""
    n = samples(dur, sr)
    ng = min(n, samples(glide, sr))
    out = np.full(n, float(f1))
    if ng > 0:
        out[:ng] = freq_curve(f0, f1, ng / sr, curve, sr)[:ng]
    return out


def arpeggio(notes: Sequence[Union[str, float]], dur: float, rate: float = 30.0,
             sr: int = SR) -> np.ndarray:
    """Chiptune arpeggio: frequency curve cycling through `notes` `rate` times per second."""
    freqs = np.array([to_freq(nn) for nn in notes], dtype=np.float64)
    n = samples(dur, sr)
    idx = np.floor(np.arange(n) * (rate / sr)).astype(np.int64) % len(freqs)
    return freqs[idx]


# ------------------------------------------------------------------------------------------
# Envelopes
# ------------------------------------------------------------------------------------------
def _seg_shape(n: int, v0: float, v1: float, curve: str) -> np.ndarray:
    if n <= 0:
        return np.zeros(0)
    u = np.linspace(0.0, 1.0, n, endpoint=False)
    if curve == "exp":
        k = 5.0
        u = (1.0 - np.exp(-k * u)) / (1.0 - math.exp(-k))
    return v0 + (v1 - v0) * u


def env_adsr(n: int, a: float, d: float, s: float, r: float, sr: int = SR,
             curve: str = "lin") -> np.ndarray:
    """ADSR envelope of exactly n samples: attack/decay/release in seconds, sustain level 0..1.
    The sustain segment fills whatever remains; if n is too short the segments are scaled down.
    curve 'lin' or 'exp' (exponential-feel decay/release)."""
    n = int(n)
    if n <= 0:
        return np.zeros(0)
    na, nd, nr = samples(a, sr), samples(d, sr), samples(r, sr)
    total = na + nd + nr
    if total > n:
        k = n / total
        na, nd = int(na * k), int(nd * k)
        nr = n - na - nd
    ns = n - na - nd - nr
    att = np.linspace(0.0, 1.0, na, endpoint=False) if na > 0 else np.zeros(0)
    dec = _seg_shape(nd, 1.0, s, curve)
    sus = np.full(ns, float(s))
    rel = _seg_shape(nr, s if (nd or ns) else 1.0, 0.0, curve)
    env = np.concatenate([att, dec, sus, rel])
    return env[:n]


def env_decay(n: int, tau: float, sr: int = SR) -> np.ndarray:
    """Exponential decay exp(-t/tau) of n samples."""
    t = np.arange(int(n)) / sr
    return np.exp(-t / max(float(tau), 1e-9))


def env_points(points: Sequence[Tuple[float, float]], n: Optional[int] = None,
               sr: int = SR) -> np.ndarray:
    """Breakpoint envelope from (time_s, value) pairs, linearly interpolated; n defaults to
    the last point's time."""
    pts = sorted((float(t), float(v)) for t, v in points)
    if not pts:
        return np.zeros(n or 0)
    if n is None:
        n = samples(pts[-1][0], sr)
    t = np.arange(int(n)) / sr
    return np.interp(t, [p[0] for p in pts], [p[1] for p in pts])


def env_note(dur: float, a: float, d: float, s: float, r: float, sr: int = SR,
             curve: str = "exp") -> np.ndarray:
    """ADSR for a note held `dur` seconds: sustain lasts until `dur`, release follows after it.
    Length = samples(dur) + samples(r)."""
    nd = samples(dur, sr)
    nr = samples(r, sr)
    return env_adsr(nd + nr, a, d, s, r, sr, curve)


def apply_env(x: Signal, env: np.ndarray) -> np.ndarray:
    """Multiply by an envelope (env truncated / zero-padded to the signal length)."""
    x = _as_signal(x)
    env = np.asarray(env, dtype=np.float64).reshape(-1)
    n = len(x)
    if len(env) < n:
        env = np.concatenate([env, np.zeros(n - len(env))])
    env = env[:n]
    return x * env if x.ndim == 1 else x * env[:, None]


# ------------------------------------------------------------------------------------------
# Filters (numpy only: IIR filters are rendered as truncated impulse responses + FFT convolve)
# ------------------------------------------------------------------------------------------
def fft_convolve(x: Signal, h: np.ndarray, full: bool = False) -> np.ndarray:
    """Linear convolution via FFT.  Returns len(x) samples (or len(x)+len(h)-1 with full)."""
    x = _as_signal(x)
    h = np.asarray(h, dtype=np.float64).reshape(-1)
    if x.ndim == 2:
        return _channel_map(lambda c: fft_convolve(c, h, full), x)
    n, m = len(x), len(h)
    if n == 0 or m == 0:
        return np.zeros(n + m - 1 if full else n)
    size = 1 << int(math.ceil(math.log2(n + m - 1)))
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(h, size), size)[: n + m - 1]
    return y if full else y[:n]


_IIR_CACHE: Dict[tuple, np.ndarray] = {}


def _iir_impulse(b: Sequence[float], a: Sequence[float], max_len: int = 1 << 17,
                 eps: float = 1e-7) -> np.ndarray:
    """Impulse response of the IIR filter (b, a) (a[0] == 1), truncated when it has decayed."""
    key = (tuple(round(float(v), 12) for v in b), tuple(round(float(v), 12) for v in a))
    h = _IIR_CACHE.get(key)
    if h is not None:
        return h
    b = [float(v) for v in b]
    a = [float(v) for v in a]
    nb, na = len(b), len(a)
    out = []
    ybuf = [0.0] * na
    quiet = 0
    for n in range(max_len):
        acc = b[n] if n < nb else 0.0
        for k in range(1, na):
            acc -= a[k] * ybuf[k - 1]
        out.append(acc)
        ybuf = [acc] + ybuf[:-1]
        quiet = quiet + 1 if abs(acc) < eps else 0
        if quiet > 64 and n >= nb:
            break
    h = np.array(out[: len(out) - quiet] if quiet > 64 else out, dtype=np.float64)
    if len(h) == 0:
        h = np.zeros(1)
    _IIR_CACHE[key] = h
    return h


def _iir(x: np.ndarray, b: Sequence[float], a: Sequence[float]) -> np.ndarray:
    return fft_convolve(x, _iir_impulse(b, a))


def lowpass(x: Signal, cutoff: float, sr: int = SR, order: int = 1) -> np.ndarray:
    """One-pole low-pass (6 dB/oct per order), applied `order` times."""
    x = _as_signal(x)
    if cutoff >= sr * 0.5 or len(x) == 0:
        return x.copy()
    k = 1.0 - math.exp(-2.0 * math.pi * max(float(cutoff), 1e-3) / sr)
    L = int(min(max(math.log(1e-7) / math.log(max(1.0 - k, 1e-12)), 1), 1 << 17)) + 1
    h = k * (1.0 - k) ** np.arange(L)
    y = x
    for _ in range(max(1, int(order))):
        y = fft_convolve(y, h)
    return y


def highpass(x: Signal, cutoff: float, sr: int = SR, order: int = 1) -> np.ndarray:
    """One-pole high-pass (x minus its one-pole low-pass), applied `order` times."""
    x = _as_signal(x)
    y = x
    for _ in range(max(1, int(order))):
        y = y - lowpass(y, cutoff, sr, 1)
    return y


def lowpass_var(x: Signal, cutoff: Union[float, np.ndarray], sr: int = SR) -> np.ndarray:
    """One-pole low-pass with a per-sample cutoff curve (pure Python loop: use on short SFX)."""
    x = _as_signal(x)
    if x.ndim == 2:
        return _channel_map(lambda c: lowpass_var(c, cutoff, sr), x)
    n = len(x)
    c = resample_len(np.asarray(cutoff, dtype=np.float64).reshape(-1), n) if not np.isscalar(cutoff) else np.full(n, float(cutoff))
    k = 1.0 - np.exp(-2.0 * math.pi * np.clip(c, 1e-3, sr * 0.5) / sr)
    y = np.empty(n)
    acc = 0.0
    xl, kl = x.tolist(), k.tolist()
    for i in range(n):
        acc += kl[i] * (xl[i] - acc)
        y[i] = acc
    return y


def _rbj(kind: str, cutoff: float, q: float, sr: int) -> Tuple[list, list]:
    w0 = 2.0 * math.pi * float(np.clip(cutoff, 1.0, sr * 0.499)) / sr
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2.0 * max(float(q), 0.05))
    if kind == "lp":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
    elif kind == "hp":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
    elif kind == "bp":
        b = [alpha, 0.0, -alpha]
    else:
        raise ValueError(kind)
    a = [1 + alpha, -2 * cw, 1 - alpha]
    return [v / a[0] for v in b], [v / a[0] for v in a]


def biquad_lowpass(x: Signal, cutoff: float, q: float = 0.707, sr: int = SR) -> np.ndarray:
    """RBJ 12 dB/oct resonant low-pass (q 0.707 = flat, higher = resonance)."""
    b, a = _rbj("lp", cutoff, q, sr)
    return _iir(_as_signal(x), b, a)


def biquad_highpass(x: Signal, cutoff: float, q: float = 0.707, sr: int = SR) -> np.ndarray:
    b, a = _rbj("hp", cutoff, q, sr)
    return _iir(_as_signal(x), b, a)


def biquad_bandpass(x: Signal, center: float, q: float = 2.0, sr: int = SR) -> np.ndarray:
    """Constant-skirt band-pass (peak gain ~ q); good for breath/bow/wind formants."""
    b, a = _rbj("bp", center, q, sr)
    return _iir(_as_signal(x), b, a)


# ------------------------------------------------------------------------------------------
# Effects
# ------------------------------------------------------------------------------------------
def bitcrush(x: Signal, bits: int = 8, rate: Optional[float] = None, sr: int = SR) -> np.ndarray:
    """Amplitude quantisation to `bits` and optional sample-and-hold to `rate` Hz."""
    x = _as_signal(x)
    levels = float(2 ** int(bits)) / 2.0
    y = np.round(x * levels) / levels
    if rate is not None and rate < sr:
        idx = np.floor(np.arange(len(y)) * (float(rate) / sr)).astype(np.int64)
        first = np.concatenate([[0], np.flatnonzero(np.diff(idx)) + 1])
        hold = np.repeat(np.arange(len(first)), np.diff(np.append(first, len(y))))
        y = y[first][hold]
    return y


def delay(x: Signal, time_s: float = 0.25, feedback: float = 0.35, mix: float = 0.3,
          sr: int = SR, max_repeats: int = 40, damp: float = 0.0) -> np.ndarray:
    """Feedback delay / echo.  Output is longer than the input (the echo tail is kept).
    `damp` 0..1 low-passes each repeat a little more (darker echoes)."""
    x = _as_signal(x)
    if x.ndim == 2:
        return _channel_map(lambda c: delay(c, time_s, feedback, mix, sr, max_repeats, damp), x)
    d = max(1, samples(time_s, sr))
    fb = float(np.clip(feedback, 0.0, 0.98))
    reps = 1 if fb <= 0 else int(min(max_repeats, max(1, math.ceil(math.log(1e-4) / math.log(max(fb, 1e-9))))))
    n = len(x) + reps * d
    out = np.zeros(n)
    out[: len(x)] = x * (1.0 - mix)
    tap = x.copy()
    for k in range(1, reps + 1):
        tap = tap * fb
        if damp > 0:
            tap = lowpass(tap, 12000.0 * (1.0 - damp) ** k + 400.0, sr)
        out[k * d: k * d + len(tap)] += tap * mix
    return out


echo = delay


_REVERB_CACHE: Dict[tuple, np.ndarray] = {}


def _reverb_ir(decay: float, damp: float, sr: int) -> np.ndarray:
    key = (round(decay, 4), round(damp, 4), sr)
    ir = _REVERB_CACHE.get(key)
    if ir is not None:
        return ir
    combs_ms = (29.7, 37.1, 41.1, 43.7)
    allpass_ms = (5.0, 1.7)
    n_ir = samples(min(decay * 1.5 + 0.1, 12.0), sr)
    ir = np.zeros(n_ir)
    for i, ms in enumerate(combs_ms):
        d = samples(ms / 1000.0, sr)
        g = 10.0 ** (-3.0 * d / (max(decay, 0.05) * sr))
        k = np.arange(0, n_ir // d + 1)
        taps = (k * d)[k * d < n_ir]
        ir[taps] += g ** k[: len(taps)] * (1.0 if i % 2 == 0 else -1.0) * 0.25
    for ms in allpass_ms:
        d = samples(ms / 1000.0, sr)
        g = 0.7
        kmax = int(math.log(1e-5) / math.log(g)) + 1
        ap = np.zeros(kmax * d + 1)
        ap[0] = -g
        for k in range(1, kmax + 1):
            ap[k * d] = (1.0 - g * g) * g ** (k - 1)
        ir = fft_convolve(ir, ap)
    if damp > 0:
        cutoff = 12000.0 * (1.0 - damp) + 1500.0
        ir = lowpass(ir, cutoff, sr)
    ir *= np.exp(-np.arange(n_ir) / (max(decay, 0.05) * sr) * 1.5) + 0.02
    ir /= max(np.sum(np.abs(ir)) / 4.0, 1e-9)
    _REVERB_CACHE[key] = ir
    return ir


def reverb(x: Signal, decay: float = 1.5, mix: float = 0.25, sr: int = SR, damp: float = 0.5,
           predelay: float = 0.0, keep_tail: bool = True) -> np.ndarray:
    """Cheap Schroeder reverb (4 parallel combs + 2 allpasses, rendered as one impulse
    response and FFT-convolved).  `decay` ~ RT60 seconds, `mix` wet amount, `damp` darkens.
    With keep_tail the output is longer than the input."""
    x = _as_signal(x)
    if x.ndim == 2:
        return _channel_map(lambda c: reverb(c, decay, mix, sr, damp, predelay, keep_tail), x)
    ir = _reverb_ir(decay, damp, sr)
    if predelay > 0:
        ir = np.concatenate([np.zeros(samples(predelay, sr)), ir])
    wet = fft_convolve(x, ir, full=keep_tail)
    out = np.zeros(len(wet))
    out[: len(x)] = x * (1.0 - mix)
    out += wet * mix
    return out


def soft_clip(x: Signal, drive: float = 1.0, mode: str = "tanh") -> np.ndarray:
    """Soft saturation (tanh or cubic), output peak normalised to the input peak."""
    x = _as_signal(x)
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak == 0.0:
        return x.copy()
    y = x * drive / peak
    if mode == "cubic":
        y = np.clip(y, -1.5, 1.5)
        y = y - (y ** 3) / 6.75
        y /= 1.0
    else:
        y = np.tanh(y)
    return y * (peak / max(np.max(np.abs(y)), 1e-12))


def clip(x: Signal, limit: float = 1.0) -> np.ndarray:
    return np.clip(_as_signal(x), -limit, limit)


# ------------------------------------------------------------------------------------------
# Dynamics / editing
# ------------------------------------------------------------------------------------------
def remove_dc(x: Signal, cutoff: Optional[float] = None, sr: int = SR) -> np.ndarray:
    """Remove the DC offset (mean), or DC-block with a one-pole high-pass if cutoff is given."""
    x = _as_signal(x)
    if cutoff:
        return highpass(x, cutoff, sr)
    return x - np.mean(x, axis=0)


def normalize(x: Signal, peak_db: float = SFX_PEAK_DB, int16_safe: bool = True) -> np.ndarray:
    """Scale so the peak sits at peak_db dBFS.  int16_safe lowers the target by one 16-bit
    LSB so that the written WAV never exceeds peak_db under any reference (32767 or 32768)."""
    x = _as_signal(x)
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak <= 0.0:
        return x.copy()
    target = db_to_amp(peak_db)
    if int16_safe:
        target = (math.floor(target * 32767.0) - 1) / 32767.0
    return x * (target / peak)


def trim_silence(x: Signal, thresh_db: float = -60.0, sr: int = SR, head: bool = True,
                 tail: bool = True, keep_tail_s: float = 0.0) -> np.ndarray:
    """Cut leading (and trailing) samples below thresh_db relative to full scale.
    keep_tail_s leaves that much of the trailing silence in place."""
    x = _as_signal(x)
    if len(x) == 0:
        return x.copy()
    mag = np.abs(x) if x.ndim == 1 else np.max(np.abs(x), axis=1)
    thr = db_to_amp(thresh_db)
    idx = np.flatnonzero(mag > thr)
    if len(idx) == 0:
        return x[:0].copy()
    start = int(idx[0]) if head else 0
    end = int(idx[-1]) + 1 if tail else len(x)
    end = min(len(x), end + samples(keep_tail_s, sr))
    return x[start:end].copy()


def fade(x: Signal, in_s: float = 0.002, out_s: float = 0.002, sr: int = SR,
         shape: str = "lin") -> np.ndarray:
    """Linear (or 'cos' = raised cosine) fade-in / fade-out."""
    x = _as_signal(x).copy()
    n = len(x)
    ni, no = min(n, samples(in_s, sr)), min(n, samples(out_s, sr))
    if ni > 0:
        w = np.linspace(0.0, 1.0, ni, endpoint=False)
        if shape == "cos":
            w = 0.5 - 0.5 * np.cos(math.pi * w)
        x[:ni] *= w if x.ndim == 1 else w[:, None]
    if no > 0:
        u = np.linspace(0.0, 1.0, no, endpoint=False)
        w = (1.0 - u) if shape != "cos" else 0.5 + 0.5 * np.cos(math.pi * u)
        x[n - no:] *= w if x.ndim == 1 else w[:, None]
    return x


def pad(x: Signal, seconds_after: float = 0.0, sr: int = SR, seconds_before: float = 0.0) -> np.ndarray:
    """Append (and/or prepend) silence."""
    x = _as_signal(x)
    nb, na = samples(seconds_before, sr), samples(seconds_after, sr)
    shape_b = (nb,) if x.ndim == 1 else (nb, 2)
    shape_a = (na,) if x.ndim == 1 else (na, 2)
    return np.concatenate([np.zeros(shape_b), x, np.zeros(shape_a)])


def pad_to(x: Signal, n: int) -> np.ndarray:
    """Zero-pad or truncate to exactly n samples."""
    x = _as_signal(x)
    n = int(n)
    if len(x) >= n:
        return x[:n].copy()
    extra = (n - len(x),) if x.ndim == 1 else (n - len(x), 2)
    return np.concatenate([x, np.zeros(extra)])


def _promote(signals: List[np.ndarray]) -> List[np.ndarray]:
    if any(s.ndim == 2 for s in signals):
        return [to_stereo(s) if s.ndim == 1 else s for s in signals]
    return signals


def mix(*signals, gains: Optional[Sequence[float]] = None) -> np.ndarray:
    """Sum signals (len = longest).  Any stereo input promotes all to stereo."""
    sigs = [_as_signal(s) for s in (signals[0] if len(signals) == 1 and isinstance(signals[0], (list, tuple)) else signals)]
    if not sigs:
        return np.zeros(0)
    sigs = _promote(sigs)
    n = max(len(s) for s in sigs)
    out = np.zeros((n,) if sigs[0].ndim == 1 else (n, 2))
    for i, s in enumerate(sigs):
        g = 1.0 if gains is None else float(gains[i])
        out[: len(s)] += s * g
    return out


def concat(*signals) -> np.ndarray:
    """Concatenate signals in time (stereo promotion as in mix)."""
    sigs = [_as_signal(s) for s in (signals[0] if len(signals) == 1 and isinstance(signals[0], (list, tuple)) else signals)]
    if not sigs:
        return np.zeros(0)
    return np.concatenate(_promote(sigs))


# ------------------------------------------------------------------------------------------
# Music theory
# ------------------------------------------------------------------------------------------
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d+)$")
_NOTE_BASE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

# Chinese/Korean pentatonic modes (궁상각치우) = the five rotations of the major pentatonic.
PENTATONIC_MODES = {
    "major": (0, 2, 4, 7, 9), "gung": (0, 2, 4, 7, 9), "궁": (0, 2, 4, 7, 9),
    "sang": (0, 2, 5, 7, 10), "상": (0, 2, 5, 7, 10),
    "gak": (0, 3, 5, 8, 10), "각": (0, 3, 5, 8, 10),
    "chi": (0, 2, 5, 7, 9), "치": (0, 2, 5, 7, 9),
    "minor": (0, 3, 5, 7, 10), "u": (0, 3, 5, 7, 10), "우": (0, 3, 5, 7, 10),
}
CHORD_QUALITIES = {
    "maj": (0, 4, 7), "": (0, 4, 7), "M": (0, 4, 7), "min": (0, 3, 7), "m": (0, 3, 7),
    "5": (0, 7), "sus2": (0, 2, 7), "sus4": (0, 5, 7), "dim": (0, 3, 6), "aug": (0, 4, 8),
    "maj7": (0, 4, 7, 11), "min7": (0, 3, 7, 10), "m7": (0, 3, 7, 10), "dom7": (0, 4, 7, 10),
    "7": (0, 4, 7, 10), "add9": (0, 4, 7, 14), "madd9": (0, 3, 7, 14), "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9), "sus2add6": (0, 2, 7, 9), "pent": (0, 2, 4, 7, 9), "mpent": (0, 3, 5, 7, 10),
    "quartal": (0, 5, 10), "open": (0, 7, 12), "openm": (0, 7, 15), "openM": (0, 7, 16),
}


def note_to_midi(name: str) -> int:
    """'C4' -> 60, 'F#3' -> 54, 'Bb2' -> 46 (A4 = 69)."""
    m = _NOTE_RE.match(name.strip())
    if not m:
        raise ValueError("bad note name %r" % name)
    letter, acc, octv = m.group(1).upper(), m.group(2), int(m.group(3))
    return 12 * (octv + 1) + _NOTE_BASE[letter] + (1 if acc == "#" else -1 if acc == "b" else 0)


def midi_to_note(n: int) -> str:
    n = int(round(n))
    return "%s%d" % (NOTE_NAMES[n % 12], n // 12 - 1)


def midi_to_freq(n: float) -> float:
    return float(440.0 * 2.0 ** ((float(n) - 69.0) / 12.0))


def freq_to_midi(f: float) -> float:
    return float(69.0 + 12.0 * math.log2(max(float(f), 1e-9) / 440.0))


def note_freq(name: str) -> float:
    """'C4' -> 261.63 Hz (also accepts a midi number or a frequency, see to_freq)."""
    return midi_to_freq(note_to_midi(name))


def to_freq(note: Union[str, int, float, None]) -> Optional[float]:
    """Note name (str) -> Hz; int -> midi number -> Hz; float -> Hz as is; None -> None."""
    if note is None:
        return None
    if isinstance(note, str):
        return note_freq(note)
    if isinstance(note, (int, np.integer)) and not isinstance(note, bool):
        return midi_to_freq(int(note))
    return float(note)


def transpose(note: str, semitones: int) -> str:
    return midi_to_note(note_to_midi(note) + int(semitones))


def scale(root: str, intervals: Sequence[int], octaves: int = 1, include_top: bool = True) -> List[str]:
    """Note names of `intervals` (semitones from root) repeated over `octaves`, plus the top root."""
    base = note_to_midi(root)
    out = []
    for o in range(int(octaves)):
        out.extend(midi_to_note(base + 12 * o + i) for i in intervals)
    if include_top:
        out.append(midi_to_note(base + 12 * int(octaves)))
    return out


def pentatonic(root: str, mode: str = "major", octaves: int = 2, include_top: bool = True) -> List[str]:
    """Pentatonic note names over `octaves` octaves from root (e.g. 'C4').
    mode: 'major'/'gung'(궁), 'sang'(상), 'gak'(각), 'chi'(치), 'minor'/'u'(우).
    pentatonic('C4', 'major', 1) -> ['C4','D4','E4','G4','A4','C5']."""
    try:
        iv = PENTATONIC_MODES[mode]
    except KeyError:
        raise ValueError("unknown pentatonic mode %r" % mode)
    return scale(root, iv, octaves, include_top)


def chord(root: str, quality: str = "maj", inversion: int = 0) -> List[str]:
    """Chord note names, e.g. chord('A3', 'min') -> ['A3','C4','E4']; sus2/open/quartal
    voicings suit the pentatonic palette."""
    try:
        iv = list(CHORD_QUALITIES[quality])
    except KeyError:
        raise ValueError("unknown chord quality %r" % quality)
    base = note_to_midi(root)
    notes = [base + i for i in iv]
    for _ in range(int(inversion) % len(notes)):
        notes = notes[1:] + [notes[0] + 12]
    return [midi_to_note(n) for n in notes]


# ------------------------------------------------------------------------------------------
# Patterns
#   pattern = list of (start_beat, note_or_None, length_beats, velocity)
#   note: 'C4' | midi int | Hz float | list/tuple of those (chord) | None (rest)
# ------------------------------------------------------------------------------------------
Event = Tuple[float, object, float, float]
Pattern = List[Event]


def parse_pattern(text: str, step_beats: float = 0.25, velocity: float = 1.0,
                  accent: float = 1.0, soft: float = 0.7) -> Pattern:
    """Parse a step-sequencer string into a pattern.

    Tokens are whitespace separated ('|' bar lines are ignored).  Each token is one step of
    `step_beats` beats:
        C4  F#3  Bb2   note on (name)        60  midi number        440.0  frequency
        C4+E4+G4       chord (several notes starting together)
        --  -  .  r    rest                  ==  =  ~  _            tie (extend previous note)
        x  X           unpitched hit (for drum tracks; X = accent, x = `soft` velocity)
        C4@0.6         explicit velocity suffix (0..1), also works on x/X
        C4*            accent (velocity = `accent`)
    parse_pattern('C4 == E4 -- G4@0.5', 0.25) -> [(0,'C4',0.5,1.0),(0.75,'E4',0.25,1.0),(1.25,'G4',0.25,0.5)]
    """
    out: Pattern = []
    tokens = [t for t in text.replace("|", " ").split() if t]
    last = -1
    for i, tok in enumerate(tokens):
        if tok in ("--", "-", ".", "r", "R"):
            last = -1
            continue
        if tok in ("==", "=", "~", "_"):
            if last >= 0:
                s, n, l, v = out[last]
                out[last] = (s, n, l + step_beats, v)
            continue
        vel = velocity
        if "@" in tok:
            tok, vs = tok.split("@", 1)
            vel = float(vs)
        if tok.endswith("*"):
            tok, vel = tok[:-1], accent
        if tok in ("x", "X"):
            vel = soft * velocity if tok == "x" else vel
            note: object = "x"
        else:
            parts = tok.split("+")
            notes = [_parse_note_token(p) for p in parts]
            note = notes[0] if len(notes) == 1 else notes
        out.append((i * step_beats, note, step_beats, vel))
        last = len(out) - 1
    return out


def _parse_note_token(tok: str):
    if _NOTE_RE.match(tok):
        return tok[0].upper() + tok[1:]
    try:
        if re.match(r"^-?\d+$", tok):
            return int(tok)
        return float(tok)
    except ValueError:
        raise ValueError("bad pattern token %r" % tok)


def pattern_length(pattern: Pattern) -> float:
    """End of the last event in beats."""
    return max((s + l for s, _, l, _ in pattern), default=0.0)


def shift_pattern(pattern: Pattern, beats: float) -> Pattern:
    return [(s + beats, n, l, v) for s, n, l, v in pattern]


def bar(pattern: Pattern, index: int, beats_per_bar: int = 4) -> Pattern:
    """The pattern moved to bar `index` (0-based)."""
    return shift_pattern(pattern, index * beats_per_bar)


def repeat_pattern(pattern: Pattern, times: int, length_beats: Optional[float] = None) -> Pattern:
    """Tile a pattern `times` times every `length_beats` (default: its own rounded-up length)."""
    if length_beats is None:
        length_beats = pattern_length(pattern)
    out: Pattern = []
    for i in range(int(times)):
        out.extend(shift_pattern(pattern, i * length_beats))
    return out


def merge_patterns(*patterns: Pattern) -> Pattern:
    out: Pattern = []
    for p in patterns:
        out.extend(p)
    return sorted(out, key=lambda e: e[0])


def transpose_pattern(pattern: Pattern, semitones: int) -> Pattern:
    def tr(n):
        if n is None or n == "x":
            return n
        if isinstance(n, (list, tuple)):
            return [tr(k) for k in n]
        if isinstance(n, str):
            return transpose(n, semitones)
        if isinstance(n, (int, np.integer)):
            return int(n) + semitones
        return float(n) * 2.0 ** (semitones / 12.0)
    return [(s, tr(n), l, v) for s, n, l, v in pattern]


# ------------------------------------------------------------------------------------------
# Instrument adapter
# ------------------------------------------------------------------------------------------
_CORE_ARGS = ("freq", "dur", "vel")


def instrument(fn: Callable, **fixed) -> Callable[[float, float, float], np.ndarray]:
    """Adapt any sound function to the (freq, dur, vel) instrument signature.

    Arguments named freq/pitch, dur and vel are filled from the note (unless given in
    `fixed`); other keyword options are passed through, e.g.
        instrument(taiko, kind='low')     instrument(wood_block, pitch=880)
        instrument(zither, bright=0.6)    instrument(gong)
    Callables whose parameters have other names are called positionally (freq, dur, vel)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        params = {}
    names = set(params)
    has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    freq_name = "freq" if "freq" in names else ("pitch" if "pitch" in names else None)
    positional = not (names & {"freq", "pitch", "dur", "vel"}) and not has_varkw

    def inst(freq: float, dur: float, vel: float = 1.0) -> np.ndarray:
        if positional:
            return _as_signal(fn(freq, dur, vel, **fixed))
        kw = dict(fixed)
        if freq_name and freq_name not in kw and freq is not None:
            kw[freq_name] = freq
        if ("dur" in names or has_varkw) and "dur" not in kw:
            kw["dur"] = dur
        if ("vel" in names or has_varkw) and "vel" not in kw:
            kw["vel"] = vel
        return _as_signal(fn(**kw))

    inst.__name__ = "instrument(%s)" % getattr(fn, "__name__", "fn")
    inst.base = fn            # type: ignore[attr-defined]
    inst.fixed = fixed        # type: ignore[attr-defined]
    return inst


# ------------------------------------------------------------------------------------------
# Sequencer
# ------------------------------------------------------------------------------------------
def loop_samples(bpm: float, bars: int, beats_per_bar: int = 4, sr: int = SR) -> int:
    """Exact loop length in samples: round(bars*beats_per_bar*60/bpm*sr)."""
    return int(round(bars * beats_per_bar * 60.0 / bpm * sr))


class Track:
    def __init__(self, name, inst, pattern, volume, pan, swing, transpose_st, fx):
        self.name = name
        self.inst = inst
        self.pattern = list(pattern)
        self.volume = float(volume)
        self.pan = float(pan)
        self.swing = float(swing)
        self.transpose = int(transpose_st)
        self.fx = fx


class Sequencer:
    """Pattern sequencer rendering to stereo float32.

        seq = Sequencer(bpm=92)
        seq.add_track('lead', zither, parse_pattern('C5 == E5 G5 | A5 == G5 E5'), volume=0.8, pan=-0.2)
        seq.add_track('drum', instrument(taiko, kind='low'), parse_pattern('X -- x --'), swing=0.0)
        audio = seq.render_loop_safe(bars=4)      # exactly loop_samples(92, 4) samples

    Events: (start_beat, note, length_beats, velocity); note None = rest, 'x' = unpitched hit
    (freq C4).  Instruments may return tails longer than the note; `render` truncates at the
    loop end, `render_loop_safe` wraps the tails around to the start so loops are seamless.
    """

    HIT_FREQ = 261.6255653005986   # C4, passed to unpitched instruments for 'x' hits

    def __init__(self, bpm: float, sr: int = SR):
        self.bpm = float(bpm)
        self.sr = int(sr)
        self.tracks: List[Track] = []
        self.master_fx: List[Callable[[np.ndarray], np.ndarray]] = []
        self._cache: Dict[tuple, np.ndarray] = {}

    # -- timing ---------------------------------------------------------------------------
    @property
    def seconds_per_beat(self) -> float:
        return 60.0 / self.bpm

    def beats_to_samples(self, beats: float) -> int:
        return int(round(beats * self.seconds_per_beat * self.sr))

    def length_samples(self, bars: int, beats_per_bar: int = 4) -> int:
        return loop_samples(self.bpm, bars, beats_per_bar, self.sr)

    # -- tracks ---------------------------------------------------------------------------
    def add_track(self, name: str, instrument_fn: Callable, pattern: Pattern, volume: float = 1.0,
                  pan: float = 0.0, swing: float = 0.0, transpose: int = 0,
                  fx: Optional[Callable[[np.ndarray], np.ndarray]] = None) -> Track:
        """swing 0..1 delays every off-beat eighth (beat fraction .5) toward a triplet feel
        (1.0 = full triplet).  `fx` is applied to the finished mono track (e.g. reverb)."""
        inst = instrument_fn if getattr(instrument_fn, "base", None) is not None else instrument(instrument_fn)
        tr = Track(name, inst, pattern, volume, pan, swing, transpose, fx)
        self.tracks.append(tr)
        return tr

    def _note_audio(self, inst, freq: Optional[float], n_len: int, vel: float) -> np.ndarray:
        key = (id(inst), None if freq is None else round(freq, 5), n_len, round(vel, 4))
        y = self._cache.get(key)
        if y is None:
            y = _as_signal(inst(self.HIT_FREQ if freq is None else freq, n_len / self.sr, vel))
            if y.ndim == 2:
                y = to_mono(y)
            y = np.nan_to_num(y)
            self._cache[key] = y
        return y

    def _events(self, tr: Track):
        for start, note, length, vel in tr.pattern:
            if note is None:
                continue
            notes = note if isinstance(note, (list, tuple)) else [note]
            s = float(start)
            if tr.swing > 0 and abs((s % 1.0) - 0.5) < 1e-6:
                s += tr.swing / 6.0
            n_start = self.beats_to_samples(s)
            n_len = max(1, self.beats_to_samples(length))
            for nn in notes:
                if nn == "x":
                    freq = None
                else:
                    freq = to_freq(nn)
                    if tr.transpose and freq is not None:
                        freq *= 2.0 ** (tr.transpose / 12.0)
                yield n_start, n_len, freq, float(vel)

    def _render_track(self, tr: Track, total: int, extra: int) -> np.ndarray:
        """Mono buffer of length >= total; material beyond `total` is the wrap tail."""
        buf = np.zeros(total + extra)
        for n_start, n_len, freq, vel in self._events(tr):
            if n_start >= total or n_start < 0:
                continue
            y = self._note_audio(tr.inst, freq, n_len, vel)
            end = n_start + len(y)
            if end > len(buf):
                buf = np.concatenate([buf, np.zeros(end - len(buf))])
            buf[n_start:end] += y
        if tr.fx is not None:
            buf = _as_signal(tr.fx(buf))
            if buf.ndim == 2:
                buf = to_mono(buf)
        return buf * tr.volume

    def _mix(self, total: int, wrap: bool) -> np.ndarray:
        out = np.zeros((total, 2))
        for tr in self.tracks:
            buf = self._render_track(tr, total, 0)
            if wrap:
                folded = buf[:total].copy()
                pos = total
                while pos < len(buf):
                    chunk = buf[pos: pos + total]
                    folded[: len(chunk)] += chunk
                    pos += total
                buf = folded
            else:
                buf = buf[:total]
            if len(buf) < total:
                buf = pad_to(buf, total)
            out += to_stereo(buf, tr.pan)
        for fx in self.master_fx:
            y = _as_signal(fx(out))
            out = pad_to(y if y.ndim == 2 else to_stereo(y), total)
        return out

    def render(self, bars: int, beats_per_bar: int = 4) -> np.ndarray:
        """Stereo float32 of exactly loop_samples(...) samples; note tails are truncated."""
        total = self.length_samples(bars, beats_per_bar)
        return self._mix(total, wrap=False).astype(np.float32)

    def render_loop_safe(self, bars: int, beats_per_bar: int = 4) -> np.ndarray:
        """Like render, but tails that spill past the end wrap around to the start (seamless)."""
        total = self.length_samples(bars, beats_per_bar)
        return self._mix(total, wrap=True).astype(np.float32)


# ------------------------------------------------------------------------------------------
# Instrument library.  Pitched instruments: (freq, dur, vel=1.0, **opts) -> mono array,
# returning the note plus its natural release (longer than dur).  Velocity 0..1.
# ------------------------------------------------------------------------------------------
def _vel_gain(vel: float) -> float:
    return float(np.clip(vel, 0.0, 1.5)) ** 1.3


def _nseed(*parts) -> int:
    return _hash_seed(*parts)


def _click(dur: float, cutoff: float, seed_v: int, sr: int = SR) -> np.ndarray:
    n = samples(dur, sr)
    if n <= 0:
        return np.zeros(0)
    return lowpass(noise(dur, "white", sr, seed_v), cutoff, sr) * env_decay(n, dur / 3.0, sr)


# -- chip instruments ------------------------------------------------------------------------
def nes_lead(duty: float = 0.5, attack: float = 0.004, decay: float = 0.08, sustain: float = 0.7,
             release: float = 0.05, vib_depth: float = 0.12, vib_rate: float = 6.0,
             vib_onset: float = 0.2) -> Callable:
    """Factory: NES pulse lead with the given duty (0.125 / 0.25 / 0.5) and light vibrato."""
    def inst(freq: float, dur: float, vel: float = 1.0, sr: int = SR) -> np.ndarray:
        env = env_note(dur, attack, decay, sustain, release, sr)
        f = vibrato(freq, len(env) / sr, vib_rate, vib_depth, sr, onset=vib_onset) if vib_depth > 0 else freq
        y = osc_pulse(f, None if vib_depth > 0 else len(env) / sr, duty, sr)
        return y * env * 0.5 * _vel_gain(vel)
    inst.__name__ = "nes_lead(duty=%g)" % duty
    return inst


def nes_bass_tri(freq: float, dur: float, vel: float = 1.0, sr: int = SR, release: float = 0.02) -> np.ndarray:
    """NES triangle bass: 4-bit stepped triangle, no attack, hard-ish release."""
    env = env_note(dur, 0.002, 0.0, 1.0, release, sr, curve="lin")
    y = osc_tri(freq, len(env) / sr, sr)
    y = bitcrush(y, 4)
    return y * env * 0.8 * _vel_gain(vel)


def nes_noise_drum(kind: str = "kick") -> Callable:
    """Factory: chip drums from NES noise + triangle: kick, snare, hat, openhat, tom, crash."""
    kind = kind.lower()

    def inst(freq: float = 100.0, dur: float = 0.25, vel: float = 1.0, sr: int = SR) -> np.ndarray:
        g = _vel_gain(vel)
        if kind == "kick":
            n = samples(0.22, sr)
            body = osc_tri(freq_curve(160.0, 45.0, 0.22, "exp", sr), None, sr) * env_decay(n, 0.07, sr)
            click = nes_noise(0.02, period=2, sr=sr) * env_decay(samples(0.02, sr), 0.004, sr)
            return mix(body * 0.9, click * 0.4) * g
        if kind == "snare":
            n = samples(0.2, sr)
            tone = osc_tri(freq_curve(220.0, 150.0, 0.2, "exp", sr), None, sr) * env_decay(n, 0.03, sr)
            nz = nes_noise(0.2, period=6, sr=sr) * env_decay(n, 0.05, sr)
            return mix(tone * 0.5, nz * 0.7) * g
        if kind in ("hat", "closedhat", "hihat"):
            n = samples(0.06, sr)
            return nes_noise(0.06, period=0, mode="long", sr=sr) * env_decay(n, 0.012, sr) * 0.5 * g
        if kind == "openhat":
            n = samples(0.3, sr)
            return nes_noise(0.3, period=1, sr=sr) * env_decay(n, 0.09, sr) * 0.45 * g
        if kind == "tom":
            n = samples(0.3, sr)
            return osc_tri(freq_curve(freq * 1.4, freq * 0.8, 0.3, "exp", sr), None, sr) * env_decay(n, 0.09, sr) * 0.8 * g
        if kind == "crash":
            n = samples(0.8, sr)
            return nes_noise(0.8, period=3, mode="short", sr=sr) * env_decay(n, 0.25, sr) * 0.4 * g
        raise ValueError("unknown nes drum kind %r" % kind)
    inst.__name__ = "nes_noise_drum(%s)" % kind
    return inst


def pluck(freq: float, dur: float, vel: float = 1.0, sr: int = SR, bright: float = 0.6,
          duty: float = 0.25, release: float = 0.25) -> np.ndarray:
    """Chip pluck: pulse through a fast-closing low-pass, exponential amplitude decay."""
    n = samples(dur, sr) + samples(release, sr)
    g = _vel_gain(vel)
    y = osc_pulse(freq, n / sr, duty, sr)
    cutoff = freq * (2.0 + 10.0 * bright * g) * env_decay(n, 0.12, sr) + freq * 1.5
    y = lowpass_var(y, np.clip(cutoff, 200.0, sr * 0.45), sr) if n < sr * 3 else lowpass(y, freq * 4, sr)
    env = env_decay(n, 0.18 + 0.25 * dur, sr) * env_note(dur, 0.002, 0.0, 1.0, release, sr)
    return y * env * 0.7 * g


def pad(freq: float, dur: float, vel: float = 1.0, sr: int = SR, attack: float = 0.35,
        release: float = 0.6, detune: float = 0.4, cutoff: float = 2200.0) -> np.ndarray:
    """Soft pad: three detuned saws + a sub triangle, slow attack, low-passed (wind-like)."""
    env = env_note(dur, attack, 0.2, 0.85, release, sr)
    n = len(env)
    d = 2.0 ** (detune / 1200.0)
    y = (osc_saw(freq, n / sr, sr) + osc_saw(freq * d, n / sr, sr, phase=0.33)
         + osc_saw(freq / d, n / sr, sr, phase=0.61)) / 3.0
    y = lowpass(y, cutoff, sr, order=2) + 0.35 * osc_tri(freq * 0.5, n / sr, sr)
    return y * env * 0.45 * _vel_gain(vel)


def bell(freq: float, dur: float, vel: float = 1.0, sr: int = SR, release: float = 1.2) -> np.ndarray:
    """FM-style bell from inharmonic partials (1, 2.76, 5.4, 8.9), fast attack."""
    total = dur + release
    partials = [(1.0, 1.0, 0.35 * total), (2.76, 0.5, 0.18 * total), (5.4, 0.28, 0.1 * total),
                (8.93, 0.12, 0.06 * total), (0.5, 0.15, 0.4 * total)]
    y = additive(freq, total, partials, sr)
    n = len(y)
    y *= env_adsr(n, 0.002, 0.0, 1.0, 0.1, sr)
    return y * 0.55 * _vel_gain(vel)


# -- wuxia instruments -----------------------------------------------------------------------
def zither(freq: float, dur: float, vel: float = 1.0, sr: int = SR, bright: float = 0.7,
           release: float = 0.5, detune_cents: float = 4.0) -> np.ndarray:
    """가야금/古箏-like pluck: sharp attack, fast exponential decay, 2-3 slightly detuned
    harmonics (higher ones decay faster), a tiny pitch drop at onset and a short pick noise.
    Rings for dur + release seconds (or less for high notes)."""
    g = _vel_gain(vel)
    ring = min(dur + release, 0.5 + 180.0 / max(freq, 40.0))
    n = max(samples(ring, sr), 8)
    t = np.arange(n) / sr
    drop = 2.0 ** (0.35 / 12.0 * np.exp(-t / 0.025))               # +35 cents decaying in ~25 ms
    f0 = freq * drop
    d = 2.0 ** (detune_cents / 1200.0)
    tau = 0.22 + 0.9 * (120.0 / max(freq, 60.0)) ** 0.5 * 0.35
    h1 = osc_sine(f0, None, sr) * np.exp(-t / tau)
    h2 = osc_sine(f0 * 2.0 * d, None, sr, phase=0.17) * np.exp(-t / (tau * 0.45)) * (0.55 + 0.25 * bright * g)
    h3 = osc_sine(f0 * 3.0 / d, None, sr, phase=0.41) * np.exp(-t / (tau * 0.25)) * (0.3 + 0.3 * bright * g)
    h4 = osc_tri(f0 * 4.0, None, sr) * np.exp(-t / (tau * 0.12)) * 0.18 * bright * g
    pick = _click(0.012, 6000.0, _nseed("zither", freq, dur, vel), sr) * 0.5 * g
    y = mix(h1 + h2 + h3 + h4, pick)
    y *= env_adsr(n, 0.0015, 0.0, 1.0, min(0.08, ring * 0.3), sr)
    return y * 0.6 * g


def flute(freq: float, dur: float, vel: float = 1.0, sr: int = SR, attack: float = 0.02,
          release: float = 0.08, breath: float = 0.35, vib_rate: float = 5.2,
          vib_depth: float = 0.25, vib_onset: float = 0.15) -> np.ndarray:
    """대금/dizi-like: sine + triangle body, breath noise burst at the onset (and a little
    sustained air), slow 20 ms attack, vibrato starting after 150 ms."""
    g = _vel_gain(vel)
    env = env_note(dur, attack, 0.08, 0.85, release, sr)
    n = len(env)
    f = vibrato(freq, n / sr, vib_rate, vib_depth, sr, onset=vib_onset, ramp=0.2)
    body = osc_sine(f, None, sr) * 0.7 + osc_tri(f, None, sr) * 0.3 + osc_sine(f * 2.0, None, sr, phase=0.3) * 0.12
    body = lowpass(body, min(freq * 6.0, 9000.0), sr)
    sd = _nseed("flute", freq, dur, vel)
    air = biquad_bandpass(noise(n / sr, "white", sr, sd), min(freq * 4.0, 5000.0), 1.2, sr)
    air_env = env_decay(n, 0.06, sr) * 1.0 + 0.12
    y = body * env + air * air_env * env * breath * 0.35
    return y * 0.55 * g


def erhu(freq: float, dur: float, vel: float = 1.0, sr: int = SR, attack: float = 0.05,
         release: float = 0.12, vib_rate: float = 5.0, vib_depth: float = 0.45,
         glide: float = 0.07, from_semitones: float = -1.0) -> np.ndarray:
    """二胡-like: sawtooth-ish, low-passed (cutoff tracks pitch), slow wide vibrato and a
    slight portamento into the note from `from_semitones` below; bow noise at the onset."""
    g = _vel_gain(vel)
    env = env_note(dur, attack, 0.1, 0.9, release, sr)
    n = len(env)
    f_start = freq * 2.0 ** (from_semitones / 12.0)
    f = portamento(f_start, freq, n / sr, glide, "exp", sr)
    f = vibrato(f, None, vib_rate, vib_depth, sr, onset=0.12, ramp=0.25)
    y = osc_saw(f, None, sr) * 0.7 + osc_tri(f, None, sr) * 0.3
    y = biquad_lowpass(y, min(max(freq * 4.5, 1200.0), 7000.0), 1.4, sr)
    y = lowpass(y, 5000.0, sr)
    sd = _nseed("erhu", freq, dur, vel)
    bow = biquad_bandpass(noise(n / sr, "white", sr, sd), 3200.0, 1.0, sr) * (env_decay(n, 0.05, sr) * 0.6 + 0.06)
    return (y + bow * 0.25) * env * 0.5 * g


def taiko(kind: str = "low", vel: float = 1.0, dur: Optional[float] = None,
          freq: Optional[float] = None, sr: int = SR) -> np.ndarray:
    """Taiko / 북 hit: sine thump with a pitch drop plus a skin click.
    kind 'low' (大太鼓), 'mid', 'rim' (wood rim click).  `freq` overrides the body pitch."""
    kind = kind.lower()
    g = _vel_gain(vel)
    sd = _nseed("taiko", kind, vel)
    if kind == "rim":
        d = dur or 0.09
        n = samples(d, sr)
        tone = osc_sine(freq_curve(1900.0 if freq is None else freq * 2, 1200.0, d, "exp", sr), None, sr) * env_decay(n, 0.012, sr)
        clk = highpass(noise(d, "white", sr, sd), 2500.0, sr) * env_decay(n, 0.008, sr)
        y = tone * 0.6 + clk * 0.9
        return fade(y * 0.8 * g, 0.0005, 0.01, sr)
    if kind == "mid":
        f0, f1, d, tau = (200.0, 95.0, dur or 0.45, 0.12)
    else:
        f0, f1, d, tau = (130.0, 48.0, dur or 0.7, 0.22)
    if freq is not None:
        f0, f1 = freq * 2.2, freq
    n = samples(d, sr)
    body = osc_sine(freq_curve(f0, f1, d, "exp", sr), None, sr) * env_decay(n, tau, sr)
    body = soft_clip(body * (1.0 + 1.2 * g), 1.4)
    click = lowpass(noise(d, "white", sr, sd), 1800.0, sr) * env_decay(n, 0.006, sr) * 0.7
    skin = lowpass(noise(d, "pink", sr, sd + 1), 500.0, sr) * env_decay(n, 0.05, sr) * 0.35
    y = mix(body, click, skin)
    y *= env_adsr(n, 0.001, 0.0, 1.0, min(0.05, d * 0.2), sr)
    return y * 0.85 * g


def gong(dur: float = 3.0, vel: float = 1.0, freq: float = 92.0, sr: int = SR,
         shimmer: float = 0.6) -> np.ndarray:
    """Chinese gong (銅鑼): inharmonic partials that bloom after the strike, long decay and a
    slow beating shimmer.  `freq` is the fundamental (~80-120 Hz for a large gong)."""
    g = _vel_gain(vel)
    n = samples(dur, sr)
    t = np.arange(n) / sr
    ratios = (1.0, 1.52, 2.03, 2.58, 3.37, 4.11, 5.43, 6.8)
    amps = (1.0, 0.75, 0.55, 0.5, 0.35, 0.28, 0.18, 0.1)
    bloom = (0.0, 0.12, 0.18, 0.25, 0.3, 0.35, 0.3, 0.2)       # seconds to reach full level
    y = np.zeros(n)
    for i, (r, a, b) in enumerate(zip(ratios, amps, bloom)):
        tau = dur * (0.42 - 0.035 * i)
        env = np.exp(-t / max(tau, 0.05))
        if b > 0:
            env *= np.minimum(1.0, 0.35 + t / b)
        beat = 1.0 + shimmer * 0.5 * np.sin(2.0 * math.pi * (0.7 + 0.9 * i) * t + i)
        f = freq * r * (1.0 + 0.0015 * np.sin(2.0 * math.pi * (0.3 + 0.2 * i) * t))
        y += osc_sine(f, None, sr, phase=0.1 * i) * a * env * (0.6 + 0.4 * beat)
    strike = lowpass(noise(min(0.08, dur), "white", sr, _nseed("gong", vel)), 3000.0, sr)
    strike *= env_decay(len(strike), 0.015, sr) * 1.2
    y = mix(y, strike)
    y = soft_clip(y * (1.0 + 0.8 * g), 1.3)
    y *= env_adsr(n, 0.003, 0.0, 1.0, min(0.3, dur * 0.25), sr, curve="exp")
    return y * 0.7 * g


def temple_bell(freq: float = 196.0, dur: float = 3.0, vel: float = 1.0, sr: int = SR,
                beat_hz: float = 1.1) -> np.ndarray:
    """Korean/Chinese temple bell (범종): hum + prime + tierce + quint + nominal partials,
    the hum detuned into a slow 맥놀이 beat, long decay; `freq` is the prime (strike tone)."""
    g = _vel_gain(vel)
    n = samples(dur, sr)
    t = np.arange(n) / sr
    hum = freq * 0.5
    parts = [(hum - beat_hz * 0.5, 0.55, dur * 0.6), (hum + beat_hz * 0.5, 0.55, dur * 0.6),
             (freq, 1.0, dur * 0.35), (freq * 1.19, 0.42, dur * 0.22), (freq * 1.5, 0.35, dur * 0.2),
             (freq * 2.0, 0.5, dur * 0.14), (freq * 2.51, 0.22, dur * 0.09), (freq * 2.99, 0.16, dur * 0.07),
             (freq * 4.1, 0.08, dur * 0.04)]
    y = np.zeros(n)
    for i, (f, a, tau) in enumerate(parts):
        y += osc_sine(f, n / sr, sr, phase=0.13 * i) * a * np.exp(-t / max(tau, 0.03))
    strike = lowpass(noise(min(0.03, dur), "white", sr, _nseed("bell", freq, vel)), 5000.0, sr)
    strike *= env_decay(len(strike), 0.006, sr) * 0.8
    y = mix(y, strike)
    y *= env_adsr(n, 0.002, 0.0, 1.0, min(0.25, dur * 0.2), sr, curve="exp")
    y = soft_clip(y * (1.0 + 0.5 * g), 1.2)
    return y * 0.6 * g


def wood_block(pitch: float = 900.0, vel: float = 1.0, dur: float = 0.11, sr: int = SR) -> np.ndarray:
    """목탁 / wood block: short band-passed click with a damped tone at `pitch` Hz."""
    g = _vel_gain(vel)
    n = samples(dur, sr)
    t = np.arange(n) / sr
    tone = osc_sine(pitch * (1.0 + 0.03 * np.exp(-t / 0.004)), None, sr) * np.exp(-t / 0.022)
    tone2 = osc_sine(pitch * 2.41, n / sr, sr) * np.exp(-t / 0.008) * 0.35
    sd = _nseed("wood", pitch, vel)
    clk = biquad_bandpass(noise(dur, "white", sr, sd), min(pitch * 1.6, 8000.0), 1.5, sr) * np.exp(-t / 0.006)
    y = mix(tone * 0.8, tone2, clk * 1.6)
    y *= env_adsr(n, 0.0005, 0.0, 1.0, min(0.03, dur * 0.3), sr)
    return y * 0.8 * g


def shaker(dur: float = 0.14, vel: float = 1.0, sr: int = SR, tone: float = 6000.0) -> np.ndarray:
    """Seed shaker / 방울: high-passed noise with a quick swell and decay."""
    g = _vel_gain(vel)
    n = samples(dur, sr)
    y = highpass(noise(dur, "white", sr, _nseed("shaker", dur, vel)), tone, sr, order=2)
    y *= env_adsr(n, 0.008, 0.0, 1.0, dur * 0.7, sr, curve="exp")
    return y * 0.5 * g


INSTRUMENTS: Dict[str, Callable] = {
    "nes_lead": nes_lead(0.5), "nes_lead_25": nes_lead(0.25), "nes_lead_12": nes_lead(0.125),
    "nes_bass_tri": nes_bass_tri, "kick": nes_noise_drum("kick"), "snare": nes_noise_drum("snare"),
    "hat": nes_noise_drum("hat"), "pluck": pluck, "pad": pad, "bell": bell, "zither": zither,
    "flute": flute, "erhu": erhu,
}


# ------------------------------------------------------------------------------------------
# File I/O
# ------------------------------------------------------------------------------------------
def _to_int16(x: np.ndarray) -> np.ndarray:
    return np.clip(np.round(x * 32767.0), -32768, 32767).astype("<i2")


def write_wav(path: str, x: Signal, sr: int = SR) -> str:
    """Write 16-bit PCM WAV (mono (n,) or stereo (n,2) floats in -1..1, clipped)."""
    x = _as_signal(x)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    data = _to_int16(np.nan_to_num(x))
    ch = 1 if x.ndim == 1 else 2
    with wave.open(path, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(data.tobytes())
    return path


def read_wav(path: str) -> Tuple[np.ndarray, int]:
    """Read a PCM (8/16/24/32-bit) or 32-bit float WAV -> (float64 array (n,) or (n,2), sr)."""
    with open(path, "rb") as fh:
        blob = fh.read()
    if blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        raise ValueError("not a RIFF/WAVE file: %s" % path)
    pos = 12
    fmt = None
    data = None
    while pos + 8 <= len(blob):
        cid, size = blob[pos:pos + 4], struct.unpack("<I", blob[pos + 4:pos + 8])[0]
        body = blob[pos + 8: pos + 8 + size]
        if cid == b"fmt ":
            tag, ch, sr, _, _, bits = struct.unpack("<HHIIHH", body[:16])
            if tag == 0xFFFE and len(body) >= 26:   # WAVE_FORMAT_EXTENSIBLE: sub-format guid
                tag = struct.unpack("<H", body[24:26])[0]
            fmt = (tag, ch, sr, bits)
        elif cid == b"data":
            data = body
        pos += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise ValueError("WAV without fmt/data chunk: %s" % path)
    tag, ch, sr, bits = fmt
    if tag == 3 and bits == 32:
        arr = np.frombuffer(data, dtype="<f4").astype(np.float64)
    elif tag == 1 and bits == 16:
        arr = np.frombuffer(data, dtype="<i2").astype(np.float64) / 32768.0
    elif tag == 1 and bits == 8:
        arr = (np.frombuffer(data, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    elif tag == 1 and bits == 24:
        raw = np.frombuffer(data[: len(data) - len(data) % 3], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        val = raw[:, 0] | (raw[:, 1] << 8) | (raw[:, 2] << 16)
        val = np.where(val >= 1 << 23, val - (1 << 24), val)
        arr = val.astype(np.float64) / float(1 << 23)
    elif tag == 1 and bits == 32:
        arr = np.frombuffer(data, dtype="<i4").astype(np.float64) / float(1 << 31)
    else:
        raise ValueError("unsupported WAV format tag=%d bits=%d" % (tag, bits))
    if ch == 2:
        arr = arr[: len(arr) - len(arr) % 2].reshape(-1, 2)
    elif ch != 1:
        arr = arr[: len(arr) - len(arr) % ch].reshape(-1, ch).mean(axis=1)
    return arr, int(sr)


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found on PATH (needed for OGG)")
    return exe


def write_ogg(path: str, x: Signal, sr: int = SR, quality: float = 6, stereo: bool = True) -> str:
    """Encode to OGG Vorbis (ffmpeg libvorbis, -q:a quality) from float samples piped to ffmpeg.
    `stereo=True` promotes mono input to stereo (spec: music is stereo)."""
    x = _as_signal(x)
    if stereo and x.ndim == 1:
        x = to_stereo(x)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    ch = 1 if x.ndim == 1 else 2
    raw = np.nan_to_num(x).astype("<f4").tobytes()
    cmd = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
           "-f", "f32le", "-ar", str(int(sr)), "-ac", str(ch), "-i", "pipe:0",
           "-vn", "-map_metadata", "-1", "-fflags", "+bitexact", "-flags", "+bitexact",
           "-c:a", "libvorbis", "-q:a", str(quality), "-ar", str(int(sr)), "-ac", str(ch),
           "-f", "ogg", path]
    proc = subprocess.run(cmd, input=raw, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed: %s" % proc.stderr.decode("utf-8", "replace").strip())
    return path


def read_ogg(path: str, tmp_dir: Optional[str] = None) -> Tuple[np.ndarray, int]:
    """Decode any ffmpeg-readable audio (OGG) via a temporary 32-bit float WAV."""
    info = ffprobe_info(path)
    sr = int(info.get("sample_rate") or SR)
    ch = int(info.get("channels") or 1)
    tmp = tempfile.NamedTemporaryFile(prefix="ak_dec_", suffix=".wav", dir=tmp_dir, delete=False)
    tmp.close()
    try:
        cmd = [_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", path,
               "-vn", "-c:a", "pcm_f32le", "-ar", str(sr), "-ac", str(ch), "-f", "wav", tmp.name]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError("ffmpeg decode failed: %s" % proc.stderr.decode("utf-8", "replace").strip())
        return read_wav(tmp.name)
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass


def ffprobe_info(path: str) -> dict:
    """{'codec','channels','sample_rate','duration','bits'} for the first audio stream."""
    exe = shutil.which("ffprobe")
    if not exe:
        raise RuntimeError("ffprobe not found on PATH")
    cmd = [exe, "-v", "error", "-select_streams", "a:0", "-show_entries",
           "stream=codec_name,channels,sample_rate,duration,bits_per_sample,bits_per_raw_sample:format=duration",
           "-of", "json", path]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError("ffprobe failed: %s" % proc.stderr.decode("utf-8", "replace").strip())
    js = json.loads(proc.stdout.decode("utf-8", "replace") or "{}")
    st = (js.get("streams") or [{}])[0]
    fmt = js.get("format") or {}
    dur = st.get("duration") or fmt.get("duration")
    return {
        "codec": st.get("codec_name"),
        "channels": int(st.get("channels") or 0),
        "sample_rate": int(st.get("sample_rate") or 0),
        "duration": float(dur) if dur else None,
        "bits": int(st.get("bits_per_sample") or st.get("bits_per_raw_sample") or 0),
    }


# ------------------------------------------------------------------------------------------
# Measurement + spec helpers
# ------------------------------------------------------------------------------------------
def measure(x: Signal, sr: int = SR, silence_db: float = -60.0) -> dict:
    """Duration, peak/RMS dBFS, leading/trailing silence (ms) and DC offset of a signal."""
    x = _as_signal(x)
    n = len(x)
    mag = np.abs(x) if x.ndim == 1 else np.max(np.abs(x), axis=1)
    peak = float(mag.max()) if n else 0.0
    rms = float(np.sqrt(np.mean(x ** 2))) if n else 0.0
    thr = db_to_amp(silence_db)
    idx = np.flatnonzero(mag > thr)
    lead = (idx[0] / sr * 1000.0) if len(idx) else n / sr * 1000.0
    trail = ((n - 1 - idx[-1]) / sr * 1000.0) if len(idx) else n / sr * 1000.0
    dc = float(np.max(np.abs(np.mean(x, axis=0)))) if n else 0.0
    return {"samples": n, "channels": 1 if x.ndim == 1 else 2, "sr": sr, "duration": n / sr,
            "peak": peak, "peak_db": amp_to_db(peak), "rms_db": amp_to_db(rms),
            "leading_silence_ms": float(lead), "trailing_silence_ms": float(trail), "dc": dc}


def is_pascal_case(name: str) -> bool:
    return bool(_PASCAL_RE.match(name))


def sfx_path(audio_root: str, name: str) -> str:
    if not is_pascal_case(name):
        raise ValueError("SFX name must be PascalCase: %r" % name)
    return os.path.join(audio_root, "Sfx", name + ".wav")


def music_path(audio_root: str, name: str) -> str:
    if not is_pascal_case(name):
        raise ValueError("music name must be PascalCase: %r" % name)
    return os.path.join(audio_root, "Music", name + ".ogg")


def finalize_sfx(x: Signal, sr: int = SR, peak_db: float = SFX_PEAK_DB, fade_s: float = 0.002,
                 thresh_db: float = -60.0, max_seconds: float = SFX_MAX_SECONDS,
                 tail_s: float = 0.0) -> np.ndarray:
    """Spec section 6 SFX mastering: mono, DC removed, trimmed at thresh_db, clamped to
    max_seconds (with a 30 ms fade-out when cut), 2 ms fades, peak at -1 dBFS."""
    x = to_mono(x)
    x = np.nan_to_num(x)
    x = remove_dc(x)
    x = trim_silence(x, thresh_db, sr, keep_tail_s=tail_s)
    if len(x) == 0:
        raise ValueError("finalize_sfx: signal is silent")
    n_max = samples(max_seconds, sr)
    if len(x) > n_max:
        x = fade(x[:n_max], 0.0, 0.03, sr)
    x = fade(x, fade_s, fade_s, sr)
    x = remove_dc(x)
    x = normalize(x, peak_db)
    return x


def save_sfx(path: str, x: Signal, sr: int = SR, finalize: bool = True) -> str:
    """finalize_sfx + write_wav.  Returns the path."""
    if finalize:
        x = finalize_sfx(x, sr)
    return write_wav(path, x, sr)


def save_music(path: str, x: Signal, sr: int = SR, peak_db: float = MUSIC_PEAK_DB,
               quality: float = 6, master_wav: Optional[str] = None, normalize_peak: bool = True) -> str:
    """Normalise a stereo mix to peak_db (headroom for Vorbis), write the OGG and optionally
    a WAV master (into tmp_dir, never into Assets).  Length is kept exactly (no trimming)."""
    x = _as_signal(x)
    if x.ndim == 1:
        x = to_stereo(x)
    x = np.nan_to_num(x)
    if normalize_peak:
        x = normalize(x, peak_db)
    if master_wav:
        write_wav(master_wav, x, sr)
    return write_ogg(path, x, sr, quality, stereo=True)


def check_sfx(path: str, peak_db: float = SFX_PEAK_DB, max_seconds: float = SFX_MAX_SECONDS,
              max_lead_ms: float = 5.0) -> List[str]:
    """Spec checks for one SFX file; returns a list of problems (empty = OK)."""
    issues = []
    name, ext = os.path.splitext(os.path.basename(path))
    if ext.lower() != ".wav":
        issues.append("extension must be .wav")
    if not is_pascal_case(name):
        issues.append("name must be PascalCase")
    try:
        x, sr = read_wav(path)
    except Exception as e:  # noqa: BLE001
        return issues + ["unreadable: %s" % e]
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2:
            issues.append("must be 16-bit (is %d-bit)" % (8 * w.getsampwidth()))
    if sr != SR:
        issues.append("sample rate must be 44100 (is %d)" % sr)
    if x.ndim != 1:
        issues.append("must be mono")
    m = measure(x, sr)
    if m["peak_db"] > peak_db + 0.01:
        issues.append("peak %.2f dBFS > %.1f" % (m["peak_db"], peak_db))
    if m["peak_db"] < -12.0:
        issues.append("peak %.2f dBFS is very low (not normalised?)" % m["peak_db"])
    if m["duration"] > max_seconds + 1e-6:
        issues.append("duration %.3f s > %.1f s" % (m["duration"], max_seconds))
    if m["leading_silence_ms"] > max_lead_ms:
        issues.append("leading silence %.1f ms > %.0f ms" % (m["leading_silence_ms"], max_lead_ms))
    if m["dc"] > 0.02:
        issues.append("DC offset %.3f" % m["dc"])
    if m["samples"] == 0:
        issues.append("empty file")
    return issues


def check_music(path: str, bpm: Optional[float] = None, bars: Optional[int] = None,
                beats_per_bar: int = 4, peak_db: float = SFX_PEAK_DB, loop: bool = True) -> List[str]:
    """Spec checks for one music file (decodes it); with bpm+bars the exact loop length is
    verified.  Returns a list of problems (empty = OK)."""
    issues = []
    name, ext = os.path.splitext(os.path.basename(path))
    if ext.lower() != ".ogg":
        issues.append("extension must be .ogg")
    if not is_pascal_case(name):
        issues.append("name must be PascalCase")
    try:
        info = ffprobe_info(path)
    except Exception as e:  # noqa: BLE001
        return issues + ["unreadable: %s" % e]
    if info["codec"] != "vorbis":
        issues.append("codec must be vorbis (is %s)" % info["codec"])
    if info["channels"] != 2:
        issues.append("must be stereo (is %d ch)" % info["channels"])
    if info["sample_rate"] != SR:
        issues.append("sample rate must be 44100 (is %d)" % info["sample_rate"])
    try:
        x, sr = read_ogg(path)
    except Exception as e:  # noqa: BLE001
        return issues + ["decode failed: %s" % e]
    m = measure(x, sr)
    if m["peak_db"] > peak_db + 0.01:
        issues.append("decoded peak %.2f dBFS > %.1f" % (m["peak_db"], peak_db))
    if m["peak_db"] < -12.0:
        issues.append("peak %.2f dBFS is very low" % m["peak_db"])
    if bpm and bars and loop:
        want = loop_samples(bpm, bars, beats_per_bar, SR)
        if m["samples"] != want:
            issues.append("loop length %d samples != %d (bpm %g, %d bars)" % (m["samples"], want, bpm, bars))
    return issues
