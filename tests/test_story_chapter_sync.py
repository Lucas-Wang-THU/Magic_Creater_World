from worldforger.schemas import StoryChapter
from worldforger.story.story_chapter_sync import (
    outline_chapters_from_markdown,
    reconcile_macro_outline_chapters,
    reconcile_story_chapters,
    strip_chapter_title_prefix,
    title_from_beat_markdown,
)
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


def test_outline_chapter_parser_supports_chinese_and_session_headings():
    content = """
## 第一章：雾中来客
### 第十二章 旧城终局
- 第2次跑团会话：裂隙入口
"""
    assert outline_chapters_from_markdown(content) == [
        (1, "雾中来客"),
        (2, "裂隙入口"),
        (12, "旧城终局"),
    ]


def test_strip_chapter_title_prefix_removes_duplicate_chapter_label_and_bad_separator():
    assert strip_chapter_title_prefix("第一章：雾中来客", fallback_order=1) == "雾中来客"
    assert strip_chapter_title_prefix("第1章 合：雾中来客", fallback_order=1) == "雾中来客"
    assert strip_chapter_title_prefix("Chapter 2 - Old City", fallback_order=2) == "Old City"


def test_outline_chapter_parser_strips_bad_he_separator_after_chapter_label():
    assert outline_chapters_from_markdown("## 第一章合：雾中来客\n") == [(1, "雾中来客")]


def test_outline_chapter_parser_supports_markdown_table_rows():
    content = """
| 章号 | 标题 | 核心事件 | 钩子 |
|------|------|----------|------|
| 1 | 「规则第一条：观众不得离席」 | 沈厌进入剧院。 | 主持人低语。 |
| 第2章 | 空椅子上的名字 | 发现何铭座位。 | 何铭还活着。 |
"""
    assert outline_chapters_from_markdown(content) == [
        (1, "「规则第一条：观众不得离席」"),
        (2, "空椅子上的名字"),
    ]


def test_outline_chapter_parser_respects_declared_chapter_count():
    content = """
# 第一卷：剧院规则 · 粗纲（2章）

| 章号 | 标题 | 核心事件 |
|------|------|----------|
| 1 | 开局 | 事件 |
| 2 | 破局 | 事件 |
| 3 | 第二卷误入 | 事件 |
"""
    assert outline_chapters_from_markdown(content) == [(1, "开局"), (2, "破局")]


def test_macro_outline_title_change_reuses_existing_chapter_id():
    w = create_world("粗纲精确覆盖")
    original = StoryChapter(id="ch_keep", order=1, title="旧标题", word_count=1800)
    w.story.chapters.append(original)

    w2, notes = reconcile_macro_outline_chapters(w, "## 第一章：新标题\n")

    assert len(w2.story.chapters) == 1
    assert w2.story.chapters[0].id == "ch_keep"
    assert w2.story.chapters[0].title == "新标题"
    assert w2.story.chapters[0].word_count == 1800
    assert any("沿用 ch_keep" in note for note in notes)


def test_repeated_macro_outline_sync_does_not_duplicate_chapters():
    w = create_world("粗纲重复同步")
    w, first_notes = reconcile_macro_outline_chapters(
        w,
        "## 第一章：启程\n## 第二章：抵达\n",
    )
    ids = [chapter.id for chapter in w.story.chapters]

    w, second_notes = reconcile_macro_outline_chapters(
        w,
        "## 第一章：启程修订\n## 第二章：抵达修订\n",
    )

    assert len(w.story.chapters) == 2
    assert [chapter.id for chapter in w.story.chapters] == ids
    assert [chapter.title for chapter in w.story.chapters] == ["启程修订", "抵达修订"]
    assert len(first_notes) == 2
    assert len(second_notes) == 2
