"""charkit.py -- shared 16x16 character construction kit for the InkPixel (수묵 픽셀 팩) cast.

Every character sheet of ASSET_SPEC.md §5.1 (heroes, companions, NPCs, enemies) is assembled
from the same hand-drawn ASCII layers so the whole cast shares one silhouette language, one
light direction (top-left), one walk cycle and one attack grammar. A character is described by
a small *spec dict*; the kit returns the 16x16 frames that `pixelkit.character_sheet` expects
plus the 32x32 dialogue face.

    from charkit import make_character, make_face
    from pixelkit import character_sheet

    spec = {
        "build": "normal",            # child | normal | tall | burly
        "hair": "topknot",            # see HAIR_STYLES
        "headwear": "none",           # see HEADWEAR
        "beard": "none",              # none | short | long | goatee | mustache (mustache: face only)
        "hair_accessory": "none",     # none | ribbon
        "robe": "long_robe",          # see ROBE_STYLES
        "weapon": "jian",             # see WEAPONS (attack frames only)
        "hip_weapon": True,           # hilt + scabbard at the hip in walk frames (blades only)
        "expression": "neutral",      # face: see EXPRESSIONS
        "eyes": "normal",             # face: normal | narrow | closed
        "colors": {                   # palette NAMES only; friendly keys or raw letters
            "skin": "skin", "hair": "ink_dark", "cloth": "paper", "accent": "sand",
            # cloth_dark / cloth_light / hair_light / skin_shade / hat_dark / accent_dark are
            # derived from palette.RAMPS when omitted
        },
        "extras": [                   # optional custom overlays (towel, key ring, scar...)
            {"rows": ["X"], "x": 11, "y": 9, "dirs": ["down"], "poses": ["*"], "anchor": "body"},
        ],
    }
    walk, attack, hurt, face = make_character(spec)
    sheet, face_sheet = character_sheet("hero_1", walk, attack, hurt, face)

Spec keys (all optional; defaults shown above):
  build           child | normal | tall | burly        (BUILDS)
  hair            bald | short | topknot | topknot_pin | bun | bun_pin | ponytail | ponytail_high |
                  braid | loose_long
  headwear        none | straw_hat | scholar_hat | headband | hood | cap | headscarf | helmet
  beard           none | short | long | goatee | mustache
  hair_accessory  none | ribbon                          (uses the 'extra' color, X)
  robe            long_robe | robe_sash | short_tunic | vest_bare_arms | armor_lamellar | dress |
                  apron_dress | ragged
  weapon          none | palm | jian | dao | dagger | staff | spear | fan | needle_throw | sling |
                  cleaver | broom | pole | basket        ('none' == 'palm': unarmed palm strike)
  hip_weapon      bool, a hilt at the hip in the walk/idle frames (only for jian/dao/dagger/cleaver)
  carry           none | basket | bolt | scroll | abacus | gourd | towel | keys   (walk/idle/hurt
                  frames, held in the off hand; prop colors V/J, bolt uses X/Q, scroll M, keys G)
  collar          none | fur                              (fur collar over the shoulder row, V/J)
  scar            bool, a dark scar across the right eye (down/side views and the face)
  expression      neutral | smile | grin | stern | angry | sad | sly | calm | fierce | worried
  eyes            normal | narrow | closed               (face only)
  colors          {friendly-key-or-letter: palette name}, see LETTERS / FRIENDLY_KEYS
  extras          list of overlay dicts: rows (ASCII with the kit letters), x, y, dirs (list or
                  ["*"]), poses (list of pose names or ["*"]), anchor ("body" | "head"),
                  layer ("front" default | "back" = under the body), face (bool: also on the face)
  face_extras     list of overlay dicts {rows, x, y} drawn on the 32x32 face (front layer)

Placeholder letters (templates are letter grids; colors are applied last, so palette swaps are
just a different `colors` dict):
  S skin   Z skin shade   E eye   H hair   U hair light
  C cloth  D cloth dark   L cloth light   T trim/collar   A accent (sash)   a accent dark
  P pants/legs   F feet   K dark   B headwear   N headwear dark
  W weapon blade   M weapon highlight   G hilt/guard   O wood   V prop   J prop dark
  X extra accent (ribbon, headband, patches)   Q extra 2 (palm-strike qi)
  '.' transparent.  Lowercase 'c' is the sleeve (resolved by the robe style), 'h' marks the
  weapon hand in the body templates (resolved to S).

Pose names: stand, step_l, pass, step_r (walk 0-3), wind, strike, recover (attack 0-2), hurt.
Directions: down, up, left; right is the mirror of left (weapon hand mirrored too).
Frame geometry (normal build): head box 6x6 at x=5, y=3 (hair rises above it), shoulders at
y=9, sash at y=11, feet at y=14, 1px ink_black outline added last (row 15 / row 1-2 are the
outline rows, so the art never touches the canvas edge except a tall topknot on tall builds).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

try:
    from .pixelkit import Canvas, PALETTE, RAMPS
except ImportError:  # run as a top-level module (build_all.py puts Tools/pixelgen on sys.path)
    from pixelkit import Canvas, PALETTE, RAMPS  # type: ignore

__all__ = [
    "make_character", "make_face", "compose_frame", "resolve_colors", "Grid",
    "BUILDS", "HAIR_STYLES", "HEADWEAR", "BEARDS", "HAIR_ACCESSORIES", "ROBE_STYLES", "WEAPONS",
    "EXPRESSIONS", "EYE_STYLES", "LETTERS", "FRIENDLY_KEYS", "DEFAULT_COLORS", "DEFAULT_SPEC",
    "WALK_POSES", "ATTACK_POSES", "POSES", "DIRS", "FRAME", "FACE_SIZE", "list_parts",
]

FRAME = 16
FACE_SIZE = 32
DIRS = ("down", "up", "left", "right")
TEMPLATE_DIRS = ("down", "up", "left")
WALK_POSES = ("stand", "step_l", "pass", "step_r")
ATTACK_POSES = ("wind", "strike", "recover")
POSES = WALK_POSES + ATTACK_POSES + ("hurt",)
HEAD_X = 5
HEAD_W = 6
HEAD_H = 6

# ------------------------------------------------------------------------------------------
# Letters, defaults and color resolution
# ------------------------------------------------------------------------------------------
# letter -> (friendly key, default palette name)
LETTERS: Dict[str, Tuple[str, str]] = {
    "S": ("skin", "skin"),
    "Z": ("skin_shade", "sand"),
    "E": ("eye", "ink_black"),
    "H": ("hair", "ink_dark"),
    "U": ("hair_light", "ink"),
    "C": ("cloth", "paper"),
    "D": ("cloth_dark", "paper_dark"),
    "L": ("cloth_light", "paper_light"),
    "T": ("trim", "paper_light"),
    "A": ("accent", "sand"),
    "a": ("accent_dark", "earth_light"),
    "P": ("pants", "ink_dark"),
    "F": ("feet", "earth_dark"),
    "K": ("dark", "ink_dark"),
    "B": ("hat", "paper_dark"),
    "N": ("hat_dark", "earth_light"),
    "W": ("weapon", "ink_pale"),
    "M": ("weapon_light", "paper_light"),
    "G": ("hilt", "gold"),
    "O": ("wood", "earth"),
    "V": ("prop", "paper_dark"),
    "J": ("prop_dark", "earth_light"),
    "X": ("extra", "vermilion"),
    "Q": ("extra2", "jade_light"),
}
FRIENDLY_KEYS: Dict[str, str] = {v[0]: k for k, v in LETTERS.items()}
DEFAULT_COLORS: Dict[str, str] = {k: v[1] for k, v in LETTERS.items()}

# (derived letter, source letter, direction): darker = previous ramp entry, lighter = next one
_DERIVED = (("D", "C", -1), ("L", "C", +1), ("Z", "S", -1), ("U", "H", +1), ("N", "B", -1),
            ("a", "A", -1), ("J", "V", -1))


def _ramp_neighbor(name: str, step: int) -> str:
    """The palette name `step` places along the ramp that contains `name` (clamped); the
    name itself when it is in no ramp."""
    for names in RAMPS.values():
        if name in names:
            i = names.index(name)
            j = min(max(i + step, 0), len(names) - 1)
            return names[j]
    return name


def resolve_colors(colors: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Letter -> palette name map for a spec's `colors` (friendly keys or letters), with the
    shade/highlight letters derived from palette.RAMPS when they are not given explicitly."""
    out = dict(DEFAULT_COLORS)
    given: Dict[str, str] = {}
    for key, value in (colors or {}).items():
        letter = FRIENDLY_KEYS.get(key, key)
        if letter not in LETTERS:
            raise KeyError(f"unknown color key {key!r} (letters: {''.join(LETTERS)}; "
                           f"keys: {', '.join(FRIENDLY_KEYS)})")
        if value not in PALETTE:
            raise KeyError(f"color {key!r}={value!r} is not a palette name")
        given[letter] = value
    out.update(given)
    for derived, source, step in _DERIVED:
        if derived not in given and source in given:
            out[derived] = _ramp_neighbor(given[source], step)
    if "T" not in given and "C" in given:
        out["T"] = out["L"] if out["L"] != out["C"] else out["D"]
    return out


