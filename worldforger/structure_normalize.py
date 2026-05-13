"""将结构化同步器返回的 JSON 归一化，减少因字段别名或类型偏差导致的校验失败（item_quality_system、geography 等）。"""

from __future__ import annotations

import hashlib
import json
import re
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
    tid = _as_str(
        raw.get("target_id") or raw.get("target") or raw.get("to") or raw.get("id") or raw.get("对方")
    ).strip()
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
        d.get("terrain") or d.get("landform") or d.get("地形") or d.get("地貌") or d.get("terrain_type")
    ).strip()
    climate_raw = _join_if_list(
        d.get("climate") or d.get("气候") or d.get("气候带") or d.get("local_climate") or d.get("局地气候")
    ).strip()
    if not terrain and climate_raw:
        terrain = climate_raw
    notes = _join_if_list(
        d.get("notes")
        or d.get("备注")
        or d.get("note")
        or d.get("旅行")
        or d.get("hooks")
        or d.get("dangers")
        or d.get("风险")
    ).strip()
    relations = _normalize_geo_relations(d.get("relations"))
    landmarks = _normalize_str_list_field(d.get("landmarks") or d.get("地标") or d.get("landmark"))
    resources = _normalize_str_list_field(d.get("resources") or d.get("资源") or d.get("resource"))
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
    if landmarks:
        out["landmarks"] = landmarks
    if resources:
        out["resources"] = resources
    if climate_raw and climate_raw != terrain:
        out["climate"] = climate_raw
    if notes:
        out["notes"] = notes
    for k, v in d.items():
        if k in out or k in (
            "desc",
            "description",
            "概述",
            "region_id",
            "climate",
            "气候",
            "气候带",
            "local_climate",
            "局地气候",
            "landmarks",
            "地标",
            "resources",
            "资源",
            "notes",
            "备注",
            "note",
            "旅行",
            "hooks",
            "dangers",
            "风险",
        ):
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        elif isinstance(v, list) and all(type(x) in (str, int, float, bool, type(None)) for x in v):
            out[k] = [_as_str(x) for x in v]
    return out, synthesized


