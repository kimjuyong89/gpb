"""gen_characters_animals.py -- the 13 animal character sheets + 13 faces of ASSET_SPEC.md §5.1.

wolf, tiger, bear, deer, egret (백로), dog, chicken, boar, monkey, snake, fox, horse, raccoon
(너구리) -- the beasts of 강호유랑기's mountains (무명산 산중수련: 너구리·늑대 사냥, the 큰 곰 of the
cave), reed beds (백로진 = "white egret town") and village yards.

Animals are quadrupeds and birds, so charkit's human templates do not apply: every animal is
drawn here directly as ASCII patterns per direction (down = facing the camera, up = seen from
behind, left = side view; right = mirrored left). Each direction has a hand-drawn `stand` pose;
the walk frames swap the leg band (`legs`) and bob the body 1 px (`bob`), the attack frames
(bite / pounce / peck / kick / headbutt) and the hurt flinch are hand-drawn or derived from
`stand` by small ops (shift, rect/paste overlays, letter swaps). The 1 px ink_black outline is
added LAST (`Canvas.outlined()`), so all art stays inside x,y 1..14 of the 16x16 frame (1..30 of
the 32x32 face); `build()` asserts this so no outline is ever clipped.

Pose spec (per view, per pose name):
  * a list of row strings (full pattern; rows shorter than 16 are padded, ' ' == '.'), or
  * a dict of ops applied in this order: "from" (base pose, default "stand"), "shift" (dx, dy),
    "bob" (True: body up 1 px, used with "legs"), "move" [(x, y, w, h, dx, dy)] (move a rect),
    "rows" [(y, rows)] (full-width row replace), "rect" [(x, y, rows)] (rectangle replace, '.'
    erases), "legs" rows (rectangle replace at the view's `leg_rect`; with "bob" the band grows
    one row upward so the feet stay on the ground), "paste" [(x, y, rows)] (overlay, '.' keeps),
    "swap" {letter: letter}.
  Walk = stand, step_l, pass, step_r; attack = wind, strike, recover; hurt. Missing wind/recover/
  hurt fall back to shifts away from the facing direction (see `DEFAULT_BACK`) with the eye
  letter E swapped to the squint letter S for hurt.

Colors are palette NAMES only (ink-wash mood: paper lights, ink darks, muted earth/moss, sparse
vermilion/jade/gold). Light from the top-left: highlights on the top/left (letter L), shade on
the bottom/right (letter D). Letters are per animal; the common ones are B body, D shade,
L light, K darkest fur, E eye, N nose, S squint, W white (fangs/teeth), T tongue/comb accent.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple, Union

from pixelkit import Canvas, character_sheet

FRAME = 16
FACE = 32
DIRS = ("down", "up", "left", "right")
WALK_POSES = ("stand", "step_l", "pass", "step_r")
ATTACK_POSES = ("wind", "strike", "recover")
POSES = WALK_POSES + ATTACK_POSES + ("hurt",)
# "back" = away from the facing direction, used by the default wind-up and hurt flinch.
DEFAULT_BACK = {"down": (0, -1), "up": (0, 0), "left": (1, 0)}

Rows = Sequence[str]
Grid = List[List[str]]
PoseSpec = Union[Rows, dict]


# ------------------------------------------------------------------------------------------
# letter grid ops
# ------------------------------------------------------------------------------------------
def _grid(rows: Rows, w: int = FRAME, h: int = FRAME) -> Grid:
    g = [["."] * w for _ in range(h)]
    rows = list(rows)
    if len(rows) > h:
        raise ValueError(f"pattern has {len(rows)} rows, max {h}")
    for y, row in enumerate(rows):
        if len(row) > w:
            raise ValueError(f"pattern row {y} is {len(row)} wide, max {w}: {row!r}")
        for x, ch in enumerate(row):
            if ch not in ". ":
                g[y][x] = ch
    return g


def _shift(g: Grid, dx: int, dy: int) -> Grid:
    h, w = len(g), len(g[0])
    out = [["."] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            ch = g[y][x]
            if ch == ".":
                continue
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h:
                out[ny][nx] = ch
    return out


def _rect(g: Grid, x: int, y: int, rows: Rows) -> None:
    """Rectangle replace: every cell of the rows' bounding box is overwritten ('.' erases)."""
    w = max(len(r) for r in rows)
    for j, row in enumerate(rows):
        row = row.ljust(w, ".")
        for i, ch in enumerate(row):
            yy, xx = y + j, x + i
            if 0 <= yy < len(g) and 0 <= xx < len(g[0]):
                g[yy][xx] = "." if ch in ". " else ch


def _paste(g: Grid, x: int, y: int, rows: Rows) -> None:
    """Overlay: '.' / ' ' keep the underlying cell, '_' erases, anything else paints."""
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch in ". ":
                continue
            yy, xx = y + j, x + i
            if 0 <= yy < len(g) and 0 <= xx < len(g[0]):
                g[yy][xx] = "." if ch == "_" else ch


def _move(g: Grid, x: int, y: int, w: int, h: int, dx: int, dy: int) -> None:
    """Move the cells of a rectangle by (dx, dy), clearing the source first."""
    block = [[g[yy][xx] if 0 <= yy < len(g) and 0 <= xx < len(g[0]) else "." for xx in range(x, x + w)]
             for yy in range(y, y + h)]
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            if 0 <= yy < len(g) and 0 <= xx < len(g[0]):
                g[yy][xx] = "."
    for j in range(h):
        for i in range(w):
            ch = block[j][i]
            if ch == ".":
                continue
            yy, xx = y + j + dy, x + i + dx
            if 0 <= yy < len(g) and 0 <= xx < len(g[0]):
                g[yy][xx] = ch


def _rows_of(g: Grid) -> List[str]:
    return ["".join(r) for r in g]


# ------------------------------------------------------------------------------------------
# animal definition + pose resolution
# ------------------------------------------------------------------------------------------
class Animal:
    """One animal: palette letters, three hand-drawn views (down/up/left; right = mirrored left
    unless given), the leg band rectangle per view (x, y, w, h) and the 32x32 face rows."""

    def __init__(self, name: str, colors: Dict[str, str], views: Dict[str, Dict[str, PoseSpec]],
                 leg_rect: Dict[str, Tuple[int, int, int, int]], face: Rows,
                 squint: str = "S", back: Optional[Dict[str, Tuple[int, int]]] = None,
                 post: str = ""):
        self.name = name
        self.colors = dict(colors)
        self.views = views
        self.leg_rect = leg_rect
        self.face = list(face)
        self.squint = squint
        self.back = dict(DEFAULT_BACK)
        if back:
            self.back.update(back)
        # `post` letters are painted AFTER the outline pass, so they get no outline of their own:
        # used for 1 px bird legs (an ink_black leg outlined in ink_black would be a 3 px bar).
        self.post = post
        for d in ("down", "up", "left"):
            if d not in views:
                raise ValueError(f"{name}: view {d!r} missing")
            if "stand" not in views[d]:
                raise ValueError(f"{name}: view {d!r} has no 'stand' pose")

    # -- pose resolution ---------------------------------------------------------------
    def _default(self, view: str, pose: str) -> PoseSpec:
        back = self.back[view]
        if pose == "wind":
            return {"from": "stand", "shift": back}
        if pose == "recover":
            return {"from": "stand"}
        if pose == "hurt":
            return {"from": "stand", "shift": back, "swap": {"E": self.squint}}
        raise KeyError(f"{self.name}: view {view!r} has no pose {pose!r} and no default")

    def grid(self, view: str, pose: str, _depth: int = 0) -> Grid:
        if _depth > 8:
            raise RecursionError(f"{self.name}: pose chain too deep at {view}/{pose}")
        poses = self.views[view]
        spec = poses.get(pose)
        if spec is None:
            spec = self._default(view, pose)
        if not isinstance(spec, dict):
            return _grid(spec)
        g = self.grid(view, spec.get("from", "stand"), _depth + 1)
        dx, dy = spec.get("shift", (0, 0))
        if dx or dy:
            g = _shift(g, dx, dy)
        bob = bool(spec.get("bob"))
        if bob:
            g = _shift(g, 0, -1)
        for (x, y, w, h, mdx, mdy) in spec.get("move", ()):
            _move(g, x, y, w, h, mdx, mdy)
        for (y, rows) in spec.get("rows", ()):
            _rect(g, 0, y, [r.ljust(FRAME, ".") for r in rows])
        for (x, y, rows) in spec.get("rect", ()):
            _rect(g, x, y, rows)
        legs = spec.get("legs")
        if legs is not None:
            lx, ly, lw, lh = self.leg_rect[view]
            legs = [r.ljust(lw, ".")[:lw] for r in legs]
            if len(legs) != lh:
                raise ValueError(f"{self.name}: {view}/{pose} legs must have {lh} rows, got {len(legs)}")
            if bob:
                legs = [legs[0]] + legs
                ly -= 1
            _rect(g, lx, ly, legs)
        for (x, y, rows) in spec.get("paste", ()):
            _paste(g, x, y, rows)
        swap = spec.get("swap")
        if swap:
            for row in g:
                for i, ch in enumerate(row):
                    if ch in swap:
                        row[i] = swap[ch]
        return g

    def frame(self, d: str, pose: str) -> Canvas:
        """Outlined 16x16 frame for direction d (right = mirrored left when not drawn)."""
        if d == "right" and "right" not in self.views:
            return self.frame("left", pose).flipped_x()
        rows = _rows_of(self.grid(d, pose))
        return self._render(rows, f"{self.name} {d}/{pose}")

    def _render(self, rows: Rows, what: str) -> Canvas:
        """Pattern -> outlined canvas; `post` letters are stamped on top of the outline."""
        if not self.post:
            c = Canvas.from_pattern(rows, self.colors)
            _assert_margin(c, what, 1)
            return c.outlined("ink_black")
        base_rows = ["".join("." if ch in self.post else ch for ch in r) for r in rows]
        post_rows = ["".join(ch if ch in self.post else "." for ch in r) for r in rows]
        base = Canvas.from_pattern(base_rows, self.colors)
        overlay = Canvas.from_pattern(post_rows, self.colors)
        _assert_margin(Canvas.from_pattern(rows, self.colors), what, 1)
        out = base.outlined("ink_black")
        out.blit(overlay, 0, 0)
        return out

    def face_canvas(self) -> Canvas:
        g = _grid(self.face, FACE, FACE)
        return self._render(_rows_of(g), f"{self.name} face")

    def character(self):
        walk = {d: [self.frame(d, p) for p in WALK_POSES] for d in DIRS}
        attack = {d: [self.frame(d, p) for p in ATTACK_POSES] for d in DIRS}
        hurt = {d: self.frame(d, "hurt") for d in DIRS}
        return walk, attack, hurt, self.face_canvas()


def _assert_margin(c: Canvas, what: str, margin: int) -> None:
    bb = c.bbox()
    if bb is None:
        raise ValueError(f"{what}: empty frame")
    x, y, w, h = bb
    if x < margin or y < margin or x + w > c.w - margin or y + h > c.h - margin:
        raise ValueError(f"{what}: art bbox {bb} leaves no room for the outline (keep inside {margin}..{c.w - margin - 1})")


ANIMALS: Dict[str, Animal] = {}


def register(animal: Animal) -> Animal:
    if animal.name in ANIMALS:
        raise ValueError(f"duplicate animal {animal.name}")
    ANIMALS[animal.name] = animal
    return animal


# ==========================================================================================
# WOLF (늑대) -- grey wolf: ink_light coat, ink shade, ink_pale muzzle/belly, ink_dark ears/tail.
# Long low body, pointed ears, hanging tail. Attack = bite (lunge with open jaws).
# ==========================================================================================
WOLF_COLORS = {"B": "ink_light", "D": "ink", "K": "ink_dark", "L": "ink_pale", "E": "ink_black",
               "N": "ink_black", "S": "ink", "W": "paper_light", "T": "vermilion"}

