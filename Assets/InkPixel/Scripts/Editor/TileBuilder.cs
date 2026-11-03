// InkPixel — builds Tile and RuleTile assets from sidecar "tiles" / "tileRules" / "ruleTileDefaults"
// (ASSET_SPEC §3, §4, §7.1). Output: Generated/Tiles/<Name>.asset.
//
// RuleTile field names verified against com.unity.2d.tilemap.extras 6.0.3 (Runtime/Tiles/RuleTile/RuleTile.cs,
// namespace UnityEngine): m_DefaultSprite, m_DefaultGameObject, m_DefaultColliderType, m_TilingRules;
// TilingRuleOutput { m_Id, m_Sprites, m_GameObject, m_MinAnimationSpeed, m_MaxAnimationSpeed, m_PerlinScale,
// m_Output (Single|Random|Animation), m_ColliderType, m_RandomTransform; Neighbor.This=1, NotThis=2 };
// TilingRule : TilingRuleOutput { m_Neighbors (List<int>), m_NeighborPositions (List<Vector3Int>),
// m_RuleTransform (Fixed|Rotated|MirrorX|MirrorY|MirrorXY|RotatedMirror) }.
using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;
using UnityEngine.Tilemaps;

namespace InkPixel.EditorTools
{
    public static class TileBuilder
    {
        private const string Log = "[InkPixel] ";

        // Blob mask bits (§3 / §4).
        public const int MaskN = 1;
        public const int MaskNE = 2;
        public const int MaskE = 4;
        public const int MaskSE = 8;
        public const int MaskS = 16;
        public const int MaskSW = 32;
        public const int MaskW = 64;
        public const int MaskNW = 128;

        private static readonly Vector3Int PosN = new Vector3Int(0, 1, 0);
        private static readonly Vector3Int PosNE = new Vector3Int(1, 1, 0);
        private static readonly Vector3Int PosE = new Vector3Int(1, 0, 0);
        private static readonly Vector3Int PosSE = new Vector3Int(1, -1, 0);
        private static readonly Vector3Int PosS = new Vector3Int(0, -1, 0);
        private static readonly Vector3Int PosSW = new Vector3Int(-1, -1, 0);
        private static readonly Vector3Int PosW = new Vector3Int(-1, 0, 0);
        private static readonly Vector3Int PosNW = new Vector3Int(-1, 1, 0);

        public struct Report
        {
            public int sheets;
            public int tiles;
            public int tilesCreated;
            public int tilesUpdated;
            public int tilesUnchanged;
            public int tilesFailed;
            public int ruleTiles;
            public int ruleTilesCreated;
            public int ruleTilesUpdated;
            public int ruleTilesUnchanged;
            public int ruleTilesFailed;

            public override string ToString()
            {
                return sheets + " sheet(s); Tiles " + tiles + " (" + tilesCreated + " created, " + tilesUpdated + " updated, " + tilesUnchanged + " unchanged, " + tilesFailed + " failed); RuleTiles " + ruleTiles + " (" + ruleTilesCreated + " created, " + ruleTilesUpdated + " updated, " + ruleTilesUnchanged + " unchanged, " + ruleTilesFailed + " failed)";
            }
        }

        [MenuItem("Tools/InkPixel/3. Build Tiles", false, 3)]
        public static void BuildMenu()
        {
            Report report = Build();
            AssetDatabase.SaveAssets();
            Debug.Log(Log + "Build Tiles: " + report + " -> " + InkPixelPaths.GenTiles);
        }

        /// <summary>Asset path of a Tile or RuleTile named <paramref name="name"/>.</summary>
        public static string TilePath(string name)
        {
            return InkPixelPaths.GenTiles + "/" + name + ".asset";
        }

