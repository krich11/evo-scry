import type { RawSearchResult, SearchResult } from "../providers/types.js";
import { extractDomain } from "./dedup.js";

// Domain authority tiers (higher = more authoritative)
const DOMAIN_AUTHORITY: Record<string, number> = {
  "github.com": 0.95,
  "stackoverflow.com": 0.95,
  "developer.mozilla.org": 0.95,
  "docs.python.org": 0.90,
  "docs.microsoft.com": 0.90,
  "learn.microsoft.com": 0.90,
  "wikipedia.org": 0.85,
  "en.wikipedia.org": 0.85,
  "arxiv.org": 0.85,
  "medium.com": 0.60,
  "dev.to": 0.65,
  "hackernews.com": 0.70,
  "news.ycombinator.com": 0.75,
  "reddit.com": 0.60,
  "twitter.com": 0.50,
  "x.com": 0.50,
};

const DOMAIN_PATTERN_AUTHORITY: [RegExp, number][] = [
  [/\.gov$/, 0.90],
  [/\.edu$/, 0.85],
  [/\.org$/, 0.70],
  [/docs\./, 0.80],
  [/wiki\./, 0.70],
];

function getDomainAuthority(domain: string): number {
  if (DOMAIN_AUTHORITY[domain] !== undefined) {
    return DOMAIN_AUTHORITY[domain];
  }
  for (const [pattern, score] of DOMAIN_PATTERN_AUTHORITY) {
    if (pattern.test(domain)) {
      return score;
    }
  }
  return 0.50; // default
}

function computeKeywordMatch(query: string, title: string, snippet: string): number {
  const queryTerms = query.toLowerCase().split(/\s+/).filter((t) => t.length > 2);
  if (queryTerms.length === 0) return 0.5;

  const text = `${title} ${snippet}`.toLowerCase();
  let matches = 0;
  for (const term of queryTerms) {
    if (text.includes(term)) matches++;
  }
  return matches / queryTerms.length;
}

function computeFreshness(publishedDate: string | null): number {
  if (!publishedDate) return 0.5; // neutral when unknown
  try {
    const date = new Date(publishedDate);
    const now = new Date();
    const daysSince = (now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24);
    if (daysSince < 7) return 1.0;
    if (daysSince < 30) return 0.85;
    if (daysSince < 90) return 0.70;
    if (daysSince < 365) return 0.55;
    return 0.30;
  } catch {
    return 0.5;
  }
}

interface RankingContext {
  query: string;
  engineCounts: Map<string, Set<string>>; // url -> set of engines that returned it
}

const WEIGHTS = {
  position: 0.40,
  keyword: 0.25,
  authority: 0.20,
  freshness: 0.15,
};

const CROSS_ENGINE_BOOST = 1.2;

export function rankResults(
  raw: RawSearchResult[],
  query: string,
): SearchResult[] {
  // Track which engines returned each URL
  const engineSets = new Map<string, Set<string>>();
  for (const r of raw) {
    const key = r.url.toLowerCase();
    if (!engineSets.has(key)) engineSets.set(key, new Set());
    engineSets.get(key)!.add(r.engine);
  }

  // Score each result
  const scored: SearchResult[] = raw.map((r, index) => {
    const domain = extractDomain(r.url);
    const positionScore = 1 / (index + 1);
    const keywordScore = computeKeywordMatch(query, r.title, r.snippet);
    const authorityScore = getDomainAuthority(domain);
    const freshnessScore = computeFreshness(r.publishedDate);

    let relevanceScore =
      WEIGHTS.position * positionScore +
      WEIGHTS.keyword * keywordScore +
      WEIGHTS.authority * authorityScore +
      WEIGHTS.freshness * freshnessScore;

    // Boost results that appear in multiple engines
    const engines = engineSets.get(r.url.toLowerCase());
    if (engines && engines.size > 1) {
      relevanceScore *= CROSS_ENGINE_BOOST;
    }

    // Clamp to [0, 1]
    relevanceScore = Math.min(1, Math.max(0, relevanceScore));

    return {
      rank: 0, // assigned after sorting
      title: r.title,
      url: r.url,
      snippet: r.snippet,
      engine: r.engine,
      publishedDate: r.publishedDate,
      domain,
      relevanceScore: Math.round(relevanceScore * 1000) / 1000,
      summary: null,
    };
  });

  // Sort by relevanceScore descending
  scored.sort((a, b) => b.relevanceScore - a.relevanceScore);

  // Assign ranks
  for (let i = 0; i < scored.length; i++) {
    scored[i].rank = i + 1;
  }

  return scored;
}
