"""gen_tiles_ground.py -- InkPixel ground tiles + blob autotiles (ASSET_SPEC.md v2 §4, §5.2).

Writes
  <art_root>/Tiles/ground.png     + ground.sprites.json     (kind tiles, 1x1 ground, no outline)
  <art_root>/Tiles/autotiles.png  + autotiles.sprites.json  (kind autotiles, six 47-blob sets)
  <preview_dir>/ground_preview.png, autotiles_preview.png, ground_tiling_preview.png (3x3 seam test),
  tiles_demo.png (24x16 scene assembled from ground + autotiles at 3x)
  <cellmap_dir>/ground_cellmap.png, ground.md, autotiles_cellmap.png, autotiles.md

Technique: every ground texture is a seamless 16x16 canvas (marks placed on a torus). Autotile
quadrants are composed from a 16x16 *inside* texture, a 16x16 *outside* texture (the plain
ground tile the set sits on, cropped at the same tile offset so it continues into the adjacent
plain ground tiles) and a per-edge margin profile, so all 47 masks join seamlessly.

Deterministic: fixed seeds only (Rng("...")); no wall-clock, no set iteration.
"""
from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from pixelkit import Canvas, Rng, Sheet, blob47, CANONICAL_MASKS, mask_from_neighbors

T = 16                      # tile size
H = 8                       # quadrant size
WATER_FPS = 4               # ground water frames / Water blob frames

# ------------------------------------------------------------------------------------------
# small drawing helpers (all wrap on the 16px torus so textures tile seamlessly)
# ------------------------------------------------------------------------------------------
Shape = Sequence[Tuple[int, int]]
DOT: Shape = ((0, 0),)
DASH2: Shape = ((0, 0), (1, 0))
DASH3: Shape = ((0, 0), (1, 0), (2, 0))
BLADE: Shape = ((0, 0), (0, 1))
DIAG: Shape = ((0, 0), (1, 1))
DIAG2: Shape = ((1, 0), (0, 1))
TUFT: Shape = ((0, 1), (1, 0), (2, 1))          # small "^" grass stroke
BLOB22: Shape = ((0, 0), (1, 0), (0, 1), (1, 1))
BLOB32: Shape = ((0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1))
ROUND33: Shape = ((1, 0), (0, 1), (1, 1), (2, 1), (1, 2))


def tex(fill: str) -> Canvas:
    return Canvas(T, T, fill=fill)


def put(c: Canvas, x: int, y: int, color) -> None:
    c.set(x % c.w, y % c.h, color)


def mark(c: Canvas, x: int, y: int, shape: Shape, color) -> None:
    for dx, dy in shape:
        put(c, x + dx, y + dy, color)


def tdist(a: Tuple[int, int], b: Tuple[int, int], n: int = T) -> int:
    """Chebyshev distance on the n x n torus."""
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return max(min(dx, n - dx), min(dy, n - dy))


def scatter(rng: Rng, count: int, min_d: int = 3, avoid: Sequence[Tuple[int, int]] = (),
            tries: int = 400, n: int = T) -> List[Tuple[int, int]]:
    """`count` points on the torus with pairwise (and to `avoid`) Chebyshev distance >= min_d."""
    pts: List[Tuple[int, int]] = []
    taken = list(avoid)
    for _ in range(count):
        for _ in range(tries):
            p = (rng.randint(0, n - 1), rng.randint(0, n - 1))
            if all(tdist(p, q, n) >= min_d for q in taken):
                pts.append(p)
                taken.append(p)
                break
    return pts


def seamless_ok(c: Canvas) -> bool:
    """Cheap sanity check: nothing to assert for a torus-drawn canvas, kept for symmetry."""
    return c.w == T and c.h == T


# ------------------------------------------------------------------------------------------
# ground textures (16x16, seamless, no outline)
# ------------------------------------------------------------------------------------------
GRASS_SHAPES = (BLADE, DIAG, DIAG2, DOT, TUFT, BLADE, DIAG)


def grass_family(seed: str, base: str, dark: str, light: str, n_dark: int = 9, n_light: int = 2,
                 variants: int = 4, swap: int = 3) -> List[Canvas]:
    """Plain grass: `base` with sparse `dark` strokes and rare `light` specks.
    Variants share most strokes and differ in `swap` of them (spec: 'differ in a few specks')."""
    rng = Rng(f"{seed}/base")
    pts = scatter(rng, n_dark, min_d=3)
    marks = [(p, rng.choice(GRASS_SHAPES)) for p in pts]
    lights = scatter(rng, n_light, min_d=4, avoid=pts)
    out = []
    for v in range(variants):
        vr = Rng(f"{seed}/v{v}")
        m = list(marks)
        l = list(lights)
        if v > 0:
            idx = vr.sample(range(len(m)), swap)
            keep = [p for i, (p, _) in enumerate(m) if i not in idx]
            new_pts = scatter(vr, swap, min_d=3, avoid=keep + l)
            for i, np_ in zip(idx, new_pts):
                m[i] = (np_, vr.choice(GRASS_SHAPES))
            l = scatter(vr, n_light, min_d=4, avoid=[p for p, _ in m])
        c = tex(base)
        for (x, y), shape in m:
            mark(c, x, y, shape, dark)
        for x, y in l:
            put(c, x, y, light)
        out.append(c)
    return out


def grass_flowers(grass: Canvas, seed: str, count: int = 3) -> Canvas:
    """Tiny paper / vermilion dots on a grass tile (a 1px flower with a dark stem below)."""
    rng = Rng(seed)
    c = grass.copy()
    pts = scatter(rng, count, min_d=5)
    cols = ["paper", "vermilion_light", "paper", "paper_light"]
    for i, (x, y) in enumerate(pts):
        put(c, x, y, cols[(i + rng.randint(0, 1)) % len(cols)])
        put(c, x, y + 1, "moss_dark")
    return c


