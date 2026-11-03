// InkPixel — shared editor helpers: sprite lookup cache, generated-asset lookups, folder and
// create-or-update utilities used by every Tools/InkPixel command (ASSET_SPEC §7.1).
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Tilemaps;

namespace InkPixel.EditorTools
{
    /// <summary>Outcome of <see cref="InkPixelAssetUtil.CreateOrUpdateAsset{T}"/>.</summary>
    public enum AssetResult
    {
        Created,
        Updated,
        Unchanged,
        Failed
    }

    public static class InkPixelAssetUtil
    {
        private const string Log = "[InkPixel] ";

        private static Dictionary<string, Sprite> spriteCache;
        private static Dictionary<string, string> spriteOwnerCache;

        /// <summary>Drops the sprite cache; called automatically whenever something under Art is (re)imported.</summary>
        public static void InvalidateCaches()
        {
            spriteCache = null;
            spriteOwnerCache = null;
        }

        // ------------------------------------------------------------------------------ textures

        /// <summary>Every PNG under Assets/InkPixel/Art, sorted (ordinal) for deterministic passes.</summary>
        public static List<string> ArtTexturePaths()
        {
            var result = new List<string>();
            if (!AssetDatabase.IsValidFolder(InkPixelPaths.Art)) return result;
            string[] guids = AssetDatabase.FindAssets("t:Texture2D", new[] { InkPixelPaths.Art });
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (string guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (string.IsNullOrEmpty(path) || !InkPixelImporter.IsInkPixelTexture(path)) continue;
                if (seen.Add(path)) result.Add(path);
            }
            result.Sort(StringComparer.Ordinal);
            return result;
        }

        /// <summary>The subset of <see cref="ArtTexturePaths"/> that has a sidecar on disk.</summary>
        public static List<string> SidecarTexturePaths()
        {
            List<string> all = ArtTexturePaths();
            var result = new List<string>(all.Count);
            foreach (string p in all)
                if (SidecarData.Exists(p)) result.Add(p);
            return result;
        }

        /// <summary>
        /// Sprites of one texture by name (sub-assets of a Multiple sheet, or the single sprite of a
        /// Single texture). With <paramref name="sliceIfEmpty"/> an unsliced sheet that has a sidecar is
        /// sliced first (SpriteSlicer.Apply) and then loaded again.
        /// </summary>
        public static Dictionary<string, Sprite> LoadSprites(string texturePath, bool sliceIfEmpty = false)
        {
            var dict = CollectSprites(texturePath);
            if (dict.Count == 0 && sliceIfEmpty && SidecarData.Exists(texturePath))
            {
                if (SpriteSlicer.Apply(texturePath) == SpriteSlicer.SliceResult.Applied)
                    dict = CollectSprites(texturePath);
            }
            return dict;
        }

        private static Dictionary<string, Sprite> CollectSprites(string texturePath)
        {
            var dict = new Dictionary<string, Sprite>(StringComparer.Ordinal);
            if (string.IsNullOrEmpty(texturePath)) return dict;
            UnityEngine.Object[] representations = AssetDatabase.LoadAllAssetRepresentationsAtPath(texturePath);
            if (representations != null)
            {
                foreach (UnityEngine.Object o in representations)
                {
                    var sprite = o as Sprite;
                    if (sprite == null) continue;
                    if (dict.ContainsKey(sprite.name))
                        Debug.LogWarning(Log + "Duplicate sprite name '" + sprite.name + "' in '" + texturePath + "'; keeping the first.");
                    else
                        dict.Add(sprite.name, sprite);
                }
            }
            if (dict.Count == 0)
            {
                var single = AssetDatabase.LoadAssetAtPath<Sprite>(texturePath);
                if (single != null) dict.Add(single.name, single);
            }
            return dict;
        }

        // ------------------------------------------------------------------------------- lookups

