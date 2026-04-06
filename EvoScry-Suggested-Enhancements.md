# EvoScry — Suggested Enhancements

This document proposes sixteen enhancements to the EvoScry MCP search server, organized into five categories. Each enhancement is described in sufficient detail that a formal function specification could be written directly from it without additional discovery.

All references to existing code correspond to the EvoScry v2.0.0 codebase as of April 2026.

---

## Table of Contents

### Search Quality
- [E-01 — Brave Search Provider](#e-01--brave-search-provider)
- [E-02 — Query Expansion via LLM](#e-02--query-expansion-via-llm)
- [E-03 — Snippet Quality Scoring](#e-03--snippet-quality-scoring)
- [E-04 — Date-Restricted Search Hardening](#e-04--date-restricted-search-hardening)

### Architecture & Reliability
- [E-05 — Playwright Fallback for Google](#e-05--playwright-fallback-for-google)
- [E-06 — Circuit Breaker Per Engine](#e-06--circuit-breaker-per-engine)
- [E-07 — Health and Readiness Probes](#e-07--health-and-readiness-probes)
- [E-08 — Webhook Notification on Degradation](#e-08--webhook-notification-on-degradation)

### MCP-Native Features
- [E-09 — MCP Resources for Curated Sources](#e-09--mcp-resources-for-curated-sources)
- [E-10 — `site_search` Tool](#e-10--site_search-tool)
- [E-11 — `find_similar` Tool](#e-11--find_similar-tool)

### Content & Extraction
- [E-12 — PDF and GitHub Content Extraction](#e-12--pdf-and-github-content-extraction)
- [E-13 — Structured Data Extraction](#e-13--structured-data-extraction)
- [E-14 — Screenshot Capture](#e-14--screenshot-capture)

### Privacy & Security
- [E-15 — Tor Transport Option](#e-15--tor-transport-option)
- [E-16 — Query Anonymization Log Mode](#e-16--query-anonymization-log-mode)

---

## Search Quality

---

### E-01 — Brave Search Provider

#### Summary

Add Brave Search as a fourth search provider, following the same implicit provider protocol used by DuckDuckGo and Bing. Brave's HTML search endpoint does not require JavaScript rendering, making it a natural fit for EvoScry's HTML-scraping architecture. A third reliable engine improves result diversity and strengthens the cross-engine ranking boost (results appearing in 2+ engines receive a 1.2× multiplier in `rank_results()`).

#### Motivation

EvoScry currently has two reliable engines (DuckDuckGo, Bing) and one deprecated engine (Google). Google's deprecation leaves the system dependent on only two sources. If either DuckDuckGo or Bing begins aggressive bot-blocking, search quality degrades significantly. Brave Search provides a privacy-focused alternative with good technical-content indexing and minimal anti-bot measures on its HTML endpoint.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/providers/brave.py` | **Create** — new provider module |
| `src/evoscry/providers/__init__.py` | **Modify** — export `search_brave` |
| `src/evoscry/config.py` | **Modify** — add `"brave"` to valid engine whitelist |
| `src/evoscry/search.py` | **Modify** — add `"brave"` case to engine dispatch in `execute_web_search()` and add `execute_search_brave()` single-engine function |
| `src/evoscry/mcp_server.py` | **Modify** — register new `search_brave` MCP tool |

#### New Configuration

| Env Var | Change |
|---------|--------|
| `EVOSCRY_SEARCH_ENGINES` | Accept `"brave"` as a valid value (e.g., `"duckduckgo,bing,brave"`) |

No new environment variables are required. The existing `EVOSCRY_SEARCH_ENGINES` comma-separated list is sufficient.

#### Interface / API Changes

**New provider function** (implicit protocol — no base class):

```
async def search_brave(
    query: str,
    max_results: int = 10,
    language: str = "en",
    date_range: str | None = None,
    **_kwargs
) -> list[dict]
```

Return type: `list[SearchResult]` where each dict contains `{"title": str, "url": str, "snippet": str, "engine": "brave", "published_date": str | None}`.

**New MCP tool** `search_brave`:

```
Parameters:
  query: str          — Search query text [required]
  max_results: int    — Max results (default: config value)
  language: str       — ISO 639-1 code (default: "en")
  date_range: str     — "day" | "week" | "month" | "year" | null
  
Returns: JSON string with {"query", "engine": "brave", "total_results", "results"}
```

#### Implementation Details

**Endpoint**: `https://search.brave.com/search`

**Request construction**:
- Method: GET
- Query parameters: `q` (query), `source` (`web`), `tf` (time filter)
- Date range mapping: `{"day": "pd", "week": "pw", "month": "pm", "year": "py"}`
- Language: set via `Accept-Language` header using the `language` parameter value

**User-Agent strategy**: Use a pool of 3 mobile user-agents (similar to Bing's `_MOBILE_UAS` pattern in `providers/bing.py`) to reduce anti-bot detection. Brave's HTML endpoint is less aggressive than Google but more so than DuckDuckGo. Rotate via module-level index.

**HTML parsing**:
- Parser: BeautifulSoup with lxml backend (existing dependency)
- Result container: CSS selector `div.snippet` (each organic result)
- Title extraction: `a.snippet-title` → `.get_text(strip=True)`
- URL extraction: `a.snippet-title["href"]` — Brave uses direct URLs (no redirect wrappers)
- Snippet extraction: `p.snippet-description` → `.get_text(strip=True)`
- Published date extraction: Check for date prefix pattern in snippet using regex `r'^(\w{3}\s+\d{1,2},\s+\d{4})'` (same pattern as Bing provider), parse with `strptime("%b %d, %Y")`, format as `"%Y-%m-%d"`. Strip date prefix from snippet text.
- Ad filtering: Skip results inside `div.ad-result` or any element with class containing `"ad"` or `"sponsored"`

**Rate limiting**: Uses existing `fetch_with_config()` from `http_client.py`, which enforces `EVOSCRY_REQUEST_DELAY_MS` automatically.

**Error handling**: Wrap in try/except matching the `_safe_search()` pattern in `search.py`. HTTP 429 → raise `RuntimeError` with retry guidance. HTTP 403 → log warning, return empty list. Other errors → propagate to `_safe_search()` for collection.

**Search dispatch integration** in `search.py`:

```
# In execute_web_search(), add to the engine dispatch:
"brave": _safe_search(search_brave, query, max_results, language, date_range)

# New single-engine function:
async def execute_search_brave(query, max_results, language, date_range) -> dict
```

#### Dependencies

No new Python dependencies. Uses existing `httpx`, `beautifulsoup4`, `lxml`.

#### Acceptance Criteria

1. `search_brave("python asyncio", max_results=5)` returns 3–5 results with valid URLs, non-empty titles, and non-empty snippets
2. `web_search("python asyncio", engines=["brave", "duckduckgo"])` returns deduplicated, ranked results from both engines, with cross-engine boost applied to URLs found in both
3. `"brave"` appears in the `EVOSCRY_SEARCH_ENGINES` validation whitelist
4. Brave results follow the `SearchResult` dict structure with `"engine": "brave"`
5. Date range parameter `"week"` produces time-filtered results
6. Ad results are excluded from output

---

### E-02 — Query Expansion via LLM

#### Summary

Before the search fan-out in `execute_web_search()`, optionally invoke the AI backend to generate 2–3 reformulated queries (synonyms, related terms, alternate phrasings). All variants are searched in parallel alongside the original query, and results are merged through the existing deduplication and ranking pipeline. This significantly improves recall for vague, ambiguous, or jargon-heavy queries.

#### Motivation

Users and AI agents frequently issue underspecified queries. A search for "fix slow docker" could benefit from parallel searches for "docker container performance optimization" and "docker build cache slow". Currently, EvoScry searches exactly the query given. LLM-based expansion leverages the already-configured AI backend (Copilot or Ollama) to generate smarter variants before the search even begins, leading to broader and more relevant result sets.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/normalize/expand.py` | **Create** — new query expansion module |
| `src/evoscry/normalize/__init__.py` | **Modify** — export `expand_query` |
| `src/evoscry/search.py` | **Modify** — call `expand_query()` in `execute_web_search()` before fan-out, when `expand=True` |
| `src/evoscry/mcp_server.py` | **Modify** — add `expand: bool = False` parameter to `web_search` tool schema |
| `src/evoscry/config.py` | **Modify** — add `query_expansion_max` field to `Config` |

#### New Configuration

| Env Var | Type | Default | Description |
|---------|------|---------|-------------|
| `EVOSCRY_QUERY_EXPANSION_MAX` | int | 3 | Maximum number of alternate queries to generate |

#### Interface / API Changes

**New function** in `src/evoscry/normalize/expand.py`:

```
async def expand_query(
    query: str,
    max_expansions: int = 3
) -> list[str]
```

- Returns a list of 1–`max_expansions` alternate query strings
- Returns `[query]` (original only) if AI backend is unavailable or expansion fails
- Never returns an empty list

**Modified `web_search` MCP tool** — new parameter:

```
expand: bool = False   — Generate alternate query phrasings via AI before searching
```

**Modified `execute_web_search()`** — new parameter:

```
async def execute_web_search(
    query: str,
    engines: list[str] | None = None,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
    summarize: bool = False,
    expand: bool = False,          # NEW
) -> dict
```

#### Implementation Details

**AI prompt template** for query expansion:

```
Given the search query: "{query}"

Generate {max_expansions} alternative search queries that would help find relevant results.
Each alternative should approach the topic from a different angle: synonyms, related terms,
more specific phrasing, or broader context.

Return ONLY a JSON array of strings, with no additional text. Example:
["alternative query 1", "alternative query 2", "alternative query 3"]
```

**AI invocation**: Reuse the `_chat_with_ai()` dispatch pattern from `src/evoscry/normalize/summarize.py`:
1. If Copilot token available → call `chat_copilot(prompt, token, refresh_token)` with `max_tokens=200`, `temperature=0.7` (higher than summarization to encourage diversity)
2. If Ollama available → call `chat_local(prompt, url, model_name)`
3. If neither available → return `[query]` (graceful fallback, no error)

**Response parsing**:
1. Strip whitespace from AI response
2. Attempt `json.loads()` to parse as `list[str]`
3. If parsing fails, attempt regex extraction: `r'\[.*?\]'` to find JSON array in response
4. If still unparseable, log warning and return `[query]`
5. Validate each expansion is a non-empty string; filter out empties
6. Truncate list to `max_expansions`
7. Always prepend original query to the list (deduplicated)

**Search pipeline modification** in `execute_web_search()`:

```
# After validation, before fan-out:
if expand:
    queries = await expand_query(query, config.query_expansion_max)
else:
    queries = [query]

# Fan-out: for each query variant × each engine, create tasks:
tasks = []
for q in queries:
    for engine in engines:
        tasks.append(_safe_search(provider[engine], q, max_results, language, date_range))

all_results = await asyncio.gather(*tasks)
# Flatten, then proceed with existing dedup → rank → trim pipeline
```

**Cache key**: Include `expand` flag and the expanded queries in the cache key dict so that expanded and non-expanded searches are cached separately.

**Performance note**: Expansion adds one AI call (150–300ms for Copilot, 500ms–2s for Ollama) before the search fan-out. Total additional latency is bounded by this single AI call since the expanded query searches run in parallel.

#### Dependencies

No new Python dependencies. Uses existing AI integration (`chat_copilot`, `chat_local`) and `json` stdlib.

#### Acceptance Criteria

1. `web_search("fix slow docker", expand=True)` generates 2–3 alternate queries and returns a richer result set than `expand=False`
2. When AI backend is unavailable, `expand=True` silently falls back to original query only (no error)
3. Malformed AI responses (non-JSON, empty, etc.) are handled gracefully with fallback to original query
4. Expanded and non-expanded searches produce separate cache entries
5. The `expand` parameter appears in the `web_search` MCP tool schema
6. AI call timeout does not exceed 5 seconds (fail fast, fall back)

---

### E-03 — Snippet Quality Scoring

#### Summary

Add a heuristic filter that scores the information quality of each search result snippet. Low-quality snippets (login prompts, cookie walls, boilerplate) are penalized in the ranking pipeline. This improves the signal-to-noise ratio of search results, particularly for queries that return many gated or SEO-heavy pages.

#### Motivation

Scraped search engine snippets frequently contain non-informative text: "Sign in to continue", "Accept cookies to proceed", "Enable JavaScript", or near-empty strings. These results waste context window space when consumed by AI agents. Currently, `rank_results()` in `rank.py` uses four scoring factors (position, keyword match, domain authority, freshness) — none of which account for snippet content quality. Adding a fifth factor directly targets this gap.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/normalize/filter.py` | **Create** — snippet quality scoring module |
| `src/evoscry/normalize/__init__.py` | **Modify** — export `snippet_quality` |
| `src/evoscry/normalize/rank.py` | **Modify** — integrate snippet quality as 5th scoring factor; rebalance weights |

#### New Configuration

No new environment variables. Quality thresholds and patterns are hardcoded as module-level constants in `filter.py`. This keeps the feature simple and avoids configuration sprawl for what is fundamentally a heuristic filter.

#### Interface / API Changes

**New function** in `src/evoscry/normalize/filter.py`:

```
def snippet_quality(snippet: str) -> float
```

- Input: raw snippet string from a `SearchResult` dict
- Output: float in range [0.0, 1.0] where 1.0 is high-quality and 0.0 is garbage
- Pure function, no side effects, no I/O

**Modified weight constants** in `src/evoscry/normalize/rank.py`:

```
# Current weights (sum = 1.0):
W_POSITION  = 0.40
W_KEYWORD   = 0.25
W_AUTHORITY = 0.20
W_FRESHNESS = 0.15

# Proposed weights (sum = 1.0):
W_POSITION  = 0.35
W_KEYWORD   = 0.22
W_AUTHORITY = 0.18
W_FRESHNESS = 0.13
W_SNIPPET   = 0.12
```

**Modified scoring** in `rank_results()`: add `snippet_quality(result["snippet"])` as the fifth factor in the weighted sum.

#### Implementation Details

**Low-quality indicator patterns** (compiled regex, case-insensitive):

```python
LOW_QUALITY_PATTERNS = [
    r"sign\s*in",
    r"log\s*in\s*(to\s+)?(continue|access|view)",
    r"accept\s*(all\s+)?cookies",
    r"cookie\s*(policy|consent|banner)",
    r"enable\s+javascript",
    r"your\s+browser\s+(does\s+not|doesn't)\s+support",
    r"please\s+enable",
    r"subscribe\s+to\s+(read|continue|access|view|unlock)",
    r"(create|sign\s*up\s+for)\s+(a\s+)?(free\s+)?account",
    r"you('ve|\s+have)\s+reached\s+(your|the)\s+(free\s+)?(article\s+)?limit",
    r"this\s+content\s+is\s+(only\s+)?available\s+to\s+(subscribers|members)",
    r"access\s+denied",
    r"403\s+forbidden",
    r"page\s+not\s+found",
    r"404\s+error",
]
```

**Scoring algorithm** (`snippet_quality()`):

```
1. If snippet is None or empty → return 0.0
2. stripped = snippet.strip()
3. If len(stripped) < 20 → return 0.1  (too short to be useful)
4. If len(stripped) < 50 → return 0.4  (marginal)
5. penalty = 0.0
6. For each pattern in LOW_QUALITY_PATTERNS:
     If regex matches in stripped: penalty += 0.25
7. penalty = min(penalty, 0.9)  (cap so even bad snippets get a floor)
8. word_count = len(stripped.split())
9. variety = len(set(stripped.lower().split())) / word_count  (unique/total ratio)
10. If variety < 0.3: penalty += 0.2  (repetitive text)
11. base_score = 1.0
12. Return max(0.0, base_score - penalty)
```

**Integration into `rank_results()`**:

In the scoring loop where `position`, `keyword`, `authority`, and `freshness` are computed for each result, add:

```
snippet_score = snippet_quality(result.get("snippet", ""))
score = (W_POSITION * position
         + W_KEYWORD * keyword
         + W_AUTHORITY * authority
         + W_FRESHNESS * freshness
         + W_SNIPPET * snippet_score)
```

#### Dependencies

No new Python dependencies. Uses `re` from stdlib.

#### Acceptance Criteria

1. `snippet_quality("Sign in to continue reading this article")` returns ≤ 0.5
2. `snippet_quality("Python asyncio provides a framework for writing concurrent code using the async/await syntax.")` returns ≥ 0.8
3. `snippet_quality("")` returns 0.0
4. `snippet_quality("x")` returns 0.1
5. Results with low-quality snippets rank lower than equivalent results with informative snippets
6. All five weight constants in `rank.py` sum to 1.0

---

### E-04 — Date-Restricted Search Hardening

#### Summary

Harden the existing `date_range` parameter handling across all search tools. The `date_range` parameter and per-engine `DATE_RANGE_MAP` dicts already exist in the codebase but lack input validation, have inconsistent documentation in MCP tool descriptions, and provide no guidance on per-engine effectiveness. This enhancement adds validation, improves tool descriptions, and documents engine-specific behavior.

#### Motivation

The `date_range` parameter is accepted by all five MCP tools and forwarded to all three providers, each of which maps it to engine-specific query parameters. However, there is no validation — an invalid value like `"yesterday"` is silently passed through and ignored by the provider `DATE_RANGE_MAP.get()` calls (returning `None`). The `web_search` tool description in `mcp_server.py` does not prominently document the available date range options. Agents frequently want time-filtered results (recent news, latest documentation) but may not discover this capability.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/search.py` | **Modify** — add `date_range` validation at the top of `execute_web_search()` and each `execute_search_*()` function |
| `src/evoscry/mcp_server.py` | **Modify** — update tool descriptions for `web_search`, `search_duckduckgo`, and `search_bing` to prominently document `date_range` options and per-engine notes |

#### New Configuration

None.

#### Interface / API Changes

No changes to function signatures or return types. The only changes are:

1. **Validation**: Invalid `date_range` values now raise `ValueError` with a descriptive message listing valid options, instead of being silently ignored.

2. **Tool descriptions**: MCP tool docstrings updated to include:
   - Explicit list of valid values: `"day"`, `"week"`, `"month"`, `"year"`, or `null`
   - Per-engine effectiveness notes

#### Implementation Details

**Validation** — add at the top of `execute_web_search()` and each `execute_search_*()`:

```python
VALID_DATE_RANGES = {"day", "week", "month", "year", None}

if date_range is not None and date_range not in VALID_DATE_RANGES:
    raise ValueError(
        f"Invalid date_range '{date_range}'. "
        f"Valid options: 'day', 'week', 'month', 'year', or null/None."
    )
```

**Tool description updates** — add to each search tool's MCP docstring:

```
Date filtering:
  - "day"   — results from the past 24 hours
  - "week"  — results from the past 7 days
  - "month" — results from the past 30 days
  - "year"  — results from the past 12 months
  - null    — no date filter (default)

Engine-specific notes:
  - DuckDuckGo: Date filtering is reliable and consistently applied.
  - Bing: Date filtering works well; uses the Bing "filters" parameter.
  - Google: DEPRECATED — Google provider returns empty results regardless of date filter.
```

**Per-engine date parameter mapping** (already implemented, documented here for completeness):

| Engine | Parameter | day | week | month | year |
|--------|-----------|-----|------|-------|------|
| DuckDuckGo | `df` (form field) | `"d"` | `"w"` | `"m"` | `"y"` |
| Bing | `filters` (query param) | `ex1:"ez1"` | `ex1:"ez2"` | `ex1:"ez3"` | `ex1:"ez5"` |
| Google | `tbs` (query param) | `qdr:d` | `qdr:w` | `qdr:m` | `qdr:y` |

#### Dependencies

None.

#### Acceptance Criteria

1. `execute_web_search("test", date_range="yesterday")` raises `ValueError` with descriptive message
2. `execute_web_search("test", date_range="week")` succeeds normally
3. `execute_web_search("test", date_range=None)` succeeds normally (no filter applied)
4. MCP tool descriptions for `web_search`, `search_duckduckgo`, and `search_bing` include date range documentation
5. Invalid `date_range` on single-engine tools (`search_bing`, `search_duckduckgo`) also raises `ValueError`

---

## Architecture & Reliability

---

### E-05 — Playwright Fallback for Google

#### Summary

Restore Google search functionality by providing an optional Playwright-based provider that uses headless Chromium to render Google's JavaScript-heavy search results page. This is gated behind a feature flag and an optional dependency so it does not affect the default lightweight install.

#### Motivation

The Google provider in `src/evoscry/providers/google.py` is deprecated because Google now requires full JavaScript rendering — the current `fetch_with_config()` GET request returns a page with `"enablejs"` or `<noscript>` content, and `search_google()` correctly detects this and returns an empty list. Google remains the highest-quality general search engine, and many users would benefit from having it available. Playwright provides a maintained, headless browser that can render Google's results page.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/providers/google_playwright.py` | **Create** — Playwright-based Google search implementation |
| `src/evoscry/providers/google.py` | **Modify** — when `EVOSCRY_ENABLE_PLAYWRIGHT=true`, delegate to `google_playwright.search_google_pw()` instead of returning empty |
| `src/evoscry/config.py` | **Modify** — add `enable_playwright` field to `Config` |
| `pyproject.toml` | **Modify** — add `playwright` to `[project.optional-dependencies.playwright]` |

#### New Configuration

| Env Var | Type | Default | Description |
|---------|------|---------|-------------|
| `EVOSCRY_ENABLE_PLAYWRIGHT` | bool | `false` | Enable Playwright-based browser rendering for Google search |

#### Interface / API Changes

**New internal function** in `src/evoscry/providers/google_playwright.py`:

```
async def search_google_pw(
    query: str,
    max_results: int = 10,
    language: str = "en",
    date_range: str | None = None
) -> list[dict]
```

Returns the standard `list[SearchResult]` with `"engine": "google"`.

**Modified `search_google()`** in `providers/google.py`: when Playwright is enabled and importable, delegates to `search_google_pw()` instead of returning empty results. The function signature remains unchanged.

**Browser lifecycle functions** (module-level in `google_playwright.py`):

```
async def _get_browser() -> Browser
    # Lazy-initialize and cache a single browser instance

async def close_browser() -> None
    # Graceful shutdown; called from server shutdown hook
```

#### Implementation Details

**Lazy import pattern** — Playwright is only imported when `EVOSCRY_ENABLE_PLAYWRIGHT=true`:

```python
# In google.py, at the top of search_google():
if config.enable_playwright:
    try:
        from .google_playwright import search_google_pw
        return await search_google_pw(query, max_results, language, date_range)
    except ImportError:
        logger.warning("Playwright not installed; Google search unavailable")
        return []
```

**Browser instance management**:

```python
_browser: Browser | None = None
_browser_lock = asyncio.Lock()

async def _get_browser() -> Browser:
    global _browser
    async with _browser_lock:
        if _browser is None:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            _browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
        return _browser
```

**Search execution**:

1. Get or create browser instance via `_get_browser()`
2. Create new browser context with:
   - Desktop user-agent from `http_client.USER_AGENTS` pool (not mobile — Google desktop layout is more parseable)
   - Viewport: 1280×720
   - Locale: `language` parameter value
3. Create new page
4. Build Google URL: `https://www.google.com/search?q={query}&num={max_results+5}&hl={language}`
   - If `date_range`: append `&tbs={DATE_RANGE_MAP[date_range]}`
5. Navigate with `page.goto(url, wait_until="domcontentloaded", timeout=12000)`
6. Wait for selector `div.g` with timeout 5000ms
7. Parse results: `page.query_selector_all("div.g")`
8. For each result element:
   - Title: `el.query_selector("h3")` → `inner_text()`
   - URL: `el.query_selector("a")` → `get_attribute("href")` — filter to `http(s)` only
   - Snippet: `el.query_selector("div[data-sncf], div.VwiC3b, span.aCOpRe")` → `inner_text()`
   - Ad detection: skip if parent has class `"uEierd"` or `data-text-ad` attribute
   - Date extraction: same regex pattern as Bing provider
9. Close page and context (browser persists)
10. Return list of dicts up to `max_results`

**Timeout and error handling**:
- Overall search timeout: 15 seconds
- If `div.g` selector not found: log warning, return empty (Google may have changed layout)
- On `playwright.async_api.Error`: log, return empty
- On `TimeoutError`: log, return empty

**Shutdown hook**: Register `close_browser()` as an `atexit` handler or hook into the MCP server's shutdown sequence to close the browser process gracefully.

**Resource constraints**: Only one browser instance is created (shared across searches). Each search creates and destroys its own context and page, preventing cookie/state leakage between searches.

#### Dependencies

New optional dependency:

```toml
[project.optional-dependencies]
playwright = ["playwright>=1.40"]
```

Post-install: `playwright install chromium` required to download browser binary. Document this in setup instructions.

#### Acceptance Criteria

1. With `EVOSCRY_ENABLE_PLAYWRIGHT=true` and Playwright installed: `search_google("python asyncio")` returns 5+ results with valid URLs
2. With `EVOSCRY_ENABLE_PLAYWRIGHT=false`: `search_google()` returns empty list (existing behavior)
3. With `EVOSCRY_ENABLE_PLAYWRIGHT=true` but Playwright not installed: `search_google()` returns empty list with a logged warning (no crash)
4. Browser instance is reused across multiple searches (verified via logging)
5. Ad results are excluded
6. Server shutdown cleanly terminates the browser process

---

### E-06 — Circuit Breaker Per Engine

#### Summary

Implement a per-engine circuit breaker that tracks consecutive failures and temporarily disables engines that are unreliable. This prevents wasting time and rate-limit budget on engines that are actively blocking requests, and allows automatic recovery when the engine becomes available again.

#### Motivation

Currently, `_safe_search()` in `search.py` catches exceptions from individual engine calls and adds them to an error list, but always attempts every configured engine on every search. If Bing starts returning HTTP 429 consistently, every search still waits for Bing's timeout before falling back. A circuit breaker skips known-bad engines immediately and automatically retests them after a cooldown period.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/circuit_breaker.py` | **Create** — circuit breaker implementation |
| `src/evoscry/search.py` | **Modify** — integrate circuit breaker into `_safe_search()` and `execute_web_search()` |
| `src/evoscry/config.py` | **Modify** — add circuit breaker config fields |

#### New Configuration

| Env Var | Type | Default | Description |
|---------|------|---------|-------------|
| `EVOSCRY_CIRCUIT_FAILURE_THRESHOLD` | int | 5 | Consecutive failures before opening circuit |
| `EVOSCRY_CIRCUIT_RECOVERY_TIMEOUT` | int | 60 | Seconds to wait before half-open test |

#### Interface / API Changes

**New class** in `src/evoscry/circuit_breaker.py`:

```
class CircuitState(Enum):
    CLOSED = "closed"         # Normal operation
    OPEN = "open"             # Engine disabled
    HALF_OPEN = "half_open"   # Testing recovery

class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: int = 60)
    
    @property
    def state(self) -> CircuitState
    
    @property
    def failure_count(self) -> int
    
    @property
    def last_failure_time(self) -> float | None
    
    async def can_execute(self) -> bool
        # Returns True if circuit is CLOSED or HALF_OPEN (after recovery timeout)
    
    async def record_success(self) -> None
        # Reset failure count, transition to CLOSED
    
    async def record_failure(self) -> None
        # Increment failure count, potentially transition to OPEN
    
    def status(self) -> dict
        # Return {"name", "state", "failure_count", "last_failure_time"} for health endpoint
```

**Module-level registry**:

```
_breakers: dict[str, CircuitBreaker] = {}

def get_breaker(engine: str) -> CircuitBreaker
    # Get or create circuit breaker for an engine name
```

#### Implementation Details

**State machine**:

```
CLOSED (normal)
  │
  ├── on success → stay CLOSED (reset failure count to 0)
  │
  └── on failure → increment failure_count
        │
        └── if failure_count >= threshold → transition to OPEN
                                              │
                                              └── record open_time = monotonic()

OPEN (engine disabled)
  │
  ├── can_execute() called:
  │     if (monotonic() - open_time) >= recovery_timeout:
  │       → transition to HALF_OPEN, return True
  │     else:
  │       → return False (skip engine)

HALF_OPEN (testing one request)
  │
  ├── on success → transition to CLOSED (reset failure count)
  │
  └── on failure → transition to OPEN (reset open_time)
```

**Thread safety**: Each `CircuitBreaker` instance uses an `asyncio.Lock` to protect state transitions. Since EvoScry is single-process async, this is sufficient.

**Integration into `search.py`**:

```python
# Modified _safe_search():
async def _safe_search(engine_name, search_fn, query, max_results, language, date_range):
    breaker = get_breaker(engine_name)
    
    if not await breaker.can_execute():
        logger.warning(f"Circuit OPEN for {engine_name}, skipping")
        return []   # Do not count as error — engine is known-bad
    
    try:
        results = await search_fn(query, max_results, language, date_range)
        await breaker.record_success()
        return results
    except Exception as e:
        await breaker.record_failure()
        logger.error(f"Search failed for {engine_name}: {e}")
        return []
```

**Logging**:
- Log at WARNING level when circuit transitions to OPEN: `"Circuit breaker OPEN for {engine}: {failure_count} consecutive failures"`
- Log at INFO level when circuit transitions to HALF_OPEN: `"Circuit breaker testing recovery for {engine}"`
- Log at INFO level when circuit transitions to CLOSED from HALF_OPEN: `"Circuit breaker recovered for {engine}"`

#### Dependencies

No new dependencies. Uses `asyncio`, `enum`, `time` from stdlib.

#### Acceptance Criteria

1. After 5 consecutive failures for an engine, `can_execute()` returns `False` (circuit OPEN)
2. After `recovery_timeout` seconds, `can_execute()` returns `True` (circuit HALF_OPEN)
3. A successful search in HALF_OPEN state transitions to CLOSED
4. A failed search in HALF_OPEN state transitions back to OPEN
5. Circuit breaker status is accessible via `.status()` dict for health endpoint integration
6. Concurrent searches do not cause race conditions in state transitions

---

### E-07 — Health and Readiness Probes

#### Summary

Expand the existing `/health` HTTP endpoint to return detailed operational status, and add a `/readiness` endpoint for deployment orchestrators. The health response includes per-engine status, cache statistics, AI backend availability, and server uptime. A new metrics module tracks counters across the server lifetime.

#### Motivation

EvoScry's current `/health` endpoint returns a minimal response suitable for basic liveness checks but provides no insight into operational quality. For systemd deployments (the documented production path), operators need to know: which engines are working, whether the cache is effective, and whether AI summarization is available. For Kubernetes deployments, a readiness probe is needed to remove unhealthy instances from load balancing.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/metrics.py` | **Create** — global metrics counters |
| `src/evoscry/mcp_server.py` | **Modify** — expand `/health` response, add `/readiness` route |
| `src/evoscry/search.py` | **Modify** — increment metrics counters on search events |
| `src/evoscry/cache.py` | **Modify** — increment cache hit/miss/eviction counters |

#### New Configuration

None. Health and readiness endpoints are always available when running in SSE or streamable-http transport mode.

#### Interface / API Changes

**New module** `src/evoscry/metrics.py`:

```
class Metrics:
    # Server
    start_time: float              # monotonic() at server start
    
    # Searches
    search_total: int              # Total searches executed
    search_errors: int             # Total search errors
    searches_by_engine: dict[str, int]   # Per-engine search count
    errors_by_engine: dict[str, int]     # Per-engine error count
    last_success_by_engine: dict[str, float]  # Per-engine last success timestamp
    last_failure_by_engine: dict[str, float]  # Per-engine last failure timestamp
    
    # Cache
    cache_hits: int
    cache_misses: int
    cache_evictions: int
    cache_size: int                # Current number of cached entries
    
    # AI
    ai_calls_total: int
    ai_calls_failed: int
    
    def snapshot(self) -> dict     # Return all metrics as a JSON-serializable dict

# Module-level singleton:
metrics = Metrics()
```

**Expanded `/health` response**:

```json
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "engines": {
    "duckduckgo": {
      "state": "closed",
      "searches": 150,
      "errors": 2,
      "last_success": "2026-04-06T10:30:00Z",
      "last_failure": "2026-04-06T09:15:00Z"
    },
    "bing": {
      "state": "open",
      "searches": 148,
      "errors": 12,
      "last_success": "2026-04-06T10:25:00Z",
      "last_failure": "2026-04-06T10:29:00Z"
    }
  },
  "cache": {
    "size": 45,
    "max_size": 100,
    "hits": 200,
    "misses": 100,
    "evictions": 5,
    "hit_rate": 0.667
  },
  "ai": {
    "copilot_available": true,
    "ollama_available": false,
    "calls_total": 50,
    "calls_failed": 1
  },
  "config": {
    "transport": "sse",
    "engines": ["duckduckgo", "bing"],
    "max_results": 10,
    "cache_ttl_seconds": 300
  }
}
```

**New `/readiness` response**:

```json
{
  "ready": true,
  "checks": {
    "at_least_one_engine_healthy": true,
    "cache_initialized": true
  }
}
```

Returns HTTP 200 if `ready: true`, HTTP 503 if `ready: false`.

#### Implementation Details

**Metrics tracking**:
- Use simple integer counters (no need for Prometheus or complex libraries)
- Thread safety: asyncio is single-threaded, so plain `int +=` is safe
- Timestamps stored as `time.time()` (wall clock, for human-readable output)
- Uptime computed as `time.monotonic() - start_time` (monotonic, not wall clock)

**Integration points**:
- `search.py`: increment `search_total` at start of `execute_web_search()`, `search_errors` on exception, `searches_by_engine[name]` in `_safe_search()` on success, `errors_by_engine[name]` on failure
- `cache.py`: increment `cache_hits` in `cache_get()` on hit, `cache_misses` on miss, `cache_evictions` in `cache_set()` when evicting
- `summarize.py`: increment `ai_calls_total` and `ai_calls_failed` around `_chat_with_ai()`

**Circuit breaker integration**: If E-06 is implemented, the per-engine `"state"` field in the health response comes from `CircuitBreaker.status()`. If E-06 is not implemented, the `"state"` field is omitted.

**Readiness logic**:
- `at_least_one_engine_healthy`: at least one configured engine has `state != "open"` (or if no circuit breaker, at least one engine had a success in the last 5 minutes)
- `cache_initialized`: always true after startup (the in-memory cache is always ready)

#### Dependencies

No new dependencies. Uses `time`, `dataclasses` from stdlib.

#### Acceptance Criteria

1. `GET /health` returns JSON with all documented fields
2. `GET /readiness` returns HTTP 200 when at least one engine is working
3. `GET /readiness` returns HTTP 503 when all engines are in OPEN circuit state (if E-06 is implemented) or all engines have failed in the last 5 minutes
4. Cache hit rate is correctly computed as `hits / (hits + misses)` (handle division by zero)
5. Metrics persist across searches within the server lifetime (not reset per request)
6. Timestamps are ISO 8601 formatted strings in the response

---

### E-08 — Webhook Notification on Degradation

#### Summary

Send HTTP webhook notifications when EvoScry detects operational degradation: a circuit breaker opening, sustained low cache hit rate, or total engine failure. Supports generic HTTP POST, Slack incoming webhooks, and ntfy.sh. Notifications are fire-and-forget and rate-limited to prevent alert storms.

#### Motivation

EvoScry is designed for production deployment via systemd. Operators need to know when search quality degrades, but adding a full monitoring stack (Prometheus + Alertmanager) is heavy for what is typically a single-instance service. A lightweight webhook provides immediate notification through channels operators already use (Slack, ntfy.sh, email via webhook) with minimal configuration.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/alerts.py` | **Create** — webhook notification module |
| `src/evoscry/config.py` | **Modify** — add alert config fields |
| `src/evoscry/circuit_breaker.py` | **Modify** (if E-06 implemented) — fire alert on circuit OPEN transition |
| `src/evoscry/search.py` | **Modify** — fire alert when all engines fail in a single search |

#### New Configuration

| Env Var | Type | Default | Description |
|---------|------|---------|-------------|
| `EVOSCRY_ALERT_WEBHOOK_URL` | str | None | HTTP endpoint to POST alert payloads; disabled if unset |
| `EVOSCRY_ALERT_CACHE_HIT_THRESHOLD` | float | 0.3 | Fire alert when cache hit rate drops below this value (0.0–1.0) |

#### Interface / API Changes

**New functions** in `src/evoscry/alerts.py`:

```
async def fire_alert(
    event_type: str,
    message: str,
    details: dict | None = None
) -> None
    # Send alert to configured webhook; no-op if webhook not configured
    # Rate-limited: at most once per event_type per 5 minutes

def should_alert(event_type: str) -> bool
    # Check rate limit for a given event type
```

**Event types** (string constants):

```
ALERT_CIRCUIT_OPEN = "circuit_breaker_open"
ALERT_ALL_ENGINES_FAILED = "all_engines_failed"
ALERT_LOW_CACHE_HIT_RATE = "low_cache_hit_rate"
ALERT_AI_UNAVAILABLE = "ai_unavailable"
```

#### Implementation Details

**Webhook payload** (JSON):

```json
{
  "event": "circuit_breaker_open",
  "service": "evoscry",
  "timestamp": "2026-04-06T10:30:00Z",
  "message": "Circuit breaker opened for engine 'bing' after 5 consecutive failures",
  "details": {
    "engine": "bing",
    "failure_count": 5,
    "last_error": "HTTP 429 Too Many Requests"
  }
}
```

**Slack compatibility**: Slack incoming webhooks expect a `"text"` field. The payload includes both the structured fields above and a `"text"` field containing `"{message}"` for Slack rendering.

**ntfy.sh compatibility**: ntfy.sh expects a `"topic"` in the URL path and accepts the title in a `Title` header. When `EVOSCRY_ALERT_WEBHOOK_URL` contains `ntfy.sh` or `ntfy.`, send as:
- `POST {url}` with body = message text
- Header: `Title: EvoScry Alert: {event_type}`
- Header: `Priority: high`
- Header: `Tags: warning`

**Detection logic**:
- Auto-detect Slack URL (contains `hooks.slack.com`)
- Auto-detect ntfy URL (contains `ntfy.sh` or `ntfy.`)
- Default: generic JSON POST

**Rate limiting**:

```python
_last_alert: dict[str, float] = {}
ALERT_COOLDOWN = 300  # 5 minutes

def should_alert(event_type: str) -> bool:
    now = time.monotonic()
    last = _last_alert.get(event_type, 0)
    if now - last >= ALERT_COOLDOWN:
        _last_alert[event_type] = now
        return True
    return False
```

**Fire-and-forget**: Alerts are dispatched via `asyncio.create_task()` so they do not delay search responses. Webhook failures are logged at WARNING level but never propagate to the caller.

**Timeout**: Webhook POST has a 5-second timeout. If the webhook endpoint is slow or down, the alert is dropped silently (logged only).

**Integration points**:
- Circuit breaker: call `fire_alert(ALERT_CIRCUIT_OPEN, ...)` when state transitions from CLOSED/HALF_OPEN → OPEN
- Search: call `fire_alert(ALERT_ALL_ENGINES_FAILED, ...)` when `execute_web_search()` would raise `RuntimeError` for total failure
- Metrics (if E-07 implemented): periodically check cache hit rate against threshold; fire alert if below

#### Dependencies

No new dependencies. Uses existing `httpx` for HTTP POST.

#### Acceptance Criteria

1. When `EVOSCRY_ALERT_WEBHOOK_URL` is unset, `fire_alert()` is a no-op (no errors)
2. When configured, circuit breaker OPEN event sends JSON POST to webhook URL within 5 seconds
3. Duplicate alerts for the same event type within 5 minutes are suppressed
4. Slack webhook URL is auto-detected and payload includes `"text"` field
5. ntfy.sh URL is auto-detected and uses plain-text body with appropriate headers
6. Webhook POST failure does not block or crash the search pipeline

---

## MCP-Native Features

---

### E-09 — MCP Resources for Curated Sources

#### Summary

Register three MCP resources that expose EvoScry's internal configuration and reference data to connected agents. This allows agents to query EvoScry's capabilities, understand which engines are active, and inspect the domain authority rankings that influence result scoring — all through the standard MCP resource protocol.

#### Motivation

MCP resources provide a read-only data channel that agents can access without invoking tools. Currently, an agent using EvoScry has no way to discover which engines are configured, what domain authority tiers exist, or what configuration is active. Exposing this information as resources enables smarter agent behavior — for example, an agent could check that a specific engine is available before recommending it, or understand why certain domains rank higher.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/mcp_server.py` | **Modify** — register three MCP resources using `@mcp.resource()` decorators |
| `src/evoscry/normalize/rank.py` | **No change** — read `DOMAIN_AUTHORITY` and `DOMAIN_PATTERNS` from existing module-level constants |
| `src/evoscry/config.py` | **No change** — read from `load_config()` |

#### New Configuration

None.

#### Interface / API Changes

**Three new MCP resources**:

**Resource 1**: `evoscry://search-engines`

```json
{
  "engines": [
    {
      "name": "duckduckgo",
      "enabled": true,
      "endpoint": "https://html.duckduckgo.com/html/",
      "method": "POST",
      "date_filtering": true,
      "notes": "Most reliable; no bot detection; privacy-focused"
    },
    {
      "name": "bing",
      "enabled": true,
      "endpoint": "https://www.bing.com/search",
      "method": "GET",
      "date_filtering": true,
      "notes": "Mobile UA bypass for Turnstile CAPTCHA; good for Microsoft docs"
    },
    {
      "name": "google",
      "enabled": false,
      "endpoint": "https://www.google.com/search",
      "method": "GET",
      "date_filtering": true,
      "notes": "DEPRECATED: requires JavaScript rendering; returns empty without Playwright"
    }
  ]
}
```

**Resource 2**: `evoscry://domain-authorities`

```json
{
  "explicit_domains": {
    "github.com": 0.95,
    "stackoverflow.com": 0.95,
    "developer.mozilla.org": 0.95,
    "docs.python.org": 0.90,
    "...": "..."
  },
  "pattern_rules": [
    {"pattern": "\\.gov$", "score": 0.90},
    {"pattern": "\\.edu$", "score": 0.85},
    {"pattern": "\\.org$", "score": 0.70},
    {"pattern": "^docs\\.", "score": 0.80},
    {"pattern": "^wiki\\.", "score": 0.70}
  ],
  "default_score": 0.50,
  "weight_in_ranking": 0.20
}
```

**Resource 3**: `evoscry://config`

```json
{
  "transport": "sse",
  "host": "0.0.0.0",
  "port": 3000,
  "search_engines": ["duckduckgo", "bing"],
  "max_results": 10,
  "request_delay_ms": 1000,
  "user_agent": "rotate",
  "cache_ttl_seconds": 300,
  "log_level": "info",
  "ai_provider": "copilot",
  "copilot_configured": true,
  "ollama_configured": false,
  "proxy_configured": false
}
```

Sensitive fields (`copilot_token`, `copilot_refresh_token`, `proxy_url`) are **never** included. Only boolean flags indicating whether they are configured.

#### Implementation Details

**MCP resource registration** using the `mcp` library's resource API:

```python
@mcp.resource("evoscry://search-engines")
async def resource_search_engines() -> str:
    config = load_config()
    engines_info = []
    for engine_def in ALL_ENGINES:  # Static list of all known engines
        engines_info.append({
            "name": engine_def["name"],
            "enabled": engine_def["name"] in config.search_engines,
            "endpoint": engine_def["endpoint"],
            "method": engine_def["method"],
            "date_filtering": engine_def["date_filtering"],
            "notes": engine_def["notes"],
        })
    return json.dumps({"engines": engines_info}, indent=2)
```

**Static engine metadata** (defined as a module-level constant in `mcp_server.py` or a separate `engines_meta.py`):

```python
ALL_ENGINES = [
    {
        "name": "duckduckgo",
        "endpoint": "https://html.duckduckgo.com/html/",
        "method": "POST",
        "date_filtering": True,
        "notes": "Most reliable; no bot detection; privacy-focused",
    },
    # ... bing, google, brave (if E-01 implemented)
]
```

**Domain authority resource**: reads directly from `DOMAIN_AUTHORITY` dict and `DOMAIN_PATTERNS` list defined as module-level constants in `rank.py`. No transformation needed — just serialize to JSON.

**Config resource**: Calls `load_config()`, serializes all non-sensitive fields. For sensitive fields, reports only whether they are configured (not `None`/empty).

#### Dependencies

No new dependencies. Uses `json` from stdlib and existing `mcp` library resource registration.

#### Acceptance Criteria

1. An MCP client can list available resources and see all three `evoscry://` URIs
2. Reading `evoscry://search-engines` returns accurate engine data matching current config
3. Reading `evoscry://domain-authorities` returns the full `DOMAIN_AUTHORITY` dict from `rank.py`
4. Reading `evoscry://config` never includes token values, proxy URLs, or other secrets
5. Resources are available on all transport modes (STDIO, SSE, streamable-http)

---

### E-10 — `site_search` Tool

#### Summary

Add a new MCP tool that restricts search results to a specific domain by prepending `site:` to the query. This is a thin semantic wrapper around `execute_web_search()` that makes domain-scoped searching a first-class operation for AI agents.

#### Motivation

Agents frequently want to search within a specific domain: `site:docs.python.org asyncio`, `site:github.com fastapi middleware`, etc. Currently, agents must manually construct the `site:` prefix in the `query` parameter of `web_search`. A dedicated tool makes this intent explicit, enables better parameter validation, and improves discoverability for agents browsing available tools.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/mcp_server.py` | **Modify** — register new `site_search` MCP tool |
| `src/evoscry/search.py` | **Modify** — add `execute_site_search()` function |

#### New Configuration

None.

#### Interface / API Changes

**New MCP tool** `site_search`:

```
Parameters:
  query: str           — Search query text [required]
  site: str            — Domain to restrict search to (e.g., "docs.python.org") [required]
  engines: list[str]   — Engines to use (default: config engines)
  max_results: int     — Max results (default: config value)
  language: str        — ISO 639-1 code (default: "en")
  date_range: str      — "day" | "week" | "month" | "year" | null

Returns: JSON string with same structure as web_search:
  {"query", "engines", "total_results", "results", "site"}
```

**New function** in `search.py`:

```
async def execute_site_search(
    query: str,
    site: str,
    engines: list[str] | None = None,
    max_results: int | None = None,
    language: str = "en",
    date_range: str | None = None,
) -> dict
```

#### Implementation Details

**Site parameter validation**:

```python
import re

DOMAIN_PATTERN = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$')

def _validate_site(site: str) -> str:
    site = site.strip().lower()
    # Strip protocol if user includes it
    if site.startswith("http://"):
        site = site[7:]
    if site.startswith("https://"):
        site = site[8:]
    # Strip trailing slash
    site = site.rstrip("/")
    # Strip path components (keep domain only)
    site = site.split("/")[0]
    
    if not DOMAIN_PATTERN.match(site):
        raise ValueError(f"Invalid site domain: '{site}'")
    return site
```

**Query construction**:

```python
async def execute_site_search(query, site, engines, max_results, language, date_range):
    validated_site = _validate_site(site)
    site_query = f"site:{validated_site} {query}"
    
    result = await execute_web_search(
        query=site_query,
        engines=engines,
        max_results=max_results,
        language=language,
        date_range=date_range,
        summarize=False,
    )
    
    # Add site field to response
    result["site"] = validated_site
    # Replace the modified query with the original for cleaner output
    result["original_query"] = query
    
    return result
```

**Edge cases**:
- If `query` already contains `site:`, strip it and log a warning (use provided `site` parameter instead)
- If `site` includes a path (e.g., `docs.python.org/3/library`), use only the domain portion
- Empty `site` after validation → raise `ValueError`

#### Dependencies

No new dependencies.

#### Acceptance Criteria

1. `site_search("asyncio", site="docs.python.org")` returns results exclusively from `docs.python.org`
2. `site_search("asyncio", site="https://docs.python.org/")` handles URL-format site input correctly (strips protocol and trailing slash)
3. `site_search("asyncio", site="not a domain!!!")` raises `ValueError`
4. Results include `"site": "docs.python.org"` in the response dict
5. The `site_search` tool appears in MCP tool listing with documented parameters
6. Caching works correctly (site-scoped queries produce different cache keys than non-site queries)

---

### E-11 — `find_similar` Tool

#### Summary

Add a new MCP tool that, given a URL, extracts the page content, generates descriptive keywords, and searches for similar pages. This enables "find me more like this" workflows where an agent has found one useful resource and wants to discover related content.

#### Motivation

A common agent workflow is: find one good result → want more like it. Currently, the agent must manually read the page, determine keywords, and construct a follow-up search. The `find_similar` tool automates this entire pipeline, producing relevant results in a single tool call.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/normalize/keywords.py` | **Create** — keyword extraction module |
| `src/evoscry/normalize/__init__.py` | **Modify** — export `extract_keywords` |
| `src/evoscry/mcp_server.py` | **Modify** — register new `find_similar` MCP tool |
| `src/evoscry/search.py` | **Modify** — add `execute_find_similar()` function |

#### New Configuration

None.

#### Interface / API Changes

**New MCP tool** `find_similar`:

```
Parameters:
  url: str             — URL to find similar content for [required]
  max_results: int     — Max similar results to return (default: 10)
  engines: list[str]   — Engines to use (default: config engines)

Returns: JSON string with:
  {
    "source_url": str,
    "source_title": str,
    "generated_query": str,
    "keywords": list[str],
    "total_results": int,
    "results": list[SearchResult]
  }
```

**New function** in `src/evoscry/normalize/keywords.py`:

```
def extract_keywords(
    content: str,
    title: str = "",
    max_keywords: int = 8
) -> list[str]
```

- Input: plain text content (potentially truncated to first 5000 chars for performance) and page title
- Output: list of up to `max_keywords` keyword strings, ordered by relevance

**New function** in `search.py`:

```
async def execute_find_similar(
    url: str,
    max_results: int = 10,
    engines: list[str] | None = None,
) -> dict
```

#### Implementation Details

**Keyword extraction algorithm** (`extract_keywords()`):

```
1. Combine title (weighted 3×) and content (first 5000 chars):
     text = (title + " ") * 3 + content[:5000]

2. Tokenize:
     tokens = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())

3. Filter stopwords:
     STOPWORDS = {"the", "and", "for", "are", "but", "not", "you", "all",
                  "can", "had", "her", "was", "one", "our", "out", "has",
                  "have", "been", "from", "this", "that", "with", "they",
                  "will", "each", "make", "like", "been", "more", "some",
                  "than", "very", "when", "what", "your", "how", "about",
                  "which", "their", "there", "would", "could", "should",
                  "into", "also", "just", "other", "these", "then", "were"}
     tokens = [t for t in tokens if t not in STOPWORDS]

4. Position-weighted frequency counting:
     For each token at index i:
       weight = 1.0 + (1.0 - i / len(tokens))  # Earlier tokens score higher
       frequency[token] += weight

5. Sort by weighted frequency, descending

6. Deduplicate stems (simple: if a keyword is a prefix of a higher-ranked keyword,
   skip it — e.g., "python" and "pythonic" → keep "python" if ranked higher)

7. Return top max_keywords
```

**Find-similar pipeline** (`execute_find_similar()`):

```python
async def execute_find_similar(url, max_results, engines):
    # 1. Extract content from source URL
    extracted = await extract_content([url], fmt="text")
    if extracted[0].get("error"):
        raise ValueError(f"Could not extract content from {url}: {extracted[0]['error']}")
    
    content = extracted[0]["content"]
    title = extracted[0].get("title", "")
    
    # 2. Extract keywords
    keywords = extract_keywords(content, title, max_keywords=8)
    if not keywords:
        raise ValueError(f"Could not extract keywords from {url}")
    
    # 3. Build search query from keywords
    generated_query = " ".join(keywords)
    
    # 4. Search
    search_result = await execute_web_search(
        query=generated_query,
        engines=engines,
        max_results=max_results + 1,  # +1 to account for filtering source URL
    )
    
    # 5. Filter out the source URL
    from .normalize.dedup import normalize_url
    source_normalized = normalize_url(url)
    search_result["results"] = [
        r for r in search_result["results"]
        if normalize_url(r["url"]) != source_normalized
    ][:max_results]
    
    # 6. Build response
    return {
        "source_url": url,
        "source_title": title,
        "generated_query": generated_query,
        "keywords": keywords,
        "total_results": len(search_result["results"]),
        "results": search_result["results"],
    }
```

**Caching**: The generated search query is cached normally by `execute_web_search()`. The content extraction is not cached (it goes through `extract_content()` which does not use the search cache). This is acceptable since `find_similar` is typically a one-off operation.

#### Dependencies

No new Python dependencies. Uses `re`, `collections.Counter` from stdlib.

#### Acceptance Criteria

1. `find_similar("https://docs.python.org/3/library/asyncio.html")` returns results about Python asyncio from various sources
2. The source URL is excluded from the result list
3. `extract_keywords()` returns 5–8 meaningful keywords for a typical web page
4. Empty or inaccessible URLs produce a clear `ValueError`
5. Keywords do not include common stopwords
6. The response includes `generated_query` and `keywords` for transparency

---

## Content & Extraction

---

### E-12 — PDF and GitHub Content Extraction

#### Summary

Extend the `extract_content()` function in `extract.py` to handle PDF documents and GitHub repository URLs. PDFs are extracted using `pymupdf` (optional dependency). GitHub blob URLs are automatically transformed to raw content URLs for direct text fetching. GitHub tree URLs return directory listings.

#### Motivation

AI agents frequently encounter PDF links (research papers, documentation, spec sheets) and GitHub URLs (source files, READMEs) in search results. Currently, `extract_content()` attempts to parse these as HTML, producing garbage output for PDFs and suboptimal output for GitHub pages (which are wrapped in GitHub's UI chrome). Handling these content types natively eliminates a common failure mode.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/extract.py` | **Modify** — add PDF detection and extraction; add GitHub URL transformation |
| `pyproject.toml` | **Modify** — add `pymupdf` to `[project.optional-dependencies.pdf]` |

#### New Configuration

None. PDF support is automatically enabled when `pymupdf` is installed.

#### Interface / API Changes

No changes to the `extract_content()` function signature or MCP tool schema. The changes are internal to the extraction pipeline. Two new response behaviors:

1. **PDF URLs**: `content` field contains extracted plain text (regardless of `format` parameter — PDFs don't have HTML structure to convert to Markdown). New response field: `"content_type": "pdf"`.

2. **GitHub blob URLs**: `content` field contains the raw file content. New response field: `"content_type": "github_file"`.

3. **GitHub tree URLs**: `content` field contains a formatted directory listing. New response field: `"content_type": "github_directory"`.

The `content_type` field is **added to all responses** (default `"html"`) as a non-breaking addition.

#### Implementation Details

**Content type detection** (added at the top of the per-URL processing loop in `extract_content()`):

```python
import re
from urllib.parse import urlparse

GITHUB_BLOB_RE = re.compile(
    r'^https?://github\.com/([^/]+)/([^/]+)/blob/(.+)$'
)
GITHUB_TREE_RE = re.compile(
    r'^https?://github\.com/([^/]+)/([^/]+)/tree/(.+)$'
)

def _detect_content_type(url: str, response_headers: dict | None = None) -> str:
    parsed = urlparse(url)
    path_lower = parsed.path.lower()
    
    # PDF detection by URL extension
    if path_lower.endswith(".pdf"):
        return "pdf"
    
    # PDF detection by Content-Type header
    if response_headers:
        ct = response_headers.get("content-type", "")
        if "application/pdf" in ct:
            return "pdf"
    
    # GitHub blob (file view)
    if GITHUB_BLOB_RE.match(url):
        return "github_file"
    
    # GitHub tree (directory view)
    if GITHUB_TREE_RE.match(url):
        return "github_directory"
    
    # Raw GitHub content
    if parsed.hostname == "raw.githubusercontent.com":
        return "github_raw"
    
    return "html"
```

**PDF extraction**:

```python
MAX_PDF_BYTES = 10 * 1024 * 1024  # 10MB

async def _extract_pdf(url: str) -> dict:
    try:
        import pymupdf
    except ImportError:
        return {
            "url": url,
            "title": "",
            "content": "PDF extraction requires pymupdf. Install with: pip install pymupdf",
            "byte_length": 0,
            "content_type": "pdf",
            "error": "pymupdf not installed",
        }
    
    # Fetch PDF bytes
    async with httpx.AsyncClient(proxy=config.proxy_url, timeout=30) as client:
        response = await client.get(url)
        response.raise_for_status()
    
    if len(response.content) > MAX_PDF_BYTES:
        return {"url": url, "error": f"PDF exceeds {MAX_PDF_BYTES} byte limit", ...}
    
    # Extract text with pymupdf
    doc = pymupdf.open(stream=response.content, filetype="pdf")
    title = doc.metadata.get("title", "") or ""
    
    pages_text = []
    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        if text.strip():
            pages_text.append(f"--- Page {page_num + 1} ---\n{text.strip()}")
    
    content = "\n\n".join(pages_text)
    
    # Truncate to MAX_CONTENT_BYTES (50KB)
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > MAX_CONTENT_BYTES:
        content = content_bytes[:MAX_CONTENT_BYTES].decode("utf-8", errors="ignore")
        content += "\n\n[Content truncated at 50KB]"
    
    doc.close()
    
    return {
        "url": url,
        "title": title,
        "content": content,
        "byte_length": len(content.encode("utf-8")),
        "content_type": "pdf",
        "error": None,
    }
```

**GitHub blob URL transformation**:

```python
async def _extract_github_file(url: str) -> dict:
    match = GITHUB_BLOB_RE.match(url)
    owner, repo, path = match.group(1), match.group(2), match.group(3)
    
    # Transform to raw URL
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{path}"
    
    # Fetch raw content
    response = await fetch_with_config(raw_url)
    content = response.text
    
    # Determine title from filename
    filename = path.split("/")[-1]
    
    # Truncate
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > MAX_CONTENT_BYTES:
        content = content_bytes[:MAX_CONTENT_BYTES].decode("utf-8", errors="ignore")
        content += "\n\n[Content truncated at 50KB]"
    
    return {
        "url": url,
        "title": filename,
        "content": content,
        "byte_length": len(content.encode("utf-8")),
        "content_type": "github_file",
        "error": None,
    }
```

**GitHub tree URL directory listing**:

```python
async def _extract_github_directory(url: str) -> dict:
    match = GITHUB_TREE_RE.match(url)
    owner, repo, path = match.group(1), match.group(2), match.group(3)
    
    # Split path into ref and directory path
    # Convention: first path component is the ref (branch/tag)
    parts = path.split("/", 1)
    ref = parts[0]
    dir_path = parts[1] if len(parts) > 1 else ""
    
    # Use GitHub API (no auth required for public repos)
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{dir_path}?ref={ref}"
    
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(api_url, headers={"Accept": "application/vnd.github.v3+json"})
        response.raise_for_status()
    
    entries = response.json()
    listing = []
    for entry in entries:
        type_indicator = "/" if entry["type"] == "dir" else ""
        size = f" ({entry.get('size', 0)} bytes)" if entry["type"] == "file" else ""
        listing.append(f"  {entry['name']}{type_indicator}{size}")
    
    content = f"Directory: {owner}/{repo}/{dir_path}\n\n" + "\n".join(listing)
    
    return {
        "url": url,
        "title": f"{owner}/{repo}/{dir_path or '/'}",
        "content": content,
        "byte_length": len(content.encode("utf-8")),
        "content_type": "github_directory",
        "error": None,
    }
```

**Integration into `extract_content()`**:

```python
# At the top of the per-URL loop, before HTML fetching:
content_type = _detect_content_type(url)

if content_type == "pdf":
    result = await _extract_pdf(url)
elif content_type == "github_file" or content_type == "github_raw":
    result = await _extract_github_file(url)
elif content_type == "github_directory":
    result = await _extract_github_directory(url)
else:
    # Existing HTML extraction pipeline
    ...
```

#### Dependencies

New optional dependency:

```toml
[project.optional-dependencies]
pdf = ["pymupdf>=1.24"]
```

#### Acceptance Criteria

1. `extract_content(["https://arxiv.org/pdf/2301.12345.pdf"])` returns extracted text with page markers (when `pymupdf` installed)
2. `extract_content(["https://arxiv.org/pdf/2301.12345.pdf"])` returns a helpful error message when `pymupdf` is not installed
3. `extract_content(["https://github.com/user/repo/blob/main/README.md"])` returns raw file content, not GitHub's HTML chrome
4. `extract_content(["https://github.com/user/repo/tree/main/src"])` returns a directory listing
5. PDFs exceeding 10MB are rejected with a clear error
6. All responses include the `content_type` field
7. Existing HTML extraction is unaffected (regression test)

---

### E-13 — Structured Data Extraction

#### Summary

Extend `extract_content()` to optionally extract structured metadata from web pages: JSON-LD, OpenGraph tags, and Twitter Card tags. This gives AI agents access to machine-readable facts (author, publish date, ratings, article type) without parsing prose.

#### Motivation

Many web pages embed structured data that is invisible in the rendered text but highly useful for AI agents: publication dates, author names, article categories, product ratings, recipe ingredients, event dates. Currently, `extract_content()` strips all `<script>` and `<meta>` tags during its noise removal phase. Preserving and extracting structured data before noise removal provides a richer signal to agents.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/extract.py` | **Modify** — add metadata extraction before noise removal; add `include_metadata` parameter |
| `src/evoscry/mcp_server.py` | **Modify** — add `include_metadata: bool = False` parameter to `extract_content` tool schema |

#### New Configuration

None.

#### Interface / API Changes

**Modified `extract_content` MCP tool** — new parameter:

```
include_metadata: bool = False  — Extract JSON-LD, OpenGraph, and Twitter Card metadata
```

**Modified `extract_content()` function** — new parameter:

```
async def extract_content(
    urls: list[str],
    fmt: str = "markdown",
    include_metadata: bool = False,   # NEW
) -> list[dict]
```

**New response field** (present only when `include_metadata=True`):

```json
{
  "url": "https://example.com/article",
  "title": "Example Article",
  "content": "...",
  "byte_length": 1234,
  "error": null,
  "metadata": {
    "json_ld": [
      {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": "Example Article",
        "author": {"@type": "Person", "name": "Jane Doe"},
        "datePublished": "2026-03-15"
      }
    ],
    "opengraph": {
      "og:title": "Example Article",
      "og:description": "An example article about...",
      "og:type": "article",
      "og:image": "https://example.com/image.jpg",
      "og:url": "https://example.com/article"
    },
    "twitter_card": {
      "twitter:card": "summary_large_image",
      "twitter:title": "Example Article",
      "twitter:description": "An example article about..."
    }
  }
}
```

#### Implementation Details

**Metadata extraction** (executed BEFORE the noise removal step in the per-URL pipeline):

```python
def _extract_metadata(soup: BeautifulSoup) -> dict:
    metadata = {
        "json_ld": [],
        "opengraph": {},
        "twitter_card": {},
    }
    
    # JSON-LD: <script type="application/ld+json">
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                metadata["json_ld"].extend(data)
            else:
                metadata["json_ld"].append(data)
        except (json.JSONDecodeError, TypeError):
            continue  # Skip malformed JSON-LD
    
    # OpenGraph: <meta property="og:...">
    for meta in soup.find_all("meta", property=re.compile(r'^og:')):
        prop = meta.get("property", "")
        content = meta.get("content", "")
        if prop and content:
            metadata["opengraph"][prop] = content
    
    # Twitter Card: <meta name="twitter:...">
    for meta in soup.find_all("meta", attrs={"name": re.compile(r'^twitter:')}):
        name = meta.get("name", "")
        content = meta.get("content", "")
        if name and content:
            metadata["twitter_card"][name] = content
    
    return metadata
```

**Integration into `extract_content()` per-URL pipeline**:

```python
# After parsing HTML with BeautifulSoup, BEFORE noise removal:
if include_metadata:
    metadata = _extract_metadata(soup)

# Continue with existing noise removal (removing <script>, <style>, etc.)
# ...

# In the result dict:
result = {
    "url": url,
    "title": title,
    "content": content,
    "byte_length": byte_length,
    "error": None,
}
if include_metadata:
    result["metadata"] = metadata
```

**JSON-LD sanitization**: JSON-LD blocks can contain arbitrary JSON. To prevent excessively large metadata:
- Truncate individual JSON-LD objects to 10KB serialized
- Maximum 5 JSON-LD blocks per page
- Strip any `<script>` tags that may be nested within JSON-LD content (defense against injection)

**OpenGraph and Twitter Card limits**:
- Maximum 20 properties each (prevents pathological pages)
- Truncate individual values to 1000 characters

#### Dependencies

No new dependencies. Uses `json`, `re` from stdlib and existing `beautifulsoup4`.

#### Acceptance Criteria

1. `extract_content(["https://example.com"], include_metadata=True)` returns `"metadata"` field with JSON-LD, OpenGraph, and Twitter Card data (for pages that have them)
2. `extract_content(["https://example.com"], include_metadata=False)` does NOT include `"metadata"` field (backward-compatible)
3. Malformed JSON-LD is silently skipped (no crash)
4. Pages with no structured data return empty arrays/dicts in metadata
5. Metadata extraction does not affect the `content` field (same output with or without `include_metadata`)
6. The `include_metadata` parameter appears in the MCP tool schema

---

### E-14 — Screenshot Capture

#### Summary

Add a new MCP tool that captures a screenshot of a web page as a base64-encoded PNG image. This requires Playwright (shared optional dependency with E-05) and is only registered when Playwright is available.

#### Motivation

Some web pages are primarily visual: dashboards, charts, design systems, image galleries. Text extraction produces poor results for these pages. A screenshot gives AI agents with vision capabilities a faithful representation of the page. This is also useful for visual regression checks, accessibility audits, and verifying that a page renders correctly.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/mcp_server.py` | **Modify** — conditionally register `screenshot_url` tool when Playwright is available |
| `src/evoscry/providers/google_playwright.py` | **Modify** (if E-05 implemented) — share browser lifecycle; or create `src/evoscry/browser.py` as shared browser management module |

If E-05 is **not** implemented, create `src/evoscry/browser.py` with standalone browser lifecycle management.

#### New Configuration

| Env Var | Type | Default | Description |
|---------|------|---------|-------------|
| `EVOSCRY_ENABLE_PLAYWRIGHT` | bool | `false` | Shared with E-05; enables browser-based features |

#### Interface / API Changes

**New MCP tool** `screenshot_url`:

```
Parameters:
  url: str             — URL to capture [required]
  width: int           — Viewport width in pixels (default: 1280, min: 320, max: 3840)
  height: int          — Viewport height in pixels (default: 720, min: 240, max: 2160)
  full_page: bool      — Capture full scrollable page, not just viewport (default: false)

Returns: JSON string with:
  {
    "url": str,
    "screenshot_base64": str,    # Base64-encoded PNG
    "width": int,                # Actual viewport width used
    "height": int,               # Actual viewport height used
    "byte_length": int,          # Size of PNG in bytes (before base64 encoding)
    "full_page": bool,
    "error": str | null
  }
```

**Conditional registration**: The tool is only registered if:
1. `EVOSCRY_ENABLE_PLAYWRIGHT=true`
2. `playwright` is importable

```python
# In mcp_server.py startup:
if config.enable_playwright:
    try:
        import playwright
        # Register screenshot_url tool
    except ImportError:
        logger.info("Playwright not installed; screenshot_url tool not available")
```

#### Implementation Details

**Browser management** (shared with E-05 if implemented):

```python
# src/evoscry/browser.py (or reuse google_playwright.py)
_browser: Browser | None = None
_browser_lock = asyncio.Lock()

async def get_browser() -> Browser:
    global _browser
    async with _browser_lock:
        if _browser is None:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            _browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
        return _browser
```

**Screenshot capture**:

```python
MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024  # 5MB

async def capture_screenshot(
    url: str,
    width: int = 1280,
    height: int = 720,
    full_page: bool = False,
) -> dict:
    # Validate dimensions
    width = max(320, min(width, 3840))
    height = max(240, min(height, 2160))
    
    browser = await get_browser()
    context = await browser.new_context(
        viewport={"width": width, "height": height},
        user_agent=random.choice(USER_AGENTS),  # From http_client
    )
    page = await context.new_page()
    
    try:
        await page.goto(url, wait_until="networkidle", timeout=15000)
        
        # Wait a moment for any animations/lazy-loading
        await page.wait_for_timeout(500)
        
        screenshot_bytes = await page.screenshot(
            type="png",
            full_page=full_page,
        )
        
        if len(screenshot_bytes) > MAX_SCREENSHOT_BYTES:
            # Try with lower quality JPEG instead
            screenshot_bytes = await page.screenshot(
                type="jpeg",
                quality=70,
                full_page=full_page,
            )
        
        if len(screenshot_bytes) > MAX_SCREENSHOT_BYTES:
            return {
                "url": url,
                "error": f"Screenshot exceeds {MAX_SCREENSHOT_BYTES} byte limit even as compressed JPEG",
                ...
            }
        
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("ascii")
        
        return {
            "url": url,
            "screenshot_base64": screenshot_b64,
            "width": width,
            "height": height,
            "byte_length": len(screenshot_bytes),
            "full_page": full_page,
            "error": None,
        }
    
    except Exception as e:
        return {
            "url": url,
            "screenshot_base64": "",
            "width": width,
            "height": height,
            "byte_length": 0,
            "full_page": full_page,
            "error": str(e),
        }
    
    finally:
        await page.close()
        await context.close()
```

**URL validation**: Only `http://` and `https://` URLs are accepted. Reject `file://`, `javascript:`, `data:`, etc.

**Timeout**: 15 seconds for page load + 500ms settling time. Total budget: ~16 seconds per screenshot.

**Cookie/state isolation**: Each screenshot uses a fresh browser context, so no cookies or session state leak between captures.

#### Dependencies

Shared optional dependency with E-05:

```toml
[project.optional-dependencies]
playwright = ["playwright>=1.40"]
```

Also requires `base64` from stdlib.

#### Acceptance Criteria

1. With Playwright enabled and installed: `screenshot_url("https://example.com")` returns a valid base64-encoded PNG
2. Without Playwright: the `screenshot_url` tool does not appear in the MCP tool listing
3. Custom viewport dimensions are respected (verifiable by inspecting the decoded image dimensions)
4. `full_page=True` captures content below the fold
5. Screenshots exceeding 5MB fall back to JPEG compression
6. Invalid URLs (e.g., `file:///etc/passwd`) are rejected
7. Screenshot capture does not leak cookies between calls

---

## Privacy & Security

---

### E-15 — Tor Transport Option

#### Summary

Add a Tor operation mode that routes all search traffic through the Tor network via SOCKS5 proxy. When enabled, EvoScry adopts Tor-safe defaults: a single Tor Browser user-agent string, disabled referer headers, circuit isolation per search, and increased timeouts. This provides strong anonymity for sensitive or classified-context query workloads.

#### Motivation

EvoScry already supports SOCKS5 proxies via `EVOSCRY_PROXY_URL`. However, simply pointing at a Tor SOCKS5 port is not sufficient for true anonymity — the user-agent rotation pool, referer headers, and short timeouts leak information or cause Tor-routed requests to fail. A dedicated Tor mode configures all necessary hardening automatically, removing the burden of manual configuration and reducing the risk of misconfiguration.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/tor.py` | **Create** — Tor-specific configuration, UA, and connectivity validation |
| `src/evoscry/config.py` | **Modify** — add `tor_mode` field; when enabled, override proxy, UA, and timeout defaults |
| `src/evoscry/http_client.py` | **Modify** — respect Tor-mode overrides (single UA, no referer, longer timeout) |
| `pyproject.toml` | **Modify** — add `httpx[socks]` to dependencies or optional deps |

#### New Configuration

| Env Var | Type | Default | Description |
|---------|------|---------|-------------|
| `EVOSCRY_TOR_MODE` | bool | `false` | Enable Tor anonymity mode |
| `EVOSCRY_TOR_SOCKS_PORT` | int | 9050 | SOCKS5 port for Tor daemon |
| `EVOSCRY_TOR_SOCKS_HOST` | str | `127.0.0.1` | SOCKS5 host for Tor daemon |

When `EVOSCRY_TOR_MODE=true`, the following config values are **overridden regardless of env vars**:

| Setting | Forced Value | Reason |
|---------|-------------|--------|
| `proxy_url` | `socks5://{host}:{port}` | Route through Tor |
| `user_agent` | Tor Browser UA (see below) | Blend with Tor traffic |
| `request_delay_ms` | `2000` (minimum) | Tor is slower; reduce load on exit nodes |

#### Interface / API Changes

No changes to MCP tool signatures or return types. Tor mode is transparent to agents — they use the same tools, and traffic is automatically routed through Tor.

**New module** `src/evoscry/tor.py`:

```
TOR_USER_AGENT: str
    # Single UA matching Tor Browser fingerprint

async def validate_tor_connection(host: str, port: int) -> bool
    # Test connectivity to Tor SOCKS5 proxy; return True/False

def get_tor_proxy_url(host: str, port: int) -> str
    # Return formatted SOCKS5 URL

def get_circuit_isolation_proxy(host: str, port: int) -> str
    # Return SOCKS5 URL with random auth for circuit isolation
```

#### Implementation Details

**Tor Browser user-agent** (must match the standard Tor Browser fingerprint for anonymity):

```python
TOR_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; rv:128.0) "
    "Gecko/20100101 Firefox/128.0"
)
```

Using any other UA on the Tor network makes the user uniquely identifiable. The Tor Project standardizes on this specific string.

**Circuit isolation**: Tor creates new circuits for different SOCKS5 authentication credentials. By generating a random username for each search, each query goes through a different Tor circuit (different exit node), preventing correlation between searches.

```python
import secrets

def get_circuit_isolation_proxy(host: str, port: int) -> str:
    random_user = secrets.token_hex(8)
    random_pass = secrets.token_hex(8)
    return f"socks5://{random_user}:{random_pass}@{host}:{port}"
```

**Connectivity validation** (called once at startup when Tor mode is enabled):

```python
async def validate_tor_connection(host: str, port: int) -> bool:
    proxy_url = get_tor_proxy_url(host, port)
    try:
        async with httpx.AsyncClient(
            proxy=proxy_url,
            timeout=15,
        ) as client:
            response = await client.get("https://check.torproject.org/api/ip")
            data = response.json()
            if data.get("IsTor"):
                logger.info(f"Tor connection verified. Exit IP: {data.get('IP')}")
                return True
            else:
                logger.error("Connected through proxy but NOT using Tor network")
                return False
    except Exception as e:
        logger.error(f"Tor connectivity check failed: {e}")
        return False
```

**Config integration** in `config.py`:

```python
def load_config() -> Config:
    # ... existing loading logic ...
    
    tor_mode = os.environ.get("EVOSCRY_TOR_MODE", "false").lower() == "true"
    
    if tor_mode:
        tor_host = os.environ.get("EVOSCRY_TOR_SOCKS_HOST", "127.0.0.1")
        tor_port = int(os.environ.get("EVOSCRY_TOR_SOCKS_PORT", "9050"))
        
        # Override settings for Tor safety
        proxy_url = f"socks5://{tor_host}:{tor_port}"
        user_agent = "tor"  # Special value recognized by http_client
        request_delay_ms = max(request_delay_ms, 2000)
        
        logger.info("Tor mode enabled — forcing Tor-safe defaults")
```

**HTTP client integration** in `http_client.py`:

```python
def _get_user_agent(config: Config) -> str:
    if config.user_agent == "tor":
        from .tor import TOR_USER_AGENT
        return TOR_USER_AGENT
    elif config.user_agent == "rotate":
        return _rotate_ua()
    else:
        return config.user_agent

# In fetch_with_config() and post_with_config():
# When tor mode: do NOT set Referer or Origin headers
if config.user_agent != "tor":
    headers["Referer"] = ...
    headers["Origin"] = ...

# When tor mode: use circuit-isolated proxy for each request
if config.user_agent == "tor":
    from .tor import get_circuit_isolation_proxy
    proxy = get_circuit_isolation_proxy(tor_host, tor_port)
else:
    proxy = config.proxy_url
```

**Timeout adjustment**: All HTTP timeouts increased to 30s when Tor mode is enabled (Tor adds 2–10 seconds of latency per request due to multi-hop routing).

#### Dependencies

```toml
[project.optional-dependencies]
tor = ["httpx[socks]>=0.27"]
```

If `httpx[socks]` is not installed and Tor mode is enabled, raise a clear error at startup: `"Tor mode requires httpx[socks]. Install with: pip install 'httpx[socks]'"`.

#### Acceptance Criteria

1. With `EVOSCRY_TOR_MODE=true` and Tor running: searches are routed through Tor (verifiable via Tor check API at startup)
2. User-agent is the standard Tor Browser string (no rotation)
3. No `Referer` or `Origin` headers are sent
4. Each search uses a different Tor circuit (different exit IP for consecutive searches — verifiable via logging exit IPs)
5. Minimum request delay is enforced at 2000ms
6. Startup fails with a clear error if Tor is not reachable
7. Startup fails with a clear error if `httpx[socks]` is not installed
8. Search results are returned successfully (Tor routing works end-to-end with DuckDuckGo and Bing)

---

### E-16 — Query Anonymization Log Mode

#### Summary

Add a logging mode that replaces search query strings with SHA-256 hash prefixes in all log output. This allows operators to retain useful operational logs (timing, error types, engine health) while ensuring that the actual content of searches is not recorded in plaintext. Designed for environments where log files may be audited or shared with third parties.

#### Motivation

EvoScry logs search queries at INFO level for debugging and monitoring. In sensitive environments (government, legal, healthcare), plaintext query logs may violate data handling policies. Simply disabling logging sacrifices all operational visibility. Hash-based anonymization preserves log structure and allows correlation (same hash = same query) without revealing query content.

#### Affected Files

| File | Action |
|------|--------|
| `src/evoscry/config.py` | **Modify** — add `anonymize_logs` field to `Config` |
| `src/evoscry/mcp_server.py` | **Modify** — attach `AnonymizeFilter` to root logger at startup when enabled |
| `src/evoscry/search.py` | **Modify** — use anonymization-aware logging helper for query-containing log messages |

#### New Configuration

| Env Var | Type | Default | Description |
|---------|------|---------|-------------|
| `EVOSCRY_ANONYMIZE_LOGS` | bool | `false` | Replace search queries with hashed identifiers in log output |

#### Interface / API Changes

No changes to MCP tools or function signatures. This is purely an internal logging behavior change.

**New logging filter class** (in `mcp_server.py` or a new `src/evoscry/log_filter.py` if the logic is substantial):

```
class AnonymizeFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool
        # Mutate record.msg and record.args to hash query strings
        # Always return True (do not suppress records)
```

#### Implementation Details

**Hash function**:

```python
import hashlib

def anonymize_query(query: str) -> str:
    h = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"q:{h[:12]}"
    
# Example: "python asyncio tutorial" → "q:a3f8b2c1d4e5"
```

The 12-character hex prefix (48 bits) provides enough uniqueness for log correlation while being compact. Full SHA-256 is unnecessary for this purpose.

**Filter implementation**:

```python
class AnonymizeFilter(logging.Filter):
    def __init__(self, patterns: list[re.Pattern] | None = None):
        super().__init__()
        # Patterns that identify query strings in log messages
        self.patterns = patterns or [
            re.compile(r'query[=:]\s*["\'](.+?)["\']', re.IGNORECASE),
            re.compile(r'searching\s+for\s+["\'](.+?)["\']', re.IGNORECASE),
            re.compile(r'search query:\s*(.+?)(?:\s*$|\s*,)', re.IGNORECASE),
        ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern in self.patterns:
                record.msg = pattern.sub(
                    lambda m: m.group(0).replace(m.group(1), anonymize_query(m.group(1))),
                    record.msg
                )
        
        # Also process args if they contain strings
        if record.args and isinstance(record.args, (tuple, dict)):
            record.args = self._anonymize_args(record.args)
        
        return True  # Never suppress records
    
    def _anonymize_args(self, args):
        if isinstance(args, dict):
            return {
                k: anonymize_query(v) if k in ("query", "q", "search_query") and isinstance(v, str) else v
                for k, v in args.items()
            }
        elif isinstance(args, tuple):
            return tuple(
                anonymize_query(a) if isinstance(a, str) and len(a) > 3 else a
                for a in args
            )
        return args
```

**Structured logging approach** — For more reliable anonymization, modify logging call sites in `search.py` to use structured key-value pairs:

```python
# Before (current):
logger.info(f'Searching for "{query}" on engines: {engines}')

# After (anonymization-aware):
logger.info("Searching for query=%(query)s on engines: %(engines)s",
            {"query": query, "engines": engines})
```

This allows the filter to target the `"query"` key specifically in `record.args`, which is more reliable than regex pattern matching on free-form log messages.

**Attachment at startup** in `mcp_server.py`:

```python
def _configure_logging(config: Config):
    logging.basicConfig(level=getattr(logging, config.log_level.upper()))
    
    if config.anonymize_logs:
        anon_filter = AnonymizeFilter()
        logging.getLogger().addFilter(anon_filter)
        # Also apply to all existing handlers
        for handler in logging.getLogger().handlers:
            handler.addFilter(anon_filter)
        logging.info("Query anonymization enabled in logs")
```

**Cache key safety**: The existing cache in `cache.py` uses SHA-256 hashing for cache keys (via `cache_key()`), so cached query data is already hashed. No change needed. However, verify that debug-level logging in `cache.py` does not print the raw `params` dict (which contains the plaintext query). If it does, those log lines must be routed through the anonymization filter.

**Completeness check**: Search all log statements in `search.py`, `mcp_server.py`, `cache.py`, and provider modules for query string leakage. Any `logger.debug()` or `logger.info()` call that includes the raw query must either use structured logging (dict-based args with `"query"` key) or be explicitly anonymized.

#### Dependencies

No new dependencies. Uses `hashlib`, `re`, `logging` from stdlib.

#### Acceptance Criteria

1. With `EVOSCRY_ANONYMIZE_LOGS=true`: log output for a search contains `q:a3f8b2c1d4e5` instead of the plaintext query
2. With `EVOSCRY_ANONYMIZE_LOGS=false`: log output is unchanged (plaintext queries visible)
3. The same query always produces the same hash prefix (deterministic, correlatable)
4. Different queries produce different hash prefixes (no collisions in practical use)
5. Non-query log messages (errors, timing, engine status) are unaffected
6. Cache debug logs do not leak plaintext queries when anonymization is enabled
7. The filter does not raise exceptions on any log message format (robust to unexpected input)

---

## Cross-Enhancement Dependencies

The following enhancements have shared dependencies or integration points:

| Enhancement | Depends On | Shared Component |
|-------------|-----------|-----------------|
| E-05 (Playwright Google) | — | Playwright optional dependency; browser lifecycle |
| E-06 (Circuit Breaker) | — | Standalone; consumed by E-07 and E-08 |
| E-07 (Health Probes) | E-06 (optional) | Reads circuit breaker state if available |
| E-08 (Webhooks) | E-06 (optional), E-07 (optional) | Fires on circuit events; reads cache metrics |
| E-14 (Screenshot) | E-05 (shared dep) | Shares Playwright dependency and browser instance |

All other enhancements are fully independent and can be implemented in any order.
