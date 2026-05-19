"""将 story/beats/*.md 与 world.story.chapters[] 对齐（发现缺失章、同步标题）。"""

from __future__ import annotations

import re

from worldforger.schemas import StoryChapter, World
from worldforger.story_store import (
    default_beat_rel,
    default_manuscript_rel,
    read_text,
    sorted_chapters,
    story_beats_dir,
)


def title_from_beat_markdown(content: str) -> str:
    """取细纲首条 Markdown 一级标题作为章节名。"""
    for line in (content or "").splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^#\s+(.+?)\s*$", s)
        if m:
            return m.group(1).strip()
    return ""


def reconcile_story_chapters(world: World) -> tuple[World, list[str]]:
    """
    - 磁盘存在 beats/<id>.md 但 JSON 无条目 → 自动建章
    - 细纲有一级标题且与 chapters[].title 不一致 → 以细纲标题为准
    """
    wid = world.meta.id
    notes: list[str] = []
    by_id = {c.id: c for c in world.story.chapters}
    beats_root = story_beats_dir(wid)
    if not beats_root.is_dir():
        return world, notes

    max_order = max((c.order for c in world.story.chapters), default=0)

    for path in sorted(beats_root.glob("*.md")):
        cid = path.stem.strip()
        if not cid:
            continue
        content = read_text(path)
        beat_title = title_from_beat_markdown(content)
        ch = by_id.get(cid)
        if ch is None:
            max_order += 1
            ch = StoryChapter(
                id=cid,
                order=max_order,
                title=beat_title or cid,
                beat_file=default_beat_rel(cid),
                manuscript_file=default_manuscript_rel(cid),
            )
            world.story.chapters.append(ch)
            by_id[cid] = ch
            notes.append(f"已从细纲文件注册章节 {cid}")
        else:
            if not (ch.beat_file or "").strip():
                ch.beat_file = default_beat_rel(cid)
            if not (ch.manuscript_file or "").strip():
                ch.manuscript_file = default_manuscript_rel(cid)

        if beat_title and beat_title != (ch.title or "").strip():
            prev = (ch.title or "").strip() or "（空）"
            ch.title = beat_title
            notes.append(f"{cid} 标题对齐细纲：{prev} → {beat_title}")

    return world, notes


def chapter_display_for_prompt(world: World) -> list[dict[str, str | int]]:
    """供 API/前端展示的章节列表（已排序）。"""
    rows: list[dict[str, str | int]] = []
    for ch in sorted_chapters(world):
        beat_title = ""
        p = story_beats_dir(world.meta.id) / f"{ch.id}.md"
        if p.is_file():
            beat_title = title_from_beat_markdown(read_text(p))
        title = (ch.title or "").strip() or beat_title or ch.id
        rows.append(
            {
                "id": ch.id,
                "order": ch.order,
                "title": title,
                "status": ch.status,
                "beat_title": beat_title,
                "has_beat": p.is_file(),
            }
        )
    return rows
