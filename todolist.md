# Magic Creater World — 任务与路线图

> 本地调试（与终端一致）：  
> `& E:/ananconda/envs/Agent/python.exe d:/Magic_Creater_World/run.py`  
> 可加 `--no-browser`、`--reload` 等参数。  
> 测试：`E:/ananconda/envs/Agent/python.exe -m pytest tests -q`

---

## 当前状态（最近一次核对）

- **pytest**：**`113 passed`**（使用 `E:/ananconda/envs/Agent/python.exe`）。
- **全部 11 个世界观模块**（地理/生态/境界/属性/物品/派系/文化/历史/经济/角色/情节）已完成 **Schema + GUI 表单 + 第二路结构化同步**。
- **情节 Agent**：工具调用（伏笔管理 + 文稿生成）+ 意图检测 + 代码块自动落盘粗纲/细纲/文稿/伏笔，全部可用。
- **角色卡司**：主角团 / 重要配角 / 人物关系网络 Mermaid 图，全部可用。
- **工具链**：全文搜索、引用一致性校验、版本快照 diff 与回滚，全部可用。

---

## 当前架构总览

```
用户 (GUI)
  │
  ├─ 世界观构建 ──→ POST /chat
  │                   └─ (可选) POST /sync-panels-from-chat → 第二路合并
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
| story scope 第二路同步测试 | 构造含 story 数据的对话回复，断言 `/sync-panels-from-chat` scope=story 成功合并 summary/chapters/foreshadowing | ▢ |
| 伏笔 Apply API 集成测试 | 调用 `POST /story/foreshadowing/apply`，验证 upsert/resolve/delete 各操作后 world.json 正确 | ▢ |
| Agent 工具调用全流程测试 | mock `chat_completion_with_tools` 返回指定工具调用，验证 `run_story_chat_agent` 的正确落盘 | ▢ |
| 代码块自动注册章节测试 | 模拟 `` ```story-beat:new_id `` 回复，验证章节自动注册 + 标题从 beat Markdown 提取 | ✅ 已补 |
| 前端伏笔视图刷新测试 | 手动验证：Agent 对话建新章后，伏笔页下拉框是否立即包含该章 | ✅ 已补 |

---

## P1 — 同步鲁棒性补齐

各模块的 normalize 成熟度不同，部分模块缺少回归测试。

| 任务 | 说明 | 状态 |
|:--|:--|:--|
| 文化/宗教同步回归测试 | `_normalize_cultures_dict` 路径测试（实体数组/单对象/别名、relations 归一） | ▢ |
| 经济同步回归测试 | `_normalize_economy_dict` 路径测试（currencies/markets/trade_routes/trade_goods 各数组） | ▢ |
| 角色 normalize 完整覆盖 | `_normalize_characters_dict` 边界用例（entities 单对象、cast_role 非法值、relations target_id 缺失） | ▢ |
| 情节 save/load 状态保持 | 保存世界后再加载，story.chapters / foreshadowing 字段无损 | ▢ |
| 第二路「仅同步当前页」各 scope 回归 | 每个 scope 值（geography/ecology/.../story）至少一条简单测试 | ▢ |

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
- **第二路**：`sync_panels_from_dialogue` → `parse_structure_json` → **`normalize_structure_patch_detailed`**（`normalize_structure_patch` 为其首元组）→ `merge_section_conservative` → **各节 `model_validate`**；成功响应含 **`normalize_notes`**。
- **情节 Agent**：`run_story_chat_agent` → 工具循环（`list_foreshadowing` / `apply_foreshadowing` / `generate_manuscript`）→ `auto_apply_story_artifacts_from_reply`。
- **静态前端**：`/static/*`；API：`/api/*`；根路径不整站挂载静态，避免盖住 API。

---

## 已完成（归档）

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
