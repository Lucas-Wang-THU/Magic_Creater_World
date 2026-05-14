from __future__ import annotations

from worldforger.schemas import World


def world_to_markdown(w: World) -> str:
    m = w.meta
    def _norm(s: object) -> str:
        return str(s or "").strip()

    lines: list[str] = [
        f"# {m.name}",
        "",
        f"- **世界 ID**：`{m.id}`",
        f"- **版本**：{m.version}",
        f"- **更新**：{m.updated_at}",
        f"- **标签**：{', '.join(m.genre_tags) or '（无）'}",
        f"- **创作载体**：{m.creative_mode or '（未指定）'}",
        "",
        "## 地理",
        "",
        w.geography.summary or "（待补充）",
        "",
    ]
    if w.geography.climate_notes:
        lines += ["### 气候", "", w.geography.climate_notes, ""]
    regions = w.geography.regions or []
    if regions:
        lines += ["### 大陆与区域", ""]
        for r in regions:
            if not isinstance(r, dict):
                continue
            nm = (r.get("name") or r.get("id") or "（未命名区域）").strip() or "（未命名区域）"
            lines.append(f"#### {nm}")
            lines.append("")
            if (r.get("summary") or "").strip():
                lines += [r["summary"].strip(), ""]
            if (r.get("terrain") or "").strip():
                lines += [f"**地貌** {r['terrain'].strip()}", ""]
            if (r.get("climate") or "").strip():
                lines += [f"**局地气候** {r['climate'].strip()}", ""]
            if (r.get("notes") or "").strip():
                lines += [r["notes"].strip(), ""]
            lm = r.get("landmarks") or []
            if isinstance(lm, list) and lm:
                lines.append("**地标**")
                for x in lm:
                    if str(x).strip():
                        lines.append(f"- {str(x).strip()}")
                lines.append("")
            res = r.get("resources") or []
            if isinstance(res, list) and res:
                lines.append("**资源**")
                for x in res:
                    if str(x).strip():
                        lines.append(f"- {str(x).strip()}")
                lines.append("")
        lines.append("")
    elif w.geography.landmarks or w.geography.resources:
        if w.geography.landmarks:
            lines += ["### 地标", ""]
            lines += [f"- {x}" for x in w.geography.landmarks]
            lines.append("")
        if w.geography.resources:
            lines += ["### 资源", ""]
            lines += [f"- {x}" for x in w.geography.resources]
            lines.append("")

    eco = w.ecology
    if (eco.summary or "").strip() or (eco.design_notes or "").strip() or eco.biomes or eco.species:
        lines += ["## 生态", "", (eco.summary or "").strip() or "（待补充）", ""]
        if (eco.design_notes or "").strip():
            lines += ["### 设计说明", "", eco.design_notes.strip(), ""]
        if eco.biomes:
            lines += ["### 生境群落", ""]
            for b in eco.biomes:
                if not isinstance(b, dict):
                    continue
                nm = (b.get("name") or b.get("id") or "生境").strip()
                lines.append(f"#### {nm} (`{b.get('id', '')}`)")
                lines.append("")
                if (b.get("summary") or "").strip():
                    lines += [b["summary"].strip(), ""]
                lr = b.get("linked_region_ids") or []
                if isinstance(lr, list) and lr:
                    lines.append("**关联区域 id** " + "、".join(str(x) for x in lr if str(x).strip()))
                    lines.append("")
                if (b.get("climate_habitat") or "").strip():
                    lines += [f"**生境气候** {b['climate_habitat'].strip()}", ""]
            lines.append("")
        if eco.species:
            lines += ["### 物种与遭遇", ""]
            for s in eco.species:
                if not isinstance(s, dict):
                    continue
                nm = (s.get("name") or s.get("id") or "物种").strip()
                lines.append(f"#### {nm}")
                lines.append("")
                if (s.get("biome_id") or "").strip():
                    bid = (s.get("biome_id") or "").strip()
                    lines.append(f"**生境 id** `{bid}`")
                    lines.append("")
                sk = s.get("notable_skills") or []
                if isinstance(sk, list) and sk:
                    lines.append("**notable_skills**")
                    for x in sk:
                        if str(x).strip():
                            lines.append(f"- {str(x).strip()}")
                    lines.append("")
                if (s.get("encounter_dialogue") or "").strip():
                    lines += ["**遭遇台词 / 旁白**", "", f"> {s['encounter_dialogue'].strip()}", ""]
            lines.append("")

    lines += ["## 境界体系", ""]
    lines += ["### 境界概述", "", w.power_system.summary or "（待补充）", ""]
    if (w.power_system.realm_design_notes or "").strip():
        lines += ["**设计说明**", "", w.power_system.realm_design_notes.strip(), ""]
    lines += ["### 境界技能树", ""]
    if (w.power_system.skill_tree_design_notes or "").strip():
        lines += ["**设计说明**", "", w.power_system.skill_tree_design_notes.strip(), ""]
    else:
        lines += ["*（无单独跨境说明，见各境 skill_tree / subclass_paths）*", ""]
    ps = w.power_system.profession_system
    if (ps.summary or "").strip() or (ps.design_notes or "").strip() or ps.by_tier:
        lines += ["### 境界职业体系", ""]
        if (ps.summary or "").strip():
            lines += [ps.summary.strip(), ""]
        if (ps.design_notes or "").strip():
            lines += ["**设计说明**", "", ps.design_notes.strip(), ""]
        for block in ps.by_tier:
            tname = (block.tier_name or "").strip() or "（未命名境界）"
            if not block.professions:
                continue
            lines += [f"#### {tname}", ""]
            for pr in block.professions:
                fac = f" · 派系专属 `{pr.exclusive_faction_id}`" if pr.exclusive_faction_id else ""
                lines.append(f"- **{pr.name}** (`{pr.id}`){fac}" + (f" — {pr.tagline}" if pr.tagline else ""))
                if pr.flavor:
                    lines.append(f"  - {pr.flavor}")
                if pr.notes:
                    lines.append(f"  - 备注：{pr.notes}")
            lines.append("")
    for t in w.power_system.tiers:
        lines += [f"### {t.name}", "", t.description or "（无描述）", ""]
        if t.skill_tree:
            lines.append("**本境通用技能树**")
            for n in t.skill_tree:
                branch = f" · {n.branch}" if n.branch else ""
                pre = f"（前置：{', '.join(n.prereq_ids)}）" if n.prereq_ids else ""
                lines.append(f"- `{n.id}` **{n.name}**{branch}{pre}")
                if n.summary:
                    lines.append(f"  - {n.summary}")
            lines.append("")
        if t.subclass_paths:
            lines.append("**子类职业**")
            for sp in t.subclass_paths:
                pid = f" · 职业 `{sp.profession_id}`" if sp.profession_id else ""
                lines.append(f"- **{sp.name}** (`{sp.id}`){pid}" + (f" — {sp.tagline}" if sp.tagline else ""))
                if sp.flavor:
                    lines.append(f"  - {sp.flavor}")
                if sp.skill_tree:
                    for n in sp.skill_tree:
                        pre = f" ← {', '.join(n.prereq_ids)}" if n.prereq_ids else ""
                        lines.append(f"  - `{n.id}` {n.name}{pre}")
                lines.append("")
        if t.typical_capabilities:
            lines.append("**典型能力**")
            lines += [f"- {c}" for c in t.typical_capabilities]
            lines.append("")
        if t.limitations:
            lines.append("**限制**")
            lines += [f"- {c}" for c in t.limitations]
            lines.append("")
        if t.examples:
            lines.append("**范例**")
            lines += [f"- {c}" for c in t.examples]
            lines.append("")

    lines += ["## 物品品质体系", "", w.item_quality_system.summary or "（待补充）", ""]
    for g in w.item_quality_system.grades:
        lines += [f"### {g.name}", "", g.rarity_narrative or "", ""]
        if g.typical_effects:
            lines += ["**典型效果**", g.typical_effects, ""]
        if g.binding_rules:
            lines += ["**绑定/规则**", g.binding_rules, ""]
        if g.examples:
            lines.append("**范例**")
            lines += [f"- {c}" for c in g.examples]
            lines.append("")

    lines += ["## 通用人物属性", "", w.attribute_system.summary or "（待补充）", ""]
    if w.attribute_system.design_notes:
        lines += ["### 读法与设计说明", "", w.attribute_system.design_notes, ""]
    if w.attribute_system.stats:
        lines.append("### 维度")
        for s in w.attribute_system.stats:
            ab = f"（{s.abbreviation}）" if s.abbreviation else ""
            lines.append(f"- **{s.name}** `{s.id}`{ab} · 参照刻度 {s.reference_percent}/100")
            if (s.intro or "").strip():
                lines.append(f"  - 简介：{s.intro.strip()}")
            if s.scale:
                lines.append(f"  - 刻度：{s.scale}")
            if s.typical_use:
                lines.append(f"  - 用途：{s.typical_use}")
            if s.description:
                lines.append(f"  - 说明：{s.description}")
        lines.append("")
    if w.attribute_system.tier_average_profiles:
        lines.append("### 各境界平均人物属性（雷达刻度 0–100）")
        for tp in w.attribute_system.tier_average_profiles:
            lines.append(f"- **{tp.tier_name}**")
            if tp.averages:
                for sid, val in tp.averages.items():
                    lines.append(f"  - `{sid}`：{val}")
            lines.append("")

    lines += ["## 派系与关系", "", w.factions.summary or "（待补充）", ""]
    for f in w.factions.entities:
        lines += [f"### {f.name} (`{f.id}`)", "", f"goals: {f.goals}" if f.goals else "", ""]
        if f.territory:
            lines += [f"**地盘**：{f.territory}", ""]
        if f.key_figures:
            lines += ["**关键人物**", ""]
            lines += [f"- {x}" for x in f.key_figures]
            lines.append("")
        if f.relations:
            lines.append("**关系**")
            for r in f.relations:
                lines.append(f"- → `{r.target_id}` **{r.type}**：{r.notes}")
            lines.append("")

    lines += ["## 文化与宗教", "", w.cultures.summary or "（待补充）", ""]
    for c in w.cultures.entities:
        kind_zh = {"culture": "文化", "religion": "宗教", "syncretic": "融合传统"}.get(c.kind, c.kind)
        lines += [f"### {c.name} (`{c.id}`) · {kind_zh}", "", c.summary or "", ""]
        if c.tenets:
            lines += ["**观念 / 教义**", "", c.tenets, ""]
        if c.practices:
            lines += ["**实践 / 仪式**", "", c.practices, ""]
        if c.sacred_sites:
            lines += ["**圣地 / 中心**", ""]
            lines += [f"- {x}" for x in c.sacred_sites]
            lines.append("")
        if c.key_figures:
            lines += ["**关键人物**", ""]
            lines += [f"- {x}" for x in c.key_figures]
            lines.append("")
        if c.relations:
            lines.append("**与其它传统/教团的关系**")
            for r in c.relations:
                lines.append(f"- → `{r.target_id}` **{r.type}**：{r.notes}")
            lines.append("")

    ch = w.characters
    if (ch.summary or "").strip() or (ch.design_notes or "").strip() or ch.entities or ch.relations:
        lines += ["## 人物与卡司", "", (ch.summary or "").strip() or "（待补充）", ""]
        if (ch.design_notes or "").strip():
            lines += ["### 设计说明", "", ch.design_notes.strip(), ""]
        if ch.entities:
            lines += ["### 角色条目", ""]
            for ent in ch.entities:
                if not isinstance(ent, dict):
                    continue
                nm = _norm(ent.get("name")) or _norm(ent.get("id")) or "（未命名）"
                cid = _norm(ent.get("id"))
                cr = _norm(ent.get("cast_role")) or "background"
                lines.append(f"#### {nm}" + (f" (`{cid}`)" if cid else ""))
                lines.append("")
                lines.append(f"- **cast_role**：`{cr}`")
                if ent.get("one_line_hook"):
                    lines += ["", f"**一句钩子**：{ent['one_line_hook']}", ""]
                if ent.get("aliases"):
                    als = ent.get("aliases") or []
                    if isinstance(als, list) and als:
                        lines.append("**别名** " + "、".join(str(x) for x in als if str(x).strip()))
                        lines.append("")
                fids = ent.get("faction_ids") or []
                if isinstance(fids, list) and fids:
                    lines.append("**派系** " + "、".join(f"`{x}`" for x in fids if _norm(x)))
                    lines.append("")
                if _norm(ent.get("home_region_id")):
                    lines += ["**籍贯区域**", "", f"`{ent['home_region_id']}`", ""]
                sk = ent.get("notable_skills") or []
                if isinstance(sk, list) and sk:
                    lines.append("**人物技能 / 特长**")
                    for x in sk:
                        if str(x).strip():
                            lines.append(f"- {str(x).strip()}")
                    lines.append("")
                if _norm(ent.get("notes")):
                    lines += [ent["notes"].strip(), ""]
        if ch.relations:
            lines += ["### 人物关系（结构化）", ""]
            for rel in ch.relations:
                if not isinstance(rel, dict):
                    continue
                s = _norm(rel.get("source_id"))
                t = _norm(rel.get("target_id"))
                rt = _norm(rel.get("relation_type")) or "关联"
                vis = _norm(rel.get("visibility"))
                vis_s = f" · 可见性 `{vis}`" if vis else ""
                nt = _norm(rel.get("notes"))
                lines.append(f"- `{s}` → `{t}` **{rt}**{vis_s}" + (f"：{nt}" if nt else ""))
            lines.append("")

    eco = w.economy
    if (
        (eco.summary or "").strip()
        or (eco.design_notes or "").strip()
        or (eco.labor_notes or "").strip()
        or (eco.taxation_notes or "").strip()
        or (eco.volatility_notes or "").strip()
        or eco.currencies
        or eco.markets
        or eco.trade_routes
        or eco.trade_goods
    ):
        lines += ["## 经济与流通", "", (eco.summary or "").strip() or "（待补充）", ""]
        if (eco.design_notes or "").strip():
            lines += ["### 设计说明", "", eco.design_notes.strip(), ""]
        if eco.currencies:
            lines += ["### 货币与等价物", ""]
            for cur in eco.currencies:
                if not isinstance(cur, dict):
                    continue
                nm = _norm(cur.get("name")) or _norm(cur.get("id")) or "（未命名）"
                cid = _norm(cur.get("id"))
                lines.append(f"- **{nm}**" + (f" (`{cid}`)" if cid else ""))
                if _norm(cur.get("symbol")):
                    lines.append(f"  - 符号：{cur['symbol']}")
                if _norm(cur.get("issuer_faction_id")):
                    lines.append(f"  - 发行派系：`{cur['issuer_faction_id']}`")
                if _norm(cur.get("exchange_notes")):
                    lines.append(f"  - 兑换：{cur['exchange_notes']}")
            lines.append("")
        if eco.markets:
            lines += ["### 市场与层级", ""]
            for m in eco.markets:
                if not isinstance(m, dict):
                    continue
                nm = _norm(m.get("name")) or _norm(m.get("id")) or "市场"
                lines.append(f"#### {nm}")
                lines.append("")
                if _norm(m.get("summary")):
                    lines += [m["summary"].strip(), ""]
                lr = m.get("linked_region_ids") or []
                if isinstance(lr, list) and lr:
                    lines.append("**关联区域** " + "、".join(f"`{x}`" for x in lr if _norm(x)))
                    lines.append("")
                df = m.get("dominant_faction_ids") or []
                if isinstance(df, list) and df:
                    lines.append("**主导派系** " + "、".join(f"`{x}`" for x in df if _norm(x)))
                    lines.append("")
                if _norm(m.get("notes")):
                    lines += [m["notes"].strip(), ""]
            lines.append("")
        if eco.trade_routes:
            lines += ["### 商路与流通", ""]
            for r in eco.trade_routes:
                if not isinstance(r, dict):
                    continue
                nm = _norm(r.get("name")) or _norm(r.get("id")) or "商路"
                fr = _norm(r.get("from_region_id"))
                to = _norm(r.get("to_region_id"))
                lines.append(f"- **{nm}**：`{fr}` → `{to}`" if fr or to else f"- **{nm}**")
                if _norm(r.get("summary")):
                    lines.append(f"  - {r['summary'].strip()}")
                if _norm(r.get("goods_notes")):
                    lines.append(f"  - 货物：{r['goods_notes'].strip()}")
                cf = r.get("controlling_faction_ids") or []
                if isinstance(cf, list) and cf:
                    lines.append("  - 控制派系：" + "、".join(f"`{x}`" for x in cf if _norm(x)))
                lines.append("")
        if eco.trade_goods:
            lines += ["### 关键商品", ""]
            for g in eco.trade_goods:
                if not isinstance(g, dict):
                    continue
                nm = _norm(g.get("name")) or _norm(g.get("id")) or "商品"
                cat = _norm(g.get("category"))
                suf = f" · `{cat}`" if cat else ""
                lines.append(f"- **{nm}**{suf}")
                if _norm(g.get("summary")):
                    lines.append(f"  - {g['summary'].strip()}")
                if _norm(g.get("notes")):
                    lines.append(f"  - 备注：{g['notes'].strip()}")
            lines.append("")
        if (eco.labor_notes or "").strip():
            lines += ["### 劳动力与生产", "", eco.labor_notes.strip(), ""]
        if (eco.taxation_notes or "").strip():
            lines += ["### 税收与再分配", "", eco.taxation_notes.strip(), ""]
        if (eco.volatility_notes or "").strip():
            lines += ["### 危机与波动", "", eco.volatility_notes.strip(), ""]

    lines += ["## 世界历史", "", w.history.summary or "（待补充）", ""]
    for e in w.history.events:
        lines += [f"### {e.when} — {e.title}", "", e.summary or "", ""]
        if e.consequences:
            lines.append("**后果**")
            lines += [f"- {c}" for c in e.consequences]
            lines.append("")

    return "\n".join(lines).strip() + "\n"
