from unittest.mock import AsyncMock, patch

import pytest

from worldforger.sync.panel_merge import _merge_array_by_name_or_append, merge_section_conservative
from worldforger.sync.panel_sync import (
    apply_structure_patch,
    extract_power_system_markdown_supplement,
    parse_structure_json,
    sync_panels_from_dialogue,
)
from worldforger.world_store import create_world


def test_parse_structure_json_strips_fence():
    raw = '```json\n{"geography": {"summary": "x"}}\n```'
    d = parse_structure_json(raw)
    assert d["geography"]["summary"] == "x"


def test_parse_structure_json_recovers_item_quality_when_root_tail_is_broken():
    raw = """
{
  "item_quality_system": {
    "summary": "心器按稳定度分档。",
    "grades": [
      {"name": "遗落品", "rarity_narrative": "常见", "typical_effects": "短效", "binding_rules": "可拾取"},
      {"name": "刻痕品", "rarity_narrative": "较少见", "typical_effects": "单次消耗", "binding_rules": "使用后消散"}
    ]
  },
  "characters": {
"""
    d = parse_structure_json(raw)

    assert d["item_quality_system"]["summary"] == "心器按稳定度分档。"
    assert [g["name"] for g in d["item_quality_system"]["grades"]] == ["遗落品", "刻痕品"]


def test_parse_structure_json_salvages_complete_item_grades_from_truncated_array():
    raw = """
{
  "item_quality_system": {
    "summary": "心器在物理世界中没有固定形态。",
    "grades": [
      {"name": "遗落品", "rarity_narrative": "最常见", "typical_effects": "精神碎片", "binding_rules": "普通人可撞见"},
      {"name": "刻痕品", "rarity_narrative": "单次消耗", "typical_effects": "触发一次刻痕", "binding_rules": "使用后破碎"},
      {"name": "编织品", "rarity_narrative": "可重复使用", "typical_effects": "稳定投影", "binding_rules": "需要心智锚
"""
    d = parse_structure_json(raw)

    iqs = d["item_quality_system"]
    assert iqs["summary"] == "心器在物理世界中没有固定形态。"
    assert [g["name"] for g in iqs["grades"]] == ["遗落品", "刻痕品"]


@pytest.mark.asyncio
@patch("worldforger.sync.panel_sync.chat_completion", new_callable=AsyncMock)
async def test_sync_panels_keeps_patch_when_proofreader_connection_fails(mock_chat):
    APIConnectionError = type("APIConnectionError", (Exception,), {})
    mock_chat.side_effect = [
        '{"geography": {"summary": "Recovered geography"}}',
        APIConnectionError("Connection error."),
    ]
    w = create_world("sync proofreader connection")

    result = await sync_panels_from_dialogue(
        w,
        user_message="update geography",
        assistant_reply="Recovered geography",
        scope="geography",
        proofreader_max_retries=1,
    )

    assert result["ok"] is True
    assert result["world"].geography.summary == "Recovered geography"
    assert result["updated_sections"] == ["geography"]
    assert result["proofreader_final_verdict"] == "skipped_connection_error"
    assert any("APIConnectionError" in w for w in result["merge_warnings"])


@pytest.mark.asyncio
@patch("worldforger.sync.panel_sync.chat_completion", new_callable=AsyncMock)
async def test_sync_panels_persists_item_quality_from_truncated_synchronizer_json(mock_chat):
    mock_chat.return_value = """
{
  "item_quality_system": {
    "summary": "在深潜世界中，超凡物品统称为心器。",
    "grades": [
      {"name": "遗落品", "rarity_narrative": "最常见", "typical_effects": "精神碎片", "binding_rules": "普通人偶尔撞见"},
      {"name": "刻痕品", "rarity_narrative": "单次消耗", "typical_effects": "触发后改变一次深潜状态", "binding_rules": "使用后消散"},
      {"name": "编织品", "rarity_narrative": "可重复使用", "typical_effects": "稳定心智投影", "binding_rules": "需要持有者维持锚点
"""
    w = create_world("sync truncated item quality")

    result = await sync_panels_from_dialogue(
        w,
        user_message="补充物品品质体系",
        assistant_reply="请设计心器六档品质。",
        scope="item_quality_system",
        proofreader_max_retries=0,
    )

    assert result["ok"] is True
    assert result["updated_sections"] == ["item_quality_system"]
    iqs = result["world"].item_quality_system
    assert iqs.summary == "在深潜世界中，超凡物品统称为心器。"
    assert [g.name for g in iqs.grades] == ["遗落品", "刻痕品"]


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


