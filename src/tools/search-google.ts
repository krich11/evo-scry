import { searchGoogle } from "../providers/google.js";
import { rankResults } from "../normalize/rank.js";
import { cacheKey, cacheGet, cacheSet } from "../cache.js";
import type { RawSearchResult, SearchResponse } from "../providers/types.js";
import { loadConfig } from "../config.js";

export interface SearchGoogleArgs {
  query: string;
  maxResults?: number;
  language?: string;
  dateRange?: string;
}

export async function executeSearchGoogle(args: SearchGoogleArgs): Promise<SearchResponse> {
  const config = loadConfig();
  const query = args.query.trim();
  if (!query) throw new Error("Search query cannot be empty");

  const maxResults = args.maxResults || config.maxResults;
  const language = args.language || "en";
  const dateRange = args.dateRange;

  const key = cacheKey({ engine: "google", query, language, dateRange: dateRange || "", maxResults });
  const cached = cacheGet<RawSearchResult[]>(key);

  let raw: RawSearchResult[];
  if (cached) {
    raw = cached;
  } else {
    raw = await searchGoogle({ query, maxResults, language, dateRange });
    cacheSet(key, raw);
  }

  const ranked = rankResults(raw, query).slice(0, maxResults);

  return {
    query,
    engines: ["google"],
    totalResults: ranked.length,
    results: ranked,
    cached: !!cached,
    timestamp: new Date().toISOString(),
  };
}