        /// <summary>Creates or updates every Tile / RuleTile of every sidecar under Art. Idempotent.</summary>
        public static Report Build()
        {
            var report = new Report();
            if (!InkPixelAssetUtil.EnsureFolder(InkPixelPaths.GenTiles)) return report;

            List<string> textures = InkPixelAssetUtil.ArtTexturePaths();
            try
            {
                for (int i = 0; i < textures.Count; i++)
                {
                    string texturePath = textures[i];
                    SidecarData sidecar = SidecarData.Load(texturePath);
                    if (sidecar == null || (!sidecar.HasTiles && !sidecar.HasTileRules)) continue;
                    report.sheets++;
                    EditorUtility.DisplayProgressBar("InkPixel", "Tiles: " + sidecar.sheet, (i + 1f) / textures.Count);

                    Dictionary<string, Sprite> sprites = InkPixelAssetUtil.LoadSprites(texturePath, true);
                    if (sprites.Count == 0)
                    {
                        Debug.LogError(Log + "TileBuilder: '" + texturePath + "' has no sprites (run Tools/InkPixel/1. Reimport All Sprites). Skipped.");
                        report.tilesFailed += sidecar.tiles.Length;
                        report.ruleTilesFailed += CountRuleTiles(sidecar);
                        continue;
                    }

                    foreach (TileEntry tile in sidecar.tiles)
                        BuildTile(sidecar, tile, sprites, ref report);

                    foreach (KeyValuePair<string, List<TileRuleEntry>> group in GroupRules(sidecar))
                        BuildRuleTile(sidecar, group.Key, group.Value, sprites, ref report);
                }
            }
            finally
            {
                EditorUtility.ClearProgressBar();
            }
            return report;
        }

        // -------------------------------------------------------------------------------- tiles

        private static void BuildTile(SidecarData sidecar, TileEntry entry, Dictionary<string, Sprite> sprites, ref Report report)
        {
            report.tiles++;
            if (string.IsNullOrEmpty(entry.name))
            {
                Debug.LogError(Log + "TileBuilder: a tile in '" + sidecar.sidecarPath + "' has no name; skipped.");
                report.tilesFailed++;
                return;
            }
            Sprite sprite;
            if (!sprites.TryGetValue(entry.sprite ?? "", out sprite) || sprite == null)
            {
                Debug.LogError(Log + "TileBuilder: tile '" + entry.name + "' (" + sidecar.sidecarPath + ") references missing sprite '" + entry.sprite + "'; skipped.");
                report.tilesFailed++;
                return;
            }
            Tile.ColliderType collider = ParseCollider(entry.collider, "tile '" + entry.name + "'");
            string path = TilePath(entry.name);
            if (!CheckAssetType<Tile>(path, "tile '" + entry.name + "'"))
            {
                report.tilesFailed++;
                return;
            }

            AssetResult result = InkPixelAssetUtil.CreateOrUpdateAsset<Tile>(path, tile =>
            {
                bool changed = false;
                if (tile.sprite != sprite) { tile.sprite = sprite; changed = true; }
                if (tile.colliderType != collider) { tile.colliderType = collider; changed = true; }
                if (tile.color != Color.white) { tile.color = Color.white; changed = true; }
                return changed;
            });
            switch (result)
            {
                case AssetResult.Created: report.tilesCreated++; break;
                case AssetResult.Updated: report.tilesUpdated++; break;
                case AssetResult.Unchanged: report.tilesUnchanged++; break;
                default: report.tilesFailed++; break;
            }
        }

        // --------------------------------------------------------------------------- rule tiles

        private static int CountRuleTiles(SidecarData sidecar)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (TileRuleEntry r in sidecar.tileRules) names.Add(r.ruleTile ?? "");
            return names.Count;
        }

        /// <summary>Rules grouped by ruleTile in first-seen order.</summary>
        private static List<KeyValuePair<string, List<TileRuleEntry>>> GroupRules(SidecarData sidecar)
        {
            var order = new List<string>();
            var groups = new Dictionary<string, List<TileRuleEntry>>(StringComparer.Ordinal);
            foreach (TileRuleEntry r in sidecar.tileRules)
            {
                string key = r.ruleTile ?? "";
                List<TileRuleEntry> list;
                if (!groups.TryGetValue(key, out list))
                {
                    list = new List<TileRuleEntry>();
                    groups.Add(key, list);
                    order.Add(key);
                }
                list.Add(r);
            }
            var result = new List<KeyValuePair<string, List<TileRuleEntry>>>(order.Count);
            foreach (string key in order) result.Add(new KeyValuePair<string, List<TileRuleEntry>>(key, groups[key]));
            return result;
        }