# ------------------------------------------------------------------------------------------
# Grid: a letter raster (the kit composes letters, colors are applied at the very end)
# ------------------------------------------------------------------------------------------
class Grid:
    """W x H grid of single characters ('.' = transparent)."""

    def __init__(self, w: int = FRAME, h: int = FRAME):
        self.w, self.h = int(w), int(h)
        self.rows: List[List[str]] = [["."] * self.w for _ in range(self.h)]

    def get(self, x: int, y: int) -> str:
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.rows[y][x]
        return "."

    def set(self, x: int, y: int, ch: str) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.rows[y][x] = ch

    def paste(self, rows: Sequence[str], x: int, y: int, only_over: Optional[str] = None) -> None:
        """Paste ASCII rows at (x, y); '.' and ' ' are skipped. With only_over='.', pixels are
        only written where the grid is still transparent (back layers)."""
        for dy, row in enumerate(rows):
            for dx, ch in enumerate(row):
                if ch in ". ":
                    continue
                px, py = x + dx, y + dy
                if only_over is not None and self.get(px, py) != only_over:
                    continue
                self.set(px, py, ch)

    def replace(self, mapping: Dict[str, str]) -> None:
        for y in range(self.h):
            self.rows[y] = [mapping.get(ch, ch) for ch in self.rows[y]]

    def find(self, ch: str) -> List[Tuple[int, int]]:
        return [(x, y) for y in range(self.h) for x in range(self.w) if self.rows[y][x] == ch]

    def shifted(self, dx: int, dy: int) -> "Grid":
        g = Grid(self.w, self.h)
        for y in range(self.h):
            for x in range(self.w):
                ch = self.rows[y][x]
                if ch != ".":
                    g.set(x + dx, y + dy, ch)
        return g

    def flipped_x(self) -> "Grid":
        g = Grid(self.w, self.h)
        g.rows = [list(reversed(r)) for r in self.rows]
        return g

    def blit(self, other: "Grid", x: int = 0, y: int = 0) -> None:
        self.paste(["".join(r) for r in other.rows], x, y)

    def bbox(self) -> Optional[Tuple[int, int, int, int]]:
        xs = [x for y in range(self.h) for x in range(self.w) if self.rows[y][x] != "."]
        ys = [y for y in range(self.h) for x in range(self.w) if self.rows[y][x] != "."]
        if not xs:
            return None
        return (min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)

    def is_empty(self) -> bool:
        return self.bbox() is None

    def to_rows(self) -> List[str]:
        return ["".join(r) for r in self.rows]

    def to_canvas(self, colors: Dict[str, str]) -> Canvas:
        rows = self.to_rows()
        used = {ch for r in rows for ch in r if ch != "."}
        missing = sorted(ch for ch in used if ch not in colors)
        if missing:
            raise KeyError(f"letters without a color: {missing}")
        return Canvas.from_pattern(rows, {ch: colors[ch] for ch in used})


def _pad(rows: Sequence[str], width: int = FRAME) -> List[str]:
    out = []
    for r in rows:
        if len(r) > width:
            raise ValueError(f"template row wider than {width}: {r!r}")
        out.append(r + "." * (width - len(r)))
    return out


# ------------------------------------------------------------------------------------------
# Builds
# ------------------------------------------------------------------------------------------
# torso_rows: rows between the shoulder row and the sash row; lower_rows: rows below the sash
# (skirt / legs + feet) ending at y = 14; width: -1 narrow (child), 0, +1 wide (burly).
BUILDS: Dict[str, Dict[str, int]] = {
    "child":  {"torso_rows": 0, "lower_rows": 2, "width": -1},
    "normal": {"torso_rows": 1, "lower_rows": 3, "width": 0},
    "tall":   {"torso_rows": 2, "lower_rows": 3, "width": 0},
    "burly":  {"torso_rows": 2, "lower_rows": 3, "width": 1},
}
# columns duplicated (burly) / removed (child) per template direction
_WIDEN_COLS = {"down": (7, 8), "up": (7, 8), "left": (6, 9)}
_NARROW = {"down": ((7, 8), 4), "up": ((7, 8), 4), "left": ((9,), 5)}


def _widen_row(row: str, cols: Tuple[int, int]) -> str:
    c1, c2 = cols
    chars = list(row)
    out = chars[:c1 + 1] + [chars[c1]] + chars[c1 + 1:c2 + 1] + [chars[c2]] + chars[c2 + 1:]
    return "".join(out[1:-1])


def _narrow_row(row: str, cols: Tuple[int, ...], insert_at: int) -> str:
    chars = [ch for i, ch in enumerate(row) if i not in cols]
    chars.insert(insert_at, ".")
    while len(chars) < FRAME:
        chars.append(".")
    return "".join(chars[:FRAME])


# ------------------------------------------------------------------------------------------
# Body templates (normal build). Upper blocks end with the sash row; rows above the shoulder
# row are allowed (raised hands). Lower blocks are the 3 rows below the sash (last row = y 14).
# Letters: C/D/L torso, c sleeve, T collar, S hand, h weapon hand, A/a sash, P legs, F feet.
# "extras": (x, dy from the sash row, letter) pasted before the build transform.
# ------------------------------------------------------------------------------------------
UPPER: Dict[str, Dict[str, Tuple[List[str], List[Tuple[int, int, str]]]]] = {
    "down": {
        "stand": (["....CCTSSTCC....",
                   "....cLCCCCDc....",
                   "....SAAAAAAS...."], []),
        "step_l": (["....CCTSSTCC....",
                    "....cLCCCCDc....",
                    "....SAAAAAAc...."], [(11, 1, "S")]),
        "pass": (["....CCTSSTCC....",
                  "....cLCCCCDc....",
                  "....SAAAAAAS...."], []),
        "step_r": (["....CCTSSTCC....",
                    "....cLCCCCDc....",
                    "....cAAAAAAS...."], [(4, 1, "S")]),
        "wind": (["...h............",
                  "...cCCTSSTCC....",
                  "....cLCCCCDc....",
                  ".....AAAAAAS...."], []),
        "strike": (["....CCTSSTCCS...",
                    "....cLCCCCDc....",
                    "....cAAAAAA....."], [(4, 1, "h")]),
        "recover": (["....CCTSSTCC....",
                     "....cLCCCCDc....",
                     "....hAAAAAAS...."], []),
        "hurt": (["...S........S...",
                  "...cCCTSSTCCc...",
                  "....cLCCCCDc....",
                  ".....AAAAAA....."], []),
    },
    "up": {
        "stand": (["....CCCCCCCC....",
                   "....cLCCCCDc....",
                   "....SAAaaAAS...."], []),
        "step_l": (["....CCCCCCCC....",
                    "....cLCCCCDc....",
                    "....cAAaaAAS...."], [(4, 1, "S")]),
        "pass": (["....CCCCCCCC....",
                  "....cLCCCCDc....",
                  "....SAAaaAAS...."], []),
        "step_r": (["....CCCCCCCC....",
                    "....cLCCCCDc....",
                    "....SAAaaAAc...."], [(11, 1, "S")]),
        "wind": (["............h...",
                  "....CCCCCCCCc...",
                  "....cLCCCCDc....",
                  "....SAAaaAA....."], []),
        "strike": (["............h...",
                    "............c...",
                    "....CCCCCCCCc...",
                    "...c.LCCCCD.....",
                    "...S.AAaaAA....."], []),
        "recover": (["....CCCCCCCC....",
                     "....cLCCCCDc....",
                     "....SAAaaAAh...."], []),
        "hurt": (["...S........S...",
                  "...cCCCCCCCCc...",
                  "....cLCCCCDc....",
                  ".....AAaaAA....."], []),
    },
    "left": {
        "stand": ([".....CCCCCC.....",
                   "......LcCD......",
                   "......ASAA......"], []),
        "step_l": ([".....CCCCCC.....",
                    "......cCCD......",
                    ".....SAAAA......"], []),
        "pass": ([".....CCCCCC.....",
                  "......LcCD......",
                  "......ASAA......"], []),
        "step_r": ([".....CCCCCC.....",
                    "......LCcD......",
                    "......AAAS......"], []),
        "wind": ([".....hCCCCC.....",
                  "......cCCD......",
                  "......AAAA......"], []),
        "strike": ([".....CCCCCC.....",
                    "....hcLCCD......",
                    "......AAAA......"], []),
        "recover": ([".....CCCCCC.....",
                     "......cCCD......",
                     ".....hAAAA......"], []),
        "hurt": (["....S...........",
                  "....cCCCCCC.....",
                  "......LCCD......",
                  "......AAAA......"], []),
    },
}

