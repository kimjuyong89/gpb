// InkPixel → 강호유랑기(GPA) 연동 에디터 도구.
// 이 파일을 GPA 프로젝트의 Assets/_Project/Editor/ 에 복사해서 쓴다. (gpb 저장소 안에서는 컴파일되지 않도록
// GPA 네임스페이스가 있을 때만 켜진다: GPA 프로젝트에 넣으면 아래 define 없이도 동작하도록 #if 를 지워도 된다.)
//
// 메뉴
//   GPA/InkPixel/1. InkPixel 에셋 복사...         gpb 저장소의 Assets/InkPixel 폴더를 골라 Art/Audio 를 Resources 아래로 복사
//   GPA/InkPixel/2. TileDefs JSON 적용 (선택한 RegionData)   tiledefs_<region>.json 으로 tiles/npcs 의 시트·칸을 채운다
//
// JSON 형식은 gpb/Tools/gpa_sim/resolve_tiledefs.py 가 만든다 (키 → 시트 경로, 칸 좌표, 크기, solid, ground, overlay ...).
#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;

namespace GPA.InkPixelTools
{
    [Serializable]
    public class TileDefJson
    {
        public string key; public string sheet; public int cellX, cellY, sizeX = 1, sizeY = 1;
        public bool solid; public string ground = "."; public bool overlay; public string portal = ""; public string encounterNode = "";
    }

    [Serializable]
    public class NpcDefJson
    {
        public string key; public string name; public string sheet; public string prop; public int propCellX, propCellY;
    }

    [Serializable]
    public class TileDefsJson
    {
        public string region; public string sheetBase = "Assets/_Project/Art/Resources/InkPixel/"; public string specialGround; public string playerSheet;
        public List<TileDefJson> tiles = new List<TileDefJson>();
        public List<NpcDefJson> npcs = new List<NpcDefJson>();
    }

    public static class GpaInkPixelTools
    {
        const string ResourcesRoot = "Assets/_Project/Art/Resources";

        // ---------------------------------------------------------------- 1. 에셋 복사
        [MenuItem("GPA/InkPixel/1. InkPixel 에셋 복사...")]
        public static void CopyAssets()
        {
            string src = EditorUtility.OpenFolderPanel("gpb 저장소의 Assets/InkPixel 폴더를 고르세요", "", "");
            if (string.IsNullOrEmpty(src)) return;
            if (!Directory.Exists(Path.Combine(src, "Art")) || !Directory.Exists(Path.Combine(src, "Audio")))
            {
                EditorUtility.DisplayDialog("InkPixel", "선택한 폴더에 Art/ 와 Audio/ 가 없습니다. gpb/Assets/InkPixel 을 고르세요.", "확인");
                return;
            }
            int n = 0;
            // 타일·캐릭터·UI 는 Resources/InkPixel/ 아래에 그대로.
            n += CopyTree(Path.Combine(src, "Art", "Tiles"), ResourcesRoot + "/InkPixel/Tiles", "*.png");
            n += CopyTree(Path.Combine(src, "Art", "Characters"), ResourcesRoot + "/InkPixel/Characters", "*.png");
            n += CopyTree(Path.Combine(src, "Art", "UI"), ResourcesRoot + "/InkPixel/UI", "*.png");
            // 아이콘은 Ui.ItemIcon 이 "Icons/<이름>" 으로 찾으므로 Resources/Icons 에 낱장으로.
            n += CopyTree(Path.Combine(src, "Art", "Icons"), ResourcesRoot + "/Icons", "*.png", topLevelOnly: true);
            n += CopyTree(Path.Combine(src, "Art", "Icons", "Mini"), ResourcesRoot + "/Icons/Mini", "*.png");
            // 전투 이펙트는 Ui.Strip("FX/<이름>", n) 이 찾는 Resources/FX 에.
            n += CopyTree(Path.Combine(src, "Art", "FX"), ResourcesRoot + "/FX", "*.png");
            // 소리는 Sound.Play / Sound.Music 이 찾는 Resources/Audio/Sfx, Audio/Music 에.
            n += CopyTree(Path.Combine(src, "Audio", "Sfx"), ResourcesRoot + "/Audio/Sfx", "*.wav");
            n += CopyTree(Path.Combine(src, "Audio", "Music"), ResourcesRoot + "/Audio/Music", "*.ogg");
            AssetDatabase.Refresh();
            Debug.Log($"[InkPixel] {n}개 파일을 복사했습니다. PixelArtImport 가 16px, Point 필터로 들여옵니다.");
        }

