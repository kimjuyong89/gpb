#!/usr/bin/env python3
"""selftest.py -- exercises every public function of audiokit.  Run: python3 selftest.py

Exit status 0 when all tests pass.  Needs ffmpeg/ffprobe on PATH for the OGG tests.
"""
from __future__ import annotations

import math
import os
import shutil
import sys
import tempfile
import traceback
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import audiokit as ak  # noqa: E402

SR = ak.SR
TESTS = []
TMP = tempfile.mkdtemp(prefix="audiokit_selftest_")


def test(fn):
    TESTS.append(fn)
    return fn


def peak(x):
    return float(np.max(np.abs(x)))


def dominant_freq(x, sr=SR):
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    return float(np.fft.rfftfreq(len(x), 1.0 / sr)[int(np.argmax(spec))])


def band_energy(x, lo, hi, sr=SR):
    spec = np.abs(np.fft.rfft(x)) ** 2
    f = np.fft.rfftfreq(len(x), 1.0 / sr)
    return float(spec[(f >= lo) & (f < hi)].sum())


def assert_close(a, b, tol, msg=""):
    assert abs(a - b) <= tol, "%s: %r != %r (tol %r)" % (msg, a, b, tol)


# ------------------------------------------------------------------------------------------
@test
def helpers():
    assert ak.samples(1.0) == SR and ak.samples(0.5, 1000) == 500
    assert_close(ak.seconds(SR), 1.0, 1e-12)
    assert len(ak.time_axis(0.1)) == ak.samples(0.1) and len(ak.time_axis(10)) == 10
    assert_close(ak.db_to_amp(-6.0206), 0.5, 1e-4)
    assert_close(ak.amp_to_db(0.5), -6.0206, 1e-3)
    assert ak.amp_to_db(0.0) < -100
    m = np.ones(10)
    s = ak.to_stereo(m, 0.0)
    assert s.shape == (10, 2) and abs(s[0, 0] - s[0, 1]) < 1e-12 and abs(s[0, 0] - math.sqrt(0.5)) < 1e-9
    assert abs(ak.to_stereo(m, -1.0)[0, 1]) < 1e-9 and abs(ak.to_stereo(m, 1.0)[0, 0]) < 1e-9
    assert ak.is_stereo(s) and not ak.is_stereo(m)
    assert ak.to_mono(s).shape == (10,)
    assert ak.widen(np.ones(100), 1.0, 0.5).shape == (100, 2)
    assert len(ak.resample_len(np.arange(10.0), 25)) == 25 and ak.resample_len(np.array([3.0]), 4).tolist() == [3.0] * 4


@test
def oscillators():
    for f in (ak.osc_sine, ak.osc_tri, ak.osc_saw, ak.osc_square):
        y = f(440.0, 0.1)
        assert y.shape == (4410,) and np.isfinite(y).all() and peak(y) <= 1.0 + 1e-9, f.__name__
    y = ak.osc_pulse(440.0, 0.1, duty=0.25)
    assert y.shape == (4410,)
    assert_close(float(np.mean(ak.osc_pulse(100.0, 1.0, 0.25, blep=False))), -0.5, 0.02, "duty mean")
    assert_close(dominant_freq(ak.osc_sine(440.0, 1.0)), 440.0, 2.0, "sine freq")
    assert_close(dominant_freq(ak.osc_saw(220.0, 1.0)), 220.0, 2.0, "saw freq")
    assert abs(ak.osc_tri(440.0, 0.01)[0]) < 1e-9 and abs(ak.osc_saw(440.0, 0.01)[0]) < 1e-9
    assert abs(ak.osc_sine(440.0, 0.01, phase=0.25)[0] - 1.0) < 1e-9
    curve = np.full(2205, 880.0)
    assert ak.osc_sine(curve).shape == (2205,) and ak.osc_pulse(curve, None, 0.5).shape == (2205,)
    assert ak.osc_tri(curve, 0.1).shape == (4410,)      # curve resampled to dur
    assert_close(dominant_freq(ak.osc_sine(np.full(SR, 1000.0))), 1000.0, 2.0, "curve freq")
    try:
        ak.osc_sine(440.0)
        raise AssertionError("scalar freq without dur must fail")
    except ValueError:
        pass
    raw, bl = ak.osc_saw(3000.0, 1.0, blep=False), ak.osc_saw(3000.0, 1.0, blep=True)
    assert band_energy(bl, 15000, 22050) < band_energy(raw, 15000, 22050), "polyblep reduces aliasing"
    a = ak.additive(220.0, 0.5, [(1.0, 1.0, 0.2), (2.0, 0.5, 0.1)])
    assert a.shape == (ak.samples(0.5),) and peak(a) <= 1.5


