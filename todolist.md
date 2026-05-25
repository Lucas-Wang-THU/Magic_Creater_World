# Magic Creater World — 任务与路线图

> 本地调试（与终端一致）：  
> `& E:/ananconda/envs/Agent/python.exe d:/Magic_Creater_World/run.py`  
> 可加 `--no-browser`、`--reload` 等参数。  
> 测试：`E:/ananconda/envs/Agent/python.exe -m pytest tests -q`

---

## 当前状态（最近一次核对）

- **pytest**：**`337 passed, 3 deselected`**（337 tests 全部通过；含 84 个 Layer 3 测试；3 个慢速 LLM 测试需 API key；使用 `E:/ananconda/envs/Agent/python.exe`）。
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

| 优先级 | 项 | 说明 |
|:--:|:--|:--|
| P2 | **world.md 导出包含情节** | 目前 `markdown_export` 不含 story 节的章节列表与伏笔台账；导出追加 `## 情节` 小节 | ▢ |
| P2 | **章节批量操作** | 拖拽排序、多选删除、批量重编号 | ▢ |
| P2 | **伏笔时间轴交互优化** | 拖拽分配章节、状态切换动画、筛选视图 | ▢ |
| P2 | **写作看板统计** | 各章字数趋势、伏笔 open/resolved 比例、完成度进度条 | ▢ |
| P2 | **章节细分状态** | 当前 `planned | drafting | locked` 三级，可考虑扩展 `revising`、`done` 等 | ▢ |

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
| 情感曲线可视化 | 前端 Mermaid 图表：各章情感倾向走势 | ✅ |

---

### 推荐实施路径

```
第一轮 (已完成) ──────── 第二轮 (已完成) ──────── 第三轮 (已完成)
├─ A. 章节摘要卡片       ├─ D. RAG 语义检索        ├─ F. 叙事知识图谱
├─ B. 人物运行时状态     ├─ E. 多粒度分层记忆      ├─ G. 一致性审校 Agent
└─ C. 节拍衔接校验                                  └─ H. 情感弧线追踪
```

**第一轮已显著改善**：A+B+C 改动集中在 `story_service.py`、`story_prompts.py`、`story_store.py`、`schemas.py` 四个文件。

**第二轮已实现质的飞跃**：D+E 将"盲目截断"替换为"智能检索"，是解决长篇小说跨章节遗忘的关键。

**第三轮已完成**：F+G+H 实现了叙事知识图谱、7 维度一致性自动审校和情感弧线追踪，达到接近人类编辑水平的叙事一致性保障。

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

### P0 — 角色认知/知识系统（2 周）

#### 问题

当前系统不追踪"谁知道什么"。导致：
- 角色在对话中不经意说出不该知道的信息
- 同一个秘密被反复"首次揭露"
- 无法利用信息差制造戏剧张力（读者知道 A 是叛徒，B 不知道——但系统不追踪这个）

#### Schema 设计

```python
class CharacterKnowledgeEntry(BaseModel):
    """单条知识——某个角色知道某件事"""
    knowledge_id: str = ""                  # 如 "know_traitor_identity"
    character_id: str = ""                  # 谁知道
    topic: str = ""                         # "芬恩是叛徒" / "翠绿议会的真正起源"
    category: Literal[
        "secret",          # 秘密（只有特定角色知道）
        "personal_history", # 个人历史（童年经历、创伤）
        "world_lore",      # 世界设定知识
        "plan",            # 计划/策略（某角色知道的行动计划）
        "suspicion",       # 怀疑（不确定但有所察觉）
        "misunderstanding", # 误解（角色以为是真的但其实是假的）
    ] = "secret"
    certainty: Literal["knows_for_sure", "strongly_suspects", "vaguely_senses", "believes_wrongly"] = "knows_for_sure"
    source_chapter: str = ""                # 从哪章获得此知识
    source_detail: str = ""                 # 如何获得的："偷听了议会对话"
    shared_with: list[str] = Field(default_factory=list)
    # [{"char_id": "char_b", "chapter": "ch_5", "method": "主动告知"}]
    is_still_true: bool = True              # 是否仍是真相（可能后来的事件改变了事实）
    notes: str = ""

class CharacterKnowledgeGraph(BaseModel):
    """全局角色知识图谱"""
    entries: list[CharacterKnowledgeEntry] = Field(default_factory=list)
    # 视角查询：GET /knowledge?character=char_a → 该角色知道的全部信息
    # 秘密查询：GET /knowledge?topic=traitor → 谁知道/不知道此信息
```

**存储位置**：`World` 新增可选字段 `character_knowledge: CharacterKnowledgeGraph`

#### 检测与更新

