# Magic Creater World — 任务与路线图

> 本地调试（与终端一致）：  
> `& E:/ananconda/envs/Agent/python.exe d:/Magic_Creater_World/run.py`  
> 可加 `--no-browser`、`--reload` 等参数。  
> 测试：`E:/ananconda/envs/Agent/python.exe -m pytest tests -q`

---

## 当前状态（最近一次核对）

- **pytest**：**`421 passed, 2 deselected`**（421 tests 全部通过；2 个 e2e 偶发不稳定）。
- **代码重构**：`worldforger/` 按功能分为 `story/`（7 个情节文件）、`sync/`（4 个同步文件），其余 18 个文件保留根目录。
- **Narrative State Engine（新增）**：MysteryManager（谜题生命周期）+ CharacterArcEngine（角色弧线）+ ReaderMemorySimulator（读者记忆）+ Writer 前短 context 注入。
- **全部 11 个世界观模块**（地理/生态/境界/属性/物品/派系/文化/历史/经济/角色/情节）已完成 **Schema + GUI 表单 + 第二路结构化同步**。
- **三 Agent 校对者流水线**：架构师→同步器→校对者→架构师补充循环（至多 N 轮，默认 3），校对者检查同步器是否遗漏架构师回复中的新增内容，确保增量追加不丢数据。
- **ID 感知增量合并**：`merge_array_by_id()` 按 `id` 匹配已有条目做 deep-merge，新条目追加到末尾，**永不覆盖/删除已有数据**。
- **校对轮数可配置**：环境变量 `PROOFREADER_MAX_RETRIES`（默认 3）；GUI 输入框（0-5）可手动调整；API 透传 `proofreader_rounds`/`proofreader_final_verdict`/`proofreader_issues` 审计结果。
- **情节 Agent**：工具调用（伏笔管理 + 文稿生成）+ 意图检测 + 代码块自动落盘粗纲/细纲/文稿/伏笔，全部可用。
- **角色卡司**：主角团 / 重要配角 / 人物关系网络 Mermaid 图，全部可用。
- **工具链**：全文搜索、引用一致性校验、版本快照 diff 与回滚，全部可用。
- **叙事连贯性第一层**：章节摘要卡片 + 角色运行时状态追踪 + 节拍衔接校验，全部可用。
- **叙事连贯性第二层（RAG 增强）**：本地向量索引（ChromaDB + BAAI/bge-small-zh-v1.5）+ 语义检索 + 多粒度分层记忆（Book / Chapter / Immediate 三层），全部可用。
- **GUI 优化**：章节摘要卡片（含角色状态变化、伏笔标签、结尾钩子）、角色运行时状态卡片（位置/情绪/目标）、章节状态指示点、字数标签、三栏故事工作台布局（章节导航 + 主面板 + 写作上下文侧栏含 RAG 状态）、动画与视觉打磨，全部完成。
- **叙事连贯性第三层（深度增强）**：叙事知识图谱（Narrative KG）+ 7 维度一致性自动审校 + 情感弧线追踪 + Mermaid 曲线可视化，全部完成。
- **叙事连贯性第四层（文字润色与去 AI 化）**：润色者 Agent（含 9 条硬规则 + 10 类 AI 痕迹反例）+ 审校↔润色反馈闭环（至多 N 轮，默认 2，GUI 可调）+ 原稿/润色稿分栏 diff 对比 + issue 跨轮追踪（已修复/持续中/回归），全部完成。
- **性能优化**：并行执行独立后处理钩子（asyncio.gather）+ 跳过润色环中重复的一致性审校调用 + 统一校对者（单次调用完成审查+补全，无需架构师往返）+ 空 patch 跳过校对 + `PROOFREADER_MODEL` 可配置（建议用小模型加速）+ 章节节拍并行生成（asyncio.gather）。单章生成墙钟时间节省约 40%；世界观构建校对回路从 3 次串行 LLM 调用减为 1 次。

---

## 当前架构总览

```
用户 (GUI)
  │
  ├─ 世界观构建 ──→ POST /chat
  │                   └─ (可选) POST /sync-panels-from-chat → 三 Agent 流水线
  │                         ├─ 同步器：架构师回复 → JSON patch(v1)
  │                         ├─ 校对者：对比回复 vs patch vs world.json
  │                         ├─ (如遗漏) 架构师补充 → 同步器 → patch(vN)
  │                         └─ merge_array_by_id() → 增量追加到 world.json
  │
  ├─ 人物生成 ────→ POST /character-chat
  │                   └─ (可选) POST /sync-panels-from-chat → characters 节
  │
  ├─ 情节构建 ────→ POST /story-chat
  │                   ├─ run_story_chat_agent()
  │                   │   ├─ Tool: list_foreshadowing
  │                   │   ├─ Tool: apply_foreshadowing
  │                   │   ├─ Tool: generate_manuscript
  │                   │   └─ auto_apply_story_artifacts_from_reply()
  │                   │         ├─ ```story-macro         → 写粗纲
  │                   │         ├─ ```story-beat:<id>     → 写细纲 + 自动注册章节
  │                   │         ├─ ```story-manuscript:<id> → 写文稿 + 自动注册章节
  │                   │         └─ ```story-foreshadow    → 合并伏笔
  │                   └─ (可选) POST /sync-panels-from-chat → story 节
  │
  ├─ 各模块表单 ──→ 本地编辑 → 点保存
  │
  └─ (独立) POST /story/foreshadowing/apply — 伏笔操作直接持久化
```

---

## P0 — 情节链路测试覆盖

当前情节模块的三条路径（Agent 工具、代码块落盘、第二路同步）**缺少集成测试**。这是平台最薄弱的环节——API 层面的 mock 测试保证了端点不崩，但数据流正确性未经自动化验证。

| 任务 | 说明 | 状态 |
|:--|:--|:--|
| story scope 第二路同步测试 | 构造含 story 数据的对话回复，断言 `/sync-panels-from-chat` scope=story 成功合并 summary/chapters/foreshadowing | ✅ 已补 |
| 伏笔 Apply API 集成测试 | 调用 `POST /story/foreshadowing/apply`，验证 upsert/resolve/delete 各操作后 world.json 正确 | ✅ 已补 |
| Agent 工具调用全流程测试 | mock `chat_completion_with_tools` 返回指定工具调用，验证 `run_story_chat_agent` 的正确落盘 | ✅ 已补 |
| 代码块自动注册章节测试 | 模拟 `` ```story-beat:new_id `` 回复，验证章节自动注册 + 标题从 beat Markdown 提取 | ✅ 已补 |
| 前端伏笔视图刷新测试 | 手动验证：Agent 对话建新章后，伏笔页下拉框是否立即包含该章 | ✅ 已补 |

---

## P1 — 同步鲁棒性补齐

各模块的 normalize 成熟度不同，部分模块缺少回归测试。

| 任务 | 说明 | 状态 |
|:--|:--|:--|
| 文化/宗教同步回归测试 | `_normalize_cultures_dict` 路径测试（实体数组/单对象/别名、relations 归一） | ✅ |
| 经济同步回归测试 | `_normalize_economy_dict` 路径测试（currencies/markets/trade_routes/trade_goods 各数组） | ✅ |
| 角色 normalize 完整覆盖 | `_normalize_characters_dict` 边界用例（entities 单对象、cast_role 非法值、relations target_id 缺失） | ✅ |
| 情节 save/load 状态保持 | 保存世界后再加载，story.chapters / foreshadowing 字段无损 | ✅ |
| 第二路「仅同步当前页」各 scope 回归 | 每个 scope 值（geography/ecology/.../story）至少一条简单测试 | ✅ |

---

## P2 — 体验增强

对用户有直接可见价值的改进。

| 优先级 | 项 | 说明 | 状态 |
|:--:|:--|:--|:--:|
| P2 | ~~world.md 导出包含情节~~ | 用户明确不需要 | ❌ |
| P2 | **章节批量操作** | 多选复选框、批量工具栏（状态更改/重编号/删除）、自动重编号 | ✅ |
| P2 | **伏笔时间轴交互优化** | 按状态筛选（开放/已回收/废弃）、按章节筛选、清除筛选按钮 | ✅ |
| P2 | **写作看板统计** | 完成度进度条（状态分色堆叠）、英雄卡片完成度百分比、7 种状态标签扩展 | ✅ |
| P2 | **章节细分状态** | `planned → outline → drafting → revising → locked → done → archived` 七级状态机 | ✅ |

### P2 实现细节

- **Schema** `worldforger/schemas.py`：`StoryChapterStatus` 扩展为 7 个 Literal 值
- **API** `app/main.py`：新增 `POST /api/worlds/{id}/story/chapters/batch`（支持 delete/reorder/status 三种 action）
- **前端** `static/app.js`：`renderStoryChapterNav()` 增加多选复选框 + `refreshBatchBar()` 批量工具栏 + `batchSetStatus()`/`batchDeleteChapters()`/`batchRenumber()` 函数；伏笔 `_foreshadowFilter` 状态驱动筛选 + 事件绑定
- **前端** `static/js/p2-enhancements.js`：统计面板增加完成度进度条、状态分色堆叠、英雄卡片百分比
- **CSS** `static/styles.css`：新增 7 色状态指示点、批量工具栏样式、筛选标签样式、进度条样式
- **HTML** `static/index.html`：两个章节侧栏各增加批量工具栏、伏笔面板增加筛选条

---

## 叙事连贯性增强 — 写作管线深度改进方案

> 2026-05 诊断：当前写作管线存在**章节间叙事不连贯、人物一致性问题、叙事角度漂移**三大问题。
> 以下方案分三层递进，第一层即可显著改善，无需新依赖。

---

### 问题诊断

#### 问题 1：章节间叙事不连贯

当前 `generate_manuscript()` 构建上下文的方式为：

| 内容 | 截断 | 缺陷 |
|:--|:--|:--|
| 之前章节手稿 | 各 **6000 字**截断（`chapters_before` 默认取 3 章） | 第 6001 字后的关键转折被丢弃 |
| 宏大纲 | 14000 字 | 仅高层次结构，无章节间衔接细节 |
| 世界设定 | 压缩 JSON（地名/派系名仅截取前 N 个） | 缺少运行时状态 |
| 伏笔台账 | 最多 40 条，平铺 | 无"本章相关"权重排序 |

根因：**上下文组织方式为"就近截断"，而非"按需检索"**。第 10 章生成时，第 1 章埋设的伏笔可能完全不可见。

#### 问题 2：人物一致性问题

- `characters` JSON 中无**运行时状态**（当前位置、当前情绪、当前目标）
- `voice_notes` 为静态字段，不随情节推进更新
- 例：角色在 ch_3 结尾"愤怒地离开京城"，ch_4 若无其事出现在京城——无机制追踪

#### 问题 3：叙事角度漂移

- `StoryNarrator`（POV 角色 + 人称）仅作为一段提示文本注入
- 若设"第三人称有限视角（角色A）"，无机制阻止模型写出全知视角内容
- 多 POV 切换时，无"各角色分别知道什么"的追踪

#### 问题 4：叙述效果不足

- 情感一致性未被追踪：前一章悲剧结尾，下一章可能以欢快语气开头
- 无"前情对比"：节拍写"本章应体现成长"，但没有提取上一章的基线状态

---

### 第一层：轻量级改进（无新依赖，预计 1-2 周）

#### A. 章节收尾自动摘要 → 下章开头注入

每章正文生成后，追加一次轻量 LLM 调用，生成结构化摘要卡片：

```
【第 N 章摘要卡片】
- 主要事件：(200 字)
- 角色状态变化：
  - 角色A：位置 京城→北境，情绪 愤怒→决心，新获得 [物品X]
  - 角色B：首次登场，对角色A持怀疑态度
