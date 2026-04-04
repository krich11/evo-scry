"""Relevance ranking with 4-factor weighted scoring."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from evoscry.normalize.dedup import extract_domain

# Domain authority tiers
DOMAIN_AUTHORITY: dict[str, float] = {
    "github.com": 0.95,
    "stackoverflow.com": 0.95,
    "developer.mozilla.org": 0.95,
    "docs.python.org": 0.90,
    "docs.microsoft.com": 0.90,
    "learn.microsoft.com": 0.90,
    "wikipedia.org": 0.85,
    "en.wikipedia.org": 0.85,
    "arxiv.org": 0.85,
    "medium.com": 0.60,
    "dev.to": 0.65,
    "news.ycombinator.com": 0.75,
    "reddit.com": 0.60,
    "twitter.com": 0.50,
    "x.com": 0.50,
}

DOMAIN_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"\.gov$"), 0.90),
    (re.compile(r"\.edu$"), 0.85),
    (re.compile(r"\.org$"), 0.70),
    (re.compile(r"^docs\."), 0.80),
    (re.compile(r"^wiki\."), 0.70),
]

# Scoring weights
W_POSITION = 0.40
W_KEYWORD = 0.25
W_AUTHORITY = 0.20
W_FRESHNESS = 0.15
CROSS_ENGINE_BOOST = 1.2


def _get_domain_authority(domain: str) -> float:
    if domain in DOMAIN_AUTHORITY:
        return DOMAIN_AUTHORITY[domain]
    for pattern, score in DOMAIN_PATTERNS:
        if pattern.search(domain):
            return score
    return 0.50


def _keyword_match(query: str, title: str, snippet: str) -> float:
    terms = [t for t in query.lower().split() if len(t) > 2]
    if not terms:
        return 0.5
    text = f"{title} {snippet}".lower()
    matches = sum(1 for t in terms if t in text)
    return matches / len(terms)


def _freshness_score(published_date: str | None) -> float:
    if not published_date:
        return 0.5
    try:
        d = datetime.strptime(published_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - d).days
        if days < 7:
            return 1.0
        if days < 30:
            return 0.85
        if days < 90:
            return 0.70
        if days < 365:
            return 0.55
        return 0.30
    except Exception:
        return 0.5


def rank_results(raw: list[dict], query: str) -> list[dict]:
    """Score and sort results by relevance. Returns list of dicts with 'score' added."""
    # Track which engines returned each URL
    engine_sets: dict[str, set[str]] = {}
    for r in raw:
        key = r["url"].lower()
        engine_sets.setdefault(key, set()).add(r.get("engine", "unknown"))

    scored = []
    for i, r in enumerate(raw):
        domain = extract_domain(r["url"])
        position = max(0, 1.0 - (i / max(len(raw), 1)))
        keyword = _keyword_match(query, r.get("title", ""), r.get("snippet", ""))
        authority = _get_domain_authority(domain)
        freshness = _freshness_score(r.get("published_date"))

        score = (
            W_POSITION * position
            + W_KEYWORD * keyword
            + W_AUTHORITY * authority
            + W_FRESHNESS * freshness
        )

        # Cross-engine boost
        key = r["url"].lower()
        if len(engine_sets.get(key, set())) > 1:
            score *= CROSS_ENGINE_BOOST

        result = dict(r)
        result["score"] = round(score, 4)
        result["domain"] = domain
        # Drop internal tracking fields
        result.pop("_engines", None)
        scored.append(result)

    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored
