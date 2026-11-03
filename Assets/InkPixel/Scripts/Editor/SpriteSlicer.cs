// InkPixel — applies "<sheet>.sprites.json" rects to a texture through the 2D Sprite package's
// ISpriteEditorDataProvider (ASSET_SPEC §3, §7). Never touches the obsolete TextureImporter.spritesheet.
//
// API shapes verified against com.unity.2d.sprite@1.0 docs:
//   SpriteDataProviderFactories: Init(), GetSpriteEditorDataProviderFromObject(Object)
//   ISpriteEditorDataProvider: InitSpriteEditorDataProvider(), GetSpriteRects(), SetSpriteRects(SpriteRect[]),
//                              GetDataProvider<T>(), Apply(), targetObject, spriteImportMode
//   SpriteRect: name, rect, alignment, pivot, border (x=L y=B z=R w=T), spriteID (GUID)
//   ISpriteNameFileIdDataProvider: GetNameFileIdPairs(), SetNameFileIdPairs(IEnumerable<SpriteNameFileIdPair>)
//   SpriteNameFileIdPair(string name, GUID fileId)
//   ITextureDataProvider: GetTextureActualWidthAndHeight(out int, out int)
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEditor.U2D.Sprites;
using UnityEngine;

namespace InkPixel.EditorTools
{
    public static class SpriteSlicer
    {
        private const string Log = "[InkPixel] ";
        private const float Epsilon = 1e-4f;

        public enum SliceResult
        {
            /// <summary>The texture has no sidecar; nothing to do.</summary>
            NoSidecar,
            /// <summary>The importer already holds exactly the sidecar's rects.</summary>
            Unchanged,
            /// <summary>Rects were written (and the texture reimported when asked to).</summary>
            Applied,
            /// <summary>Something went wrong; details were logged.</summary>
            Failed
        }

        public struct Report
        {
            public int textures;
            public int reimported;
            public int sliced;
            public int unchanged;
            public int failed;

            public override string ToString()
            {
                return textures + " texture(s) under Art, " + reimported + " reimported, " + sliced + " sliced from sidecars, " + unchanged + " already up to date, " + failed + " failed";
            }
        }

        // --------------------------------------------------------------------------------- menu

        [MenuItem("Tools/InkPixel/1. Reimport All Sprites", false, 1)]
        public static void ReimportAllMenu()
        {
            Report report = ReimportAll();
            Debug.Log(Log + "Reimport All Sprites: " + report + ".");
        }

        /// <summary>
        /// Force-reimports every PNG under Assets/InkPixel/Art (OnPreprocessTexture applies the current
        /// import rules and the sidecar rects) and then verifies every sidecar against the importer,
        /// rewriting any that still differ.
        /// </summary>
        public static Report ReimportAll()
        {
            var report = new Report();
            List<string> textures = InkPixelAssetUtil.ArtTexturePaths();
            report.textures = textures.Count;
            if (textures.Count == 0)
            {
                Debug.LogWarning(Log + "No PNG textures found under " + InkPixelPaths.Art + ".");
                return report;
            }

            try
            {
                EditorUtility.DisplayProgressBar("InkPixel", "Reimporting " + textures.Count + " texture(s)...", 0f);
                AssetDatabase.StartAssetEditing();
                try
                {
                    foreach (string path in textures)
                    {
                        AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
                        report.reimported++;
                    }
                }
                finally
                {
                    AssetDatabase.StopAssetEditing();
                }

                for (int i = 0; i < textures.Count; i++)
                {
                    string path = textures[i];
                    if (!SidecarData.Exists(path)) continue;
                    EditorUtility.DisplayProgressBar("InkPixel", "Slicing " + Path.GetFileName(path), (i + 1f) / textures.Count);
                    switch (Apply(path))
                    {
                        case SliceResult.Applied: report.sliced++; break;
                        case SliceResult.Unchanged: report.unchanged++; break;
                        case SliceResult.Failed: report.failed++; break;
                    }
                }
            }
            finally
            {
                EditorUtility.ClearProgressBar();
            }

            // The reimports above queued the same sheets for the deferred pass; they are known to be current.
            InkPixelImporter.ClearPending();
            InkPixelAssetUtil.InvalidateCaches();
            return report;
        }

        // -------------------------------------------------------------------------------- apply

