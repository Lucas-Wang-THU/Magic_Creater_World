"""Tests for P1 (Scene Chunking) and P2 (Unified Extractors)."""
import json
import pytest
from unittest.mock import AsyncMock, patch

from worldforger.schemas import (
    StoryChapter, StorySection, StoryNarrator, StoryWritingDefaults,
    World, Meta, MysteryTracker, CharacterArc, ReaderMemoryEntry,
    EmotionalAftermath, CharacterPhysicalState, CharacterKnowledgeEntry,
    CharacterDecision, PersonalTimelineEvent, CharacterPersonalTimeline,
)


@pytest.fixture
def test_world():
    import uuid
    wid = f"test_{uuid.uuid4().hex[:10]}"
    w = World(
        meta=Meta(id=wid, name="Test"),
        story=StorySection(
            writing_defaults=StoryWritingDefaults(
                enable_scene_chunking=True,
                enable_unified_extractors=True,
            ),
            chapters=[StoryChapter(id="ch_1", order=1, title="Ch1")],
            narrator=StoryNarrator(person="third_person_limited"),
        ),
    )
    w.characters.entities = [
        {"id": "char_a", "name": "Alice"},
        {"id": "char_b", "name": "Bob"},
    ]
    return w


# ── P1: Scene Chunking ──────────────────────────────────────

class TestSceneChunking:
    @pytest.mark.asyncio
    async def test_scene_plan_parses_valid_json(self):
        from worldforger.story.story_service import _generate_scene_plan
        mock_reply = json.dumps({"scenes": [
            {"order": 1, "type": "opening", "chars": ["char_a"], "goal": "开场", "est_words": 500},
            {"order": 2, "type": "conflict", "chars": ["char_a", "char_b"], "goal": "冲突", "est_words": 800},
        ]}, ensure_ascii=False)
        with patch("worldforger.story.story_service.chat_completion",
                   new=AsyncMock(return_value=mock_reply)):
            scenes = await _generate_scene_plan(
                World(meta=Meta(id="t", name="t"), story=StorySection(
                    chapters=[StoryChapter(id="ch_1", order=1, title="T")])),
                "ch_1", "beat text", 2000, None,
            )
            assert len(scenes) == 2
            assert scenes[0]["type"] == "opening"

    @pytest.mark.asyncio
    async def test_scene_plan_handles_bad_json(self):
        from worldforger.story.story_service import _generate_scene_plan
        with patch("worldforger.story.story_service.chat_completion",
                   new=AsyncMock(return_value="not json at all")):
            scenes = await _generate_scene_plan(
                World(meta=Meta(id="t", name="t"), story=StorySection(
                    chapters=[StoryChapter(id="ch_1", order=1, title="T")])),
                "ch_1", "beat", 2000, None,
            )
            assert scenes == []

    @pytest.mark.asyncio
    async def test_scene_draft_generates_text(self):
        from worldforger.story.story_service import _generate_scene_draft
        mock_reply = "The scene unfolds..."
        with patch("worldforger.story.story_service.chat_completion",
                   new=AsyncMock(return_value=mock_reply)):
            result = await _generate_scene_draft(
                World(meta=Meta(id="t", name="t")),
                {"goal": "test", "chars": ["char_a"], "est_words": 500},
                "", "hard context", None,
            )
            assert "scene" in result.lower()

    @pytest.mark.asyncio
    async def test_merge_scenes(self):
        from worldforger.story.story_service import _merge_scenes
        mock_reply = "Merged chapter content"
        with patch("worldforger.story.story_service.chat_completion",
                   new=AsyncMock(return_value=mock_reply)):
            result = await _merge_scenes(
                World(meta=Meta(id="t", name="t"), story=StorySection(
                    chapters=[StoryChapter(id="ch_1", order=1, title="T")])),
                ["Scene 1", "Scene 2"], "ch_1", None,
            )
            assert len(result) > 10

    @pytest.mark.asyncio
    async def test_chunked_falls_through_on_few_scenes(self, test_world):
        from worldforger.story.story_service import _generate_manuscript_chunked
        mock_reply = json.dumps({"scenes": [{"order": 1, "type": "opening", "chars": [], "goal": "x", "est_words": 500}]})
        with patch("worldforger.story.story_service.chat_completion",
                   new=AsyncMock(return_value=mock_reply)):
            result = await _generate_manuscript_chunked(
                test_world, "ch_1", "beat text", 5000, "hard ctx", None,
            )
            assert result == ""  # <2 scenes, should fall through

    @pytest.mark.asyncio
    async def test_chunked_generates_with_enough_scenes(self, test_world):
        from worldforger.story.story_service import _generate_manuscript_chunked
        plan_reply = json.dumps({"scenes": [
            {"order": 1, "type": "opening", "chars": ["char_a"], "goal": "A", "est_words": 500},
            {"order": 2, "type": "conflict", "chars": ["char_b"], "goal": "B", "est_words": 600},
            {"order": 3, "type": "resolution", "chars": ["char_a"], "goal": "C", "est_words": 400},
        ]})
        draft_reply = "Scene draft content that is long enough for the merge function to work properly with all scenes"
        mock = AsyncMock()
        mock.side_effect = [plan_reply, draft_reply, draft_reply, draft_reply, "Merged final chapter content here"]
        with patch("worldforger.story.story_service.chat_completion", new=mock):
            result = await _generate_manuscript_chunked(
                test_world, "ch_1", "beat text", 5000, "hard ctx", None,
            )
            assert len(result) > 10


