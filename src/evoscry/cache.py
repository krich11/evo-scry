"""In-memory LRU cache with TTL."""

from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from typing import Any

from evoscry.config import load_config

_MAX_ENTRIES = 100
_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()


def cache_key(params: dict) -> str:
    """Generate a deterministic SHA-256 cache key from params."""
    raw = json.dumps(params, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_get(key: str) -> Any | None:
    """Get a value from cache if it exists and hasn't expired."""
    from evoscry.metrics import metrics

    config = load_config()
    entry = _cache.get(key)
    if entry is None:
        metrics.record_cache_miss()
        return None
    ts, value = entry
    if time.time() - ts > config.cache_ttl_seconds:
        _cache.pop(key, None)
        metrics.record_cache_miss()
        metrics.cache_size = len(_cache)
        return None
    # Move to end (most recently used)
    _cache.move_to_end(key)
    metrics.record_cache_hit()
    return value


def cache_set(key: str, value: Any) -> None:
    """Store a value in cache, evicting oldest if at capacity."""
    from evoscry.metrics import metrics

    _cache[key] = (time.time(), value)
    _cache.move_to_end(key)
    while len(_cache) > _MAX_ENTRIES:
        _cache.popitem(last=False)
        metrics.record_cache_eviction()
    metrics.cache_size = len(_cache)
