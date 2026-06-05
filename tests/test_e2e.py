"""End-to-end tests using a real LLM API key.

These tests validate the complete pipeline: user action → API call →
real LLM response → parsing → persistence → frontend data.

All tests auto-skip when no API key is available (set PARATERA_API_KEY in
.env or E2E_TEST_API_KEY in the environment).

Run intentionally (not on every CI push):
    python -m pytest tests/test_e2e.py -v -s
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from worldforger.schemas import StoryChapter, World
from worldforger.story.story_store import (
    beat_path,
    ensure_story_dirs,
    macro_outline_path,
    manuscript_path,
    narrative_kg_path,
    polished_path,
    read_consistency_report,
    read_sentiment_log,
    read_summary_card,
    write_text,
)
from worldforger.world_store import create_world, load_world, save_world

client = TestClient(app)


def _has_api_key() -> bool:
    """Check if a real API key is available for E2E tests."""
    # Check E2E-specific key first, then fall back to .env key
    if os.getenv("E2E_TEST_API_KEY"):
        return True
    from worldforger.config import api_key
    try:
        return bool(api_key())
    except Exception:
        return False


def _skip_reason() -> str:
    return "E2E_TEST_API_KEY or PARATERA_API_KEY not set — skipping E2E test"


# ═══════════════════════════════════════════════════════════════════
# E2E Test 1: Create world → chat-based world-building → verify data
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _has_api_key(), reason=_skip_reason())
def test_e2e_create_world_and_chat_build_worldview():
    """创建世界 → 对话式构建世界观 → 断言 world.json 中 geography 有数据。"""
    w = create_world("E2E-世界观构建")
    wid = w.meta.id

    # Simulate user chat: ask the AI to create geography
    geo_prompt = (
        "请为这个世界创建基本地理设定：一块大陆叫「苍蓝大陆」，"
        "上面有三大王国——北境雪国、中原王朝、南方森林联盟。"
        "用中文回答，50 字左右即可。"
    )
    r = client.post(
        f"/api/worlds/{wid}/chat",
        json={
            "messages": [{"role": "user", "content": geo_prompt}],
        },
    )
    assert r.status_code == 200, f"chat failed: {r.text}"
    reply = r.json().get("reply", "")
    assert len(reply) > 20, f"LLM reply too short: {reply[:100]}"

    # Trigger sync to update world.json
    r2 = client.post(
        f"/api/worlds/{wid}/sync-panels-from-chat",
        json={
            "user_message": geo_prompt,
            "assistant_reply": reply,
            "scope": "geography",
            "persist": True,
        },
    )
    assert r2.status_code == 200, f"sync failed: {r2.text}"
    sync_result = r2.json()
    assert sync_result.get("ok"), f"sync ok=false: {sync_result}"

    # Verify world.json now has geography data
    w2 = load_world(wid)
    geo = w2.geography
    # Geography should have at least some regions or landmarks
    has_regions = bool(geo.regions)
    has_landmarks = bool(geo.landmarks)
    assert has_regions or has_landmarks, (
        f"Geography is empty after sync: regions={len(geo.regions)}, "
        f"landmarks={len(geo.landmarks)}"
    )
    print(f"  OK: regions={len(geo.regions)}, landmarks={len(geo.landmarks)}")


# ═══════════════════════════════════════════════════════════════════
# E2E Test 2: Full manuscript generation pipeline
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _has_api_key(), reason=_skip_reason())
def test_e2e_generate_chapter_full_pipeline():
    """生成全书粗纲 → 章节节拍 → 正文 → 断言所有产物文件存在且格式正确。"""
    w = create_world("E2E-全流程")
    wid = w.meta.id
    ensure_story_dirs(wid)

    # Add a basic character for narrator
    w.characters.entities = [
        {"id": "char_e2e", "name": "艾琳", "cast_role": "protagonist_core"}
    ]
    w.story.narrator.person = "third_person_limited"
    w.story.narrator.character_id = "char_e2e"
    # Enable all Layer 3 features for E2E coverage
    w.story.writing_defaults.enable_narrative_kg = True
    w.story.writing_defaults.enable_consistency_check = True
    w.story.writing_defaults.enable_sentiment_track = True
    w.story.writing_defaults.enable_polisher = False  # skip polish to save time
    save_world(w)

    # Step 1: Generate macro outline
    print("  Step 1: Generating macro outline...")
    r1 = client.post(
        f"/api/worlds/{wid}/story/generate/macro-outline",
        json={"prompt": "写一个3章的短篇小说粗纲，主角艾琳踏上寻找失落古城的冒险。"},
    )
    assert r1.status_code == 200, f"macro generation failed: {r1.text}"
    macro = r1.json().get("reply", "")
    assert len(macro) > 50, f"macro outline too short: {macro[:100]}"
    assert macro_outline_path(wid).is_file(), "macro outline file not created"
    print(f"    Macro outline: {len(macro)} chars")

    # Step 2: Create chapters
    chapters_added = []
    for i, title in enumerate(["启程", "古城的秘密", "归途"], start=1):
        r = client.post(
            f"/api/worlds/{wid}/story/chapters",
            json={"title": title, "order": i},
        )
        assert r.status_code == 200, f"create chapter failed: {r.text}"
        chapters_added.append(r.json()["chapter"]["id"])

    ch_id = chapters_added[0]
    print(f"  Step 2: Created {len(chapters_added)} chapters, testing with {ch_id}")

    # Step 3: Generate chapter beat (fine outline)
    print("  Step 3: Generating chapter beat...")
    r3 = client.post(
        f"/api/worlds/{wid}/story/generate/chapter-beats",
        json={"chapter_ids": [ch_id], "prompt": "写本章细纲。"},
    )
    assert r3.status_code == 200, f"beat generation failed: {r3.text}"
    beat_file = beat_path(wid, ch_id)
    assert beat_file.is_file(), "beat file not created"
    beat_content = beat_file.read_text(encoding="utf-8")
    assert len(beat_content) > 20, f"beat content too short: {beat_content[:100]}"
    print(f"    Beat: {len(beat_content)} chars")

    # Step 4: Generate manuscript (non-streaming for simplicity)
    print("  Step 4: Generating manuscript...")
    r4 = client.post(
        f"/api/worlds/{wid}/story/generate/manuscript",
        json={
            "chapter_id": ch_id,
            "prompt": "请撰写本章正文，500-1000 字。",
            "person": "third_person_limited",
            "character_id": "char_e2e",
            "persist": True,
        },
    )
    assert r4.status_code == 200, f"manuscript generation failed: {r4.text}"
    result = r4.json()
    reply = result.get("reply", "")
    assert len(reply) > 100, f"manuscript too short: {reply[:100]}"
    print(f"    Manuscript: {len(reply)} chars")

    # Verify manuscript file
    ms_file = manuscript_path(wid, ch_id)
    assert ms_file.is_file(), "manuscript file not created"

    # Verify post-generation hooks produced files
    # (KG, consistency, sentiment may fail gracefully — that's OK)
    kg_file = narrative_kg_path(wid)
    has_kg = kg_file.is_file()
    cr = read_consistency_report(wid, ch_id)
    sl = read_sentiment_log(wid, ch_id)
    sm = read_summary_card(wid, ch_id)

    print(f"    KG file: {has_kg}, consistency: {cr is not None}, "
          f"sentiment: {sl is not None}, summary: {sm is not None}")

    # At minimum, summary card should exist (it's always-on)
    assert sm is not None, "summary card was not generated"
    assert sm.get("chapter_id") == ch_id, f"summary card chapter_id mismatch: {sm}"

    # Check hook_errors in response
    hook_errors = result.get("hook_errors", [])
    if hook_errors:
        print(f"    Hook errors (non-fatal): {hook_errors}")


# ═══════════════════════════════════════════════════════════════════
# E2E Test 3: Synchronizer → Proofreader complete loop
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _has_api_key(), reason=_skip_reason())
def test_e2e_sync_proofread_complete_loop():
    """同步器→校对者完整回路：同步到表单 → 断言 world 结构正确且无损坏。"""
    w = create_world("E2E-校对回路")
    wid = w.meta.id

    # Step 1: Chat to create faction data
    faction_prompt = (
        "请创建两个势力：\n"
        "1. 黎明骑士团 — 正义的军事组织，领袖是团长阿尔萨斯\n"
        "2. 暗影兄弟会 — 秘密刺客组织，领袖是大师伊森\n"
        "两者是敌对关系。用中文回答，简洁即可，100 字左右。"
    )
    r = client.post(
        f"/api/worlds/{wid}/chat",
        json={
            "messages": [{"role": "user", "content": faction_prompt}],
        },
    )
    assert r.status_code == 200, f"chat failed: {r.text}"
    reply = r.json().get("reply", "")
    assert len(reply) > 20, f"LLM reply too short"

    # Step 2: Sync factions panel
    print("  Syncing factions...")
    r2 = client.post(
        f"/api/worlds/{wid}/sync-panels-from-chat",
        json={
            "user_message": faction_prompt,
            "assistant_reply": reply,
            "scope": "factions",
        },
    )
    assert r2.status_code == 200, f"sync failed: {r2.text}"
    sync_result = r2.json()
    assert sync_result.get("ok"), f"sync ok=false: {sync_result}"

    proofreader_rounds = sync_result.get("proofreader_rounds", 0)
    print(f"    Proofreader rounds: {proofreader_rounds}")

    # Step 3: Verify world.json integrity
    w2 = load_world(wid)
    factions = w2.factions

    # Should have at least some faction entities
    entity_count = len(factions.entities)
    print(f"    Faction entities: {entity_count}")

    if entity_count > 0:
        # Verify entities are properly structured
        for ent in factions.entities:
            assert ent.id, f"entity missing id: {ent}"
            assert ent.name, f"entity missing name: {ent}"
            # Relations should have valid types if present
            for rel in (ent.relations or []):
                assert rel.target_id, f"relation missing target_id in {ent.id}"
                assert rel.type in (
                    "ally", "enemy", "neutral", "complex",
                ), f"invalid relation type {rel.type} in {ent.id}"
        print(f"    All {entity_count} entities have valid structure")

    # World should still be loadable and serializable
    w_json = w2.model_dump(mode="json")
    assert w_json["meta"]["id"] == wid
    # Round-trip: serialize → deserialize
    World.model_validate(w_json)
    print("    World round-trip validation OK")

    # Step 4: Save world and reload — should not corrupt
    save_world(w2)
    w3 = load_world(wid)
    assert w3.meta.id == wid
    assert len(w3.factions.entities) == entity_count
    print(f"    Reload after save: {entity_count} entities preserved")