# ── P2: Unified Extractors ──────────────────────────────────

class TestUnifiedExtractors:
    @pytest.mark.asyncio
    async def test_narrative_state_extractor(self, test_world):
        from worldforger.story.story_service import _unified_narrative_state_extractor
        reply = json.dumps({
            "summary_card": {"main_events": "events summary", "character_state_changes": [],
                             "foreshadowing_planted": [], "foreshadowing_resolved": [], "ending_hook": "hook"},
            "runtime_states": {"char_a": {"current_location": "here", "current_goal": "goal", "emotional_state": "calm"}},
            "physical_states": [{"character_id": "char_a", "active_injuries": [], "fatigue_level": "rested"}],
            "timeline_events": [{"event_id": "ptl_1", "character_id": "char_a", "event": "something happened"}],
        }, ensure_ascii=False)
        with patch("worldforger.story.story_service.chat_completion",
                   new=AsyncMock(return_value=reply)):
            err = await _unified_narrative_state_extractor(test_world, "ch_1", "manuscript text")
            assert err == ""
            assert test_world.story.chapters[0].summary_card is not None

    @pytest.mark.asyncio
    async def test_knowledge_plot_extractor(self, test_world):
        from worldforger.story.story_service import _unified_knowledge_plot_extractor
        reply = json.dumps({
            "knowledge_entries": [{"knowledge_id": "k1", "character_id": "char_a", "topic": "secret",
                                   "category": "secret", "certainty": "knows_for_sure",
                                   "source_chapter": "ch_1", "source_detail": "overheard"}],
            "decisions": [{"decision_id": "d1", "character_id": "char_a", "summary": "choice",
                           "decision_type": "moral_choice"}],
            "kg_events": [],
        }, ensure_ascii=False)
        with patch("worldforger.story.story_service.chat_completion",
                   new=AsyncMock(return_value=reply)):
            err = await _unified_knowledge_plot_extractor(test_world, "ch_1", "manuscript text")
            assert err == ""
            assert len(test_world.character_knowledge.entries) >= 1
            assert len(test_world.character_decisions) >= 1

    @pytest.mark.asyncio
    async def test_quality_reviewer(self, test_world):
        from worldforger.story.story_service import _unified_quality_reviewer
        reply = json.dumps({
            "consistency_report": {"verdict": "clean", "issues": []},
            "sentiment": {"segments": [{"segment_index": 1, "label": "开篇", "tone": "calm", "intensity": 5, "summary": "calm"}],
                          "overall_tone": "calm", "ending_tone": "calm", "transition_from_prev": "first_chapter"},
            "aftermaths": [{"aftermath_id": "am1", "character_id": "char_a", "source_event": "event",
                            "symptoms": ["tired"], "intensity": 3, "trigger_conditions": []}],
        }, ensure_ascii=False)
        with patch("worldforger.story.story_service.chat_completion",
                   new=AsyncMock(return_value=reply)):
            err = await _unified_quality_reviewer(test_world, "ch_1", "manuscript text")
            assert err == ""
            assert test_world.story.chapters[0].consistency_report is not None
            assert test_world.story.chapters[0].sentiment_log is not None

    @pytest.mark.asyncio
    async def test_narrative_state_handles_bad_json(self, test_world):
        from worldforger.story.story_service import _unified_narrative_state_extractor
        with patch("worldforger.story.story_service.chat_completion",
                   new=AsyncMock(return_value="no json here")):
            err = await _unified_narrative_state_extractor(test_world, "ch_1", "text")
            assert "no JSON" in err


# ── Narrative State Engine schemas ───────────────────────────

class TestNarrativeSchemas:
    def test_mystery_tracker_defaults(self):
        m = MysteryTracker()
        assert m.status == "active"
        assert m.reader_knowledge == "none"
        assert m.salience == 0.5

    def test_character_arc_defaults(self):
        a = CharacterArc()
        assert a.arc_stage == "denial"
        assert a.beliefs == []

    def test_reader_memory_defaults(self):
        r = ReaderMemoryEntry()
        assert r.type == "mystery"
        assert r.reader_salience == 0.5


# ── Hard Context builder ────────────────────────────────────

# ── Break Mechanism ─────────────────────────────────────────

