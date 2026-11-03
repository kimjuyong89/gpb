// InkPixel demo — a walkable region built exactly like GPA's World/RegionView.cs (ASSET_SPEC §7.2):
// ground under props, props anchored at their top-left letter, Y-sorting 1000 - round(y*10),
// 4x4 walk frames from a 128x64 sheet, grid walking at 6 cells/s (Shift x1.8), 경공 leap on F,
// attack frames on J/Space, talk on E/Enter (face panel), step SFX through SimpleAudio,
// camera follow clamped to the map at orthographicSize 7.5.
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

namespace InkPixel.Demo
{
    [AddComponentMenu("InkPixel/Region Viewer")]
    [DisallowMultipleComponent]
    public class RegionViewer : MonoBehaviour
    {
        /// <summary>Name of the child that holds everything Build() creates (destroyed by Clear()).</summary>
        public const string MapRootName = "Map";
        /// <summary>GPA RegionView.StepSpeed: cells per second.</summary>
        public const float DefaultStepSpeed = 6f;
        /// <summary>GPA RegionView.RunMultiplier.</summary>
        public const float DefaultRunMultiplier = 1.8f;
        /// <summary>GPA RegionView.LeapHeight (world units at the top of a leap).</summary>
        public const float LeapHeight = 0.9f;
        /// <summary>Sorting order of ground tiles (GPA: -1000).</summary>
        public const int GroundOrder = -1000;

        [Header("Map data")]
        [Tooltip("Layout text, one row per line and one letter per cell (GPA RegionData.layout). Overrides the inline layout when set.")]
        public TextAsset layoutAsset;
        [Tooltip("Inline layout used when no TextAsset is assigned.")]
        [TextArea(6, 30)] public string layout = "";
        [Tooltip("Letter -> tile / NPC definitions (GPA RegionData.tiles and npcs).")]
        public TileDefs tileDefs;
        [Tooltip("Player character sheet (128x64, ASSET_SPEC §5.1). Falls back to TileDefs.playerSheet.")]
        public Texture2D playerSheet;

        [Header("Movement")]
        [Tooltip("Walking speed in cells per second (GPA: 6).")]
        public float stepSpeed = DefaultStepSpeed;
        [Tooltip("Speed multiplier while Shift is held (GPA: 1.8).")]
        public float runMultiplier = DefaultRunMultiplier;
        [Tooltip("Enable running and the 경공 leap on F. GPA turns this on once a 경공 is learned; the demo defaults to on.")]
        public bool agile = true;
        [Tooltip("Cells a leap can cover (GPA: 3).")]
        public int leapReach = GridWalker.DefaultLeapReach;
        [Tooltip("Seconds the attack pose (attack frames 0-2) is shown after J/Space.")]
        public float attackDuration = 0.25f;
        [Tooltip("Seconds the talk panel stays visible after E/Enter.")]
        public float talkDuration = 2f;
        [Tooltip("Ignore input (movement in progress still finishes).")]
        public bool paused;
        [Tooltip("Build the map automatically in Start() when playing.")]
        public bool buildOnStart = true;

        [Header("Camera")]
        [Tooltip("Move Camera.main to follow the player, clamped so nothing outside the map shows (GPA).")]
        public bool followCamera = true;
        [Tooltip("Orthographic size applied to the camera (GPA: 7.5).")]
        public float cameraSize = 7.5f;

        [Header("Audio and FX (optional, by SimpleAudio clip name)")]
        [Tooltip("Clip names picked at random when a step completes.")]
        public string[] stepSfx = { "Step1", "Step2", "Step3" };
        [Tooltip("Clip played on attack.")]
        public string attackSfx = "Slash";
        [Tooltip("Clip played when talking to an NPC.")]
        public string talkSfx = "Talk";
        [Tooltip("Clip played on a leap.")]
        public string leapSfx = "Leap";
        [Tooltip("Clip played when the exit letter is reached.")]
        public string exitSfx = "Accept";
        [Tooltip("FX strip spawned in front of the player on attack (e.g. Art/FX/Slash.png). Optional.")]
        public Texture2D attackFx;
        [Tooltip("Frame count of the attack FX strip (its sidecar stripFrames).")]
        public int attackFxFrames = 5;
        [Tooltip("Playback fps of the attack FX strip (its sidecar stripFps).")]
        public float attackFxFps = 16f;