def test_apply_power_system_profession_and_skill_aliases():
    from worldforger.schemas import PowerTier

    w = create_world("power aliases")
    w.power_system.tiers.append(PowerTier(name="Tier One", description="base tier"))
    patch = {
        "power_system": {
            "tiers": [
                {
                    "tier_name": "Tier One",
                    "skills": [
                        {
                            "title": "Mist Step",
                            "desc": "Short movement through fog.",
                            "prerequisites": ["Breath Control"],
                        }
                    ],
                    "subclasses": [
                        {
                            "title": "Blade Warden",
                            "profession": "prof_blade_warden",
                            "skills": [
                                {
                                    "name": "Cut Fog",
                                    "effect": "Open a narrow path in dense mist.",
                                }
                            ],
                        }
                    ],
                }
            ],
            "profession_system": {
                "summary": "Professions by realm.",
                "by_tier": [
                    {
                        "tier": "Tier One",
                        "professions": [
                            {
                                "name": "Blade Warden",
                                "description": "Frontline profession.",
                            }
                        ],
                    }
                ],
            },
        }
    }

    merged, keys, warns, _notes = apply_structure_patch(w, patch)

    assert "power_system" in keys
    assert warns == []
    tier = merged.power_system.tiers[0]
    assert tier.name == "Tier One"
    assert tier.skill_tree[0].name == "Mist Step"
    assert tier.skill_tree[0].id
    assert tier.skill_tree[0].prereq_ids == ["Breath Control"]
    assert tier.subclass_paths[0].name == "Blade Warden"
    assert tier.subclass_paths[0].profession_id == "prof_blade_warden"
    assert tier.subclass_paths[0].skill_tree[0].name == "Cut Fog"
    prof_block = merged.power_system.profession_system.by_tier[0]
    assert prof_block.tier_name == "Tier One"
    assert prof_block.professions[0].id
    assert prof_block.professions[0].name == "Blade Warden"


def test_extract_power_markdown_skill_blocks_by_tier_and_subclass():
    from worldforger.schemas import PowerTier, ProfessionEntry, TierProfessionBlock

    w = create_world("power markdown skill blocks")
    w.power_system.tiers.append(PowerTier(name="碎尘", description="known"))
    w.power_system.tiers.append(PowerTier(name="共鸣", description="known"))
    w.power_system.profession_system.by_tier.append(
        TierProfessionBlock(
            tier_name="共鸣",
            professions=[ProfessionEntry(id="prof_causal_tracker", name="因果追溯者")],
        )
    )
    reply = """
- **节点 id 前缀**：通用树节点以 `causal_` 开头。
- **prereq_ids** 仅能引用同树已有 id。

### 碎尘境（因果）
**通用技能树**
```json
[
  {"id": "causal_sense", "name": "因果感知", "summary": "感知因果", "prereq_ids": []}
]
```

### 共鸣境（因果）
**通用技能树**
```json
[
  {"id": "causal_trace", "name": "因果追溯", "summary": "追溯因果", "prereq_ids": []}
]
```

#### 因果追溯者（`prof_causal_tracker`）
```json
[
  {"id": "ct_deep_trace", "name": "深度追溯", "summary": "深追", "prereq_ids": []}
]
```
"""

    patch = extract_power_system_markdown_supplement(
        w.power_system.model_dump(mode="json"),
        reply,
    )

    tiers = patch["power_system"]["tiers"]
    assert [t["name"] for t in tiers] == ["碎尘", "共鸣"]
    assert tiers[0]["skill_tree"][0]["id"] == "causal_sense"
    assert tiers[1]["skill_tree"][0]["id"] == "causal_trace"
    assert tiers[1]["subclass_paths"][0]["profession_id"] == "prof_causal_tracker"
    assert tiers[1]["subclass_paths"][0]["skill_tree"][0]["id"] == "ct_deep_trace"
    assert "节点 id 前缀" in patch["power_system"]["skill_tree_design_notes"]


