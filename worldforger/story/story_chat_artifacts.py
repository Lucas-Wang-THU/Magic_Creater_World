"""从情节对话回复中自动落盘 Markdown 块与伏笔操作。"""

from __future__ import annotations

import re
from typing import Any

from worldforger.story.foreshadow_apply import apply_foreshadow_operations, parse_story_foreshadow_blocks
from worldforger.schemas import StoryChapter, World
from worldforger.story.story_chapter_sync import title_from_beat_markdown
from worldforger.story.story_store import (
    beat_path,
    default_beat_rel,
    default_manuscript_rel,
    macro_outline_path,
    manuscript_path,
    sync_chapter_word_count,
    write_text,
)


def parse_story_md_blocks(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    raw = text or ""
    for m in re.finditer(r"```([^\n`]+)\s*\n([\s\S]*?)```", raw):
        tag = (m.group(1) or "").strip().lower()
        content = (m.group(2) or "").strip()
        if not content:
            continue
        if tag == "story-macro":
            blocks.append({"kind": "macro", "chapter_id": "", "content": content})
        elif tag.startswith("story-beat:"):
            blocks.append(
                {
                    "kind": "beat",
                    "chapter_id": tag[len("story-beat:") :].strip(),
                    "content": content,
                }
            )
        elif tag.startswith("story-manuscript:"):
            blocks.append(
                {
                    "kind": "manuscript",
                    "chapter_id": tag[len("story-manuscript:") :].strip(),
                    "content": content,
                }
            )
    return blocks


def _ensure_chapter_registered(world: World, chapter_id: str, content: str = "") -> None:
    """如果 chapter_id 尚未在 world.story.chapters 中，自动注册。

    确保 Agent 通过 ```story-beat:xxx 代码块新建章节时
    立即出现在 chapters[] 中，无需等待下次 GET /story 的 reconcile。
    """
    if any(c.id == chapter_id for c in world.story.chapters):
        return
    max_order = max((c.order for c in world.story.chapters), default=0)
    beat_title = title_from_beat_markdown(content) if content else ""
    ch = StoryChapter(
        id=chapter_id,
        order=max_order + 1,
        title=beat_title or chapter_id,
        beat_file=default_beat_rel(chapter_id),
        manuscript_file=default_manuscript_rel(chapter_id),
    )
    world.story.chapters.append(ch)


def auto_apply_story_artifacts_from_reply(
    world: World,
    text: str,
) -> tuple[World, list[str], list[str]]:
    """返回 (world, applied, warnings)。"""
    applied: list[str] = []
    warnings: list[str] = []
    wid = world.meta.id

    for block in parse_story_md_blocks(text):
        kind = block.get("kind") or ""
        content = block.get("content") or ""
        if not content:
            continue
        if kind == "macro":
            write_text(macro_outline_path(wid), content)
            applied.append("写入粗纲 macro_outline.md")
            continue
        cid = (block.get("chapter_id") or "").strip()
        if not cid:
            warnings.append(f"跳过 {kind}：缺少 chapter_id")
            continue
        # 自动注册未存在的章节（避免依赖 reconcile 的延迟补注册）
        _ensure_chapter_registered(world, cid, content)
        if kind == "beat":
            write_text(beat_path(wid, cid), content)
            applied.append(f"写入细纲 beats/{cid}.md")
        elif kind == "manuscript":
            write_text(manuscript_path(wid, cid), content)
            sync_chapter_word_count(world, cid)
            ch = next((c for c in world.story.chapters if c.id == cid), None)
            if ch:
                ch.status = "drafting"
            applied.append(f"写入文稿 manuscript/{cid}.md")
            # Trigger post-generation hooks asynchronously (fire-and-forget)
            try:
                import asyncio as _asyncio
                from worldforger.story.story_service import (
                    _try_generate_summary_card, _try_track_sentiment,
                    _try_update_runtime_states, _try_index_chapter,
                )
                for hook in [_try_generate_summary_card, _try_track_sentiment,
                             _try_update_runtime_states, _try_index_chapter]:
                    _asyncio.ensure_future(hook(world, cid, content))
            except Exception:
                pass  # best-effort

    fs_ops = parse_story_foreshadow_blocks(text)
    if fs_ops:
        world, fs_applied, fs_warn = apply_foreshadow_operations(world, fs_ops)
        applied.extend(fs_applied)
        warnings.extend(fs_warn)

    return world, applied, warnings
