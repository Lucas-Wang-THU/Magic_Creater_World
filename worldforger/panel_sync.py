from __future__ import annotations

import json
import re
from typing import Any

from worldforger.config import get_settings
from worldforger.creative_modes import genre_tags_prompt_addon, structure_sync_addon
from worldforger.llm import chat_completion
from worldforger.schemas import (
    AttributeSystem,
    CulturesSection,
    FactionsSection,
    GeographySection,
    HistorySection,
    ItemQualitySystem,
    PowerSystem,
    World,
)

STRUCTURE_SYSTEM_BASE = """你是「设定结构化同步器」，与负责自然语言对话的「世界观架构师」是不同角色。
你的唯一任务：根据【用户消息】与【助手自然语言回复】，把其中可写入世界设定、且与【当前 world.json】相容的**事实性内容**，整理成 JSON。

硬性规则：
1. 只输出**一个** JSON 对象，不要输出任何 JSON 以外的文字（不要 Markdown 标题、不要解释）。
2. 顶层键**只能**来自：geography, power_system, item_quality_system, attribute_system, factions, cultures, history。未涉及或无法可靠抽取的模块**不要出现**该键。**不得**输出 `files`、`search` 等工作台键（「导出与快照」「全文搜索」见对话上下文中 **studio** 说明，非 world.json 持久化字段）。
3. 每个出现的键对应的对象结构必须与标准 world.json 中该节一致：
   - geography: **summary**（行星/多陆总览，避免把地标清单堆进总览）、**regions[]**（大陆/王国/海域等可区分单元）、**climate_notes**（全图气候带/季风/异常气象）、**map_notes**（方位、比例、制图或旅行网络说明）。**可选**顶层 **landmarks[]**、**resources[]**（仅放尚未归属区域的散项，或与各区域合并后的汇总；**优先**写在所属区域的 **landmarks / resources**）。字符串数组项为短名；勿输出对象数组。**regions 必须为数组**；单对象须包成 `[{...}]`。区域项：**id**（建议小写 slug，如 `north_realm`，与 **relations[].target_id** 对齐）、**name**、**summary**；可选 **terrain**（地貌类型词）、**climate**（局地气候一句）、**notes**（旅行风险、关卡/调查钩子）、**landmarks**、**resources**、**relations**（`target_id`、`type` 短标签、`notes` 可选）。
   - power_system: 顶层键必须为 **power_system**（勿拆到根级）。
     • **summary**：境界总览（力量阶梯在叙事中的位置）。
     • **realm_design_notes**：境界命名、递进逻辑、破境代价、与 **attribute_system** 的边界。
     • **skill_tree_design_notes**：跨境技能树规则（节点 **id**、**prereq_ids** 含义、通用树与子类树关系）。
     • **tiers[]**：每项 **name**、**description**、**typical_capabilities[]**、**limitations[]**、**examples[]**；可选本境 **skill_tree**（节点 **id**、**name**、**summary**、**prereq_ids[]**、**branch**）；可选 **subclass_paths**（**id**、**name**、**tagline**、**flavor**、可选 **profession_id**、可选专属 **skill_tree**）。**prereq_ids** 只能引用**同一棵树**内已声明节点 **id**。
     • **profession_system**（可选）：**summary**、**design_notes**、**by_tier[]**（**tier_name** + **professions[]**；职业项 **id**、**name**、**tagline**、**flavor**、**exclusive_faction_id**、**notes**）。**subclass_paths.profession_id** 须与同境 **by_tier** 中某职业 **id** 一致。
   - item_quality_system: 顶层键必须为 **`item_quality_system`**（勿用 `items` / `item_grades` 等别名）。
     • **summary**：物品阶梯总览、与境界/派系/经济的关系。
     • **grades[]**：每项 **name**（档位名，必填字符串）、**rarity_narrative**（稀有度叙事）、**typical_effects**（典型效果或词条方向）、**binding_rules**（绑定、交易、掉落、使用限制等可裁定规则）、**examples**（可选，字符串数组，短例）。勿用空对象占位；档位边界须可区分。
   - attribute_system: summary, design_notes, stats[]（每项 id、name 必填；**intro** 为该维度单独简介；其余 abbreviation、description、scale、typical_use、reference_percent 0–100 整数可选）；**tier_average_profiles[]**（每项 **tier_name** 与境界名对应；**averages** 为对象，键为 stat 的 **id**、值为 0–100 表示该境普通人的平均刻度）。**顶层键名必须为 attribute_system**，禁止使用 attributes、character_stats 或根级纯 stats 数组代替；若误用 attributes 对象/数组，后端会尽力映射。stats 可用 dimensions 等别名，每项须能识别为一条属性维度。
   - factions: summary, entities[]（每项 id, name, goals, territory, key_figures[], relations[] 含 target_id, type: ally|enemy|neutral|complex, notes）
   - cultures: summary, entities[]（每项 **id**、**name**、**kind**: culture|religion|syncretic, summary, tenets, practices, sacred_sites[], key_figures[], relations[] 含 target_id、type（短字符串，如影响/冲突/融合）、notes）。**entities 必须为数组**；单条传统/教团也须用 `[{...}]` 包裹。文化与宗教共用本节，用 **kind** 区分。
   - history: summary, events[]（每项 when, title, summary, consequences[], linked_faction_ids[]）
4. **合并策略（重要）**：先从【当前 world.json】复制该节，再写入本轮变更。若某数组或字符串本轮**没有变化**，请**完全省略**该字段，**禁止**输出空字符串 \"\" 或空数组 [] 来占位（否则程序会误保留旧值逻辑复杂；后端会丢弃空占位，但你仍应省略未改字段）。
5. 若某数组确有更新，必须输出**合并后的完整数组**（含旧条目 + 新条目），不要只输出新增的一条。
6. 不要修改 meta（id、name、version 等由程序管理）。
7. 若助手回复仅为规划、提问或闲聊、没有任何可落盘设定，输出空对象：{}。
8. **多模块同答**：若助手一段话里同时写了地理、力量、物品、人物属性、派系、文化/宗教、历史等多个方面，必须在**同一个** JSON 里输出**多个顶层键**（geography、power_system、item_quality_system、attribute_system、factions、cultures、history 等），每个键下给出合并后的完整小节，不要只挑一个模块写。
9. **地理 regions（大陆/区域）**：凡出现可区分的地理/政治单元，必须写入 **`geography.regions`**；每项至少 **name** + **summary**，并尽量给出稳定 **id** 以便 **relations** 引用。地标、特产、矿脉、可调查点等写入该区域的 **landmarks** / **resources**（短字符串列表）；**勿**把长段落塞进列表项——长叙事放在 **summary** 或 **notes**。区域间邻接、贸易、航道、关隘写在 **`relations`**：`target_id` 指向对方 **id**，`type` 用短标签（如 邻接/贸易/航道/调查轴）。**形态示例（虚构名，勿照抄）**：`{"geography":{"summary":"双陆夹内海","climate_notes":"西岸多雨","map_notes":"上北下南，比例示意","regions":[{"id":"north_realm","name":"北境","summary":"河谷农业带","terrain":"丘陵","climate":"冬雨型","notes":"关隘易守；主线常经古渡","landmarks":["古渡","碑林"],"resources":["盐","木材"],"relations":[{"target_id":"south_realm","type":"贸易","notes":"粮盐"}]}]}}`"""


