# InkPixel 아이템 아이콘 매핑 (강호유랑기 GPA)

`Assets/InkPixel/Art/Icons/`의 40×40 PNG를 GPA의 `Assets/_Project/Art/Resources/Icons/`에 그대로
복사하면 된다 (`GPA/InkPixel/1. InkPixel 에셋 복사...` 메뉴가 해 준다). GPA의 `Ui.ItemIcon`은
`Resources.Load<Texture2D>("Icons/" + 이름)`으로 읽어 54px 등급 프레임 안에 40px로 보여 주므로
파일 이름이 곧 아이콘 키다. 모든 파일은 투명 배경, 1px 먹 외곽선, 32색 팔레트, Point 필터용.

## 1. 지금 GPA 코드가 고르는 아이콘 (종류별, 교체만 하면 됨)

`Ui.IconOf`(`Scripts/UI/Ui.cs`)는 아이템 **종류**로 아이콘을 고른다. 아래 9개는 GPA가 이미 쓰는
이름 그대로이므로 파일만 덮어쓰면 즉시 바뀐다. 각 계열에서 가장 평범한 그림이다.

| GPA 규칙 | 파일 | 그림 |
|---|---|---|
| 무기(검) `WeaponType.Sword` | `jian.png` | 회색 날 검, 주묵 술 |
| 무기(단검) `WeaponType.Dagger` | `dagger.png` | 짧은 단도 |
| 옷 `ItemKind.Clothes` | `robe.png` | 한지색 도포, 가죽 띠 |
| 장갑 `ItemKind.Gloves` | `glove.png` | 가죽 장갑 한 짝 |
| 소모품·영약 `Consumable`/`Elixir` | `pill.png` | 한지 위의 검은 환 |
| 이름 예외 지혈 부적·해독 향낭 | `talisman.png` | 노란 부적, 주묵 부호 |
| 이름 예외 행운 엽전 | `coin.png` | 엽전 |
| (예비) 비급 `ItemKind.Manual` | `manual.png` | 남색 선장본 |
| (예비) 독 | `poison.png` | 자줏빛 독병 |

`manual`·`poison`은 현재 GPA 코드에서 한자(書·物)로 대체되는 종류를 위해 준비해 둔 것이다.

## 2. 아이템별 전용 아이콘 (`docs/12_아이템.md` + `Data/Resources/Items/`)

"기본"은 현재 GPA 코드가 고르는 아이콘, "전용"은 InkPixel이 따로 그린 아이콘이다. 전용 아이콘을 쓰려면
§4의 코드처럼 `IconOf`에 이름 분기를 추가한다.

### 장비

| 아이템 | 칸 | 기본 | 전용 아이콘 | 비고 |
|---|---|---|---|---|
| 녹슨 철검 | 무기 | `jian` | `jian_rusty` | 녹 얼룩, 이 빠진 날 |
| 철검 | 무기 | `jian` | `jian_iron` | 어두운 무쇠 날 |
| 정강검 | 무기 | `jian` | `jian_steel` | 광택 날, 금 코등이 |
| 청운제식검 | 무기 | `jian` | `jian_cheongun` | 옥빛 자루, 한지 술 |
| 청운보검 | 무기 | `jian` | `jian_cheongun` | 데이터에만 있는 검. 제식검과 같은 그림 |
| 단도 | 무기 | `dagger` | `dagger` | |
| 흑사단검 | 무기 | `dagger` | `dagger_heuksa` | 검푸른 날, 주묵 끈 |
| 베옷 | 옷 | `robe` | `robe_hemp` | 거친 베 질감 |
| 가죽조끼 | 옷 | `robe` | `vest_leather` | |
| 청운도복 | 옷 | `robe` | `robe_cheongun` | 옥색, 한지 단 |
| 흑사흑의 | 옷 | `robe` | `robe_heuksa` | 남색, 주묵 띠 |
| 연갑 | 옷 | `robe` | `armor_soft` | 누빔 조끼, 어깨 판 |
| 짚신 | 신발 | (履) | `straw_sandals` | |
| 가죽장화 | 신발 | (履) | `leather_boots` | |
| 운리화 | 신발 | (履) | `cloud_shoes` | 흰 신, 옥빛 구름 무늬 |
| 무명 권대 | 장갑 | `glove` | `cloth_wraps` | 무명 감은 손 |
| 가죽 장갑 | 장갑 | `glove` | `leather_gloves` | 두 짝 |
| 행운 엽전 | 장신구 | `coin` | `lucky_coin` | 주묵 끈 달린 엽전 |
| 옥패 | 장신구 | (珮) | `jade_pendant` | 옥 고리, 주묵 끈 |
| 낡은 옥패 | 장신구 | (珮) | `jade_pendant_old` | 금 간 회색 옥 |
| 청운옥패 | 장신구 | (珮) | `jade_pendant_cheongun` | 구름 새긴 옥패, 금 구슬 |
| 해독 향낭 | 장신구 | `talisman` | `sachet` | 이끼색 주머니, 금 끈 |
| 지혈 부적 | 장신구 | `talisman` | `talisman` | |
| 흑사독낭 | 장신구 | (珮) | `poison_pouch` | 남색 주머니, 뱀 표식 |
| 흑사호부 | 장신구 | (珮) | `talisman` | 데이터에만 있는 장신구. 전용 그림 없음, 부적으로 대체 |

