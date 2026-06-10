# 角色涌现式叙事系统 · 实施状态 v12

> **核心愿景**：让每个重要角色拥有独立的 Agent 模拟层，叙事从角色的自主互动中涌现。
>
> **设计约束**：单 POV 优先 / 粗纲为骨架 / 细纲为参考 / 前后章逻辑通顺

---

## 实施进度总览

```
Phase 0: 角色 Agent 内核 + 单 POV 管线集成    [████████████] 100%  已完成
Phase 1: 多角色完整互动 + 细纲协调             [████████████] 100%  已完成
Phase 2: 多场景编织 + 离线角色影子影响          [████████████] 100%  已完成
Phase 3: 长期运行 + 质量控制                    [████████████] 100%  已完成
附录 B: 结构同步改进                          [████████████] 100%  已完成
```

---

## 文件清单（21 个模块，6 个测试文件，~110 个测试）

```
worldforger/agents/                   # 全部 17 个模块
├── __init__.py                       # 导出 19 个符号
├── types.py                          # 6 个数据模型
├── character_agent.py                # P0: 角色 LLM 决策引擎
├── character_prompts.py              # P0: 角色 prompt 模板 + 战斗能力注入
├── scene_simulator.py                # P0/P1: V2 多角色互动 + 意图泄露 + 情绪传染
├── pov_filter.py                     # P0: 单 POV 过滤器
├── state_injector.py                 # P0: 状态→prompt 注入
├── outline_constraint.py             # P0: 粗纲约束解析
├── beat_reference.py                 # P0: 细纲软参考
├── continuity_checker.py             # P0: 跨章连续性校验
├── agent_store.py                    # P0: Agent 持久化
├── dialog_quality.py                 # P1: 对话质量评分（冲突/情感/信息）
├── beat_coordinator.py               # P1: 节拍偏离量化 + 自动协调
├── world_clock.py                    # P2: 时间推进 + 外部事件注入
├── shadow_influence.py               # P2: 离线角色→环境线索 + 伏笔关联
├── scene_assembler.py                # P2: 场景检测 + 过渡 + 节奏
├── quality_evaluator.py              # P3: 5维叙事质量评分 (A-F)
├── autonomy.py                       # P3: 角色自主等级管理 (L1-L3)
└── chapter_runner.py                 # P3: 多章节半自主运行器 + 质量基准

worldforger/
├── punctuation_normalize.py          # 中文标点规范化
└── sync/
    ├── panel_sync.py                 # C1/C3: 分片同步 + 中文标点归一化
    └── panel_merge.py                # C2: tier_name 语义匹配 + 技能节点 reconcile

tests/
├── test_agents.py                    # 25 tests (Phase 0)
├── test_agents_p1p2.py               # 30 tests (Phase 1/2)
├── test_agents_p3.py                 # 36 tests (Phase 3)
├── test_agent_e2e.py                 # 14 tests (E2E API)
└── test_sync_repair.py               # 28 tests (C1/C2/C3 sync)
```

---

## 新增功能（v11→v12）

### 角色详情面板
| 功能 | 位置 |
|------|------|
| 角色详情覆盖层 | 点击角色卡片 → 毛玻璃遮罩 + 圆角面板 |
| 力量境界选择器 | 从 `power_system.tiers[]` 自动生成下拉 |
| 职业选择器 | 从 `profession_system.by_tier[]` 自动生成下拉 |
| 年龄编辑 | 文本输入 |
| 物品清单 CRUD | 名称/描述/用法/数量/来源章/状态，4 种状态追踪 |
| 属性滑块 | 从 `attribute_system.stats[]` 生成滑块 0-100，含参考值标记 |
| 关闭方式 | 点击遮罩 / Esc 键 / 圆形关闭按钮 |
| 角色卡片图标 | 根据 `power_tier` 自动匹配 Material Symbol 图标 |
| 境界/职业标签 | 卡片上显示紫色境界标签 + 绿色职业标签 |
| ID 详情按钮 | 每个角色卡片 ID 旁 `info` 按钮直达详情 |

