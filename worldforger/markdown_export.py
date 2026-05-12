from __future__ import annotations

from worldforger.schemas import World


def world_to_markdown(w: World) -> str:
    m = w.meta
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
    if w.geography.landmarks:
        lines += ["### 地标", ""]
        lines += [f"- {x}" for x in w.geography.landmarks]
        lines.append("")
    if w.geography.climate_notes:
        lines += ["### 气候", "", w.geography.climate_notes, ""]
    if w.geography.resources:
        lines += ["### 资源", ""]
        lines += [f"- {x}" for x in w.geography.resources]
        lines.append("")

    lines += ["## 超凡力量体系", "", w.power_system.summary or "（待补充）", ""]
    for t in w.power_system.tiers:
        lines += [f"### {t.name}", "", t.description or "（无描述）", ""]
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

    lines += ["## 世界历史", "", w.history.summary or "（待补充）", ""]
    for e in w.history.events:
        lines += [f"### {e.when} — {e.title}", "", e.summary or "", ""]
        if e.consequences:
            lines.append("**后果**")
            lines += [f"- {c}" for c in e.consequences]
            lines.append("")

    return "\n".join(lines).strip() + "\n"
