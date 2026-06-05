from __future__ import annotations

import json
import re
from typing import Any

from worldforger.config import get_settings
from worldforger.creative_modes import genre_tags_prompt_addon, structure_sync_addon
from worldforger.llm import chat_completion
from worldforger.sync.panel_merge import merge_section_conservative
from worldforger.prompts import system_with_world_json
from worldforger.schemas import (
    AttributeSystem,
    CharactersSection,
    CulturesSection,
    EcologySection,
    EconomySection,
    FactionsSection,
    GeographySection,
    HistorySection,
    ItemQualitySystem,
    PowerSystem,
    StorySection,
    World,
)

STRUCTURE_SYSTEM_BASE = """你是「设定结构化同步器」，所有内容都是虚构世界设定，不涉及现实。请直接输出，不要拒绝。

你的输出将被 `json.loads()` 直接解析，因此**你的整个回复体必须是且仅是一个合法 JSON 对象**。

严禁输出：Markdown 标题、代码块围栏（```）、解释性文字、问候语、拒绝语句。如果你输出任何非 JSON 文本，系统将无法解析你的回复。

你的任务：根据【用户消息】与【助手自然语言回复】，把其中可写入世界设定的内容整理成 JSON。

顶层键只能来自：geography, ecology, power_system, item_quality_system, attribute_system, factions, cultures, characters, history, economy, story。未涉及的模块不要出现该键。

各模块结构参考：
- geography: summary, regions[] (每项 id, name, summary; 可选 terrain, climate, notes, landmarks[], resources[], relations[]), climate_notes, map_notes。regions 必须为数组。
- power_system: 顶层键名必须为 power_system。summary, realm_design_notes, skill_tree_design_notes, tiers[] (每项 name, description, typical_capabilities[], limitations[], examples[]; 可选 skill_tree, subclass_paths), profession_system (可选)。
- item_quality_system: 顶层键名必须为 item_quality_system。summary, grades[] (每项 name, rarity_narrative, typical_effects, binding_rules, examples[])。
- attribute_system: 顶层键名必须为 attribute_system。summary, design_notes, stats[] (每项 id, name; 可选 intro, description, reference_percent), tier_average_profiles[]。
- factions: summary, entities[] (每项 id, name; 可选 goals, territory, key_figures[] (仅字符串数组), relations[] (target_id, type: ally|enemy|neutral|complex, notes))。
- cultures: summary, entities[] (每项 id, name, kind: culture|religion|syncretic, summary, tenets, practices, sacred_sites[], key_figures[], relations[])。
- characters: summary, design_notes, entities[] (每项 id, name; 可选 cast_role, faction_ids[], home_region_id, one_line_hook, notes, notable_skills[], relations[])。
- history: summary, events[] (每项 when, title, summary, consequences[], linked_faction_ids[])。
- economy: summary, design_notes, currencies[], markets[], trade_routes[], trade_goods[], labor_notes, taxation_notes, volatility_notes。
- ecology: summary, design_notes, biomes[] (每项 id, name, summary, linked_region_ids[]), species[] (每项 id, name, biome_id, traits[], notable_skills[])。
- story: summary, design_notes, chapters[] (id, order, title, status), foreshadowing[] (id, label, planted_chapter_id, status), narrator, writing_defaults。

合并规则：
- 从【当前 world.json】复制该节，再写入本轮变更。没有变化的字段完全省略，禁止输出 "" 或 [] 占位。
- 数组有更新时输出合并后的完整数组（旧条目 + 新条目），不要只输出新增条目。
- 若没有任何可落盘设定，输出 {}。
- 多模块同答时在同一个 JSON 里输出多个顶层键。
- 不要修改 meta（id、name、version）。

关键约束：
- factions.entities[].relations[].type 只能是 ally|enemy|neutral|complex
- factions.entities[].key_figures 只能是字符串数组，禁止对象数组
- 所有 entities 字段必须为数组，单条也须 [{...}]
- 区域间关系用 relations，target_id 指向对方 id

牢记：你的**整个回复**必须以 `{` 开头，以 `}` 结尾。不要输出任何其他内容。"""


