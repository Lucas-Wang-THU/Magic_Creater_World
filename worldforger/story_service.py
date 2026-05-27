"""情节生成与章节管理业务逻辑。"""

from __future__ import annotations

import asyncio

from worldforger.llm import chat_completion
from worldforger.schemas import StoryChapter, StoryPerson, World
from worldforger.story_prompts import (
    build_chapter_summary_user_payload,
    build_character_state_user_payload,
    build_consistency_check_user_payload,
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
    sentiment_analysis_system,
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

    async def _gen_one_beat(cid: str) -> tuple[str, str]:
        ch = next((c for c in world.story.chapters if c.id == cid), None)
        if not ch:
            return cid, ""
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
        return cid, reply

    results = await asyncio.gather(*[_gen_one_beat(cid) for cid in chapter_ids])
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

    if post_hooks:
        await asyncio.gather(*post_hooks)

    # ── Layer 4：审校 ↔ 润色 Loop（内部自带一致性审校，不再重复调用）──
    if world.story.writing_defaults.enable_polisher:
        await _run_polish_loop(world, chapter_id, reply)

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


# ── 收尾：叙事知识图谱提取 ─────────────────────────────────


async def _try_extract_kg_events(world: World, chapter_id: str, manuscript_text: str) -> None:
    """正文生成后，从正文提取 KG 实体和事件。失败不阻塞。"""
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
        )
        data = _json.loads(reply.strip())
        if not isinstance(data, dict):
            return
        mgr = NarrativeKGManager(world.meta.id)
        kg = mgr.merge_extraction(data)
        world.story.narrative_kg = kg
    except Exception:
        pass


# ── 收尾：一致性审校 ──────────────────────────────────────


async def _try_run_consistency_check(world: World, chapter_id: str, manuscript_text: str) -> None:
    """正文生成后，运行 7 维度一致性审校。失败不阻塞。"""
    try:
        from worldforger.consistency_checker import run_consistency_check

        await run_consistency_check(world, chapter_id, manuscript_text)
    except Exception:
        pass


# ── 收尾：情感弧线追踪 ─────────────────────────────────────


async def _try_track_sentiment(world: World, chapter_id: str, manuscript_text: str) -> None:
    """正文生成后，分析情感弧线并保存。失败不阻塞。"""
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
        )
        log = _parse_sentiment(reply.strip(), chapter_id, ch.title if ch else "")
        if not log:
            return
        tracker = SentimentTracker(world.meta.id)
        tracker.save_log(log)
        if ch:
            ch.sentiment_log = log
    except Exception:
        pass


# ── Layer 4：审校 ↔ 润色反馈闭环 ─────────────────────────────


async def _run_polish_loop(world: World, chapter_id: str, manuscript_text: str) -> None:
    """Run the consistency-check ↔ polish feedback loop.

    Iterates up to ``polish_max_rounds`` times.  Each round:
      1. Run consistency check on the current text (or reuse the existing
         report for round 1).
      2. If verdict is clean or only info-level issues remain, exit.
      3. Feed issues into the polisher and generate a polished version.
      4. The polished text becomes the input for the next round.

    On completion the polished manuscript is written to
    ``story/polished/{chapter_id}.md`` and the chapter model is updated.
    Failure at any point does **not** block the main generation flow.
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

            # ── Step 1: Run consistency check ──
            from worldforger.consistency_checker import run_consistency_check

            report = await run_consistency_check(world, chapter_id, current_text)
            round_record["verdict"] = report.verdict
            round_record["total_issues"] = report.total_issues

            # Classify issues for this round
            current_issue_ids = {iss.issue_id for iss in report.issues} if report.issues else set()
            prev_issue_ids = set()
            for h in all_issues_history:
                for iss in h.get("issues", []):
                    prev_issue_ids.add(iss.get("issue_id", ""))

            fixed_ids = prev_issue_ids - current_issue_ids
            new_ids = current_issue_ids - prev_issue_ids
            persistent_ids = current_issue_ids & prev_issue_ids

            # Build classified issue lists
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

            # Reconstruct classified issues from history for "fixed" display
            for h in all_issues_history:
                for iss in h.get("issues", []):
                    if iss.get("issue_id") in fixed_ids:
                        iss["_classification"] = "fixed"
                        fixed_issues.append(iss)

            round_record["issues_before"] = all_issues_history[-1].get("issues", []) if all_issues_history else []
            round_record["issues_after"] = [iss.model_dump() if hasattr(iss, "model_dump") else {} for iss in (report.issues or [])]
            round_record["classification"] = {
                "fixed": fixed_issues,
                "persistent": persistent_issues,
                "regression": new_issues,
            }

            trace["rounds"].append(round_record)

            # ── Step 2: Check termination conditions ──
            non_critical_issues = [
                iss for iss in (report.issues or []) if iss.severity != "critical"
            ]
            if report.verdict == "clean" or report.total_issues == 0:
                trace["termination_reason"] = "clean"
                break
            if all(iss.severity == "info" for iss in (report.issues or [])):
                trace["termination_reason"] = "info_only"
                break
            if new_issues and all(
                iss.get("severity") == "critical"
                for iss in new_issues
                if isinstance(iss, dict)
            ):
                trace["termination_reason"] = "critical_only_new"
                break

            # ── Step 3: No fixable issues → exit ──
            if not non_critical_issues:
                trace["termination_reason"] = "no_fixable_issues"
                break

            # ── Step 4: Build polisher input ──
            from worldforger.story_prompts import (
                build_polisher_user_payload,
                format_consistency_issues_for_polisher,
                polisher_system,
            )

            # Format regression issues separately for higher priority
            regression_text = ""
            if new_issues:
                regression_lines = []
                for iss in new_issues:
                    sev = iss.get("severity", "warning")
                    cat = iss.get("category", "")
                    desc = iss.get("description", "")
                    sug = iss.get("suggestion", "")
                    regression_lines.append(f"  [REGRESSION-{sev}] {cat}: {desc}" + (f"（建议：{sug}）" if sug else ""))
                regression_text = "\n".join(regression_lines)

            issues_text = format_consistency_issues_for_polisher(report)

            system = polisher_system()
            user = build_polisher_user_payload(
                world,
                chapter_id,
                current_text,
                consistency_issues=issues_text,
                polish_round=round_idx,
                regression_issues=regression_text,
            )

            # ── Step 5: Call polisher LLM ──
            polished_reply = await chat_completion(
                [{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.35,
                max_tokens=8192,
            )

            if polished_reply and polished_reply.strip():
                current_text = polished_reply.strip()

            # Store current issues for next round comparison
            all_issues_history.append({
                "round": round_idx,
                "issues": [iss.model_dump() if hasattr(iss, "model_dump") else {} for iss in (report.issues or [])],
            })

            # ── Check max rounds after polish ──
            if round_idx >= max_rounds:
                trace["termination_reason"] = "max_rounds"
                break

        # ── After loop: persist polished result ──
        trace["actual_rounds"] = len(trace["rounds"])
        from worldforger.story_store import polished_path, polish_trace_path, write_text

        write_text(polished_path(world.meta.id, chapter_id), current_text)

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

    except Exception:
        # Polish loop failure does not block the main generation flow
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
