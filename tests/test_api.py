from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from worldforger.creative_modes import (
    chat_mode_system,
    normalize_creative_mode,
    outline_mode_addon,
    structure_sync_addon,
)

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_config_has_api_key_bool_no_500():
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["has_api_key"], bool)
    assert "default_model" in body


def test_api_not_shadowed_by_static():
    """根路径不再挂整目录 StaticFiles，/api 须始终可达。"""
    assert client.get("/api/health").status_code == 200
    r = client.get("/static/styles.css")
    assert r.status_code == 200
    r2 = client.get("/")
    assert r2.status_code == 200
    assert "text/html" in (r2.headers.get("content-type") or "")
    assert b"Magic Creater World" in r2.content


def test_world_crud_and_export():
    r = client.post("/api/worlds", json={"name": "CRUD 世界"})
    assert r.status_code == 200
    wid = r.json()["world"]["meta"]["id"]
    r2 = client.get(f"/api/worlds/{wid}")
    assert r2.status_code == 200
    data = r2.json()
    assert "world" in data and "has_nonempty_world_md" in data
    assert data["has_nonempty_world_md"] is True
    body = data["world"]
    body["geography"]["summary"] = "高山与深谷"
    r3 = client.put(f"/api/worlds/{wid}", json=body)
    assert r3.status_code == 200
    assert r3.json()["geography"]["summary"] == "高山与深谷"
    r4 = client.post(f"/api/worlds/{wid}/export-md")
    assert r4.status_code == 200


def test_put_wrong_id_rejected():
    w = client.post("/api/worlds", json={"name": "Z"}).json()["world"]
    wid = w["meta"]["id"]
    w["meta"]["id"] = "wrong"
    r = client.put(f"/api/worlds/{wid}", json=w)
    assert r.status_code == 400


def test_patch_rename_and_delete_world():
    r = client.post("/api/worlds", json={"name": "原名"})
    assert r.status_code == 200
    wid = r.json()["world"]["meta"]["id"]
    r2 = client.patch(f"/api/worlds/{wid}", json={"name": "  新显示名  "})
    assert r2.status_code == 200
    body = r2.json()
    assert body["meta"]["name"] == "新显示名"
    assert body["meta"]["id"] == wid
    r3 = client.delete(f"/api/worlds/{wid}")
    assert r3.status_code == 200
    assert r3.json().get("ok") is True
    assert client.get(f"/api/worlds/{wid}").status_code == 404


def test_delete_world_missing_404():
    assert client.delete("/api/worlds/nonexistent-world-00000000").status_code == 404


def test_search_world_endpoint_hits_json_and_md():
    wid = client.post("/api/worlds", json={"name": "全文搜测"}).json()["world"]["meta"]["id"]
    w = client.get(f"/api/worlds/{wid}").json()["world"]
    token = "TokSearchUniqueXy9"
    w["geography"]["summary"] = f"含标记 {token}"
    assert client.put(f"/api/worlds/{wid}", json=w).status_code == 200
    assert client.post(f"/api/worlds/{wid}/export-md").status_code == 200
    rs = client.get(f"/api/worlds/{wid}/search", params={"q": token})
    assert rs.status_code == 200
    data = rs.json()
    assert data["query"] == token
    assert data["total_json"] >= 1
    assert any(token in (h.get("snippet") or "") for h in data["json_hits"])
    assert data["total_md"] >= 1


def test_search_world_missing_q_422():
    wid = client.post("/api/worlds", json={"name": "搜空q"}).json()["world"]["meta"]["id"]
    assert client.get(f"/api/worlds/{wid}/search").status_code == 422


def test_search_world_blank_q_400():
    wid = client.post("/api/worlds", json={"name": "搜空白"}).json()["world"]["meta"]["id"]
    assert client.get(f"/api/worlds/{wid}/search", params={"q": "   "}).status_code == 400


def test_search_world_not_found_404():
    assert (
        client.get("/api/worlds/nonexistent-world-00000000/search", params={"q": "a"}).status_code == 404
    )


def test_lint_references_endpoint():
    wid = client.post("/api/worlds", json={"name": "Lint 接口"}).json()["world"]["meta"]["id"]
    r = client.get(f"/api/worlds/{wid}/lint-references")
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data and "warnings" in data
    assert isinstance(data["warnings"], list)
    assert "counts" in data


def test_lint_references_404():
    assert client.get("/api/worlds/nonexistent-world-00000000/lint-references").status_code == 404


def test_list_worlds_returns_id_and_display_name():
    wid = client.post("/api/worlds", json={"name": "列表原名"}).json()["world"]["meta"]["id"]
    r = client.get("/api/worlds")
    assert r.status_code == 200
    rows = r.json()["worlds"]
    row = next((x for x in rows if x.get("id") == wid), None)
    assert row is not None
    assert row["name"] == "列表原名"
    assert client.patch(f"/api/worlds/{wid}", json={"name": "列表新名"}).status_code == 200
    r2 = client.get("/api/worlds")
    row2 = next((x for x in r2.json()["worlds"] if x.get("id") == wid), None)
    assert row2["name"] == "列表新名"


