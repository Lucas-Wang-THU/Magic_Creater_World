from worldforger.structure_normalize import (
    normalize_structure_patch,
    normalize_structure_patch_detailed,
)
from worldforger.panel_sync import apply_structure_patch
from worldforger.world_store import create_world


def test_normalize_items_alias_to_item_quality_system():
    patch = {
        "items": {
            "summary": "品质总览",
            "grades": [
                {"grade": "凡品", "rarity": "常见", "effects": "无魔"},
                {"name": "灵器", "typical_effects": ["发光", "共鸣"]},
            ],
        }
    }
    out = normalize_structure_patch(patch)
    assert "items" not in out
    assert out["item_quality_system"]["summary"] == "品质总览"
    g = out["item_quality_system"]["grades"]
    assert g[0]["name"] == "凡品"
    assert g[0]["rarity_narrative"] == "常见"
    assert g[0]["typical_effects"] == "无魔"
    assert g[1]["name"] == "灵器"
    assert "发光" in g[1]["typical_effects"]


def test_normalize_item_grades_top_level_list():
    patch = {"item_grades": [{"title": "铜", "rules": ["不可交易"]}]}
    out = normalize_structure_patch(patch)
    g = out["item_quality_system"]["grades"]
    assert g[0]["name"] == "铜"
    assert "不可交易" in g[0]["binding_rules"]


def test_apply_patch_accepts_normalized_items_alias():
    w = create_world("物品归一")
    patch = {
        "items": {
            "summary": "测试",
            "grades": [{"name": "白", "rarity_narrative": "普通"}],
        }
    }
    merged, keys, warns, _nn = apply_structure_patch(w, patch)
    assert not warns
    assert "item_quality_system" in keys
    assert merged.item_quality_system.summary == "测试"
    assert len(merged.item_quality_system.grades) == 1
    assert merged.item_quality_system.grades[0].name == "白"


def test_normalize_geography_landmarks_object_array():
    patch = {
        "geography": {
            "summary": "群岛",
            "landmarks": [{"name": "灯塔"}, {"label": "古港"}],
            "resources": "鱼盐\n木材",
        }
    }
    out = normalize_structure_patch(patch)
    assert out["geography"]["landmarks"] == ["灯塔", "古港"]
    assert out["geography"]["resources"] == ["鱼盐", "木材"]


def test_normalize_geography_regions_single_object_and_relations():
    patch = {
        "geography": {
            "regions": {
                "name": "北境",
                "summary": "苦寒",
                "relations": {"target_id": "r-south", "type": "邻接", "notes": "关隘"},
            }
        }
    }
    out = normalize_structure_patch(patch)
    regs = out["geography"]["regions"]
    assert len(regs) == 1
    assert regs[0]["name"] == "北境"
    assert len(regs[0]["relations"]) == 1
    assert regs[0]["relations"][0]["target_id"] == "r-south"


def test_normalize_top_level_culture_alias_to_cultures():
    patch = {
        "culture": {
            "summary": "别名测",
            "entities": [{"id": "x1", "name": "传统甲", "kind": "culture"}],
        }
    }
    out, notes = normalize_structure_patch_detailed(patch)
    assert "culture" not in out
    assert out["cultures"]["summary"] == "别名测"
    assert len(out["cultures"]["entities"]) == 1
    assert "cultures" in notes


def test_normalize_geography_json_string_section():
    patch = {"geography": '{"summary": "从字符串解析", "landmarks": ["塔"]}'}
    out = normalize_structure_patch(patch)
    assert out["geography"]["summary"] == "从字符串解析"
    assert out["geography"]["landmarks"] == ["塔"]


def test_apply_geography_patch_after_normalize_no_warnings():
    w = create_world("地理归一")
    patch = {
        "geography": {
            "summary": "两陆",
            "landmarks": [{"name": "界碑"}],
            "regions": [{"title": "东陆", "desc": "平原多"}],
        }
    }
    merged, keys, warns, nn = apply_structure_patch(w, patch)
    assert not warns
    assert "geography" in keys
    assert merged.geography.landmarks == ["界碑"]
    assert len(merged.geography.regions) == 1
    assert merged.geography.regions[0]["name"] == "东陆"
    rid = merged.geography.regions[0].get("id") or ""
    assert rid.startswith("rg_")
    assert "geography" in nn
    assert any("landmarks" in s for s in nn["geography"])
    assert any("占位" in s or "稳定" in s for s in nn["geography"])


def test_normalize_structure_patch_detailed_notes_geography_json_string():
    patch = {"geography": '{"summary": "S", "regions": []}'}
    out, notes = normalize_structure_patch_detailed(patch)
    assert out["geography"]["summary"] == "S"
    assert "geography" in notes
    assert any("JSON" in s or "解析" in s for s in notes["geography"])
