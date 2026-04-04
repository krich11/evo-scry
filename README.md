# evo-scry

MCP server for internet search via direct Google and DuckDuckGo HTML scraping with AI-powered result normalization.

**Zero API keys required for search.** Optional AI summarization via GitHub Copilot token or local Ollama model.

## Features

- **4 MCP Tools**: `web_search`, `search_google`, `search_duckduckgo`, `extract_content`
- **Multi-engine aggregation**: Parallel search across Google + DuckDuckGo with deduplication and cross-engine ranking
- **AI summarization**: Optional result summaries via GitHub Copilot or local Ollama models
- **Production-ready**: Systemd service with full environment variable configuration
- **Privacy-respecting**: Direct HTML scraping, no third-party search APIs

## Quick Start

```bash
# Install dependencies
npm install

# Build
npm run build

# Run (STDIO transport for local MCP clients)
npm start
```

### Claude Desktop / VS Code Configuration

```json
{
  "mcpServers": {
    "evo-scry": {
      "command": "node",
      "args": ["/path/to/evo-scry/dist/index.js"]
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
| engines    | string[] | no       | both    | Engines to use |
| maxResults | number   | no       | 10      | Max results per engine |
| language   | string   | no       | "en"    | Language code |
| dateRange  | string   | no       | —       | "day", "week", "month", "year" |
| summarize  | boolean  | no       | false   | AI-summarize results |

### `search_google` / `search_duckduckgo`
Engine-specific search tools with the same parameters (minus `engines` and `summarize`).

### `extract_content`
Fetch URLs and extract clean text or Markdown content.

| Parameter | Type            | Required | Default    | Description |
|-----------|-----------------|----------|------------|-------------|
| url       | string\|string[] | yes      | —          | URL(s) to extract |
| format    | string          | no       | "markdown" | "text" or "markdown" |

## AI Summarization Setup

### GitHub Copilot Token (recommended)

```bash
npm run generate-token
```

Follow the prompts to authenticate via GitHub OAuth Device Flow. Add the generated tokens to your `.env` or systemd environment file.

### Local Model (Ollama)

```bash
# In .env or systemd env:
EVOSCRY_LOCAL_MODEL_URL=http://localhost:11434
EVOSCRY_LOCAL_MODEL_NAME=llama3
```

## Systemd Deployment

```bash
# Build first
npm install && npm run build

# Install (requires root)
sudo bash scripts/install.sh

# Configure
sudo vim /etc/evo-scry/evo-scry.env

# Start
sudo systemctl enable --now evo-scry
```

MCP endpoint: `http://localhost:3000/mcp`
Health check: `http://localhost:3000/health`

## Configuration

All options via environment variables. See [.env.example](.env.example) for the full list.

| Variable | Default | Description |
|----------|---------|-------------|
| `EVOSCRY_TRANSPORT` | `stdio` | `stdio` or `http` |
| `EVOSCRY_PORT` | `3000` | HTTP port |
| `EVOSCRY_SEARCH_ENGINES` | `google,duckduckgo` | Enabled engines |
| `EVOSCRY_MAX_RESULTS` | `10` | Results per engine |
| `EVOSCRY_REQUEST_DELAY_MS` | `1000` | Rate limiting delay |
| `EVOSCRY_USER_AGENT` | `rotate` | UA rotation |
| `EVOSCRY_PROXY_URL` | — | HTTP/SOCKS5 proxy |
| `EVOSCRY_COPILOT_TOKEN` | — | Copilot API token |
| `EVOSCRY_LOCAL_MODEL_URL` | — | Ollama endpoint |
| `EVOSCRY_LOG_LEVEL` | `info` | Log verbosity |
| `EVOSCRY_CACHE_TTL_SECONDS` | `300` | Cache TTL |

## License

MIT
