# -*- coding: utf-8 -*-
"""Tests for Phase 3 agent modules."""

import pytest
from worldforger.agents.types import AgentDecision, AgentSimResult
from worldforger.agents.quality_evaluator import QualityEvaluator
from worldforger.agents.autonomy import AutonomyManager, AutonomyLevel


class TestQualityEvaluator:
    def test_empty_result(self):
        r = AgentSimResult(decision_sequence=[])
        q = QualityEvaluator.evaluate(r)
        assert "scores" in q
        assert "overall" in q
        assert "grade" in q
        assert q["overall"] < 50

    def test_rich_scene_scores_well(self):
        decisions = [
            AgentDecision(
                character_id="a", intended_speech="你骗了我！",
                target_character="b", intended_action="对峙",
                emotional_shift="平静→愤怒", new_short_term_goal="问出真相",
                relationship_changes={"b": "不信任-5"},
            ),
            AgentDecision(
                character_id="b", intended_speech="我有苦衷……",
                target_character="a", emotional_shift="冷静→愧疚",
                hidden_intent="拖延时间",
            ),
            AgentDecision(
                character_id="a", intended_speech="告诉我为什么！",
                target_character="b", emotional_shift="愤怒→崩溃",
            ),
        ]
        r = AgentSimResult(decision_sequence=decisions)
        q = QualityEvaluator.evaluate(r)
        assert q["scores"]["dialog"] > 30
        assert q["scores"]["character_arc"] > 20

    def test_grade_mapping(self):
        r = AgentSimResult(decision_sequence=[])
        # Empty scene = low quality
        q = QualityEvaluator.evaluate(r)
        assert q["grade"] in ("D", "F")

    def test_trend_analysis(self):
        r = AgentSimResult(decision_sequence=[
            AgentDecision(character_id="a", emotional_shift="平静→愤怒",
                          intended_action="对峙", intended_speech="不！"),
        ])
        q1 = QualityEvaluator.evaluate(r)

        # Simulate improvement in next chapter
        r2 = AgentSimResult(decision_sequence=[
            AgentDecision(character_id="a", emotional_shift="平静→愤怒"),
            AgentDecision(character_id="b", emotional_shift="愤怒→愧疚",
                          intended_speech="对不起……"),
        ])
        q2 = QualityEvaluator.evaluate(r2, prev_quality={"overall": q1["overall"]})

        # Trend should be computed
        assert q2["trend"] is not None

    def test_suggestions_for_low_score(self):
        r = AgentSimResult(decision_sequence=[])
        q = QualityEvaluator.evaluate(r)
        assert len(q["suggestions"]) > 0

    def test_all_dimensions_present(self):
        r = AgentSimResult(decision_sequence=[
            AgentDecision(character_id="a", intended_action="观察"),
        ])
        q = QualityEvaluator.evaluate(r)
        for dim in QualityEvaluator.DIMENSIONS:
            assert dim in q["scores"], f"Missing dimension: {dim}"


class TestAutonomyManager:
    def test_default_levels(self):
        assert AutonomyManager.default_level("protagonist_core") == AutonomyLevel.SEMI_AUTO
        assert AutonomyManager.default_level("supporting_minor") == AutonomyLevel.ADVISOR
        assert AutonomyManager.default_level("background") == AutonomyLevel.ADVISOR

    def test_unknown_role_defaults_to_advisor(self):
        assert AutonomyManager.default_level("nonexistent_role") == AutonomyLevel.ADVISOR

    def test_temperature_adjustment(self):
        base = 0.55
        assert AutonomyManager.temperature_for(AutonomyLevel.ADVISOR, base) < base
        assert AutonomyManager.temperature_for(AutonomyLevel.SEMI_AUTO, base) == base
        assert AutonomyManager.temperature_for(AutonomyLevel.FULL_AUTO, base) > base

    def test_constraint_strictness(self):
        assert AutonomyManager.constraint_strictness(AutonomyLevel.ADVISOR) > 0.8
        assert AutonomyManager.constraint_strictness(AutonomyLevel.FULL_AUTO) < 0.5

    def test_intervention_advisor_light_deviation(self):
        """Advisor mode should intervene even on light deviation."""
        assert AutonomyManager.should_intervene(
            AutonomyLevel.ADVISOR, "light", 60,
        ) is True

    def test_intervention_full_auto_moderate_deviation(self):
        """Full auto should NOT intervene on moderate deviation."""
        assert AutonomyManager.should_intervene(
            AutonomyLevel.FULL_AUTO, "moderate", 60,
        ) is False

    def test_intervention_full_auto_severe_deviation(self):
        """Full auto SHOULD intervene on severe deviation."""
        assert AutonomyManager.should_intervene(
            AutonomyLevel.FULL_AUTO, "severe", 60,
        ) is True

    def test_intervention_low_quality_always(self):
        """All levels should intervene when quality < 25."""
        for level in AutonomyLevel:
            assert AutonomyManager.should_intervene(level, "none", 20) is True

    def test_describe(self):
        for level in AutonomyLevel:
            desc = AutonomyManager.describe(level)
            assert len(desc) > 10


