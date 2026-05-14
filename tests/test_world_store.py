from worldforger.markdown_export import world_to_markdown
from worldforger.schemas import (
    EconomySection,
    FactionEntity,
    GeographySection,
    HistoryEvent,
    Meta,
    PowerTier,
    ProfessionEntry,
    TierProfessionBlock,
    World,
)
from worldforger.world_store import (
    create_world,
    list_world_briefs,
    list_world_ids,
    load_world,
    rename_world,
    save_world,
    world_context_for_prompt,
    world_json_path,
)


def test_create_list_load_roundtrip():
    w = create_world("测试世界")
    assert w.meta.id in list_world_ids()
    w2 = load_world(w.meta.id)
    assert w2.meta.name == "测试世界"
    assert world_json_path(w.meta.id).is_file()


def test_world_context_includes_studio_files_and_fulltext_search():
    w = create_world("StudioCtx")
    ctx = world_context_for_prompt(w, include_markdown=False)
    assert '"id": "files"' in ctx or '"id":"files"' in ctx.replace(" ", "")
    assert '"id": "search"' in ctx or '"id":"search"' in ctx.replace(" ", "")
    assert "full_text_search" in ctx
    assert "全文搜索" in ctx
    assert "导出与快照" in ctx


def test_list_world_briefs_reflects_rename():
    w = create_world("BriefA")
    wid = w.meta.id
    rows = list_world_briefs()
    assert any(r["id"] == wid and r["name"] == "BriefA" for r in rows)
    rename_world(wid, "BriefB")
    rows2 = list_world_briefs()
    assert any(r["id"] == wid and r["name"] == "BriefB" for r in rows2)


def test_save_bump_and_geography():
    w = create_world("A")
    w.geography = GeographySection(summary="多岛链", climate_notes="多雨")
    w.bump_version()
    save_world(w)
    w3 = load_world(w.meta.id)
    assert w3.geography.summary == "多岛链"
    assert w3.meta.version >= 2


def test_put_meta_id_mismatch_guard():
    w = create_world("B")
    bad = World(meta=Meta(id="other", name="X"))
    assert bad.meta.id == "other"


def test_export_contains_headings():
    w = create_world("导出测")
    w.power_system.profession_system.summary = "各境职业与流派"
    w.power_system.profession_system.by_tier.append(
        TierProfessionBlock(
            tier_name="第一境",
            professions=[ProfessionEntry(id="p1", name="巡卫")],
        )
    )
    w.power_system.tiers.append(PowerTier(name="第一境", description="入门"))
    w.history.events.append(HistoryEvent(when="元年", title="奠基", summary="立国"))
    w.factions.entities.append(
        FactionEntity(id="f1", name="学派", goals="求知", territory="北境")
    )
    w.attribute_system.summary = "六维叙事板"
    w.economy = EconomySection(summary="盐铁与关榷", currencies=[{"id": "c1", "name": "官钞"}])
    md = world_to_markdown(w)
    assert "境界体系" in md
    assert "### 境界概述" in md
    assert "### 境界技能树" in md
    assert "### 境界职业体系" in md
    assert "通用人物属性" in md
    assert "文化与宗教" in md
    assert "第一境" in md
    assert "学派" in md
    assert "元年" in md
    assert "## 经济与流通" in md