register(Animal(
    "wolf", WOLF_COLORS,
    views={
        "left": {
            "stand": [
                "................",
                "................",
                "....K.K.........",
                "...BKLKL........",
                "...BBBBBB.......",
                "..NBBEBBBBBBB...",
                "..LLLBBBBBBBBD..",
                "....BBBBBBBBBD..",
                "....LBBBBBBKDD..",
                "....LLBBBBLKKD..",
                "....BBD..DBB.K..",
                "....BBD..DBB.K..",
                "....BBD..DBB....",
                "....BBD..DBB....",
                "....DD...DDD....",
            ],
            "step_l": {"bob": True, "legs": [
                ".BBD..DBB.", ".BB.D.D.BB", "BB..D.D.BB", "BB..D.D.BB", "DD..D.D.DD"]},
            "pass": {"legs": [
                ".BBD..DBB.", ".BBD..DBB.", ".BBD..DBB.", "..BD..DB..", "..D....D.."]},
            "step_r": {"bob": True, "legs": [
                ".BBD..DBB.", ".DBB.BB.D.", "D..BB.BB.D", "D..BB.BB.D", "D..DD.DD.D"]},
            "wind": {"shift": (1, 0), "move": [(3, 2, 9, 5, 0, 1)],
                     "rows": [(3, ["................"]), (4, ["....BBKK........"])]},
            "strike": [
                "................",
                "................",
                "...K.K..........",
                "..BKLKL.........",
                "..BBBBBB........",
                ".NBBEBBBBBBB....",
                ".WW.BBBBBBBBD...",
                ".LLLBBBBBBBBDD..",
                "...LBBBBBBKDD...",
                "...LLBBBBLKKD...",
                "...BBD..DBB.K...",
                "..BB.D..D.BB.K..",
                ".BB..D..D..BB...",
                ".BB..D..D..BB...",
                ".DD..D..D..DD...",
            ],
            "hurt": {"shift": (1, 0), "rows": [(2, ["................"]), (3, ["....BBBKK......."])],
                     "swap": {"E": "S"}},
        },
        "down": {
            "stand": [
                "................",
                "................",
                "....KK....KK....",
                "....KL....LK....",
                "....BBBBBBBB....",
                "...BBBBBBBBBD...",
                "...BBEBBBBEBD...",
                "...BBBLLLLBBD...",
                "....BBLNNLBB....",
                ".....BLLLLB.....",
                "....BBBBBBBD....",
                "....BLLLLLBD....",
                "....BBLLLLBB....",
                "....BB....BB....",
                "....DD....DD....",
            ],
            "step_l": {"bob": True, "legs": ["BBLLLLBB", "BB....DD", "DD......"]},
            "pass": {"legs": ["BBLLLLBB", ".BB..BB.", ".DD..DD."]},
            "step_r": {"bob": True, "legs": ["BBLLLLBB", "DD....BB", "......DD"]},
            "strike": [
                "................",
                "................",
                "................",
                "....KK....KK....",
                "....KL....LK....",
                "....BBBBBBBB....",
                "...BBBBBBBBBD...",
                "...BBEBBBBEBD...",
                "...BBBLLLLBBD...",
                "....BBLNNLBB....",
                "....BBWTTWBB....",
                "....BBLLLLBB....",
                "...BBBLLLLBBB...",
                "...BB......BB...",
                "...DD......DD...",
            ],
            "hurt": {"shift": (0, -1), "swap": {"E": "S"},
                     "rows": [(1, ["................"]), (2, ["...KBBBBBBBBK..."])]},
        },
        "up": {
            "stand": [
                "................",
                "................",
                "....KK....KK....",
                "....KK....KK....",
                "....BBBBBBBB....",
                "...BBBBBBBBBD...",
                "...BBBBBBBBBD...",
                "...BBBBBBBBBD...",
                "....BBBBBBBD....",
                ".....BBBBBB.....",
                "....BBBBBBBD....",
                "....BBBDDBBD....",
                "....BB.DD.BB....",
                "....BB.DK.BB....",
                "....DD.KK.DD....",
            ],
            "step_l": {"bob": True, "legs": ["BB.DD.BB", "BB.DK.DD", "DD.KK..."]},
            "pass": {"legs": ["BB.DD.BB", ".BBDKBB.", ".DDKKDD."]},
            "step_r": {"bob": True, "legs": ["BB.DD.BB", "DD.DK.BB", "...KK.DD"]},
            "wind": {"move": [(3, 2, 10, 7, 0, 1)]},
            "strike": {"bob": True, "legs": ["BB.DD.BB", "BB.DK.BB", "DD.KK.DD"]},
            "hurt": {"move": [(3, 2, 10, 7, 0, 1)],
                     "rows": [(3, ["................"]), (4, ["...KKBBBBBBKK..."])]},
        },
    },
    leg_rect={"left": (3, 10, 10, 5), "down": (4, 12, 8, 3), "up": (4, 12, 8, 3)},
    face=[
        "................................",
        "................................",
        "......K..................K......",
        ".....KKK................KKK.....",
        ".....KLKK..............KKLK.....",
        ".....KLLKK............KKLLK.....",
        ".....KLLLKK..........KKLLLK.....",
        ".....KLLLKBBBBBBBBBBBBKLLLK.....",
        ".....KLLKBBBBBBBBBBBBBBKLLK.....",
        "......KKBBBBBBBBBBBBBBBBKK......",
        ".......BBBBBBBBBBBBBBBBBBD......",
        "......BBBBBBBBBBBBBBBBBBBBD.....",
        "......BBBBBBBBBBBBBBBBBBBBD.....",
        ".....BBBBKKKBBBBBBBBKKKBBBBD....",
        ".....BBBBKEEKBBBBBBKEEKBBBBD....",
        ".....BBBBBEEBBBBBBBBEEBBBBBD....",
        "....BBBBBBBBBBLLLLBBBBBBBBBBD...",
        "....BBBBBBBBBLLLLLLBBBBBBBBBD...",
        "....BBBBBBBBLLLNNLLLBBBBBBBBD...",
        ".....BBBBBBBLLNNNNLLBBBBBBBD....",
        ".....BBBBBBBLLLNNLLLBBBBBBBD....",
        "......BBBBBBLLLKKLLLBBBBBBD.....",
        ".......BBBBBLLKLLKLLBBBBBD......",
        "........BBBBBLLLLLLBBBBBD.......",
        ".........BBBBLLLLLLBBBBD........",
        "...........BBBBBBBBBBD..........",
        "........BBBBBBBBBBBBBBBBD.......",
        ".....BBBBBBBBBBBBBBBBBBBBBBD....",
        "...BBBBBBBBBLLLLLLBBBBBBBBBBDD..",
        "..BBBBBBBBBLLLLLLLLBBBBBBBBBDDD.",
        "..BBBBBBBBBLLLLLLLLBBBBBBBBBDDD.",
        "................................",
    ],
))


# ==========================================================================================
# TIGER (호랑이) -- gold coat with gold_light highlights, earth_light shade, paper muzzle/belly,
# ink_dark stripes (王 mark on the forehead), raised tail. Fills the cell. Attack = pounce/swipe.
# ==========================================================================================
TIGER_COLORS = {"B": "gold", "L": "gold_light", "D": "earth_light", "M": "paper", "K": "ink_dark",
                "E": "ink_black", "N": "ink_black", "S": "ink", "W": "paper_light", "T": "vermilion"}

_TIGER_LEGS_SIDE = ["BBD..DBBD.", "BBD..DBBD.", "BBD..DBBD.", "BBD..DBBD.", "DD...DDDD."]

register(Animal(
    "tiger", TIGER_COLORS,
    views={
        "left": {
            "stand": [
                "...............",
                "...............",
                "..KK.KK........",
                ".LBBLBBB......K",
                ".LBBEBBBKBBB..K",
                ".NBBBBBBKBBBKBK",
                ".MMBBBBBBBBBBKD",
                "...BBBBBKBBBBKD",
                "...MMBBBBBBBKDD",
                "...MMMBBBBBBBDD",
                "...BBD..DBBD...",
                "...BBD..DBBD...",
                "...BBD..DBBD...",
                "...BBD..DBBD...",
                "...DD...DDDD...",
            ],
            "step_l": {"bob": True, "legs": [
                ".BBD..DBBD..", ".BB.D.D.BBD.", "BB..D.D..BBD", "BB..D.D..BBD", "DD..D.D..DDD"]},
            "pass": {"legs": [
                ".BBD..DBBD..", ".BBD..DBBD..", ".BBD..DBBD..", "..BD..DBD...", "..D....DD..."]},
            "step_r": {"bob": True, "legs": [
                ".BBD..DBBD..", ".DBB.BB.DD..", "D..BB.BB..D.", "D..BB.BB..D.", "D..DD.DD..D."]},
            "wind": {"move": [(1, 2, 8, 5, 0, 1)]},
            "strike": [
                "...............",
                "...............",
                "..............K",
                "..KK.KK.......K",
                ".LBBLBBBKBBB..K",
                ".LBBEBBBKBBBKBK",
                ".NBBBBBBBBBBBKD",
                ".WW.BBBBKBBBBKD",
                ".MMMBBBBBBBBKDD",
                ".BBBBMBBBBBBBDD",
                ".DD..D..DBBD...",
                ".....D..DBBD...",
                ".....D..DBBD...",
                ".....D..DBBD...",
                ".....D..DDDD...",
            ],
            "hurt": {"move": [(1, 2, 8, 5, 0, -1)], "swap": {"E": "S"},
                     "rows": [(1, ["..............."]), (2, [".KBBBBBK......."])]},
        },
        "down": {
            "stand": [
                "...............",
                "...............",
                "..KK......KK...",
                "..BBBKBBKBBB...",
                ".LBBBBKKBBBBD..",
                ".LBBEBBBBEBBD..",
                ".LBKBBMMBBKBD..",
                "..BBMMMMMMBB...",
                "..BBMMNNMMBB...",
                "...BMMMMMMB....",
                "..BBBBBBBBBBD..",
                "..BBKMMMMKBBD..",
                "..BBDMMMMBBD...",
                "..BBD....BBD...",
                "..DDD....DDD...",
            ],
            "step_l": {"bob": True, "legs": ["BBDMMMMBBD.", "BBD....DDD.", "DDD........"]},
            "pass": {"legs": ["BBDMMMMBBD.", ".BBD..BBD..", ".DDD..DDD.."]},
            "step_r": {"bob": True, "legs": ["BBDMMMMBBD.", "DDD....BBD.", ".......DDD."]},
            "strike": [
                "...............",
                "...............",
                "...............",
                "..KK......KK...",
                "..BBBKBBKBBB...",
                ".LBBBBKKBBBBD..",
                ".LBBEBBBBEBBD..",
                ".LBKBBMMBBKBD..",
                "..BBMMMMMMBB...",
                "..BBMMNNMMBB...",
                "..BBMWTTWMBB...",
                "..BBBMMMMBBBD..",
                ".BBBDMMMMDBBB..",
                ".BBD......DBB..",
                ".DDD......DDD..",
            ],
            "hurt": {"shift": (0, -1), "swap": {"E": "S"},
                     "rows": [(1, ["..............."]), (2, [".KBBBKBBKBBBK.."])]},
        },
        "up": {
            "stand": [
                "...............",
                "...............",
                "..KK......KK...",
                "..BBBBBBBBBB...",
                ".LBBKBBBBKBBD..",
                ".LBBBKBBKBBBD..",
                ".LBBBBBBBBBBD..",
                "..BBBBBBBBBB...",
                "...BBBBBBBB..K.",
                "..BBKBBBBKBBBK.",
                "..BBBBKKBBBBDK.",
                "..BBKBBBBKBBDD.",
                "..BBD....BBD...",
                "..BBD....BBD...",
                "..DDD....DDD...",
            ],
            "step_l": {"bob": True, "legs": ["BBD....BBD.", "BBD....DDD.", "DDD........"]},
            "pass": {"legs": ["BBD....BBD.", ".BBD..BBD..", ".DDD..DDD.."]},
            "step_r": {"bob": True, "legs": ["BBD....BBD.", "DDD....BBD.", ".......DDD."]},
            "wind": {"move": [(1, 2, 12, 6, 0, 1)]},
            "strike": {"bob": True, "legs": ["BBD....BBD.", "BBD....BBD.", "DDD....DDD."]},
            "hurt": {"move": [(1, 2, 12, 6, 0, 1)],
                     "rows": [(3, ["..............."]), (4, [".KKBBBBBBBBKK.."])]},
        },
    },
    leg_rect={"left": (2, 10, 12, 5), "down": (2, 12, 11, 3), "up": (2, 12, 11, 3)},
    back={"left": (0, 0)},
    face=[
        "...............................",
        "...............................",
        "....KKKK................KKKK...",
        "...KKBBKK..............KKBBKK..",
        "...KBBBBBKK..........KKBBBBBK..",
        "...KBBBBBBKBBBBBBBBBBKBBBBBBK..",
        "....KBBBBBBBBBBBBBBBBBBBBBBK...",
        ".....LBBBBBBBKBBBBKBBBBBBBBD...",
        "....LBBBBBBBBKKBBKKBBBBBBBBBD..",
        "....LBBBBBKBBBKKKKBBBKBBBBBBD..",
        "...LBBBBBBKKBBBBBBBBKKBBBBBBBD.",
        "...LBBBBBBBBBBBBBBBBBBBBBBBBBD.",
        "...LBBBBKBBBBBBBBBBBBBBKBBBBBD.",
        "...LBBBBKKEEKBBBBBBKEEKKBBBBBD.",
        "...LBBBBBBEEBBBBBBBBEEBBBBBBBD.",
        "...LBBBBBBBBBBLLLLBBBBBBBBBBBD.",
        "...BBBBBBBBBLLLLLLLLBBBBBBBBBD.",
        "...BBKBBBBBLLLLNNLLLLBBBBBKBBD.",
        "...BBKKBBBLLLLNNNNLLLLBBBKKBBD.",
        "....BBBBBBLLLLLNNLLLLLBBBBBBD..",
        "....BBBBBBLLLLLKKLLLLLBBBBBBD..",
        ".....BBBBBLLLLKLLKLLLLBBBBBD...",
        "......BBBBLLLLLLLLLLLLBBBBD....",
        ".......BBBBLLLLLLLLLLBBBBD.....",
        ".........BBBBLLLLLLBBBBD.......",
        "...........BBBBBBBBBBD.........",
        "........BBBBBBBBBBBBBBBBBD.....",
        ".....BBBBBBBKBBBBBBBBKBBBBBBD..",
        "...BBBBBKBBBBBMMMMMMBBBBKBBBBBD",
        "..BBBBBBBBBBBMMMMMMMMBBBBBBBBDD",
        "..BBBBBKBBBBBMMMMMMMMBBBBBKBBDD",
    ],
))