def test_extract_power_markdown_subclass_heading_matches_profession_name_without_id():
    from worldforger.schemas import PowerTier, ProfessionEntry, TierProfessionBlock

    w = create_world("power markdown profession name heading")
    w.power_system.tiers.append(PowerTier(name="碎尘", description="known"))
    w.power_system.profession_system.by_tier.append(
        TierProfessionBlock(
            tier_name="碎尘",
            professions=[ProfessionEntry(id="prof_blade_warden", name="刃雾守望者")],
        )
    )
    reply = """
### 碎尘境
#### 刃雾守望者技能树
```json
[
  {"id": "bw_cut_fog", "name": "切雾", "summary": "劈开雾障", "prereq_ids": []}
]
```
"""

    patch = extract_power_system_markdown_supplement(
        w.power_system.model_dump(mode="json"),
        reply,
    )

    subclass = patch["power_system"]["tiers"][0]["subclass_paths"][0]
    assert subclass["id"] == "prof_blade_warden"
    assert subclass["profession_id"] == "prof_blade_warden"
    assert subclass["name"] == "刃雾守望者"
    assert subclass["skill_tree"][0]["id"] == "bw_cut_fog"


@pytest.mark.asyncio
@patch("worldforger.sync.panel_sync.chat_completion", new_callable=AsyncMock)
async def test_sync_panels_uses_local_power_markdown_supplement_when_llm_patch_is_empty(mock_chat):
    from worldforger.schemas import PowerTier

    mock_chat.return_value = "{}"
    w = create_world("sync local power markdown")
    w.power_system.tiers.append(PowerTier(name="碎尘", description="known"))
    reply = """
### 碎尘境（因果）
**通用技能树**
```json
[
  {"id": "causal_sense", "name": "因果感知", "summary": "感知因果", "prereq_ids": []}
]
```
"""

    result = await sync_panels_from_dialogue(
        w,
        user_message="补充技能树",
        assistant_reply=reply,
        scope="power_system",
        proofreader_max_retries=0,
    )

    assert result["ok"] is True
    assert result["updated_sections"] == ["power_system"]
    assert result["world"].power_system.tiers[0].skill_tree[0].id == "causal_sense"
    assert "local power_system markdown supplement applied" in result["merge_warnings"]


def test_power_subclass_patch_reuses_existing_profession_path_by_name():
    from worldforger.schemas import PowerTier, ProfessionEntry, SubclassPath, TierProfessionBlock

    w = create_world("subclass profession alignment")
    w.power_system.tiers.append(
        PowerTier(
            name="碎尘",
            description="known",
            subclass_paths=[SubclassPath(id="path_blade", name="刃雾守望者", profession_id="prof_blade")],
        )
    )
    w.power_system.profession_system.by_tier.append(
        TierProfessionBlock(
            tier_name="碎尘",
            professions=[ProfessionEntry(id="prof_blade", name="刃雾守望者")],
        )
    )
    patch = {
        "power_system": {
            "tiers": [
                {
                    "name": "碎尘",
                    "subclass_paths": [
                        {
                            "name": "刃雾守望者",
                            "skill_tree": [{"id": "bw_cut_fog", "name": "切雾"}],
                        }
                    ],
                }
            ]
        }
    }

    merged, keys, warns, _notes = apply_structure_patch(w, patch)

    assert "power_system" in keys
    assert warns == []
    tier = merged.power_system.tiers[0]
    assert len(tier.subclass_paths) == 1
    assert tier.subclass_paths[0].id == "path_blade"
    assert tier.subclass_paths[0].profession_id == "prof_blade"
    assert tier.subclass_paths[0].skill_tree[0].id == "bw_cut_fog"