LOWER: Dict[str, Dict[str, Dict[str, List[str]]]] = {
    "down": {
        "skirt": {
            "stand":   [".....LCCCCD.....", "....LLCCCCDD....", ".....FF..FF....."],
            "step_l":  [".....LCCCCD.....", "....LCCCCCD.....", "....FF...FF....."],
            "pass":    [".....LCCCCD.....", "....LLCCCCDD....", ".....FF..FF....."],
            "step_r":  [".....LCCCCD.....", ".....LCCCCCDD...", ".....FF...FF...."],
            "wind":    [".....LCCCCD.....", "....LLCCCCDD....", ".....FF..FF....."],
            "strike":  [".....LCCCCD.....", "....LLCCCCDD....", "....FF....FF...."],
            "recover": [".....LCCCCD.....", "....LLCCCCDD....", ".....FF..FF....."],
            "hurt":    [".....LCCCCD.....", "....LLCCCCDD....", ".....FF..FF....."],
        },
        "legs": {
            "stand":   [".....LCCCCD.....", ".....PP..PP.....", ".....FF..FF....."],
            "step_l":  [".....LCCCCD.....", "....PP...PP.....", "....FF.........."],
            "pass":    [".....LCCCCD.....", ".....PP..PP.....", ".....FF..FF....."],
            "step_r":  [".....LCCCCD.....", ".....PP...PP....", "..........FF...."],
            "wind":    [".....LCCCCD.....", ".....PP..PP.....", ".....FF..FF....."],
            "strike":  [".....LCCCCD.....", "....PP....PP....", "....FF....FF...."],
            "recover": [".....LCCCCD.....", ".....PP..PP.....", ".....FF..FF....."],
            "hurt":    [".....LCCCCD.....", ".....PP..PP.....", ".....FF..FF....."],
        },
    },
    "left": {
        "skirt": {
            "stand":   ["......LCCD......", "......LCCDD.....", ".....FFF........"],
            "step_l":  ["......LCCD......", ".....LCCCDD.....", "....FF...FF....."],
            "pass":    ["......LCCD......", "......LCCDD.....", "......FFF......."],
            "step_r":  ["......LCCD......", ".....LCCCDD.....", ".....FF..FF....."],
            "wind":    ["......LCCD......", "......LCCDD.....", ".....FFF........"],
            "strike":  ["......LCCD......", ".....LCCCDD.....", "....FF...FF....."],
            "recover": ["......LCCD......", "......LCCDD.....", ".....FFF........"],
            "hurt":    ["......LCCD......", "......LCCDD.....", "......FFF......."],
        },
        "legs": {
            "stand":   ["......LCCD......", ".......PP.......", "......FFF......."],
            "step_l":  ["......LCCD......", ".....PP..P......", "....FF...FF....."],
            "pass":    ["......LCCD......", ".......PP.......", "......FFF......."],
            "step_r":  ["......LCCD......", "......P..PP.....", ".....FF..FF....."],
            "wind":    ["......LCCD......", ".......PP.......", "......FFF......."],
            "strike":  ["......LCCD......", ".....PP..P......", "....FF...FF....."],
            "recover": ["......LCCD......", ".......PP.......", "......FFF......."],
            "hurt":    ["......LCCD......", ".......PP.......", "......FFF......."],
        },
    },
}
LOWER["up"] = LOWER["down"]  # the back of the robe / the legs look the same from behind

# head shift (dx, dy) and body shift (dx, dy) per direction and pose
POSE_SHIFT: Dict[str, Dict[str, Tuple[int, int, int, int]]] = {
    "down": {"stand": (0, 0, 0, 0), "step_l": (0, 1, 0, 0), "pass": (0, 0, 0, 0), "step_r": (0, 1, 0, 0),
             "wind": (0, 0, 0, 0), "strike": (0, 1, 0, 0), "recover": (0, 0, 0, 0), "hurt": (0, -1, 0, 0)},
    "up":   {"stand": (0, 0, 0, 0), "step_l": (0, 1, 0, 0), "pass": (0, 0, 0, 0), "step_r": (0, 1, 0, 0),
             "wind": (0, 0, 0, 0), "strike": (0, 0, 0, 0), "recover": (0, 0, 0, 0), "hurt": (0, 1, 0, 0)},
    "left": {"stand": (0, 0, 0, 0), "step_l": (0, 1, 0, 0), "pass": (0, 0, 0, 0), "step_r": (0, 1, 0, 0),
             "wind": (1, 0, 0, 0), "strike": (-1, 0, 0, 0), "recover": (0, 0, 0, 0), "hurt": (1, 0, 1, 0)},
}

# ------------------------------------------------------------------------------------------
# Head box (6x6, skin base; hair/headwear overlays go on top) and the nose for side views
# ------------------------------------------------------------------------------------------
HEAD_BOX: Dict[str, List[str]] = {
    "down": [".SSSS.", "SSSSSS", "SSSSSS", "SESSES", "SSSSSS", ".SSSS."],
    "up":   [".SSSS.", "SSSSSS", "SSSSSS", "SSSSSS", "SSSSSS", ".SSSS."],
    "left": [".SSSS.", "SSSSSS", "SSSSSS", "SESSSS", "SSSSSS", ".SSSS."],
}
HEAD_EXTRA: Dict[str, List[Tuple[int, int, str]]] = {   # (dx, dy, letter) relative to the box
    "down": [],
    "up": [],
    "left": [(-1, 4, "S")],                              # nose
}

# ------------------------------------------------------------------------------------------
# Hair styles: per direction (rows, ox, oy) relative to the head box top-left
# ------------------------------------------------------------------------------------------
_SHORT_DOWN = ([".HHHHHH.", "HUHHHHHH", "HH....HH", "H......H"], -1, 0)
_SHORT_UP = ([".HHHHHH.", "HUHHHHHH", "HHHHHHHH", "HHHHHHHH", ".HHHHHH."], -1, 0)
_SHORT_LEFT = ([".HHHHHH.", ".HUHHHHH", "....HHHH", ".....HHH", ".....HH."], -1, 0)

HAIR_STYLES: Dict[str, Dict[str, Tuple[List[str], int, int]]] = {
    "bald": {"down": ([], 0, 0), "up": ([], 0, 0), "left": ([], 0, 0)},
    "short": {"down": _SHORT_DOWN, "up": _SHORT_UP, "left": _SHORT_LEFT},
    "topknot": {
        "down": (["...HH...", "..HHHH..", ".HHHHHH.", "HUHHHHHH", "HH....HH", "H......H"], -1, -2),
        "up":   (["...HH...", "..HHHH..", ".HHHHHH.", "HUHHHHHH", "HHHHHHHH", "HHHHHHHH", ".HHHHHH."], -1, -2),
        "left": (["....HH..", "...HHHH.", ".HHHHHH.", ".HUHHHHH", "....HHHH", ".....HHH", ".....HH."], -1, -2),
    },
    "topknot_pin": {
        "down": (["...HH...", "GGHHHH..", ".HHHHHH.", "HUHHHHHH", "HH....HH", "H......H"], -1, -2),
        "up":   (["...HH...", "..HHHHGG", ".HHHHHH.", "HUHHHHHH", "HHHHHHHH", "HHHHHHHH", ".HHHHHH."], -1, -2),
        "left": (["....HH..", "...HHHHG", ".HHHHHH.", ".HUHHHHH", "....HHHH", ".....HHH", ".....HH."], -1, -2),
    },
    "bun": {
        "down": (["..HHHH..", ".HHHHHH.", "HUHHHHHH", "HH....HH", "H......H"], -1, -1),
        "up":   (["..HHHH..", ".HHHHHH.", "HUHHHHHH", "HHHHHHHH", "HHHHHHHH", ".HHHHHH."], -1, -1),
        "left": ([".HHHHHH..", ".HUHHHHHH", "....HHHHH", ".....HHH.", ".....HH.."], -1, 0),
    },
    "bun_pin": {
        "down": ([".GHHHHG.", ".HHHHHH.", "HUHHHHHH", "HH....HH", "H......H"], -1, -1),
        "up":   ([".GHHHHG.", ".HHHHHH.", "HUHHHHHH", "HHHHHHHH", "HHHHHHHH", ".HHHHHH."], -1, -1),
        "left": ([".HHHHHHG.", ".HUHHHHHH", "....HHHHH", ".....HHH.", ".....HH.."], -1, 0),
    },
    "ponytail_high": {
        "down": (["...HH...", ".HHHHHH.", "HUHHHHHH", "HH....HH", "H......H", ".......H", ".......H"], -1, -1),
        "up":   (["...HH...", ".HHAAHH.", "HUHHHHHH", "HHHUUHHH", "HHHUUHHH", ".HHUUHH.", "..HUUH..", "...UU...", "...HH...", "....H..."], -1, -1),
        "left": (["....HHA..", ".HHHHHHH.", ".HUHHHHH.", "....HHHHH", ".....HHHH", "......HHU", "........H", "........H"], -1, -1),
    },
    "ponytail": {
        "down": ([".HHHHHH.", "HUHHHHHH", "HH....HH", "H......H", ".......H", ".......H", ".......H"], -1, 0),
        "up":   ([".HHHHHH.", "HUHHHHHH", "HHHHHHHH", "HHHHHHHH", ".HHHHHH.", "..HHHH..", "...AA...", "...HH...", "...HH...", "....H..."], -1, 0),
        "left": ([".HHHHHH..", ".HUHHHHH.", "....HHHHA", ".....HHHH", ".....HH.H", "........H", "........U", "........H"], -1, 0),
    },
    "braid": {
        "down": ([".HHHHHH.", "HUHHHHHH", "HH....HH", "H......H", ".......H", ".......U", ".......H", ".......X"], -1, 0),
        "up":   ([".HHHHHH.", "HUHHHHHH", "HHHHHHHH", "HHHHHHHH", ".HHHHHH.", "..HHHH..", "....H...", "....U...", "....H...", "....U...", "....X..."], -1, 0),
        "left": ([".HHHHHH..", ".HUHHHHH.", "....HHHHH", ".....HHHH", ".....HH.U", "........H", "........U", "........X"], -1, 0),
    },
    "loose_long": {
        "down": ([".HHHHHH.", "HUHHHHHH", "HH....HH", "H......H", "H......H", "H......H", "H......H"], -1, 0),
        "up":   ([".HHHHHH.", "HUHHHHHH", "HHHHHHHH", "HHHHHHHH", "HHHHHHHH", "HHHHHHHH", "HHHHHHHH", ".HHHHHH.", "..HHHH..", "...HH..."], -1, 0),
        "left": ([".HHHHHH..", ".HUHHHHH.", "...HHHHHH", "....HHHHH", "....HHHHH", ".....HHHH", ".....HHHH", "......HHH", "......HH."], -1, 0),
    },
}