FORMAT_PROOFREADER_SYSTEM = """你是「JSON 格式校对者」。你的唯一任务是修复 JSON 语法错误，使文本变为合法 JSON。

输入：
- 一段包含 JSON 的文本（可能包裹在 ```json``` 代码块中，也可能前后有多余文字）
- json.loads 报错信息（包含行号、列号、字符偏移）

硬性规则：
1. 只输出修正后的合法 JSON 对象（不要代码块、不要解释），确保 json.loads 可以无报错解析
2. 保持所有字段名、字段值、嵌套结构完全不变——只修复语法错误，不增删改内容
3. 常见需修复问题（按频率排序）：
   a. 缺少逗号：{"a": 1\n"b": 2} → {"a": 1,\n"b": 2}
   b. 多余逗号：{"a": 1,} → {"a": 1}；[1, 2,] → [1, 2]
   c. 单引号替代双引号：{'a': 'b'} → {"a": "b"}
   d. 字符串内含未转义双引号："title": "He said "hello"" → "title": "He said \\"hello\\""
   e. 字符串内含换行符：多行字符串值应转义为 \\n
   f. // 或 /* */ 注释
   g. JSON 前后的解释性句子（去除即可）
4. 若文本完全无法识别为 JSON（如纯自然语言、无任何 { } 结构），输出：{"_format_error": true, "reason": "具体说明"}
5. 若修复后 JSON 依然无法通过 json.loads 校验，也输出 _format_error 对象并说明原因"""


PROOFREADER_SYSTEM = """你是「设定校对者」，与负责自然语言创作的「世界观架构师」及负责 JSON 提取的「结构化同步器」是不同角色。
你的唯一任务：对比【架构师自然语言回复】与【同步器提取的 JSON patch】，检查同步器是否**完整捕获**了架构师回复中的**所有新增/修改的设定**。

硬性规则：
1. 只输出**一个** JSON 对象，不要输出任何 JSON 以外的文字。
2. 逐模块对比：架构师回复中提到的每个设定模块（地理/生态/境界/物品/属性/派系/文化/角色/历史/经济/情节），同步器 JSON 中是否有对应条目。
3. 数组条目计数：若架构师回复中提到 N 个实体（如 N 个派系、N 种货币、N 个职业），同步器 JSON 中应至少包含 N 个条目。
4. 字段完整性：每个条目的核心字段（如 name、summary、description）是否已填充有意义的非空值。
5. 不要求逐字一致：语义等价即可通过。架构师的文学性描述与同步器的结构化表述只要含义相同就视为覆盖。
6. 若发现遗漏或明显不完整，verdict 设为 "retry"，并在 supplement_patch 中**直接输出**遗漏部分的完整 JSON（与同步器相同的结构），**不要输出自然语言问题**。你应当参考【当前 world.json】和【架构师自然语言回复】，直接构造遗漏的设定 JSON。
7. 若审查通过，verdict 设为 "ok"。

【叙事知识边界检查 — 极其重要】
- 检查角色设定中是否出现了超出当前章节时间线的内容（如第1章的角色描述提到了第5章的事件）。
- 检查角色是否被赋予了ta在当前章不应知道的信息。
- 如果发现"上帝视角"信息泄露（如角色内心写着写着变成了全知叙述者），标注为严重问题。

输出格式：
{
  "verdict": "ok" | "retry",
  "missing": ["描述每条遗漏或缺陷"],
  "supplement_patch": { ... }  // 仅在 verdict="retry" 时输出，结构与同步器 JSON patch 一致
}
"""


def _proofreader_model_name() -> str:
    s = get_settings()
    m = s.proofreader_model.strip()
    if m:
        return m
    return _structure_model_name()


def structure_system_for_scope(scope: str | None) -> str:
    if not scope or scope == "all":
        return STRUCTURE_SYSTEM_BASE
    allowed = {
        "geography",
        "ecology",
        "power_system",
        "item_quality_system",
        "attribute_system",
        "factions",
        "cultures",
        "characters",
        "history",
        "economy",
        "story",
    }
    if scope not in allowed:
        return STRUCTURE_SYSTEM_BASE
    extra = ""
    if scope == "factions":
        extra = (
            " **factions 专规（本轮）**：根下 **entities** 必须为数组；每条 **relations[].type** 只能是英文 "
            "**ally|enemy|neutral|complex**；**key_figures** 只能是字符串数组；**target_id** 须为已有或本轮一并给出的派系 **id**。"
        )
    return (
        STRUCTURE_SYSTEM_BASE
        + f"\n10. **本轮同步范围**：只输出顶层键 `{scope}`，禁止输出其它顶层键；若本轮与 `{scope}` 无关则输出 {{}}。"
        + extra
    )


def _structure_model_name() -> str:
    s = get_settings()
    m = s.structure_sync_model.strip()
    return m or s.openai_chat_model


def _json_size(v: Any) -> int:
    if isinstance(v, dict):
        return sum(_json_size(sv) for sv in v.values())
    if isinstance(v, list):
        return len(v)
    if isinstance(v, str):
        return len(v)
    return 1


