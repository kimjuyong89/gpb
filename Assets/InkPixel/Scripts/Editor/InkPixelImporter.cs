// InkPixel — texture import rules for everything under Assets/InkPixel/Art (ASSET_SPEC §7.1).
// Mirrors GPA's Editor/PixelArtImport.cs (Sprite, PPU 16, Point, uncompressed, no mipmaps) and adds
// sidecar-driven slicing: Multiple + SpriteSlicer when "<sheet>.sprites.json" exists, Single otherwise.
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace InkPixel.EditorTools
{
    public class InkPixelImporter : AssetPostprocessor
    {
        /// <summary>Bump to force every InkPixel texture through OnPreprocessTexture again.</summary>
        private const uint ImporterVersion = 3;
        private const string Log = "[InkPixel] ";

        // Slicing is deferred to EditorApplication.delayCall so it never runs inside an import callback.
        private static readonly HashSet<string> pending = new HashSet<string>(StringComparer.Ordinal);
        private static bool scheduled;
        private static bool running;

        public override uint GetVersion()
        {
            return ImporterVersion;
        }

        /// <summary>A PNG under Assets/InkPixel/Art (any depth).</summary>
        public static bool IsInkPixelTexture(string assetPath)
        {
            return InkPixelPaths.IsUnderArt(assetPath)
                && assetPath.EndsWith(InkPixelPaths.TextureExtension, StringComparison.OrdinalIgnoreCase);
        }

        /// <summary>A "*.sprites.json" under Assets/InkPixel/Art.</summary>
        public static bool IsInkPixelSidecar(string assetPath)
        {
            return InkPixelPaths.IsUnderArt(assetPath)
                && assetPath.EndsWith(InkPixelPaths.SidecarSuffix, StringComparison.OrdinalIgnoreCase);
        }

        // ------------------------------------------------------------------------------ import

        private void OnPreprocessTexture()
        {
            if (!IsInkPixelTexture(assetPath)) return;
            var importer = assetImporter as TextureImporter;
            if (importer == null) return;
            bool hasSidecar = SidecarData.Exists(assetPath);
            ApplySettings(importer, hasSidecar);
            if (!hasSidecar) return;

            // Write the sidecar rects into this very import (documented data-provider usage from
            // OnPreprocessTexture), so a fresh sheet lands sliced in one pass. The deferred pass in
            // Flush() re-checks it afterwards and normally finds it unchanged.
            try
            {
                SpriteSlicer.ApplyToImporter(importer, assetPath, false);
            }
            catch (Exception ex)
            {
                Debug.LogError(Log + "Slicing during import of '" + assetPath + "' threw (the deferred pass will retry): " + ex);
            }
        }

        /// <summary>
        /// The binding import settings (§7.1): Sprite, PPU 16, Point, Uncompressed, no mipmaps,
        /// alphaIsTransparency, FullRect mesh, no physics shape, max 4096, sRGB. Multiple when a
        /// sidecar exists (rects come from SpriteSlicer), Single with a centered pivot otherwise.
        /// </summary>
        public static void ApplySettings(TextureImporter importer, bool hasSidecar)
        {
            if (importer == null) return;
            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = hasSidecar ? SpriteImportMode.Multiple : SpriteImportMode.Single;
            importer.spritePixelsPerUnit = InkPixelPaths.PixelsPerUnit;
            importer.filterMode = FilterMode.Point;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.crunchedCompression = false;
            importer.mipmapEnabled = false;
            importer.alphaSource = TextureImporterAlphaSource.FromInput;
            importer.alphaIsTransparency = true;
            importer.sRGBTexture = true;
            importer.maxTextureSize = 4096;
            importer.npotScale = TextureImporterNPOTScale.None;
            importer.wrapMode = TextureWrapMode.Clamp;

            var settings = new TextureImporterSettings();
            importer.ReadTextureSettings(settings);
            settings.spriteMeshType = SpriteMeshType.FullRect;
            settings.spriteGenerateFallbackPhysicsShape = false;
            if (!hasSidecar)
            {
                settings.spriteAlignment = (int)SpriteAlignment.Center;
                settings.spritePivot = new Vector2(0.5f, 0.5f);
                settings.spriteBorder = Vector4.zero;
            }
            importer.SetTextureSettings(settings);
        }

        // --------------------------------------------------------------------- deferred slicing

        private static void OnPostprocessAllAssets(string[] importedAssets, string[] deletedAssets, string[] movedAssets, string[] movedFromAssetPaths)
        {
            bool touchedArt = false;
            Queue(importedAssets, ref touchedArt);
            Queue(movedAssets, ref touchedArt);
            if (deletedAssets != null)
                foreach (string p in deletedAssets)
                    if (InkPixelPaths.IsUnderArt(p)) touchedArt = true;
            if (movedFromAssetPaths != null)
                foreach (string p in movedFromAssetPaths)
                    if (InkPixelPaths.IsUnderArt(p)) touchedArt = true;

            if (touchedArt) InkPixelAssetUtil.InvalidateCaches();
            if (pending.Count > 0) Schedule();
        }

        private static void Queue(string[] paths, ref bool touchedArt)
        {
            if (paths == null) return;
            foreach (string raw in paths)
            {
                if (string.IsNullOrEmpty(raw)) continue;
                string p = raw.Replace('\\', '/');
                if (IsInkPixelTexture(p))
                {
                    touchedArt = true;
                    if (SidecarData.Exists(p)) pending.Add(p);
                }
                else if (IsInkPixelSidecar(p))
                {
                    touchedArt = true;
                    string texture = InkPixelPaths.TexturePathFor(p);
                    if (File.Exists(texture)) pending.Add(texture);
                }
            }
        }

        /// <summary>Queues a texture for sidecar slicing on the next editor tick (coalesced).</summary>
        public static void QueueSlice(string texturePath)
        {
            if (!IsInkPixelTexture(texturePath) || !SidecarData.Exists(texturePath)) return;
            pending.Add(texturePath.Replace('\\', '/'));
            Schedule();
        }

        /// <summary>Drops queued textures (used after an explicit pass that already sliced everything).</summary>
        public static void ClearPending()
        {
            pending.Clear();
        }

        private static void Schedule()
        {
            if (scheduled) return;
            scheduled = true;
            EditorApplication.delayCall += Flush;
        }

        private static void Flush()
        {
            scheduled = false;
            if (running)
            {
                // Re-entrancy guard: a SaveAndReimport inside the pass below queued more work; run it next tick.
                Schedule();
                return;
            }
            if (pending.Count == 0) return;

            running = true;
            try
            {
                var batch = new List<string>(pending);
                batch.Sort(StringComparer.Ordinal);
                pending.Clear();

                int applied = 0, failed = 0;
                foreach (string texturePath in batch)
                {
                    try
                    {
                        SpriteSlicer.SliceResult result = SpriteSlicer.Apply(texturePath);
                        if (result == SpriteSlicer.SliceResult.Applied) applied++;
                        else if (result == SpriteSlicer.SliceResult.Failed) failed++;
                    }
                    catch (Exception ex)
                    {
                        failed++;
                        Debug.LogError(Log + "Sidecar slicing threw on '" + texturePath + "': " + ex);
                    }
                }
                if (applied > 0 || failed > 0)
                    Debug.Log(Log + "Sidecar slicing pass: " + applied + " sheet(s) sliced, " + failed + " failed, " + (batch.Count - applied - failed) + " unchanged.");
            }
            finally
            {
                running = false;
            }
            // Reimports above re-queued the same sheets; the next pass verifies them as unchanged.
            if (pending.Count > 0) Schedule();
        }
    }
}
