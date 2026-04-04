export interface RawSearchResult {
  title: string;
  url: string;
  snippet: string;
  engine: "google" | "duckduckgo";
  publishedDate: string | null;
}

export interface SearchResult {
  rank: number;
  title: string;
  url: string;
  snippet: string;
  engine: "google" | "duckduckgo";
  publishedDate: string | null;
  domain: string;
  relevanceScore: number;
  summary: string | null;
}

export interface SearchResponse {
  query: string;
  engines: string[];
  totalResults: number;
  results: SearchResult[];
  summary?: string;
  cached: boolean;
  timestamp: string;
}

export interface SearchOptions {
  query: string;
  maxResults: number;
  language: string;
  dateRange?: string;
}
