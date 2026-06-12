"""RAG 向量索引 —— 单元测试与集成测试。

embedding 部分通过 mock 避免网络依赖（HuggingFace 不可用），
ChromaDB 本地操作、分块、格式化等仍做真实验证。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from worldforger.world_store import create_world, save_world
import worldforger.chapter_indexer as _ci_mod

_DIM = 512
_REAL_GET_LOCAL_MODEL = _ci_mod._get_local_model


def _fixed_vector(text: str) -> list[float]:
    """用固定随机种子生成伪 embedding，返回 list。"""
    rng = np.random.RandomState(hash(text) & 0xFFFFFFFF)
    v = rng.randn(_DIM).astype(np.float32)
    v = v / (np.linalg.norm(v) + 1e-8)
    return v.tolist()


# Patch the module-level embedding functions
_mock_embed_texts = MagicMock()
_mock_embed_texts.side_effect = lambda texts: [_fixed_vector(t) for t in texts]

_mock_embed_query = MagicMock()
_mock_embed_query.side_effect = lambda q: _fixed_vector(q) if q.strip() else []

_mock_model = MagicMock()
_mock_model.encode = MagicMock()
_mock_model.encode.side_effect = lambda texts, normalize_embeddings=True: \
    np.array([_fixed_vector(t) for t in (texts if isinstance(texts, list) else [texts])])
_mock_model.get_sentence_embedding_dimension = MagicMock(return_value=_DIM)


@pytest.fixture(autouse=True)
def mock_embedding(monkeypatch):
    """所有测试自动 mock SentenceTransformer 和 API embedding。"""
    import worldforger.chapter_indexer as ci

    monkeypatch.setattr(ci, "_use_api_fallback", False)
    monkeypatch.setattr(ci, "_embed_texts", _mock_embed_texts)
    monkeypatch.setattr(ci, "_embed_query_text", _mock_embed_query)
    monkeypatch.setattr(ci, "_embedding_dim", _DIM)
    monkeypatch.setattr(ci, "_get_local_model", MagicMock(return_value=_mock_model))
    yield


@pytest.fixture
def world():
    """创建一个测试用世界并落盘。"""
    w = create_world("RAG测试世界")
    save_world(w)
    return w


@pytest.fixture
def indexer(world):
    from worldforger.chapter_indexer import ChapterIndexer

    idx = ChapterIndexer(world.meta.id)
    idx.clear_all()
    yield idx, world
    idx.clear_all()


# ── chunking tests ──


def test_auto_skips_hf_when_model_not_cached(monkeypatch):
    monkeypatch.setattr(_ci_mod, "_get_local_model", _REAL_GET_LOCAL_MODEL)
    monkeypatch.setattr(_ci_mod, "_model", None)
    monkeypatch.setenv("MCW_EMBEDDING_BACKEND", "auto")
    monkeypatch.setattr(_ci_mod, "_model_cached", lambda _name: False)
    with pytest.raises(RuntimeError, match="跳过 HuggingFace"):
        _REAL_GET_LOCAL_MODEL()


def test_api_backend_skips_local_download(monkeypatch):
    monkeypatch.setenv("MCW_EMBEDDING_BACKEND", "api")
    assert _ci_mod._should_skip_local_download() is True


def test_chunk_text_empty():
    from worldforger.chapter_indexer import ChapterIndexer

    assert ChapterIndexer._chunk_text("") == []
    assert ChapterIndexer._chunk_text("   \n\n  ") == []


def test_chunk_text_single_paragraph():
    from worldforger.chapter_indexer import ChapterIndexer

    text = "这是一段测试文本。"
    chunks = ChapterIndexer._chunk_text(text)
    assert len(chunks) == 1
    assert "测试" in chunks[0]


def test_chunk_text_multiple_paragraphs():
    from worldforger.chapter_indexer import ChapterIndexer

    text = "第一段。\n\n第二段。\n\n第三段。"
    chunks = ChapterIndexer._chunk_text(text)
    assert len(chunks) == 1
    assert "第一段" in chunks[0]


def test_chunk_text_long_splits():
    from worldforger.chapter_indexer import ChapterIndexer

    para = "这是一个很长的段落。" * 50
    text = para + "\n\n" + para
    chunks = ChapterIndexer._chunk_text(text, max_chars=600)
    assert len(chunks) >= 1


def test_chunk_text_preserves_boundaries():
    from worldforger.chapter_indexer import ChapterIndexer

    text = "第一节场景描述。" * 30 + "\n\n" + "第二节场景描述。" * 30
    chunks = ChapterIndexer._chunk_text(text, max_chars=250)
    assert len(chunks) >= 2


def test_scene_chunks_respect_explicit_scene_boundaries():
    from worldforger.chapter_indexer import ChapterIndexer

    text = (
        "## 场景一：城门\n"
        "李铁站在城门下，听见北风穿过旗杆。\n\n"
        "守军低声谈论昨夜的火光。\n\n"
        "## 场景二：烽塔\n"
        "王素瑶登上烽塔，看见远处陌生旗帜。\n\n"
        "她把信纸压进袖口。"
    )
    chunks = ChapterIndexer._scene_chunks(text)
    assert len(chunks) == 2
    assert chunks[0]["unit_type"] == "scene"
    assert "场景一" in chunks[0]["text"]
    assert "场景二" in chunks[1]["text"]
    assert all(c["boundary"] == "explicit" for c in chunks)


def test_scene_chunks_merge_paragraphs_into_long_units():
    from worldforger.chapter_indexer import ChapterIndexer

    paras = [f"第{i}段。" + "叙事内容。" * 24 for i in range(14)]
    text = "\n\n".join(paras)
    chunks = ChapterIndexer._scene_chunks(text, target_chars=900, max_chars=1200)
    assert 1 < len(chunks) < len(paras)
    assert all(c["chars"] <= 1200 for c in chunks)
    assert any(c["boundary"] == "paragraph_group" for c in chunks)


# ── format functions ──


def test_format_rag_chunks_empty():
    from worldforger.story.story_prompts import format_rag_chunks

    assert format_rag_chunks([]) == ""


def test_format_rag_chunks_manuscript():
    from worldforger.story.story_prompts import format_rag_chunks

    chunks = [
        {
            "chunk_id": "ch_x_0",
            "document": "测试内容",
            "metadata": {
                "source_type": "manuscript",
                "chapter_order": 3,
                "chapter_title": "测试章",
            },
            "distance": 0.2,
        }
    ]
    result = format_rag_chunks(chunks)
    assert "测试章" in result
    assert "测试内容" in result
    assert "片段 1" in result


def test_format_rag_chunks_character():
    from worldforger.story.story_prompts import format_rag_chunks

    chunks = [
        {
            "chunk_id": "char_x_0",
            "document": "角色描述",
            "metadata": {"source_type": "character", "character_name": "张三"},
            "distance": 0.3,
        }
    ]
    result = format_rag_chunks(chunks)
    assert "人物卡" in result
    assert "张三" in result


def test_format_rag_chunks_world_md():
    from worldforger.story.story_prompts import format_rag_chunks

    chunks = [
        {
            "chunk_id": "wb_x_0",
            "document": "世界观设定内容",
            "metadata": {"source_type": "world_md", "section": "地理"},
            "distance": 0.15,
        }
    ]
    result = format_rag_chunks(chunks)
    assert "世界观设定" in result
    assert "地理" in result


def test_format_rag_chunks_truncates_long():
    from worldforger.story.story_prompts import format_rag_chunks

    long_text = "长文本" * 400
    chunks = [
        {
            "chunk_id": "x",
            "document": long_text,
            "metadata": {"source_type": "manuscript", "chapter_order": 1, "chapter_title": "T"},
            "distance": 0.1,
        }
    ]
    result = format_rag_chunks(chunks)
    assert "已截断" in result or len(result) < len(long_text) + 200


def test_format_rag_chunks_keeps_complete_scene_longer():
    from worldforger.story.story_prompts import format_rag_chunks

    long_scene = "完整场景内容。" * 150
    chunks = [
        {
            "chunk_id": "scene_ch_1_0",
            "document": long_scene,
            "metadata": {
                "source_type": "manuscript",
                "unit_type": "scene",
                "chapter_order": 2,
                "chapter_title": "烽火",
                "scene_index": 1,
            },
            "distance": 0.1,
        }
    ]
    result = format_rag_chunks(chunks)
    assert "完整场景" in result
    assert "scene#1" in result
    assert "已截断" not in result
    assert len(result) > 900


# ── book summary ──


def test_build_book_summary_has_structure(world):
    from worldforger.story.story_prompts import build_book_summary

    summary = build_book_summary(world)
    assert "RAG测试世界" in summary
    assert len(summary) > 0


# ── rag_index_dir / book_summary_path ──


def test_rag_index_dir(world):
    from worldforger.story.story_store import rag_index_dir

    d = rag_index_dir(world.meta.id)
    assert d.name == "rag_index"


def test_book_summary_path(world):
    from worldforger.story.story_store import book_summary_path

    p = book_summary_path(world.meta.id)
    assert p.name == "book_summary.json"


# ── ChapterIndexer integration tests ──


def test_index_and_retrieve_chapter(indexer):
    idx, w = indexer
    text = (
        "北境的寒风吹过长城垛口。李铁站在城墙上，望着远处连绵的雪山。\n\n"
        "「将军，探子回来了。」副将张维快步走来，铠甲上覆着一层薄霜。\n\n"
        "李铁没有回头，只是沉声问道：「可有什么发现？」\n\n"
        "「北方部落正在集结，看规模，至少三千人。」张维的声音里透着紧张。\n\n"
        "李铁终于转过身，眼中闪过一丝忧虑。自从父亲战死沙场，他就知道这一天迟早会来。"
    )
    n = idx.index_chapter("ch_test01", text, {"chapter_order": 1, "chapter_title": "北境风云"})
    assert n >= 1

    stats = idx.get_stats()
    assert stats["total_chunks"] >= 1
    assert "ch_test01" in stats["chapter_ids"]

    results = idx.retrieve("将军在北境巡视长城", top_k=2)
    assert len(results) >= 1


def test_index_and_retrieve_characters(indexer):
    idx, w = indexer
    chars = [
        {
            "id": "char_001",
            "name": "李铁",
            "cast_role": "主角",
            "runtime_state": {
                "current_location": "北境·长城",
                "current_goal": "抵御北方部落入侵",
                "emotional_state": "坚毅但忧虑",
            },
            "notes": "青年将领，继承父亲遗志守卫边疆。",
        },
        {
            "id": "char_002",
            "name": "王素瑶",
            "cast_role": "女主角",
            "runtime_state": {
                "current_location": "京城·王府",
                "current_goal": "调查父亲被冤案真相",
                "emotional_state": "谨慎而决心坚定",
            },
            "notes": "丞相之女，暗中习武。",
        },
    ]
    n = idx.index_characters(chars)
    assert n >= 1

    results = idx.retrieve("守卫边疆的将领", top_k=2, source_types=["character"])
    assert len(results) >= 1


def test_index_world_md(indexer):
    idx, w = indexer
    md = (
        "## 世界观概述\n这个世界由三个大陆组成。\n\n"
        "## 北境大陆\n北境常年冰雪覆盖，资源匮乏，居民以游牧为生。\n\n"
        "## 中原大陆\n中原沃土千里，七国争雄，战乱不休。\n\n"
        "## 南疆大陆\n南疆密林遍布，以部落联盟形式存在，崇尚巫蛊之术。"
    )
    n = idx.index_world_md(md)
    assert n >= 1

    results = idx.retrieve("北方冰雪覆盖的地区", top_k=2, source_types=["world_md"])
    assert len(results) >= 1


def test_remove_chapter(indexer):
    idx, w = indexer
    text = "测试内容，用于删除测试。" * 20
    idx.index_chapter("ch_rm_test", text, {"chapter_order": 1, "chapter_title": "待删除章"})
    stats_before = idx.get_stats()
    assert "ch_rm_test" in stats_before.get("chapter_ids", [])

    n = idx.remove_chapter("ch_rm_test")
    assert n >= 1

    stats_after = idx.get_stats()
    assert "ch_rm_test" not in stats_after.get("chapter_ids", [])


def test_exclude_chapter_id(indexer):
    idx, w = indexer
    text_a = "北境长城守卫军的故事，李铁将军坐镇边疆。" * 5
    text_b = "京城王府中的阴谋，王素瑶暗中调查真相。" * 5
    idx.index_chapter("ch_a", text_a, {"chapter_order": 1, "chapter_title": "北境"})
    idx.index_chapter("ch_b", text_b, {"chapter_order": 2, "chapter_title": "京城"})

    results = idx.retrieve("将军守卫边疆", top_k=3, exclude_chapter_id="ch_a")
    for r in results:
        cid = r.get("metadata", {})
        if isinstance(cid, dict):
            assert cid.get("chapter_id") != "ch_a"


def test_get_stats(indexer):
    idx, w = indexer
    idx.clear_all()
    idx.index_chapter("ch_s1", "统计测试数据。" * 30, {"chapter_order": 1, "chapter_title": "S1"})
    idx.index_chapter("ch_s2", "更多统计测试。" * 30, {"chapter_order": 2, "chapter_title": "S2"})

    stats = idx.get_stats()
    assert stats["total_chunks"] >= 2
    assert stats["indexed_chapters"] >= 2
    assert "ch_s1" in stats["chapter_ids"]
    assert "ch_s2" in stats["chapter_ids"]
    assert stats["unit_counts"].get("scene", 0) >= 2


def test_index_chapter_records_scene_metadata(indexer):
    idx, w = indexer
    idx.clear_all()
    text = (
        "## 场景一\n北境长城守卫军发现异动。\n\n"
        "## 场景二\n李铁将军召集斥候，命他们追查陌生旗帜。"
    )
    n = idx.index_chapter("ch_scene_meta", text, {"chapter_order": 4, "chapter_title": "边声"})
    assert n == 2
    got = idx._collection.get(where={"chapter_id": "ch_scene_meta"}, include=["metadatas", "documents"])
    metas = got.get("metadatas", [])
    docs = got.get("documents", [])
    assert len(metas) == 2
    assert all(m.get("unit_type") == "scene" for m in metas)
    assert all(m.get("scene_boundary") == "explicit" for m in metas)
    assert any("李铁将军" in d for d in docs)


def test_retrieve_for_chapter_debug_reports_longrag(indexer):
    idx, w = indexer
    idx.clear_all()
    idx.index_chapter("ch_debug_a", "北境长城守卫军发现陌生旗帜。" * 20, {"chapter_order": 1, "chapter_title": "北境"})
    report = idx.retrieve_for_chapter_debug("ch_target", beat_text="李铁追查陌生旗帜", top_k=2)
    assert report["strategy"] == "scene_longrag"
    assert report["top_k"] == 2
    assert report["result_count"] >= 1
    assert any(r["unit_type"] == "scene" for r in report["results"])


def test_clear_all(indexer):
    idx, w = indexer
    idx.index_chapter("ch_clr", "清除测试。" * 20, {"chapter_order": 1, "chapter_title": "待清除"})
    assert idx.get_stats()["total_chunks"] >= 1

    idx.clear_all()
    assert idx.get_stats()["total_chunks"] == 0


# ── layered context integration ──


def test_build_manuscript_user_payload_with_rag(world):
    from worldforger.story.story_prompts import build_manuscript_user_payload
    from worldforger.story.story_service import add_chapter

    ch = add_chapter(world, title="测试章")

    rag_chunks = [
        {
            "chunk_id": "ch_old_0",
            "document": "前情片段：李铁在长城发现北方部落异动。",
            "metadata": {
                "source_type": "manuscript",
                "chapter_order": 1,
                "chapter_title": "长城风云",
            },
            "distance": 0.2,
        }
    ]
    result = build_manuscript_user_payload(
        world,
        chapter_id=ch.id,
        macro_outline="粗纲测试内容",
        beat_text="本章细纲：李铁率军迎战。",
        prev_manuscripts=[],
        user_hint="写得精彩一些",
        include_world_md=False,
        rag_chunks=rag_chunks,
    )
    assert "前情检索" in result
    assert "前情片段" in result
    assert "长城风云" in result


def test_build_manuscript_user_payload_without_rag(world):
    from worldforger.story.story_prompts import build_manuscript_user_payload
    from worldforger.story.story_service import add_chapter

    ch = add_chapter(world, title="测试章")

    result = build_manuscript_user_payload(
        world,
        chapter_id=ch.id,
        macro_outline="",
        beat_text="",
        prev_manuscripts=[],
        user_hint="",
        include_world_md=False,
        rag_chunks=None,
    )
    assert "世界设定摘要" in result
    assert "测试章" in result


def test_manuscript_context_assembler_keeps_hard_and_reports_soft_budget():
    from worldforger.story.story_prompts import (
        ManuscriptContextBlock,
        assemble_manuscript_context,
    )

    blocks = [
        ManuscriptContextBlock("硬规则", "HARD_RULE_" * 80, "hard", hard=True),
        ManuscriptContextBlock("工作层", "WORKING_" * 200, "working", priority=10, min_chars=120),
        ManuscriptContextBlock("归档层", "ARCHIVE_" * 200, "archival", priority=1, min_chars=120),
        ManuscriptContextBlock("输出", "START_WRITING", "hard", hard=True),
    ]

    payload, report = assemble_manuscript_context(
        blocks,
        soft_budget=350,
        tier_budgets={"working": 220, "chapter": 0, "archival": 120, "optional": 0},
    )

    assert "HARD_RULE_" in payload
    assert payload.endswith("START_WRITING")
    assert report["hard_chars"] > 0
    assert report["soft_chars"] <= 350
    assert report["truncated"] or report["dropped"]


def test_build_manuscript_context_debug_uses_summary_instead_of_prev_raw(world):
    from worldforger.story.story_prompts import build_manuscript_context_debug
    from worldforger.story.story_service import add_chapter
    from worldforger.story.story_store import write_summary_card

    prev = add_chapter(world, title="旧章")
    current = add_chapter(world, title="新章")
    raw_prev = "RAW_SECRET_SHOULD_NOT_LEAK " * 200 + "上一章末尾。"
    write_summary_card(world.meta.id, prev.id, {
        "chapter_id": prev.id,
        "title": prev.title,
        "main_events": "摘要事件：李铁发现北境异动。",
        "ending_hook": "城门外出现陌生旗帜。",
    })

    payload, report = build_manuscript_context_debug(
        world,
        chapter_id=current.id,
        macro_outline="",
        beat_text="李铁迎战。",
        prev_manuscripts=[(prev.id, raw_prev)],
        user_hint="",
        include_world_md=False,
        rag_chunks=None,
    )

    assert "Chapter Memory / 前文摘要" in payload
    assert "摘要事件：李铁发现北境异动" in payload
    assert "RAW_SECRET_SHOULD_NOT_LEAK" not in payload
    assert any(item["title"] == "前文摘要" for item in report["included"])


def test_character_extraction_from_beat(world):
    from worldforger.story.story_service import _extract_character_ids_from_beat

    world.characters.entities = [
        {"id": "char_hero", "name": "李白", "cast_role": "主角"},
        {"id": "char_villain", "name": "曹操", "cast_role": "反派"},
    ]
    ids = _extract_character_ids_from_beat(world, "李白在京城遇到曹操，两人展开一场激战。")
    assert "char_hero" in ids
    assert "char_villain" in ids


def test_foreshadowing_extraction(world):
    from worldforger.story.story_service import _extract_foreshadowing_ids
    from worldforger.schemas import StoryForeshadowing

    world.story.foreshadowing = [
        StoryForeshadowing(id="fs_001", label="隐藏的宝藏", planted_chapter_id="ch_test", payoff_chapter_id="ch_test", status="open"),
        StoryForeshadowing(id="fs_002", label="叛徒的身份", planted_chapter_id="ch_other", payoff_chapter_id="ch_test", status="open"),
        StoryForeshadowing(id="fs_003", label="无关伏笔", planted_chapter_id="ch_other", payoff_chapter_id="ch_other", status="open"),
    ]
    ids = _extract_foreshadowing_ids(world, "ch_test")
    assert "fs_001" in ids
    assert "fs_002" in ids
    assert "fs_003" not in ids


# ── remove_chapter cleans up RAG index ──


def test_remove_chapter_cleans_rag_index(world):
    from worldforger.chapter_indexer import ChapterIndexer
    from worldforger.story.story_service import add_chapter, remove_chapter

    ch = add_chapter(world, title="待删除章")
    assert ch.id

    idx = ChapterIndexer(world.meta.id)
    idx.clear_all()
    idx.index_chapter(ch.id, "测试内容用于删除。" * 30, {"chapter_order": ch.order, "chapter_title": ch.title})
    assert idx.get_stats()["indexed_chapters"] >= 1

    result = remove_chapter(world, ch.id)
    assert result is True

    stats = idx.get_stats()
    assert ch.id not in stats.get("chapter_ids", [])


# ── _slug helper ──


def test_slug():
    from worldforger.chapter_indexer import _slug

    assert _slug("Hello World") == "Hello_World"
    assert _slug("中文测试") == ""
    assert _slug("test!@#name") == "test_name"
    assert len(_slug("a" * 60)) <= 40


# ── RAG stats API endpoint ──


def test_rag_stats_endpoint_empty(world):
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.get(f"/api/worlds/{world.meta.id}/story/rag/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["ready"] is False
    assert data["total_chunks"] == 0


def test_rag_stats_endpoint_ready(world):
    from fastapi.testclient import TestClient
    from app.main import app
    from worldforger.chapter_indexer import ChapterIndexer

    idx = ChapterIndexer(world.meta.id)
    idx.clear_all()
    idx.index_chapter("ch_test", "测试内容用于 RAG stats 端点。" * 30, {"chapter_order": 1, "chapter_title": "测试"})

    client = TestClient(app)
    r = client.get(f"/api/worlds/{world.meta.id}/story/rag/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["ready"] is True
    assert data["total_chunks"] >= 1
    assert data["indexed_chapters"] >= 1
    assert "ch_test" in data["chapter_ids"]
    assert "source_counts" in data
