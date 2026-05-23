from __future__ import annotations

from typing import Any


def merge_section_conservative(
    base: dict[str, Any], patch: dict[str, Any]
) -> dict[str, Any]:
    """
    将 patch 合并进 base：空字符串不覆盖已有非空文案；空数组不覆盖已有非空数组；
    若双方数组元素都含 id 字段，则按 id 匹配做增量合并（更新已有 + 追加新增），
    避免模型误返回空列表或不完整列表导致已有数据被清空。
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
            out[k] = pv
            continue
        if isinstance(bv, list) and isinstance(pv, list):
            if len(pv) == 0 and len(bv) > 0:
                continue
            if _array_items_have_ids(bv) and _array_items_have_ids(pv):
                out[k] = merge_array_by_id(bv, pv)
            else:
                out[k] = pv
            continue
        if isinstance(bv, dict) and isinstance(pv, dict):
            out[k] = merge_section_conservative(bv, pv)
            continue
        out[k] = pv
    return out


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
