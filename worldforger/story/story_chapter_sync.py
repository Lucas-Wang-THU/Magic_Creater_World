"""将 story/beats/*.md 与 world.story.chapters[] 对齐（发现缺失章、同步标题）。"""

from __future__ import annotations

import re

from worldforger.schemas import StoryChapter, World
from worldforger.story.story_store import (
    beat_path,
    default_beat_rel,
    default_manuscript_rel,
    macro_outline_path,
    manuscript_path,
    read_text,
    sorted_chapters,
    story_beats_dir,
    write_text,
)


_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9}


def _chapter_number(raw: str) -> int | None:
    value = (raw or "").strip()
    if not value:
        return None
    if value.isdigit():
        number = int(value)
        return number if number > 0 else None
    total = 0
    current = 0
    units = {"十": 10, "百": 100, "千": 1000}
    for char in value:
        if char in _CN_DIGITS:
            current = _CN_DIGITS[char]
        elif char in units:
            unit = units[char]
            total += (current or 1) * unit
            current = 0
        else:
            return None
    number = total + current
    return number if number > 0 else None


def strip_chapter_title_prefix(raw_title: str, fallback_order: int | None = None) -> str:
    """Remove duplicated chapter labels from a stored chapter title.

    Frontend already displays the order as "第一章"; storing titles like
    "第一章：启程" would render as "第一章 第一章：启程".
    """
    title = re.sub(r"\s+", " ", (raw_title or "")).strip()
    title = title.strip(" -*_")
    if fallback_order is not None:
        title = re.sub(r"^合[：:]\s*", "", title).strip()
    if not title:
        return ""
    pattern = re.compile(
        r"^第\s*([零〇一二两三四五六七八九十百千\d]+)\s*(?:次\s*)?"
        r"(跑团会话|章节|章|回|话|节)\s*(?:[：:、.\-—]\s*|\s+)?(.+?)\s*$",
        re.IGNORECASE,
    )
    m = pattern.match(title)
    if m:
        n = _chapter_number(m.group(1))
        if fallback_order is None or n is None or n == fallback_order:
            cleaned = (m.group(3) or "").strip(" -*_：:")
            cleaned = re.sub(r"^合[：:]\s*", "", cleaned).strip()
            if cleaned:
                return cleaned
    english = re.match(
        r"^(?:chapter|session|scene|act|part)\s*(\d+)\s*(?:[：:、.\-—]\s*|\s+)?(.+?)\s*$",
        title,
        re.IGNORECASE,
    )
    if english:
        n = _chapter_number(english.group(1))
        if fallback_order is None or n is None or n == fallback_order:
            cleaned = (english.group(2) or "").strip(" -*_：:")
            cleaned = re.sub(r"^合[：:]\s*", "", cleaned).strip()
            if cleaned:
                return cleaned
    numbered = re.match(r"^\s*(\d+)[.)、]\s*(.+?)\s*$", title)
    if numbered:
        n = _chapter_number(numbered.group(1))
        if fallback_order is None or n is None or n == fallback_order:
            cleaned = (numbered.group(2) or "").strip(" -*_：:")
            cleaned = re.sub(r"^合[：:]\s*", "", cleaned).strip()
            if cleaned:
                return cleaned
    return title


