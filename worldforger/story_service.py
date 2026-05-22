"""情节生成与章节管理业务逻辑。"""

from __future__ import annotations

from worldforger.llm import chat_completion
from worldforger.schemas import StoryChapter, StoryPerson, World
from worldforger.story_prompts import (
    build_chapter_summary_user_payload,
    build_character_state_user_payload,
    build_manuscript_user_payload,
    chapter_beats_system,
    chapter_list_for_prompt,
    chapter_summary_system,
    character_state_extract_system,
    compact_world_snippet,
    macro_outline_system,
    manuscript_system,
)
from worldforger.story_store import (
    beat_path,
    chapters_before,
    default_beat_rel,
    default_manuscript_rel,
    ensure_story_dirs,
    get_character_runtime_states,
    import_legacy_plot_outline,
    macro_outline_path,
    manuscript_path,
    new_chapter_id,
    read_text,
    resolve_unit_label,
    sorted_chapters,
    summaries_before,
    sync_chapter_word_count,
    unit_label_for_mode,
    update_character_runtime_state,
    utc_now_iso,
    write_summary_card,
    write_text,
)
from worldforger.world_store import world_context_for_prompt


def apply_unit_label_from_mode(world: World, creative_mode: str | None) -> None:
    world.story.unit_label = unit_label_for_mode(
        creative_mode or world.meta.creative_mode
    )


def add_chapter(world: World, *, title: str = "", order: int | None = None) -> StoryChapter:
    ensure_story_dirs(world.meta.id)
    cid = new_chapter_id()
    orders = [c.order for c in world.story.chapters]
    ord_val = order if order is not None else (max(orders) + 1 if orders else 1)
    ch = StoryChapter(
        id=cid,
        order=ord_val,
        title=(title or "").strip() or f"{resolve_unit_label(world)}{ord_val}",
        beat_file=default_beat_rel(cid),
        manuscript_file=default_manuscript_rel(cid),
    )
    write_text(beat_path(world.meta.id, cid), f"# {ch.title}\n\n（细纲）\n")
    write_text(manuscript_path(world.meta.id, cid), f"# {ch.title}\n\n")
    world.story.chapters.append(ch)
    return ch


def remove_chapter(world: World, chapter_id: str) -> bool:
    before = len(world.story.chapters)
    world.story.chapters = [c for c in world.story.chapters if c.id != chapter_id]
    if len(world.story.chapters) == before:
        return False
    wid = world.meta.id
    for p in (beat_path(wid, chapter_id), manuscript_path(wid, chapter_id)):
        if p.is_file():
            try:
                p.unlink()
            except OSError:
                pass
    # 清理 RAG 索引中该章节的向量
    try:
        from worldforger.chapter_indexer import ChapterIndexer
        ChapterIndexer(wid).remove_chapter(chapter_id)
    except Exception:
        pass
    return True


async def generate_macro_outline(
    world: World,
    *,
    prompt: str,
    creative_mode: str | None,
    include_world_md: bool,
) -> str:
    mode_eff = creative_mode or world.meta.creative_mode
    apply_unit_label_from_mode(world, mode_eff)
    system = macro_outline_system(world, creative_mode=mode_eff)
    ctx = compact_world_snippet(world, include_markdown=include_world_md)
    user = (
        f"{chapter_list_for_prompt(world)}\n\n"
        f"【用户要求】\n{prompt.strip()}\n\n"
        f"【世界设定】\n{ctx}"
    )
    reply = await chat_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.65,
        max_tokens=8192,
    )
    wid = world.meta.id
    ensure_story_dirs(wid)
    header = (
        "---\n"
        f"based_on_world_id: {wid}\n"
        f"based_on_world_version: {world.meta.version}\n"
        f"generated_at: {utc_now_iso()}\n"
        "---\n\n"
    )
    write_text(macro_outline_path(wid), header + reply)
    world.story.outline_macro.file = "story/macro_outline.md"
    world.story.outline_macro.updated_at = utc_now_iso()
    return reply


