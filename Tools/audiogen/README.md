# Tools/audiogen — InkPixel audio generators

numpy-only synthesis for the 수묵 wuxia pack (spec: `Docs/ASSET_SPEC.md` §6 and §8).
Python 3.13 + numpy; `ffmpeg`/`ffprobe` on PATH for OGG. No scipy, no Unity.

```
Tools/audiogen/
  audiokit.py     the toolkit (oscillators, envelopes, filters, FX, music theory, Sequencer,
                  instruments, WAV/OGG I/O, spec checks)
  gen_*.py        generators — one or more per family (gen_sfx.py, gen_music.py, ...)
  build_all.py    runs every gen_*.py (sorted) and prints a summary; non-zero exit on failure
  analyze.py      duration / peak / RMS / leading silence / format of every file in a folder
  selftest.py     unit tests for audiokit (python3 selftest.py)
  README.md       this file
```

## Module contract (binding for every `gen_*.py`)

```python
# Tools/audiogen/gen_sfx.py
import audiokit as ak

LOOP_INFO = {}                         # music generators: {"Town": {"bpm": 92, "bars": 32, "beats_per_bar": 4}}

def build(audio_root: str, tmp_dir: str) -> list[str]:
    """Write files, return the absolute paths written."""
    ak.seed(0)                         # optional; build_all reseeds before every generator anyway
    out = []
    x = ak.apply_env(ak.osc_pulse(ak.note_freq("A5"), 0.12, duty=0.25), ak.env_decay(ak.samples(0.12), 0.04))
    out.append(ak.save_sfx(ak.sfx_path(audio_root, "Accept"), x))
    return out
```

* `build(audio_root, tmp_dir)` → `list[str]`. `audio_root` is `Assets/InkPixel/Audio`
  (default `/home/user/gpb/Assets/InkPixel/Audio`); `tmp_dir` exists and is for scratch
  files only (WAV masters of music, intermediate renders). **Nothing but the final `.wav` /
  `.ogg` files goes under `audio_root`.**
* **SFX** → `audio_root + '/Sfx/<Name>.wav'`: PascalCase name, mono, 44100 Hz, 16-bit,
  peak −1 dBFS, no DC, ≤ 2.0 s, trimmed (no leading silence), 2 ms fade in/out.
  `ak.save_sfx(path, x)` applies all of this (`finalize_sfx` = to mono → remove DC → trim at
  −60 dB → clamp to 2 s → 2 ms fades → normalise to −1 dBFS, 16-bit safe) and writes the file.
  `ak.sfx_path(audio_root, "Hit1")` builds and validates the path.
* **Music** → `audio_root + '/Music/<Name>.ogg'`: PascalCase, stereo, 44100 Hz, OGG Vorbis
  q6. Loops are whole bars: **exactly** `round(bars*beats_per_bar*60/bpm*SR)` samples, no end
  fade — `Sequencer.render_loop_safe(bars)` returns precisely that and wraps note tails around
  to the start. `ak.save_music(path, x, master_wav=os.path.join(tmp_dir, "Town.wav"))`
  normalises to −1.5 dBFS (Vorbis overshoot headroom so the decoded peak stays ≤ −1 dBFS),
  writes the OGG and, optionally, the WAV master into `tmp_dir`. Non-loop stings
  (`Victory`, `GameOver`) may fade out (`ak.fade(x, 0, 0.5)`), still via `save_music`.
* Expose `LOOP_INFO` so `build_all.py` / `analyze.py --check` can verify loop lengths
  (`"loop": False` for stings).
* Determinism: fixed seeds only. `ak.noise(dur, color, seed=N)` for explicit seeds, otherwise
  the module RNG that `ak.seed(n)` resets. Instruments seed their own noise from
  (freq, dur, vel). OGG encoding is byte-identical across runs (`-bitexact`).
* Never commit WAV masters of music; never write outside `audio_root` and `tmp_dir`.

Build and check:

```
python3 Tools/audiogen/build_all.py            # all generators
python3 Tools/audiogen/build_all.py sfx        # only gen_sfx.py (name / substring / file name)
python3 Tools/audiogen/build_all.py --list     # show generators
python3 Tools/audiogen/analyze.py Assets/InkPixel/Audio --check
python3 Tools/audiogen/selftest.py
```

`build_all.py` exit codes: 0 OK, 1 a generator raised / returned garbage, 2 spec violations
(use `--lenient` to only print them, `--no-check` to skip the checks).

## audiokit at a glance

Signals are float64 arrays in −1..1, mono `(n,)` or stereo `(n, 2)`; `SR = 44100`.

| group | functions |
|---|---|
| time/level | `samples(s)`, `seconds(n)`, `time_axis`, `db_to_amp`, `amp_to_db`, `to_stereo(x, pan)`, `to_mono`, `widen` |
| oscillators | `osc_pulse(freq, dur, duty)`, `osc_square`, `osc_tri`, `osc_saw`, `osc_sine` — `freq` may be a scalar **or a frequency-curve array** (then `dur` may be `None`); `additive(freq, dur, partials)` |
| noise | `noise(dur, 'white'/'pink'/'brown', seed=)`, `nes_noise(dur, rate_hz / period=0..15, mode='long'/'short')` (NES LFSR) |
| curves | `freq_curve(f0, f1, dur, 'exp'/'lin')`, `sweep(f0, f1, dur, wave, duty, curve)`, `vibrato(freq, dur, rate, depth_semitones, onset=, ramp=)`, `portamento(f0, f1, dur, glide)`, `arpeggio(notes, dur, rate)` |
| envelopes | `env_adsr(n, a, d, s, r, curve='lin'/'exp')`, `env_decay(n, tau)`, `env_points([(t, v), ...])`, `env_note(dur, a, d, s, r)` (sustain to `dur`, then release), `apply_env(x, env)` |
| filters | `lowpass(x, hz, order=)`, `highpass`, `lowpass_var(x, cutoff_curve)`, `biquad_lowpass(x, hz, q)`, `biquad_highpass`, `biquad_bandpass(x, hz, q)`, `fft_convolve` |
| effects | `bitcrush(x, bits, rate)`, `delay/echo(x, time, feedback, mix)`, `reverb(x, decay, mix, damp)` (Schroeder combs+allpasses), `soft_clip(x, drive)`, `clip` |
| editing | `mix(*xs)` (sum, longest wins, mono→stereo promotion), `concat`, `pad(x, after, seconds_before=)`, `pad_to(x, n)`, `fade(x, in_s, out_s)`, `normalize(x, peak_db=-1)`, `trim_silence(x, -60)`, `remove_dc`, `resample_len` |
| theory | `note_freq('F#3')`, `note_to_midi`, `midi_to_note`, `midi_to_freq`, `freq_to_midi`, `to_freq`, `transpose('C4', 2)`, `scale`, `pentatonic(root, mode, octaves)`, `chord(root, quality)` |
| sequencing | `Sequencer(bpm)`, `parse_pattern`, `bar`, `shift_pattern`, `repeat_pattern`, `merge_patterns`, `transpose_pattern`, `pattern_length`, `instrument(fn, **fixed)`, `loop_samples(bpm, bars)` |
| I/O | `write_wav`, `read_wav`, `write_ogg(path, x, sr, quality=6)`, `read_ogg`, `ffprobe_info`, `measure(x)` |
| spec | `finalize_sfx`, `save_sfx`, `save_music`, `sfx_path`, `music_path`, `is_pascal_case`, `check_sfx(path)`, `check_music(path, bpm, bars)` |

Filters are IIR designs rendered as truncated impulse responses and FFT-convolved, so they
are fast on whole tracks; `lowpass_var` (per-sample cutoff) is a Python loop — use it on
short SFX only.

## Instruments

Pitched instruments are plain callables `(freq, dur, vel=1.0, **options) -> mono array`
and return the note **plus its natural release** (longer than `dur`). Velocity 0..1 scales
level (and brightness for the zither). Peaks at vel 1.0 are ≈ 0.5–0.9, so sums of a few
voices stay under 1.0 before the master normalise.