def speck_tile(seed: str, base: str, marks: Sequence[Tuple[str, int, Sequence[Shape], int]]) -> Canvas:
    """`base` fill plus groups of (color, count, shapes, min_d) marks scattered on the torus."""
    rng = Rng(seed)
    c = tex(base)
    taken: List[Tuple[int, int]] = []
    for color, count, shapes, min_d in marks:
        pts = scatter(rng, count, min_d=min_d, avoid=taken)
        for x, y in pts:
            mark(c, x, y, rng.choice(list(shapes)), color)
        taken += pts
    return c


def dirt_tile(seed: str) -> Canvas:
    return speck_tile(seed, "earth", [
        ("earth_dark", 6, (DOT, DASH2, DIAG, BLADE), 3),
        ("earth_light", 4, (DOT, DASH2), 3),
        ("earth_dark", 2, (DOT,), 2),
    ])


def road_tile(seed: str, rut_gaps: Sequence[Tuple[int, int]]) -> Canvas:
    """Packed earth with two horizontal wheel ruts (broken `earth` lines with dark pits)."""
    c = speck_tile(seed, "earth_light", [
        ("sand", 4, (DOT, DASH2), 3),
        ("earth", 4, (DOT, DIAG, DASH2), 3),
    ])
    rng = Rng(seed + "/ruts")
    for yi, y in enumerate((5, 10)):
        gaps = rut_gaps[yi]
        for x in range(T):
            in_gap = any(((x - g) % T) < gl for g, gl in [gaps])
            if in_gap:
                continue
            put(c, x, y, "earth")
        # a couple of darker pits in the rut
        for x in rng.sample(range(T), 2):
            if c.get_name(x, y) == "earth":
                put(c, x, y, "earth_dark")
    return c


def sand_tile(seed: str) -> Canvas:
    return speck_tile(seed, "paper_dark", [
        ("sand", 7, (DOT, DASH2, DIAG, DIAG2), 3),
        ("paper", 3, (DOT, DASH2), 3),
        ("ink_pale", 1, (DOT,), 4),
    ])


def mud_tile(seed: str) -> Canvas:
    return speck_tile(seed, "earth", [
        ("earth_dark", 5, (BLOB22, BLOB32, DASH3, DASH2), 4),
        ("ink_dark", 3, (DOT, DASH2), 3),
        ("earth_light", 2, (DOT,), 3),
    ])


def flagstone_tile(seed: str, cracked: bool = False) -> Canvas:
    """Square paving (方砖): 2x2 stones of 7px with 1px `ink` seams at x,y = 0 and 8 (seamless)."""
    c = tex("ink_pale")
    for s in (0, 8):
        c.hline(0, T - 1, s, "ink")
        c.vline(s, 0, T - 1, "ink")
    for sx in (0, 8):
        for sy in (0, 8):
            # shade bottom row / right column of each stone (light from top-left)
            c.hline(sx + 1, sx + 7, sy + 7, "ink_light")
            c.vline(sx + 7, sy + 1, sy + 7, "ink_light")
    rng = Rng(seed)
    for sx in (0, 8):
        for sy in (0, 8):
            if rng.chance(0.5):
                put(c, sx + 1, sy + 1, "paper_dark")   # a lit pixel at the top-left corner
    # a few worn specks and a chipped corner
    for _ in range(4):
        x, y = rng.randint(2, 6) + rng.choice((0, 8)), rng.randint(2, 6) + rng.choice((0, 8))
        put(c, x, y, "ink_light")
    put(c, 7 + rng.choice((0, 8)), 1 + rng.choice((0, 8)), "ink")
    if cracked:
        # a diagonal crack across one stone + moss in two seam pixels
        c.line(10, 2, 13, 5, "ink_light")
        put(c, 12, 4, "ink")
        put(c, 8, 12, "moss_dark")
        put(c, 3, 8, "moss_dark")
    return c


def cobble_tile(seed: str) -> Canvas:
    """Rounded cobbles 4x4 in staggered rows, `ink` gaps, lit top-left."""
    c = tex("ink")
    cob = [
        ".PPi",
        "PLLs",
        "PLLs",
        "isss",
    ]
    cmap = {"P": "ink_pale", "L": "ink_light", "s": "ink", "i": "ink"}
    rng = Rng(seed)
    for row in range(4):
        off = 2 if row % 2 else 0
        for col in range(4):
            x0, y0 = col * 4 + off, row * 4
            for yy, line in enumerate(cob):
                for xx, ch in enumerate(line):
                    if ch == ".":
                        continue
                    put(c, x0 + xx, y0 + yy, cmap[ch])
            r = rng.random()
            if r < 0.3:              # worn: no top highlight
                put(c, x0 + 1, y0, "ink_light")
                put(c, x0 + 2, y0, "ink_light")
            elif r < 0.5:            # a smaller stone: trim the right column
                put(c, x0 + 3, y0 + 1, "ink")
                put(c, x0 + 3, y0 + 2, "ink")
    return c


def planks_tile(seed: str, ends: Sequence[int], light: str, mid: str, seam: str,
                grain: str, knots: int = 1) -> Canvas:
    """Four horizontal planks (4px each): lit top rows, mid shade, dark seam; staggered ends."""
    c = tex(light)
    rng = Rng(seed)
    for p in range(4):
        y0 = p * 4
        c.hline(0, T - 1, y0 + 2, mid)
        c.hline(0, T - 1, y0 + 3, seam)
        ex = ends[p] % T
        c.vline(ex, y0, y0 + 2, seam)
        put(c, ex + 1, y0 + 1, mid)
        # grain dash
        gx = (ex + rng.randint(4, 9)) % T
        gl = rng.randint(2, 4)
        for i in range(gl):
            if (gx + i) % T != ex:
                put(c, gx + i, y0 + 1, grain)
    for _ in range(knots):
        p = rng.randint(0, 3)
        kx = (ends[p] + rng.randint(3, 11)) % T
        put(c, kx, p * 4 + 1, seam)
    return c


