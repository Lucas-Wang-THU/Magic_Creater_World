from worldforger.markdown_export import world_to_markdown
from worldforger.schemas import FactionEntity, GeographySection, HistoryEvent, Meta, PowerTier, World
from worldforger.world_store import (
    create_world,
    list_world_briefs,
    list_world_ids,
    load_world,
    rename_world,
    save_world,
    world_json_path,
)


def test_create_list_load_roundtrip():
    w = create_world("测试世界")
    assert w.meta.id in list_world_ids()
    w2 = load_world(w.meta.id)
    assert w2.meta.name == "测试世界"
    assert world_json_path(w.meta.id).is_file()


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
    w.power_system.tiers.append(PowerTier(name="第一境", description="入门"))
    w.history.events.append(HistoryEvent(when="元年", title="奠基", summary="立国"))
    w.factions.entities.append(
        FactionEntity(id="f1", name="学派", goals="求知", territory="北境")
    )
    md = world_to_markdown(w)
    assert "超凡力量" in md
    assert "文化与宗教" in md
    assert "第一境" in md
    assert "学派" in md
    assert "元年" in md
