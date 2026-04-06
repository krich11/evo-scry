"""Content extraction from URLs — strips nav/ads, returns text or Markdown.

Supports HTML pages, PDF documents (via pymupdf), and GitHub URLs
(auto-transforms blob/tree URLs for direct content access).
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from evoscry.http_client import fetch_url, fetch_with_config

MAX_CONTENT_BYTES = 50_000  # 50KB per URL
MAX_PDF_BYTES = 10 * 1024 * 1024  # 10MB

_GITHUB_BLOB_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+)/blob/(.+)$"
)
_GITHUB_TREE_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+)/tree/(.+)$"
)


def _detect_content_type(url: str) -> str:
    """Classify URL into a content-type hint before fetching."""
    parsed = urlparse(url)
    path_lower = (parsed.path or "").lower()

    if path_lower.endswith(".pdf"):
        return "pdf"
    if parsed.hostname == "raw.githubusercontent.com":
        return "github_file"
    if _GITHUB_BLOB_RE.match(url):
        return "github_file"
    if _GITHUB_TREE_RE.match(url):
        return "github_directory"
    return "html"


async def extract_content(
    urls: list[str],
    fmt: str = "markdown",
) -> list[dict]:
    """Fetch URLs and extract clean content."""
    import asyncio

    for u in urls:
        parsed = urlparse(u)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme} — only http and https are allowed")

    tasks = [_extract_one(u, fmt) for u in urls]
    return await asyncio.gather(*tasks)


async def _extract_one(url: str, fmt: str) -> dict:
    content_type = _detect_content_type(url)

    try:
        if content_type == "pdf":
            return await _extract_pdf(url)
        if content_type == "github_file":
            return await _extract_github_file(url)
        if content_type == "github_directory":
            return await _extract_github_directory(url)
        return await _extract_html(url, fmt)
    except Exception as exc:
        return {
            "url": url,
            "title": "",
            "content": "",
            "byte_length": 0,
            "content_type": content_type,
            "error": str(exc),
        }


# ── HTML extraction (original pipeline) ─────────────────────────────────────

async def _extract_html(url: str, fmt: str) -> dict:
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

    content_el = soup.select_one(
        "main, article, [role='main'], .content, .post-content, .entry-content, #content"
    )
    if not content_el:
        content_el = soup.body or soup

    if fmt == "markdown":
        content = _html_to_markdown(content_el)
    else:
        content = content_el.get_text(separator=" ", strip=True)

    content = _truncate(content)

    return {
        "url": url,
        "title": title,
        "content": content,
        "byte_length": len(content.encode("utf-8")),
        "content_type": "html",
    }


# ── PDF extraction ───────────────────────────────────────────────────────────

async def _extract_pdf(url: str) -> dict:
    try:
        import pymupdf  # noqa: F811
    except ImportError:
        return {
            "url": url,
            "title": "",
            "content": "PDF extraction requires pymupdf. Install with: pip install pymupdf",
            "byte_length": 0,
            "content_type": "pdf",
            "error": "pymupdf not installed",
        }

    import httpx
    from evoscry.config import load_config

    config = load_config()
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=30.0, proxy=config.proxy_url
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    if len(resp.content) > MAX_PDF_BYTES:
        return {
            "url": url,
            "title": "",
            "content": "",
            "byte_length": 0,
            "content_type": "pdf",
            "error": f"PDF exceeds {MAX_PDF_BYTES // (1024*1024)}MB limit",
        }

    doc = pymupdf.open(stream=resp.content, filetype="pdf")
    title = (doc.metadata or {}).get("title", "") or ""

    pages_text: list[str] = []
    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        if text.strip():
            pages_text.append(f"--- Page {page_num + 1} ---\n{text.strip()}")
    doc.close()

    content = _truncate("\n\n".join(pages_text))

    return {
        "url": url,
        "title": title,
        "content": content,
        "byte_length": len(content.encode("utf-8")),
        "content_type": "pdf",
    }


# ── GitHub file extraction ───────────────────────────────────────────────────

async def _extract_github_file(url: str) -> dict:
    parsed = urlparse(url)

    # Already a raw URL
    if parsed.hostname == "raw.githubusercontent.com":
        raw_url = url
        filename = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    else:
        match = _GITHUB_BLOB_RE.match(url)
        if not match:
            return await _extract_html(url, "markdown")
        owner, repo, path = match.group(1), match.group(2), match.group(3)
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{path}"
        filename = path.rsplit("/", 1)[-1]

    content = await fetch_url(raw_url)
    content = _truncate(content)

    return {
        "url": url,
        "title": filename,
        "content": content,
        "byte_length": len(content.encode("utf-8")),
        "content_type": "github_file",
    }


# ── GitHub directory listing ─────────────────────────────────────────────────

async def _extract_github_directory(url: str) -> dict:
    match = _GITHUB_TREE_RE.match(url)
    if not match:
        return await _extract_html(url, "markdown")

    owner, repo, path = match.group(1), match.group(2), match.group(3)

    # First path component is the ref (branch/tag)
    parts = path.split("/", 1)
    ref = parts[0]
    dir_path = parts[1] if len(parts) > 1 else ""

    import httpx

    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{dir_path}?ref={ref}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            api_url,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        resp.raise_for_status()

    entries = resp.json()
    if not isinstance(entries, list):
        return {
            "url": url,
            "title": f"{owner}/{repo}/{dir_path or '/'}",
            "content": "Not a directory listing.",
            "byte_length": 0,
            "content_type": "github_directory",
            "error": "GitHub API did not return a directory listing",
        }

    lines: list[str] = []
    for entry in entries:
        suffix = "/" if entry.get("type") == "dir" else ""
        size = f" ({entry.get('size', 0)} bytes)" if entry.get("type") == "file" else ""
        lines.append(f"  {entry['name']}{suffix}{size}")

    content = f"Directory: {owner}/{repo}/{dir_path}\n\n" + "\n".join(lines)

    return {
        "url": url,
        "title": f"{owner}/{repo}/{dir_path or '/'}",
        "content": content,
        "byte_length": len(content.encode("utf-8")),
        "content_type": "github_directory",
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _truncate(content: str) -> str:
    """Truncate to MAX_CONTENT_BYTES."""
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > MAX_CONTENT_BYTES:
        content = content_bytes[:MAX_CONTENT_BYTES].decode("utf-8", errors="ignore")
        content += "\n\n[Content truncated at 50KB]"
    return content


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
