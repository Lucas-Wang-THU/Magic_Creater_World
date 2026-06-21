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


def test_fix_references_dry_run_and_apply():
    wid = client.post("/api/worlds", json={"name": "Fix 引用"}).json()["world"]["meta"]["id"]
    w = client.get(f"/api/worlds/{wid}").json()["world"]
    w["factions"]["entities"] = [
        {"id": "f1", "name": "一", "relations": [{"target_id": "ghost", "type": "enemy"}]},
    ]
    assert client.put(f"/api/worlds/{wid}", json=w).status_code == 200
    assert client.get(f"/api/worlds/{wid}/lint-references").json()["ok"] is False
    dr = client.post(f"/api/worlds/{wid}/fix-references", json={"dry_run": True})
    assert dr.status_code == 200
    dj = dr.json()
    assert dj["dry_run"] is True
    assert dj["apply_count"] >= 1
    assert client.get(f"/api/worlds/{wid}/lint-references").json()["ok"] is False
    ap = client.post(f"/api/worlds/{wid}/fix-references", json={"dry_run": False})
    assert ap.status_code == 200
    aj = ap.json()
    assert aj["saved"] is True
    assert aj["lint"]["ok"] is True
    w2 = client.get(f"/api/worlds/{wid}").json()["world"]
    assert w2["factions"]["entities"][0]["relations"] == []


def test_fix_references_404():
    assert client.post("/api/worlds/nonexistent-world-00000000/fix-references", json={}).status_code == 404


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


