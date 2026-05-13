"""跨小节引用一致性检查（纯本地、不修改 world）。"""

from __future__ import annotations

from typing import Any

from worldforger.schemas import World

_MAX_WARNINGS = 120


def _norm(s: object) -> str:
    return str(s or "").strip()


def _as_relation_list(raw: object) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def lint_world_references(world: World) -> dict[str, Any]:
    """
    检查地理 regions.relations、派系/文化 relations.target_id、历史 linked_faction_ids、
    职业 exclusive_faction_id、境界技能树 prereq_ids、subclass_paths.profession_id 等。

    返回：ok（无问题时 True）、warnings（人类可读短句列表）、counts（各分类计数）。
    """
    warnings: list[str] = []
    counts = {
        "geography": 0,
        "factions": 0,
        "cultures": 0,
        "history": 0,
        "power_system": 0,
    }

    def push(msg: str, key: str) -> None:
        if len(warnings) >= _MAX_WARNINGS:
            return
        warnings.append(msg)
        counts[key] = counts.get(key, 0) + 1

    # --- 派系 id 集（历史、职业独占派系等复用） ---
    faction_ids = {_norm(e.id) for e in world.factions.entities if _norm(e.id)}

    # --- 地理：区域 id 与 relations.target_id（先收齐 id，再校验边） ---
    regions_raw = [r for r in (world.geography.regions or []) if isinstance(r, dict)]
    region_ids: set[str] = set()
    seen_dup: set[str] = set()
    for r in regions_raw:
        rid = _norm(r.get("id"))
        if not rid:
            continue
        if rid in region_ids:
            seen_dup.add(rid)
        region_ids.add(rid)
    for rid in seen_dup:
        push(f"地理：区域 id「{rid}」重复出现", "geography")

    has_geo_rels = any(_as_relation_list(r.get("relations")) for r in regions_raw)
    if not region_ids and has_geo_rels:
        push("地理：存在 relations 但无任何区域带 id，无法解析 target_id", "geography")
    else:
        for ri, r in enumerate(regions_raw):
            rid = _norm(r.get("id"))
            rname = _norm(r.get("name")) or rid or f"第{ri + 1}条"
            if not rid:
                push(f"地理：区域「{rname}」缺少稳定 id，relations 难以对照", "geography")
            for rel in _as_relation_list(r.get("relations")):
                tid = _norm(rel.get("target_id"))
                if not tid:
                    push(f"地理：区域「{rname}」的 relation 缺少 target_id", "geography")
                elif tid not in region_ids:
                    push(f"地理：区域「{rname}」的 relation 指向未知区域 target_id「{tid}」", "geography")

    # --- 派系 relations ---
    for ent in world.factions.entities:
        eid = _norm(ent.id)
        label = _norm(ent.name) or eid or "（无 id 派系）"
        for rel in ent.relations:
            tid = _norm(rel.target_id)
            if not tid:
                push(f"派系：「{label}」的关系缺少 target_id", "factions")
            elif tid not in faction_ids:
                push(f"派系：「{label}」的关系指向未知派系 target_id「{tid}」", "factions")

    # --- 文化 relations（实体间） ---
    culture_ids = {_norm(e.id) for e in world.cultures.entities if _norm(e.id)}
    for ent in world.cultures.entities:
        cid = _norm(ent.id)
        label = _norm(ent.name) or cid or "（无 id 文化实体）"
        for rel in ent.relations:
            tid = _norm(rel.target_id)
            if not tid:
                push(f"文化·宗教：「{label}」的关系缺少 target_id", "cultures")
            elif tid not in culture_ids:
                push(f"文化·宗教：「{label}」的关系指向未知实体 target_id「{tid}」", "cultures")

    # --- 历史 linked_faction_ids ---
    for ev in world.history.events:
        title = _norm(ev.title) or "（无标题事件）"
        for raw in ev.linked_faction_ids or []:
            fid = _norm(raw)
            if not fid:
                continue
            if fid not in faction_ids:
                push(f"历史：事件「{title}」的 linked_faction_id「{fid}」无对应派系", "history")

    # --- 职业 exclusive_faction_id ---
    for bi, block in enumerate(world.power_system.profession_system.by_tier or []):
        for pr in block.professions:
            fac = _norm(pr.exclusive_faction_id)
            if not fac:
                continue
            pname = _norm(pr.name) or _norm(pr.id) or "未命名职业"
            if fac not in faction_ids:
                push(
                    f"境界职业：块 {bi + 1}「{pname}」的 exclusive_faction_id「{fac}」无对应派系",
                    "power_system",
                )

    # --- 境界：技能树 prereq_ids；subclass_paths.profession_id ---
    by_tier = world.power_system.profession_system.by_tier or []
    for ti, tier in enumerate(world.power_system.tiers):
        tname = _norm(tier.name) or f"境 {ti + 1}"

        def check_tree(nodes: list[Any], tree_label: str) -> None:
            ids = {_norm(n.id) for n in nodes if _norm(n.id)}
            for n in nodes:
                nid = _norm(n.id)
                nn = _norm(n.name) or nid or "未命名节点"
                for pr in n.prereq_ids or []:
                    p = _norm(pr)
                    if not p:
                        continue
                    if p not in ids:
                        push(
                            f"境界「{tname}」{tree_label}：节点「{nn}」的 prereq_ids 引用未知 id「{p}」",
                            "power_system",
                        )

        check_tree(tier.skill_tree, "通用技能树")
        prof_ids: set[str] = set()
        if ti < len(by_tier):
            for p in by_tier[ti].professions:
                pid = _norm(p.id)
                if pid:
                    prof_ids.add(pid)
        for spi, sp in enumerate(tier.subclass_paths):
            spl = _norm(sp.name) or _norm(sp.id) or f"子类 {spi + 1}"
            check_tree(sp.skill_tree, f"子类「{spl}」技能树")
            pid = _norm(sp.profession_id)
            if not pid:
                continue
            if not prof_ids:
                push(
                    f"境界「{tname}」子类「{spl}」填写了 profession_id「{pid}」，但该境职业表无可用 id",
                    "power_system",
                )
            elif pid not in prof_ids:
                push(
                    f"境界「{tname}」子类「{spl}」的 profession_id「{pid}」在同境职业表中不存在",
                    "power_system",
                )

    return {
        "ok": len(warnings) == 0,
        "warnings": warnings,
        "counts": counts,
        "truncated": len(warnings) >= _MAX_WARNINGS,
    }
