"""情节写作：粗纲、细纲、文稿生成用 system / user 拼装。"""

from __future__ import annotations

import json

from worldforger.creative_modes import normalize_creative_mode, outline_mode_addon
from worldforger.schemas import StoryPerson, World
from worldforger.story_store import resolve_unit_label, sorted_chapters
from worldforger.world_store import world_context_for_prompt

_PERSON_LABELS: dict[StoryPerson, str] = {
    "first_person": "第一人称",
    "third_person_limited": "第三人称（有限视角，仅贴近 POV 角色所知）",
    "third_person_omniscient": "第三人称（全知视角，可描写角色未察觉的信息，但勿无节制剧透未回收伏笔）",
}


def person_instruction(person: StoryPerson) -> str:
    return _PERSON_LABELS.get(person, _PERSON_LABELS["third_person_limited"])


def narrator_block(world: World, *, person_override: StoryPerson | None = None) -> str:
    n = world.story.narrator
    person = person_override or n.person
    lines = [f"叙事人称：{person_instruction(person)}"]
    cid = (n.character_id or "").strip()
    if cid:
        ent = next((e for e in world.characters.entities if str(e.get("id", "")).strip() == cid), None)
        name = str(ent.get("name", "")).strip() if isinstance(ent, dict) else ""
        lines.append(f"叙事人物（POV）：id={cid}" + (f"，姓名={name}" if name else ""))
    if (n.voice_notes or "").strip():
        lines.append(f"口吻与禁忌：{n.voice_notes.strip()}")
    return "\n".join(lines)


def story_mode_addon(mode: str | None, *, unit_label: str | None = None) -> str:
    m = normalize_creative_mode(mode)
    base = outline_mode_addon(mode) or ""
    extra = {
        "novel": "粗纲按幕/高潮组织；细纲按「章」写场景目标；文稿重描写与伏笔。",
        "game": "粗纲区分主线与分支；细纲按「章节」标玩法节点；文稿偏过场与引导。",
        "coc": "粗纲为调查链；细纲按「跑团会话」标线索层级；作者备注区可写守秘人真相。",
        "dnd": "粗纲为冒险路径；细纲按「跑团会话」标遭遇与等级感。",
    }.get(m or "", "按当前载体组织粗纲与细纲。")
    tail = f"\n【情节单位】每{unit_label}为一单元。" if unit_label else ""
    return (base + "\n" + extra + tail).strip()


def macro_outline_system(world: World, *, creative_mode: str | None) -> str:
    mode_eff = normalize_creative_mode(creative_mode) or world.meta.creative_mode
    unit = resolve_unit_label(world) if not mode_eff else _unit_for_mode(mode_eff)
    addon = story_mode_addon(mode_eff, unit_label=unit)
    return (
        "你是长篇叙事策划，负责撰写**粗纲**（全书/全模组流程总览）。\n"
        f"当前情节单元称为「{unit}」。\n"
        "你必须只依据世界设定，输出 Markdown（可用二/三级标题），描述从开端到结局的流程、主要转折与伏笔位。\n"
        "不要输出 JSON；不要写单章正文。\n"
        + (f"\n{addon}\n" if addon else "")
    )


def _unit_for_mode(mode: str | None) -> str:
    from worldforger.story_store import unit_label_for_mode

    return unit_label_for_mode(mode)


def chapter_beats_system(world: World, *, creative_mode: str | None) -> str:
    mode_eff = normalize_creative_mode(creative_mode) or world.meta.creative_mode
    unit = _unit_for_mode(mode_eff)
    return (
        "你是叙事策划，负责撰写**细纲**（单章/单会话要写什么）。\n"
        f"每个单元为一「{unit}」。\n"
        "输出 Markdown：场景目标、冲突、出场人物（对齐已有 id）、需种植/推进的伏笔、与粗纲的衔接。\n"
        "不要写完整正文。\n\n"
        "【叙事连贯性检查（在细纲开头用 3-5 行简要回答，再写细纲正文）】\n"
        "1. 上一章结尾各主要角色的位置与状态？本章开头如何承接？\n"
        "2. 上一章结尾未解决的悬念/钩子是什么？本章如何处理？\n"
        "3. 叙事人称是否与设定一致？若切换 POV，过渡是否明确？\n"
        "4. 本章与【粗纲】中对应段落的衔接点在哪里？\n"
        + (f"\n{story_mode_addon(mode_eff, unit_label=unit)}\n" if story_mode_addon(mode_eff, unit_label=unit) else "")
    )


