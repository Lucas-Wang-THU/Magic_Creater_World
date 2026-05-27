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

### Windows One-Click Setup (Recommended)

```
1. Double-click setup.bat   → Auto-detect environment, install deps, configure .env
2. Double-click launch.bat  → Start server, browser opens automatically
```

> Optional: right-click `launch.bat` → Send to desktop → right-click shortcut → Properties → Change Icon → select `icon.ico` for one-click desktop launch.

### Manual Setup

```bash
# 1. Create virtual environment (recommended)
python -m venv .venv

# Activate on Linux / macOS
source .venv/bin/activate

# Activate on Windows
.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure your API key
cp .env.example .env          # Linux / macOS
copy .env.example .env        # Windows
# Edit .env and fill in PARATERA_API_KEY

# 4. Launch
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
| 🧩 **Structure Sync + Proofreader** | 3-Agent pipeline: Architect→Synchronizer→Proofreader→Supplement loop, auto-extracting JSON patches with ID-aware incremental merge into forms |
| 🗺️ **11 World Modules** | Geography · Ecology · Power System · Attributes · Items · Cultures · Factions · History · Economy · Characters · Story |
| 📊 **Relationship Visualization** | Mermaid diagrams: relationship networks, skill trees, profession graphs, timelines, causal chains |
| 🧠 **Semantic Memory (RAG)** | Local vector index (ChromaDB) with semantic retrieval of prior narrative fragments for coherence |
| 🔍 **Data Tools** | Full-text search, reference consistency linting & auto-fix, version snapshots with diff & rollback |
| 📤 **Export** | Auto-generated `world.md` human-readable handbook; outlines written to `outlines/` |
| 💾 **Local-First** | All data lives on your disk — no cloud service required |

</div>

### Two Conversation Paths (3-Agent Pipeline)

| Path | Description |
|:--|:--|
| **Path 1 · Dialogue** | Natural language chat with the "World Architect"; optionally attach `world.md` as context |
| **Path 2 · Structure Sync** | 3-Agent pipeline: **Synchronizer** extracts JSON from architect reply → **Unified Proofreader** audits completeness AND directly outputs missing JSON in a single call (no architect round-trip) → **ID-aware incremental merge** — existing entries updated, new entries appended, never overwritten. Empty synchronizer output automatically skips proofreading. |

The structure sync model defaults to the main chat model. Set `STRUCTURE_SYNC_MODEL` to use a different one. The proofreader model can be set via `PROOFREADER_MODEL` (use a smaller model for speed). Proofreading rounds can be configured via `PROOFREADER_MAX_RETRIES` and adjusted in the UI (0 = skip proofreader).

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
  subgraph Path2["🧩 Path 2 · 3-Agent Pipeline"]
    C[Structure Sync]
    D[Proofreader]
    E[Architect Supplement]
  end
  subgraph Local["💾 Local Data"]
    F[(world.json)]
    G[world.md export]
  end
  A --> B
  B --> C
  C --> D
  D -->|pass| F
  D -->|gaps| E
  E --> C
  F --> G
```

**3-Agent Sync Pipeline (sequence)**

