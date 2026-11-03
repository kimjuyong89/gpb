// InkPixel — Tools/InkPixel/4. Build Demo Scene (ASSET_SPEC §7.1, §7.2): writes
// Generated/Scenes/InkPixelDemo.unity with a RegionViewer (Demo/demo_layout.txt + demo_tiledefs.json),
// a GalleryController over every character sheet and FX strip, SimpleAudio with every clip, a help
// canvas and an EventSystem. Registers itself as InkPixelMenu.BuildDemoSceneHook. Re-runnable.
using System;
using System.Collections.Generic;
using System.IO;
using InkPixel.Demo;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem.UI;
#endif

namespace InkPixel.EditorTools
{
    [InitializeOnLoad]
    public static class DemoSceneBuilder
    {
        private const string Log = "[InkPixel] ";

        public const string DemoFolder = InkPixelPaths.Root + "/Demo";
        public const string LayoutPath = DemoFolder + "/demo_layout.txt";
        public const string TileDefsJsonPath = DemoFolder + "/demo_tiledefs.json";
        public const string TileDefsAssetPath = InkPixelPaths.GenScenes + "/InkPixelDemoTileDefs.asset";
        public const string PlayerSheetPath = InkPixelPaths.Characters + "/hero_1.png";
        public const string AttackFxPath = InkPixelPaths.FX + "/Slash.png";
        public const string FaceSuffix = "_face";
        /// <summary>Where the gallery is laid out, well clear of the 32x20 map.</summary>
        public static readonly Vector2 GalleryOrigin = new Vector2(48f, 0f);
        /// <summary>SFX names mapped to the keys 1-9 when they exist; the rest is filled from the folder.</summary>
        public static readonly string[] PreferredSampleSfx = { "Slash", "Hit1", "Impact", "Accept", "Cancel", "Coin", "Qi", "Gong", "Victory" };
        /// <summary>Music order for the M key; GPA's three first.</summary>
        public static readonly string[] PreferredMusicOrder = { "Town", "World", "Battle" };
        private static readonly Color InkBackground = new Color(0x1e / 255f, 0x1b / 255f, 0x18 / 255f, 1f);

        static DemoSceneBuilder()
        {
            InkPixelMenu.BuildDemoSceneHook = Build;
        }

        public struct Report
        {
            public int characters;
            public int characterFaces;
            public int strips;
            public int sfx;
            public int music;
            public int tiles;
            public int tilesResolved;
            public int tilesUnresolved;
            public int npcs;
            public int npcFaces;
            public int missingSheets;
            public int warnings;
            public bool failed;

            public override string ToString()
            {
                return "characters " + characters + " (faces " + characterFaces + "), FX strips " + strips + ", SFX " + sfx + ", music " + music
                    + ", tiles " + tiles + " (" + tilesResolved + " resolved from sidecars, " + tilesUnresolved + " unresolved), NPCs " + npcs
                    + " (faces " + npcFaces + "), missing sheets " + missingSheets + ", warnings " + warnings + (failed ? ", FAILED" : "");
            }
        }

        private struct SpriteRef
        {
            public string texturePath;
            public SpriteEntry entry;
            public int cellSize;
        }

        [MenuItem("Tools/InkPixel/4. Build Demo Scene", false, 4)]
        public static void BuildMenu()
        {
            Build();
        }

        /// <summary>Builds (or rebuilds) the demo scene and logs a summary. Never throws.</summary>
        public static void Build()
        {
            Report report;
            try
            {
                report = BuildScene();
            }
            catch (Exception ex)
            {
                Debug.LogError(Log + "Build Demo Scene failed: " + ex);
                return;
            }
            string summary = Log + "Build Demo Scene: " + report + " -> " + InkPixelPaths.DemoScene;
            if (report.failed) Debug.LogError(summary);
            else if (report.warnings > 0) Debug.LogWarning(summary);
            else Debug.Log(summary);
        }

