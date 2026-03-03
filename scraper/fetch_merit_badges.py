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
    write_md, rate_limit, clean_markdown, extract_content
)

console = Console()

BADGES_INDEX_URL = "https://www.scouting.org/skills/merit-badges/all/"


async def get_all_badges(page: Page) -> list[dict]:
    """
    Scrape the merit badges index page.
    The page groups badges into sections — we detect eagle-required status
    from section headings before each group of badge links.
    Returns list of {name, url, eagle_required}.
    """
    await page.goto(BADGES_INDEX_URL, wait_until="networkidle", timeout=45000)

    badges = await page.evaluate("""
        () => {
            const results = [];
            let currentlyEagleRequired = false;

            // Walk all heading and anchor nodes in document order.
            // Section headers tell us whether following badges are eagle-required.
            const allNodes = document.querySelectorAll('h2, h3, h4, a[href*="/skills/merit-badges/"]');

            for (const node of allNodes) {
                if (/^H[2-4]$/.test(node.tagName)) {
                    const text = node.textContent.toLowerCase();
                    currentlyEagleRequired = (
                        text.includes('eagle') &&
                        (text.includes('required') || text.includes('req'))
                    );
                } else if (node.tagName === 'A') {
                    const href = node.href;
                    const name = node.textContent.trim();
                    // Skip the index page itself, category headers, and nav links
                    if (
                        name &&
                        href &&
                        name.length < 80 &&
                        !href.endsWith('/all/') &&
                        !href.endsWith('/merit-badges/') &&
                        href.includes('/skills/merit-badges/')
                    ) {
                        results.push({ name, url: href, eagle_required: currentlyEagleRequired });
                    }
                }
            }
            return results;
        }
    """)

    # Deduplicate by URL, preserving order
    seen = set()
    unique = []
    for b in badges:
        if b["url"] not in seen and b["name"]:
            seen.add(b["url"])
            unique.append(b)

    return unique


async def fetch_merit_badges(
    output_dir: str = "data/merit-badges",
    built_date: str = None,
    bsa_version: str = None,
    force: bool = False,
) -> int:
    """Main entry point. Returns count of badges successfully fetched."""
    today = date.today()
    built_date = built_date or today.isoformat()
    bsa_version = bsa_version or bsa_version_from_date(today)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold blue]Merit Badges[/bold blue] → {output_dir}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (compatible; scouting-kb/1.0; educational use)"
        )
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
                    await page.goto(badge["url"], wait_until="networkidle", timeout=30000)
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
