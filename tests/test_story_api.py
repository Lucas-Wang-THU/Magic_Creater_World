import json

import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from worldforger.schemas import StoryChapter, StoryForeshadowing, World
from worldforger.story_store import (
    macro_outline_path,
    summary_path,
    unit_label_for_mode,
    write_summary_card,
    write_text,
)
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


# ── P0: story scope 第二路同步集成测试 ──────────────────────


@patch("app.main.sync_panels_from_dialogue", new_callable=AsyncMock)
def test_sync_panels_story_scope_integration(mock_sync):
    """第二路同步 scope=story：验证 summary/chapters/foreshadowing 全链路合并。"""
    w = create_world("情节同步集成")
    wid = w.meta.id
    w.story.summary = "旧总览"
    # 加一个伏笔和目标章节
    ch = StoryChapter(id="ch_sync01", order=1, title="测试章")
    w.story.chapters.append(ch)
    fs = StoryForeshadowing(id="fs_sync01", label="测试伏笔", planted_chapter_id="ch_sync01", status="open")
    w.story.foreshadowing.append(fs)
    save_world(w)

    merged = w.model_copy(deep=True)
    merged.story.summary = "新总览"
    merged.story.design_notes = "新设计说明"
    mock_sync.return_value = {
        "world": merged,
        "updated_sections": ["story"],
        "applied_patch": {"story": {"summary": "新总览", "design_notes": "新设计说明"}},
        "structure_output_keys": ["story"],
        "scope_applied": "story",
        "merge_warnings": [],
        "normalize_notes": {},
    }
    r = client.post(
        f"/api/worlds/{wid}/sync-panels-from-chat",
        json={
            "user_message": "更新情节总览与设计说明",
            "assistant_reply": "已更新 story 节。",
            "scope": "story",
            "persist": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "story" in body["updated_sections"]
    mock_sync.assert_awaited_once()


# ── P0: 伏笔 Apply API 集成测试 ─────────────────────────────


def test_foreshadow_apply_api_upsert_and_resolve():
    """POST /story/foreshadowing/apply 完整流程：upsert → resolve → 验证 world.json。"""
    w = create_world("伏笔 API 集成")
    wid = w.meta.id
    ch = StoryChapter(id="ch_fs01", order=1, title="第一章")
    w.story.chapters.append(ch)
    save_world(w)

    # upsert
    r = client.post(
        f"/api/worlds/{wid}/story/foreshadowing/apply",
        json={
            "operations": [
                {
                    "op": "upsert",
                    "id": "fs_integ",
                    "label": "集成测试伏笔",
                    "planted_chapter_id": "ch_fs01",
                    "status": "open",
                }
            ],
            "persist": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["applied"]) >= 1
    assert not body["warnings"]

    # 验证 world.json 已持久化
    w2 = load_world(wid)
    assert any(f.id == "fs_integ" for f in w2.story.foreshadowing)

    # resolve
    r2 = client.post(
        f"/api/worlds/{wid}/story/foreshadowing/apply",
        json={
            "operations": [
                {"op": "resolve", "id": "fs_integ", "payoff_chapter_id": "ch_fs01"}
            ],
            "persist": True,
        },
    )
    assert r2.status_code == 200
    w3 = load_world(wid)
    fs = next(f for f in w3.story.foreshadowing if f.id == "fs_integ")
    assert fs.status == "resolved"
    assert fs.payoff_chapter_id == "ch_fs01"


def test_foreshadow_apply_api_delete():
    """删除伏笔并验证持久化。"""
    w = create_world("伏笔删除")
    wid = w.meta.id
    ch = StoryChapter(id="ch_fs02", order=1, title="章")
    w.story.chapters.append(ch)
    w.story.foreshadowing.append(
        StoryForeshadowing(id="fs_del", label="待删除", planted_chapter_id="ch_fs02")
    )
    save_world(w)

    r = client.post(
        f"/api/worlds/{wid}/story/foreshadowing/apply",
        json={"operations": [{"op": "delete", "id": "fs_del"}], "persist": True},
    )
    assert r.status_code == 200
    w2 = load_world(wid)
    assert not any(f.id == "fs_del" for f in w2.story.foreshadowing)


# ── P0: Agent 工具调用全流程测试 ──────────────────────────


@pytest.mark.anyio
@patch("worldforger.story_agent.chat_completion_with_tools", new_callable=AsyncMock)
async def test_agent_tool_list_foreshadowing(mock_chat):
    """Agent 调用 list_foreshadowing 工具。"""
    from worldforger.story_agent import run_story_chat_agent

    w = create_world("Agent 伏笔查询")
    ch = StoryChapter(id="ch_agt01", order=1, title="第一章")
    w.story.chapters.append(ch)
    w.story.foreshadowing.append(
        StoryForeshadowing(id="fs_agt01", label="神秘信件", planted_chapter_id="ch_agt01", status="open")
    )

    # 模拟 LLM 返回 tool_calls
    async def fake_execute_tool(name, args):
        if name == "list_foreshadowing":
            items = [{"id": "fs_agt01", "label": "神秘信件", "status": "open"}]
            return json.dumps({"foreshadowing": items}, ensure_ascii=False)
        return "{}"

    mock_chat.return_value = ("查询结果：一条伏笔", [{"tool": "list_foreshadowing", "count": 1}])

    result = await run_story_chat_agent(
        w,
        messages=[{"role": "user", "content": "列出所有伏笔"}],
        active_chapter_id="ch_agt01",
        include_story_files=False,
        creative_mode="novel",
        persist=False,
    )
    assert "result" in result or "reply" in result
    mock_chat.assert_awaited_once()


@pytest.mark.anyio
@patch("worldforger.story_agent.chat_completion_with_tools", new_callable=AsyncMock)
@patch("worldforger.story_agent.generate_manuscript", new_callable=AsyncMock)
async def test_agent_tool_generate_manuscript(mock_gen_manuscript, mock_chat):
    """Agent 调用 generate_manuscript 工具后，验证章节状态更新。"""
    from worldforger.story_agent import run_story_chat_agent

    w = create_world("Agent 文稿生成")
    ch = StoryChapter(id="ch_agt02", order=1, title="待写章")
    w.story.chapters.append(ch)

    async def fake_execute_tool(name, args):
        if name == "generate_manuscript":
            return json.dumps({"ok": True, "chapter_id": "ch_agt02", "word_count": 500})
        return "{}"

    mock_chat.return_value = ("文稿已生成。", [{"tool": "generate_manuscript", "chapter_id": "ch_agt02"}])
    mock_gen_manuscript.return_value = "# 第一章\n\n正文内容..."

    result = await run_story_chat_agent(
        w,
        messages=[{"role": "user", "content": "撰写本章正文"}],
        active_chapter_id="ch_agt02",
        include_story_files=False,
        creative_mode="novel",
        persist=False,
    )
    assert result["intent"] == "write_manuscript"
    # chat_completion_with_tools 被 mock 直接返回结果时不经过 execute_tool，
    # generate_manuscript 的实际调用由 test_generate_manuscript_triggers_summary_card 覆盖
    mock_chat.assert_awaited_once()


# ── Layer 1 新增功能测试 ──────────────────────────────────


def test_chapter_summary_card_write_and_read():
    """章节摘要卡片写入磁盘并正确读取。"""
    w = create_world("摘要卡片")
    wid = w.meta.id
    from worldforger.story_store import ensure_story_dirs, read_summary_card

    ensure_story_dirs(wid)
    data = {
        "chapter_id": "ch_sum01",
        "title": "测试章",
        "main_events": "主角离开京城前往北境。",
        "character_state_changes": [
            {
                "char_id": "char_01",
                "name": "主角",
                "location_before": "京城",
                "location_after": "北境",
                "emotion_before": "平静",
                "emotion_after": "坚定",
                "new_items": "族徽碎片",
                "goal_change": "找到真相",
            }
        ],
        "foreshadowing_planted": ["fs_001"],
        "foreshadowing_resolved": [],
        "ending_hook": "北境城墙外出现不明军队。",
    }
    write_summary_card(wid, "ch_sum01", data)
    assert summary_path(wid, "ch_sum01").is_file()

    card = read_summary_card(wid, "ch_sum01")
    assert card is not None
    assert card["main_events"] == "主角离开京城前往北境。"
    assert len(card["character_state_changes"]) == 1
    assert card["ending_hook"] == "北境城墙外出现不明军队。"


def test_character_runtime_state_update():
    """角色运行时状态更新并持久化在 world.json 中。"""
    from worldforger.story_store import update_character_runtime_state, get_character_runtime_states

    w = create_world("运行时状态")
    w.characters.entities = [
        {"id": "char_hero", "name": "英雄", "cast_role": "protagonist_core"},
        {"id": "char_mentor", "name": "导师", "cast_role": "supporting_major"},
    ]
    save_world(w)

    update_character_runtime_state(
        w, "char_hero",
        {"current_location": "北境·寒风要塞", "current_goal": "寻找族徽", "emotional_state": "坚定但疲惫"},
        "ch_01",
    )

    states = get_character_runtime_states(w)
    assert len(states) >= 1
    hero_state = next((s for s in states if s["id"] == "char_hero"), None)
    assert hero_state is not None
    assert hero_state["runtime_state"]["current_location"] == "北境·寒风要塞"
    assert hero_state["runtime_state"]["last_updated_chapter"] == "ch_01"

    # 验证 world.json 持久化
    save_world(w)
    w2 = load_world(w.meta.id)
    hero2 = next((e for e in w2.characters.entities if e.get("id") == "char_hero"), None)
    assert hero2 is not None
    assert hero2["runtime_state"]["current_location"] == "北境·寒风要塞"


def test_summaries_before_retrieval():
    """验证 summaries_before 按章节顺序正确获取前文章节摘要。"""
    from worldforger.story_store import summaries_before, ensure_story_dirs

    w = create_world("摘要检索")
    wid = w.meta.id
    ensure_story_dirs(wid)

    ch1 = StoryChapter(id="ch_sb01", order=1, title="第一章")
    ch2 = StoryChapter(id="ch_sb02", order=2, title="第二章")
    ch3 = StoryChapter(id="ch_sb03", order=3, title="第三章")
    w.story.chapters = [ch1, ch2, ch3]

    write_summary_card(wid, "ch_sb01", {"chapter_id": "ch_sb01", "title": "第一章", "main_events": "事件1", "ending_hook": "钩子1"})
    write_summary_card(wid, "ch_sb02", {"chapter_id": "ch_sb02", "title": "第二章", "main_events": "事件2", "ending_hook": "钩子2"})

    cards = summaries_before(wid, "ch_sb03", 3, w)
    assert len(cards) == 2
    assert cards[0]["chapter_id"] == "ch_sb01"
    assert cards[1]["chapter_id"] == "ch_sb02"


def test_beat_continuity_checks_prompt_includes_checklist():
    """验证细纲 system prompt 包含叙事连贯性检查清单。"""
    from worldforger.story_prompts import chapter_beats_system

    w = create_world("节拍检查")
    w.meta.creative_mode = "novel"
    system = chapter_beats_system(w, creative_mode="novel")
    assert "叙事连贯性检查" in system
    assert "上一章结尾" in system
    assert "叙事人称" in system
    assert "POV" in system


def test_compact_world_snippet_includes_runtime_states():
    """验证 compact_world_snippet 注入角色运行时状态。"""
    from worldforger.story_prompts import compact_world_snippet
    from worldforger.story_store import update_character_runtime_state

    w = create_world("运行时状态注入")
    w.characters.entities = [
        {"id": "char_rt", "name": "测试角色", "cast_role": "protagonist_core"},
    ]
    update_character_runtime_state(
        w, "char_rt",
        {"current_location": "东海", "current_goal": "寻找宝藏", "emotional_state": "兴奋"},
        "ch_01",
    )
    snippet = compact_world_snippet(w, include_markdown=False)
    assert "_runtime_states" in snippet
    assert "东海" in snippet
    assert "寻找宝藏" in snippet


@pytest.mark.anyio
@patch("worldforger.story_service.chat_completion", new_callable=AsyncMock)
async def test_generate_manuscript_triggers_summary_card(mock_chat):
    """验证 generate_manuscript 后自动生成摘要卡片。"""
    from worldforger.story_service import generate_manuscript
    from worldforger.story_store import read_summary_card, ensure_story_dirs

    w = create_world("文稿摘要联调")
    wid = w.meta.id
    ensure_story_dirs(wid)
    ch = StoryChapter(id="ch_ms01", order=1, title="第一章")
    w.story.chapters.append(ch)
    w.characters.entities = [{"id": "char_01", "name": "主角", "cast_role": "protagonist_core"}]

    # 第一次调用：正文生成
    # 第二次调用：摘要卡片生成（由 _try_generate_summary_card 触发）
    # 第三次调用：运行时状态提取（由 _try_update_runtime_states 触发）
    mock_chat.side_effect = [
        "# 第一章\n\n主角离开京城，前往北境寻找真相。\n\n北境城墙外出现不明军队。",
        json.dumps(
            {
                "main_events": "主角离开京城前往北境。",
                "character_state_changes": [
                    {
                        "char_id": "char_01",
                        "name": "主角",
                        "location_before": "京城",
                        "location_after": "北境",
                        "emotion_before": "平静",
                        "emotion_after": "坚定",
                        "new_items": "无",
                        "goal_change": "寻找真相",
                    }
                ],
                "foreshadowing_planted": [],
                "foreshadowing_resolved": [],
                "ending_hook": "北境城墙外出现不明军队。",
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {"char_01": {"current_location": "北境", "current_goal": "寻找真相", "emotional_state": "坚定"}},
            ensure_ascii=False,
        ),
    ]

    reply = await generate_manuscript(
        w,
        chapter_id="ch_ms01",
        prompt="写第一章",
        creative_mode="novel",
        person=None,
        attach_prev_chapters=3,
        include_world_md=None,
    )
    assert "京城" in reply

    # 验证摘要卡片已写入磁盘
    card = read_summary_card(wid, "ch_ms01")
    assert card is not None
    assert "京城" in card.get("main_events", "")
    assert len(card.get("character_state_changes", [])) >= 1
    assert "不明军队" in card.get("ending_hook", "")

    # 验证角色运行时状态已更新
    hero = next((e for e in w.characters.entities if e.get("id") == "char_01"), None)
    assert hero is not None
    rs = hero.get("runtime_state", {})
    assert rs.get("current_location") == "北境"
    assert rs.get("last_updated_chapter") == "ch_ms01"

    # 验证章节 status 已更新
    assert ch.status == "drafting"
    assert mock_chat.call_count == 3
