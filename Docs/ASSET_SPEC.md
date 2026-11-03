# InkPixel (수묵 픽셀 팩) — Design Spec v2

A 16px-grid, ink-wash-toned (수묵·한지) **wuxia** pixel-art asset pack for the Unity game
**강호유랑기 (GPA)**: a 2D top-down turn-based party RPG. The pack lives in this repo (`gpb`)
as a self-contained Unity project, and every file is designed to be **copied as-is into GPA's
`Assets/_Project/Art/Resources/...` folders** and consumed by GPA's existing code.

This document is the single source of truth for every generator, script and reviewer. All
names, sizes, formats and conventions below are binding. If something is unspecified, choose
the simplest option that fits these conventions.

Reference project (read-only, cloned at `/home/user/kimjuyong89/gpa`): Unity 6000.3.27f1, URP 2D,
UI Toolkit UI. Its pipeline, which we MUST match:
- `Editor/PixelArtImport.cs`: everything under `Art/` imports as Sprite, **Single**, PPU 16,
  Point filter, no mipmaps, uncompressed. (Our sheets must therefore work when the whole PNG is
  one sprite and the game slices at runtime.)
- `World/RegionView.cs`: tiles are `TileDef{sheet, cell(x,y in 16px cells from TOP-LEFT),
  size(cells), solid, ground, overlay}`; it slices with `Sprite.Create(sheet, rect, pivot(0,0),
  16)`; props larger than 1x1 are placed with the letter at their top-left cell; characters are
  `Frames(sheet)`: **4 columns = directions down, up, left, right; 4 rows = walk frames**, each
  16x16, row 0 shown when standing.
- `UI/Ui.cs`: `Strip(path, count)` slices a horizontal FX strip into `count` equal frames;
  `Tex("NinjaAdventure/Characters/{who}/Faceset")` loads a dialogue face; item icons are single
  40x40 PNGs under `Icons/` chosen by kind (`jian, dagger, robe, glove, pill, talisman, coin,
  manual, poison`), shown at 40px inside a 54px frame.
- `UI/Sound.cs`: `Resources.Load<AudioClip>("Audio/Sfx/" + name)` and `"Audio/Music/" + name`.
  Names in use: Sfx `Accept, Cancel, Move1, Slash, Hit1, Hit2, Impact, Coin, Bonus, Jump`;
  Music `Town, World, Battle`.
- GPA's design docs say the current bright pixel map clashes with its ink-wash UI; the map art
  is explicitly the next atmosphere task. So: **muted, paper-and-ink tones**, restrained accents.

---------------------------------------------------------------------------------------------

## 1. Repository layout

```
gpb/
  README.md                      Korean user guide (written last)
  LICENSE                        MIT (code) + CC0 (art/audio)
  .gitignore                     Unity gitignore (no LFS in this repo)
  Packages/manifest.json         copy of GPA's manifest minus the ink package
  ProjectSettings/ProjectVersion.txt   6000.3.27f1 (same as GPA)
  Assets/InkPixel/
    Art/
      Tiles/        ground.png, autotiles.png, nature.png, town.png  (+ <sheet>.sprites.json)
      Characters/   <name>.png (128x64) + <name>_face.png (32x32) + <name>.sprites.json
      Icons/        <icon>.png (40x40, one file per icon) + icons_sheet.png (+json, for slicing users)
      Icons/Mini/   <icon>.png (16x16)
      FX/           <Name>.png horizontal strips (+ <Name>.sprites.json with stripFrames/stripFps)
      UI/           Status/<name>.png (16x16), Markers/<name>.png (16x16), Frames/<name>.png, ui_sheet.png (+json)
    Audio/
      Sfx/          <Name>.wav   (PascalCase, 44100 Hz, 16-bit, mono)
      Music/        <Name>.ogg   (PascalCase, 44100 Hz, stereo, OGG Vorbis, seamless loop)
    Scripts/
      Runtime/      InkPixel.* demo + helpers (see §8)
      Editor/       importer, sidecar slicer, animation/tile builders, demo scene builder
    Generated/      created inside Unity by the editor tools (only .gitkeep committed)
  Integration/GPA/  (outside Assets so gpb does not compile it) GpaInkPixelTools.cs, tiledefs_*.src.json
                    + resolved tiledefs_*.json, layouts/, icon_map.md, README_GPA.md
  Tools/
    pixelgen/       Python generators for all art (pixelkit.py + gen_*.py + build_all.py)
    audiogen/       Python generators for all audio (audiokit.py + gen_*.py + build_all.py)
  Docs/
    ASSET_SPEC.md   this file
    previews/       upscaled, labelled contact sheets (PNG) for review and README
    cellmaps/       <sheet>_cellmap.png (grid + cell coordinates) and <sheet>.md tables
```

Every PNG sheet has a sidecar `<basename>.sprites.json` (§3). Never hand-edit PNGs: edit the
Python generator and rerun `python3 Tools/pixelgen/build_all.py`. Generators are deterministic
(fixed seeds) — running twice yields byte-identical output.

---------------------------------------------------------------------------------------------

## 2. Art conventions

- Grid: 16x16 px cells. PPU = 16 (1 cell = 1 Unity unit). Every tile/prop sprite is a whole
  number of cells and sits on the 16px grid of its sheet (GPA addresses them by cell).
- Palette: exactly the 32 colors in §2.1 plus full transparency. No other colors, no
  anti-aliasing, no partial alpha (verified by script).
- Mood: 수묵·한지. Paper-cream lights, ink-dark darks, desaturated greens/browns, sparse
  accents in vermilion (주묵) and jade (옥). No saturated cartoon colors. Think ink painting
  translated to pixels: strong value structure, few hues.