        /// <summary>
        /// Applies the sidecar of <paramref name="texturePath"/> when the importer's sprite rects
        /// differ (by name, rect, pivot, border or sprite id). Returns true only when the texture was
        /// rewritten and reimported; false when there is no sidecar, nothing changed, or it failed (logged).
        /// </summary>
        public static bool ApplyIfNeeded(string texturePath)
        {
            return Apply(texturePath) == SliceResult.Applied;
        }

        /// <summary>Same as <see cref="ApplyIfNeeded"/> but tells the four outcomes apart.</summary>
        public static SliceResult Apply(string texturePath)
        {
            if (string.IsNullOrEmpty(texturePath)) return SliceResult.Failed;
            texturePath = texturePath.Replace('\\', '/');
            if (!SidecarData.Exists(texturePath)) return SliceResult.NoSidecar;

            var importer = AssetImporter.GetAtPath(texturePath) as TextureImporter;
            if (importer == null)
            {
                Debug.LogWarning(Log + "SpriteSlicer: '" + texturePath + "' has no TextureImporter (not imported yet?). Skipped.");
                return SliceResult.Failed;
            }
            return ApplyToImporter(importer, texturePath, true);
        }

        /// <summary>
        /// Core routine. With <paramref name="saveAndReimport"/> false it only writes the rects into the
        /// importer (for use inside OnPreprocessTexture, where the import that follows picks them up);
        /// with true it also calls SaveAndReimport so the sub-assets are regenerated right away.
        /// </summary>
        public static SliceResult ApplyToImporter(TextureImporter importer, string texturePath, bool saveAndReimport)
        {
            if (importer == null || string.IsNullOrEmpty(texturePath)) return SliceResult.Failed;
            texturePath = texturePath.Replace('\\', '/');
            string sidecarPath = InkPixelPaths.SidecarPathFor(texturePath);
            if (!File.Exists(sidecarPath)) return SliceResult.NoSidecar;

            SidecarData sidecar = SidecarData.Load(texturePath);
            if (sidecar == null) return SliceResult.Failed; // parse error already logged

            try
            {
                // The sidecar is the source of truth: the texture must be a Multiple-mode sprite.
                bool modeChanged = false;
                if (importer.textureType != TextureImporterType.Sprite)
                {
                    importer.textureType = TextureImporterType.Sprite;
                    modeChanged = true;
                }
                if (importer.spriteImportMode != SpriteImportMode.Multiple)
                {
                    importer.spriteImportMode = SpriteImportMode.Multiple;
                    modeChanged = true;
                }

                var factory = new SpriteDataProviderFactories();
                factory.Init();
                ISpriteEditorDataProvider provider = factory.GetSpriteEditorDataProviderFromObject(importer);
                if (provider == null)
                {
                    Debug.LogError(Log + "SpriteSlicer: no ISpriteEditorDataProvider for '" + texturePath + "'. Is com.unity.2d.sprite installed?");
                    return SliceResult.Failed;
                }
                provider.InitSpriteEditorDataProvider();

                int textureWidth, textureHeight;
                if (!TryReadPngSize(texturePath, out textureWidth, out textureHeight))
                {
                    textureWidth = textureHeight = 0;
                    var textureData = provider.GetDataProvider<ITextureDataProvider>();
                    if (textureData != null) textureData.GetTextureActualWidthAndHeight(out textureWidth, out textureHeight);
                }
                if (textureWidth <= 0 || textureHeight <= 0)
                {
                    Debug.LogError(Log + "SpriteSlicer: could not determine the size of '" + texturePath + "'.");
                    return SliceResult.Failed;
                }

                List<string> problems = sidecar.Validate(textureWidth, textureHeight);
                if (problems.Count > 0)
                {
                    Debug.LogError(Log + "SpriteSlicer: sidecar '" + sidecarPath + "' has " + problems.Count + " problem(s); not applied:\n - " + string.Join("\n - ", problems));
                    return SliceResult.Failed;
                }

                SpriteRect[] desired = BuildRects(sidecar, textureHeight);
                SpriteRect[] existing = provider.GetSpriteRects() ?? new SpriteRect[0];
                if (!modeChanged && RectsEqual(existing, desired)) return SliceResult.Unchanged;

                provider.SetSpriteRects(desired);
                try
                {
                    var nameFileIds = provider.GetDataProvider<ISpriteNameFileIdDataProvider>();
                    if (nameFileIds != null)
                    {
                        var pairs = new List<SpriteNameFileIdPair>(desired.Length);
                        foreach (SpriteRect r in desired) pairs.Add(new SpriteNameFileIdPair(r.name, r.spriteID));
                        nameFileIds.SetNameFileIdPairs(pairs);
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogWarning(Log + "SpriteSlicer: could not register name/fileId pairs for '" + texturePath + "': " + ex.Message);
                }
                provider.Apply();
                if (saveAndReimport) importer.SaveAndReimport();

                Debug.Log(Log + "Sliced '" + texturePath + "' into " + desired.Length + " sprite(s) from " + Path.GetFileName(sidecarPath)
                    + " (" + Describe(existing, desired) + (saveAndReimport ? "; reimported" : "; during import") + ").");
                return SliceResult.Applied;
            }
            catch (Exception ex)
            {
                Debug.LogError(Log + "SpriteSlicer failed on '" + texturePath + "': " + ex);
                return SliceResult.Failed;
            }
        }

        // ------------------------------------------------------------------------------ helpers

        /// <summary>Desired rects; the sidecar's top-left y becomes Unity's bottom-left y = height - y - h.</summary>
        public static SpriteRect[] BuildRects(SidecarData sidecar, int textureHeight)
        {
            var rects = new SpriteRect[sidecar.sprites.Length];
            for (int i = 0; i < sidecar.sprites.Length; i++)
            {
                SpriteEntry s = sidecar.sprites[i];
                var pivot = new Vector2(s.pivotX, s.pivotY);
                var rect = new SpriteRect();
                rect.name = s.name;
                rect.rect = new Rect(s.x, textureHeight - s.y - s.h, s.w, s.h);
                rect.alignment = AlignmentFor(pivot);
                rect.pivot = pivot;
                rect.border = new Vector4(s.borderL, s.borderB, s.borderR, s.borderT);
                rect.spriteID = GuidForName(s.name);
                rects[i] = rect;
            }
            return rects;
        }

        /// <summary>Deterministic sprite id: MD5 of the sprite name, parsed as a 32-hex-digit GUID.</summary>
        public static GUID GuidForName(string spriteName)
        {
            using (MD5 md5 = MD5.Create())
            {
                byte[] hash = md5.ComputeHash(Encoding.UTF8.GetBytes(spriteName ?? ""));
                var hex = new StringBuilder(32);
                for (int i = 0; i < hash.Length; i++) hex.Append(hash[i].ToString("x2"));
                GUID guid;
                if (GUID.TryParse(hex.ToString(), out guid) && !guid.Empty()) return guid;
            }
            Debug.LogError(Log + "SpriteSlicer: could not derive a GUID for sprite '" + spriteName + "'; using a random one.");
            return GUID.Generate();
        }

        /// <summary>Width/height from the PNG IHDR chunk (bytes 16..23, big-endian) without decoding the image.</summary>
        public static bool TryReadPngSize(string path, out int width, out int height)
        {
            width = height = 0;
            try
            {
                if (!File.Exists(path)) return false;
                var head = new byte[24];
                using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read))
                {
                    int read = 0;
                    while (read < head.Length)
                    {
                        int n = stream.Read(head, read, head.Length - read);
                        if (n <= 0) break;
                        read += n;
                    }
                    if (read < head.Length) return false;
                }
                bool signature = head[0] == 0x89 && head[1] == 0x50 && head[2] == 0x4E && head[3] == 0x47
                              && head[4] == 0x0D && head[5] == 0x0A && head[6] == 0x1A && head[7] == 0x0A;
                bool ihdr = head[12] == (byte)'I' && head[13] == (byte)'H' && head[14] == (byte)'D' && head[15] == (byte)'R';
                if (!signature || !ihdr) return false;
                width = (head[16] << 24) | (head[17] << 16) | (head[18] << 8) | head[19];
                height = (head[20] << 24) | (head[21] << 16) | (head[22] << 8) | head[23];
                return width > 0 && height > 0;
            }
            catch (Exception ex)
            {
                Debug.LogWarning(Log + "SpriteSlicer: could not read PNG header of '" + path + "': " + ex.Message);
                width = height = 0;
                return false;
            }
        }

