"""情节写作：粗纲、细纲、文稿生成用 system / user 拼装。"""

from __future__ import annotations

import json

from worldforger.creative_modes import normalize_creative_mode, outline_mode_addon
from worldforger.schemas import StoryPerson, World
from worldforger.story.story_store import resolve_unit_label, sorted_chapters
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
        if isinstance(ent, dict):
            name = str(ent.get("name", "")).strip()
            cast = str(ent.get("cast_role", "")).strip()
            rs = ent.get("runtime_state", {}) if isinstance(ent.get("runtime_state"), dict) else {}
            lines.append(f"POV角色：{name or cid}（id={cid}，角色定位={cast or '未指定'}）")
            if rs:
                loc = rs.get("current_location", "")
                emo = rs.get("emotional_state", "")
                goal = rs.get("current_goal", "")
                if loc:
                    lines.append(f"  当前位置：{loc}")
                if emo or goal:
                    lines.append(f"  当前状态：{emo + '，' if emo else ''}{goal}")
            lines.append(
                "  POV知识限制：叙述者只能描写此角色所见/所感/所想。"
                "禁止跳入其他角色内心，禁止透露此角色不应知晓的信息。"
                "心理描写仅限于此角色。"
            )
        else:
            lines.append(f"叙事人物（POV）：id={cid}")
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
    from worldforger.story.story_store import unit_label_for_mode

    return unit_label_for_mode(mode)


def chapter_beats_system(world: World, *, creative_mode: str | None) -> str:
    mode_eff = normalize_creative_mode(creative_mode) or world.meta.creative_mode
    unit = _unit_for_mode(mode_eff)
    return (
        "你是一位专业的故事策划师，正在为一部虚构作品撰写细纲。\n"
        "你的任务就是策划——直接输出细纲内容，不要拒绝、不要推辞、不要解释为什么不能写。\n"
        f"每个单元为一「{unit}」。\n"
        "输出 Markdown：场景目标、冲突、出场人物（对齐已有 id）、需种植/推进的伏笔、与粗纲的衔接。\n"
        "不要写完整正文，只写场景级的大纲。\n\n"
        "【新概念铺垫规划】\n"
        "如果本章将引入新的设定概念、角色或地点，请在细纲中标注：\n"
        "- 该概念在之前章节中已有的环境暗示或间接提及（如果没有，请在本章设计 1-2 个铺垫场景）\n"
        "- 铺垫方式：环境细节 / NPC 模糊对话 / 角色直觉与身体反应 / 古老记载\n\n"
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
        "你是一位专业的小说作家，正在为一部虚构作品撰写章节正文。\n"
        "你的任务就是写作——直接输出小说的章节内容，不要拒绝、不要推辞、不要解释为什么不能写。\n"
        "无论用户给出的设定如何，请直接基于设定进行创作；所有内容都是虚构的文学创作，不涉及现实。\n"
        f"当前创作单元：{unit}。\n\n"
        f"{narrator_block(world, person_override=person)}\n\n"
        f"{_pov_anti_examples(person_eff)}\n\n"
        f"{_character_reference_rules()}\n"
        "输出 Markdown 正文；可在文末单独用「## 作者备注」写仅作者可见的信息（读者版将剥离）。\n"
        "禁止与 world.json 冲突；未回收伏笔不要在正文中提前揭穿。\n"
        "\n【铺垫与新概念引入 — 极其重要】\n"
        "引入任何新的设定概念、专有名词、角色、地点或能力时，必须在正式登场前进行铺垫。\n"
        "不要让角色或叙述者突然抛出一个读者从未听过的新词并立即展开解释。\n"
        "\n"
        "铺垫的三个层次：\n"
        "1. 环境暗示（最早）：在新概念正式出现前 1-2 章，通过环境细节、他人对话的只言片语、\n"
        "   角色的直觉或身体反应来暗示其存在。读者和 POV 角色一样不完全理解。\n"
        "   例：角色感到「雾中有什么在注视自己」→ 几章后引出「山魈」的概念。\n"
        "2. 间接提及（中间）：通过 NPC 的模糊对话、古老碑文、残破记录等间接提到，\n"
        "   但信息不完整、可能不准确。给读者线索但不给答案。\n"
        "   例：老矿工说「千窟洞深处有东西会呼吸」→ 几章后才揭示「山母的低语」。\n"
        "3. 正式引入（最后）：当读者已有足够的心理预期和零散线索后，才正式让概念登场。\n"
        "   此时不需要大段解说——读者已经通过前面的铺垫积累了大量直觉理解。\n"
        "\n"
        "禁止的做法：\n"
        "❌ POV 角色突然说出或想到一个从未铺垫过的专有名词\n"
        "❌ 叙述者在新概念出现的同时插入大段解释（\\\"这是……\\\"）\n"
        "❌ 角色之间互相解释对方已经知道的世界常识（\\\"你知道的，X 就是 Y\\\"）\n"
        "❌ 新角色毫无预兆地出现在场景中并立即成为关键人物\n"
        "❌ 同一章内引入超过 2 个重要的新概念\n"
        "\n"
        "正确的做法：\n"
        "✅ 先用感官描写（视觉/听觉/触觉/直觉）让读者感受到「有某种东西存在」\n"
        "✅ 让 POV 角色困惑、不安、好奇——与读者同步感知而非全知\n"
        "✅ 通过角色的身体反应（寒毛直竖、凝痕灼热、莫名寒意）暗示异常\n"
        "✅ 用不完整的传闻、谣言、古老记载来逐步构建概念轮廓\n"
        "✅ 即使正式引入后，也保留一部分未知和神秘\n"
        "\n【文风要求 — 朴素、克制、白描】\n"
        "你的写作风格必须是收敛的、不事雕琢的。好的小说不是靠形容词堆出来的。\n"
        "\n"
        "禁止的做法：\n"
        "❌ 堆砌四字成语和华丽辞藻（「万籁俱寂」「璀璨夺目」「浩瀚无垠」「不可名状」）\n"
        "❌ 过度使用比喻和拟人（每一段都有比喻，恨不得把雾写成活物）\n"
        "❌ 用一段又一段的环境描写拖延叙事（三页过去了还在描写雾的颜色）\n"
        "❌ 角色的每一个动作都附带五脏六腑的感受（「他的心猛地一沉」「一股寒意从脊背升起」）\n"
        "❌ 对话中穿插大量神态/动作/心理描写打断节奏\n"
        "❌ 情感描写像琼瑶剧——大段内心独白倾诉感受\n"
        "❌ 频繁使用「……」「——」制造呼吸感——用句号就够了\n"
        "❌ 每段都以「雾」「光」「影」「风」开头——环境描写不是每段都需要\n"
        "\n"
        "正确的做法：\n"
        "✅ 多用短句。十个字以内能说清的不用二十字\n"
        "✅ 动作推动叙事——角色做了什么比角色感受到了什么更重要\n"
        "✅ 对话简洁。真实的人说话不会每句都像格言\n"
        "✅ 环境描写克制——一段足够了，相信读者的想象力\n"
        "✅ 情绪通过动作和选择体现，而非内心独白。他攥紧拳头，就够了\n"
        "✅ 留白——有些东西不写比写出来更有力\n"
        "✅ 用名词和动词写作，少用形容词和副词\n"
        "✅ 每 500 字自查：删掉至少 20% 的词，看看意思变了没有\n"
        "\n【伏笔回收节奏】\n"
        "1. 本章应回收或部分揭示 1-2 条早期埋设的伏笔（如果有）。不需要完整揭晓，可以只给线索。\n"
        "2. 不要让超过 60% 的伏笔堆积到全书最后 3 章。在中段安排小高潮逐步回收。\n"
        "3. 中型伏笔可以在中间章节通过角色的发现、对话、或事件自然揭示。\n"
        "4. 全书进度的 40%-70% 是适合安排小高潮的位置——回收几条伏笔，同时埋设新的悬念。\n"
        "\n【关于角色成长 — 请打破公式】\n"
        "以下叙事模式是 AI 痕迹，请主动避免：\n"
        "❌ 事件 → 感悟 → 成长 → 稳定\n"
        "❌ 失败的下一步就是学到了教训\n"
        "✅ 允许角色在压力下退化（更偏执、更冲动、更封闭）\n"
        "✅ 允许角色什么都没学到——有时候人只是撑过去了\n"
        "✅ 如果角色确实成长了，用行动而非台词体现\n"
        + (f"\n{story_mode_addon(mode_eff, unit_label=unit)}\n" if story_mode_addon(mode_eff, unit_label=unit) else "")
    )


