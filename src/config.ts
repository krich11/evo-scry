export interface Config {
  transport: "stdio" | "http";
  port: number;
  searchEngines: ("google" | "duckduckgo")[];
  maxResults: number;
  requestDelayMs: number;
  userAgent: string;
  proxyUrl: string | undefined;
  copilotToken: string | undefined;
  copilotRefreshToken: string | undefined;
  localModelUrl: string | undefined;
  localModelName: string;
  logLevel: "debug" | "info" | "warn" | "error";
  cacheTtlSeconds: number;
}

export function loadConfig(): Config {
  const engines = (process.env.EVOSCRY_SEARCH_ENGINES || "duckduckgo")
    .split(",")
    .map((e) => e.trim().toLowerCase())
    .filter((e): e is "google" | "duckduckgo" => e === "google" || e === "duckduckgo");

  const logLevel = (process.env.EVOSCRY_LOG_LEVEL || "info").toLowerCase();
  const validLevels = ["debug", "info", "warn", "error"] as const;
  const resolvedLogLevel = validLevels.includes(logLevel as typeof validLevels[number])
    ? (logLevel as Config["logLevel"])
    : "info";

  return {
    transport: process.env.EVOSCRY_TRANSPORT === "http" ? "http" : "stdio",
    port: parseInt(process.env.EVOSCRY_PORT || "3000", 10),
    searchEngines: engines.length > 0 ? engines : ["duckduckgo"],
    maxResults: parseInt(process.env.EVOSCRY_MAX_RESULTS || "10", 10),
    requestDelayMs: parseInt(process.env.EVOSCRY_REQUEST_DELAY_MS || "1000", 10),
    userAgent: process.env.EVOSCRY_USER_AGENT || "rotate",
    proxyUrl: process.env.EVOSCRY_PROXY_URL || undefined,
    copilotToken: process.env.EVOSCRY_COPILOT_TOKEN || undefined,
    copilotRefreshToken: process.env.EVOSCRY_COPILOT_REFRESH_TOKEN || undefined,
    localModelUrl: process.env.EVOSCRY_LOCAL_MODEL_URL || undefined,
    localModelName: process.env.EVOSCRY_LOCAL_MODEL_NAME || "llama3",
    logLevel: resolvedLogLevel,
    cacheTtlSeconds: parseInt(process.env.EVOSCRY_CACHE_TTL_SECONDS || "300", 10),
  };
}