# ==========================================================================================
# BEAR (큰 곰) -- the big bear of the cave: ink coat, ink_dark shade, ink_light highlight,
# earth_light muzzle, paper_light chest crescent (반달가슴곰). Fills the cell. Attack = rears up
# and slams with both paws.
# ==========================================================================================
BEAR_COLORS = {"B": "ink", "D": "ink_dark", "L": "ink_light", "M": "earth_light", "W": "paper_light",
               "E": "ink_black", "N": "ink_black", "K": "ink_black", "S": "ink_dark", "T": "vermilion"}

register(Animal(
    "bear", BEAR_COLORS,
    views={
        "left": {
            "stand": [
                "...............",
                "...............",
                "..LL.LL........",
                ".LBBBBBBB......",
                ".LBBEBBBBBBBB..",
                ".MMBBBBBBBBBBB.",
                ".NMBBBBBBBBBBBD",
                "..BBBBBBBBBBBBD",
                "..BBBBBBBBBBBDD",
                "...BBBBBBBBBBDD",
                "...BBBD..DBBBD.",
                "...BBBD..DBBBD.",
                "...BBBD..DBBBD.",
                "...BBBD..DBBBD.",
                "...DDD...DDDDD.",
            ],
            "step_l": {"bob": True, "legs": [
                ".BBBD..DBBBD.", ".BBBD..DBBBD.", "BBB.D..D.BBBD", "BBB.D..D.BBBD", "DDD.D..D.DDDD"]},
            "pass": {"legs": [
                ".BBBD..DBBBD.", ".BBBD..DBBBD.", ".BBBD..DBBBD.", "..BBD..DBBD..", "..DD....DDD.."]},
            "step_r": {"bob": True, "legs": [
                ".BBBD..DBBBD.", ".DBBB.BBB.D..", "D..BBB.BBB.D.", "D..BBB.BBB.D.", "D..DDD.DDD.D."]},
            "wind": {"move": [(1, 2, 9, 5, 0, 1)]},
            "strike": [
                "...............",
                "...............",
                "...LL.LL.......",
                "..LBBBBBB......",
                "..LBBEBBBB.....",
                ".MMBBBBBBBB....",
                ".NMBBBBBBBBB...",
                ".WW.BBBBBBBBB..",
                ".BBBBBBBBBBBBB.",
                ".DDBBBWWBBBBBBD",
                "...BBBBWWBBBBBD",
                "....BBBBBBBBBBD",
                "....BBBD..DBBBD",
                "....BBBD..DBBBD",
                "....DDD...DDDD.",
            ],
            "hurt": {"move": [(1, 2, 9, 5, 0, -1)], "swap": {"E": "S"},
                     "rows": [(1, ["..............."]), (2, [".LBBBBBBB......"])]},
        },
        "down": {
            "stand": [
                "...............",
                "...............",
                "..LL......LL...",
                "..BBBBBBBBBB...",
                ".LBBBBBBBBBBD..",
                ".LBBEBBBBEBBD..",
                ".LBBBMMMMBBBD..",
                "..BBBMNNMBBB...",
                "...BBBMMBBB....",
                ".BBBBBBBBBBBBB.",
                ".BBBWBBBBBBWBBD",
                ".BBBBWWBBWWBBBD",
                ".BBBDBBWWBBDBBD",
                ".BBBD......DBBD",
                ".DDDD......DDDD",
            ],
            "step_l": {"bob": True, "legs": ["BBBDBBWWBBDBBD", "BBBD......DDDD", "DDDD.........."]},
            "pass": {"legs": ["BBBDBBWWBBDBBD", ".BBBD....DBBD.", ".DDDD....DDDD."]},
            "step_r": {"bob": True, "legs": ["BBBDBBWWBBDBBD", "DDDD......DBBD", "..........DDDD"]},
            "strike": [
                "...............",
                "..LL......LL...",
                "..BBBBBBBBBB...",
                ".LBBBBBBBBBBD..",
                ".LBBEBBBBEBBD..",
                ".LBBBMMMMBBBD..",
                "..BBBMNNMBBB...",
                ".BB.BBMWWMBB.BB",
                ".BBBBBBBBBBBBBD",
                ".DDBBBWBBBBWBBD",
                "..BBBBWWBWWBBD.",
                "..BBBBBBWWBBBD.",
                "..BBBDBBBBBDBBD",
                "..BBBD.....DBBD",
                "..DDDD.....DDDD",
            ],
            "hurt": {"shift": (0, -1), "swap": {"E": "S"},
                     "rows": [(1, ["..............."]), (2, [".LBBBBBBBBBBB.."])]},
        },
        "up": {
            "stand": [
                "...............",
                "...............",
                "..LL......LL...",
                "..BBBBBBBBBB...",
                ".LBBBBBBBBBBD..",
                ".LBBBBBBBBBBD..",
                ".LBBBBBBBBBBD..",
                "..BBBBBBBBBBD..",
                "...BBBBBBBBD...",
                ".BBBBBBBBBBBBB.",
                ".BBBBBBBBBBBBBD",
                ".BBBBBBBBBBBBBD",
                ".BBBDBBBBBBDBBD",
                ".BBBD..BD..DBBD",
                ".DDDD......DDDD",
            ],
            "step_l": {"bob": True, "legs": ["BBBDBBBBBBDBBD", "BBBD..BD..DDDD", "DDDD.........."]},
            "pass": {"legs": ["BBBDBBBBBBDBBD", ".BBBD.BD.DBBD.", ".DDDD....DDDD."]},
            "step_r": {"bob": True, "legs": ["BBBDBBBBBBDBBD", "DDDD..BD..DBBD", "..........DDDD"]},
            "wind": {"move": [(1, 2, 12, 7, 0, 1)]},
            "strike": [
                "...............",
                "..LL......LL...",
                "..BBBBBBBBBB...",
                ".LBBBBBBBBBBD..",
                ".LBBBBBBBBBBD..",
                ".LBBBBBBBBBBD..",
                "..BBBBBBBBBBD..",
                ".BB.BBBBBBBB.BB",
                ".BBBBBBBBBBBBBD",
                ".DDBBBBBBBBBBBD",
                "..BBBBBBBBBBBD.",
                "..BBBBBBBBBBBD.",
                "..BBBDBBBBBDBBD",
                "..BBBD.BD..DBBD",
                "..DDDD.....DDDD",
            ],
            "hurt": {"move": [(1, 2, 12, 7, 0, 1)],
                     "rows": [(3, ["..............."]), (4, [".LLBBBBBBBBLL.."])]},
        },
    },
    leg_rect={"left": (2, 10, 13, 5), "down": (1, 12, 14, 3), "up": (1, 12, 14, 3)},
    back={"left": (0, 0)},
    face=[
        "...............................",
        "...............................",
        "...............................",
        ".....LLLL............LLLL......",
        "....LLBBLL..........LLBBLL.....",
        "....LBBBBBBBBBBBBBBBBBBBBD.....",
        "....LBBBBBBBBBBBBBBBBBBBBD.....",
        ".....LBBBBBBBBBBBBBBBBBBD......",
        "....LBBBBBBBBBBBBBBBBBBBBD.....",
        "...LBBBBBBBBBBBBBBBBBBBBBBD....",
        "...LBBBBBBBBBBBBBBBBBBBBBBD....",
        "..LBBBBBBBBBBBBBBBBBBBBBBBBD...",
        "..LBBBBBBEEBBBBBBBBBBEEBBBBD...",
        "..LBBBBBBEEBBBBBBBBBBEEBBBBD...",
        "..LBBBBBBBBBBMMMMMMBBBBBBBBD...",
        "..LBBBBBBBBBMMMMMMMMBBBBBBBD...",
        "..LBBBBBBBBMMMMNNNMMMBBBBBBD...",
        "...BBBBBBBBMMMNNNNNMMBBBBBBD...",
        "...BBBBBBBBMMMMNNNMMMBBBBBD....",
        "....BBBBBBBMMMMMMMMMMBBBBBD....",
        "....BBBBBBBBMMMKKMMMBBBBBBD....",
        ".....BBBBBBBBMMMMMMBBBBBBD.....",
        "......BBBBBBBBBBBBBBBBBBD......",
        ".......BBBBBBBBBBBBBBBBD.......",
        ".........BBBBBBBBBBBBD.........",
        "......BBBBBBBBBBBBBBBBBBBD.....",
        "...BBBBBBBBBBBBBBBBBBBBBBBBD...",
        "..BBBBBBBBBBBWWBBBBWWBBBBBBBDD.",
        ".BBBBBBBBBBBBBWWBBWWBBBBBBBBDDD",
        ".BBBBBBBBBBBBBBWWWWBBBBBBBBBDDD",
        ".BBBBBBBBBBBBBBBWWBBBBBBBBBBDDD",
    ],
))


# ==========================================================================================
# DEER (사슴) -- earth coat with sand belly/muzzle, paper spots, paper_dark antlers, thin legs
# with ink_dark hooves, white tail patch. Attack = lowered-antler charge.
# ==========================================================================================
DEER_COLORS = {"B": "earth", "D": "earth_dark", "M": "sand", "W": "paper", "A": "paper_dark",
               "K": "ink_dark", "E": "ink_black", "N": "ink_black", "S": "earth_dark"}

