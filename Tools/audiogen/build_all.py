#!/usr/bin/env python3
"""build_all.py -- run the InkPixel audio generators (Tools/audiogen/gen_*.py).

Every generator module exposes

    def build(audio_root: str, tmp_dir: str) -> list[str]

and returns the absolute paths of the files it wrote: SFX under `<audio_root>/Sfx/<Name>.wav`
and music under `<audio_root>/Music/<Name>.ogg`.  WAV masters / scratch files go to
`tmp_dir`.  A module may also expose `LOOP_INFO = {"Town": {"bpm": 92, "bars": 32,
"beats_per_bar": 4}, ...}` so the exact loop length of its music files can be verified here.

usage: build_all.py [names...] [--audio-root DIR] [--tmp DIR] [--list] [--no-check] [--lenient]

  names        select generators: 'sfx' / 'gen_sfx' / 'gen_sfx.py' / any substring of the stem.
               No names = all generators, sorted by file name.
  --list       only list the generators that would run.
  --no-check   skip the spec checks (format, peak, silence, loop length).
  --lenient    print spec violations but do not fail the build because of them.

Exit status: 0 = everything built and passed, 1 = a generator raised or returned garbage,
2 = spec violations (unless --lenient).  audiokit is reseeded (seed 0) before each generator.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEFAULT_AUDIO_ROOT = os.path.join(REPO, "Assets", "InkPixel", "Audio")
DEFAULT_TMP = os.environ.get(
    "INKPIXEL_AUDIO_TMP",
    "/tmp/claude-0/-home-user-gpb/22e3df2d-b7a9-5c89-9887-c3aaf349be7d/scratchpad/audio_tmp")

if HERE not in sys.path:
    sys.path.insert(0, HERE)
import audiokit as ak  # noqa: E402


def discover(gen_dir: str = HERE) -> list:
    return sorted(f for f in os.listdir(gen_dir) if f.startswith("gen_") and f.endswith(".py"))


def select(files: list, names: list) -> list:
    if not names:
        return files
    out = []
    for f in files:
        stem = f[:-3]
        short = stem[4:]
        for n in names:
            n = n[:-3] if n.endswith(".py") else n
            if n in (stem, short) or n in stem:
                out.append(f)
                break
    return out


def load_module(path: str):
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def ensure_tmp(tmp: str) -> str:
    try:
        os.makedirs(tmp, exist_ok=True)
        return tmp
    except OSError:
        import tempfile
        alt = os.path.join(tempfile.gettempdir(), "inkpixel_audio_tmp")
        os.makedirs(alt, exist_ok=True)
        print("warning: cannot create %s, using %s" % (tmp, alt))
        return alt


def describe(path: str, audio_root: str, loop_info: dict, check: bool):
    """Return (summary_line, issues)."""
    rel = os.path.relpath(path, audio_root) if path.startswith(audio_root) else path
    name = os.path.splitext(os.path.basename(path))[0]
    ext = os.path.splitext(path)[1].lower()
    issues = []
    try:
        if ext == ".wav":
            x, sr = ak.read_wav(path)
            kind = "wav"
        else:
            info = ak.ffprobe_info(path)
            x, sr = ak.read_ogg(path)
            kind = "ogg/%s" % info.get("codec")
    except Exception as e:  # noqa: BLE001
        return "  %-34s UNREADABLE: %s" % (rel, e), ["unreadable"]
    m = ak.measure(x, sr)
    line = "  %-34s %-11s %dch %6d Hz %8.3f s  peak %6.2f dBFS  rms %6.1f dBFS  lead %4.1f ms" % (
        rel, kind, m["channels"], sr, m["duration"], m["peak_db"], m["rms_db"], m["leading_silence_ms"])
    if check:
        if ext == ".wav":
            issues = ak.check_sfx(path)
        else:
            li = loop_info.get(name) or {}
            if isinstance(li, (tuple, list)):
                li = {"bpm": li[0], "bars": li[1], "beats_per_bar": li[2] if len(li) > 2 else 4}
            issues = ak.check_music(path, li.get("bpm"), li.get("bars"), li.get("beats_per_bar", 4),
                                    loop=li.get("loop", True))
    return line, issues


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="generators to run (default: all)")
    ap.add_argument("--audio-root", default=DEFAULT_AUDIO_ROOT)
    ap.add_argument("--tmp", default=DEFAULT_TMP)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--lenient", action="store_true")
    ap.add_argument("--gen-dir", default=HERE, help="folder holding the gen_*.py files (default: this folder)")
    args = ap.parse_args(argv)

    gen_dir = os.path.abspath(args.gen_dir)
    files = select(discover(gen_dir), args.names)
    if not files:
        print("no generators found%s in %s" % (" matching %r" % args.names if args.names else "", gen_dir))
        return 1
    if args.list:
        for f in files:
            print(f)
        return 0

    audio_root = os.path.abspath(args.audio_root)
    tmp_dir = ensure_tmp(os.path.abspath(args.tmp))
    os.makedirs(os.path.join(audio_root, "Sfx"), exist_ok=True)
    os.makedirs(os.path.join(audio_root, "Music"), exist_ok=True)
    print("audio_root: %s\ntmp_dir:    %s" % (audio_root, tmp_dir))

    failed = []
    violations = 0
    total_files = 0
    t_all = time.time()
    for f in files:
        path = os.path.join(gen_dir, f)
        print("\n== %s" % f)
        t0 = time.time()
        try:
            mod = load_module(path)
            if not hasattr(mod, "build"):
                raise AttributeError("%s has no build(audio_root, tmp_dir)" % f)
            ak.seed(0)
            out = mod.build(audio_root, tmp_dir)
            if out is None:
                out = []
            if not isinstance(out, (list, tuple)) or not all(isinstance(p, str) for p in out):
                raise TypeError("build() must return a list of file paths, got %r" % type(out))
            out = [os.path.abspath(p) for p in out]
            missing = [p for p in out if not os.path.isfile(p)]
            if missing:
                raise FileNotFoundError("build() reported files that do not exist: %s" % missing)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            failed.append(f)
            continue
        loop_info = getattr(mod, "LOOP_INFO", {}) or {}
        for p in out:
            line, issues = describe(p, audio_root, loop_info, not args.no_check)
            print(line)
            for i in issues:
                print("      ! %s" % i)
            violations += len(issues)
        total_files += len(out)
        print("  -> %d file(s) in %.1f s" % (len(out), time.time() - t0))

    print("\n%d generator(s), %d file(s), %.1f s total" % (len(files) - len(failed), total_files, time.time() - t_all))
    if failed:
        print("FAILED generators: %s" % ", ".join(failed))
        return 1
    if violations:
        print("%d spec violation(s)%s" % (violations, " (lenient: not failing)" if args.lenient else ""))
        return 0 if args.lenient else 2
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
