"""AI-powered summarization of search results."""

from __future__ import annotations

from evoscry.ai.copilot import chat_copilot
from evoscry.ai.local import chat_local
from evoscry.config import load_config


async def summarize_results(query: str, results: list[dict]) -> str | None:
    """Summarize top search results using AI. Returns None if AI unavailable."""
    top = results[:5]
    if not top:
        return None

    context = "\n\n".join(
        f"{i+1}. [{r['title']}]({r['url']})\n   {r.get('snippet', '')}"
        for i, r in enumerate(top)
    )
    prompt = (
        f'Summarize the following search results for the query "{query}". '
        "Provide a concise 2-3 sentence overview of what the results indicate. "
        "Do not include any URLs or links in the summary.\n\n"
        f"Results:\n{context}"
    )

    try:
        return await _chat_with_ai(prompt)
    except Exception:
        return None


async def _chat_with_ai(prompt: str) -> str:
    config = load_config()

    # Try Copilot first
    if config.copilot_token or config.copilot_refresh_token:
        try:
            return await chat_copilot(
                prompt,
                config.copilot_token,
                config.copilot_refresh_token,
            )
        except Exception:
            pass

    # Try local model
    if config.local_model_url:
        return await chat_local(prompt, config.local_model_url, config.local_model_name)

    raise RuntimeError("No AI provider configured")
