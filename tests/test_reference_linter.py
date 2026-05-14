from worldforger.reference_linter import fix_world_references, lint_world_references
from worldforger.schemas import (
    CultureEntity,
    CultureRelation,
    EconomySection,
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


def test_fix_world_references_removes_dangling_and_clears_fields():
    w = World(
        meta=_meta(),
        geography=GeographySection(
            regions=[
                {"id": "r1", "name": "北", "relations": [{"target_id": "rx", "type": "邻接"}, {"target_id": "", "type": "x"}]},
            ]
        ),
        factions={
            "summary": "",
            "entities": [
                {"id": "fac_a", "name": "A", "relations": [{"target_id": "zzz", "type": "ally"}]},
            ],
        },
        history=HistorySection(
            events=[
                HistoryEvent(title="E1", linked_faction_ids=["fac_a", "ghost"]),
            ]
        ),
        power_system=PowerSystem(
            profession_system=ProfessionSystem(
                by_tier=[TierProfessionBlock(tier_name="T1", professions=[ProfessionEntry(id="p1", name="P", exclusive_faction_id="nope")])]
            ),
            tiers=[
                {
                    "name": "T1",
                    "skill_tree": [
                        SkillNode(id="a", name="A", prereq_ids=["missing"]),
                    ],
                    "subclass_paths": [
                        SubclassPath(id="s1", name="S", profession_id="bad", skill_tree=[]),
                    ],
                }
            ],
        ),
    )
    w2, log = fix_world_references(w)
    assert log
    r = lint_world_references(w2)
    assert r["ok"] is True, r["warnings"]
    assert w2.factions.entities[0].relations == []
    assert w2.history.events[0].linked_faction_ids == ["fac_a"]
    assert w2.power_system.profession_system.by_tier[0].professions[0].exclusive_faction_id == ""
    assert w2.power_system.tiers[0].skill_tree[0].prereq_ids == []
    assert w2.power_system.tiers[0].subclass_paths[0].profession_id == ""
    assert w2.geography.regions[0].get("relations") == []


def test_lint_economy_market_region_and_fix():
    w = World(
        meta=_meta(),
        geography=GeographySection(regions=[{"id": "r1", "name": "北", "relations": []}]),
        factions={"summary": "", "entities": [{"id": "f1", "name": "商会", "relations": []}]},
        economy=EconomySection(
            summary="测",
            currencies=[{"id": "c1", "name": "铜币", "issuer_faction_id": "ghost"}],
            markets=[{"id": "m1", "name": "边市", "linked_region_ids": ["rx"], "dominant_faction_ids": ["f1", "badfac"]}],
            trade_routes=[
                {
                    "id": "t1",
                    "name": "盐路",
                    "from_region_id": "r1",
                    "to_region_id": "missing",
                    "controlling_faction_ids": ["f1", "x"],
                }
            ],
        ),
    )
    r = lint_world_references(w)
    assert r["ok"] is False
    assert r["counts"]["economy"] >= 1
    w2, log = fix_world_references(w)
    assert any("经济" in x for x in log)
    r2 = lint_world_references(w2)
    assert r2["ok"] is True, r2["warnings"]
    assert w2.economy.currencies[0].get("issuer_faction_id") == ""
    assert w2.economy.markets[0].get("linked_region_ids") == []
    assert w2.economy.markets[0].get("dominant_faction_ids") == ["f1"]
    assert w2.economy.trade_routes[0].get("to_region_id") == ""
    assert w2.economy.trade_routes[0].get("controlling_faction_ids") == ["f1"]
