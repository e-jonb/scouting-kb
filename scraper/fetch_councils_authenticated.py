"""
fetch_councils_authenticated.py

Fetches the COMPLETE, authoritative Scouting America local council list via
api.scouting.org/organizations/councils — the "list all councils" endpoint
that fetch_councils.py's docstring already noted requires a JWT token.

Unlike every other fetch_*.py script in this repo, this one CANNOT run
unattended: the JWT only exists after a human logs into my.scouting.org.
It is NOT wired into build_all.py's automated tier flow — run it manually,
separately, whenever a council refresh is needed.

Why this exists (confirmed 2026-08-02): fetch_councils.py's zip-sampling
approach (~200 representative zips against the public, unauthenticated
per-zip lookup endpoint) is fundamentally a *sample*, not a canvas. A full
council-list pull found 228 real local councils against fetch_councils.py's
137 — a 91-council gap — plus 2 councils in the old data (South Plains #694,
Black Hills Area #695) that no longer exist at all (merged/dissolved), and
at least 2 renames (Golden Empire -> Greater California #047, Andrew Jackson
-> Mississippi Riverlands #303) that a zip re-sample wouldn't reliably catch
either, since a zip code that used to resolve to the old name still resolves
to *a* council — just not necessarily flagging that the name changed.
See docs/PLAYBOOK.md for the full incident writeup.

Setup (do this before running):
  1. Launch a CDP-connected Chrome the normal way for this repo:
       pkill -x "Google Chrome"
       "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \\
         --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-cdp-scraper --no-first-run &
  2. In that Chrome window, log into https://my.scouting.org yourself.
  3. Navigate to https://my.scouting.org/tools/manage-member-id (any page that
     loads the council-search dropdown will do — that's what triggers the
     browser's own JS to fetch /organizations/councils with a valid
     Authorization: Bearer <JWT> header; a plain fetch() with credentials:
     'include' is NOT enough, the JWT lives in the app's JS state/storage
     and gets attached by its own fetch wrapper, not via cookies).
  4. Run this script pointed at that CDP session.

Output:
  data/councils/councils.json   — [{id, name, state, city, address, zip, phone, ...}]
  data/councils/councils.md     — human-readable table sorted by state

  Same schema as fetch_councils.py's output, but address/zip/phone/website/
  email are null for every record — /organizations/councils doesn't return
  them, only id/name/city/state. (A future improvement could cross-reference
  fetch_councils.py's per-council zip lookups to backfill those fields for
  councils this endpoint newly reveals, but that wasn't done here — the user
  explicitly chose a clean rebuild over a partial merge, see docs/PLAYBOOK.md.)

Usage:
  python fetch_councils_authenticated.py --cdp-url http://localhost:9222
"""

import argparse
import asyncio
import re
from datetime import date
from pathlib import Path

from playwright.async_api import async_playwright, Page
from rich.console import Console

from utils import bsa_version_from_date, make_frontmatter, write_json, write_md

console = Console()

COUNCILS_API = "https://api.scouting.org/organizations/councils"
TRIGGER_URL = "https://my.scouting.org/tools/manage-member-id"

# api.scouting.org's bulk endpoint returns 2-letter USPS codes; the existing
# per-zip endpoint (and this repo's committed data) uses full uppercase
# names, so map for consistency with what's already in data/councils/.
STATE_NAMES = {
    "AL": "ALABAMA", "AK": "ALASKA", "AZ": "ARIZONA", "AR": "ARKANSAS", "CA": "CALIFORNIA",
    "CO": "COLORADO", "CT": "CONNECTICUT", "DE": "DELAWARE", "FL": "FLORIDA", "GA": "GEORGIA",
    "HI": "HAWAII", "ID": "IDAHO", "IL": "ILLINOIS", "IN": "INDIANA", "IA": "IOWA",
    "KS": "KANSAS", "KY": "KENTUCKY", "LA": "LOUISIANA", "ME": "MAINE", "MD": "MARYLAND",
    "MA": "MASSACHUSETTS", "MI": "MICHIGAN", "MN": "MINNESOTA", "MS": "MISSISSIPPI",
    "MO": "MISSOURI", "MT": "MONTANA", "NE": "NEBRASKA", "NV": "NEVADA", "NH": "NEW HAMPSHIRE",
    "NJ": "NEW JERSEY", "NM": "NEW MEXICO", "NY": "NEW YORK", "NC": "NORTH CAROLINA",
    "ND": "NORTH DAKOTA", "OH": "OHIO", "OK": "OKLAHOMA", "OR": "OREGON", "PA": "PENNSYLVANIA",
    "RI": "RHODE ISLAND", "SC": "SOUTH CAROLINA", "SD": "SOUTH DAKOTA", "TN": "TENNESSEE",
    "TX": "TEXAS", "UT": "UTAH", "VT": "VERMONT", "VA": "VIRGINIA", "WA": "WASHINGTON",
    "WV": "WEST VIRGINIA", "WI": "WISCONSIN", "WY": "WYOMING", "DC": "DISTRICT OF COLUMBIA",
    "PR": "PUERTO RICO", "GU": "GUAM", "VI": "VIRGIN ISLANDS", "AS": "AMERICAN SAMOA",
    "MP": "NORTHERN MARIANA ISLANDS", "AE": "ARMED FORCES EUROPE",
}


