"""
fetch_ranks.py

Scrapes Scouts BSA rank requirements from scouting.org.
Ranks are fixed and known — no index scraping needed.

Output:
  data/ranks/index.md      — all ranks in advancement order
  data/ranks/{slug}.md     — one file per rank (7 total)

Usage:
  python fetch_ranks.py
  python fetch_ranks.py --output data/ranks --force
"""

import asyncio
import argparse
from pathlib import Path
from datetime import date

from playwright.async_api import async_playwright
import markdownify
from rich.console import Console

from utils import (
    slug, bsa_version_from_date, make_frontmatter,
    write_md, rate_limit, clean_markdown, extract_content
)

console = Console()

# Rank pages in advancement order. URLs are stable BSA program pages.
RANKS = [
    {
        "name": "Scout",
        "url": "https://www.scouting.org/programs/scouts-bsa/advancement-and-awards/ranks/scout/",
        "description": "The entry rank. Focuses on basic Scouting knowledge and the Scout Oath and Law.",
    },
    {
        "name": "Tenderfoot",
        "url": "https://www.scouting.org/programs/scouts-bsa/advancement-and-awards/ranks/tenderfoot/",
        "description": "First advancement rank. Introduces camping, first aid, and Scout skills.",
    },
    {
        "name": "Second Class",
        "url": "https://www.scouting.org/programs/scouts-bsa/advancement-and-awards/ranks/second-class/",
        "description": "Builds outdoor and survival skills, including navigation and cooking.",
    },
    {
        "name": "First Class",
        "url": "https://www.scouting.org/programs/scouts-bsa/advancement-and-awards/ranks/first-class/",
        "description": "Full Scouting skills — considered a fully capable Scout.",
    },
    {
        "name": "Star",
        "url": "https://www.scouting.org/programs/scouts-bsa/advancement-and-awards/ranks/star/",
        "description": "Leadership and merit badge focus begins. Requires 6 merit badges (4 Eagle-required).",
    },
    {
        "name": "Life",
        "url": "https://www.scouting.org/programs/scouts-bsa/advancement-and-awards/ranks/life/",
        "description": "Advanced leadership and service. Requires 11 merit badges (7 Eagle-required).",
    },
    {
        "name": "Eagle Scout",
        "url": "https://www.scouting.org/programs/scouts-bsa/advancement-and-awards/ranks/eagle-scout/",
        "description": "Highest rank. Requires 21 merit badges, demonstrated leadership, and an Eagle project.",
    },
]

RANKS_INDEX_URL = "https://www.scouting.org/programs/scouts-bsa/advancement-and-awards/"


async def fetch_ranks(
    output_dir: str = "data/ranks",
    built_date: str = None,
    bsa_version: str = None,
    force: bool = False,
) -> int:
    """Main entry point. Returns count of ranks successfully fetched."""
    today = date.today()
    built_date = built_date or today.isoformat()
    bsa_version = bsa_version or bsa_version_from_date(today)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold blue]Ranks[/bold blue] → {output_dir}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (compatible; scouting-kb/1.0; educational use)"
        )
        page = await context.new_page()

        fetched = 0
        for i, rank in enumerate(RANKS):
            out_file = output_path / f"{slug(rank['name'])}.md"
            console.print(f"  [{i+1}/{len(RANKS)}] {rank['name']}...", end=" ")

            if out_file.exists() and not force:
                console.print("[yellow]skipped (exists)[/yellow]")
                continue

            try:
                await page.goto(rank["url"], wait_until="networkidle", timeout=30000)
                content_html = await extract_content(page)

                if not content_html:
                    console.print(f"[red]ERROR: no content found[/red]")
                    console.print(f"    Check manually: {rank['url']}")
                    continue

                md_content = markdownify.markdownify(
                    content_html,
                    heading_style="ATX",
                    strip=["script", "style", "nav", "footer", "header", "form", "button"],
                )
                md_content = clean_markdown(md_content)

                fm = make_frontmatter(
                    rank["url"], built_date, bsa_version,
                    rank_order=i,
                )
                full_content = (
                    f"{fm}\n\n"
                    f"# {rank['name']} Rank Requirements\n\n"
                    f"_{rank['description']}_\n\n"
                    f"{md_content}\n"
                )
                write_md(out_file, full_content)
                fetched += 1
                console.print("[green]done[/green]")

            except Exception as e:
                console.print(f"[red]ERROR: {e}[/red]")

            if i < len(RANKS) - 1:
                rate_limit(1.5)

        # Write index file
        index_lines = [
            make_frontmatter(RANKS_INDEX_URL, built_date, bsa_version),
            "",
            "# Scouts BSA Ranks",
            "",
            f"_As of {bsa_version}. Listed in advancement order._",
            "",
            "| # | Rank | Description | File |",
            "|---|---|---|---|",
        ]
        for i, rank in enumerate(RANKS):
            index_lines.append(
                f"| {i+1} | {rank['name']} | {rank['description']} "
                f"| [{slug(rank['name'])}.md]({slug(rank['name'])}.md) |"
            )

        write_md(output_path / "index.md", "\n".join(index_lines) + "\n")

        await browser.close()

    console.print(f"  [green]Done:[/green] {fetched}/{len(RANKS)} ranks fetched → {output_dir}")
    return fetched


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch BSA rank requirements from scouting.org")
    parser.add_argument("--output", default="data/ranks", help="Output directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()
    asyncio.run(fetch_ranks(output_dir=args.output, force=args.force))
