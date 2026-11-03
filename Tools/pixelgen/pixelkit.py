"""pixelkit.py -- InkPixel (수묵 픽셀 팩) pixel-art toolkit (binding surface: ASSET_SPEC.md v2, §8).

    from pixelkit import Canvas, Sheet, blob47, PALETTE, Rng, verify_palette, character_sheet

Canvas          : RGBA pixel buffer (numpy (H, W, 4) uint8, (0, 0) = top-left) with pixel-art
                  drawing primitives. Alpha is strictly 0 or 255 (the pack forbids partial alpha).
Sheet           : named sprites (+ animations / tiles / tile rules) packed into one PNG with the
                  v2 sidecar `<file>.sprites.json` of spec §3. Supports flowing row packing (§2.3),
                  fixed placement (`add_at`), FX strips (`set_strip`), single-file export
                  (`save_singles`), review previews and tile cell maps.
character_sheet : builds the 128x64 character layout of §5.1 (+ optional 32x32 face sheet).
blob47          : assembles the 47 canonical blob-tile masks from a quadrant drawer (§4).
Rng             : deterministic random source (fixed seeds everywhere).
verify_palette / check_sheet / check_sidecar : reviewer helpers (§9).

Colors everywhere are "color-likes": a palette name ("moss"), the alias "outline"
(= ink_black), "#rrggbb", an (r, g, b[, a]) tuple, or None (= transparent / erase).
"""
from __future__ import annotations

import json
import math
import os
import random
import re
from collections import OrderedDict
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image

try:  # imported as a package member (Tools.pixelgen.pixelkit) or as a top-level module
    from .palette import (PALETTE, COLORS, NAME_TO_RGB, RGB_TO_NAME, PALETTE_NAMES, ALIASES,
                          OUTLINE, RAMPS, hex_to_rgb, rgb_to_hex, is_palette_rgb,
                          nearest_palette_name, resolve_rgba, ramp, TRANSPARENT, ColorLike)
except ImportError:  # pragma: no cover - depends on how the module is imported
    from palette import (PALETTE, COLORS, NAME_TO_RGB, RGB_TO_NAME, PALETTE_NAMES, ALIASES,  # type: ignore
                         OUTLINE, RAMPS, hex_to_rgb, rgb_to_hex, is_palette_rgb,
                         nearest_palette_name, resolve_rgba, ramp, TRANSPARENT, ColorLike)

__all__ = [
    # palette re-exports
    "PALETTE", "COLORS", "NAME_TO_RGB", "RGB_TO_NAME", "PALETTE_NAMES", "ALIASES", "OUTLINE",
    "RAMPS", "hex_to_rgb", "rgb_to_hex", "is_palette_rgb", "nearest_palette_name",
    "resolve_rgba", "ramp", "TRANSPARENT",
    # core
    "Canvas", "Sheet", "SpriteEntry", "Rng", "blob47", "character_sheet",
    # blob helpers
    "MASK_N", "MASK_NE", "MASK_E", "MASK_SE", "MASK_S", "MASK_SW", "MASK_W", "MASK_NW",
    "CANONICAL_MASKS", "QUADRANT_NAMES", "QUADRANT_KINDS", "KIND_INNER", "KIND_EDGE_H",
    "KIND_EDGE_V", "KIND_CORNER_OUT", "KIND_CORNER_IN", "quadrant_kind", "quadrant_kinds",
    "canonicalize", "is_canonical", "mask_from_neighbors",
    # conventions
    "SHEET_KINDS", "TILE_KINDS", "DIRECTIONS", "COLLIDERS", "PIXELS_PER_UNIT", "CELL_SIZE",
    "MAX_SHEET_WIDTH", "SIDECAR_VERSION", "CHARACTER_SHEET_SIZE", "FACE_SIZE", "FRAME_SIZE",
    "WALK_FRAMES", "ATTACK_FRAMES", "WALK_FPS", "ATTACK_FPS", "FX_FRAME_SIZE", "ICON_SIZE",
    "pascal_case", "file_base_for_sheet",
    # reviewer helpers
    "verify_palette", "check_sheet", "check_sidecar", "check_character_sheet", "load_sidecar",
    # misc
    "FONT_3X5", "FONT_3X5_ADVANCE", "text_width",
]

# ------------------------------------------------------------------------------------------
# Conventions (spec §2, §3, §5)
# ------------------------------------------------------------------------------------------
PIXELS_PER_UNIT = 16
CELL_SIZE = 16
MAX_SHEET_WIDTH = 512
SIDECAR_VERSION = 2
SHEET_KINDS = ("tiles", "autotiles", "character", "icons", "fx", "ui", "face")
TILE_KINDS = ("tiles", "autotiles")          # every sprite must sit on the 16px grid
DIRECTIONS = ("down", "up", "left", "right")
COLLIDERS = ("none", "sprite", "grid")
CHARACTER_SHEET_SIZE = (128, 64)             # §5.1
FACE_SIZE = (32, 32)
FRAME_SIZE = 16
WALK_FRAMES = 4
ATTACK_FRAMES = 3
WALK_FPS = 8
ATTACK_FPS = 12
FX_FRAME_SIZE = 48                           # §5.4 (informational; not enforced by Sheet)
ICON_SIZE = 40                               # §5.3 (informational; not enforced by Sheet)
_NAME_RE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")
_FILE_RE = re.compile(r"^[A-Za-z0-9_]+$")
_SINGLE_RE = re.compile(r"^[A-Za-z0-9_]+(/[A-Za-z0-9_]+)*$")

RGBA = Tuple[int, int, int, int]


def _rgba(color: ColorLike) -> RGBA:
    """Resolve a color-like to (r, g, b, a) with a in {0, 255}."""
    return resolve_rgba(color)


def _rgba_arr(color: ColorLike) -> np.ndarray:
    return np.array(_rgba(color), dtype=np.uint8)


def pascal_case(snake: str) -> str:
    """'slash_heavy' -> 'SlashHeavy', 'sprite_sheet_slash01' -> 'SpriteSheetSlash01'."""
    return "".join(p[:1].upper() + p[1:] for p in snake.split("_") if p)


def file_base_for_sheet(name: str, kind: str) -> str:
    """Default PNG/sidecar base name for a sheet: PascalCase for `fx` (GPA loads strips by
    PascalCase name, §2.2), the sheet name itself otherwise."""
    return pascal_case(name) if kind == "fx" else name


def _allowed_file_bases(name: str) -> Tuple[str, ...]:
    """File base names a sheet may be written to: `<sheet>`, PascalCase (fx) or `<sheet>_sheet`
    (icons_sheet.png / ui_sheet.png contact sheets, §5.3 / §5.5)."""
    return (name, pascal_case(name), name + "_sheet")


# ------------------------------------------------------------------------------------------
# Tiny 3x5 debug font (used by Canvas.stamp, previews and cell maps). Never shipped.
# Each glyph: 5 rows of 3 chars, '#' = ink. Advance is 4 px (3 + 1 gap).
# ------------------------------------------------------------------------------------------
FONT_3X5: Dict[str, Tuple[str, str, str, str, str]] = {
    "A": (".#.", "#.#", "###", "#.#", "#.#"),
    "B": ("##.", "#.#", "##.", "#.#", "##."),
    "C": (".##", "#..", "#..", "#..", ".##"),
    "D": ("##.", "#.#", "#.#", "#.#", "##."),
    "E": ("###", "#..", "##.", "#..", "###"),
    "F": ("###", "#..", "##.", "#..", "#.."),
    "G": (".##", "#..", "#.#", "#.#", ".##"),
    "H": ("#.#", "#.#", "###", "#.#", "#.#"),
    "I": ("###", ".#.", ".#.", ".#.", "###"),
    "J": ("..#", "..#", "..#", "#.#", ".#."),
    "K": ("#.#", "#.#", "##.", "#.#", "#.#"),
    "L": ("#..", "#..", "#..", "#..", "###"),
    "M": ("#.#", "###", "###", "#.#", "#.#"),
    "N": ("##.", "#.#", "#.#", "#.#", "#.#"),
    "O": (".#.", "#.#", "#.#", "#.#", ".#."),
    "P": ("##.", "#.#", "##.", "#..", "#.."),
    "Q": (".#.", "#.#", "#.#", ".#.", "..#"),
    "R": ("##.", "#.#", "##.", "#.#", "#.#"),
    "S": (".##", "#..", ".#.", "..#", "##."),
    "T": ("###", ".#.", ".#.", ".#.", ".#."),
    "U": ("#.#", "#.#", "#.#", "#.#", "###"),
    "V": ("#.#", "#.#", "#.#", "#.#", ".#."),
    "W": ("#.#", "#.#", "###", "###", "#.#"),
    "X": ("#.#", "#.#", ".#.", "#.#", "#.#"),
    "Y": ("#.#", "#.#", ".#.", ".#.", ".#."),
    "Z": ("###", "..#", ".#.", "#..", "###"),
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("##.", "..#", ".#.", "#..", "###"),
    "3": ("###", "..#", ".##", "..#", "###"),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "##.", "..#", "##."),
    "6": (".##", "#..", "###", "#.#", "###"),
    "7": ("###", "..#", ".#.", ".#.", ".#."),
    "8": ("###", "#.#", "###", "#.#", "###"),
    "9": ("###", "#.#", "###", "..#", "##."),
    " ": ("...", "...", "...", "...", "..."),
    "_": ("...", "...", "...", "...", "###"),
    "-": ("...", "...", "###", "...", "..."),
    ".": ("...", "...", "...", "...", ".#."),
    ",": ("...", "...", "...", ".#.", "#.."),
    ":": ("...", ".#.", "...", ".#.", "..."),
    ";": ("...", ".#.", "...", ".#.", "#.."),
    "/": ("..#", "..#", ".#.", "#..", "#.."),
    "\\": ("#..", "#..", ".#.", "..#", "..#"),
    "#": ("#.#", "###", "#.#", "###", "#.#"),
    "?": ("##.", "..#", ".#.", "...", ".#."),
    "!": (".#.", ".#.", ".#.", "...", ".#."),
    "+": ("...", ".#.", "###", ".#.", "..."),
    "=": ("...", "###", "...", "###", "..."),
    "(": (".#.", "#..", "#..", "#..", ".#."),
    ")": (".#.", "..#", "..#", "..#", ".#."),
    "[": ("##.", "#..", "#..", "#..", "##."),
    "]": (".##", "..#", "..#", "..#", ".##"),
    "<": ("..#", ".#.", "#..", ".#.", "..#"),
    ">": ("#..", ".#.", "..#", ".#.", "#.."),
    "%": ("#.#", "..#", ".#.", "#..", "#.#"),
    "*": ("#.#", ".#.", "###", ".#.", "#.#"),
    "~": ("...", ".##", "##.", "...", "..."),
    "'": (".#.", ".#.", "...", "...", "..."),
    '"': ("#.#", "#.#", "...", "...", "..."),
    "|": (".#.", ".#.", ".#.", ".#.", ".#."),
    "^": (".#.", "#.#", "...", "...", "..."),
    "@": (".#.", "#.#", "###", "#..", ".##"),
    "&": (".#.", "#.#", ".#.", "#.#", ".##"),
    "$": (".##", "##.", ".#.", ".##", "##."),
}
FONT_3X5_ADVANCE = 4


def text_width(text: str, scale: int = 1) -> int:
    """Width in pixels of `text` rendered with the 3x5 debug font at `scale`."""
    return len(text) * FONT_3X5_ADVANCE * scale


