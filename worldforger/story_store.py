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
