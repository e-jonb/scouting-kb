"""
fetch_merit_badges.py

Scrapes all Scouts BSA merit badge requirements from scouting.org.
Uses Playwright for JS-rendered content.

Output:
  data/merit-badges/index.md       — all badges with eagle-required flag
  data/merit-badges/{slug}.md      — one file per badge (~130+ files)

Usage:
  python fetch_merit_badges.py
  python fetch_merit_badges.py --output data/merit-badges --force
"""

import asyncio
import argparse
from pathlib import Path
from datetime import date

from playwright.async_api import async_playwright, Page
import markdownify
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from utils import (
    slug, bsa_version_from_date, make_frontmatter,
    write_md, rate_limit, clean_markdown, extract_content, make_browser_context
)

console = Console()

BADGES_INDEX_URL = "https://www.scouting.org/skills/merit-badges/all/"
EAGLE_REQUIRED_URL = "https://www.scouting.org/skills/merit-badges/eagle-required/"


def _extract_badge_links(js_result: list) -> list[dict]:
    """Deduplicate badge links by URL, preserving order."""
    seen = set()
    unique = []
    for b in js_result:
        if b["url"] not in seen and b["name"]:
            seen.add(b["url"])
            unique.append(b)
    return unique


_BADGE_LINK_JS = """
    () => {
        // As of 2026, individual badge pages use the new /merit-badges/{slug}/ URL pattern.
        // Nav/category links use the old /skills/merit-badges/ pattern and are excluded.
        const links = document.querySelectorAll('a[href*="/merit-badges/"]');
        const results = [];
        for (const a of links) {
            const href = a.href;
            const name = a.textContent.trim();
            if (
                name && name.length > 5 && name.length < 80 &&
                href.includes('/merit-badges/') &&
                !href.includes('/skills/merit-badges/')
            ) {
                results.push({ name, url: href });
            }
        }
        return results;
    }
"""


async def get_all_badges(page: Page) -> list[dict]:
    """
    Scrape the merit badges index + eagle-required pages.

    As of 2026 BSA redesign:
      - All badges listed alphabetically at /skills/merit-badges/all/
        Each badge is an H2 heading containing an <a href="/merit-badges/{slug}/"> link.
        There are no longer section headings separating Eagle-required from elective.
      - Eagle-required badges listed separately at /skills/merit-badges/eagle-required/
        with the same new /merit-badges/{slug}/ link pattern.

    Strategy: scrape all badges from the index, then get eagle-required slugs from
    the eagle-required page, and mark badges accordingly.
    """
    async def _safe_evaluate(pg, js):
        """Evaluate JS, retrying once if the execution context is destroyed by a redirect."""
        try:
            return await pg.evaluate(js)
        except Exception:
            await pg.wait_for_load_state("networkidle", timeout=30000)
            await pg.wait_for_timeout(1000)
            return await pg.evaluate(js)

    # Step 1: all badges from the main index
    await page.goto(BADGES_INDEX_URL, wait_until="networkidle", timeout=60000)
    await page.wait_for_timeout(2000)
    all_badges = _extract_badge_links(await _safe_evaluate(page, _BADGE_LINK_JS))

    # Step 2: eagle-required badge URLs from the dedicated page
    await page.goto(EAGLE_REQUIRED_URL, wait_until="networkidle", timeout=60000)
    await page.wait_for_timeout(2000)
    eagle_badges = _extract_badge_links(await _safe_evaluate(page, _BADGE_LINK_JS))
    eagle_urls = {b["url"] for b in eagle_badges}

    # Step 3: mark eagle-required
    for b in all_badges:
        b["eagle_required"] = b["url"] in eagle_urls

    return all_badges


