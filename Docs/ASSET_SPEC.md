# PixelPack — Unity 2D Top-Down Pixel-Art Asset Pack: Design Spec

This document is the single source of truth for every generator, script and reviewer
working on this pack. All names, sizes, formats and conventions below are binding.
If something is unspecified, choose the simplest option that fits these conventions.

Target: Unity 6 (6000.0 LTS), 2D, Built-in Render Pipeline (must also work under URP 2D).
Genre: top-down action RPG / roguelike (Zelda-like). Style: 16x16 pixel art, 32-color palette.

---------------------------------------------------------------------------------------------

## 1. Repository layout

```
gpb/
  README.md                         # Korean user-facing guide (written last)
  LICENSE                           # MIT (code) + CC0 note (art/audio)
  .gitignore                        # standard Unity gitignore
  Packages/manifest.json            # Unity package manifest (2D packages + input system)
  ProjectSettings/ProjectVersion.txt
  Assets/PixelPack/
    Sprites/
      Characters/   player.png + player.sprites.json, villager_a.png, ..., portraits.png
      Enemies/      slime.png, slime_blue.png, bat.png, ghost.png, skeleton.png, goblin.png, golem.png
      Objects/      items.png, props.png
      Effects/      effects.png
      Tiles/        terrain_grass.png, terrain_dirt.png, terrain_sand.png, terrain_stone.png,
                    terrain_water.png, dungeon.png, floors.png, decor.png
      UI/           ui_panels.png, ui_buttons.png, ui_bars.png, ui_icons.png, ui_font_8x8.png
    Audio/
      SFX/          sfx_*.wav   (44100 Hz, 16-bit, mono)
      Music/        music_*.ogg (44100 Hz, stereo, OGG Vorbis; rendered from WAV via ffmpeg)
    Scripts/
      Runtime/      Core/ Animation/ Entities/ Items/ UI/ World/
      Editor/       importer + builders (slicing, tiles, animations, prefabs, demo scene)
    Generated/      (created inside Unity by the editor tools; NOT committed except .gitkeep)
      Animations/ Tiles/ Prefabs/ Scenes/ Fonts/
  Tools/
    pixelgen/       Python generators for all sprites (pixelkit.py + gen_*.py + build_all.py)
    audiogen/       Python generators for all audio (audiokit.py + gen_sfx.py + gen_music.py + build_all.py)
  Docs/
    ASSET_SPEC.md   this file
    previews/       upscaled contact sheets (PNG) used for review and README
```

Every PNG in `Assets/PixelPack/Sprites/**` has a sidecar `<name>.sprites.json` next to it
(same basename). The Unity importer reads the sidecar to slice the sheet. Never hand-edit PNGs:
edit the Python generator and rerun `python3 Tools/pixelgen/build_all.py`.

Generators must be deterministic (fixed seeds). Running them twice yields byte-identical output.

---------------------------------------------------------------------------------------------

## 2. Art conventions

- Base tile: 16x16 px. Pixels-per-unit (PPU) = 16 everywhere (1 tile = 1 Unity unit).
- Palette: exactly the 32 colors below (plus full transparency). No other colors, no
  anti-aliasing, no partial alpha. A reviewer script verifies palette compliance.
