from __future__ import annotations

import json
import re
from typing import Any

from worldforger.config import get_settings
from worldforger.creative_modes import structure_sync_addon
from worldforger.llm import chat_completion
from worldforger.schemas import (
    FactionsSection,
    GeographySection,
    HistorySection,
    ItemQualitySystem,
    PowerSystem,
    World,
)
from worldforger.structure_normalize import normalize_structure_patch

STRUCTURE_SYSTEM_BASE = """你是「设定结构化同步器」，与负责自然语言对话的「世界观架构师」是不同角色。
你的唯一任务：根据【用户消息】与【助手自然语言回复】，把其中可写入世界设定、且与【当前 world.json】相容的**事实性内容**，整理成 JSON。

硬性规则：
1. 只输出**一个** JSON 对象，不要输出任何 JSON 以外的文字（不要 Markdown 标题、不要解释）。
2. 顶层键**只能**来自：geography, power_system, item_quality_system, factions, history。未涉及或无法可靠抽取的模块**不要出现**该键。
3. 每个出现的键对应的对象结构必须与标准 world.json 中该节一致：
   - geography: summary, regions[], landmarks[], climate_notes, resources[], map_notes
   - power_system: summary, tiers[]（每项 name, description, typical_capabilities[], limitations[], examples[]）
   - item_quality_system: summary, grades[]（每项 name, rarity_narrative, typical_effects, binding_rules）。**顶层键必须写 `item_quality_system`**，禁止使用 `items`、`item_grades` 等别名；grades 每项必须有字符串 **name**（档位名），勿用空对象占位。
   - factions: summary, entities[]（每项 id, name, goals, territory, key_figures[], relations[] 含 target_id, type: ally|enemy|neutral|complex, notes）
   - history: summary, events[]（每项 when, title, summary, consequences[], linked_faction_ids[]）
4. **合并策略（重要）**：先从【当前 world.json】复制该节，再写入本轮变更。若某数组或字符串本轮**没有变化**，请**完全省略**该字段，**禁止**输出空字符串 \"\" 或空数组 [] 来占位（否则程序会误保留旧值逻辑复杂；后端会丢弃空占位，但你仍应省略未改字段）。
5. 若某数组确有更新，必须输出**合并后的完整数组**（含旧条目 + 新条目），不要只输出新增的一条。
6. 不要修改 meta（id、name、version 等由程序管理）。
7. 若助手回复仅为规划、提问或闲聊、没有任何可落盘设定，输出空对象：{}。
8. **多模块同答**：若助手一段话里同时写了地理、力量、派系等多个方面，必须在**同一个** JSON 里输出**多个顶层键**（geography、power_system、factions 等），每个键下给出合并后的完整小节，不要只挑一个模块写。
9. **地理 regions（大陆/区域）**：凡助手描述了不同大陆、王国、海域等可区分的地理单元，必须写入 `geography.regions` 数组；每项为对象，至少包含 `name` 与 `summary`（可含 `id`、`terrain`、`climate` 等字符串字段）。若描述了区域之间的邻接、贸易路线、航道、山脉隘口等联系，请在对应区域的 **`relations`** 数组中写出：`target_id`（另一区域的 `id`）、`type`（短字符串，如邻接/贸易/航道）、`notes`（可选）。总览仍写在 `geography.summary`。"""


def structure_system_for_scope(scope: str | None) -> str:
    if not scope or scope == "all":
        return STRUCTURE_SYSTEM_BASE
    allowed = {
        "geography",
        "power_system",
        "item_quality_system",
        "factions",
        "history",
    }
    if scope not in allowed:
        return STRUCTURE_SYSTEM_BASE
    return (
        STRUCTURE_SYSTEM_BASE
        + f"\n10. **本轮同步范围**：只输出顶层键 `{scope}`，禁止输出其它顶层键；若本轮与 `{scope}` 无关则输出 {{}}。"
    )


def _structure_model_name() -> str:
    s = get_settings()
    m = s.structure_sync_model.strip()
    return m or s.openai_chat_model


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def parse_structure_json(raw: str) -> dict[str, Any]:
    t = _strip_code_fence(raw)
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no json object in model output")
    return json.loads(t[start : end + 1])


def apply_structure_patch(world: World, patch: dict[str, Any]) -> tuple[World, list[str], list[str]]:
    """Merge patch into world. Returns (new_world, updated_keys, merge_warnings)."""
    from worldforger.panel_merge import merge_section_conservative

    patch = normalize_structure_patch(patch)
    data = world.model_dump(mode="json")
    updated: list[str] = []
    warnings: list[str] = []
    allowed = {
        "geography": GeographySection,
        "power_system": PowerSystem,
        "item_quality_system": ItemQualitySystem,
        "factions": FactionsSection,
        "history": HistorySection,
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
    return new_world, updated, warnings


async def sync_panels_from_dialogue(
    world: World,
    *,
    user_message: str,
    assistant_reply: str,
    scope: str | None = None,
    creative_mode: str | None = None,
) -> dict[str, Any]:
    """
    Second-pass LLM: natural language -> structured sections.
    scope: 非 all 时会丢弃其它顶层键（前端默认应使用 all 以免助手多模块输出被截断）。
    返回 dict：world, updated_sections, applied_patch, structure_output_keys, scope_applied, merge_warnings
    """
    world_json = json.dumps(world.model_dump(mode="json"), ensure_ascii=False, indent=2)
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
    raw = await chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_block},
        ],
        model=_structure_model_name(),
        temperature=0.15,
        max_tokens=8192,
    )
    raw_patch = parse_structure_json(raw)
    if not isinstance(raw_patch, dict):
        raise ValueError("parsed root is not an object")
    structure_output_keys = list(raw_patch.keys())
    if sc != "all":
        patch = {k: v for k, v in raw_patch.items() if k == sc}
    else:
        patch = dict(raw_patch)
    merged, keys, merge_warnings = apply_structure_patch(world, patch)
    return {
        "world": merged,
        "updated_sections": keys,
        "applied_patch": patch,
        "structure_output_keys": structure_output_keys,
        "scope_applied": sc,
        "merge_warnings": merge_warnings,
    }
