# InkPixel music notes (`Assets/InkPixel/Audio/Music/*.ogg`)

Composer's notes for the twelve cues of `Docs/ASSET_SPEC.md` §6, so a human can tweak them
without reverse-engineering the generator. Everything is written in
`Tools/audiogen/gen_music.py` on top of `audiokit.py` (numpy only, deterministic: two runs
give byte-identical OGGs). Rebuild with

```
python3 Tools/audiogen/build_all.py music          # writes the 12 OGGs, verifies them
python3 Tools/audiogen/analyze.py Assets/InkPixel/Audio/Music --check
```

Format of every file: OGG Vorbis q6, 44100 Hz, stereo, decoded peak ≤ −1 dBFS (the master is
normalised to −1.5 dBFS before encoding to leave room for Vorbis overshoot). Loops are
**exactly** `bars × 4 × 60 / BPM × 44100` samples with no end fade; note tails and reverb
tails are folded back onto the start (`Sequencer.render_loop_safe`), so the loop point is
seamless. The two stings (`Victory`, `GameOver`) are fixed-length and fade out.

## Overview

| cue | GPA use | key / scale | BPM | bars | length | form | mood |
|---|---|---|---|---|---|---|---|
| `Town` | 백로진 (town) | G major pentatonic (G A B D E), roots G E C D | 92 | 32 | 83.478 s | A A′ B A″ | gentle, river-town morning |
| `World` | 강호 (overworld) | D major pentatonic (D E F♯ A B), roots D Bm G A | 110 | 32 | 69.818 s | A1 A2 B A3 | travelling, bright B |
| `Battle` | combat | E minor pentatonic (E G A B D) | 150 | 32 | 51.200 s | A A′ B A″ | driving taiko, zither riff |
| `Mountain` | 무명산 (산중수련) | A minor pentatonic (A C D E G), open fifths | 70 | 32 | 109.714 s | through-composed, 4-bar pad groups | sparse, wind, distant |
| `Cave` | caves / 독무 동굴 | D minor pentatonic over a D drone; tritone G♯ in bars 17–24 | 80 | 32 | 96.000 s | drone sections 1–16 / 17–24 / 25–32 | eerie, dripping |
| `Sect` | 청운검문 | F major pentatonic (F G A C D), chords F Dm B♭ C | 84 | 32 | 91.429 s | A A′ B A″ | dignified, ceremonial |
| `Dark` | 흑사방 | A minor pentatonic over an Andalusian descent A G F E | 100 | 32 | 76.800 s | A A′ B A″ | low, tense pulse |
| `Night` | 백로진의 밤 | D minor pentatonic (D F G A C), chords Dm B♭ F Gm Am | 66 | 32 | 116.364 s | A A′ B A″ | tragic, slow |
| `Demon` | 심마 (inner demon) | C / F♯ tritone axis, semitone clusters | 120 | 16 | 32.000 s | 4 × 4-bar pad changes | dissonant, irregular |
| `Title` | title screen | C major pentatonic (C D E G A), chords C Am F G | 76 | 32 | 101.053 s | intro A (zither only) · A · B · A″ | calm, arpeggiated |
| `Victory` | battle won (sting) | G major pentatonic | 120 | — | 5.000 s | fanfare → rolled chord + gong | bright, fade 1.2 s |
| `GameOver` | defeat (sting) | D minor pentatonic | 60 | — | 8.000 s | descending phrase + low gong | dark, fade 2.0 s |

`gen_music.LOOP_INFO` holds the BPM / bars of every cue; `build_all.py` and `analyze.py` use it
to verify the exact sample count. Change a tempo or length there **and** in the builder.

Measured on the current build (decoded OGG; A-weighted level is over the whole file and is the
better guide to how loud a cue *feels*):

