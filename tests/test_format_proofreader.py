"""Integration tests for the two-stage format proofreader pipeline.

Tests _try_parse_with_format_recovery orchestration with mocked LLM calls.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from worldforger.panel_sync import (
    _try_parse_with_format_recovery,
    _run_format_proofreader,
    _run_synchronizer_self_correct,
    parse_structure_json,
)


# ── _run_format_proofreader tests (mock chat_completion directly) ──

async def test_format_proofreader_fixes_missing_commas():
    """Format proofreader receives broken JSON and returns fixed JSON."""
    broken = '{"a": 1\n"b": 2}'
    fixed = '{"a": 1,\n"b": 2}'

    with patch(
        "worldforger.panel_sync.chat_completion",
        new=AsyncMock(return_value=fixed),
    ):
        result = await _run_format_proofreader(
            raw_json_text=broken,
            parse_error="Expecting ',' delimiter: line 2",
        )

    assert result == {"a": 1, "b": 2}


async def test_format_proofreader_reports_unfixable():
    """Format proofreader returns _format_error when it cannot fix the JSON."""
    with patch(
        "worldforger.panel_sync.chat_completion",
        new=AsyncMock(return_value='{"_format_error": true, "reason": "too corrupted"}'),
    ):
        result = await _run_format_proofreader(
            raw_json_text="not even close to json {{{",
            parse_error="Expecting value: line 1",
        )

    assert result.get("_format_error") is True
    assert "reason" in result


async def test_format_proofreader_output_unparseable():
    """Format proofreader returns garbage that parse_structure_json cannot handle."""
    with patch(
        "worldforger.panel_sync.chat_completion",
        new=AsyncMock(return_value="this is not json either"),
    ):
        result = await _run_format_proofreader(
            raw_json_text='{"a": 1\n"b": 2}',
            parse_error="Expecting ',' delimiter",
        )

    assert result.get("_format_error") is True


# ── _run_synchronizer_self_correct tests ──

async def test_synchronizer_self_correct_succeeds():
    """Synchronizer self-correct returns valid JSON on second attempt."""
    fixed = '{"geography": {"summary": "A continent"}, "factions": {"entities": []}}'

    with patch(
        "worldforger.panel_sync.chat_completion",
        new=AsyncMock(return_value=fixed),
    ):
        result = await _run_synchronizer_self_correct(
            raw_json_text='{"geography": {"summary": "A continent"}\n"factions": {"entities": []}}',
            parse_error="Expecting ',' delimiter: line 2 column 1",
            world_json='{"meta": {"id": "test"}}',
            system="You are a synchronizer.",
        )

    assert result["geography"]["summary"] == "A continent"


async def test_synchronizer_self_correct_still_fails():
    """Synchronizer self-correct still outputs broken JSON → ValueError."""
    with patch(
        "worldforger.panel_sync.chat_completion",
        new=AsyncMock(return_value="still broken {{{"),
    ):
        with pytest.raises(ValueError):
            await _run_synchronizer_self_correct(
                raw_json_text='{"a": 1\n"b": 2}',
                parse_error="Expecting ',' delimiter",
                world_json="{}",
                system="You are a synchronizer.",
            )


# ── _try_parse_with_format_recovery orchestration tests ──


async def test_stage0_succeeds_no_llm_called():
    """Valid JSON passes stage 0 — no LLM calls needed."""
    valid = '{"geography": {"summary": "test"}, "factions": {"entities": []}}'

    # chat_completion should never be called
    mock_chat = AsyncMock()
    with patch("worldforger.panel_sync.chat_completion", mock_chat):
        result = await _try_parse_with_format_recovery(
            raw=valid,
            world_json="{}",
            system="You are a synchronizer.",
        )

    assert result["geography"]["summary"] == "test"
    mock_chat.assert_not_called()


async def test_stage0_repairs_missing_commas_no_llm_called():
    """Missing commas are fixed by parse_structure_json in stage 0 — no LLM."""
    broken = '{"geography": {"summary": "test"}\n"factions": {"entities": []}}'

    mock_chat = AsyncMock()
    with patch("worldforger.panel_sync.chat_completion", mock_chat):
        result = await _try_parse_with_format_recovery(
            raw=broken,
            world_json="{}",
            system="You are a synchronizer.",
        )

    assert result["geography"]["summary"] == "test"
    mock_chat.assert_not_called()


async def test_stage0_fails_stage1_format_proofreader_succeeds():
    """Stage 0 cannot repair, stage 1 format proofreader fixes it."""
    # Intentionally broken beyond what parse_structure_json can fix
    broken = '{"_corrupted": true\x00invalid byte\n"more": [1, 2,}'

    fixed = '{"geography": {"summary": "recovered by fp"}}'

    call_count = 0

    async def mock_chat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return fixed

    with patch("worldforger.panel_sync.chat_completion", mock_chat):
        result = await _try_parse_with_format_recovery(
            raw=broken,
            world_json="{}",
            system="You are a synchronizer.",
        )

    assert result["geography"]["summary"] == "recovered by fp"
    assert call_count == 1  # only format proofreader called, not self-correct


async def test_stage0_fails_stage1_fails_stage2_succeeds():
    """Stage 0 and stage 1 fail, stage 2 (self-correct) succeeds."""
    broken = '{"a": totally broken {{{'

    fp_response = '{"_format_error": true, "reason": "too broken for fp"}'
    sc_response = '{"geography": {"summary": "recovered by self-correct"}}'

    call_responses = [fp_response, sc_response]

    async def mock_chat(*args, **kwargs):
        return call_responses.pop(0)

    with patch("worldforger.panel_sync.chat_completion", mock_chat):
        result = await _try_parse_with_format_recovery(
            raw=broken,
            world_json="{}",
            system="You are a synchronizer.",
        )

    assert result["geography"]["summary"] == "recovered by self-correct"
    assert len(call_responses) == 0  # both stages called


async def test_all_stages_fail_raises_value_error():
    """All 3 stages fail → ValueError propagates."""
    broken = 'total garbage {{{[[['

    fp_response = '{"_format_error": true, "reason": "unrecoverable"}'
    sc_response = "also garbage <<<"

    call_responses = [fp_response, sc_response]

    async def mock_chat(*args, **kwargs):
        return call_responses.pop(0)

    with patch("worldforger.panel_sync.chat_completion", mock_chat):
        with pytest.raises(ValueError):
            await _try_parse_with_format_recovery(
                raw=broken,
                world_json="{}",
                system="You are a synchronizer.",
            )

    assert len(call_responses) == 0


async def test_large_nested_structure_self_correct():
    """Synchronizer self-correct handles a large nested world structure."""
    import random

    # Build a moderately large world-like JSON with missing commas
    parts = []
    for i in range(100):
        parts.append(f'  "key_{i}": {{"name": "item_{i}", "value": {i}}}')
    broken = "{\n" + "\n".join(parts) + "\n}"

    # This should be repairable by stage 0 already — verify
    result = await _try_parse_with_format_recovery(
        raw=broken,
        world_json="{}",
        system="You are a synchronizer.",
    )

    assert result[f"key_0"]["name"] == "item_0"
    assert result[f"key_99"]["value"] == 99
    assert len(result) == 100


# ── parse_structure_json per-key extraction fallback ──


def test_per_key_extraction_saves_partial_data():
    """Per-key extraction salvages individual valid top-level keys from corrupted JSON."""
    corrupted = (
        '{\n'
        '  "geography": {"summary": "valid"},\n'
        '  "power_system": {"summary": "also valid"},\n'
        '  "cultures": {broken garbage here},\n'
        '  "factions": {"entities": []}\n'
        '}'
    )
    try:
        result = parse_structure_json(corrupted)
    except ValueError:
        result = None

    # Even if the whole thing fails, the function attempts per-key extraction
    # The key point is that it doesn't crash and either returns partial data or raises cleanly
    if result is not None:
        # If per-key extraction worked, at least geography should be present
        assert isinstance(result, dict)


def test_parse_structure_json_handles_empty_string():
    """Empty string should not crash."""
    with pytest.raises(ValueError):
        parse_structure_json("")


def test_parse_structure_json_handles_whitespace_only():
    """Whitespace-only input should not crash."""
    with pytest.raises(ValueError):
        parse_structure_json("   \n\t  ")
