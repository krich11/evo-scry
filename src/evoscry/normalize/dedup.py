"""URL deduplication with canonicalization."""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse

# Tracking params to strip during canonicalization
_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "source"}


def normalize_url(url: str) -> str:
    """Canonicalize a URL for dedup comparison."""
    try:
        parsed = urlparse(url)
        normalized = f"{parsed.scheme}://{parsed.hostname.lower()}{parsed.path}"
        if normalized.endswith("/"):
            normalized = normalized[:-1]
        # Remove tracking params
        qs = parse_qs(parsed.query, keep_blank_values=False)
        clean = {k: v for k, v in qs.items() if k not in _TRACKING_PARAMS}
        if clean:
            normalized += "?" + urlencode(clean, doseq=True)
        return normalized
    except Exception:
        return url.lower()


def extract_domain(url: str) -> str:
    """Extract bare domain (no www.) from URL."""
    try:
        host = urlparse(url).hostname or ""
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def deduplicate(results: list[dict]) -> list[dict]:
    """Deduplicate raw results by normalized URL, merging metadata."""
    seen: dict[str, dict] = {}
    for r in results:
        key = normalize_url(r["url"])
        existing = seen.get(key)
        if existing is None:
            seen[key] = dict(r)
        else:
            # Prefer longer snippet
            if len(r.get("snippet", "")) > len(existing.get("snippet", "")):
                existing["snippet"] = r["snippet"]
            # Prefer result with a date
            if not existing.get("published_date") and r.get("published_date"):
                existing["published_date"] = r["published_date"]
            # Track multiple engines
            if r.get("engine") != existing.get("engine"):
                existing.setdefault("_engines", {existing["engine"]})
                existing["_engines"].add(r["engine"])
    return list(seen.values())
