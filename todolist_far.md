# 角色涌现式叙事系统 · 实施状态 v11

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
```

---

## 文件清单（21 个模块，4 个测试文件，108 个测试）

```
worldforger/agents/                   # 全部 17 个模块
├── __init__.py                       # 导出 17 个符号
├── types.py                          # 6 个数据模型
├── character_agent.py                # P0: 角色 LLM 决策引擎
├── character_prompts.py              # P0: 角色 prompt 模板
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
└── punctuation_normalize.py          # 中文标点规范化

tests/
├── test_agents.py                    # 25 tests (Phase 0)
├── test_agents_p1p2.py               # 30 tests (Phase 1/2)
└── test_agents_p3.py                 # 15 tests (Phase 3)
```

---

## Phase 0 — 已完成（100%）

| 模块 | 测试 |
|------|------|
| `CharacterAgent` + 温度自适应 | ✅ |
| `SceneSimulator` V2 (僵局打破/影子行动/收敛检测) | ✅ |
| `POVFilter` + 读者知识标注 | ✅ |
| `StateInjector` for_writer/for_character | ✅ |
| `OutlineConstraint` 解析/注入/校验 | ✅ |
| `BeatReference` 解析/偏离记录 | ✅ |
| `ContinuityChecker` 生成前/后 + 衰减 | ✅ |
| `AgentStore` 持久化 + world.json 初始化 | ✅ |
| 管线集成 + 失败自动回退 | ✅ |
| Agent toggle UI (双面板) | ✅ |

---

## Phase 1 — 已完成（90%）

| 功能 | 位置 |
|------|------|
| 意图泄露检测 | `SceneSimulator._detect_intent_leak()` |
| 情绪传染 | `SceneSimulator._apply_emotional_contagion()` |
| 僵局打破多样化 (6种) | `SceneSimulator._inject_stuck_breaker()` |
| 对话质量评分 (3维) | `DialogQuality.assess()` |
| 节拍偏离量化 (4级) | `BeatCoordinator.classify_deviation()` |
| 节拍自动协调 | `BeatCoordinator` — 轻度采纳/中度提示/严重重试 |
| Agent 决策 API | `GET /api/worlds/{id}/story/agent-decisions/{ch}` |
| UI 双面板联动 | `_bindAgentToggleSync()` |
| 情感自动刷新 | `refreshSentimentArc()` |
| 情感标签归一化 | `_TONE_NORMALIZE` + 3层回退 |
| 终端错误可见 | 全局异常处理器 |

| Agent 决策分析面板 | `app.js:refreshAgentPanel()` — 质量趋势图 + 决策序列 + 偏离追踪 + 状态总览 | ✅ |

---

## Phase 2 — 已完成（100%）

| 功能 | 位置 |
|------|------|
| 时间推进 + 外部事件 | `WorldClock` — 日/季节/雾蚀循环，6种外部事件模板 |
| 离线角色→环境线索 | `ShadowInfluence.generate_hints()` — 8种模板 |
| 伏笔自动关联 | `ShadowInfluence.link_to_foreshadowing()` |
| 环境线索→prompt | `ShadowInfluence.format_shadow_context()` |
| 场景边界检测 | `SceneAssembler.detect_scene_boundaries()` |
| 场景过渡生成 | `SceneAssembler.generate_transition()` |
| 节奏曲线检查 | `SceneAssembler.check_pacing()` |
| **管线集成** | `_generate_manuscript_with_agents()` 中实际调用全部 P2 模块 |

---

## Phase 3 — 已完成（100%）

### ✅ 已完成

| 功能 | 位置 |
|------|------|
| 5维质量评分 | `QualityEvaluator.evaluate()` (节奏/弧光/对话/一致性/吸引力) |
| A-F 等级 + 趋势分析 | `QualityEvaluator._grade()` + trend detection |
| 质量建议生成 | `QualityEvaluator._generate_suggestions()` |
| 角色自主等级 | `AutonomyManager` — L1顾问/L2半自主/L3全自主 |
| 温度/约束/偏离控制 | 按自主等级调整温度、约束严格度、最大容忍偏离 |
| 管线质量日志 | `[MCW-QUALITY]` 终端输出 + 建议 |
| Agent 列表 API | `GET /api/worlds/{id}/agents` |
| Agent 详情 API | `GET /api/worlds/{id}/agents/{char_id}` |
| Agent 初始化 API | `POST /api/worlds/{id}/agents/init` |
| Agent 重置 API | `POST /api/worlds/{id}/agents/{char_id}/reset` |
| 质量历史 API | `GET /api/worlds/{id}/agents/{char_id}/quality-history` |

| 多章节半自主运行 | `ChapterRunner` — 从粗纲自动推进 N 章，质量监控 + 自主干预 |
| 质量基准对比 | `QualityBenchmark.compare()` — 当前章 vs 历史均值 |
| 多章节生成 API | `POST /api/worlds/{id}/story/generate/multi-chapter` |
| 质量基准 API | `GET /api/worlds/{id}/story/quality-benchmark` |

| 全自主模式端到端验证 | `TestChapterRunnerE2E` (4 tests) + `TestStateConsistency` (5 tests) — 模拟生成 + 状态往返 + 10章累积 + 衰减收敛 | ✅ |

### ⬜ 待实施

（无 — Phase 3 全部完成）

---

## 全局修复汇总（本次会话，跨系统）

| 修复 | 说明 |
|------|------|
| 章节截断检测 | `_text_looks_truncated()` + finish_reason + 续写 + 收束 |
| 粗纲 32768 token | 8192→32768 + 自动触发工具 + 5轮续写 |
| story-macro 容错 | 截断无闭合 \`\`\` 时容错解析 |
| 标点规范化 | 全角/半角 + 引号配对 + 省略号/破折号 |
| 终端错误日志 | HTTPException + ValidationError + 未处理异常 3 处理器 |
| 情感系统 9 bug | 持久化/标签归一化/UI 刷新/静默错误消除 |

---

## 测试覆盖

```
tests/test_agents.py        25 tests   Phase 0
tests/test_agents_p1p2.py   30 tests   Phase 1/2
tests/test_agents_p3.py     36 tests   Phase 3
tests/test_*.py (existing)  447 tests 已有测试
─────────────────────────────────────
Total:                      569 tests  (excluding 3 e2e)
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
  │     │           ├── OutlineConstraint.parse()          # 粗纲硬约束
  │     │           ├── AgentStore.load_all_states()       # 加载角色状态
  │     │           ├── BeatReference.parse()              # 细纲软参考
  │     │           ├── ContinuityChecker.pre_check()      # 连续性校验
  │     │           ├── WorldClock.advance_chapter()       # P2: 时间推进
  │     │           ├── SceneSimulator.run()               # 角色互动 + 意图泄露 + 情绪传染
  │     │           ├── POVFilter.filter()                 # 单 POV 过滤
  │     │           ├── ShadowInfluence                    # P2: 影子→环境线索
  │     │           ├── SceneAssembler.check_pacing()      # P2: 节奏检查
  │     │           ├── BeatCoordinator.classify()         # P1: 偏离协调
  │     │           ├── StateInjector.for_writer_agent()   # 状态注入
  │     │           ├── chat_completion()                  # 作家 Agent
  │     │           ├── QualityEvaluator.evaluate()        # P3: 质量评分
  │     │           ├── ContinuityChecker.post_update()    # 状态更新
  │     │           └── AgentStore.save_state()            # 持久化
  │     │
  │     └── 失败 (<200 chars) → 自动回退正常路径
  │
  └── NO (或 Agent 失败) → 正常生成路径
           ├── (可选) Scene Chunking
           ├── 截断检测 + 续写 + 收束
           ├── 标点规范化
           └── 后处理 hooks
