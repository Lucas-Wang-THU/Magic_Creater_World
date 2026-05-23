from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from worldforger.world_store import create_world

client = TestClient(app)


@patch(
    "app.main.run_story_chat_agent",
    new_callable=AsyncMock,
    return_value={
        "reply": "情节回复",
        "world": None,
        "actions": [],
        "intent": None,
        "auto_applied": [],
        "auto_warnings": [],
    },
)
def test_story_chat_endpoint(mock_agent):
    w = create_world("情节对话")
    wid = w.meta.id
    r = client.post(
        f"/api/worlds/{wid}/story-chat",
        json={"messages": [{"role": "user", "content": "写粗纲"}], "active_chapter_id": ""},
    )
    assert r.status_code == 200
    assert r.json()["reply"] == "情节回复"
    mock_agent.assert_awaited_once()


@patch("app.main.chat_completion", new_callable=AsyncMock, return_value="纯文本")
def test_story_chat_without_tools(mock_chat):
    w = create_world("情节对话无工具")
    wid = w.meta.id
    r = client.post(
        f"/api/worlds/{wid}/story-chat",
        json={
            "messages": [{"role": "user", "content": "闲聊"}],
            "use_tools": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["reply"] == "纯文本"
    mock_chat.assert_awaited_once()


@patch("app.main.sync_panels_from_dialogue", new_callable=AsyncMock)
def test_sync_panels_story_scope(mock_sync):
    w = create_world("情节同步")
    wid = w.meta.id
    w.story.summary = "旧"
    merged = w.model_copy(deep=True)
    merged.story.summary = "新总览"
    mock_sync.return_value = {
        "world": merged,
        "updated_sections": ["story"],
        "applied_patch": {"story": {"summary": "新总览"}},
        "structure_output_keys": ["story"],
        "scope_applied": "story",
        "merge_warnings": [],
        "normalize_notes": {},
        "proofreader_rounds": 0,
        "proofreader_final_verdict": "ok",
        "proofreader_issues": [],
    }
    r = client.post(
        f"/api/worlds/{wid}/sync-panels-from-chat",
        json={
            "user_message": "更新情节总览",
            "assistant_reply": "好",
            "scope": "story",
            "persist": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "story" in body["updated_sections"]
    mock_sync.assert_awaited_once()