每章生成后：
```
【角色知识检测】
检查本章正文中：
1. 是否有角色获得了新信息？（谁、什么信息、从什么来源、确定程度）
2. 是否有角色分享了信息？（谁告诉了谁什么）
3. 是否有角色基于错误信息行动？（记录下来——这是戏剧冲突来源）
4. 是否有角色"不应该知道但说了出来"？（标注为潜在的一致性 bug）

对每个检测到的知识变化，创建或更新 KnowledgeEntry。
```

#### 注入策略

在 manuscript prompt 中追加：
```
【本章各角色所知信息（请严格遵守信息边界）】
- 艾拉 KNOWS: 芬恩的真实身份（ch_2 偷听得知）、裂隙的初步情报
- 艾拉 DOES NOT KNOW: 凯伦在 ch_3 与敌人的秘密交易
- 芬恩 KNOWS: 艾拉在隐瞒某事（suspicion, ch_4 察觉到异常）
- 芬恩 DOES NOT KNOW: 艾拉隐瞒的具体内容

【信息差叙事规则】
1. 角色不能说出ta不知道的信息
2. 如果 X 不知道 Y，X 的对话和内心独白不应含有 Y
3. 利用信息差制造张力：读者知道但角色不知道的，用角色的"无知"行为体现
4. 误解（believes_wrongly）是好的戏剧素材——不要急于纠正
```

#### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | 新增 `CharacterKnowledgeEntry`、`CharacterKnowledgeGraph`，`World` 增加字段 |
| `worldforger/story_prompts.py` | 新增 `knowledge_detection_system()`；manuscript prompt 注入知识边界 |
| `worldforger/story_service.py` | 章节后知识检测 + 更新 |
| `worldforger/panel_sync.py` | 同步器 characters scope 支持 knowledge entries |
| `static/app.js` | 新增"角色知识"面板：按角色视角筛选 + 信息差高亮 + 秘密传播图 |

---

### P1 — 角色决策日志（1.5 周）

#### 问题

角色在 ch_2 做了一个关键选择（"放弃救 NPC 以获取情报"），到 ch_8 时行为模式已变，但无系统追踪该决策的长期影响。导致角色行为看似随机——没有决策→后果→信念变化的因果链。

#### Schema 设计

```python
class CharacterDecision(BaseModel):
    """角色的关键决策及其后果链"""
    decision_id: str = ""
    character_id: str = ""
    chapter: str = ""
    summary: str = ""                       # "艾拉选择不救 NPC 莫里斯，以获取翠绿议会的关键情报"
    decision_type: Literal[
        "moral_choice",       # 道德抉择（牺牲谁/什么）
        "trust_decision",     # 信任决策（相信/拒绝某人）
        "strategic_choice",   # 战略选择（走哪条路）
        "self_revelation",    # 自我揭示（角色的某个选择暴露了ta真正的价值观）
        "relationship_choice", # 关系决策（切断/建立/修复关系）
        "sacrifice",          # 牺牲（失去某物以换取某物）
    ] = "moral_choice"
    options_considered: list[str] = Field(default_factory=list)
    # ["A: 冲进去救莫里斯但失去情报", "B: 放弃莫里斯获取情报"]
    option_chosen: str = ""                 # "B"
    stated_reason: str = ""                 # 角色自己说的理由
    actual_reason: str = ""                 # 真实原因（可能不同——角色会自我欺骗）

    # 后果链
    immediate_consequences: list[str] = Field(default_factory=list)
    # ["莫里斯死亡", "获得翠绿议会情报", "凯伦对艾拉的信任降低"]
    long_term_consequences: list[dict] = Field(default_factory=list)
    # [{"chapter": "ch_5", "effect": "艾拉开始回避需要牺牲他人的决策", "type": "personality_shift"}]

    # 角色的反思
    reflections: list[dict] = Field(default_factory=list)
    # [{"chapter": "ch_4", "reflection": "艾拉梦到莫里斯", "type": "emotional"}]

    # 是否已被证明是错误/正确的？
    outcome_verdict: Literal["pending", "proved_right", "proved_wrong", "ambiguous", "irrelevant"] = "pending"
```

**存储位置**：在 `characters.entities[]` 每项 dict 中新增可选字段 `decisions: list[dict]`

#### 检测时机

每章生成后检测新的关键决策（与 aftermath 检测合并调用）。不要求每章都有新决策——关键决策以 3-5 章为单位出现。

#### Prompt 注入

```
【角色决策历史——行为一致性参考】
艾拉的关键决策：
- ch_2：放弃莫里斯获取情报（moral_choice）→ 长期影响：对牺牲类决策犹豫
  → 本章提示：如果艾拉面临"牺牲 X 换取 Y"的情境，她的犹豫应比普通角色更明显
- ch_5：主动向芬恩坦白身份（self_revelation）→ 说明艾拉在信任方面有进展
  → 本章提示：艾拉的对人态度应有微妙变化——更愿意冒信任风险
```

#### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | 新增 `CharacterDecision` |
| `worldforger/story_prompts.py` | 新增 `decision_detection_system()`；manuscript prompt 注入决策历史 |
| `worldforger/story_service.py` | 章节后决策检测 |
| `static/app.js` | 角色面板新增"关键决策"时间轴 + 后果链可视化 |

