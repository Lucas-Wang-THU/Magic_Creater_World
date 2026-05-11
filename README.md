<div align="center">

![Magic Creater World — 横幅](docs/readme-hero.svg)

**把对话里的灵感，落成可保存、可导出的完整世界观。**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063?style=flat-square&logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![pytest](https://img.shields.io/badge/tests-pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white)](https://pytest.org/)

</div>

---

## 目录

- [它能做什么](#它能做什么)
- [整体流程](#整体流程)
- [功能一览](#功能一览)
- [环境要求](#环境要求)
- [安装依赖](#安装依赖)
- [配置](#配置)
- [启动服务](#启动服务)
- [数据目录](#数据目录结构)
- [测试](#测试)
- [更多文档](#更多文档)
- [许可证](#许可证)

---

## 它能做什么

世界观辅助工具：在本地持久化 **地理、超凡力量、物品品质、派系与关系、世界历史**，并通过兼容 OpenAI 的 API（默认 `https://llmapi.paratera.com/v1`）进行对话补全。**人物与情节大纲**在生成前会强制读取当前世界的 `world.json`，结果写入 `worlds/<world_id>/outlines/`。

**双路模型（Web 工作台）**

| 路径 | 角色 | 说明 |
|:--|:--|:--|
| **第一路** | 世界观架构师 | 自然语言对话，补全与修订设定 |
| **第二路** | 结构化同步器 | 对话后（可选）再调模型，把可落盘内容解析为 JSON，**自动填回**各模块表单 |

表单更新后仍需手动 **「保存世界」** 才写入 `world.json`。第二路模型默认同主对话，可用 `STRUCTURE_SYNC_MODEL` 单独指定。

---

## 整体流程

```mermaid
flowchart LR
  subgraph 用户["你"]
    A[输入设定 / 对话]
  end
  subgraph 第一路["第一路 · 对话"]
    B[世界观架构师]
  end
  subgraph 第二路["第二路 · 可选"]
    C[结构化同步器]
  end
  subgraph 本地["本地数据"]
    D[(world.json)]
    E[world.md 导出]
  end
  A --> B
  B --> C
  C --> D
  D --> E
```

---

## 功能一览

| 模块 | 说明 |
|:--|:--|
| **对话** | 与架构师聊天；支持 Ctrl+Enter 快捷发送；可选对话后同步表单 |
| **地理** | 大陆 / 区域卡片、区域关系网络图、区域类型图标 |
| **力量 / 物品** | 分境界 / 分档卡片化预览（能力、限制、范例等） |
| **派系** | 总览预览、全局关系图（缩放 + 拖拽平移）、单卡简介与关系小图 |
| **历史** | 大事件时间轴、因果链导图 |
| **大纲 / 文件** | 人物与情节生成、导出 `world.md`、浏览数据目录 |

工作台为 **单页静态前端 + FastAPI**：`/` 为界面，`/api/*` 为接口，`/static/*` 为前端资源（根路径不整站挂载静态目录，避免抢占 API）。

---

## 环境要求

- Python 3.10+（推荐与 `requirements.txt` 一致）
- 可选：使用 Paratera 或其它兼容网关时，需可用的 API Key 与模型名

---

## 安装依赖

在项目根目录执行：

```bash
pip install -r requirements.txt
```

若使用指定的 Conda 环境，可将 `python` 换为你的解释器路径，例如：

```powershell
& "E:\ananconda\envs\Agent\python.exe" -m pip install -r requirements.txt
```

---

## 配置

复制环境变量模板并编辑：

```bash
# Windows（PowerShell / CMD）
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

常用变量（详见 `.env.example`）：

| 变量 | 说明 |
|:--|:--|
| `PARATERA_API_KEY` | 兼容 OpenAI 的 API 密钥；未设置时对话、大纲与板块同步会返回 **503**，其余读写世界仍可用 |
| `OPENAI_API_BASE` | 默认 `https://llmapi.paratera.com/v1` |
| `OPENAI_CHAT_MODEL` | 默认 `DeepSeek-V4-Flash`，请按网关实际可用模型修改 |
| `STRUCTURE_SYNC_MODEL` | 可选；对话后「板块结构化同步」所用模型，留空则与 `OPENAI_CHAT_MODEL` 相同 |
| `WORLDS_DIR` | 可选，自定义世界数据根目录（默认项目下 `worlds/`） |

### 临时设置 API Key（不写 `.env`）

适合一次性试用：只在**当前终端窗口**生效，关闭窗口后即失效，也不会把密钥写进仓库里的文件。

**Windows PowerShell**（先设变量，再在同一窗口里启动）：

```powershell
$env:PARATERA_API_KEY = "你的密钥"
python run.py
```

**Windows CMD**：

```bat
set PARATERA_API_KEY=你的密钥
python run.py
```

**macOS / Linux（bash/zsh）**：

```bash
export PARATERA_API_KEY="你的密钥"
python run.py
```

或单行（仅作用于这一条命令）：

```bash
PARATERA_API_KEY="你的密钥" python run.py
```

说明：应用通过 `python-dotenv` 读取 `.env`；若同时存在 `.env` 与上面的临时变量，**以当前进程环境变量为准**。临时密钥请勿提交到 Git。

---

## 启动服务

**推荐**：在项目根目录运行：

```bash
python run.py
```

启动约 1 秒后会在**系统默认浏览器**中自动打开工作台（`127.0.0.1` 与端口一致；监听 `0.0.0.0` 时仍打开本机 `127.0.0.1`）。若不需要自动打开，请加 **`--no-browser`**。

默认监听 **`http://127.0.0.1:8765`**。可勾选「对话后同步表单」以调用 `POST /api/worlds/{id}/sync-panels-from-chat`；勾选「按当前导航限定同步范围」时，仅在当前模块写入，其它模块输出会被丢弃。合并时对**空数组 / 空白字符串**采用保守策略，避免误清空已有内容。

常用参数：

```bash
python run.py --host 0.0.0.0 --port 8765
python run.py --reload
python run.py --no-browser
```

等价方式（未使用 `run.py` 时）：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

---

## 数据目录结构

每个世界位于 `worlds/<world_id>/`：

| 文件 / 目录 | 说明 |
|:--|:--|
| `world.json` | 权威结构化设定 |
| `world.md` | 由程序从 JSON 导出的可读手册 |
| `outlines/` | 人物 / 情节大纲（含 YAML 头：`based_on_world_id`、`based_on_world_version`） |
| `sessions/` | 对话片段日志（可选） |
| `manifest.json` | 创建时间与网关元信息（不含密钥） |

---

## 测试

```bash
python -m pytest tests -q
```

---

## 更多文档

| 文档 | 内容 |
|:--|:--|
| [`todolist.md`](todolist.md) | 架构与实现要点 |
| [`html.md`](html.md) | 界面与前端设计思路 |

---

## 许可证

未指定；由项目维护者自行补充。
