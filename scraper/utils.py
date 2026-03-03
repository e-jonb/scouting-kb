"""
utils.py — Shared utilities for the BSA Knowledge Base scraper.

Used by all fetch_*.py scripts and build_all.py.
"""

import re
import time
import json
from pathlib import Path
from datetime import date
from typing import Optional


def slug(text: str) -> str:
    """Convert text to a URL-safe filename slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def bsa_version_from_date(d: date) -> str:
    """Generate version string like '2026.Q1' from a date."""
    quarter = (d.month - 1) // 3 + 1
    return f"{d.year}.Q{quarter}"


def make_frontmatter(source_url: str, built_date: str, bsa_version: str, **extras) -> str:
    """Generate YAML frontmatter block for a markdown file."""
    lines = ["---"]
    lines.append(f"source: {source_url}")
    lines.append(f"fetched: {built_date}")
    lines.append(f"bsa_version: {bsa_version}")
    for k, v in extras.items():
        if isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, int):
            lines.append(f"{k}: {v}")
        else:
            lines.append(f'{k}: {v}')
    lines.append("---")
    return "\n".join(lines)


def write_md(path: Path, content: str) -> None:
    """Write markdown content to a file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data) -> None:
    """Write JSON data to a file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def rate_limit(seconds: float = 1.5) -> None:
    """Polite delay between requests — be a good citizen to scouting.org."""
    time.sleep(seconds)


def clean_markdown(md: str) -> str:
    """Remove excessive whitespace and normalize markdown output from markdownify."""
    # Collapse 3+ blank lines to 2
    md = re.sub(r"\n{3,}", "\n\n", md)
    # Remove trailing whitespace on each line
    md = re.sub(r"[ \t]+\n", "\n", md)
    # Remove backslash line continuations that markdownify sometimes inserts
    md = re.sub(r"\\\n", "\n", md)
    return md.strip()


# CSS selectors to try for main content extraction, in priority order.
# scouting.org is WordPress-based; these cover the most common content wrappers.
CONTENT_SELECTORS = [
    ".entry-content",
    ".wpb_wrapper",
    ".vc_column-inner",
    "article .content",
    "main article",
    ".page-content",
    ".post-content",
    "article",
    "main",
]


async def extract_content(page, selectors: list[str] = None) -> str:
    """
    Try each selector in order and return the first one that yields substantial content.
    Falls back to <main> if none match.
    """
    selectors = selectors or CONTENT_SELECTORS
    for selector in selectors:
        try:
            el = page.locator(selector).first
            if await el.count() > 0:
                html = await el.inner_html()
                if len(html) > 300:  # Sanity check — not just nav chrome
                    return html
        except Exception:
            continue
    return ""
