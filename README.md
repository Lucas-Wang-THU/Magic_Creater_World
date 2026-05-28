<div align="center">

![Magic Creater World — 横幅](docs/readme-hero.svg)

**把对话里的灵感，落成可保存、可导出的完整世界。**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063?style=flat-square&logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![pytest](https://img.shields.io/badge/tests-pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white)](https://pytest.org/)
[![OpenAI Compatible](https://img.shields.io/badge/LLM-OpenAI%20Compatible-412991?style=flat-square&logo=openai&logoColor=white)](https://platform.openai.com/)

</div>

<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/语言-中文-red?style=flat-square" alt="中文" /></a>
  <a href="README.en.md"><img src="https://img.shields.io/badge/Language-English-blue?style=flat-square" alt="English" /></a>
</p>

---

## 目录

- [快速开始](#快速开始)
- [它能做什么](#它能做什么)
- [界面导览](#界面导览)
- [整体流程](#整体流程)
- [写作多智能体协同](#写作多智能体协同)
- [功能一览](#功能一览)
- [产品地图](#产品地图工作台--worldjson)
- [环境要求与安装](#环境要求与安装)
- [配置](#配置)
- [启动服务](#启动服务)
- [数据目录结构](#数据目录结构)
- [API 摘要](#api-摘要)
- [测试](#测试)
- [后续路线](#后续路线)
- [更多文档](#更多文档)

---

## 快速开始

### Windows 一键部署（推荐）

```
1. 双击 setup.bat   → 自动检测环境、安装依赖、配置 .env
2. 双击 launch.bat  → 启动服务，浏览器自动打开
```

> 可选：右键 `launch.bat` → 发送到桌面快捷方式 → 右键快捷方式 → 属性 → 更改图标 → 选择 `icon.ico`，即可从桌面一键启动。

### 手动安装

```bash
# 1. 创建虚拟环境（推荐）
python -m venv .venv

# Linux / macOS 激活
source .venv/bin/activate

# Windows 激活
.venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key
cp .env.example .env          # Linux / macOS
copy .env.example .env        # Windows
# 编辑 .env，填入 PARATERA_API_KEY

# 4. 启动
python run.py
```

浏览器自动打开 `http://127.0.0.1:8765`，即可开始构建你的世界观。

---

## 它能做什么

**Magic Creater World (MCW)** 是一个本地优先、AI 辅助的虚构世界观构建工作台。它将 LLM 对话的灵感转化为可持久化、可导出的结构化数据。

<div align="center">

| ✨ 核心特性 | 说明 |
|:--|:--|
| 📌 **单一事实源** | 磁盘上的 `world.json` 为权威结构；`world.md` 为可读导出 |
| 💬 **对话构建** | 与"世界观架构师"自然语言交流，4 种创作模式（小说 / 游戏 / CoC / DnD） |
| 🧩 **结构化同步 + 校对者** | 三 Agent 流水线：架构师→同步器→校对者→补充循环，自动抽取 JSON 补丁，按 ID 增量合并进表单 |
| 🗺️ **11 个世界观模块** | 地理 · 生态 · 境界 · 属性 · 物品 · 文化 · 派系 · 历史 · 经济 · 角色 · 故事 |
| 📊 **关系可视化** | vis.js 交互式人物关系网络（拖拽/缩放）；Mermaid 图表：技能树、职业晋升图、时间线、因果链 |
| 🧠 **语义记忆 (RAG)** | 本地向量索引（ChromaDB），智能检索前文片段保持叙事连贯性 |
| 🔍 **数据工具** | 全文搜索、引用一致性检查与修复、world.json 版本快照与 diff 回滚、章节版本快照 |
| 📤 **多格式导出** | 自动生成 `world.md`；EPUB / DOCX / Markdown 全书导出；大纲写入 `outlines/` |
| 📈 **写作统计看板** | Chart.js 可视化：字数进度、章节完成度、伏笔状态、情感分布 |
| ⏱️ **LLM 计时分析** | 每次生成展示各阶段 LLM 调用耗时分解，辅助定位性能瓶颈 |
| 💾 **本地优先** | 所有数据在本地磁盘，无需云端服务 |

</div>

### 两条对话路径（三 Agent 流水线）

| 路径 | 说明 |
|:--|:--|
| **第一路 · 对话** | 自然语言与"世界观架构师"交流；可选附带 `world.md` 上下文 |
| **第二路 · 结构同步** | 三 Agent 流水线：**同步器** 从架构师回复提取 JSON → **统一校对者** 审查完整性并直接补全遗漏 JSON（单次调用完成审查+补全，无需架构师往返）→ 按 **ID 增量合并**，已有条目更新、新条目追加，永不覆盖。同步器空输出时自动跳过校对。 |

第二路模型默认同主对话，可用 `STRUCTURE_SYNC_MODEL` 单独指定。校对者模型可用 `PROOFREADER_MODEL` 指定（建议用小模型加速）。校对轮数可用 `PROOFREADER_MAX_RETRIES` 配置，UI 可手动调整（0=跳过校对者）。

---

## 界面导览

工作台采用**三栏布局**：顶栏 + 左侧导航 + 中间主区 + 右侧看板。

<div align="center">

![工作台布局示意](docs/readme-workbench.svg)

*顶栏：世界选择、保存、退出；左侧：对话与世界观各模块导航；中间：对话或表单编辑区；右侧：统计看板与 JSON 查看器*

</div>

### 对话视图

![对话视图](docs/gui-chat-and-sync.svg)

*同步选项、创作模式选择、快捷词条、消息列表、输入框（Ctrl+Enter 发送）*

---

## 整体流程

```mermaid
flowchart LR
  subgraph 用户["👤 你"]
    A[输入设定 / 对话]
  end
  subgraph 第一路["💬 第一路 · 对话"]
    B[世界观架构师]
  end
  subgraph 第二路["🧩 第二路 · 三 Agent 流水线"]
    C[结构化同步器]
    D[校对者]
    E[架构师补充]
  end
  subgraph 本地["💾 本地数据"]
    F[(world.json)]
    G[world.md 导出]
  end
  A --> B
  B --> C
  C --> D
  D -->|通过| F
  D -->|遗漏| E
  E --> C
  F --> G
```

**三 Agent 同步流水线（时序）**

```mermaid
sequenceDiagram
  participant U as 👤 用户
  participant W as 🖥️ 工作台
  participant API as ⚡ FastAPI
  participant S as 🤖 同步器
  participant P as 🔍 校对者
  participant A as 🎨 架构师

  U->>W: 发送消息（可选勾选同步）
  W->>API: POST …/chat
  API-->>W: 架构师回复

  alt 开启对话后同步
    W->>API: POST …/sync-panels-from-chat
    API->>S: 抽取 JSON patch(v1)
    S-->>API: patch
    loop 校对→补充循环（最多 N 轮）
      API->>P: 对比「架构师回复」vs「同步器 JSON」vs「world.json」
      P-->>API: verdict: ok / retry
      opt verdict=retry
        API->>A: 补充问题
        A-->>API: 补充回复
        API->>S: 抽取新 patch
        S-->>API: patch(vN)
      end
    end
    Note over API: 按 ID 增量合并累积 patch
    API-->>W: world + updated_sections + proofreader 审计
    W->>API: PUT …/world（自动落盘）
  end
```

---

## 写作多智能体协同

故事写作模块采用**多智能体乐团（Multi-Agent Orchestra）**架构，由 10+ 个专职 Agent 协同完成从大纲到润色稿的全流程。各 Agent 职责单一、温度独立调优，并通过**并行后处理**和**可选反馈闭环**实现高效高质产出。

### 智能体协同架构

```mermaid
flowchart TB
  subgraph PreGen["📋 准备阶段"]
    MACRO["<b>宏大纲 Agent</b><br/>temp=0.65 · max_tokens=8192<br/>基于世界设定生成全书情节大纲"]
    BEATS["<b>节拍细纲 Agent</b><br/>temp=0.60 · 多章并行生成<br/>注入前章摘要确保跨章衔接"]
  end

  subgraph Inject["🧠 上下文自动注入（手稿生成前）"]
    direction LR
    RAG["RAG 语义检索<br/>ChromaDB 向量查询"]
    KG_STATE["知识图谱状态<br/>角色位置·情绪·目标"]
    SENT_HINT["情感基调提示<br/>上一章结尾情感"]
    STRUCT["宏大纲 + 节拍细纲<br/>前 N 章手稿原文"]
  end

  subgraph Core["✍️ 核心生成"]
    WRITER["<b>手稿生成 Agent</b><br/>temp=0.75 · max_tokens=8192<br/>综合全部上下文撰写正文<br/>支持流式输出 (SSE)"]
  end

  subgraph Parallel["⚡ 并行后处理钩子（asyncio.gather 并发）"]
    direction TB
    SUM["摘要卡片 Agent<br/>temp=0.2"]
    STATE["角色状态 Agent<br/>temp=0.3"]
    INDEX["RAG 索引 Agent<br/>ChromaDB 写入"]
    KG_AGENT["KG 提取 Agent<br/>temp=0.2"]
    AUDIT["一致性审校 Agent<br/>temp=0.3 · 7 维度"]
    TONE["情感追踪 Agent<br/>temp=0.2"]
  end

  subgraph Polish["🔄 可选：审校 ↔ 润色反馈闭环"]
    direction LR
    P_CHECK["<b>一致性审校</b><br/>（闭环内复用）"]
    POLISHER["<b>润色者 Agent</b><br/>temp=0.55 · 最多 N 轮<br/>9 条硬规则去 AI 化"]
    P_CHECK -->|"发现问题"| POLISHER
    POLISHER -->|"润色稿"| P_CHECK
  end

  subgraph Output["📦 输出产物"]
    direction LR
    O1["手稿正本<br/>manuscript/"]
    O2["摘要卡片<br/>SQLite+JSON"]
    O3["知识图谱<br/>narrative_kg.json"]
    O4["审校报告<br/>consistency_reports/"]
    O5["情感日志<br/>sentiment_logs/"]
    O6["润色稿<br/>polished/"]
    O7["版本快照<br/>snapshots/"]
  end

  MACRO --> BEATS
  BEATS --> Core
  Inject --> Core
  Core --> Parallel
  Parallel --> Polish
  Polish -.->|"润色稿"| Output
  Parallel -.-> Output
  Core -.->|"手稿正本"| Output
```

### 智能体职责一览

| 阶段 | Agent | 温度 | 职责 |
|:--|:--|:--|:--|
| **准备** | 宏大纲 Agent | 0.65 | 根据用户提示与世界设定生成全书宏观情节大纲 |
| **准备** | 节拍细纲 Agent | 0.60 | 按章撰写详细节拍，多章可并行生成；注入前章摘要确保衔接 |
| **注入** | RAG 语义检索 | — | ChromaDB 向量相似度查询，自动注入相关前文片段 |
| **注入** | 叙事知识图谱 | — | 提供角色当前状态（位置/情绪/目标）和关键物品流转 |
| **注入** | 情感基调提示 | — | 传递上一章结尾情感基调，指导本章开篇情绪过渡 |
| **核心** | 手稿生成 Agent | 0.75 | 综合全部上下文撰写正文，支持 SSE 流式输出 |
| **后处理** | 摘要卡片 Agent | 0.2 | 提取章节摘要（主要事件/出场人物/伏笔操作/结尾钩子） |
| **后处理** | 角色状态 Agent | 0.3 | 从正文提取各角色运行时状态变化并持久化 |
| **后处理** | RAG 索引 Agent | — | 将新章写入 ChromaDB 向量索引供后续检索 |
| **后处理** | KG 提取 Agent | 0.2 | 提取实体-事件-伏笔三元组，更新叙事知识图谱 |
| **后处理** | 一致性审校 Agent | 0.3 | 7 维度自动审查：位置/性格/物品状态/POV/伏笔/情感连续/时间线 |
| **后处理** | 情感追踪 Agent | 0.2 | 章节分段情感分析，判定各段基调和整体情感弧线 |
| **闭环** | 润色者 Agent | 0.55 | 与审校形成反馈闭环（最多 N 轮）；9 条硬规则去 AI 化：破折号节制、段落合并、句式破形、情绪具象化、对话节奏、冗余修剪、三遍精炼、描写锚定感官、信息密度分层 |

### 关键设计原则

- **非阻塞钩子**：所有后处理钩子由 `try/except Exception: pass` 包裹，任一 Agent 失败不影响手稿产出
- **并行加速**：摘要卡片、角色状态、RAG 索引、KG 提取、一致性审校、情感追踪 6 个独立钩子通过 `asyncio.gather` 并发执行
- **闭环隔离**：润色者在所有并行钩子完成后**串行**执行，避免与独立的一致性审校冲突
- **温度差异化**：创造性任务（手稿 0.75、润色 0.55）使用较高温度；抽取式任务（摘要 0.2、KG 0.2、情感 0.2）使用低温确保稳定输出
- **上下文窗口分层**：手稿生成仅注入前一章摘要 + 前 N 章手稿片段 + RAG 检索片段，避免上下文膨胀

---

## 功能一览

### 🌍 世界观模块（11 个）

| 模块 | 核心功能 | 可视化 |
|:--|:--|:--|
| **地理** | 大陆 / 区域卡片；区域关系 | 关系网络图（Mermaid） |
| **生态** | 生境群落、代表物种、遭遇话术 | 一键 AI 生态生成 |
| **境界** | 分境卡片、技能树、职业体系 | 职业晋升图谱（Mermaid） |
| **属性** | 通用人物属性维度定义 | 雷达参照图 |
| **物品** | 品质档位卡片化预览 | 稀有度叙事 |
| **文化·宗教** | 文化 / 宗教 / 融合实体卡片 | 实体关系图（Mermaid） |
| **派系** | 组织总览、单卡简介 | 全局关系图（缩放+拖拽） |
| **历史** | 重大事件管理 | 时间轴 + 因果链导图 |
| **经济** | 货币、市场、商路、贸易品 | 与地理/派系 id 对齐 |
| **角色** | 主角团、重要配角、卡司 JSON | vis.js 交互式人物关系网络（拖拽/缩放） |
| **故事** | 章节、宏大纲、节拍大纲、手稿 | 伏笔时间线 · RAG 语义检索 · KG 一致性审校 · 情感弧线 · 章节快照 · EPUB/DOCX 导出 · 统计看板 |

### 🤖 AI 对话能力

| 功能 | 说明 |
|:--|:--|
| **世界观构建对话** | 与架构师自由交流；快捷词条引导；Ctrl+Enter 发送 |
| **人物生成对话** | 独立对话线程；可配合引导与结构化同步 |
| **故事 Agent** | 工具调用：伏笔查询/埋设/回收、手稿生成、自动识别 markdown 代码块 |
| **RAG 语义检索** | 本地向量索引（ChromaDB + BGE embedding），智能检索相关前文片段注入写作上下文 |\n| **叙事知识图谱** | 轻量事件-实体-时间三元组，追踪角色状态演变和关键物品流转 |\n| **一致性审校** | 7 维度自动审校（位置/性格/物品/POV/伏笔/情感/时间线），非阻塞式章节后检查 |\n| **情感弧线追踪** | 逐章情感分析 + Mermaid 曲线可视化，确保跨章情感过渡自然 |\n| **润色者 Agent** | 审校↔润色反馈闭环（至多 N 轮），9 条硬规则去 AI 化（破折号节制/段落合并/句式破形/情绪具象化等），原稿↔润色稿分栏 diff 对比 |
| **创作模式** | 小说 / 游戏 / CoC / DnD，注入不同 system prompt 与词汇表 |
| **一键生态生成** | 基于当前世界观上下文自动生成生态设定 |

### 🔧 数据工具

| 工具 | 说明 |
|:--|:--|
| **全文搜索** | 同时搜索 `world.json` 与 `world.md` |
| **引用一致性检查** | 跨模块 id 引用校验（区域、派系等） |
| **自动修复** | 保守修复引用问题，支持 `dry_run` 预览 |
| **版本快照** | 每次保存自动快照；diff 查看；一键回滚；单个快照删除 |
| **章节版本快照** | 手稿保存时自动创建版本快照（最多 10 个），支持版本间行级 diff 对比 |
| **多格式导出** | 一键导出 EPUB（电子书）/ DOCX（Word）/ Markdown 全书，自动处理中文文件名 |
| **写作统计看板** | Chart.js 可视化仪表盘：总字数、章节进度、伏笔状态分布、情感基调分布 |
| **LLM 计时面板** | 手稿生成后展示各阶段 LLM 调用耗时柱状图（大纲/节拍/手稿/摘要/KG/情感） |
| **RAG 索引就绪指示** | 情节工作台顶栏状态点 + 侧边上下文面板（前章摘要 / 角色状态 / 索引统计） |
| **world.md 导出** | 从 JSON 自动生成人类可读手册 |

### 🌐 世界管理

顶栏提供 **新建 / 重命名 / 删除** 世界；下拉列表展示 **显示名 · id**；**保存**（Ctrl+S / ⌘S）写入磁盘；**退出** 关闭服务进程。

---

## 产品地图（工作台 ↔ world.json）

下图概括单页应用中主要板块与本地 `world.json` 的对应关系。

```mermaid
flowchart TB
  subgraph UI["🖥️ Web 工作台"]
    CHAT[世界观构建]
    CHARCHAT[人物生成]
    STORYCHAT[故事 Agent]
    GEO[地理]
    ECO[生态]
    POW[境界·技能树·职业]
    ATTR[属性系统]
    ITEM[物品品质]
    CUL[文化·宗教]
    FAC[派系]
    HIS[历史]
    ECON[经济]
    CHAR[角色·卡司]
    STORY[故事·章节]
    TOOLS[搜索·引用·快照]
  end
  JSON[(📄 world.json)]
  MD[📝 world.md 导出]
  OL[📁 outlines/]

  CHAT --> JSON
  CHARCHAT --> JSON
  STORYCHAT --> JSON
  GEO --> JSON
  ECO --> JSON
  POW --> JSON
  ATTR --> JSON
  ITEM --> JSON
  CUL --> JSON
  FAC --> JSON
  HIS --> JSON
  ECON --> JSON
  CHAR --> JSON
  STORY --> JSON
  JSON --> MD
  TOOLS --> JSON
  OL --> JSON
```

---

## 环境要求与安装

### 环境要求

- **Python 3.10+**
- 兼容 OpenAI API 的网关（默认 `https://llmapi.paratera.com/v1`）及可用 API Key

### 安装依赖

```bash
pip install -r requirements.txt
```

依赖清单：

| 包 | 用途 |
|:--|:--|
| `fastapi` | Web API 框架 |
| `uvicorn` | ASGI 服务器 |
| `openai` | LLM 客户端（OpenAI 兼容） |
| `pydantic` + `pydantic-settings` | 数据验证与配置管理 |
| `python-dotenv` | 环境变量加载 |
| `httpx` | 异步 HTTP 客户端 |
| `chromadb` | 本地向量数据库（RAG 语义检索） |
| `sentence-transformers` | 本地文本 embedding（BAAI/bge-small-zh-v1.5） |
| `ebooklib` | EPUB 电子书生成 |
| `python-docx` | DOCX Word 文档生成 |
| `pytest` | 测试框架 |

若使用 Conda 环境，可指定解释器路径：

```powershell
& "E:\ananconda\envs\Agent\python.exe" -m pip install -r requirements.txt
```

---

## 配置

复制环境变量模板并编辑：

```bash
# Linux / macOS
cp .env.example .env

# Windows (PowerShell / CMD)
copy .env.example .env
```

常用变量：

| 变量 | 说明 | 默认值 |
|:--|:--|:--|
| `PARATERA_API_KEY` | 兼容 OpenAI 的 API 密钥 | *(必填)* |
| `OPENAI_API_BASE` | API 网关地址 | `https://llmapi.paratera.com/v1` |
| `OPENAI_CHAT_MODEL` | 对话模型 | `DeepSeek-V4-Flash` |
| `STRUCTURE_SYNC_MODEL` | 可选：结构化同步专用模型 | 同 `OPENAI_CHAT_MODEL` |
| `PROOFREADER_MODEL` | 可选：校对者专用模型，建议用小模型加速 | 同 `STRUCTURE_SYNC_MODEL` |
| `PROOFREADER_MAX_RETRIES` | 可选：校对者→架构师补充最大轮数（0=跳过校对者） | `3` |
| `MCW_EMBEDDING_MODEL` | 可选：本地 embedding 模型名 | `BAAI/bge-small-zh-v1.5` |
| `MCW_EMBEDDING_BACKEND` | `auto` / `api` / `local`：无本地缓存时 `auto` 不走 HuggingFace，直接 API | `auto` |
| `MCW_HF_ENDPOINT` | 可选：Hugging Face 镜像（如 `https://hf-mirror.com`） | *(空)* |
| `WORLDS_DIR` | 可选：自定义世界数据根目录 | `worlds/` |

> 💡 **临时设置密钥**（不写 `.env`，关闭终端即失效）：
>
> ```bash
> # Windows PowerShell
> $env:PARATERA_API_KEY = "你的密钥"
> python run.py
>
> # macOS / Linux
> PARATERA_API_KEY="你的密钥" python run.py
> ```

---

## 启动服务

### 基本启动

```bash
python run.py
```

启动约 1 秒后在默认浏览器中自动打开 `http://127.0.0.1:8765`。

### 常用参数

| 参数 | 说明 |
|:--|:--|
| `--host 0.0.0.0` | 监听所有网络接口 |
| `--port 8765` | 自定义端口 |
| `--reload` | 代码变更自动重载（开发模式） |
| `--no-browser` | 不自动打开浏览器 |

```bash
# 局域网访问
python run.py --host 0.0.0.0 --port 8765

# 开发调试
python run.py --reload
```

> 使用 `--reload` 时自动设置 `MCW_NO_STATIC_CACHE=1`，禁用前端缓存避免 app.js 长期 304。

### 等价启动方式

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

### 退出

顶栏**「退出」**调用 `POST /api/shutdown`，停止 Uvicorn 进程并尝试关闭浏览器标签页（仅回环地址可调用）。

---

## 数据目录结构

每个世界位于 `worlds/<world_id>/`：

```
worlds/
└── 诸神黄昏-58bddae5/
    ├── world.json          ← 权威结构化设定
    ├── world.md            ← 人类可读手册（自动导出）
    ├── manifest.json       ← 创建时间与网关元信息
    ├── outlines/           ← 人物 / 情节大纲导出
    ├── story/               ← 章节手稿、摘要卡片、RAG 索引
    │   ├── macro_outline.md
    │   ├── beats/             ← 节拍大纲
    │   ├── manuscript/        ← 手稿正本
    │   ├── summaries/         ← 章节摘要卡片
    │   ├── polished/          ← 润色后文稿
    │   ├── snapshots/         ← 章节版本快照
    │   ├── consistency_reports/  ← 一致性审校报告
    │   ├── sentiment_logs/    ← 情感日志
    │   └── rag_index/         ← ChromaDB 向量索引
    ├── sessions/           ← 对话片段日志（可选）
    └── snapshots/          ← 版本快照
        ├── v001.json
        ├── v002.json
        └── ...
```

---

## API 摘要

> 完整路由定义见 `app/main.py`。

| 方法 | 路径 | 说明 |
|:--|:--|:--|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/config` | 公开配置（模型名、Key 状态等） |
| `POST` | `/api/shutdown` | 停止服务（仅回环） |
| `GET` | `/api/worlds` | 世界列表 |
| `POST` | `/api/worlds` | 创建世界 |
| `GET` | `/api/worlds/{id}` | 加载世界 |
| `PUT` | `/api/worlds/{id}` | 保存完整 world |
| `PATCH` | `/api/worlds/{id}` | 重命名显示名 |
| `DELETE` | `/api/worlds/{id}` | 删除世界 |
| `POST` | `/api/worlds/{id}/chat` | 世界观对话 |
| `POST` | `/api/worlds/{id}/character-chat` | 人物生成对话 |
| `POST` | `/api/worlds/{id}/story-chat` | 故事 Agent 对话 |
| `POST` | `/api/worlds/{id}/sync-panels-from-chat` | 结构化同步（含校对者审计） |
| `POST` | `/api/worlds/{id}/ecology-generate` | 一键生态生成 |
| `POST` | `/api/worlds/{id}/outline` | 大纲生成 |
| `GET` | `/api/worlds/{id}/search` | 全文搜索 |
| `GET` | `/api/worlds/{id}/lint-references` | 引用一致性检查 |
| `POST` | `/api/worlds/{id}/fix-references` | 自动修复引用 |
| `POST` | `/api/worlds/{id}/export-md` | 导出 world.md |
| `GET` | `/api/worlds/{id}/snapshots` | 快照列表 |
| `GET` | `/api/worlds/{id}/snapshots/diff` | 快照行级 diff |
| `POST` | `/api/worlds/{id}/snapshots/rollback` | 回滚到快照 |
| `DELETE` | `/api/worlds/{id}/snapshots/{version}` | 删除单个快照 |
| `DELETE` | `/api/worlds/{id}/snapshots` | 清空全部快照 |
| `POST` | `/api/worlds/{id}/refresh/faction-relations` | 重算派系关系 |
| `POST` | `/api/worlds/{id}/refresh/culture-relations` | 重算文化关系 |
| `GET` | `/api/worlds/{id}/story/rag/stats` | RAG 索引统计与就绪状态 |\n| `GET` | `/api/worlds/{id}/story/narrative-kg` | 叙事知识图谱（实体/事件/伏笔） |\n| `GET` | `/api/worlds/{id}/story/consistency-report/{chapter_id}` | 章节一致性审校报告 |\n| `GET` | `/api/worlds/{id}/story/sentiment-arc` | 情感弧线数据 + Mermaid 图表 |\n| `GET` | `/api/worlds/{id}/story/manuscript/{chapter_id}/polished` | 润色后文稿 + 元数据 |\n| `GET` | `/api/worlds/{id}/story/manuscript/{chapter_id}/polish-trace` | 审校↔润色 Loop 轮次追踪 |\n| `GET` | `/api/worlds/{id}/story/chapters/{chapter_id}/snapshots` | 章节版本快照列表 |\n| `GET` | `/api/worlds/{id}/story/chapters/{chapter_id}/snapshots/{version}` | 读取特定章节快照版本 |\n| `GET` | `/api/worlds/{id}/story/chapters/{chapter_id}/snapshots/diff` | 章节快照行级 diff 对比 |\n| `GET` | `/api/worlds/{id}/story/export` | 全书导出（epub/docx/md） |\n| `GET` | `/api/worlds/{id}/story/stats` | 写作统计（字数/进度/伏笔/情感分布） |\n| `PATCH` | `/api/worlds/{id}/story/writing-defaults` | 切换写作增强开关（KG/审校/情感/润色/最大轮数） |
| `*` | `/api/worlds/{id}/story/*` | 故事 CRUD（章节/大纲/节拍/手稿/伏笔） |

---

## 测试

```bash
python -m pytest tests -q
```

VS Code / Cursor 中可使用 `.vscode/launch.json` 配置 F5 调试；需安装 `debugpy`。

---

## 后续路线

```mermaid
flowchart LR
  subgraph 近期["🟢 近期"]
    A1[关系图筛选与布局]
    A2[引用校验覆盖扩展]
  end
  subgraph 中期["🟡 中期"]
    B1[大纲与卡司版本联动]
    B2[批量导出 / 模板]
  end
  subgraph 已完成["✅ 已完成"]
    C1[三 Agent 校对者流水线]
    C2[ID 感知增量合并]
    C3[RAG 语义检索]
    C4[叙事知识图谱]
    C5[一致性审校 Agent]
    C6[情感弧线追踪]
    C7[润色者 Agent + 审校↔润色 Loop]
    C8[并行后处理优化]
    C9[统一校对者 + 节拍并行生成]
    C10[章节版本快照 + Diff]
    C11[vis.js 人物关系网络]
    C12[EPUB/DOCX 多格式导出]
    C13[写作统计看板]
    C14[LLM 计时分析面板]
  end
  A1 --> A2 --> B1 --> B2
```

详见 [`todolist.md`](todolist.md)。

---

## 更多文档

| 文档 | 内容 |
|:--|:--|
| [`docs/readme-hero.svg`](docs/readme-hero.svg) | 仓库首页横幅图（矢量） |
| [`docs/readme-workbench.svg`](docs/readme-workbench.svg) | 工作台布局示意（矢量） |
| [`docs/gui-chat-and-sync.svg`](docs/gui-chat-and-sync.svg) | 对话与同步流程示意 |
| [`docs/gui-workbench-layout.svg`](docs/gui-workbench-layout.svg) | 三栏布局详解示意 |
| [`todolist.md`](todolist.md) | 路线图、架构速记与 backlog |
| [`.cursor/skills/`](.cursor/skills/) | Cursor Agent Skills（9 个模块专属 skill） |

---

<div align="center">

**❤️ 为世界创造者，游戏工作者，和每一个具有奇思妙想的Idea而创建。**

</div>
