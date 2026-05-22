from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

from worldforger.config import get_settings
from worldforger.markdown_export import world_to_markdown
from worldforger.schemas import Meta, World


def _slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "world"


def world_root(world_id: str) -> Path:
    return get_settings().worlds_dir / world_id


def manifest_path(world_id: str) -> Path:
    return world_root(world_id) / "manifest.json"


def world_json_path(world_id: str) -> Path:
    return world_root(world_id) / "world.json"


def world_md_path(world_id: str) -> Path:
    return world_root(world_id) / "world.md"


def outlines_dir(world_id: str) -> Path:
    return world_root(world_id) / "outlines"


def sessions_dir(world_id: str) -> Path:
    return world_root(world_id) / "sessions"


def snapshots_dir(world_id: str) -> Path:
    return world_root(world_id) / "snapshots"


def _prune_snapshots(snap_root: Path, *, max_keep: int = 64) -> None:
    if not snap_root.is_dir():
        return
    files: list[tuple[int, Path]] = []
    for p in snap_root.glob("v*.json"):
        if not p.is_file():
            continue
        stem = p.stem
        if len(stem) < 2 or not stem[1:].isdigit():
            continue
        files.append((int(stem[1:]), p))
    files.sort(key=lambda x: x[0])
    if len(files) <= max_keep:
        return
    for _, p in files[: len(files) - max_keep]:
        try:
            p.unlink()
        except OSError:
            pass


def list_snapshots(world_id: str) -> list[dict[str, object]]:
    """列出磁盘上的版本快照（文件名 v{version}.json），新版本在前。"""
    d = snapshots_dir(world_id)
    if not d.is_dir():
        return []
    rows: list[dict[str, object]] = []
    for p in d.glob("v*.json"):
        if not p.is_file():
            continue
        stem = p.stem
        if len(stem) < 2 or not stem[1:].isdigit():
            continue
        v = int(stem[1:])
        updated_at = ""
        name = ""
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            meta = data.get("meta") or {}
            if isinstance(meta, dict):
                updated_at = str(meta.get("updated_at") or "")
                name = str(meta.get("name") or "")
        except (json.JSONDecodeError, OSError, TypeError):
            pass
        rows.append({"version": v, "updated_at": updated_at, "name": name})
    rows.sort(key=lambda r: int(r["version"]), reverse=True)
    return rows


def load_snapshot_dict(world_id: str, version: int) -> dict[str, object]:
    p = snapshots_dir(world_id) / f"v{int(version)}.json"
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return json.loads(p.read_text(encoding="utf-8"))


def rollback_to_snapshot(world_id: str, snapshot_version: int) -> World:
    """
    用指定快照覆盖当前 world.json，版本号在当前基础上 +1（与正常保存一致）。
    """
    snap = load_snapshot_dict(world_id, snapshot_version)
    restored = World.model_validate(snap)
    if restored.meta.id != world_id:
        raise ValueError("snapshot meta.id does not match world_id")
    current = load_world(world_id)
    restored.meta.version = int(current.meta.version)
    restored.bump_version()
    save_world(restored, export_markdown=True)
    return restored


def clear_snapshots(world_id: str) -> int:
    """删除所有快照文件（保留最新一份），返回删除数量。"""
    d = snapshots_dir(world_id)
    if not d.is_dir():
        return 0
    files = sorted(d.glob("v*.json"))
    if len(files) <= 1:
        return 0
    # 保留最新的一份（版本号最大的）
    to_delete = files[:-1]
    for f in to_delete:
        f.unlink()
    return len(to_delete)


def new_world_id(display_name: str) -> str:
    return f"{_slug(display_name)}-{uuid.uuid4().hex[:8]}"


def create_world(display_name: str) -> World:
    settings = get_settings()
    settings.worlds_dir.mkdir(parents=True, exist_ok=True)
    wid = new_world_id(display_name)
    root = world_root(wid)
    root.mkdir(parents=True, exist_ok=True)
    outlines_dir(wid).mkdir(parents=True, exist_ok=True)
    sessions_dir(wid).mkdir(parents=True, exist_ok=True)
    from worldforger.story_store import ensure_story_dirs

    ensure_story_dirs(wid)

    from datetime import datetime, timezone

    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = {
        "world_id": wid,
        "display_name": display_name,
        "created_at": created,
        "api_base": settings.openai_api_base,
        "default_model": settings.openai_chat_model,
    }
    manifest_path(wid).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    world = World(meta=Meta(id=wid, name=display_name))
    save_world(world, export_markdown=True)
    return world


