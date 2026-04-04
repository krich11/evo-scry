"""Ollama-compatible local model client."""

from __future__ import annotations

import httpx


async def chat_local(prompt: str, base_url: str, model: str) -> str:
    """Call a local Ollama-compatible model."""
    url = f"{base_url.rstrip('/')}/api/chat"

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful search result summarizer. Be concise and factual.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    content = data.get("message", {}).get("content")
    if not content:
        raise RuntimeError("Local model returned empty response")

    return content.strip()
