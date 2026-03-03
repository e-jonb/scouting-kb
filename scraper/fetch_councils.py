"""
fetch_councils.py

Fetches Scouting America local council data.

Strategy:
  1. Navigate to BSA's council finder page with Playwright
  2. Intercept network responses — look for the JSON API call that powers the widget
  3. If a council data response is captured, parse it directly (clean, structured)
  4. If not, fall back to scraping whatever structured content is on the page

If the auto-detection fails, the script prints instructions for manually
finding the API endpoint via browser DevTools.

Output:
  data/councils/councils.json   — [{id, name, state, city, website, phone, email, ...}]
  data/councils/councils.md     — human-readable table sorted by state

Usage:
  python fetch_councils.py
  python fetch_councils.py --output data/councils --force
"""

import asyncio
import argparse
from pathlib import Path
from datetime import date

from playwright.async_api import async_playwright
from rich.console import Console

from utils import bsa_version_from_date, make_frontmatter, write_md, write_json

console = Console()

COUNCIL_FINDER_URL = "https://www.scouting.org/local-council-finder/"

# Minimum number of records to consider a response "council data"
MIN_COUNCIL_COUNT = 50


def looks_like_council_data(data) -> bool:
    """
    Heuristic: does this JSON response look like it contains council records?
    BSA's API may use various key conventions — we check both the list structure
    and whether records have council-like keys.
    """
    candidate_list = None

    if isinstance(data, list) and len(data) >= MIN_COUNCIL_COUNT:
        candidate_list = data
    elif isinstance(data, dict):
        for key in ("councils", "Councils", "data", "results", "items"):
            if key in data and isinstance(data[key], list) and len(data[key]) >= MIN_COUNCIL_COUNT:
                candidate_list = data[key]
                break

    if candidate_list is None:
        return False

    # Check that first item looks like a council record
    first = candidate_list[0] if candidate_list else {}
    if not isinstance(first, dict):
        return False

    keys = {k.lower() for k in first.keys()}
    council_indicators = {"council", "name", "state", "id", "councilnumber", "councilnum", "website", "phone"}
    return bool(keys & council_indicators)


