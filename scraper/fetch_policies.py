"""
fetch_policies.py

Fetches key BSA policy documents relevant to unit leaders from scouting.org.
All sources are public web pages (Playwright for JS rendering).

Policies covered (Tier 2):
  - Two-deep leadership
  - Youth Protection Training (Safety Youth Training / SYT)
  - Annual Health and Medical Record requirements
  - Guide to Safe Scouting overview
  - Campout and activity permissions
  - Chartered organization relationship

Output:
  data/policies/{slug}.md — one file per policy

Usage:
  python fetch_policies.py
  python fetch_policies.py --output data/policies --force
"""

import asyncio
import argparse
from pathlib import Path
from datetime import date

from playwright.async_api import async_playwright, Page
import markdownify
from rich.console import Console

from utils import (
    bsa_version_from_date, make_frontmatter,
    write_md, rate_limit, clean_markdown, extract_content
)

console = Console()

# Policies to fetch. Add new entries here as Tier 2 expands.
POLICIES = [
    {
        "name": "Two-Deep Leadership",
        "slug": "two-deep-leadership",
        "url": "https://www.scouting.org/health-and-safety/safety-moments/two-deep-leadership/",
        "description": (
            "BSA's two-deep adult leadership requirement. All Scouting activities must have "
            "at least two registered adult leaders present, or one adult and a parent."
        ),
    },
    {
        "name": "Youth Protection Training (Safety Youth Training)",
        "slug": "youth-protection-training",
        "url": "https://www.scouting.org/training/youth-protection/",
        "description": (
            "SYT (formerly YPT) requirements, training frequency, renewal timeline, "
            "and what the training covers. All registered adults must complete this."
        ),
        "note": (
            "BSA renamed Youth Protection Training to Safety Youth Training (SYT). "
            "All UI should display 'SYT'. DB columns retain legacy names."
        ),
    },
    {
        "name": "Annual Health and Medical Record",
        "slug": "annual-health-medical-record",
        "url": "https://www.scouting.org/health-and-safety/ahmr/",
        "description": (
            "When to use Part A/B (day hikes and short outings) vs. Part C (extended trips, "
            "high adventure, council events). Requirements vary by event duration and activity type."
        ),
    },
    {
        "name": "Guide to Safe Scouting — Overview",
        "slug": "guide-to-safe-scouting",
        "url": "https://www.scouting.org/health-and-safety/gss/",
        "description": (
            "Overview of the Guide to Safe Scouting (GSS). The GSS is BSA's primary policy "
            "document covering all aspects of safe unit operation."
        ),
        "note": "Full PDF available at scouting.org. This file captures the web summary pages.",
    },
    {
        "name": "Chartered Organization Relationship",
        "slug": "chartered-organization",
        "url": "https://www.scouting.org/programs/scouts-bsa/resources-for-volunteers/chartered-organizations/",
        "description": (
            "The chartered organization's role, responsibilities, and relationship with BSA. "
            "COs own their units — they select leaders and are responsible for the program."
        ),
    },
    {
        "name": "Camping and Activity Permissions",
        "slug": "camping-permissions",
        "url": "https://www.scouting.org/health-and-safety/gss/gss01/",
        "description": (
            "Permission slip requirements, activity consent forms, and parental notification "
            "requirements for outings, overnight trips, and high-adventure activities."
        ),
    },
    {
        "name": "Reporting Youth Protection Concerns",
        "slug": "reporting-youth-protection",
        "url": "https://www.scouting.org/health-and-safety/gss/gss02/",
        "description": (
            "Mandatory reporting requirements for suspected abuse. Leaders are mandated reporters. "
            "Includes BSA's 24-hour hotline and the reporting chain."
        ),
    },
]


async def fetch_policy_page(page: Page, policy: dict, built_date: str, bsa_version: str) -> str | None:
    """
    Fetch a single policy web page and return formatted markdown content.
    Returns None if no content is found.
    """
    await page.goto(policy["url"], wait_until="networkidle", timeout=30000)
    content_html = await extract_content(page)

    if not content_html:
        return None

    md_content = markdownify.markdownify(
        content_html,
        heading_style="ATX",
        strip=["script", "style", "nav", "footer", "header", "form", "button"],
    )
    md_content = clean_markdown(md_content)

    # Build frontmatter extras
    extras = {}
    if policy.get("note"):
        extras["note"] = f'"{policy["note"]}"'

    fm = make_frontmatter(policy["url"], built_date, bsa_version, **extras)

    lines = [fm, "", f"# {policy['name']}", "", f"_{policy['description']}_", ""]

    if policy.get("note"):
        lines += [f"> **Note:** {policy['note']}", ""]

    lines.append(md_content)
    lines.append("")

    return "\n".join(lines)


async def fetch_policies(
    output_dir: str = "data/policies",
    built_date: str = None,
    bsa_version: str = None,
    force: bool = False,
) -> int:
    """Main entry point. Returns count of policy files successfully written."""
    today = date.today()
    built_date = built_date or today.isoformat()
    bsa_version = bsa_version or bsa_version_from_date(today)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold blue]Policies[/bold blue] → {output_dir}")

    fetched = 0
    errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (compatible; scouting-kb/1.0; educational use)"
        )
        page = await context.new_page()

        for i, policy in enumerate(POLICIES):
            out_file = output_path / f"{policy['slug']}.md"
            console.print(f"  [{i+1}/{len(POLICIES)}] {policy['name']}...", end=" ")

            if out_file.exists() and not force:
                console.print("[yellow]skipped[/yellow]")
                continue

            try:
                content = await fetch_policy_page(page, policy, built_date, bsa_version)
                if content:
                    write_md(out_file, content)
                    fetched += 1
                    console.print("[green]done[/green]")
                else:
                    errors.append(policy["name"])
                    console.print(f"[red]no content found[/red]")
                    console.print(f"    Check manually: {policy['url']}")
            except Exception as e:
                errors.append(f"{policy['name']}: {e}")
                console.print(f"[red]ERROR: {e}[/red]")

            if i < len(POLICIES) - 1:
                rate_limit(1.5)

        await browser.close()

    if errors:
        console.print(f"  [yellow]Failed ({len(errors)}): {', '.join(errors)}[/yellow]")

    console.print(
        f"  [green]Done:[/green] {fetched}/{len(POLICIES)} policies fetched → {output_dir}"
    )
    return fetched


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch BSA policy documents from scouting.org")
    parser.add_argument("--output", default="data/policies", help="Output directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()
    asyncio.run(fetch_policies(output_dir=args.output, force=args.force))
