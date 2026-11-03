#!/usr/bin/env python3
"""gen_music.py -- every music cue of ASSET_SPEC.md section 6 (InkPixel / 강호유랑기).

Composed with the audiokit Sequencer and its wuxia voices (zither, flute, erhu, taiko, gong,
temple bell, wood block, shaker) plus a few custom voices built from audiokit primitives
(water drip, wind bed).  Loops are rendered with `render_loop_safe` so they are EXACTLY
`loop_samples(bpm, bars)` long and note tails wrap to the start; the two stings (Victory,
GameOver) are rendered with `render`, cut to length and faded.

Output: `<audio_root>/Music/<Name>.ogg` (OGG Vorbis q6, 44100 Hz stereo); WAV masters go to
`tmp_dir` only.  Everything is deterministic (fixed seeds, no wall-clock input).

Musical notes for humans (key / BPM / form / instrumentation) are in Docs/MUSIC_NOTES.md.
"""
from __future__ import annotations

import math
import os
import sys
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import audiokit as ak  # noqa: E402

SR = ak.SR

# bpm / bars of every cue; build_all.py and analyze.py read this to verify exact loop lengths.
LOOP_INFO = {
    "Town":     {"bpm": 92,  "bars": 32, "beats_per_bar": 4},
    "World":    {"bpm": 110, "bars": 32, "beats_per_bar": 4},
    "Battle":   {"bpm": 150, "bars": 32, "beats_per_bar": 4},
    "Mountain": {"bpm": 70,  "bars": 32, "beats_per_bar": 4},
    "Cave":     {"bpm": 80,  "bars": 32, "beats_per_bar": 4},
    "Sect":     {"bpm": 84,  "bars": 32, "beats_per_bar": 4},
    "Dark":     {"bpm": 100, "bars": 32, "beats_per_bar": 4},
    "Night":    {"bpm": 66,  "bars": 32, "beats_per_bar": 4},
    "Demon":    {"bpm": 120, "bars": 16, "beats_per_bar": 4},
    "Title":    {"bpm": 76,  "bars": 32, "beats_per_bar": 4},
    "Victory":  {"bpm": 120, "bars": 3,  "beats_per_bar": 4, "loop": False, "seconds": 5.0},
    "GameOver": {"bpm": 60,  "bars": 2,  "beats_per_bar": 4, "loop": False, "seconds": 8.0},
}

Pattern = List[Tuple[float, object, float, float]]
BEATS = 4   # every cue is in 4/4


# ------------------------------------------------------------------------------------------
# Pattern helpers (thin layer over ak.parse_pattern with bar-length validation)
# ------------------------------------------------------------------------------------------
def P(text: str, step: float = 0.5, velocity: float = 1.0, soft: float = 0.6, accent: float = 1.0) -> Pattern:
    """parse_pattern with a safety net: every '|'-separated bar must hold exactly 4/step
    tokens, so a typo cannot silently shift the rest of the track."""
    per_bar = int(round(BEATS / step))
    for i, b in enumerate(t for t in text.split("|") if t.strip()):
        n = len(b.split())
        if n != per_bar:
            raise ValueError("bar %d has %d tokens, expected %d (step %g): %r" % (i, n, per_bar, step, b.strip()))
    return ak.parse_pattern(text, step, velocity=velocity, soft=soft, accent=accent)


def at(pattern: Pattern, bar_index: int) -> Pattern:
    """Pattern moved to bar `bar_index` (0-based)."""
    return ak.bar(pattern, bar_index, BEATS)


def cat(*parts: Pattern) -> Pattern:
    """Concatenate patterns bar after bar (each part is padded to whole bars)."""
    out: Pattern = []
    pos = 0.0
    for p in parts:
        out.extend(ak.shift_pattern(p, pos))
        pos += math.ceil((ak.pattern_length(p) or BEATS) / BEATS - 1e-9) * BEATS
    return out


def rep(pattern: Pattern, times: int, bars: Optional[int] = None) -> Pattern:
    """Repeat a pattern every `bars` bars (default: its own length)."""
    length = (bars * BEATS) if bars else math.ceil(ak.pattern_length(pattern) / BEATS - 1e-9) * BEATS
    return ak.repeat_pattern(pattern, times, length)


def merge(*patterns: Pattern) -> Pattern:
    return ak.merge_patterns(*patterns)


def vel(pattern: Pattern, k: float) -> Pattern:
    """Scale every velocity (phrase dynamics)."""
    return [(s, n, l, v * k) for s, n, l, v in pattern]


def ramp(pattern: Pattern, v0: float, v1: float) -> Pattern:
    """Linear crescendo/diminuendo over the pattern's own length."""
    L = max(ak.pattern_length(pattern), 1e-9)
    return [(s, n, l, v * (v0 + (v1 - v0) * s / L)) for s, n, l, v in pattern]


def trn(pattern: Pattern, semitones: int) -> Pattern:
    return ak.transpose_pattern(pattern, semitones)


def hits(beats: Sequence[float], length: float = 0.25, velocity: float = 1.0) -> Pattern:
    """Unpitched hits at the given beat positions (one bar unless positions exceed 4)."""
    return [(float(b), "x", length, velocity) for b in beats]


def notes(events: Sequence[Tuple[float, object, float]], velocity: float = 1.0) -> Pattern:
    """[(start_beat, note, length_beats), ...] -> pattern."""
    return [(float(s), n, float(l), velocity) for s, n, l in events]


_SYMBOLIC = {"R": 0, "F": 7, "O": 12, "L": -5, "D": -12, "T": 4, "M": 3, "S": 2, "N": -2, "U": 14}


def bassline(roots: Sequence[str], template: str, step: float = 0.5, velocity: float = 1.0) -> Pattern:
    """A bass pattern from per-bar chord roots and ONE symbolic bar template.
    template tokens (one per step): R root, F fifth, O octave, L fifth below, D octave below,
    S 2nd, N 2nd below, T major third, M minor third, U ninth; '--' rest, '==' tie, '@v' velocity."""
    out: Pattern = []
    per_bar = int(round(BEATS / step))
    toks = template.replace("|", " ").split()
    if len(toks) != per_bar:
        raise ValueError("bass template has %d tokens, expected %d" % (len(toks), per_bar))
    for b, root in enumerate(roots):
        base = ak.note_to_midi(root)
        last = -1
        for i, tok in enumerate(toks):
            if tok in ("--", "-", "."):
                last = -1
                continue
            if tok in ("==", "="):
                if last >= 0:
                    s, n, l, v = out[last]
                    out[last] = (s, n, l + step, v)
                continue
            v = velocity
            if "@" in tok:
                tok, vs = tok.split("@", 1)
                v = float(vs)
            out.append((b * BEATS + i * step, base + _SYMBOLIC[tok], step, v))
            last = len(out) - 1
    return out


def arp(voicing: Sequence[str], order: Sequence[int], step: float = 0.5, velocity: float = 1.0,
        accents: Optional[Sequence[float]] = None, length: Optional[float] = None) -> Pattern:
    """One bar of arpeggio: `order` indexes into `voicing` (-1 = rest), one note per step."""
    out: Pattern = []
    L = length if length is not None else step * 1.6
    for i, idx in enumerate(order):
        if idx < 0:
            continue
        v = velocity * (accents[i] if accents else 1.0)
        out.append((i * step, voicing[idx], L, v))
    return out


def strum(voicing: Sequence[str], start: float, length: float, velocity: float = 1.0,
          spread: float = 0.045, down: bool = True) -> Pattern:
    """A rolled zither chord: each string a little after the previous one (low to high)."""
    names = list(voicing) if down else list(reversed(voicing))
    out: Pattern = []
    for i, n in enumerate(names):
        out.append((start + i * spread, n, max(0.1, length - i * spread), velocity * (1.0 - 0.07 * i)))
    return out


def chord_bars(voicings: Sequence[Sequence[str]], starts: Sequence[float] = (0.0, 2.0),
               length: float = 1.9, velocity: float = 1.0, spread: float = 0.045) -> Pattern:
    """Strummed chords, one voicing per bar, at the given beats within each bar."""
    out: Pattern = []
    for b, vo in enumerate(voicings):
        for k, s in enumerate(starts):
            out.extend(strum(vo, b * BEATS + s, length, velocity * (1.0 if k == 0 else 0.8), spread))
    return out


