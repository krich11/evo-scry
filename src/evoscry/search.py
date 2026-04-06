"""Search execution — fan-out to engines, deduplicate, rank, optionally summarize."""

from __future__ import annotations

import asyncio
import logging

from evoscry.cache import cache_get, cache_key, cache_set
from evoscry.circuit_breaker import get_breaker
from evoscry.config import load_config
from evoscry.normalize.dedup import deduplicate
from evoscry.normalize.rank import rank_results
from evoscry.normalize.summarize import summarize_results
from evoscry.providers.bing import search_bing
from evoscry.providers.duckduckgo import search_duckduckgo
from evoscry.providers.google import search_google

logger = logging.getLogger("evoscry.search")

_ENGINE_FNS = {
    "google": search_google,
    "duckduckgo": search_duckduckgo,
    "bing": search_bing,
}

# Brave is imported lazily to avoid hard-dep before the file exists
def _get_engine_fn(name: str):
    if name in _ENGINE_FNS:
        return _ENGINE_FNS[name]
    if name == "brave":
        from evoscry.providers.brave import search_brave
        _ENGINE_FNS["brave"] = search_brave
        return search_brave
    return None


async def execute_web_search(
    query: str,
    engines: list[str] | None = None,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
    summarize: bool = False,
) -> dict:
    """Run a multi-engine search with normalization pipeline."""
    config = load_config()
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty")

    engines = engines or config.search_engines
    engines = [e for e in engines if e in ("google", "duckduckgo", "bing", "brave")]
    max_results = max_results or config.max_results

    # Check cache
    key = cache_key({
        "engines": ",".join(engines),
        "query": query,
        "language": language,
        "date_range": date_range or "",
        "max_results": max_results,
    })
    cached = cache_get(key)

    if cached is not None:
        all_results = cached
    else:
        # Fan out to engines in parallel
        tasks = []
        engine_errors: list[str] = []

        for engine in engines:
            fn = _get_engine_fn(engine)
            if fn is not None:
                tasks.append(
                    _safe_search(engine, fn, query, max_results, language, date_range, engine_errors)
                )

        result_sets = await asyncio.gather(*tasks)
        all_results = [r for batch in result_sets for r in batch]

        if not all_results and engine_errors:
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
    from evoscry.providers.brave import search_brave

    config = load_config()
    max_results = max_results or config.max_results
    raw = await search_brave(query, max_results, language, date_range)
    ranked = rank_results(raw, query)
    return {"query": query, "engine": "brave", "total_results": len(ranked), "results": ranked[:max_results]}


async def _safe_search(engine_name, fn, query, max_results, language, date_range, errors):
    from evoscry.metrics import metrics

    breaker = get_breaker(engine_name)
    metrics.record_search(engine_name)

    if not await breaker.can_execute():
        logger.warning("Circuit OPEN for %s, skipping", engine_name)
        return []

    try:
        results = await fn(query=query, max_results=max_results, language=language, date_range=date_range)
        await breaker.record_success()
        metrics.record_search_success(engine_name)
        return results
    except Exception as exc:
        await breaker.record_failure()
        metrics.record_search_error(engine_name)
        logger.error("Search failed for %s: %s", engine_name, exc)
        errors.append(f"{engine_name}: {exc}")
        return []
