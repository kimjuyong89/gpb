# InkPixel 데모 씬 (`Generated/Scenes/InkPixelDemo.unity`)

InkPixel 팩이 **강호유랑기(GPA)의 코드 그대로** 쓰일 수 있다는 것을 Unity 안에서 눈으로 확인하는 씬입니다.
지도는 GPA의 `World/RegionView.cs`와 똑같은 계산으로 자르고 그리며(16px 칸, 왼쪽 위 기준, 소품은 글자 칸이
왼쪽 위, `sortingOrder = 1000 - round(y*10)`), 캐릭터는 128x64 시트의 4열 x 4행을 `Sprite.Create(tex, rect,
Vector2.zero, 16)`으로 잘라 걷고, FX 띠는 `Ui.Strip`처럼 균등 분할해 돌립니다. 그림이 하나라도 빠져 있으면
예외 대신 경고만 남기고 나머지를 그립니다.

## 만드는 법

| 방법 | 설명 |
|---|---|
| `Tools / InkPixel / Setup All` | 1 (임포트·슬라이스) → 2 (애니메이션) → 3 (타일) 뒤에 데모 씬까지 만듭니다. |
| `Tools / InkPixel / 4. Build Demo Scene` | 데모 씬만 다시 만듭니다. 몇 번을 돌려도 같은 결과입니다. |

빌더(`Scripts/Editor/DemoSceneBuilder.cs`)는 다음을 합니다.

1. `Assets/InkPixel/Demo/demo_tiledefs.json`을 읽어 `Generated/Scenes/InkPixelDemoTileDefs.asset`(`TileDefs`)을 만듭니다.
   각 항목의 `sprite` 이름을 `Art/**/*.sprites.json` 사이드카에서 찾아 **칸 좌표·크기를 자동으로 채우고**, 못 찾으면
   JSON에 적힌 `cellX/cellY/sizeX/sizeY`를 그대로 씁니다. NPC 시트 옆의 `<이름>_face.png`가 있으면 얼굴로 붙입니다.
2. `Art/Characters/*.png`(얼굴 제외), `Art/FX/*.png`(사이드카의 `stripFrames`/`stripFps`), `Audio/Sfx/*.wav`,
   `Audio/Music/*.ogg`를 폴더에서 찾아 갤러리와 `SimpleAudio`에 넣습니다. 빠진 파일은 경고로만 알립니다.
3. 빈 씬을 새로 만들어 아래 오브젝트를 놓고 `Generated/Scenes/InkPixelDemo.unity`로 저장한 뒤 Build Settings에
   추가합니다. 열려 있던 씬이 수정 중이면 먼저 저장할지 묻습니다.
4. 에디터에서도 바로 보이도록 지도와 갤러리를 한 번 만들어 둡니다(`RegionViewer.Build()` / `GalleryController.Build()`는
   코루틴 없이 편집 모드에서도 동작). 이때 만든 오브젝트는 씬에 저장되지만 스프라이트는 `Sprite.Create`로 잘라 낸
   런타임 객체라 씬을 다시 열면 비어 보입니다. Play를 누르면 `Start()`에서 전부 지우고 다시 만들고, 편집 모드에서
   다시 보고 싶으면 컴포넌트의 컨텍스트 메뉴 **Build**를 누르면 됩니다.

콘솔 마지막 줄에 요약이 찍힙니다. 예: `characters 59 (faces 51), FX strips 29, SFX 90, music 13, tiles 35
(35 resolved from sidecars, 0 unresolved), NPCs 23 (faces 23), missing sheets 0, warnings 0`.

## 씬 구성

| 오브젝트 | 컴포넌트 | 내용 |
|---|---|---|
| Main Camera | Camera, AudioListener | 직교 7.5, 배경 먹색 `#1e1b18`. 지도에서는 주인공을 따라가며 GPA와 같은 식으로 지도 밖이 안 보이게 붙잡습니다. |
| Audio | `SimpleAudio` | 효과음·음악 목록. `Play("Slash")`, `Music("Town")`처럼 이름(대소문자 무시)으로 부릅니다. 시작 음악 `Town`. |
| Region | `RegionViewer` | `Demo/demo_layout.txt` + `TileDefs` + `Characters/hero_1.png`. 강변 마을 32x20칸. |
| Gallery | `GalleryController` | 지도 오른쪽(x=48)에 있는 두 번째 구역. Tab으로 카메라를 옮깁니다. |
| Canvas | Canvas, Text | 화면 왼쪽 위 조작 안내(내장 `LegacyRuntime.ttf`). |
| EventSystem | EventSystem + 입력 모듈 | 새 Input System이 켜져 있으면 `InputSystemUIInputModule`, 아니면 `StandaloneInputModule`. |

