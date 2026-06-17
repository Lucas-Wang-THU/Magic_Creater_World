from __future__ import annotations

import hashlib
import json as _json
from typing import Any


def merge_section_conservative(
    base: dict[str, Any], patch: dict[str, Any]
) -> dict[str, Any]:
    """
    将 patch 合并进 base：空字符串不覆盖已有非空文案；空数组不覆盖已有非空数组；
    若双方数组元素都含 id 字段，则按 id 匹配做增量合并（更新已有 + 追加新增）；
    否则按 name 去重追加，避免模型误返回不完整列表导致已有数据被清空。

    新增：power_system 合并后自动执行 reconcile——当 skill node 在 patch 中
    被移动到 subclass 树时，从原位置（tier 通用树）删除，避免重复。
    """
    out = dict(base)
    for k, pv in patch.items():
        if pv is None:
            continue
        if k not in base:
            out[k] = pv
            continue
        bv = base[k]
        if isinstance(bv, str) and isinstance(pv, str):
            if not pv.strip() and bv.strip():
                continue
            # Protect 'name' field: if patch name looks like an ID (underscore English)
            # and base name is real (contains CJK or spaces), keep base name
            if k == "name" and bv.strip() and pv.strip():
                import re as _re2
                _id_like = bool(_re2.match(r'^[a-z][a-z0-9_]*$', pv.strip()))
                _real_name = bool(_re2.search(r'[一-鿿]', bv)) or ' ' in bv.strip()
                if _id_like and _real_name:
                    continue  # don't overwrite real name with ID-like string
            out[k] = pv
            continue
        if isinstance(bv, list) and isinstance(pv, list):
            if len(pv) == 0 and len(bv) > 0:
                continue
            if _array_items_have_ids(bv) and _array_items_have_ids(pv):
                out[k] = merge_array_by_id(bv, pv)
            else:
                out[k] = _merge_array_by_name_or_append(bv, pv)
            continue
        if isinstance(bv, dict) and isinstance(pv, dict):
            out[k] = merge_section_conservative(bv, pv)
            continue
        out[k] = pv
    return out


def _merge_array_by_name_or_append(
    base_list: list[dict[str, Any]], patch_list: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """无伪数组的聚合符：按 name 去重追加；若无 name 则按 JSON 序列化去重。

    绝不删除 base 中已有条目。
    """
    merged: list[dict[str, Any]] = list(base_list)

    # 收集已有条目的 key（name 或 JSON 哈希）
    seen_names: set[str] = set()
    seen_hashes: set[str] = set()
    for item in merged:
        if isinstance(item, dict):
            nm = (item.get("name") or item.get("tier_name") or "").strip()
            if nm:
                seen_names.add(nm)
            else:
                seen_hashes.add(_stable_json_hash(item))
        else:
            seen_hashes.add(_stable_json_hash(item) if isinstance(item, dict) else str(item))

    for patch_item in patch_list:
        if not isinstance(patch_item, dict):
            # 非 dict 项按原样追加
            merged.append(patch_item)
            continue
        # Match by name (common) or tier_name (power_system.tiers / profession_system.by_tier)
        raw_nm = (patch_item.get("name") or patch_item.get("tier_name") or "").strip()
        # Normalize: strip trailing "境" suffix for matching (e.g. "碎尘境" → "碎尘")
        nm = raw_nm
        if nm.endswith("境") and len(nm) > 1:
            nm_no_suffix = nm[:-1]
            # Check if the no-suffix version exists in seen_names or merged
            if nm_no_suffix in seen_names:
                nm = nm_no_suffix
            else:
                for base_item in merged:
                    if isinstance(base_item, dict):
                        bn = (base_item.get("name") or base_item.get("tier_name") or "").strip()
                        if bn == nm_no_suffix:
                            nm = nm_no_suffix
                            break
        if nm:
            key = nm
            if key in seen_names:
                # 同名/tier_name 项做 deep-merge 更新
                for idx, base_item in enumerate(merged):
                    if isinstance(base_item, dict):
                        base_nm = (base_item.get("name") or base_item.get("tier_name") or "").strip()
                        if base_nm == key:
                            merged[idx] = merge_section_conservative(base_item, patch_item)
                            break
                continue
            seen_names.add(key)
        else:
            h = _stable_json_hash(patch_item)
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
        merged.append(dict(patch_item))

    return merged


def _stable_json_hash(obj: dict[str, Any]) -> str:
    """键排序后的 JSON 哈希，用于无 id/无 name 的条目去重。"""
    raw = _json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def merge_array_by_id(
    base_list: list[dict[str, Any]], patch_list: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """按 id 合并数组：已存在 id → 递归 deep-merge；新 id → 追加到末尾。

    绝不删除 base 中已有条目；patch 中缺失 id 的条目会被跳过。
    """
    merged: list[dict[str, Any]] = list(base_list)
    id_to_idx: dict[str, int] = {}
    for i, item in enumerate(merged):
        item_id = item.get("id")
        if isinstance(item_id, str) and item_id:
            id_to_idx[item_id] = i

    for patch_item in patch_list:
        pid = patch_item.get("id") if isinstance(patch_item, dict) else None
        if not isinstance(pid, str) or not pid:
            continue
        if pid in id_to_idx:
            idx = id_to_idx[pid]
            merged[idx] = merge_section_conservative(merged[idx], patch_item)
        else:
            merged.append(dict(patch_item))
            id_to_idx[pid] = len(merged) - 1

    return merged


def reconcile_power_system_skill_nodes(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure skill nodes are placed in the correct tier/subclass tree.

    When LLM moves a skill node from a tier's general skill_tree into a
    subclass_path's skill_tree, the standard merge preserves both copies.
    This function removes nodes from locations where they no longer belong.

    Rule: If a node ID appears in a subclass tree, it should NOT also
    appear in the same tier's general tree (unless explicitly duplicated).
    """
    ps = data.get("power_system")
    if not isinstance(ps, dict):
        return data
    tiers = ps.get("tiers")
    if not isinstance(tiers, list):
        return data

    modified = False
    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        # Collect all node IDs that appear in ANY subclass_path of this tier
        subclass_node_ids: set[str] = set()
        sub_paths = tier.get("subclass_paths")
        if isinstance(sub_paths, list):
            for sp in sub_paths:
                if isinstance(sp, dict):
                    for sn in (sp.get("skill_tree") or []):
                        if isinstance(sn, dict) and sn.get("id"):
                            subclass_node_ids.add(sn["id"])

        if not subclass_node_ids:
            continue

        # Remove nodes from the tier's general skill_tree if they now live in a subclass
        general_tree = tier.get("skill_tree")
        if isinstance(general_tree, list):
            before = len(general_tree)
            tier["skill_tree"] = [
                n for n in general_tree
                if not (isinstance(n, dict) and n.get("id") in subclass_node_ids)
            ]
            if len(tier["skill_tree"]) < before:
                modified = True

    if modified:
        print("[MCW-MERGE] Reconciled power_system: moved skill nodes from general to subclass trees")
    return data


def _array_items_have_ids(arr: list[Any]) -> bool:
    """检查数组的非空元素是否都为含有效 id 的 dict。"""
    if not arr:
        return False
    for item in arr:
        if not isinstance(item, dict):
            return False
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            return False
    return True