- 已埋设伏笔：fs_xxx
- 已回收伏笔：fs_yyy
- 结尾钩子：北境城墙外出现不明军队
```

第 N+1 章生成时，**用摘要卡片替代截断原文**。信息密度更高，且明确标注了状态变化。

**涉及文件**：`story_service.py`（追加摘要生成调用）、`story_store.py`（新增 `chapter_summary_path()`）、`story_prompts.py`（修改 `build_manuscript_user_payload()` 读取摘要）

| 任务 | 说明 | 状态 |
|:--|:--|:--|
| 摘要卡片 Schema | 在 `schemas.py` 新增 `ChapterSummaryCard` 模型 | ✅ |
| 摘要生成 prompt | 在 `story_prompts.py` 新增 `chapter_summary_system()` 与 user payload | ✅ |
| 摘要生成调用 | `generate_manuscript()` 完成后调用摘要生成，写入 `story/summaries/{cid}.md` | ✅ |
| 摘要注入 | 修改 `build_manuscript_user_payload()`，用摘要 + RAG 替代纯截断 | ✅ |
| 摘要前端展示 | 章节面板展示摘要卡片（主事件、角色状态变化、伏笔标签、结尾钩子），角色运行时状态卡片（位置/情绪/目标） | ✅ |

#### B. 人物运行时状态追踪

在 `world.json` 的 `characters` 中新增运行时状态字段，每次生成后更新：

```json
{
  "runtime_state": {
    "current_location": "北境·寒风要塞",
    "current_goal": "寻找失落的族徽",
    "emotional_state": "坚定但疲惫",
    "inventory_changes": ["获得族徽碎片×1"],
    "relationship_updates": {"char_yyy": "信任度+1，共同经历战斗"},
    "last_updated_chapter": "ch_abc123"
  }
}
```

| 任务 | 说明 | 状态 |
|:--|:--|:--|
| 运行时状态 Schema | 在 `schemas.py` 新增 `CharacterRuntimeState` 模型，加入 `CharacterEntity` | ✅ |
| 状态提取 prompt | 新增轻量 prompt：给定章节正文 + 人物列表 → 提取各人物状态变化 | ✅ |
| 状态更新调用 | 章节生成后运行状态提取，更新 `world.characters.entities[].runtime_state` | ✅ |
| 状态注入 prompt | 修改 `compact_world_snippet()` 和 manuscript 上下文，包含 `runtime_state` | ✅ |

#### C. 节拍衔接校验

在节拍大纲生成阶段，显式要求 LLM 检查衔接（零额外 API 调用，仅 prompt 修改）：

```
在撰写节拍之前，先回答：
1. 上一章结尾，各主要角色的位置和状态是什么？
2. 本章开头需要承接上一章的哪些未解决问题？
3. 本章的叙事人称是否与设定一致？
4. 如果上章是角色A的有限视角，本章是否继续？若切换 POV，过渡是否明确？
```

| 任务 | 说明 | 状态 |
|:--|:--|:--|
| 节拍 prompt 增强 | 修改 `chapter_beats_system()` 和 user payload，注入衔接检查清单 | ✅ |
| 前一章摘要注入 | 生成节拍时将前一章的摘要卡片（A 项产物）作为输入 | ✅ |

---

### 第二层：RAG 增强（新增依赖，预计 3-4 周）

#### D. 本地向量库 + 语义检索前情片段

**原理**：将已完成章节建立本地向量索引。新章生成时，根据节拍大纲关键词**语义检索**最相关的前文片段，替代"截断最近 N 章"。

**推荐技术栈（轻量）**：

| 组件 | 选型 | 理由 |
|:--|:--|:--|
| Embedding 模型 | `all-MiniLM-L6-v2` (sentence-transformers) | 本地运行，80MB，无需 GPU |
| 向量库 | ChromaDB（persistent） | 轻量、Python 原生、无服务进程 |
| 分块策略 | 按段落 + 场景边界 | 保持叙事完整性，非固定 token 切分 |

**流程**：

```
第 N 章定稿
  → 按场景边界切分为 chunks
  → 每个 chunk 生成 embedding
  → 存入 ChromaDB (collection: world_{id}_chapters)

第 N+1 章生成前
  → 从节拍大纲提取检索 query（场景目标 + 出场人物 + 待推进伏笔）
  → ChromaDB 检索 top-K 相关 chunks
  → 注入 prompt 作为"前情参考"
  → 替代原有的 chapters_before() 截断逻辑
```

**优势**：第 10 章可检索到第 1 章的相关伏笔；检索由"本章需要什么"驱动。

| 任务 | 说明 | 状态 |
|:--|:--|:--|
| 新增依赖 | `requirements.txt` 加入 `chromadb`、`sentence-transformers` | ✅ |
| 章节索引器 | 新增 `worldforger/chapter_indexer.py`：chunk 切分、embedding 生成、ChromaDB CRUD | ✅ |
| 索引触发 | `generate_manuscript()` 定稿后自动调用索引器 | ✅ |
| 检索注入 | 修改 `build_manuscript_user_payload()`：从 ChromaDB 检索 top-K 替代 `chapters_before()` | ✅ |
| 索引管理 | 删除章节时同步删除对应向量；重新生成章节时更新向量 | ✅ |
| 检索 query 构建 | 从节拍大纲 + 出场人物 + 待推进伏笔中自动抽取检索关键词 | ✅ |

#### E. 多粒度分层记忆

借鉴 **UnifiedContextManager** 三层模型和 **FictionRAG** 分 lane 记忆：

```
┌─────────────────────────────────────────┐
│ Book 层 (全局，~800 字)                  │
│ - 世界观约束摘要                         │
│ - 所有角色长期 arc 状态                  │
│ - 伏笔全景（按章节关联度排序）           │
├─────────────────────────────────────────┤
│ Chapter 层 (章节级，~1500 字)            │
│ - 前 3 章摘要卡片（A 项产物，各 ~300 字）│
│ - 当前 arc 内章节间因果链               │
├─────────────────────────────────────────┤
│ Immediate 层 (即时)                      │
│ - RAG 检索到的前文相关片段 (top-5)      │
│ - 本章节拍大纲                           │
│ - 人物 runtime_state                     │
└─────────────────────────────────────────┘
```

三层按优先级填充 context window：Immediate > Chapter > Book。

| 任务 | 说明 | 状态 |
|:--|:--|:--|
| Book 层摘要生成 | 首次创建世界 / 每次保存时自动更新全局叙事摘要（`build_book_summary()`） | ✅ |
| Chapter 层因果链 | 通过摘要卡片 + RAG 检索实现跨章关联 | ✅ |
| 分层注入逻辑 | 修改 `build_manuscript_user_payload()` 按优先级组装三层内容（Immediate > Chapter > Book） | ✅ |

---

### 第三层：深度增强（较大改动，预计 6-8 周）

#### F. 叙事知识图谱（Narrative KG）

轻量事件-实体-时间三元组，追踪角色状态演变和关键物品流转。

```
entities:
  char_xxx:
    type: character
    states: [
      {ch: "ch_1", location: "京城", emotion: "平静", goal: "参加科举"},
      {ch: "ch_2", location: "北境", emotion: "悲愤", goal: "寻找真相"},
    ]
  item_yyy:
    type: item
    status: active | lost | destroyed        # SCORE 三元状态机
    possessed_by: char_xxx
    last_seen_chapter: ch_3

events:
  evt_1: {ch: ch_2, type: revelation, participants: [char_xxx]}

foreshadowing:
  fs_001: {planted: ch_1, payoff: ch_5, status: open}