async def fetch_merit_badges(
    output_dir: str = "data/merit-badges",
    built_date: str = None,
    bsa_version: str = None,
    force: bool = False,
    cdp_url: str = None,
) -> int:
    """Main entry point. Returns count of badges successfully fetched."""
    today = date.today()
    built_date = built_date or today.isoformat()
    bsa_version = bsa_version or bsa_version_from_date(today)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold blue]Merit Badges[/bold blue] → {output_dir}")

    async with async_playwright() as p:
        browser, context = await make_browser_context(p, cdp_url=cdp_url)
        page = await context.new_page()

        # Step 1: Get badge list from index page
        console.print("  Fetching badge index...")
        badges = await get_all_badges(page)

        if not badges:
            console.print(
                "[red]  ERROR: No badges found. "
                "BSA page structure may have changed — check selectors.[/red]"
            )
            console.print(f"  Verify manually: {BADGES_INDEX_URL}")
            await browser.close()
            return 0

        eagle_count = sum(1 for b in badges if b["eagle_required"])
        console.print(
            f"  Found [green]{len(badges)}[/green] merit badges "
            f"({eagle_count} Eagle-required)"
        )

        # Step 2: Fetch each badge page
        fetched = 0
        skipped = 0
        errors = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("  Fetching...", total=len(badges))

            for badge in badges:
                out_file = output_path / f"{slug(badge['name'])}.md"
                progress.update(task, description=f"  {badge['name'][:45]}")

                if out_file.exists() and not force:
                    skipped += 1
                    progress.advance(task)
                    continue

                try:
                    try:
                        await page.goto(badge["url"], wait_until="networkidle", timeout=60000)
                    except Exception:
                        # Fallback: some pages never reach networkidle (e.g. Skating)
                        await page.goto(badge["url"], wait_until="load", timeout=30000)
                        await page.wait_for_timeout(2000)
                    content_html = await extract_content(page)

                    if not content_html:
                        errors.append(f"No content: {badge['name']}")
                        progress.advance(task)
                        continue

                    md_content = markdownify.markdownify(
                        content_html,
                        heading_style="ATX",
                        strip=["script", "style", "nav", "footer", "header", "form", "button"],
                    )
                    md_content = clean_markdown(md_content)

                    fm = make_frontmatter(
                        badge["url"], built_date, bsa_version,
                        eagle_required=badge["eagle_required"],
                    )
                    full_content = (
                        f"{fm}\n\n"
                        f"# {badge['name']} Merit Badge\n\n"
                        f"{md_content}\n"
                    )
                    write_md(out_file, full_content)
                    fetched += 1

                except Exception as e:
                    errors.append(f"{badge['name']}: {e}")

                progress.advance(task)
                rate_limit(1.5)

        # Step 3: Write index file
        eagle_badges = sorted([b for b in badges if b["eagle_required"]], key=lambda x: x["name"])
        elective_badges = sorted([b for b in badges if not b["eagle_required"]], key=lambda x: x["name"])

        index_lines = [
            make_frontmatter(BADGES_INDEX_URL, built_date, bsa_version),
            "",
            "# Merit Badges Index",
            "",
            f"_As of {bsa_version}. Total: {len(badges)} badges ({len(eagle_badges)} Eagle-required)._",
            "",
            "## Eagle-Required Badges",
            "",
            "| Badge | File |",
            "|---|---|",
        ]
        for b in eagle_badges:
            index_lines.append(f"| {b['name']} | [{slug(b['name'])}.md]({slug(b['name'])}.md) |")

        index_lines += [
            "",
            "## Elective Badges",
            "",
            "| Badge | File |",
            "|---|---|",
        ]
        for b in elective_badges:
            index_lines.append(f"| {b['name']} | [{slug(b['name'])}.md]({slug(b['name'])}.md) |")

        write_md(output_path / "index.md", "\n".join(index_lines) + "\n")

        await browser.close()

    if errors:
        console.print(f"  [yellow]Errors ({len(errors)}):[/yellow]")
        for e in errors:
            console.print(f"    [yellow]- {e}[/yellow]")

    console.print(
        f"  [green]Done:[/green] {fetched} fetched, {skipped} skipped"
        f"{f', {len(errors)} errors' if errors else ''} → {output_dir}"
    )
    return fetched


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch BSA merit badge requirements from scouting.org")
    parser.add_argument("--output", default="data/merit-badges", help="Output directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()
    asyncio.run(fetch_merit_badges(output_dir=args.output, force=args.force))
