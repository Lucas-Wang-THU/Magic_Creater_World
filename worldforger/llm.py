from __future__ import annotations

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
