"""EvoScry MCP Server — internet search via DuckDuckGo, Bing, Brave, and Google HTML scraping.

Tools (7):
    web_search        — multi-engine search with dedup, ranking, optional AI summary
    search_google     — Google-only search (deprecated)
    search_duckduckgo — DuckDuckGo-only search
    search_bing       — Bing-only search
    search_brave      — Brave-only search
    site_search       — domain-scoped search via site: prefix
    extract_content   — fetch URLs and extract clean text/Markdown

Run with::

    python -m evoscry.mcp_server                       # stdio (default)
    python -m evoscry.mcp_server --transport sse        # SSE + streamable-http
    python -m evoscry.mcp_server --transport streamable-http  # streamable-http only
    evo-scry --transport sse --port 3000                # via installed script
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

from mcp.server.fastmcp import FastMCP

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

# ── FastMCP app ──────────────────────────────────────────────────────────────

mcp = FastMCP(
    "evo-scry",
    instructions=(
        "You have access to EvoScry, an internet search server. "
        "Use web_search for general queries (aggregates multiple engines), "
        "search_bing, search_duckduckgo, or search_brave for engine-specific searches, "
        "and extract_content to read full articles from URLs.\n\n"
        "Tips:\n"
        "- DuckDuckGo is the default engine and most reliable (no rate limits).\n"
        "- Bing is the recommended second engine for result diversity.\n"
        "- Brave is a privacy-focused third engine with good technical-content indexing.\n"
        "- Google is deprecated — it requires JavaScript and returns empty results. "
        "Use Bing, DuckDuckGo, or Brave instead.\n"
        "- Set summarize=true on web_search to get an AI summary of results.\n"
        "- Use extract_content after searching to read promising articles.\n"
        "- Use fetch_raw to inspect a page's full HTML structure, headers, "
        "meta tags, and technology stack.\n"
        "- Date filtering: set date_range to 'day', 'week', 'month', or 'year' "
        "to restrict results by recency. DuckDuckGo and Bing support this reliably.\n"
    ),
)


# ═════════════════════════════════════════════════════════════════════════════
# Tools
# ═════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def web_search(
    query: str,
    engines: list[str] | None = None,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
    summarize: bool = False,
    expand: bool = False,
) -> str:
    """Search the internet using multiple search engines.

    Results are aggregated, deduplicated, and ranked by relevance.
    Optionally summarized using AI.

    Args:
        query: Search query text.
        engines: Engines to query (default: configured engines). Options: "bing", "brave", "duckduckgo", "google" (deprecated).
        max_results: Maximum results to return (default: 10).
        language: Language code ISO 639-1 (default: "en").
        date_range: Date range filter: "day", "week", "month", "year". DuckDuckGo and Bing are most reliable.
        summarize: Generate AI summary of top results (default: false).
        expand: Use AI to generate alternate query phrasings for broader recall (default: false).
    """
    from evoscry.search import execute_web_search

    response = await execute_web_search(
        query=query,
        engines=engines,
        max_results=max_results,
        language=language,
        date_range=date_range,
        summarize=summarize,
        expand=expand,
    )
    return json.dumps(response, indent=2)


@mcp.tool()
async def search_google(
    query: str,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
) -> str:
    """[DEPRECATED] Search Google directly. Google now requires JavaScript
    rendering and this tool typically returns empty results.
    Use search_bing or search_duckduckgo instead.

    Args:
        query: Search query text.
        max_results: Maximum results to return (default: 10).
        language: Language code (default: "en").
        date_range: Date range filter: "day", "week", "month", "year".
    """
    from evoscry.search import execute_search_google

    response = await execute_search_google(
        query=query,
        max_results=max_results,
        language=language,
        date_range=date_range,
    )
    return json.dumps(response, indent=2)


@mcp.tool()
async def search_duckduckgo(
    query: str,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
) -> str:
    """Search DuckDuckGo directly via its HTML endpoint.

    Privacy-focused, no JavaScript rendering required.

    Args:
        query: Search query text.
        max_results: Maximum results to return (default: 10).
        language: Language code (default: "en").
        date_range: Date range filter: "day", "week", "month", "year".
    """
    from evoscry.search import execute_search_ddg

    response = await execute_search_ddg(
        query=query,
        max_results=max_results,
        language=language,
        date_range=date_range,
    )
    return json.dumps(response, indent=2)


@mcp.tool()
async def search_bing(
    query: str,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
) -> str:
    """Search Bing directly. Returns parsed results from Bing's HTML search page.

    Bing is less aggressive with bot detection than Google and does not
    require JavaScript rendering.

    Args:
        query: Search query text.
        max_results: Maximum results to return (default: 10).
        language: Language code (default: "en").
        date_range: Date range filter: "day", "week", "month", "year".
    """
    from evoscry.search import execute_search_bing

    response = await execute_search_bing(
        query=query,
        max_results=max_results,
        language=language,
        date_range=date_range,
    )
    return json.dumps(response, indent=2)


@mcp.tool()
async def search_brave(
    query: str,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
) -> str:
    """Search Brave directly. Privacy-focused engine with good technical-content indexing.

    Does not require JavaScript rendering.

    Args:
        query: Search query text.
        max_results: Maximum results to return (default: 10).
        language: Language code (default: "en").
        date_range: Date range filter: "day", "week", "month", "year".
    """
    from evoscry.search import execute_search_brave

    response = await execute_search_brave(
        query=query,
        max_results=max_results,
        language=language,
        date_range=date_range,
    )
    return json.dumps(response, indent=2)


@mcp.tool()
async def site_search(
    query: str,
    site: str,
    engines: list[str] | None = None,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
) -> str:
    """Search within a specific domain using ``site:`` restriction.

    Restricts results to a single domain. Useful for searching documentation
    sites, specific repos, etc.

    Args:
        query: Search query text.
        site: Domain to restrict to (e.g., "docs.python.org").
        engines: Engines to query (default: configured engines).
        max_results: Maximum results to return (default: 10).
        language: Language code (default: "en").
        date_range: Date range filter: "day", "week", "month", "year".
    """
    from evoscry.search import execute_site_search

    response = await execute_site_search(
        query=query,
        site=site,
        engines=engines,
        max_results=max_results,
        language=language,
        date_range=date_range,
    )
    return json.dumps(response, indent=2)


@mcp.tool()
async def extract_content(
    url: str | list[str],
    format: str = "markdown",
) -> str:
    """Fetch one or more URLs and extract clean text or Markdown content.

    Useful for reading full articles from search results.

    Args:
        url: URL or list of URLs to extract content from.
        format: Output format: "text" or "markdown" (default: "markdown").
    """
    from evoscry.extract import extract_content as _extract

    urls = [url] if isinstance(url, str) else url
    results = await _extract(urls, fmt=format)
    return json.dumps(results, indent=2)


@mcp.tool()
async def fetch_raw(
    url: str | list[str],
    strip_noise: bool = True,
) -> str:
    """Fetch one or more URLs and return raw HTTP headers + HTML body.

    Unlike extract_content, this preserves the full page structure so
    you can inspect meta tags, JSON-LD, Open Graph data, script/link
    references, DOM layout, forms, and HTTP response headers.

    By default, inline script and style contents are replaced with a
    placeholder to reduce noise while keeping the tags (so you can see
    what resources are loaded). Set strip_noise=false for completely raw HTML.

    Args:
        url: URL or list of URLs to fetch.
        strip_noise: Strip inline script/style contents (default: true).
                     Tags and their attributes are preserved.
    """
    from evoscry.fetch_raw import fetch_raw as _fetch_raw

    urls = [url] if isinstance(url, str) else url
    results = await _fetch_raw(urls, strip_noise=strip_noise)
    return json.dumps(results, indent=2)


# ═════════════════════════════════════════════════════════════════════════════
# Dual-transport HTTP app (SSE + streamable-HTTP) — mirrors evo-mem pattern
# ═════════════════════════════════════════════════════════════════════════════

def _build_dual_transport_app():
    """Build a Starlette ASGI app with SSE + streamable-HTTP on the same port."""
    from mcp.server.fastmcp.server import StreamableHTTPASGIApp
    from mcp.server.sse import SseServerTransport
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    # ── SSE transport (GET /sse + POST /messages/) ──
    sse = SseServerTransport(
        "/messages/",
        security_settings=mcp.settings.transport_security,
    )

    async def handle_sse(scope, receive, send):
        async with sse.connect_sse(scope, receive, send) as streams:
            await mcp._mcp_server.run(
                streams[0],
                streams[1],
                mcp._mcp_server.create_initialization_options(),
            )
        return Response()

    async def sse_endpoint(request: Request) -> Response:
        return await handle_sse(
            request.scope, request.receive, request._send  # type: ignore[reportPrivateUsage]
        )

    # ── Streamable-HTTP transport (POST /sse) ──
    session_mgr = StreamableHTTPSessionManager(
        app=mcp._mcp_server,
        event_store=mcp._event_store,
        json_response=mcp.settings.json_response,
        stateless=mcp.settings.stateless_http,
        security_settings=mcp.settings.transport_security,
    )
    streamable_app = StreamableHTTPASGIApp(session_mgr)

    # ── REST endpoints ──
    async def health_endpoint(request: Request) -> Response:
        from evoscry.circuit_breaker import all_breaker_statuses
        from evoscry.config import load_config as _load_config
        from evoscry.metrics import metrics

        cfg = _load_config()
        breakers = all_breaker_statuses()

        engines_health: dict = {}
        for engine in cfg.search_engines:
            b = breakers.get(engine, {})
            engines_health[engine] = {
                "state": b.get("state", "closed"),
                "searches": metrics.searches_by_engine.get(engine, 0),
                "errors": metrics.errors_by_engine.get(engine, 0),
                "last_success": metrics._iso(metrics.last_success_by_engine.get(engine)),
                "last_failure": metrics._iso(metrics.last_failure_by_engine.get(engine)),
            }

        body = {
            "status": "healthy",
            "name": "evo-scry",
            "version": "2.1.0",
            "uptime_seconds": round(metrics.uptime_seconds, 1),
            "engines": engines_health,
            "cache": {
                "size": metrics.cache_size,
                "max_size": 100,
                "hits": metrics.cache_hits,
                "misses": metrics.cache_misses,
                "evictions": metrics.cache_evictions,
                "hit_rate": round(metrics.cache_hit_rate, 3),
            },
            "ai": {
                "copilot_configured": cfg.copilot_token is not None or cfg.copilot_refresh_token is not None,
                "ollama_configured": cfg.local_model_url is not None,
                "calls_total": metrics.ai_calls_total,
                "calls_failed": metrics.ai_calls_failed,
            },
            "config": {
                "transport": cfg.transport,
                "engines": cfg.search_engines,
                "max_results": cfg.max_results,
                "cache_ttl_seconds": cfg.cache_ttl_seconds,
            },
        }
        return Response(
            json.dumps(body, indent=2),
            media_type="application/json",
        )

    async def readiness_endpoint(request: Request) -> Response:
        from evoscry.circuit_breaker import all_breaker_statuses
        from evoscry.config import load_config as _load_config

        cfg = _load_config()
        breakers = all_breaker_statuses()

        # At least one configured engine must not be OPEN
        engine_ok = any(
            breakers.get(e, {}).get("state", "closed") != "open"
            for e in cfg.search_engines
        )

        ready = engine_ok
        body = {
            "ready": ready,
            "checks": {
                "at_least_one_engine_healthy": engine_ok,
                "cache_initialized": True,
            },
        }
        status = 200 if ready else 503
        return Response(
            json.dumps(body, indent=2),
            media_type="application/json",
            status_code=status,
        )

    # ── Combined routes ──
    routes = [
        Route("/health", endpoint=health_endpoint, methods=["GET"]),
        Route("/readiness", endpoint=readiness_endpoint, methods=["GET"]),
        # SSE stream — GET only
        Route("/sse", endpoint=sse_endpoint, methods=["GET"]),
        # Streamable-HTTP — POST, DELETE on /sse
        Route("/sse", endpoint=streamable_app, methods=["POST", "DELETE"]),
        # SSE message posting
        Mount("/messages/", app=sse.handle_post_message),
    ]

    _starlette_app = Starlette(
        debug=mcp.settings.debug,
        routes=routes,
        lifespan=lambda app: session_mgr.run(),
    )

    return _starlette_app


# ═════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    """Parse CLI args and run the MCP server."""
    parser = argparse.ArgumentParser(
        prog="evo-scry",
        description="EvoScry MCP Server — internet search via HTML scraping",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=None,
        help="MCP transport: stdio (default), sse (dual SSE+streamable-http), streamable-http",
    )
    parser.add_argument("--host", default=None, help="HTTP host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="HTTP port (default: 3000)")
    args = parser.parse_args()

    # CLI args override env vars
    transport = args.transport or os.environ.get("EVOSCRY_TRANSPORT", "stdio")
    host = args.host or os.environ.get("EVOSCRY_HOST", "0.0.0.0")
    port = args.port or int(os.environ.get("EVOSCRY_PORT", "3000"))

    # ── Logging setup ──
    from evoscry.config import load_config as _load_cfg

    _cfg = _load_cfg()
    import logging

    logging.basicConfig(level=getattr(logging, _cfg.log_level.upper(), logging.INFO))

    if _cfg.anonymize_logs:
        from evoscry.log_filter import AnonymizeFilter

        anon = AnonymizeFilter()
        root = logging.getLogger()
        root.addFilter(anon)
        for handler in root.handlers:
            handler.addFilter(anon)
        logging.info("Query anonymization enabled in logs")

    if transport in ("sse", "streamable-http"):
        mcp.settings.host = host
        mcp.settings.port = port

        # DNS rebinding protection for non-localhost binds
        if host not in ("127.0.0.1", "localhost", "::1"):
            sec = mcp.settings.transport_security
            if sec is not None:
                sec.allowed_hosts.append(f"{host}:*")
                sec.allowed_origins.append(f"http://{host}:*")
                if host == "0.0.0.0":
                    sec.enable_dns_rebinding_protection = False

        if transport == "sse":
            # Dual-transport: SSE + streamable-http on the same port.
            import anyio
            import uvicorn

            async def _run_dual():
                app = _build_dual_transport_app()
                config = uvicorn.Config(
                    app,
                    host=host,
                    port=port,
                    log_level="info",
                    access_log=False,
                )
                server = uvicorn.Server(config)
                await server.serve()

            print(
                f"[evo-scry] Starting SSE+streamable-http on {host}:{port}",
                file=sys.stderr,
            )
            anyio.run(_run_dual)
        else:
            print(
                f"[evo-scry] Starting streamable-http on {host}:{port}",
                file=sys.stderr,
            )
            mcp.run(transport="streamable-http")
    else:
        print("[evo-scry] Starting stdio transport", file=sys.stderr)
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
