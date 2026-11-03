// InkPixel — the "<sheet>.sprites.json" sidecar schema (ASSET_SPEC §3, v2) for JsonUtility.
// Flat, [Serializable] classes only: no dictionaries, no nested arrays of arrays.
using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace InkPixel.EditorTools
{
    /// <summary>One sprite rect. x/y are measured from the TOP-LEFT of the PNG (the slicer flips y).</summary>
    [Serializable]
    public class SpriteEntry
    {
        public string name = "";
        public int x;
        public int y;
        public int w;
        public int h;
        /// <summary>Normalized pivot; NaN until resolved against the sidecar default in Normalize().</summary>
        public float pivotX = float.NaN;
        public float pivotY = float.NaN;
        public int borderL;
        public int borderB;
        public int borderR;
        public int borderT;
        public int cellX;
        public int cellY;
        public int cellW;
        public int cellH;
        public bool solid;
        public bool overlay;
        /// <summary>Name of the 1x1 ground sprite to draw under a prop; "" when none (GPA TileDef.ground).</summary>
        public string ground = "";
        /// <summary>Free comma-separated list.</summary>
        public string tags = "";

        public bool HasBorder
        {
            get { return borderL > 0 || borderB > 0 || borderR > 0 || borderT > 0; }
        }
    }

    /// <summary>A flip-book clip; Unity asset name is "&lt;sheet&gt;_&lt;name&gt;".</summary>
    [Serializable]
    public class AnimationEntry
    {
        public string name = "";
        public string state = "";
        /// <summary>"down" | "up" | "left" | "right" | "" (non-directional).</summary>
        public string direction = "";
        public float fps = 8f;
        public bool loop = true;
        public string[] frames = new string[0];
    }

    /// <summary>One UnityEngine.Tilemaps.Tile asset.</summary>
    [Serializable]
    public class TileEntry
    {
        public string name = "";
        public string sprite = "";
        /// <summary>"none" | "sprite" | "grid".</summary>
        public string collider = "none";
    }

    /// <summary>One tiling rule of a RuleTile; mask uses the blob bits N=1 NE=2 E=4 SE=8 S=16 SW=32 W=64 NW=128.</summary>
    [Serializable]
    public class TileRuleEntry
    {
        public string ruleTile = "";
        public string sprite = "";
        public int mask;
        public string[] animFrames = new string[0];
        public float animFps;

        public bool IsAnimated
        {
            get { return animFrames != null && animFrames.Length > 0; }
        }
    }

    /// <summary>Default sprite/collider of a RuleTile.</summary>
    [Serializable]
    public class RuleTileDefaultEntry
    {
        public string ruleTile = "";
        public string defaultSprite = "";
        /// <summary>"none" | "sprite" | "grid".</summary>
        public string collider = "none";
    }

    /// <summary>
    /// Root of a sidecar document. Load with <see cref="Load(string)"/> (texture path) or
    /// <see cref="LoadSidecar(string, string)"/> (json path). Missing fields keep their defaults.
    /// </summary>
    [Serializable]
    public class SidecarData
    {
        public const int SupportedVersion = 2;
        public const string KindTiles = "tiles";
        public const string KindAutotiles = "autotiles";
        public const string KindCharacter = "character";
        public const string KindIcons = "icons";
        public const string KindFx = "fx";
        public const string KindUi = "ui";
        public const string KindFace = "face";

        public int version;
        public string sheet = "";
        /// <summary>tiles | autotiles | character | icons | fx | ui | face</summary>
        public string kind = "";
        public int pixelsPerUnit = InkPixelPaths.PixelsPerUnit;
        public float defaultPivotX = 0.5f;
        public float defaultPivotY = 0f;
        public int cellSize = InkPixelPaths.CellSize;
        /// <summary>FX strips only: number of frames laid out in one row, left to right.</summary>
        public int stripFrames;
        /// <summary>FX strips only: playback fps (0 = static).</summary>
        public float stripFps;

        public SpriteEntry[] sprites = new SpriteEntry[0];
        public AnimationEntry[] animations = new AnimationEntry[0];
        public TileEntry[] tiles = new TileEntry[0];
        public TileRuleEntry[] tileRules = new TileRuleEntry[0];
        public RuleTileDefaultEntry[] ruleTileDefaults = new RuleTileDefaultEntry[0];

        /// <summary>Where this document was read from (not part of the JSON).</summary>
        [NonSerialized] public string sidecarPath = "";
        /// <summary>The PNG this document describes (not part of the JSON).</summary>
        [NonSerialized] public string texturePath = "";

        public bool HasSprites { get { return sprites != null && sprites.Length > 0; } }
        public bool HasAnimations { get { return animations != null && animations.Length > 0; } }
        public bool HasTiles { get { return tiles != null && tiles.Length > 0; } }
        public bool HasTileRules { get { return tileRules != null && tileRules.Length > 0; } }
        /// <summary>True for an FX strip sheet ("kind": "fx" with stripFrames &gt; 0).</summary>
        public bool IsFxStrip { get { return stripFrames > 0 && string.Equals(kind, KindFx, StringComparison.OrdinalIgnoreCase); } }

        // ------------------------------------------------------------------------------------ IO

        /// <summary>Sidecar path for a texture: "&lt;texture minus .png&gt;.sprites.json".</summary>
        public static string SidecarPathFor(string texturePath)
        {
            return InkPixelPaths.SidecarPathFor(texturePath);
        }

        /// <summary>True when the texture has a sidecar file on disk.</summary>
        public static bool Exists(string texturePath)
        {
            string p = SidecarPathFor(texturePath);
            return !string.IsNullOrEmpty(p) && File.Exists(p);
        }

        /// <summary>Loads the sidecar of <paramref name="texturePath"/>; null when absent or unreadable (errors are logged).</summary>
        public static SidecarData Load(string texturePath)
        {
            string sidecarPath = SidecarPathFor(texturePath);
            if (string.IsNullOrEmpty(sidecarPath) || !File.Exists(sidecarPath)) return null;
            return LoadSidecar(sidecarPath, texturePath);
        }

        /// <summary>Loads a sidecar JSON file directly; null when absent or unreadable (errors are logged).</summary>
        public static SidecarData LoadSidecar(string sidecarPath, string texturePath = null)
        {
            if (string.IsNullOrEmpty(sidecarPath) || !File.Exists(sidecarPath)) return null;
            try
            {
                string json = File.ReadAllText(sidecarPath);
                SidecarData data = JsonUtility.FromJson<SidecarData>(json);
                if (data == null)
                {
                    Debug.LogError("[InkPixel] Sidecar '" + sidecarPath + "' did not parse to a document.");
                    return null;
                }
                data.Normalize();
                data.sidecarPath = sidecarPath.Replace('\\', '/');
                data.texturePath = (texturePath ?? InkPixelPaths.TexturePathFor(sidecarPath)).Replace('\\', '/');
                if (string.IsNullOrEmpty(data.sheet)) data.sheet = InkPixelPaths.SheetNameOf(sidecarPath);
                if (data.version != SupportedVersion)
                    Debug.LogWarning("[InkPixel] Sidecar '" + sidecarPath + "' has version " + data.version + " (expected " + SupportedVersion + "); loading with defaults for missing fields.");
                return data;
            }
            catch (Exception ex)
            {
                Debug.LogError("[InkPixel] Failed to read sidecar '" + sidecarPath + "': " + ex.Message);
                return null;
            }
        }

        /// <summary>Replaces nulls by empty values and resolves per-sprite pivots against the defaults.</summary>
        public void Normalize()
        {
            sheet = sheet ?? "";
            kind = kind ?? "";
            if (float.IsNaN(defaultPivotX)) defaultPivotX = 0.5f;
            if (float.IsNaN(defaultPivotY)) defaultPivotY = 0f;
            if (pixelsPerUnit <= 0) pixelsPerUnit = InkPixelPaths.PixelsPerUnit;
            if (cellSize <= 0) cellSize = InkPixelPaths.CellSize;

            sprites = sprites ?? new SpriteEntry[0];
            animations = animations ?? new AnimationEntry[0];
            tiles = tiles ?? new TileEntry[0];
            tileRules = tileRules ?? new TileRuleEntry[0];
            ruleTileDefaults = ruleTileDefaults ?? new RuleTileDefaultEntry[0];

            for (int i = 0; i < sprites.Length; i++)
            {
                SpriteEntry s = sprites[i];
                if (s == null) { sprites[i] = s = new SpriteEntry(); }
                s.name = s.name ?? "";
                s.ground = s.ground ?? "";
                s.tags = s.tags ?? "";
                if (float.IsNaN(s.pivotX)) s.pivotX = defaultPivotX;
                if (float.IsNaN(s.pivotY)) s.pivotY = defaultPivotY;
            }
            for (int i = 0; i < animations.Length; i++)
            {
                AnimationEntry a = animations[i];
                if (a == null) { animations[i] = a = new AnimationEntry(); }
                a.name = a.name ?? "";
                a.state = a.state ?? "";
                a.direction = a.direction ?? "";
                a.frames = a.frames ?? new string[0];
            }
            for (int i = 0; i < tiles.Length; i++)
            {
                TileEntry t = tiles[i];
                if (t == null) { tiles[i] = t = new TileEntry(); }
                t.name = t.name ?? "";
                t.sprite = t.sprite ?? "";
                t.collider = string.IsNullOrEmpty(t.collider) ? "none" : t.collider;
            }
            for (int i = 0; i < tileRules.Length; i++)
            {
                TileRuleEntry r = tileRules[i];
                if (r == null) { tileRules[i] = r = new TileRuleEntry(); }
                r.ruleTile = r.ruleTile ?? "";
                r.sprite = r.sprite ?? "";
                r.animFrames = r.animFrames ?? new string[0];
            }
            for (int i = 0; i < ruleTileDefaults.Length; i++)
            {
                RuleTileDefaultEntry d = ruleTileDefaults[i];
                if (d == null) { ruleTileDefaults[i] = d = new RuleTileDefaultEntry(); }
                d.ruleTile = d.ruleTile ?? "";
                d.defaultSprite = d.defaultSprite ?? "";
                d.collider = string.IsNullOrEmpty(d.collider) ? "none" : d.collider;
            }
        }

        // --------------------------------------------------------------------------------- lookup

        public SpriteEntry FindSprite(string spriteName)
        {
            if (string.IsNullOrEmpty(spriteName)) return null;
            for (int i = 0; i < sprites.Length; i++)
                if (string.Equals(sprites[i].name, spriteName, StringComparison.Ordinal)) return sprites[i];
            return null;
        }

        public AnimationEntry FindAnimation(string animationName)
        {
            if (string.IsNullOrEmpty(animationName)) return null;
            for (int i = 0; i < animations.Length; i++)
                if (string.Equals(animations[i].name, animationName, StringComparison.Ordinal)) return animations[i];
            return null;
        }

        public RuleTileDefaultEntry FindRuleTileDefault(string ruleTileName)
        {
            if (string.IsNullOrEmpty(ruleTileName)) return null;
            for (int i = 0; i < ruleTileDefaults.Length; i++)
                if (string.Equals(ruleTileDefaults[i].ruleTile, ruleTileName, StringComparison.Ordinal)) return ruleTileDefaults[i];
            return null;
        }

        /// <summary>Unity asset name of an animation of this sheet: "&lt;sheet&gt;_&lt;anim&gt;".</summary>
        public string AnimationAssetName(string animationName)
        {
            return sheet + "_" + animationName;
        }

        /// <summary>The strip frames of an FX sheet in strip order (sorted by x, then y).</summary>
        public List<SpriteEntry> StripSprites()
        {
            var list = new List<SpriteEntry>(sprites);
            list.Sort((a, b) =>
            {
                int c = a.y.CompareTo(b.y);
                return c != 0 ? c : a.x.CompareTo(b.x);
            });
            if (stripFrames > 0 && list.Count > stripFrames) list.RemoveRange(stripFrames, list.Count - stripFrames);
            return list;
        }

        public static bool IsValidCollider(string collider)
        {
            if (string.IsNullOrEmpty(collider)) return false;
            string c = collider.ToLowerInvariant();
            return c == "none" || c == "sprite" || c == "grid";
        }

        // ----------------------------------------------------------------------------- validation

        /// <summary>
        /// Structural checks (§3 rules). Pass the real texture size for bounds checks, or 0/0 to skip them.
        /// Returns human-readable problems; empty when the document is usable.
        /// </summary>
        public List<string> Validate(int textureWidth, int textureHeight)
        {
            var problems = new List<string>();
            var names = new HashSet<string>(StringComparer.Ordinal);

            if (string.IsNullOrEmpty(sheet)) problems.Add("'sheet' is empty");
            if (sprites.Length == 0) problems.Add("'sprites' is empty");
            foreach (SpriteEntry s in sprites)
            {
                if (string.IsNullOrEmpty(s.name)) { problems.Add("a sprite entry has an empty name"); continue; }
                if (!names.Add(s.name)) problems.Add("duplicate sprite name '" + s.name + "'");
                if (s.w <= 0 || s.h <= 0 || s.x < 0 || s.y < 0)
                    problems.Add("sprite '" + s.name + "' has a degenerate rect (" + s.x + "," + s.y + "," + s.w + "," + s.h + ")");
                else if (textureWidth > 0 && textureHeight > 0 && (s.x + s.w > textureWidth || s.y + s.h > textureHeight))
                    problems.Add("sprite '" + s.name + "' rect (" + s.x + "," + s.y + "," + s.w + "," + s.h + ") exceeds the " + textureWidth + "x" + textureHeight + " texture");
                if (s.borderL < 0 || s.borderB < 0 || s.borderR < 0 || s.borderT < 0 || s.borderL + s.borderR > s.w || s.borderB + s.borderT > s.h)
                    problems.Add("sprite '" + s.name + "' has an invalid 9-slice border (" + s.borderL + "," + s.borderB + "," + s.borderR + "," + s.borderT + ")");
                if (float.IsNaN(s.pivotX) || float.IsNaN(s.pivotY))
                    problems.Add("sprite '" + s.name + "' has an unresolved pivot");
            }

            var animNames = new HashSet<string>(StringComparer.Ordinal);
            foreach (AnimationEntry a in animations)
            {
                if (string.IsNullOrEmpty(a.name)) { problems.Add("an animation entry has an empty name"); continue; }
                if (!animNames.Add(a.name)) problems.Add("duplicate animation name '" + a.name + "'");
                if (a.frames.Length == 0) problems.Add("animation '" + a.name + "' has no frames");
                if (a.fps <= 0f) problems.Add("animation '" + a.name + "' has fps " + a.fps + " (must be > 0)");
                foreach (string f in a.frames)
                    if (!names.Contains(f ?? "")) problems.Add("animation '" + a.name + "' references missing sprite '" + f + "'");
            }

            var tileNames = new HashSet<string>(StringComparer.Ordinal);
            foreach (TileEntry t in tiles)
            {
                if (string.IsNullOrEmpty(t.name)) { problems.Add("a tile entry has an empty name"); continue; }
                if (!tileNames.Add(t.name)) problems.Add("duplicate tile name '" + t.name + "'");
                if (!names.Contains(t.sprite)) problems.Add("tile '" + t.name + "' references missing sprite '" + t.sprite + "'");
                if (!IsValidCollider(t.collider)) problems.Add("tile '" + t.name + "' has unknown collider '" + t.collider + "'");
            }

            var ruleKeys = new HashSet<string>(StringComparer.Ordinal);
            foreach (TileRuleEntry r in tileRules)
            {
                if (string.IsNullOrEmpty(r.ruleTile)) { problems.Add("a tileRule entry has an empty ruleTile"); continue; }
                if (r.mask < 0 || r.mask > 255) problems.Add("tileRule " + r.ruleTile + "/m" + r.mask + " has a mask outside 0..255");
                if (!ruleKeys.Add(r.ruleTile + "#" + r.mask)) problems.Add("duplicate tileRule (" + r.ruleTile + ", m" + r.mask + ")");
                if (!names.Contains(r.sprite)) problems.Add("tileRule " + r.ruleTile + "/m" + r.mask + " references missing sprite '" + r.sprite + "'");
                foreach (string f in r.animFrames)
                    if (!names.Contains(f ?? "")) problems.Add("tileRule " + r.ruleTile + "/m" + r.mask + " references missing frame '" + f + "'");
                if (r.IsAnimated && r.animFps <= 0f) problems.Add("tileRule " + r.ruleTile + "/m" + r.mask + " is animated but animFps is " + r.animFps);
            }

            foreach (RuleTileDefaultEntry d in ruleTileDefaults)
            {
                if (string.IsNullOrEmpty(d.ruleTile)) { problems.Add("a ruleTileDefaults entry has an empty ruleTile"); continue; }
                if (!names.Contains(d.defaultSprite)) problems.Add("ruleTileDefault '" + d.ruleTile + "' references missing sprite '" + d.defaultSprite + "'");
                if (!IsValidCollider(d.collider)) problems.Add("ruleTileDefault '" + d.ruleTile + "' has unknown collider '" + d.collider + "'");
            }

            if (stripFrames > 0 && sprites.Length < stripFrames)
                problems.Add("stripFrames is " + stripFrames + " but only " + sprites.Length + " sprites are listed");
            if (stripFrames < 0) problems.Add("stripFrames is negative");

            return problems;
        }
    }
}