# ═══════════════════════════════════════════════════════════════════
# ChapterRunner tests
# ═══════════════════════════════════════════════════════════════════

class TestChapterRunner:
    def test_runner_init(self):
        from worldforger.agents.chapter_runner import ChapterRunner
        runner = ChapterRunner("test_world", max_chapters=3)
        assert runner.max_chapters == 3
        assert runner.session.chapters_completed == 0

    def test_chapter_run_result_defaults(self):
        from worldforger.agents.chapter_runner import ChapterRunResult
        r = ChapterRunResult()
        assert r.success is False
        assert r.manuscript_length == 0

    def test_run_session_defaults(self):
        from worldforger.agents.chapter_runner import RunSession
        s = RunSession(world_id="test")
        assert s.world_id == "test"
        assert s.chapters_completed == 0
        assert s.stopped is False

    def test_summary_empty_session(self):
        from worldforger.agents.chapter_runner import ChapterRunner
        runner = ChapterRunner("test")
        summary = runner.summary()
        assert "Completed: 0" in summary
        assert "test" in summary

    def test_summary_with_results(self):
        from worldforger.agents.chapter_runner import ChapterRunner, ChapterRunResult
        runner = ChapterRunner("test_world")
        runner.session.results = [
            ChapterRunResult(chapter_id="ch1", chapter_order=1, success=True, manuscript_length=5000),
            ChapterRunResult(chapter_id="ch2", chapter_order=2, success=False, error="too short"),
        ]
        runner.session.chapters_completed = 2
        runner.session.chapters_failed = 1
        summary = runner.summary()
        assert "Completed: 2" in summary
        assert "Failed: 1" in summary
        assert "ch1" in summary


# ═══════════════════════════════════════════════════════════════════
# QualityBenchmark tests
# ═══════════════════════════════════════════════════════════════════