---

### P1 — 角色身体状况追踪（1 周）

#### 问题

角色在 ch_1 手臂中箭，ch_2 若无其事地攀岩——没有"伤病史"追踪。真正的身体承载历史：旧伤在雨天隐隐作痛、疤痕让人不敢穿短袖、长期疲劳导致判断力下降。

#### Schema 设计

```python
class CharacterPhysicalState(BaseModel):
    """角色身体状况——身体承载叙事历史"""
    character_id: str = ""

    # 活跃伤情
    active_injuries: list[dict] = Field(default_factory=list)
    # [{"injury_id": "inj_001", "type": "箭伤", "location": "左肩",
    #   "caused_in_chapter": "ch_1", "severity": "moderate",
    #   "healing_progress": "60%", "functional_impact": "左手抬不过肩",
    #   "last_mentioned_chapter": "ch_3"}]

    # 永久疤痕/改变
    permanent_marks: list[dict] = Field(default_factory=list)
    # [{"mark_id": "scar_001", "type": "疤痕", "location": "左前臂",
    #   "origin": "ch_1 箭伤愈合", "visibility": "noticeable",
    #   "character_feeling": "不愿被人看到"}]

    # 慢性状态
    chronic_conditions: list[dict] = Field(default_factory=list)
    # [{"condition": "左肩旧伤——阴雨天酸痛", "since_chapter": "ch_2"}]

    # 当前身体状态
    fatigue_level: Literal["rested", "tired", "exhausted", "collapse_imminent"] = "rested"
    general_condition: str = ""
    # "连续三章高强度战斗，身体处于透支边缘"

    last_updated_chapter: str = ""
```

**存储位置**：在 `characters.entities[]` 每项 dict 中新增可选字段 `physical_state: dict`

#### 更新与注入

轻量——不需要独立 LLM 调用。在 manuscript prompt 中要求模型自己标注身体状态变化：
```
【角色身体状况——请让身体承载历史】
- 芬恩：左肩箭伤（ch_1，愈合约 60%，左手抬不过肩）、疲劳度=tired
  → 本章任何涉及左臂的动作应有不适感（一句即可）
  → 如果有人拍他左肩，他应该缩一下
- 艾拉：无伤，但疲劳度=exhausted（ch_4-5 连续战斗+失眠）
  → 决策速度应变慢，可能因为疲劳犯小错误

【身体叙事规则】
1. 旧伤不是背景装饰——它真的影响行动
2. 疲劳会影响判断力——疲劳的角色更容易出错
```

#### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | 新增 `CharacterPhysicalState` |
| `worldforger/story_prompts.py` | manuscript prompt 注入身体状态 |
| `worldforger/story_service.py` | 章节后从正文提取身体状态变化（复用已有 aftermath 提取流程） |
| `static/app.js` | 角色卡片展示活跃伤情 + 身体状况 |

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
Phase 1（2-3 周）──────────── Phase 2（2-3 周）──────────── Phase 3（2-3 周）──
├─ P0: 关系演变状态机          ├─ P1: 角色决策日志           ├─ P2: 团队/群像动力学
├─ P0: 角色认知/知识系统       ├─ P1: 角色身体状况追踪       ├─ P2: 角色个人时间线
│                               │                             │
│  + todolist_far Phase 1      │  + todolist_far Phase 2     │  + todolist_far Phase 3
│    (语言风格+后遗症+反公式)    │    (呼吸段落+金句+缺陷+习惯) │    (设定揭示+不可逆失败+相互改变)
└──────────────────────────────┴──────────────────────────────┴──────────────────────────
```

**Phase 1 策略**：关系演变 + 认知系统是两个基础性的"横向"系统——几乎所有角色功能都依赖它们。优先做这两个，后续模块（决策日志、身体追踪、团队动力学）可以建立在它们之上。

**Phase 2 策略**：决策日志 + 身体状况是"纵向"系统——追踪单个角色随时间的变化。它们依赖 Phase 1 的关系和知识系统来提供上下文。

**Phase 3 策略**：团队动力学 + 个人时间线是"全局"系统——需要 Phase 1+2 的数据累积才能发挥最大价值。

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
- **第二路**：`sync_panels_from_dialogue` → 同步器 → 校对者（`_run_proofreader` → `verdict: ok|retry`）→（如 retry）架构师补充（`_run_architect_supplement`）→ 同步器再提取 → 循环至多 N 轮 → `parse_structure_json` → **`normalize_structure_patch_detailed`**（`normalize_structure_patch` 为其首元组）→ `merge_section_conservative` → `merge_array_by_id`（有 ID 数组增量追加）→ **各节 `model_validate`**；成功响应含 **`normalize_notes`**、**`proofreader_rounds`**、**`proofreader_issues`**。
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
