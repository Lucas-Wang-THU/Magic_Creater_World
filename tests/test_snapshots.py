from worldforger.snapshot_diff import line_diff_json
from worldforger.world_store import (
    clear_snapshots,
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


def test_clear_snapshots():
    w = create_world("清空快照")
    # 保存 3 次产生 3 个快照
    for i in range(3):
        w2 = load_world(w.meta.id)
        w2.geography.summary = f"第{i+1}版"
        w2.bump_version()
        save_world(w2)
    assert len(list_snapshots(w.meta.id)) == 3
    n = clear_snapshots(w.meta.id)
    assert n == 2  # 保留最新一份
    remaining = list_snapshots(w.meta.id)
    assert len(remaining) == 1
    # 剩下的应是最新版本
    assert remaining[0]["version"] == 3


def test_clear_snapshots_only_one_keeps_it():
    w = create_world("仅一个快照")
    w2 = load_world(w.meta.id)
    w2.geography.summary = "改"
    w2.bump_version()
    save_world(w2)
    assert len(list_snapshots(w.meta.id)) == 1
    n = clear_snapshots(w.meta.id)
    assert n == 0
    assert len(list_snapshots(w.meta.id)) == 1


def test_clear_snapshots_no_dir():
    n = clear_snapshots("nonexistent-world-id")
    assert n == 0


def test_clear_snapshots_api():
    from app.main import app
    from fastapi.testclient import TestClient

    c = TestClient(app)
    w = create_world("API清空快照")
    # 保存 2 次
    for i in range(2):
        w2 = load_world(w.meta.id)
        w2.geography.summary = f"api版{i+1}"
        w2.bump_version()
        save_world(w2)
    assert len(list_snapshots(w.meta.id)) == 2

    r = c.delete(f"/api/worlds/{w.meta.id}/snapshots")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["deleted"] == 1  # 保留最新一份
    remaining = list_snapshots(w.meta.id)
    assert len(remaining) == 1
    assert remaining[0]["version"] == 2
