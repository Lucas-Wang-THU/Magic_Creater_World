from worldforger.sync.structure_normalize import (
    normalize_structure_patch,
    normalize_structure_patch_detailed,
)
from worldforger.sync.panel_sync import apply_structure_patch
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


def test_normalize_geography_dalu_merged_into_regions():
    patch = {
        "geography": {
            "summary": "双陆",
            "regions": [{"name": "西陆", "summary": "沙漠"}],
            "大陆": [{"name": "东陆", "summary": "平原"}],
        }
    }
    out = normalize_structure_patch(patch)
    regs = out["geography"]["regions"]
    assert len(regs) == 2
    assert regs[0]["name"] == "西陆"
    assert regs[1]["name"] == "东陆"


def test_normalize_geography_top_level_climate_string_to_climate_notes():
    patch = {"geography": {"climate": "多雨", "summary": "群岛"}}
    out = normalize_structure_patch(patch)
    assert out["geography"]["climate_notes"] == "多雨"
    assert out["geography"]["summary"] == "群岛"


def test_normalize_geography_zh_geo_key():
    patch = {"地理": {"summary": "从中文键", "regions": [{"name": "甲", "summary": "x"}]}}
    out, notes = normalize_structure_patch_detailed(patch)
    assert "地理" not in out
    assert out["geography"]["summary"] == "从中文键"
    assert len(out["geography"]["regions"]) == 1
    assert "geography" in notes


def test_normalize_region_local_climate_separate_from_terrain():
    patch = {
        "geography": {
            "regions": [
                {
                    "name": "北境",
                    "summary": "河谷",
                    "terrain": "丘陵",
                    "climate": "冬雨型",
                }
            ]
        }
    }
    out = normalize_structure_patch(patch)
    r0 = out["geography"]["regions"][0]
    assert r0["terrain"] == "丘陵"
    assert r0["climate"] == "冬雨型"


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


def test_normalize_attributes_top_level_alias_dict():
    patch = {
        "attributes": {
            "overview": "叙事板",
            "dimensions": [
                {"title": "体魄", "percent": 70},
                {"name": "神识", "id": "mind", "reference_percent": 40},
            ],
        }
    }
    out, notes = normalize_structure_patch_detailed(patch)
    assert "attributes" not in out
    assert out["attribute_system"]["summary"] == "叙事板"
    assert len(out["attribute_system"]["stats"]) == 2
    assert out["attribute_system"]["stats"][0]["name"] == "体魄"
    assert out["attribute_system"]["stats"][0]["reference_percent"] == 70
    assert out["attribute_system"]["stats"][1]["id"] == "mind"
    assert "attribute_system" in notes


def test_normalize_attributes_top_level_list():
    patch = {"attributes": [{"name": "幸运", "reference_percent": 30}]}
    out = normalize_structure_patch(patch)
    assert len(out["attribute_system"]["stats"]) == 1
    assert out["attribute_system"]["stats"][0]["name"] == "幸运"


def test_apply_patch_accepts_attributes_alias():
    w = create_world("属性别名")
    patch = {
        "attributes": {
            "summary": "检定向",
            "stats": [{"dimension": "理智", "scale": "0-99", "雷达": 50}],
        }
    }
    merged, keys, warns, _nn = apply_structure_patch(w, patch)
    assert not warns
    assert "attribute_system" in keys
    assert merged.attribute_system.summary == "检定向"
    assert merged.attribute_system.stats[0].name == "理智"
    assert merged.attribute_system.stats[0].reference_percent == 50


def test_normalize_attribute_system_tier_profiles_and_stat_intro():
    patch = {
        "attribute_system": {
            "stats": [
                {"id": "phy", "name": "体魄", "intro": "肉身与耐力", "reference_percent": 55},
                {"id": "soul", "name": "神魂", "intro": "感知与意志", "reference_percent": 40},
            ],
            "tier_average_profiles": [
                {"tier_name": "炼气", "averages": {"phy": 25, "soul": 20}},
                {"tier_name": "筑基", "averages": {"phy": 55, "soul": 45}},
            ],
        }
    }
    out, _ = normalize_structure_patch_detailed(patch)
    att = out["attribute_system"]
    assert att["stats"][0]["intro"] == "肉身与耐力"
    assert len(att["tier_average_profiles"]) == 2
    assert att["tier_average_profiles"][1]["tier_name"] == "筑基"
    assert att["tier_average_profiles"][1]["averages"]["phy"] == 55


def test_normalize_zh_economy_top_level_key():
    out, notes = normalize_structure_patch_detailed({"经济": {"summary": "盐与贝壳", "currencies": [{"name": "盐券"}]}})
    assert "经济" not in out
    assert out["economy"]["summary"] == "盐与贝壳"
    assert out["economy"]["currencies"][0]["id"].startswith("cur_")
    assert "economy" in notes


def test_normalize_economy_trade_routes_alias():
    out, _ = normalize_structure_patch_detailed(
        {"economy": {"trade_routes": [{"name": "北路", "from": "a", "to": "b"}]}}
    )
    r = out["economy"]["trade_routes"][0]
    assert r["from_region_id"] == "a"
    assert r["to_region_id"] == "b"


def test_normalize_factions_entities_object_map_and_key_figure_objects():
    patch = {
        "factions": {
            "summary": "两强",
            "entities": {
                "fa": {
                    "id": "fa",
                    "name": "甲派",
                    "goals": "扩张",
                    "relations": [{"target_id": "fb", "type": "rival"}],
                },
                "fb": {
                    "id": "fb",
                    "name": "乙派",
                    "key_figures": [{"name": "李四", "role": "长老", "hook": "暗中通敌"}],
                },
            },
        }
    }
    out, notes = normalize_structure_patch_detailed(patch)
    ents = {e["id"]: e for e in out["factions"]["entities"]}
    assert len(ents) == 2
    assert ents["fa"]["relations"][0]["type"] == "enemy"
    assert "李四" in ents["fb"]["key_figures"][0]
    assert "factions" in notes


def test_normalize_zh_faction_top_level_key():
    out, _ = normalize_structure_patch_detailed(
        {"派系": {"entities": [{"name": "行会", "goals": "抽成"}]}}
    )
    e0 = out["factions"]["entities"][0]
    assert e0["id"].startswith("f_")
    assert e0["name"] == "行会"
    assert e0["goals"] == "抽成"


def test_apply_patch_accepts_normalized_factions_key_figures():
    w = create_world("派系归一")
    patch = {
        "factions": {
            "entities": {
                "fx": {
                    "id": "fx",
                    "name": "秘社",
                    "key_figures": [{"name": "王五", "role": "主持"}],
                }
            }
        }
    }
    merged, keys, warns, _nn = apply_structure_patch(w, patch)
    assert not warns
    assert "factions" in keys
    assert merged.factions.entities[0].key_figures[0].startswith("王五")
