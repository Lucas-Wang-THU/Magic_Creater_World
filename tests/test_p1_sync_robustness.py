"""P1: 同步鲁棒性回归测试 —— 各模块 normalize 边界覆盖、情节 save/load 无损、scope 全覆盖。"""

import json

import pytest

from worldforger.schemas import (
    StoryChapter,
    StoryForeshadowing,
    World,
)
from worldforger.world_store import create_world, load_world, save_world


# ═══════════════════════════════════════════════════════════════════════════
# 1. 文化/宗教同步回归测试
# ═══════════════════════════════════════════════════════════════════════════


class TestCulturesNormalize:
    def test_entities_single_dict_wrapped_to_array(self):
        from worldforger.structure_normalize import _normalize_cultures_dict

        result = _normalize_cultures_dict({"entities": {"id": "cu_a", "name": "龙裔文化"}})
        ents = result.get("entities", [])
        assert isinstance(ents, list)
        assert len(ents) == 1
        assert ents[0]["id"] == "cu_a"

    def test_traditions_fallback_when_entities_missing(self):
        from worldforger.structure_normalize import _normalize_cultures_dict

        result = _normalize_cultures_dict(
            {"traditions": [{"id": "tr_x", "name": "冬至祭"}]}
        )
        ents = result.get("entities", [])
        assert len(ents) == 1
        assert ents[0]["id"] == "tr_x"

    def test_non_dict_non_list_entities_stripped(self):
        from worldforger.structure_normalize import _normalize_cultures_dict

        # string entities → 不是 list，返回空（无 entities 键）
        result = _normalize_cultures_dict({"summary": "X", "entities": "not_a_list"})
        assert "entities" not in result
        assert result["summary"] == "X"

    def test_summary_preserved(self):
        from worldforger.structure_normalize import _normalize_cultures_dict

        result = _normalize_cultures_dict({"summary": "文化总览"})
        assert result["summary"] == "文化总览"
        assert "entities" not in result

    def test_kind_maps_chinese_heuristics(self):
        from worldforger.structure_normalize import _normalize_culture_entity

        # 教/神 → religion
        r1 = _normalize_culture_entity({"id": "r1", "name": "圣教", "kind": "宗教"})
        assert r1["kind"] == "religion"
        # 混/融合 → syncretic
        r2 = _normalize_culture_entity({"id": "c1", "name": "融合教", "kind": "混合型"})
        assert r2["kind"] == "syncretic"
        # default → culture
        r3 = _normalize_culture_entity({"id": "x1", "name": "部落", "kind": "tribe"})
        assert r3["kind"] == "culture"

    def test_entity_missing_id_returns_none(self):
        from worldforger.structure_normalize import _normalize_culture_entity

        assert _normalize_culture_entity({"name": "无名"}) is None
        assert _normalize_culture_entity({"id": "  "}) is None

    def test_sacred_sites_from_string_split_by_newline(self):
        from worldforger.structure_normalize import _normalize_culture_entity

        r = _normalize_culture_entity(
            {"id": "s1", "name": "圣地文化", "sacred_sites": "圣殿\n祭坛\n神木"}
        )
        assert r["sacred_sites"] == ["圣殿", "祭坛", "神木"]

    def test_relations_none_empty_dict_wrap(self):
        from worldforger.structure_normalize import _normalize_culture_relations

        assert _normalize_culture_relations(None) == []
        assert _normalize_culture_relations("invalid") == []
        # 单个 dict 包装
        rel = _normalize_culture_relations(
            {"target_id": "cu_b", "type": "influence"}
        )
        assert len(rel) == 1
        assert rel[0]["target_id"] == "cu_b"

    def test_relation_missing_target_id_skipped(self):
        from worldforger.structure_normalize import _normalize_culture_relation_item

        assert _normalize_culture_relation_item({"type": "trade"}) is None
        assert _normalize_culture_relation_item(None) is None
        assert _normalize_culture_relation_item("invalid") is None

    def test_culture_entity_aliases_fields(self):
        from worldforger.structure_normalize import _normalize_culture_entity

        # culture_id, title, desc 等别名字段
        r = _normalize_culture_entity(
            {
                "culture_id": "cu_z",
                "title": "别名文化",
                "desc": "一段描述",
                "beliefs": "信条\n教条",
                "rites": ["仪式A", "仪式B"],
                "sites": "圣所",
                "figures": ["先知X"],
                "relations": [],
            }
        )
        assert r is not None
        assert r["id"] == "cu_z"
        assert r["name"] == "别名文化"
        assert r["summary"] == "一段描述"
        assert r["tenets"] == "信条\n教条"
        assert r["practices"] == "仪式A\n仪式B"
        assert r["sacred_sites"] == ["圣所"]
        assert r["key_figures"] == ["先知X"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. 经济同步回归测试
# ═══════════════════════════════════════════════════════════════════════════


class TestEconomyNormalize:
    def test_non_dict_section_returns_default(self):
        from worldforger.structure_normalize import _normalize_economy_dict

        result = _normalize_economy_dict("invalid")
        assert result["summary"] == ""
        assert result["currencies"] == []
        assert result["markets"] == []
        assert result["trade_routes"] == []
        assert result["trade_goods"] == []

    def test_currency_from_string_auto_id(self):
        from worldforger.structure_normalize import _normalize_economy_dict

        result = _normalize_economy_dict({"currencies": ["金币"]})
        cur = result["currencies"][0]
        assert cur["name"] == "金币"
        assert cur["id"].startswith("cur_")
        assert len(cur["id"]) > 4

    def test_currency_dict_with_alias_fields(self):
        from worldforger.structure_normalize import _normalize_economy_dict

        result = _normalize_economy_dict(
            {
                "currencies": [
                    {
                        "currency_id": "coin_gold",
                        "货币": "黄金币",
                        "symbol": "G",
                        "issuer": "帝国铸币局",
                        "exchange": "1G = 10S",
                    }
                ]
            }
        )
        cur = result["currencies"][0]
        assert cur["id"] == "coin_gold"
        assert cur["name"] == "黄金币"
        assert cur["symbol"] == "G"
        assert cur["issuer_faction_id"] == "帝国铸币局"
        assert cur["exchange_notes"] == "1G = 10S"

    def test_market_with_comma_separated_region_ids(self):
        from worldforger.structure_normalize import _normalize_economy_dict

        result = _normalize_economy_dict(
            {
                "markets": [
                    {
                        "id": "mkt_01",
                        "name": "中央市场",
                        "region_ids": "北境, 南域，东海",
                    }
                ]
            }
        )
        mkt = result["markets"][0]
        assert set(mkt["linked_region_ids"]) == {"北境", "南域", "东海"}

    def test_trade_routes_from_routes_key(self):
        from worldforger.structure_normalize import _normalize_economy_dict

        result = _normalize_economy_dict(
            {"routes": [{"id": "r1", "name": "丝绸之路", "from": "长安", "to": "罗马"}]}
        )
        assert len(result["trade_routes"]) == 1
        assert result["trade_routes"][0]["id"] == "r1"
        assert result["trade_routes"][0]["from_region_id"] == "长安"

    def test_trade_goods_from_goods_key(self):
        from worldforger.structure_normalize import _normalize_economy_dict

        result = _normalize_economy_dict(
            {
                "goods": [
                    {"id": "g1", "name": "丝绸", "type": "奢侈品"}
                ]
            }
        )
        assert len(result["trade_goods"]) == 1
        assert result["trade_goods"][0]["id"] == "g1"
        assert result["trade_goods"][0]["category"] == "奢侈品"

    def test_empty_arrays_preserved(self):
        from worldforger.structure_normalize import _normalize_economy_dict

        result = _normalize_economy_dict({"summary": "无经济"})
        assert result["currencies"] == []
        assert result["markets"] == []
        assert result["trade_routes"] == []
        assert result["trade_goods"] == []

    def test_string_fields_stripped(self):
        from worldforger.structure_normalize import _normalize_economy_dict

        result = _normalize_economy_dict(
            {"labor_notes": " 苦役  ", "taxation_notes": " 重税 "}
        )
        assert result["labor_notes"] == "苦役"
        assert result["taxation_notes"] == "重税"

    def test_non_dict_market_skipped(self):
        from worldforger.structure_normalize import _normalize_economy_dict

        result = _normalize_economy_dict({"markets": ["not_a_dict", {"id": "m1", "name": "OK"}]})
        assert len(result["markets"]) == 1
        assert result["markets"][0]["id"] == "m1"


# ═══════════════════════════════════════════════════════════════════════════
# 3. 角色 normalize 完整覆盖
# ═══════════════════════════════════════════════════════════════════════════


class TestCharactersNormalize:
    def test_non_dict_section_returns_safe_defaults(self):
        from worldforger.structure_normalize import _normalize_characters_dict

        result = _normalize_characters_dict("invalid")
        assert result["summary"] == ""
        assert result["design_notes"] == ""
        assert result["entities"] == []
        assert result["relations"] == []

    def test_entities_single_dict_wrapped_to_array(self):
        from worldforger.structure_normalize import _normalize_characters_dict

        result = _normalize_characters_dict({"entities": {"id": "ch_x", "name": "英雄"}})
        ents = result["entities"]
        assert len(ents) == 1
        assert ents[0]["id"] == "ch_x"

    def test_missing_id_auto_generated_from_name(self):
        from worldforger.structure_normalize import _normalize_characters_dict

        result = _normalize_characters_dict({"entities": [{"name": "路人甲"}]})
        e = result["entities"][0]
        assert e["name"] == "路人甲"
        assert e["id"].startswith("ch_")
        assert len(e["id"]) > 3

    def test_missing_name_falls_back_to_unnamed(self):
        from worldforger.structure_normalize import _normalize_characters_dict

        result = _normalize_characters_dict({"entities": [{}]})
        e = result["entities"][0]
        assert e["name"] == "未命名角色"
        assert e["id"].startswith("ch_")

    def test_cast_role_from_alias_fields(self):
        from worldforger.structure_normalize import _normalize_characters_dict

        result = _normalize_characters_dict(
            {"entities": [{"id": "c1", "name": "主角", "role": "Protagonist"}]}
        )
        assert result["entities"][0]["cast_role"] == "protagonist"

    def test_relations_missing_source_or_target_skipped(self):
        from worldforger.structure_normalize import _normalize_characters_dict

        result = _normalize_characters_dict(
            {
                "entities": [{"id": "a1", "name": "A"}, {"id": "b1", "name": "B"}],
                "relations": [
                    {"source_id": "a1"},  # 缺 target → skipped
                    {"target_id": "b1"},  # 缺 source → skipped
                    {"source_id": "a1", "target_id": "b1", "type": "friend"},
                ],
            }
        )
        rels = result["relations"]
        assert len(rels) == 1
        assert rels[0]["source_id"] == "a1"
        assert rels[0]["target_id"] == "b1"

    def test_relations_single_dict_wrapped(self):
        from worldforger.structure_normalize import _normalize_characters_dict

        result = _normalize_characters_dict(
            {
                "entities": [{"id": "a1", "name": "A"}, {"id": "b1", "name": "B"}],
                "relations": {"source_id": "a1", "target_id": "b1", "type": "ally"},
            }
        )
        assert len(result["relations"]) == 1

    def test_entities_from_roster_fallback(self):
        from worldforger.structure_normalize import _normalize_characters_dict

        result = _normalize_characters_dict(
            {"roster": [{"id": "ch_ro", "name": "编队角色"}]}
        )
        assert len(result["entities"]) == 1
        assert result["entities"][0]["id"] == "ch_ro"

    def test_entities_from_cast_fallback(self):
        from worldforger.structure_normalize import _normalize_characters_dict

        result = _normalize_characters_dict(
            {"cast": [{"id": "ch_ca", "name": "卡司角色"}]}
        )
        assert len(result["entities"]) == 1
        assert result["entities"][0]["id"] == "ch_ca"

    def test_non_dict_entity_items_skipped(self):
        from worldforger.structure_normalize import _normalize_characters_dict

        result = _normalize_characters_dict(
            {"entities": ["not_a_dict", {"id": "ok", "name": "有效"}]}
        )
        assert len(result["entities"]) == 1
        assert result["entities"][0]["id"] == "ok"

    def test_relations_from_character_relations_key(self):
        from worldforger.structure_normalize import _normalize_characters_dict

        result = _normalize_characters_dict(
            {
                "entities": [{"id": "a1", "name": "A"}, {"id": "b1", "name": "B"}],
                "character_relations": [
                    {"source": "a1", "to": "b1", "关系": "师徒", "可见": "公开"}
                ],
            }
        )
        rel = result["relations"][0]
        assert rel["source_id"] == "a1"
        assert rel["target_id"] == "b1"
        assert rel["relation_type"] == "师徒"
        assert rel["visibility"] == "公开"

    def test_entity_chinese_alias_fields(self):
        from worldforger.structure_normalize import _normalize_characters_dict

        result = _normalize_characters_dict(
            {
                "entities": [
                    {
                        "character_id": "ch_cn",
                        "姓名": "中文字段角色",
                        "类型": "supporting_major",
                        "别名": ["小名", "大名"],
                        "factions": "帝国, 公会",
                        "籍贯": "北境",
                        "一句": "命运多舛的英雄",
                        "背景": "曾为奴隶，后获自由。",
                        "人物技能": ["剑术", "潜行"],
                    }
                ]
            }
        )
        e = result["entities"][0]
        assert e["id"] == "ch_cn"
        assert e["name"] == "中文字段角色"
        assert e["cast_role"] == "supporting_major"
        assert e["aliases"] == ["小名", "大名"]
        assert set(e["faction_ids"]) == {"帝国", "公会"}
        assert e["home_region_id"] == "北境"
        assert e["one_line_hook"] == "命运多舛的英雄"
        assert e["notes"] == "曾为奴隶，后获自由。"
        assert e["notable_skills"] == ["剑术", "潜行"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. 情节 save/load 状态保持
# ═══════════════════════════════════════════════════════════════════════════


class TestStorySaveLoadRoundtrip:
    def test_chapters_and_foreshadowing_survive_roundtrip(self):
        w = create_world("情节保存")
        ch1 = StoryChapter(id="ch_r01", order=1, title="第一章", status="drafting", word_count=1500)
        ch2 = StoryChapter(id="ch_r02", order=2, title="第二章", status="planned")
        w.story.chapters = [ch1, ch2]
        fs1 = StoryForeshadowing(
            id="fs_r01", label="神秘信件", planted_chapter_id="ch_r01", status="open"
        )
        fs2 = StoryForeshadowing(
            id="fs_r02", label="叛徒身份", planted_chapter_id="ch_r01",
            payoff_chapter_id="ch_r02", status="resolved",
        )
        w.story.foreshadowing = [fs1, fs2]
        w.story.summary = "史诗故事总览"
        w.story.design_notes = "设计说明文字"
        save_world(w)

        w2 = load_world(w.meta.id)
        s = w2.story
        assert s.summary == "史诗故事总览"
        assert s.design_notes == "设计说明文字"
        assert len(s.chapters) == 2
        assert s.chapters[0].id == "ch_r01"
        assert s.chapters[0].title == "第一章"
        assert s.chapters[0].status == "drafting"
        assert s.chapters[0].word_count == 1500
        assert s.chapters[1].id == "ch_r02"
        assert len(s.foreshadowing) == 2
        assert s.foreshadowing[0].id == "fs_r01"
        assert s.foreshadowing[0].label == "神秘信件"
        assert s.foreshadowing[1].id == "fs_r02"
        assert s.foreshadowing[1].status == "resolved"
        assert s.foreshadowing[1].payoff_chapter_id == "ch_r02"

    def test_chapter_summary_card_survives_roundtrip(self):
        from worldforger.story_store import ensure_story_dirs, write_summary_card, read_summary_card

        w = create_world("摘要卡片保存")
        wid = w.meta.id
        ensure_story_dirs(wid)
        ch = StoryChapter(id="ch_sc01", order=1, title="摘要章")
        w.story.chapters = [ch]
        save_world(w)

        write_summary_card(wid, "ch_sc01", {
            "chapter_id": "ch_sc01",
            "title": "摘要章",
            "main_events": "主角离开京城。",
            "ending_hook": "远方传来号角声。",
        })

        # 重新加载，验证 summary_card 仍可从磁盘读取
        card = read_summary_card(wid, "ch_sc01")
        assert card is not None
        assert card["main_events"] == "主角离开京城。"

    def test_character_runtime_state_survives_roundtrip(self):
        from worldforger.story_store import update_character_runtime_state, get_character_runtime_states

        w = create_world("运行时状态保存")
        w.characters.entities = [
            {"id": "char_rs", "name": "测试角色", "cast_role": "protagonist_core"}
        ]
        save_world(w)

        update_character_runtime_state(
            w, "char_rs",
            {"current_location": "北境要塞", "current_goal": "寻找真相", "emotional_state": "坚定"},
            "ch_01",
        )
        save_world(w)

        w2 = load_world(w.meta.id)
        hero = next((e for e in w2.characters.entities if e.get("id") == "char_rs"), None)
        assert hero is not None
        rs = hero.get("runtime_state", {})
        assert rs.get("current_location") == "北境要塞"
        assert rs.get("last_updated_chapter") == "ch_01"


# ═══════════════════════════════════════════════════════════════════════════
# 5. 第二路「仅同步当前页」各 scope 回归
# ═══════════════════════════════════════════════════════════════════════════


def _scope_test_patch(scope: str) -> dict:
    """为各 scope 生成合法的最小补丁。"""
    patches = {
        "geography": {"geography": {"summary": "地理概览", "regions": [{"id": "r_sc", "name": "测试区域", "summary": "一个区域"}]}},
        "ecology": {"ecology": {"summary": "生态概览", "biomes": [{"id": "bio_01", "name": "森林"}]}},
        "power_system": {"power_system": {"summary": "境界体系", "tiers": [{"id": "t1", "name": "炼气", "order": 1}]}},
        "item_quality_system": {"item_quality_system": {"summary": "品阶", "grades": [{"id": "g1", "name": "凡品", "order": 0}]}},
        "attribute_system": {"attribute_system": {"summary": "属性", "stats": [{"id": "str", "name": "力量"}]}},
        "factions": {"factions": {"summary": "派系", "entities": [{"id": "f_01", "name": "帝国"}]}},
        "cultures": {"cultures": {"summary": "文化", "entities": [{"id": "cu_01", "name": "龙裔"}]}},
        "characters": {"characters": {"summary": "角色", "entities": [{"id": "c_01", "name": "英雄"}]}},
        "history": {"history": {"summary": "历史", "events": [{"id": "evt_01", "name": "大灾变", "era": "远古"}]}},
        "economy": {"economy": {"summary": "经济", "currencies": [{"id": "cur_01", "name": "金币"}]}},
        "story": {"story": {"summary": "情节总览"}},
    }
    p = patches.get(scope)
    if p is None:
        raise ValueError(f"unknown scope: {scope}")
    return p


class TestPerScopeSyncNormalize:
    """验证 normalize_structure_patch_detailed 对每个 scope 值的处理。"""

    SCOPES = [
        "geography",
        "ecology",
        "power_system",
        "item_quality_system",
        "attribute_system",
        "factions",
        "cultures",
        "characters",
        "history",
        "economy",
        "story",
    ]

    @pytest.mark.parametrize("scope", SCOPES)
    def test_normalize_accepts_scope_key(self, scope):
        from worldforger.structure_normalize import normalize_structure_patch_detailed

        patch = _scope_test_patch(scope)
        normalized, notes = normalize_structure_patch_detailed(patch)
        assert scope in normalized
        assert isinstance(normalized[scope], dict)

    @pytest.mark.parametrize("scope", SCOPES)
    def test_apply_structure_patch_for_scope(self, scope):
        from worldforger.panel_sync import apply_structure_patch

        w = create_world(f"scope-{scope}")
        patch = _scope_test_patch(scope)
        new_world, updated, warnings, notes = apply_structure_patch(w, patch)
        assert scope in updated, f"scope={scope} 未被更新，warnings={warnings}"
        assert len(warnings) == 0

    def test_structure_system_for_scope_all(self):
        from worldforger.panel_sync import structure_system_for_scope

        s = structure_system_for_scope(None)
        assert "本轮同步范围" not in s
        s2 = structure_system_for_scope("all")
        assert "本轮同步范围" not in s2

    def test_structure_system_for_specific_scope(self):
        from worldforger.panel_sync import structure_system_for_scope

        s = structure_system_for_scope("geography")
        assert "本轮同步范围" in s
        assert "geography" in s

    def test_structure_system_for_factions_has_extra_hint(self):
        from worldforger.panel_sync import structure_system_for_scope

        s = structure_system_for_scope("factions")
        assert "ally|enemy|neutral|complex" in s

    def test_structure_system_for_unknown_scope_falls_back(self):
        from worldforger.panel_sync import structure_system_for_scope

        s = structure_system_for_scope("unknown_scope_xyz")
        assert "本轮同步范围" not in s  # 回退到 BASE

    @pytest.mark.anyio
    @pytest.mark.parametrize("scope", SCOPES)
    async def test_sync_panels_applies_single_scope(self, scope):
        """Mock LLM 返回仅包含指定 scope 的补丁，验证 sync 正确应用。"""
        from unittest.mock import AsyncMock, patch

        from app.main import app
        from fastapi.testclient import TestClient

        w = create_world(f"sync-{scope}")
        wid = w.meta.id

        # mock 的 LLM 返回对应 scope 的 JSON
        import json as _json
        patch_data = _scope_test_patch(scope)

        mock_reply = _json.dumps(patch_data, ensure_ascii=False)

        with patch(
            "worldforger.panel_sync.chat_completion", new_callable=AsyncMock
        ) as mock_chat:
            mock_chat.return_value = mock_reply
            c = TestClient(app)
            r = c.post(
                f"/api/worlds/{wid}/sync-panels-from-chat",
                json={
                    "user_message": f"添加 {scope} 数据",
                    "assistant_reply": mock_reply,
                    "scope": scope,
                    "persist": True,
                },
            )
            assert r.status_code == 200, f"scope={scope} failed: {r.text}"
            body = r.json()
            assert body["ok"] is True
            assert scope in body["updated_sections"], (
                f"scope={scope} 未出现在 updated_sections={body.get('updated_sections')} 中"
            )
            mock_chat.assert_awaited_once()
