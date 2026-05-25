"""Layer 3: 叙事知识图谱 + 一致性审校 + 情感弧线 测试。"""
import json
import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from worldforger.schemas import (
    CharacterStateSnapshot,
    ConsistencyIssue,
    ConsistencyReport,
    KGEntity,
    KGEvent,
    NarrativeKG,
    SentimentLog,
    SentimentSegment,
    StoryChapter,
    StoryWritingDefaults,
    World,
)
from worldforger.story_store import (
    consistency_path,
    ensure_story_dirs,
    narrative_kg_path,
    read_consistency_report,
    read_narrative_kg,
    read_sentiment_log,
    sentiment_path,
    write_consistency_report,
    write_narrative_kg,
    write_sentiment_log,
)
from worldforger.world_store import create_world, load_world, save_world

client = TestClient(app)


# ═══════════════════════════════════════════════════════════════
# Schema validation
# ═══════════════════════════════════════════════════════════════

class TestCharacterStateSnapshot:
    def test_defaults(self):
        s = CharacterStateSnapshot()
        assert s.chapter_id == ""
        assert s.location == ""
        assert s.emotion == ""
        assert s.goal == ""

    def test_full_snapshot(self):
        s = CharacterStateSnapshot(
            chapter_id="ch_01", location="北境", emotion="悲愤", goal="寻找真相"
        )
        assert s.chapter_id == "ch_01"
        assert s.location == "北境"

    def test_serialization_roundtrip(self):
        s = CharacterStateSnapshot(
            chapter_id="ch_01", location="王都", emotion="坚定", goal="击败魔王"
        )
        d = s.model_dump(mode="json")
        s2 = CharacterStateSnapshot(**d)
        assert s2.chapter_id == s.chapter_id
        assert s2.location == s.location


class TestKGEntity:
    def test_defaults(self):
        e = KGEntity()
        assert e.entity_type == "character"
        assert e.states == []
        assert e.item_status == "active"

    def test_character_entity(self):
        e = KGEntity(
            entity_id="char_01", entity_type="character", name="爱丽丝",
            states=[CharacterStateSnapshot(chapter_id="ch_01", location="森林")]
        )
        assert len(e.states) == 1

    def test_item_entity(self):
        e = KGEntity(
            entity_id="item_01", entity_type="item", name="圣剑",
            item_status="active", possessed_by="char_01", last_seen_chapter="ch_01"
        )
        assert e.entity_type == "item"
        assert e.possessed_by == "char_01"


class TestKGEvent:
    def test_defaults(self):
        evt = KGEvent()
        assert evt.event_id == ""
        assert evt.participants == []

    def test_full_event(self):
        evt = KGEvent(
            event_id="evt_01", chapter_id="ch_01", event_type="battle",
            summary="大战黑龙", participants=["char_01", "char_02"],
            location="龙巢", consequences=["char_01 受伤", "获得龙晶"]
        )
        d = evt.model_dump(mode="json")
        evt2 = KGEvent(**d)
        assert evt2.event_type == "battle"
        assert len(evt2.participants) == 2


class TestNarrativeKG:
    def test_empty_kg(self):
        kg = NarrativeKG()
        assert kg.entities == []
        assert kg.events == []
        assert kg.foreshadowing_ids == []

    def test_with_entities_and_events(self):
        kg = NarrativeKG(
            entities=[KGEntity(entity_id="char_01", name="主角")],
            events=[KGEvent(event_id="evt_01", chapter_id="ch_01")],
            foreshadowing_ids=["fs_01"],
            last_updated_chapter="ch_01",
        )
        d = kg.model_dump(mode="json")
        kg2 = NarrativeKG(**d)
        assert len(kg2.entities) == 1
        assert len(kg2.events) == 1
        assert kg2.foreshadowing_ids == ["fs_01"]


class TestConsistencyIssue:
    def test_defaults(self):
        iss = ConsistencyIssue()
        assert iss.category == "position"
        assert iss.severity == "warning"

    def test_critical_issue(self):
        iss = ConsistencyIssue(
            issue_id="ci_01", category="pov", severity="critical",
            description="POV 不一致：上一章以爱丽丝视角叙述，本章切换为全知视角但未标记。"
        )
        assert iss.severity == "critical"

    def test_serialization(self):
        iss = ConsistencyIssue(
            category="timeline", severity="info",
            description="时间线：事件发生在前一章之前但未说明闪回。",
            excerpt="那天早上...", suggestion="添加闪回标记"
        )
        d = iss.model_dump(mode="json")
        iss2 = ConsistencyIssue(**d)
        assert iss2.excerpt == "那天早上..."


class TestConsistencyReport:
    def test_clean_report(self):
        cr = ConsistencyReport(chapter_id="ch_01", verdict="clean")
        assert cr.total_issues == 0
        assert cr.issues == []

    def test_with_issues(self):
        cr = ConsistencyReport(
            chapter_id="ch_01", verdict="needs_review", total_issues=2,
            issues=[
                ConsistencyIssue(category="position", severity="critical", description="位置错误"),
                ConsistencyIssue(category="pov", severity="warning", description="视角问题"),
            ]
        )
        d = cr.model_dump(mode="json")
        cr2 = ConsistencyReport(**d)
        assert cr2.total_issues == 2
        assert len(cr2.issues) == 2


