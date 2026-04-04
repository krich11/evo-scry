# evo-scry MCP Server — Functional Specification

**Version**: 1.0.0
**Date**: 2026-04-04
**Status**: Draft

## 1. Overview

evo-scry is a Model Context Protocol (MCP) server that provides internet search capabilities using direct HTML scraping of Google and DuckDuckGo search engines. It requires no API keys for search functionality. Search result normalization and summarization can optionally use AI via a GitHub Copilot token or a local model (Ollama).

### 1.1 Design Goals

- **Zero API keys for search**: Scrape Google and DuckDuckGo HTML endpoints directly
- **MCP-native**: Expose tools via the Model Context Protocol for use by AI agents (VS Code Copilot, Claude Desktop, etc.)
- **AI-enhanced normalization**: Optionally summarize and rank results using Copilot or local LLMs
- **Production-ready deployment**: Systemd service with full environment variable configuration
- **Multi-engine aggregation**: Combine results from multiple engines with deduplication and cross-engine ranking

### 1.2 Non-Goals

- Replace paid search APIs (Tavily, Exa, Brave) for high-volume production use
- Provide image or video search
- Bypass CAPTCHAs or sophisticated bot detection (graceful degradation instead)

## 2. Architecture

```
┌─────────────────────────────────────────────────────┐
│                    MCP Client                        │
│          (VS Code, Claude Desktop, etc.)             │
└──────────────────────┬──────────────────────────────┘
                       │ JSON-RPC 2.0
                       │ (STDIO or Streamable HTTP)
┌──────────────────────▼──────────────────────────────┐
│                  evo-scry MCP Server                 │
│                                                      │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Tools   │  │  Providers   │  │  Normalizer   │  │
│  │          │  │              │  │               │  │
│  │ web_     │──│ Google       │──│ Dedup         │  │
│  │ search   │  │ DuckDuckGo   │  │ Rank          │  │
│  │          │  │              │  │ Summarize(AI) │  │
│  │ search_  │  └──────────────┘  └───────┬───────┘  │
│  │ google   │                            │          │
│  │          │  ┌──────────────┐  ┌───────▼───────┐  │
│  │ search_  │  │    Cache     │  │  AI Clients   │  │
│  │ ddg      │  │  (in-memory) │  │               │  │
│  │          │  └──────────────┘  │ Copilot API   │  │
│  │ extract_ │                    │ Ollama (local) │  │
│  │ content  │                    └───────────────┘  │
│  └──────────┘                                        │
│                                                      │
│  ┌──────────────────────────────────────────────┐    │
│  │              Config (env vars)                │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
```

## 3. MCP Tools

### 3.1 `web_search` — Unified Multi-Engine Search

**Description**: Search the internet using Google and DuckDuckGo. Results are aggregated, deduplicated, and ranked by relevance. Optionally summarized using AI.

**Input Schema**:
| Parameter   | Type     | Required | Default         | Description |
|-------------|----------|----------|-----------------|-------------|
| query       | string   | yes      | —               | Search query text |
| engines     | string[] | no       | ["google","duckduckgo"] | Engines to query |
| maxResults  | number   | no       | 10              | Max results per engine |
| language    | string   | no       | "en"            | Language code (ISO 639-1) |
| dateRange   | string   | no       | —               | Filter: "day", "week", "month", "year" |
| summarize   | boolean  | no       | false           | Generate AI summary of top results |

**Output**: Array of normalized `SearchResult` objects (see §4), wrapped in MCP text content. When `summarize=true`, includes an AI-generated summary paragraph prepended to the results.

**Behavior**:
1. Fan out query to selected engines in parallel
2. Collect raw results from each engine
3. Normalize results into common schema
4. Deduplicate by URL (keep highest-ranked instance)
5. Apply cross-engine relevance scoring
6. If `summarize=true`, send top N results to AI for summary generation
7. Return sorted results as JSON text content

### 3.2 `search_google` — Google Search

**Description**: Search Google directly. Returns parsed results from Google's HTML search page.

**Input Schema**:
| Parameter   | Type   | Required | Default | Description |
|-------------|--------|----------|---------|-------------|
| query       | string | yes      | —       | Search query text |
| maxResults  | number | no       | 10      | Maximum results to return |
| language    | string | no       | "en"    | Language code |
| dateRange   | string | no       | —       | Filter: "day", "week", "month", "year" |

**Output**: Array of `SearchResult` objects with `engine: "google"`.

**Notes**: Uses user-agent rotation and configurable request delays to reduce blocking risk. Returns graceful error if blocked (HTTP 429/503).

### 3.3 `search_duckduckgo` — DuckDuckGo Search

**Description**: Search DuckDuckGo directly via its HTML endpoint. Privacy-focused, no JavaScript rendering required.