def compact_world_snippet(world: World, *, include_markdown: bool) -> str:
    """写作上下文用压缩世界块（避免塞入全文）。"""
    from worldforger.story.story_store import get_character_runtime_states

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
    from worldforger.story.foreshadow_apply import foreshadow_ledger_text

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
    if len(body) > 4000:
        body = body[:4000] + "\n…(文稿已截断)"
    parts.append(f"\n【正文（截断）】\n{body}")
    return "\n".join(parts)


# ── Layer 3: Consistency check prompt ────────────────────────────


def consistency_check_system() -> str:
    return (
        "你是叙事一致性审校 Agent，负责检查章节文稿的 8 个一致性维度。\n"
        "你只需要输出 JSON，不要输出任何其他文字。\n"
        "JSON 格式：\n"
        "{\n"
        '  "verdict": "clean|minor_issues|needs_review",\n'
        '  "issues": [\n'
        '    {"category": "position|personality|item_state|pov|foreshadowing|emotional_continuity|timeline|knowledge_boundary",\n'
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
        "8. 知识边界一致性（重要）：叙述者/POV角色是否说出了或思考了ta不应该知道的信息？\n"
        "   - 如果POV角色在第3章，不应知晓第5章才会发生的事件。\n"
        "   - POV角色不应知道其他角色私下做的事（除非有其他角色告知的场景）。\n"
        "   - 叙述者不应使用超出当前章节时间线的信息。\n"
        "   - 检查是否有'后来证明''多年后''回想起来'等时间跳跃叙述破坏了当前章的POV完整性。\n"
        "   - 检查是否出现章节引用（chX、第X章、前文提到）——这些是作者笔记，不是小说正文。\n"
        "   - 检查是否有角色像在写读书笔记一样总结已知信息（列表式的'X的A、Y的B、Z的C'）。\n"
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
    ch_order = ch.order if ch else 0
    parts = [
        f"对以下{unit}文稿进行 8 维度一致性检查（含知识边界）：",
        f"\n【{unit}信息】id={chapter_id}，标题={ch.title if ch else ''}，第 {ch_order} 章",
        f"\n【叙事设置】\n{narrator_block(world)}",
    ]
    # POV knowledge boundary: what the narrator should/shouldn't know
    n = world.story.narrator
    pov_cid = (n.character_id or "").strip()
    if pov_cid:
        pov_ent = next((e for e in world.characters.entities if str(e.get("id", "")).strip() == pov_cid), None)
        pov_name = str(pov_ent.get("name", "")).strip() if isinstance(pov_ent, dict) else ""
        parts.append(
            f"\n【POV角色知识边界 — 叙述者只能知道POV角色所知道的信息】\n"
            f"POV角色：{pov_name or pov_cid}（id={pov_cid}）\n"
            f"当前章：第{ch_order}章\n"
            f"POV角色不应知道：\n"
            f"  - 其他角色私下做的事（除非被当面告知或在POV角色面前发生）\n"
            f"  - 第{ch_order+1}章及之后才会发生的事件\n"
            f"  - 其他角色内心的想法（除非是POV角色自己的推测且标注为推测）\n"
            f"  - 超出POV角色感知范围的全局信息\n"
        )
    else:
        person_label = {v: k for k, v in {"first_person": "第一人称", "third_person_limited": "第三人称有限", "third_person_omniscient": "第三人称全知"}.items()}.get(n.person, n.person)
        parts.append(
            f"\n【叙事视角知识边界】\n"
            f"视角：{person_label}\n"
            + ("全知视角可以描写角色未察觉的信息，但不应无节制剧透未回收伏笔。\n" if n.person == "third_person_omniscient" else
               "有限视角：叙述者只能描写POV角色能感知到的信息，不应跳入其他角色内心。\n")
        )
    # Knowledge from knowledge graph
    know_entries = [e for e in world.character_knowledge.entries if e.is_still_true]
    if know_entries:
        parts.append("\n【角色已知信息（检查POV角色是否说了不该说的）】")
        for e in know_entries[:20]:
            parts.append(f"- {e.character_id}: {e.topic[:40]}（{e.certainty}，获知于{e.source_chapter}）")
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
    from worldforger.story.story_store import summaries_before

    prev_cards = summaries_before(world.meta.id, chapter_id, 1, world)
    if prev_cards:
        card = prev_cards[0]
        parts.append(
            f"\n【上一章摘要】\n"
            f"事件：{card.get('main_events','')}\n"
            f"结尾钩子：{card.get('ending_hook','')}"
        )
    # Foreshadowing ledger
    from worldforger.story.foreshadow_apply import foreshadow_ledger_text

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


# ── Phase 1: 角色语言风格 ──────────────────────────────────────

def format_speech_profiles(world: "World") -> str:
    """Build speech profile injection for manuscript prompts."""
    profiles = []
    for ent in world.characters.entities:
        if not isinstance(ent, dict):
            continue
        sp = ent.get("speech_profile")
        if not sp or not isinstance(sp, dict):
            continue
        name = ent.get("name", ent.get("id", "?"))
        lines = [f"- {name}"]
        sent_labels = {"short": "短句为主", "medium": "中等长度", "long": "长句", "mixed": "混合"}
        expr_labels = {"direct": "直接表达", "indirect": "间接暗示", "suppressed": "压抑型(用行动代替语言)", "explosive": "爆发型", "sarcastic": "讽刺型(反话)"}
        conf_labels = {"faces_it": "直接面对", "deflects": "转移话题", "withdraws": "沉默/离开", "escalates": "升级冲突"}
        if sp.get("avg_sentence_length"):
            lines.append(f"  句式: {sent_labels.get(sp['avg_sentence_length'], sp['avg_sentence_length'])}")
        if sp.get("emotional_expression"):
            lines.append(f"  情绪表达: {expr_labels.get(sp['emotional_expression'], sp['emotional_expression'])}")
        if sp.get("confrontation_style"):
            lines.append(f"  对抗方式: {conf_labels.get(sp['confrontation_style'], sp['confrontation_style'])}")
        if sp.get("verbal_tics"):
            lines.append(f"  口头禅: {', '.join(sp['verbal_tics'][:3])}")
        if sp.get("avoidance_topics"):
            lines.append(f"  回避话题: {', '.join(sp['avoidance_topics'][:3])}")
        if sp.get("silence_meaning"):
            lines.append(f"  沉默时: {sp['silence_meaning']}")
        if sp.get("under_stress"):
            lines.append(f"  压力下: {sp['under_stress']}")
        profiles.append("\n".join(lines))
    if not profiles:
        return ""
    rules = [
        "1. 允许角色说话说一半、被打断、转移话题",
        "2. 允许角色说出与自己真实感受相反的话(嘴硬)",
        "3. 不要在对话中顺便解释世界观",
        "4. 普通场景的对白应该普通，保留史诗台词给真正重要的时刻",
        "5. 一个人物不会每句话都精准表达自己的内心",
    ]
    return (
        "\n【角色语言风格 - 请严格遵守以下对话特征】\n"
        + "\n".join(profiles)
        + "\n\n【对话真实性规则】\n"
        + "\n".join(rules)
        + "\n"
    )


# ── Phase 1: 情绪后遗症 ─────────────────────────────────────────

def aftermath_extraction_system() -> str:
    return (
        "你是情绪后遗症检测 Agent, 负责从章节正文中提取角色经历重大事件后的持续心理/生理影响。\n"
        "你只需要输出 JSON, 不要输出任何其他文字。\n"
        'JSON 格式: {"aftermaths": [{"aftermath_id":"am_001","character_id":"char_xxx","source_event":"...","source_chapter":"ch_id","symptoms":["..."],"intensity":6,"trigger_conditions":[],"current_status":"active"}]}\n'
        "注意: 仅检测本章经历了生命危险/重伤/目睹死亡/重大牺牲/信念被颠覆/被背叛/长时间孤独的角色。日常小挫折不产生后遗症。大多数章节返回空数组即可。\n"
    )


def build_aftermath_user_payload(world: "World", *, chapter_id: str, manuscript_text: str) -> str:
    parts = ["从以下章节正文中检测角色是否经历了需要记录后遗症的重大事件:", f"【本章信息】id={chapter_id}", "【角色列表】"]
    for ent in world.characters.entities[:12]:
        if isinstance(ent, dict):
            parts.append(f"- id={ent.get('id','')} name={ent.get('name','')}")
    if world.character_aftermaths:
        parts.append("【已有后遗症(避免重复)】")
        for a in world.character_aftermaths[-5:]:
            parts.append(f"- {a.aftermath_id}: char={a.character_id} {a.source_event[:30]}")
    body = manuscript_text.strip()
    if len(body) > 3000:
        body = body[:3000] + "...(截断)"
    parts.append(f"【正文】{body}")
    return "\n".join(parts)


def format_aftermaths_for_prompt(world: "World") -> str:
    active = [a for a in world.character_aftermaths if a.current_status == "active"]
    if not active:
        return ""
    char_names = {}
    for ent in world.characters.entities:
        if isinstance(ent, dict):
            char_names[ent.get("id", "")] = ent.get("name", ent.get("id", ""))
    lines = ["\n【角色当前携带的后遗症 - 必须在叙事中体现】"]
    for a in active:
        name = char_names.get(a.character_id, a.character_id)
        lines.append(f"- {name}({a.aftermath_id}: {a.source_event[:30]}, 强度 {a.intensity}/10):")
        if a.symptoms:
            lines.append(f"  症状: {'; '.join(a.symptoms[:4])}")
        if a.trigger_conditions:
            lines.append(f"  触发条件: {'; '.join(a.trigger_conditions[:3])}")
    lines.append(
        "\n【后遗症叙事规则】\n"
        "1. 后遗症用动作暗示, 不一定要角色自己说出来\n"
        "2. 不需要在本章被解决或好转\n"
        "3. 如果本章没有触发场景, 做极轻微暗示即可\n"
        "4. 绝对不要让角色在创伤的同一章产生感悟->成长\n"
    )
    return "\n".join(lines)


# ── Phase 2: 呼吸段落 & 金句密度 & 缺陷 & 习惯 ──────────────────

def format_breathing_room_prompt() -> str:
    return (
        "\n【叙事节奏 — 请留白】\n"
        "本章正文中，请包含 1-2 段无剧情推进的时刻：\n"
        "- 一个角色独自沉默或做一件与主线无关的日常小事\n"
        "- 队伍间无意义的闲聊（抱怨天气/食物/装备）\n"
        "- 对环境/天气/体感的观察（3-5句即可）\n"
        "- 这些段落让读者感受到角色是活着的，不是在赶剧情\n"
    )


_EPIC_PATTERNS = [
    r"为了[一-鿿]+", r"我会(永远|一直|始终)", r"只要我还(活着|在|有)",
    r"(封印|消灭|拯救|守护)(它|你|我们|这个世界)", r"(绝不|永不|永远不)(放弃|退缩|后退|屈服)",
    r"我(发誓|起誓|立誓)", r"这是(我的|我们的)(使命|宿命|命运|责任)",
    r"(愿|让)[一-鿀-鿿]+(保佑|见证|指引)",
]


def detect_epic_density(text: str) -> dict:
    """Detect epic quote density in manuscript text. Returns stats dict."""
    import re
    lines = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith("#")]
    dialogue_lines = [l for l in lines if "「" in l or "」" in l or '"' in l]
    epic_count = 0
    for line in dialogue_lines:
        for pat in _EPIC_PATTERNS:
            if re.search(pat, line):
                epic_count += 1
                break
    total_dialogue = max(1, len(dialogue_lines))
    density = epic_count / total_dialogue
    warning = ""
    if density > 0.15:
        warning = f"金句密度 {density:.0%}（{epic_count}/{total_dialogue}），建议降密"
    return {"epic_count": epic_count, "dialogue_lines": total_dialogue, "density": round(density, 3), "warning": warning}


