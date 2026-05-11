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
    body = r2.json()
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