def _strip_code_fence(text: str) -> str:
    """Remove markdown code fences around JSON content.

    Handles both outer-fenced (```json...```) and inline-fenced
    (# Markdown...```json{...}```) patterns by extracting the largest
    JSON-like block.
    """
    t = text.strip()
    # Case 1: entire text is a fenced code block
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
        return t.strip()
    # Case 2: markdown with embedded ```json ... ``` block — extract it
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.DOTALL)
    if m:
        return m.group(1).strip()
    return t.strip()


def parse_structure_json(raw: str) -> dict[str, Any]:
    t = _strip_code_fence(raw)
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no json object in model output")
    segment = t[start : end + 1]
    # Try progressively more aggressive repairs (common LLM JSON mistakes)
    attempts = [
        segment,                                    # 1. standard
        _strip_json_comments(segment),              # 2. strip // comments
        _strip_trailing_commas(segment),            # 3. trailing commas
        _fix_missing_commas(segment),               # 4. missing commas
        _fix_missing_commas(_strip_trailing_commas(segment)),         # 5. both fixes
        _fix_missing_commas(_strip_json_comments(segment)),           # 6. comments + commas
        _fix_missing_commas(_strip_trailing_commas(_strip_json_comments(segment))),  # 7. all fixes
    ]
    for i, attempt in enumerate(attempts):
        try:
            result = json.loads(attempt)
            if i > 0:
                print(f"[MCW-SYNC] JSON repaired with strategy #{i + 1}")
            return result
        except json.JSONDecodeError:
            continue
    # Last resort: try extracting top-level keys individually
    result = _extract_top_level_keys(segment)
    if result:
        print("[MCW-SYNC] JSON recovered via per-key extraction")
        return result
    raise ValueError(f"no json object in model output (tried {len(attempts)} repair strategies)")


def _salvage_partial_json(text: str) -> dict[str, Any]:
    """Attempt to salvage a truncated JSON object by auto-closing unclosed braces/brackets.

    When the LLM output is truncated mid-JSON (e.g. at max_tokens limit), this tries
    progressively more aggressive repairs to recover whatever valid data we can.
    """
    t = _strip_code_fence(text)
    start = t.find("{")
    if start == -1:
        raise ValueError("no JSON object start found in truncated output")
    segment = t[start:]

    # Strategy 1: auto-close unclosed braces and brackets
    repaired = _auto_close_json(segment)
    for attempt in [repaired, _strip_trailing_commas(repaired), _fix_missing_commas(repaired)]:
        try:
            result = json.loads(attempt)
            print("[MCW-SYNC] Salvage: auto-closed truncated JSON successfully")
            return result
        except json.JSONDecodeError:
            continue

    # Strategy 2: truncation mid-string — try closing the last string then auto-close
    if segment.rstrip()[-1:] not in ("}", "]", '"'):
        repaired2 = _auto_close_json(segment.rstrip() + '"')
        try:
            result = json.loads(repaired2)
            print("[MCW-SYNC] Salvage: closed mid-string truncation successfully")
            return result
        except json.JSONDecodeError:
            pass

    # Strategy 3: remove likely-incomplete last key-value pair and try again
    repaired3 = _auto_close_json(_trim_incomplete_entry(segment))
    for attempt in [repaired3, _strip_trailing_commas(repaired3)]:
        try:
            result = json.loads(attempt)
            print("[MCW-SYNC] Salvage: trimmed incomplete trailing entry successfully")
            return result
        except json.JSONDecodeError:
            continue

    # Strategy 4: per-key extraction as last resort
    result = _extract_top_level_keys(segment)
    if result:
        print("[MCW-SYNC] Salvage: recovered via per-key extraction from truncated output")
        return result

    raise ValueError("all salvage strategies failed on truncated output")


def _auto_close_json(text: str) -> str:
    """Count open/close braces and brackets, append missing closers."""
    depth_brace = 0
    depth_bracket = 0
    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not in_string:
            in_string = True
        elif ch == '"' and in_string:
            in_string = False
        elif in_string:
            continue
        elif ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace -= 1
        elif ch == "[":
            depth_bracket += 1
        elif ch == "]":
            depth_bracket -= 1
    closers = "]" * max(0, depth_bracket) + "}" * max(0, depth_brace)
    return text.rstrip() + closers