        public static Report BuildScene()
        {
            var report = new Report();
            if (!InkPixelAssetUtil.EnsureFolder(InkPixelPaths.GenScenes))
            {
                report.failed = true;
                return report;
            }

            // ---- inputs (a missing one only warns) --------------------------------------------
            var layoutAsset = AssetDatabase.LoadAssetAtPath<TextAsset>(LayoutPath);
            if (layoutAsset == null) Warn(ref report, "demo layout '" + LayoutPath + "' not found; the map will be empty.");
            var jsonAsset = AssetDatabase.LoadAssetAtPath<TextAsset>(TileDefsJsonPath);
            TileDefsJson data = jsonAsset != null ? TileDefs.Parse(jsonAsset.text) : null;
            if (data == null)
            {
                Warn(ref report, "demo tiledefs '" + TileDefsJsonPath + "' missing or unreadable; TileDefs will be empty.");
                data = new TileDefsJson();
                data.Normalize();
            }

            // ---- TileDefs asset: sprite names -> cells from the sidecars, then textures ------------
            Dictionary<string, SpriteRef> index = SidecarIndex();
            ResolveSprites(data, index, ref report);
            int missingSheets = 0;
            Func<string, Texture2D> resolver = path =>
            {
                var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(path);
                if (tex == null) missingSheets++;
                return tex;
            };
            AssetResult tileDefsResult = InkPixelAssetUtil.CreateOrUpdateAsset<TileDefs>(TileDefsAssetPath, t =>
            {
                bool changed = t.Populate(data, resolver);
                if (AssignNpcFaces(t)) changed = true;
                return changed;
            });
            report.missingSheets = missingSheets;
            if (tileDefsResult == AssetResult.Failed) Warn(ref report, "TileDefs asset '" + TileDefsAssetPath + "' could not be written.");
            AssetDatabase.SaveAssets();
            var tileDefs = AssetDatabase.LoadAssetAtPath<TileDefs>(TileDefsAssetPath);
            if (tileDefs != null)
            {
                report.tiles = tileDefs.tiles.Count;
                report.npcs = tileDefs.npcs.Count;
                foreach (NpcDef n in tileDefs.npcs)
                    if (n.face != null) report.npcFaces++;
            }

            // ---- art and audio discovery ----------------------------------------------------------
            List<GalleryController.CharacterEntry> characters = FindCharacters(ref report);
            List<GalleryController.StripEntry> strips = FindStrips(ref report);
            AudioClip[] sfx = InkPixelAssetUtil.AllClips(InkPixelPaths.Sfx);
            AudioClip[] music = InkPixelAssetUtil.AllClips(InkPixelPaths.Music);
            report.sfx = sfx.Length;
            report.music = music.Length;
            if (sfx.Length == 0) Warn(ref report, "no AudioClips under '" + InkPixelPaths.Sfx + "'.");
            if (music.Length == 0) Warn(ref report, "no AudioClips under '" + InkPixelPaths.Music + "'.");

            var player = AssetDatabase.LoadAssetAtPath<Texture2D>(PlayerSheetPath);
            if (player == null)
            {
                if (characters.Count > 0)
                {
                    player = characters[0].sheet;
                    Warn(ref report, "player sheet '" + PlayerSheetPath + "' not found; using '" + characters[0].name + "'.");
                }
                else
                {
                    Warn(ref report, "player sheet '" + PlayerSheetPath + "' not found and no character sheets exist; the player will be invisible.");
                }
            }

            // ---- the scene -------------------------------------------------------------------------
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
            {
                Warn(ref report, "Build Demo Scene cancelled: the open scene was not saved.");
                report.failed = true;
                return report;
            }
            Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            var cameraGo = new GameObject("Main Camera");
            cameraGo.tag = "MainCamera";
            var camera = cameraGo.AddComponent<Camera>();
            camera.orthographic = true;
            camera.orthographicSize = 7.5f;
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = InkBackground;
            camera.nearClipPlane = 0.3f;
            camera.farClipPlane = 100f;
            cameraGo.transform.position = new Vector3(16f, 10f, -10f);
            cameraGo.AddComponent<AudioListener>();

            var audioGo = new GameObject("Audio");
            var audio = audioGo.AddComponent<SimpleAudio>();
            audio.sfx = new List<AudioClip>(sfx);
            audio.music = new List<AudioClip>(music);
            string[] musicOrder = MusicOrder(music);
            audio.musicOnStart = musicOrder.Length > 0 ? musicOrder[0] : "";

            var regionGo = new GameObject("Region");
            var viewer = regionGo.AddComponent<RegionViewer>();
            viewer.layoutAsset = layoutAsset;
            viewer.tileDefs = tileDefs;
            viewer.playerSheet = player;
            ConfigureAttackFx(viewer, ref report);

            var galleryGo = new GameObject("Gallery");
            var gallery = galleryGo.AddComponent<GalleryController>();
            gallery.characters = characters;
            gallery.strips = strips;
            gallery.sampleSfx = SampleSfx(sfx);
            gallery.musicNames = musicOrder;
            gallery.regionViewer = viewer;
            gallery.origin = GalleryOrigin;

            Canvas canvas = DemoUi.CreateOverlayCanvas("Canvas", 50, null);
            Image helpBackground = DemoUi.CreateImage("HelpBackground", canvas.transform, new Color(InkBackground.r, InkBackground.g, InkBackground.b, 0.6f));
            DemoUi.Layout(helpBackground.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(8f, -8f), new Vector2(880f, 92f));
            Text help = DemoUi.CreateText("Help", canvas.transform, HelpText(report), 14, DemoUi.Paper, TextAnchor.UpperLeft);
            DemoUi.Layout(help.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(16f, -14f), new Vector2(864f, 80f));

            var eventSystemGo = new GameObject("EventSystem");
            eventSystemGo.AddComponent<EventSystem>();
#if ENABLE_INPUT_SYSTEM
            eventSystemGo.AddComponent<InputSystemUIInputModule>();
#else
            eventSystemGo.AddComponent<StandaloneInputModule>();
#endif

            // Edit-mode preview (the sprites are runtime objects; Start() rebuilds everything on Play).
            try
            {
                viewer.Build();
            }
            catch (Exception ex)
            {
                Warn(ref report, "RegionViewer preview build threw " + ex.GetType().Name + ": " + ex.Message);
            }
            try
            {
                gallery.Build();
            }
            catch (Exception ex)
            {
                Warn(ref report, "GalleryController preview build threw " + ex.GetType().Name + ": " + ex.Message);
            }

            if (!EditorSceneManager.SaveScene(scene, InkPixelPaths.DemoScene))
            {
                Debug.LogError(Log + "could not save '" + InkPixelPaths.DemoScene + "'.");
                report.failed = true;
                return report;
            }
            AddToBuildSettings(InkPixelPaths.DemoScene);
            return report;
        }

