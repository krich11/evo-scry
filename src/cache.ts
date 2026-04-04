import { loadConfig } from "./config.js";
import { createHash } from "node:crypto";

interface CacheEntry<T> {
  value: T;
  expires: number;
}

const cache = new Map<string, CacheEntry<unknown>>();
const MAX_ENTRIES = 100;

export function cacheKey(parts: Record<string, string | number | undefined>): string {
  const raw = JSON.stringify(parts);
  return createHash("sha256").update(raw).digest("hex");
}

export function cacheGet<T>(key: string): T | undefined {
  const config = loadConfig();
  if (config.cacheTtlSeconds <= 0) return undefined;

  const entry = cache.get(key) as CacheEntry<T> | undefined;
  if (!entry) return undefined;

  if (Date.now() > entry.expires) {
    cache.delete(key);
    return undefined;
  }

  return entry.value;
}

export function cacheSet<T>(key: string, value: T): void {
  const config = loadConfig();
  if (config.cacheTtlSeconds <= 0) return;

  // LRU eviction: remove oldest if over limit
  if (cache.size >= MAX_ENTRIES) {
    const firstKey = cache.keys().next().value;
    if (firstKey) cache.delete(firstKey);
  }

  cache.set(key, {
    value,
    expires: Date.now() + config.cacheTtlSeconds * 1000,
  });
}