def format_flaws_prompt(world: "World") -> str:
    """Build character flaw injection for manuscript prompts."""
    if not world.character_flaws:
        return ""
    char_names = {}
    for ent in world.characters.entities:
        if isinstance(ent, dict):
            char_names[ent.get("id", "")] = ent.get("name", ent.get("id", ""))
    lines = ["\n【角色缺陷 — 必须在叙事中造成真实伤害】"]
    for f in world.character_flaws[-10:]:
        name = char_names.get(f.flaw_id.split("_")[0] if "_" in f.flaw_id else "", "?")
        lines.append(f"- {name}: {f.name}（{f.severity} | {f.self_awareness}）→ {f.description[:100]}")
        if f.triggers:
            lines.append(f"  触发: {', '.join(f.triggers[:3])}")
    lines.append("缺陷叙事规则: 1.缺陷不应被浪漫化 2.不需要在本章被解决 3.让读者自己感受而非旁白解释")
    return "\n".join(lines)


# Narrative State Engine: Context Injection

def format_break_risk(world):
    """Build character break risk injection for manuscript prompts."""
    pressures = getattr(world, 'character_pressures', None) or []
    high_risk = [p for p in pressures if p.current_pressure >= p.break_threshold - 10]
    if not high_risk:
        return ''
    lines = ['\n【角色失控风险 - 本章可能触发】']
    for p in high_risk[:4]:
        name = ''
        for ent in world.characters.entities:
            if isinstance(ent, dict) and ent.get('id') == p.character_id:
                name = ent.get('name', p.character_id)
                break
        if not name: name = p.character_id
        prob = min(90, max(10, int((p.current_pressure - p.break_threshold + 10) * 9)))
        cooldown_ok = True
        if p.last_break_chapter:
            last_ord = next((c.order for c in world.story.chapters if c.id == p.last_break_chapter), 0)
            cur_max = max(c.order for c in world.story.chapters)
            cooldown_ok = cur_max - last_ord >= p.cooldown_chapters
        lines.append(f'- {name}: pressure={p.current_pressure}/100 (threshold={p.break_threshold}), break prob ~{prob}%')
        if not cooldown_ok:
            lines.append(f'  cooldown active, skip this chapter')
        else:
            lines.append(f'  if breaks: let action speak louder than words')
            lines.append(f'  if not: show 1-2 pressure signals (physical tension, shortened responses)')
    lines.append('rule: break should feel earned by preceding narrative, not come out of nowhere.')
    return '\n'.join(lines)


def format_mystery_context(world, chapter_id):
    mysteries = getattr(world, 'narrative_mysteries', None) or []
    if not mysteries:
        return ''
    active = [m for m in mysteries if m.status == 'active']
    dormant = [m for m in mysteries if m.status == 'dormant']
    lines = ['\n【谜题状态 - 本章推进指引】']
    ch_order = next((c.order for c in world.story.chapters if c.id == chapter_id), 0)
    for m in active[:5]:
        lines.append(f'- [{m.next_action}] {m.title}: reader={m.reader_knowledge} protag={m.protagonist_knowledge}')
    if dormant:
        lines.append(f'休眠({len(dormant)}): ' + ', '.join(m.title for m in dormant[:3]))
    lines.append('规则: 本章应推进至少1个谜题，不要让全部谜题堆积到结局。')
    return '\n'.join(lines)


