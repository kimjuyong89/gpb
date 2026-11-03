"""palette.py -- the binding 32-color InkPixel (수묵 픽셀 팩) palette (ASSET_SPEC.md v2, §2.1).

Every generator draws with palette *names*; the reviewer tooling (`pixelkit.verify_palette`)
checks that every opaque pixel of every shipped PNG is exactly one of these 32 colors and that
alpha is strictly 0 or 255.

Exports
-------
PALETTE        OrderedDict  name -> "#rrggbb"   (spec order)
COLORS         list of (r, g, b) tuples          (same order as PALETTE)
NAME_TO_RGB    OrderedDict  name -> (r, g, b)
RGB_TO_NAME    dict         (r, g, b) -> name
PALETTE_NAMES  list of names
ALIASES        dict         alias -> palette name  ("outline" -> "ink_black", v1 compatibility)
OUTLINE        "ink_black"  the default outline color name
RAMPS          dict         material -> tuple of names, dark -> light (ink-wash guidance, §2)
hex_to_rgb / rgb_to_hex / is_palette_rgb / nearest_palette_name / resolve_rgba / ramp
TRANSPARENT    (0, 0, 0, 0)
ColorLike      a palette name, an alias, '#rrggbb', '#rrggbbaa', an (r, g, b[, a]) tuple or None
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Dict, Optional, Sequence, Tuple, Union

__all__ = [
    "PALETTE", "COLORS", "NAME_TO_RGB", "RGB_TO_NAME", "PALETTE_NAMES", "ALIASES", "OUTLINE",
    "RAMPS", "hex_to_rgb", "rgb_to_hex", "is_palette_rgb", "nearest_palette_name",
    "resolve_rgba", "ramp", "TRANSPARENT", "ColorLike",
]

# name -> hex, in the exact order of the spec table (§2.1). Do not reorder: COLORS/PALETTE_NAMES
# follow this order and the README documents it.
PALETTE: "OrderedDict[str, str]" = OrderedDict([
    ("ink_black",       "#1e1b18"),   # outlines, darkest (GPA 먹)
    ("ink_dark",        "#3a342e"),   # deep shade, hair, dark cloth
    ("ink",             "#5c554c"),   # mid grey-brown, stone shade, roof tiles
    ("ink_light",       "#8a8378"),   # stone, grey cloth, roof light
    ("ink_pale",        "#b5ad9e"),   # pale stone, bone, light grey
    ("paper_dark",      "#d6c6a4"),   # aged paper, sand shade, straw
    ("paper",           "#e9dec6"),   # paper, sand, light walls (GPA 한지)
    ("paper_light",     "#f4ecdc"),   # highlights, white cloth, foam, eyes
    ("vermilion_dark",  "#6e1512"),   # blood, red shade
    ("vermilion",       "#9e241c"),   # accents, hearts, seals, red cloth (GPA 주묵)
    ("vermilion_light", "#c4473a"),   # red highlight, lanterns, flowers
    ("jade_dark",       "#1c5c4e"),   # sect robes shade, deep foliage (GPA 옥)
    ("jade",            "#3f8a73"),   # jade, sect cloth, teal foliage
    ("jade_light",      "#7fb79b"),   # jade highlight, pale teal
    ("bronze_navy",     "#18243c"),   # night, black cloth (흑사방), deep shade (GPA 청동 남색)
    ("navy",            "#2f4466"),   # blue cloth, slate, deep water shade
    ("steel",           "#5a7391"),   # steel, blue highlight, distant mountains
    ("moss_dark",       "#35502f"),   # grass shade, pine shade
    ("moss",            "#5a7a45"),   # grass, foliage
    ("moss_light",      "#88a05a"),   # grass light, leaves
    ("moss_pale",       "#b4c278"),   # grass highlight, bamboo light
    ("earth_dark",      "#4a3324"),   # wood shade, dirt shade, bark
    ("earth",           "#76533a"),   # wood, dirt, leather
    ("earth_light",     "#a6805a"),   # wood light, road
    ("sand",            "#cfae7e"),   # tan, rope, straw light, skin shade
    ("skin",            "#e6c39b"),   # skin
    ("gold",            "#c9a24a"),   # gold, brass, coins, lantern glow
    ("gold_light",      "#e8d690"),   # gold highlight, candle light, elixir glow
    ("water_deep",      "#2d5b73"),   # river deep
    ("water",           "#4f8aa3"),   # river
    ("water_light",     "#8dbfcc"),   # river highlight, ripples
    ("plum",            "#5b3a6b"),   # poison, inner-demon, purple cloth
])

# Old (v1) color names that generators may still use. Resolved before anything else fails.
ALIASES: Dict[str, str] = {
    "outline": "ink_black",
}

OUTLINE = "ink_black"

# Suggested value ramps (dark -> light) for the ink-wash look (§2 "Mood"). Pure guidance: any
# palette color may be used anywhere, but sticking to these keeps the pack coherent.
RAMPS: Dict[str, Tuple[str, ...]] = OrderedDict([
    ("cloth",     ("ink_dark", "ink", "ink_light")),            # grey/dark robes
    ("wood",      ("earth_dark", "earth", "earth_light")),      # timber, barrels, docks
    ("grass",     ("moss_dark", "moss", "moss_light")),         # ground, foliage
    ("grass_hi",  ("moss", "moss_light", "moss_pale")),         # sunlit grass, bamboo
    ("skin",      ("sand", "skin")),                            # faces, hands
    ("paper",     ("paper_dark", "paper", "paper_light")),      # hanji walls, white cloth, sand
    ("stone",     ("ink", "ink_light", "ink_pale")),            # rock, flagstone, roof tiles
    ("water",     ("water_deep", "water", "water_light")),      # river
    ("night",     ("bronze_navy", "navy", "steel")),            # black cloth, slate, mountains
    ("vermilion", ("vermilion_dark", "vermilion", "vermilion_light")),  # accents, lanterns
    ("jade",      ("jade_dark", "jade", "jade_light")),         # sect colors, jade items
    ("gold",      ("gold", "gold_light")),                      # coins, brass, glow
    ("ink",       ("ink_black", "ink_dark", "ink")),            # the darkest ramp
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
assert all(v in PALETTE for v in ALIASES.values()), "every alias must point at a palette name"
assert all(c in PALETTE for names in RAMPS.values() for c in names), "ramps must use palette names"


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


def ramp(material: str) -> Tuple[str, ...]:
    """The suggested dark->light palette names for a material key of RAMPS."""
    try:
        return RAMPS[material]
    except KeyError:
        raise KeyError(f"unknown ramp {material!r}; known: {', '.join(RAMPS)}") from None


def resolve_rgba(color: ColorLike) -> RGBA:
    """Resolve any color spec to an (r, g, b, a) tuple with a in {0, 255}.

    Resolution order: palette name, then alias (ALIASES, e.g. 'outline'), then '#rrggbb' /
    '#rrggbbaa', then an (r, g, b) / (r, g, b, a) sequence. None means transparent.
    Partial alpha is not a thing in this pack: any alpha > 0 becomes 255, alpha 0 becomes
    the canonical transparent pixel (0, 0, 0, 0).
    """
    if color is None:
        return TRANSPARENT
    if isinstance(color, str):
        rgb = NAME_TO_RGB.get(color)
        if rgb is None:
            alias = ALIASES.get(color)
            if alias is not None:
                rgb = NAME_TO_RGB[alias]
        if rgb is not None:
            return (rgb[0], rgb[1], rgb[2], 255)
        s = color.strip()
        if s.startswith("#") and len(s) in (7, 9):
            r, g, b = hex_to_rgb(s[:7])
            a = int(s[7:9], 16) if len(s) == 9 else 255
            return (r, g, b, 255) if a > 0 else TRANSPARENT
        raise KeyError(
            f"unknown color {color!r}: not a palette name ({', '.join(PALETTE_NAMES)}), "
            f"not an alias ({', '.join(ALIASES)}) and not '#rrggbb'")
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