        /// <summary>Raised when the player talks to an NPC (GPA RegionView.OnTalk).</summary>
        public event Action<NpcDef> OnTalk;
        /// <summary>Raised when the player reaches the exit letter (GPA RegionView.OnExit).</summary>
        public event Action OnExit;
        /// <summary>Raised when a leap starts (GPA RegionView.OnLeap).</summary>
        public event Action OnLeap;
        /// <summary>Raised when a step ends on a non-exit cell with that cell's tile (GPA RegionView.OnStep).</summary>
        public event Action<TileDef> OnStep;

        private class NpcInstance
        {
            public NpcDef def;
            public SpriteRenderer renderer;
            public Sprite[,] frames;
        }

        private readonly Dictionary<Vector2Int, NpcInstance> npcs = new Dictionary<Vector2Int, NpcInstance>();
        private readonly GridWalker walker = new GridWalker();
        private readonly HashSet<string> warned = new HashSet<string>();
        private string[] rows = new string[0];
        private bool[,] solid;
        private int width;
        private int height;
        private Transform mapRoot;
        private Transform player;
        private SpriteRenderer playerSr;
        private Sprite[,] walkFrames;
        private Sprite[,] attackFrames;
        private bool running;
        private float attackTimer;
        private float talkTimer;
        private bool built;

        // Talk panel (created on first use while playing).
        private GameObject talkPanel;
        private Image talkFace;
        private Text talkName;
        private Text talkLine;

        public bool IsBuilt { get { return built; } }
        public int Width { get { return width; } }
        public int Height { get { return height; } }
        /// <summary>GPA RegionView.Cell.</summary>
        public Vector2Int Cell { get { return walker.cell; } }
        /// <summary>GPA RegionView.Previous.</summary>
        public Vector2Int Previous { get { return walker.previous; } }
        /// <summary>GPA RegionView.Moving.</summary>
        public bool Moving { get { return walker.Moving; } }
        /// <summary>0 down, 1 up, 2 left, 3 right.</summary>
        public int Facing { get { return walker.facing; } }
        /// <summary>GPA RegionView.Running.</summary>
        public bool Running { get { return running; } }
        public GridWalker Walker { get { return walker; } }
        public Transform Player { get { return player; } }
        public Transform MapRoot { get { return mapRoot; } }
        public int NpcCount { get { return npcs.Count; } }

        /// <summary>The layout text in use (TextAsset first, inline string otherwise).</summary>
        public string LayoutText
        {
            get { return layoutAsset != null ? layoutAsset.text : (layout ?? ""); }
        }

        /// <summary>GPA RegionData.Rows: layout.Replace("\r", "").Trim('\n').Split('\n').</summary>
        public static string[] RowsOf(string text)
        {
            return (text ?? "").Replace("\r", "").Trim('\n').Split('\n');
        }

        /// <summary>GPA RegionView.OrderAt: lower on screen = drawn in front.</summary>
        public static int OrderAt(float y)
        {
            return 1000 - Mathf.RoundToInt(y * 10f);
        }

        private void Start()
        {
            if (buildOnStart && Application.isPlaying) Build();
        }

        // ------------------------------------------------------------------------------------- build

        /// <summary>Destroys everything a previous Build() created (works in edit mode too).</summary>
        public void Clear()
        {
            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                Transform child = transform.GetChild(i);
                if (child.name == MapRootName) DestroyNow(child.gameObject);
            }
            npcs.Clear();
            mapRoot = null;
            player = null;
            playerSr = null;
            walkFrames = null;
            attackFrames = null;
            solid = null;
            width = height = 0;
            attackTimer = 0f;
            built = false;
        }

