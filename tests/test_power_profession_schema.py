from worldforger.schemas import PowerSystem


def test_power_system_profession_and_subclass_profession_id():
    ps = PowerSystem.model_validate(
        {
            "summary": "灵能阶梯",
            "profession_system": {
                "summary": "宗门职业",
                "by_tier": [
                    {
                        "tier_name": "筑基",
                        "professions": [
                            {
                                "id": "blade_warden",
                                "name": "刃卫",
                                "exclusive_faction_id": "sect_north",
                            }
                        ],
                    }
                ],
            },
            "tiers": [
                {
                    "name": "筑基",
                    "subclass_paths": [
                        {
                            "id": "sp1",
                            "name": "外门刃卫",
                            "profession_id": "blade_warden",
                            "skill_tree": [],
                        }
                    ],
                }
            ],
        }
    )
    assert ps.profession_system.by_tier[0].professions[0].id == "blade_warden"
    assert ps.tiers[0].subclass_paths[0].profession_id == "blade_warden"
