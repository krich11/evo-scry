"""Snippet quality scoring — penalize low-information snippets."""

from __future__ import annotations

import re

# Pre-compiled patterns that indicate low-quality / gated content
_LOW_QUALITY_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"sign\s*in",
        r"log\s*in\s*(to\s+)?(continue|access|view)",
        r"accept\s*(all\s+)?cookies",
        r"cookie\s*(policy|consent|banner)",
        r"enable\s+javascript",
        r"your\s+browser\s+(does\s+not|doesn't)\s+support",
        r"please\s+enable",
        r"subscribe\s+to\s+(read|continue|access|view|unlock)",
        r"(create|sign\s*up\s+for)\s+(a\s+)?(free\s+)?account",
        r"you('ve|\s+have)\s+reached\s+(your|the)\s+(free\s+)?(article\s+)?limit",
        r"this\s+content\s+is\s+(only\s+)?available\s+to\s+(subscribers|members)",
        r"access\s+denied",
        r"403\s+forbidden",
        r"page\s+not\s+found",
        r"404\s+error",
    )
]


def snippet_quality(snippet: str) -> float:
    """Score a search result snippet from 0.0 (garbage) to 1.0 (high quality).

    Scoring factors:
    - Length (very short snippets are penalised)
    - Low-quality content patterns (login walls, cookie prompts, errors)
    - Word variety (repetitive text is penalised)
    """
    if not snippet:
        return 0.0

    stripped = snippet.strip()
    length = len(stripped)

    if length < 20:
        return 0.1
    if length < 50:
        return 0.4

    # Pattern-based penalty
    penalty = 0.0
    for pattern in _LOW_QUALITY_PATTERNS:
        if pattern.search(stripped):
            penalty += 0.25

    penalty = min(penalty, 0.9)

    # Word variety check
    words = stripped.lower().split()
    if words:
        variety = len(set(words)) / len(words)
        if variety < 0.3:
            penalty += 0.2

    return max(0.0, min(1.0, 1.0 - penalty))