# ------------------------------------------------------------------------------------------
# Headwear: per direction (rows, ox, oy) relative to the head box top-left; drawn over hair
# ------------------------------------------------------------------------------------------
_STRAW = (["....BB....", "..BBBBBB..", "BBBBBBBBBB"], -2, -2)
HEADWEAR: Dict[str, Dict[str, Tuple[List[str], int, int]]] = {
    "none": {"down": ([], 0, 0), "up": ([], 0, 0), "left": ([], 0, 0)},
    "straw_hat": {"down": _STRAW, "up": _STRAW, "left": _STRAW},
    "scholar_hat": {
        "down": (["..BBBB..", ".BBBBBB.", ".BBBBBB.", "BB....BB"], -1, -2),
        "up":   (["..BBBB..", ".BBBBBB.", ".BBBBBB.", "BBBBBBBB"], -1, -2),
        "left": (["...BBBB.", "..BBBBB.", ".BBBBBB.", "......BB"], -1, -2),
    },
    "headband": {
        "down": (["XXXXXXXX"], -1, 2),
        "up":   (["XXXXXXXX", "...X.X.."], -1, 2),
        "left": (["XXXXXXXXX", "........X"], -1, 2),
    },
    "hood": {
        "down": (["..BBBB..", ".BBBBBB.", "BBBBBBBB", "BB....BB", "B......B", "B......B", "BB....BB"], -1, -1),
        "up":   (["..BBBB..", ".BBBBBB.", "BBBBBBBB", "BBBBBBBB", "BBBBBBBB", "BBBBBBBB", "BBBBBBBB", "BBBBBBBB"], -1, -1),
        "left": (["..BBBBB.", ".BBBBBBB", ".BBBBBBB", "B..BBBBB", "....BBBB", "....BBBB", "....BBBB"], -1, -1),
    },
    "cap": {
        "down": (["..BBBB..", ".BBBBBB.", "BNBBBBNB"], -1, -1),
        "up":   (["..BBBB..", ".BBBBBB.", "BBBBBBBB"], -1, -1),
        "left": (["..BBBB..", ".BBBBBBB", ".NN.BBBB"], -1, -1),
    },
    "headscarf": {
        "down": ([".BBBBBB.", "BBBBBBBB", "B......B"], -1, 0),
        "up":   ([".BBBBBB.", "BBBBBBBB", "BBBBBBBB", "..BB.B..", "....B..."], -1, 0),
        "left": ([".BBBBBB.", "BBBBBBBB", "....BBBB", ".....BBB", "......BB", ".......B"], -1, 0),
    },
    "helmet": {   # 관병 iron cap: metal letters W/M with a dark rim K
        "down": (["...M....", "..WWWW..", ".WMWWWW.", "KWWWWWWK"], -1, -2),
        "up":   (["...M....", "..WWWW..", ".WMWWWW.", "KWWWWWWK"], -1, -2),
        "left": (["....M...", "..WWWW..", ".WMWWWW.", ".KKKKKKK"], -1, -2),
    },
}

# carried props shown in walk / idle / hurt frames at the off hand: (rows, dx, dy) from the
# off-hand anchor of each direction (down: right hand x 11, up: x 4, left: the near hand x 7)
CARRY: Dict[str, Dict[str, Tuple[List[str], int, int]]] = {
    "none": {"down": ([], 0, 0), "up": ([], 0, 0), "left": ([], 0, 0)},
    "basket": {"down": (["VV", "JJ"], 0, 1), "up": (["VV", "JJ"], -1, 1), "left": (["VV", "JJ"], -2, 1)},
    "bolt": {"down": (["XXX", "QXX"], 0, -1), "up": (["XXX", "XXQ"], -2, -1), "left": (["XXX", "QXX"], -2, -1)},
    "scroll": {"down": (["M", "M", "M"], 1, -1), "up": (["M", "M", "M"], -1, -1), "left": (["M", "M", "M"], -1, -1)},
    "abacus": {"down": (["OOO", "OKO"], 0, 0), "up": (["OOO", "OKO"], -2, 0), "left": (["OOO", "OKO"], -2, 0)},
    "gourd": {"down": (["J", "V", "V"], 1, 0), "up": (["J", "V", "V"], -1, 0), "left": (["J", "V", "V"], -1, 0)},
    "towel": {"down": (["T", "T", "T"], -1, -3), "up": (["T", "T", "T"], 1, -3), "left": (["T", "T", "T"], 1, -3)},
    "keys": {"down": (["G", "GG"], 1, 0), "up": (["G", "GG"], -2, 0), "left": (["G", "GG"], -1, 0)},
}
_OFF_HAND = {"down": 11, "up": 4, "left": 7}
COLLARS = ("none", "fur")

BEARDS: Dict[str, Dict[str, Tuple[List[str], int, int]]] = {
    "none": {"down": ([], 0, 0), "up": ([], 0, 0), "left": ([], 0, 0)},
    "short": {"down": ([".HHHHHH."], -1, 5), "up": ([], 0, 0), "left": ([".HHHHH.."], -1, 5)},
    "long": {"down": ([".HHHHHH.", "..HHHH..", "...HH..."], -1, 5), "up": ([], 0, 0),
             "left": ([".HHHHH..", "..HHH...", "..HH...."], -1, 5)},
    "goatee": {"down": (["...HH...", "...HH..."], -1, 5), "up": ([], 0, 0), "left": ([".HH.....", ".HH....."], -1, 5)},
    "mustache": {"down": ([], 0, 0), "up": ([], 0, 0), "left": ([], 0, 0)},   # face only
}

HAIR_ACCESSORIES: Dict[str, Dict[str, Tuple[List[str], int, int]]] = {
    "none": {"down": ([], 0, 0), "up": ([], 0, 0), "left": ([], 0, 0)},
    "ribbon": {
        "down": (["......XX", ".......X"], -1, 0),
        "up":   (["...XX...", "..X..X.."], -1, 1),
        "left": (["......XX", ".......X"], -1, 1),
    },
}

# ------------------------------------------------------------------------------------------
# Robe styles
# ------------------------------------------------------------------------------------------
ROBE_STYLES: Dict[str, Dict[str, object]] = {
    "long_robe":      {"sleeve": "C", "collar": "T", "lower": "skirt"},
    "robe_sash":      {"sleeve": "C", "collar": "T", "lower": "skirt", "sash_tail": True},
    "short_tunic":    {"sleeve": "C", "collar": "T", "lower": "legs"},
    "vest_bare_arms": {"sleeve": "S", "collar": "S", "lower": "legs", "vest": True},
    "armor_lamellar": {"sleeve": "C", "collar": "D", "lower": "legs", "texture": "lamellar"},
    "dress":          {"sleeve": "C", "collar": "T", "lower": "skirt", "hem": "trim"},
    "apron_dress":    {"sleeve": "C", "collar": "T", "lower": "skirt", "hem": "trim", "apron": True},
    "ragged":         {"sleeve": "C", "collar": "C", "lower": "skirt", "hem": "ragged", "texture": "patches"},
}

# ------------------------------------------------------------------------------------------
# Weapons: drawn from the weapon-hand anchor along a direction vector per (dir, phase)
# ------------------------------------------------------------------------------------------
WEAPON_VECTORS: Dict[str, Dict[str, Tuple[int, int]]] = {
    "down": {"wind": (0, -1), "strike": (1, 0), "recover": (-1, 1)},
    "up":   {"wind": (0, -1), "strike": (0, -1), "recover": (1, 1)},
    "left": {"wind": (-1, -1), "strike": (-1, 0), "recover": (-1, 1)},
}
BLADES = {"jian": 5, "dao": 5, "dagger": 3, "cleaver": 3}
POLES = {"staff": (3, 6), "spear": (3, 6), "pole": (4, 7), "broom": (3, 5)}
WEAPONS = ("none", "palm", "jian", "dao", "dagger", "staff", "spear", "fan", "needle_throw",
           "sling", "cleaver", "broom", "pole", "basket")


def _perp(v: Tuple[int, int]) -> Tuple[int, int]:
    return (-v[1], v[0])


