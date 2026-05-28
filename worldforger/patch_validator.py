"""Code-level enforcement of structural constraints on sync patches.

These validators act as a safety net below the prompt layer: when an LLM
produces JSON that violates known rules, we fix or warn rather than letting
bad data through to world.json.
"""

from __future__ import annotations

from typing import Any


def validate_patch_constraints(patch: dict[str, Any]) -> list[str]:
    """Validate key constraints on a sync patch and return a list of warnings.

    Returns a list of warning strings (empty list = clean).  These warnings
    are informational — the caller may still apply the patch after logging.
    """
    warnings: list[str] = []
    _check_faction_relations(patch, warnings)
    _check_faction_key_figures(patch, warnings)
    _check_entities_are_arrays(patch, warnings)
    _check_region_relations(patch, warnings)
    return warnings


def _check_faction_relations(patch: dict[str, Any], warnings: list[str]) -> None:
    factions = patch.get("factions", {})
    if not isinstance(factions, dict):
        return
    entities = factions.get("entities", [])
    if not isinstance(entities, list):
        return
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        ent_name = ent.get("name", ent.get("id", "?"))
        relations = ent.get("relations", [])
        if not isinstance(relations, list):
            continue
        for i, rel in enumerate(relations):
            if not isinstance(rel, dict):
                continue
            rt = rel.get("type")
            valid_types = {"ally", "enemy", "neutral", "complex"}
            if rt is not None and rt not in valid_types:
                warnings.append(
                    f"派系「{ent_name}」relations[{i}].type = {rt!r} 不是合法值，"
                    f"已强制改为 'neutral'（合法值：{'/'.join(sorted(valid_types))})"
                )
                rel["type"] = "neutral"


def _check_faction_key_figures(patch: dict[str, Any], warnings: list[str]) -> None:
    factions = patch.get("factions", {})
    if not isinstance(factions, dict):
        return
    entities = factions.get("entities", [])
    if not isinstance(entities, list):
        return
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        ent_name = ent.get("name", ent.get("id", "?"))
        kf = ent.get("key_figures")
        if kf is None:
            continue
        if not isinstance(kf, list):
            warnings.append(
                f"派系「{ent_name}」key_figures 应为字符串数组，"
                f"收到 {type(kf).__name__}，已重置为空数组"
            )
            ent["key_figures"] = []
            continue
        # Check each entry is a string
        fixed_kf: list[str] = []
        had_fix = False
        for item in kf:
            if isinstance(item, str):
                fixed_kf.append(item)
            elif isinstance(item, dict):
                name = item.get("name", item.get("id", str(item)))
                if isinstance(name, str) and name:
                    fixed_kf.append(name)
                    had_fix = True
                else:
                    had_fix = True
            else:
                had_fix = True
        if had_fix:
            warnings.append(
                f"派系「{ent_name}」key_figures 包含非字符串条目，已自动提取名称"
            )
            ent["key_figures"] = fixed_kf


def _check_entities_are_arrays(patch: dict[str, Any], warnings: list[str]) -> None:
    """Ensure top-level entity lists inside sections are arrays, not single objects."""
    sections_with_entities = {
        "factions", "cultures", "characters", "ecology", "history", "economy",
    }
    for section_key in sections_with_entities:
        section = patch.get(section_key)
        if not isinstance(section, dict):
            continue
        entities = section.get("entities")
        if entities is None:
            continue
        if isinstance(entities, dict):
            # Single object — wrap in array
            section["entities"] = [entities]
            ent_name = entities.get("name", entities.get("id", "?"))
            warnings.append(
                f"「{section_key}」entities 收到单对象而非数组，"
                f"已自动包装（{ent_name}）"
            )


def _check_region_relations(patch: dict[str, Any], warnings: list[str]) -> None:
    geography = patch.get("geography", {})
    if not isinstance(geography, dict):
        return
    regions = geography.get("regions", [])
    if not isinstance(regions, list):
        return
    for region in regions:
        if not isinstance(region, dict):
            continue
        reg_name = region.get("name", region.get("id", "?"))
        relations = region.get("relations", [])
        if not isinstance(relations, list):
            continue
        for i, rel in enumerate(relations):
            if not isinstance(rel, dict):
                continue
            if "target_id" not in rel or not rel.get("target_id"):
                warnings.append(
                    f"地理「{reg_name}」relations[{i}] 缺少 target_id，已跳过"
                )
                # Mark for removal by setting a flag; caller should filter
                rel["_invalid"] = True
        # Filter out invalid relations
        region["relations"] = [r for r in relations if not r.get("_invalid")]
