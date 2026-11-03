"""pixelkit.py -- PixelPack pixel-art toolkit (binding surface: ASSET_SPEC.md section 8).

    from pixelkit import Canvas, Sheet, blob47, PALETTE, Rng

Canvas  : an RGBA pixel buffer (numpy (H, W, 4) uint8, (0, 0) = top-left) with pixel-art
          drawing primitives. Alpha is strictly 0 or 255 (the pack forbids partial alpha);
          any color written with alpha > 0 becomes fully opaque, alpha 0 becomes the
          canonical transparent pixel (0, 0, 0, 0).
Sheet   : collects named sprites (+ animations / tiles / tile rules / font block), packs
          them into one PNG (rows, left-to-right in insertion order, variable row height)
          and writes the sidecar `<sheet>.sprites.json` exactly as spec section 3 describes.
blob47  : builds the 47 canonical blob-tile masks from a quadrant drawer (spec section 4).
Rng     : thin deterministic wrapper over random.Random (fixed seeds everywhere).
verify_palette / check_sheet : reviewer helpers.

Colors everywhere are "color-likes": a palette name ("green"), "#rrggbb", an (r, g, b[, a])
tuple, or None (= transparent / erase). Palette names are resolved first.
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
    from .palette import (PALETTE, COLORS, NAME_TO_RGB, RGB_TO_NAME, PALETTE_NAMES,
                          hex_to_rgb, rgb_to_hex, is_palette_rgb, nearest_palette_name,
                          resolve_rgba, TRANSPARENT, ColorLike)
except ImportError:  # pragma: no cover - depends on how the module is imported
    from palette import (PALETTE, COLORS, NAME_TO_RGB, RGB_TO_NAME, PALETTE_NAMES,  # type: ignore
                         hex_to_rgb, rgb_to_hex, is_palette_rgb, nearest_palette_name,
                         resolve_rgba, TRANSPARENT, ColorLike)

__all__ = [
    # palette re-exports
    "PALETTE", "COLORS", "NAME_TO_RGB", "RGB_TO_NAME", "PALETTE_NAMES", "hex_to_rgb",
    "rgb_to_hex", "is_palette_rgb", "nearest_palette_name", "resolve_rgba", "TRANSPARENT",
    # core
    "Canvas", "Sheet", "SpriteEntry", "Rng", "blob47",
    # blob helpers
    "MASK_N", "MASK_NE", "MASK_E", "MASK_SE", "MASK_S", "MASK_SW", "MASK_W", "MASK_NW",
    "CANONICAL_MASKS", "QUADRANT_NAMES", "QUADRANT_KINDS", "KIND_INNER", "KIND_EDGE_H",
    "KIND_EDGE_V", "KIND_CORNER_OUT", "KIND_CORNER_IN", "quadrant_kind", "quadrant_kinds",
    "canonicalize", "is_canonical", "mask_from_neighbors",
    # conventions
    "SHEET_KINDS", "DIRECTIONS", "COLLIDERS", "PIXELS_PER_UNIT", "MAX_SHEET_WIDTH",
    # reviewer helpers
    "verify_palette", "check_sheet", "load_sidecar",
    # misc
    "FONT_3X5", "text_width",
]

# ------------------------------------------------------------------------------------------
# Conventions (spec sections 2, 3, 5)
# ------------------------------------------------------------------------------------------
PIXELS_PER_UNIT = 16
MAX_SHEET_WIDTH = 512
SHEET_KINDS = ("character", "enemy", "items", "props", "effects", "tiles", "ui", "font", "portraits")
DIRECTIONS = ("down", "up", "left", "right")
COLLIDERS = ("none", "sprite", "grid")
_NAME_RE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")

RGBA = Tuple[int, int, int, int]


def _rgba(color: ColorLike) -> RGBA:
    """Resolve a color-like to (r, g, b, a) with a in {0, 255}."""
    return resolve_rgba(color)


def _rgba_arr(color: ColorLike) -> np.ndarray:
    return np.array(_rgba(color), dtype=np.uint8)


# ------------------------------------------------------------------------------------------
# Tiny 3x5 debug font (used by Canvas.stamp and Sheet.preview labels). Never shipped.
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

    def outlined(self, color: ColorLike = "outline", diagonal: bool = False,
                 grow: bool = False) -> "Canvas":
        """New canvas with a 1px outline added around opaque pixels.

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
        so {"green": "blue", "blue": "green"} exchanges the two)."""
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
# Blob (47-tile) terrain sets  (spec section 4)
# ------------------------------------------------------------------------------------------
MASK_N, MASK_NE, MASK_E, MASK_SE, MASK_S, MASK_SW, MASK_W, MASK_NW = 1, 2, 4, 8, 16, 32, 64, 128

KIND_INNER = "inner"
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
    """Kind of quadrant 0..3 (TL, TR, BL, BR) for `mask` (spec section 4 rules)."""
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
    """Assemble all 47 canonical blob masks from a quadrant drawer.

    `draw_quadrant(quadrant_index, kind, frame, rng)` must return a (size/2 x size/2) Canvas
    drawn in its final orientation (quadrant_index 0..3 = TL, TR, BL, BR; kind one of
    QUADRANT_KINDS). With cache=True (default) each (quadrant, kind, frame) is drawn once and
    reused for every mask, which guarantees seamless tiling; cache=False redraws per mask
    (the drawer then receives the same rng and may add per-tile variation).

    Returns [(mask, [canvas_per_frame, ...]), ...] in ascending mask order (CANONICAL_MASKS).
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
class SpriteEntry:
    """One sprite in a Sheet (name, pixels, pivot, 9-slice border as (l, b, r, t))."""
    __slots__ = ("name", "canvas", "pivot", "border")

    def __init__(self, name: str, canvas: Canvas, pivot: Tuple[float, float],
                 border: Tuple[int, int, int, int]):
        self.name = name
        self.canvas = canvas
        self.pivot = pivot
        self.border = border

    @property
    def w(self) -> int:
        return self.canvas.w

    @property
    def h(self) -> int:
        return self.canvas.h

    def __repr__(self) -> str:
        return f"SpriteEntry({self.name!r}, {self.w}x{self.h})"


class Sheet:
    """A sprite sheet: named sprites packed into one PNG + the sidecar sprites.json.

    Packing (spec section 2.3): sprites go left-to-right in insertion order; a new row starts
    when the next sprite would exceed `max_width` (default 512), when its height differs from
    the current row's height (variable-height rows), or when the row already holds `columns`
    sprites (if `columns` is given). The PNG is the tight bounding box of all cells rounded
    up to a multiple of 4 px. Sprite order in the JSON == insertion order (deterministic).
    """

    def __init__(self, name: str, kind: str, pivot: Tuple[float, float] = (0.5, 0.5),
                 columns: Optional[int] = None, max_width: int = MAX_SHEET_WIDTH,
                 pixels_per_unit: int = PIXELS_PER_UNIT, strict_names: bool = True):
        if not _NAME_RE.match(name):
            raise ValueError(f"sheet name {name!r} must be lowercase snake_case ASCII")
        if kind not in SHEET_KINDS:
            raise ValueError(f"sheet kind {kind!r} must be one of {SHEET_KINDS}")
        if columns is not None and int(columns) < 1:
            raise ValueError("columns must be >= 1 or None")
        if int(max_width) < 1 or int(max_width) > MAX_SHEET_WIDTH:
            raise ValueError(f"max_width must be in 1..{MAX_SHEET_WIDTH}")
        self.name = name
        self.kind = kind
        self.pivot = (float(pivot[0]), float(pivot[1]))
        self.columns = int(columns) if columns is not None else None
        self.max_width = int(max_width)
        self.pixels_per_unit = int(pixels_per_unit)
        self.strict_names = strict_names
        self.sprites: List[SpriteEntry] = []
        self._index: Dict[str, SpriteEntry] = {}
        self.animations: List[dict] = []
        self.tiles: List[dict] = []
        self.tile_rules: List[dict] = []
        self.rule_tile_defaults: List[dict] = []
        self.font: Optional[dict] = None

    # --- content --------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.sprites)

    def __contains__(self, name: str) -> bool:
        return name in self._index

    @property
    def sprite_names(self) -> List[str]:
        """Sprite names in written (JSON) order."""
        return [e.name for e in self.sprites]

    def get(self, name: str) -> SpriteEntry:
        return self._index[name]

    def get_canvas(self, name: str) -> Canvas:
        return self._index[name].canvas

    def add(self, name: str, canvas: Canvas, pivot: Optional[Tuple[float, float]] = None,
            border: Optional[Tuple[int, int, int, int]] = None) -> str:
        """Add a sprite (the canvas is copied). `border` = (l, b, r, t) for 9-slice sprites.

        Names must be lowercase snake_case ASCII, unique, and (strict_names) start with
        '<sheet>_' so they are unique across the pack. Returns the name.
        """
        if not isinstance(canvas, Canvas):
            raise TypeError(f"sprite {name!r}: expected a Canvas, got {type(canvas).__name__}")
        if not _NAME_RE.match(name):
            raise ValueError(f"sprite name {name!r} must be lowercase snake_case ASCII")
        if self.strict_names and not name.startswith(self.name + "_"):
            raise ValueError(f"sprite name {name!r} must start with '{self.name}_' (sheet prefix)")
        if name in self._index:
            raise ValueError(f"duplicate sprite name {name!r} in sheet {self.name!r}")
        if canvas.w > self.max_width:
            raise ValueError(f"sprite {name!r} is wider ({canvas.w}) than max_width {self.max_width}")
        pv = self.pivot if pivot is None else (float(pivot[0]), float(pivot[1]))
        if border is None:
            bd = (0, 0, 0, 0)
        else:
            if len(border) != 4:
                raise ValueError(f"sprite {name!r}: border must be (l, b, r, t)")
            bd = tuple(int(v) for v in border)  # type: ignore[assignment]
            if min(bd) < 0 or bd[0] + bd[2] > canvas.w or bd[1] + bd[3] > canvas.h:
                raise ValueError(f"sprite {name!r}: border {bd} does not fit a {canvas.w}x{canvas.h} sprite")
        entry = SpriteEntry(name, canvas.copy(), pv, bd)  # type: ignore[arg-type]
        self.sprites.append(entry)
        self._index[name] = entry
        return name

    def add_frames(self, prefix: str, canvases: Sequence[Canvas], pivot=None, border=None) -> List[str]:
        """Add `canvases` as '<prefix>_0', '<prefix>_1', ... and return the names."""
        names = []
        for i, c in enumerate(canvases):
            names.append(self.add(f"{prefix}_{i}", c, pivot=pivot, border=border))
        return names

    def add_animation(self, name: str, frames: Sequence[str], fps: float, loop: bool = True,
                      state: str = "", direction: str = "") -> dict:
        """Declare an animation over existing (or later-added) sprite names."""
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
        """Declare a plain Tile asset (`name` is the Unity asset name, e.g. 'GrassPlain0')."""
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
                 pivot=None) -> List[str]:
        """Add a blob47() result: sprites '<prefix>_m<mask>' (animated: '<prefix>_m<mask>_f<i>'),
        one tile rule per mask and the rule-tile default. Returns the first-frame names."""
        first_names = []
        for mask, frames in blob:
            if len(frames) == 1:
                name = f"{name_prefix}_m{mask}"
                self.add(name, frames[0], pivot=pivot)
                self.add_tile_rule(rule_tile, name, mask)
            else:
                if not anim_fps or anim_fps <= 0:
                    raise ValueError("animated blob needs anim_fps > 0")
                names = [self.add(f"{name_prefix}_m{mask}_f{i}", c, pivot=pivot) for i, c in enumerate(frames)]
                name = names[0]
                self.add_tile_rule(rule_tile, name, mask, anim_frames=names, anim_fps=anim_fps)
            if mask == default_mask:
                self.set_rule_tile_default(rule_tile, name, collider=collider)
            first_names.append(name)
        return first_names

    def set_font(self, first_char: int, last_char: int, cell_w: int, cell_h: int, columns: int,
                 line_height: int, space_advance: int, advances: Sequence[int]) -> dict:
        """Fill the `font` block (font sheets only); `advances` has one int per glyph."""
        n = int(last_char) - int(first_char) + 1
        advances = [int(a) for a in advances]
        if n < 1:
            raise ValueError("font: last_char must be >= first_char")
        if len(advances) != n:
            raise ValueError(f"font: expected {n} advances for chars {first_char}..{last_char}, got {len(advances)}")
        self.font = OrderedDict([
            ("firstChar", int(first_char)), ("lastChar", int(last_char)),
            ("cellW", int(cell_w)), ("cellH", int(cell_h)), ("columns", int(columns)),
            ("lineHeight", int(line_height)), ("spaceAdvance", int(space_advance)),
            ("advances", advances),
        ])
        return self.font

    # --- packing --------------------------------------------------------------------
    def layout(self) -> List[Tuple[str, int, int, int, int]]:
        """[(name, x, y, w, h), ...] in insertion order (see class docstring for the rules)."""
        rects: List[Tuple[str, int, int, int, int]] = []
        x = y = 0
        row_h = 0
        row_count = 0
        for e in self.sprites:
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
            rects.append((e.name, x, y, w, h))
            x += w
            row_count += 1
        return rects

    def png_size(self) -> Tuple[int, int]:
        """Size of the packed PNG (tight bounding box rounded up to a multiple of 4)."""
        rects = self.layout()
        if not rects:
            return (0, 0)
        w = max(x + rw for _, x, _, rw, _ in rects)
        h = max(y + rh for _, _, y, _, rh in rects)
        return (_round4(w), _round4(h))

    def render(self) -> Canvas:
        """The packed sheet as one Canvas."""
        if not self.sprites:
            raise ValueError(f"sheet {self.name!r} has no sprites")
        W, H = self.png_size()
        out = Canvas(W, H)
        for (name, x, y, _, _) in self.layout():
            out.blit(self._index[name].canvas, x, y)
        return out

    # --- validation / IO ------------------------------------------------------------
    def validate(self, strict: bool = True) -> List[str]:
        """Return a list of problems (empty when the sheet is consistent with spec section 3).

        Always: sprite references in animations/tiles/tileRules/defaults exist, PNG width
        fits. strict=True also requires the 47 canonical masks per ruleTile, all four
        directions for every directional animation state, and a font block on font sheets.
        """
        problems: List[str] = []
        if not self.sprites:
            problems.append("sheet has no sprites")
        W, H = self.png_size()
        if W > self.max_width:
            problems.append(f"packed width {W} exceeds max_width {self.max_width}")
        for a in self.animations:
            for f in a["frames"]:
                if f not in self._index:
                    problems.append(f"animation {a['name']!r} references missing sprite {f!r}")
        for t in self.tiles:
            if t["sprite"] not in self._index:
                problems.append(f"tile {t['name']!r} references missing sprite {t['sprite']!r}")
        for r in self.tile_rules:
            if r["sprite"] not in self._index:
                problems.append(f"tileRule {r['ruleTile']}/m{r['mask']} references missing sprite {r['sprite']!r}")
            for f in r["animFrames"]:
                if f not in self._index:
                    problems.append(f"tileRule {r['ruleTile']}/m{r['mask']} references missing frame {f!r}")
        for d in self.rule_tile_defaults:
            if d["defaultSprite"] not in self._index:
                problems.append(f"ruleTileDefault {d['ruleTile']!r} references missing sprite {d['defaultSprite']!r}")
        if strict:
            by_rule: Dict[str, set] = {}
            for r in self.tile_rules:
                by_rule.setdefault(r["ruleTile"], set()).add(r["mask"])
            for rule, masks in by_rule.items():
                missing = sorted(set(CANONICAL_MASKS) - masks)
                if missing:
                    problems.append(f"ruleTile {rule!r} is missing {len(missing)} canonical masks: {missing[:8]}...")
                if not any(d["ruleTile"] == rule for d in self.rule_tile_defaults):
                    problems.append(f"ruleTile {rule!r} has no ruleTileDefaults entry")
            states: Dict[str, set] = {}
            for a in self.animations:
                if a["direction"]:
                    states.setdefault(a["state"] or a["name"], set()).add(a["direction"])
            for state, dirs in states.items():
                missing = [d for d in DIRECTIONS if d not in dirs]
                if missing:
                    problems.append(f"directional state {state!r} is missing directions {missing}")
            if self.kind == "font" and self.font is None:
                problems.append("font sheet has no font block (call set_font)")
            if self.kind != "font" and self.font is not None:
                problems.append(f"font block set on a non-font sheet (kind={self.kind!r})")
        return problems

    def to_json_dict(self) -> "OrderedDict[str, object]":
        """The sidecar document (spec section 3 shape and field order)."""
        sprites = []
        for (name, x, y, w, h) in self.layout():
            e = self._index[name]
            l, b, r, t = e.border
            sprites.append(OrderedDict([
                ("name", name), ("x", int(x)), ("y", int(y)), ("w", int(w)), ("h", int(h)),
                ("pivotX", float(e.pivot[0])), ("pivotY", float(e.pivot[1])),
                ("borderL", int(l)), ("borderB", int(b)), ("borderR", int(r)), ("borderT", int(t)),
            ]))
        doc: "OrderedDict[str, object]" = OrderedDict([
            ("version", 1),
            ("sheet", self.name),
            ("kind", self.kind),
            ("pixelsPerUnit", self.pixels_per_unit),
            ("defaultPivotX", float(self.pivot[0])),
            ("defaultPivotY", float(self.pivot[1])),
            ("sprites", sprites),
            ("animations", [OrderedDict(a) for a in self.animations]),
            ("tiles", [OrderedDict(t) for t in self.tiles]),
            ("tileRules", [OrderedDict(r) for r in self.tile_rules]),
            ("ruleTileDefaults", [OrderedDict(d) for d in self.rule_tile_defaults]),
        ])
        if self.font is not None:
            doc["font"] = OrderedDict(self.font)
        return doc

    def to_json(self) -> str:
        return json.dumps(self.to_json_dict(), indent=2) + "\n"

    def save(self, out_dir: str, strict: bool = True) -> Tuple[str, str]:
        """Write <out_dir>/<sheet>.png and <out_dir>/<sheet>.sprites.json.

        Raises ValueError (listing every problem) when validate(strict) finds any.
        Returns (png_path, json_path). Output is byte-deterministic.
        """
        problems = self.validate(strict=strict)
        if problems:
            raise ValueError(f"sheet {self.name!r} is not valid:\n  - " + "\n  - ".join(problems))
        os.makedirs(out_dir, exist_ok=True)
        png_path = os.path.join(out_dir, f"{self.name}.png")
        json_path = os.path.join(out_dir, f"{self.name}.sprites.json")
        self.render().save(png_path)
        with open(json_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.to_json())
        return png_path, json_path

    # --- previews -------------------------------------------------------------------
    def preview(self, path: str, scale: int = 4, labels: bool = True, max_width: int = 1024,
                names: Optional[Iterable[str]] = None) -> str:
        """Upscaled contact sheet for human review: every sprite (nearest-neighbour scaled)
        on a checkerboard with its name beneath, laid out in rows. Returns `path`."""
        entries = self.sprites if names is None else [self._index[n] for n in names]
        title = f"{self.name}  kind={self.kind}  sprites={len(self.sprites)}  png={'x'.join(map(str, self.png_size()))}"
        if names is not None:
            title += f"  shown={len(entries)}"
        img = _render_preview(entries, scale=scale, labels=labels, max_width=max_width, title=title)
        return img.save(path)

    def preview_group(self, path: str, name_prefix: str, scale: int = 8, labels: bool = True,
                      max_width: int = 1024) -> str:
        """Preview only the sprites whose names start with `name_prefix`, at a larger scale."""
        sel = [e.name for e in self.sprites if e.name.startswith(name_prefix)]
        if not sel:
            raise ValueError(f"no sprite in {self.name!r} starts with {name_prefix!r}")
        return self.preview(path, scale=scale, labels=labels, max_width=max_width, names=sel)

    def __repr__(self) -> str:
        return f"Sheet({self.name!r}, kind={self.kind!r}, sprites={len(self.sprites)})"


