# Tools/pixelgen — InkPixel art toolkit (generator author guide)

Python 3.13 + Pillow + numpy. Everything in `Docs/ASSET_SPEC.md` (v2) is binding; this README
explains how to use the toolkit to meet it. Run the toolkit self-test before relying on it:

```
python3 Tools/pixelgen/selftest.py          # must print N/N passed
python3 Tools/pixelgen/build_all.py         # runs every gen_*.py, verifies, prints a table
```

## 1. Generator module contract

Create `Tools/pixelgen/gen_<name>.py` (e.g. `gen_tiles.py`, `gen_characters.py`, `gen_icons.py`,
`gen_fx.py`, `gen_ui.py`). `build_all.py` discovers `gen_*.py` in sorted order, imports each one
in its own namespace (this folder is on `sys.path`, so `from pixelkit import ...` works) and calls

```python
def build(art_root: str, preview_dir: str, cellmap_dir: str) -> list[str]:
    """Write all sheets/singles of this generator and return every path written."""
```

- `art_root`    = `<repo>/Assets/InkPixel/Art` (the folders below already exist)
- `preview_dir` = `<repo>/Docs/previews`
- `cellmap_dir` = `<repo>/Docs/cellmaps`
- Return every file you wrote (PNG, sidecar JSON, previews, cell maps). `build_all` runs
  `check_sheet` on each PNG that has a `<base>.sprites.json` beside it and `verify_palette` on
  every other PNG; any problem fails the build (`--no-verify` to skip while iterating).
- Be deterministic: fixed seeds (`Rng(<constant>)`), no wall-clock, no set iteration order.
  Running twice must give byte-identical files.
- Never write outside your own files, never touch other generators' outputs.

Selecting generators: `python3 Tools/pixelgen/build_all.py tiles fx` (names with or without
`gen_`/`.py`). `--list` shows what would run. Exit code 1 = something failed.

## 2. Where each kind goes

| kind        | Sheet(...)                                      | writes with                                   | destination                                             |
|-------------|-------------------------------------------------|-----------------------------------------------|---------------------------------------------------------|
| `tiles`     | `Sheet("ground"/"nature"/"town", "tiles", pivot=(0.5, 0))` | `save(Tiles/)` + `cellmap(...)` + `preview(...)` | `Art/Tiles/<sheet>.png` + `.sprites.json`               |
| `autotiles` | `Sheet("autotiles", "autotiles")` + `add_blob`  | `save(Tiles/)` + `cellmap` + `preview`        | `Art/Tiles/autotiles.png`                               |
| `character` | `character_sheet(name, walk, attack, hurt, face)` | `sheet.save(Characters/)`, `face.save(Characters/)` | `Art/Characters/<name>.png` (128x64), `<name>_face.png` (32x32) |
| `icons`     | `Sheet("icons", "icons", file_name="icons_sheet")` | `save_singles(Icons/)` + `save(Icons/)`     | `Art/Icons/<icon>.png` (40x40) + `Icons/icons_sheet.png` |
| `icons` mini| `Sheet("icons_mini", "icons")`                  | `save_singles(Icons/Mini/)`                   | `Art/Icons/Mini/<icon>.png` (16x16)                     |
| `fx`        | `Sheet("slash_heavy", "fx", pivot=(0.5, 0.5))` + `set_strip(n, fps)` | `save(FX/)`               | `Art/FX/SlashHeavy.png` (PascalCase automatically) + `.sprites.json` |
| `ui`        | `Sheet("ui", "ui", file_name="ui_sheet")` with `single_name="Status/bleed"` etc. | `save_singles(UI/)` + `save(UI/)` | `Art/UI/Status/<n>.png`, `UI/Markers/<n>.png`, `UI/Frames/<n>.png`, `UI/ui_sheet.png` |

Previews: `sheet.preview(os.path.join(preview_dir, f"{sheet.file_name}_preview.png"))` for every
sheet (name `<sheet>_preview.png`; use `preview_group(path, prefix, scale=8)` for close-ups).
Cell maps (tile sheets only): `sheet.cellmap(os.path.join(cellmap_dir, f"{sheet.name}_cellmap.png"),
os.path.join(cellmap_dir, f"{sheet.name}.md"))`.

