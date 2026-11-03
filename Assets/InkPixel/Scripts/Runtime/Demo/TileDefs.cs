// InkPixel demo — letter → tile / NPC definitions mirroring GPA's World/RegionData.cs (TileDef, NpcDef)
// plus a JsonUtility reader for the resolved tiledefs JSON of ASSET_SPEC §7.3.
using System;
using System.Collections.Generic;
using UnityEngine;

namespace InkPixel.Demo
{
    /// <summary>
    /// What one map letter is (GPA TileDef). A size larger than 1x1 (or <c>overlay</c>) makes it a prop
    /// drawn over its <c>ground</c> letter, anchored at the letter's cell = the prop's TOP-LEFT cell.
    /// </summary>
    [Serializable]
    public class TileDef
    {
        [Tooltip("The map letter (one character).")]
        public string key = "";
        [Tooltip("Sheet the sprite is sliced from at runtime.")]
        public Texture2D sheet;
        [Tooltip("Top-left cell in the sheet, in 16px cells counted from the TOP-LEFT of the PNG.")]
        public Vector2Int cell;
        [Tooltip("Size in cells. Anything but 1x1 is a prop placed with its letter at the top-left.")]
        public Vector2Int size = Vector2Int.one;
        [Tooltip("Blocks walking (the whole footprint for props).")]
        public bool solid;
        [Tooltip("Letter of the 1x1 ground tile drawn under a prop.")]
        public string ground = ".";
        [Tooltip("Draw over the ground even when 1x1 (reeds, flowers, small props with transparency).")]
        public bool overlay;
        [Tooltip("GPA: node entered when the hero steps here (informational in the demo).")]
        public string portal = "";
        [Tooltip("GPA: encounter node rolled when the hero steps here (informational in the demo).")]
        public string encounterNode = "";

        /// <summary>GPA: <c>def.size != Vector2Int.one || def.overlay</c>.</summary>
        public bool IsProp
        {
            get { return size != Vector2Int.one || overlay; }
        }

        public char Key
        {
            get { return string.IsNullOrEmpty(key) ? '\0' : key[0]; }
        }

        public bool SameAs(TileDef o)
        {
            return o != null && key == o.key && sheet == o.sheet && cell == o.cell && size == o.size && solid == o.solid
                && ground == o.ground && overlay == o.overlay && portal == o.portal && encounterNode == o.encounterNode;
        }
    }

    /// <summary>A walking NPC (GPA NpcDef). With <c>prop</c> set it is drawn as a still object instead.</summary>
    [Serializable]
    public class NpcDef
    {
        [Tooltip("The map letter (one character).")]
        public string key = "";
        [Tooltip("Display name (also the GameObject name).")]
        public string name = "";
        [Tooltip("Character sheet (128x64, §5.1): walk frame [down, 0] is shown.")]
        public Texture2D sheet;
        [Tooltip("When set, a 1x1 cell of this sheet is drawn instead of the character (GPA: 나물, 그루터기).")]
        public Texture2D prop;
        [Tooltip("Cell of the prop in its sheet (from the top-left).")]
        public Vector2Int propCell;
        [Tooltip("Optional 32x32 face (<name>_face.png) shown by the talk panel. Not part of GPA's NpcDef.")]
        public Texture2D face;

        public char Key
        {
            get { return string.IsNullOrEmpty(key) ? '\0' : key[0]; }
        }

        public bool SameAs(NpcDef o)
        {
            return o != null && key == o.key && name == o.name && sheet == o.sheet && prop == o.prop && propCell == o.propCell && face == o.face;
        }
    }

    // ------------------------------------------------------------------ JSON mirror (§7.3 resolved format)

    /// <summary>One "tiles" entry of tiledefs_&lt;region&gt;.json. <c>sprite</c> is an optional sprite name the editor builder resolves to cells.</summary>
    [Serializable]
    public class TileDefJson
    {
        public string key = "";
        public string sprite = "";
        public string sheet = "";
        public int cellX;
        public int cellY;
        public int sizeX = 1;
        public int sizeY = 1;
        public bool solid;
        public string ground = ".";
        public bool overlay;
        public string portal = "";
        public string encounterNode = "";
    }

