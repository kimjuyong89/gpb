#!/usr/bin/env python3
"""gen_icons.py -- InkPixel item icons (ASSET_SPEC.md v2, §5.3).

Writes  Art/Icons/<name>.png            one 40x40 PNG per icon (GPA loads these by name)
        Art/Icons/icons_sheet.png       contact sheet of every 40x40 icon + icons_sheet.sprites.json
        Art/Icons/Mini/<name>.png       16x16 HUD minis (coin, hp, qi, fatigue, hunger, warmth, qi_orb)
        Docs/previews/icons_sheet_preview.png, icons_mini_preview.png   (4x, labelled)

Style: Jianghu-Lite-like wuxia item icons -- the object drawn large (~30 px) and centred in the
40 px cell, 1px ink_black outline, 2-3 tone shading, light from the top-left, ink-wash palette
(paper lights, ink darks, muted moss/earth) with sparse vermilion / jade / gold accents to tell
variants apart. Families share one drawing with role letters so palette swaps are trivial:
weapons are procedural 45-degree bands, garments are procedural silhouettes, everything organic
is a hand-drawn ASCII pattern. Fully deterministic (no randomness at all).
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

from pixelkit import Canvas, Sheet

SHEET = "icons"
MINI_SHEET = "icons_mini"
ICON = 40
MINI = 16

# One letter per palette color (same letters as the tile generators) ------------------------
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


def pat(text: str, roles: Optional[Dict[str, Optional[str]]] = None) -> Canvas:
    """ASCII block -> Canvas ('.' transparent; blank leading/trailing lines dropped; rows padded).
    `roles` maps placeholder digits (or any extra letters) to palette names (None = transparent)."""
    rows = [r.rstrip() for r in text.split("\n")]
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    w = max(len(r) for r in rows)
    cm: Dict[str, Optional[str]] = dict(CM)
    if roles:
        cm.update(roles)
    # None-mapped letters must become '.', from_pattern treats None as "erase" which is fine too
    return Canvas.from_pattern([r.ljust(w, ".") for r in rows], cm)


def finish(c: Canvas, outline: bool = True) -> Canvas:
    """Centre the art in the 40x40 cell and add the 1px ink outline."""
    rb = c.bbox()
    if rb is None:
        raise ValueError("empty icon")
    if (c.w, c.h) == (ICON, ICON) and (rb[0] == 0 or rb[1] == 0 or rb[0] + rb[2] == c.w or rb[1] + rb[3] == c.h):
        # positioned drawings must stay off the canvas edge, otherwise something was silently clipped
        raise ValueError(f"icon art touches the drawing canvas edge (bbox {rb}): it was probably clipped")
    out = c.centered(ICON, ICON)
    bb = out.bbox()
    if bb is None:
        raise ValueError("empty icon")
    x, y, w, h = bb
    if x < 1 or y < 1 or x + w > ICON - 1 or y + h > ICON - 1:
        raise ValueError(f"icon art {w}x{h} leaves no room for the outline")
    return out.outlined("ink_black") if outline else out


def blank() -> Canvas:
    return Canvas(ICON, ICON)


# ------------------------------------------------------------------------------------------
# small drawing helpers
# ------------------------------------------------------------------------------------------
def ball(c: Canvas, cx: int, cy: int, r: int, body: str, shade: str, hi: str,
         hi2: Optional[str] = None, mid: Optional[str] = None) -> None:
    """Sphere: shade crescent bottom-right, highlight blob top-left. With `mid` the crescent is
    two-toned (shade outside, mid inside) and twice as wide -- needed for pale spheres that
    would otherwise melt into a pale background."""
    c.circle(cx, cy, r, shade)
    if mid:
        c.circle(cx - 1, cy - 1, r - 1, mid)
        c.circle(cx - 2, cy - 2, r - 2, body)
    else:
        c.circle(cx - 1, cy - 1, r - 1, body)
    hx, hy = cx - max(1, r // 2), cy - max(1, r // 2)
    c.rect(hx - 1, hy, 3, 2, hi)
    c.set(hx, hy - 1, hi)
    if hi2:
        c.set(hx - 1, hy, hi2)


def sparkle(c: Canvas, x: int, y: int, color: str, size: int = 1) -> None:
    c.set(x, y, color)
    for k in range(1, size + 1):
        c.set(x + k, y, color)
        c.set(x - k, y, color)
        c.set(x, y + k, color)
        c.set(x, y - k, color)


def band_row(c: Canvas, x0: int, y0: int, i: int, off: int, cols: Sequence[Optional[str]]) -> None:
    """Row `i` of a 45-degree band rising to the right: y = y0 - i, x = x0 + i + off + k."""
    y = y0 - i
    for k, col in enumerate(cols):
        if col is not None:
            c.set(x0 + i + off + k, y, col)


def anti_bar(c: Canvas, cx: int, cy: int, half: int, hi: str, body: str, thick: int = 2) -> None:
    """Short bar perpendicular to the 45-degree blade (runs down-right through (cx, cy))."""
    for k in range(-half, half + 1):
        for t in range(thick):
            c.set(cx + k + t, cy + k, hi if (k < 0 and t == 0) else body)


# ------------------------------------------------------------------------------------------
# weapons (procedural, 45 degrees, hilt bottom-left, tip top-right)
# ------------------------------------------------------------------------------------------
def tip_rows(hi: str, body: str, shade: str) -> List[Tuple[int, List[str]]]:
    """(offset, colors) for the last four rows of a symmetric blade point."""
    return [(1, [hi, body, body, shade]), (1, [hi, body, shade]), (2, [hi, shade]), (2, [hi])]


def sword(blade_len: int, grip_len: int, blade: Tuple[str, str, str], guard: Tuple[str, str],
          grip: str, wrap: str, pommel: str, tassel: Optional[Tuple[str, str]] = None,
          guard_half: int = 3, pommel_rows: int = 2, shine: bool = False,
          rust: bool = False, chips: Sequence[int] = (), x0: int = 2, y0: int = 31) -> Canvas:
    c = blank()
    hi, body, shade = blade
    i = 0
    for r in range(pommel_rows):
        band_row(c, x0, y0, i, 1, [pommel, pommel, pommel])
        i += 1
    for r in range(grip_len):
        col = wrap if r % 2 == 0 else grip
        band_row(c, x0, y0, i, 1, [col, col, grip])
        i += 1
    guard_i = i
    i += 2
    tips = tip_rows(hi, body, shade)
    for r in range(blade_len):
        rem = blade_len - 1 - r
        if rem < 4:
            off, cols = tips[3 - rem]
        else:
            off, cols = 0, [hi, body, body, body, shade]
            cols = list(cols)
            if shine and 3 <= r <= 9:
                cols[1] = hi
            if rust:
                if r % 3 == 1:
                    cols[2] = "earth"
                if r % 4 == 2:
                    cols[3] = "vermilion_dark"
                if r % 5 == 0:
                    cols[1] = "ink"
            if r in chips:
                cols[0] = None  # a notch bitten out of the edge (the outline fills it)
        band_row(c, x0, y0, i, off, cols)
        i += 1
    anti_bar(c, x0 + guard_i + 2, y0 - guard_i, guard_half, guard[0], guard[1])
    if tassel:
        t, td = tassel
        c.vline(x0 + 1, y0 + 1, y0 + 2, "ink_dark")
        c.rect(x0 - 1, y0 + 3, 4, 4, t)
        c.vline(x0 + 2, y0 + 3, y0 + 6, td)
        c.hline(x0 - 1, x0 + 2, y0 + 3, td)
        c.set(x0 + 1, y0 + 3, "gold")
        for x in (x0 - 1, x0 + 1):
            c.set(x, y0 + 7, t)
        c.set(x0 + 2, y0 + 7, td)
    return finish(c)


def ic_jian() -> Canvas:
    return sword(19, 7, ("paper_light", "ink_pale", "ink_light"), ("ink_light", "ink"),
                 "earth", "sand", "ink", tassel=("vermilion", "vermilion_dark"))


def ic_jian_iron() -> Canvas:
    return sword(19, 7, ("ink_pale", "ink_light", "ink"), ("ink_light", "ink_dark"),
                 "earth_dark", "earth", "ink_dark")


def ic_jian_steel() -> Canvas:
    return sword(19, 7, ("paper_light", "ink_pale", "ink_light"), ("gold_light", "gold"),
                 "ink_dark", "navy", "gold", tassel=("vermilion", "vermilion_dark"), shine=True)


def ic_jian_rusty() -> Canvas:
    return sword(18, 7, ("ink_pale", "ink_light", "ink"), ("earth", "earth_dark"),
                 "earth_dark", "earth", "earth_dark", rust=True, chips=(4, 10))


def ic_jian_cheongun() -> Canvas:
    return sword(19, 7, ("paper_light", "ink_pale", "ink_light"), ("jade_light", "jade"),
                 "jade_dark", "jade", "jade_light", tassel=("paper", "paper_dark"), shine=True)


def dagger(blade: Tuple[str, str, str], guard: Tuple[str, str], grip: str, wrap: str,
           pommel: str) -> Canvas:
    return sword(14, 7, blade, guard, grip, wrap, pommel, guard_half=2, pommel_rows=2, x0=6, y0=31)


def ic_dagger() -> Canvas:
    return dagger(("paper_light", "ink_pale", "ink_light"), ("ink_light", "ink"), "earth", "sand", "ink")


def ic_dagger_heuksa() -> Canvas:
    return dagger(("ink_pale", "steel", "navy"), ("ink_light", "ink_dark"), "bronze_navy",
                  "vermilion_dark", "vermilion")


def ic_dao() -> Canvas:
    """Curved single-edged sabre: edge top-left, spine bottom-right, clipped tip, ring pommel."""
    c = blank()
    x0, y0 = 1, 31
    hi, body, shade = "paper_light", "ink_pale", "ink_light"
    i = 0
    # ring pommel
    c.circle(x0 + 2, y0 + 1, 2, "ink_light", fill=False)
    c.set(x0 + 1, y0, "ink_pale")
    i = 2
    for r in range(7):                       # red-corded grip
        col = "vermilion" if r % 2 == 0 else "vermilion_dark"
        band_row(c, x0, y0, i, 1, [col, col, "vermilion_dark"])
        i += 1
    guard_i = i
    i += 2
    L = 17
    xl = list(range(6)) + [6, 7, 9, 10, 12, 13, 15, 17, 19, 21, 23]          # edge curves up-right
    xr = [k + 5 for k in range(6)] + [11, 12, 14, 15, 17, 18, 20, 21, 23, 24, 25]  # spine follows, blade thins
    for r in range(L):
        w = xr[r] - xl[r] + 1
        if w >= 4:
            cols = [hi] + [body] * (w - 3) + [shade, "ink"]
        elif w == 3:
            cols = [hi, body, shade]
        else:
            cols = [hi, shade][:w]
        band_row(c, x0, y0, i, xl[r] - r, cols)
        i += 1
    anti_bar(c, x0 + guard_i + 2, y0 - guard_i, 3, "gold_light", "gold")
    return finish(c)


def ic_cleaver() -> Canvas:
    """Kitchen cleaver: a broad slab at 45 degrees, wooden handle at the bottom-left."""
    c = blank()
    x0, y0 = 1, 30
    i = 0
    for r in range(8):                       # handle
        band_row(c, x0, y0, i, 2, ["earth_light", "earth", "earth", "earth_dark"])
        i += 1
    for r in range(2):                       # ferrule
        band_row(c, x0, y0, i, 2, ["ink_pale", "ink_light", "ink_light", "ink"])
        i += 1
    L = 17
    for r in range(L):
        w = 13
        if r == 0:
            cols = ["paper_light"] + ["ink_pale"] * 8 + ["ink_light"] * 2
            band_row(c, x0, y0, i, 0, cols)
        elif r >= L - 3:                     # top corner is cut (slanted back)
            w = 13 - 3 * (r - (L - 3)) - 3
            cols = ["paper_light"] + ["ink_pale"] * max(0, w - 3) + ["ink_light"] * 2
            band_row(c, x0, y0, i, 0, cols)
        else:
            cols = ["paper_light"] + ["ink_pale"] * 9 + ["ink_light"] * 2 + ["ink"]
            band_row(c, x0, y0, i, 0, cols)
        i += 1
    c.set(x0 + 9 + 10, y0 - 9 - 2, "ink")    # hanging hole near the spine
    return finish(c)


def ic_staff() -> Canvas:
    c = blank()
    x0, y0 = 2, 34
    for i in range(32):
        if i < 4 or i >= 28:
            cols = ["ink_pale", "ink_light", "ink_light", "ink"]
        elif 13 <= i <= 18:
            cols = ["sand", "earth_light", "earth", "earth_dark"] if i % 2 else ["earth_light", "earth", "earth", "earth_dark"]
        else:
            cols = ["earth_light", "earth", "earth", "earth_dark"]
        band_row(c, x0, y0, i, 0, cols)
    anti_bar(c, x0 + 29 + 1, y0 - 29, 2, "ink_pale", "ink_light", thick=1)   # iron ring near the top cap
    return finish(c)


def ic_sling() -> Canvas:
    """Y-fork slingshot with a leather band holding a stone."""
    return finish(pat("""