        /// <summary>
        /// Builds the map from the layout + TileDefs exactly like GPA's RegionView.Build. Safe to call
        /// repeatedly and in edit mode (no coroutines); problems are warnings, never exceptions.
        /// </summary>
        [ContextMenu("Build")]
        public void Build()
        {
            Clear();
            rows = RowsOf(LayoutText);
            if (tileDefs == null)
            {
                Warn("tiledefs", "RegionViewer '" + name + "': no TileDefs assigned; nothing built.");
                return;
            }
            if (rows.Length == 0 || (rows.Length == 1 && rows[0].Length == 0))
            {
                Warn("layout", "RegionViewer '" + name + "': the layout is empty; nothing built.");
                return;
            }

            height = rows.Length;
            width = 0;
            foreach (string r in rows) width = Mathf.Max(width, r.Length);
            solid = new bool[width, height];

            var rootGo = new GameObject(MapRootName);
            rootGo.transform.SetParent(transform, false);
            mapRoot = rootGo.transform;

            string start = tileDefs.start ?? "";
            string exit = tileDefs.exit ?? "";
            string specialGround = tileDefs.specialGround ?? "";
            Vector2Int startCell = Vector2Int.zero;
            bool foundStart = false;

            for (int row = 0; row < height; row++)
            {
                for (int x = 0; x < width; x++)
                {
                    char c = x < rows[row].Length ? rows[row][x] : ' ';
                    if (c == ' ') continue;
                    bool special = start.IndexOf(c) == 0 || exit.IndexOf(c) == 0 || tileDefs.Npc(c) != null;
                    TileDef def = special
                        ? (specialGround.Length > 0 ? tileDefs.Tile(specialGround[0]) : null)
                        : tileDefs.Tile(c);
                    if (def == null)
                    {
                        if (special) Warn("special", "RegionViewer: special ground letter '" + specialGround + "' has no TileDef; start/exit/NPC cells have no ground.");
                        else Warn("letter:" + c, "RegionViewer: letter '" + c + "' has no TileDef; skipped.");
                        if (start.IndexOf(c) == 0) { startCell = new Vector2Int(x, row); foundStart = true; }
                        PlaceNpc(c, x, row);
                        continue;
                    }

                    bool isProp = def.size != Vector2Int.one || def.overlay;
                    TileDef ground = isProp
                        ? (string.IsNullOrEmpty(def.ground) ? null : tileDefs.Tile(def.ground[0]))
                        : def;
                    if (isProp && ground == null && !string.IsNullOrEmpty(def.ground))
                        Warn("ground:" + def.ground, "RegionViewer: ground letter '" + def.ground + "' of '" + def.key + "' has no TileDef.");
                    if (ground != null)
                    {
                        if (ground.sheet != null)
                            Place(x + "," + row, CellSlicer.Slice(ground.sheet, ground.cell, Vector2Int.one), World(x, row), GroundOrder);
                        else
                            Warn("sheet:" + ground.key, "RegionViewer: tile '" + ground.key + "' has no sheet; its cells stay empty.");
                        if (ground.solid) solid[x, row] = true;
                    }

                    if (isProp)
                    {
                        var bottomLeft = new Vector2(x, height - row - def.size.y);
                        if (def.sheet != null)
                            Place(def.key + "@" + x + "," + row, CellSlicer.Slice(def.sheet, def.cell, def.size), bottomLeft, OrderAt(bottomLeft.y));
                        else
                            Warn("sheet:" + def.key, "RegionViewer: prop '" + def.key + "' has no sheet; not drawn (its footprint still counts).");
                        if (def.solid)
                            for (int dy = 0; dy < def.size.y; dy++)
                                for (int dx = 0; dx < def.size.x; dx++)
                                    if (x + dx < width && row + dy < height) solid[x + dx, row + dy] = true;
                    }

                    if (start.IndexOf(c) == 0) { startCell = new Vector2Int(x, row); foundStart = true; }
                    PlaceNpc(c, x, row);
                }
            }

            if (!foundStart)
                Warn("start", "RegionViewer: no start letter '" + start + "' in the layout; the player starts at (0,0).");
            walker.Place(startCell);

            Texture2D sheet = playerSheet != null ? playerSheet : tileDefs.playerSheet;
            if (sheet == null)
                Warn("player", "RegionViewer: no player sheet (RegionViewer.playerSheet or TileDefs.playerSheet); the player is invisible.");
            else if (!CharacterSheet.IsStandardSheet(sheet))
                Warn("player-size", "RegionViewer: player sheet '" + sheet.name + "' is " + sheet.width + "x" + sheet.height + ", not 128x64 (ASSET_SPEC §5.1).");
            walkFrames = CharacterSheet.Frames(sheet);
            attackFrames = CharacterSheet.HasAttackColumns(sheet) ? CharacterSheet.AttackFrames(sheet) : null;
            playerSr = Place("Player", walkFrames != null ? walkFrames[0, 0] : null, World(startCell.x, startCell.y), 0);
            player = playerSr.transform;

            built = true;
            UpdatePlayer();
        }

