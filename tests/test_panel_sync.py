from worldforger.panel_merge import merge_section_conservative
from worldforger.panel_sync import apply_structure_patch, parse_structure_json
from worldforger.world_store import create_world


def test_parse_structure_json_strips_fence():
    raw = '```json\n{"geography": {"summary": "x"}}\n```'
    d = parse_structure_json(raw)
    assert d["geography"]["summary"] == "x"


def test_apply_structure_patch_geography():
    w = create_world("合并测")
    patch = {"geography": {"summary": "高原王国", "climate_notes": "干冷"}}
    merged, keys, _warn, _nn = apply_structure_patch(w, patch)
    assert "geography" in keys
    assert merged.geography.summary == "高原王国"
    assert merged.geography.climate_notes == "干冷"
    assert merged.meta.id == w.meta.id


def test_apply_structure_invalid_section_skipped():
    w = create_world("跳过测")
    patch = {"geography": {"summary": "ok"}, "power_system": "not-a-dict"}
    merged, keys, _w, _nn = apply_structure_patch(w, patch)
    assert "geography" in keys
    assert merged.geography.summary == "ok"
    assert "power_system" not in keys


def test_apply_patch_empty_tiers_does_not_wipe():
    from worldforger.schemas import PowerTier

    w = create_world("等级保留")
    w.power_system.tiers.append(PowerTier(name="第一境", description="入门"))
    patch = {"power_system": {"summary": "新总览", "tiers": []}}
    merged, keys, _w, _nn = apply_structure_patch(w, patch)
    assert "power_system" in keys
    assert merged.power_system.summary == "新总览"
    assert len(merged.power_system.tiers) == 1
    assert merged.power_system.tiers[0].name == "第一境"


def test_apply_patch_cultures_entities():
    w = create_world("文化测")
    patch = {
        "cultures": {
            "summary": "多神并存",
            "entities": [
                {
                    "id": "c_old",
                    "name": "河神会",
                    "kind": "religion",
                    "summary": "水运从业者崇拜",
                    "tenets": "",
                    "practices": "放灯节",
                    "sacred_sites": ["古渡"],
                    "key_figures": [],
                    "relations": [],
                }
            ],
        }
    }
    merged, keys, _w, _nn = apply_structure_patch(w, patch)
    assert "cultures" in keys
    assert merged.cultures.summary == "多神并存"
    assert len(merged.cultures.entities) == 1
    assert merged.cultures.entities[0].name == "河神会"


def test_merge_keeps_nonempty_list_when_patch_empty():
    base = {"summary": "a", "tiers": [{"name": "L1"}]}
    patch = {"summary": "b", "tiers": []}
    out = merge_section_conservative(base, patch)
    assert out["summary"] == "b"
    assert len(out["tiers"]) == 1
    assert out["tiers"][0]["name"] == "L1"


def test_merge_keeps_nonempty_string_when_patch_blank():
    base = {"summary": "原有", "climate_notes": "冷"}
    patch = {"summary": "新", "climate_notes": "  "}
    out = merge_section_conservative(base, patch)
    assert out["summary"] == "新"
    assert out["climate_notes"] == "冷"


def test_apply_structure_patch_attribute_system():
    w = create_world("属性测")
    patch = {
        "attribute_system": {
            "summary": "叙事六维",
            "design_notes": "雷达为参照，非硬数值。",
            "stats": [
                {
                    "id": "phy",
                    "name": "体魄",
                    "abbreviation": "体",
                    "description": "耐力与爆发",
                    "scale": "1-10",
                    "typical_use": "战斗",
                    "reference_percent": 50,
                }
            ],
        }
    }
    merged, keys, _w, _nn = apply_structure_patch(w, patch)
    assert "attribute_system" in keys
    assert merged.attribute_system.summary == "叙事六维"
    assert len(merged.attribute_system.stats) == 1
    assert merged.attribute_system.stats[0].name == "体魄"


def test_merge_replaces_list_when_patch_nonempty():
    base = {"tiers": [{"name": "A"}]}
    patch = {"tiers": [{"name": "A"}, {"name": "B"}]}
    out = merge_section_conservative(base, patch)
    assert len(out["tiers"]) == 2