def manuscript_system(world: World, *, creative_mode: str | None, person: StoryPerson | None) -> str:
    mode_eff = normalize_creative_mode(creative_mode) or world.meta.creative_mode
    unit = _unit_for_mode(mode_eff)
    return (
        "你是小说/跑团执笔者，根据世界设定、粗纲与细纲撰写**章节文稿**。\n"
        f"当前单元：{unit}。\n"
        f"{narrator_block(world, person_override=person)}\n"
        "输出 Markdown 正文；可在文末单独用「## 作者备注」写仅作者可见的信息（读者版将剥离）。\n"
        "禁止与 world.json 冲突；未回收伏笔不要在正文中提前揭穿。\n"
        + (f"\n{story_mode_addon(mode_eff, unit_label=unit)}\n" if story_mode_addon(mode_eff, unit_label=unit) else "")
    )


def compact_world_snippet(world: World, *, include_markdown: bool) -> str:
    """写作上下文用压缩世界块（避免塞入全文）。"""
    from worldforger.story_store import get_character_runtime_states

    data = world.model_dump(mode="json")
    for key in ("geography", "history", "factions", "characters", "cultures", "story"):
        pass
    char_data = data.get("characters") or {}
    # 注入运行时状态摘要
    runtime_states = get_character_runtime_states(world)
    if runtime_states:
        char_data = dict(char_data)
        char_data["_runtime_states"] = runtime_states
    slim = {
        "meta": data.get("meta"),
        "characters": char_data,
        "history": data.get("history"),
        "factions": {
            "summary": (data.get("factions") or {}).get("summary"),
            "entities": [
                {
                    "id": e.get("id"),
                    "name": e.get("name"),
                    "goals": (e.get("goals") or "")[:200],
                }
                for e in ((data.get("factions") or {}).get("entities") or [])[:24]
                if isinstance(e, dict)
            ],
        },
        "geography": {
            "summary": (data.get("geography") or {}).get("summary"),
            "regions": [
                {"id": r.get("id"), "name": r.get("name")}
                for r in ((data.get("geography") or {}).get("regions") or [])[:32]
                if isinstance(r, dict)
            ],
        },
    }
    base = json.dumps(slim, ensure_ascii=False, indent=2)
    if include_markdown:
        from worldforger.world_store import load_world_markdown_optional

        md = load_world_markdown_optional(world.meta.id)
        if md:
            cap = md[:12000] + ("\n…(world.md 已截断)" if len(md) > 12000 else "")
            return base + "\n\n--- world.md (截断) ---\n\n" + cap
    return base


# ── 章节摘要卡片 prompt ──────────────────────────────────────


def chapter_summary_system(world: World) -> str:
    unit = resolve_unit_label(world)
    return (
        f"你是叙事分析助手，负责为已完成的{unit}撰写**摘要卡片**。\n"
        "你只需要输出 JSON，不要输出任何其他文字。\n"
        "JSON 格式：\n"
        "{\n"
        '  "main_events": "本章主要事件概述（150-250 字）",\n'
        '  "character_state_changes": [\n'
        '    {"char_id": "角色id", "name": "角色名",\n'
        '     "location_before": "之前在哪", "location_after": "现在在哪",\n'
        '     "emotion_before": "之前情绪", "emotion_after": "现在情绪",\n'
        '     "new_items": "新获得的物品/能力（空则写无）",\n'
        '     "goal_change": "目标变化描述（空则写无变化）"}\n'
        "  ],\n"
        '  "foreshadowing_planted": ["本章新埋设的伏笔 id 列表"],\n'
        '  "foreshadowing_resolved": ["本章回收的伏笔 id 列表"],\n'
        '  "ending_hook": "结尾钩子（本章结束时未解决的悬念，30-80 字）"\n'
        "}\n"
        "注意：\n"
        "- character_state_changes 仅列出本章中状态发生变化的角色，未出场或状态无变化的角色不列出。\n"
        "- foreshadowing_planted/resolved 中填伏笔的 id（如 fs_xxx），无则写空数组。\n"
    )