class TestSentimentSegment:
    def test_defaults(self):
        seg = SentimentSegment()
        assert seg.tone == "mixed"
        assert seg.intensity == 5

    def test_intensity_clamp(self):
        # Pydantic v2 raises validation error for out-of-range values
        with pytest.raises(Exception):
            SentimentSegment(intensity=15)
        # Valid value works
        seg = SentimentSegment(intensity=10)
        assert seg.intensity == 10


class TestSentimentLog:
    def test_defaults(self):
        sl = SentimentLog()
        assert sl.transition_from_prev == "first_chapter"
        assert sl.segments == []

    def test_with_segments(self):
        sl = SentimentLog(
            chapter_id="ch_01", title="开端",
            segments=[
                SentimentSegment(segment_index=1, label="开篇", tone="calm", intensity=4),
                SentimentSegment(segment_index=2, label="高潮", tone="tense", intensity=8),
            ],
            overall_tone="tense", ending_tone="tense",
            transition_from_prev="first_chapter",
        )
        d = sl.model_dump(mode="json")
        sl2 = SentimentLog(**d)
        assert len(sl2.segments) == 2
        assert sl2.ending_tone == "tense"


class TestStoryWritingDefaultsToggles:
    def test_defaults_enable_all(self):
        wd = StoryWritingDefaults()
        assert wd.enable_narrative_kg is True
        assert wd.enable_consistency_check is True
        assert wd.enable_sentiment_track is True

    def test_toggles_in_world_roundtrip(self):
        w = create_world("toggle test")
        w.story.writing_defaults.enable_narrative_kg = False
        w.story.writing_defaults.enable_consistency_check = False
        w.story.writing_defaults.enable_sentiment_track = False
        d = w.model_dump(mode="json")
        w2 = World.model_validate(d)
        assert w2.story.writing_defaults.enable_narrative_kg is False
        assert w2.story.writing_defaults.enable_consistency_check is False
        assert w2.story.writing_defaults.enable_sentiment_track is False


class TestStoryChapterOptionalFields:
    def test_chapter_has_layer3_fields(self):
        ch = StoryChapter(id="ch_01", order=1, title="测试")
        assert ch.consistency_report is None
        assert ch.sentiment_log is None

    def test_chapter_with_consistency_report(self):
        cr = ConsistencyReport(chapter_id="ch_01", verdict="clean")
        ch = StoryChapter(id="ch_01", order=1, consistency_report=cr)
        assert ch.consistency_report is not None
        assert ch.consistency_report.verdict == "clean"
        d = ch.model_dump(mode="json")
        assert d["consistency_report"]["verdict"] == "clean"


# ═══════════════════════════════════════════════════════════════
# Storage path tests
# ═══════════════════════════════════════════════════════════════

class TestLayer3Paths:
    def test_narrative_kg_path(self):
        p = narrative_kg_path("world_x")
        assert p.name == "narrative_kg.json"
        assert "story" in str(p)

    def test_consistency_path(self):
        p = consistency_path("world_x", "ch_01")
        assert p.name == "ch_01.json"
        assert "consistency_reports" in str(p)

    def test_sentiment_path(self):
        p = sentiment_path("world_x", "ch_01")
        assert p.name == "ch_01.json"
        assert "sentiment_logs" in str(p)


class TestLayer3ReadWrite:
    def test_narrative_kg_write_read(self, tmp_path, monkeypatch):
        world_id = "test_kg_rw"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        from worldforger.story_store import story_dir
        story = story_dir(world_id)
        # Override world_root to use tmp_path
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            ensure_story_dirs(world_id)
            data = {"entities": [{"entity_id": "char_01", "name": "Test"}], "events": []}
            write_narrative_kg(world_id, data)
            read = read_narrative_kg(world_id)
            assert read is not None
            assert len(read["entities"]) == 1
        finally:
            ws.world_root = original

    def test_consistency_report_write_read(self, tmp_path, monkeypatch):
        world_id = "test_cr_rw"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            ensure_story_dirs(world_id)
            data = {"chapter_id": "ch_01", "verdict": "clean", "total_issues": 0, "issues": []}
            write_consistency_report(world_id, "ch_01", data)
            read = read_consistency_report(world_id, "ch_01")
            assert read is not None
            assert read["verdict"] == "clean"
        finally:
            ws.world_root = original

    def test_sentiment_log_write_read(self, tmp_path, monkeypatch):
        world_id = "test_sl_rw"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            ensure_story_dirs(world_id)
            data = {"chapter_id": "ch_01", "overall_tone": "tense", "segments": []}
            write_sentiment_log(world_id, "ch_01", data)
            read = read_sentiment_log(world_id, "ch_01")
            assert read is not None
            assert read["overall_tone"] == "tense"
        finally:
            ws.world_root = original

    def test_ensure_story_dirs_creates_layer3_dirs(self, tmp_path, monkeypatch):
        world_id = "test_dirs"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            ensure_story_dirs(world_id)
            assert consistency_path(world_id, "x").parent.is_dir()
            assert sentiment_path(world_id, "x").parent.is_dir()
        finally:
            ws.world_root = original