        private void PlaceNpc(char c, int x, int row)
        {
            NpcDef npc = tileDefs.Npc(c);
            if (npc == null) return;
            Sprite[,] frames = npc.prop != null ? Still(npc) : CharacterSheet.Frames(npc.sheet);
            if (frames == null)
            {
                Warn("npc:" + c, "RegionViewer: NPC '" + npc.name + "' (" + c + ") has neither a sheet nor a prop; skipped.");
                return;
            }
            if (npc.prop == null && !CharacterSheet.IsStandardSheet(npc.sheet))
                Warn("npc-size:" + c, "RegionViewer: NPC sheet '" + npc.sheet.name + "' is " + npc.sheet.width + "x" + npc.sheet.height + ", not 128x64.");
            Vector2 pos = World(x, row);
            var instance = new NpcInstance();
            instance.def = npc;
            instance.frames = frames;
            instance.renderer = Place(string.IsNullOrEmpty(npc.name) ? "NPC " + c : npc.name, frames[0, 0], pos, OrderAt(pos.y) + 5);
            npcs[new Vector2Int(x, row)] = instance;
        }

        /// <summary>GPA RegionView.Still: a prop NPC shows the same cell from every side.</summary>
        private static Sprite[,] Still(NpcDef npc)
        {
            var f = new Sprite[CharacterSheet.DirectionCount, CharacterSheet.WalkFrameCount];
            Sprite s = CellSlicer.Slice(npc.prop, npc.propCell, Vector2Int.one);
            for (int d = 0; d < CharacterSheet.DirectionCount; d++)
                for (int i = 0; i < CharacterSheet.WalkFrameCount; i++)
                    f[d, i] = s;
            return f;
        }

        /// <summary>GPA RegionView.Place: a child SpriteRenderer at a local position with a sorting order.</summary>
        private SpriteRenderer Place(string objectName, Sprite sprite, Vector2 pos, int order)
        {
            var go = new GameObject(objectName);
            go.transform.SetParent(mapRoot, false);
            go.transform.localPosition = pos;
            var sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = sprite;
            sr.sortingOrder = order;
            return sr;
        }

        /// <summary>GPA RegionView.World: rows count from the top, world y grows upward.</summary>
        private Vector2 World(int x, int row)
        {
            return new Vector2(x, height - 1 - row);
        }

        private bool Walkable(Vector2Int c)
        {
            return c.x >= 0 && c.y >= 0 && c.x < width && c.y < height && !solid[c.x, c.y] && !npcs.ContainsKey(c);
        }

        private char LetterAt(Vector2Int c)
        {
            if (c.y < 0 || c.y >= rows.Length || c.x < 0 || c.x >= rows[c.y].Length) return ' ';
            return rows[c.y][c.x];
        }

        /// <summary>GPA RegionView.TileAt.</summary>
        public TileDef TileAt(Vector2Int c)
        {
            char letter = LetterAt(c);
            return letter == ' ' || tileDefs == null ? null : tileDefs.Tile(letter);
        }

        /// <summary>GPA RegionView.Exits.</summary>
        public bool Exits(Vector2Int c)
        {
            char letter = LetterAt(c);
            return letter != ' ' && tileDefs != null && (tileDefs.exit ?? "").IndexOf(letter) == 0;
        }