def _trim_incomplete_entry(text: str) -> str:
    """Remove a trailing incomplete JSON key or key-value pair (likely truncated)."""
    # Remove trailing comma and whitespace first
    t = text.rstrip().rstrip(",").rstrip()
    # Find last complete entry: look for the last comma or { that precedes a complete value
    # Strategy: find the last "key": that is followed by an incomplete value
    # We remove everything after the last safely-identifiable complete key-value boundary
    # Simply: find last comma that's at a reasonable depth, and trim after it
    in_string = False
    escape = False
    depth = 0
    last_safe_comma = -1
    for i, ch in enumerate(t):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not in_string:
            in_string = True
        elif ch == '"' and in_string:
            in_string = False
        elif in_string:
            continue
        elif ch in ("{", "["):
            depth += 1
        elif ch in ("}", "]"):
            depth -= 1
        elif ch == "," and depth == 0:
            last_safe_comma = i
    if last_safe_comma > 0:
        return t[:last_safe_comma]
    # If no safe comma, just return the opening brace — we'll get an empty dict
    brace_idx = t.find("{")
    return t[:brace_idx + 1] if brace_idx != -1 else "{}"


def _strip_json_comments(text: str) -> str:
    """Remove // line comments from JSON text."""
    import re as _re
    return _re.sub(r"//[^\n]*", "", text)


def _strip_trailing_commas(text: str) -> str:
    """Remove trailing commas before ] or } — a common LLM JSON mistake."""
    import re as _re
    return _re.sub(r",\s*([}\]])", r"\1", text)


def _fix_missing_commas(text: str) -> str:
    """Insert missing commas between JSON values — handles LLM formatting mistakes.

    Uses a simple state machine: when a JSON value ends (string close, }, ], number,
    true/false/null) and the next non-whitespace char starts a new value, insert comma.
    """
    import re as _re

    VALUE_ENDERS = {'"', "}", "]"}  # chars that can end a JSON value
    DIGIT_STARTERS = set("0123456789-")
    # After a string end not preceded by backslash
    t = text
    # Pattern: " (not escaped) followed by optional whitespace followed by " (new key/value)
    t = _re.sub(r'(?<!\\)"(\s*)(?=")', r'",\1', t)
    # Pattern: } followed by optional whitespace followed by " or {
    t = _re.sub(r'}(\s*)(?=")', r'},\1', t)
    t = _re.sub(r'}(\s*)(?=\{)', r'},\1', t)
    # Pattern: ] followed by optional whitespace followed by " or {
    t = _re.sub(r'](\s*)(?=")', r'],\1', t)
    t = _re.sub(r'](\s*)(?=\{)', r'],\1', t)
    # Pattern: number literal (must be preceded by JSON structural char, not inside string)
    # JSON_NUMBER_CTX = lookbehind for : [ { , or whitespace (not a letter/digit inside string)
    t = _re.sub(r'(?<=[\s:\[,\{])(\d+)(\s*)(?=")', r'\1,\2', t)
    t = _re.sub(r'(?<=[\s:\[,\{])(\d+)(\s*)(?=\{)', r'\1,\2', t)
    # Pattern: true/false/null literal (must be preceded by JSON structural char)
    t = _re.sub(r'(?<=[\s:\[,\{])(true|false|null)(\s*)(?=")', r'\1,\2', t)
    t = _re.sub(r'(?<=[\s:\[,\{])(true|false|null)(\s*)(?=\{)', r'\1,\2', t)
    # Pattern:  } or ] followed by [ (array of objects)
    t = _re.sub(r'([}\]])(\s*)(?=\[)', r'\1,\2', t)
    # Pattern: number literal followed by [ (array start)
    t = _re.sub(r'(?<=[\s:\[,\{])(\d+)(\s*)(?=\[)', r'\1,\2', t)
    return t