    /// <summary>One "npcs" entry. <c>propSprite</c> is an optional sprite name resolved by the editor builder.</summary>
    [Serializable]
    public class NpcDefJson
    {
        public string key = "";
        public string name = "";
        public string sheet = "";
        public string prop = "";
        public string propSprite = "";
        public int propCellX;
        public int propCellY;
    }

    /// <summary>Root of tiledefs_&lt;region&gt;.json (Integration/GPA, Tools/gpa_sim/resolve_tiledefs.py).</summary>
    [Serializable]
    public class TileDefsJson
    {
        public string region = "";
        public string sheetBase = "";
        public string specialGround = "=";
        public string playerSheet = "";
        public List<TileDefJson> tiles = new List<TileDefJson>();
        public List<NpcDefJson> npcs = new List<NpcDefJson>();

        /// <summary>sheetBase.TrimEnd('/') + "/" + rel, like GpaInkPixelTools.LoadTexture; rel alone when sheetBase is empty.</summary>
        public static string Combine(string sheetBase, string rel)
        {
            if (string.IsNullOrEmpty(rel)) return "";
            rel = rel.Replace('\\', '/');
            if (string.IsNullOrEmpty(sheetBase)) return rel;
            return sheetBase.Replace('\\', '/').TrimEnd('/') + "/" + rel.TrimStart('/');
        }

        public void Normalize()
        {
            region = region ?? "";
            sheetBase = sheetBase ?? "";
            specialGround = string.IsNullOrEmpty(specialGround) ? "=" : specialGround;
            playerSheet = playerSheet ?? "";
            tiles = tiles ?? new List<TileDefJson>();
            npcs = npcs ?? new List<NpcDefJson>();
            for (int i = 0; i < tiles.Count; i++)
            {
                TileDefJson t = tiles[i];
                if (t == null) { tiles[i] = t = new TileDefJson(); }
                t.key = t.key ?? "";
                t.sprite = t.sprite ?? "";
                t.sheet = t.sheet ?? "";
                t.ground = string.IsNullOrEmpty(t.ground) ? "." : t.ground;
                t.portal = t.portal ?? "";
                t.encounterNode = t.encounterNode ?? "";
                if (t.sizeX < 1) t.sizeX = 1;
                if (t.sizeY < 1) t.sizeY = 1;
            }
            for (int i = 0; i < npcs.Count; i++)
            {
                NpcDefJson n = npcs[i];
                if (n == null) { npcs[i] = n = new NpcDefJson(); }
                n.key = n.key ?? "";
                n.name = n.name ?? "";
                n.sheet = n.sheet ?? "";
                n.prop = n.prop ?? "";
                n.propSprite = n.propSprite ?? "";
            }
        }
    }

    // ---------------------------------------------------------------------------------- the asset

    /// <summary>
    /// The letter table of a region (GPA RegionData without the layout): tiles, NPCs and the
    /// start / exit / special-ground letters. Built by the demo scene builder from
    /// Assets/InkPixel/Demo/demo_tiledefs.json, or at runtime with <see cref="FromJson(TextAsset, Func{string, Texture2D})"/>.
    /// </summary>
    [CreateAssetMenu(fileName = "TileDefs", menuName = "InkPixel/Tile Defs", order = 101)]
    public class TileDefs : ScriptableObject
    {
        [Tooltip("Region name (informational).")]
        public string region = "";
        [Tooltip("Letter -> tile.")]
        public List<TileDef> tiles = new List<TileDef>();
        [Tooltip("Letter -> NPC.")]
        public List<NpcDef> npcs = new List<NpcDef>();
        [Tooltip("Letter where the player starts (GPA RegionData.start).")]
        public string start = "@";
        [Tooltip("Letter that leaves the region (GPA RegionData.exit).")]
        public string exit = "E";
        [Tooltip("Ground letter drawn under start, exit and NPC cells (GPA RegionData.specialGround).")]
        public string specialGround = "=";
        [Tooltip("Default player sheet (from the JSON 'playerSheet'); RegionViewer.playerSheet overrides it.")]
        public Texture2D playerSheet;

