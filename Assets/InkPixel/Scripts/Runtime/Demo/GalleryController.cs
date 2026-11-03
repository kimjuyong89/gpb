// InkPixel demo — the gallery area: every character sheet walking in place in four directions plus
// attack / hurt poses and its face, every FX strip looping, SFX on 1-9 and music on M (ASSET_SPEC §7.2).
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

namespace InkPixel.Demo
{
    [AddComponentMenu("InkPixel/Gallery Controller")]
    [DisallowMultipleComponent]
    public class GalleryController : MonoBehaviour
    {
        /// <summary>A character sheet shown in a booth (filled by the demo scene builder).</summary>
        [Serializable]
        public class CharacterEntry
        {
            [Tooltip("Label (the sheet name, e.g. hero_1).")]
            public string name = "";
            [Tooltip("128x64 character sheet (ASSET_SPEC §5.1).")]
            public Texture2D sheet;
            [Tooltip("Optional 32x32 face (<name>_face.png).")]
            public Texture2D face;
        }

        /// <summary>An FX strip with the frame count / fps baked from its sidecar (stripFrames / stripFps).</summary>
        [Serializable]
        public class StripEntry
        {
            [Tooltip("Label (the strip name, e.g. Slash).")]
            public string name = "";
            [Tooltip("Horizontal strip texture (frames of 48x48).")]
            public Texture2D texture;
            [Tooltip("Frames in the strip (sidecar stripFrames).")]
            public int frames = 1;
            [Tooltip("Playback fps (sidecar stripFps); 0 = static.")]
            public float fps = 12f;
        }

        public const string RootName = "GalleryRoot";
        /// <summary>Width of one page in units at orthographicSize 7.5 and 16:9.</summary>
        public const float DesignWidth = 26.6667f;
        public const float DesignHeight = 15f;
        /// <summary>Canvas pixels per world unit for the world-space labels (48 = 1:1 pixels at 720p).</summary>
        public const float CanvasPixelsPerUnit = 48f;
        public const int BoothColumns = 3;
        public const int BoothRows = 4;

        [Header("Content (assigned by Tools/InkPixel/4. Build Demo Scene)")]
        [Tooltip("Every character sheet under Art/Characters (faces excluded).")]
        public List<CharacterEntry> characters = new List<CharacterEntry>();
        [Tooltip("Every FX strip under Art/FX with its sidecar frame count and fps.")]
        public List<StripEntry> strips = new List<StripEntry>();
        [Tooltip("SimpleAudio clip names played by the number keys 1-9.")]
        public string[] sampleSfx = new string[0];
        [Tooltip("Music clip names cycled by M (empty: every clip of the SimpleAudio music list).")]
        public string[] musicNames = new string[0];

        [Header("Behaviour")]
        [Tooltip("The region map; it is disabled while the gallery is shown and re-enabled on Tab.")]
        public RegionViewer regionViewer;
        [Tooltip("Bottom-left world corner of the gallery area (keep it away from the map).")]
        public Vector2 origin = new Vector2(48f, 0f);
        [Tooltip("Show the gallery first instead of the map.")]
        public bool startVisible;
        [Tooltip("Orthographic size while the gallery is shown.")]
        public float cameraSize = 7.5f;
        [Tooltip("Build the booths automatically in Start() when playing.")]
        public bool buildOnStart = true;

        private class Booth
        {
            public GameObject root;
            public SpriteRenderer[] walk = new SpriteRenderer[CharacterSheet.DirectionCount];
            public SpriteRenderer attack;
            public SpriteRenderer hurt;
            public SpriteRenderer face;
            public Text label;
            public Sprite[,] walkFrames;
            public Sprite[,] attackFrames;
            public Sprite[] hurtFrames;
            public CharacterEntry entry;
        }

        private class FxSlot
        {
            public GameObject root;
            public StripPlayer player;
            public Text label;
        }

        private readonly List<Booth> booths = new List<Booth>();
        private readonly List<FxSlot> fxSlots = new List<FxSlot>();
        private Transform root;
        private Canvas canvas;
        private Text title;
        private Text status;
        private int page;
        private int musicIndex = -1;
        private bool visible;
        private bool built;

        public bool Visible { get { return visible; } }
        public bool IsBuilt { get { return built; } }
        public int Page { get { return page; } }

        public int CharactersPerPage { get { return BoothColumns * BoothRows; } }
        public int StripsPerPage { get { return 8; } }

        public int PageCount
        {
            get
            {
                int c = characters != null ? (characters.Count + CharactersPerPage - 1) / CharactersPerPage : 0;
                int f = strips != null ? (strips.Count + StripsPerPage - 1) / StripsPerPage : 0;
                return Mathf.Max(1, Mathf.Max(c, f));
            }
        }

