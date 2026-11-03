"""gen_characters_npcs.py -- the 13 named NPC character sheets + faces of ASSET_SPEC.md §5.1.

yun_baeksan 윤백산   청운검문 장문인: elderly master, paper_light hair + long beard, jade_dark robe
go_jinak    고진악   청운검문 대사형: senior disciple, navy/jade robe, sharp look, jian at the hip
tak_ung     탁웅     흑사방 방주: burly gang boss, bronze_navy coat, beard, dao
baek_yeorin 백여린   흑사방 책사: strategist, ink_dark robe, folding fan
boatman     구씨     old boatman, straw hat, pole
silk_merchant 비단 장수  merchant carrying a silk bolt, plum accents
waiter      점소이   inn waiter, paper shirt, towel on the shoulder
merchant    장터 상인  market vendor, sand/earth, abacus
heuksa_thug 흑사방 졸개  black outfit, headscarf, dao
heuksa_courier 연락책  grey hooded
warehouse_keeper 창고지기  burly, black, key ring
hermit      은둔 노인  long white hair, ragged paper robe, bare feet
bandit_boss 도적 두목  scarred, fur collar, dao

Allegiance is readable at a glance: 청운검문 = jade robes; 흑사방 = bronze_navy / ink_dark with a
vermilion detail; commoners = paper / earth / sand. All assembled with charkit so the NPCs
share the heroes' and companions' silhouette language.
"""
from __future__ import annotations

import os
from typing import Dict, List

from charkit import make_character
from pixelkit import character_sheet

# Shared allegiance color blocks (merged under each character's own colors).
CHEONGUN: Dict[str, str] = {      # 청운검문: jade robes with paper trim
    "cloth": "jade", "cloth_dark": "jade_dark", "cloth_light": "jade_light",
    "trim": "paper", "accent": "paper_dark", "accent_dark": "sand",
    "pants": "jade_dark", "feet": "ink_dark",
}
HEUKSA: Dict[str, str] = {        # 흑사방: black clothes (bronze_navy / ink_dark) + vermilion detail
    "cloth": "bronze_navy", "cloth_dark": "ink_dark", "cloth_light": "navy",
    "trim": "ink", "accent": "vermilion", "accent_dark": "vermilion_dark",
    "pants": "ink_dark", "feet": "ink_dark",
}