| cue | samples | peak | RMS | A-weighted | crest | notes |
|---|---|---|---|---|---|---|
| `Town` | 3 681 391 | −1.40 dBFS | −17.6 dB | −22.2 dB | 16.1 dB | plucked, airy |
| `World` | 3 078 982 | −1.37 | −14.2 | −19.1 | 12.8 | |
| `Battle` | 2 257 920 | −1.36 | −12.2 | −17.4 | 10.7 | loudest cue |
| `Mountain` | 4 838 400 | −1.51 | −15.5 | −21.7 | 14.0 | pad-led |
| `Cave` | 4 233 600 | −1.46 | −16.3 | −29.5 | 14.8 | quietest by far: all energy is below 250 Hz |
| `Sect` | 4 032 000 | −1.25 | −15.1 | −20.4 | 13.6 | |
| `Dark` | 3 386 880 | −1.38 | −15.9 | −24.8 | 14.4 | bass-led |
| `Night` | 5 131 636 | −1.34 | −12.6 | −15.8 | 11.1 | densest (arpeggios + erhu) |
| `Demon` | 1 411 200 | −1.45 | −12.3 | −21.5 | 10.8 | |
| `Title` | 4 456 421 | −1.40 | −13.6 | −18.6 | 12.2 | |
| `Victory` | 220 500 | −1.37 | −16.2 | −21.6 | 14.7 | |
| `GameOver` | 352 800 | −1.67 | −14.3 | −22.1 | 12.8 | |

Every master is peak-normalised, so the perceived differences come from the material (a drone
cue cannot be as loud as a riff cue without saturating). If `Cave` turns out too quiet in game,
raise its `bell`, `dripL/R` and `zither` volumes rather than the drone (the drone sets the
peak), or play it with a slightly higher mixer level; a 40 Hz master high-pass was tried and
recovers only ~1.5 dB, so it was left out.

## Instruments (all from `audiokit.py`)

| voice | what it is | where |
|---|---|---|
| `zither` | 가야금/古箏 pluck: sharp attack, fast decay, 2–3 detuned harmonics, pick noise. `bright` 0.3 (bass, dark) … 1.0 (riff) | every cue |
| `flute` | 대금/dizi: sine + triangle, breath burst, vibrato after 150 ms | Town, World, Mountain, Sect, Title, Victory |
| `erhu` | 二胡: low-passed saw, wide slow vibrato, portamento in from a semitone below (`from_semitones`), bow noise | Battle, Mountain, Sect, Dark, Night, Demon, GameOver |
| `pad_synth` | three detuned saws + sub triangle, slow attack — the "wind-like pad". `cutoff`, `detune` (cents), `attack`, `release` | Mountain, Cave, Sect, Dark, Night, Demon, Title, GameOver |
| `pluck` | chip pluck (pulse through a closing low-pass) — bass lines | World, Battle, Dark |
| `nes_bass_tri` | NES 4-bit triangle bass | Demon |
| `bell` | FM-style inharmonic bell | Title sparkles, Demon |
| `temple_bell` | 범종: hum/prime/tierce/quint/nominal partials with a 맥놀이 beat | Cave, Sect, Night, Demon, GameOver |
| `taiko` | `low` (大太鼓 thump), `mid`, `rim` (wood rim click) | every cue |
| `gong` | inharmonic partials that bloom after the strike, shimmer | Battle, Demon, Victory, GameOver |
| `wood_block` | 목탁 click with a damped tone at `pitch` Hz | Town, World, Mountain, Victory |
| `shaker` | high-passed noise swell | Town, World |

Three extra voices live in `gen_music.py` itself (plain `(freq, dur, vel)` callables built from
audiokit primitives): `drip` (water drop, rising-pitch plink — Cave), `wind` (band-passed
pink-noise gust; the pattern "note" is the band centre in Hz, not a pitch — Mountain, Cave) and
`tremolo_zither` (輪指 repeated plucks at 11 Hz — Demon).

## Mix conventions

* Lead centre; counter-melody / zither accompaniment slightly right (+0.25…+0.3); shaker, rim
  and octave-doublings slightly left (−0.2…−0.35); bass and pads centre.
* Every shaker / noise track has a 2nd-order low-pass at 9 kHz; masters end with a loop-safe
  low-pass (`master_lp`, 9–15 kHz depending on the cue) that is primed with the end of the
  loop so sample 0 is filtered with the state it has after wrapping.
* `sat(drive)` = gentle tanh saturation on zither tracks and some masters: it rounds the pick
  transients so the master normalise can sit 3–4 dB louder without changing the balance.
* `hp()` = 30 Hz high-pass on every `pluck` bass track: the pulse oscillator carries a DC
  offset that would otherwise step the mix on every note.
