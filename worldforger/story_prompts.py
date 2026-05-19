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
        "不要写完整正文。\n"
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
    data = world.model_dump(mode="json")
    for key in ("geography", "history", "factions", "characters", "cultures", "story"):
        pass
    slim = {
        "meta": data.get("meta"),
        "characters": data.get("characters"),
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


def build_manuscript_user_payload(
    world: World,
    *,
    chapter_id: str,
    macro_outline: str,
    beat_text: str,
    prev_manuscripts: list[tuple[str, str]],
    user_hint: str,
    include_world_md: bool,
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
    if prev_manuscripts:
        parts.append("\n【前文参考（保持衔接）】")
        for cid, text in prev_manuscripts:
            cht = next((c for c in world.story.chapters if c.id == cid), None)
            lab = cht.title if cht else cid
            body = text.strip()
            if len(body) > 6000:
                body = body[:6000] + "\n…(该章文稿已截断)"
            parts.append(f"\n### {lab} ({cid})\n{body}")
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
