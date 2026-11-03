"""gen_ui.py -- ASSET_SPEC.md §5.5: the InkPixel UI set (kind `ui`).

Writes
    Art/UI/Status/<name>.png     20 status icons, 16x16 (one symbol, ink_black outline, one accent)
    Art/UI/Markers/<name>.png    16 map markers, 16x16 (tiny pictograms readable at 1x)
    Art/UI/Frames/<name>.png     panels / bar frames / bar fills / slots / cursor / arrow / seal
                                 (+ <name>.sprites.json for every 9-sliced frame, one sprite,
                                 border recorded, so the Unity importer slices it with the border)
    Art/UI/ui_sheet.png + ui_sheet.sprites.json   everything packed, borders in the sidecar
    Docs/previews/ui_sheet_preview.png            4x labelled contact sheet
    Docs/previews/ui_mockup_preview.png           frames in use (9-sliced, bars with fills, slots,
                                                  status row, markers on paper and on ink) at 3x

Everything is a hand-drawn ASCII pattern or a few procedural strokes; no randomness, so the
output is byte-identical between runs. Colors are palette names only (letters of CM below,
the same letter map the icon/tile generators use).

Design notes (ink-wash mood, light from the top-left):
  * status icons: a 12-14 px symbol with a 2-3 tone ramp of ONE accent (vermilion, jade, gold,
    plum, steel) or a neutral (ink / paper) body, then `outlined("ink_black")`.
  * markers: solid silhouettes (roofs, gate, bridge...) with internal ink lines where two parts
    would otherwise merge; player = gold ring, companion = paper dot, quest = vermilion '!'.
  * 9-slice frames keep the stretchable middles uniform (texture only in the fixed corners) so
    sliced/tiled rendering never streaks.

Run:  python3 Tools/pixelgen/build_all.py ui
      python3 Tools/pixelgen/gen_ui.py --review   (also writes 8x close-ups to Docs/previews/tmp/)
"""
from __future__ import annotations

import json
import math
import os
from collections import OrderedDict
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from pixelkit import Canvas, Sheet, check_sidecar

SHEET_NAME = "ui"
FILE_NAME = "ui_sheet"
PIVOT = (0.5, 0.5)