register(Animal(
    "deer", DEER_COLORS,
    views={
        "left": {
            "stand": [
                "...............",
                "...............",
                "..A.A..........",
                "..AAA.B........",
                ".BBBBBB........",
                ".NBEBBB........",
                ".MMBBBB........",
                "....BBBB.......",
                ".....BBBBBBBBB.",
                ".....BWBBWBBBBW",
                ".....MMBBWBBBBD",
                ".....B.D..D.B..",
                ".....B.D..D.B..",
                ".....B.D..D.B..",
                ".....K.K..K.K..",
            ],
            "step_l": {"bob": True, "legs": [
                ".B.D..D.B.", "B...D.D..B", "B...D.D..B", "K...K.K..K"]},
            "pass": {"legs": [
                ".B.D..D.B.", ".BD....DB.", ".BD....DB.", ".KK....KK."]},
            "step_r": {"bob": True, "legs": [
                ".B.D..D.B.", ".DB...BD..", "D..B.B..D.", "K..K.K..K."]},
            "wind": {"move": [(1, 2, 7, 5, 0, 1)]},
            "strike": [
                "...............",
                "...............",
                "...............",
                "...............",
                "...............",
                "...............",
                ".A.A....BB.....",
                "..AAABBBBBBBBBB",
                "...BBBBBBWBBWBB",
                "..NBEBBBBBBBBBD",
                "..MMBBMMBBWBBBD",
                ".....BBB.D..D.B",
                "....B....D..D.B",
                "...B.....D..D.B",
                "...K.....K..K.K",
            ],
            "hurt": {"swap": {"E": "S"}, "move": [(1, 2, 7, 5, 0, -1)]},
        },
        "down": {
            "stand": [
                "...............",
                "...............",
                "..A.A...A.A....",
                "...AA...AA.....",
                "..B.AA..AA.B...",
                "..BBBBBBBBBB...",
                "...BBEBBEBBD...",
                "....BBBBBBD....",
                "....BMNNMB.....",
                ".....MMMM......",
                "....BBBBBBBD...",
                "....BWBBBBWD...",
                "....BB....BB...",
                "....B......B...",
                "....K......K...",
            ],
            "step_l": {"bob": True, "legs": ["BB....BB", "B......K", "K......."]},
            "pass": {"legs": ["BB....BB", ".B....B.", ".K....K."]},
            "step_r": {"bob": True, "legs": ["BB....BB", "K......B", ".......K"]},
            "strike": [
                "...............",
                "...............",
                "...............",
                "...............",
                "...............",
                ".A.A......A.A..",
                "..AA.A..A.AA...",
                ".B.AAA..AAA.B..",
                ".BBBBBBBBBBBB..",
                "..BBBEBBBBEBD..",
                "...BBBBBBBBD...",
                "....BMMNNMB....",
                "....BB.MM.BB...",
                "....B......B...",
                "....K......K...",
            ],
            "hurt": {"shift": (0, -1), "swap": {"E": "S"}},
        },
        "up": {
            "stand": [
                "...............",
                "...............",
                "..A.A...A.A....",
                "...AA...AA.....",
                "..B.AA..AA.B...",
                "..BBBBBBBBBB...",
                "...BBBBBBBBD...",
                "....BBBBBBD....",
                ".....BBBB......",
                "....BBBBBBBD...",
                "....BWBBWBBD...",
                "....BBBWWBBD...",
                "....BB.WW.BB...",
                "....B......B...",
                "....K......K...",
            ],
            "step_l": {"bob": True, "legs": ["BB.WW.BB", "B......K", "K......."]},
            "pass": {"legs": ["BB.WW.BB", ".B....B.", ".K....K."]},
            "step_r": {"bob": True, "legs": ["BB.WW.BB", "K......B", ".......K"]},
            "wind": {"move": [(1, 2, 12, 7, 0, 1)]},
            "strike": {"bob": True, "legs": ["BB.WW.BB", "B......B", "K......K"]},
            "hurt": {"move": [(1, 2, 12, 7, 0, 1)]},
        },
    },
    leg_rect={"left": (4, 11, 10, 4), "down": (4, 12, 8, 3), "up": (4, 12, 8, 3)},
    face=[
        "...............................",
        "....A.A.............A.A........",
        "....A.A.A.........A.A.A........",
        ".....AAA...........AAA.........",
        "......AA...........AA..........",
        "......AA...........AA..........",
        "..BB..AA...........AA..BB......",
        ".BMMB.AAA.........AAA.BMMB.....",
        ".BMMMBBBBBBBBBBBBBBBBBBMMMB....",
        ".BMMMBBBBBBBBBBBBBBBBBBMMMD....",
        "..BMBBBBBBBBBBBBBBBBBBBBMD.....",
        "...BBBBBBBBBBBBBBBBBBBBBD......",
        "....BBBBBBBBBBBBBBBBBBBD.......",
        ".....BBBBEEBBBBBBBBEEBBD.......",
        ".....BBBBEEBBBBBBBBEEBBD.......",
        "......BBBBBBBBBBBBBBBBD........",
        "......BBBBBBBBBBBBBBBBD........",
        ".......BBBBBMMMMMBBBBD.........",
        ".......BBBBMMMMMMMBBBD.........",
        "........BBBMMNNNMMBBD..........",
        "........BBBMMNNNMMBBD..........",
        ".........BBMMMMMMMBD...........",
        ".........BBBMMKMMBBD...........",
        "..........BBBMMMBBD............",
        "...........BBBBBBD.............",
        "............BBBBD..............",
        "..........BBBBBBBBD............",
        ".......BBBBBBBBBBBBBBD.........",
        ".....BBBBBBWBBBBBBWBBBBD.......",
        "....BBBBBBBBBWBBWBBBBBBBD......",
        "...BBBBBWBBBBBBBBBBBBWBBBDD....",
    ],
))


# ==========================================================================================
# EGRET (백로) -- the white egret of 백로진: paper_light plumage, paper shade, gold beak with an
# ink_black tip, 1 px ink_black legs (painted after the outline, see Animal.post). Tall and
# thin: long neck, head high. Attack = peck (neck shoots forward, head low).
# ==========================================================================================
EGRET_COLORS = {"B": "paper_light", "D": "paper", "Y": "gold", "K": "ink_black", "G": "ink_black",
                "E": "ink_black", "S": "ink_light"}

register(Animal(
    "egret", EGRET_COLORS,
    views={
        "left": {
            "stand": [
                "................",
                "................",
                "......BBB.......",
                ".KYYYBEBBB......",
                "......BBBD......",
                ".......BBD......",
                ".......BBD...BB.",
                "......BBBBBBBBB.",
                ".....BBBBBBBBBD.",
                ".....BBBBBBBBDD.",
                "......BBBBBBDD..",
                ".......DDDD.....",
                "........G.G.....",
                "........G.G.....",
                ".......GG.GG....",
            ],
            "step_l": {"bob": True, "legs": [".G...G..", ".G...G..", "GG...GG."]},
            "pass": {"legs": ["..G.G...", "..G.G...", ".GG.G..."]},
            "step_r": {"bob": True, "legs": ["..G.G...", ".G...G..", "GG...GG."]},
            "wind": {"move": [(1, 2, 9, 3, 1, 0)]},
            "strike": [
                "................",
                "................",
                "................",
                "................",
                "......BBB.......",
                ".KYYYBEBBBBB.BB.",
                "......BBBB...BB.",
                "......BBBBBBBBB.",
                ".....BBBBBBBBBD.",
                ".....BBBBBBBBDD.",
                "......BBBBBBDD..",
                ".......DDDD.....",
                "........G.G.....",
                "........G.G.....",
                ".......GG.GG....",
            ],
            "hurt": {"from": "wind", "swap": {"E": "S"}},
        },
        "down": {
            "stand": [
                "................",
                "................",
                "......BBBB......",
                ".....BBBBBB.....",
                ".....BEBBEB.....",
                "......BYYB......",
                ".......BD.......",
                ".......BD.......",
                "......BBBD......",
                ".....BBBBBD.....",
                ".....BBBBBD.....",
                "......BBBDD.....",
                ".......DDD......",
                ".......G.G......",
                "......GG.GG.....",
            ],
            "step_l": {"bob": True, "legs": ["..G.G.", "....GG"]},
            "pass": {"legs": ["..G.G.", ".GG.GG"]},
            "step_r": {"bob": True, "legs": ["..G.G.", ".GG..."]},
            "wind": {"move": [(5, 2, 6, 4, 1, 0)]},
            "strike": {"move": [(5, 2, 6, 4, 0, 2)]},
            "hurt": {"shift": (0, -1), "swap": {"E": "S"}},
        },
        "up": {
            "stand": [
                "................",
                "................",
                "......BBBB......",
                ".....BBBBBB.....",
                ".....BBBBBBD....",
                "......BBBD......",
                ".......BD.......",
                ".......BD.......",
                "......BBBD......",
                ".....BBBBBD.....",
                ".....BBBBBD.....",
                "......BBBBD.....",
                ".......BBD......",
                ".......G.G......",
                "......GG.GG.....",
            ],
            "step_l": {"bob": True, "legs": ["..G.G.", "....GG"]},
            "pass": {"legs": ["..G.G.", ".GG.GG"]},
            "step_r": {"bob": True, "legs": ["..G.G.", ".GG..."]},
            "wind": {"move": [(5, 2, 7, 4, 1, 0)]},
            "strike": {"bob": True, "legs": [".G...G", "GG...G"]},
            "hurt": {"move": [(5, 2, 7, 4, 0, 1)]},
        },
    },
    leg_rect={"left": (6, 12, 8, 3), "down": (5, 13, 6, 2), "up": (5, 13, 6, 2)},
    back={"left": (0, 0), "down": (0, 0)},
    post="G",
    face=[
        "................................",
        "................................",
        "................................",
        "...........BBBBBBB..............",
        ".........BBBBBBBBBBB............",
        "........BBBBBBBBBBBBB...........",
        "........BBBBBBBBBBBBBBBB........",
        ".......BBBBBBEEBBBBBBBDBB.......",
        ".......BBBBBBEEBBBBBBBD.........",
        ".KKYYYYBBBBBBBBBBBBBBD..........",
        ".KKYYYYYYBBBBBBBBBBBBD..........",
        "..KYYYYYBBBBBBBBBBBBBD..........",
        "........BBBBBBBBBBBBD...........",
        ".........BBBBBBBBBBD............",
        "..........BBBBBBBBD.............",
        "............BBBBBD..............",
        ".............BBBBD..............",
        ".............BBBBD..............",
        ".............BBBBD..............",
        ".............BBBBD..............",
        ".............BBBBD..............",
        ".............BBBBBD.............",
        "............BBBBBBBD............",
        "..........BBBBBBBBBBBD..........",
        ".......BBBBBBBBBBBBBBBBB........",
        ".....BBBBBBBBBBBBBBBBBBBBBD.....",
        "...BBBBBBBBBBBBBBBBBBBBBBBBDD...",
        "..BBBBBBBBBBBBBBBBBBBBBBBBBBDD..",
        "..BBBBBBBBBBBBBBBBBBBBBBBBBBDDD.",
        "..BBBBBBBBBBBBBBBBBBBBBBBBBBDDD.",
        "................................",
        "................................",
    ],
))


# ==========================================================================================
# DOG (개) -- a village 진돗개: sand coat, earth_light shade, paper_light muzzle/chest, pointed
# ears, tail curled over the back. Smaller and rounder than the wolf. Attack = bite.
# ==========================================================================================
DOG_COLORS = {"B": "sand", "D": "earth_light", "K": "earth", "L": "paper_light", "E": "ink_black",
              "N": "ink_black", "S": "earth", "W": "paper_light", "T": "vermilion"}