def extract_council_list(data) -> list[dict]:
    """Extract the flat council list from various API response shapes."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("councils", "Councils", "data", "results", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
    return []


def normalize_council(raw: dict) -> dict:
    """
    Normalize a council record to a consistent schema.
    BSA's API may use camelCase, PascalCase, or snake_case keys.
    """
    def get(*keys):
        for k in keys:
            v = raw.get(k)
            if v is not None and v != "":
                return str(v).strip()
        return None

    return {
        "id": get("id", "ID", "councilId", "council_id", "CouncilId", "councilNum", "CouncilNum", "CouncilNumber"),
        "name": get("name", "Name", "council_name", "CouncilName", "councilName", "title", "Title"),
        "state": get("state", "State", "st", "ST"),
        "city": get("city", "City"),
        "website": get("website", "Website", "url", "URL", "website_url", "WebsiteUrl"),
        "phone": get("phone", "Phone", "phone_number", "PhoneNumber"),
        "email": get("email", "Email"),
        "address": get("address", "Address", "street", "Street"),
        "zip": get("zip", "Zip", "zipcode", "ZipCode", "postal_code"),
    }


async def fetch_councils(
    output_dir: str = "data/councils",
    built_date: str = None,
    bsa_version: str = None,
    force: bool = False,
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

    console.print(f"\n[bold blue]Councils[/bold blue] → {output_dir}")

    captured_councils = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (compatible; scouting-kb/1.0; educational use)"
        )
        page = await context.new_page()

        # Intercept all JSON responses and look for council data
        async def handle_response(response):
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                return
            try:
                data = await response.json()
                if looks_like_council_data(data):
                    council_list = extract_council_list(data)
                    captured_councils.extend(council_list)
                    console.print(
                        f"  [green]Intercepted council data: "
                        f"{len(council_list)} records from:[/green]"
                    )
                    console.print(f"  {response.url[:100]}")
            except Exception:
                pass

        page.on("response", handle_response)

        console.print(f"  Navigating to council finder (waiting for API call)...")
        await page.goto(COUNCIL_FINDER_URL, wait_until="networkidle", timeout=60000)

        # Give the council widget extra time to load its data
        await page.wait_for_timeout(4000)

        if not captured_councils:
            # Try interacting with the page to trigger data loads
            console.print("  No data intercepted yet — trying page interactions...")
            try:
                # Some council finders trigger on search interaction
                search_input = page.locator("input[type='text'], input[type='search']").first
                if await search_input.count() > 0:
                    await search_input.fill("A")
                    await page.wait_for_timeout(2000)
                    await search_input.fill("")
                    await page.wait_for_timeout(2000)
            except Exception:
                pass

        if not captured_councils:
            # Last resort: scrape structured content from the page
            console.print(
                "  [yellow]WARNING: API interception failed. Attempting page scrape.[/yellow]"
            )
            raw = await page.evaluate("""
                () => {
                    const results = [];

                    // Try tables
                    const tables = document.querySelectorAll('table');
                    for (const table of tables) {
                        const rows = table.querySelectorAll('tr');
                        for (const row of rows) {
                            const cells = row.querySelectorAll('td');
                            if (cells.length >= 2) {
                                const name = cells[0]?.textContent?.trim();
                                const state = cells[1]?.textContent?.trim();
                                if (name && name.length > 3 && name.length < 100) {
                                    results.push({ name, state });
                                }
                            }
                        }
                    }

                    // Try links that look like council sites
                    if (results.length < 10) {
                        const links = document.querySelectorAll('a[href*="council"], a[href*="scouting"]');
                        for (const link of links) {
                            const name = link.textContent.trim();
                            if (name && name.length > 5 && name.length < 80) {
                                results.push({ name, website: link.href });
                            }
                        }
                    }

                    return results;
                }
            """)
            captured_councils.extend(raw)

        await browser.close()

    if not captured_councils:
        console.print("\n[red]  ERROR: Could not fetch council data.[/red]")
        console.print("  The BSA widget API endpoint may have changed.")
        console.print("  Manual fallback:")
        console.print(f"    1. Open {COUNCIL_FINDER_URL} in Chrome")
        console.print("    2. Open DevTools → Network → Filter: XHR/Fetch")
        console.print("    3. Look for a request returning 200+ council records")
        console.print("    4. Copy the response JSON to data/councils/councils.json manually")
        console.print("    5. Run: python fetch_councils.py --force")
        return 0

    # Normalize and deduplicate
    normalized = [normalize_council(c) for c in captured_councils]
    normalized = [c for c in normalized if c.get("name")]  # Drop empty records

    # Deduplicate by name
    seen_names = set()
    unique_councils = []
    for c in normalized:
        name_key = (c.get("name") or "").lower()
        if name_key not in seen_names:
            seen_names.add(name_key)
            unique_councils.append(c)

    # Sort by state, then name
    unique_councils.sort(key=lambda c: (c.get("state") or "ZZ", c.get("name") or ""))

    # Write JSON
    write_json(json_file, unique_councils)
    console.print(f"  Wrote {len(unique_councils)} councils → councils.json")

    # Write Markdown table
    fm = make_frontmatter(COUNCIL_FINDER_URL, built_date, bsa_version)
    md_lines = [
        fm, "",
        "# Scouting America Local Councils",
        "",
        f"_As of {bsa_version}. {len(unique_councils)} councils listed by state._",
        "",
        "| ID | Council Name | State | City | Website |",
        "|---|---|---|---|---|",
    ]
    for c in unique_councils:
        cid = c.get("id") or "—"
        name = c.get("name") or "—"
        state = c.get("state") or "—"
        city = c.get("city") or "—"
        site = c.get("website")
        site_col = f"[link]({site})" if site else "—"
        md_lines.append(f"| {cid} | {name} | {state} | {city} | {site_col} |")

    write_md(md_file, "\n".join(md_lines) + "\n")
    console.print(f"  Wrote → councils.md")

    return len(unique_councils)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch BSA local council data")
    parser.add_argument("--output", default="data/councils", help="Output directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()
    asyncio.run(fetch_councils(output_dir=args.output, force=args.force))
