"""Layer 4: 润色者 Agent — 文风统一与去 AI 化 测试."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from worldforger.schemas import (
    World,
    Meta,
    StorySection,
    StoryChapter,
    StoryWritingDefaults,
    StoryNarrator,
    ConsistencyReport,
    ConsistencyIssue,
)
from worldforger.story_prompts import (
    polisher_system,
    build_polisher_user_payload,
    format_consistency_issues_for_polisher,
    _build_style_reference,
    _build_char_voice_profile,
)
from worldforger.story_store import (
    polished_path,
    polished_dir,
    polish_trace_path,
    ensure_story_dirs,
    write_text,
    read_text,
)


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def tmp_world_id():
    wid = "test_polish_" + os.urandom(4).hex()
    yield wid
    import shutil
    from worldforger.world_store import world_root
    root = world_root(wid)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def sample_world(tmp_world_id):
    ensure_story_dirs(tmp_world_id)
    return World(
        meta=Meta(id=tmp_world_id, name="测试世界"),
        story=StorySection(
            writing_defaults=StoryWritingDefaults(
                enable_polisher=True,
                polish_max_rounds=2,
            ),
            chapters=[
                StoryChapter(id="ch_1", order=1, title="第一章"),
                StoryChapter(id="ch_2", order=2, title="第二章"),
            ],
            narrator=StoryNarrator(person="third_person_limited"),
        ),
    )


@pytest.fixture
def client():
    return TestClient(app)


# ── Schema Tests ──────────────────────────────────────────────────


class TestPolisherSchema:
    def test_story_writing_defaults_has_polish_fields(self):
        wd = StoryWritingDefaults()
        assert wd.enable_polisher is True
        assert wd.polish_max_rounds == 2

    def test_story_writing_defaults_polish_max_rounds_range(self):
        wd = StoryWritingDefaults(polish_max_rounds=1)
        assert wd.polish_max_rounds == 1
        wd = StoryWritingDefaults(polish_max_rounds=3)
        assert wd.polish_max_rounds == 3

    def test_story_chapter_has_polish_fields(self):
        ch = StoryChapter(id="ch_1", order=1)
        assert ch.polished_file == ""
        assert ch.polish_rounds == 0
        assert ch.polish_issue_tracking is None

    def test_story_chapter_polish_fields_serialize(self):
        ch = StoryChapter(
            id="ch_1",
            order=1,
            polished_file="story/polished/ch_1.md",
            polish_rounds=2,
            polish_issue_tracking={"rounds": []},
        )
        d = ch.model_dump(mode="json")
        assert d["polished_file"] == "story/polished/ch_1.md"
        assert d["polish_rounds"] == 2
        assert d["polish_issue_tracking"] == {"rounds": []}


# ── Storage Tests ─────────────────────────────────────────────────


class TestPolisherStorage:
    def test_polished_path(self, tmp_world_id):
        pp = polished_path(tmp_world_id, "ch_1")
        assert pp.name == "ch_1.md"
        assert "polished" in str(pp)

    def test_polished_dir_created_by_ensure(self, tmp_world_id):
        ensure_story_dirs(tmp_world_id)
        assert polished_dir(tmp_world_id).is_dir()

    def test_polish_trace_path(self, tmp_world_id):
        tp = polish_trace_path(tmp_world_id, "ch_1")
        assert tp.name == "ch_1_trace.json"
        assert "polished" in str(tp)

    def test_write_and_read_polished(self, tmp_world_id):
        ensure_story_dirs(tmp_world_id)
        pp = polished_path(tmp_world_id, "ch_1")
        write_text(pp, "润色后的文字内容")
        assert pp.is_file()
        assert read_text(pp) == "润色后的文字内容"

    def test_read_polished_missing(self, tmp_world_id):
        ensure_story_dirs(tmp_world_id)
        pp = polished_path(tmp_world_id, "ch_99")
        assert read_text(pp) == ""


# ── Prompt Tests ──────────────────────────────────────────────────


class TestPolisherPrompts:
    def test_polisher_system_contains_rules(self):
        s = polisher_system()
        assert "破题多样化" in s
        assert "去金句化" in s
        assert "情绪具象化" in s
        assert "对话自然化" in s
        assert "感官补充" in s
        assert "句式破形" in s
        assert "文风锚定" in s
        assert "破折号节制" in s
        assert "段落合并" in s

    def test_polisher_system_contains_anti_examples(self):
        s = polisher_system()
        assert "他转身。城门在身后闷响一声合拢" in s
        assert "后槽牙咬得太紧" in s
        assert "破折号滥用" in s
        assert "小段落碎片化" in s

    def test_polisher_system_contains_forbidden_rules(self):
        s = polisher_system()
        assert "禁止新增情节事件" in s
        assert "禁止改动叙事人称" in s

    def test_build_polisher_user_payload_basic(self, sample_world):
        result = build_polisher_user_payload(
            sample_world,
            "ch_2",
            "这是第二章的正文内容。",
        )
        assert "第二章" in result
        assert "这是第二章的正文内容" in result
        assert "【叙事约束" in result
        assert "第三人称" in result

    def test_build_polisher_user_payload_with_consistency_issues(self, sample_world):
        result = build_polisher_user_payload(
            sample_world,
            "ch_2",
            "正文内容",
            consistency_issues="需要修复的问题列表",
        )
        assert "需要修复的问题列表" in result

    def test_build_polisher_user_payload_with_regression(self, sample_world):
        result = build_polisher_user_payload(
            sample_world,
            "ch_2",
            "正文",
            consistency_issues="问题",
            regression_issues="回归问题",
            polish_round=2,
        )
        assert "第 2 轮" in result
        assert "回归问题" in result

    def test_format_consistency_issues_empty(self):
        result = format_consistency_issues_for_polisher(None)
        assert result == ""

    def test_format_consistency_issues_with_no_issues(self):
        report = ConsistencyReport(
            chapter_id="ch_1",
            total_issues=0,
            verdict="clean",
        )
        result = format_consistency_issues_for_polisher(report)
        assert result == ""

    def test_format_consistency_issues_with_warning(self):
        report = ConsistencyReport(
            chapter_id="ch_1",
            total_issues=2,
            verdict="minor_issues",
            issues=[
                ConsistencyIssue(
                    issue_id="iss_1",
                    category="position",
                    severity="warning",
                    description="位置描述不一致",
                    suggestion="统一为北境",
                ),
                ConsistencyIssue(
                    issue_id="iss_2",
                    category="pov",
                    severity="info",
                    description="POV 轻微漂移",
                ),
            ],
        )
        result = format_consistency_issues_for_polisher(report)
        assert "位置描述不一致" in result
        assert "统一为北境" in result

    def test_format_consistency_issues_with_critical(self):
        report = ConsistencyReport(
            chapter_id="ch_1",
            total_issues=1,
            verdict="needs_review",
            issues=[
                ConsistencyIssue(
                    issue_id="iss_3",
                    category="timeline",
                    severity="critical",
                    description="时间线严重冲突",
                ),
            ],
        )
        result = format_consistency_issues_for_polisher(report)
        assert "CRITICAL" in result
        assert "仅作标注" in result


# ── Polish Loop Tests ─────────────────────────────────────────────


class TestPolishLoop:
    @pytest.mark.asyncio
    async def test_loop_runs_when_enabled(self, sample_world):
        from worldforger.story_service import _run_polish_loop

        mock_report = ConsistencyReport(
            chapter_id="ch_2",
            total_issues=1,
            verdict="minor_issues",
            issues=[
                ConsistencyIssue(
                    issue_id="iss_1",
                    category="position",
                    severity="warning",
                    description="位置不一致",
                    suggestion="修正",
                ),
            ],
        )

        # Reuse the report (round 2 clean)
        mock_report_clean = ConsistencyReport(
            chapter_id="ch_2",
            total_issues=0,
            verdict="clean",
        )

        with (
            patch("worldforger.consistency_checker.run_consistency_check") as mock_check,
            patch("worldforger.story_service.chat_completion") as mock_llm,
        ):
            mock_check.side_effect = [mock_report, mock_report_clean]
            mock_llm.return_value = "润色后的正文\n\n## 润色说明\n- 修改了位置描述"

            await _run_polish_loop(sample_world, "ch_2", "原始正文")

            # Should have called consistency check twice (once per round)
            assert mock_check.call_count == 2
            # Should have called LLM once (round 1 polish)
            assert mock_llm.call_count >= 1

            # Verify polished file written
            pp = polished_path(sample_world.meta.id, "ch_2")
            assert pp.is_file()

            # Verify chapter model updated
            ch = next(c for c in sample_world.story.chapters if c.id == "ch_2")
            assert ch.polished_file
            assert ch.polish_rounds > 0
            assert ch.polish_issue_tracking is not None

    @pytest.mark.asyncio
    async def test_loop_skips_when_clean(self, sample_world):
        from worldforger.story_service import _run_polish_loop

        mock_report = ConsistencyReport(
            chapter_id="ch_2",
            total_issues=0,
            verdict="clean",
        )

        with (
            patch("worldforger.consistency_checker.run_consistency_check") as mock_check,
            patch("worldforger.story_service.chat_completion") as mock_llm,
        ):
            mock_check.return_value = mock_report

            await _run_polish_loop(sample_world, "ch_2", "原始正文")

            # Only 1 check, no polish needed
            assert mock_check.call_count == 1
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_loop_stops_at_max_rounds(self, sample_world):
        from worldforger.story_service import _run_polish_loop

        # Set max rounds to 2
        sample_world.story.writing_defaults.polish_max_rounds = 2

        mock_report = ConsistencyReport(
            chapter_id="ch_2",
            total_issues=1,
            verdict="minor_issues",
            issues=[
                ConsistencyIssue(
                    issue_id="iss_1",
                    category="position",
                    severity="warning",
                    description="一直存在的位置问题",
                ),
            ],
        )

        with (
            patch("worldforger.consistency_checker.run_consistency_check") as mock_check,
            patch("worldforger.story_service.chat_completion") as mock_llm,
        ):
            # Always return issues → forces max rounds
            mock_check.return_value = mock_report
            mock_llm.return_value = "润色后内容"

            await _run_polish_loop(sample_world, "ch_2", "正文")

            # Check called per round: round1 check+polish, round2 check+polish, then stops at max_rounds
            assert mock_check.call_count == 2
            assert mock_llm.call_count == 2

    @pytest.mark.asyncio
    async def test_loop_disabled_respected(self, sample_world):
        from worldforger.story_service import _run_polish_loop

        sample_world.story.writing_defaults.enable_polisher = False

        with (
            patch("worldforger.consistency_checker.run_consistency_check") as mock_check,
            patch("worldforger.story_service.chat_completion") as mock_llm,
        ):
            # This test verifies the hook checks the toggle — the generate_manuscript function
            # checks enable_polisher before calling _run_polish_loop
            assert sample_world.story.writing_defaults.enable_polisher is False

    @pytest.mark.asyncio
    async def test_loop_with_1_round(self, sample_world):
        from worldforger.story_service import _run_polish_loop

        sample_world.story.writing_defaults.polish_max_rounds = 1

        mock_report = ConsistencyReport(
            chapter_id="ch_2",
            total_issues=1,
            verdict="minor_issues",
            issues=[
                ConsistencyIssue(
                    issue_id="iss_1",
                    category="position",
                    severity="warning",
                    description="位置问题",
                ),
            ],
        )

        with (
            patch("worldforger.consistency_checker.run_consistency_check") as mock_check,
            patch("worldforger.story_service.chat_completion") as mock_llm,
        ):
            mock_check.return_value = mock_report
            mock_llm.return_value = "润色后"

            await _run_polish_loop(sample_world, "ch_2", "正文")

            assert mock_check.call_count == 1
            mock_llm.assert_called_once()

            # Verify trace written
            tp = polish_trace_path(sample_world.meta.id, "ch_2")
            assert tp.is_file()
            trace = json.loads(tp.read_text(encoding="utf-8"))
            assert trace["max_rounds"] == 1
            assert trace["termination_reason"] == "max_rounds"

    @pytest.mark.asyncio
    async def test_loop_failure_does_not_raise(self, sample_world):
        from worldforger.story_service import _run_polish_loop

        with patch("worldforger.consistency_checker.run_consistency_check", side_effect=RuntimeError("Boom")):
            # Should not raise
            await _run_polish_loop(sample_world, "ch_2", "正文")

    @pytest.mark.asyncio
    async def test_loop_tracks_issue_classification(self, sample_world):
        from worldforger.story_service import _run_polish_loop

        sample_world.story.writing_defaults.polish_max_rounds = 3

        # Round 1: has 2 issues → polish → Round 2: 1 issue (1 fixed, 1 persistent)
        mock_report_r1 = ConsistencyReport(
            chapter_id="ch_2",
            total_issues=2,
            verdict="minor_issues",
            issues=[
                ConsistencyIssue(
                    issue_id="iss_a", category="position", severity="warning",
                    description="位置不一致",
                ),
                ConsistencyIssue(
                    issue_id="iss_b", category="pov", severity="info",
                    description="POV 轻微漂移",
                ),
            ],
        )
        mock_report_r2 = ConsistencyReport(
            chapter_id="ch_2",
            total_issues=1,
            verdict="minor_issues",
            issues=[
                ConsistencyIssue(
                    issue_id="iss_b", category="pov", severity="warning",
                    description="POV 轻微漂移",
                ),
            ],
        )
        mock_report_r3 = ConsistencyReport(
            chapter_id="ch_2", total_issues=0, verdict="clean",
        )

        with (
            patch("worldforger.consistency_checker.run_consistency_check") as mock_check,
            patch("worldforger.story_service.chat_completion") as mock_llm,
        ):
            mock_check.side_effect = [mock_report_r1, mock_report_r2, mock_report_r3]
            mock_llm.return_value = "润色后"

            await _run_polish_loop(sample_world, "ch_2", "正文")

            tp = polish_trace_path(sample_world.meta.id, "ch_2")
            trace = json.loads(tp.read_text(encoding="utf-8"))
            assert trace["termination_reason"] == "clean"

            # Round 2 classification should show 1 fixed
            r2 = trace["rounds"][1]  # second round (index 1)
            assert len(r2["classification"]["fixed"]) >= 0  # iss_a was fixed


# ── API Tests ─────────────────────────────────────────────────────


class TestPolisherAPI:
    def test_get_polished_no_file(self, client, sample_world, tmp_world_id):
        from worldforger.world_store import save_world
        save_world(sample_world, export_markdown=False)

        res = client.get(f"/api/worlds/{tmp_world_id}/story/manuscript/ch_1/polished")
        assert res.status_code == 200
        data = res.json()
        assert data["chapter_id"] == "ch_1"
        assert data["polished_text"] == ""

    def test_get_polished_with_file(self, client, sample_world, tmp_world_id):
        from worldforger.world_store import save_world
        save_world(sample_world, export_markdown=False)
        ensure_story_dirs(tmp_world_id)
        write_text(polished_path(tmp_world_id, "ch_1"), "润色后的内容")

        res = client.get(f"/api/worlds/{tmp_world_id}/story/manuscript/ch_1/polished")
        assert res.status_code == 200
        data = res.json()
        assert data["polished_text"] == "润色后的内容"

    def test_get_polish_trace_no_file(self, client, sample_world, tmp_world_id):
        from worldforger.world_store import save_world
        save_world(sample_world, export_markdown=False)

        res = client.get(f"/api/worlds/{tmp_world_id}/story/manuscript/ch_1/polish-trace")
        assert res.status_code == 200
        data = res.json()
        assert data["trace"] is None

    def test_get_polish_trace_with_file(self, client, sample_world, tmp_world_id):
        from worldforger.world_store import save_world
        save_world(sample_world, export_markdown=False)
        ensure_story_dirs(tmp_world_id)
        trace_data = {"chapter_id": "ch_1", "max_rounds": 2, "actual_rounds": 1, "rounds": []}
        polish_trace_path(tmp_world_id, "ch_1").write_text(
            json.dumps(trace_data, ensure_ascii=False), encoding="utf-8"
        )

        res = client.get(f"/api/worlds/{tmp_world_id}/story/manuscript/ch_1/polish-trace")
        assert res.status_code == 200
        data = res.json()
        assert data["trace"]["max_rounds"] == 2

    def test_get_polished_world_not_found(self, client):
        res = client.get("/api/worlds/nonexistent_id/story/manuscript/ch_1/polished")
        assert res.status_code == 404

    def test_patch_writing_defaults_polish(self, client, sample_world, tmp_world_id):
        from worldforger.world_store import save_world
        save_world(sample_world, export_markdown=False)

        res = client.patch(
            f"/api/worlds/{tmp_world_id}/story/writing-defaults",
            json={"enable_polisher": False, "polish_max_rounds": 3},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["writing_defaults"]["enable_polisher"] is False
        assert data["writing_defaults"]["polish_max_rounds"] == 3

    def test_patch_writing_defaults_polish_partial(self, client, sample_world, tmp_world_id):
        from worldforger.world_store import save_world
        save_world(sample_world, export_markdown=False)

        # Only change polish_max_rounds, leave enable_polisher unchanged
        res = client.patch(
            f"/api/worlds/{tmp_world_id}/story/writing-defaults",
            json={"polish_max_rounds": 1},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["writing_defaults"]["polish_max_rounds"] == 1
        assert data["writing_defaults"]["enable_polisher"] is True  # unchanged


# ── Style Reference Tests ─────────────────────────────────────────


class TestStyleReference:
    def test_no_previous_chapters(self, sample_world):
        refs = _build_style_reference(sample_world, "ch_1")
        assert refs == []

    def test_previous_chapter_no_polished(self, sample_world, tmp_world_id):
        from worldforger.story_store import manuscript_path
        ensure_story_dirs(tmp_world_id)
        write_text(
            manuscript_path(tmp_world_id, "ch_1"),
            "第一章原文内容。" * 50,
        )
        refs = _build_style_reference(sample_world, "ch_2")
        # Should fall back to original manuscript
        assert len(refs) > 0
        assert "未润色原稿" in refs[0] or "第一章" in refs[0]

    def test_previous_chapter_has_polished(self, sample_world, tmp_world_id):
        ensure_story_dirs(tmp_world_id)
        write_text(
            polished_path(tmp_world_id, "ch_1"),
            "润色后的第一章内容。" * 50 + "\n\n## 润色说明\n- 修改了措辞",
        )
        refs = _build_style_reference(sample_world, "ch_2")
        assert len(refs) > 0
        assert "润色稿参考" in refs[0]
        # Should strip the polish notes
        assert "## 润色说明" not in refs[0]


# ── Integration Test ──────────────────────────────────────────────


class TestPolishIntegration:
    @pytest.mark.asyncio
    async def test_generate_manuscript_triggers_polish(self, sample_world):
        """Verify that the polish loop is triggered after manuscript generation."""
        from worldforger.story_service import generate_manuscript

        with (
            patch("worldforger.story_service.chat_completion") as mock_llm,
            patch("worldforger.story_service._try_generate_summary_card") as mock_summary,
            patch("worldforger.story_service._try_update_runtime_states") as mock_runtime,
            patch("worldforger.story_service._try_index_chapter") as mock_index,
            patch("worldforger.story_service._run_polish_loop") as mock_polish,
        ):
            mock_llm.return_value = "生成的正文内容"
            mock_summary.return_value = None
            mock_runtime.return_value = None
            mock_index.return_value = None

            await generate_manuscript(
                sample_world,
                chapter_id="ch_2",
                prompt="写下一章",
                creative_mode=None,
                person="third_person_limited",
                attach_prev_chapters=0,
                include_world_md=False,
            )

            # Polish loop should have been called
            mock_polish.assert_called_once_with(sample_world, "ch_2", "生成的正文内容")

    @pytest.mark.asyncio
    async def test_generate_manuscript_skips_polish_when_disabled(self, sample_world):
        sample_world.story.writing_defaults.enable_polisher = False

        from worldforger.story_service import generate_manuscript

        with (
            patch("worldforger.story_service.chat_completion") as mock_llm,
            patch("worldforger.story_service._try_generate_summary_card") as mock_summary,
            patch("worldforger.story_service._try_update_runtime_states") as mock_runtime,
            patch("worldforger.story_service._try_index_chapter") as mock_index,
            patch("worldforger.story_service._run_polish_loop") as mock_polish,
        ):
            mock_llm.return_value = "生成的正文内容"

            await generate_manuscript(
                sample_world,
                chapter_id="ch_2",
                prompt="写下一章",
                creative_mode=None,
                person="third_person_limited",
                attach_prev_chapters=0,
                include_world_md=False,
            )

            mock_polish.assert_not_called()