        private static void BuildRuleTile(SidecarData sidecar, string ruleTileName, List<TileRuleEntry> rules, Dictionary<string, Sprite> sprites, ref Report report)
        {
            report.ruleTiles++;
            string context = "ruleTile '" + ruleTileName + "' (" + sidecar.sidecarPath + ")";
            if (string.IsNullOrEmpty(ruleTileName))
            {
                Debug.LogError(Log + "TileBuilder: " + rules.Count + " tileRules in '" + sidecar.sidecarPath + "' have an empty ruleTile; skipped.");
                report.ruleTilesFailed++;
                return;
            }

            // Default sprite / collider.
            RuleTileDefaultEntry defaults = sidecar.FindRuleTileDefault(ruleTileName);
            Sprite defaultSprite = null;
            Tile.ColliderType defaultCollider = Tile.ColliderType.None;
            if (defaults != null)
            {
                if (!sprites.TryGetValue(defaults.defaultSprite ?? "", out defaultSprite) || defaultSprite == null)
                    Debug.LogError(Log + "TileBuilder: " + context + " default sprite '" + defaults.defaultSprite + "' is missing.");
                defaultCollider = ParseCollider(defaults.collider, context);
            }
            else
            {
                Debug.LogWarning(Log + "TileBuilder: " + context + " has no ruleTileDefaults entry; using the m255 (or first) rule sprite and collider 'none'.");
            }
            if (defaultSprite == null)
            {
                TileRuleEntry fallback = rules.Find(r => r.mask == 255) ?? rules[0];
                Sprite s;
                if (sprites.TryGetValue(fallback.sprite ?? "", out s)) defaultSprite = s;
            }

            // Rules sorted by popcount (most specific first), then mask descending; duplicates dropped.
            var ordered = new List<TileRuleEntry>(rules);
            ordered.Sort((a, b) =>
            {
                int c = PopCount(b.mask).CompareTo(PopCount(a.mask));
                return c != 0 ? c : b.mask.CompareTo(a.mask);
            });

            var desired = new List<RuleTile.TilingRule>(ordered.Count);
            var seenMasks = new HashSet<int>();
            var problems = new List<string>();
            foreach (TileRuleEntry r in ordered)
            {
                if (r.mask < 0 || r.mask > 255) { problems.Add("mask " + r.mask + " is outside 0..255"); continue; }
                if (!seenMasks.Add(r.mask)) { problems.Add("duplicate mask " + r.mask); continue; }
                if (!IsCanonicalMask(r.mask))
                    Debug.LogWarning(Log + "TileBuilder: " + context + " mask " + r.mask + " is not canonical (a corner bit is set without both adjacent edges); its corner bits are ignored.");

                Sprite[] frames;
                if (r.IsAnimated)
                {
                    frames = new Sprite[r.animFrames.Length];
                    bool ok = true;
                    for (int i = 0; i < r.animFrames.Length; i++)
                    {
                        Sprite s;
                        if (sprites.TryGetValue(r.animFrames[i] ?? "", out s) && s != null) frames[i] = s;
                        else { problems.Add("m" + r.mask + " frame '" + r.animFrames[i] + "' is missing"); ok = false; }
                    }
                    if (!ok) continue;
                }
                else
                {
                    Sprite s;
                    if (!sprites.TryGetValue(r.sprite ?? "", out s) || s == null) { problems.Add("m" + r.mask + " sprite '" + r.sprite + "' is missing"); continue; }
                    frames = new Sprite[] { s };
                }

                var rule = new RuleTile.TilingRule();
                rule.m_Id = desired.Count;
                rule.m_Sprites = frames;
                rule.m_GameObject = null;
                rule.m_ColliderType = defaultCollider;
                rule.m_RuleTransform = RuleTile.TilingRuleOutput.Transform.Fixed;
                rule.m_RandomTransform = RuleTile.TilingRuleOutput.Transform.Fixed;
                rule.m_PerlinScale = 0.5f;
                if (r.IsAnimated)
                {
                    float fps = r.animFps > 0f ? r.animFps : 1f;
                    if (r.animFps <= 0f) Debug.LogWarning(Log + "TileBuilder: " + context + " m" + r.mask + " is animated with animFps " + r.animFps + "; using 1.");
                    rule.m_Output = RuleTile.TilingRuleOutput.OutputSprite.Animation;
                    rule.m_MinAnimationSpeed = fps;
                    rule.m_MaxAnimationSpeed = fps;
                }
                else
                {
                    rule.m_Output = RuleTile.TilingRuleOutput.OutputSprite.Single;
                    rule.m_MinAnimationSpeed = 1f;
                    rule.m_MaxAnimationSpeed = 1f;
                }
                rule.m_NeighborPositions = new List<Vector3Int>();
                rule.m_Neighbors = new List<int>();
                AddNeighbors(rule, r.mask);
                desired.Add(rule);
            }

            if (problems.Count > 0)
                Debug.LogError(Log + "TileBuilder: " + context + " skipped " + problems.Count + " rule(s):\n - " + string.Join("\n - ", problems));
            if (desired.Count == 0 || defaultSprite == null)
            {
                Debug.LogError(Log + "TileBuilder: " + context + " produced no usable rules or default sprite; asset not written.");
                report.ruleTilesFailed++;
                return;
            }
            if (desired.Count < 47)
                Debug.LogWarning(Log + "TileBuilder: " + context + " has " + desired.Count + " rules (a full blob set has 47).");

            string path = TilePath(ruleTileName);
            if (!CheckAssetType<RuleTile>(path, context))
            {
                report.ruleTilesFailed++;
                return;
            }

            Sprite finalDefault = defaultSprite;
            AssetResult result = InkPixelAssetUtil.CreateOrUpdateAsset<RuleTile>(path, tile =>
            {
                bool changed = false;
                if (tile.m_DefaultSprite != finalDefault) { tile.m_DefaultSprite = finalDefault; changed = true; }
                if (tile.m_DefaultGameObject != null) { tile.m_DefaultGameObject = null; changed = true; }
                if (tile.m_DefaultColliderType != defaultCollider) { tile.m_DefaultColliderType = defaultCollider; changed = true; }
                if (!RulesEqual(tile.m_TilingRules, desired)) { tile.m_TilingRules = new List<RuleTile.TilingRule>(desired); changed = true; }
                return changed;
            });
            switch (result)
            {
                case AssetResult.Created: report.ruleTilesCreated++; break;
                case AssetResult.Updated: report.ruleTilesUpdated++; break;
                case AssetResult.Unchanged: report.ruleTilesUnchanged++; break;
                default: report.ruleTilesFailed++; break;
            }
        }

