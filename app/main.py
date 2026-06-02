from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.requests import Request

from worldforger.config import get_settings
from worldforger.llm import chat_completion
from worldforger.creative_modes import chat_guides_content, chat_mode_system, genre_tags_prompt_addon, normalize_chat_guides
from worldforger.panel_sync import sync_panels_from_dialogue
from worldforger.relation_graph_refresh import (
    refresh_world_culture_relations,
    refresh_world_faction_relations,
)
from worldforger.prompts import (
    character_chat_system_prompt,
    ecology_generate_system_prompt,
    ecology_generate_user_payload,
    outline_system_prompt,
    system_with_world_json,
)
from worldforger.schemas import StoryPerson, World
from worldforger.foreshadow_apply import apply_foreshadow_operations
from worldforger.story_agent import run_story_chat_agent
from worldforger.story_chapter_sync import chapter_display_for_prompt, reconcile_story_chapters, title_from_beat_markdown
from worldforger.story_prompts import story_chat_system_prompt
from worldforger.story_service import (
    add_chapter,
    apply_unit_label_from_mode,
    generate_chapter_beats,
    generate_macro_outline,
    generate_manuscript,
    generate_manuscript_stream,
    remove_chapter,
    try_import_legacy,
)
from worldforger.story_store import (
    beat_path,
    macro_outline_path,
    manuscript_path,
    read_text,
    resolve_unit_label,
    sync_chapter_word_count,
    utc_now_iso,
    write_text,
)
from worldforger.snapshot_diff import line_diff_json
from worldforger.reference_linter import fix_world_references, lint_world_references
from worldforger.world_search import search_world_payload
from worldforger.world_store import (
    create_world,
    delete_world,
    list_snapshots,
    list_world_briefs,
    load_snapshot_dict,
    load_world,
    load_world_markdown_optional,
    outlines_dir,
    rename_world,
    rollback_to_snapshot,
    save_world,
    sessions_dir,
    world_context_for_prompt,
    world_json_path,
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _static_nocache_enabled() -> bool:
    """本地调试：避免 /static/* 长期 304，浏览器拿不到最新 app.js。"""
    v = (os.environ.get("MCW_NO_STATIC_CACHE") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


from starlette.types import ASGIApp, Scope, Receive, Send


class DevStaticCacheBypassMiddleware:
    """纯 ASGI：去掉 /static/ 的条件 GET + 移除 ETag + 禁止浏览器缓存。

    BaseHTTPMiddleware 与 StaticFiles 挂载路由有已知交互问题，这里
    直接操作 ASGI scope/event 以保证可靠性。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _static_nocache_enabled() or not scope.get("path", "").startswith("/static/"):
            await self.app(scope, receive, send)
            return

        # 移除请求中的条件头，避免 304
        headers = scope.get("headers", ())
        scope["headers"] = [
            (k, v) for k, v in headers if k.lower() not in (b"if-none-match", b"if-modified-since")
        ]

        async def _send(message: dict) -> None:
            if message["type"] == "http.response.start":
                # 移除响应中的 ETag，避免浏览器下次发条件请求
                resp_headers = [
                    (k, v) for k, v in message.get("headers", ())
                    if k.lower() not in (b"etag",)
                ]
                resp_headers.append((b"cache-control", b"no-store, max-age=0"))
                message["headers"] = resp_headers
            await send(message)

        await self.app(scope, receive, _send)


class CreateWorldBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class RenameWorldBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class RollbackSnapshotBody(BaseModel):
    snapshot_version: int = Field(ge=1, le=9_999_999)


class FixReferencesBody(BaseModel):
    """引用自动修复：仅移除悬空边 / 无效 id 引用等；不合并重复区域、不生成缺失 id。"""

    dry_run: bool = False


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatBody(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    mode: str | None = None
    include_markdown_context: bool = False
    chat_guides: list[str] = Field(default_factory=list)

    @field_validator("chat_guides", mode="before")
    @classmethod
    def _filter_chat_guides(cls, v: object) -> list[str]:
        return normalize_chat_guides(v)


class StoryChatBody(ChatBody):
    active_chapter_id: str = ""
    include_story_files: bool = False
    use_tools: bool = True
    persist_tool_changes: bool = True
    writing_prompt: str = Field(default="", max_length=8000)
    attach_prev_chapters: int | None = Field(default=None, ge=0, le=5)
    person: StoryPerson | None = None
    character_id: str | None = None


class StoryForeshadowApplyBody(BaseModel):
    operations: list[dict[str, Any]] = Field(default_factory=list)
    persist: bool = True


class OutlineBody(BaseModel):
    kind: Literal["characters", "plot"]
    prompt: str = Field(min_length=1, max_length=8000)
    include_markdown_context: bool = True
    creative_mode: str | None = None


class EcologyGenerateBody(BaseModel):
    """一键生成生态叙事 + 文末 ecology JSON 代码块（用户可复制或再开对话后同步）。"""

    hint: str = Field(default="", max_length=6000)
    creative_mode: str | None = None


class StoryTextBody(BaseModel):
    content: str = ""


class StoryChapterCreateBody(BaseModel):
    title: str = Field(default="", max_length=500)
    order: int | None = Field(default=None, ge=1, le=9999)


class StoryGenerateMacroBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    include_markdown_context: bool = False
    creative_mode: str | None = None
    persist: bool = True


class StoryGenerateBeatsBody(BaseModel):
    chapter_ids: list[str] = Field(default_factory=list)
    prompt: str = Field(min_length=1, max_length=8000)
    include_markdown_context: bool = False
    creative_mode: str | None = None
    persist: bool = True


class StoryWritingDefaultsPatchBody(BaseModel):
    enable_narrative_kg: bool | None = None
    enable_consistency_check: bool | None = None
    enable_sentiment_track: bool | None = None
    # Layer 4
    enable_polisher: bool | None = None
    polish_max_rounds: int | None = Field(default=None, ge=1, le=3)
    enable_knowledge_track: bool | None = None
    enable_decision_track: bool | None = None
    enable_physical_state_track: bool | None = None
    enable_personal_timeline_track: bool | None = None


class StoryGenerateManuscriptBody(BaseModel):
    chapter_id: str = Field(min_length=1, max_length=120)
    prompt: str = Field(default="", max_length=8000)
    last_user_message: str = Field(default="", max_length=8000)
    person: StoryPerson | None = None
    character_id: str | None = None
    attach_prev_chapters: int | None = Field(default=None, ge=0, le=5)
    include_markdown_context: bool | None = None
    creative_mode: str | None = None
    persist: bool = True


SyncScope = Literal[
    "all",
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


class SyncPanelsBody(BaseModel):
    """由「结构化同步器」读取对话，将可落盘设定合并进各板块。"""

    user_message: str = Field(min_length=1, max_length=16000)
    assistant_reply: str = Field(min_length=1, max_length=64000)
    persist: bool = False
    scope: SyncScope = "all"
    creative_mode: str | None = None
    proofreader_max_retries: int | None = None  # None → 使用 Settings 默认值


class RefreshRelationsBody(BaseModel):
    """仅重算派系或文化实体的 relations，供关系图与卡片同步。"""

    creative_mode: str | None = None
    persist: bool = True


app = FastAPI(title="Magic Creater World", version="0.1.0")


def _shutdown_request_allowed(request: Request) -> bool:
    """仅允许回环地址触发退出，避免误将服务暴露到公网时被远程关停。"""
    host = (request.client.host if request.client else "") or ""
    if host in ("127.0.0.1", "::1"):
        return True
    if host.startswith("::ffff:") and host[len("::ffff:") :] == "127.0.0.1":
        return True
    return False


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(DevStaticCacheBypassMiddleware)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """避免浏览器默认请求产生无意义 404。"""
    return Response(status_code=204)


@app.get("/")
def serve_index() -> FileResponse:
    """首页与 /static 分离，避免根路径 StaticFiles 抢占 /api/* 导致 404。"""
    index = STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="index.html missing")
    return FileResponse(index, media_type="text/html; charset=utf-8")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def public_config() -> dict[str, Any]:
    from worldforger.config import get_settings

    s = get_settings()
    return {
        "api_base": s.openai_api_base,
        "default_model": s.openai_chat_model,
        "structure_sync_model": (s.structure_sync_model.strip() or s.openai_chat_model),
        "has_api_key": bool(s.paratera_api_key.strip()),
    }


@app.post("/api/shutdown")
def api_shutdown(request: Request) -> dict[str, Any]:
    """结束本地 Uvicorn 进程（工作台「退出」）。仅本机回环可调用。"""
    if not _shutdown_request_allowed(request):
        raise HTTPException(status_code=403, detail="仅允许从本机回环地址关闭服务")

    def _exit_process() -> None:
        import time

        time.sleep(0.35)
        os._exit(0)

    threading.Thread(target=_exit_process, daemon=True).start()
    return {"ok": True, "message": "服务即将停止"}


@app.get("/api/worlds")
def api_list_worlds() -> dict[str, Any]:
    return {"worlds": list_world_briefs()}


@app.post("/api/worlds")
def api_create_world(body: CreateWorldBody) -> dict[str, Any]:
    w = create_world(body.name.strip())
    return {"world": w.model_dump(mode="json")}


@app.get("/api/worlds/{world_id}")
def api_get_world(world_id: str) -> dict[str, Any]:
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found")
    md = load_world_markdown_optional(world_id)
    has_md = bool(md and str(md).strip())
    return {"world": w.model_dump(mode="json"), "has_nonempty_world_md": has_md}


@app.get("/api/worlds/{world_id}/search")
def api_search_world(world_id: str, q: str, limit_json: int = 120, limit_md: int = 80) -> dict[str, Any]:
    """在 world.json 与 world.md 中全文检索（大小写不敏感）；用于跨板块找关键词。"""
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    if not (q or "").strip():
        raise HTTPException(status_code=400, detail="missing or empty query parameter q")
    lj = max(1, min(int(limit_json), 300))
    lm = max(1, min(int(limit_md), 200))
    md = load_world_markdown_optional(world_id)
    try:
        return search_world_payload(
            w.model_dump(mode="json"),
            md,
            q,
            max_json_hits=lj,
            max_md_hits=lm,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/worlds/{world_id}/lint-references")
def api_lint_world_references(world_id: str) -> dict[str, Any]:
    """纯本地：检查地理/派系/文化/历史/境界等跨 id 引用是否指向存在的实体。"""
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    return lint_world_references(w)


@app.post("/api/worlds/{world_id}/fix-references")
def api_fix_world_references(world_id: str, body: FixReferencesBody = FixReferencesBody()) -> dict[str, Any]:
    """
    基于磁盘当前 world 做保守引用修复；dry_run 时只返回将执行的操作与修复后校验结果，不写盘。
    """
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    w2, applied = fix_world_references(w)
    lint_after = lint_world_references(w2)
    if body.dry_run:
        return {
            "dry_run": True,
            "would_apply": applied,
            "apply_count": len(applied),
            "lint_after": lint_after,
        }
    if not applied:
        return {
            "dry_run": False,
            "applied": [],
            "saved": False,
            "world": w.model_dump(mode="json"),
            "lint": lint_world_references(w),
        }
    if w2.meta.id != world_id:
        raise HTTPException(status_code=500, detail="fix produced mismatched meta.id")
    w2.bump_version()
    save_world(w2, export_markdown=True)
    return {
        "dry_run": False,
        "applied": applied,
        "saved": True,
        "world": w2.model_dump(mode="json"),
        "lint": lint_after,
    }


@app.put("/api/worlds/{world_id}")
def api_put_world(world_id: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found")
    try:
        w = World.model_validate(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid world: {e}") from e
    if w.meta.id != world_id:
        raise HTTPException(status_code=400, detail="meta.id must match URL world_id")
    w.bump_version()
    save_world(w, export_markdown=True)
    return w.model_dump(mode="json")


@app.patch("/api/worlds/{world_id}")
def api_patch_world_rename(world_id: str, body: RenameWorldBody) -> dict[str, Any]:
    """仅重命名显示名称（meta.name），不改变磁盘上的 world_id 目录名。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name must not be empty")
    try:
        w = rename_world(world_id, name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return w.model_dump(mode="json")


@app.delete("/api/worlds/{world_id}")
def api_delete_world(world_id: str) -> dict[str, bool]:
    try:
        delete_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    return {"ok": True}


@app.post("/api/worlds/{world_id}/export-md")
def api_export_md(world_id: str) -> dict[str, str]:
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found")
    save_world(w, export_markdown=True)
    return {"ok": "true", "path": str(world_json_path(world_id).with_name("world.md"))}


# ── P2-11: Story Export (EPUB / DOCX / MD) ──────────────────────────


@app.get("/api/worlds/{world_id}/story/export")
def api_story_export(world_id: str, format: str = "md") -> Response:
    """导出小说为 EPUB / DOCX / Markdown 格式。"""
    from urllib.parse import quote

    from worldforger.export_format import export_docx, export_epub, export_markdown

    fmt = (format or "md").strip().lower()
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    # Build safe ASCII fallback + RFC 5987 encoded filename
    raw_name = w.meta.name or "story"
    safe_ascii = "".join(c if c.isascii() and c.isalnum() or c in " _-." else "_" for c in raw_name).strip() or "story"
    encoded = quote(raw_name, safe="")

    if fmt == "epub":
        try:
            content = export_epub(w)
        except ImportError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        return Response(
            content=content,
            media_type="application/epub+zip",
            headers={
                "Content-Disposition": f"attachment; filename=\"{safe_ascii}.epub\"; filename*=UTF-8''{encoded}.epub"
            },
        )
    elif fmt == "docx":
        try:
            content = export_docx(w)
        except ImportError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f"attachment; filename=\"{safe_ascii}.docx\"; filename*=UTF-8''{encoded}.docx"
            },
        )
    else:
        content = export_markdown(w)
        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename=\"{safe_ascii}.md\"; filename*=UTF-8''{encoded}.md"
            },
        )


def _json_for_diff(world_id: str, ref: str) -> dict[str, Any]:
    """ref: `current` 或版本号字符串（如 3）。"""
    r = (ref or "").strip().lower()
    if r in ("", "current"):
        p = world_json_path(world_id)
        if not p.is_file():
            raise HTTPException(status_code=404, detail="world not found")
        return json.loads(p.read_text(encoding="utf-8"))
    if not r.isdigit():
        raise HTTPException(
            status_code=400, detail="left/right must be `current` or a positive integer"
        )
    try:
        return load_snapshot_dict(world_id, int(r))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="snapshot not found") from e


@app.get("/api/worlds/{world_id}/snapshots")
def api_list_snapshots(world_id: str) -> dict[str, Any]:
    try:
        load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    return {"snapshots": list_snapshots(world_id)}


@app.get("/api/worlds/{world_id}/snapshots/diff")
def api_snapshots_diff(world_id: str, left: str | None = None, right: str | None = None) -> dict[str, Any]:
    if left is None or not str(left).strip() or right is None or not str(right).strip():
        raise HTTPException(
            status_code=400,
            detail="queries `left` and `right` are required (each: `current` or a snapshot version number)",
        )
    try:
        load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    dl = _json_for_diff(world_id, str(left))
    dr = _json_for_diff(world_id, str(right))
    lines, truncated = line_diff_json(dl, dr)
    return {
        "left": str(left).strip().lower(),
        "right": str(right).strip().lower(),
        "lines": lines,
        "truncated": truncated,
    }


@app.post("/api/worlds/{world_id}/snapshots/rollback")
def api_snapshot_rollback(world_id: str, body: RollbackSnapshotBody) -> dict[str, Any]:
    try:
        w = rollback_to_snapshot(world_id, body.snapshot_version)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="snapshot not found") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"world": w.model_dump(mode="json")}


@app.delete("/api/worlds/{world_id}/snapshots/{version}")
def api_snapshot_delete(world_id: str, version: int) -> dict[str, object]:
    from worldforger.world_store import delete_snapshot

    try:
        ok = delete_snapshot(world_id, version)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return {"ok": True, "deleted_version": version}


@app.delete("/api/worlds/{world_id}/snapshots")
def api_snapshot_clear(world_id: str) -> dict[str, object]:
    from worldforger.world_store import clear_snapshots

    try:
        n = clear_snapshots(world_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"ok": True, "deleted": n}


@app.post("/api/worlds/{world_id}/chat")
async def api_chat(world_id: str, body: ChatBody) -> dict[str, str]:
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found")

    ctx = world_context_for_prompt(w, include_markdown=body.include_markdown_context)
    system = system_with_world_json(ctx)
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system}]
    mode_eff = (body.mode or "").strip() or w.meta.creative_mode
    addon = chat_mode_system(mode_eff)
    if addon:
        msgs.append({"role": "system", "content": addon})
    tag_addon = genre_tags_prompt_addon(w.meta.genre_tags)
    if tag_addon:
        msgs.append({"role": "system", "content": tag_addon})
    guide_text = chat_guides_content(body.chat_guides)
    if guide_text:
        msgs.append({"role": "system", "content": guide_text})
    for m in body.messages:
        msgs.append({"role": m.role, "content": m.content})
    try:
        reply = await chat_completion(msgs)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}") from e

    _append_session_log(world_id, body.messages, reply)
    return {"reply": reply}


@app.post("/api/worlds/{world_id}/character-chat")
async def api_character_chat(world_id: str, body: ChatBody) -> dict[str, str]:
    """与「世界观构建」同级的人物/卡司对话：系统提示侧重 characters 节。"""
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found")

    ctx = world_context_for_prompt(w, include_markdown=body.include_markdown_context)
    system = character_chat_system_prompt(ctx)
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system}]
    mode_eff = (body.mode or "").strip() or w.meta.creative_mode
    addon = chat_mode_system(mode_eff)
    if addon:
        msgs.append({"role": "system", "content": addon})
    tag_addon = genre_tags_prompt_addon(w.meta.genre_tags)
    if tag_addon:
        msgs.append({"role": "system", "content": tag_addon})
    guide_text = chat_guides_content(body.chat_guides)
    if guide_text:
        msgs.append({"role": "system", "content": guide_text})
    for m in body.messages:
        msgs.append({"role": m.role, "content": m.content})
    try:
        reply = await chat_completion(msgs)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}") from e

    _append_session_log(world_id, body.messages, reply)
    return {"reply": reply}


@app.post("/api/worlds/{world_id}/story-chat")
async def api_story_chat(world_id: str, body: StoryChatBody) -> dict[str, Any]:
    """情节/叙事对话；默认启用工具调用与回复内伏笔/Markdown 自动落盘。"""
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found")

    mode_eff = (body.mode or "").strip() or w.meta.creative_mode
    extra_system: list[str] = []
    addon = chat_mode_system(mode_eff)
    if addon:
        extra_system.append(addon)
    tag_addon = genre_tags_prompt_addon(w.meta.genre_tags)
    if tag_addon:
        extra_system.append(tag_addon)
    guide_text = chat_guides_content(body.chat_guides)
    if guide_text:
        extra_system.append(guide_text)

    msg_dicts = [{"role": m.role, "content": m.content} for m in body.messages]

    if body.use_tools:
        try:
            result = await run_story_chat_agent(
                w,
                msg_dicts,
                active_chapter_id=body.active_chapter_id,
                include_story_files=body.include_story_files,
                creative_mode=mode_eff,
                persist=body.persist_tool_changes,
                writing_prompt=body.writing_prompt,
                person=body.person,
                character_id=body.character_id,
                attach_prev_chapters=body.attach_prev_chapters,
                extra_system=extra_system,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"upstream error: {e}") from e
        _append_session_log(world_id, body.messages, result["reply"])
        return result

    system = story_chat_system_prompt(
        w,
        active_chapter_id=body.active_chapter_id,
        include_story_files=body.include_story_files,
    )
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for s in extra_system:
        msgs.append({"role": "system", "content": s})
    for m in body.messages:
        msgs.append({"role": m.role, "content": m.content})
    try:
        reply = await chat_completion(msgs)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}") from e

    _append_session_log(world_id, body.messages, reply)
    return {"reply": reply, "world": w.model_dump(mode="json"), "actions": [], "intent": None}


@app.post("/api/worlds/{world_id}/sync-panels-from-chat")
async def api_sync_panels_from_chat(world_id: str, body: SyncPanelsBody) -> dict[str, Any]:
    """
    第二路 Agent：把对话中的设定抽成 world.json 各板块结构，供前端表单展示。
    persist=true 时写盘并 bump 版本；默认仅返回合并结果由用户再点保存。
    """
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found")
    mode_eff = (body.creative_mode or "").strip() or w.meta.creative_mode
    pr_max_retries = (
        body.proofreader_max_retries
        if body.proofreader_max_retries is not None
        else get_settings().proofreader_max_retries
    )
    result = await sync_panels_from_dialogue(
        w,
        user_message=body.user_message,
        assistant_reply=body.assistant_reply,
        scope=body.scope,
        creative_mode=mode_eff,
        proofreader_max_retries=pr_max_retries,
    )
    if not result.get("ok"):
        # sync_panels_from_dialogue returns ok=False on parse/recovery failure;
        # world is the original World model (not a dict) in the error path
        w_out = result["world"]
        world_dict = w_out.model_dump(mode="json") if hasattr(w_out, "model_dump") else w_out
        return {
            "ok": False,
            "error": result.get("error", "structure sync error"),
            "world": world_dict,
            "updated_sections": result.get("updated_sections") or [],
            "patch": result.get("applied_patch") or {},
            "structure_output_keys": result.get("structure_output_keys") or [],
            "scope_applied": result.get("scope_applied") or body.scope,
            "merge_warnings": result.get("merge_warnings") or [],
            "normalize_notes": result.get("normalize_notes") or {},
            "proofreader_rounds": result.get("proofreader_rounds") or 0,
            "proofreader_final_verdict": result.get("proofreader_final_verdict") or "error",
            "proofreader_issues": result.get("proofreader_issues") or [],
            "format_proofreader_used": result.get("format_proofreader_used", False),
            "format_stages": result.get("format_stages") or [],
        }

    merged = result["world"]
    print(f"[MCW-API] Sync result updated_sections: {result['updated_sections']}")
    print(f"[MCW-API] Sync result merge_warnings: {result['merge_warnings']}")
    print(f"[MCW-API] Sync result proofreader_rounds: {result['proofreader_rounds']}")
    if result['updated_sections']:
        for key in result['updated_sections']:
            section = getattr(merged, key, None)
            if section is not None:
                if hasattr(section, 'tiers'):
                    print(f"[MCW-API] merged.{key}.tiers count: {len(section.tiers or [])}")
                if hasattr(section, 'entities'):
                    print(f"[MCW-API] merged.{key}.entities count: {len(section.entities or [])}")
    if body.persist:
        merged.bump_version()
        save_world(merged, export_markdown=True)
    return {
        "ok": True,
        "world": merged.model_dump(mode="json"),
        "updated_sections": result["updated_sections"],
        "patch": result["applied_patch"],
        "structure_output_keys": result["structure_output_keys"],
        "scope_applied": result["scope_applied"],
        "merge_warnings": result["merge_warnings"],
        "normalize_notes": result.get("normalize_notes") or {},
        "proofreader_rounds": result["proofreader_rounds"],
        "proofreader_final_verdict": result["proofreader_final_verdict"],
        "proofreader_issues": result["proofreader_issues"],
        "format_proofreader_used": result.get("format_proofreader_used", False),
        "format_stages": result.get("format_stages", []),
    }


@app.post("/api/worlds/{world_id}/refresh/faction-relations")
async def api_refresh_faction_relations(
    world_id: str, body: RefreshRelationsBody | None = None
) -> dict[str, Any]:
    """
    根据当前 factions 设定调用 LLM，重写各派系 relations；可选写盘。
    """
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    eff = body or RefreshRelationsBody()
    if not w.factions.entities:
        return {
            "ok": True,
            "world": w.model_dump(mode="json"),
            "warnings": ["当前无派系实体，未调用模型"],
            "persisted": False,
        }
    try:
        merged, warnings = await refresh_world_faction_relations(
            w, creative_mode=eff.creative_mode
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except (ValueError, json.JSONDecodeError, TypeError) as e:
        return {
            "ok": False,
            "error": str(e),
            "world": w.model_dump(mode="json"),
            "warnings": [],
            "persisted": False,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"relation refresh error: {e}") from e

    persisted = False
    if eff.persist:
        merged.bump_version()
        save_world(merged, export_markdown=True)
        persisted = True
    return {
        "ok": True,
        "world": merged.model_dump(mode="json"),
        "warnings": warnings,
        "persisted": persisted,
    }


@app.post("/api/worlds/{world_id}/refresh/culture-relations")
async def api_refresh_culture_relations(
    world_id: str, body: RefreshRelationsBody | None = None
) -> dict[str, Any]:
    """
    根据当前 cultures 设定调用 LLM，重写各实体 relations；可选写盘。
    """
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    eff = body or RefreshRelationsBody()
    if not w.cultures.entities:
        return {
            "ok": True,
            "world": w.model_dump(mode="json"),
            "warnings": ["当前无文化/宗教实体，未调用模型"],
            "persisted": False,
        }
    try:
        merged, warnings = await refresh_world_culture_relations(
            w, creative_mode=eff.creative_mode
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except (ValueError, json.JSONDecodeError, TypeError) as e:
        return {
            "ok": False,
            "error": str(e),
            "world": w.model_dump(mode="json"),
            "warnings": [],
            "persisted": False,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"relation refresh error: {e}") from e

    persisted = False
    if eff.persist:
        merged.bump_version()
        save_world(merged, export_markdown=True)
        persisted = True
    return {
        "ok": True,
        "world": merged.model_dump(mode="json"),
        "warnings": warnings,
        "persisted": persisted,
    }


@app.post("/api/worlds/{world_id}/outline")
async def api_outline(world_id: str, body: OutlineBody) -> dict[str, str]:
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found")

    world_block = world_context_for_prompt(
        w, include_markdown=body.include_markdown_context
    )
    mode_eff = (body.creative_mode or "").strip() or w.meta.creative_mode
    system = outline_system_prompt(body.kind, world_block, creative_mode=mode_eff)
    tag_addon = genre_tags_prompt_addon(w.meta.genre_tags)
    if tag_addon:
        system = system + "\n\n" + tag_addon
    user = body.prompt.strip()
    try:
        reply = await chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.75,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}") from e

    filename = "characters.md" if body.kind == "characters" else "plot_outline.md"
    out = outlines_dir(world_id) / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    cm = mode_eff or ""
    header = (
        "---\n"
        f"based_on_world_id: {w.meta.id}\n"
        f"based_on_world_version: {w.meta.version}\n"
        f"kind: {body.kind}\n"
        f"creative_mode: {cm}\n"
        f"generated_at: {ts}\n"
        "---\n\n"
    )
    out.write_text(header + reply, encoding="utf-8")
    return {"reply": reply, "saved": str(out)}


def _story_world_or_404(world_id: str) -> World:
    try:
        return load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None


def _maybe_persist_story(world_id: str, w: World, *, persist: bool) -> None:
    if persist:
        w.bump_version()
        save_world(w, export_markdown=False)


@app.get("/api/worlds/{world_id}/story")
def api_get_story(world_id: str) -> dict[str, Any]:
    w = _story_world_or_404(world_id)
    imported = try_import_legacy(w)
    if imported:
        save_world(w, export_markdown=False)
    w, sync_notes = reconcile_story_chapters(w)
    if sync_notes:
        w.bump_version()
        save_world(w, export_markdown=False)
    apply_unit_label_from_mode(w, w.meta.creative_mode)
    return {
        "story": w.story.model_dump(mode="json"),
        "unit_label": resolve_unit_label(w),
        "legacy_imported": imported,
        "chapter_sync_notes": sync_notes,
        "chapters_display": chapter_display_for_prompt(w),
    }


@app.post("/api/worlds/{world_id}/story/import-legacy-outline")
def api_story_import_legacy(world_id: str) -> dict[str, Any]:
    w = _story_world_or_404(world_id)
    ok = try_import_legacy(w)
    if ok:
        w.bump_version()
        save_world(w, export_markdown=False)
    return {"ok": ok, "content": read_text(macro_outline_path(world_id))}


@app.get("/api/worlds/{world_id}/story/macro-outline")
def api_get_macro_outline(world_id: str) -> dict[str, str]:
    _story_world_or_404(world_id)
    return {"content": read_text(macro_outline_path(world_id))}


@app.put("/api/worlds/{world_id}/story/macro-outline")
def api_put_macro_outline(world_id: str, body: StoryTextBody) -> dict[str, Any]:
    w = _story_world_or_404(world_id)
    write_text(macro_outline_path(world_id), body.content)
    w.story.outline_macro.updated_at = utc_now_iso()
    w.bump_version()
    save_world(w, export_markdown=False)
    return {"ok": True, "updated_at": w.story.outline_macro.updated_at}


@app.get("/api/worlds/{world_id}/story/chapters/{chapter_id}/beat")
def api_get_chapter_beat(world_id: str, chapter_id: str) -> dict[str, str]:
    _story_world_or_404(world_id)
    return {"content": read_text(beat_path(world_id, chapter_id))}


@app.put("/api/worlds/{world_id}/story/chapters/{chapter_id}/beat")
def api_put_chapter_beat(world_id: str, chapter_id: str, body: StoryTextBody) -> dict[str, Any]:
    w = _story_world_or_404(world_id)
    if not any(c.id == chapter_id for c in w.story.chapters):
        raise HTTPException(status_code=404, detail="chapter not found")
    write_text(beat_path(world_id, chapter_id), body.content)
    ch = next((c for c in w.story.chapters if c.id == chapter_id), None)
    title_synced = False
    if ch:
        beat_title = title_from_beat_markdown(body.content)
        if beat_title and beat_title != (ch.title or "").strip():
            ch.title = beat_title
            title_synced = True
    if title_synced:
        w.bump_version()
        save_world(w, export_markdown=False)
    return {"ok": True, "title_synced": title_synced, "chapter": ch.model_dump(mode="json") if ch else None}


@app.get("/api/worlds/{world_id}/story/chapters/{chapter_id}/manuscript")
def api_get_chapter_manuscript(world_id: str, chapter_id: str) -> dict[str, str]:
    _story_world_or_404(world_id)
    return {"content": read_text(manuscript_path(world_id, chapter_id))}


@app.put("/api/worlds/{world_id}/story/chapters/{chapter_id}/manuscript")
def api_put_chapter_manuscript(
    world_id: str, chapter_id: str, body: StoryTextBody
) -> dict[str, Any]:
    w = _story_world_or_404(world_id)
    if not any(c.id == chapter_id for c in w.story.chapters):
        raise HTTPException(status_code=404, detail="chapter not found")
    write_text(manuscript_path(world_id, chapter_id), body.content)
    n = sync_chapter_word_count(w, chapter_id)
    # P2-9: Auto-save version snapshot
    from worldforger.story_store import save_chapter_snapshot
    snap_v = save_chapter_snapshot(world_id, chapter_id)
    w.bump_version()
    save_world(w, export_markdown=False)
    return {"ok": True, "word_count": n, "snapshot_version": snap_v}


@app.post("/api/worlds/{world_id}/story/chapters")
def api_create_story_chapter(world_id: str, body: StoryChapterCreateBody) -> dict[str, Any]:
    w = _story_world_or_404(world_id)
    ch = add_chapter(w, title=body.title, order=body.order)
    apply_unit_label_from_mode(w, w.meta.creative_mode)
    w.bump_version()
    save_world(w, export_markdown=False)
    return {"chapter": ch.model_dump(mode="json"), "world": w.model_dump(mode="json")}


@app.delete("/api/worlds/{world_id}/story/chapters/{chapter_id}")
def api_delete_story_chapter(world_id: str, chapter_id: str) -> dict[str, Any]:
    w = _story_world_or_404(world_id)
    if not remove_chapter(w, chapter_id):
        raise HTTPException(status_code=404, detail="chapter not found")
    w.bump_version()
    save_world(w, export_markdown=False)
    return {"ok": True, "world": w.model_dump(mode="json")}


# ── P2: Chapter batch operations ──────────────────────────────────────

class StoryChapterBatchBody(BaseModel):
    action: str  # "delete", "reorder", "status"
    chapter_ids: list[str] = Field(default_factory=list)
    # For reorder: new order list of {id, order}
    orders: list[dict] | None = None
    # For status batch change
    new_status: str | None = None


@app.post("/api/worlds/{world_id}/story/chapters/batch")
def api_batch_chapters(world_id: str, body: StoryChapterBatchBody) -> dict[str, Any]:
    """Batch operations on chapters: delete, reorder, status change."""
    w = _story_world_or_404(world_id)
    chapters = w.story.chapters
    action = body.action

    if action == "delete":
        ids = set(body.chapter_ids)
        kept = [c for c in chapters if c.id not in ids]
        w.story.chapters = kept
        if kept:
            for i, c in enumerate(kept):
                c.order = i + 1

    elif action == "reorder":
        if body.orders:
            order_map = {item.get("id"): item.get("order", 0) for item in body.orders if isinstance(item, dict)}
            for c in chapters:
                if c.id in order_map:
                    c.order = order_map[c.id]

    elif action == "status":
        new_status = body.new_status
        if new_status in {"planned", "outline", "drafting", "revising", "locked", "done", "archived"}:
            ids = set(body.chapter_ids)
            for c in chapters:
                if c.id in ids:
                    c.status = new_status  # type: ignore[assignment]

    else:
        raise HTTPException(status_code=400, detail=f"unknown action: {action}")

    w.bump_version()
    save_world(w, export_markdown=False)
    return {"ok": True, "world": w.model_dump(mode="json")}


# ── P2-9: Chapter Version Snapshots ──────────────────────────────────


@app.get("/api/worlds/{world_id}/story/chapters/{chapter_id}/snapshots")
def api_list_chapter_snapshots(world_id: str, chapter_id: str) -> dict[str, Any]:
    """列出某章的所有版本快照。"""
    from worldforger.story_store import list_chapter_snapshots
    _story_world_or_404(world_id)
    return {"snapshots": list_chapter_snapshots(world_id, chapter_id)}


@app.get("/api/worlds/{world_id}/story/chapters/{chapter_id}/snapshots/{version}")
def api_get_chapter_snapshot(world_id: str, chapter_id: str, version: int) -> dict[str, Any]:
    """获取某章某个版本的快照内容。"""
    from worldforger.story_store import read_chapter_snapshot
    _story_world_or_404(world_id)
    try:
        content = read_chapter_snapshot(world_id, chapter_id, version)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="snapshot not found") from None
    return {"version": version, "content": content}


@app.get("/api/worlds/{world_id}/story/chapters/{chapter_id}/snapshots/diff")
def api_chapter_snapshot_diff(
    world_id: str, chapter_id: str, left: str = "", right: str = ""
) -> dict[str, Any]:
    """对比章节两个版本之间的差异（left/right 为版本号或 'current'）。"""
    from worldforger.snapshot_diff import line_diff_text
    from worldforger.story_store import manuscript_path, read_chapter_snapshot, read_text

    _story_world_or_404(world_id)

    def _resolve(ref: str) -> str:
        r = ref.strip()
        if r == "current" or r == "":
            return read_text(manuscript_path(world_id, chapter_id))
        if r.isdigit():
            return read_chapter_snapshot(world_id, chapter_id, int(r))
        raise HTTPException(status_code=400, detail=f"invalid version ref: {ref!r}")

    try:
        left_text = _resolve(left)
        right_text = _resolve(right)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise

    lines, truncated = line_diff_text(left_text, right_text)
    return {"left": left, "right": right, "lines": lines, "truncated": truncated}


@app.post("/api/worlds/{world_id}/story/generate/macro-outline")
async def api_story_generate_macro(world_id: str, body: StoryGenerateMacroBody) -> dict[str, Any]:
    w = _story_world_or_404(world_id)
    try:
        reply = await generate_macro_outline(
            w,
            prompt=body.prompt,
            creative_mode=body.creative_mode,
            include_world_md=body.include_markdown_context,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}") from e
    _maybe_persist_story(world_id, w, persist=body.persist)
    return {"reply": reply, "world": w.model_dump(mode="json")}


@app.post("/api/worlds/{world_id}/story/generate/chapter-beats")
async def api_story_generate_beats(world_id: str, body: StoryGenerateBeatsBody) -> dict[str, Any]:
    w = _story_world_or_404(world_id)
    ids = body.chapter_ids or [c.id for c in w.story.chapters]
    if not ids:
        raise HTTPException(status_code=400, detail="no chapters to generate beats for")
    try:
        beats = await generate_chapter_beats(
            w,
            chapter_ids=ids,
            prompt=body.prompt,
            creative_mode=body.creative_mode,
            include_world_md=body.include_markdown_context,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}") from e
    _maybe_persist_story(world_id, w, persist=body.persist)
    return {"beats": beats, "world": w.model_dump(mode="json")}


@app.post("/api/worlds/{world_id}/story/generate/manuscript")
async def api_story_generate_manuscript(
    world_id: str, body: StoryGenerateManuscriptBody
) -> dict[str, Any]:
    w = _story_world_or_404(world_id)
    if not any(c.id == body.chapter_id for c in w.story.chapters):
        raise HTTPException(status_code=404, detail="chapter not found")
    if body.character_id is not None:
        w.story.narrator.character_id = body.character_id.strip()
    attach = (
        body.attach_prev_chapters
        if body.attach_prev_chapters is not None
        else w.story.writing_defaults.attach_prev_chapters
    )
    prompt_parts = [p for p in (body.last_user_message.strip(), body.prompt.strip()) if p]
    prompt_eff = "\n\n".join(prompt_parts) or "请撰写本章正文。"
    try:
        reply, hook_errors, timing_breakdown = await generate_manuscript(
            w,
            chapter_id=body.chapter_id,
            prompt=prompt_eff,
            creative_mode=body.creative_mode,
            person=body.person,
            attach_prev_chapters=attach,
            include_world_md=body.include_markdown_context,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}") from e
    _maybe_persist_story(world_id, w, persist=body.persist)
    ch = next((c for c in w.story.chapters if c.id == body.chapter_id), None)
    return {
        "reply": reply,
        "hook_errors": hook_errors,
        "world": w.model_dump(mode="json"),
        "timing_breakdown": timing_breakdown,
        "polish_rounds": ch.polish_rounds if ch else 0,
    }


@app.post("/api/worlds/{world_id}/story/generate/manuscript/stream")
async def api_story_generate_manuscript_stream(world_id: str, body: StoryGenerateManuscriptBody) -> StreamingResponse:
    """Stream manuscript generation via Server-Sent Events.

    Events emitted:
      - ``data: {"type":"text","content":"..."}`` — token chunks
      - ``data: {"type":"hook_errors","errors":["..."]}`` — post-processing issues
      - ``data: {"type":"done","world":{...}}`` — completion with updated world
    """
    import json as _json

    w = _story_world_or_404(world_id)
    if not any(c.id == body.chapter_id for c in w.story.chapters):
        raise HTTPException(status_code=404, detail="chapter not found in story.chapters")
    attach = (
        body.attach_prev_chapters
        if body.attach_prev_chapters is not None
        else w.story.writing_defaults.attach_prev_chapters
    )
    prompt_parts = [p for p in (body.last_user_message.strip(), body.prompt.strip()) if p]
    prompt_eff = "\n\n".join(prompt_parts) or "请撰写本章正文。"

    async def event_stream():
        try:
            async for event in generate_manuscript_stream(
                w,
                chapter_id=body.chapter_id,
                prompt=prompt_eff,
                creative_mode=body.creative_mode,
                person=body.person,
                attach_prev_chapters=attach,
                include_world_md=body.include_markdown_context,
            ):
                yield f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            if body.persist:
                _maybe_persist_story(world_id, w, persist=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/worlds/{world_id}/story/rag/stats")
def api_story_rag_stats(world_id: str) -> dict[str, object]:
    """返回当前世界 RAG 索引的统计信息。"""
    from worldforger.chapter_indexer import ChapterIndexer

    try:
        stats = ChapterIndexer(world_id).get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    ready = stats.get("total_chunks", 0) > 0
    return {"ready": ready, **stats}


# ── Polish-only (re-polish existing manuscript) ──────────────────────

@app.post("/api/worlds/{world_id}/story/generate/polish-only")
async def api_story_polish_only(
    world_id: str, body: StoryGenerateManuscriptBody
) -> dict[str, Any]:
    """Re-run the polish loop on an existing manuscript without regenerating."""
    from worldforger.story_service import _run_polish_loop

    w = _story_world_or_404(world_id)
    if not any(c.id == body.chapter_id for c in w.story.chapters):
        raise HTTPException(status_code=404, detail="chapter not found")
    existing = read_text(manuscript_path(world_id, body.chapter_id))
    if not existing.strip():
        raise HTTPException(status_code=400, detail="该章节暂无文稿，请先生成。")

    # Enable polisher temporarily
    was_enabled = w.story.writing_defaults.enable_polisher
    w.story.writing_defaults.enable_polisher = True
    try:
        polished = await _run_polish_loop(w, body.chapter_id, existing)
    finally:
        w.story.writing_defaults.enable_polisher = was_enabled

    sync_chapter_word_count(w, body.chapter_id)
    _maybe_persist_story(world_id, w, persist=body.persist)
    ch = next((c for c in w.story.chapters if c.id == body.chapter_id), None)
    return {
        "reply": polished,
        "world": w.model_dump(mode="json"),
        "polish_rounds": ch.polish_rounds if ch else 0,
    }


# ── Layer 3: Narrative KG ──────────────────────────────────────────


@app.get("/api/worlds/{world_id}/story/narrative-kg")
def api_get_narrative_kg(world_id: str) -> dict[str, Any]:
    """返回叙事知识图谱的完整 JSON，供前端可视化。"""
    from worldforger.narrative_kg import NarrativeKGManager

    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    mgr = NarrativeKGManager(world_id)
    kg = w.story.narrative_kg
    # Ensure we have the latest from disk
    disk_kg = mgr.load()
    if disk_kg.entities or disk_kg.events:
        kg = disk_kg
    return {"narrative_kg": kg.model_dump(mode="json")}


# ── Layer 3: Consistency Reports ────────────────────────────────────


@app.get("/api/worlds/{world_id}/story/consistency-report/{chapter_id}")
def api_get_consistency_report(world_id: str, chapter_id: str) -> dict[str, Any]:
    """返回指定章节的一致性审校报告。"""
    from worldforger.story_store import read_consistency_report

    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    ch = next((c for c in w.story.chapters if c.id == chapter_id), None)
    if not ch:
        raise HTTPException(status_code=404, detail="chapter not found")
    report = ch.consistency_report
    if not report:
        disk = read_consistency_report(world_id, chapter_id)
        if disk:
            from worldforger.schemas import ConsistencyReport
            try:
                report = ConsistencyReport(**disk)
            except Exception:
                pass
    if not report:
        return {"consistency_report": None}
    return {"consistency_report": report.model_dump(mode="json")}


# ── Layer 3: Sentiment Arc ──────────────────────────────────────────


@app.get("/api/worlds/{world_id}/story/sentiment-arc")
def api_get_sentiment_arc(world_id: str) -> dict[str, Any]:
    """返回所有情感日志 + 情感弧线图数据。"""
    from worldforger.sentiment_tracker import SentimentTracker

    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    tracker = SentimentTracker(world_id)
    logs = tracker.get_all_logs(w)
    chart_data = tracker.build_sentiment_arc_chart(w)
    return {
        "sentiment_logs": [log.model_dump(mode="json") for log in logs],
        "chart_data": chart_data,
    }


# ── P1-6: Usage Stats ───────────────────────────────────────────────


@app.get("/api/worlds/{world_id}/story/usage-stats")
def api_get_usage_stats(world_id: str) -> dict[str, Any]:
    """返回每章各类 LLM 调用的估算 token 消耗和总预算。"""
    from worldforger.story_service import compute_usage_stats

    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    return compute_usage_stats(w)


# ── P2-12: Writing Statistics Dashboard ──────────────────────────────


@app.get("/api/worlds/{world_id}/story/stats")
def api_get_story_stats(world_id: str) -> dict[str, Any]:
    """聚合写作统计数据：字数、进度、伏笔、情感分布。"""
    from worldforger.story_store import (
        count_words,
        manuscript_path,
        read_sentiment_log,
        read_text,
        sorted_chapters,
    )

    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    chapters = sorted_chapters(w)
    wid = world_id

    # Per-chapter stats
    chapter_stats: list[dict] = []
    total_words = 0
    for ch in chapters:
        ms = read_text(manuscript_path(wid, ch.id))
        wc = ch.word_count or count_words(ms)
        total_words += wc
        chapter_stats.append({
            "id": ch.id,
            "title": ch.title,
            "order": ch.order,
            "word_count": wc,
            "status": ch.status or "outline",
        })

    # Foreshadowing stats
    foreshadowing = {
        "total": len(w.story.foreshadowing),
        "open": sum(1 for f in w.story.foreshadowing if f.status == "planted"),
        "resolved": sum(1 for f in w.story.foreshadowing if f.status == "resolved"),
        "abandoned": sum(1 for f in w.story.foreshadowing if f.status == "abandoned"),
    }

    # Sentiment distribution across all chapters
    sentiment_dist: dict[str, int] = {}
    sentiment_logs = []
    for ch in chapters:
        log = read_sentiment_log(wid, ch.id)
        if log:
            sentiment_logs.append(log)
            tone = log.get("overall_tone", "")
            if tone:
                sentiment_dist[tone] = sentiment_dist.get(tone, 0) + 1

    # Completion ratio
    locked = sum(1 for c in chapters if c.status == "locked")
    completed = sum(1 for c in chapters if c.status == "completed")
    drafting = sum(1 for c in chapters if c.status == "drafting")

    return {
        "total_words": total_words,
        "chapter_count": len(chapters),
        "chapter_progress": chapter_stats,
        "completion": {
            "locked": locked,
            "completed": completed,
            "drafting": drafting,
            "outline": len(chapters) - locked - completed - drafting,
        },
        "foreshadowing": foreshadowing,
        "sentiment_distribution": sentiment_dist,
        "sentiment_logs": sentiment_logs,
    }


# ── Layer 3: Writing Defaults Toggle ────────────────────────────────


@app.patch("/api/worlds/{world_id}/story/writing-defaults")
def api_patch_story_writing_defaults(
    world_id: str, body: StoryWritingDefaultsPatchBody
) -> dict[str, Any]:
    """切换 Layer 3 / Layer 4 功能的开关。"""
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    wd = w.story.writing_defaults
    changed = False
    if body.enable_narrative_kg is not None:
        wd.enable_narrative_kg = body.enable_narrative_kg
        changed = True
    if body.enable_consistency_check is not None:
        wd.enable_consistency_check = body.enable_consistency_check
        changed = True
    if body.enable_sentiment_track is not None:
        wd.enable_sentiment_track = body.enable_sentiment_track
        changed = True
    if body.enable_polisher is not None:
        wd.enable_polisher = body.enable_polisher
        changed = True
    if body.polish_max_rounds is not None:
        wd.polish_max_rounds = body.polish_max_rounds
        changed = True
    if body.enable_knowledge_track is not None:
        wd.enable_knowledge_track = body.enable_knowledge_track
        changed = True
    if body.enable_decision_track is not None:
        wd.enable_decision_track = body.enable_decision_track
        changed = True
    if body.enable_physical_state_track is not None:
        wd.enable_physical_state_track = body.enable_physical_state_track
        changed = True
    if body.enable_personal_timeline_track is not None:
        wd.enable_personal_timeline_track = body.enable_personal_timeline_track
        changed = True
    if changed:
        w.bump_version()
        save_world(w, export_markdown=False)
    return {
        "writing_defaults": wd.model_dump(mode="json"),
        "changed": changed,
    }


# ── Layer 4: Polished Manuscript ────────────────────────────────────────


@app.get("/api/worlds/{world_id}/story/manuscript/{chapter_id}/polished")
def api_get_polished_manuscript(world_id: str, chapter_id: str) -> dict[str, Any]:
    """获取某章的润色稿。"""
    from worldforger.story_store import polished_path, read_text

    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    pp = polished_path(world_id, chapter_id)
    polished_text = read_text(pp)

    ch = next((c for c in w.story.chapters if c.id == chapter_id), None)
    return {
        "chapter_id": chapter_id,
        "polished_text": polished_text,
        "polished_file": ch.polished_file if ch else "",
        "polish_rounds": ch.polish_rounds if ch else 0,
        "polish_issue_tracking": ch.polish_issue_tracking if ch else None,
    }


@app.get("/api/worlds/{world_id}/story/manuscript/{chapter_id}/polish-trace")
def api_get_polish_trace(world_id: str, chapter_id: str) -> dict[str, Any]:
    """获取某章的审校↔润色循环追踪记录。"""
    import json as _json

    from worldforger.story_store import polish_trace_path

    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    tp = polish_trace_path(world_id, chapter_id)
    if not tp.is_file():
        return {"chapter_id": chapter_id, "trace": None}

    return {
        "chapter_id": chapter_id,
        "trace": _json.loads(tp.read_text(encoding="utf-8")),
    }


# ── Token Usage ─────────────────────────────────────────────────────

@app.get("/api/worlds/{world_id}/token-usage")
def api_token_usage(world_id: str) -> dict[str, Any]:
    """Return actual token usage statistics for *world_id*.

    Merges session-level (in-memory) usage with persisted per-chapter
    records from ``token_usage.json``.
    """
    from worldforger.llm import get_token_usage
    from worldforger.story_store import read_token_usage

    try:
        _ = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    saved = read_token_usage(world_id)
    live_session = get_token_usage()

    # Prefer live session; fall back to persisted last_session
    session = live_session if live_session else saved.get("last_session", {})

    s_prompt = sum(v.get("prompt_tokens", 0) for v in session.values())
    s_completion = sum(v.get("completion_tokens", 0) for v in session.values())
    saved_prompt = saved.get("prompt_tokens", 0) or 0
    saved_completion = saved.get("completion_tokens", 0) or 0

    # Per-chapter breakdown
    by_chapter = saved.get("by_chapter", {})
    if not isinstance(by_chapter, dict):
        by_chapter = {}
    persisted_by_label = saved.get("by_label", {})
    if not isinstance(persisted_by_label, dict):
        persisted_by_label = {}

    return {
        "world_id": world_id,
        "session": {
            "prompt_tokens": s_prompt,
            "completion_tokens": s_completion,
            "total_tokens": s_prompt + s_completion,
            "by_label": session,
        },
        "persisted": {
            "prompt_tokens": saved_prompt,
            "completion_tokens": saved_completion,
            "total_tokens": saved_prompt + saved_completion,
            "by_chapter": by_chapter,
            "by_label": persisted_by_label,
        },
        "total": {
            "prompt_tokens": s_prompt + saved_prompt,
            "completion_tokens": s_completion + saved_completion,
            "total_tokens": s_prompt + saved_prompt + s_completion + saved_completion,
        },
    }


# ── Character Knowledge Graph ────────────────────────────────────────

@app.get("/api/worlds/{world_id}/knowledge-graph")
def api_get_knowledge_graph(world_id: str) -> dict[str, Any]:
    """Return the full character knowledge graph."""
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    return {
        "world_id": world_id,
        "entries": [e.model_dump(mode="json") for e in w.character_knowledge.entries],
        "total_entries": len(w.character_knowledge.entries),
    }


@app.post("/api/worlds/{world_id}/knowledge-graph/clear")
def api_clear_knowledge_graph(world_id: str) -> dict[str, Any]:
    """Clear all knowledge entries (useful for resetting after major rewrites)."""
    w = _story_world_or_404(world_id)
    w.character_knowledge.entries = []
    w.bump_version()
    save_world(w, export_markdown=False)
    return {"ok": True, "world": w.model_dump(mode="json")}


# ── P1: Character Decisions ────────────────────────────────────

@app.get("/api/worlds/{world_id}/decisions")
def api_get_decisions(world_id: str) -> dict[str, Any]:
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    return {
        "world_id": world_id,
        "decisions": [d.model_dump(mode="json") for d in w.character_decisions],
        "total": len(w.character_decisions),
    }


@app.post("/api/worlds/{world_id}/decisions/extract-all")
async def api_extract_all_decisions(world_id: str) -> dict[str, Any]:
    """Scan all existing chapter manuscripts and extract character decisions."""
    import asyncio as _asyncio

    w = _story_world_or_404(world_id)
    chapters = [c for c in w.story.chapters if c.status not in ("planned", "outline")]
    if not chapters:
        return {"ok": True, "total_new": 0, "by_chapter": {}, "message": "没有可提取的章节"}

    from worldforger.story_store import manuscript_path, read_text
    from worldforger.story_service import _try_detect_decisions

    results = {}
    sem = _asyncio.Semaphore(3)

    async def _extract_one(ch) -> dict:
        async with sem:
            ms = read_text(manuscript_path(world_id, ch.id))
            if not ms.strip():
                return {"chapter_id": ch.id, "skipped": True}
            await _asyncio.sleep(3)
            prev = len(w.character_decisions)
            err = await _try_detect_decisions(w, ch.id, ms)
            new_count = len(w.character_decisions) - prev
            return {"chapter_id": ch.id, "new": new_count, "error": err} if err else {"chapter_id": ch.id, "new": new_count}

    chapter_results = await _asyncio.gather(*[_extract_one(ch) for ch in chapters])
    total_new = 0
    for r in chapter_results:
        results[r["chapter_id"]] = {k: v for k, v in r.items() if k != "chapter_id"}
        total_new += r.get("new", 0)

    w.bump_version()
    save_world(w, export_markdown=False)
    return {"ok": True, "total_new": total_new, "total": len(w.character_decisions), "by_chapter": results, "world": w.model_dump(mode="json")}


# ── P1: Physical State ──────────────────────────────────────

@app.get("/api/worlds/{world_id}/physical-states")
def api_get_physical_states(world_id: str) -> dict[str, Any]:
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    return {
        "world_id": world_id,
        "physical_states": [ps.model_dump(mode="json") for ps in w.character_physical_states],
    }


@app.post("/api/worlds/{world_id}/physical-states/extract-all")
async def api_extract_all_physical_states(world_id: str) -> dict[str, Any]:
    """Scan all existing chapter manuscripts and extract physical states."""
    import asyncio as _asyncio

    w = _story_world_or_404(world_id)
    chapters = [c for c in w.story.chapters if c.status not in ("planned", "outline")]
    if not chapters:
        return {"ok": True, "total_new": 0, "by_chapter": {}, "message": "没有可提取的章节"}

    from worldforger.story_store import manuscript_path, read_text
    from worldforger.story_service import _try_update_physical_states

    results = {}
    sem = _asyncio.Semaphore(3)

    async def _extract_one(ch) -> dict:
        async with sem:
            ms = read_text(manuscript_path(world_id, ch.id))
            if not ms.strip():
                return {"chapter_id": ch.id, "skipped": True}
            await _asyncio.sleep(3)
            prev = len(w.character_physical_states)
            err = await _try_update_physical_states(w, ch.id, ms)
            new_count = len(w.character_physical_states) - prev
            return {"chapter_id": ch.id, "new": new_count, "error": err} if err else {"chapter_id": ch.id, "new": new_count}

    chapter_results = await _asyncio.gather(*[_extract_one(ch) for ch in chapters])
    total_new = 0
    for r in chapter_results:
        results[r["chapter_id"]] = {k: v for k, v in r.items() if k != "chapter_id"}
        total_new += r.get("new", 0)

    w.bump_version()
    save_world(w, export_markdown=False)
    return {"ok": True, "total_new": total_new, "total": len(w.character_physical_states), "by_chapter": results, "world": w.model_dump(mode="json")}


# ── P2: Personal Timelines ──────────────────────────────────

@app.get("/api/worlds/{world_id}/personal-timelines")
def api_get_personal_timelines(world_id: str) -> dict[str, Any]:
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    return {
        "world_id": world_id,
        "timelines": [tl.model_dump(mode="json") for tl in w.character_personal_timelines],
    }


@app.post("/api/worlds/{world_id}/personal-timelines/extract-all")
async def api_extract_all_timelines(world_id: str) -> dict[str, Any]:
    """Scan all existing chapter manuscripts and extract personal timeline events."""
    import asyncio as _asyncio

    w = _story_world_or_404(world_id)
    chapters = [c for c in w.story.chapters if c.status not in ("planned", "outline")]
    if not chapters:
        return {"ok": True, "total_new": 0, "by_chapter": {}, "message": "没有可提取的章节"}

    from worldforger.story_store import manuscript_path, read_text
    from worldforger.story_service import _try_detect_timeline_events

    results = {}
    sem = _asyncio.Semaphore(3)

    async def _extract_one(ch) -> dict:
        async with sem:
            ms = read_text(manuscript_path(world_id, ch.id))
            if not ms.strip():
                return {"chapter_id": ch.id, "skipped": True}
            await _asyncio.sleep(3)
            prev = sum(len(tl.events) for tl in w.character_personal_timelines)
            err = await _try_detect_timeline_events(w, ch.id, ms)
            new_count = sum(len(tl.events) for tl in w.character_personal_timelines) - prev
            return {"chapter_id": ch.id, "new": new_count, "error": err} if err else {"chapter_id": ch.id, "new": new_count}

    chapter_results = await _asyncio.gather(*[_extract_one(ch) for ch in chapters])
    total_new = 0
    for r in chapter_results:
        results[r["chapter_id"]] = {k: v for k, v in r.items() if k != "chapter_id"}
        total_new += r.get("new", 0)

    w.bump_version()
    save_world(w, export_markdown=False)
    total_events = sum(len(tl.events) for tl in w.character_personal_timelines)
    return {"ok": True, "total_new": total_new, "total_events": total_events, "by_chapter": results, "world": w.model_dump(mode="json")}


@app.post("/api/worlds/{world_id}/knowledge-graph/extract-all")
async def api_extract_all_knowledge(world_id: str) -> dict[str, Any]:
    """Scan all existing chapter manuscripts and extract knowledge entries.

    Processes chapters in parallel (up to 5 at a time) for speed.
    Returns counts of new/updated entries per chapter.
    """
    import asyncio as _asyncio

    w = _story_world_or_404(world_id)
    chapters = [c for c in w.story.chapters if c.status not in ("planned", "outline")]
    if not chapters:
        return {"ok": True, "total_new": 0, "by_chapter": {}, "message": "没有可提取的章节"}

    from worldforger.story_store import manuscript_path, read_text
    from worldforger.story_service import _try_detect_knowledge

    results = {}
    sem = _asyncio.Semaphore(3)  # limit concurrency to avoid rate limiting

    async def _extract_one(ch) -> dict:
        async with sem:
            ms = read_text(manuscript_path(world_id, ch.id))
            if not ms.strip():
                return {"chapter_id": ch.id, "skipped": True, "reason": "文稿为空"}
            prev_count = len(w.character_knowledge.entries)
            # Small delay between calls to avoid rate limiting
            await _asyncio.sleep(3)
            err = await _try_detect_knowledge(w, ch.id, ms)
            new_count = len(w.character_knowledge.entries) - prev_count
            return {"chapter_id": ch.id, "skipped": False, "new": new_count, "error": err} if err else {"chapter_id": ch.id, "skipped": False, "new": new_count}

    chapter_results = await _asyncio.gather(*[_extract_one(ch) for ch in chapters])
    total_new = 0
    for r in chapter_results:
        results[r["chapter_id"]] = {k: v for k, v in r.items() if k != "chapter_id"}
        total_new += r.get("new", 0)

    w.bump_version()
    save_world(w, export_markdown=False)
    return {
        "ok": True,
        "total_new": total_new,
        "total_entries": len(w.character_knowledge.entries),
        "by_chapter": results,
        "world": w.model_dump(mode="json"),
    }




@app.post("/api/worlds/{world_id}/story/foreshadowing/apply")
async def api_story_foreshadow_apply(
    world_id: str, body: StoryForeshadowApplyBody
) -> dict[str, Any]:
    w = _story_world_or_404(world_id)
    w, applied, warnings = apply_foreshadow_operations(w, body.operations)
    if body.persist:
        save_world(w)
    return {
        "world": w.model_dump(mode="json"),
        "applied": applied,
        "warnings": warnings,
    }


@app.post("/api/worlds/{world_id}/ecology-generate")
async def api_ecology_generate(
    world_id: str, body: EcologyGenerateBody = EcologyGenerateBody(),
) -> dict[str, str]:
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found")

    sys_p = ecology_generate_system_prompt()
    user_p = ecology_generate_user_payload(w, hint=body.hint)
    msgs: list[dict[str, str]] = [{"role": "system", "content": sys_p}]
    mode_eff = (body.creative_mode or "").strip() or w.meta.creative_mode
    addon = chat_mode_system(mode_eff)
    if addon:
        msgs.append({"role": "system", "content": addon})
    tag_addon = genre_tags_prompt_addon(w.meta.genre_tags)
    if tag_addon:
        msgs.append({"role": "system", "content": tag_addon})
    msgs.append({"role": "user", "content": user_p})
    try:
        reply = await chat_completion(msgs, temperature=0.35, max_tokens=8192)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}") from e
    return {"reply": reply}


def _append_session_log(
    world_id: str, messages: list[ChatMessage], assistant_reply: str
) -> None:
    d = sessions_dir(world_id)
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    log = d / f"{ts}.md"
    parts = ["# Session snippet\n", f"- time: {ts}\n\n"]
    for m in messages:
        parts.append(f"## {m.role}\n\n{m.content}\n\n")
    parts.append("## assistant\n\n")
    parts.append(assistant_reply + "\n")
    log.write_text("".join(parts), encoding="utf-8")


if STATIC_DIR.is_dir():
    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR), html=False),
        name="static",
    )
