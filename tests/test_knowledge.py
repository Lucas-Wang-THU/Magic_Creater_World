"""Tests for character knowledge/cognition system (P0)."""
import json
import tempfile
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch

from worldforger.schemas import (
    CharacterKnowledgeEntry,
    CharacterKnowledgeGraph,
    StoryWritingDefaults,
    StoryChapter,
    StorySection,
    StoryNarrator,
    World,
    Meta,
)
from worldforger.story_prompts import (
    knowledge_detection_system,
    build_knowledge_detection_user_payload,
    format_knowledge_boundaries,
)


# ── Fixtures ───────────────────────────────────────────────────

@pytest.fixture
def tmp_world_id():
    import uuid
    return f"test_{uuid.uuid4().hex[:10]}"


@pytest.fixture
def sample_world(tmp_world_id):
    return World(
        meta=Meta(id=tmp_world_id, name="测试世界"),
        story=StorySection(
            writing_defaults=StoryWritingDefaults(
                enable_knowledge_track=True,
            ),
            chapters=[
                StoryChapter(id="ch_1", order=1, title="第一章"),
                StoryChapter(id="ch_2", order=2, title="第二章"),
            ],
            narrator=StoryNarrator(person="third_person_limited"),
        ),
    )


# ── Schema tests ────────────────────────────────────────────────

class TestKnowledgeSchema:
    def test_entry_defaults(self):
        e = CharacterKnowledgeEntry()
        assert e.knowledge_id == ""
        assert e.character_id == ""
        assert e.category == "secret"
        assert e.certainty == "knows_for_sure"
        assert e.is_still_true is True
        assert e.shared_with == []

    def test_entry_serialization_roundtrip(self):
        e = CharacterKnowledgeEntry(
            knowledge_id="know_traitor",
            character_id="char_finn",
            topic="艾拉是叛徒",
            category="secret",
            certainty="knows_for_sure",
            source_chapter="ch_3",
            source_detail="偷听了议会对话",
            shared_with=[{"character_id": "char_kellen", "chapter": "ch_4", "method": "主动告知"}],
            is_still_true=True,
            notes="关键剧情信息",
        )
        d = e.model_dump(mode="json")
        e2 = CharacterKnowledgeEntry.model_validate(d)
        assert e2.knowledge_id == "know_traitor"
        assert e2.topic == "艾拉是叛徒"
        assert e2.shared_with == [{"character_id": "char_kellen", "chapter": "ch_4", "method": "主动告知"}]

    def test_all_valid_categories(self):
        for cat in ("secret", "personal_history", "world_lore", "plan", "suspicion", "misunderstanding"):
            e = CharacterKnowledgeEntry(knowledge_id="k1", category=cat)
            assert e.category == cat

    def test_all_valid_certainties(self):
        for cert in ("knows_for_sure", "strongly_suspects", "vaguely_senses", "believes_wrongly"):
            e = CharacterKnowledgeEntry(knowledge_id="k1", certainty=cert)
            assert e.certainty == cert

    def test_graph_defaults(self):
        g = CharacterKnowledgeGraph()
        assert g.entries == []

    def test_graph_with_entries(self):
        e1 = CharacterKnowledgeEntry(knowledge_id="k1", character_id="c1", topic="秘密")
        e2 = CharacterKnowledgeEntry(knowledge_id="k2", character_id="c2", topic="传说")
        g = CharacterKnowledgeGraph(entries=[e1, e2])
        assert len(g.entries) == 2

    def test_world_has_knowledge_field(self):
        w = World(meta=Meta(id="test", name="Test"))
        assert isinstance(w.character_knowledge, CharacterKnowledgeGraph)
        assert w.character_knowledge.entries == []

    def test_writing_defaults_has_knowledge_toggle(self):
        wd = StoryWritingDefaults()
        assert wd.enable_knowledge_track is True


# ── Prompt tests ────────────────────────────────────────────────