        /// <summary>
        /// Neighbor rules for a blob mask (§3/§4): the four edges are always This/NotThis; a corner is
        /// listed only when both adjacent edges are set (This when its bit is set, NotThis otherwise);
        /// other corners are left out, i.e. "don't care". Order follows Unity's default 3x3 layout.
        /// </summary>
        public static void AddNeighbors(RuleTile.TilingRule rule, int mask)
        {
            bool n = (mask & MaskN) != 0;
            bool e = (mask & MaskE) != 0;
            bool s = (mask & MaskS) != 0;
            bool w = (mask & MaskW) != 0;

            if (n && w) AddNeighbor(rule, PosNW, (mask & MaskNW) != 0);
            AddNeighbor(rule, PosN, n);
            if (n && e) AddNeighbor(rule, PosNE, (mask & MaskNE) != 0);
            AddNeighbor(rule, PosW, w);
            AddNeighbor(rule, PosE, e);
            if (s && w) AddNeighbor(rule, PosSW, (mask & MaskSW) != 0);
            AddNeighbor(rule, PosS, s);
            if (s && e) AddNeighbor(rule, PosSE, (mask & MaskSE) != 0);
        }

        private static void AddNeighbor(RuleTile.TilingRule rule, Vector3Int position, bool present)
        {
            rule.m_NeighborPositions.Add(position);
            rule.m_Neighbors.Add(present ? RuleTile.TilingRuleOutput.Neighbor.This : RuleTile.TilingRuleOutput.Neighbor.NotThis);
        }