def build_chapter_summary_user_payload(
    world: World,
    *,
    chapter_id: str,
    manuscript_text: str,
) -> str:
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    unit = resolve_unit_label(world)
    parts = [
        f"为以下{unit}正文撰写摘要卡片：",
        f"\n【{unit}信息】id={chapter_id}，标题={ch.title if ch else ''}",
        f"\n【出场人物参考】",
    ]
    for ent in world.characters.entities[:20]:
        if isinstance(ent, dict):
            parts.append(
                f"- id={ent.get('id','')} name={ent.get('name','')} "
                f"cast_role={ent.get('cast_role','')}"
                f"{' runtime_state=' + str(ent.get('runtime_state','')) if ent.get('runtime_state') else ''}"
            )
    from worldforger.foreshadow_apply import foreshadow_ledger_text

    parts.append(f"\n【伏笔台账】\n{foreshadow_ledger_text(world, chapter_id=chapter_id)}")
    body = manuscript_text.strip()
    if len(body) > 16000:
        body = body[:16000] + "\n…(文稿已截断)"
    parts.append(f"\n【{unit}正文（截断）】\n{body}")
    return "\n".join(parts)


# ── 角色运行时状态提取 prompt ─────────────────────────────────


def character_state_extract_system() -> str:
    return (
        "你是叙事分析助手，负责从章节目录正文中提取各角色的**运行时状态变化**。\n"
        "你只需要输出 JSON，不要输出任何其他文字。\n"
        'JSON 格式：{"char_id": {"current_location": "...", "current_goal": "...", '
        '"emotional_state": "...", "inventory_changes": ["..."], '
        '"relationship_updates": {"other_char_id": "变化描述"}}}\n'
        "注意：\n"
        "- 仅列出本章中状态发生了变化的角色。未出场或状态无变化的角色不要列出。\n"
        "- current_location：角色本章结尾时的所在地点。\n"
        "- current_goal：角色当前的主要目标。\n"
        "- emotional_state：角色本章结尾时的情绪状态。\n"
        "- inventory_changes：本章中新获得/失去的重要物品或能力。\n"
        "- relationship_updates：与其他角色的关系变化，key 为对方 char_id。\n"
    )


def build_character_state_user_payload(
    world: World,
    *,
    manuscript_text: str,
) -> str:
    parts = ["从以下正文中提取各角色的运行时状态变化：\n"]
    for ent in world.characters.entities[:30]:
        if isinstance(ent, dict):
            parts.append(
                f"- id={ent.get('id','')} name={ent.get('name','')} "
                f"cast_role={ent.get('cast_role','')}"
            )
    body = manuscript_text.strip()
    if len(body) > 16000:
        body = body[:16000] + "\n…(文稿已截断)"
    parts.append(f"\n【正文（截断）】\n{body}")
    return "\n".join(parts)


# ────────────────────────────────────────────────────────────


def format_rag_chunks(chunks: list[dict]) -> str:
    """将 RAG 检索到的 chunk 格式化为 prompt 片段。"""
    if not chunks:
        return ""
    lines = []
    for i, c in enumerate(chunks, 1):
        meta = c.get("metadata", {})
        source_type = meta.get("source_type", "manuscript")
        if source_type == "manuscript":
            label = f"来源：第 {meta.get('chapter_order', '?')} 章「{meta.get('chapter_title', '')}」"
        elif source_type == "character":
            label = f"来源：人物卡「{meta.get('character_name', '')}」"
        elif source_type == "world_md":
            label = f"来源：世界观设定「{meta.get('section', '')}」"
        else:
            label = f"来源：{source_type}"
        doc = c.get("document", "")
        if len(doc) > 800:
            doc = doc[:800] + "\n…(片段已截断)"
        lines.append(f"[片段 {i} — {label}]\n{doc}")
    return "\n\n".join(lines)


