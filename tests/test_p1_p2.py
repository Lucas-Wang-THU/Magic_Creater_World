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