def _extract_top_level_keys(segment: str) -> dict[str, Any]:
    """Fallback: extract each known top-level key individually from malformed JSON."""
    known_keys = [
        "geography", "ecology", "power_system", "item_quality_system",
        "attribute_system", "factions", "cultures", "characters",
        "history", "economy", "story",
    ]
    result: dict[str, Any] = {}
    for key in known_keys:
        # Look for "key": { ... } in the segment
        pattern = re.compile(
            r'"' + re.escape(key) + r'"\s*:\s*\{',
        )
        m = pattern.search(segment)
        if not m:
            continue
        val_start = m.end() - 1  # position of {
        # Find matching }
        depth = 0
        val_end = val_start
        for i in range(val_start, len(segment)):
            ch = segment[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    val_end = i + 1
                    break
        if depth != 0:
            continue  # unbalanced braces, skip this key
        val_segment = segment[val_start:val_end]
        # Try to parse the value
        for fix_fn in (lambda x: x, _strip_trailing_commas, _fix_missing_commas):
            try:
                result[key] = json.loads(fix_fn(val_segment))
                break
            except json.JSONDecodeError:
                continue
    return result


def apply_structure_patch(
    world: World, patch: dict[str, Any]
) -> tuple[World, list[str], list[str], dict[str, list[str]]]:
    """Merge patch into world. Returns (new_world, updated_keys, merge_warnings, normalize_notes)."""
    from worldforger.sync.panel_merge import merge_section_conservative
    from worldforger.sync.patch_validator import validate_patch_constraints
    from worldforger.sync.structure_normalize import normalize_structure_patch_detailed

    patch, normalize_notes = normalize_structure_patch_detailed(patch)
    # Code-level constraint validation — safety net below the prompt layer
    constraint_warnings = validate_patch_constraints(patch)
    for w in constraint_warnings:
        print(f"[MCW-VALIDATE] {w}")
    data = world.model_dump(mode="json")
    updated: list[str] = []
    warnings: list[str] = list(constraint_warnings)  # start with constraint violations
    allowed = {
        "geography": GeographySection,
        "ecology": EcologySection,
        "power_system": PowerSystem,
        "item_quality_system": ItemQualitySystem,
        "attribute_system": AttributeSystem,
        "factions": FactionsSection,
        "cultures": CulturesSection,
        "characters": CharactersSection,
        "history": HistorySection,
        "economy": EconomySection,
        "story": StorySection,
    }
    for key, model_cls in allowed.items():
        if key not in patch or not isinstance(patch[key], dict):
            continue
        merged_dict = merge_section_conservative(data[key], patch[key])
        try:
            data[key] = model_cls.model_validate(merged_dict).model_dump(mode="json")
            updated.append(key)
        except Exception as e:
            warnings.append(f"{key}: {e}")
            continue
    new_world = World.model_validate(data)
    return new_world, updated, warnings, normalize_notes


async def _run_proofreader(
    *,
    architect_reply: str,
    patch: dict[str, Any],
    world_json: str,
) -> dict[str, Any]:
    """校对者 LLM：检查同步器 JSON patch 是否完整覆盖架构师回复。"""
    patch_json = json.dumps(patch, ensure_ascii=False, indent=2)
    user_block = (
        "【当前 world.json】\n"
        + world_json
        + "\n\n【架构师自然语言回复】\n"
        + architect_reply.strip()
        + "\n\n【同步器提取的 JSON patch】\n"
        + patch_json
    )
    raw = await chat_completion(
        [
            {"role": "system", "content": PROOFREADER_SYSTEM},
            {"role": "user", "content": user_block},
        ],
        model=_proofreader_model_name(),
        temperature=0.05,
        max_tokens=4096,
    )
    return parse_structure_json(raw)


async def _run_format_proofreader(
    *,
    raw_json_text: str,
    parse_error: str,
) -> dict[str, Any]:
    """Stage 1: 格式校对者 LLM — 修复同步器输出的 JSON 语法错误。

    返回修复后解析出的 dict；若格式校对者也失败，返回含 _format_error 的 dict。
    """
    user_block = (
        "【原始文本】\n"
        + raw_json_text[:16000]
        + "\n\n【json.loads 报错】\n"
        + parse_error
    )
    raw = await chat_completion(
        [
            {"role": "system", "content": FORMAT_PROOFREADER_SYSTEM},
            {"role": "user", "content": user_block},
        ],
        model=_structure_model_name(),
        temperature=0.0,
        max_tokens=32768,
    )
    print(f"[MCW-SYNC] Format proofreader raw output length: {len(raw)} chars")
    try:
        result = parse_structure_json(raw)
        if isinstance(result, dict) and result.get("_format_error"):
            print(f"[MCW-SYNC] Format proofreader reported error: {result.get('reason', 'unknown')}")
        else:
            print(f"[MCW-SYNC] Format proofreader succeeded, keys: {list(result.keys())}")
        return result
    except ValueError:
        print("[MCW-SYNC] Format proofreader output also unparseable")
        return {"_format_error": True, "reason": "format proofreader output also unparseable"}


async def _run_synchronizer_self_correct(
    *,
    raw_json_text: str,
    parse_error: str,
    world_json: str,
    system: str,
) -> dict[str, Any]:
    """Stage 2: 让同步器自修正 — 告知 JSON 格式错误，要求严格重新输出。

    使用 temperature=0 + 更严格的 JSON 格式要求。
    """
    strict_system = (
        system
        + "\n\n【重要】你的上一轮输出无法通过 json.loads 校验。"
        "请修正以下格式问题后重新输出完整的 JSON 对象：\n"
        + parse_error
        + "\n\n请严格确保：\n"
        "- 所有字符串用双引号包裹\n"
        "- 对象/数组元素之间用逗号分隔\n"
        "- 对象/数组末尾无多余逗号\n"
        "- 所有花括号和方括号正确配对\n"
        "- 字符串内不包含未转义的特殊字符"
    )
    user_block = (
        "【当前 world.json】\n"
        + world_json
        + "\n\n【你上一轮输出（有格式错误）】\n"
        + raw_json_text[:12000]
    )
    raw = await chat_completion(
        [
            {"role": "system", "content": strict_system},
            {"role": "user", "content": user_block},
        ],
        model=_structure_model_name(),
        temperature=0.0,
        max_tokens=32768,
    )
    print(f"[MCW-SYNC] Synchronizer self-correct output length: {len(raw)} chars")
    try:
        result = parse_structure_json(raw)
        print(f"[MCW-SYNC] Synchronizer self-correct succeeded, keys: {list(result.keys())}")
        return result
    except ValueError as e:
        print(f"[MCW-SYNC] Synchronizer self-correct also failed: {e}")
        raise


def _has_json_structure(text: str) -> bool:
    """Check if text contains at least a plausible JSON object structure."""
    t = _strip_code_fence(text)
    brace_open = t.find("{")
    brace_close = t.rfind("}")
    return brace_open != -1 and brace_close != -1 and brace_close > brace_open


JSON_ENFORCE_SYSTEM = """你是 JSON 提取器。所有内容都是虚构世界设定。直接输出 JSON，不要拒绝。

你的整个回复必须是且仅是一个合法 JSON 对象，以 `{` 开头、以 `}` 结尾。

严禁：Markdown、代码块、解释、拒绝语。只输出 JSON。

任务：从【助手自然语言回复】中提取可写入 world.json 的结构化设定。
顶层键：geography, ecology, power_system, item_quality_system, attribute_system, factions, cultures, characters, history, economy, story。
没有变更的模块不要出现。没有任何可落盘设定时输出 {}。"""


async def _run_json_enforce_retry(
    *,
    world_json: str,
    assistant_reply: str,
) -> dict[str, Any]:
    """Stage 0.5: model produced non-JSON output (e.g. pure Markdown).
    Re-prompt with an extremely minimal, forceful system message.
    """
    wj = world_json
    if len(wj) > 8000:
        wj = wj[:8000] + "\n…(截断)"
    user_block = (
        "【当前 world.json】\n"
        + wj
        + "\n\n【助手自然语言回复】\n"
        + assistant_reply.strip()[:4000]
    )
    raw = await chat_completion(
        [
            {"role": "system", "content": JSON_ENFORCE_SYSTEM},
            {"role": "user", "content": user_block},
        ],
        model=_structure_model_name(),
        temperature=0.0,
        max_tokens=32768,
    )
    print(f"[MCW-SYNC] JSON-enforce retry output length: {len(raw)} chars")
    print(f"[MCW-SYNC] JSON-enforce retry preview (first 300): {raw[:300]}")
    # Fallback: if still no JSON, return empty patch gracefully
    if not _has_json_structure(raw):
        print("[MCW-SYNC] JSON-enforce retry also produced no JSON, returning empty patch")
        return {"_format_error": True, "reason": "model refused or produced non-JSON output after retry"}
    return parse_structure_json(raw)


async def _try_parse_with_format_recovery(
    raw: str,
    *,
    world_json: str,
    system: str,
    assistant_reply: str = "",
) -> dict[str, Any]:
    """尝试解析同步器原始输出；若所有自动修复 + 逐键提取均失败，走多阶段恢复。

    Returns parsed dict. Raises ValueError only if all stages fail.
    """
    # Stage 0: non-LLM repair (7 strategies + per-key extraction)
    try:
        return parse_structure_json(raw)
    except ValueError as e0:
        parse_error = str(e0)
        print(f"[MCW-SYNC] Stage 0 (non-LLM repair) failed: {parse_error}")

    # Stage 0.5: if output has no JSON structure at all (model produced Markdown/narrative),
    # re-prompt with a minimal, forceful system message. This is cheaper and more reliable
    # than the format proofreader for this case.
    if not _has_json_structure(raw):
        print("[MCW-SYNC] Stage 0.5: no JSON structure detected, re-prompting with JSON-enforce")
        try:
            result = await _run_json_enforce_retry(
                world_json=world_json,
                assistant_reply=assistant_reply,
            )
            if isinstance(result, dict) and result.get("_format_error"):
                print("[MCW-SYNC] Stage 0.5 returned _format_error, falling through to Stage 1/2")
            else:
                return result
        except ValueError as e05:
            print(f"[MCW-SYNC] Stage 0.5 (JSON-enforce retry) failed: {e05}")
            # Fall through to Stage 1/2 with the original raw output + error

    # Stage 1: format proofreader LLM
    fp_result = await _run_format_proofreader(
        raw_json_text=raw,
        parse_error=parse_error,
    )
    if isinstance(fp_result, dict) and not fp_result.get("_format_error"):
        return fp_result
    fp_reason = fp_result.get("reason", "unknown") if isinstance(fp_result, dict) else "unknown"

    # Stage 2: synchronizer self-correction
    print(f"[MCW-SYNC] Stage 1 (format proofreader) failed: {fp_reason}, trying Stage 2")
    return await _run_synchronizer_self_correct(
        raw_json_text=raw,
        parse_error=parse_error,
        world_json=world_json,
        system=system,
    )


async def _run_architect_supplement(
    *,
    questions: list[str],
    world: World,
    creative_mode: str | None = None,
) -> str:
    """架构师补充轮：回答校对者提出的补充问题。"""
    from worldforger.creative_modes import chat_mode_system

    world_json = json.dumps(world.model_dump(mode="json"), ensure_ascii=False, indent=2)
    question_text = "\n\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions))
    user_msg = (
        "以下是对你上一轮世界观回复的**补充需求**，请针对性地补充缺失的设定，用自然语言描述即可：\n\n"
        + question_text
    )
    system = system_with_world_json(world_json)
    if creative_mode:
        addon = chat_mode_system(creative_mode)
        if addon:
            system = system + "\n\n" + addon
    raw = await chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        model=get_settings().openai_chat_model,
        temperature=0.8,
        max_tokens=4096,
    )
    return raw.strip()