        /// <summary>True when every set corner bit has both adjacent edge bits set (§3 blob convention).</summary>
        public static bool IsCanonicalMask(int mask)
        {
            bool n = (mask & MaskN) != 0, e = (mask & MaskE) != 0, s = (mask & MaskS) != 0, w = (mask & MaskW) != 0;
            if ((mask & MaskNE) != 0 && !(n && e)) return false;
            if ((mask & MaskSE) != 0 && !(s && e)) return false;
            if ((mask & MaskSW) != 0 && !(s && w)) return false;
            if ((mask & MaskNW) != 0 && !(n && w)) return false;
            return true;
        }

        public static int PopCount(int value)
        {
            int count = 0;
            uint v = (uint)value;
            while (v != 0)
            {
                v &= v - 1;
                count++;
            }
            return count;
        }

        /// <summary>"none" | "sprite" | "grid" (case-insensitive) to Tile.ColliderType; unknown values warn and give None.</summary>
        public static Tile.ColliderType ParseCollider(string collider, string context)
        {
            switch ((collider ?? "").Trim().ToLowerInvariant())
            {
                case "": case "none": return Tile.ColliderType.None;
                case "sprite": return Tile.ColliderType.Sprite;
                case "grid": return Tile.ColliderType.Grid;
                default:
                    Debug.LogWarning(Log + "TileBuilder: unknown collider '" + collider + "' for " + context + "; using None.");
                    return Tile.ColliderType.None;
            }
        }

        /// <summary>Guards against overwriting a different asset type at the same path (e.g. a Tile named like a RuleTile).</summary>
        private static bool CheckAssetType<T>(string path, string context) where T : UnityEngine.Object
        {
            UnityEngine.Object main = AssetDatabase.LoadMainAssetAtPath(path);
            if (main == null || main is T) return true;
            Debug.LogError(Log + "TileBuilder: " + context + " wants to write '" + path + "' but a " + main.GetType().Name + " already lives there; rename one of them.");
            return false;
        }

        public static bool RulesEqual(List<RuleTile.TilingRule> a, List<RuleTile.TilingRule> b)
        {
            if (a == null || b == null) return a == b;
            if (a.Count != b.Count) return false;
            for (int i = 0; i < a.Count; i++)
            {
                RuleTile.TilingRule x = a[i], y = b[i];
                if (x == null || y == null) return false;
                if (x.m_Id != y.m_Id) return false;
                if (x.m_Output != y.m_Output) return false;
                if (x.m_ColliderType != y.m_ColliderType) return false;
                if (x.m_RuleTransform != y.m_RuleTransform) return false;
                if (x.m_RandomTransform != y.m_RandomTransform) return false;
                if (x.m_GameObject != y.m_GameObject) return false;
                if (!Mathf.Approximately(x.m_MinAnimationSpeed, y.m_MinAnimationSpeed)) return false;
                if (!Mathf.Approximately(x.m_MaxAnimationSpeed, y.m_MaxAnimationSpeed)) return false;
                if (!Mathf.Approximately(x.m_PerlinScale, y.m_PerlinScale)) return false;
                if (!InkPixelAssetUtil.SameSequence(x.m_Sprites, y.m_Sprites)) return false;
                if (!InkPixelAssetUtil.SameSequence(x.m_NeighborPositions, y.m_NeighborPositions)) return false;
                if (!InkPixelAssetUtil.SameSequence(x.m_Neighbors, y.m_Neighbors)) return false;
            }
            return true;
        }
    }
}