@patch("app.main.chat_completion", new_callable=AsyncMock, return_value="生态正文")
def test_ecology_generate_returns_reply(mock_chat):
    wid = client.post("/api/worlds", json={"name": "生态API"}).json()["world"]["meta"]["id"]
    r = client.post(
        f"/api/worlds/{wid}/ecology-generate",
        json={"hint": "强调夜行生物"},
    )
    assert r.status_code == 200
    assert r.json().get("reply") == "生态正文"
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

    old = os.environ.get("PARATERA_API_KEY")
    old2 = os.environ.get("OPENAI_API_KEY")
    os.environ["PARATERA_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""
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
        else:
            os.environ.pop("PARATERA_API_KEY", None)
        if old2 is not None:
            os.environ["OPENAI_API_KEY"] = old2
        else:
            os.environ.pop("OPENAI_API_KEY", None)
        get_settings.cache_clear()


@patch("app.main.sync_panels_from_dialogue", new_callable=AsyncMock)
def test_sync_panels_endpoint(mock_sync):
    from worldforger.world_store import load_world

    wid = client.post("/api/worlds", json={"name": "同步测"}).json()["world"]["meta"]["id"]
    w = load_world(wid)
    w2 = w.model_copy(deep=True)
    w2.geography.summary = "从对话合并"
    mock_sync.return_value = {
        "ok": True,
        "world": w2,
        "updated_sections": ["geography"],
        "applied_patch": {"geography": {"summary": "从对话合并"}},
        "structure_output_keys": ["geography"],
        "scope_applied": "geography",
        "merge_warnings": [],
        "normalize_notes": {},
        "proofreader_rounds": 0,
        "proofreader_final_verdict": "ok",
        "proofreader_issues": [],
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


@patch("app.main.sync_panels_from_dialogue", new_callable=AsyncMock)
@patch("app.main.chat_completion", new_callable=AsyncMock, return_value="structured geography reply")
def test_chat_auto_sync_persists_world_json(mock_chat, mock_sync):
    from worldforger.world_store import load_world

    wid = client.post("/api/worlds", json={"name": "auto sync chat"}).json()["world"]["meta"]["id"]
    original = load_world(wid)
    merged = original.model_copy(deep=True)
    merged.geography.summary = "auto persisted geography"
    mock_sync.return_value = {
        "ok": True,
        "world": merged,
        "updated_sections": ["geography"],
        "applied_patch": {"geography": {"summary": "auto persisted geography"}},
        "structure_output_keys": ["geography"],
        "scope_applied": "geography",
        "merge_warnings": [],
        "normalize_notes": {},
        "proofreader_rounds": 0,
        "proofreader_final_verdict": "ok",
        "proofreader_issues": [],
        "format_proofreader_used": False,
        "format_stages": [],
    }

    r = client.post(
        f"/api/worlds/{wid}/chat",
        json={
            "messages": [{"role": "user", "content": "please add a plateau"}],
            "auto_sync": True,
            "persist_sync": True,
            "sync_scope": "geography",
            "proofreader_max_retries": 0,
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "structured geography reply"
    assert body["sync"]["ok"] is True
    assert body["sync"]["persisted"] is True
    assert body["world"]["geography"]["summary"] == "auto persisted geography"
    saved = load_world(wid)
    assert saved.geography.summary == "auto persisted geography"
    assert saved.meta.version == original.meta.version + 1
    mock_chat.assert_awaited()
    mock_sync.assert_awaited()
    _args, kwargs = mock_sync.call_args
    assert kwargs["user_message"] == "please add a plateau"
    assert kwargs["assistant_reply"] == "structured geography reply"
    assert kwargs["scope"] == "geography"
    assert kwargs["proofreader_max_retries"] == 0


@patch("app.main.sync_panels_from_dialogue", new_callable=AsyncMock)
@patch("app.main.chat_completion", new_callable=AsyncMock, return_value="structured character reply")
def test_character_chat_auto_sync_defaults_to_characters(mock_chat, mock_sync):
    from worldforger.world_store import load_world

    wid = client.post("/api/worlds", json={"name": "auto sync characters"}).json()["world"]["meta"]["id"]
    original = load_world(wid)
    merged = original.model_copy(deep=True)
    merged.characters.summary = "auto persisted cast"
    mock_sync.return_value = {
        "ok": True,
        "world": merged,
        "updated_sections": ["characters"],
        "applied_patch": {"characters": {"summary": "auto persisted cast"}},
        "structure_output_keys": ["characters"],
        "scope_applied": "characters",
        "merge_warnings": [],
        "normalize_notes": {},
        "proofreader_rounds": 0,
        "proofreader_final_verdict": "ok",
        "proofreader_issues": [],
        "format_proofreader_used": False,
        "format_stages": [],
    }

    r = client.post(
        f"/api/worlds/{wid}/character-chat",
        json={
            "messages": [{"role": "user", "content": "add the main cast"}],
            "auto_sync": True,
            "persist_sync": True,
            "proofreader_max_retries": 0,
        },
    )

    assert r.status_code == 200
    body = r.json()
    assert body["sync"]["persisted"] is True
    assert body["world"]["characters"]["summary"] == "auto persisted cast"
    assert load_world(wid).characters.summary == "auto persisted cast"
    mock_chat.assert_awaited()
    mock_sync.assert_awaited()
    _args, kwargs = mock_sync.call_args
    assert kwargs["scope"] == "characters"


@patch("app.main.sync_panels_from_dialogue", new_callable=AsyncMock)
@patch("app.main.chat_completion", new_callable=AsyncMock, return_value="plain reply")
def test_chat_does_not_sync_unless_requested(mock_chat, mock_sync):
    wid = client.post("/api/worlds", json={"name": "manual sync chat"}).json()["world"]["meta"]["id"]
    r = client.post(
        f"/api/worlds/{wid}/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert r.status_code == 200
    assert r.json() == {"reply": "plain reply"}
    mock_chat.assert_awaited()
    mock_sync.assert_not_awaited()


@patch("app.main.chat_completion", new_callable=AsyncMock)
def test_chat_writes_each_turn_to_world_sessions(mock_chat):
    import json

    from worldforger.world_store import sessions_dir

    mock_chat.side_effect = ["reply one", "reply two"]
    wid = client.post("/api/worlds", json={"name": "session turns"}).json()["world"]["meta"]["id"]

    for text in ("first user turn", "second user turn"):
        r = client.post(
            f"/api/worlds/{wid}/chat",
            json={"messages": [{"role": "user", "content": text}]},
        )
        assert r.status_code == 200

    sdir = sessions_dir(wid)
    md_files = sorted(p for p in sdir.glob("*.md") if p.name != "world.md")
    assert len(md_files) >= 2
    assert len({p.name for p in md_files}) == len(md_files)
    jsonl = sdir / "dialogues.jsonl"
    assert jsonl.is_file()
    rows = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) >= 2
    assert rows[-2]["user"] == "first user turn"
    assert rows[-2]["assistant"] == "reply one"
    assert rows[-1]["user"] == "second user turn"
    assert rows[-1]["assistant"] == "reply two"
    assert rows[-1]["kind"] == "chat"


@patch("app.main.chat_completion", new_callable=AsyncMock)
def test_chat_token_usage_is_persisted_for_world(mock_chat):
    from worldforger.llm import drain_token_usage, record_token_usage
    from worldforger.story.story_store import read_token_usage

    drain_token_usage()

    async def _reply(_messages, **_kwargs):
        record_token_usage(
            "chat_completion",
            prompt_chars=400,
            completion_chars=200,
        )
        return "reply with usage"

    mock_chat.side_effect = _reply
    wid = client.post("/api/worlds", json={"name": "token persist chat"}).json()["world"]["meta"]["id"]
    r = client.post(
        f"/api/worlds/{wid}/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert r.status_code == 200

    saved = read_token_usage(wid)
    assert saved["prompt_tokens"] == 100
    assert saved["completion_tokens"] == 50
    assert saved["total_tokens"] == 150
    assert saved["by_context"]["world_chat"]["total_tokens"] == 150
    assert saved["by_label"]["chat_completion"]["total_tokens"] == 150

    usage = client.get(f"/api/worlds/{wid}/token-usage")
    assert usage.status_code == 200
    body = usage.json()
    assert body["persisted"]["total_tokens"] == 150
    assert body["persisted"]["by_context"]["world_chat"]["total_tokens"] == 150
    assert body["total"]["total_tokens"] == 150


def test_add_profession_requires_existing_power_tier():
    from worldforger.schemas import PowerTier
    from worldforger.world_store import load_world, save_world

    wid = client.post("/api/worlds", json={"name": "profession existing tier"}).json()["world"]["meta"]["id"]
    w = load_world(wid)
    w.power_system.tiers.append(PowerTier(name="Tier A", description="known"))
    save_world(w, export_markdown=False)

    missing = client.post(
        f"/api/worlds/{wid}/power-system/professions",
        json={"tier_name": "Tier B", "profession": {"id": "prof_b", "name": "Profession B"}},
    )
    assert missing.status_code == 404
    assert load_world(wid).power_system.profession_system.by_tier == []

    ok = client.post(
        f"/api/worlds/{wid}/power-system/professions",
        json={"tier_name": "Tier A", "profession": {"id": "prof_a", "name": "Profession A"}},
    )
    assert ok.status_code == 200
    saved = load_world(wid)
    assert len(saved.power_system.profession_system.by_tier) == 1
    assert saved.power_system.profession_system.by_tier[0].tier_name == "Tier A"
    assert saved.power_system.profession_system.by_tier[0].professions[0].id == "prof_a"


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


def test_character_detail_patch_skills_and_notable_skills():
    from worldforger.world_store import load_world

    wid = client.post("/api/worlds", json={"name": "skill patch"}).json()["world"]["meta"]["id"]
    w = client.get(f"/api/worlds/{wid}").json()["world"]
    w["characters"]["entities"].append(
        {"id": "ch_test", "name": "测试", "age": 20, "gender": "男"}
    )
    client.put(f"/api/worlds/{wid}", json=w)

    r = client.patch(
        f"/api/worlds/{wid}/characters/ch_test",
        json={
            "skills": [
                {"name": "剑术", "description": "基础剑法", "exclusive": False, "level": "入门"},
                {"name": "专属领域", "exclusive": True},
            ],
            "notable_skills": ["剑术", "专注"],
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "skills" in r.json()["updated_fields"]
    assert "notable_skills" in r.json()["updated_fields"]

    saved = load_world(wid)
    char = next(e for e in saved.characters.entities if e.get("id") == "ch_test")
    assert len(char["skills"]) == 2
    assert char["skills"][0]["name"] == "剑术"
    assert char["skills"][0]["level"] == "入门"
    assert char["skills"][1]["exclusive"] is True
    assert char["notable_skills"] == ["剑术", "专注"]

    detail = client.get(f"/api/worlds/{wid}/characters/ch_test/detail").json()
    assert detail["skills"][0]["name"] == "剑术"
    assert detail["notable_skills"] == ["剑术", "专注"]


def test_clear_knowledge_graph_clears_all_tracking_sections():
    from worldforger.world_store import load_world

    wid = client.post("/api/worlds", json={"name": "clear tracking"}).json()["world"]["meta"]["id"]
    w = client.get(f"/api/worlds/{wid}").json()["world"]
    w["characters"]["entities"].append(
        {"id": "ch_a", "name": "A", "speech_profile": {"avg_sentence_length": "short", "verbal_tics": ["啧"]}}
    )
    w["character_knowledge"]["entries"].append({"knowledge_id": "k1", "character_id": "ch_a", "topic": "测试"})
    w["character_decisions"].append({"decision_id": "d1", "character_id": "ch_a", "type": "moral_choice"})
    w["character_physical_states"].append({"character_id": "ch_a", "fatigue": "tired"})
    w["character_personal_timelines"].append({"character_id": "ch_a", "events": [{"chapter_id": "ch1", "title": "出生"}]})
    w["character_aftermaths"].append({"aftermath_id": "a1", "character_id": "ch_a", "current_status": "active"})
    client.put(f"/api/worlds/{wid}", json=w)

    r = client.post(f"/api/worlds/{wid}/knowledge-graph/clear")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["world"]["character_knowledge"]["entries"] == []
    assert body["world"]["character_decisions"] == []
    assert body["world"]["character_physical_states"] == []
    assert body["world"]["character_personal_timelines"] == []
    assert body["world"]["character_aftermaths"] == []
    ent = next(e for e in body["world"]["characters"]["entities"] if e["id"] == "ch_a")
    assert not ent.get("speech_profile")

    saved = load_world(wid)
    assert saved.character_knowledge.entries == []
    assert saved.character_decisions == []
    assert saved.character_physical_states == []
    assert saved.character_personal_timelines == []
    assert saved.character_aftermaths == []