# ------------------------------------------------------------------------------------------
# Extra voices built from audiokit primitives (deterministic: explicit noise seeds)
# ------------------------------------------------------------------------------------------
def drip(freq: float, dur: float, vel: float = 1.0, sr: int = SR) -> np.ndarray:
    """Water drop: a short sine 'plink' whose pitch RISES (bubble resonance) then decays."""
    n = ak.samples(0.26, sr)
    t = np.arange(n) / sr
    f = freq * (0.55 + 0.75 * (1.0 - np.exp(-t / 0.018)))     # 0.55f -> 1.3f in ~40 ms
    body = ak.osc_sine(f, None, sr) * np.exp(-t / 0.045)
    ring = ak.osc_sine(freq * 1.3, n / sr, sr) * np.exp(-t / 0.09) * 0.35
    clk = ak.lowpass(ak.noise(0.01, "white", sr, ak._hash_seed("drip", freq)), 5000.0, sr)
    y = ak.mix(body + ring, clk * 0.25 * np.exp(-np.arange(ak.samples(0.01, sr)) / sr / 0.002))
    y *= ak.env_adsr(n, 0.001, 0.0, 1.0, 0.05, sr)
    return ak._level(y, 0.7 * ak._vel_gain(vel))


def wind(freq: float, dur: float, vel: float = 1.0, sr: int = SR) -> np.ndarray:
    """Wind gust: pink noise through a slowly wandering band-pass, long swell, soft release.
    `freq` sets the band centre (hundreds of Hz)."""
    total = dur + 1.5
    n = ak.samples(total, sr)
    sd = ak._hash_seed("wind", freq, dur, vel)
    nz = ak.noise(total, "pink", sr, sd)
    y = ak.biquad_bandpass(nz, float(freq), 0.9, sr) * 0.6 + ak.biquad_bandpass(nz, float(freq) * 2.3, 1.4, sr) * 0.4
    t = np.arange(n) / sr
    swell = 0.6 + 0.4 * np.sin(2.0 * math.pi * 0.21 * t + 0.3 * freq)
    env = ak.env_adsr(n, min(1.2, dur * 0.4), 0.0, 1.0, 1.5, sr, curve="exp")
    y = ak.lowpass(y * swell * env, 4000.0, sr)
    return ak._level(y, 0.5 * ak._vel_gain(vel))


def tremolo_zither(freq: float, dur: float, vel: float = 1.0, sr: int = SR, rate: float = 11.0) -> np.ndarray:
    """Zither tremolo (轮指): repeated plucks at `rate` Hz for the note length."""
    n_total = ak.samples(dur + 0.5, sr)
    out = np.zeros(n_total)
    k = 0
    while True:
        t0 = k / rate
        if t0 >= dur:
            break
        y = ak.zither(freq, 1.0 / rate, vel * (0.85 + 0.15 * (k % 2)), sr, bright=0.8, release=0.25)
        s = ak.samples(t0, sr)
        e = min(n_total, s + len(y))
        out[s:e] += y[: e - s]
        k += 1
    return ak._level(out, 0.8 * ak._vel_gain(vel))


# ------------------------------------------------------------------------------------------
# Rendering / saving helpers
# ------------------------------------------------------------------------------------------
def rev(decay: float, mix: float, damp: float = 0.5, predelay: float = 0.0) -> Callable:
    return lambda x: ak.reverb(x, decay, mix, damp=damp, predelay=predelay)


def lp(hz: float, order: int = 1) -> Callable:
    return lambda x: ak.lowpass(x, hz, order=order)


def chain(*fns: Callable) -> Callable:
    def f(x):
        for fn in fns:
            x = fn(x)
        return x
    return f


def save_loop(seq: ak.Sequencer, name: str, audio_root: str, tmp_dir: str) -> str:
    info = LOOP_INFO[name]
    x = seq.render_loop_safe(info["bars"], info["beats_per_bar"])
    assert len(x) == ak.loop_samples(info["bpm"], info["bars"], info["beats_per_bar"]), name
    return ak.save_music(ak.music_path(audio_root, name), x,
                         master_wav=os.path.join(tmp_dir, name + ".wav"))


def save_sting(seq: ak.Sequencer, name: str, audio_root: str, tmp_dir: str, fade_out: float) -> str:
    info = LOOP_INFO[name]
    x = seq.render(info["bars"], info["beats_per_bar"])
    n = ak.samples(info["seconds"])
    x = ak.pad_to(x, n)
    x = ak.fade(x, 0.0, fade_out, shape="cos")
    return ak.save_music(ak.music_path(audio_root, name), x,
                         master_wav=os.path.join(tmp_dir, name + ".wav"))


# ==========================================================================================
# Town  --  백로진 (white-egret river town).  G major pentatonic (G A B D E), 92 BPM, 32 bars
# Form A(1-8) A'(9-16) B(17-24) A''(25-32).  Zither lead with a 2-bar motif, flute
# counter-melody in B, zither bass on roots/fifths, soft taiko + wood block, shaker.
# ==========================================================================================
def build_town(audio_root: str, tmp_dir: str) -> str:
    seq = ak.Sequencer(92)
    # -- zither lead ------------------------------------------------------------------
    A = P("D5 == B4 D5 E5 == D5 B4 | A4 == == B4 A4 == G4 == |"
          "E5 == D5 B4 D5 == E5 G5 | A5 == G5 E5 D5 == == == |"
          "D5 == B4 D5 E5 == D5 B4 | A4 == B4 D5 E5 == == == |"
          "G5 == E5 D5 B4 == D5 B4 | A4 == G4 == == == -- --", 0.5)
    A2 = P("D5 == == == B4 == D5 == E5 == == == D5 B4 D5 B4 |"
           "A4 == == == == == B4 == A4 == == == G4 == == == |"
           "E5 == == == D5 == B4 == D5 == E5 D5 E5 == G5 == |"
           "A5 == == == G5 == E5 == D5 == == == == == == == |"
           "D5 == == == B4 == D5 == E5 == == == D5 == B4 == |"
           "A4 == == == B4 == D5 == E5 == == == == == G5 A5 |"
           "G5 == == == E5 == D5 == B4 == == == D5 == B4 == |"
           "A4 == == == G4 == == == == == == == -- -- -- --", 0.25)
    B = P("E5 == G5 == A5 == G5 E5 | D5 == E5 D5 B4 == == == |"
          "D5 == E5 == G5 == A5 G5 | E5 == D5 B4 A4 == == == |"
          "B4 D5 E5 == G5 == E5 D5 | E5 == D5 == B4 == A4 B4 |"
          "A4 == == == B4 == D5 == | E5 == D5 == -- -- -- --", 0.5)
    lead = cat(vel(A, 0.9), vel(A2, 0.8), vel(B, 1.0), vel(A2, 0.95))
    seq.add_track("zither", ak.zither, lead, volume=0.9, pan=0.0, fx=rev(1.1, 0.14, 0.6))

    # -- flute counter-melody (B) + two sustained answers in the last A ------------------
    fl = P("-- -- -- -- B4 == == == | G4 == == == == == -- -- |"
           "-- -- -- -- D5 == == == | E5 == == == == == == == |"
           "-- -- G5 == E5 == == == | D5 == == == -- -- -- -- |"
           "A4 == == == B4 == == == | D5 == == == == == -- --", 0.5)
    fl_tail = merge(at(P("-- -- -- -- B4 == == == | D5 == == == == == -- --", 0.5), 2),
                    at(P("-- -- -- -- E5 == D5 == | D5 == == == == == -- --", 0.5), 6))
    seq.add_track("flute", ak.flute, merge(at(vel(fl, 0.8), 16), at(vel(fl_tail, 0.6), 24)),
                  volume=0.42, pan=0.28, fx=rev(1.4, 0.22, 0.5))

    # -- zither bass: roots and fifths --------------------------------------------------
    rootsA = ["G2", "E2", "C3", "D3", "G2", "E2", "D3", "G2"]
    rootsB = ["E2", "C3", "G2", "D3", "E2", "C3", "D3", "D3"]
    bass = cat(bassline(rootsA, "R == == == F@0.8 == R@0.7 --", 0.5, 0.95),
               bassline(rootsA, "R == == == F@0.8 == R@0.7 F@0.5", 0.5, 0.85),
               bassline(rootsB, "R == == F@0.7 R == F@0.6 --", 0.5, 1.0),
               bassline(rootsA, "R == == == F@0.8 == R@0.7 F@0.5", 0.5, 0.95))
    seq.add_track("bass", ak.instrument(ak.zither, bright=0.35), bass, volume=0.6, pan=-0.08)

    # -- percussion ------------------------------------------------------------------
    low = rep(hits([0.0], 0.5, 0.75) + hits([2.5], 0.5, 0.42), 32)
    mid = rep(hits([2.0], 0.5, 0.5), 32)
    low_B = rep(hits([0.0], 0.5, 0.85) + hits([1.5, 2.5], 0.5, 0.45), 8)
    seq.add_track("taiko_low", ak.instrument(ak.taiko, kind="low"), merge(low, at(low_B, 16)), volume=0.62)
    seq.add_track("taiko_mid", ak.instrument(ak.taiko, kind="mid"), mid, volume=0.5, pan=0.1)
    wb = rep(hits([1.0, 3.0], 0.25, 0.55), 32)
    wb_fill = rep(hits([3.75], 0.25, 0.4), 8, 4)         # 16th pickup every 4th bar
    seq.add_track("block", ak.instrument(ak.wood_block, pitch=1050), merge(wb, at(wb_fill, 3)),
                  volume=0.45, pan=0.35, fx=rev(0.7, 0.18, 0.4))
    sh = rep(P("x X x X x X x X", 0.5, velocity=0.6, soft=0.5), 32)
    sh_dyn = cat(vel(rep(sh[:8], 8), 0.85), vel(rep(sh[:8], 8), 0.7), vel(rep(sh[:8], 8), 1.0), vel(rep(sh[:8], 8), 0.9))
    seq.add_track("shaker", ak.shaker, sh_dyn, volume=0.3, pan=-0.3, fx=lp(9000, 2))

    seq.master_fx.append(lp(13000))
    return save_loop(seq, "Town", audio_root, tmp_dir)


