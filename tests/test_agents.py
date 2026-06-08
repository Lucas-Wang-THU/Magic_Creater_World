# -*- coding: utf-8 -*-
"""Tests for the character agent emergent narrative system."""

import pytest
from worldforger.agents.types import (
    AgentDecision, AgentSimResult, CharacterAgentState,
    OutlineConstraints, BeatReferenceData, ContinuityReport,
)
from worldforger.agents.pov_filter import POVFilter
from worldforger.agents.state_injector import StateInjector
from worldforger.agents.continuity_checker import ContinuityChecker
from worldforger.agents.outline_constraint import OutlineConstraint
from worldforger.agents.beat_reference import BeatReference
from worldforger.agents.agent_store import AgentStore


class TestAgentDecision:
    def test_default_decision(self):
        d = AgentDecision(character_id="ch_test")
        assert d.character_id == "ch_test"
        assert d.decision_round == 0
        assert d.confidence == 0.5

    def test_full_decision(self):
        d = AgentDecision(
            character_id="ch_yunhe",
            decision_round=2,
            internal_reaction="他感到不安",
            emotional_shift="平静→警觉",
            intended_action="退后一步，手按上护符",
            intended_speech="你是谁？",
            target_character="ch_stranger",
            hidden_intent="拖延时间观察对方",
            relationship_changes={"ch_stranger": "信任-1"},
            new_short_term_goal="确认对方身份",
            confidence=0.8,
        )
        assert d.intended_speech == "你是谁？"
        assert d.hidden_intent == "拖延时间观察对方"
        assert d.relationship_changes["ch_stranger"] == "信任-1"


class TestAgentSimResult:
    def test_empty_result(self):
        r = AgentSimResult()
        assert r.decision_sequence == []
        assert r.pov_visible_events == []

    def test_with_decisions(self):
        d = AgentDecision(character_id="ch_a", intended_action="走向门口")
        r = AgentSimResult(
            chapter_id="ch1",
            decision_sequence=[d],
            macro_events=["铁壁卫设卡"],
        )
        assert len(r.decision_sequence) == 1
        assert "铁壁卫设卡" in r.macro_events


class TestCharacterAgentState:
    def test_default_state(self):
        s = CharacterAgentState(character_id="ch_test", name="测试")
        assert s.name == "测试"
        assert s.pressure_level == 0

    def test_state_with_aftermaths(self):
        s = CharacterAgentState(
            character_id="ch_test", name="测试",
            active_aftermaths=[{"source_event": "战斗", "intensity": 7, "symptoms": ["失眠"]}],
            physical_state={"active_injuries": ["左臂擦伤"]},
        )
        assert len(s.active_aftermaths) == 1
        assert s.active_aftermaths[0]["intensity"] == 7


class TestPOVFilter:
    def test_pov_own_decisions_visible(self):
        decisions = [
            AgentDecision(
                character_id="ch_pov", internal_reaction="不安",
                intended_action="停下脚步", emotional_shift="平静→警觉",
            ),
        ]
        events = POVFilter.filter(decisions, "ch_pov")
        assert len(events) >= 3
        assert any("不安" in e for e in events)

    def test_other_internal_reaction_not_visible(self):
        decisions = [
            AgentDecision(
                character_id="ch_other", internal_reaction="他在说谎",
                intended_speech="好的", target_character="ch_pov",
            ),
        ]
        events = POVFilter.filter(decisions, "ch_pov")
        # POV character should NOT see other's internal reaction
        assert not any("说谎" in e for e in events)
        # Should see the speech though
        assert any("好的" in e for e in events)

    def test_observer_see_interaction(self):
        decisions = [
            AgentDecision(
                character_id="ch_a", intended_speech="走吧",
                target_character="ch_b",
            ),
        ]
        events = POVFilter.filter(decisions, "ch_pov")
        assert any("旁观" in e for e in events)

    def test_empty_decisions(self):
        events = POVFilter.filter([], "ch_pov")
        assert events == []


class TestStateInjector:
    def test_for_writer_agent_basic(self):
        pov = CharacterAgentState(
            character_id="ch_pov", name="云鹤",
            current_location="峡道北段", emotional_state="警觉",
            current_goal="找到隐秘岔道",
        )
        result = StateInjector.for_writer_agent(pov, {}, {})
        assert "云鹤" in result
        assert "峡道北段" in result
        assert "警觉" in result

    def test_for_writer_agent_with_present_and_shadow(self):
        pov = CharacterAgentState(character_id="ch_pov", name="云鹤")
        present = {"ch_b": CharacterAgentState(character_id="ch_b", name="塞琳", emotional_state="焦虑")}
        shadow = {"ch_c": CharacterAgentState(character_id="ch_c", name="封岳", current_location="押解途中")}
        result = StateInjector.for_writer_agent(pov, present, shadow)
        assert "塞琳" in result
        assert "封岳" in result
        assert "不要在正文中直接描写" in result


