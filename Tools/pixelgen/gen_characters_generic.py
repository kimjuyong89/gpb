"""gen_characters_generic.py -- the 12 generic NPC / enemy character sheets + faces of ASSET_SPEC.md §5.1.

villager_m  촌민(남)   plain commoner: 상투 topknot, undyed grey hemp tunic, earth sash, straw shoes
villager_f  촌민(여)   married commoner: 쪽머리 bun, cream dress with an earth hem, moss sash, basket
old_woman   노파       grey bun, dark grey long robe, paper collar, walking cane (walk frames), sad narrow eyes
child_m     남자아이   child build, small topknot, slate-blue tunic, sand belt, bare feet
child_f     여자아이   child build, bun with a vermilion ribbon, cream dress with a vermilion sash
monk        승려       shaved head, grey robe, ochre kasaya sash, staff; calm closed-eye face with prayer beads
guard       관병       tall, iron cap, navy/steel lamellar vest, spear with a vermilion tassel
scholar     서생       ink_dark scholar hat, paper robe, navy sash, scroll in hand
beggar      거지       patched grey rags (개방 look), rope belt, bare feet, gourd, cheeky grin
bandit      갈대밭 도적 vermilion_dark bandana (headscarf), earth tunic, stubble, rusty iron jian at the hip
disciple_m  청운 외문제자(남)  short hair + paper sect headband, jade robe with sash, iron jian
disciple_f  청운 외문제자(여)  bun + paper sect headband, jade dress with a paper hem, iron jian

Faction reads at a glance (same rules as the named NPCs): 청운검문 = jade robes + paper trim;
commoners = paper / grey hemp / earth; the reed-field bandit shares the 도적 두목's dark-red
headcloth. Everything is assembled with charkit so the generic cast keeps the heroes' silhouette
language, walk cycle and attack grammar; each entry is a spec (parts + palette names) and the only
custom art is the old woman's cane overlay and the monk's bead string on the dialogue bust.

Color rules kept from the companions' review rounds: nothing touching the face sits on the skin
ramp (skin / sand / paper_dark); headwear keeps a value step against the hair; feet keep a value
step against the pants or skirt so the walk cycle reads; `dark` (K) and `extra` (X) both color
the ragged-robe patches (16 px frames / 32 px face) so they are set to the same tone.
"""
from __future__ import annotations

import os
from typing import Dict, List

from charkit import make_character
from pixelkit import character_sheet

# 청운검문 (jade robes with paper trim) -- the same block the heroes' _cheongun outfit and the named
# sect NPCs use, so every sect member on screen matches.
CHEONGUN: Dict[str, str] = {
    "cloth": "jade", "cloth_dark": "jade_dark", "cloth_light": "jade_light",
    "trim": "paper", "accent": "paper_dark", "accent_dark": "sand",
    "pants": "jade_dark", "feet": "ink_dark",
}

# The old woman's walking cane: a wood (O) stick with a lighter knob (V) above the off hand, planted
# on the ground (y 10..14) one pixel away from the body so the ink outline separates it from the
# robe; shown in every walk / idle frame (she lets go of it in the attack and hurt frames, where
# both hands are busy). Body-anchored: the body never bobs, only the head does, so it stays planted.
_WALK = ["stand", "step_l", "pass", "step_r"]
_CANE = ["V", "O", "O", "O", "O"]
_CANE_DOWN = {"rows": _CANE, "x": 13, "y": 10, "dirs": ["down"], "poses": _WALK, "anchor": "body"}
_CANE_UP = {"rows": _CANE, "x": 2, "y": 10, "dirs": ["up"], "poses": _WALK, "anchor": "body"}
_CANE_LEFT = {"rows": _CANE, "x": 4, "y": 10, "dirs": ["left"], "poses": _WALK, "anchor": "body"}

# 32x32 face overlays (letters -> the spec's colors).
# Old woman: crow's feet (two diagonal strokes) at the outer corner of each eye.
_WRINKLES = [
    {"rows": ["K.", ".K"], "x": 8, "y": 12},
    {"rows": [".K", "K."], "x": 22, "y": 12},
]
# Monk: a string of prayer beads (염주) hanging over the chest of the bust.
_BEADS = [{"rows": ["J....J", ".J..J.", "..JJ.."], "x": 13, "y": 26}]

