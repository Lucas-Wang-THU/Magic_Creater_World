# -*- coding: utf-8 -*-
"""Tests for C3 JSON repair and C2 semantic incremental merge."""

import json
import pytest
from worldforger.sync.panel_sync import _normalize_json_punctuation, parse_structure_json
from worldforger.sync.panel_merge import merge_section_conservative, _merge_array_by_name_or_append


# ═══════════════════════════════════════════════════════════════════
# C3: JSON punctuation normalization tests
# ═══════════════════════════════════════════════════════════════════

class TestJSONPunctuationNormalize:
    def test_chinese_comma_to_ascii(self):
        raw = '{"name": "云鹤"，"age": 20}'
        fixed = _normalize_json_punctuation(raw)
        assert "，" not in fixed
        assert "," in fixed

    def test_chinese_colon_to_ascii(self):
        raw = '{"name"："云鹤"}'
        fixed = _normalize_json_punctuation(raw)
        assert "：" not in fixed
        assert ":" in fixed

    def test_mixed_punctuation(self):
        raw = '{"name"："测试角色"，"id"："ch_001"，"tagline"："一段描述"}'
        fixed = _normalize_json_punctuation(raw)
        # After normalization, should be valid JSON
        data = json.loads(fixed)
        assert data["name"] == "测试角色"
        assert data["id"] == "ch_001"

    def test_no_change_needed(self):
        raw = '{"name": "test", "id": "abc"}'
        fixed = _normalize_json_punctuation(raw)
        assert fixed == raw

    def test_parse_with_chinese_punctuation(self):
        """parse_structure_json should handle Chinese punctuation in JSON."""
        raw = '{"summary"："测试概述"，"regions"：[{"id"："r1"，"name"："区域一"}]}'
        result = parse_structure_json(raw)
        assert result["summary"] == "测试概述"
        assert result["regions"][0]["name"] == "区域一"

    def test_parse_with_code_fence_and_chinese(self):
        raw = '```json\n{"name"："测试"，"value"：123}\n```'
        result = parse_structure_json(raw)
        assert result["name"] == "测试"
        assert result["value"] == 123

    def test_chinese_brackets(self):
        raw = '{"items"：["a"，"b"，"c"]}'
        fixed = _normalize_json_punctuation(raw)
        data = json.loads(fixed)
        assert data["items"] == ["a", "b", "c"]


# ═══════════════════════════════════════════════════════════════════
# C2: Semantic incremental merge tests
# ═══════════════════════════════════════════════════════════════════

class TestMergeByTierName:
    def test_match_by_tier_name(self):
        """Items with tier_name should match by tier_name."""
        base = [
            {"tier_name": "拓雾者", "professions": [{"id": "p1", "name": "幸存者"}]},
            {"tier_name": "凝痕者", "professions": []},
        ]
        patch = [
            {"tier_name": "拓雾者", "professions": [{"id": "p2", "name": "矿难初觉者"}]},
        ]
        merged = _merge_array_by_name_or_append(base, patch)
        assert len(merged) == 2  # should not add duplicate tier
        t1 = next(t for t in merged if t["tier_name"] == "拓雾者")
        assert len(t1["professions"]) == 2  # p1 kept, p2 added
        assert any(p["id"] == "p1" for p in t1["professions"])
        assert any(p["id"] == "p2" for p in t1["professions"])

    def test_match_by_name_fallback(self):
        """Items with name (not tier_name) should match by name."""
        base = [
            {"name": "东极神州", "summary": "大陆"},
            {"name": "西极陆洲", "summary": "另一大陆"},
        ]
        patch = [
            {"name": "东极神州", "summary": "最大陆块，中国文化圈核心"},
        ]
        merged = _merge_array_by_name_or_append(base, patch)
        assert len(merged) == 2
        r1 = next(r for r in merged if r["name"] == "东极神州")
        assert "最大陆块" in r1["summary"]

    def test_new_item_appended(self):
        """Unmatched items should be appended, not overwrite."""
        base = [{"tier_name": "拓雾者", "professions": []}]
        patch = [{"tier_name": "凝痕者", "professions": [{"id": "p_new", "name": "新职业"}]}]
        merged = _merge_array_by_name_or_append(base, patch)
        assert len(merged) == 2
        assert any(t["tier_name"] == "凝痕者" for t in merged)

    def test_empty_patch_preserves_base(self):
        """Empty patch should not clear base data."""
        base = [{"tier_name": "拓雾者", "professions": [{"id": "p1"}]}]
        patch = []
        merged = _merge_array_by_name_or_append(base, patch)
        assert len(merged) == 1
        assert merged[0]["tier_name"] == "拓雾者"