def format_runtime_states(world: World, chapter_id: str = "") -> str:
    """格式化角色运行时状态为 prompt 片段。"""
    from worldforger.story_store import get_character_runtime_states

    states = get_character_runtime_states(world)
    if not states:
        return ""
    lines = ["【人物当前状态（运行时追踪）】"]
    for s in states:
        rs = s.get("runtime_state", {})
        if not isinstance(rs, dict):
            continue
        loc = rs.get("current_location", "?")
        goal = rs.get("current_goal", "?")
        emo = rs.get("emotional_state", "?")
        lines.append(f"- {s.get('name', '?')}({s.get('id', '')})：位置={loc}，目标={goal}，情绪={emo}")
    return "\n".join(lines)


def build_book_summary(world: World) -> str:
    """构建 Book 层全局叙事摘要。"""
    from worldforger.story_store import get_character_runtime_states, sorted_chapters

    parts = []
    parts.append(f"【全局叙事摘要】世界「{world.meta.name}」")
    parts.append(f"创作模式：{world.meta.creative_mode or 'novel'}，体裁标签：{', '.join(world.meta.genre_tags or [])}")

    # 章节概览
    chapters = sorted_chapters(world)
    done = [c for c in chapters if c.status != "planned"]
    if done:
        parts.append(f"已完成 {len(done)}/{len(chapters)} 个章节：")
        for c in done[-5:]:
            card = c.summary_card
            hook = f" → 钩子：{card.ending_hook}" if card and card.ending_hook else ""
            parts.append(f"  - 第{c.order}章「{c.title}」(id={c.id}, {c.word_count}字){hook}")
    else:
        parts.append(f"共 {len(chapters)} 个章节待撰写。")

    # 伏笔全景
    open_fs = [f for f in world.story.foreshadowing if f.status != "resolved"]
    if open_fs:
        parts.append(f"未回收伏笔 {len(open_fs)} 条：")
        for f in open_fs[:12]:
            parts.append(f"  - {f.id}：{f.label}（植于 {f.planted_chapter_id}）")
    resolved = [f for f in world.story.foreshadowing if f.status == "resolved"]
    if resolved:
        parts.append(f"已回收伏笔 {len(resolved)} 条。")

    # 角色长期弧线（从 runtime_state 推断）
    states = get_character_runtime_states(world)
    major_chars = [s for s in states if s.get("runtime_state", {}).get("last_updated_chapter")]
    if major_chars:
        parts.append("主要角色当前状态：")
        for s in major_chars[:8]:
            rs = s.get("runtime_state", {})
            parts.append(
                f"  - {s.get('name', '?')}：{rs.get('current_location', '?')}，"
                f"情绪 {rs.get('emotional_state', '?')}，目标 {rs.get('current_goal', '?')}"
            )

    return "\n".join(parts)