        private void Start()
        {
            if (!Application.isPlaying) return;
            if (buildOnStart) Build();
            SetVisible(startVisible);
        }

        // ------------------------------------------------------------------------------------- build

        /// <summary>Destroys the booths (edit mode safe).</summary>
        public void Clear()
        {
            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                Transform child = transform.GetChild(i);
                if (child.name == RootName)
                {
                    if (Application.isPlaying) Destroy(child.gameObject);
                    else DestroyImmediate(child.gameObject);
                }
            }
            booths.Clear();
            fxSlots.Clear();
            root = null;
            canvas = null;
            title = null;
            status = null;
            built = false;
        }

        /// <summary>Creates the booths, FX slots and labels for one page; works in edit mode (no coroutines).</summary>
        [ContextMenu("Build")]
        public void Build()
        {
            Clear();
            var rootGo = new GameObject(RootName);
            rootGo.transform.SetParent(transform, false);
            rootGo.transform.localPosition = origin;
            root = rootGo.transform;

            // World-space canvas: 48 canvas px per unit so 14px text is 14 screen px at 720p.
            var canvasGo = new GameObject("Labels", typeof(RectTransform));
            canvasGo.transform.SetParent(root, false);
            canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.WorldSpace;
            canvas.sortingOrder = 2000;
            var crt = (RectTransform)canvasGo.transform;
            crt.pivot = Vector2.zero;
            crt.anchorMin = crt.anchorMax = Vector2.zero;
            crt.sizeDelta = new Vector2(DesignWidth * CanvasPixelsPerUnit, DesignHeight * CanvasPixelsPerUnit);
            crt.localScale = Vector3.one / CanvasPixelsPerUnit;
            crt.localPosition = Vector3.zero;
            if (Camera.main != null) canvas.worldCamera = Camera.main;

            title = Label("Title", "", 16, DemoUi.Paper, TextAnchor.UpperLeft, 0.4f, 14.25f, DesignWidth - 0.8f, 0.45f);
            status = Label("Status", "", 14, DemoUi.Gold, TextAnchor.UpperLeft, 0.4f, 13.75f, DesignWidth - 0.8f, 0.4f);

            for (int slot = 0; slot < CharactersPerPage; slot++)
            {
                int col = slot % BoothColumns, row = slot / BoothColumns;
                float bx = 0.4f + col * 8.7f;
                float by = 11.4f - row * 2.4f;
                var booth = new Booth();
                booth.root = new GameObject("Booth " + slot);
                booth.root.transform.SetParent(root, false);
                booth.root.transform.localPosition = new Vector3(bx, by, 0f);
                // Face: 32x32 px = 2x2 units at PPU 16, scaled to 1.5 units.
                booth.face = MakeRenderer("Face", booth.root.transform, new Vector2(0f, 0f), 10);
                booth.face.transform.localScale = Vector3.one * 0.75f;
                for (int d = 0; d < CharacterSheet.DirectionCount; d++)
                    booth.walk[d] = MakeRenderer("Walk " + CharacterSheet.DirectionNames[d], booth.root.transform, new Vector2(1.8f + d * 1.05f, 0.3f), 10);
                booth.attack = MakeRenderer("Attack", booth.root.transform, new Vector2(6.25f, 0.3f), 10);
                booth.hurt = MakeRenderer("Hurt", booth.root.transform, new Vector2(7.35f, 0.3f), 10);
                // Below the face (the face spans by .. by+1.5), so the name never overlaps the sprites.
                booth.label = Label("Label " + slot, "", 14, DemoUi.PaperLight, TextAnchor.UpperLeft, bx, by - 0.5f, 8.4f, 0.4f);
                booths.Add(booth);
            }

            for (int slot = 0; slot < StripsPerPage; slot++)
            {
                float sx = 0.5f + slot * 3.25f;
                var fx = new FxSlot();
                fx.root = new GameObject("FX " + slot);
                fx.root.transform.SetParent(root, false);
                fx.root.transform.localPosition = new Vector3(sx, 0.7f, 0f);
                var sr = fx.root.AddComponent<SpriteRenderer>();
                sr.sortingOrder = 10;
                fx.player = fx.root.AddComponent<StripPlayer>();
                fx.player.playOnEnable = false;
                fx.player.randomPhase = false;
                // The 3x3-unit strip starts at y 0.7; the label box ends at 0.55 so they never touch.
                fx.label = Label("FX Label " + slot, "", 12, DemoUi.PaperLight, TextAnchor.UpperCenter, sx, 0.2f, 3f, 0.35f);
                fxSlots.Add(fx);
            }

            built = true;
            ShowPage(0);
        }