```

---

> **最后更新**：2026-06-07
> **版本**：v11 — Phase 0/1/2/3 全部 100% + 附录 B C2/C3 完成 + 569 测试通过

---

## 附录 B：结构同步改进方案（设计稿，待实施）

### 问题诊断

当 LLM 输出极其复杂的嵌套 JSON（如包含 7 个境界 × 5 个职业 × 每个职业 10+ 技能节点的完整 `power_system`），当前结构同步流水线面临三个瓶颈：

**B1. 单次 JSON 过大导致 LLM 输出截断**
- 完整境界体系 JSON 可达 5000-15000 行
- 即使 max_tokens 足够，LLM 在生成长 JSON 时容易出现：键名拼写错误、嵌套层级丢失、尾部截断、中文标点混入 JSON 值导致解析失败

**B2. 增量合并策略过于粗粒度**
- 当前合并按整个 `power_system` 对象替换子字段（`summary`, `tiers[]`, `profession_system`）
- 如果 LLM 只输出了一个境界的修改，但 JSON 包含了所有境界（因为 LLM 倾向于输出"完整"数据），合并时会覆盖其他境界的已有修改

**B3. 校对者过于依赖架构师补充**
- 当同步器提取失败或 JSON 不完整时，校对者→架构师补充循环需要额外 LLM 调用
- 对于超长 JSON，校对者自己也容易在审计时产生遗漏

### 改进方案

**C1. 分片式同步协议**

新增"分批同步"指令，让架构师在输出复杂模块时使用标记分段：

```
@@POWER_TIER:1@@
{...第1境 JSON...}
@@POWER_TIER:2@@
{...第2境 JSON...}
```

同步器逐段解析、逐段合并。某段解析失败不影响其他段。

**C2. 语义级增量合并算法**

以 `tiers[].name` 为锚点，只合并 LLM 实际修改过的境界：
- 架构师 prompt 中明确要求"只输出你修改过的境界"
- 同步器按 `tiers[].name` 匹配已有境界，仅更新匹配项
- 新增境界追加，已有但未在输出中提及的境界保持不动

**C3. 同步前 JSON 预校验 + 修复**

在同步器提取 JSON 后、合并前，增加一层轻量修复：
- 自动闭合未配对的 `{}[]`
- 移除尾部逗号
- 转义字符串中的未转义换行符
- 检测并修复中文标点混入（如 `，`→`,`、`：`→`:`）

**C4. 前端分批引导 UI**

- 在境界面板增加显眼提示（✅ 已实施）
- 聊天输入区增加"分批模式"切换：开启后，架构师只输出指定批次的 JSON
- 进度指示器：显示"第 2/5 批 — 已完成第 1-3 境，待完成第 4-7 境"

**C5. 职业/技能树 CRUD API（✅ 已实施）**

新增 5 个 API 端点支持精确的增量操作，绕过 JSON 同步流水线：
- `GET /power-system/professions` — 列出所有职业
- `POST /power-system/professions` — 添加/更新单个职业
- `DELETE /power-system/professions/{id}` — 删除职业
- `POST /power-system/skill-nodes` — 添加/更新技能节点
- `DELETE /power-system/skill-nodes/{id}` — 删除技能节点

这些端点允许未来的"职业构建 Agent"工具直接进行精确操作，而非依赖大批量 JSON 同步。

### 实施优先级

| 优先级 | 改进项 | 理由 |
|--------|--------|------|
| P0 | C5 职业/技能树 CRUD API | 已完成；为后续工具化打基础 |
| P0 | C4 前端分批引导 UI | 已完成 UI 提示；待增加进度指示器 |
| P1 | C3 同步前 JSON 预校验 | ✅ 已完成 — 中文标点归一化 + 自动闭合截断 JSON |
| P1 | C2 语义级增量合并 | ✅ 已完成 — tier_name 匹配 + 递归保护已有数据 |
| P2 | C1 分片式同步协议 | 解决超大 JSON 问题，但需要架构师 prompt 配合 |
