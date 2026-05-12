---
name: worldforger-cultures-religions
description: >-
  在 Magic_Creater_World 仓库中编辑、结构化同步或扩展 world.json 的 cultures（文化与宗教）节：
  CultureEntity、kind、relations、归一化别名与第二路 LLM 提示。
  在用户或对话提到文化、宗教、教团、民俗、仪式、信仰、圣地、cultures 实体或「文化·宗教」页时使用。
---

# 文化与宗教（cultures）· 协作要点

## 何时启用

- 用户要增加/修改 **文化、宗教、民俗、教团、仪式、禁忌、圣地、综摄** 等设定。
- 涉及 **`world.json` → `cultures`**、`PATCH`/保存、`sync-panels-from-chat` 的 `scope=cultures`，或前端 **「文化·宗教」** 导航。
- 与 **派系 factions**、**地理 geography**、**历史 history** 交叉引用（用稳定 **id** 串关系）。

## 数据形态（与代码一致）

- **顶层键**：`cultures`（对象）。**不要用**顶层 `culture` 单数作为最终键（归一化会映射为 `cultures` 并记 `normalize_notes`）。
- **小节字段**：`summary`（总览字符串）；`entities`（**数组**，每项一条文化/教团传统）。
- **实体 `CultureEntity`**（见 `worldforger/schemas.py`）：
  - **id**、**name**：必填；id 在 `entities` 内唯一，供 `relations[].target_id` 引用。
  - **kind**：`culture` | `religion` | `syncretic`（文化与传统 / 宗教组织 / 融合传统）。
  - **summary**、**tenets**（观念/教义）、**practices**（仪式、节日、禁忌叙事）。
  - **sacred_sites**：字符串数组（圣地或中心）。
  - **key_figures**：字符串数组。
  - **relations**：`{ target_id, type, notes }[]`；`type` 为自由短字符串（如 影响、冲突、融合），**不是**派系那种 ally/enemy 枚举。
- **归一化**（`worldforger/structure_normalize.py`）：`traditions` → `entities`；单对象 `entities` → 单元素数组；顶层 **`culture` → `cultures`**；关系单对象 → 数组；部分中文字段别名（如 `教义`→`tenets`、`圣地`→列表解析）。

## 结构化同步（第二路）

- 白名单与规则：`worldforger/panel_sync.py` 中 `STRUCTURE_SYSTEM_BASE`（含 `cultures` 字段说明）。
- 载体侧重：`worldforger/creative_modes.py` 的 `STRUCTURE_SYNC_ADDON` 在各模式下补充了 **cultures** 的写作方向。
- 合并与校验：`apply_structure_patch` 用 `CulturesSection` 校验；失败原因在 **`merge_warnings`**；归一化说明在 **`normalize_notes`**。

## 与其它模块的配合

- **派系**：教团可作为 `factions.entities`；民俗共同体放在 `cultures`；两者用 **不同 id 空间**，在叙事里用文字互指即可，避免混用同一 id。
- **地理**：圣地名可出现在 `sacred_sites`；若要与 `geography.regions` 强绑定，在 summary/notes 里写区域 **id**，不要硬编码未文档化的字段。
- **历史**：重大宗教事件放在 `history.events`；仍在流传的教义与仪式放在 `cultures`。

## 不要

- 不要把 **派系关系**（ally/enemy/…）塞进 `cultures.relations` 的 `type` 并指望 schema 约束相同（二者模型不同）。
- 不要省略 **id** 或重复 id 导致关系图无法解析。
- 不要只改前端卡片却忘记提醒用户 **保存**（`PUT /api/worlds/{id}`）若需落盘。

## 代码锚点

- Schema：`worldforger/schemas.py`（`CulturesSection`、`CultureEntity`、`CultureRelation`）。
- 归一化：`worldforger/structure_normalize.py`（`cultures` / `_normalize_cultures_dict`）。
- 同步提示：`worldforger/panel_sync.py`、`worldforger/creative_modes.py`。
- 前端提示：`static/app.js` 中 `CULTURE_MODULE_HINT`、`CULTURE_GENRE_HINTS`、`updateCultureHint`；`static/index.html` 中 `#cultureHintPanel`。

## 与其它 worldforger-* skill

- 先按载体选用 `worldforger-novel` / `worldforger-game` / `worldforger-coc-trpg` / `worldforger-dnd5e`，**本 skill 补充 cultures 节的专门约定**；二者同时启用时不冲突。
