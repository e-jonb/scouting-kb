"""
fetch_ranks.py

Downloads and parses Scouts BSA rank requirement PDFs from scouting.org.

BSA publishes rank requirements as PDF files on their WordPress CDN:
  https://www.scouting.org/wp-content/uploads/2025/12/{Rank}.pdf

These are protected by Cloudflare Enterprise and cannot be downloaded with
a plain HTTP client. A CDP-connected Chrome browser (which has Cloudflare
clearance from normal use) is required.

Usage:
  # From build_all.py (recommended):
  python build_all.py --tier 1 --cdp-url http://localhost:9222

  # Standalone:
  python fetch_ranks.py --cdp-url http://localhost:9222
  python fetch_ranks.py --cdp-url http://localhost:9222 --force

CDP setup (one-time per scraping session):
  pkill -x "Google Chrome"
  open -a "Google Chrome" --args --remote-debugging-port=9222 --no-first-run
  # Navigate to https://www.scouting.org in the opened Chrome window, then run.
"""

import asyncio
import argparse
import io
import re
from pathlib import Path
from datetime import date

from playwright.async_api import async_playwright
import pdfplumber
from rich.console import Console

from utils import (
    slug, bsa_version_from_date, make_frontmatter,
    write_md, rate_limit, make_browser_context
)

console = Console()

_BASE = "https://www.scouting.org/wp-content/uploads/2025/12/"

# BSA publishes a single combined PDF with all 7 rank requirements.
# Individual rank PDFs exist for some ranks but naming is inconsistent.
# The combined PDF is the authoritative source — use it as primary, individual as fallback.
COMBINED_PDF_URL = _BASE + "Scouts-BSA-Rank-Requirements.pdf"

RANKS = [
    {
        "name": "Scout",
        "rank_order": 0,
        "pdf_url": _BASE + "Scout-Rank.pdf",
        "section_pattern": r"SCOUT RANK",
        "description": "The entry rank. Focuses on basic Scouting knowledge and the Scout Oath and Law.",
    },
    {
        "name": "Tenderfoot",
        "rank_order": 1,
        "pdf_url": _BASE + "Tenderfoot-Rank.pdf",
        "section_pattern": r"TENDERFOOT RANK",
        "description": "First advancement rank. Introduces camping, first aid, and Scout skills.",
    },
    {
        "name": "Second Class",
        "rank_order": 2,
        "pdf_url": _BASE + "Second-Class-v2.pdf",
        "section_pattern": r"SECOND CLASS RANK",
        "description": "Builds outdoor and survival skills, including navigation and cooking.",
    },
    {
        "name": "First Class",
        "rank_order": 3,
        "pdf_url": _BASE + "First-Class.pdf",
        "section_pattern": r"FIRST CLASS RANK",
        "description": "Full Scouting skills — considered a fully capable Scout.",
    },
    {
        "name": "Star",
        "rank_order": 4,
        "pdf_url": _BASE + "Star-Rank.pdf",
        "section_pattern": r"STAR RANK",
        "description": "Leadership and merit badge focus begins. Requires 6 merit badges (4 Eagle-required).",
    },
    {
        "name": "Life",
        "rank_order": 5,
        "pdf_url": _BASE + "Life-Rank.pdf",
        "section_pattern": r"LIFE RANK",
        "description": "Advanced leadership and service. Requires 11 merit badges (7 Eagle-required).",
    },
    {
        "name": "Eagle Scout",
        "rank_order": 6,
        "pdf_url": None,  # No confirmed individual PDF — use combined
        "section_pattern": r"EAGLE SCOUT RANK",
        "description": "Highest rank. Requires 21 merit badges, demonstrated leadership, and an Eagle project.",
    },
]

RANKS_INDEX_URL = "https://www.scouting.org/programs/scouts-bsa/advancement-and-awards/"


async def download_pdf(page, url: str) -> bytes | None:
    """
    Download a PDF by running fetch() inside the browser page.

    context.request.get() does not reliably pass Cloudflare clearance to the
    scouting.org CDN. Running fetch() from inside the page uses the full browser
    session (cookies, TLS fingerprint, etc.) and bypasses this limitation.
    Returns raw bytes on success, None on failure.
    """
    try:
        data = await page.evaluate(
            """async (url) => {
                const resp = await fetch(url, {credentials: 'include'});
                if (!resp.ok) return null;
                const buf = await resp.arrayBuffer();
                return Array.from(new Uint8Array(buf));
            }""",
            url,
        )
        if data:
            return bytes(data)
    except Exception as e:
        console.print(f"    [yellow]fetch error: {e}[/yellow]")
    return None


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF and return as a cleaned string."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page_texts = []
        for p in pdf.pages:
            text = p.extract_text(x_tolerance=2, y_tolerance=2)
            if text and text.strip():
                page_texts.append(text.strip())

    raw = "\n\n".join(page_texts)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    raw = re.sub(r"[ \t]+\n", "\n", raw)
    return raw.strip()


def split_combined_pdf(full_text: str) -> dict[str, str]:
    """
    Split the combined ranks PDF text into per-rank sections.
    Returns {rank_name: section_text} for each rank found.

    BSA's combined PDF uses "RANK NAME REQUIREMENTS" as section headers in all-caps.
    """
    # Find all section start positions
    patterns = {
        "Scout": re.compile(r"^SCOUT RANK", re.MULTILINE),
        "Tenderfoot": re.compile(r"^TENDERFOOT RANK", re.MULTILINE),
        "Second Class": re.compile(r"^SECOND CLASS RANK", re.MULTILINE),
        "First Class": re.compile(r"^FIRST CLASS RANK", re.MULTILINE),
        "Star": re.compile(r"^STAR RANK", re.MULTILINE),
        "Life": re.compile(r"^LIFE RANK", re.MULTILINE),
        "Eagle Scout": re.compile(r"^EAGLE RANK", re.MULTILINE),
    }

    # Find match positions
    positions = []
    for rank_name, pat in patterns.items():
        m = pat.search(full_text)
        if m:
            positions.append((m.start(), rank_name))

    if not positions:
        return {}

    positions.sort()

    # Extract each section as text between consecutive markers
    sections = {}
    for i, (start, rank_name) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(full_text)
        sections[rank_name] = full_text[start:end].strip()

    return sections