        /// <summary>The NPC standing on <paramref name="c"/>, or null.</summary>
        public NpcDef NpcAt(Vector2Int c)
        {
            NpcInstance n;
            return npcs.TryGetValue(c, out n) ? n.def : null;
        }

        // ------------------------------------------------------------------------------------ update

        private void Update()
        {
            if (!built || !Application.isPlaying) return;
            float dt = Time.deltaTime;
            if (walker.Moving)
            {
                // GPA: a leap takes StepSpeed / leapCells; running only applies to plain steps.
                float speed = walker.Leaping ? stepSpeed : (running && agile ? stepSpeed * runMultiplier : stepSpeed);
                if (walker.Advance(dt, speed)) Arrived();
            }
            else if (!paused)
            {
                ReadInput();
            }
            if (attackTimer > 0f) attackTimer -= dt;
            if (talkTimer > 0f)
            {
                talkTimer -= dt;
                if (talkTimer <= 0f) HideTalk();
            }
            UpdatePlayer();
        }

        private void ReadInput()
        {
            int dir;
            bool leap, talk, attack;
#if ENABLE_INPUT_SYSTEM
            Keyboard kb = Keyboard.current;
            if (kb == null) return;
            dir = kb.downArrowKey.isPressed || kb.sKey.isPressed ? 0
                : kb.upArrowKey.isPressed || kb.wKey.isPressed ? 1
                : kb.leftArrowKey.isPressed || kb.aKey.isPressed ? 2
                : kb.rightArrowKey.isPressed || kb.dKey.isPressed ? 3 : -1;
            running = kb.leftShiftKey.isPressed || kb.rightShiftKey.isPressed;
            leap = kb.fKey.wasPressedThisFrame;
            talk = kb.eKey.wasPressedThisFrame || kb.enterKey.wasPressedThisFrame || kb.numpadEnterKey.wasPressedThisFrame;
            attack = kb.jKey.wasPressedThisFrame || kb.spaceKey.wasPressedThisFrame;
#else
            dir = Input.GetKey(KeyCode.DownArrow) || Input.GetKey(KeyCode.S) ? 0
                : Input.GetKey(KeyCode.UpArrow) || Input.GetKey(KeyCode.W) ? 1
                : Input.GetKey(KeyCode.LeftArrow) || Input.GetKey(KeyCode.A) ? 2
                : Input.GetKey(KeyCode.RightArrow) || Input.GetKey(KeyCode.D) ? 3 : -1;
            running = Input.GetKey(KeyCode.LeftShift) || Input.GetKey(KeyCode.RightShift);
            leap = Input.GetKeyDown(KeyCode.F);
            talk = Input.GetKeyDown(KeyCode.E) || Input.GetKeyDown(KeyCode.Return) || Input.GetKeyDown(KeyCode.KeypadEnter);
            attack = Input.GetKeyDown(KeyCode.J) || Input.GetKeyDown(KeyCode.Space);
#endif
            if (leap) Leap();
            if (dir >= 0) Move(dir);
            if (talk) Interact();
            if (attack) Attack();
        }

        /// <summary>GPA RegionView.Move: face <paramref name="dir"/> and step when the next cell is free.</summary>
        public void Move(int dir)
        {
            if (!built) return;
            walker.TryMove(dir, Walkable);
        }

        /// <summary>GPA RegionView.Leap: jump up to leapReach cells in the facing direction (needs <c>agile</c>).</summary>
        public bool Leap()
        {
            if (!built || !agile || walker.Moving) return false;
            if (!walker.TryLeap(Walkable, Mathf.Max(2, leapReach))) return false;
            SimpleAudio.TryPlay(leapSfx);
            if (OnLeap != null) OnLeap();
            return true;
        }

        /// <summary>GPA RegionView.Interact: the NPC in front turns to the player; the talk panel shows its face.</summary>
        public void Interact()
        {
            if (!built) return;
            NpcInstance npc;
            if (!npcs.TryGetValue(walker.cell + GridWalker.Step(walker.facing), out npc)) return;
            int back = GridWalker.Opposite(walker.facing);
            if (npc.frames != null && npc.frames[back, 0] != null) npc.renderer.sprite = npc.frames[back, 0];
            SimpleAudio.TryPlay(talkSfx);
            ShowTalk(npc.def);
            if (OnTalk != null) OnTalk(npc.def);
        }

