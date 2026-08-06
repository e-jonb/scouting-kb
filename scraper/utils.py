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
    # Empty lazy-load placeholder images: a bare <svg viewBox="..."></svg> data
    # URI with no shapes/fill, as its own standalone image (not wrapped in a
    # link — those cases can carry a real outer URL and are left alone). The
    # real image swaps in via JS after the page settles, so the scraper only
    # ever sees the empty spacer — found on both merit badge and policy pages
    # (e.g. annual-health-medical-record.md, confirmed 2026-08-02). Only
    # strips SVGs with no content between the tags, so a real inline SVG icon
    # elsewhere wouldn't be affected.
    md = re.sub(r"(?m)^!\[\]\(data:image/svg\+xml,%3Csvg[^)]*%3E%3C/svg%3E\)\s*$\n?", "", md)
    md = _space_glued_emphasis(md)
    return md.strip()


_EMPHASIS_SPAN_RE = re.compile(r"(\*{2,3})([^*\n]+?)\1")


def _space_glued_emphasis(md: str) -> str:
    """
    markdownify sometimes converts two adjacent <strong>/<em> elements (or a
    <strong> tag butted directly against a following plain-text node) from
    the source HTML with no separating whitespace, since the two nodes were
    only visually adjacent in the rendered page, not textually joined in the
    DOM. Left alone this reads as run-together text -- e.g.
    "adult program participant.****Adult volunteers" (two bold spans glued
    into one 4-asterisk run) or "**must**be no more" (bold text glued to the
    next word). Confirmed 2026-08-05 in two-deep-leadership.md, see
    docs/PLAYBOOK.md.

    A bare run of exactly 4 asterisks between two non-space characters is
    unambiguous -- it's always "close one bold span, open the next" -- so
    it's split into two delimiter pairs with a space between first. The
    general case then pads any complete `**text**`/`***text***` span that's
    directly touching a letter or digit on either side, using a
    paired-delimiter match (not raw delimiter runs) so open vs. close is
    unambiguous from the match itself.

    Doesn't handle deeper nested/chained emphasis (e.g. alternating single-
    and triple-asterisk runs from a source `<strong><em>A</em> <em>B</em>
    </strong>`) -- content class excludes `*` so those simply don't match
    and are left as-is rather than risk a wrong edit.
    """
    md = re.sub(r"(?<=\S)\*{4}(?=\S)", "** **", md)

    def _pad(m: re.Match) -> str:
        start, end = m.span()
        pre = md[start - 1] if start > 0 else ""
        post = md[end] if end < len(md) else ""
        text = m.group(0)
        if pre.isalnum():
            text = " " + text
        if post.isalnum():
            text = text + " "
        return text

    return _EMPHASIS_SPAN_RE.sub(_pad, md)


def absolutize_relative_links(md: str, base_url: str = "https://www.scouting.org") -> str:
    """
    Resolve root-relative links/images (`[text](/path)`, `![alt](/path)`) to
    absolute URLs. markdownify preserves an href exactly as written in the
    source HTML — a root-relative link resolves fine in a browser (against
    the page's own origin) but is a dead link in a standalone markdown file
    with no base URL to resolve against. Confirmed 2026-08-02 on 3 policy
    files (13 links total, e.g. guide-to-safe-scouting.md's "VIEW THE ONLINE
    VERSION" pointing at bare `/health-and-safety/gss/toc`) — every one
    resolved to a real page once the domain was prepended, confirming these
    are extraction artifacts, not actually-broken/moved pages.

    Only matches a *single* leading slash, so protocol-relative `//` URLs
    (which need a scheme, not just a domain) and already-absolute `http(s)://`
    URLs are left untouched.
    """
    return re.sub(r"\]\((/[^/][^)]*)\)", lambda m: f"]({base_url}{m.group(1)})", md)


def clean_merit_badge_markdown(md: str, badge_name: str) -> str:
    """
    Strip template boilerplate specific to the merit badge page layout that
    extract_merit_badge_content() picks up as part of the Overview/Requirements
    widgets — none of it is real content:
      - a duplicate "{badge_name}" mini-heading label above each widget
      - the Scoutbook-requirements loading placeholder (with a trailing numeric
        badge ID that only renders because the real content loaded alongside it)
      - "Show More" / "Show Less" toggle links
      - a bare "1." (or "2.", "3.", ...) marker on its own line, immediately
        followed by the requirement text on the next line with no space after
        the period. The source page puts the number and the requirement text
        in visually adjacent but structurally separate elements, and
        markdownify converts that gap into a line break. A "1." with nothing
        after it isn't valid CommonMark ordered-list content — most renderers
        parse it as an empty list item and treat the requirement text as an
        unrelated paragraph below it, exactly the broken-looking rendering
        this was written to fix. Joining them onto one line ("1. Describe...")
        makes it a real, non-empty list item that renders correctly.
    """
    md = re.sub(rf"(?m)^#{{1,6}}\s+{re.escape(badge_name)}\s*$\n?", "", md)
    md = re.sub(
        r"(?m)^The requirements will be fed dynamically using the scout ?book integration\s*\d*\s*$\n?",
        "",
        md,
        flags=re.IGNORECASE,
    )
    md = re.sub(r"(?m)^\[Show (More|Less)\]\(#\)\s*$\n?", "", md)
    md = re.sub(r"(?m)^(\d+)\.\s*\n[ \t]*(?=\S)", r"\1. ", md)
    return clean_markdown(md)  # also strips the empty-SVG placeholder, see clean_markdown()


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


async def extract_merit_badge_content(page) -> str:
    """
    Merit badge pages don't have one single "content" container the way policy
    pages do — the Overview and Requirements sections are two widgets among many
    siblings (Scout Shop product cards, Scouting Magazine article teasers,
    related-badge carousels), and those promotional widgets routinely have MORE
    visible text than the real content. That made extract_content()'s
    longest-innerText heuristic pick the wrong widget on every single merit badge
    page — confirmed 2026-08-01, see docs/PLAYBOOK.md.

    Target the two known widgets directly instead of scoring:
      - Requirements: `.profile-card` — a stable, purpose-named class (not an
        autogenerated Elementor ID), consistent across every badge page tested.
      - Overview: no stable class exists for this widget, so it's located by its
        "Merit Badge Overview" heading text, then a fixed 3-ancestor hop up to
        the flex-child container that holds the heading + paragraph together.

    Returns '' if neither widget is found, so callers can fall back to
    extract_content() for any page that doesn't match this template.
    """
    html = await page.evaluate(
        """() => {
            document.querySelectorAll('script, style, noscript, nav, header, footer, form, button, iframe')
                .forEach((el) => el.remove());

            const parts = [];

            const h2s = Array.from(document.querySelectorAll('h2'));
            const overviewH2 = h2s.find((h) => h.textContent.trim() === 'Merit Badge Overview');
            if (overviewH2) {
                const container = overviewH2.parentElement?.parentElement?.parentElement;
                if (container) parts.push(container.innerHTML);
            }

            const reqEl = document.querySelector('.profile-card');
            if (reqEl) parts.push(reqEl.innerHTML);

            return parts.join('\\n\\n');
        }"""
    )
    return html or ""
