from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import contextmanager
from typing import Any

from openai import AsyncOpenAI

from worldforger.config import api_key, get_settings

# ── P2-13: Timing instrumentation ──────────────────────────────────

_CALL_LOG: list[dict[str, Any]] = []


@contextmanager
def timing_context():
    """Context manager that records wall-clock duration of each LLM call."""
    t0 = time.perf_counter()
    record: dict[str, Any] = {"start": t0}
    try:
        yield record
    finally:
        t1 = time.perf_counter()
        record["elapsed_ms"] = round((t1 - t0) * 1000, 1)
        _CALL_LOG.append(record)


def drain_timing_log() -> list[dict[str, Any]]:
    """Pop and return the accumulated timing log, clearing it."""
    global _CALL_LOG
    result = _CALL_LOG[:]
    _CALL_LOG.clear()
    return result


def _client() -> AsyncOpenAI | None:
    key = api_key()
    if not key:
        return None
    s = get_settings()
    return AsyncOpenAI(api_key=key, base_url=s.openai_api_base.rstrip("/"))


async def chat_completion(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timing_label: str = "",
) -> str:
    client = _client()
    if client is None:
        raise RuntimeError(
            "PARATERA_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    s = get_settings()
    m = model or s.openai_chat_model
    with timing_context() as rec:
        rec["label"] = timing_label or "chat_completion"
        rec["model"] = m
        resp = await client.chat.completions.create(
            model=m,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    choice = resp.choices[0].message
    content = choice.content
    if not content:
        return ""
    return content


async def chat_completion_stream(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timing_label: str = "",
) -> AsyncIterator[str]:
    """Stream tokens from a chat completion.

    Yields each content delta as a string.  Useful for SSE endpoints.
    """
    client = _client()
    if client is None:
        raise RuntimeError(
            "PARATERA_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    s = get_settings()
    m = model or s.openai_chat_model
    with timing_context() as rec:
        rec["label"] = timing_label or "chat_completion_stream"
        rec["model"] = m
        stream = await client.chat.completions.create(
            model=m,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content


async def chat_completion_with_tools(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]],
    execute_tool: Callable[[str, dict[str, Any]], Awaitable[str]],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 8192,
    max_rounds: int = 8,
    timing_label: str = "",
) -> tuple[str, list[dict[str, Any]]]:
    """多轮 tool calling，直至模型返回纯文本或无 tool_calls。"""
    client = _client()
    if client is None:
        raise RuntimeError(
            "PARATERA_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    s = get_settings()
    m = model or s.openai_chat_model
    actions: list[dict[str, Any]] = []
    convo = list(messages)

    with timing_context() as rec:
        rec["label"] = timing_label or "chat_completion_with_tools"
        rec["model"] = m
        for _ in range(max_rounds):
            resp = await client.chat.completions.create(
                model=m,
                messages=convo,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = resp.choices[0].message
            if choice.tool_calls:
                convo.append(choice.model_dump(exclude_none=True))
                for tc in choice.tool_calls:
                    fn = tc.function
                    name = fn.name or ""
                    try:
                        args = json.loads(fn.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if not isinstance(args, dict):
                        args = {}
                    result = await execute_tool(name, args)
                    actions.append(
                        {
                            "tool": name,
                            "args": args,
                            "result_preview": (result or "")[:500],
                        }
                    )
                    convo.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        }
                    )
                continue
            content = choice.content or ""
            return content, actions

    return "", actions
