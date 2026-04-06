"""EvoScry configuration — all settings from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    transport: str = "stdio"  # "stdio" | "sse" | "streamable-http"
    host: str = "0.0.0.0"
    port: int = 3000
    search_engines: list[str] = field(default_factory=lambda: ["duckduckgo", "bing"])
    max_results: int = 10
    request_delay_ms: int = 1000
    user_agent: str = "rotate"
    proxy_url: str | None = None
    copilot_token: str | None = None
    copilot_refresh_token: str | None = None
    local_model_url: str | None = None
    local_model_name: str = "llama3"
    log_level: str = "info"
    cache_ttl_seconds: int = 300
    circuit_failure_threshold: int = 5
    circuit_recovery_timeout: int = 60
    query_expansion_max: int = 3
    anonymize_logs: bool = False


def load_config() -> Config:
    engines_raw = os.environ.get("EVOSCRY_SEARCH_ENGINES", "duckduckgo,bing")
    engines = [
        e.strip().lower()
        for e in engines_raw.split(",")
        if e.strip().lower() in ("google", "duckduckgo", "bing", "brave")
    ]
    if not engines:
        engines = ["duckduckgo"]

    log_level = os.environ.get("EVOSCRY_LOG_LEVEL", "info").lower()
    if log_level not in ("debug", "info", "warn", "error"):
        log_level = "info"

    return Config(
        transport=os.environ.get("EVOSCRY_TRANSPORT", "stdio"),
        host=os.environ.get("EVOSCRY_HOST", "0.0.0.0"),
        port=int(os.environ.get("EVOSCRY_PORT", "3000")),
        search_engines=engines,
        max_results=int(os.environ.get("EVOSCRY_MAX_RESULTS", "10")),
        request_delay_ms=int(os.environ.get("EVOSCRY_REQUEST_DELAY_MS", "1000")),
        user_agent=os.environ.get("EVOSCRY_USER_AGENT", "rotate"),
        proxy_url=os.environ.get("EVOSCRY_PROXY_URL") or None,
        copilot_token=os.environ.get("EVOSCRY_COPILOT_TOKEN") or None,
        copilot_refresh_token=os.environ.get("EVOSCRY_COPILOT_REFRESH_TOKEN") or None,
        local_model_url=os.environ.get("EVOSCRY_LOCAL_MODEL_URL") or None,
        local_model_name=os.environ.get("EVOSCRY_LOCAL_MODEL_NAME", "llama3"),
        log_level=log_level,
        cache_ttl_seconds=int(os.environ.get("EVOSCRY_CACHE_TTL_SECONDS", "300")),
        circuit_failure_threshold=int(os.environ.get("EVOSCRY_CIRCUIT_FAILURE_THRESHOLD", "5")),
        circuit_recovery_timeout=int(os.environ.get("EVOSCRY_CIRCUIT_RECOVERY_TIMEOUT", "60")),
        query_expansion_max=int(os.environ.get("EVOSCRY_QUERY_EXPANSION_MAX", "3")),
        anonymize_logs=os.environ.get("EVOSCRY_ANONYMIZE_LOGS", "false").lower() == "true",
    )
