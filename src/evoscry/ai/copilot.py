"""GitHub Copilot API client with automatic token refresh."""

from __future__ import annotations

import time

import httpx

COPILOT_CHAT_URL = "https://api.githubcopilot.com/chat/completions"
COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"

_cached_token: str | None = None
_token_expires_at: float = 0.0


async def _get_valid_token(
    token: str | None,
    refresh_token: str | None,
) -> str:
    """Get a valid Copilot API token, refreshing if needed."""
    global _cached_token, _token_expires_at

    # Use cached token if still valid (60s buffer)
    if _cached_token and time.time() < _token_expires_at - 60:
        return _cached_token

    # Try refreshing via GitHub OAuth token
    if refresh_token:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    COPILOT_TOKEN_URL,
                    headers={
                        "Authorization": f"token {refresh_token}",
                        "Accept": "application/json",
                        "User-Agent": "evo-scry/2.0.0",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    _cached_token = data["token"]
                    _token_expires_at = data["expires_at"]
                    return _cached_token
        except Exception:
            pass

    # Fall back to static token
    if token:
        return token

    raise RuntimeError("No valid Copilot token available")


async def chat_copilot(
    prompt: str,
    token: str | None = None,
    refresh_token: str | None = None,
) -> str:
    """Call GitHub Copilot chat API."""
    valid_token = await _get_valid_token(token, refresh_token)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            COPILOT_CHAT_URL,
            headers={
                "Authorization": f"Bearer {valid_token}",
                "Content-Type": "application/json",
                "Editor-Version": "vscode/1.96.0",
                "Editor-Plugin-Version": "copilot-chat/0.24.0",
                "Openai-Intent": "conversation-panel",
                "Copilot-Integration-Id": "vscode-chat",
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful search result summarizer. Be concise and factual.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 300,
                "temperature": 0.3,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    content = None
    choices = data.get("choices", [])
    if choices:
        content = choices[0].get("message", {}).get("content")

    if not content:
        raise RuntimeError("Copilot returned empty response")

    return content.strip()