# ==========================================================================================
# World  --  강호 (travelling).  D major pentatonic (D E F# A B), 110 BPM, 32 bars
# Form A1(1-8) A2(9-16) B(17-24, bright) A3(25-32).  Flute lead over plucked bass, light
# taiko, zither broken chords from A2 on.
# ==========================================================================================
def build_world(audio_root: str, tmp_dir: str) -> str:
    seq = ak.Sequencer(110)
    A1 = P("D5 == E5 == F#5 == == == | A5 == F#5 == E5 == == == |"
           "D5 == E5 F#5 E5 == D5 == | B4 == == == -- -- A4 B4 |"
           "D5 == E5 == F#5 == A5 == | B5 == A5 == F#5 == == == |"
           "E5 == F#5 E5 D5 == E5 == | E5 == == == == == -- --", 0.5)
    A2 = P("D5 == E5 == F#5 == == == | A5 == F#5 == E5 == == == |"
           "D5 == E5 F#5 E5 == D5 == | B4 == == == -- -- A4 B4 |"
           "D5 == E5 == F#5 == A5 == | B5 == A5 == F#5 == == == |"
           "E5 == F#5 E5 D5 == E5 == | D5 == == == == == -- --", 0.5)
    B = P("B5 == A5 == F#5 == A5 == | B5 == == == A5 == == == |"
          "F#5 == A5 == D6 == B5 == | A5 == == == F#5 == == == |"
          "E5 == F#5 == A5 == B5 == | A5 == F#5 == E5 == == == |"
          "D5 == E5 == F#5 == E5 == | E5 == == == -- -- -- --", 0.5)
    lead = cat(vel(A1, 0.85), vel(A2, 0.9), vel(B, 1.0), vel(A2, 0.95))
    seq.add_track("flute", ak.flute, lead, volume=0.5, pan=0.0, fx=rev(1.2, 0.2, 0.5))

    # zither broken chords (A2, B, A3) slightly right; chord voicings per bar
    V = {"D": ["D4", "A4", "D5", "F#5"], "Bm": ["B3", "F#4", "B4", "D5"], "G": ["G3", "D4", "G4", "B4"],
         "A": ["A3", "E4", "A4", "B4"]}
    chA2 = ["D", "Bm", "G", "A", "D", "Bm", "A", "D"]
    chB = ["G", "A", "D", "Bm", "G", "A", "Bm", "A"]
    chA1 = ["D", "Bm", "G", "A", "D", "Bm", "G", "A"]

    def broken(chords, order, acc):
        return cat(*[arp(V[c], order, 0.5, 1.0, acc) for c in chords])

    z = merge(at(broken(chA2, [0, 2, 1, 3, 0, 2, 1, 3], [1, .6, .7, .6, .9, .6, .7, .6]), 8),
              at(broken(chB, [0, 1, 2, 3, 2, 3, 1, 2], [1, .6, .8, .7, .9, .6, .7, .6]), 16),
              at(broken(chA2, [0, 2, 1, 3, 0, 2, 1, 3], [1, .6, .7, .6, .9, .6, .7, .6]), 24))
    seq.add_track("zither", ak.instrument(ak.zither, bright=0.55), vel(z, 0.7), volume=0.42, pan=0.3,
                  fx=rev(0.9, 0.12, 0.5))

    # plucked bass
    roots = {"D": "D3", "Bm": "B2", "G": "G2", "A": "A2"}
    bass = cat(bassline([roots[c] for c in chA1], "R == R@0.8 F@0.8 R == O@0.7 F@0.7", 0.5, 0.9),
               bassline([roots[c] for c in chA2], "R == R@0.8 F@0.8 R == O@0.7 F@0.7", 0.5, 0.95),
               bassline([roots[c] for c in chB], "R R@0.7 F@0.8 R@0.7 R R@0.7 O@0.8 F@0.7", 0.5, 1.0),
               bassline([roots[c] for c in chA2], "R == R@0.8 F@0.8 R == O@0.7 F@0.7", 0.5, 0.95))
    seq.add_track("bass", ak.instrument(ak.pluck, bright=0.45), bass, volume=0.42, pan=-0.05, fx=lp(3000))

    # light drums
    low = rep(hits([0.0], 0.5, 0.75) + hits([2.5], 0.5, 0.55), 32)
    mid = rep(hits([2.0], 0.5, 0.5) + hits([3.5], 0.5, 0.35), 32)
    mid_fill = merge(*[at(hits([3.0, 3.25, 3.5, 3.75], 0.25, v), b) for b, v in ((7, .5), (15, .6), (23, .7), (31, .6))])
    rim = rep(hits([1.0, 3.0], 0.25, 0.4), 32)
    seq.add_track("taiko_low", ak.instrument(ak.taiko, kind="low"), low, volume=0.58)
    seq.add_track("taiko_mid", ak.instrument(ak.taiko, kind="mid"), merge(mid, mid_fill), volume=0.45, pan=0.12)
    seq.add_track("rim", ak.instrument(ak.taiko, kind="rim"), rim, volume=0.3, pan=-0.2)
    wb = merge(rep(hits([3.5], 0.25, 0.5), 16, 2), at(rep(hits([1.5], 0.25, 0.4), 8, 1), 16))
    seq.add_track("block", ak.instrument(ak.wood_block, pitch=1250), wb, volume=0.35, pan=0.4, fx=rev(0.6, 0.15, 0.4))
    sh = rep(P("x X x X x X x X", 0.5, velocity=0.6, soft=0.5), 32)
    seq.add_track("shaker", ak.shaker, cat(vel(sh[:64], 0.7), vel(sh[:64], 0.85), vel(sh[:64], 1.0), vel(sh[:64], 0.9)),
                  volume=0.28, pan=-0.3, fx=lp(9000, 2))

    seq.master_fx.append(lp(13000))
    return save_loop(seq, "World", audio_root, tmp_dir)