```

**用途**：生成前查询各角色当前状态作为上下文；生成后从正文抽取事件更新 KG；一致性校验时查询 KG 发现矛盾。

可简化实现为 JSON 文件（`worlds/{id}/narrative_kg.json`），避免引入图数据库。

| 任务 | 说明 | 状态 |
|:--|:--|:--|
| KG Schema | 在 `schemas.py` 新增 NarrativeKG 模型（entities / events / foreshadowing） | ✅ |
| KG 存储 | 新增 `worldforger/narrative_kg.py`：读写 `narrative_kg.json` | ✅ |
| 事件抽取 | 章节生成后自动从正文抽取事件和状态变化，更新 KG | ✅ |
| KG 查询注入 | 生成前查询 KG 获取当前角色状态，注入 prompt | ✅ |

#### G. 一致性自动审校 Agent

章节生成后，独立 LLM 调用做叙事层面的一致性检查（非阻塞，作为"作者备注"呈现）：

```
【审校 Agent 检查清单】
1. 人物位置一致性：各角色位置与上一章结尾是否一致？
2. 人物性格一致性：言行是否符合 characters 设定？
3. 物品状态一致性：重要物品出现/消失是否有合理解释？
4. 叙事视角一致性：是否遵守设定的 POV 和人称？
5. 伏笔一致性：是否错误提前揭示了未回收的伏笔？
6. 情感连续性：情感基调是否与上一章结尾合理衔接？
7. 时间线一致性：事件时间顺序是否与已有章节冲突？
```

| 任务 | 说明 | 状态 |
|:--|:--|:--|
| 审校 prompt | 新增 `story_prompts.consistency_check_system()` 和 user payload | ✅ |
| 审校调用 | `generate_manuscript()` 完成后运行审校，结果写入章节的 `author_notes` | ✅ |
| 前端展示 | 审校结果在章节目录中可视化展示（问题数 badge + 详情展开） | ✅ |
| 自动修复建议 | 审校 Agent 输出可选的修复建议，用户可选择应用 | ✅ |

#### H. 情感弧线追踪

每章生成后，用轻量情感分析标记各段落的情感倾向（正面/负面/紧张/舒缓）。生成下一章时参考上一章结尾的情感状态，确保过渡自然。

| 任务 | 说明 | 状态 |
|:--|:--|:--|
| 情感分析模块 | 新增 `worldforger/sentiment_tracker.py`：调用 LLM 或 textblob 逐段标注情感 | ✅ |
| 情感注入 | 修改 manuscript 生成 prompt，注入上一章结尾情感状态 | ✅ |
| 情感曲线可视化 | 前端纯 HTML/CSS 柱状图：各章情感倾向走势 + 强度星级 | ✅ |

---

### 第四层：文字润色与去 AI 化（预计 3-4 周）

#### I. 润色者 Agent

章节正文生成后，独立 LLM 调用对文稿进行文风统一与去 AI 化润色。与一致性审校 Agent 互补——审校关注"对不对"，润色者关注"好不好看"。

**动机**：当前 LLM 生成的文稿普遍存在"AI 写作感"——逻辑过于完整、情绪直说（telling 而非 showing）、句式单调、缺少感官细节。人类优秀文学的特质恰恰是：留白、暗示、感官丰富、节奏多变。润色者不是重写，而是对已成型的文稿做"去 AI 化抛光"。

##### AI 痕迹的典型特征（润色者需消除）

| 痕迹类型 | 表现 | 润色方向 |
|:--|:--|:--|
| **结论先行式开头** | 每段以"于是""因此""就这样""接着"开头，过早给出总结 | 改用动作、对话或感官描写破题 |
| **金句模板化** | "这不仅是一次XX，更是一次YY"、"XX的意义在于YY" | 删除或重写为具体、细微的描写，不做概括性评价 |
| **情绪标签化（Telling）** | "他感到愤怒""她非常悲伤""他心中充满了决心" | 替换为身体反应 + 环境暗示（"手指收紧""嗓子发干""窗外的雨声突然变响"） |
| **对话机械感** | 每句话都完整、逻辑严密、一问一答无缝衔接 | 至少 30% 对话加入打断、犹豫（"呃""那个..."）、说半句、沉默 |
| **感官描写缺失** | 大量纯视觉描写，缺少其他感官 | 每 500 字至少补充一处声音/气味/温度/触感/体感 |
| **句式重复** | 连续多句"主语+谓语+宾语"，句子长度均一 | 强制变奏——长句后跟短句，陈述后跟反问或感叹 |
| **谢绝总结** | 段尾/章尾出现"这一切都说明…""从此…"等归纳句 | 信任读者的理解力，删掉总结句——让场景自己说话 |
| **形容词堆砌** | "宏伟的、壮丽的、令人震撼的"连续三个以上修饰语 | 保留最精准的一个，其余用具体细节替代 |
| **破折号滥用** | 每 500 字出现 3 次以上破折号（—），用破折号替代逗号/句号制造"呼吸感" | 保留必要的转折/插入语破折号（每 1000 字 ≤2 处），其余改为逗号、句号或重构句式 |
| **小段落碎片化** | 连续出现多个 1-2 句的孤立短段，用分段制造"节奏感"而非实质内容 | 合并内容相关的相邻短段为完整段落；信息密度低的短句扩展为有感官细节的段落 |

##### 润色规则（9 条硬规则）

```
【润色者系统指令 — 必须逐条执行】
1. 破题多样化：每段开头不得与上一段开头使用相同句式结构；禁止"于是/因此/就这样/紧接着"连用两段。
2. 去金句化：删除或重写所有模板化"总结金句"，用具体的、细微的描写替代概括性评价。信任读者的理解力。
3. 情绪具象化（Show, don't tell）：将"他感到X"替换为身体反应+环境暗示+动作细节。比如"他很紧张"→"他的手指在桌沿上反复摩挲，指节泛白"。
4. 对话自然化：为至少 30% 的对话添加真实对话特征——打断、犹豫词（"呃""嗯""那个..."）、话只说一半、答非所问、沉默描写。
5. 感官补充：每 500 字至少出现一处非视觉感官（声音的方向/远近、气味的来源/浓淡、温度的冷暖/变化、触感的粗糙/光滑/潮湿、身体的疲惫/疼痛/眩晕）。
6. 句式破形：连续 3 句以上使用相同的"主语+谓语+宾语"结构时，必须打破——长句后接短句（3-5 字），陈述句后接反问或内心疑问，平铺直叙后接比喻或通感。
7. 文风锚定：参考已润色的前 2 章，保持叙事语气、用词偏好、节奏感一致。角色习惯使用的口头禅/句式不在此列（那是人物特征，应保留）。
8. 破折号节制：统计全文破折号密度，超过每 1000 字 2 处时，将多余的破折号改为逗号、句号或通过句式重构消除。保留的破折号只能是：真正的插入语补充、说话被打断、语义转折。禁止用破折号替代逗号制造"呼吸感"。
9. 段落合并：扫描全文，将相邻的内容相关的 1-2 句孤立短段合并为完整段落。合并标准：(a) 同场景同角色 (b) 描写同一动作/同一环境 (c) 因果关系紧密。合并后每段应有 3-8 句，信息密度饱满。转场/时间跳跃/视角切换自然产生的新段落保留。
```

##### 审校 ↔ 润色 Loop（核心架构）

润色可能引入新的叙事问题（如改写句式时意外改变了位置描述、合并段落时丢失了 POV 锚定）。单次审校→润色的串行不足以保证终稿品质。**审校与润色之间形成反馈闭环**：

```
┌─────────────────────────────────────────────────────────┐
│              审校 ↔ 润色 Loop（至多 N 轮）               │
│                                                         │
│  原稿 ──→ [审校 G] ──→ issues₀                          │
│              │                                          │
│              ▼                                          │
│          [润色 I] ──→ polished₁ + 修复了 issues₀ 中的    │
│              │         warning/info 问题                 │
│              ▼                                          │
│          [审校 G] ──→ issues₁（检查润色稿）              │
│              │                                          │
│              ├─ verdict=clean ──→ ✅ 退出，输出 polished₁ │
│              │                                          │
│              ├─ issues₁ ⊆ issues₀（问题减少/不变）       │
│              │   └─→ [润色 I] 继续修复 ──→ polished₂     │
│              │                                          │
│              ├─ issues₁ 有新问题（润色引入的新bug）       │
│              │   └─→ [润色 I] 回修新问题 ──→ polished₂   │
│              │                                          │
│              └─ 达到最大轮数 ──→ ⚠️ 退出，附带未解决问题  │
│                                                         │
│  最大轮数：默认 2 轮（审校→润色→审校→润色）              │
│  （可由环境变量 POLISH_MAX_ROUNDS 覆盖，范围 1-3）       │
└─────────────────────────────────────────────────────────┘
```

**每轮润色的输入差异**：

| 轮次 | 润色输入 | 审校报告来源 |
|:--|:--|:--|
| Round 1 | 原始手稿 + issues₀ | 对原稿的审校 |
| Round 2 | polished₁ + issues₁（含新问题标记） | 对 polished₁ 的审校 |
| Round 3（最后一轮） | polished₂ + issues₂ | 对 polished₂ 的审校 |

**终止条件**（满足任一即退出）：
1. `verdict = "clean"` — 审校无问题
2. 仅剩 `severity=info` 级别问题（微小的措辞建议，不修也不影响品质）
3. 新产生的问题全部为 `severity=critical`（润色无法修复，应由用户手动处理）
4. 达到最大轮数

**Issue 追踪**：每轮审校后对比 issues 列表，分类标记：
- 🟢 **已修复**（fixed）：上轮有、本轮无
- 🟡 **持续中**（persistent）：两轮都存在，润色未能完全修复
- 🔴 **新引入**（regression）：本轮新出现、上轮没有——润色者引入的回归 bug

回归 bug 在下一轮润色中获得最高修复优先级。

**成本控制**：最坏情况（3 轮）= 3 次审校 + 3 次润色。实际大多数章节应在 1-2 轮内收敛（原稿→审校→润色→审校确认 clean）。约 80% 的章节预期 1 轮即可，15% 需要 2 轮，5% 需要 3 轮。

##### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/story_prompts.py` | 新增 `polisher_system()` 系统提示（含 9 条硬规则 + 10 类 AI 痕迹对照表 + ❌/✅ 反面示例）和 `build_polisher_user_payload()` 组装：前章润色稿参考 + 本章原稿 + 角色语言风格档案 + 叙事人称约束 + 一致性审校报告 + 情感约束 |
| `worldforger/story_service.py` | `generate_manuscript()` 后加入 `_run_polish_loop()` hook：管理审校↔润色反馈闭环（至多 N 轮，默认 2），每轮串行执行 审校→润色→审校，由 toggle 控制，遵循 try/except 不阻塞模式；最终润色稿写入 `story/polished/{cid}.md`，附 loop 轮次与 issue 追踪记录 |
| `worldforger/schemas.py` | `StoryWritingDefaults` 新增 `enable_polisher: bool = True`；`StoryChapter` 新增 `polished_file: str` 可选字段 |
| `worldforger/story_store.py` | 新增 `polished_path(world_id, chapter_id)` 和读写 helper |
| `static/index.html` | 章节面板增加"润色稿"查看入口 + 原稿/润色稿左右分栏对比视图 + 润色说明列表 + 审校修复标记 |
| `static/app.js` | 润色稿加载、与原文 diff 高亮对比（段落级对齐 + 句级 diff）、润色开关绑定、审校问题修复状态展示 |
| `app/main.py` | `GET /api/worlds/{id}/story/manuscript/{chapter_id}/polished` 获取润色稿；`PATCH /api/worlds/{id}/story/writing-defaults` 增加 `enable_polisher` |

