# charkit — shared character construction kit (Tools/pixelgen/charkit.py)

Every character sheet of `Docs/ASSET_SPEC.md` §5.1 is assembled from the same hand-drawn
ASCII layers, so heroes, companions, NPCs and enemies share one silhouette language, one light
direction (top-left), the same walk cycle and the same attack grammar. You describe a character
with a **spec dict**; the kit returns the 16x16 frames `pixelkit.character_sheet` expects plus
the 32x32 dialogue face.

```python
import os
from charkit import make_character
from pixelkit import character_sheet

spec = {
    "build": "normal", "hair": "topknot", "robe": "robe_sash", "weapon": "jian", "hip_weapon": True,
    "expression": "neutral",
    "colors": {"hair": "ink_dark", "cloth": "paper", "trim": "earth_light", "accent": "sand",
               "pants": "earth", "feet": "earth_dark"},
}
walk, attack, hurt, face = make_character(spec)          # face=False -> face is None
sheet, face_sheet = character_sheet("hero_1", walk, attack, hurt, face)
sheet.save(os.path.join(art_root, "Characters"))        # hero_1.png (128x64) + sidecar
face_sheet.save(os.path.join(art_root, "Characters"))   # hero_1_face.png (32x32) + sidecar
sheet.preview(os.path.join(preview_dir, "hero_1_preview.png"), scale=4)
```

Outfit variants are just another `colors` dict (`copy.deepcopy(spec)` then
`spec["colors"].update({...})`), e.g. 청운도복 = `cloth jade / cloth_dark jade_dark /
cloth_light jade_light / trim paper / accent paper_dark`, 흑사흑의 = `cloth bronze_navy /
cloth_dark ink_dark / cloth_light navy / trim ink / accent vermilion`.
See `gen_characters_heroes.py` for the full pattern.

## API

| call | returns |
|---|---|
| `make_character(spec, face=True)` | `(walk, attack, hurt, face)` — `walk {dir: [4 Canvas]}`, `attack {dir: [3 Canvas]}`, `hurt {dir: Canvas}` (all 16x16, outlined), `face` Canvas 32x32 or None |
| `make_face(spec)` | 32x32 outlined bust |
| `compose_frame(spec, dir, pose, outline=True)` | one 16x16 frame; `dir` in `down/up/left/right`, `pose` in `stand, step_l, pass, step_r, wind, strike, recover, hurt` |
| `resolve_colors(colors)` | letter -> palette-name map with derived shades (see below) |
| `list_parts()` | every part name per spec key (for validation / docs) |
| `Grid` | the letter raster used internally (`paste`, `replace`, `flipped_x`, `to_canvas(colors)`) — handy for custom `extras` experiments |

Walk frames: `stand` (frame 0 = idle, feet together, also a contact pose), `step_l`, `pass`,
`step_r` (1px head bob on 1 and 3, legs alternate, the back arm swings). Attack: `wind`
(weapon raised / pulled back), `strike` (weapon extended toward the facing direction, 1px
lunge / wide stance), `recover` (weapon lowered). `hurt`: leaning back, squinting, hands up.
`right` is the mirror of `left` (weapon hand mirrored too).

## Spec keys