register(Animal(
    "dog", DOG_COLORS,
    views={
        "left": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "...K.K..........",
                "...BKBK.....KK..",
                "..LBBBBB...KBBK.",
                ".NLBEBBBBBBBBK..",
                "..LLBBBBBBBBBD..",
                "...LLBBBBBBBBD..",
                "....BBD..DBBD...",
                "....BBD..DBBD...",
                "....BBD..DBBD...",
                "....DD...DDD....",
            ],
            "step_l": {"bob": True, "legs": [
                ".BBD..DBBD", "BB.D..D.BD", "BB.D..D.BD", "DD.D..D.DD"]},
            "pass": {"legs": [
                ".BBD..DBBD", ".BBD..DBBD", "..BD..DB..", "..D....D.."]},
            "step_r": {"bob": True, "legs": [
                ".BBD..DBBD", ".DBB.BB.D.", "D..BB.BB.D", "D..DD.DD.D"]},
            "wind": {"move": [(1, 5, 8, 5, 0, 1)]},
            "strike": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "...K.K..........",
                "...BKBK.....KK..",
                "..LBBBBB...KBBK.",
                ".NLBEBBBBBBBBK..",
                ".WW.BBBBBBBBBD..",
                ".LLLBBBBBBBBBD..",
                "...BBD..DBBD....",
                "..BB.D..D.BB....",
                ".BB..D..D..BB...",
                ".DD..D..D..DD...",
            ],
            "hurt": {"move": [(1, 5, 8, 4, 0, -1)], "swap": {"E": "S"}},
        },
        "down": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "...KK....KK.....",
                "...BK....KB.....",
                "...BBBBBBBB.....",
                "..BBEBBBBEBD....",
                "..BBBLLLLBBD....",
                "...BBLNNLBD.....",
                "....BLLLLD......",
                "...BBLLLLBBD....",
                "...BB....BBD....",
                "...DD....DDD....",
            ],
            "step_l": {"bob": True, "legs": ["BBLLLLBBD", "BB....DDD", "DD......."]},
            "pass": {"legs": ["BBLLLLBBD", ".BB..BB..", ".DD..DD.."]},
            "step_r": {"bob": True, "legs": ["BBLLLLBBD", "DD....BBD", "......DDD"]},
            "strike": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "................",
                "...KK....KK.....",
                "...BK....KB.....",
                "...BBBBBBBB.....",
                "..BBEBBBBEBD....",
                "..BBBLLLLBBD....",
                "...BBLNNLBD.....",
                "...BBWTTWBD.....",
                "..BBBLLLLBBB....",
                "..DD......DDD...",
            ],
            "hurt": {"shift": (0, -1), "swap": {"E": "S"}},
        },
        "up": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "...KK....KK.....",
                "...BB....BB.....",
                "...BBBBBBBB.....",
                "..BBBBBBBBBD....",
                "..BBBBBBBBBD....",
                "...BBBBBBBBD....",
                "....BBLLBBD.....",
                "...BBBLLBBBD....",
                "...BB....BBD....",
                "...DD....DDD....",
            ],
            "step_l": {"bob": True, "legs": ["BBBLLBBBD", "BB....DDD", "DD......."]},
            "pass": {"legs": ["BBBLLBBBD", ".BB..BB..", ".DD..DD.."]},
            "step_r": {"bob": True, "legs": ["BBBLLBBBD", "DD....BBD", "......DDD"]},
            "wind": {"move": [(2, 5, 10, 7, 0, 1)]},
            "strike": {"bob": True, "legs": ["BBBLLBBBD", "BB....BBD", "DD....DDD"]},
            "hurt": {"move": [(2, 5, 10, 7, 0, 1)]},
        },
    },
    leg_rect={"left": (3, 11, 10, 4), "down": (3, 12, 9, 3), "up": (3, 12, 9, 3)},
    back={"left": (0, 0)},
    face=[
        "................................",
        "................................",
        "................................",
        ".....K...............K..........",
        "....KKK.............KKK.........",
        "....KKKK...........KKKK.........",
        "....KBKKK.........KKKBK.........",
        "....KBBKKK.......KKKBBK.........",
        "....KBBBKKBBBBBBBKKBBBK.........",
        "....KBBBBBBBBBBBBBBBBBK.........",
        ".....KBBBBBBBBBBBBBBBK..........",
        "......BBBBBBBBBBBBBBBBD.........",
        ".....BBBBBBBBBBBBBBBBBBD........",
        "....BBBBBEEBBBBBBBEEBBBBD.......",
        "....BBBBBEEBBBBBBBEEBBBBD.......",
        "....BBBBBBBBBLLLLBBBBBBBD.......",
        "....BBBBBBBBLLLLLLBBBBBBD.......",
        "....BBBBBBBLLLNNLLLBBBBBD.......",
        ".....BBBBBBLLNNNNLLBBBBD........",
        ".....BBBBBBLLLNNLLLBBBBD........",
        "......BBBBBLLLKKLLLBBBD.........",
        ".......BBBBLLKLLKLLBBD..........",
        "........BBBLLLTTLLBBD...........",
        ".........BBBLLTTLBBD............",
        "...........BBBBBBBD.............",
        "........BBBBBBBBBBBBBBD.........",
        ".....BBBBBBBBBBBBBBBBBBBBD......",
        "...BBBBBBBBBLLLLLLBBBBBBBBBDD...",
        "..BBBBBBBBBLLLLLLLLBBBBBBBBBDDD.",
        "..BBBBBBBBBLLLLLLLLBBBBBBBBBDDD.",
        "................................",
        "................................",
    ],
))


# ==========================================================================================
# CHICKEN (닭) -- a yard rooster: paper_light body, paper shade, vermilion comb and wattle, gold
# beak, ink_dark tail with a jade_dark sheen, 1 px earth legs (post-outline). Attack = peck.
# ==========================================================================================
CHICKEN_COLORS = {"B": "paper_light", "D": "paper", "K": "ink_dark", "J": "jade_dark", "Y": "gold",
                  "T": "vermilion", "E": "ink_black", "S": "ink_light", "G": "earth"}

register(Animal(
    "chicken", CHICKEN_COLORS,
    views={
        "left": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "...T.T..........",
                "...TTT..........",
                ".YYBEBB.....KK..",
                "..TBBBB....KJK..",
                "...BBDDDBBKJKK..",
                "...BBBDDBBBKK...",
                "....BBBBBBDD....",
                ".....DDDDD......",
                "......G.G.......",
                ".....GG.GG......",
            ],
            "step_l": {"bob": True, "legs": [".G...G.", "GG...GG"]},
            "pass": {"legs": ["..G.G..", ".GG.G.."]},
            "step_r": {"bob": True, "legs": ["..G.G..", ".G...GG"]},
            "wind": {"move": [(1, 5, 6, 4, 1, 0)]},
            "strike": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "................",
                "............KK..",
                "...........KJK..",
                "....T.T...KJKK..",
                "....TTTBBBBKK...",
                "...BBBBBDDDB....",
                "..YBEBBBBDD.....",
                ".Y.TBBDDDD......",
                "......G.G.......",
                ".....GG.GG......",
            ],
            "hurt": {"from": "wind", "swap": {"E": "S"}},
        },
        "down": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "......T.T.......",
                "......TTT.......",
                ".....BEBEB......",
                "......BYB.......",
                "......BTB.......",
                "....BBBBBBD.....",
                "...BBBBBBBBD....",
                "....BBBBBDD.....",
                "......G.G.......",
                ".....GG.GG......",
            ],
            "step_l": {"bob": True, "legs": ["..G.G.", "....GG"]},
            "pass": {"legs": ["..G.G.", ".GG.GG"]},
            "step_r": {"bob": True, "legs": ["..G.G.", ".GG..."]},
            "wind": {"move": [(5, 5, 5, 5, 1, 0)]},
            "strike": {"move": [(5, 5, 5, 5, 0, 2)]},
            "hurt": {"shift": (0, -1), "swap": {"E": "S"}},
        },
        "up": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "......T.T.......",
                "......TTT.......",
                ".....BBBBB......",
                "......BBB.......",
                "......BBD.......",
                "....BBKJKBD.....",
                "...BBBKJKBBD....",
                "....BBBKBDD.....",
                "......G.G.......",
                ".....GG.GG......",
            ],
            "step_l": {"bob": True, "legs": ["..G.G.", "....GG"]},
            "pass": {"legs": ["..G.G.", ".GG.GG"]},
            "step_r": {"bob": True, "legs": ["..G.G.", ".GG..."]},
            "wind": {"move": [(5, 5, 5, 5, 1, 0)]},
            "strike": {"bob": True, "legs": [".G...G", "GG...G"]},
            "hurt": {"move": [(5, 5, 5, 5, 0, 1)]},
        },
    },
    leg_rect={"left": (4, 13, 7, 2), "down": (5, 13, 6, 2), "up": (5, 13, 6, 2)},
    back={"left": (0, 0), "down": (0, 0)},
    post="G",
    face=[
        "................................",
        "................................",
        "...........T..T..T..............",
        "..........TTT.TT.TT.............",
        "..........TTTTTTTTTT............",
        "...........TTTTTTTTT............",
        "...........TTTTTTTT.............",
        "..........BBBBBBBBBBB...........",
        ".........BBBBBBBBBBBBB..........",
        "........BBBBBBBBBBBBBBB.........",
        ".......BBBBBEEBBBBBBBBBD........",
        "......BBBBBBEEBBBBBBBBBD........",
        "...YYYBBBBBBBBBBBBBBBBBD........",
        ".YYYYYYYBBBBBBBBBBBBBBD.........",
        ".YYYYYYYYBBBBBBBBBBBBBD.........",
        "..YYYYYYBBBBBBBBBBBBBD..........",
        "...YYYYTTBBBBBBBBBBBBD..........",
        "......TTTTBBBBBBBBBBD...........",
        "......TTTTBBBBBBBBBD............",
        ".......TTTBBBBBBBBBD............",
        "........TBBBBBBBBBD.............",
        ".........BBBBBBBBBD.............",
        "..........BBBBBBBBD.............",
        "..........BBBBBBBBBD............",
        "..........BBBBBBBBBBD...........",
        ".........BBBBBBBBBBBBD..........",
        ".......BBBBBBBBBBBBBBBBDD.......",
        ".....BBBBBBBBBBBBBBBBBBBDDD.....",
        "...BBBBBBBBBBBDDDBBBBBBBBDDDD...",
        "..BBBBBBBBBBBDDDDDBBBBBBBBDDDD..",
        "................................",
        "................................",
    ],
))


# ==========================================================================================
# BOAR (멧돼지) -- heavy wedge: earth coat, earth_dark shade, earth_light flank, ink_dark bristle
# ridge down the back, sand snout, paper_light tusks, ink_dark hooves. Attack = charge (head
# lowered, tusks forward, legs stretched).
# ==========================================================================================
BOAR_COLORS = {"B": "earth", "D": "earth_dark", "K": "ink_dark", "L": "earth_light", "M": "sand",
               "W": "paper_light", "E": "ink_black", "N": "ink_black", "S": "earth_dark"}