        /// <summary>Shows the attack frames (sheet columns 4-7) for attackDuration seconds and spawns the attack FX strip.</summary>
        public void Attack()
        {
            if (!built || attackTimer > 0f) return;
            attackTimer = Mathf.Max(0.05f, attackDuration);
            SimpleAudio.TryPlay(attackSfx);
            if (attackFrames == null)
                Warn("attack", "RegionViewer: the player sheet has no attack columns (needs 128x64); only the SFX plays.");
            if (attackFx != null && Application.isPlaying && mapRoot != null)
            {
                // A 48x48 strip frame is 3x3 units with pivot (0,0): centre it on the cell in front.
                Vector2 front = World(walker.cell.x, walker.cell.y) + (Vector2)GridWalker.Dirs[walker.facing];
                var go = new GameObject("AttackFx");
                go.transform.SetParent(mapRoot, false);
                go.transform.localPosition = front + new Vector2(0.5f, 0.5f) - new Vector2(1.5f, 1.5f);
                var sr = go.AddComponent<SpriteRenderer>();
                sr.sortingOrder = OrderAt(front.y) + 50;
                var fx = go.AddComponent<StripPlayer>();
                fx.playOnEnable = false;
                fx.destroyWhenDone = true;
                int frames = Mathf.Max(1, attackFxFrames);
                fx.Play(attackFx, frames, attackFxFps, false);
                // Static strips (fps 0) would stay forever: give every FX a hard lifetime.
                float lifetime = attackFxFps > 0f ? frames / attackFxFps + 0.1f : attackTimer;
                Destroy(go, lifetime);
            }
        }

        private void Arrived()
        {
            if (Exits(walker.cell))
            {
                SimpleAudio.TryPlay(exitSfx);
                Toast("출구", "강호(월드맵)로 나가는 칸입니다. 데모에서는 그대로 머뭅니다.");
                if (OnExit != null) OnExit();
                return;
            }
            if (stepSfx != null && stepSfx.Length > 0)
                SimpleAudio.TryPlay(stepSfx[UnityEngine.Random.Range(0, stepSfx.Length)]);
            TileDef tile = TileAt(walker.cell);
            if (tile != null)
            {
                if (!string.IsNullOrEmpty(tile.portal)) Toast("입구", "'" + tile.portal + "' 노드로 들어가는 칸 (portal)");
                else if (!string.IsNullOrEmpty(tile.encounterNode)) Toast("조우 지대", "'" + tile.encounterNode + "' 조우를 굴리는 칸 (encounterNode)");
            }
            if (OnStep != null) OnStep(tile);
        }

        /// <summary>GPA RegionView.UpdatePlayer: position, walk/attack frame, sorting and the clamped camera.</summary>
        private void UpdatePlayer()
        {
            if (player == null) return;
            Vector2 from = World(walker.cell.x, walker.cell.y);
            Vector2 to = World(walker.target.x, walker.target.y);
            Vector2 pos = walker.Lerp(from, to);
            float lift = walker.Leaping ? Mathf.Sin(walker.moveT * Mathf.PI) * LeapHeight : 0f;
            player.localPosition = pos + Vector2.up * lift;

            int facing = walker.facing;
            Sprite sprite = null;
            if (attackTimer > 0f && attackFrames != null)
            {
                float t = 1f - attackTimer / Mathf.Max(0.05f, attackDuration);
                int i = Mathf.Clamp((int)(t * CharacterSheet.AttackFrameCount), 0, CharacterSheet.AttackFrameCount - 1);
                sprite = attackFrames[facing, i];
            }
            else if (walkFrames != null)
            {
                sprite = walkFrames[facing, walker.Moving ? CharacterSheet.WalkFrameAt(Time.time) : 0];
            }
            playerSr.sprite = sprite;
            playerSr.sortingOrder = OrderAt(pos.y) + (walker.Leaping ? 500 : 5); // in front of everything while leaping

            if (!followCamera) return;
            Camera cam = Camera.main;
            if (cam == null) return;
            cam.orthographic = true;
            cam.orthographicSize = cameraSize;
            float halfW = cam.orthographicSize * cam.aspect, halfH = cam.orthographicSize;
            Vector2 center = pos + new Vector2(0.5f, 0.5f);
            // When the map is larger than the view, keep the view inside the map.
            center.x = width > halfW * 2 ? Mathf.Clamp(center.x, halfW, width - halfW) : width / 2f;
            center.y = height > halfH * 2 ? Mathf.Clamp(center.y, halfH, height - halfH) : height / 2f;
            Vector3 world = mapRoot != null ? mapRoot.TransformPoint(center) : (Vector3)center;
            cam.transform.position = new Vector3(world.x, world.y, -10f);
        }