* Pads and drones are written slightly longer than their slot (e.g. 16.6 beats for a 16-beat
  group) so consecutive chords overlap and the bed never dips to silence.
* Velocity: every section is scaled with `vel(pattern, k)` (A 0.75–0.9, B 1.0, final A 0.85–0.95)
  and patterns carry per-note accents (`C4@0.6`, `x`/`X`), so dynamics are in the data, not in
  the mix.

## Cue by cue

### Town — 백로진 (92 BPM, G major pentatonic, 32 bars)

Form A(1–8) A′(9–16) B(17–24) A″(25–32). The 2-bar motif `D5 B4 D5 E5 D5 B4 | A4 B4 A4 G4`
opens A and comes back at bar 5; A′ is the same melody in 16th-note ornamentation (turns and
pickups); B climbs to E5–G5–A5 with the flute answering; A″ repeats A′ with two sustained flute
answers (bars 27–28 and 31–32).

| track | instrument | notes | pan |
|---|---|---|---|
| `zither` | `zither(bright=0.85)` + sat 1.5 + short reverb | lead | 0 |
| `flute` | `flute` | counter-melody in B (long notes on beats 3–4, answering the lead), answers in A″ | +0.28 |
| `bass` | `zither(bright=0.35)` | roots on 1, fifth on 3, root pickup on 4; roots G E C D G E D G (A) and E C G D E C D D (B) | −0.08 |
| `taiko_low` / `taiko_mid` | `taiko` | low on 1 and the "and" of 3 (B adds the "and" of 2), mid on 3 | 0 / +0.1 |
| `block` | `wood_block(pitch=1050)` | beats 2 and 4, a 16th pickup before every 4th bar | +0.35 |
| `shaker` | `shaker` | straight 8ths (accented on the off-beats), section dynamics 0.85 / 0.7 / 1.0 / 0.9 | −0.3 |

### World — 강호 (110 BPM, D major pentatonic, 32 bars)

Form A1(1–8) A2(9–16) B(17–24) A3(25–32). Flute lead throughout (A1 ends open on E5, A2 and
A3 close on D5). B is the bright section: the melody moves up to B5/D6 over G–A–D–Bm,
the bass goes to quarter-note root/fifth and the wood block adds the "and" of 2. Zither broken
chords (4-note voicings, 8ths, accent pattern per bar) enter at bar 9 and sit right of centre;
the taiko mid adds a 16th-note fill in the last beat of bars 8, 16, 24 and 32.

Chords: A sections D Bm G A | D Bm G A (A1) / D Bm G A | D Bm A D (A2, A3); B: G A D Bm | G A Bm A.

### Battle (150 BPM, E minor pentatonic, 32 bars)

Form A(1–8) A′(9–16) B(17–24) A″(25–32). The zither riff is a 16th-note figure
`E4 · E4 G4 E4 · D4 E4 | G4 · · A4 G4 · E4 D4` transposed through E, G, A, E, D and an ending
bar (`B4 D5 E5` upwards); A′ lifts the last four bars an octave. B replaces the riff with
power-chord stabs (A4+E5 and transpositions) under an erhu melody; A″ adds a second zither one
octave up, panned left. Erhu stabs punctuate the A sections (bars 3–4 and 7–8); a gong (96 Hz)
marks bars 1, 9, 17, 25. Bass: plucked 8ths on E E G A E E D E (A), with octave jumps in A′
and a pedal with octave jumps in B (A A G G D D B E). Taiko: a 2-bar low pattern
(1, 2+, 3, 4+ | 1, 2+, 3, 3+), mid on 2 and 4 (and 4+ in the second bar), a 16th fill in the last
beat of every 8th bar, rim 16ths accenting every off-beat 8th and the last 16th of the bar.

### Mountain — 무명산 (70 BPM, A minor pentatonic, 32 bars)

A pad bed of open fifths changes every 4 bars (A/E, A/E, G/D, A/E, C/G, D/A, A/E, A/E; the C
and D groups are the "lift" in bars 17–24). Two wind tracks (left / right) blow gusts of
different band centre (380–600 Hz) at staggered times. Four flute phrases (bars 3–5, 9–12,
19–22, 27–30) are separated by long rests; long erhu notes (E4 for 8 beats at bar 6, A4→G4 at
bar 13, C5→D5→A4 at bar 23, E4 at bar 30) fill the gaps. Wood block (820 Hz) eight times in the
whole loop, three distant low taiko hits (bars 1, 17, 25) with long reverb. The pad is the
loudest element by design; the flute sits on top of it.