        // ------------------------------------------------------------------------------ tile defs

        /// <summary>sprite name -> (texture path, sidecar entry, cell size) over every sidecar under Art.</summary>
        private static Dictionary<string, SpriteRef> SidecarIndex()
        {
            var index = new Dictionary<string, SpriteRef>(StringComparer.Ordinal);
            foreach (string texturePath in InkPixelAssetUtil.SidecarTexturePaths())
            {
                SidecarData sidecar = SidecarData.Load(texturePath);
                if (sidecar == null) continue;
                int cellSize = sidecar.cellSize > 0 ? sidecar.cellSize : InkPixelPaths.CellSize;
                foreach (SpriteEntry entry in sidecar.sprites)
                {
                    if (string.IsNullOrEmpty(entry.name) || index.ContainsKey(entry.name)) continue;
                    var r = new SpriteRef();
                    r.texturePath = texturePath;
                    r.entry = entry;
                    r.cellSize = cellSize;
                    index.Add(entry.name, r);
                }
            }
            return index;
        }

        /// <summary>
        /// Fills sheet/cell/size of every entry that names a sprite from the sidecars (the authoritative
        /// cell coordinates), keeps the JSON's cellX/cellY as a fallback, and turns every sheet path into
        /// a full "Assets/..." path so the resolver can load it directly.
        /// </summary>
        private static void ResolveSprites(TileDefsJson data, Dictionary<string, SpriteRef> index, ref Report report)
        {
            foreach (TileDefJson t in data.tiles)
            {
                if (!string.IsNullOrEmpty(t.sprite))
                {
                    SpriteRef r;
                    if (index.TryGetValue(t.sprite, out r))
                    {
                        t.sheet = r.texturePath;
                        t.cellX = r.entry.x / r.cellSize;
                        t.cellY = r.entry.y / r.cellSize;
                        t.sizeX = Mathf.Max(1, r.entry.w / r.cellSize);
                        t.sizeY = Mathf.Max(1, r.entry.h / r.cellSize);
                        report.tilesResolved++;
                    }
                    else
                    {
                        report.tilesUnresolved++;
                        Warn(ref report, "tile '" + t.key + "': sprite '" + t.sprite + "' is in no sidecar; falling back to sheet '" + t.sheet + "' cell (" + t.cellX + "," + t.cellY + ") size " + t.sizeX + "x" + t.sizeY + ".");
                    }
                }
                t.sheet = Absolute(data.sheetBase, t.sheet);
            }
            foreach (NpcDefJson n in data.npcs)
            {
                if (!string.IsNullOrEmpty(n.propSprite))
                {
                    SpriteRef r;
                    if (index.TryGetValue(n.propSprite, out r))
                    {
                        n.prop = r.texturePath;
                        n.propCellX = r.entry.x / r.cellSize;
                        n.propCellY = r.entry.y / r.cellSize;
                    }
                    else
                    {
                        Warn(ref report, "NPC '" + n.name + "': prop sprite '" + n.propSprite + "' is in no sidecar; falling back to prop '" + n.prop + "' cell (" + n.propCellX + "," + n.propCellY + ").");
                    }
                }
                n.sheet = Absolute(data.sheetBase, n.sheet);
                n.prop = Absolute(data.sheetBase, n.prop);
            }
            data.playerSheet = Absolute(data.sheetBase, data.playerSheet);
            data.sheetBase = "";
        }

