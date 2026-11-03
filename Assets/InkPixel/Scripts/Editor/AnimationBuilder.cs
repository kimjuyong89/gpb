// InkPixel — builds SpriteAnimation assets from sidecar "animations" (ASSET_SPEC §3, §7.1).
// Output: Generated/Animations/<sheet>_<anim>.asset, plus <sheet>_strip.asset for FX strips.
using System;
using System.Collections.Generic;
using UnityEditor;
using UnityEngine;

namespace InkPixel.EditorTools
{
    public static class AnimationBuilder
    {
        private const string Log = "[InkPixel] ";
        public const string StripAnimationName = "strip";

        public struct Report
        {
            public int sheets;
            public int clips;
            public int created;
            public int updated;
            public int unchanged;
            public int failed;

            public override string ToString()
            {
                return sheets + " sheet(s), " + clips + " clip(s): " + created + " created, " + updated + " updated, " + unchanged + " unchanged, " + failed + " failed";
            }
        }

        [MenuItem("Tools/InkPixel/2. Build Animations", false, 2)]
        public static void BuildMenu()
        {
            Report report = Build();
            AssetDatabase.SaveAssets();
            Debug.Log(Log + "Build Animations: " + report + " -> " + InkPixelPaths.GenAnimations);
        }

        /// <summary>Asset path of the clip "&lt;sheet&gt;_&lt;anim&gt;".</summary>
        public static string ClipPath(string sheet, string animationName)
        {
            return InkPixelPaths.GenAnimations + "/" + sheet + "_" + animationName + ".asset";
        }

        /// <summary>Asset path of an FX strip clip "&lt;sheet&gt;_strip".</summary>
        public static string StripClipPath(string sheet)
        {
            return ClipPath(sheet, StripAnimationName);
        }

        /// <summary>Creates or updates every clip of every sidecar under Art. Idempotent.</summary>
        public static Report Build()
        {
            var report = new Report();
            if (!InkPixelAssetUtil.EnsureFolder(InkPixelPaths.GenAnimations)) return report;

            List<string> textures = InkPixelAssetUtil.ArtTexturePaths();
            try
            {
                for (int i = 0; i < textures.Count; i++)
                {
                    string texturePath = textures[i];
                    SidecarData sidecar = SidecarData.Load(texturePath);
                    if (sidecar == null || (!sidecar.HasAnimations && !sidecar.IsFxStrip)) continue;
                    report.sheets++;
                    EditorUtility.DisplayProgressBar("InkPixel", "Animations: " + sidecar.sheet, (i + 1f) / textures.Count);

                    Dictionary<string, Sprite> sprites = InkPixelAssetUtil.LoadSprites(texturePath, true);
                    if (sprites.Count == 0)
                    {
                        Debug.LogError(Log + "AnimationBuilder: '" + texturePath + "' has no sprites (run Tools/InkPixel/1. Reimport All Sprites). Skipped " + (sidecar.animations.Length + (sidecar.IsFxStrip ? 1 : 0)) + " clip(s).");
                        report.failed += sidecar.animations.Length + (sidecar.IsFxStrip ? 1 : 0);
                        continue;
                    }

                    foreach (AnimationEntry anim in sidecar.animations)
                        BuildClip(sidecar, anim, sprites, ref report);
                    if (sidecar.IsFxStrip)
                        BuildStrip(sidecar, sprites, ref report);
                }
            }
            finally
            {
                EditorUtility.ClearProgressBar();
            }
            return report;
        }