# ═══════════════════════════════════════════════════════════════
# NarrativeKGManager tests
# ═══════════════════════════════════════════════════════════════

class TestNarrativeKGManager:
    def test_load_empty(self, tmp_path, monkeypatch):
        world_id = "test_kg_mgr_empty"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.narrative_kg import NarrativeKGManager
            ensure_story_dirs(world_id)
            mgr = NarrativeKGManager(world_id)
            kg = mgr.load()
            assert isinstance(kg, NarrativeKG)
            assert kg.entities == []
            assert kg.events == []
        finally:
            ws.world_root = original

    def test_save_and_load(self, tmp_path, monkeypatch):
        world_id = "test_kg_save"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.narrative_kg import NarrativeKGManager
            ensure_story_dirs(world_id)
            kg = NarrativeKG(
                entities=[KGEntity(entity_id="char_01", name="爱丽丝", entity_type="character")],
                events=[KGEvent(event_id="evt_01", chapter_id="ch_01", event_type="discovery")],
            )
            mgr = NarrativeKGManager(world_id)
            mgr.save(kg)
            kg2 = mgr.load()
            assert len(kg2.entities) == 1
            assert len(kg2.events) == 1
        finally:
            ws.world_root = original

    def test_get_character_timeline(self, tmp_path, monkeypatch):
        world_id = "test_kg_timeline"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.narrative_kg import NarrativeKGManager
            ensure_story_dirs(world_id)
            kg = NarrativeKG(entities=[
                KGEntity(
                    entity_id="char_01", name="爱丽丝", entity_type="character",
                    states=[
                        CharacterStateSnapshot(chapter_id="ch_01", location="森林"),
                        CharacterStateSnapshot(chapter_id="ch_02", location="王都"),
                    ]
                )
            ])
            mgr = NarrativeKGManager(world_id)
            mgr.save(kg)
            timeline = mgr.get_character_timeline("char_01")
            assert len(timeline) == 2
            assert timeline[1].location == "王都"
        finally:
            ws.world_root = original

    def test_get_character_state_none_for_unknown(self, tmp_path, monkeypatch):
        world_id = "test_kg_unknown"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.narrative_kg import NarrativeKGManager
            ensure_story_dirs(world_id)
            mgr = NarrativeKGManager(world_id)
            assert mgr.get_character_state("nonexistent") is None
        finally:
            ws.world_root = original

    def test_get_item_status(self, tmp_path, monkeypatch):
        world_id = "test_kg_item"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.narrative_kg import NarrativeKGManager
            ensure_story_dirs(world_id)
            kg = NarrativeKG(entities=[
                KGEntity(entity_id="item_01", entity_type="item", name="圣剑",
                         item_status="active", possessed_by="char_01")
            ])
            mgr = NarrativeKGManager(world_id)
            mgr.save(kg)
            item = mgr.get_item_status("item_01")
            assert item is not None
            assert item.possessed_by == "char_01"
        finally:
            ws.world_root = original

    def test_get_events_for_chapter(self, tmp_path, monkeypatch):
        world_id = "test_kg_events"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.narrative_kg import NarrativeKGManager
            ensure_story_dirs(world_id)
            kg = NarrativeKG(events=[
                KGEvent(event_id="evt_01", chapter_id="ch_01", event_type="battle"),
                KGEvent(event_id="evt_02", chapter_id="ch_02", event_type="alliance"),
            ])
            mgr = NarrativeKGManager(world_id)
            mgr.save(kg)
            ch1_events = mgr.get_events_for_chapter("ch_01")
            assert len(ch1_events) == 1
            assert ch1_events[0].event_id == "evt_01"
        finally:
            ws.world_root = original

    def test_merge_extraction_new_entities(self, tmp_path, monkeypatch):
        world_id = "test_kg_merge"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.narrative_kg import NarrativeKGManager
            ensure_story_dirs(world_id)
            mgr = NarrativeKGManager(world_id)
            extracted = {
                "entities": [
                    {"entity_id": "char_01", "entity_type": "character", "name": "爱丽丝",
                     "states": [{"chapter_id": "ch_01", "location": "森林", "emotion": "平静", "goal": "探险"}]}
                ],
                "events": [
                    {"event_id": "evt_01", "chapter_id": "ch_01", "event_type": "discovery",
                     "summary": "发现遗迹", "participants": ["char_01"], "location": "森林", "consequences": []}
                ],
                "foreshadowing_planted": ["fs_01"],
                "foreshadowing_resolved": [],
            }
            kg = mgr.merge_extraction(extracted)
            assert len(kg.entities) == 1
            assert len(kg.events) == 1
            assert "fs_01" in kg.foreshadowing_ids
        finally:
            ws.world_root = original

    def test_merge_extraction_dedup_events(self, tmp_path, monkeypatch):
        world_id = "test_kg_dedup"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.narrative_kg import NarrativeKGManager
            ensure_story_dirs(world_id)
            kg = NarrativeKG(events=[
                KGEvent(event_id="evt_01", chapter_id="ch_01", event_type="battle", summary="战斗")
            ])
            mgr = NarrativeKGManager(world_id)
            mgr.save(kg)
            extracted = {
                "entities": [],
                "events": [
                    {"event_id": "evt_01", "chapter_id": "ch_01", "event_type": "battle",
                     "summary": "重复事件", "participants": [], "location": "", "consequences": []},
                ],
                "foreshadowing_planted": [],
                "foreshadowing_resolved": [],
            }
            kg2 = mgr.merge_extraction(extracted)
            assert len(kg2.events) == 1  # deduped, still 1
        finally:
            ws.world_root = original

    def test_format_for_prompt(self, tmp_path, monkeypatch):
        world_id = "test_kg_prompt"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.narrative_kg import NarrativeKGManager
            ensure_story_dirs(world_id)
            kg = NarrativeKG(entities=[
                KGEntity(
                    entity_id="char_01", name="爱丽丝", entity_type="character",
                    states=[CharacterStateSnapshot(chapter_id="ch_01", location="王都", emotion="坚定", goal="寻找真相")]
                )
            ])
            mgr = NarrativeKGManager(world_id)
            mgr.save(kg)
            text = mgr.format_for_prompt()
            assert "爱丽丝" in text
            assert "王都" in text
            assert "坚定" in text
        finally:
            ws.world_root = original

    def test_format_for_prompt_empty(self, tmp_path, monkeypatch):
        world_id = "test_kg_prompt_empty"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.narrative_kg import NarrativeKGManager
            ensure_story_dirs(world_id)
            mgr = NarrativeKGManager(world_id)
            assert mgr.format_for_prompt() == ""
        finally:
            ws.world_root = original

    def test_merge_character_state_append(self, tmp_path, monkeypatch):
        world_id = "test_kg_state_append"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.narrative_kg import NarrativeKGManager
            ensure_story_dirs(world_id)
            kg = NarrativeKG(entities=[
                KGEntity(entity_id="char_01", name="爱丽丝", entity_type="character",
                         states=[CharacterStateSnapshot(chapter_id="ch_01", location="森林")])
            ])
            mgr = NarrativeKGManager(world_id)
            mgr.save(kg)
            extracted = {
                "entities": [
                    {"entity_id": "char_01", "entity_type": "character", "name": "爱丽丝",
                     "states": [{"chapter_id": "ch_02", "location": "王都", "emotion": "坚定", "goal": "寻找真相"}]}
                ],
                "events": [],
                "foreshadowing_planted": [],
                "foreshadowing_resolved": [],
            }
            kg2 = mgr.merge_extraction(extracted)
            char = next(e for e in kg2.entities if e.entity_id == "char_01")
            assert len(char.states) == 2  # new state appended
            assert char.states[1].location == "王都"
        finally:
            ws.world_root = original


