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

# Written verbatim into every manifest. See the comment in build() below.
MANIFEST_NOTES = "See docs/PLAYBOOK.md for what changed in this corpus and why."


def _corpus_counts() -> dict:
    """
    Count what is in `data/` right now, per content type.

    The manifest's `counts` describes the corpus, not the run: a consumer reads
    it to know how many merit badges it has. Deriving it from each fetcher's
    return value conflated the two and broke on any incremental build.
    A type whose directory is missing or empty counts 0 and is then skipped by
    the caller, so a partial build never zeroes a tier it did not touch.
    """
    def _md_files(d: Path) -> int:
        return len([f for f in d.glob("*.md") if f.name != "index.md"]) if d.is_dir() else 0

    councils_json = DATA_DIR / "councils" / "councils.json"
    councils = 0
    if councils_json.exists():
        try:
            councils = len(json.loads(councils_json.read_text()))
        except Exception:
            councils = 0

    return {
        "councils": councils,
        "ranks": _md_files(DATA_DIR / "ranks"),
        "merit_badges": _md_files(DATA_DIR / "merit-badges"),
        "policies": _md_files(DATA_DIR / "policies"),
    }


async def build(tier: int = 0, force: bool = False, cdp_url: str = None,
                skip: set = None) -> None:
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

    skip = set(skip or ())
    if skip:
        console.print(f"  [yellow]Skipping:[/yellow] {', '.join(sorted(skip))}")

    if tier in (0, 1):
        if "councils" not in skip:
            results["councils"] = await fetch_councils(
                output_dir=str(DATA_DIR / "councils"), **kwargs
            )
        if "ranks" not in skip:
            results["ranks"] = await fetch_ranks(
                output_dir=str(DATA_DIR / "ranks"), **kwargs
            )
        if "merit_badges" not in skip:
            results["merit_badges"] = await fetch_merit_badges(
                output_dir=str(DATA_DIR / "merit-badges"), **kwargs
            )

    if tier in (0, 2):
        if "policies" not in skip:
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

    # `results` holds what each fetcher *fetched this run*, which on an
    # incremental (non-`--force`) build is only the missing files — 2, not 144.
    # `counts` is meant to describe the corpus, and consumers read it that way,
    # so count what is actually on disk instead. Found 2026-09-13, when an
    # incremental run to add two merit badges would have written
    # `"merit_badges": 2` over the corpus total.
    on_disk = _corpus_counts()
    existing_counts.update(
        {k: on_disk[k] for k in results if on_disk.get(k, 0) > 0}
    )

    manifest = {
        "built": built_date,
        "version": bsa_version,
        "tier_built": "all" if tier == 0 else tier,
        "forced": force,
        "counts": existing_counts,
        # Fixed, generated, deterministic. "notes" used to hold a
        # hand-maintained account of what changed in the corpus and why, which
        # this function rebuilt from scratch and silently erased on every run.
        # Carrying it forward instead stopped the deletion but not the drift:
        # preserving a narrative is not the same as keeping it true.
        #
        # Studio decision 2026-09-05 — hand-maintained narrative does not belong
        # in a machine-regenerated artifact at all, because it will either be
        # destroyed or go stale and you do not get to choose which. The
        # provenance now lives in docs/PLAYBOOK.md, which is append-only and
        # which nothing regenerates. This line is generated, not maintained, so
        # there is nothing left to erase.
        "notes": MANIFEST_NOTES,
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
            "launching a new headless browser. Preferred for full --force rebuilds "
            "of scouting.org, which throttles under sustained load. "
            "Setup: pkill -x 'Google Chrome', then launch the binary directly "
            "(not 'open -a', which often fails to open the port) with both "
            "--remote-debugging-port=9222 and --user-data-dir=/tmp/chrome-cdp-scraper "
            "-- the port alone is not enough on macOS. See docs/PLAYBOOK.md, "
            "'Chrome CDP setup needs --user-data-dir'. Navigate to scouting.org "
            "once before running this script. "
            "Default CDP URL: http://localhost:9222"
        ),
    )
    parser.add_argument(
        "--skip", default="",
        help=(
            "Comma-separated content types to leave untouched: "
            "councils, ranks, merit_badges, policies. "
            "Exists mainly for councils: `--tier 1 --force` would otherwise run the "
            "zip-sampling fetcher over data/councils/councils.json, which holds the "
            "authoritative 228-council list produced by fetch_councils_authenticated.py "
            "(a human-driven my.scouting.org run). Zip sampling found 137 of 228 in "
            "August 2026 and cannot see renames or dissolutions at all, so a forced "
            "rebuild is a 40%% data loss that no error would report. "
            "Use `--skip councils` for any forced Tier 1 rebuild."
        ),
    )
    args = parser.parse_args()
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    unknown = skip - {"councils", "ranks", "merit_badges", "policies"}
    if unknown:
        parser.error(f"unknown --skip value(s): {', '.join(sorted(unknown))}")
    asyncio.run(build(tier=args.tier, force=args.force, cdp_url=args.cdp_url, skip=skip))
