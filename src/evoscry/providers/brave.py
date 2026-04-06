"""Brave Search HTML scraper.

Brave's HTML search endpoint does not require JavaScript rendering,
similar to DuckDuckGo's html endpoint.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

from evoscry.http_client import fetch_with_config

BRAVE_SEARCH_URL = "https://search.brave.com/search"

DATE_RANGE_MAP = {
    "day": "pd",
    "week": "pw",
    "month": "pm",
    "year": "py",
}

# Mobile UAs reduce anti-bot friction
_MOBILE_UAS = [
    "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

_ua_index = 0


async def search_brave(
    query: str,
    max_results: int = 10,
    language: str = "en",
    date_range: str | None = None,
    **_kwargs,
) -> list[dict]:
    """Scrape Brave Search HTML results."""
    params: dict[str, str] = {
        "q": query,
        "source": "web",
    }
    if date_range and date_range in DATE_RANGE_MAP:
        params["tf"] = DATE_RANGE_MAP[date_range]

    url = f"{BRAVE_SEARCH_URL}?{urlencode(params)}"
    resp = await _fetch_brave(url, language)

    if resp.status_code == 429:
        raise RuntimeError(
            "Brave rate-limited (HTTP 429). "
            "Try increasing EVOSCRY_REQUEST_DELAY_MS or using a proxy."
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Brave returned HTTP {resp.status_code}")

    return _parse(resp.text, max_results)


async def _fetch_brave(url: str, language: str) -> httpx.Response:
    """Fetch from Brave with mobile UA rotation via shared http_client."""
    global _ua_index
    from evoscry.config import load_config

    config = load_config()

    ua = _MOBILE_UAS[_ua_index % len(_MOBILE_UAS)]
    _ua_index += 1

    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": f"{language},{language[:2]};q=0.9,en;q=0.8" if language != "en" else "en-US,en;q=0.9",
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


def _parse(html: str, max_results: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []

    # Brave uses several possible result container selectors
    for el in soup.select("div.snippet"):
        if len(results) >= max_results:
            break

        # Skip ads / sponsored
        classes = el.get("class") or []
        class_str = " ".join(classes) if isinstance(classes, list) else str(classes)
        if "ad" in class_str or "sponsored" in class_str:
            continue

        # Title + URL
        link = el.select_one("a.snippet-title") or el.select_one("a[href]")
        if not link:
            continue

        href = str(link.get("href", "") or "")
        title = link.get_text(strip=True)
        if not href.startswith("http"):
            continue

        # Snippet
        snippet = ""
        desc = el.select_one("p.snippet-description") or el.select_one(".snippet-content")
        if desc:
            snippet = desc.get_text(strip=True)
        if not snippet:
            p = el.select_one("p")
            if p:
                snippet = p.get_text(strip=True)

        # Date extraction from snippet
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
                "engine": "brave",
                "published_date": published_date,
            })

    # Fallback: try broader selectors if div.snippet yields nothing
    if not results:
        for el in soup.select("#results .fdb"):
            if len(results) >= max_results:
                break

            link = el.select_one("a[href]")
            if not link:
                continue
            href = str(link.get("href", "") or "")
            if not href.startswith("http"):
                continue
            title = link.get_text(strip=True)

            snippet = ""
            desc_el = el.select_one(".body")
            if desc_el:
                snippet = desc_el.get_text(strip=True)

            if title and href:
                results.append({
                    "title": title,
                    "url": href,
                    "snippet": snippet,
                    "engine": "brave",
                    "published_date": None,
                })

    return results