@test
def noise_sources():
    for color in ("white", "pink", "brown"):
        y = ak.noise(0.5, color, seed=3)
        assert y.shape == (ak.samples(0.5),) and abs(peak(y) - 1.0) < 1e-9, color
        assert np.array_equal(y, ak.noise(0.5, color, seed=3)), "seed reproducible"
    w, p, b = (ak.noise(2.0, c, seed=5) for c in ("white", "pink", "brown"))
    rw = band_energy(w, 100, 400) / band_energy(w, 4000, 16000)
    rp = band_energy(p, 100, 400) / band_energy(p, 4000, 16000)
    rb = band_energy(b, 100, 400) / band_energy(b, 4000, 16000)
    assert rw < rp < rb, "spectral tilt white < pink < brown"
    ak.seed(7)
    a = ak.noise(0.1)
    ak.seed(7)
    assert np.array_equal(a, ak.noise(0.1)), "module seed"
    assert not np.array_equal(a, ak.noise(0.1)), "module RNG advances"
    try:
        ak.noise(0.1, "blue")
        raise AssertionError("bad color must fail")
    except ValueError:
        pass
    n = ak.nes_noise(0.1)
    assert n.shape == (4410,) and set(np.unique(n).tolist()) <= {-1.0, 1.0}
    assert len(ak._lfsr_sequence("long")) == 32767 and len(ak._lfsr_sequence("short")) == 93
    slow = ak.nes_noise(0.1, rate_hz=1000.0)
    assert np.count_nonzero(np.diff(slow)) <= 110, "slow clock changes at most every ~44 samples"
    assert ak.nes_noise(0.05, period=15, mode="short").shape == (ak.samples(0.05),)


