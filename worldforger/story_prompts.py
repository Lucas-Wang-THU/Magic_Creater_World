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


def _pov_anti_examples(person: StoryPerson) -> str:
    """按叙事人称生成反面示例，防止人称漂移。"""
    if person == "first_person":
        return (
            "【叙事人称硬约束 — 反面示例】\n"
            "本章使用第一人称，叙述者 = 已绑定的 POV 角色。\n"
            "❌ 禁止以其他角色的视角叙述内心活动。\n"
            "❌ 禁止出现「他心想」「她暗自思忖」等跳出第一人称的写法。\n"
            "✅ 只能写「我」所看、所感、所想。"
        )
    elif person == "third_person_limited":
        return (
            "【叙事人称硬约束 — 反面示例】\n"
            "❌ 「我站在城墙上，望着远方的烽火。」（禁止第一人称叙述）\n"
            "❌ 「我们一行人穿过密林，李明和我走在最前面。」（禁止第一人称复数）\n"
            "❌ 「李明心想：这家伙肯定在撒谎。」同时写「王五心想：他果然上当了。」（限知视角只能贴近一个 POV 角色的内心）\n"
            "✅ 「李明站在城墙上，望着远方的烽火。」（第三人称）\n"
            "✅ 「三人穿过密林，李明走在最前面。」（第三人称）\n"
            "✅ 仅描写 POV 角色能感知到的信息；其他角色的内心活动不可直接描写。"
        )
    else:
        return (
            "【叙事人称硬约束 — 反面示例】\n"
            "❌ 「我站在城墙上，望着远方的烽火。」（禁止第一人称叙述）\n"
            "❌ 「我们一行人穿过密林。」（禁止第一人称复数）\n"
            "✅ 「李明站在城墙上，望着远方的烽火。」（第三人称）\n"
            "✅ 全知视角可描写各角色内心活动，但勿无节制剧透未回收伏笔。"
        )