- Outlines: 1px `ink_black` outline around characters, props, items, FX, icons. Tiles (ground,
  autotiles) have NO outline. Selective lighter outlines allowed only with palette colors.
- Light from top-left: highlight top/left, shade bottom/right.
- Characters: no baked ground shadow. Items/icons: centered, iconic, 2–3 tone ramps.
- Directional art: "down" faces the camera, "up" shows the back, "left"/"right" side views
  (right may be a mirror of left). Both stored explicitly.
- East-Asian wuxia setting: robes (도포/장포) with sashes, topknots and hairpins, straw hats,
  jian swords, dao sabres, tiled (기와) and thatched (초가) roofs, paifang gates, paper lanterns,
  bamboo, pine, willow, reeds, river docks, stone lanterns, wells, cloth banners (酒旗).

### 2.1 Palette (32 colors)

| name            | hex     | use |
|-----------------|---------|-----|
| ink_black       | #1e1b18 | outlines, darkest (GPA 먹) |
| ink_dark        | #3a342e | deep shade, hair, dark cloth |
| ink             | #5c554c | mid grey-brown, stone shade, roof tiles |
| ink_light       | #8a8378 | stone, grey cloth, roof light |
| ink_pale        | #b5ad9e | pale stone, bone, light grey |
| paper_dark      | #d6c6a4 | aged paper, sand shade, straw |
| paper           | #e9dec6 | paper, sand, light walls (GPA 한지) |
| paper_light     | #f4ecdc | highlights, white cloth, foam, eyes |
| vermilion_dark  | #6e1512 | blood, red shade |
| vermilion       | #9e241c | accents, hearts, seals, red cloth (GPA 주묵) |
| vermilion_light | #c4473a | red highlight, lanterns, flowers |
| jade_dark       | #1c5c4e | sect robes shade, deep foliage (GPA 옥) |
| jade            | #3f8a73 | jade, sect cloth, teal foliage |
| jade_light      | #7fb79b | jade highlight, pale teal |
| bronze_navy     | #18243c | night, black cloth (흑사방), deep shade (GPA 청동 남색) |
| navy            | #2f4466 | blue cloth, slate, deep water shade |
| steel           | #5a7391 | steel, blue highlight, distant mountains |
| moss_dark       | #35502f | grass shade, pine shade |
| moss            | #5a7a45 | grass, foliage |
| moss_light      | #88a05a | grass light, leaves |
| moss_pale       | #b4c278 | grass highlight, bamboo light |
| earth_dark      | #4a3324 | wood shade, dirt shade, bark |
| earth           | #76533a | wood, dirt, leather |
| earth_light     | #a6805a | wood light, road |
| sand            | #cfae7e | tan, rope, straw light, skin shade |
| skin            | #e6c39b | skin |
| gold            | #c9a24a | gold, brass, coins, lantern glow |
| gold_light      | #e8d690 | gold highlight, candle light, elixir glow |
| water_deep      | #2d5b73 | river deep |
| water           | #4f8aa3 | river |
| water_light     | #8dbfcc | river highlight, ripples |
| plum            | #5b3a6b | poison, inner-demon, purple cloth |

Python: `Tools/pixelgen/palette.py` exposes `PALETTE` (ordered dict name->hex), `COLORS`,
`NAME_TO_RGB`, `RGB_TO_NAME`. All drawing uses palette names.

### 2.2 Naming

Sheet and sprite names: lowercase snake_case ASCII. Sprite names are globally unique thanks to
the sheet-name prefix: `<sheet>_<descriptor>[_<dir>][_<frame>]`. Directions: `down, up, left,
right`. Frames 0-based. Blob tiles: `_m<mask>` (decimal), animated blob frames `_f<frame>`.
Files that GPA loads by name (icons, FX strips, audio) use the exact names in §5–§6 (icons
lowercase, FX and audio PascalCase).

### 2.3 Sheet layout

Sprites are packed left-to-right, top-to-bottom in rows of equal height; a new row starts when
the next sprite does not fit in the max width (512 px) or has a different height. For tile
sheets every sprite is a multiple of 16 px, so every sprite lands on the 16px grid. The PNG is
RGBA 8-bit, size rounded up to a multiple of 16. Each tile sheet gets a cell map
(`Docs/cellmaps/<sheet>_cellmap.png` at 3x with grid lines and `x,y` cell labels, plus
`Docs/cellmaps/<sheet>.md` listing name → cell, size, solid, overlay, ground).

---------------------------------------------------------------------------------------------

## 3. Sidecar JSON (`<basename>.sprites.json`) — read by Unity via JsonUtility

Flat schema (no dictionaries, no nested arrays of arrays). `x`,`y` are from the TOP-LEFT of
the PNG; the importer converts: `unityY = textureHeight - y - h`.

```json
{
  "version": 2,
  "sheet": "town",
  "kind": "tiles",                 // tiles | autotiles | character | icons | fx | ui | face
  "pixelsPerUnit": 16,
  "defaultPivotX": 0.5, "defaultPivotY": 0.0,
  "cellSize": 16,
  "stripFrames": 0, "stripFps": 0,      // fx strips only (frames in the strip, playback fps)
  "sprites": [
    { "name": "town_house_small_a", "x": 0, "y": 0, "w": 48, "h": 48,
      "pivotX": 0.5, "pivotY": 0.0,
      "borderL": 0, "borderB": 0, "borderR": 0, "borderT": 0,
      "cellX": 0, "cellY": 0, "cellW": 3, "cellH": 3,
      "solid": true, "overlay": false, "ground": "ground_grass_0", "tags": "building,house" }
  ],
  "animations": [
    { "name": "walk_down", "state": "walk", "direction": "down", "fps": 8, "loop": true,
      "frames": ["hero_1_walk_down_0", "hero_1_walk_down_1", "hero_1_walk_down_2", "hero_1_walk_down_3"] }
  ],
  "tiles": [ { "name": "GrassA", "sprite": "ground_grass_0", "collider": "none" } ],
  "tileRules": [ { "ruleTile": "Road", "sprite": "autotiles_road_m255", "mask": 255, "animFrames": [], "animFps": 0 } ],
  "ruleTileDefaults": [ { "ruleTile": "Road", "defaultSprite": "autotiles_road_m255", "collider": "none" } ]
}
```

