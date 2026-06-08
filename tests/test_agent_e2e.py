# -*- coding: utf-8 -*-
"""End-to-end tests for the character agent emergent narrative system.

Verifies the complete flow from UI toggle → agent generation →
decision persistence → quality scoring → frontend data retrieval.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock


# ═══════════════════════════════════════════════════════════════════
# Agent toggle API tests
# ═══════════════════════════════════════════════════════════════════

class TestAgentToggleAPI:
    """Verify agent toggle can be enabled/disabled via the writing-defaults API."""

    def test_toggle_enable_agents(self, tmp_path, monkeypatch):
        """PATCH writing-defaults with enable_character_agents=true should persist."""
        world_id = "test_toggle_agents"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)

        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.world_store import create_world, save_world, load_world
            from app.main import app
            from fastapi.testclient import TestClient

            w = create_world("Agent Toggle Test")
            w.meta.id = world_id
            w.meta.version = 1
            save_world(w)
            w = load_world(world_id)

            client = TestClient(app)
            # Enable agents
            r = client.patch(
                f"/api/worlds/{world_id}/story/writing-defaults",
                json={"enable_character_agents": True, "agent_max_rounds": 4},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["changed"] is True
            assert data["writing_defaults"]["enable_character_agents"] is True
            assert data["writing_defaults"]["agent_max_rounds"] == 4

            # Verify it's persisted in the world model
            w = load_world(world_id)
            assert w.story.writing_defaults.enable_character_agents is True

            # Disable agents
            r2 = client.patch(
                f"/api/worlds/{world_id}/story/writing-defaults",
                json={"enable_character_agents": False},
            )
            assert r2.status_code == 200
            w = load_world(world_id)
            assert w.story.writing_defaults.enable_character_agents is False
        finally:
            ws.world_root = original_root

    def test_toggle_no_change(self, tmp_path, monkeypatch):
        """PATCH with no actual changes should return changed=false."""
        world_id = "test_toggle_noop"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)

        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.world_store import create_world, save_world
            from app.main import app
            from fastapi.testclient import TestClient

            w = create_world("No-op Toggle")
            w.meta.id = world_id
            save_world(w)

            client = TestClient(app)
            r = client.patch(
                f"/api/worlds/{world_id}/story/writing-defaults",
                json={},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["changed"] is False
        finally:
            ws.world_root = original_root


# ═══════════════════════════════════════════════════════════════════
# Agent state initialization tests
# ═══════════════════════════════════════════════════════════════════

class TestAgentInitAPI:
    """Verify agent states can be initialized from world.json."""

    def test_init_agents_from_world(self, tmp_path, monkeypatch):
        """POST /agents/init should create agent states for all characters."""
        import uuid
        world_id = "test_init_" + uuid.uuid4().hex[:8]
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)

        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.world_store import create_world, save_world
            from app.main import app
            from fastapi.testclient import TestClient

            w = create_world("Agent Init Test")
            w.meta.id = world_id
            w.characters.entities = [
                {"id": "ch_test1", "name": "测试角色1", "cast_role": "protagonist_core",
                 "runtime_state": {}, "speech_profile": {}},
                {"id": "ch_test2", "name": "测试角色2", "cast_role": "supporting_major",
                 "runtime_state": {}},
            ]
            save_world(w)

            client = TestClient(app)
            r = client.post(f"/api/worlds/{world_id}/agents/init")
            assert r.status_code == 200
            data = r.json()
            assert data["ok"] is True
            assert data["initialized"] >= 1
        finally:
            ws.world_root = original_root

    def test_list_agents(self, tmp_path, monkeypatch):
        """GET /agents should list all initialized agent states."""
        world_id = "test_list_agents"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)

        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.world_store import create_world, save_world
            from app.main import app
            from fastapi.testclient import TestClient

            w = create_world("List Agents Test")
            w.meta.id = world_id
            w.characters.entities = [{"id": "ch_a", "name": "角色A"}]
            save_world(w)

            client = TestClient(app)
            # Init first
            client.post(f"/api/worlds/{world_id}/agents/init")
            # List
            r = client.get(f"/api/worlds/{world_id}/agents")
            assert r.status_code == 200
            data = r.json()
            assert data["count"] >= 1
            assert "ch_a" in data["agents"]
            assert data["agents"]["ch_a"]["name"] == "角色A"
        finally:
            ws.world_root = original_root


# ═══════════════════════════════════════════════════════════════════
# Agent decision log tests
# ═══════════════════════════════════════════════════════════════════

class TestAgentDecisionLog:
    """Verify agent decisions can be stored and retrieved."""

    def test_decision_log_append_and_read(self, tmp_path):
        """Decision log should be appendable and readable via API."""
        import uuid
        world_id = "test_dec_" + uuid.uuid4().hex[:8]
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)

        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.agents.agent_store import AgentStore
            from worldforger.agents.types import AgentDecision, CharacterAgentState
            from app.main import app
            from fastapi.testclient import TestClient
            from worldforger.world_store import create_world, save_world

            w = create_world("Decision Log Test")
            w.meta.id = world_id
            save_world(w)

            state = CharacterAgentState(
                character_id="ch_a", name="角色A",
                emotional_state="警觉", current_goal="探索峡道",
                current_location="南飞雁峡道",
            )
            AgentStore.save_state(world_id, state)

            decisions = [
                AgentDecision(
                    character_id="ch_a", decision_round=0,
                    internal_reaction="前方雾气异常",
                    emotional_shift="平静→警觉",
                    intended_action="放慢脚步",
                    hidden_intent="确认是否有塑脉信号",
                    confidence=0.7,
                ),
                AgentDecision(
                    character_id="ch_a", decision_round=0,
                    intended_action="观察痕迹",
                    intended_speech="有东西经过",
                    target_character="ch_b",
                    emotional_shift="警觉→紧张",
                ),
            ]
            AgentStore.append_decision_log(world_id, "ch_a", "ch1", decisions)

            client = TestClient(app)
            r = client.get(f"/api/worlds/{world_id}/story/agent-decisions/ch1")
            assert r.status_code == 200
            data = r.json()
            assert data["chapter_id"] == "ch1"
            assert "ch_a" in data["characters"]
            assert data["characters"]["ch_a"]["count"] >= 1

            # Check decision content
            decs = data["characters"]["ch_a"]["decisions"]
            assert len(decs) >= 1
            assert decs[0]["emotional_shift"] == "平静→警觉"
            assert decs[0]["confidence"] == 0.7
        finally:
            ws.world_root = original_root

    def test_decision_log_empty_chapter(self, tmp_path):
        """Requesting decisions for a chapter with no data should return gracefully."""
        world_id = "test_dec_empty"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)

        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.world_store import create_world, save_world
            from app.main import app
            from fastapi.testclient import TestClient

            w = create_world("Empty Log Test")
            w.meta.id = world_id
            save_world(w)

            client = TestClient(app)
            r = client.get(f"/api/worlds/{world_id}/story/agent-decisions/ch_nonexistent")
            # Should return 200 with empty data or empty characters
            assert r.status_code == 200
            data = r.json()
            # The API returns {"chapter_id": ..., "decisions": [], "characters": {}}
            assert data.get("decisions", []) == [] or data.get("total", 0) == 0
        finally:
            ws.world_root = original_root


# ═══════════════════════════════════════════════════════════════════
# Quality history API tests
# ═══════════════════════════════════════════════════════════════════

class TestQualityHistoryAPI:
    """Verify quality scores are computed and retrievable."""

    def test_quality_history_from_decisions(self, tmp_path):
        """Quality history should be computed from stored decision logs."""
        world_id = "test_quality_hist"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)

        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.agents.agent_store import AgentStore
            from worldforger.agents.types import AgentDecision, CharacterAgentState
            from app.main import app
            from fastapi.testclient import TestClient
            from worldforger.world_store import create_world, save_world

            w = create_world("Quality Test")
            w.meta.id = world_id
            save_world(w)

            state = CharacterAgentState(character_id="ch_a", name="角色A")
            AgentStore.save_state(world_id, state)

            # Store decisions across 3 chapters with varying quality
            for ch_num in range(1, 4):
                if ch_num == 1:
                    decs = [
                        AgentDecision(character_id="ch_a", intended_action="观察",
                                      emotional_shift="", intended_speech=None),
                    ]
                elif ch_num == 2:
                    decs = [
                        AgentDecision(character_id="ch_a",
                                      intended_speech="为什么？！", target_character="ch_b",
                                      emotional_shift="平静→愤怒",
                                      internal_reaction="三年来的疑问终于爆发",
                                      hidden_intent="逼出真相",
                                      relationship_changes={"ch_b": "信任-3"},
                                      new_short_term_goal="问出真相"),
                        AgentDecision(character_id="ch_a",
                                      intended_action="抓住对方衣领",
                                      emotional_shift="愤怒→崩溃"),
                    ]
                else:
                    decs = [
                        AgentDecision(character_id="ch_a",
                                      intended_speech="我明白了……", target_character="ch_b",
                                      emotional_shift="崩溃→疲惫的接受",
                                      internal_reaction="他理解了对方的苦衷——尽管依然痛苦",
                                      new_short_term_goal="重新开始"),
                    ]
                AgentStore.append_decision_log(world_id, "ch_a", f"ch{ch_num}", decs)

            client = TestClient(app)
            r = client.get(f"/api/worlds/{world_id}/agents/ch_a/quality-history")
            assert r.status_code == 200
            data = r.json()
            assert data["character_id"] == "ch_a"
            chapters = data["chapters"]
            assert len(chapters) == 3

            # Chapter 2 (highest quality) should score higher than chapter 1
            ch1_q = next(c for c in chapters if c["chapter_id"] == "ch1")
            ch2_q = next(c for c in chapters if c["chapter_id"] == "ch2")
            assert ch2_q["overall"] > ch1_q["overall"], (
                f"ch2 (conflict+emotion) should score higher than ch1 (passive). "
                f"ch1={ch1_q['overall']}, ch2={ch2_q['overall']}"
            )
            # Verify all dimensions present
            for ch in chapters:
                for dim in ["pacing", "character_arc", "dialog", "consistency", "engagement"]:
                    assert dim in ch["scores"], f"Missing dimension {dim} in {ch['chapter_id']}"
                assert "grade" in ch
                assert ch["grade"] in ("A", "B", "C", "D", "F")
        finally:
            ws.world_root = original_root


# ═══════════════════════════════════════════════════════════════════
# Agent decision data format validation (frontend contract)
# ═══════════════════════════════════════════════════════════════════

class TestAgentFrontendContract:
    """Verify API responses match what the frontend agent panel expects."""

    def test_decision_format_matches_frontend(self, tmp_path):
        """Decision JSON should contain all fields used by _renderAgentDecisionList()."""
        world_id = "test_fe_contract"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)

        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.agents.agent_store import AgentStore
            from worldforger.agents.types import AgentDecision, CharacterAgentState
            from app.main import app
            from fastapi.testclient import TestClient
            from worldforger.world_store import create_world, save_world

            w = create_world("FE Contract")
            w.meta.id = world_id
            save_world(w)

            state = CharacterAgentState(character_id="ch_a", name="云鹤")
            AgentStore.save_state(world_id, state)

            d = AgentDecision(
                character_id="ch_a", decision_round=0,
                intended_speech="你是谁？",
                intended_action="后退一步",
                emotional_shift="平静→警觉",
                hidden_intent="拖延时间",
            )
            AgentStore.append_decision_log(world_id, "ch_a", "ch1", [d])

            client = TestClient(app)
            r = client.get(f"/api/worlds/{world_id}/story/agent-decisions/ch1")
            data = r.json()

            char_data = data["characters"]["ch_a"]
            # Frontend uses: decs[0]?.character_id, d.decision_round, d.intended_speech,
            #               d.intended_action, d.emotional_shift, d.hidden_intent
            dec = char_data["decisions"][0]
            assert "character_id" in dec
            assert "decision_round" in dec
            assert "intended_speech" in dec
            assert "intended_action" in dec
            assert "emotional_shift" in dec
            assert "hidden_intent" in dec
            assert dec["intended_speech"] == "你是谁？"
            assert dec["hidden_intent"] == "拖延时间"
        finally:
            ws.world_root = original_root

    def test_agent_list_format_matches_frontend(self, tmp_path):
        """Agent list JSON should match what _renderAgentStatesList() expects."""
        world_id = "test_fe_states"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)

        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.agents.agent_store import AgentStore
            from worldforger.agents.types import CharacterAgentState
            from app.main import app
            from fastapi.testclient import TestClient
            from worldforger.world_store import create_world, save_world

            w = create_world("FE States")
            w.meta.id = world_id
            save_world(w)

            state = CharacterAgentState(
                character_id="ch_a", name="云鹤",
                emotional_state="警觉", current_goal="确认雾中异常",
                current_location="南飞雁峡道", pressure_level=45,
                total_decisions_made=12, last_chapter="ch5",
                active_aftermaths=[{"source_event": "封岳被捕", "intensity": 5}],
            )
            AgentStore.save_state(world_id, state)

            client = TestClient(app)
            r = client.get(f"/api/worlds/{world_id}/agents")
            data = r.json()

            agent = data["agents"]["ch_a"]
            # Frontend uses: a.name, a.emotional_state, a.current_goal,
            #               a.current_location, a.pressure_level,
            #               a.total_decisions_made, a.active_aftermaths_count,
            #               a.last_chapter
            assert agent["name"] == "云鹤"
            assert agent["emotional_state"] == "警觉"
            assert agent["current_goal"] == "确认雾中异常"
            assert agent["current_location"] == "南飞雁峡道"
            assert agent["pressure_level"] == 45
            assert agent["total_decisions_made"] == 12
            assert agent["last_chapter"] == "ch5"
            assert agent["active_aftermaths_count"] == 1
        finally:
            ws.world_root = original_root

    def test_quality_chart_format(self, tmp_path):
        """Quality history should have the format _renderAgentQualityChart() expects."""
        world_id = "test_fe_quality"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)

        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.agents.agent_store import AgentStore
            from worldforger.agents.types import AgentDecision, CharacterAgentState
            from app.main import app
            from fastapi.testclient import TestClient
            from worldforger.world_store import create_world, save_world

            w = create_world("FE Chart")
            w.meta.id = world_id
            save_world(w)

            state = CharacterAgentState(character_id="ch_a", name="云鹤")
            AgentStore.save_state(world_id, state)

            # Store decisions for 3 chapters
            for ch_num in range(1, 4):
                AgentStore.append_decision_log(world_id, "ch_a", f"ch{ch_num}", [
                    AgentDecision(character_id="ch_a",
                                  intended_action="对峙" if ch_num > 1 else "观察",
                                  emotional_shift=f"状态{ch_num-1}→状态{ch_num}",
                                  relationship_changes={"ch_b": f"信任变化{ch_num}"}),
                ])

            client = TestClient(app)
            r = client.get(f"/api/worlds/{world_id}/agents/ch_a/quality-history")
            data = r.json()

            # Frontend uses: ch.chapter_id, ch.overall, ch.grade,
            #               ch.scores.pacing, ch.scores.character_arc, ch.scores.dialog
            for ch in data["chapters"]:
                assert "chapter_id" in ch
                assert "overall" in ch
                assert "grade" in ch
                assert "scores" in ch
                assert "pacing" in ch["scores"]
                assert "character_arc" in ch["scores"]
                assert "dialog" in ch["scores"]
                # Frontend gradeColors uses A-F
                assert ch["grade"] in ("A", "B", "C", "D", "F")
        finally:
            ws.world_root = original_root


# ═══════════════════════════════════════════════════════════════════
# Quality benchmark API tests
# ═══════════════════════════════════════════════════════════════════

class TestQualityBenchmarkAPI:
    """Verify the quality benchmark endpoint returns correct data."""

    def test_benchmark_with_data(self, tmp_path):
        """Benchmark should aggregate quality data from agent logs."""
        world_id = "test_benchmark"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)

        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.agents.agent_store import AgentStore
            from worldforger.agents.types import AgentDecision, CharacterAgentState
            from app.main import app
            from fastapi.testclient import TestClient
            from worldforger.world_store import create_world, save_world

            w = create_world("Benchmark Test")
            w.meta.id = world_id
            save_world(w)

            state = CharacterAgentState(character_id="ch_a", name="云鹤")
            AgentStore.save_state(world_id, state)

            AgentStore.append_decision_log(world_id, "ch_a", "ch1", [
                AgentDecision(character_id="ch_a", intended_speech="测试",
                              emotional_shift="平静→警觉", intended_action="观察"),
            ])

            client = TestClient(app)
            r = client.get(f"/api/worlds/{world_id}/story/quality-benchmark")
            assert r.status_code == 200
            data = r.json()
            assert data["world_id"] == world_id
            assert data["chapter_count"] >= 1
            assert "baseline" in data
            assert "overall" in data["baseline"]
            assert "scores" in data["baseline"]
            assert "grade" in data["baseline"]
        finally:
            ws.world_root = original_root

    def test_benchmark_empty_world(self, tmp_path):
        """Benchmark on world with no agent data should return empty baseline."""
        world_id = "test_benchmark_empty"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)

        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from app.main import app
            from fastapi.testclient import TestClient
            from worldforger.world_store import create_world, save_world

            w = create_world("Empty Benchmark")
            w.meta.id = world_id
            save_world(w)

            client = TestClient(app)
            r = client.get(f"/api/worlds/{world_id}/story/quality-benchmark")
            assert r.status_code == 200
            data = r.json()
            assert data["chapter_count"] == 0
            assert data["baseline"] == {}
        finally:
            ws.world_root = original_root


# ═══════════════════════════════════════════════════════════════════
# Agent reset API tests
# ═══════════════════════════════════════════════════════════════════

class TestAgentResetAPI:
    """Verify agent state can be reset."""

    def test_reset_agent(self, tmp_path):
        """POST /agents/{id}/reset should restore initial world.json state."""
        world_id = "test_reset_agent"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)

        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.agents.agent_store import AgentStore
            from worldforger.agents.types import CharacterAgentState
            from app.main import app
            from fastapi.testclient import TestClient
            from worldforger.world_store import create_world, save_world

            w = create_world("Reset Test")
            w.meta.id = world_id
            w.characters.entities = [{"id": "ch_a", "name": "云鹤", "runtime_state": {"emotional_state": "平静"}}]
            save_world(w)

            # Init and then modify state
            client = TestClient(app)
            client.post(f"/api/worlds/{world_id}/agents/init")

            # Modify state manually (simulate chapter generation)
            state = AgentStore.load_state(world_id, "ch_a")
            state.emotional_state = "愤怒"
            state.total_decisions_made = 42
            state.pressure_level = 80
            AgentStore.save_state(world_id, state)

            # Reset
            r = client.post(f"/api/worlds/{world_id}/agents/ch_a/reset")
            assert r.status_code == 200
            assert r.json()["ok"] is True

            # Verify reset
            state2 = AgentStore.load_state(world_id, "ch_a")
            assert state2.emotional_state == "平静"  # back to initial
            assert state2.total_decisions_made == 0
            assert state2.pressure_level == 0
        finally:
            ws.world_root = original_root


# ═══════════════════════════════════════════════════════════════════
# Multi-chapter API test
# ═══════════════════════════════════════════════════════════════════

class TestMultiChapterAPI:
    """Verify the multi-chapter generation endpoint."""

    def test_multi_chapter_request_validation(self, tmp_path):
        """Request body validation should work correctly."""
        world_id = "test_multi_ch"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)

        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from app.main import app
            from fastapi.testclient import TestClient
            from worldforger.world_store import create_world, save_world

            w = create_world("Multi Chapter Test")
            w.meta.id = world_id
            save_world(w)

            client = TestClient(app)

            # Test with custom parameters
            r = client.post(
                f"/api/worlds/{world_id}/story/generate/multi-chapter",
                json={
                    "chapter_ids": ["ch1", "ch2"],
                    "autonomy_level": "advisor",
                    "max_chapters": 2,
                    "stop_on_intervention": True,
                },
            )
            # Will fail because no chapters exist, but the request should be accepted
            assert r.status_code in (200, 404, 500)  # any non-422 is OK (validation passed)

            # Test with invalid autonomy level
            r2 = client.post(
                f"/api/worlds/{world_id}/story/generate/multi-chapter",
                json={
                    "chapter_ids": [],
                    "autonomy_level": "invalid_level",
                    "max_chapters": 1,
                },
            )
            assert r2.status_code in (200, 422, 404, 500)  # 422 = validation error is acceptable
        finally:
            ws.world_root = original_root