@patch("app.main.chat_completion", new_callable=AsyncMock, return_value="大纲正文")
def test_outline_saves_file(mock_chat):
    wid = client.post("/api/worlds", json={"name": "大纲测"}).json()["world"]["meta"]["id"]
    r = client.post(
        f"/api/worlds/{wid}/outline",
        json={"kind": "characters", "prompt": "写三位主角"},
    )
    assert r.status_code == 200
    assert "saved" in r.json()
    from pathlib import Path

    from worldforger.config import get_settings

    p = Path(get_settings().worlds_dir) / wid / "outlines" / "characters.md"
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "based_on_world_id" in text
    assert "大纲正文" in text
    mock_chat.assert_awaited()


def test_snapshots_list_diff_rollback_via_api():
    wid = client.post("/api/worlds", json={"name": "快照API"}).json()["world"]["meta"]["id"]
    assert client.get(f"/api/worlds/{wid}/snapshots").json()["snapshots"] == []
    w = client.get(f"/api/worlds/{wid}").json()["world"]
    w["geography"]["summary"] = "第一稿"
    assert client.put(f"/api/worlds/{wid}", json=w).status_code == 200
    rs = client.get(f"/api/worlds/{wid}/snapshots")
    assert rs.status_code == 200
    assert 1 in {s["version"] for s in rs.json()["snapshots"]}
    diff = client.get(f"/api/worlds/{wid}/snapshots/diff", params={"left": "1", "right": "current"})
    assert diff.status_code == 200
    body = diff.json()
    assert "lines" in body
    assert any("第一稿" in (ln.get("text") or "") for ln in body["lines"])
    rb = client.post(f"/api/worlds/{wid}/snapshots/rollback", json={"snapshot_version": 1})
    assert rb.status_code == 200
    assert rb.json()["world"]["meta"]["version"] == 3
    assert rb.json()["world"]["geography"]["summary"] == ""


def test_snapshots_diff_requires_left_right():
    wid = client.post("/api/worlds", json={"name": "diff缺参"}).json()["world"]["meta"]["id"]
    assert client.get(f"/api/worlds/{wid}/snapshots/diff").status_code == 400


def test_chat_503_without_key():
    from worldforger.config import get_settings

    get_settings.cache_clear()
    import os

    old = os.environ.pop("PARATERA_API_KEY", None)
    old2 = os.environ.pop("OPENAI_API_KEY", None)
    get_settings.cache_clear()
    try:
        wid = client.post("/api/worlds", json={"name": "K"}).json()["world"]["meta"]["id"]
        r = client.post(
            f"/api/worlds/{wid}/chat",
            json={"messages": [{"role": "user", "content": "hello"}]},
        )
        assert r.status_code == 503
    finally:
        if old is not None:
            os.environ["PARATERA_API_KEY"] = old
        if old2 is not None:
            os.environ["OPENAI_API_KEY"] = old2
        get_settings.cache_clear()