| key | values | notes |
|---|---|---|
| `build` | `child` `normal` `tall` `burly` | child: 13px tall incl. outline, narrow; tall: +1 torso row; burly: +1 row and 2px wider |
| `hair` | `bald` `short` `topknot` `topknot_pin` `bun` `bun_pin` `ponytail` `ponytail_high` `braid` `loose_long` | color letters `H` (hair) / `U` (highlight), pins `G`, braid tip `X` |
| `headwear` | `none` `straw_hat` `scholar_hat` `headband` `hood` `cap` `headscarf` `helmet` | hats use `B`/`N`; headband uses `X`; helmet uses `W`/`M`/`K` |
| `beard` | `none` `short` `long` `goatee` `mustache` | hair color; `mustache` shows on the face only |
| `hair_accessory` | `none` `ribbon` | `X` color |
| `robe` | `long_robe` `robe_sash` `short_tunic` `vest_bare_arms` `armor_lamellar` `dress` `apron_dress` `ragged` | see below |
| `weapon` | `none` `palm` `jian` `dao` `dagger` `staff` `spear` `fan` `needle_throw` `sling` `cleaver` `broom` `pole` `basket` | attack frames only; `none`==`palm` (qi burst `Q` on strike) |
| `hip_weapon` | bool | hilt (`G`) + scabbard (`K`) at the hip in walk/idle frames, blades only |
| `carry` | `none` `basket` `bolt` `scroll` `abacus` `gourd` `towel` `keys` | held in the off hand in walk/idle/hurt frames |
| `collar` | `none` `fur` | fur over the shoulder row (`V`/`J`) and on the face |
| `scar` | bool | dark scar across the right eye (down/side views and the face) |
| `expression` | `neutral` `smile` `grin` `stern` `angry` `sad` `sly` `calm` `fierce` `worried` | face only |
| `eyes` | `normal` `narrow` `closed` | face only (`calm` forces `closed`) |
| `colors` | `{friendly key or letter: palette name}` | see the letter table |
| `extras` | list of overlays | `{"rows": [...], "x": 11, "y": 9, "dirs": ["down"], "poses": ["*"], "anchor": "body"|"head", "layer": "front"|"back", "face": bool, "face_x", "face_y"}` |
| `face_extras` | list of `{"rows", "x", "y"}` | overlays drawn on the 32x32 face only |

### Letters and colors

Templates are letter grids; colors are applied last, so a palette swap is just a different
`colors` dict. Keys may be the friendly name or the letter; values are palette names only.

| letter | key | default | used for |
|---|---|---|---|
| `S` | `skin` | skin | face, hands, bare arms |
| `Z` | `skin_shade` | sand (derived from skin) | neck shade on the face |
| `E` | `eye` | ink_black | eyes |
| `H` / `U` | `hair` / `hair_light` | ink_dark / ink (derived) | hair, beard, brows |
| `C` / `D` / `L` | `cloth` / `cloth_dark` / `cloth_light` | paper / paper_dark / paper_light (D, L derived from `cloth` via `palette.RAMPS`) | robe |
| `T` | `trim` | cloth_light (derived) | collar, dress hem, apron, towel |
| `A` / `a` | `accent` / `accent_dark` | sand / earth_light | sash, ties |
| `P` / `F` | `pants` / `feet` | ink_dark / earth_dark | legs under short robes, shoes (`feet: skin` = barefoot) |
| `K` | `dark` | ink_dark | scabbard, patches, squint, scar, helmet rim |
| `B` / `N` | `hat` / `hat_dark` | paper_dark / earth_light (derived) | headwear |
| `W` / `M` / `G` / `O` | `weapon` / `weapon_light` / `hilt` / `wood` | ink_pale / paper_light / gold / earth | blades, tips, guards, poles |
| `V` / `J` | `prop` / `prop_dark` | paper_dark / earth_light | basket, broom head, fan, fur, gourd |
| `X` / `Q` | `extra` / `extra2` | vermilion / jade_light | ribbon, headband, spear tassel, silk bolt / palm-strike qi |

Derived shades: give only `cloth`, `skin`, `hair`, `hat`, `accent`, `prop` and the kit picks the
darker / lighter neighbour on the palette ramp that contains the color (clamped at ramp ends);
set the derived key explicitly to override (e.g. `"cloth": "bronze_navy", "cloth_light": "navy"`).

### Part examples (one spec per part)