        private static string Absolute(string sheetBase, string rel)
        {
            if (string.IsNullOrEmpty(rel)) return "";
            string r = rel.Replace('\\', '/');
            if (r.StartsWith("Assets/", StringComparison.Ordinal)) return r;
            return TileDefsJson.Combine(sheetBase, r);
        }

        /// <summary>Assigns "&lt;sheet&gt;_face.png" next to each NPC sheet; returns true when anything changed.</summary>
        private static bool AssignNpcFaces(TileDefs tileDefs)
        {
            bool changed = false;
            foreach (NpcDef npc in tileDefs.npcs)
            {
                Texture2D face = npc.sheet != null ? LoadFace(AssetDatabase.GetAssetPath(npc.sheet)) : null;
                if (npc.face != face)
                {
                    npc.face = face;
                    changed = true;
                }
            }
            return changed;
        }

        /// <summary>The 32x32 face next to a character sheet ("&lt;dir&gt;/&lt;name&gt;_face.png"), or null.</summary>
        public static Texture2D LoadFace(string sheetPath)
        {
            if (string.IsNullOrEmpty(sheetPath)) return null;
            string dir = Path.GetDirectoryName(sheetPath);
            dir = string.IsNullOrEmpty(dir) ? "" : dir.Replace('\\', '/') + "/";
            return AssetDatabase.LoadAssetAtPath<Texture2D>(dir + InkPixelPaths.SheetNameOf(sheetPath) + FaceSuffix + InkPixelPaths.TextureExtension);
        }

        // ------------------------------------------------------------------------------ discovery

        private static List<string> TexturePathsUnder(string folder)
        {
            var paths = new List<string>();
            if (string.IsNullOrEmpty(folder) || !AssetDatabase.IsValidFolder(folder)) return paths;
            string[] guids = AssetDatabase.FindAssets("t:Texture2D", new[] { folder });
            var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (string guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (string.IsNullOrEmpty(path) || !path.EndsWith(InkPixelPaths.TextureExtension, StringComparison.OrdinalIgnoreCase)) continue;
                if (seen.Add(path)) paths.Add(path);
            }
            paths.Sort(StringComparer.Ordinal);
            return paths;
        }

        private static List<GalleryController.CharacterEntry> FindCharacters(ref Report report)
        {
            var list = new List<GalleryController.CharacterEntry>();
            List<string> paths = TexturePathsUnder(InkPixelPaths.Characters);
            if (paths.Count == 0) Warn(ref report, "no character sheets under '" + InkPixelPaths.Characters + "'.");
            foreach (string path in paths)
            {
                string sheetName = InkPixelPaths.SheetNameOf(path);
                if (sheetName.EndsWith(FaceSuffix, StringComparison.Ordinal)) continue;
                var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(path);
                if (tex == null) continue;
                if (!CharacterSheet.IsStandardSheet(tex))
                    Warn(ref report, "character sheet '" + path + "' is " + tex.width + "x" + tex.height + "; ASSET_SPEC §5.1 wants 128x64.");
                var entry = new GalleryController.CharacterEntry();
                entry.name = sheetName;
                entry.sheet = tex;
                entry.face = LoadFace(path);
                if (entry.face != null)
                {
                    report.characterFaces++;
                    if (entry.face.width != 32 || entry.face.height != 32)
                        Warn(ref report, "face '" + sheetName + FaceSuffix + "' is " + entry.face.width + "x" + entry.face.height + "; expected 32x32.");
                }
                list.Add(entry);
            }
            report.characters = list.Count;
            return list;
        }

