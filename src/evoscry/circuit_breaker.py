"""Per-engine circuit breaker — CLOSED → OPEN → HALF_OPEN → CLOSED."""

from __future__ import annotations

import asyncio
import time
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Track consecutive failures for a single engine and short-circuit when unhealthy."""

    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: int = 60) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._last_success_time: float | None = None
        self._open_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def last_failure_time(self) -> float | None:
        return self._last_failure_time

    @property
    def last_success_time(self) -> float | None:
        return self._last_success_time

    async def can_execute(self) -> bool:
        """Return True if the engine should be attempted."""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._open_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    return True
                return False
            # HALF_OPEN — allow one test request
            return True

    async def record_success(self) -> None:
        async with self._lock:
            self._failure_count = 0
            self._last_success_time = time.time()
            if self._state != CircuitState.CLOSED:
                self._state = CircuitState.CLOSED

    async def record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._open_time = time.monotonic()
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._open_time = time.monotonic()

    def status(self) -> dict:
        """Snapshot for health endpoint."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "last_failure_time": self._last_failure_time,
            "last_success_time": self._last_success_time,
        }


# ── Module-level registry ────────────────────────────────────────────────────

_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(engine: str) -> CircuitBreaker:
    """Get or create a circuit breaker for *engine*."""
    if engine not in _breakers:
        from evoscry.config import load_config

        config = load_config()
        _breakers[engine] = CircuitBreaker(
            name=engine,
            failure_threshold=getattr(config, "circuit_failure_threshold", 5),
            recovery_timeout=getattr(config, "circuit_recovery_timeout", 60),
        )
    return _breakers[engine]


def all_breakers() -> dict[str, CircuitBreaker]:
    """Return the full registry (read-only view)."""
    return dict(_breakers)