- Outlines: 1px dark outline (`outline` #1a1c2c) around characters, items, props and effects
  (not around tiles). Selective outlining (lighter outline on lit top edges) is allowed only
  using palette colors.
- Lighting: light comes from top-left. Highlight on top/left, shade on bottom/right.
- Shadows: do NOT bake ground shadows into character sprites; a separate `effects_shadow_*`
  sprite is used by the runtime.
- Readability over detail: strong silhouettes, 2–3 tone ramps per material, no noise.
- Characters stand on the bottom row of their cell; pivot (0.5, 0.0) = bottom-center.
- Tiles, items, UI and effects use pivot (0.5, 0.5) = center. 9-slice sprites have borders.
- Directional art: "down" faces the camera, "up" shows the back, "left"/"right" are side
  views. Both left and right are stored explicitly (right may be a mirror of left).
- Non-directional art (slime, bat, ghost, items, props) is drawn front-facing and symmetric.

### 2.1 Palette (32 colors)

| name          | hex     | use |
|---------------|---------|-----|
| black         | #0d0b14 | deepest shadow, void |
| outline       | #1a1c2c | outlines, darkest ramp |
| navy          | #2b2f4a | dark metal, night |
| slate_dark    | #3f4a6b | metal shade, stone shade |
| slate         | #5d6f94 | metal, stone |
| slate_light   | #8ea3bf | metal highlight |
| silver        | #c3d0dd | bright metal, bone |
| white         | #f5f7fa | highlights, eyes |
| brown_dark    | #3d2a22 | wood shade, dirt shade |
| brown         | #6b4332 | wood, dirt |
| wood          | #9c6b48 | wood light, leather |
| tan           | #c9956a | skin shade, rope |
| skin          | #eec39a | skin, sand |
| cream         | #fbe9c9 | parchment, sand light |
| green_dark    | #1f4a2f | foliage shade |
| green         | #2f7d46 | foliage, grass |
| green_light   | #5cc46a | grass light, slime |
| lime          | #b6e65b | grass highlight |
| yellow        | #f7e05a | gold highlight, light |
| gold          | #f2b134 | gold, coins, fire |
| orange        | #e86f2a | fire, autumn, hair |
| red_dark      | #8a1e2e | blood, cloth shade |
| red           | #d9333f | hearts, cloth |
| pink          | #f58aa3 | flowers, magic |
| blue_dark     | #1e3f73 | deep water, cloth shade |
| blue          | #3271d1 | water, cloth |
| sky           | #5cc5ff | water highlight, ice |
| ice           | #bfefff | foam, glow |
| purple_dark   | #42285f | magic shade, ghost shade |
| purple        | #8552c7 | magic, poison |
| lavender      | #c9a8f2 | ghost, magic highlight |
| stone         | #8a8aa0 | stone floor, rock |

Python: `Tools/pixelgen/palette.py` exposes `PALETTE` (ordered dict name->hex) and `COLORS`
(list of (r,g,b)). All drawing uses palette names.

### 2.2 Sprite naming

`<sheet>_<descriptor>[_<dir>][_<frame>]`, lowercase snake_case, ASCII only. Names are unique
across the whole pack (the sheet name prefix guarantees it). Frames are 0-based. Directions
are exactly `down`, `up`, `left`, `right`. Blob tiles use `_m<mask>` (decimal mask, see §4).
Animated blob tiles add `_f<frame>`.

### 2.3 Sheet layout

Sprites are packed left-to-right, top-to-bottom in fixed-size cells per sheet (cell size is
the largest sprite in the sheet, e.g. 16x16, 32x32). Different-size sprites may live in one
sheet by using variable-height rows (the packer in pixelkit handles it). Sheet width ≤ 512 px.
No padding is required (point filtering, no mipmaps), but a 0-px gap is fine. Sheet PNGs are
RGBA, 8-bit.

---------------------------------------------------------------------------------------------

## 3. Sidecar JSON (`<sheet>.sprites.json`) — read by Unity via JsonUtility

Keep the schema flat (JsonUtility: no dictionaries, no nested arrays of arrays).
Coordinates: `x`,`y` are measured from the TOP-LEFT of the PNG (image space). The importer
converts to Unity's bottom-left origin: `unityY = textureHeight - y - h`.

```json
{
  "version": 1,
  "sheet": "player",
  "kind": "character",            // character | enemy | items | props | effects | tiles | ui | font | portraits
  "pixelsPerUnit": 16,
  "defaultPivotX": 0.5,
  "defaultPivotY": 0.0,
  "sprites": [
    { "name": "player_idle_down_0", "x": 0, "y": 0, "w": 16, "h": 16,
      "pivotX": 0.5, "pivotY": 0.0,
      "borderL": 0, "borderB": 0, "borderR": 0, "borderT": 0 }
  ],
  "animations": [
    { "name": "idle_down", "state": "idle", "direction": "down", "fps": 6, "loop": true,
      "frames": ["player_idle_down_0", "player_idle_down_1"] }
  ],
  "tiles": [
    { "name": "GrassVar0", "sprite": "terrain_grass_var_0", "collider": "none" }
  ],
  "tileRules": [
    { "ruleTile": "Grass", "sprite": "terrain_grass_m255", "mask": 255,
      "animFrames": [], "animFps": 0 }
  ],
  "ruleTileDefaults": [
    { "ruleTile": "Grass", "defaultSprite": "terrain_grass_m255", "collider": "none" }
  ],
  "font": { "firstChar": 32, "lastChar": 126, "cellW": 8, "cellH": 8, "columns": 16,
            "lineHeight": 10, "spaceAdvance": 4, "advances": [4, 2, ...] }   // 95 ints, one per glyph (ink width + 1)
}
```

Rules:
- `sprites` is always present. Other arrays may be empty (`[]`) but must exist. `font` is
  present only for font sheets (otherwise `"font": null` is omitted entirely — JsonUtility
  leaves it default; the C# reader checks `font != null && font.cellW > 0`).
- `animations[].name` is unique within the sheet; the Unity asset is named `<sheet>_<name>`.
  `direction` is `""` for non-directional animations. Every character/enemy sheet with
  directional animations provides all four directions for each directional `state`.
- `collider` ∈ `none | sprite | grid`.
- `tileRules`: one entry per (ruleTile, mask). For animated rule tiles, `animFrames` lists the
  frame sprite names (including the first) and `animFps` > 0; `sprite` is the first frame.
- Mask convention (§4): N=1, NE=2, E=4, SE=8, S=16, SW=32, W=64, NW=128. A corner bit is set
  only when both adjacent edge bits are set (47-blob canonical form). The 47 canonical masks
  must all be present for each ruleTile. Mask 0 (isolated tile) is one of the 47.

---------------------------------------------------------------------------------------------

## 4. Blob (47-tile) terrain sets

Tiles are built from four 8x8 quadrants (TL, TR, BL, BR). For a quadrant, look at its two
adjacent edges (e.g. TL: N and W) and the diagonal corner (NW):
- both edges absent  → `corner_out` (convex outer corner)
- only one edge present (N xor W) → `edge_h` if the missing edge is N/S (horizontal border),
  `edge_v` if the missing edge is W/E (vertical border)
- both edges present, corner absent → `corner_in` (concave inner corner)
- both edges + corner present → `inner` (fully inside)

`pixelkit.blob47(draw_quadrant, size=16, frames=1)` calls
`draw_quadrant(quadrant_index, kind, frame, rng)` (quadrant_index 0..3 = TL,TR,BL,BR;
kind ∈ inner|edge_h|edge_v|corner_out|corner_in) and assembles all 47 canonical masks,
returning `[(mask, [canvas_per_frame...]) ...]`. The quadrant drawer must draw the quadrant in
its final orientation (it receives the quadrant index; mirror/rotate internally as needed).

Terrain layering model for the demo (Tilemap layers, bottom to top):
1. `Ground` — fills everything with grass plain variants (`floors` tiles)
2. `Overlay` — blob terrains painted on top: Dirt (over grass), Sand (over grass), Stone path,
   Water (drawn with foam/sand edge, has collider), DungeonWall (collider)
3. `Decor` — small decorations, no collider
4. Props/entities are GameObjects (sprites), Y-sorted by pivot.

---------------------------------------------------------------------------------------------

## 5. Sprite inventory (binding names)

### 5.1 Characters (`Sprites/Characters/`) — cells 16x16, pivot (0.5, 0)
`player`: directional states `idle` (4 frames), `walk` (4), `attack` (3), `hurt` (1);
non-directional `death` (4). Sprite names `player_<state>_<dir>_<i>` / `player_death_<i>`.
Player: hero with brown hair, green tunic, brown boots, small sword in attack frames.
`villager_a`, `villager_b`, `merchant`, `elder`: directional `idle` (4), `walk` (4) only.
`portraits`: 32x32, pivot center: `portraits_player`, `portraits_villager_a`,
`portraits_villager_b`, `portraits_merchant`, `portraits_elder`, `portraits_goblin`,
`portraits_skeleton`. kind = `portraits`, no animations.

### 5.2 Enemies (`Sprites/Enemies/`) — cells 16x16 (golem 32x32), pivot (0.5, 0)
Non-directional (`direction: ""`): `slime`, `slime_blue`, `bat`, `ghost` with states
`idle` (4), `move` (4), `attack` (3), `hurt` (1), `death` (4).
Directional: `skeleton`, `goblin`: `idle` (4), `walk` (4), `attack` (3), `hurt` (1) per
direction + non-directional `death` (4). `golem` (32x32): same with `attack` (4), `death` (6).

### 5.3 Objects (`Sprites/Objects/`)
`items` (16x16, pivot center, kind `items`), no outline exceptions: 
coin_0..3 (spin animation "coin_spin", 8 fps), heart, heart_half, heart_empty, potion_red,
potion_blue, potion_green, key_gold, key_silver, sword_wood, sword_iron, sword_gold, bow,
arrow, shield_wood, shield_iron, gem_red, gem_blue, gem_green, bomb, scroll, map, meat,
apple, bread, cheese, ring, boots, armor, helmet, wand, book, torch, lantern, pickaxe, axe,
fish, mushroom, herb, bone, feather, crystal. (names prefixed `items_`)

`props` (variable size, pivot (0.5, 0), kind `props`): chest_closed, chest_open_0..2
(animation "chest_open", 10 fps, no loop), barrel, crate, pot, pot_broken, sign, signpost,
tombstone_a, tombstone_b, fence_h, fence_v, fence_post, tree_oak (32x32), tree_pine (32x32),
tree_dead (16x32), bush, bush_berry, rock_small, rock_large, stump, log, flowers_red,
flowers_yellow, flowers_blue, mushrooms, campfire_0..3 (anim "campfire", 8 fps, loop),
torch_wall_0..3 (anim "torch_wall", 8 fps, loop), door_closed, door_open, stairs_down,
stairs_up, well (16x32), statue (16x32), bed, table, chair, bookshelf (16x32), anvil,
lever_off, lever_on, pressure_plate, spikes_0..2 (anim "spikes", 6 fps, no loop), pit, cart,
hay, crate_stack, barrel_stack, lamp_post (16x32), crystal_cluster, bones, skull, cobweb,
tent (32x32), house_small (48x48). (names prefixed `props_`)

### 5.4 Effects (`Sprites/Effects/effects`, pivot center, kind `effects`)
slash_0..3 (32x32, anim "slash" 16 fps), hit_0..3 (16x16, "hit" 16 fps), explosion_0..5
(32x32, "explosion" 12 fps), dust_0..3 (16x16, "dust" 12 fps), smoke_0..3 ("smoke" 8 fps),
sparkle_0..3 ("sparkle" 10 fps, loop), levelup_0..5 (32x32, "levelup" 12 fps), poof_0..3
("poof" 12 fps), fireball_0..3 (16x16, "fireball" 12 fps loop, faces right),
bolt_0..3 (16x16, "bolt" 12 fps loop, faces right), arrow (16x16, faces right),
impact_0..3 ("impact" 16 fps), ripple_0..3 ("ripple" 8 fps), shadow_small (16x16),
shadow_large (32x32), light_soft (64x64 radial, uses only `ice`/`white` with 1-bit alpha
dithering — no partial alpha). (names prefixed `effects_`)

### 5.5 Tiles (`Sprites/Tiles/`, 16x16, pivot center, kind `tiles`)
- `terrain_grass`: rule tile `Grass`: blob47 `terrain_grass_m<mask>` (grass over dirt base),
  plus tiles `GrassPlain0..3` → `terrain_grass_var_0..3` (plain grass variants).
- `terrain_dirt`: rule tile `Dirt`: blob47 (dirt over grass).
- `terrain_sand`: rule tile `Sand`: blob47 (sand over grass).
- `terrain_stone`: rule tile `StonePath`: blob47 (cobblestone over grass).
- `terrain_water`: rule tile `Water` (collider `grid`): blob47 animated 4 frames
  (`terrain_water_m<mask>_f<frame>`), water inner + foam edge.
- `dungeon`: rule tile `DungeonWall` (collider `grid`): blob47 `dungeon_wall_m<mask>` (stone
  brick wall seen from above, top face + darker front face on S-facing edges); tiles
  `DungeonFloor0..3` → `dungeon_floor_0..3`, `DungeonVoid` → `dungeon_void`,
  `DungeonFloorCracked` → `dungeon_floor_cracked`.
- `floors`: tiles `FloorWood0..1`, `FloorDirt0..3`, `FloorSand0..1`, `FloorCobble0..1`,
  `FloorSnow0..1` → sprites `floors_wood_0`, `floors_dirt_0`, ...
- `decor`: tiles (collider none) `DecorGrass0..2`, `DecorFlower0..2`, `DecorPebble0..1`,
  `DecorCrack0..1`, `DecorPuddle`, `DecorBones`, `DecorCobweb`, `DecorMoss`, `DecorLeaves`,
  `DecorMushroom`, `DecorVine` → sprites `decor_grass_0` etc. Transparent background.

### 5.6 UI (`Sprites/UI/`, pivot center, kind `ui`)
- `ui_panels`: 9-slice 24x24, border 8 on all sides: `ui_panels_wood`, `ui_panels_stone`,
  `ui_panels_dark`, `ui_panels_light`, `ui_panels_parchment`, `ui_panels_tooltip` (border 4,
  16x16), `ui_panels_portrait_frame` (40x40, border 4).
- `ui_buttons`: 9-slice 32x16, border 6: `ui_buttons_<style>_<state>` with style ∈
  wood, stone, blue, red, green and state ∈ normal, hover, pressed, disabled.
- `ui_bars`: `ui_bars_frame` (48x8, 9-slice border 3), `ui_bars_fill_red/blue/green/yellow`
  (48x8, 9-slice border 2), `ui_bars_heart_full`, `ui_bars_heart_half`, `ui_bars_heart_empty`
  (16x16), `ui_bars_slot` (20x20, border 4), `ui_bars_slot_selected` (20x20, border 4).
- `ui_icons` (16x16): sword, shield, bag, map, gear, close, check, arrow_up, arrow_down,
  arrow_left, arrow_right, pause, play, sound_on, sound_off, music, star, skull, quest, chat,
  coin, key, heart, potion, lock, unlock, info, plus, minus, home, save, exclamation,
  question, cursor_arrow, cursor_hand, checkbox_off, checkbox_on, radio_off, radio_on,
  slider_knob, dialogue_arrow_0, dialogue_arrow_1 (anim "dialogue_arrow", 4 fps loop).
  (names prefixed `ui_icons_`)
- `ui_font_8x8`: kind `font`. 95 glyphs for ASCII 32..126, 16 columns × 6 rows, 8x8 cells,
  glyphs left-aligned in the cell, 1px shadow NOT included (renderer adds it). Sprite names
  `ui_font_8x8_<code>` (decimal char code). `font` block filled as in §3. Readable at 1x.

---------------------------------------------------------------------------------------------

## 6. Audio

- SFX: WAV, 44100 Hz, 16-bit PCM, mono, peak ≤ -1 dBFS, no DC offset, ≤ 2.0 s each,
  trailing silence trimmed, 2 ms fade-in/out to avoid clicks. Style: chiptune / NES-like
  (pulse, triangle, noise) with light filtering. Names `sfx_<name>.wav`:
  ui_hover, ui_select, ui_confirm, ui_cancel, ui_open, ui_close, ui_error,
  coin, pickup, heart, potion, key, chest_open, door_open, door_close,
  sword_swing_0, sword_swing_1, hit_flesh, hit_metal, hit_wall, player_hurt, player_death,
  enemy_hurt, enemy_death, slime_jump, slime_land, bat_flap, skeleton_rattle, ghost_whoosh,
  golem_step, arrow_shoot, bow_draw, magic_cast, fireball, explosion, bomb_fuse,
  footstep_grass_0..2, footstep_stone_0..2, footstep_water, dash, level_up, quest_complete,
  game_over, save, lever, spikes, water_splash, torch_light, text_blip.
- Music: OGG Vorbis (q=6), 44100 Hz, stereo, seamless loop (length = exact whole bars at
  the song BPM, no fade at the end, tail of the last note cut at the loop point and the loop
  verified by checking the sample count = bars * beats * 60/BPM * SR). Names
  `music_<name>.ogg`: overworld (upbeat, ~120 BPM, major), town (gentle, ~96 BPM),
  dungeon (tense, ~100 BPM, minor), battle (fast, ~150 BPM), title (calm intro, ~80 BPM),
  game_over (short non-looping sting, ~8 s). Each loop 32–64 bars. Keep WAV masters out of
  git (write to a temp dir; only OGG is committed).
- All synthesis via numpy; no external samples. Deterministic.

---------------------------------------------------------------------------------------------

## 7. C# conventions

- No assembly definitions. Runtime scripts under `Scripts/Runtime/**`, editor scripts under
  `Scripts/Editor/**` (Unity's special folder name `Editor`).
- Namespaces: `PixelPack`, `PixelPack.Animation`, `PixelPack.Entities`, `PixelPack.Items`,
  `PixelPack.UI`, `PixelPack.World`, `PixelPack.EditorTools`.
- Target C# 9 / .NET Standard 2.1 (Unity 6). No `record`s with positional syntax issues, no
  file-scoped namespaces (keep block namespaces for 2021 compatibility), no init-only setters.
- Input: support both input backends:
  ```csharp
  #if ENABLE_INPUT_SYSTEM
  using UnityEngine.InputSystem;   // use Keyboard.current / Mouse.current
  #else
  // UnityEngine.Input
  #endif
  ```
  Only `InputReader` touches input APIs; everything else reads `InputReader`.
- Packages that may be referenced directly: `UnityEngine.Tilemaps` (RuleTile, AnimatedTile
  from com.unity.2d.tilemap.extras), `UnityEngine.UI`, `TMPro` is NOT used (we ship our own
  bitmap-font renderer `PixelText`). Optional packages (`com.unity.2d.pixel-perfect`) are
  accessed via reflection so the pack compiles without them.
- Sprite slicing in the editor uses `UnityEditor.U2D.Sprites.ISpriteEditorDataProvider`
  (com.unity.2d.sprite), NOT the obsolete `TextureImporter.spritesheet`. Sprite IDs are
  deterministic GUIDs derived from the sprite name (MD5), so references survive reimports.
- Every `MonoBehaviour` has a short XML doc comment, `[Tooltip]`s on public fields, and
  sensible defaults so the editor builders can create working prefabs with few assignments.
- Audio: `AudioManager` is a scene singleton (no DontDestroyOnLoad required), plays SFX by
  clip name lookup (`AudioManager.PlaySfx("coin")`) from clips assigned in a list, and
  loops music with crossfade.
- Editor tools live under menu `Tools/PixelPack/...` and generate into
  `Assets/PixelPack/Generated/...`. Everything in `Generated/` must be reproducible.
- All editor builders must be idempotent (re-running overwrites assets in place, keeping GUIDs
  via `AssetDatabase.LoadAssetAtPath` + modify + `SaveAssets`, or `CreateAsset` only when
  missing).

### 7.1 Runtime component set (names are binding; details are up to the implementer)
Core: `GameManager`, `AudioManager`, `InputReader`, `CameraFollow`, `ScreenShake`,
`ObjectPool`, `PixelPackPaths` (static string constants for all asset folders/sheet names).
Animation: `SpriteAnimation` (ScriptableObject: frames, fps, loop, events),
`SpriteAnimator` (plays a SpriteAnimation on a SpriteRenderer or UI Image),
`DirectionalAnimator` (state + facing → SpriteAnimation; data in `AnimationSet` entries
`{state, down, up, left, right}`; non-directional sets reuse one clip for all four).
Entities: `IDamageable`, `Health`, `Hitbox`, `Hurtbox`, `Knockback`, `DamageFlash`,
`PlayerController` (8-way move, dash, facing), `PlayerCombat` (melee swing with hitbox +
slash effect, ranged arrow), `EnemyAI` (wander/chase/attack/flee states, contact damage,
uses DirectionalAnimator), `Projectile`, `Spawner`, `LootDrop`, `EntityShadow`.
Items: `ItemData` (SO: id, display name, icon sprite name, type, value, stackable),
`Pickup`, `Inventory`, `Chest`, `Door`, `Lever`, `IInteractable`, `Interactor`,
`InteractionPrompt`.
UI: `PixelFont` (SO built from the font sheet), `PixelText` (UI Graphic that renders text
with PixelFont), `HeartsUI`, `BarUI`, `CoinCounterUI`, `InventoryUI`, `DialogueBox`
(typewriter with `text_blip`), `DialogueData` (SO), `PauseMenu`, `DamagePopup`,
`ScreenFader`.
World: `AnimatedSpriteProp` (campfire/torch), `YSorter` (sets sortingOrder from y),
`AreaTrigger`, `Teleporter`, `MapGenerator` (runtime procedural map painter used by the demo).

---------------------------------------------------------------------------------------------

## 8. Python toolkit API (`Tools/pixelgen/pixelkit.py`) — binding surface

```python
from pixelkit import Canvas, Sheet, blob47, PALETTE, Rng
c = Canvas(16, 16)                       # RGBA, transparent; (0,0) is top-left
c.set(x, y, "green")                     # palette name, "#rrggbb", (r,g,b[,a]) or None (erase)
c.get(x, y) -> (r,g,b,a)
c.rect(x, y, w, h, color, fill=True)     # outline when fill=False
c.line(x0, y0, x1, y1, color)
c.ellipse(cx, cy, rx, ry, color, fill=True)
c.circle(cx, cy, r, color, fill=True)
c.fill_points([(x,y),...], color)
c.blit(src, x, y, flip_x=False, flip_y=False)   # alpha-aware composite
c.flipped_x() / c.flipped_y() / c.rotated(k)    # new canvases
c.outlined(color="outline", diagonal=False)      # new canvas with 1px outline added around opaque pixels
c.recolored({"green": "blue", ...})     # palette swap → new canvas
c.shifted(dx, dy) / c.cropped(x, y, w, h) / c.scaled(k)
c.stamp(text, x, y, color, font="3x5")   # tiny debug text (optional)
c.paste_pattern(pattern_rows, x, y, colormap)   # ASCII art rows → pixels, e.g. ["..##..", ...]
c.to_image() -> PIL.Image ; c.save(path)
Canvas.from_pattern(rows, colormap)      # colormap: {char: palette_name}; '.' = transparent

rng = Rng(seed)                           # thin wrapper over random.Random; rng.choice/randint/random/shuffle

s = Sheet("player", kind="character", pivot=(0.5, 0.0), columns=8)
s.add("player_idle_down_0", canvas, pivot=None, border=None)   # border=(l,b,r,t) for 9-slice
s.add_animation("idle_down", ["player_idle_down_0", ...], fps=6, loop=True, state="idle", direction="down")
s.add_tile("GrassPlain0", "terrain_grass_var_0", collider="none")
s.add_tile_rule("Grass", "terrain_grass_m255", mask=255, anim_frames=None, anim_fps=0)
s.set_rule_tile_default("Grass", "terrain_grass_m255", collider="none")
s.set_font(first_char=32, last_char=126, cell_w=8, cell_h=8, columns=16, line_height=10, space_advance=4, advances=[...])
s.save(out_dir)                           # writes <out_dir>/<sheet>.png + <sheet>.sprites.json (deterministic order)
s.preview(path, scale=4, labels=True)     # upscaled contact sheet with sprite names, for review

blob47(draw_quadrant, size=16, frames=1, rng=None) -> list[(mask, [Canvas per frame])]
MASK_N, MASK_NE, MASK_E, MASK_SE, MASK_S, MASK_SW, MASK_W, MASK_NW ; CANONICAL_MASKS (47 ints)
verify_palette(png_path) -> list of offending (x, y, rgba)   # used by reviewers
```

`Tools/audiogen/audiokit.py` — binding surface:
```python
SR = 44100
osc_pulse(freq, dur, duty=0.5), osc_tri(freq, dur), osc_saw(freq, dur), osc_sine(freq, dur), noise(dur, color="white")
env_adsr(n, a, d, s, r) ; env_decay(n, tau) ; apply_env(x, env)
sweep(f0, f1, dur, wave="pulse", duty=0.5, curve="exp")   # pitch sweep
lowpass(x, cutoff_hz, order=1), highpass(x, cutoff_hz), bitcrush(x, bits), vibrato(freq_curve, rate, depth)
mix(*signals), concat(*signals), pad(x, seconds), fade(x, in_s, out_s), normalize(x, peak_db=-1.0), trim_silence(x, thresh_db=-60)
note_freq("C4") ; midi_to_freq(n)
write_wav(path, x, sr=SR)                 # mono or (n,2) stereo float -1..1 → 16-bit
write_ogg(path, x, sr=SR, quality=6)      # via ffmpeg
Sequencer(bpm, sr=SR) : add_track(name, instrument_fn, pattern, volume, pan)  # pattern = list of (beat, note_or_None, length_beats, velocity)
Sequencer.render(bars) -> stereo numpy array with exact length bars*4*60/bpm*sr samples
```

---------------------------------------------------------------------------------------------

## 9. Verification checklist (reviewers)

Art: palette compliance (0 offending pixels), all sidecar rects within bounds, unique names,
animations reference existing sprites with ≥1 frame, directional states have all 4 directions,
47 masks present per rule tile, every inventory name in §5 exists, previews regenerated, visual
review of each preview at ≥4x (silhouette readable, consistent light direction, no stray
pixels, animations show motion between frames).
Audio: file format as specified, no clipping (peak ≤ -1 dBFS), no leading silence > 5 ms,
music loop length exact, every §6 name exists.
C#: all §7.1 names exist, no obsolete/removed Unity APIs, consistent names between sidecar
JSON, `PixelPackPaths`, and editor builders, all `using`s present, no TMPro, both input
backends compile, editor-only code only under `Editor/`.