### 战斗能力注入
| 功能 | 位置 |
|------|------|
| 技能清单 | `_inject_character_capabilities()` — 从 `power_tier` 读取技能树注入 Agent prompt |
| 物品清单 | 从 `character.inventory` 读取，含用法描述 |
| 属性值 | 从 `character.attributes` 读取，含参考值对比 |
| 发动规则 | 从 `power_tier.activation_rules` + `skill_node.activation_rules` 读取 |
| 对抗规则 | Agent prompt 新增 5 条战斗/冲突能力使用规则 |

### 结构同步增强
| 改进项 | 说明 |
|--------|------|
| C1 分片协议 | `_parse_chunked()` — `@@SECTION@@` 标记逐片解析，独立容错 |
| C2 tier_name 匹配 | `_merge_array_by_name_or_append` 同时按 `name` + `tier_name` 匹配 |
| C2 技能节点 reconciler | `reconcile_power_system_skill_nodes()` — 自动移动节点避免重复 |
| C3 中文标点修复 | `_normalize_json_punctuation()` — 6 种中文标点→ASCII |
| C4 分批进度追踪 | checkbox + 进度条 + localStorage 持久化 |

### 发动规则
| 功能 | 位置 |
|------|------|
| `PowerTier.activation_rules` | 境界级发动条件 |
| `SkillNode.activation_rules` | 技能节点级发动条件 |
| UI 编辑器 | 境界编辑卡片中 textarea，含说明占位符 |
| Agent 注入 | 角色 Agent 决策前强制检查 |

### UI 修复
| 修复 | 说明 |
|------|------|
| 派系网络 height:0 | 显式 `height:420px` + `redraw()` + `fit()` |
| 关系颜色哈希 | 中文关系类型（航道/邻接等）自动生成 HSL 颜色 |
| 缺失节点自动补充 | target_id 不在实体列表中时灰显"未建档"节点 |
| 标点规范化 | 全角/半角统一 + 引号配对 + 省略号/破折号修复 |
| 朴素文风约束 | manuscript/polisher prompt 各新增文风规则 |

---

## 测试覆盖

```
tests/test_agents.py          25 tests   Phase 0
tests/test_agents_p1p2.py     30 tests   Phase 1/2
tests/test_agents_p3.py       36 tests   Phase 3
tests/test_agent_e2e.py       14 tests   E2E API
tests/test_sync_repair.py     28 tests   C1/C2/C3 sync
tests/test_*.py (existing)   447 tests   已有测试
─────────────────────────────────────
Total:                        580 tests  (excluding 3 e2e)
```

---

## 集成架构（完整）

```
generate_manuscript()
  │
  ├── enable_character_agents == true?
  │     │
  │     ├── YES → _generate_manuscript_with_agents()
  │     │           │
  │     │           ├── OutlineConstraint.parse()
  │     │           ├── AgentStore.load_all_states()
  │     │           ├── BeatReference.parse()
  │     │           ├── ContinuityChecker.pre_check()
  │     │           ├── _inject_character_capabilities()    # 技能/物品/属性/发动规则
  │     │           ├── WorldClock.advance_chapter()
  │     │           ├── SceneSimulator.run()                # 意图泄露 + 情绪传染
  │     │           ├── POVFilter.filter()
  │     │           ├── ShadowInfluence + SceneAssembler
  │     │           ├── BeatCoordinator.classify()
  │     │           ├── StateInjector.for_writer_agent()
  │     │           ├── chat_completion()                   # 作家 Agent
  │     │           ├── QualityEvaluator.evaluate()
  │     │           ├── ContinuityChecker.post_update()
  │     │           └── AgentStore.save_state()
  │     │
  │     └── 失败 → 自动回退正常路径（终端 + 前端 toast）
  │
  └── NO → 正常路径
           ├── Scene Chunking
           ├── 截断检测 + 续写 + 收束
           ├── 标点规范化 (punctuation_normalize)
           └── 后处理 hooks
```

---

> **最后更新**：2026-06-09
> **版本**：v12 — Phase 0/1/2/3 + 附录 B 全部 100% + 580 测试通过