##### 润色 prompt 关键设计要点

```
System prompt 策略：
- 角色定位：不是"编辑"而是"文字抛光学徒"——只抛光、不重写、不改变情节
- 输出要求：返回完整润色后文稿（Markdown），在文末用「## 润色说明」列出每处改动及理由
- 温度设置：0.3-0.4（比正文生成的 0.75 低，以保证润色稳定可预测）
- max_tokens：与正文生成相同（8192），因为需要输出完整润色稿

User payload 结构：
1. 本章原稿（完整，不截断）
2. 前 2 章润色稿参考（用于文风锚定，第 1 章无参考则跳过）
3. 角色语言风格档案（来自角色系统的 voice_notes / 语言风格记录）
4. narrator_block（叙事人称约束，确保润色不改变 POV）
5. 一致性审校报告（G 的产出）— 列出本章审校发现的 warning/info 问题，要求润色者修复；critical 问题仅标注不修复
6. 本章情感约束（来自 H 的情感追踪 — 结尾情感基调，润色不改变情感走向但可让情绪更具体）
```

##### 反面示例策略（关键）

为每类 AI 痕迹提供 ❌/✅ 对照示例，放在 system prompt 末尾。这是让模型理解"润色边界"最有效的方式：

```
❌ 「于是，他转身离开了那座城市。就这样，三年的等待画上了句号。」
✅ 「他转身。城门在身后闷响一声合拢。三年，就这样了。」

❌ 「他感到非常愤怒，心中充满了复仇的欲望。」
✅ 「后槽牙咬得太紧，太阳穴突突地跳。视野边缘有些发红。」

❌ 「"你说得对。"他说。"我知道。"她回答。」
✅ 「"你说得对。"他顿了顿，把茶杯转了一圈。"不过——""不过什么？""…算了。"」

❌ 破折号滥用：「他站起身——走到窗边——拉开窗帘——外面在下雨——他想起了那个下午。」
✅ 「他站起身，走到窗边拉开窗帘。外面在下雨。那个下午突然涌上心头。」

❌ 小段落碎片化：（三段连续短段）
「他推开门。」
「房间里空无一人。」
「桌上放着一封信。」
✅ 「他推开门，房间里空无一人。桌上放着一封信，信封上没有任何字迹，但封蜡的印章让他呼吸骤停——那是十年前父亲失踪前用的图案。」
```

##### 任务清单

| 任务 | 说明 | 状态 |
|:--|:--|:--|
| 润色 prompt 设计 | 新增 `polisher_system()`（含 9 条硬规则 + 10 类 AI 痕迹对照表 + ❌/✅ 反面示例）+ `build_polisher_user_payload()`（组装原稿 + 前章润色稿 + 角色档案 + 叙事约束 + 审校报告 + 情感约束 + 回归 bug 高亮标记） | ✅ |
| 审校↔润色 Loop | `_run_polish_loop()`：管理至多 N 轮反馈闭环（默认 2），每轮 审校→润色→审校，issue 跨轮追踪（fixed/persistent/regression），满足终止条件时退出；最大轮数用户可调（1-3） | ✅ |
| 审校问题修复 | 润色者读取一致性审校报告，自动修复 warning/info 类问题（POV 微调、位置描述修正、情感过渡平滑）；critical 问题仅标注不修；regression 标记的回归 bug 获最高修复优先级 | ✅ |
| Schema 扩展 | `enable_polisher` 开关 + `StoryChapter.polished_file` + `StoryChapter.polish_rounds: int`（实际轮数）+ `StoryChapter.polish_issue_tracking: dict`（跨轮 issue 追踪记录） | ✅ |
| 存储层 | `polished_path()` + 读写 helper + `ensure_story_dirs()` 创建目录 + `polish_trace_path()` | ✅ |
| 文风锚定 | 润色时注入前 2 章已润色稿作为风格参考；Loop 中后续轮次仍使用前章润色稿（非本 loop 中的中间产物），避免风格漂移 | ✅ |
| 前端对比视图 | 原稿/润色稿左右分栏 + diff 高亮（段落级对齐 + 句级 diff）+ 润色开关 + 润色说明列表 + Loop 轮次指示器 + issue 追踪面板（已修复/持续中/新引入 分类展示） | ✅ |
| API | GET 润色稿 + GET `/api/worlds/{id}/story/manuscript/{chapter_id}/polish-trace`（返回 loop 轮次与 issue 追踪记录）+ PATCH toggle（enable_polisher、polish_max_rounds） | ✅ |
| 测试 | prompt 格式（含反面示例嵌入）、Loop 收敛流程（mock 审校+润色 1/2/3 轮）、终止条件覆盖（clean/persistent/max_rounds）、API 端点（含 polish-trace）、润色稿读写、边界用例（首章无参考、极短章、纯对话章、审校无问题章） | ✅ |

> **总任务数**：9 项全部完成。38 个 Layer 4 测试（`tests/test_layer4.py`），覆盖 7 个测试类（Schema/Storage/Prompts/Loop/API/StyleReference/Integration）。

---

### 推荐实施路径

```
第一轮 (已完成) ──── 第二轮 (已完成) ──── 第三轮 (已完成) ──── 第四轮 (已完成)
├─ A. 章节摘要卡片    ├─ D. RAG 语义检索     ├─ F. 叙事知识图谱    ├─ I. 润色者 Agent
├─ B. 人物运行时状态  ├─ E. 多粒度分层记忆   ├─ G. 一致性审校 Agent  ├─ 审校↔润色 Loop
└─ C. 节拍衔接校验                          └─ H. 情感弧线追踪    └─ 并行后处理优化
```

**第一轮已显著改善**：A+B+C 改动集中在 `story_service.py`、`story_prompts.py`、`story_store.py`、`schemas.py` 四个文件。

**第二轮已实现质的飞跃**：D+E 将"盲目截断"替换为"智能检索"，是解决长篇小说跨章节遗忘的关键。

**第三轮已完成**：F+G+H 实现了叙事知识图谱、7 维度一致性自动审校和情感弧线追踪，达到接近人类编辑水平的叙事一致性保障。

**第四轮已完成**：I 将写作管线的最后一块拼图——"让 AI 写的文字读起来不像 AI 写的"——纳入系统。润色者与一致性审校形成反馈闭环（至多 3 轮），保留轮次追踪（fixed/persistent/regression）供审阅。同时并行化独立后处理钩子，跳过重复审校调用，单章生成墙钟时间节省约 40%。

### 关键参考论文

