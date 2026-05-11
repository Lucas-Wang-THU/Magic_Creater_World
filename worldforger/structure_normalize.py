"""将结构化同步器返回的 JSON 归一化，减少因字段别名或类型偏差导致的校验失败（尤其 item_quality_system）。"""

from __future__ import annotations

from typing import Any


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float, bool)):
        return str(v)
    return ""


def _join_if_list(v: Any) -> str:
    if isinstance(v, list):
        return "\n".join(_as_str(x) for x in v if x is not None)
    return _as_str(v)


def _normalize_grade_item(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        return {
            "name": s,
            "rarity_narrative": "",
            "typical_effects": "",
            "binding_rules": "",
        }
    if not isinstance(raw, dict):
        return None
    d = dict(raw)
    # 常见别名 → schema 字段
    name = (
        d.get("name")
        or d.get("grade")
        or d.get("tier")
        or d.get("title")
        or d.get("label")
        or d.get("档位")
        or d.get("品质")
    )
    name_s = _as_str(name).strip() or "未命名档位"
    rarity = (
        d.get("rarity_narrative")
        or d.get("rarity")
        or d.get("narrative")
        or d.get("稀有度叙事")
        or d.get("稀有度")
    )
    effects = d.get("typical_effects") or d.get("effects") or d.get("效果") or d.get("描述")
    rules = d.get("binding_rules") or d.get("rules") or d.get("限制") or d.get("绑定规则")
    return {
        "name": name_s,
        "rarity_narrative": _join_if_list(rarity),
        "typical_effects": _join_if_list(effects),
        "binding_rules": _join_if_list(rules),
    }


def _normalize_item_quality_dict(section: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "summary" in section:
        out["summary"] = _as_str(section.get("summary"))
    raw_grades = section.get("grades")
    if raw_grades is None:
        return out
    if not isinstance(raw_grades, list):
        return out
    grades: list[dict[str, Any]] = []
    for g in raw_grades:
        ng = _normalize_grade_item(g)
        if ng:
            grades.append(ng)
    if grades:
        out["grades"] = grades
    return out


def normalize_structure_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """
    返回新 patch 副本：合并顶层别名、归一化 item_quality_system.grades。
    """
    p = dict(patch)

    # 顶层键别名（模型常误用 items / item_grades）
    if "item_quality_system" not in p:
        if "items" in p and isinstance(p["items"], dict):
            p["item_quality_system"] = p.pop("items")
        elif "item_grades" in p:
            ig = p.pop("item_grades")
            if isinstance(ig, list):
                p["item_quality_system"] = {"grades": ig}
            elif isinstance(ig, dict):
                p["item_quality_system"] = ig

    if "item_quality_system" in p and isinstance(p["item_quality_system"], dict):
        p["item_quality_system"] = _normalize_item_quality_dict(p["item_quality_system"])

    return p