**Input Schema**:
| Parameter   | Type   | Required | Default | Description |
|-------------|--------|----------|---------|-------------|
| query       | string | yes      | —       | Search query text |
| maxResults  | number | no       | 10      | Maximum results to return |
| language    | string | no       | "en"    | Language code |
| dateRange   | string | no       | —       | Filter: "day", "week", "month", "year" |

**Output**: Array of `SearchResult` objects with `engine: "duckduckgo"`.

**Endpoint**: `https://html.duckduckgo.com/html/?q=<encoded_query>`

### 3.4 `extract_content` — URL Content Extraction

**Description**: Fetch one or more URLs and extract clean text or Markdown content. Useful for reading full articles from search results.

**Input Schema**:
| Parameter | Type            | Required | Default    | Description |
|-----------|-----------------|----------|------------|-------------|
| url       | string\|string[] | yes      | —          | URL(s) to extract content from |
| format    | string          | no       | "markdown" | Output format: "text" or "markdown" |

**Output**: For each URL, returns extracted content as text. Multiple URLs are processed in parallel with results keyed by URL.

**Behavior**:
1. Fetch URL with appropriate headers
2. Parse HTML with cheerio
3. Extract main content area (strip nav, ads, scripts, styles)
4. Convert to requested format
5. Return content (truncated to 50KB per URL to prevent context overflow)

## 4. Data Model

### 4.1 SearchResult

```typescript
interface SearchResult {
  rank: number;            // Position in final results (1-indexed)
  title: string;           // Result title
  url: string;             // Result URL
  snippet: string;         // Text snippet/description
  engine: "google" | "duckduckgo";  // Source engine
  publishedDate: string | null;     // ISO date if detectable
  domain: string;          // Extracted domain (e.g., "github.com")
  relevanceScore: number;  // 0.0–1.0, cross-engine normalized
  summary: string | null;  // AI-generated summary (when summarize=true)
}
```

### 4.2 SearchResponse (MCP tool output)

```typescript
interface SearchResponse {
  query: string;           // Original query
  engines: string[];       // Engines actually queried
  totalResults: number;    // Total results returned
  results: SearchResult[]; // Sorted by relevanceScore descending
  summary?: string;        // AI summary of top results (if requested)
  cached: boolean;         // Whether results came from cache
  timestamp: string;       // ISO 8601 timestamp
}
```

## 5. Search Engine Providers

### 5.1 Google Provider

**Method**: HTTP GET to `https://www.google.com/search`

**Query Parameters**:
- `q`: Search query (URL-encoded)
- `num`: Number of results (10–100)
- `hl`: Language code
- `tbs`: Date range filter (`qdr:d` day, `qdr:w` week, `qdr:m` month, `qdr:y` year)

**HTML Parsing Strategy**:
- Result containers: `div.g` elements
- Title: `h3` text within result container
- URL: `a[href]` from the result heading link
- Snippet: `div[data-sncf]` or `div.VwiC3b` text content
- Filter out ads (`div.uEierd`), knowledge panels, and "People also ask"

**Anti-Bot Measures**:
- User-agent rotation from a pool of 10+ real browser UAs
- Configurable inter-request delay (default: 1000ms)
- Respect HTTP 429/503 with exponential backoff
- Optional proxy support (HTTP/SOCKS5)

### 5.2 DuckDuckGo Provider

**Method**: HTTP GET to `https://html.duckduckgo.com/html/`

**Query Parameters**:
- `q`: Search query (URL-encoded)

**HTML Parsing Strategy**:
- Result containers: `div.result` or `.results_links`
- Title: `.result__title a` text
- URL: `.result__url` href (DuckDuckGo uses redirect URLs — extract actual URL from `uddg` param)
- Snippet: `.result__snippet` text

**Advantages**: No JavaScript rendering needed; DuckDuckGo's HTML endpoint is designed for non-JS clients and is more scraping-friendly than Google.

## 6. Result Normalization

### 6.1 Deduplication

Results from multiple engines are deduplicated by canonical URL:
1. Normalize URL (lowercase host, remove trailing slash, strip tracking params like `utm_*`)
2. Group by normalized URL
3. Keep the result with the highest relevance score
4. Merge snippets if they differ significantly

### 6.2 Relevance Scoring

Each result receives a score from 0.0 to 1.0 based on:

| Factor          | Weight | Description |
|-----------------|--------|-------------|
| Position        | 0.40   | Inverse of rank position (1/rank) |
| Keyword match   | 0.25   | Proportion of query terms in title + snippet |
| Domain authority | 0.20  | Pre-scored domain tiers (tier 1: github.com, stackoverflow.com, etc.) |
| Freshness       | 0.15   | Recency bonus if date detectable |

