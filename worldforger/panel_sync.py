from __future__ import annotations

import json
import re
from typing import Any

from worldforger.config import get_settings
from worldforger.creative_modes import genre_tags_prompt_addon, structure_sync_addon
from worldforger.llm import chat_completion
from worldforger.panel_merge import merge_section_conservative
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

STRUCTURE_SYSTEM_BASE = """你是「设定结构化同步器」，与负责自然语言对话的「世界观架构师」是不同角色。
你的唯一任务：根据【用户消息】与【助手自然语言回复】，把其中可写入世界设定、且与【当前 world.json】相容的**事实性内容**，整理成 JSON。

硬性规则：
1. 只输出**一个** JSON 对象，不要输出任何 JSON 以外的文字（不要 Markdown 标题、不要解释）。
2. 顶层键**只能**来自：geography, ecology, power_system, item_quality_system, attribute_system, factions, cultures, characters, history, economy, story。未涉及或无法可靠抽取的模块**不要出现**该键。**不得**输出 `files`、`search` 等工作台键（「导出与快照」「全文搜索」见对话上下文中 **studio** 说明，非 world.json 持久化字段）。
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
   - factions: **summary**（多派系总览与博弈格局）。**entities[]**（**必须为数组**；单条派系也须 `[{...}]`；勿把实体摊平到根级）。每项实体：
     • **id**（必填，短 slug，全局唯一）、**name**（必填）。
     • **goals**、**territory**：各为**字符串**一段；勿用对象/数组代替整段叙事（长说明可写在 goals 字符串内换行）。
     • **key_figures[]**：**仅字符串数组**；每项一行（`姓名` 或 `姓名 · 职务` 或带括号的短钩子）。**禁止** `{name, role}` 或 `{name, title}` 对象数组；若模型输出对象，须压成单行字符串再输出。
     • **relations[]**：每项 **target_id**（须为**另一实体**的 **id**，勿写派系中文名代替 id）、**type** 字段**只能是**英文枚举 **ally** | **enemy** | **neutral** | **complex**（勿用 rival、hostile、联盟、敌对、中立等——若语义如此请映射为 enemy/ally/neutral/complex 后再输出）、**notes**（可选）。
     • 勿使用 **organizations**、**factions_list** 等替代 **entities**；顶层键名必须是 **factions**。
   - cultures: summary, entities[]（每项 **id**、**name**、**kind**: culture|religion|syncretic, summary, tenets, practices, sacred_sites[], key_figures[], relations[] 含 target_id、type（短字符串，如影响/冲突/融合）、notes）。**entities 必须为数组**；单条传统/教团也须用 `[{...}]` 包裹。文化与宗教共用本节，用 **kind** 区分。
   - characters: **summary**（卡司总览）、**design_notes**（与派系要人、历史事件、地理籍贯的对齐说明）。**entities[]**：每项 **id**、**name**；可选 **aliases[]**、**cast_role**（`protagonist_core` | `supporting_major` | `supporting_minor` | `antagonist` | `background`）、**faction_ids[]**（须为已有 **factions.entities[].id**）、**home_region_id**（须为已有 **geography.regions[].id**）、**one_line_hook**、**notes**、**notable_skills[]**（叙事或玩法向人物特长短句，**非**境界 **power_system.skill_tree** 节点）。**relations[]**：**source_id**、**target_id**（须为本次或已有 **entities[].id**）、**relation_type**（如 ally/rival/family/debt/secret）、可选 **visibility**（reader/author_only）、**notes**。
   - history: summary, events[]（每项 when, title, summary, consequences[], linked_faction_ids[]）
   - economy: **summary**（通货与总流通叙事）、**design_notes**（与物品档位、派系、地理 id 的对齐）。**currencies[]**：**id**、**name**；可选 **symbol**、**issuer_faction_id**（须 **factions.entities[].id**）、**exchange_notes**。**markets[]**：**id**、**name**；可选 **summary**、**linked_region_ids[]**（**geography.regions[].id**）、**dominant_faction_ids[]**、**notes**。**trade_routes[]**：**id**、**name**、**from_region_id**、**to_region_id**（须为区域 id）；可选 **summary**、**goods_notes**、**controlling_faction_ids[]**、**notes**。**trade_goods[]**：**id**、**name**；可选 **category**（如 strategic|luxury|common|contraband）、**summary**、**notes**。**labor_notes**、**taxation_notes**、**volatility_notes**（劳动力/税收再分配/波动危机等条款式说明）。
   - ecology: **summary**（全图食物网/危险带/与文明交界叙事）、**design_notes**（如何与 **geography**、**attribute_system** 对齐引用）。**biomes[]**：每项 **id**、**name**、**summary**；**linked_region_ids[]**（须为已有 **geography.regions[].id**）；可选 **climate_habitat**、**hazards**、**notes**。**species[]**：每项 **id**、**name**、**biome_id**（对齐 **biomes[].id**）；**traits[]**（短标签）；**notable_skills[]**（叙事或规则向「技能/行为」短句，非境界 skill_tree）；**encounter_dialogue**（一句遭遇台词或环境旁白，供跑团/叙事）；可选 **danger_notes**。数组项为对象或短字符串时，后端会尽力归一。
   - story: **summary**、**design_notes**、**unit_label**（章/章节/跑团会话等，可选）。**chapters[]**：**id**、**order**、**title**、**status**（planned|drafting|locked）；可选 **reader_synopsis**、**author_notes**、**word_count**。**foreshadowing[]**：**id**、**label**、**planted_chapter_id**、**payoff_chapter_id**（须为 chapters[].id 或空）、**status**（open|partial|resolved）、**reader_known**、**notes**。**narrator**：**character_id**、**person**、**voice_notes**。**writing_defaults**：**attach_prev_chapters**（0–5）。**勿**在 story 内输出粗纲/细纲/正文全文（它们在 story/*.md 文件）。
4. **合并策略（重要）**：先从【当前 world.json】复制该节，再写入本轮变更。若某数组或字符串本轮**没有变化**，请**完全省略**该字段，**禁止**输出空字符串 \"\" 或空数组 [] 来占位（否则程序会误保留旧值逻辑复杂；后端会丢弃空占位，但你仍应省略未改字段）。
5. 若某数组确有更新，必须输出**合并后的完整数组**（含旧条目 + 新条目），不要只输出新增的一条。
6. 不要修改 meta（id、name、version 等由程序管理）。
7. 若助手回复仅为规划、提问或闲聊、没有任何可落盘设定，输出空对象：{}。
8. **多模块同答**：若助手一段话里同时写了地理、生态、力量、物品、人物属性、派系、文化/宗教、人物卡司、历史、经济流通等多个方面，必须在**同一个** JSON 里输出**多个顶层键**（geography、ecology、power_system、item_quality_system、attribute_system、factions、cultures、characters、history、economy 等），每个键下给出合并后的完整小节，不要只挑一个模块写。
9. **地理 regions（大陆/区域）**：凡出现可区分的地理/政治单元，必须写入 **`geography.regions`**；每项至少 **name** + **summary**，并尽量给出稳定 **id** 以便 **relations** 引用。地标、特产、矿脉、可调查点等写入该区域的 **landmarks** / **resources**（短字符串列表）；**勿**把长段落塞进列表项——长叙事放在 **summary** 或 **notes**。区域间邻接、贸易、航道、关隘写在 **`relations`**：`target_id` 指向对方 **id**，`type` 用短标签（如 邻接/贸易/航道/调查轴）。**形态示例（虚构名，勿照抄）**：`{"geography":{"summary":"双陆夹内海","climate_notes":"西岸多雨","map_notes":"上北下南，比例示意","regions":[{"id":"north_realm","name":"北境","summary":"河谷农业带","terrain":"丘陵","climate":"冬雨型","notes":"关隘易守；主线常经古渡","landmarks":["古渡","碑林"],"resources":["盐","木材"],"relations":[{"target_id":"south_realm","type":"贸易","notes":"粮盐"}]}]}}`"""