def _normalize_geography_dict(section: dict[str, Any], notes: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """将 LLM 输出的 geography 小节压成可通过 GeographySection 校验的结构。"""
    if not isinstance(section, dict):
        return {}
    d = dict(section)
    out: dict[str, Any] = {}

    sum_raw = (
        d.get("summary")
        or d.get("overview")
        or d.get("geo_summary")
        or d.get("地理概况")
        or d.get("概况")
    )
    if sum_raw is not None:
        out["summary"] = _join_if_list(sum_raw)

    cn_raw = d.get("climate_notes")
    if cn_raw is None:
        cn_raw = d.get("weather") or d.get("气象") or d.get("全球气候") or d.get("气候说明")
    if cn_raw is None and isinstance(d.get("climate"), str):
        cn_raw = d.get("climate")
    if cn_raw is not None:
        out["climate_notes"] = _join_if_list(cn_raw)

    mn_raw = d.get("map_notes") or d.get("map") or d.get("地图") or d.get("cartography") or d.get("制图说明")
    if mn_raw is not None:
        out["map_notes"] = _join_if_list(mn_raw)

    if "landmarks" in d:
        lm_raw = d.get("landmarks")
        if notes is not None and isinstance(lm_raw, list) and any(isinstance(x, dict) for x in lm_raw):
            _note(notes, "geography", "landmarks 已从对象数组压平为字符串列表")
        out["landmarks"] = _normalize_str_list_field(lm_raw)
    if "resources" in d:
        out["resources"] = _normalize_str_list_field(d.get("resources"))

    extra_region_items: list[Any] = []
    for ak in (
        "continents",
        "continent",
        "areas",
        "locations",
        "subregions",
        "大陆",
        "子区域",
        "地理单元",
    ):
        if ak not in d:
            continue
        v = d.pop(ak)
        if isinstance(v, list):
            extra_region_items.extend(v)
            if notes is not None:
                _note(notes, "geography", f"已将别名键「{ak}」中的列表并入 regions")
        elif isinstance(v, dict):
            extra_region_items.append(v)
            if notes is not None:
                _note(notes, "geography", f"已将别名键「{ak}」中的单对象并入 regions")

    raw_regions = d.get("regions")
    if extra_region_items:
        if raw_regions is None:
            raw_regions = extra_region_items
        elif isinstance(raw_regions, dict):
            raw_regions = [raw_regions] + extra_region_items
        elif isinstance(raw_regions, list):
            raw_regions = list(raw_regions) + extra_region_items
        else:
            raw_regions = extra_region_items

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


def _clamp_reference_percent(val: Any, default: int = 55) -> int:
    if val is None or isinstance(val, bool):
        return default
    if isinstance(val, (int, float)):
        return int(max(0, min(100, round(float(val)))))
    s = _as_str(val).strip()
    if not s:
        return default
    try:
        return int(max(0, min(100, round(float(s)))))
    except ValueError:
        return default


def _attribute_stat_id_fallback(name: str, idx: int) -> str:
    base = name.strip()[:24] or "stat"
    h = hashlib.sha256(base.encode("utf-8")).hexdigest()[:10]
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", base, flags=re.UNICODE).strip("_")[:16]
    return (slug + "_" + h) if slug else f"st_{h}"


def _normalize_attribute_stat_item(raw: Any, idx: int) -> dict[str, Any] | None:
    """将单条维度归一成 AttributeStat 可校验的字典。"""
    if isinstance(raw, str) and raw.strip():
        nm = raw.strip()
        return {
            "id": _attribute_stat_id_fallback(nm, idx),
            "name": nm[:200],
            "abbreviation": "",
            "intro": "",
            "description": "",
            "scale": "",
            "typical_use": "",
            "reference_percent": _clamp_reference_percent(55),
        }
    if not isinstance(raw, dict):
        return None
    d = dict(raw)
    name = _as_str(
        d.get("name")
        or d.get("title")
        or d.get("label")
        or d.get("dimension")
        or d.get("维度")
        or d.get("属性")
    ).strip()
    cid = _as_str(d.get("id") or d.get("stat_id") or d.get("key") or d.get("code")).strip()
    if not name and not cid:
        return None
    if not cid:
        cid = _attribute_stat_id_fallback(name or "x", idx)
    if not name:
        name = cid[:200]
    abbrev = _as_str(d.get("abbreviation") or d.get("abbr") or d.get("短名")).strip()
    intro = _as_str(d.get("intro") or d.get("简介") or d.get("brief") or d.get("summary_short")).strip()
    desc = _join_if_list(d.get("description") or d.get("desc") or d.get("说明"))
    scale = _as_str(d.get("scale") or d.get("刻度") or d.get("范围")).strip()
    use = _as_str(d.get("typical_use") or d.get("use") or d.get("用途") or d.get("应用场景")).strip()
    ref_raw = d.get("reference_percent") or d.get("percent") or d.get("reference") or d.get("雷达") or d.get("强度")
    return {
        "id": cid[:80],
        "name": name[:200],
        "abbreviation": abbrev[:32],
        "intro": (intro or "")[:800],
        "description": (desc or "")[:4000],
        "scale": scale[:200],
        "typical_use": use[:200],
        "reference_percent": _clamp_reference_percent(ref_raw, 55),
    }


def _normalize_tier_average_item(raw: Any, idx: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    tier_name = _as_str(
        raw.get("tier_name") or raw.get("name") or raw.get("tier") or raw.get("境界")
    ).strip()
    if not tier_name:
        return None
    av_raw = raw.get("averages") or raw.get("values") or raw.get("means") or raw.get("avg") or {}
    if not isinstance(av_raw, dict):
        av_raw = {}
    averages: dict[str, int] = {}
    for k, val in av_raw.items():
        key = _as_str(k).strip()
        if not key:
            continue
        averages[key] = _clamp_reference_percent(val, 0)
    return {"tier_name": tier_name[:200], "averages": averages}


def _normalize_attribute_dict(section: dict[str, Any], *, notes: dict[str, list[str]]) -> dict[str, Any]:
    out = dict(section)
    # summary / design_notes 常见别名
    if not _as_str(out.get("summary")).strip():
        for k in ("overview", "总览"):
            if k in out and _as_str(out.get(k)).strip():
                out["summary"] = _as_str(out.get(k))
                _note(notes, "attribute_system", f"已将 {k} 映射为 summary")
                break
    if not _as_str(out.get("design_notes")).strip():
        for k in ("read_me", "读法", "how_to_read", "guide"):
            if k in out and _as_str(out.get(k)).strip():
                out["design_notes"] = _as_str(out.get(k))
                _note(notes, "attribute_system", f"已将 {k} 映射为 design_notes")
                break

    st = out.get("stats")
    if st is None or (isinstance(st, list) and len(st) == 0):
        for alt in ("dimensions", "attribute_stats", "stats_list", "dims", "axes"):
            altv = out.get(alt)
            if isinstance(altv, list) and len(altv) > 0:
                out["stats"] = list(altv)
                if alt != "stats":
                    del out[alt]
                _note(notes, "attribute_system", f"已将 {alt} 映射为 stats")
                break

    st = out.get("stats")
    if st is None:
        out["stats"] = []
    elif not isinstance(st, list):
        _note(notes, "attribute_system", "stats 非数组，已置为空列表")
        out["stats"] = []
    else:
        cleaned: list[dict[str, Any]] = []
        for i, row in enumerate(st):
            one = _normalize_attribute_stat_item(row, i)
            if one:
                cleaned.append(one)
        out["stats"] = cleaned

    tav = out.get("tier_average_profiles")
    if tav is None:
        for alt in ("tier_profiles", "realm_attribute_averages", "境界人物属性均值"):
            altv = out.get(alt)
            if isinstance(altv, list) and len(altv) > 0:
                out["tier_average_profiles"] = list(altv)
                if alt != "tier_average_profiles":
                    del out[alt]
                _note(notes, "attribute_system", f"已将 {alt} 映射为 tier_average_profiles")
                break
    tav = out.get("tier_average_profiles")
    if tav is None:
        out["tier_average_profiles"] = []
    elif not isinstance(tav, list):
        _note(notes, "attribute_system", "tier_average_profiles 非数组，已置为空列表")
        out["tier_average_profiles"] = []
    else:
        cleaned_tp: list[dict[str, Any]] = []
        for i, row in enumerate(tav):
            one = _normalize_tier_average_item(row, i)
            if one:
                cleaned_tp.append(one)
        out["tier_average_profiles"] = cleaned_tp
    return out


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


def _normalize_profession_entry(
    raw: Any, notes: dict[str, list[str]] | None, idx: int
) -> dict[str, Any] | None:
    if raw is None or not isinstance(raw, dict):
        return None
    pid = _as_str(raw.get("id") or raw.get("profession_id") or raw.get("code") or "").strip()
    name = _as_str(raw.get("name") or raw.get("title") or raw.get("label") or "").strip()
    if not pid and name:
        pid = f"prof_{idx}"
    if not pid:
        return None
    if not name:
        name = pid
    return {
        "id": pid[:200],
        "name": name[:400],
        "tagline": _as_str(raw.get("tagline") or raw.get("tag") or "").strip()[:600],
        "flavor": _join_if_list(raw.get("flavor") or raw.get("description") or raw.get("desc")),
        "exclusive_faction_id": _as_str(
            raw.get("exclusive_faction_id")
            or raw.get("faction_exclusive_id")
            or raw.get("faction_id")
            or raw.get("faction")
            or ""
        ).strip()[:200],
        "notes": _join_if_list(raw.get("notes") or raw.get("note") or ""),
    }


def _coerce_professions_list(val: Any, notes: dict[str, list[str]] | None) -> list[dict[str, Any]]:
    if val is None:
        return []
    if isinstance(val, dict):
        one = _normalize_profession_entry(val, notes, 0)
        return [one] if one else []
    if not isinstance(val, list):
        return []
    out: list[dict[str, Any]] = []
    for i, item in enumerate(val):
        if isinstance(item, dict):
            ne = _normalize_profession_entry(item, notes, i)
            if ne:
                out.append(ne)
    return out


def _normalize_profession_tier_block(
    raw: Any, fallback_tier_name: str, notes: dict[str, list[str]] | None
) -> dict[str, Any] | None:
    if raw is None or not isinstance(raw, dict):
        return None
    tn = (
        _as_str(raw.get("tier_name") or raw.get("tier") or raw.get("realm") or raw.get("境界") or "")
        .strip()
        or fallback_tier_name
    )
    prof_raw = raw.get("professions") or raw.get("careers") or raw.get("jobs") or raw.get("entries")
    if prof_raw is None and ("id" in raw or "name" in raw):
        one = _normalize_profession_entry(raw, notes, 0)
        if one:
            return {"tier_name": tn[:400], "professions": [one]}
        return None
    profs = _coerce_professions_list(prof_raw, notes)
    return {"tier_name": tn[:400], "professions": profs}


def _tier_names_from_power_tiers(raw_tiers: Any) -> list[str]:
    if not isinstance(raw_tiers, list):
        return []
    names: list[str] = []
    for t in raw_tiers:
        if isinstance(t, dict):
            names.append(_as_str(t.get("name")).strip())
        elif isinstance(t, str) and t.strip():
            names.append(t.strip())
    return names


def _normalize_profession_system_dict(
    raw: Any, tier_names: list[str], notes: dict[str, list[str]] | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {"summary": "", "design_notes": "", "by_tier": []}
    if raw is None:
        return out
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return out
        try:
            raw = json.loads(s)
            if notes is not None:
                _note(notes, "power_system", "profession_system 已从 JSON 字符串解析")
        except (json.JSONDecodeError, TypeError, ValueError):
            if notes is not None:
                _note(notes, "power_system", "profession_system 非法 JSON 字符串，已忽略")
            return out
    if not isinstance(raw, dict):
        return out
    out["summary"] = _join_if_list(raw.get("summary"))
    out["design_notes"] = _join_if_list(
        raw.get("design_notes") or raw.get("design") or raw.get("notes") or raw.get("说明")
    )
    bt = raw.get("by_tier") or raw.get("tiers_professions") or raw.get("per_tier")

    blocks: list[dict[str, Any]] = []

    if isinstance(bt, dict):
        if notes is not None:
            _note(notes, "power_system", "profession_system.by_tier 已由对象映射为数组")
        for k, v in bt.items():
            tn = _as_str(k).strip()
            profs = _coerce_professions_list(v, notes)
            blocks.append({"tier_name": tn, "professions": profs})
    elif isinstance(bt, list):
        if bt and all(isinstance(x, dict) for x in bt):
            flat_prof = all(
                isinstance(x, dict)
                and "professions" not in x
                and "tier_name" not in x
                and "typical_capabilities" not in x
                and "skill_tree" not in x
                and ("id" in x or "name" in x)
                for x in bt
            )
            if flat_prof:
                tn0 = tier_names[0] if tier_names else ""
                blocks = [{"tier_name": tn0, "professions": _coerce_professions_list(bt, notes)}]
                if notes is not None:
                    _note(notes, "power_system", "profession_system.by_tier 为扁平职业数组，已并入首境")
            else:
                for i, item in enumerate(bt):
                    fallback = tier_names[i] if i < len(tier_names) else ""
                    if isinstance(item, list):
                        blocks.append(
                            {
                                "tier_name": fallback or f"第{i + 1}境",
                                "professions": _coerce_professions_list(item, notes),
                            }
                        )
                        continue
                    nb = _normalize_profession_tier_block(item, fallback, notes)
                    if nb:
                        blocks.append(nb)
    if tier_names:
        name_map: dict[str, list[dict[str, Any]]] = {}
        display: dict[str, str] = {}
        for b in blocks:
            tn_raw = _as_str(b.get("tier_name")).strip()
            key = tn_raw.casefold() if tn_raw else ""
            profs = _coerce_professions_list(b.get("professions"), notes)
            if not key:
                key = "__anon__"
                if notes is not None:
                    _note(notes, "power_system", "部分职业块缺少 tier_name，已暂归未命名组")
            display.setdefault(key, tn_raw or key)
            name_map.setdefault(key, []).extend(profs)
        aligned: list[dict[str, Any]] = []
        for tn in tier_names:
            k = tn.strip().casefold()
            aligned.append({"tier_name": tn, "professions": name_map.pop(k, [])})
        for k, profs in name_map.items():
            if k == "__anon__" and not profs:
                continue
            aligned.append({"tier_name": display.get(k, k), "professions": profs})
        if notes is not None and blocks and len(blocks) != len(tier_names):
            _note(notes, "power_system", "profession_system.by_tier 已按境界表对齐并合并同名境界")
        out["by_tier"] = aligned
    else:
        out["by_tier"] = blocks
    return out


def _normalize_power_system_dict(
    section: dict[str, Any], notes: dict[str, list[str]] | None = None
) -> dict[str, Any]:
    out = dict(section)
    tier_names = _tier_names_from_power_tiers(out.get("tiers"))
    if "profession_system" in out and out["profession_system"] is not None:
        out["profession_system"] = _normalize_profession_system_dict(
            out["profession_system"], tier_names, notes=notes
        )
    return out


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

    # 人物属性：顶层别名（模型常输出 attributes）与 JSON 字符串
    zh_attr_key = "\u4eba\u7269\u5c5e\u6027"
    if "attribute_system" not in p:
        if "attributes" in p:
            alt = p.pop("attributes")
            if isinstance(alt, dict):
                p["attribute_system"] = alt
                _note(notes, "attribute_system", "已将顶层 attributes 映射为 attribute_system")
            elif isinstance(alt, list):
                p["attribute_system"] = {"stats": alt}
                _note(notes, "attribute_system", "已将顶层 attributes 数组包装为 attribute_system.stats")
        elif "character_attributes" in p:
            alt = p.pop("character_attributes")
            if isinstance(alt, dict):
                p["attribute_system"] = alt
                _note(notes, "attribute_system", "已将 character_attributes 映射为 attribute_system")
            elif isinstance(alt, list):
                p["attribute_system"] = {"stats": alt}
                _note(notes, "attribute_system", "已将 character_attributes 数组包装为 attribute_system.stats")
        elif zh_attr_key in p:
            alt = p.pop(zh_attr_key)
            if isinstance(alt, dict):
                p["attribute_system"] = alt
                _note(notes, "attribute_system", "已将顶层「人物属性」键映射为 attribute_system")

    if "attribute_system" in p and isinstance(p["attribute_system"], str):
        raw_s = p["attribute_system"].strip()
        try:
            parsed = json.loads(raw_s)
            if isinstance(parsed, list):
                p["attribute_system"] = {"stats": parsed}
                _note(notes, "attribute_system", "attribute_system JSON 根为数组，已包装为 stats")
            elif isinstance(parsed, dict):
                p["attribute_system"] = parsed
                _note(notes, "attribute_system", "已从 JSON 字符串解析 attribute_system")
            else:
                del p["attribute_system"]
                _note(notes, "attribute_system", "解析结果非对象/数组，已丢弃")
        except (json.JSONDecodeError, TypeError, ValueError):
            del p["attribute_system"]
            _note(notes, "attribute_system", "attribute_system 非法 JSON 字符串，已丢弃")

    zh_geo_key = "\u5730\u7406"  # 地理
    if zh_geo_key in p:
        alt_geo = p.pop(zh_geo_key)
        if isinstance(alt_geo, dict):
            if "geography" not in p:
                p["geography"] = alt_geo
            elif isinstance(p.get("geography"), dict):
                p["geography"] = {**alt_geo, **p["geography"]}
            else:
                p["geography"] = alt_geo
            _note(notes, "geography", "已将顶层「地理」键合并入 geography")
        elif isinstance(alt_geo, str) and alt_geo.strip():
            try:
                parsed = json.loads(alt_geo.strip())
                if isinstance(parsed, dict):
                    if "geography" not in p:
                        p["geography"] = parsed
                    elif isinstance(p.get("geography"), dict):
                        p["geography"] = {**parsed, **p["geography"]}
                    else:
                        p["geography"] = parsed
                    _note(notes, "geography", "已将顶层「地理」JSON 字符串合并入 geography")
                elif isinstance(parsed, list) and parsed and all(isinstance(x, dict) for x in parsed):
                    if "geography" not in p:
                        p["geography"] = {"regions": parsed}
                    elif isinstance(p.get("geography"), dict):
                        g = p["geography"]
                        er = g.get("regions")
                        if isinstance(er, list):
                            g["regions"] = list(er) + parsed
                        else:
                            g["regions"] = parsed
                    else:
                        p["geography"] = {"regions": parsed}
                    _note(notes, "geography", "已将顶层「地理」JSON 数组视为 regions 并入 geography")
                else:
                    p.setdefault("geography", {})
                    if isinstance(p["geography"], dict):
                        prev = _as_str(p["geography"].get("summary")).strip()
                        suf = alt_geo.strip()
                        p["geography"]["summary"] = (prev + "\n" + suf).strip() if prev else suf
            except (json.JSONDecodeError, TypeError, ValueError):
                p.setdefault("geography", {})
                if isinstance(p["geography"], dict):
                    prev = _as_str(p["geography"].get("summary")).strip()
                    suf = alt_geo.strip()
                    p["geography"]["summary"] = (prev + "\n" + suf).strip() if prev else suf
                else:
                    p["geography"] = {"summary": alt_geo.strip()}
                _note(notes, "geography", "已将顶层「地理」纯文本并入 geography.summary")

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

    if "attribute_system" in p and isinstance(p["attribute_system"], dict):
        p["attribute_system"] = _normalize_attribute_dict(p["attribute_system"], notes=notes)

    zh_prof_key = "\u804c\u4e1a\u4f53\u7cfb"  # 职业体系
    if "profession_system" in p and isinstance(p["profession_system"], dict):
        ps_root = p.pop("profession_system")
        if isinstance(p.get("power_system"), dict):
            base_ps = p["power_system"].get("profession_system")
            if isinstance(base_ps, dict):
                p["power_system"]["profession_system"] = {**base_ps, **ps_root}
            else:
                p["power_system"]["profession_system"] = ps_root
            _note(notes, "power_system", "已将顶层 profession_system 合并入 power_system")
        else:
            p["power_system"] = {"profession_system": ps_root}
            _note(notes, "power_system", "已将顶层 profession_system 包装为 power_system")

    if zh_prof_key in p and isinstance(p[zh_prof_key], dict):
        inner = p.pop(zh_prof_key)
        p.setdefault("power_system", {})
        if not isinstance(p["power_system"], dict):
            p["power_system"] = {}
        base_ps = p["power_system"].get("profession_system")
        if isinstance(base_ps, dict):
            p["power_system"]["profession_system"] = {**base_ps, **inner}
        else:
            p["power_system"]["profession_system"] = inner
        _note(notes, "power_system", "已将「职业体系」顶层键并入 power_system")

    if "power_system" in p:
        raw_ps = p["power_system"]
        if isinstance(raw_ps, str):
            raw_s = raw_ps.strip()
            try:
                p["power_system"] = json.loads(raw_s)
                _note(notes, "power_system", "已从 JSON 字符串解析 power_system")
            except (json.JSONDecodeError, TypeError, ValueError):
                del p["power_system"]
                _note(notes, "power_system", "power_system 非法 JSON 字符串，已丢弃该键")
        if "power_system" in p and isinstance(p["power_system"], dict):
            p["power_system"] = _normalize_power_system_dict(p["power_system"], notes=notes)

    return p, notes


def normalize_structure_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """
    返回新 patch 副本：合并顶层别名、归一化 geography、item_quality_system、cultures 等。
    """
    return normalize_structure_patch_detailed(patch)[0]
