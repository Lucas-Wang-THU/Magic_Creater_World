"""伏笔台账：解析 story-foreshadow 块并合并进 world.story.foreshadowing。"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from worldforger.schemas import StoryForeshadowing, StoryForeshadowStatus, World


def new_foreshadow_id() -> str:
    return f"fs_{hashlib.sha256(str(id(object())).encode()).hexdigest()[:10]}"


def _valid_status(s: str) -> StoryForeshadowStatus:
    v = (s or "open").strip()
    if v in ("open", "partial", "resolved"):
        return v  # type: ignore[return-value]
    return "open"


def _chapter_ids(world: World) -> set[str]:
    return {str(c.id).strip() for c in world.story.chapters if c and str(c.id).strip()}


def _find_fs(world: World, fid: str) -> StoryForeshadowing | None:
    fid = fid.strip()
    for f in world.story.foreshadowing:
        if str(f.id).strip() == fid:
            return f
    return None


def apply_foreshadow_operations(
    world: World,
    operations: list[dict[str, Any]],
) -> tuple[World, list[str], list[str]]:
    """
    返回 (world, applied_summaries, warnings)。
    op: upsert | patch | resolve | delete
    """
    applied: list[str] = []
    warnings: list[str] = []
    ch_ids = _chapter_ids(world)

    for raw in operations:
        if not isinstance(raw, dict):
            warnings.append("跳过非对象操作")
            continue
        op = str(raw.get("op") or "patch").strip().lower()

        if op == "delete":
            fid = str(raw.get("id") or "").strip()
            if not fid:
                warnings.append("delete 缺少 id")
                continue
            before = len(world.story.foreshadowing)
            world.story.foreshadowing = [f for f in world.story.foreshadowing if str(f.id).strip() != fid]
            if len(world.story.foreshadowing) < before:
                applied.append(f"删除伏笔 {fid}")
            else:
                warnings.append(f"未找到伏笔 {fid}")
            continue

        fid = str(raw.get("id") or "").strip()
        if not fid:
            fid = new_foreshadow_id()
            item = StoryForeshadowing(id=fid)
            world.story.foreshadowing.append(item)
            applied.append(f"新建伏笔 {fid}")
        else:
            item = _find_fs(world, fid)
            if item is None:
                item = StoryForeshadowing(id=fid)
                world.story.foreshadowing.append(item)
                applied.append(f"新建伏笔 {fid}")

        if op == "resolve":
            item.status = "resolved"
            if raw.get("payoff_chapter_id"):
                pc = str(raw["payoff_chapter_id"]).strip()
                if pc and pc not in ch_ids:
                    warnings.append(f"{item.id}: payoff_chapter_id {pc} 不存在")
                else:
                    item.payoff_chapter_id = pc
            applied.append(f"回收伏笔 {item.id} → resolved")
            continue

        if "label" in raw:
            item.label = str(raw.get("label") or "").strip()
        if "notes" in raw:
            item.notes = str(raw.get("notes") or "").strip()
        if "reader_known" in raw:
            item.reader_known = bool(raw.get("reader_known"))
        if "status" in raw:
            item.status = _valid_status(str(raw.get("status")))
        for key in ("planted_chapter_id", "payoff_chapter_id"):
            if key in raw:
                cid = str(raw.get(key) or "").strip()
                if cid and cid not in ch_ids:
                    warnings.append(f"{item.id}: {key}={cid} 不存在")
                else:
                    setattr(item, key, cid)
        if op == "upsert":
            applied.append(f"更新伏笔 {item.id}")
        elif op == "patch":
            applied.append(f"修补伏笔 {item.id}")

    return world, applied, warnings


def parse_story_foreshadow_blocks(text: str) -> list[dict[str, Any]]:
    """从助手回复中解析 ```story-foreshadow … ``` JSON 数组。"""
    out: list[dict[str, Any]] = []
    raw = text or ""
    pattern = re.compile(r"```story-foreshadow\s*\n([\s\S]*?)```", re.IGNORECASE)
    for m in pattern.finditer(raw):
        body = (m.group(1) or "").strip()
        if not body:
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            out.extend([x for x in data if isinstance(x, dict)])
        elif isinstance(data, dict) and "operations" in data:
            ops = data.get("operations")
            if isinstance(ops, list):
                out.extend([x for x in ops if isinstance(x, dict)])
    return out


def foreshadow_ledger_text(world: World, *, chapter_id: str = "", max_items: int = 40) -> str:
    """供写作 / 对话 system 注入的伏笔台账。"""
    cid = (chapter_id or "").strip()
    lines: list[str] = []
    for f in world.story.foreshadowing:
        if cid:
            rel = f.planted_chapter_id == cid or f.payoff_chapter_id == cid
            if f.status == "resolved" and not rel:
                continue
        lines.append(
            f"- {f.id} | {f.status} | 埋设:{f.planted_chapter_id or '—'} | "
            f"回收:{f.payoff_chapter_id or '—'} | 读者已知:{f.reader_known} | {f.label or '（无题）'}"
        )
        if len(lines) >= max_items:
            lines.append("…(更多伏笔已省略)")
            break
    if not lines:
        return "（暂无伏笔条目）"
    return "\n".join(lines)