Rules:
- `sprites` always present; other arrays present but may be empty. `cellX/Y/W/H` are filled
  for every sprite on a tile sheet (`x/16` etc.); for other kinds they may be 0.
- `solid`/`overlay`/`ground` are the suggested GPA `TileDef` values (`ground` = name of the
  1x1 ground sprite to draw under a prop, "" if none). `tags` is a free comma list.
- `animations[].name` unique per sheet; Unity asset name `<sheet>_<name>`; `direction` is ""
  for non-directional clips.
- `collider` ∈ `none | sprite | grid`.
- Blob mask convention (§4): N=1, NE=2, E=4, SE=8, S=16, SW=32, W=64, NW=128; a corner bit is
  set only when both adjacent edges are set; all 47 canonical masks present per ruleTile.

---------------------------------------------------------------------------------------------

## 4. Blob (47-tile) autotiles

Tiles are built from four 8x8 quadrants (TL, TR, BL, BR). For a quadrant, look at its two
adjacent edges (e.g. TL: N and W) and its diagonal corner (NW):
- both edges absent → `corner_out`; exactly one edge present → `edge_h` when the missing edge
  is N/S, `edge_v` when it is W/E; both present, corner absent → `corner_in`; all present →
  `inner`.

`pixelkit.blob47(draw_quadrant, size=16, frames=1, rng=None)` calls
`draw_quadrant(quadrant_index, kind, frame, rng)` (0..3 = TL,TR,BL,BR) and assembles all 47
canonical masks → `[(mask, [Canvas per frame]), ...]`. The quadrant drawer draws the quadrant in
its final orientation and keeps the border at a fixed inset so variants join seamlessly.

Autotile sets (sheet `autotiles`, kind `autotiles`), each a RuleTile with the given name:
`Road` (packed-earth road over grass), `Water` (river over bank, 4 animated frames, collider
grid), `Reeds` (갈대밭 reed bed over grass, overlay, encounter zone look), `Cliff` (mountain
cliff top over grass, collider grid; S-facing edges show a rock face), `CaveWall` (cave rock
wall over cave floor, collider grid), `Courtyard` (flagstone courtyard over grass).

---------------------------------------------------------------------------------------------

## 5. Art inventory (binding names)

### 5.1 Characters (`Art/Characters/`), kind `character`
File `<name>.png` is **128x64**: columns 0–3 = `walk` for directions down, up, left, right;
rows 0–3 = frames 0..3 where **row 0 is the neutral standing pose** (feet together, also used
as a walk contact frame; GPA shows row 0 when idle and cycles rows 0–3 at 8 fps when walking).
Rows 1–3: step-left, pass, step-right with a 1px head bob on rows 1 and 3. Columns 4–7 =
`attack` for down, up, left, right: rows 0–2 = wind-up, strike (weapon extended toward the
facing direction), recover; **row 3 = `hurt` pose** for that direction. Pivot (0.5, 0).
Sprite names `<name>_walk_<dir>_<i>`, `<name>_attack_<dir>_<i>`, `<name>_hurt_<dir>`.
Animations: `walk_<dir>` (8 fps, loop), `attack_<dir>` (12 fps, no loop), `idle_<dir>` (1 frame
= walk_<dir>_0), `hurt_<dir>` (1 frame). File `<name>_face.png` is a **32x32** bust (head and
shoulders, matching colors, 1px outline, transparent background) with sidecar kind `face` and
one sprite `<name>_face`.

Bodies are 16x16: ~13–15 px tall, head ~6 px with 1px eyes (2 px apart), topknot/hair
readable, robe to the knee or ankle, sash at the waist in an accent color. Unarmed characters
attack with a palm strike; weapon users show their weapon only in attack frames (and a hilt at
the hip otherwise if room allows).

Heroes (character creation faces 1–4; ×3 outfits via palette swap):
`hero_1` (young man, black topknot, plain traveler robe paper/earth, sand sash),
`hero_2` (young man, brown hair tied back, slightly taller, grey robe),
`hero_3` (young woman, black hair with vermilion ribbon, pale robe),
`hero_4` (young woman, brown braid, jade-trim robe).
Outfits: `<hero>` (traveler), `<hero>_cheongun` (청운도복: jade/jade_dark robe, paper trim),
`<hero>_heuksa` (흑사흑의: bronze_navy/ink_dark robe, vermilion sash). 12 sheets + 4 faces
(faces only for the base outfit; outfits reuse the base face).

