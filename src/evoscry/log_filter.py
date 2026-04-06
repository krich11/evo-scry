"""Query anonymization filter for Python logging.

When enabled, replaces search query strings in log output with truncated
SHA-256 hashes so that operational logs remain useful without exposing
the actual content of searches.
"""

from __future__ import annotations

import hashlib
import logging
import re

# Patterns that identify query strings in structured log args
_QUERY_ARG_KEYS = frozenset({"query", "q", "search_query", "site_query"})

# Patterns that identify query strings in free-form log messages
_MSG_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'query[=:]\s*"(.+?)"', re.IGNORECASE),
    re.compile(r"query[=:]\\s*'(.+?)'", re.IGNORECASE),
    re.compile(r'searching\s+for\s+"(.+?)"', re.IGNORECASE),
    re.compile(r"searching\s+for\s+'(.+?)'", re.IGNORECASE),
    re.compile(r"search query:\s*(.+?)(?:\s*$|\s*,)", re.IGNORECASE),
]


def anonymize_query(query: str) -> str:
    """Return ``q:<12-char-hex>`` hash of *query*."""
    h = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"q:{h[:12]}"


class AnonymizeFilter(logging.Filter):
    """Logging filter that replaces detected query strings with hashed IDs."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Mutate the message — always return True (never suppress records)
        if isinstance(record.msg, str):
            for pattern in _MSG_PATTERNS:
                record.msg = pattern.sub(
                    lambda m: m.group(0).replace(m.group(1), anonymize_query(m.group(1))),
                    record.msg,
                )

        if record.args:
            record.args = _anonymize_args(record.args)

        return True


def _anonymize_args(args):
    """Anonymize query-like keys in structured log arguments."""
    if isinstance(args, dict):
        return {
            k: anonymize_query(v) if k in _QUERY_ARG_KEYS and isinstance(v, str) else v
            for k, v in args.items()
        }
    if isinstance(args, tuple):
        # Can't reliably identify which positional arg is a query,
        # so leave tuples untouched — prefer dict-style logging.
        return args
    return args