register(Animal(
    "boar", BOAR_COLORS,
    views={
        "left": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                ".....K.KKKKKKK..",
                "....BKKBBBBBBBD.",
                "...BBBBBLLBBBBK.",
                "..BBBEBBBBBBBBD.",
                ".MMBBBBBBBBBBDD.",
                ".NMBBBBBBBBBBDD.",
                ".WWBBBBBBBBBBDD.",
                "...DDBBBBBBBDD..",
                "...BBD..DBBD....",
                "...BBD..DBBD....",
                "...KK...KKK.....",
            ],
            "step_l": {"bob": True, "legs": [
                ".BBD..DBBD", "BB.D..D.BD", "KK.K..K.KK"]},
            "pass": {"legs": [
                ".BBD..DBBD", "..BD..DB..", "..KK..KK.."]},
            "step_r": {"bob": True, "legs": [
                ".BBD..DBBD", ".DBB.BB.D.", "K..KK.KK.K"]},
            "wind": {"move": [(1, 4, 8, 7, 0, 1)]},
            "strike": [
                "................",
                "................",
                "................",
                "................",
                ".......KKKKKKK..",
                "......BBBBBBBBD.",
                ".....KKBBLLBBBK.",
                "....BBBBBBBBBBD.",
                "...BBBEBBBBBBDD.",
                "..MBBBBBBBBBBDD.",
                ".NMBBBBBBBBBBDD.",
                ".WWDDBBBBBBBDD..",
                "..BBD...DBBD....",
                ".BB.D...D.BBD...",
                ".KK.K...K.KKK...",
            ],
            "hurt": {"move": [(1, 4, 8, 7, 0, -1)], "swap": {"E": "S"}},
        },
        "down": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                ".....KKKK.......",
                "...KBBBBBBK.....",
                "..BBBBBBBBBBD...",
                "..BBEBBBBBEBD...",
                "..BBBBBBBBBBD...",
                "...BBMMMMMBBD...",
                "...BWMNMNMWBD...",
                "...BBBMMMBBBD...",
                "...BBD...DBBD...",
                "...BBD...DBBD...",
                "...KKK...KKKK...",
            ],
            "step_l": {"bob": True, "legs": ["BBD...DBBD", "BBD...DDDD", "KKK......."]},
            "pass": {"legs": ["BBD...DBBD", ".BBD.DBBD.", ".KKK.KKKK."]},
            "step_r": {"bob": True, "legs": ["BBD...DBBD", "DDD...DBBD", ".......KKK"]},
            "strike": [
                "................",
                "................",
                "................",
                "................",
                "................",
                ".....KKKK.......",
                "...KBBBBBBK.....",
                "..BBBBBBBBBBD...",
                "..BBEBBBBBEBD...",
                "..BBBBBBBBBBD...",
                "..BBBMMMMMBBBD..",
                "..BWWMNMNMWWBD..",
                "..BBBBMMMBBBBD..",
                ".BBD.......DBBD.",
                ".KKK.......KKKK.",
            ],
            "hurt": {"shift": (0, -1), "swap": {"E": "S"}},
        },
        "up": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                ".....KKKK.......",
                "...KBBKKBBK.....",
                "..BBBBKKBBBBD...",
                "..BBBBKKBBBBD...",
                "..BBBBKKBBBBD...",
                "...BBBKKBBBD....",
                "...BBBBKBBBD....",
                "...BBBBKKBBBD...",
                "...BBD.K.DBBD...",
                "...BBD...DBBD...",
                "...KKK...KKKK...",
            ],
            "step_l": {"bob": True, "legs": ["BBD.K.DBBD", "BBD...DDDD", "KKK......."]},
            "pass": {"legs": ["BBD.K.DBBD", ".BBD.DBBD.", ".KKK.KKKK."]},
            "step_r": {"bob": True, "legs": ["BBD.K.DBBD", "DDD...DBBD", ".......KKK"]},
            "wind": {"move": [(2, 4, 11, 8, 0, 1)]},
            "strike": {"bob": True, "legs": ["BBD.K.DBBD", "BBD...DBBD", "KKK...KKKK"]},
            "hurt": {"move": [(2, 4, 11, 8, 0, 1)]},
        },
    },
    leg_rect={"left": (3, 12, 10, 3), "down": (3, 12, 10, 3), "up": (3, 12, 10, 3)},
    back={"left": (0, 0)},
    face=[
        "................................",
        "................................",
        "...............KK...............",
        "..........KKKKKKKKKKK...........",
        "........KKBBBKKKKBBBKK..........",
        "......KKBBBBBBKKBBBBBBKK........",
        ".....KBBBBBBBBBBBBBBBBBBK.......",
        "....KBBBBBBBBBBBBBBBBBBBBK......",
        "....BBBBBBBBBBBBBBBBBBBBBBD.....",
        "....BBBBBBBBBBBBBBBBBBBBBBD.....",
        "...BBBBBBBBBBBBBBBBBBBBBBBBD....",
        "...BBBBBBEEBBBBBBBBBBEEBBBBD....",
        "...BBBBBBEEBBBBBBBBBBEEBBBBD....",
        "...LBBBBBBBBBBBBBBBBBBBBBBBD....",
        "...LBBBBBBBBBBBBBBBBBBBBBBBD....",
        "...LBBBBBBBBBBBBBBBBBBBBBBBD....",
        "....BBBBBBBBMMMMMMMMBBBBBBD.....",
        "....BBBBBBBMMMMMMMMMMBBBBBD.....",
        "....BBBBBBMMMMMMMMMMMMBBBBD.....",
        ".....BBBBBMMMNNMMNNMMMBBBD......",
        ".....BBBBWMMMNNMMNNMMMWBBD......",
        "......BBBWWMMMMMMMMMMWWBD.......",
        ".......BBWWMMMMMMMMMMWWD........",
        "........BBBBMMMMMMMMBBD.........",
        "..........BBBBBBBBBBD...........",
        ".......BBBBBBBBBBBBBBBBBD.......",
        "....BBBBBBBBBBBBBBBBBBBBBBDD....",
        "..BBBBBBBBBBBBBBBBBBBBBBBBBBDD..",
        "..BBBBBBBBBBBBBBBBBBBBBBBBBBDDD.",
        "..BBBBBBBBBBBBBBBBBBBBBBBBBBDDD.",
        "................................",
        "................................",
    ],
))


# ==========================================================================================
# MONKEY (원숭이) -- upright macaque: earth_light fur, earth shade, skin face, sand belly,
# earth_dark hands/feet, long tail curling up behind. Attack = screeching pounce (arms out,
# teeth bared).
# ==========================================================================================
MONKEY_COLORS = {"B": "earth_light", "D": "earth", "K": "earth_dark", "M": "skin", "A": "sand",
                 "E": "ink_black", "N": "ink_black", "S": "earth_dark", "W": "paper_light"}

register(Animal(
    "monkey", MONKEY_COLORS,
    views={
        "left": {
            "stand": [
                "................",
                "................",
                "................",
                ".....BBBBB......",
                "....BBBBBBB.....",
                "...MMBBBBBBB....",
                "..MEMMBBBBB.....",
                "..NMMMBBBB...K..",
                "...MMMBBB....B..",
                ".....BBBBB..B...",
                "....BBAABBBB....",
                "....BBAABBBD....",
                "....KK.BBBD.....",
                ".....BBB.BB.....",
                ".....KKK.KK.....",
            ],
            "step_l": {"bob": True, "legs": ["KK.BBBD", "BBB...B", "KKK...K"]},
            "pass": {"legs": ["KK.BBBD", "..BBBB.", "..KKKK."]},
            "step_r": {"bob": True, "legs": ["KK.BBBD", "..B.BBB", "..K.KKK"]},
            "wind": {"move": [(2, 3, 10, 6, 1, 1)]},
            "strike": [
                "................",
                "................",
                "................",
                "................",
                ".....BBBBB......",
                "....BBBBBBB.....",
                "...MMBBBBBBB....",
                "..MEMMBBBBB.....",
                "..NMMMBBBB...K..",
                "..WWMMBBB....B..",
                ".KKBBBBBBBB.B...",
                "....BBAABBBB....",
                ".....BBAABBD....",
                "....BBB..BBB....",
                "....KKK..KKK....",
            ],
            "hurt": {"move": [(2, 3, 10, 6, 1, -1)], "swap": {"E": "S"}},
        },
        "down": {
            "stand": [
                "................",
                "................",
                "................",
                ".....BBBBBB.....",
                "....BBBBBBBB....",
                "...BBMMMMMMBB...",
                "...BMMEMMEMMB...",
                "....BMMNNMMB....",
                ".....MMMMMM.....",
                "....BBBBBBBB....",
                "...BBBAAAABBB...",
                "...BBBAAAABBB...",
                "...KK.BBBB.KK...",
                ".....BB..BB.....",
                ".....KK..KK.....",
            ],
            "step_l": {"bob": True, "legs": ["BB..BB", "KK...."]},
            "pass": {"legs": ["BB..BB", "KK..KK"]},
            "step_r": {"bob": True, "legs": ["BB..BB", "....KK"]},
            "strike": [
                "................",
                "................",
                "................",
                "................",
                ".....BBBBBB.....",
                "....BBBBBBBB....",
                "...BBMMMMMMBB...",
                "...BMMEMMEMMB...",
                "....BMMNNMMB....",
                ".....MWWWWM.....",
                "...BBBBBBBBBB...",
                "..BBBAAAAAABBB..",
                "..KK.BBBBBB.KK..",
                ".....BB..BB.....",
                ".....KK..KK.....",
            ],
            "hurt": {"shift": (0, -1), "swap": {"E": "S"}},
        },
        "up": {
            "stand": [
                "................",
                "................",
                "................",
                ".....BBBBBB.....",
                "....BBBBBBBB....",
                "...BBBBBBBBBB...",
                "...BBBBBBBBBB...",
                "....BBBBBBBB....",
                ".....BBBBBB..K..",
                "....BBBBBBBB.K..",
                "...BBBBBBBBBBK..",
                "...BBBBBBBBBK...",
                "...KK.BBBB.KK...",
                ".....BB..BB.....",
                ".....KK..KK.....",
            ],
            "step_l": {"bob": True, "legs": ["BB..BB", "KK...."]},
            "pass": {"legs": ["BB..BB", "KK..KK"]},
            "step_r": {"bob": True, "legs": ["BB..BB", "....KK"]},
            "wind": {"move": [(3, 3, 11, 9, 0, 1)]},
            "strike": {"bob": True, "legs": ["BB..BB", "KK..KK"],
                       "rect": [(2, 10, ["BBBBBBBBBBB", "BBBBBBBBBB.", "KK.BBBB.KK."])]},
            "hurt": {"move": [(3, 3, 11, 9, 0, 1)]},
        },
    },
    leg_rect={"left": (4, 12, 7, 3), "down": (5, 13, 6, 2), "up": (5, 13, 6, 2)},
    back={"left": (0, 0)},
    face=[
        "................................",
        "................................",
        "................................",
        "..........BBBBBBBBBBB...........",
        "........BBBBBBBBBBBBBBB.........",
        ".......BBBBBBBBBBBBBBBBB........",
        "......BBBBBBBBBBBBBBBBBBB.......",
        ".....BBBBBBBMMMMMMBBBBBBBD......",
        "....BBBBBBMMMMMMMMMMBBBBBBD.....",
        "...BBBMBBMMMMMMMMMMMMBBMBBBD....",
        "...BMMMBMMMMMMMMMMMMMMBMMMBD....",
        "...BMMMMMMMMMMMMMMMMMMMMMMBD....",
        "...BMMMBMMMEEMMMMMMEEMMMBMMBD...",
        "....BMBMMMMEEMMMMMMEEMMMMBMD....",
        ".....BMMMMMMMMMMMMMMMMMMMMD.....",
        "......MMMMMMMMMMMMMMMMMMMM......",
        "......MMMMMMMMMNNMMMMMMMMM......",
        "......MMMMMMMMNMMNMMMMMMMM......",
        ".......MMMMMMMMMMMMMMMMMM.......",
        ".......MMMMMMMKKKKKKMMMMM.......",
        "........MMMMMMMMMMMMMMMM........",
        ".........MMMMMMMMMMMMMM.........",
        "..........MMMMMMMMMMMM..........",
        "............BBBBBBBB............",
        ".........BBBBBBBBBBBBBB.........",
        "......BBBBBBBBBBBBBBBBBBBB......",
        "....BBBBBBBBBBAAAAAABBBBBBBD....",
        "...BBBBBBBBBAAAAAAAAAABBBBBBDD..",
        "..BBBBBBBBBBAAAAAAAAAABBBBBBDDD.",
        "..BBBBBBBBBBAAAAAAAAAABBBBBBDDD.",
        "................................",
        "................................",
    ],
))


# ==========================================================================================
# SNAKE (뱀) -- a green 청사: moss body, moss_dark shade, moss_pale belly, ink_dark diamond
# marks, gold eyes. The body is a procedural wave (traveling phase = slither), the head is a
# hand-drawn overlay. Attack = strike (head shoots forward, fangs + tongue).
# ==========================================================================================
SNAKE_COLORS = {"B": "moss", "D": "moss_dark", "L": "moss_pale", "K": "ink_dark", "E": "gold",
                "S": "ink", "W": "paper_light", "T": "vermilion"}


def _snake_side(phase: float, head_dx: int = 0, head_dy: int = 0, mouth: bool = False,
                flat: bool = False) -> List[str]:
    """Side view (facing left): head at cols 2..6 rows 8..10, body wave along the ground."""
    import math
    g = _grid([])
    x0 = 6
    for x in range(x0, 15):
        if flat:
            y = 13
        else:
            y = 12 + int(round(math.sin(2 * math.pi * (x - x0) / 6.0 + phase)))
        if x >= 13:                       # tapering tail: 1 px
            g[min(y + 1, 14)][x] = "D"
            continue
        g[y][x] = "K" if (x - x0) % 3 == 1 else "B"
        g[y + 1][x] = "L" if y + 1 == 14 else "D"
    # neck: join the head (chin at row 10, col 6) to the body column x0
    top = min(yy for yy in range(16) if g[yy][x0] != ".")
    for yy in range(11, top):
        g[yy][x0] = "B"
        g[yy][x0 - 1] = "D"
    head = [
        "...BBB..",
        "..BEBBB.",
        "..DDBBB.",
    ]
    if mouth:
        head = [
            "...BBB..",
            ".BBEBBB.",
            ".WW.BBB.",
            ".T.DD...",
        ]
    _paste(g, head_dx, 8 + head_dy, head)
    return _rows_of(g)


