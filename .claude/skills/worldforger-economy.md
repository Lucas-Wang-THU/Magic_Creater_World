---
name: worldforger-economy
description: >-
  在 Magic_Creater_World 仓库中设计、结构化同步或修订 world.json 的 economy（经济与流通）节：
  货币、市场、商路、贸易品及劳动力/税收/波动说明；与工作台「世界观构建」对话、引导勾选与「经济」页表单/JSON 一致。
  在用户或对话提到通货、商会、关税、商路、黑市、物价危机、economy 时使用。
---

# 经济与流通（economy）· 协作要点

## 何时启用

- 用户要增加/修改 **货币体系、区域市场、商路、战略品/违禁品叙事**，或要把现金流与 **派系 / 地理 / 物品档位** 对齐。
- 涉及 **`POST …/sync-panels-from-chat`** 且 JSON 顶层键 **`economy`**，或 `updated_sections` 含 **`economy`**。
- 用户使用工作台 **「世界观构建」**：勾选 **「引导：经济系统」**（请求体 `chat_guides` 含 **`economy`**），或点击芯片 **「写经济」**（会勾选该引导并填入长提示）。

## 数据形态（与 `worldforger/schemas.py` 一致）

- **顶层键**：`economy`（对象）。
- **字段**：`summary`、`design_notes`；`labor_notes`、`taxation_notes`、`volatility_notes`（字符串说明）。
- **`currencies[]`**：`id`、`name`；可选 `symbol`、`issuer_faction_id`（须 **`factions.entities[].id`**）、`exchange_notes`。
- **`markets[]`**：`id`、`name`；可选 `summary`、`linked_region_ids[]`（**`geography.regions[].id`**）、`dominant_faction_ids[]`、`notes`。
- **`trade_routes[]`**：`id`、`name`、`from_region_id`、`to_region_id`（均为区域 **id**）；可选 `summary`、`goods_notes`、`controlling_faction_ids[]`、`notes`。
- **`trade_goods[]`**：`id`、`name`；可选 `category`（如 strategic|luxury|common|contraband）、`summary`、`notes`。

## 看板与前端

- 左侧 **「经济」** 视图：表单与 JSON 与 `world.json` 的 `economy` 双向一致；保存走与其它模块相同的落盘路径。
- **推荐工作流**：世界观页开启 **「对话后同步」** → 勾选 **引导：经济系统** 或使用 **「写经济」** 芯片 → 发送对话 → 同步成功后 **自动落盘** 并 **切换到「经济」页** 滚动到卡片区，便于立刻核对表单与机读结果。
- 系统片段来源：`worldforger/creative_modes.py` 中 **`CHAT_GUIDE_FRAGMENTS["economy"]`**（与后端白名单 **`ALLOWED_CHAT_GUIDES`** 一致）。

## 结构化同步（第二路）

- 规则与白名单：`worldforger/panel_sync.py`（`economy` 小节说明）。
- 归一化：`worldforger/structure_normalize.py`（`_normalize_economy_dict`）。
- 引用校验：`worldforger/reference_linter.py`（货币发行派系、市场区域、商路端点、控制派系等）。
- 导出：`worldforger/markdown_export.py`（经济相关章节）。

## 不要

- 不要编造不存在的 **`geography.regions[].id`** 或 **`factions.entities[].id`**；新增条目请用新的稳定短 **id**。
- 不要把 **境界技能树** 或 **人物卡司 notable_skills** 误写进经济条目；贸易叙事与规则向能力应各归其模块。

## 与其它 skill

- **派系 / 地理 / 物品档位** 仍分别见 **`worldforger-factions`** 与物品品质相关约定；本 skill 专门约束 **流通结构与引用 id** 的形态与同步边界。
- 载体语气仍可用 **`worldforger-novel` / `worldforger-game` / `coc-trpg` / `dnd5e`** 等 skill 搭配。