def snow_tile(seed: str) -> Canvas:
    return speck_tile(seed, "paper_light", [
        ("paper", 6, (DOT, DASH2, DIAG), 3),
        ("ink_pale", 2, (DOT,), 4),
        ("paper_dark", 1, (DOT,), 4),
    ])


def rock_tile(seed: str) -> Canvas:
    rng = Rng(seed)
    c = tex("ink_light")
    pts = scatter(rng, 5, min_d=4)
    for x, y in pts:
        # a short crack with a highlight on its upper-left side
        kind = rng.randint(0, 2)
        if kind == 0:
            mark(c, x, y, DASH3, "ink")
            put(c, x, y - 1, "ink_pale")
        elif kind == 1:
            mark(c, x, y, ((0, 0), (1, 1), (2, 1)), "ink")
            put(c, x - 1, y, "ink_pale")
        else:
            mark(c, x, y, ((0, 0), (0, 1), (1, 2)), "ink")
            put(c, x - 1, y - 1, "ink_pale")
    for x, y in scatter(rng, 3, min_d=3, avoid=pts):
        put(c, x, y, "ink_pale")
    for x, y in scatter(rng, 2, min_d=3, avoid=pts):
        put(c, x, y, "ink")
    return c


def cave_tile(seed: str) -> Canvas:
    return speck_tile(seed, "ink_dark", [
        ("ink", 7, (DOT, DASH2, DIAG, BLADE), 3),
        ("ink_black", 2, (DOT, DASH2), 3),
        ("ink_light", 1, (DOT,), 4),
    ])


def moss_tile(seed: str) -> Canvas:
    return speck_tile(seed, "moss", [
        ("moss_dark", 4, (BLOB22, BLOB32, DASH3, ((0, 0), (1, 0), (1, 1))), 4),
        ("moss_light", 4, (DOT, DASH2), 3),
        ("moss_pale", 1, (DOT,), 4),
        ("jade_dark", 1, (DOT,), 3),
    ])


def leaves_tile(seed: str) -> Canvas:
    return speck_tile(seed, "earth", [
        ("earth_light", 5, (DIAG, DIAG2, DASH2), 3),
        ("sand", 3, (DOT, DIAG2), 3),
        ("vermilion_dark", 2, (DOT,), 4),
        ("gold", 1, (DOT,), 3),
        ("earth_dark", 4, (DOT, DIAG), 2),
    ])