## 3. Recommended technique

- **Characters, icons, UI, markers**: hand-drawn ASCII patterns via `Canvas.from_pattern(rows,
  colormap)`. Draw the "down" body once, derive "up" (back view: hair instead of face), "left"
  (side view), and `right = left.flipped_x()` when the design is symmetric (weapon hand may need a
  redraw). Walk frames: row 0 = standing (feet together), rows 1/3 = step with a 1px head bob
  (`shifted(0, -1)` on the head part, or a second pattern), row 2 = pass. Attack frames: wind-up
  (`shifted` back 1px), strike (weapon extended toward the facing direction), recover. Outfit
  variants: `body.recolored({"paper": "jade", "earth": "jade_dark"})`. Add the outline LAST with
  `canvas.outlined()` (1px `ink_black`, §2), and keep the art inside 1px of the edge so the
  outline is not clipped. `Canvas.to_pattern()` dumps a canvas back to text for editing.
- **Tiles / autotiles / FX**: procedural (`rect`, `circle`, `ellipse`, `line`, `dither_rect`,
  `fill_where` with numpy masks, `Rng` specks). Ground tiles have NO outline and must tile
  seamlessly (test by blitting a 2x2 of the tile). Blob sets: write one `draw_quadrant(qi, kind,
  frame, rng)` returning an 8x8 canvas in its final orientation (see the `blob47` docstring
  example), then `sheet.add_blob("Road", "autotiles_road", blob47(draw_quadrant))`.
- **Icons**: draw at ~32px inside the 40x40 cell, `art.centered(40, 40)` then `outlined()`.
- **Iterate on previews**: build, open `Docs/previews/<sheet>_preview.png` (4x, labelled) and
  `preview_group` close-ups at 8x; check silhouettes, light from top-left (highlight top/left,
  shade bottom/right), no stray pixels, directions distinct, animations move.
- `Sheet.load(png)` rebuilds a saved sheet so you can `preview` / `validate_character` /
  `cellmap` files written earlier (or by someone else).

## 4. Ink-wash palette guidance (§2.1, 32 colors, names only)

Use **palette names** everywhere (`"moss"`, not hex). `palette.RAMPS` / `palette.ramp("wood")`
give dark→light ramps:

| material            | ramp (dark → light)                                 |
|---------------------|-----------------------------------------------------|
| cloth (grey robes)  | `ink_dark` / `ink` / `ink_light`                    |
| wood, leather, dirt | `earth_dark` / `earth` / `earth_light`              |
| grass, foliage      | `moss_dark` / `moss` / `moss_light` (+ `moss_pale` highlight) |
| skin                | `sand` (shade) / `skin`                             |
| paper, hanji walls, white cloth, sand | `paper_dark` / `paper` / `paper_light` |
| stone, roof tiles   | `ink` / `ink_light` / `ink_pale`                    |
| water               | `water_deep` / `water` / `water_light`              |
| night, black cloth, distant mountains | `bronze_navy` / `navy` / `steel`      |
| accents (sparse!)   | `vermilion_dark` / `vermilion` / `vermilion_light`, `jade_dark` / `jade` / `jade_light`, `gold` / `gold_light`, `plum` |

Outline: `ink_black` (the v1 name `"outline"` still resolves to it). Mood: paper-cream lights,
ink-dark darks, desaturated greens/browns, strong value structure, few hues, vermilion and jade
only as small accents (sashes, lanterns, seals, sect trim). Light from the top-left. No partial
alpha, no colors outside the 32: `verify_palette(png)` must return `[]`.

## 5. API cheat sheet (full docstrings in `pixelkit.py`)

