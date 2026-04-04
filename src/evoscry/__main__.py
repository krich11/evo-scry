"""EvoScry MCP Server — internet search via DuckDuckGo and Google.

Run with::

    python -m evoscry.mcp_server                       # stdio (default)
    python -m evoscry.mcp_server --transport sse        # SSE + streamable-http
    evo-scry --transport sse --port 3000                # via installed script
"""

from evoscry.mcp_server import mcp, main

__all__ = ["mcp", "main"]

if __name__ == "__main__":
    main()
