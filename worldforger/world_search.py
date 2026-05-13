"""在世界 JSON 与 world.md 中做简单全文检索（大小写不敏感）。"""

from __future__ import annotations

from typing import Any


def _needle(q: str) -> str:
    s = (q or "").strip()
    if not s:
        raise ValueError("empty query")
    if len(s) > 200:
        raise ValueError("query too long")
    return s


def _snippet(text: str, max_len: int = 180) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def search_json_strings(
    obj: Any,
    needle: str,
    *,
    path: str = "",
    max_hits: int = 120,
) -> list[dict[str, str]]:
    """遍历 JSON，在字符串叶子及可转字符串的标量中查找子串；返回 path + snippet。"""
    hits: list[dict[str, str]] = []
    low = needle.lower()

    def walk(o: Any, p: str) -> None:
        if len(hits) >= max_hits:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                seg = f"{p}.{k}" if p else str(k)
                walk(v, seg)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{p}[{i}]")
        elif isinstance(o, str):
            if low in o.lower():
                hits.append({"path": p or "(root)", "snippet": _snippet(o)})
        elif o is not None and not isinstance(o, (dict, list)):
            s = str(o)
            if low in s.lower():
                hits.append({"path": p or "(root)", "snippet": _snippet(s)})

    walk(obj, path)
    return hits


def search_markdown_lines(text: str | None, needle: str, *, max_hits: int = 80) -> list[dict[str, Any]]:
    if not text or not str(text).strip():
        return []
    low = needle.lower()
    hits: list[dict[str, Any]] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if low in line.lower():
            hits.append({"line": i, "text": _snippet(line.strip(), 240)})
            if len(hits) >= max_hits:
                break
    return hits


def search_world_payload(
    world_dict: dict[str, Any],
    markdown: str | None,
    query: str,
    *,
    max_json_hits: int = 120,
    max_md_hits: int = 80,
) -> dict[str, Any]:
    """供 API 使用：返回 json_hits、markdown_hits 与计数。"""
    n = _needle(query)
    json_hits = search_json_strings(world_dict, n, max_hits=max_json_hits)
    md_hits = search_markdown_lines(markdown, n, max_hits=max_md_hits)
    return {
        "query": n,
        "json_hits": json_hits,
        "markdown_hits": md_hits,
        "total_json": len(json_hits),
        "total_md": len(md_hits),
    }