```python
from pixelkit import Canvas, Sheet, Rng, blob47, character_sheet, verify_palette, check_sheet, DIRECTIONS

c = Canvas(16, 16)                                   # transparent RGBA, (0,0) top-left
c.set(x, y, "moss"); c.get(x, y); c.get_name(x, y)
c.rect(x, y, w, h, color, fill=True); c.line(...); c.hline(...); c.vline(...)
c.ellipse(cx, cy, rx, ry, color, fill=True); c.circle(cx, cy, r, color, fill=True)
c.fill_points(points, color); c.fill_where(mask, color); c.dither_rect(x, y, w, h, color, parity=0)
c.paste_pattern(rows, x, y, colormap); Canvas.from_pattern(rows, colormap); c.to_pattern()
c.blit(src, x, y, flip_x=False, flip_y=False)
c.flipped_x() / c.flipped_y() / c.rotated(k) / c.mirrored_lr() / c.mirrored_tb()
c.outlined(color="ink_black", diagonal=False, grow=False); c.recolored({"moss": "jade"})
c.shifted(dx, dy) / c.cropped(x, y, w, h) / c.centered(w, h) / c.scaled(k) / c.dithered(parity)
c.bbox(); c.count_opaque(); c.colors_used(); c.equals(other); c.copy()
c.stamp(text, x, y, color)                            # 3x5 debug font (previews only)
c.to_image(); c.save(path); Canvas.load(path)
rng = Rng(seed); rng.choice / randint / random / uniform / shuffle / sample / chance / fork(label)

s = Sheet("town", kind="tiles", pivot=(0.5, 0.0), max_width=512, cell_size=16)   # + columns=, file_name=
s.add(name, canvas, pivot=None, border=None, solid=False, overlay=False, ground="", tags="", single_name=None)
s.add_at(name, canvas, x, y, ...)                     # fixed position (character grids)
s.add_frames(prefix, canvases, **kw)                  # prefix_0, prefix_1, ...
s.add_animation(name, frames, fps, loop=True, state="", direction="")
s.add_directional_animation(state, {dir: frames}, fps, loop=True)
s.add_tile(name, sprite, collider="none"); s.add_tile_rule(rule, sprite, mask, anim_frames=None, anim_fps=0)
s.set_rule_tile_default(rule, sprite, collider="none"); s.add_blob(rule, prefix, blob47(...), collider=, anim_fps=)
s.set_strip(frames, fps)                              # fx: one row, PNG = frames*w x h
s.layout() / s.rects() / s.png_size() / s.render()
s.validate(strict=True) -> [problems]; s.validate_character()
s.save(out_dir) -> (png, json); s.save_singles(out_dir) -> [png...]
s.preview(path, scale=4, labels=True); s.preview_group(path, prefix, scale=8)
s.cellmap(png_path, md_path, scale=3); Sheet.load(png_path)

sheet, face_sheet = character_sheet(name, walk={dir: [4]}, attack={dir: [3]}, hurt={dir: c}, face=c32)
blob47(draw_quadrant, size=16, frames=1, rng=None) -> [(mask, [Canvas per frame]), ...]
verify_palette(png) -> [(x, y, rgba)...]; check_sheet(png) -> [problems]; check_character_sheet(png)
```

Sidecar (`<file>.sprites.json`, §3 v2) is written by `save()`: version 2, kind, cellSize,
stripFrames/stripFps, per-sprite rect + pivot + 9-slice border + cellX/Y/W/H + solid/overlay/
ground/tags, animations, tiles, tileRules, ruleTileDefaults. `save()` refuses sheets that break
the spec (tile sprites off the 16px grid, missing masks, fx without a strip, a character sheet
that is not the §5.1 grid, dangling sprite references); `save(out_dir, strict=False)` is for
work-in-progress only.

## 6. Naming reminders (§2.2)

- Sheet and sprite names: lowercase snake_case; sprite = `<sheet>_<descriptor>[_<dir>][_<frame>]`.
- Files GPA loads by name keep the exact spec names: icons lowercase (`jian.png`), FX PascalCase
  (`SlashHeavy.png`, done automatically for kind `fx`), UI singles via `single_name="Status/bleed"`.
- Blob tiles: `autotiles_<set>_m<mask>` (animated: `_f<frame>`), RuleTile names `Road`, `Water`,
  `Reeds`, `Cliff`, `CaveWall`, `Courtyard`.
- Tile assets (`add_tile`) use PascalCase Unity names, e.g. `GrassA`.