### 소모품

| 아이템 | 기본 | 전용 아이콘 | 비고 |
|---|---|---|---|
| 금창약 | `pill` | `salve` | 작은 약단지 |
| 회기단 | `pill` | `pill_qi` | 흰 환 |
| 지혈산 | `pill` | `powder` | 약포지, 쏟아진 가루 |
| 해독단 | `pill` | `pill_antidote` | 옥빛 환 |
| 청심환 | `pill` | `pill_clear` | 푸른 환 |
| 활력환 | `pill` | `pill_vigor` | 주홍 환 |

### 영약 (빛나는 환, 밀랍 껍질 위)

| 아이템 | 기본 | 전용 아이콘 | 비고 |
|---|---|---|---|
| 천력환 | `pill` | `elixir_red` | 외공 |
| 자하단 | `pill` | `elixir_purple` | 내공 |
| 비연단 | `pill` | `elixir_blue` | 경공 |
| 호골단 | `pill` | `elixir_orange` | 근골 |
| 청명단 | `pill` | `elixir_green` | 오성 |
| 소환단 | `pill` | `elixir_white` | 내공 축적 |
| 대환단 | `pill` | `elixir_gold` | 경지 돌파 |

### 비급

| 아이템 | 기본 | 전용 아이콘 | 비고 |
|---|---|---|---|
| 오호단문도 비급 | (書) | `manual_dao` | 먹색 표지, 도 표식 |
| 철사장 비급 | (書) | `manual_palm` | 갈색 표지, 손바닥 표식 |
| 맹호권 비급 | (書) | `manual_fist` | 주묵 표지, 주먹 표식 |
| 선풍각 비급 | (書) | `manual_kick` | 이끼색 표지, 발 표식 |
| 심법 비급 (청심결 등, 미구현) | (書) | `scroll_mind` | 두루마리, 옥빛 끈 |
| 그 밖의 비급 | (書) | `manual` | 남색 선장본 |

### 그 밖의 무기·물건 (퀘스트·상점·연출용 예비)

| 이름 | 파일 | 이름 | 파일 |
|---|---|---|---|
| 도 | `dao` | 부엌칼 (유소소) | `cleaver` |
| 투석 새총 (연아) | `sling` | 봉 (승려) | `staff` |
| 권대 (맨손 무기) | `fist_wraps` | 엽전 묶음 | `coin_stack` |
| 장부 (고진악·탁웅·윤백산 퀘스트) | `ledger` | 서신 | `letter` |
| 지도 | `map` | 열쇠 (창고) | `key` |
| 등롱 | `lantern` | 국밥 | `rice_soup` |
| 술병 | `wine_jug` | 차 | `tea` |
| 약초 | `herb` | 버섯 | `mushroom` |
| 죽순 | `bamboo_shoot` | 생선 | `fish` |
| 고기 | `meat` | 밧줄 | `rope` |
| 부싯돌 | `flint` | 호리병 | `gourd` |
| 붕대 | `bandage` | 침 (백설화) | `needle` |
| 붓 (묵향) | `ink_brush` | 돌 | `stone` |
| 접부채 (백여린) | `fan` | 독병 | `poison` |
| 비단 (비단 장수) | `silk` | 바구니 | `basket` |