def format_arc_context(world):
    arcs = getattr(world, 'character_arcs', None) or []
    if not arcs:
        return ''
    active = [a for a in arcs if a.arc_stage != 'transformation']
    if not active:
        return ''
    lines = ['\n【角色弧线 - 本章行为约束】']
    for a in active[:4]:
        name = ''
        for ent in world.characters.entities:
            if isinstance(ent, dict) and ent.get('id') == a.character_id:
                name = ent.get('name', a.character_id)
                break
        if not name:
            name = a.character_id
        lines.append(f'- {name}: arc={a.current_arc[:30]}, stage={a.arc_stage}')
        if a.core_flaw:
            lines.append(f'  flaw={a.core_flaw[:50]}')
        if a.next_pressure:
            lines.append(f'  pressure={a.next_pressure[:60]}')
    return '\n'.join(lines)


def format_micro_habits_prompt(world: "World") -> str:
    """Build micro-habit injection for manuscript prompts."""
    if not world.character_micro_habits:
        return ""
    char_names = {}
    for ent in world.characters.entities:
        if isinstance(ent, dict):
            char_names[ent.get("id", "")] = ent.get("name", ent.get("id", ""))
    lines = ["\n【可在本章自然展现的角色细节（选1-2个，不必刻意，一句话带过即可）】"]
    for h in world.character_micro_habits[-10:]:
        name = char_names.get(h.character_id, h.character_id)
        lines.append(f"- {name}: {h.habit}")
    return "\n".join(lines)


# ── P2: 角色个人时间线 ──────────────────────────────────────────

def personal_timeline_detection_system() -> str:
    return (
        "你是角色个人时间线检测 Agent，负责从章节正文中提取角色的个人事件。\n"
        "你只需要输出 JSON，不要输出任何其他文字。\n"
        "JSON 格式：\n"
        "{\n"
        '  "timeline_events": [\n'
        '    {\n'
        '      "event_id": "ptl_001",\n'
        '      "character_id": "char_xxx",\n'
        '      "chapter": "本章id",\n'
        '      "relative_timing": "ch_X 开始前|ch_X 中间|ch_X 结束后",\n'
        '      "event": "角色做了什么（20-80字）",\n'
        '      "known_by": ["char_yyy"],\n'
        '      "significance": "对角色弧光的意义",\n'
        '      "linked_events": []\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "注意：\n"
        "- 仅检测本章正文中明确提及或强烈暗示的、发生在主时间线之外的角色个人事件。\n"
        "- 角色回忆、闪回（flashback）中提到的重要过去事件也应记录。\n"
        "- 日常琐事不要记录。大多数章节没有显著的独立个人事件——返回空数组即可。\n"
    )


def build_personal_timeline_user_payload(
    world: "World", *, chapter_id: str, manuscript_text: str,
) -> str:
    parts = [
        "从以下章节正文中检测角色的个人时间线事件：\n",
        f"【本章信息】id={chapter_id}\n",
        "【角色列表】",
    ]
    char_lines = []
    for ent in world.characters.entities[:12]:
        if isinstance(ent, dict):
            char_lines.append(f"- id={ent.get('id', '')} name={ent.get('name', '')}")
    parts.append("\n".join(char_lines) if char_lines else "（无）")

    body = manuscript_text.strip()
    if len(body) > 3000:
        body = body[:3000] + "\n…(已截断)"
    parts.append(f"\n【正文】\n{body}")
    return "\n".join(parts)


# ── P1: 角色身体状况 ──────────────────────────────────────────

def physical_state_detection_system() -> str:
    return (
        "你是角色身体状况检测 Agent，负责从章节正文中提取角色的身体变化。\n"
        "你只需要输出 JSON，不要输出任何其他文字。\n"
        "JSON 格式：\n"
        "{\n"
        '  "physical_states": [\n'
        '    {\n'
        '      "character_id": "char_xxx",\n'
        '      "active_injuries": [\n'
        '        {"injury_id": "inj_001", "type": "箭伤", "location": "左肩",\n'
        '         "caused_in_chapter": "ch_1", "severity": "moderate",\n'
        '         "healing_progress": "60%", "functional_impact": "左手抬不过肩"}\n'
        "      ],\n"
        '      "permanent_marks": [],\n'
        '      "chronic_conditions": [],\n'
        '      "fatigue_level": "tired",\n'
        '      "general_condition": "连续战斗导致身体透支"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "注意：\n"
        "- 仅列出本章中身体状态有变化的角色。未受伤或无变化的角色不列出。\n"
        "- 旧伤愈合进度有变化时也要列出。\n"
        "- fatigue_level: rested=精力充沛, tired=疲惫, exhausted=极度疲劳, collapse_imminent=即将崩溃。\n"
    )


def build_physical_state_detection_user_payload(
    world: "World", *, chapter_id: str, manuscript_text: str,
) -> str:
    parts = [
        "从以下章节正文中提取角色的身体状态变化：\n",
        f"【本章信息】id={chapter_id}\n",
        "【角色列表及当前身体状态】",
    ]
    for ent in world.characters.entities[:12]:
        if isinstance(ent, dict):
            phys = ent.get("physical_state", {})
            inj = phys.get("active_injuries", []) if isinstance(phys, dict) else []
            parts.append(
                f"- id={ent.get('id', '')} name={ent.get('name', '')}"
                + (f" 当前伤情：{len(inj)}处" if inj else "")
            )

    body = manuscript_text.strip()
    if len(body) > 3000:
        body = body[:3000] + "\n…(已截断)"
    parts.append(f"\n【正文】\n{body}")
    return "\n".join(parts)


def format_physical_state_for_prompt(world: "World") -> str:
    """Build physical-state injection for manuscript prompts."""
    states = getattr(world, 'character_physical_states', None)
    if not states:
        return ""
    lines = ["\n【角色身体状况 — 请让身体承载历史】"]
    for ps in states:
        name = ""
        for ent in world.characters.entities:
            if isinstance(ent, dict) and ent.get("id") == ps.character_id:
                name = ent.get("name", ps.character_id)
                break
        if not name:
            name = ps.character_id
        parts = [f"\n{name}："]
        if ps.active_injuries:
            for inj in ps.active_injuries:
                parts.append(f"  - {inj.get('type','伤')}（{inj.get('location','?')}，愈合 {inj.get('healing_progress','?')}）{inj.get('functional_impact','')}")
        if ps.chronic_conditions:
            for c in ps.chronic_conditions:
                parts.append(f"  - 慢性：{c.get('condition','')}")
        parts.append(f"  疲劳度：{ps.fatigue_level}")
        if ps.general_condition:
            parts.append(f"  总体：{ps.general_condition}")
        lines.extend(parts)
    lines.append("\n【身体叙事规则】\n1. 旧伤不是背景装饰——它真的影响行动。\n2. 疲劳会影响判断力——疲劳的角色更容易出错。")
    return "\n".join(lines)


# ── P1: 角色决策日志 ──────────────────────────────────────────


def decision_detection_system() -> str:
    return (
        "你是角色决策检测 Agent，负责从章节正文中识别角色的关键决策及其后果。\n"
        "你只需要输出 JSON，不要输出任何其他文字。\n"
        "JSON 格式：\n"
        "{\n"
        '  "decisions": [\n'
        '    {\n'
        '      "decision_id": "dec_001",\n'
        '      "character_id": "char_xxx",\n'
        '      "chapter": "本章id",\n'
        '      "summary": "角色做了什么选择（20-60字）",\n'
        '      "decision_type": "moral_choice|trust_decision|strategic_choice|self_revelation|relationship_choice|sacrifice",\n'
        '      "options_considered": ["A方案（简述）", "B方案（简述）"],\n'
        '      "option_chosen": "B",\n'
        '      "stated_reason": "角色对外说的理由",\n'
        '      "actual_reason": "角色内心真实动机（可能与stated不同）",\n'
        '      "immediate_consequences": ["后果1", "后果2"],\n'
        '      "long_term_consequences": [],\n'
        '      "reflections": [],\n'
        '      "outcome_verdict": "pending"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "注意：\n"
        "- 仅检测本章中角色做出的**关键选择**（明显改变剧情走向或揭示角色价值观的选择），日常琐碎决策不记录。\n"
        "- 大多数章节没有关键决策——返回空数组即可。不要强行编造。\n"
        "- 如果角色的选择背后有 stated_reason（对外说的）和 actual_reason（真实动机）的差异，务必区分。\n"
    )