def test_power_subclass_patch_aligns_to_profession_created_in_same_patch():
    from worldforger.schemas import PowerTier

    w = create_world("same patch profession subclass alignment")
    w.power_system.tiers.append(PowerTier(name="共鸣", description="known"))
    patch = {
        "power_system": {
            "profession_system": {
                "by_tier": [
                    {
                        "tier_name": "共鸣",
                        "professions": [{"id": "prof_resonator", "name": "回声共鸣者"}],
                    }
                ]
            },
            "tiers": [
                {
                    "name": "共鸣",
                    "subclass_paths": [
                        {
                            "name": "回声共鸣者技能树",
                            "skill_tree": [{"id": "er_echo_step", "name": "回声步"}],
                        }
                    ],
                }
            ],
        }
    }

    merged, keys, warns, _notes = apply_structure_patch(w, patch)

    assert "power_system" in keys
    assert warns == []
    tier = merged.power_system.tiers[0]
    assert tier.subclass_paths[0].id == "prof_resonator"
    assert tier.subclass_paths[0].profession_id == "prof_resonator"
    assert tier.subclass_paths[0].skill_tree[0].id == "er_echo_step"


def test_apply_power_system_root_skill_tree_attaches_to_single_existing_tier():
    from worldforger.schemas import PowerTier

    w = create_world("root skill tree")
    w.power_system.tiers.append(PowerTier(name="Tier One", description="base tier"))
    patch = {
        "power_system": {
            "skill_tree": [
                {
                    "name": "Root Skill",
                    "description": "The model placed this at power_system root.",
                }
            ]
        }
    }

    merged, keys, warns, _notes = apply_structure_patch(w, patch)

    assert "power_system" in keys
    assert warns == []
    assert len(merged.power_system.tiers) == 1
    assert merged.power_system.tiers[0].name == "Tier One"
    assert merged.power_system.tiers[0].skill_tree[0].name == "Root Skill"
    assert merged.power_system.tiers[0].skill_tree[0].id


def test_power_system_supplement_ignores_unknown_tiers():
    from worldforger.schemas import PowerTier

    w = create_world("power known tiers only")
    w.power_system.tiers.append(PowerTier(name="Tier A", description="known"))
    patch = {
        "tiers": [
            {
                "name": "Tier A",
                "skill_tree": [{"id": "sk_a", "name": "Skill A"}],
            },
            {
                "name": "Tier B",
                "skill_tree": [{"id": "sk_b", "name": "Skill B"}],
            },
        ],
        "profession_system": {
            "by_tier": [
                {"tier_name": "Tier A", "professions": [{"id": "prof_a", "name": "Profession A"}]},
                {"tier_name": "Tier B", "professions": [{"id": "prof_b", "name": "Profession B"}]},
            ]
        },
    }

    merged, keys, warns, notes = apply_structure_patch(w, {"power_system": patch})

    assert "power_system" in keys
    assert warns == []
    assert [t.name for t in merged.power_system.tiers] == ["Tier A"]
    assert [n.id for n in merged.power_system.tiers[0].skill_tree] == ["sk_a"]
    block = merged.power_system.profession_system.by_tier[0]
    assert block.tier_name == "Tier A"
    assert [p.id for p in block.professions] == ["prof_a"]
    assert all(t.name != "Tier B" for t in merged.power_system.tiers)
    assert "ignored unknown power_system.tiers" in " ".join(notes.get("power_system", []))
    assert "ignored profession_system.by_tier" in " ".join(notes.get("power_system", []))


