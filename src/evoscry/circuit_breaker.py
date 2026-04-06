"""Per-engine circuit breaker — tracks consecutive failures and temporarily
disables unreliable engines.

State machine::

    CLOSED  ─failure→  (count < threshold) CLOSED
            ─failure→  (count >= threshold) OPEN
    OPEN    ─(timeout elapsed)→  HALF_OPEN
    HALF_OPEN ─success→  CLOSED
              ─failure→  OPEN
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker for a single search engine."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._opened_at: float | None = None
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

    async def can_execute(self) -> bool:
        """Return *True* if this engine should be attempted."""
        async with self._lock:
            if self._state is CircuitState.CLOSED:
                return True

            if self._state is CircuitState.OPEN:
                elapsed = time.monotonic() - (self._opened_at or 0)
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    logger.info(
                        "Circuit breaker testing recovery for %s", self.name
                    )
                    return True
                return False

            # HALF_OPEN — allow one probe request
            return True

    async def record_success(self) -> None:
        async with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                logger.info("Circuit breaker recovered for %s", self.name)
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None

    async def record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state is CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    "Circuit breaker re-opened for %s (probe failed)", self.name
                )
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    "Circuit breaker OPEN for %s: %d consecutive failures",
                    self.name,
                    self._failure_count,
                )

    def status(self) -> dict:
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "last_failure_time": self._last_failure_time,
        }


# ── Module-level registry ────────────────────────────────────────────────────

_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(
    engine: str,
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
) -> CircuitBreaker:
    """Get or create a circuit breaker for *engine*."""
    if engine not in _breakers:
        _breakers[engine] = CircuitBreaker(
            name=engine,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
    return _breakers[engine]


def all_breaker_statuses() -> dict[str, dict]:
    """Return status dicts keyed by engine name."""
    return {name: cb.status() for name, cb in _breakers.items()}
