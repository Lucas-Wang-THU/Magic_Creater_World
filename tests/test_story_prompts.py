import pytest

from worldforger.schemas import StoryWritingDefaults, World
from worldforger.story.story_prompts import (
    chapter_beats_system,
    manuscript_system,
    polisher_system,
)
from worldforger.world_store import create_world


def _world_with_toggles(**toggles) -> World:
    w = create_world("prompt-toggle-test")
    for key, value in toggles.items():
        setattr(w.story.writing_defaults, key, value)
    return w


class TestManuscriptPromptToggles:
    def test_default_includes_punctuation_but_not_webnovel_or_panel(self):
        w = _world_with_toggles()
        s = manuscript_system(w, creative_mode="novel", person="third_person_limited")
        assert "中文标点硬规范" in s
        assert "网文爽点与节奏要求" not in s
        assert "人物面板" not in s

    def test_webnovel_enabled_includes_webnovel_block(self):
        w = _world_with_toggles(enable_webnovel_style=True)
        s = manuscript_system(w, creative_mode="novel", person="third_person_limited")
        assert "中文标点硬规范" in s
        assert "网文爽点与节奏要求" in s
        assert "起承转爽" in s
        assert "人物面板" not in s

    def test_panel_enabled_includes_panel_template(self):
        w = _world_with_toggles(enable_panel_template=True)
        s = manuscript_system(w, creative_mode="novel", person="third_person_limited")
        assert "中文标点硬规范" in s
        assert "人物面板" in s
        assert "姓名：{角色名}" in s
        assert "网文爽点与节奏要求" not in s

    def test_both_enabled_includes_all_blocks(self):
        w = _world_with_toggles(enable_webnovel_style=True, enable_panel_template=True)
        s = manuscript_system(w, creative_mode="novel", person="third_person_limited")
        assert "中文标点硬规范" in s
        assert "网文爽点与节奏要求" in s
        assert "人物面板" in s


class TestChapterBeatsPromptToggles:
    def test_default_includes_punctuation_not_webnovel(self):
        w = _world_with_toggles()
        s = chapter_beats_system(w, creative_mode="novel")
        assert "中文标点硬规范" in s
        assert "网文爽点与节奏要求" not in s

    def test_webnovel_enabled_includes_webnovel_block(self):
        w = _world_with_toggles(enable_webnovel_style=True)
        s = chapter_beats_system(w, creative_mode="novel")
        assert "中文标点硬规范" in s
        assert "网文爽点与节奏要求" in s
        assert "起承转爽" in s


class TestPolisherPromptToggles:
    def test_default_does_not_include_webnovel_or_panel_checks(self):
        s = polisher_system()
        assert "网文模式附加检查" not in s
        assert "面板格式附加检查" not in s

    def test_webnovel_flag_includes_webnovel_check(self):
        s = polisher_system(webnovel=True)
        assert "网文模式附加检查" in s
        assert "每章至少 1 个小爽点" in s
        assert "面板格式附加检查" not in s

    def test_panel_flag_includes_panel_check(self):
        s = polisher_system(panel=True)
        assert "面板格式附加检查" in s
        assert "【人物面板】" in s
        assert "网文模式附加检查" not in s

    def test_both_flags_include_both_checks(self):
        s = polisher_system(webnovel=True, panel=True)
        assert "网文模式附加检查" in s
        assert "面板格式附加检查" in s


class TestWritingDefaultsSchema:
    def test_new_toggles_default_to_false(self):
        wd = StoryWritingDefaults()
        assert wd.enable_webnovel_style is False
        assert wd.enable_panel_template is False



class TestWebnovelPanelApi:
    def test_patch_new_writing_defaults_via_api(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient
        from app.main import app

        root = tmp_path / "worlds_root"
        root.mkdir(parents=True, exist_ok=True)
        import worldforger.world_store as ws

        original_root = ws.world_root
        ws.world_root = lambda wid: root / wid
        try:
            w = create_world("API Webnovel Toggle Test")
            from worldforger.world_store import save_world

            save_world(w)
            client = TestClient(app)
            res = client.patch(
                f"/api/worlds/{w.meta.id}/story/writing-defaults",
                json={"enable_webnovel_style": True, "enable_panel_template": True},
            )
            assert res.status_code == 200
            data = res.json()
            assert data["changed"] is True
            assert data["writing_defaults"]["enable_webnovel_style"] is True
            assert data["writing_defaults"]["enable_panel_template"] is True
        finally:
            ws.world_root = original_root