.FFe..............eFF.
.Fee..............eeF.
.Fee..............eeF.
.kFe..............ekk.
.kkFe............ekk..
..kkkee........eekkk..
...kkkkeeeeeeeekkkk...
....kkiIIiIIIikkkk....
......kkIPPPIkk.......
........iIIIi.........
.........FFe..........
.........FFe..........
.........FFe..........
.........FFe..........
.........FFe..........
.........FeE..........
........sFeEs.........
........sFeEs.........
........sFeEs.........
........sFeEs.........
........sFeEs.........
........sFeEs.........
.........FeE..........
"""))


def ic_fist_wraps() -> Canvas:
    """Clenched fist seen from the thumb side, knuckles to the right: four notched finger
    segments on the right edge, the thumb folded over the top, a cloth wrap across the back
    of the hand and around the wrist (bare-hand weapon)."""
    return finish(pat("""
........oooooooo..........
......oooooooooooo........
.....ooooooooooooooo......
....oooooooooooooooooooo..
....ooooooooooooooooooooo.
....oossskkkkkkkkooooooos.
....oooooooooooooooooooos.
....ooooooooooooooookkkks.
....oooooooooooooooooooos.
....WWWWWWWWWWWWWooooooooo
....PPWWWWWWWWWWWookkkkss.
....PPPPPPPPPPPPPooooooooo
.....oooooooooooooooooooos
.....oooooooooooooookkkks.
.....ooooooooooooooooooos.
......oooooooooooooooooss.
.......ssooooooooooosss...
........sssssooooss.......
......WWWWWWWWWW..........
.....WWWWWWWWWWPP.........
.....PPPPPPPPPPPPP........
......ooooooooooo.........
......sssssssssss.........
"""))


# ------------------------------------------------------------------------------------------
# garments (procedural silhouettes with role colours)
# ------------------------------------------------------------------------------------------
def robe_base(hi: str, mid: str, shade: str, trim: str, sash: str, knot: str,
              texture: bool = False) -> Canvas:
    """Hanfu/dopo laid flat: wide sleeves, crossed collar, sash, flared skirt (32x31)."""
    c = Canvas(40, 40)
    ox, oy = 4, 4
    # left half (cols 0..15), then mirror
    left_edge = [7, 4, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    for r, le in enumerate(left_edge):            # sleeve rows 0..17 (cols le..9)
        c.hline(ox + le, ox + 9, oy + r, mid)
    for r in range(18, 31):                       # body/skirt rows
        flare = max(0, (r - 18) // 4)
        c.hline(ox + 9 - flare, ox + 15, oy + r, mid)
    for r in range(0, 18):
        c.hline(ox + 10, ox + 15, oy + r, mid)
    c = c.mirrored_lr()
    # sleeve cuffs and hem (trim), shade on the lower/right side
    c.rect(ox + 0, oy + 16, 10, 2, trim)
    c.rect(ox + 22, oy + 16, 10, 2, trim)
    c.rect(ox + 1, oy + 14, 9, 2, shade)
    c.rect(ox + 22, oy + 14, 9, 2, shade)
    c.rect(ox + 29, oy + 4, 3, 10, shade)
    c.rect(ox + 20, oy + 0, 2, 16, shade)
    c.rect(ox + 20, oy + 18, 2, 13, shade)
    c.rect(ox + 21, oy + 22, 3, 9, shade)
    c.rect(ox + 1, oy + 4, 2, 10, hi)
    c.rect(ox + 10, oy + 2, 2, 14, hi)
    c.rect(ox + 9, oy + 19, 2, 12, hi)
    # collar: crossed V
    for r in range(0, 8):
        c.rect(ox + 12 + r, oy + r, 2, 1, trim)
        c.rect(ox + 18 - r, oy + r, 2, 1, trim)
    c.rect(ox + 14, oy + 7, 4, 1, trim)
    c.vline(ox + 16, oy + 8, oy + 11, shade)      # overlap line
    # neck opening (skin shows) -- small triangle
    c.set(ox + 15, oy + 0, "sand"); c.set(ox + 16, oy + 0, "sand")
    c.set(ox + 14, oy + 0, "skin"); c.set(ox + 17, oy + 0, "skin")
    c.hline(ox + 15, ox + 16, oy + 1, "skin")
    # sash
    c.rect(ox + 9, oy + 12, 14, 3, sash)
    c.rect(ox + 9, oy + 14, 14, 1, knot)
    c.rect(ox + 14, oy + 11, 4, 5, knot)
    c.rect(ox + 15, oy + 12, 2, 2, sash)
    c.vline(ox + 13, oy + 15, oy + 20, knot)      # hanging sash end
    c.vline(ox + 14, oy + 15, oy + 18, sash)
    # hem trim + centre seam of the skirt
    c.rect(ox + 6, oy + 29, 20, 2, trim)
    c.vline(ox + 16, oy + 16, oy + 28, shade)
    if texture:
        for y in range(oy + 2, oy + 29, 3):
            for x in range(ox + 1, ox + 31, 4):
                if c.get_name(x + (y % 2), y) == mid:
                    c.set(x + (y % 2), y, shade)
    return finish(c)


def ic_robe() -> Canvas:
    return robe_base("paper_light", "paper", "paper_dark", "earth", "earth_light", "earth_dark")


def ic_robe_hemp() -> Canvas:
    return robe_base("paper_dark", "sand", "earth_light", "earth", "ink_light", "ink", texture=True)


def ic_robe_cheongun() -> Canvas:
    return robe_base("jade_light", "jade", "jade_dark", "paper", "paper", "paper_dark")


def ic_robe_heuksa() -> Canvas:
    return robe_base("steel", "navy", "bronze_navy", "ink_dark", "vermilion", "vermilion_dark")


def vest_base(hi: str, mid: str, shade: str, trim: str, tie: str, quilt: bool = False,
              plates: Optional[Tuple[str, str]] = None) -> Canvas:
    """Sleeveless vest, open front with ties (24x30)."""
    c = Canvas(40, 40)
    ox, oy = 8, 5
    edge = [5, 3, 2, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    for r, le in enumerate(edge):
        c.hline(ox + le, ox + 11, oy + r, mid)
    # arm hole (cut from the top-left)
    for r in range(1, 9):
        cut = max(0, 4 - abs(r - 4))
        c.hline(ox + 0, ox + 0 + cut, oy + r, None)
    c = c.mirrored_lr()
    # neck opening (V) and front opening
    for r in range(0, 6):
        c.hline(ox + 8 + r, ox + 15 - r, oy + r, None)
    c.vline(ox + 12, oy + 6, oy + 29, trim)
    c.vline(ox + 11, oy + 6, oy + 29, shade)
    c.vline(ox + 10, oy + 6, oy + 29, trim)
    c.rect(ox + 2, oy + 9, 2, 18, hi)
    c.rect(ox + 20, oy + 9, 2, 19, shade)
    c.rect(ox + 1, oy + 28, 22, 2, shade)
    for r in range(0, 6):                         # collar trim along the V
        c.rect(ox + 7 + r, oy + r, 1, 1, trim)
        c.rect(ox + 16 - r, oy + r, 1, 1, trim)
    for y in (oy + 11, oy + 17, oy + 23):          # ties across the opening
        c.hline(ox + 8, ox + 14, y, tie)
        c.set(ox + 8, y + 1, tie); c.set(ox + 14, y + 1, tie)
    if quilt:
        for y in range(oy + 7, oy + 28, 4):
            for x in range(ox + 1, ox + 23, 4):
                xx = x + (2 if (y // 4) % 2 else 0)
                if c.get_name(xx, y) == mid:
                    c.set(xx, y, shade)
    if plates:
        p_hi, p_sh = plates
        for x in (ox + 1, ox + 19):               # shoulder plates
            c.rect(x, oy + 1, 4, 3, p_hi)
            c.rect(x, oy + 3, 4, 2, p_sh)
            c.rect(x, oy + 5, 4, 1, p_hi)
            c.rect(x, oy + 6, 4, 1, p_sh)
    return finish(c)


def ic_vest_leather() -> Canvas:
    return vest_base("earth_light", "earth", "earth_dark", "earth_dark", "sand")


def ic_armor_soft() -> Canvas:
    return vest_base("steel", "navy", "bronze_navy", "ink_dark", "ink_pale", quilt=True,
                     plates=("ink_pale", "ink_light"))


# ------------------------------------------------------------------------------------------
# shoes & gloves (ASCII)
# ------------------------------------------------------------------------------------------
def sandal() -> Canvas:
    return pat("""
