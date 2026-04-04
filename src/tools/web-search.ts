import type { RawSearchResult, SearchResponse } from "../providers/types.js";
import { loadConfig } from "../config.js";
import { searchGoogle } from "../providers/google.js";
import { searchDuckDuckGo } from "../providers/duckduckgo.js";
import { deduplicateResults } from "../normalize/dedup.js";
import { rankResults } from "../normalize/rank.js";
import { summarizeResults } from "../normalize/summarize.js";
import { cacheKey, cacheGet, cacheSet } from "../cache.js";

export interface WebSearchArgs {
  query: string;
  engines?: string[];
  maxResults?: number;
  language?: string;
  dateRange?: string;
  summarize?: boolean;
}

export async function executeWebSearch(args: WebSearchArgs): Promise<SearchResponse> {
  const config = loadConfig();
  const query = args.query.trim();
  if (!query) {
    throw new Error("Search query cannot be empty");
  }

  const engines = (args.engines || config.searchEngines).filter(
    (e): e is "google" | "duckduckgo" => e === "google" || e === "duckduckgo",
  );
  const maxResults = args.maxResults || config.maxResults;
  const language = args.language || "en";
  const dateRange = args.dateRange;
  const shouldSummarize = args.summarize ?? false;

  // Check cache
  const key = cacheKey({ engines: engines.join(","), query, language, dateRange: dateRange || "", maxResults });
  const cached = cacheGet<RawSearchResult[]>(key);

  let allResults: RawSearchResult[];

  if (cached) {
    allResults = cached;
  } else {
    // Fan out to engines in parallel
    const promises: Promise<RawSearchResult[]>[] = [];
    const engineErrors: string[] = [];

    for (const engine of engines) {
      if (engine === "google") {
        promises.push(
          searchGoogle({ query, maxResults, language, dateRange }).catch((err) => {
            engineErrors.push(`google: ${(err as Error).message}`);
            return [];
          }),
        );
      } else if (engine === "duckduckgo") {
        promises.push(
          searchDuckDuckGo({ query, maxResults, language, dateRange }).catch((err) => {
            engineErrors.push(`duckduckgo: ${(err as Error).message}`);
            return [];
          }),
        );
      }
    }

    const resultSets = await Promise.all(promises);
    allResults = resultSets.flat();

    if (allResults.length === 0 && engineErrors.length > 0) {
      throw new Error(`All search engines failed: ${engineErrors.join("; ")}`);
    }

    // Cache raw results
    cacheSet(key, allResults);
  }

  // Normalize
  const deduped = deduplicateResults(allResults);
  const ranked = rankResults(deduped, query);
  const trimmed = ranked.slice(0, maxResults);

  // AI summarization
  let summary: string | undefined;
  if (shouldSummarize) {
    summary = await summarizeResults(query, trimmed);
  }

  return {
    query,
    engines,
    totalResults: trimmed.length,
    results: trimmed,
    summary,
    cached: !!cached,
    timestamp: new Date().toISOString(),
  };
}