def _snake_top(phase: float, facing_down: bool, head_dy: int = 0, mouth: bool = False) -> List[str]:
    """Top-down views: body winds vertically, head at the bottom (down) or top (up)."""
    import math
    g = _grid([])
    if facing_down:
        body_rows = range(2, 11)           # tail at the top, neck at row 10
        tail_rows = (2, 3)
    else:
        body_rows = range(5, 14)           # neck at row 5, tail at the bottom
        tail_rows = (12, 13)
    for y in body_rows:
        x = 8 + int(round(1.5 * math.sin(2 * math.pi * (y - 2) / 7.0 + phase)))
        if y in tail_rows:
            g[y][x] = "D"
            continue
        g[y][x] = "K" if (y % 3 == 0) else "B"
        g[y][x + 1] = "D"
    if facing_down:
        head = [
            "..BBBB..",
            ".BEBBEB.",
            ".BBBBBB.",
            "..DDDD..",
        ]
        if mouth:
            head = [
                "..BBBB..",
                ".BEBBEB.",
                ".BWBBWB.",
                "..DTTD..",
            ]
        _paste(g, 4, 10 + head_dy, head)
    else:
        head = [
            "..BBBB..",
            ".BBBBBB.",
            ".BBBBBBD",
            "..BBBBD.",
        ]
        _paste(g, 4, 2 + head_dy, head)
    return _rows_of(g)


_PH = [0.0, 1.5707963, 3.1415927, 4.712389]
register(Animal(
    "snake", SNAKE_COLORS,
    views={
        "left": {
            "stand": _snake_side(_PH[0]),
            "step_l": _snake_side(_PH[1]),
            "pass": _snake_side(_PH[2]),
            "step_r": _snake_side(_PH[3]),
            "wind": _snake_side(_PH[0], head_dx=1, head_dy=-1),
            "strike": _snake_side(_PH[0], head_dx=0, head_dy=1, mouth=True, flat=True),
            "recover": _snake_side(_PH[2]),
            "hurt": {"from": "wind", "swap": {"E": "S"}},
        },
        "down": {
            "stand": _snake_top(_PH[0], True),
            "step_l": _snake_top(_PH[1], True),
            "pass": _snake_top(_PH[2], True),
            "step_r": _snake_top(_PH[3], True),
            "wind": _snake_top(_PH[0], True, head_dy=-1),
            "strike": _snake_top(_PH[0], True, head_dy=1, mouth=True),
            "recover": _snake_top(_PH[2], True),
            "hurt": {"from": "wind", "swap": {"E": "S"}},
        },
        "up": {
            "stand": _snake_top(_PH[0], False),
            "step_l": _snake_top(_PH[1], False),
            "pass": _snake_top(_PH[2], False),
            "step_r": _snake_top(_PH[3], False),
            "wind": _snake_top(_PH[0], False, head_dy=1),
            "strike": _snake_top(_PH[0], False, head_dy=-1),
            "recover": _snake_top(_PH[2], False),
            "hurt": {"from": "wind"},
        },
    },
    leg_rect={"left": (0, 0, 1, 1), "down": (0, 0, 1, 1), "up": (0, 0, 1, 1)},
    back={"left": (0, 0), "down": (0, 0)},
    face=[
        "................................",
        "................................",
        "................................",
        "................................",
        "..........BBBBBBBBBBB...........",
        "........BBBBBBBBBBBBBBB.........",
        ".......BBBBKBBBBBBKBBBBB........",
        "......BBBBKKKBBBBKKKBBBBB.......",
        ".....BBBBBBKBBBBBBKBBBBBBD......",
        ".....BBBBBBBBBBBBBBBBBBBBD......",
        "....BBBBBBBBBBBBBBBBBBBBBBD.....",
        "....BBBBEEBBBBBBBBBBEEBBBBD.....",
        "....BBBBEKBBBBBBBBBBKEBBBBD.....",
        "....BBBBBBBBBBBBBBBBBBBBBBD.....",
        ".....BBBBBBBBBBBBBBBBBBBBD......",
        ".....BBBBBBBBKBBBBKBBBBBBD......",
        "......BBBBBBBBBBBBBBBBBBD.......",
        ".......BBBBBBBBBBBBBBBBD........",
        "........BBBBBBBBBBBBBBD.........",
        ".........LLLLLLLLLLLLD..........",
        "..........LLLTLLTLLLD...........",
        "..............TTTT..............",
        "...............TT...............",
        "...............T.T..............",
        "..........BBBBBBBBBBBB..........",
        ".......BBBBBKBBBBBBKBBBBB.......",
        ".....BBBBBBKKKBBBBKKKBBBBBD.....",
        "....BBBBBBBBKBBBBBBKBBBBBBBD....",
        "...LLLLLLLLLLLLLLLLLLLLLLLLLD...",
        "...LLLLLLLLLLLLLLLLLLLLLLLLLD...",
        "................................",
        "................................",
    ],
))


# ==========================================================================================
# FOX (여우) -- earth_light coat with a vermilion_light crown/saddle/tail, paper_light muzzle,
# chest and tail tip, ink_dark socks and ear tips, big bushy tail. Attack = pounce-bite.
# ==========================================================================================
FOX_COLORS = {"B": "earth_light", "A": "vermilion_light", "D": "earth", "H": "sand", "L": "paper_light",
              "K": "ink_dark", "E": "ink_black", "N": "ink_black", "S": "earth", "W": "paper_light",
              "T": "vermilion"}

register(Animal(
    "fox", FOX_COLORS,
    views={
        "left": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "...K.K..........",
                "...AAAA.........",
                "..LBEBAAAAAA....",
                ".NLBBBBBBBBAAAA.",
                "..LLBBBBBBBBAAD.",
                "...LLBBBBBBDALL.",
                "....BBD..DBB.LL.",
                "....BBD..DBB....",
                "....KK...KK.....",
                "....KK...KK.....",
            ],
            "step_l": {"bob": True, "legs": [
                ".BBD..DBB.", "BB.D..D.BB", "KK.K..K.KK", "KK.K..K.KK"]},
            "pass": {"legs": [
                ".BBD..DBB.", ".BBD..DBB.", "..KK..KK..", "..K....K.."]},
            "step_r": {"bob": True, "legs": [
                ".BBD..DBB.", ".DBB.BB.D.", "K..KK.KK.K", "K..KK.KK.K"]},
            "wind": {"move": [(1, 5, 7, 6, 0, 1)]},
            "strike": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "................",
                "...K.K..........",
                "...AAAA....AAAA.",
                "..LBEBAAAAAAAAA.",
                ".NLBBBBBBBBBBAD.",
                ".WW.BBBBBBBBALL.",
                ".LL..BBD..DBBLL.",
                "....BB.D..D.BB..",
                "...KK..K..K..KK.",
                "...KK..K..K..KK.",
            ],
            "hurt": {"move": [(1, 5, 7, 6, 0, -1)], "swap": {"E": "S"}},
        },
        "down": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "...K.....K......",
                "...AA...AA......",
                "...AAAAAAA......",
                "..BBEBBBEBBD....",
                "..BBBLLLBBBD....",
                "...BBLNLBBD.....",
                "....BLLLBD......",
                "...BHLLLLHBD....",
                "...KK....KKD....",
                "...KK....KK.....",
            ],
            "step_l": {"bob": True, "legs": ["KK....KKD", "KK......."]},
            "pass": {"legs": [".KK..KK..", ".KK..KK.."]},
            "step_r": {"bob": True, "legs": ["KK....KKD", "......KK."]},
            "strike": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "................",
                "...K.....K......",
                "...AA...AA......",
                "...AAAAAAA......",
                "..BBEBBBEBBD....",
                "..BBBLLLBBBD....",
                "...BBLNLBBD.....",
                "...BBWTTWBD.....",
                "..BHHLLLLHHB....",
                "..KK......KK....",
            ],
            "hurt": {"shift": (0, -1), "swap": {"E": "S"}},
        },
        "up": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "...K.....K......",
                "...AA...AA......",
                "...AAAAAAA......",
                "..AAAAAAAAAD....",
                "..BAAAAAAABD....",
                "...BAAAAAABD....",
                "....BAAAABD.....",
                "...HBBAABBHD....",
                "...KK.AA.KKD....",
                "...KK.LL.KK.....",
            ],
            "step_l": {"bob": True, "legs": ["KK.AA.KKD", "KK.LL...."]},
            "pass": {"legs": [".KKAAKK..", ".KKLLKK.."]},
            "step_r": {"bob": True, "legs": ["KK.AA.KKD", "....LL.KK"]},
            "wind": {"move": [(2, 5, 10, 8, 0, 1)]},
            "strike": {"bob": True, "legs": ["KK.AA.KKD", "KK.LL.KK."]},
            "hurt": {"move": [(2, 5, 10, 8, 0, 1)]},
        },
    },
    leg_rect={"left": (3, 11, 10, 4), "down": (3, 13, 9, 2), "up": (3, 13, 9, 2)},
    back={"left": (0, 0)},
    face=[
        "................................",
        "................................",
        "....K.....................K.....",
        "...KKK...................KKK....",
        "...KAKK.................KKAK....",
        "...KAAKK...............KKAAK....",
        "...KAAAKK.............KKAAAK....",
        "...KAAAAKK...........KKAAAAK....",
        "...KAAAAAAAAAAAAAAAAAAAAAAAK....",
        "....KAAAAAAAAAAAAAAAAAAAAAK.....",
        ".....AAAAAAAAAAAAAAAAAAAAAD.....",
        ".....BAAAAAAAAAAAAAAAAAAABD.....",
        "....BBBBAAAAAAAAAAAAAAABBBBD....",
        "....BBBBEEBBBBBBBBBBBEEBBBBD....",
        "....BBBBBEEBBBBBBBBBEEBBBBBD....",
        "....BBBBBBBBBBLLLLBBBBBBBBBD....",
        ".....BBBBBBBBLLLLLLBBBBBBBD.....",
        ".....BBBBBBBLLLNNLLLBBBBBBD.....",
        "......BBBBBBLLNNNNLLBBBBBD......",
        "......BBBBBBLLLNNLLLBBBBBD......",
        ".......BBBBBLLLKKLLLBBBBD.......",
        "........BBBBLLKLLKLLBBBD........",
        ".........BBBBLLLLLLBBBD.........",
        "..........BBBBLLLLBBBD..........",
        "............BBBBBBBD............",
        ".........AAAAAAAAAAAAAD.........",
        "......AAAAAAAAAAAAAAAAAAAD......",
        "....BBBAAAAALLLLLLLLAAAAABBBD...",
        "...BBBBBBBLLLLLLLLLLLLBBBBBBDD..",
        "..BBBBBBBBLLLLLLLLLLLLBBBBBBDDD.",
        "................................",
        "................................",
    ],
))


# ==========================================================================================
# HORSE (말) -- fills the cell: earth coat, earth_dark shade, earth_light highlight, ink_dark
# mane/tail/hooves, paper_light blaze and muzzle. Attack = rears and strikes with the front
# hooves toward the facing direction.
# ==========================================================================================
HORSE_COLORS = {"B": "earth", "D": "earth_dark", "L": "earth_light", "K": "ink_dark", "M": "paper_light",
                "E": "ink_black", "N": "ink_black", "S": "earth_dark"}