class TestKnowledgePrompts:
    def test_detection_system_returns_str(self):
        s = knowledge_detection_system()
        assert isinstance(s, str)
        assert "JSON" in s
        assert "new_entries" in s
        assert "secret" in s
        assert "misunderstanding" in s

    def test_detection_user_payload(self, sample_world):
        payload = build_knowledge_detection_user_payload(
            sample_world, chapter_id="ch_1", manuscript_text="测试正文内容。"
        )
        assert "ch_1" in payload
        assert "测试正文内容" in payload

    def test_detection_user_payload_with_existing_knowledge(self, sample_world):
        e = CharacterKnowledgeEntry(
            knowledge_id="k1", character_id="char_1",
            topic="古神的存在", category="world_lore",
        )
        sample_world.character_knowledge.entries.append(e)
        payload = build_knowledge_detection_user_payload(
            sample_world, chapter_id="ch_2", manuscript_text="新章节。"
        )
        assert "已有知识条目" in payload
        assert "k1" in payload
        assert "古神的存在" in payload

    def test_format_knowledge_boundaries_empty(self, sample_world):
        result = format_knowledge_boundaries(sample_world, "ch_1")
        assert result == ""

    def test_format_knowledge_boundaries_with_entries(self, sample_world):
        e1 = CharacterKnowledgeEntry(
            knowledge_id="k1", character_id="char_1",
            topic="翠绿议会的秘密", category="secret",
            certainty="knows_for_sure",
        )
        e2 = CharacterKnowledgeEntry(
            knowledge_id="k2", character_id="char_2",
            topic="芬恩的真实身份", category="suspicion",
            certainty="strongly_suspects",
        )
        sample_world.character_knowledge.entries = [e1, e2]
        sample_world.characters.entities = [
            {"id": "char_1", "name": "艾拉"},
            {"id": "char_2", "name": "凯伦"},
        ]

        result = format_knowledge_boundaries(sample_world, "ch_1")
        assert "信息边界" in result
        assert "艾拉" in result
        assert "翠绿议会的秘密" in result
        assert "knows_for_sure" in result
        assert "凯伦" in result
        assert "strongly_suspects" in result


# ── Storage tests ────────────────────────────────────────────────

class TestKnowledgeStorage:
    def test_knowledge_graph_path_format(self, tmp_path):
        """knowledge_graph_path returns correct file name."""
        # We test the import and function signature
        from worldforger.story_store import knowledge_graph_path as kgp
        assert callable(kgp)

    def test_read_write_roundtrip(self, tmp_path):
        """Read/write roundtrip with patched path function."""
        test_file = tmp_path / "knowledge_graph.json"

        with patch("worldforger.story_store.knowledge_graph_path", return_value=test_file):
            from worldforger.story_store import read_knowledge_graph, write_knowledge_graph
            data = {"entries": [{"knowledge_id": "k1", "character_id": "c1", "topic": "测试"}]}
            write_knowledge_graph("test_id", data)
            result = read_knowledge_graph("test_id")
            assert result["entries"][0]["knowledge_id"] == "k1"

    def test_read_missing_file_returns_empty(self, tmp_path):
        test_file = tmp_path / "nonexistent.json"
        with patch("worldforger.story_store.knowledge_graph_path", return_value=test_file):
            from worldforger.story_store import read_knowledge_graph
            result = read_knowledge_graph("test_id")
            assert result == {}


# ── Service hook tests ──────────────────────────────────────────

