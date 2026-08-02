"""
fetch_councils.py

Fetches Scouting America local council data via the BSA Organizations API.

Strategy:
  The BSA council locator page uses api.scouting.org/organizations/v2/zip/{zip}/council
  to look up the council for a given zip code. This endpoint is open (no auth required).
  We query ~200 representative US zip codes covering every state/territory, deduplicate
  by council number, and collect the full council dataset.

  The "list all councils" endpoint requires a JWT token, so the zip-code approach
  is the practical alternative for *unattended* runs (this is the script
  build_all.py calls automatically). ~200 queries at 0.5s ≈ 2 minutes.

  IMPORTANT (confirmed 2026-08-02): this zip-sampling approach is a sample,
  not a canvas, and it showed — 137 councils found here vs. 228 real ones.
  If you can log into my.scouting.org yourself, prefer
  fetch_councils_authenticated.py instead: it hits the real "list all
  councils" endpoint with your session's JWT and returns the complete,
  authoritative list (at the cost of not being unattended-automatable, and
  not including address/zip/phone/website/email — this script's output has
  those, that one doesn't). See docs/PLAYBOOK.md for the full comparison.

Output:
  data/councils/councils.json   — [{id, name, state, city, address, zip, phone, ...}]
  data/councils/councils.md     — human-readable table sorted by state

Usage:
  python fetch_councils.py --cdp-url http://localhost:9222
  python fetch_councils.py --cdp-url http://localhost:9222 --force
"""

import asyncio
import argparse
from pathlib import Path
from datetime import date

from playwright.async_api import async_playwright
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from utils import bsa_version_from_date, make_frontmatter, write_md, write_json, make_browser_context

console = Console()

COUNCIL_FINDER_URL = "https://www.scouting.org/about/local-council-locator/"
BSA_ORG_API = "https://api.scouting.org/organizations/v2/zip/{zip}/council"

# Representative US zip codes — selected to cover every BSA council territory.
# Includes state capitals, major cities, and rural areas to ensure full coverage.
# ~200 zip codes × 0.5s delay ≈ 2 minutes.
REPRESENTATIVE_ZIPS = [
    # Alabama (2 councils)
    "35203", "36104", "36602",
    # Alaska (1 council)
    "99501", "99701",
    # Arizona (1 council)
    "85001", "85701", "86001",
    # Arkansas (1 council)
    "72201", "72701",
    # California (multiple councils)
    "90001", "94102", "95814", "92101", "94601", "95401",
    "93301", "93501", "93901", "96001", "95501", "91201",
    # Colorado (2 councils)
    "80202", "80901", "81501",
    # Connecticut (1 council)
    "06101", "06901",
    # Delaware (1 council)
    "19901",
    # Florida (multiple councils)
    "32301", "33101", "33601", "32801", "34101", "32401", "32501",
    # Georgia (multiple councils)
    "30301", "31401", "30901", "31701",
    # Hawaii (1 council)
    "96801", "96720",
    # Idaho (1 council)
    "83701", "83401",
    # Illinois (multiple councils)
    "60601", "62701", "61602", "62901", "60901",
    # Indiana (multiple councils)
    "46201", "46801", "47401", "47501",
    # Iowa (1 council)
    "50301", "52401", "51101",
    # Kansas (1 council)
    "66601", "67201",
    # Kentucky (multiple councils)
    "40601", "40201", "40501", "41501",
    # Louisiana (multiple councils)
    "70801", "70112", "71101",
    # Maine (1 council)
    "04101", "04330",
    # Maryland (1 council)
    "21401", "21202", "20601",
    # Massachusetts (1 council)
    "02108", "01103", "02540",
    # Michigan (multiple councils)
    "48226", "48933", "49503", "49801", "48601",
    # Minnesota (1 council)
    "55101", "55401", "55801",
    # Mississippi (1 council)
    "39201", "39401",
    # Missouri (multiple councils)
    "65101", "63101", "64101", "65801",
    # Montana (1 council)
    "59601", "59801", "59401",
    # Nebraska (1 council)
    "68501", "68101",
    # Nevada (1 council)
    "89701", "89101", "89501",
    # New Hampshire (1 council)
    "03301", "03801",
    # New Jersey (multiple councils)
    "08601", "07102", "08701", "07701",
    # New Mexico (1 council)
    "87501", "87101",
    # New York (multiple councils)
    "10001", "12207", "14201", "13201", "12601", "11530", "10901",
    # North Carolina (multiple councils)
    "27601", "28201", "27401", "28801", "28301",
    # North Dakota (1 council)
    "58501", "58201",
    # Ohio (multiple councils)
    "43215", "44101", "45201", "45801", "44701", "43401",
    # Oklahoma (1 council)
    "73101", "74101",
    # Oregon (1 council)
    "97301", "97201", "97401", "97601",
    # Pennsylvania (multiple councils)
    "17101", "19101", "15201", "18503", "16501", "17701",
    # Rhode Island (1 council)
    "02908",
    # South Carolina (1 council)
    "29201", "29401", "29601",
    # South Dakota (1 council)
    "57501", "57101", "57701",
    # Tennessee (multiple councils)
    "37219", "37501", "37902", "37401",
    # Texas (many councils)
    "78701", "77001", "75201", "78201", "79901", "76101",
    "79401", "79701", "78501", "75901", "76801", "78401",
    "77340", "75401", "79901",
    # Utah (1 council)
    "84101", "84401", "84601",
    # Vermont (1 council)
    "05601", "05401",
    # Virginia (multiple councils)
    "23219", "23510", "22201", "24011", "22801",
    # Washington (multiple councils)
    "98501", "98101", "99201", "98201", "98801",
    # West Virginia (1 council)
    "25301", "26101",
    # Wisconsin (multiple councils)
    "53703", "53201", "54601", "54401",
    # Wyoming (1 council)
    "82001", "82601",
    # Washington DC
    "20001", "20002",
    # US Territories
    "00901",  # San Juan, PR
    "96910",  # Guam
    "00801",  # St. Thomas, USVI
]