        /// <summary>True when both sets hold the same sprites by name with equal rect, pivot, border and id.</summary>
        public static bool RectsEqual(SpriteRect[] existing, SpriteRect[] desired)
        {
            if (existing == null || desired == null) return false;
            if (existing.Length != desired.Length) return false;
            var byName = new Dictionary<string, SpriteRect>(StringComparer.Ordinal);
            foreach (SpriteRect e in existing)
            {
                if (e == null || string.IsNullOrEmpty(e.name) || byName.ContainsKey(e.name)) return false;
                byName.Add(e.name, e);
            }
            foreach (SpriteRect d in desired)
            {
                SpriteRect e;
                if (!byName.TryGetValue(d.name, out e)) return false;
                if (!Approximately(e.rect.x, d.rect.x) || !Approximately(e.rect.y, d.rect.y)
                    || !Approximately(e.rect.width, d.rect.width) || !Approximately(e.rect.height, d.rect.height)) return false;
                Vector2 ep = EffectivePivot(e), dp = EffectivePivot(d);
                if (!Approximately(ep.x, dp.x) || !Approximately(ep.y, dp.y)) return false;
                if (!Approximately(e.border.x, d.border.x) || !Approximately(e.border.y, d.border.y)
                    || !Approximately(e.border.z, d.border.z) || !Approximately(e.border.w, d.border.w)) return false;
                if (e.spriteID != d.spriteID) return false;
            }
            return true;
        }