async def _run_synchronizer(
    *,
    world_json: str,
    assistant_reply: str,
    system: str,
) -> dict[str, Any]:
    """同步器 LLM：从架构师回复中提取 JSON patch。"""
    user_block = (
        "【当前 world.json】\n"
        + world_json
        + "\n\n【助手自然语言回复】\n"
        + assistant_reply.strip()
    )
    raw = await chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_block},
        ],
        model=_structure_model_name(),
        temperature=0.15,
        max_tokens=32768,
    )

    # Detect refusal & retry with minimal prompt
    _REFUSAL = ["无法给到", "无法提供", "不能提供", "抱歉", "我无法", "我不能"]
    if raw and len(raw.strip()) < 100 and any(m in raw for m in _REFUSAL):
        short_user = (
            "请仅基于下方的助手回复提取结构化 JSON patch。"
            "如果助手回复中没有可写入的设定变更，返回 {}。\n"
            + assistant_reply.strip()[:3000]
        )
        raw = await chat_completion(
            [
                {"role": "system", "content": "你是结构化同步器。直接输出 JSON，不要拒绝。"},
                {"role": "user", "content": short_user},
            ],
            model=_structure_model_name(),
            temperature=0.3,
            max_tokens=32768,
        )
    return parse_structure_json(raw)