def build_manuscript_user_payload(
    world: World,
    *,
    chapter_id: str,
    macro_outline: str,
    beat_text: str,
    prev_manuscripts: list[tuple[str, str]],
    user_hint: str,
    include_world_md: bool,
    rag_chunks: list[dict] | None = None,
) -> str:
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    title = ch.title if ch else chapter_id
    unit = resolve_unit_label(world)
    parts = [
        f"【任务】撰写「{unit}」文稿：{title}（id={chapter_id}）",
        f"\n【世界设定摘要】\n{compact_world_snippet(world, include_markdown=include_world_md)}",
    ]
    if macro_outline.strip():
        cap = macro_outline.strip()
        if len(cap) > 14000:
            cap = cap[:14000] + "\n…(粗纲已截断)"
        parts.append(f"\n【粗纲】\n{cap}")
    if beat_text.strip():
        parts.append(f"\n【本章细纲】\n{beat_text.strip()}")

    # ── 三层记忆：Immediate → Chapter → Book ──
    # Immediate 层：RAG 检索到的语义相关前文片段 + 人物运行时状态
    immediate_parts = []
    if rag_chunks:
        rag_text = format_rag_chunks(rag_chunks)
        if rag_text:
            immediate_parts.append(f"【语义检索到的前情相关片段（请参考以保持叙事一致性）】\n{rag_text}")
    runtime_text = format_runtime_states(world, chapter_id)
    if runtime_text:
        immediate_parts.append(runtime_text)
    if immediate_parts:
        parts.append("\n" + "\n\n".join(immediate_parts))

    # Chapter 层：前章摘要卡片 + fallback 原文截断
    if prev_manuscripts:
        parts.append("\n【前文摘要（保持衔接）】")
        from worldforger.story_store import summaries_before

        summary_cards = summaries_before(world.meta.id, chapter_id, len(prev_manuscripts), world)
        has_summaries = len(summary_cards) >= len(prev_manuscripts) * 0.5

        if has_summaries and summary_cards:
            for card in summary_cards:
                cid = card.get("chapter_id", "")
                ctitle = card.get("title", "")
                main = card.get("main_events", "")
                hook = card.get("ending_hook", "")
                changes = card.get("character_state_changes", [])
                parts.append(f"\n### {ctitle} ({cid})\n**事件**：{main}")
                if changes:
                    chg_lines = []
                    for sc in changes:
                        chg_lines.append(
                            f"- {sc.get('name','?')}：{sc.get('location_before','?')}→{sc.get('location_after','?')}，"
                            f"情绪 {sc.get('emotion_before','?')}→{sc.get('emotion_after','?')}"
                        )
                    parts.append(f"**状态变化**：\n" + "\n".join(chg_lines))
                if hook:
                    parts.append(f"**结尾钩子**：{hook}")
        else:
            # 退回到原文截断
            for cid, text in prev_manuscripts:
                cht = next((c for c in world.story.chapters if c.id == cid), None)
                lab = cht.title if cht else cid
                body = text.strip()
                if len(body) > 6000:
                    body = body[:6000] + "\n…(该章文稿已截断)"
                parts.append(f"\n### {lab} ({cid})\n{body}")

    # Book 层：全局叙事摘要
    book_summary = build_book_summary(world)
    if book_summary.strip():
        parts.append(f"\n{book_summary}")

    if user_hint.strip():
        parts.append(f"\n【用户补充要求】\n{user_hint.strip()}")
    from worldforger.foreshadow_apply import foreshadow_ledger_text

    parts.append(
        f"\n【伏笔台账（正文勿提前揭穿未回收项）】\n"
        f"{foreshadow_ledger_text(world, chapter_id=chapter_id)}"
    )
    return "\n".join(parts)


def chapter_list_for_prompt(world: World) -> str:
    lines = []
    unit = resolve_unit_label(world)
    for ch in sorted_chapters(world):
        lines.append(f"- {ch.order}. {ch.title or ch.id} (id={ch.id}, status={ch.status})")
    return f"已有{unit}列表：\n" + ("\n".join(lines) if lines else "（尚无）")


STORY_CHAT_SCHEMA_HINT = """【与 world.json 的 story 对齐】
- **story.summary** / **story.design_notes**：情节项目总览与结构设计说明。
- **story.chapters[]**：每项 **id**（建议 ch_ 前缀 slug）、**order**、**title**、**status**（planned|drafting|locked）、可选 **reader_synopsis**、**author_notes**。
- **story.foreshadowing[]**：**id**、**label**、**planted_chapter_id** / **payoff_chapter_id**（须为 chapters[].id）、**status**（open|partial|resolved）、**reader_known**、**notes**。
- **story.narrator**：**character_id**（对齐 characters.entities[].id）、**person**（first_person|third_person_limited|third_person_omniscient）、**voice_notes**。
- 粗纲/细纲/正文在磁盘 `story/macro_outline.md`、`story/beats/<id>.md`、`story/manuscript/<id>.md`；长 Markdown 请用代码块输出（见下），勿塞进 JSON 字符串字段。"""