        private static void BuildClip(SidecarData sidecar, AnimationEntry anim, Dictionary<string, Sprite> sprites, ref Report report)
        {
            report.clips++;
            string assetName = sidecar.AnimationAssetName(anim.name);
            if (string.IsNullOrEmpty(anim.name))
            {
                Debug.LogError(Log + "AnimationBuilder: an animation in '" + sidecar.sidecarPath + "' has no name; skipped.");
                report.failed++;
                return;
            }
            if (anim.frames.Length == 0)
            {
                Debug.LogError(Log + "AnimationBuilder: animation '" + assetName + "' (" + sidecar.sidecarPath + ") has no frames; skipped.");
                report.failed++;
                return;
            }

            var frames = new Sprite[anim.frames.Length];
            var missing = new List<string>();
            for (int i = 0; i < anim.frames.Length; i++)
            {
                Sprite s;
                if (sprites.TryGetValue(anim.frames[i] ?? "", out s) && s != null) frames[i] = s;
                else missing.Add(anim.frames[i]);
            }
            if (missing.Count > 0)
            {
                Debug.LogError(Log + "AnimationBuilder: animation '" + assetName + "' (" + sidecar.sidecarPath + ") references missing sprite(s): " + string.Join(", ", missing) + "; skipped.");
                report.failed++;
                return;
            }

            float fps = anim.fps > 0f ? anim.fps : 8f;
            Tally(Write(ClipPath(sidecar.sheet, anim.name), frames, fps, anim.loop, sidecar.sheet, anim.state, anim.direction), ref report);
        }

        private static void BuildStrip(SidecarData sidecar, Dictionary<string, Sprite> sprites, ref Report report)
        {
            report.clips++;
            List<SpriteEntry> entries = sidecar.StripSprites();
            if (entries.Count != sidecar.stripFrames)
                Debug.LogWarning(Log + "AnimationBuilder: '" + sidecar.sheet + "' declares stripFrames=" + sidecar.stripFrames + " but lists " + entries.Count + " sprite(s); using " + entries.Count + ".");

            var frames = new List<Sprite>(entries.Count);
            var missing = new List<string>();
            foreach (SpriteEntry e in entries)
            {
                Sprite s;
                if (sprites.TryGetValue(e.name, out s) && s != null) frames.Add(s);
                else missing.Add(e.name);
            }
            if (frames.Count == 0 || missing.Count > 0)
            {
                Debug.LogError(Log + "AnimationBuilder: strip '" + sidecar.sheet + "' is missing sprite(s): " + string.Join(", ", missing) + "; skipped.");
                report.failed++;
                return;
            }
            // FX strips are one-shots in GPA (Ui.Strip); a strip with fps 0 (Arrow, Shadow) is a static frame.
            Tally(Write(StripClipPath(sidecar.sheet), frames.ToArray(), Mathf.Max(0f, sidecar.stripFps), false, sidecar.sheet, StripAnimationName, ""), ref report);
        }

        private static AssetResult Write(string path, Sprite[] frames, float fps, bool loop, string sheet, string state, string direction)
        {
            return InkPixelAssetUtil.CreateOrUpdateAsset<SpriteAnimation>(path, clip =>
            {
                bool changed = false;
                if (!InkPixelAssetUtil.SameSequence(clip.frames, frames)) { clip.frames = (Sprite[])frames.Clone(); changed = true; }
                if (!Mathf.Approximately(clip.fps, fps)) { clip.fps = fps; changed = true; }
                if (clip.loop != loop) { clip.loop = loop; changed = true; }
                if (!string.Equals(clip.sheet, sheet, StringComparison.Ordinal)) { clip.sheet = sheet; changed = true; }
                if (!string.Equals(clip.state, state ?? "", StringComparison.Ordinal)) { clip.state = state ?? ""; changed = true; }
                if (!string.Equals(clip.direction, direction ?? "", StringComparison.Ordinal)) { clip.direction = direction ?? ""; changed = true; }
                return changed;
            });
        }

        private static void Tally(AssetResult result, ref Report report)
        {
            switch (result)
            {
                case AssetResult.Created: report.created++; break;
                case AssetResult.Updated: report.updated++; break;
                case AssetResult.Unchanged: report.unchanged++; break;
                default: report.failed++; break;
            }
        }
    }
}