async def generate_chapter_beats(
    world: World,
    *,
    chapter_ids: list[str],
    prompt: str,
    creative_mode: str | None,
    include_world_md: bool,
) -> dict[str, str]:
    mode_eff = creative_mode or world.meta.creative_mode
    macro = read_text(macro_outline_path(world.meta.id))
    system = chapter_beats_system(world, creative_mode=mode_eff)
    ctx = compact_world_snippet(world, include_markdown=include_world_md)
    out: dict[str, str] = {}
    for cid in chapter_ids:
        ch = next((c for c in world.story.chapters if c.id == cid), None)
        if not ch:
            continue
        # 注入前一章摘要卡片（衔接检查用）
        prev_summary_block = ""
        prev_cards = summaries_before(world.meta.id, cid, 1, world)
        if prev_cards:
            pc = prev_cards[0]
            prev_summary_block = (
                "\n【前一章摘要（务必检查衔接）】\n"
                f"事件：{pc.get('main_events', '')}\n"
                f"结尾钩子：{pc.get('ending_hook', '')}\n"
            )
        user = (
            f"{chapter_list_for_prompt(world)}\n\n"
            f"【目标】仅为 id={cid}（{ch.title}）撰写细纲。\n"
            f"【用户要求】\n{prompt.strip()}\n\n"
            f"【粗纲】\n{macro[:8000]}\n\n"
            f"【世界设定】\n{ctx}"
            f"{prev_summary_block}"
        )
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.6,
            max_tokens=4096,
        )
        write_text(beat_path(world.meta.id, cid), reply)
        out[cid] = reply
    return out


async def generate_manuscript(
    world: World,
    *,
    chapter_id: str,
    prompt: str,
    creative_mode: str | None,
    person: StoryPerson | None,
    attach_prev_chapters: int,
    include_world_md: bool | None,
) -> str:
    mode_eff = creative_mode or world.meta.creative_mode
    wd = world.story.writing_defaults
    inc_md = include_world_md if include_world_md is not None else wd.include_world_md
    prev_n = max(0, min(5, attach_prev_chapters))
    person_eff = person or world.story.narrator.person
    macro = read_text(macro_outline_path(world.meta.id)) if wd.include_macro_outline else ""
    beat = read_text(beat_path(world.meta.id, chapter_id)) if wd.include_chapter_beats else ""
    prev: list[tuple[str, str]] = []
    for pch in chapters_before(world, chapter_id, prev_n):
        prev.append((pch.id, read_text(manuscript_path(world.meta.id, pch.id))))

    # ── RAG 检索：语义查询相关前文片段 ──
    rag_chunks = await _try_retrieve_rag_chunks(world, chapter_id, beat)

    system = manuscript_system(world, creative_mode=mode_eff, person=person_eff)
    user = build_manuscript_user_payload(
        world,
        chapter_id=chapter_id,
        macro_outline=macro,
        beat_text=beat,
        prev_manuscripts=prev,
        user_hint=prompt,
        include_world_md=inc_md,
        rag_chunks=rag_chunks if rag_chunks else None,
    )
    reply = await chat_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.75,
        max_tokens=8192,
    )
    write_text(manuscript_path(world.meta.id, chapter_id), reply)
    sync_chapter_word_count(world, chapter_id)
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    if ch:
        ch.status = "drafting"

    # ── 收尾：生成章节摘要卡片 ──
    await _try_generate_summary_card(world, chapter_id, reply)

    # ── 收尾：更新角色运行时状态 ──
    await _try_update_runtime_states(world, chapter_id, reply)

    # ── 收尾：索引新章节到向量库 ──
    await _try_index_chapter(world, chapter_id, reply)

    return reply


def try_import_legacy(world: World) -> bool:
    return import_legacy_plot_outline(world)


# ── 收尾：章节摘要卡片 ──────────────────────────────────────


