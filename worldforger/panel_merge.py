from __future__ import annotations

from typing import Any


def merge_section_conservative(
    base: dict[str, Any], patch: dict[str, Any]
) -> dict[str, Any]:
    """
    将 patch 合并进 base：空字符串不覆盖已有非空文案；空数组不覆盖已有非空数组；
    避免模型误返回空列表导致整块看板数据被清空。
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
            out[k] = pv
            continue
        if isinstance(bv, dict) and isinstance(pv, dict):
            out[k] = merge_section_conservative(bv, pv)
            continue
        out[k] = pv
    return out