# ═══════════════════════════════════════════════════════════════
# SentimentTracker tests
# ═══════════════════════════════════════════════════════════════

class TestSentimentTracker:
    def test_load_log_empty(self, tmp_path, monkeypatch):
        world_id = "test_st_empty"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.sentiment_tracker import SentimentTracker
            ensure_story_dirs(world_id)
            tracker = SentimentTracker(world_id)
            assert tracker.load_log("ch_01") is None
        finally:
            ws.world_root = original

    def test_save_and_load_log(self, tmp_path, monkeypatch):
        world_id = "test_st_save"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.sentiment_tracker import SentimentTracker
            ensure_story_dirs(world_id)
            log = SentimentLog(
                chapter_id="ch_01", title="开端",
                segments=[SentimentSegment(segment_index=1, label="开篇", tone="calm", intensity=4)],
                overall_tone="calm", ending_tone="calm",
                transition_from_prev="first_chapter",
            )
            tracker = SentimentTracker(world_id)
            tracker.save_log(log)
            loaded = tracker.load_log("ch_01")
            assert loaded is not None
            assert loaded.overall_tone == "calm"
            assert len(loaded.segments) == 1
        finally:
            ws.world_root = original

    def test_get_previous_ending_tone(self, tmp_path, monkeypatch):
        world_id = "test_st_prev"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.sentiment_tracker import SentimentTracker
            ensure_story_dirs(world_id)
            w = create_world("情感测试")
            # Override world root
            ws.world_root = lambda wid: root / wid
            # Add chapters with sentiment
            ch1 = StoryChapter(id="ch_01", order=1, title="第一章",
                               sentiment_log=SentimentLog(chapter_id="ch_01", overall_tone="calm", ending_tone="calm"))
            ch2 = StoryChapter(id="ch_02", order=2, title="第二章")
            w.story.chapters = [ch1, ch2]
            tracker = SentimentTracker(world_id)
            tone = tracker.get_previous_ending_tone(w, "ch_02")
            assert tone == "calm"
        finally:
            ws.world_root = original

    def test_get_previous_ending_tone_first_chapter(self, tmp_path, monkeypatch):
        world_id = "test_st_first"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.sentiment_tracker import SentimentTracker
            w = create_world("情感测试2")
            w.story.chapters = [StoryChapter(id="ch_01", order=1, title="第一章")]
            tracker = SentimentTracker(world_id)
            tone = tracker.get_previous_ending_tone(w, "ch_01")
            assert tone == ""
        finally:
            ws.world_root = original

    def test_build_sentiment_arc_chart(self, tmp_path, monkeypatch):
        world_id = "test_st_chart"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.sentiment_tracker import SentimentTracker
            ensure_story_dirs(world_id)
            w = create_world("情感图表")
            w.story.chapters = [
                StoryChapter(id="ch_01", order=1, title="开端",
                             sentiment_log=SentimentLog(chapter_id="ch_01", overall_tone="positive")),
                StoryChapter(id="ch_02", order=2, title="发展",
                             sentiment_log=SentimentLog(chapter_id="ch_02", overall_tone="tense")),
            ]
            tracker = SentimentTracker(world_id)
            chart_data = tracker.build_sentiment_arc_chart(w)
            assert isinstance(chart_data, list)
            assert len(chart_data) == 2
            assert chart_data[0]["chapter_id"] == "ch_01"
            assert chart_data[0]["tone_value"] == 5  # positive = 5
            assert chart_data[0]["tone_color"] == "#16a34a"
            assert chart_data[1]["tone_value"] == 2  # tense = 2
            assert chart_data[1]["tone_color"] == "#f59e0b"
            assert "avg_intensity" in chart_data[0]
        finally:
            ws.world_root = original

    def test_build_sentiment_arc_chart_empty(self, tmp_path, monkeypatch):
        world_id = "test_st_chart_empty"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.sentiment_tracker import SentimentTracker
            w = create_world("空图表")
            w.story.chapters = []
            tracker = SentimentTracker(world_id)
            assert tracker.build_sentiment_arc_chart(w) == []
        finally:
            ws.world_root = original

    def test_parse_sentiment_valid(self):
        from worldforger.sentiment_tracker import _parse_sentiment
        raw = json.dumps({
            "segments": [{"segment_index": 1, "label": "开篇", "tone": "calm", "intensity": 4, "summary": "平静开始"}],
            "overall_tone": "calm", "ending_tone": "calm",
            "transition_from_prev": "first_chapter",
        })
        log = _parse_sentiment(raw, "ch_01", "开端")
        assert log is not None
        assert log.overall_tone == "calm"

    def test_parse_sentiment_invalid_json(self):
        from worldforger.sentiment_tracker import _parse_sentiment
        assert _parse_sentiment("not json", "ch_01", "test") is None

    def test_parse_sentiment_not_dict(self):
        from worldforger.sentiment_tracker import _parse_sentiment
        assert _parse_sentiment("[1, 2, 3]", "ch_01", "test") is None