async def fetch_ranks(
    output_dir: str = "data/ranks",
    built_date: str = None,
    bsa_version: str = None,
    force: bool = False,
    cdp_url: str = None,
) -> int:
    """Main entry point. Returns count of ranks successfully fetched."""
    today = date.today()
    built_date = built_date or today.isoformat()
    bsa_version = bsa_version or bsa_version_from_date(today)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    if not cdp_url:
        console.print(
            "\n[bold red]Ranks[/bold red]: [red]--cdp-url required.[/red]\n"
            "  scouting.org Cloudflare Enterprise blocks all automated downloads.\n"
            "  Setup:\n"
            "    pkill -x 'Google Chrome'\n"
            "    open -a 'Google Chrome' --args --remote-debugging-port=9222 --no-first-run\n"
            "    # Navigate to https://www.scouting.org, then re-run:\n"
            "    python build_all.py --tier 1 --cdp-url http://localhost:9222"
        )
        return 0

    console.print(f"\n[bold blue]Ranks[/bold blue] → {output_dir} (PDF via CDP)")

    async with async_playwright() as p:
        browser, context = await make_browser_context(p, cdp_url=cdp_url)
        # Use a page (not context.request) so fetch() runs inside the real browser
        # session, inheriting Cloudflare clearance from the connected Chrome.
        page = await context.new_page()
        # Warm up the session on scouting.org to ensure Cloudflare clearance is active.
        await page.goto(RANKS_INDEX_URL, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(1000)

        fetched = 0
        errors = []

        # Step 1: Download combined PDF and pre-split into sections.
        # This gives us all 7 ranks in one download, including any without
        # individual PDF URLs (Second Class, Eagle Scout as of 2026.Q1).
        console.print(f"  Downloading combined ranks PDF...")
        combined_bytes = await download_pdf(page, COMBINED_PDF_URL)
        combined_sections: dict[str, str] = {}
        if combined_bytes:
            full_text = extract_pdf_text(combined_bytes)
            combined_sections = split_combined_pdf(full_text)
            console.print(
                f"  Combined PDF: {len(combined_bytes):,} bytes, "
                f"{len(combined_sections)}/7 rank sections found"
            )
            if combined_sections:
                console.print(f"    Sections: {list(combined_sections.keys())}")
        else:
            console.print("  [yellow]Combined PDF download failed — will try individual PDFs only[/yellow]")

        for rank in RANKS:
            out_file = output_path / f"{slug(rank['name'])}.md"
            console.print(
                f"  [{rank['rank_order'] + 1}/{len(RANKS)}] {rank['name']}...", end=" "
            )

            if out_file.exists() and not force:
                console.print("[yellow]skipped (exists)[/yellow]")
                fetched += 1
                continue

            md_content = None
            source_url = COMBINED_PDF_URL

            # Prefer: section from combined PDF
            if rank["name"] in combined_sections:
                md_content = combined_sections[rank["name"]]

            # Fallback: individual PDF (if URL is available)
            elif rank.get("pdf_url"):
                source_url = rank["pdf_url"]
                pdf_bytes = await download_pdf(page, rank["pdf_url"])
                if pdf_bytes:
                    md_content = extract_pdf_text(pdf_bytes)
                    rate_limit(1.0)

            if not md_content:
                console.print("[red]ERROR: no content (combined split missed + no individual PDF)[/red]")
                errors.append(rank["name"])
                continue

            try:
                fm = make_frontmatter(
                    source_url, built_date, bsa_version,
                    rank_order=rank["rank_order"],
                    content_type="pdf",
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
                console.print(f"[red]parse error: {e}[/red]")
                errors.append(f"{rank['name']}: {e}")

        # Write index
        index_lines = [
            make_frontmatter(RANKS_INDEX_URL, built_date, bsa_version),
            "",
            "# Scouts BSA Ranks",
            "",
            (
                f"_As of {bsa_version}. Listed in advancement order. "
                "Requirements sourced from official BSA PDFs._"
            ),
            "",
            "| # | Rank | Description | File |",
            "|---|---|---|---|",
        ]
        for rank in RANKS:
            index_lines.append(
                f"| {rank['rank_order'] + 1} | {rank['name']} | {rank['description']} "
                f"| [{slug(rank['name'])}.md]({slug(rank['name'])}.md) |"
            )
        write_md(output_path / "index.md", "\n".join(index_lines) + "\n")

        if errors:
            console.print(f"  [yellow]Failed ({len(errors)}): {', '.join(errors)}[/yellow]")
            console.print(
                "  [yellow]Update RANKS pdf_url entries in fetch_ranks.py for any 404s.[/yellow]"
            )

        console.print(
            f"  [green]Done:[/green] {fetched}/{len(RANKS)} ranks fetched → {output_dir}"
        )

        await browser.close()

    return fetched


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch BSA rank requirements from official PDFs via CDP-connected Chrome"
    )
    parser.add_argument("--output", default="data/ranks", help="Output directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument(
        "--cdp-url", default=None,
        help="CDP endpoint of a running Chrome instance (e.g. http://localhost:9222)"
    )
    args = parser.parse_args()
    asyncio.run(fetch_ranks(output_dir=args.output, force=args.force, cdp_url=args.cdp_url))