def clean_council_name(raw_name: str) -> tuple[str | None, str]:
    """
    Split a raw "Foo Bar Council 123" name into (council_number, clean_name).

    Loops the strip-trailing-number / strip-trailing-"Council"(-BSA) passes
    to a fixed point rather than doing one pass each: at least one real
    record ("Hoosier Trails Council #145 145") has a doubled trailing
    number — a data-entry quirk in BSA's own system, confirmed 2026-08-02.
    A single pass leaves "...Council #145" dangling (the redundant "#145"
    is no longer at the string's end after the outer " 145" is stripped, so
    the "Council" suffix regex can't reach past it); looping strips it as a
    second trailing number, and only then does "Council" become trailing.
    """
    num_match = re.search(r"\s*#?(\d{2,4})\s*$", raw_name)
    num = num_match.group(1).zfill(3) if num_match else None

    base = raw_name
    for _ in range(4):
        new_base = re.sub(r"\s*#?\d+\s*$", "", base).strip()
        new_base = re.sub(r",?\s*Councils?(,?\s*-?\s*BSA)?\s*$", "", new_base, flags=re.IGNORECASE).strip()
        new_base = re.sub(r"[,\-]\s*$", "", new_base).strip()
        if new_base == base:
            break
        base = new_base
    return num, base


async def fetch_councils_authenticated(
    output_dir: str = "data/councils",
    built_date: str = None,
    bsa_version: str = None,
    cdp_url: str = None,
) -> int:
    """Main entry point. Returns count of councils fetched, or 0 on failure."""
    if not cdp_url:
        console.print(
            "[red]  ERROR: --cdp-url required — this script needs your "
            "already-logged-in my.scouting.org session.[/red]\n"
            "  See this file's module docstring for setup steps."
        )
        return 0

    today = date.today()
    built_date = built_date or today.isoformat()
    bsa_version = bsa_version or bsa_version_from_date(today)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold blue]Councils (authenticated)[/bold blue] → {output_dir}")

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp_url)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()

        page: Page = next((pg for pg in context.pages if "my.scouting.org" in pg.url), None)
        if page is None:
            console.print(
                "[red]  ERROR: no my.scouting.org tab found in this CDP session — "
                "log in first (see module docstring).[/red]"
            )
            return 0

        captured: dict = {}

        async def on_response(resp):
            if resp.url == COUNCILS_API:
                captured["status"] = resp.status
                captured["body"] = await resp.text()

        page.on("response", lambda r: asyncio.create_task(on_response(r)))

        console.print(f"  Reloading {page.url} to trigger the councils fetch...")
        await page.goto(TRIGGER_URL, wait_until="load", timeout=60000)
        await page.wait_for_timeout(4000)

        # Not logged in / session expired -> no organizations/councils call
        # ever fires, or fires and gets a 401. Give one retry via reload
        # before giving up, since the app sometimes needs a second trip to
        # attach the auth header (observed 2026-08-02).
        if captured.get("status") != 200:
            await page.reload(wait_until="load", timeout=60000)
            await page.wait_for_timeout(4000)

        await browser.close()

    if captured.get("status") != 200:
        console.print(
            f"[red]  ERROR: /organizations/councils returned "
            f"{captured.get('status', 'no response')} — are you logged into "
            f"my.scouting.org in that Chrome window?[/red]"
        )
        return 0

    import json
    official = json.loads(captured["body"])
    console.print(f"  Fetched {len(official)} raw entries from the authoritative API")

    councils = []
    for c in official:
        num, name = clean_council_name(c["councilName"])
        if not num:
            console.print(f"  [yellow]WARNING: could not parse council number from {c['councilName']!r}[/yellow]")
            continue
        if num == "000":
            # "National" — a BSA administrative placeholder in this API
            # response, not a real chartering council.
            continue
        state_code = c.get("state", "")
        councils.append({
            "id": num,
            "name": name,
            "state": STATE_NAMES.get(state_code, state_code),
            "city": c.get("city", ""),
            "address": None,
            "zip": None,
            "phone": None,
            "website": None,
            "email": None,
        })

    dupe_ids = {c["id"] for c in councils if sum(1 for x in councils if x["id"] == c["id"]) > 1}
    if dupe_ids:
        console.print(f"  [yellow]WARNING: duplicate council IDs found: {sorted(dupe_ids)}[/yellow]")

    councils.sort(key=lambda c: (c["state"], c["name"]))

    json_file = output_path / "councils.json"
    md_file = output_path / "councils.md"
    write_json(json_file, councils)
    console.print(f"  Wrote {len(councils)} councils → councils.json")

    fm = make_frontmatter(
        COUNCILS_API, built_date, bsa_version,
        note='"Full authoritative list via the authenticated organizations/councils API — see fetch_councils_authenticated.py. address/zip/phone/website/email are not available from this endpoint."',
    )
    md_lines = [
        fm, "",
        "# Scouting America Local Councils",
        "",
        f"_As of {bsa_version}. {len(councils)} councils listed by state._",
        f"_Source: {COUNCILS_API} (authenticated)_",
        "",
        "| ID | Council Name | State | City |",
        "|---|---|---|---|",
    ]
    for c in councils:
        md_lines.append(f"| {c['id']} | {c['name']} | {c['state'] or '—'} | {c['city'] or '—'} |")
    write_md(md_file, "\n".join(md_lines) + "\n")
    console.print("  Wrote → councils.md")

    console.print(f"  [green]Done:[/green] {len(councils)} councils → {output_dir}")
    return len(councils)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch the complete BSA council list via an authenticated my.scouting.org session"
    )
    parser.add_argument("--output", default="data/councils", help="Output directory")
    parser.add_argument(
        "--cdp-url", required=True,
        help="CDP endpoint of a Chrome session already logged into my.scouting.org"
    )
    args = parser.parse_args()
    asyncio.run(fetch_councils_authenticated(output_dir=args.output, cdp_url=args.cdp_url))
