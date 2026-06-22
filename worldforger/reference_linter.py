"""跨小节引用一致性检查（纯本地、不修改 world）。"""

from __future__ import annotations

import copy
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
    职业 exclusive_faction_id、境界技能树 prereq_ids、subclass_paths.profession_id、
    生态 biome/region、人物卡司引用、经济市场/商路/货币对区域与派系 id 等。

    返回：ok（无问题时 True）、warnings（人类可读短句列表）、counts（各分类计数）。
    """
    warnings: list[str] = []
    counts = {
        "geography": 0,
        "factions": 0,
        "cultures": 0,
        "history": 0,
        "power_system": 0,
        "ecology": 0,
        "characters": 0,
        "economy": 0,
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

    # --- 生态：biomes.linked_region_ids、species.biome_id ---
    biome_ids: set[str] = set()
    for b in world.ecology.biomes or []:
        if isinstance(b, dict) and _norm(b.get("id")):
            biome_ids.add(_norm(b.get("id")))
    for bi, b in enumerate(world.ecology.biomes or []):
        if not isinstance(b, dict):
            continue
        bid = _norm(b.get("id"))
        bname = _norm(b.get("name")) or bid or f"生境 {bi + 1}"
        for raw in b.get("linked_region_ids") or []:
            rid = _norm(raw)
            if not rid:
                continue
            if region_ids and rid not in region_ids:
                push(f"生态：生境「{bname}」的 linked_region_id「{rid}」无对应地理区域", "ecology")
    for si, sp in enumerate(world.ecology.species or []):
        if not isinstance(sp, dict):
            continue
        sname = _norm(sp.get("name")) or _norm(sp.get("id")) or f"物种 {si + 1}"
        bref = _norm(sp.get("biome_id"))
        if not bref:
            continue
        if not biome_ids:
            push(f"生态：物种「{sname}」填写了 biome_id「{bref}」但 biomes 中无可用 id", "ecology")
        elif bref not in biome_ids:
            push(f"生态：物种「{sname}」的 biome_id「{bref}」未在 biomes 中声明", "ecology")

    # --- 人物：faction_ids、home_region_id、relations 端点 ---
    char_ids: set[str] = set()
    for ent in world.characters.entities or []:
        if isinstance(ent, dict) and _norm(ent.get("id")):
            char_ids.add(_norm(ent.get("id")))
    for ei, ent in enumerate(world.characters.entities or []):
        if not isinstance(ent, dict):
            continue
        eid = _norm(ent.get("id"))
        label = _norm(ent.get("name")) or eid or f"角色 {ei + 1}"
        for raw in ent.get("faction_ids") or []:
            fid = _norm(raw)
            if not fid:
                continue
            if fid not in faction_ids:
                push(f"人物：「{label}」的 faction_id「{fid}」无对应派系", "characters")
        hri = _norm(ent.get("home_region_id"))
        if hri and region_ids and hri not in region_ids:
            push(f"人物：「{label}」的 home_region_id「{hri}」无对应地理区域", "characters")
    for ri, rel in enumerate(world.characters.relations or []):
        if not isinstance(rel, dict):
            continue
        s = _norm(rel.get("source_id"))
        t = _norm(rel.get("target_id"))
        if not s or not t:
            push(f"人物关系：第 {ri + 1} 条缺少 source_id 或 target_id", "characters")
            continue
        if char_ids and s not in char_ids:
            push(f"人物关系：source_id「{s}」不在当前卡司 id 列表中", "characters")
        if char_ids and t not in char_ids:
            push(f"人物关系：target_id「{t}」不在当前卡司 id 列表中", "characters")

    # --- 经济：货币发行方、市场区域/派系、商路端点 ---
    eco = world.economy
    for ci, cur in enumerate(eco.currencies or []):
        if not isinstance(cur, dict):
            continue
        clab = _norm(cur.get("name")) or _norm(cur.get("id")) or f"货币 {ci + 1}"
        iss = _norm(cur.get("issuer_faction_id"))
        if iss and iss not in faction_ids:
            push(f"经济：货币「{clab}」的 issuer_faction_id「{iss}」无对应派系", "economy")
    for mi, mkt in enumerate(eco.markets or []):
        if not isinstance(mkt, dict):
            continue
        mlab = _norm(mkt.get("name")) or _norm(mkt.get("id")) or f"市场 {mi + 1}"
        for raw in mkt.get("linked_region_ids") or []:
            rid = _norm(raw)
            if not rid:
                continue
            if region_ids and rid not in region_ids:
                push(f"经济：市场「{mlab}」的 linked_region_id「{rid}」无对应地理区域", "economy")
        for raw in mkt.get("dominant_faction_ids") or []:
            fid = _norm(raw)
            if not fid:
                continue
            if fid not in faction_ids:
                push(f"经济：市场「{mlab}」的 dominant_faction_id「{fid}」无对应派系", "economy")
    for ri, rte in enumerate(eco.trade_routes or []):
        if not isinstance(rte, dict):
            continue
        rlab = _norm(rte.get("name")) or _norm(rte.get("id")) or f"商路 {ri + 1}"
        fr = _norm(rte.get("from_region_id"))
        to = _norm(rte.get("to_region_id"))
        if fr and region_ids and fr not in region_ids:
            push(f"经济：商路「{rlab}」的 from_region_id「{fr}」无对应地理区域", "economy")
        if to and region_ids and to not in region_ids:
            push(f"经济：商路「{rlab}」的 to_region_id「{to}」无对应地理区域", "economy")
        for raw in rte.get("controlling_faction_ids") or []:
            fid = _norm(raw)
            if not fid:
                continue
            if fid not in faction_ids:
                push(f"经济：商路「{rlab}」的 controlling_faction_id「{fid}」无对应派系", "economy")

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


def fix_world_references(world: World) -> tuple[World, list[str]]:
    """
    在 **内存副本** 上执行保守自动修复并校验为 World。

    策略（不处理：重复区域 id、缺少区域 id、仅有 relations 却无 id 等需人工决策的问题）：

    - 地理：移除缺少 target_id 或 target_id 不在区域 id 集内的 relation 项。
    - 派系 / 文化：移除缺少 target_id 或 target 不在对应实体 id 集内的关系边。
    - 历史：从 linked_faction_ids 中移除不存在于派系表中的 id。
    - 经济：清空无效的 issuer_faction_id；从 markets / trade_routes 中移除无效的区域或派系 id 引用。
    - 境界职业：清空无效的 exclusive_faction_id。
    - 技能树（通用树与子类树）：从各节点的 prereq_ids 中移除不在本树节点 id 集内的引用。
    - 子类：清空无效的 profession_id（含该境无职业表但仍填写了 id 的情况）。

    返回 (修复后的 World, 人类可读操作日志列表)。
    """
    data = copy.deepcopy(world.model_dump(mode="json"))
    log: list[str] = []

    def _n(s: object) -> str:
        return str(s or "").strip()

    faction_ids = {
        _n(e.get("id"))
        for e in (data.get("factions") or {}).get("entities") or []
        if isinstance(e, dict) and _n(e.get("id"))
    }

    regions = (data.get("geography") or {}).get("regions") or []
    region_ids: set[str] = set()
    for r in regions:
        if isinstance(r, dict) and _n(r.get("id")):
            region_ids.add(_n(r.get("id")))

    for ri, r in enumerate(regions):
        if not isinstance(r, dict):
            continue
        rels = _as_relation_list(r.get("relations"))
        if not rels:
            continue
        rname = _n(r.get("name")) or _n(r.get("id")) or f"第{ri + 1}条"
        kept: list[dict[str, Any]] = []
        for rel in rels:
            if not isinstance(rel, dict):
                continue
            tid = _n(rel.get("target_id"))
            if not tid:
                log.append(f"已移除：地理「{rname}」无 target_id 的 relation")
                continue
            if region_ids and tid not in region_ids:
                log.append(f"已移除：地理「{rname}」→ 未知区域「{tid}」的 relation")
                continue
            kept.append(rel)
        if len(kept) != len(rels):
            r["relations"] = kept

    for ent in (data.get("factions") or {}).get("entities") or []:
        if not isinstance(ent, dict):
            continue
        label = _n(ent.get("name")) or _n(ent.get("id")) or "（无 id 派系）"
        rels = ent.get("relations")
        if not isinstance(rels, list):
            continue
        kept: list[dict[str, Any]] = []
        for rel in rels:
            if not isinstance(rel, dict):
                continue
            tid = _n(rel.get("target_id"))
            if not tid:
                log.append(f"已移除：派系「{label}」无 target_id 的关系")
                continue
            if tid not in faction_ids:
                log.append(f"已移除：派系「{label}」→ 未知派系「{tid}」的关系")
                continue
            kept.append(rel)
        if len(kept) != len(rels):
            ent["relations"] = kept

    cult_entities = (data.get("cultures") or {}).get("entities") or []
    culture_ids = {_n(e.get("id")) for e in cult_entities if isinstance(e, dict) and _n(e.get("id"))}
    for ent in cult_entities:
        if not isinstance(ent, dict):
            continue
        label = _n(ent.get("name")) or _n(ent.get("id")) or "（无 id 文化实体）"
        rels = ent.get("relations")
        if not isinstance(rels, list):
            continue
        kept = []
        for rel in rels:
            if not isinstance(rel, dict):
                continue
            tid = _n(rel.get("target_id"))
            if not tid:
                log.append(f"已移除：文化·宗教「{label}」无 target_id 的关系")
                continue
            if tid not in culture_ids:
                log.append(f"已移除：文化·宗教「{label}」→ 未知实体「{tid}」的关系")
                continue
            kept.append(rel)
        if len(kept) != len(rels):
            ent["relations"] = kept

    for ev in (data.get("history") or {}).get("events") or []:
        if not isinstance(ev, dict):
            continue
        title = _n(ev.get("title")) or "（无标题事件）"
        old = ev.get("linked_faction_ids")
        if not isinstance(old, list):
            continue
        new_ids: list[str] = []
        for raw in old:
            fid = _n(raw)
            if not fid:
                continue
            if fid not in faction_ids:
                log.append(f"已自历史事件「{title}」移除无效 linked_faction_id「{fid}」")
                continue
            new_ids.append(fid)
        old_nonempty = [_n(str(x)) for x in old if _n(str(x))]
        if new_ids != old_nonempty:
            ev["linked_faction_ids"] = new_ids

    ps = (data.get("power_system") or {}).get("profession_system") or {}
    by_tier = ps.get("by_tier") or []
    if not isinstance(by_tier, list):
        by_tier = []

    for bi, block in enumerate(by_tier):
        if not isinstance(block, dict):
            continue
        for pr in block.get("professions") or []:
            if not isinstance(pr, dict):
                continue
            fac = _n(pr.get("exclusive_faction_id"))
            if not fac:
                continue
            pname = _n(pr.get("name")) or _n(pr.get("id")) or "未命名职业"
            if fac not in faction_ids:
                pr["exclusive_faction_id"] = ""
                log.append(f"已清空：境界职业块 {bi + 1}「{pname}」无效的 exclusive_faction_id「{fac}」")

    tiers = (data.get("power_system") or {}).get("tiers") or []
    for ti, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            continue
        tname = _n(tier.get("name")) or f"境 {ti + 1}"
        prof_ids: set[str] = set()
        if ti < len(by_tier) and isinstance(by_tier[ti], dict):
            for p in by_tier[ti].get("professions") or []:
                if isinstance(p, dict) and _n(p.get("id")):
                    prof_ids.add(_n(p.get("id")))

        def fix_tree(nodes: object, tree_label: str) -> None:
            if not isinstance(nodes, list):
                return
            ids = {_n(n.get("id")) for n in nodes if isinstance(n, dict) and _n(n.get("id"))}
            for n in nodes:
                if not isinstance(n, dict):
                    continue
                prereqs = n.get("prereq_ids")
                if not isinstance(prereqs, list):
                    continue
                nn = _n(n.get("name")) or _n(n.get("id")) or "未命名节点"
                kept_pr: list[str] = []
                for pr in prereqs:
                    p = _n(pr)
                    if not p:
                        continue
                    if p not in ids:
                        log.append(
                            f"已移除：境界「{tname}」{tree_label} 节点「{nn}」无效的 prereq「{p}」"
                        )
                        continue
                    kept_pr.append(p)
                if len(kept_pr) != len([_n(x) for x in prereqs if _n(x)]):
                    n["prereq_ids"] = kept_pr

        fix_tree(tier.get("skill_tree") or [], "通用技能树")
        for spi, sp in enumerate(tier.get("subclass_paths") or []):
            if not isinstance(sp, dict):
                continue
            spl = _n(sp.get("name")) or _n(sp.get("id")) or f"子类 {spi + 1}"
            fix_tree(sp.get("skill_tree") or [], f"子类「{spl}」技能树")
            pid = _n(sp.get("profession_id"))
            if not pid:
                continue
            if not prof_ids:
                sp["profession_id"] = ""
                log.append(f"已清空：境界「{tname}」子类「{spl}」的 profession_id（该境无职业表）")
            elif pid not in prof_ids:
                sp["profession_id"] = ""
                log.append(f"已清空：境界「{tname}」子类「{spl}」无效的 profession_id「{pid}」")

    eco = data.get("economy")
    if isinstance(eco, dict):
        for cur in eco.get("currencies") or []:
            if not isinstance(cur, dict):
                continue
            iss = _n(cur.get("issuer_faction_id"))
            if iss and iss not in faction_ids:
                cur["issuer_faction_id"] = ""
                clab = _n(cur.get("name")) or _n(cur.get("id")) or "货币"
                log.append(f"已清空：经济货币「{clab}」无效的 issuer_faction_id「{iss}」")
        for mkt in eco.get("markets") or []:
            if not isinstance(mkt, dict):
                continue
            mlab = _n(mkt.get("name")) or _n(mkt.get("id")) or "市场"
            for key in ("linked_region_ids", "dominant_faction_ids"):
                old = mkt.get(key)
                if not isinstance(old, list):
                    continue
                kept: list[str] = []
                for raw in old:
                    x = _n(raw)
                    if not x:
                        continue
                    if key == "linked_region_ids" and region_ids and x not in region_ids:
                        log.append(f"已移除：经济市场「{mlab}」无效的 {key}「{x}」")
                        continue
                    if key == "dominant_faction_ids" and x not in faction_ids:
                        log.append(f"已移除：经济市场「{mlab}」无效的 {key}「{x}」")
                        continue
                    kept.append(x)
                if len(kept) != len([_n(str(z)) for z in old if _n(str(z))]):
                    mkt[key] = kept
        for rte in eco.get("trade_routes") or []:
            if not isinstance(rte, dict):
                continue
            rlab = _n(rte.get("name")) or _n(rte.get("id")) or "商路"
            fr = _n(rte.get("from_region_id"))
            if fr and region_ids and fr not in region_ids:
                rte["from_region_id"] = ""
                log.append(f"已清空：经济商路「{rlab}」无效的 from_region_id「{fr}」")
            to = _n(rte.get("to_region_id"))
            if to and region_ids and to not in region_ids:
                rte["to_region_id"] = ""
                log.append(f"已清空：经济商路「{rlab}」无效的 to_region_id「{to}」")
            old = rte.get("controlling_faction_ids")
            if not isinstance(old, list):
                continue
            kept2: list[str] = []
            for raw in old:
                x = _n(raw)
                if not x:
                    continue
                if x not in faction_ids:
                    log.append(f"已移除：经济商路「{rlab}」无效的 controlling_faction_id「{x}」")
                    continue
                kept2.append(x)
            if len(kept2) != len([_n(str(z)) for z in old if _n(str(z))]):
                rte["controlling_faction_ids"] = kept2

    # ── 人物关系：移除 source_id 或 target_id 不在卡司列表中的边 ──
    char_ids = set()
    for ent in (data.get("characters") or {}).get("entities") or []:
        if isinstance(ent, dict):
            cid = _n(ent.get("id"))
            if cid:
                char_ids.add(cid)
    if char_ids:
        char_rels = (data.get("characters") or {}).get("relations")
        if isinstance(char_rels, list):
            kept_rels = []
            for rel in char_rels:
                if not isinstance(rel, dict):
                    continue
                s = _n(rel.get("source_id"))
                t = _n(rel.get("target_id"))
                if not s or not t:
                    log.append("已移除：人物关系中缺少 source_id 或 target_id 的边")
                    continue
                if s not in char_ids:
                    log.append(f"已移除：人物关系 source_id「{s}」不在卡司列表中")
                    continue
                if t not in char_ids:
                    log.append(f"已移除：人物关系 target_id「{t}」不在卡司列表中")
                    continue
                kept_rels.append(rel)
            if len(kept_rels) != len(char_rels):
                data["characters"]["relations"] = kept_rels
                log.append(f"人物关系已清理：{len(char_rels)}→{len(kept_rels)} 条（移除了 {len(char_rels)-len(kept_rels)} 条无效边）")

    w2 = World.model_validate(data)
    return w2, log