# ==========================================================================================
# Battle  --  E minor pentatonic (E G A B D), 150 BPM, 32 bars
# Form A(1-8) A'(9-16) B(17-24, erhu melody over pedal) A''(25-32).  Driving taiko,
# aggressive zither riff, erhu stabs, gong at every section start.
# ==========================================================================================
def build_battle(audio_root: str, tmp_dir: str) -> str:
    seq = ak.Sequencer(150)
    rE = P("E4 -- E4 G4 E4 -- D4 E4 G4 -- -- A4 G4 -- E4 D4 |"
           "E4 -- E4 G4 E4 -- D4 E4 B4 -- A4 G4 E4 -- -- --", 0.25, soft=0.75)
    rG = P("G4 -- G4 B4 G4 -- E4 G4 D5 -- -- B4 A4 -- G4 E4", 0.25)
    rA = P("A4 -- A4 B4 A4 -- G4 A4 E5 -- -- D5 B4 -- A4 G4", 0.25)
    rD = P("D4 -- D4 E4 D4 -- B3 D4 A4 -- -- G4 E4 -- D4 B3", 0.25)
    rEnd = P("E4 -- E4 G4 E4 -- D4 E4 B4 -- D5 -- E5 -- -- --", 0.25)
    riffA = cat(rE, rG, rA, rE, rD, rEnd)                       # 8 bars
    # A': riff an octave up for the last 4 bars (zither doubled)
    riffA2 = cat(rE, rG, rA, trn(rE, 12), trn(rD, 12), trn(rEnd, 12))
    stab = P("A4+E5 -- -- -- -- -- A4+E5 -- -- -- -- -- A4+E5 -- A4+E5 --", 0.25)
    stabsB = cat(stab, stab, trn(stab, -2), trn(stab, -2), trn(stab, -7), trn(stab, -7), trn(stab, 2), trn(stab, -5))
    riff = cat(vel(riffA, 0.95), vel(riffA2, 1.0), vel(stabsB, 0.9), vel(riffA, 1.0))
    seq.add_track("zither", ak.instrument(ak.zither, bright=0.9, release=0.3), riff, volume=0.85, pan=0.0,
                  fx=chain(lambda x: ak.soft_clip(x, 1.25), rev(0.6, 0.1, 0.6)))
    # second zither: octave double in A'' (bars 25-32), panned left
    seq.add_track("zither2", ak.instrument(ak.zither, bright=0.8, release=0.3), at(vel(trn(riffA, 12), 0.6), 24),
                  volume=0.4, pan=-0.35)

    # erhu stabs (A sections) and the B melody
    stabsA = merge(at(notes([(3.5, "A4", 0.5)]), 2), at(notes([(3.0, "B4", 0.5), (3.5, "D5", 0.5)]), 3),
                   at(notes([(3.5, "E5", 0.5)]), 6), at(notes([(2.0, "D5", 0.5), (3.0, "B4", 1.0)]), 7))
    erB = P("E5 == == == G5 == E5 == | D5 == == == == == B4 D5 |"
            "E5 == D5 == B4 == == == | D5 == E5 == G5 == == == |"
            "A5 == == == G5 == E5 == | D5 == == == E5 == D5 B4 |"
            "D5 == B4 == A4 == B4 == | E5 == == == == == -- --", 0.5)
    erhu = merge(vel(stabsA, 0.9), at(vel(stabsA, 0.95), 8), at(vel(erB, 1.0), 16), at(vel(stabsA, 1.0), 24))
    seq.add_track("erhu", ak.instrument(ak.erhu, vib_depth=0.35, glide=0.05), erhu, volume=0.62, pan=0.25,
                  fx=rev(1.0, 0.18, 0.5))

    # gong at section starts
    seq.add_track("gong", ak.instrument(ak.gong, dur=3.0, freq=96.0),
                  merge(*[at(hits([0.0], 1.0, v), b) for b, v in ((0, .62), (8, .5), (16, .72), (24, .6))]),
                  volume=0.5, pan=-0.1)

    # bass: plucked 8ths, chord roots, pedal with octave jumps in B
    rootsA = ["E2", "E2", "G2", "A2", "E2", "E2", "D2", "E2"]
    rootsB = ["A2", "A2", "G2", "G2", "D2", "D2", "B2", "E2"]
    bass = cat(bassline(rootsA, "R R@0.75 R R@0.75 R R@0.75 R R@0.75", 0.5, 0.95),
               bassline(rootsA, "R R@0.75 R R@0.75 R R@0.75 O@0.7 R@0.75", 0.5, 1.0),
               bassline(rootsB, "R O@0.7 R O@0.7 R O@0.7 R O@0.7", 0.5, 1.0),
               bassline(rootsA, "R R@0.75 R R@0.75 R R@0.75 R R@0.75", 0.5, 1.0))
    seq.add_track("bass", ak.instrument(ak.pluck, bright=0.5), bass, volume=0.45, pan=0.0, fx=lp(2500))

    # taiko: 2-bar pattern, fills every 8th bar
    low = rep(hits([0.0, 2.0], 0.5, 0.95) + hits([1.5, 3.5], 0.5, 0.6) +
              ak.shift_pattern(hits([0.0, 2.0], 0.5, 0.95) + hits([1.5, 2.5], 0.5, 0.6), 4), 16)
    mid = rep(hits([1.0, 3.0], 0.5, 0.7) + ak.shift_pattern(hits([1.0, 3.0, 3.5], 0.5, 0.7), 4), 16)
    fill = merge(*[at(hits([3.0, 3.25, 3.5, 3.75], 0.25, 0.8), b) for b in (7, 15, 23, 31)])
    rim = rep(P("x x X x x x X x x x X x x x X X", 0.25, velocity=0.5, soft=0.55), 32)
    seq.add_track("taiko_low", ak.instrument(ak.taiko, kind="low"), low, volume=0.72)
    seq.add_track("taiko_mid", ak.instrument(ak.taiko, kind="mid"), merge(mid, fill), volume=0.55, pan=0.15)
    seq.add_track("rim", ak.instrument(ak.taiko, kind="rim"), rim, volume=0.32, pan=-0.3, fx=lp(10000))

    seq.master_fx.append(chain(lambda x: ak.soft_clip(x, 1.3), lp(15000)))
    return save_loop(seq, "Battle", audio_root, tmp_dir)


# ==========================================================================================
# Mountain  --  무명산 (nameless mountain, 산중수련).  A minor pentatonic (A C D E G),
# 70 BPM, 32 bars.  Sparse flute, long erhu notes, wind-like pad + real wind gusts,
# occasional wood block and a distant taiko.
# ==========================================================================================
def build_mountain(audio_root: str, tmp_dir: str) -> str:
    seq = ak.Sequencer(70)
    # pad bed: one chord per 4-bar group, slightly overlapping so the bed never dips to zero
    groups = [["A2", "E3"], ["A2", "E3"], ["G2", "D3"], ["A2", "E3"], ["C3", "G3"], ["D3", "A3"], ["A2", "E3"], ["A2", "E3"]]
    pad = [(i * 16.0, g, 16.6, 0.8 if i in (4, 5) else 0.7) for i, g in enumerate(groups)]
    seq.add_track("pad", ak.instrument(ak.pad_synth, attack=1.6, release=2.2, cutoff=1100.0, detune=6.0), pad,
                  volume=1.35, pan=0.0, fx=rev(2.5, 0.25, 0.6))
    # wind gusts (two tracks for width); note = band centre in Hz, length in beats
    gustsL = [(0.0, 420.0, 12.0, 0.7), (26.0, 520.0, 10.0, 0.55), (56.0, 380.0, 14.0, 0.75), (96.0, 460.0, 11.0, 0.6)]
    gustsR = [(12.0, 480.0, 11.0, 0.6), (40.0, 600.0, 9.0, 0.5), (74.0, 440.0, 12.0, 0.7), (110.0, 520.0, 12.0, 0.6)]
    seq.add_track("windL", wind, gustsL, volume=0.5, pan=-0.6)
    seq.add_track("windR", wind, gustsR, volume=0.5, pan=0.6)

    # flute phrases with long rests between them
    p1 = P("E5 == == == G5 == == == | A5 == == == == == E5 == | D5 == == == == == -- --", 0.5)
    p2 = P("A4 == C5 == D5 == == == | E5 == == == == == == == | G5 == E5 == D5 == == == | C5 == == == A4 == == ==", 0.5)
    p3 = P("A5 == == == G5 == E5 == | D5 == == == E5 == == == | C5 == D5 == E5 == == == | A4 == == == == == -- --", 0.5)
    p4 = P("E5 == == == D5 == C5 == | A4 == == == == == == == | G4 == A4 == C5 == == == | A4 == == == == == == ==", 0.5)
    fl = merge(at(vel(p1, 0.7), 2), at(vel(p2, 0.8), 8), at(vel(p3, 0.9), 18), at(vel(p4, 0.75), 26))
    seq.add_track("flute", ak.instrument(ak.flute, breath=0.45, vib_depth=0.3), fl, volume=0.45, pan=0.0,
                  fx=rev(2.8, 0.35, 0.5, predelay=0.03))

    # long erhu notes (slow, wide vibrato)
    er = merge(at(notes([(0.0, "E4", 8.0)]), 5), at(notes([(0.0, "A4", 6.0), (6.0, "G4", 2.0)]), 12),
               at(notes([(0.0, "C5", 4.0), (4.0, "D5", 2.0), (6.0, "A4", 2.0)]), 22),
               at(notes([(2.0, "E4", 6.0)]), 29))
    seq.add_track("erhu", ak.instrument(ak.erhu, vib_rate=4.3, vib_depth=0.5, attack=0.25, release=0.5), vel(er, 0.55),
                  volume=0.5, pan=0.2, fx=rev(2.5, 0.3, 0.5))

    # occasional wood block, distant taiko
    wb = merge(*[at(hits([b], 0.25, v), bar) for bar, b, v in
                 ((1, 2.0, .5), (5, 0.0, .45), (9, 3.0, .5), (13, 1.0, .4), (17, 0.0, .55), (20, 2.5, .4), (24, 0.0, .5), (29, 1.0, .45))])
    seq.add_track("block", ak.instrument(ak.wood_block, pitch=820), wb, volume=0.4, pan=0.4, fx=rev(2.2, 0.4, 0.4))
    tk = merge(at(hits([0.0], 1.0, .5), 0), at(hits([0.0], 1.0, .45), 16), at(hits([2.0], 1.0, .35), 24))
    seq.add_track("taiko", ak.instrument(ak.taiko, kind="low"), tk, volume=0.4, fx=rev(3.0, 0.45, 0.7))

    seq.master_fx.append(lp(11000))
    return save_loop(seq, "Mountain", audio_root, tmp_dir)


