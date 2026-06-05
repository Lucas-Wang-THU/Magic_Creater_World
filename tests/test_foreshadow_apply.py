from worldforger.story.foreshadow_apply import (
    apply_foreshadow_operations,
    parse_story_foreshadow_blocks,
)
from worldforger.schemas import StoryChapter, StoryForeshadowing
from worldforger.story.story_chat_artifacts import auto_apply_story_artifacts_from_reply
from worldforger.world_store import create_world


def test_apply_foreshadow_upsert_and_resolve():
    w = create_world("伏笔测试")
    ch = StoryChapter(id="ch_test01", order=1, title="第一章")
    w.story.chapters.append(ch)
    w, applied, warnings = apply_foreshadow_operations(
        w,
        [
            {
                "op": "upsert",
                "id": "fs_a",
                "label": "神秘信件",
                "planted_chapter_id": "ch_test01",
                "status": "open",
            },
            {"op": "resolve", "id": "fs_a", "payoff_chapter_id": "ch_test01"},
        ],
    )
    assert not warnings
    assert len(applied) >= 2
    fs = next(f for f in w.story.foreshadowing if f.id == "fs_a")
    assert fs.status == "resolved"
    assert fs.label == "神秘信件"


def test_parse_story_foreshadow_blocks():
    text = """说明
```story-foreshadow
[{"op": "upsert", "id": "fs_b", "label": "剑"}]
```
"""
    ops = parse_story_foreshadow_blocks(text)
    assert len(ops) == 1
    assert ops[0]["id"] == "fs_b"


def test_auto_apply_manuscript_block():
    w = create_world("自动文稿")
    ch = StoryChapter(id="ch_auto", order=1, title="章")
    w.story.chapters.append(ch)
    reply = "```story-manuscript:ch_auto\n正文一段。\n```"
    w2, applied, warnings = auto_apply_story_artifacts_from_reply(w, reply)
    assert not warnings
    assert any("文稿" in a for a in applied)
    assert w2.story.chapters[0].status == "drafting"