### Cave (80 BPM, D minor pentatonic over a D drone, 32 bars)

Three layers of drone: `drone` D2+A2 (D2+G♯2 in bars 17–24 — the tritone is the only harmonic
event), `drift` a slow higher voice D3 (bars 1–16) → C3 (17–20) → G♯3 (21–24) → D3 (25–32), and
`air`, a very low wind. Temple bells (pitched by the note: D4 bar 1, A3 bar 9, G3 bar 13, F4 bar
17, D4 bar 25, A3 bar 29). Water drops: two tracks (left / right) of the custom `drip` voice at
pseudo-random times (seed 7, 1.5–6.5 s apart, pitches D6–D7) through a 370 ms feedback delay and
a long reverb. A sparse low zither plays the group roots (bars 1, 5, 9, 13, 25, 29) and a falling line
F3 D3 C3 A2 in bars 21–24. To make the cave busier, lower the `1.5 + 5.0 * rng.random()` spacing of the drips.

### Sect — 청운검문 (84 BPM, F major pentatonic, 32 bars)

Form A(1–8) A′(9–16) B(17–24) A″(25–32). Rolled zither chords (`strum`: each string 45 ms after
the previous one) on beats 1 and 3 — beats 1, 3 and 4 in B — over F Dm B♭ C F Dm C F (A) and
Dm C B♭ F Dm B♭ C C (B). The flute carries the melody (A ends on F4, B reaches A5); the erhu
adds held harmony notes in A′ (F4 F4 F4 G4 A4 F4 G4 F4) and doubles the melody in unison,
softly, in A″. Low pad on the chord roots, taiko low on beat 1 (plus beat 3 in B and A″),
taiko mid on 3, temple bell (196 Hz) at bars 1 and 17.

### Dark — 흑사방 (100 BPM, A minor pentatonic, 32 bars)

Form A(1–8) A′(9–16) B(17–24) A″(25–32). The pulsing pluck bass (8ths with accents on 1 and
3, an approach note on the last 8th) walks the Andalusian descent A A A A G G F E; B moves to
C C D D F F E E. Under F and C the approach note comes from above (G, D) so it stays in the
pentatonic set. Dark pad on the roots; the erhu melody A/A2/B/A2 stays low (C4–D5) with wide
vibrato and a 90 ms glide; rim hits on a 2-bar pattern (3+ | 2+, 4a) that doubles in B (2+, 4+ | 1+, 3+, 4a); low
taiko on 1 (B adds 3+); low zither doubles the roots in A′ and A″.

### Night — 백로진의 밤 (66 BPM, D minor pentatonic, 32 bars)

Form A(1–8) A′(9–16) B(17–24) A″(25–32). Zither arpeggios over Dm Dm B♭ F Gm Dm Am Dm (A) and
F C Dm Am B♭ F Gm A5 (B): 8th-note up-and-down figures in A / A′, 16ths in B / A″. The erhu
melody enters on beat 3 of bar 1 (A4 → D5 … ends on D5 held a whole bar); B rises to A5 and
falls through the B♭4 appoggiatura to A4. Temple bell on D3 (146.8 Hz) at bars 1, 9, 17, 25
and on beat 3 of bar 32 (its tail wraps into bar 1). Pad on the roots from bar 9 on.

### Demon — 심마 (120 BPM, C/F♯ tritone, 16 bars)

Pads on C2+F♯2 (bars 1–4), C2+F♯2+G2 (5–8), C♯2+G2 (9–12), C2+F♯2+C♯3 (13–16), detuned 28
cents, plus a high cluster pad (F♯4+G4, C♯5+D5, F♯4+C5) at 45 cents detune. The erhu "wails":
every note glides in from a tritone below over 350 ms with 0.8-semitone vibrato. Zither
tremolo on the C5+C♯5 cluster (bars 2, 7, 10, 13, 15). Taiko: four 6–7-hit groupings that
rotate every bar (so no two consecutive bars share a grid), crescendo across the 16 bars, rim
fills in bars 4, 8, 12, 14, 16. Gong (80 Hz) at bars 1, 9 and beat 4 of bar 16; FM bells on
C6+F♯6 and C♯6+G6; a temple bell at 370 Hz on bar 9; NES triangle bass on C2 / F♯2 / C♯2 / G2.

