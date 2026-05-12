---
name: worldforger-novel
description: >-
  在 Magic_Creater_World 仓库中以「小说」载体打磨世界观：叙事弧线、人物、伏笔与场景化地理。
  在用户选择小说模式、写长篇设定、或 meta.creative_mode 为 novel 时使用。
---

# 小说载体 · 世界观协作

## 何时启用

- 用户在 Web UI 选择「小说」，或 `world.json` 的 `meta.creative_mode` 为 `novel`。
- 用户要人物弧线、分幕大纲、伏笔与母题，而非关卡表或调查表。

## 行为要点

- **对话与大纲**：优先动机、秘密、冲突升级、象征与回收；地理/派系写可被章节调用的细节。
- **结构化同步**（`worldforger/creative_modes.py`）：落盘时偏向 `history.events` 后果、`factions` 人物线索、`cultures` 民俗与仪式张力、`geography.regions` 氛围与场景。
- **不要**：把一切都写成数值战力或 encounter 表；除非用户明确要求。

## 代码锚点

- 模式文案：`worldforger/creative_modes.py`（`CHAT_MODE_SYSTEM["novel"]` 等）。
- API：`app/main.py` 将 `creative_mode` 传给对话、同步与大纲。