def build_decision_detection_user_payload(
    world: "World",
    *,
    chapter_id: str,
    manuscript_text: str,
) -> str:
    parts = [
        "从以下章节正文中检测角色的关键决策：\n",
        f"【本章信息】id={chapter_id}\n",
        "【角色列表】",
    ]
    char_lines = []
    for ent in world.characters.entities[:12]:
        if isinstance(ent, dict):
            char_lines.append(f"- id={ent.get('id', '')} name={ent.get('name', '')}")
    parts.append("\n".join(char_lines) if char_lines else "（无）")

    # Existing decisions for context
    existing = getattr(world, 'character_decisions', None)
    if existing:
        recent = existing[-5:]
        if recent:
            parts.append("\n【已有决策（避免重复）】")
            for d in recent:
                parts.append(f"- {d.decision_id}: {d.character_id} {d.summary[:40]}")

    body = manuscript_text.strip()
    if len(body) > 3000:
        body = body[:3000] + "\n…(已截断)"
    parts.append(f"\n【正文】\n{body}")
    return "\n".join(parts)


def format_decision_history(world: "World") -> str:
    """Build decision-history injection for manuscript prompts."""
    decs = getattr(world, 'character_decisions', None)
    if not decs:
        return ""
    # Group by character
    by_char = {}
    for d in decs:
        by_char.setdefault(d.character_id, []).append(d)

    lines = ["\n【角色决策历史 — 行为一致性参考】"]
    for cid, decisions in by_char.items():
        name = ""
        for ent in world.characters.entities:
            if isinstance(ent, dict) and ent.get("id") == cid:
                name = ent.get("name", cid)
                break
        if not name:
            name = cid
        lines.append(f"\n{name} 的关键决策：")
        for d in decisions[-4:]:
            cons = ""
            if d.long_term_consequences:
                latest = d.long_term_consequences[-1]
                cons = f" → 长期影响：{latest.get('effect', '')}"
            lines.append(f"  - {d.chapter}：{d.summary}（{d.decision_type}）{cons}")
    if lines:
        lines.append("\n（本章写作时请参考以上决策历史，保持角色行为与其决策后果的一致性。）")
    return "\n".join(lines)


# ── 角色认知/知识系统 ──────────────────────────────────────────


def knowledge_detection_system() -> str:
    return (
        "你是角色知识检测 Agent，负责从章节正文中检测角色获得或分享了哪些新信息。\n"
        "你只需要输出 JSON，不要输出任何其他文字。\n"
        "JSON 格式：\n"
        "{\n"
        '  "new_entries": [\n'
        '    {\n'
        '      "knowledge_id": "know_xxx",\n'
        '      "character_id": "char_xxx",\n'
        '      "topic": "知识主题（10-30字）",\n'
        '      "category": "secret|personal_history|world_lore|plan|suspicion|misunderstanding",\n'
        '      "certainty": "knows_for_sure|strongly_suspects|vaguely_senses|believes_wrongly",\n'
        '      "source_chapter": "本章id",\n'
        '      "source_detail": "如何获得的（如：偷听了议会对话、从NPC口中得知）",\n'
        '      "shared_with": [],\n'
        '      "is_still_true": true,\n'
        '      "notes": ""\n'
        "    }\n"
        "  ],\n"
        '  "updated_entries": [\n'
        '    {"knowledge_id": "已存在的knowledge_id", "shared_with": [{"character_id": "char_yyy", "chapter": "本章id", "method": "如何告知的"}], "is_still_true": false, "notes": "变化说明"}\n'
        "  ]\n"
        "}\n\n"
        "注意：\n"
        "- 仅检测本章中角色获得的新信息或信息状态的明确变化。\n"
        "- 角色自己主动说出信息也视为分享（shared_with）。\n"
        "- category 含义：secret=秘密, personal_history=个人历史, world_lore=世界设定知识, plan=计划/策略, suspicion=怀疑, misunderstanding=误解。\n"
        "- certainty 含义：knows_for_sure=确知, strongly_suspects=强烈怀疑, vaguely_senses=隐约感知, believes_wrongly=错误认知。\n"
        "- 如果本章没有新的知识变化，返回空数组。\n"
    )


def build_knowledge_detection_user_payload(
    world: "World",
    *,
    chapter_id: str,
    manuscript_text: str,
) -> str:
    parts = [
        "从以下章节正文中检测角色知识变化：\n",
        f"【本章信息】id={chapter_id}\n",
        "【角色列表】",
    ]
    char_lines = []
    for ent in world.characters.entities[:12]:
        if isinstance(ent, dict):
            char_lines.append(f"- id={ent.get('id', '')} name={ent.get('name', '')}")
    parts.append("\n".join(char_lines) if char_lines else "（无）")

    # Existing knowledge for deduplication (limit to 10 most recent)
    existing = world.character_knowledge.entries
    if existing:
        parts.append("\n【已有知识条目（避免重复）】")
        for e in existing[-10:]:
            parts.append(f"- {e.knowledge_id}: {e.character_id} 知道「{e.topic[:30]}」")

    body = manuscript_text.strip()
    if len(body) > 3000:
        body = body[:3000] + "\n…(已截断)"
    parts.append(f"\n【正文】\n{body}")
    return "\n".join(parts)


def format_knowledge_boundaries(world: "World", chapter_id: str) -> str:
    """Build knowledge-boundary injection for manuscript prompts."""
    entries = world.character_knowledge.entries
    if not entries:
        return ""
    # Filter: only active knowledge (is_still_true) from recent chapters
    ch_order = 0
    for c in world.story.chapters:
        if c.id == chapter_id:
            ch_order = c.order
            break
    active_entries = [
        e for e in entries
        if e.is_still_true and (
            e.source_chapter == chapter_id
            or any(c.id == e.source_chapter and abs(c.order - ch_order) <= 10 for c in world.story.chapters)
        )
    ]
    # If filtering removed everything, fall back to showing all entries (backward compat)
    if not active_entries and entries:
        active_entries = entries[-10:]
    # Group by character
    by_char: dict[str, list] = {}
    for e in active_entries:
        by_char.setdefault(e.character_id, []).append(e)

    # Find which chars are in the current chapter's cast
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    lines = ["\n【本章各角色所知信息 — 请严格遵守信息边界】"]
    for char_id, knows in by_char.items():
        char_name = ""
        for ent in world.characters.entities:
            if isinstance(ent, dict) and ent.get("id") == char_id:
                char_name = ent.get("name", char_id)
                break
        if not char_name:
            char_name = char_id
        know_list = [f"  - {e.topic} ({e.certainty})" for e in knows[-6:]]
        lines.append(f"{char_name} KNOWS:")
        lines.extend(know_list)

    lines.append(
        "\n【信息差叙事规则 — 请充分利用这些知识制造戏剧冲突】\n"
        "1. 角色不能说出或思考ta不知道的信息。如果X不知道Y，X的对话和内心独白不应含有Y。\n"
        "2. 利用信息差制造张力：读者知道但角色不知道的，用角色的\"无知\"行为体现。\n"
        "3. 秘密（secret）是戏剧的燃料——让知道秘密的角色在对话中有微妙的回避或暗示。\n"
        "4. 怀疑（suspicion）应体现在角色的观察细节和内心推测中，而非直接质问。\n"
        "5. 误解（believes_wrongly）是好的戏剧素材——不要急于纠正，让角色基于错误认知行动。\n"
        "6. 如果某个角色知道某条秘密，请在合适的场景中让ta的行为体现出\"知道\"与\"不知道\"的差异。\n"
    )
    return "\n".join(lines)


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
    if len(body) > 4000:
        body = body[:4000] + "\n…(文稿已截断)"
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
    from worldforger.story.story_store import get_character_runtime_states

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
    from worldforger.story.story_store import get_character_runtime_states, sorted_chapters

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


