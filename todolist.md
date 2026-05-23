# Magic Creater World — 任务与路线图

> 本地调试（与终端一致）：  
> `& E:/ananconda/envs/Agent/python.exe d:/Magic_Creater_World/run.py`  
> 可加 `--no-browser`、`--reload` 等参数。  
> 测试：`E:/ananconda/envs/Agent/python.exe -m pytest tests -q`

---

## 当前状态（最近一次核对）

- **pytest**：**`226 passed, 3 deselected`**（229 tests 全部通过；3 个慢速 LLM 测试需 API key；使用 `E:/ananconda/envs/Agent/python.exe`）。
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
| KG Schema | 在 `schemas.py` 新增 NarrativeKG 模型（entities / events / foreshadowing） | ▢ |
| KG 存储 | 新增 `worldforger/narrative_kg.py`：读写 `narrative_kg.json` | ▢ |
| 事件抽取 | 章节生成后自动从正文抽取事件和状态变化，更新 KG | ▢ |
| KG 查询注入 | 生成前查询 KG 获取当前角色状态，注入 prompt | ▢ |

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
| 审校 prompt | 新增 `story_prompts.consistency_check_system()` 和 user payload | ▢ |
| 审校调用 | `generate_manuscript()` 完成后运行审校，结果写入章节的 `author_notes` | ▢ |
| 前端展示 | 审校结果在章节目录中可视化展示（问题数 badge + 详情展开） | ▢ |
| 自动修复建议 | 审校 Agent 输出可选的修复建议，用户可选择应用 | ▢ |

#### H. 情感弧线追踪

每章生成后，用轻量情感分析标记各段落的情感倾向（正面/负面/紧张/舒缓）。生成下一章时参考上一章结尾的情感状态，确保过渡自然。

| 任务 | 说明 | 状态 |
|:--|:--|:--|
| 情感分析模块 | 新增 `worldforger/sentiment_tracker.py`：调用 LLM 或 textblob 逐段标注情感 | ▢ |
| 情感注入 | 修改 manuscript 生成 prompt，注入上一章结尾情感状态 | ▢ |
| 情感曲线可视化 | 前端 Mermaid 图表：各章情感倾向走势 | ▢ |

---

### 推荐实施路径

```
第一轮 (已完成) ──────── 第二轮 (已完成) ──────── 第三轮 (6-8周)
├─ A. 章节摘要卡片       ├─ D. RAG 语义检索        ├─ F. 叙事知识图谱
├─ B. 人物运行时状态     ├─ E. 多粒度分层记忆      ├─ G. 一致性审校 Agent
└─ C. 节拍衔接校验                                  └─ H. 情感弧线追踪
```

**第一轮已显著改善**：A+B+C 改动集中在 `story_service.py`、`story_prompts.py`、`story_store.py`、`schemas.py` 四个文件。

**第二轮已实现质的飞跃**：D+E 将"盲目截断"替换为"智能检索"，是解决长篇小说跨章节遗忘的关键。

**第三轮是天花板**：F+G+H 需要较大工程投入，实现接近人类编辑水平的叙事一致性保障。

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