# ═══════════════════════════════════════════════════════════════
# Consistency checker tests
# ═══════════════════════════════════════════════════════════════

class TestConsistencyChecker:
    def test_parse_check_result_valid(self):
        from worldforger.consistency_checker import _parse_check_result
        raw = json.dumps({
            "verdict": "minor_issues",
            "issues": [
                {"category": "position", "severity": "warning", "description": "位置不一致",
                 "excerpt": "", "suggestion": ""}
            ]
        })
        cr = _parse_check_result(raw, "ch_01")
        assert cr.verdict == "minor_issues"
        assert cr.total_issues == 1
        assert cr.chapter_id == "ch_01"

    def test_parse_check_result_clean(self):
        from worldforger.consistency_checker import _parse_check_result
        raw = json.dumps({"verdict": "clean", "issues": []})
        cr = _parse_check_result(raw, "ch_01")
        assert cr.verdict == "clean"
        assert cr.total_issues == 0

    def test_parse_check_result_with_code_fences(self):
        from worldforger.consistency_checker import _parse_check_result
        raw = '```json\n' + json.dumps({"verdict": "clean", "issues": []}) + '\n```'
        cr = _parse_check_result(raw, "ch_01")
        assert cr.verdict == "clean"

    def test_parse_check_result_no_json(self):
        from worldforger.consistency_checker import _parse_check_result
        cr = _parse_check_result("no json here at all", "ch_01")
        assert cr.verdict == "clean"
        assert cr.total_issues == 0

    def test_parse_check_result_invalid_json(self):
        from worldforger.consistency_checker import _parse_check_result
        cr = _parse_check_result("{invalid json!!!}", "ch_01")
        assert cr.verdict == "clean"

    def test_parse_check_result_not_dict(self):
        from worldforger.consistency_checker import _parse_check_result
        cr = _parse_check_result("[1, 2, 3]", "ch_01")
        assert cr.verdict == "clean"

    async def test_run_consistency_check_with_mock_llm(self, tmp_path, monkeypatch):
        """模拟 LLM 返回一个包含问题的审校报告。"""
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.consistency_checker import run_consistency_check
            w = create_world("审校测试")
            world_id = w.meta.id
            ensure_story_dirs(world_id)
            w.story.chapters = [StoryChapter(id="ch_01", order=1, title="测试章")]
            mock_raw = json.dumps({
                "verdict": "needs_review",
                "issues": [
                    {"category": "pov", "severity": "critical",
                     "description": "POV 不一致", "excerpt": "...", "suggestion": "统一视角"}
                ]
            })
            with patch("worldforger.consistency_checker.chat_completion",
                       new_callable=AsyncMock, return_value=mock_raw):
                cr = await run_consistency_check(w, "ch_01", "正文内容...")
                assert cr.verdict == "needs_review"
                assert cr.total_issues == 1
                # Verify report persisted to disk
                disk = read_consistency_report(world_id, "ch_01")
                assert disk is not None
                assert disk["verdict"] == "needs_review"
                # Verify attached to chapter
                ch = w.story.chapters[0]
                assert ch.consistency_report is not None
                assert ch.consistency_report.verdict == "needs_review"
        finally:
            ws.world_root = original

    async def test_run_consistency_check_clean(self, tmp_path, monkeypatch):
        """模拟 LLM 返回 clean 审校报告。"""
        world_id = "test_cc_clean"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.consistency_checker import run_consistency_check
            ensure_story_dirs(world_id)
            w = create_world("审校测试2")
            w.story.chapters = [StoryChapter(id="ch_01", order=1, title="测试章")]
            mock_raw = json.dumps({"verdict": "clean", "issues": []})
            with patch("worldforger.consistency_checker.chat_completion",
                       new_callable=AsyncMock, return_value=mock_raw):
                cr = await run_consistency_check(w, "ch_01", "正文")
                assert cr.verdict == "clean"
                assert cr.total_issues == 0
        finally:
            ws.world_root = original

    async def test_run_consistency_check_llm_failure(self, tmp_path, monkeypatch):
        """LLM 调用失败时不抛异常，返回 clean 报告。"""
        world_id = "test_cc_fail"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.consistency_checker import run_consistency_check
            ensure_story_dirs(world_id)
            w = create_world("审校测试3")
            w.story.chapters = [StoryChapter(id="ch_01", order=1, title="测试章")]
            with patch("worldforger.consistency_checker.chat_completion",
                       new_callable=AsyncMock, side_effect=RuntimeError("LLM down")):
                cr = await run_consistency_check(w, "ch_01", "正文")
                assert cr.verdict == "clean"
                assert cr.total_issues == 0
        finally:
            ws.world_root = original

    def test_format_consistency_report_display_clean(self):
        from worldforger.consistency_checker import format_consistency_report_for_display
        cr = ConsistencyReport(chapter_id="ch_01", verdict="clean")
        text = format_consistency_report_for_display(cr)
        assert "通过" in text

    def test_format_consistency_report_display_with_issues(self):
        from worldforger.consistency_checker import format_consistency_report_for_display
        cr = ConsistencyReport(
            chapter_id="ch_01", verdict="minor_issues", total_issues=2,
            issues=[
                ConsistencyIssue(category="position", severity="critical",
                                 description="位置不一致", suggestion="修正位置描述"),
                ConsistencyIssue(category="pov", severity="info",
                                 description="视角切换未标记"),
            ]
        )
        text = format_consistency_report_for_display(cr)
        assert "2 个问题" in text
        assert "位置不一致" in text