def list_world_ids() -> list[str]:
    base = get_settings().worlds_dir
    if not base.is_dir():
        return []
    return sorted(
        p.name for p in base.iterdir() if p.is_dir() and (p / "world.json").is_file()
    )


def world_display_name(world_id: str) -> str:
    """从 world.json 读取 meta.name，失败时退回 world_id。"""
    path = world_json_path(world_id)
    if not path.is_file():
        return world_id
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        name = (data.get("meta") or {}).get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    except (json.JSONDecodeError, OSError, TypeError):
        pass
    return world_id


def list_world_briefs() -> list[dict[str, str]]:
    """供列表 UI 使用：每项 id + 显示名（与 meta.name 同步）。"""
    return [{"id": wid, "name": world_display_name(wid)} for wid in list_world_ids()]


def load_world(world_id: str) -> World:
    path = world_json_path(world_id)
    if not path.is_file():
        raise FileNotFoundError(world_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    return World.model_validate(data)


def rename_world(world_id: str, display_name: str) -> World:
    """更新 meta.name 与 manifest.display_name；**不改变** world_id 目录名。"""
    name = display_name.strip()
    if not name:
        raise ValueError("empty display name")
    w = load_world(world_id)
    data = w.model_dump(mode="json")
    data["meta"]["name"] = name
    w2 = World.model_validate(data)
    w2.bump_version()
    save_world(w2, export_markdown=True)
    mp = manifest_path(world_id)
    if mp.is_file():
        try:
            man = json.loads(mp.read_text(encoding="utf-8"))
            man["display_name"] = name
            mp.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass
    return w2


def delete_world(world_id: str) -> None:
    """删除整个世界目录（world.json、大纲、会话等）。"""
    if not world_json_path(world_id).is_file():
        raise FileNotFoundError(world_id)
    shutil.rmtree(world_root(world_id))


def save_world(world: World, *, export_markdown: bool = True) -> None:
    wid = world.meta.id
    root = world_root(wid)
    root.mkdir(parents=True, exist_ok=True)
    outlines_dir(wid).mkdir(parents=True, exist_ok=True)
    path = world_json_path(wid)
    snap_root = snapshots_dir(wid)
    snap_root.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            old_raw = path.read_text(encoding="utf-8")
            old_data = json.loads(old_raw)
            old_meta = old_data.get("meta") if isinstance(old_data, dict) else None
            old_v = int((old_meta or {}).get("version") or 0) if isinstance(old_meta, dict) else 0
            if old_v > 0:
                (snap_root / f"v{old_v}.json").write_text(old_raw, encoding="utf-8")
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    path.write_text(
        json.dumps(world.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _prune_snapshots(snap_root)
    if export_markdown:
        world_md_path(wid).write_text(world_to_markdown(world), encoding="utf-8")


def load_world_markdown_optional(world_id: str) -> str | None:
    p = world_md_path(world_id)
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return None


# 拼入对话/大纲上下文，便于模型区分「可结构化落盘」与「工作台只读能力」。
_STUDIO_CONTEXT_BLOCK = (
    "\n\n--- studio（工作台能力；**不**写入 world.json schema，仅供助手理解侧栏「数据」分组） ---\n"
    + json.dumps(
        {
            "studio": {
                "modules": [
                    {
                        "id": "search",
                        "label": "全文搜索",
                        "kind": "full_text_search",
                        "description": "在磁盘 world.json 与 world.md 内按关键词检索（大小写不敏感）；API：GET /api/worlds/{world_id}/search?q=关键词",
                    },
                    {
                        "id": "files",
                        "label": "导出与快照",
                        "description": "世界目录路径提示、重新导出 world.md、当前内存中 world.json 只读快照（与是否已保存落盘一致）。",
                    },
                ]
            }
        },
        ensure_ascii=False,
        indent=2,
    )
)


def world_context_for_prompt(world: World, *, include_markdown: bool = False) -> str:
    base = json.dumps(world.model_dump(mode="json"), ensure_ascii=False, indent=2) + _STUDIO_CONTEXT_BLOCK
    if not include_markdown:
        return base
    md = load_world_markdown_optional(world.meta.id)
    if not md:
        return base
    return base + "\n\n--- world.md (human view, JSON wins on conflict) ---\n\n" + md
