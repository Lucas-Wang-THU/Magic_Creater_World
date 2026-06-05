"""Tests for JSON repair functions used by the structure sync pipeline."""
from worldforger.sync.panel_sync import (
    parse_structure_json,
)


def test_standard_json():
    r = parse_structure_json('{"a": 1}')
    assert r == {"a": 1}


def test_trailing_commas():
    r = parse_structure_json('{"a": 1, "b": [1, 2, 3,], "c": {"d": 4,},}')
    assert r == {"a": 1, "b": [1, 2, 3], "c": {"d": 4}}


def test_missing_comma_between_keys():
    r = parse_structure_json('{\n  "a": 1\n  "b": 2\n}')
    assert r == {"a": 1, "b": 2}


def test_missing_comma_after_nested_object():
    r = parse_structure_json('{\n  "a": {"x": 1}\n  "b": 2\n}')
    assert r == {"a": {"x": 1}, "b": 2}


def test_line_comments():
    r = parse_structure_json(
        '{\n  "a": 1,\n  // this is a comment\n  "b": 2\n}'
    )
    assert r == {"a": 1, "b": 2}


def test_complex_nested_missing_commas():
    r = parse_structure_json(
        '{\n'
        '  "power_system": {\n'
        '    "summary": "test"\n'
        '    "tiers": [\n'
        '      {"name": "A" "description": "First"}\n'
        '      {"name": "B" "description": "Second"}\n'
        '    ]\n'
        '  }\n'
        '}'
    )
    assert r["power_system"]["tiers"][0]["name"] == "A"
    assert len(r["power_system"]["tiers"]) == 2


def test_extra_text_around_json():
    r = parse_structure_json(
        "Some text before.\n"
        '{"geography": {"summary": "A continent"}, "power_system": {"tiers": [{"name": "L1"}]}}\n'
        "Some text after."
    )
    assert r["geography"]["summary"] == "A continent"
    assert r["power_system"]["tiers"][0]["name"] == "L1"


def test_llm_code_fence():
    r = parse_structure_json('```json\n{"a": 1}\n```')
    assert r == {"a": 1}


def test_missing_comma_with_true_false_null():
    r = parse_structure_json(
        '{\n  "a": true\n  "b": false\n  "c": null\n  "d": 42\n}'
    )
    assert r == {"a": True, "b": False, "c": None, "d": 42}