class TestKnowledgeService:
    @pytest.mark.asyncio
    async def test_detect_knowledge_new_entries(self, sample_world):
        from worldforger.story_service import _try_detect_knowledge

        mock_reply = json.dumps({
            "new_entries": [
                {
                    "knowledge_id": "know_secret",
                    "character_id": "char_1",
                    "topic": "古神即将苏醒",
                    "category": "secret",
                    "certainty": "knows_for_sure",
                    "source_chapter": "ch_1",
                    "source_detail": "偷听了祭祀的对话",
                    "shared_with": [],
                    "is_still_true": True,
                    "notes": "",
                }
            ],
            "updated_entries": [],
        }, ensure_ascii=False)

        with patch("worldforger.story_service.chat_completion", new=AsyncMock(return_value=mock_reply)):
            err = await _try_detect_knowledge(sample_world, "ch_1", "测试正文")
            assert err == ""
            assert len(sample_world.character_knowledge.entries) == 1
            assert sample_world.character_knowledge.entries[0].knowledge_id == "know_secret"

    @pytest.mark.asyncio
    async def test_detect_knowledge_no_changes(self, sample_world):
        from worldforger.story_service import _try_detect_knowledge

        mock_reply = json.dumps({"new_entries": [], "updated_entries": []})
        with patch("worldforger.story_service.chat_completion", new=AsyncMock(return_value=mock_reply)):
            err = await _try_detect_knowledge(sample_world, "ch_1", "测试正文")
            assert err == ""
            assert len(sample_world.character_knowledge.entries) == 0

    @pytest.mark.asyncio
    async def test_detect_knowledge_dedup(self, sample_world):
        from worldforger.story_service import _try_detect_knowledge

        existing = CharacterKnowledgeEntry(
            knowledge_id="know_secret", character_id="char_1",
            topic="古神即将苏醒", category="secret",
        )
        sample_world.character_knowledge.entries.append(existing)

        mock_reply = json.dumps({
            "new_entries": [
                {
                    "knowledge_id": "know_secret",
                    "character_id": "char_1",
                    "topic": "duplicate",
                    "category": "secret",
                    "certainty": "knows_for_sure",
                    "source_chapter": "ch_1",
                    "source_detail": "",
                    "shared_with": [],
                    "is_still_true": True,
                    "notes": "",
                }
            ],
            "updated_entries": [],
        }, ensure_ascii=False)

        with patch("worldforger.story_service.chat_completion", new=AsyncMock(return_value=mock_reply)):
            err = await _try_detect_knowledge(sample_world, "ch_1", "测试正文")
            assert err == ""
            assert len(sample_world.character_knowledge.entries) == 1

    @pytest.mark.asyncio
    async def test_detect_knowledge_update_existing(self, sample_world):
        from worldforger.story_service import _try_detect_knowledge

        existing = CharacterKnowledgeEntry(
            knowledge_id="know_secret", character_id="char_1",
            topic="古神即将苏醒", is_still_true=True, notes="",
        )
        sample_world.character_knowledge.entries.append(existing)

        mock_reply = json.dumps({
            "new_entries": [],
            "updated_entries": [
                {
                    "knowledge_id": "know_secret",
                    "is_still_true": False,
                    "notes": "事实已变化：古神已苏醒",
                }
            ],
        }, ensure_ascii=False)

        with patch("worldforger.story_service.chat_completion", new=AsyncMock(return_value=mock_reply)):
            err = await _try_detect_knowledge(sample_world, "ch_1", "测试正文")
            assert err == ""
            assert sample_world.character_knowledge.entries[0].is_still_true is False
            assert "古神已苏醒" in sample_world.character_knowledge.entries[0].notes

    @pytest.mark.asyncio
    async def test_detect_knowledge_markdown_wrapped_json(self, sample_world):
        from worldforger.story_service import _try_detect_knowledge

        mock_reply = '```json\n{"new_entries": [{"knowledge_id": "k1", "character_id": "c1", "topic": "测试", "category": "secret", "certainty": "knows_for_sure", "source_chapter": "ch_1", "source_detail": "", "shared_with": [], "is_still_true": true, "notes": ""}], "updated_entries": []}\n```'

        with patch("worldforger.story_service.chat_completion", new=AsyncMock(return_value=mock_reply)):
            err = await _try_detect_knowledge(sample_world, "ch_1", "测试正文")
            assert err == ""
            assert len(sample_world.character_knowledge.entries) == 1

    @pytest.mark.asyncio
    async def test_detect_knowledge_invalid_json(self, sample_world):
        from worldforger.story_service import _try_detect_knowledge

        mock_reply = "这不是有效的 JSON 格式"

        with patch("worldforger.story_service.chat_completion", new=AsyncMock(return_value=mock_reply)):
            err = await _try_detect_knowledge(sample_world, "ch_1", "测试正文")
            assert err != ""
            assert "知识检测" in err

    @pytest.mark.asyncio
    async def test_detect_knowledge_empty_response(self, sample_world):
        from worldforger.story_service import _try_detect_knowledge

        with patch("worldforger.story_service.chat_completion", new=AsyncMock(return_value="")):
            err = await _try_detect_knowledge(sample_world, "ch_1", "测试正文")
            assert err != ""

    @pytest.mark.asyncio
    async def test_detect_knowledge_shared_with_update(self, sample_world):
        from worldforger.story_service import _try_detect_knowledge

        existing = CharacterKnowledgeEntry(
            knowledge_id="know_secret", character_id="char_1",
            topic="秘密", shared_with=[],
        )
        sample_world.character_knowledge.entries.append(existing)

        mock_reply = json.dumps({
            "new_entries": [],
            "updated_entries": [
                {
                    "knowledge_id": "know_secret",
                    "shared_with": [{"character_id": "char_2", "chapter": "ch_2", "method": "主动告知"}],
                }
            ],
        }, ensure_ascii=False)

        with patch("worldforger.story_service.chat_completion", new=AsyncMock(return_value=mock_reply)):
            err = await _try_detect_knowledge(sample_world, "ch_2", "测试正文")
            assert err == ""
            assert len(sample_world.character_knowledge.entries[0].shared_with) == 1

    @pytest.mark.asyncio
    async def test_detect_knowledge_both_new_and_update(self, sample_world):
        from worldforger.story_service import _try_detect_knowledge

        existing = CharacterKnowledgeEntry(
            knowledge_id="old_knowledge", character_id="char_1",
            topic="旧知识", is_still_true=True,
        )
        sample_world.character_knowledge.entries.append(existing)

        mock_reply = json.dumps({
            "new_entries": [
                {
                    "knowledge_id": "new_knowledge",
                    "character_id": "char_2",
                    "topic": "新知识",
                    "category": "world_lore",
                    "certainty": "knows_for_sure",
                    "source_chapter": "ch_2",
                    "source_detail": "从古书中学到",
                    "shared_with": [],
                    "is_still_true": True,
                    "notes": "",
                }
            ],
            "updated_entries": [
                {"knowledge_id": "old_knowledge", "is_still_true": False, "notes": "过时了"}
            ],
        }, ensure_ascii=False)

        with patch("worldforger.story_service.chat_completion", new=AsyncMock(return_value=mock_reply)):
            err = await _try_detect_knowledge(sample_world, "ch_2", "测试正文")
            assert err == ""
            assert len(sample_world.character_knowledge.entries) == 2
            old = next(e for e in sample_world.character_knowledge.entries if e.knowledge_id == "old_knowledge")
            assert old.is_still_true is False


# ── Integration tests ───────────────────────────────────────────

class TestKnowledgeIntegration:
    def test_toggle_default_true(self):
        w = World(meta=Meta(id="test", name="Test"))
        assert w.story.writing_defaults.enable_knowledge_track is True

    def test_format_boundaries_with_entries(self, sample_world):
        e = CharacterKnowledgeEntry(knowledge_id="k1", character_id="c1", topic="测试")
        sample_world.character_knowledge.entries.append(e)
        result = format_knowledge_boundaries(sample_world, "ch_1")
        assert result != ""

    def test_format_boundaries_empty_when_no_entries(self, sample_world):
        result = format_knowledge_boundaries(sample_world, "ch_1")
        assert result == ""
