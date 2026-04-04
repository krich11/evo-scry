"""Content extraction from URLs — strips nav/ads, returns text or Markdown."""

from __future__ import annotations

from bs4 import BeautifulSoup

from evoscry.http_client import fetch_url

MAX_CONTENT_BYTES = 50_000  # 50KB per URL


async def extract_content(
    urls: list[str],
    fmt: str = "markdown",
) -> list[dict]:
    """Fetch URLs and extract clean content."""
    import asyncio

    # Validate URLs
    from urllib.parse import urlparse

    for u in urls:
        parsed = urlparse(u)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme} — only http and https are allowed")

    tasks = [_extract_one(u, fmt) for u in urls]
    return await asyncio.gather(*tasks)


async def _extract_one(url: str, fmt: str) -> dict:
    try:
        html = await fetch_url(url)
        soup = BeautifulSoup(html, "lxml")

        # Remove non-content elements
        for tag in soup.select(
            "script, style, nav, header, footer, aside, iframe, noscript, svg, form"
        ):
            tag.decompose()
        for tag in soup.select(
            "[role='navigation'], [role='banner'], [role='contentinfo']"
        ):
            tag.decompose()
        for tag in soup.select(
            ".nav, .menu, .sidebar, .footer, .header, .ad, .advertisement, .cookie-banner"
        ):
            tag.decompose()

        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)
        if not title:
            h1 = soup.select_one("h1")
            if h1:
                title = h1.get_text(strip=True)

        # Find main content area
        content_el = soup.select_one(
            "main, article, [role='main'], .content, .post-content, .entry-content, #content"
        )
        if not content_el:
            content_el = soup.body or soup

        if fmt == "markdown":
            content = _html_to_markdown(content_el)
        else:
            content = content_el.get_text(separator=" ", strip=True)

        # Truncate
        content_bytes = content.encode("utf-8")
        if len(content_bytes) > MAX_CONTENT_BYTES:
            content = content_bytes[:MAX_CONTENT_BYTES].decode("utf-8", errors="ignore")
            content += "\n\n[Content truncated at 50KB]"

        return {
            "url": url,
            "title": title,
            "content": content,
            "byte_length": len(content.encode("utf-8")),
        }
    except Exception as exc:
        return {
            "url": url,
            "title": "",
            "content": "",
            "byte_length": 0,
            "error": str(exc),
        }


def _html_to_markdown(el) -> str:
    """Simple HTML-to-Markdown conversion."""
    lines: list[str] = []

    for child in el.descendants:
        if child.name is None:
            # Text node
            text = child.get_text(strip=True) if hasattr(child, "get_text") else str(child).strip()
            if text:
                lines.append(text)
        elif child.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(child.name[1])
            text = child.get_text(strip=True)
            if text:
                lines.append(f"\n{'#' * level} {text}\n")
        elif child.name == "p":
            text = child.get_text(strip=True)
            if text:
                lines.append(f"\n{text}\n")
        elif child.name in ("ul", "ol"):
            pass  # handled via li
        elif child.name == "li":
            text = child.get_text(strip=True)
            if text:
                lines.append(f"- {text}")
        elif child.name == "a":
            href = child.get("href", "")
            text = child.get_text(strip=True)
            if text and href and href.startswith("http"):
                lines.append(f"[{text}]({href})")
        elif child.name == "code":
            text = child.get_text(strip=True)
            if text:
                lines.append(f"`{text}`")
        elif child.name == "pre":
            text = child.get_text()
            if text:
                lines.append(f"\n```\n{text.strip()}\n```\n")
        elif child.name == "br":
            lines.append("")

    return "\n".join(lines)
