"""Bing HTML scraper.

Uses a mobile user-agent to avoid Cloudflare Turnstile challenges
that Bing now serves to desktop scrapers.
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from evoscry.config import load_config

BING_SEARCH_URL = "https://www.bing.com/search"

DATE_RANGE_MAP = {
    "day": "ex1:\"ez1\"",
    "week": "ex1:\"ez2\"",
    "month": "ex1:\"ez3\"",
    "year": "ex1:\"ez5\"",
}

# Mobile UAs bypass Bing's Turnstile CAPTCHA
_MOBILE_UAS = [
    "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

_ua_index = 0
_last_request_time = 0.0


async def search_bing(
    query: str,
    max_results: int = 10,
    language: str = "en",
    date_range: str | None = None,
    **_kwargs,
) -> list[dict]:
    """Scrape Bing HTML search using a mobile user-agent."""
    params: dict[str, str] = {
        "q": query,
        "count": str(min(max_results + 5, 50)),
        "setlang": language,
    }
    if date_range and date_range in DATE_RANGE_MAP:
        params["filters"] = DATE_RANGE_MAP[date_range]

    url = f"{BING_SEARCH_URL}?{urlencode(params)}"
    resp = await _fetch_bing(url)

    if resp.status_code == 429:
        raise RuntimeError(
            "Bing rate-limited (HTTP 429). "
            "Try increasing EVOSCRY_REQUEST_DELAY_MS or using a proxy."
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Bing returned HTTP {resp.status_code}")

    return _parse(resp.text, max_results)


async def _fetch_bing(url: str) -> httpx.Response:
    """Fetch from Bing with mobile UA, rate limiting, and optional proxy."""
    global _ua_index, _last_request_time

    config = load_config()

    # Rate limiting
    now = time.monotonic()
    elapsed_ms = (now - _last_request_time) * 1000
    if elapsed_ms < config.request_delay_ms:
        await asyncio.sleep((config.request_delay_ms - elapsed_ms) / 1000)
    _last_request_time = time.monotonic()

    ua = _MOBILE_UAS[_ua_index % len(_MOBILE_UAS)]
    _ua_index += 1

    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=10.0,
        proxy=config.proxy_url,
    ) as client:
        return await client.get(url, headers=headers)

    return _parse(resp.text, max_results)


def _parse(html: str, max_results: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []

    for el in soup.select("li.b_algo"):
        if len(results) >= max_results:
            break

        # Title + URL: try .b_algoheader a (mobile), then h2 a (desktop)
        link = el.select_one(".b_algoheader a") or el.select_one("h2 a")
        if not link:
            continue

        href = link.get("href", "") or ""
        title = link.get_text(strip=True)
        if not href.startswith("http"):
            continue

        # Snippet from caption paragraph
        snippet = ""
        caption = el.select_one(".b_caption p")
        if caption:
            snippet = caption.get_text(strip=True)
        if not snippet:
            p = el.select_one("p")
            if p:
                snippet = p.get_text(strip=True)

        # Try to extract date from snippet (e.g. "Apr 3, 2026 · ...")
        published_date = None
        date_match = re.match(
            r"^(\w{3}\s+\d{1,2},\s+\d{4})\s*[·—–\-]\s*", snippet
        )
        if date_match:
            try:
                d = datetime.strptime(date_match.group(1), "%b %d, %Y")
                published_date = d.strftime("%Y-%m-%d")
                snippet = snippet[date_match.end():]
            except ValueError:
                pass

        if title and href:
            results.append({
                "title": title,
                "url": href,
                "snippet": snippet,
                "engine": "bing",
                "published_date": published_date,
            })

    return results
