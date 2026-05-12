---
name: worldforger-dnd5e
description: >-
  在 Magic_Creater_World 仓库中以 D&D 类跑团载体构建世界：冒险钩子、遭遇地形、阵营与可裁定规则。
  在用户选择 DnD、谈 CR/等级感/据点、或 meta.creative_mode 为 dnd 时使用。
---

# DnD 跑团载体 · 世界观协作

## 何时启用

- UI 选择「DnD 跑团」，或 `meta.creative_mode` 为 `dnd`。
- 用户要任务发布者、阵营、旅行遭遇、稀有度与调谐式物品规则。

## 行为要点

- **对话**：威胁感与地形战术、派系据点与钩子；力量体系在 `limitations` 中写清对 PC 的硬边界。
- **结构化同步**：地理写旅行危险与地标遭遇；派系写任务与阵营；`cultures` 写神殿网络、节日与意识形态钩子；物品用 `binding_rules` 表达类 attunement 规则。
- **不要**：默认强加官方 CR 表数字；用「威胁层级 / 建议区间」等可由主持本地换算的表述即可。

## 代码锚点

- `worldforger/creative_modes.py` 中 `dnd` 条目。