class TestMergeSectionConservative:
    def test_empty_string_does_not_overwrite(self):
        """Patch empty string should not overwrite base non-empty string."""
        base = {"summary": "完整的概述文本"}
        patch = {"summary": ""}
        merged = merge_section_conservative(base, patch)
        assert merged["summary"] == "完整的概述文本"

    def test_empty_list_does_not_overwrite(self):
        """Patch empty list should not overwrite base non-empty list."""
        base = {"tiers": [{"name": "拓雾者"}]}
        patch = {"tiers": []}
        merged = merge_section_conservative(base, patch)
        assert len(merged["tiers"]) == 1

    def test_nested_dict_merge(self):
        """Nested dicts should merge recursively."""
        base = {
            "profession_system": {
                "summary": "原有概述",
                "by_tier": [{"tier_name": "拓雾者", "professions": []}],
            }
        }
        patch = {
            "profession_system": {
                "design_notes": "新增设计说明",
                "by_tier": [{"tier_name": "凝痕者", "professions": []}],
            }
        }
        merged = merge_section_conservative(base, patch)
        assert merged["profession_system"]["summary"] == "原有概述"  # preserved
        assert merged["profession_system"]["design_notes"] == "新增设计说明"  # added
        assert len(merged["profession_system"]["by_tier"]) == 2  # both tiers

    def test_profession_upsert_in_tier(self):
        """Adding a profession to an existing tier should merge, not replace."""
        base = {
            "profession_system": {
                "by_tier": [
                    {"tier_name": "拓雾者", "professions": [
                        {"id": "p1", "name": "幸存者"}
                    ]},
                ],
            }
        }
        patch = {
            "profession_system": {
                "by_tier": [
                    {"tier_name": "拓雾者", "professions": [
                        {"id": "p2", "name": "矿难初觉者"}
                    ]},
                ],
            }
        }
        merged = merge_section_conservative(base, patch)
        t1 = merged["profession_system"]["by_tier"][0]
        prof_ids = [p["id"] for p in t1["professions"]]
        assert "p1" in prof_ids  # original preserved
        assert "p2" in prof_ids  # new added


# ═══════════════════════════════════════════════════════════════════
# C3: Auto-close JSON tests
# ═══════════════════════════════════════════════════════════════════

class TestAutoCloseJSON:
    def test_parse_truncated_json_salvage(self):
        """Truncated JSON should be salvageable via auto-close."""
        from worldforger.sync.panel_sync import _salvage_partial_json
        raw = '{"summary": "test", "items": [{"id": "a", "name": "A"}'
        result = _salvage_partial_json(raw)
        assert "summary" in result
        assert result["summary"] == "test"

    def test_parse_with_trailing_comma(self):
        """JSON with trailing comma should parse successfully."""
        raw = '{"name": "test", "items": [1, 2, 3,],}'
        result = parse_structure_json(raw)
        assert result["name"] == "test"
        assert result["items"] == [1, 2, 3]


# ═══════════════════════════════════════════════════════════════════
# C1: Chunked sync protocol tests
# ═══════════════════════════════════════════════════════════════════

