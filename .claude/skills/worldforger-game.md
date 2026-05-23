---
name: worldforger-game
description: >-
  在 Magic_Creater_World 仓库中以「游戏」载体设计世界：成长曲线、任务链、系统边界与策划可读规格。
  在用户选择游戏模式、讨论职业/掉落/关卡、或 meta.creative_mode 为 game 时使用。
---

# 游戏载体 · 世界观协作

## 何时启用

- UI 选择「游戏」，或 `meta.creative_mode` 为 `game`。
- 用户谈平衡、进度、支线、区域解锁、掉落与档位规则。

## 行为要点

- **对话**：层级清晰、边界规则、反作弊/资源循环；地理与历史写成可映射任务或版本的模块。
- **结构化同步**：强化 `power_system.tiers` 与 `item_quality_system.grades` 的 `limitations` / `binding_rules`；地理与派系挂钩奖励链或区域控制；`cultures` 可写节日、声望与文化标签等可策划钩子。
- **不要**：默认写成纯文学意识流；保留可执行、可拆任务的表述粒度。

## 代码锚点

- `worldforger/creative_modes.py` 中 `game` 条目与 `STRUCTURE_SYNC_ADDON["game"]`。
