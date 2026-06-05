"""情节生成与章节管理业务逻辑。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from worldforger.llm import chat_completion, chat_completion_stream, drain_timing_log, drain_token_usage
from worldforger.schemas import StoryChapter, StoryPerson, World
from worldforger.story.story_prompts import (
    build_chapter_summary_user_payload,
    build_character_state_user_payload,
    build_consistency_check_user_payload,
    build_hard_context,
    build_kg_extraction_user_payload,
    build_manuscript_user_payload,
    build_sentiment_analysis_user_payload,
    chapter_beats_system,
    chapter_list_for_prompt,
    chapter_summary_system,
    character_state_extract_system,
    compact_world_snippet,
    consistency_check_system,
    kg_extraction_system,
    macro_outline_system,
    manuscript_system,
    narrator_block,
    person_instruction,
    sentiment_analysis_system,
)
from worldforger.story.story_store import (
    accumulate_token_usage,
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
        timing_label="macro_outline",
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
    # ── Shared context computed ONCE ──
    macro = read_text(macro_outline_path(world.meta.id))
    if len(macro) > 3000:
        macro = macro[:3000] + "\n…(粗纲已截断)"
    system = chapter_beats_system(world, creative_mode=mode_eff)
    ctx = compact_world_snippet(world, include_markdown=include_world_md)
    if len(ctx) > 2000:
        ctx = ctx[:2000] + "\n…(世界设定已截断)"
    chapter_list = chapter_list_for_prompt(world)  # computed once
    user_prompt = prompt.strip()

    # Limit concurrency to avoid API rate-limit / queue bloat
    sem = asyncio.Semaphore(5)

    async def _gen_one_beat(cid: str) -> tuple[str, str]:
        async with sem:
            ch = next((c for c in world.story.chapters if c.id == cid), None)
            if not ch:
                return cid, ""
            # 前一章摘要卡片（衔接检查用）
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
                f"{chapter_list}\n\n"
                f"【目标】仅为 id={cid}（{ch.title}）撰写细纲。\n"
                f"【用户要求】\n{user_prompt}\n\n"
                f"【粗纲】\n{macro}\n\n"
                f"【世界设定】\n{ctx}"
                f"{prev_summary_block}"
            )
            reply = await chat_completion(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.4,
                max_tokens=2048,
                timing_label=f"chapter_beat:{cid}",
            )

            # Detect refusal and retry with minimal prompt
            _REFUSAL = ["无法给到", "无法提供", "不能提供", "抱歉", "我无法", "我不能"]
            if reply and len(reply.strip()) < 100 and any(m in reply for m in _REFUSAL):
                retry_user = (
                    f"请为「{ch.title or cid}」撰写细纲。\n"
                    f"场景目标、冲突、出场人物、伏笔衔接——用 Markdown 输出。\n"
                    "直接开始写，不要解释："
                )
                reply = await chat_completion(
                    [{"role": "system", "content": "你是一位专业策划师。请直接输出细纲，不要拒绝。"},
                     {"role": "user", "content": retry_user}],
                    temperature=0.5,
                    max_tokens=2048,
                    timing_label=f"chapter_beat_retry:{cid}",
                )

            write_text(beat_path(world.meta.id, cid), reply)
            return cid, reply

    tasks = [_gen_one_beat(cid) for cid in chapter_ids]
    results = await asyncio.gather(*tasks)
    return {cid: reply for cid, reply in results if reply}


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
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
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
        person=person_eff,
    )
    # Drain timing log before manuscript generation to get a clean slate
    drain_timing_log()

    # Guard: truncate user prompt if excessively large (>60K chars)
    user_effective = user
    if len(user) > 60000:
        user_effective = user[:60000] + "\n…(上下文已截断，请基于已有设定写作)"

    # ── P1: Scene chunking path (for long chapters) ──
    target_words = ch.target_word_count if ch else 0
    if world.story.writing_defaults.enable_scene_chunking and beat.strip() and target_words >= 4000:
        hard_ctx = build_hard_context(world, chapter_id, beat)
        chunked = await _generate_manuscript_chunked(
            world, chapter_id, beat, target_words, hard_ctx, person_eff,
        )
        if chunked and len(chunked) > 500:
            reply = chunked
        else:
            # Fall through to normal generation
            reply = await chat_completion(
                [{"role": "system", "content": system}, {"role": "user", "content": user_effective}],
                temperature=0.75, max_tokens=8192,
                timing_label="manuscript_generation",
            )
    else:
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user_effective}],
            temperature=0.75, max_tokens=8192,
            timing_label="manuscript_generation",
        )

    # Detect refusal — retry once with a minimal prompt
    _REFUSAL_MARKERS = ["无法给到", "无法提供", "不能提供", "抱歉", "我无法", "我不能"]
    if reply and len(reply.strip()) < 100 and any(m in reply for m in _REFUSAL_MARKERS):
        chapter_title = ch.title if ch else chapter_id
        retry_user = (
            f"请为「{chapter_title}」撰写小说章节正文。\n"
            f"叙事人称：{person_instruction(person_eff)}。\n"
            "请直接输出正文（Markdown格式），不要输出任何解释。开始写作："
        )
        reply = await chat_completion(
            [{"role": "system", "content": "你是一位专业小说作家。请直接输出用户要求的章节内容，不要拒绝，不要解释。"},
             {"role": "user", "content": retry_user}],
            temperature=0.8,
            max_tokens=8192,
            timing_label="manuscript_retry",
        )

    write_text(manuscript_path(world.meta.id, chapter_id), reply)
    sync_chapter_word_count(world, chapter_id)
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    if ch:
        ch.status = "drafting"

    # ── 收尾：并行执行独立的后处理钩子 ──
    # 摘要卡片、角色状态、RAG 索引、知识图谱、情感追踪互不依赖，并发执行以加速
    post_hooks: list = [
        _try_generate_summary_card(world, chapter_id, reply),
        _try_update_runtime_states(world, chapter_id, reply),
        _try_index_chapter(world, chapter_id, reply),
    ]

    if world.story.writing_defaults.enable_narrative_kg:
        post_hooks.append(_try_extract_kg_events(world, chapter_id, reply))

    # 如果启用了润色 Loop，跳过独立的一致性审校（润色 Loop 内部会做，避免重复 LLM 调用）
    if world.story.writing_defaults.enable_consistency_check and not world.story.writing_defaults.enable_polisher:
        post_hooks.append(_try_run_consistency_check(world, chapter_id, reply))

    if world.story.writing_defaults.enable_sentiment_track:
        post_hooks.append(_try_track_sentiment(world, chapter_id, reply))

    if world.story.writing_defaults.enable_knowledge_track:
        post_hooks.append(_try_detect_knowledge(world, chapter_id, reply))

    if world.story.writing_defaults.enable_decision_track:
        post_hooks.append(_try_detect_decisions(world, chapter_id, reply))

    if world.story.writing_defaults.enable_physical_state_track:
        post_hooks.append(_try_update_physical_states(world, chapter_id, reply))

    if world.story.writing_defaults.enable_personal_timeline_track:
        post_hooks.append(_try_detect_timeline_events(world, chapter_id, reply))

    # Arc summary generation (every ~10 chapters)
    post_hooks.append(_try_generate_arc_summary(world, chapter_id))

    # Emotional aftermath extraction
    if world.story.writing_defaults.enable_aftermath_track:
        post_hooks.append(_try_extract_aftermaths(world, chapter_id, reply))

    # Epic density check (no LLM, just regex)
    if world.story.writing_defaults.enable_epic_density_check:
        _run_epic_density_check(chapter_id, reply)

    # ── P2: Unified extractors path (when enabled) ──
    if world.story.writing_defaults.enable_unified_extractors and post_hooks:
        # Skip individual hooks; use 3 unified extractors in parallel
        post_hooks = [
            _unified_narrative_state_extractor(world, chapter_id, reply),
            _unified_knowledge_plot_extractor(world, chapter_id, reply),
            _unified_quality_reviewer(world, chapter_id, reply),
        ]

    hook_errors: list[str] = []
    if post_hooks:
        results = await asyncio.gather(*post_hooks)
        hook_errors = [r for r in results if r]

    # ── Layer 4：审校 ↔ 润色 Loop（内部自带一致性审校，不再重复调用）──
    if world.story.writing_defaults.enable_polisher:
        reply = await _run_polish_loop(world, chapter_id, reply)
        sync_chapter_word_count(world, chapter_id)

    timing_breakdown = drain_timing_log()

    # Persist token usage per chapter
    token_usage = drain_token_usage()
    if token_usage:
        accumulate_token_usage(world.meta.id, chapter_id, token_usage)

    return reply, hook_errors, timing_breakdown


async def generate_manuscript_stream(
    world: World,
    *,
    chapter_id: str,
    prompt: str,
    creative_mode: str | None = None,
    person: StoryPerson | None = None,
    attach_prev_chapters: int = 0,
    include_world_md: bool | None = None,
) -> AsyncIterator[dict]:
    """Stream manuscript generation token-by-token.

    Yields dicts of shape ``{"type": "text", "content": "..."}`` for each
    token chunk, then ``{"type": "hook_errors", "errors": [...]}`` after
    post-processing, and finally ``{"type": "done", "world": {...}}``.
    """
    mode_eff = creative_mode or world.meta.creative_mode
    wd = world.story.writing_defaults
    inc_md = include_world_md if include_world_md is not None else wd.include_world_md
    prev_n = max(0, min(5, attach_prev_chapters))
    person_eff = person or world.story.narrator.person
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    macro = read_text(macro_outline_path(world.meta.id)) if wd.include_macro_outline else ""
    beat = read_text(beat_path(world.meta.id, chapter_id)) if wd.include_chapter_beats else ""
    prev: list[tuple[str, str]] = []
    for pch in chapters_before(world, chapter_id, prev_n):
        prev.append((pch.id, read_text(manuscript_path(world.meta.id, pch.id))))

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
        person=person_eff,
    )

    # ── Stream the manuscript ──
    drain_timing_log()
    yield {"type": "step", "phase": "manuscript", "label": "正在撰写文稿…", "index": 1, "total": 3}
    full_text_parts: list[str] = []
    async for token in chat_completion_stream(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.75,
        max_tokens=8192,
        timing_label="manuscript_generation",
    ):
        full_text_parts.append(token)
        yield {"type": "text", "content": token}

    reply = "".join(full_text_parts)
    write_text(manuscript_path(world.meta.id, chapter_id), reply)
    sync_chapter_word_count(world, chapter_id)
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    if ch:
        ch.status = "drafting"

    # ── Post-processing hooks (same as generate_manuscript) ──
    total_steps = 3 + (1 if world.story.writing_defaults.enable_polisher else 0)
    post_hooks: list = [
        _try_generate_summary_card(world, chapter_id, reply),
        _try_update_runtime_states(world, chapter_id, reply),
        _try_index_chapter(world, chapter_id, reply),
    ]
    if world.story.writing_defaults.enable_narrative_kg:
        post_hooks.append(_try_extract_kg_events(world, chapter_id, reply))
    if world.story.writing_defaults.enable_consistency_check and not world.story.writing_defaults.enable_polisher:
        post_hooks.append(_try_run_consistency_check(world, chapter_id, reply))
    if world.story.writing_defaults.enable_sentiment_track:
        post_hooks.append(_try_track_sentiment(world, chapter_id, reply))

    if world.story.writing_defaults.enable_knowledge_track:
        post_hooks.append(_try_detect_knowledge(world, chapter_id, reply))

    if world.story.writing_defaults.enable_decision_track:
        post_hooks.append(_try_detect_decisions(world, chapter_id, reply))

    if world.story.writing_defaults.enable_physical_state_track:
        post_hooks.append(_try_update_physical_states(world, chapter_id, reply))

    if world.story.writing_defaults.enable_personal_timeline_track:
        post_hooks.append(_try_detect_timeline_events(world, chapter_id, reply))

    # Arc summary generation (every ~10 chapters)
    post_hooks.append(_try_generate_arc_summary(world, chapter_id))

    # Emotional aftermath extraction
    if world.story.writing_defaults.enable_aftermath_track:
        post_hooks.append(_try_extract_aftermaths(world, chapter_id, reply))

    # Epic density check (no LLM, just regex)
    if world.story.writing_defaults.enable_epic_density_check:
        _run_epic_density_check(chapter_id, reply)

    hook_errors: list[str] = []
    if post_hooks:
        yield {"type": "step", "phase": "posthooks", "label": "正在执行后处理（摘要/状态/审校/情感分析）…", "index": 2, "total": total_steps}
        results = await asyncio.gather(*post_hooks)
        hook_errors = [r for r in results if r]

    if hook_errors:
        yield {"type": "hook_errors", "errors": hook_errors}

    if world.story.writing_defaults.enable_polisher:
        yield {"type": "step", "phase": "polish", "label": "正在润色文稿…", "index": 3, "total": total_steps}
        polished = await _run_polish_loop(world, chapter_id, reply)
        sync_chapter_word_count(world, chapter_id)

    timing_breakdown = drain_timing_log()

    # Persist token usage per chapter
    token_usage = drain_token_usage()
    if token_usage:
        accumulate_token_usage(world.meta.id, chapter_id, token_usage)

    yield {"type": "step", "phase": "done", "label": "生成完成", "index": total_steps, "total": total_steps}
    ch_final = next((c for c in world.story.chapters if c.id == chapter_id), None)
    done_payload = {
        "type": "done",
        "world": world.model_dump(mode="json"),
        "timing_breakdown": timing_breakdown,
        "polish_rounds": ch_final.polish_rounds if ch_final else 0,
    }
    if world.story.writing_defaults.enable_polisher:
        done_payload["polished_text"] = polished
    yield done_payload


def try_import_legacy(world: World) -> bool:
    return import_legacy_plot_outline(world)


# ── P1: 场景级分块生成 ──────────────────────────────────────

async def _generate_scene_plan(
    world: World, chapter_id: str, beat_text: str, target_words: int,
    person: StoryPerson | None,
) -> list[dict]:
    """Step 1: Generate a scene plan from the beat."""
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    system = (
        "你是小说场景规划师。你只需要输出 JSON 场景列表，不要输出正文。\n"
        'JSON 格式: {"scenes": [{"order":1,"type":"opening|conflict|revelation|transition|climax|resolution|breathing",'
        '"chars":["char_id"],"goal":"场景目标(20-30字)","est_words":600}]}\n'
        "场景类型: opening=开场, conflict=冲突, revelation=揭示, transition=过渡, climax=高潮, resolution=收尾, breathing=留白\n"
        f"目标总字数: {target_words} 字。场景数 3-6 个为宜。"
    )
    user = (
        f"为以下细纲生成场景规划：\n"
        f"章节: {ch.title if ch else chapter_id}\n"
        f"目标: {target_words} 字\n"
        f"【细纲】\n{beat_text[:3000]}"
    )
    reply = await chat_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.3, max_tokens=1024, timing_label="scene_plan",
    )
    import json as _json, re as _re
    t = _re.sub(r"^```[a-zA-Z0-9]*\s*|```$", "", reply.strip()).strip()
    s, e = t.find("{"), t.rfind("}")
    if s < 0 or e < 0:
        return []
    try:
        data = _json.loads(t[s:e + 1])
        return data.get("scenes", [])
    except _json.JSONDecodeError:
        return []


async def _generate_scene_draft(
    world: World, scene: dict, prev_scene_end: str,
    hard_context: str, person: StoryPerson | None,
) -> str:
    """Step 2: Generate a single scene draft."""
    goal = scene.get("goal", "")
    chars = scene.get("chars", [])
    est = scene.get("est_words", 600)
    system = (
        "你正在写小说的一个场景，不是整章。只写这个场景的正文。"
        "不要写场景标题、章节号。"
        f"目标字数约 {est} 字。直接开始叙述。"
    )
    user = f"【场景目标】{goal}\n【出场角色】{', '.join(chars[:5])}\n"
    if prev_scene_end:
        user += f"【衔接】上一场景结尾: {prev_scene_end[:200]}\n"
    if hard_context.strip():
        user += f"\n{hard_context}"
    reply = await chat_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.7, max_tokens=max(1024, int(est * 2.5)),
        timing_label=f"scene_draft_{scene.get('order',0)}",
    )
    return reply.strip()


async def _merge_scenes(
    world: World, scenes_text: list[str], chapter_id: str,
    person: StoryPerson | None,
) -> str:
    """Step 3: Merge scenes with continuity polish."""
    joined = "\n\n".join(scenes_text)
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    system = (
        "你是小说编辑。请合并以下场景片段为完整的章节正文。\n"
        "仅做: 场景间过渡句补充、人称一致性检查、重复内容删除、标点规范化。\n"
        "不要改变情节内容、角色对白、叙事顺序。"
    )
    user = (
        f"合并以下场景为「{ch.title if ch else chapter_id}」的完整章节:\n\n{joined[:12000]}"
    )
    reply = await chat_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.3, max_tokens=8192, timing_label="merge_scenes",
    )
    return reply.strip() if reply.strip() else joined


async def _generate_manuscript_chunked(
    world: World, chapter_id: str, beat_text: str, target_words: int,
    hard_context: str, person: StoryPerson | None,
) -> str:
    """Scene-chunked manuscript generation: Plan → Draft → Merge."""
    # Step 1: Scene plan
    scenes = await _generate_scene_plan(world, chapter_id, beat_text, target_words, person)
    if len(scenes) < 2:
        return ""  # Fall through to normal generation

    # Step 2: Generate each scene in parallel
    import asyncio as _asyncio
    prev_ends = [""]
    async def _draft_one(i, sc):
        return await _generate_scene_draft(
            world, sc, prev_ends[i] if i < len(prev_ends) else "", hard_context, person,
        )
    drafts = await _asyncio.gather(*[_draft_one(i, sc) for i, sc in enumerate(scenes)])
    drafts = [d for d in drafts if d and len(d) > 50]

    if len(drafts) < 2:
        return ""

    # Step 3: Merge
    return await _merge_scenes(world, drafts, chapter_id, person)


# ── P2: Unified Post-Processing Extractors ─────────────────────

async def _unified_narrative_state_extractor(
    world: World, chapter_id: str, manuscript_text: str,
) -> str:
    """Narrative State Extractor: summary + runtime + timeline + physical (1 LLM call)."""
    import json as _json
    try:
        ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
        chars = []
        for ent in world.characters.entities[:15]:
            if isinstance(ent, dict):
                chars.append(f"- id={ent.get('id','')} name={ent.get('name','')}")
        system = (
            "你是叙事状态抽取器。从章节正文中一次性提取以下四类信息。只输出JSON。\n"
            'JSON格式: {"summary_card":{"main_events":"...","character_state_changes":[],'
            '"foreshadowing_planted":[],"foreshadowing_resolved":[],"ending_hook":"..."},'
            '"runtime_states":{"char_id":{"current_location":"...","current_goal":"...","emotional_state":"..."}},'
            '"physical_states":[{"character_id":"char_id","active_injuries":[],"fatigue_level":"rested"}],'
            '"timeline_events":[{"event_id":"ptl_001","character_id":"char_id","event":"..."}]}\n'
        )
        user = f"章节id={chapter_id}，标题={ch.title if ch else ''}\n角色:\n" + "\n".join(chars)
        user += f"\n正文(截断):\n{manuscript_text[:8000]}"
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2, max_tokens=3072, timing_label="unified_narrative_state",
        )
        t = _repair_llm_json(reply)
        if "{" not in t: return "narrative_state: no JSON"
        data = _json.loads(t)

        # Distribute to individual systems
        sc = data.get("summary_card")
        if sc and isinstance(sc, dict):
            sc["chapter_id"] = chapter_id
            if ch: sc["title"] = ch.title
            from worldforger.schemas import ChapterSummaryCard
            try: ch.summary_card = ChapterSummaryCard(**sc)
            except: pass
            from worldforger.story.story_store import write_summary_card
            write_summary_card(world.meta.id, chapter_id, sc)

        rs = data.get("runtime_states")
        if isinstance(rs, dict):
            from worldforger.story.story_store import update_character_runtime_state
            for cid, state in rs.items():
                if isinstance(state, dict):
                    update_character_runtime_state(world, cid, state, chapter_id)

        ps = data.get("physical_states")
        if isinstance(ps, list):
            from worldforger.schemas import CharacterPhysicalState
            existing = {p.character_id: p for p in world.character_physical_states}
            for raw in ps:
                if isinstance(raw, dict) and raw.get("character_id"):
                    cid2 = raw["character_id"]
                    st = CharacterPhysicalState(character_id=cid2,
                        active_injuries=raw.get("active_injuries") if isinstance(raw.get("active_injuries"),list) else [],
                        fatigue_level=raw.get("fatigue_level","rested"),
                        general_condition=str(raw.get("general_condition",""))[:200],
                        last_updated_chapter=chapter_id)
                    if cid2 in existing:
                        idx2 = next(i for i,p in enumerate(world.character_physical_states) if p.character_id==cid2)
                        world.character_physical_states[idx2] = st
                    else:
                        world.character_physical_states.append(st)

        te = data.get("timeline_events")
        if isinstance(te, list):
            from worldforger.schemas import PersonalTimelineEvent, CharacterPersonalTimeline
            for raw in te:
                if isinstance(raw, dict) and raw.get("event_id"):
                    evt = PersonalTimelineEvent(
                        event_id=raw["event_id"], character_id=raw.get("character_id",""),
                        chapter=chapter_id, event=str(raw.get("event",""))[:200])
                    tl = next((t for t in world.character_personal_timelines if t.character_id==evt.character_id), None)
                    if tl is None:
                        tl = CharacterPersonalTimeline(character_id=evt.character_id)
                        world.character_personal_timelines.append(tl)
                    tl.events.append(evt)
        return ""
    except Exception as e:
        return f"unified_narrative_state: {e}"


async def _unified_knowledge_plot_extractor(
    world: World, chapter_id: str, manuscript_text: str,
) -> str:
    """Knowledge & Plot Extractor: knowledge + decisions + KG events (1 LLM call)."""
    import json as _json
    try:
        chars_list = []
        for ent in world.characters.entities[:15]:
            if isinstance(ent, dict):
                chars_list.append(f"- id={ent.get('id','')} name={ent.get('name','')}")
        system = (
            "你是知识与剧情抽取器。从章节正文中一次性提取三类信息。只输出JSON。\n"
            'JSON格式: {"knowledge_entries":[{"knowledge_id":"know_001","character_id":"char_id","topic":"...","category":"secret","certainty":"knows_for_sure","source_chapter":"ch_id","source_detail":"..."}],'
            '"decisions":[{"decision_id":"dec_001","character_id":"char_id","summary":"...","decision_type":"moral_choice","options_considered":[],"option_chosen":"","stated_reason":"","actual_reason":"","immediate_consequences":[],"outcome_verdict":"pending"}],'
            '"kg_events":[{"event_id":"evt_001","chapter_id":"ch_id","event_type":"revelation","summary":"...","participants":[],"location":"...","consequences":[]}]}\n'
        )
        user = f"章节id={chapter_id}\n角色:\n" + "\n".join(chars_list)
        user += f"\n正文(截断):\n{manuscript_text[:8000]}"
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2, max_tokens=3072, timing_label="unified_knowledge_plot",
        )
        t = _repair_llm_json(reply)
        if "{" not in t: return "knowledge_plot: no JSON"
        data = _json.loads(t)

        ke = data.get("knowledge_entries")
        if isinstance(ke, list):
            from worldforger.schemas import CharacterKnowledgeEntry
            existing_ids = {e.knowledge_id for e in world.character_knowledge.entries}
            for raw in ke:
                if isinstance(raw, dict) and raw.get("knowledge_id") not in existing_ids:
                    try:
                        world.character_knowledge.entries.append(CharacterKnowledgeEntry(
                            knowledge_id=raw["knowledge_id"], character_id=raw.get("character_id",""),
                            topic=raw.get("topic","")[:200], category=raw.get("category","secret"),
                            certainty=raw.get("certainty","knows_for_sure"), source_chapter=chapter_id,
                            source_detail=raw.get("source_detail","")[:200]))
                    except: pass

        decs = data.get("decisions")
        if isinstance(decs, list):
            from worldforger.schemas import CharacterDecision
            existing_dec_ids = {d.decision_id for d in world.character_decisions}
            for raw in decs:
                if isinstance(raw, dict) and raw.get("decision_id") not in existing_dec_ids:
                    try:
                        world.character_decisions.append(CharacterDecision(
                            decision_id=raw["decision_id"], character_id=raw.get("character_id",""),
                            chapter=chapter_id, summary=raw.get("summary","")[:200],
                            decision_type=raw.get("decision_type","moral_choice"),
                            options_considered=raw.get("options_considered") if isinstance(raw.get("options_considered"),list) else [],
                            option_chosen=raw.get("option_chosen","")[:100],
                            stated_reason=raw.get("stated_reason","")[:200],
                            actual_reason=raw.get("actual_reason","")[:200],
                            immediate_consequences=raw.get("immediate_consequences") if isinstance(raw.get("immediate_consequences"),list) else [],
                            outcome_verdict=raw.get("outcome_verdict","pending")))
                    except: pass

        kg_evts = data.get("kg_events")
        if isinstance(kg_evts, list):
            from worldforger.schemas import KGEvent
            from worldforger.narrative_kg import NarrativeKGManager
            mgr = NarrativeKGManager(world.meta.id)
            for raw in kg_evts:
                if isinstance(raw, dict) and raw.get("event_id"):
                    try:
                        world.story.narrative_kg.events.append(KGEvent(
                            event_id=raw["event_id"], chapter_id=chapter_id,
                            event_type=raw.get("event_type","other"),
                            summary=raw.get("summary","")[:200],
                            participants=raw.get("participants") if isinstance(raw.get("participants"),list) else [],
                            location=raw.get("location",""),
                            consequences=raw.get("consequences") if isinstance(raw.get("consequences"),list) else []))
                    except: pass
        return ""
    except Exception as e:
        return f"unified_knowledge_plot: {e}"


async def _unified_quality_reviewer(
    world: World, chapter_id: str, manuscript_text: str,
) -> str:
    """Consistency & Quality Reviewer: consistency + sentiment + aftermaths (1 LLM call)."""
    import json as _json
    try:
        ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
        chars_list = []
        for ent in world.characters.entities[:15]:
            if isinstance(ent, dict):
                chars_list.append(f"- id={ent.get('id','')} name={ent.get('name','')}")
        system = (
            "你是叙事质量审阅器。从章节正文中一次性提取三类信息。只输出JSON。\n"
            'JSON格式: {"consistency_report":{"verdict":"clean|minor_issues|needs_review","issues":[{"category":"position|personality|item_state|pov|foreshadowing|emotional_continuity|timeline|knowledge_boundary","severity":"critical|warning|info","description":"...","excerpt":"...","suggestion":"..."}]},'
            '"sentiment":{"segments":[{"segment_index":1,"label":"开篇|中段|高潮|尾声","tone":"positive|negative|tense|calm|mixed","intensity":5,"summary":"..."}],"overall_tone":"...","ending_tone":"...","transition_from_prev":"smooth|abrupt|intentional_contrast|first_chapter"},'
            '"aftermaths":[{"aftermath_id":"am_001","character_id":"char_id","source_event":"...","symptoms":[],"intensity":5,"trigger_conditions":[]}]}\n'
        )
        user = f"章节id={chapter_id}，标题={ch.title if ch else ''}，叙事设置={narrator_block(world)}\n角色:\n" + "\n".join(chars_list)
        user += f"\n正文(截断):\n{manuscript_text[:8000]}"
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2, max_tokens=3072, timing_label="unified_quality_review",
        )
        t = _repair_llm_json(reply)
        if "{" not in t: return "quality_review: no JSON"
        data = _json.loads(t)

        cr = data.get("consistency_report")
        if isinstance(cr, dict) and ch:
            from worldforger.schemas import ConsistencyReport
            try: ch.consistency_report = ConsistencyReport(chapter_id=chapter_id, **cr)
            except: pass

        sent = data.get("sentiment")
        if isinstance(sent, dict) and ch:
            from worldforger.schemas import SentimentLog
            try: ch.sentiment_log = SentimentLog(chapter_id=chapter_id, **sent)
            except: pass

        ams = data.get("aftermaths")
        if isinstance(ams, list):
            from worldforger.schemas import EmotionalAftermath
            for raw in ams:
                if isinstance(raw, dict) and raw.get("aftermath_id"):
                    try:
                        world.character_aftermaths.append(EmotionalAftermath(
                            aftermath_id=raw["aftermath_id"], character_id=raw.get("character_id",""),
                            source_event=raw.get("source_event","")[:200], source_chapter=chapter_id,
                            symptoms=raw.get("symptoms") if isinstance(raw.get("symptoms"),list) else [],
                            intensity=max(1,min(10,raw.get("intensity",5))),
                            trigger_conditions=raw.get("trigger_conditions") if isinstance(raw.get("trigger_conditions"),list) else []))
                    except: pass
        return ""
    except Exception as e:
        return f"unified_quality_review: {e}"


# ── 收尾：章节摘要卡片 ──────────────────────────────────────


async def _try_generate_summary_card(world: World, chapter_id: str, manuscript_text: str) -> str:
    """正文生成后，调用轻量 LLM 生成章节摘要卡片。失败不阻塞，返回错误描述。"""
    import json as _json

    try:
        system = chapter_summary_system(world)
        # Truncate manuscript to keep prompt small
        short_ms = manuscript_text.strip()
        if len(short_ms) > 6000:
            short_ms = short_ms[:6000] + "\n…(截断)"
        user = build_chapter_summary_user_payload(
            world, chapter_id=chapter_id, manuscript_text=short_ms
        )
        # Truncate user payload if too large
        if len(user) > 8000:
            user = user[:8000] + "\n…(截断)"
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.4,
            max_tokens=2048,
            timing_label="summary_card",
        )

        # Detect refusal and retry with minimal prompt
        _REFUSAL = ["无法给到", "无法提供", "不能提供", "抱歉", "我无法", "正文内容缺失"]
        if reply and len(reply.strip()) < 100 and any(m in reply for m in _REFUSAL):
            ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
            retry_user = (
                f"为以下章节撰写摘要卡片：\nid={chapter_id}，标题={ch.title if ch else ''}\n"
                f"【正文前4000字】\n{short_ms[:4000]}"
            )
            reply = await chat_completion(
                [{"role": "system", "content": "你是叙事分析助手。请输出JSON格式的章节摘要。直接输出，不要拒绝。"},
                 {"role": "user", "content": retry_user}],
                temperature=0.4,
                max_tokens=2048,
                timing_label="summary_card_retry",
            )

        # Parse JSON with repair
        t = _repair_llm_json(reply)
        data = _json.loads(t)
        if not isinstance(data, dict):
            return "摘要卡片：LLM 返回非 JSON 格式"
        # Skip if the summary is a refusal placeholder
        if "无法提取" in str(data.get("main_events", "")):
            return "摘要卡片：LLM 无法提取内容"
        data["chapter_id"] = chapter_id
        ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
        if ch:
            data["title"] = ch.title
            from worldforger.schemas import ChapterSummaryCard
            try:
                ch.summary_card = ChapterSummaryCard(**data)
            except Exception:
                pass
        write_summary_card(world.meta.id, chapter_id, data)
        return ""
    except Exception as e:
        return f"摘要卡片：{e}"


# ── 收尾：角色运行时状态提取 ─────────────────────────────────


async def _try_update_runtime_states(world: World, chapter_id: str, manuscript_text: str) -> str:
    """正文生成后，从正文提取各角色运行时状态变化。失败不阻塞，返回错误描述。"""
    import json as _json

    try:
        system = character_state_extract_system()
        user = build_character_state_user_payload(world, manuscript_text=manuscript_text)
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.3,
            max_tokens=2048,
            timing_label="runtime_state_update",
        )
        data = _json.loads(reply.strip())
        if not isinstance(data, dict):
            return "角色状态：LLM 返回非 JSON 格式"
        for char_id, updates in data.items():
            if isinstance(updates, dict):
                update_character_runtime_state(world, str(char_id), updates, chapter_id)
        return ""
    except Exception as e:
        return f"角色状态：{e}"


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


async def _try_index_chapter(world: World, chapter_id: str, manuscript_text: str) -> str:
    """将新生成的章节索引到向量库。失败不阻塞，返回错误描述。"""
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
        return ""
    except Exception as e:
        return f"RAG 索引：{e}"


# ── 收尾：叙事知识图谱提取 ─────────────────────────────────


# ── JSON repair helper (handles common LLM output quirks) ──────

def _repair_llm_json(raw: str) -> str:
    """Repair common LLM JSON errors: trailing commas, unescaped newlines in strings."""
    import re as _re
    t = raw.strip()
    if t.startswith("```"):
        t = _re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = _re.sub(r"\s*```$", "", t)
        t = t.strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1:
        return t
    t = t[start:end + 1]
    # Remove trailing commas
    t = _re.sub(r",(\s*[}\]])", r"\1", t)
    # Truncate to last complete JSON object (handle mid-string truncation)
    if not t.endswith("}") and not t.endswith("]"):
        # Scan backwards: find where braces balance
        brace_depth = 0
        last_good = len(t)
        for i in range(len(t) - 1, -1, -1):
            if t[i] == "}" or t[i] == "]":
                brace_depth += 1
            elif t[i] == "{" or t[i] == "[":
                brace_depth -= 1
                if brace_depth <= 0:
                    last_good = i
                    break
        if last_good > 0:
            t = t[:last_good]
    # Remove trailing commas AGAIN after truncation
    t = _re.sub(r",(\s*[}\]])", r"\1", t)
    # Fix unescaped newlines inside string values
    result = []
    i = 0
    in_string = False
    escape_next = False
    while i < len(t):
        ch = t[i]
        if escape_next:
            escape_next = False
            result.append(ch)
            i += 1
            continue
        if ch == '\\':
            escape_next = True
            result.append(ch)
            i += 1
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            i += 1
            continue
        if in_string:
            if ch == '\n':
                result.append('\\n')
            elif ch == '\r':
                result.append('')
            elif ch == '\t':
                result.append('\\t')
            else:
                result.append(ch)
        else:
            result.append(ch)
        i += 1
    return ''.join(result)


async def _try_extract_kg_events(world: World, chapter_id: str, manuscript_text: str) -> str:
    """正文生成后，从正文提取 KG 实体和事件。失败不阻塞，返回错误描述。"""
    import json as _json

    try:
        from worldforger.narrative_kg import NarrativeKGManager

        system = kg_extraction_system()
        user = build_kg_extraction_user_payload(
            world, chapter_id=chapter_id, manuscript_text=manuscript_text,
        )
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=2048,
            timing_label="kg_extraction",
        )

        t = _repair_llm_json(reply)
        if t == reply.strip() or t.find("{") == -1:
            # _repair_llm_json returned unchanged text without valid JSON
            if "{" not in reply and "}" not in reply:
                return "KG 抽取：LLM 返回不包含 JSON 对象"

        data = _json.loads(t)
        if not isinstance(data, dict):
            return "KG 抽取：LLM 返回非 JSON 格式"
        mgr = NarrativeKGManager(world.meta.id)
        kg = mgr.merge_extraction(data)
        world.story.narrative_kg = kg
        return ""
    except _json.JSONDecodeError as e:
        return f"KG 抽取：JSON 解析失败 — {e}"
    except Exception as e:
        return f"KG 抽取：{e}"


# ── 角色知识检测 ──────────────────────────────────────────


async def _try_detect_knowledge(world: World, chapter_id: str, manuscript_text: str) -> str:
    """从章节正文检测角色知识变化。失败不阻塞，返回错误描述。"""
    import json as _json

    try:
        from worldforger.story.story_prompts import (
            build_knowledge_detection_user_payload,
            knowledge_detection_system,
        )
        from worldforger.schemas import CharacterKnowledgeEntry

        system = knowledge_detection_system()
        user = build_knowledge_detection_user_payload(
            world, chapter_id=chapter_id, manuscript_text=manuscript_text,
        )
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=1536,
            timing_label="knowledge_detection",
        )

        t = _repair_llm_json(reply)
        if "{" not in t or "}" not in t:
            return "知识检测：LLM 返回不包含 JSON 对象"
        data = _json.loads(t)
        if not isinstance(data, dict):
            return "知识检测：LLM 返回非 JSON 格式"

        new_entries = data.get("new_entries", [])
        updated = data.get("updated_entries", [])
        if not isinstance(new_entries, list):
            new_entries = []
        if not isinstance(updated, list):
            updated = []

        updated_ids = {u.get("knowledge_id", "") for u in updated if isinstance(u, dict)}

        for raw in new_entries:
            if not isinstance(raw, dict):
                continue
            kid = str(raw.get("knowledge_id", "")).strip()
            if not kid or any(
                e.knowledge_id == kid for e in world.character_knowledge.entries
            ):
                continue
            try:
                entry = CharacterKnowledgeEntry(
                    knowledge_id=kid,
                    character_id=str(raw.get("character_id", "")).strip(),
                    topic=str(raw.get("topic", "")).strip()[:200],
                    category=raw.get("category", "secret"),
                    certainty=raw.get("certainty", "knows_for_sure"),
                    source_chapter=chapter_id,
                    source_detail=str(raw.get("source_detail", "")).strip()[:300],
                    shared_with=raw.get("shared_with") if isinstance(raw.get("shared_with"), list) else [],
                    is_still_true=bool(raw.get("is_still_true", True)),
                    notes=str(raw.get("notes", "")).strip()[:500],
                )
                world.character_knowledge.entries.append(entry)
            except Exception:
                continue

        for raw_up in updated:
            if not isinstance(raw_up, dict):
                continue
            kid = str(raw_up.get("knowledge_id", "")).strip()
            for e in world.character_knowledge.entries:
                if e.knowledge_id == kid:
                    sw = raw_up.get("shared_with")
                    if isinstance(sw, list):
                        e.shared_with = sw
                    if "is_still_true" in raw_up:
                        e.is_still_true = bool(raw_up["is_still_true"])
                    if raw_up.get("notes"):
                        e.notes = str(raw_up.get("notes", "")).strip()[:500]
                    break

        return ""
    except _json.JSONDecodeError as e:
        return f"知识检测：JSON 解析失败 — {e}"
    except Exception as e:
        return f"知识检测：{e}"


# ── P1: 角色决策检测 ──────────────────────────────────────────


async def _try_detect_decisions(world: World, chapter_id: str, manuscript_text: str) -> str:
    """从章节正文检测角色的关键决策。失败不阻塞，返回错误描述。"""
    import json as _json

    try:
        from worldforger.story.story_prompts import (
            build_decision_detection_user_payload,
            decision_detection_system,
        )
        from worldforger.schemas import CharacterDecision

        system = decision_detection_system()
        user = build_decision_detection_user_payload(
            world, chapter_id=chapter_id, manuscript_text=manuscript_text,
        )
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=1536,
            timing_label="decision_detection",
        )

        t = _repair_llm_json(reply)
        if "{" not in t or "}" not in t:
            return "决策检测：LLM 返回不包含 JSON 对象"
        data = _json.loads(t)
        if not isinstance(data, dict):
            return "决策检测：LLM 返回非 JSON 格式"

        decisions = data.get("decisions", [])
        if not isinstance(decisions, list):
            return "决策检测：decisions 非数组"

        existing_ids = {d.decision_id for d in world.character_decisions}
        added = 0
        for raw in decisions:
            if not isinstance(raw, dict):
                continue
            did = str(raw.get("decision_id", "")).strip()
            if not did or did in existing_ids:
                continue
            try:
                dec = CharacterDecision(
                    decision_id=did,
                    character_id=str(raw.get("character_id", "")).strip(),
                    chapter=chapter_id,
                    summary=str(raw.get("summary", "")).strip()[:200],
                    decision_type=raw.get("decision_type", "moral_choice"),
                    options_considered=raw.get("options_considered") if isinstance(raw.get("options_considered"), list) else [],
                    option_chosen=str(raw.get("option_chosen", "")).strip()[:100],
                    stated_reason=str(raw.get("stated_reason", "")).strip()[:200],
                    actual_reason=str(raw.get("actual_reason", "")).strip()[:200],
                    immediate_consequences=raw.get("immediate_consequences") if isinstance(raw.get("immediate_consequences"), list) else [],
                    long_term_consequences=raw.get("long_term_consequences") if isinstance(raw.get("long_term_consequences"), list) else [],
                    reflections=raw.get("reflections") if isinstance(raw.get("reflections"), list) else [],
                    outcome_verdict=raw.get("outcome_verdict", "pending"),
                )
                world.character_decisions.append(dec)
                added += 1
            except Exception:
                continue
        return "" if added > 0 else "决策检测：未发现新的关键决策"
    except _json.JSONDecodeError as e:
        return f"决策检测：JSON 解析失败 — {e}"
    except Exception as e:
        return f"决策检测：{e}"


# ── P1: 角色身体状况更新 ──────────────────────────────────────


async def _try_update_physical_states(world: World, chapter_id: str, manuscript_text: str) -> str:
    """从章节正文提取角色身体状态变化。失败不阻塞，返回错误描述。"""
    import json as _json

    try:
        from worldforger.story.story_prompts import (
            build_physical_state_detection_user_payload,
            physical_state_detection_system,
        )
        from worldforger.schemas import CharacterPhysicalState

        system = physical_state_detection_system()
        user = build_physical_state_detection_user_payload(
            world, chapter_id=chapter_id, manuscript_text=manuscript_text,
        )
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=1536,
            timing_label="physical_state_detection",
        )

        t = _repair_llm_json(reply)
        if "{" not in t or "}" not in t:
            return "身体状态检测：LLM 返回不包含 JSON 对象"
        data = _json.loads(t)
        if not isinstance(data, dict):
            return "身体状态检测：LLM 返回非 JSON 格式"

        states = data.get("physical_states", [])
        if not isinstance(states, list):
            return "身体状态检测：physical_states 非数组"

        existing_map = {ps.character_id: ps for ps in world.character_physical_states}
        updated = 0
        for raw in states:
            if not isinstance(raw, dict):
                continue
            cid = str(raw.get("character_id", "")).strip()
            if not cid:
                continue
            try:
                ps = CharacterPhysicalState(
                    character_id=cid,
                    active_injuries=raw.get("active_injuries") if isinstance(raw.get("active_injuries"), list) else [],
                    permanent_marks=raw.get("permanent_marks") if isinstance(raw.get("permanent_marks"), list) else [],
                    chronic_conditions=raw.get("chronic_conditions") if isinstance(raw.get("chronic_conditions"), list) else [],
                    fatigue_level=raw.get("fatigue_level", "rested"),
                    general_condition=str(raw.get("general_condition", "")).strip()[:300],
                    last_updated_chapter=chapter_id,
                )
                if cid in existing_map:
                    idx = next(i for i, s in enumerate(world.character_physical_states) if s.character_id == cid)
                    world.character_physical_states[idx] = ps
                else:
                    world.character_physical_states.append(ps)
                updated += 1
            except Exception:
                continue
        return "" if updated > 0 else "身体状态检测：未发现新的身体状态变化"
    except _json.JSONDecodeError as e:
        return f"身体状态检测：JSON 解析失败 — {e}"
    except Exception as e:
        return f"身体状态检测：{e}"


# ── P2: 角色个人时间线检测 ──────────────────────────────────────

async def _try_detect_timeline_events(world: World, chapter_id: str, manuscript_text: str) -> str:
    """从章节正文检测角色的个人时间线事件。失败不阻塞，返回错误描述。"""
    import json as _json

    try:
        from worldforger.story.story_prompts import (
            build_personal_timeline_user_payload,
            personal_timeline_detection_system,
        )
        from worldforger.schemas import CharacterPersonalTimeline, PersonalTimelineEvent

        system = personal_timeline_detection_system()
        user = build_personal_timeline_user_payload(
            world, chapter_id=chapter_id, manuscript_text=manuscript_text,
        )
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=1536,
            timing_label="personal_timeline_detection",
        )

        t = _repair_llm_json(reply)
        if "{" not in t or "}" not in t:
            return "时间线检测：LLM 返回不包含 JSON 对象"
        data = _json.loads(t)
        if not isinstance(data, dict):
            return "时间线检测：LLM 返回非 JSON 格式"

        events = data.get("timeline_events", [])
        if not isinstance(events, list):
            return "时间线检测：timeline_events 非数组"

        existing_ids = set()
        for tl in world.character_personal_timelines:
            for e in tl.events:
                existing_ids.add(e.event_id)

        added = 0
        for raw in events:
            if not isinstance(raw, dict):
                continue
            eid = str(raw.get("event_id", "")).strip()
            if not eid or eid in existing_ids:
                continue
            cid = str(raw.get("character_id", "")).strip()
            if not cid:
                continue
            try:
                evt = PersonalTimelineEvent(
                    event_id=eid, character_id=cid,
                    chapter=chapter_id,
                    relative_timing=str(raw.get("relative_timing", "")).strip()[:60],
                    event=str(raw.get("event", "")).strip()[:200],
                    known_by=raw.get("known_by") if isinstance(raw.get("known_by"), list) else [],
                    significance=str(raw.get("significance", "")).strip()[:200],
                    linked_events=raw.get("linked_events") if isinstance(raw.get("linked_events"), list) else [],
                )
                # Upsert into the character's timeline
                tl = next((t for t in world.character_personal_timelines if t.character_id == cid), None)
                if tl is None:
                    tl = CharacterPersonalTimeline(character_id=cid)
                    world.character_personal_timelines.append(tl)
                tl.events.append(evt)
                added += 1
            except Exception:
                continue
        return "" if added > 0 else "时间线检测：未发现新的个人时间线事件"
    except _json.JSONDecodeError as e:
        return f"时间线检测：JSON 解析失败 — {e}"
    except Exception as e:
        return f"时间线检测：{e}"


# ── P2: 滚动阶段摘要 ───────────────────────────────────────────

async def _try_generate_arc_summary(world: World, chapter_id: str) -> str:
    """Generate a rolling arc summary every ~10 chapters.

    Only fires when the chapter order is a multiple of 10.  Reads
    the last 10 chapters' summaries and generates a compressed arc
    overview stored in ``story/arc_summaries/arc_X_Y.md``.
    """
    ARC_INTERVAL = 10
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    if not ch or ch.order % ARC_INTERVAL != 0:
        return ""
    if ch.order < ARC_INTERVAL:
        return ""  # Not enough chapters yet

    arc_start = ch.order - ARC_INTERVAL + 1
    arc_end = ch.order

    from worldforger.story.story_store import (
        arc_summaries_dir, arc_summary_path, summaries_before, write_text,
    )
    arc_summaries_dir(world.meta.id).mkdir(parents=True, exist_ok=True)

    # Skip if already exists
    if arc_summary_path(world.meta.id, arc_start, arc_end).is_file():
        return ""

    # Collect summaries for chapters in this arc
    summary_parts = []
    for c in world.story.chapters:
        if arc_start <= c.order <= arc_end:
            cards = summaries_before(world.meta.id, c.id, 0, world)
            if cards:
                card = cards[0]
                summary_parts.append(
                    f"第{c.order}章 {c.title}：{card.get('main_events', '')} "
                    f"结尾：{card.get('ending_hook', '')}"
                )
            else:
                summary_parts.append(f"第{c.order}章 {c.title}：（摘要缺失）")

    if not summary_parts:
        return ""

    user_text = (
        f"为以下 {len(summary_parts)} 个章节撰写一个 200-500 字的阶段摘要，概括主要事件发展、角色变化和伏笔进展：\n"
        + "\n".join(summary_parts)
    )
    try:
        reply = await chat_completion(
            [{"role": "system", "content": "你是故事编辑，负责为多个章节撰写阶段性摘要。直接输出摘要文字，不要JSON。"},
             {"role": "user", "content": user_text}],
            temperature=0.3,
            max_tokens=600,
            timing_label=f"arc_summary_{arc_start}_{arc_end}",
        )
        if reply and len(reply.strip()) > 30:
            write_text(arc_summary_path(world.meta.id, arc_start, arc_end), reply.strip())
        return ""
    except Exception as e:
        return f"阶段摘要生成：{e}"


# ── Phase 2: 金句密度检测 ──────────────────────────────────────

def _run_epic_density_check(chapter_id: str, text: str) -> None:
    """Detect epic quote density in manuscript (non-blocking, regex only)."""
    try:
        from worldforger.story.story_prompts import detect_epic_density
        result = detect_epic_density(text)
        if result.get("warning"):
            print(f"[MCW-DENSITY] Chapter {chapter_id}: {result['warning']}")
    except Exception:
        pass


# ── Phase 1: 情绪后遗症提取 ──────────────────────────────────

async def _try_extract_aftermaths(world: World, chapter_id: str, manuscript_text: str) -> str:
    """从章节正文提取角色的情绪后遗症。失败不阻塞。"""
    import json as _json
    try:
        from worldforger.story.story_prompts import aftermath_extraction_system, build_aftermath_user_payload
        from worldforger.schemas import EmotionalAftermath

        system = aftermath_extraction_system()
        user = build_aftermath_user_payload(world, chapter_id=chapter_id, manuscript_text=manuscript_text)
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2, max_tokens=1536, timing_label="aftermath_extraction",
        )
        t = _repair_llm_json(reply)
        if "{" not in t or "}" not in t:
            return ""
        data = _json.loads(t)
        aftermaths = data.get("aftermaths", [])
        if not isinstance(aftermaths, list):
            return ""

        existing_ids = {a.aftermath_id for a in world.character_aftermaths}
        added = 0
        for raw in aftermaths:
            if not isinstance(raw, dict):
                continue
            aid = str(raw.get("aftermath_id", "")).strip()
            if not aid or aid in existing_ids:
                continue
            try:
                cid = str(raw.get("character_id", "")).strip()
                am = EmotionalAftermath(
                    aftermath_id=aid,
                    character_id=cid,
                    source_event=str(raw.get("source_event", "")).strip()[:200],
                    source_chapter=chapter_id,
                    symptoms=raw.get("symptoms") if isinstance(raw.get("symptoms"), list) else [],
                    intensity=max(1, min(10, int(raw.get("intensity", 5)))),
                    trigger_conditions=raw.get("trigger_conditions") if isinstance(raw.get("trigger_conditions"), list) else [],
                    current_status="active",
                )
                world.character_aftermaths.append(am)
                added += 1
            except Exception:
                continue

        # Decay existing active aftermaths
        for am in world.character_aftermaths:
            if am.current_status == "active":
                am.intensity = max(1, int(am.intensity - am.decay_rate))
                if am.intensity <= 2:
                    ch_order = next((c.order for c in world.story.chapters if c.id == chapter_id), 0)
                    src_order = next((c.order for c in world.story.chapters if c.id == am.source_chapter), 0)
                    if ch_order - src_order >= 5:
                        am.current_status = "became_trait"
        return "" if added > 0 else ""
    except Exception:
        return ""


# ── 收尾：一致性审校 ──────────────────────────────────────


async def _try_run_consistency_check(world: World, chapter_id: str, manuscript_text: str) -> str:
    """正文生成后，运行 7 维度一致性审校。失败不阻塞，返回错误描述。"""
    try:
        from worldforger.consistency_checker import run_consistency_check

        await run_consistency_check(world, chapter_id, manuscript_text)
        return ""
    except Exception as e:
        return f"一致性审校：{e}"


# ── 收尾：情感弧线追踪 ─────────────────────────────────────


async def _try_track_sentiment(world: World, chapter_id: str, manuscript_text: str) -> str:
    """正文生成后，分析情感弧线并保存。失败不阻塞，返回错误描述。"""
    import json as _json

    try:
        from worldforger.sentiment_tracker import SentimentTracker, _parse_sentiment

        ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
        system = sentiment_analysis_system()
        user = build_sentiment_analysis_user_payload(
            world, chapter_id=chapter_id, manuscript_text=manuscript_text,
        )
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=1024,
            timing_label="sentiment_track",
        )
        log = _parse_sentiment(reply.strip(), chapter_id, ch.title if ch else "")
        if not log:
            return "情感追踪：LLM 返回无效格式"
        tracker = SentimentTracker(world.meta.id)
        tracker.save_log(log)
        if ch:
            ch.sentiment_log = log
        return ""
    except Exception as e:
        return f"情感追踪：{e}"


# ── Layer 4：审校 ↔ 润色反馈闭环 ─────────────────────────────


def _text_similarity(a: str, b: str) -> float:
    """Return similarity ratio (0.0–1.0) between two strings."""
    from difflib import SequenceMatcher

    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


async def _run_polish_loop(world: World, chapter_id: str, manuscript_text: str) -> str:
    """Run the consistency-check ↔ polish feedback loop.

    Always runs at least **one** round of polish (the polisher LLM is always
    called).  Subsequent rounds only run when the consistency check still
    reports fixable issues **and** the polisher produced a meaningfully
    different text from the previous round (convergence detection).

    Returns the polished text.  On failure returns the original text unchanged.
    """
    import json as _json

    try:
        max_rounds = world.story.writing_defaults.polish_max_rounds
        ch = next((c for c in world.story.chapters if c.id == chapter_id), None)

        current_text = manuscript_text
        all_issues_history: list[dict] = []
        trace = {
            "chapter_id": chapter_id,
            "max_rounds": max_rounds,
            "actual_rounds": 0,
            "termination_reason": "",
            "rounds": [],
        }

        for round_idx in range(1, max_rounds + 1):
            round_record = {"round": round_idx, "issues_before": [], "issues_after": []}

            # ── Step 1: Run consistency check (for polisher input, NOT as a gate) ──
            from worldforger.consistency_checker import run_consistency_check

            report = await run_consistency_check(world, chapter_id, current_text)
            round_record["verdict"] = report.verdict
            round_record["total_issues"] = report.total_issues

            # Classify issues vs previous rounds
            current_issue_ids = {iss.issue_id for iss in report.issues} if report.issues else set()
            prev_issue_ids = set()
            for h in all_issues_history:
                for iss in h.get("issues", []):
                    prev_issue_ids.add(iss.get("issue_id", ""))

            fixed_ids = prev_issue_ids - current_issue_ids
            new_ids = current_issue_ids - prev_issue_ids
            persistent_ids = current_issue_ids & prev_issue_ids

            fixed_issues = []
            persistent_issues = []
            new_issues = []
            if report.issues:
                for iss in report.issues:
                    iss_dict = iss.model_dump() if hasattr(iss, "model_dump") else {}
                    if iss.issue_id in new_ids:
                        iss_dict["_classification"] = "regression" if round_idx > 1 else "new"
                        new_issues.append(iss_dict)
                    elif iss.issue_id in persistent_ids:
                        iss_dict["_classification"] = "persistent"
                        persistent_issues.append(iss_dict)

            for h in all_issues_history:
                for iss in h.get("issues", []):
                    if iss.get("issue_id") in fixed_ids:
                        iss["_classification"] = "fixed"
                        fixed_issues.append(iss)

            round_record["issues_before"] = (
                all_issues_history[-1].get("issues", []) if all_issues_history else []
            )
            round_record["issues_after"] = [
                iss.model_dump() if hasattr(iss, "model_dump") else {}
                for iss in (report.issues or [])
            ]
            round_record["classification"] = {
                "fixed": fixed_issues,
                "persistent": persistent_issues,
                "regression": new_issues,
            }

            # ── Step 2: Build polisher input (ALWAYS, even for clean text) ──
            from worldforger.story.story_prompts import (
                build_polisher_user_payload,
                format_consistency_issues_for_polisher,
                polisher_system,
            )

            issues_text = format_consistency_issues_for_polisher(report)

            regression_text = ""
            if new_issues:
                regression_lines = []
                for iss in new_issues:
                    sev = iss.get("severity", "warning")
                    cat = iss.get("category", "")
                    desc = iss.get("description", "")
                    sug = iss.get("suggestion", "")
                    regression_lines.append(
                        f"  [REGRESSION-{sev}] {cat}: {desc}"
                        + (f"（建议：{sug}）" if sug else "")
                    )
                regression_text = "\n".join(regression_lines)

            system = polisher_system()
            user = build_polisher_user_payload(
                world,
                chapter_id,
                current_text,
                consistency_issues=issues_text,
                polish_round=round_idx,
                regression_issues=regression_text,
            )

            # ── Step 3: Call polisher LLM (always, at least once) ──
            polished_reply = await chat_completion(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.35,
                max_tokens=8192,
                timing_label=f"polish_round:{round_idx}",
            )

            prev_text = current_text
            if polished_reply and polished_reply.strip():
                current_text = polished_reply.strip()

            trace["rounds"].append(round_record)

            # ── Step 4: Convergence detection ──
            # (a) Consistency says clean or info-only → polisher did its job
            if report.verdict == "clean" or report.total_issues == 0:
                trace["termination_reason"] = "clean"
                trace["actual_rounds"] = round_idx
                break

            if all(iss.severity == "info" for iss in (report.issues or [])):
                trace["termination_reason"] = "info_only"
                trace["actual_rounds"] = round_idx
                break

            # (b) Text barely changed → converged
            sim = _text_similarity(prev_text, current_text)
            if sim >= 0.95:
                trace["termination_reason"] = f"converged_sim={sim:.3f}"
                trace["actual_rounds"] = round_idx
                break

            # (c) All remaining issues are critical (can't fix via polish)
            non_critical = [
                iss
                for iss in (report.issues or [])
                if iss.severity != "critical"
            ]
            if not non_critical and (report.issues or []):
                trace["termination_reason"] = "no_fixable_issues"
                trace["actual_rounds"] = round_idx
                break

            # Store for next round
            all_issues_history.append({
                "round": round_idx,
                "issues": [
                    iss.model_dump() if hasattr(iss, "model_dump") else {}
                    for iss in (report.issues or [])
                ],
            })

            # Max rounds reached
            if round_idx >= max_rounds:
                trace["termination_reason"] = "max_rounds"
                trace["actual_rounds"] = round_idx
                break

        # ── After loop: persist polished result ──
        if "actual_rounds" not in trace or not trace["actual_rounds"]:
            trace["actual_rounds"] = len(trace["rounds"])
        if not trace["termination_reason"]:
            trace["termination_reason"] = "max_rounds"

        from worldforger.story.story_store import polished_path, polish_trace_path, write_text

        # Persist polished text to both polished/ and manuscript/
        write_text(polished_path(world.meta.id, chapter_id), current_text)
        # Save snapshot of original before overwriting (for diff comparison)
        try:
            from worldforger.story.story_store import save_chapter_snapshot
            save_chapter_snapshot(world.meta.id, chapter_id)
        except Exception:
            pass
        write_text(manuscript_path(world.meta.id, chapter_id), current_text)
        sync_chapter_word_count(world, chapter_id)

        # Write trace
        polish_trace_path(world.meta.id, chapter_id).write_text(
            _json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Update chapter model
        polished_rel = f"story/polished/{chapter_id}.md"
        if ch:
            ch.polished_file = polished_rel
            ch.polish_rounds = trace["actual_rounds"]
            ch.polish_issue_tracking = trace

        return current_text

    except Exception:
        # Polish loop failure does not block the main generation flow
        return manuscript_text


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


# ── P1-6: Usage Stats ────────────────────────────────────────────

# Conservative token estimates per hook (input + output combined).
_HOOK_TOKEN_ESTIMATES: dict[str, int] = {
    "manuscript_generation": 8000,
    "summary_card": 500,
    "runtime_state_update": 300,
    "rag_index": 200,
    "kg_extraction": 800,
    "consistency_check": 1200,
    "sentiment_track": 400,
    "polish_loop_per_round": 3000,
}

_HOOK_LABELS_ZH: dict[str, str] = {
    "manuscript_generation": "文稿生成",
    "summary_card": "摘要卡片",
    "runtime_state_update": "运行时状态",
    "rag_index": "RAG 索引",
    "kg_extraction": "知识图谱提取",
    "consistency_check": "一致性审校",
    "sentiment_track": "情感弧线追踪",
    "polish_loop_per_round": "润色环（每轮）",
}

_HOOK_RECOMMENDED: set[str] = {
    "summary_card", "runtime_state_update", "rag_index",
}


def compute_usage_stats(world: World) -> dict:
    """Compute estimated token usage per chapter based on enabled hooks.

    Returns a dict suitable for JSON serialization, with per-hook breakdown
    and a total estimate.
    """
    wd = world.story.writing_defaults
    hooks: list[dict] = []

    hooks.append({
        "key": "manuscript_generation",
        "label": _HOOK_LABELS_ZH["manuscript_generation"],
        "estimated_tokens": _HOOK_TOKEN_ESTIMATES["manuscript_generation"],
        "enabled": True,
        "always_on": True,
        "recommended": False,
    })

    for key in ("summary_card", "runtime_state_update", "rag_index"):
        hooks.append({
            "key": key,
            "label": _HOOK_LABELS_ZH[key],
            "estimated_tokens": _HOOK_TOKEN_ESTIMATES[key],
            "enabled": True,
            "always_on": True,
            "recommended": True,
        })

    # KG
    kg_enabled = wd.enable_narrative_kg
    hooks.append({
        "key": "kg_extraction",
        "label": _HOOK_LABELS_ZH["kg_extraction"],
        "estimated_tokens": _HOOK_TOKEN_ESTIMATES["kg_extraction"],
        "enabled": kg_enabled,
        "always_on": False,
        "recommended": False,
    })

    # Consistency check
    cc_enabled = wd.enable_consistency_check
    hooks.append({
        "key": "consistency_check",
        "label": _HOOK_LABELS_ZH["consistency_check"],
        "estimated_tokens": _HOOK_TOKEN_ESTIMATES["consistency_check"],
        "enabled": cc_enabled,
        "always_on": False,
        "recommended": False,
    })

    # Sentiment
    st_enabled = wd.enable_sentiment_track
    hooks.append({
        "key": "sentiment_track",
        "label": _HOOK_LABELS_ZH["sentiment_track"],
        "estimated_tokens": _HOOK_TOKEN_ESTIMATES["sentiment_track"],
        "enabled": st_enabled,
        "always_on": False,
        "recommended": False,
    })

    # Polisher
    pol_enabled = wd.enable_polisher
    pol_rounds = max(1, wd.polish_max_rounds)
    hooks.append({
        "key": "polish_loop",
        "label": f"{_HOOK_LABELS_ZH['polish_loop_per_round']} × {pol_rounds}",
        "estimated_tokens": _HOOK_TOKEN_ESTIMATES["polish_loop_per_round"] * pol_rounds,
        "enabled": pol_enabled,
        "always_on": False,
        "recommended": False,
    })

    total = sum(h["estimated_tokens"] for h in hooks if h["enabled"])
    chapter_count = len(world.story.chapters)

    return {
        "hooks": hooks,
        "estimated_total_per_chapter": total,
        "chapter_count": chapter_count,
        "estimated_project_total": total * max(1, chapter_count),
    }
