from worldforger.schemas import StoryChapter
from worldforger.story.story_chapter_sync import reconcile_story_chapters, title_from_beat_markdown
from worldforger.story.story_store import beat_path, write_text
from worldforger.world_store import create_world


def test_title_from_beat_markdown():
    assert title_from_beat_markdown("# 跑团会话2\n\n正文") == "跑团会话2"
    assert title_from_beat_markdown("无标题") == ""


def test_reconcile_fills_empty_title_from_beat():
    w = create_world("同步章名")
    wid = w.meta.id
    ch = StoryChapter(id="ch_sync", order=1, title="")
    w.story.chapters.append(ch)
    write_text(beat_path(wid, "ch_sync"), "# 新章名\n\n细纲内容")
    w2, notes = reconcile_story_chapters(w)
    assert any("新章名" in n for n in notes)
    assert w2.story.chapters[0].title == "新章名"

def test_reconcile_preserves_existing_title():
    w = create_world("保留章名")
    wid = w.meta.id
    ch = StoryChapter(id="ch_sync2", order=1, title="用户起的名字")
    w.story.chapters.append(ch)
    write_text(beat_path(wid, "ch_sync2"), "# 自动提取的名字\n\n细纲内容")
    w2, notes = reconcile_story_chapters(w)
    assert w2.story.chapters[0].title == "用户起的名字"  # Should NOT be overwritten