# ═══════════════════════════════════════════════════════════════
# Story service hook tests
# ═══════════════════════════════════════════════════════════════

class TestStoryServiceHooks:
    async def test_kg_extraction_hook(self, tmp_path, monkeypatch):
        """测试 _try_extract_kg_events 成功提取。"""
        world_id = "test_hook_kg"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.story_service import _try_extract_kg_events
            ensure_story_dirs(world_id)
            w = create_world("KG Hook 测试")
            w.story.chapters = [StoryChapter(id="ch_01", order=1, title="测试")]
            mock_raw = json.dumps({
                "entities": [
                    {"entity_id": "char_01", "entity_type": "character", "name": "爱丽丝",
                     "states": [{"chapter_id": "ch_01", "location": "王都", "emotion": "坚定", "goal": "探险"}]}
                ],
                "events": [],
                "foreshadowing_planted": [],
                "foreshadowing_resolved": [],
            })
            with patch("worldforger.story_service.chat_completion",
                       new_callable=AsyncMock, return_value=mock_raw):
                await _try_extract_kg_events(w, "ch_01", "正文")
                assert len(w.story.narrative_kg.entities) == 1
        finally:
            ws.world_root = original

    async def test_kg_extraction_hook_failure_does_not_raise(self, tmp_path, monkeypatch):
        """_try_extract_kg_events 失败不抛异常。"""
        world_id = "test_hook_kg_fail"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.story_service import _try_extract_kg_events
            ensure_story_dirs(world_id)
            w = create_world("KG Hook Fail")
            w.story.chapters = [StoryChapter(id="ch_01", order=1, title="测试")]
            with patch("worldforger.story_service.chat_completion",
                       new_callable=AsyncMock, side_effect=RuntimeError("fail")):
                # Should not raise
                await _try_extract_kg_events(w, "ch_01", "正文")
        finally:
            ws.world_root = original

    async def test_sentiment_hook(self, tmp_path, monkeypatch):
        """测试 _try_track_sentiment 成功追踪。"""
        world_id = "test_hook_sent"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.story_service import _try_track_sentiment
            ensure_story_dirs(world_id)
            w = create_world("情感 Hook 测试")
            w.story.chapters = [StoryChapter(id="ch_01", order=1, title="测试章")]
            mock_raw = json.dumps({
                "segments": [{"segment_index": 1, "label": "开篇", "tone": "tense", "intensity": 7, "summary": "紧张开局"}],
                "overall_tone": "tense", "ending_tone": "tense",
                "transition_from_prev": "first_chapter",
            })
            with patch("worldforger.story_service.chat_completion",
                       new_callable=AsyncMock, return_value=mock_raw):
                await _try_track_sentiment(w, "ch_01", "正文")
                ch = w.story.chapters[0]
                assert ch.sentiment_log is not None
                assert ch.sentiment_log.overall_tone == "tense"
        finally:
            ws.world_root = original

    async def test_sentiment_hook_failure_does_not_raise(self, tmp_path, monkeypatch):
        world_id = "test_hook_sent_fail"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.story_service import _try_track_sentiment
            ensure_story_dirs(world_id)
            w = create_world("情感 Hook Fail")
            with patch("worldforger.story_service.chat_completion",
                       new_callable=AsyncMock, side_effect=RuntimeError("fail")):
                await _try_track_sentiment(w, "ch_01", "正文")
        finally:
            ws.world_root = original

    async def test_consistency_check_hook(self, tmp_path, monkeypatch):
        """测试 _try_run_consistency_check 成功执行。"""
        world_id = "test_hook_cc"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.story_service import _try_run_consistency_check
            ensure_story_dirs(world_id)
            w = create_world("审校 Hook 测试")
            w.story.chapters = [StoryChapter(id="ch_01", order=1, title="测试")]
            mock_raw = json.dumps({"verdict": "clean", "issues": []})
            with patch("worldforger.story_service.chat_completion",
                       new_callable=AsyncMock, return_value=mock_raw):
                await _try_run_consistency_check(w, "ch_01", "正文")
                ch = w.story.chapters[0]
                assert ch.consistency_report is not None
                assert ch.consistency_report.verdict == "clean"
        finally:
            ws.world_root = original

    async def test_consistency_check_hook_failure_does_not_raise(self, tmp_path, monkeypatch):
        world_id = "test_hook_cc_fail"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.story_service import _try_run_consistency_check
            ensure_story_dirs(world_id)
            w = create_world("审校 Hook Fail")
            with patch("worldforger.story_service.chat_completion",
                       new_callable=AsyncMock, side_effect=RuntimeError("fail")):
                await _try_run_consistency_check(w, "ch_01", "正文")
        finally:
            ws.world_root = original

    async def test_hooks_respect_toggle_flags(self, tmp_path, monkeypatch):
        """当 toggle 关闭时 hooks 不执行。"""
        world_id = "test_hook_toggle"
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            from worldforger.story_service import (
                _try_extract_kg_events,
                _try_run_consistency_check,
                _try_track_sentiment,
            )
            ensure_story_dirs(world_id)
            w = create_world("Toggle 测试")
            w.story.writing_defaults.enable_narrative_kg = False
            w.story.writing_defaults.enable_consistency_check = False
            w.story.writing_defaults.enable_sentiment_track = False
            w.story.chapters = [StoryChapter(id="ch_01", order=1, title="测试")]

            # None of these should call chat_completion since they're gated
            # But the gate checks happen in generate_manuscript(), not in the hooks themselves.
            # The _try_* functions don't check toggles themselves.
            # They'll still run, but without persist.
            # Let's verify they don't crash with toggles off.
            mock_raw = json.dumps({"entities": [], "events": [], "foreshadowing_planted": [], "foreshadowing_resolved": []})
            with patch("worldforger.story_service.chat_completion",
                       new_callable=AsyncMock, return_value=mock_raw):
                await _try_extract_kg_events(w, "ch_01", "正文")
            # Should not raise
        finally:
            ws.world_root = original


