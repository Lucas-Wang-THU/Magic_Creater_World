<div align="center">

![Magic Creater World — Banner](docs/readme-hero.svg)

**Turn inspiration from conversation into a complete, saveable, exportable world.**

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

## Table of Contents

- [Quick Start](#quick-start)
- [What It Does](#what-it-does)
- [UI Overview](#ui-overview)
- [Overall Workflow](#overall-workflow)
- [Feature Tour](#feature-tour)
- [Product Map (Workbench ↔ world.json)](#product-map-workbench--worldjson)
- [Requirements & Installation](#requirements--installation)
- [Configuration](#configuration)
- [Launching the Server](#launching-the-server)
- [Data Directory Structure](#data-directory-structure)
- [API Summary](#api-summary)
- [Testing](#testing)
- [Roadmap](#roadmap)
- [More Documentation](#more-documentation)

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure your API key
cp .env.example .env          # Linux / macOS
copy .env.example .env        # Windows
# Edit .env and fill in PARATERA_API_KEY

# 3. Launch
python run.py
```

The app opens automatically at `http://127.0.0.1:8765`. Start building your world.

---

## What It Does

**Magic Creater World (MCW)** is a local-first, AI-assisted world-building workbench for fiction writers, game masters, and roleplayers. It turns LLM conversations into structured, persistent, exportable world data.

<div align="center">

| ✨ Core Feature | Description |
|:--|:--|
| 📌 **Single Source of Truth** | `world.json` on disk is the authoritative structure; `world.md` is the human-readable export |
| 💬 **Conversational Building** | Chat with a "World Architect" LLM agent in natural language across 4 creative modes (Novel / Game / CoC / DnD) |
| 🧩 **Structure Sync** | Optional post-chat structured extraction — the LLM parses conversation into JSON patches merged into forms |
| 🗺️ **11 World Modules** | Geography · Ecology · Power System · Attributes · Items · Cultures · Factions · History · Economy · Characters · Story |
| 📊 **Relationship Visualization** | Mermaid diagrams: relationship networks, skill trees, profession graphs, timelines, causal chains |
| 🔍 **Data Tools** | Full-text search, reference consistency linting & auto-fix, version snapshots with diff & rollback |
| 📤 **Export** | Auto-generated `world.md` human-readable handbook; outlines written to `outlines/` |
| 💾 **Local-First** | All data lives on your disk — no cloud service required |

</div>

### Two Conversation Paths

| Path | Description |
|:--|:--|
| **Path 1 · Dialogue** | Natural language chat with the "World Architect"; optionally attach `world.md` as context |
| **Path 2 · Structure Sync** | When enabled, a second LLM call extracts structured JSON from the conversation and merges it into the world data |

The structure sync model defaults to the main chat model. Set `STRUCTURE_SYNC_MODEL` to use a different one.

---

## UI Overview

The workbench uses a **three-column layout**: top bar + left navigation + main panel + right dashboard.

<div align="center">

![Workbench Layout](docs/readme-workbench.svg)

*Top bar: world selector, save, quit; Left: conversation & module navigation; Center: chat or form editor; Right: stats dashboard & JSON viewer*

</div>

### Chat View

![Chat View](docs/gui-chat-and-sync.svg)

*Sync options, creative mode selector, quick chips, message list, composer (Ctrl+Enter to send)*

### Full Layout Detail

![Workbench Layout Detail](docs/gui-workbench-layout.svg)

*Header, nav, main panel with forms/cards/Mermaid diagrams, and dashboard with stats/snapshots/reference lint/raw JSON*

---

## Overall Workflow

```mermaid
flowchart LR
  subgraph User["👤 You"]
    A[Write setting / Chat]
  end
  subgraph Path1["💬 Path 1 · Dialogue"]
    B[World Architect]
  end
  subgraph Path2["🧩 Path 2 · Opt"]
    C[Structure Sync]
  end
  subgraph Local["💾 Local Data"]
    D[(world.json)]
    E[world.md export]
  end
  A --> B
  B --> C
  C --> D
  D --> E
```

**Post-chat Sync & Save (sequence)**

```mermaid
sequenceDiagram
  participant U as 👤 User
  participant W as 🖥️ Workbench
  participant API as ⚡ FastAPI
  participant LLM as 🤖 Model Gateway
  U->>W: Send message (sync optional)
  W->>API: POST …/chat
  API->>LLM: Completion
  LLM-->>API: Assistant reply
  API-->>W: reply
  alt Sync enabled
    W->>API: POST …/sync-panels-from-chat
    API->>LLM: Extract JSON patch
    LLM-->>API: Structured result
    API-->>W: world + updated_sections
    W->>API: PUT …/world (auto-save)
  end
```

---

## Feature Tour

### 🌍 World Modules (11)

| Module | Core Features | Visualization |
|:--|:--|:--|
| **Geography** | Continent / region cards; region relationships | Relationship network (Mermaid) |
| **Ecology** | Biomes, species, encounter dialogue | One-click AI ecology generation |
| **Power System** | Realm tiers, skill trees, profession system | Profession promotion graph (Mermaid) |
| **Attributes** | Generic character stat dimensions | Radar reference chart |
| **Items** | Quality tier cards with rarity narrative | Tier preview cards |
| **Cultures** | Culture / religion / syncretic entity cards | Entity relationship diagram (Mermaid) |
| **Factions** | Organization overview, single-card profiles | Global relationship graph (zoomable + pannable) |
| **History** | Major event management | Timeline + causal chain diagram |
| **Economy** | Currencies, markets, trade routes, goods | ID-aligned with Geography/Factions |
| **Characters** | Protagonist core, supporting cast, cast JSON | Character relationship network |
| **Story** | Chapters, macro outlines, beat outlines, manuscripts | Foreshadowing timeline |

### 🤖 AI Conversation Features

| Feature | Description |
|:--|:--|
| **World-building Chat** | Free-form conversation with the Architect agent; quick chips; Ctrl+Enter to send |
| **Character Generation** | Dedicated chat thread with optional guide and structure sync |
| **Story Agent** | Tool calling: foreshadowing CRUD, manuscript generation, auto-detection of markdown code blocks |
| **Creative Modes** | Novel / Game / CoC / DnD — each injects different system prompts and terminology |
| **One-click Ecology** | Auto-generate ecology settings from current world context |

### 🔧 Data Tools

| Tool | Description |
|:--|:--|
| **Full-text Search** | Searches both `world.json` and `world.md` simultaneously |
| **Reference Linter** | Cross-module ID reference validation (regions, factions, etc.) |
| **Auto-fix** | Conservative reference repair with `dry_run` preview |
| **Version Snapshots** | Auto-snapshot on every save; line-level diff viewer; one-click rollback |
| **world.md Export** | Auto-generate human-readable handbook from JSON |

### 🌐 World Management

Use the top bar to **create / rename / delete** worlds. The dropdown shows **display name · id**. **Save** (Ctrl+S / ⌘S) writes to disk. **Quit** shuts down the server process.

---

## Product Map (Workbench ↔ world.json)

How the SPA panels map to the local `world.json`:

```mermaid
flowchart TB
  subgraph UI["🖥️ Web Workbench"]
    CHAT[World-building Chat]
    CHARCHAT[Character Gen]
    STORYCHAT[Story Agent]
    GEO[Geography]
    ECO[Ecology]
    POW[Powers·Skills·Professions]
    ATTR[Attributes]
    ITEM[Items]
    CUL[Cultures·Religions]
    FAC[Factions]
    HIS[History]
    ECON[Economy]
    CHAR[Characters·Cast]
    STORY[Story·Chapters]
    TOOLS[Search·Lint·Snapshots]
  end
  JSON[(📄 world.json)]
  MD[📝 world.md export]
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

## Requirements & Installation

### Requirements

- **Python 3.10+**
- An OpenAI-compatible API gateway (default: `https://llmapi.paratera.com/v1`) with a valid API key

### Install Dependencies

```bash
pip install -r requirements.txt
```

Dependency overview:

| Package | Purpose |
|:--|:--|
| `fastapi` | Web API framework |
| `uvicorn` | ASGI server |
| `openai` | LLM client (OpenAI-compatible) |
| `pydantic` + `pydantic-settings` | Data validation & config management |
| `python-dotenv` | Environment variable loading |
| `httpx` | Async HTTP client |
| `pytest` | Test framework |

For Conda environments, specify your interpreter path:

```powershell
& "E:\ananconda\envs\Agent\python.exe" -m pip install -r requirements.txt
```

---

## Configuration

Copy the environment template and edit:

```bash
# Linux / macOS
cp .env.example .env

# Windows (PowerShell / CMD)
copy .env.example .env
```

Key variables:

| Variable | Description | Default |
|:--|:--|:--|
| `PARATERA_API_KEY` | OpenAI-compatible API key | *(required)* |
| `OPENAI_API_BASE` | API gateway URL | `https://llmapi.paratera.com/v1` |
| `OPENAI_CHAT_MODEL` | Chat model name | `DeepSeek-V4-Flash` |
| `STRUCTURE_SYNC_MODEL` | Optional: dedicated model for structure sync | Same as `OPENAI_CHAT_MODEL` |
| `WORLDS_DIR` | Optional: custom worlds root directory | `worlds/` |

> 💡 **Temporary key** (not written to `.env`, expires with terminal session):
>
> ```bash
> # Windows PowerShell
> $env:PARATERA_API_KEY = "your-key"
> python run.py
>
> # macOS / Linux
> PARATERA_API_KEY="your-key" python run.py
> ```

---

## Launching the Server

### Basic Launch

```bash
python run.py
```

Opens `http://127.0.0.1:8765` in your default browser after ~1 second.

### Common Options

| Option | Description |
|:--|:--|
| `--host 0.0.0.0` | Listen on all network interfaces |
| `--port 8765` | Custom port |
| `--reload` | Auto-reload on code changes (dev mode) |
| `--no-browser` | Don't auto-open browser |

```bash
# LAN access
python run.py --host 0.0.0.0 --port 8765

# Development with auto-reload
python run.py --reload
```

> Using `--reload` automatically sets `MCW_NO_STATIC_CACHE=1` to disable frontend caching, preventing stale `app.js` from being served.

### Alternative Launch

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

### Quitting

Use the top-bar **"Quit"** button to call `POST /api/shutdown`, which stops the Uvicorn process and attempts to close the browser tab (loopback only).

---

## Data Directory Structure

Each world lives under `worlds/<world_id>/`:

```
worlds/
└── Twilight-of-the-Gods-58bddae5/
    ├── world.json          ← Authoritative structured data
    ├── world.md            ← Human-readable handbook (auto-exported)
    ├── manifest.json       ← Creation metadata & gateway info
    ├── outlines/           ← Character & plot outlines
    ├── sessions/           ← Chat session logs (optional)
    └── snapshots/          ← Version snapshots
        ├── v001.json
        ├── v002.json
        └── ...
```

---

## API Summary

> Full route definitions in `app/main.py`.

| Method | Path | Description |
|:--|:--|:--|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/config` | Public config (model name, key status) |
| `POST` | `/api/shutdown` | Stop server (loopback only) |
| `GET` | `/api/worlds` | List all worlds |
| `POST` | `/api/worlds` | Create a world |
| `GET` | `/api/worlds/{id}` | Load a world |
| `PUT` | `/api/worlds/{id}` | Save complete world |
| `PATCH` | `/api/worlds/{id}` | Rename display name |
| `DELETE` | `/api/worlds/{id}` | Delete world |
| `POST` | `/api/worlds/{id}/chat` | World-building chat |
| `POST` | `/api/worlds/{id}/character-chat` | Character generation chat |
| `POST` | `/api/worlds/{id}/story-chat` | Story agent chat (with tools) |
| `POST` | `/api/worlds/{id}/sync-panels-from-chat` | Structure sync |
| `POST` | `/api/worlds/{id}/ecology-generate` | One-click ecology generation |
| `POST` | `/api/worlds/{id}/outline` | Outline generation |
| `GET` | `/api/worlds/{id}/search` | Full-text search |
| `GET` | `/api/worlds/{id}/lint-references` | Reference consistency check |
| `POST` | `/api/worlds/{id}/fix-references` | Auto-fix references |
| `POST` | `/api/worlds/{id}/export-md` | Export world.md |
| `GET` | `/api/worlds/{id}/snapshots` | List snapshots |
| `GET` | `/api/worlds/{id}/snapshots/diff` | Line-level diff between snapshots |
| `POST` | `/api/worlds/{id}/snapshots/rollback` | Rollback to snapshot |
| `POST` | `/api/worlds/{id}/refresh/faction-relations` | Recalculate faction relations |
| `POST` | `/api/worlds/{id}/refresh/culture-relations` | Recalculate culture relations |
| `*` | `/api/worlds/{id}/story/*` | Story CRUD (chapters, outlines, beats, manuscripts, foreshadowing) |

---

## Testing

```bash
python -m pytest tests -q
```

For VS Code / Cursor debugging, use the included `.vscode/launch.json` configurations (F5). Install `debugpy` if missing.

---

## Roadmap

```mermaid
flowchart LR
  subgraph Near["🟢 Near Term"]
    A1[Relationship graph filtering & layout]
    A2[Extended reference linting coverage]
  end
  subgraph Mid["🟡 Mid Term"]
    B1[Outline & cast version linking]
    B2[Batch export / templates]
  end
  subgraph Far["🔵 Long Term"]
    C1[Narrative timeline & event anchors]
    C2[Collaboration & multi-world toolchain]
  end
  A1 --> A2 --> B1 --> B2 --> C1 --> C2
```

See [`todolist.md`](todolist.md) for details.

---

## More Documentation

| Document | Content |
|:--|:--|
| [`docs/readme-hero.svg`](docs/readme-hero.svg) | Repository hero banner (vector) |
| [`docs/readme-workbench.svg`](docs/readme-workbench.svg) | Workbench layout diagram (vector) |
| [`docs/gui-chat-and-sync.svg`](docs/gui-chat-and-sync.svg) | Chat & sync flow diagram |
| [`docs/gui-workbench-layout.svg`](docs/gui-workbench-layout.svg) | Three-column layout detail diagram |
| [`todolist.md`](todolist.md) | Roadmap, architecture notes & backlog |
| [`.cursor/skills/`](.cursor/skills/) | Cursor Agent Skills (9 module-specific skills) |

---

<div align="center">

**Made with ❤️ for world-builders, game masters, and storytellers.**

</div>