## 조작

| 키 | 지도 | 갤러리 |
|---|---|---|
| WASD / 방향키 | 한 칸씩 걷기 (초당 6칸, 걷는 동안 4프레임을 8fps로) | |
| Shift | 달리기 (1.8배) | |
| F | 경공 도약: 보는 쪽으로 최대 3칸, 가장 멀리 내릴 수 있는 칸에 착지 (강 위 섬의 은둔 노인은 이걸로만 닿습니다) | |
| J / Space | 공격: 시트 4~7열의 공격 3프레임을 0.25초 보여 주고 앞 칸에 `FX/Slash` 띠를 한 번 재생, 효과음 `Slash` | |
| E / Enter | 앞 칸 NPC에게 말 걸기: NPC가 주인공을 돌아보고, 왼쪽 아래 패널에 얼굴(`<이름>_face.png`)과 이름이 2초 뜹니다 | E = 다음 쪽 |
| Tab | 갤러리로 | 지도로 |
| Q / E | | 이전 / 다음 쪽 |
| 1 ~ 9 | | 효과음 (기본 `Slash Hit1 Impact Accept Cancel Coin Qi Gong Victory`, 없는 건 다른 클립으로 채움) |
| M | | 음악 바꾸기: Town → World → Battle → 나머지 → 정지 |

걸음마다 `Step1~3` 중 하나가 납니다. 출구 글자(`E`)를 밟으면 `Accept`가 나고 "출구" 안내가 뜹니다(데모라 이동은
하지 않습니다). `portal`이나 `encounterNode`가 적힌 칸(객잔 앞, 갈대밭)은 밟을 때 안내만 보여 줍니다.

## 갤러리가 보여 주는 것

- **캐릭터 부스** (한 쪽에 12장, 3열 x 4행): 얼굴(있으면) · 걷기 4방향(down, up, left, right)이 제자리에서 8fps로 걷기 ·
  공격 3프레임(12fps, 2초마다 방향이 바뀜) · 피격 자세. 아래에 시트 이름.
- **FX 띠** (한 쪽에 8개): 사이드카의 `stripFrames`/`stripFps`로 반복 재생. `Arrow`, `Shadow`처럼 fps 0인 띠는 정지 그림.
  라벨에 `이름 N f X fps`.
- 쪽 수는 캐릭터 쪽과 FX 쪽 중 많은 쪽을 따릅니다(59장이면 5쪽).

## 데이터 파일

### `Assets/InkPixel/Demo/demo_layout.txt`

GPA `RegionData.layout`과 같은 규칙: 한 줄이 한 행, 한 글자가 한 칸, 32x20. 강변 마을(백로진 느낌)입니다.

| 글자 | 뜻 | 글자 | 뜻 |
|---|---|---|---|
| `.` `,` | 풀 (`ground_grass_0/1`) | `=` `:` | 길 (`ground_road_0`, 시작·출구·NPC 아래 바닥) · 객잔 문 앞 (`ground_road_1`, `portal` 객잔) |
| `~` | 강 (막힘) | `_` | 강변 모래 |
| `#` | 다리 | `d` `k` `B` | 나루터 판자(걸을 수 있음) · 말뚝 · 배 |
| `T` `P` `w` `g` | 소나무 · 매화 · 버드나무 · 대나무 (2x2) | `y` `R` `F` `"` | 덤불 · 바위 · 꽃 · 갈대 (1칸, 겹쳐 그림) |
| `C` `G` | 청운검문 (4x3) · 문 (2x2) | `A` | 객잔 (3x3, `portal` 객잔) |
| `h` `b` `W` `H` `S` | 기와집 · 초가 · 창고 · 흑사방 (3x3/4x3) · 사당 | `n` `N` | 장터 좌판 (2x2) |
| `o` `l` `i` `j` `c` `f` `\|` `z` | 우물 · 등롱 · 석등 · 항아리 · 상자 · 울타리 · 팻말 | `@` `E` | 시작 · 출구 |
| `1`~`9` `0` `m` `$` `p q r s t u v x` `V D K` | NPC (아래 표) | | |

NPC 글자는 GPA의 `Baekrojin.asset`과 같은 키를 씁니다: `1` 점소이, `2` 흑사방 졸개, `3` 흑사방 연락책, `4` 소육,
`5` 윤백산, `6` 탁웅, `7` 창고지기, `8` 고진악, `9` 은둔 노인(강 위 섬), `m` 장터 상인, `p` 석두, `q` 운학, `r` 연아,
`s` 백설화, `t` 홍련, `u` 묵향, `v` 유소소, `x` 능소. 데모에만 있는 것: `0` 뱃사공 구씨, `$` 비단 장수,
`V` 마을 아낙, `D` 누렁이(개), `K` 닭.

