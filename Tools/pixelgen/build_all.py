#!/usr/bin/env python3
"""build_all.py -- run every InkPixel art generator (gen_*.py in this folder) and verify its output.

    python3 Tools/pixelgen/build_all.py                 # build everything
    python3 Tools/pixelgen/build_all.py tiles fx        # only gen_tiles.py and gen_fx.py
    python3 Tools/pixelgen/build_all.py --list          # show the generators that would run
    python3 Tools/pixelgen/build_all.py --no-verify     # skip the §9 checks on the written files

Generator contract (see README.md): a module `gen_<name>.py` exposing

    def build(art_root: str, preview_dir: str, cellmap_dir: str) -> list[str]

that writes its PNG/sidecar files below `art_root` (Tiles/, Characters/, Icons/, FX/, UI/), its
review previews into `preview_dir`, cell maps into `cellmap_dir`, and returns the paths it wrote.
Generators run in sorted file-name order, each in its own module namespace, with this folder on
sys.path (so `import pixelkit` works). Every written PNG with a `<base>.sprites.json` sidecar is
checked with `pixelkit.check_sheet`; other PNGs are checked with `pixelkit.verify_palette`.
Exit status: 0 = all generators succeeded and verified, 1 = a generator failed or an output
failed verification, 2 = usage error (unknown generator name, nothing to run).
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import time
import traceback
from typing import Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
ART_ROOT = os.path.join(REPO_ROOT, "Assets", "InkPixel", "Art")
PREVIEW_DIR = os.path.join(REPO_ROOT, "Docs", "previews")
CELLMAP_DIR = os.path.join(REPO_ROOT, "Docs", "cellmaps")
ART_SUBDIRS = ("Tiles", "Characters", "Icons", os.path.join("Icons", "Mini"), "FX",
               os.path.join("UI", "Status"), os.path.join("UI", "Markers"), os.path.join("UI", "Frames"))


def discover(gen_dir: str = HERE) -> List[str]:
    """Sorted list of generator file names (gen_*.py) in `gen_dir`."""
    return sorted(f for f in os.listdir(gen_dir)
                  if f.startswith("gen_") and f.endswith(".py") and os.path.isfile(os.path.join(gen_dir, f)))


def normalize_name(arg: str) -> str:
    """'tiles', 'gen_tiles', 'gen_tiles.py', 'Tools/pixelgen/gen_tiles.py' -> 'gen_tiles'."""
    base = os.path.basename(arg)
    if base.endswith(".py"):
        base = base[:-3]
    if not base.startswith("gen_"):
        base = "gen_" + base
    return base


def select(files: Sequence[str], names: Sequence[str]) -> Tuple[List[str], List[str]]:
    """Filter discovered files by requested names. Returns (selected files, unknown names)."""
    if not names:
        return list(files), []
    by_mod = {f[:-3]: f for f in files}
    selected: List[str] = []
    unknown: List[str] = []
    for n in names:
        mod = normalize_name(n)
        if mod in by_mod:
            if by_mod[mod] not in selected:
                selected.append(by_mod[mod])
        else:
            unknown.append(n)
    selected.sort()
    return selected, unknown


def load_generator(path: str):
    """Import a generator file as its own module (fresh namespace, name = file stem)."""
    mod_name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "build") or not callable(module.build):
        raise AttributeError(f"{os.path.basename(path)} has no build(art_root, preview_dir, cellmap_dir)")
    return module


def ensure_dirs(art_root: str, preview_dir: str, cellmap_dir: str) -> None:
    for d in (art_root, preview_dir, cellmap_dir):
        os.makedirs(d, exist_ok=True)
    for sub in ART_SUBDIRS:
        os.makedirs(os.path.join(art_root, sub), exist_ok=True)


def _under(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(root)]) == os.path.abspath(root)
    except ValueError:  # different drives on Windows
        return False


def verify_outputs(files: Sequence[str], art_root: str) -> List[str]:
    """§9 checks on written files: every file must exist; PNGs under `art_root` get check_sheet
    (with a sidecar) or verify_palette (without). Previews and cell maps outside `art_root` use
    free colors and are only checked for existence. Returns problem strings."""
    import pixelkit  # local import: sys.path is prepared in main()
    problems: List[str] = []
    for f in files:
        if not os.path.exists(f):
            problems.append(f"{f}: reported but not written")
            continue
        if not f.lower().endswith(".png") or not _under(f, art_root):
            continue
        sidecar = pixelkit.sidecar_path(f)
        if os.path.isfile(sidecar):
            for p in pixelkit.check_sheet(f, sidecar):
                problems.append(f"{os.path.relpath(f, REPO_ROOT) if f.startswith(REPO_ROOT) else f}: {p}")
        else:
            bad = pixelkit.verify_palette(f, max_results=3)
            if bad:
                n = len(pixelkit.verify_palette(f))
                problems.append(f"{f}: {n} off-palette/partial-alpha pixels, first {bad}")
    return problems


def run_generator(path: str, art_root: str, preview_dir: str, cellmap_dir: str,
                  verify: bool = True) -> Dict[str, object]:
    """Run one generator; never raises. Returns a result dict for the summary table."""
    name = os.path.splitext(os.path.basename(path))[0]
    result: Dict[str, object] = {"name": name, "status": "ok", "files": 0, "seconds": 0.0, "note": "",
                                 "problems": [], "paths": []}
    t0 = time.perf_counter()
    try:
        module = load_generator(path)
        written = module.build(art_root, preview_dir, cellmap_dir)
        if written is None:
            written = []
        if isinstance(written, (str, bytes)):
            raise TypeError("build() must return a list of paths, not a single string")
        paths = [str(p) for p in written]
        result["paths"] = paths
        result["files"] = len(paths)
        if verify:
            problems = verify_outputs(paths, art_root)
            if problems:
                result["status"] = "VERIFY FAILED"
                result["problems"] = problems
                result["note"] = f"{len(problems)} problem(s)"
        if not paths:
            result["note"] = (result["note"] + "; " if result["note"] else "") + "wrote nothing"
    except Exception as ex:  # noqa: BLE001 - we report and continue with the next generator
        result["status"] = "FAILED"
        result["note"] = f"{type(ex).__name__}: {ex}"
        result["traceback"] = traceback.format_exc()
    result["seconds"] = time.perf_counter() - t0
    return result


def format_table(results: Sequence[Dict[str, object]]) -> str:
    rows = [("generator", "status", "files", "seconds", "note")]
    for r in results:
        note = str(r["note"]).splitlines()[0] if r["note"] else ""
        rows.append((str(r["name"]), str(r["status"]), str(r["files"]), f"{float(r['seconds']):.2f}", note[:70]))
    widths = [max(len(row[i]) for row in rows) for i in range(5)]
    lines = []
    for i, row in enumerate(rows):
        lines.append("  ".join(cell.ljust(widths[c]) for c, cell in enumerate(row)).rstrip())
        if i == 0:
            lines.append("  ".join("-" * w for w in widths))
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Run InkPixel art generators (gen_*.py).")
    ap.add_argument("names", nargs="*", help="generator names to run (e.g. tiles, gen_fx); default: all")
    ap.add_argument("--list", action="store_true", help="list generators and exit")
    ap.add_argument("--no-verify", action="store_true", help="skip check_sheet/verify_palette on the outputs")
    ap.add_argument("--gen-dir", default=HERE, help="folder holding gen_*.py (default: this folder)")
    ap.add_argument("--art-root", default=ART_ROOT)
    ap.add_argument("--preview-dir", default=PREVIEW_DIR)
    ap.add_argument("--cellmap-dir", default=CELLMAP_DIR)
    ap.add_argument("--quiet", action="store_true", help="only print the summary table")
    args = ap.parse_args(argv)

    gen_dir = os.path.abspath(args.gen_dir)
    for p in (HERE, gen_dir):
        if p not in sys.path:
            sys.path.insert(0, p)
    files = discover(gen_dir)
    selected, unknown = select(files, args.names)
    if unknown:
        print(f"error: unknown generator(s) {unknown}; available: {[f[:-3] for f in files]}", file=sys.stderr)
        return 2
    if args.list:
        for f in selected:
            print(f[:-3])
        return 0
    if not selected:
        print(f"error: no gen_*.py found in {gen_dir}", file=sys.stderr)
        return 2

    art_root = os.path.abspath(args.art_root)
    preview_dir = os.path.abspath(args.preview_dir)
    cellmap_dir = os.path.abspath(args.cellmap_dir)
    ensure_dirs(art_root, preview_dir, cellmap_dir)
    if not args.quiet:
        print(f"art_root    {art_root}\npreview_dir {preview_dir}\ncellmap_dir {cellmap_dir}\n")

    results: List[Dict[str, object]] = []
    for f in selected:
        if not args.quiet:
            print(f"==> {f[:-3]}", flush=True)
        r = run_generator(os.path.join(gen_dir, f), art_root, preview_dir, cellmap_dir,
                          verify=not args.no_verify)
        results.append(r)
        if not args.quiet:
            if r.get("traceback"):
                print(r["traceback"], file=sys.stderr)
            for p in r["problems"]:  # type: ignore[union-attr]
                print(f"    ! {p}")
            print(f"    {r['status']}: {r['files']} file(s) in {float(r['seconds']):.2f}s")

    print("\n" + format_table(results))
    total_files = sum(int(r["files"]) for r in results)
    failed = [r for r in results if r["status"] != "ok"]
    print(f"\n{len(results)} generator(s), {total_files} file(s), {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