### Title (76 BPM, C major pentatonic, 32 bars)

Zither arpeggios (5-note voicings, 8ths) over C Am F G (bars 1–16, 25–32) and Am F C G Am F G G
(17–24, a different arpeggio order). The flute melody enters at bar 9 (M), varies in bars 17–24
(MB) and closes on C5 in bar 32 (M2). Pad on the roots, four bell sparkles (bars 4, 12, 20,
28), a distant low taiko every other bar in bars 17–32.

### Victory (sting, 5.0 s)

Gong (96 Hz) and a taiko roll under a rising G-pentatonic fanfare in three octaves (flute,
zither, low zither): `G5 A5 B5 D6 E6 … D6 E6 G6 | A6 G6 E6 D6 G6`. A rolled G chord and a
second gong land at 3.0 s; raised-cosine fade-out over the last 1.2 s. Rendered as 3 bars at
120 BPM and cut to 5.0 s.

### GameOver (sting, 8.0 s)

Low gong (70 Hz) at 0 s, descending erhu A4 G4 F4 D4 C4 A3 echoed by a low zither D4 C4 A3 D3
A2 D2, a low taiko at 4 s, a temple bell on D3 at 5 s, a D2+A2 pad under everything; 2 s
fade-out.

## How to tweak

* **Melodies** are step strings parsed by `P(text, step)`: one token per step (`0.5` = 8ths,
  `0.25` = 16ths), `==` ties, `--` rests, `C5@0.6` velocity, `|` bar lines. `P` raises an error
  if a bar does not have exactly `4/step` tokens, so a typo cannot shift the rest of the track.
* **Sections**: `cat(a, b, ...)` lays parts bar after bar, `rep(p, n)` repeats, `at(p, bar)`
  moves a part to a 0-based bar, `merge(...)` overlays, `vel(p, k)` scales dynamics,
  `ramp(p, v0, v1)` makes a crescendo, `trn(p, semitones)` transposes.
* **Bass lines**: `bassline(roots, template)` — one symbolic bar template (`R` root, `F`
  fifth, `O` octave, `L` fifth below, `N`/`S` whole step below/above, `@v` velocity) applied to
  a list of per-bar roots.
* **Arpeggios / chords**: `arp(voicing, order, step, vel, accents)`, `strum(voicing, start,
  length)` (rolled), `chord_bars(voicings, starts)`.
* **Hits**: `hits([beat, ...], length, vel)`; wrap unpitched instruments with
  `ak.instrument(ak.taiko, kind="low")` etc.
* **Levels**: `volume=` per track (linear), `pan=` −1…+1, `fx=` a callable on the mono track
  (`rev(decay, mix, damp, predelay)`, `lp(hz)`, `hp()`, `sat(drive)`, `chain(...)`).
  `seq.master_fx` holds the master chain; keep `master_lp` last.
* **Loop safety**: keep `save_loop` (uses `render_loop_safe`) for loops and never add an end
  fade; a track-level `fx` must be time-invariant (filters, reverb, saturation are fine).
  Pads that must sound across the loop point can simply overrun the last bar — the overrun is
  folded onto bar 1.
* After editing: `python3 Tools/audiogen/build_all.py music` (exit 0 = all spec checks pass:
  codec, stereo, 44100 Hz, decoded peak, exact loop length). `analyze.py --check` prints peak /
  RMS / DC / loop length per file. Because nobody can listen in the build pipeline, the cues
  were reviewed numerically while composing; the same three checks are worth repeating after a
  change: (1) collect every pitched note of a cue and compare its pitch classes with the cue's
  scale (the lists above), (2) compare the loop join `|x[0] − x[-1]|` and the high-frequency
  energy in the 5 ms around sample 0 with the same measure at other bar starts (a click shows
  up as an outlier), (3) render each track solo through its `fx` / `volume` and compare
  A-weighted RMS over its active windows with the lead's (targets used here: counter-melody
  and accompaniment 3–8 dB under the lead, accents 8–14 dB under, shaker ≈ 16 dB under).