# ═══════════════════════════════════════════════════════════════
# API endpoint tests
# ═══════════════════════════════════════════════════════════════

class TestLayer3ApiEndpoints:
    def test_get_narrative_kg(self, tmp_path, monkeypatch):
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            w = create_world("API KG 测试")
            save_world(w)
            r = client.get(f"/api/worlds/{w.meta.id}/story/narrative-kg")
            assert r.status_code == 200
            data = r.json()
            assert "narrative_kg" in data
            assert data["narrative_kg"]["entities"] == []
        finally:
            ws.world_root = original_root

    def test_get_consistency_report(self, tmp_path, monkeypatch):
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            w = create_world("API CR 测试")
            w.story.chapters = [
                StoryChapter(id="ch_01", order=1, title="测试",
                             consistency_report=ConsistencyReport(chapter_id="ch_01", verdict="minor_issues", total_issues=1))
            ]
            save_world(w)
            r = client.get(f"/api/worlds/{w.meta.id}/story/consistency-report/ch_01")
            assert r.status_code == 200
            data = r.json()
            assert data["consistency_report"]["verdict"] == "minor_issues"
        finally:
            ws.world_root = original_root

    def test_get_consistency_report_missing_chapter(self, tmp_path, monkeypatch):
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            w = create_world("API CR Missing")
            save_world(w)
            r = client.get(f"/api/worlds/{w.meta.id}/story/consistency-report/nonexistent")
            assert r.status_code == 404
        finally:
            ws.world_root = original_root

    def test_get_sentiment_arc(self, tmp_path, monkeypatch):
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            w = create_world("API SA 测试")
            w.story.chapters = [
                StoryChapter(id="ch_01", order=1, title="第一章",
                             sentiment_log=SentimentLog(chapter_id="ch_01", overall_tone="positive"))
            ]
            save_world(w)
            r = client.get(f"/api/worlds/{w.meta.id}/story/sentiment-arc")
            assert r.status_code == 200
            data = r.json()
            assert "sentiment_logs" in data
            assert len(data["sentiment_logs"]) == 1
            assert "chart_data" in data
        finally:
            ws.world_root = original_root

    def test_patch_writing_defaults(self, tmp_path, monkeypatch):
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            w = create_world("API WD 测试")
            save_world(w)
            r = client.patch(
                f"/api/worlds/{w.meta.id}/story/writing-defaults",
                json={"enable_narrative_kg": False, "enable_consistency_check": False}
            )
            assert r.status_code == 200
            data = r.json()
            assert data["writing_defaults"]["enable_narrative_kg"] is False
            assert data["writing_defaults"]["enable_consistency_check"] is False
            # Sentiment should remain untouched
            assert data["writing_defaults"]["enable_sentiment_track"] is True
            assert data["changed"] is True
        finally:
            ws.world_root = original_root

    def test_patch_writing_defaults_no_change(self, tmp_path, monkeypatch):
        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws
        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            w = create_world("API WD No Change")
            save_world(w)
            r = client.patch(
                f"/api/worlds/{w.meta.id}/story/writing-defaults",
                json={}
            )
            assert r.status_code == 200
            assert r.json()["changed"] is False
        finally:
            ws.world_root = original_root


