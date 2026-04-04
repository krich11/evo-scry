import type { RawSearchResult, SearchResult } from "../providers/types.js";

export function deduplicateResults(results: RawSearchResult[]): RawSearchResult[] {
  const seen = new Map<string, RawSearchResult>();

  for (const result of results) {
    const key = normalizeUrl(result.url);
    const existing = seen.get(key);
    if (!existing) {
      seen.set(key, result);
    } else {
      // Merge: prefer longer snippet
      if (result.snippet.length > existing.snippet.length) {
        seen.set(key, { ...existing, snippet: result.snippet });
      }
      // Prefer result with a date
      if (!existing.publishedDate && result.publishedDate) {
        seen.set(key, { ...seen.get(key)!, publishedDate: result.publishedDate });
      }
    }
  }

  return Array.from(seen.values());
}

function normalizeUrl(url: string): string {
  try {
    const parsed = new URL(url);
    // Lowercase host
    let normalized = `${parsed.protocol}//${parsed.hostname.toLowerCase()}${parsed.pathname}`;
    // Remove trailing slash
    if (normalized.endsWith("/")) {
      normalized = normalized.slice(0, -1);
    }
    // Remove tracking params
    const cleanParams = new URLSearchParams();
    for (const [key, value] of parsed.searchParams) {
      if (!key.startsWith("utm_") && key !== "ref" && key !== "source") {
        cleanParams.set(key, value);
      }
    }
    const paramStr = cleanParams.toString();
    return paramStr ? `${normalized}?${paramStr}` : normalized;
  } catch {
    return url.toLowerCase();
  }
}

export function extractDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}