class TestChunkedSync:
    def test_no_chunks_falls_through(self):
        """Normal JSON without markers should parse normally."""
        from worldforger.sync.panel_sync import _parse_chunked
        raw = '{"summary": "test", "tiers": [{"name": "拓雾者"}]}'
        result = _parse_chunked(raw)
        assert result is None  # Should return None, caller falls through

    def test_two_tier_chunks(self):
        """Two tier chunks should merge into power_system.tiers."""
        from worldforger.sync.panel_sync import _parse_chunked
        raw = (
            '@@POWER_TIER:拓雾者@@\n'
            '{"name": "拓雾者", "description": "初识迷雾", "typical_capabilities": ["感知雾蚀"]}\n'
            '@@POWER_TIER:凝痕者@@\n'
            '{"name": "凝痕者", "description": "刻痕仪式", "typical_capabilities": ["凝痕态"]}'
        )
        result = _parse_chunked(raw)
        assert result is not None
        assert "power_system" in result
        tiers = result["power_system"]["tiers"]
        assert len(tiers) == 2
        assert tiers[0]["name"] == "拓雾者"
        assert tiers[1]["name"] == "凝痕者"

    def test_single_chunk_returns_none(self):
        """Single chunk should fall through to normal parsing."""
        from worldforger.sync.panel_sync import _parse_chunked
        raw = '@@TIER:拓雾者@@ {"name": "拓雾者"}'
        result = _parse_chunked(raw)
        assert result is None  # Only 1 chunk, use normal parsing

    def test_profession_chunk(self):
        """Profession chunks should merge into profession_system.by_tier."""
        from worldforger.sync.panel_sync import _parse_chunked
        raw = (
            '@@PROFESSION:拓雾者@@\n'
            '{"tier_name": "拓雾者", "professions": [{"id": "p1", "name": "幸存者"}]}\n'
            '@@PROFESSION:凝痕者@@\n'
            '{"tier_name": "凝痕者", "professions": [{"id": "p2", "name": "塑痕兵"}]}'
        )
        result = _parse_chunked(raw)
        assert result is not None
        by_tier = result["power_system"]["profession_system"]["by_tier"]
        assert len(by_tier) == 2

    def test_partial_failure_recovery(self):
        """One bad chunk should not block other chunks."""
        from worldforger.sync.panel_sync import _parse_chunked
        raw = (
            '@@TIER_GOOD:拓雾者@@\n'
            '{"name": "拓雾者", "description": "ok"}\n'
            '@@TIER_BAD:broken@@\n'
            '{this is not valid json}\n'
            '@@TIER_GOOD2:凝痕者@@\n'
            '{"name": "凝痕者", "description": "also ok"}'
        )
        result = _parse_chunked(raw)
        assert result is not None
        tiers = result["power_system"]["tiers"]
        assert len(tiers) == 2  # Both good chunks merged

    def test_full_parse_with_chunks(self):
        """parse_structure_json should detect chunks automatically."""
        from worldforger.sync.panel_sync import parse_structure_json
        raw = (
            '@@T1:拓雾者@@\n{"name": "拓雾者", "description": "test", "typical_capabilities": []}\n'
            '@@T2:凝痕者@@\n{"name": "凝痕者", "description": "test2", "typical_capabilities": []}'
        )
        result = parse_structure_json(raw)
        assert result is not None
        assert "power_system" in result

    def test_chunked_merge_preserves_existing(self):
        """Chunked merge should not overwrite existing chunks with same name."""
        from worldforger.sync.panel_sync import _chunked_merge
        # First chunk
        base = {}
        c1 = {"name": "拓雾者", "description": "first version", "typical_capabilities": ["感知"]}
        base = _chunked_merge(base, c1, "T1")
        # Second chunk with same name
        c2 = {"name": "拓雾者", "description": "updated version", "limitations": ["不稳定"]}
        base = _chunked_merge(base, c2, "T2")
        tiers = base["power_system"]["tiers"]
        assert len(tiers) == 1  # Not duplicated
        assert tiers[0]["description"] == "updated version"  # Updated
        assert tiers[0]["typical_capabilities"] == ["感知"]  # Preserved
        assert tiers[0]["limitations"] == ["不稳定"]  # Added


