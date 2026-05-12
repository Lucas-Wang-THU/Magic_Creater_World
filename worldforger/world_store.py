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
    path.write_text(
        json.dumps(world.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if export_markdown:
        world_md_path(wid).write_text(world_to_markdown(world), encoding="utf-8")


def load_world_markdown_optional(world_id: str) -> str | None:
    p = world_md_path(world_id)
    if p.is_file():
        return p.read_text(encoding="utf-8")
    return None


def world_context_for_prompt(world: World, *, include_markdown: bool = False) -> str:
    base = json.dumps(world.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if not include_markdown:
        return base
    md = load_world_markdown_optional(world.meta.id)
    if not md:
        return base
    return base + "\n\n--- world.md (human view, JSON wins on conflict) ---\n\n" + md
