from worldforger.panel_merge import _merge_array_by_name_or_append, merge_section_conservative
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


def test_apply_structure_patch_ecology():
    w = create_world("生态合并")
    w.geography.regions = [{"id": "r1", "name": "一区"}]
    patch = {
        "ecology": {
            "summary": "干草原与盐湖带",
            "design_notes": "体魄高区多大型掠食者",
            "biomes": [
                {
                    "id": "b_salt",
                    "name": "盐湖荒原",
                    "summary": "结晶岸与嗜盐菌毯",
                    "linked_region_ids": ["r1"],
                }
            ],
            "species": [
                {
                    "id": "sp_crab",
                    "name": "盐壳蟹",
                    "biome_id": "b_salt",
                    "traits": ["甲壳", "夜行"],
                    "notable_skills": ["扬沙遮蔽视线"],
                    "encounter_dialogue": "甲壳摩擦如细沙洒落，你闻到苦咸与金属味。",
                }
            ],
        }
    }
    merged, keys, _w, _nn = apply_structure_patch(w, patch)
    assert "ecology" in keys
    assert merged.ecology.summary == "干草原与盐湖带"
    assert len(merged.ecology.biomes) == 1
    assert merged.ecology.biomes[0].get("linked_region_ids") == ["r1"]
    assert len(merged.ecology.species) == 1
    assert merged.ecology.species[0].get("biome_id") == "b_salt"


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


def test_merge_appends_non_id_array_by_name():
    base = {"tiers": [{"name": "A"}]}
    patch = {"tiers": [{"name": "A"}, {"name": "B"}]}
    out = merge_section_conservative(base, patch)
    assert len(out["tiers"]) == 2
    names = [t["name"] for t in out["tiers"]]
    assert names == ["A", "B"]


def test_merge_name_array_dedup_preserves_old():
    """name 去重追加：patch 只含新条目时，旧条目不丢失。"""
    base = {"grades": [{"name": "凡品"}, {"name": "灵品"}]}
    patch = {"grades": [{"name": "仙品"}]}
    out = merge_section_conservative(base, patch)
    names = [g["name"] for g in out["grades"]]
    assert names == ["凡品", "灵品", "仙品"]


def test_merge_name_array_duplicate_deep_merges():
    """同名条目：递归 deep-merge 更新字段，不新增。"""
    base = {"grades": [{"name": "凡品", "rarity_narrative": "随处可见"}]}
    patch = {"grades": [{"name": "凡品", "rarity_narrative": "更新描述", "binding_rules": "不可交易"}]}
    out = merge_section_conservative(base, patch)
    assert len(out["grades"]) == 1
    g = out["grades"][0]
    assert g["rarity_narrative"] == "更新描述"
    assert g["binding_rules"] == "不可交易"


def test_merge_name_array_no_name_falls_back_to_hash_dedup():
    """无 name 的 dict 条目按内容哈希去重追加。"""
    base = [{"stats": ["攻", "防"]}]
    patch = [{"stats": ["攻", "防"]}, {"stats": ["速"]}]
    merged = _merge_array_by_name_or_append(base, patch)
    assert len(merged) == 2
    assert merged[1]["stats"] == ["速"]


def test_merge_name_array_patch_only_new_preserves_base():
    """patch 只含新条目时 base 完整保留 + 新条目追加。"""
    base = [{"name": "炼气"}, {"name": "筑基"}, {"name": "金丹"}]
    patch = [{"name": "元婴"}, {"name": "化神"}]
    merged = _merge_array_by_name_or_append(base, patch)
    names = [m["name"] for m in merged]
    assert names == ["炼气", "筑基", "金丹", "元婴", "化神"]


def test_apply_structure_patch_characters():
    w = create_world("人物测")
    w.geography.regions = [{"id": "r_cap", "name": "王都"}]
    w.factions.entities = [{"id": "f_guard", "name": "禁卫", "goals": "", "territory": "", "key_figures": [], "relations": []}]
    patch = {
        "characters": {
            "summary": "三人小队驱动主线",
            "design_notes": "籍贯与派系 id 对齐",
            "entities": [
                {
                    "id": "ch_hero",
                    "name": "阿绫",
                    "cast_role": "protagonist_core",
                    "faction_ids": ["f_guard"],
                    "home_region_id": "r_cap",
                    "one_line_hook": "被迫拿起旧印",
                    "notable_skills": ["辨印纹真伪"],
                },
                {
                    "id": "ch_rival",
                    "name": "朔夜",
                    "cast_role": "antagonist",
                    "faction_ids": [],
                    "one_line_hook": "觊觎同一印记",
                    "notable_skills": [],
                },
            ],
            "relations": [
                {
                    "source_id": "ch_hero",
                    "target_id": "ch_rival",
                    "relation_type": "rival",
                    "notes": "旧识",
                }
            ],
        }
    }
    merged, keys, _w, _nn = apply_structure_patch(w, patch)
    assert "characters" in keys
    assert merged.characters.summary == "三人小队驱动主线"
    assert len(merged.characters.entities) == 2
    assert merged.characters.entities[0].get("id") == "ch_hero"
    assert len(merged.characters.relations) == 1
    assert merged.characters.relations[0].get("relation_type") == "rival"


def test_apply_structure_patch_economy():
    w = create_world("经济合并")
    patch = {
        "economy": {
            "summary": "盐铁专营",
            "currencies": [{"id": "cur1", "name": "官钞", "exchange_notes": "1:10"}],
            "markets": [{"id": "m1", "name": "城关市", "summary": "课税重"}],
            "trade_routes": [],
            "trade_goods": [{"id": "g1", "name": "粗盐", "category": "strategic"}],
        }
    }
    merged, keys, warns, _nn = apply_structure_patch(w, patch)
    assert not warns
    assert "economy" in keys
    assert merged.economy.summary == "盐铁专营"
    assert len(merged.economy.currencies) == 1
    assert merged.economy.currencies[0]["name"] == "官钞"
    assert len(merged.economy.trade_goods) == 1