        private SpriteRenderer MakeRenderer(string objectName, Transform parent, Vector2 localPos, int order)
        {
            var go = new GameObject(objectName);
            go.transform.SetParent(parent, false);
            go.transform.localPosition = localPos;
            var sr = go.AddComponent<SpriteRenderer>();
            sr.sortingOrder = order;
            return sr;
        }

        private Text Label(string objectName, string text, int fontSize, Color color, TextAnchor anchor, float x, float y, float w, float h)
        {
            Text label = DemoUi.CreateText(objectName, canvas.transform, text, fontSize, color, anchor);
            DemoUi.Layout(label.rectTransform, Vector2.zero, Vector2.zero, Vector2.zero,
                new Vector2(x * CanvasPixelsPerUnit, y * CanvasPixelsPerUnit), new Vector2(w * CanvasPixelsPerUnit, h * CanvasPixelsPerUnit));
            return label;
        }

        // ------------------------------------------------------------------------------------- pages

        public void ShowPage(int index)
        {
            if (!built) return;
            int count = PageCount;
            page = ((index % count) + count) % count;

            for (int i = 0; i < booths.Count; i++)
            {
                Booth booth = booths[i];
                int ci = page * CharactersPerPage + i;
                CharacterEntry entry = characters != null && ci < characters.Count ? characters[ci] : null;
                booth.entry = entry;
                bool show = entry != null && entry.sheet != null;
                booth.root.SetActive(show);
                booth.label.gameObject.SetActive(show);
                if (!show) continue;
                booth.walkFrames = CharacterSheet.Frames(entry.sheet);
                booth.attackFrames = CharacterSheet.HasAttackColumns(entry.sheet) ? CharacterSheet.AttackFrames(entry.sheet) : null;
                booth.hurtFrames = CharacterSheet.HasAttackColumns(entry.sheet) ? CharacterSheet.Hurt(entry.sheet) : null;
                booth.face.sprite = DemoUi.FullSprite(entry.face);
                booth.face.gameObject.SetActive(entry.face != null);
                booth.label.text = string.IsNullOrEmpty(entry.name) ? entry.sheet.name : entry.name;
                for (int d = 0; d < CharacterSheet.DirectionCount; d++) booth.walk[d].sprite = booth.walkFrames[d, 0];
                booth.attack.sprite = booth.attackFrames != null ? booth.attackFrames[CharacterSheet.Down, 0] : null;
                booth.hurt.sprite = booth.hurtFrames != null ? booth.hurtFrames[CharacterSheet.Down] : null;
            }

            for (int i = 0; i < fxSlots.Count; i++)
            {
                FxSlot slot = fxSlots[i];
                int si = page * StripsPerPage + i;
                StripEntry entry = strips != null && si < strips.Count ? strips[si] : null;
                bool show = entry != null && entry.texture != null;
                slot.root.SetActive(show);
                slot.label.gameObject.SetActive(show);
                if (!show) continue;
                slot.player.Play(entry.texture, Mathf.Max(1, entry.frames), entry.fps, true);
                slot.label.text = (string.IsNullOrEmpty(entry.name) ? entry.texture.name : entry.name) + "  " + entry.frames + "f " + entry.fps + "fps";
            }

            RefreshTitle();
        }

        public void NextPage()
        {
            ShowPage(page + 1);
        }

        public void PreviousPage()
        {
            ShowPage(page - 1);
        }

        private void RefreshTitle()
        {
            if (title == null) return;
            int chars = characters != null ? characters.Count : 0;
            int fx = strips != null ? strips.Count : 0;
            SimpleAudio audio = SimpleAudio.Instance;
            int sfxCount = audio != null && audio.sfx != null ? audio.sfx.Count : 0;
            int musicCount = audio != null && audio.music != null ? audio.music.Count : 0;
            title.text = "InkPixel 갤러리  " + (page + 1) + "/" + PageCount + "쪽   캐릭터 " + chars + "장 · FX " + fx + "개 · 효과음 " + sfxCount + " · 음악 " + musicCount
                + "     Q/E 쪽 넘김 · Tab 지도로 · 1-9 효과음 · M 음악 (Q/E page · Tab map · 1-9 SFX · M music)";
        }

        // -------------------------------------------------------------------------------- visibility

        public void Toggle()
        {
            SetVisible(!visible);
        }

        /// <summary>Shows or hides the gallery; the RegionViewer is disabled while the gallery is shown.</summary>
        public void SetVisible(bool show)
        {
            visible = show;
            if (regionViewer != null) regionViewer.enabled = !show;
            if (show)
            {
                UpdateCamera();
                RefreshTitle();
                if (status != null && string.IsNullOrEmpty(status.text)) SetStatus("1-9: 효과음 " + SampleSfxList() + "   M: 음악");
            }
        }