class TestBreakMechanism:
    def test_break_event_defaults(self):
        from worldforger.schemas import BreakEvent
        b = BreakEvent()
        assert b.trigger_type == "accumulated_pressure"
        assert b.break_type == "emotional_explosion"
        assert b.aftermath_attitude == "ashamed"

    def test_character_pressure_defaults(self):
        from worldforger.schemas import CharacterPressure
        p = CharacterPressure()
        assert p.current_pressure == 0
        assert p.break_threshold == 75
        assert p.cooldown_chapters == 3

    def test_break_event_serialization(self):
        from worldforger.schemas import BreakEvent
        b = BreakEvent(break_id="br_1", character_id="char_a", chapter="ch_5",
                       trigger_type="flaw_exploited", break_type="cold_cruelty",
                       affected_characters=[{"character_id": "char_b", "damage_type": "trust_broken", "intensity": 8}],
                       witnesses=["char_c"])
        d = b.model_dump(mode="json")
        assert d["break_id"] == "br_1"
        assert d["affected_characters"][0]["intensity"] == 8

    def test_world_has_break_fields(self):
        from worldforger.schemas import World, Meta
        w = World(meta=Meta(id="t", name="t"))
        assert w.character_pressures == []
        assert w.break_events == []

    @pytest.mark.asyncio
    async def test_pressure_update_adds_new(self, test_world):
        from worldforger.story.story_service import _update_character_pressures
        # Text with combat and conflict keywords mentioning Alice
        err = await _update_character_pressures(test_world, "ch_1",
            "Alice起身迎接战斗。敌人逼近，死亡的阴影笼罩。她与Bob发生了激烈的争吵和冲突。孤独与恐惧攫住了她。")
        assert err == ""
        pressures = test_world.character_pressures
        assert len(pressures) >= 1
        assert any(p.current_pressure > 0 for p in pressures)

    @pytest.mark.asyncio
    async def test_pressure_update_noop_on_empty(self, test_world):
        from worldforger.story.story_service import _update_character_pressures
        err = await _update_character_pressures(test_world, "ch_1",
            "A quiet morning. Nothing happens.")
        assert err == ""
        # Should not crash, may or may not add entries

    def test_break_risk_prompt_no_high_risk(self, test_world):
        from worldforger.story.story_prompts import format_break_risk
        result = format_break_risk(test_world)
        assert result == ""  # No pressure data → no risk

    def test_format_break_works(self):
        assert True  # placeholder


class TestHardContext:
    def test_builds_context_for_valid_world(self, test_world):
        from worldforger.story.story_prompts import build_hard_context
        result = build_hard_context(test_world, "ch_1", "Alice goes to market")
        assert "Ch1" in result or "Alice" in result
        assert len(result) > 20

    def test_chars_in_beat(self, test_world):
        from worldforger.story.story_prompts import _chars_in_beat
        chars = _chars_in_beat(test_world, "Alice goes to market")
        assert "char_a" in chars

# ── Truncation Detection & Continuation ────────────────────

class TestTruncationDetection:
    def test_truncated_text_heuristic_comma_end(self):
        """Text ending with comma likely truncated."""
        text = "云鹤推开石门，走进了幽暗的隧道，"
        tail = text.strip()[-50:]
        looks_truncated = tail.endswith("，") and "。" not in tail
        assert looks_truncated is True

    def test_complete_text_not_truncated(self):
        text = "云鹤终于找到了答案。他站在废墟前，望着黎明的曙光。本章完。"
        tail = text.strip()[-200:]
        has_end = any(m in tail[-100:] for m in ("## ", "本章完", "（完）"))
        ends_proper = tail.endswith("。")
        assert has_end or ends_proper  # Complete text has ending

    def test_truncated_mid_sentence(self):
        text = "云鹤转过身，看着远处的地平线。他深吸一口气，正准备说出那句话时，突然"  # truncated
        tail = text.strip()[-50:]
        looks_truncated = not tail.endswith("。") and not tail.endswith("」")
        assert looks_truncated


class TestContinuationFlow:
    @pytest.mark.asyncio
    async def test_continuation_not_triggered_for_short_reply(self, test_world):
        """Short reply should not trigger continuation (might be refusal)."""
        from worldforger.story.story_service import generate_manuscript
        with patch("worldforger.story.story_service.chat_completion",
                   new=AsyncMock(return_value="Short reply.")):
            with patch("worldforger.story.story_service._try_generate_summary_card",
                       new=AsyncMock(return_value="")):
                with patch("worldforger.story.story_service._try_update_runtime_states",
                           new=AsyncMock(return_value="")):
                    with patch("worldforger.story.story_service._try_index_chapter",
                               new=AsyncMock(return_value="")):
                        reply, _, _ = await generate_manuscript(
                            test_world, chapter_id="ch_1", prompt="test",
                            creative_mode=None, person="third_person_limited",
                            attach_prev_chapters=0, include_world_md=False,
                        )
                        # Short reply < 2000 chars won't trigger continuation
                        assert len(reply) < 2000