def _weapon_pixels(kind: str, phase: str, d: str, hand: Tuple[int, int]) -> List[Tuple[int, int, str]]:
    """Letter pixels of `kind` for attack phase `phase` seen from template direction `d`,
    relative to nothing (absolute frame coordinates), the weapon hand being at `hand`."""
    hx, hy = hand
    vx, vy = WEAPON_VECTORS[d][phase]
    px, py = _perp((vx, vy))
    if d == "down" and phase == "strike":
        px, py = (0, 1)
    out: List[Tuple[int, int, str]] = []

    def at(k: int, side: int = 0, ch: str = "W") -> None:
        out.append((hx + k * vx + side * px, hy + k * vy + side * py, ch))

    if kind in BLADES:
        L = BLADES[kind]
        if kind == "cleaver":
            at(1, 0, "O")
            for k in (2, 3):
                at(k, 0, "W")
                at(k, 1, "M")
            at(4, 0, "M")
            at(4, 1, "W")
            return out
        at(1, 0, "G")
        for k in range(2, L):
            at(k, 0, "W")
        if kind == "dao":
            at(L, 0, "W")
            at(L + 1, 1, "M")
            at(L, 1, "W")
        else:
            at(L, 0, "M")
        if kind == "jian" and phase != "recover":
            at(1, 1, "G")
            at(1, -1, "G")
        return out
    if kind in POLES:
        back, fwd = POLES[kind]
        for k in range(-back, fwd + 1):
            if k == 0:
                continue
            at(k, 0, "O")
        if kind == "staff":
            at(-back, 0, "M")
            at(fwd, 0, "M")
        elif kind == "spear":
            at(fwd, 0, "W")
            at(fwd + 1, 0, "M")
            at(fwd - 1, 1, "X")
        elif kind == "broom":
            for k in (fwd, fwd + 1):
                at(k, 0, "V")
                at(k, 1, "V")
                at(k, -1, "J")
        return out
    if kind == "fan":
        if phase == "strike":
            at(1, 0, "O")
            at(2, 0, "J")
            at(2, 1, "V")
            at(2, -1, "V")
            at(3, 0, "V")
            at(3, 1, "J")
            at(3, -1, "J")
            at(3, 2, "V")
            at(3, -2, "V")
            at(4, 0, "V")
            at(4, 1, "V")
            at(4, -1, "V")
        else:
            at(1, 0, "O")
            at(2, 0, "V")
            at(3, 0, "V")
        return out
    if kind == "needle_throw":
        if phase == "wind":
            at(1, 0, "M")
        elif phase == "strike":
            at(2, 0, "M")
            at(3, 0, "M")
            at(3, 1, "M")
            at(4, 1, "M")
            at(5, -1, "M")
            at(6, -1, "M")
        return out
    if kind == "sling":
        if phase == "wind":
            at(1, 0, "J")
            at(2, 1, "J")
            at(2, -1, "J")
            at(3, 0, "K")
        elif phase == "strike":
            at(1, 0, "J")
            at(2, 0, "J")
            at(4, 0, "K")
            at(5, 0, "K")
            at(3, 1, "M")
        else:
            at(1, 0, "J")
            at(2, 0, "J")
        return out
    if kind == "basket":
        at(1, 0, "O")
        for k in (2, 3):
            at(k, 0, "V")
            at(k, 1, "V")
            at(k, -1, "J")
        at(4, 0, "V")
        at(4, 1, "J")
        return out
    if kind in ("none", "palm"):
        if phase == "strike":
            at(2, 1, "Q")
            at(2, -1, "Q")
            at(3, 0, "Q")
        return out
    raise KeyError(f"unknown weapon {kind!r}; known: {', '.join(WEAPONS)}")


# hilt + scabbard shown at the hip in walk frames (hip_weapon=True), relative to the sash row y
_HIP_WEAPON = {
    "down": [(3, 0, "G"), (3, 1, "K"), (3, 2, "K")],
    "up":   [(12, 0, "G"), (12, 1, "K"), (12, 2, "K")],
    "left": [(10, -1, "G"), (10, 0, "K"), (11, 1, "K")],
}

# ------------------------------------------------------------------------------------------
# Spec handling
# ------------------------------------------------------------------------------------------
DEFAULT_SPEC: Dict[str, object] = {
    "build": "normal", "hair": "short", "headwear": "none", "beard": "none",
    "hair_accessory": "none", "robe": "long_robe", "weapon": "none", "hip_weapon": False,
    "carry": "none", "collar": "none", "scar": False,
    "expression": "neutral", "eyes": "normal", "colors": {}, "extras": [], "face_extras": [],
}


def _norm_spec(spec: Dict[str, object]) -> Dict[str, object]:
    s = dict(DEFAULT_SPEC)
    s.update(spec or {})
    checks = (("build", BUILDS), ("hair", HAIR_STYLES), ("headwear", HEADWEAR), ("beard", BEARDS),
              ("hair_accessory", HAIR_ACCESSORIES), ("robe", ROBE_STYLES), ("expression", EXPRESSIONS),
              ("eyes", EYE_STYLES), ("carry", CARRY), ("collar", {c: c for c in COLLARS}))
    for key, table in checks:
        if s[key] not in table:
            raise KeyError(f"spec {key}={s[key]!r} unknown; choose one of {', '.join(table)}")
    if s["weapon"] not in WEAPONS:
        raise KeyError(f"spec weapon={s['weapon']!r} unknown; choose one of {', '.join(WEAPONS)}")
    s["_colors"] = resolve_colors(s.get("colors"))  # type: ignore[arg-type]
    return s


def _extras_for(spec: Dict[str, object], d: str, pose: str, layer: str) -> List[dict]:
    out = []
    for ex in spec.get("extras", []) or []:
        dirs = ex.get("dirs", ["*"])
        poses = ex.get("poses", ["*"])
        if ("*" not in dirs and d not in dirs) or ("*" not in poses and pose not in poses):
            continue
        if ex.get("layer", "front") != layer:
            continue
        out.append(ex)
    return out


# ------------------------------------------------------------------------------------------
# Frame composition
# ------------------------------------------------------------------------------------------
def _body_rows(spec: Dict[str, object], d: str, pose: str) -> Tuple[List[str], int]:
    """Full-height (16) rows of the body for template direction `d`, and the sash row y."""
    build = BUILDS[spec["build"]]  # type: ignore[index]
    robe = ROBE_STYLES[spec["robe"]]  # type: ignore[index]
    upper, extras = UPPER[d][pose]
    upper = _pad(upper)
    lower = _pad(LOWER[d][str(robe["lower"])][pose])
    rows = upper + lower
    sash_i = len(upper) - 1
    # pose extras (hands reaching into the lower block etc.)
    g = Grid(FRAME, len(rows))
    g.paste(rows, 0, 0)
    for (x, dy, ch) in extras:
        g.set(x, sash_i + dy, ch)
    rows = g.to_rows()
    # build: torso rows
    torso_i = sash_i - 1
    torso_rows = int(build["torso_rows"])
    if torso_rows == 0:
        del rows[torso_i]
        sash_i -= 1
    else:
        for _ in range(torso_rows - 1):
            rows.insert(torso_i, rows[torso_i])
            sash_i += 1
    # build: lower rows
    lower_rows = int(build["lower_rows"])
    if lower_rows == 2:
        del rows[sash_i + 2]
    # build: width
    width = int(build["width"])
    if width > 0:
        rows = [_widen_row(r, _WIDEN_COLS[d]) for r in rows]
    elif width < 0:
        cols, ins = _NARROW[d]
        rows = [_narrow_row(r, cols, ins) for r in rows]
    # vertical placement: the last row sits at y = 14
    top = FRAME - 1 - len(rows)
    full = ["." * FRAME] * (top + 0) + rows
    full = full + ["." * FRAME] * (FRAME - len(full))
    return full, top + sash_i


def _apply_robe(g: Grid, spec: Dict[str, object], d: str, sash_y: int, shoulder_y: int) -> None:
    robe = ROBE_STYLES[spec["robe"]]  # type: ignore[index]
    texture = robe.get("texture")
    if texture == "lamellar":
        for y in range(shoulder_y, sash_y):
            for x in range(FRAME):
                if g.get(x, y) in ("C", "L", "D"):
                    g.set(x, y, "L" if (x + y) % 2 == 0 else "D")
    elif texture == "patches":
        for (x, y) in ((6, sash_y + 1), (9, shoulder_y + 1), (8, sash_y + 2)):
            if g.get(x, y) in ("C", "L", "D"):
                g.set(x, y, "K")
    hem = robe.get("hem")
    if hem == "ragged":
        y = FRAME - 2
        for x in range(FRAME):
            if g.get(x, y) in ("C", "L", "D") and x % 3 == 1:
                g.set(x, y, ".")
    elif hem == "trim":
        y = FRAME - 2
        for x in range(FRAME):
            if g.get(x, y) in ("C", "L", "D"):
                g.set(x, y, "T")
    if robe.get("sash_tail"):
        tails = {"down": [(9, sash_y + 1, "A"), (9, sash_y + 2, "a")],
                 "up": [(7, sash_y + 1, "A"), (8, sash_y + 1, "A"), (7, sash_y + 2, "a"), (8, sash_y + 2, "a")],
                 "left": [(9, sash_y + 1, "A"), (10, sash_y + 2, "a")]}[d]
        for (x, y, ch) in tails:
            if g.get(x, y) != ".":
                g.set(x, y, ch)
    if robe.get("vest"):
        # open vest: a strip of skin down the chest front (down view only)
        if d == "down":
            for y in range(shoulder_y + 1, sash_y):
                for x in (7, 8):
                    if g.get(x, y) in ("C", "L", "D"):
                        g.set(x, y, "S")
    if robe.get("apron") and d != "up":
        xs = (6, 7, 8, 9) if d == "down" else (6, 7)
        for y in range(sash_y + 1, FRAME - 1):
            for x in xs:
                if g.get(x, y) in ("C", "L", "D"):
                    g.set(x, y, "T")
    if spec.get("collar", "none") == "fur":
        for x in range(FRAME):
            if g.get(x, shoulder_y) in ("C", "L", "D", "T", "c"):
                g.set(x, shoulder_y, "V" if x % 2 == 0 else "J")
    sleeve = str(robe["sleeve"])
    if d == "left" and sleeve == "C":
        sleeve = "D"            # the near arm lies in front of the torso: shade it so it reads
    g.replace({"c": sleeve, "T": str(robe["collar"])})