def _num(v):
    """int when integral, else float (keeps JSON tidy: 6 not 6.0)."""
    f = float(v)
    return int(f) if f.is_integer() else f


def _round4(v: int) -> int:
    return ((int(v) + 3) // 4) * 4


# --- preview rendering ----------------------------------------------------------------
_PV_BG = (20, 21, 28)
_PV_CHECK_A = (58, 59, 71)
_PV_CHECK_B = (42, 43, 53)
_PV_FRAME = (88, 92, 112)
_PV_TEXT = (216, 220, 232)
_PV_TITLE = (255, 214, 120)


def _wrap_label(name: str, chars_per_line: int, max_lines: int = 3) -> List[str]:
    chars_per_line = max(1, chars_per_line)
    lines = [name[i:i + chars_per_line] for i in range(0, len(name), chars_per_line)]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:max(0, chars_per_line - 1)] + "~"
    return lines


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
# Reviewer helpers
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
    their RGB. Accepts a path, a PIL image, a Canvas or an (H, W, 4) array.
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


def check_sheet(png_path: str, json_path: Optional[str] = None, palette: bool = True) -> List[str]:
    """Reviewer check of a written sheet (spec section 9, art part). Returns problem strings.

    Checks: sidecar exists and has the section-3 shape, every rect lies inside the PNG,
    names unique and sheet-prefixed, animations/tiles/rules reference existing sprites,
    directional states complete, 47 masks per ruleTile, font block consistency, palette
    compliance (0 offending pixels).
    """
    problems: List[str] = []
    if json_path is None:
        base = png_path[:-4] if png_path.lower().endswith(".png") else png_path
        json_path = base + ".sprites.json"
    if not os.path.isfile(png_path):
        return [f"missing PNG {png_path}"]
    if not os.path.isfile(json_path):
        return [f"missing sidecar {json_path}"]
    try:
        doc = load_sidecar(json_path)
    except Exception as ex:  # noqa: BLE001
        return [f"sidecar {json_path} is not valid JSON: {ex}"]
    with Image.open(png_path) as img:
        W, H = img.size
        mode = img.mode
    if mode != "RGBA":
        problems.append(f"PNG mode is {mode}, expected RGBA")
    if W > MAX_SHEET_WIDTH:
        problems.append(f"PNG width {W} > {MAX_SHEET_WIDTH}")
    for key in ("version", "sheet", "kind", "pixelsPerUnit", "defaultPivotX", "defaultPivotY",
                "sprites", "animations", "tiles", "tileRules", "ruleTileDefaults"):
        if key not in doc:
            problems.append(f"sidecar missing key {key!r}")
    if problems:
        return problems
    sheet = doc["sheet"]
    if os.path.basename(png_path) != f"{sheet}.png":
        problems.append(f"sidecar sheet {sheet!r} does not match file name {os.path.basename(png_path)}")
    if doc["kind"] not in SHEET_KINDS:
        problems.append(f"unknown kind {doc['kind']!r}")
    if doc.get("pixelsPerUnit") != PIXELS_PER_UNIT:
        problems.append(f"pixelsPerUnit is {doc.get('pixelsPerUnit')}, expected {PIXELS_PER_UNIT}")
    names = set()
    for s in doc["sprites"]:
        n = s.get("name")
        for k in ("x", "y", "w", "h", "pivotX", "pivotY", "borderL", "borderB", "borderR", "borderT"):
            if k not in s:
                problems.append(f"sprite {n!r} missing field {k!r}")
        if n in names:
            problems.append(f"duplicate sprite name {n!r}")
        names.add(n)
        if not isinstance(n, str) or not _NAME_RE.match(n) or not n.startswith(sheet + "_"):
            problems.append(f"sprite name {n!r} is not snake_case with the '{sheet}_' prefix")
        x, y, w, h = s.get("x", 0), s.get("y", 0), s.get("w", 0), s.get("h", 0)
        if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > W or y + h > H:
            problems.append(f"sprite {n!r} rect ({x},{y},{w},{h}) is outside the {W}x{H} PNG")
        if s.get("borderL", 0) + s.get("borderR", 0) > w or s.get("borderB", 0) + s.get("borderT", 0) > h:
            problems.append(f"sprite {n!r} 9-slice border exceeds its size")
    anim_names = set()
    states: Dict[str, set] = {}
    for a in doc["animations"]:
        an = a.get("name")
        if an in anim_names:
            problems.append(f"duplicate animation {an!r}")
        anim_names.add(an)
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
        if not a.get("fps", 0) or a["fps"] <= 0:
            problems.append(f"animation {an!r} fps must be > 0")
    for st, dirs in states.items():
        missing = [d for d in DIRECTIONS if d not in dirs]
        if missing:
            problems.append(f"directional state {st!r} is missing {missing}")
    tile_names = set()
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
        if frames and (r.get("animFps", 0) <= 0 or frames[0] != r.get("sprite")):
            problems.append(f"tileRule {rt!r}/m{m} animated entry is inconsistent")
    for rt, masks in by_rule.items():
        missing = sorted(set(CANONICAL_MASKS) - masks)
        if missing:
            problems.append(f"ruleTile {rt!r} is missing masks {missing}")
        if not any(d.get("ruleTile") == rt for d in doc["ruleTileDefaults"]):
            problems.append(f"ruleTile {rt!r} has no ruleTileDefaults entry")
    for d in doc["ruleTileDefaults"]:
        if d.get("defaultSprite") not in names:
            problems.append(f"ruleTileDefault {d.get('ruleTile')!r} references missing sprite {d.get('defaultSprite')!r}")
        if d.get("collider") not in COLLIDERS:
            problems.append(f"ruleTileDefault {d.get('ruleTile')!r} has bad collider")
    font = doc.get("font")
    if doc["kind"] == "font":
        if not font or font.get("cellW", 0) <= 0:
            problems.append("font sheet has no usable font block")
        else:
            n = font["lastChar"] - font["firstChar"] + 1
            if len(font.get("advances", [])) != n:
                problems.append(f"font advances has {len(font.get('advances', []))} entries, expected {n}")
            for code in range(font["firstChar"], font["lastChar"] + 1):
                if f"{sheet}_{code}" not in names:
                    problems.append(f"font glyph sprite {sheet}_{code} missing")
                    break
    elif font is not None:
        problems.append("non-font sheet carries a font block")
    if palette:
        bad = verify_palette(png_path, max_results=5)
        if bad:
            problems.append(f"palette violation: {len(verify_palette(png_path))} offending pixels, first {bad}")
    return problems
