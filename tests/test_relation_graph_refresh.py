from worldforger.relation_graph_refresh import (
    apply_culture_relations_patch,
    apply_faction_relations_patch,
)
from worldforger.schemas import CulturesSection, FactionsSection


def test_apply_faction_relations_patch_updates_and_validates():
    sec = FactionsSection(
        entities=[
            {
                "id": "a",
                "name": "A",
                "goals": "",
                "territory": "",
                "key_figures": [],
                "relations": [{"target_id": "b", "type": "enemy", "notes": "old"}],
            },
            {"id": "b", "name": "B", "goals": "", "territory": "", "key_figures": [], "relations": []},
        ]
    )
    patch = {
        "entities": [
            {"id": "a", "relations": [{"target_id": "b", "type": "ally", "notes": "reconciled"}]},
        ]
    }
    out, warnings = apply_faction_relations_patch(sec, patch)
    assert out.entities[0].relations[0].type == "ally"
    assert out.entities[0].relations[0].notes == "reconciled"
    assert not any("非法" in w for w in warnings)


def test_apply_faction_relations_patch_drops_unknown_target():
    sec = FactionsSection(
        entities=[
            {
                "id": "a",
                "name": "A",
                "goals": "",
                "territory": "",
                "key_figures": [],
                "relations": [],
            },
        ]
    )
    patch = {
        "entities": [
            {
                "id": "a",
                "relations": [{"target_id": "ghost", "type": "ally", "notes": ""}],
            },
        ]
    }
    out, warnings = apply_faction_relations_patch(sec, patch)
    assert out.entities[0].relations == []
    assert any("非法" in w for w in warnings)


def test_apply_culture_relations_patch():
    sec = CulturesSection(
        entities=[
            {
                "id": "c1",
                "name": "River cult",
                "kind": "religion",
                "relations": [],
            },
            {
                "id": "c2",
                "name": "City faith",
                "kind": "religion",
                "relations": [],
            },
        ]
    )
    patch = {
        "entities": [
            {"id": "c1", "relations": [{"target_id": "c2", "type": "冲突", "notes": ""}]},
        ]
    }
    out, _ = apply_culture_relations_patch(sec, patch)
    assert len(out.entities[0].relations) == 1
    assert out.entities[0].relations[0].target_id == "c2"
    assert out.entities[0].relations[0].type == "冲突"
