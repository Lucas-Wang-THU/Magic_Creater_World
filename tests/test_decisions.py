"""Tests for character decision tracking (P1)."""
import json
import pytest
from unittest.mock import AsyncMock, patch

from worldforger.schemas import (
    CharacterDecision,
    StoryWritingDefaults,
    StoryChapter,
    StorySection,
    StoryNarrator,
    World,
    Meta,
)
from worldforger.story_prompts import (
    decision_detection_system,
    build_decision_detection_user_payload,
    format_decision_history,
)


@pytest.fixture
def sample_world():
    import uuid
    wid = f"test_{uuid.uuid4().hex[:10]}"
    return World(
        meta=Meta(id=wid, name="测试世界"),
        story=StorySection(
            writing_defaults=StoryWritingDefaults(enable_decision_track=True),
            chapters=[StoryChapter(id="ch_1", order=1, title="第一章")],
            narrator=StoryNarrator(person="third_person_limited"),
        ),
    )


class TestDecisionSchema:
    def test_defaults(self):
        d = CharacterDecision()
        assert d.decision_id == ""
        assert d.decision_type == "moral_choice"
        assert d.outcome_verdict == "pending"
        assert d.options_considered == []
        assert d.immediate_consequences == []

    def test_serialization_roundtrip(self):
        d = CharacterDecision(
            decision_id="dec_001", character_id="char_a", chapter="ch_1",
            summary="放弃救NPC以获取情报",
            decision_type="moral_choice",
            options_considered=["A: 救人", "B: 取情报"],
            option_chosen="B",
            stated_reason="情报更重要",
            actual_reason="害怕面对NPC",
            immediate_consequences=["NPC死亡", "获得情报"],
            outcome_verdict="proved_right",
        )
        d2 = CharacterDecision.model_validate(d.model_dump(mode="json"))
        assert d2.decision_id == "dec_001"
        assert d2.actual_reason == "害怕面对NPC"

    def test_all_types(self):
        for t in ("moral_choice", "trust_decision", "strategic_choice", "self_revelation", "relationship_choice", "sacrifice"):
            d = CharacterDecision(decision_id="d1", decision_type=t)
            assert d.decision_type == t

    def test_toggle_in_writing_defaults(self):
        wd = StoryWritingDefaults()
        assert wd.enable_decision_track is True

    def test_world_has_decisions_field(self):
        w = World(meta=Meta(id="test", name="Test"))
        assert w.character_decisions == []


class TestDecisionPrompts:
    def test_detection_system(self):
        s = decision_detection_system()
        assert "JSON" in s
        assert "decision_type" in s
        assert "moral_choice" in s

    def test_user_payload(self, sample_world):
        p = build_decision_detection_user_payload(sample_world, chapter_id="ch_1", manuscript_text="测试正文")
        assert "ch_1" in p
        assert "测试正文" in p

    def test_format_history_empty(self, sample_world):
        assert format_decision_history(sample_world) == ""

    def test_format_history_with_decisions(self, sample_world):
        sample_world.character_decisions = [
            CharacterDecision(decision_id="d1", character_id="char_a", chapter="ch_1",
                              summary="关键选择", decision_type="moral_choice",
                              long_term_consequences=[{"effect": "性格变化"}]),
        ]
        sample_world.characters.entities = [{"id": "char_a", "name": "艾拉"}]
        result = format_decision_history(sample_world)
        assert "决策历史" in result
        assert "艾拉" in result


class TestDecisionService:
    @pytest.mark.asyncio
    async def test_detect_new(self, sample_world):
        from worldforger.story_service import _try_detect_decisions
        reply = json.dumps({"decisions": [{
            "decision_id": "dec_001", "character_id": "char_a", "chapter": "ch_1",
            "summary": "测试决策", "decision_type": "moral_choice",
            "options_considered": ["A"], "option_chosen": "A",
            "stated_reason": "", "actual_reason": "",
            "immediate_consequences": [], "long_term_consequences": [],
            "reflections": [], "outcome_verdict": "pending",
        }]}, ensure_ascii=False)
        with patch("worldforger.story_service.chat_completion", new=AsyncMock(return_value=reply)):
            err = await _try_detect_decisions(sample_world, "ch_1", "测试正文")
            assert err == ""
            assert len(sample_world.character_decisions) == 1

    @pytest.mark.asyncio
    async def test_detect_no_decisions(self, sample_world):
        from worldforger.story_service import _try_detect_decisions
        reply = json.dumps({"decisions": []})
        with patch("worldforger.story_service.chat_completion", new=AsyncMock(return_value=reply)):
            err = await _try_detect_decisions(sample_world, "ch_1", "测试")
            assert "未发现" in err

    @pytest.mark.asyncio
    async def test_detect_dedup(self, sample_world):
        from worldforger.story_service import _try_detect_decisions
        sample_world.character_decisions.append(
            CharacterDecision(decision_id="dec_001", character_id="char_a", chapter="ch_1", summary="existing")
        )
        reply = json.dumps({"decisions": [{"decision_id": "dec_001", "character_id": "char_a", "summary": "dup"}]})
        with patch("worldforger.story_service.chat_completion", new=AsyncMock(return_value=reply)):
            err = await _try_detect_decisions(sample_world, "ch_1", "test")
            assert len(sample_world.character_decisions) == 1  # no dup

    @pytest.mark.asyncio
    async def test_detect_markdown_wrapped(self, sample_world):
        from worldforger.story_service import _try_detect_decisions
        reply = '```json\n{"decisions": [{"decision_id": "d1", "character_id": "c1", "summary": "test", "decision_type": "sacrifice", "options_considered": [], "option_chosen": "", "stated_reason": "", "actual_reason": "", "immediate_consequences": [], "long_term_consequences": [], "reflections": [], "outcome_verdict": "pending"}]}\n```'
        with patch("worldforger.story_service.chat_completion", new=AsyncMock(return_value=reply)):
            err = await _try_detect_decisions(sample_world, "ch_1", "test")
            assert err == ""
            assert len(sample_world.character_decisions) == 1
