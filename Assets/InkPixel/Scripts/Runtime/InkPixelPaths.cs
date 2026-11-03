// InkPixel — folder constants (ASSET_SPEC §1, §7). Runtime-safe: no UnityEditor references.
using System;

namespace InkPixel
{
    /// <summary>
    /// Project-relative asset paths of every InkPixel folder plus the pack-wide constants
    /// (pixels per unit, cell size, sidecar suffix). Paths use forward slashes, no trailing slash.
    /// </summary>
    public static class InkPixelPaths
    {
        public const string Root = "Assets/InkPixel";

        // ---- Art: PNG sheets + "<sheet>.sprites.json" sidecars -------------------------------
        public const string Art = Root + "/Art";
        public const string Tiles = Art + "/Tiles";
        public const string Characters = Art + "/Characters";
        public const string Icons = Art + "/Icons";
        public const string IconsMini = Icons + "/Mini";
        public const string FX = Art + "/FX";
        public const string UI = Art + "/UI";
        public const string UIStatus = UI + "/Status";
        public const string UIMarkers = UI + "/Markers";
        public const string UIFrames = UI + "/Frames";

        // ---- Audio ------------------------------------------------------------------------------
        public const string Audio = Root + "/Audio";
        public const string Sfx = Audio + "/Sfx";
        public const string Music = Audio + "/Music";

        // ---- Scripts ----------------------------------------------------------------------------
        public const string Scripts = Root + "/Scripts";
        public const string ScriptsRuntime = Scripts + "/Runtime";
        public const string ScriptsEditor = Scripts + "/Editor";

        // ---- Generated inside Unity by Tools/InkPixel/... (only .gitkeep files are committed) ----
        public const string Generated = Root + "/Generated";
        public const string GenAnimations = Generated + "/Animations";
        public const string GenTiles = Generated + "/Tiles";
        public const string GenScenes = Generated + "/Scenes";
        public const string GenPrefabs = Generated + "/Prefabs";
        public const string DemoScene = GenScenes + "/InkPixelDemo.unity";

        // ---- GPA integration --------------------------------------------------------------------
        public const string Integration = Root + "/Integration";
        public const string IntegrationGPA = Integration + "/GPA";

        /// <summary>The binding spec, relative to the project root (it lives outside Assets/).</summary>
        public const string SpecFile = "Docs/ASSET_SPEC.md";

        // ---- Pack-wide constants ----------------------------------------------------------------
        /// <summary>16 px = 1 Unity unit = 1 grid cell.</summary>
        public const int PixelsPerUnit = 16;
        /// <summary>Tile grid cell size in pixels.</summary>
        public const int CellSize = 16;
        /// <summary>Every sheet "<name>.png" has a sidecar "<name>.sprites.json" next to it.</summary>
        public const string SidecarSuffix = ".sprites.json";
        public const string TextureExtension = ".png";

        /// <summary>Asset path of the sidecar that belongs to a texture: "&lt;path minus .png&gt;.sprites.json".</summary>
        public static string SidecarPathFor(string texturePath)
        {
            if (string.IsNullOrEmpty(texturePath)) return null;
            string p = texturePath.Replace('\\', '/');
            if (p.EndsWith(TextureExtension, StringComparison.OrdinalIgnoreCase))
                p = p.Substring(0, p.Length - TextureExtension.Length);
            return p + SidecarSuffix;
        }

        /// <summary>Asset path of the PNG that a sidecar describes.</summary>
        public static string TexturePathFor(string sidecarPath)
        {
            if (string.IsNullOrEmpty(sidecarPath)) return null;
            string p = sidecarPath.Replace('\\', '/');
            if (p.EndsWith(SidecarSuffix, StringComparison.OrdinalIgnoreCase))
                p = p.Substring(0, p.Length - SidecarSuffix.Length);
            return p + TextureExtension;
        }

        /// <summary>Sheet name of an asset path: the file name without ".png" or ".sprites.json".</summary>
        public static string SheetNameOf(string assetPath)
        {
            if (string.IsNullOrEmpty(assetPath)) return "";
            string p = assetPath.Replace('\\', '/');
            int slash = p.LastIndexOf('/');
            string file = slash >= 0 ? p.Substring(slash + 1) : p;
            if (file.EndsWith(SidecarSuffix, StringComparison.OrdinalIgnoreCase))
                return file.Substring(0, file.Length - SidecarSuffix.Length);
            int dot = file.LastIndexOf('.');
            return dot > 0 ? file.Substring(0, dot) : file;
        }

        /// <summary>True when <paramref name="assetPath"/> lies inside <paramref name="folder"/> (any depth).</summary>
        public static bool IsUnder(string assetPath, string folder)
        {
            if (string.IsNullOrEmpty(assetPath) || string.IsNullOrEmpty(folder)) return false;
            return assetPath.Replace('\\', '/').StartsWith(folder + "/", StringComparison.Ordinal);
        }

        public static bool IsUnderArt(string assetPath)
        {
            return IsUnder(assetPath, Art);
        }

        public static string Combine(string folder, string fileName)
        {
            return folder + "/" + fileName;
        }
    }
}
