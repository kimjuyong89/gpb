"""gen_characters_heroes.py -- the 12 hero character sheets + 4 faces of ASSET_SPEC.md §5.1.

hero_1..hero_4 (the four character-creation faces) x 3 outfits:
  <hero>            traveler clothes (base; the only variant with a face sheet)
  <hero>_cheongun   청운도복: jade / jade_dark robe with paper trim
  <hero>_heuksa     흑사흑의: bronze_navy / ink_dark robe with a vermilion sash

Everything is assembled with charkit (shared body/hair/robe/weapon templates) so the heroes
match the companions and NPCs built by the other generators.
"""
from __future__ import annotations

import copy
import os
from typing import Dict, List

from charkit import make_character
from pixelkit import character_sheet

# The four heroes must read as four different people at 16 px: hair style + color, build,
# ribbon / braid, robe cut and accent.
HEROES: Dict[str, dict] = {
    "hero_1": {   # young man, black topknot, plain traveler robe paper/earth, sand sash
        "build": "normal", "hair": "topknot", "robe": "robe_sash", "weapon": "jian", "hip_weapon": True,
        "expression": "neutral",
        "colors": {"skin": "skin", "hair": "ink_dark", "cloth": "paper", "cloth_dark": "paper_dark",
                   "cloth_light": "paper_light", "trim": "earth_light", "accent": "sand",
                   "accent_dark": "earth_light", "pants": "earth", "feet": "earth_dark"},
    },
    "hero_2": {   # young man, brown hair tied back, slightly taller, grey robe
        "build": "tall", "hair": "ponytail", "robe": "long_robe", "weapon": "jian", "hip_weapon": True,
        "expression": "stern",
        "colors": {"skin": "skin", "hair": "earth", "hair_light": "earth_light", "cloth": "ink_light",
                   "cloth_dark": "ink", "cloth_light": "ink_pale", "trim": "ink_pale", "accent": "earth",
                   "accent_dark": "earth_dark", "pants": "ink_dark", "feet": "ink_dark"},
    },
    "hero_3": {   # young woman, black hair with a vermilion ribbon, pale robe
        "build": "normal", "hair": "loose_long", "hair_accessory": "ribbon", "robe": "dress",
        "weapon": "jian", "hip_weapon": True, "expression": "smile",
        "colors": {"skin": "skin", "hair": "ink_dark", "cloth": "paper_light", "cloth_dark": "paper",
                   "cloth_light": "paper_light", "trim": "paper_dark", "accent": "vermilion",
                   "accent_dark": "vermilion_dark", "extra": "vermilion", "pants": "paper_dark",
                   "feet": "earth"},
    },
    "hero_4": {   # young woman, brown braid, jade-trim robe
        "build": "normal", "hair": "braid", "robe": "dress", "weapon": "jian", "hip_weapon": True,
        "expression": "calm",
        "colors": {"skin": "skin", "hair": "earth", "hair_light": "earth_light", "cloth": "paper",
                   "cloth_dark": "paper_dark", "cloth_light": "paper_light", "trim": "jade",
                   "accent": "jade", "accent_dark": "jade_dark", "extra": "jade_dark", "pants": "earth",
                   "feet": "earth_dark"},
    },
}

OUTFITS: Dict[str, Dict[str, str]] = {
    "": {},
    "_cheongun": {"cloth": "jade", "cloth_dark": "jade_dark", "cloth_light": "jade_light",
                  "trim": "paper", "accent": "paper_dark", "accent_dark": "sand",
                  "pants": "jade_dark", "feet": "ink_dark"},
    "_heuksa": {"cloth": "bronze_navy", "cloth_dark": "ink_dark", "cloth_light": "navy",
                "trim": "ink", "accent": "vermilion", "accent_dark": "vermilion_dark",
                "pants": "ink_dark", "feet": "ink_dark"},
}


def hero_spec(hero: str, suffix: str) -> dict:
    spec = copy.deepcopy(HEROES[hero])
    spec["colors"].update(OUTFITS[suffix])
    return spec


def build(art_root: str, preview_dir: str, cellmap_dir: str) -> List[str]:
    out_dir = os.path.join(art_root, "Characters")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(preview_dir, exist_ok=True)
    written: List[str] = []
    for hero in HEROES:
        for suffix in OUTFITS:
            name = hero + suffix
            spec = hero_spec(hero, suffix)
            walk, attack, hurt, face = make_character(spec, face=(suffix == ""))
            sheet, face_sheet = character_sheet(name, walk, attack, hurt, face)
            written.extend(sheet.save(out_dir))
            written.append(sheet.preview(os.path.join(preview_dir, f"{sheet.file_name}_preview.png"), scale=4))
            if face_sheet is not None:
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
