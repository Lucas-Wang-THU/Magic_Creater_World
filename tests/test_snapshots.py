from worldforger.snapshot_diff import line_diff_json
from worldforger.world_store import (
    create_world,
    list_snapshots,
    load_world,
    rollback_to_snapshot,
    save_world,
)


def test_save_writes_snapshot_of_previous_version():
    w = create_world("快照")
    assert list_snapshots(w.meta.id) == []
    w2 = load_world(w.meta.id)
    w2.geography.summary = "改一"
    w2.bump_version()
    save_world(w2)
    snaps = list_snapshots(w.meta.id)
    assert {int(s["version"]) for s in snaps} == {1}


def test_rollback_restores_snapshot_and_bumps_version():
    w = create_world("回滚")
    w2 = load_world(w.meta.id)
    w2.geography.summary = "第二"
    w2.bump_version()
    save_world(w2)
    w3 = load_world(w.meta.id)
    assert w3.meta.version == 2
    w3.geography.summary = "第三"
    w3.bump_version()
    save_world(w3)
    assert load_world(w.meta.id).meta.version == 3
    w4 = rollback_to_snapshot(w.meta.id, 1)
    assert w4.meta.version == 4
    assert w4.geography.summary == ""


def test_line_diff_detects_change():
    lines, truncated = line_diff_json({"x": 1}, {"x": 2})
    assert not truncated
    kinds = {ln["kind"] for ln in lines}
    assert "add" in kinds or "rem" in kinds