def tatami_tile(vertical: bool) -> Canvas:
    """paper_dark / sand weave (2x1 brick checker) with an `ink` heri on the top and left edge."""
    c = tex("paper_dark")
    for y in range(T):
        for x in range(T):
            if vertical:
                on = x % 2 == 0 and ((y + (x // 2)) % 4) < 2
            else:
                on = y % 2 == 0 and ((x + (y // 2)) % 4) < 2
            if on:
                put(c, x, y, "sand")
    c.hline(0, T - 1, 0, "ink")
    c.vline(0, 0, T - 1, "ink")
    put(c, 1, 1, "paper")      # lit inner corner
    return c


# ---- water ---------------------------------------------------------------------------------
RIPPLES = [  # (x, y, group)
    (3, 2, 0), (11, 5, 1), (1, 9, 1), (8, 12, 0), (13, 10, 0), (6, 7, 1), (14, 1, 1), (10, 15, 1),
]
SHADE = [(5, 4), (12, 8), (2, 13), (9, 1), (15, 6)]


def water_frames(base: str, shade: str, light: str, frames: int = 4) -> List[Canvas]:
    """Looping water: static dark shade dashes + light ripples that breathe/shift over 4 frames."""
    out = []
    for f in range(frames):
        c = tex(base)
        for x, y in SHADE:
            mark(c, x, y, DASH3, shade)
        for x, y, g in RIPPLES:
            ph = (f + 2 * g) % 4
            # phase 0: 3px dash, 1: 2px shifted right, 2: 3px shifted right with a tail, 3: 2px
            if ph == 0:
                mark(c, x, y, DASH3, light)
            elif ph == 1:
                mark(c, x + 1, y, DASH2, light)
            elif ph == 2:
                mark(c, x + 1, y, DASH3, light)
                put(c, x + 4, y - 1, light)
            else:
                mark(c, x, y, DASH2, light)
        out.append(c)
    return out


def shallow_tile(sand: Canvas) -> Canvas:
    """Wadeable water: translucent look = water_light checker dither over sand, with a few
    solid ripple dashes and darker `water` pixels in the troughs."""
    c = sand.copy()
    for y in range(T):
        for x in range(T):
            if (x + y) % 2 == 0:
                put(c, x, y, "water_light")
    for x, y in [(2, 3), (9, 6), (4, 11), (12, 13), (13, 1)]:
        mark(c, x, y, DASH2, "paper_light")
        put(c, x + 3, y + 1, "water")
    return c


def stepping_stone_tile(water: Canvas) -> Canvas:
    c = water.copy()
    c.ellipse(7.5, 7.5, 3.5, 3, "ink_light")
    c.ellipse(7, 7, 2.5, 2, "ink_pale")
    c.ellipse(8, 8.5, 2, 1.5, "ink_light")
    c.hline(5, 10, 11, "ink")
    put(c, 11, 10, "ink")
    put(c, 4, 10, "ink")
    for x, y in [(3, 7), (12, 7), (7, 3), (8, 12), (12, 12), (3, 12)]:
        put(c, x, y, "water_light")
    return c


def bridge_h_tile() -> Canvas:
    """Plank bridge crossing E-W: vertical planks between two earth_dark stringer beams."""
    c = planks_tile("bridge", (7, 7, 7, 7), "earth_light", "earth", "earth_dark", "earth", knots=0).rotated(-1)
    c.hline(0, T - 1, 0, "earth_dark")
    c.hline(0, T - 1, 1, "earth")
    c.hline(0, T - 1, 14, "earth")
    c.hline(0, T - 1, 15, "earth_dark")
    return c


def rail_n_tile() -> Canvas:
    c = Canvas(T, T)
    c.hline(0, T - 1, 0, "earth")
    c.hline(0, T - 1, 1, "earth_dark")
    for px in (1, 9):
        c.vline(px, 2, 4, "earth_dark")
        put(c, px + 1, 2, "earth")
    return c


def rail_s_tile() -> Canvas:
    c = Canvas(T, T)
    c.hline(0, T - 1, 11, "earth")
    c.hline(0, T - 1, 12, "earth_dark")
    for px in (1, 9):
        c.vline(px, 13, 15, "earth_dark")
        put(c, px + 1, 13, "earth")
    return c


# ------------------------------------------------------------------------------------------
# reed tufts (galdae) for the Reeds blob set
# ------------------------------------------------------------------------------------------
TUFT_PATTERNS = [
    [   # 0: tall 4x6
        "i..i",
        ".ii.",
        "s.s.",
        ".ss.",
        "s.s.",
        ".dd.",
    ],
    [   # 1: tall 4x6, leaning
        ".i..",
        "i.i.",
        ".s.s",
        "ss..",
        ".s..",
        ".d..",
    ],
    [   # 2: tall 4x6
        "..i.",
        ".i.i",
        "s.s.",
        ".ss.",
        ".s..",
        ".d..",
    ],
    [   # 3: short 3x4
        ".i.",
        "i.s",
        ".s.",
        ".d.",
    ],
    [   # 4: medium 3x5
        "i.i",
        ".s.",
        "s.s",
        ".s.",
        ".d.",
    ],
]
TUFT_MAP = {"i": "ink_light", "s": "sand", "d": "moss_dark"}


def tuft_canvas(idx: int, pale: bool = False) -> Canvas:
    cm = dict(TUFT_MAP)
    if pale:
        cm["s"] = "paper_dark"
    return Canvas.from_pattern(TUFT_PATTERNS[idx], cm)


def reed_tile(seed: str, count: int = 15) -> Canvas:
    """Reed bed (갈대밭) OVERLAY: a field of 1px stalks (sand / paper_dark) with ink_light seed
    heads and a moss_dark foot on a transparent canvas (drawn over any ground). With the blob margin m = 2 a 1px stalk is never cut
    by a border as long as its rows lie fully inside [3..12] or straddle the tile edge with
    every row within 2px of it (rows 13..15 + 0..2), so every column is allowed."""
    rng = Rng(seed)
    c = Canvas(T, T)
    placed: List[Tuple[int, int, int]] = []     # (x, y_top, height)
    for _ in range(count):
        for _ in range(200):
            x = rng.randint(0, T - 1)
            h = rng.choice((3, 4, 4, 5, 5, 6))
            if rng.chance(0.3):                      # straddles the horizontal tile edge
                y0 = 19 - h - rng.randint(0, 6 - h)  # rows within 13..18 (= 13..15 + 0..2)
                if y0 < 13:
                    continue
            else:
                y0 = rng.randint(3, 13 - h)
            # keep stalks apart: no other stalk within 1 column whose rows overlap (+1 margin)
            ok = True
            for px, py, ph in placed:
                dx = min(abs(px - x), T - abs(px - x))
                if dx <= 1:
                    ya, yb = y0, y0 + h - 1
                    if not (yb + 1 < py or ya - 1 > py + ph - 1):
                        ok = False
                        break
            if ok:
                placed.append((x, y0, h))
                break
    for x, y0, h in placed:
        stalk = rng.choice(("sand", "sand", "paper_dark", "earth_light"))
        for i in range(h):
            put(c, x, y0 + i, stalk)
        put(c, x, y0, "ink_light")                   # seed head
        put(c, x, y0 + h - 1, "moss_dark")           # foot
        if h >= 4 and rng.chance(0.5):               # a small leaf, never touching another stalk
            lx, ly = (x + rng.choice((-1, 1))) % T, y0 + 1 + rng.randint(0, 1)
            if all(c.get(lx + dx, (ly + dy) % T)[3] == 0 for dx in (-1, 1) for dy in (-1, 0, 1)) \
                    and c.get(lx, ly % T)[3] == 0:
                put(c, lx, ly, stalk)
    return c


# ------------------------------------------------------------------------------------------
# blob quadrant geometry (spec §4) with per-edge margins
# ------------------------------------------------------------------------------------------
class Zones:
    """Boolean 8x8 masks for one quadrant of one mask kind.

    d_ns / d_we : distance from the quadrant's outer N-or-S / W-or-E edge (0..7)
    ns_out / ns_border : the margin strip and border line along the N/S edge (when missing)
    we_out / we_border : same for the W/E edge
    For corner_in both *_out are the notch (d_ns < m_ns and d_we < m_we) and the borders are
    the two legs of the L wrapping it.
    """

    def __init__(self, qi: int, kind: str, m_n: int, m_s: int, m_w: int, m_e: int):
        self.qi, self.kind = qi, kind
        self.top, self.left = qi in (0, 1), qi in (0, 2)
        yq, xq = np.mgrid[0:H, 0:H]
        self.xq, self.yq = xq, yq
        self.d_ns = yq if self.top else (H - 1 - yq)
        self.d_we = xq if self.left else (H - 1 - xq)
        self.m_ns = m_n if self.top else m_s
        self.m_we = m_w if self.left else m_e
        self.ns_missing = kind in ("edge_h", "corner_out")
        self.we_missing = kind in ("edge_v", "corner_out")
        F = np.zeros((H, H), dtype=bool)
        if kind == "corner_in":
            notch = (self.d_ns < self.m_ns) & (self.d_we < self.m_we)
            self.ns_out = notch
            self.we_out = notch
            self.ns_border = (self.d_ns == self.m_ns) & (self.d_we <= self.m_we)
            self.we_border = (self.d_we == self.m_we) & (self.d_ns <= self.m_ns)
        else:
            self.ns_out = (self.d_ns < self.m_ns) if self.ns_missing else F
            self.ns_border = (self.d_ns == self.m_ns) if self.ns_missing else F
            self.we_out = (self.d_we < self.m_we) if self.we_missing else F
            self.we_border = (self.d_we == self.m_we) if self.we_missing else F
        self.out = self.ns_out | self.we_out
        self.border = (self.ns_border | self.we_border) & ~self.out
        # tile-space coordinates of every quadrant pixel
        ox, oy = (0 if self.left else H), (0 if self.top else H)
        self.xt = xq + ox
        self.yt = yq + oy
        self.ox, self.oy = ox, oy

    def chamfer(self) -> None:
        """Round convex corners: the border's corner pixel becomes outside material."""
        if self.kind == "corner_out":
            cpx = (self.d_ns == self.m_ns) & (self.d_we == self.m_we)
            self.out = self.out | cpx
            self.border = self.border & ~cpx


def crop(c: Canvas, z: Zones) -> Canvas:
    return c.cropped(z.ox, z.oy, H, H)


def compose(inside: Canvas, outside: Canvas, z: Zones) -> Canvas:
    """Inside crop with the outside crop pasted on the margin strips (border left for the caller)."""
    q = crop(inside, z)
    o = crop(outside, z)
    q.px[z.out] = o.px[z.out]
    return q


def paint(q: Canvas, mask: np.ndarray, color) -> None:
    if mask.any():
        q.fill_where(mask, color)


def line_tex(z: Zones, period: int, phase: int = 0) -> np.ndarray:
    """A deterministic along-the-edge pattern: True on every `period`-th pixel measured along the
    tile edge (x for N/S borders, y for W/E borders), consistent across quadrants."""
    ns = ((z.xt + phase) % period) == 0
    we = ((z.yt + phase) % period) == 0
    return np.where(z.ns_border, ns, we)


# ---- set drawers ---------------------------------------------------------------------------
def road_drawer(inside: Canvas, grass: Canvas) -> Callable:
    def draw(qi, kind, frame, rng):
        z = Zones(qi, kind, 2, 2, 2, 2)
        z.chamfer()
        q = compose(inside, grass, z)
        # border: packed-earth shoulder, broken by darker grass-shadow pixels (brush edge)
        paint(q, z.border, "earth")
        dots = line_tex(z, 3, 1)
        paint(q, z.border & dots, "moss_dark")
        return q
    return draw


def water_drawer(frames: List[Canvas], bank: Canvas) -> Callable:
    def draw(qi, kind, frame, rng):
        z = Zones(qi, kind, 2, 2, 2, 2)
        z.chamfer()
        q = compose(frames[frame], bank, z)
        # shoreline: wet sand line just outside, light water line on the border
        paint(q, z.border, "water_light")
        foam = line_tex(z, 4, frame)          # foam specks drift along the shore
        paint(q, z.border & foam, "paper_light")
        ns_ring, we_ring = _ring(z, 1)        # 1px inside the border: lapping water_light pixels
        lap = line_tex_inner(z, 4, frame + 2, ns_ring, we_ring)
        paint(q, lap, "water_light")
        return q
    return draw


def _ring(z: Zones, k: int) -> Tuple[np.ndarray, np.ndarray]:
    """(ns, we) pixel masks exactly k px inside the N/S and W/E border lines."""
    F = np.zeros((H, H), dtype=bool)
    if z.kind == "corner_in":
        ns = (z.d_ns == z.m_ns + k) & (z.d_we <= z.m_we + k)
        we = (z.d_we == z.m_we + k) & (z.d_ns <= z.m_ns + k)
    else:
        ns = (z.d_ns == z.m_ns + k) if z.ns_missing else F
        we = (z.d_we == z.m_we + k) if z.we_missing else F
    keep = ~z.out & ~z.border
    return ns & keep, we & keep


def line_tex_inner(z: Zones, period: int, phase: int, ns_ring: np.ndarray, we_ring: np.ndarray) -> np.ndarray:
    ns = ((z.xt + phase) % period) == 0
    we = ((z.yt + phase) % period) == 0
    return (ns_ring & ns) | (we_ring & we & ~ns_ring)


def reeds_drawer(inside: Canvas) -> Callable:
    """Overlay set: the margin and border are simply transparent (the stalks stop)."""
    empty = Canvas(T, T)

    def draw(qi, kind, frame, rng):
        z = Zones(qi, kind, 2, 2, 2, 2)
        q = compose(inside, empty, z)
        q.px[z.border] = 0
        return q
    return draw


def courtyard_drawer(inside: Canvas, grass: Canvas) -> Callable:
    def draw(qi, kind, frame, rng):
        z = Zones(qi, kind, 2, 2, 2, 2)
        q = compose(inside, grass, z)
        paint(q, z.border, "ink")
        return q
    return draw


def cliff_drawer(top: Canvas, grass: Canvas, face_rows: int, rim_lit: str, rim_shade: str,
                 face_base: str, face_dark: str, face_light: str, face_edge: str) -> Callable:
    """Plateau: N/W/E edges show a 2px ground margin + 1px rim; S edges show a `face_rows`px
    rock face (ink-wash vertical strokes) under a lit rim. Used by Cliff and CaveWall."""
    face_h = face_rows + 1                  # face + the rim row above it

    # vertical ink strokes hanging from the rim: stroke length per tile column (period 16 so
    # the face continues seamlessly into the next tile), 0 = no stroke
    stroke_len = [0, 3, 0, 5, 1, 0, 4, 0, 2, 0, 0, 5, 0, 3, 0, 1]
    foot_len = [1, 0, 2, 0, 0, 1, 0, 3, 0, 1, 0, 0, 2, 0, 1, 0]

    def face_pattern(z: Zones) -> Dict[str, np.ndarray]:
        xt, d = z.xt, z.d_ns                 # d: 0 = foot of the face, face_rows-1 = under the rim
        top_row = face_rows - 1
        sl = np.vectorize(lambda x: stroke_len[x % 16])(xt)
        fl = np.vectorize(lambda x: foot_len[x % 16])(xt)
        return {
            "dark": (d <= top_row - 1) & (d > top_row - 1 - sl),        # strokes from the rim down
            "dark2": (d >= 1) & (d <= fl),                              # short strokes rising from the foot
            "light": (xt % 7 == 2) & (d == top_row),
        }

    def draw(qi, kind, frame, rng):
        z = Zones(qi, kind, 2, face_h, 2, 2)
        q = compose(top, grass, z)
        bottom = not z.top
        face = bottom & z.ns_out                       # the S face region (notch or strip)
        # ground beyond the face (W/E margin on corner_out) wins over the face
        if kind == "corner_out" and bottom:
            face = face & ~z.we_out
            q.px[z.we_out] = crop(grass, z).px[z.we_out]
        if face.any():
            q.fill_where(face, face_base)
            fp = face_pattern(z)
            paint(q, face & fp["dark"], face_dark)
            paint(q, face & fp["dark2"], face_dark)
            paint(q, face & fp["light"], face_light)
            paint(q, face & (z.d_ns == 0), face_dark)          # foot of the face in shadow
            paint(q, face & (z.d_ns == face_rows - 1), face_light)  # just under the rim: lit
        # rims
        ns_rim = z.ns_border
        we_rim = z.we_border
        if bottom:
            paint(q, ns_rim, rim_lit)
            if kind == "corner_out":
                # the vertical rim meets the face: below the rim row the W/E boundary is the face's side
                side = we_rim & (z.d_ns < face_h)
                paint(q, we_rim & ~side, rim_lit if z.left else rim_shade)
                paint(q, side & ~z.ns_border, face_edge if z.left else face_dark)
                paint(q, we_rim & z.ns_border, rim_lit)
            else:
                paint(q, we_rim, rim_lit if z.left else rim_shade)
        else:
            paint(q, ns_rim, rim_lit)
            paint(q, we_rim, rim_lit if z.left else rim_shade)
            if kind == "corner_out":
                paint(q, we_rim & z.ns_border, rim_lit)
        return q
    return draw


# ------------------------------------------------------------------------------------------
# sheets
# ------------------------------------------------------------------------------------------
def tile_asset_name(sprite: str, prefix: str = "ground_") -> str:
    desc = sprite[len(prefix):]
    parts = desc.split("_")
    if parts[-1].isdigit():
        parts[-1] = "ABCDEFGH"[int(parts[-1])]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def build_textures() -> Dict[str, object]:
    """All 16x16 textures, keyed by ground sprite descriptor (lists for animated ones)."""
    tx: Dict[str, object] = {}
    grass = grass_family("grass", "moss", "moss_dark", "moss_light")
    for i, g in enumerate(grass):
        tx[f"grass_{i}"] = g
    tx["grass_flowers_0"] = grass_flowers(grass[1], "flowers/0", 3)
    tx["grass_flowers_1"] = grass_flowers(grass[2], "flowers/1", 2)
    dark = grass_family("grass_dark", "moss_dark", "ink_dark", "moss", n_dark=7, n_light=3, variants=2)
    tx["grass_dark_0"], tx["grass_dark_1"] = dark
    tx["dirt_0"], tx["dirt_1"] = dirt_tile("dirt/0"), dirt_tile("dirt/1")
    tx["road_0"] = road_tile("road/0", [(3, 2), (11, 3)])
    tx["road_1"] = road_tile("road/1", [(9, 3), (1, 2)])
    tx["sand_0"], tx["sand_1"] = sand_tile("sand/0"), sand_tile("sand/1")
    tx["mud"] = mud_tile("mud")
    tx["stone_0"] = flagstone_tile("stone/0")
    tx["stone_1"] = flagstone_tile("stone/1", cracked=True)
    tx["cobble_0"], tx["cobble_1"] = cobble_tile("cobble/0"), cobble_tile("cobble/1")
    tx["planks_0"] = planks_tile("planks/0", (5, 12, 2, 9), "earth_light", "earth", "earth_dark", "earth")
    tx["planks_1"] = planks_tile("planks/1", (10, 3, 14, 7), "earth_light", "earth", "earth_dark", "earth", knots=2)
    tx["planks_v"] = tx["planks_0"].rotated(-1)
    tx["snow_0"], tx["snow_1"] = snow_tile("snow/0"), snow_tile("snow/1")
    tx["rock_0"], tx["rock_1"] = rock_tile("rock/0"), rock_tile("rock/1")
    tx["cave_0"], tx["cave_1"] = cave_tile("cave/0"), cave_tile("cave/1")
    tx["moss"] = moss_tile("moss")
    tx["leaves"] = leaves_tile("leaves")
    tx["water"] = water_frames("water", "water_deep", "water_light")
    tx["water_deep"] = water_frames("water_deep", "navy", "water")
    tx["shallow"] = shallow_tile(tx["sand_0"])
    tx["bridge_h"] = bridge_h_tile()
    tx["bridge_v"] = tx["bridge_h"].rotated(-1)
    tx["bridge_rail_n"] = rail_n_tile()
    tx["bridge_rail_s"] = rail_s_tile()
    tx["stepping_stone"] = stepping_stone_tile(tx["water"][0])
    tx["void"] = tex("ink_black")
    tx["tatami_0"], tx["tatami_1"] = tatami_tile(False), tatami_tile(True)
    tx["wood_floor_0"] = planks_tile("floor/0", (6, 13, 1, 9), "earth_light", "earth_light", "earth", "sand", knots=0)
    tx["wood_floor_1"] = planks_tile("floor/1", (11, 4, 8, 15), "earth_light", "earth_light", "earth", "sand", knots=1)
    return tx


GROUND_ORDER = [
    "grass_0", "grass_1", "grass_2", "grass_3", "grass_flowers_0", "grass_flowers_1",
    "grass_dark_0", "grass_dark_1", "dirt_0", "dirt_1", "road_0", "road_1", "sand_0", "sand_1",
    "mud", "stone_0", "stone_1", "cobble_0", "cobble_1", "planks_0", "planks_1", "planks_v",
    "snow_0", "snow_1", "rock_0", "rock_1", "cave_0", "cave_1", "moss", "leaves",
    "water_0", "water_1", "water_2", "water_3", "water_deep_0", "water_deep_1", "water_deep_2",
    "water_deep_3", "shallow", "bridge_h", "bridge_v", "bridge_rail_n", "bridge_rail_s",
    "stepping_stone", "void", "tatami_0", "tatami_1", "wood_floor_0", "wood_floor_1",
]
SOLID = {"water_0", "water_1", "water_2", "water_3", "water_deep_0", "water_deep_1",
         "water_deep_2", "water_deep_3", "void"}
TAGS = {
    "grass": "grass,outdoor", "dirt": "dirt,outdoor", "road": "road,outdoor", "sand": "sand,riverbank",
    "mud": "mud,outdoor", "stone": "stone,courtyard", "cobble": "stone,street", "planks": "wood,dock",
    "snow": "snow,mountain", "rock": "rock,mountain", "cave": "cave,floor", "moss": "moss,forest",
    "leaves": "leaves,forest", "water": "water,river,animated", "shallow": "water,wadeable",
    "bridge": "bridge,wood", "stepping": "water,stone,walkable", "void": "void", "tatami": "interior,tatami",
    "wood": "interior,wood",
}


def build_ground(tx: Dict[str, object]) -> Sheet:
    s = Sheet("ground", "tiles", pivot=(0.5, 0.0))
    for desc in GROUND_ORDER:
        if desc in ("water_0", "water_1", "water_2", "water_3"):
            c = tx["water"][int(desc[-1])]
        elif desc.startswith("water_deep_"):
            c = tx["water_deep"][int(desc[-1])]
        else:
            c = tx[desc]
        name = f"ground_{desc}"
        key = desc.split("_")[0]
        tags = TAGS.get(key, key)
        overlay = desc.startswith("bridge_rail")
        ground = "ground_bridge_h" if overlay else ""
        s.add(name, c, solid=desc in SOLID, overlay=overlay, ground=ground, tags=tags)
        s.add_tile(tile_asset_name(name), name, collider="grid" if desc in SOLID else "none")
    s.add_animation("water", [f"ground_water_{i}" for i in range(4)], WATER_FPS, loop=True, state="water")
    s.add_animation("water_deep", [f"ground_water_deep_{i}" for i in range(4)], WATER_FPS, loop=True, state="water")
    return s


def build_autotiles(tx: Dict[str, object]) -> Tuple[Sheet, Dict[str, Callable]]:
    grass = tx["grass_0"]
    s = Sheet("autotiles", "autotiles", pivot=(0.5, 0.0))
    road_inside = speck_tile("auto/road", "earth_light", [
        ("sand", 4, (DOT, DASH2), 3),
        ("earth", 5, (DOT, DIAG, DASH2), 3),
    ])
    drawers = {
        "Road": road_drawer(road_inside, grass),
        "Water": water_drawer(tx["water"], tx["sand_0"]),
        "Reeds": reeds_drawer(reed_tile("reeds")),
        "Cliff": cliff_drawer(tx["rock_0"], grass, 6, "ink_pale", "ink", "ink", "ink_dark", "ink_light", "ink_dark"),
        "CaveWall": cliff_drawer(cave_wall_top(), tx["cave_0"], 6, "ink_light", "ink_dark", "ink", "ink_dark", "ink_light", "ink_black"),
        "Courtyard": courtyard_drawer(tx["stone_0"], grass),
    }
    specs = [  # (rule, prefix, frames, collider, fps, tags)
        ("Road", "autotiles_road", 1, "none", 0, "road,over_grass"),
        ("Water", "autotiles_water", 4, "grid", WATER_FPS, "water,river,over_sand,animated"),
        ("Reeds", "autotiles_reeds", 1, "none", 0, "reeds,encounter,overlay"),
        ("Cliff", "autotiles_cliff", 1, "grid", 0, "cliff,rock,over_grass"),
        ("CaveWall", "autotiles_cave_wall", 1, "grid", 0, "cave,wall,over_cave_floor"),
        ("Courtyard", "autotiles_courtyard", 1, "none", 0, "stone,courtyard,over_grass"),
    ]
    for rule, prefix, frames, collider, fps, tags in specs:
        blob = blob47(drawers[rule], size=T, frames=frames, rng=Rng(f"blob/{rule}"))
        overlay = rule == "Reeds"
        s.add_blob(rule, prefix, blob, collider=collider, anim_fps=fps,
                   solid=(collider == "grid"), overlay=overlay,
                   ground="ground_grass_0" if overlay else "", tags=tags)
    return s, drawers


def cave_wall_top() -> Canvas:
    return speck_tile("auto/cavewall", "ink_dark", [
        ("ink_black", 6, (DASH2, DIAG, BLADE, DOT), 3),
        ("ink", 3, (DOT,), 3),
    ])


# ------------------------------------------------------------------------------------------
# previews: 3x3 tiling test and the 24x16 demo scene
# ------------------------------------------------------------------------------------------
def tiling_preview(ground: Sheet, path: str, scale: int = 4) -> str:
    t = Sheet("ground", "tiles")
    for e in ground.sprites:
        big = Canvas(T * 3, T * 3)
        if e.overlay:
            base = ground.get_canvas("ground_bridge_h")
            for yy in range(3):
                for xx in range(3):
                    big.blit(base, xx * T, yy * T)
        for yy in range(3):
            for xx in range(3):
                big.blit(e.canvas, xx * T, yy * T)
        t.add(e.name, big)
    return t.preview(path, scale=scale, labels=True)


DEMO_MAP = [
    "....cccccc...ww..kkkkk..",
    "....cccccc...ww..kkkkkk.",
    "....cccccc...ww..kkkkkk.",
    "....cccc.....ww..kkkk...",
    ".............ww..kkkk...",
    ".............ww.........",
    "............ww..........",
    "............ww..........",
    "rrrrrrrrrrrrbbrrrrrrrrrr",
    "rrrrrrrrrrrrbbrrrrrrrrrr",
    "............ww..vvvvvvvv",
    "..eeee......ww..vWWWWWWW",
    ".eeeeee.....ww..vWfffffW",
    ".eeeeeee....ww..vWfffffW",
    "..eeeee.....ww..vWWWWWWW",
    "...eee......ww..vvvvvvvv",
]


def demo_scene(ground: Sheet, auto: Sheet, path: str, scale: int = 3) -> str:
    rows = DEMO_MAP
    Hc, Wc = len(rows), len(rows[0])
    rng = Rng("demo")

    def ch(x: int, y: int) -> str:
        if 0 <= x < Wc and 0 <= y < Hc:
            return rows[y][x]
        return "#"

    def present(set_chars: str, oob: bool):
        def f(x: int, y: int) -> bool:
            c = ch(x, y)
            if c == "#":
                return oob
            return c in set_chars
        return f

    def mask_at(x: int, y: int, pres) -> int:
        return mask_from_neighbors(
            n=pres(x, y - 1), ne=pres(x + 1, y - 1), e=pres(x + 1, y), se=pres(x + 1, y + 1),
            s=pres(x, y + 1), sw=pres(x - 1, y + 1), w=pres(x - 1, y), nw=pres(x - 1, y - 1))

    sets = {
        "c": ("autotiles_courtyard", present("c", False), ""),
        "k": ("autotiles_cliff", present("k", False), ""),
        "w": ("autotiles_water", present("wb", False), "_f0"),
        "r": ("autotiles_road", present("rb", False), ""),
        "e": ("autotiles_reeds", present("e", False), ""),
        "W": ("autotiles_cave_wall", present("Wv", True), ""),
    }
    img = Canvas(Wc * T, Hc * T)
    water = set()
    for y in range(Hc):
        for x in range(Wc):
            if rows[y][x] in "wb":
                water.add((x, y))
    bank = set()
    for (x, y) in water:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if (x + dx, y + dy) not in water and ch(x + dx, y + dy) != "#":
                    bank.add((x + dx, y + dy))
    grass_names = ["ground_grass_0", "ground_grass_1", "ground_grass_2", "ground_grass_3"]
    for y in range(Hc):
        for x in range(Wc):
            c = rows[y][x]
            # ground layer
            if (x, y) in bank or c in "wb":
                g = rng.choice(["ground_sand_0", "ground_sand_1"])
            elif c in "fW":
                g = rng.choice(["ground_cave_0", "ground_cave_1"])
            elif c == "v":
                g = "ground_void"
            else:
                g = rng.choice(grass_names + grass_names + ["ground_grass_flowers_0", "ground_grass_flowers_1"])
            img.blit(ground.get_canvas(g), x * T, y * T)
            if c in sets:
                prefix, pres, suffix = sets[c]
                m = mask_at(x, y, pres)
                img.blit(auto.get_canvas(f"{prefix}_m{m}{suffix}"), x * T, y * T)
            elif c == "b":
                img.blit(ground.get_canvas("ground_bridge_h"), x * T, y * T)
                rail = "ground_bridge_rail_n" if rows[y - 1][x] != "b" else "ground_bridge_rail_s"
                img.blit(ground.get_canvas(rail), x * T, y * T)
    out = img.scaled(scale)
    return out.save(path)


# ------------------------------------------------------------------------------------------
def build(art_root: str, preview_dir: str, cellmap_dir: str) -> List[str]:
    tiles_dir = os.path.join(art_root, "Tiles")
    os.makedirs(tiles_dir, exist_ok=True)
    os.makedirs(preview_dir, exist_ok=True)
    os.makedirs(cellmap_dir, exist_ok=True)
    written: List[str] = []

    tx = build_textures()
    ground = build_ground(tx)
    auto, _ = build_autotiles(tx)

    for s in (ground, auto):
        png, js = s.save(tiles_dir)
        written += [png, js]
        written.append(s.preview(os.path.join(preview_dir, f"{s.file_name}_preview.png"), scale=4, labels=True))
        cm = s.cellmap(os.path.join(cellmap_dir, f"{s.name}_cellmap.png"), os.path.join(cellmap_dir, f"{s.name}.md"))
        written += list(cm)
    written.append(tiling_preview(ground, os.path.join(preview_dir, "ground_tiling_preview.png")))
    written.append(demo_scene(ground, auto, os.path.join(preview_dir, "tiles_demo.png")))
    return written


if __name__ == "__main__":
    import sys
    root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    for p in build(os.path.join(root, "Assets", "InkPixel", "Art"), os.path.join(root, "Docs", "previews"),
                   os.path.join(root, "Docs", "cellmaps")):
        print(p)