        private string SampleSfxList()
        {
            if (sampleSfx == null || sampleSfx.Length == 0) return "(없음)";
            var parts = new List<string>();
            for (int i = 0; i < sampleSfx.Length && i < 9; i++)
                if (!string.IsNullOrEmpty(sampleSfx[i])) parts.Add((i + 1) + "=" + sampleSfx[i]);
            return string.Join(" ", parts.ToArray());
        }

        public void SetStatus(string text)
        {
            if (status != null) status.text = text ?? "";
        }

        // ------------------------------------------------------------------------------------ update

        private void Update()
        {
            if (!built || !Application.isPlaying) return;
            ReadInput();
            if (!visible) return;
            Animate();
            UpdateCamera();
        }

        private void ReadInput()
        {
            bool toggle, prev, next, music;
            int digit = -1;
#if ENABLE_INPUT_SYSTEM
            Keyboard kb = Keyboard.current;
            if (kb == null) return;
            toggle = kb.tabKey.wasPressedThisFrame;
            prev = kb.qKey.wasPressedThisFrame;
            next = kb.eKey.wasPressedThisFrame;
            music = kb.mKey.wasPressedThisFrame;
            for (int i = 0; i < 9; i++)
                if (kb[Key.Digit1 + i].wasPressedThisFrame) { digit = i; break; }
#else
            toggle = Input.GetKeyDown(KeyCode.Tab);
            prev = Input.GetKeyDown(KeyCode.Q);
            next = Input.GetKeyDown(KeyCode.E);
            music = Input.GetKeyDown(KeyCode.M);
            for (int i = 0; i < 9; i++)
                if (Input.GetKeyDown(KeyCode.Alpha1 + i)) { digit = i; break; }
#endif
            if (toggle) Toggle();
            if (!visible) return;
            if (prev) PreviousPage();
            if (next) NextPage();
            if (music) NextMusic();
            if (digit >= 0) PlaySample(digit);
        }

        /// <summary>Plays sampleSfx[index] (keys 1-9).</summary>
        public void PlaySample(int index)
        {
            if (sampleSfx == null || index < 0 || index >= sampleSfx.Length || string.IsNullOrEmpty(sampleSfx[index]))
            {
                SetStatus("효과음 " + (index + 1) + ": (지정되지 않음)");
                return;
            }
            bool ok = SimpleAudio.TryPlay(sampleSfx[index]);
            SetStatus("효과음 " + (index + 1) + ": " + sampleSfx[index] + (ok ? "" : "  (클립 없음)"));
        }

        /// <summary>Cycles through the music list, ending with silence (key M).</summary>
        public void NextMusic()
        {
            SimpleAudio audio = SimpleAudio.Instance;
            List<string> names = new List<string>();
            if (musicNames != null && musicNames.Length > 0) names.AddRange(musicNames);
            else if (audio != null) names = audio.MusicNames();
            if (names.Count == 0 || audio == null)
            {
                SetStatus("음악: 클립이 없습니다 (Audio/Music)");
                return;
            }
            musicIndex = (musicIndex + 1) % (names.Count + 1);
            if (musicIndex == names.Count)
            {
                audio.StopMusic();
                SetStatus("음악: 정지");
                return;
            }
            bool ok = audio.Music(names[musicIndex]);
            SetStatus("음악: " + names[musicIndex] + (ok ? "" : "  (클립 없음)"));
        }

        private void Animate()
        {
            float t = Time.time;
            int walkFrame = CharacterSheet.WalkFrameAt(t);
            int poseDir = (int)(t / 2f) % CharacterSheet.DirectionCount;      // attack / hurt turn every 2 s
            int attackPhase = (int)(t * 12f) % 6;                               // 3 frames at 12 fps, then rest
            for (int i = 0; i < booths.Count; i++)
            {
                Booth booth = booths[i];
                if (booth.entry == null || booth.walkFrames == null || !booth.root.activeSelf) continue;
                for (int d = 0; d < CharacterSheet.DirectionCount; d++)
                    booth.walk[d].sprite = booth.walkFrames[d, walkFrame];
                if (booth.attackFrames != null)
                    booth.attack.sprite = attackPhase < CharacterSheet.AttackFrameCount ? booth.attackFrames[poseDir, attackPhase] : booth.walkFrames[poseDir, 0];
                if (booth.hurtFrames != null)
                    booth.hurt.sprite = booth.hurtFrames[poseDir];
            }
        }

        private void UpdateCamera()
        {
            Camera cam = Camera.main;
            if (cam == null) return;
            cam.orthographic = true;
            cam.orthographicSize = cameraSize;
            Vector3 center = (root != null ? root.position : (Vector3)origin) + new Vector3(DesignWidth * 0.5f, DesignHeight * 0.5f, 0f);
            cam.transform.position = new Vector3(center.x, center.y, -10f);
            if (canvas != null && canvas.worldCamera == null) canvas.worldCamera = cam;
        }
    }
}
