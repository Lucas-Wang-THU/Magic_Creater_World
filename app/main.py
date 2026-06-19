from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.requests import Request

from worldforger.config import get_settings
from worldforger.llm import chat_completion
from worldforger.creative_modes import chat_guides_content, chat_mode_system, genre_tags_prompt_addon, normalize_chat_guides
from worldforger.sync.panel_sync import sync_panels_from_dialogue
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
from worldforger.story.foreshadow_apply import apply_foreshadow_operations
from worldforger.story.story_agent import run_story_chat_agent
from worldforger.story.story_chapter_sync import chapter_display_for_prompt, reconcile_story_chapters, title_from_beat_markdown
from worldforger.story.story_prompts import story_chat_system_prompt
from worldforger.story.story_service import (
    add_chapter,
    apply_unit_label_from_mode,
    generate_chapter_beats,
    generate_macro_outline,
    generate_manuscript,
    generate_manuscript_stream,
    remove_chapter,
    try_import_legacy,
)
from worldforger.story.story_store import (
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


class ChatBody(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    mode: str | None = None
    include_markdown_context: bool = False
    chat_guides: list[str] = Field(default_factory=list)
    auto_sync: bool = False
    persist_sync: bool = True
    sync_scope: SyncScope = "all"
    proofreader_max_retries: int | None = None

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
    enable_speech_profile: bool | None = None
    enable_aftermath_track: bool | None = None
    enable_breathing_room: bool | None = None
    enable_epic_density_check: bool | None = None
    enable_flaw_track: bool | None = None
    enable_micro_habit_track: bool | None = None
    enable_mystery_manager: bool | None = None
    enable_character_arc_engine: bool | None = None
    enable_reader_memory: bool | None = None
    enable_narrative_state_injection: bool | None = None
    enable_scene_chunking: bool | None = None
    enable_unified_extractors: bool | None = None
    enable_break_mechanism: bool | None = None
    enable_character_agents: bool | None = None
    agent_max_rounds: int | None = Field(default=None, ge=1, le=8)
    enable_webnovel_style: bool | None = None
    enable_panel_template: bool | None = None


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


class SyncPanelsBody(BaseModel):
    """由「结构化同步器」读取对话，将可落盘设定合并进各板块。"""

    user_message: str = Field(min_length=1, max_length=16000)
    assistant_reply: str = Field(default="", max_length=64000)
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


# ── Global error logging: print UI-facing errors to terminal ──────────

from fastapi.responses import JSONResponse


@app.exception_handler(HTTPException)
async def _log_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    """Log every HTTP error that reaches the UI to the terminal."""
    detail = str(exc.detail) if exc.detail else ""
    # Truncate very long details for readability
    detail_short = detail[:500] + ("…" if len(detail) > 500 else "")
    print(f"[MCW-ERROR] {exc.status_code} {request.method} {request.url.path} | {detail_short}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def _log_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions, log to terminal, return 500 to UI."""
    import traceback
    detail = f"internal error: {exc}"
    print(f"[MCW-ERROR] 500 {request.method} {request.url.path} | {detail}")
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": detail})


@app.exception_handler(RequestValidationError)
async def _log_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Log request validation errors (422) to terminal."""
    errors = exc.errors()
    detail_short = str(errors)[:500] + ("…" if len(str(errors)) > 500 else "")
    print(f"[MCW-ERROR] 422 {request.method} {request.url.path} | {detail_short}")
    return JSONResponse(status_code=422, content={"detail": errors})


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


def _last_user_content(messages: list[ChatMessage]) -> str:
    for m in reversed(messages):
        if m.role == "user":
            return m.content
    return ""


def _sync_result_payload(result: dict[str, Any], *, persisted: bool = False) -> dict[str, Any]:
    w_out = result.get("world")
    world_dict = w_out.model_dump(mode="json") if hasattr(w_out, "model_dump") else w_out
    return {
        "ok": bool(result.get("ok")),
        "error": result.get("error"),
        "world": world_dict,
        "updated_sections": result.get("updated_sections") or [],
        "patch": result.get("applied_patch") or {},
        "applied_patch": result.get("applied_patch") or {},
        "structure_output_keys": result.get("structure_output_keys") or [],
        "scope_applied": result.get("scope_applied"),
        "merge_warnings": result.get("merge_warnings") or [],
        "normalize_notes": result.get("normalize_notes") or {},
        "proofreader_rounds": result.get("proofreader_rounds", 0),
        "proofreader_final_verdict": result.get("proofreader_final_verdict", ""),
        "proofreader_issues": result.get("proofreader_issues") or [],
        "format_proofreader_used": result.get("format_proofreader_used", False),
        "format_stages": result.get("format_stages") or [],
        "persisted": persisted,
    }


def _persist_world_token_usage(world_id: str, *, bucket: str = "world_chat") -> None:
    from worldforger.llm import drain_token_usage
    from worldforger.story.story_store import accumulate_world_token_usage

    usage = drain_token_usage()
    if usage:
        accumulate_world_token_usage(world_id, usage, bucket=bucket)


async def _sync_reply_into_world(
    world: World,
    *,
    user_message: str,
    assistant_reply: str,
    scope: SyncScope = "all",
    creative_mode: str | None = None,
    proofreader_max_retries: int | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    if not (assistant_reply or "").strip():
        return {
            "ok": True,
            "world": world,
            "updated_sections": [],
            "applied_patch": {},
            "structure_output_keys": [],
            "scope_applied": scope,
            "merge_warnings": ["assistant_reply 为空，跳过同步"],
            "normalize_notes": {},
            "proofreader_rounds": 0,
            "proofreader_final_verdict": "skipped",
            "proofreader_issues": [],
            "format_proofreader_used": False,
            "format_stages": [],
        }
    pr_max_retries = (
        proofreader_max_retries
        if proofreader_max_retries is not None
        else get_settings().proofreader_max_retries
    )
    result = await sync_panels_from_dialogue(
        world,
        user_message=user_message,
        assistant_reply=assistant_reply,
        scope=scope,
        creative_mode=(creative_mode or "").strip() or world.meta.creative_mode,
        proofreader_max_retries=pr_max_retries,
    )
    if result.get("ok") and persist and result.get("updated_sections"):
        merged = result["world"]
        merged.bump_version()
        save_world(merged, export_markdown=True)
        result["world"] = merged
        result["persisted"] = True
    else:
        result["persisted"] = False
    return result


@app.post("/api/worlds/{world_id}/chat")
async def api_chat(world_id: str, body: ChatBody) -> dict[str, Any]:
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
        reply = await chat_completion(msgs, max_tokens=16384)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}") from e

    _append_session_log(world_id, body.messages, reply, kind="chat")
    payload: dict[str, Any] = {"reply": reply}
    if body.auto_sync:
        sync_result = await _sync_reply_into_world(
            w,
            user_message=_last_user_content(body.messages),
            assistant_reply=reply,
            scope=body.sync_scope,
            creative_mode=mode_eff,
            proofreader_max_retries=body.proofreader_max_retries,
            persist=body.persist_sync,
        )
        payload["sync"] = _sync_result_payload(sync_result, persisted=bool(sync_result.get("persisted")))
        payload["world"] = payload["sync"].get("world")
    _persist_world_token_usage(world_id, bucket="world_chat")
    return payload


@app.post("/api/worlds/{world_id}/character-chat")
async def api_character_chat(world_id: str, body: ChatBody) -> dict[str, Any]:
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
        reply = await chat_completion(msgs, max_tokens=16384)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {e}") from e

    _append_session_log(world_id, body.messages, reply, kind="character-chat")
    payload: dict[str, Any] = {"reply": reply}
    if body.auto_sync:
        sync_scope: SyncScope = body.sync_scope if body.sync_scope != "all" else "characters"
        sync_result = await _sync_reply_into_world(
            w,
            user_message=_last_user_content(body.messages),
            assistant_reply=reply,
            scope=sync_scope,
            creative_mode=mode_eff,
            proofreader_max_retries=body.proofreader_max_retries,
            persist=body.persist_sync,
        )
        payload["sync"] = _sync_result_payload(sync_result, persisted=bool(sync_result.get("persisted")))
        payload["world"] = payload["sync"].get("world")
    _persist_world_token_usage(world_id, bucket="character_chat")
    return payload


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
        _append_session_log(world_id, body.messages, result["reply"], kind="story-chat")
        _persist_world_token_usage(world_id, bucket="story_chat")
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

    _append_session_log(world_id, body.messages, reply, kind="story-chat")
    _persist_world_token_usage(world_id, bucket="story_chat")
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
    if not (body.assistant_reply or "").strip():
        return {
            "ok": True, "world": w.model_dump(mode="json"),
            "updated_sections": [], "applied_patch": {},
            "structure_output_keys": [],
            "scope_applied": body.scope,
            "merge_warnings": ["assistant_reply 为空，跳过同步"],
            "normalize_notes": {}, "proofreader_rounds": 0,
            "proofreader_final_verdict": "skipped",
            "proofreader_issues": [],
            "format_proofreader_used": False, "format_stages": [],
            "persisted": False,
        }
    result = await sync_panels_from_dialogue(
        w,
        user_message=body.user_message,
        assistant_reply=body.assistant_reply,
        scope=body.scope,
        creative_mode=mode_eff,
        proofreader_max_retries=pr_max_retries,
    )
    _persist_world_token_usage(world_id, bucket="structure_sync")
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
            "persisted": False,
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
        "persisted": bool(body.persist and result["updated_sections"]),
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
    from worldforger.story.story_store import save_chapter_snapshot
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
        from worldforger.story.story_service import remove_chapter
        for cid in ids:
            remove_chapter(w, cid)
        # Re-number remaining chapters
        kept = w.story.chapters
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
    from worldforger.story.story_store import list_chapter_snapshots
    _story_world_or_404(world_id)
    return {"snapshots": list_chapter_snapshots(world_id, chapter_id)}


@app.get("/api/worlds/{world_id}/story/chapters/{chapter_id}/snapshots/diff")
def api_chapter_snapshot_diff(
    world_id: str, chapter_id: str, left: str = "", right: str = ""
) -> dict[str, Any]:
    """对比章节两个版本之间的差异（left/right 为版本号或 'current'）。"""
    from worldforger.snapshot_diff import line_diff_text
    from worldforger.story.story_store import manuscript_path, read_chapter_snapshot, read_text

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


@app.get("/api/worlds/{world_id}/story/chapters/{chapter_id}/snapshots/{version}")
def api_get_chapter_snapshot(world_id: str, chapter_id: str, version: int) -> dict[str, Any]:
    """获取某章某个版本的快照内容。"""
    from worldforger.story.story_store import read_chapter_snapshot
    _story_world_or_404(world_id)
    try:
        content = read_chapter_snapshot(world_id, chapter_id, version)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="snapshot not found") from None
    return {"version": version, "content": content}


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
    from worldforger.story.story_service import _run_polish_loop

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
    from worldforger.story.story_store import read_consistency_report

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


# ── Agent Decision Log ────────────────────────────────────────────

@app.get("/api/worlds/{world_id}/story/agent-decisions/{chapter_id}")
def api_get_agent_decisions(world_id: str, chapter_id: str) -> dict[str, Any]:
    """Return agent decision log for a specific chapter."""
    import json as _json
    from pathlib import Path

    agents_dir = Path("worlds") / world_id / "agents"
    if not agents_dir.is_dir():
        return {"chapter_id": chapter_id, "decisions": [], "characters": {}}

    result: dict = {"chapter_id": chapter_id, "decisions": [], "characters": {}}
    for child in sorted(agents_dir.iterdir()):
        if not child.is_dir():
            continue
        log_path = child / "decision_log.jsonl"
        if not log_path.is_file():
            continue
        char_decisions = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                if entry.get("chapter_id") == chapter_id:
                    char_decisions.append(entry.get("decision", {}))
        if char_decisions:
            result["characters"][child.name] = {
                "count": len(char_decisions),
                "decisions": char_decisions,
            }
            result["decisions"].extend(char_decisions)
    result["total"] = len(result["decisions"])
    return result


# ── Agent Management CRUD API ────────────────────────────────────

@app.get("/api/worlds/{world_id}/agents")
def api_list_agents(world_id: str) -> dict[str, Any]:
    """List all character agent states for a world."""
    from worldforger.agents.agent_store import AgentStore

    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    states = AgentStore.load_all_states(world_id)
    if not states:
        states = AgentStore.init_states_from_world(world_id, w)

    agents = {}
    for cid, s in states.items():
        agents[cid] = {
            "character_id": cid,
            "name": s.name,
            "emotional_state": s.emotional_state,
            "current_goal": s.current_goal,
            "current_location": s.current_location,
            "pressure_level": s.pressure_level,
            "total_decisions_made": s.total_decisions_made,
            "last_chapter": s.last_chapter,
            "active_aftermaths_count": len(s.active_aftermaths),
        }
    return {"world_id": world_id, "agents": agents, "count": len(agents)}


@app.get("/api/worlds/{world_id}/agents/{character_id}")
def api_get_agent(world_id: str, character_id: str) -> dict[str, Any]:
    """Get a single character agent's full state."""
    from worldforger.agents.agent_store import AgentStore

    state = AgentStore.load_state(world_id, character_id)
    if not state:
        raise HTTPException(status_code=404, detail="agent not found")
    return {"agent": state.model_dump(mode="json")}


@app.post("/api/worlds/{world_id}/agents/init")
def api_init_agents(world_id: str) -> dict[str, Any]:
    """Initialize all agent states from world.json."""
    from worldforger.agents.agent_store import AgentStore

    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    states = AgentStore.init_states_from_world(world_id, w)
    for state in states.values():
        AgentStore.save_state(world_id, state)

    return {
        "ok": True,
        "initialized": len(states),
        "characters": [s.name for s in states.values()],
    }


@app.post("/api/worlds/{world_id}/agents/{character_id}/reset")
def api_reset_agent(
    world_id: str, character_id: str,
) -> dict[str, Any]:
    """Reset a character agent state to a specific chapter snapshot."""
    from pathlib import Path
    import json as _json
    from worldforger.agents.agent_store import AgentStore

    agents_dir = Path("worlds") / world_id / "agents"
    if not agents_dir.is_dir():
        raise HTTPException(status_code=404, detail="no agents found for this world")

    state = AgentStore.load_state(world_id, character_id)
    if not state:
        raise HTTPException(status_code=404, detail="agent not found")

    # Reset to initial state from world.json
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    states = AgentStore.init_states_from_world(world_id, w)
    if character_id not in states:
        raise HTTPException(status_code=404, detail="character not found in world.json")

    fresh = states[character_id]
    AgentStore.save_state(world_id, fresh)

    return {
        "ok": True,
        "character_id": character_id,
        "name": fresh.name,
        "message": f"Agent '{fresh.name}' reset to initial world.json state",
    }


@app.get("/api/worlds/{world_id}/agents/{character_id}/quality-history")
def api_get_agent_quality_history(
    world_id: str, character_id: str,
) -> dict[str, Any]:
    """Return quality evaluation history from decision logs."""
    import json as _json
    from pathlib import Path
    from worldforger.agents.quality_evaluator import QualityEvaluator
    from worldforger.agents.types import AgentDecision, AgentSimResult

    log_path = Path("worlds") / world_id / "agents" / character_id / "decision_log.jsonl"
    if not log_path.is_file():
        return {"character_id": character_id, "chapters": [], "message": "No decision log found"}

    chapters: dict[str, list[dict]] = {}
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            ch = entry.get("chapter_id", "unknown")
            dec = entry.get("decision", {})
            if ch not in chapters:
                chapters[ch] = []
            chapters[ch].append(dec)

    quality_by_chapter = {}
    for ch, decs in chapters.items():
        decisions = [AgentDecision(**d) for d in decs if isinstance(d, dict)]
        sr = AgentSimResult(chapter_id=ch, decision_sequence=decisions)
        quality_by_chapter[ch] = QualityEvaluator.evaluate(sr)

    return {
        "character_id": character_id,
        "chapters": [
            {"chapter_id": ch, **q}
            for ch, q in sorted(quality_by_chapter.items())
        ],
    }
# ── P3: Multi-Chapter Runner + Quality Benchmark ─────────────────

class MultiChapterRunBody(BaseModel):
    chapter_ids: list[str] = Field(default_factory=list)
    autonomy_level: str = "semi_auto"  # advisor | semi_auto | full_auto
    max_chapters: int = Field(default=3, ge=1, le=10)
    stop_on_intervention: bool = True


@app.post("/api/worlds/{world_id}/story/generate/multi-chapter")
async def api_generate_multi_chapter(
    world_id: str, body: MultiChapterRunBody,
) -> dict[str, Any]:
    """Generate multiple chapters semi-autonomously using character agents."""
    from worldforger.agents.chapter_runner import ChapterRunner
    from worldforger.agents.autonomy import AutonomyLevel
    from worldforger.story.story_service import generate_manuscript

    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    if not body.chapter_ids:
        # Default: generate all non-done chapters in order
        body.chapter_ids = [
            c.id for c in sorted(w.story.chapters, key=lambda c: c.order)
            if c.status not in ("done", "locked")
        ]

    level_map = {
        "advisor": AutonomyLevel.ADVISOR,
        "semi_auto": AutonomyLevel.SEMI_AUTO,
        "full_auto": AutonomyLevel.FULL_AUTO,
    }
    level = level_map.get(body.autonomy_level, AutonomyLevel.SEMI_AUTO)

    async def _generate(w, ch_id):
        try:
            text, hook_errors, timing = await generate_manuscript(
                w, chapter_id=ch_id, prompt="",
                creative_mode=w.meta.creative_mode,
                person=None, attach_prev_chapters=3,
                include_world_md=w.story.writing_defaults.include_world_md,
            )
            return text, hook_errors, timing
        except Exception as e:
            return "", [str(e)], []

    runner = ChapterRunner(
        world_id=world_id,
        autonomy_level=level,
        max_chapters=body.max_chapters,
        stop_on_intervention=body.stop_on_intervention,
    )
    session = await runner.run(w, body.chapter_ids, _generate)

    return {
        "ok": True,
        "summary": runner.summary(),
        "session": {
            "chapters_completed": session.chapters_completed,
            "chapters_failed": session.chapters_failed,
            "stopped": session.stopped,
            "stop_reason": session.stop_reason,
            "results": [
                {
                    "chapter_id": r.chapter_id,
                    "success": r.success,
                    "quality_overall": r.quality.get("overall") if r.quality else None,
                    "quality_grade": r.quality.get("grade") if r.quality else None,
                    "intervention_needed": r.intervention_needed,
                }
                for r in session.results
            ],
        },
    }


@app.get("/api/worlds/{world_id}/story/quality-benchmark")
def api_quality_benchmark(world_id: str) -> dict[str, Any]:
    """Build quality baseline from existing chapters and report stats."""
    import json as _json
    from pathlib import Path
    from worldforger.agents.quality_evaluator import QualityEvaluator
    from worldforger.agents.chapter_runner import QualityBenchmark
    from worldforger.agents.types import AgentSimResult

    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    # Collect quality data from agent decision logs
    agents_dir = Path("worlds") / world_id / "agents"
    chapter_qualities: list[dict] = []
    if agents_dir.is_dir():
        for child in agents_dir.iterdir():
            if not child.is_dir():
                continue
            log_path = child / "decision_log.jsonl"
            if not log_path.is_file():
                continue
            chapters: dict[str, list] = {}
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = _json.loads(line)
                    except _json.JSONDecodeError:
                        continue
                    ch = entry.get("chapter_id", "unknown")
                    dec = entry.get("decision", {})
                    if ch not in chapters:
                        chapters[ch] = []
                    chapters[ch].append(dec)
            for ch, decs in chapters.items():
                from worldforger.agents.types import AgentDecision
                decisions = [AgentDecision(**d) for d in decs if isinstance(d, dict)]
                sr = AgentSimResult(chapter_id=ch, decision_sequence=decisions)
                q = QualityEvaluator.evaluate(sr)
                q["chapter_id"] = ch
                chapter_qualities.append(q)

    baseline = QualityBenchmark.build_baseline_from_chapters(chapter_qualities)

    # Get latest chapter quality for comparison
    latest_quality = chapter_qualities[-1] if chapter_qualities else None
    comparison = None
    if latest_quality and baseline:
        comparison = QualityBenchmark.compare(latest_quality, baseline)

    return {
        "world_id": world_id,
        "baseline": baseline,
        "chapter_count": len(chapter_qualities),
        "latest_quality": latest_quality,
        "comparison": comparison,
    }


# ── P1-6: Usage Stats ───────────────────────────────────────────────


@app.get("/api/worlds/{world_id}/story/usage-stats")
def api_get_usage_stats(world_id: str) -> dict[str, Any]:
    """返回每章各类 LLM 调用的估算 token 消耗和总预算。"""
    from worldforger.story.story_service import compute_usage_stats

    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None
    return compute_usage_stats(w)


# ── P2-12: Writing Statistics Dashboard ──────────────────────────────


@app.get("/api/worlds/{world_id}/story/stats")
def api_get_story_stats(world_id: str) -> dict[str, Any]:
    """聚合写作统计数据：字数、进度、伏笔、情感分布。"""
    from worldforger.story.story_store import (
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
        # Check disk first, fall back to in-memory ch.sentiment_log
        log = read_sentiment_log(wid, ch.id)
        if not log and ch.sentiment_log:
            log = ch.sentiment_log.model_dump(mode="json")
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
    if body.enable_speech_profile is not None:
        wd.enable_speech_profile = body.enable_speech_profile
        changed = True
    if body.enable_aftermath_track is not None:
        wd.enable_aftermath_track = body.enable_aftermath_track
        changed = True
    if body.enable_breathing_room is not None:
        wd.enable_breathing_room = body.enable_breathing_room
        changed = True
    if body.enable_epic_density_check is not None:
        wd.enable_epic_density_check = body.enable_epic_density_check
        changed = True
    if body.enable_flaw_track is not None:
        wd.enable_flaw_track = body.enable_flaw_track
        changed = True
    if body.enable_micro_habit_track is not None:
        wd.enable_micro_habit_track = body.enable_micro_habit_track
        changed = True
    if body.enable_mystery_manager is not None:
        wd.enable_mystery_manager = body.enable_mystery_manager
        changed = True
    if body.enable_character_arc_engine is not None:
        wd.enable_character_arc_engine = body.enable_character_arc_engine
        changed = True
    if body.enable_reader_memory is not None:
        wd.enable_reader_memory = body.enable_reader_memory
        changed = True
    if body.enable_narrative_state_injection is not None:
        wd.enable_narrative_state_injection = body.enable_narrative_state_injection
        changed = True
    if body.enable_scene_chunking is not None:
        wd.enable_scene_chunking = body.enable_scene_chunking
        changed = True
    if body.enable_unified_extractors is not None:
        wd.enable_unified_extractors = body.enable_unified_extractors
        changed = True
    if body.enable_break_mechanism is not None:
        wd.enable_break_mechanism = body.enable_break_mechanism
        changed = True
    if body.enable_character_agents is not None:
        wd.enable_character_agents = body.enable_character_agents
        changed = True
    if body.agent_max_rounds is not None:
        wd.agent_max_rounds = body.agent_max_rounds
        changed = True
    if body.enable_webnovel_style is not None:
        wd.enable_webnovel_style = body.enable_webnovel_style
        changed = True
    if body.enable_panel_template is not None:
        wd.enable_panel_template = body.enable_panel_template
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
    from worldforger.story.story_store import polished_path, read_text

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

    from worldforger.story.story_store import polish_trace_path

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
    from worldforger.story.story_store import read_token_usage

    try:
        _ = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    saved = read_token_usage(world_id)
    live_session = get_token_usage()
    saved_last_session = saved.get("last_session", {})
    if live_session and live_session == saved_last_session:
        live_session = {}

    # Prefer live session; fall back to persisted last_session
    session = live_session if live_session else saved_last_session
    session_is_already_persisted = bool(session and not live_session and session == saved_last_session)

    s_prompt = sum(v.get("prompt_tokens", 0) for v in session.values())
    s_completion = sum(v.get("completion_tokens", 0) for v in session.values())
    total_session_prompt = 0 if session_is_already_persisted else s_prompt
    total_session_completion = 0 if session_is_already_persisted else s_completion
    saved_prompt = saved.get("prompt_tokens", 0) or 0
    saved_completion = saved.get("completion_tokens", 0) or 0

    # Per-chapter breakdown
    by_chapter = saved.get("by_chapter", {})
    if not isinstance(by_chapter, dict):
        by_chapter = {}
    by_context = saved.get("by_context", {})
    if not isinstance(by_context, dict):
        by_context = {}
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
            "by_context": by_context,
            "by_label": persisted_by_label,
        },
        "total": {
            "prompt_tokens": total_session_prompt + saved_prompt,
            "completion_tokens": total_session_completion + saved_completion,
            "total_tokens": total_session_prompt + saved_prompt + total_session_completion + saved_completion,
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

    from worldforger.story.story_store import manuscript_path, read_text
    from worldforger.story.story_service import _try_detect_decisions

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

    from worldforger.story.story_store import manuscript_path, read_text
    from worldforger.story.story_service import _try_update_physical_states

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


# ── Phase 1: Emotional Aftermath ──────────────────────────────

@app.post("/api/worlds/{world_id}/aftermaths/extract-all")
async def api_extract_all_aftermaths(world_id: str) -> dict[str, Any]:
    """Scan all existing chapter manuscripts and extract emotional aftermaths."""
    import asyncio as _asyncio

    w = _story_world_or_404(world_id)
    chapters = [c for c in w.story.chapters if c.status not in ("planned", "outline")]
    if not chapters:
        return {"ok": True, "total_new": 0, "by_chapter": {}}

    from worldforger.story.story_store import manuscript_path, read_text
    from worldforger.story.story_service import _try_extract_aftermaths

    results = {}
    sem = _asyncio.Semaphore(3)

    async def _extract_one(ch) -> dict:
        async with sem:
            ms = read_text(manuscript_path(world_id, ch.id))
            if not ms.strip():
                return {"chapter_id": ch.id, "skipped": True}
            await _asyncio.sleep(3)
            prev = len(w.character_aftermaths)
            err = await _try_extract_aftermaths(w, ch.id, ms)
            new_count = len(w.character_aftermaths) - prev
            return {"chapter_id": ch.id, "new": new_count, "error": err} if err else {"chapter_id": ch.id, "new": new_count}

    chapter_results = await _asyncio.gather(*[_extract_one(ch) for ch in chapters])
    total_new = 0
    for r in chapter_results:
        results[r["chapter_id"]] = {k: v for k, v in r.items() if k != "chapter_id"}
        total_new += r.get("new", 0)

    w.bump_version()
    save_world(w, export_markdown=False)
    return {"ok": True, "total_new": total_new, "total": len(w.character_aftermaths), "by_chapter": results, "world": w.model_dump(mode="json")}


@app.post("/api/worlds/{world_id}/personal-timelines/extract-all")
async def api_extract_all_timelines(world_id: str) -> dict[str, Any]:
    """Scan all existing chapter manuscripts and extract personal timeline events."""
    import asyncio as _asyncio

    w = _story_world_or_404(world_id)
    chapters = [c for c in w.story.chapters if c.status not in ("planned", "outline")]
    if not chapters:
        return {"ok": True, "total_new": 0, "by_chapter": {}, "message": "没有可提取的章节"}

    from worldforger.story.story_store import manuscript_path, read_text
    from worldforger.story.story_service import _try_detect_timeline_events

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

    from worldforger.story.story_store import manuscript_path, read_text
    from worldforger.story.story_service import _try_detect_knowledge

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


# ── Character Detail Update ────────────────────────────────────

class CharacterDetailBody(BaseModel):
    power_tier: str | None = None
    profession_id: str | None = None
    age: str | None = None
    gender: str | None = None
    inventory: list[dict[str, Any]] | None = None
    attributes: dict[str, int] | None = None  # {stat_id: value}
    skills: list[dict[str, Any]] | None = None
    notable_skills: list[str] | None = None


@app.patch("/api/worlds/{world_id}/characters/{character_id}")
def api_update_character_detail(
    world_id: str, character_id: str, body: CharacterDetailBody,
) -> dict[str, Any]:
    """Update character detail fields: power_tier, profession_id, age, inventory."""
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    char_idx = next(
        (i for i, e in enumerate(w.characters.entities)
         if isinstance(e, dict) and e.get("id") == character_id), None
    )
    if char_idx is None:
        raise HTTPException(status_code=404, detail="character not found")

    char = w.characters.entities[char_idx]
    updated_fields = []

    if body.power_tier is not None:
        char["power_tier"] = body.power_tier.strip()
        updated_fields.append("power_tier")
    if body.profession_id is not None:
        char["profession_id"] = body.profession_id.strip()
        updated_fields.append("profession_id")
    if body.age is not None:
        char["age"] = str(body.age).strip()
        updated_fields.append("age")
    if body.gender is not None:
        char["gender"] = str(body.gender).strip()
        updated_fields.append("gender")
    if body.inventory is not None:
        inv = []
        for item in body.inventory:
            if isinstance(item, dict):
                inv.append({
                    "name": str(item.get("name", "")).strip(),
                    "description": str(item.get("description", "")).strip(),
                    "usage": str(item.get("usage", "")).strip(),
                    "quantity": item.get("quantity", 1),
                    "source_chapter": str(item.get("source_chapter", "")).strip(),
                    "status": str(item.get("status", "携带中")).strip(),
                })
        char["inventory"] = inv
        updated_fields.append("inventory")
    if body.attributes is not None:
        existing = char.get("attributes", {}) or {}
        for stat_id, val in body.attributes.items():
            existing[str(stat_id)] = max(0, min(100, int(val)))
        char["attributes"] = existing
        updated_fields.append("attributes")

    if body.skills is not None:
        cleaned: list[dict[str, Any]] = []
        for sk in body.skills:
            if not isinstance(sk, dict):
                continue
            name = str(sk.get("name", "")).strip()
            if not name:
                continue
            row: dict[str, Any] = {
                "name": name,
                "description": str(sk.get("description", "")).strip(),
                "exclusive": bool(sk.get("exclusive", False)),
            }
            source = str(sk.get("source", "")).strip()
            if source:
                row["source"] = source
            level = str(sk.get("level", "")).strip()
            if level:
                row["level"] = level
            cleaned.append(row)
        char["skills"] = cleaned
        updated_fields.append("skills")

    if body.notable_skills is not None:
        char["notable_skills"] = [
            str(s).strip() for s in body.notable_skills
            if isinstance(s, str) and str(s).strip()
        ]
        updated_fields.append("notable_skills")

    w.bump_version()
    save_world(w, export_markdown=False)
    return {
        "ok": True, "character_id": character_id,
        "updated_fields": updated_fields,
        "character": char,
        "world": w.model_dump(mode="json"),
    }


@app.get("/api/worlds/{world_id}/characters/{character_id}/detail")
def api_get_character_detail(world_id: str, character_id: str) -> dict[str, Any]:
    """Get character detail with resolved power/profession/item info."""
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    char = next(
        (e for e in w.characters.entities
         if isinstance(e, dict) and e.get("id") == character_id), None
    )
    if char is None:
        raise HTTPException(status_code=404, detail="character not found")

    profession_name = ""
    prof_id = char.get("profession_id", "")
    if prof_id:
        for block in w.power_system.profession_system.by_tier:
            for p in block.professions:
                if p.id == prof_id:
                    profession_name = p.name
                    break

    tier_name = char.get("power_tier", "")
    tier_desc = ""
    if tier_name:
        tier = next((t for t in w.power_system.tiers if t.name == tier_name), None)
        if tier:
            tier_desc = tier.description

    inventory = char.get("inventory", []) or []
    items_active = [i for i in inventory if i.get("status") != "已失去"]
    items_lost = [i for i in inventory if i.get("status") == "已失去"]

    # Build attribute values with stat names
    char_attrs = char.get("attributes", {}) or {}
    attr_details = []
    for stat in w.attribute_system.stats:
        val = char_attrs.get(stat.id, stat.reference_percent)
        attr_details.append({
            "stat_id": stat.id,
            "name": stat.name,
            "abbreviation": stat.abbreviation,
            "value": val,
            "reference_percent": stat.reference_percent,
            "intro": stat.intro,
        })

    return {
        "character_id": character_id,
        "name": char.get("name", ""),
        "power_tier": tier_name,
        "tier_description": tier_desc,
        "profession_id": prof_id,
        "profession_name": profession_name,
        "age": char.get("age", ""),
        "gender": char.get("gender", ""),
        "cast_role": char.get("cast_role", ""),
        "attributes": attr_details,
        "attributes_count": len(attr_details),
        "inventory": inventory,
        "items_active_count": len(items_active),
        "items_lost_count": len(items_lost),
        "notable_skills": char.get("notable_skills", []),
        "skills": char.get("skills", []),
        "speech_profile": char.get("speech_profile", {}),
        "runtime_state": char.get("runtime_state", {}),
    }


# ── Profession & Skill Tree CRUD ──────────────────────────────────

class ProfessionUpsertBody(BaseModel):
    tier_name: str = Field(min_length=1, max_length=100)
    profession: dict[str, Any] = Field(default_factory=dict)  # {id, name, tagline, flavor, exclusive_faction_id, notes}


class SkillNodeBody(BaseModel):
    tier_name: str = Field(min_length=1, max_length=100)
    subclass_id: str = ""  # empty = general tier skill tree
    node: dict[str, Any] = Field(default_factory=dict)


@app.get("/api/worlds/{world_id}/power-system/professions")
def api_list_professions(world_id: str) -> dict[str, Any]:
    """List all professions grouped by tier."""
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    ps = w.power_system.profession_system
    result = {}
    for block in ps.by_tier:
        result[block.tier_name] = [p.model_dump(mode="json") for p in block.professions]
    return {"world_id": world_id, "professions_by_tier": result, "total_tiers": len(result)}


@app.post("/api/worlds/{world_id}/power-system/professions")
def api_add_profession(world_id: str, body: ProfessionUpsertBody) -> dict[str, Any]:
    """Add or update a profession entry in a specific tier."""
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    prof_data = body.profession
    prof_id = str(prof_data.get("id", "")).strip()
    if not prof_id:
        raise HTTPException(status_code=400, detail="profession.id is required")

    tier_name = body.tier_name.strip()
    tier = next((t for t in w.power_system.tiers if t.name == tier_name), None)
    if tier is None:
        raise HTTPException(status_code=404, detail=f"tier '{tier_name}' not found")

    ps = w.power_system.profession_system
    # Find or create the tier block
    block = next((b for b in ps.by_tier if b.tier_name == tier_name), None)
    if block is None:
        from worldforger.schemas import TierProfessionBlock
        block = TierProfessionBlock(tier_name=tier_name)
        ps.by_tier.append(block)

    # Upsert: update existing or append new
    existing_idx = next((i for i, p in enumerate(block.professions) if p.id == prof_id), None)
    from worldforger.schemas import ProfessionEntry
    entry = ProfessionEntry(
        id=prof_id,
        name=str(prof_data.get("name", "")).strip(),
        tagline=str(prof_data.get("tagline", "")).strip(),
        flavor=str(prof_data.get("flavor", "")).strip(),
        exclusive_faction_id=str(prof_data.get("exclusive_faction_id", "")).strip(),
        notes=str(prof_data.get("notes", "")).strip(),
    )
    if existing_idx is not None:
        block.professions[existing_idx] = entry
        action = "updated"
    else:
        block.professions.append(entry)
        action = "added"

    w.bump_version()
    save_world(w, export_markdown=False)
    return {"ok": True, "action": action, "tier_name": tier_name, "profession_id": prof_id, "world": w.model_dump(mode="json")}


@app.delete("/api/worlds/{world_id}/power-system/professions/{profession_id}")
def api_delete_profession(world_id: str, profession_id: str) -> dict[str, Any]:
    """Delete a profession entry from all tiers."""
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    removed = 0
    for block in w.power_system.profession_system.by_tier:
        before = len(block.professions)
        block.professions = [p for p in block.professions if p.id != profession_id]
        removed += before - len(block.professions)

    if removed == 0:
        raise HTTPException(status_code=404, detail="profession not found in any tier")

    w.bump_version()
    save_world(w, export_markdown=False)
    return {"ok": True, "removed": removed, "profession_id": profession_id, "world": w.model_dump(mode="json")}


@app.post("/api/worlds/{world_id}/power-system/skill-nodes")
def api_add_skill_node(world_id: str, body: SkillNodeBody) -> dict[str, Any]:
    """Add a skill node to a specific tier's skill tree or subclass path."""
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    tier = next((t for t in w.power_system.tiers if t.name == body.tier_name), None)
    if tier is None:
        raise HTTPException(status_code=404, detail=f"tier '{body.tier_name}' not found")

    node_data = body.node
    node_id = str(node_data.get("id", "")).strip()
    if not node_id:
        raise HTTPException(status_code=400, detail="node.id is required")

    from worldforger.schemas import SkillNode

    # Upsert a single node
    def _upsert_node(nodes: list, nd: dict) -> str:
        nid = nd["id"]
        existing = next((i for i, n in enumerate(nodes) if n.id == nid), None)
        sn = SkillNode(
            id=nid,
            name=str(nd.get("name", "")).strip(),
            summary=str(nd.get("summary", "")).strip(),
            description=str(nd.get("description", "")).strip(),
            prereq_ids=nd.get("prereq_ids") if isinstance(nd.get("prereq_ids"), list) else [],
            branch=str(nd.get("branch", "")).strip(),
            effect=str(nd.get("effect", "")).strip(),
            cost=str(nd.get("cost", "")).strip(),
            activation_rules=str(nd.get("activation_rules", "")).strip(),
        )
        if existing is not None:
            nodes[existing] = sn
            return "updated"
        else:
            nodes.append(sn)
            return "added"

    if body.subclass_id:
        sub = next((s for s in (tier.subclass_paths or []) if s.id == body.subclass_id), None)
        if sub is None:
            raise HTTPException(status_code=404, detail=f"subclass '{body.subclass_id}' not found in tier '{body.tier_name}'")
        action = _upsert_node(sub.skill_tree, node_data)
        target = f"subclass:{body.subclass_id}"
    else:
        action = _upsert_node(tier.skill_tree, node_data)
        target = "tier general"

    w.bump_version()
    save_world(w, export_markdown=False)
    return {"ok": True, "action": action, "node_id": node_id, "tier_name": body.tier_name, "target": target, "world": w.model_dump(mode="json")}


@app.delete("/api/worlds/{world_id}/power-system/skill-nodes/{node_id}")
def api_delete_skill_node(world_id: str, node_id: str) -> dict[str, Any]:
    """Delete a skill node from all tiers and subclass paths."""
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found") from None

    removed = 0
    for tier in w.power_system.tiers:
        before = len(tier.skill_tree)
        tier.skill_tree = [n for n in tier.skill_tree if n.id != node_id]
        removed += before - len(tier.skill_tree)
        for sub in (tier.subclass_paths or []):
            before_sub = len(sub.skill_tree)
            sub.skill_tree = [n for n in sub.skill_tree if n.id != node_id]
            removed += before_sub - len(sub.skill_tree)

    if removed == 0:
        raise HTTPException(status_code=404, detail="skill node not found in any tier")

    w.bump_version()
    save_world(w, export_markdown=False)
    return {"ok": True, "removed": removed, "node_id": node_id, "world": w.model_dump(mode="json")}


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
    world_id: str,
    messages: list[ChatMessage],
    assistant_reply: str,
    *,
    kind: str = "chat",
) -> None:
    d = sessions_dir(world_id)
    d.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%d-%H%M%S-%f")
    turn_id = f"{ts}-{kind}"
    log = d / f"{turn_id}.md"
    last_user = _last_user_content(messages)
    parts = ["# Session turn\n", f"- id: {turn_id}\n", f"- time: {now.isoformat()}\n", f"- kind: {kind}\n\n"]
    for m in messages:
        parts.append(f"## {m.role}\n\n{m.content}\n\n")
    parts.append("## assistant\n\n")
    parts.append(assistant_reply + "\n")
    log.write_text("".join(parts), encoding="utf-8")
    jsonl = d / "dialogues.jsonl"
    record = {
        "id": turn_id,
        "time": now.isoformat(),
        "kind": kind,
        "user": last_user,
        "assistant": assistant_reply,
        "messages": [m.model_dump(mode="json") for m in messages],
        "markdown_file": log.name,
    }
    with jsonl.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


if STATIC_DIR.is_dir():
    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR), html=False),
        name="static",
    )
