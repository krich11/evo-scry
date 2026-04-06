"""Brave Search HTML scraper.

Brave's HTML search endpoint does not require JavaScript rendering,
making it a reliable third engine alongside DuckDuckGo and Bing.
"""

from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from evoscry.http_client import fetch_with_config

BRAVE_SEARCH_URL = "https://search.brave.com/search"

DATE_RANGE_MAP = {
    "day": "pd",
    "week": "pw",
    "month": "pm",
    "year": "py",
}

_DATE_PREFIX_RE = re.compile(r"^(\w{3}\s+\d{1,2},\s+\d{4})\s*[-—–]?\s*")


async def search_brave(
    query: str,
    max_results: int = 10,
    language: str = "en",
    date_range: str | None = None,
    **_kwargs,
) -> list[dict]:
    """Scrape Brave Search HTML results."""
    params = f"q={_quote(query)}&source=web"
    if date_range and date_range in DATE_RANGE_MAP:
        params += f"&tf={DATE_RANGE_MAP[date_range]}"

    url = f"{BRAVE_SEARCH_URL}?{params}"
    resp = await fetch_with_config(url)

    if resp.status_code == 429:
        raise RuntimeError(
            "Brave rate-limited (HTTP 429). "
            "Try increasing EVOSCRY_REQUEST_DELAY_MS or using a proxy."
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Brave returned HTTP {resp.status_code}")

    return _parse(resp.text, max_results)


def _quote(text: str) -> str:
    """Minimal percent-encoding for query params."""
    from urllib.parse import quote_plus
    return quote_plus(text)


def _parse(html: str, max_results: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []

    # Brave organic results live in #results > .snippet
    for el in soup.select("#results .snippet"):
        if len(results) >= max_results:
            break

        # Skip ads / sponsored
        el_classes = el.get("class") or []
        classes = " ".join(el_classes) if isinstance(el_classes, list) else str(el_classes)
        if "ad" in classes or "sponsored" in classes:
            continue

        # Title + URL
        link = el.select_one("a.snippet-title") or el.select_one("a[href^='http']")
        if not link:
            continue
        href = str(link.get("href", "") or "")
        if not href.startswith("http"):
            continue
        title = link.get_text(strip=True)

        # Snippet
        desc = el.select_one("p.snippet-description") or el.select_one(".snippet-description")
        snippet = desc.get_text(strip=True) if desc else ""

        # Published date
        published_date = None
        match = _DATE_PREFIX_RE.match(snippet)
        if match:
            try:
                dt = datetime.strptime(match.group(1), "%b %d, %Y")
                published_date = dt.strftime("%Y-%m-%d")
                snippet = snippet[match.end():]
            except ValueError:
                pass

        if title:
            results.append({
                "title": title,
                "url": href,
                "snippet": snippet,
                "engine": "brave",
                "published_date": published_date,
            })

    return results