async def _try_generate_summary_card(world: World, chapter_id: str, manuscript_text: str) -> None:
    """正文生成后，调用轻量 LLM 生成章节摘要卡片。失败不阻塞。"""
    import json as _json

    try:
        system = chapter_summary_system(world)
        user = build_chapter_summary_user_payload(
            world, chapter_id=chapter_id, manuscript_text=manuscript_text
        )
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.4,
            max_tokens=2048,
        )
        # 尝试解析 JSON
        data = _json.loads(reply.strip())
        if not isinstance(data, dict):
            return
        data["chapter_id"] = chapter_id
        ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
        if ch:
            data["title"] = ch.title
            # 同步到内存模型
            from worldforger.schemas import ChapterSummaryCard

            try:
                ch.summary_card = ChapterSummaryCard(**data)
            except Exception:
                pass
        write_summary_card(world.meta.id, chapter_id, data)
    except Exception:
        # 摘要生成失败不影响主流程
        pass


# ── 收尾：角色运行时状态提取 ─────────────────────────────────


async def _try_update_runtime_states(world: World, chapter_id: str, manuscript_text: str) -> None:
    """正文生成后，从正文提取各角色运行时状态变化。失败不阻塞。"""
    import json as _json

    try:
        system = character_state_extract_system()
        user = build_character_state_user_payload(world, manuscript_text=manuscript_text)
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.3,
            max_tokens=2048,
        )
        data = _json.loads(reply.strip())
        if not isinstance(data, dict):
            return
        for char_id, updates in data.items():
            if isinstance(updates, dict):
                update_character_runtime_state(world, str(char_id), updates, chapter_id)
    except Exception:
        # 状态提取失败不影响主流程
        pass


# ── RAG：检索与索引 ──────────────────────────────────────────


async def _try_retrieve_rag_chunks(world: World, chapter_id: str, beat_text: str) -> list[dict]:
    """从向量索引中检索与当前章相关的历史片段。失败返回空列表。"""
    try:
        from worldforger.chapter_indexer import ChapterIndexer

        indexer = ChapterIndexer(world.meta.id)
        # 提取出场人物 id
        char_ids = _extract_character_ids_from_beat(world, beat_text)
        # 提取待推进伏笔 id
        fs_ids = _extract_foreshadowing_ids(world, chapter_id)
        return indexer.retrieve_for_chapter(
            chapter_id,
            beat_text=beat_text,
            character_ids=char_ids,
            foreshadowing_ids=fs_ids,
            top_k=5,
        )
    except Exception:
        return []


async def _try_index_chapter(world: World, chapter_id: str, manuscript_text: str) -> None:
    """将新生成的章节索引到向量库。失败不阻塞。"""
    try:
        from worldforger.chapter_indexer import ChapterIndexer

        ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
        indexer = ChapterIndexer(world.meta.id)
        # 先移除旧向量（如果重新生成）
        indexer.remove_chapter(chapter_id)
        indexer.index_chapter(chapter_id, manuscript_text, {
            "chapter_order": ch.order if ch else 0,
            "chapter_title": ch.title if ch else "",
        })
    except Exception:
        pass


def _extract_character_ids_from_beat(world: World, beat_text: str) -> list[str]:
    """从节拍文本中提取出出场人物 ID（与 world 中实际人物匹配）。"""
    ids: list[str] = []
    for ent in world.characters.entities:
        if not isinstance(ent, dict):
            continue
        cid = str(ent.get("id", ""))
        cname = str(ent.get("name", ""))
        if cid and cid in beat_text:
            ids.append(cid)
        elif cname and cname in beat_text:
            ids.append(cid)
    return ids


def _extract_foreshadowing_ids(world: World, chapter_id: str) -> list[str]:
    """提取与当前章相关的伏笔 ID（植于本章或计划在本章回收）。"""
    ids: list[str] = []
    for f in world.story.foreshadowing:
        if f.planted_chapter_id == chapter_id or f.payoff_chapter_id == chapter_id:
            ids.append(f.id)
    return ids
