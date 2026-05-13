"""world.json 快照之间的行级 diff（用于看板可视化）。"""

from __future__ import annotations

import difflib
import json
from typing import Any, Literal

DiffLine = dict[str, str]
DiffLineKind = Literal["ctx", "add", "rem"]


def line_diff_json(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    max_lines: int = 1600,
) -> tuple[list[DiffLine], bool]:
    """
    将两侧 JSON 规范序列化后做 ndiff，返回行列表与是否截断。
    每行: { "kind": "ctx"|"add"|"rem", "text": "…" }（text 不含 diff 前缀）。
    """
    la = json.dumps(left, ensure_ascii=False, indent=2).splitlines()
    lb = json.dumps(right, ensure_ascii=False, indent=2).splitlines()
    out: list[DiffLine] = []
    truncated = False
    for line in difflib.ndiff(la, lb):
        if line.startswith("? "):
            continue
        if line.startswith("+ "):
            out.append({"kind": "add", "text": line[2:]})
        elif line.startswith("- "):
            out.append({"kind": "rem", "text": line[2:]})
        else:
            out.append({"kind": "ctx", "text": line[2:]})
        if len(out) >= max_lines:
            truncated = True
            break
    return out, truncated