Cross-engine boost: Results appearing in both engines get a 1.2x multiplier.

### 6.3 AI Summarization

When `summarize=true`:
1. Take top 5 results (title + snippet + URL)
2. Send to AI provider (Copilot or local model) with prompt:
   > "Summarize the following search results for the query '{query}'. Provide a concise 2-3 sentence overview of what the results indicate."
3. Attach summary to the response as `summary` field
4. If AI is unavailable, return results without summary (no error)

## 7. AI Integration

### 7.1 GitHub Copilot

**Token acquisition**: OAuth Device Flow via `scripts/generate-copilot-token.ts`

1. `POST https://github.com/login/device/code` with `client_id` and `scope=copilot`
2. Display user code + verification URL to user
3. Poll `POST https://github.com/login/oauth/access_token` for token
4. Exchange GitHub token for Copilot token via `GET https://api.github.com/copilot_internal/v2/token`
5. Store token in environment variable or file

**API**: `POST https://api.githubcopilot.com/chat/completions` with model `gpt-4o`

### 7.2 Local Model (Ollama)

**Endpoint**: Configurable (default `http://localhost:11434/api/chat`)
**Model**: Configurable (default `llama3`)
**Fallback**: Used when Copilot token is unavailable or expired

## 8. Configuration

All options are configurable via environment variables, suitable for systemd `EnvironmentFile` directive.

| Variable | Default | Description |
|----------|---------|-------------|
| `EVOSCRY_TRANSPORT` | `stdio` | Transport: `stdio` or `http` |
| `EVOSCRY_PORT` | `3000` | HTTP port (when transport=http) |
| `EVOSCRY_SEARCH_ENGINES` | `google,duckduckgo` | Enabled engines |
| `EVOSCRY_MAX_RESULTS` | `10` | Max results per engine |
| `EVOSCRY_REQUEST_DELAY_MS` | `1000` | Inter-request delay (ms) |
| `EVOSCRY_USER_AGENT` | `rotate` | UA string or "rotate" |
| `EVOSCRY_PROXY_URL` | — | HTTP/SOCKS5 proxy |
| `EVOSCRY_COPILOT_TOKEN` | — | Copilot API token |
| `EVOSCRY_COPILOT_REFRESH_TOKEN` | — | Copilot refresh token |
| `EVOSCRY_LOCAL_MODEL_URL` | — | Ollama endpoint |
| `EVOSCRY_LOCAL_MODEL_NAME` | `llama3` | Ollama model name |
| `EVOSCRY_LOG_LEVEL` | `info` | Log level |
| `EVOSCRY_CACHE_TTL_SECONDS` | `300` | Cache TTL (0=off) |

## 9. Transport

### 9.1 STDIO (default)

Standard input/output JSON-RPC communication. Used by VS Code Copilot, Claude Desktop, and other local MCP clients.

**MCP Client Configuration** (Claude Desktop example):
```json
{
  "mcpServers": {
    "evo-scry": {
      "command": "node",
      "args": ["/path/to/evo-scry/dist/index.js"],
      "env": {
        "EVOSCRY_COPILOT_TOKEN": "your-token"
      }
    }
  }
}
```

### 9.2 Streamable HTTP (systemd)

HTTP server exposing the MCP endpoint for remote clients. Used when deployed as a systemd service.

**Endpoint**: `POST http://localhost:3000/mcp`

## 10. Error Handling

| Scenario | Behavior |
|----------|----------|
| Google blocks request (429/503) | Return DuckDuckGo-only results with warning |
| DuckDuckGo unavailable | Return Google-only results with warning |
| Both engines fail | Return error with diagnostics |
| AI summarization fails | Return results without summary (no error) |
| Invalid query (empty string) | Return MCP error with descriptive message |
| URL extraction fails | Return error for that URL, continue others |
| Network timeout | 10-second default timeout per request |

## 11. Caching

In-memory LRU cache with configurable TTL (default 300 seconds):
- **Key**: `SHA-256(engine + query + language + dateRange + maxResults)`
- **Value**: Raw engine results (pre-normalization)
- **Eviction**: TTL-based + LRU when cache exceeds 100 entries
- **Bypass**: Can be disabled with `EVOSCRY_CACHE_TTL_SECONDS=0`

## 12. Security Considerations

- **Input sanitization**: Query strings are validated and encoded before use in HTTP requests
- **URL validation**: Only `http://` and `https://` schemes permitted in `extract_content`
- **No credential logging**: Copilot tokens never appear in log output
- **Rate limiting**: Built-in delay between requests prevents abuse of search engines
- **Proxy safety**: Proxy URL validated for supported schemes (http, https, socks5)