        private static string Describe(SpriteRect[] existing, SpriteRect[] desired)
        {
            var before = new HashSet<string>(existing.Where(r => r != null).Select(r => r.name), StringComparer.Ordinal);
            var after = new HashSet<string>(desired.Select(r => r.name), StringComparer.Ordinal);
            int added = after.Count(n => !before.Contains(n));
            int removed = before.Count(n => !after.Contains(n));
            return added + " added, " + removed + " removed, " + (after.Count - added) + " kept";
        }

        private static bool Approximately(float a, float b)
        {
            return Mathf.Abs(a - b) <= Epsilon;
        }

        /// <summary>The pivot a SpriteRect resolves to, taking a non-Custom alignment into account.</summary>
        public static Vector2 EffectivePivot(SpriteRect rect)
        {
            switch (rect.alignment)
            {
                case SpriteAlignment.Center: return new Vector2(0.5f, 0.5f);
                case SpriteAlignment.TopLeft: return new Vector2(0f, 1f);
                case SpriteAlignment.TopCenter: return new Vector2(0.5f, 1f);
                case SpriteAlignment.TopRight: return new Vector2(1f, 1f);
                case SpriteAlignment.LeftCenter: return new Vector2(0f, 0.5f);
                case SpriteAlignment.RightCenter: return new Vector2(1f, 0.5f);
                case SpriteAlignment.BottomLeft: return new Vector2(0f, 0f);
                case SpriteAlignment.BottomCenter: return new Vector2(0.5f, 0f);
                case SpriteAlignment.BottomRight: return new Vector2(1f, 0f);
                default: return rect.pivot;
            }
        }

        /// <summary>A standard alignment when the pivot is one of the nine anchors, else Custom.</summary>
        public static SpriteAlignment AlignmentFor(Vector2 pivot)
        {
            int px = Approximately(pivot.x, 0f) ? 0 : Approximately(pivot.x, 0.5f) ? 1 : Approximately(pivot.x, 1f) ? 2 : -1;
            int py = Approximately(pivot.y, 0f) ? 0 : Approximately(pivot.y, 0.5f) ? 1 : Approximately(pivot.y, 1f) ? 2 : -1;
            if (px < 0 || py < 0) return SpriteAlignment.Custom;
            if (py == 2) return px == 0 ? SpriteAlignment.TopLeft : px == 1 ? SpriteAlignment.TopCenter : SpriteAlignment.TopRight;
            if (py == 1) return px == 0 ? SpriteAlignment.LeftCenter : px == 1 ? SpriteAlignment.Center : SpriteAlignment.RightCenter;
            return px == 0 ? SpriteAlignment.BottomLeft : px == 1 ? SpriteAlignment.BottomCenter : SpriteAlignment.BottomRight;
        }
    }
}
