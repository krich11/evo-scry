"""Raw URL fetcher — returns HTTP headers + HTML with optional script/style stripping."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from evoscry.http_client import fetch_with_config

MAX_RAW_BYTES = 100_000  # 100KB per URL


async def fetch_raw(
    urls: list[str],
    strip_noise: bool = True,
) -> list[dict]:
    """Fetch URLs and return status, headers, and HTML body.

    Args:
        urls: URLs to fetch (http/https only).
        strip_noise: If True (default), remove contents of <script> and <style>
                     tags but keep the tags themselves so the model can see what
                     resources are loaded.  Set False for completely raw HTML.
    """
    for u in urls:
        parsed = urlparse(u)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme} — only http and https are allowed")

    tasks = [_fetch_one(u, strip_noise) for u in urls]
    return await asyncio.gather(*tasks)


async def _fetch_one(url: str, strip_noise: bool) -> dict:
    try:
        resp = await fetch_with_config(url)

        # Collect response headers as a flat dict
        headers = {k: v for k, v in resp.headers.items()}

        body = resp.text

        if strip_noise and body:
            body = _strip_inline_noise(body)

        # Truncate
        body_bytes = body.encode("utf-8")
        truncated = False
        if len(body_bytes) > MAX_RAW_BYTES:
            body = body_bytes[:MAX_RAW_BYTES].decode("utf-8", errors="ignore")
            truncated = True

        return {
            "url": url,
            "status_code": resp.status_code,
            "headers": headers,
            "html": body,
            "byte_length": len(body.encode("utf-8")),
            "truncated": truncated,
        }
    except Exception as exc:
        return {
            "url": url,
            "status_code": 0,
            "headers": {},
            "html": "",
            "byte_length": 0,
            "truncated": False,
            "error": str(exc),
        }


def _strip_inline_noise(html: str) -> str:
    """Remove contents of <script> and <style> tags but keep the opening tags
    so the model can see src/href attributes and type declarations."""
    soup = BeautifulSoup(html, "lxml")

    for tag in soup.find_all("script"):
        # Preserve the tag with its attributes, empty the body
        if tag.string:
            tag.string = "/* stripped */"

    for tag in soup.find_all("style"):
        if tag.string:
            tag.string = "/* stripped */"

    return str(soup)