        /// <summary>A sprite by its (globally unique, sheet-prefixed) name, searched over every texture under Art. Cached.</summary>
        public static Sprite FindSprite(string spriteName)
        {
            if (string.IsNullOrEmpty(spriteName)) return null;
            EnsureSpriteCache();
            Sprite sprite;
            return spriteCache.TryGetValue(spriteName, out sprite) ? sprite : null;
        }

        /// <summary>Texture path that owns a sprite name (null when unknown).</summary>
        public static string FindSpriteOwner(string spriteName)
        {
            if (string.IsNullOrEmpty(spriteName)) return null;
            EnsureSpriteCache();
            string owner;
            return spriteOwnerCache.TryGetValue(spriteName, out owner) ? owner : null;
        }

        /// <summary>Number of sprites known to the cache (builds it on first use).</summary>
        public static int CachedSpriteCount
        {
            get
            {
                EnsureSpriteCache();
                return spriteCache.Count;
            }
        }

        private static void EnsureSpriteCache()
        {
            if (spriteCache != null) return;
            spriteCache = new Dictionary<string, Sprite>(StringComparer.Ordinal);
            spriteOwnerCache = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (string texturePath in ArtTexturePaths())
            {
                foreach (KeyValuePair<string, Sprite> kv in CollectSprites(texturePath))
                {
                    if (spriteCache.ContainsKey(kv.Key))
                    {
                        Debug.LogWarning(Log + "Sprite name '" + kv.Key + "' exists in both '" + spriteOwnerCache[kv.Key] + "' and '" + texturePath + "'; FindSprite returns the first.");
                        continue;
                    }
                    spriteCache.Add(kv.Key, kv.Value);
                    spriteOwnerCache.Add(kv.Key, texturePath);
                }
            }
        }

        /// <summary>The generated clip "Generated/Animations/&lt;sheet&gt;_&lt;anim&gt;.asset", or null.</summary>
        public static SpriteAnimation FindAnimation(string sheet, string animationName)
        {
            if (string.IsNullOrEmpty(sheet) || string.IsNullOrEmpty(animationName)) return null;
            return AssetDatabase.LoadAssetAtPath<SpriteAnimation>(AnimationBuilder.ClipPath(sheet, animationName));
        }

        /// <summary>The generated FX strip clip "Generated/Animations/&lt;sheet&gt;_strip.asset", or null.</summary>
        public static SpriteAnimation FindStripAnimation(string sheet)
        {
            if (string.IsNullOrEmpty(sheet)) return null;
            return AssetDatabase.LoadAssetAtPath<SpriteAnimation>(AnimationBuilder.StripClipPath(sheet));
        }

        /// <summary>The generated Tile "Generated/Tiles/&lt;name&gt;.asset", or null.</summary>
        public static Tile FindTile(string name)
        {
            if (string.IsNullOrEmpty(name)) return null;
            return AssetDatabase.LoadAssetAtPath<Tile>(TileBuilder.TilePath(name));
        }

        /// <summary>The generated RuleTile "Generated/Tiles/&lt;name&gt;.asset", or null.</summary>
        public static RuleTile FindRuleTile(string name)
        {
            if (string.IsNullOrEmpty(name)) return null;
            return AssetDatabase.LoadAssetAtPath<RuleTile>(TileBuilder.TilePath(name));
        }

        /// <summary>Every AudioClip under <paramref name="folder"/> (e.g. InkPixelPaths.Sfx), sorted by name.</summary>
        public static AudioClip[] AllClips(string folder)
        {
            if (string.IsNullOrEmpty(folder) || !AssetDatabase.IsValidFolder(folder)) return new AudioClip[0];
            string[] guids = AssetDatabase.FindAssets("t:AudioClip", new[] { folder });
            var clips = new List<AudioClip>(guids.Length);
            foreach (string guid in guids)
            {
                var clip = AssetDatabase.LoadAssetAtPath<AudioClip>(AssetDatabase.GUIDToAssetPath(guid));
                if (clip != null) clips.Add(clip);
            }
            clips.Sort((a, b) => string.CompareOrdinal(a.name, b.name));
            return clips.ToArray();
        }

