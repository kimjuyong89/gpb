"""palette.py -- the binding 32-color PixelPack palette (ASSET_SPEC.md, section 2.1).

Every generator draws with palette *names*; the reviewer tooling checks that every
opaque pixel of every shipped PNG is one of these 32 colors.

Exports
-------
PALETTE        OrderedDict  name -> "#rrggbb"   (spec order)
COLORS         list of (r, g, b) tuples          (same order as PALETTE)
NAME_TO_RGB    OrderedDict  name -> (r, g, b)
RGB_TO_NAME    dict         (r, g, b) -> name
PALETTE_NAMES  list of names
hex_to_rgb / rgb_to_hex / is_palette_rgb / nearest_palette_name / resolve_rgba
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Optional, Sequence, Tuple, Union

__all__ = [
    "PALETTE", "COLORS", "NAME_TO_RGB", "RGB_TO_NAME", "PALETTE_NAMES",
    "hex_to_rgb", "rgb_to_hex", "is_palette_rgb", "nearest_palette_name",
    "resolve_rgba", "TRANSPARENT", "ColorLike",
]

# name -> hex, in the exact order of the spec table (section 2.1).
PALETTE: "OrderedDict[str, str]" = OrderedDict([
    ("black",       "#0d0b14"),   # deepest shadow, void
    ("outline",     "#1a1c2c"),   # outlines, darkest ramp
    ("navy",        "#2b2f4a"),   # dark metal, night
    ("slate_dark",  "#3f4a6b"),   # metal shade, stone shade
    ("slate",       "#5d6f94"),   # metal, stone
    ("slate_light", "#8ea3bf"),   # metal highlight
    ("silver",      "#c3d0dd"),   # bright metal, bone
    ("white",       "#f5f7fa"),   # highlights, eyes
    ("brown_dark",  "#3d2a22"),   # wood shade, dirt shade
    ("brown",       "#6b4332"),   # wood, dirt
    ("wood",        "#9c6b48"),   # wood light, leather
    ("tan",         "#c9956a"),   # skin shade, rope
    ("skin",        "#eec39a"),   # skin, sand
    ("cream",       "#fbe9c9"),   # parchment, sand light
    ("green_dark",  "#1f4a2f"),   # foliage shade
    ("green",       "#2f7d46"),   # foliage, grass
    ("green_light", "#5cc46a"),   # grass light, slime
    ("lime",        "#b6e65b"),   # grass highlight
    ("yellow",      "#f7e05a"),   # gold highlight, light
    ("gold",        "#f2b134"),   # gold, coins, fire
    ("orange",      "#e86f2a"),   # fire, autumn, hair
    ("red_dark",    "#8a1e2e"),   # blood, cloth shade
    ("red",         "#d9333f"),   # hearts, cloth
    ("pink",        "#f58aa3"),   # flowers, magic
    ("blue_dark",   "#1e3f73"),   # deep water, cloth shade
    ("blue",        "#3271d1"),   # water, cloth
    ("sky",         "#5cc5ff"),   # water highlight, ice
    ("ice",         "#bfefff"),   # foam, glow
    ("purple_dark", "#42285f"),   # magic shade, ghost shade
    ("purple",      "#8552c7"),   # magic, poison
    ("lavender",    "#c9a8f2"),   # ghost, magic highlight
    ("stone",       "#8a8aa0"),   # stone floor, rock
])

RGB = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]
ColorLike = Union[str, Sequence[int], None]

TRANSPARENT: RGBA = (0, 0, 0, 0)


def hex_to_rgb(h: str) -> RGB:
    """'#rrggbb' (or 'rrggbb') -> (r, g, b)."""
    s = h.strip().lstrip("#")
    if len(s) != 6:
        raise ValueError(f"bad hex color {h!r} (expected #rrggbb)")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def rgb_to_hex(rgb: Sequence[int]) -> str:
    """(r, g, b[, a]) -> '#rrggbb' (alpha is ignored)."""
    r, g, b = (int(v) & 255 for v in rgb[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


COLORS: list = [hex_to_rgb(h) for h in PALETTE.values()]
NAME_TO_RGB: "OrderedDict[str, RGB]" = OrderedDict((n, hex_to_rgb(h)) for n, h in PALETTE.items())
RGB_TO_NAME: dict = {rgb: n for n, rgb in NAME_TO_RGB.items()}
PALETTE_NAMES: list = list(PALETTE.keys())

assert len(PALETTE) == 32 and len(RGB_TO_NAME) == 32, "palette must have 32 distinct colors"


def is_palette_rgb(rgb: Sequence[int]) -> bool:
    """True when (r, g, b[, a]) is exactly one of the 32 palette colors."""
    return tuple(int(v) for v in rgb[:3]) in RGB_TO_NAME


def nearest_palette_name(rgb: Sequence[int]) -> str:
    """Name of the palette color closest (euclidean RGB) to the given color. Debug helper."""
    r, g, b = (int(v) for v in rgb[:3])
    best, best_d = PALETTE_NAMES[0], float("inf")
    for name, (pr, pg, pb) in NAME_TO_RGB.items():
        d = (pr - r) ** 2 + (pg - g) ** 2 + (pb - b) ** 2
        if d < best_d:
            best, best_d = name, d
    return best


def resolve_rgba(color: ColorLike) -> RGBA:
    """Resolve any color spec to an (r, g, b, a) tuple with a in {0, 255}.

    Resolution order (binding, see spec section 8): palette name first, then '#rrggbb'
    (or '#rrggbbaa'), then an (r, g, b) / (r, g, b, a) tuple. None means transparent.
    Partial alpha is not a thing in this pack: any alpha > 0 becomes 255, alpha 0 becomes
    the canonical transparent pixel (0, 0, 0, 0).
    """
    if color is None:
        return TRANSPARENT
    if isinstance(color, str):
        rgb = NAME_TO_RGB.get(color)
        if rgb is not None:
            return (rgb[0], rgb[1], rgb[2], 255)
        s = color.strip()
        if s.startswith("#") and len(s) in (7, 9):
            r, g, b = hex_to_rgb(s[:7])
            a = int(s[7:9], 16) if len(s) == 9 else 255
            return (r, g, b, 255) if a > 0 else TRANSPARENT
        raise KeyError(
            f"unknown color {color!r}: not a palette name ({', '.join(PALETTE_NAMES)}) "
            f"and not '#rrggbb'")
    try:
        parts = [int(v) for v in color]
    except TypeError:
        raise TypeError(f"unsupported color spec {color!r}") from None
    if len(parts) == 3:
        r, g, b = parts
        a = 255
    elif len(parts) == 4:
        r, g, b, a = parts
    else:
        raise ValueError(f"color tuple must have 3 or 4 components, got {color!r}")
    if a <= 0:
        return TRANSPARENT
    for v in (r, g, b):
        if not 0 <= v <= 255:
            raise ValueError(f"color component out of range in {color!r}")
    return (r, g, b, 255)
