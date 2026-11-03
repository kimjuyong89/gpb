// InkPixel — Tools/InkPixel menu: Setup All (1 → 2 → 3 → demo scene hook), sidecar validation, Open Spec.
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace InkPixel.EditorTools
{
    public static class InkPixelMenu
    {
        private const string Log = "[InkPixel] ";

        /// <summary>
        /// Set by the demo scene builder (e.g. from an [InitializeOnLoadMethod]); invoked at the end of
        /// Setup All when non-null. Exceptions are caught and logged so the other steps keep their results.
        /// </summary>
        public static System.Action BuildDemoSceneHook;

        [MenuItem("Tools/InkPixel/Setup All", false, 20)]
        public static void SetupAll()
        {
            var stopwatch = System.Diagnostics.Stopwatch.StartNew();
            Debug.Log(Log + "Setup All: start (" + InkPixelPaths.Root + ")");

            AssetDatabase.Refresh();

            // 1. Import rules + sidecar slicing.
            SpriteSlicer.Report slice = SpriteSlicer.ReimportAll();
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            // 2. SpriteAnimation assets.
            AnimationBuilder.Report animations = AnimationBuilder.Build();
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            // 3. Tile / RuleTile assets.
            TileBuilder.Report tiles = TileBuilder.Build();
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            // 4. Demo scene (registered by a later tool, optional).
            string demo;
            if (BuildDemoSceneHook != null)
            {
                try
                {
                    BuildDemoSceneHook();
                    AssetDatabase.SaveAssets();
                    demo = "built";
                }
                catch (Exception ex)
                {
                    Debug.LogError(Log + "Setup All: demo scene builder failed: " + ex);
                    demo = "FAILED (" + ex.GetType().Name + ": " + ex.Message + ")";
                }
            }
            else
            {
                demo = "skipped (no BuildDemoSceneHook registered)";
            }

            stopwatch.Stop();
            int failures = slice.failed + animations.failed + tiles.tilesFailed + tiles.ruleTilesFailed;
            string summary = Log + "Setup All finished in " + stopwatch.Elapsed.TotalSeconds.ToString("0.0") + " s"
                + (failures > 0 ? " with " + failures + " failure(s) (see errors above)" : "") + "\n"
                + "  1. Sprites:    " + slice + "\n"
                + "  2. Animations: " + animations + " -> " + InkPixelPaths.GenAnimations + "\n"
                + "  3. Tiles:      " + tiles + " -> " + InkPixelPaths.GenTiles + "\n"
                + "  4. Demo scene: " + demo;
            if (failures > 0) Debug.LogWarning(summary);
            else Debug.Log(summary);
        }

        [MenuItem("Tools/InkPixel/Validate Sidecars", false, 21)]
        public static void ValidateSidecars()
        {
            List<string> textures = InkPixelAssetUtil.ArtTexturePaths();
            int withSidecar = 0, bad = 0, problemCount = 0;
            var orphans = new List<string>();
            foreach (string texturePath in textures)
            {
                if (!SidecarData.Exists(texturePath)) continue;
                withSidecar++;
                SidecarData sidecar = SidecarData.Load(texturePath);
                if (sidecar == null)
                {
                    bad++;
                    continue;
                }
                int width, height;
                if (!SpriteSlicer.TryReadPngSize(texturePath, out width, out height)) width = height = 0;
                List<string> problems = sidecar.Validate(width, height);
                if (string.IsNullOrEmpty(sidecar.sheet) || sidecar.sheet != InkPixelPaths.SheetNameOf(texturePath))
                    problems.Add("'sheet' is '" + sidecar.sheet + "' but the file is '" + InkPixelPaths.SheetNameOf(texturePath) + "'");
                if (sidecar.pixelsPerUnit != InkPixelPaths.PixelsPerUnit)
                    problems.Add("pixelsPerUnit is " + sidecar.pixelsPerUnit + " (expected " + InkPixelPaths.PixelsPerUnit + ")");
                if (problems.Count > 0)
                {
                    bad++;
                    problemCount += problems.Count;
                    Debug.LogError(Log + "Sidecar '" + sidecar.sidecarPath + "' has " + problems.Count + " problem(s):\n - " + string.Join("\n - ", problems));
                }
            }

            // Sidecars without a PNG.
            if (AssetDatabase.IsValidFolder(InkPixelPaths.Art))
            {
                string artAbsolute = Path.Combine(InkPixelAssetUtil.ProjectRoot, InkPixelPaths.Art);
                if (Directory.Exists(artAbsolute))
                {
                    foreach (string file in Directory.GetFiles(artAbsolute, "*" + InkPixelPaths.SidecarSuffix, SearchOption.AllDirectories))
                    {
                        string texture = InkPixelPaths.TexturePathFor(file);
                        if (!File.Exists(texture)) orphans.Add(file.Replace('\\', '/'));
                    }
                }
            }
            foreach (string orphan in orphans)
                Debug.LogWarning(Log + "Sidecar '" + orphan + "' has no matching PNG.");

            string summary = Log + "Validate Sidecars: " + textures.Count + " texture(s), " + withSidecar + " with sidecars, " + bad + " with problems (" + problemCount + " problem(s)), " + orphans.Count + " orphan sidecar(s).";
            if (bad > 0 || orphans.Count > 0) Debug.LogWarning(summary);
            else Debug.Log(summary);
        }

        [MenuItem("Tools/InkPixel/Open Spec", false, 40)]
        public static void OpenSpec()
        {
            string path = Path.GetFullPath(Path.Combine(InkPixelAssetUtil.ProjectRoot, InkPixelPaths.SpecFile));
            if (!File.Exists(path))
            {
                Debug.LogError(Log + "Spec not found at '" + path + "'.");
                return;
            }
            EditorUtility.OpenWithDefaultApp(path);
        }
    }
}
