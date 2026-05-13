---
name: worldforger-factions
description: >-
  在 Magic_Creater_World 仓库中设计、结构化同步或修订 world.json 的 factions（派系）节：
  entities、relations、key_figures，以及「生成派系重要人物」子流程。
  在用户或对话提到派系、组织、阵营、教团政治、key_figures、派系要人或 factions 实体时使用。
---

# 派系（factions）· 协作要点

## 何时启用

- 用户要增加/修改 **派系、组织、阵营、地盘、派系关系**。
- 用户要 **列出或扩写派系重要人物**（对应 `entities[].key_figures`）。
- 涉及 **`POST …/sync-panels-from-chat`** 且 `scope=factions` 或 JSON 顶层键 **`factions`**。

## 数据形态（与代码一致）

- **顶层键**：`factions`（对象）。
- **字段**：`summary`（总览）；`entities`（**数组**）。
- **实体 `FactionEntity`**（`worldforger/schemas.py`）：
  - **id**、**name**：必填；`id` 用于 `relations[].target_id` 互指。
  - **goals**、**territory**：字符串。
  - **key_figures**：**字符串数组**，每项通常一行：**「姓名」或「姓名 · 职务/立场」**（schema 无单独子对象，可把钩子写进该字符串）。
  - **relations**：`{ target_id, type: ally|enemy|neutral|complex, notes }[]`。

## 子功能：生成派系重要人物（`key_figures`）

在已存在或即将写入的 **`factions.entities`** 上，为**每个相关派系**补充可扮演、可叙事的重要人物名单。

### 产出约定

1. **与派系 id 对齐**：先确定（或让用户确认）每个派系的 **`id` 与 `name`**，再在该实体下写 `key_figures`，避免张冠李戴。
2. **条数**：默认每派系 **3～7** 人；用户指定数量时从其约定。
3. **每条字符串建议形态**（任选其一，保持简短）：
   - `「灰鸦」阿兰`（仅称呼）
   - `阿兰 · 外务执事`（姓名 + 职务）
   - `主教赫连（表面慈善，暗中清洗异见者）`（姓名 + 一句叙事钩子，控制在约 40 字内）
4. **自然语言阶段**：可用 Markdown 小标题分派系列出；**结构化同步**阶段必须能落到 **`factions.entities[].key_figures`** 的 **字符串数组**（第二路会合并进现有实体，勿用空数组占位冲掉旧名单，除非用户明确要求清空）。
5. **与 `cultures` 区分**：民俗/教团意识形态在 **`cultures`**；**组织权力与政治站队**在 **`factions`**。同一人物若两边都出现，应用**相同称呼**并在叙事中说明身份重叠。

### 不要

- 不要把 `key_figures` 写成对象数组（当前 schema 不支持）；人物详情可写在对话或 `goals`/`notes`，名单列在 `key_figures` 字符串中。
- 不要编造与 **`world.json` 已有 id** 冲突的新派系 id；新增派系时生成新的唯一 `id`（如 `f_` 前缀 + 短随机，与前端 `uid` 风格一致即可）。

## 结构化同步（第二路）

- 规则与白名单：`worldforger/panel_sync.py` 中 `STRUCTURE_SYSTEM_BASE`（`factions` 小节）。
- 合并与校验：`apply_structure_patch` → `FactionsSection`；失败信息在 **`merge_warnings`**。

## 代码锚点

- Schema：`worldforger/schemas.py`（`FactionEntity`、`FactionsSection`）。
- 前端卡片与对话快照：`static/app.js`（`renderFactionCards`、`refreshFactionChatViz`）、`static/index.html`（`#factionChatViz`）。
- 对话快捷词条：「派系要人」chip 文案与「写派系」并列。

## 与其它 skill

- 载体侧重仍用 **`worldforger-novel` / `game` / `coc-trpg` / `dnd5e`**；本 skill 专门约束 **派系与要人名单** 的形态与同步边界。
- 文化/教团条目见 **`worldforger-cultures-religions`**。