def _character_reference_rules() -> str:
    """人物指称规则：用人名而非过度依赖代词。"""
    return (
        "【人物指称规则】\n"
        "1. 每段首次提及某角色，必须用完整人名，禁止以「他」「她」开头。\n"
        "2. 同段落多个同性别角色互动时，每个动作/对话的主体必须用人名标清，禁止连续使用「他」「她」造成指代不明。\n"
        "3. 心理描写开头必须用「人名 + 心想/暗想/思忖」，不可仅用「他」「她」。\n"
        "4. 场景切换或视角转换后第一句话，必须用人名重新锚定。\n"
        "5. 「他」「她」仅限前一句已用人名明确指代且当前句无其他同性别角色时使用；每 3–4 句至少重新出现一次人名。"
    )


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
    elif person != "first_person":
        lines.append("口吻与禁忌：全文使用第三人称，优先用人名称呼角色而非过度依赖「他」「她」，每段首次出现和场景切换时必须用人名锚定。")
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
    person_eff = person or world.story.narrator.person
    return (
        "你是小说/跑团执笔者，根据世界设定、粗纲与细纲撰写**章节文稿**。\n"
        f"当前单元：{unit}。\n"
        f"{narrator_block(world, person_override=person)}\n\n"
        f"{_pov_anti_examples(person_eff)}\n\n"
        f"{_character_reference_rules()}\n"
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


# ── Layer 3: Narrative KG extraction prompt ─────────────────────


def kg_extraction_system() -> str:
    return (
        "你是叙事知识图谱提取器，负责从章节正文中提取角色状态变化、关键事件和物品流转。\n"
        "你只需要输出 JSON，不要输出任何其他文字。\n"
        "JSON 格式：\n"
        "{\n"
        '  "entities": [\n'
        '    {"entity_id": "char_xxx", "entity_type": "character",\n'
        '     "name": "角色名",\n'
        '     "states": [{"chapter_id": "本章id", "location": "结尾位置", '
        '"emotion": "情绪", "goal": "当前目标"}]},\n'
        '    {"entity_id": "item_xxx", "entity_type": "item", "name": "物品名",\n'
        '     "item_status": "active|lost|destroyed", "possessed_by": "char_xxx",\n'
        '     "last_seen_chapter": "本章id"}\n'
        "  ],\n"
        '  "events": [\n'
        '    {"event_id": "evt_xxx", "chapter_id": "本章id",\n'
        '     "event_type": "revelation|battle|death|betrayal|alliance|discovery|other",\n'
        '     "summary": "事件简述（50-100字）",\n'
        '     "participants": ["char_xxx"], "location": "地点",\n'
        '     "consequences": ["后果1", "后果2"]}\n'
        "  ],\n"
        '  "foreshadowing_planted": ["本章新埋的伏笔id"],\n'
        '  "foreshadowing_resolved": ["本章回收的伏笔id"]\n'
        "}\n"
        "注意：\n"
        "- entities 仅列出本章中状态/归属有变化的角色或物品。状态无变化的不要列出。\n"
        "- events 仅列出本章中的关键叙事事件（通常 1-5 个），日常琐事不要列出。\n"
        "- event_id 建议使用 evt_ 前缀加序号。\n"
    )


def build_kg_extraction_user_payload(
    world: World,
    *,
    chapter_id: str,
    manuscript_text: str,
) -> str:
    parts = [
        f"从以下章节正文中提取角色状态变化、关键事件和物品流转：\n",
        f"【本章信息】id={chapter_id}\n",
        "【角色列表】",
    ]
    for ent in world.characters.entities[:20]:
        if isinstance(ent, dict):
            rs = ent.get("runtime_state", {})
            parts.append(
                f"- id={ent.get('id','')} name={ent.get('name','')} "
                f"cast_role={ent.get('cast_role','')}"
                f"{' 上章=' + str(rs.get('last_updated_chapter','')) if rs else ''}"
            )
    # Current KG state for deduplication
    kg = world.story.narrative_kg
    if kg.entities or kg.events:
        existing_events = [e.event_id for e in kg.events[-10:]]
        existing_entities = [e.entity_id for e in kg.entities]
        parts.append(
            f"\n【已有 KG 状态（避免重复）】\n"
            f"已有实体 ids: {existing_entities}\n"
            f"最近事件 ids: {existing_events}"
        )
    body = manuscript_text.strip()
    if len(body) > 12000:
        body = body[:12000] + "\n…(文稿已截断)"
    parts.append(f"\n【正文（截断）】\n{body}")
    return "\n".join(parts)


# ── Layer 3: Consistency check prompt ────────────────────────────


def consistency_check_system() -> str:
    return (
        "你是叙事一致性审校 Agent，负责检查章节文稿的 7 个一致性维度。\n"
        "你只需要输出 JSON，不要输出任何其他文字。\n"
        "JSON 格式：\n"
        "{\n"
        '  "verdict": "clean|minor_issues|needs_review",\n'
        '  "issues": [\n'
        '    {"category": "position|personality|item_state|pov|foreshadowing|emotional_continuity|timeline",\n'
        '     "severity": "critical|warning|info",\n'
        '     "description": "问题描述（具体说明不一致之处）",\n'
        '     "excerpt": "相关原文摘录（可选）",\n'
        '     "suggestion": "修改建议（可选）"}\n'
        "  ]\n"
        "}\n"
        "检查清单：\n"
        "1. 人物位置一致性：各角色位置与上一章结尾是否一致？如有跳跃是否有合理解释？\n"
        "2. 人物性格一致性：言行是否符合 characters 设定？是否有 OOC 行为？\n"
        "3. 物品状态一致性：重要物品出现/消失/使用是否有合理解释？\n"
        "4. 叙事视角一致性：是否遵守设定的 POV 和人称？多 POV 切换是否明确？\n"
        "5. 伏笔一致性：是否错误提前揭示未回收伏笔？新伏笔是否合理？\n"
        "6. 情感连续性：情感基调是否与上一章结尾合理衔接？\n"
        "7. 时间线一致性：事件时间顺序是否与已有章节冲突？\n"
        "注意：\n"
        "- 无问题则 issues 为空数组，verdict 为 clean。\n"
        "- 仅报告明确的不一致，不确定的不要列为问题。\n"
        "- severity: critical=严重破坏前后连贯, warning=可能不一致, info=轻微瑕疵。\n"
    )


def build_consistency_check_user_payload(
    world: World,
    *,
    chapter_id: str,
    manuscript_text: str,
) -> str:
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    unit = resolve_unit_label(world)
    parts = [
        f"对以下{unit}文稿进行 7 维度一致性检查：",
        f"\n【{unit}信息】id={chapter_id}，标题={ch.title if ch else ''}",
        f"\n【叙事设置】\n{narrator_block(world)}",
    ]
    # Character profiles
    parts.append("\n【角色设定】")
    for ent in world.characters.entities[:15]:
        if isinstance(ent, dict):
            rs = ent.get("runtime_state", {})
            parts.append(
                f"- {ent.get('name','')} (id={ent.get('id','')}) "
                f"角色={ent.get('cast_role','')} "
                f"当前位置={rs.get('current_location','?')} "
                f"情绪={rs.get('emotional_state','?')}"
            )
    # Previous chapter summary
    from worldforger.story_store import summaries_before

    prev_cards = summaries_before(world.meta.id, chapter_id, 1, world)
    if prev_cards:
        card = prev_cards[0]
        parts.append(
            f"\n【上一章摘要】\n"
            f"事件：{card.get('main_events','')}\n"
            f"结尾钩子：{card.get('ending_hook','')}"
        )
    # Foreshadowing ledger
    from worldforger.foreshadow_apply import foreshadow_ledger_text

    parts.append(f"\n【伏笔台账】\n{foreshadow_ledger_text(world, chapter_id=chapter_id)}")
    # Previous sentiment for emotional continuity check
    prev_ch = next((c for c in sorted(world.story.chapters, key=lambda x: x.order) if c.order < (ch.order if ch else 999)), None)
    if prev_ch and prev_ch.sentiment_log:
        parts.append(f"\n【上一章结尾情感基调】{prev_ch.sentiment_log.ending_tone}")
    body = manuscript_text.strip()
    if len(body) > 10000:
        body = body[:10000] + "\n…(文稿已截断)"
    parts.append(f"\n【{unit}正文（截断）】\n{body}")
    return "\n".join(parts)


# ── Layer 3: Sentiment analysis prompt ───────────────────────────


def sentiment_analysis_system() -> str:
    return (
        "你是情感弧线分析器，负责将章节正文分为若干段落并标注情感倾向。\n"
        "你只需要输出 JSON，不要输出任何其他文字。\n"
        "JSON 格式：\n"
        "{\n"
        '  "segments": [\n'
        '    {"segment_index": 1, "label": "开篇|中段|高潮|尾声",\n'
        '     "tone": "positive|negative|tense|calm|mixed",\n'
        '     "intensity": 5, "summary": "本段氛围简述（20-40字）"}\n'
        "  ],\n"
        '  "overall_tone": "本章主导情感倾向",\n'
        '  "ending_tone": "结尾段情感倾向（用于下章过渡）",\n'
        '  "transition_from_prev": "smooth|abrupt|intentional_contrast|first_chapter"\n'
        "}\n"
        "注意：\n"
        "- 通常分为 3-6 个段落。不要分得过细（每段至少 300 字）。\n"
        "- intensity 1-10：1=非常平淡，10=极度强烈。\n"
        "- transition_from_prev：与上一章结尾的情感对比。首章填 first_chapter。\n"
    )


def build_sentiment_analysis_user_payload(
    world: World,
    *,
    chapter_id: str,
    manuscript_text: str,
) -> str:
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    parts = [
        f"对以下章节正文进行情感弧线分析：",
        f"章节：{ch.title if ch else chapter_id} (id={chapter_id})",
    ]
    # Previous chapter sentiment for transition analysis
    prev_ch = next(
        (c for c in sorted(world.story.chapters, key=lambda x: x.order)
         if c.id != chapter_id and c.order < (ch.order if ch else 999)),
        None
    )
    if prev_ch and prev_ch.sentiment_log:
        parts.append(f"上一章结尾情感：{prev_ch.sentiment_log.ending_tone}")
    else:
        parts.append("上一章结尾情感：（无，这是首章）")
    body = manuscript_text.strip()
    if len(body) > 10000:
        body = body[:10000] + "\n…(文稿已截断)"
    parts.append(f"\n【正文（截断）】\n{body}")
    return "\n".join(parts)


# ── Layer 3: Prompt injection helpers ────────────────────────────


def format_kg_states_for_prompt(world: World, chapter_id: str = "") -> str:
    """Format Narrative KG character states for manuscript prompt injection."""
    kg = world.story.narrative_kg
    if not kg.entities:
        return ""
    char_entities = [e for e in kg.entities if e.entity_type == "character" and e.states]
    if not char_entities:
        return ""
    lines = ["【知识图谱 — 角色当前状态（跨章节追踪）】"]
    for ent in char_entities:
        latest = ent.states[-1] if ent.states else None
        if not latest:
            continue
        lines.append(
            f"- {ent.name}({ent.entity_id})：位于 {latest.location}，"
            f"情绪 {latest.emotion}，目标 {latest.goal}"
        )
    recent_events = kg.events[-5:]
    if recent_events:
        lines.append("\n最近关键事件：")
        for evt in recent_events:
            lines.append(f"  - [{evt.chapter_id}] {evt.event_type}: {evt.summary[:80]}")
    return "\n".join(lines)


def format_previous_sentiment_for_prompt(world: World, chapter_id: str) -> str:
    """Format previous chapter ending sentiment for manuscript prompt injection."""
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    if not ch:
        return ""
    prev_ch = next(
        (c for c in sorted(world.story.chapters, key=lambda x: x.order)
         if c.order < ch.order and c.sentiment_log),
        None
    )
    if not prev_ch or not prev_ch.sentiment_log:
        return ""
    sl = prev_ch.sentiment_log
    return (
        f"【上一章结尾情感基调】{sl.ending_tone}（强度 {sl.segments[-1].intensity if sl.segments else '?'}/10）\n"
        f"过渡评价：{sl.transition_from_prev}\n"
        "→ 本章开篇应注意情感过渡，避免突兀的基调切换（除非有意为之）。"
    )


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
    person: StoryPerson | None = None,
) -> str:
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    title = ch.title if ch else chapter_id
    unit = resolve_unit_label(world)
    person_eff = person or world.story.narrator.person
    pov_label = person_instruction(person_eff)
    parts = [
        f"【任务】撰写「{unit}」文稿：{title}（id={chapter_id}）",
    ]
    # ── POV 硬约束（user prompt 首部，利用注意力峰区）──
    parts.append(
        f"\n【叙事人称硬约束 — 本章写作开始前务必确认】\n"
        f"本章叙事人称：{pov_label}\n"
        + (
            "严禁出现任何第一人称叙述（「我」「我们」作为叙述主体）。\n"
            "角色对话中角色说「我」是允许的，但叙述者绝不能以「我」自称。\n"
            if person_eff != "first_person" else ""
        )
        + "如果写到一半发现人称错误，请立即回头修改。"
    )
    parts.append(f"\n【世界设定摘要】\n{compact_world_snippet(world, include_markdown=include_world_md)}")
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
    # Layer 3: KG states injection
    kg_text = format_kg_states_for_prompt(world, chapter_id)
    if kg_text:
        immediate_parts.append(kg_text)
    # Layer 3: Previous sentiment injection
    prev_sent_text = format_previous_sentiment_for_prompt(world, chapter_id)
    if prev_sent_text:
        immediate_parts.append(prev_sent_text)
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
    # ── 尾部署名提醒（近因效应：最后一行紧邻模型输出的位置）──
    parts.append(
        f"\n（开始写作前再次确认：本章使用{pov_label}，优先用人名称呼角色，不依赖「他」「她」。请开始正文。）"
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


# ═══════════════════════════════════════════════════════════════════
# Layer 4: 润色者 Agent — 文风统一与去 AI 化
# ═══════════════════════════════════════════════════════════════════


def polisher_system() -> str:
    return (
        "你是「文字抛光学徒」——只抛光、不重写、不改变情节。\n"
        "你的工具是：换词、调句序、补感官、断长句、加一个身体反应、合并碎片段落。\n"
        "你不能做的是：增删情节、改变对话含义、添加新事件、修改角色行为。\n\n"
        "【硬规则 — 必须逐条执行】\n"
        "1. 破题多样化：每段开头不得与上一段开头使用相同句式结构；"
        "禁止「于是/因此/就这样/紧接着」连用两段。\n"
        "2. 去金句化：删除或重写所有模板化「总结金句」，用具体的、细微的描写替代概括性评价。"
        "信任读者的理解力。\n"
        "3. 情绪具象化（Show, don't tell）：将「他感到X」替换为身体反应+环境暗示+动作细节。"
        "如「他很紧张」→「他的手指在桌沿上反复摩挲，指节泛白」。\n"
        "4. 对话自然化：为至少 30% 的对话添加真实对话特征——打断、犹豫词（「呃」「嗯」「那个…」）、"
        "话说一半、答非所问、沉默描写。\n"
        "5. 感官补充：每 500 字至少出现一处非视觉感官（声音的方向/远近、气味的来源/浓淡、"
        "温度的冷暖/变化、触感的粗糙/光滑/潮湿、身体的疲惫/疼痛/眩晕）。\n"
        "6. 句式破形：连续 3 句以上使用相同的「主语+谓语+宾语」结构时，必须打破——"
        "长句后接短句（3-5 字），陈述句后接反问或内心疑问，平铺直叙后接比喻或通感。\n"
        "7. 文风锚定：参考已润色的前章，保持叙事语气、用词偏好、节奏感一致。"
        "角色习惯使用的口头禅/句式不在此列（那是人物特征，应保留）。\n"
        "8. 破折号节制：统计全文破折号（—）密度，超过每 1000 字 2 处时，"
        "将多余的破折号改为逗号、句号或通过句式重构消除。保留的破折号只能是："
        "真正的插入语补充、说话被打断、语义转折。禁止用破折号替代逗号制造「呼吸感」。\n"
        "9. 段落合并：扫描全文，将相邻的内容相关的 1-2 句孤立短段合并为完整段落。"
        "合并标准：(a)同场景同角色 (b)描写同一动作/同一环境 (c)因果关系紧密。"
        "合并后每段应有 3-8 句，信息密度饱满。转场/时间跳跃/视角切换自然产生的新段落保留。\n\n"
        "【禁止事项 — 违反即失败】\n"
        "- 禁止新增情节事件\n"
        "- 禁止删除或改变对话的语义内容（可以调整措辞和节奏）\n"
        "- 禁止改变角色行动的结果\n"
        "- 禁止添加原文没有的设定信息\n"
        "- 禁止改动叙事人称（POV）\n"
        "- 禁止修改专有名词（地名、人名的写法）\n"
        "- 原文字数 X，润色后字数必须在 0.9X 到 1.1X 之间\n\n"
        "【反面示例对照 — 请将 ❌ 改写为 ✅ 的风格】\n"
        '❌ 「于是，他转身离开了那座城市。就这样，三年的等待画上了句号。」\n'
        '✅ 「他转身。城门在身后闷响一声合拢。三年，就这样了。」\n'
        '❌ 「他感到非常愤怒，心中充满了复仇的欲望。」\n'
        '✅ 「后槽牙咬得太紧，太阳穴突突地跳。视野边缘有些发红。」\n'
        '❌ 「"你说得对。"他说。"我知道。"她回答。」\n'
        '✅ 「"你说得对。"他顿了顿，把茶杯转了一圈。"不过——""不过什么？""…算了。"」\n'
        '❌ 破折号滥用：「他站起身——走到窗边——拉开窗帘——外面在下雨——他想起了那个下午。」\n'
        '✅ 「他站起身，走到窗边拉开窗帘。外面在下雨。那个下午突然涌上心头。」\n'
        '❌ 小段落碎片化（三段连续短段）：\n'
        '「他推开门。」\n「房间里空无一人。」\n「桌上放着一封信。」\n'
        '✅ 「他推开门，房间里空无一人。桌上放着一封信，信封上没有任何字迹，'
        '但封蜡的印章让他呼吸骤停——那是十年前父亲失踪前用的图案。」\n\n'
        "【输出格式】\n"
        "返回完整润色后文稿（Markdown），在文末用「## 润色说明」列出每处改动及理由，格式：\n"
        "- 第X段第Y句：「原文」→「润色后」— 理由（如「补充听觉感官」「打破连续三句SVO结构」「合并碎片短段」「移除冗余破折号」）\n"
    )


def build_polisher_user_payload(
    world: World,
    chapter_id: str,
    manuscript_text: str,
    *,
    consistency_issues: str = "",
    polish_round: int = 1,
    regression_issues: str = "",
) -> str:
    """Assemble the user payload for the polisher LLM call."""
    from worldforger.story_store import polished_path, read_text

    st = world.story
    ch = next((c for c in st.chapters if c.id == chapter_id), None)
    chapter_title = ch.title if ch else chapter_id

    parts = [f"【润色任务】请对以下章节进行文风润色与去 AI 化抛光（第 {polish_round} 轮）。"]

    # 1. 叙事人称约束
    narrator = narrator_block(world)
    if narrator.strip():
        parts.append(f"\n【叙事约束 — 请严格遵守】\n{narrator.strip()}")

    # 2. 角色语言风格档案
    char_voices = _build_char_voice_profile(world)
    if char_voices.strip():
        parts.append(f"\n【角色语言风格档案 — 对话润色参考】\n{char_voices.strip()}")

    # 3. 前章润色稿参考（文风锚定）
    style_refs = _build_style_reference(world, chapter_id)
    if style_refs:
        parts.append("\n【文风参考 — 已润色前章】")
        parts.extend(style_refs)

    # 4. 一致性审校报告（需要修复的问题）
    if consistency_issues.strip():
        parts.append(f"\n【需要修复的叙事问题 — 请在润色时修正】\n{consistency_issues.strip()}")
        if regression_issues.strip():
            parts.append(
                f"\n【⚠️ 回归问题（上一轮润色引入的新 bug，最高优先级修复）】\n{regression_issues.strip()}"
            )

    # 5. 本章原稿
    parts.append(f"\n【本章原稿 — {chapter_title}】\n{manuscript_text.strip()}")

    return "\n".join(parts)


def _build_char_voice_profile(world: World) -> str:
    """Extract character voice profiles for dialogue polishing reference."""
    chars = world.characters.entities if world.characters and world.characters.entities else []
    if not chars:
        return ""
    lines = []
    for c in chars[:8]:  # limit to 8 main characters
        name = (c.get("name") or "").strip()
        if not name:
            continue
        voice = (c.get("voice_notes") or "").strip()
        personality = (c.get("personality") or "").strip()
        if not voice and not personality:
            continue
        parts = [f"- {name}"]
        if personality:
            parts.append(f"性格：{personality[:120]}")
        if voice:
            parts.append(f"语言习惯：{voice[:120]}")
        lines.append("；".join(parts))
    return "\n".join(lines) if lines else ""


def _build_style_reference(world: World, current_chapter_id: str) -> list[str]:
    """Get polished excerpts from previous 1-2 chapters for style anchoring."""
    from worldforger.story_store import polished_path, read_text

    chapters = sorted(
        [c for c in world.story.chapters if c.id != current_chapter_id],
        key=lambda c: c.order,
    )
    refs = []
    for c in reversed(chapters[-2:]):  # last 2 chapters before current
        pp = polished_path(world.meta.id, c.id)
        if not pp.is_file():
            # fall back to original manuscript
            from worldforger.story_store import manuscript_path

            mp = manuscript_path(world.meta.id, c.id)
            if mp.is_file():
                txt = read_text(mp)
                # take first 400 chars + a middle 400-char chunk
                excerpt = txt[:400]
                mid = len(txt) // 2
                if mid > 400:
                    excerpt += "\n…\n" + txt[mid : mid + 400]
                refs.append(f"【{c.title or c.id} 参考片段（未润色原稿）】\n{excerpt}")
            continue
        txt = read_text(pp)
        # Remove the polish notes section for style reference
        notes_marker = "## 润色说明"
        if notes_marker in txt:
            txt = txt.split(notes_marker)[0].strip()
        excerpt = txt[:400]
        mid = len(txt) // 2
        if mid > 400:
            excerpt += "\n…\n" + txt[mid : mid + 400]
        refs.append(f"【{c.title or c.id} 润色稿参考】\n{excerpt}")
    return refs


def format_consistency_issues_for_polisher(report) -> str:
    """Format consistency issues as actionable items for the polisher.

    Returns (issues_text, regression_text) tuple-like joined string.
    Only includes warning and info issues; critical issues are noted but not for fixing.
    """
    if not report or not hasattr(report, "issues") or not report.issues:
        return ""

    fixable = []
    critical_notes = []
    for i, iss in enumerate(report.issues, 1):
        if iss.severity == "critical":
            critical_notes.append(f"  [仅标注-CRITICAL] {iss.category}: {iss.description}")
        else:
            suggestion = f"（建议：{iss.suggestion}）" if iss.suggestion else ""
            fixable.append(f"  {i}. [{iss.category}] {iss.description} {suggestion}")

    parts = []
    if fixable:
        parts.append("以下问题需在润色时修复：\n" + "\n".join(fixable))
    if critical_notes:
        parts.append(
            "以下严重问题仅作标注，请勿自行修改（需用户手动处理）：\n" + "\n".join(critical_notes)
        )
    return "\n\n".join(parts)