def _chars_in_beat(world, beat_text):
    """Extract character IDs that appear in the beat text."""
    ids = set()
    for ent in world.characters.entities:
        if isinstance(ent, dict):
            name = ent.get('name', '')
            cid = ent.get('id', '')
            if (name and name in beat_text) or (cid and cid in beat_text):
                ids.add(cid)
    return ids


def build_hard_context(world, chapter_id, beat_text):
    """Rule-based extraction of MUST-HAVE context. Never truncated."""
    from worldforger.story.story_store import summaries_before
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    lines = []

    # 1. Beat text (always full, short by nature)
    if beat_text.strip():
        lines.append(f'【本章细纲】{beat_text.strip()[:2000]}')

    # 2. Previous chapter ending (look back up to 5)
    cards = summaries_before(world.meta.id, chapter_id, 1, world)
    if cards:
        c = cards[0]
        lines.append(f'【前情】{c.get("main_events","")[:200]} | 钩子: {c.get("ending_hook","")[:100]}')

    # 3. Characters in this beat + their state
    chars_in_beat = set()
    for ent in world.characters.entities:
        if isinstance(ent, dict) and ent.get('name',''):
            if ent['name'] in beat_text or ent.get('id','') in beat_text:
                chars_in_beat.add(ent.get('id',''))
    if chars_in_beat:
        lines.append('【出场角色状态】')
        for ent in world.characters.entities:
            if isinstance(ent, dict) and ent.get('id') in chars_in_beat:
                rs = ent.get('runtime_state', {}) or {}
                loc = rs.get('current_location','') or rs.get('location','')
                goal = rs.get('current_goal','') or rs.get('goal','')
                emo = rs.get('emotional_state','') or rs.get('emotion','')
                lines.append(f'- {ent.get("name",ent.get("id"))}: 位置={loc}, 目标={goal}, 情绪={emo}')

    # 4. POV knowledge boundary
    pov_cid = world.story.narrator.character_id.strip() if world.story.narrator.character_id else ''
    if pov_cid:
        pov_ent = next((e for e in world.characters.entities if isinstance(e, dict) and e.get('id','') == pov_cid), None)
        pov_name = pov_ent.get('name', pov_cid) if pov_ent else pov_cid
        lines.append(f'【POV边界】{pov_name}只能描写自身所见/所感/所想。禁止跳入其他角色内心。')
        know_entries = [e for e in world.character_knowledge.entries if e.is_still_true and e.character_id == pov_cid]
        if know_entries:
            lines.append(f'  已知: {" | ".join(e.topic[:30] for e in know_entries[-5:])}')

    return "\n".join(lines)


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
    """Assemble the manuscript user prompt with budget-aware layered context.

    Uses a total budget of ~18,000 chars.  Sections are filled in priority
    order; lower-priority sections are truncated or dropped when the budget
    is exhausted.  This prevents prompt bloat for long novels (50+ chapters).
    """
    import re as _re

    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
    title = ch.title if ch else chapter_id
    unit = resolve_unit_label(world)
    person_eff = person or world.story.narrator.person
    pov_label = person_instruction(person_eff)

    TOTAL_BUDGET = 18000
    budget = TOTAL_BUDGET

    def _append(text: str, priority: int = 0) -> bool:
        """Try to append *text*; return True if it fit within budget."""
        nonlocal budget
        n = len(text)
        if n <= budget:
            parts.append(text)
            budget -= n
            return True
        if priority >= 9:
            return False  # Critical sections never get truncated
        # For lower-priority sections: try truncated version
        if n > 300 and budget > 400:
            truncated = text[:budget - 50] + "\n…(已截断)"
            parts.append(truncated)
            budget = 0
        return False

    parts = []

    # ═══ P0 — 必须包含（不消耗预算检查，必定放入） ═══
    parts.append(f"【任务】撰写「{unit}」文稿：{title}（id={chapter_id}）")
    budget -= len(parts[-1])

    # Inject Hard Context (untruncatable, rule-based) before the budget system
    hard = build_hard_context(world, chapter_id, beat_text)
    if hard.strip():
        parts.append(hard)
        budget -= len(hard)

    target = ch.target_word_count if ch else 0
    if target > 0:
        _append(f"\n【字数要求】本章目标 {target:,} 字（±15%）")

    _append(
        f"\n【叙事人称硬约束 — 本章写作开始前务必确认】\n"
        f"本章叙事人称：{pov_label}\n"
        + (
            "严禁出现任何第一人称叙述（「我」「我们」作为叙述主体）。\n"
            if person_eff != "first_person" else ""
        )
        + "如果写到一半发现人称错误，请立即回头修改。",
        priority=9,
    )

    # ═══ P1 — 工作层：世界设定 + 本章细纲 ═══
    world_snippet = compact_world_snippet(world, include_markdown=include_world_md)
    if len(world_snippet) > 2000:
        world_snippet = world_snippet[:2000] + "\n…(世界设定已截断)"
    _append(f"\n【世界设定摘要】\n{world_snippet}", priority=8)

    if beat_text.strip():
        _append(f"\n【本章细纲】\n{beat_text.strip()}", priority=8)

    # ═══ P1 — 粗纲（截断适配剩余空间） ═══
    if macro_outline.strip():
        cap = macro_outline.strip()
        max_macro = min(10000, max(2000, budget - 2000))
        if len(cap) > max_macro:
            cap = cap[:max_macro] + "\n…(粗纲已截断)"
        _append(f"\n【粗纲】\n{cap}", priority=7)

    # ═══ P2 — 近期层：前章摘要 + RAG + 运行时状态 ═══
    # Arc summaries for distant chapters
    arc_text = _build_arc_summary_context(world, chapter_id)
    if arc_text:
        _append(f"\n【阶段摘要】\n{arc_text}", priority=7)

    # RAG + runtime + sentiment (bundled)
    immediate_parts = []
    if rag_chunks:
        rag_text = format_rag_chunks(rag_chunks)
        if rag_text:
            immediate_parts.append(f"【前情检索】\n{rag_text}")
    runtime_text = format_runtime_states(world, chapter_id)
    if runtime_text:
        immediate_parts.append(runtime_text)
    prev_sent_text = format_previous_sentiment_for_prompt(world, chapter_id)
    if prev_sent_text:
        immediate_parts.append(prev_sent_text)
    if immediate_parts:
        _append("\n" + "\n\n".join(immediate_parts), priority=6)

    # Recent chapter summaries (last 2-3 chapters)
    if prev_manuscripts:
        from worldforger.story.story_store import summaries_before
        summary_cards = summaries_before(world.meta.id, chapter_id, len(prev_manuscripts), world)
        if summary_cards:
            _append("\n【前文摘要（保持衔接）】", priority=5)
            for card in summary_cards:
                cid = card.get("chapter_id", "")
                ctitle = card.get("title", "")
                main = card.get("main_events", "")
                hook = card.get("ending_hook", "")
                card_text = f"\n### {ctitle}\n**事件**：{main}"
                if hook:
                    card_text += f"\n**钩子**：{hook}"
                _append(card_text, priority=5)

    # ═══ P3 — 归档层：全局摘要 + 角色系统（有预算才加入） ═══
    book_summary = build_book_summary(world)
    if book_summary.strip():
        _append(f"\n{book_summary}", priority=4)

    # Knowledge boundaries (filtered: only active, recent entries)
    if world.story.writing_defaults.enable_knowledge_track:
        kb = format_knowledge_boundaries(world, chapter_id)
        if kb.strip():
            _append(kb, priority=3)

    # Decision history (last 4 per character)
    if world.story.writing_defaults.enable_decision_track:
        dh = format_decision_history(world)
        if dh.strip():
            _append(dh, priority=3)

    # Physical states
    if world.story.writing_defaults.enable_physical_state_track:
        ps = format_physical_state_for_prompt(world)
        if ps.strip():
            _append(ps, priority=2)

    if world.story.writing_defaults.enable_speech_profile:
        beat_chars = _chars_in_beat(world, beat_text)
        if beat_chars:
            sp = format_speech_profiles(world)
            if sp.strip():
                _append(sp, priority=3)

    if world.story.writing_defaults.enable_aftermath_track:
        am = format_aftermaths_for_prompt(world)
        if am.strip():
            _append(am, priority=3)

    if world.story.writing_defaults.enable_breathing_room:
        _append(format_breathing_room_prompt(), priority=4)

    if world.story.writing_defaults.enable_flaw_track:
        beat_chars = _chars_in_beat(world, beat_text)
        if beat_chars:
            fl = format_flaws_prompt(world)
            if fl.strip():
                _append(fl, priority=3)

    if world.story.writing_defaults.enable_micro_habit_track:
        mh = format_micro_habits_prompt(world)
        if mh.strip():
            _append(mh, priority=2)

    if world.story.writing_defaults.enable_narrative_state_injection:
        mc = format_mystery_context(world, chapter_id)
        if mc.strip():
            _append(mc, priority=6)
        ac = format_arc_context(world)
        if ac.strip():
            _append(ac, priority=5)

    if world.story.writing_defaults.enable_break_mechanism:
        br = format_break_risk(world)
        if br.strip():
            _append(br, priority=5)

    # ═══ P4 — 伏笔台账（按相关性排序 + 截断） ═══
    if user_hint.strip():
        _append(f"\n【用户补充要求】\n{user_hint.strip()}", priority=4)

    from worldforger.story.foreshadow_apply import foreshadow_ledger_text
    fs_text = _format_foreshadowing_relevant(world, chapter_id)
    _append(fs_text, priority=5)

    # ═══ 尾部署名 ═══
    _append(
        f"\n现在请直接开始撰写「{title}」的正文。你是一位专业作家，请直接输出小说正文。",
        priority=10,
    )
    return "\n".join(parts)