        /// <summary>GPA RegionData.Tile(c): the first tile whose key starts with <paramref name="c"/>, or null.</summary>
        public TileDef Tile(char c)
        {
            for (int i = 0; i < tiles.Count; i++)
            {
                TileDef t = tiles[i];
                if (t != null && !string.IsNullOrEmpty(t.key) && t.key[0] == c) return t;
            }
            return null;
        }

        /// <summary>GPA RegionData.Npc(c): the first NPC whose key starts with <paramref name="c"/>, or null.</summary>
        public NpcDef Npc(char c)
        {
            for (int i = 0; i < npcs.Count; i++)
            {
                NpcDef n = npcs[i];
                if (n != null && !string.IsNullOrEmpty(n.key) && n.key[0] == c) return n;
            }
            return null;
        }

        /// <summary>True when the letter is drawn over the special ground (start, exit or an NPC) — GPA Build's "special".</summary>
        public bool IsSpecial(char c)
        {
            return (start ?? "").IndexOf(c) == 0 || (exit ?? "").IndexOf(c) == 0 || Npc(c) != null;
        }

        // ------------------------------------------------------------------------------------ JSON

        /// <summary>Parses the §7.3 JSON text; null (with an error logged) when it cannot be read.</summary>
        public static TileDefsJson Parse(string json)
        {
            if (string.IsNullOrEmpty(json))
            {
                Debug.LogError("[InkPixel] TileDefs.Parse: empty JSON.");
                return null;
            }
            try
            {
                TileDefsJson data = JsonUtility.FromJson<TileDefsJson>(json);
                if (data == null)
                {
                    Debug.LogError("[InkPixel] TileDefs.Parse: the JSON did not parse to a document.");
                    return null;
                }
                data.Normalize();
                return data;
            }
            catch (Exception ex)
            {
                Debug.LogError("[InkPixel] TileDefs.Parse failed: " + ex.Message);
                return null;
            }
        }

        /// <summary>
        /// Creates a TileDefs instance from a resolved tiledefs JSON TextAsset. <paramref name="resolveSheet"/>
        /// receives <c>sheetBase + sheet</c> (e.g. "Assets/InkPixel/Art/Tiles/town.png") and returns the texture
        /// (AssetDatabase in the editor, Resources.Load at runtime, ...). Never throws; missing sheets are warned about.
        /// </summary>
        public static TileDefs FromJson(TextAsset json, Func<string, Texture2D> resolveSheet)
        {
            return FromJson(json != null ? json.text : null, resolveSheet);
        }

        /// <summary>See <see cref="FromJson(TextAsset, Func{string, Texture2D})"/>.</summary>
        public static TileDefs FromJson(string json, Func<string, Texture2D> resolveSheet)
        {
            var defs = CreateInstance<TileDefs>();
            defs.name = "TileDefs";
            TileDefsJson data = Parse(json);
            if (data != null)
            {
                defs.Populate(data, resolveSheet);
                if (!string.IsNullOrEmpty(data.region)) defs.name = "TileDefs_" + data.region;
            }
            return defs;
        }