def outline_chapters_from_markdown(content: str) -> list[tuple[int, str]]:
    """Extract explicit chapter/session headings as ``(order, title)`` rows."""
    rows: dict[int, str] = {}
    max_declared_chapters: int | None = None
    for line in (content or "").splitlines()[:20]:
        if not re.match(r"^\s*#{1,6}\s+", line):
            continue
        m_count = re.search(
            r"(?:粗纲|大纲|全书|全卷|第一卷)[^\n]{0,50}[（(]\s*([零〇一二两三四五六七八九十百千\d]+)\s*章[）)]",
            line,
            re.IGNORECASE,
        )
        if m_count:
            max_declared_chapters = _chapter_number(m_count.group(1))
            break
    prefix = r"\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)、]\s+)?(?:\*\*)?\s*"
    cn = re.compile(
        prefix
        + r"第\s*([零〇一二两三四五六七八九十百千\d]+)\s*(?:次\s*)?"
          r"(跑团会话|章节|章|回|话|节)\s*(?:[：:、.\-—]\s*)?(.*?)\s*(?:\*\*)?\s*$",
        re.IGNORECASE,
    )
    session = re.compile(
        prefix + r"跑团会话\s*([零〇一二两三四五六七八九十百千\d]+)"
        r"\s*(?:[：:、.\-—]\s*)?(.*?)\s*(?:\*\*)?\s*$",
        re.IGNORECASE,
    )
    english = re.compile(
        prefix + r"chapter\s+(\d+)\s*(?:[：:、.\-—]\s*)?(.*?)\s*(?:\*\*)?\s*$",
        re.IGNORECASE,
    )
    table_row = re.compile(r"^\s*\|\s*([^|\n]+?)\s*\|\s*([^|\n]+?)\s*\|")
    for line in (content or "").splitlines():
        if len(line) > 240:
            continue
        table_match = table_row.match(line)
        if table_match:
            first = table_match.group(1).strip()
            second = table_match.group(2).strip()
            if not re.fullmatch(r"[-:：\s]+", first) and first not in {"章号", "章节", "章", "序号"}:
                order_text = first
                label_match = re.search(
                    r"第\s*([零〇一二两三四五六七八九十百千\d]+)\s*(?:次\s*)?(?:跑团会话|章节|章|回|话|节)",
                    order_text,
                    re.IGNORECASE,
                )
                if label_match:
                    order_text = label_match.group(1)
                order = _chapter_number(order_text)
                if order is not None:
                    title = strip_chapter_title_prefix(second, fallback_order=order)
                    rows[order] = title
                    continue
        match = cn.match(line) or session.match(line) or english.match(line)
        if not match:
            continue
        order = _chapter_number(match.group(1))
        if order is None:
            continue
        title = strip_chapter_title_prefix(
            match.group(3) if match.re is cn else match.group(2),
            fallback_order=order,
        )
        rows[order] = title
    result = sorted(rows.items())
    if max_declared_chapters:
        result = [(order, title) for order, title in result if order <= max_declared_chapters]
    return result


def reconcile_macro_outline_chapters(world: World, content: str) -> tuple[World, list[str]]:
    """Align explicit macro-outline chapter headings to existing chapter orders.

    Existing chapter IDs and files are preserved. A changed outline title updates
    the chapter at the same order; only previously missing orders create records.
    """
    notes: list[str] = []
    entries = outline_chapters_from_markdown(content)
    if not entries:
        return world, notes

    by_order: dict[int, StoryChapter] = {}
    for chapter in sorted_chapters(world):
        by_order.setdefault(chapter.order, chapter)

    existing_ids = {c.id for c in world.story.chapters}
    unit = (world.story.unit_label or "章").strip() or "章"
    for order, raw_title in entries:
        title = raw_title or f"第{order}{unit}"
        chapter = by_order.get(order)
        if chapter is not None:
            old_title = (chapter.title or "").strip()
            if title != old_title:
                chapter.title = title
                notes.append(f"第 {order} 章沿用 {chapter.id} 并更新标题：{old_title or '（空）'} → {title}")
            continue

        base_id = f"ch_outline_{order:04d}"
        cid = base_id
        suffix = 2
        while cid in existing_ids:
            cid = f"{base_id}_{suffix}"
            suffix += 1
        chapter = StoryChapter(
            id=cid,
            order=order,
            title=title,
            beat_file=default_beat_rel(cid),
            manuscript_file=default_manuscript_rel(cid),
        )
        world.story.chapters.append(chapter)
        by_order[order] = chapter
        existing_ids.add(cid)
        write_text(beat_path(world.meta.id, cid), f"# {title}\n\n（细纲）\n")
        write_text(manuscript_path(world.meta.id, cid), f"# {title}\n\n")
        notes.append(f"粗纲新增第 {order} 章：{cid}（{title}）")

    world.story.chapters.sort(key=lambda c: (c.order, c.id))
    return world, notes


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
    macro = read_text(macro_outline_path(wid))
    if macro.strip():
        world, macro_notes = reconcile_macro_outline_chapters(world, macro)
        notes.extend(macro_notes)
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

        # Only auto-set title from beat if chapter title is empty (don't overwrite user-set titles)
        if beat_title and not (ch.title or "").strip():
            ch.title = beat_title
            notes.append(f"{cid} 标题从细纲补全：→ {beat_title}")

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