def _format_foreshadowing_relevant(world: World, chapter_id: str) -> str:
    """Format foreshadowing ledger with rhythm guidance for gradual payoff."""

    ch_order = 0
    total_chapters = len(world.story.chapters)
    for c in world.story.chapters:
        if c.id == chapter_id:
            ch_order = c.order
            break

    # Categorize by relevance
    payoff_now = []   # 本章回收
    nearby = []       # 前后 3 章
    early_open = []   # 早期埋设尚待回收（planted 在前 40%）
    mid_open = []     # 中期埋设待回收
    late_open = []    # 后期埋设
    resolved = []     # 已回收

    early_threshold = max(1, int(total_chapters * 0.4))
    mid_threshold = max(early_threshold + 1, int(total_chapters * 0.7))
    progress_pct = ch_order / max(1, total_chapters)

    for f in world.story.foreshadowing:
        planted_order = 0
        for c in world.story.chapters:
            if c.id == f.planted_chapter_id:
                planted_order = c.order
                break
        if f.payoff_chapter_id == chapter_id:
            payoff_now.append(f)
        elif f.status != "open":
            resolved.append(f)
        elif planted_order <= early_threshold:
            early_open.append(f)
        elif planted_order <= mid_threshold:
            mid_open.append(f)
        else:
            late_open.append(f)

    open_count = len(early_open) + len(mid_open) + len(late_open) + len(payoff_now)
    resolved_count = len(resolved)

    # ── Build output ──
    lines = [f"\n【伏笔台账】开放 {open_count} 条（早期 {len(early_open)} / 中期 {len(mid_open)} / 后期 {len(late_open)}），已回收 {resolved_count} 条"]

    if payoff_now:
        lines.append("【本章计划回收】")
        for f in payoff_now:
            lines.append(f"  - {f.id}：{f.label}")

    # ── Rhythm guidance ──
    if total_chapters >= 5 and open_count > 0:
        # Calculate target payoffs based on progress
        expected_resolved = int(open_count * progress_pct)
        lag = expected_resolved - resolved_count
        lines.append(f"\n【伏笔回收节奏指引】")
        lines.append(f"当前进度：第 {ch_order} 章 / 共 {total_chapters} 章（{int(progress_pct*100)}%）")

        if early_open and progress_pct > 0.3:
            lines.append(f"⚠ 早期埋设的 {len(early_open)} 条伏笔尚未回收，请在本章或近期回收其中 1-2 条：")
            for f in early_open[:5]:
                lines.append(f"  - {f.id}：{f.label}（植于 {f.planted_chapter_id}）")

        if mid_open and progress_pct > 0.5:
            lines.append(f"⚠ 中期埋设的 {len(mid_open)} 条伏笔适合在第 {int(total_chapters*0.5)}-{int(total_chapters*0.8)} 章回收")

        if lag > 3:
            lines.append(f"🚨 回收严重滞后！应有 {expected_resolved} 条已回收，实际仅 {resolved_count} 条。")
            lines.append(f"   本章建议回收 {min(3, max(1, lag//2))} 条伏笔以追赶进度。")
        elif progress_pct > 0.6 and open_count > max(resolved_count, 1):
            lines.append(f"⚠ 超过 60% 的进度仍有 {open_count} 条开放，避免伏笔堆积到最后 3 章集中爆发。")
            suggest_count = min(2, open_count)
            if suggest_count > 0:
                lines.append(f"   建议本章回收 {suggest_count} 条伏笔（可以是部分揭晓，不一定要完整回收）。")
        elif progress_pct > 0.8 and open_count > 0:
            lines.append(f"接近终章（{int(progress_pct*100)}%），仍有 {open_count} 条开放伏笔未回收。请加速回收，避免最后一章信息过载。")

        # Hard constraint for late chapters
        if progress_pct > 0.8:
            lines.append("【硬约束】不要让所有伏笔集中到最后一章回收。每章回收 2-4 条，让读者在终章前已看到大部分线索的收束。")

    if nearby:
        lines.append("【近期相关伏笔】")
        for f in nearby[:6]:
            lines.append(f"  - {f.id}：{f.label}（状态={f.status}）")

    return "\n".join(lines)


