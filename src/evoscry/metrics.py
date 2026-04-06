"""Global operational metrics — lightweight counters for health endpoints."""

from __future__ import annotations

import time
from datetime import datetime, timezone


class Metrics:
    """In-process counters tracked across the server lifetime."""

    def __init__(self) -> None:
        self.start_time: float = time.monotonic()
        self.start_wall: float = time.time()

        # Searches
        self.search_total: int = 0
        self.search_errors: int = 0
        self.searches_by_engine: dict[str, int] = {}
        self.errors_by_engine: dict[str, int] = {}
        self.last_success_by_engine: dict[str, float] = {}
        self.last_failure_by_engine: dict[str, float] = {}

        # Cache
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.cache_evictions: int = 0

        # AI
        self.ai_calls_total: int = 0
        self.ai_calls_failed: int = 0

    # ── Helpers ───────────────────────────────────────────────────────────

    def record_search(self, engine: str) -> None:
        self.search_total += 1
        self.searches_by_engine[engine] = self.searches_by_engine.get(engine, 0) + 1

    def record_search_success(self, engine: str) -> None:
        self.last_success_by_engine[engine] = time.time()

    def record_search_error(self, engine: str) -> None:
        self.search_errors += 1
        self.errors_by_engine[engine] = self.errors_by_engine.get(engine, 0) + 1
        self.last_failure_by_engine[engine] = time.time()

    def record_cache_hit(self) -> None:
        self.cache_hits += 1

    def record_cache_miss(self) -> None:
        self.cache_misses += 1

    def record_cache_eviction(self) -> None:
        self.cache_evictions += 1

    def record_ai_call(self, failed: bool = False) -> None:
        self.ai_calls_total += 1
        if failed:
            self.ai_calls_failed += 1

    # ── Snapshot ──────────────────────────────────────────────────────────

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self.start_time

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total else 0.0

    def _iso(self, ts: float | None) -> str | None:
        if ts is None:
            return None
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    def snapshot(self) -> dict:
        """Full metrics snapshot suitable for JSON serialisation."""
        return {
            "uptime_seconds": round(self.uptime_seconds, 1),
            "searches": {
                "total": self.search_total,
                "errors": self.search_errors,
                "by_engine": dict(self.searches_by_engine),
                "errors_by_engine": dict(self.errors_by_engine),
                "last_success_by_engine": {
                    k: self._iso(v) for k, v in self.last_success_by_engine.items()
                },
                "last_failure_by_engine": {
                    k: self._iso(v) for k, v in self.last_failure_by_engine.items()
                },
            },
            "cache": {
                "hits": self.cache_hits,
                "misses": self.cache_misses,
                "evictions": self.cache_evictions,
                "hit_rate": round(self.cache_hit_rate, 3),
            },
            "ai": {
                "calls_total": self.ai_calls_total,
                "calls_failed": self.ai_calls_failed,
            },
        }


# Module-level singleton
metrics = Metrics()