        /// <summary>
        /// Fills this asset from parsed JSON. Returns true when anything changed (so editor builders can
        /// mark the asset dirty only when needed). Sheets are resolved through <paramref name="resolveSheet"/>.
        /// </summary>
        public bool Populate(TileDefsJson data, Func<string, Texture2D> resolveSheet)
        {
            if (data == null) return false;
            data.Normalize();
            bool changed = false;

            var newTiles = new List<TileDef>(data.tiles.Count);
            foreach (TileDefJson t in data.tiles)
            {
                if (string.IsNullOrEmpty(t.key))
                {
                    Debug.LogWarning("[InkPixel] TileDefs: a tile entry has no key; skipped.");
                    continue;
                }
                var def = new TileDef();
                def.key = t.key;
                def.sheet = Resolve(data, t.sheet, resolveSheet, "tile '" + t.key + "'");
                def.cell = new Vector2Int(t.cellX, t.cellY);
                def.size = new Vector2Int(Mathf.Max(1, t.sizeX), Mathf.Max(1, t.sizeY));
                def.solid = t.solid;
                def.ground = string.IsNullOrEmpty(t.ground) ? "." : t.ground;
                def.overlay = t.overlay;
                def.portal = t.portal ?? "";
                def.encounterNode = t.encounterNode ?? "";
                newTiles.Add(def);
            }

            var newNpcs = new List<NpcDef>(data.npcs.Count);
            foreach (NpcDefJson n in data.npcs)
            {
                if (string.IsNullOrEmpty(n.key))
                {
                    Debug.LogWarning("[InkPixel] TileDefs: an NPC entry has no key; skipped.");
                    continue;
                }
                var def = new NpcDef();
                def.key = n.key;
                def.name = string.IsNullOrEmpty(n.name) ? n.key : n.name;
                def.sheet = Resolve(data, n.sheet, resolveSheet, "NPC '" + def.name + "'");
                def.prop = Resolve(data, n.prop, resolveSheet, "NPC '" + def.name + "' prop");
                def.propCell = new Vector2Int(n.propCellX, n.propCellY);
                // Keep an already assigned face (the editor builder fills it after Populate).
                NpcDef old = Npc(def.Key);
                if (old != null) def.face = old.face;
                newNpcs.Add(def);
            }

            if (!SameTiles(tiles, newTiles)) { tiles = newTiles; changed = true; }
            if (!SameNpcs(npcs, newNpcs)) { npcs = newNpcs; changed = true; }

            string newRegion = data.region ?? "";
            if (region != newRegion) { region = newRegion; changed = true; }
            string newSpecial = string.IsNullOrEmpty(data.specialGround) ? "=" : data.specialGround;
            if (specialGround != newSpecial) { specialGround = newSpecial; changed = true; }
            Texture2D newPlayer = Resolve(data, data.playerSheet, resolveSheet, "playerSheet");
            if (playerSheet != newPlayer) { playerSheet = newPlayer; changed = true; }
            return changed;
        }

        private static Texture2D Resolve(TileDefsJson data, string rel, Func<string, Texture2D> resolveSheet, string what)
        {
            if (string.IsNullOrEmpty(rel)) return null;
            string path = TileDefsJson.Combine(data.sheetBase, rel);
            if (resolveSheet == null)
            {
                Debug.LogWarning("[InkPixel] TileDefs: no sheet resolver; " + what + " keeps no sheet (" + path + ").");
                return null;
            }
            Texture2D tex = null;
            try
            {
                tex = resolveSheet(path);
            }
            catch (Exception ex)
            {
                Debug.LogWarning("[InkPixel] TileDefs: resolving '" + path + "' for " + what + " threw " + ex.GetType().Name + ": " + ex.Message);
            }
            if (tex == null) Debug.LogWarning("[InkPixel] TileDefs: sheet not found for " + what + ": '" + path + "'.");
            return tex;
        }

        private static bool SameTiles(List<TileDef> a, List<TileDef> b)
        {
            if (a == null || b == null || a.Count != b.Count) return false;
            for (int i = 0; i < a.Count; i++)
                if (a[i] == null || !a[i].SameAs(b[i])) return false;
            return true;
        }

        private static bool SameNpcs(List<NpcDef> a, List<NpcDef> b)
        {
            if (a == null || b == null || a.Count != b.Count) return false;
            for (int i = 0; i < a.Count; i++)
                if (a[i] == null || !a[i].SameAs(b[i])) return false;
            return true;
        }
    }
}