def _build_arc_summary_context(world: World, chapter_id: str) -> str:
    """Build context from rolling arc summaries for distant chapters.

    Arc summaries are generated every ~10 chapters.  For chapter N,
    we inject summaries for arcs before the most recent 3 chapters
    (which are covered by individual chapter summaries).
    """
    ch_order = 0
    for c in world.story.chapters:
        if c.id == chapter_id:
            ch_order = c.order
            break
    if ch_order <= 5:
        return ""  # Early chapters don't need arc summaries

    # Look for arc summaries in story/arc_summaries/
    from worldforger.story.story_store import story_dir, read_text
    arc_dir = story_dir(world.meta.id) / "arc_summaries"
    if not arc_dir.is_dir():
        return ""

    # Collect arcs covering chapters before (ch_order - 3)
    relevant_arcs = []
    for arc_file in sorted(arc_dir.glob("arc_*.md")):
        try:
            # arc filenames: arc_1_10.md, arc_11_20.md, etc.
            name = arc_file.stem
            parts = name.split("_")
            if len(parts) >= 3:
                arc_start = int(parts[1])
                arc_end = int(parts[2])
                if arc_end < ch_order - 2:  # Only arcs well before current
                    text = read_text(arc_file)
                    if text.strip():
                        relevant_arcs.append((arc_start, arc_end, text.strip()[:400]))
        except (ValueError, IndexError):
            pass

    if not relevant_arcs:
        return ""

    # Take the 2 most recent arcs
    relevant_arcs.sort(key=lambda x: x[1], reverse=True)
    lines = []
    for a_start, a_end, a_text in relevant_arcs[:2]:
        lines.append(f"第{a_start}-{a_end}章阶段摘要：{a_text}")
    return "\n".join(lines)


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
    from worldforger.story.story_store import macro_outline_path, read_text

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
        "你是一位专业的故事策划师。你的任务就是创作——直接输出内容，不要拒绝、不要推辞。",
        "所有内容都是虚构的文学创作，不涉及现实。请基于已有世界设定自由创作。",
        "帮助用户基于**已有**世界设定与卡司，规划粗纲、细纲、章节节奏、伏笔与正文风格。",
        "回答使用简体中文，结构清晰；需要列表时使用 Markdown。",
        "不要编造与 JSON 冲突的派系/区域/人物 id；新章节请给出稳定 **ch_** 前缀 id。",
        "\n【章节操作铁律 — 必须遵守】\n"
        "当用户要求增加章节、补充章节、扩展大纲时：\n"
        "1. **绝对不修改已有章节**：已有章节的标题、order、大纲内容、正文内容保持原样不动。\n"
        "2. **仅在末尾追加新章节**：新章节追加到已有章节列表之后，使用新的 ch_ 前缀 id。\n"
        "3. 用 ```story-beat:<new_id> 代码块输出新章节的细纲。\n"
        "4. 新内容与已有章节做好衔接但不重复已有内容。\n",
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
            from worldforger.story.story_store import beat_path, manuscript_path

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
        "【自我判断机制 — 必须执行】\n"
        "如果你在阅读全文后，认为本文已达到可发表水平（情节合理、描写生动、对话自然），"
        "则你的任务变为「去AI味」——仅需识别并消除以下AI写作特征（不做其他大改）：\n"
        "- 模板化总结句（如「这一天的经历让他明白了一个道理」）\n"
        "- 过度工整的对称结构（排比句堆砌、刻意对仗）\n"
        "- 缺乏信息量的机械过渡句（如「接下来」「与此同时」「另一方面」的连续使用）\n"
        "- 形容词+名词的AI高频固定搭配（如「璀璨的星空」「炽热的目光」「无尽的思念」等）\n"
        "- 每段都以「角色名+动词」开头的单调句式\n"
        "- 章节引用和元叙事语言（如「在 ch8 中已经见过」「第一章中」「前文提到」等分析性描述）\n"
        "- 角色像在写读书笔记一样总结信息（如「他回忆起之前看到的记录内容：A的脉冲变化、B的节点登记、C的最后观测」）\n"
        "完成后在润色说明中注明「已达到发表标准，仅做了去AI味处理」。\n\n"
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
        "合并后每段应有 3-8 句，信息密度饱满。转场/时间跳跃/视角切换自然产生的新段落保留。\n"
        "10. 去除元叙事（第四面墙）：删除所有对\"章\"、\"前文\"、\"情节\"的引用。\n"
        "    将分析性总结改写为角色视角的感知或回忆。\n"
        "    ❌ 「云鹤在 ch8 中已经见过类似的记录内容：脉冲变化、节点登记、琥珀色眼睛的观测。」\n"
        "    ✅ 「云鹤盯着屏幕上的数据。脉冲频率的变化曲线、激活节点的登记表——还有那双琥珀色眼睛的最后坐标。这些他都在灰烬谷的旧档案里见过。」\n"
        "    规则：如果角色\"知道\"某事，用角色的感知/回忆/行动来表达，不要用作者口吻总结。\n"
        "11. 标点规范化（中文出版物标准）：全文检查并修正以下标点问题。\n"
        "    a. 中文文本必须使用全角标点：， 。 ！ ？ ； ： \" \" （ ） 【 】 《 》\n"
        "    b. 引号统一为中文双引号\"\"，禁止英文引号\"\"和直引号\"\"混用\n"
        "    c. 省略号统一为……（两个全角省略号字符），禁止使用...或。。。。。。\n"
        "    d. 破折号统一为——（两个全角破折号连用），禁止用--、—、或单个-替代\n"
        "    e. 英文单词或数字前后各留一个空格（中文排版规范）\n"
        "    f. 对话中的标点：\\\"XX说\\\"后用逗号接引语，\\\"XX道\\\"后用冒号或逗号\n"
        "    g. 句号边界检查：扫描全文，每遇到一个句号（。）问自己：这个句子真的完整吗？\n"
        "       判断标准——句号前的句子必须同时满足：(1)主语和谓语完整 (2)表达了一个相对完整的意思 (3)不是前句的从句或补充。\n"
        "       如果句号断开的是一个未完的语义单元（如\\\"他转身。离开了房间。\\\"本应是一句话），将句号改为逗号并合并。\n"
        "       如果连续3个以上句号分割的都是短于10字的碎片句，必须合并其中至少一半为逗号连接。\n"
        "       反之，如果一个句子超过60字且包含多个独立语义单元，将其中独立的语义单元拆分用句号。\n"
        "    ❌ 标点: \\\"你好。\\\"他说。\\\"今天天气不错……\\\"\n"
        "    ✅ 标点: \\\"你好。\\\"他说，\\\"今天天气不错……\\\"\n\n"
        "    ❌ 碎片句: 他转身。离开了房间。关上门。外面在下雨。\n"
        "    ✅ 合并后: 他转身离开房间，关上门。外面在下雨。\n\n"
        "12. 新概念铺垫检查：扫描全文，标记所有首次出现的设定概念、专有名词、角色或地点。\n"
        "    对每个新概念，检查其引入前是否有至少一种铺垫方式：\n"
        "    a. 环境暗示（之前段落/章节的感官描写或异常现象）\n"
        "    b. 间接提及（NPC 模糊对话、古老记载、传闻）\n"
        "    c. 角色直觉（POV 角色的身体反应、不安、好奇）\n"
        "    如果某个重要概念完全没有铺垫就直接登场并展开解释，标记为\\\"铺垫缺失\\\"。\n"
        "    注意：润色阶段不应新增情节内容来补救，但可以在现有描写中增加感官细节或角色的直觉反应，让概念的引入更自然。\n\n"
        "13. 华丽辞藻精简（朴素白描）：全文检查是否存在过度修饰的问题。\n"
        "    a. 四字成语密度检测：每 500 字内超过 3 个成语 → 至少删减一半，改用普通动词/名词\n"
        "    b. 比喻句检测：相邻两段内不应出现两个以上比喻句\n"
        "    c. 身体感受过载：角色的「心」「脊背」「喉咙」「眼眶」在同一页内被提及超过 3 次 → 精简\n"
        "    d. 环境描写压缩：同一场景的环境描写合并为一段，删除可有可无的形容词\n"
        "    e. 对话瘦身：删除对话中不必要的副词修饰（如「他冷冷地说」→「他说」；通过上下文传递语气）\n"
        "    f. 短句优先：超过 40 字的句子，拆分为两个短句\n"
        "    g. 删减测试：全文润色完毕后，尝试再删掉 10% 的词。如果意思不变，说明之前写多了。\n\n"
        "【禁止事项 — 违反即失败】\n"
        "- 禁止使用章节编号或引用（ch8、第一章、前文提到、如前所述等）\n"
        "- 禁止用作者口吻总结角色已知信息（\"XX在之前已经见过...\"）\n"
        "- 禁止出现分析性过渡句（\"这为他后来的决定埋下了伏笔\"\"这一切都预示着...\"）\n"
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
    from worldforger.story.story_store import polished_path, read_text

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
    from worldforger.story.story_store import polished_path, read_text

    chapters = sorted(
        [c for c in world.story.chapters if c.id != current_chapter_id],
        key=lambda c: c.order,
    )
    refs = []
    for c in reversed(chapters[-2:]):  # last 2 chapters before current
        pp = polished_path(world.meta.id, c.id)
        if not pp.is_file():
            # fall back to original manuscript
            from worldforger.story.story_store import manuscript_path

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