PROOFREADER_SYSTEM = """你是「设定校对者」，与负责自然语言创作的「世界观架构师」及负责 JSON 提取的「结构化同步器」是不同角色。
你的唯一任务：对比【架构师自然语言回复】与【同步器提取的 JSON patch】，检查同步器是否**完整捕获**了架构师回复中的**所有新增/修改的设定**。

硬性规则：
1. 只输出**一个** JSON 对象，不要输出任何 JSON 以外的文字。
2. 逐模块对比：架构师回复中提到的每个设定模块（地理/生态/境界/物品/属性/派系/文化/角色/历史/经济/情节），同步器 JSON 中是否有对应条目。
3. 数组条目计数：若架构师回复中提到 N 个实体（如 N 个派系、N 种货币、N 个职业），同步器 JSON 中应至少包含 N 个条目。
4. 字段完整性：每个条目的核心字段（如 name、summary、description）是否已填充有意义的非空值。
5. 不要求逐字一致：语义等价即可通过。架构师的文学性描述与同步器的结构化表述只要含义相同就视为覆盖。
6. 若发现遗漏或明显不完整，verdict 设为 "retry"，并在 questions_for_architect 中生成**面向架构师的补充问题**（用自然语言，告诉架构师需要补充哪些具体内容，而非 JSON 指令）。
7. 若审查通过，verdict 设为 "ok"。

输出格式：
{
  "verdict": "ok" | "retry",
  "missing": ["描述每条遗漏或缺陷"],
  "questions_for_architect": ["面向架构师的补充问题1", "问题2", ...]
}
"""


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
        model=_structure_model_name(),
        temperature=0.05,
        max_tokens=2048,
    )
    return parse_structure_json(raw)


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
        max_tokens=8192,
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
    返回 dict 含 world, updated_sections, applied_patch, proofreader_rounds,
    proofreader_final_verdict, proofreader_issues 等。
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

    # --- 同步器 #1 ---
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
        patch_accum = {k: v for k, v in raw_patch.items() if k == sc}
    else:
        patch_accum = dict(raw_patch)

    # --- 校对者 + 架构师补充循环 ---
    proofreader_rounds = 0
    proofreader_final_verdict = "ok"
    proofreader_issues: list[dict[str, Any]] = []
    retries = max(0, proofreader_max_retries)
    architect_reply = assistant_reply  # 始终保持最新一轮的架构师回复引用

    for _ in range(retries):
        proofreader_rounds += 1
        pr_result = await _run_proofreader(
            architect_reply=architect_reply,
            patch=patch_accum,
            world_json=world_json,
        )
        proofreader_issues.append(pr_result)
        if pr_result.get("verdict") == "retry":
            proofreader_final_verdict = "retry"
            questions = pr_result.get("questions_for_architect") or []
            if not questions:
                break
            architect_supplement = await _run_architect_supplement(
                questions=questions,
                world=world,
                creative_mode=creative_mode,
            )
            architect_reply = architect_supplement
            new_patch_raw = await _run_synchronizer(
                world_json=world_json,
                assistant_reply=architect_supplement,
                system=system,
            )
            if isinstance(new_patch_raw, dict) and new_patch_raw:
                if sc != "all":
                    new_patch = {k: v for k, v in new_patch_raw.items() if k == sc}
                else:
                    new_patch = dict(new_patch_raw)
                patch_accum = merge_section_conservative(patch_accum, new_patch)
        else:
            proofreader_final_verdict = "ok"
            break

    # --- 最终合并 ---
    merged, keys, merge_warnings, normalize_notes = apply_structure_patch(world, patch_accum)
    return {
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
    }
