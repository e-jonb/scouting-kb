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
import io
import re
from urllib.parse import urlparse
from pathlib import Path
from datetime import date

from playwright.async_api import async_playwright, Page
import markdownify
import pdfplumber
from rich.console import Console
from rich.markup import escape

from utils import (
    bsa_version_from_date, make_frontmatter,
    write_md, rate_limit, clean_markdown, absolutize_relative_links,
    extract_content, make_browser_context, download_pdf,
    label_tokens, label_overlap_ratio
)

console = Console()

_COUNCIL_LOCATOR_RE = re.compile(
    r"Find your local council Scout executive:.*?Search Result\n\n####\n*",
    re.DOTALL,
)


def _strip_council_locator_widget(text: str) -> str:
    """
    The youth-protection-training page embeds a "find your council" search
    widget (empty result-form labels: "Council Number :", "Address :", etc.)
    directly inside the article's own content column — not inside a
    <nav>/<header>/<form> element extract_content() already strips, so it
    survives as junk labels with nothing behind them. Confirmed 2026-08-02,
    see docs/PLAYBOOK.md. This repo already has real council data in
    data/councils/councils.json — this widget was never going to be
    interactive in a static markdown file anyway.
    """
    return _COUNCIL_LOCATOR_RE.sub("", text)

# Policies to fetch. Add new entries here as Tier 2 expands.
POLICIES = [
    {
        "name": "Youth Protection and Adult Leadership",
        "slug": "two-deep-leadership",
        "url": "https://www.scouting.org/health-and-safety/gss/gss01/",
        "description": (
            "BSA's youth protection and adult leadership requirements from the Guide to Safe Scouting. "
            "Covers two-deep leadership (two registered adults required), mandatory reporting, "
            "and other adult supervision policies."
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
        # Renamed from slug "chartered-organization" on 2026-09-05. The entry
        # was originally pointed at
        # /programs/scouts-bsa/resources-for-volunteers/chartered-organizations/,
        # which 404s; commit 5bfc84e substituted the Scouter Code of Conduct
        # URL but left name/slug unchanged and only half-edited the
        # description, so the file shipped a chartered-organization label over
        # Scouter Code of Conduct content. The Code of Conduct is itself a
        # named RESOURCES item in the Annual Unit Charter Agreement, so the
        # fix is to label it correctly rather than re-point the URL.
        # See docs/PLAYBOOK.md.
        "name": "Scouting America Scouter Code of Conduct",
        "slug": "scouter-code-of-conduct",
        "url": "https://www.scouting.org/health-and-safety/gss/bsa-scouter-code-of-conduct/",
        "description": (
            "The Scouter Code of Conduct — the conduct commitments every registered "
            "adult leader affirms, covering youth protection, transportation, "
            "fundraising, social media, and disclosure obligations."
        ),
    },
    {
        "name": "Camping and Activity Permissions",
        "slug": "camping-permissions",
        "url": "https://www.scouting.org/health-and-safety/gss/gss03/",
        "description": (
            "BSA camping policies and activity guidelines from the Guide to Safe Scouting. "
            "Covers campout requirements, activity planning, and safety standards."
        ),
    },
    {
        "name": "Aquatics Safety",
        "slug": "aquatics-safety",
        "url": "https://www.scouting.org/health-and-safety/gss/gss02/",
        "description": (
            "BSA aquatics safety requirements — Safe Swim Defense, Safety Afloat, "
            "supervision ratios, and swimmer classification requirements."
        ),
    },
    {
        # Same source page as "two-deep-leadership" above (gss01) -- BSA
        # doesn't publish a standalone page for this, the "Reporting
        # Requirements" section (mandatory abuse reporting, Scouts First
        # Helpline) lives inside the general Youth Protection and Adult
        # Leadership page alongside two-deep leadership itself. Previously
        # this slug was wired to the *wrong* URL entirely (gss02, Aquatics
        # Safety) -- an apparent copy-paste error when the Aquatics Safety
        # entry above was added, confirmed 2026-08-05. See docs/PLAYBOOK.md.
        "name": "Reporting Youth Protection Concerns",
        "slug": "reporting-youth-protection",
        "url": "https://www.scouting.org/health-and-safety/gss/gss01/",
        "description": (
            "How to recognize and report Youth Protection policy violations and "
            "suspected child abuse -- the Scouts First Helpline, mandatory "
            "reporting requirements, and online incident reporting."
        ),
    },

    # ---------------------------------------------------------------------
    # Added 2026-09-05 to close the gaps against the RESOURCES list in the
    # Annual Unit Charter Agreement (form 524-956, 2026 edition), which is
    # now this tier's coverage target. See docs/PLAYBOOK.md.
    # ---------------------------------------------------------------------
    {
        # The charter's own intro line points here for "the Bylaws, Rules and
        # Regulations, guidelines, policies, and other publications". Note the
        # PDF breaks this URL across a line as "membership- standards" — the
        # real path has no space (the spaced form 404/403s, verified).
        "name": "Membership Standards",
        "slug": "membership-standards",
        "url": "https://www.scouting.org/about/membership-standards/",
        "description": (
            "Scouting America's membership standards, and the hub the Annual Unit "
            "Charter Agreement points units to for the governing publications — "
            "it carries the live links to the Charter and Bylaws and the Rules "
            "and Regulations."
        ),
    },
    {
        # The mission statement is published in the "Foundation of Scouting"
        # section of the About page; there is no standalone /about/mission/
        # page (verified 2026-09-05).
        "name": "The Mission of Scouting America",
        "slug": "mission-of-scouting-america",
        "url": "https://www.scouting.org/about/",
        "description": (
            "The mission of Scouting America — to prepare young people to make "
            "ethical and moral choices over their lifetimes by instilling in them "
            "the values of the Scout Oath and Scout Law."
        ),
    },
    {
        "name": "The Scout Oath and Scout Law",
        "slug": "scout-oath-and-law",
        "url": "https://www.scouting.org/about/faq/question10/",
        "description": (
            "The Scout Oath and the twelve points of the Scout Law, with the "
            "meaning of each point. Covers Duty to God via the Oath's "
            "'duty to God and my country' and the Law's 'reverent' point."
        ),
    },
    {
        "name": "Scouting Safely",
        "slug": "scouting-safely",
        "url": "https://www.scouting.org/health-and-safety/",
        "description": (
            "The Scouting Safely section landing page — the index of BSA's health "
            "and safety guidance, linking the Guide to Safe Scouting, SAFE "
            "Checklist, incident reporting, youth protection, and the AHMR."
        ),
    },
    {
        "name": "SAFE Scouting Checklist",
        "slug": "safe-checklist",
        "url": "https://www.scouting.org/health-and-safety/safe/",
        "description": (
            "The SAFE Checklist — Supervision, Assessment, Fitness and skill, "
            "Equipment and environment. The four-point check leaders apply when "
            "planning and running any Scouting activity."
        ),
    },
    {
        "name": "Incident Reporting",
        "slug": "incident-reporting",
        "url": "https://www.scouting.org/health-and-safety/incident-report/",
        "description": (
            "How and when to report incidents, near misses, and injuries, and "
            "which reporting form or channel applies to each."
        ),
    },
    {
        "name": "Charter and Bylaws of Scouting America",
        "slug": "charter-and-bylaws",
        "kind": "pdf",
        "url": "https://filestore.scouting.org/filestore/about/2025_Charter_Bylaws.pdf",
        "description": (
            "The congressional charter and the corporate bylaws of Scouting "
            "America — the governing instruments the Annual Unit Charter "
            "Agreement binds a chartered organization to."
        ),
        "note": (
            "Captured as extracted PDF text, not a rendered web page. This is a "
            "governance document in legal prose — it is the authoritative source "
            "text for citation, not unit-facing guidance."
        ),
    },
    {
        "name": "Rules and Regulations of Scouting America",
        "slug": "rules-and-regulations",
        "kind": "pdf",
        "url": (
            "https://www.scouting.org/wp-content/uploads/2025/11/"
            "2025-Rules_Regulations_NEB-Approved-10.28.2025.pdf"
        ),
        "description": (
            "The Rules and Regulations of Scouting America, as amended "
            "October 28, 2025 — including the policies on unit fundraising, "
            "branding, membership, and unit operation."
        ),
        "note": (
            "Captured as extracted PDF text, not a rendered web page. This is a "
            "governance document in legal prose — it is the authoritative source "
            "text for citation, not unit-facing guidance."
        ),
    },
]


# ---------------------------------------------------------------------------
# Label checks: does a policy file's body match what the entry says it is?
#
# Two bugs have shipped this defect through two different mechanisms, and both
# passed every automated signal we had — the fetch succeeded, extraction found
# real content, and the frontmatter `source:` was accurate. Nothing compared
# what a file *claimed to be* against what it *was*.
#
#   reporting-youth-protection (2026-08-05) — a copy-paste error. name,
#     description and url all said "Aquatics Safety"; the slug was the odd one
#     out. Detectable statically, with no network: the slug disagreed with its
#     own entry.
#
#   chartered-organization (2026-09-05) — a dead-link substitution. Commit
#     5bfc84e swapped a 404ing URL for a working page describing a *different*
#     document and left name and slug untouched. Here the URL was the odd one
#     out, so every field in the entry still agreed with every other field.
#     Nothing static could catch it; only the fetched document disagrees.
#
# Hence two checks. Check A is static and catches the first shape. Check B is
# post-fetch and catches the second.
# ---------------------------------------------------------------------------

# (slug, check) -> why this entry is exempt. Keep the reason specific enough
# that a future maintainer can tell whether it still applies.
#
# A check that cries wolf gets switched off, which is worse than no check — so
# genuinely-legitimate mismatches belong here. A *failing* Check A, though, is
# a signal the token rule needs work, not a candidate for this table.
LABEL_CHECK_ALLOWLIST = {
    ("reporting-youth-protection", "B"): (
        "Shares one source page with two-deep-leadership by design. BSA bundles "
        "youth protection and mandatory reporting onto gss01 and publishes no "
        "standalone reporting page, so both entries point at the same URL and "
        "fetch_policy_page() extracts the same container. This file's body is "
        "therefore headed 'Youth Protection and Adult Leadership' rather than "
        "anything about reporting. Intentional, documented in docs/PLAYBOOK.md."
    ),
}


def _allowlist_reason(slug: str, check: str) -> str | None:
    return LABEL_CHECK_ALLOWLIST.get((slug, check))


def check_slug_matches_entry(policies: list[dict] = None) -> list[tuple[str, set[str]]]:
    """
    CHECK A (static, no network). Every significant token in an entry's `slug`
    must appear somewhere in that entry's own name + description + note.

    The slug is compared against the *whole entry*, not against `name` alone,
    and that is the detail the check lives or dies on. `two-deep-leadership` is
    a legitimate entry whose name is "Youth Protection and Adult Leadership" —
    zero token overlap with its slug. A name-only rule flags it exactly as
    loudly as a real bug. Its description says "two-deep leadership (two
    registered adults required)", which is what rescues it, so the description
    is what makes this check usable rather than noise.

    Returns [(slug, missing_tokens)] for each failing entry; empty list = pass.
    """
    failures = []
    for policy in policies if policies is not None else POLICIES:
        slug = policy["slug"]
        if _allowlist_reason(slug, "A"):
            continue
        haystack = " ".join(
            filter(None, (policy.get("name"), policy.get("description"), policy.get("note")))
        )
        missing = label_tokens(slug) - label_tokens(haystack)
        if missing:
            failures.append((slug, missing))
    return failures


# Fraction of an entry's `name` tokens that must appear in the fetched
# document's own heading. Proportional, because a page heading is routinely a
# longer or shorter phrasing of the same subject ("Incident Reporting" vs.
# "Welcome to Scouting America Incident Landing Page!"). Calibrated against the
# current 16-entry table: the lowest-scoring correct entry sits at 0.5, and the
# chartered-organization bug scores 0.0.
_HEADING_MATCH_THRESHOLD = 0.5

# h1 and h2 get separate patterns rather than one pattern with a `</h\1>`
# backreference. Deliberate: the backreference version was mangled into
# `</h\x01>` when this file was edited programmatically (a non-raw string ate
# the \1), producing a pattern that silently never matched. Check B then
# looked like it was passing on all 16 entries when it was in fact dead --
# caught only by testing it against real fetched HTML. Nothing to get wrong
# in the two-pattern form.
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1\s*>", re.IGNORECASE | re.DOTALL)
_H2_RE = re.compile(r"<h2[^>]*>(.*?)</h2\s*>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def heading_from_html(content_html: str) -> str | None:
    """
    The fetched document's own top heading: the first <h1> in the extracted
    content, falling back to the first <h2>.

    Read from the extracted content container rather than the whole page, so a
    site-wide banner <h1> can't stand in for the document's real title.
    """
    def _first(pattern) -> str | None:
        for inner in pattern.findall(content_html or ""):
            text = re.sub(r"\s+", " ", _TAG_RE.sub(" ", inner)).strip()
            if text:
                return text
        return None

    return _first(_H1_RE) or _first(_H2_RE)


def check_name_matches_document(policy: dict, *candidates: str | None) -> tuple[float, str] | None:
    """
    CHECK B (post-fetch). Compare the entry's `name` against the document's own
    heading.

    Compares NAME, not slug: `name` is the field that claims to describe the
    document, so on a correct entry the two should agree strongly. On the
    chartered-organization bug, name "Chartered Organization Relationship"
    against heading "Scouting America Scouter Code of Conduct" scores 0.0.

    Returns (ratio, heading) when the entry looks mislabeled, else None. This
    is advisory — page headings drift, and a rename upstream should not fail a
    build — so callers warn rather than abort.
    """
    if _allowlist_reason(policy["slug"], "B"):
        return None

    # Every candidate the document offers to identify itself -- its <h1>, and
    # its <title> -- is scored, and the best wins. Either one naming the
    # document correctly is sufficient evidence that the entry is not
    # mislabeled. This matters on real pages: /about/ carries the mission
    # statement this entry is for, but its <h1> is the marketing tagline
    # "Scouting invites every youth to a safe, fun place..." while its <title>
    # is "About Scouting America". Scoring only the h1 fires on a correct
    # entry; scoring both does not, and a genuine mislabel still scores zero
    # against every candidate.
    #
    # Each candidate is compared in BOTH directions, taking the better score,
    # because a heading is often a shorter phrasing of the entry name -- gss03
    # is titled just "Camping" where the entry is "Camping and Activity
    # Permissions". Containment either way means they describe the same
    # document. The chartered-organization bug scores 0.0 in both directions
    # against both candidates.
    best_ratio, best_text = None, None
    for candidate in candidates:
        if not candidate:
            continue
        scores = [
            r for r in (
                label_overlap_ratio(policy["name"], candidate),
                label_overlap_ratio(candidate, policy["name"]),
            ) if r is not None
        ]
        if not scores:
            continue
        ratio = max(scores)
        if best_ratio is None or ratio > best_ratio:
            best_ratio, best_text = ratio, candidate

    if best_ratio is None or best_ratio >= _HEADING_MATCH_THRESHOLD:
        return None
    return best_ratio, best_text


def report_slug_check(policies: list[dict] = None) -> int:
    """Run Check A and print the result. Returns the number of failures."""
    failures = check_slug_matches_entry(policies)
    if not failures:
        return 0
    console.print(
        f"\n[bold red]LABEL CHECK A FAILED[/bold red] — "
        f"{len(failures)} entr{'y' if len(failures) == 1 else 'ies'} whose slug "
        f"disagrees with its own name/description/note:"
    )
    for slug, missing in failures:
        console.print(
            f"    [red]{escape(slug)}[/red] — nothing in the entry mentions: "
            f"{escape(', '.join(sorted(missing)))}"
        )
    console.print(
        "    [yellow]Either the slug or the rest of the entry is wrong. "
        "Check the URL actually serves the document the slug names.[/yellow]"
    )
    return len(failures)


_GOVERNANCE_FURNITURE = [
    # Repeating page furniture in the national governance PDFs. Each of these
    # is printed on nearly every page and carries no informational value in a
    # text-only knowledge base. Confirmed 2026-09-05 against the October 2025
    # revisions of both documents.
    re.compile(r"(?m)^\s*©\s*\d{4}\s+Boy Scouts of America\s*$\n?"),
    re.compile(r"(?m)^\s*(?:BIN\s+)?100-49\d\s*$\n?"),
    re.compile(r"(?m)^\s*(?:Oct(?:ober)?)\s+\d{4}\s+Revision\s*$\n?"),
    # Bare page-number lines — arabic (body) and lower-case roman (front
    # matter). Anchored to a whole line so a numbered clause like "2." or a
    # section reference inside a sentence is never touched.
    re.compile(r"(?m)^\s*\d{1,3}\s*$\n?"),
    re.compile(r"(?m)^\s*[ivxl]{1,6}\s*$\n?"),
]


def _clean_governance_pdf_text(text: str) -> str:
    """
    Strip repeating page furniture from an extracted governance PDF.

    The copyright/BIN/revision footer sometimes extracts glued onto the line
    above or below it (e.g. "©2025 Boy Scouts of AmericaBIN 100-491"), because
    the footer sits in a separate text object that pdfplumber merges into the
    nearest line. Those glued forms are split apart first so the line-anchored
    patterns above can match them.
    """
    text = re.sub(r"(?<=[a-z])(?=©\d{4}\s+Boy Scouts)", "\n", text)
    text = re.sub(r"(?<=America)(?=BIN\s+100-49\d)", "\n", text)
    text = re.sub(r"(?<=America)(?=(?:Oct(?:ober)?)\s+\d{4}\s+Revision)", "\n", text)
    text = re.sub(r"(?<=Revision)(?=[A-Z]{2,})", "\n", text)

    for pattern in _GOVERNANCE_FURNITURE:
        text = pattern.sub("", text)

    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_governance_pdf_text(pdf_bytes: bytes) -> str:
    """
    Extract text from a national governance PDF (Charter and Bylaws, Rules and
    Regulations) as paragraphs.

    Deliberately simpler than fetch_ranks.extract_pdf_text(): these documents
    are single-column running legal prose with no fill-in tables, no two-column
    option lists, and no fake-bold double-printing, so none of the rank
    handbook's reconstruction machinery applies. Verified 2026-09-05 —
    dedupe_chars() changed nothing on either document.
    """
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = [p.extract_text(x_tolerance=2, y_tolerance=2) or "" for p in pdf.pages]
    return _clean_governance_pdf_text("\n".join(pages))


async def fetch_policy_pdf(page: Page, policy: dict, built_date: str, bsa_version: str) -> str | None:
    """
    Fetch a policy published as a PDF and return formatted markdown.

    The download runs through the browser (utils.download_pdf) rather than a
    plain HTTP client, for consistency with the rest of the bulk path — not
    because a bare request is blocked. A bare curl gets a valid PDF from this
    CDN (confirmed 2026-09-10); the reason to stay on the browser path is
    throttling under bulk load. Returns None if the download or extraction
    yields nothing usable.
    """
    # download_pdf() runs fetch() inside the current page, so a PDF on a
    # different host than the page is a cross-origin request and the browser
    # blocks reading the response body. The Charter and Bylaws lives on
    # filestore.scouting.org while the page is usually on www.scouting.org —
    # confirmed 2026-09-05 to come back empty for exactly this reason, with no
    # HTTP error to point at it. Park the page on the PDF's own origin first so
    # the fetch is same-origin. See docs/PLAYBOOK.md.
    pdf_host = urlparse(policy["url"]).netloc
    if urlparse(page.url).netloc != pdf_host:
        try:
            await page.goto(f"https://{pdf_host}/", wait_until="domcontentloaded", timeout=30000)
        except Exception:
            # A bare 403/404 on the host root is fine — the document that
            # loads is still on the right origin, which is all fetch() needs.
            pass

    pdf_bytes = await download_pdf(page, policy["url"])
    if not pdf_bytes:
        return None

    body = extract_governance_pdf_text(pdf_bytes)
    if len(body) < 500:
        return None

    extras = {}
    if policy.get("note"):
        extras["note"] = f'"{policy["note"]}"'
    fm = make_frontmatter(policy["url"], built_date, bsa_version, **extras)

    lines = [fm, "", f"# {policy['name']}", "", f"_{policy['description']}_", ""]
    if policy.get("note"):
        lines += [f"> **Note:** {policy['note']}", ""]
    lines += [body, ""]
    return "\n".join(lines)


# Escalating backoff between 403 retries, in seconds. The edge throttle can
# hold for well over a minute on the /about/* paths, so the tail of this
# schedule is deliberately long — a short schedule (4/8/12/16s) was measured
# on 2026-09-05 to give up while the URL was still only throttled, not gone.
_RETRY_BACKOFF_S = [5, 15, 30, 60, 90]


async def _goto_with_retry(page: Page, url: str, attempts: int = None) -> None:
    """
    Navigate to `url`, retrying on an HTTP 403 with escalating backoff.

    scouting.org's edge intermittently serves a bare nginx 403 to an automated
    browser — the same URL that 403s on one request returns 200 on the next,
    and the /about/* paths trip it far more readily than /health-and-safety/*.
    Confirmed 2026-09-05: /about/governance/charter/ 403'd four times in a row
    headless while loading normally in a real browser, so a 403 here means
    "throttled", NOT "page is gone". Do not respond to it by dropping a URL
    from POLICIES, and do not switch the fetch to a plain HTTP client — that
    removes the browser session the site is gating on and guarantees a 403.
    See docs/PLAYBOOK.md.
    """
    attempts = attempts or len(_RETRY_BACKOFF_S) + 1
    last_status = None
    for attempt in range(attempts):
        try:
            response = await page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception:
            # Some pages never settle to networkidle — e.g. the youth-protection
            # page's "find your council" widget keeps polling. Confirmed
            # 2026-08-02, see docs/PLAYBOOK.md.
            response = await page.goto(url, wait_until="load", timeout=30000)
            await page.wait_for_timeout(2000)

        last_status = response.status if response else None
        if last_status != 403:
            return

        if attempt < attempts - 1:
            backoff = _RETRY_BACKOFF_S[min(attempt, len(_RETRY_BACKOFF_S) - 1)]
            await page.wait_for_timeout(backoff * 1000)

    console.print(f"    [yellow]still HTTP {last_status} after {attempts} attempts[/yellow]")


async def fetch_policy_page(page: Page, policy: dict, built_date: str, bsa_version: str) -> str | None:
    """
    Fetch a single policy web page and return formatted markdown content.
    Returns None if no content is found.
    """
    await _goto_with_retry(page, policy["url"])
    await page.wait_for_timeout(1000)
    content_html = await extract_content(page)

    if not content_html:
        return None

    md_content = markdownify.markdownify(
        content_html,
        heading_style="ATX",
        strip=["script", "style", "nav", "footer", "header", "form", "button"],
    )
    md_content = clean_markdown(md_content)
    md_content = _strip_council_locator_widget(md_content)
    md_content = absolutize_relative_links(md_content)

    # CHECK B — does the document call itself what this entry claims it is?
    mismatch = check_name_matches_document(
        policy, heading_from_html(content_html), await page.title()
    )
    if mismatch:
        ratio, heading = mismatch
        # Every interpolated value here is escaped: rich reads square brackets
        # as markup, and an unescaped "[two-deep-leadership]" is parsed as a
        # style tag and rendered as nothing -- silently deleting the slug,
        # which is the one field the reader most needs. Confirmed 2026-09-05.
        console.print(
            f"\n    [bold yellow]LABEL CHECK B WARNING[/bold yellow] "
            f"{escape(policy['slug'])}: entry name and document self-description "
            f"disagree ({ratio:.0%} token overlap):"
        )
        console.print(f"      entry name      : {escape(policy['name'])}")
        console.print(f"      document says   : {escape(heading)}")
        console.print(f"      source          : {escape(policy['url'])}")

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
    cdp_url: str = None,
) -> int:
    """Main entry point. Returns count of policy files successfully written."""
    today = date.today()
    built_date = built_date or today.isoformat()
    bsa_version = bsa_version or bsa_version_from_date(today)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold blue]Policies[/bold blue] → {output_dir}")

    # CHECK A runs before any network work — it needs nothing but the table,
    # and a mislabeled entry is worth knowing about before spending ten
    # minutes fetching. Reported loudly but not fatal here, so a label typo
    # can't block a data refresh; `--check-labels` exits non-zero for CI.
    report_slug_check()

    fetched = 0
    errors = []

    async with async_playwright() as p:
        browser, context = await make_browser_context(p, cdp_url=cdp_url)
        page = await context.new_page()

        for i, policy in enumerate(POLICIES):
            out_file = output_path / f"{policy['slug']}.md"
            console.print(f"  [{i+1}/{len(POLICIES)}] {policy['name']}...", end=" ")

            if out_file.exists() and not force:
                console.print("[yellow]skipped[/yellow]")
                continue

            try:
                if policy.get("kind") == "pdf":
                    content = await fetch_policy_pdf(page, policy, built_date, bsa_version)
                else:
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

    # Report what was fetched this run, but return what the tier actually
    # *contains*. build_all.py feeds this into manifest.json's "counts", which
    # describes the data package, not one run of the scraper — a partial or
    # incremental build (where most entries are skipped as already-present, or
    # a few 403 out) would otherwise write a count far below the real file
    # count. Confirmed 2026-09-05: a run that fetched 5 of 16 wrote
    # "policies": 5 over a directory holding 12 files.
    present = len(list(output_path.glob("*.md")))
    console.print(
        f"  [green]Done:[/green] {fetched}/{len(POLICIES)} policies fetched "
        f"({present} files present) → {output_dir}"
    )
    return present


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch BSA policy documents from scouting.org")
    parser.add_argument("--output", default="data/policies", help="Output directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument(
        "--check-labels",
        action="store_true",
        help="Run the static slug/label check (Check A) and exit non-zero on failure. No network.",
    )
    args = parser.parse_args()

    if args.check_labels:
        failures = report_slug_check()
        if not failures:
            console.print(
                f"[green]Label check A passed[/green] — "
                f"{len(POLICIES)} entries, no slug/label disagreements."
            )
        raise SystemExit(1 if failures else 0)

    asyncio.run(fetch_policies(output_dir=args.output, force=args.force))
