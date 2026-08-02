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
# scouting.org uses both WordPress classic themes and Elementor page builder.
CONTENT_SELECTORS = [
    # WordPress classic / WPBakery (merit badges, ranks)
    ".entry-content",
    ".wpb_wrapper",
    ".vc_column-inner",
    "article .content",
    ".page-content",
    ".post-content",
    # Elementor (policy / health-and-safety pages)
    ".elementor-widget-wrap.elementor-element-populated",
    ".elementor-section.elementor-top-section",
    ".elementor-widget-wrap",
    # Generic fallbacks
    "main article",
    "article",
    "main",
]


# Realistic Chrome/Mac user agent — avoids Cloudflare bot detection triggered
# by the previous "scouting-kb/1.0" custom agent.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


async def make_browser_context(playwright, cdp_url: str = None):
    """
    Return (browser, context) for scraping.

    Two modes:
      CDP mode (cdp_url set): connects to a user-launched Chrome via Chrome DevTools
        Protocol. The browser already has Cloudflare clearance from normal use.
        browser.close() is patched to browser.disconnect() so the user's Chrome
        stays open after the scraper finishes.

      Headless mode (default): launches Playwright's own Chromium. Works for sites
        without aggressive bot detection. scouting.org Cloudflare Enterprise will
        block this — use CDP mode for that site.

    CDP setup (one-time):
      pkill -x "Google Chrome"
      open -a "Google Chrome" --args --remote-debugging-port=9222 --no-first-run
      # Navigate to scouting.org once in that Chrome window, then run the scraper.
      python build_all.py --cdp-url http://localhost:9222
    """
    if cdp_url:
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        # Use the first existing browser context (has Cloudflare clearance cookies)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        # Replace close() with a no-op so we don't shut down the user's Chrome.
        # Playwright drops the CDP websocket when the async_playwright context exits.
        async def _noop():
            pass
        browser.close = _noop
        return browser, context

    # Headless fallback — blocked by Cloudflare Enterprise on scouting.org
    browser = await playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ],
    )
    context = await browser.new_context(
        user_agent=BROWSER_UA,
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        timezone_id="America/New_York",
    )
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return browser, context


async def extract_content(page, selectors: list[str] = None) -> str:
    """
    For each selector, find the element with the most visible text and return
    its innerHTML. Skips navigation/header chrome that has lots of markup but
    little readable text (common on Elementor pages where the nav widget matches
    the same selector as the content widget).

    Falls back to the next selector if none yield 200+ chars of visible text.
    """
    selectors = selectors or CONTENT_SELECTORS
    html = await page.evaluate(
        """(selectors) => {
            // Remove nav/header/footer/script chrome from the whole document first.
            // markdownify's strip=[...] only unwraps these tags (keeps their text/JS
            // as plain text) rather than removing them, so any nav or inline <script>
            // left inside whichever container gets selected below leaks into the
            // final markdown. Deleting them here — before scoring candidates — means
            // a stray nav/header can neither win the best-match comparison nor
            // contribute leftover text/code if it does.
            document.querySelectorAll('script, style, noscript, nav, header, footer, form, button, iframe')
                .forEach((el) => el.remove());

            for (const sel of selectors) {
                let bestEl = null, bestLen = 0;
                for (const el of document.querySelectorAll(sel)) {
                    const len = (el.innerText || '').trim().length;
                    if (len > bestLen) { bestLen = len; bestEl = el; }
                }
                if (bestEl && bestLen > 200) return bestEl.innerHTML;
            }
            return '';
        }""",
        selectors,
    )
    return html or ""