def structure_system_for_scope(scope: str | None) -> str:
    if not scope or scope == "all":
        return STRUCTURE_SYSTEM_BASE
    allowed = {
        "geography",
        "power_system",
        "item_quality_system",
        "attribute_system",
        "factions",
        "cultures",
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


def apply_structure_patch(
    world: World, patch: dict[str, Any]
) -> tuple[World, list[str], list[str], dict[str, list[str]]]:
    """Merge patch into world. Returns (new_world, updated_keys, merge_warnings, normalize_notes)."""
    from worldforger.panel_merge import merge_section_conservative
    from worldforger.structure_normalize import normalize_structure_patch_detailed

    patch, normalize_notes = normalize_structure_patch_detailed(patch)
    data = world.model_dump(mode="json")
    updated: list[str] = []
    warnings: list[str] = []
    allowed = {
        "geography": GeographySection,
        "power_system": PowerSystem,
        "item_quality_system": ItemQualitySystem,
        "attribute_system": AttributeSystem,
        "factions": FactionsSection,
        "cultures": CulturesSection,
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
    return new_world, updated, warnings, normalize_notes


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
    返回 dict：world, updated_sections, applied_patch, structure_output_keys, scope_applied, merge_warnings, normalize_notes
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
    gt = genre_tags_prompt_addon(world.meta.genre_tags)
    if gt:
        system = system + "\n\n" + gt
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
    merged, keys, merge_warnings, normalize_notes = apply_structure_patch(world, patch)
    return {
        "world": merged,
        "updated_sections": keys,
        "applied_patch": patch,
        "structure_output_keys": structure_output_keys,
        "scope_applied": sc,
        "merge_warnings": merge_warnings,
        "normalize_notes": normalize_notes,
    }
