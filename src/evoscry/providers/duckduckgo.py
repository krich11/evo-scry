"""DuckDuckGo HTML scraper."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from evoscry.http_client import post_with_config

DDG_HTML_URL = "https://html.duckduckgo.com/html/"

# Date range mapping for DDG
_DDG_DATE_MAP = {
    "day": "d",
    "week": "w",
    "month": "m",
    "year": "y",
}


async def search_duckduckgo(
    query: str,
    max_results: int = 10,
    date_range: str | None = None,
    **_kwargs,
) -> list[dict]:
    """Scrape DuckDuckGo HTML search via POST (avoids 202 bot detection)."""
    form_data: dict[str, str] = {
        "q": query,
        "b": "",
    }
    if date_range and date_range in _DDG_DATE_MAP:
        form_data["df"] = _DDG_DATE_MAP[date_range]

    resp = await post_with_config(DDG_HTML_URL, data=form_data)
    if resp.status_code != 200:
        raise RuntimeError(f"DuckDuckGo returned HTTP {resp.status_code}")
    return _parse(resp.text, max_results)


def _parse(html: str, max_results: int) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []

    for el in soup.select(".result.results_links"):
        if len(results) >= max_results:
            break

        # Skip ads
        classes = el.get("class", [])
        if "result--ad" in classes:
            continue
        if el.select_one(".badge--ad"):
            continue

        title_a = el.select_one(".result__title a")
        snippet_el = el.select_one(".result__snippet")

        title = title_a.get_text(strip=True) if title_a else ""
        # Strip trailing "more info"
        if title.lower().endswith("more info"):
            title = title[: -len("more info")].strip()
        snippet = snippet_el.get_text(strip=True) if snippet_el else ""

        # Extract actual URL from uddg redirect
        href = title_a.get("href", "") if title_a else ""
        result_url = ""
        if "uddg=" in href:
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            result_url = qs.get("uddg", [href])[0]
        elif href.startswith("http"):
            result_url = href
        else:
            url_el = el.select_one(".result__url")
            if url_el:
                display = url_el.get_text(strip=True)
                result_url = display if display.startswith("http") else f"https://{display}"

        # Filter ad redirect URLs
        if "duckduckgo.com/y.js" in result_url or "ad_provider=" in result_url:
            continue

        if title and result_url:
            results.append({
                "title": title,
                "url": result_url,
                "snippet": snippet,
                "engine": "duckduckgo",
                "published_date": None,
            })

    return results