### `Assets/InkPixel/Demo/demo_tiledefs.json`

`Integration/GPA/tiledefs_<region>.json`과 같은 **§7.3 resolved 형식**에 `sprite` 이름을 더한 것입니다.

```json
{
  "region": "InkPixelDemo", "sheetBase": "Assets/InkPixel/Art/", "specialGround": "=",
  "playerSheet": "Characters/hero_1.png",
  "tiles": [ {"key": "T", "sprite": "nature_pine_a", "sheet": "Tiles/nature.png",
              "cellX": 0, "cellY": 0, "sizeX": 2, "sizeY": 2, "solid": true, "ground": ".",
              "overlay": false, "portal": "", "encounterNode": ""} ],
  "npcs":  [ {"key": "1", "name": "점소이", "sheet": "Characters/waiter.png",
              "prop": "", "propSprite": "", "propCellX": 0, "propCellY": 0} ]
}
```

- `sprite`가 있으면 빌더가 사이드카에서 칸을 찾아 `sheet/cellX/cellY/sizeX/sizeY`를 덮어씁니다. `solid`, `ground`,
  `overlay`, `portal`, `encounterNode`는 JSON 값이 그대로 쓰입니다(GPA `TileDef`와 같은 뜻).
- 1칸짜리 소품(우물, 항아리, 덤불 등)은 반드시 `"overlay": true`로 두어야 바닥 위에 겹쳐 그립니다. GPA는 1x1이고
  overlay가 아니면 그 그림 자체를 바닥으로 취급하기 때문입니다.
- 런타임에서 직접 읽으려면 `TileDefs.FromJson(textAsset, path => Resources.Load<Texture2D>(...))`를 쓰면 됩니다.
  `resolveSheet`에는 `sheetBase + sheet`가 넘어옵니다.

## 런타임 스크립트 (`Scripts/Runtime/Demo/`, 네임스페이스 `InkPixel.Demo`)

| 파일 | 역할 |
|---|---|
| `CellSlicer` | GPA `RegionView.Slice`: `rect = (cell.x*16, h - (cell.y+size.y)*16, size.x*16, size.y*16)`, 피벗 (0,0), PPU 16. 캐시. |
| `CharacterSheet` | `Frames(tex)` → `Sprite[4,4]` (열 = 방향 down/up/left/right, 행 = 프레임), `AttackFrames(tex)` → `Sprite[4,3]` (4~7열, 0~2행), `Hurt(tex)` → `Sprite[4]` (4~7열, 3행). |
| `StripSheet` | GPA `Ui.Strip`: 띠를 `count`개로 균등 분할. |
| `TileDefs` | `TileDef`/`NpcDef`(GPA와 같은 필드 + NPC `face`) 목록 ScriptableObject, `Tile(char)`, `Npc(char)`, `FromJson`. |
| `RegionViewer` | GPA `RegionView.Build`와 같은 순서로 바닥·소품·NPC·주인공을 놓고 걷기·달리기·도약·공격·대화·카메라를 처리. 새 Input System(`#if ENABLE_INPUT_SYSTEM`) + 구 `Input` 대체. |
| `GridWalker` | 칸 단위 이동 상태(현재 칸, 목표 칸, 진행도, 방향, 도약). |
| `StripPlayer` | SpriteRenderer에 띠를 fps로 반복 재생. |
| `GalleryController` | 캐릭터 부스와 FX 띠 쪽 넘김, 효과음·음악 키, Tab 전환. |
| `SimpleAudio` | 클립 목록 → `Play(name)` / `Music(name)`, `static Instance`, `TryPlay`. |
| `DemoUi` | 내장 폰트·먹/한지 색·패널 생성 도우미, `FullSprite`(GPA `Ui.Face`). |

## 알아 둘 것

- 라벨과 도움말은 Unity 내장 `LegacyRuntime.ttf`를 씁니다. 한글은 OS의 대체 폰트로 그려지므로 환경에 따라 글꼴이
  다를 수 있습니다(영문 안내를 함께 적어 두었습니다).
- 지도의 강 위 섬은 GPA처럼 걸어서는 못 가고 `F` 도약으로만 건넙니다(강변 x=24 칸에서 아래를 보고 F).
- 갤러리는 지도 오른쪽 멀리(x = 48)에 실제 오브젝트로 놓여 있으며, Tab은 카메라만 옮기고 `RegionViewer`를 끕니다.
- 씬은 빌더가 매번 새로 만듭니다. 손으로 고친 내용은 다음 빌드 때 사라지므로, 바꾸고 싶은 것은
  `demo_layout.txt` / `demo_tiledefs.json` 또는 빌더에 반영하세요.
