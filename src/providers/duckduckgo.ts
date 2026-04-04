import * as cheerio from "cheerio";
import type { RawSearchResult, SearchOptions } from "./types.js";
import { fetchWithConfig } from "./http.js";

const DDG_HTML_URL = "https://html.duckduckgo.com/html/";

export async function searchDuckDuckGo(options: SearchOptions): Promise<RawSearchResult[]> {
  const params = new URLSearchParams({ q: options.query });

  const url = `${DDG_HTML_URL}?${params.toString()}`;
  const response = await fetchWithConfig(url);

  if (!response.ok) {
    throw new Error(`DuckDuckGo returned HTTP ${response.status}`);
  }

  const html = await response.text();
  return parseDuckDuckGoResults(html, options.maxResults);
}

function parseDuckDuckGoResults(html: string, maxResults: number): RawSearchResult[] {
  const $ = cheerio.load(html);
  const results: RawSearchResult[] = [];

  $(".result.results_links").each((_i, el) => {
    if (results.length >= maxResults) return false;

    // Skip sponsored/ad results
    if ($(el).hasClass("result--ad")) return;
    if ($(el).find(".badge--ad").length > 0) return;

    const titleEl = $(el).find(".result__title a");
    const snippetEl = $(el).find(".result__snippet");
    const urlEl = $(el).find(".result__url");

    const title = titleEl.text().trim().replace(/more info$/i, "");
    const snippet = snippetEl.text().trim();

    // DuckDuckGo wraps URLs in redirect links — extract actual URL from uddg param
    let resultUrl = "";
    const href = titleEl.attr("href") || "";
    if (href.includes("uddg=")) {
      try {
        const parsed = new URL(href, "https://duckduckgo.com");
        resultUrl = parsed.searchParams.get("uddg") || href;
      } catch {
        resultUrl = href;
      }
    } else if (href.startsWith("http")) {
      resultUrl = href;
    } else {
      // Try the displayed URL text
      const displayUrl = urlEl.text().trim();
      if (displayUrl) {
        resultUrl = displayUrl.startsWith("http") ? displayUrl : `https://${displayUrl}`;
      }
    }

    // Filter out ad redirect URLs
    if (resultUrl.includes("duckduckgo.com/y.js") || resultUrl.includes("ad_provider=")) {
      return;
    }

    if (title && resultUrl) {
      results.push({
        title,
        url: resultUrl,
        snippet,
        engine: "duckduckgo",
        publishedDate: null,
      });
    }
  });

  return results;
}