NPCS: Dict[str, dict] = {
    "yun_baeksan": {   # 윤백산: elderly sect master, white hair + long beard, jade_dark robe
        "build": "normal", "hair": "topknot_pin", "beard": "long", "robe": "long_robe",
        "weapon": "jian", "hip_weapon": True, "expression": "stern", "eyes": "narrow",
        "colors": {**CHEONGUN, "hair": "paper_light", "hair_light": "paper_light",
                   "cloth": "jade_dark", "cloth_dark": "jade_dark", "cloth_light": "jade",
                   "trim": "paper_light", "accent": "paper", "accent_dark": "paper_dark",
                   "hilt": "gold"},
    },
    "go_jinak": {      # 고진악: senior disciple, navy/jade robe, sharp look, jian
        "build": "tall", "hair": "topknot_pin", "robe": "robe_sash", "weapon": "jian",
        "hip_weapon": True, "expression": "sly", "eyes": "narrow",
        "colors": {**CHEONGUN, "hair": "ink_dark", "cloth": "jade", "cloth_dark": "navy",
                   "cloth_light": "jade_light", "trim": "paper", "accent": "navy",
                   "accent_dark": "bronze_navy", "pants": "navy", "hilt": "gold"},
    },
    "tak_ung": {       # 탁웅: gang boss, burly, bronze_navy coat, beard, dao
        "build": "burly", "hair": "short", "beard": "short", "robe": "long_robe", "weapon": "dao",
        "hip_weapon": True, "expression": "stern",
        "colors": {**HEUKSA, "hair": "ink_dark", "trim": "vermilion", "hilt": "gold"},
    },
    "baek_yeorin": {   # 백여린: strategist, ink_dark robe, folding fan
        "build": "tall", "hair": "topknot_pin", "robe": "long_robe", "weapon": "fan",
        "expression": "sly", "eyes": "narrow",
        "colors": {"hair": "ink_dark", "cloth": "ink_dark", "cloth_dark": "ink_dark",
                   "cloth_light": "ink", "trim": "ink_pale", "accent": "vermilion",
                   "accent_dark": "vermilion_dark", "pants": "ink_dark", "feet": "ink_dark",
                   "prop": "paper", "prop_dark": "ink_light", "wood": "earth_dark", "hilt": "ink_pale"},
    },
    "boatman": {       # 구씨: old boatman, straw hat, pole
        "build": "normal", "hair": "short", "headwear": "straw_hat", "beard": "short",
        "robe": "short_tunic", "weapon": "pole", "expression": "sad", "eyes": "narrow",
        "colors": {"hair": "ink_light", "hair_light": "ink_pale", "cloth": "paper_dark",
                   "cloth_dark": "sand", "cloth_light": "paper", "trim": "paper", "accent": "earth",
                   "accent_dark": "earth_dark", "pants": "earth", "feet": "earth_dark",
                   "hat": "sand", "hat_dark": "earth_light", "wood": "earth"},
    },
    "silk_merchant": { # 비단 장수: merchant with a silk bolt, plum accents
        "build": "normal", "hair": "short", "headwear": "cap", "robe": "long_robe", "weapon": "palm",
        "carry": "bolt", "expression": "worried",
        "colors": {"hair": "ink_dark", "cloth": "paper", "cloth_dark": "paper_dark",
                   "cloth_light": "paper_light", "trim": "plum", "accent": "plum",
                   "accent_dark": "plum", "pants": "ink_dark", "feet": "ink_dark",
                   "hat": "plum", "hat_dark": "ink_dark", "extra": "plum", "extra2": "vermilion_light"},
    },
    "waiter": {        # 점소이: inn waiter, paper shirt, towel on the shoulder
        "build": "normal", "hair": "short", "headwear": "headscarf", "robe": "short_tunic",
        "weapon": "palm", "carry": "towel", "expression": "grin",
        "colors": {"hair": "ink_dark", "cloth": "paper", "cloth_dark": "paper_dark",
                   "cloth_light": "paper_light", "trim": "paper_light", "accent": "earth",
                   "accent_dark": "earth_dark", "pants": "ink_dark", "feet": "earth_dark",
                   "hat": "paper_dark", "hat_dark": "sand"},
    },
    "merchant": {      # 장터 상인: market vendor, sand/earth, abacus
        "build": "normal", "hair": "short", "headwear": "cap", "beard": "goatee",
        "robe": "robe_sash", "weapon": "palm", "carry": "abacus", "expression": "smile",
        "colors": {"hair": "ink", "hair_light": "ink_light", "cloth": "sand", "cloth_dark": "earth_light",
                   "cloth_light": "paper_dark", "trim": "paper", "accent": "earth",
                   "accent_dark": "earth_dark", "pants": "earth_dark", "feet": "earth_dark",
                   "hat": "earth", "hat_dark": "earth_dark", "wood": "earth", "dark": "ink_dark"},
    },
    "heuksa_thug": {   # 흑사방 졸개: black outfit, headscarf, dao
        "build": "normal", "hair": "short", "headwear": "headscarf", "robe": "short_tunic",
        "weapon": "dao", "hip_weapon": True, "expression": "angry",
        "colors": {**HEUKSA, "hair": "ink_dark", "hat": "ink_dark", "hat_dark": "ink_black",
                   "hilt": "earth_light"},
    },
    "heuksa_courier": {  # 연락책: grey hooded
        "build": "normal", "hair": "short", "headwear": "hood", "robe": "long_robe",
        "weapon": "dagger", "expression": "neutral", "eyes": "narrow",
        "colors": {"hair": "ink_dark", "cloth": "ink_light", "cloth_dark": "ink",
                   "cloth_light": "ink_pale", "trim": "ink", "accent": "vermilion",
                   "accent_dark": "vermilion_dark", "pants": "ink_dark", "feet": "ink_dark",
                   "hat": "ink_light", "hat_dark": "ink", "hilt": "earth_light"},
    },
    "warehouse_keeper": {  # 창고지기: burly, black, key ring
        "build": "burly", "hair": "short", "headwear": "headscarf", "robe": "short_tunic",
        "weapon": "palm", "carry": "keys", "expression": "stern",
        "colors": {**HEUKSA, "hair": "ink_dark", "hat": "ink_dark", "hat_dark": "ink_black",
                   "hilt": "gold"},
    },
    "hermit": {        # 은둔 노인: long white hair, ragged paper robe, bare feet
        "build": "normal", "hair": "loose_long", "beard": "long", "robe": "ragged", "weapon": "palm",
        "carry": "gourd", "expression": "calm",
        "colors": {"hair": "paper_light", "hair_light": "paper_light", "cloth": "paper",
                   "cloth_dark": "paper_dark", "cloth_light": "paper_light", "trim": "paper_dark",
                   "accent": "earth_light", "accent_dark": "earth", "pants": "paper_dark",
                   "feet": "skin", "dark": "ink_dark", "prop": "earth_light", "prop_dark": "earth",
                   "extra2": "jade_light"},
    },
    "bandit_boss": {   # 도적 두목: scarred, fur collar, dao
        "build": "burly", "hair": "short", "headwear": "headband", "beard": "short", "scar": True,
        "collar": "fur", "robe": "short_tunic", "weapon": "dao", "hip_weapon": True,
        "expression": "fierce",
        "colors": {"hair": "ink_dark", "cloth": "earth", "cloth_dark": "earth_dark",
                   "cloth_light": "earth_light", "trim": "earth_light", "accent": "ink_dark",
                   "accent_dark": "ink_black", "pants": "ink_dark", "feet": "earth_dark",
                   "prop": "paper_dark", "prop_dark": "earth_light", "extra": "vermilion_dark",
                   "hilt": "earth_light"},
    },
}


def build(art_root: str, preview_dir: str, cellmap_dir: str) -> List[str]:
    out_dir = os.path.join(art_root, "Characters")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(preview_dir, exist_ok=True)
    written: List[str] = []
    for name, spec in NPCS.items():
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
