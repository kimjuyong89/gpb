# InkPixel editor tools (`Assets/InkPixel/Scripts/Editor/`)

Editor-only C# (namespace `InkPixel.EditorTools`, no assembly definition, Unity 6000.3) that turns
the PNG sheets + `<sheet>.sprites.json` sidecars under `Assets/InkPixel/Art/` into Unity assets.
Everything is idempotent: running a tool twice changes nothing and logs "unchanged".
The binding rules live in `Docs/ASSET_SPEC.md` (§3 sidecar schema, §4 blob masks, §7 C# conventions).

Menu: **Tools / InkPixel**

| Item | What it does |
|---|---|
| `1. Reimport All Sprites` | Force-reimports every PNG under `Art/` (applies the import rules below) and then applies every sidecar whose rects differ from the importer's. |
| `2. Build Animations` | Creates/updates `SpriteAnimation` assets from sidecar `animations` and FX strips. |
| `3. Build Tiles` | Creates/updates `Tile` and `RuleTile` assets from sidecar `tiles` / `tileRules` / `ruleTileDefaults`. |
| `Setup All` | 1 → 2 → 3 (with `SaveAssets`/`Refresh` between steps), then `InkPixelMenu.BuildDemoSceneHook` if a demo-scene builder registered one; prints a summary with counts and failures. |
| `Validate Sidecars` | Structural check of every sidecar (names unique, rects inside the PNG, references resolve, colliders valid, orphan sidecars) without writing anything. |
| `Open Spec` | Opens `Docs/ASSET_SPEC.md` with the default application. |

Importing happens automatically too: dropping or regenerating a PNG/sidecar under `Art/` re-slices
that sheet on the next editor tick, so the numbered items are only needed for a full rebuild.

## Files

### Runtime types used by the tools (`Scripts/Runtime/`, namespace `InkPixel`)

- `InkPixelPaths` — string constants for every folder of §1 (`Root`, `Art`, `Tiles`, `Characters`,
  `Icons`, `IconsMini`, `FX`, `UI`, `UIStatus`, `UIMarkers`, `UIFrames`, `Audio`, `Sfx`, `Music`,
  `Generated`, `GenAnimations`, `GenTiles`, `GenScenes`, `GenPrefabs`, …), `PixelsPerUnit = 16`,
  `CellSize = 16`, `SidecarSuffix = ".sprites.json"`, plus `SidecarPathFor`, `TexturePathFor`,
  `SheetNameOf`, `IsUnderArt` helpers.
- `SpriteAnimation` — ScriptableObject: `Sprite[] frames`, `float fps = 8`, `bool loop = true`,
  `Duration`, `FrameAt`, `FrameIndexAt`; informational `sheet` / `state` / `direction`.
- `SpriteAnimator` — MonoBehaviour that plays a `SpriteAnimation` on a `SpriteRenderer` and/or
  `UnityEngine.UI.Image` (auto-detected): `Play(anim, restart = false)`, `Play()`, `Stop()`,
  `SetFrame`, `Current`, `IsPlaying`, `FrameIndex`, `NormalizedTime`, `Speed`; events `OnComplete`
  (non-looping clip reached its last frame), `OnLoop`, `OnFrame`. A clip with `fps = 0` is static.

### `SidecarData.cs`

`[Serializable]` mirror of the §3 v2 schema for `JsonUtility`: `SidecarData { version, sheet, kind,
pixelsPerUnit, defaultPivotX/Y, cellSize, stripFrames, stripFps, sprites[], animations[], tiles[],
tileRules[], ruleTileDefaults[] }` with `SpriteEntry`, `AnimationEntry`, `TileEntry`, `TileRuleEntry`,
`RuleTileDefaultEntry`. `SidecarData.Load(texturePath)` reads `<path minus .png>.sprites.json` and
returns `null` when absent (parse errors are logged). Missing JSON fields keep their defaults; a
sprite without `pivotX/Y` inherits `defaultPivotX/Y`. `Validate(width, height)` returns a list of
problems; `StripSprites()` gives FX frames in strip order.

### `InkPixelImporter.cs` — `AssetPostprocessor`

`OnPreprocessTexture` for every PNG under `Assets/InkPixel/Art/` (mirrors GPA's `PixelArtImport.cs`):
Sprite, PPU 16, Point filter, Uncompressed, no mipmaps, `alphaIsTransparency`, sRGB, max size 4096,
FullRect mesh, no fallback physics shape, NPOT none, Clamp wrap. `spriteImportMode` is **Multiple**
when a sidecar exists next to the PNG, else **Single** with a centered pivot. `GetVersion()` bumps
force a reimport when the rules change.

When a sidecar exists, `OnPreprocessTexture` also writes its rects into the running import
(`SpriteSlicer.ApplyToImporter(importer, path, saveAndReimport: false)`, the data-provider usage the
2D Sprite package documents for preprocessors), so a fresh or regenerated sheet lands sliced in one
import. `OnPostprocessAllAssets` then queues every imported/moved PNG that has a sidecar (and every
imported sidecar's PNG) and runs `SpriteSlicer.Apply` for them in one coalesced
`EditorApplication.delayCall`; this safety net catches a sidecar edited without its PNG changing. A
re-entrancy guard defers work queued by the reimports that pass triggers, and the follow-up pass finds
them unchanged. The sprite cache is invalidated whenever anything under `Art/` changes.

### `SpriteSlicer.cs`

`ApplyIfNeeded(texturePath)` / `Apply(texturePath)` / `ApplyToImporter(importer, path, saveAndReimport)`
write the sidecar's rects through `UnityEditor.U2D.Sprites.ISpriteEditorDataProvider` (never
`TextureImporter.spritesheet`):

1. `SpriteDataProviderFactories.Init()` → `GetSpriteEditorDataProviderFromObject(importer)` →
   `InitSpriteEditorDataProvider()`.
2. Texture size comes from the PNG's IHDR chunk (fallback `ITextureDataProvider`); sidecar `y` is
   top-left based, Unity's is bottom-left: `unityY = height - y - h`.
3. Desired `SpriteRect`s: name, rect, pivot (standard alignment when it matches one of the nine
   anchors, else Custom), border `(L, B, R, T)`, and a **deterministic `spriteID`** = MD5 of the
   sprite name parsed as a 32-hex-digit `GUID`, so sub-asset ids (and therefore references) survive
   regeneration on any machine.
4. Existing rects are compared by name/rect/pivot/border/id; identical → `Unchanged`, nothing written.
5. Otherwise `SetSpriteRects`, `ISpriteNameFileIdDataProvider.SetNameFileIdPairs` (in try/catch),
   `Apply()`, `SaveAndReimport()`.

The sidecar is validated against the real texture size first; a sidecar with problems is reported
with every problem listed and is not applied.

### `AnimationBuilder.cs`

For every sidecar with `animations`, loads the sheet's sprites by name
(`AssetDatabase.LoadAllAssetRepresentationsAtPath`, slicing first if the sheet is still unsliced)
and creates/updates `Generated/Animations/<sheet>_<anim>.asset` (`frames`, `fps`, `loop`, metadata).
An animation that references a missing sprite is skipped with an error naming the sprite.
For `kind: "fx"` sidecars with `stripFrames > 0` it also writes `<sheet>_strip.asset` from the strip
sprites in order (left to right), `fps = stripFps`, `loop = false` (GPA plays FX once;
`fps = 0` strips such as `Arrow`/`Shadow` are static).

### `TileBuilder.cs`

- `tiles` → `UnityEngine.Tilemaps.Tile` at `Generated/Tiles/<name>.asset` (`sprite`, `colliderType`
  from `none | sprite | grid`, white color).
- `tileRules` grouped by `ruleTile` → `RuleTile` (2D Tilemap Extras 6.0.3) at
  `Generated/Tiles/<ruleTile>.asset`: `m_DefaultSprite` / `m_DefaultColliderType` from
  `ruleTileDefaults` (fallback: the `m255` rule), one `TilingRule` per mask with `m_Sprites`,
  `m_Output = Animation` + `m_MinAnimationSpeed = m_MaxAnimationSpeed = animFps` when `animFrames`
  exist (else `Single`), `m_RuleTransform = Fixed`, collider = the default collider.
  Neighbors from the mask (`N=1 NE=2 E=4 SE=8 S=16 SW=32 W=64 NW=128`): the four edges are always
  `This`/`NotThis`; a corner is listed only when both adjacent edges are set (`This` if its bit is
  set, `NotThis` otherwise); other corners are omitted ("don't care"). Rules are sorted by popcount
  descending (most specific first), then mask descending; duplicate masks are skipped with an error.
- A Tile and a RuleTile may not share a name (same output path); the second one is refused with an
  error instead of overwriting.

### `InkPixelAssetUtil.cs`

`FindSprite(name)` (cached over every texture under `Art/`, warns on duplicate names),
`FindSpriteOwner`, `FindAnimation(sheet, anim)`, `FindStripAnimation(sheet)`, `FindTile(name)`,
`FindRuleTile(name)`, `AllClips(folder)`, `ArtTexturePaths()`, `SidecarTexturePaths()`,
`LoadSprites(texturePath, sliceIfEmpty)`, `EnsureFolder(path)`,
`CreateOrUpdateAsset<T>(path, Func<T,bool> configure)` (returns `Created | Updated | Unchanged |
Failed`; marks dirty only when `configure` reports a change), `SameSequence`, `InvalidateCaches()`.

### `InkPixelMenu.cs`

`Setup All`, `Validate Sidecars`, `Open Spec` and the `public static System.Action BuildDemoSceneHook`
that the demo scene builder assigns (for example from an `[InitializeOnLoadMethod]`).

## Generated asset naming

| Source | Asset | Type |
|---|---|---|
| sidecar `animations[].name` | `Generated/Animations/<sheet>_<name>.asset` (e.g. `hero_1_walk_down`) | `SpriteAnimation` |
| FX sidecar `stripFrames > 0` | `Generated/Animations/<sheet>_strip.asset` (e.g. `Slash_strip`) | `SpriteAnimation` |
| sidecar `tiles[].name` | `Generated/Tiles/<name>.asset` (e.g. `GrassA`) | `Tile` |
| sidecar `tileRules[].ruleTile` | `Generated/Tiles/<ruleTile>.asset` (e.g. `Road`, `Water`) | `RuleTile` |
| sliced sprites | sub-assets of the PNG named exactly as in the sidecar (`<sheet>_<descriptor>[_<dir>][_<frame>]`) | `Sprite` |

Sprite sub-asset ids are stable (MD5 of the name), so regenerating art never breaks scene or prefab
references as long as the sprite names stay the same. Only `.gitkeep` files are committed under
`Generated/`; everything else there is rebuilt by `Setup All`.

## Logging

Every message is prefixed `[InkPixel]`. Errors always name the sidecar/asset and the offending sprite,
animation, tile or mask; builders continue with the next item after an error and report
`created / updated / unchanged / failed` counts at the end.