```python
# builds
{"build": "child",  "hair": "short", "headwear": "cap", "robe": "ragged", "weapon": "dagger"}      # 소육
{"build": "burly",  "hair": "short", "headwear": "headband", "robe": "vest_bare_arms", "weapon": "palm"}  # 석두
{"build": "tall",   "hair": "ponytail", "robe": "long_robe", "weapon": "jian", "hip_weapon": True}  # hero_2
# hair
{"hair": "topknot_pin", "beard": "long", "colors": {"hair": "paper_light"}}                           # 윤백산
{"hair": "bun_pin", "robe": "long_robe", "weapon": "needle_throw", "carry": "basket"}                 # 백설화
{"hair": "ponytail_high", "robe": "short_tunic", "weapon": "dao", "colors": {"cloth": "vermilion"}}   # 홍련
{"hair": "braid", "robe": "dress", "colors": {"hair": "earth", "trim": "jade", "accent": "jade"}}     # hero_4
{"hair": "loose_long", "hair_accessory": "ribbon", "robe": "dress"}                                   # hero_3
{"hair": "bald", "robe": "long_robe", "weapon": "staff", "colors": {"cloth": "ink_light"}}            # monk
# headwear
{"headwear": "straw_hat", "beard": "short", "weapon": "pole"}                                         # boatman
{"headwear": "scholar_hat", "carry": "scroll", "colors": {"hat": "ink_dark", "hat_dark": "ink_black"}} # scholar
{"headwear": "hood", "weapon": "dagger", "colors": {"hat": "ink_light", "cloth": "ink_light"}}       # heuksa_courier
{"headwear": "headscarf", "weapon": "dao", "colors": {"hat": "ink_dark", "cloth": "bronze_navy"}}    # heuksa_thug
{"headwear": "helmet", "robe": "armor_lamellar", "weapon": "spear", "build": "tall"}                  # guard
# robes
{"robe": "robe_sash"}  {"robe": "short_tunic"}  {"robe": "vest_bare_arms"}  {"robe": "armor_lamellar"}
{"robe": "dress"}  {"robe": "apron_dress", "weapon": "cleaver", "colors": {"cloth": "earth", "trim": "paper"}}  # 유소소
{"robe": "ragged", "hair": "loose_long", "beard": "long", "carry": "gourd", "colors": {"hair": "paper_light", "feet": "skin"}}  # hermit
# weapons (attack frames): none/palm jian dao dagger staff spear fan needle_throw sling cleaver broom pole basket
{"weapon": "fan", "colors": {"prop": "paper", "prop_dark": "ink_light"}}                              # 백여린
{"weapon": "sling", "build": "child", "hair": "braid"}                                                # 연아
{"weapon": "broom", "colors": {"cloth": "jade", "prop": "paper_dark"}}                                # 능소
# carried props / details
{"carry": "towel", "robe": "short_tunic"}  {"carry": "abacus", "headwear": "cap"}  {"carry": "bolt", "colors": {"extra": "plum"}}
{"carry": "keys", "build": "burly", "headwear": "headscarf"}
{"scar": True, "collar": "fur", "build": "burly", "beard": "short", "weapon": "dao"}                   # bandit_boss
# faces
{"expression": "stern"}  {"expression": "calm"}  {"expression": "grin", "eyes": "narrow"}
# custom overlay: a plum patch on the right sleeve, down view only, all poses
{"extras": [{"rows": ["X"], "x": 11, "y": 10, "dirs": ["down"], "poses": ["*"], "anchor": "body"}]}
```

## Geometry (normal build, for `extras` coordinates)

16x16 frame, 1px `ink_black` outline added last (so art stays inside x 1..14, y 1..14).
Head box 6x6 at x 5..10, y 3..8 (eyes at y 6, x 6 and 9); hair rises up to 2 rows above.
Shoulder row y 9, torso y 10, sash y 11, skirt / legs y 12..13, feet y 14. Arms at x 4 and
x 11 (hands at the sash row). Side view: torso x 6..9, the near arm (shaded `D`) at x 7, nose at
x 4. Child: head box top y 5, no torso row, 2 lower rows. Tall / burly: head top y 2, two torso
rows; burly is also 2px wider (arms at x 3 / x 12). Poses shift the head (bob +1 on step_l /
step_r / down-strike; hurt leans back) and the weapon hand is wherever the body template puts it,
so prefer `anchor: "head"` for things on the head and `anchor: "body"` for the rest.

Face (32x32): head x 8..23, y 5..19; eyes 2x2 at x 11 / 19, y 12..13; mouth y 17; neck y 20..21;
bust from y 22 (shoulders out to x 3..28). Hair rises to y 1 for topknots.

## Reviewing

`Sheet.preview(path, scale=4)` for the whole sheet, `preview_group(path, "<name>_attack_left",
scale=8)` for close-ups. The kit guarantees the outline is never clipped (`compose_frame`
keeps every opaque pixel inside 1..14) and `build_all.py` verifies palette + sidecar layout.