# ==========================================================================================
# Cave  --  eerie.  D minor pentatonic (D F G A C) over a D drone, 80 BPM, 32 bars.
# Low pad drones (tritone G# creeps in at bars 17-24), temple bell hits, water-drop plucks
# with cave echo, sparse low zither.
# ==========================================================================================
def build_cave(audio_root: str, tmp_dir: str) -> str:
    seq = ak.Sequencer(80)
    drones = [(0.0, ["D2", "A2"], 32.6, 0.8), (32.0, ["D2", "A2"], 32.6, 0.8), (64.0, ["D2", "G#2"], 32.6, 0.85),
              (96.0, ["D2", "A2"], 32.6, 0.8)]
    seq.add_track("drone", ak.instrument(ak.pad_synth, attack=2.5, release=3.0, cutoff=650.0, detune=9.0), drones,
                  volume=1.5, pan=0.0)
    # a second, higher drone voice that drifts: D3 for 16 bars, then C3 / G#3 / D3
    drift = [(0.0, "D3", 64.5, 0.35), (64.0, "C3", 16.5, 0.35), (80.0, "G#3", 16.5, 0.3), (96.0, "D3", 32.5, 0.35)]
    seq.add_track("drift", ak.instrument(ak.pad_synth, attack=3.0, release=3.0, cutoff=900.0, detune=14.0), drift,
                  volume=1.1, pan=0.0, fx=rev(3.5, 0.4, 0.7))
    # cave air: very low, slow gusts
    seq.add_track("air", wind, [(0.0, 170.0, 30.0, 0.5), (60.0, 150.0, 28.0, 0.45), (100.0, 190.0, 26.0, 0.5)],
                  volume=0.35, pan=-0.2)

    bells = [(0, "D4", .55), (8, "A3", .45), (12, "G3", .28), (16, "F4", .5), (24, "D4", .5), (28, "A3", .3)]
    seq.add_track("bell", ak.instrument(ak.temple_bell, use_note_freq=True, dur=4.5),
                  merge(*[at(notes([(0.0, n, 2.0)], v), b) for b, n, v in bells]),
                  volume=0.55, pan=0.1, fx=rev(4.0, 0.35, 0.6))

    # water drops: deterministic pseudo-random placement, two tracks for spread
    rng = np.random.default_rng(7)
    pitches = ["D6", "F6", "G6", "A6", "C7", "D7"]
    dripsL, dripsR = [], []
    t = 1.5
    while t < 128.0:
        ev = (round(t * 4) / 4.0, pitches[int(rng.integers(len(pitches)))], 0.5, float(0.35 + 0.5 * rng.random()))
        (dripsL if rng.random() < 0.5 else dripsR).append(ev)
        t += float(1.5 + 5.0 * rng.random())
    cave_echo = chain(lambda x: ak.delay(x, 0.37, 0.42, 0.4, damp=0.35), rev(3.2, 0.35, 0.5))
    seq.add_track("dripL", drip, dripsL, volume=0.5, pan=-0.45, fx=cave_echo)
    seq.add_track("dripR", drip, dripsR, volume=0.5, pan=0.45, fx=cave_echo)

    # sparse low zither: group starts, and a slow falling line in the tritone section
    z = merge(*[at(notes([(0.0, n, 2.0)], v), b) for b, n, v in
                ((0, "D3", .55), (4, "A2", .4), (8, "D3", .5), (12, "F3", .4), (20, "F3", .5), (21, "D3", .45),
                 (22, "C3", .45), (23, "A2", .5), (24, "D3", .55), (28, "A2", .4))])
    seq.add_track("zither", ak.instrument(ak.zither, bright=0.3, release=1.5), z, volume=0.6, pan=0.0,
                  fx=rev(3.5, 0.45, 0.6))

    seq.master_fx.append(lp(9000))
    return save_loop(seq, "Cave", audio_root, tmp_dir)


# ==========================================================================================
# Sect  --  청운검문 (dignified).  F major pentatonic (F G A C D), 84 BPM, 32 bars
# Form A(1-8) A'(9-16, erhu harmony) B(17-24) A''(25-32, erhu unison).  Slow rolled zither
# chords, flute melody, taiko on 1 and 3, low pad, soft temple bell at section starts.
# ==========================================================================================
def build_sect(audio_root: str, tmp_dir: str) -> str:
    seq = ak.Sequencer(84)
    V = {"F": ["F3", "C4", "F4", "A4"], "Dm": ["D3", "A3", "D4", "F4"], "Bb": ["A#2", "F3", "A#3", "D4"],
         "C": ["C3", "G3", "C4", "D4"], "Am": ["A2", "E3", "A3", "C4"], "Gm": ["G2", "D3", "G3", "A#3"]}
    chA = ["F", "Dm", "Bb", "C", "F", "Dm", "C", "F"]
    chB = ["Dm", "C", "Bb", "F", "Dm", "Bb", "C", "C"]
    chords = cat(chord_bars([V[c] for c in chA], (0.0, 2.0), 1.9, 0.85),
                 chord_bars([V[c] for c in chA], (0.0, 2.0), 1.9, 0.75),
                 chord_bars([V[c] for c in chB], (0.0, 2.0, 3.0), 1.9, 0.9),
                 chord_bars([V[c] for c in chA], (0.0, 2.0), 1.9, 0.9))
    seq.add_track("zither", ak.instrument(ak.zither, bright=0.5, release=1.0), chords, volume=0.75, pan=-0.15,
                  fx=rev(1.6, 0.2, 0.5))

    A = P("C5 == == == D5 == C5 == | A4 == == == == == F4 G4 |"
          "A4 == C5 == D5 == == == | C5 == == == G4 == == == |"
          "F5 == == == D5 == C5 == | A4 == C5 == D5 == == == |"
          "C5 == A4 == G4 == A4 == | F4 == == == == == -- --", 0.5)
    B = P("D5 == F5 == G5 == == == | A5 == G5 == F5 == == == |"
          "D5 == F5 == D5 == C5 == | A4 == == == == == C5 D5 |"
          "F5 == == == G5 == F5 == | D5 == C5 == A4 == == == |"
          "G4 == A4 == C5 == == == | C5 == == == == == -- --", 0.5)
    fl = cat(vel(A, 0.8), vel(A, 0.85), vel(B, 1.0), vel(A, 0.9))
    seq.add_track("flute", ak.instrument(ak.flute, vib_depth=0.2), fl, volume=0.45, pan=0.0, fx=rev(1.8, 0.25, 0.5))

    harm = notes([(0.0, "F4", 3.8), (4.0, "F4", 3.8), (8.0, "F4", 3.8), (12.0, "G4", 3.8), (16.0, "A4", 3.8),
                  (20.0, "F4", 3.8), (24.0, "G4", 3.8), (28.0, "F4", 3.8)], 0.55)
    erhu = merge(at(harm, 8), at(vel(A, 0.5), 24))
    seq.add_track("erhu", ak.instrument(ak.erhu, vib_depth=0.3, attack=0.12), erhu, volume=0.45, pan=0.25,
                  fx=rev(1.8, 0.22, 0.5))

    roots = {"F": "F2", "Dm": "D2", "Bb": "A#1", "C": "C2", "Am": "A1", "Gm": "G1"}
    pad = [(b * 4.0, roots[c], 4.2, 0.7) for b, c in enumerate(chA + chA + chB + chA)]
    seq.add_track("pad", ak.instrument(ak.pad_synth, attack=0.6, release=0.8, cutoff=700.0), pad, volume=1.0, pan=0.0)

    low = rep(hits([0.0], 1.0, 0.7), 32)
    mid = rep(hits([2.0], 1.0, 0.5), 32)
    low_B = rep(hits([2.0], 1.0, 0.45), 8)
    seq.add_track("taiko_low", ak.instrument(ak.taiko, kind="low"), merge(low, at(low_B, 16), at(low_B, 24)),
                  volume=0.6, fx=rev(1.2, 0.15, 0.6))
    seq.add_track("taiko_mid", ak.instrument(ak.taiko, kind="mid"), mid, volume=0.42, pan=0.12, fx=rev(1.2, 0.15, 0.6))
    seq.add_track("bell", ak.instrument(ak.temple_bell, freq=196.0, dur=3.5),
                  merge(at(hits([0.0], 1.0, .35), 0), at(hits([0.0], 1.0, .4), 16)), volume=0.45, pan=0.1)

    seq.master_fx.append(lp(12000))
    return save_loop(seq, "Sect", audio_root, tmp_dir)