        // ------------------------------------------------------------------------- asset writing

        /// <summary>Creates every missing segment of an "Assets/..." folder path. Returns false (and logs) on failure.</summary>
        public static bool EnsureFolder(string folderPath)
        {
            if (string.IsNullOrEmpty(folderPath)) return false;
            string path = folderPath.Replace('\\', '/').TrimEnd('/');
            if (AssetDatabase.IsValidFolder(path)) return true;
            string[] parts = path.Split('/');
            if (parts.Length == 0 || parts[0] != "Assets")
            {
                Debug.LogError(Log + "EnsureFolder: '" + folderPath + "' is not under Assets/.");
                return false;
            }
            string current = parts[0];
            for (int i = 1; i < parts.Length; i++)
            {
                if (string.IsNullOrEmpty(parts[i])) continue;
                string next = current + "/" + parts[i];
                if (!AssetDatabase.IsValidFolder(next))
                {
                    string guid = AssetDatabase.CreateFolder(current, parts[i]);
                    if (string.IsNullOrEmpty(guid))
                    {
                        Debug.LogError(Log + "EnsureFolder: could not create '" + next + "'.");
                        return false;
                    }
                }
                current = next;
            }
            return true;
        }

        /// <summary>
        /// Loads the ScriptableObject at <paramref name="assetPath"/> or creates it, then runs
        /// <paramref name="configure"/>, which must return true only when it changed something. The asset
        /// is marked dirty only on change, so repeated runs are no-ops (save with AssetDatabase.SaveAssets).
        /// </summary>
        public static AssetResult CreateOrUpdateAsset<T>(string assetPath, Func<T, bool> configure) where T : ScriptableObject
        {
            if (string.IsNullOrEmpty(assetPath))
            {
                Debug.LogError(Log + "CreateOrUpdateAsset: empty path.");
                return AssetResult.Failed;
            }
            string path = assetPath.Replace('\\', '/');
            try
            {
                var existing = AssetDatabase.LoadAssetAtPath<T>(path);
                if (existing != null)
                {
                    bool changed = configure != null && configure(existing);
                    if (changed) EditorUtility.SetDirty(existing);
                    return changed ? AssetResult.Updated : AssetResult.Unchanged;
                }

                UnityEngine.Object other = AssetDatabase.LoadMainAssetAtPath(path);
                if (other != null)
                {
                    Debug.LogError(Log + "CreateOrUpdateAsset: '" + path + "' already holds a " + other.GetType().Name + ", not a " + typeof(T).Name + ".");
                    return AssetResult.Failed;
                }

                string folder = Path.GetDirectoryName(path);
                if (!string.IsNullOrEmpty(folder) && !EnsureFolder(folder.Replace('\\', '/'))) return AssetResult.Failed;

                var created = ScriptableObject.CreateInstance<T>();
                created.name = Path.GetFileNameWithoutExtension(path);
                if (configure != null) configure(created);
                AssetDatabase.CreateAsset(created, path);
                return AssetResult.Created;
            }
            catch (Exception ex)
            {
                Debug.LogError(Log + "CreateOrUpdateAsset failed for '" + path + "': " + ex);
                return AssetResult.Failed;
            }
        }

        /// <summary>Element-wise equality of two lists/arrays (null and empty are equal).</summary>
        public static bool SameSequence<T>(IList<T> a, IList<T> b)
        {
            int na = a == null ? 0 : a.Count;
            int nb = b == null ? 0 : b.Count;
            if (na != nb) return false;
            EqualityComparer<T> cmp = EqualityComparer<T>.Default;
            for (int i = 0; i < na; i++)
                if (!cmp.Equals(a[i], b[i])) return false;
            return true;
        }

        /// <summary>Absolute path of the Unity project root (the folder that contains Assets/).</summary>
        public static string ProjectRoot
        {
            get { return Path.GetDirectoryName(Application.dataPath); }
        }
    }
}
