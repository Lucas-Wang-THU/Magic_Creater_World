"""情节对话：工具调用 + 对话后自动落盘伏笔/Markdown 块。"""

from __future__ import annotations

import json
from typing import Any

from worldforger.foreshadow_apply import apply_foreshadow_operations, foreshadow_ledger_text
from worldforger.llm import chat_completion_with_tools
from worldforger.schemas import StoryPerson, World
from worldforger.story_chat_artifacts import auto_apply_story_artifacts_from_reply
from worldforger.story_prompts import story_chat_system_prompt
from worldforger.story_service import generate_manuscript
from worldforger.world_store import save_world

STORY_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_foreshadowing",
            "description": "列出当前世界的伏笔台账，可按章节或状态筛选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter_id": {
                        "type": "string",
                        "description": "仅返回与该章埋设/回收相关的伏笔；空则全部",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["open", "partial", "resolved", "all"],
                        "description": "筛选状态，默认 all",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_foreshadowing",
            "description": (
                "批量更新伏笔。operations 每项含 op: upsert|patch|resolve|delete，"
                "及 id、label、planted_chapter_id、payoff_chapter_id、status、reader_known、notes"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "operations": {
                        "type": "array",
                        "items": {"type": "object"},
                    }
                },
                "required": ["operations"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_manuscript",
            "description": (
                "根据粗纲、细纲与伏笔撰写指定章节正文并写入 manuscript 文件。"
                "当用户明确要求写正文/撰写本章/成稿时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chapter_id": {"type": "string", "description": "章节 id，须存在于 story.chapters"},
                    "extra_prompt": {
                        "type": "string",
                        "description": "额外写作要求（会与用户最近一条消息合并）",
                    },
                },
                "required": ["chapter_id"],
            },
        },
    },
]

TOOL_SYSTEM_APPEND = """
【工具与意图】
你可调用工具维护伏笔台账、撰写章节文稿。规则：
- 用户要求**写正文/撰写本章/成稿**时，优先调用 `generate_manuscript`（chapter_id 用当前选中章或用户指定 id）。
- 用户要求**埋设/回收/更新伏笔**时，调用 `apply_foreshadowing`；也可在回复末尾附 ```story-foreshadow` JSON 数组（与工具等效）。
- 粗纲/细纲/文稿长文仍可用 story-macro / story-beat:id / story-manuscript:id 代码块；系统会自动写入磁盘。
- 勿编造不存在的 chapter_id / character_id。
"""


