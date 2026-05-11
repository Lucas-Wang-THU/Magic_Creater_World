from worldforger.structure_normalize import normalize_structure_patch
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
    merged, keys, warns = apply_structure_patch(w, patch)
    assert not warns
    assert "item_quality_system" in keys
    assert merged.item_quality_system.summary == "测试"
    assert len(merged.item_quality_system.grades) == 1
    assert merged.item_quality_system.grades[0].name == "白"
