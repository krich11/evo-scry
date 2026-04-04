# evo-scry Enhancement Ideas

## 1. Persistent Disk Cache with SQLite
Replace the in-memory LRU cache with a SQLite-backed cache that survives restarts. Would allow much larger cache sizes and TTL-based eviction without memory pressure. Use `better-sqlite3` for synchronous API that won't complicate the async flow.

## 2. Bing Search Engine Support
Add Microsoft Bing as a third search provider. Bing's HTML results page is similar to Google's but typically less aggressive with bot detection. Would improve result diversity, especially for technical queries where Bing indexes Microsoft docs uniquely well.

## 3. Search Result Streaming via MCP Progress Notifications
For multi-engine searches, stream partial results as they arrive using MCP progress notifications. This gives the client (and the user) faster first results instead of waiting for all engines to complete — especially valuable when one engine is slow or timing out.

## 4. Intent-Aware Search Strategy (inspired by OpenClaw search-layer)
Classify queries by intent (factual, comparison, tutorial, news, status, exploratory, resource) and automatically adjust search strategy: different query reformulations, engine priority, date filters, and scoring weights per intent type. The OpenClaw search-layer v2 demonstrates this pattern effectively.

## 5. Proxy Pool & Rotation
Support multiple proxy URLs with automatic rotation and health checking. When one proxy gets rate-limited, cycle to the next. Useful for heavier search loads where a single IP will hit Google's bot detection quickly. Could read proxies from a file or environment variable (comma-separated list).

## 6. Content-Aware Result Enrichment
After search, automatically follow the top N result URLs and extract a brief content preview (first 200 words). This gives the AI client much richer context than a snippet alone, reducing the need for separate `extract_content` calls. Make this an opt-in parameter like `enrich: true`.

## 7. Search History & Analytics Resource
Expose an MCP resource (`search://history`) that returns recent search queries, hit rates, cache statistics, and engine health. Useful for monitoring the server's behavior and debugging search quality issues without checking logs.

## 8. Rate Limit Budget System
Instead of a fixed delay, implement a token-bucket rate limiter per engine. Configure a requests-per-minute budget (e.g., `EVOSCRY_GOOGLE_RPM=10`). This allows burst searches when the bucket is full while enforcing long-term limits. More sophisticated than a flat delay.

## 9. Copilot Token Auto-Refresh Daemon
When `EVOSCRY_COPILOT_REFRESH_TOKEN` is set, automatically refresh the Copilot API token before it expires (tokens last ~30 minutes). Run a background timer that exchanges the GitHub OAuth token for a fresh Copilot token and updates the in-memory config. Eliminates manual token regeneration.

## 10. Multi-Language Query Reformulation
For non-English queries, automatically generate parallel English-language search variants. Search both the original language query and the English reformulation, then merge results. This dramatically improves result quality for technical topics in non-English languages where English documentation dominates.