def _paste_part(g: Grid, part: Tuple[List[str], int, int], hx: int, hy: int) -> None:
    """Paste a head part; rows that would land above y = 1 are dropped so the outline is
    never clipped at the top edge (tall builds + topknot / straw hat)."""
    rows, ox, oy = part
    rows = list(rows)
    y = hy + oy
    while rows and y < 1:
        rows.pop(0)
        y += 1
    rows = rows[:max(0, FRAME - 1 - y)]          # and never below y = 14 (long tails on children)
    if rows:
        g.paste(rows, hx + ox, y)


def compose_frame(spec: Dict[str, object], d: str, pose: str, outline: bool = True) -> Canvas:
    """One 16x16 frame (outlined) of `spec` facing `d` (down/up/left/right) in `pose`."""
    s = _norm_spec(spec) if "_colors" not in spec else spec
    if d == "right":
        g = _compose_grid(s, "left", pose).flipped_x()
    else:
        g = _compose_grid(s, d, pose)
    c = g.to_canvas(s["_colors"])  # type: ignore[arg-type]
    return c.outlined("ink_black") if outline else c


def _compose_grid(s: Dict[str, object], d: str, pose: str) -> Grid:
    build = BUILDS[s["build"]]  # type: ignore[index]
    hdx, hdy, bdx, bdy = POSE_SHIFT[d][pose]
    rows, sash_y = _body_rows(s, d, pose)
    shoulder_y = sash_y - int(build["torso_rows"]) - 1
    head_y = shoulder_y - HEAD_H
    body = Grid()
    body.paste(rows, 0, 0)
    # weapon hand anchor
    hands = body.find("h")
    hand = hands[0] if hands else None
    body.replace({"h": "S"})
    _apply_robe(body, s, d, sash_y, shoulder_y)
    if hand is not None:
        hand = (hand[0] + bdx, hand[1] + bdy)
    g = Grid()
    # back layer extras (under the body)
    for ex in _extras_for(s, d, pose, "back"):
        ax, ay = int(ex["x"]), int(ex["y"])
        if ex.get("anchor", "body") == "head":
            ax, ay = ax + hdx, ay + hdy
        g.paste(ex["rows"], ax + bdx, ay + bdy)
    g.blit(body.shifted(bdx, bdy))
    # hip weapon / carried prop in walk frames
    weapon = str(s["weapon"])
    width = int(build["width"])
    if s.get("hip_weapon") and pose in WALK_POSES and weapon in BLADES:
        wx = {"down": -width, "up": width, "left": max(width, 0)}[d]
        for (x, dy, ch) in _HIP_WEAPON[d]:
            g.set(x + wx + bdx, sash_y + dy + bdy, ch)
    carry = str(s.get("carry", "none"))
    if carry != "none" and pose in WALK_POSES + ("hurt",):
        rows, dx, dy = CARRY[carry][d]
        ox = _OFF_HAND[d] + (1 if BUILDS[str(s["build"])]["width"] > 0 and d != "left" else 0)
        if d == "up" and BUILDS[str(s["build"])]["width"] > 0:
            ox -= 2
        g.paste(rows, ox + dx + bdx, sash_y + dy + bdy)
    # head: box, nose, hair, beard, headwear, accessory
    hx, hy = HEAD_X + hdx + bdx, head_y + hdy + bdy
    head = Grid()
    head.paste(HEAD_BOX[d], hx, hy)
    for (dx, dy, ch) in HEAD_EXTRA[d]:
        head.set(hx + dx, hy + dy, ch)
    _paste_part(head, HAIR_STYLES[str(s["hair"])][d], hx, hy)
    _paste_part(head, BEARDS[str(s["beard"])][d], hx, hy)
    _paste_part(head, HEADWEAR[str(s["headwear"])][d], hx, hy)
    _paste_part(head, HAIR_ACCESSORIES[str(s["hair_accessory"])][d], hx, hy)
    if s.get("scar") and d != "up":
        if d == "down":
            for (dx, dy) in ((4, 2), (4, 4)):
                if head.get(hx + dx, hy + dy) == "S":
                    head.set(hx + dx, hy + dy, "K")
        else:
            for (dx, dy) in ((0, 2), (0, 4)):
                if head.get(hx + dx, hy + dy) == "S":
                    head.set(hx + dx, hy + dy, "K")
    if pose == "hurt" and d != "up":
        for (ex_, ey_) in head.find("E"):
            head.set(ex_, ey_, "K")
            side = -1 if ex_ < hx + HEAD_W // 2 else 1
            if head.get(ex_ + side, ey_) == "S":
                head.set(ex_ + side, ey_, "K")
    # neck fill when the head is lifted off the shoulders
    if hdy < 0:
        for x in (hx + 2, hx + 3):
            if g.get(x, hy + HEAD_H) == ".":
                g.set(x, hy + HEAD_H, "S")
    g.blit(head)
    # weapon
    if pose in ATTACK_POSES and hand is not None:
        for (x, y, ch) in _weapon_pixels(weapon, pose, d, hand):
            if 1 <= x <= FRAME - 2 and 1 <= y <= FRAME - 2:
                g.set(x, y, ch)
    # front extras
    for ex in _extras_for(s, d, pose, "front"):
        ax, ay = int(ex["x"]), int(ex["y"])
        if ex.get("anchor", "body") == "head":
            ax, ay = ax + hdx, ay + hdy
        g.paste(ex["rows"], ax + bdx, ay + bdy)
    return g


def make_character(spec: Dict[str, object], face: bool = True):
    """(walk, attack, hurt, face) for `pixelkit.character_sheet`: walk {dir: [4 Canvas]},
    attack {dir: [3 Canvas]}, hurt {dir: Canvas}, face Canvas 32x32 (None when face=False)."""
    s = _norm_spec(spec)
    walk = {d: [compose_frame(s, d, p) for p in WALK_POSES] for d in DIRS}
    attack = {d: [compose_frame(s, d, p) for p in ATTACK_POSES] for d in DIRS}
    hurt = {d: compose_frame(s, d, "hurt") for d in DIRS}
    f = make_face(s) if face else None
    return walk, attack, hurt, f


# ------------------------------------------------------------------------------------------
# Face (32x32 bust)
# ------------------------------------------------------------------------------------------
def _f(rows: Dict[int, str]) -> List[Tuple[int, str]]:
    return sorted(rows.items())


_FACE_HEAD = {
    5:  "...........SSSSSSSSSS...........",
    6:  ".........SSSSSSSSSSSSSS.........",
    7:  "........SSSSSSSSSSSSSSSS........",
    8:  "........SSSSSSSSSSSSSSSS........",
    9:  "........SSSSSSSSSSSSSSSS........",
    10: "........SSSSSSSSSSSSSSSS........",
    11: "........SSSSSSSSSSSSSSSS........",
    12: "........SSSSSSSSSSSSSSSS........",
    13: "........SSSSSSSSSSSSSSSS........",
    14: "........SSSSSSSSSSSSSSSS........",
    15: "........SSSSSSSSSSSSSSSS........",
    16: "........SSSSSSSSSSSSSSSS........",
    17: ".........SSSSSSSSSSSSSS.........",
    18: "..........SSSSSSSSSSSS..........",
    19: "............SSSSSSSS............",
    20: ".............ZZZZZZ.............",
    21: ".............SSSSSS.............",
}
_FACE_HEAD_BURLY = {
    17: "........SSSSSSSSSSSSSSSS........",
    18: ".........SSSSSSSSSSSSSS.........",
    19: "..........SSSSSSSSSSSS..........",
    20: "............ZZZZZZZZ............",
    21: "............SSSSSSSS............",
}
_FACE_BUST = {
    22: "..........CCCSSSSSSCCC..........",
    23: "........CCCCCTSSSSTCCCCC........",
    24: "......ccCCCCCCTSSTCCCCCCcc......",
    25: ".....cccCCCCCCCTTCCCCCCCccc.....",
    26: "....ccccCCCCCCCCCCCCCCCCcccc....",
    27: "...cccccCCCCCCCCCCCCCCCCccccc...",
    28: "...cccccCCCCCCCCCCCCCCCCccccc...",
    29: "...cccccCCCCCCCCCCCCCCCCccccc...",
    30: "...cccccCCCCCCCCCCCCCCCCccccc...",
}
_FACE_BUST_BURLY = {
    22: "........CCCCCSSSSSSSSCCCCC......",
    23: "......CCCCCCCTSSSSSSTCCCCCCC....",
    24: "....ccCCCCCCCCTSSSSTCCCCCCCCcc..",
    25: "...cccCCCCCCCCCTSSTCCCCCCCCccc..",
    26: "..ccccCCCCCCCCCCTTCCCCCCCCCcccc.",
    27: "..cccccCCCCCCCCCCCCCCCCCCccccc..",
    28: "..cccccCCCCCCCCCCCCCCCCCCccccc..",
    29: "..cccccCCCCCCCCCCCCCCCCCCccccc..",
    30: "..cccccCCCCCCCCCCCCCCCCCCccccc..",
}
_FACE_BUST_CHILD = {
    22: "...........CCCSSSSCCC...........",
    23: ".........CCCCCTSSTCCCCC.........",
    24: ".......ccCCCCCCTTCCCCCCcc.......",
    25: "......cccCCCCCCCCCCCCCCccc......",
    26: ".....ccccCCCCCCCCCCCCCCcccc.....",
    27: ".....ccccCCCCCCCCCCCCCCcccc.....",
    28: ".....ccccCCCCCCCCCCCCCCcccc.....",
    29: ".....ccccCCCCCCCCCCCCCCcccc.....",
    30: ".....ccccCCCCCCCCCCCCCCcccc.....",
}

