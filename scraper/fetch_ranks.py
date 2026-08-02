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


_LETTER_MARKER_RE = re.compile(r"^([a-n])\.(.*)$")


def _find_two_column_block(page):
    """
    Detect a compact two-column lettered sub-list — the handbook's space-
    saving layout for longer flat option lists (e.g. Life rank requirement 6:
    a-d printed in a left column, e-h in a right column, side by side).
    pdfplumber's plain top-to-bottom text extraction interleaves these into
    unreadable merged lines. Confirmed 2026-08-02, see docs/PLAYBOOK.md.

    Returns (top_start, top_end, words_in_block) if found, else None.
    top_end is exclusive — the first line's `top` that resumes single-column
    flow, detected by its leftmost word falling back to the outer margin
    (requirement numbers like "7." sit further left than any nested
    sub-item, so a leftward jump reliably signals the block ended).
    """
    words = page.extract_words(x_tolerance=2, y_tolerance=2)
    lines = {}
    for w in words:
        lines.setdefault(round(w["top"]), []).append(w)
    for top_lines in lines.values():
        top_lines.sort(key=lambda w: w["x0"])
    sorted_tops = sorted(lines)

    block_start, left_indent = None, None
    for top in sorted_tops:
        markers = [w for w in lines[top] if _LETTER_MARKER_RE.match(w["text"])]
        if len(markers) >= 2 and markers[1]["x0"] - markers[0]["x1"] > 40:
            block_start, left_indent = top, markers[0]["x0"]
            break
    if block_start is None:
        return None

    block_end = None
    for top in sorted_tops:
        if top <= block_start:
            continue
        if lines[top][0]["x0"] < left_indent - 10:
            block_end = top
            break
    if block_end is None:
        block_end = sorted_tops[-1] + 1

    block_words = [w for top in sorted_tops if block_start <= top < block_end for w in lines[top]]
    return block_start, block_end, block_words


def _reconstruct_two_column_block(block_words: list) -> str:
    """
    Splits a two-column block's words into left/right columns and
    reconstructs each in natural reading order (left column top-to-bottom,
    then right column top-to-bottom — which is also correct letter order,
    e.g. a-d then e-h). The column boundary (gutter) is found from the
    block's own word x-coverage rather than assumed, since it varies with
    how long each column's text runs: merge all word x-intervals, and the
    single largest gap between merged intervals is the empty gutter between
    columns.
    """
    intervals = sorted((w["x0"], w["x1"]) for w in block_words)
    merged = [list(intervals[0])]
    for x0, x1 in intervals[1:]:
        if x0 <= merged[-1][1] + 3:
            merged[-1][1] = max(merged[-1][1], x1)
        else:
            merged.append([x0, x1])
    gaps = sorted(
        ((merged[i + 1][0] - merged[i][1], merged[i][1], merged[i + 1][0]) for i in range(len(merged) - 1)),
        reverse=True,
    )
    gutter = (gaps[0][1] + gaps[0][2]) / 2

    left = sorted((w for w in block_words if w["x0"] < gutter), key=lambda w: (w["top"], w["x0"]))
    right = sorted((w for w in block_words if w["x0"] >= gutter), key=lambda w: (w["top"], w["x0"]))

    def reconstruct_items(col_words):
        items, marker, text_parts = [], None, []
        for w in col_words:
            m = _LETTER_MARKER_RE.match(w["text"])
            if m:
                if marker:
                    items.append(f"{marker}. {' '.join(text_parts)}")
                marker = m.group(1)
                text_parts = [m.group(2)] if m.group(2) else []
            else:
                text_parts.append(w["text"])
        if marker:
            items.append(f"{marker}. {' '.join(text_parts)}")
        return items

    items = reconstruct_items(left) + reconstruct_items(right)
    # Indented as a bullet sub-list (3-space indent — matches "N. " marker
    # width) so it nests inside the parent requirement instead of reading as
    # a fresh top-level list. Confirmed 2026-08-02 via user feedback that a
    # flat, unindented "a./b./c.../h." run was easy to misread as unrelated
    # to the requirement it belongs to.
    return "\n".join(f"   - {item}" for item in items)