@patch("app.main.sync_panels_from_dialogue", new_callable=AsyncMock)
def test_sync_panels_endpoint(mock_sync):
    from worldforger.world_store import load_world

    wid = client.post("/api/worlds", json={"name": "同步测"}).json()["world"]["meta"]["id"]
    w = load_world(wid)
    w2 = w.model_copy(deep=True)
    w2.geography.summary = "从对话合并"
    mock_sync.return_value = {
        "world": w2,
        "updated_sections": ["geography"],
        "applied_patch": {"geography": {"summary": "从对话合并"}},
        "structure_output_keys": ["geography"],
        "scope_applied": "geography",
        "merge_warnings": [],
        "normalize_notes": {},
    }

    r = client.post(
        f"/api/worlds/{wid}/sync-panels-from-chat",
        json={
            "user_message": "补充地理",
            "assistant_reply": "这里是高原…",
            "persist": False,
            "scope": "geography",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["world"]["geography"]["summary"] == "从对话合并"
    assert "geography" in body["updated_sections"]
    assert body.get("normalize_notes") == {}
    mock_sync.assert_awaited()
    _args, kwargs = mock_sync.call_args
    assert kwargs.get("scope") == "geography"


def test_normalize_creative_mode():
    assert normalize_creative_mode(None) is None
    assert normalize_creative_mode("") is None
    assert normalize_creative_mode("  NOVEL ") == "novel"
    assert normalize_creative_mode("CoC") == "coc"
    assert normalize_creative_mode("xyz") is None


def test_chat_mode_system_only_known():
    assert chat_mode_system("novel") and "小说" in chat_mode_system("novel")
    assert chat_mode_system("bad") is None


def test_structure_sync_addon_nonempty_for_modes():
    for m in ("novel", "game", "coc", "dnd"):
        assert "载体" in structure_sync_addon(m)


def test_outline_mode_addon():
    assert outline_mode_addon("novel").strip()
    assert outline_mode_addon("dnd").strip()
    assert outline_mode_addon(None) == ""


def test_refresh_faction_relations_empty_entities_no_llm():
    wid = client.post("/api/worlds", json={"name": "派系关系空"}).json()["world"]["meta"]["id"]
    r = client.post(f"/api/worlds/{wid}/refresh/faction-relations", json={"persist": True})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["persisted"] is False
    assert any("无派系实体" in (w or "") for w in (body.get("warnings") or []))


@patch("worldforger.relation_graph_refresh.chat_completion", new_callable=AsyncMock)
def test_refresh_faction_relations_merge_and_persist(mock_llm):
    mock_llm.return_value = (
        "```json\n"
        '{"entities": [{"id": "f1", "relations": [{"target_id": "f2", "type": "ally", "notes": ""}]}]}'
        "\n```"
    )
    wid = client.post("/api/worlds", json={"name": "派系关系测"}).json()["world"]["meta"]["id"]
    w = client.get(f"/api/worlds/{wid}").json()["world"]
    w["factions"]["entities"] = [
        {
            "id": "f1",
            "name": "北",
            "goals": "",
            "territory": "",
            "key_figures": [],
            "relations": [],
        },
        {
            "id": "f2",
            "name": "南",
            "goals": "",
            "territory": "",
            "key_figures": [],
            "relations": [],
        },
    ]
    assert client.put(f"/api/worlds/{wid}", json=w).status_code == 200
    v0 = client.get(f"/api/worlds/{wid}").json()["world"]["meta"]["version"]

    r = client.post(f"/api/worlds/{wid}/refresh/faction-relations", json={"persist": True})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["persisted"] is True
    rels = body["world"]["factions"]["entities"][0]["relations"]
    assert rels[0]["target_id"] == "f2"
    assert rels[0]["type"] == "ally"
    mock_llm.assert_awaited()

    w_disk = client.get(f"/api/worlds/{wid}").json()["world"]
    assert w_disk["meta"]["version"] > v0
    assert w_disk["factions"]["entities"][0]["relations"][0]["type"] == "ally"


@patch("worldforger.relation_graph_refresh.chat_completion", new_callable=AsyncMock)
def test_refresh_culture_relations_ok(mock_llm):
    mock_llm.return_value = '{"entities": [{"id": "c1", "relations": [{"target_id": "c2", "type": "影响", "notes": ""}]}]}'
    wid = client.post("/api/worlds", json={"name": "文化关系测"}).json()["world"]["meta"]["id"]
    w = client.get(f"/api/worlds/{wid}").json()["world"]
    w["cultures"]["entities"] = [
        {
            "id": "c1",
            "name": "甲",
            "kind": "culture",
            "summary": "",
            "tenets": "",
            "practices": "",
            "sacred_sites": [],
            "key_figures": [],
            "relations": [],
        },
        {
            "id": "c2",
            "name": "乙",
            "kind": "culture",
            "summary": "",
            "tenets": "",
            "practices": "",
            "sacred_sites": [],
            "key_figures": [],
            "relations": [],
        },
    ]
    assert client.put(f"/api/worlds/{wid}", json=w).status_code == 200
    r = client.post(f"/api/worlds/{wid}/refresh/culture-relations", json={"persist": False})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["persisted"] is False
    assert body["world"]["cultures"]["entities"][0]["relations"][0]["target_id"] == "c2"
    w_disk = client.get(f"/api/worlds/{wid}").json()["world"]
    assert w_disk["cultures"]["entities"][0]["relations"] == []
    mock_llm.assert_awaited()


@patch("worldforger.relation_graph_refresh.chat_completion", new_callable=AsyncMock)
def test_refresh_faction_relations_parse_error_returns_ok_false(mock_llm):
    mock_llm.return_value = "not json at all"
    wid = client.post("/api/worlds", json={"name": "派系解析败"}).json()["world"]["meta"]["id"]
    w = client.get(f"/api/worlds/{wid}").json()["world"]
    w["factions"]["entities"] = [
        {
            "id": "f1",
            "name": "A",
            "goals": "",
            "territory": "",
            "key_figures": [],
            "relations": [],
        },
        {
            "id": "f2",
            "name": "B",
            "goals": "",
            "territory": "",
            "key_figures": [],
            "relations": [],
        },
    ]
    assert client.put(f"/api/worlds/{wid}", json=w).status_code == 200
    r = client.post(f"/api/worlds/{wid}/refresh/faction-relations", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "error" in body
