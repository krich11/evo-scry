# evo-scry

MCP server for internet search via direct Google and DuckDuckGo HTML scraping with AI-powered result normalization.

**Python.** **Zero API keys required for search.** Optional AI summarization via GitHub Copilot token or local Ollama model.

## Features

- **4 MCP Tools**: `web_search`, `search_google`, `search_duckduckgo`, `extract_content`
- **Multi-engine aggregation**: Parallel search across Google + DuckDuckGo with deduplication and cross-engine ranking
- **AI summarization**: Optional result summaries via GitHub Copilot or local Ollama models
- **Production-ready**: Systemd service with full environment variable configuration
- **Privacy-respecting**: Direct HTML scraping, no third-party search APIs
- **FastMCP pattern**: Same architecture as evo-mem — SSE + streamable-http dual transport

## Quick Start

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install
pip install -e .

# Run (STDIO transport for local MCP clients)
python -m evoscry.mcp_server

# Run (SSE transport for remote/systemd)
python -m evoscry.mcp_server --transport sse --port 3000
```

### Claude Desktop / VS Code Configuration

```json
{
  "mcpServers": {
    "evo-scry": {
      "command": "python",
      "args": ["-m", "evoscry.mcp_server"]
    }
  }
}
```

### SSE Transport (remote)

```json
{
  "mcpServers": {
    "evo-scry": {
      "url": "http://your-server:3000/sse"
    }
  }
}
```

## MCP Tools

### `web_search`
Search the internet using both Google and DuckDuckGo. Results are aggregated, deduplicated, and ranked.

| Parameter  | Type     | Required | Default | Description |
|------------|----------|----------|---------|-------------|
| query      | string   | yes      | —       | Search query |
| engines    | list     | no       | config  | Engines to use |
| max_results| int      | no       | 10      | Max results per engine |
| language   | string   | no       | "en"    | Language code |
| date_range | string   | no       | —       | "day", "week", "month", "year" |
| summarize  | bool     | no       | false   | AI-summarize results |

### `search_google` / `search_duckduckgo`
Engine-specific search tools with the same parameters (minus `engines` and `summarize`).

### `extract_content`
Fetch URLs and extract clean text or Markdown content.

| Parameter | Type            | Required | Default    | Description |
|-----------|-----------------|----------|------------|-------------|
| url       | str \| list[str] | yes     | —          | URL(s) to extract |
| format    | string          | no       | "markdown" | "text" or "markdown" |

## AI Summarization Setup

### GitHub Copilot Token (recommended)

```bash
python -m evoscry.generate_copilot_token
```

Follow the prompts to authenticate via GitHub OAuth Device Flow. Add the generated token to your `.env` or systemd environment file.

### Local Model (Ollama)

```bash
# In .env or systemd env:
EVOSCRY_LOCAL_MODEL_URL=http://localhost:11434
EVOSCRY_LOCAL_MODEL_NAME=llama3
```

## Systemd Deployment

```bash
# Install (requires root)
sudo bash install.sh

# Configure
sudo vim /etc/evo-scry/evo-scry.env

# Start
sudo systemctl enable --now evo-scry
```

SSE endpoint: `http://localhost:3000/sse`
Health check: `http://localhost:3000/health`

## Configuration

All options via environment variables. See [.env.example](.env.example) for the full list.

| Variable | Default | Description |
|----------|---------|-------------|
| `EVOSCRY_TRANSPORT` | `stdio` | `stdio`, `sse`, or `streamable-http` |
| `EVOSCRY_HOST` | `0.0.0.0` | HTTP bind address |
| `EVOSCRY_PORT` | `3000` | HTTP port |
| `EVOSCRY_SEARCH_ENGINES` | `duckduckgo` | Enabled engines |
| `EVOSCRY_MAX_RESULTS` | `10` | Results per engine |
| `EVOSCRY_REQUEST_DELAY_MS` | `1000` | Rate limiting delay |
| `EVOSCRY_USER_AGENT` | `rotate` | UA rotation |
| `EVOSCRY_PROXY_URL` | — | HTTP/SOCKS5 proxy |
| `EVOSCRY_COPILOT_TOKEN` | — | Copilot API token |
| `EVOSCRY_COPILOT_REFRESH_TOKEN` | — | GitHub OAuth token for auto-refresh |
| `EVOSCRY_LOCAL_MODEL_URL` | — | Ollama endpoint |
| `EVOSCRY_LOG_LEVEL` | `info` | Log verbosity |
| `EVOSCRY_CACHE_TTL_SECONDS` | `300` | Cache TTL |

## License

MIT
