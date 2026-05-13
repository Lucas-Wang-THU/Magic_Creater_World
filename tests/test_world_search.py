import pytest

from worldforger.world_search import search_json_strings, search_world_payload


def test_search_json_finds_nested_string():
    data = {"meta": {"name": "Alpha"}, "geography": {"summary": "Alpha 平原"}}
    hits = search_json_strings(data, "alpha", max_hits=50)
    paths = {h["path"] for h in hits}
    assert "meta.name" in paths
    assert "geography.summary" in paths


def test_search_world_payload_includes_md():
    world = {"meta": {"id": "x", "name": "T"}, "geography": {"summary": "河流"}}
    md = "# T\n\n河流与山\n"
    out = search_world_payload(world, md, "河流")
    assert out["total_json"] >= 1
    assert out["total_md"] >= 1
    assert any("geography" in h["path"] for h in out["json_hits"])
    assert out["markdown_hits"][0]["line"] >= 1


def test_empty_query_raises():
    with pytest.raises(ValueError):
        search_world_payload({}, None, "   ")