register(Animal(
    "horse", HORSE_COLORS,
    views={
        "left": {
            "stand": [
                "................",
                "................",
                "...K............",
                "..BBKK..........",
                ".LBBEBKK........",
                ".MBBBBBKK.......",
                ".NMBBBBBKK......",
                "..DDBBBBBKK..K..",
                "....BBBBBBBBBBK.",
                "....LBBBBBBBBBK.",
                "....BBBBBBBBBDK.",
                "....BBD...DBBDK.",
                "....BBD...DBB.K.",
                "....BBD...DBB...",
                "....KK....KKK...",
            ],
            "step_l": {"bob": True, "legs": [
                ".BBD...DBBD", "BB.D...D.BB", "BB.D...D.BB", "KK.K...K.KK"]},
            "pass": {"legs": [
                ".BBD...DBBD", ".BBD...DBB.", "..BD...DB..", "..KK...KK.."]},
            "step_r": {"bob": True, "legs": [
                ".BBD...DBBD", ".DBB..BB.D.", "D..BB.BB..D", "K..KK.KK..K"]},
            "wind": {"move": [(1, 2, 10, 6, 0, 1)]},
            "strike": [
                "................",
                "...K............",
                "..BBKK..........",
                ".LBBEBKK........",
                ".MBBBBBKK.......",
                ".NMBBBBBKK......",
                "..DDBBBBBKK.....",
                ".....BBBBBKK.K..",
                "..BB.BBBBBBBBBK.",
                ".KK.BBBBBBBBBBK.",
                "..BB.BBBBBBBBDK.",
                ".KK....BBD.DBBD.",
                ".......BBD.DBB..",
                ".......BBD.DBB..",
                ".......KK..KKK..",
            ],
            "hurt": {"move": [(1, 2, 10, 6, 1, 0)], "swap": {"E": "S"}},
        },
        "down": {
            "stand": [
                "................",
                ".....K...K......",
                ".....KKKKK......",
                "....BBMMMBB.....",
                "....BEBMBEB.....",
                ".....BBMBB......",
                ".....BBMBB......",
                ".....MNNM.......",
                "....BBBBBBBD....",
                "...BBBBBBBBBD...",
                "...BBBBBBBBBD...",
                "...BBD.....DBBD.",
                "...BBD.....DBB..",
                "...BBD.....DBB..",
                "...KKK.....KKK..",
            ],
            "step_l": {"bob": True, "legs": [
                "BBD.....DBBD", "BBD.....DDD.", "BBD.........", "KKK........."]},
            "pass": {"legs": [
                "BBD.....DBBD", ".BBD...DBB..", ".BBD...DBB..", ".KKK...KKK.."]},
            "step_r": {"bob": True, "legs": [
                "BBD.....DBBD", "DDD.....DBB.", "........DBB.", "........KKK."]},
            "wind": {"move": [(3, 1, 10, 7, 0, 1)]},
            "strike": [
                "................",
                ".....K...K......",
                ".....KKKKK......",
                "....BBMMMBB.....",
                "....BEBMBEB.....",
                ".....BBMBB......",
                ".....BBMBB......",
                ".....MNNM.......",
                "...BBBBBBBBBD...",
                "..BBBBBBBBBBBD..",
                "..BBBBBBBBBBBD..",
                "..BBD.KK.KK.BBD.",
                "..BBD.KK.KK.BB..",
                "..BBD.......BB..",
                "..KKK.......KKK.",
            ],
            "hurt": {"move": [(3, 1, 10, 7, 0, 1)], "swap": {"E": "S"}},
        },
        "up": {
            "stand": [
                "................",
                ".....K...K......",
                ".....KKKKK......",
                "....BBKKKBB.....",
                "....BBBKBBB.....",
                ".....BBKBB......",
                ".....BBKBB......",
                ".....BBKBB......",
                "....BBBBBBBD....",
                "...BBBBBBBBBD...",
                "...BBBBKKBBBD...",
                "...BBDKKKKDBBD..",
                "...BBD.KK..DBB..",
                "...BBD.KK..DBB..",
                "...KKK.KK..KKK..",
            ],
            "step_l": {"bob": True, "legs": [
                "BBDKKKKDBBD.", "BBD.KK..DDD.", "BBD.KK......", "KKK.KK......"]},
            "pass": {"legs": [
                "BBDKKKKDBBD.", ".BBDKK.DBB..", ".BBDKK.DBB..", ".KKKKK.KKK.."]},
            "step_r": {"bob": True, "legs": [
                "BBDKKKKDBBD.", "DDD.KK..DBB.", "....KK..DBB.", "....KK..KKK."]},
            "wind": {"move": [(3, 1, 10, 7, 0, 1)]},
            "strike": {"bob": True, "legs": [
                "BBDKKKKDBBD.", "BBD.KK..DBB.", "BBD.KK..DBB.", "KKK.KK..KKK."]},
            "hurt": {"move": [(3, 1, 10, 7, 0, 1)]},
        },
    },
    leg_rect={"left": (3, 11, 11, 4), "down": (3, 11, 12, 4), "up": (3, 11, 12, 4)},
    back={"left": (0, 0), "down": (0, 0)},
    face=[
        "................................",
        "................................",
        ".........KK.........KK..........",
        "........KBBK.......KBBK.........",
        "........KBBBK.....KBBBK.........",
        "........KBBBKKKKKKKBBBK.........",
        ".........KKKKKKKKKKKKK..........",
        "........KKKKKKKKKKKKKKK.........",
        ".......KBBBBBBMMMMBBBBBBK.......",
        ".......BBBBBBBMMMMBBBBBBBD......",
        "......LBBBBBBBMMMMBBBBBBBD......",
        "......LBBBEEBBMMMMBBEEBBBD......",
        "......LBBBEEBBMMMMBBEEBBBD......",
        "......LBBBBBBBMMMMBBBBBBBD......",
        ".......BBBBBBBMMMMBBBBBBD.......",
        ".......BBBBBBBMMMMBBBBBBD.......",
        "........BBBBBBMMMMBBBBBD........",
        "........BBBBBBMMMMBBBBBD........",
        "........BBBBBBMMMMBBBBBD........",
        ".........BBBBBMMMMBBBBD.........",
        ".........BBBBBMMMMBBBBD.........",
        ".........BBBBMMMMMMBBBD.........",
        ".........BBMMMMMMMMMMBD.........",
        ".........BMMMNNMMNNMMMD.........",
        ".........BMMMNNMMNNMMMD.........",
        "..........MMMMMMMMMMMD..........",
        "...........MMMMMMMMMD...........",
        ".......KKBBBBBBBBBBBBBBD........",
        "....BBKKKKBBBBBBBBBBBBBBBD......",
        "..BBBBKKKKBBBBBBBBBBBBBBBBBDD...",
        "................................",
        "................................",
    ],
))


# ==========================================================================================
# RACCOON (너구리) -- chubby raccoon dog of 무명산: ink_light coat, ink shade, ink_dark eye
# mask, spine stripe and short banded tail, ink_pale cheeks/muzzle. Attack = snapping bite.
# ==========================================================================================
RACCOON_COLORS = {"B": "ink_light", "D": "ink", "K": "ink_dark", "L": "ink_pale", "E": "ink_black",
                  "N": "ink_black", "S": "ink_dark", "W": "paper_light", "T": "vermilion"}

register(Animal(
    "raccoon", RACCOON_COLORS,
    views={
        "left": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "................",
                "...B.B..........",
                "..LBBBB.........",
                ".LKEKBBBBBBBB...",
                ".NLLBBBBBBBBKLK.",
                "..LLBBBBBBBBKLK.",
                "...BBBBBBBBBKLK.",
                "...BBD..DBBD....",
                "...KKD..DKKD....",
                "...KK....KK.....",
            ],
            "step_l": {"bob": True, "legs": ["BBD..DBBD", "K.D..D.KD", "K.K..K.KK"]},
            "pass": {"legs": ["BBD..DBBD", ".KD..DK..", ".K....K.."]},
            "step_r": {"bob": True, "legs": ["BBD..DBBD", ".DK.K.KD.", "K..KK.K.K"]},
            "wind": {"move": [(1, 6, 7, 5, 0, 1)]},
            "strike": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "................",
                "...B.B..........",
                "..LBBBB.........",
                ".LKEKBBBBBBBB...",
                ".NLLBBBBBBBBKLK.",
                ".WW.BBBBBBBBKLK.",
                ".LL.BBBBBBBBKLK.",
                "..BBD....DBBD...",
                ".KK.D....D.KKD..",
                ".KK........KK...",
            ],
            "hurt": {"move": [(1, 6, 7, 5, 0, -1)], "swap": {"E": "S"}},
        },
        "down": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "................",
                "...BB...BB......",
                "...BBBBBBB......",
                "..BKEKBKEKBD....",
                "..BLLBBBLLBD....",
                "...BLLNLLBD.....",
                "....BBBBBD......",
                "...BBLLLLBBD....",
                "...KK....KKD....",
                "...KK....KK.....",
            ],
            "step_l": {"bob": True, "legs": ["KK....KKD", "KK......."]},
            "pass": {"legs": [".KK..KK..", ".KK..KK.."]},
            "step_r": {"bob": True, "legs": ["KK....KKD", "......KK."]},
            "strike": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "................",
                "................",
                "...BB...BB......",
                "...BBBBBBB......",
                "..BKEKBKEKBD....",
                "..BLLBBBLLBD....",
                "...BLLNLLBD.....",
                "...BBWTTWBD.....",
                "..BBBLLLLBBB....",
                "..KK......KK....",
            ],
            "hurt": {"shift": (0, -1), "swap": {"E": "S"}},
        },
        "up": {
            "stand": [
                "................",
                "................",
                "................",
                "................",
                "................",
                "................",
                "...BB...BB......",
                "...BBBBBBB......",
                "..BBBBKBBBBD....",
                "..BBBBKBBBBD....",
                "...BBBKBBBD.....",
                "....BBKBBD......",
                "...BBBKKBBBD....",
                "...KK.LL.KKD....",
                "...KK.KK.KK.....",
            ],
            "step_l": {"bob": True, "legs": ["KK.LL.KKD", "KK.KK...."]},
            "pass": {"legs": [".KKLLKK..", ".KKKKKK.."]},
            "step_r": {"bob": True, "legs": ["KK.LL.KKD", "....KK.KK"]},
            "wind": {"move": [(2, 6, 10, 7, 0, 1)]},
            "strike": {"bob": True, "legs": ["KK.LL.KKD", "KK.KK.KK."]},
            "hurt": {"move": [(2, 6, 10, 7, 0, 1)]},
        },
    },
    leg_rect={"left": (3, 12, 9, 3), "down": (3, 13, 9, 2), "up": (3, 13, 9, 2)},
    back={"left": (0, 0)},
    face=[
        "................................",
        "................................",
        "................................",
        ".......BBB...........BBB........",
        "......BBBBB.........BBBBB.......",
        ".....BBBBBBB.......BBBBBBB......",
        ".....BBBBBBBBBBBBBBBBBBBBB......",
        "....BBBBBBBBBBBBBBBBBBBBBBD.....",
        "....BBBBBBBBBBBBBBBBBBBBBBD.....",
        "...BBBBBBBBBBBBBBBBBBBBBBBBD....",
        "...BBBKKKKKKKBBBBKKKKKKKBBBD....",
        "...BBKKKKKKKKKBBKKKKKKKKKBBD....",
        "...BBKKKEEKKKKBBKKKKEEKKKBBD....",
        "...BBKKKEEKKKKBBKKKKEEKKKBBD....",
        "...BBBKKKKKKKLLLLKKKKKKKBBBD....",
        "...LLBBKKKKKLLLLLLKKKKKBBLLD....",
        "...LLLBBBBBLLLLLLLLBBBBBLLLD....",
        "....LLLBBBBLLLNNLLLBBBBLLLD.....",
        "....LLLLBBLLLNNNNLLLBBLLLLD.....",
        ".....LLLLLLLLLNNLLLLLLLLLD......",
        ".....LLLLLLLLLKKLLLLLLLLLD......",
        "......LLLLLLLKLLKLLLLLLLD.......",
        ".......LLLLLLLLLLLLLLLLD........",
        ".........LLLLLLLLLLLLD..........",
        "...........BBBBBBBBD............",
        "........BBBBBBBBBBBBBBD.........",
        ".....BBBBBBBBBBBBBBBBBBBBD......",
        "...BBBBBBBBBBLLLLLLBBBBBBBBDD...",
        "..BBBBBBBBBBLLLLLLLLBBBBBBBBDDD.",
        "..BBBBBBBBBBLLLLLLLLBBBBBBBBDDD.",
        "................................",
        "................................",
    ],
))


# ==========================================================================================
# build
# ==========================================================================================
NAMES = ("wolf", "tiger", "bear", "deer", "egret", "dog", "chicken", "boar", "monkey", "snake",
         "fox", "horse", "raccoon")


def build(art_root: str, preview_dir: str, cellmap_dir: str) -> List[str]:
    out_dir = os.path.join(art_root, "Characters")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(preview_dir, exist_ok=True)
    written: List[str] = []
    names = [n for n in NAMES if n in ANIMALS]
    for name in names:
        animal = ANIMALS[name]
        walk, attack, hurt, face = animal.character()
        sheet, face_sheet = character_sheet(name, walk, attack, hurt, face)
        written.extend(sheet.save(out_dir))
        written.append(sheet.preview(os.path.join(preview_dir, f"{sheet.file_name}_preview.png"), scale=4))
        assert face_sheet is not None
        written.extend(face_sheet.save(out_dir))
        written.append(face_sheet.preview(
            os.path.join(preview_dir, f"{face_sheet.file_name}_preview.png"), scale=4))
    return written


if __name__ == "__main__":
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.normpath(os.path.join(here, "..", ".."))
    for p in build(os.path.join(root, "Assets", "InkPixel", "Art"), os.path.join(root, "Docs", "previews"),
                   os.path.join(root, "Docs", "cellmaps")):
        print(p)
    sys.exit(0)
