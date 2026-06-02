---
name: mcw-dev
description: Magic Creater World 项目开发指南。当用户要求开发新功能、修改后端/前端/测试时使用。
---

# Magic Creater World — 开发 Skill

## 项目概述

Magic Creater World 是一个世界观构建 + 长篇小说写作平台。后端用 Python/FastAPI，前端用 vanilla JS/CSS/HTML，LLM 用 OpenAI-compatible API。

## 关键技术栈

- **后端**: Python 3.10+ / FastAPI / Pydantic v2 / uvicorn
- **前端**: Vanilla JS (ES modules) / CSS / Material Symbols icons / Chart.js / vis.js / marked + DOMPurify
- **LLM**: OpenAI-compatible API (Paratera `DeepSeek-V4-Pro/Flash`)
- **存储**: JSON 文件 (world.json) + Markdown 文件 (章节/细纲/粗纲) + ChromaDB (RAG 向量索引) + SQLite (ChromaDB 内部)
- **测试**: pytest + pytest-asyncio + unittest.mock

## 核心架构

```
用户 (GUI)
  ├─ 世界观构建 → POST /chat → LLM 对话 → 第二路结构化同步
  ├─ 人物生成   → POST /character-chat → characters 节
  ├─ 情节构建   → POST /story-chat → 工具调用 + 代码块自动落盘
  └─ 各模块表单 → 本地编辑 → 保存 → world.json
```

## 目录结构

```
worldforger/
  schemas.py          # 所有 Pydantic 模型 (World, StoryChapter, etc.)
  story_service.py    # 情节生成核心逻辑 (generate_manuscript, hooks)
  story_prompts.py    # 所有 LLM prompt 函数
  story_agent.py      # 故事对话 Agent (tool calling)
  story_store.py      # 情节文件读写 (manuscript_path, beat_path, etc.)
  world_store.py      # 世界 CRUD (load_world, save_world, delete_world)
  llm.py              # LLM API 调用 (chat_completion, stream, tools)
  config.py           # Settings (API key, model, paths)
  chapter_indexer.py  # ChromaDB RAG 索引
  consistency_checker.py
  sentiment_tracker.py
  narrative_kg.py
  structure_normalize.py  # 第二路同步 JSON 归一化
  panel_sync.py       # 对话→面板同步
  creative_modes.py   # novel/game/coc/dnd 模式

app/
  main.py             # FastAPI 路由 (所有 /api/* 端点)

static/
  app.js              # 前端主逻辑 (~8500 lines, ES module)
  index.html          # 主 HTML (~1500 lines)
  styles.css          # 全局 CSS (~7500 lines)
  js/
    utils.js          # API helper, toast, escapeHtml, etc.
    state.js          # 全局 state 对象
    p2-enhancements.js # 统计面板、关系网络 vis.js 渲染

tests/
  test_story_api.py   # 情节/文稿 API 测试
  test_layer3.py      # KG/审校/情感 测试
  test_layer4.py      # 润色 Loop 测试
  test_knowledge.py   # 知识图谱 测试
  test_decisions.py   # 决策日志 测试
  ...
```

## 开发模式

### 新增 Schema 字段

1. 在 `schemas.py` 添加 Pydantic 模型
2. 在 `StoryWritingDefaults` 添加 `enable_xxx: bool = True` toggle
3. 在 `World` model 添加字段（default_factory）
4. 旧数据向后兼容：字段必须有默认值，不破坏已有 world.json

### 新增后处理 Hook

1. `story_prompts.py`：添加 `xxx_system()` + `build_xxx_user_payload()` 两个 prompt 函数
2. 可选：添加 `format_xxx_for_prompt()` 注入 manuscript prompt
3. `story_service.py`：添加 `_try_xxx()` async 函数（`→ str` 返回错误描述，不抛异常）
4. 在 `generate_manuscript()` 和 `generate_manuscript_stream()` 的 post_hooks 列表中添加调用（两处都要加）
5. `app/main.py`：添加 GET API 端点 + PATCH toggle 字段 + extract-all POST 端点

### 新增前端页面/标签

1. `index.html`：添加 section panel + nav button（`data-view="xxx"`）
2. `app.js`：
   - 在 `VIEW_SCOPE_MAP` 添加 view→scope 映射
   - 在 `isCharacterPanelView()` 等函数中添加 view name
   - 在 `switchView()` 中添加渲染调用
   - 添加 render 函数
3. `styles.css`：添加页面样式

