"""Search execution — fan-out to engines, deduplicate, rank, optionally summarize."""

from __future__ import annotations

import asyncio

from evoscry.cache import cache_get, cache_key, cache_set
from evoscry.config import load_config
from evoscry.normalize.dedup import deduplicate
from evoscry.normalize.rank import rank_results
from evoscry.normalize.summarize import summarize_results
from evoscry.providers.duckduckgo import search_duckduckgo
from evoscry.providers.google import search_google


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
    engines = [e for e in engines if e in ("google", "duckduckgo")]
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
            if engine == "google":
                tasks.append(
                    _safe_search(search_google, query, max_results, language, date_range, engine_errors)
                )
            elif engine == "duckduckgo":
                tasks.append(
                    _safe_search(search_duckduckgo, query, max_results, language, date_range, engine_errors)
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


async def _safe_search(fn, query, max_results, language, date_range, errors):
    try:
        return await fn(query=query, max_results=max_results, language=language, date_range=date_range)
    except Exception as exc:
        errors.append(str(exc))
        return []
