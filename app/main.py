from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from worldforger.llm import chat_completion
from worldforger.creative_modes import chat_mode_system
from worldforger.panel_sync import sync_panels_from_dialogue
from worldforger.prompts import outline_system_prompt, system_with_world_json
from worldforger.schemas import World
from worldforger.world_store import (
    create_world,
    list_world_ids,
    load_world,
    outlines_dir,
    save_world,
    sessions_dir,
    world_context_for_prompt,
    world_json_path,
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class CreateWorldBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatBody(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    mode: str | None = None
    include_markdown_context: bool = False


class OutlineBody(BaseModel):
    kind: Literal["characters", "plot"]
    prompt: str = Field(min_length=1, max_length=8000)
    include_markdown_context: bool = True
    creative_mode: str | None = None


SyncScope = Literal[
    "all",
    "geography",
    "power_system",
    "item_quality_system",
    "factions",
    "history",
]


class SyncPanelsBody(BaseModel):
    """由「结构化同步器」读取对话，将可落盘设定合并进各板块。"""

    user_message: str = Field(min_length=1, max_length=16000)
    assistant_reply: str = Field(min_length=1, max_length=64000)
    persist: bool = False
    scope: SyncScope = "all"
    creative_mode: str | None = None


app = FastAPI(title="Magic Creater World", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/api/worlds")
def api_list_worlds() -> dict[str, list[str]]:
    return {"worlds": list_world_ids()}


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
    return w.model_dump(mode="json")


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


@app.post("/api/worlds/{world_id}/export-md")
def api_export_md(world_id: str) -> dict[str, str]:
    try:
        w = load_world(world_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="world not found")
    save_world(w, export_markdown=True)
    return {"ok": "true", "path": str(world_json_path(world_id).with_name("world.md"))}


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
    try:
        mode_eff = (body.creative_mode or "").strip() or w.meta.creative_mode
        result = await sync_panels_from_dialogue(
            w,
            user_message=body.user_message,
            assistant_reply=body.assistant_reply,
            scope=body.scope,
            creative_mode=mode_eff,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except (ValueError, json.JSONDecodeError, TypeError) as e:
        return {
            "ok": False,
            "error": str(e),
            "world": w.model_dump(mode="json"),
            "updated_sections": [],
            "patch": {},
            "structure_output_keys": [],
            "scope_applied": body.scope,
            "merge_warnings": [],
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"structure sync error: {e}") from e

    merged = result["world"]
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
