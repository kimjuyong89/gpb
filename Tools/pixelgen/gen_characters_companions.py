"""gen_characters_companions.py -- the 9 companion character sheets + 9 faces of ASSET_SPEC.md §5.1.

soyuk (소육), seokdu (석두), unhak (운학), yeona (연아), baekseolhwa (백설화), hongryeon (홍련),
mukhyang (묵향), yusoso (유소소), neungso (능소) -- the 1막 백로진 companions of 강호유랑기.

Every sheet is assembled with charkit (the shared body / hair / robe / weapon templates) so the
companions share the heroes' silhouette language, walk cycle and attack grammar; each spec only
chooses parts and palette names. Look cues come from ASSET_SPEC.md §5.1 and GPA's docs
(docs/08_인물.md, docs/14_동료_스토리.md).

Color rules that came out of the review rounds (keep them when editing specs):
  * nothing next to the face may sit on the skin ramp (skin / sand / paper_dark): a sand tunic or
    a paper_dark headscarf melts into the face at 16 px and the bust looks bare-shouldered;
  * headwear needs a value step against the hair (a cap in `ink` on `ink_dark` hair vanishes);
  * feet need a value step against the pants/skirt so the walk cycle reads;
  * `extra` (X) colors the ragged-robe patches on the 32x32 face, `dark` (K) colors them at 16 px:
    set both to the same cloth-patch tone or the face shows red "patches".
"""
from __future__ import annotations

import os
from typing import Dict, List

from charkit import make_character
from pixelkit import character_sheet

# 32x32 face overlay: 연아's crow (까마귀) perched on her shoulder (viewer's left, away from
# the braid that hangs on the other side); the beak is the hilt letter G (gold) so the bird keeps
# one readable bright point. Head top-left, beak pointing outward, tail resting on the shoulder.
_CROW_ROWS = [
    ".HH...",
    "GHHH..",
    ".HHHH.",
    "..HHHH",
    "...HH.",
]

# Off-hand book for 묵향 (she reads and writes even in battle): letter Q = extra2 (paper_light)
# pages with a K spine on the side away from the hand. Anchored on the body at the sash row
# (y 11 for the normal build) in every walk / idle frame; the attack frames keep both hands free.
_BOOK = ["QK", "QK", "QK"]
_BOOK_DOWN = {"rows": _BOOK, "x": 12, "y": 10, "dirs": ["down"],
              "poses": ["stand", "step_l", "pass", "step_r"], "anchor": "body"}
_BOOK_UP = {"rows": ["KQ", "KQ", "KQ"], "x": 2, "y": 10, "dirs": ["up"],
            "poses": ["stand", "step_l", "pass", "step_r"], "anchor": "body"}
_BOOK_LEFT = {"rows": ["KQ", "KQ", "KQ"], "x": 4, "y": 10, "dirs": ["left"],
              "poses": ["stand", "step_l", "pass", "step_r"], "anchor": "body"}