def _last_user_message(messages: list[dict[str, str]]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return str(m.get("content") or "").strip()
    return ""


def detect_story_intent(text: str) -> str | None:
    t = (text or "").strip().lower()
    if not t:
        return None
    write_kw = ("撰写", "写正文", "成稿", "写本章", "写这一章", "生成文稿", "写稿", "正文")
    if any(k in t for k in write_kw):
        return "write_manuscript"
    fs_kw = ("伏笔", "埋设", "回收", "呼应", "揭晓")
    if any(k in t for k in fs_kw):
        return "foreshadow"
    outline_kw = ("粗纲", "细纲", "大纲", "节拍")
    if any(k in t for k in outline_kw):
        return "outline"
    return None


async def run_story_chat_agent(
    world: World,
    messages: list[dict[str, str]],
    *,
    active_chapter_id: str,
    include_story_files: bool,
    creative_mode: str | None,
    persist: bool,
    writing_prompt: str = "",
    person: StoryPerson | None = None,
    character_id: str | None = None,
    attach_prev_chapters: int | None = None,
    extra_system: list[str] | None = None,
) -> dict[str, Any]:
    wid = world.meta.id
    last_user = _last_user_message(messages)
    intent = detect_story_intent(last_user)
    actions: list[dict[str, Any]] = []

    async def execute_tool(name: str, args: dict[str, Any]) -> str:
        nonlocal world
        if name == "list_foreshadowing":
            status = str(args.get("status") or "all").strip().lower()
            cid = str(args.get("chapter_id") or active_chapter_id or "").strip()
            items = []
            for f in world.story.foreshadowing:
                if status != "all" and f.status != status:
                    continue
                if cid and f.planted_chapter_id != cid and f.payoff_chapter_id != cid:
                    continue
                items.append(f.model_dump(mode="json"))
            actions.append({"tool": name, "count": len(items)})
            return json.dumps({"foreshadowing": items}, ensure_ascii=False)

        if name == "apply_foreshadowing":
            ops = args.get("operations") or []
            if not isinstance(ops, list):
                return json.dumps({"ok": False, "error": "operations must be array"})
            world, applied, warnings = apply_foreshadow_operations(
                world, [x for x in ops if isinstance(x, dict)]
            )
            actions.append({"tool": name, "applied": applied, "warnings": warnings})
            return json.dumps(
                {"ok": True, "applied": applied, "warnings": warnings},
                ensure_ascii=False,
            )

        if name == "generate_manuscript":
            cid = str(args.get("chapter_id") or active_chapter_id or "").strip()
            if not cid:
                return json.dumps({"ok": False, "error": "chapter_id required"})
            if not any(c.id == cid for c in world.story.chapters):
                return json.dumps({"ok": False, "error": f"chapter {cid} not found"})
            extra = str(args.get("extra_prompt") or writing_prompt or "").strip()
            prompt_parts = [p for p in (last_user, extra) if p]
            prompt = "\n\n".join(prompt_parts) or "请撰写本章正文。"
            if character_id is not None:
                world.story.narrator.character_id = character_id.strip()
            attach = (
                attach_prev_chapters
                if attach_prev_chapters is not None
                else world.story.writing_defaults.attach_prev_chapters
            )
            try:
                text = await generate_manuscript(
                    world,
                    chapter_id=cid,
                    prompt=prompt,
                    creative_mode=creative_mode,
                    person=person,
                    attach_prev_chapters=attach,
                    include_world_md=world.story.writing_defaults.include_world_md,
                )
            except Exception as e:
                return json.dumps({"ok": False, "error": str(e)})
            actions.append({"tool": name, "chapter_id": cid, "chars": len(text)})
            return json.dumps(
                {"ok": True, "chapter_id": cid, "word_count": len(text), "preview": text[:400]},
                ensure_ascii=False,
            )

        return json.dumps({"ok": False, "error": f"unknown tool {name}"})

    system = story_chat_system_prompt(
        world,
        active_chapter_id=active_chapter_id,
        include_story_files=include_story_files,
    )
    system += "\n\n" + TOOL_SYSTEM_APPEND
    system += f"\n\n【伏笔台账（写作须对齐）】\n{foreshadow_ledger_text(world, chapter_id=active_chapter_id)}"
    if intent:
        system += f"\n\n【本轮意图提示】检测到用户意图偏向：{intent}"

    msgs: list[dict[str, Any]] = [{"role": "system", "content": system}]
    if extra_system:
        for s in extra_system:
            if s.strip():
                msgs.append({"role": "system", "content": s.strip()})
    for m in messages:
        msgs.append({"role": m["role"], "content": m["content"]})

    reply, tool_actions = await chat_completion_with_tools(
        msgs,
        tools=STORY_TOOLS,
        execute_tool=execute_tool,
        temperature=0.65,
        max_tokens=8192,
    )
    actions.extend(tool_actions)

    world, auto_applied, auto_warnings = auto_apply_story_artifacts_from_reply(world, reply)
    if auto_applied:
        actions.append({"auto_apply": auto_applied})
    if auto_warnings:
        actions.append({"auto_warnings": auto_warnings})

    if persist:
        save_world(world)

    return {
        "reply": reply,
        "world": world.model_dump(mode="json"),
        "actions": actions,
        "intent": intent,
        "auto_applied": auto_applied,
        "auto_warnings": auto_warnings,
    }