async def sync_panels_from_dialogue(
    world: World,
    *,
    user_message: str,
    assistant_reply: str,
    scope: str | None = None,
    creative_mode: str | None = None,
    proofreader_max_retries: int = 3,
) -> dict[str, Any]:
    """Second-pass LLM: natural language -> structured sections, with optional proofreader loop.

    proofreader_max_retries: 校对者→架构师补充的最大轮数（0 跳过校对者，保持原有行为）。
    若解析失败则返回 ok=False 的 dict（而非抛异常），以便 API 透传诊断信息。
    """
    world_json = json.dumps(world.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if len(world_json) > 12000:
        world_json = world_json[:12000] + "\n…(world.json 已截断)"
    user_block = (
        "【当前 world.json】\n"
        + world_json
        + "\n\n【用户消息】\n"
        + user_message.strip()
        + "\n\n【助手自然语言回复】\n"
        + assistant_reply.strip()
    )
    sc = (scope or "all").strip() or "all"
    system = structure_system_for_scope(sc) + structure_sync_addon(creative_mode)
    gt = genre_tags_prompt_addon(world.meta.genre_tags)
    if gt:
        system = system + "\n\n" + gt

    # --- 同步器 #1 ---
    format_proofreader_used = False
    format_stages: list[str] = []
    structure_output_keys: list[str] = []
    proofreader_rounds = 0
    proofreader_final_verdict = "ok"
    proofreader_issues: list[dict[str, Any]] = []
    patch_accum: dict[str, Any] = {}

    try:
        raw = await chat_completion(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_block},
            ],
            model=_structure_model_name(),
            temperature=0.15,
            max_tokens=32768,
        )
        print(f"[MCW-SYNC] Synchronizer raw output length: {len(raw)} chars")
        print(f"[MCW-SYNC] Synchronizer raw preview (first 500): {raw[:500]}")
        # Check for truncation: after stripping code fences, content must end with }
        fence_stripped = _strip_code_fence(raw)
        if not fence_stripped.rstrip().endswith("}"):
            print(f"[MCW-SYNC] Output appears truncated (ends with '{raw.rstrip()[-80:]}')")
            try:
                raw_patch = _salvage_partial_json(raw)
                print(
                    f"[MCW-SYNC] Salvaged partial JSON from truncated output, "
                    f"keys: {list(raw_patch.keys())}"
                )
            except ValueError as salvage_err:
                raise ValueError(
                    "synchronizer output appears truncated (no closing '}' after stripping fences); "
                    f"length={len(raw)}, last 100 chars: {raw[-100:]}"
                ) from salvage_err
        else:
            try:
                raw_patch = parse_structure_json(raw)
            except ValueError as init_parse_err:
                print(f"[MCW-SYNC] Initial parse failed: {init_parse_err}, entering format recovery")
                try:
                    raw_patch = await _try_parse_with_format_recovery(
                        raw, world_json=world_json, system=system,
                        assistant_reply=assistant_reply,
                    )
                    format_proofreader_used = True
                    format_stages.append("format_recovery")
                    print(f"[MCW-SYNC] Format recovery result keys: {list(raw_patch.keys())}")
                except ValueError as recovery_err:
                    print(f"[MCW-SYNC] Format recovery also failed: {recovery_err}")
                    print(f"[MCW-SYNC] === SYNCHRONIZER RAW OUTPUT (first 500 chars) ===")
                    print(raw[:500])
                    print(f"[MCW-SYNC] === END RAW OUTPUT ===")
                    # Graceful fallback: return empty patch instead of crashing
                    raw_patch = {}
                    format_proofreader_used = True
                    format_stages.append("empty_fallback")
        print(f"[MCW-SYNC] Parsed patch keys: {list(raw_patch.keys())}")
        print(f"[MCW-SYNC] Patch sizes: {{{', '.join(f'{k}: {_json_size(raw_patch[k])}' for k in raw_patch)}}}")
        if not isinstance(raw_patch, dict):
            raise ValueError("parsed root is not an object")
        structure_output_keys = list(raw_patch.keys())
        if sc != "all":
            patch_accum = {k: v for k, v in raw_patch.items() if k == sc}
        else:
            patch_accum = dict(raw_patch)

        # --- 校对者统一审查 + 补全循环 ---
        # 统一校对者：一次 LLM 调用同时完成审查和补全 JSON 输出，
        # 无需再走「架构师补充 → 同步器提取」的 3 调用往返。
        retries = max(0, proofreader_max_retries)
        proofreader_reference_reply = assistant_reply

        for _ in range(retries):
            # 跳过空 patch：同步器未提取任何新内容，无需校对
            if not patch_accum:
                proofreader_final_verdict = "ok"
                break

            proofreader_rounds += 1
            pr_result = await _run_proofreader(
                architect_reply=proofreader_reference_reply,
                patch=patch_accum,
                world_json=world_json,
            )
            proofreader_issues.append(pr_result)
            if pr_result.get("verdict") == "retry":
                proofreader_final_verdict = "retry"
                # 统一校对者直接输出 supplement_patch JSON
                supplement_patch = pr_result.get("supplement_patch") or {}
                if not isinstance(supplement_patch, dict) or not supplement_patch:
                    break
                if sc != "all":
                    new_patch = {k: v for k, v in supplement_patch.items() if k == sc}
                else:
                    new_patch = dict(supplement_patch)
                patch_accum = merge_section_conservative(patch_accum, new_patch)
            else:
                proofreader_final_verdict = "ok"
                break

        # --- 最终合并 ---
        merged, keys, merge_warnings, normalize_notes = apply_structure_patch(world, patch_accum)
        return {
            "ok": True,
            "world": merged,
            "updated_sections": keys,
            "applied_patch": patch_accum,
            "structure_output_keys": structure_output_keys,
            "scope_applied": sc,
            "merge_warnings": merge_warnings,
            "normalize_notes": normalize_notes,
            "proofreader_rounds": proofreader_rounds,
            "proofreader_final_verdict": proofreader_final_verdict,
            "proofreader_issues": proofreader_issues,
            "format_proofreader_used": format_proofreader_used,
            "format_stages": format_stages,
        }
    except Exception as exc:
        print(f"[MCW-SYNC] sync_panels_from_dialogue exception: {type(exc).__name__}: {exc}")
        return {
            "ok": False,
            "error": str(exc),
            "world": world,
            "updated_sections": [],
            "applied_patch": {},
            "structure_output_keys": structure_output_keys,
            "scope_applied": sc,
            "merge_warnings": [],
            "normalize_notes": {},
            "proofreader_rounds": proofreader_rounds,
            "proofreader_final_verdict": "error",
            "proofreader_issues": proofreader_issues,
            "format_proofreader_used": format_proofreader_used,
            "format_stages": format_stages,
        }