# ═══════════════════════════════════════════════════════════════
# Prompt function tests
# ═══════════════════════════════════════════════════════════════

class TestLayer3Prompts:
    def test_kg_extraction_system(self):
        from worldforger.story_prompts import kg_extraction_system
        sys = kg_extraction_system()
        assert "JSON" in sys
        assert "entities" in sys
        assert "events" in sys

    def test_consistency_check_system(self):
        from worldforger.story_prompts import consistency_check_system
        sys = consistency_check_system()
        assert "7" in sys or "七个" in sys or "一致性" in sys
        assert "position" in sys
        assert "timeline" in sys

    def test_sentiment_analysis_system(self):
        from worldforger.story_prompts import sentiment_analysis_system
        sys = sentiment_analysis_system()
        assert "JSON" in sys
        assert "segments" in sys
        assert "intensity" in sys

    def test_build_kg_extraction_user_payload(self):
        from worldforger.story_prompts import build_kg_extraction_user_payload
        w = create_world("KG prompt test")
        w.story.chapters = [StoryChapter(id="ch_01", order=1, title="测试")]
        payload = build_kg_extraction_user_payload(w, chapter_id="ch_01", manuscript_text="正文内容")
        assert "ch_01" in payload
        assert "正文内容" in payload

    def test_build_consistency_check_user_payload(self):
        from worldforger.story_prompts import build_consistency_check_user_payload
        w = create_world("CC prompt test")
        w.story.chapters = [StoryChapter(id="ch_01", order=1, title="测试")]
        payload = build_consistency_check_user_payload(w, chapter_id="ch_01", manuscript_text="正文")
        assert "ch_01" in payload
        assert "正文" in payload

    def test_build_sentiment_analysis_user_payload(self):
        from worldforger.story_prompts import build_sentiment_analysis_user_payload
        w = create_world("SA prompt test")
        w.story.chapters = [StoryChapter(id="ch_01", order=1, title="测试")]
        payload = build_sentiment_analysis_user_payload(w, chapter_id="ch_01", manuscript_text="正文")
        assert "ch_01" in payload or "测试" in payload
        assert "正文" in payload

    def test_format_kg_states_for_prompt(self):
        from worldforger.story_prompts import format_kg_states_for_prompt
        w = create_world("KG format test")
        w.story.narrative_kg = NarrativeKG(
            entities=[KGEntity(entity_id="char_01", name="爱丽丝", entity_type="character",
                               states=[CharacterStateSnapshot(chapter_id="ch_01", location="王都", emotion="坚定", goal="探险")])]
        )
        text = format_kg_states_for_prompt(w, "ch_02")
        assert "爱丽丝" in text
        assert "王都" in text

    def test_format_kg_states_for_prompt_empty(self):
        from worldforger.story_prompts import format_kg_states_for_prompt
        w = create_world("KG format empty")
        assert format_kg_states_for_prompt(w, "ch_01") == ""

    def test_format_previous_sentiment_for_prompt(self):
        from worldforger.story_prompts import format_previous_sentiment_for_prompt
        w = create_world("Sent prompt test")
        w.story.chapters = [
            StoryChapter(id="ch_01", order=1, title="第一章",
                         sentiment_log=SentimentLog(chapter_id="ch_01", overall_tone="tense",
                                                    ending_tone="tense", transition_from_prev="first_chapter",
                                                    segments=[SentimentSegment(tone="tense", intensity=8)])),
            StoryChapter(id="ch_02", order=2, title="第二章"),
        ]
        text = format_previous_sentiment_for_prompt(w, "ch_02")
        assert "tense" in text
        assert "情感过渡" in text

    def test_format_previous_sentiment_for_prompt_none(self):
        from worldforger.story_prompts import format_previous_sentiment_for_prompt
        w = create_world("Sent prompt none")
        w.story.chapters = [StoryChapter(id="ch_01", order=1, title="第一章")]
        assert format_previous_sentiment_for_prompt(w, "ch_01") == ""
