from worldforger.reference_linter import lint_world_references
from worldforger.schemas import (
    CultureEntity,
    CultureRelation,
    FactionEntity,
    FactionRelation,
    GeographySection,
    HistoryEvent,
    HistorySection,
    Meta,
    PowerSystem,
    ProfessionEntry,
    ProfessionSystem,
    SkillNode,
    SubclassPath,
    TierProfessionBlock,
    World,
)


def _meta() -> Meta:
    return Meta(id="w-test", name="Lint")


def test_lint_factions_history_and_profession_faction():
    w = World(
        meta=_meta(),
        factions={
            "summary": "",
            "entities": [
                {"id": "fac_a", "name": "A", "relations": [{"target_id": "zzz", "type": "ally"}]},
                {"id": "fac_b", "name": "B", "relations": []},
            ],
        },
        history=HistorySection(
            events=[
                HistoryEvent(title="E1", linked_faction_ids=["fac_a", "ghost"]),
            ]
        ),
        power_system=PowerSystem(
            profession_system=ProfessionSystem(
                by_tier=[TierProfessionBlock(tier_name="T1", professions=[ProfessionEntry(id="p1", name="P")])]
            ),
            tiers=[
                {
                    "name": "T1",
                    "skill_tree": [],
                    "subclass_paths": [
                        SubclassPath(id="s1", name="S", profession_id="p1", skill_tree=[]),
                    ],
                }
            ],
        ),
    )
    r = lint_world_references(w)
    assert any("zzz" in x for x in r["warnings"])
    assert any("ghost" in x for x in r["warnings"])


def test_lint_geography_region_target():
    w = World(
        meta=_meta(),
        geography=GeographySection(
            regions=[
                {"id": "r1", "name": "北", "relations": [{"target_id": "r2", "type": "邻接"}]},
                {"id": "r2", "name": "南", "relations": []},
            ]
        ),
    )
    assert lint_world_references(w)["ok"] is True

    w2 = World(
        meta=_meta(),
        geography=GeographySection(
            regions=[
                {"id": "r1", "name": "北", "relations": [{"target_id": "rx", "type": "邻接"}]},
                {"id": "r2", "name": "南", "relations": []},
            ]
        ),
    )
    r2 = lint_world_references(w2)
    assert r2["ok"] is False
    assert any("rx" in x for x in r2["warnings"])


def test_lint_skill_prereq_unknown():
    w = World(
        meta=_meta(),
        power_system=PowerSystem(
            tiers=[
                {
                    "name": "一境",
                    "skill_tree": [
                        SkillNode(id="a", name="A", prereq_ids=["missing"]),
                    ],
                    "subclass_paths": [],
                }
            ]
        ),
    )
    r = lint_world_references(w)
    assert any("missing" in x for x in r["warnings"])


def test_lint_culture_relation_unknown_target():
    w = World(
        meta=_meta(),
        cultures={
            "summary": "",
            "entities": [
                CultureEntity(
                    id="c1",
                    name="C1",
                    relations=[CultureRelation(target_id="c2", type="influence")],
                ),
                CultureEntity(id="c2", name="C2", relations=[]),
            ],
        },
    )
    assert lint_world_references(w)["ok"] is True

    w2 = World(
        meta=_meta(),
        cultures={
            "summary": "",
            "entities": [
                CultureEntity(
                    id="c1",
                    name="C1",
                    relations=[CultureRelation(target_id="cx", type="influence")],
                ),
            ],
        },
    )
    assert lint_world_references(w2)["ok"] is False