## 3. HUD 미니 아이콘 (`Icons/Mini/`, 16×16)

| 파일 | 용도 |
|---|---|
| `coin.png` | HUD 엽전 금액 옆 |
| `hp.png` | 체력 (주묵 하트) |
| `qi.png` | 내력 (옥빛 소용돌이) |
| `fatigue.png` | 피로 (달과 zz) |
| `hunger.png` | 허기 (산중수련, 밥그릇) |
| `warmth.png` | 온기 (산중수련, 불꽃) |
| `qi_orb.png` | 내공 축적 / 경지 (옥 구슬) |

## 4. `Ui.IconOf`를 아이템별 아이콘으로 넓히는 예

GPA는 아이템 데이터에 `icon` 필드를 두지 않으므로 이름으로 분기한다. 전용 아이콘이 없는 이름은 기존
종류 규칙으로 떨어진다. 파일만 복사해 두면 아래처럼 바꿀 수 있다.

```csharp
static readonly Dictionary<string, string> IconByName = new()
{
    ["녹슨 철검"] = "jian_rusty", ["철검"] = "jian_iron", ["정강검"] = "jian_steel",
    ["청운제식검"] = "jian_cheongun", ["청운보검"] = "jian_cheongun", ["흑사단검"] = "dagger_heuksa",
    ["베옷"] = "robe_hemp", ["가죽조끼"] = "vest_leather", ["청운도복"] = "robe_cheongun",
    ["흑사흑의"] = "robe_heuksa", ["연갑"] = "armor_soft",
    ["짚신"] = "straw_sandals", ["가죽장화"] = "leather_boots", ["운리화"] = "cloud_shoes",
    ["무명 권대"] = "cloth_wraps", ["가죽 장갑"] = "leather_gloves",
    ["행운 엽전"] = "lucky_coin", ["옥패"] = "jade_pendant", ["낡은 옥패"] = "jade_pendant_old",
    ["청운옥패"] = "jade_pendant_cheongun", ["해독 향낭"] = "sachet", ["지혈 부적"] = "talisman",
    ["흑사독낭"] = "poison_pouch", ["흑사호부"] = "talisman",
    ["금창약"] = "salve", ["회기단"] = "pill_qi", ["지혈산"] = "powder", ["해독단"] = "pill_antidote",
    ["청심환"] = "pill_clear", ["활력환"] = "pill_vigor",
    ["천력환"] = "elixir_red", ["자하단"] = "elixir_purple", ["비연단"] = "elixir_blue",
    ["호골단"] = "elixir_orange", ["청명단"] = "elixir_green", ["소환단"] = "elixir_white",
    ["대환단"] = "elixir_gold",
    ["오호단문도 비급"] = "manual_dao", ["철사장 비급"] = "manual_palm",
    ["맹호권 비급"] = "manual_fist", ["선풍각 비급"] = "manual_kick",
};

static string IconOf(ItemData i) => IconByName.TryGetValue(i.name, out var icon) ? icon : i.kind switch
{
    ItemKind.Weapon => i.weapon == WeaponType.Dagger ? "dagger" : "jian",
    ItemKind.Clothes => "robe",
    ItemKind.Gloves => "glove",
    ItemKind.Consumable or ItemKind.Elixir => "pill",
    ItemKind.Manual => "manual",
    _ => null,
};
```

## 5. 검수용 그림

- `Docs/previews/icons_sheet_preview.png` — 77개 전부, 4배, 이름표.
- `Docs/previews/icons_mini_preview.png` — 미니 7개, 4배.
- `Assets/InkPixel/Art/Icons/icons_sheet.png` + `icons_sheet.sprites.json` — 한 장에 모은 접촉 시트
  (스프라이트 이름 `icons_<파일이름>`), 자르기 쓰는 사람용.
