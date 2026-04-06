"""LLM-based query expansion — generates alternate search queries for broader recall."""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)


async def expand_query(query: str, max_expansions: int = 3) -> list[str]:
    """Generate alternate query phrasings via AI.

    Returns a list starting with the original query, followed by up to
    *max_expansions* alternate phrasings.  Falls back to ``[query]`` if AI
    is unavailable or returns unparseable output.
    """
    prompt = (
        f'Given the search query: "{query}"\n\n'
        f"Generate {max_expansions} alternative search queries that would help "
        "find relevant results. Each alternative should approach the topic from "
        "a different angle: synonyms, related terms, more specific phrasing, or "
        "broader context.\n\n"
        "Return ONLY a JSON array of strings, with no additional text. Example:\n"
        '["alternative query 1", "alternative query 2", "alternative query 3"]'
    )

    try:
        variants = await _ask_ai(prompt)
    except Exception:
        logger.debug("Query expansion AI call failed; using original query only")
        return [query]

    parsed = _parse_variants(variants, max_expansions)
    if not parsed:
        return [query]

    # Ensure the original query is always first and deduplicated
    seen: set[str] = set()
    result: list[str] = []
    for q in [query, *parsed]:
        key = q.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(q.strip())
    return result


def _parse_variants(text: str, max_expansions: int) -> list[str]:
    """Best-effort parse of an AI-generated JSON array of strings."""
    text = text.strip()

    # Try direct JSON parse
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(s) for s in data if s][:max_expansions]
    except json.JSONDecodeError:
        pass

    # Try extracting a JSON array from the response
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return [str(s) for s in data if s][:max_expansions]
        except json.JSONDecodeError:
            pass

    return []


async def _ask_ai(prompt: str) -> str:
    """Dispatch to Copilot or Ollama, matching the summarize.py pattern."""
    from evoscry.ai.copilot import chat_copilot
    from evoscry.ai.local import chat_local
    from evoscry.config import load_config

    config = load_config()

    if config.copilot_token or config.copilot_refresh_token:
        try:
            return await chat_copilot(
                prompt, config.copilot_token, config.copilot_refresh_token
            )
        except Exception:
            pass

    if config.local_model_url:
        return await chat_local(prompt, config.local_model_url, config.local_model_name)

    raise RuntimeError("No AI provider configured for query expansion")
