"""Google HTML scraper."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from evoscry.http_client import fetch_with_config

GOOGLE_SEARCH_URL = "https://www.google.com/search"

DATE_RANGE_MAP = {
    "day": "qdr:d",
    "week": "qdr:w",
    "month": "qdr:m",
    "year": "qdr:y",
}


async def search_google(
    query: str,
    max_results: int = 10,
    language: str = "en",
    date_range: str | None = None,
) -> list[dict]:
    """Scrape Google HTML search and return raw results."""
    params: dict[str, str] = {
        "q": query,
        "num": str(min(max_results + 5, 40)),
        "hl": language,
    }
    if date_range and date_range in DATE_RANGE_MAP:
        params["tbs"] = DATE_RANGE_MAP[date_range]

    url = f"{GOOGLE_SEARCH_URL}?{urlencode(params)}"
    resp = await fetch_with_config(url)

    if resp.status_code in (429, 503):
        raise RuntimeError(
            f"Google rate-limited (HTTP {resp.status_code}). "
            "Try increasing EVOSCRY_REQUEST_DELAY_MS or using a proxy."
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Google returned HTTP {resp.status_code}")

    return _parse(resp.text, max_results)


def _parse(html: str, max_results: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []

    for el in soup.select("div.g"):
        if len(results) >= max_results:
            break

        # Skip ads
        if el.find_parent(class_="uEierd"):
            continue
        if el.find_parent(attrs={"data-text-ad": True}):
            continue

        link = el.select_one("a")
        title_el = el.select_one("h3")
        if not link or not title_el:
            continue

        href = link.get("href", "")
        title = title_el.get_text(strip=True)
        if not href.startswith("http"):
            continue

        # Extract snippet
        snippet = ""
        for sel in ["div[data-sncf]", "div.VwiC3b", "span.aCOpRe"]:
            found = el.select_one(sel)
            if found:
                snippet = found.get_text(strip=True)
                break
        if not snippet:
            all_text = el.get_text()
            idx = all_text.find(title)
            if idx >= 0:
                snippet = all_text[idx + len(title) :].strip()[:300]

        # Try to extract date from snippet
        published_date = None
        date_match = re.match(r"^(\w{3}\s+\d{1,2},\s+\d{4})\s*[—–\-]\s*", snippet)
        if date_match:
            try:
                d = datetime.strptime(date_match.group(1), "%b %d, %Y")
                published_date = d.strftime("%Y-%m-%d")
                snippet = snippet[date_match.end() :]
            except ValueError:
                pass

        if title and href:
            results.append({
                "title": title,
                "url": href,
                "snippet": snippet,
                "engine": "google",
                "published_date": published_date,
            })

    return results