# ==========================================================================================
# Dark  --  흑사방 (black-snake gang; low, tense).  A minor pentatonic (A C D E G) with an
# Andalusian bass descent (A G F E), 100 BPM, 32 bars.  Low pulsing plucked bass, erhu
# minor melody, sparse rim hits, dark pad, low zither doubling in A' and A''.
# ==========================================================================================
def build_dark(audio_root: str, tmp_dir: str) -> str:
    seq = ak.Sequencer(100)
    rootsA = ["A2", "A2", "A2", "A2", "G2", "G2", "F2", "E2"]
    rootsB = ["C3", "C3", "D3", "D3", "F2", "F2", "E2", "E2"]
    pulse = "R R@0.6 R@0.85 R@0.6 R R@0.6 R@0.85 N@0.7"
    pulse2 = "R R@0.6 R@0.85 O@0.55 R R@0.6 R@0.85 N@0.7"
    bass = cat(bassline(rootsA, pulse, 0.5, 0.9), bassline(rootsA, pulse2, 0.5, 0.95),
               bassline(rootsB, pulse2, 0.5, 1.0), bassline(rootsA, pulse2, 0.5, 1.0))
    seq.add_track("bass", ak.instrument(ak.pluck, bright=0.3, duty=0.35), bass, volume=0.5, pan=0.0, fx=lp(1800))

    pad = [(b * 4.0, r, 4.3, 0.55) for b, r in enumerate(rootsA + rootsA + rootsB + rootsA)]
    seq.add_track("pad", ak.instrument(ak.pad_synth, attack=0.8, release=1.0, cutoff=520.0, detune=7.0), pad,
                  volume=1.1, pan=0.0, fx=rev(2.0, 0.2, 0.7))

    A = P("E4 == == == G4 == E4 == | D4 == == == == == C4 D4 |"
          "E4 == == == A4 == G4 == | E4 == == == == == -- -- |"
          "G4 == == == A4 == G4 == | E4 == D4 == == == -- -- |"
          "C4 == D4 == E4 == == == | D4 == E4 == == == == ==", 0.5)
    B = P("G4 == == == A4 == C5 == | G4 == E4 == == == -- -- |"
          "A4 == == == C5 == D5 == | A4 == == == == == -- -- |"
          "C5 == D5 == C5 == A4 == | G4 == == == == == A4 == |"
          "G4 == E4 == D4 == E4 == | E4 == == == == == == ==", 0.5)
    A2 = P("E4 == == == G4 == E4 == | D4 == == == == == C4 D4 |"
           "E4 == == == A4 == G4 == | E4 == == == == == -- -- |"
           "G4 == A4 == C5 == A4 == | G4 == E4 == D4 == -- -- |"
           "C4 == D4 == E4 == G4 == | E4 == D4 == == == == ==", 0.5)
    erhu = cat(vel(A, 0.8), vel(A2, 0.9), vel(B, 1.0), vel(A2, 0.95))
    seq.add_track("erhu", ak.instrument(ak.erhu, vib_depth=0.45, vib_rate=4.8, glide=0.09), erhu, volume=0.55, pan=0.0,
                  fx=rev(1.8, 0.25, 0.6))

    rim = rep(hits([2.5], 0.25, 0.5) + ak.shift_pattern(hits([1.5], 0.25, 0.4) + hits([3.75], 0.25, 0.35), 4), 16)
    rimB = rep(hits([1.5, 3.5], 0.25, 0.5) + ak.shift_pattern(hits([0.5, 2.5, 3.75], 0.25, 0.45), 4), 4)
    seq.add_track("rim", ak.instrument(ak.taiko, kind="rim"), merge(rim, at(rimB, 16)), volume=0.4, pan=0.3,
                  fx=rev(1.4, 0.3, 0.5))
    low = rep(hits([0.0], 1.0, 0.55), 32)
    lowB = rep(hits([2.5], 1.0, 0.45), 8)
    seq.add_track("taiko", ak.instrument(ak.taiko, kind="low"), merge(low, at(lowB, 16)), volume=0.5, fx=rev(1.2, 0.15, 0.7))

    zl = [(b * 4.0, r, 1.5, 0.5) for b, r in list(enumerate(rootsA + rootsA + rootsB + rootsA)) if 8 <= b < 16 or b >= 24]
    seq.add_track("zither", ak.instrument(ak.zither, bright=0.3, release=0.8), zl, volume=0.5, pan=-0.2)

    seq.master_fx.append(lp(10000))
    return save_loop(seq, "Dark", audio_root, tmp_dir)


# ==========================================================================================
# Night  --  백로진의 밤 (the night the town burns; tragic).  D minor pentatonic (D F G A C)
# with Bb / A harmonies, 66 BPM, 32 bars.  Form A(1-8) A'(9-16) B(17-24) A''(25-32).
# Slow erhu melody over zither arpeggios, temple bell, low pad.
# ==========================================================================================
def build_night(audio_root: str, tmp_dir: str) -> str:
    seq = ak.Sequencer(66)
    V = {"Dm": ["D3", "A3", "D4", "F4", "A4"], "Bb": ["A#2", "F3", "A#3", "D4", "F4"], "F": ["F3", "C4", "F4", "A4", "C5"],
         "Gm": ["G3", "D4", "G4", "A#4", "D5"], "Am": ["A3", "E4", "A4", "C5", "E5"], "C": ["C3", "G3", "C4", "E4", "G4"],
         "A5": ["A3", "E4", "A4", "E5", "A5"]}
    chA = ["Dm", "Dm", "Bb", "F", "Gm", "Dm", "Am", "Dm"]
    chB = ["F", "C", "Dm", "Am", "Bb", "F", "Gm", "A5"]
    o8 = [0, 1, 2, 3, 4, 3, 2, 1]
    a8 = [1, .55, .7, .6, .85, .6, .7, .55]
    o16 = [0, 1, 2, 3, 4, 3, 2, 3, 4, 3, 2, 3, 4, 3, 2, 1]
    a16 = [1, .5, .65, .55, .8, .55, .65, .5, .85, .5, .65, .55, .8, .55, .65, .5]
    z = cat(vel(cat(*[arp(V[c], o8, 0.5, 1.0, a8) for c in chA]), 0.75),
            vel(cat(*[arp(V[c], o8, 0.5, 1.0, a8) for c in chA]), 0.85),
            vel(cat(*[arp(V[c], o16, 0.25, 1.0, a16) for c in chB]), 0.95),
            vel(cat(*[arp(V[c], o16, 0.25, 1.0, a16) for c in chA]), 0.85))
    seq.add_track("zither", ak.instrument(ak.zither, bright=0.45, release=0.9), z, volume=0.7, pan=-0.2,
                  fx=rev(2.2, 0.25, 0.5))

    A = P("-- -- -- -- A4 == == == | D5 == == == == == C5 == |"
          "D5 == F5 == D5 == == == | C5 == == == == == A4 == |"
          "G4 == == == A4 == C5 == | D5 == == == == == F5 == |"
          "E5 == D5 == C5 == == == | D5 == == == == == == ==", 0.5)
    B = P("F5 == == == G5 == A5 == | G5 == == == == == F5 == |"
          "D5 == F5 == A5 == G5 == | E5 == == == == == -- -- |"
          "D5 == F5 == D5 == C5 == | A4 == C5 == A4 == == == |"
          "G4 == == == A4 == A#4 == | A4 == == == == == == ==", 0.5)
    erhu = cat(vel(A, 0.7), vel(A, 0.85), vel(B, 1.0), vel(A, 0.9))
    seq.add_track("erhu", ak.instrument(ak.erhu, vib_depth=0.55, vib_rate=4.6, glide=0.1, attack=0.08), erhu,
                  volume=0.6, pan=0.1, fx=rev(2.6, 0.3, 0.5, predelay=0.02))

    bells = [(0, .5), (8, .45), (16, .6), (24, .5)]
    seq.add_track("bell", ak.instrument(ak.temple_bell, freq=146.8, dur=5.0),
                  merge(*[at(hits([0.0], 1.0, v), b) for b, v in bells] + [at(hits([2.0], 1.0, .4), 31)]),
                  volume=0.55, pan=0.15, fx=rev(3.0, 0.3, 0.6))

    roots = {"Dm": "D2", "Bb": "A#1", "F": "F2", "Gm": "G2", "Am": "A2", "C": "C2", "A5": "A2"}
    pad = [(b * 4.0, roots[c], 4.3, 0.5) for b, c in enumerate(chA + chA + chB + chA) if b >= 8]
    seq.add_track("pad", ak.instrument(ak.pad_synth, attack=0.8, release=1.0, cutoff=600.0), pad, volume=0.9, pan=0.0)

    seq.master_fx.append(lp(11000))
    return save_loop(seq, "Night", audio_root, tmp_dir)