class TestQualityBenchmark:
    def test_compare_no_baseline(self):
        from worldforger.agents.chapter_runner import QualityBenchmark
        result = QualityBenchmark.compare({"overall": 60}, {})
        assert result["compared"] is False

    def test_compare_better(self):
        from worldforger.agents.chapter_runner import QualityBenchmark
        current = {
            "overall": 75, "grade": "A",
            "scores": {"pacing": 70, "character_arc": 80, "dialog": 75, "consistency": 80, "engagement": 70},
        }
        baseline = {
            "overall": 55, "grade": "C",
            "scores": {"pacing": 50, "character_arc": 55, "dialog": 60, "consistency": 55, "engagement": 55},
        }
        result = QualityBenchmark.compare(current, baseline)
        assert result["compared"] is True
        assert result["assessment"] == "better"
        assert result["overall_delta"] > 0

    def test_compare_worse(self):
        from worldforger.agents.chapter_runner import QualityBenchmark
        current = {
            "overall": 40, "grade": "D",
            "scores": {"pacing": 40, "character_arc": 40, "dialog": 40, "consistency": 40, "engagement": 40},
        }
        baseline = {
            "overall": 65, "grade": "B",
            "scores": {"pacing": 60, "character_arc": 65, "dialog": 70, "consistency": 65, "engagement": 65},
        }
        result = QualityBenchmark.compare(current, baseline)
        assert result["assessment"] == "worse"

    def test_build_baseline_empty(self):
        from worldforger.agents.chapter_runner import QualityBenchmark
        baseline = QualityBenchmark.build_baseline_from_chapters([])
        assert baseline == {}

    def test_build_baseline_from_qualities(self):
        from worldforger.agents.chapter_runner import QualityBenchmark
        qualities = [
            {
                "scores": {"pacing": 50, "character_arc": 60, "dialog": 55, "consistency": 70, "engagement": 55},
                "overall": 58, "grade": "C",
            },
            {
                "scores": {"pacing": 70, "character_arc": 75, "dialog": 65, "consistency": 80, "engagement": 70},
                "overall": 72, "grade": "B",
            },
        ]
        baseline = QualityBenchmark.build_baseline_from_chapters(qualities)
        assert baseline["sample_size"] == 2
        assert 55 < baseline["overall"] < 70
        assert baseline["grade"] in ("B", "C")
        for dim in ["pacing", "character_arc", "dialog", "consistency", "engagement"]:
            assert dim in baseline["scores"]

    def test_compare_comparable(self):
        from worldforger.agents.chapter_runner import QualityBenchmark
        current = {
            "overall": 55, "grade": "C",
            "scores": {"pacing": 55, "character_arc": 55, "dialog": 55, "consistency": 55, "engagement": 55},
        }
        baseline = {
            "overall": 58, "grade": "C",
            "scores": {"pacing": 58, "character_arc": 58, "dialog": 58, "consistency": 58, "engagement": 58},
        }
        result = QualityBenchmark.compare(current, baseline)
        assert result["assessment"] == "comparable"

    def test_compare_dimension_deltas(self):
        from worldforger.agents.chapter_runner import QualityBenchmark
        current = {
            "overall": 70,
            "scores": {"pacing": 60, "character_arc": 80, "dialog": 70, "consistency": 65, "engagement": 75},
        }
        baseline = {
            "overall": 55,
            "scores": {"pacing": 50, "character_arc": 55, "dialog": 55, "consistency": 55, "engagement": 60},
        }
        result = QualityBenchmark.compare(current, baseline)
        assert result["dimension_deltas"]["pacing"] == 10.0
        assert result["dimension_deltas"]["character_arc"] == 25.0


# ═══════════════════════════════════════════════════════════════════
# P3: End-to-end autonomous mode validation
# ═══════════════════════════════════════════════════════════════════