# one letter per palette color (identical to gen_icons.py / the tile generators) ----------------
CM: Dict[str, Optional[str]] = {
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


# ------------------------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------------------------
def pat(text: str, roles: Optional[Dict[str, Optional[str]]] = None, size: Optional[int] = None) -> Canvas:
    """ASCII block -> Canvas. '.' is transparent, blank leading/trailing lines are dropped, rows
    are padded; `size` pads (or checks) the canvas to size x size. `roles` adds/overrides letters."""
    rows = [r.rstrip() for r in text.split("\n")]
    while rows and not rows[0].strip():
        rows.pop(0)
    while rows and not rows[-1].strip():
        rows.pop()
    w = max(len(r) for r in rows)
    if size is not None:
        if w > size or len(rows) > size:
            raise ValueError(f"pattern {w}x{len(rows)} does not fit {size}x{size}")
        w = size
        rows += ["" for _ in range(size - len(rows))]
    cm: Dict[str, Optional[str]] = dict(CM)
    if roles:
        cm.update(roles)
    return Canvas.from_pattern([r.ljust(w, ".") for r in rows], cm)


def pat16(text: str, roles: Optional[Dict[str, Optional[str]]] = None) -> Canvas:
    return pat(text, roles, size=16)


def fin(c: Canvas, size: int = 16, outline: bool = True, center: bool = False) -> Canvas:
    """Finish a 16x16 icon: optional centring, a check that the art leaves 1px for the
    outline, then the 1px ink_black outline (4-neighbour, size kept)."""
    if (c.w, c.h) != (size, size):
        c = c.centered(size, size)
    elif center:
        c = c.centered(size, size)
    bb = c.bbox()
    if bb is None:
        raise ValueError("empty icon")
    x, y, w, h = bb
    if outline and (x < 1 or y < 1 or x + w > size - 1 or y + h > size - 1):
        raise ValueError(f"art bbox {bb} leaves no room for the outline in {size}x{size}")
    return c.outlined("ink_black") if outline else c


def chevron(c: Canvas, apex_x: int, top: int, half_w: int, thick: int, body: str,
            hi: Optional[str] = None, down: bool = False) -> None:
    """A '^' (or 'v' when down) band: each column |dx| <= half_w gets `thick` pixels starting
    `|dx|` rows below `top` (above when down). `hi` colours the top-most (light) pixel of
    every column on the left half + the apex."""
    for dx in range(-half_w, half_w + 1):
        x = apex_x + dx
        d = abs(dx)
        for t in range(thick):
            y = (top + d + t) if not down else (top - d - t)
            col = body
            if hi is not None and t == 0 and dx <= 0:
                col = hi
            c.set(x, y, col)


def thick_line(c: Canvas, x0: int, y0: int, x1: int, y1: int, color: str, thick: int = 2,
               step: Tuple[int, int] = (1, 0)) -> None:
    """Bresenham line repeated `thick` times offset by `step` (e.g. (1, 0) widens horizontally)."""
    for t in range(thick):
        c.line(x0 + step[0] * t, y0 + step[1] * t, x1 + step[0] * t, y1 + step[1] * t, color)


def ring(c: Canvas, cx: float, cy: float, r_out: float, r_in: float, color: str) -> None:
    c.circle(cx, cy, r_out, color)
    c.circle(cx, cy, r_in, None)


# ------------------------------------------------------------------------------------------
# §5.5 status icons (16x16)
# ------------------------------------------------------------------------------------------
def st_bleed() -> Canvas:
    # a single heavy blood drop: vermilion ramp, one paper glint
    return fin(pat16("""
................
.......v........
......vVv.......
......vVv.......
.....vVVvv......
.....vWVvvv.....
....vVVvvvvv....
....vVvvvvvu....
....vVvvvvvu....
....vvvvvvuu....
.....vvvvuuu....
......vuuuu.....
.......uu.......
................
"""))


def st_poison() -> Canvas:
    # plum skull with ink_pale bone glint, ink sockets and teeth gaps
    return fin(pat16("""
................
.....qqqqqq.....
....qPqqqqqq....
...qPqqqqqqqq...
...qqqqqqqqqq...
...qKKqqqqKKq...
...qKKqqqqKKq...
...qqqqqKqqqq...
....qqqqqqqq....
....qqqqqqqq....
.....qKqKqK.....
.....qqqqqq.....
................
"""))


def st_acupoint() -> Canvas:
    # ink figure, jade pressure point on the chest with four jade_light ticks
    return fin(pat16("""
................
......kkkk......
.....kkkkkk.....
.....kkkkkk.....
......kkkk......
....kkkhkkkk....
...kkkkkkkkkk...
...kkhhJJhkkk...
...kkkJJjkkkk...
...kkkkhkkkkk...
...kk.kkkk.kk...
......kkkk......
.....kkk.kkk....
.....kkk.kkk....
................
"""))


def st_injury() -> Canvas:
    # heart split by an ink crack (내상): vermilion ramp
    return fin(pat16("""
................
...vvv...vvv....
..vVVvv.vvvvv...
.vVVvvvKvvvvvu..
.vVvvvvKvvvvuu..
.vvvvvvKvvvvuu..
.vvvvvKvvvvuu...
..vvvvvKvvvuu...
...vvvvKvvuu....
....vvvKvuu.....
.....vvKuu......
......vuu.......
.......u........
................
"""))


def st_deviation() -> Canvas:
    # 주화입마: a plum vortex (2px arm, 1px ink gap) -- procedural spiral
    c = Canvas(16, 16)
    cx = cy = 7.0
    for y in range(16):
        for x in range(16):
            dx, dy = x - cx, y - cy
            r = math.hypot(dx, dy)
            if r > 6.4:
                continue
            t = (math.atan2(dy, dx) + math.pi) / (2 * math.pi)        # 0..1 around
            phase = (r - t * 3.0) % 3.0
            c.set(x, y, "plum" if phase < 2.0 else "ink_black")
    c.set(7, 7, "plum")
    c.set(6, 7, "plum")
    c.set(7, 6, "plum")
    c.set(6, 6, "ink_pale")                                           # a cold glint at the eye
    return fin(c)


def st_guard() -> Canvas:
    # jade shield: light rim top-left, dark rim bottom-right
    return fin(pat16("""
................
...JJJJJJJJJJ...
..JhhJJJJJJJjJ..
..JhJJJJJJJJjJ..
..JhJJJJJJJJjJ..
..JhJJJJJJJJjJ..
..JhJJJJJJJjjJ..
...hJJJJJJJjj...
...JJJJJJJJjj...
....JJJJJJjj....
.....JJJJjj.....
......JJjj......
.......Jj.......
................
"""))


def st_dodge() -> Canvas:
    # ink_pale afterimage: a leaning figure with two trailing wisps
    return fin(pat16("""
................
.........PPP....
........PWPP....
........PPPP....
.........PP.....
..PP...PPPPPP...
..PPP.PPPPPPPP..
.....PPPPPPPPP..
..PPP.PPPPPPP...
..PP...PPPPP....
.......PP.PP....
......PP..PP....
.....PP...PP....
................
"""))


def st_momentum() -> Canvas:
    # 기세: tall gold flame with a gold_light core and two rising sparks
    return fin(pat16("""
................
........g.......
.......gg...g...
.......ggg......
..g...gggg......
.....ggggg......
.....gGgggg.....
....ggGGgggg....
....gGGGGggg....
....gGGGGgggg...
....gGGGGGggg...
.....gGGGggg....
......ggggg.....
................
"""))


def st_ultimate() -> Canvas:
    # 절초: vermilion burst, paper_light eye
    return fin(pat16("""
................
.......v........
.......v........
...v...v...v....
....v.vVv.v.....
.....vvVvv......
......vVv.......
.vvvvVVWVVvvvv..
......vVv.......
.....vvVvv......
....v.vVv.v.....
...v...v...v....
.......v........
.......v........
................
"""))


def st_fatigue() -> Canvas:
    # ink_light figure slumped with the head sunk into the shoulders + a small 'z'
    return fin(pat16("""
................
..........III...
...........I....
.......IIIIIII..
......IIIIII....
......IIIIII....
...IIIIIIIIII...
..IIIIIIIIIIII..
..IIIIIIIIIIII..
..II.IIIIIII.I..
..II.IIIIIII.I..
.....IIIIII.....
.....III.III....
.....III.III....
................
"""))


def st_hunger() -> Canvas:
    # empty rice bowl: paper body, dark hollow, paper_dark foot
    return fin(pat16("""
................
................
................
...WWWWWWWWWW...
..WAAAAAAAAAAa..
..Akkkkkkkkkka..
..AkKKKKKKKKka..
..aAAAAAAAAAaa..
...aAAAAAAAaa...
....aAAAAAaa....
.....aaaaaa.....
......aaaa......
................
"""))


def st_cold() -> Canvas:
    # steel snowflake: six arms (vertical + 1:2 slopes) with forked tips, paper_light eye
    c = Canvas(16, 16)
    cx, cy = 7, 7
    S = "steel"
    c.vline(cx, cy - 6, cy + 6, S)
    for sx in (-1, 1):
        for sy in (-1, 1):
            pts = [(1, 0), (2, 1), (3, 1), (4, 2), (5, 2), (6, 3)]
            for dx, dy in pts:
                c.set(cx + sx * dx, cy + sy * dy, S)
    # forked tips
    for sy in (-1, 1):
        c.set(cx - 1, cy + sy * 5, S)
        c.set(cx + 1, cy + sy * 5, S)
    for sx in (-1, 1):
        for sy in (-1, 1):
            c.set(cx + sx * 5, cy + sy * 1, S)
            c.set(cx + sx * 4, cy + sy * 3, S)
    c.set(cx, cy, "paper_light")
    return fin(c)


def st_warmth() -> Canvas:
    # campfire: gold flame over two earth logs
    return fin(pat16("""
................
.......g........
......gg........
......ggg.......
.....gggg.......
.....gGgg.......
....ggGGgg......
....gGGGggg.....
....gGGGgggg....
.....gGGggg.....
..FFFFFFFFFFF...
.EeeeeeeeeeeeE..
..EEEEEEEEEEE...
................
"""))


def st_buff() -> Canvas:
    # two stacked jade chevrons
    c = Canvas(16, 16)
    chevron(c, 7, 1, 5, 3, "jade", "jade_light")
    chevron(c, 7, 7, 5, 3, "jade", "jade_light")
    for dx in range(1, 6):            # shade the right half's lowest pixel
        c.set(7 + dx, 1 + dx + 2, "jade_dark")
        c.set(7 + dx, 7 + dx + 2, "jade_dark")
    return fin(c)


def st_debuff() -> Canvas:
    # two stacked vermilion chevrons pointing down
    c = Canvas(16, 16)
    chevron(c, 7, 7, 5, 3, "vermilion", "vermilion_light", down=True)
    chevron(c, 7, 13, 5, 3, "vermilion", "vermilion_light", down=True)
    for dx in range(1, 6):
        c.set(7 + dx, 7 - dx - 2, "vermilion_dark")
        c.set(7 + dx, 13 - dx - 2, "vermilion_dark")
    return fin(c)


def st_stun() -> Canvas:
    # three gold stars circling (dizzy)
    return fin(pat16("""
................
..........g.....
.........gGg....
....g...gGGGg...
...gGg...gGg....
..gGGGg...g.....
.gGGGGGg........
..gGGGg.........
...gGg.....g....
....g.....gGg...
.........gGGGg..
..........gGg...
...........g....
................
"""))


def st_heal() -> Canvas:
    # thick jade cross, light top/left, dark bottom/right
    return fin(pat16("""
................
......hhJ.......
......hJj.......
......hJj.......
......hJj.......
......hJj.......
.hhhhhhJjjjjjj..
.hJJJJJJJJJJjj..
.jjjjjjjjjjjjj..
......hJj.......
......hJj.......
......hJj.......
......hJj.......
......jjj.......
................
"""))


def st_attack_up() -> Canvas:
    # upright jian (pale blade, vermilion guard) + a vermilion chevron
    return fin(pat16("""
................
......P.........
.....WPP...v....
.....WPP..vvv...
.....WPP.vv.vv..
.....WPP........
.....WPP........
.....WPP........
...vvVVvvv......
......kkk.......
......kkk.......
......kkk.......
......vvv.......
................
"""))


def st_defense_up() -> Canvas:
    # small jade shield under a jade chevron
    c = Canvas(16, 16)
    chevron(c, 7, 1, 4, 2, "jade", "jade_light")
    shield = pat("""
JJJJJJJJ
hJJJJJJj
hJJJJJjj
.hJJJjj.
..hJjj..
...Jj...
""")
    c.blit(shield, 4, 9)
    return fin(c)


def st_speed_up() -> Canvas:
    # three steel wind streaks with a leading chevron
    return fin(pat16("""
................
..SSSSSSS.......
.SWSSSSSSS......
................
................
.SSSSSSSSSSS....
SWSSSSSSSSSSS...
...........SSS..
............SS..
...SSSSSSS......
..SWSSSSSSS.....
................
""").shifted(1, 1))


STATUS: "OrderedDict[str, Callable[[], Canvas]]" = OrderedDict([
    ("bleed", st_bleed), ("poison", st_poison), ("acupoint", st_acupoint), ("injury", st_injury),
    ("deviation", st_deviation), ("guard", st_guard), ("dodge", st_dodge), ("momentum", st_momentum),
    ("ultimate", st_ultimate), ("fatigue", st_fatigue), ("hunger", st_hunger), ("cold", st_cold),
    ("warmth", st_warmth), ("buff", st_buff), ("debuff", st_debuff), ("stun", st_stun),
    ("heal", st_heal), ("attack_up", st_attack_up), ("defense_up", st_defense_up),
    ("speed_up", st_speed_up),
])


# ------------------------------------------------------------------------------------------
# §5.5 map markers (16x16)
# ------------------------------------------------------------------------------------------
def mk_town() -> Canvas:
    # two tiled roofs with paper walls and dark doors; ink eave lines separate roof and wall
    return fin(pat16("""
................
....ii..........
...iIii.........
..iIiiii...II...
.iIiiiiii.IPII..
.KKKKKKK.IPIIII.
..AAkkA..KKKKKK.
..AakkA...AAkA..
..AAkkA...AkkA..
..AAkkA...AkkA..
..AAkkA...AkkA..
................
"""))


def mk_sect() -> Canvas:
    # paifang: ink roof with upturned ends, jade_dark beams and posts, name board in the middle
    return fin(pat16("""
................
..i..........i..
..iiiiiiiiiiii..
...jjjjjjjjjj...
....j.AvvA.j....
....j.AvvA.j....
...jjjjjjjjjj...
....j......j....
....j......j....
....j......j....
....j......j....
...jj......jj...
................
"""))


def mk_gate() -> Canvas:
    # town gate: tiled cap, pale stone wall, dark arched opening
    return fin(pat16("""
................
..i..i.ii.i..i..
..iiiiiiiiiiii..
..IIIIIIIIIIII..
..PPPPPPPPPPPP..
..PPPPPkkPPIPP..
..PPPPkkkkPPPP..
..PIPkkkkkkPPP..
..PPPkkkkkkPIP..
..PPPkkkkkkPPP..
..PPPkkkkkkPPP..
..IIIkkkkkkIII..
................
"""))


def mk_bridge() -> Canvas:
    # humped plank bridge over water
    return fin(pat16("""
................
................
.....FFFFFF.....
...FFeeeeeeFF...
.FFeeeeeeeeeeFF.
.EeeE......EeeE.
.EeeE......EeeE.
.EEEE......EEEE.
..cwwcwwcwwcww..
..wwwwwwwwwwww..
..xwwxwwxwwxww..
................
"""))


def mk_cave() -> Canvas:
    # rock mound with a black opening
    return fin(pat16("""
................
......IIII......
....IIPIIIII....
...IPIIIIIIII...
..IIIIIKKIIIIi..
..IIIIKKKKIIIi..
.IIIIKKKKKKIIii.
.IIIIKKKKKKIiii.
.IIIIKKKKKKIiii.
.iIIIKKKKKKiiii.
.iiiiKKKKKKiiii.
................
"""))


def mk_mountain() -> Canvas:
    # two peaks: steel lit faces, navy shade, paper_light snow on the main peak
    return fin(pat16("""
................
.......W........
......WWW.......
......SWSS......
.....SSSSSn.....
.....SSSSSnn....
....SSSSSSnnn...
..S.SSSSSSnnnn..
.SSSSSSSSSnnnnn.
.SSnSSSSSSnnnnn.
.SSnnSSSSSnnnnn.
.SnnnSSSSSnnnnn.
................
"""))


def mk_encounter() -> Canvas:
    # crossed jian: pale blades, vermilion guards, earth grips
    return fin(pat16("""
................
..P.........P...
..WP.......PP...
..vWP.....PPv...
..evWP...PPve...
...e.WP.PP.e....
......WPP.......
.......PP.......
......PPWP......
.....PP..WP.....
....PP....WP....
...PP......WP...
...P........W...
................
"""))


def mk_quest() -> Canvas:
    # vermilion '!'
    return fin(pat16("""
................
.....VVvvv......
.....VVvvv......
.....VVvvu......
.....VVvvu......
.....Vvvvu......
......Vvu.......
......Vvu.......
......vvu.......
................
................
......Vvv.......
.....VVvvu......
......vuu.......
................
"""))


def mk_quest_done() -> Canvas:
    # thick jade check mark
    return fin(pat16("""
................
................
............hJ..
...........hJj..
..........hJJj..
.........hJJj...
..hJ....hJJj....
..hJJ..hJJj.....
..hJJJhJJj......
...JJJJJj.......
....JJJj........
.....Jj.........
................
"""))


def mk_player() -> Canvas:
    # gold ring with a gold_light centre dot
    c = Canvas(16, 16)
    ring(c, 7.5, 7.5, 5.5, 3.5, "gold")
    for x in range(3, 8):                      # light arc top-left
        for y in range(3, 8):
            if c.get_name(x, y) == "gold" and (x - 7.5) + (y - 7.5) < -5.5:
                c.set(x, y, "gold_light")
    c.circle(7.5, 7.5, 1.5, "gold_light")
    c.set(8, 8, "gold")
    return fin(c)


def mk_companion() -> Canvas:
    # paper dot with a light crescent and a dark rim bottom-right
    c = Canvas(16, 16)
    c.circle(7.5, 7.5, 4.5, "paper")
    c.circle(6.5, 6.5, 2.0, "paper_light")
    for x in range(16):
        for y in range(16):
            if c.get_name(x, y) == "paper" and (x - 7.5) + (y - 7.5) > 5.0:
                c.set(x, y, "paper_dark")
    return fin(c)


def mk_exit() -> Canvas:
    # bold paper arrow pointing right
    return fin(pat16("""
................
................
.........W......
.........WW.....
.........WWW....
..WWWWWWWWWWW...
..WWWWWWWWWWWW..
..WAAAAAAAAAAAA.
..AAAAAAAAAAAA..
.........AAA....
.........aa.....
.........a......
................
"""))


def mk_shop() -> Canvas:
    # 엽전: gold coin with a square hole
    return fin(pat16("""
................
.....GGGGg......
....GGGggggg....
...GGgggggggg...
..GGggggggggge..
..Gggggkkkgggee.
..Gggggkkkgggee.
..gggggkkkgggee.
..ggggggggggeee.
...gggggggggee..
....gggggeeee...
.....eeeee......
................
"""))


def mk_inn() -> Canvas:
    # 酒旗: vermilion cloth banner on an earth pole, paper mark
    return fin(pat16("""
................
..E.............
..eEEEEEEEEE....
..e.vvvvvvvv....
..e.vVWWWvvu....
..e.vVvWvvvu....
..e.vVWWWvvu....
..e.vVvWvvvu....
..e.vVWWWvvu....
..e.vvvvvvvu....
..e.vvvvvvuu....
..e..vvvvvu.....
..e.............
..E.............
................
"""))


def mk_dock() -> Canvas:
    # sampan with a mast and furled paper sail on water
    return fin(pat16("""
................
.........E......
.........EAW....
.........EAAW...
.........EAAAW..
.........EAAW...
.........EAW....
.........E......
.FFFFFFFFFFFFFF.
..eeeeeeeeeeee..
...EEEEEEEEEE...
..cwwcwwcwwcww..
..wwwwwwwwwwww..
................
"""))


def mk_shrine() -> Canvas:
    # 사당: tiled roof with upturned ends, paper walls, vermilion door, stone step
    return fin(pat16("""
................
.......ii.......
.....iiiiii.....
...iiIiiiiIii...
.i.iiiiiiiiii.i.
.iKKKKKKKKKKKKi.
...AAAvvvvAAA...
...AaAvVvvAaA...
...AAAvvuvAAA...
...AAAvvuvAAA...
..PPPPPPPPPPPP..
..IIIIIIIIIIII..
................
"""))


MARKERS: "OrderedDict[str, Callable[[], Canvas]]" = OrderedDict([
    ("town", mk_town), ("sect", mk_sect), ("gate", mk_gate), ("bridge", mk_bridge),
    ("cave", mk_cave), ("mountain", mk_mountain), ("encounter", mk_encounter), ("quest", mk_quest),
    ("quest_done", mk_quest_done), ("player", mk_player), ("companion", mk_companion),
    ("exit", mk_exit), ("shop", mk_shop), ("inn", mk_inn), ("dock", mk_dock), ("shrine", mk_shrine),
])


# ------------------------------------------------------------------------------------------
# §5.5 frames
# ------------------------------------------------------------------------------------------
def fr_panel_paper() -> Canvas:
    """24x24, border 8: hanji panel. Outer 1px paper_dark deckle, 1px ink line inset 1px,
    paper inside; a few paper_dark fibres only in the fixed corner cells (the stretchable
    edges and centre stay uniform)."""
    c = Canvas(24, 24, fill="paper")
    c.rect(0, 0, 24, 24, "paper_dark", fill=False)
    c.rect(1, 1, 22, 22, "ink_black", fill=False)
    c.rect(2, 2, 20, 20, "paper_light", fill=False)          # soft inner rim
    for x, y in ((3, 4), (4, 3), (5, 5)):                   # fibres, each corner (rotational)
        c.set(x, y, "paper_dark")
        c.set(23 - x, y, "paper_dark")
        c.set(x, 23 - y, "paper_dark")
        c.set(23 - x, 23 - y, "paper_dark")
    # ink pooling at the four corners of the line (brush starts/ends)
    for x, y in ((1, 1), (22, 1), (1, 22), (22, 22)):
        c.set(x, y, "ink_black")
    return c


def fr_panel_ink() -> Canvas:
    """24x24, border 8: dark ink panel. Outer ink_black, ink_light line inset 1px, ink_dark fill,
    a subtle ink step at the inner corners."""
    c = Canvas(24, 24, fill="ink_dark")
    c.rect(0, 0, 24, 24, "ink_black", fill=False)
    c.rect(1, 1, 22, 22, "ink_light", fill=False)
    c.rect(2, 2, 20, 20, "ink", fill=False)
    for x, y in ((3, 3), (20, 3), (3, 20), (20, 20)):
        c.set(x, y, "ink")
    return c


def fr_bar_frame(body: str, dark: str) -> Canvas:
    """48x8, border 3: ink_black outline, 1px coloured frame (dark on the bottom/right), 1px
    paper_light inner highlight on the top/left, ink_dark track."""
    c = Canvas(48, 8, fill="ink_dark")
    c.rect(0, 0, 48, 8, "ink_black", fill=False)
    c.rect(1, 1, 46, 6, body, fill=False)
    c.hline(2, 46, 6, dark)
    c.vline(46, 2, 6, dark)
    c.hline(2, 45, 2, "paper_light")
    c.vline(2, 2, 5, "paper_light")
    c.hline(3, 45, 5, "ink_black")                            # track shadow (bottom inner)
    c.vline(45, 3, 5, "ink_black")
    c.set(1, 1, "paper_light")                                # corner glint
    return c


def fr_bar_fill(light: str, body: str, dark: str) -> Canvas:
    """48x8, border 2: solid fill with a 1px lighter top line and a dark bottom line; the
    left/right 2px caps are kept by the border so a filled width never loses them."""
    c = Canvas(48, 8, fill=body)
    c.hline(0, 47, 0, light)
    c.hline(0, 47, 7, dark)
    c.vline(0, 0, 7, light)
    c.vline(47, 0, 7, dark)
    c.set(47, 0, body)
    c.set(0, 7, body)
    return c


def fr_slot() -> Canvas:
    """20x20, border 4: recessed paper slot: ink_black outline, paper_dark ring, ink_light inner
    shadow top/left, paper_light inner lip bottom/right, paper well."""
    c = Canvas(20, 20, fill="paper")
    c.rect(0, 0, 20, 20, "ink_black", fill=False)
    c.rect(1, 1, 18, 18, "paper_dark", fill=False)
    c.rect(2, 2, 16, 16, "paper_light", fill=False)
    c.hline(2, 17, 2, "ink_light")
    c.vline(2, 2, 17, "ink_light")
    c.set(17, 2, "paper_dark")
    c.set(2, 17, "paper_dark")
    return c


def fr_slot_selected() -> Canvas:
    """20x20, border 4: the same slot with a gold ring and a gold_light lip (selection)."""
    c = fr_slot()
    c.rect(1, 1, 18, 18, "gold", fill=False)
    c.rect(2, 2, 16, 16, "gold_light", fill=False)
    c.hline(2, 17, 2, "gold")
    c.vline(2, 2, 17, "gold")
    c.set(2, 2, "gold_light")
    c.set(17, 17, "gold")
    c.rect(3, 3, 14, 14, "paper_light", fill=True)
    return c


def fr_cursor() -> Canvas:
    """16x16: menu cursor, an ink arrow pointing right with a paper_light edge."""
    return fin(pat16("""
................
................
..WW............
..WkW...........
..WkkW..........
..WkkkW.........
..WkkkkW........
..WkkkkkW.......
..WkkkkkkW......
..WkkkkkW.......
..WkkkkW........
..WkkkW.........
..WkkW..........
..WkW...........
..WW............
................
"""))


def fr_arrow_down(frame: int) -> Canvas:
    """16x16 x2: dialogue 'continue' arrow; frame 1 sits 1px lower and lighter (blink)."""
    body = "ink_dark" if frame == 0 else "ink"
    c = pat16("""
................
................
................
................
..WWWWWWWWWWW...
..WkkkkkkkkkW...
...WkkkkkkkW....
....WkkkkkW.....
.....WkkkW......
......WkW.......
.......W........
................
................
................
................
................
""", roles={"k": body})
    if frame == 1:
        c = c.shifted(0, 1)
    return fin(c)


def fr_select_frame() -> Canvas:
    """20x20, border 4: four vermilion corner brackets (2px thick, light/dark), transparent
    middle. The 4x4 corners hold the brackets; edges and centre are empty."""
    c = Canvas(20, 20)
    tl = pat("""
VVVV
Vvu.
Vu..
Vu..
""")
    c.blit(tl, 0, 0)
    c.blit(tl.flipped_x(), 16, 0)
    c.blit(tl.flipped_y(), 0, 16)
    c.blit(tl.flipped_x().flipped_y(), 16, 16)
    return c


def fr_seal() -> Canvas:
    """16x16: 낙관 -- vermilion square seal with a rough vermilion_dark edge and a paper_light mark."""
    return pat16("""
................
..uuuuuuuuuuu...
.uvvvvvvvvvvvu..
.uvVWWWvvWWWvu..
.uvvvvWvvvWvvu..
.uvvWWWWWWWvvu..
.uvvvvvvvvvvvu..
.uvvWWWWWWWvvu..
.uvvWvvvvvWvvu..
.uvvWWWWWWWvvu..
.uvvvvvvvvvvvu..
.uvvvWvvvvWvvu..
.uvvvvvvvvvvvu..
..uuuuuuuuuuu...
................
................
""").shifted(1, 0)


# (sprite descriptor, canvas factory, border (l, b, r, t) or None, tags)
FRAMES: List[Tuple[str, Callable[[], Canvas], Optional[Tuple[int, int, int, int]], str]] = [
    ("panel_paper", fr_panel_paper, (8, 8, 8, 8), "frame,panel,paper"),
    ("panel_ink", fr_panel_ink, (8, 8, 8, 8), "frame,panel,ink"),
    ("bar_frame_jade", lambda: fr_bar_frame("jade", "jade_dark"), (3, 3, 3, 3), "frame,bar,jade"),
    ("bar_frame_bronze", lambda: fr_bar_frame("navy", "bronze_navy"), (3, 3, 3, 3), "frame,bar,bronze"),
    ("bar_frame_vermilion", lambda: fr_bar_frame("vermilion", "vermilion_dark"), (3, 3, 3, 3), "frame,bar,vermilion"),
    ("bar_fill_red", lambda: fr_bar_fill("vermilion_light", "vermilion", "vermilion_dark"), (2, 2, 2, 2), "fill,bar,hp"),
    ("bar_fill_blue", lambda: fr_bar_fill("water_light", "water", "water_deep"), (2, 2, 2, 2), "fill,bar,qi"),
    ("bar_fill_green", lambda: fr_bar_fill("jade_light", "jade", "jade_dark"), (2, 2, 2, 2), "fill,bar,mastery"),
    ("bar_fill_gold", lambda: fr_bar_fill("gold_light", "gold", "earth_light"), (2, 2, 2, 2), "fill,bar,fatigue"),
    ("slot", fr_slot, (4, 4, 4, 4), "frame,slot"),
    ("slot_selected", fr_slot_selected, (4, 4, 4, 4), "frame,slot,selected"),
    ("select_frame", fr_select_frame, (4, 4, 4, 4), "frame,select"),
    ("cursor", fr_cursor, None, "cursor"),
    ("arrow_down_0", lambda: fr_arrow_down(0), None, "dialogue,blink"),
    ("arrow_down_1", lambda: fr_arrow_down(1), None, "dialogue,blink"),
    ("seal", fr_seal, None, "seal,stamp"),
]


# ------------------------------------------------------------------------------------------
# sheet assembly
# ------------------------------------------------------------------------------------------
def make_sheet() -> Sheet:
    """The `ui` sheet (file ui_sheet.png), 384 px wide so the rows pack tidily:
    row 1 = 20 status icons + cursor, arrow x2, seal (24 x 16px); row 2 = 16 markers;
    then the two 24px panels, the seven 48x8 bars, the three 20px slots/frames."""
    s = Sheet(SHEET_NAME, "ui", pivot=PIVOT, max_width=384, file_name=FILE_NAME)
    for name, fn in STATUS.items():
        s.add(f"ui_status_{name}", fn(), single_name=f"Status/{name}", tags="status")
    frames = {d: (fn, border, tags) for d, fn, border, tags in FRAMES}
    for d in ("cursor", "arrow_down_0", "arrow_down_1", "seal"):
        fn, border, tags = frames[d]
        s.add(f"ui_{d}", fn(), border=border, single_name=f"Frames/{d}", tags=tags)
    for name, fn in MARKERS.items():
        s.add(f"ui_marker_{name}", fn(), single_name=f"Markers/{name}", tags="marker")
    for d, fn, border, tags in FRAMES:
        if d in ("cursor", "arrow_down_0", "arrow_down_1", "seal"):
            continue
        s.add(f"ui_{d}", fn(), border=border, single_name=f"Frames/{d}", tags=tags)
    s.add_animation("arrow_down", ["ui_arrow_down_0", "ui_arrow_down_1"], fps=2, loop=True,
                    state="blink", direction="")
    return s


def single_sidecar_doc(name: str, canvas: Canvas, border: Tuple[int, int, int, int],
                       tags: str) -> "OrderedDict[str, object]":
    """One-sprite sidecar (§3 field order) for a 9-sliced single PNG: sheet == sprite == name."""
    l, b, r, t = border
    cs = 16
    sprite = OrderedDict([
        ("name", name), ("x", 0), ("y", 0), ("w", canvas.w), ("h", canvas.h),
        ("pivotX", float(PIVOT[0])), ("pivotY", float(PIVOT[1])),
        ("borderL", int(l)), ("borderB", int(b)), ("borderR", int(r)), ("borderT", int(t)),
        ("cellX", 0), ("cellY", 0), ("cellW", -(-canvas.w // cs)), ("cellH", -(-canvas.h // cs)),
        ("solid", False), ("overlay", False), ("ground", ""), ("tags", tags),
    ])
    return OrderedDict([
        ("version", 2),
        ("sheet", name),
        ("kind", "ui"),
        ("pixelsPerUnit", 16),
        ("defaultPivotX", float(PIVOT[0])),
        ("defaultPivotY", float(PIVOT[1])),
        ("cellSize", cs),
        ("stripFrames", 0),
        ("stripFps", 0),
        ("sprites", [sprite]),
        ("animations", []),
        ("tiles", []),
        ("tileRules", []),
        ("ruleTileDefaults", []),
    ])


def write_frame_sidecars(sheet: Sheet, frames_dir: str) -> List[str]:
    out: List[str] = []
    for d, _fn, border, tags in FRAMES:
        if border is None:
            continue
        e = sheet.get(f"ui_{d}")
        doc = single_sidecar_doc(d, e.canvas, border, tags)
        problems = check_sidecar(doc, e.canvas.w, e.canvas.h, file_base=d)
        if problems:
            raise ValueError(f"{d}.sprites.json: {problems}")
        path = os.path.join(frames_dir, f"{d}.sprites.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")
        out.append(path)
    return out


# ------------------------------------------------------------------------------------------
# previews: 9-slice renderer + mock-up
# ------------------------------------------------------------------------------------------
def nine_slice(src: Canvas, border: Tuple[int, int, int, int], w: int, h: int) -> Canvas:
    """Render a 9-sliced sprite at w x h (corners fixed, edges/centre tiled)."""
    l, b, r, t = border
    out = Canvas(w, h)
    mid_w = max(1, src.w - l - r)
    mid_h = max(1, src.h - t - b)

    def map_x(x: int) -> int:
        if x < l:
            return x
        if x >= w - r:
            return src.w - (w - x)
        return l + (x - l) % mid_w

    def map_y(y: int) -> int:
        if y < t:
            return y
        if y >= h - b:
            return src.h - (h - y)
        return t + (y - t) % mid_h

    xs = [map_x(x) for x in range(w)]
    ys = [map_y(y) for y in range(h)]
    for y in range(h):
        for x in range(w):
            out.px[y, x] = src.px[ys[y], xs[x]]
    return out


def mockup(sheet: Sheet) -> Canvas:
    """A small HUD mock-up: paper panel with bars/slots/status row/cursor/seal, an ink panel
    with the same, markers on a grass/road patch and on paper. Returns the 1x canvas."""
    g = sheet.get_canvas
    W, H = 232, 150
    c = Canvas(W, H, fill="moss")
    # background: muted map patch (grass + road) for the markers
    c.rect(0, 0, W, H, "moss")
    c.dither_rect(0, 0, W, H, "moss_dark", parity=1)
    c.rect(0, 118, W, 32, "earth_light")
    c.dither_rect(0, 118, W, 32, "sand", parity=0)

    # paper panel (left) -------------------------------------------------------------
    px, py, pw, ph = 4, 4, 112, 110
    c.blit(nine_slice(g("ui_panel_paper"), (8, 8, 8, 8), pw, ph), px, py)
    # bars: jade frame + red fill, bronze + blue, vermilion + gold
    bars = [("ui_bar_frame_jade", "ui_bar_fill_red", 0.72), ("ui_bar_frame_bronze", "ui_bar_fill_blue", 0.45),
            ("ui_bar_frame_vermilion", "ui_bar_fill_gold", 0.9)]
    y = py + 8
    for frame, fill, pct in bars:
        bw = 72
        c.blit(nine_slice(g(frame), (3, 3, 3, 3), bw, 8), px + 8, y)
        fw = max(4, int(round((bw - 4) * pct)))
        c.blit(nine_slice(g(fill), (2, 2, 2, 2), fw, 4), px + 10, y + 2)
        y += 11
    # a long bar with the fill drawn in the track at 2px (frame on top) to show both usages
    c.blit(nine_slice(g("ui_bar_fill_green"), (2, 2, 2, 2), 96, 8), px + 8, y)
    c.blit(nine_slice(g("ui_bar_frame_jade"), (3, 3, 3, 3), 96, 8), px + 8, y)
    y += 12
    # slots with mini icons (status icons stand in for item icons)
    sx = px + 8
    for i, (frame, inner) in enumerate((("ui_slot", "ui_status_heal"), ("ui_slot_selected", "ui_status_guard"),
                                        ("ui_slot", "ui_status_momentum"), ("ui_slot", None))):
        c.blit(g(frame), sx, y)
        if inner:
            c.blit(g(inner), sx + 2, y + 2)
        if i == 2:
            c.blit(g("ui_select_frame"), sx, y)
        sx += 24
    # cursor + seal + dialogue arrow
    c.blit(g("ui_cursor"), px + 8, y + 24)
    c.blit(g("ui_seal"), px + pw - 24, y + 24)
    c.blit(g("ui_arrow_down_0"), px + 44, y + 24)
    c.blit(g("ui_arrow_down_1"), px + 60, y + 24)
    # status row on paper
    y += 44
    sx = px + 6
    for i, name in enumerate(STATUS):
        if i >= 10:
            break
        c.blit(g(f"ui_status_{name}"), sx + i * 10, y)
    y += 12
    for i, name in enumerate(list(STATUS)[10:]):
        c.blit(g(f"ui_status_{name}"), sx + i * 10, y)

    # ink panel (right) --------------------------------------------------------------
    px2, pw2 = 120, 108
    c.blit(nine_slice(g("ui_panel_ink"), (8, 8, 8, 8), pw2, ph), px2, py)
    y = py + 8
    for frame, fill, pct in bars:
        bw = 68
        c.blit(nine_slice(g(frame), (3, 3, 3, 3), bw, 8), px2 + 8, y)
        fw = max(4, int(round((bw - 4) * pct)))
        c.blit(nine_slice(g(fill), (2, 2, 2, 2), fw, 4), px2 + 10, y + 2)
        y += 11
    c.blit(nine_slice(g("ui_bar_fill_green"), (2, 2, 2, 2), 92, 8), px2 + 8, y)
    c.blit(nine_slice(g("ui_bar_frame_bronze"), (3, 3, 3, 3), 92, 8), px2 + 8, y)
    y += 12
    sx = px2 + 8
    for i, (frame, inner) in enumerate((("ui_slot", "ui_status_bleed"), ("ui_slot_selected", "ui_status_poison"),
                                        ("ui_slot", "ui_status_stun"), ("ui_slot", None))):
        c.blit(g(frame), sx, y)
        if inner:
            c.blit(g(inner), sx + 2, y + 2)
        if i == 0:
            c.blit(g("ui_select_frame"), sx, y)
        sx += 24
    c.blit(g("ui_cursor"), px2 + 8, y + 24)
    c.blit(g("ui_seal"), px2 + pw2 - 24, y + 24)
    c.blit(g("ui_arrow_down_0"), px2 + 44, y + 24)
    y += 44
    sx = px2 + 4
    for i, name in enumerate(STATUS):
        if i >= 10:
            break
        c.blit(g(f"ui_status_{name}"), sx + i * 10, y)
    y += 12
    for i, name in enumerate(list(STATUS)[10:]):
        c.blit(g(f"ui_status_{name}"), sx + i * 10, y)

    # markers on the map strip ----------------------------------------------------------
    mx = 4
    for i, name in enumerate(MARKERS):
        c.blit(g(f"ui_marker_{name}"), mx + i * 14, 120 if i % 2 == 0 else 132)
    return c


def write_mockup(sheet: Sheet, path: str, scale: int = 3) -> str:
    return mockup(sheet).scaled(scale).save(path)


def review_previews(sheet: Sheet, tmp_dir: str) -> List[str]:
    """8x close-ups per group + 1x/2x legibility strips on paper and on ink (reviewer aid)."""
    os.makedirs(tmp_dir, exist_ok=True)
    out: List[str] = []
    for prefix, label in (("ui_status_", "status"), ("ui_marker_", "markers"), ("ui_bar", "bars"),
                          ("ui_panel", "panels"), ("ui_slot", "slots"), ("ui_select", "select"),
                          ("ui_cursor", "cursor"), ("ui_arrow", "arrow"), ("ui_seal", "seal")):
        out.append(sheet.preview_group(os.path.join(tmp_dir, f"ui_{label}_x8.png"), prefix, scale=8))
    g = sheet.get_canvas
    for bg_name, bg in (("hanji", "paper"), ("ink", "ink_dark"), ("grass", "moss")):
        names = [f"ui_status_{n}" for n in STATUS] + [f"ui_marker_{n}" for n in MARKERS]
        strip = Canvas(len(names) * 18 + 2, 20, fill=bg)
        for i, n in enumerate(names):
            strip.blit(g(n), 2 + i * 18, 2)
        for sc in (1, 2, 4):
            out.append(strip.scaled(sc).save(os.path.join(tmp_dir, f"ui_icons_{bg_name}_x{sc}.png")))
    out.append(write_mockup(sheet, os.path.join(tmp_dir, "ui_mockup_x4.png"), scale=4))
    return out


# ------------------------------------------------------------------------------------------
# generator contract
# ------------------------------------------------------------------------------------------
def build(art_root: str, preview_dir: str, cellmap_dir: str) -> List[str]:
    ui_dir = os.path.join(art_root, "UI")
    for sub in ("Status", "Markers", "Frames"):
        os.makedirs(os.path.join(ui_dir, sub), exist_ok=True)
    os.makedirs(preview_dir, exist_ok=True)
    sheet = make_sheet()
    written: List[str] = []
    written += sheet.save_singles(ui_dir)
    written += write_frame_sidecars(sheet, os.path.join(ui_dir, "Frames"))
    written += list(sheet.save(ui_dir))
    written.append(sheet.preview(os.path.join(preview_dir, f"{sheet.file_name}_preview.png"), scale=4))
    written.append(write_mockup(sheet, os.path.join(preview_dir, "ui_mockup_preview.png"), scale=3))
    return written


if __name__ == "__main__":
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.normpath(os.path.join(here, "..", ".."))
    art = os.path.join(root, "Assets", "InkPixel", "Art")
    previews = os.path.join(root, "Docs", "previews")
    if "--review" in sys.argv:
        for p in review_previews(make_sheet(), os.path.join(previews, "tmp")):
            print(p)
    else:
        for p in build(art, previews, os.path.join(root, "Docs", "cellmaps")):
            print(p)
