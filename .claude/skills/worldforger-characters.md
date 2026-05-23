---
name: worldforger-characters
description: >-
  在 Magic_Creater_World 仓库中设计、结构化同步或修订 world.json 的 characters（人物卡司）节：
  entities、relations、cast_role、notable_skills，以及工作台「人物生成」对话与左侧「角色」分区看板。
  在用户或对话提到主角团、配角、人物关系网、卡司、characters、人物生成时使用。
---

# 人物卡司（characters）· 协作要点

## 何时启用

- 用户要增加/修改 **主角团、重要配角、人物关系**（非派系组织图，而是 **角色实体之间的关系边**）。
- 用户要落盘 **`notable_skills[]`**（人物叙事或玩法向特长短句，**不是** `power_system.skill_tree` 里的境界节点）。
- 涉及 **`POST …/sync-panels-from-chat`** 且 `scope=characters` 或 JSON 顶层键 **`characters`**。
- 用户使用工作台 **「人物生成」**（`/api/worlds/{id}/character-chat`）并开启 **「引导：人物卡司」**（`chat_guides` 含 **`character_roster`**）。

## 数据形态（与代码一致）

- **顶层键**：`characters`（对象）。
- **字段**：`summary`（卡司总览）、`design_notes`（与派系要人、历史、地理 id 的对齐说明）。
- **`entities[]`**：`dict` 数组（Pydantic 为宽松 dict）。建议字段：
  - **id**、**name**（稳定引用核心）。
  - **cast_role**：`protagonist_core` | `supporting_major` | `supporting_minor` | `antagonist` | `background`。
  - **faction_ids[]**：须对齐已有 **`factions.entities[].id`**。
  - **home_region_id**：若填写，须对齐 **`geography.regions[].id`**。
  - 可选：**aliases[]**、**one_line_hook**、**notes**、**notable_skills[]**。
- **`relations[]`**：**source_id**、**target_id**（均为 **`entities[].id`**）、**relation_type**（如 ally/rival/family/debt/secret）、可选 **visibility**、**notes**。

## 看板与前端

- 左侧 **「角色」** 分组：**主角团**、**重要配角**、**人物关系网络**、**卡司数据** 为同级入口，各自对应独立页面（`#view-charProtagonists` 等）。**主角团 / 重要配角** 页在开启卡片上方 **编辑模式** 后，可在卡片表单内改字段并写回 `characters.entities`（与 **卡司数据** JSON 双向一致）；**卡司数据** 页编辑完整 `entities` / `relations` JSON；`summary` / `design_notes` 仍存于 `world.json`，保存时与 JSON 合并，本界面不提供该二字段的表单。
- **人物生成**（`#view-charChat`）：独立消息线程，调用 **`character-chat`**；本页可勾选 **附带 world.md**、**对话后同步**（与「世界观构建」页的同类选项相互独立）。**创作模式**、**仅同步当前页** 仍共用世界观页控件。

## 结构化同步（第二路）

- 规则与白名单：`worldforger/panel_sync.py`（`characters` 小节说明）。
- 归一化：`worldforger/structure_normalize.py`（`_normalize_characters_dict`、中文「人物」键映射等）。
- 引用校验：`worldforger/reference_linter.py`（`faction_ids`、`home_region_id`、`relations` 端点）。
- 导出：`worldforger/markdown_export.py`（人物与卡司章节）。

## 不要

- 不要把 **境界技能树节点**写进 **`characters.entities[].notable_skills`** 又声称是 power_system；若需规则向能力，应落在 **power_system** 或 **attribute_system** 并在叙事上分界说明。
- 不要编造与 **`factions.entities[].id`**、**`geography.regions[].id`** 冲突的引用；新增角色请用新的唯一 **id**（短 slug，与前端 `uid` 风格一致即可）。

## 与其它 skill

- 载体侧重仍用 **`worldforger-novel` / `game` / `coc-trpg` / `dnd5e`**；本 skill 专门约束 **卡司实体与关系边** 的形态与同步边界。
- **派系权力与组织关系**见 **`worldforger-factions`**（`factions.relations` 是派系之间，不是人物之间）。
