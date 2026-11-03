#!/usr/bin/env python3
"""gen_sfx.py -- every SFX of ASSET_SPEC.md section 6 for the InkPixel (수묵 wuxia) pack.

Module contract (Tools/audiogen/README.md):

    build(audio_root, tmp_dir) -> list[str]      # writes <audio_root>/Sfx/<Name>.wav

Each cue is a small function returning a float64 mono array at 44100 Hz (any level); the
mastering (mono, DC removal, trim at -60 dB, clamp to 2.0 s, 2 ms fades, peak -1 dBFS,
16-bit) is `ak.save_sfx`.  Everything is deterministic: every noise call carries an explicit
seed derived from the cue name, and the audiokit instruments seed themselves.

Sound-design language (wuxia, "chiptune-plus"):
  * menu        = zither plucks and wood-block (목탁) ticks, paper slides -- no beeps
  * coins       = metallic 엽전 clinks: two detuned high pulse tones + a noise transient
  * combat      = whooshes (band-swept noise) and thuds (sine 110->45 Hz + noise)
  * 내공/무공   = hums (sine + fifth + breath), gong/bell shimmer, dissonant detuned drones
  * steps       = short band-limited noise taps (grass soft / stone clicky / water splashy)
  * rhythm      = wood blocks at four pitches, dull block for a miss, block + bell for perfect
  * world       = gong, taiko, temple bell, 목탁, egret, wind, fire, rain, thunder, animals
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import audiokit as ak  # noqa: E402

SR = ak.SR
LOOP_INFO: dict = {}          # no music in this generator

# The ten names GPA's UI/Sound.cs loads today (must exist, in this order of importance).
GPA_NAMES = ["Accept", "Cancel", "Move1", "Slash", "Hit1", "Hit2", "Impact", "Coin", "Bonus", "Jump"]

# Every SFX of spec section 6 (GPA's ten + extras), in spec order.
SPEC_NAMES = GPA_NAMES + [
    "Hover", "Open", "Close", "Error", "Talk", "Buy", "Sell", "Equip", "Unequip",
    "Pill", "Drink", "Eat", "Read", "Heal", "Poison", "Bleed",
    "Acupoint", "Guard", "Dodge", "Crit", "Stab", "Punch", "Palm", "Kick", "Stone", "Needle",
    "Qi", "Burst", "Breakthrough", "Deviation", "Demon", "Victory", "Defeat",
    "Step1", "Step2", "Step3", "StepStone1", "StepStone2", "StepWater", "Run", "Leap", "Land",
    "Rhythm1", "Rhythm2", "Rhythm3", "Rhythm4", "RhythmMiss", "RhythmPerfect",
    "Gong", "Drum", "Bell", "Wood", "Bird", "Wind", "Fire", "Chop", "Pick", "Fish", "Door",
    "Chest", "Save", "Sleep", "Night", "Rain", "Thunder", "Horse", "Wolf", "Tiger",
]


# ==========================================================================================
# Shared helpers
# ==========================================================================================
def sd(name: str, k: int = 0) -> int:
    """Deterministic 32-bit seed from a cue name and an index (FNV-1a, no hash randomisation)."""
    h = 2166136261
    for ch in ("%s/%d" % (name, k)).encode("utf-8"):
        h ^= ch
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def N(dur: float) -> int:
    return ak.samples(dur)


def T(dur_or_n) -> np.ndarray:
    return ak.time_axis(dur_or_n)


def nz(dur: float, seed: int, color: str = "white") -> np.ndarray:
    return ak.noise(dur, color, seed=seed)


def place(*parts, tail: float = 0.0) -> np.ndarray:
    """Mix (time_s, signal[, gain]) parts into one mono buffer (length = latest end + tail)."""
    items = []
    n = 0
    for p in parts:
        t, sig = p[0], np.asarray(p[1], dtype=np.float64).reshape(-1)
        g = float(p[2]) if len(p) > 2 else 1.0
        s = N(t)
        items.append((s, sig, g))
        n = max(n, s + len(sig))
    out = np.zeros(n + N(tail))
    for s, sig, g in items:
        out[s:s + len(sig)] += sig * g
    return out


def clamp_len(x: np.ndarray, dur: float, fade: float = 0.03) -> np.ndarray:
    """Cut a long natural tail at `dur` seconds with a fade-out (keeps short signals as is)."""
    n = N(dur)
    if len(x) <= n:
        return x
    return ak.fade(x[:n], 0.0, fade)


def env_shape(points, n: int, power: float = 1.0) -> np.ndarray:
    """Breakpoint envelope [(t, v), ...] of n samples, optionally curved (v ** power)."""
    e = ak.env_points(points, n)
    return e ** power if power != 1.0 else e


def center_curve(points, n: int) -> np.ndarray:
    """Frequency trajectory through (time_s, hz) points, interpolated in the log domain."""
    t = np.arange(n) / SR
    ts = [float(p[0]) for p in points]
    lh = [math.log(float(p[1])) for p in points]
    return np.exp(np.interp(t, ts, lh))


def band_var(x: np.ndarray, center, k: float = 1.6, passes: int = 2) -> np.ndarray:
    """Moving band-pass: lowpass_var(c*k) - lowpass_var(c/k), repeated `passes` times.
    `center` = Hz scalar, (c0, c1) exponential sweep, [(t, hz), ...] or a curve array."""
    n = len(x)
    if isinstance(center, (int, float)):
        c = np.full(n, float(center))
    elif isinstance(center, tuple) and len(center) == 2 and np.isscalar(center[0]):
        c = ak.resample_len(ak.freq_curve(center[0], center[1], n / SR, "exp"), n)
    elif isinstance(center, (list, tuple)):
        c = center_curve(center, n)
    else:
        c = ak.resample_len(np.asarray(center, dtype=np.float64), n)
    hi = np.minimum(c * k, SR * 0.45)
    lo = np.maximum(c / k, 20.0)
    y = x
    for _ in range(max(1, passes)):
        y = ak.lowpass_var(y, hi) - ak.lowpass_var(y, lo)
    m = float(np.max(np.abs(y))) if len(y) else 0.0
    return y / m if m > 0 else y        # peak 1, so layer gains are predictable


def whoosh(dur: float, center, seed: int, color: str = "white", k: float = 1.5, passes: int = 2,
           peak: float = 0.15, power: float = 1.4) -> np.ndarray:
    """Band-swept noise with a swell envelope peaking at `peak` * dur (0..1)."""
    n = N(dur)
    y = band_var(nz(dur, seed, color), center, k, passes)
    env = env_shape([(0.0, 0.0), (peak * dur, 1.0), (dur, 0.0)], n, power)
    return y * env


def thud(f0: float = 110.0, f1: float = 45.0, dur: float = 0.25, tau: float = 0.07, seed: int = 1,
         noise_cut: float = 1800.0, noise_tau: float = 0.012, noise_gain: float = 0.6,
         drive: float = 1.6) -> np.ndarray:
    """Body hit: sine with an exponential pitch drop (f0 -> f1), saturated, plus a low-passed
    noise transient."""
    n = N(dur)
    body = ak.osc_sine(ak.freq_curve(f0, f1, dur, "exp")) * ak.env_decay(n, tau)
    body = ak.soft_clip(body, drive)
    burst = ak.lowpass(nz(dur, seed), noise_cut) * ak.env_decay(n, noise_tau) * noise_gain
    y = body + burst
    return y * ak.env_adsr(n, 0.001, 0.0, 1.0, min(0.05, dur * 0.3))


def click(dur: float = 0.01, cutoff: float = 6000.0, seed: int = 1, hp: float = 0.0,
          tau: float = 0.0) -> np.ndarray:
    """Short noise transient (low-passed, optionally high-passed), exponential decay."""
    n = N(dur)
    y = nz(dur, seed)
    if hp > 0:
        y = ak.highpass(y, hp)
    y = ak.lowpass(y, cutoff)
    return y * ak.env_decay(n, tau or dur / 3.0)


def snap(center: float, q: float = 1.2, dur: float = 0.04, tau: float = 0.008, seed: int = 1) -> np.ndarray:
    """Band-passed noise snap (slap / crack transient)."""
    return ak.biquad_bandpass(nz(dur, seed), center, q) * ak.env_decay(N(dur), tau)


def ring(freq: float, dur: float, tau: float, gain: float = 1.0, wave: str = "sine") -> np.ndarray:
    """A decaying partial (sine / tri / pulse)."""
    n = N(dur)
    y = {"sine": ak.osc_sine, "tri": ak.osc_tri, "saw": ak.osc_saw}.get(wave, ak.osc_sine)(freq, dur)
    return y * ak.env_decay(n, tau) * gain


def glide_pluck(f0: float, f1: float, dur: float = 0.3, glide: float = 0.12, bright: float = 0.6,
                seed: int = 1) -> np.ndarray:
    """String-like pluck whose pitch glides f0 -> f1 (used for 'descending pluck' cues)."""
    n = N(dur)
    t = T(n)
    f = ak.portamento(f0, f1, dur, glide, "exp")
    y = (ak.osc_sine(f) * np.exp(-t / 0.18)
         + ak.osc_sine(f * 2.003) * 0.5 * np.exp(-t / 0.08)
         + ak.osc_sine(f * 2.997) * 0.3 * bright * np.exp(-t / 0.04)
         + ak.osc_tri(f * 4.0) * 0.15 * bright * np.exp(-t / 0.02))
    pick = click(0.012, 6000.0, seed) * 0.4
    y = ak.mix(y, pick)
    return y * ak.env_adsr(n, 0.001, 0.0, 1.0, min(0.05, dur * 0.3))


def zpluck(note: str, dur: float = 0.08, vel: float = 1.0, bright: float = 0.7,
           release: float = 0.4) -> np.ndarray:
    """Zither pluck by note name (natural ring kept; callers clamp the cue length)."""
    return ak.zither(ak.note_freq(note), dur, vel, bright=bright, release=release)


def coin_clink(seed: int, f: float = 2480.0, detune: float = 1.021, tau: float = 0.055,
               dur: float = 0.2) -> np.ndarray:
    """엽전 clink: two detuned high pulse tones (beating) + an upper partial + a noise tick."""
    n = N(dur)
    t = T(n)
    a = ak.osc_pulse(f, dur, 0.5) * np.exp(-t / tau)
    b = ak.osc_pulse(f * detune, dur, 0.5, phase=0.3) * np.exp(-t / (tau * 0.85))
    c = ak.osc_sine(f * 1.58, dur) * np.exp(-t / (tau * 0.5)) * 0.5
    y = ak.lowpass((a + b) * 0.5 + c, 10000.0)
    y = ak.mix(y, click(0.004, 9000.0, seed, hp=1500.0) * 0.8)
    return y * ak.env_adsr(n, 0.0005, 0.0, 1.0, 0.03)


def grass_tap(seed: int, center: float = 750.0, dur: float = 0.09, tau: float = 0.022) -> np.ndarray:
    """Soft footstep on grass: band-limited pink noise with a tiny second crunch."""
    n = N(dur)
    y = ak.biquad_bandpass(nz(dur, seed, "pink"), center, 0.8)
    y = ak.lowpass(y, 2500.0)
    env = env_shape([(0.0, 0.0), (0.004, 1.0), (dur, 0.0)], n, 1.0) * ak.env_decay(n, tau)
    crunch = ak.lowpass(nz(0.03, seed + 1), 1800.0, order=2) * ak.env_decay(N(0.03), 0.006)
    return ak.mix(y * env, place((0.018, crunch, 0.3)))


def stone_tap(seed: int, tick_hz: float = 1900.0, dur: float = 0.07) -> np.ndarray:
    """Footstep on stone: clicky high-passed noise, a short stone 'tick' partial and a small
    sole thump."""
    n = N(dur)
    y = ak.lowpass(ak.highpass(nz(dur, seed), 1500.0), 7000.0) * ak.env_decay(n, 0.008)
    tick = ring(tick_hz, dur, 0.01, 0.35)
    thump = ak.osc_sine(ak.freq_curve(180.0, 90.0, 0.05, "exp")) * ak.env_decay(N(0.05), 0.012) * 0.35
    return ak.mix(y, tick, thump)


def gulp(seed: int, f0: float = 280.0, f1: float = 130.0, dur: float = 0.14) -> np.ndarray:
    """Swallow: descending low sine + low-passed liquid noise + a tiny rising bubble blip."""
    n = N(dur)
    tone = ak.osc_sine(ak.freq_curve(f0, f1, dur, "exp")) * env_shape([(0, 0), (0.01, 1), (dur, 0)], n, 1.5)
    liquid = ak.lowpass(nz(dur, seed), 600.0) * ak.env_decay(n, 0.04) * 0.6
    blip = ak.osc_sine(ak.freq_curve(800.0, 1500.0, 0.03, "exp")) * ak.env_decay(N(0.03), 0.01) * 0.2
    return place((0.0, tone), (0.0, liquid), (0.04, blip))


def creak(dur: float, f0: float, f1: float, seed: int, rough_hz: float = 22.0, cutoff: float = 1200.0) -> np.ndarray:
    """Wood creak: sawtooth with a wobbling glide, stick-slip amplitude roughness, resonant LPF."""
    n = N(dur)
    t = T(n)
    f = ak.vibrato(ak.freq_curve(f0, f1, dur, "exp"), None, 7.0, 0.5, onset=0.0, ramp=0.05)
    y = ak.osc_saw(f) * (0.65 + 0.35 * np.sign(np.sin(2.0 * math.pi * rough_hz * t + 0.3)))
    y = ak.biquad_lowpass(y, cutoff, 2.0)
    bow = ak.biquad_bandpass(nz(dur, seed), cutoff * 1.5, 1.0) * 0.25
    y = y + bow
    return y * env_shape([(0, 0), (0.08, 1), (dur - 0.05, 0.9), (dur, 0)], n, 1.0)


def bubble(f0: float, f1: float, dur: float = 0.03, tau: float = 0.012, gain: float = 0.3) -> np.ndarray:
    return ak.osc_sine(ak.freq_curve(f0, f1, dur, "exp")) * ak.env_decay(N(dur), tau) * gain


def rumble(dur: float, seed: int, cutoff: float = 120.0, order: int = 2) -> np.ndarray:
    """Brown noise rumble, band-limited to 30 Hz .. cutoff (no sub-sonic wander)."""
    y = ak.lowpass(nz(dur, seed, "brown"), cutoff, order=order)
    y = ak.highpass(y, 30.0, order=2)
    m = float(np.max(np.abs(y))) if len(y) else 0.0
    return y / m if m > 0 else y


# ==========================================================================================
# Menu / UI
# ==========================================================================================
def sfx_accept() -> np.ndarray:
    """Confirm: two rising zither plucks (G5 -> C6), tight 0.35 s."""
    a = zpluck("G5", 0.06, 0.85)
    b = zpluck("C6", 0.08, 1.0)
    return clamp_len(place((0.0, a), (0.075, b)), 0.36, 0.08)


def sfx_cancel() -> np.ndarray:
    """Back / miss: one low wood block + a short descending pluck (A4 -> E4)."""
    block = ak.wood_block(520.0, 1.0, 0.1)
    pl = glide_pluck(440.0, 330.0, 0.28, 0.1, 0.5, sd("Cancel"))
    return place((0.0, block), (0.03, pl, 0.9))


def sfx_move1() -> np.ndarray:
    """Cursor move / dialogue advance: a soft wood tick (50 ms)."""
    y = ak.wood_block(1400.0, 0.7, 0.05)
    return ak.lowpass(y, 6500.0)


def sfx_hover() -> np.ndarray:
    """Hover: a very soft, thin tick (30 ms, high-passed so it reads quieter than Move1)."""
    y = ak.wood_block(2000.0, 0.5, 0.03)
    return ak.highpass(y, 900.0)


def sfx_open() -> np.ndarray:
    """Panel open: rising paper-slide noise sweep + a soft settle tick at the end."""
    slide = whoosh(0.28, (800.0, 3600.0), sd("Open"), "pink", k=1.7, passes=2, peak=0.35, power=1.2)
    tick = ak.wood_block(950.0, 0.4, 0.05)
    return place((0.0, slide), (0.25, tick, 0.5))


def sfx_close() -> np.ndarray:
    """Panel close: falling paper-slide sweep ending in a soft knock."""
    slide = whoosh(0.25, (3600.0, 700.0), sd("Close"), "pink", k=1.7, passes=2, peak=0.3, power=1.2)
    knock = ak.mix(ak.wood_block(500.0, 0.6, 0.07), thud(170.0, 70.0, 0.1, 0.025, sd("Close", 1), 1200.0, 0.008, 0.4, 1.3) * 0.6)
    return place((0.0, slide), (0.21, knock, 0.8))


def sfx_error() -> np.ndarray:
    """Invalid action: a low dissonant pluck pair (A3 + Bb3, a semitone apart)."""
    a = zpluck("A3", 0.12, 1.0, 0.5, 0.35)
    b = zpluck("A#3", 0.12, 0.9, 0.5, 0.35)
    return clamp_len(place((0.0, a), (0.018, b)), 0.45, 0.1)


def sfx_talk() -> np.ndarray:
    """Text blip: a 30 ms muted zither pluck."""
    y = ak.lowpass(zpluck("C5", 0.03, 1.0, 0.3), 3000.0)
    return clamp_len(y, 0.03, 0.008)


# ==========================================================================================
# Money / inventory
# ==========================================================================================
def sfx_coin() -> np.ndarray:
    """엽전 clink: main clink + a softer, slightly higher second coin 70 ms later."""
    a = coin_clink(sd("Coin"))
    b = coin_clink(sd("Coin", 1), f=2650.0, tau=0.045, dur=0.16)
    return place((0.0, a), (0.07, b, 0.55))


def sfx_bonus() -> np.ndarray:
    """Reward jingle: three rising zither notes (G5 C6 E6) + a bell on the top note."""
    notes = [("G5", 0.0, 0.8), ("C6", 0.07, 0.9), ("E6", 0.14, 1.0)]
    parts = [(t, zpluck(nm, 0.07, v, 0.8, 0.3)) for nm, t, v in notes]
    parts.append((0.14, ak.bell(ak.note_freq("E6"), 0.08, 0.8, release=0.45), 0.55))
    return clamp_len(place(*parts), 0.7, 0.15)


def sfx_buy() -> np.ndarray:
    """Purchase: clink + a light rising pluck pair (E5 -> A5)."""
    y = place((0.0, coin_clink(sd("Buy"), tau=0.045)),
              (0.07, zpluck("E5", 0.05, 0.7, 0.6, 0.3)),
              (0.15, zpluck("A5", 0.06, 0.85, 0.6, 0.3)))
    return clamp_len(y, 0.45, 0.1)


def sfx_sell() -> np.ndarray:
    """Sale: clink + a falling pluck pair (A5 -> E5)."""
    y = place((0.0, coin_clink(sd("Sell"), f=2300.0, tau=0.045)),
              (0.07, zpluck("A5", 0.05, 0.85, 0.6, 0.3)),
              (0.15, zpluck("E5", 0.06, 0.7, 0.6, 0.3)))
    return clamp_len(y, 0.45, 0.1)


def sfx_equip() -> np.ndarray:
    """Equip: cloth rustle then a bright metallic 'shing' (rising zip + two high partials)."""
    rustle = ak.biquad_bandpass(nz(0.14, sd("Equip"), "pink"), 2500.0, 0.7) * ak.env_decay(N(0.14), 0.045)
    zip_ = whoosh(0.09, (3000.0, 7500.0), sd("Equip", 1), k=1.3, passes=2, peak=0.5, power=1.0)
    shine = ak.mix(ring(4200.0, 0.3, 0.07, 0.6), ring(6300.0, 0.3, 0.05, 0.35), ring(4200.0 * 1.013, 0.3, 0.06, 0.4))
    return place((0.0, rustle, 0.8), (0.05, zip_, 0.5), (0.07, shine, 0.9), (0.07, click(0.004, 9000.0, sd("Equip", 2)), 0.5))


def sfx_unequip() -> np.ndarray:
    """Unequip: lower rustle, a small descending tone and a dull wooden click/thud."""
    rustle = ak.biquad_bandpass(nz(0.14, sd("Unequip"), "pink"), 1800.0, 0.7) * ak.env_decay(N(0.14), 0.045)
    down = ak.osc_sine(ak.freq_curve(900.0, 450.0, 0.08, "exp")) * ak.env_decay(N(0.08), 0.03) * 0.3
    knock = ak.mix(ak.wood_block(600.0, 0.6, 0.07), thud(180.0, 90.0, 0.09, 0.02, sd("Unequip", 1), 1500.0, 0.008, 0.4, 1.3) * 0.6)
    return place((0.0, rustle, 0.8), (0.03, down), (0.09, knock, 0.9))


# ==========================================================================================
# Consumables / status
# ==========================================================================================
def sfx_pill() -> np.ndarray:
    """Take a pill: tiny pop then one swallow."""
    pop = ak.mix(click(0.006, 7000.0, sd("Pill")), ring(1500.0, 0.04, 0.012, 0.5))
    return place((0.0, pop), (0.06, gulp(sd("Pill", 1), 320.0, 140.0, 0.12), 0.8))


def sfx_drink() -> np.ndarray:
    """Drink: two gulps."""
    return place((0.0, gulp(sd("Drink"), 280.0, 130.0)), (0.18, gulp(sd("Drink", 1), 260.0, 120.0), 0.85))


def sfx_eat() -> np.ndarray:
    """Eat: three crunches (each a low-passed noise burst + band crunch + a soft thump)."""
    parts = []
    for i, (t, cut, gain) in enumerate([(0.0, 3200.0, 1.0), (0.12, 2600.0, 0.85), (0.25, 2200.0, 0.75)]):
        n = N(0.08)
        burst = ak.lowpass(nz(0.08, sd("Eat", i)), cut, order=2) * ak.env_decay(n, 0.018)
        crunch = ak.biquad_bandpass(nz(0.08, sd("Eat", 10 + i)), 1200.0, 1.0) * ak.env_decay(n, 0.01) * 0.6
        bump = ak.osc_sine(150.0, 0.05) * ak.env_decay(N(0.05), 0.012) * 0.3
        parts.append((t, ak.mix(burst, crunch, bump), gain))
    return place(*parts)


def sfx_read() -> np.ndarray:
    """Read a manual: two paper swipes (rising, then falling band sweep) and a page-set tick."""
    s1 = whoosh(0.16, (1500.0, 4200.0), sd("Read"), "pink", k=1.8, passes=1, peak=0.4, power=1.2)
    s2 = whoosh(0.2, (3600.0, 1400.0), sd("Read", 1), "pink", k=1.8, passes=1, peak=0.35, power=1.2)
    tick = ak.wood_block(1500.0, 0.3, 0.04)
    return place((0.0, s1), (0.2, s2, 0.9), (0.4, tick, 0.3))


def sfx_heal() -> np.ndarray:
    """Heal: rising bell arpeggio (C5 E5 G5) under a soft rising shimmer."""
    parts = [(t, ak.bell(ak.note_freq(nm), 0.1, v, release=0.5)) for nm, t, v in [("C5", 0.0, 0.6), ("E5", 0.09, 0.7), ("G5", 0.18, 0.8)]]
    n = N(0.55)
    shimmer = ak.osc_sine(ak.freq_curve(1046.5, 2093.0, 0.55, "exp")) * env_shape([(0, 0), (0.25, 1), (0.55, 0)], n, 1.5) * 0.18
    parts.append((0.05, shimmer))
    return clamp_len(ak.lowpass(place(*parts), 8000.0), 0.7, 0.15)


def sfx_poison() -> np.ndarray:
    """Poison: bubbling blips drifting downward over a plum-dark tritone tone."""
    parts = []
    for i, (t, f) in enumerate([(0.0, 950.0), (0.09, 880.0), (0.21, 760.0), (0.3, 700.0), (0.42, 600.0)]):
        parts.append((t, bubble(f * 0.4, f, 0.035, 0.014, 0.6 - 0.05 * i)))
    n = N(0.6)
    dark = (ak.osc_sine(98.0, 0.6) + ak.osc_sine(138.6, 0.6) * 0.7 + ak.osc_tri(49.0, 0.6) * 0.3) * env_shape([(0, 0), (0.1, 1), (0.4, 0.8), (0.6, 0)], n, 1.2) * 0.35
    parts.append((0.0, dark))
    return place(*parts)


def sfx_bleed() -> np.ndarray:
    """Bleed: a wet burst and a falling drip blip."""
    n = N(0.12)
    wet = ak.biquad_bandpass(nz(0.12, sd("Bleed")), 700.0, 1.0) * ak.env_decay(n, 0.03)
    wet = ak.mix(wet, ak.lowpass(nz(0.12, sd("Bleed", 1)), 2000.0) * ak.env_decay(n, 0.015) * 0.6)
    drip = ak.osc_sine(ak.freq_curve(1100.0, 500.0, 0.07, "exp")) * ak.env_decay(N(0.07), 0.025) * 0.5
    return place((0.0, wet), (0.05, drip), tail=0.1)


# ==========================================================================================
# Combat
# ==========================================================================================
def sfx_slash() -> np.ndarray:
    """Sword swing: fast downward noise whoosh (4 kHz -> 700 Hz) with a thin steel ring at the start."""
    w = whoosh(0.22, (4000.0, 700.0), sd("Slash"), k=1.4, passes=2, peak=0.12, power=1.2)
    edge = ak.mix(ring(5200.0, 0.1, 0.03, 0.25), ring(7800.0, 0.1, 0.02, 0.15))
    return place((0.0, w), (0.0, edge))


def sfx_hit1() -> np.ndarray:
    """Flesh hit: thud 120 -> 45 Hz + slap transient."""
    return ak.mix(thud(120.0, 45.0, 0.18, 0.05, sd("Hit1"), 2200.0, 0.012, 0.7, 1.8),
                  snap(900.0, 1.5, 0.04, 0.01, sd("Hit1", 1)) * 0.5)


def sfx_hit2() -> np.ndarray:
    """Flesh hit variant: slightly higher and snappier (150 -> 55 Hz)."""
    return ak.mix(thud(150.0, 55.0, 0.16, 0.045, sd("Hit2"), 3000.0, 0.01, 0.7, 1.6),
                  snap(1400.0, 1.5, 0.04, 0.008, sd("Hit2", 1)) * 0.5)


def sfx_impact() -> np.ndarray:
    """Heavy hit / crit / KO: deep saturated thud (90 -> 32 Hz), sub rumble and a crack."""
    body = thud(90.0, 32.0, 0.4, 0.11, sd("Impact"), 1500.0, 0.02, 0.6, 2.5)
    sub = rumble(0.4, sd("Impact", 1), 120.0) * ak.env_decay(N(0.4), 0.12) * 0.5
    crack = snap(2500.0, 1.0, 0.05, 0.006, sd("Impact", 2)) * 0.5
    return ak.mix(body, sub, crack)


def sfx_punch() -> np.ndarray:
    """권법: tight thud with a mid snap."""
    return ak.mix(thud(140.0, 60.0, 0.14, 0.035, sd("Punch"), 2000.0, 0.01, 0.6, 1.8),
                  snap(1800.0, 1.2, 0.04, 0.008, sd("Punch", 1)) * 0.7)


def sfx_palm() -> np.ndarray:
    """장법: broad 'whump' -- short air push, then a soft wide thud with a long low-passed air tail."""
    push = whoosh(0.1, (1500.0, 500.0), sd("Palm"), k=1.6, passes=2, peak=0.3, power=1.0)
    body = thud(130.0, 50.0, 0.3, 0.08, sd("Palm", 1), 1200.0, 0.02, 0.5, 1.4)
    n = N(0.3)
    air = ak.lowpass(nz(0.3, sd("Palm", 2), "pink"), 900.0) * env_shape([(0, 0), (0.01, 1), (0.3, 0)], n, 1.0) * ak.env_decay(n, 0.06) * 0.8
    return place((0.0, push, 0.6), (0.04, body), (0.04, air))


def sfx_kick() -> np.ndarray:
    """각법: short whoosh then a heavy thud with a snap."""
    w = whoosh(0.09, (2500.0, 800.0), sd("Kick"), k=1.5, passes=2, peak=0.3, power=1.0)
    body = thud(110.0, 40.0, 0.22, 0.06, sd("Kick", 1), 1800.0, 0.012, 0.6, 2.0)
    sn = snap(1500.0, 1.2, 0.04, 0.008, sd("Kick", 2)) * 0.6
    return place((0.0, w, 0.7), (0.07, body), (0.07, sn))


def sfx_stab() -> np.ndarray:
    """Stab: short bright zip (2.5 -> 6 kHz), a sharp click and a small thud."""
    zip_ = whoosh(0.05, (2500.0, 6000.0), sd("Stab"), k=1.3, passes=2, peak=0.5, power=1.0)
    clk = click(0.006, 9000.0, sd("Stab", 1), hp=2000.0)
    body = thud(260.0, 110.0, 0.06, 0.015, sd("Stab", 2), 2500.0, 0.006, 0.5, 1.5)
    return place((0.0, zip_), (0.04, clk, 0.9), (0.045, body, 0.35))


def sfx_crit() -> np.ndarray:
    """Critical: impact thud + a gong-like shimmer blooming behind it (1.1 s)."""
    body = thud(100.0, 35.0, 0.35, 0.1, sd("Crit"), 1500.0, 0.02, 0.6, 2.3)
    g = ak.gong(1.1, 1.0, 150.0, shimmer=0.8)
    crack = snap(2500.0, 1.0, 0.05, 0.006, sd("Crit", 1)) * 0.5
    return clamp_len(place((0.0, body), (0.01, g, 0.7), (0.0, crack)), 1.1, 0.15)


def sfx_guard() -> np.ndarray:
    """Guard: a short jade bell 'ting' (A6 bell + E7 partial) with a metallic click."""
    b = ak.bell(1760.0, 0.05, 1.0, release=0.3)
    hi = ring(2637.0, 0.25, 0.04, 0.3)
    clk = click(0.005, 10000.0, sd("Guard"), hp=2500.0) * 0.6
    return clamp_len(place((0.0, b), (0.0, hi), (0.0, clk)), 0.35, 0.08)


def sfx_dodge() -> np.ndarray:
    """Dodge: airy rise-then-fall pink whoosh, no impact."""
    return whoosh(0.3, [(0.0, 700.0), (0.12, 2400.0), (0.3, 900.0)], sd("Dodge"), "pink", k=1.5, passes=2, peak=0.35, power=1.3)


def sfx_acupoint() -> np.ndarray:
    """점혈: a short high click followed by a crisp tone (G6 + D7)."""
    clk = click(0.004, 8000.0, sd("Acupoint"), hp=1500.0)
    tone = ak.mix(ring(1568.0, 0.2, 0.06, 1.0), ring(2349.0, 0.2, 0.03, 0.4))
    return place((0.0, clk), (0.004, tone, 0.9))


def sfx_needle() -> np.ndarray:
    """암기 needle: fast rising zip (3 -> 9 kHz), a thin metallic partial and a tiny whoosh."""
    zip_ = whoosh(0.07, (3000.0, 9000.0), sd("Needle"), k=1.3, passes=2, peak=0.4, power=1.0)
    w = whoosh(0.15, (1500.0, 4000.0), sd("Needle", 1), "pink", k=1.5, passes=2, peak=0.3, power=1.2)
    metal = ring(6000.0, 0.1, 0.02, 0.3)
    return place((0.0, zip_), (0.0, w, 0.5), (0.0, metal))


def sfx_stone() -> np.ndarray:
    """투석 stone: sling release zip then a lower descending whoosh."""
    zip_ = whoosh(0.06, (1200.0, 3500.0), sd("Stone"), k=1.4, passes=2, peak=0.4, power=1.0)
    w = whoosh(0.24, (2000.0, 500.0), sd("Stone", 1), "pink", k=1.5, passes=2, peak=0.2, power=1.2)
    return place((0.0, zip_, 0.8), (0.03, w))


# ==========================================================================================
# Inner power / martial events
# ==========================================================================================
def sfx_qi() -> np.ndarray:
    """운기 hum: sine G3 + fifth D4 + octave + sub, slow 0.45 s swell, breath noise, light room."""
    dur = 0.85
    n = N(dur)
    env = env_shape([(0, 0), (0.45, 1.0), (0.6, 0.95), (dur, 0)], n, 1.6)
    f = ak.vibrato(196.0, dur, 5.0, 0.1, onset=0.3, ramp=0.2)
    y = (ak.osc_sine(f) + ak.osc_sine(f * 1.5) * 0.6 + ak.osc_sine(f * 2.0) * 0.3 + ak.osc_tri(f * 0.5) * 0.3)
    breath = ak.biquad_bandpass(nz(dur, sd("Qi"), "pink"), 1200.0, 1.0) * 0.25
    y = (y + breath) * env
    return clamp_len(ak.reverb(y, 0.6, 0.15, damp=0.6), 0.95, 0.1)


def sfx_burst() -> np.ndarray:
    """절초 flash: reversed-envelope rising noise (0.3 s) into a snap, a deep thud, a bright
    decaying saw tone and a sparkle tail."""
    n = N(0.3)
    rev = band_var(nz(0.3, sd("Burst")), (600.0, 4000.0), 1.6, 2) * env_shape([(0, 0.12), (0.3, 1)], n, 2.5)
    snp = ak.mix(click(0.01, 9000.0, sd("Burst", 1)), snap(3000.0, 0.8, 0.04, 0.006, sd("Burst", 2)))
    body = thud(180.0, 60.0, 0.15, 0.04, sd("Burst", 3), 1500.0, 0.01, 0.4, 2.0)
    tone = ak.lowpass(ak.osc_saw(880.0, 0.25), 4000.0) * ak.env_decay(N(0.25), 0.07) * 0.5
    spark = ak.highpass(nz(0.3, sd("Burst", 4)), 5000.0) * ak.env_decay(N(0.3), 0.08) * 0.4
    return place((0.0, rev, 0.8), (0.3, snp), (0.3, body), (0.3, tone), (0.3, spark))


def sfx_breakthrough() -> np.ndarray:
    """경지 돌파: gong + a rising shimmer (sine sweep 440 -> 1760 Hz with sparkle) capped by a bell."""
    g = ak.gong(1.6, 1.0, 104.0, shimmer=0.7)
    n = N(1.25)
    f = ak.freq_curve(440.0, 1760.0, 1.25, "exp")
    env = env_shape([(0, 0), (0.45, 0.8), (0.95, 1.0), (1.25, 0)], n, 1.3)
    rise = (ak.osc_sine(f) + ak.osc_sine(f * 2.0) * 0.4 + ak.osc_sine(f * 3.0) * 0.15) * env * 0.5
    spark = ak.highpass(nz(1.25, sd("Breakthrough")), 6000.0) * env * 0.25
    bell_ = ak.bell(1318.5, 0.1, 0.8, release=0.6)
    y = place((0.0, g), (0.05, rise), (0.05, spark), (1.05, bell_, 0.6))
    return clamp_len(y, 1.7, 0.2)


def sfx_deviation() -> np.ndarray:
    """주화입마: three detuned saws (±half-semitone) sliding A3 -> A2 under a tritone sine, resonant
    low-pass and a 6 Hz wobble."""
    dur = 1.0
    n = N(dur)
    t = T(n)
    f = ak.freq_curve(220.0, 110.0, dur, "exp")
    y = (ak.osc_saw(f) + ak.osc_saw(f * 1.03, phase=0.2) + ak.osc_saw(f * 0.97, phase=0.5)) / 3.0
    y = ak.biquad_lowpass(y, 900.0, 1.2)
    tri_ = ak.osc_sine(f * 1.4142) * 0.3
    wob = 1.0 - 0.3 * (0.5 + 0.5 * np.sin(2.0 * math.pi * 6.0 * t))
    y = (y + tri_) * wob
    # the static low-pass lets the saws through more as they slide down: compensate so the
    # drone starts strong and sinks, instead of swelling
    comp = env_shape([(0, 1.0), (dur, 0.55)], n, 1.0)
    return y * comp * env_shape([(0, 0), (0.05, 1), (0.8, 0.9), (dur, 0)], n, 1.2)


def sfx_demon() -> np.ndarray:
    """심마: low growl (brown noise, 28 Hz amplitude roughness) + plum-dark dissonant tone
    (A2 + tritone + a semitone-beating partner), with a short dark room."""
    dur = 0.95
    n = N(dur)
    t = T(n)
    growl_am = 0.2 + 0.8 * (0.5 + 0.5 * np.sin(2.0 * math.pi * 28.0 * t))
    growl = rumble(dur, sd("Demon"), 400.0, 1) * growl_am
    tone = (ak.osc_sine(110.0, dur) + ak.osc_sine(155.6, dur) * 0.7 + ak.osc_sine(116.5, dur) * 0.5 + ak.osc_tri(55.0, dur) * 0.4)
    tone = ak.lowpass(tone, 1500.0) * 0.5
    env = env_shape([(0, 0), (0.15, 1), (0.6, 0.85), (dur, 0)], n, 1.3)
    y = (growl + tone) * env
    return clamp_len(ak.reverb(y, 0.8, 0.18, damp=0.8), 1.0, 0.15)


def sfx_victory() -> np.ndarray:
    """Victory: zither fanfare C5 E5 G5 C6 landing on a gong (1.3 s)."""
    notes = [("C5", 0.0, 0.8), ("E5", 0.11, 0.85), ("G5", 0.22, 0.9), ("C6", 0.33, 1.0)]
    parts = [(t, zpluck(nm, 0.1, v, 0.8, 0.5)) for nm, t, v in notes]
    parts.append((0.33, ak.gong(1.0, 1.0, 120.0, shimmer=0.6), 0.8))
    parts.append((0.33, ak.bell(ak.note_freq("C6"), 0.1, 0.7, release=0.6), 0.4))
    return clamp_len(place(*parts), 1.3, 0.15)


def sfx_defeat() -> np.ndarray:
    """Defeat: slow descending flute (E5 -> C5 -> A4, minor pentatonic) fading into a room."""
    parts = [(0.0, ak.flute(ak.note_freq("E5"), 0.4, 0.9, breath=0.4)),
             (0.42, ak.flute(ak.note_freq("C5"), 0.4, 0.8, breath=0.4)),
             (0.84, ak.flute(ak.note_freq("A4"), 0.55, 0.7, breath=0.45))]
    y = place(*parts)
    y = ak.reverb(y, 1.0, 0.2, damp=0.6)
    return clamp_len(y, 1.55, 0.2)


# ==========================================================================================
# Movement
# ==========================================================================================
def sfx_step1() -> np.ndarray:
    return grass_tap(sd("Step1"), 750.0, 0.09, 0.022)


def sfx_step2() -> np.ndarray:
    return grass_tap(sd("Step2"), 880.0, 0.085, 0.02)


def sfx_step3() -> np.ndarray:
    return grass_tap(sd("Step3"), 640.0, 0.095, 0.024)


def sfx_step_stone1() -> np.ndarray:
    return stone_tap(sd("StepStone1"), 1900.0, 0.07)


def sfx_step_stone2() -> np.ndarray:
    return stone_tap(sd("StepStone2"), 2300.0, 0.065)


def sfx_step_water() -> np.ndarray:
    """Wading step: band-passed splash + two rising bubble blips."""
    n = N(0.16)
    sp = ak.biquad_bandpass(nz(0.16, sd("StepWater")), 3500.0, 0.7) * env_shape([(0, 0), (0.01, 1), (0.16, 0)], n, 1.0) * ak.env_decay(n, 0.05)
    return place((0.0, sp), (0.03, bubble(600.0, 1200.0)), (0.07, bubble(900.0, 1500.0, gain=0.25)))


def sfx_run() -> np.ndarray:
    """Run: two quick grass taps 100 ms apart."""
    return place((0.0, grass_tap(sd("Run"), 760.0)), (0.1, grass_tap(sd("Run", 1), 820.0), 0.9))


def sfx_leap() -> np.ndarray:
    """경공 leap: long airy rising whoosh (300 -> 2200 Hz) with a slow swell."""
    return whoosh(0.45, (300.0, 2200.0), sd("Leap"), "pink", k=1.5, passes=2, peak=0.45, power=1.3)


def sfx_jump() -> np.ndarray:
    """Jump (map travel): rising whoosh (500 -> 2800 Hz) with a subtle rising tone."""
    w = whoosh(0.32, (500.0, 2800.0), sd("Jump"), k=1.5, passes=2, peak=0.4, power=1.3)
    n = N(0.26)
    tone = (ak.osc_sine(ak.freq_curve(300.0, 800.0, 0.26, "exp")) + ak.osc_tri(ak.freq_curve(300.0, 800.0, 0.26, "exp")) * 0.4) * env_shape([(0, 0), (0.08, 1), (0.26, 0)], n, 1.5) * 0.22
    return place((0.0, w), (0.02, tone))


def sfx_land() -> np.ndarray:
    """Land: soft thud (120 -> 50 Hz) with a dust puff."""
    body = thud(120.0, 50.0, 0.16, 0.04, sd("Land"), 1200.0, 0.01, 0.5, 1.4)
    dust = ak.lowpass(nz(0.12, sd("Land", 1), "pink"), 1500.0) * ak.env_decay(N(0.12), 0.03) * 0.5
    return ak.mix(body, dust)


# ==========================================================================================
# 초식 연마 rhythm lanes
# ==========================================================================================
RHYTHM_NOTES = ("G4", "B4", "D5", "G5")


def _rhythm(i: int) -> np.ndarray:
    return ak.wood_block(ak.note_freq(RHYTHM_NOTES[i]), 1.0, 0.12)


def sfx_rhythm1() -> np.ndarray:
    return _rhythm(0)


def sfx_rhythm2() -> np.ndarray:
    return _rhythm(1)


def sfx_rhythm3() -> np.ndarray:
    return _rhythm(2)


def sfx_rhythm4() -> np.ndarray:
    return _rhythm(3)


def sfx_rhythm_miss() -> np.ndarray:
    """Miss: a dull low block (240 Hz, low-passed) with a flat thump."""
    blk = ak.lowpass(ak.wood_block(240.0, 1.0, 0.16), 900.0)
    bump = ak.osc_sine(ak.freq_curve(160.0, 90.0, 0.12, "exp")) * ak.env_decay(N(0.12), 0.03) * 0.5
    return ak.mix(blk, bump)


def sfx_rhythm_perfect() -> np.ndarray:
    """Perfect: bright block (G5) + a tiny bell (E7)."""
    blk = ak.wood_block(ak.note_freq("G5"), 1.0, 0.12)
    b = ak.bell(2637.0, 0.05, 0.7, release=0.35)
    return clamp_len(place((0.0, blk), (0.01, b, 0.5)), 0.4, 0.08)


# ==========================================================================================
# World / ambience / animals
# ==========================================================================================
def sfx_gong() -> np.ndarray:
    return ak.gong(2.0, 1.0, 92.0, shimmer=0.6)


def sfx_drum() -> np.ndarray:
    return ak.taiko("low", 1.0, 0.7)


def sfx_bell() -> np.ndarray:
    return ak.temple_bell(196.0, 2.0, 1.0)


def sfx_wood() -> np.ndarray:
    """목탁: tok tok."""
    return place((0.0, ak.wood_block(700.0, 1.0, 0.11)), (0.17, ak.wood_block(700.0, 0.85, 0.11)))


def _egret_note(f0: float, f1: float, dur: float, seed: int) -> np.ndarray:
    n = N(dur)
    f = ak.vibrato(ak.freq_curve(f0, f1, dur, "exp"), None, 28.0, 0.25, onset=0.0, ramp=0.02)
    tone = ak.osc_sine(f) + ak.osc_sine(f * 2.0) * 0.4 + ak.osc_sine(f * 3.0) * 0.15
    air = band_var(nz(dur, seed), f, 1.25, 2) * 0.6
    env = env_shape([(0, 0), (0.015, 1), (dur - 0.04, 0.8), (dur, 0)], n, 1.0)
    return (tone + air) * env


def sfx_bird() -> np.ndarray:
    """Egret: a two-note airy call (1.9 -> 1.5 kHz, then 1.6 -> 1.25 kHz), slightly distant."""
    y = place((0.0, _egret_note(1900.0, 1500.0, 0.13, sd("Bird"))),
              (0.2, _egret_note(1600.0, 1250.0, 0.17, sd("Bird", 1)), 0.9))
    return clamp_len(ak.reverb(y, 0.5, 0.15, damp=0.5), 0.5, 0.1)


def sfx_wind() -> np.ndarray:
    """Wind: 1.2 s pink-noise swell whose band centre rises then falls (300 -> 1000 -> 400 Hz)."""
    dur = 1.2
    n = N(dur)
    y = band_var(nz(dur, sd("Wind"), "pink"), [(0.0, 300.0), (0.55, 1000.0), (dur, 400.0)], 1.8, 2)
    env = env_shape([(0, 0), (0.5, 1), (0.8, 0.85), (dur, 0)], n, 1.3)
    air = ak.highpass(nz(dur, sd("Wind", 1)), 2500.0) * 0.08
    return (y + air) * env


def sfx_fire() -> np.ndarray:
    """Fire: low flame bed with slow flicker, a mid hiss and ~18 sparse crackles (1 s)."""
    dur = 1.0
    n = N(dur)
    rng = np.random.default_rng(sd("Fire"))
    flicker = 0.6 + 0.4 * ak.lowpass(nz(dur, sd("Fire", 1)), 8.0) / 0.05
    flicker = np.clip(flicker, 0.2, 1.4)
    bed = rumble(dur, sd("Fire", 2), 250.0, 2) * flicker * 0.5
    hiss = ak.biquad_bandpass(nz(dur, sd("Fire", 3), "pink"), 1500.0, 0.6) * (0.5 + 0.5 * flicker) * 0.25
    parts = [(0.0, bed), (0.0, hiss)]
    for i in range(18):
        t = float(rng.uniform(0.0, dur - 0.02))
        d = float(rng.uniform(0.003, 0.012))
        cut = float(rng.uniform(2500.0, 7000.0))
        parts.append((t, click(d, cut, sd("Fire", 10 + i), hp=800.0), float(rng.uniform(0.35, 1.0))))
    y = place(*parts)
    return y[:n] * env_shape([(0, 0), (0.03, 1), (dur - 0.08, 1), (dur, 0)], n, 1.0)


def sfx_chop() -> np.ndarray:
    """Chop wood: short axe whoosh, then a wood knock + thud + crack."""
    w = whoosh(0.07, (1800.0, 600.0), sd("Chop"), k=1.5, passes=2, peak=0.3, power=1.0)
    hit = ak.mix(thud(210.0, 90.0, 0.12, 0.03, sd("Chop", 1), 1800.0, 0.008, 0.5, 1.8),
                 ak.wood_block(420.0, 1.0, 0.1) * 0.7,
                 snap(3000.0, 0.8, 0.04, 0.006, sd("Chop", 2)) * 0.7)
    return place((0.0, w, 0.6), (0.06, hit))


def sfx_pick() -> np.ndarray:
    """Pick herbs: two leafy rustles and a stem snap."""
    n = N(0.14)
    r1 = ak.biquad_bandpass(nz(0.14, sd("Pick"), "pink"), 3200.0, 0.7) * ak.env_decay(n, 0.04)
    r2 = ak.biquad_bandpass(nz(0.14, sd("Pick", 1), "pink"), 2800.0, 0.7) * ak.env_decay(n, 0.045)
    snp = ak.mix(click(0.005, 5000.0, sd("Pick", 2)), ring(1200.0, 0.04, 0.01, 0.5))
    return place((0.0, r1), (0.12, r2, 0.9), (0.22, snp, 0.8), tail=0.03)


def sfx_fish() -> np.ndarray:
    """Fish caught: plunk + rising splash + a string of rising bubbles."""
    plunk = ak.osc_sine(ak.freq_curve(300.0, 120.0, 0.12, "exp")) * ak.env_decay(N(0.12), 0.035) * 0.5
    n = N(0.32)
    splash = band_var(nz(0.32, sd("Fish")), [(0.0, 1500.0), (0.12, 4500.0), (0.32, 3000.0)], 1.6, 2)
    splash *= env_shape([(0, 0), (0.02, 1), (0.32, 0)], n, 1.0) * ak.env_decay(n, 0.1)
    bubbles = [(0.1, bubble(500.0, 1100.0, 0.04)), (0.18, bubble(700.0, 1400.0, 0.04)),
               (0.27, bubble(900.0, 1600.0, 0.04)), (0.36, bubble(1100.0, 1900.0, 0.04, gain=0.25))]
    return place((0.0, plunk), (0.0, splash), *bubbles, tail=0.05)


def sfx_door() -> np.ndarray:
    """Door: wood creak (0.4 s) then a thunk."""
    c = creak(0.4, 160.0, 230.0, sd("Door"))
    thunk = ak.mix(thud(140.0, 60.0, 0.2, 0.05, sd("Door", 1), 1500.0, 0.01, 0.5, 1.7),
                   ak.wood_block(380.0, 1.0, 0.08) * 0.6,
                   click(0.006, 5000.0, sd("Door", 2)) * 0.5)
    return place((0.0, c, 0.6), (0.42, thunk))


def sfx_chest() -> np.ndarray:
    """Chest: latch click, short rising lid creak, then a soft two-note sparkle (A6, E7)."""
    latch = ak.mix(click(0.008, 6000.0, sd("Chest")), ak.wood_block(1100.0, 1.0, 0.06) * 0.5)
    lid = creak(0.22, 200.0, 320.0, sd("Chest", 1), rough_hz=25.0)
    b1 = ak.bell(1760.0, 0.05, 0.8, release=0.4)
    b2 = ak.bell(2637.0, 0.05, 0.6, release=0.4)
    return clamp_len(place((0.0, latch), (0.05, lid, 0.45), (0.3, b1, 0.5), (0.38, b2, 0.35)), 0.75, 0.12)


def sfx_save() -> np.ndarray:
    """Save: a soft bell pair (A5, E6), slightly mellowed."""
    y = place((0.0, ak.bell(880.0, 0.1, 0.9, release=0.5)), (0.22, ak.bell(1318.5, 0.1, 0.8, release=0.6)))
    return clamp_len(ak.lowpass(y, 6000.0), 0.85, 0.15)


def sfx_sleep() -> np.ndarray:
    """Sleep: three soft descending tones (E5, C5, G4) with gentle attacks, mellow, roomy."""
    parts = []
    for nm, t, d, v in [("E5", 0.0, 0.3, 1.0), ("C5", 0.3, 0.3, 0.9), ("G4", 0.6, 0.5, 0.8)]:
        f = ak.note_freq(nm)
        n = N(d + 0.15)
        tone = (ak.osc_sine(f, d + 0.15) + ak.osc_tri(f, d + 0.15) * 0.35 + ak.osc_sine(f * 2.0, d + 0.15) * 0.1)
        env = ak.env_adsr(n, 0.04, 0.05, 0.8, 0.15, curve="exp")
        parts.append((t, tone * env, v))
    y = ak.lowpass(place(*parts), 2500.0)
    return clamp_len(ak.reverb(y, 0.9, 0.2, damp=0.6), 1.25, 0.2)


def _cricket(dur: float, carrier: float, pulse_hz: float, pulses: int, chirp_period: float,
             offset: float, seed: int) -> np.ndarray:
    """Cricket: a sine carrier gated by chirps (bursts of `pulses` raised-cosine pulses)."""
    n = N(dur)
    t = T(n)
    pulse_len = 0.6 / pulse_hz
    gate = np.zeros(n)
    rng = np.random.default_rng(seed)
    t0 = offset
    while t0 < dur:
        for p in range(pulses):
            s = t0 + p / pulse_hz
            i0, i1 = N(s), N(s + pulse_len)
            if i0 >= n:
                break
            i1 = min(i1, n)
            u = np.linspace(0.0, 1.0, i1 - i0, endpoint=False)
            gate[i0:i1] = np.maximum(gate[i0:i1], 0.5 - 0.5 * np.cos(2.0 * math.pi * u))
        t0 += chirp_period * float(rng.uniform(0.95, 1.05))
    f = carrier * (1.0 + 0.004 * np.sin(2.0 * math.pi * 1.3 * t))
    return ak.osc_sine(f) * gate


def sfx_night() -> np.ndarray:
    """Night: two crickets (4.3 kHz and 3.8 kHz carriers, chirps of 4 pulses at ~45 Hz every
    0.3 / 0.37 s) over a faint night air (1.5 s)."""
    dur = 1.5
    n = N(dur)
    a = _cricket(dur, 4300.0, 45.0, 4, 0.3, 0.0, sd("Night"))
    b = _cricket(dur, 3800.0, 40.0, 3, 0.37, 0.15, sd("Night", 1)) * 0.6
    air = rumble(dur, sd("Night", 2), 200.0, 1) * 0.06
    y = a + b + air
    return y * env_shape([(0, 0), (0.05, 1), (dur - 0.1, 1), (dur, 0)], n, 1.0)


def sfx_rain() -> np.ndarray:
    """Rain: dense hiss (white 800 Hz .. 9 kHz) + low body + ~40 random droplet ticks (1.5 s)."""
    dur = 1.5
    n = N(dur)
    rng = np.random.default_rng(sd("Rain"))
    hiss = ak.lowpass(ak.highpass(nz(dur, sd("Rain", 1)), 800.0), 5500.0, order=2) * 0.5
    body = ak.biquad_bandpass(nz(dur, sd("Rain", 2), "pink"), 1800.0, 0.5) * 0.5
    parts = [(0.0, hiss), (0.0, body)]
    for i in range(40):
        t = float(rng.uniform(0.0, dur - 0.02))
        c = float(rng.uniform(2500.0, 5500.0))
        parts.append((t, snap(c, 1.5, 0.02, 0.004, sd("Rain", 10 + i)), float(rng.uniform(0.2, 0.6))))
    y = place(*parts)[:n]
    return y * env_shape([(0, 0), (0.15, 1), (dur - 0.2, 1), (dur, 0)], n, 1.2)


def sfx_thunder() -> np.ndarray:
    """Thunder: an initial crack, then a slowly fluctuating brown rumble + 45 Hz sub (1.5 s)."""
    dur = 1.5
    n = N(dur)
    crack = ak.lowpass(nz(0.12, sd("Thunder")), 3000.0) * ak.env_decay(N(0.12), 0.03) * 0.8
    mod = 0.55 + 0.45 * np.clip(ak.lowpass(nz(dur, sd("Thunder", 1)), 3.0) / 0.03, -1.0, 1.0)
    rum = rumble(dur, sd("Thunder", 2), 120.0, 2) * mod
    sub = ak.osc_sine(45.0, dur) * 0.4
    env = env_shape([(0, 0.3), (0.15, 1.0), (dur, 0)], n, 1.0) * ak.env_decay(n, 0.55)
    y = place((0.0, crack), (0.0, (rum + sub) * env))
    return ak.soft_clip(y, 2.0)


def sfx_horse() -> np.ndarray:
    """Horse: trot of four hoof taps (ta-tak ... ta-tak) with slight pitch variation."""
    parts = []
    for i, t in enumerate([0.0, 0.12, 0.34, 0.46]):
        f0 = 260.0 * (1.0 + 0.06 * ((i * 7) % 3 - 1))
        tap = ak.mix(thud(f0, 110.0, 0.08, 0.015, sd("Horse", i), 2500.0, 0.004, 0.6, 1.5),
                     ak.lowpass(nz(0.03, sd("Horse", 10 + i)), 3500.0) * ak.env_decay(N(0.03), 0.004) * 0.6)
        parts.append((t, tap, 1.0 if i % 2 == 0 else 0.8))
    dust = ak.lowpass(nz(0.6, sd("Horse", 20), "pink"), 800.0) * 0.08
    parts.append((0.0, dust))
    return place(*parts)


def sfx_wolf() -> np.ndarray:
    """Wolf howl: rise 380 -> 720 Hz, hold with slow 4.5 Hz vibrato, fall to 520 Hz; harmonics,
    breath that follows the pitch, distant room (1.05 s)."""
    dur = 1.05
    n = N(dur)
    f = center_curve([(0.0, 380.0), (0.3, 720.0), (0.72, 700.0), (dur, 520.0)], n)
    f = ak.vibrato(f, None, 4.5, 0.35, onset=0.35, ramp=0.2)
    tone = ak.osc_sine(f) + ak.osc_sine(f * 2.0) * 0.5 + ak.osc_sine(f * 3.0) * 0.25 + ak.osc_sine(f * 4.0) * 0.1
    breath = band_var(nz(dur, sd("Wolf")), f, 1.3, 2) * 0.25
    env = env_shape([(0, 0), (0.08, 1), (0.85, 0.9), (dur, 0)], n, 1.2)
    y = ak.lowpass(tone + breath, 4000.0) * env
    return clamp_len(ak.reverb(y, 0.8, 0.2, damp=0.6), 1.15, 0.15)


def sfx_tiger() -> np.ndarray:
    """Tiger growl: sawtooth 75 -> 62 Hz with 24 Hz amplitude roughness + low noise + a
    band-passed roar layer, resonant low-pass, saturated (0.7 s)."""
    dur = 0.7
    n = N(dur)
    t = T(n)
    f = ak.freq_curve(75.0, 62.0, dur, "exp")
    am = 0.3 + 0.7 * (0.5 + 0.5 * np.sin(2.0 * math.pi * 24.0 * t))
    saw = (ak.osc_saw(f) + ak.osc_saw(f * 1.5, phase=0.3) * 0.3) * am
    saw = ak.biquad_lowpass(saw, 700.0, 1.2)
    low = rumble(dur, sd("Tiger"), 500.0, 1) * am * 0.5
    roar = ak.biquad_bandpass(nz(dur, sd("Tiger", 1), "pink"), 400.0, 1.0) * am * 0.5
    env = env_shape([(0, 0), (0.06, 1), (0.55, 0.9), (dur, 0)], n, 1.2)
    return ak.soft_clip((saw + low + roar) * env, 2.0)


# ==========================================================================================
# Registry (spec order) and build
# ==========================================================================================
CUES = {
    "Accept": sfx_accept, "Cancel": sfx_cancel, "Move1": sfx_move1, "Slash": sfx_slash,
    "Hit1": sfx_hit1, "Hit2": sfx_hit2, "Impact": sfx_impact, "Coin": sfx_coin, "Bonus": sfx_bonus,
    "Jump": sfx_jump,
    "Hover": sfx_hover, "Open": sfx_open, "Close": sfx_close, "Error": sfx_error, "Talk": sfx_talk,
    "Buy": sfx_buy, "Sell": sfx_sell, "Equip": sfx_equip, "Unequip": sfx_unequip,
    "Pill": sfx_pill, "Drink": sfx_drink, "Eat": sfx_eat, "Read": sfx_read, "Heal": sfx_heal,
    "Poison": sfx_poison, "Bleed": sfx_bleed,
    "Acupoint": sfx_acupoint, "Guard": sfx_guard, "Dodge": sfx_dodge, "Crit": sfx_crit,
    "Stab": sfx_stab, "Punch": sfx_punch, "Palm": sfx_palm, "Kick": sfx_kick, "Stone": sfx_stone,
    "Needle": sfx_needle,
    "Qi": sfx_qi, "Burst": sfx_burst, "Breakthrough": sfx_breakthrough, "Deviation": sfx_deviation,
    "Demon": sfx_demon, "Victory": sfx_victory, "Defeat": sfx_defeat,
    "Step1": sfx_step1, "Step2": sfx_step2, "Step3": sfx_step3, "StepStone1": sfx_step_stone1,
    "StepStone2": sfx_step_stone2, "StepWater": sfx_step_water, "Run": sfx_run, "Leap": sfx_leap,
    "Land": sfx_land,
    "Rhythm1": sfx_rhythm1, "Rhythm2": sfx_rhythm2, "Rhythm3": sfx_rhythm3, "Rhythm4": sfx_rhythm4,
    "RhythmMiss": sfx_rhythm_miss, "RhythmPerfect": sfx_rhythm_perfect,
    "Gong": sfx_gong, "Drum": sfx_drum, "Bell": sfx_bell, "Wood": sfx_wood, "Bird": sfx_bird,
    "Wind": sfx_wind, "Fire": sfx_fire, "Chop": sfx_chop, "Pick": sfx_pick, "Fish": sfx_fish,
    "Door": sfx_door, "Chest": sfx_chest, "Save": sfx_save, "Sleep": sfx_sleep, "Night": sfx_night,
    "Rain": sfx_rain, "Thunder": sfx_thunder, "Horse": sfx_horse, "Wolf": sfx_wolf, "Tiger": sfx_tiger,
}

assert list(CUES) == SPEC_NAMES, "CUES must list every spec section 6 SFX name, in order"


def render(name: str) -> np.ndarray:
    """Render one cue as float64 mono scaled to peak 1.0 (un-mastered otherwise).

    The peak-1.0 scaling matters: `finalize_sfx` trims at -60 dBFS *before* it normalises,
    so a cue whose raw sum peaks well above 1.0 would keep a head that ends up below -60 dB
    after mastering (reported as leading silence).  Scaling first makes the trim relative
    to the final peak for every cue."""
    ak.seed(sd(name))
    x = np.asarray(CUES[name](), dtype=np.float64).reshape(-1)
    x = np.nan_to_num(x)
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    return x / peak if peak > 0 else x


def build(audio_root: str, tmp_dir: str) -> list:
    """Write every section 6 SFX as <audio_root>/Sfx/<Name>.wav; return the paths written."""
    out = []
    for name in SPEC_NAMES:
        ak.seed(sd(name))            # independence from other generators / ordering
        x = render(name)
        out.append(ak.save_sfx(ak.sfx_path(audio_root, name), x))
    return out


if __name__ == "__main__":
    repo = os.path.dirname(os.path.dirname(HERE))
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(repo, "Assets", "InkPixel", "Audio")
    tmp = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.getcwd(), "audio_tmp")
    os.makedirs(tmp, exist_ok=True)
    for p in build(os.path.abspath(root), os.path.abspath(tmp)):
        print(p)