GENERIC: Dict[str, dict] = {
    # 촌민(남): topknot, undyed grey hemp tunic (ink_pale / ink_light), earth sash, earth trousers.
    "villager_m": {
        "build": "normal", "hair": "topknot", "robe": "short_tunic", "weapon": "palm",
        "expression": "smile", "eyes": "normal",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "ink_pale", "cloth_dark": "ink_light", "cloth_light": "paper",
                   "trim": "ink_light", "accent": "earth", "accent_dark": "earth_dark",
                   "pants": "earth", "feet": "ink_dark"},
    },
    # 촌민(여): bun, cream dress with an earth_light hem and collar, moss sash, a basket on the arm.
    "villager_f": {
        "build": "normal", "hair": "bun", "robe": "dress", "weapon": "palm", "carry": "basket",
        "expression": "smile", "eyes": "normal",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "paper", "cloth_dark": "paper_dark", "cloth_light": "paper_light",
                   "trim": "earth_light", "accent": "moss", "accent_dark": "moss_dark",
                   "pants": "paper_dark", "feet": "earth_dark",
                   "prop": "sand", "prop_dark": "earth_light"},
    },
    # 노파: grey bun, dark ink long robe, paper collar, earth_light sash, brown shoes, cane; sad narrow eyes.
    "old_woman": {
        "build": "normal", "hair": "bun", "robe": "long_robe", "weapon": "palm",
        "expression": "sad", "eyes": "narrow",
        "extras": [_CANE_DOWN, _CANE_UP, _CANE_LEFT],
        "face_extras": _WRINKLES,
        "colors": {"skin": "skin", "hair": "ink_pale", "hair_light": "paper_dark",
                   "cloth": "ink", "cloth_dark": "ink_dark", "cloth_light": "ink_light",
                   "trim": "paper", "accent": "earth_light", "accent_dark": "earth",
                   "pants": "ink_dark", "feet": "earth", "wood": "earth", "prop": "earth_light",
                   "dark": "ink"},
    },
    # 남자아이: child build, small topknot, slate-blue tunic with a sand belt, bare feet.
    "child_m": {
        "build": "child", "hair": "topknot", "robe": "short_tunic", "weapon": "palm",
        "expression": "grin", "eyes": "normal",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "navy", "cloth_dark": "bronze_navy", "cloth_light": "steel",
                   "trim": "steel", "accent": "sand", "accent_dark": "earth_light",
                   "pants": "earth", "feet": "skin"},
    },
    # 여자아이: child build, bun with a vermilion ribbon, cream dress, vermilion sash, paper_dark hem.
    "child_f": {
        "build": "child", "hair": "bun", "hair_accessory": "ribbon", "robe": "dress", "weapon": "palm",
        "expression": "smile", "eyes": "normal",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "paper", "cloth_dark": "paper_dark", "cloth_light": "paper_light",
                   "trim": "paper_dark", "accent": "vermilion", "accent_dark": "vermilion_dark",
                   "extra": "vermilion", "pants": "paper_dark", "feet": "earth"},
    },
    # 승려: shaved head, grey robe, ochre (earth_light) kasaya sash, iron-shod staff, calm closed eyes.
    "monk": {
        "build": "normal", "hair": "bald", "robe": "long_robe", "weapon": "staff",
        "expression": "calm", "eyes": "closed",
        "face_extras": _BEADS,
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "ink_light", "cloth_dark": "ink", "cloth_light": "ink_pale",
                   "trim": "ink_pale", "accent": "earth_light", "accent_dark": "earth",
                   "pants": "ink", "feet": "earth_dark", "wood": "earth", "weapon_light": "ink_pale",
                   "prop_dark": "earth_dark", "dark": "ink_dark"},
    },
    # 관병: tall, iron cap (ink_light / ink_pale), navy-and-steel lamellar vest, leather belt,
    # spear with a vermilion tassel.
    "guard": {
        "build": "tall", "hair": "short", "headwear": "helmet", "robe": "armor_lamellar",
        "weapon": "spear", "expression": "stern", "eyes": "normal",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "navy", "cloth_dark": "bronze_navy", "cloth_light": "steel",
                   "trim": "steel", "accent": "earth", "accent_dark": "earth_dark",
                   "pants": "ink_dark", "feet": "earth", "dark": "ink_dark",
                   "weapon": "ink_light", "weapon_light": "ink_pale", "wood": "earth",
                   "extra": "vermilion"},
    },
    # 서생: ink_dark scholar hat over `ink` hair (a value step, so the hat is not a hair blob),
    # paper robe, navy sash, a pale-grey scroll in the off hand.
    "scholar": {
        "build": "normal", "hair": "short", "headwear": "scholar_hat", "robe": "long_robe",
        "weapon": "palm", "carry": "scroll", "expression": "neutral", "eyes": "normal",
        "colors": {"skin": "skin", "hair": "ink", "hair_light": "ink_light",
                   "cloth": "paper", "cloth_dark": "paper_dark", "cloth_light": "paper_light",
                   "trim": "ink_light", "accent": "navy", "accent_dark": "bronze_navy",
                   "pants": "ink_dark", "feet": "ink_dark",
                   "hat": "ink_dark", "hat_dark": "ink_black", "weapon_light": "ink_pale"},
    },
    # 거지: stubble, patched grey rags (K/X patches in earth_dark), rope belt, bare feet, gourd.
    "beggar": {
        "build": "normal", "hair": "short", "beard": "short", "robe": "ragged", "weapon": "palm",
        "carry": "gourd", "expression": "grin", "eyes": "narrow",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "ink_light", "cloth_dark": "ink", "cloth_light": "ink_pale",
                   "trim": "ink_light", "accent": "earth", "accent_dark": "earth_dark",
                   "pants": "ink", "feet": "skin", "dark": "earth_dark", "extra": "earth_dark",
                   "prop": "earth_light", "prop_dark": "earth"},
    },
    # 갈대밭 도적: dark-red bandana (headscarf), earth tunic, ink_dark sash, stubble, rusty jian
    # (dull ink_light blade with a rust-brown tip, wooden grip) worn at the hip.
    "bandit": {
        "build": "normal", "hair": "short", "headwear": "headscarf", "beard": "short",
        "robe": "short_tunic", "weapon": "jian", "hip_weapon": True,
        "expression": "fierce", "eyes": "narrow",
        "colors": {"skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "cloth": "earth", "cloth_dark": "earth_dark", "cloth_light": "earth_light",
                   "trim": "earth_light", "accent": "ink_dark", "accent_dark": "ink_black",
                   "pants": "earth_dark", "feet": "ink_dark", "dark": "earth_dark",
                   "hat": "vermilion_dark", "hat_dark": "ink_dark",
                   "weapon": "ink_light", "weapon_light": "earth_light", "hilt": "earth_light"},
    },
    # 청운검문 외문제자(남): short hair under a paper sect headband, jade robe with sash, iron jian.
    "disciple_m": {
        "build": "normal", "hair": "short", "headwear": "headband", "robe": "robe_sash",
        "weapon": "jian", "hip_weapon": True, "expression": "neutral", "eyes": "normal",
        "colors": {**CHEONGUN, "skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "extra": "paper", "hilt": "earth_light", "weapon": "ink_pale",
                   "weapon_light": "paper_light"},
    },
    # 청운검문 외문제자(여): bun under a paper sect headband, jade dress with a paper hem, iron jian.
    "disciple_f": {
        "build": "normal", "hair": "bun", "headwear": "headband", "robe": "dress",
        "weapon": "jian", "hip_weapon": True, "expression": "smile", "eyes": "normal",
        "colors": {**CHEONGUN, "skin": "skin", "hair": "ink_dark", "hair_light": "ink",
                   "extra": "paper", "hilt": "earth_light", "weapon": "ink_pale",
                   "weapon_light": "paper_light"},
    },
}

NAMES = tuple(GENERIC)


def build(art_root: str, preview_dir: str, cellmap_dir: str) -> List[str]:
    out_dir = os.path.join(art_root, "Characters")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(preview_dir, exist_ok=True)
    written: List[str] = []
    for name, spec in GENERIC.items():
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