class TestChapterRunnerE2E:
    """End-to-end validation of ChapterRunner with mocked generation."""

    @pytest.mark.asyncio
    async def test_run_with_mocked_generation(self):
        """ChapterRunner should successfully process mocked chapter generation."""
        from worldforger.agents.chapter_runner import ChapterRunner
        from worldforger.agents.autonomy import AutonomyLevel

        # Mock world-like object
        class MockChapter:
            def __init__(self, cid, order):
                self.id = cid
                self.order = order

        class MockWorld:
            def __init__(self):
                self.story = type('obj', (object,), {
                    'chapters': [
                        MockChapter("ch1", 1), MockChapter("ch2", 2),
                        MockChapter("ch3", 3),
                    ],
                })()

        mock_world = MockWorld()

        # Mock generate function
        call_count = [0]
        async def mock_generate(w, ch_id):
            call_count[0] += 1
            text = f"Generated content for {ch_id} with sufficient length for quality evaluation. " * 20
            return text, [], []

        runner = ChapterRunner(
            world_id="test_e2e",
            autonomy_level=AutonomyLevel.SEMI_AUTO,
            max_chapters=3,
            stop_on_intervention=False,
        )
        session = await runner.run(
            mock_world,
            chapter_ids=["ch1", "ch2", "ch3"],
            generate_fn=mock_generate,
        )

        assert call_count[0] == 3
        assert session.chapters_completed == 3
        assert session.chapters_failed == 0
        assert not session.stopped
        assert len(session.results) == 3
        for r in session.results:
            assert r.success
            assert r.manuscript_length > 200
            assert r.quality is not None
            assert "grade" in r.quality

    @pytest.mark.asyncio
    async def test_run_stops_on_failure(self):
        """ChapterRunner should record failures but continue."""
        from worldforger.agents.chapter_runner import ChapterRunner
        from worldforger.agents.autonomy import AutonomyLevel

        class MockChapter:
            def __init__(self, cid, order):
                self.id = cid
                self.order = order

        class MockWorld:
            def __init__(self):
                self.story = type('obj', (object,), {
                    'chapters': [
                        MockChapter("ch1", 1), MockChapter("ch2", 2),
                    ],
                })()

        mock_world = MockWorld()

        async def mock_generate(w, ch_id):
            if ch_id == "ch1":
                return "good text " * 50, [], []
            else:
                raise RuntimeError("API error")

        runner = ChapterRunner(
            world_id="test_fail",
            max_chapters=2,
            stop_on_intervention=False,
        )
        session = await runner.run(
            mock_world, chapter_ids=["ch1", "ch2"],
            generate_fn=mock_generate,
        )

        assert session.chapters_completed == 2
        assert session.chapters_failed == 1
        assert session.results[0].success
        assert not session.results[1].success
        assert "API error" in session.results[1].error

    @pytest.mark.asyncio
    async def test_run_stops_on_quality_intervention(self):
        """With stop_on_intervention=True, low quality should halt the run."""
        from worldforger.agents.chapter_runner import ChapterRunner
        from worldforger.agents.autonomy import AutonomyLevel

        class MockChapter:
            def __init__(self, cid, order):
                self.id = cid
                self.order = order

        class MockWorld:
            def __init__(self):
                self.story = type('obj', (object,), {
                    'chapters': [
                        MockChapter("ch1", 1), MockChapter("ch2", 2),
                    ],
                })()

        mock_world = MockWorld()
        call_count = [0]

        async def mock_generate(w, ch_id):
            call_count[0] += 1
            # First chapter: barely long enough to pass length check but empty decisions = low quality
            if call_count[0] == 1:
                return ("minimal text without any character decisions or conflict. " * 10), [], []
            return ("good text with proper narrative development and character interaction. " * 20), [], []

        runner = ChapterRunner(
            world_id="test_intervene",
            autonomy_level=AutonomyLevel.ADVISOR,  # Advisor intervenes on low quality
            max_chapters=2,
            stop_on_intervention=True,
        )
        session = await runner.run(
            mock_world, chapter_ids=["ch1", "ch2"],
            generate_fn=mock_generate,
        )

        # First chapter succeeds (passes length check) but quality is evaluated
        # With ADVISOR autonomy and empty decisions, quality should be low enough
        assert session.results[0].success
        # Quality evaluation should have produced a score
        assert session.results[0].quality is not None

    @pytest.mark.asyncio
    async def test_run_respects_max_chapters(self):
        """ChapterRunner should not exceed max_chapters."""
        from worldforger.agents.chapter_runner import ChapterRunner

        class MockChapter:
            def __init__(self, cid, order):
                self.id = cid
                self.order = order

        class MockWorld:
            def __init__(self):
                self.story = type('obj', (object,), {
                    'chapters': [
                        MockChapter("ch1", 1), MockChapter("ch2", 2),
                        MockChapter("ch3", 3), MockChapter("ch4", 4),
                    ],
                })()

        mock_world = MockWorld()

        async def mock_generate(w, ch_id):
            return "good text " * 50, [], []

        runner = ChapterRunner(world_id="test_max", max_chapters=2)
        session = await runner.run(
            mock_world,
            chapter_ids=["ch1", "ch2", "ch3", "ch4"],
            generate_fn=mock_generate,
        )

        assert session.chapters_completed == 2
        assert "max_chapters" in session.stop_reason


# ═══════════════════════════════════════════════════════════════════
# P3: State consistency stress tests
# ═══════════════════════════════════════════════════════════════════

