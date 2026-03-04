"""
build_all.py — BSA Knowledge Base Master Builder

Runs all scrapers in sequence and updates data/manifest.json.

Usage:
  python build_all.py                   # Build all tiers
  python build_all.py --tier 1          # Tier 1 only: councils, ranks, merit badges
  python build_all.py --tier 2          # Tier 2 only: policies
  python build_all.py --force           # Overwrite all existing files
  python build_all.py --tier 1 --force  # Tier 1, force refresh

Tiers:
  1 — Councils, Ranks, Merit Badges (core data, highest value, ~40 min first run)
  2 — Key policies (Two-deep, SYT, health forms, Guide to Safe Scouting, ~5 min)
  3 — Roles, program manuals (planned — not yet implemented)

Before first run:
  pip install -r requirements.txt
  playwright install chromium
"""

import asyncio
import argparse
import json
from pathlib import Path
from datetime import date

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from utils import bsa_version_from_date, write_json
from fetch_councils import fetch_councils
from fetch_ranks import fetch_ranks
from fetch_merit_badges import fetch_merit_badges
from fetch_policies import fetch_policies

console = Console()
DATA_DIR = Path(__file__).parent.parent / "data"


async def build(tier: int = 0, force: bool = False, cdp_url: str = None) -> None:
    today = date.today()
    built_date = today.isoformat()
    bsa_version = bsa_version_from_date(today)

    console.print(Panel(
        f"[bold]BSA Knowledge Base Builder[/bold]\n"
        f"Date: [cyan]{built_date}[/cyan]  |  "
        f"Version: [cyan]{bsa_version}[/cyan]  |  "
        f"Tier: [cyan]{'all' if tier == 0 else tier}[/cyan]  |  "
        f"Force: [cyan]{force}[/cyan]",
        style="blue",
    ))

    kwargs = dict(built_date=built_date, bsa_version=bsa_version, force=force, cdp_url=cdp_url)
    results = {}

    if tier in (0, 1):
        results["councils"] = await fetch_councils(
            output_dir=str(DATA_DIR / "councils"), **kwargs
        )
        results["ranks"] = await fetch_ranks(
            output_dir=str(DATA_DIR / "ranks"), **kwargs
        )
        results["merit_badges"] = await fetch_merit_badges(
            output_dir=str(DATA_DIR / "merit-badges"), **kwargs
        )

    if tier in (0, 2):
        results["policies"] = await fetch_policies(
            output_dir=str(DATA_DIR / "policies"), **kwargs
        )

    if tier == 3:
        console.print("\n[yellow]Tier 3 (roles, program manuals) not yet implemented.[/yellow]")
        console.print("  To add: create fetch_roles.py following the pattern in fetch_ranks.py.")

    # Update manifest — merge with existing counts so partial builds don't zero out other tiers
    manifest_file = DATA_DIR / "manifest.json"
    existing_counts = {}
    if manifest_file.exists():
        try:
            existing = json.loads(manifest_file.read_text())
            existing_counts = existing.get("counts", {})
        except Exception:
            pass

    existing_counts.update({k: v for k, v in results.items() if v > 0})

    manifest = {
        "built": built_date,
        "version": bsa_version,
        "tier_built": "all" if tier == 0 else tier,
        "forced": force,
        "counts": existing_counts,
    }
    write_json(manifest_file, manifest)

    # Summary
    console.print()
    table = Table(title="Build Summary", show_header=True, header_style="bold")
    table.add_column("Content Type", style="bold")
    table.add_column("Files", justify="right")
    table.add_column("Status")

    for key, count in results.items():
        label = key.replace("_", " ").title()
        if count > 0:
            status = "[green]OK[/green]"
        else:
            status = "[red]Failed or empty[/red]"
        table.add_row(label, str(count), status)

    console.print(table)
    console.print(f"\n[green]Manifest updated:[/green] data/manifest.json")
    console.print(
        f"\n[bold]Done.[/bold] Commit the updated data/ directory:\n"
        f"  git add data/ && git commit -m 'chore(data): {bsa_version} refresh'"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build the BSA Knowledge Base from public scouting.org content.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--tier", type=int, default=0, choices=[0, 1, 2, 3],
        help="Which tier to build (0=all, 1=core data, 2=policies, 3=roles/manuals [not yet implemented])",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite all existing files regardless of whether they already exist",
    )
    parser.add_argument(
        "--cdp-url", default=None,
        help=(
            "Connect to a running Chrome via Chrome DevTools Protocol instead of "
            "launching a new headless browser. Required for sites with Cloudflare "
            "Enterprise bot protection (e.g. scouting.org). "
            "Setup: pkill -x 'Google Chrome' && "
            "open -a 'Google Chrome' --args --remote-debugging-port=9222 --no-first-run "
            "then navigate to scouting.org once before running this script. "
            "Default CDP URL: http://localhost:9222"
        ),
    )
    args = parser.parse_args()
    asyncio.run(build(tier=args.tier, force=args.force, cdp_url=args.cdp_url))