# ------------------------------------------------------------------------------------------
# Canvas
# ------------------------------------------------------------------------------------------
class Canvas:
    """RGBA pixel buffer with pixel-art drawing primitives.

    Storage: `px`, a numpy array of shape (H, W, 4), dtype uint8. (0, 0) is top-left,
    x grows right, y grows down. Out-of-bounds writes are silently ignored; out-of-bounds
    reads return the transparent pixel (0, 0, 0, 0). All methods that return "a new canvas"
    leave `self` untouched; everything else mutates in place and returns None.
    """

    def __init__(self, w: int, h: int, fill: ColorLike = None):
        w, h = int(w), int(h)
        if w <= 0 or h <= 0:
            raise ValueError(f"Canvas size must be positive, got {w}x{h}")
        self.px = np.zeros((h, w, 4), dtype=np.uint8)
        if fill is not None:
            self.fill(fill)

    # --- construction ---------------------------------------------------------------
    @classmethod
    def from_array(cls, arr: np.ndarray) -> "Canvas":
        """Wrap an (H, W, 4) or (H, W, 3) uint8 array (copied; alpha normalised to 0/255)."""
        arr = np.asarray(arr)
        if arr.ndim != 3 or arr.shape[2] not in (3, 4):
            raise ValueError("expected an (H, W, 3|4) array")
        c = cls.__new__(cls)
        h, w = arr.shape[:2]
        px = np.zeros((h, w, 4), dtype=np.uint8)
        px[..., :3] = arr[..., :3]
        if arr.shape[2] == 4:
            opaque = arr[..., 3] > 0
            px[..., 3] = np.where(opaque, 255, 0).astype(np.uint8)
            px[~opaque] = 0
        else:
            px[..., 3] = 255
        c.px = px
        return c

    @classmethod
    def from_image(cls, img: Image.Image) -> "Canvas":
        """From a PIL image (converted to RGBA)."""
        return cls.from_array(np.asarray(img.convert("RGBA")))

    @classmethod
    def load(cls, path: str) -> "Canvas":
        """Load a PNG file."""
        with Image.open(path) as img:
            return cls.from_image(img)

    @classmethod
    def from_pattern(cls, rows: Sequence[str], colormap: Dict[str, ColorLike]) -> "Canvas":
        """Build a canvas from ASCII-art rows.

        `colormap` maps each character to a color-like ('.' and ' ' are transparent and need
        no entry). Width = longest row (shorter rows are padded with transparency).
        Any other unmapped character raises KeyError.

            body = Canvas.from_pattern([
                "..kkk...",
                ".ksssk..",
                ".kssk...",
            ], {"k": "ink_black", "s": "skin"})
        """
        rows = list(rows)
        if not rows:
            raise ValueError("from_pattern needs at least one row")
        w = max(len(r) for r in rows)
        if w == 0:
            raise ValueError("from_pattern rows are empty")
        c = cls(w, len(rows))
        c.paste_pattern(rows, 0, 0, colormap)
        return c

    def copy(self) -> "Canvas":
        c = Canvas.__new__(Canvas)
        c.px = self.px.copy()
        return c

    # --- geometry -------------------------------------------------------------------
    @property
    def w(self) -> int:
        return int(self.px.shape[1])

    @property
    def h(self) -> int:
        return int(self.px.shape[0])

    width = w
    height = h

    @property
    def size(self) -> Tuple[int, int]:
        return (self.w, self.h)

    def __repr__(self) -> str:
        return f"Canvas({self.w}x{self.h}, opaque={self.count_opaque()})"

    def _in(self, x: int, y: int) -> bool:
        return 0 <= x < self.px.shape[1] and 0 <= y < self.px.shape[0]

    # --- pixel access ---------------------------------------------------------------
    def set(self, x: int, y: int, color: ColorLike) -> None:
        """Write one pixel. Out-of-bounds coordinates are silently ignored. None erases."""
        x, y = int(x), int(y)
        if 0 <= x < self.px.shape[1] and 0 <= y < self.px.shape[0]:
            self.px[y, x] = _rgba(color)

    def get(self, x: int, y: int) -> RGBA:
        """Read one pixel as (r, g, b, a). Out of bounds -> (0, 0, 0, 0)."""
        x, y = int(x), int(y)
        if 0 <= x < self.px.shape[1] and 0 <= y < self.px.shape[0]:
            return tuple(int(v) for v in self.px[y, x])  # type: ignore[return-value]
        return TRANSPARENT

    def get_name(self, x: int, y: int) -> Optional[str]:
        """Palette name of the pixel at (x, y); None when transparent or off-palette."""
        r, g, b, a = self.get(x, y)
        if a == 0:
            return None
        return RGB_TO_NAME.get((r, g, b))

    def is_opaque(self, x: int, y: int) -> bool:
        return self.get(x, y)[3] != 0

    def fill(self, color: ColorLike) -> None:
        """Fill the whole canvas."""
        self.px[:, :] = _rgba_arr(color)

    def clear(self) -> None:
        """Make the whole canvas transparent."""
        self.px[:, :] = 0

    # --- primitives -----------------------------------------------------------------
    def hline(self, x0: int, x1: int, y: int, color: ColorLike) -> None:
        """Horizontal line from x0 to x1 inclusive (either order)."""
        x0, x1, y = int(x0), int(x1), int(y)
        if x0 > x1:
            x0, x1 = x1, x0
        if not (0 <= y < self.h):
            return
        x0 = max(x0, 0)
        x1 = min(x1, self.w - 1)
        if x0 <= x1:
            self.px[y, x0:x1 + 1] = _rgba_arr(color)

    def vline(self, x: int, y0: int, y1: int, color: ColorLike) -> None:
        """Vertical line from y0 to y1 inclusive (either order)."""
        x, y0, y1 = int(x), int(y0), int(y1)
        if y0 > y1:
            y0, y1 = y1, y0
        if not (0 <= x < self.w):
            return
        y0 = max(y0, 0)
        y1 = min(y1, self.h - 1)
        if y0 <= y1:
            self.px[y0:y1 + 1, x] = _rgba_arr(color)

    def rect(self, x: int, y: int, w: int, h: int, color: ColorLike, fill: bool = True) -> None:
        """Axis-aligned rectangle with top-left (x, y) and size w x h; 1px outline if fill=False."""
        x, y, w, h = int(x), int(y), int(w), int(h)
        if w <= 0 or h <= 0:
            return
        if fill:
            x0, y0 = max(x, 0), max(y, 0)
            x1, y1 = min(x + w, self.w), min(y + h, self.h)
            if x1 > x0 and y1 > y0:
                self.px[y0:y1, x0:x1] = _rgba_arr(color)
        else:
            self.hline(x, x + w - 1, y, color)
            self.hline(x, x + w - 1, y + h - 1, color)
            self.vline(x, y, y + h - 1, color)
            self.vline(x + w - 1, y, y + h - 1, color)

    def line(self, x0: int, y0: int, x1: int, y1: int, color: ColorLike) -> None:
        """1px Bresenham line, both endpoints included."""
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        rgba = _rgba(color)
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        px, W, H = self.px, self.w, self.h
        while True:
            if 0 <= x0 < W and 0 <= y0 < H:
                px[y0, x0] = rgba
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    @staticmethod
    def _ellipse_mask(cx: float, cy: float, rx: float, ry: float):
        """Boolean mask of a pixel-art ellipse plus its bounding-box origin (x0, y0).

        Pixel centers are at integer coordinates. Integer center + integer radius gives an
        odd diameter (2r + 1); use half-integer centers (cx = 7.5, rx = 4) for even sizes.
        The inclusion test is slightly inflated (r^2 + r/2) so small circles look like the
        classic hand-drawn pixel circles (3-5-5-5-3 for diameter 5, etc.).
        """
        rx, ry = float(rx), float(ry)
        if rx < 0 or ry < 0:
            return None, 0, 0
        x0, x1 = int(math.floor(cx - rx)), int(math.ceil(cx + rx))
        y0, y1 = int(math.floor(cy - ry)), int(math.ceil(cy + ry))
        xs = np.arange(x0, x1 + 1, dtype=np.float64) - cx
        ys = np.arange(y0, y1 + 1, dtype=np.float64) - cy
        erx = max(rx, 1e-9)
        ery = max(ry, 1e-9)
        k = 0.5 / max(min(rx, ry), 0.5)
        nx = (xs / erx) ** 2
        ny = (ys / ery) ** 2
        mask = (ny[:, None] + nx[None, :]) <= 1.0 + k
        return mask, x0, y0

    def _apply_mask(self, mask: np.ndarray, x0: int, y0: int, color: ColorLike) -> None:
        """Paint `color` where `mask` (placed at x0, y0) is True, clipped to the canvas."""
        mh, mw = mask.shape
        cx0, cy0 = max(x0, 0), max(y0, 0)
        cx1, cy1 = min(x0 + mw, self.w), min(y0 + mh, self.h)
        if cx1 <= cx0 or cy1 <= cy0:
            return
        sub = mask[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
        region = self.px[cy0:cy1, cx0:cx1]
        region[sub] = _rgba_arr(color)

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, color: ColorLike,
                fill: bool = True) -> None:
        """Pixel ellipse centred on (cx, cy) with radii rx, ry (floats allowed, see _ellipse_mask)."""
        mask, x0, y0 = self._ellipse_mask(cx, cy, rx, ry)
        if mask is None:
            return
        if not fill:
            mask = _boundary(mask)
        self._apply_mask(mask, x0, y0, color)

    def circle(self, cx: float, cy: float, r: float, color: ColorLike, fill: bool = True) -> None:
        """Pixel circle (see ellipse)."""
        self.ellipse(cx, cy, r, r, color, fill=fill)

    def fill_points(self, points: Iterable[Tuple[int, int]], color: ColorLike) -> None:
        """Set every (x, y) in `points` (out-of-bounds points are ignored)."""
        pts = np.asarray(list(points), dtype=np.int64).reshape(-1, 2)
        if len(pts) == 0:
            return
        ok = (pts[:, 0] >= 0) & (pts[:, 0] < self.w) & (pts[:, 1] >= 0) & (pts[:, 1] < self.h)
        pts = pts[ok]
        self.px[pts[:, 1], pts[:, 0]] = _rgba_arr(color)

    def fill_where(self, mask: np.ndarray, color: ColorLike) -> None:
        """Set every pixel where the (H, W) boolean `mask` is True."""
        mask = np.asarray(mask, dtype=bool)
        if mask.shape != self.px.shape[:2]:
            raise ValueError("mask shape must be (H, W) of this canvas")
        self.px[mask] = _rgba_arr(color)

    def dither_rect(self, x: int, y: int, w: int, h: int, color: ColorLike, parity: int = 0) -> None:
        """Checkerboard-fill a rect: pixels where (x + y) % 2 == parity get `color`."""
        x, y, w, h = int(x), int(y), int(w), int(h)
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, self.w), min(y + h, self.h)
        if x1 <= x0 or y1 <= y0:
            return
        ys, xs = np.mgrid[y0:y1, x0:x1]
        sub = ((xs + ys) % 2) == (parity % 2)
        region = self.px[y0:y1, x0:x1]
        region[sub] = _rgba_arr(color)

    def paste_pattern(self, rows: Sequence[str], x: int, y: int,
                      colormap: Dict[str, ColorLike]) -> None:
        """Paint ASCII-art rows at (x, y). '.' and ' ' are skipped (underlying pixel kept).

        Map a character to None in `colormap` to erase explicitly. Unmapped characters
        (other than '.' / ' ') raise KeyError.
        """
        x, y = int(x), int(y)
        cache: Dict[str, RGBA] = {}
        px, W, H = self.px, self.w, self.h
        for row_i, row in enumerate(rows):
            py = y + row_i
            if not (0 <= py < H):
                continue
            for col_i, ch in enumerate(row):
                if ch == "." or ch == " ":
                    continue
                pxx = x + col_i
                if not (0 <= pxx < W):
                    continue
                rgba = cache.get(ch)
                if rgba is None:
                    if ch not in colormap:
                        raise KeyError(f"pattern char {ch!r} (row {row_i}, col {col_i}) not in colormap")
                    rgba = _rgba(colormap[ch])
                    cache[ch] = rgba
                px[py, pxx] = rgba

    def to_pattern(self, charmap: Optional[Dict[str, str]] = None) -> List[str]:
        """ASCII-art rows of this canvas ('.' = transparent), the inverse of from_pattern.

        `charmap` maps palette names to single characters; names not in it (and off-palette
        pixels) get letters assigned in order of first appearance, skipping '.' and ' '.
        Handy for iterating on hand-drawn art: draw procedurally, dump, tweak the text.
        """
        charmap = dict(charmap or {})
        used = set(charmap.values()) | {".", " "}
        pool = [c for c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" if c not in used]
        rows: List[str] = []
        for y in range(self.h):
            row = []
            for x in range(self.w):
                r, g, b, a = self.get(x, y)
                if a == 0:
                    row.append(".")
                    continue
                key = RGB_TO_NAME.get((r, g, b)) or rgb_to_hex((r, g, b))
                ch = charmap.get(key)
                if ch is None:
                    ch = pool.pop(0) if pool else "?"
                    charmap[key] = ch
                row.append(ch)
            rows.append("".join(row))
        return rows

    def blit(self, src: "Canvas", x: int, y: int, flip_x: bool = False, flip_y: bool = False) -> None:
        """Composite `src` onto this canvas with its top-left at (x, y).

        Alpha-aware in the 1-bit sense: opaque source pixels overwrite, transparent ones are
        skipped. Clipped at the canvas edges.
        """
        x, y = int(x), int(y)
        arr = src.px
        if flip_x:
            arr = arr[:, ::-1]
        if flip_y:
            arr = arr[::-1]
        sh, sw = arr.shape[:2]
        dx0, dy0 = max(x, 0), max(y, 0)
        dx1, dy1 = min(x + sw, self.w), min(y + sh, self.h)
        if dx1 <= dx0 or dy1 <= dy0:
            return
        sub = arr[dy0 - y:dy1 - y, dx0 - x:dx1 - x]
        m = sub[..., 3] > 0
        dst = self.px[dy0:dy1, dx0:dx1]
        dst[m] = sub[m]

    # --- transforms (return new canvases) --------------------------------------------
    def flipped_x(self) -> "Canvas":
        """Mirror left-right."""
        return Canvas.from_array(self.px[:, ::-1])

    def flipped_y(self) -> "Canvas":
        """Mirror top-bottom."""
        return Canvas.from_array(self.px[::-1])

    def rotated(self, k: int = 1) -> "Canvas":
        """Rotate by k * 90 degrees clockwise (k may be negative)."""
        return Canvas.from_array(np.rot90(self.px, -int(k)))

    def mirrored_lr(self) -> "Canvas":
        """New canvas whose right half is the mirror of the left half (symmetric art helper).

        The left ceil(w/2) columns are kept; the right side is their reflection.
        """
        out = self.copy()
        W = self.w
        left = self.px[:, :(W + 1) // 2]
        out.px[:, W - left.shape[1]:] = left[:, ::-1]
        out.px[:, :left.shape[1]] = left
        return out

    def mirrored_tb(self) -> "Canvas":
        """New canvas whose bottom half mirrors the top half."""
        out = self.copy()
        H = self.h
        top = self.px[:(H + 1) // 2]
        out.px[H - top.shape[0]:] = top[::-1]
        out.px[:top.shape[0]] = top
        return out

    def outlined(self, color: ColorLike = OUTLINE, diagonal: bool = False,
                 grow: bool = False) -> "Canvas":
        """New canvas with a 1px outline (default `ink_black`) added around opaque pixels.

        The outline is painted on transparent pixels that touch an opaque pixel (4-neighbour,
        or 8-neighbour when diagonal=True). With grow=False (default) the canvas keeps its
        size, so an outline that would fall outside the edge is simply clipped; grow=True
        returns a canvas 2px larger in each dimension with the art shifted by (1, 1).
        """
        src = self.px
        if grow:
            padded = np.zeros((self.h + 2, self.w + 2, 4), dtype=np.uint8)
            padded[1:-1, 1:-1] = src
            src = padded
        opaque = src[..., 3] > 0
        ring = _dilate(opaque, diagonal) & ~opaque
        out = Canvas.from_array(src)
        out.px[ring] = _rgba_arr(color)
        return out

    def recolored(self, mapping: Dict[ColorLike, ColorLike]) -> "Canvas":
        """New canvas with exact colors swapped: {src: dst, ...} (all swaps applied at once,
        so {"moss": "jade", "jade": "moss"} exchanges the two). Palette-swap outfits with it."""
        out = self.copy()
        masks = []
        for src, dst in mapping.items():
            s = _rgba_arr(src)
            m = np.all(self.px == s, axis=-1)
            masks.append((m, _rgba_arr(dst)))
        for m, d in masks:
            out.px[m] = d
        return out

    def shifted(self, dx: int, dy: int, wrap: bool = False) -> "Canvas":
        """New canvas with the content moved by (dx, dy); pixels leaving the canvas are lost
        unless wrap=True."""
        dx, dy = int(dx), int(dy)
        if wrap:
            return Canvas.from_array(np.roll(np.roll(self.px, dy, axis=0), dx, axis=1))
        out = Canvas(self.w, self.h)
        out.blit(self, dx, dy)
        return out

    def cropped(self, x: int, y: int, w: int, h: int) -> "Canvas":
        """New w x h canvas holding the region at (x, y); outside areas are transparent."""
        out = Canvas(w, h)
        out.blit(self, -int(x), -int(y))
        return out

    def centered(self, w: int, h: int) -> "Canvas":
        """New w x h canvas with this canvas's opaque bounding box centred in it
        (icons: draw loosely, then `art.centered(40, 40)`). Empty canvases come back empty."""
        out = Canvas(w, h)
        bb = self.bbox()
        if bb is None:
            return out
        bx, by, bw, bh = bb
        out.blit(self, (w - bw) // 2 - bx, (h - bh) // 2 - by)
        return out

    def scaled(self, k: int) -> "Canvas":
        """New canvas scaled by integer factor k (nearest neighbour)."""
        k = int(k)
        if k < 1:
            raise ValueError("scale factor must be >= 1")
        if k == 1:
            return self.copy()
        return Canvas.from_array(np.repeat(np.repeat(self.px, k, axis=0), k, axis=1))

    def dithered(self, parity: int = 0) -> "Canvas":
        """New canvas keeping only pixels where (x + y) % 2 == parity (1-bit checker dither)."""
        ys, xs = np.mgrid[0:self.h, 0:self.w]
        keep = ((xs + ys) % 2) == (parity % 2)
        out = self.copy()
        out.px[~keep] = 0
        return out

    # --- queries --------------------------------------------------------------------
    def opaque_mask(self) -> np.ndarray:
        """(H, W) boolean array, True where alpha == 255."""
        return self.px[..., 3] > 0

    def count_opaque(self) -> int:
        return int(np.count_nonzero(self.px[..., 3]))

    def is_empty(self) -> bool:
        return self.count_opaque() == 0

    def bbox(self) -> Optional[Tuple[int, int, int, int]]:
        """(x, y, w, h) of the opaque pixels, or None when empty."""
        m = self.opaque_mask()
        if not m.any():
            return None
        ys = np.nonzero(m.any(axis=1))[0]
        xs = np.nonzero(m.any(axis=0))[0]
        return (int(xs[0]), int(ys[0]), int(xs[-1] - xs[0] + 1), int(ys[-1] - ys[0] + 1))

    def equals(self, other: "Canvas") -> bool:
        return self.px.shape == other.px.shape and bool(np.array_equal(self.px, other.px))

    def colors_used(self) -> List[Optional[str]]:
        """Sorted list of palette names used (None included once for any off-palette pixel)."""
        m = self.opaque_mask()
        if not m.any():
            return []
        uniq = np.unique(self.px[m][:, :3], axis=0)
        names = set()
        for r, g, b in uniq:
            names.add(RGB_TO_NAME.get((int(r), int(g), int(b))))
        return sorted(names, key=lambda n: (n is None, n or ""))

    # --- debug text -----------------------------------------------------------------
    def stamp(self, text: str, x: int, y: int, color: ColorLike, font: str = "3x5",
              scale: int = 1) -> int:
        """Draw tiny debug text (3x5 font, 4px advance, lowercase is uppercased).

        Returns the x coordinate just after the last glyph. Unknown characters draw as '?'.
        """
        if font != "3x5":
            raise ValueError("only the built-in '3x5' font exists")
        x, y, scale = int(x), int(y), max(1, int(scale))
        rgba = _rgba(color)
        px, W, H = self.px, self.w, self.h
        cx = x
        for ch in str(text):
            glyph = FONT_3X5.get(ch.upper()) or FONT_3X5["?"]
            for gy, row in enumerate(glyph):
                for gx, cell in enumerate(row):
                    if cell != "#":
                        continue
                    x0, y0 = cx + gx * scale, y + gy * scale
                    x1, y1 = min(x0 + scale, W), min(y0 + scale, H)
                    x0, y0 = max(x0, 0), max(y0, 0)
                    if x1 > x0 and y1 > y0:
                        px[y0:y1, x0:x1] = rgba
            cx += FONT_3X5_ADVANCE * scale
        return cx

    # --- IO -------------------------------------------------------------------------
    def to_image(self) -> Image.Image:
        return Image.fromarray(self.px, "RGBA")

    def save(self, path: str) -> str:
        """Write as PNG (parent folders are created). Returns the path."""
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.to_image().save(path, "PNG", optimize=False)
        return path


def _dilate(mask: np.ndarray, diagonal: bool) -> np.ndarray:
    """Binary dilation by one pixel (4- or 8-neighbourhood) without wrap-around."""
    h, w = mask.shape
    p = np.zeros((h + 2, w + 2), dtype=bool)
    p[1:-1, 1:-1] = mask
    out = (p[0:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, 0:-2] | p[1:-1, 2:])
    if diagonal:
        out |= p[0:-2, 0:-2] | p[0:-2, 2:] | p[2:, 0:-2] | p[2:, 2:]
    return out | mask


def _boundary(mask: np.ndarray) -> np.ndarray:
    """Pixels of `mask` that have at least one 4-neighbour outside the mask (1px ring)."""
    h, w = mask.shape
    p = np.zeros((h + 2, w + 2), dtype=bool)
    p[1:-1, 1:-1] = mask
    interior = p[0:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, 0:-2] & p[1:-1, 2:]
    return mask & ~interior


# ------------------------------------------------------------------------------------------
# Rng
# ------------------------------------------------------------------------------------------
class Rng:
    """Deterministic random source (thin wrapper over random.Random).

    Always construct with an explicit seed; `fork(label)` derives an independent stream
    for a sub-task so adding a new random call in one place does not reshuffle another.
    """

    def __init__(self, seed: Union[int, str] = 0):
        self.seed = seed
        self.rand = random.Random(seed)

    def choice(self, seq):
        return self.rand.choice(seq)

    def choices(self, seq, weights=None, k=1):
        return self.rand.choices(seq, weights=weights, k=k)

    def randint(self, a: int, b: int) -> int:
        return self.rand.randint(a, b)

    def random(self) -> float:
        return self.rand.random()

    def uniform(self, a: float, b: float) -> float:
        return self.rand.uniform(a, b)

    def shuffle(self, seq) -> None:
        self.rand.shuffle(seq)

    def sample(self, seq, k: int):
        return self.rand.sample(seq, k)

    def chance(self, p: float) -> bool:
        """True with probability p."""
        return self.rand.random() < p

    def fork(self, label: Union[str, int]) -> "Rng":
        """New independent Rng seeded from (this seed, label)."""
        return Rng(f"{self.seed}/{label}")

    def __repr__(self) -> str:
        return f"Rng({self.seed!r})"


# ------------------------------------------------------------------------------------------
# Blob (47-tile) terrain sets  (spec §4)
# ------------------------------------------------------------------------------------------
MASK_N, MASK_NE, MASK_E, MASK_SE, MASK_S, MASK_SW, MASK_W, MASK_NW = 1, 2, 4, 8, 16, 32, 64, 128

KIND_INNER = "inner"            # both edges and the diagonal present: fully inside
KIND_EDGE_H = "edge_h"          # horizontal border: the N (or S) neighbour is missing
KIND_EDGE_V = "edge_v"          # vertical border: the W (or E) neighbour is missing
KIND_CORNER_OUT = "corner_out"  # convex outer corner: both edges missing
KIND_CORNER_IN = "corner_in"    # concave inner corner: both edges present, diagonal missing
QUADRANT_KINDS = (KIND_INNER, KIND_EDGE_H, KIND_EDGE_V, KIND_CORNER_OUT, KIND_CORNER_IN)
QUADRANT_NAMES = ("TL", "TR", "BL", "BR")

# per quadrant: (N/S edge bit, W/E edge bit, diagonal corner bit)
_QUADRANT_BITS = (
    (MASK_N, MASK_W, MASK_NW),  # 0 TL
    (MASK_N, MASK_E, MASK_NE),  # 1 TR
    (MASK_S, MASK_W, MASK_SW),  # 2 BL
    (MASK_S, MASK_E, MASK_SE),  # 3 BR
)
_CORNER_RULES = (
    (MASK_NE, MASK_N | MASK_E),
    (MASK_SE, MASK_S | MASK_E),
    (MASK_SW, MASK_S | MASK_W),
    (MASK_NW, MASK_N | MASK_W),
)


def canonicalize(mask: int) -> int:
    """Drop every corner bit whose two adjacent edge bits are not both set (47-blob form)."""
    mask = int(mask) & 255
    for corner, edges in _CORNER_RULES:
        if (mask & corner) and (mask & edges) != edges:
            mask &= ~corner
    return mask


def is_canonical(mask: int) -> bool:
    return canonicalize(mask) == (int(mask) & 255)


CANONICAL_MASKS: Tuple[int, ...] = tuple(m for m in range(256) if is_canonical(m))
assert len(CANONICAL_MASKS) == 47


def mask_from_neighbors(n=False, ne=False, e=False, se=False, s=False, sw=False, w=False, nw=False) -> int:
    """Canonical mask from eight neighbour flags (corners only count with both edges)."""
    m = 0
    if n:
        m |= MASK_N
    if ne:
        m |= MASK_NE
    if e:
        m |= MASK_E
    if se:
        m |= MASK_SE
    if s:
        m |= MASK_S
    if sw:
        m |= MASK_SW
    if w:
        m |= MASK_W
    if nw:
        m |= MASK_NW
    return canonicalize(m)


def quadrant_kind(mask: int, quadrant_index: int) -> str:
    """Kind of quadrant 0..3 (TL, TR, BL, BR) for `mask` (spec §4 rules).

    For a quadrant look at its two adjacent edges and its diagonal corner, e.g. TL: N, W, NW.
    both edges absent -> corner_out; exactly one present -> edge_h when the MISSING edge is
    N/S, edge_v when it is W/E; both present, corner absent -> corner_in; all -> inner.

        >>> quadrant_kinds(0)                      # isolated tile: four convex corners
        ('corner_out', 'corner_out', 'corner_out', 'corner_out')
        >>> quadrant_kinds(255)                    # surrounded: four inner quadrants
        ('inner', 'inner', 'inner', 'inner')
        >>> quadrant_kinds(MASK_E | MASK_W)        # horizontal strip: N and S borders
        ('edge_h', 'edge_h', 'edge_h', 'edge_h')
        >>> quadrant_kinds(MASK_N | MASK_E)        # L without the NE corner bit
        ('edge_v', 'corner_in', 'corner_out', 'edge_h')
    """
    ns_bit, we_bit, corner_bit = _QUADRANT_BITS[quadrant_index]
    has_ns = bool(mask & ns_bit)
    has_we = bool(mask & we_bit)
    if not has_ns and not has_we:
        return KIND_CORNER_OUT
    if has_ns != has_we:
        # exactly one edge present: the missing one decides the border orientation
        return KIND_EDGE_H if not has_ns else KIND_EDGE_V
    if not (mask & corner_bit):
        return KIND_CORNER_IN
    return KIND_INNER


def quadrant_kinds(mask: int) -> Tuple[str, str, str, str]:
    """(TL, TR, BL, BR) kinds for `mask`."""
    return tuple(quadrant_kind(mask, q) for q in range(4))  # type: ignore[return-value]


QuadrantDrawer = Callable[[int, str, int, Rng], Canvas]


def blob47(draw_quadrant: QuadrantDrawer, size: int = 16, frames: int = 1,
           rng: Optional[Rng] = None, cache: bool = True) -> List[Tuple[int, List[Canvas]]]:
    """Assemble all 47 canonical blob masks from a quadrant drawer (spec §4).

    `draw_quadrant(quadrant_index, kind, frame, rng)` must return a (size/2 x size/2) Canvas
    drawn in its final orientation (quadrant_index 0..3 = TL, TR, BL, BR; kind one of
    QUADRANT_KINDS). With cache=True (default) each (quadrant, kind, frame) is drawn once and
    reused for every mask, which guarantees seamless tiling; cache=False redraws per mask
    (the drawer then receives the same rng and may add per-tile variation).

    Returns [(mask, [canvas_per_frame, ...]), ...] in ascending mask order (CANONICAL_MASKS).

    Example -- a packed-earth road over grass, border 1px inside the quadrant edge:

        def road_quadrant(qi, kind, frame, rng):
            q = Canvas(8, 8, fill="earth_light")            # inside = road
            top, left = qi in (0, 1), qi in (0, 2)           # which outer edges this quadrant owns
            if kind in ("edge_h", "corner_out"):             # border along the N/S edge
                q.hline(0, 7, 0 if top else 7, "moss")
            if kind in ("edge_v", "corner_out"):             # border along the W/E edge
                q.vline(0 if left else 7, 0, 7, "moss")
            if kind == "corner_in":                          # the diagonal neighbour is grass
                q.set(0 if left else 7, 0 if top else 7, "moss")
            return q

        tiles = blob47(road_quadrant)                        # 47 x [Canvas(16x16)]
        sheet.add_blob("Road", "autotiles_road", tiles)      # sprites autotiles_road_m<mask>
    """
    size = int(size)
    if size < 2 or size % 2:
        raise ValueError("blob47 size must be an even number of pixels")
    if frames < 1:
        raise ValueError("frames must be >= 1")
    half = size // 2
    rng = rng if rng is not None else Rng("blob47")
    memo: Dict[Tuple[int, str, int], Canvas] = {}

    def quadrant(qi: int, kind: str, frame: int) -> Canvas:
        key = (qi, kind, frame)
        if cache and key in memo:
            return memo[key]
        c = draw_quadrant(qi, kind, frame, rng)
        if not isinstance(c, Canvas):
            raise TypeError(f"draw_quadrant({qi}, {kind!r}, {frame}) must return a Canvas, got {type(c).__name__}")
        if c.size != (half, half):
            raise ValueError(f"draw_quadrant({qi}, {kind!r}, {frame}) returned {c.w}x{c.h}, expected {half}x{half}")
        if cache:
            memo[key] = c
        return c

    offsets = ((0, 0), (half, 0), (0, half), (half, half))
    out: List[Tuple[int, List[Canvas]]] = []
    for mask in CANONICAL_MASKS:
        kinds = quadrant_kinds(mask)
        per_frame: List[Canvas] = []
        for f in range(frames):
            tile = Canvas(size, size)
            for qi, kind in enumerate(kinds):
                ox, oy = offsets[qi]
                tile.blit(quadrant(qi, kind, f), ox, oy)
            per_frame.append(tile)
        out.append((mask, per_frame))
    return out


# ------------------------------------------------------------------------------------------
# Sheet
# ------------------------------------------------------------------------------------------
def _round_up(v: int, m: int) -> int:
    return ((int(v) + m - 1) // m) * m


def _num(v):
    """int when integral, else float (keeps JSON tidy: 6 not 6.0)."""
    f = float(v)
    return int(f) if f.is_integer() else f


def _tags_str(tags) -> str:
    if tags is None:
        return ""
    if isinstance(tags, str):
        return tags.strip()
    return ",".join(str(t).strip() for t in tags if str(t).strip())


class SpriteEntry:
    """One sprite in a Sheet.

    name        unique, lowercase snake_case, '<sheet>_<descriptor>' (or == sheet name)
    canvas      pixels (copied on add)
    pivot       (px, py) normalised, (0.5, 0) = bottom centre
    border      9-slice (l, b, r, t) in pixels
    solid / overlay / ground / tags   suggested GPA TileDef values (§3)
    single_name file name (without .png, '/' for subfolders) used by save_singles; None = descriptor
    fixed       (x, y) for sprites placed with add_at, else None (packed in rows)
    """
    __slots__ = ("name", "canvas", "pivot", "border", "solid", "overlay", "ground", "tags",
                 "single_name", "fixed")

    def __init__(self, name: str, canvas: Canvas, pivot: Tuple[float, float],
                 border: Tuple[int, int, int, int], solid: bool = False, overlay: bool = False,
                 ground: str = "", tags: str = "", single_name: Optional[str] = None,
                 fixed: Optional[Tuple[int, int]] = None):
        self.name = name
        self.canvas = canvas
        self.pivot = pivot
        self.border = border
        self.solid = bool(solid)
        self.overlay = bool(overlay)
        self.ground = ground
        self.tags = tags
        self.single_name = single_name
        self.fixed = fixed

    @property
    def w(self) -> int:
        return self.canvas.w

    @property
    def h(self) -> int:
        return self.canvas.h

    def __repr__(self) -> str:
        pos = f" @({self.fixed[0]},{self.fixed[1]})" if self.fixed else ""
        return f"SpriteEntry({self.name!r}, {self.w}x{self.h}{pos})"


class Sheet:
    """A sprite sheet: named sprites packed into one PNG + the v2 sidecar sprites.json (§3).

    Packing (§2.3): sprites go left-to-right in insertion order; a new row starts when the
    next sprite would exceed `max_width` (default 512), when its height differs from the
    current row's height, or when the row already holds `columns` sprites (if given). The
    PNG is the bounding box of all sprites rounded up to a multiple of `cell_size` (16) so
    tile sheets stay grid aligned. Sprites placed with `add_at` keep their fixed position;
    packed sprites then start below the fixed block. `set_strip` lays everything in ONE row
    and the PNG is exactly frames*w x h (GPA slices strips by equal division).

    File names: `<out_dir>/<file_name>.png` + `<file_name>.sprites.json`. `file_name`
    defaults to the sheet name, or PascalCase for kind `fx` (GPA loads `FX/Slash`); it may
    also be `<sheet>_sheet` for the icons/ui contact sheets.
    """

    def __init__(self, name: str, kind: str, pivot: Tuple[float, float] = (0.5, 0.0),
                 max_width: int = MAX_SHEET_WIDTH, cell_size: int = CELL_SIZE,
                 columns: Optional[int] = None, file_name: Optional[str] = None,
                 strict_names: bool = True):
        if not _NAME_RE.match(name):
            raise ValueError(f"sheet name {name!r} must be lowercase snake_case ASCII")
        if kind not in SHEET_KINDS:
            raise ValueError(f"sheet kind {kind!r} must be one of {SHEET_KINDS}")
        if columns is not None and int(columns) < 1:
            raise ValueError("columns must be >= 1 or None")
        if int(max_width) < 1 or int(max_width) > MAX_SHEET_WIDTH:
            raise ValueError(f"max_width must be in 1..{MAX_SHEET_WIDTH}")
        if int(cell_size) < 1:
            raise ValueError("cell_size must be >= 1")
        if file_name is None:
            file_name = file_base_for_sheet(name, kind)
        if not _FILE_RE.match(file_name):
            raise ValueError(f"file_name {file_name!r} must be [A-Za-z0-9_]+ (no extension)")
        if file_name not in _allowed_file_bases(name):
            raise ValueError(f"file_name {file_name!r} must be one of {_allowed_file_bases(name)} "
                             f"so the file can be found from the sheet name {name!r}")
        self.name = name
        self.kind = kind
        self.file_name = file_name
        self.pivot = (float(pivot[0]), float(pivot[1]))
        self.max_width = int(max_width)
        self.cell_size = int(cell_size)
        self.columns = int(columns) if columns is not None else None
        self.pixels_per_unit = PIXELS_PER_UNIT
        self.strict_names = strict_names
        self.sprites: List[SpriteEntry] = []
        self._index: Dict[str, SpriteEntry] = {}
        self.animations: List[dict] = []
        self.tiles: List[dict] = []
        self.tile_rules: List[dict] = []
        self.rule_tile_defaults: List[dict] = []
        self.strip_frames = 0
        self.strip_fps = 0
        self.min_size: Optional[Tuple[int, int]] = None   # set by load(): keep the original PNG size

    # --- content --------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.sprites)

    def __contains__(self, name: str) -> bool:
        return name in self._index

    def __repr__(self) -> str:
        return f"Sheet({self.name!r}, kind={self.kind!r}, sprites={len(self.sprites)})"

    @property
    def sprite_names(self) -> List[str]:
        """Sprite names in written (JSON) order."""
        return [e.name for e in self.sprites]

    @property
    def is_strip(self) -> bool:
        return self.strip_frames > 0

    def get(self, name: str) -> SpriteEntry:
        return self._index[name]

    def get_canvas(self, name: str) -> Canvas:
        return self._index[name].canvas

    def descriptor(self, name: str) -> str:
        """Sprite name without the '<sheet>_' prefix ('icons_jian' -> 'jian')."""
        prefix = self.name + "_"
        return name[len(prefix):] if name.startswith(prefix) else name

    def single_file_name(self, name: str) -> str:
        """Relative PNG path (with extension) that save_singles writes for sprite `name`."""
        e = self._index[name]
        base = e.single_name if e.single_name is not None else self.descriptor(name)
        return base + ".png"

    def _check_name(self, name: str) -> None:
        if not isinstance(name, str) or not _NAME_RE.match(name):
            raise ValueError(f"sprite name {name!r} must be lowercase snake_case ASCII")
        if self.strict_names and not (name == self.name or name.startswith(self.name + "_")):
            raise ValueError(f"sprite name {name!r} must start with '{self.name}_' (sheet prefix)")
        if name in self._index:
            raise ValueError(f"duplicate sprite name {name!r} in sheet {self.name!r}")

    def _make_entry(self, name: str, canvas: Canvas, pivot, border, solid, overlay, ground, tags,
                    single_name, fixed) -> SpriteEntry:
        if not isinstance(canvas, Canvas):
            raise TypeError(f"sprite {name!r}: expected a Canvas, got {type(canvas).__name__}")
        self._check_name(name)
        if canvas.w > self.max_width:
            raise ValueError(f"sprite {name!r} is wider ({canvas.w}) than max_width {self.max_width}")
        if self.kind in TILE_KINDS and (canvas.w % self.cell_size or canvas.h % self.cell_size):
            raise ValueError(f"sprite {name!r} is {canvas.w}x{canvas.h}: sprites on a {self.kind!r} "
                             f"sheet must be multiples of {self.cell_size} px (§2)")
        pv = self.pivot if pivot is None else (float(pivot[0]), float(pivot[1]))
        if border is None:
            bd: Tuple[int, int, int, int] = (0, 0, 0, 0)
        else:
            if len(border) != 4:
                raise ValueError(f"sprite {name!r}: border must be (l, b, r, t)")
            bd = tuple(int(v) for v in border)  # type: ignore[assignment]
            if min(bd) < 0 or bd[0] + bd[2] > canvas.w or bd[1] + bd[3] > canvas.h:
                raise ValueError(f"sprite {name!r}: border {bd} does not fit a {canvas.w}x{canvas.h} sprite")
        if single_name is not None:
            single_name = str(single_name).replace("\\", "/").strip("/")
            if not _SINGLE_RE.match(single_name):
                raise ValueError(f"sprite {name!r}: single_name {single_name!r} must be "
                                 f"[A-Za-z0-9_] path segments joined by '/' (no extension)")
        if fixed is not None:
            fx, fy = int(fixed[0]), int(fixed[1])
            if fx < 0 or fy < 0:
                raise ValueError(f"sprite {name!r}: add_at position must be >= 0, got ({fx}, {fy})")
            if fx + canvas.w > self.max_width:
                raise ValueError(f"sprite {name!r} at x={fx} exceeds max_width {self.max_width}")
            if self.kind in TILE_KINDS and (fx % self.cell_size or fy % self.cell_size):
                raise ValueError(f"sprite {name!r}: add_at position ({fx}, {fy}) is off the "
                                 f"{self.cell_size}px grid of a {self.kind!r} sheet")
            fixed = (fx, fy)
        return SpriteEntry(name, canvas.copy(), pv, bd, solid=solid, overlay=overlay,
                           ground=str(ground or ""), tags=_tags_str(tags),
                           single_name=single_name, fixed=fixed)

    def add(self, name: str, canvas: Canvas, pivot: Optional[Tuple[float, float]] = None,
            border: Optional[Tuple[int, int, int, int]] = None, solid: bool = False,
            overlay: bool = False, ground: str = "", tags: Union[str, Sequence[str]] = "",
            single_name: Optional[str] = None) -> str:
        """Add a sprite (the canvas is copied) to the packed flow. Returns the name.

        pivot    (px, py) or None for the sheet default
        border   9-slice (l, b, r, t) in px for UI frames
        solid / overlay / ground / tags   suggested GPA TileDef values written to the sidecar
        single_name   file name used by save_singles instead of the descriptor; may contain
                      '/' for subfolders ('Status/bleed' -> <out_dir>/Status/bleed.png)
        """
        entry = self._make_entry(name, canvas, pivot, border, solid, overlay, ground, tags,
                                 single_name, None)
        self.sprites.append(entry)
        self._index[name] = entry
        return name

    def add_at(self, name: str, canvas: Canvas, x: int, y: int,
               pivot: Optional[Tuple[float, float]] = None,
               border: Optional[Tuple[int, int, int, int]] = None, solid: bool = False,
               overlay: bool = False, ground: str = "", tags: Union[str, Sequence[str]] = "",
               single_name: Optional[str] = None) -> str:
        """Add a sprite at a FIXED position (x, y) from the top-left of the PNG.

        Fixed sprites must not overlap each other; packed sprites added with add() start on
        the first 16px row below every fixed sprite. Used by character_sheet for the §5.1 grid.
        """
        entry = self._make_entry(name, canvas, pivot, border, solid, overlay, ground, tags,
                                 single_name, (x, y))
        for other in self.sprites:
            if other.fixed is not None and _overlap(entry.fixed + (entry.w, entry.h),
                                                    other.fixed + (other.w, other.h)):
                raise ValueError(f"sprite {name!r} at ({x}, {y}) overlaps fixed sprite {other.name!r}")
        self.sprites.append(entry)
        self._index[name] = entry
        return name

    def add_frames(self, prefix: str, canvases: Sequence[Canvas], **kw) -> List[str]:
        """Add `canvases` as '<prefix>_0', '<prefix>_1', ... (kw as for add) and return the names."""
        return [self.add(f"{prefix}_{i}", c, **kw) for i, c in enumerate(canvases)]

    def add_animation(self, name: str, frames: Sequence[str], fps: float, loop: bool = True,
                      state: str = "", direction: str = "") -> dict:
        """Declare an animation over existing (or later-added) sprite names.

        Unity asset name becomes '<sheet>_<name>'; `direction` is '' for non-directional clips.
        """
        if not _NAME_RE.match(name):
            raise ValueError(f"animation name {name!r} must be lowercase snake_case ASCII")
        if any(a["name"] == name for a in self.animations):
            raise ValueError(f"duplicate animation {name!r} in sheet {self.name!r}")
        if direction not in ("",) + DIRECTIONS:
            raise ValueError(f"animation {name!r}: direction {direction!r} must be '' or one of {DIRECTIONS}")
        frames = [str(f) for f in frames]
        if not frames:
            raise ValueError(f"animation {name!r} needs at least one frame")
        if not fps or fps <= 0:
            raise ValueError(f"animation {name!r}: fps must be > 0")
        anim = OrderedDict([
            ("name", name), ("state", str(state)), ("direction", direction),
            ("fps", _num(fps)), ("loop", bool(loop)), ("frames", frames),
        ])
        self.animations.append(anim)
        return anim

    def add_directional_animation(self, state: str, frames_by_dir: Dict[str, Sequence[str]],
                                  fps: float, loop: bool = True) -> List[dict]:
        """Add '<state>_<dir>' animations for all four directions at once."""
        out = []
        for d in DIRECTIONS:
            if d not in frames_by_dir:
                raise ValueError(f"directional state {state!r} is missing direction {d!r}")
            out.append(self.add_animation(f"{state}_{d}", frames_by_dir[d], fps, loop=loop,
                                          state=state, direction=d))
        return out

    def add_tile(self, name: str, sprite: str, collider: str = "none") -> dict:
        """Declare a plain Tile asset (`name` is the Unity asset name, e.g. 'GrassA')."""
        if collider not in COLLIDERS:
            raise ValueError(f"tile {name!r}: collider {collider!r} must be one of {COLLIDERS}")
        if any(t["name"] == name for t in self.tiles):
            raise ValueError(f"duplicate tile {name!r} in sheet {self.name!r}")
        tile = OrderedDict([("name", str(name)), ("sprite", str(sprite)), ("collider", collider)])
        self.tiles.append(tile)
        return tile

    def add_tile_rule(self, rule_tile: str, sprite: str, mask: int,
                      anim_frames: Optional[Sequence[str]] = None, anim_fps: float = 0) -> dict:
        """Declare one (ruleTile, mask) entry; for animated rules pass all frame names
        (including the first) and anim_fps > 0."""
        mask = int(mask)
        if not is_canonical(mask):
            raise ValueError(f"tile rule {rule_tile!r}: mask {mask} is not canonical (corner bit without both edges)")
        if any(r["ruleTile"] == rule_tile and r["mask"] == mask for r in self.tile_rules):
            raise ValueError(f"duplicate tile rule ({rule_tile!r}, mask {mask}) in sheet {self.name!r}")
        frames = [str(f) for f in (anim_frames or [])]
        if frames and (not anim_fps or anim_fps <= 0):
            raise ValueError(f"tile rule {rule_tile!r} mask {mask}: animFrames given but animFps <= 0")
        if frames and frames[0] != sprite:
            raise ValueError(f"tile rule {rule_tile!r} mask {mask}: first animFrame must be the sprite itself")
        rule = OrderedDict([
            ("ruleTile", str(rule_tile)), ("sprite", str(sprite)), ("mask", mask),
            ("animFrames", frames), ("animFps", _num(anim_fps) if frames else 0),
        ])
        self.tile_rules.append(rule)
        return rule

    def set_rule_tile_default(self, rule_tile: str, default_sprite: str, collider: str = "none") -> dict:
        """Default sprite + collider for a RuleTile asset (one entry per ruleTile)."""
        if collider not in COLLIDERS:
            raise ValueError(f"rule tile {rule_tile!r}: collider {collider!r} must be one of {COLLIDERS}")
        entry = OrderedDict([("ruleTile", str(rule_tile)), ("defaultSprite", str(default_sprite)),
                             ("collider", collider)])
        self.rule_tile_defaults = [d for d in self.rule_tile_defaults if d["ruleTile"] != rule_tile]
        self.rule_tile_defaults.append(entry)
        return entry

    def add_blob(self, rule_tile: str, name_prefix: str, blob: List[Tuple[int, List[Canvas]]],
                 collider: str = "none", anim_fps: float = 0, default_mask: int = 255,
                 pivot=None, **kw) -> List[str]:
        """Add a blob47() result: sprites '<prefix>_m<mask>' (animated: '<prefix>_m<mask>_f<i>'),
        one tile rule per mask and the rule-tile default (§2.2 naming). kw as for add().
        Returns the first-frame names."""
        first_names = []
        for mask, frames in blob:
            if len(frames) == 1:
                name = f"{name_prefix}_m{mask}"
                self.add(name, frames[0], pivot=pivot, **kw)
                self.add_tile_rule(rule_tile, name, mask)
            else:
                if not anim_fps or anim_fps <= 0:
                    raise ValueError("animated blob needs anim_fps > 0")
                names = [self.add(f"{name_prefix}_m{mask}_f{i}", c, pivot=pivot, **kw)
                         for i, c in enumerate(frames)]
                name = names[0]
                self.add_tile_rule(rule_tile, name, mask, anim_frames=names, anim_fps=anim_fps)
            if mask == default_mask:
                self.set_rule_tile_default(rule_tile, name, collider=collider)
            first_names.append(name)
        return first_names

    def set_strip(self, frames: int, fps: float) -> None:
        """Mark this sheet as an FX strip: every sprite is laid out in ONE row in insertion
        order and the sidecar records stripFrames/stripFps. The PNG is exactly frames*w x h
        (frames must all share one size); save() validates that the sprite count == frames."""
        frames = int(frames)
        if frames < 1:
            raise ValueError("strip frames must be >= 1")
        if fps is None or float(fps) < 0:
            raise ValueError("strip fps must be >= 0 (0 = still image)")
        self.strip_frames = frames
        self.strip_fps = _num(fps)

    # --- packing --------------------------------------------------------------------
    def layout(self) -> List[Tuple[str, int, int, int, int]]:
        """[(name, x, y, w, h), ...] in insertion order (see class docstring for the rules)."""
        pos: Dict[str, Tuple[int, int]] = {}
        y0 = 0
        for e in self.sprites:
            if e.fixed is not None:
                pos[e.name] = e.fixed
                y0 = max(y0, _round_up(e.fixed[1] + e.h, self.cell_size))
        flow = [e for e in self.sprites if e.fixed is None]
        if self.is_strip:
            x = 0
            for e in flow:
                pos[e.name] = (x, y0)
                x += e.w
        else:
            x = 0
            y = y0
            row_h = 0
            row_count = 0
            for e in flow:
                w, h = e.w, e.h
                new_row = row_count > 0 and (
                    h != row_h or x + w > self.max_width
                    or (self.columns is not None and row_count >= self.columns))
                if new_row:
                    y += row_h
                    x = 0
                    row_count = 0
                if row_count == 0:
                    row_h = h
                pos[e.name] = (x, y)
                x += w
                row_count += 1
        return [(e.name, pos[e.name][0], pos[e.name][1], e.w, e.h) for e in self.sprites]

    def rects(self) -> Dict[str, Tuple[int, int, int, int]]:
        """{name: (x, y, w, h)} of the current layout."""
        return {n: (x, y, w, h) for n, x, y, w, h in self.layout()}

    def png_size(self) -> Tuple[int, int]:
        """Size of the packed PNG: bounding box rounded up to a multiple of cell_size (16),
        or exactly frames*w x h for a strip. (0, 0) for an empty sheet."""
        rects = self.layout()
        if not rects:
            return (0, 0)
        w = max(x + rw for _, x, _, rw, _ in rects)
        h = max(y + rh for _, _, y, _, rh in rects)
        if not self.is_strip:
            w, h = _round_up(w, self.cell_size), _round_up(h, self.cell_size)
        if self.min_size is not None:
            w, h = max(w, self.min_size[0]), max(h, self.min_size[1])
        return (w, h)

    def render(self) -> Canvas:
        """The packed sheet as one Canvas."""
        if not self.sprites:
            raise ValueError(f"sheet {self.name!r} has no sprites")
        W, H = self.png_size()
        out = Canvas(W, H)
        for (name, x, y, _, _) in self.layout():
            out.blit(self._index[name].canvas, x, y)
        return out

    # --- sidecar --------------------------------------------------------------------
    def to_json_dict(self) -> "OrderedDict[str, object]":
        """The sidecar document (spec §3 v2 shape and field order)."""
        cs = self.cell_size
        sprites = []
        for (name, x, y, w, h) in self.layout():
            e = self._index[name]
            l, b, r, t = e.border
            sprites.append(OrderedDict([
                ("name", name), ("x", int(x)), ("y", int(y)), ("w", int(w)), ("h", int(h)),
                ("pivotX", float(e.pivot[0])), ("pivotY", float(e.pivot[1])),
                ("borderL", int(l)), ("borderB", int(b)), ("borderR", int(r)), ("borderT", int(t)),
                ("cellX", int(x) // cs), ("cellY", int(y) // cs),
                ("cellW", -(-int(w) // cs)), ("cellH", -(-int(h) // cs)),
                ("solid", bool(e.solid)), ("overlay", bool(e.overlay)),
                ("ground", str(e.ground)), ("tags", str(e.tags)),
            ]))
        return OrderedDict([
            ("version", SIDECAR_VERSION),
            ("sheet", self.name),
            ("kind", self.kind),
            ("pixelsPerUnit", self.pixels_per_unit),
            ("defaultPivotX", float(self.pivot[0])),
            ("defaultPivotY", float(self.pivot[1])),
            ("cellSize", cs),
            ("stripFrames", int(self.strip_frames)),
            ("stripFps", _num(self.strip_fps)),
            ("sprites", sprites),
            ("animations", [OrderedDict(a) for a in self.animations]),
            ("tiles", [OrderedDict(t) for t in self.tiles]),
            ("tileRules", [OrderedDict(r) for r in self.tile_rules]),
            ("ruleTileDefaults", [OrderedDict(d) for d in self.rule_tile_defaults]),
        ])

    def to_json(self) -> str:
        """Deterministic 2-space-indented sidecar text."""
        return json.dumps(self.to_json_dict(), indent=2) + "\n"

    # --- validation / IO ------------------------------------------------------------
    def validate(self, strict: bool = True) -> List[str]:
        """Return a list of problems (empty when the sheet is consistent with spec §3/§5).

        Runs the same checker as check_sheet() on the in-memory sidecar plus in-memory-only
        checks (empty sheet, fixed-sprite overlap, max_width). strict=False relaxes the
        'complete' checks (47 masks per ruleTile, all four directions per state, fx must be a
        strip, character/face layout) for work-in-progress saves.
        """
        problems: List[str] = []
        if not self.sprites:
            problems.append("sheet has no sprites")
            return problems
        W, H = self.png_size()
        if W > self.max_width:
            problems.append(f"packed width {W} exceeds max_width {self.max_width}")
        fixed = [e for e in self.sprites if e.fixed is not None]
        for i, a in enumerate(fixed):
            for b in fixed[i + 1:]:
                if _overlap(a.fixed + (a.w, a.h), b.fixed + (b.w, b.h)):
                    problems.append(f"fixed sprites {a.name!r} and {b.name!r} overlap")
        problems.extend(check_sidecar(self.to_json_dict(), W, H, file_base=self.file_name, strict=strict))
        return problems

    def validate_character(self) -> List[str]:
        """Reviewer helper: problems with this sheet as a §5.1 character sheet (128x64, the
        column/row layout, sprite names, animations, pivot). Empty list = compliant.
        For a saved sheet use `Sheet.load(png).validate_character()` or check_character_sheet()."""
        W, H = self.png_size()
        return _check_character(self.to_json_dict(), W, H)

    def save(self, out_dir: str, strict: bool = True) -> Tuple[str, str]:
        """Write <out_dir>/<file_name>.png and <out_dir>/<file_name>.sprites.json.

        Raises ValueError (listing every problem) when validate(strict) finds any.
        Returns (png_path, json_path). Output is byte-deterministic.
        """
        problems = self.validate(strict=strict)
        if problems:
            raise ValueError(f"sheet {self.name!r} is not valid:\n  - " + "\n  - ".join(problems))
        os.makedirs(out_dir, exist_ok=True)
        png_path = os.path.join(out_dir, f"{self.file_name}.png")
        json_path = os.path.join(out_dir, f"{self.file_name}.sprites.json")
        self.render().save(png_path)
        with open(json_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.to_json())
        return png_path, json_path

    def save_singles(self, out_dir: str, names: Optional[Iterable[str]] = None) -> List[str]:
        """Write one PNG per sprite: <out_dir>/<descriptor>.png, or <out_dir>/<single_name>.png
        when the sprite was added with single_name (subfolders are created). Returns the paths.
        Icons, Icons/Mini, UI/Status, UI/Markers and UI/Frames are shipped this way (§1)."""
        entries = self.sprites if names is None else [self._index[n] for n in names]
        seen: Dict[str, str] = {}
        for e in entries:
            rel = self.single_file_name(e.name)
            key = rel.lower()
            if key in seen:
                raise ValueError(f"save_singles: sprites {seen[key]!r} and {e.name!r} both map to {rel!r}")
            seen[key] = e.name
        out: List[str] = []
        for e in entries:
            path = os.path.join(out_dir, *self.single_file_name(e.name).split("/"))
            e.canvas.save(path)
            out.append(path)
        return out

    @classmethod
    def load(cls, png_path: str, json_path: Optional[str] = None) -> "Sheet":
        """Rebuild a Sheet from a saved PNG + sidecar (every sprite becomes a fixed sprite at
        its recorded rect, the PNG size is kept). Lets reviewers preview / validate / re-save
        shipped sheets: `Sheet.load(p).validate_character()`, `.preview(...)`, `.cellmap(...)`."""
        if json_path is None:
            json_path = sidecar_path(png_path)
        doc = load_sidecar(json_path)
        img = Canvas.load(png_path)
        base = os.path.splitext(os.path.basename(png_path))[0]
        name, kind = doc["sheet"], doc["kind"]
        file_name = base if base in _allowed_file_bases(name) else None
        s = cls(name, kind, pivot=(doc.get("defaultPivotX", 0.5), doc.get("defaultPivotY", 0.0)),
                cell_size=int(doc.get("cellSize", CELL_SIZE) or CELL_SIZE), file_name=file_name,
                strict_names=False)
        for sp in doc["sprites"]:
            c = img.cropped(sp["x"], sp["y"], sp["w"], sp["h"])
            s.add_at(sp["name"], c, sp["x"], sp["y"],
                     pivot=(sp.get("pivotX", s.pivot[0]), sp.get("pivotY", s.pivot[1])),
                     border=(sp.get("borderL", 0), sp.get("borderB", 0), sp.get("borderR", 0), sp.get("borderT", 0)),
                     solid=sp.get("solid", False), overlay=sp.get("overlay", False),
                     ground=sp.get("ground", ""), tags=sp.get("tags", ""))
        for a in doc.get("animations", []):
            s.add_animation(a["name"], a["frames"], a["fps"], loop=a.get("loop", True),
                            state=a.get("state", ""), direction=a.get("direction", ""))
        for t in doc.get("tiles", []):
            s.add_tile(t["name"], t["sprite"], t.get("collider", "none"))
        for r in doc.get("tileRules", []):
            s.add_tile_rule(r["ruleTile"], r["sprite"], r["mask"], r.get("animFrames") or None,
                            r.get("animFps", 0))
        for d in doc.get("ruleTileDefaults", []):
            s.set_rule_tile_default(d["ruleTile"], d["defaultSprite"], d.get("collider", "none"))
        if doc.get("stripFrames", 0):
            s.set_strip(doc["stripFrames"], doc.get("stripFps", 0))
        s.min_size = (img.w, img.h)
        return s

    # --- previews -------------------------------------------------------------------
    def preview(self, path: str, scale: int = 4, labels: bool = True, max_width: int = 1024,
                names: Optional[Iterable[str]] = None) -> str:
        """Upscaled contact sheet for human review: every sprite (nearest-neighbour scaled)
        on a dark checkerboard with its name beneath (3x5 debug font), in a grid. Returns `path`."""
        entries = self.sprites if names is None else [self._index[n] for n in names]
        title = f"{self.file_name}  kind={self.kind}  sprites={len(self.sprites)}  png={'x'.join(map(str, self.png_size()))}"
        if names is not None:
            title += f"  shown={len(entries)}"
        img = _render_preview(entries, scale=scale, labels=labels, max_width=max_width, title=title)
        return img.save(path)

    def preview_group(self, path: str, prefix: str, scale: int = 8, labels: bool = True,
                      max_width: int = 1024) -> str:
        """Preview only the sprites whose names start with `prefix`, at a larger scale."""
        sel = [e.name for e in self.sprites if e.name.startswith(prefix)]
        if not sel:
            raise ValueError(f"no sprite in {self.name!r} starts with {prefix!r}")
        return self.preview(path, scale=scale, labels=labels, max_width=max_width, names=sel)

    def cellmap(self, png_path: str, md_path: str, scale: int = 3) -> Tuple[str, str]:
        """Cell map for tile sheets (§2.3): the sheet at `scale` with 1px `ink_pale` grid lines
        every cell, each sprite outlined, an "x,y" cell label in its top-left cell and its name
        beneath; plus a markdown table (name | cell x,y | size | solid | overlay | ground | tags).
        Returns (png_path, md_path)."""
        scale = max(1, int(scale))
        cs = self.cell_size
        sheet = self.render()
        W, H = sheet.w, sheet.h
        img = Canvas(W * scale, H * scale, fill=_CM_BG)
        img.blit(sheet.scaled(scale), 0, 0)
        for gx in range(0, W + 1, cs):
            img.vline(min(gx * scale, W * scale - 1), 0, H * scale - 1, "ink_pale")
        for gy in range(0, H + 1, cs):
            img.hline(0, W * scale - 1, min(gy * scale, H * scale - 1), "ink_pale")
        rows_md = []
        for (name, x, y, w, h) in self.layout():
            e = self._index[name]
            sx, sy, sw, sh = x * scale, y * scale, w * scale, h * scale
            img.rect(sx, sy, sw, sh, _CM_RECT, fill=False)
            ty = sy + 2
            ty = _stamp_label(img, f"{x // cs},{y // cs}", sx + 2, ty, sx + sw - 1, sy + sh - 1)
            cpl = max(1, (sw - 4) // FONT_3X5_ADVANCE)
            for line in _wrap_label(name, cpl, max_lines=8):
                if ty + 5 > sy + sh - 1:
                    break
                ty = _stamp_label(img, line, sx + 2, ty, sx + sw - 1, sy + sh - 1)
            size = f"{-(-w // cs)}x{-(-h // cs)}"
            rows_md.append(f"| {name} | {x // cs},{y // cs} | {size} | {'yes' if e.solid else 'no'} | "
                           f"{'yes' if e.overlay else 'no'} | {e.ground} | {e.tags} |")
        img.save(png_path)
        md = [
            f"# {self.file_name} cell map",
            "",
            f"Sheet `{self.name}` (kind `{self.kind}`), PNG {W}x{H} px, cell {cs} px, "
            f"{len(self.sprites)} sprites. Cells are counted from the TOP-LEFT; size is in cells.",
            "",
            "| name | cell x,y | size | solid | overlay | ground | tags |",
            "|---|---|---|---|---|---|---|",
        ] + rows_md + [""]
        d = os.path.dirname(md_path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(md_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(md))
        return png_path, md_path


def _overlap(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def sidecar_path(png_path: str) -> str:
    """'<dir>/<base>.png' -> '<dir>/<base>.sprites.json'."""
    base = png_path[:-4] if png_path.lower().endswith(".png") else png_path
    return base + ".sprites.json"


# ------------------------------------------------------------------------------------------
# character_sheet (spec §5.1)
# ------------------------------------------------------------------------------------------
def _frames16(name: str, what: str, d: str, canvases, count: int) -> List[Canvas]:
    try:
        lst = list(canvases)
    except TypeError:
        raise TypeError(f"{name}: {what}[{d!r}] must be a sequence of {count} Canvas") from None
    if len(lst) != count:
        raise ValueError(f"{name}: {what}[{d!r}] must have exactly {count} frames, got {len(lst)}")
    for i, c in enumerate(lst):
        if not isinstance(c, Canvas):
            raise TypeError(f"{name}: {what}[{d!r}][{i}] is not a Canvas")
        if c.size != (FRAME_SIZE, FRAME_SIZE):
            raise ValueError(f"{name}: {what}[{d!r}][{i}] is {c.w}x{c.h}, must be {FRAME_SIZE}x{FRAME_SIZE}")
    return lst


def character_sheet(name: str, walk: Dict[str, Sequence[Canvas]],
                    attack: Dict[str, Sequence[Canvas]], hurt: Dict[str, Canvas],
                    face: Optional[Canvas] = None) -> Tuple[Sheet, Optional[Sheet]]:
    """Build the §5.1 character sheet (and face sheet) with fixed placement.

    walk   {dir: [4 Canvas 16x16]}   columns 0-3 (down, up, left, right), rows 0-3 = frames
    attack {dir: [3 Canvas 16x16]}   columns 4-7, rows 0-2 = wind-up, strike, recover
    hurt   {dir: Canvas 16x16}       columns 4-7, row 3
    face   Canvas 32x32 or None      -> Sheet '<name>_face' (kind face, sprite '<name>_face')

    Sprite names '<name>_walk_<dir>_<i>', '<name>_attack_<dir>_<i>', '<name>_hurt_<dir>'.
    Animations walk_<dir> (8 fps loop), attack_<dir> (12 fps, no loop), idle_<dir> (1 frame =
    walk_<dir>_0), hurt_<dir> (1 frame). Pivot (0.5, 0). The PNG is exactly 128x64.
    Returns (sheet, face_sheet); face_sheet is None when no face is given.
    """
    if not _NAME_RE.match(name):
        raise ValueError(f"character name {name!r} must be lowercase snake_case ASCII")
    for what, src in (("walk", walk), ("attack", attack), ("hurt", hurt)):
        missing = [d for d in DIRECTIONS if d not in src]
        if missing:
            raise ValueError(f"{name}: {what} is missing directions {missing}")
    sheet = Sheet(name, "character", pivot=(0.5, 0.0))
    fs = FRAME_SIZE
    for di, d in enumerate(DIRECTIONS):
        for i, c in enumerate(_frames16(name, "walk", d, walk[d], WALK_FRAMES)):
            sheet.add_at(f"{name}_walk_{d}_{i}", c, di * fs, i * fs, tags=f"walk,{d}")
    for di, d in enumerate(DIRECTIONS):
        for i, c in enumerate(_frames16(name, "attack", d, attack[d], ATTACK_FRAMES)):
            sheet.add_at(f"{name}_attack_{d}_{i}", c, (4 + di) * fs, i * fs, tags=f"attack,{d}")
    for di, d in enumerate(DIRECTIONS):
        c = _frames16(name, "hurt", d, [hurt[d]], 1)[0]
        sheet.add_at(f"{name}_hurt_{d}", c, (4 + di) * fs, 3 * fs, tags=f"hurt,{d}")
    for d in DIRECTIONS:
        sheet.add_animation(f"walk_{d}", [f"{name}_walk_{d}_{i}" for i in range(WALK_FRAMES)],
                            WALK_FPS, loop=True, state="walk", direction=d)
    for d in DIRECTIONS:
        sheet.add_animation(f"attack_{d}", [f"{name}_attack_{d}_{i}" for i in range(ATTACK_FRAMES)],
                            ATTACK_FPS, loop=False, state="attack", direction=d)
    for d in DIRECTIONS:
        sheet.add_animation(f"idle_{d}", [f"{name}_walk_{d}_0"], 1, loop=True, state="idle", direction=d)
    for d in DIRECTIONS:
        sheet.add_animation(f"hurt_{d}", [f"{name}_hurt_{d}"], 1, loop=False, state="hurt", direction=d)
    assert sheet.png_size() == CHARACTER_SHEET_SIZE
    face_sheet = None
    if face is not None:
        if not isinstance(face, Canvas):
            raise TypeError(f"{name}: face must be a Canvas")
        if face.size != FACE_SIZE:
            raise ValueError(f"{name}: face is {face.w}x{face.h}, must be {FACE_SIZE[0]}x{FACE_SIZE[1]}")
        face_sheet = Sheet(f"{name}_face", "face", pivot=(0.5, 0.0))
        face_sheet.add_at(f"{name}_face", face, 0, 0, tags="face")
    return sheet, face_sheet


def _expected_character(sheet_name: str) -> "OrderedDict[str, Tuple[int, int]]":
    """{sprite name: (x, y)} of the §5.1 grid for a character sheet."""
    fs = FRAME_SIZE
    exp: "OrderedDict[str, Tuple[int, int]]" = OrderedDict()
    for di, d in enumerate(DIRECTIONS):
        for i in range(WALK_FRAMES):
            exp[f"{sheet_name}_walk_{d}_{i}"] = (di * fs, i * fs)
    for di, d in enumerate(DIRECTIONS):
        for i in range(ATTACK_FRAMES):
            exp[f"{sheet_name}_attack_{d}_{i}"] = ((4 + di) * fs, i * fs)
    for di, d in enumerate(DIRECTIONS):
        exp[f"{sheet_name}_hurt_{d}"] = ((4 + di) * fs, 3 * fs)
    return exp


def _expected_character_anims(sheet_name: str) -> Dict[str, dict]:
    exp: Dict[str, dict] = {}
    for d in DIRECTIONS:
        exp[f"walk_{d}"] = dict(fps=WALK_FPS, loop=True, state="walk", direction=d,
                                frames=[f"{sheet_name}_walk_{d}_{i}" for i in range(WALK_FRAMES)])
        exp[f"attack_{d}"] = dict(fps=ATTACK_FPS, loop=False, state="attack", direction=d,
                                  frames=[f"{sheet_name}_attack_{d}_{i}" for i in range(ATTACK_FRAMES)])
        exp[f"idle_{d}"] = dict(fps=None, loop=None, state="idle", direction=d,
                                frames=[f"{sheet_name}_walk_{d}_0"])
        exp[f"hurt_{d}"] = dict(fps=None, loop=None, state="hurt", direction=d,
                                frames=[f"{sheet_name}_hurt_{d}"])
    return exp


def _check_character(doc: dict, W: int, H: int) -> List[str]:
    """§5.1 layout problems of a character sidecar document rendered at W x H."""
    problems: List[str] = []
    sheet_name = str(doc.get("sheet", ""))
    if doc.get("kind") != "character":
        problems.append(f"kind is {doc.get('kind')!r}, expected 'character'")
    if (W, H) != CHARACTER_SHEET_SIZE:
        problems.append(f"character PNG is {W}x{H}, must be {CHARACTER_SHEET_SIZE[0]}x{CHARACTER_SHEET_SIZE[1]}")
    expected = _expected_character(sheet_name)
    have = {s.get("name"): s for s in doc.get("sprites", [])}
    for n, (ex, ey) in expected.items():
        s = have.get(n)
        if s is None:
            problems.append(f"missing character sprite {n!r}")
            continue
        rect = (s.get("x"), s.get("y"), s.get("w"), s.get("h"))
        if rect != (ex, ey, FRAME_SIZE, FRAME_SIZE):
            problems.append(f"sprite {n!r} rect {rect} must be ({ex}, {ey}, {FRAME_SIZE}, {FRAME_SIZE})")
        if (s.get("pivotX"), s.get("pivotY")) != (0.5, 0.0):
            problems.append(f"sprite {n!r} pivot must be (0.5, 0.0)")
    extra = sorted(set(have) - set(expected))
    if extra:
        problems.append(f"unexpected sprites on a character sheet: {extra}")
    if (doc.get("defaultPivotX"), doc.get("defaultPivotY")) != (0.5, 0.0):
        problems.append("character sheet default pivot must be (0.5, 0.0)")
    anims = {a.get("name"): a for a in doc.get("animations", [])}
    for n, spec in _expected_character_anims(sheet_name).items():
        a = anims.get(n)
        if a is None:
            problems.append(f"missing animation {n!r}")
            continue
        if list(a.get("frames", [])) != spec["frames"]:
            problems.append(f"animation {n!r} frames {a.get('frames')} must be {spec['frames']}")
        if spec["fps"] is not None and a.get("fps") != spec["fps"]:
            problems.append(f"animation {n!r} fps {a.get('fps')} must be {spec['fps']}")
        if spec["loop"] is not None and bool(a.get("loop")) != spec["loop"]:
            problems.append(f"animation {n!r} loop must be {spec['loop']}")
        if a.get("state") != spec["state"] or a.get("direction") != spec["direction"]:
            problems.append(f"animation {n!r} must have state {spec['state']!r} and direction {spec['direction']!r}")
    return problems


def _check_face(doc: dict, W: int, H: int) -> List[str]:
    problems: List[str] = []
    if (W, H) != FACE_SIZE:
        problems.append(f"face PNG is {W}x{H}, must be {FACE_SIZE[0]}x{FACE_SIZE[1]}")
    sprites = doc.get("sprites", [])
    sheet_name = doc.get("sheet")
    if len(sprites) != 1:
        problems.append(f"face sheet must hold exactly one sprite, has {len(sprites)}")
    else:
        s = sprites[0]
        if s.get("name") != sheet_name:
            problems.append(f"face sprite must be named {sheet_name!r}, is {s.get('name')!r}")
        if (s.get("x"), s.get("y"), s.get("w"), s.get("h")) != (0, 0, FACE_SIZE[0], FACE_SIZE[1]):
            problems.append("face sprite must cover the whole 32x32 PNG")
    if not str(sheet_name).endswith("_face"):
        problems.append(f"face sheet name {sheet_name!r} must end with '_face'")
    return problems


# ------------------------------------------------------------------------------------------
# Previews / cell maps (never shipped: free colors)
# ------------------------------------------------------------------------------------------
_PV_BG = (20, 21, 28)
_PV_CHECK_A = (58, 59, 71)
_PV_CHECK_B = (42, 43, 53)
_PV_FRAME = (88, 92, 112)
_PV_TEXT = (216, 220, 232)
_PV_TITLE = (255, 214, 120)
_CM_BG = (36, 34, 40)
_CM_RECT = "vermilion_light"


def _wrap_label(name: str, chars_per_line: int, max_lines: int = 3) -> List[str]:
    chars_per_line = max(1, chars_per_line)
    lines = [name[i:i + chars_per_line] for i in range(0, len(name), chars_per_line)]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:max(0, chars_per_line - 1)] + "~"
    return lines


def _stamp_label(img: Canvas, text: str, x: int, y: int, max_x: int, max_y: int) -> int:
    """Stamp `text` (paper_light on a 1px ink_black halo) clipped to (max_x, max_y);
    returns the y of the next line."""
    tw = text_width(text)
    box = Canvas(tw + 2, 7)
    box.stamp(text, 1, 1, "paper_light")
    box = box.outlined("ink_black", diagonal=True)
    clip_w = min(box.w, max_x - (x - 1) + 1)
    clip_h = min(box.h, max_y - (y - 1) + 1)
    if clip_w > 0 and clip_h > 0:
        img.blit(box.cropped(0, 0, clip_w, clip_h), x - 1, y - 1)
    return y + 6


def _render_preview(entries: Sequence[SpriteEntry], scale: int = 4, labels: bool = True,
                    max_width: int = 1024, title: str = "") -> Canvas:
    scale = max(1, int(scale))
    margin, pad = 8, 4
    ls = max(1, scale // 4)                  # label font scale
    ts = 2                                   # title font scale
    title_h = (7 * ts + 6) if title else 0
    checker = max(2, scale * 2)

    # measure cells
    cells = []  # (entry, cell_w, cell_h, sprite_w, sprite_h, label_lines)
    for e in entries:
        sw, sh = e.w * scale, e.h * scale
        cell_w = max(sw, 16 * scale)
        lines: List[str] = []
        label_h = 0
        if labels:
            cpl = cell_w // (FONT_3X5_ADVANCE * ls)
            lines = _wrap_label(e.name, cpl)
            label_h = len(lines) * 6 * ls + 2
        cells.append((e, cell_w, sh + 2 + label_h, sw, sh, lines))

    # row packing (left-to-right, wrap at max_width)
    rows: List[List[tuple]] = []
    row: List[tuple] = []
    x = margin
    usable = max(max_width, margin * 2 + max((c[1] for c in cells), default=0) + pad * 2)
    for c in cells:
        cw = c[1] + pad * 2
        if row and x + cw > usable - margin:
            rows.append(row)
            row = []
            x = margin
        row.append(c)
        x += cw
    if row:
        rows.append(row)

    row_heights = [max(c[2] for c in r) + pad * 2 for r in rows] if rows else []
    width = max([margin * 2 + sum(c[1] + pad * 2 for c in r) for r in rows] + [text_width(title, ts) + margin * 2, 64])
    height = margin * 2 + title_h + sum(row_heights)
    img = Canvas(width, height, fill=_PV_BG)
    if title:
        img.stamp(title, margin, margin, _PV_TITLE, scale=ts)

    y = margin + title_h
    for r, rh in zip(rows, row_heights):
        x = margin
        for (e, cell_w, cell_h, sw, sh, lines) in r:
            cx = x + pad
            cy = y + pad
            sx = cx + (cell_w - sw) // 2
            # checkerboard behind the sprite rect
            for by in range(0, sh, checker):
                for bx in range(0, sw, checker):
                    col = _PV_CHECK_A if ((bx // checker + by // checker) % 2 == 0) else _PV_CHECK_B
                    img.rect(sx + bx, cy + by, min(checker, sw - bx), min(checker, sh - by), col)
            img.rect(sx - 1, cy - 1, sw + 2, sh + 2, _PV_FRAME, fill=False)
            img.blit(e.canvas.scaled(scale), sx, cy)
            if labels:
                ly = cy + sh + 2
                for line in lines:
                    lx = cx + (cell_w - text_width(line, ls)) // 2
                    img.stamp(line, lx, ly, _PV_TEXT, scale=ls)
                    ly += 6 * ls
            x += cell_w + pad * 2
        y += rh
    return img


# ------------------------------------------------------------------------------------------
# Reviewer helpers (spec §9)
# ------------------------------------------------------------------------------------------
_PALETTE_INTS = np.array([(r << 16) | (g << 8) | b for r, g, b in COLORS], dtype=np.int64)


def _as_rgba_array(src) -> np.ndarray:
    if isinstance(src, Canvas):
        return src.px
    if isinstance(src, Image.Image):
        return np.asarray(src.convert("RGBA"))
    if isinstance(src, np.ndarray):
        if src.ndim == 3 and src.shape[2] == 4:
            return src
        raise ValueError("expected an (H, W, 4) array")
    with Image.open(str(src)) as img:
        return np.asarray(img.convert("RGBA"))


def verify_palette(png_path, max_results: Optional[int] = None) -> List[Tuple[int, int, RGBA]]:
    """Return offending pixels [(x, y, (r, g, b, a)), ...] in row-major order.

    A pixel offends when its alpha is neither 0 nor 255, or when it is opaque and its RGB is
    not one of the 32 palette colors. Fully transparent pixels are never reported, whatever
    their RGB. Accepts a path, a PIL image, a Canvas or an (H, W, 4) array. Empty = compliant.
    """
    arr = _as_rgba_array(png_path)
    a = arr[..., 3].astype(np.int64)
    rgb = (arr[..., 0].astype(np.int64) << 16) | (arr[..., 1].astype(np.int64) << 8) | arr[..., 2].astype(np.int64)
    bad = ((a != 0) & (a != 255)) | ((a == 255) & ~np.isin(rgb, _PALETTE_INTS))
    ys, xs = np.nonzero(bad)
    out = []
    for yy, xx in zip(ys, xs):
        out.append((int(xx), int(yy), tuple(int(v) for v in arr[yy, xx])))
        if max_results is not None and len(out) >= max_results:
            break
    return out  # type: ignore[return-value]


def load_sidecar(json_path: str) -> dict:
    with open(json_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


_SIDECAR_KEYS = ("version", "sheet", "kind", "pixelsPerUnit", "defaultPivotX", "defaultPivotY",
                 "cellSize", "stripFrames", "stripFps", "sprites", "animations", "tiles",
                 "tileRules", "ruleTileDefaults")
_SPRITE_KEYS = ("name", "x", "y", "w", "h", "pivotX", "pivotY", "borderL", "borderB", "borderR",
                "borderT", "cellX", "cellY", "cellW", "cellH", "solid", "overlay", "ground", "tags")


def check_sidecar(doc: dict, width: int, height: int, file_base: Optional[str] = None,
                  strict: bool = True) -> List[str]:
    """Problems of a sidecar document (§3 v2) for a PNG of `width` x `height`.

    Checks: keys and version, kind, pixelsPerUnit/cellSize, file name <-> sheet name, sprite
    fields, unique prefixed snake_case names, rects in bounds, 9-slice borders, tile sheets on
    the 16px grid with consistent cell fields, animations (frames exist, fps, directions
    complete), tiles, tileRules (canonical, 47 masks per ruleTile, defaults), strip layout
    (count, equal frames, one row, PNG == frames*w x h; fx sheets must be strips), the §5.1
    character layout and the 32x32 face layout. `strict=False` skips the completeness rules.
    """
    problems: List[str] = []
    for key in _SIDECAR_KEYS:
        if key not in doc:
            problems.append(f"sidecar missing key {key!r}")
    if problems:
        return problems
    if doc["version"] != SIDECAR_VERSION:
        problems.append(f"sidecar version is {doc['version']!r}, expected {SIDECAR_VERSION}")
    sheet = doc["sheet"]
    kind = doc["kind"]
    if not isinstance(sheet, str) or not _NAME_RE.match(sheet):
        problems.append(f"sheet name {sheet!r} is not lowercase snake_case")
        sheet = str(sheet)
    if kind not in SHEET_KINDS:
        problems.append(f"unknown kind {kind!r} (expected one of {SHEET_KINDS})")
    if doc["pixelsPerUnit"] != PIXELS_PER_UNIT:
        problems.append(f"pixelsPerUnit is {doc['pixelsPerUnit']!r}, expected {PIXELS_PER_UNIT}")
    cs = doc["cellSize"]
    if not isinstance(cs, int) or cs < 1:
        problems.append(f"cellSize {cs!r} must be a positive int")
        cs = CELL_SIZE
    elif cs != CELL_SIZE:
        problems.append(f"cellSize is {cs}, the pack uses {CELL_SIZE}")
    if file_base is not None and file_base not in _allowed_file_bases(sheet):
        problems.append(f"file name {file_base!r} does not match sheet {sheet!r} "
                        f"(expected one of {_allowed_file_bases(sheet)})")
    if width > MAX_SHEET_WIDTH:
        problems.append(f"PNG width {width} > {MAX_SHEET_WIDTH}")
    if not isinstance(doc["sprites"], list) or not doc["sprites"]:
        problems.append("sidecar has no sprites")

    names: set = set()
    for s in doc["sprites"]:
        n = s.get("name")
        missing = [k for k in _SPRITE_KEYS if k not in s]
        if missing:
            problems.append(f"sprite {n!r} missing fields {missing}")
        if n in names:
            problems.append(f"duplicate sprite name {n!r}")
        names.add(n)
        if not isinstance(n, str) or not _NAME_RE.match(n) or not (n == sheet or n.startswith(sheet + "_")):
            problems.append(f"sprite name {n!r} is not snake_case with the '{sheet}_' prefix")
        x, y, w, h = (s.get(k, 0) for k in ("x", "y", "w", "h"))
        if not all(isinstance(v, int) for v in (x, y, w, h)):
            problems.append(f"sprite {n!r} rect must be ints")
            continue
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > width or y + h > height:
            problems.append(f"sprite {n!r} rect ({x},{y},{w},{h}) is outside the {width}x{height} PNG")
        if s.get("borderL", 0) + s.get("borderR", 0) > w or s.get("borderB", 0) + s.get("borderT", 0) > h:
            problems.append(f"sprite {n!r} 9-slice border exceeds its size")
        if min(s.get("borderL", 0), s.get("borderB", 0), s.get("borderR", 0), s.get("borderT", 0)) < 0:
            problems.append(f"sprite {n!r} has a negative 9-slice border")
        if kind in TILE_KINDS:
            if x % cs or y % cs or w % cs or h % cs:
                problems.append(f"sprite {n!r} rect ({x},{y},{w},{h}) is not aligned to the {cs}px grid")
            cell = (s.get("cellX"), s.get("cellY"), s.get("cellW"), s.get("cellH"))
            if cell != (x // cs, y // cs, w // cs, h // cs):
                problems.append(f"sprite {n!r} cell fields {cell} do not match its rect")
        if not isinstance(s.get("solid"), bool) or not isinstance(s.get("overlay"), bool):
            problems.append(f"sprite {n!r} solid/overlay must be booleans")
        if not isinstance(s.get("ground"), str) or not isinstance(s.get("tags"), str):
            problems.append(f"sprite {n!r} ground/tags must be strings")
        if s.get("ground") and s["ground"] not in names and not _NAME_RE.match(str(s["ground"])):
            problems.append(f"sprite {n!r} ground {s['ground']!r} is not a sprite name")

    anim_names: set = set()
    states: Dict[str, set] = {}
    for a in doc["animations"]:
        an = a.get("name")
        if an in anim_names:
            problems.append(f"duplicate animation {an!r}")
        anim_names.add(an)
        if not isinstance(an, str) or not _NAME_RE.match(an):
            problems.append(f"animation name {an!r} is not snake_case")
        if not a.get("frames"):
            problems.append(f"animation {an!r} has no frames")
        for f in a.get("frames", []):
            if f not in names:
                problems.append(f"animation {an!r} references missing sprite {f!r}")
        d = a.get("direction", "")
        if d not in ("",) + DIRECTIONS:
            problems.append(f"animation {an!r} has bad direction {d!r}")
        if d:
            states.setdefault(a.get("state") or an, set()).add(d)
        if not isinstance(a.get("fps"), (int, float)) or a["fps"] <= 0:
            problems.append(f"animation {an!r} fps must be > 0")
        if not isinstance(a.get("loop"), bool):
            problems.append(f"animation {an!r} loop must be a boolean")
    if strict:
        for st, dirs in states.items():
            missing_dirs = [d for d in DIRECTIONS if d not in dirs]
            if missing_dirs:
                problems.append(f"directional state {st!r} is missing {missing_dirs}")

    tile_names: set = set()
    for t in doc["tiles"]:
        if t.get("name") in tile_names:
            problems.append(f"duplicate tile {t.get('name')!r}")
        tile_names.add(t.get("name"))
        if t.get("sprite") not in names:
            problems.append(f"tile {t.get('name')!r} references missing sprite {t.get('sprite')!r}")
        if t.get("collider") not in COLLIDERS:
            problems.append(f"tile {t.get('name')!r} has bad collider {t.get('collider')!r}")

    by_rule: Dict[str, set] = {}
    for r in doc["tileRules"]:
        rt, m = r.get("ruleTile"), r.get("mask")
        if not isinstance(m, int) or not is_canonical(m):
            problems.append(f"tileRule {rt!r} mask {m!r} is not canonical")
        if m in by_rule.setdefault(rt, set()):
            problems.append(f"duplicate tileRule ({rt!r}, {m})")
        by_rule[rt].add(m)
        if r.get("sprite") not in names:
            problems.append(f"tileRule {rt!r}/m{m} references missing sprite {r.get('sprite')!r}")
        frames = r.get("animFrames", [])
        for f in frames:
            if f not in names:
                problems.append(f"tileRule {rt!r}/m{m} references missing frame {f!r}")
        if frames and (not isinstance(r.get("animFps"), (int, float)) or r.get("animFps", 0) <= 0
                       or frames[0] != r.get("sprite")):
            problems.append(f"tileRule {rt!r}/m{m} animated entry is inconsistent")
    for rt, masks in by_rule.items():
        if strict:
            missing_masks = sorted(set(CANONICAL_MASKS) - masks)
            if missing_masks:
                problems.append(f"ruleTile {rt!r} is missing {len(missing_masks)} masks {missing_masks}")
            if not any(d.get("ruleTile") == rt for d in doc["ruleTileDefaults"]):
                problems.append(f"ruleTile {rt!r} has no ruleTileDefaults entry")
    for d in doc["ruleTileDefaults"]:
        if d.get("defaultSprite") not in names:
            problems.append(f"ruleTileDefault {d.get('ruleTile')!r} references missing sprite {d.get('defaultSprite')!r}")
        if d.get("collider") not in COLLIDERS:
            problems.append(f"ruleTileDefault {d.get('ruleTile')!r} has bad collider")
        if d.get("ruleTile") not in by_rule:
            problems.append(f"ruleTileDefault {d.get('ruleTile')!r} has no tileRules")

    frames_n, fps = doc["stripFrames"], doc["stripFps"]
    if not isinstance(frames_n, int) or frames_n < 0:
        problems.append(f"stripFrames {frames_n!r} must be an int >= 0")
    elif frames_n > 0:
        sprites = doc["sprites"]
        if not isinstance(fps, (int, float)) or fps < 0:
            problems.append(f"stripFps {fps!r} must be >= 0")
        if len(sprites) != frames_n:
            problems.append(f"strip has {len(sprites)} sprites but stripFrames = {frames_n}")
        if sprites and all(isinstance(s.get(k), int) for s in sprites for k in ("x", "y", "w", "h")):
            fw, fh = sprites[0]["w"], sprites[0]["h"]
            for i, s in enumerate(sprites):
                if (s["w"], s["h"]) != (fw, fh):
                    problems.append(f"strip frame {s.get('name')!r} is {s['w']}x{s['h']}, expected {fw}x{fh}")
                if (s["x"], s["y"]) != (i * fw, 0):
                    problems.append(f"strip frame {s.get('name')!r} at ({s['x']},{s['y']}) should be ({i * fw}, 0)")
            if (width, height) != (frames_n * fw, fh):
                problems.append(f"strip PNG is {width}x{height}, expected {frames_n * fw}x{fh} "
                                f"({frames_n} frames of {fw}x{fh})")
    if strict and kind == "fx":
        if frames_n == 0:
            problems.append("fx sheet must be a strip (stripFrames > 0; call set_strip)")
        if (doc["defaultPivotX"], doc["defaultPivotY"]) != (0.5, 0.5):
            problems.append("fx strips use the centre pivot (0.5, 0.5) (§5.4)")
    if strict and kind == "character":
        problems.extend(_check_character(doc, width, height))
    if strict and kind == "face":
        problems.extend(_check_face(doc, width, height))
    return problems


def check_sheet(png_path: str, json_path: Optional[str] = None, palette: bool = True,
                strict: bool = True) -> List[str]:
    """Reviewer check of a written sheet (§9, art part). Returns problem strings (empty = OK).

    Reads the PNG + sidecar and runs check_sidecar() (rects in bounds, unique names, animation
    frames exist, 47 masks per ruleTile, strip layout consistent, character layout when kind
    == character, face layout) plus PNG mode and palette compliance.
    """
    problems: List[str] = []
    if json_path is None:
        json_path = sidecar_path(png_path)
    if not os.path.isfile(png_path):
        return [f"missing PNG {png_path}"]
    if not os.path.isfile(json_path):
        return [f"missing sidecar {json_path}"]
    try:
        doc = load_sidecar(json_path)
    except Exception as ex:  # noqa: BLE001
        return [f"sidecar {json_path} is not valid JSON: {ex}"]
    if not isinstance(doc, dict):
        return [f"sidecar {json_path} is not a JSON object"]
    with Image.open(png_path) as img:
        W, H = img.size
        mode = img.mode
    if mode != "RGBA":
        problems.append(f"PNG mode is {mode}, expected RGBA")
    base = os.path.splitext(os.path.basename(png_path))[0]
    problems.extend(check_sidecar(doc, W, H, file_base=base, strict=strict))
    if palette:
        bad = verify_palette(png_path, max_results=5)
        if bad:
            problems.append(f"palette violation: {len(verify_palette(png_path))} offending pixels, first {bad}")
    return problems


def check_character_sheet(png_path: str, json_path: Optional[str] = None) -> List[str]:
    """Reviewer helper: §5.1 layout problems of a SAVED character sheet (PNG + sidecar),
    including the general sidecar checks. Empty list = compliant."""
    problems = check_sheet(png_path, json_path, palette=True, strict=True)
    if json_path is None:
        json_path = sidecar_path(png_path)
    if os.path.isfile(json_path) and os.path.isfile(png_path):
        try:
            doc = load_sidecar(json_path)
            with Image.open(png_path) as img:
                W, H = img.size
            if doc.get("kind") != "character":
                problems.extend(_check_character(doc, W, H))
        except Exception as ex:  # noqa: BLE001
            problems.append(f"cannot re-read {png_path}: {ex}")
    return sorted(set(problems), key=problems.index)