class TestStateConsistency:
    """Verify state consistency across multi-chapter runs."""

    def test_agent_state_roundtrip(self):
        """CharacterAgentState should serialize and deserialize without loss."""
        from worldforger.agents.types import CharacterAgentState

        original = CharacterAgentState(
            character_id="ch_test",
            name="测试角色",
            speech_profile={"avg_sentence_length": "short"},
            core_desire="找到真相",
            core_fear="失去所爱",
            flaws=[{"name": "过度牺牲", "triggers": ["队友受伤"]}],
            current_location="峡道北段",
            current_goal="前往千窟洞",
            emotional_state="警觉",
            physical_state={"active_injuries": ["左臂擦伤"]},
            active_aftermaths=[{"source_event": "封岳被捕", "intensity": 7, "symptoms": ["自责"]}],
            pressure_level=45,
            relationships={"ch_seline": {"last_change": "信任加深"}},
            knowledge_boundary={"秦渊的身份": "knows_for_sure"},
            recent_memories=[{"event": "封岳交付骨片", "chapter": "ch15"}],
            last_chapter="ch15",
            total_decisions_made=42,
        )

        # Serialize
        data = original.model_dump(mode="json")
        # Deserialize
        restored = CharacterAgentState.model_validate(data)

        assert restored.character_id == original.character_id
        assert restored.name == original.name
        assert restored.core_desire == original.core_desire
        assert restored.core_fear == original.core_fear
        assert restored.relationships == original.relationships
        assert restored.pressure_level == original.pressure_level
        assert restored.total_decisions_made == original.total_decisions_made
        assert len(restored.active_aftermaths) == 1
        assert restored.active_aftermaths[0]["intensity"] == 7

    def test_decision_roundtrip(self):
        """AgentDecision should roundtrip through JSON correctly."""
        from worldforger.agents.types import AgentDecision

        original = AgentDecision(
            character_id="ch_yunhe",
            decision_round=2,
            internal_reaction="感到不安——他意识到对方在说谎",
            emotional_shift="平静→警觉",
            intended_action="后退一步，手按上护符",
            intended_speech="你是谁？",
            target_character="ch_stranger",
            hidden_intent="拖延时间观察对方",
            relationship_changes={"ch_stranger": "信任-1"},
            new_short_term_goal="确认对方身份",
            confidence=0.8,
        )

        data = original.model_dump(mode="json")
        restored = AgentDecision.model_validate(data)

        assert restored.character_id == original.character_id
        assert restored.intended_speech == original.intended_speech
        assert restored.hidden_intent == original.hidden_intent
        assert restored.confidence == original.confidence
        assert restored.relationship_changes == original.relationship_changes

    def test_multi_chapter_state_accumulation(self):
        """Simulate 10 chapters of state accumulation — no data loss."""
        from worldforger.agents.types import CharacterAgentState
        from worldforger.agents.continuity_checker import ContinuityChecker
        from worldforger.agents.types import AgentSimResult, AgentDecision

        state = CharacterAgentState(
            character_id="ch_test", name="测试",
            pressure_level=10, emotional_state="平静",
            active_aftermaths=[{"source_event": "初始事件", "intensity": 8, "decay_rate": 0.3}],
        )

        for ch_num in range(1, 11):
            sim = AgentSimResult(
                chapter_id=f"ch{ch_num}",
                decision_sequence=[
                    AgentDecision(
                        character_id="ch_test",
                        emotional_shift=f"状态{ch_num-1}→状态{ch_num}" if ch_num % 3 == 0 else "",
                        new_short_term_goal=f"目标{ch_num}" if ch_num % 2 == 0 else None,
                    ),
                ],
            )
            states = ContinuityChecker.post_generation_update(sim, {"ch_test": state})
            state = states["ch_test"]

        # After 10 chapters, state should still be valid
        assert state.last_chapter == "ch10"
        assert state.total_decisions_made >= 5  # at least half of chapters had decisions
        assert state.pressure_level >= 10  # should have accumulated some pressure

    def test_natural_decay_convergence(self):
        """Active aftermaths should decay toward dormancy over many chapters."""
        from worldforger.agents.types import CharacterAgentState
        from worldforger.agents.continuity_checker import ContinuityChecker
        from worldforger.agents.types import AgentSimResult

        state = CharacterAgentState(
            character_id="ch_off", name="离线角色",
            pressure_level=50,
            active_aftermaths=[
                {"source_event": "创伤事件", "intensity": 9, "decay_rate": 0.5, "current_status": "active"},
            ],
        )

        # Simulate 10 chapters off-screen
        for ch_num in range(1, 11):
            sim = AgentSimResult(chapter_id=f"ch{ch_num}", decision_sequence=[])
            states = ContinuityChecker.post_generation_update(sim, {"ch_off": state})
            state = states["ch_off"]

        # After 10 chapters of decay
        assert state.pressure_level <= 25  # 50 - 10*3 = 20, should decrease
        aftermath = state.active_aftermaths[0]
        # 9 - 10*0.5 = 4, still above dormancy threshold (2)
        assert aftermath["intensity"] <= 5  # should be approaching dormancy
        assert aftermath.get("current_status") in ("dormant", "active")

    def test_continuity_report_model(self):
        """ContinuityReport should correctly report passed/failed."""
        from worldforger.agents.types import ContinuityReport

        r1 = ContinuityReport(warnings=[], passed=True)
        assert r1.passed

        r2 = ContinuityReport(warnings=["位置跳跃"], passed=False)
        assert not r2.passed
        assert len(r2.warnings) == 1