FACE_HAIR: Dict[str, Dict[str, Dict[int, str]]] = {
    "bald": {"front": {}, "back": {}},
    "short": {"front": {
        3:  "...........HHHHHHHHHH...........",
        4:  ".........HHUUHHHHHHHHHH.........",
        5:  "........HHUHHHHHHHHHHHHH........",
        6:  ".......HHHHHHHHHHHHHHHHHH.......",
        7:  ".......HHHHHHHHHHHHHHHHHH.......",
        8:  ".......HHHHHHHHHHHHHHHHHH.......",
        9:  ".......HHHHHH......HHHHHH.......",
        10: ".......HH..............HH.......",
        11: ".......HH..............HH.......",
        12: ".......HH..............HH.......",
        13: ".......H................H.......",
        14: ".......H................H.......",
    }, "back": {}},
}
FACE_HAIR["topknot"] = {"front": {**FACE_HAIR["short"]["front"],
    1: "..............HHHH..............",
    2: ".............HHHHHH.............",
}, "back": {}}
FACE_HAIR["topknot_pin"] = {"front": {**FACE_HAIR["topknot"]["front"],
    2: ".........GGGGHHHHHHGG...........",
}, "back": {}}
FACE_HAIR["bun"] = {"front": {**FACE_HAIR["short"]["front"],
    2: "............HHHHHHHH............",
    3: "..........HHHHHHHHHHHH..........",
}, "back": {}}
FACE_HAIR["bun_pin"] = {"front": {**FACE_HAIR["bun"]["front"],
    2: "........GGGGHHHHHHHHGG..........",
}, "back": {}}
FACE_HAIR["ponytail_high"] = {"front": {**FACE_HAIR["short"]["front"],
    1: "...............HHHH.............",
    2: "..............HHHHHH............",
}, "back": {
    2:  "....................HH..........",
    3:  "....................AAH.........",
    4:  ".....................HHH........",
    5:  "......................HHH.......",
    6:  "......................HHHH......",
    7:  ".......................HHH......",
    8:  ".......................HHU......",
    9:  ".......................HHH......",
    10: ".......................HHU......",
    11: ".......................HHH......",
    12: ".......................HHU......",
    13: ".......................HHH......",
    14: ".......................HHU......",
    15: ".......................HHH......",
    16: ".......................HHH......",
    17: "........................HH......",
    18: "........................HH......",
    19: "........................H.......",
}}
FACE_HAIR["ponytail"] = {"front": dict(FACE_HAIR["short"]["front"]), "back": {
    7:  "......................HHHH......",
    8:  ".......................HHH......",
    9:  "........................AA......",
    10: "........................HH......",
    11: "........................HH......",
    12: "........................HU......",
    13: "........................HH......",
    14: "........................HH......",
    15: "........................HU......",
    16: "........................HH......",
    17: "........................HH......",
    18: "........................HU......",
    19: "........................HH......",
    20: "........................HH......",
    21: "........................HH......",
    22: "........................HH......",
    23: ".........................H......",
}}
FACE_HAIR["braid"] = {"front": {**FACE_HAIR["short"]["front"],
    15: ".......H...............HH.......",
    16: "......................HHU.......",
    17: "......................UHH.......",
    18: "......................HHU.......",
    19: "......................UHH.......",
    20: "......................HHU.......",
    21: "......................UHH.......",
    22: "......................HHU.......",
    23: "......................UHH.......",
    24: "......................HHU.......",
    25: ".......................XX.......",
    26: "......................X..X......",
}, "back": {}}
FACE_HAIR["loose_long"] = {"front": {**FACE_HAIR["short"]["front"],
    10: "......HHH..............HHH......",
    11: "......HHH..............HHH......",
    12: "......HHH..............HHH......",
    13: "......HHH..............HHH......",
    14: "......HHH..............HHH......",
    15: "......HHH..............HHH......",
    16: "......HHH..............HHH......",
    17: "......HHH..............HHH......",
    18: "......HHH..............HHH......",
    19: ".....HHH................HHH.....",
    20: ".....HHH................HHH.....",
    21: ".....HHH................HHH.....",
    22: ".....HHH................HHH.....",
    23: "....HHH..................HHH....",
    24: "....HHH..................HHH....",
    25: "....HH....................HH....",
}, "back": {
    17: "........HHHHHHHHHHHHHHHH........",
    18: ".........HHHHHHHHHHHHHH.........",
    19: ".........HHHHHHHHHHHHHH.........",
    20: ".........HHHHHHHHHHHHHH.........",
    21: ".........HHHHHHHHHHHHHH.........",
    22: "..........HHHHHHHHHHHH..........",
}}

FACE_BEARD: Dict[str, Dict[int, str]] = {
    "none": {},
    "short": {
        15: "........H..............H........",
        16: "........HH............HH........",
        17: ".........HH..........HH.........",
        18: "..........HHH......HHH..........",
        19: "...........HHHHHHHHHH...........",
        20: "............HHHHHHHH............",
    },
    "long": {
        15: "........H..............H........",
        16: "........HH............HH........",
        17: ".........HH..........HH.........",
        18: "..........HHH......HHH..........",
        19: "...........HHHHHHHHHH...........",
        20: "............HHHHHHHH............",
        21: ".............HHHHHH.............",
        22: ".............HHUHHH.............",
        23: "..............HHHH..............",
        24: "..............HUHH..............",
        25: "...............HH...............",
        26: "...............HH...............",
    },
    "goatee": {
        18: "..............HHHH..............",
        19: "..............HHHH..............",
        20: "...............HH...............",
    },
    "mustache": {
        16: "............HHH..HHH............",
    },
}

FACE_HEADWEAR: Dict[str, Dict[int, str]] = {
    "none": {},
    "straw_hat": {
        1:  "...............BB...............",
        2:  "..............BBBB..............",
        3:  ".............BBBBBB.............",
        4:  "...........BBBBBBBBBB...........",
        5:  ".........BBBBBBBBBBBBBB.........",
        6:  ".......BBBBBBBBBBBBBBBBBB.......",
        7:  ".....BBBBBBBBBBBBBBBBBBBBBB.....",
        8:  "...BBBBBBBBBBBBBBBBBBBBBBBBBB...",
        9:  "..NNNNNNNNNNNNNNNNNNNNNNNNNNNN..",
    },
    "scholar_hat": {
        1:  "............BBBBBBBB............",
        2:  "...........BBBBBBBBBB...........",
        3:  "..........BBBBBBBBBBBB..........",
        4:  "..........BBBBBBBBBBBB..........",
        5:  ".........BBBBBBBBBBBBBB.........",
        6:  "........BBBBBBBBBBBBBBBB........",
        7:  ".....BBBBBBBBBBBBBBBBBBBBBB.....",
        8:  ".....BB..................BB.....",
        9:  ".....BB..................BB.....",
        10: ".....B....................B.....",
    },
    "headband": {
        9:  "......XXXXXXXXXXXXXXXXXXXX......",
        10: "......XXXXXXXXXXXXXXXXXXXXX.....",
        11: "..........................XX....",
        12: "...........................XX...",
        13: "...........................X....",
    },
    "hood": {
        2:  "............BBBBBBBB............",
        3:  "..........BBBBBBBBBBBB..........",
        4:  ".........BBBBBBBBBBBBBB.........",
        5:  "........BBBBBBBBBBBBBBBB........",
        6:  ".......BBBBBBBBBBBBBBBBBB.......",
        7:  "......BBBBBBBBBBBBBBBBBBBB......",
        8:  "......BBB..............BBB......",
        9:  "......BBB..............BBB......",
        10: "......BBB..............BBB......",
        11: "......BBB..............BBB......",
        12: "......BBB..............BBB......",
        13: "......BBB..............BBB......",
        14: "......BBB..............BBB......",
        15: "......BBB..............BBB......",
        16: "......BBB..............BBB......",
        17: "......BBB..............BBB......",
        18: "......BBB..............BBB......",
        19: ".....BBBB..............BBBB.....",
        20: "....BBBBB..............BBBBB....",
        21: "...BBBBBB..............BBBBBB...",
        22: "...BBBBBBB............BBBBBBB...",
        23: "...BBBBBBBB..........BBBBBBBB...",
        24: "...BBBBBBBBB........BBBBBBBBB...",
        25: "...BBBBBBBBBB......BBBBBBBBBN...",
        26: "...BBBBBBBBBBB....BBBBBBBBBNN...",
        27: "...BBBBBBBBBBB....BBBBBBBBBNN...",
        28: "...BBBBBBBBBBB....BBBBBBBBBNN...",
        29: "...BBBBBBBBBBB....BBBBBBBBBNN...",
        30: "...BBBBBBBBBBB....BBBBBBBBBNN...",
    },
    "cap": {
        2:  "............BBBBBBBB............",
        3:  "..........BBBBBBBBBBBB..........",
        4:  ".........BBBBBBBBBBBBBB.........",
        5:  "........BBBBBBBBBBBBBBBB........",
        6:  "........BBBBBBBBBBBBBBBB........",
        7:  "........BBBBBBBBBBBBBBBB........",
        8:  ".......NNNNNNNNNNNNNNNNNN.......",
    },
    "headscarf": {
        3:  "...........BBBBBBBBBB...........",
        4:  ".........BBBBBBBBBBBBBB.........",
        5:  "........BBBBBBBBBBBBBBBB........",
        6:  ".......BBBBBBBBBBBBBBBBBB.......",
        7:  ".......BBBBBBBBBBBBBBBBBB.......",
        8:  ".......BBBBBBBBBBBBBBBBBBBB.....",
        9:  ".......NBBBBBBBBBBBBBBBBBBBB....",
        10: "........................BBBBB...",
        11: ".........................BB.B...",
        12: "..........................B.B...",
    },
    "helmet": {
        1:  "...............MM...............",
        2:  "..............WWWW..............",
        3:  "............WWWWWWWW............",
        4:  "..........WWMWWWWWWWWW..........",
        5:  ".........WWMWWWWWWWWWWW.........",
        6:  "........WWWWWWWWWWWWWWWW........",
        7:  "........WWWWWWWWWWWWWWWW........",
        8:  ".......KKKKKKKKKKKKKKKKKK.......",
        9:  ".......KK..............KK.......",
    },
}