# ═══════════════════════════════════════════════════════════════════
# Skill node reconcile: move nodes between general and subclass trees
# ═══════════════════════════════════════════════════════════════════

class TestReconcileSkillNodes:
    def test_move_node_from_general_to_subclass(self):
        """If a node appears in subclass tree, it should be removed from general tree."""
        from worldforger.sync.panel_merge import reconcile_power_system_skill_nodes
        data = {
            "power_system": {
                "tiers": [{
                    "name": "塑脉师",
                    "skill_tree": [
                        {"id": "sk_001", "name": "深读态"},
                        {"id": "sk_002", "name": "塑脉抽取"},
                    ],
                    "subclass_paths": [{
                        "id": "vein_resonator",
                        "skill_tree": [
                            {"id": "sk_001", "name": "深读态（更新版）"},
                        ],
                    }],
                }],
            },
        }
        result = reconcile_power_system_skill_nodes(data)
        tier = result["power_system"]["tiers"][0]
        # sk_001 should be removed from general (it's in subclass now)
        general_ids = [n["id"] for n in tier["skill_tree"]]
        assert "sk_001" not in general_ids
        assert "sk_002" in general_ids  # Not in subclass, stays

    def test_node_stays_if_not_in_subclass(self):
        """Node in general tree that's NOT in any subclass should stay."""
        from worldforger.sync.panel_merge import reconcile_power_system_skill_nodes
        data = {
            "power_system": {
                "tiers": [{
                    "name": "拓雾者",
                    "skill_tree": [{"id": "sk_gen", "name": "通用技能"}],
                    "subclass_paths": [],
                }],
            },
        }
        result = reconcile_power_system_skill_nodes(data)
        tier = result["power_system"]["tiers"][0]
        assert len(tier["skill_tree"]) == 1  # unchanged

    def test_no_tiers_no_crash(self):
        """Empty power_system should not crash."""
        from worldforger.sync.panel_merge import reconcile_power_system_skill_nodes
        result = reconcile_power_system_skill_nodes({"power_system": {}})
        assert result is not None

    def test_merge_then_reconcile(self):
        """Full merge + reconcile: patch moves a node to subclass, base keeps both."""
        from worldforger.sync.panel_merge import merge_section_conservative, reconcile_power_system_skill_nodes
        base = {
            "power_system": {
                "tiers": [{
                    "name": "塑脉师",
                    "skill_tree": [
                        {"id": "sk_001", "name": "深读态"},
                        {"id": "sk_002", "name": "塑脉抽取"},
                    ],
                    "subclass_paths": [{
                        "id": "vein_resonator",
                        "skill_tree": [],
                    }],
                }],
            },
        }
        patch = {
            "power_system": {
                "tiers": [{
                    "name": "塑脉师",
                    "skill_tree": [],  # patch wants them empty here
                    "subclass_paths": [{
                        "id": "vein_resonator",
                        "skill_tree": [
                            {"id": "sk_001", "name": "深读态（移至子流派）"},
                        ],
                    }],
                }],
            },
        }
        merged = merge_section_conservative(base, patch)
        # Before reconcile: sk_001 exists in BOTH general and subclass
        tier = merged["power_system"]["tiers"][0]
        assert any(n["id"] == "sk_001" for n in tier.get("skill_tree", [])), "should be in general before reconcile"
        # After reconcile: sk_001 only in subclass
        reconciled = reconcile_power_system_skill_nodes(merged)
        tier_r = reconciled["power_system"]["tiers"][0]
        general_ids = [n["id"] for n in tier_r.get("skill_tree", [])]
        subclass_ids = [n["id"] for n in tier_r["subclass_paths"][0].get("skill_tree", [])]
        assert "sk_001" not in general_ids, "sk_001 should be removed from general"
        assert "sk_001" in subclass_ids, "sk_001 should be in subclass"