# ==========================================================================================
# Demon  --  심마 (inner demon; dissonant).  C / F# tritone axis, 120 BPM, 16 bars.
# Detuned pads on tritone clusters, wailing erhu (glides from a tritone below), zither
# tremolo semitone clusters, irregular taiko groupings, gongs and tritone bells.
# ==========================================================================================
def build_demon(audio_root: str, tmp_dir: str) -> str:
    seq = ak.Sequencer(120)
    pads = [(0.0, ["C2", "F#2"], 16.4, 0.8), (16.0, ["C2", "F#2", "G2"], 16.4, 0.85), (32.0, ["C#2", "G2"], 16.4, 0.85),
            (48.0, ["C2", "F#2", "C#3"], 16.4, 0.95)]
    seq.add_track("pad", ak.instrument(ak.pad_synth, attack=1.0, release=1.5, cutoff=1500.0, detune=28.0), pads,
                  volume=1.3, pan=0.0, fx=rev(2.5, 0.3, 0.6))
    seq.add_track("pad_hi", ak.instrument(ak.pad_synth, attack=2.0, release=2.0, cutoff=2600.0, detune=45.0),
                  [(8.0, ["F#4", "G4"], 8.4, 0.35), (40.0, ["C#5", "D5"], 8.4, 0.4), (56.0, ["F#4", "C5"], 8.4, 0.45)],
                  volume=1.0, pan=0.3, fx=rev(3.0, 0.4, 0.5))

    wail = ak.instrument(ak.erhu, glide=0.35, from_semitones=-6, vib_depth=0.8, vib_rate=6.5, attack=0.08, release=0.3)
    er = merge(at(notes([(0.0, "C5", 2.0), (2.0, "F#5", 2.0)], 0.9), 0),
               at(P("F#5 == == == G5 == F#5 == | C5 == == == == == -- --", 0.5, velocity=0.9), 2),
               at(notes([(1.0, "C#5", 1.5), (2.5, "G5", 1.5)], 1.0), 5),
               at(notes([(0.0, "F#5", 3.0), (3.0, "F5", 1.0)], 1.0), 7),
               at(notes([(0.0, "C6", 2.0), (2.0, "F#5", 2.0)], 1.0), 8),
               at(P("G5 == F#5 == C5 == C#5 == | F#5 == == == == == == ==", 0.5, velocity=1.0), 10),
               at(notes([(0.5, "C#6", 1.5), (2.0, "G5", 2.0)], 1.0), 13),
               at(notes([(0.0, "F#5", 2.5), (2.5, "C5", 1.5)], 1.0), 15))
    seq.add_track("erhu", wail, er, volume=0.6, pan=0.0, fx=rev(2.2, 0.3, 0.5))

    trem = merge(*[at(notes([(0.0, ["C5", "C#5"], 2.0)], v), b) for b, v in ((1, .6), (6, .7), (9, .75), (12, .85), (14, .9))])
    seq.add_track("tremolo", tremolo_zither, trem, volume=0.5, pan=-0.3, fx=rev(1.5, 0.25, 0.5))

    grp = [[0.0, 0.75, 1.5, 2.25, 3.0, 3.75], [0.0, 0.5, 1.25, 2.0, 2.5, 3.25], [0.0, 0.75, 1.25, 2.0, 2.75, 3.5],
           [0.0, 0.5, 1.0, 1.75, 2.5, 3.0, 3.5]]
    low: Pattern = []
    mid: Pattern = []
    for b in range(16):
        g = grp[b % 4]
        base = 0.6 + 0.4 * (b / 15.0)
        low.extend(at(hits(g[::2], 0.5, base) + hits(g[1::2], 0.5, base * 0.7), b))
        mid.extend(at(hits([p + 0.25 for p in g[1::2]], 0.25, base * 0.6), b))
    rimb = merge(*[at(hits([3.0, 3.25, 3.5, 3.75], 0.25, 0.6 + 0.1 * (b // 4)), b) for b in (3, 7, 11, 13, 15)])
    seq.add_track("taiko_low", ak.instrument(ak.taiko, kind="low"), low, volume=0.7, fx=rev(1.0, 0.12, 0.7))
    seq.add_track("taiko_mid", ak.instrument(ak.taiko, kind="mid"), mid, volume=0.5, pan=0.2)
    seq.add_track("rim", ak.instrument(ak.taiko, kind="rim"), rimb, volume=0.4, pan=-0.3)

    seq.add_track("gong", ak.instrument(ak.gong, dur=3.5, freq=80.0, shimmer=0.9),
                  merge(at(hits([0.0], 1.0, .7), 0), at(hits([0.0], 1.0, .75), 8), at(hits([3.0], 1.0, .5), 15)),
                  volume=0.5, pan=-0.1)
    seq.add_track("bell", ak.bell, merge(at(notes([(0.0, ["C6", "F#6"], 1.0)], .5), 4), at(notes([(2.0, ["C#6", "G6"], 1.0)], .55), 11)),
                  volume=0.45, pan=0.35, fx=rev(2.5, 0.35, 0.4))
    seq.add_track("tbell", ak.instrument(ak.temple_bell, freq=370.0, dur=4.0), at(hits([0.0], 1.0, .45), 8), volume=0.5, pan=0.2)

    bass = P("C2 C2@0.6 -- C2 F#2@0.8 -- C2 C2@0.6 | C2 -- C2@0.7 F#2 -- C2 C#2@0.8 -- |"
             "C2 C2@0.6 -- C2 F#2@0.8 -- C2 C2@0.6 | C2 -- C2@0.7 G2 -- C#2 C2@0.8 --", 0.5)
    seq.add_track("bass", ak.nes_bass_tri, rep(bass, 4), volume=0.45, pan=0.0, fx=lp(1500))

    seq.master_fx.append(chain(lambda x: ak.soft_clip(x, 1.2), lp(12000)))
    return save_loop(seq, "Demon", audio_root, tmp_dir)


# ==========================================================================================
# Title  --  calm.  C major pentatonic (C D E G A), 76 BPM, 32 bars.  Arpeggiated zither
# throughout, flute melody entering at bar 9, soft pad, bell sparkles, distant taiko in B.
# ==========================================================================================
def build_title(audio_root: str, tmp_dir: str) -> str:
    seq = ak.Sequencer(76)
    V = {"C": ["C3", "G3", "C4", "E4", "G4"], "Am": ["A2", "E3", "A3", "C4", "E4"], "F": ["F3", "C4", "F4", "A4", "C5"],
         "G": ["G2", "D3", "G3", "A3", "D4"]}
    chA = ["C", "Am", "F", "G", "C", "Am", "F", "G"]
    chB = ["Am", "F", "C", "G", "Am", "F", "G", "G"]
    o8 = [0, 1, 2, 3, 4, 3, 2, 1]
    a8 = [1, .55, .7, .6, .85, .6, .7, .55]
    o8b = [0, 2, 1, 3, 4, 3, 1, 2]
    z = cat(vel(cat(*[arp(V[c], o8, 0.5, 1.0, a8) for c in chA]), 0.75),
            vel(cat(*[arp(V[c], o8, 0.5, 1.0, a8) for c in chA]), 0.85),
            vel(cat(*[arp(V[c], o8b, 0.5, 1.0, a8) for c in chB]), 0.95),
            vel(cat(*[arp(V[c], o8, 0.5, 1.0, a8) for c in chA]), 0.85))
    seq.add_track("zither", ak.instrument(ak.zither, bright=0.5, release=0.9), z, volume=0.75, pan=-0.15,
                  fx=rev(1.8, 0.22, 0.5))

    M = P("E5 == == == G5 == A5 == | G5 == == == E5 == == == |"
          "D5 == E5 == C5 == D5 == | D5 == == == == == -- -- |"
          "E5 == G5 == A5 == C6 == | A5 == G5 == E5 == == == |"
          "D5 == E5 == G5 == E5 == | D5 == == == C5 == == ==", 0.5)
    MB = P("A5 == == == G5 == E5 == | D5 == E5 == D5 == C5 == |"
           "E5 == == == G5 == == == | D5 == == == == == -- -- |"
           "C5 == D5 == E5 == G5 == | A5 == G5 == E5 == D5 == |"
           "D5 == E5 == D5 == C5 == | D5 == == == == == -- --", 0.5)
    M2 = P("E5 == == == G5 == A5 == | G5 == == == E5 == == == |"
           "D5 == E5 == C5 == D5 == | D5 == == == == == -- -- |"
           "E5 == G5 == A5 == C6 == | A5 == G5 == E5 == == == |"
           "D5 == E5 == G5 == E5 == | C5 == == == == == == ==", 0.5)
    fl = merge(at(vel(M, 0.8), 8), at(vel(MB, 0.95), 16), at(vel(M2, 0.85), 24))
    seq.add_track("flute", ak.instrument(ak.flute, vib_depth=0.22, breath=0.3), fl, volume=0.42, pan=0.0,
                  fx=rev(2.2, 0.28, 0.5, predelay=0.02))

    roots = {"C": "C3", "Am": "A2", "F": "F2", "G": "G2"}
    pad = [(b * 4.0, roots[c], 4.3, 0.5) for b, c in enumerate(chA + chA + chB + chA)]
    seq.add_track("pad", ak.instrument(ak.pad_synth, attack=0.9, release=1.0, cutoff=800.0), pad, volume=0.9, pan=0.0)

    sparkle = merge(at(notes([(3.5, "G6", 0.5)], .35), 3), at(notes([(3.5, "E6", 0.5)], .35), 11),
                    at(notes([(1.5, "A6", 0.5)], .4), 19), at(notes([(3.5, "G6", 0.5)], .35), 27))
    seq.add_track("bell", ak.bell, sparkle, volume=0.4, pan=0.4, fx=rev(2.5, 0.4, 0.4))
    tk = merge(*[at(hits([0.0], 1.0, .4), b) for b in range(16, 32, 2)])
    seq.add_track("taiko", ak.instrument(ak.taiko, kind="low"), tk, volume=0.4, fx=rev(2.5, 0.4, 0.7))

    seq.master_fx.append(lp(12000))
    return save_loop(seq, "Title", audio_root, tmp_dir)


# ==========================================================================================
# Victory  --  ~5 s sting (non-loop): gong + rising G major pentatonic fanfare (flute and
# zither in octaves), taiko roll, final rolled chord and a second gong; cosine fade-out.
# ==========================================================================================
def build_victory(audio_root: str, tmp_dir: str) -> str:
    seq = ak.Sequencer(120)
    fan = P("G5 A5 B5 D6 E6 == == == D6 == E6 == G6 == == == |"
            "A6 == G6 == E6 == D6 == G6 == == == == == == == |"
            "-- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --", 0.25)
    seq.add_track("flute", ak.instrument(ak.flute, vib_depth=0.3), fan, volume=0.5, pan=0.0, fx=rev(1.6, 0.25, 0.5))
    seq.add_track("zither", ak.instrument(ak.zither, bright=0.8), trn(fan, -12), volume=0.8, pan=-0.2, fx=rev(1.2, 0.18, 0.5))
    seq.add_track("zither2", ak.instrument(ak.zither, bright=0.6), trn(fan, -24), volume=0.5, pan=0.2)
    final = strum(["G3", "D4", "G4", "B4", "D5", "G5"], 6.0, 3.0, 1.0, 0.05)
    seq.add_track("chord", ak.instrument(ak.zither, bright=0.6, release=1.5), final, volume=0.7, pan=0.1, fx=rev(1.8, 0.25, 0.5))
    seq.add_track("gong", ak.instrument(ak.gong, dur=3.5, freq=96.0),
                  merge(hits([0.0], 1.0, .85), notes([(6.0, 130.0, 1.0)], .55)), volume=0.55, pan=-0.1)
    seq.add_track("taiko_low", ak.instrument(ak.taiko, kind="low"),
                  hits([0.0, 1.0, 2.0, 3.0], 0.5, .8) + hits([4.0, 6.0], 0.5, 1.0), volume=0.65)
    seq.add_track("taiko_mid", ak.instrument(ak.taiko, kind="mid"),
                  hits([2.5, 2.75, 3.25, 3.5, 3.75], 0.25, .6) + hits([5.0, 5.5], 0.25, .5), volume=0.5, pan=0.15)
    seq.add_track("block", ak.instrument(ak.wood_block, pitch=1100), hits([0.5, 1.5, 2.5, 3.5, 4.5, 5.5], 0.25, .5),
                  volume=0.35, pan=0.35)
    seq.master_fx.append(lp(13000))
    return save_sting(seq, "Victory", audio_root, tmp_dir, fade_out=1.2)


# ==========================================================================================
# GameOver  --  ~8 s sting (non-loop): low gong, descending D minor pentatonic erhu phrase
# echoed by low zither, low temple bell, dark pad; long cosine fade-out.
# ==========================================================================================
def build_gameover(audio_root: str, tmp_dir: str) -> str:
    seq = ak.Sequencer(60)
    seq.add_track("gong", ak.instrument(ak.gong, dur=5.0, freq=70.0, shimmer=0.7), hits([0.0], 1.0, .85), volume=0.6, pan=0.0)
    er = notes([(0.5, "A4", 1.0), (1.5, "G4", 1.0), (2.5, "F4", 1.0), (3.5, "D4", 1.5), (5.25, "C4", 0.75), (6.0, "A3", 2.0)], 0.9)
    seq.add_track("erhu", ak.instrument(ak.erhu, vib_depth=0.5, vib_rate=4.4, glide=0.12, release=0.6), er, volume=0.6, pan=0.1,
                  fx=rev(2.8, 0.3, 0.5))
    z = notes([(1.0, "D4", 1.0), (2.0, "C4", 1.0), (3.0, "A3", 1.0), (4.0, "D3", 1.5), (5.5, "A2", 1.0), (6.5, "D2", 2.0)], 0.6)
    seq.add_track("zither", ak.instrument(ak.zither, bright=0.35, release=1.5), z, volume=0.6, pan=-0.25, fx=rev(2.5, 0.3, 0.5))
    seq.add_track("bell", ak.instrument(ak.temple_bell, freq=146.8, dur=5.0), hits([5.0], 1.0, .5), volume=0.5, pan=0.2)
    seq.add_track("pad", ak.instrument(ak.pad_synth, attack=1.5, release=2.0, cutoff=500.0), notes([(0.0, ["D2", "A2"], 7.0)], .6),
                  volume=1.0)
    seq.add_track("taiko", ak.instrument(ak.taiko, kind="low"), hits([4.0], 1.0, .7), volume=0.5, fx=rev(2.0, 0.3, 0.7))
    seq.master_fx.append(lp(10000))
    return save_sting(seq, "GameOver", audio_root, tmp_dir, fade_out=2.0)


# ==========================================================================================
BUILDERS = [("Town", build_town), ("World", build_world), ("Battle", build_battle),
            ("Mountain", build_mountain), ("Cave", build_cave), ("Sect", build_sect),
            ("Dark", build_dark), ("Night", build_night), ("Demon", build_demon),
            ("Title", build_title), ("Victory", build_victory), ("GameOver", build_gameover)]


def build(audio_root: str, tmp_dir: str) -> list:
    """Write every music cue; returns the absolute paths written."""
    ak.seed(0)
    os.makedirs(os.path.join(audio_root, "Music"), exist_ok=True)
    os.makedirs(tmp_dir, exist_ok=True)
    out = []
    for name, fn in BUILDERS:
        ak.seed(0)
        out.append(os.path.abspath(fn(audio_root, tmp_dir)))
    return out


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(HERE)), "Assets", "InkPixel", "Audio")
    tmp = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(root), "_music_tmp")
    for p in build(root, tmp):
        print(p)
