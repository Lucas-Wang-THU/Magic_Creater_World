from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from worldforger.schemas import World
from worldforger.story_store import macro_outline_path, unit_label_for_mode
from worldforger.world_store import create_world, load_world, save_world

client = TestClient(app)


def test_unit_label_for_mode():
    assert unit_label_for_mode("novel") == "章"
    assert unit_label_for_mode("game") == "章节"
    assert unit_label_for_mode("coc") == "跑团会话"
    assert unit_label_for_mode("dnd") == "跑团会话"


def test_world_has_story_section():
    w = create_world("情节 schema")
    assert hasattr(w, "story")
    assert w.story.chapters == []


def test_story_chapter_crud():
    w = create_world("情节 CRUD")
    wid = w.meta.id
    r = client.post(f"/api/worlds/{wid}/story/chapters", json={"title": "开端"})
    assert r.status_code == 200
    ch = r.json()["chapter"]
    assert ch["id"].startswith("ch_")
    w2 = load_world(wid)
    assert len(w2.story.chapters) == 1
    r2 = client.get(f"/api/worlds/{wid}/story/chapters/{ch['id']}/beat")
    assert r2.status_code == 200
    client.put(
        f"/api/worlds/{wid}/story/chapters/{ch['id']}/beat",
        json={"content": "# 细纲\n\n冲突爆发。"},
    )
    beat = client.get(f"/api/worlds/{wid}/story/chapters/{ch['id']}/beat").json()["content"]
    assert "冲突" in beat
    client.delete(f"/api/worlds/{wid}/story/chapters/{ch['id']}")
    w3 = load_world(wid)
    assert len(w3.story.chapters) == 0


def test_story_macro_outline_put_get():
    w = create_world("粗纲读写")
    wid = w.meta.id
    client.put(f"/api/worlds/{wid}/story/macro-outline", json={"content": "# 粗纲\n\n第一幕。"})
    g = client.get(f"/api/worlds/{wid}/story/macro-outline")
    assert "第一幕" in g.json()["content"]
    assert macro_outline_path(wid).is_file()


@patch("app.main.generate_macro_outline", new_callable=AsyncMock, return_value="# AI 粗纲")
def test_story_generate_macro(mock_gen):
    w = create_world("生成粗纲")
    wid = w.meta.id
    r = client.post(
        f"/api/worlds/{wid}/story/generate/macro-outline",
        json={"prompt": "写粗纲", "persist": True},
    )
    assert r.status_code == 200
    assert "AI 粗纲" in r.json()["reply"]
    mock_gen.assert_awaited_once()
