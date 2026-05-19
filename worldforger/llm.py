from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from openai import AsyncOpenAI

from worldforger.config import api_key, get_settings


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
) -> str:
    client = _client()
    if client is None:
        raise RuntimeError(
            "PARATERA_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    s = get_settings()
    m = model or s.openai_chat_model
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


async def chat_completion_with_tools(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]],
    execute_tool: Callable[[str, dict[str, Any]], Awaitable[str]],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 8192,
    max_rounds: int = 8,
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
