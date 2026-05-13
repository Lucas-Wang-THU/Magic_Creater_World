from worldforger.structure_normalize import normalize_structure_patch_detailed


def test_hoist_root_profession_system_into_power_system():
    patch = {"profession_system": {"summary": "S", "by_tier": [{"tier_name": "T1", "professions": [{"id": "a", "name": "A"}]}]}}
    out, notes = normalize_structure_patch_detailed(patch)
    assert "power_system" in out
    ps = out["power_system"]["profession_system"]
    assert ps["summary"] == "S"
    assert any("顶层 profession_system" in m for m in notes.get("power_system", []))


def test_profession_by_tier_object_to_array_and_align():
    patch = {
        "power_system": {
            "tiers": [{"name": "境乙"}, {"name": "境甲"}],
            "profession_system": {
                "by_tier": {
                    "境甲": [{"id": "x", "name": "游侠"}],
                    "境乙": [{"id": "y", "name": "民兵"}],
                }
            },
        }
    }
    out, _ = normalize_structure_patch_detailed(patch)
    bt = out["power_system"]["profession_system"]["by_tier"]
    assert [b["tier_name"] for b in bt] == ["境乙", "境甲"]
    assert bt[0]["professions"][0]["id"] == "y"
    assert bt[1]["professions"][0]["id"] == "x"


def test_flat_profession_list_goes_to_first_tier():
    patch = {
        "power_system": {
            "tiers": [{"name": "唯一境"}],
            "profession_system": {"by_tier": [{"id": "p1", "name": "铁匠"}, {"id": "p2", "name": "学者"}]},
        }
    }
    out, _ = normalize_structure_patch_detailed(patch)
    bt = out["power_system"]["profession_system"]["by_tier"]
    assert len(bt) == 1
    assert len(bt[0]["professions"]) == 2
