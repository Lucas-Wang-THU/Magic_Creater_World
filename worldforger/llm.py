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

# ── Token usage accumulator (session-level, per-label) ─────────────

_TOKEN_USAGE: dict[str, dict[str, int]] = {}  # label -> {prompt_tokens, completion_tokens, total_tokens}
_LAST_DRAINED: dict[str, dict[str, int]] = {}  # snapshot from most recent drain


def _estimate_tokens_from_text(text: str) -> int:
    """Rough token estimate from character count (4 chars ≈ 1 token for CJK+EN mixed)."""
    return max(1, len(text) // 4)


def record_token_usage(label: str, usage: Any = None, *, prompt_chars: int = 0, completion_chars: int = 0) -> None:
    """Extract token counts from an OpenAI ``response.usage`` object and
    accumulate them under *label*.

    If *usage* is ``None``, falls back to estimating tokens from the
    supplied *prompt_chars* and *completion_chars* (4 chars/token heuristic).
    """
    entry = _TOKEN_USAGE.setdefault(label, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    if usage is not None:
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            val = getattr(usage, key, 0) or 0
            if isinstance(val, int) and val > 0:
                entry[key] += val
    else:
        # Fallback: estimate from character counts
        est_pt = max(1, prompt_chars // 4)
        est_ct = max(1, completion_chars // 4)
        entry["prompt_tokens"] += est_pt
        entry["completion_tokens"] += est_ct
        entry["total_tokens"] += est_pt + est_ct


def get_token_usage() -> dict[str, dict[str, int]]:
    """Return a copy of the current session token usage dict.

    If the live accumulator is empty, returns the last drained snapshot
    so the API always has data to show during the current session.
    """
    if _TOKEN_USAGE:
        return {k: dict(v) for k, v in _TOKEN_USAGE.items()}
    return {k: dict(v) for k, v in _LAST_DRAINED.items()}


def drain_token_usage() -> dict[str, dict[str, int]]:
    """Pop and return the accumulated token usage, clearing it.

    A snapshot is saved to ``_LAST_DRAINED`` so ``get_token_usage()``
    continues to return meaningful data after the drain.
    """
    global _TOKEN_USAGE, _LAST_DRAINED
    _LAST_DRAINED = {k: dict(v) for k, v in _TOKEN_USAGE.items()}
    result = _TOKEN_USAGE
    _TOKEN_USAGE = {}
    return result


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
    label = timing_label or "chat_completion"
    # Count prompt chars for fallback estimation
    prompt_chars = sum(
        len(str(msg.get("content", ""))) for msg in messages if msg.get("content")
    )
    with timing_context() as rec:
        rec["label"] = label
        rec["model"] = m
        resp = await client.chat.completions.create(
            model=m,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    choice = resp.choices[0].message
    content = choice.content or ""
    if resp.usage:
        record_token_usage(label, resp.usage)
    else:
        # Fallback: estimate from chars when API doesn't return usage
        record_token_usage(label, prompt_chars=prompt_chars, completion_chars=len(content))
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

    Token usage is *estimated* from character counts because the streaming
    API does not return ``usage``.  The estimate uses a simple 4 chars/token
    heuristic which is conservative for mixed Chinese/English text.
    """
    client = _client()
    if client is None:
        raise RuntimeError(
            "PARATERA_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    s = get_settings()
    m = model or s.openai_chat_model

    # Estimate prompt tokens from input messages
    prompt_chars = sum(
        len(str(msg.get("content", ""))) for msg in messages if msg.get("content")
    )
    estimated_prompt_tokens = max(1, prompt_chars // 4)

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

    total_chars = 0
    async for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            total_chars += len(delta.content)
            yield delta.content

    estimated_completion_tokens = max(1, total_chars // 4)
    label = timing_label or "chat_completion_stream"
    entry = _TOKEN_USAGE.setdefault(label, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    entry["prompt_tokens"] += estimated_prompt_tokens
    entry["completion_tokens"] += estimated_completion_tokens
    entry["total_tokens"] += estimated_prompt_tokens + estimated_completion_tokens


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
    label = timing_label or "chat_completion_with_tools"
    total_completion_chars = 0

    with timing_context() as rec:
        rec["label"] = label
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
            if resp.usage:
                record_token_usage(label, resp.usage)
            if choice.content:
                total_completion_chars += len(choice.content)
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
            # If no round had usage info, estimate from total chars
            if label not in _TOKEN_USAGE:
                prompt_chars = sum(
                    len(str(msg.get("content", ""))) for msg in convo if msg.get("content")
                )
                record_token_usage(label, prompt_chars=prompt_chars, completion_chars=total_completion_chars)
            return content, actions

    # All rounds were tool calls with no final text
    if label not in _TOKEN_USAGE:
        prompt_chars = sum(
            len(str(msg.get("content", ""))) for msg in convo if msg.get("content")
        )
        record_token_usage(label, prompt_chars=prompt_chars, completion_chars=total_completion_chars)
    return "", actions
