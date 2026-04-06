"""Search execution — fan-out to engines, deduplicate, rank, optionally summarize."""

from __future__ import annotations

import asyncio
import logging
import re

from evoscry.cache import cache_get, cache_key, cache_set
from evoscry.circuit_breaker import get_breaker
from evoscry.config import load_config
from evoscry.metrics import metrics
from evoscry.normalize.dedup import deduplicate
from evoscry.normalize.rank import rank_results
from evoscry.normalize.summarize import summarize_results
from evoscry.providers.bing import search_bing
from evoscry.providers.brave import search_brave
from evoscry.providers.duckduckgo import search_duckduckgo
from evoscry.providers.google import search_google

logger = logging.getLogger(__name__)

VALID_DATE_RANGES = {"day", "week", "month", "year", None}

_ENGINE_FN = {
    "google": search_google,
    "duckduckgo": search_duckduckgo,
    "bing": search_bing,
    "brave": search_brave,
}


def _validate_date_range(date_range: str | None) -> None:
    if date_range is not None and date_range not in VALID_DATE_RANGES:
        raise ValueError(
            f"Invalid date_range '{date_range}'. "
            "Valid options: 'day', 'week', 'month', 'year', or null/None."
        )


async def execute_web_search(
    query: str,
    engines: list[str] | None = None,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
    summarize: bool = False,
    expand: bool = False,
) -> dict:
    """Run a multi-engine search with normalization pipeline."""
    config = load_config()
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty")
    _validate_date_range(date_range)

    engines = engines or config.search_engines
    engines = [e for e in engines if e in _ENGINE_FN]
    max_results = max_results or config.max_results

    metrics.search_total += 1

    # Query expansion
    if expand:
        from evoscry.normalize.expand import expand_query
        queries = await expand_query(query, config.query_expansion_max)
    else:
        queries = [query]

    # Check cache
    key = cache_key({
        "engines": ",".join(engines),
        "query": query,
        "queries": ",".join(queries),
        "language": language,
        "date_range": date_range or "",
        "max_results": max_results,
    })
    cached = cache_get(key)

    if cached is not None:
        all_results = cached
    else:
        # Fan out: each query variant × each engine
        tasks = []
        engine_errors: list[str] = []

        for q in queries:
            for engine in engines:
                fn = _ENGINE_FN.get(engine)
                if fn:
                    tasks.append(
                        _safe_search(engine, fn, q, max_results, language, date_range, engine_errors)
                    )

        result_sets = await asyncio.gather(*tasks)
        all_results = [r for batch in result_sets for r in batch]

        if not all_results and engine_errors:
            metrics.search_errors += 1
            raise RuntimeError(f"All search engines failed: {'; '.join(engine_errors)}")

        cache_set(key, all_results)

    # Normalize pipeline
    deduped = deduplicate(all_results)
    ranked = rank_results(deduped, query)
    trimmed = ranked[:max_results]

    response: dict = {
        "query": query,
        "engines": engines,
        "total_results": len(trimmed),
        "results": trimmed,
    }

    if summarize:
        summary = await summarize_results(query, trimmed)
        if summary:
            response["summary"] = summary

    return response


async def execute_search_google(
    query: str,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
) -> dict:
    _validate_date_range(date_range)
    config = load_config()
    max_results = max_results or config.max_results
    raw = await search_google(query, max_results, language, date_range)
    ranked = rank_results(raw, query)
    return {"query": query, "engine": "google", "total_results": len(ranked), "results": ranked[:max_results]}


async def execute_search_ddg(
    query: str,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
) -> dict:
    _validate_date_range(date_range)
    config = load_config()
    max_results = max_results or config.max_results
    raw = await search_duckduckgo(query, max_results)
    ranked = rank_results(raw, query)
    return {"query": query, "engine": "duckduckgo", "total_results": len(ranked), "results": ranked[:max_results]}


async def execute_search_bing(
    query: str,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
) -> dict:
    _validate_date_range(date_range)
    config = load_config()
    max_results = max_results or config.max_results
    raw = await search_bing(query, max_results, language, date_range)
    ranked = rank_results(raw, query)
    return {"query": query, "engine": "bing", "total_results": len(ranked), "results": ranked[:max_results]}


async def execute_search_brave(
    query: str,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
) -> dict:
    _validate_date_range(date_range)
    config = load_config()
    max_results = max_results or config.max_results
    raw = await search_brave(query, max_results, language, date_range)
    ranked = rank_results(raw, query)
    return {"query": query, "engine": "brave", "total_results": len(ranked), "results": ranked[:max_results]}


_DOMAIN_RE = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?"
    r"(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*"
    r"\.[a-zA-Z]{2,}$"
)


def _validate_site(site: str) -> str:
    """Normalize and validate a domain for site-scoped search."""
    site = site.strip().lower()
    for prefix in ("https://", "http://"):
        if site.startswith(prefix):
            site = site[len(prefix):]
    site = site.rstrip("/").split("/")[0]
    if not _DOMAIN_RE.match(site):
        raise ValueError(f"Invalid site domain: '{site}'")
    return site


async def execute_site_search(
    query: str,
    site: str,
    engines: list[str] | None = None,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
) -> dict:
    """Search restricted to a specific domain via ``site:`` prefix."""
    validated = _validate_site(site)

    # Strip any existing site: prefix the caller may have included
    clean_query = re.sub(r"\bsite:\S+\s*", "", query).strip()
    site_query = f"site:{validated} {clean_query}"

    result = await execute_web_search(
        query=site_query,
        engines=engines,
        max_results=max_results,
        language=language,
        date_range=date_range,
    )
    result["site"] = validated
    result["original_query"] = clean_query
    return result


async def _safe_search(engine_name, fn, query, max_results, language, date_range, errors):
    config = load_config()
    breaker = get_breaker(
        engine_name,
        failure_threshold=config.circuit_failure_threshold,
        recovery_timeout=config.circuit_recovery_timeout,
    )

    if not await breaker.can_execute():
        logger.warning("Circuit OPEN for %s, skipping", engine_name)
        return []

    try:
        results = await fn(query=query, max_results=max_results, language=language, date_range=date_range)
        await breaker.record_success()
        metrics.record_engine_search(engine_name)
        return results
    except Exception as exc:
        await breaker.record_failure()
        metrics.record_engine_error(engine_name)
        errors.append(f"{engine_name}: {exc}")
        return []
