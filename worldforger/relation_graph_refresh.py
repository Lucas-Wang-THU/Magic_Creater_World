"""根据当前 factions / cultures 设定，调用 LLM 仅修订 relations 边，供关系图更新。"""

from __future__ import annotations

import json
from typing import Any

from worldforger.config import get_settings
from worldforger.creative_modes import normalize_creative_mode, structure_sync_addon
from worldforger.llm import chat_completion
from worldforger.panel_sync import parse_structure_json
from worldforger.schemas import (
    CultureRelation,
    CulturesSection,
    FactionRelation,
    FactionsSection,
    World,
)

FACTION_RELATIONS_SYSTEM = """你是「派系关系网络」修订器。根据已给出的 factions 数据（含 summary 与各实体 id、name、goals、territory、key_figures），为每个派系重写 **relations**，使关系图与叙述一致、可渲染为有向边。

硬性规则：
1. 只输出**一个** JSON 对象，不要 Markdown 标题或解释文字。
2. 根对象形如：{"entities": [ {"id": "派系id", "relations": [ {"target_id": "另一派系id", "type": "ally|enemy|neutral|complex", "notes": "短说明"} ] } ] }
3. **entities** 中每条必须有 **id**（与输入中已有派系 id **完全一致**）与 **relations** 数组。
4. **target_id** 必须是输入中某一派系的 id；禁止虚构 id。禁止自环（target_id 不得等于自己的 id）。
5. **type** 必须是 ally、enemy、neutral、complex 四者之一。
6. 若某派系在输出中未出现，程序会保留其原有 relations；你应优先为所有派系给出一致的 relations（除非输入中只有一个派系，则 relations 可为空数组）。"""

CULTURE_RELATIONS_SYSTEM = """你是「文化 / 宗教关系网络」修订器。根据已给出的 cultures 数据（含 summary 与各实体 id、name、kind、summary、tenets、practices 等），为每个实体重写 **relations**，表达影响、冲突、融合、正统与异端等联系。

硬性规则：
1. 只输出**一个** JSON 对象，不要 Markdown 标题或解释文字。
2. 根对象形如：{"entities": [ {"id": "实体id", "relations": [ {"target_id": "另一实体id", "type": "短标签如 影响/冲突/融合", "notes": ""} ] } ] }
3. **id**、**target_id** 必须与输入中已有文化实体 id 完全一致；禁止虚构 id；禁止自环。
4. **type** 为简短中文或中英标签（如 影响、冲突、融合、正统对立），勿写长段落。
5. 若某实体在输出中未出现，程序会保留其原有 relations；你应优先为所有实体给出与叙述一致的 relations。"""


def _structure_model_name() -> str:
    s = get_settings()
    m = (s.structure_sync_model or "").strip()
    return m or s.openai_chat_model


def _effective_creative_mode(world: World, body_mode: str | None) -> str | None:
    return normalize_creative_mode(body_mode) or normalize_creative_mode(world.meta.creative_mode)


def apply_faction_relations_patch(
    section: FactionsSection, patch: dict[str, Any]
) -> tuple[FactionsSection, list[str]]:
    warnings: list[str] = []
    rows = patch.get("entities")
    if not isinstance(rows, list):
        return section, ["模型输出缺少 entities 数组，未修改"]
    data = section.model_dump(mode="json")
    entities_data: list[dict[str, Any]] = data.get("entities") or []
    valid_ids = {str(e.get("id", "")).strip() for e in entities_data if isinstance(e, dict) and str(e.get("id", "")).strip()}
    if not valid_ids:
        return section, ["当前无派系实体，跳过合并"]
    id_to_index = {str(e["id"]).strip(): i for i, e in enumerate(entities_data) if isinstance(e, dict) and e.get("id")}
    for row in rows:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("id") or "").strip()
        if eid not in id_to_index:
            warnings.append(f"跳过未知派系 id: {eid}")
            continue
        rels_in = row.get("relations")
        if not isinstance(rels_in, list):
            warnings.append(f"{eid}: relations 不是数组，已跳过该条")
            continue
        cleaned: list[dict[str, Any]] = []
        for r in rels_in:
            if not isinstance(r, dict):
                continue
            tid = str(r.get("target_id") or "").strip()
            if tid not in valid_ids:
                warnings.append(f"{eid}: 非法 target_id {tid!r}，已丢弃该边")
                continue
            if tid == eid:
                warnings.append(f"{eid}: 忽略自环 target_id")
                continue
            try:
                fr = FactionRelation.model_validate(
                    {
                        "target_id": tid,
                        "type": r.get("type"),
                        "notes": str(r.get("notes") or ""),
                    }
                )
                cleaned.append(fr.model_dump(mode="json"))
            except Exception as e:
                warnings.append(f"{eid}→{tid}: 无法解析关系 ({e})")
        idx = id_to_index[eid]
        entities_data[idx]["relations"] = cleaned
    data["entities"] = entities_data
    return FactionsSection.model_validate(data), warnings


def apply_culture_relations_patch(
    section: CulturesSection, patch: dict[str, Any]
) -> tuple[CulturesSection, list[str]]:
    warnings: list[str] = []
    rows = patch.get("entities")
    if not isinstance(rows, list):
        return section, ["模型输出缺少 entities 数组，未修改"]
    data = section.model_dump(mode="json")
    entities_data: list[dict[str, Any]] = data.get("entities") or []
    valid_ids = {str(e.get("id", "")).strip() for e in entities_data if isinstance(e, dict) and str(e.get("id", "")).strip()}
    if not valid_ids:
        return section, ["当前无文化实体，跳过合并"]
    id_to_index = {str(e["id"]).strip(): i for i, e in enumerate(entities_data) if isinstance(e, dict) and e.get("id")}
    for row in rows:
        if not isinstance(row, dict):
            continue
        eid = str(row.get("id") or "").strip()
        if eid not in id_to_index:
            warnings.append(f"跳过未知文化实体 id: {eid}")
            continue
        rels_in = row.get("relations")
        if not isinstance(rels_in, list):
            warnings.append(f"{eid}: relations 不是数组，已跳过该条")
            continue
        cleaned: list[dict[str, Any]] = []
        for r in rels_in:
            if not isinstance(r, dict):
                continue
            tid = str(r.get("target_id") or "").strip()
            if tid not in valid_ids:
                warnings.append(f"{eid}: 非法 target_id {tid!r}，已丢弃该边")
                continue
            if tid == eid:
                warnings.append(f"{eid}: 忽略自环 target_id")
                continue
            try:
                cr = CultureRelation.model_validate(
                    {
                        "target_id": tid,
                        "type": str(r.get("type") or "influence").strip() or "influence",
                        "notes": str(r.get("notes") or ""),
                    }
                )
                cleaned.append(cr.model_dump(mode="json"))
            except Exception as e:
                warnings.append(f"{eid}→{tid}: 无法解析关系 ({e})")
        idx = id_to_index[eid]
        entities_data[idx]["relations"] = cleaned
    data["entities"] = entities_data
    return CulturesSection.model_validate(data), warnings


async def refresh_world_faction_relations(
    world: World, *, creative_mode: str | None
) -> tuple[World, list[str]]:
    if not world.factions.entities:
        return world, ["当前无派系实体，未调用模型"]
    mode_eff = _effective_creative_mode(world, creative_mode)
    addon = structure_sync_addon(mode_eff) if mode_eff else ""
    system = FACTION_RELATIONS_SYSTEM + (addon if addon else "")
    payload = json.dumps(world.factions.model_dump(mode="json"), ensure_ascii=False, indent=2)
    user = "以下为当前 factions 节完整 JSON。请按系统规则仅输出含 relations 的 entities 列表：\n\n" + payload
    raw = await chat_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        model=_structure_model_name(),
        temperature=0.2,
        max_tokens=8192,
    )
    parsed = parse_structure_json(raw)
    if not isinstance(parsed, dict):
        raise ValueError("parsed root is not an object")
    new_fac, warnings = apply_faction_relations_patch(world.factions, parsed)
    data = world.model_dump(mode="json")
    data["factions"] = new_fac.model_dump(mode="json")
    return World.model_validate(data), warnings


async def refresh_world_culture_relations(
    world: World, *, creative_mode: str | None
) -> tuple[World, list[str]]:
    if not world.cultures.entities:
        return world, ["当前无文化/宗教实体，未调用模型"]
    mode_eff = _effective_creative_mode(world, creative_mode)
    addon = structure_sync_addon(mode_eff) if mode_eff else ""
    system = CULTURE_RELATIONS_SYSTEM + (addon if addon else "")
    payload = json.dumps(world.cultures.model_dump(mode="json"), ensure_ascii=False, indent=2)
    user = "以下为当前 cultures 节完整 JSON。请按系统规则仅输出含 relations 的 entities 列表：\n\n" + payload
    raw = await chat_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        model=_structure_model_name(),
        temperature=0.2,
        max_tokens=8192,
    )
    parsed = parse_structure_json(raw)
    if not isinstance(parsed, dict):
        raise ValueError("parsed root is not an object")
    new_cul, warnings = apply_culture_relations_patch(world.cultures, parsed)
    data = world.model_dump(mode="json")
    data["cultures"] = new_cul.model_dump(mode="json")
    return World.model_validate(data), warnings
