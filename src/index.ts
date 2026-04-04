#!/usr/bin/env node

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { loadConfig } from "./config.js";
import { executeWebSearch } from "./tools/web-search.js";
import { executeSearchGoogle } from "./tools/search-google.js";
import { executeSearchDdg } from "./tools/search-ddg.js";
import { executeExtractContent } from "./tools/extract-content.js";

const config = loadConfig();

const server = new McpServer({
  name: "evo-scry",
  version: "1.0.0",
});

// --- Tool: web_search ---
server.tool(
  "web_search",
  "Search the internet using Google and DuckDuckGo. Results are aggregated, deduplicated, and ranked by relevance. Optionally summarized using AI.",
  {
    query: z.string().describe("Search query text"),
    engines: z
      .array(z.enum(["google", "duckduckgo"]))
      .optional()
      .describe('Engines to query (default: both). Example: ["google","duckduckgo"]'),
    maxResults: z
      .number()
      .int()
      .min(1)
      .max(50)
      .optional()
      .describe("Maximum results per engine (default: 10)"),
    language: z
      .string()
      .optional()
      .describe('Language code ISO 639-1 (default: "en")'),
    dateRange: z
      .enum(["day", "week", "month", "year"])
      .optional()
      .describe("Date range filter"),
    summarize: z
      .boolean()
      .optional()
      .describe("Generate AI summary of top results (default: false)"),
  },
  async (args) => {
    const response = await executeWebSearch(args);
    return {
      content: [{ type: "text", text: JSON.stringify(response, null, 2) }],
    };
  },
);

// --- Tool: search_google ---
server.tool(
  "search_google",
  "Search Google directly. Returns parsed results from Google's HTML search page.",
  {
    query: z.string().describe("Search query text"),
    maxResults: z
      .number()
      .int()
      .min(1)
      .max(50)
      .optional()
      .describe("Maximum results to return (default: 10)"),
    language: z.string().optional().describe('Language code (default: "en")'),
    dateRange: z
      .enum(["day", "week", "month", "year"])
      .optional()
      .describe("Date range filter"),
  },
  async (args) => {
    const response = await executeSearchGoogle(args);
    return {
      content: [{ type: "text", text: JSON.stringify(response, null, 2) }],
    };
  },
);

// --- Tool: search_duckduckgo ---
server.tool(
  "search_duckduckgo",
  "Search DuckDuckGo directly via its HTML endpoint. Privacy-focused, no JavaScript rendering required.",
  {
    query: z.string().describe("Search query text"),
    maxResults: z
      .number()
      .int()
      .min(1)
      .max(50)
      .optional()
      .describe("Maximum results to return (default: 10)"),
    language: z.string().optional().describe('Language code (default: "en")'),
    dateRange: z
      .enum(["day", "week", "month", "year"])
      .optional()
      .describe("Date range filter"),
  },
  async (args) => {
    const response = await executeSearchDdg(args);
    return {
      content: [{ type: "text", text: JSON.stringify(response, null, 2) }],
    };
  },
);

// --- Tool: extract_content ---
server.tool(
  "extract_content",
  "Fetch one or more URLs and extract clean text or Markdown content. Useful for reading full articles from search results.",
  {
    url: z
      .union([z.string().url(), z.array(z.string().url())])
      .describe("URL or array of URLs to extract content from"),
    format: z
      .enum(["text", "markdown"])
      .optional()
      .describe('Output format (default: "markdown")'),
  },
  async (args) => {
    const results = await executeExtractContent(args);
    return {
      content: [{ type: "text", text: JSON.stringify(results, null, 2) }],
    };
  },
);

// --- Start server ---
async function main() {
  if (config.transport === "http") {
    const { StreamableHTTPServerTransport } = await import(
      "@modelcontextprotocol/sdk/server/streamableHttp.js"
    );
    const { createServer } = await import("node:http");

    const httpTransport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined });
    await server.connect(httpTransport);

    const httpServer = createServer(async (req, res) => {
      if (req.method === "POST" && req.url === "/mcp") {
        const body = await collectBody(req);
        const fakeReq = {
          ...req,
          body: JSON.parse(body),
        } as unknown as Parameters<typeof httpTransport.handleRequest>[0];
        await httpTransport.handleRequest(fakeReq, res);
      } else if (req.method === "GET" && req.url === "/health") {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ status: "ok", name: "evo-scry", version: "1.0.0" }));
      } else {
        res.writeHead(404);
        res.end("Not found");
      }
    });

    httpServer.listen(config.port, () => {
      log("info", `evo-scry HTTP server listening on port ${config.port}`);
    });
  } else {
    // STDIO transport (default)
    const transport = new StdioServerTransport();
    await server.connect(transport);
    log("info", "evo-scry MCP server started on STDIO");
  }
}

function collectBody(req: import("node:http").IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks).toString()));
    req.on("error", reject);
  });
}

function log(level: string, message: string) {
  const levels = ["debug", "info", "warn", "error"];
  if (levels.indexOf(level) >= levels.indexOf(config.logLevel)) {
    const ts = new Date().toISOString();
    process.stderr.write(`[${ts}] [${level.toUpperCase()}] ${message}\n`);
  }
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${(err as Error).message}\n`);
  process.exit(1);
});