COMPANIONS: Dict[str, dict] = {
    # 소육: small boy pickpocket (하오문 소매치기), ragged ink_dark clothes with brown cloth
    # patches, a brown cloth cap, straw sandals, a dagger at the hip. Sly smirk, narrow eyes.
    "soyuk": {
        "build": "child", "hair": "short", "headwear": "cap", "robe": "ragged",
        "weapon": "dagger", "hip_weapon": True, "expression": "sly", "eyes": "narrow",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "ink_dark", "cloth_dark": "ink_dark", "cloth_light": "ink",
                   "trim": "ink", "accent": "earth", "accent_dark": "earth_dark",
                   "pants": "ink_dark", "feet": "sand", "dark": "earth_dark", "extra": "earth",
                   "hat": "earth", "hat_dark": "earth_dark", "hilt": "earth_light",
                   "weapon": "ink_pale", "weapon_light": "paper_light"},
    },
    # 석두: big quiet brawler (떠돌이 주먹), bare arms, vermilion headband, earth vest over
    # ink_dark trousers, leather shoes; bare fists (palm strike with a pale qi burst).
    "seokdu": {
        "build": "burly", "hair": "short", "headwear": "headband", "robe": "vest_bare_arms",
        "weapon": "palm", "expression": "neutral", "eyes": "normal",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "earth", "cloth_dark": "earth_dark", "cloth_light": "earth_light",
                   "trim": "earth_light", "accent": "sand", "accent_dark": "earth_light",
                   "pants": "ink_dark", "feet": "earth", "extra": "vermilion",
                   "extra2": "paper_light"},
    },
    # 운학: wandering swordsman cast out of 청운검문, tall, topknot, pale (ink_pale / paper)
    # robe with a faded jade_dark sash as the last trace of the sect, jian at the hip. Stern.
    "unhak": {
        "build": "tall", "hair": "topknot", "robe": "robe_sash", "weapon": "jian",
        "hip_weapon": True, "expression": "stern", "eyes": "normal",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "ink_pale", "cloth_dark": "ink_light", "cloth_light": "paper",
                   "trim": "paper", "accent": "jade_dark", "accent_dark": "bronze_navy",
                   "pants": "ink_dark", "feet": "ink_dark", "hilt": "gold", "dark": "ink_dark",
                   "weapon": "ink_pale", "weapon_light": "paper_light"},
    },
    # 연아: bright slingshot girl of the ferry, short, braid with a red tie, moss tunic with a
    # sand collar and sash over earth trousers ("sand/moss clothes"); sling in the attack
    # frames; her crow sits on her shoulder on the dialogue face.
    "yeona": {
        "build": "child", "hair": "braid", "robe": "short_tunic", "weapon": "sling",
        "expression": "smile", "eyes": "normal",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "moss", "cloth_dark": "moss_dark", "cloth_light": "moss_light",
                   "trim": "sand", "accent": "sand", "accent_dark": "earth_light",
                   "pants": "earth", "feet": "earth_dark", "extra": "vermilion",
                   "prop": "earth_light", "prop_dark": "earth", "dark": "ink_dark",
                   "weapon_light": "paper_light", "hilt": "gold"},
        "face_extras": [{"rows": _CROW_ROWS, "x": 3, "y": 19}],
    },
    # 백설화: quiet herbalist / medic in a white (paper_light) robe, hair bun, jade sash and
    # collar, herb basket in the off hand; attack = needle throw. Serene closed-eye smile.
    "baekseolhwa": {
        "build": "normal", "hair": "bun", "robe": "long_robe", "weapon": "needle_throw",
        "carry": "basket", "expression": "calm", "eyes": "closed",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "paper_light", "cloth_dark": "paper", "cloth_light": "paper_light",
                   "trim": "jade_light", "accent": "jade", "accent_dark": "jade_dark",
                   "pants": "paper_dark", "feet": "earth", "prop": "paper_dark",
                   "prop_dark": "earth_light", "weapon_light": "ink_pale"},
    },
    # 홍련: mercenary swordswoman in vermilion, dao sabre at the hip, high ponytail with a
    # dark tie, black sash over ink_dark trousers. Stern, narrow eyes.
    "hongryeon": {
        "build": "normal", "hair": "ponytail_high", "robe": "short_tunic", "weapon": "dao",
        "hip_weapon": True, "expression": "stern", "eyes": "narrow",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "vermilion", "cloth_dark": "vermilion_dark",
                   "cloth_light": "vermilion_light", "trim": "paper_dark",
                   "accent": "ink_dark", "accent_dark": "bronze_navy",
                   "pants": "ink_dark", "feet": "ink_dark", "hilt": "gold", "dark": "ink_dark",
                   "weapon": "ink_pale", "weapon_light": "paper_light"},
    },
    # 묵향: scholar's daughter, plum robe shaded ink_dark, pale hairpins in a bun, a book in
    # the off hand; attack = ink-needle throw (dark grey needles). Worried look.
    "mukhyang": {
        "build": "normal", "hair": "bun_pin", "robe": "long_robe", "weapon": "needle_throw",
        "expression": "worried", "eyes": "normal",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "plum", "cloth_dark": "ink_dark", "cloth_light": "plum",
                   "trim": "paper_light", "accent": "ink_dark", "accent_dark": "bronze_navy",
                   "pants": "ink_dark", "feet": "ink_dark", "hilt": "ink_pale",
                   "weapon_light": "ink_light", "extra2": "paper_light", "dark": "ink_dark"},
        "extras": [_BOOK_DOWN, _BOOK_UP, _BOOK_LEFT],
    },
    # 유소소: cheerful cook, grey (ink_light) headscarf, paper apron over an earth dress,
    # kitchen cleaver. Big grin.
    "yusoso": {
        "build": "normal", "hair": "short", "headwear": "headscarf", "robe": "apron_dress",
        "weapon": "cleaver", "hip_weapon": False, "expression": "grin", "eyes": "normal",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "earth", "cloth_dark": "earth_dark", "cloth_light": "earth_light",
                   "trim": "paper", "accent": "sand", "accent_dark": "earth_light",
                   "pants": "earth_dark", "feet": "earth_dark", "hat": "ink_light",
                   "hat_dark": "ink", "wood": "earth", "weapon": "ink_pale",
                   "weapon_light": "paper_light"},
    },
    # 능소: earnest 청운검문 outer disciple, jade sect robe (same palette as the 청운도복 hero
    # outfit), low ponytail with a pale tie, her broom is her sword.
    "neungso": {
        "build": "normal", "hair": "ponytail", "robe": "robe_sash", "weapon": "broom",
        "expression": "neutral", "eyes": "normal",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "jade", "cloth_dark": "jade_dark", "cloth_light": "jade_light",
                   "trim": "paper", "accent": "paper_dark", "accent_dark": "sand",
                   "pants": "jade_dark", "feet": "ink_dark", "wood": "earth",
                   "prop": "sand", "prop_dark": "earth_light"},
    },
}

NAMES = tuple(COMPANIONS)


def build(art_root: str, preview_dir: str, cellmap_dir: str) -> List[str]:
    out_dir = os.path.join(art_root, "Characters")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(preview_dir, exist_ok=True)
    written: List[str] = []
    for name, spec in COMPANIONS.items():
        walk, attack, hurt, face = make_character(spec, face=True)
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
