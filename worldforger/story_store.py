"""情节（story）目录与 Markdown 文件读写。"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from worldforger.creative_modes import normalize_creative_mode
from worldforger.schemas import StoryChapter, World
from worldforger.world_store import outlines_dir, world_root


def story_dir(world_id: str) -> Path:
    return world_root(world_id) / "story"


def story_beats_dir(world_id: str) -> Path:
    return story_dir(world_id) / "beats"


def story_manuscript_dir(world_id: str) -> Path:
    return story_dir(world_id) / "manuscript"


def story_summaries_dir(world_id: str) -> Path:
    return story_dir(world_id) / "summaries"


def rag_index_dir(world_id: str) -> Path:
    """RAG 向量索引目录。"""
    return story_dir(world_id) / "rag_index"


def book_summary_path(world_id: str) -> Path:
    """全书叙事摘要 JSON 路径。"""
    return story_dir(world_id) / "book_summary.json"


# ── Layer 3: Narrative KG ──────────────────────────────────────────


def narrative_kg_path(world_id: str) -> Path:
    return story_dir(world_id) / "narrative_kg.json"


# ── Layer 3: Consistency Reports ──────────────────────────────────


def consistency_dir(world_id: str) -> Path:
    return story_dir(world_id) / "consistency_reports"


def consistency_path(world_id: str, chapter_id: str) -> Path:
    return consistency_dir(world_id) / f"{chapter_id}.json"


# ── Layer 3: Sentiment Logs ───────────────────────────────────────


def sentiment_dir(world_id: str) -> Path:
    return story_dir(world_id) / "sentiment_logs"


def sentiment_path(world_id: str, chapter_id: str) -> Path:
    return sentiment_dir(world_id) / f"{chapter_id}.json"


# ── Layer 4: Polished Manuscripts ─────────────────────────────────


def polished_dir(world_id: str) -> Path:
    return story_dir(world_id) / "polished"


def polished_path(world_id: str, chapter_id: str) -> Path:
    return polished_dir(world_id) / f"{chapter_id}.md"


def polish_trace_path(world_id: str, chapter_id: str) -> Path:
    return polished_dir(world_id) / f"{chapter_id}_trace.json"


def summary_path(world_id: str, chapter_id: str) -> Path:
    return story_summaries_dir(world_id) / f"{chapter_id}.json"


def macro_outline_path(world_id: str) -> Path:
    return story_dir(world_id) / "macro_outline.md"


def beat_path(world_id: str, chapter_id: str) -> Path:
    return story_beats_dir(world_id) / f"{chapter_id}.md"


def manuscript_path(world_id: str, chapter_id: str) -> Path:
    return story_manuscript_dir(world_id) / f"{chapter_id}.md"


def default_beat_rel(chapter_id: str) -> str:
    return f"story/beats/{chapter_id}.md"


def default_manuscript_rel(chapter_id: str) -> str:
    return f"story/manuscript/{chapter_id}.md"


def unit_label_for_mode(mode: str | None) -> str:
    m = normalize_creative_mode(mode)
    if m == "game":
        return "章节"
    if m in ("coc", "dnd"):
        return "跑团会话"
    return "章"


def resolve_unit_label(world: World) -> str:
    lab = (world.story.unit_label or "").strip()
    if lab:
        return lab
    return unit_label_for_mode(world.meta.creative_mode)


def ensure_story_dirs(world_id: str) -> None:
    story_dir(world_id).mkdir(parents=True, exist_ok=True)
    story_beats_dir(world_id).mkdir(parents=True, exist_ok=True)
    story_manuscript_dir(world_id).mkdir(parents=True, exist_ok=True)
    story_summaries_dir(world_id).mkdir(parents=True, exist_ok=True)
    consistency_dir(world_id).mkdir(parents=True, exist_ok=True)
    sentiment_dir(world_id).mkdir(parents=True, exist_ok=True)
    polished_dir(world_id).mkdir(parents=True, exist_ok=True)
    # Initialize SQLite tables (idempotent)
    from worldforger import sqlite_store
    sqlite_store._get_conn(world_id)  # triggers _ensure_tables


def new_chapter_id() -> str:
    return "ch_" + uuid.uuid4().hex[:8]


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def count_words(text: str) -> int:
    t = (text or "").strip()
    if not t:
        return 0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", t))
    rest = re.sub(r"[\u4e00-\u9fff]", " ", t)
    latin = len([w for w in rest.split() if w.strip()])
    return cjk + latin


def sync_chapter_word_count(world: World, chapter_id: str) -> int:
    p = manuscript_path(world.meta.id, chapter_id)
    n = count_words(read_text(p))
    for ch in world.story.chapters:
        if ch.id == chapter_id:
            ch.word_count = n
            break
    return n


def find_chapter(world: World, chapter_id: str) -> StoryChapter | None:
    for ch in world.story.chapters:
        if ch.id == chapter_id:
            return ch
    return None


def sorted_chapters(world: World) -> list[StoryChapter]:
    return sorted(world.story.chapters, key=lambda c: (c.order, c.id))


def chapters_before(world: World, chapter_id: str, limit: int) -> list[StoryChapter]:
    ordered = sorted_chapters(world)
    idx = next((i for i, c in enumerate(ordered) if c.id == chapter_id), -1)
    if idx <= 0 or limit <= 0:
        return []
    start = max(0, idx - limit)
    return ordered[start:idx]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def import_legacy_plot_outline(world: World) -> bool:
    """若存在 outlines/plot_outline.md 且粗纲为空，则导入。"""
    wid = world.meta.id
    legacy = outlines_dir(wid) / "plot_outline.md"
    if not legacy.is_file():
        return False
    macro = macro_outline_path(wid)
    if macro.is_file() and read_text(macro).strip():
        return False
    ensure_story_dirs(wid)
    body = read_text(legacy)
    header = (
        "---\n"
        f"imported_from: outlines/plot_outline.md\n"
        f"based_on_world_id: {wid}\n"
        f"based_on_world_version: {world.meta.version}\n"
        f"imported_at: {utc_now_iso()}\n"
        "---\n\n"
    )
    write_text(macro, header + body)
    world.story.outline_macro.file = "story/macro_outline.md"
    world.story.outline_macro.updated_at = utc_now_iso()
    return True


# ── 章节摘要卡片 ──────────────────────────────────────────────


def read_summary_card(world_id: str, chapter_id: str) -> dict | None:
    """读取章节摘要卡片，SQLite 优先，回退到 JSON 文件并自动迁移。"""
    from worldforger import sqlite_store

    result = sqlite_store.read_summary_card(world_id, chapter_id)
    if result is not None:
        return result
    # Fallback: read from legacy JSON file and migrate
    import json as _json

    p = summary_path(world_id, chapter_id)
    if not p.is_file():
        return None
    try:
        data = _json.loads(read_text(p))
    except _json.JSONDecodeError:
        return None
    # Auto-migrate to SQLite
    try:
        sqlite_store.write_summary_card(world_id, chapter_id, data)
    except Exception:
        pass
    return data


def write_summary_card(world_id: str, chapter_id: str, data: dict) -> None:
    """写入章节摘要卡片（SQLite + JSON 双写）。"""
    import json as _json

    from worldforger import sqlite_store

    # Write to SQLite (primary)
    try:
        sqlite_store.write_summary_card(world_id, chapter_id, data)
    except Exception:
        pass
    # Also write JSON file for backward compatibility
    write_text(summary_path(world_id, chapter_id), _json.dumps(data, ensure_ascii=False, indent=2))


def summaries_before(world_id: str, chapter_id: str, limit: int, world: World) -> list[dict]:
    """获取目标章节之前最近 N 章的摘要卡片（已有摘要的章节）。"""
    from worldforger.schemas import ChapterSummaryCard

    ordered = sorted_chapters(world)
    idx = next((i for i, c in enumerate(ordered) if c.id == chapter_id), -1)
    if idx <= 0 or limit <= 0:
        return []
    results: list[dict] = []
    for c in reversed(ordered[:idx]):
        if len(results) >= limit:
            break
        card = read_summary_card(world_id, c.id)
        if card:
            results.append(card)
        elif c.summary_card:
            results.append(c.summary_card.model_dump(mode="json"))
    results.reverse()
    return results


# ── 角色运行时状态 ───────────────────────────────────────────


def get_character_runtime_states(world: World) -> list[dict]:
    """提取所有角色的 runtime_state。"""
    states: list[dict] = []
    for ent in world.characters.entities:
        if not isinstance(ent, dict):
            continue
        rs = ent.get("runtime_state")
        if isinstance(rs, dict):
            states.append({"id": ent.get("id", ""), "name": ent.get("name", ""), "runtime_state": rs})
    return states


def update_character_runtime_state(world: World, char_id: str, updates: dict, chapter_id: str) -> None:
    """更新指定角色的 runtime_state。"""
    for ent in world.characters.entities:
        if not isinstance(ent, dict):
            continue
        if str(ent.get("id", "")).strip() == char_id.strip():
            rs = ent.get("runtime_state")
            if not isinstance(rs, dict):
                rs = {}
            rs.update(updates)
            rs["last_updated_chapter"] = chapter_id
            ent["runtime_state"] = rs
            return


# ── Layer 3: Narrative KG read/write ──────────────────────────────


def read_narrative_kg(world_id: str) -> dict | None:
    import json as _json

    p = narrative_kg_path(world_id)
    if not p.is_file():
        return None
    try:
        return _json.loads(read_text(p))
    except _json.JSONDecodeError:
        return None


def write_narrative_kg(world_id: str, data: dict) -> None:
    import json as _json

    write_text(narrative_kg_path(world_id), _json.dumps(data, ensure_ascii=False, indent=2))


# ── Layer 3: Consistency Report read/write ────────────────────────


def read_consistency_report(world_id: str, chapter_id: str) -> dict | None:
    """读取一致性审校报告，SQLite 优先，回退到 JSON 文件并自动迁移。"""
    from worldforger import sqlite_store

    result = sqlite_store.read_consistency_report(world_id, chapter_id)
    if result is not None:
        return result
    # Fallback: legacy JSON file
    import json as _json

    p = consistency_path(world_id, chapter_id)
    if not p.is_file():
        return None
    try:
        data = _json.loads(read_text(p))
    except _json.JSONDecodeError:
        return None
    try:
        sqlite_store.write_consistency_report(world_id, chapter_id, data)
    except Exception:
        pass
    return data


def write_consistency_report(world_id: str, chapter_id: str, data: dict) -> None:
    """写入一致性审校报告（SQLite + JSON 双写）。"""
    import json as _json

    from worldforger import sqlite_store

    try:
        sqlite_store.write_consistency_report(world_id, chapter_id, data)
    except Exception:
        pass
    write_text(consistency_path(world_id, chapter_id), _json.dumps(data, ensure_ascii=False, indent=2))


# ── Layer 3: Sentiment Log read/write ─────────────────────────────


def read_sentiment_log(world_id: str, chapter_id: str) -> dict | None:
    """读取情感日志，SQLite 优先，回退到 JSON 文件并自动迁移。"""
    from worldforger import sqlite_store

    result = sqlite_store.read_sentiment_log(world_id, chapter_id)
    if result is not None:
        return result
    # Fallback: legacy JSON file
    import json as _json

    p = sentiment_path(world_id, chapter_id)
    if not p.is_file():
        return None
    try:
        data = _json.loads(read_text(p))
    except _json.JSONDecodeError:
        return None
    try:
        sqlite_store.write_sentiment_log(world_id, chapter_id, data)
    except Exception:
        pass
    return data


def write_sentiment_log(world_id: str, chapter_id: str, data: dict) -> None:
    """写入情感日志（SQLite + JSON 双写）。"""
    import json as _json

    from worldforger import sqlite_store

    try:
        sqlite_store.write_sentiment_log(world_id, chapter_id, data)
    except Exception:
        pass
    write_text(sentiment_path(world_id, chapter_id), _json.dumps(data, ensure_ascii=False, indent=2))


# ── P2-9: Chapter Version Snapshots ──────────────────────────────────

MAX_CHAPTER_SNAPSHOTS = 10


def chapter_snapshots_dir(world_id: str, chapter_id: str) -> Path:
    return story_dir(world_id) / "snapshots" / chapter_id


def chapter_snapshot_path(world_id: str, chapter_id: str, version: int) -> Path:
    return chapter_snapshots_dir(world_id, chapter_id) / f"v{version}.md"


def save_chapter_snapshot(world_id: str, chapter_id: str) -> int | None:
    """Save current manuscript as a new snapshot version. Returns version number or None."""
    src = manuscript_path(world_id, chapter_id)
    if not src.is_file():
        return None
    text = read_text(src)
    if not text.strip():
        return None
    snap_dir = chapter_snapshots_dir(world_id, chapter_id)
    snap_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(
        [int(p.stem[1:]) for p in snap_dir.glob("v*.md") if p.stem[1:].isdigit()]
    )
    next_v = max(existing) + 1 if existing else 1
    # Skip if identical to the latest snapshot
    if existing:
        latest = read_text(chapter_snapshot_path(world_id, chapter_id, existing[-1]))
        if latest.strip() == text.strip():
            return None
    # Enforce max snapshots
    while len(existing) >= MAX_CHAPTER_SNAPSHOTS:
        oldest = existing.pop(0)
        try:
            chapter_snapshot_path(world_id, chapter_id, oldest).unlink()
        except OSError:
            pass
    write_text(chapter_snapshot_path(world_id, chapter_id, next_v), text)
    return next_v


def list_chapter_snapshots(world_id: str, chapter_id: str) -> list[dict]:
    """List all snapshots for a chapter with metadata."""
    snap_dir = chapter_snapshots_dir(world_id, chapter_id)
    if not snap_dir.is_dir():
        return []
    result: list[dict] = []
    for p in sorted(snap_dir.glob("v*.md"), key=lambda x: int(x.stem[1:]) if x.stem[1:].isdigit() else 0):
        if not p.stem[1:].isdigit():
            continue
        v = int(p.stem[1:])
        stat = p.stat()
        result.append({
            "version": v,
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "word_count": count_words(read_text(p)),
        })
    return result


def read_chapter_snapshot(world_id: str, chapter_id: str, version: int) -> str:
    """Read a specific snapshot version."""
    p = chapter_snapshot_path(world_id, chapter_id, version)
    if not p.is_file():
        raise FileNotFoundError(f"snapshot v{version} not found for chapter {chapter_id}")
    return read_text(p)