def test_power_system_supplement_function_uses_existing_tier_rules():
    from worldforger.schemas import PowerTier
    from worldforger.sync.panel_sync import supplement_power_system_existing_tiers

    w = create_world("power supplement function")
    w.power_system.tiers.append(PowerTier(name="Tier A", description="known"))
    merged, keys, warns, _notes = supplement_power_system_existing_tiers(
        w,
        {
            "target_tier": "Tier A",
            "skill_tree": [{"name": "Root Skill A"}],
            "profession_system": {
                "by_tier": [
                    {"tier_name": "Tier Missing", "professions": [{"id": "bad", "name": "Bad"}]}
                ]
            },
        },
    )

    assert "power_system" in keys
    assert warns == []
    assert [t.name for t in merged.power_system.tiers] == ["Tier A"]
    assert merged.power_system.tiers[0].skill_tree[0].name == "Root Skill A"
    assert merged.power_system.profession_system.by_tier == []


def test_root_skill_tree_targeting_unknown_tier_is_ignored():
    from worldforger.schemas import PowerTier

    w = create_world("root unknown target")
    w.power_system.tiers.append(PowerTier(name="Tier A", description="known"))
    merged, keys, warns, _notes = apply_structure_patch(
        w,
        {
            "power_system": {
                "target_tier": "Tier B",
                "skill_tree": [{"id": "sk_b", "name": "Skill B"}],
            }
        },
    )

    assert "power_system" in keys
    assert warns == []
    assert [t.name for t in merged.power_system.tiers] == ["Tier A"]
    assert merged.power_system.tiers[0].skill_tree == []


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


def test_apply_structure_patch_history_normalizes_string_consequences():
    w = create_world("历史字符串后果")
    patch = {
        "history": {
            "events": [
                {
                    "when": "2062-04-01",
                    "title": "深潜技术的发现",
                    "summary": "首次实现非自主性意识投影。",
                    "consequences": "东亚联合城邦前身机构迅速锁定技术。",
                    "linked_faction_ids": ["f_east_asia_authority"],
                }
            ]
        }
    }

    merged, keys, warns, _nn = apply_structure_patch(w, patch)

    assert "history" in keys
    assert warns == []
    event = merged.history.events[0]
    assert event.title == "深潜技术的发现"
    assert event.consequences == ["东亚联合城邦前身机构迅速锁定技术。"]
    assert event.linked_faction_ids == ["f_east_asia_authority"]


def test_apply_structure_patch_history_updates_existing_event_by_when_and_title():
    from worldforger.schemas import HistoryEvent

    w = create_world("历史修订覆盖")
    w.history.events.append(
        HistoryEvent(
            when="2062-04-01",
            title="深潜技术的发现",
            summary="旧摘要",
            consequences=["旧后果"],
            linked_faction_ids=[],
        )
    )
    patch = {
        "history": {
            "events": [
                {
                    "when": "2062-04-01",
                    "title": "深潜技术的发现",
                    "summary": "新摘要",
                    "consequences": "新后果",
                    "linked_faction_ids": ["f_east_asia_authority"],
                }
            ]
        }
    }

    merged, keys, warns, _nn = apply_structure_patch(w, patch)

    assert "history" in keys
    assert warns == []
    assert len(merged.history.events) == 1
    event = merged.history.events[0]
    assert event.summary == "新摘要"
    assert event.consequences == ["新后果"]
    assert event.linked_faction_ids == ["f_east_asia_authority"]


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


def test_apply_structure_patch_characters_supplements_existing_by_name():
    w = create_world("人物按姓名补充")
    w.characters.entities = [
        {
            "id": "ch_hero",
            "name": "阿绫",
            "cast_role": "protagonist_core",
            "age": 17,
            "gender": "女",
            "notable_skills": ["辨印纹真伪"],
        },
        {
            "id": "ch_rival",
            "name": "朔夜",
            "cast_role": "antagonist",
        },
    ]
    patch = {
        "characters": {
            "entities": [
                {
                    "name": "阿绫",
                    "one_line_hook": "被迫拿起旧印",
                    "notable_skills": ["深潜锚定"],
                }
            ],
            "relations": [
                {
                    "source_id": "阿绫",
                    "target_id": "朔夜",
                    "relation_type": "rival",
                    "notes": "争夺同一枚旧印",
                }
            ],
        }
    }

    merged, keys, warns, _nn = apply_structure_patch(w, patch)

    assert "characters" in keys
    assert warns == []
    assert len(merged.characters.entities) == 2
    hero = next(e for e in merged.characters.entities if e.get("id") == "ch_hero")
    assert hero["cast_role"] == "protagonist_core"
    assert hero["age"] == 17
    assert hero["gender"] == "女"
    assert hero["one_line_hook"] == "被迫拿起旧印"
    assert hero["notable_skills"] == ["辨印纹真伪", "深潜锚定"]
    assert merged.characters.relations[0]["source_id"] == "ch_hero"
    assert merged.characters.relations[0]["target_id"] == "ch_rival"


