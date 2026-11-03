#!/usr/bin/env python3
"""selftest.py -- exercises every public API of the InkPixel pixel toolkit (pixelkit + palette +
build_all). Run `python3 Tools/pixelgen/selftest.py [--out DIR] [--keep]`; exit 0 = green.

Writes its scratch files into a temporary folder (or --out DIR) and deletes it unless --keep.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import palette  # noqa: E402
import pixelkit as pk  # noqa: E402
from pixelkit import (  # noqa: E402
    Canvas, Sheet, Rng, blob47, character_sheet, verify_palette, check_sheet, check_sidecar,
    check_character_sheet, PALETTE, DIRECTIONS, CANONICAL_MASKS, MASK_N, MASK_E, MASK_S, MASK_W,
    MASK_NE, MASK_NW, quadrant_kinds, quadrant_kind, canonicalize, is_canonical,
    mask_from_neighbors, resolve_rgba,
)

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def raises(exc, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except exc:
        return True
    except Exception as ex:  # noqa: BLE001
        raise AssertionError(f"expected {exc.__name__}, got {type(ex).__name__}: {ex}") from None
    raise AssertionError(f"expected {exc.__name__} to be raised")


OUT = ""  # set by main()


def out(*parts: str) -> str:
    p = os.path.join(OUT, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


# ------------------------------------------------------------------------------------------
# palette
# ------------------------------------------------------------------------------------------
@test
def palette_v2_table():
    spec = [
        ("ink_black", "#1e1b18"), ("ink_dark", "#3a342e"), ("ink", "#5c554c"), ("ink_light", "#8a8378"),
        ("ink_pale", "#b5ad9e"), ("paper_dark", "#d6c6a4"), ("paper", "#e9dec6"), ("paper_light", "#f4ecdc"),
        ("vermilion_dark", "#6e1512"), ("vermilion", "#9e241c"), ("vermilion_light", "#c4473a"),
        ("jade_dark", "#1c5c4e"), ("jade", "#3f8a73"), ("jade_light", "#7fb79b"), ("bronze_navy", "#18243c"),
        ("navy", "#2f4466"), ("steel", "#5a7391"), ("moss_dark", "#35502f"), ("moss", "#5a7a45"),
        ("moss_light", "#88a05a"), ("moss_pale", "#b4c278"), ("earth_dark", "#4a3324"), ("earth", "#76533a"),
        ("earth_light", "#a6805a"), ("sand", "#cfae7e"), ("skin", "#e6c39b"), ("gold", "#c9a24a"),
        ("gold_light", "#e8d690"), ("water_deep", "#2d5b73"), ("water", "#4f8aa3"), ("water_light", "#8dbfcc"),
        ("plum", "#5b3a6b"),
    ]
    assert list(PALETTE.items()) == spec, "palette must match ASSET_SPEC §2.1 exactly, in order"
    assert len(palette.COLORS) == 32 and palette.PALETTE_NAMES == [n for n, _ in spec]
    assert palette.NAME_TO_RGB["ink_black"] == (0x1e, 0x1b, 0x18)
    assert palette.RGB_TO_NAME[(0x5b, 0x3a, 0x6b)] == "plum"
    assert palette.hex_to_rgb("#9e241c") == (158, 36, 28) and palette.rgb_to_hex((158, 36, 28)) == "#9e241c"
    assert palette.is_palette_rgb((0x5a, 0x7a, 0x45, 255)) and not palette.is_palette_rgb((0, 0, 0))
    assert palette.nearest_palette_name((0, 0, 0)) == "ink_black"
    assert palette.nearest_palette_name((255, 255, 255)) == "paper_light"
    assert palette.OUTLINE == "ink_black" and palette.ALIASES["outline"] == "ink_black"
    assert palette.ramp("wood") == ("earth_dark", "earth", "earth_light")
    assert palette.ramp("skin") == ("sand", "skin") and palette.ramp("paper")[1] == "paper"
    raises(KeyError, palette.ramp, "nope")
    for names in palette.RAMPS.values():
        assert all(n in PALETTE for n in names)


@test
def palette_resolve():
    assert resolve_rgba("moss") == (0x5a, 0x7a, 0x45, 255)
    assert resolve_rgba("outline") == resolve_rgba("ink_black") == (0x1e, 0x1b, 0x18, 255)
    assert resolve_rgba(None) == (0, 0, 0, 0) == palette.TRANSPARENT
    assert resolve_rgba("#102030") == (16, 32, 48, 255)
    assert resolve_rgba("#10203000") == (0, 0, 0, 0)
    assert resolve_rgba((1, 2, 3)) == (1, 2, 3, 255)
    assert resolve_rgba((1, 2, 3, 7)) == (1, 2, 3, 255), "partial alpha becomes opaque"
    assert resolve_rgba((1, 2, 3, 0)) == (0, 0, 0, 0)
    raises(KeyError, resolve_rgba, "green")          # v1 name, not aliased
    raises(ValueError, resolve_rgba, (1, 2))
    raises(ValueError, resolve_rgba, (300, 0, 0))
    raises(TypeError, resolve_rgba, 12)


# ------------------------------------------------------------------------------------------
# Canvas
# ------------------------------------------------------------------------------------------
@test
def canvas_basics():
    c = Canvas(16, 16)
    assert c.size == (16, 16) and c.w == 16 and c.h == 16 and c.is_empty()
    c.set(3, 4, "moss")
    assert c.get(3, 4) == (0x5a, 0x7a, 0x45, 255) and c.get_name(3, 4) == "moss" and c.is_opaque(3, 4)
    assert c.get(-1, 0) == (0, 0, 0, 0) and c.get(99, 99) == (0, 0, 0, 0)
    c.set(99, 99, "moss")  # ignored
    c.set(3, 4, None)
    assert not c.is_opaque(3, 4) and c.get(3, 4) == (0, 0, 0, 0)
    raises(ValueError, Canvas, 0, 4)
    c2 = Canvas(4, 4, fill="paper")
    assert c2.count_opaque() == 16 and c2.colors_used() == ["paper"]
    c2.clear()
    assert c2.is_empty()
    assert repr(c2).startswith("Canvas(4x4")


@test
def canvas_primitives():
    c = Canvas(16, 16)
    c.rect(2, 2, 4, 3, "earth")
    assert c.count_opaque() == 12 and c.bbox() == (2, 2, 4, 3)
    c.rect(0, 0, 16, 16, "ink_black", fill=False)
    assert c.get_name(0, 0) == "ink_black" and c.get_name(15, 15) == "ink_black" and c.get_name(1, 1) is None
    c.hline(0, 15, 8, "sand")
    c.vline(8, 0, 15, "sand")
    assert c.get_name(15, 8) == "sand" and c.get_name(8, 0) == "sand"
    c.line(0, 0, 15, 15, "jade")
    assert c.get_name(7, 7) == "jade" and c.get_name(15, 15) == "jade"
    c.line(15, 0, 0, 15, "jade")
    assert c.get_name(0, 15) == "jade"
    d = Canvas(9, 9)
    d.circle(4, 4, 2, "gold")
    assert d.count_opaque() == 21 and d.bbox() == (2, 2, 5, 5)     # classic 3-5-5-5-3 circle
    assert not d.is_opaque(2, 2) and d.is_opaque(2, 3) and d.is_opaque(3, 2)
    d.circle(4, 4, 2, "gold_light", fill=False)
    assert d.get_name(4, 4) == "gold" and d.get_name(2, 4) == "gold_light"
    e = Canvas(10, 6)
    e.ellipse(4.5, 2.5, 4, 2, "water")                      # half-integer centre -> even size
    assert e.bbox() == (1, 1, 8, 4)
    e2 = Canvas(11, 7)
    e2.ellipse(5, 3, 4, 2, "water")                         # integer centre -> odd size
    assert e2.bbox() == (1, 1, 9, 5)
    f = Canvas(5, 5)
    f.fill_points([(0, 0), (4, 4), (9, 9)], "plum")
    assert f.count_opaque() == 2
    f.fill_where(np.ones((5, 5), bool), "ink")
    assert f.count_opaque() == 25
    raises(ValueError, f.fill_where, np.ones((2, 2), bool), "ink")
    g = Canvas(4, 4)
    g.dither_rect(0, 0, 4, 4, "steel")
    assert g.count_opaque() == 8 and g.is_opaque(0, 0) and not g.is_opaque(1, 0)
    g2 = Canvas(4, 4, fill="steel").dithered(1)
    assert g2.count_opaque() == 8 and not g2.is_opaque(0, 0)


@test
def canvas_patterns():
    rows = ["..k..", ".ksk.", "kssk.", ".k..."]
    c = Canvas.from_pattern(rows, {"k": "ink_black", "s": "skin"})
    assert c.size == (5, 4) and c.get_name(2, 0) == "ink_black" and c.get_name(2, 1) == "skin"
    assert c.get_name(0, 0) is None
    assert c.to_pattern({"ink_black": "k", "skin": "s"}) == rows
    auto = c.to_pattern()
    assert auto[0] == "..a.." and auto[1] == ".aba."
    raises(KeyError, Canvas.from_pattern, ["x"], {})
    raises(ValueError, Canvas.from_pattern, [], {})
    raises(ValueError, Canvas.from_pattern, [""], {})
    d = Canvas(8, 8, fill="paper")
    d.paste_pattern(["ab", " ."], 1, 1, {"a": "moss", "b": None})
    assert d.get_name(1, 1) == "moss" and d.get_name(2, 1) is None and d.get_name(1, 2) == "paper"
    d.paste_pattern(["zz"], 7, 7, {"z": "jade"})            # clipped
    assert d.get_name(7, 7) == "jade"


@test
def canvas_blit_and_transforms():
    src = Canvas.from_pattern(["ab", "c."], {"a": "moss", "b": "jade", "c": "plum"})
    dst = Canvas(4, 4, fill="paper")
    dst.blit(src, 1, 1)
    assert dst.get_name(1, 1) == "moss" and dst.get_name(2, 1) == "jade" and dst.get_name(2, 2) == "paper"
    dst.blit(src, 3, 3)                                      # clipped
    assert dst.get_name(3, 3) == "moss"
    dst.blit(src, -1, -1)
    assert dst.get_name(0, 0) is None or dst.get_name(0, 0) == "paper"  # src (1,1) is transparent
    fx = Canvas(4, 4)
    fx.blit(src, 0, 0, flip_x=True)
    assert fx.get_name(0, 0) == "jade" and fx.get_name(1, 0) == "moss" and fx.get_name(1, 1) == "plum"
    fy = Canvas(4, 4)
    fy.blit(src, 0, 0, flip_y=True)
    assert fy.get_name(0, 0) == "plum" and fy.get_name(0, 1) == "moss"
    assert src.flipped_x().get_name(0, 0) == "jade" and src.flipped_y().get_name(0, 0) == "plum"
    r = src.rotated(1)                                       # clockwise: 'c' (bottom-left) -> top-left
    assert r.get_name(0, 0) == "plum" and r.get_name(1, 0) == "moss" and r.get_name(1, 1) == "jade"
    assert src.rotated(4).equals(src) and src.rotated(-1).equals(src.rotated(3))
    m = Canvas.from_pattern(["ab..", "c..."], {"a": "moss", "b": "jade", "c": "plum"}).mirrored_lr()
    assert m.get_name(3, 0) == "moss" and m.get_name(2, 0) == "jade"
    t = Canvas.from_pattern(["a", ".", "."], {"a": "moss"}).mirrored_tb()
    assert t.get_name(0, 2) == "moss"
    o = Canvas(5, 5)
    o.set(2, 2, "skin")
    ol = o.outlined()
    assert ol.get_name(1, 2) == "ink_black" and ol.get_name(2, 1) == "ink_black" and ol.get_name(1, 1) is None
    assert ol.get_name(2, 2) == "skin"
    assert o.outlined(diagonal=True).get_name(1, 1) == "ink_black"
    assert o.outlined("vermilion").get_name(1, 2) == "vermilion"
    assert o.outlined("outline").get_name(1, 2) == "ink_black"          # v1 alias
    edge = Canvas(1, 1, fill="skin")
    assert edge.outlined().size == (1, 1) and edge.outlined(grow=True).size == (3, 3)
    assert edge.outlined(grow=True).get_name(1, 1) == "skin"
    rc = src.recolored({"moss": "jade", "jade": "moss"})
    assert rc.get_name(0, 0) == "jade" and rc.get_name(1, 0) == "moss" and rc.get_name(0, 1) == "plum"
    sh = src.shifted(1, 0)
    assert sh.get_name(1, 0) == "moss" and sh.get_name(0, 0) is None
    wr = src.shifted(1, 0, wrap=True)
    assert wr.get_name(0, 0) == "jade"
    cr = src.cropped(1, 0, 2, 2)
    assert cr.size == (2, 2) and cr.get_name(0, 0) == "jade" and cr.get_name(1, 0) is None
    ce = src.centered(6, 6)
    assert ce.size == (6, 6) and ce.bbox() == (2, 2, 2, 2)
    assert Canvas(3, 3).centered(5, 5).is_empty()
    sc = src.scaled(3)
    assert sc.size == (6, 6) and sc.get_name(2, 2) == "moss" and sc.get_name(3, 0) == "jade"
    assert src.scaled(1).equals(src)
    raises(ValueError, src.scaled, 0)
    cp = src.copy()
    cp.set(0, 0, "paper")
    assert src.get_name(0, 0) == "moss"


@test
def canvas_io_and_text():
    c = Canvas(12, 7)
    end = c.stamp("a1", 0, 1, "paper_light")
    assert end == 8 and c.count_opaque() > 0
    assert pk.text_width("abc") == 12 and pk.text_width("ab", 2) == 16
    raises(ValueError, c.stamp, "x", 0, 0, "paper", font="8x8")
    img = c.to_image()
    assert img.mode == "RGBA" and img.size == (12, 7)
    p = out("canvas.png")
    assert c.save(p) == p and os.path.isfile(p)
    assert Canvas.load(p).equals(c)
    assert Canvas.from_image(img).equals(c)
    arr = np.zeros((2, 2, 4), np.uint8)
    arr[0, 0] = (10, 20, 30, 128)
    arr[1, 1] = (1, 1, 1, 0)
    fa = Canvas.from_array(arr)
    assert fa.get(0, 0) == (10, 20, 30, 255) and fa.get(1, 1) == (0, 0, 0, 0), "alpha normalised to 0/255"
    assert Canvas.from_array(np.zeros((2, 3, 3), np.uint8)).count_opaque() == 6
    raises(ValueError, Canvas.from_array, np.zeros((2, 2), np.uint8))


# ------------------------------------------------------------------------------------------
# Rng
# ------------------------------------------------------------------------------------------
@test
def rng_determinism():
    a, b = Rng(7), Rng(7)
    seq_a = [a.randint(0, 100) for _ in range(5)] + [a.random(), a.uniform(1, 2), a.choice("xyz")]
    seq_b = [b.randint(0, 100) for _ in range(5)] + [b.random(), b.uniform(1, 2), b.choice("xyz")]
    assert seq_a == seq_b
    assert Rng("s").fork("x").randint(0, 10 ** 9) == Rng("s").fork("x").randint(0, 10 ** 9)
    assert Rng("s").fork("x").randint(0, 10 ** 9) != Rng("s").fork("y").randint(0, 10 ** 9)
    lst = list(range(10))
    Rng(1).shuffle(lst)
    assert sorted(lst) == list(range(10))
    r = Rng(3)
    assert len(r.sample(range(10), 3)) == 3 and len(r.choices("ab", k=4)) == 4
    assert isinstance(r.chance(0.5), bool) and repr(r) == "Rng(3)"


# ------------------------------------------------------------------------------------------
# blob47
# ------------------------------------------------------------------------------------------
@test
def blob_masks_and_kinds():
    assert len(CANONICAL_MASKS) == 47 and CANONICAL_MASKS[0] == 0 and CANONICAL_MASKS[-1] == 255
    assert canonicalize(MASK_NE) == 0 and canonicalize(MASK_N | MASK_NE) == MASK_N
    assert canonicalize(MASK_N | MASK_E | MASK_NE) == MASK_N | MASK_E | MASK_NE
    assert is_canonical(255) and not is_canonical(2)
    assert mask_from_neighbors(n=True, e=True, ne=True) == 7 and mask_from_neighbors(ne=True) == 0
    assert quadrant_kinds(0) == ("corner_out",) * 4
    assert quadrant_kinds(255) == ("inner",) * 4
    assert quadrant_kinds(MASK_E | MASK_W) == ("edge_h",) * 4          # strip: N/S missing
    assert quadrant_kinds(MASK_N | MASK_S) == ("edge_v",) * 4          # strip: W/E missing
    assert quadrant_kinds(MASK_N | MASK_E) == ("edge_v", "corner_in", "corner_out", "edge_h")
    assert quadrant_kinds(MASK_N | MASK_E | MASK_NE) == ("edge_v", "inner", "corner_out", "edge_h")
    assert quadrant_kinds(255 & ~MASK_NW) == ("corner_in", "inner", "inner", "inner")
    assert quadrant_kinds(MASK_S) == ("corner_out", "corner_out", "edge_v", "edge_v")
    assert quadrant_kind(MASK_W, 0) == "edge_h" and quadrant_kind(MASK_W, 1) == "corner_out"


@test
def blob47_assembly():
    calls = []

    def q(qi, kind, frame, rng):
        calls.append((qi, kind, frame))
        c = Canvas(8, 8, fill="earth_light")
        top, left = qi in (0, 1), qi in (0, 2)
        if kind in ("edge_h", "corner_out"):
            c.hline(0, 7, 0 if top else 7, "moss")
        if kind in ("edge_v", "corner_out"):
            c.vline(0 if left else 7, 0, 7, "moss")
        if kind == "corner_in":
            c.set(0 if left else 7, 0 if top else 7, "moss")
        if frame:
            c.set(3, 3, "moss_light")
        return c

    tiles = blob47(q, size=16, frames=2, rng=Rng(1))
    assert [m for m, _ in tiles] == list(CANONICAL_MASKS)
    assert all(len(f) == 2 and all(c.size == (16, 16) for c in f) for _, f in tiles)
    assert len(calls) == 4 * 5 * 2, "cache: each (quadrant, kind, frame) drawn once"
    by_mask = dict(tiles)
    assert by_mask[255][0].colors_used() == ["earth_light"]
    iso = by_mask[0][0]
    assert iso.get_name(0, 0) == "moss" and iso.get_name(15, 15) == "moss" and iso.get_name(8, 8) == "earth_light"
    assert by_mask[255][1].get_name(3, 3) == "moss_light" and by_mask[255][0].get_name(3, 3) == "earth_light"
    raises(ValueError, blob47, q, size=15)
    raises(ValueError, blob47, q, frames=0)
    raises(ValueError, blob47, lambda *a: Canvas(4, 4))
    raises(TypeError, blob47, lambda *a: None)
    uncached = blob47(q, cache=False)
    assert len(uncached) == 47


# ------------------------------------------------------------------------------------------
# Sheet
# ------------------------------------------------------------------------------------------
def tile(color="moss", mark=None, size=16):
    c = Canvas(size, size, fill=color)
    if mark is not None:
        c.set(mark % size, (mark * 3) % size, "moss_light")
    return c


@test
def sheet_construction_rules():
    s = Sheet("town", kind="tiles", pivot=(0.5, 0.0), max_width=512, cell_size=16)
    assert s.pivot == (0.5, 0.0) and s.cell_size == 16 and s.max_width == 512 and s.file_name == "town"
    assert Sheet("slash_heavy", "fx").file_name == "SlashHeavy"
    assert Sheet("sprite_sheet_slash01", "fx").file_name == "SpriteSheetSlash01"
    assert Sheet("icons", "icons", file_name="icons_sheet").file_name == "icons_sheet"
    raises(ValueError, Sheet, "Town", "tiles")
    raises(ValueError, Sheet, "town", "props")
    raises(ValueError, Sheet, "town", "tiles", max_width=1024)
    raises(ValueError, Sheet, "town", "tiles", columns=0)
    raises(ValueError, Sheet, "town", "tiles", file_name="village")
    raises(ValueError, Sheet, "town", "tiles", file_name="town.png")
    assert len(s) == 0 and "town_x" not in s and repr(s).startswith("Sheet('town'")


@test
def sheet_add_rules():
    s = Sheet("town", "tiles")
    assert s.add("town_well", tile(), solid=True, ground="ground_grass_0", tags=["building", "well"]) == "town_well"
    e = s.get("town_well")
    assert e.solid and not e.overlay and e.ground == "ground_grass_0" and e.tags == "building,well"
    assert e.pivot == (0.5, 0.0) and e.border == (0, 0, 0, 0) and e.fixed is None
    assert "town_well" in s and s.get_canvas("town_well").equals(tile()) and s.sprite_names == ["town_well"]
    raises(ValueError, s.add, "town_well", tile())                      # duplicate
    raises(ValueError, s.add, "well", tile())                           # missing prefix
    raises(ValueError, s.add, "town_Well", tile())                      # not snake_case
    raises(ValueError, s.add, "town_odd", Canvas(20, 16))               # off grid on a tile sheet
    raises(ValueError, s.add, "town_wide", Canvas(528, 16))             # wider than max_width
    raises(TypeError, s.add, "town_img", Image.new("RGBA", (16, 16)))
    raises(ValueError, s.add, "town_b", tile(), border=(9, 0, 9, 0))    # border too big
    raises(ValueError, s.add, "town_s", tile(), single_name="../x")
    s.add("town_mat", tile(), pivot=(0.5, 0.5), border=(2, 2, 2, 2), overlay=True, single_name="Mats/mat")
    assert s.get("town_mat").pivot == (0.5, 0.5) and s.get("town_mat").border == (2, 2, 2, 2)
    assert s.descriptor("town_mat") == "mat" and s.single_file_name("town_mat") == "Mats/mat.png"
    assert s.single_file_name("town_well") == "well.png"
    lax = Sheet("ui", "ui", strict_names=False)
    lax.add("cursor", Canvas(16, 16, fill="paper"))
    ui = Sheet("ui", "ui")
    ui.add("ui_bar", Canvas(48, 8, fill="jade"), border=(3, 3, 3, 3))  # non-tile kinds: any size
    names = ui.add_frames("ui_arrow_down", [Canvas(16, 16, fill="paper")] * 2)
    assert names == ["ui_arrow_down_0", "ui_arrow_down_1"]


@test
def sheet_packing_rules():
    s = Sheet("ground", "tiles")
    for i in range(40):
        s.add(f"ground_t{i}", tile(mark=i))
    rects = s.rects()
    assert rects["ground_t0"] == (0, 0, 16, 16) and rects["ground_t31"] == (496, 0, 16, 16)
    assert rects["ground_t32"] == (0, 16, 16, 16), "wraps at max_width 512"
    s.add("ground_big", Canvas(48, 48, fill="earth"))
    assert s.rects()["ground_big"] == (0, 32, 48, 48), "different height starts a new row"
    s.add("ground_big2", Canvas(48, 48, fill="earth"))
    assert s.rects()["ground_big2"] == (48, 32, 48, 48)
    s.add("ground_small", tile())
    assert s.rects()["ground_small"] == (0, 80, 16, 16)
    assert s.png_size() == (512, 96)
    r = s.render()
    assert r.size == (512, 96) and r.get_name(0, 32) == "earth" and r.get_name(5, 5) == "moss"
    u = Sheet("ui", "ui")
    u.add("ui_a", Canvas(20, 20, fill="paper"))
    u.add("ui_b", Canvas(20, 20, fill="paper"))
    u.add("ui_c", Canvas(10, 10, fill="paper"))
    assert u.png_size() == (48, 32), "bounding box 40x30 rounded up to 16"
    assert u.rects()["ui_c"] == (0, 20, 10, 10)
    cols = Sheet("icons", "icons", columns=3)
    for i in range(7):
        cols.add(f"icons_i{i}", Canvas(40, 40, fill="gold"))
    assert cols.rects()["icons_i3"] == (0, 40, 40, 40) and cols.rects()["icons_i6"] == (0, 80, 40, 40)
    assert cols.png_size() == (128, 128)
    raises(ValueError, Sheet("x", "ui").render)


@test
def sheet_add_at_fixed():
    s = Sheet("hero", "character")
    s.add_at("hero_a", tile(), 16, 32)
    s.add_at("hero_b", tile(), 112, 48)
    raises(ValueError, s.add_at, "hero_c", tile(), 20, 40)            # overlaps hero_a
    raises(ValueError, s.add_at, "hero_d", tile(), -1, 0)
    raises(ValueError, s.add_at, "hero_e", tile(), 500, 0)             # exceeds max_width
    assert s.rects()["hero_a"] == (16, 32, 16, 16) and s.rects()["hero_b"] == (112, 48, 16, 16)
    s.add("hero_flow", tile())
    assert s.rects()["hero_flow"] == (0, 64, 16, 16), "packed sprites start below the fixed block"
    assert s.png_size() == (128, 80)
    t = Sheet("ground", "tiles")
    raises(ValueError, t.add_at, "ground_x", tile(), 8, 0)             # off grid on a tile sheet
    t.add_at("ground_x", tile(), 32, 16)
    assert t.png_size() == (48, 32)


@test
def sheet_metadata_and_sidecar_shape():
    s = Sheet("ground", "tiles", pivot=(0.5, 0.0))
    s.add("ground_grass_0", tile(mark=0), tags="grass")
    s.add("ground_water_0", tile("water"), solid=True)
    s.add("ground_water_1", tile("water_light"), solid=True)
    s.add("ground_house", Canvas(48, 48, fill="paper"), solid=True, ground="ground_grass_0", tags="building,house")
    s.add_tile("GrassA", "ground_grass_0")
    s.add_tile("WaterA", "ground_water_0", collider="grid")
    s.add_animation("water", ["ground_water_0", "ground_water_1"], fps=4, loop=True, state="water")
    raises(ValueError, s.add_animation, "water", ["ground_water_0"], 4)           # duplicate
    raises(ValueError, s.add_animation, "w2", [], 4)
    raises(ValueError, s.add_animation, "w3", ["ground_water_0"], 0)
    raises(ValueError, s.add_animation, "w4", ["ground_water_0"], 4, direction="north")
    raises(ValueError, s.add_tile, "GrassA", "ground_grass_0")
    raises(ValueError, s.add_tile, "X", "ground_grass_0", collider="mesh")
    doc = s.to_json_dict()
    assert list(doc.keys()) == ["version", "sheet", "kind", "pixelsPerUnit", "defaultPivotX", "defaultPivotY",
                                "cellSize", "stripFrames", "stripFps", "sprites", "animations", "tiles",
                                "tileRules", "ruleTileDefaults"]
    assert doc["version"] == 2 and doc["kind"] == "tiles" and doc["pixelsPerUnit"] == 16 and doc["cellSize"] == 16
    assert doc["defaultPivotX"] == 0.5 and doc["defaultPivotY"] == 0.0
    assert doc["stripFrames"] == 0 and doc["stripFps"] == 0
    sp = doc["sprites"]
    assert list(sp[0].keys()) == ["name", "x", "y", "w", "h", "pivotX", "pivotY", "borderL", "borderB",
                                  "borderR", "borderT", "cellX", "cellY", "cellW", "cellH", "solid",
                                  "overlay", "ground", "tags"]
    house = sp[3]
    assert (house["x"], house["y"], house["w"], house["h"]) == (0, 16, 48, 48)
    assert (house["cellX"], house["cellY"], house["cellW"], house["cellH"]) == (0, 1, 3, 3)
    assert house["solid"] is True and house["ground"] == "ground_grass_0" and house["tags"] == "building,house"
    assert doc["animations"][0] == {"name": "water", "state": "water", "direction": "", "fps": 4, "loop": True,
                                    "frames": ["ground_water_0", "ground_water_1"]}
    assert doc["tiles"][1] == {"name": "WaterA", "sprite": "ground_water_0", "collider": "grid"}
    txt = s.to_json()
    assert txt.startswith('{\n  "version": 2,\n  "sheet": "ground",') and txt.endswith("}\n")
    assert '"defaultPivotY": 0.0' in txt and json.loads(txt) == json.loads(json.dumps(doc))
    assert s.validate() == []


@test
def sheet_save_is_deterministic_and_checked():
    s = Sheet("ground", "tiles")
    for i in range(5):
        s.add(f"ground_g{i}", tile(mark=i))
    d1, d2 = out("det1", "x"), out("det2", "x")
    p1, j1 = s.save(os.path.dirname(d1))
    p2, j2 = s.save(os.path.dirname(d2))
    assert os.path.basename(p1) == "ground.png" and os.path.basename(j1) == "ground.sprites.json"
    assert open(p1, "rb").read() == open(p2, "rb").read() and open(j1, "rb").read() == open(j2, "rb").read()
    with Image.open(p1) as img:
        assert img.mode == "RGBA" and img.size == (80, 16)
    assert check_sheet(p1) == []
    assert pk.sidecar_path(p1) == j1
    # a tile sheet whose sprite is off the grid cannot even be built; a sheet with dangling
    # references cannot be saved
    bad = Sheet("ground", "tiles")
    bad.add("ground_a", tile())
    bad.add_animation("x", ["ground_missing"], 4)
    raises(ValueError, bad.save, out("bad", "x") and os.path.dirname(out("bad", "x")))
    assert any("missing sprite" in p for p in bad.validate())
    assert bad.validate(strict=False) and "sheet has no sprites" in Sheet("e", "ui").validate()


@test
def sheet_blob_rules_and_defaults():
    def q(qi, kind, frame, rng):
        c = Canvas(8, 8, fill="water")
        if kind != "inner":
            c.set(0, 0, "water_light")
        if frame:
            c.set(4, 4, "water_light")
        return c

    s = Sheet("autotiles", "autotiles")
    names = s.add_blob("Water", "autotiles_water", blob47(q, frames=2), collider="grid", anim_fps=4)
    assert names[0] == "autotiles_water_m0_f0" and names[-1] == "autotiles_water_m255_f0"
    assert len(s) == 94 and len(s.tile_rules) == 47
    assert s.rule_tile_defaults == [{"ruleTile": "Water", "defaultSprite": "autotiles_water_m255_f0", "collider": "grid"}]
    r = s.tile_rules[-1]
    assert r == {"ruleTile": "Water", "sprite": "autotiles_water_m255_f0", "mask": 255,
                 "animFrames": ["autotiles_water_m255_f0", "autotiles_water_m255_f1"], "animFps": 4}
    s.add_blob("Road", "autotiles_road", blob47(lambda *a: Canvas(8, 8, fill="earth_light")))
    assert s.tile_rules[-1] == {"ruleTile": "Road", "sprite": "autotiles_road_m255", "mask": 255,
                                "animFrames": [], "animFps": 0}
    raises(ValueError, s.add_tile_rule, "Road", "autotiles_road_m255", 255)      # duplicate
    raises(ValueError, s.add_tile_rule, "Road", "autotiles_road_m2", 2)          # non-canonical
    raises(ValueError, s.add_tile_rule, "X", "autotiles_road_m0", 0, anim_frames=["autotiles_road_m0"], anim_fps=0)
    raises(ValueError, s.add_tile_rule, "X", "autotiles_road_m0", 0, anim_frames=["autotiles_road_m1"], anim_fps=4)
    raises(ValueError, s.set_rule_tile_default, "Road", "autotiles_road_m255", collider="mesh")
    s.set_rule_tile_default("Road", "autotiles_road_m0")
    assert [d["ruleTile"] for d in s.rule_tile_defaults] == ["Water", "Road"]      # replaced, not duplicated
    assert s.validate() == []
    png, js = s.save(out("blob", "x") and os.path.dirname(out("blob", "x")))
    assert check_sheet(png) == []
    assert s.png_size()[0] % 16 == 0 and s.png_size()[1] % 16 == 0
    # incomplete rule tile is a strict problem
    inc = Sheet("autotiles", "autotiles")
    inc.add("autotiles_cliff_m255", tile("ink"))
    inc.add_tile_rule("Cliff", "autotiles_cliff_m255", 255)
    probs = inc.validate()
    assert any("missing 46 masks" in p for p in probs) and any("no ruleTileDefaults" in p for p in probs)
    assert inc.validate(strict=False) == []


@test
def sheet_strip_layout():
    fx = Sheet("slash_heavy", "fx", pivot=(0.5, 0.5))
    frames = []
    for i in range(5):
        f = Canvas(48, 48)
        f.circle(24, 24, 3 + i * 4, "gold_light")
        f.circle(24, 24, 3 + i * 4, "vermilion_light", fill=False)
        frames.append(f)
    fx.add_frames("slash_heavy", frames)
    raises(ValueError, fx.save, os.path.dirname(out("fx", "x")))            # fx must be a strip
    fx.set_strip(frames=5, fps=14)
    assert fx.is_strip and fx.strip_frames == 5 and fx.strip_fps == 14
    assert [r[1:3] for r in fx.layout()] == [(0, 0), (48, 0), (96, 0), (144, 0), (192, 0)]
    assert fx.png_size() == (240, 48)
    png, js = fx.save(os.path.dirname(out("fx", "x")))
    assert os.path.basename(png) == "SlashHeavy.png" and os.path.basename(js) == "SlashHeavy.sprites.json"
    doc = json.load(open(js))
    assert doc["stripFrames"] == 5 and doc["stripFps"] == 14 and doc["sheet"] == "slash_heavy"
    assert check_sheet(png) == []
    # Unity-style equal division reproduces the frames
    with Image.open(png) as img:
        assert img.size == (240, 48)
        fw = img.width // 5
        for i in range(5):
            frame = Canvas.from_image(img.crop((i * fw, 0, (i + 1) * fw, 48)))
            assert frame.equals(frames[i])
    # count mismatch is refused; odd sizes keep exact strip size (no 16px rounding)
    fx.set_strip(frames=6, fps=14)
    assert any("stripFrames = 6" in p for p in fx.validate())
    raises(ValueError, fx.set_strip, 0, 10)
    raises(ValueError, fx.set_strip, 3, -1)
    still = Sheet("arrow", "fx", pivot=(0.5, 0.5))
    still.add("arrow_0", Canvas(20, 10, fill="ink_pale"))
    still.set_strip(1, 0)
    assert still.png_size() == (20, 10) and still.validate() == []
    uneven = Sheet("dust", "fx", pivot=(0.5, 0.5))
    uneven.add("dust_0", Canvas(48, 48, fill="ink_pale"))
    uneven.add("dust_1", Canvas(32, 48, fill="ink_pale"))
    uneven.set_strip(2, 12)
    assert any("expected 48x48" in p for p in uneven.validate())
    offcenter = Sheet("dust", "fx")                                    # default pivot (0.5, 0)
    offcenter.add("dust_0", Canvas(48, 48, fill="ink_pale"))
    offcenter.set_strip(1, 0)
    assert any("centre pivot" in p for p in offcenter.validate())


@test
def sheet_save_singles_with_subfolders():
    ui = Sheet("ui", "ui", file_name="ui_sheet")
    ui.add("ui_status_bleed", Canvas(16, 16, fill="vermilion"), single_name="Status/bleed")
    ui.add("ui_marker_town", Canvas(16, 16, fill="paper"), single_name="Markers/town")
    ui.add("ui_panel_paper", Canvas(24, 24, fill="paper"), border=(8, 8, 8, 8), single_name="Frames/panel_paper")
    ui.add("ui_cursor", Canvas(16, 16, fill="gold"))
    root = os.path.dirname(out("singles", "x"))
    paths = ui.save_singles(root)
    rel = [os.path.relpath(p, root).replace(os.sep, "/") for p in paths]
    assert rel == ["Status/bleed.png", "Markers/town.png", "Frames/panel_paper.png", "cursor.png"]
    assert all(os.path.isfile(p) for p in paths)
    assert Canvas.load(paths[0]).equals(Canvas(16, 16, fill="vermilion"))
    assert ui.save_singles(root, names=["ui_cursor"]) == [os.path.join(root, "cursor.png")]
    png, js = ui.save(root)
    assert os.path.basename(png) == "ui_sheet.png" and check_sheet(png) == []
    assert json.load(open(js))["sprites"][2]["borderL"] == 8
    icons = Sheet("icons", "icons", file_name="icons_sheet")
    icons.add("icons_jian", Canvas(40, 40, fill="steel"))
    icons.add("icons_coin", Canvas(40, 40, fill="gold"))
    ip = icons.save_singles(root)
    assert [os.path.basename(p) for p in ip] == ["jian.png", "coin.png"]
    clash = Sheet("icons", "icons")
    clash.add("icons_a", Canvas(4, 4, fill="gold"), single_name="x")
    clash.add("icons_b", Canvas(4, 4, fill="gold"), single_name="X")
    raises(ValueError, clash.save_singles, root)


@test
def sheet_previews_and_cellmap():
    s = Sheet("nature", "tiles")
    s.add("nature_bush_a", tile("moss_dark"), solid=True, ground="ground_grass_0", tags="bush")
    s.add("nature_pine_a", Canvas(32, 32, fill="moss_dark").outlined(), solid=True, ground="ground_grass_0")
    s.add("nature_reed_a", tile("moss_pale"), overlay=True)
    pv = out("previews", "nature_preview.png")
    assert s.preview(pv, scale=4, labels=True) == pv
    with Image.open(pv) as img:
        assert img.size[0] >= 64 and img.size[1] > 32 * 4
    s.preview(out("previews", "nature_nolabel.png"), scale=2, labels=False)
    gp = s.preview_group(out("previews", "nature_pine.png"), "nature_pine", scale=8)
    assert os.path.isfile(gp)
    raises(ValueError, s.preview_group, out("previews", "none.png"), "nature_zzz")
    cm_png, cm_md = out("cellmaps", "nature_cellmap.png"), out("cellmaps", "nature.md")
    assert s.cellmap(cm_png, cm_md, scale=3) == (cm_png, cm_md)
    with Image.open(cm_png) as img:
        assert img.size == (s.png_size()[0] * 3, s.png_size()[1] * 3)
        px = np.asarray(img.convert("RGBA"))
        pale = palette.NAME_TO_RGB["ink_pale"]
        # rows: bush (0,0) 16px, pine (0,16) 32px, reed (0,48) 16px -> PNG 32x64, map 96x192
        assert tuple(px[0, 48, :3]) == pale and tuple(px[96, 50, :3]) == pale, "16px grid lines at scale 3"
        red = palette.NAME_TO_RGB["vermilion_light"]
        assert tuple(px[48, 5, :3]) == red, "sprite rect outline (pine top edge)"
    md = open(cm_md, encoding="utf-8").read()
    assert "| name | cell x,y | size | solid | overlay | ground | tags |" in md
    assert "| nature_bush_a | 0,0 | 1x1 | yes | no | ground_grass_0 | bush |" in md
    assert "| nature_pine_a | 0,1 | 2x2 | yes | no | ground_grass_0 |  |" in md
    assert "| nature_reed_a | 0,3 | 1x1 | no | yes |  |  |" in md


@test
def sheet_load_round_trip():
    s = Sheet("town", "tiles")
    s.add("town_well", tile("ink_light").outlined(), solid=True, ground="ground_grass_0", tags="well")
    s.add("town_inn", Canvas(80, 64, fill="paper"), solid=True, tags="building")
    s.add("town_torch_0", tile("gold"))
    s.add("town_torch_1", tile("gold_light"))
    s.add_animation("torch", ["town_torch_0", "town_torch_1"], 6, state="torch")
    s.add_tile("Well", "town_well", collider="sprite")
    png, js = s.save(os.path.dirname(out("rt", "x")))
    ld = Sheet.load(png)
    assert ld.name == "town" and ld.kind == "tiles" and ld.file_name == "town" and ld.sprite_names == s.sprite_names
    assert ld.rects() == s.rects() and ld.png_size() == s.png_size()
    assert ld.render().equals(s.render())
    assert ld.get("town_well").solid and ld.get("town_well").ground == "ground_grass_0" and ld.get("town_well").tags == "well"
    assert ld.animations == s.animations and ld.tiles == s.tiles
    assert ld.to_json() == s.to_json()
    assert ld.validate() == []
    ld.save(os.path.dirname(out("rt2", "x")))
    assert open(out("rt2", "town.png"), "rb").read() == open(png, "rb").read()


# ------------------------------------------------------------------------------------------
# character_sheet
# ------------------------------------------------------------------------------------------
def body(col, dx=0):
    c = Canvas(16, 16)
    c.rect(5 + dx, 2, 6, 11, col)
    c.rect(6 + dx, 3, 4, 4, "skin")
    return c.outlined()


def make_character(name="hero_1", with_face=True):
    walk = {d: [body("paper", (i % 2)) for i in range(4)] for d in DIRECTIONS}
    attack = {d: [body("jade", i - 1) for i in range(3)] for d in DIRECTIONS}
    hurt = {d: body("vermilion") for d in DIRECTIONS}
    face = None
    if with_face:
        face = Canvas(32, 32)
        face.circle(16, 14, 9, "skin")
        face.rect(8, 22, 16, 10, "paper")
        face = face.outlined()
    return character_sheet(name, walk, attack, hurt, face)


@test
def character_sheet_layout():
    sheet, face = make_character()
    assert isinstance(sheet, Sheet) and isinstance(face, Sheet)
    assert sheet.kind == "character" and sheet.name == "hero_1" and sheet.pivot == (0.5, 0.0)
    assert face.kind == "face" and face.name == "hero_1_face" and face.sprite_names == ["hero_1_face"]
    assert sheet.png_size() == (128, 64) and face.png_size() == (32, 32)
    assert len(sheet) == 32 and sheet.validate() == [] and sheet.validate_character() == [] and face.validate() == []
    rects = sheet.rects()
    for di, d in enumerate(DIRECTIONS):
        for i in range(4):
            assert rects[f"hero_1_walk_{d}_{i}"] == (di * 16, i * 16, 16, 16)
        for i in range(3):
            assert rects[f"hero_1_attack_{d}_{i}"] == ((4 + di) * 16, i * 16, 16, 16)
        assert rects[f"hero_1_hurt_{d}"] == ((4 + di) * 16, 48, 16, 16)
    anims = {a["name"]: a for a in sheet.animations}
    assert len(anims) == 16
    assert anims["walk_left"] == {"name": "walk_left", "state": "walk", "direction": "left", "fps": 8, "loop": True,
                                  "frames": [f"hero_1_walk_left_{i}" for i in range(4)]}
    assert anims["attack_up"]["fps"] == 12 and anims["attack_up"]["loop"] is False and len(anims["attack_up"]["frames"]) == 3
    assert anims["idle_down"]["frames"] == ["hero_1_walk_down_0"] and anims["hurt_right"]["frames"] == ["hero_1_hurt_right"]
    # save, reload the PNG and assert the 128x64 grid, then the reviewer helpers
    d = os.path.dirname(out("chars", "x"))
    png, js = sheet.save(d)
    fpng, fjs = face.save(d)
    assert os.path.basename(png) == "hero_1.png" and os.path.basename(fpng) == "hero_1_face.png"
    with Image.open(png) as img:
        assert img.size == (128, 64) and img.mode == "RGBA"
        whole = Canvas.from_image(img)
    with Image.open(fpng) as img:
        assert img.size == (32, 32)
    doc = json.load(open(js))
    assert doc["kind"] == "character" and len(doc["sprites"]) == 32 and doc["defaultPivotY"] == 0.0
    for sp in doc["sprites"]:
        assert (sp["w"], sp["h"]) == (16, 16) and sp["x"] % 16 == 0 and sp["y"] % 16 == 0
        assert whole.cropped(sp["x"], sp["y"], 16, 16).equals(sheet.get_canvas(sp["name"]))
    # GPA's Frames(): column = direction, row = frame; row 0 = standing
    for di, d in enumerate(DIRECTIONS):
        for i in range(4):
            assert whole.cropped(di * 16, i * 16, 16, 16).equals(sheet.get_canvas(f"hero_1_walk_{d}_{i}"))
    assert check_sheet(png) == [] and check_sheet(fpng) == [] and check_character_sheet(png) == []
    assert Sheet.load(png).validate_character() == []
    assert json.load(open(fjs))["sprites"][0]["name"] == "hero_1_face"
    sheet_only, no_face = make_character("soyuk", with_face=False)
    assert no_face is None and sheet_only.validate() == []


@test
def character_sheet_validation_errors():
    walk = {d: [body("paper") for _ in range(4)] for d in DIRECTIONS}
    attack = {d: [body("jade") for _ in range(3)] for d in DIRECTIONS}
    hurt = {d: body("vermilion") for d in DIRECTIONS}
    bad_walk = dict(walk)
    bad_walk["up"] = walk["up"][:3]
    raises(ValueError, character_sheet, "x", bad_walk, attack, hurt)
    bad_size = dict(walk)
    bad_size["left"] = [Canvas(16, 17)] * 4
    raises(ValueError, character_sheet, "x", bad_size, attack, hurt)
    raises(ValueError, character_sheet, "x", {k: v for k, v in walk.items() if k != "right"}, attack, hurt)
    raises(ValueError, character_sheet, "x", walk, attack, hurt, face=Canvas(16, 16))
    raises(TypeError, character_sheet, "x", walk, attack, hurt, face="face")
    raises(ValueError, character_sheet, "Hero", walk, attack, hurt)
    # a hand-built sheet that misses the §5.1 layout is rejected on save, and
    # validate_character names the missing parts
    s = Sheet("npc", "character")
    s.add_at("npc_walk_down_0", body("paper"), 0, 0)
    probs = s.validate_character()
    assert any("missing character sprite 'npc_walk_down_1'" in p for p in probs)
    assert any("missing animation 'walk_down'" in p for p in probs)
    assert any("128x64" in p for p in probs)
    raises(ValueError, s.save, os.path.dirname(out("charbad", "x")))
    s.save(os.path.dirname(out("charbad", "x")), strict=False)             # WIP saves are allowed
    f = Sheet("npc_face", "face")
    f.add("npc_face_big", Canvas(32, 48, fill="skin"))
    assert any("32x32" in p for p in f.validate()) and any("named 'npc_face'" in p for p in f.validate())


# ------------------------------------------------------------------------------------------
# reviewer helpers
# ------------------------------------------------------------------------------------------
@test
def verify_palette_images():
    good = Canvas(8, 8)
    good.rect(1, 1, 4, 4, "jade")
    good.rect(2, 2, 2, 2, "paper_light")
    p = good.save(out("pal", "good.png"))
    assert verify_palette(p) == [] and verify_palette(good) == []
    arr = np.zeros((4, 4, 4), np.uint8)
    arr[0, 0] = (0x5a, 0x7a, 0x45, 255)       # moss: fine
    arr[1, 2] = (0x5a, 0x7a, 0x46, 255)       # off by one: offends
    arr[2, 3] = (0x5a, 0x7a, 0x45, 128)       # partial alpha: offends
    arr[3, 3] = (9, 9, 9, 0)                  # transparent garbage RGB: fine
    bad_path = out("pal", "bad.png")
    Image.fromarray(arr, "RGBA").save(bad_path)
    offenders = verify_palette(bad_path)
    assert offenders == [(2, 1, (0x5a, 0x7a, 0x46, 255)), (3, 2, (0x5a, 0x7a, 0x45, 128))]
    assert verify_palette(bad_path, max_results=1) == offenders[:1]
    assert verify_palette(np.asarray(Image.open(bad_path).convert("RGBA"))) == offenders
    assert verify_palette(Image.open(bad_path)) == offenders
    raises(ValueError, verify_palette, np.zeros((2, 2, 3), np.uint8))


@test
def check_sheet_good_and_broken():
    s = Sheet("ground", "tiles")
    for i in range(3):
        s.add(f"ground_g{i}", tile(mark=i))
    s.add("ground_w0", tile("water"), solid=True)
    s.add("ground_w1", tile("water_light"), solid=True)
    s.add_animation("water", ["ground_w0", "ground_w1"], 4, state="water")
    s.add_tile("GrassA", "ground_g0")
    d = os.path.dirname(out("chk", "x"))
    png, js = s.save(d)
    assert check_sheet(png) == [] and check_sheet(png, js, palette=False) == []
    assert check_sheet(os.path.join(d, "nope.png")) == [f"missing PNG {os.path.join(d, 'nope.png')}"]
    shutil.copy(png, os.path.join(d, "lonely.png"))
    assert check_sheet(os.path.join(d, "lonely.png"))[0].startswith("missing sidecar")
    good_doc = json.load(open(js))
    with Image.open(png) as img:
        W, H = img.size
    assert check_sidecar(good_doc, W, H, file_base="ground") == []

    def broken(mutate):
        doc = json.loads(json.dumps(good_doc))
        mutate(doc)
        return check_sidecar(doc, W, H, file_base="ground")

    assert any("outside the" in p for p in broken(lambda d: d["sprites"][0].update(x=500)))
    assert any("duplicate sprite name" in p for p in broken(lambda d: d["sprites"][1].update(name="ground_g0")))
    assert any("references missing sprite 'ground_zz'" in p for p in broken(lambda d: d["animations"][0]["frames"].append("ground_zz")))
    assert any("not aligned to the 16px grid" in p for p in broken(lambda d: d["sprites"][0].update(w=8)))
    assert any("cell fields" in p for p in broken(lambda d: d["sprites"][0].update(cellW=2)))
    assert any("prefix" in p for p in broken(lambda d: d["sprites"][0].update(name="grass")))
    assert any("missing key 'cellSize'" in p for p in broken(lambda d: d.pop("cellSize")))
    assert any("version" in p for p in broken(lambda d: d.update(version=1)))
    assert any("unknown kind" in p for p in broken(lambda d: d.update(kind="props")))
    assert any("file name 'town' does not match sheet 'ground'" in p
               for p in check_sidecar(good_doc, W, H, file_base="town"))
    assert any("directional state 'walk' is missing ['up', 'left', 'right']" in p for p in broken(
        lambda d: d["animations"].extend([{"name": "walk_down", "state": "walk", "direction": "down", "fps": 8,
                                           "loop": True, "frames": ["ground_g0"]}])))
    assert any("missing 46 masks" in p for p in broken(
        lambda d: d["tileRules"].append({"ruleTile": "R", "sprite": "ground_g0", "mask": 255, "animFrames": [], "animFps": 0})))
    assert any("not canonical" in p for p in broken(
        lambda d: d["tileRules"].append({"ruleTile": "R", "sprite": "ground_g0", "mask": 2, "animFrames": [], "animFps": 0})))
    assert any("has bad collider" in p for p in broken(lambda d: d["tiles"][0].update(collider="box")))
    assert any("stripFrames = 3" in p for p in broken(lambda d: d.update(stripFrames=3)))
    # broken sidecar on disk, and a palette violation in the PNG
    bad_js = json.loads(json.dumps(good_doc))
    bad_js["sprites"][0]["h"] = 999
    json.dump(bad_js, open(js, "w"))
    assert any("outside the" in p for p in check_sheet(png))
    open(js, "w").write("{not json")
    assert check_sheet(png)[0].startswith("sidecar") and "not valid JSON" in check_sheet(png)[0]
    json.dump(good_doc, open(js, "w"))
    with Image.open(png) as img:
        arr = np.array(img.convert("RGBA"))
    arr[0, 0] = (1, 2, 3, 255)
    Image.fromarray(arr, "RGBA").save(png)
    probs = check_sheet(png)
    assert len(probs) == 1 and probs[0].startswith("palette violation: 1 offending pixels")
    # character sheet checks through check_sheet: a renamed frame breaks the layout
    sheet, _ = make_character("guard", with_face=False)
    cpng, cjs = sheet.save(os.path.dirname(out("chk2", "x")))
    cdoc = json.load(open(cjs))
    cdoc["sprites"][5]["name"] = "guard_walk_down_9"
    json.dump(cdoc, open(cjs, "w"))
    probs = check_sheet(cpng)
    assert any("missing character sprite 'guard_walk_up_1'" in p for p in probs)
    assert any("unexpected sprites" in p for p in probs)
    cdoc = json.load(open(cjs))
    cdoc["kind"] = "tiles"
    json.dump(cdoc, open(cjs, "w"))
    assert any("expected 'character'" in p for p in check_character_sheet(cpng))


# ------------------------------------------------------------------------------------------
# build_all
# ------------------------------------------------------------------------------------------
@test
def build_all_discovery_and_run():
    import build_all
    assert build_all.normalize_name("tiles") == "gen_tiles"
    assert build_all.normalize_name("gen_fx.py") == "gen_fx"
    assert build_all.normalize_name("Tools/pixelgen/gen_ui.py") == "gen_ui"
    assert build_all.select(["gen_a.py", "gen_b.py"], ["b", "a", "zz"]) == (["gen_a.py", "gen_b.py"], ["zz"])
    gen_dir = os.path.dirname(out("gens", "x"))
    open(os.path.join(gen_dir, "gen_ok.py"), "w").write(
        "import os\nfrom pixelkit import Sheet, Canvas\n"
        "def build(art_root, preview_dir, cellmap_dir):\n"
        "    s = Sheet('ground', 'tiles')\n"
        "    s.add('ground_a', Canvas(16, 16, fill='moss'))\n"
        "    png, js = s.save(os.path.join(art_root, 'Tiles'))\n"
        "    pv = s.preview(os.path.join(preview_dir, 'ground_preview.png'))\n"
        "    cm = s.cellmap(os.path.join(cellmap_dir, 'ground_cellmap.png'), os.path.join(cellmap_dir, 'ground.md'))\n"
        "    return [png, js, pv] + list(cm)\n")
    open(os.path.join(gen_dir, "gen_broken.py"), "w").write(
        "def build(art_root, preview_dir, cellmap_dir):\n    raise RuntimeError('boom')\n")
    open(os.path.join(gen_dir, "gen_offpalette.py"), "w").write(
        "import os\nfrom PIL import Image\n"
        "def build(art_root, preview_dir, cellmap_dir):\n"
        "    p = os.path.join(art_root, 'Icons', 'bad.png')\n"
        "    Image.new('RGBA', (4, 4), (1, 2, 3, 255)).save(p)\n    return [p]\n")
    assert build_all.discover(gen_dir) == ["gen_broken.py", "gen_offpalette.py", "gen_ok.py"]
    root = os.path.dirname(out("build_out", "x"))
    args = ["--gen-dir", gen_dir, "--art-root", os.path.join(root, "Art"),
            "--preview-dir", os.path.join(root, "previews"), "--cellmap-dir", os.path.join(root, "cellmaps"), "--quiet"]
    assert build_all.main(args + ["ok"]) == 0
    assert os.path.isfile(os.path.join(root, "Art", "Tiles", "ground.png"))
    assert os.path.isfile(os.path.join(root, "previews", "ground_preview.png"))
    assert os.path.isfile(os.path.join(root, "cellmaps", "ground.md"))
    assert os.path.isdir(os.path.join(root, "Art", "UI", "Status")) and os.path.isdir(os.path.join(root, "Art", "Icons", "Mini"))
    assert build_all.main(args + ["broken"]) == 1
    assert build_all.main(args + ["offpalette"]) == 1
    assert build_all.main(args + ["offpalette", "--no-verify"]) == 0
    assert build_all.main(args) == 1                                         # all: one failure
    assert build_all.main(args + ["nope"]) == 2
    assert build_all.main(args + ["--list"]) == 0
    # as a subprocess (the real entry point), with the real default paths only listed
    r = subprocess.run([sys.executable, os.path.join(HERE, "build_all.py"), "--gen-dir", gen_dir, "--list"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.split() == ["gen_broken", "gen_offpalette", "gen_ok"]
    r = subprocess.run([sys.executable, os.path.join(HERE, "build_all.py")] + args + ["ok"],
                       capture_output=True, text=True)
    assert r.returncode == 0 and "gen_ok" in r.stdout and "0 failed" in r.stdout


# ------------------------------------------------------------------------------------------
def main() -> int:
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="scratch folder (default: a temporary folder)")
    ap.add_argument("--keep", action="store_true", help="keep the scratch folder")
    ap.add_argument("-k", default="", help="only run tests whose name contains this text")
    args = ap.parse_args()
    tmp = None
    if args.out:
        OUT = os.path.abspath(args.out)
        os.makedirs(OUT, exist_ok=True)
    else:
        tmp = tempfile.mkdtemp(prefix="pixelkit_selftest_")
        OUT = tmp
    failed = 0
    ran = 0
    for fn in TESTS:
        if args.k and args.k not in fn.__name__:
            continue
        ran += 1
        try:
            fn()
            print(f"ok    {fn.__name__}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{ran - failed}/{ran} passed" + (f"  (scratch: {OUT})" if args.keep or args.out else ""))
    if tmp and not args.keep:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