        static int CopyTree(string srcDir, string dstDir, string pattern, bool topLevelOnly = false)
        {
            if (!Directory.Exists(srcDir)) return 0;
            int n = 0;
            var opt = topLevelOnly ? SearchOption.TopDirectoryOnly : SearchOption.AllDirectories;
            foreach (var file in Directory.GetFiles(srcDir, pattern, opt))
            {
                string rel = Path.GetRelativePath(srcDir, file);
                string dst = Path.Combine(dstDir, rel);
                Directory.CreateDirectory(Path.GetDirectoryName(dst));
                File.Copy(file, dst, true);
                n++;
            }
            return n;
        }

        // ---------------------------------------------------------------- 2. TileDefs 적용
        [MenuItem("GPA/InkPixel/2. TileDefs JSON 적용 (선택한 RegionData)")]
        public static void ApplyTileDefs()
        {
            var region = Selection.activeObject as GPA.World.RegionData;
            if (region == null)
            {
                EditorUtility.DisplayDialog("InkPixel", "프로젝트 창에서 RegionData 에셋(예: Data/Regions/Baekrojin)을 먼저 선택하세요.", "확인");
                return;
            }
            string path = EditorUtility.OpenFilePanel("tiledefs_<region>.json 선택", "", "json");
            if (string.IsNullOrEmpty(path)) return;
            var json = JsonUtility.FromJson<TileDefsJson>(File.ReadAllText(path));
            if (json == null || json.tiles == null)
            {
                Debug.LogError("[InkPixel] JSON 을 읽지 못했습니다: " + path);
                return;
            }
            Undo.RecordObject(region, "Apply InkPixel TileDefs");
            int tilesSet = 0, npcsSet = 0, missing = 0;
            foreach (var t in json.tiles)
            {
                var tex = LoadTexture(json.sheetBase, t.sheet, ref missing);
                var def = region.tiles.Find(d => d.key == t.key);
                if (def == null) { def = new GPA.World.TileDef { key = t.key }; region.tiles.Add(def); }
                def.sheet = tex;
                def.cell = new Vector2Int(t.cellX, t.cellY);
                def.size = new Vector2Int(Mathf.Max(1, t.sizeX), Mathf.Max(1, t.sizeY));
                def.solid = t.solid;
                def.ground = string.IsNullOrEmpty(t.ground) ? "." : t.ground;
                def.overlay = t.overlay;
                if (!string.IsNullOrEmpty(t.portal)) def.portal = t.portal;
                if (!string.IsNullOrEmpty(t.encounterNode)) def.encounterNode = t.encounterNode;
                tilesSet++;
            }
            foreach (var n in json.npcs)
            {
                var def = region.npcs.Find(d => d.key == n.key);
                if (def == null)
                {
                    Debug.LogWarning($"[InkPixel] RegionData 에 NPC 키 '{n.key}' 가 없어 건너뜁니다 (이름: {n.name}).");
                    continue;
                }
                if (!string.IsNullOrEmpty(n.sheet))
                {
                    def.sheet = LoadTexture(json.sheetBase, n.sheet, ref missing);
                    def.prop = null;
                }
                if (!string.IsNullOrEmpty(n.prop))
                {
                    def.prop = LoadTexture(json.sheetBase, n.prop, ref missing);
                    def.propCell = new Vector2Int(n.propCellX, n.propCellY);
                }
                npcsSet++;
            }
            if (!string.IsNullOrEmpty(json.specialGround)) region.specialGround = json.specialGround;
            EditorUtility.SetDirty(region);
            AssetDatabase.SaveAssets();
            Debug.Log($"[InkPixel] {region.name}: 타일 {tilesSet}개, NPC {npcsSet}개 적용. 찾지 못한 시트 {missing}개 (먼저 '1. InkPixel 에셋 복사' 를 실행했는지 확인).");
        }

        static Texture2D LoadTexture(string sheetBase, string rel, ref int missing)
        {
            string assetPath = (sheetBase ?? "").TrimEnd('/') + "/" + rel.Replace('\\', '/');
            var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(assetPath);
            if (tex == null) { missing++; Debug.LogWarning("[InkPixel] 시트를 찾지 못했습니다: " + assetPath); }
            return tex;
        }
    }
}
#endif
