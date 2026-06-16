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
    # 85 章粗纲约需 20000-30000 tokens — 使用 API 最大允许值
    _MACRO_MAX_TOKENS = 32768
    reply = await chat_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.65,
        max_tokens=_MACRO_MAX_TOKENS,
        timing_label="macro_outline",
    )

    # ── Truncation detection & auto-continuation for macro outlines ──
    # 使用与正文相同的截断检测 + 续写机制，但针对大纲格式优化
    from worldforger.llm import _CALL_LOG as _TIMING_LOG
    for cont_round in range(5):  # 大纲可能需要更多续写轮次
        was_truncated = False
        if _TIMING_LOG:
            was_truncated = _TIMING_LOG[-1].get("finish_reason", "") == "length"
        if not was_truncated:
            was_truncated = _text_looks_truncated(reply)
        # 额外检查：大纲特有的截断信号——末尾行不完整
        if not was_truncated:
            last_line = reply.strip().split("\n")[-1]
            # 大纲行通常以 | 或数字结尾，如果最后一行看起来像被截断
            if len(last_line) < 30 and not last_line.endswith(("|", "。", "—", "…")):
                if any(kw in last_line.lower() for kw in ("ch", "章", "第", "|", "卷")):
                    was_truncated = True
        if not was_truncated:
            break

        # 续写 — 使用与正文续写相同的策略，但 max_tokens 更大
        continue_max = max(_MACRO_MAX_TOKENS // 2, 16384)
        last_section = reply.strip()[-600:]
        continue_user = (
            f"你正在撰写一份完整的小说粗纲。上面的粗纲在以下位置截断了：\n\n"
            f"…{last_section}\n\n"
            f"请从截断处继续完成剩余的所有章节大纲，保持相同的格式（表格或列表）。"
            f"直接输出后续章节，不要重复已有内容。"
        )
        continuation = await chat_completion(
            [{"role": "system", "content": "你是一位专业策划师。请继续完成粗纲大纲的后续章节，使用与上文一致的格式，直接输出后续内容。"},
             {"role": "user", "content": continue_user}],
            temperature=0.65,
            max_tokens=continue_max,
            timing_label=f"macro_outline_continue_{cont_round+1}",
        )
        if continuation and len(continuation.strip()) > 50:
            reply = reply.rstrip() + "\n\n" + continuation.strip()
        else:
            break

    # Final wrap-up — 如果多轮续写后仍不完整，做简洁收束
    if _text_looks_truncated(reply) and len(reply.strip()) > 500:
        # 检测当前写到第几章了
        import re as _re2
        ch_nums = _re2.findall(r'\bch[_]?(\d+)\b', reply[-2000:].lower())
        last_ch = max(int(n) for n in ch_nums) if ch_nums else 0
        if last_ch > 0:
            wrap_user = (
                f"粗纲已写到第 {last_ch} 章，但尚未完成全部章节。"
                f"请为第 {last_ch+1} 章开始到最后的章节写出简洁大纲条目（每章 1-2 行即可）。\n"
                f"当前最后一章的上下文：\n…{reply.strip()[-400:]}"
            )
        else:
            wrap_user = (
                f"以下粗纲尚未完成，请补充剩余章节的简洁大纲条目：\n"
                f"…{reply.strip()[-400:]}"
            )
        wrap_up = await chat_completion(
            [{"role": "system", "content": "你是一位专业策划师。请简洁补充剩余章节的大纲，保持格式一致。"},
             {"role": "user", "content": wrap_user}],
            temperature=0.5,
            max_tokens=8192,
            timing_label="macro_outline_wrap_up",
        )
        if wrap_up and len(wrap_up.strip()) > 30:
            reply = reply.rstrip() + "\n\n" + wrap_up.strip()
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

    # ── Agent path: character-driven emergent narrative ──
    target_words = ch.target_word_count if ch else 0
    dynamic_max_tokens = min(32768, max(4096, int(target_words * 2.5) + 500)) if target_words > 0 else 8192
    used_chunked_path = False

    # Try agent path first if enabled; fall back to normal generation on failure
    _agent_reply = None
    _agent_fail_reason = ""
    if world.story.writing_defaults.enable_character_agents:
        try:
            _agent_reply = await _generate_manuscript_with_agents(
                world, chapter_id, beat, macro, prev, user_hint or prompt,
                person_eff, system, user_effective,
            )
        except Exception as e:
            _agent_fail_reason = f"Agent 路径异常: {e}"
            _agent_reply = None

    _agent_path_succeeded = False
    if _agent_reply and len(_agent_reply.strip()) > 200:
        reply = _agent_reply
        _agent_path_succeeded = True
        # Agent path already handled truncation internally for the writer agent.
        # But do a final heuristic check here as safety net.
        if _text_looks_truncated(reply):
            continue_max_tokens = max(dynamic_max_tokens, 8192)
            continue_user = (
                f"请继续写下去，直到本章自然结束。从以下内容结尾接着写:\n"
                f"…{reply.strip()[-500:]}\n\n请直接续写正文："
            )
            continuation = await chat_completion(
                [{"role": "system", "content": "你是一位专业小说作家。请续写章节正文，直接输出，不要重复已有内容。"},
                 {"role": "user", "content": continue_user}],
                temperature=0.75,
                max_tokens=continue_max_tokens,
                timing_label="manuscript_agent_continue",
            )
            if continuation and len(continuation.strip()) > 50:
                reply = reply.rstrip() + "\n\n" + continuation.strip()
    else:
        # ── Normal path: Scene chunking or single-call generation ──
        if world.story.writing_defaults.enable_scene_chunking and beat.strip() and target_words >= 2500:
            hard_ctx = build_hard_context(world, chapter_id, beat)
            chunked = await _generate_manuscript_chunked(
                world, chapter_id, beat, target_words, hard_ctx, person_eff,
            )
            if chunked and len(chunked) > 500:
                reply = chunked
                used_chunked_path = True
            else:
                # Fall through to normal generation
                reply = await chat_completion(
                    [{"role": "system", "content": system}, {"role": "user", "content": user_effective}],
                    temperature=0.75, max_tokens=dynamic_max_tokens,
                    timing_label="manuscript_generation",
                )
        else:
            reply = await chat_completion(
                [{"role": "system", "content": system}, {"role": "user", "content": user_effective}],
                temperature=0.75, max_tokens=dynamic_max_tokens,
                timing_label="manuscript_generation",
            )

    # ── Agent fallback reason: detect WHY the agent path didn't succeed ──
    if world.story.writing_defaults.enable_character_agents and not _agent_path_succeeded:
        if not _agent_fail_reason and _agent_reply:
            _agent_fail_reason = f"Agent 路径输出过短 ({len(_agent_reply.strip())} 字符)，回退正常生成"
        elif not _agent_fail_reason:
            _agent_fail_reason = "Agent 路径返回空结果（可能缺乏角色数据或 LLM 调用失败）"
        print(f"[MCW-AGENT] ch:{chapter_id} FALLBACK: {_agent_fail_reason}")
        # Store for frontend reporting
        _agent_fallback_reported = _agent_fail_reason
    elif world.story.writing_defaults.enable_character_agents and _agent_path_succeeded:
        _agent_fallback_reported = ""
    else:
        _agent_fallback_reported = ""

    # ── Capture finish_reason IMMEDIATELY after generation ──
    # Must capture before any sub-calls (refusal retry, post-hooks) pollute _CALL_LOG.
    # NOTE: When agent path succeeded, _CALL_LOG is already polluted by agent sub-calls.
    # The agent path handles its own truncation detection internally.
    from worldforger.llm import _CALL_LOG as _TIMING_LOG, any_finish_reason_was_length
    _gen_finish_reason = ""
    _gen_was_truncated = False
    if not _agent_path_succeeded and _TIMING_LOG:
        _gen_finish_reason = _TIMING_LOG[-1].get("finish_reason", "") or ""
        if _gen_finish_reason == "length":
            _gen_was_truncated = True
    # For chunked path: check ALL sub-calls (scene drafts may have been truncated individually)
    if used_chunked_path and not _gen_was_truncated:
        _gen_was_truncated = any_finish_reason_was_length()

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
        # Re-capture finish_reason after retry
        _gen_was_truncated = False
        _gen_finish_reason = ""
        if _TIMING_LOG:
            _gen_finish_reason = _TIMING_LOG[-1].get("finish_reason", "") or ""
            if _gen_finish_reason == "length":
                _gen_was_truncated = True

    # ── Truncation detection & auto-continuation ──
    # Agent path already has its own truncation handling; only run heuristic check
    for continuation_round in range(3):
        was_truncated = (not _agent_path_succeeded) and (_gen_was_truncated or False)

        # Heuristic fallback: check if text looks incomplete (runs for both paths)
        if not was_truncated:
            was_truncated = _text_looks_truncated(reply)
        # LLM-based completeness check (more reliable than heuristic)
        if not was_truncated and len(reply.strip()) > 500:
            was_truncated = await _check_chapter_incomplete(reply, beat)
        if not was_truncated:
            break

        # Continue writing — use larger max_tokens to reduce chained truncation
        continue_max_tokens = min(32768, max(dynamic_max_tokens, 16384))
        continue_user = (
            f"请继续写下去，直到本章自然结束。以下是本章的细纲和当前已写到的位置，"
            f"请基于细纲判断还剩下哪些内容需要写，然后从截断处接着写：\n\n"
            f"【本章细纲（参考需要覆盖的场景）】\n{beat[:1200] if beat else '（无）'}\n\n"
            f"【当前已写到的位置（请从此处接着写）】\n…{reply.strip()[-3000:]}\n\n"
            f"请直接续写正文，不要重复已有内容，直到本章自然结束："
        )
        continuation = await chat_completion(
            [{"role": "system", "content": "你是一位专业小说作家。请续写章节正文，直接输出，不要重复已有内容。"},
             {"role": "user", "content": continue_user}],
            temperature=0.75,
            max_tokens=continue_max_tokens,
            timing_label=f"manuscript_continue_{continuation_round+1}",
        )
        if continuation and len(continuation.strip()) > 50:
            reply = reply.rstrip() + "\n\n" + continuation.strip()
            # Update truncation flag for next loop iteration
            _gen_was_truncated = False
            if _TIMING_LOG:
                _gen_was_truncated = _TIMING_LOG[-1].get("finish_reason", "") == "length"
        else:
            break  # No meaningful continuation, stop

        # If continuation finished cleanly, stop
        if not _gen_was_truncated and not _text_looks_truncated(reply):
            break

    # ── Final wrap-up: if text STILL looks truncated after all rounds, do one
    #     dedicated "write a concluding paragraph" call ──
    if _text_looks_truncated(reply) and len(reply.strip()) > 500:
        wrap_user = (
            f"以下章节正文尚未完成，请在结尾续写一个简短的自然收束段落（200-500字），"
            f"让本章有一个完整的结尾感。直接续写，不要重复已有内容：\n"
            f"…{reply.strip()[-400:]}"
        )
        wrap_up = await chat_completion(
            [{"role": "system", "content": "你是一位专业小说作家。请为章节写一个收束段落，让章节自然结束。"},
             {"role": "user", "content": wrap_user}],
            temperature=0.7,
            max_tokens=1024,
            timing_label="manuscript_wrap_up",
        )
        if wrap_up and len(wrap_up.strip()) > 30:
            reply = reply.rstrip() + "\n\n" + wrap_up.strip()

    # Strip chX references from manuscript (common AI artifact)
    import re as _re
    reply = _re.sub(r'(?:在|于|见|参见|参考)\s*ch[_]?\d+\s*[中里内]?(?:已经|已|曾)?', '', reply)
    reply = _re.sub(r'ch[_]?\d+\s*[中里内]', '', reply)

    # ── Programmatic punctuation normalization (always-on, no LLM cost) ──
    from worldforger.punctuation_normalize import normalize_and_log
    reply = normalize_and_log(reply, f"ch:{chapter_id}")

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

    # Character pressure update (no LLM, rule-based)
    if world.story.writing_defaults.enable_break_mechanism:
        post_hooks.append(_update_character_pressures(world, chapter_id, reply))

    # Epic density check (no LLM, just regex)
    if world.story.writing_defaults.enable_epic_density_check:
        _run_epic_density_check(chapter_id, reply)

    # ── P2: Unified extractors path (when enabled) ──
    if world.story.writing_defaults.enable_unified_extractors and post_hooks:
        post_hooks = [
            _unified_narrative_state_extractor(world, chapter_id, reply),
            _unified_knowledge_plot_extractor(world, chapter_id, reply),
            _unified_quality_reviewer(world, chapter_id, reply),
            _run_timeline_fallback(world, chapter_id, reply),
        ]
        # Only run sentiment fallback if the feature is enabled AND the
        # unified reviewer may have failed to produce sentiment data
        if world.story.writing_defaults.enable_sentiment_track:
            post_hooks.append(_run_sentiment_fallback(world, chapter_id, reply))

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

    # ── Agent fallback reason → surface to frontend as warning ──
    if _agent_fallback_reported:
        hook_errors.append(f"[Agent 回退] {_agent_fallback_reported}")

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
    # Strip chX references from manuscript (common AI artifact)
    import re as _re
    reply = _re.sub(r'(?:在|于|见|参见|参考)\s*ch[_]?\d+\s*[中里内]?(?:已经|已|曾)?', '', reply)
    reply = _re.sub(r'ch[_]?\d+\s*[中里内]', '', reply)

    # ── Truncation detection & auto-continuation (stream path) ──
    # The streaming API doesn't expose finish_reason, so we rely on the
    # heuristic.  Run up to 2 continuation rounds to finish the chapter.
    for cont_round in range(2):
        if not _text_looks_truncated(reply):
            break
        target_words_ = ch.target_word_count if ch else 0
        cont_max_tokens = min(16384, max(4096, int(target_words_ * 2.5) + 500)) if target_words_ > 0 else 8192
        continue_user = (
            f"请继续写下去，直到本章自然结束。从以下内容结尾接着写:\n"
            f"…{reply.strip()[-500:]}\n\n请直接续写正文："
        )
        continuation = await chat_completion(
            [{"role": "system", "content": "你是一位专业小说作家。请续写章节正文，直接输出，不要重复已有内容。"},
             {"role": "user", "content": continue_user}],
            temperature=0.75,
            max_tokens=cont_max_tokens,
            timing_label=f"manuscript_stream_continue_{cont_round+1}",
        )
        if continuation and len(continuation.strip()) > 50:
            yield {"type": "text", "content": "\n\n" + continuation.strip()}
            reply = reply.rstrip() + "\n\n" + continuation.strip()
        else:
            break
    # Final wrap-up if still truncated
    if _text_looks_truncated(reply) and len(reply.strip()) > 500:
        wrap_user = (
            f"以下章节正文尚未完成，请在结尾续写一个简短的自然收束段落（200-500字），"
            f"让本章有一个完整的结尾感。直接续写，不要重复已有内容：\n"
            f"…{reply.strip()[-400:]}"
        )
        wrap_up = await chat_completion(
            [{"role": "system", "content": "你是一位专业小说作家。请为章节写一个收束段落，让章节自然结束。"},
             {"role": "user", "content": wrap_user}],
            temperature=0.7,
            max_tokens=1024,
            timing_label="manuscript_stream_wrap_up",
        )
        if wrap_up and len(wrap_up.strip()) > 30:
            yield {"type": "text", "content": "\n\n" + wrap_up.strip()}
            reply = reply.rstrip() + "\n\n" + wrap_up.strip()

    # ── Programmatic punctuation normalization (always-on, no LLM cost) ──
    from worldforger.punctuation_normalize import normalize_and_log
    reply = normalize_and_log(reply, f"ch:{chapter_id}")

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

    # Character pressure update (no LLM, rule-based)
    if world.story.writing_defaults.enable_break_mechanism:
        post_hooks.append(_update_character_pressures(world, chapter_id, reply))

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


# ── Agent-driven manuscript generation ──────────────────────────────────

async def _generate_manuscript_with_agents(
    world, chapter_id, beat_text, macro_text, prev_manuscripts,
    user_hint, person_eff, writer_system, writer_user,
) -> str:
    """Generate chapter manuscript using character agent simulation.

    Raises RuntimeError with specific reason on failure so the caller
    can report the exact cause to the user.
    """
    from worldforger.agents import (
        CharacterAgent, SceneSimulator, POVFilter, StateInjector,
        OutlineConstraint, BeatReference, ContinuityChecker, AgentStore,
    )
    from worldforger.agents.types import CharacterAgentState

    _failures: list[str] = []  # collect all failure reasons

    # Step 1: Parse macro constraints
    try:
        constraints = await OutlineConstraint.parse(macro_text or "", chapter_id)
    except Exception as e:
        _failures.append(f"粗纲解析失败: {e}")
        constraints = OutlineConstraint.parse.__wrapped__ if hasattr(OutlineConstraint.parse, '__wrapped__') else None
        if constraints is None:
            from worldforger.agents.types import OutlineConstraints
            constraints = OutlineConstraints()

    # Step 2: Load or initialize agent states
    agent_states = {}
    try:
        agent_states = AgentStore.load_all_states(world.meta.id)
        if not agent_states:
            agent_states = AgentStore.init_states_from_world(world.meta.id, world)
    except Exception as e:
        _failures.append(f"Agent 状态加载/初始化失败: {e}")

    if not agent_states:
        raise RuntimeError(f"Agent 涌现不可用：未找到任何角色数据。{' | '.join(_failures)}")

    # Step 3: POV character and scene characters
    pov_id = world.story.narrator.character_id or "ch_yunhe"
    # Determine which characters appear in this scene from the beat
    scene_char_ids = set()
    if beat_text:
        scene_char_ids = _extract_character_ids_from_beat(world, beat_text)
    # Always include POV character
    scene_char_ids.add(pov_id)
    # Limit to characters that actually have agent states
    scene_char_ids = {cid for cid in scene_char_ids if cid in agent_states}

    present_states = {cid: agent_states[cid] for cid in scene_char_ids}
    shadow_states = {cid: s for cid, s in agent_states.items() if cid not in scene_char_ids}

    # Step 4: Beat soft references
    soft_hints = None
    beat_ref = None
    if beat_text and beat_text.strip():
        beat_ref = await BeatReference.parse(beat_text)
        if beat_ref:
            soft_hints = BeatReference.inject_as_soft_hints(beat_ref)

    # Step 5: Build scene setup
    scene_setup = _build_scene_setup_from_context(
        world, chapter_id, beat_text, macro_text, prev_manuscripts,
    )
    scene_setup = OutlineConstraint.inject_to_scene(constraints, scene_setup)

    # Step 6: Pre-generation continuity check
    continuity = ContinuityChecker.pre_generation_check(
        present_states, scene_setup, pov_id=pov_id,
    )
    if continuity.warnings:
        scene_setup += "\n\n【连续性提醒】" + "\n".join(
            f"- {w}" for w in continuity.warnings[:5]
        )

    # Step 7: Create agent instances and run simulation
    # Inject character capabilities (skills, items, attributes, activation rules)
    _inject_character_capabilities(agent_states, world)

    agents = {
        cid: CharacterAgent(
            state, base_temperature=_char_agent_temp(cid)
        )
        for cid, state in {**present_states, **shadow_states}.items()
    }

    sim = SceneSimulator(
        max_rounds=world.story.writing_defaults.agent_max_rounds,
    )
    sim_result = await sim.run(
        agents=agents,
        pov_character_id=pov_id,
        scene_setup=scene_setup,
        macro_events=constraints.hard_events,
        soft_hints=soft_hints,
    )
    sim_result.chapter_id = chapter_id

    # Step 8: POV filter + reader knowledge hints
    reader_hints = POVFilter.annotate_reader_knowledge(
        sim_result.pov_visible_events,
        sim_result.shadow_events,
        world.story.foreshadowing,
    )

    # ── P2: WorldClock — time progression + external events ──
    from worldforger.agents.world_clock import WorldClock
    ch_num = next((c.order for c in world.story.chapters if c.id == chapter_id), 1)
    clock = WorldClock()
    external_events = clock.advance_chapter(ch_num)
    if external_events:
        time_ctx = clock.scene_context_block()
        scene_setup = time_ctx + "\n" + scene_setup
        for evt in external_events:
            sim_result.macro_events.append(f"[世界事件] {evt.description}")

    # ── P2: ShadowInfluence — off-screen character hints ──
    from worldforger.agents.shadow_influence import ShadowInfluence
    shadow_hints = ShadowInfluence.generate_hints(sim_result.shadow_events)
    fs_links = ShadowInfluence.link_to_foreshadowing(
        shadow_hints, world.story.foreshadowing,
    )
    shadow_context = ShadowInfluence.format_shadow_context(
        sim_result.shadow_events, shadow_hints, fs_links,
    )

    # ── P2: SceneAssembler — pacing check ──
    from worldforger.agents.scene_assembler import SceneAssembler
    pacing = SceneAssembler.check_pacing([sim_result])

    # ── P1: BeatCoordinator — deviation handling ──
    from worldforger.agents.beat_coordinator import BeatCoordinator
    deviation = None
    if beat_ref:
        deviation = BeatCoordinator.classify_deviation(beat_ref, sim_result)
        if BeatCoordinator.should_warn(deviation):
            print(f"[MCW-AGENT] ch:{chapter_id} beat deviation: {deviation.get('detail','')[:150]}")

    # Step 9: Build writer agent prompt with agent simulation results
    pov_state = present_states.get(pov_id) or shadow_states.get(pov_id)
    state_context = ""
    if pov_state:
        state_context = StateInjector.for_writer_agent(
            pov_state, present_states, shadow_states,
        )

    # Assemble agent-informed writer prompt
    pov_events_block = "\n".join(
        f"  {e}" for e in sim_result.pov_visible_events[:20]
    )
    agent_writer_user = (
        writer_user + "\n\n" +
        "【角色 Agent 模拟结果 — 以下是角色们在场景中的自主决策序列】\n"
        f"{pov_events_block}\n\n"
        f"{state_context}\n\n"
        + (f"【读者线索提示】{reader_hints}\n\n" if reader_hints else "")
        + (f"{shadow_context}\n\n" if shadow_context else "")
        + (f"【节奏提示】{pacing.get('rhythm','')} | {', '.join(pacing.get('suggestions',[])[:2])}\n\n" if pacing.get("suggestions") else "")
        + "【写作规则 — 单 POV 模式】\n"
        f"1. 只写 {pov_state.name if pov_state else pov_id} 能感知到的内容。\n"
        "2. 不要写其他角色的内心独白。动机只能通过对话/动作暗示。\n"
        "3. POV 角色的内部反应可以写。误解和不确信保留，不要以叙述者口吻纠正。\n"
        "4. 粗纲的世界事件必须发生，但角色应对方式由上述 Agent 决策决定。\n"
    )

    # Call writer agent — use same dynamic sizing as normal path
    ch_num_real = next((c.order for c in world.story.chapters if c.id == chapter_id), 1)
    target_wc = next((c.target_word_count for c in world.story.chapters if c.id == chapter_id), 0)
    _writer_max_tokens = min(32768, max(8192, int(target_wc * 2.5) + 500)) if target_wc > 0 else 8192
    draft = await chat_completion(
        [{"role": "system", "content": writer_system},
         {"role": "user", "content": agent_writer_user}],
        temperature=0.75,
        max_tokens=_writer_max_tokens,
        timing_label="writer_agent",
    )

    # ── Capture writer agent finish_reason IMMEDIATELY ──
    # Subsequent steps (persistence, quality eval) will append to _CALL_LOG
    from worldforger.llm import _CALL_LOG as _WLOG
    _writer_truncated = False
    if _WLOG:
        _writer_truncated = _WLOG[-1].get("finish_reason", "") == "length"

    # ── Truncation continuation for writer agent ──
    for _wc in range(3):
        if not _writer_truncated and not _text_looks_truncated(draft):
            # Additional LLM completeness check (more reliable)
            if len(draft.strip()) > 500:
                incomplete = await _check_chapter_incomplete(draft, beat_text)
                if not incomplete:
                    break
            else:
                break
        cont_user = (
            f"请继续写下去，直到本章自然结束。以下是本章的细纲和当前已写到的位置：\n\n"
            f"【本章细纲（参考需要覆盖的场景）】\n{beat_text[:1200] if beat_text else '（无）'}\n\n"
            f"【当前已写到的位置（请从此处接着写）】\n…{draft.strip()[-3000:]}\n\n"
            f"请直接续写正文，不要重复已有内容，直到本章自然结束："
        )
        cont = await chat_completion(
            [{"role": "system", "content": "你是一位专业小说作家。请续写章节正文，直接输出，不要重复已有内容。"},
             {"role": "user", "content": cont_user}],
            temperature=0.75,
            max_tokens=8192,
            timing_label=f"writer_agent_continue_{_wc+1}",
        )
        if cont and len(cont.strip()) > 50:
            draft = draft.rstrip() + "\n\n" + cont.strip()
            _writer_truncated = False
            if _WLOG:
                _writer_truncated = _WLOG[-1].get("finish_reason", "") == "length"
        else:
            break

    # Final wrap-up if still looks truncated
    if _text_looks_truncated(draft) and len(draft.strip()) > 500:
        wrap_u = (
            f"以下章节正文尚未完成，请在结尾续写一个简短的自然收束段落（200-500字），"
            f"让本章有一个完整的结尾感。直接续写，不要重复已有内容：\n"
            f"…{draft.strip()[-400:]}"
        )
        wrap = await chat_completion(
            [{"role": "system", "content": "你是一位专业小说作家。请为章节写一个收束段落，让章节自然结束。"},
             {"role": "user", "content": wrap_u}],
            temperature=0.7,
            max_tokens=1024,
            timing_label="writer_agent_wrap_up",
        )
        if wrap and len(wrap.strip()) > 30:
            draft = draft.rstrip() + "\n\n" + wrap.strip()

    # Step 10: Persist agent states
    new_states = ContinuityChecker.post_generation_update(sim_result, agent_states)
    for cid, state in new_states.items():
        AgentStore.save_state(world.meta.id, state)
        AgentStore.append_decision_log(
            world.meta.id, cid, chapter_id,
            [d for d in sim_result.decision_sequence if d.character_id == cid],
        )

    # Log beat deviation if any
    if beat_ref:
        deviation = BeatReference.record_deviation(beat_ref, sim_result)
        if deviation:
            print(f"[MCW-AGENT] ch:{chapter_id} beat deviation: {deviation[:120]}")

    # ── P3: Quality evaluation ──
    from worldforger.agents.quality_evaluator import QualityEvaluator
    quality = QualityEvaluator.evaluate(
        sim_result,
        continuity_issues=len(continuity.warnings) if continuity else 0,
    )
    quality_msg = f"[MCW-QUALITY] ch:{chapter_id} grade={quality['grade']} overall={quality['overall']} pacing={quality['scores'].get('pacing',0)} arc={quality['scores'].get('character_arc',0)} dialog={quality['scores'].get('dialog',0)}"
    print(quality_msg)
    if quality["suggestions"]:
        for s in quality["suggestions"][:2]:
            print(f"[MCW-QUALITY] ch:{chapter_id} suggestion: {s}")

    return draft


def _build_scene_setup_from_context(
    world, chapter_id, beat_text, macro_text, prev_manuscripts,
) -> str:
    """Build initial scene setup text from all available context."""
    parts = []
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    if ch:
        parts.append(f"章节: 第{ch.order}章「{ch.title}」")

    if macro_text:
        # Extract relevant section for this chapter
        macro_short = macro_text[:2000]
        parts.append(f"\n粗纲指引:\n{macro_short}")

    if beat_text:
        parts.append(f"\n细纲参考:\n{beat_text[:1500]}")

    if prev_manuscripts:
        prev_id, prev_text = prev_manuscripts[-1]
        parts.append(f"\n上一章结尾 ({prev_id}):\n{prev_text.strip()[-500:]}")

    return "\n\n".join(parts)


def _char_agent_temp(char_id: str) -> float:
    """Return base temperature for a character agent."""
    _TEMP_MAP = {
        "ch_qinyuan": 0.35,
        "ch_mistwalker_k": 0.75,
        "ch_yunhe": 0.55,
        "ch_dayna": 0.65,
    }
    return _TEMP_MAP.get(char_id, 0.55)


def _inject_character_capabilities(
    agent_states: dict, world,
) -> None:
    """Inject character capabilities into each agent state for combat/conflict.

    Injects four categories:
    1. Skills — from power_system tier's skill_tree/subclass_paths
    2. Inventory — from character.inventory (items with usage descriptions)
    3. Attributes — from character.attributes {stat_id: value}
    4. Activation rules — from power_system tier/skill_node activation_rules

    All stored as `_activation_rules_context` for the character prompt builder.
    """
    tiers = getattr(getattr(world, 'power_system', None), 'tiers', None) or []
    attr_stats = getattr(getattr(world, 'attribute_system', None), 'stats', None) or []

    for cid, state in agent_states.items():
        rules: list[str] = []

        # Find the character entity from world
        char_ent = next(
            (e for e in (getattr(world, 'characters', None) and getattr(world.characters, 'entities', None) or [])
             if isinstance(e, dict) and e.get('id') == cid), None
        )
        if not char_ent:
            continue

        # ── 1. Skills ──
        char_tier_name = char_ent.get('power_tier', '')
        known_skill_ids = set()
        if char_tier_name:
            tier = next((t for t in tiers if t.name == char_tier_name), None)
            if tier:
                rules.append(f"\n## 你掌握的技能")
                for sn in (tier.skill_tree or []):
                    known_skill_ids.add(sn.id)
                    desc = f"{sn.name}"
                    if sn.description:
                        desc += f" — {sn.description[:80]}"
                    if sn.cost:
                        desc += f"（代价: {sn.cost}）"
                    rules.append(f"- {desc}")
                for sp in (tier.subclass_paths or []):
                    sp_name = getattr(sp, 'name', '') or sp.id or '子流派'
                    for sn in (sp.skill_tree or []):
                        known_skill_ids.add(sn.id)
                        desc = f"[{sp_name}] {sn.name}"
                        if sn.description:
                            desc += f" — {sn.description[:80]}"
                        if sn.cost:
                            desc += f"（代价: {sn.cost}）"
                        rules.append(f"- {desc}")

        # ── 2. Inventory ──
        inventory = char_ent.get('inventory', []) or []
        active_items = [i for i in inventory if i.get('status') != '已失去' and i.get('name', '').strip()]
        if active_items:
            rules.append(f"\n## 你携带的物品（可以在场景中使用）")
            for item in active_items:
                desc = f"【{item.get('name','')}】"
                if item.get('description', '').strip():
                    desc += f" — {item.get('description','')[:60]}"
                if item.get('usage', '').strip():
                    desc += f"。用法: {item.get('usage','')[:80]}"
                if item.get('quantity', 1) > 1:
                    desc += f"（×{item.get('quantity')}）"
                rules.append(f"- {desc}")

        # ── 3. Attributes ──
        char_attrs = char_ent.get('attributes', {}) or {}
        if char_attrs and attr_stats:
            rules.append(f"\n## 你的属性值（0-100，用于对抗判定参考）")
            for stat in attr_stats:
                val = char_attrs.get(stat.id, stat.reference_percent)
                rules.append(f"- {stat.name}（{stat.abbreviation or stat.id}）: {val}/100"
                             + (f" — {stat.intro}" if stat.intro else ""))

        # ── 4. Activation rules ──
        if char_tier_name:
            tier = next((t for t in tiers if t.name == char_tier_name), None)
            if tier:
                # Collect tier-level activation rules
                tier_skill_ids = {sn.id for sn in (tier.skill_tree or [])}
                for sp in (tier.subclass_paths or []):
                    tier_skill_ids.update(sn.id for sn in (sp.skill_tree or []))
                if known_skill_ids & tier_skill_ids:
                    if getattr(tier, 'activation_rules', None) and str(tier.activation_rules).strip():
                        rules.append(f"\n## 能力发动规则（必须严格遵守）")
                        rules.append(f"【{tier.name}境】{tier.activation_rules.strip()}")
                    # Per-node activation rules
                    for sn in (tier.skill_tree or []):
                        if sn.id in known_skill_ids and getattr(sn, 'activation_rules', None) and str(sn.activation_rules).strip():
                            rules.append(f"【技能 {sn.name}】{sn.activation_rules.strip()}")
                    for sp in (tier.subclass_paths or []):
                        for sn in (sp.skill_tree or []):
                            if sn.id in known_skill_ids and getattr(sn, 'activation_rules', None) and str(sn.activation_rules).strip():
                                rules.append(f"【技能 {sn.name}】{sn.activation_rules.strip()}")

        if rules:
            state._activation_rules_context = rules


async def _check_chapter_incomplete(text: str, beat_text: str = "") -> bool:
    """LLM-based check: does this chapter appear to have finished naturally?

    More reliable than heuristic checks. Uses a minimal prompt and low max_tokens.
    Returns True if the chapter looks INCOMPLETE (needs continuation).
    """
    tail = text.strip()[-2000:]
    beat_hint = f"细纲参考: {beat_text[:600]}" if beat_text and beat_text.strip() else ""
    prompt = (
        f"检查以下小说章节是否已经写完。只回答 YES（已完成）或 NO（未完成）。\n"
        f"{beat_hint}\n"
        f"章节结尾部分:\n...{tail}\n\n"
        f"判断标准: 1) 场景是否有自然收束 2) 对话/行动是否完整 3) 是否明显在中途截断。"
        f"只输出 YES 或 NO:"
    )
    try:
        raw = await chat_completion(
            [{"role": "system", "content": "你是一个文本完整性检查器。只输出 YES 或 NO。"},
             {"role": "user", "content": prompt}],
            temperature=0.1, max_tokens=10,
            timing_label="completeness_check",
        )
        result = raw.strip().upper()
        return "NO" in result  # True = incomplete, needs continuation
    except Exception:
        return False  # on error, assume complete (don't loop forever)


def _text_looks_truncated(text: str) -> bool:
    """Heuristic check: does *text* look like it was cut off mid-sentence or mid-word?

    Returns True when the text appears incomplete (truncated by token limit),
    False when it appears to end naturally.
    """
    if not text or len(text.strip()) < 100:
        return False
    t = text.strip()
    tail = t[-300:]
    # ── Markers that indicate a deliberate ending ──
    _ENDING_MARKERS = (
        "## ", "本章完", "（完）", "（未完待续）", "（待续）",
        "作者备注", "润色说明", "（全文完）", "【完】",
        "——全文完——", "（终）",
    )
    if any(m in tail[-150:] for m in _ENDING_MARKERS):
        return False
    # ── Natural sentence-ending punctuation ──
    # NOTE: "——" is deliberately excluded — ending with a dash is ambiguous
    # and often signals truncation; it's handled by the truncation checks below.
    _SENTENCE_END = ("。", "！", "？", "…", "……", "」", "）", "】", "\"", "'", "；")
    if t.endswith(_SENTENCE_END):
        # Ends with proper punctuation — check if final paragraph has
        # reasonable length (not a sudden 1-sentence fragment).
        # 12 chars ≈ minimum for a complete Chinese sentence like "他找到了答案。"
        last_para = t.rsplit("\n\n", 1)[-1] if "\n\n" in t else t[-200:]
        if len(last_para.strip()) >= 12:
            return False
    # ── Signs of truncation ──
    # 1. Ends mid-word: common Chinese compounds that rarely end a sentence
    _MID_WORD_PATTERNS = (
        "的同", "的时", "的一", "的那", "的这",  # incomplete "同一/同时/一样/那个/这个"
        "了一", "了个", "了一",  # incomplete "了一下/了一个"
        "然没", "然不", "然是",  # incomplete "然而/虽然"
        "过这", "过一", "过那",  # incomplete "过这个/过一次/过那个"
        "着这", "着一", "着那",  # incomplete "着这个/着一个"
        "来的", "去的",  # incomplete compound
        "走在", "站在", "坐在", "看着", "想着", "说道",  # incomplete "走在XX/站在XX..."
        "和她", "和他", "和那", "和这",  # incomplete
        "从那", "从那", "把那", "把这",  # incomplete
        "没有完", "没有说", "没有看", "没有再",  # incomplete
        "突然感", "突然想", "突然发",  # incomplete
    )
    for pat in _MID_WORD_PATTERNS:
        if t.endswith(pat):
            return True
    # 2. Last char is a comma (mid-clause)
    if t[-1] in "，,、":
        return True
    # 3. Ends with a colon or dash suggesting continuation
    if t[-1] in "：:—" and len(t) > 2000:
        return True
    # 4. Final paragraph is very short (< 15 chars) suggesting it just started.
    #    Only flag when it doesn't end with sentence-ending punctuation —
    #    a short paragraph ending with "。" is a legitimate stylistic choice.
    last_para = t.rsplit("\n\n", 1)[-1] if "\n\n" in t else t[-200:]
    if len(last_para.strip()) < 15 and len(t) > 2000 and not t.endswith(_SENTENCE_END):
        return True
    # 5. Text is long (>2000 chars) and ends without any sentence-ending punctuation
    if len(t) > 2000:
        if not t.endswith(_SENTENCE_END) and t[-1] not in "，,、：:—":
            return True
    return False


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
        temperature=0.7, max_tokens=max(2048, int(est * 3.5)),
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
    """Scene-chunked manuscript generation: Plan → Draft (sequential) → Merge.

    Scenes are drafted *sequentially* so each scene can see the previous
    scene's ending for continuity.  Concurrency is traded for coherence.
    """
    # Step 1: Scene plan
    scenes = await _generate_scene_plan(world, chapter_id, beat_text, target_words, person)
    if len(scenes) < 2:
        return ""  # Fall through to normal generation

    # Step 2: Generate each scene sequentially — each draft receives the
    #         previous scene's last 200 chars as the ``prev_scene_end`` hint.
    drafts: list[str] = []
    prev_scene_end = ""
    for i, sc in enumerate(scenes):
        draft = await _generate_scene_draft(
            world, sc, prev_scene_end, hard_context, person,
        )
        if draft and len(draft.strip()) > 50:
            drafts.append(draft.strip())
            # Feed the last ~200 chars of THIS scene as the next scene's context
            prev_scene_end = draft.strip()[-200:]
        else:
            # This scene produced nothing meaningful; next scene still gets
            # the previous valid scene's ending.
            pass

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
            from worldforger.sentiment_tracker import SentimentTracker, _TONE_NORMALIZE, _TRANSITION_NORMALIZE
            try:
                sent["title"] = ch.title or ""
                sent["analyzed_at"] = utc_now_iso()
                sent["chapter_id"] = chapter_id
                # ── Normalize tone labels (LLM may output Chinese) ──
                for key in ("overall_tone", "ending_tone"):
                    raw = str(sent.get(key, "")).strip()
                    sent[key] = _TONE_NORMALIZE.get(raw, "mixed")
                raw_trans = str(sent.get("transition_from_prev", "")).strip()
                sent["transition_from_prev"] = _TRANSITION_NORMALIZE.get(raw_trans, "first_chapter")
                # Normalize segments
                segs = sent.get("segments", [])
                if isinstance(segs, list):
                    for seg in segs:
                        if isinstance(seg, dict):
                            raw_tone = str(seg.get("tone", "")).strip()
                            seg["tone"] = _TONE_NORMALIZE.get(raw_tone, "mixed")
                            try:
                                seg["intensity"] = max(1, min(10, int(seg.get("intensity", 5))))
                            except (ValueError, TypeError):
                                seg["intensity"] = 5
                log = SentimentLog.model_validate(sent)
                ch.sentiment_log = log
                SentimentTracker(world.meta.id).save_log(log)
            except Exception as e:
                print(f"[MCW-SENTIMENT] ch:{chapter_id} unified reviewer validation: {e}")
                # Last resort: try with minimal defaults
                try:
                    sent["segments"] = [{"segment_index": 1, "label": "全文", "tone": "mixed", "intensity": 5, "summary": ""}]
                    log = SentimentLog.model_validate(sent)
                    ch.sentiment_log = log
                    SentimentTracker(world.meta.id).save_log(log)
                except Exception as e2:
                    print(f"[MCW-SENTIMENT] ch:{chapter_id} fallback also failed: {e2}")

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


async def _run_sentiment_fallback(world: World, chapter_id: str, manuscript_text: str) -> str:
    """Check if unified reviewer produced sentiment; if not, run individual hook.

    Checks BOTH in-memory (ch.sentiment_log) AND on-disk (SQLite/JSON)
    to avoid unnecessary duplicate LLM calls when sentiment was
    persisted by a previous session.
    """
    if not world.story.writing_defaults.enable_sentiment_track:
        return ""
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    # Check in-memory first
    if ch and ch.sentiment_log:
        return ""
    # Check disk (may have been persisted by unified extractor or previous session)
    from worldforger.story.story_store import read_sentiment_log
    if read_sentiment_log(world.meta.id, chapter_id):
        return ""
    return await _try_track_sentiment(world, chapter_id, manuscript_text)


async def _run_timeline_fallback(world: World, chapter_id: str, manuscript_text: str) -> str:
    """Check if unified extractor produced timeline events; if not, run individual hook."""
    tls = getattr(world, 'character_personal_timelines', None) or []
    ch_order = next((c.order for c in world.story.chapters if c.id == chapter_id), 0)
    # Check if any timeline event was added for this chapter by unified extractor
    for tl in tls:
        for e in tl.events:
            if e.chapter == chapter_id:
                return ""  # Already done
    if not world.story.writing_defaults.enable_personal_timeline_track:
        return ""
    return await _try_detect_timeline_events(world, chapter_id, manuscript_text)


async def _update_character_pressures(world: World, chapter_id: str, manuscript_text: str) -> str:
    """Rule-based character pressure tracking (no LLM call)."""
    try:
        from worldforger.schemas import CharacterPressure
        ch_order = next((c.order for c in world.story.chapters if c.id == chapter_id), 0)
        chars_in_ms = set()
        for ent in world.characters.entities:
            if isinstance(ent, dict):
                name = ent.get("name", "")
                if name and name in manuscript_text:
                    chars_in_ms.add(ent.get("id", ""))

        existing = {p.character_id: p for p in world.character_pressures}
        for cid in chars_in_ms:
            # Estimate pressure delta from text signals
            delta = 0
            factors = []
            # Simple keyword heuristics for pressure estimation
            if any(kw in manuscript_text for kw in ("战斗", "攻击", "危机", "死亡", "受伤")):
                delta += 12; factors.append({"factor": "战斗/危机", "intensity": 12, "decay_per_chapter": 3})
            if any(kw in manuscript_text for kw in ("隐瞒", "谎言", "秘密", "背叛", "欺骗")):
                delta += 10; factors.append({"factor": "隐瞒/秘密", "intensity": 10, "decay_per_chapter": 2})
            if any(kw in manuscript_text for kw in ("孤独", "绝望", "无助", "恐惧", "崩溃")):
                delta += 8; factors.append({"factor": "孤独/恐惧", "intensity": 8, "decay_per_chapter": 2})
            if any(kw in manuscript_text for kw in ("质疑", "冲突", "争吵", "对立")):
                delta += 6; factors.append({"factor": "人际冲突", "intensity": 6, "decay_per_chapter": 2})

            # Check active aftermaths
            active_ams = [a for a in world.character_aftermaths
                          if a.character_id == cid and a.current_status == "active"]
            if active_ams:
                delta += len(active_ams) * 5
                factors.append({"factor": "活跃后遗症", "intensity": len(active_ams)*5, "decay_per_chapter": 2})

            if cid in existing:
                p = existing[cid]
                # Natural decay for old factors
                for f in p.pressure_factors:
                    decay = f.get("decay_per_chapter", 3)
                    chapters_passed = ch_order - next((c.order for c in world.story.chapters
                        if c.id == p.last_updated_chapter), ch_order)
                    f["intensity"] = max(0, f.get("intensity", 0) - decay * chapters_passed)
                p.pressure_factors = [f for f in p.pressure_factors if f.get("intensity", 0) > 0]
                # Add new factors
                for f in factors:
                    p.pressure_factors.append(f)
                p.current_pressure = min(100, sum(f.get("intensity", 0) for f in p.pressure_factors))
                p.last_updated_chapter = chapter_id
            else:
                p = CharacterPressure(character_id=cid, current_pressure=min(100, delta),
                                      pressure_factors=factors, last_updated_chapter=chapter_id)
                world.character_pressures.append(p)
        return ""
    except Exception:
        return ""


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

        # ── Programmatic punctuation normalization (safety net after polish) ──
        from worldforger.punctuation_normalize import normalize_and_log
        current_text = normalize_and_log(current_text, f"ch:{chapter_id}:polished")

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