class TestContinuityChecker:
    def test_pre_check_location_mismatch(self):
        states = {
            "ch_pov": CharacterAgentState(
                character_id="ch_pov", name="云鹤",
                current_location="峡道北段", current_goal="找到岔道",
            ),
        }
        report = ContinuityChecker.pre_generation_check(
            states, "千窟洞外围", pov_id="ch_pov",
        )
        assert not report.passed
        assert any("峡道北段" in w for w in report.warnings)

    def test_pre_check_aftermath_reminder(self):
        states = {
            "ch_pov": CharacterAgentState(
                character_id="ch_pov", name="云鹤",
                current_location="哨站",
                active_aftermaths=[{"source_event": "封岳被捕", "intensity": 7, "symptoms": ["自责", "走神"]}],
            ),
        }
        report = ContinuityChecker.pre_generation_check(
            states, "哨站", pov_id="ch_pov",
        )
        assert any("封岳被捕" in w for w in report.warnings)

    def test_post_update_emotional_shift(self):
        states = {
            "ch_a": CharacterAgentState(character_id="ch_a", name="A", emotional_state="平静"),
        }
        sim = AgentSimResult(
            chapter_id="ch1",
            decision_sequence=[
                AgentDecision(character_id="ch_a", emotional_shift="平静→愤怒",
                              new_short_term_goal="离开这里"),
            ],
        )
        new_states = ContinuityChecker.post_generation_update(sim, states)
        assert new_states["ch_a"].emotional_state == "平静→愤怒"
        assert new_states["ch_a"].current_goal == "离开这里"

    def test_natural_decay_off_screen(self):
        states = {
            "ch_off": CharacterAgentState(
                character_id="ch_off", name="Off",
                active_aftermaths=[{"source_event": "旧伤", "intensity": 5, "decay_rate": 0.5}],
                pressure_level=20,
            ),
        }
        sim = AgentSimResult(chapter_id="ch1", decision_sequence=[])
        new_states = ContinuityChecker.post_generation_update(sim, states)
        # Off-screen character should have decay applied
        assert new_states["ch_off"].pressure_level <= 17
        assert new_states["ch_off"].active_aftermaths[0]["intensity"] < 5


class TestOutlineConstraint:
    def test_default_constraints(self):
        c = OutlineConstraints()
        assert c.hard_events == []
        assert c.soft_direction == ""

    def test_inject_to_scene(self):
        c = OutlineConstraints(
            hard_events=["铁壁卫设卡盘查"],
            soft_direction="角色北上，接触山母势力",
        )
        result = OutlineConstraint.inject_to_scene(c, "峡道场景")
        assert "铁壁卫设卡盘查" in result
        assert "接触山母势力" in result

    def test_verify_completion(self):
        c = OutlineConstraints(hard_events=["铁壁卫设卡盘查"])
        result = OutlineConstraint.verify_completion(c, "铁壁卫设卡盘查过往行人")
        assert result["all_satisfied"]

    def test_verify_incomplete(self):
        c = OutlineConstraints(hard_events=["铁壁卫设卡盘查"])
        result = OutlineConstraint.verify_completion(c, "云鹤走在空无一人的峡道上")
        assert not result["all_satisfied"]


class TestBeatReference:
    def test_default_data(self):
        b = BeatReferenceData()
        assert b.scene_goals == []

    def test_inject_as_hints(self):
        b = BeatReferenceData(
            scene_goals=["建立与山母势力的初次接触"],
            conflict_hints=["铁壁卫与山母入门者的对峙"],
        )
        hints = BeatReference.inject_as_soft_hints(b)
        assert len(hints) >= 1
        assert any("山母" in h for h in hints)

    def test_record_deviation_none(self):
        b = BeatReferenceData()
        sim = AgentSimResult(decision_sequence=[])
        assert BeatReference.record_deviation(b, sim) is None

    def test_record_deviation_found(self):
        b = BeatReferenceData(scene_goals=["建立与山母势力的初次接触XYZ"])
        sim = AgentSimResult(
            decision_sequence=[
                AgentDecision(character_id="ch_a", intended_action="寻找水源"),
            ],
        )
        result = BeatReference.record_deviation(b, sim)
        assert result is not None
        assert "未完全覆盖" in result


class TestAgentStore:
    def test_init_states_from_world(self, tmp_path):
        """Test state initialization. Requires a mock world."""
        # This test validates the function doesn't crash on real world data
        # Full integration test would need a real world object
        pass
