#!/usr/bin/env python3
"""gen_tiles_town.py -- InkPixel `town` prop sheet (ASSET_SPEC.md v2, §5.2 'town').

Writes  Art/Tiles/town.png + town.sprites.json          (kind `tiles`, pivot (0.5, 0), 16px grid)
        Docs/previews/town_preview.png                  (4x contact sheet, labels)
        Docs/previews/town_on_ground_preview.png        (props on grass and on road, 4x)
        Docs/cellmaps/town_cellmap.png + town.md

백로진 (白鷺鎭): an East-Asian riverside market town. 기와 tiled roofs in ink / ink_light with
ink_dark ridges and eave shadows, 초가 thatch in paper_dark / sand / earth, hanji walls on earth
timber frames, dark doorways, lattice windows, a 酒 banner and red lanterns on the inn, a jade
paifang for 청운검문, a bronze_navy banner with a tiny vermilion snake for 흑사방.

Technique: buildings are composed from a small parts kit (tiled / thatched roofs, hanji walls,
doors, lattice windows, stone plinths) drawn with palette names only; small props are ASCII
patterns (`pat()`, one letter per palette color, see CM). Every prop is drawn one pixel inside
its cell footprint and finished with `Canvas.outlined()` (1px ink_black). Pieces that must join
their neighbours (fences, walls, docks, bridge) carry their own outline instead. Light comes from
the top-left. Deterministic: no randomness except fixed-seed Rng for straw / ash specks.
"""
from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from pixelkit import Canvas, Sheet, Rng, pascal_case

SHEET = "town"
GROUND = "ground_grass_0"
CELL = 16

# One letter per palette color (same letters as gen_tiles_nature.py so patterns are portable).
CM: Dict[str, str] = {
    "K": "ink_black", "k": "ink_dark", "i": "ink", "I": "ink_light", "P": "ink_pale",
    "a": "paper_dark", "A": "paper", "W": "paper_light",
    "u": "vermilion_dark", "v": "vermilion", "V": "vermilion_light",
    "j": "jade_dark", "J": "jade", "h": "jade_light",
    "N": "bronze_navy", "n": "navy", "S": "steel",
    "D": "moss_dark", "M": "moss", "L": "moss_light", "p": "moss_pale",
    "E": "earth_dark", "e": "earth", "F": "earth_light", "s": "sand", "o": "skin",
    "g": "gold", "G": "gold_light",
    "x": "water_deep", "w": "water", "c": "water_light", "q": "plum",
}


def pat(text: str, w: int, h: int, extra: Optional[Dict[str, str]] = None) -> Canvas:
    """ASCII block -> Canvas of exactly w x h ('.' transparent, short rows padded with '.')."""
    rows = text.split("\n")
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    if len(rows) != h:
        raise ValueError(f"pattern has {len(rows)} rows, expected {h}")
    out = []
    for i, r in enumerate(rows):
        r = r.rstrip()
        if len(r) > w:
            raise ValueError(f"pattern row {i} is {len(r)} wide, expected <= {w}: {r!r}")
        out.append(r.ljust(w, "."))
    cm = dict(CM)
    if extra:
        cm.update(extra)
    return Canvas.from_pattern(out, cm)


def paste(c: Canvas, text: str, x: int, y: int, extra: Optional[Dict[str, str]] = None) -> None:
    """Paste an ASCII block (leading/trailing blank lines dropped) at (x, y)."""
    rows = text.split("\n")
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    cm = dict(CM)
    if extra:
        cm.update(extra)
    c.paste_pattern([r.rstrip() for r in rows], x, y, cm)