```mermaid
sequenceDiagram
  participant U as 👤 User
  participant W as 🖥️ Workbench
  participant API as ⚡ FastAPI
  participant S as 🤖 Synchronizer
  participant P as 🔍 Proofreader
  participant A as 🎨 Architect

  U->>W: Send message (sync optional)
  W->>API: POST …/chat
  API-->>W: Architect reply

  alt Sync enabled
    W->>API: POST …/sync-panels-from-chat
    API->>S: Extract JSON patch(v1)
    S-->>API: patch
    loop Proofread→Supplement (up to N rounds)
      API->>P: Compare "Architect reply" vs "Sync JSON" vs "world.json"
      P-->>API: verdict: ok / retry
      opt verdict=retry
        API->>A: Supplement questions
        A-->>API: Supplement reply
        API->>S: Extract new patch
        S-->>API: patch(vN)
      end
    end
    Note over API: ID-aware incremental merge
    API-->>W: world + updated_sections + proofreader audit
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
| **Story** | Chapters, macro outlines, beat outlines, manuscripts | Foreshadowing timeline · RAG semantic retrieval · Narrative KG · Consistency audit · Sentiment arc · Polisher diff view |

### 🤖 AI Conversation Features

| Feature | Description |
|:--|:--|
| **World-building Chat** | Free-form conversation with the Architect agent; quick chips; Ctrl+Enter to send |
| **Character Generation** | Dedicated chat thread with optional guide and structure sync |
| **Story Agent** | Tool calling: foreshadowing CRUD, manuscript generation, auto-detection of markdown code blocks |
| **RAG Semantic Retrieval** | Local vector index (ChromaDB + BGE embedding), intelligently retrieves relevant prior fragments for writing context |
| **Narrative Knowledge Graph** | Lightweight event-entity-time triples tracking character state evolution and key item flow |
| **Consistency Auditor** | 7-dimension automatic audit (position / personality / items / POV / foreshadowing / emotional continuity / timeline), non-blocking post-chapter check |
| **Sentiment Arc Tracker** | Per-chapter emotional tone analysis + Mermaid curve visualization for cross-chapter emotional coherence |
| **Polisher Agent** | Consistency-audit ↔ polish feedback loop (up to N rounds), 9 hard rules for de-AI-ification (dash restraint / paragraph merging / sentence variation / show-don't-tell / etc.), original ↔ polished side-by-side diff comparison |
| **Creative Modes** | Novel / Game / CoC / DnD — each injects different system prompts and terminology |
| **One-click Ecology** | Auto-generate ecology settings from current world context |

### 🔧 Data Tools

| Tool | Description |
|:--|:--|
| **Full-text Search** | Searches both `world.json` and `world.md` simultaneously |
| **Reference Linter** | Cross-module ID reference validation (regions, factions, etc.) |
| **Auto-fix** | Conservative reference repair with `dry_run` preview |
| **Version Snapshots** | Auto-snapshot on every save; line-level diff viewer; one-click rollback; per-snapshot delete |
| **RAG Index Readiness Indicator** | Story workbench header status dot + sidebar context panel (prev-chapter summary / character states / index stats) |
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
| `chromadb` | Local vector database (RAG semantic retrieval) |
| `sentence-transformers` | Local text embedding (BAAI/bge-small-zh-v1.5) |
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
| `PROOFREADER_MODEL` | Optional: dedicated model for proofreader (use smaller model for speed) | Same as `STRUCTURE_SYNC_MODEL` |
| `PROOFREADER_MAX_RETRIES` | Optional: max proofreader→architect supplement rounds (0=skip) | `3` |
| `MCW_EMBEDDING_MODEL` | Optional: local embedding model name | `BAAI/bge-small-zh-v1.5` |
| `MCW_EMBEDDING_BACKEND` | `auto` / `api` / `local`: `auto` skips HuggingFace if model not cached | `auto` |
| `MCW_HF_ENDPOINT` | Optional HF mirror (e.g. `https://hf-mirror.com`) | *(empty)* |
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
    ├── outlines/           ← Character & plot outline exports
    ├── story/               ← Chapter manuscripts, summary cards, RAG index
    │   ├── macro_outline.md
    │   ├── ch_xxx_manuscript.md
    │   ├── ch_xxx_summary_card.json
    │   └── rag_index/        ← ChromaDB vector index
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
| `POST` | `/api/worlds/{id}/sync-panels-from-chat` | Structure sync (with proofreader audit) |
| `POST` | `/api/worlds/{id}/ecology-generate` | One-click ecology generation |
| `POST` | `/api/worlds/{id}/outline` | Outline generation |
| `GET` | `/api/worlds/{id}/search` | Full-text search |
| `GET` | `/api/worlds/{id}/lint-references` | Reference consistency check |
| `POST` | `/api/worlds/{id}/fix-references` | Auto-fix references |
| `POST` | `/api/worlds/{id}/export-md` | Export world.md |
| `GET` | `/api/worlds/{id}/snapshots` | List snapshots |
| `GET` | `/api/worlds/{id}/snapshots/diff` | Line-level diff between snapshots |
| `POST` | `/api/worlds/{id}/snapshots/rollback` | Rollback to snapshot |
| `DELETE` | `/api/worlds/{id}/snapshots/{version}` | Delete a single snapshot |
| `DELETE` | `/api/worlds/{id}/snapshots` | Clear all snapshots |
| `POST` | `/api/worlds/{id}/refresh/faction-relations` | Recalculate faction relations |
| `POST` | `/api/worlds/{id}/refresh/culture-relations` | Recalculate culture relations |
| `GET` | `/api/worlds/{id}/story/rag/stats` | RAG index statistics & readiness |
| `GET` | `/api/worlds/{id}/story/narrative-kg` | Narrative knowledge graph (entities / events / foreshadowing) |
| `GET` | `/api/worlds/{id}/story/consistency-report/{chapter_id}` | Chapter consistency audit report |
| `GET` | `/api/worlds/{id}/story/sentiment-arc` | Sentiment arc data + Mermaid chart |
| `GET` | `/api/worlds/{id}/story/manuscript/{chapter_id}/polished` | Polished manuscript + metadata |
| `GET` | `/api/worlds/{id}/story/manuscript/{chapter_id}/polish-trace` | Audit ↔ polish loop round tracing |
| `PATCH` | `/api/worlds/{id}/story/writing-defaults` | Toggle writing enhancement switches (KG / audit / sentiment / polisher / max rounds) |
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
  subgraph Done["✅ Completed"]
    C1[3-Agent Proofreader Pipeline]
    C2[ID-Aware Incremental Merge]
    C3[RAG Semantic Retrieval]
    C4[Narrative Knowledge Graph]
    C5[Consistency Audit Agent]
    C6[Sentiment Arc Tracker]
    C7[Polisher Agent + Audit↔Polish Loop]
    C8[Parallel Post-processing Optimization]
    C9[Unified Proofreader + Parallel Beat Gen]
  end
  A1 --> A2 --> B1 --> B2
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