| instrument | character | notes |
|---|---|---|
| `zither(freq, dur, vel, bright=0.7, release=0.5)` | 가야금/古箏 pluck: sharp attack, fast exponential decay, 2–3 slightly detuned harmonics, +35-cent pitch drop at onset, pick noise | lead/arpeggio voice of `Town`, riff voice of `Battle`; rings ≤ dur+release, shorter for high notes |
| `flute(freq, dur, vel, breath=0.35, vib_depth=0.25)` | 대금/dizi: sine+triangle, breath burst at onset, 20 ms attack, vibrato after 150 ms | `World`, `Mountain` lead |
| `erhu(freq, dur, vel, glide=0.07, vib_depth=0.45)` | 二胡: low-passed saw, slow wide vibrato, portamento in from a semitone below, bow noise | `Night`, `Dark` melodies |
| `pad_synth(freq, dur, vel, attack=0.35, cutoff=2200)` (alias `synth_pad`) | detuned saws + sub, slow attack: wind-like bed | `Mountain`, `Cave`, `Title`. Named `pad_synth` because `pad(x, seconds)` is the padding primitive |
| `pluck(freq, dur, vel, bright, duty)` | chip pluck (filtered pulse) | bass lines |
| `bell(freq, dur, vel)` | FM-ish bell (inharmonic partials) | sparkle, `Bonus` |
| `nes_lead(duty)` → inst | NES pulse lead factory (duty 0.125/0.25/0.5) with light vibrato | |
| `nes_bass_tri(freq, dur, vel)` | NES 4-bit triangle bass | |
| `nes_noise_drum(kind)` → inst | `kick`, `snare`, `hat`, `openhat`, `tom`, `crash` from LFSR noise | |
| `temple_bell(freq=196, dur=3, vel)` | 범종: hum/prime/tierce/quint/nominal partials, 맥놀이 beat on the hum, long decay | `Bell`, `Cave`, `Breakthrough` |

Unpitched hits take their own arguments and return audio directly:

| hit | signature | character |
|---|---|---|
| `taiko` | `taiko(kind='low'/'mid'/'rim', vel=1, dur=None, freq=None)` | sine thump with pitch drop + skin click; `rim` = wooden rim click |
| `gong` | `gong(dur=3.0, vel=1, freq=92, shimmer=0.6)` | inharmonic partials that bloom after the strike, long decay, slow beating shimmer |
| `wood_block` | `wood_block(pitch=900, vel=1, dur=0.11)` | 목탁 click with a damped tone — use four pitches for `Rhythm1..4` |
| `shaker` | `shaker(dur=0.14, vel=1)` | high-passed noise swell |

To put a hit into a `Sequencer` track wrap it: `ak.instrument(ak.taiko, kind='low')`,
`ak.instrument(ak.wood_block, pitch=1200)`, `ak.instrument(ak.gong, dur=4.0)`. The adapter passes
the note's `freq`/`dur` only to parameters that are **required** (pitched instruments), so hits
keep their natural pitch and length (a 16th-note taiko is not cut to 0.1 s); `vel` is always
passed; fixed keyword options win. Force note pitch/length on a hit with
`ak.instrument(ak.taiko, kind='mid', use_note_freq=True, use_note_dur=True)`. `add_track`
applies the adapter automatically to any callable, and options on pitched instruments work the
same way: `ak.instrument(ak.zither, bright=0.4)`. In patterns, `'x'` hits hand pitched
instruments C4 (`ak.HIT_FREQ`).

## Sequencer

