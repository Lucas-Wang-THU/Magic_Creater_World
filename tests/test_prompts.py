from worldforger.prompts import ecology_generate_user_payload, system_with_world_json


def test_system_with_world_json_appends_geography_hint():
    s = system_with_world_json('{"meta":{"name":"T"}}')
    assert "```json" in s
    assert "geography.summary" in s
    assert "【地理与 world.json 的 geography 对齐" in s
    assert "relations" in s


def test_system_with_world_json_appends_power_system_hint():
    s = system_with_world_json("{}")
    assert "power_system.summary" in s
    assert "realm_design_notes" in s
    assert "skill_tree_design_notes" in s
    assert "prereq_ids" in s
    assert "profession_system" in s
    assert "【境界体系与 world.json 的 power_system 对齐" in s


def test_system_with_world_json_appends_item_quality_hint():
    s = system_with_world_json("{}")
    assert "item_quality_system" in s
    assert "rarity_narrative" in s
    assert "binding_rules" in s
    assert "item_grades" in s


def test_system_with_world_json_appends_ecology_hint():
    s = system_with_world_json("{}")
    assert "【生态与 world.json 的 ecology 对齐" in s
    assert "notable_skills" in s


def test_system_with_world_json_appends_economy_hint():
    s = system_with_world_json("{}")
    assert "【经济与 world.json 的 economy 对齐" in s
    assert "trade_routes" in s
    assert "issuer_faction_id" in s


def test_system_with_world_json_appends_factions_hint():
    s = system_with_world_json("{}")
    assert "【派系与 world.json 的 factions 对齐" in s
    assert "key_figures" in s
    assert "ally" in s and "enemy" in s


def test_ecology_generate_user_payload_contains_region_ids():
    from worldforger.schemas import GeographySection, Meta, World

    w = World(
        meta=Meta(id="t-abcd1234", name="T"),
        geography=GeographySection(regions=[{"id": "north", "name": "北境"}]),
    )
    p = ecology_generate_user_payload(w, hint="突出苔原")
    assert "north" in p
    assert "突出苔原" in p