STORY_CHAT_MARKDOWN_HINT = """【长文 Markdown 输出约定（供用户一键写入文件）】
当需要给出可落盘的粗纲、细纲或文稿时，在回复中使用**独立** fenced 代码块，语言标签必须为：
- ```story-macro` … ` 全书粗纲
- ```story-beat:<chapter_id>` … ` 某章细纲（id 须与 chapters 一致）
- ```story-manuscript:<chapter_id>` … ` 某章文稿
可同时给出多个块。叙述性说明写在代码块外。"""

STORY_CHAT_FORESHADOW_HINT = """【伏笔 JSON 块（可选，与 apply_foreshadowing 工具等效）】
```story-foreshadow
[
  {"op": "upsert", "id": "fs_xxx", "label": "…", "planted_chapter_id": "ch_…", "status": "open"},
  {"op": "resolve", "id": "fs_yyy", "payoff_chapter_id": "ch_…"}
]
```
系统会自动合并进 story.foreshadowing。"""


def story_chat_system_prompt(
    world: World,
    *,
    active_chapter_id: str = "",
    include_story_files: bool = False,
) -> str:
    from worldforger.story_store import macro_outline_path, read_text

    unit = resolve_unit_label(world)
    st = world.story
    ctx = {
        "story": st.model_dump(mode="json"),
        "characters_summary": (world.characters.summary or "")[:800],
        "open_foreshadowing": [
            {
                "id": f.id,
                "label": f.label,
                "planted_chapter_id": f.planted_chapter_id,
                "payoff_chapter_id": f.payoff_chapter_id,
                "status": f.status,
            }
            for f in st.foreshadowing
            if f.status != "resolved"
        ][:24],
    }
    parts = [
        "你是「情节与叙事」策划助手，帮助用户基于**已有**世界设定与卡司，规划粗纲、细纲、章节节奏、伏笔与正文风格。",
        "回答使用简体中文，结构清晰；需要列表时使用 Markdown。",
        "不要编造与 JSON 冲突的派系/区域/人物 id；新章节请给出稳定 **ch_** 前缀 id。",
        f"\n当前情节单元：「{unit}」。",
        chapter_list_for_prompt(world),
        f"\n```json\n{json.dumps(ctx, ensure_ascii=False, indent=2)}\n```",
        STORY_CHAT_SCHEMA_HINT,
        STORY_CHAT_MARKDOWN_HINT,
        STORY_CHAT_FORESHADOW_HINT,
    ]
    cid = (active_chapter_id or "").strip()
    if cid:
        parts.append(f"\n【用户当前选中章节】id={cid}")
    if include_story_files:
        wid = world.meta.id
        macro = read_text(macro_outline_path(wid))
        if macro.strip():
            cap = macro.strip()
            if len(cap) > 8000:
                cap = cap[:8000] + "\n…(粗纲已截断)"
            parts.append(f"\n【磁盘粗纲 macro_outline.md（截断）】\n{cap}")
        if cid:
            from worldforger.story_store import beat_path, manuscript_path

            beat = read_text(beat_path(wid, cid))
            if beat.strip():
                parts.append(f"\n【本章细纲 beats/{cid}.md】\n{beat.strip()[:6000]}")
            ms = read_text(manuscript_path(wid, cid))
            if ms.strip():
                parts.append(f"\n【本章文稿 manuscript/{cid}.md（截断）】\n{ms.strip()[:4000]}")
    parts.append(
        f"\n【世界设定摘要】\n{compact_world_snippet(world, include_markdown=False)}"
    )
    return "\n".join(parts)