        private static List<GalleryController.StripEntry> FindStrips(ref Report report)
        {
            var list = new List<GalleryController.StripEntry>();
            List<string> paths = TexturePathsUnder(InkPixelPaths.FX);
            if (paths.Count == 0) Warn(ref report, "no FX strips under '" + InkPixelPaths.FX + "'.");
            foreach (string path in paths)
            {
                var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(path);
                if (tex == null) continue;
                var entry = new GalleryController.StripEntry();
                entry.name = InkPixelPaths.SheetNameOf(path);
                entry.texture = tex;
                SidecarData sidecar = SidecarData.Load(path);
                if (sidecar != null && sidecar.stripFrames > 0)
                {
                    entry.frames = sidecar.stripFrames;
                    entry.fps = Mathf.Max(0f, sidecar.stripFps);
                }
                else
                {
                    entry.frames = StripSheet.GuessFrameCount(tex);
                    entry.fps = 12f;
                    Warn(ref report, "FX strip '" + path + "' has no sidecar stripFrames; guessed " + entry.frames + " frame(s) at 12 fps.");
                }
                if (tex.height != 48 || tex.width != entry.frames * 48)
                    Warn(ref report, "FX strip '" + path + "' is " + tex.width + "x" + tex.height + " for " + entry.frames + " frame(s); ASSET_SPEC §5.4 wants N x 48 by 48.");
                list.Add(entry);
            }
            report.strips = list.Count;
            return list;
        }

        private static void ConfigureAttackFx(RegionViewer viewer, ref Report report)
        {
            var slash = AssetDatabase.LoadAssetAtPath<Texture2D>(AttackFxPath);
            if (slash == null)
            {
                Warn(ref report, "attack FX '" + AttackFxPath + "' not found; attacks play without a strip.");
                return;
            }
            viewer.attackFx = slash;
            SidecarData sidecar = SidecarData.Load(AttackFxPath);
            if (sidecar != null && sidecar.stripFrames > 0)
            {
                viewer.attackFxFrames = sidecar.stripFrames;
                viewer.attackFxFps = Mathf.Max(0f, sidecar.stripFps);
            }
            else
            {
                viewer.attackFxFrames = StripSheet.GuessFrameCount(slash);
                viewer.attackFxFps = 16f;
            }
        }

        /// <summary>Up to nine SFX names: the preferred ones that exist, then the rest in name order.</summary>
        private static string[] SampleSfx(AudioClip[] sfx)
        {
            var names = new List<string>();
            var available = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (AudioClip c in sfx)
                if (c != null) available.Add(c.name);
            foreach (string preferred in PreferredSampleSfx)
                if (available.Contains(preferred) && names.Count < 9) names.Add(preferred);
            foreach (AudioClip c in sfx)
            {
                if (names.Count >= 9) break;
                if (c != null && !names.Contains(c.name)) names.Add(c.name);
            }
            return names.ToArray();
        }

        /// <summary>Every music name, GPA's Town / World / Battle first.</summary>
        private static string[] MusicOrder(AudioClip[] music)
        {
            var names = new List<string>();
            var available = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (AudioClip c in music)
                if (c != null) available.Add(c.name);
            foreach (string preferred in PreferredMusicOrder)
                if (available.Contains(preferred)) names.Add(preferred);
            foreach (AudioClip c in music)
                if (c != null && !names.Contains(c.name)) names.Add(c.name);
            return names.ToArray();
        }

        // ---------------------------------------------------------------------------------- misc

        private static string HelpText(Report report)
        {
            return "InkPixel Demo - 수묵 픽셀 팩 (강호유랑기 RegionView 호환 데모)   캐릭터 " + report.characters + " · FX " + report.strips + " · 효과음 " + report.sfx + " · 음악 " + report.music + "\n"
                + "이동 WASD/방향키 · 달리기 Shift · 도약 F · 공격 J/Space · 말 걸기 E/Enter · Tab 갤러리<->지도\n"
                + "갤러리: Q/E 쪽 넘김 · 1-9 효과음 · M 음악\n"
                + "Move WASD/Arrows · Run Shift · Leap F · Attack J/Space · Talk E/Enter · Tab gallery/map · Q/E page · 1-9 SFX · M music";
        }

        private static void AddToBuildSettings(string scenePath)
        {
            var scenes = new List<EditorBuildSettingsScene>(EditorBuildSettings.scenes);
            foreach (EditorBuildSettingsScene s in scenes)
                if (s.path == scenePath) return;
            scenes.Add(new EditorBuildSettingsScene(scenePath, true));
            EditorBuildSettings.scenes = scenes.ToArray();
        }

        private static void Warn(ref Report report, string message)
        {
            report.warnings++;
            Debug.LogWarning(Log + "Build Demo Scene: " + message);
        }
    }
}