async def fetch_councils(
    output_dir: str = "data/councils",
    built_date: str = None,
    bsa_version: str = None,
    force: bool = False,
    cdp_url: str = None,
) -> int:
    """Main entry point. Returns count of councils fetched."""
    today = date.today()
    built_date = built_date or today.isoformat()
    bsa_version = bsa_version or bsa_version_from_date(today)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    json_file = output_path / "councils.json"
    md_file = output_path / "councils.md"

    if json_file.exists() and not force:
        import json
        existing = json.loads(json_file.read_text())
        console.print(
            f"\n[bold blue]Councils[/bold blue] → skipped "
            f"({len(existing)} councils already in {output_dir}, use --force to refresh)"
        )
        return len(existing)

    console.print(f"\n[bold blue]Councils[/bold blue] → {output_dir} (BSA Organizations API)")
    console.print(f"  Querying {len(REPRESENTATIVE_ZIPS)} zip codes to discover all councils...")

    raw_councils: dict[str, dict] = {}  # keyed by councilNumber

    async with async_playwright() as p:
        browser, context = await make_browser_context(p, cdp_url=cdp_url)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("  Querying...", total=len(REPRESENTATIVE_ZIPS))

            for zip_code in REPRESENTATIVE_ZIPS:
                progress.update(task, description=f"  zip {zip_code} ({len(raw_councils)} unique councils)")
                url = BSA_ORG_API.format(zip=zip_code)
                try:
                    resp = await context.request.get(url, timeout=10000)
                    if resp.ok:
                        data = await resp.json()
                        cn = data.get("councilNumber")
                        if cn and cn not in raw_councils:
                            raw_councils[cn] = data
                except Exception:
                    pass
                progress.advance(task)
                await asyncio.sleep(0.5)

        await browser.close()

    console.print(f"  Discovered {len(raw_councils)} unique councils from {len(REPRESENTATIVE_ZIPS)} zip queries")

    if not raw_councils:
        console.print("[red]  ERROR: No council data returned. Check network access to api.scouting.org[/red]")
        return 0

    # Normalize to output schema
    councils = []
    for data in raw_councils.values():
        addr = data.get("primaryAddress") or {}
        councils.append({
            "id": data.get("councilNumber"),
            "name": data.get("councilName"),
            "state": addr.get("state"),
            "city": addr.get("city"),
            "address": (addr.get("address1") or "").strip() or None,
            "zip": addr.get("zip"),
            "phone": data.get("phone") or data.get("primaryPhone"),
            "website": data.get("website") or data.get("url"),
            "email": data.get("email"),
        })

    # Sort by state, then name
    councils.sort(key=lambda c: (c.get("state") or "ZZ", c.get("name") or ""))

    # Write JSON
    write_json(json_file, councils)
    console.print(f"  Wrote {len(councils)} councils → councils.json")

    # Write Markdown table
    fm = make_frontmatter(COUNCIL_FINDER_URL, built_date, bsa_version)
    md_lines = [
        fm, "",
        "# Scouting America Local Councils",
        "",
        f"_As of {bsa_version}. {len(councils)} councils listed by state._",
        "_Source: api.scouting.org/organizations/v2/zip/{{zip}}/council_",
        "",
        "| ID | Council Name | State | City | Zip |",
        "|---|---|---|---|---|",
    ]
    for c in councils:
        cid = c.get("id") or "—"
        name = c.get("name") or "—"
        state = c.get("state") or "—"
        city = c.get("city") or "—"
        zipcode = c.get("zip") or "—"
        md_lines.append(f"| {cid} | {name} | {state} | {city} | {zipcode} |")

    write_md(md_file, "\n".join(md_lines) + "\n")
    console.print(f"  Wrote → councils.md")

    return len(councils)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch BSA local council data via BSA Organizations API")
    parser.add_argument("--output", default="data/councils", help="Output directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument(
        "--cdp-url", default=None,
        help="CDP endpoint of a running Chrome instance (e.g. http://localhost:9222)"
    )
    args = parser.parse_args()
    asyncio.run(fetch_councils(output_dir=args.output, force=args.force, cdp_url=args.cdp_url))