# ------------------------------------------------------------------------------------------
# Building parts kit
# ------------------------------------------------------------------------------------------
def roof_tiled(w: int, h: int, inset: int, body: str = "ink_light", groove: str = "ink",
               light: str = "ink_pale", ridge: str = "ink_dark", finial: Optional[str] = None,
               shade_right: bool = True) -> Canvas:
    """Hip roof of 기와 tiles seen from the front: ridge cap with up-turned ends on rows 0-1, a
    trapezoid slope (ridge `inset` px narrower than the eave on each side), vertical tile
    ridges lit from the left (light / body / body / groove), and a scalloped eave row of tile
    end caps. `finial` (e.g. gold) puts 치미 ornaments on the ridge ends."""
    c = Canvas(w, h)
    top, eave = 2, 2
    slope_rows = h - top - eave
    bounds: Dict[int, Tuple[int, int]] = {}
    for y in range(top, h):
        if y >= h - eave:
            ins = 0
        else:
            t = (y - top) / max(1, slope_rows - 1)
            ins = int(round(inset * (1.0 - t)))
        x0, x1 = ins, w - 1 - ins
        bounds[y] = (x0, x1)
        c.hline(x0, x1, y, body)
    mid = w // 2
    shade_from = w - max(4, w // 4)
    for y in range(top, h - 1):
        x0, x1 = bounds[y]
        row_edge = (h - 2 - y) % 6 == 0 and y > top + 1   # lit upper edge of every tile row
        for x in range(x0 + 1, x1):
            ph = (x - mid) % 4
            if ph == 3:
                c.set(x, y, groove)
            elif ph == 0 and not (shade_right and x >= shade_from):
                c.set(x, y, light)
            elif row_edge and not (shade_right and x >= shade_from):
                c.set(x, y, light)
    # eave end caps: scalloped last row (groove, light, light, groove)
    y = h - 1
    for x in range(1, w - 1):
        ph = (x - mid) % 4
        c.set(x, y, light if ph in (0, 1) else groove)
    c.set(0, y, None)
    c.set(w - 1, y, None)
    c.set(0, y - 1, ridge)          # up-turned eave corners
    c.set(w - 1, y - 1, ridge)
    # hip edges
    for y in range(top, h - eave):
        x0, x1 = bounds[y]
        c.set(x0, y, ridge)
        c.set(x1, y, ridge)
    # ridge cap + curled ends
    x0, x1 = bounds[top]
    c.hline(x0 - 1, x1 + 1, 1, ridge)
    c.set(x0 - 1, 0, ridge)
    c.set(x1 + 1, 0, ridge)
    if finial:
        c.set(x0 - 1, 0, finial)
        c.set(x1 + 1, 0, finial)
        c.set(x0, 0, finial)
        c.set(x1, 0, finial)
    return c


def roof_thatch(w: int, h: int, seed: str, body: str = "paper_dark", light: str = "sand",
                dark: str = "earth", deep: str = "earth_dark") -> Canvas:
    """Rounded 초가 straw roof: paper_dark body, sand highlight on the top-left shoulder, earth
    straw strokes, earth_dark shade along the right and the ragged bottom edge, and a rope
    (새끼줄) ridge line."""
    rng = Rng(f"thatch/{seed}")
    c = Canvas(w, h)
    shoulder = [9, 5, 3, 2, 1]  # insets of the first rows (rounded dome shoulders)
    for y in range(h):
        ins = shoulder[y] if y < len(shoulder) else 0
        c.hline(ins, w - 1 - ins, y, body)
    # highlight: top-left shoulder and a lit band
    for y in range(0, h // 2):
        ins = shoulder[y] if y < len(shoulder) else 0
        x_end = max(ins, w // 2 - y * 2)
        c.hline(ins, x_end, y, light)
    # shade: right side and lower rows
    for y in range(h):
        ins = shoulder[y] if y < len(shoulder) else 0
        depth = 1 + (3 * y) // h
        c.hline(w - 1 - ins - depth, w - 1 - ins, y, dark)
    c.hline(1, w - 2, h - 1, dark)
    c.hline(w - 6, w - 2, h - 2, dark)
    c.set(w - 1, h - 1, None)
    c.set(0, h - 1, None)
    # straw strokes (short vertical dashes), lighter on the left, darker on the right
    for _ in range(w * h // 18):
        x = rng.randint(1, w - 2)
        y = rng.randint(2, h - 3)
        n = rng.randint(1, 2)
        col = dark if x > w // 2 or rng.chance(0.4) else light
        if c.get_name(x, y) in (body, light, dark):
            c.vline(x, y, y + n, col)
    # ragged eave: nibble every few pixels of the last row
    for x in range(2, w - 2, 5):
        c.set(x + (x // 5) % 2, h - 1, None)
    # rope ridge (새끼줄) : a dark line on the shoulder with knots
    c.hline(shoulder[2] + 1, w - 2 - shoulder[2], 2, dark)
    for x in range(shoulder[2] + 2, w - 2 - shoulder[2], 6):
        c.set(x, 2, deep)
        c.set(x, 3, dark)
    # rounded lower corners
    c.set(0, h - 2, None)
    c.set(w - 1, h - 2, None)
    c.set(1, h - 1, None)
    c.set(w - 2, h - 1, None)
    return c


def wall(c: Canvas, x: int, y: int, w: int, h: int, paper: str = "paper", shade: str = "paper_dark",
         post: str = "earth", post_dark: str = "earth_dark", bays: Sequence[int] = (),
         beam: bool = True, eave_shadow: bool = True) -> None:
    """Hanji wall on an earth timber frame: eave shadow (ink_dark + shade) on the top two rows,
    a beam, 2px posts at both ends and at every `bays` offset, right / bottom shade."""
    c.rect(x, y, w, h, paper)
    c.vline(x + w - 1, y, y + h - 1, shade)
    c.vline(x + w - 2, y + h // 2, y + h - 1, shade)
    c.hline(x, x + w - 1, y + h - 1, shade)
    if eave_shadow:
        c.hline(x, x + w - 1, y, "ink_dark")
        c.hline(x, x + w - 1, y + 1, shade)
    y0 = y + (2 if eave_shadow else 0)
    if beam:
        c.hline(x, x + w - 1, y0, post)
        c.hline(x, x + w - 1, y0 + 1, post_dark)
        y0 += 2
    for px in [x, x + w - 2] + [x + b for b in bays]:
        c.vline(px, y0 - (2 if beam else 0), y + h - 1, post)
        c.vline(px + 1, y0 - (2 if beam else 0), y + h - 1, post_dark)


def plinth(c: Canvas, x: int, y: int, w: int, rows: int = 2, light: str = "ink_pale",
           dark: str = "ink_light", mortar: str = "ink") -> None:
    """기단 stone platform under a wall: light top row, darker face with block joints."""
    c.rect(x, y, w, rows, dark)
    c.hline(x, x + w - 1, y, light)
    for jx in range(x + 5, x + w - 1, 7):
        c.set(jx, y + rows - 1, mortar)
    c.set(x + w - 1, y + rows - 1, mortar)


def door(c: Canvas, x: int, y: int, w: int, h: int, frame: str = "earth_dark", inside: str = "ink_dark",
         lintel: str = "earth", double: bool = False) -> None:
    """Dark doorway: 1px frame, ink_black shadow under the lintel, ink threshold."""
    c.rect(x, y, w, h, frame)
    c.rect(x + 1, y + 1, w - 2, h - 2, inside)
    c.hline(x, x + w - 1, y, lintel)
    c.hline(x + 1, x + w - 2, y + 1, "ink_black")
    c.hline(x + 1, x + w - 2, y + h - 1, "ink")
    if double:
        c.vline(x + w // 2, y + 1, y + h - 2, "ink_black")


def red_door(c: Canvas, x: int, y: int, w: int, h: int) -> None:
    """Closed vermilion double door (shrine / sect): vermilion leaves, vermilion_dark split and
    rails, gold studs, earth_dark frame."""
    c.rect(x, y, w, h, "earth_dark")
    c.rect(x + 1, y + 1, w - 2, h - 2, "vermilion")
    c.vline(x + w // 2, y + 1, y + h - 2, "vermilion_dark")
    c.vline(x + w // 2 - 1, y + 1, y + h - 2, "vermilion_dark")
    c.hline(x + 1, x + w - 2, y + 1, "vermilion_light")
    c.hline(x + 1, x + w - 2, y + h // 2, "vermilion_dark")
    c.set(x + w // 2 - 2, y + h // 2 - 1, "gold")
    c.set(x + w // 2 + 1, y + h // 2 - 1, "gold")
    c.hline(x + 1, x + w - 2, y + h - 1, "ink")


def window(c: Canvas, x: int, y: int, w: int, h: int, frame: str = "earth", pane: str = "paper_light",
           lattice: str = "ink", barred: bool = False) -> None:
    """Lattice window (창살): frame, pale hanji panes, ink lattice cross."""
    c.rect(x, y, w, h, frame)
    c.rect(x + 1, y + 1, w - 2, h - 2, pane)
    if barred:
        for bx in range(x + 2, x + w - 1, 2):
            c.vline(bx, y + 1, y + h - 2, lattice)
        return
    cx = x + w // 2
    cy = y + h // 2
    c.vline(cx, y + 1, y + h - 2, lattice)
    c.hline(x + 1, x + w - 2, cy, lattice)
    c.set(x + w - 2, y + h - 2, frame)


def lantern(c: Canvas, x: int, y: int, cord: int = 2) -> None:
    """Hanging red paper lantern 6x8 (top-left x, y of the cord)."""
    paste(c, f"""
..k...
..k...
.ggg..
VVVVVv
VVVVVv
uVVVVv
.ggg..
..g...
""".replace("..k...\n..k...\n", "..k...\n" * cord), x, y)


def banner_jiu(c: Canvas, x: int, y: int) -> None:
    """Vertical 酒 banner (7 wide x 15 tall) hanging under a pole arm: vermilion cloth with a
    paper_light 酒-like glyph (a drop-shaped 氵 and a boxed 酉)."""
    paste(c, """
EEEEEEE
.vVVVVv
.vVWVVv
.vVVWVv
.vWVVVv
.vVVVVv
.vWWWWv
.vWVWVv
.vWWWWv
.vWVWVv
.vWWWWv
.vVVVVv
.vVVVVv
.uVuVuv
""", x, y)


# ------------------------------------------------------------------------------------------
# Buildings
# ------------------------------------------------------------------------------------------
def house_tile_a() -> Canvas:
    c = Canvas(48, 48)
    c.blit(roof_tiled(46, 23, 10), 1, 1)
    wall(c, 4, 24, 40, 20, bays=())
    window(c, 8, 30, 7, 6)
    window(c, 33, 30, 7, 6)
    door(c, 20, 33, 8, 11)
    plinth(c, 3, 44, 42, 3)
    return c


def house_tile_b() -> Canvas:
    c = Canvas(48, 48)
    c.blit(roof_tiled(46, 23, 6), 1, 1)
    wall(c, 4, 24, 40, 20, paper="paper", shade="paper_dark", bays=(13,))
    window(c, 8, 30, 7, 6)
    window(c, 20, 30, 7, 6)
    door(c, 32, 33, 8, 11)
    # 쪽마루 wooden porch strip along the front
    c.rect(5, 41, 26, 3, "earth_light")
    c.hline(5, 30, 43, "earth")
    c.hline(5, 30, 41, "sand")
    plinth(c, 3, 44, 42, 3)
    # stone 굴뚝 chimney rising beside the right slope
    paste(c, """
PPPI
PIIi
.PIi
.PIi
.PIi
.PIi
.PIi
""", 39, 3)
    return c


def house_thatch_a() -> Canvas:
    c = Canvas(48, 48)
    c.blit(roof_thatch(46, 22, "a"), 1, 1)
    wall(c, 4, 23, 40, 21, bays=())
    window(c, 9, 30, 7, 6)
    door(c, 21, 33, 8, 11)
    window(c, 32, 30, 7, 6)
    plinth(c, 3, 44, 42, 3)
    return c


def house_thatch_b() -> Canvas:
    c = Canvas(48, 48)
    c.blit(roof_thatch(46, 24, "b"), 1, 1)
    # mud (흙벽) wall: sand with paper_dark shade and earth frame
    wall(c, 4, 25, 40, 19, paper="sand", shade="paper_dark", bays=(20,))
    door(c, 8, 33, 8, 11)
    window(c, 30, 30, 7, 6, pane="paper")
    # firewood stack under the right window
    paste(c, """
EeEeEeE
eEeEeEe
EeEeEeE
""", 29, 40)
    plinth(c, 3, 44, 42, 3)
    return c


def house_large() -> Canvas:
    c = Canvas(64, 48)
    c.blit(roof_tiled(62, 23, 12), 1, 1)
    wall(c, 4, 24, 56, 20, bays=(18, 36))
    window(c, 8, 30, 7, 6)
    window(c, 23, 30, 7, 6)
    door(c, 38, 33, 10, 11, double=True)
    window(c, 50, 30, 7, 6)
    plinth(c, 3, 44, 58, 3)
    return c


def house_large_thatch() -> Canvas:
    c = Canvas(64, 48)
    c.blit(roof_thatch(62, 23, "large"), 1, 1)
    wall(c, 4, 24, 56, 20, bays=(18, 36))
    window(c, 8, 30, 7, 6)
    door(c, 23, 33, 8, 11)
    window(c, 42, 30, 7, 6)
    window(c, 51, 30, 7, 6)
    plinth(c, 3, 44, 58, 3)
    return c


def inn() -> Canvas:
    """객잔 5x4: two storeys, balcony rail, 酒 banner on a pole arm, two red lanterns."""
    c = Canvas(80, 64)
    c.blit(roof_tiled(78, 22, 14), 1, 1)
    # upper floor
    wall(c, 4, 23, 72, 16, bays=(24, 48))
    for wx in (10, 30, 50):
        window(c, wx, 29, 9, 7)
    # balcony rail
    c.rect(5, 36, 70, 3, "earth_light")
    c.hline(5, 74, 36, "sand")
    for bx in range(7, 74, 4):
        c.vline(bx, 37, 38, "earth_dark")
    c.hline(5, 74, 39, "earth_dark")
    # lower floor (no eave shadow: the balcony casts it)
    wall(c, 4, 40, 72, 20, bays=(24, 48), eave_shadow=False, beam=False)
    c.hline(4, 75, 40, "ink_dark")
    c.hline(4, 75, 41, "paper_dark")
    door(c, 34, 48, 12, 12, double=True)
    window(c, 12, 46, 9, 7)
    window(c, 58, 46, 9, 7)
    lantern(c, 26, 40, cord=2)
    lantern(c, 48, 40, cord=2)
    plinth(c, 3, 60, 74, 3)
    # banner pole from the upper-left eave
    c.vline(1, 20, 23, "earth_dark")
    banner_jiu(c, 1, 23)
    return c


def inn_small() -> Canvas:
    c = Canvas(48, 48)
    c.blit(roof_tiled(46, 22, 10), 1, 1)
    wall(c, 4, 23, 40, 21, bays=())
    door(c, 26, 33, 9, 11, double=True)
    window(c, 8, 30, 7, 6)
    lantern(c, 18, 25, cord=2)
    lantern(c, 37, 25, cord=2)
    plinth(c, 3, 44, 42, 3)
    c.vline(1, 20, 24, "earth_dark")
    banner_jiu(c, 1, 24)
    return c


def sect_gate() -> Canvas:
    """청운검문 paifang 4x3: two jade_dark posts, double beam, small tiled roof, paper board."""
    c = Canvas(64, 48)
    c.blit(roof_tiled(52, 11, 6), 6, 1)
    # upper beam
    c.rect(8, 12, 48, 3, "jade_dark")
    c.hline(8, 55, 12, "jade")
    # name board
    paste(c, """
AAAAAAAAAAAA
AWiWWiWWiWWA
AWWiWiWiWiWA
AWiWWiWWiWWA
AWWWWWWWWWWA
aaaaaaaaaaaa
""", 26, 15)
    c.rect(25, 15, 1, 6, "jade_dark")
    c.rect(38, 15, 1, 6, "jade_dark")
    # lower beam with a jade highlight
    c.rect(8, 21, 48, 3, "jade_dark")
    c.hline(8, 55, 21, "jade")
    # posts
    for px in (10, 50):
        c.rect(px, 12, 4, 33, "jade_dark")
        c.vline(px, 12, 44, "jade")
        c.vline(px + 3, 12, 44, "bronze_navy")
        c.rect(px - 1, 43, 6, 3, "ink_light")
        c.hline(px - 1, px + 4, 43, "ink_pale")
    return c


def sect_gate_small() -> Canvas:
    c = Canvas(32, 32)
    c.blit(roof_tiled(28, 9, 4), 2, 1)
    c.rect(4, 10, 24, 2, "jade_dark")
    c.hline(4, 27, 10, "jade")
    paste(c, """
AAAAAAAA
AWiWiWiA
AWiWiWiA
aaaaaaaa
""", 12, 12)
    c.rect(4, 16, 24, 2, "jade_dark")
    c.hline(4, 27, 16, "jade")
    for px in (5, 24):
        c.rect(px, 10, 3, 19, "jade_dark")
        c.vline(px, 10, 28, "jade")
        c.rect(px - 1, 28, 5, 3, "ink_light")
        c.hline(px - 1, px + 3, 28, "ink_pale")
    return c


def sect_hall() -> Canvas:
    """청운검문 main hall 5x4: wide tiled roof with gold finials, jade_dark beam and columns,
    paper walls, a jade sign board over the double door, stone 기단 with steps."""
    c = Canvas(80, 64)
    c.blit(roof_tiled(78, 26, 16, finial="gold"), 1, 1)
    wall(c, 4, 27, 72, 30, post="jade_dark", post_dark="bronze_navy", bays=(14, 28, 42, 56))
    c.hline(4, 75, 29, "jade_dark")
    c.hline(4, 75, 30, "jade")
    # sign board
    paste(c, """
jjjjjjjjjjjjjj
jAWiWWiWWiWWAj
jAWWiWiWiWiWAj
jAWiWWiWWiWWAj
jjjjjjjjjjjjjj
""", 33, 32)
    door(c, 34, 44, 12, 13, lintel="jade_dark", double=True)
    for wx in (8, 20, 50, 62):
        window(c, wx, 36, 9, 8)
    plinth(c, 3, 57, 74, 3)
    c.hline(3, 76, 60, "ink")
    # steps
    c.rect(32, 58, 16, 4, "ink_pale")
    c.hline(32, 47, 59, "ink_light")
    c.hline(32, 47, 61, "ink")
    c.vline(32, 58, 61, "ink_light")
    return c


def sect_hall_small() -> Canvas:
    c = Canvas(64, 48)
    c.blit(roof_tiled(62, 21, 12, finial="gold"), 1, 1)
    wall(c, 4, 22, 56, 22, post="jade_dark", post_dark="bronze_navy", bays=(18, 36))
    c.hline(4, 59, 24, "jade_dark")
    c.hline(4, 59, 25, "jade")
    paste(c, """
jjjjjjjjjj
jAWiWWiWAj
jAWWiWiWAj
jjjjjjjjjj
""", 27, 27)
    door(c, 27, 33, 10, 11, lintel="jade_dark", double=True)
    window(c, 8, 30, 8, 7)
    window(c, 48, 30, 8, 7)
    plinth(c, 3, 44, 58, 3)
    return c


def warehouse() -> Canvas:
    """창고 4x3: plain, low tiled roof, dark plank walls, barred double door, slit windows."""
    c = Canvas(64, 48)
    c.blit(roof_tiled(62, 19, 8, light="ink_light"), 1, 1)
    # plank wall
    c.rect(4, 20, 56, 24, "earth")
    c.hline(4, 59, 20, "ink_dark")
    c.hline(4, 59, 21, "earth_dark")
    for py in range(24, 44, 4):
        c.hline(4, 59, py, "earth_dark")
        c.hline(4, 59, py + 1, "earth_light")
    c.vline(58, 22, 43, "earth_dark")
    c.vline(59, 20, 43, "earth_dark")
    for px in (4, 30):
        c.vline(px, 22, 43, "earth_light")
        c.vline(px + 1, 22, 43, "earth_dark")
    # barred door
    c.rect(36, 30, 14, 14, "earth_dark")
    c.rect(37, 31, 12, 12, "ink_dark")
    c.hline(37, 48, 34, "earth_light")
    c.hline(37, 48, 38, "earth_light")
    c.hline(37, 48, 35, "earth_dark")
    c.hline(37, 48, 39, "earth_dark")
    c.vline(43, 31, 42, "earth_dark")
    c.set(40, 36, "ink")
    c.set(46, 36, "ink")
    # slit windows
    window(c, 10, 28, 6, 5, pane="ink_dark", barred=True)
    window(c, 20, 28, 6, 5, pane="ink_dark", barred=True)
    plinth(c, 3, 44, 58, 3)
    return c


def shrine() -> Canvas:
    """사당 3x3: small tiled roof, paper_dark walls, vermilion double door, stone plinth."""
    c = Canvas(48, 48)
    c.blit(roof_tiled(46, 20, 10, finial="gold"), 1, 1)
    wall(c, 6, 21, 36, 22, paper="paper_dark", shade="ink_pale", bays=())
    red_door(c, 19, 29, 10, 14)
    window(c, 9, 28, 6, 6, pane="paper_dark")
    window(c, 33, 28, 6, 6, pane="paper_dark")
    plinth(c, 4, 43, 40, 4)
    c.hline(4, 43, 45, "ink")
    # incense burner on the plinth
    paste(c, """
.ii.
ikki
.ii.
""", 12, 42)
    return c


def temple() -> Canvas:
    """절 4x3: tiled roof with gold finials, vermilion columns (단청), a bronze bell under the
    left eave, dark door with a jade transom."""
    c = Canvas(64, 48)
    c.blit(roof_tiled(62, 22, 12, finial="gold"), 1, 1)
    wall(c, 4, 23, 56, 21, post="vermilion", post_dark="vermilion_dark", bays=(18, 36))
    c.hline(4, 59, 25, "vermilion")
    c.hline(4, 59, 26, "vermilion_dark")
    door(c, 25, 33, 12, 11, lintel="vermilion_dark", double=True)
    c.rect(26, 30, 10, 3, "jade_dark")
    c.hline(27, 34, 31, "jade")
    window(c, 13, 30, 8, 7)
    window(c, 46, 30, 8, 7)
    # bell hanging from the eave on the left (gold with a dark rope)
    paste(c, """
..kk..
..kk..
.gggg.
gGgggg
gGgggg
gggggg
gggggg
.gggg.
..gg..
""", 6, 23)
    plinth(c, 3, 44, 58, 3)
    return c


def beam(c: Canvas, x0: int, y0: int, x1: int, y1: int, dark: str = "ink_dark", core: str = "ink_black") -> None:
    """A charred 2px beam: a dark line with a black line beside it."""
    c.line(x0, y0, x1, y1, dark)
    c.line(x0 + 1, y0, x1 + 1, y1, core)


def ash_mound(c: Canvas, cx: int, cy: int, rx: int, ry: int) -> None:
    """A heap of ash: ink_pale dome with an ink_light base and a few ink specks."""
    c.ellipse(cx, cy, rx, ry, "ink_light")
    c.ellipse(cx - 1, cy - 1, max(1, rx - 1), max(1, ry - 1), "ink_pale")
    c.set(cx + rx // 2, cy, "ink")


def ruin(seed: str, variant: int) -> Canvas:
    """Burnt house 3x3: a charred floor slab, standing wall stub with soot, thick collapsed
    beams, ash mounds and a few embers (백로진의 밤)."""
    rng = Rng(f"ruin/{seed}")
    c = Canvas(48, 48)
    # charred floor slab (what is left of the 기단 and the floor)
    c.rect(4, 36, 40, 10, "ink_dark")
    c.hline(4, 43, 36, "ink")
    c.rect(3, 44, 42, 3, "ink")
    c.hline(3, 44, 44, "ink_light")
    for _ in range(18):
        x = rng.randint(5, 42)
        y = rng.randint(37, 43)
        c.set(x, y, "ink")
    if variant == 0:
        # left wall stub with a burnt window, soot licking up from it, ragged burnt top
        c.rect(5, 15, 16, 22, "paper_dark")
        c.vline(5, 15, 36, "earth_dark")
        c.vline(6, 15, 36, "earth")
        c.vline(20, 15, 36, "ink_dark")
        c.vline(19, 15, 36, "ink")
        for x, top in ((7, 15), (8, 13), (9, 14), (10, 12), (11, 14), (12, 13), (13, 15), (14, 14),
                       (15, 12), (16, 13), (17, 15), (18, 14)):
            c.vline(x, top, 16, "ink_dark")
            c.set(x, top, "ink_black")
        c.rect(9, 24, 6, 7, "ink_black")
        c.rect(9, 31, 6, 1, "ink_dark")
        for x in (8, 10, 12, 14, 16):          # soot streaks above the window
            c.vline(x, 17 + (x % 3), 23, "ink_dark" if x % 4 == 0 else "ink")
        c.hline(7, 17, 34, "ink")
        # collapsed roof beams leaning on the stub, one post still standing on the right
        beam(c, 21, 16, 40, 38)
        beam(c, 44, 18, 30, 40)
        beam(c, 24, 26, 42, 30)
        c.vline(42, 14, 43, "ink_dark")
        c.vline(43, 14, 43, "ink_black")
        c.set(42, 13, "ink")
        # remains of roof tiles on the beams
        c.hline(28, 33, 27, "ink_light")
        c.hline(29, 32, 28, "ink")
        ash_mound(c, 30, 41, 6, 3)
        ash_mound(c, 12, 42, 4, 2)
        ash_mound(c, 39, 43, 3, 2)
        embers = [(26, 39), (36, 41), (14, 41)]
    else:
        # roof plane collapsed onto two charred posts, hearth and a broken jar
        c.vline(8, 12, 43, "ink_dark")
        c.vline(9, 12, 43, "ink_black")
        c.vline(38, 20, 43, "ink_dark")
        c.vline(39, 20, 43, "ink_black")
        # roof plane: a slab of dark tiles sagging from the left post to the ground on the right
        for i in range(8):
            c.line(9 + i, 13 + i * 2, 44, 23 + i * 2, "ink_dark" if i % 2 else "ink")
        c.line(9, 13, 44, 23, "ink_black")
        c.line(9, 12, 44, 22, "ink_dark")
        c.line(16, 28, 44, 37, "ink_black")
        for x in range(12, 42, 5):              # tile ridges on the fallen plane
            y = 15 + (x - 9) * 10 // 35
            c.vline(x, y, y + 11, "ink_light")
        beam(c, 2, 30, 18, 44)
        beam(c, 18, 22, 24, 43)
        # hearth stones
        c.rect(26, 38, 11, 6, "ink_light")
        c.hline(27, 36, 38, "ink_pale")
        c.set(30, 41, "ink")
        c.set(34, 40, "ink")
        c.vline(36, 38, 43, "ink")
        ash_mound(c, 13, 42, 5, 2)
        ash_mound(c, 41, 42, 3, 2)
        ash_mound(c, 22, 43, 3, 1)
        embers = [(29, 41), (12, 40), (40, 40)]
    for ex, ey in embers:
        c.set(ex, ey, "vermilion_dark")
        c.set(ex + 1, ey, "vermilion")
    return c


def heuksa_den() -> Canvas:
    """흑사방 hideout 3x3: dark (ink_dark) tiled roof, dark plank walls, narrow barred window,
    bronze_navy banner with the vermilion snake beside the door."""
    c = Canvas(48, 48)
    c.blit(roof_tiled(46, 22, 8, body="ink", groove="ink_dark", light="ink_light", ridge="ink_black"), 1, 1)
    c.rect(4, 23, 40, 21, "earth_dark")
    c.hline(4, 43, 23, "ink_black")
    c.hline(4, 43, 24, "ink_dark")
    for py in range(27, 44, 4):
        c.hline(4, 43, py, "ink_dark")
        c.hline(4, 43, py + 1, "earth")
    c.vline(4, 25, 43, "earth")
    c.vline(43, 23, 43, "ink_dark")
    c.vline(42, 25, 43, "ink_dark")
    door(c, 26, 33, 9, 11, frame="ink_dark", inside="ink_black", lintel="ink")
    window(c, 36, 29, 5, 6, frame="ink_dark", pane="ink", barred=True)
    # hanging banner: bronze_navy, vermilion snake
    paste(c, """
EEEEEEE
.NNNNNN
.NnNNNn
.NNvvNn
.NNNNvn
.NNvvNn
.NvNNNn
.NNvvNn
.NNNNvn
.NNNvNn
.NNNNNn
.uNuNun
""", 10, 25)
    plinth(c, 3, 44, 42, 3, light="ink_light", dark="ink")
    return c


def stall(seed: str, stripe: str, stripe_dark: str, cloth: str, goods: str) -> Canvas:
    """Market stall 2x2: striped cloth awning with a scalloped edge, two posts, a table of goods."""
    c = Canvas(32, 32)
    # awning
    for y in range(1, 9):
        ins = 0 if y > 1 else 1
        c.hline(2 + ins, 29 - ins, y, cloth)
    for x in range(2, 30):
        if (x // 3) % 2 == 0:
            col = stripe
            c.vline(x, 2, 8, col)
            c.set(x, 2, stripe_dark if x % 3 == 2 else stripe)
    c.hline(2, 29, 8, stripe_dark)
    for x in range(2, 30):
        if (x - 2) % 4 == 3:
            c.set(x, 9, None)
        else:
            c.set(x, 9, stripe if (x // 3) % 2 == 0 else cloth)
    c.hline(3, 28, 1, cloth)
    # posts
    for px in (3, 27):
        c.vline(px, 10, 27, "earth")
        c.vline(px + 1, 10, 27, "earth_dark")
    # table
    c.rect(4, 20, 24, 3, "earth_light")
    c.hline(4, 27, 20, "sand")
    c.hline(4, 27, 22, "earth")
    c.rect(4, 23, 24, 6, "earth")
    c.hline(4, 27, 28, "earth_dark")
    c.vline(27, 23, 28, "earth_dark")
    for bx in range(7, 27, 6):
        c.vline(bx, 23, 27, "earth_dark")
    paste(c, goods, 5, 13)
    return c


def stall_a() -> Canvas:
    goods = """
......................
.LMM...VVV.....ggg....
LMMMM.VuVV..sGGGgg....
.DMM..VVuV.sssGgg.....
......................
.PPP.WWWWW..aaa.aaaa..
PiiiPWaWaW.aEEa.aEEEa.
.PPPPWWWWW..aaa.aaaa..
"""
    return stall("a", "vermilion", "vermilion_dark", "paper_light", goods)


def stall_b() -> Canvas:
    goods = """
......................
.qqq..JJJJ...AAAA.....
qqqqq.jJJj..AWWAA.....
.qqq..JJJJ..AAAA......
......................
.kkk..eee..PPPP.gg....
kiiik.EeE.PiiiP.Gg....
.kkk..eee.PPPPP.gg....
"""
    return stall("b", "navy", "bronze_navy", "paper", goods)


def pavilion() -> Canvas:
    """정자 3x3: open pavilion -- tiled roof on four earth posts, a low rail, raised plank floor."""
    c = Canvas(48, 48)
    c.blit(roof_tiled(46, 20, 10, finial="gold"), 1, 1)
    c.hline(4, 43, 21, "ink_dark")
    # back posts and rail are seen through the open front
    for px in (6, 39):
        c.vline(px, 22, 40, "earth")
        c.vline(px + 1, 22, 40, "earth_dark")
        c.vline(px + 1, 22, 24, "ink_dark")
    # back rail
    c.rect(8, 30, 31, 2, "earth_light")
    c.hline(8, 38, 31, "earth")
    # floor platform
    c.rect(4, 38, 40, 6, "earth_light")
    c.hline(4, 43, 38, "sand")
    for py in (40, 42):
        c.hline(4, 43, py, "earth")
    c.vline(43, 38, 43, "earth")
    c.hline(4, 43, 43, "earth_dark")
    # front posts
    for px in (5, 40):
        c.vline(px, 22, 43, "earth")
        c.vline(px + 1, 22, 43, "earth_dark")
    # front rail with a gap in the middle (entrance)
    for rx0, rx1 in ((7, 18), (29, 39)):
        c.rect(rx0, 33, rx1 - rx0 + 1, 2, "earth_light")
        c.hline(rx0, rx1, 34, "earth")
        for bx in range(rx0 + 1, rx1, 3):
            c.vline(bx, 35, 37, "earth_dark")
    plinth(c, 3, 44, 42, 3)
    return c


def bell_tower() -> Canvas:
    """종루 2x3: tiled roof on four posts over a bronze bell, stone base."""
    c = Canvas(32, 48)
    c.blit(roof_tiled(30, 14, 6, finial="gold"), 1, 1)
    c.hline(3, 28, 15, "ink_dark")
    for px in (4, 26):
        c.vline(px, 16, 42, "earth")
        c.vline(px + 1, 16, 42, "earth_dark")
    # crossbeam and bell
    c.rect(4, 17, 24, 2, "earth")
    c.hline(4, 27, 18, "earth_dark")
    paste(c, """
....kk....
....kk....
...gggg...
..gGgggg..
..gGgggg..
..gGgggg..
..gggggg..
.gggggggg.
.gggggggg.
...gggg...
""", 11, 19)
    c.rect(2, 42, 28, 2, "ink_pale")
    c.rect(2, 43, 28, 3, "ink_light")
    c.hline(2, 29, 42, "ink_pale")
    c.hline(2, 29, 45, "ink")
    return c


def wall_gate() -> Canvas:
    """Gateway in a stone wall 2x2 (decoration: a single TileDef cannot have a walkable centre)."""
    c = Canvas(32, 32)
    c.blit(roof_tiled(30, 9, 5), 1, 1)
    for px in (2, 23):
        c.rect(px, 10, 7, 20, "ink_light")
        c.hline(px, px + 6, 10, "ink_pale")
        c.vline(px + 6, 10, 29, "ink")
        for jy in range(14, 29, 4):
            c.hline(px, px + 6, jy, "ink")
        c.set(px + 3, 12, "ink")
        c.set(px + 3, 20, "ink")
        c.hline(px, px + 6, 29, "ink_dark")
    # threshold
    c.rect(9, 27, 14, 3, "ink_pale")
    c.hline(9, 22, 29, "ink_light")
    return c


# ------------------------------------------------------------------------------------------
# Small props (ASCII patterns)
# ------------------------------------------------------------------------------------------
def well() -> Canvas:
    """Stone well with a wooden frame, crossbar and a hanging bucket (3/4 view)."""
    return pat("""
................
...EeEEEEEEeE...
...EeE..k..eE...
...EeE..k..eE...
...EeE.sss.eE...
...EeE.ses.eE...
..PPPPPPPPPPPP..
.PIxxxxxxxxxxIP.
.PIxxwwwwwwxxIP.
.PIxxwcwwwwxxIP.
.PIIxxxxxxxxIIP.
.PPIIIIIIIIIIPP.
.PIPIIPIIPIIPii.
.iPIIPIIPIIPIii.
..iiiiiiiiiiii..
................
""", 16, 16)


def stone_lantern() -> Canvas:
    return pat("""
................
.......P........
......PIi.......
.......I........
......PIi.......
.....PPIii......
....PPPIiii.....
...PPPPIiiii....
...iiiiiiiiii...
.....PGGGi......
.....PGGGi......
.....PGkGi......
.....PGGGi......
.....iiiii......
.....PPIii......
......PIi.......
......PIi.......
......PIi.......
......PIi.......
......PIi.......
......PIi.......
......PIi.......
......PIi.......
......PIi.......
......PIi.......
......PIi.......
.....PPIii......
....PPPIiii.....
....PIIIIii.....
...PPPPPIiiii...
...iiiiiiiiii...
................
""", 16, 32)


def lantern_post() -> Canvas:
    return pat("""
................
....EEEEEE......
....E....k......
...EEE...k......
...EeE..ggg.....
...EeE.VVVVVv...
...EeE.VVVVVv...
...EeE.uVVVVv...
...EeE.uVVVVv...
...EeE..ggg.....
...EeE...g......
...EeE...v......
...EeE..........
...EeE..........
...EeE..........
...EeE..........
...EeE..........
...EeE..........
...EeE..........
...EeE..........
...EeE..........
...EeE..........
...EeE..........
...EeE..........
...EeE..........
...EeE..........
...EeE..........
...EeE..........
..IEeEI.........
..IPIII.........
..iiiii.........
................
""", 16, 32)


def fence_h() -> Canvas:
    return pat("""
................
................
................
................
................
......KKKK......
......KEeK......
KKKKKKKEeKKKKKKK
KFFFFFKEeKFFFFFK
KeeeeeKEeKeeeeeK
KKKKKKKEeKKKKKKK
......KEeK......
KKKKKKKEeKKKKKKK
KFFFFFKEeKFFFFFK
KeeeeeKEeKeeeeeK
KKKKKKKEeKKKKKKK
""", 16, 16)


def fence_v() -> Canvas:
    return pat("""
....KKKKKKKK....
....KFEEeeEK....
....KEEEeeEK....
....KEEEeeEK....
....KKKFeKKK....
......KFeK......
......KFeK......
......KFeK......
....KKKFeKKK....
....KFEEeeEK....
....KEEEeeEK....
....KEEEeeEK....
....KKKFeKKK....
......KFeK......
......KFeK......
......KFeK......
""", 16, 16)


def fence_post() -> Canvas:
    return pat("""
................
................
................
................
................
......KKKK......
......KEeK......
......KEeK......
......KEeK......
......KEeK......
......KEeK......
......KEeK......
......KEeK......
......KEeK......
......KEeK......
......KKKK......
""", 16, 16)


def fence_end_l() -> Canvas:
    return pat("""
................
................
................
................
................
....KKKK........
....KEeK........
....KEeKKKKKKKKK
....KEeKFFFFFFFK
....KEeKeeeeeeeK
....KEeKKKKKKKKK
....KEeK........
....KEeKKKKKKKKK
....KEeKFFFFFFFK
....KEeKeeeeeeeK
....KKKKKKKKKKKK
""", 16, 16)


def wall_h() -> Canvas:
    return pat("""
................
................
KKKKKKKKKKKKKKKK
kkkkkkkkkkkkkkkk
IPIIIPIIIPIIIPII
IIiIIIiIIIiIIIiI
iiiiiiiiiiiiiiii
PPPPPPPPPPPPPPPP
PPPiPPPPPPPiPPPP
iiiiiiiiiiiiiiii
PPPPPPiPPPPPPPPP
PPPPPPiPPPPPPPPP
iiiiIiiiiiiiIiii
PPPPPPPPPiPPPPPP
PPPPPPPPPiPPPPPP
KKKKKKKKKKKKKKKK
""", 16, 16)


def wall_v() -> Canvas:
    return pat("""
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIiK...
""", 16, 16)


def wall_corner_nw() -> Canvas:
    return pat("""
................
................
...KKKKKKKKKKKKK
...KkkkkkkkkkkkK
...KPIIkkIIIPIII
...KPIIkkIIiIIiI
...KPIIkkiiiiiii
...KPIIkkIIKPPPP
...KPIIkkIIKPPiP
...KPIIkkIIKiiii
...KPIIkkIIKPPPP
...KPIIkkIIKPPPP
...KPIIkkIIKiIii
...KPIIkkIIKPPPP
...KPIIkkIIKPPPP
...KPIIkkIIKKKKK
""", 16, 16)


def wall_corner_sw() -> Canvas:
    return pat("""
...KPIIkkIIiK...
...KPIIkkIIiK...
...KPIIkkIIkKKKK
...KPIIkkIIkkkkk
...KPIIkkIIIPIII
...KPIIkkIIiIIiI
...Kiiiiiiiiiiii
...KPPPPPPPPPPPP
...KPPPiPPPPPPiP
...Kiiiiiiiiiiii
...KPPPPPPiPPPPP
...KPPPPPPiPPPPP
...KiiiiIiiiiiii
...KPPPPPPPPPiPP
...KPPPPPPPPPiPP
...KKKKKKKKKKKKK
""", 16, 16)


def sign() -> Canvas:
    return pat("""
................
..EEEEEEEEEEE...
..EaAAAAAAAaE...
..EAiAAiAAiAE...
..EAAiAiAiAAE...
..EAiAAiAAiAE...
..EaaaaaaaaaE...
..EEEEEEEEEEE...
......EeE.......
......EeE.......
......EeE.......
......EeE.......
......EeE.......
......EeE.......
.....IEeEI......
.....iiiii......
""", 16, 16)


def barrel() -> Canvas:
    return pat("""
................
.....ssssss.....
....FeeeeeeE....
...FeFeeeeeEE...
...kkkkkkkkkk...
...FeFeeeeeEE...
...FeFeeeeeEE...
...FeFeeeeeEE...
...FeFeeeeeEE...
...kkkkkkkkkk...
...FeFeeeeeEE...
...FeFeeeeeEE...
....FeeeeeEE....
....kkkkkkkk....
................
................
""", 16, 16)


def crate() -> Canvas:
    return pat("""
................
................
...FFFFFFFFFF...
...FssssssssE...
...FsFeeeeeFE...
...FsFeeeeFeE...
...FsFeeeFeeE...
...FsFeeFeeeE...
...FsFeFeeeeE...
...FsFFeeeeeE...
...FsssssssEE...
...EEEEEEEEEE...
................
................
................
................
""", 16, 16)


def jar_a() -> Canvas:
    return pat("""
................
................
.....IIIII......
.....PkkkI......
....kkkkkkkk....
...kkIkkkkkkk...
..kkIIkkkkkkkk..
..kkIkkkkkkkki..
..kkIkkkkkkkki..
..kkIkkkkkkkki..
..kkkkkkkkkkki..
...kkkkkkkkki...
....kkkkkkki....
.....iiiiii.....
................
................
""", 16, 16)


def jar_b() -> Canvas:
    return pat("""
................
................
.....AAAAA......
....AWAAAAa.....
....ssssssss....
....eFeeeeeE....
...eFFeeeeeEE...
..eeFeeeeeeeEE..
..eeFeeeeeeeEE..
..eeFeeeeeeeEE..
..eeeeeeeeeeEE..
...eeeeeeeeEE...
....eeeeeeEE....
.....EEEEEE.....
................
................
""", 16, 16)


def hay() -> Canvas:
    return pat("""
................
................
................
......ssss......
....sssaasss....
...ssasaaasas...
..saaseaaasaas..
..aaaaaaeaaaaa..
.aaaeaaaaaaeaaa.
.aaaaaaeaaaaaea.
.aaeaaaaaaaaaae.
.aeaaaaaeaaeaee.
..eaeaaaaaaaee..
...eeeeeeeeee...
................
................
""", 16, 16)


def cart() -> Canvas:
    return pat("""
................................
................................
................................
................................
................................
................................
................................
................................
...........sssssss..............
..........sassasass.............
.........saaasaaasas............
........aaaeaaaaaaeaa...........
........aaaaaaeaaaaaa...........
.......aaeaaaaaaaaeaaa..........
.......aaaaaaaeaaaaaaa..........
.....FFFFFFFFFFFFFFFFFFFF.......
..EEEEeeeeeeeeeeeeeeeeeeeeE.....
.EeeeeFeeeeeeeeeeeeeeeeeeeE.....
.Ee..EEeeeeeeeeeeeeeeeeeeeE.....
.....EEEEEEEEEEEEEEEEEEEEEE.....
.......EeE..........EeE.........
.......EeE..........EeE.........
......kkkkk........kkkkk........
.....kkIkkkk......kkIkkkk.......
....kkIkkikk.....kkIkkikk.......
....kIkkkkik.....kIkkkkik.......
....kkikkkIk.....kkikkkIk.......
.....kkikkk.......kkikkk........
......kkkkk........kkkkk........
................................
................................
................................
""", 32, 32)


def bench() -> Canvas:
    return pat("""
................
................
................
................
................
................
.FFFFFFFFFFFFF..
.FsssssssssssE..
.FeeeeeeeeeeeE..
.EEEEEEEEEEEEE..
..EeE.....EeE...
..EeE.....EeE...
..EeE.....EeE...
..EEE.....EEE...
................
................
""", 16, 16)


def mat() -> Canvas:
    return pat("""
................
................
................
................
..aaaaaaaaaaaa..
.aAAaAAaAAaAAaa.
.aaaaaaaaaaaaas.
.aAAaAAaAAaAAas.
.aaaaaaaaaaaaas.
.aAAaAAaAAaAAas.
.ssssssssssssss.
................
................
................
................
................
""", 16, 16)


def dock_plank() -> Canvas:
    return pat("""
FFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFF
eeeeeeeeeeeeeeee
EEEEEEEEEEEEEEEE
FFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFF
eeeeeeeeeeeeeeee
EEEEEEEEEEEEEEEE
FFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFF
eeeeeeeeeeeeeeee
EEEEEEEEEEEEEEEE
FFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFF
eeeeeeeeeeeeeeee
EEEEEEEEEEEEEEEE
""", 16, 16)


def dock_end() -> Canvas:
    return pat("""
FFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFF
eeeeeeeeeeeeeeee
EEEEEEEEEEEEEEEE
FFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFF
eeeeeeeeeeeeeeee
EEEEEEEEEEEEEEEE
FFFFFFFFFFFFFFFF
FFFFFFFFFFFFFFFF
eeeeeeeeeeeeeeee
EEEEEEEEEEEEEEEE
KKKKKKKKKKKKKKKK
xkkxxxxxxxxxxkkx
xkkxwwxxxwxxxkkx
xxxxxxxxxxxxxxxx
""", 16, 16)


def dock_post() -> Canvas:
    return pat("""
................
.....IIIi.......
.....Ikki.......
.....Ikki.......
.....Ikki.......
.....Ikki.......
.....ssss.......
.....sIkk.......
.....ssss.......
.....Ikki.......
.....Ikki.......
.....Ikki.......
.....Ikki.......
.....Ikki.......
.....Ikki.......
................
""", 16, 16)


def boat() -> Canvas:
    return pat("""
................................
................................
..........................EeE...
..........................EeE...
..........................EeE...
..........................EeE...
.....FFFFFFFFFFFFFFFFFFFFFFFFFF.
...FFFsssssssssssssssssssssssFF.
.FFeeeeeeeeeeeeeeeeeeeeeeeeeeeF.
..EeeeeeeeeeeeeeeeeeeeeeeeeeeE..
...EEeeeeeeeeeeeeeeeeeeeeeeEE...
.....EEEEEEEEEEEEEEEEEEEEEE.....
................................
................................
................................
................................
""", 32, 16)


def boat_big() -> Canvas:
    return pat("""
................................................
................................................
................................................
................................................
................................................
................................................
................................................
................................................
................................................
................................................
...............ssssssssssssssssss...............
..............saaaaaaaaaaaaaaaaaaa..............
.............aaaaaaeaaaaaeaaaaaaaa..............
.............aeaaaaaaaaaaaaaeaaaaa..............
.............eeeeeeeeeeeeeeeeeeeee..............
.............EkkkkkkkkkkkkkkkkkkkE..............
.............EkkKkkkkkkkkkkkkkKkkE..............
.............EkkkkkkkkkkkkkkkkkkkE..............
.............EEEEEEEEEEEEEEEEEEEEE..............
.......FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF...
....FFFFsssssssssssssssssssssssssssssssssssFFF..
..FFFeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeFF.
.FeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeF.
..EeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeE..
...EEeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeEE...
.....EEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE.....
................................................
................................................
................................................
................................................
................................................
................................................
""", 48, 32)


def banner(body: str, edge: str, mark: str, mark_color: str) -> Canvas:
    """1x2 vertical banner on a pole; `mark` is a 6x7 ASCII block of '.'/'#' for the emblem
    drawn in `mark_color`."""
    c = pat("""
................
...EEEEEEEEEE...
...E............
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeEbbbbbbbbb.
...EeE.bbb.bbb..
...EeE..........
...EeE..........
...EeE..........
...EeE..........
...EeE..........
..IEeEI.........
..IPIII.........
..iiiii.........
""", 16, 32, {"b": body})
    for y in range(3, 23):
        c.set(14, y, edge)
    c.hline(6, 14, 3, edge)
    rows = [r for r in mark.split("\n") if r.strip()]
    for dy, r in enumerate(rows):
        for dx, ch in enumerate(r):
            if ch == "#":
                c.set(8 + dx, 7 + dy, mark_color)
    return c


def banner_sect() -> Canvas:
    # 청운검문 mark: a paper_light jian (blade, cross guard, pommel) point up
    return banner("jade", "jade_dark", """
..#...
..#...
..#...
..#...
.###..
..#...
.#.#..
""", "paper_light")


def banner_heuksa() -> Canvas:
    # 흑사 (black snake) mark: a tiny S-shaped snake in vermilion, head on top, tongue out
    return banner("bronze_navy", "navy", """
.###..
#..##.
....#.
..##..
.#....
#...#.
.###..
""", "vermilion")


def torch() -> Canvas:
    return pat("""
................
......VgV.......
.....VGGGV......
.....VGGGV......
......GGG.......
......vGv.......
.......v........
.....kkkkk......
......EeE.......
......EeE.......
......EeE.......
......EeE.......
......EeE.......
......EeE.......
.....IEeEI......
.....iiiii......
""", 16, 16)


def gate_door() -> Canvas:
    return pat("""
................
................
KKKKKKKKKKKKKKKK
kkkkkkkkkkkkkkkk
IPIIIPIIIPIIIPII
IIiIIIiIIIiIIIiI
iiiiiiiiiiiiiiii
PPPEEEEEEEEEEPPP
PPPEFeeeEeeeEPPP
PiPEFeeeEeeeEPiP
PPPEFeeeEeeeEPPP
PPPEFkeeEeekEPPP
iiPEFeeeEeeeEPii
PPPEFeeeEeeeEPPP
PPPEFeeeEeeeEPPP
PPPEFgeeEeegEPPP
PiPEFeeeEeeeEPiP
PPPEFeeeEeeeEPPP
PPPEFeeeEeeeEPPP
iiPEFkeeEeekEPii
PPPEFeeeEeeeEPPP
PPPEFeeeEeeeEPPP
PPPEFeeeEeeeEPPP
PiPEFeeeEeeeEPiP
PPPEFeeeEeeeEPPP
PPPEFeeeEeeeEPPP
iiPEFkeeEeekEPii
PPPEFeeeEeeeEPPP
PPPEFeeeEeeeEPPP
PPPEEEEEEEEEEPPP
IIIIIIIIIIIIIIII
KKKKKKKKKKKKKKKK
""", 16, 32)


def steps() -> Canvas:
    return pat("""
PPPPPPPPPPPPPPPP
PPPPPPPiPPPPPPPP
IIIIIIIIIIIIIIII
kkkkkkkkkkkkkkkk
PPPPPPPPPPPPPPPP
PPPPiPPPPPPPPPPP
IIIIIIIIIIIIIIII
kkkkkkkkkkkkkkkk
PPPPPPPPPPPPPPPP
PPPPPPPPPPPiPPPP
IIIIIIIIIIIIIIII
kkkkkkkkkkkkkkkk
PPPPPPPPPPPPPPPP
PPPPPPiPPPPPPPPP
IIIIIIIIIIIIIIII
kkkkkkkkkkkkkkkk
""", 16, 16)


def tombstone_a() -> Canvas:
    return pat("""
................
................
.....PPPP.......
....PPPPPI......
....PIPIPI......
....PPIPPI......
....PIPIPI......
....PPPPPI......
....PIPIPI......
....PPPPPI......
....PPPPII......
...iPPPPPIi.....
...iIIIIIIi.....
...iiiiiiii.....
................
................
""", 16, 16)


def tombstone_b() -> Canvas:
    return pat("""
................
................
................
......III.......
.....IPPPI......
....IPPPPPi.....
....IPiPiPi.....
....IPPiPPi.....
....IPiPiPi.....
....MPPPPPi.....
....MMPPPIi.....
...DMMIIIIii....
..DDDMMDDDDi....
...DDDDDDDD.....
................
................
""", 16, 16)


def statue() -> Canvas:
    """Stone sage (석상): topknot, folded sleeves, robe folds, two-step plinth."""
    return pat("""
................
.......PI.......
......PPII......
.....PPPPII.....
.....PPIPII.....
.....PPPPII.....
......PIII......
.....PPPPPI.....
....PPPPPPII....
...PPPPPPPIII...
..PPPPiPPPIIII..
..PPPiPPPiIIII..
..PPiPPPPPiIII..
..PPPPPPPPIIII..
..PPPiiiiiIIII..
...PPPPPPIIII...
...PPPIPPIIII...
...PPPIPPIIII...
...PPIPPPIIII...
...PPIPPPIIII...
...PIIPPPIIII...
...PIIPPIIIIi...
...IIIPPIIIIi...
...IIIIIIIIIi...
..PPPPPPPPPPPP..
..PIIIIIIIIIIi..
..PIIIIIIIIIIi..
..iiiiiiiiiiii..
.PPPPPPPPPPPPPP.
.PIIIIIIIIIIIIi.
.iiiiiiiiiiiiii.
................
""", 16, 32)


def bridge_stone_h() -> Canvas:
    return pat("""
PPPPPPPPPPPPPPPP
IIIiIIIIIIIiIIII
kkkkkkkkkkkkkkkk
PPPPPPPPPPPPPPPP
PPPPiPPPPPPPPPPP
PPPPPPPPPPiPPPPP
PPiPPPPPPPPPPPPP
PPPPPPPPPPPPPPPP
PPPPPPPiPPPPPPPP
PPPPPPPPPPPPPiPP
PPPiPPPPPPPPPPPP
PPPPPPPPPPPPPPPP
PPPPPPPPPPPPPPPP
IIIIIIIIIIIIIIII
IIIiIIIIIIIiIIII
iiiiiiiiiiiiiiii
""", 16, 16)


# ------------------------------------------------------------------------------------------
# Inventory (binding names of §5.2 'town')
# name, builder, cells (w, h), solid, overlay, ground, tags, outline (auto 1px ink_black?)
# ------------------------------------------------------------------------------------------
INVENTORY: List[Tuple[str, Callable[[], Canvas], Tuple[int, int], bool, bool, str, str, bool]] = [
    # 4-cell tall
    ("town_inn", inn, (5, 4), True, False, GROUND, "building,inn,banner,lanterns", True),
    ("town_sect_hall", sect_hall, (5, 4), True, False, GROUND, "building,sect,hall,jade", True),
    # 3-cell tall
    ("town_house_tile_a", house_tile_a, (3, 3), True, False, GROUND, "building,house,tile_roof", True),
    ("town_house_tile_b", house_tile_b, (3, 3), True, False, GROUND, "building,house,tile_roof", True),
    ("town_house_thatch_a", house_thatch_a, (3, 3), True, False, GROUND, "building,house,thatch", True),
    ("town_house_thatch_b", house_thatch_b, (3, 3), True, False, GROUND, "building,house,thatch", True),
    ("town_house_large", house_large, (4, 3), True, False, GROUND, "building,house,tile_roof,large", True),
    ("town_sect_gate", sect_gate, (4, 3), False, False, GROUND, "gate,sect,paifang,walkable", True),
    ("town_warehouse", warehouse, (4, 3), True, False, GROUND, "building,warehouse,barred", True),
    ("town_shrine", shrine, (3, 3), True, False, GROUND, "building,shrine,red_door", True),
    ("town_temple", temple, (4, 3), True, False, GROUND, "building,temple,bell", True),
    ("town_ruin_a", lambda: ruin("a", 0), (3, 3), True, False, GROUND, "ruin,burnt,night", True),
    ("town_ruin_b", lambda: ruin("b", 1), (3, 3), True, False, GROUND, "ruin,burnt,night", True),
    ("town_bell_tower", bell_tower, (2, 3), True, False, GROUND, "building,bell_tower,bell", True),
    ("town_pavilion", pavilion, (3, 3), True, False, GROUND, "building,pavilion,open", True),
    ("town_inn_small", inn_small, (3, 3), True, False, GROUND, "building,inn,banner,gpa_footprint", True),
    ("town_sect_hall_small", sect_hall_small, (4, 3), True, False, GROUND, "building,sect,hall,jade,gpa_footprint", True),
    ("town_heuksa_den", heuksa_den, (3, 3), True, False, GROUND, "building,heuksa,den,snake_banner,gpa_footprint", True),
    ("town_house_large_thatch", house_large_thatch, (4, 3), True, False, GROUND, "building,house,thatch,large,gpa_footprint", True),
    # 2-cell tall
    ("town_stall_a", stall_a, (2, 2), True, False, GROUND, "market,stall,awning,vermilion", True),
    ("town_stall_b", stall_b, (2, 2), True, False, GROUND, "market,stall,awning,navy", True),
    ("town_wall_gate", wall_gate, (2, 2), True, False, GROUND, "wall,gate,decoration,no_walkable_centre", True),
    ("town_cart", cart, (2, 2), True, False, GROUND, "cart,wood,hay", True),
    ("town_boat_big", boat_big, (3, 2), True, False, "ground_water_0", "boat,river,cabin", True),
    ("town_sect_gate_small", sect_gate_small, (2, 2), False, False, "ground_road_0", "gate,sect,paifang,walkable,gpa_footprint", True),
    ("town_stone_lantern", stone_lantern, (1, 2), True, False, GROUND, "lantern,stone", True),
    ("town_lantern_post", lantern_post, (1, 2), True, False, GROUND, "lantern,post,red", True),
    ("town_banner_sect", banner_sect, (1, 2), True, False, GROUND, "banner,sect,jade", True),
    ("town_banner_heuksa", banner_heuksa, (1, 2), True, False, GROUND, "banner,heuksa,snake", True),
    ("town_gate_door", gate_door, (1, 2), True, False, GROUND, "door,gate,closed,wall_join", False),
    ("town_statue", statue, (1, 2), True, False, GROUND, "statue,stone", True),
    # 1-cell tall
    ("town_well", well, (1, 1), True, True, GROUND, "well,stone,water", True),
    ("town_fence_h", fence_h, (1, 1), True, True, GROUND, "fence,wood,join_h", False),
    ("town_fence_v", fence_v, (1, 1), True, True, GROUND, "fence,wood,join_v", False),
    ("town_fence_post", fence_post, (1, 1), True, True, GROUND, "fence,wood,post", False),
    ("town_fence_end_l", fence_end_l, (1, 1), True, True, GROUND, "fence,wood,end", False),
    ("town_fence_end_r", lambda: fence_end_l().flipped_x(), (1, 1), True, True, GROUND, "fence,wood,end", False),
    ("town_wall_h", wall_h, (1, 1), True, True, GROUND, "wall,stone,tile_cap,join_h", False),
    ("town_wall_v", wall_v, (1, 1), True, True, GROUND, "wall,stone,tile_cap,join_v", False),
    ("town_wall_corner_nw", wall_corner_nw, (1, 1), True, True, GROUND, "wall,stone,corner", False),
    ("town_wall_corner_ne", lambda: wall_corner_nw().flipped_x(), (1, 1), True, True, GROUND, "wall,stone,corner", False),
    ("town_wall_corner_sw", wall_corner_sw, (1, 1), True, True, GROUND, "wall,stone,corner", False),
    ("town_wall_corner_se", lambda: wall_corner_sw().flipped_x(), (1, 1), True, True, GROUND, "wall,stone,corner", False),
    ("town_sign", sign, (1, 1), True, True, GROUND, "sign,wood", True),
    ("town_barrel", barrel, (1, 1), True, True, GROUND, "barrel,wood", True),
    ("town_crate", crate, (1, 1), True, True, GROUND, "crate,wood", True),
    ("town_jar_a", jar_a, (1, 1), True, True, GROUND, "jar,pottery,dark", True),
    ("town_jar_b", jar_b, (1, 1), True, True, GROUND, "jar,pottery,cloth_lid", True),
    ("town_hay", hay, (1, 1), True, True, GROUND, "hay,straw", True),
    ("town_bench", bench, (1, 1), True, True, GROUND, "bench,wood", True),
    ("town_mat", mat, (1, 1), False, True, GROUND, "mat,straw,overlay,market", True),
    ("town_dock_plank", dock_plank, (1, 1), False, False, "", "dock,planks,walkable,ground", False),
    ("town_dock_end", dock_end, (1, 1), False, False, "", "dock,planks,walkable,ground,south_end", False),
    ("town_dock_post", dock_post, (1, 1), True, True, "ground_water_0", "dock,post,mooring", True),
    ("town_boat", boat, (2, 1), True, False, "ground_water_0", "boat,river", True),
    ("town_torch", torch, (1, 1), True, True, GROUND, "torch,fire,light", True),
    ("town_steps", steps, (1, 1), False, False, "", "steps,stone,walkable,ground", False),
    ("town_tombstone_a", tombstone_a, (1, 1), True, True, GROUND, "tombstone,stone", True),
    ("town_tombstone_b", tombstone_b, (1, 1), True, True, GROUND, "tombstone,stone,moss", True),
    ("town_bridge_stone_h", bridge_stone_h, (1, 1), False, False, "", "bridge,stone,walkable,ground", False),
]

REQUIRED_NAMES = [
    "town_house_tile_a", "town_house_tile_b", "town_house_thatch_a", "town_house_thatch_b",
    "town_house_large", "town_inn", "town_sect_gate", "town_sect_hall", "town_warehouse",
    "town_shrine", "town_temple", "town_ruin_a", "town_ruin_b", "town_stall_a", "town_stall_b",
    "town_well", "town_stone_lantern", "town_lantern_post", "town_fence_h", "town_fence_v",
    "town_fence_post", "town_fence_end_l", "town_fence_end_r", "town_wall_h", "town_wall_v",
    "town_wall_corner_nw", "town_wall_corner_ne", "town_wall_corner_sw", "town_wall_corner_se",
    "town_wall_gate", "town_sign", "town_barrel", "town_crate", "town_jar_a", "town_jar_b",
    "town_hay", "town_cart", "town_bench", "town_mat", "town_dock_plank", "town_dock_end",
    "town_dock_post", "town_boat", "town_boat_big", "town_banner_sect", "town_banner_heuksa",
    "town_torch", "town_gate_door", "town_steps", "town_tombstone_a", "town_tombstone_b",
    "town_statue", "town_bell_tower", "town_bridge_stone_h", "town_pavilion",
    "town_sect_gate_small", "town_inn_small", "town_sect_hall_small", "town_heuksa_den",
    "town_house_large_thatch",
]


def build_canvas(name: str) -> Canvas:
    for n, builder, (cw, ch), _s, _o, _g, _t, outline in INVENTORY:
        if n == name:
            c = builder()
            if (c.w, c.h) != (cw * CELL, ch * CELL):
                raise ValueError(f"{name}: canvas is {c.w}x{c.h}, expected {cw * CELL}x{ch * CELL}")
            return c.outlined("ink_black") if outline else c
    raise KeyError(name)


def make_sheet() -> Sheet:
    names = [n for n, *_ in INVENTORY]
    missing = [n for n in REQUIRED_NAMES if n not in names]
    extra = [n for n in names if n not in REQUIRED_NAMES]
    if missing or extra:
        raise ValueError(f"inventory mismatch: missing={missing} extra={extra}")
    if len(set(names)) != len(names):
        raise ValueError("duplicate names in INVENTORY")
    sheet = Sheet(SHEET, "tiles", pivot=(0.5, 0.0))
    for name, _b, (cw, ch), solid, overlay, ground, tags, _o in INVENTORY:
        c = build_canvas(name)
        sheet.add(name, c, solid=solid, overlay=overlay, ground=ground, tags=tags)
        collider = "grid" if solid else "none"
        sheet.add_tile(pascal_case(name), name, collider=collider)
    return sheet


# ------------------------------------------------------------------------------------------
# Review preview: props on grass and on road (uses the shipped ground tiles when present)
# ------------------------------------------------------------------------------------------
def _ground_tiles(art_root: Optional[str]) -> Tuple[Canvas, Canvas]:
    grass = Canvas(CELL, CELL, fill="moss")
    road = Canvas(CELL, CELL, fill="earth_light")
    rng = Rng("town-preview-ground")
    for _ in range(14):
        grass.set(rng.randint(0, 15), rng.randint(0, 15), "moss_dark")
    for _ in range(3):
        grass.set(rng.randint(0, 15), rng.randint(0, 15), "moss_light")
    for _ in range(10):
        road.set(rng.randint(0, 15), rng.randint(0, 15), "earth")
    for _ in range(3):
        road.set(rng.randint(0, 15), rng.randint(0, 15), "sand")
    if art_root:
        png = os.path.join(art_root, "Tiles", "ground.png")
        if os.path.isfile(png):
            try:
                g = Sheet.load(png)
                if "ground_grass_0" in g and "ground_road_0" in g:
                    return g.get_canvas("ground_grass_0"), g.get_canvas("ground_road_0")
            except Exception:  # noqa: BLE001 - the review preview must never break the build
                pass
    return grass, road


def on_ground_preview(sheet: Sheet, path: str, art_root: Optional[str], scale: int = 4) -> str:
    grass, road = _ground_tiles(art_root)
    cols = 20
    placements: List[Tuple[str, int, int]] = []
    x = y = 0
    row_h = 0
    for name, _b, (cw, ch), *_ in INVENTORY:
        if x + cw > cols:
            x = 0
            y += row_h + 1
            row_h = 0
        placements.append((name, x, y))
        x += cw + 1
        row_h = max(row_h, ch)
    rows = y + row_h + 1
    world = Canvas(cols * CELL * 2 + CELL, rows * CELL)
    for cy in range(rows):
        for cx in range(cols):
            world.blit(grass, cx * CELL, cy * CELL)
            world.blit(road, (cols + 1 + cx) * CELL, cy * CELL)
    for name, cx, cy in placements:
        e = sheet.get(name)
        world.blit(e.canvas, cx * CELL, cy * CELL)
        world.blit(e.canvas, (cols + 1 + cx) * CELL, cy * CELL)
    big = world.scaled(scale)
    title = Canvas(big.w, 14, fill=(20, 21, 28))
    title.stamp("TOWN PROPS ON GRASS (left) AND ROAD (right) - review only", 4, 2, (255, 214, 120), scale=2)
    out = Canvas(big.w, big.h + title.h, fill=(20, 21, 28))
    out.blit(title, 0, 0)
    out.blit(big, 0, title.h)
    return out.save(path)


def build(art_root: str, preview_dir: str, cellmap_dir: str) -> List[str]:
    sheet = make_sheet()
    tiles_dir = os.path.join(art_root, "Tiles")
    png, js = sheet.save(tiles_dir)
    written = [png, js]
    written.append(sheet.preview(os.path.join(preview_dir, f"{sheet.file_name}_preview.png"),
                                 scale=4, labels=True))
    written.append(on_ground_preview(sheet, os.path.join(preview_dir, f"{sheet.file_name}_on_ground_preview.png"),
                                     art_root))
    cm_png, cm_md = sheet.cellmap(os.path.join(cellmap_dir, f"{sheet.name}_cellmap.png"),
                                  os.path.join(cellmap_dir, f"{sheet.name}.md"))
    written += [cm_png, cm_md]
    return written


if __name__ == "__main__":  # pragma: no cover
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.normpath(os.path.join(here, "..", ".."))
    for p in build(os.path.join(root, "Assets", "InkPixel", "Art"), os.path.join(root, "Docs", "previews"),
                   os.path.join(root, "Docs", "cellmaps")):
        print(p)
    sys.exit(0)