```python
seq = ak.Sequencer(bpm=92)                       # sr defaults to 44100
lead = ak.parse_pattern("C5 == E5 G5 | A5 == G5 E5 | D5 == -- E5 | C5 == == ==", step_beats=0.25)
seq.add_track("zither", ak.zither, lead, volume=0.8, pan=-0.2)
seq.add_track("bass", ak.nes_bass_tri, ak.parse_pattern("C3 == == == | G2 == == ==", 1.0), volume=0.6)
seq.add_track("taiko", ak.instrument(ak.taiko, kind="low"), ak.repeat_pattern(ak.parse_pattern("X -- x --", 1.0), 4, 4), volume=0.7, swing=0.0)
seq.add_track("block", ak.instrument(ak.wood_block, pitch=1100), ak.parse_pattern("-- x -- x", 1.0), pan=0.4, fx=lambda x: ak.reverb(x, 0.8, 0.2))
seq.master_fx.append(lambda x: ak.lowpass(x, 9000))
x = seq.render_loop_safe(bars=4)                 # (loop_samples(92, 4), 2) float32
ak.save_music(ak.music_path(audio_root, "Town"), x, master_wav=os.path.join(tmp_dir, "Town.wav"))
```

* pattern = `list[(start_beat, note, length_beats, velocity)]`; `note` is a name `'F#3'`, a
  midi int, a Hz float, a list (chord), `'x'` (unpitched hit, C4 is passed) or `None` (rest).
* `parse_pattern(text, step_beats=0.25)`: tokens per step — `C4` note, `C4+E4+G4` chord,
  `--`/`.` rest, `==`/`~` tie (extends the previous note), `x`/`X` soft/accented hit,
  `C4@0.6` velocity, `C4*` accent, `|` ignored. Build longer parts with `bar(p, i)`,
  `repeat_pattern`, `merge_patterns`, `shift_pattern`, `transpose_pattern`.
* `add_track(name, instrument, pattern, volume=1.0, pan=0.0, swing=0.0, transpose=0, fx=None)`;
  swing 1.0 = full triplet feel on off-beat eighths; `fx` runs on the finished mono track;
  `seq.master_fx` on the stereo mix.
* `render(bars, beats_per_bar=4)` truncates tails at the loop end; `render_loop_safe` folds
  them back to the start. Both return exactly `loop_samples(bpm, bars, beats_per_bar)`
  stereo float32 samples (rendered notes are cached, so repeats are free).

## Pentatonic helper (궁상각치우)

`pentatonic(root, mode='major', octaves=2)` returns note names spanning `octaves` octaves
plus the top root (`include_top=False` to omit it):

```python
ak.pentatonic("C4", "major", 1)   # ['C4','D4','E4','G4','A4','C5']   궁 (gung)
ak.pentatonic("A3", "minor", 1)   # ['A3','C4','D4','E4','G4','A4']   우 (u) — tension / Battle
```

Modes are the five rotations of the major pentatonic: `major`/`gung`(궁) 0-2-4-7-9,
`sang`(상) 0-2-5-7-10, `gak`(각) 0-3-5-8-10, `chi`(치) 0-2-5-7-9, `minor`/`u`(우) 0-3-5-7-10.
`chord(root, quality)` supports triads/7ths and open voicings (`'5'`, `'open'`, `'sus2'`,
`'quartal'`, `'pent'`) that sit well under pentatonic lines. Melody tip: pick notes from
`pentatonic(root, mode)`, keep leaps ≤ a fifth, end phrases on the root or the fifth; for
wuxia tension use `minor` with the flat seventh held under a drone.

## SFX recipe sketches

```python
hit   = ak.mix(ak.sweep(900, 120, 0.12, "tri"), ak.lowpass(ak.noise(0.08, "white", seed=3), 2500) * 0.6)
hit   = ak.apply_env(hit, ak.env_decay(len(hit), 0.04))
slash = ak.apply_env(ak.biquad_bandpass(ak.noise(0.25, seed=4), 3500, 2.0), ak.env_adsr(ak.samples(0.25), 0.005, 0.1, 0.2, 0.1))
coin  = ak.concat(ak.osc_pulse(ak.note_freq("B5"), 0.06, 0.5), ak.osc_pulse(ak.note_freq("E6"), 0.25, 0.5))
coin  = ak.apply_env(coin, ak.env_decay(len(coin), 0.12))
gongx = ak.gong(2.0)                              # Gong.wav (finalize_sfx clamps to 2.0 s with a fade)
ak.save_sfx(ak.sfx_path(audio_root, "Hit1"), hit)
```
