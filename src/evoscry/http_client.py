"""HTTP client with user-agent rotation and rate limiting."""

from __future__ import annotations

import asyncio
import time

import httpx

from evoscry.config import load_config

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 OPR/116.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Vivaldi/7.0",
]

_ua_index = 0
_last_request_time = 0.0


def _get_user_agent() -> str:
    global _ua_index
    config = load_config()
    if config.user_agent == "rotate":
        ua = USER_AGENTS[_ua_index % len(USER_AGENTS)]
        _ua_index += 1
        return ua
    return config.user_agent


async def _enforce_delay() -> None:
    global _last_request_time
    config = load_config()
    now = time.monotonic()
    elapsed_ms = (now - _last_request_time) * 1000
    if elapsed_ms < config.request_delay_ms:
        await asyncio.sleep((config.request_delay_ms - elapsed_ms) / 1000)
    _last_request_time = time.monotonic()


async def fetch_with_config(url: str) -> httpx.Response:
    """Fetch URL with rate limiting, UA rotation, and timeout."""
    await _enforce_delay()

    headers = {
        "User-Agent": _get_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    config = load_config()
    proxy = config.proxy_url

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=10.0,
        proxy=proxy,
    ) as client:
        return await client.get(url, headers=headers)


async def post_with_config(url: str, data: dict) -> httpx.Response:
    """POST form data with rate limiting, UA rotation, and timeout."""
    await _enforce_delay()

    headers = {
        "User-Agent": _get_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://duckduckgo.com/",
        "Origin": "https://duckduckgo.com",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    config = load_config()
    proxy = config.proxy_url

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=10.0,
        proxy=proxy,
    ) as client:
        return await client.post(url, data=data, headers=headers)


async def fetch_url(url: str) -> str:
    """Fetch URL and return body text."""
    resp = await fetch_with_config(url)
    resp.raise_for_status()
    return resp.text