Companions (9): `soyuk` (소육: small boy pickpocket, ragged ink_dark clothes, cap, dagger),
`seokdu` (석두: big bare-fisted brawler, bare arms, headband, earth vest),
`unhak` (운학: wandering swordsman, ink_pale/paper robe, jian at hip),
`yeona` (연아: slingshot girl, short, braid, sand/moss clothes, sling in attack),
`baekseolhwa` (백설화: herbalist/medic, white (paper_light) robe, hair bun, needles — attack is
a needle throw),
`hongryeon` (홍련: swordswoman in vermilion, dao sabre, high ponytail),
`mukhyang` (묵향: scholar's daughter, ink_dark/plum robe, hairpin, ink-needle throw),
`yusoso` (유소소: cook, apron over earth dress, cleaver),
`neungso` (능소: sect disciple girl, jade robe, broom-sword).

Named NPCs (13): `yun_baeksan` (윤백산: elderly sect master, white (paper_light) beard and
hair, jade_dark robe), `go_jinak` (고진악: senior disciple, navy/jade robe, sharp look, jian),
`tak_ung` (탁웅: gang boss, burly, bronze_navy coat, beard, dao), `baek_yeorin` (백여린:
strategist, ink_dark robe, folding fan), `boatman` (구씨: old boatman, straw hat, pole),
`silk_merchant` (비단 장수: merchant with a silk bolt, plum accents), `waiter` (점소이: inn
waiter, paper shirt, towel on shoulder), `merchant` (장터 상인: market vendor, sand/earth,
abacus), `heuksa_thug` (흑사방 졸개: black outfit, headscarf, dao), `heuksa_courier` (연락책:
grey hooded), `warehouse_keeper` (창고지기: burly, black, key ring), `hermit` (은둔 노인: long
white hair, ragged paper robe, bare feet), `bandit_boss` (도적 두목: scarred, fur collar, dao).

Generic NPCs & enemies (12): `villager_m`, `villager_f`, `old_woman`, `child_m`, `child_f`,
`monk` (grey robe, shaved head, staff), `guard` (관병: lamellar vest, spear), `scholar` (서생:
ink_dark hat, paper robe, scroll), `beggar` (거지: patched clothes, gourd), `bandit` (갈대밭
도적: bandana, rusty jian), `disciple_m`, `disciple_f` (청운검문 outer disciples, jade robe).

Animals (13, same format; attack = bite/pounce/peck): `wolf`, `tiger`, `bear`, `deer`, `egret`
(백로: white egret, standing/stepping, flight not needed), `dog`, `chicken`, `boar`, `monkey`,
`snake`, `fox`, `horse`, `raccoon` (너구리).

Total: 12 + 9 + 13 + 12 + 13 = 59 sheets, 51 faces (outfit variants share faces).

### 5.2 Tiles (`Art/Tiles/`)
`ground` (kind `tiles`, all 1x1, no outline, seamless, `solid` false unless noted):
`ground_grass_0..3` (plain grass, subtle 2-tone, variants differ in a few specks),
`ground_grass_flowers_0..1` (tiny paper/vermilion dots), `ground_grass_dark_0..1` (shaded
grass for forest), `ground_dirt_0..1`, `ground_road_0..1` (packed earth with wheel ruts),
`ground_sand_0..1` (riverbank), `ground_mud`, `ground_stone_0..1` (flagstone courtyard),
`ground_cobble_0..1`, `ground_planks_0..1` (dock/floor planks, horizontal), `ground_planks_v`,
`ground_snow_0..1`, `ground_rock_0..1` (mountain rock floor), `ground_cave_0..1` (cave floor),
`ground_moss`, `ground_leaves` (fallen leaves on dirt), `ground_water_0..3` (plain river water,
4 animation frames; `solid` true), `ground_water_deep_0..3` (`solid` true), `ground_shallow`
(wadeable water, overlay look), `ground_bridge_h`, `ground_bridge_v` (plank bridge over water,
walkable), `ground_bridge_rail_n`, `ground_bridge_rail_s` (rail overlays), `ground_stepping_stone`,
`ground_void` (ink_black), `ground_tatami_0..1`, `ground_wood_floor_0..1` (interiors).
Also `tiles` entries for Tilemap users (one Tile per sprite; names PascalCase e.g. `GrassA`).

`autotiles` (kind `autotiles`): the six blob sets of §4, names `autotiles_<set>_m<mask>[_f<frame>]`,
`ruleTileDefaults` for each, `tileRules` complete.

`nature` (kind `tiles`, props with 1px outline, pivot (0.5,0), `solid` true unless noted,
`ground` = `ground_grass_0`): `nature_pine_a`, `nature_pine_b` (2x2, ink-painting pine: dark
layered canopy), `nature_tree_round` (2x2 broadleaf), `nature_willow` (2x2, drooping, riverside),
`nature_plum` (2x2, blossoms in vermilion_light/paper_light), `nature_dead_tree` (2x2),
`nature_bamboo_a` (1x2), `nature_bamboo_b` (2x2 cluster), `nature_mountain_a`, `nature_mountain_b`
(2x2 forested hills for the overworld, blue-grey distant look using steel/navy), `nature_mountain_big`
(3x3 peak with mist), `nature_bush_a`, `nature_bush_b` (1x1), `nature_reed_a`, `nature_reed_b`
(1x1, `overlay` true, `solid` false: reed tufts for 갈대밭), `nature_rock_a`, `nature_rock_b` (1x1),
`nature_rock_wide` (2x1), `nature_boulder` (2x2), `nature_flowers_a..c` (1x1 overlay, not solid),
`nature_stump`, `nature_log` (2x1), `nature_mushrooms` (1x1 overlay), `nature_herb_a`, `nature_herb_b`
(1x1 overlay, 약초 gathering plant), `nature_berry_bush`, `nature_waterfall_0..1` (1x2, two
animation frames), `nature_cave_entrance` (2x2, dark opening in rock), `nature_hot_spring` (2x2,
steam), `nature_stone_steps` (1x1 walkable, mountain path), `nature_cliff_face` (1x1 solid rock
face piece), `nature_shrine_stone` (1x1, roadside stone marker), `nature_spirit_tree` (3x3, old
tree with ribbons), `nature_grave` (1x1, mound with marker), `nature_tent` (2x2), and 1x1 variants used by GPA's
mountain map (its props are single cells): `nature_hut` (움막 lean-to shelter), `nature_dead_tree_small`,
`nature_stream` (계곡: rocky stream segment, solid), `nature_waterfall_small` (single-cell fall),
`nature_herb_c` (산나물 third variant).

`town` (kind `tiles`, props, 1px outline, pivot (0.5,0), `solid` true unless noted,
`ground` = `ground_grass_0`): `town_house_tile_a`, `town_house_tile_b` (3x3, grey 기와 roof,
paper walls, earth timber, door), `town_house_thatch_a`, `town_house_thatch_b` (3x3, 초가 straw
roof), `town_house_large` (4x3, tiled roof, two windows), `town_inn` (5x4, 객잔 with a hanging
酒 banner in vermilion and lanterns), `town_sect_gate` (4x3, paifang gate with jade-dark beams
and a name board), `town_sect_hall` (5x4, dignified hall, jade trim), `town_warehouse` (4x3,
plain, barred door), `town_shrine` (3x3, 사당 small shrine, red door), `town_temple` (4x3, with
bell), `town_ruin_a`, `town_ruin_b` (3x3, burnt/collapsed house, ink_dark beams — for 백로진의 밤),
`town_stall_a`, `town_stall_b` (2x2, market stalls with cloth awnings: vermilion and navy),
`town_well` (1x1), `town_stone_lantern` (1x2), `town_lantern_post` (1x2, red paper lantern),
`town_fence_h`, `town_fence_v`, `town_fence_post`, `town_fence_end_l`, `town_fence_end_r` (1x1
wood fence), `town_wall_h`, `town_wall_v`, `town_wall_corner_nw/ne/sw/se` (1x1 stone wall with
tile cap), `town_wall_gate` (2x2, open gateway in a wall; walkable centre is NOT possible with a
single TileDef — keep as decoration + note), `town_sign` (1x1), `town_barrel`, `town_crate`,
`town_jar_a`, `town_jar_b` (항아리), `town_hay`, `town_cart` (2x2), `town_bench` (1x1), `town_mat`
(1x1 overlay, not solid), `town_dock_plank` (1x1 walkable, `solid` false, `ground` ""),
`town_dock_end` (1x1 walkable), `town_dock_post` (1x1 solid), `town_boat` (2x1), `town_boat_big`
(3x2), `town_banner_sect` (1x2, jade), `town_banner_heuksa` (1x2, bronze_navy with a black snake
mark), `town_torch` (1x1), `town_gate_door` (1x2 closed door), `town_steps` (1x1 walkable),
`town_tombstone_a`, `town_tombstone_b` (1x1), `town_statue` (1x2), `town_bell_tower` (2x3),
`town_bridge_stone_h` (1x1 walkable stone bridge piece), `town_pavilion` (3x3, open pavilion),
and GPA-footprint variants so existing layouts keep their letters: `town_sect_gate_small` (2x2
paifang, `ground` = `ground_road_0`), `town_inn_small` (3x3 inn with banner), `town_sect_hall_small`
(4x3 sect hall), `town_heuksa_den` (3x3, dark-roofed gang hideout with the black-snake banner),
`town_house_large_thatch` (4x3 thatched large house).

### 5.3 Icons (`Art/Icons/`), kind `icons`
40x40 single PNGs, transparent, 1px outline, Jianghu-Lite-like legibility, drawn large within
the cell (~32 px). The nine GPA kind icons MUST exist with these exact names: `jian`, `dagger`,
`robe`, `glove`, `pill`, `talisman`, `coin`, `manual`, `poison`. Full list (file name → item):
weapons `jian_rusty` (녹슨 철검), `jian_iron` (철검), `jian_steel` (정강검), `jian_cheongun`
(청운제식검, jade hilt), `dagger` (단도), `dagger_heuksa` (흑사단검), `dao` (도), `cleaver`
(부엌칼), `sling` (투석), `staff`, `fist_wraps` (권대);
armor `robe_hemp` (베옷), `vest_leather` (가죽조끼), `robe_cheongun` (청운도복), `robe_heuksa`
(흑사흑의), `armor_soft` (연갑), `robe` (generic);
shoes `straw_sandals` (짚신), `leather_boots` (가죽장화), `cloud_shoes` (운리화);
gloves `glove` (generic), `cloth_wraps` (무명 권대), `leather_gloves` (가죽 장갑);
accessories `lucky_coin` (행운 엽전), `jade_pendant` (옥패), `jade_pendant_old` (낡은 옥패),
`jade_pendant_cheongun` (청운옥패), `sachet` (해독 향낭), `talisman` (지혈 부적), `poison_pouch`
(흑사독낭);
consumables `salve` (금창약, small jar), `pill` (generic 환), `pill_qi` (회기단, white),
`powder` (지혈산, paper packet), `pill_antidote` (해독단, green), `pill_clear` (청심환, blue),
`pill_vigor` (활력환, orange);
elixirs (glowing) `elixir_red` (천력환), `elixir_purple` (자하단), `elixir_blue` (비연단),
`elixir_orange` (호골단), `elixir_green` (청명단), `elixir_white` (소환단), `elixir_gold` (대환단);
manuals `manual` (generic 비급), `manual_dao` (오호단문도), `manual_palm` (철사장), `manual_fist`
(맹호권), `manual_kick` (선풍각), `scroll_mind` (심법 scroll);
misc `coin` (엽전), `coin_stack`, `ledger` (장부), `letter`, `map`, `key`, `lantern`, `rice_soup`
(국밥), `wine_jug`, `tea`, `herb` (약초), `mushroom`, `bamboo_shoot`, `fish`, `meat`, `rope`,
`flint`, `gourd` (호리병), `bandage`, `needle` (침), `ink_brush`, `stone`, `fan`, `poison`
(generic 독 bottle), `silk` (비단), `basket`.
Also `Icons/Mini/` 16x16: `coin`, `hp`, `qi` (내력), `fatigue`, `hunger`, `warmth`, `qi_orb`.
A contact sheet `icons_sheet.png` (+ sidecar, kind `icons`) contains all 40x40 icons for
slicing users.

### 5.4 FX strips (`Art/FX/`), kind `fx`
`<Name>.png` = horizontal strip of N frames, each **48x48**, pivot center, 1px outline where it
reads well, palette only (fire = gold/gold_light/vermilion_light; qi = jade_light/paper_light;
poison = plum/jade). `stripFrames` = N, `stripFps` as given. Names:
`SpriteSheetSlash01` (5, 16 fps — drop-in for GPA's current file: diagonal slash arc),
`Slash` (5, 16), `SlashHeavy` (5, 14, 도법 wide arc), `Stab` (4, 16), `Punch` (4, 16, 권법 impact
ring), `Palm` (5, 14, 장법 outward wave), `Kick` (4, 16), `Stone` (4, 12, 투석 stone with motion
lines, faces right), `Needle` (4, 16, 암기 needle streak, faces right), `Poison` (6, 8, bubbling
cloud), `Bleed` (4, 10, red drops), `Heal` (6, 10, rising paper-light motes), `Qi` (6, 10, 운기
swirl), `Guard` (4, 12, jade ring), `Dodge` (4, 12, afterimage wisps), `Crit` (5, 16, big burst),
`Acupoint` (4, 16, small dots converging), `Demon` (6, 8, 심마 dark plum aura), `Breakthrough`
(8, 10, 경지 돌파 rising light + ring), `Burst` (5, 14, 절초 flash), `Dust` (4, 12), `Splash` (4,
12), `Smoke` (5, 8), `Spark` (4, 16), `Death` (5, 8, body dissolving to ink smoke), `Arrow` (1,
0, projectile facing right), `Shadow` (1, 0, dithered ellipse), `LevelUp` (6, 12).

### 5.5 UI (`Art/UI/`), kind `ui`
`Status/<name>.png` 16x16 status icons (readable at 1x, ink outline, one accent): `bleed`,
`poison`, `acupoint` (점혈), `injury` (내상), `deviation` (주화입마), `guard`, `dodge`,
`momentum` (기세), `ultimate` (절초), `fatigue`, `hunger`, `cold`, `warmth`, `buff`, `debuff`,
`stun`, `heal`, `attack_up`, `defense_up`, `speed_up`.
`Markers/<name>.png` 16x16 map markers: `town`, `sect`, `gate`, `bridge`, `cave`, `mountain`,
`encounter`, `quest`, `quest_done`, `player`, `companion`, `exit`, `shop`, `inn`, `dock`, `shrine`.
`Frames/`: `panel_paper` (24x24 9-slice border 8, hanji with ink line), `panel_ink` (24x24
dark), `bar_frame_jade`, `bar_frame_bronze`, `bar_frame_vermilion` (48x8 9-slice border 3),
`bar_fill_red`, `bar_fill_blue`, `bar_fill_green`, `bar_fill_gold` (48x8 border 2),
`slot` / `slot_selected` (20x20 border 4), `cursor` (16x16), `arrow_down_0..1` (dialogue
blink), `select_frame` (20x20 border 4, vermilion corners), `seal` (16x16 red seal stamp).
All UI sprites also packed in `ui_sheet.png` (+ sidecar with borders).

---------------------------------------------------------------------------------------------

## 6. Audio (`Audio/`)

Style: East-Asian / wuxia chiptune-plus: plucked zither-like tones (fast-decay pulse/triangle
with harmonics), bamboo-flute-like leads (triangle/sine with breath noise and vibrato), taiko/
buk drums (low sine thumps), gong and temple-bell hits (inharmonic bell synthesis), wood block
(목탁) clicks, pentatonic scales (궁상각치우 / minor pentatonic for tension).

SFX: WAV 44100 Hz 16-bit mono, peak ≤ -1 dBFS, no DC, ≤ 2.0 s, trimmed, 2 ms fades. PascalCase
names. GPA's ten MUST exist: `Accept`, `Cancel`, `Move1`, `Slash`, `Hit1`, `Hit2`, `Impact`,
`Coin`, `Bonus`, `Jump`. Extras: `Hover`, `Open`, `Close`, `Error`, `Talk` (text blip), `Buy`,
`Sell`, `Equip`, `Unequip`, `Pill`, `Drink`, `Eat`, `Read`, `Heal`, `Poison`, `Bleed`,
`Acupoint`, `Guard`, `Dodge`, `Crit`, `Stab`, `Punch`, `Palm`, `Kick`, `Stone`, `Needle`, `Qi`
(운기 hum swell), `Burst` (절초), `Breakthrough` (gong + rising shimmer), `Deviation` (주화입마
dissonant), `Demon` (심마), `Victory` (short fanfare with gong), `Defeat`, `Step1`, `Step2`,
`Step3` (grass), `StepStone1`, `StepStone2`, `StepWater`, `Run`, `Leap` (경공), `Land`,
`Rhythm1`, `Rhythm2`, `Rhythm3`, `Rhythm4` (초식 연마 four lanes: wood blocks at four pitches),
`RhythmMiss`, `RhythmPerfect`, `Gong`, `Drum`, `Bell` (temple bell), `Wood` (목탁), `Bird`
(egret call), `Wind`, `Fire`, `Chop`, `Pick` (herb), `Fish`, `Door`, `Chest`, `Save`, `Sleep`,
`Night` (crickets, 1.5 s), `Rain` (1.5 s), `Thunder`, `Horse`, `Wolf`, `Tiger`.

Music: OGG Vorbis q6, 44100 Hz stereo, seamless loops of whole bars (length exactly
bars×beats×60/BPM×SR samples, no end fade; non-loop stings may fade). GPA's three MUST exist:
`Town` (백로진: gentle, ~92 BPM, major pentatonic, zither-pluck lead, soft drum, 32 bars),
`World` (강호: traveling, ~110 BPM, flute-like lead over plucked bass, light drums, 32 bars),
`Battle` (~150 BPM, driving taiko, aggressive plucked riff, minor pentatonic, 32 bars).
Extras: `Mountain` (무명산: sparse, ~70 BPM, flute, wind-like pad, 32 bars), `Cave` (eerie
drones, bell hits, ~80 BPM, 32 bars), `Sect` (청운검문: dignified, ~84 BPM, 32 bars), `Dark`
(흑사방: low tense, ~100 BPM, 32 bars), `Night` (백로진의 밤: tragic slow minor, ~66 BPM, 32
bars), `Demon` (심마: dissonant, ~120 BPM, 16 bars), `Title` (calm, ~76 BPM, 32 bars),
`Victory` (sting ~5 s, non-loop), `GameOver` (sting ~8 s, non-loop).

All synthesis via numpy, deterministic. WAV masters for music are NOT committed.

---------------------------------------------------------------------------------------------

## 7. C# conventions

- No assembly definitions. Runtime under `Scripts/Runtime/**`, editor under `Scripts/Editor/**`.
- Namespaces: `InkPixel`, `InkPixel.Demo`, `InkPixel.EditorTools`.
- C# 9, block namespaces, no init-only setters, no records. Unity 6000.3 APIs; avoid obsolete
  ones (`FindFirstObjectByType`, `linearVelocity`). Input only via the new Input System
  (`UnityEngine.InputSystem`, package present in the manifest) wrapped in `#if ENABLE_INPUT_SYSTEM`
  with a legacy `Input` fallback.
- Sprite slicing in the editor uses `UnityEditor.U2D.Sprites.ISpriteEditorDataProvider`, never
  `TextureImporter.spritesheet`. Sprite IDs deterministic (MD5 of the sprite name → GUID).
- Editor tools under menu `Tools/InkPixel/...`, generate into `Assets/InkPixel/Generated/...`,
  idempotent.
- The runtime demo mirrors GPA's approach so the pack is proven compatible: slice at runtime
  with `Sprite.Create(texture, rect, Vector2.zero, 16)`, 4x4 walk frames, strips via equal
  division, Y-sorting by `1000 - round(y*10)`.
- `InkPixelPaths`: static string constants for every folder in §1.

### 7.1 Editor tools (`Scripts/Editor/`)
`InkPixelImporter` (AssetPostprocessor: Sprite, PPU 16, Point, uncompressed, no mipmaps,
alphaIsTransparency, FullRect, no physics shape; `Multiple` + sidecar slicing when a sidecar
exists, else `Single`), `SidecarData`, `SpriteSlicer`, `AnimationBuilder` (SpriteAnimation
assets `Generated/Animations/<sheet>_<anim>.asset`), `TileBuilder` (`Generated/Tiles/<Name>.asset`
Tiles and RuleTiles from `autotiles`/`ground` sidecars, verified against the 2D Tilemap Extras
source), `DemoSceneBuilder` (`Generated/Scenes/InkPixelDemo.unity`), `InkPixelMenu` (Setup All).

### 7.2 Runtime (`Scripts/Runtime/`)
`InkPixelPaths`, `SpriteAnimation` (SO: frames, fps, loop), `SpriteAnimator`,
`CharacterSheet` (static: `Frames(Texture2D)` → `Sprite[4,4]` walk, `AttackFrames` → `Sprite[4,3]`,
`Hurt` → `Sprite[4]`, cached), `StripSheet` (static: `Strip(Texture2D, count)`),
`TileDefs` (ScriptableObject list of `{key, sheet, cell, size, solid, ground, overlay}` +
`FromJson`), `RegionViewer` (MonoBehaviour: `layout` TextAsset or string, `TileDefs`, player
sheet; builds SpriteRenderers like GPA's RegionView; grid walking with WASD/arrows, run on
Shift, step SFX, talk key shows the face of the NPC in front), `GridWalker`, `StripPlayer`
(loops a strip on a SpriteRenderer), `GalleryController` (cycles through every character sheet
and FX strip, plays SFX by name, switches music; on-screen labels via `UnityEngine.UI.Text`
with the built-in LegacyRuntime font), `SimpleAudio` (clip lists → `Play(name)` / `Music(name)`).

### 7.3 GPA integration (`Integration/GPA/`, repo root — NOT under Assets)
`GpaInkPixelTools.cs` (already written) — an editor script meant to be copied into GPA
(`Assets/_Project/Editor/`). Menus `GPA/InkPixel/1. InkPixel 에셋 복사...` (copies Art/Audio into
GPA's Resources folders) and `GPA/InkPixel/2. TileDefs JSON 적용 (선택한 RegionData)`:
reads a `tiledefs_<region>.json` (`{"tiles":[{"key":".","sheet":"Assets/_Project/Art/Resources/InkPixel/Tiles/ground.png","cellX":0,"cellY":0,"sizeX":1,"sizeY":1,"solid":false,"ground":".","overlay":false,"portal":"","encounterNode":""}],
"npcs":[{"key":"p","sheet":"Assets/.../Characters/soyuk.png"}]}`) and fills the selected
`GPA.World.RegionData` (`tiles`: List<TileDef>{key, sheet, cell, size, solid, ground, overlay,
portal, encounterNode}; `npcs`: List<NpcDef>{key, name, sheet, knot, prop, propCell} — only
`sheet` is replaced for existing keys) using `AssetDatabase.LoadAssetAtPath<Texture2D>`,
`Undo.RecordObject`, `EditorUtility.SetDirty`. Ships with `tiledefs_<region>.src.json` (sprite
names) that `Tools/gpa_sim/resolve_tiledefs.py` turns into `tiledefs_<region>.json` (cell coordinates)
for GPA's three regions, GPA's layouts as text under `layouts/`, `Tools/gpa_sim/render_region.py`
(a Python simulation of RegionView used for verification previews), `icon_map.md` and `README_GPA.md` (Korean).

---------------------------------------------------------------------------------------------

## 8. Python toolkit API — binding surface

`Tools/pixelgen/pixelkit.py`:
```python
from pixelkit import Canvas, Sheet, blob47, PALETTE, Rng, verify_palette
c = Canvas(16, 16)                        # RGBA, transparent; (0,0) top-left
c.set(x, y, "moss"); c.get(x, y) -> (r,g,b,a)
c.rect(x, y, w, h, color, fill=True); c.line(x0, y0, x1, y1, color)
c.ellipse(cx, cy, rx, ry, color, fill=True); c.circle(cx, cy, r, color, fill=True)
c.fill_points(points, color); c.blit(src, x, y, flip_x=False, flip_y=False)
c.flipped_x() / c.flipped_y() / c.rotated(k)
c.outlined(color="ink_black", diagonal=False); c.recolored({"moss": "jade"})
c.shifted(dx, dy) / c.cropped(x, y, w, h) / c.scaled(k)
c.paste_pattern(rows, x, y, colormap); Canvas.from_pattern(rows, colormap)   # '.' = transparent
c.stamp(text, x, y, color)                 # tiny 3x5 debug font
c.to_image() -> PIL.Image ; c.save(path)
rng = Rng(seed)                            # choice/randint/random/shuffle

s = Sheet("town", kind="tiles", pivot=(0.5, 0.0), max_width=512, cell_size=16)
s.add("town_well", canvas, pivot=None, border=None, solid=True, overlay=False, ground="ground_grass_0", tags="")
s.add_animation("walk_down", frames, fps=8, loop=True, state="walk", direction="down")
s.add_tile("GrassA", "ground_grass_0", collider="none")
s.add_tile_rule("Road", "autotiles_road_m255", mask=255, anim_frames=None, anim_fps=0)
s.set_rule_tile_default("Road", "autotiles_road_m255", collider="none")
s.set_strip(frames=5, fps=16)              # fx strips: sprites are laid out in ONE row, in order
s.save(out_dir)                            # <out_dir>/<sheet>.png + <sheet>.sprites.json
s.save_singles(out_dir)                    # one PNG per sprite named <descriptor>.png (icons, status, markers)
s.preview(path, scale=4, labels=True); s.preview_group(path, prefix, scale=8)
s.cellmap(png_path, md_path, scale=3)      # grid + "x,y" labels + markdown table (tile sheets)

blob47(draw_quadrant, size=16, frames=1, rng=None) -> [(mask, [Canvas...]), ...]
MASK_N..MASK_NW, CANONICAL_MASKS ; verify_palette(png_path) -> offending pixels
character_sheet(name, walk, attack, hurt) -> Sheet      # helper that lays out the 128x64 format
   # walk: {dir: [4 Canvas]}, attack: {dir: [3 Canvas]}, hurt: {dir: Canvas}; fills sprites+animations
```

`Tools/audiogen/audiokit.py`: as in §8 of v1 (oscillators, envelopes, filters, sweep, mix,
normalize, trim, note_freq, write_wav, write_ogg, Sequencer with exact-length render and
render_loop_safe, parse_pattern, instrument library) PLUS wuxia instruments: `zither(freq,dur,vel)`
(plucked, bright attack, fast decay, slight detune), `flute(freq,dur,vel)` (breathy triangle/sine,
vibrato, slow attack), `taiko(kind)`, `gong(dur)`, `temple_bell(freq,dur)`, `wood_block(pitch)`,
`erhu(freq,dur,vel)` (sawtooth-ish with vibrato and lowpass), and scales helper
`pentatonic(root, mode)` returning note names.

---------------------------------------------------------------------------------------------

## 9. Verification checklist

Art: palette compliance (0 offenders), rects within bounds, unique names, every §5 name exists,
tile sheets grid-aligned with cellmaps generated, character sheets exactly 128x64 with the
column/row layout of §5.1 and faces 32x32, FX strips exactly N×48 by 48, icons exactly 40x40,
47 masks per autotile set, previews regenerated and visually reviewed at ≥4x (silhouettes,
light direction, no stray pixels, animations move, directions distinct, ink-wash mood kept).
Audio: formats, peak ≤ -1 dBFS, no leading silence > 5 ms, loop length exact, every §6 name.
C#: syntax check passes (tree-sitter), no obsolete APIs, names consistent with sidecars and
`InkPixelPaths`, editor-only code under `Editor/`, GPA integration script matches GPA's real
`RegionData`/`TileDef`/`NpcDef` fields.
GPA compatibility: a Python simulation of `RegionView` slicing renders GPA's three layouts with
the `tiledefs_*.json` mappings into `Docs/previews/gpa_<region>.png`, and they look right.