.....ssss.....
...sasasasa...
..asasasasas..
..saskkssasa..
..aEaskssaEa..
..sEsasksasEs.
..aEasasasaEa.
..sEsasasasEs.
..aEasasasaEa.
..sEsasasasEs.
..aaasasasaaa.
..sasasasasas.
..asasasasasa.
..sasasasasas.
..asasasasasa.
...sasasasas..
...asasasasa..
....sasasas...
.....sasas....
""")


def pair(part: Canvas, pos_a: Tuple[int, int], pos_b: Tuple[int, int],
         flip_b: bool = False) -> Canvas:
    """Two-object icons (shoes, gloves): each part gets its own full outline (grow=True so the
    ring is never clipped at the part's canvas edge), then the pair is centred in the cell."""
    a = part.outlined(grow=True)
    b = a.flipped_x() if flip_b else a
    c = blank()
    c.blit(a, *pos_a)
    c.blit(b, *pos_b)
    return finish(c, outline=False)


def ic_straw_sandals() -> Canvas:
    return pair(sandal(), (4, 12), (17, 6))


def boot() -> Canvas:
    return pat("""
....FFFFFFFFF.
....FFFFFFFFF.
....eeeeeeeeE.
....eeeeeeeeE.
....eeeeeeeeE.
....FeeeeeeeE.
....FeeeeeeeE.
....FeeeeeeeE.
....FeeeeeeeE.
....FeeeeeeeE.
....FeeeeeeeE.
....FeeeeeeeE.
....eeeeeeeeE.
...FeeeeeeeeE.
..FeeeeeeeeeE.
.FeeeeeeeeeeE.
FeeeeeeeeeeeE.
EEEEEEEEEEEEE.
.EEE.....EEEE.
""")


def ic_leather_boots() -> Canvas:
    return pair(boot(), (19, 5), (3, 13))


def cloud_shoe() -> Canvas:
    return pat("""
...........WWWWWWWWW...
.W.......WWkkkkkkkkWW..
.WW....WWWkkkkkkkkkkW..
..WWWWWWWWAkkkkkkkkWA..
..WhhWWWWWWAAAAAAAAAa..
..hWhWWWWWWWWWWAAAAaa..
...WWWWWWWWWWWAAAAaaa..
...aaaaaaaaaaaaaaaaaa..
...SSSSSSSSSSSSSSSSSS..
....nnnnnnnnnnnnnnnnn..
""")


def ic_cloud_shoes() -> Canvas:
    return pair(cloud_shoe(), (14, 5), (1, 18))


GLOVE = """
....11...11...........
...1221.1221..11......
...1221.1221.1221.....
...1221.1221.1221.11..
...1222.1222.1222.122.
...12222122221222.122.
..1.12222222222222222.
.121122222222222222333
.1222222222222222223..
.12222222222222222333.
.12222222222222222333.
..122222222222222333..
...1222222222222333...
...122222222222233....
...12222222222223.....
...44444444444444.....
...45555555555554.....
...44444444444444.....
"""


def ic_glove() -> Canvas:
    return finish(pat(GLOVE, {"1": "earth_light", "2": "earth", "3": "earth_dark",
                              "4": "sand", "5": "earth_dark"}))


def ic_leather_gloves() -> Canvas:
    g = pat(GLOVE, {"1": "earth", "2": "earth_dark", "3": "ink_dark",
                    "4": "earth", "5": "ink_light"})
    return pair(g, (14, 2), (3, 10), flip_b=True)


CLOTH_WRAPS = """
....oo...oo...........
...osso.osso..oo......
...osso.osso.osso.....
...osso.osso.osso.oo..
...osss.osss.osss.oss.
...ossssossssosss.oss.
..o.oooooooooooooooss.
.oooAAAAAAAAAAAAAAAaaa
.oooaaaaaaaaaaaaaaaa..
.oooooooooooooooooss..
.oooAAAAAAAAAAAAAAAa..
..ooaaaaaaaaaaaaaaa...
...oooooooooooooos....
...oAAAAAAAAAAAAa.....
...oaaaaaaaaaaaa......
...AAAAAAAAAAAAAA.....
...aaaaaaaaaaaaaa.....
...AAAAAAAAAAAAAA.....
"""


def ic_cloth_wraps() -> Canvas:
    return finish(pat(CLOTH_WRAPS.replace("A", "W").replace("a", "P")))


# ------------------------------------------------------------------------------------------
# accessories
# ------------------------------------------------------------------------------------------
def coin_canvas(cx: int, cy: int, r: int, hole: int = 5, body: str = "gold", shade: str = "earth_light",
                hi: str = "gold_light") -> Canvas:
    c = blank()
    c.circle(cx, cy, r, shade)
    c.circle(cx - 1, cy - 1, r - 1, body)
    c.circle(cx, cy, r - 2, body)
    c.circle(cx, cy, r, hi, fill=False)
    c.circle(cx, cy, r, shade, fill=False)
    # rim: light arc top-left, dark arc bottom-right
    ring = Canvas(ICON, ICON)
    ring.circle(cx, cy, r, hi, fill=False)
    for y in range(ICON):
        for x in range(ICON):
            if ring.get(x, y)[3] and (x - cx) + (y - cy) > 0:
                ring.set(x, y, shade)
    c.blit(ring, 0, 0)
    c.circle(cx, cy, r - 2, shade, fill=False)
    # inner shading on the top-left of the inner ring is light again
    inner = Canvas(ICON, ICON)
    inner.circle(cx, cy, r - 2, hi, fill=False)
    for y in range(ICON):
        for x in range(ICON):
            if inner.get(x, y)[3] and (x - cx) + (y - cy) > 1:
                inner.set(x, y, None)
    c.blit(inner, 0, 0)
    h = hole
    c.rect(cx - h // 2, cy - h // 2, h, h, None)
    c.rect(cx - h // 2 - 1, cy - h // 2 - 1, h + 2, 1, shade)
    c.rect(cx - h // 2 - 1, cy - h // 2 - 1, 1, h + 2, shade)
    c.rect(cx - h // 2 - 1, cy + h // 2 + 1, h + 2, 1, hi)
    c.rect(cx + h // 2 + 1, cy - h // 2 - 1, 1, h + 2, hi)
    return c


def ic_coin() -> Canvas:
    return finish(coin_canvas(20, 20, 12, hole=7))


def ic_coin_stack() -> Canvas:
    c = blank()
    for (x, y) in ((11, 11), (18, 17), (25, 23)):
        c.blit(coin_canvas(x, y, 8, hole=5).outlined(), 0, 0)
    return c


def ic_lucky_coin() -> Canvas:
    c = blank()
    coin = coin_canvas(20, 23, 10, hole=5)
    c.blit(coin, 0, 0)
    # red cord through the hole, knot and loop above
    c.vline(20, 12, 25, "vermilion")
    c.vline(19, 13, 20, "vermilion_dark")
    c.rect(18, 9, 5, 3, "vermilion")
    c.rect(18, 11, 5, 1, "vermilion_dark")
    c.set(20, 10, "vermilion_light")
    c.ellipse(20, 5, 3, 3, "vermilion", fill=False)
    c.set(23, 5, "vermilion_dark"); c.set(22, 7, "vermilion_dark")
    c.vline(20, 8, 8, "vermilion")
    return finish(c)


def pendant_disc(body: str, shade: str, hi: str, cord: str, cord_dark: str, carve: str,
                 crack: bool = False) -> Canvas:
    c = blank()
    cx, cy, r = 20, 25, 11
    c.circle(cx, cy, r, shade)
    c.circle(cx - 1, cy - 1, r - 1, body)
    c.rect(cx - 7, cy - 6, 3, 2, hi)
    c.rect(cx - 6, cy - 8, 2, 2, hi)
    c.set(cx - 8, cy - 4, hi)
    for (dx, dy) in ((0, -6), (6, 0), (0, 6), (-6, 0), (4, -4), (4, 4), (-4, 4), (-4, -4)):
        c.set(cx + dx, cy + dy, carve)
    c.circle(cx, cy, 2, None)          # centre hole (the outline rings it)
    if crack:
        c.line(cx + 3, cy - 10, cx + 6, cy - 3, "ink_dark")
        c.line(cx + 6, cy - 3, cx + 4, cy + 1, "ink_dark")
        c.set(cx - 5, cy + 7, "ink_dark"); c.set(cx - 6, cy + 8, "ink_dark")
    # cord: through a small hole at the top, knot, loop
    c.vline(cx, cy - r - 1, cy - r + 2, cord)
    c.rect(cx - 2, cy - r - 4, 5, 3, cord)
    c.rect(cx - 2, cy - r - 2, 5, 1, cord_dark)
    c.set(cx, cy - r - 3, hi if body != "ink_light" else "ink_pale")
    c.vline(cx - 1, cy - r - 6, cy - r - 5, cord)
    c.vline(cx + 1, cy - r - 6, cy - r - 5, cord)
    c.ellipse(cx, cy - r - 9, 3, 3, cord, fill=False)
    c.set(cx + 3, cy - r - 9, cord_dark); c.set(cx + 2, cy - r - 7, cord_dark)
    return finish(c)


def ic_jade_pendant() -> Canvas:
    return pendant_disc("jade", "jade_dark", "jade_light", "vermilion", "vermilion_dark", "jade_dark")


def ic_jade_pendant_old() -> Canvas:
    return pendant_disc("ink_light", "ink", "ink_pale", "ink", "ink_dark", "ink", crack=True)


def ic_jade_pendant_cheongun() -> Canvas:
    """Tall jade plaque with a carved cloud, gold bead on a vermilion cord."""
    c = blank()
    x, y, w, h = 12, 15, 16, 22
    c.rect(x, y, w, h, "jade_dark")
    c.rect(x, y, w - 2, h - 2, "jade")
    c.rect(x + 1, y + 1, w - 2, h - 2, "jade")
    c.rect(x + 2, y + 2, w - 3, h - 3, "jade")
    c.rect(x, y + 1, 2, h - 4, "jade_light")
    c.rect(x + 1, y, w - 4, 2, "jade_light")
    # rounded corners
    for (px, py) in ((x, y), (x + w - 1, y), (x, y + h - 1), (x + w - 1, y + h - 1)):
        c.set(px, py, None)
    # carved cloud (paper_light) and jade_dark grooves
    c.hline(x + 5, x + 10, y + 9, "paper_light")
    c.hline(x + 4, x + 11, y + 10, "paper_light")
    c.set(x + 6, y + 8, "paper_light"); c.set(x + 7, y + 7, "paper_light"); c.set(x + 9, y + 8, "paper_light")
    c.hline(x + 6, x + 9, y + 12, "jade_dark")
    c.hline(x + 5, x + 10, y + 14, "jade_dark")
    c.hline(x + 6, x + 9, y + 16, "jade_dark")
    c.hline(x + 3, x + 12, y + 18, "paper_light")
    c.hline(x + 3, x + 12, y + 4, "jade_dark")
    # top hole + cord + gold bead + loop
    c.rect(x + 7, y + 1, 2, 2, None)
    c.vline(x + 7, y - 3, y, "vermilion"); c.vline(x + 8, y - 3, y, "vermilion_dark")
    c.rect(x + 6, y - 7, 4, 4, "gold")
    c.rect(x + 6, y - 7, 2, 2, "gold_light")
    c.set(x + 9, y - 4, "earth_light")
    c.vline(x + 7, y - 9, y - 8, "vermilion"); c.vline(x + 8, y - 9, y - 8, "vermilion_dark")
    c.ellipse(x + 7, y - 12, 3, 2, "vermilion", fill=False)
    return finish(c)


def pouch(hi: str, mid: str, shade: str, top: str, cord: str, cord_dark: str) -> Canvas:
    c = blank()
    c.ellipse(20, 23, 11, 10, shade)
    c.ellipse(19, 22, 10, 9, mid)
    c.rect(12, 14, 4, 3, mid)
    c.rect(24, 14, 4, 3, mid)
    c.ellipse(15, 18, 3, 3, hi)
    c.ellipse(14, 21, 2, 4, hi)
    # gathered neck
    c.rect(13, 11, 14, 3, top)
    c.rect(14, 9, 12, 2, top)
    for x in range(14, 26, 2):
        c.set(x, 9, mid)
        c.set(x + 1, 12, mid)
    # cord with hanging ends and a knot
    c.hline(12, 27, 13, cord)
    c.rect(18, 12, 4, 3, cord)
    c.set(19, 13, cord_dark); c.set(20, 13, cord_dark)
    c.line(26, 14, 30, 20, cord)
    c.line(27, 14, 30, 17, cord_dark)
    c.rect(29, 20, 2, 4, cord)
    c.rect(29, 17, 2, 3, cord_dark)
    return c


def ic_sachet() -> Canvas:
    c = pouch("moss_light", "moss", "moss_dark", "moss_dark", "gold", "earth_light")
    # embroidered herb-leaf mark in gold thread
    c.hline(19, 21, 22, "gold_light")
    c.hline(18, 22, 23, "gold_light")
    c.hline(19, 21, 24, "gold_light")
    c.set(20, 21, "gold_light"); c.set(20, 25, "gold_light")
    return finish(c)


def ic_poison_pouch() -> Canvas:
    c = pouch("steel", "navy", "bronze_navy", "bronze_navy", "vermilion", "vermilion_dark")
    # black-snake mark (vermilion S)
    for (x, y) in ((18, 18), (19, 18), (20, 18), (21, 19), (20, 20), (19, 20), (18, 21), (19, 22),
                   (20, 22), (21, 22), (22, 21)):
        c.set(x, y, "vermilion_light")
    c.set(21, 18, "vermilion")
    c.set(17, 22, "vermilion")
    return finish(c)


def ic_talisman() -> Canvas:
    """Yellow paper strip with vermilion marks; top-right corner folded."""
    c = blank()
    x, y, w, h = 14, 5, 12, 30
    c.rect(x, y, w, h, "gold_light")
    c.rect(x + w - 2, y + 1, 2, h - 1, "paper_dark")
    c.rect(x + 1, y + h - 1, w - 1, 1, "paper_dark")
    c.rect(x, y, 1, h - 1, "paper_light")
    # dog-eared top-right corner: a 5x5 block, the part above the fold diagonal is cut away,
    # the part below it is the back of the paper folded over (paper_dark)
    x0 = x + w - 5
    for py in range(5):
        for px in range(5):
            c.set(x0 + px, y + py, None if px - py >= 1 else "paper_dark")
    c.set(x0, y + 4, "paper")                     # soft crease at the fold's inner corner
    # vermilion marks below the fold: three dots, a zigzag column of strokes, bottom seal
    for dx in (3, 6, 9):
        c.set(x + dx, y + 6, "vermilion")
    c.rect(x + 2, y + 8, 8, 2, "vermilion")
    c.rect(x + 4, y + 10, 2, 3, "vermilion")
    c.rect(x + 3, y + 13, 6, 2, "vermilion")
    c.rect(x + 6, y + 15, 2, 3, "vermilion")
    c.rect(x + 3, y + 18, 6, 2, "vermilion")
    c.rect(x + 4, y + 20, 2, 2, "vermilion")
    c.rect(x + 3, y + 22, 6, 2, "vermilion")
    c.rect(x + 3, y + 25, 6, 4, "vermilion")
    c.rect(x + 4, y + 26, 4, 2, "vermilion_dark")
    c.set(x + 5, y + 26, "gold_light"); c.set(x + 6, y + 27, "gold_light")
    return finish(c)


# ------------------------------------------------------------------------------------------
# consumables & elixirs
# ------------------------------------------------------------------------------------------
def pill_on_paper(body: str, shade: str, hi: str, mid: Optional[str] = None) -> Canvas:
    c = blank()
    cx, cy = 20, 20
    for y in range(ICON):
        for x in range(ICON):
            d = abs(x - cx) + abs(y - cy)
            if d <= 13:
                c.set(x, y, "paper")
            if d == 13 or d == 12:
                if x - cx + y - cy > 0:
                    c.set(x, y, "paper_dark")
                else:
                    c.set(x, y, "paper_light")
    c.ellipse(cx + 1, cy + 2, 9, 8, "paper_dark")         # shadow under the pill
    ball(c, cx, cy, 8, body, shade, hi, mid=mid)
    return finish(c)


def ic_pill() -> Canvas:
    return pill_on_paper("ink", "ink_dark", "ink_light")


def ic_pill_qi() -> Canvas:
    # white pill: a grey two-tone crescent so it still reads as a sphere on the paper wrapper
    return pill_on_paper("paper_light", "ink_light", "paper_light", mid="ink_pale")


def ic_pill_antidote() -> Canvas:
    return pill_on_paper("jade", "jade_dark", "jade_light")


def ic_pill_clear() -> Canvas:
    return pill_on_paper("steel", "navy", "water_light")


def ic_pill_vigor() -> Canvas:
    return pill_on_paper("vermilion_light", "vermilion", "gold_light")


def elixir(body: str, shade: str, hi: str, extra_glow: bool = False,
           tint: Optional[str] = None, mid: Optional[str] = None) -> Canvas:
    c = blank()
    cx, cy = 20, 18
    # opened wax shell below
    c.ellipse(13, 29, 7, 5, "paper_dark")
    c.ellipse(27, 29, 7, 5, "paper_dark")
    c.ellipse(12, 28, 6, 4, "paper")
    c.ellipse(26, 28, 6, 4, "paper")
    c.ellipse(11, 27, 4, 2, "paper_light")
    c.ellipse(25, 27, 4, 2, "paper_light")
    c.rect(16, 24, 8, 4, "paper_dark")
    ball(c, cx, cy, 9, body, shade, hi, hi2="paper_light", mid=mid)
    if tint:
        # checker-dither a second hue over the lit half of the body (orange = red + gold)
        for y in range(cy - 9, cy + 10):
            for x in range(cx - 9, cx + 10):
                if c.get_name(x, y) == body and (x + y) % 2 == 0 and (x - cx) + (y - cy) < 3:
                    c.set(x, y, tint)
    c.set(cx - 5, cy - 4, "paper_light")
    out = finish(c)
    # glow sparkles (not outlined)
    for (x, y, s) in ((6, 9, 1), (33, 8, 1), (31, 20, 0), (7, 21, 0), (20, 3, 1), (12, 3, 0), (29, 3, 0)):
        sparkle(out, x, y, "gold_light", s)
    if extra_glow:
        for (x, y) in ((4, 15), (35, 14), (10, 28 - 2), (30, 26)):
            sparkle(out, x, y, "gold_light", 1)
    return out


def ic_elixir_red() -> Canvas:
    return elixir("vermilion", "vermilion_dark", "vermilion_light")


def ic_elixir_purple() -> Canvas:
    return elixir("plum", "bronze_navy", "ink_pale")


def ic_elixir_blue() -> Canvas:
    return elixir("water", "water_deep", "water_light")


def ic_elixir_orange() -> Canvas:
    return elixir("vermilion_light", "vermilion", "gold_light", tint="gold")


def ic_elixir_green() -> Canvas:
    return elixir("jade", "jade_dark", "jade_light")


def ic_elixir_white() -> Canvas:
    # white elixir: grey two-tone crescent separates the ball from the white wax shells
    return elixir("paper_light", "ink_light", "gold_light", mid="ink_pale")


def ic_elixir_gold() -> Canvas:
    return elixir("gold", "earth_light", "gold_light", extra_glow=True)


def ic_salve() -> Canvas:
    return finish(pat("""
......AAAAAAAAAAAA......
.....AWAAAAAAAAAAAa.....
.....AWAAAAAAAAAAAa.....
.....vvvvvvvvvvvvvv.....
.....PAAAAAAAAAAAAa.....
....PPPPPPPPPPPPPPPI....
...PPWWPPPPPPPPPPPPII...
..PPWWPPPPPPPPPPPPPPII..
..PWPPPPPPPPPPPPPPPPII..
..PPPPPPAAAAAAAPPPPPII..
..PPPPPPAvvvvvAPPPPPII..
..PPPPPPAvAvAvAPPPPPII..
..PPPPPPAvvvvvAPPPPPII..
..PPPPPPAAAAAAAPPPPPII..
..PPPPPPPPPPPPPPPPPIII..
...PPPPPPPPPPPPPPPIII...
....PPPPPPPPPPPPPIII....
.....IIIIIIIIIIIIII.....
"""))


def ic_powder() -> Canvas:
    """Upright paper packet (약포지): top flap folded down, side flaps folded to the back,
    a vermilion stamp, powder showing at the open mouth and a heap spilled in front."""
    c = blank()
    x, y, w, h = 10, 7, 19, 25
    c.rect(x, y, w, h, "paper")
    c.rect(x + w - 2, y + 1, 2, h - 1, "paper_dark")
    c.rect(x + 1, y + h - 2, w - 1, 2, "paper_dark")
    c.rect(x, y, 1, h - 1, "paper_light")
    c.rect(x, y, w - 1, 1, "paper_light")
    # side flaps folded behind: vertical crease lines
    c.vline(x + 3, y + 7, y + h - 3, "paper_dark")
    c.vline(x + w - 5, y + 7, y + h - 3, "paper_dark")
    # top flap folded down over the front (darker band with a crease)
    c.rect(x + 1, y + 1, w - 3, 6, "paper_dark")
    c.rect(x + 1, y + 1, w - 3, 1, "paper")
    c.hline(x + 1, x + w - 3, y + 7, "ink_light")
    for k in range(0, w - 3, 2):                       # torn / dog-eared flap edge
        c.set(x + 1 + k, y + 7, "paper_dark")
    # powder peeking out of the mouth
    c.hline(x + 5, x + w - 7, y + 6, "paper_light")
    c.set(x + 7, y + 5, "paper_light"); c.set(x + 10, y + 5, "paper_light")
    # stamp
    c.rect(x + 6, y + 12, 7, 7, "vermilion")
    c.rect(x + 7, y + 13, 5, 5, "vermilion_dark")
    c.hline(x + 8, x + 10, y + 15, "vermilion_light")
    c.set(x + 9, y + 14, "vermilion_light"); c.set(x + 9, y + 16, "vermilion_light")
    # heap of powder spilled in front (bottom-left)
    c.ellipse(x - 2, y + h + 1, 6, 2, "paper_light")
    c.ellipse(x - 2, y + h + 2, 7, 2, "ink_pale")
    c.ellipse(x - 2, y + h + 1, 5, 1, "paper_light")
    c.set(x - 2, y + h - 1, "paper_light"); c.hline(x - 3, x - 1, y + h, "paper_light")
    return finish(c)


# ------------------------------------------------------------------------------------------
# manuals
# ------------------------------------------------------------------------------------------
def book(cover: str, cover_shade: str, glyph: Optional[Canvas] = None, label: bool = True) -> Canvas:
    c = blank()
    x, y, w, h = 9, 5, 22, 29
    c.rect(x, y, w, h, cover)
    c.rect(x + w - 2, y + 1, 2, h - 1, cover_shade)
    c.rect(x + 1, y + h - 3, w - 1, 3, "paper_dark")        # page block
    c.rect(x + 1, y + h - 2, w - 1, 1, "paper")
    c.rect(x + 1, y + h - 3, w - 1, 1, "paper_light")
    c.rect(x, y, 3, h - 3, "ink_dark")                      # stitched spine
    c.set(x, y, None); c.set(x + w - 1, y, None)
    for sy in range(y + 3, y + h - 5, 6):
        c.vline(x + 1, sy, sy + 2, "sand")
        c.set(x + 2, sy + 1, "sand")
    if label:
        c.rect(x + 5, y + 2, 7, 15, "paper_light")
        c.rect(x + 11, y + 3, 1, 14, "paper_dark")
        c.rect(x + 6, y + 16, 6, 1, "paper_dark")
        # three stacked pseudo-characters (brush strokes) down the title label
        c.paste_pattern(["KKK", ".K.", "KKK", "...", "K.K", "KKK", "K.K", "...", "KKK", "K.K", "KKK"],
                        x + 7, y + 4, {"K": "ink_dark"})
    if glyph is not None:
        c.blit(glyph, x + 12, y + 17)
    return finish(c)


def glyph_dao() -> Canvas:
    return pat("""
......W.
.....WW.
....WW..
...WW...
..WW....
.WW.....
WA......
""")


def glyph_palm() -> Canvas:
    return pat("""
.W.W.W..
.W.W.W.W
.WWWWW.W
WWWWWWWW
.WWWWWW.
..WWWW..
""")


def glyph_fist() -> Canvas:
    return pat("""
.W.W.W..
WWWWWWW.
WWWWWWWW
WWWWWWWW
.WWWWWW.
..WWWW..
""")


def glyph_kick() -> Canvas:
    """A boot (kicking leg) seen from the side, toe to the right."""
    return pat("""
.WWW....
.WWW....
.WWW....
.WWWW...
.WWWWW..
.WWWWWWW
WWWWWWWW
""")


def ic_manual() -> Canvas:
    return book("navy", "bronze_navy")


def ic_manual_dao() -> Canvas:
    return book("ink_dark", "bronze_navy", glyph_dao())


def ic_manual_palm() -> Canvas:
    return book("earth", "earth_dark", glyph_palm())


def ic_manual_fist() -> Canvas:
    return book("vermilion", "vermilion_dark", glyph_fist())


def ic_manual_kick() -> Canvas:
    return book("moss", "moss_dark", glyph_kick())


def ic_scroll_mind() -> Canvas:
    """Horizontal scroll, partly unrolled, jade ribbon."""
    c = blank()
    # paper
    c.rect(9, 12, 22, 16, "paper")
    c.rect(9, 12, 22, 1, "paper_light")
    c.rect(9, 26, 22, 2, "paper_dark")
    for x in range(13, 29, 4):                      # columns of ink text
        c.vline(x, 15, 18, "ink_dark")
        c.set(x + 1, 16, "ink_dark")
        c.vline(x, 20, 24, "ink_dark")
        c.set(x + 1, 22, "ink_dark")
    # rollers
    for rx in (5, 31):
        c.rect(rx, 9, 4, 22, "earth")
        c.rect(rx, 9, 1, 22, "earth_light")
        c.rect(rx + 3, 9, 1, 22, "earth_dark")
        c.rect(rx, 9, 4, 2, "gold")
        c.rect(rx, 29, 4, 2, "gold")
        c.rect(rx, 9, 2, 1, "gold_light")
        c.rect(rx, 29, 2, 1, "gold_light")
    # ribbon tie hanging from the left roller
    c.rect(4, 14, 2, 3, "jade")
    c.line(3, 17, 2, 23, "jade")
    c.line(5, 17, 6, 22, "jade_dark")
    c.rect(1, 23, 2, 3, "jade"); c.rect(6, 22, 2, 3, "jade_dark")
    return finish(c)


# ------------------------------------------------------------------------------------------
# misc
# ------------------------------------------------------------------------------------------
def ic_ledger() -> Canvas:
    """Open account book: two pages of ink columns, a vermilion seal on the right page."""
    c = blank()
    # pages (slight V opening)
    left = pat("""
WWWWWWWWWWWWWW.
AAAAAAAAAAAAAW.
AkAkkAkAkkAkAW.
AAAAAAAAAAAAAW.
AkAkAkkAkAkAAW.
AAAAAAAAAAAAAW.
AkkAkAkAkkAkAW.
AAAAAAAAAAAAAW.
AkAkkAkAkAkkAW.
AAAAAAAAAAAAAW.
AkAkAkkAkkAkAW.
AAAAAAAAAAAAAW.
AkkAkAkAkAkAAW.
AAAAAAAAAAAAAW.
aaaaaaaaaaaaaa.
.aaaaaaaaaaaaa.
""")
    right = pat("""
WWWWWWWWWWWWWW
WAAAAAAAAAAAAA
WAkAkkAkAkAkAA
WAAAAAAAAAAAAA
WAkkAkAkAkkAkA
WAAAAAAAAAAAAA
WAkAkAkkAkAkAA
WAAAAAAAAAAAAA
WAAAAAAvvvvvAA
WAkAkAAvuuuvAA
WAAAAAAvuVuvAA
WAkAkkAvuuuvAA
WAAAAAAvvvvvAA
WAAAAAAAAAAAAA
aaaaaaaaaaaaaa
aaaaaaaaaaaaa.
""")
    c.blit(left, 5, 11)
    c.blit(right, 21, 11)
    # cover edges below (earth) and spine
    c.rect(4, 27, 32, 2, "earth")
    c.rect(4, 29, 32, 1, "earth_dark")
    c.vline(19, 11, 26, "ink_dark"); c.vline(20, 11, 26, "ink_dark")
    return finish(c)


def ic_letter() -> Canvas:
    c = blank()
    x, y, w, h = 6, 11, 28, 18
    c.rect(x, y, w, h, "paper")
    c.rect(x, y, w, 1, "paper_light")
    c.rect(x, y, 1, h, "paper_light")
    c.rect(x + w - 1, y + 1, 1, h - 1, "paper_dark")
    c.rect(x + 1, y + h - 1, w - 1, 1, "paper_dark")
    # flap
    c.line(x + 1, y + 1, x + w // 2, y + 9, "paper_dark")
    c.line(x + w - 2, y + 1, x + w // 2, y + 9, "paper_dark")
    c.line(x + 1, y + h - 2, x + 9, y + 9, "paper_dark")
    c.line(x + w - 2, y + h - 2, x + w - 10, y + 9, "paper_dark")
    # wax seal
    c.circle(x + w // 2, y + 9, 3, "vermilion")
    c.set(x + w // 2 - 1, y + 7, "vermilion_light")
    c.set(x + w // 2 + 1, y + 10, "vermilion_dark"); c.set(x + w // 2, y + 11, "vermilion_dark")
    return finish(c)


def ic_map() -> Canvas:
    c = blank()
    x, y, w, h = 4, 8, 32, 24
    c.rect(x, y, w, h, "paper")
    c.rect(x + 1, y + h - 2, w - 2, 2, "paper_dark")
    c.rect(x + w - 3, y + 1, 2, h - 2, "paper_dark")
    c.rect(x + 2, y, w - 4, 1, "paper_light")
    # rolled edges
    for rx in (x, x + w - 4):
        c.rect(rx, y - 1, 4, h + 2, "earth_light")
        c.rect(rx + 1, y, 2, h, "paper_dark")
        c.rect(rx + 1, y + 1, 1, h - 2, "paper")
    # river
    for i, (px, py) in enumerate(((8, 29), (9, 27), (10, 25), (11, 23), (13, 21), (15, 20), (17, 18),
                                   (18, 16), (19, 14), (20, 12), (21, 10), (22, 9))):
        c.set(px, py, "water"); c.set(px + 1, py, "water_light" if i % 2 else "water")
    # mountains
    for (mx, my) in ((26, 15), (29, 13), (12, 13)):
        c.set(mx, my, "steel"); c.hline(mx - 1, mx + 1, my + 1, "steel"); c.hline(mx - 2, mx + 2, my + 2, "navy")
        c.set(mx, my - 1, "ink_pale")
    # road (dotted earth) and a vermilion mark
    for (px, py) in ((10, 20), (12, 19), (14, 17), (16, 15), (18, 13), (20, 12)):
        c.set(px, py, "earth")
    c.rect(26, 22, 2, 2, "vermilion"); c.set(28, 21, "vermilion"); c.set(25, 21, "vermilion")
    c.set(25, 24, "vermilion"); c.set(28, 24, "vermilion")
    return finish(c)


def ic_key() -> Canvas:
    c = blank()
    x0, y0 = 10, 30
    # bow (ring)
    c.ellipse(x0 + 1, y0 - 1, 4, 4, "gold")
    c.ellipse(x0 + 1, y0 - 1, 2, 2, None)
    c.set(x0 - 2, y0 - 3, "gold_light"); c.set(x0 - 1, y0 - 4, "gold_light"); c.set(x0 - 3, y0 - 2, "gold_light")
    c.set(x0 + 4, y0 + 1, "earth_light"); c.set(x0 + 3, y0 + 2, "earth_light"); c.set(x0 + 5, y0, "earth_light")
    c.set(x0 + 1, y0 + 3, "earth_light")
    for i in range(4, 22):                          # shaft
        band_row(c, x0, y0, i, 0, ["gold_light" if i % 5 == 0 else "gold", "earth_light"])
    # bit: two teeth hanging down-right from the shaft end
    for (tx, ty) in ((x0 + 17, y0 - 15), (x0 + 20, y0 - 18)):
        c.rect(tx, ty + 1, 2, 4, "gold")
        c.rect(tx + 1, ty + 1, 1, 4, "earth_light")
        c.set(tx, ty + 1, "gold_light")
    return finish(c)


def ic_lantern() -> Canvas:
    c = blank()
    cx, cy = 20, 20
    c.ellipse(cx, cy, 10, 11, "vermilion")
    c.ellipse(cx - 1, cy - 1, 9, 10, "vermilion_light")
    c.ellipse(cx + 3, cy + 3, 7, 8, "vermilion")
    c.ellipse(cx - 1, cy - 1, 6, 8, "vermilion_light")
    for dx in (-6, -3, 0, 3, 6):                   # ribs
        for y in range(cy - 11, cy + 12):
            if c.get_name(cx + dx, y) in ("vermilion", "vermilion_light"):
                c.set(cx + dx, y, "vermilion_dark" if dx >= 0 else "vermilion")
    c.rect(cx - 6, cy - 7, 3, 2, "gold_light")
    c.set(cx - 7, cy - 5, "gold_light")
    # caps
    c.rect(cx - 5, cy - 13, 11, 3, "gold")
    c.rect(cx - 5, cy - 13, 11, 1, "gold_light")
    c.rect(cx - 5, cy + 11, 11, 3, "gold")
    c.rect(cx - 5, cy + 13, 11, 1, "earth_light")
    # ring on top, tassel below
    c.rect(cx - 1, cy - 16, 3, 3, "ink_light")
    c.set(cx, cy - 15, None)
    c.vline(cx, cy + 14, cy + 15, "gold")
    c.rect(cx - 2, cy + 16, 5, 3, "vermilion")
    c.rect(cx - 2, cy + 18, 5, 1, "vermilion_dark")
    return finish(c)


def ic_rice_soup() -> Canvas:
    return finish(pat("""
.......W.......W..........
......W.......W...........
......W.......W...........
.......W.......W..........
.......W.......W..........
....PPPPPPPPPPPPPPPPPP....
..PPAAAAAAAAAAAAAAAAAAPP..
.PAsssssssssssssssssssAP..
.PAsWsLLsssssWWssLssssAPI.
.PPAsssssssssssssssssAPPI.
.IPPAAAAAAAAAAAAAAAAAPPPI.
.IPPPPPPPPPPPPPPPPPPPIIII.
.IPPPPPPPPPPPPPPPPPPPIIII.
..IvvvvvvvvvvvvvvvvvvvII..
..IIPPPPPPPPPPPPPPPIIII...
...IIPPPPPPPPPPPPPIIII....
....IIIPPPPPPPPPPIIII.....
......IIIIIIIIIIIII.......
........iiiiiiiiii........
........iiiiiiiiii........
"""))


def ic_wine_jug() -> Canvas:
    return finish(pat("""
.........vVVv.........
........VVVVVv........
........vvvvvv........
.........eeee.........
........Feeeee........
.......FFeeeeeE.......
......FFeeeeeeeE......
.....FFeeeeeeeeEE.....
....FFeeeeeeeeeeEE....
...FFeeeeeeeeeeeeEE...
...FeeeeAAAAAAeeeEE...
...FeeeeAvvvvAeeeEE...
...FeeeeAvAAvAeeeEE...
...FeeeeAvvvvAeeeEE...
...FeeeeAAvvAAeeeEE...
...FeeeeAAAAAAeeeEE...
...FeeeeeeeeeeeeeEE...
...FeeeeeeeeeeeeeEE...
....FeeeeeeeeeeeEE....
.....FeeeeeeeeeEE.....
......eeeeeeeeeE......
.......EEEEEEEE.......
"""))


def ic_tea() -> Canvas:
    return finish(pat("""
...........W.....W..........
..........W.....W...........
..........W.....W...........
...........W.....W..........
.......PPPPPPPPPPPPPPP......
......PAAAAAAAAAAAAAAAP.....
......PALLLLLLLLLLLLLAP.....
......PAMLLLLLLLLLLLMAPI....
......PPAAAAAAAAAAAAAPPI....
......PPPPPPPPPPPPPPPPII....
......PWPPPPPPPPPPPPPPII....
......PWPPPPPPPPPPPPPIII....
.......PPPPPPPPPPPPPPII.....
.......PPPPPPPPPPPPPPII.....
........PPPPPPPPPPPPII......
.........IIIIIIIIIIII.......
....PPPPPPPPPPPPPPPPPPPPP...
...PPPPPPPPPPPPPPPPPPPPPPI..
....IIIIIIIIIIIIIIIIIIIII...
"""))


def ic_herb() -> Canvas:
    return finish(pat("""
.........pL...............
........pLL....LL.........
..LL...pLLM...LLM.........
.LLLM..LLMM..LLMM.........
.LLMM..LLMM..LMMM..LL.....
..LMMM.LMMM..LMMD.LLM.....
...LMM.LMMD.LMMD..LMM.....
....LMD.MD..MMD..LMMD.....
.....MMD.MD.MD..LMMD......
......DMD.MDM..MMDD.......
.......DDD.M..MDD.........
........DDDM.MD...........
.........DMMMD............
..........DMD.............
..........sMs.............
.........ssss.............
........sFsFs.............
.......sFsEsFs............
......sF.sE.Fs............
.....sF..sE..s............
"""))


def ic_mushroom() -> Canvas:
    return finish(pat("""
..........FFFFFFFF..........
........FFFFFFFFFFFe........
.......FFFFFFFFFFFFee.......
......FFWWFFFFFFFFFeee......
.....FFWWFFFFFFFFFFeeee.....
.....FFFFFFFFFFFFFeeeeee....
.....eeeeeeeeeeeeeeeeeEE....
......EEEEEEEEEEEEEEEEE.....
........aAAAAAAAaa..........
........aAAAAAAAaa..FFFF....
........aAAAAAAAaa.FFFFFe...
........aAAAAAAaaa.FWFFFee..
........aAAAAAAaaa.FFFFeeee.
........aAAAAAAaaa.eeeeeeEE.
........aAAAAAAaaa..aAAAaa..
.......aAAAAAAAaaa..aAAAaa..
.......aAAAAAAAaaa..aAAAaa..
.......aaaaaaaaaaa..aaaaaa..
"""))


def ic_bamboo_shoot() -> Canvas:
    return finish(pat("""
.........pp.........
........pLp.........
........sLL.........
.......sssLp........
.......sassL........
......saassLp.......
......sasssLL.......
.....saaasssL.......
.....sasasssLp......
....saaaassssL......
....sasaassssL......
...saaaaassssLp.....
...sasaaasssssL.....
..saaaaaassssssL....
..sasaaaaassssssp...
..aaaaaaaaasssssa...
.saaaaaaaaaasssssa..
.sasaaaaaaaassssssa.
.aaaaaaaaaaaasssssa.
.saaaaaaaaaaaassssa.
.aEaaaaaaaaaaaassaa.
..EEaaaaaaaaaaaaaa..
...EEEaaaaaaaaaaE...
.....EEEEEEEEEE.....
"""))


def ic_fish() -> Canvas:
    return finish(pat("""
............SSSS..............
.........SSSSSSSSSS...........
.......SSSPSSSSSSSSSS.........
.....SSSSSPSSSSSSSSSSS....ii..
....SSSSSSSSSSSSSSSSSSS..iii..
...SSWSSSSSSSSSSSSSSSSSSiiii..
..SSKKSSSSSSSSSSSSSSSSSSiii...
..SPKWSSSSSSSSSSSSSSSSSiii....
..PPPPPPPPPPPPSSSSSSSSSii.....
...PPPPPPPPPPPPPPPPSSSSii.....
....PPPPPPiiiiPPPPPPSSSiii....
.....PPPPPiiPPPPPPPPPSiiii....
.......PPPPiiPPPPPPPIIIIii....
..........iii.......IIII......
"""))


def ic_meat() -> Canvas:
    return finish(pat("""
..............vvvvvv....
............vvVVVvvvvv..
...........vVVVVvvvvvvv.
..........vVVVVvvvvvvvvv
.........vVVVvvvvvvvvvvu
........vVVvvvvvvvvvvvvu
.......vVvvvvvvvvvvvvvuu
......vvvvvvvvvvvvvvvvuu
.....vvvvvvvvvvvvvvvvuuu
....vvvvvvvvvvvvvvvvuuuu
...PPvvvvvvvvvvvvvvuuuu.
..PWPPvvvvvvvvvvvvuuuu..
.PWWPPPvvvvvvvvvvuuuuu..
.PWPPPPPvvvvvvvvuuuuu...
..PPPP..vvvvvvvuuuuu....
...PP.....uuuuuuuu......
"""))


def ic_rope() -> Canvas:
    """Coiled rope: a thick ring with twist segments, tied at the top, loose ends hanging."""
    import math
    c = blank()
    cx, cy = 20, 21
    for y in range(ICON):
        for x in range(ICON):
            dx, dy = x - cx, y - cy
            ro = (dx / 13.0) ** 2 + (dy / 10.0) ** 2
            ri = (dx / 6.5) ** 2 + (dy / 4.0) ** 2
            if ro <= 1.0 and ri >= 1.0:
                a = math.atan2(dy, dx)
                seg = int((a + math.pi) / (math.pi / 7)) % 2
                light = (dx + dy) < 0
                if seg:
                    col = "sand" if light else "earth_light"
                else:
                    col = "earth_light" if light else "earth"
                c.set(x, y, col)
    # darker inner edge at the bottom-right of the hole, light outer rim top-left
    c.ellipse(cx + 1, cy + 1, 7, 5, "earth_dark", fill=False)
    c.ellipse(cx, cy, 6.5, 4, None)
    # tie (knot) at the top
    c.rect(cx - 3, cy - 12, 6, 5, "earth_dark")
    c.rect(cx - 2, cy - 11, 4, 3, "earth")
    c.set(cx - 2, cy - 11, "earth_light")
    # loose ends hanging from the tie to the right
    c.line(cx + 3, cy - 10, cx + 9, cy - 4, "sand")
    c.line(cx + 4, cy - 10, cx + 10, cy - 4, "earth")
    c.vline(cx + 9, cy - 4, cy - 1, "sand"); c.vline(cx + 10, cy - 4, cy - 1, "earth")
    c.rect(cx + 8, cy - 1, 4, 2, "earth_dark")
    return finish(c)


def ic_flint() -> Canvas:
    """Flint stone (right), steel striker (left), spark between."""
    c = blank()
    c.blit(pat("""
......PPPPPP......
....PPPPPPPPII....
..PPPWWPPPPPIIII..
.PPPWPPPPPIIIIIIi.
.PPPPPPPPIIIIIIii.
..PPPPPIIIIIIIiii.
...IIIIIIIIIiiii..
.....iiiiiiiii....
"""), 20, 20)
    c.blit(pat("""
...SSSSS..
..SScSSSS.
.SSScS.SSS
.SSS....SS
.SSS....SS
.SSS....SS
.SSS....SS
.SSScS.SSS
..SScSSSS.
...SSSSS..
"""), 4, 14)
    out = finish(c)
    sparkle(out, 19, 11, "gold_light", 2)
    sparkle(out, 19, 11, "gold", 0)
    for (x, y) in ((15, 8), (23, 8), (24, 15), (14, 14)):
        out.set(x, y, "gold_light")
    sparkle(out, 27, 5, "gold_light", 1)
    sparkle(out, 11, 6, "gold_light", 0)
    return out


def ic_gourd() -> Canvas:
    return finish(pat("""
.........EEE.........
.........EeE.........
........sssss........
.......sWWssss.......
.......sWsssssF......
.......sssssssF......
........sssssF.......
........sssssF.......
.......vvvvvvvv......
......sssssssssF.....
.....sWWsssssssFF....
....sWWssssssssssF...
....sWsssssssssssF...
...sssssssssssssFFF..
...ssssssssssssFFFF..
...sssssssssssFFFFF..
...sssssssssssFFFFF..
....ssssssssssFFFF...
....ssssssssssFFFF...
.....sssssssFFFFF....
......ssssFFFFFF.....
........FFFFFF.......
"""))


def ic_bandage() -> Canvas:
    """Roll of white cloth seen end-on (spiral) with a length unrolling to the right."""
    return finish(pat("""
......WWWWWWWW................
....WWAAAAAAAAWa..............
...WAAAAaaaaaAAAa.............
..WAAAaaAAAAAaaAAa............
..WAAaAAAaaaaAaAAa............
.WAAaAAaaAAAaaAAAAa...........
.WAAaAAaAWWAaaAAAAa...........
.WAAaAAaAWAAaAAAAAa...........
.WAAaAAaaAAaaAAAAAa...........
.WAAaAAAaaaaAAAAAAa...........
.aAAAaaAAAAAaAAAAAa...........
..aAAAaaaaaaAAAAAAaWWWWWWWWW..
..aAAAAAAAAAAAAAAAaAAAAAAAAAW.
...aAAAAAAAAAAAAAaaAaAaAaAaAa.
.....aaAAAAAAAAAaaaAAAAAAAAAa.
.......aaaaaaaaaa..aaaaaaaaaa.
"""))


def ic_needle() -> Canvas:
    c = blank()
    # three acupuncture needles fanned out, coiled gold handles at the bottom-left
    for (x0, y0, length) in ((6, 32, 27), (9, 34, 24), (4, 30, 22)):
        for i in range(length):
            if i < 7:
                col = "gold" if i % 2 == 0 else "gold_light"
            else:
                col = "ink_pale" if i < length - 2 else "paper_light"
            c.set(x0 + i, y0 - i if (x0, y0, length) == (6, 32, 27) else y0 - i + (i // 4 if x0 == 9 else -(i // 4)), col)
    return finish(c)


def ic_ink_brush() -> Canvas:
    c = blank()
    x0, y0 = 3, 31
    for i in range(20):                              # handle (bamboo)
        cols = ["earth_light", "earth", "earth_dark"]
        if i % 6 == 2:
            cols = ["earth", "earth_dark", "earth_dark"]
        band_row(c, x0, y0, i, 0, cols)
    for i in range(20, 22):                          # ferrule
        band_row(c, x0, y0, i, 0, ["ink_pale", "ink_light", "ink"])
    tip = [(0, ["ink_light", "ink", "ink_dark", "ink_dark"]), (0, ["ink", "ink_dark", "ink_dark", "ink_dark"]),
           (1, ["ink", "ink_dark", "ink_dark"]), (1, ["ink", "ink_dark", "ink_dark"]), (2, ["ink", "ink_dark"]),
           (2, ["ink_dark"]), (3, ["ink_dark"])]
    for i, (off, cols) in enumerate(tip):
        band_row(c, x0, y0, 22 + i, off, cols)
    # loop at the handle end
    c.vline(x0, y0 + 1, y0 + 3, "sand")
    c.ellipse(x0, y0 + 5, 2, 2, "sand", fill=False)
    return finish(c)


def ic_stone() -> Canvas:
    return finish(pat("""
.........PPPPPPPP..........
.......PPPPPPPPPPPII.......
.....PPWWPPPPPPPPPIIII.....
....PPWWPPPPPPPPIIIIIII....
...PPPPPPPPPPPPIIIIIIIIi...
..PPPPPPPPPPPIIIIIIIIIiii..
..PPPPPPPPPPIIIIIIIIIiiii..
..PPPPPPPPPIIIIIIIIIiiiii..
..IPPPPPPIIIIIIIIIIiiiiii..
..IIPPPIIIIIIIIIIIiiiiiii..
...IIIIIIIIIIIIIIiiiiiii...
....IIIIIIIIIIIiiiiiiii....
......IIIIIiiiiiiiiii......
.........iiiiiiiiii........
"""))


def ic_fan() -> Canvas:
    c = blank()
    px, py = 20, 32                                  # pivot
    R = 19
    for y in range(ICON):
        for x in range(ICON):
            dx, dy = x - px, y - py
            d2 = dx * dx + dy * dy
            if dy <= 0 and d2 <= R * R and d2 >= 5 * 5:
                # only the upper sector between ~20 and 160 degrees
                if abs(dx) <= -dy * 2.4 + 2:
                    c.set(x, y, "paper")
    # ribs
    import math
    for k in range(9):
        ang = math.radians(22 + k * 17)
        ex, ey = px + int(round(R * math.cos(ang))), py - int(round(R * math.sin(ang)))
        c.line(px, py - 2, ex, ey, "earth" if k % 2 else "earth_light")
    # outer edge shade and a painted ink mountain
    c.hline(11, 15, 21, "ink_light"); c.hline(12, 14, 20, "ink_light"); c.set(13, 19, "ink")
    c.hline(16, 19, 22, "ink"); c.set(17, 21, "ink"); c.set(18, 21, "ink")
    c.rect(25, 17, 3, 3, "vermilion"); c.set(26, 18, "vermilion_light")
    # handle sticks
    c.rect(px - 3, py - 6, 2, 9, "earth_dark")
    c.rect(px + 1, py - 6, 2, 9, "earth")
    c.rect(px - 1, py - 4, 2, 7, "earth")
    c.rect(px - 1, py + 1, 2, 2, "gold")
    return finish(c)


def ic_poison() -> Canvas:
    return finish(pat("""
.......EEEEE.......
.......EeeeE.......
.......EeeeE.......
......qqqqqqq......
......qqqqqqq......
.....qqqqqqqNN.....
....qWqqqqqqqNN....
...qWWqqqqqqqqNN...
...qWqqqqqqqqqNN...
..qqqqAAAAAAAqqNN..
..qqqqAvAAAvAqqNN..
..qqqqAAvAvAAqqNN..
..qqqqAAAvAAAqqNN..
..qqqqAAvAvAAqqNN..
..qqqqAvAAAvAqqNN..
..qqqqAAAAAAAqqNN..
..qqqqqqqqqqqqqNN..
...qqqqqqqqqqqNNN..
....qqqqqqqqqNNN...
.....NNNNNNNNNN....
"""))


def ic_silk() -> Canvas:
    """A folded bolt of plum silk as sold in a shop: three stacked folds with navy shade lines,
    a paper label band around the middle with a vermilion merchant seal, satin sheen streaks,
    and the top fold's corner lifting at the left."""
    c = blank()
    x, y, w = 4, 13, 31
    for layer in range(3):
        ly = y + layer * 4
        c.hline(x + 1, x + w - 2, ly, "plum")
        c.rect(x, ly + 1, w - 1, 2, "plum")
        c.vline(x + w - 1, ly + 1, ly + 2, "bronze_navy")
        c.hline(x + 1, x + w - 2, ly + 3, "bronze_navy")
        c.hline(x + 3, x + 6, ly + 1, "paper_light")        # satin sheen on each fold
    # lifted corner of the top fold (a soft wave rising at the left)
    c.paste_pattern(["...qqq....", ".qqqWWqqq.", "qWWqqqqqqq", "qWqqqqqqqq"],
                    x - 1, y - 4, {"q": "plum", "W": "paper_light"})
    c.hline(x + 1, x + 6, y, "plum")
    # paper label band wrapped around the bolt, with a vermilion seal
    bx = x + 11
    c.rect(bx, y - 1, 8, 13, "paper")
    c.rect(bx + 7, y - 1, 1, 13, "paper_dark")
    c.rect(bx, y - 1, 1, 13, "paper_light")
    c.rect(bx + 2, y + 3, 4, 4, "vermilion")
    c.rect(bx + 3, y + 4, 2, 2, "vermilion_dark")
    return finish(c)


def ic_basket() -> Canvas:
    return finish(pat("""
...........eeeee............
.........eeFFFFFee..........
........eFF.....FFe.........
.......eF.........Fe........
.......eF.........Fe........
......eF...........Fe.......
......eF...........Fe.......
...eeeeeeeeeeeeeeeeeeeee....
..eFFFFFFFFFFFFFFFFFFFFFe...
..eFsFsFsFsFsFsFsFsFsFsFe...
..eFFsFsFsFsFsFsFsFsFsFse...
..eFsFsFsFsFsFsFsFsFsFsee...
...eFsFsFsFsFsFsFsFsFsee....
...eFsFsFsFsFsFsFsFsFsee....
...eFFsFsFsFsFsFsFsFsee.....
....eFsFsFsFsFsFsFsFsee.....
....eFsFsFsFsFsFsFsFee......
.....eFFsFsFsFsFsFsee.......
.....eeFsFsFsFsFsFee........
......eeeeeeeeeeeee.........
"""))


# ------------------------------------------------------------------------------------------
# minis (16x16)
# ------------------------------------------------------------------------------------------
def mini_finish(c: Canvas) -> Canvas:
    out = c.centered(MINI, MINI)
    return out.outlined("ink_black")


def mini_coin() -> Canvas:
    return mini_finish(pat("""
....GGGGg....
..GGgggggg...
.Ggggggggge..
.Ggggeeeggee.
Ggggge.egggee
Ggggge.egggee
Ggggge.egggee
.gggeeeegggee
.ggggggggggee
..ggggggggee.
....gggeee...
"""))


def mini_hp() -> Canvas:
    return mini_finish(pat("""
..vvv...vvv..
.vVVvv.vvvvv.
vVVvvvvvvvvvu
vVvvvvvvvvvuu
vvvvvvvvvvvuu
.vvvvvvvvvuu.
..vvvvvvvuu..
...vvvvvuu...
....vvvuu....
.....vuu.....
......u......
"""))


def mini_qi() -> Canvas:
    return mini_finish(pat("""
.....hhhh....
...hhJJJJh...
..hJJjjjJJj..
.hJj...hjJj..
.hJ..hhJjJj..
.hJ..hJjjJj..
.hJj.hJJJJj..
.hJJj.jjjj...
..jJJjj......
...jjJJJJjj..
.....jjjjjj..
"""))


def mini_fatigue() -> Canvas:
    return mini_finish(pat("""
...PPP...kkkkk
..PWPP......k.
.PWPP......k..
.PPP......k...
.PPP......kkkk
.PPP..........
.PPP.....kkk..
.PPPP......k..
..PPPP....k...
...PPPPP..kkk.
.....PPP......
"""))


def mini_hunger() -> Canvas:
    return mini_finish(pat("""
.....WW.W....
....W.WW.....
.PPPPPPPPPPP.
PAAAAAAAAAAAP
PAssssssssssP
.PAAAAAAAAAP.
.PPPPPPPPPPI.
..PPPPPPPPII.
...PPPPPPII..
....iiiiii...
"""))


def mini_warmth() -> Canvas:
    return mini_finish(pat("""
.....V.......
....VV.......
....VVV..V...
...VVVV.VV...
...VVGVVVVV..
..VVGGGVVVV..
..VVGGGGVvv..
..VGGGGGGvv..
..vVGGGGGvv..
..vvVGGGvvu..
...vvVVvvu...
....vvvvu....
"""))


def mini_qi_orb() -> Canvas:
    c = pat("""
....hhhh....
..hhJJJJhh..
.hhWWJJJJJh.
.hWWJJJJJJj.
hhWJJJJJJJjj
hJJJJJJJJjjj
hJJJJJJJjjjj
.JJJJJJjjjj.
.jJJJJjjjjj.
..jjjjjjjj..
....jjjj....
""")
    out = mini_finish(c)
    for (x, y) in ((1, 3), (14, 2), (13, 13), (2, 12)):
        out.set(x, y, "jade_light")
    return out


# ------------------------------------------------------------------------------------------
# inventory (binding names of §5.3, in sheet order)
# ------------------------------------------------------------------------------------------
ICONS: List[Tuple[str, object, str]] = [
    # weapons
    ("jian", ic_jian, "weapon,gpa_kind"),
    ("jian_rusty", ic_jian_rusty, "weapon"),
    ("jian_iron", ic_jian_iron, "weapon"),
    ("jian_steel", ic_jian_steel, "weapon"),
    ("jian_cheongun", ic_jian_cheongun, "weapon,cheongun"),
    ("dagger", ic_dagger, "weapon,gpa_kind"),
    ("dagger_heuksa", ic_dagger_heuksa, "weapon,heuksa"),
    ("dao", ic_dao, "weapon"),
    ("cleaver", ic_cleaver, "weapon"),
    ("sling", ic_sling, "weapon"),
    ("staff", ic_staff, "weapon"),
    ("fist_wraps", ic_fist_wraps, "weapon"),
    # armor
    ("robe", ic_robe, "armor,gpa_kind"),
    ("robe_hemp", ic_robe_hemp, "armor"),
    ("vest_leather", ic_vest_leather, "armor"),
    ("robe_cheongun", ic_robe_cheongun, "armor,cheongun"),
    ("robe_heuksa", ic_robe_heuksa, "armor,heuksa"),
    ("armor_soft", ic_armor_soft, "armor"),
    # shoes
    ("straw_sandals", ic_straw_sandals, "shoes"),
    ("leather_boots", ic_leather_boots, "shoes"),
    ("cloud_shoes", ic_cloud_shoes, "shoes"),
    # gloves
    ("glove", ic_glove, "gloves,gpa_kind"),
    ("cloth_wraps", ic_cloth_wraps, "gloves"),
    ("leather_gloves", ic_leather_gloves, "gloves"),
    # accessories
    ("lucky_coin", ic_lucky_coin, "accessory"),
    ("jade_pendant", ic_jade_pendant, "accessory"),
    ("jade_pendant_old", ic_jade_pendant_old, "accessory"),
    ("jade_pendant_cheongun", ic_jade_pendant_cheongun, "accessory,cheongun"),
    ("sachet", ic_sachet, "accessory"),
    ("talisman", ic_talisman, "accessory,gpa_kind"),
    ("poison_pouch", ic_poison_pouch, "accessory,heuksa"),
    # consumables
    ("salve", ic_salve, "consumable"),
    ("pill", ic_pill, "consumable,gpa_kind"),
    ("pill_qi", ic_pill_qi, "consumable"),
    ("powder", ic_powder, "consumable"),
    ("pill_antidote", ic_pill_antidote, "consumable"),
    ("pill_clear", ic_pill_clear, "consumable"),
    ("pill_vigor", ic_pill_vigor, "consumable"),
    # elixirs
    ("elixir_red", ic_elixir_red, "elixir"),
    ("elixir_purple", ic_elixir_purple, "elixir"),
    ("elixir_blue", ic_elixir_blue, "elixir"),
    ("elixir_orange", ic_elixir_orange, "elixir"),
    ("elixir_green", ic_elixir_green, "elixir"),
    ("elixir_white", ic_elixir_white, "elixir"),
    ("elixir_gold", ic_elixir_gold, "elixir"),
    # manuals
    ("manual", ic_manual, "manual,gpa_kind"),
    ("manual_dao", ic_manual_dao, "manual"),
    ("manual_palm", ic_manual_palm, "manual"),
    ("manual_fist", ic_manual_fist, "manual"),
    ("manual_kick", ic_manual_kick, "manual"),
    ("scroll_mind", ic_scroll_mind, "manual"),
    # misc
    ("coin", ic_coin, "misc,gpa_kind"),
    ("coin_stack", ic_coin_stack, "misc"),
    ("ledger", ic_ledger, "misc,quest"),
    ("letter", ic_letter, "misc,quest"),
    ("map", ic_map, "misc"),
    ("key", ic_key, "misc"),
    ("lantern", ic_lantern, "misc"),
    ("rice_soup", ic_rice_soup, "misc,food"),
    ("wine_jug", ic_wine_jug, "misc,food"),
    ("tea", ic_tea, "misc,food"),
    ("herb", ic_herb, "misc,material"),
    ("mushroom", ic_mushroom, "misc,food"),
    ("bamboo_shoot", ic_bamboo_shoot, "misc,food"),
    ("fish", ic_fish, "misc,food"),
    ("meat", ic_meat, "misc,food"),
    ("rope", ic_rope, "misc,material"),
    ("flint", ic_flint, "misc,material"),
    ("gourd", ic_gourd, "misc"),
    ("bandage", ic_bandage, "misc"),
    ("needle", ic_needle, "misc"),
    ("ink_brush", ic_ink_brush, "misc"),
    ("stone", ic_stone, "misc,material"),
    ("fan", ic_fan, "misc"),
    ("poison", ic_poison, "misc,gpa_kind"),
    ("silk", ic_silk, "misc,material"),
    ("basket", ic_basket, "misc"),
]

MINIS: List[Tuple[str, object, str]] = [
    ("coin", mini_coin, "hud,money"),
    ("hp", mini_hp, "hud,stat"),
    ("qi", mini_qi, "hud,stat"),
    ("fatigue", mini_fatigue, "hud,stat"),
    ("hunger", mini_hunger, "hud,mountain"),
    ("warmth", mini_warmth, "hud,mountain"),
    ("qi_orb", mini_qi_orb, "hud,qi"),
]

GPA_KINDS = ("jian", "dagger", "robe", "glove", "pill", "talisman", "coin", "manual", "poison")


def make_sheets() -> Tuple[Sheet, Sheet]:
    sheet = Sheet(SHEET, "icons", pivot=(0.5, 0.5), file_name="icons_sheet")
    for name, fn, tags in ICONS:
        c = fn()
        if (c.w, c.h) != (ICON, ICON):
            raise ValueError(f"icon {name} is {c.w}x{c.h}, expected {ICON}x{ICON}")
        sheet.add(f"{SHEET}_{name}", c, tags=tags)
    for k in GPA_KINDS:
        if f"{SHEET}_{k}" not in sheet:
            raise ValueError(f"GPA kind icon {k!r} missing")
    mini = Sheet(MINI_SHEET, "icons", pivot=(0.5, 0.5))
    for name, fn, tags in MINIS:
        c = fn()
        if (c.w, c.h) != (MINI, MINI):
            raise ValueError(f"mini {name} is {c.w}x{c.h}, expected {MINI}x{MINI}")
        mini.add(f"{MINI_SHEET}_{name}", c, tags=tags)
    return sheet, mini


def build(art_root: str, preview_dir: str, cellmap_dir: str) -> List[str]:
    sheet, mini = make_sheets()
    icons_dir = os.path.join(art_root, "Icons")
    mini_dir = os.path.join(icons_dir, "Mini")
    os.makedirs(mini_dir, exist_ok=True)
    os.makedirs(preview_dir, exist_ok=True)
    written: List[str] = []
    written += sheet.save_singles(icons_dir)
    written += list(sheet.save(icons_dir))
    written += mini.save_singles(mini_dir)
    written.append(sheet.preview(os.path.join(preview_dir, f"{sheet.file_name}_preview.png"), scale=4))
    written.append(mini.preview(os.path.join(preview_dir, f"{mini.file_name}_preview.png"), scale=4))
    return written


if __name__ == "__main__":  # quick manual run into a scratch folder
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.getcwd(), "icons_out")
    for p in build(os.path.join(root, "Art"), os.path.join(root, "previews"), os.path.join(root, "cellmaps")):
        print(p)