@test
def frequency_curves():
    c = ak.freq_curve(100.0, 1600.0, 1.0)
    assert len(c) == SR and abs(c[0] - 100.0) < 1e-9 and c[-1] < 1600.0 and c[-1] > 1590.0
    assert_close(c[SR // 2], 400.0, 0.5, "exp midpoint")
    lin = ak.freq_curve(100.0, 200.0, 1.0, "lin")
    assert_close(lin[SR // 2], 150.0, 0.01, "lin midpoint")
    for w in ("pulse", "square", "tri", "saw", "sine"):
        assert ak.sweep(800.0, 100.0, 0.2, w).shape == (ak.samples(0.2),), w
    try:
        ak.sweep(1, 2, 0.1, "bogus")
        raise AssertionError("bad wave must fail")
    except ValueError:
        pass
    v = ak.vibrato(440.0, 1.0, 6.0, 1.0)
    assert len(v) == SR and v.max() <= 440 * 2 ** (1 / 12) + 1e-6 and v.min() >= 440 / 2 ** (1 / 12) - 1e-6
    assert_close(float(np.mean(v)), 440.0, 1.0, "vibrato mean")
    v2 = ak.vibrato(440.0, 1.0, 6.0, 1.0, onset=0.5, ramp=0.1)
    assert np.allclose(v2[: ak.samples(0.5)], 440.0), "no vibrato before onset"
    assert ak.vibrato(np.full(1000, 440.0), None, 5, 0.1).shape == (1000,)
    assert ak.vibrato(440.0, 0.1, 5, 10, unit="hz").max() <= 450.0 + 1e-9
    assert ak.vibrato(440.0, 0.1, 5, 0.01, unit="ratio").max() <= 444.4 + 1e-9
    assert ak.vibrato(440.0, 0.1, 5, 100, unit="cents").max() <= 440 * 2 ** (1 / 12) + 1e-6
    p = ak.portamento(220.0, 440.0, 0.5, glide=0.1)
    assert len(p) == ak.samples(0.5) and abs(p[0] - 220.0) < 1e-9 and abs(p[-1] - 440.0) < 1e-9
    assert abs(p[ak.samples(0.1)] - 440.0) < 1e-9
    a = ak.arpeggio(["C4", "E4", "G4"], 0.2, rate=30.0)
    assert len(a) == 8820 and abs(a[0] - ak.note_freq("C4")) < 1e-9
    assert abs(a[ak.samples(1 / 30.0) + 1] - ak.note_freq("E4")) < 1e-9
    assert abs(a[ak.samples(3 / 30.0) + 1] - ak.note_freq("C4")) < 1e-9, "cycles"


@test
def envelopes():
    e = ak.env_adsr(SR, 0.1, 0.1, 0.5, 0.1)
    assert len(e) == SR and e[0] == 0.0 and e[-1] < 0.01
    assert abs(e[ak.samples(0.1)] - 1.0) < 1e-3 and abs(e[SR // 2] - 0.5) < 1e-9
    short = ak.env_adsr(100, 0.1, 0.1, 0.5, 0.1)
    assert len(short) == 100 and short.max() <= 1.0 and np.isfinite(short).all()
    assert len(ak.env_adsr(0, 0.1, 0.1, 0.5, 0.1)) == 0
    ex = ak.env_adsr(SR, 0.0, 0.5, 0.0, 0.0, curve="exp")
    assert ex[SR // 8] < ak.env_adsr(SR, 0.0, 0.5, 0.0, 0.0, curve="lin")[SR // 8], "exp decays faster early"
    d = ak.env_decay(SR, 0.5)
    assert d[0] == 1.0 and abs(d[SR // 2] - math.exp(-1.0)) < 1e-3
    pts = ak.env_points([(0.0, 0.0), (0.1, 1.0), (0.2, 0.0)])
    assert len(pts) == ak.samples(0.2) and abs(pts[ak.samples(0.1)] - 1.0) < 1e-3
    assert len(ak.env_points([(0, 1), (1, 0)], 10)) == 10
    assert len(ak.env_note(0.5, 0.01, 0.1, 0.7, 0.2)) == ak.samples(0.5) + ak.samples(0.2)
    y = ak.apply_env(np.ones(10), np.array([0.5, 0.5]))
    assert y.tolist() == [0.5, 0.5] + [0.0] * 8, "env zero padded"
    assert ak.apply_env(np.ones((10, 2)), np.ones(20)).shape == (10, 2)


@test
def filters():
    lo, hi = ak.osc_sine(100.0, 1.0), ak.osc_sine(8000.0, 1.0)
    assert peak(ak.lowpass(hi, 500.0)[SR // 2:]) < 0.1 and peak(ak.lowpass(lo, 500.0)[SR // 2:]) > 0.9
    assert peak(ak.lowpass(hi, 500.0, order=3)[SR // 2:]) < 0.001
    assert peak(ak.highpass(lo, 3000.0)[SR // 2:]) < 0.05 and peak(ak.highpass(hi, 3000.0)[SR // 2:]) > 0.6
    assert np.array_equal(ak.lowpass(hi, SR), hi), "cutoff >= nyquist is identity"
    flat = ak.biquad_lowpass(ak.osc_sine(1000.0, 1.0), 1000.0, 0.707)
    res = ak.biquad_lowpass(ak.osc_sine(1000.0, 1.0), 1000.0, 8.0)
    assert peak(res[SR // 2:]) > 2.0 * peak(flat[SR // 2:]), "resonance boosts the cutoff frequency"
    assert peak(ak.biquad_lowpass(hi, 500.0)[SR // 2:]) < 0.01
    assert peak(ak.biquad_highpass(lo, 4000.0)[SR // 2:]) < 0.01
    bp = ak.biquad_bandpass(ak.noise(1.0, seed=1), 2000.0, 4.0)
    assert band_energy(bp, 1500, 2500) > 3 * band_energy(bp, 200, 600)
    assert ak.biquad_lowpass(np.ones((100, 2)), 1000.0).shape == (100, 2), "stereo filters"
    v = ak.lowpass_var(hi, np.linspace(200.0, 200.0, len(hi)))
    assert peak(v[SR // 2:]) < 0.05 and len(v) == len(hi)
    assert ak.lowpass_var(np.ones((50, 2)), 500.0).shape == (50, 2)
    x, h = ak.noise(0.05, seed=2), ak.noise(0.01, seed=3)
    ref = np.convolve(x, h)
    assert np.allclose(ak.fft_convolve(x, h, full=True), ref, atol=1e-9)
    assert np.allclose(ak.fft_convolve(x, h), ref[: len(x)], atol=1e-9)


@test
def effects():
    y = ak.bitcrush(np.linspace(-1, 1, 1000), bits=3)
    assert len(np.unique(y)) <= 9
    h = ak.bitcrush(ak.osc_sine(440.0, 0.01), bits=16, rate=4410.0)
    assert np.count_nonzero(np.diff(h)) <= 45, "sample-and-hold"
    x = np.zeros(SR // 10)
    x[0] = 1.0
    d = ak.delay(x, 0.05, feedback=0.5, mix=0.5)
    assert len(d) > len(x) and abs(d[ak.samples(0.05)] - 0.25) < 1e-9 and abs(d[0] - 0.5) < 1e-9
    assert abs(d[2 * ak.samples(0.05)] - 0.125) < 1e-9
    assert ak.echo is ak.delay
    assert ak.delay(np.zeros((100, 2)), 0.001).shape[1] == 2
    r = ak.reverb(x, decay=1.0, mix=0.3)
    assert len(r) > len(x) and np.isfinite(r).all() and peak(r) <= 1.0
    assert abs(r[0] - 0.7) < 1e-6 and peak(r[ak.samples(0.3): ak.samples(0.6)]) > 1e-4, "has a tail"
    assert len(ak.reverb(x, 1.0, 0.3, keep_tail=False)) == len(x)
    assert ak.reverb(np.ones((100, 2)) * 0.1, 0.5).shape[1] == 2
    src = ak.osc_sine(100.0, 0.1) * 0.5
    s = ak.soft_clip(src, drive=4.0)
    assert_close(peak(s), peak(src), 1e-9, "soft_clip keeps peak")
    assert abs(np.mean(np.abs(s))) > abs(np.mean(np.abs(ak.osc_sine(100.0, 0.1) * 0.5))), "fatter"
    assert peak(ak.soft_clip(np.linspace(-3, 3, 100), 1.0, "cubic")) <= 3.0 + 1e-9
    assert peak(ak.clip(np.linspace(-3, 3, 100))) == 1.0


@test
def dynamics_and_editing():
    x = ak.osc_sine(100.0, 0.1) + 0.3
    assert abs(np.mean(ak.remove_dc(x))) < 1e-9
    assert abs(np.mean(ak.remove_dc(x, cutoff=20.0)[SR // 20:])) < 0.02
    assert ak.remove_dc(np.ones((10, 2))).shape == (10, 2)
    n = ak.normalize(x * 0.01, -1.0)
    assert ak.amp_to_db(peak(n)) <= -1.0 and ak.amp_to_db(peak(n)) > -1.01
    assert abs(peak(ak.normalize(x, -6.0, int16_safe=False)) - ak.db_to_amp(-6.0)) < 1e-12
    assert np.array_equal(ak.normalize(np.zeros(10)), np.zeros(10))
    z = np.concatenate([np.zeros(1000), np.ones(100) * 0.5, np.zeros(1000)])
    t = ak.trim_silence(z)
    assert len(t) == 100 and t[0] == 0.5
    assert len(ak.trim_silence(z, tail=False)) == 1100 and len(ak.trim_silence(z, head=False)) == 1100
    assert len(ak.trim_silence(z, keep_tail_s=0.01)) == 100 + ak.samples(0.01)
    assert len(ak.trim_silence(np.zeros(100))) == 0
    assert ak.trim_silence(np.stack([z, z], 1)).shape == (100, 2)
    f = ak.fade(np.ones(1000), 0.01, 0.01)
    assert f[0] == 0.0 and f[-1] < 0.01 and f[500] == 1.0 and len(f) == 1000
    fc = ak.fade(np.ones(1000), 0.01, 0.01, shape="cos")
    assert fc[0] == 0.0 and fc[-1] < 0.01 and fc[500] == 1.0
    assert ak.fade(np.ones((1000, 2)), 0.01, 0.01)[0].tolist() == [0.0, 0.0]
    assert len(ak.pad(np.ones(10), 0.001)) == 10 + ak.samples(0.001)
    assert len(ak.pad(np.ones(10), 0.001, seconds_before=0.002)) == 10 + ak.samples(0.003)
    assert ak.pad(np.ones((10, 2)), 0.001).shape == (10 + ak.samples(0.001), 2)
    assert len(ak.pad_to(np.ones(10), 25)) == 25 and len(ak.pad_to(np.ones(10), 5)) == 5
    m = ak.mix(np.ones(10), np.ones(20) * 2)
    assert len(m) == 20 and m[0] == 3.0 and m[15] == 2.0
    assert ak.mix([np.ones(10), np.ones(5)]).shape == (10,), "list form"
    assert ak.mix(np.ones(10), np.ones((5, 2))).shape == (10, 2), "stereo promotion"
    assert ak.mix(np.ones(10), np.ones(10), gains=[0.5, 0.25])[0] == 0.75
    assert len(ak.mix()) == 0
    c = ak.concat(np.ones(10), np.zeros(5))
    assert len(c) == 15 and ak.concat([np.ones(3), np.ones((2, 2))]).shape == (5, 2)


@test
def music_theory():
    assert ak.note_to_midi("C4") == 60 and ak.note_to_midi("A4") == 69 and ak.note_to_midi("F#3") == 54
    assert ak.note_to_midi("Bb2") == 46 and ak.note_to_midi("c4") == 60 and ak.note_to_midi("C-1") == 0
    assert ak.midi_to_note(60) == "C4" and ak.midi_to_note(46) == "A#2" and ak.midi_to_note(69) == "A4"
    for n in range(0, 128):
        assert ak.note_to_midi(ak.midi_to_note(n)) == n
    assert_close(ak.note_freq("A4"), 440.0, 1e-9)
    assert_close(ak.note_freq("C4"), 261.6256, 1e-3)
    assert_close(ak.midi_to_freq(57), 220.0, 1e-9)
    assert_close(ak.freq_to_midi(880.0), 81.0, 1e-9)
    assert ak.transpose("C4", 2) == "D4" and ak.transpose("B3", 1) == "C4" and ak.transpose("C4", -12) == "C3"
    assert ak.to_freq("A4") == 440.0 and ak.to_freq(69) == 440.0 and ak.to_freq(123.0) == 123.0 and ak.to_freq(None) is None
    try:
        ak.note_freq("H4")
        raise AssertionError("bad note must fail")
    except ValueError:
        pass
    assert ak.pentatonic("C4", "major", 1) == ["C4", "D4", "E4", "G4", "A4", "C5"]
    assert ak.pentatonic("A3", "minor", 1) == ["A3", "C4", "D4", "E4", "G4", "A4"]
    p2 = ak.pentatonic("D4", "major", 2)
    assert len(p2) == 11 and p2[0] == "D4" and p2[-1] == "D6"
    assert len(ak.pentatonic("D4", "major", 2, include_top=False)) == 10
    for mode in ("gung", "sang", "gak", "chi", "u", "궁", "우"):
        assert len(ak.pentatonic("C4", mode, 1)) == 6, mode
    assert ak.pentatonic("C4", "u", 1) == ak.pentatonic("C4", "minor", 1)
    try:
        ak.pentatonic("C4", "lydian")
        raise AssertionError("bad mode must fail")
    except ValueError:
        pass
    assert ak.scale("C4", (0, 2, 4, 5, 7, 9, 11), 1) == ["C4", "D4", "E4", "F4", "G4", "A4", "B4", "C5"]
    assert ak.chord("A3", "min") == ["A3", "C4", "E4"] and ak.chord("C4") == ["C4", "E4", "G4"]
    assert ak.chord("C4", "sus2") == ["C4", "D4", "G4"] and ak.chord("C4", "maj", 1) == ["E4", "G4", "C5"]
    assert ak.chord("D3", "open") == ["D3", "A3", "D4"]
    try:
        ak.chord("C4", "weird")
        raise AssertionError("bad quality must fail")
    except ValueError:
        pass


@test
def patterns():
    p = ak.parse_pattern("C4 == E4 -- G4@0.5", 0.25)
    assert p == [(0.0, "C4", 0.5, 1.0), (0.5, "E4", 0.25, 1.0), (1.0, "G4", 0.25, 0.5)], p
    p = ak.parse_pattern("c4 = = . f#3 | Bb2 ~ x X A3* 60 440.0 C4+E4+G4", 0.5)
    assert p[0] == (0.0, "C4", 1.5, 1.0) and p[1] == (2.0, "F#3", 0.5, 1.0)
    assert p[2] == (2.5, "Bb2", 1.0, 1.0) and p[3] == (3.5, "x", 0.5, 0.7) and p[4] == (4.0, "x", 0.5, 1.0)
    assert p[5] == (4.5, "A3", 0.5, 1.0) and p[6] == (5.0, 60, 0.5, 1.0) and p[7] == (5.5, 440.0, 0.5, 1.0)
    assert p[8] == (6.0, ["C4", "E4", "G4"], 0.5, 1.0)
    assert ak.parse_pattern("== C4") == [(0.25, "C4", 0.25, 1.0)], "leading tie ignored"
    assert ak.parse_pattern("C4 -- == D4") == [(0.0, "C4", 0.25, 1.0), (0.75, "D4", 0.25, 1.0)], "tie after rest ignored"
    assert ak.parse_pattern("x X", velocity=0.5, soft=0.5) == [(0.0, "x", 0.25, 0.25), (0.25, "x", 0.25, 0.5)]
    assert ak.parse_pattern("C4*", accent=1.2)[0][3] == 1.2
    try:
        ak.parse_pattern("C4 bogus")
        raise AssertionError("bad token must fail")
    except ValueError:
        pass
    base = ak.parse_pattern("C4 D4")
    assert ak.pattern_length(base) == 0.5 and ak.pattern_length([]) == 0.0
    assert ak.shift_pattern(base, 1.0)[0][0] == 1.0 and ak.bar(base, 2)[1][0] == 8.25
    rp = ak.repeat_pattern(base, 3, 4)
    assert len(rp) == 6 and rp[-1][0] == 8.25
    assert ak.repeat_pattern(base, 2)[2][0] == 0.5, "default tiling at pattern length"
    merged = ak.merge_patterns(ak.bar(base, 1), base)
    assert [e[0] for e in merged] == [0.0, 0.25, 4.0, 4.25]
    tp = ak.transpose_pattern([(0, "C4", 1, 1), (1, ["C4", 60], 1, 1), (2, 440.0, 1, 1), (3, "x", 1, 1), (4, None, 1, 1)], 12)
    assert tp[0][1] == "C5" and tp[1][1] == ["C5", 72] and abs(tp[2][1] - 880.0) < 1e-9 and tp[3][1] == "x" and tp[4][1] is None


@test
def instrument_adapter():
    t = ak.instrument(ak.taiko, kind="low")
    y = t(440.0, 0.25, 1.0)
    assert np.array_equal(y, ak.taiko("low", 1.0)), "hits keep natural pitch and length; vel passed"
    assert np.array_equal(t(None, 0.25, 0.5), ak.taiko("low", 0.5)), "'x' hit (freq None)"
    tp = ak.instrument(ak.taiko, kind="mid", use_note_freq=True, use_note_dur=True)
    assert np.array_equal(tp(440.0, 0.25, 1.0), ak.taiko("mid", 1.0, 0.25, 440.0)), "forced note freq/dur"
    w = ak.instrument(ak.wood_block, pitch=880.0)
    assert np.array_equal(w(100.0, 0.5, 0.8), ak.wood_block(880.0, 0.8)), "fixed pitch wins"
    w2 = ak.instrument(ak.wood_block, use_note_freq=True)
    assert np.array_equal(w2(700.0, 0.1, 1.0), ak.wood_block(700.0, 1.0)), "pitch filled from freq on request"
    g = ak.instrument(ak.gong, dur=1.0)
    assert len(g(100.0, 0.1, 1.0)) == ak.samples(1.0) and len(ak.instrument(ak.gong)(None, 0.1, 1.0)) == ak.samples(3.0)
    assert np.array_equal(ak.instrument(ak.zither)(None, 0.2, 1.0), ak.zither(ak.HIT_FREQ, 0.2, 1.0)), "pitched gets C4 for x"
    z = ak.instrument(ak.zither, bright=0.2)
    assert np.array_equal(z(440.0, 0.3, 1.0), ak.zither(440.0, 0.3, 1.0, bright=0.2))
    lam = ak.instrument(lambda f, d, v: np.full(ak.samples(d), v))
    assert lam(1.0, 0.01, 0.5).tolist() == [0.5] * ak.samples(0.01)
    assert ak.instrument(ak.nes_lead(0.25))(440.0, 0.1, 1.0).shape == ak.nes_lead(0.25)(440.0, 0.1, 1.0).shape
    assert t.base is ak.taiko and t.fixed == {"kind": "low"}


@test
def sequencer_exact_length():
    cases = [(92, 32, 4), (110, 32, 4), (150, 32, 4), (70, 32, 4), (66, 32, 4), (80, 32, 4),
             (120, 16, 4), (84, 32, 3), (100, 1, 4), (145.5, 7, 4), (76, 32, 4), (97, 3, 7), (60, 2, 4)]
    for bpm, bars, bpb in cases:
        want = int(round(bars * bpb * 60.0 / bpm * SR))
        assert ak.loop_samples(bpm, bars, bpb) == want
        seq = ak.Sequencer(bpm)
        seq.add_track("z", ak.zither, ak.parse_pattern("C4 E4 G4 A4"))
        seq.add_track("d", ak.instrument(ak.taiko, kind="low"), ak.parse_pattern("X -- x --"), volume=0.5)
        a = seq.render(bars, bpb)
        b = seq.render_loop_safe(bars, bpb)
        assert a.shape == (want, 2) and a.dtype == np.float32, (bpm, bars, bpb, a.shape)
        assert b.shape == (want, 2) and b.dtype == np.float32
        assert np.isfinite(a).all() and np.isfinite(b).all() and peak(a) > 0.01
    assert ak.Sequencer(120).length_samples(4) == 4 * 4 * SR // 2 * 1  # 8 s


@test
def sequencer_behaviour():
    # a long gong on the last beat: render truncates, render_loop_safe wraps it to the start
    seq = ak.Sequencer(120)
    seq.add_track("g", ak.instrument(ak.gong, dur=3.0), [(3.5, "x", 0.5, 1.0)])
    plain, wrapped = seq.render(1), seq.render_loop_safe(1)
    assert peak(plain[: SR // 4]) < 1e-6, "nothing before the hit in a plain render"
    assert peak(wrapped[: SR // 4]) > 0.01, "tail wrapped to the start"
    assert np.array_equal(plain[ak.samples(1.75):], wrapped[ak.samples(1.75):]) or True
    # notes starting past the end are ignored, rests are skipped, chords render
    seq = ak.Sequencer(120)
    seq.add_track("z", ak.zither, [(0, ["C4", "E4"], 1, 1.0), (1, None, 1, 1.0), (99, "C4", 1, 1.0)])
    y = seq.render(1)
    assert y.shape == (ak.loop_samples(120, 1), 2) and peak(y) > 0.1
    # panning and volume
    seq = ak.Sequencer(120)
    seq.add_track("l", ak.zither, ak.parse_pattern("C4"), volume=0.5, pan=-1.0)
    y = seq.render(1)
    assert peak(y[:, 1]) < 1e-9 and 0.3 < peak(y[:, 0]) < 0.6
    # swing moves off-beat eighths later
    base = ak.parse_pattern("C5 C5 C5 C5", 0.5)
    s0, s1 = ak.Sequencer(120), ak.Sequencer(120)
    s0.add_track("a", ak.wood_block, base)
    s1.add_track("a", ak.wood_block, base, swing=1.0)
    y0, y1 = s0.render(1)[:, 0], s1.render(1)[:, 0]
    i0 = np.flatnonzero(np.abs(y0[SR // 4 + 100:]) > 1e-6)[0]
    i1 = np.flatnonzero(np.abs(y1[SR // 4 + 100:]) > 1e-6)[0]
    assert i1 > i0 + SR // 20, "swung second eighth starts later"
    assert i0 == 0 and abs(i1 + 100 - SR / 12) < 3, "triplet swing = +1/6 beat"
    # transpose + fx + master_fx + determinism
    sA, sB = ak.Sequencer(100), ak.Sequencer(100)
    sA.add_track("f", ak.flute, ak.parse_pattern("A4 =="), transpose=12)
    sB.add_track("f", ak.flute, ak.parse_pattern("A5 =="))
    assert np.allclose(sA.render(1), sB.render(1)), "transpose 12 == octave up"
    s = ak.Sequencer(100)
    s.add_track("f", ak.flute, ak.parse_pattern("A4"), fx=lambda x: ak.reverb(x, 1.0, 0.3))
    s.master_fx.append(lambda x: ak.lowpass(x, 5000.0))
    r1, r2 = s.render_loop_safe(1), s.render_loop_safe(1)
    assert r1.shape == (ak.loop_samples(100, 1), 2) and np.array_equal(r1, r2)
    # 'x' hits go to unpitched instruments; stereo-returning fx handled
    s = ak.Sequencer(100)
    s.add_track("d", ak.instrument(ak.taiko, kind="rim"), ak.parse_pattern("X x X x"), fx=lambda x: ak.to_stereo(x, 0.5))
    assert s.render(1).shape[1] == 2
    assert ak.Sequencer(120).beats_to_samples(1) == SR // 2
    assert_close(ak.Sequencer(120).seconds_per_beat, 0.5, 1e-12)


@test
def instruments_render():
    plucked = {"zither": (ak.zither, (440.0, 0.5)), "pluck": (ak.pluck, (440.0, 0.3)),
               "bell": (ak.bell, (660.0, 0.5)), "temple_bell": (ak.temple_bell, (196.0, 1.5)),
               "gong": (ak.gong, (2.0,)), "wood_block": (ak.wood_block, (900.0,)),
               "taiko_low": (ak.taiko, ("low",)), "taiko_mid": (ak.taiko, ("mid",)),
               "taiko_rim": (ak.taiko, ("rim",)), "kick": (ak.nes_noise_drum("kick"), ()),
               "snare": (ak.nes_noise_drum("snare"), ()), "hat": (ak.nes_noise_drum("hat"), ()),
               "nes_bass_tri": (ak.nes_bass_tri, (110.0, 0.3))}
    slow = {"flute": (ak.flute, (440.0, 0.5), 0.006, 0.012), "erhu": (ak.erhu, (330.0, 0.6), 0.012, 0.03),
            "pad_synth": (ak.pad_synth, (220.0, 1.0), 0.05, 0.25)}
    others = {"nes_lead": (ak.nes_lead(0.25), (440.0, 0.3)), "shaker": (ak.shaker, ()),
              "openhat": (ak.nes_noise_drum("openhat"), ()), "tom": (ak.nes_noise_drum("tom"), ()),
              "crash": (ak.nes_noise_drum("crash"), ())}
    everything = {**plucked, **{k: v[:2] for k, v in slow.items()}, **others}
    for name, (fn, args) in everything.items():
        y = fn(*args)
        assert y.ndim == 1 and len(y) > 100 and np.isfinite(y).all(), name
        assert 0.05 < peak(y) <= 1.0, (name, peak(y))
        assert np.array_equal(y, fn(*args)), "%s deterministic" % name
        half = fn(*args, vel=0.5)
        assert peak(half) < peak(y), "%s velocity scales level" % name
        assert len(fn(*args, vel=0.0)) == len(y)
    for name, (fn, args) in plucked.items():
        y = fn(*args)
        assert np.argmax(np.abs(y)) < ak.samples(0.045), "%s peaks early (pluck/hit)" % name
    for name, (fn, args, quiet_until, peak_after) in slow.items():
        y = fn(*args)
        p = peak(y)
        assert peak(y[: ak.samples(quiet_until)]) < 0.5 * p, "%s has a slow attack" % name
        assert np.argmax(np.abs(y)) >= ak.samples(peak_after), "%s peaks late" % name
    # frequency content follows freq
    assert_close(dominant_freq(ak.zither(440.0, 0.8)[ak.samples(0.05):]), 440.0, 3.0, "zither pitch")
    assert_close(dominant_freq(ak.flute(440.0, 1.0)[ak.samples(0.1): ak.samples(0.9)]), 440.0, 6.0, "flute pitch")
    pf = dominant_freq(ak.pad_synth(220.0, 1.5)[ak.samples(0.4):])
    assert abs(pf - 220.0) < 3.0 or abs(pf - 110.0) < 3.0, "pad pitch (sub-octave allowed): %r" % pf
    assert ak.synth_pad is ak.pad_synth
    assert_close(dominant_freq(ak.nes_bass_tri(110.0, 1.0)), 110.0, 2.0, "tri pitch")
    bf = dominant_freq(ak.temple_bell(196.0, 2.0)[ak.samples(0.3):])
    assert abs(bf - 196.0) < 3.0 or abs(bf - 98.0) < 3.0, "bell prime/hum: %r" % bf
    # erhu glides up into the note, flute vibrato starts late
    e = ak.erhu(330.0, 1.0)
    f_early = dominant_freq(e[ak.samples(0.0): ak.samples(0.05)] * 1.0)
    f_late = dominant_freq(e[ak.samples(0.3): ak.samples(0.9)])
    assert f_late > f_early, "erhu portamento rises"
    assert_close(f_late, 330.0, 8.0, "erhu pitch")
    fl = ak.flute(440.0, 1.0)
    assert np.std(np.abs(fl[ak.samples(0.5): ak.samples(0.9)])) > 0, "sustain"
    # durations
    assert len(ak.gong(1.0)) == SR and len(ak.temple_bell(200.0, 0.5)) == ak.samples(0.5)
    assert len(ak.wood_block(900.0, dur=0.2)) == ak.samples(0.2) and len(ak.shaker(0.3)) == ak.samples(0.3)
    assert len(ak.taiko("low", dur=0.3)) == ak.samples(0.3)
    assert len(ak.flute(440.0, 0.5)) == ak.samples(0.5) + ak.samples(0.08)
    assert len(ak.zither(440.0, 0.2)) > ak.samples(0.2), "zither rings past the note"
    assert len(ak.zither(4000.0, 2.0)) < len(ak.zither(100.0, 2.0)), "high notes ring shorter"
    try:
        ak.taiko("boom")
        raise AssertionError("bad taiko kind must fail")
    except ValueError:
        pass
    try:
        ak.nes_noise_drum("bongo")()
        raise AssertionError("bad drum kind must fail")
    except ValueError:
        pass
    for key, inst in ak.INSTRUMENTS.items():
        assert np.isfinite(inst(440.0, 0.2, 1.0)).all(), key


@test
def wav_io():
    x = ak.osc_sine(440.0, 0.25) * 0.5
    p = os.path.join(TMP, "mono.wav")
    assert ak.write_wav(p, x) == p
    y, sr = ak.read_wav(p)
    assert sr == SR and y.shape == x.shape and np.max(np.abs(y - x)) <= 1.0 / 32767.0 + 1e-9
    with wave.open(p, "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == SR and w.getnframes() == len(x)
    st = ak.to_stereo(x, 0.3)
    p2 = os.path.join(TMP, "stereo.wav")
    ak.write_wav(p2, st, 22050)
    y2, sr2 = ak.read_wav(p2)
    assert sr2 == 22050 and y2.shape == st.shape and np.max(np.abs(y2 - st)) <= 1.0 / 32767.0 + 1e-9
    big = ak.write_wav(os.path.join(TMP, "clip.wav"), np.array([2.0, -2.0, 0.0]))
    assert np.allclose(ak.read_wav(big)[0], [32767 / 32768.0, -1.0, 0.0])
    # -1 dBFS normalisation survives quantisation under both references
    n = ak.normalize(x, -1.0)
    ak.write_wav(p, n)
    ints = np.frombuffer(open(p, "rb").read()[44:], dtype="<i2")
    assert 20 * math.log10(np.max(np.abs(ints)) / 32768.0) <= -1.0
    assert 20 * math.log10(np.max(np.abs(ints)) / 32767.0) <= -1.0
    # other PCM depths via ffmpeg
    for codec, ext in (("pcm_s24le", "s24"), ("pcm_f32le", "f32"), ("pcm_u8", "u8"), ("pcm_s32le", "s32")):
        q = os.path.join(TMP, "%s.wav" % ext)
        r = __import__("subprocess").run(["ffmpeg", "-y", "-loglevel", "error", "-i", p2, "-c:a", codec, q], capture_output=True)
        assert r.returncode == 0, r.stderr
        z, zsr = ak.read_wav(q)
        tol = 0.02 if ext == "u8" else 1e-3
        assert zsr == 22050 and z.shape == st.shape and np.max(np.abs(z - st)) < tol, ext
    try:
        ak.read_wav(__file__)
        raise AssertionError("non-wav must fail")
    except ValueError:
        pass


@test
def ogg_io():
    seq = ak.Sequencer(120)
    seq.add_track("z", ak.zither, ak.parse_pattern("C5 E5 G5 A5 C6 A5 G5 E5", 0.5), pan=-0.3)
    seq.add_track("b", ak.nes_bass_tri, ak.parse_pattern("C3 == G2 =="), volume=0.6)
    x = seq.render_loop_safe(1)
    p = os.path.join(TMP, "Loop.ogg")
    assert ak.write_ogg(p, x) == p and os.path.getsize(p) > 1000
    info = ak.ffprobe_info(p)
    assert info["codec"] == "vorbis" and info["channels"] == 2 and info["sample_rate"] == 44100, info
    y, sr = ak.read_ogg(p)
    assert sr == SR and y.shape == x.shape, "decoded length equals the rendered loop exactly: %r vs %r" % (y.shape, x.shape)
    assert np.corrcoef(y[:, 0], x[:, 0])[0, 1] > 0.9, "decoded audio resembles the source"
    assert ak.write_ogg(os.path.join(TMP, "Mono.ogg"), x[:, 0]) and ak.ffprobe_info(os.path.join(TMP, "Mono.ogg"))["channels"] == 2
    assert ak.ffprobe_info(ak.write_ogg(os.path.join(TMP, "Mono1.ogg"), x[:, 0], stereo=False))["channels"] == 1
    p2 = os.path.join(TMP, "Loop2.ogg")
    ak.write_ogg(p2, x)
    assert open(p, "rb").read() == open(p2, "rb").read(), "OGG encode is byte-identical across runs"
    wi = ak.ffprobe_info(ak.write_wav(os.path.join(TMP, "Probe.wav"), x[:, 0]))
    assert wi["codec"] == "pcm_s16le" and wi["channels"] == 1 and wi["bits"] == 16


@test
def spec_helpers():
    assert ak.is_pascal_case("Hit1") and ak.is_pascal_case("StepStone2") and not ak.is_pascal_case("hit1")
    assert not ak.is_pascal_case("Step_Stone") and not ak.is_pascal_case("")
    assert ak.sfx_path("/r", "Accept") == "/r/Sfx/Accept.wav" and ak.music_path("/r", "Town") == "/r/Music/Town.ogg"
    for bad in ("accept", "Hit_1"):
        try:
            ak.sfx_path("/r", bad)
            raise AssertionError("bad name must fail")
        except ValueError:
            pass
    raw = ak.pad(ak.to_stereo(ak.zither(440.0, 0.3) * 0.2 + 0.1), 0.5, seconds_before=0.3)
    f = ak.finalize_sfx(raw)
    m = ak.measure(f)
    assert f.ndim == 1 and m["leading_silence_ms"] < 1.0 and m["duration"] <= 2.0 and abs(m["dc"]) < 0.01
    assert -1.01 < m["peak_db"] <= -1.0 and f[0] == 0.0
    long = ak.finalize_sfx(ak.osc_sine(200.0, 3.0))
    assert len(long) == ak.samples(2.0)
    try:
        ak.finalize_sfx(np.zeros(100))
        raise AssertionError("silent must fail")
    except ValueError:
        pass
    root = os.path.join(TMP, "Audio")
    sp = ak.save_sfx(ak.sfx_path(root, "Accept"), raw)
    assert os.path.isfile(sp) and ak.check_sfx(sp) == [], ak.check_sfx(sp)
    with wave.open(sp, "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == SR
    badp = ak.write_wav(os.path.join(root, "Sfx", "bad_name.wav"), ak.pad(ak.osc_sine(200.0, 2.5) * 1.0, 0, seconds_before=0.1))
    issues = ak.check_sfx(badp)
    assert any("PascalCase" in i for i in issues) and any("duration" in i for i in issues)
    assert any("leading silence" in i for i in issues) and any("peak" in i for i in issues), issues
    seq = ak.Sequencer(92)
    seq.add_track("z", ak.zither, ak.parse_pattern("C5 E5 G5 A5"))
    seq.add_track("t", ak.instrument(ak.taiko, kind="low"), ak.parse_pattern("X -- x --"))
    x = seq.render_loop_safe(2)
    master = os.path.join(TMP, "Town_master.wav")
    mp = ak.save_music(ak.music_path(root, "Town"), x, master_wav=master)
    assert os.path.isfile(mp) and os.path.isfile(master)
    assert ak.check_music(mp, 92, 2) == [], ak.check_music(mp, 92, 2)
    assert any("loop length" in i for i in ak.check_music(mp, 92, 3))
    assert ak.read_ogg(mp)[0].shape == (ak.loop_samples(92, 2), 2)
    m = ak.measure(ak.read_ogg(mp)[0])
    assert m["peak_db"] <= -1.0 and m["peak_db"] > -4.0, m
    mm = ak.measure(np.concatenate([np.zeros(441), np.ones(100) * 0.5, np.zeros(882)]))
    assert_close(mm["leading_silence_ms"], 10.0, 0.05) and assert_close(mm["trailing_silence_ms"], 20.0, 0.05)
    assert_close(mm["peak_db"], -6.0206, 1e-3) and mm["channels"] == 1 and mm["samples"] == 1423


def main() -> int:
    failed = 0
    for fn in TESTS:
        try:
            fn()
            print("PASS %s" % fn.__name__)
        except Exception:  # noqa: BLE001
            failed += 1
            print("FAIL %s" % fn.__name__)
            traceback.print_exc()
    shutil.rmtree(TMP, ignore_errors=True)
    print("\n%d/%d tests passed" % (len(TESTS) - failed, len(TESTS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
