"""将结构化同步器返回的 JSON 归一化，减少因字段别名或类型偏差导致的校验失败（item_quality_system、geography 等）。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _stable_region_id(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\0")
    return "rg_" + h.hexdigest()[:12]


def _note(notes: dict[str, list[str]], section: str, message: str) -> None:
    notes.setdefault(section, []).append(message)


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


def _normalize_str_list_field(val: Any) -> list[str]:
    """landmarks / resources 等：模型常输出对象数组或单字符串，需压成 list[str]。"""
    if val is None:
        return []
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return []
        if "\n" in s:
            return [x.strip() for x in s.split("\n") if x.strip()]
        if "," in s and len(s) < 400:
            return [x.strip() for x in s.split(",") if x.strip()]
        return [s]
    if isinstance(val, list):
        out: list[str] = []
        for x in val:
            if x is None:
                continue
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
            elif isinstance(x, dict):
                label = _as_str(x.get("name") or x.get("label") or x.get("title")).strip()
                if label:
                    out.append(label)
            else:
                t = _as_str(x).strip()
                if t:
                    out.append(t)
        return out
    return []


def _normalize_geo_relation_item(raw: Any) -> dict[str, Any] | None:
    if raw is None or not isinstance(raw, dict):
        return None
    tid = _as_str(raw.get("target_id") or raw.get("target") or raw.get("to") or raw.get("id")).strip()
    if not tid:
        return None
    typ = _as_str(raw.get("type") or raw.get("relation_type") or raw.get("关系") or "关联").strip() or "neutral"
    notes = _as_str(raw.get("notes") or raw.get("note") or raw.get("说明"))
    return {"target_id": tid, "type": typ, "notes": notes}


def _normalize_geo_relations(val: Any) -> list[dict[str, Any]]:
    if val is None:
        return []
    if isinstance(val, dict):
        one = _normalize_geo_relation_item(val)
        return [one] if one else []
    if not isinstance(val, list):
        return []
    out: list[dict[str, Any]] = []
    for item in val:
        if isinstance(item, dict):
            r = _normalize_geo_relation_item(item)
            if r:
                out.append(r)
    return out


def _normalize_region_item(raw: Any) -> tuple[dict[str, Any] | None, bool]:
    """返回 (区域对象, 是否为本轮生成的稳定 id)。"""
    if raw is None:
        return None, False
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None, False
        rid = _stable_region_id(s, "")
        return {"id": rid, "name": s, "summary": "", "terrain": "", "relations": []}, True
    if not isinstance(raw, dict):
        return None, False
    d = dict(raw)
    rid = _as_str(d.get("id") or d.get("region_id") or "").strip()
    name = (
        _as_str(
            d.get("name")
            or d.get("title")
            or d.get("label")
            or d.get("区域")
            or d.get("大陆")
            or d.get("王国")
        ).strip()
    )
    if not name:
        name = "未命名区域"
    summary = _join_if_list(d.get("summary") or d.get("desc") or d.get("description") or d.get("概述"))
    terrain = _as_str(
        d.get("terrain")
        or d.get("landform")
        or d.get("地形")
        or d.get("地貌")
        or d.get("climate")
        or d.get("气候带")
    ).strip()
    relations = _normalize_geo_relations(d.get("relations"))
    synthesized = False
    if not rid:
        rid = _stable_region_id(name, summary)
        synthesized = True
    out: dict[str, Any] = {
        "id": rid,
        "name": name,
        "summary": summary,
        "terrain": terrain,
        "relations": relations,
    }
    for k, v in d.items():
        if k in out or k in ("desc", "description", "概述", "region_id", "climate"):
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, list) and all(type(x) in (str, int, float, bool, type(None)) for x in v):
            out[k] = [_as_str(x) for x in v]
    return out, synthesized


def _normalize_geography_dict(section: dict[str, Any], notes: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """将 LLM 输出的 geography 小节压成可通过 GeographySection 校验的结构。"""
    out: dict[str, Any] = {}
    if "summary" in section:
        out["summary"] = _join_if_list(section.get("summary"))
    if "climate_notes" in section:
        out["climate_notes"] = _join_if_list(section.get("climate_notes"))
    if "map_notes" in section:
        out["map_notes"] = _join_if_list(section.get("map_notes"))
    if "landmarks" in section:
        lm_raw = section.get("landmarks")
        if notes is not None and isinstance(lm_raw, list) and any(isinstance(x, dict) for x in lm_raw):
            _note(notes, "geography", "landmarks 已从对象数组压平为字符串列表")
        out["landmarks"] = _normalize_str_list_field(lm_raw)
    if "resources" in section:
        out["resources"] = _normalize_str_list_field(section.get("resources"))

    raw_regions = section.get("regions")
    if raw_regions is not None:
        if isinstance(raw_regions, dict):
            if notes is not None:
                _note(notes, "geography", "regions 已由单对象包装为数组")
            raw_regions = [raw_regions]
        if isinstance(raw_regions, list):
            regions: list[dict[str, Any]] = []
            any_syn = False
            for item in raw_regions:
                nr, syn = _normalize_region_item(item)
                if nr:
                    if syn:
                        any_syn = True
                    regions.append(nr)
            if regions:
                out["regions"] = regions
                if notes is not None and any_syn:
                    _note(notes, "geography", "已为缺少 id 的区域生成稳定占位 id（rg_ + 哈希）")
    return out


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


def _normalize_culture_relation_item(raw: Any) -> dict[str, Any] | None:
    if raw is None or not isinstance(raw, dict):
        return None
    tid = _as_str(raw.get("target_id") or raw.get("target") or raw.get("to")).strip()
    if not tid:
        return None
    typ = _as_str(raw.get("type") or raw.get("relation_type") or "influence").strip() or "influence"
    notes = _as_str(raw.get("notes") or raw.get("note") or "")
    return {"target_id": tid, "type": typ, "notes": notes}


def _normalize_culture_relations(val: Any) -> list[dict[str, Any]]:
    if val is None:
        return []
    if isinstance(val, dict):
        one = _normalize_culture_relation_item(val)
        return [one] if one else []
    if not isinstance(val, list):
        return []
    out: list[dict[str, Any]] = []
    for item in val:
        if isinstance(item, dict):
            r = _normalize_culture_relation_item(item)
            if r:
                out.append(r)
    return out


def _coerce_culture_kind(raw: Any) -> str:
    s = _as_str(raw).strip().lower()
    if s in ("culture", "religion", "syncretic"):
        return s
    t = _as_str(raw)
    if "教" in t or "神" in t:
        return "religion"
    if "混" in t or "融合" in t or "综摄" in t:
        return "syncretic"
    return "culture"


def _normalize_culture_entity(raw: Any) -> dict[str, Any] | None:
    if raw is None or not isinstance(raw, dict):
        return None
    d = dict(raw)
    cid = _as_str(d.get("id") or d.get("culture_id") or d.get("faith_id")).strip()
    name = _as_str(d.get("name") or d.get("title") or d.get("label") or "").strip()
    if not cid or not name:
        return None
    kind = _coerce_culture_kind(d.get("kind") or d.get("type") or d.get("类型") or "culture")
    if kind not in ("culture", "religion", "syncretic"):
        kind = "culture"
    summary = _join_if_list(d.get("summary") or d.get("desc") or d.get("description"))
    tenets = _join_if_list(d.get("tenets") or d.get("beliefs") or d.get("教义") or d.get("信念"))
    practices = _join_if_list(d.get("practices") or d.get("rites") or d.get("仪式"))
    sacred_raw = d.get("sacred_sites") or d.get("sites") or d.get("圣地") or d.get("中心")
    if isinstance(sacred_raw, str):
        sacred_sites = [x.strip() for x in sacred_raw.replace(",", "\n").split("\n") if x.strip()]
    else:
        sacred_sites = _normalize_str_list_field(sacred_raw)
    key_figures = _normalize_str_list_field(d.get("key_figures") or d.get("figures") or d.get("领袖"))
    relations = _normalize_culture_relations(d.get("relations"))
    return {
        "id": cid,
        "name": name,
        "kind": kind,
        "summary": summary,
        "tenets": tenets,
        "practices": practices,
        "sacred_sites": sacred_sites,
        "key_figures": key_figures,
        "relations": relations,
    }


def _normalize_cultures_dict(section: dict[str, Any], notes: dict[str, list[str]] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "summary" in section:
        out["summary"] = _as_str(section.get("summary"))
    raw_ent = section.get("entities")
    if raw_ent is None and "traditions" in section:
        raw_ent = section.get("traditions")
        if notes is not None:
            _note(notes, "cultures", "已将 traditions 视为 entities")
    if raw_ent is None:
        return out
    if isinstance(raw_ent, dict):
        if notes is not None:
            _note(notes, "cultures", "entities 已由单对象包装为数组")
        raw_ent = [raw_ent]
    if not isinstance(raw_ent, list):
        return out
    entities: list[dict[str, Any]] = []
    for item in raw_ent:
        ne = _normalize_culture_entity(item)
        if ne:
            entities.append(ne)
    if entities:
        out["entities"] = entities
    return out


def normalize_structure_patch_detailed(
    patch: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """
    返回 (归一化后的 patch, 归一化说明)。
    说明按板块分组，供前端/日志区分「模型未输出」与「输出经修正后合并」。
    """
    notes: dict[str, list[str]] = {}
    p = dict(patch)

    if "geography" in p:
        raw = p["geography"]
        if isinstance(raw, str):
            try:
                p["geography"] = json.loads(raw.strip())
                _note(notes, "geography", "已从 JSON 字符串解析 geography")
            except (json.JSONDecodeError, TypeError, ValueError):
                del p["geography"]
                _note(notes, "geography", "geography 为非法 JSON 字符串，已丢弃该键")
        if "geography" in p:
            raw = p["geography"]
            if isinstance(raw, dict):
                p["geography"] = _normalize_geography_dict(raw, notes=notes)
            elif isinstance(raw, list) and raw and all(isinstance(x, dict) for x in raw):
                _note(notes, "geography", "顶层 geography 数组已视为 regions")
                p["geography"] = _normalize_geography_dict({"regions": raw}, notes=notes)
            else:
                del p["geography"]
                _note(notes, "geography", "geography 根类型无效，已丢弃该键")

    if "culture" in p and "cultures" not in p and isinstance(p["culture"], dict):
        p["cultures"] = p.pop("culture")
        _note(notes, "cultures", "已将顶层 culture 映射为 cultures")

    if "cultures" in p:
        raw = p["cultures"]
        if isinstance(raw, dict):
            p["cultures"] = _normalize_cultures_dict(raw, notes=notes)
        else:
            del p["cultures"]
            _note(notes, "cultures", "cultures 根类型无效，已丢弃该键")

    if "item_quality_system" not in p:
        if "items" in p and isinstance(p["items"], dict):
            p["item_quality_system"] = p.pop("items")
            _note(notes, "item_quality_system", "已将顶层 items 映射为 item_quality_system")
        elif "item_grades" in p:
            ig = p.pop("item_grades")
            if isinstance(ig, list):
                p["item_quality_system"] = {"grades": ig}
            elif isinstance(ig, dict):
                p["item_quality_system"] = ig
            _note(notes, "item_quality_system", "已将顶层 item_grades 映射为 item_quality_system")

    if "item_quality_system" in p and isinstance(p["item_quality_system"], dict):
        p["item_quality_system"] = _normalize_item_quality_dict(p["item_quality_system"])

    return p, notes


def normalize_structure_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """
    返回新 patch 副本：合并顶层别名、归一化 geography、item_quality_system、cultures 等。
    """
    return normalize_structure_patch_detailed(patch)[0]