### API 端点模式

```python
@app.get("/api/worlds/{world_id}/xxx")
def api_get_xxx(world_id: str):
    w = load_world(world_id)  # or _story_world_or_404
    return {"world_id": world_id, "data": ...}

@app.post("/api/worlds/{world_id}/xxx/extract-all")
async def api_extract_all_xxx(world_id: str):
    # Scan existing chapters
    # parallel with Semaphore(3) + sleep(3) for rate limiting
    # return {"ok": True, "total_new": N, "world": w.model_dump(...)}
```

### 前端 API 调用

```javascript
// GET
const res = await api(`/api/worlds/${state.world.meta.id}/xxx`);
// POST
const res = await api(`/api/worlds/${state.world.meta.id}/xxx`, { method: "POST", body: JSON.stringify(payload) });
state.world = res.world;          // 更新全局状态
storyMetaToForm();                // 刷新表单
renderXxxPanel();                 // 刷新特定面板
```

## LLM Prompt 编写

### 提示词模板

```python
def xxx_system() -> str:
    return (
        "你是XXX Agent，负责XXX。\n"
        "你只需要输出 JSON，不要输出任何其他文字。\n"
        "JSON 格式：\n"
        '{"key": [...]}\n\n'
        "注意：\n"
        "- 具体规则1\n"
        "- 具体规则2\n"
    )
```

### 关键教训

1. **JSON 解析需容错**：LLM 可能输出代码围栏、尾随逗号、未转义换行符。使用 `_repair_llm_json()` 统一修复
2. **Prompt 长度控制**：DeepSeek 对超长 prompt (>5000 chars total) 返回空响应。文稿截断 3000-4000 字符
3. **并发限流**：`Semaphore(3)` + `sleep(3)` 避免 API 限流
4. **拒绝检测**：回复 <100 字且含"无法/不能/抱歉"时自动重试
5. **模型写作拒绝**：system prompt 开头加"你是专业作家，直接输出，不要拒绝"

## 测试模式

### 测试文件结构

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def sample_world():
    return World(meta=Meta(id="test_xxx", name="测试"), ...)

class TestXxxSchema:     # 7 个 Schema 验证测试
class TestXxxPrompts:    # 4 个 Prompt 函数测试
class TestXxxService:    # 5-9 个 Hook 测试 (mock chat_completion)
class TestXxxStorage:    # 3 个读写测试
class TestXxxIntegration: # 2 个集成测试
```

### Mock 模式

```python
mock_reply = json.dumps({"key": [...]}, ensure_ascii=False)
with patch("worldforger.story_service.chat_completion", new=AsyncMock(return_value=mock_reply)):
    err = await _try_xxx(world, "ch_id", "test")
    assert err == ""
    assert len(world.xxx) == expected_count
```

### 常见测试失败

1. **`mock_chat.call_count` 不对**：新增 hook → 增加一次 LLM 调用 → 旧测试的 `call_count == 3` 需改为 4，或 disable 新 toggle
2. **e2e 测试 flaky**：`test_e2e_generate_chapter_full_pipeline` 和 `test_e2e_sync_proofread_complete_loop` 偶发超时
3. **运行命令**：`E:/ananconda/envs/Agent/python.exe -m pytest tests/ -q --deselect tests/test_e2e.py::test_e2e_generate_chapter_full_pipeline --deselect tests/test_e2e.py::test_e2e_sync_proofread_complete_loop`

## 常见陷阱

1. **不要覆盖 manuscript_path**：润色结果只写 `polished_path`，原稿保留以便 diff
2. **World 字段必须是 Pydantic model**：不要用 `list[dict]`，用 Pydantic 模型列表
3. **generate_manuscript 返回 3-tuple**：`(reply, hook_errors, timing_breakdown)`，story_agent 解包也需 3 个值
4. **JSON 持久化用 `write_json_file`**：story_store.py 已有 `read_json_file`/`write_json_file`
5. **前端 JS 用 ES modules**：`import { $, toast, api } from "./utils.js"` — 函数不自动全局可用，需 `window.xxx = xxx` 暴露给 HTML onclick
6. **CSS 避免重复规则**：编辑前 grep 检查是否已有同名选择器
7. **Windows 文件锁**：ChromaDB `PersistentClient` 需 `close_world()` 释放后才能删除目录
8. **faction_entity 序列化警告**：测试中 dict → FactionEntity 有 Pydantic 警告，不影响功能