FACE_ACCESSORY: Dict[str, Dict[int, str]] = {
    "none": {},
    "ribbon": {
        4:  ".....................XX.........",
        5:  "....................XXXX........",
        6:  "......................XXX.......",
        7:  ".......................XX.......",
        8:  "........................X.......",
    },
}

EYE_STYLES = ("normal", "narrow", "closed")
EXPRESSIONS = ("neutral", "smile", "grin", "stern", "angry", "sad", "sly", "calm", "fierce", "worried")

# brows: pixels per side (left brow x 11..13, right brow x 18..20), rows relative to y=10
_BROWS = {
    "flat":   [(11, 0), (12, 0), (13, 0), (18, 0), (19, 0), (20, 0)],
    "stern":  [(11, -1), (12, -1), (13, 0), (18, 0), (19, -1), (20, -1)],
    "sad":    [(11, 0), (12, 0), (13, -1), (18, -1), (19, 0), (20, 0)],
    "sly":    [(11, 0), (12, 0), (13, 0), (18, -1), (19, -1), (20, -1)],
}
# mouths: (x, y, letter) absolute
_MOUTHS = {
    "flat":  [(14, 17, "K"), (15, 17, "K"), (16, 17, "K"), (17, 17, "K")],
    "smile": [(13, 16, "K"), (18, 16, "K"), (14, 17, "K"), (15, 17, "K"), (16, 17, "K"), (17, 17, "K")],
    "down":  [(14, 17, "K"), (15, 17, "K"), (16, 17, "K"), (17, 17, "K"), (13, 18, "K"), (18, 18, "K")],
    "grin":  [(13, 16, "K"), (14, 16, "K"), (15, 16, "K"), (16, 16, "K"), (17, 16, "K"), (18, 16, "K"),
              (13, 17, "K"), (14, 17, "M"), (15, 17, "M"), (16, 17, "M"), (17, 17, "M"), (18, 17, "K"),
              (14, 18, "K"), (15, 18, "K"), (16, 18, "K"), (17, 18, "K")],
    "smirk": [(14, 17, "K"), (15, 17, "K"), (16, 17, "K"), (17, 16, "K")],
    "small": [(15, 17, "K"), (16, 17, "K")],
}
_EXPRESSION_PARTS = {
    "neutral": ("flat", "flat", None),
    "smile":   ("flat", "smile", None),
    "grin":    ("flat", "grin", None),
    "stern":   ("stern", "flat", None),
    "angry":   ("stern", "down", None),
    "sad":     ("sad", "down", None),
    "sly":     ("sly", "smirk", None),
    "calm":    ("flat", "smile", "closed"),
    "fierce":  ("stern", "grin", None),
    "worried": ("sad", "small", None),
}


def make_face(spec: Dict[str, object]) -> Canvas:
    """32x32 outlined bust (head and shoulders) consistent with the 16x16 frames: same hair,
    headwear, beard, robe colors; readable expression (spec['expression'], spec['eyes'])."""
    s = _norm_spec(spec) if "_colors" not in spec else spec
    build = str(s["build"])
    g = Grid(FACE_SIZE, FACE_SIZE)
    hair = FACE_HAIR[str(s["hair"])]
    for y, row in _f(hair["back"]):
        g.paste([row], 0, y)
    head = dict(_FACE_HEAD)
    if build == "burly":
        head.update(_FACE_HEAD_BURLY)
    bust = {"burly": _FACE_BUST_BURLY, "child": _FACE_BUST_CHILD}.get(build, _FACE_BUST)
    for y, row in _f(head):
        g.paste([row], 0, y)
    for y, row in _f(bust):
        g.paste([row], 0, y)
    # robe on the bust
    robe = ROBE_STYLES[str(s["robe"])]
    texture = robe.get("texture")
    if texture == "lamellar":
        for y in range(22, FACE_SIZE):
            for x in range(FACE_SIZE):
                if g.get(x, y) in ("C", "c"):
                    g.set(x, y, "L" if (x // 2 + y) % 2 == 0 else "D")
    elif texture == "patches":
        for (x, y) in ((9, 27), (10, 27), (9, 28), (22, 29), (23, 29)):
            if g.get(x, y) in ("C", "c"):
                g.set(x, y, "X")
    g.replace({"c": str(robe["sleeve"]), "T": str(robe["collar"])})
    if robe.get("vest"):
        for y in range(23, 27):
            for x in range(14, 18):
                if g.get(x, y) == "C" and abs(x - 15.5) < (y - 22):
                    g.set(x, y, "S")
    if s.get("collar", "none") == "fur":
        for y in range(22, 26):
            for x in range(FACE_SIZE):
                if g.get(x, y) in ("C", "L", "D") and (y < 25 or x < 9 or x > 22):
                    g.set(x, y, "V" if (x + y) % 2 == 0 else "J")
    # shading on cloth rows: light edge left, dark edge right (top-left light)
    for y in range(22, FACE_SIZE):
        xs = [x for x in range(FACE_SIZE) if g.get(x, y) == "C"]
        if xs:
            g.set(xs[0], y, "L")
            g.set(xs[-1], y, "D")
            if len(xs) > 6:
                g.set(xs[-2], y, "D")
    # features
    eyes = str(s["eyes"])
    brows_key, mouth_key, eye_override = _EXPRESSION_PARTS[str(s["expression"])]
    if eye_override:
        eyes = eye_override
    dy = 1 if build == "child" else 0
    for (x, oy) in _BROWS[brows_key]:
        g.set(x, 10 + oy + dy, "H" if str(s["hair"]) != "bald" or str(s["beard"]) != "none" else "K")
    for ex_ in (11, 19):
        if eyes == "normal":
            g.set(ex_, 12 + dy, "M")
            g.set(ex_ + 1, 12 + dy, "E")
            g.set(ex_, 13 + dy, "E")
            g.set(ex_ + 1, 13 + dy, "E")
        elif eyes == "narrow":
            g.set(ex_, 13 + dy, "E")
            g.set(ex_ + 1, 13 + dy, "E")
        else:
            g.set(ex_, 13 + dy, "K")
            g.set(ex_ + 1, 13 + dy, "K")
    g.set(16, 14 + dy, "Z")
    g.set(15, 15 + dy, "Z")
    g.set(16, 15 + dy, "Z")
    for (x, y, ch) in _MOUTHS[mouth_key]:
        g.set(x, y + dy, ch)
    if s.get("scar"):
        for (x, y) in ((22, 9), (21, 10), (21, 11), (20, 14), (20, 15), (19, 16)):
            if g.get(x, y + dy) in ("S", "Z"):
                g.set(x, y + dy, "K")
    for y, row in _f(hair["front"]):
        g.paste([row], 0, y)
    for y, row in _f(FACE_BEARD[str(s["beard"])]):
        g.paste([row], 0, y)
    for y, row in _f(FACE_HEADWEAR[str(s["headwear"])]):
        g.paste([row], 0, y)
    for y, row in _f(FACE_ACCESSORY[str(s["hair_accessory"])]):
        g.paste([row], 0, y)
    for ex in s.get("face_extras", []) or []:
        g.paste(ex["rows"], int(ex["x"]), int(ex["y"]))
    for ex in s.get("extras", []) or []:
        if ex.get("face"):
            g.paste(ex["rows"], int(ex.get("face_x", ex["x"])), int(ex.get("face_y", ex["y"])))
    return g.to_canvas(s["_colors"]).outlined("ink_black")  # type: ignore[arg-type]


def list_parts() -> Dict[str, Tuple[str, ...]]:
    """Every part name the kit knows, for documentation and validation."""
    return {
        "build": tuple(BUILDS), "hair": tuple(HAIR_STYLES), "headwear": tuple(HEADWEAR),
        "beard": tuple(BEARDS), "hair_accessory": tuple(HAIR_ACCESSORIES), "robe": tuple(ROBE_STYLES),
        "weapon": WEAPONS, "carry": tuple(CARRY), "collar": COLLARS, "expression": EXPRESSIONS,
        "eyes": EYE_STYLES, "colors": tuple(FRIENDLY_KEYS),
    }
