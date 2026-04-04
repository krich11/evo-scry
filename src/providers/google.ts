import * as cheerio from "cheerio";
import type { RawSearchResult, SearchOptions } from "./types.js";
import { fetchWithConfig } from "./http.js";

const GOOGLE_SEARCH_URL = "https://www.google.com/search";

const DATE_RANGE_MAP: Record<string, string> = {
  day: "qdr:d",
  week: "qdr:w",
  month: "qdr:m",
  year: "qdr:y",
};

export async function searchGoogle(options: SearchOptions): Promise<RawSearchResult[]> {
  const params = new URLSearchParams({
    q: options.query,
    num: String(Math.min(options.maxResults + 5, 40)), // request a few extra to account for filtering
    hl: options.language,
  });

  if (options.dateRange && DATE_RANGE_MAP[options.dateRange]) {
    params.set("tbs", DATE_RANGE_MAP[options.dateRange]);
  }

  const url = `${GOOGLE_SEARCH_URL}?${params.toString()}`;
  const response = await fetchWithConfig(url);

  if (!response.ok) {
    if (response.status === 429 || response.status === 503) {
      throw new Error(`Google rate-limited (HTTP ${response.status}). Try increasing EVOSCRY_REQUEST_DELAY_MS or using a proxy.`);
    }
    throw new Error(`Google returned HTTP ${response.status}`);
  }

  const html = await response.text();
  return parseGoogleResults(html, options.maxResults);
}

function parseGoogleResults(html: string, maxResults: number): RawSearchResult[] {
  const $ = cheerio.load(html);
  const results: RawSearchResult[] = [];

  // Google organic results live in div.g containers
  $("div.g").each((_i, el) => {
    if (results.length >= maxResults) return false;

    // Skip ad results
    if ($(el).closest("div.uEierd").length > 0) return;
    if ($(el).closest("[data-text-ad]").length > 0) return;

    const linkEl = $(el).find("a").first();
    const titleEl = $(el).find("h3").first();

    const href = linkEl.attr("href") || "";
    const title = titleEl.text().trim();

    // Skip non-http links (Google internal pages, etc.)
    if (!href.startsWith("http")) return;

    // Extract snippet from various known selectors
    let snippet = "";
    const snippetSelectors = [
      "div[data-sncf]",
      "div.VwiC3b",
      'div[style="-webkit-line-clamp:2"]',
      "span.aCOpRe",
    ];
    for (const sel of snippetSelectors) {
      const text = $(el).find(sel).first().text().trim();
      if (text) {
        snippet = text;
        break;
      }
    }

    // Fallback: grab any text after the title that looks like a description
    if (!snippet) {
      const allText = $(el).text();
      const titleIdx = allText.indexOf(title);
      if (titleIdx >= 0) {
        snippet = allText.slice(titleIdx + title.length).trim().slice(0, 300);
      }
    }

    // Try to extract date from snippet
    let publishedDate: string | null = null;
    const dateMatch = snippet.match(/^(\w{3}\s+\d{1,2},\s+\d{4})\s*[—–-]\s*/);
    if (dateMatch) {
      try {
        const d = new Date(dateMatch[1]);
        if (!isNaN(d.getTime())) {
          publishedDate = d.toISOString().split("T")[0];
          snippet = snippet.slice(dateMatch[0].length);
        }
      } catch {
        // ignore invalid date
      }
    }

    if (title && href) {
      results.push({
        title,
        url: href,
        snippet,
        engine: "google",
        publishedDate,
      });
    }
  });

  return results;
}