def _find_merit_badge_table_row_count(page) -> int | None:
    """
    Plain text extraction only reveals blank tracking rows that have *some*
    text in them (a bare number, or "(Eagle-required)") — a row with zero
    text anywhere in it produces zero extracted lines, so it's invisible to
    a regex-based count. Confirmed 2026-08-02: Life/Star's requirement 3
    table has 5 real rows (3 labeled "(Eagle-required)" + 2 fully blank),
    but text-based counting only found 3.

    pdfplumber's table-grid detection (page.find_tables()) sees the actual
    row structure regardless of cell content, so use it here specifically
    to get an accurate row count. Locates the "NAME OF MERIT BADGE" header
    row, then counts forward while the requirement-number column (index 1)
    stays empty — that column is blank for every tracking row and is what
    turns non-empty again at the next real requirement, in both table
    styles seen so far (a bare-number style column 2, and an
    "(Eagle-required)"-label style also in column 2).
    """
    for table in page.find_tables():
        rows = table.extract()
        header_idx = next(
            (i for i, r in enumerate(rows) if r and any(c and "NAME OF MERIT BADGE" in c for c in r)),
            None,
        )
        if header_idx is None:
            continue
        count = 0
        for row in rows[header_idx + 1:]:
            if row and len(row) > 1 and (row[1] or "").strip():
                break
            count += 1
        return count
    return None


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF and return as a cleaned string."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page_texts = []
        for p in pdf.pages:
            # The source PDF double-prints certain text (a "fake bold" trick —
            # the same glyphs drawn twice at a near-identical position) for
            # emphasis. Without dedup, overlapping runs land just outside
            # extract_text()'s default merge tolerance and come out doubled:
            # "LEADER" -> "LLEEAADER", "badges required" -> "baddges requiiredd".
            # dedupe_chars() removes same-text/same-position duplicates before
            # extraction — confirmed 2026-08-02 to remove only the ~20 doubled
            # chars in the whole 41k-char combined PDF, nothing legitimate.
            deduped = p.dedupe_chars()

            block = _find_two_column_block(deduped)
            if block is None:
                text = deduped.extract_text(x_tolerance=2, y_tolerance=2)
            else:
                top_start, top_end, block_words = block
                # top_start/top_end come from line-grouping keys rounded to the
                # nearest integer, but within_bbox() requires an object's exact
                # (unrounded) bounding box to be fully inside the crop — a word
                # whose true top is e.g. 559.86 falls outside a crop starting at
                # the rounded 560 and silently disappears from both crops.
                # Confirmed 2026-08-02 (dropped Life rank requirement 7 this
                # way). A few points of buffer is safe: block content and
                # surrounding text are never packed that tight.
                before = deduped.within_bbox((0, 0, deduped.width, top_start + 2))
                after = deduped.within_bbox((0, top_end - 2, deduped.width, deduped.height))
                parts = []
                before_text = before.extract_text(x_tolerance=2, y_tolerance=2)
                if before_text and before_text.strip():
                    parts.append(before_text.strip())
                parts.append(_reconstruct_two_column_block(block_words))
                after_text = after.extract_text(x_tolerance=2, y_tolerance=2)
                if after_text and after_text.strip():
                    parts.append(after_text.strip())
                # Blank lines (not single newlines) around the reconstructed
                # block: it's an indented sub-list now, and needs clear block
                # separation from the surrounding paragraph/list on both
                # sides to nest correctly instead of being read as a lazy
                # continuation of whatever text precedes it.
                text = "\n\n".join(parts)

            if text and "NAME OF MERIT BADGE" in text:
                row_count = _find_merit_badge_table_row_count(deduped)
                if row_count is not None:
                    # Hidden hint for _build_merit_badge_table(): the real
                    # row count from the PDF's table grid, since blank rows
                    # with zero text are invisible to text-based counting.
                    text = text.replace(
                        "NAME OF MERIT BADGE", f"<!--MB_TABLE_ROWS:{row_count}-->\nNAME OF MERIT BADGE", 1
                    )

            if text and text.strip():
                page_texts.append(text.strip())

    raw = "\n\n".join(page_texts)
    raw = _clean_rank_pdf_text(raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    raw = re.sub(r"[ \t]+\n", "\n", raw)
    return raw.strip()


def _clean_rank_pdf_text(text: str) -> str:
    """
    Strip PDF page furniture that carries no informational value for a
    text-only knowledge base:
      - (cid:22): an unmapped checkbox-icon glyph used in the fillable form's
        "initial and date" tracking columns. Not decodable to real text —
        this isn't a dedup issue, the glyph simply has no text equivalent.
      - The recurring "LEADER / INITIAL & DATE" column-header block that
        repeats above every requirement-tracking column across the PDF.
      - The bare "RANK / REQUIREMENTS" running page header.
      - Bare 2-4 digit lines — the original PDF's page numbers, extracted as
        standalone lines with no other content.
      - The blank "NAME OF MERIT BADGE / DATE EARNED" tracking table (a fill-
        in-by-hand form for a Scout to record extra badges) — extracted as
        empty numbered rows ("1.", "2.", ... with nothing after them) or empty
        "(Eagle-required)" rows. On Eagle Scout's page this is fatal to
        rendering: CommonMark ignores the literal digits after the first item
        in a list and just increments from there, so those 10 empty "N."
        rows get silently renumbered 4-13, and the real next requirement
        ("4. While a Life Scout...") renders as "14." instead. Confirmed
        2026-08-02. Rebuilt as a real GFM table (blank cells, correct row
        count) instead of list markup, so it can't collide with surrounding
        numbering and still conveys "here's a blank tracking form" rather
        than silently dropping it.
    """
    text = re.sub(r"\(cid:\d+\)\n?", "", text)
    text = re.sub(r"(?m)^LEADER\n+INITIAL\n& DATE\n?", "", text)
    text = re.sub(r"(?m)^RANK\nREQUIREMENTS\n?", "", text)
    text = re.sub(
        r"(?m)(?:^<!--MB_TABLE_ROWS:(\d+)-->\n)?^NAME OF MERIT BADGE DATE EARNED\n(?:(?:\d+\.|\(Eagle-required\))[ \t]*\n)+",
        _build_merit_badge_table,
        text,
    )
    text = re.sub(r"(?m)^\d{2,4}$\n?", "", text)
    # Safety net: strip a stray hint marker if the table pattern above
    # somehow didn't match around it (e.g. an unexpected row format) so it
    # never leaks into the committed markdown as visible text.
    text = re.sub(r"(?m)^<!--MB_TABLE_ROWS:\d+-->\n?", "", text)
    return text


def _build_merit_badge_table(match: re.Match) -> str:
    """
    Rebuild a matched blank tracking-table block as a real GFM table.

    Row count prefers the `<!--MB_TABLE_ROWS:N-->` hint (from the PDF's
    actual table grid, injected in extract_pdf_text() — see
    _find_merit_badge_table_row_count()) over counting labeled rows in the
    text, since some rows are genuinely blank (no "(Eagle-required)" text,
    no number) and are invisible to text-based counting — confirmed
    2026-08-02 on Life/Star's requirement 3 table (5 real rows, only 3
    labeled). Falls back to the labeled-row count if the hint is missing
    (e.g. an individual-PDF fallback path that never went through the
    per-page table-grid detection).
    """
    labeled_rows = re.findall(r"^(?:(\d+)\.|(\(Eagle-required\)))[ \t]*$", match.group(0), re.MULTILINE)
    row_count = int(match.group(1)) if match.group(1) else len(labeled_rows)
    eagle_required_only = bool(labeled_rows) and all(r[1] for r in labeled_rows)
    header = (
        "| # | Merit Badge (must be Eagle-required) | Date Earned |"
        if eagle_required_only
        else "| # | Merit Badge | Date Earned |"
    )
    lines = [header, "|---|---|---|"]
    for i in range(1, row_count + 1):
        lines.append(f"| {i} |  |  |")
    # GFM pipe tables need a blank line before them or they're absorbed into
    # the preceding paragraph as literal pipe text instead of being parsed as
    # a table — confirmed 2026-08-02 (this table wasn't rendering at all).
    return "\n" + "\n".join(lines) + "\n\n"


_FOOTNOTE_START_RE = re.compile(r"^([ \t]*)(\d{1,2})([A-Z].*)$", re.MULTILINE)


def _reformat_footnotes(text: str) -> str:
    """
    The PDF's footnotes are extracted as a marker digit glued directly onto
    the start of its definition line ("9Assistant patrol leader..."), with
    the *reference* to that footnote likewise glued onto the end of a word
    in the body with no space ("...outdoor ethics guide.9"). The glued
    in-body digit is easy to misread as a stray list marker sitting right
    where a sub-item would be. Confirmed 2026-08-02, see docs/PLAYBOOK.md.

    Precisely bounding where each footnote's definition *ends* isn't reliably
    possible from text alone — most are one sentence, but e.g. Eagle Scout's
    footnote 12 ("APPEALS AND EXTENSIONS...") runs several paragraphs with no
    distinguishing marker before the next footnote. So this only marks each
    footnote's unambiguous *start* (bold "**N.**" on its own paragraph,
    replacing "Notes:" with a "## Notes" heading) rather than attempting to
    delimit a bounded list item per footnote. The content itself is
    unchanged either way — this only adds visual structure around it.

    Scoped to digit-style markers only (matches every rank except two
    isolated asterisk-style footnotes on Eagle Scout's Palm Requirements
    sub-section, `*`/`**` — left alone, see docs/PLAYBOOK.md for why those
    weren't worth the added ambiguity to chase).

    Not every footnote definition sits in the trailing "Notes:" block — a
    footnote can print at the bottom of whatever PDF page referenced it, so
    e.g. Eagle Scout's footnote 11 lands mid-requirement-list, between
    requirements 4 and 5. Giving *that* the same blank-line-separated
    treatment as the real trailing footnotes broke the surrounding ordered
    list into multiple disconnected `<ol>` blocks (confirmed 2026-08-02 via
    pandoc rendering — numbers still came out correct by coincidence, since
    each fragment's first item carried an explicit start value, but it's
    fragile and looks wrong structurally). So only footnote-marker lines at
    or after a "Notes:" occurrence get the full blank-line-and-heading
    treatment; anything earlier just gets its glued marker bolded in place,
    with no blank line, so it can't fracture a list it's embedded in.
    """
    marker_numbers = {m.group(2) for m in map(_FOOTNOTE_START_RE.match, text.split("\n")) if m}
    if "Notes:" not in text:
        return text

    first_notes_idx = text.find("Notes:")
    # A blank line before the heading isn't just cosmetic: without it, some
    # markdown renderers (confirmed on a real viewer, though pandoc is lenient
    # enough to not show the problem) treat "## Notes" as a lazy continuation
    # of the preceding list item's paragraph instead of a sibling heading —
    # visually merging the whole Notes section into whatever requirement
    # happened to be last. Confirmed 2026-08-02.
    text = re.sub(r"(?m)^Notes:[ \t]*", "\n## Notes\n\n", text)
    if not marker_numbers:
        return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"

    def _replace_start(m: re.Match) -> str:
        in_notes_tail = first_notes_idx >= 0 and m.start() >= first_notes_idx
        sep = "\n\n" if in_notes_tail else ""
        # Preserve any leading indent (e.g. from _reformat_position_categories
        # re-indenting a footnote as a continuation paragraph of its
        # enclosing requirement) — dropping it would pop the bolded footnote
        # back out to column 0, undoing that nesting.
        return f"{sep}{m.group(1)}**{m.group(2)}.** {m.group(3)}"

    text = _FOOTNOTE_START_RE.sub(_replace_start, text)

    notes_idx = text.find("## Notes")
    body, notes = (text[:notes_idx], text[notes_idx:]) if notes_idx >= 0 else (text, "")
    for marker in sorted(marker_numbers, key=len, reverse=True):
        # Glued directly onto a letter ("responsibility11:") or onto the
        # period ending a sentence ("guide.9", "rank.8") — both occur.
        body = re.sub(rf"(?<=[a-zA-Z.]){re.escape(marker)}(?!\d)", f" [{marker}]", body)
    text = body + notes

    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


_POSITION_CATEGORIES_RE = re.compile(
    # "Lone Scout."'s description stops at the next top-level requirement
    # ("\nN.") or a footnote-marker line ("\nN<capital letter>", no period).
    # The footnote-marker group is captured (not just used as a lookahead)
    # because e.g. Eagle Scout's footnote 11 happens to sit immediately
    # after this exact block (it prints at the bottom of whichever PDF page
    # the block landed on) and needs to be re-indented as a second paragraph
    # of the *enclosing* requirement — not left glued to the last bullet
    # (lazy-continuation swallows it into that bullet with no blank line)
    # and not given a bare blank line either (that dedents it below the
    # requirement's own indentation and fractures the surrounding ordered
    # list into separate <ol> blocks — both confirmed 2026-08-02).
    r"Scout troop\.(.*?)Venturing crew/Sea Scout ship\.(.*?)Lone Scout\.(.*?)"
    r"(?P<footnote>\n\d{1,2}[A-Z].*?)?(?=\n\d+\.|\Z)",
    re.DOTALL,
)


def _reformat_position_categories(text: str) -> str:
    """
    "Positions of responsibility" requirements (Star/Life/Eagle Scout all
    have one) list three membership-type categories — always the same three,
    always in this order: "Scout troop.", "Venturing crew/Sea Scout ship.",
    "Lone Scout." — each followed by its own list of qualifying positions.
    The source PDF bolds each category label, but plain text extraction
    loses that, leaving three runs of prose with no visual separation
    between "...or outdoor ethics guide." and "Venturing crew/Sea Scout
    ship. President, vice president...". Confirmed 2026-08-02 via user
    feedback that this was hard to read as three distinct options.

    Reformatted as a bulleted sub-list with each label bolded. The three
    labels are hardcoded (not detected generically) since they're an exact,
    unvarying BSA template repeated verbatim across ranks — a generic
    "label. description" detector would be far more error-prone than
    matching the known, stable text.

    Must run *before* _reformat_footnotes() — it captures a trailing
    footnote definition (if one immediately follows) while it's still in
    raw glued form, so it can re-indent it correctly; _reformat_footnotes()
    then bolds/brackets it wherever it ends up, same as any other footnote.
    """

    def _replace(m: re.Match) -> str:
        troop, venture, lone = (re.sub(r"\s+", " ", m.group(i)).strip() for i in (1, 2, 3))
        lines = [
            f"   - **Scout troop.** {troop}",
            f"   - **Venturing crew/Sea Scout ship.** {venture}",
            f"   - **Lone Scout.** {lone}",
        ]
        result = "\n\n" + "\n".join(lines)
        footnote = m.group("footnote")
        if footnote:
            # Blank line + 3-space indent: a second paragraph *of the same
            # requirement*, not another bullet and not a dedented sibling.
            footnote_line = re.sub(r"\s+", " ", footnote).strip()
            result += f"\n\n   {footnote_line}"
        return result

    return _POSITION_CATEGORIES_RE.sub(_replace, text)


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

            md_content = _reformat_position_categories(md_content)
            md_content = _reformat_footnotes(md_content)

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
