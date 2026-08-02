# CLAUDE.md — scouting-kb

> This is the BSA Knowledge Base repo. It scrapes and structures publicly available Scouting America content into versioned markdown files for use by ScoutSync, the planned Troop 452 Scoutmaster tool, and AI development sessions.

## What This Repo Does

Runs a Python scraper (`scraper/`) against scouting.org to produce clean, versioned markdown and JSON files in `data/`. This is not an app — it's a data package. The scraper is run manually on a quarterly refresh schedule.

Consumer repos add `scouting-kb` as a git submodule and reference `data/` directly.

## Multi-Machine Sync

Run `git pull` before starting any work. This repo is used across multiple machines — starting without a pull risks working from a stale state. At the end of every session, ensure all work is committed and pushed (`git push origin main`) so the other machine can pick up cleanly.

## Memory Graduation

Claude Code's auto-memory (`~/.claude/projects/<repo>/memory/`) captures useful session-to-session knowledge — confirmed-working patterns, project decisions and their rationale, institutional facts — but it's local application state: invisible to git, doesn't sync across your own machines, and invisible to anyone who clones this repo fresh, including a maintainer of a downstream consumer (ScoutSync, the Troop 452 tool) trying to understand how this scraper actually works.

At the end of a significant work session (or whenever you're asked to wrap up), review what got saved to auto-memory that session. For anything that clears both bars below, also write it into this repo's committed docs — in addition to the memory file, not instead of it.

**Graduate it if:**
- It's a confirmed-working pattern or playbook for recurring project work
- It's a project decision and the reasoning behind it
- It's an institutional fact about how this repo operates that a future maintainer needs

**Leave it local-only if:**
- It's a personal preference about how Claude should interact with this specific user (tone, communication style)
- It's about the human-AI working relationship rather than the project itself

**Where it goes:**
- Short, stable operating rules → straight into this CLAUDE.md, near the related existing section
- Longer-form patterns, multi-step playbooks, or detailed rationale — a scraper selector broke and how it was fixed, a scouting.org quirk to route around — → `docs/PLAYBOOK.md` (create it, this repo doesn't have one yet), with a one-line pointer added here

**When you graduate something, mark the memory file too.** Append a line to the relevant memory entry noting where it landed — "Graduated to CLAUDE.md on [date]; that file is now authoritative" (or the PLAYBOOK.md equivalent). CLAUDE.md and PLAYBOOK.md will keep evolving after graduation; without this note, a stale copy of the original guidance sits in memory with no signal that it's been superseded.

A fresh clone — by you on a new machine, or by anyone else who ends up maintaining this scraper — should be able to reconstruct the accumulated know-how from committed docs alone, without depending on any machine's local Claude Code state.

## Running the Scraper

```bash
cd scraper
pip3 install -r requirements.txt
python3 -m playwright install chromium

python3 build_all.py              # All tiers (~45 min first run)
python3 build_all.py --tier 1     # Core data only: councils, ranks, merit badges (~40 min)
python3 build_all.py --tier 2     # Policies only (~5 min)
python3 build_all.py --force      # Force-refresh everything
```

After running, commit the updated `data/` directory:
```bash
git add data/ && git commit -m "chore(data): 2026.Q2 refresh"
```

## Tier System

| Tier | Content | Est. Time |
|------|---------|-----------|
| 1 | Councils (JSON), Ranks (7 files), Merit Badges (130+ files) | ~40 min first run, ~5 min incremental |
| 2 | Key policies: two-deep, SYT, health forms, Guide to Safe Scouting | ~5 min |
| 3 | Roles, program manuals | Not yet implemented |

## Data Structure

```
data/
  manifest.json          # Build metadata: date, version, counts
  councils/
    councils.json        # [{id, name, state, city, website, phone, ...}]
    councils.md          # Human-readable table (auto-generated)
  merit-badges/
    index.md             # All badges — eagle-required flag, links to files
    {slug}.md            # One per badge (camping.md, first-aid.md, etc.)
  ranks/
    index.md             # All ranks in advancement order
    {slug}.md            # One per rank (scout.md through eagle-scout.md)
  policies/
    two-deep-leadership.md
    youth-protection-training.md    # SYT
    annual-health-medical-record.md
    guide-to-safe-scouting.md
    chartered-organization.md
    camping-permissions.md
    reporting-youth-protection.md
  roles/                 # Tier 3 — not yet implemented
```

## Frontmatter Standard

Every markdown file includes:
```yaml
---
source: https://www.scouting.org/...
fetched: YYYY-MM-DD
bsa_version: YYYY.QN
---
```

Consumer apps should read `bsa_version` from `manifest.json` to surface "as of Q1 2026" notices in the UI.

## Consumer Repos

| Repo | Purpose | Submodule Path |
|------|---------|----------------|
| scoutsync | In-app contextual guidance panels | `packages/scouting-kb` |
| troop-452 (planned) | AI context injection + reference | TBD |

### Adding a New Consumer

```bash
git submodule add <this-repo-url> packages/scouting-kb
git submodule update --init
```

Reference files at `packages/scouting-kb/data/`. Read `manifest.json` for build date and version.

## Troubleshooting

**No council data returned:** scouting.org's council widget API endpoint may have changed. See `fetch_councils.py` for manual fallback instructions — browser DevTools to find the API call.

**Council count looks low, or you want a more complete/authoritative refresh:** `fetch_councils.py`'s ~200-zip sampling approach is a sample, not a canvas — confirmed 2026-08-02 it was missing 91 of 228 real councils (137 found), plus couldn't catch 2 dissolved councils or 2 renames. If you can log into `my.scouting.org` yourself, run `fetch_councils_authenticated.py` instead for the complete, authoritative list (trade-off: no address/zip/phone/website/email, which the zip-sampled data has — see that script's docstring for login/setup steps). Not wired into `build_all.py` since it can't run unattended. See `docs/PLAYBOOK.md`.

**Merit badge page returns no content:** BSA may have updated their CSS class names. Check `CONTENT_SELECTORS` in `utils.py` and update selectors as needed.

**Merit badge file has a Scout Shop ad, a magazine article, or CSS junk instead of Purpose/Requirements text:** `fetch_merit_badges.py` uses a dedicated `extract_merit_badge_content()` (in `utils.py`) that targets the `.profile-card` (Requirements) and "Merit Badge Overview" heading directly — this was added after all 133 merit badge files were found corrupted this way, including the files this doc used to cite as working examples. If BSA changes the page template again, re-verify `.profile-card` still exists via a live CDP session before assuming the generic `extract_content()` fallback is enough. See `docs/PLAYBOOK.md` for the full incident writeup, plus two related bugs found in the same investigation: badge-name collisions from the index page listing some badges twice, and one badge (Genealogy) whose own index-page link text is mislabeled "Geology" on BSA's site.

**Scraped file contains site nav links or raw JS instead of real content:** `extract_content()` in `utils.py` strips nav/header/footer/script/form/button elements from the whole document before selecting a content container — this was added after 3 policy files silently captured page chrome instead of body content. See `docs/PLAYBOOK.md` for the full incident writeup and why `markdownify`'s `strip=` argument alone doesn't prevent this.

**Scraped file ends with a blank/broken image:** that's an empty lazy-load placeholder (`<svg viewBox="..."></svg>`, no shapes) — the real image swaps in via JS after the scraper has already captured the DOM. `clean_markdown()` in `utils.py` strips standalone instances of this automatically; instances wrapped in a real outer link are deliberately left alone since the link itself can be legitimate content. See `docs/PLAYBOOK.md`.

**Rank file (`data/ranks/*.md`) has doubled letters, `(cid:XX)` glyphs, or looks too long / contains another rank's content:** `extract_pdf_text()` in `fetch_ranks.py` calls `page.dedupe_chars()` before extracting text, to collapse the source PDF's fake-bold double-printed glyphs — without it, both doubled characters AND a section-boundary-detection regex failure (which let `life.md` silently absorb all of `eagle-scout.md`'s content) can occur. See `docs/PLAYBOOK.md` for the full incident writeup.

**Rank file's requirement numbers look wrong when rendered (e.g. requirement 4 displays as "14."):** a blank "NAME OF MERIT BADGE / DATE EARNED" fill-in table in the source PDF (Star/Life/Eagle Scout) extracts as empty numbered list rows with nothing after the number, which most markdown renderers silently absorb into the surrounding list's numbering. `_build_merit_badge_table()` in `fetch_ranks.py` rebuilds the table as real GFM markdown (blank cells, correct row count) instead of list markup — note GFM pipe tables need a blank line before them or they get absorbed as literal text into the preceding paragraph. When verifying rank-file rendering, use a real CommonMark/GFM renderer (`pandoc -f gfm`) — python-markdown's default parser doesn't implement the same lazy-continuation rules and will give a false read. See `docs/PLAYBOOK.md`.

**Rank file has a garbled two-column list, or a footnote digit glued onto a word:** `_find_two_column_block()`/`_reconstruct_two_column_block()` in `fetch_ranks.py` detect and reconstruct the handbook's compact side-by-side lettered lists (e.g. Life rank requirement 6) from PDF word coordinates — plain text extraction interleaves the two columns into unreadable merged lines, now emitted as a nested indented sub-list. `_reformat_footnotes()` bolds each footnote's start and brackets in-body references (`"guide. [9]"` instead of `"guide.9"`), without attempting to precisely bound where a footnote's content ends (not reliably possible from text alone — see `docs/PLAYBOOK.md` for why, and for the gotcha where doing this wrong split one continuous requirement list into three broken `<ol>` blocks).

**Rank file's "Notes" section reads merged into the last requirement, or a merit badge tracking table is missing rows:** always put a blank line before an inserted `## heading` — pandoc is lenient enough to parse it as a heading without one, but not every renderer is (confirmed the actual bug this way). For table row counts: some tracking rows are completely blank (zero text), invisible to counting labeled rows via regex — `_find_merit_badge_table_row_count()` uses `page.find_tables()` to read the PDF's actual table grid instead. See `docs/PLAYBOOK.md` for the "Round 2" incident writeup, including the `_reformat_position_categories()` bulleted list for the repeated "Scout troop./Venturing crew.../Lone Scout." template.

**A markdown link in `data/` points at a path with no domain (e.g. `/health-and-safety/gss/toc`):** `markdownify` preserves hrefs exactly as written in the source HTML — a root-relative link resolves fine in a browser but is dead in a standalone file. `absolutize_relative_links()` in `utils.py` prepends the site's base URL, wired into both `fetch_policies.py` and `fetch_merit_badges.py` post-markdownify. See `docs/PLAYBOOK.md`.

**Before trusting a "re-fetched, byte-identical" result as proof a file is clean:** it only proves the file didn't need whatever specific fix was being tested at that moment — not that the file has no other problems. `youth-protection-training.md` sat with an embedded "find your council" widget's raw JS/empty form labels for a full audit cycle because it happened to be byte-identical during the *nav/script* fix's re-test, which was a different bug. If a file hasn't been actually read since a fix, "identical to before" isn't the same as "verified." See `docs/PLAYBOOK.md`.

**Playwright browser errors:** Run `playwright install chromium` to reinstall the browser binary.

## Refresh Cadence

Run `python build_all.py --force` quarterly (January, April, July, October), or after BSA publishes updated requirements (typically at year-start and after national meetings). Merit badge requirements rarely change mid-year.

Council *identities* (which councils exist, their names) are not as stable as previously assumed here — confirmed 2026-08-02 that mergers/dissolutions and renames happen (see `docs/PLAYBOOK.md`). `build_all.py`'s automated zip-sampling refresh won't catch a rename (a resampled zip still resolves to *a* council, just not flagging the name changed) and can miss councils outside its ~200-zip sample entirely. Run `fetch_councils_authenticated.py` (requires logging into `my.scouting.org` yourself — not automatable) periodically for a real audit, not just the automated quarterly pass.

## Scope Boundaries

This repo only contains:
- The scraper Python scripts
- The compiled `data/` output
- Documentation

It does NOT contain app code, APIs, or UI. Those live in consumer repos.

When the Troop 452 Scoutmaster tool is built, it may warrant extracting a FastAPI layer here to serve data at runtime. That decision should go through the Studio (solution-architect-studio) before implementation.

## Copyright Note

All content in `data/` is sourced from publicly available materials at scouting.org. This repo is for internal use within authorized BSA unit applications. Do not redistribute publicly without legal review of BSA's content licensing terms.