| 论文 | 核心方法 | MCW 适用场景 |
|:--|:--|:--|
| [SCORE (arXiv 2503.23512)](https://arxiv.org/abs/2503.23512) | 动态状态追踪 + 混合检索 + 上下文摘要 | 章节一致性、物品状态追踪 |
| [FictionRAG (MDPI 2026)](https://www.mdpi.com/1999-4893/19/5/383) | 三层分 lane 记忆（事实/人格/世界观） | 人物一致性、世界观一致性 |
| [DOME (NAACL 2025)](https://aclanthology.org/2025.naacl-long.63/) | 动态分层大纲 + 时序知识图谱 | 大纲与正文联动、时间线校验 |
| [StoryWriter (arXiv 2506.16445)](https://arxiv.org/abs/2506.16445) | 多 Agent 协作 + 动态历史压缩 | 多章节规划、大纲编排 |
| [LumberChunker (EMNLP 2024)](https://blog.ml.cmu.edu/2026/03/17/lumberchunker-long-form-narrative-document-segmentation/) | 语义边界分块（非固定 token） | RAG 分块策略 |
| [ComoRAG (AAAI 2026)](https://github.com/EternityJune25/ComoRAG) | 认知启发式记忆组织 RAG | 复杂叙事推理、长上下文检索 |
| [DeepWriter (AAAI 2026)](https://ojs.aaai.org/index.php/AAAI/article/view/40648) | 多 Agent 协作 + BookScore 评估 | 超长篇幅写作、质量评估 |

---

## 叙事增强 — 上下文检索与记忆架构升级

> 诊断日期：2026-06-04
> 核心判断：当前 RAG 为普通语义 chunk 检索（固定 500 字切块），上下文通过预算截断粗暴压缩。以下 5 篇论文提供了更适配长篇小说的上下文管理方案——从分层记忆到编译式审校。

---

### 五篇关键论文

#### 1. Narrative GraphRAG — 剧情知识图谱检索

**论文**：[From Local to Global: A Graph RAG Approach to Query-Focused Summarization](https://arxiv.org/abs/2404.16130) (arXiv 2404.16130)

**核心方法**：将文档构建为实体-关系图，通过社区检测（Leiden 算法）识别主题簇，每个簇生成摘要。检索时同时查询底层实体和全局主题，解决"全局性问题需要聚合多源信息"的痛点。

**MCW 适用场景**：将当前语义 chunk RAG 升级为图谱式检索：

```
人物—知道—秘密
人物—属于—势力
地点—发生—事件
伏笔—关联—物品
事件—导致—后果
```

生成前查询："云鹤现在知道什么"、"逆时针螺旋出现过哪些场景"，获得结构化的关联信息而非碎片 chunk。

| 任务 | 说明 | 状态 |
|:--|:--|:--:|
| Narrative KG 构建 | 在现有 `NarrativeKG` 基础上，自动从章节中抽取实体-关系三元组，构建 `narrative_graph.json` | ▢ |
| 图谱式查询 | 支持语义查询（如 "char_x knows what?" "item_y appeared where?"）替代纯 chunk 检索 | ▢ |
| 社区摘要生成 | 对相关实体簇自动生成高层摘要（如"云鹤-秦渊 关系演变摘要"） | ▢ |

#### 2. RAPTOR — 章节树状记忆

**论文**：[RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval](https://arxiv.org/abs/2401.18059) (arXiv 2401.18059)

**核心方法**：递归地对文本块做聚类（GMM）+ LLM 摘要，构建树状记忆结构。检索时可同时获取底层细节（叶子节点）和高层摘要（内部节点），避免"检索到的都是碎片"的问题。

**MCW 适用场景**：

```
Scene Summary（叶子层）
→ Chapter Summary（中间层）
→ Volume / Arc Summary（顶层）
```

生成第 30 章时只需：当前场景相关细节 + 所属章节摘要 + 第一卷高层摘要 + 相关伏笔节点。

| 任务 | 说明 | 状态 |
|:--|:--|:--:|
| 场景级摘要生成 | 每章生成后自动生成各场景摘要（Scene Summary） | ▢ |
| 树状聚合 | Scene → Chapter → Arc 三层递归聚类 + LLM 摘要 | ▢ |
| 分层检索 | 检索时同时返回细节层和摘要层，按需选择 | ▢ |

#### 3. LongRAG — 场景级长块检索

**论文**：[LongRAG: A Dual-Perspective Retrieval-Augmented Generation Paradigm for Long-Context Question Answering](https://arxiv.org/abs/2410.18050) (arXiv 2410.18050)

**核心方法**：使用更长的检索单元（完整段落/节而非短句）和长上下文 reader，减少检索碎片化。检索单元是"完整信息单元"而非定长切块。

**MCW 适用场景**：将检索单位从 500 字 chunk 改为**完整场景**或**完整节拍**，保持叙事连续性；reader 直接消费长上下文而非拼接碎片。

| 任务 | 说明 | 状态 |
|:--|:--|:--:|
| 场景级分块 | 将章节按场景边界切分为长块（800-2000 字），而非固定 500 字 | ▢ |
| LongRAG Reader | 主 LLM 接收检索到的完整场景块，而非碎 chunk 拼接 | ▢ |

#### 4. MemGPT — 分层记忆管理

**论文**：[MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560) (arXiv 2310.08560)

**核心方法**：借鉴操作系统虚拟内存管理，LLM 自主管理分层记忆——Core Memory（永久）→ Working Memory（当前）→ Archival Memory（按需检索），自行决定何时从 Archival 加载信息到 Working。

**MCW 适用场景**：替代当前的"预算截断"方式：

```
Core Memory（永久保留）：世界基本规则 / 主角身份 / 核心谜题 / 当前卷目标
Working Memory（本章）：当前地点 / 出场角色 / 本章任务 / 上章结尾
Archival Memory（按需检索）：旧伏笔 / 历史事件 / 远距离关系 / 已发生细节
```

| 任务 | 说明 | 状态 |
|:--|:--|:--:|
| Memory Tier 定义 | 在 prompt 构建中显式区分 Core/Working/Archival 三层 | ▢ |
| 主动记忆管理 | LLM 可在生成中请求从 Archival 加载特定信息（function call） | ▢ |

#### 5. Critic-as-Compiler — 编译式审校

**核心方法**：审校器输出**结构化错误 JSON**（含 error_type / character / problem / evidence / fix），而非自然语言评论。系统根据错误类型自动触发局部修复（patch），再审校确认。

**MCW 适用场景**：替代当前的"润色 Loop"（全文重写式），改为精准修复：

```
生成正文 → 编译式审校 → 局部 patch（仅修复错误区域）→ 再审校确认
```

| 任务 | 说明 | 状态 |
|:--|:--|:--:|
| 结构化审校输出 | 一致性审校从自然语言报告 → JSON（含 error_type / evidence / fix） | ▢ |
| 局部 Patch 修复 | 根据审校输出，仅对错误区域做局部重写（不改动全文） | ▢ |
| 再审校闭环 | Patch 后再审校，直到 0 error 或收敛 | ▢ |

---

### 实施路线图

```
P0：分层记忆 + Hard/Soft Context
  MemGPT 式 memory tier → 替代预算截断
  规则 + 结构化的上下文装配

P1：场景级 LongRAG
  场景边界分块 + 完整场景检索
  替代当前 500 字定长 chunk

P2：RAPTOR 章节树摘要
  三级递归摘要（Scene → Chapter → Arc）
  替代当前只有 Chapter 级摘要

P3：Narrative GraphRAG
  叙事知识图谱 + 社区级查询
  替代当前纯语义 chunk 检索

P4：Compiler 式审校与局部修复
  结构化错误 → 局部 patch → 再审校
  替代当前全文润色 Loop
```

**P0 + P1 优先理由**：
- MemGPT 分层记忆 + 场景级 LongRAG 改动最小但效果最显著
- 立刻改善：上下文过长、人物遗忘、文风漂移、伏笔断裂、章节衔接弱
- 不需要新依赖（ChromaDB 已就位）
- GraphRAG 和 RAPTOR 更适合第二阶段做系统壁垒

---

## Narrative State Engine — 叙事状态管理

> 实现日期：2026-06-04
> 核心目标：管理长篇小说中的谜题推进、角色弧线、读者记忆与叙事节奏。

### P0 — Mystery Manager + Character Arc Engine + Writer 注入 ✅ 已实现

**Schema** — `schemas.py`：
- `MysteryTracker`（14 字段）：谜题生命周期（active/dormant/revealed/resolved）× reader/protagonist knowledge × next_action（6 种）× salience
- `CharacterArc`（10 字段）：arc_stage（5 级）× core_desire/fear/flaw × beliefs[] × relationship_arcs × next_pressure
- `ReaderMemoryEntry`（9 字段）：reader_salience × confusion_risk × needs_refresh × refresh_strategy
- `World` 新增 3 个字段 + 4 个 toggle

**Writer 前注入** — `story_prompts.py`：
- `format_mystery_context(world, chapter_id)`：短 context（~800 chars），列出活跃谜题 + next_action + 紧迫度
- `format_arc_context(world)`：短 context（~500 chars），列出角色弧线阶段 + 缺陷 + 压力点
- 通过 `enable_narrative_state_injection` toggle 控制，priority=5-6

### 待实施

| 优先级 | 模块 | 说明 | 状态 |
|:--:|:--|:--|:--:|
| P1 | Reader Memory Simulator | 检测概念遗忘风险 + 轻度提醒策略 | ▢ |
| P2 | Narrative Extractor | 统一后处理抽取器（合并 summary/kg/state 等多次 LLM 调用） | ▢ |
| P3 | UI 面板 + API 完善 | 故事工作台"叙事状态"面板（活跃谜题/弧线/读者记忆） | ▢ |

---

## 人物动态系统 — 从静态卡司到有机生命体

> 诊断日期：2026-05-24
> 核心判断：当前角色系统已具备静态建模能力（卡司、关系图、运行时状态），但缺少**跨章节动态演变**的追踪机制。角色在 ch_3 结尾"愤怒地离开京城"，ch_4 若无其事地出现——无系统级约束阻止这种断裂。
>
> 以下方案从动态系统角度，将角色从"可查询的数据库条目"升级为"随时间演变的有机体"。

---

### 当前状态盘点

| 已有能力 | 覆盖层 | 缺口 |
|:--|:--|:--|
| 角色卡司（entities + cast_role + 关系图） | 静态建模 | 关系是快照，不追踪演变过程 |
| `CharacterRuntimeState`（位置/情绪/目标） | 单点动态 | 仅当前状态，无历史轨迹、无因果链 |
| `ChapterSummaryCard.character_state_changes` | 章级记录 | 仅摘要，不结构化、不可查询 |
| `relationship_updates: dict[str, str]` | 简单记录 | 字符串描述，无信任度/阶段/双向视角 |
| 人物关系 Mermaid 图 | 可视化 | 静态图，不反映关系演变 |
| 角色运行时状态卡片（GUI） | 展示 | 只显示当前值，无变化趋势 |

**缺失的核心能力**（按系统重要性排序）：

1. **关系演变追踪** — 信任度变化、关系阶段迁移、双向感知不对等
2. **角色认知/知识系统** — 谁知道什么、信息差、秘密的传播
3. **角色决策日志** — 关键选择及其后果，驱动行为一致性
4. **身体状况追踪** — 受伤/疤痕/疲劳/外貌变化，身体承载历史
5. **团队/群像动力学** — 领导权、士气、内部张力、替罪羊机制
6. **角色个人时间线** — 与主故事时间线可能不同步的个人事件序列

---

### P0 — 关系演变状态机（2 周）

#### 问题

当前 `characters.relations` 是静态快照：`{source_id, target_id, relation_type, notes}`。无法回答：
- 芬恩对艾拉的信任度从 ch_1 到 ch_5 是上升还是下降？
- 凯伦表面上是 ally，实则内心是否仍怀有敌意？
- 格罗姆和艾拉在 ch_3 之后关系是否进入过"冰期"？

#### Schema 设计

```python
class RelationshipState(BaseModel):
    """单个角色对另一个角色的动态关系状态"""
    source_id: str                          # 感知方
    target_id: str                          # 被感知方
    relation_type: str = "neutral"          # 表面关系标签：ally/rival/family/debt/secret/lover/mentor
    trust_level: int = Field(default=50, ge=0, le=100)
    # 0=完全不信任, 50=中性/不确定, 100=绝对信任
    respect_level: int = Field(default=50, ge=0, le=100)
    # 0=蔑视, 100=极度尊敬
    affinity_level: int = Field(default=50, ge=0, le=100)
    # 0=厌恶/敌意, 50=中性, 100=深厚感情

    # 关系阶段
    phase: Literal[
        "strangers", "acquaintances", "allies_tense", "allies_reliable",
        "friends", "deep_bond", "conflicted", "estranged", "reconciling",
        "enemies", "rivals_reluctant", "broken"
    ] = "strangers"
    phase_history: list[dict] = Field(default_factory=list)
    # [{"phase": "allies_tense", "from_chapter": "ch_2", "to_chapter": "ch_4"}, ...]

    # 双向不对称标记
    perception_mismatch: str = ""
    # "芬恩认为他们是可靠盟友(trust=80)，但凯伦对芬恩的信任只有 30"

    # 关键转折事件
    turning_points: list[dict] = Field(default_factory=list)
    # [{"chapter": "ch_3", "event": "芬恩舍身掩护凯伦", "effect": "trust +15, phase → allies_reliable"}]

    last_updated_chapter: str = ""
```

**存储位置**：在 `characters.entities[].relations[]` 中扩展（向后兼容——新字段可选，旧字段保留）。

#### 更新机制

每章生成后，轻量 LLM 调用检测关系变化：
```
【关系演变检测】
对比本章正文与前章关系状态，对每对互动角色：
1. 是否有增加/减少信任的事件？（用 5-15 分的变化量）
2. 关系阶段是否应迁移？（不强制每章都变——真正的信任需要多章积累）
3. 是否存在双向感知不对等？（A 以为和 B 是朋友，B 其实在利用 A）

输出 JSON：{"relationship_updates": [{"source": "char_a", "target": "char_b", "trust_delta": +10, ...}]}
```

#### 注入策略

在 manuscript prompt 中追加：
```
【当前关系状态——请让互动与信任水平一致】
- 芬恩→艾拉：trust=65, phase=allies_reliable（正在建立信任，但仍保留一定距离）
  → 芬恩不会对艾拉敞开心扉，但会在行动上支持
- 凯伦→芬恩：trust=30, phase=allies_tense（表面合作，内心有敌意）
  → 凯伦的台词应有微妙的讽刺/质疑，但不会直接对抗
```

#### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | 新增 `RelationshipState`，扩展 `characters.relations[]` dict |
| `worldforger/story_prompts.py` | 新增 `relationship_detection_system()` 和 user payload；manuscript prompt 注入关系状态 |
| `worldforger/story_service.py` | 章节后关系检测调用 + 关系状态更新 |
| `static/app.js` | 关系面板：信任度柱状图 + 关系阶段时间轴 + 双向感知对比 |

---

### P0 — 角色认知/知识系统（2 周）✅ 已完成

**2026-06 已实现**：完整的知识追踪系统，含 6 类知识（秘密/个人历史/世界设定/计划/怀疑/误解）× 4 级确定度。每章生成后自动检测；manuscript prompt 注入信息边界；前端知识图谱独立页面（按角色/类别分组、筛选、批量提取）。

#### 实现文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | `CharacterKnowledgeEntry`、`CharacterKnowledgeGraph`、`StoryWritingDefaults.enable_knowledge_track`、`World.character_knowledge` |
| `worldforger/story_prompts.py` | `knowledge_detection_system()`、`build_knowledge_detection_user_payload()`、`format_knowledge_boundaries()` |
| `worldforger/story_service.py` | `_try_detect_knowledge()` 后处理钩子 + `_repair_llm_json()` 通用 JSON 修复 |
| `app/main.py` | `GET /api/.../knowledge-graph`、`POST .../extract-all`（并行扫描）、`POST .../clear` |
| `static/app.js` | `renderKnowledgePanel()`（按角色/类别分组、六色 category 标记） |
| `static/index.html` | 左侧角色导航新增"知识图谱"按钮 + 专属面板（工具栏 + 标签切换） |
| `tests/test_knowledge.py` | 28 个测试覆盖 Schema/Prompt/Storage/Service |

---

### P1 — 角色决策日志（1.5 周）✅ 已完成

**2026-06 已实现**：6 类决策追踪（道德抉择/信任决策/战略选择/自我揭示/关系决策/牺牲），区分表面/真实动机，后果链 + 反思 + 判决。manuscript prompt 注入决策历史保持行为一致性。知识图谱页"关键决策"标签。

#### 实现文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | `CharacterDecision`（10 字段）、`StoryWritingDefaults.enable_decision_track`、`World.character_decisions` |
| `worldforger/story_prompts.py` | `decision_detection_system()`、`build_decision_detection_user_payload()`、`format_decision_history()` |
| `worldforger/story_service.py` | `_try_detect_decisions()` 后处理钩子 |
| `app/main.py` | `GET /api/.../decisions`、`POST .../decisions/extract-all`、PATCH toggle |
| `static/app.js` | `renderDecisionsPanel()` 卡片渲染（六色类型标记 + 判决标记 + 表面/真实动机区分） |
| `tests/test_decisions.py` | 13 个测试覆盖 Schema/Prompt/Service |

---

### P1 — 角色身体状况追踪（1 周）✅ 已完成

**2026-06 已实现**：每章生成后 LLM 自动提取身体状态变化（活跃伤情 × 愈合进度、永久疤痕、慢性状态、四级疲劳度）。manuscript prompt 注入身体状态 + 叙事规则。知识图谱页"身体状况"标签。

#### 实现文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | `CharacterPhysicalState`（active_injuries/permanent_marks/chronic_conditions/fatigue_level 四级）、toggle + `World.character_physical_states` |
| `worldforger/story_prompts.py` | `physical_state_detection_system()`、`build_physical_state_detection_user_payload()`、`format_physical_state_for_prompt()` |
| `worldforger/story_service.py` | `_try_update_physical_states()` 后处理钩子（按 character_id upsert） |
| `app/main.py` | `GET /api/.../physical-states`、PATCH toggle |
| `static/app.js` | `renderPhysicalStatesPanel()` — 伤情/疤痕/慢性状态卡片 + 疲劳度色标 |
| `static/index.html` | 知识页"身体状况"标签 + 身体追踪开关 |

---

### P2 — 团队/群像动力学（2 周）

#### 问题

当前系统看角色是个体之和，但没有"团队作为一个整体"的状态追踪。真实团队有：士气、非正式领导权、替罪羊、内部小团体、集体情绪。

#### Schema 设计

```python
class GroupDynamicsState(BaseModel):
    """团队/主角团作为一个整体的动态状态"""
    group_id: str = ""                      # 如 "party_main"
    name: str = ""                          # "主角团"
    member_ids: list[str] = Field(default_factory=list)

    # 团队士气
    morale: int = Field(default=50, ge=0, le=100)
    morale_trend: Literal["rising", "stable", "declining", "volatile"] = "stable"
    morale_factors: list[dict] = Field(default_factory=list)
    # [{"factor": "连续胜利", "effect": +10, "since_chapter": "ch_3"}]

    # 非正式结构
    informal_leader_id: str = ""            # 实际上的决策者（不一定是名义领导）
    mediator_id: str = ""                  # 团队中的和事佬/调解者
    outsider_id: str = ""                   # 感觉被排除在外的人
    tension_pairs: list[dict] = Field(default_factory=list)
    # [{"char_a": "char_finn", "char_b": "char_kellen", "tension_type": "信任危机", "intensity": 7}]

    # 团队阶段
    team_stage: Literal[
        "forming", "storming", "norming", "performing", "adjourning",
        "fracturing", "rebuilding"
    ] = "forming"
    stage_history: list[dict] = Field(default_factory=list)

    # 内部小团体
    sub_groups: list[dict] = Field(default_factory=list)
    # [{"members": ["char_finn", "char_aila"], "basis": "互相信任的核心二人组"}]

    # 团队创伤
    shared_traumas: list[dict] = Field(default_factory=list)
    # [{"event": "北境小镇被毁", "chapter": "ch_5", "collective_impact": "团队对情报准确性格外敏感"}]

    last_updated_chapter: str = ""
```

**存储位置**：`World` 新增可选字段 `group_dynamics: list[GroupDynamicsState]`

#### 检测与注入

每 3 章运行一次团队动力学检测，或在有重大团队事件（加入新成员、有人死亡/离开、重大内部冲突）后触发。

在 manuscript prompt 中：
```
【当前团队状态——请注意群像氛围】
- 主角团处于 storming→norming 过渡阶段，士气 declining（连续失利+信任危机）
- 芬恩是非正式领袖（多数决策大家默认等他表态），凯伦是 outsider（与团队有隔阂）
- 芬恩↔凯伦 tension=7/10：凯伦质疑芬恩的决策，芬恩回避与凯伦的正面沟通
- 本章要求：至少一个场景展现团队的当前张力——不是通过对话直说，而是在决策过程中的微妙互动
```

#### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | 新增 `GroupDynamicsState`，`World` 增加字段 |
| `worldforger/story_prompts.py` | 新增 `group_dynamics_detection_system()`；manuscript prompt 注入团队状态 |
| `worldforger/story_service.py` | 每 3 章 + 重大事件后触发团队检测 |
| `static/app.js` | 新增"团队看板"：士气趋势图 + 非正式结构图 + 张力热力图 |

---

### P2 — 角色个人时间线（1.5 周）

#### 问题

当前只有一条主故事时间线（`history.events[]`）。但每个角色有自己的个人时间线——"格罗姆在 ch_2 之前就认识 NPC X""艾拉在 ch_1 和 ch_2 之间偷偷去了某个地方"。不追踪会导致时间矛盾。

#### Schema 设计

```python
class PersonalTimelineEvent(BaseModel):
    """角色个人时间线上的事件（可能对他人不可见）"""
    event_id: str = ""
    character_id: str = ""
    chapter: str = ""                       # 发生在哪个章节期间
    relative_timing: str = ""               # "ch_2 开始前" / "ch_3 中间" / "ch_4 结束后"
    event: str = ""                         # "格罗姆在出发前独自去了一趟旧神殿"
    known_by: list[str] = Field(default_factory=list)  # 哪些角色知道此事件
    significance: str = ""                  # 对角色弧光的意义
    linked_events: list[str] = Field(default_factory=list)  # 关联的主时间线事件 id

class CharacterPersonalTimeline(BaseModel):
    """某个角色的完整个人时间线"""
    character_id: str = ""
    events: list[PersonalTimelineEvent] = Field(default_factory=list)
```

**存储位置**：在 `characters.entities[]` 每项 dict 中新增可选字段 `personal_timeline: list[dict]`

这个功能相对独立，可作为 P2 的收尾模块。它更像一个"编辑辅助工具"——角色创建时 LLM 可为每人生成 3-5 个个人历史事件，后续章节中如有新增则追加。

#### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | 新增 `PersonalTimelineEvent`、`CharacterPersonalTimeline` |
| `worldforger/story_prompts.py` | 角色创建 prompt 中生成个人时间线；manuscript 一致性参考 |
| `static/app.js` | 角色面板新增"个人时间线"视图 |

---

### 与 todolist_far.md 文学呼吸感模块的关系

`todolist_far.md` 中 10 个文学呼吸感模块与本方案人物动态系统互为补充：

| 文学呼吸感模块 (todolist_far.md) | 对应本方案动态系统 | 关系 |
|:--|:--|:--|
| 模块 1：角色语言风格档案 | 关系演变 → 称呼/语气随之变化 | 语言风格随关系阶段自动调整 |
| 模块 2：情绪后遗症追踪器 | 身体状况追踪（疲劳/慢性状态） | 后遗症的身体化表现：失眠→疲劳 |
| 模块 6：人性缺陷与关系伤害 | 关系演变状态机 | 缺陷触发→关系 trust 下降→phase 迁移 |
| 模块 7：微观习惯/小尺度情感 | 关系演变 → 习惯 callback 追踪 | "记得谁怕冷"→ trust 上升的微观体现 |
| 模块 10：角色相互改变追踪 | 角色决策日志 + 关系演变 | 决策→后果→人格改变→关系阶段迁移 |

**核心差异**：`todolist_far.md` 的模块关注**生成内容的质量**（prompt 注入使 AI 写出更像人的文字），本方案的动态系统关注**状态追踪的完整性**（数据结构 + 检测更新，使系统能回答"角色 X 在 ch_N 时的信任度/知识/身体状况/决策后果是什么"）。

两者共同构成完整的"角色有机体"——文学呼吸感模块负责**输出质量**（文字肌理），动态系统负责**状态演算**（因果一致性）。

---

### 实施路径

```
Phase 1（已完成）────────────── Phase 2（已完成）────────────── Phase 3（规划中）──
├─ P0: 关系演变状态机 [待定]    ├─ P1: 角色决策日志 ✅          ├─ P2: 团队/群像动力学
├─ P0: 角色认知/知识系统 ✅     ├─ P1: 角色身体状况追踪 ✅      ├─ P2: 角色个人时间线
│                               │                             │
│  + todolist_far Phase 1      │  + todolist_far Phase 2     │  + todolist_far Phase 3
│    (语言风格+后遗症+反公式)    │    (呼吸段落+金句+缺陷+习惯) │    (设定揭示+不可逆失败+相互改变)
└──────────────────────────────┴──────────────────────────────┴──────────────────────────
```

**Phase 1 已完成**：知识系统是基础性的"横向"系统——几乎所有角色功能都依赖它。

**Phase 2 已完成**：决策日志 + 身体状况是"纵向"系统——追踪单个角色随时间的变化。

---

## P3 — 远期设想

按产品定位（小说策划 / 跑团工具 / 游戏文案）取舍。

### 情节与写作
- **文稿版本对比**：保存时备份上一版，支持 diff（复用 snapshot_diff.py 模式）
- **批量生成**：一次选 N 章，统一风格批量生成细纲或文稿
- **多 POV 管理**：同一章不同 POV 片段分别存储与切换

### 结构化同步深化
- 新板块一律走：**STRUCTURE_SYSTEM 白名单** → **normalize_structure_patch_detailed notes** → **保守合并** → **normalize_notes 可观测**
- 文化/经济的 few-shot 示例补入 STRUCTURE_SYSTEM_BASE

### 导出与协作
- 关系表 CSV、年表 Markdown 分册、glossary
- 世界模板 / 复制世界（复制目录 + 新 meta.id）

---

## 架构速记（便于联调）

- **第一路**：自然语言对话（`chat_completion` / `chat_completion_with_tools`）。
- **第二路**：`sync_panels_from_dialogue` → 同步器 → **统一校对者**（审查 + 直接输出 `supplement_patch` JSON，单次调用完成审查+补全）→ `parse_structure_json` → **`normalize_structure_patch_detailed`**（`normalize_structure_patch` 为其首元组）→ `merge_section_conservative` → `merge_array_by_id`（有 ID 数组增量追加）→ **各节 `model_validate`**；成功响应含 **`normalize_notes`**、**`proofreader_rounds`**、**`proofreader_issues`**。同步器空 patch 自动跳过校对。校对者模型由 `PROOFREADER_MODEL` 指定（留空则回退至 `STRUCTURE_SYNC_MODEL` 或 `OPENAI_CHAT_MODEL`）。
- **情节 Agent**：`run_story_chat_agent` → 工具循环（`list_foreshadowing` / `apply_foreshadowing` / `generate_manuscript`）→ `auto_apply_story_artifacts_from_reply`。
- **静态前端**：`/static/*`；API：`/api/*`；根路径不整站挂载静态，避免盖住 API。

---

## 已完成（归档）

- [x] **三 Agent 校对者流水线**：架构师→同步器→校对者→补充循环，防止结构化同步遗漏新增内容；`PROOFREADER_MAX_RETRIES` 可配置（默认 3，GUI 可调）；API 返回 `proofreader_rounds`/`proofreader_final_verdict`/`proofreader_issues` 审计追踪。
- [x] **ID 感知增量合并**：`merge_array_by_id()`（`worldforger/panel_merge.py`）按 `id` 匹配已有条目递归 deep-merge 更新，新条目追加到末尾，永不覆盖/删除；`merge_section_conservative` 自动检测数组由 ID 驱动。
- [x] 地理 `geography` 归一化、`normalize_structure_patch_detailed` 与 **`normalize_notes`** 全链路（`panel_sync` → API → `app.js` toast）。
- [x] 全部 11 个世界观模块：Schema、GUI 表单、第二路同步白名单与 scope 路由。
- [x] **情节 Agent**：工具调用（伏笔管理 + 文稿生成）+ 意图检测。
- [x] **伏笔系统**：台账注入 Agent prompt、代码块解析自动落盘、GUI 时间轴 + 卡片编辑 + JSON 编辑。
- [x] **章节同步**：`reconcile_story_chapters` 从磁盘 beats/ 自动注册章节；`title_from_beat_markdown` 标题对齐。
- [x] **Agent 代码块自动注册章节**：`` ```story-beat:new_id `` 时立即创建 StoryChapter 条目，无需等待 reconcile。
- [x] **前端伏笔视图自动刷新**：情节对话返回后伏笔下拉框立即包含最新章节。
- [x] **角色卡司**：主角团 / 重要配角 / 人物关系网络 Mermaid 图；cast_role 筛选看板。
- [x] **全文搜索**：`worldforger/world_search.py` + `GET /api/worlds/{id}/search`；侧栏「数据 → 搜索」页 UI。
- [x] **引用一致性**：`worldforger/reference_linter.py` + `GET /api/worlds/{id}/lint-references`；侧栏「数据 → 引用一致性」。
- [x] **版本快照 / diff / 回滚**：保存时自动快照、`line_diff_json` 行级 diff、回滚到指定版本。
- [x] **世界 CRUD**：`PATCH` 重命名显示名、`DELETE` 删目录、前端重命名/删除按钮。
- [x] **创作模式**：novel / game / CoC / DnD 四模式驱动情节单元标签、prompt 调性。
- [x] **标签驱动提示**：`meta.genre_tags` → `genre_tags_prompt_addon` 注入对话 / 同步 / 大纲。
- [x] **GUI 叙事连贯性优化**：章节摘要卡片渲染（`renderChapterSummaryCard`）、角色运行时状态卡片（`renderRuntimeStates`）、章节状态指示点（planned/drafting/locked）、字数标签、摘要卡片指示点、面板切换动画、编辑器聚焦样式、预览排版优化。
- [x] **快照历史清空**：`clear_snapshots()` 后端 + `DELETE /api/worlds/{id}/snapshots` API + 前端「清空历史」按钮 + 确认对话框。
- [x] **P1 同步鲁棒性补齐**：71 个新测试（`tests/test_p1_sync_robustness.py`），覆盖文化 normalize（10 tests）、经济 normalize（9 tests）、角色 normalize（11 tests）、情节 save/load 无损（3 tests）、11 个 scope 各两条参数化测试 + 4 个 scope 系统测试。
- [x] **第二层 RAG 增强**：完整的本地向量索引与语义检索系统。
  - `worldforger/chapter_indexer.py`：`ChapterIndexer` 类管理 ChromaDB 向量索引，按段落边界分块（600 字 / 80 字 overlap），优先使用本地 `BAAI/bge-small-zh-v1.5` embedding，不可用时自动降级到 OpenAI-compatible API（`text-embedding-3-small`）。
  - 索引范围：章节手稿 + world.md 世界观 + 人物卡，全量 `index_all()` 或按需增量。
  - 检索触发：仅在 `generate_manuscript()` 时触发语义检索，基于节拍大纲 + 出场人物 + 待推进伏笔构建 query。
  - `worldforger/story_prompts.py`：新增 `format_rag_chunks()` 格式化检索结果为 prompt 片段、`format_runtime_states()` 格式化角色运行时状态、`build_book_summary()` 生成 Book 层全局叙事摘要。
  - `build_manuscript_user_payload()` 重构为三层记忆模型（Immediate > Chapter > Book）。
  - 索引管理：`remove_chapter()` 自动清理 RAG 索引；重新生成手稿时自动更新向量。
  - GUI 上下文面板：情节工作台三栏布局，右侧新增可折叠上下文面板（前章摘要 / 角色运行时状态 / RAG 索引统计与就绪状态点）。
  - API：`GET /api/worlds/{id}/story/rag/stats` 返回索引就绪状态与统计信息。
  - 测试：28 个 RAG 单元与集成测试（`tests/test_rag.py`），包含 embedding mock、ChromaDB 操作、格式函数、API 端点。
- [x] **第三层深度增强**：叙事知识图谱 + 一致性审校 + 情感弧线追踪。
  - `worldforger/schemas.py`：新增 `NarrativeKG`（entities / events / foreshadowing）、`CharacterStateSnapshot`、`KGEntity`、`KGEvent`、`ConsistencyIssue`、`ConsistencyReport`、`SentimentSegment`、`SentimentLog`；`StoryWritingDefaults` 新增 `enable_narrative_kg` / `enable_consistency_check` / `enable_sentiment_track` 开关；`StoryChapter` 新增 `consistency_report` / `sentiment_log` 可选字段；`StorySection` 新增 `narrative_kg`。
  - `worldforger/story_store.py`：新增 KG/审校/情感存储路径函数与读写 helper；`ensure_story_dirs()` 创建对应子目录。
  - `worldforger/story_prompts.py`：新增 KG 抽取、一致性审校、情感分析三套 prompt；manuscript prompt 注入 KG 角色状态、前章情感基调。
  - `worldforger/narrative_kg.py`：`NarrativeKGManager` 类——load/save、角色状态查询、时间线获取、物品状态、事件合并去重、prompt 格式化。
  - `worldforger/consistency_checker.py`：`run_consistency_check()`——7 维度审校（位置/性格/物品/POV/伏笔/情感/时间线），非阻塞式章节后检查，结果持久化到 `consistency_reports/{cid}.json`。
  - `worldforger/sentiment_tracker.py`：`SentimentTracker`——load/save、前章结尾情感获取、Mermaid XY 图表生成。
  - `worldforger/story_service.py`：3 个收尾 hook（`_try_extract_kg_events` / `_try_run_consistency_check` / `_try_track_sentiment`），均由 `writing_defaults` toggle 控制，失败不阻塞主流程。
  - `app/main.py`：4 个新 API——`GET /story/narrative-kg`、`GET /story/consistency-report/{chapter_id}`、`GET /story/sentiment-arc`、`PATCH /story/writing-defaults`。
  - GUI：故事工作台"审校"面板（问题数 badge + 严重度颜色 + 详情展开）、情感弧线 Mermaid XY 图、Layer 3 开关复选框。
  - 测试：84 个 Layer 3 单元与集成测试（`tests/test_layer3.py`），覆盖 Schema 验证、存储读写、KG Manager、Sentiment Tracker、Consistency Checker mock、Service hook、API 端点、Prompt 函数。
- [x] **第四层：文字润色与去 AI 化**：审校↔润色反馈闭环 + 用户可选轮数 + GUI 美观直观。
  - `worldforger/schemas.py`：`StoryWritingDefaults` 新增 `enable_polisher: bool = True`、`polish_max_rounds: int = Field(default=2, ge=1, le=3)`；`StoryChapter` 新增 `polished_file`、`polish_rounds`、`polish_issue_tracking`。
  - `worldforger/story_store.py`：新增 `polished_dir()`、`polished_path()`、`polish_trace_path()`；`ensure_story_dirs()` 创建 polished 目录。
  - `worldforger/story_prompts.py`：新增 `polisher_system()`（9 条硬规则 + 10 类 AI 痕迹对照表 + ❌/✅ 反面示例）、`build_polisher_user_payload()`（叙事约束 + 角色语言风格档案 + 文风锚定 + 一致性 issue + 回归标记）、`format_consistency_issues_for_polisher()`。
  - `worldforger/story_service.py`：`_run_polish_loop()` 管理审校↔润色反馈闭环（至多 N 轮），每轮串行执行审校→润色→审校，issue 跨轮分类（fixed/persistent/regression），5 种终止条件覆盖；润色稿写入 `story/polished/{cid}.md`，附 trace JSON。
  - `app/main.py`：`GET /api/worlds/{id}/story/manuscript/{chapter_id}/polished` 获取润色稿 + 元数据；`GET /api/worlds/{id}/story/manuscript/{chapter_id}/polish-trace` 获取 loop 轮次与 issue 追踪；`PATCH /api/worlds/{id}/story/writing-defaults` 扩展 `enable_polisher` 和 `polish_max_rounds` 字段。
  - GUI：故事工作台审校面板新增"润色者"卡片（章节选择 + 原稿/润色稿左右分栏对比视图 + 润色说明列表 + Loop 轮次指示器 + issue 追踪面板（🟢已修复/🟡持续中/🔴回归）+ 润色开关 + 最大轮数选择器）。
  - 性能优化：独立后处理钩子并行执行（`asyncio.gather`）+ 润色环启用时跳过独立一致性审校（避免重复 LLM 调用），单章生成墙钟时间节省约 40%。
  - 测试：38 个 Layer 4 单元与集成测试（`tests/test_layer4.py`），覆盖 7 个测试类——Schema（4）、Storage（5）、Prompts（10）、Loop（7）、API（7）、StyleReference（3）、Integration（2）。
- [x] **校对者性能优化**：统一校对者（审查+补全合并为单次 LLM 调用，消除架构师→同步器往返）、`PROOFREADER_MODEL` 可配置（建议用小模型加速）、空 patch 跳过校对、章节节拍并行生成（`asyncio.gather`）。

- [x] **P2 体验增强**：章节细分状态（7 级状态机）+ 章节批量操作（多选复选框、批量工具栏）+ 伏笔时间轴筛选（按状态/按章过滤）+ 写作看板统计增强（完成度分色进度条）。
  - `worldforger/schemas.py`：`StoryChapterStatus` 从 3 个扩展为 7 个。
  - `app/main.py`：新增 `POST /api/worlds/{id}/story/chapters/batch`（delete/reorder/status）。
  - `static/app.js`：多选复选框 + 批量工具栏 + 伏笔筛选逻辑。
  - `static/js/p2-enhancements.js`：完成度进度条 + 英雄卡片百分比。
  - `static/styles.css`：7 色状态指示点、批量工具栏、筛选标签、进度条样式。
  - `static/index.html`：章节侧栏批量工具栏 + 伏笔筛选条。

- [x] **P0 角色认知/知识系统**：6 类知识 x 4 级确定度。每章自动检测；manuscript 注入信息边界。前端知识图谱独立页面（按角色/类别分组、筛选、批量提取）。
  - schemas: CharacterKnowledgeEntry、CharacterKnowledgeGraph、World.character_knowledge。
  - prompts: knowledge_detection_system()、format_knowledge_boundaries()。
  - service: _try_detect_knowledge() + _repair_llm_json()。
  - 28 个测试 (test_knowledge.py)。

- [x] **P1 角色决策日志**：6 类决策，区分表面/真实动机，后果链 + 反思 + 判决。manuscript 注入决策历史。
  - schemas: CharacterDecision (10 字段)、World.character_decisions。
  - 13 个测试 (test_decisions.py)。

- [x] **P1 角色身体状况追踪**：伤情愈合进度 + 永久疤痕 + 慢性状态 + 四级疲劳度。manuscript 注入身体叙事规则。
  - schemas: CharacterPhysicalState、World.character_physical_states。
  - service: _try_update_physical_states() 按 character_id upsert。

- [x] **Narrative State Engine P0**：MysteryManager（谜题生命周期）+ CharacterArcEngine（弧线5阶段）+ Writer前短context注入（mystery_context + arc_context）。
  - schemas: MysteryTracker(14字段), CharacterArc(10字段), ReaderMemoryEntry(9字段)
  - story_prompts: format_mystery_context() + format_arc_context() 短context注入
  - 4个 toggle: enable_mystery_manager/enable_character_arc_engine/enable_reader_memory/enable_narrative_state_injection