        // -------------------------------------------------------------------------------- talk panel

        /// <summary>Shows the NPC's face (when it has one) and name for talkDuration seconds.</summary>
        public void ShowTalk(NpcDef npc)
        {
            if (npc == null || !Application.isPlaying) return;
            EnsureTalkPanel();
            if (talkPanel == null) return;
            Sprite face = DemoUi.FullSprite(npc.face);
            talkFace.sprite = face;
            talkFace.gameObject.SetActive(face != null);
            if (face == null) Warn("face:" + npc.key, "RegionViewer: NPC '" + npc.name + "' has no face texture (<name>_face.png); showing the name only.");
            talkName.text = npc.name ?? "";
            talkLine.text = face != null ? "……" : "(얼굴 그림 없음)";
            talkPanel.SetActive(true);
            talkTimer = Mathf.Max(0.1f, talkDuration);
        }

        /// <summary>Shows a short message in the talk panel (no face).</summary>
        public void Toast(string title, string line)
        {
            if (!Application.isPlaying) return;
            EnsureTalkPanel();
            if (talkPanel == null) return;
            talkFace.sprite = null;
            talkFace.gameObject.SetActive(false);
            talkName.text = title ?? "";
            talkLine.text = line ?? "";
            talkPanel.SetActive(true);
            talkTimer = Mathf.Max(0.1f, talkDuration);
        }

        public void HideTalk()
        {
            talkTimer = 0f;
            if (talkPanel != null) talkPanel.SetActive(false);
        }

        private void EnsureTalkPanel()
        {
            if (talkPanel != null) return;
            Canvas canvas = DemoUi.CreateOverlayCanvas("TalkCanvas", 100, transform);
            Image panel = DemoUi.CreateImage("TalkPanel", canvas.transform, new Color(DemoUi.Ink.r, DemoUi.Ink.g, DemoUi.Ink.b, 0.88f));
            DemoUi.Layout(panel.rectTransform, Vector2.zero, Vector2.zero, Vector2.zero, new Vector2(24f, 24f), new Vector2(440f, 120f));
            talkPanel = panel.gameObject;

            talkFace = DemoUi.CreateImage("Face", panel.transform, Color.white);
            talkFace.preserveAspect = true;
            DemoUi.Layout(talkFace.rectTransform, Vector2.zero, Vector2.zero, Vector2.zero, new Vector2(12f, 12f), new Vector2(96f, 96f));

            talkName = DemoUi.CreateText("Name", panel.transform, "", 22, DemoUi.Paper, TextAnchor.UpperLeft);
            DemoUi.Layout(talkName.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(124f, -14f), new Vector2(300f, 30f));

            talkLine = DemoUi.CreateText("Line", panel.transform, "", 16, DemoUi.PaperLight, TextAnchor.UpperLeft);
            DemoUi.Layout(talkLine.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(124f, -52f), new Vector2(300f, 56f));

            talkPanel.SetActive(false);
        }

        // ----------------------------------------------------------------------------------- helpers

        private void Warn(string key, string message)
        {
            if (warned.Add(key)) Debug.LogWarning("[InkPixel] " + message, this);
        }

        private static void DestroyNow(GameObject go)
        {
            if (go == null) return;
            if (Application.isPlaying) Destroy(go);
            else DestroyImmediate(go);
        }
    }
}