def test_apply_structure_patch_characters_top_level_list_appends():
    w = create_world("人物数组落盘")
    w.characters.entities = [{"id": "ch_old", "name": "旧人"}]

    merged, keys, warns, _nn = apply_structure_patch(
        w,
        {"characters": [{"name": "新人", "one_line_hook": "新线索"}]},
    )

    assert "characters" in keys
    assert warns == []
    assert [e["name"] for e in merged.characters.entities] == ["旧人", "新人"]


def test_apply_structure_patch_character_relations_resolve_patch_entity_names():
    w = create_world("新增人物关系映射")

    patch = {
        "characters": {
            "entities": [
                {"id": "ch_hero", "name": "阿绫"},
                {"id": "ch_rival", "name": "朔夜"},
            ],
            "relations": [
                {
                    "source_id": "阿绫",
                    "target_id": "朔夜",
                    "relation_type": "rival",
                    "notes": "争夺同一枚旧印",
                }
            ],
        }
    }

    merged, keys, warns, _nn = apply_structure_patch(w, patch)

    assert "characters" in keys
    assert warns == []
    assert merged.characters.relations[0]["source_id"] == "ch_hero"
    assert merged.characters.relations[0]["target_id"] == "ch_rival"


def test_apply_structure_patch_promotes_inline_character_relationships():
    w = create_world("内嵌人物关系落盘")

    patch = {
        "characters": {
            "entities": [
                {
                    "id": "ch_hero",
                    "name": "阿绫",
                    "relationships": [
                        {
                            "target": "朔夜",
                            "relationship": "debt",
                            "detail": "欠下一次救命债",
                        }
                    ],
                },
                {"id": "ch_rival", "name": "朔夜"},
            ]
        }
    }

    merged, keys, warns, _nn = apply_structure_patch(w, patch)

    assert "characters" in keys
    assert warns == []
    assert merged.characters.relations == [
        {
            "source_id": "ch_hero",
            "target_id": "ch_rival",
            "relation_type": "debt",
            "notes": "欠下一次救命债",
        }
    ]


def test_character_relation_merge_appends_new_relation_type_for_same_pair():
    base = {
        "relations": [
            {
                "source_id": "ch_a",
                "target_id": "ch_b",
                "relation_type": "ally",
                "notes": "旧同盟",
            }
        ]
    }
    patch = {
        "relations": [
            {
                "source_id": "ch_a",
                "target_id": "ch_b",
                "relation_type": "secret",
                "notes": "共同隐瞒真相",
            }
        ]
    }

    merged = merge_section_conservative(base, patch)

    assert len(merged["relations"]) == 2
    assert [r["relation_type"] for r in merged["relations"]] == ["ally", "secret"]


def test_character_relation_merge_updates_only_same_relation_type():
    base = {
        "relations": [
            {
                "source_id": "ch_a",
                "target_id": "ch_b",
                "relation_type": "ally",
                "notes": "暂时合作",
            },
            {
                "source_id": "ch_a",
                "target_id": "ch_b",
                "relation_type": "debt",
                "notes": "欠一次人情",
            },
        ]
    }
    patch = {
        "relations": [
            {
                "source_id": "ch_a",
                "target_id": "ch_b",
                "relation_type": "ally",
                "notes": "正式结盟",
            }
        ]
    }

    merged = merge_section_conservative(base, patch)

    assert len(merged["relations"]) == 2
    assert merged["relations"][0]["notes"] == "正式结盟"
    assert merged["relations"][1]["notes"] == "欠一次人情"


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

