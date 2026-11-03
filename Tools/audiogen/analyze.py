#!/usr/bin/env python3
"""analyze.py -- print duration / peak / RMS / leading silence / format for audio files.

usage: analyze.py [paths...] [--check] [--loops JSON] [--json] [--silence-db -60]

  paths        files or folders (recursed) of .wav / .ogg; default = Assets/InkPixel/Audio.
  --check      also run the spec checks (audiokit.check_sfx / check_music) and list problems;
               exit status 2 when any file has a problem.
  --loops      JSON {"Town": {"bpm": 92, "bars": 32, "beats_per_bar": 4}, ...} for exact
               loop-length checks.  Without it, LOOP_INFO from the gen_*.py modules next to
               this script is used when available.
  --json       machine-readable output (one object per file).

WAV files are read with audiokit.read_wav; OGG files are probed with ffprobe and decoded
with ffmpeg to a temporary WAV.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_ROOT = os.path.join(REPO, "Assets", "InkPixel", "Audio")
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import audiokit as ak  # noqa: E402


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for f in sorted(files):
                    if f.lower().endswith((".wav", ".ogg")):
                        out.append(os.path.join(root, f))
        elif os.path.isfile(p):
            out.append(p)
        else:
            print("warning: %s not found" % p, file=sys.stderr)
    return sorted(out)


def gen_loop_info() -> dict:
    info = {}
    for f in sorted(os.listdir(HERE)):
        if f.startswith("gen_") and f.endswith(".py"):
            try:
                spec = importlib.util.spec_from_file_location(f[:-3], os.path.join(HERE, f))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                li = getattr(mod, "LOOP_INFO", None)
                if isinstance(li, dict):
                    info.update(li)
            except Exception:  # noqa: BLE001
                pass
    return info


def analyze_file(path: str, loops: dict, check: bool, silence_db: float) -> dict:
    name, ext = os.path.splitext(os.path.basename(path))
    rec = {"file": path, "name": name}
    try:
        if ext.lower() == ".wav":
            x, sr = ak.read_wav(path)
            with wave.open(path, "rb") as w:
                bits = 8 * w.getsampwidth()
            rec.update(format="wav pcm%d" % bits, bits=bits)
        else:
            info = ak.ffprobe_info(path)
            x, sr = ak.read_ogg(path)
            rec.update(format="ogg %s" % info.get("codec"), bits=0, probe=info)
    except Exception as e:  # noqa: BLE001
        rec.update(error=str(e))
        return rec
    rec.update(ak.measure(x, sr, silence_db))
    if check:
        if ext.lower() == ".wav":
            rec["issues"] = ak.check_sfx(path)
        else:
            li = loops.get(name) or {}
            if isinstance(li, (tuple, list)):
                li = {"bpm": li[0], "bars": li[1], "beats_per_bar": li[2] if len(li) > 2 else 4}
            if li.get("bpm") and li.get("bars"):
                rec["expected_samples"] = ak.loop_samples(li["bpm"], li["bars"], li.get("beats_per_bar", 4))
            rec["issues"] = ak.check_music(path, li.get("bpm"), li.get("bars"),
                                           li.get("beats_per_bar", 4), loop=li.get("loop", True))
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--loops")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--silence-db", type=float, default=-60.0)
    args = ap.parse_args(argv)

    files = collect(args.paths or [DEFAULT_ROOT])
    if not files:
        print("no audio files found")
        return 1
    loops = {}
    if args.loops:
        with open(args.loops, "r", encoding="utf-8") as fh:
            loops = json.load(fh)
    else:
        loops = gen_loop_info()

    bad = 0
    if not args.json:
        print("%-28s %-12s %2s %6s %9s %9s %9s %8s %8s %7s" % (
            "file", "format", "ch", "sr", "dur s", "peak dB", "rms dB", "lead ms", "trail ms", "dc"))
    for p in files:
        rec = analyze_file(p, loops, args.check, args.silence_db)
        if args.json:
            print(json.dumps(rec, ensure_ascii=False))
            if rec.get("issues") or rec.get("error"):
                bad += 1
            continue
        base = os.path.basename(p)
        if "error" in rec:
            print("%-28s ERROR %s" % (base, rec["error"]))
            bad += 1
            continue
        print("%-28s %-12s %2d %6d %9.3f %9.2f %9.1f %8.1f %8.1f %7.4f" % (
            base, rec["format"], rec["channels"], rec["sr"], rec["duration"], rec["peak_db"],
            rec["rms_db"], rec["leading_silence_ms"], rec["trailing_silence_ms"], rec["dc"]))
        if "expected_samples" in rec:
            print("%-28s   loop: %d samples (expected %d)" % ("", rec["samples"], rec["expected_samples"]))
        for i in rec.get("issues", []):
            print("%-28s   ! %s" % ("", i))
        if rec.get("issues"):
            bad += 1
    if args.check:
        print("\n%d file(s), %d with problems" % (len(files), bad))
        return 2 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
