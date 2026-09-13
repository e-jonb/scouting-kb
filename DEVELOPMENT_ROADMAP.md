# Development Roadmap — scouting-kb

> This is not an app. There are no sprints, deployments, or releases. This document covers:
> 1. The initial build (run once to populate `data/`)
> 2. The quarterly refresh procedure
> 3. How to expand to new content tiers

---

## Phase KB.1 — Initial Build

Run the scraper for the first time and commit the populated `data/` directory.

**Before you start:**
```bash
cd scraper

# macOS: use pip3 and python3 (not pip/python)
pip3 install -r requirements.txt
python3 -m playwright install chromium
```

**Starting prompt:**
```
I'm starting scouting-kb Phase KB.1: initial knowledge base build.

Read first:
- CLAUDE.md

Goal: Run the scraper and populate data/ with Tier 1 + Tier 2 content.

Run Tier 1 (councils, ranks, merit badges — ~40 min first run):
  cd scraper
  python3 build_all.py --tier 1

Then Tier 2 (policies — ~5 min):
  python3 build_all.py --tier 2

After each tier completes:
- Check manifest.json for counts
- Spot-check output: open 3–5 merit badge .md files, verify content looks real
- Verify all 7 rank files are present and have substantial content
- If council fetch returned 0: follow the DevTools manual fallback in fetch_councils.py comments

Quality bar before committing:
- councils.json: 200+ records, each with name + state at minimum
- ranks/: all 7 files, each with actual requirement text
- merit-badges/: 100+ files, index.md shows eagle-required split
- policies/: at least 5 of 7 files with real policy content (not just frontmatter)

If any content selectors are returning empty files:
- Open the relevant scouting.org page in Chrome
- Inspect the content block, find the CSS class wrapping the main text
- Update CONTENT_SELECTORS in scraper/utils.py and re-run with --force

Commit and deploy:
- Stage: data/
- Commit: chore(data): 2026.Q1 initial knowledge base build
- Push to main (scouting-kb repo)
```

---

## Quarterly Refresh Procedure

Run every January, April, July, and October — or after BSA publishes updated requirements.

```bash
cd scraper
python3 build_all.py --force
```

Review the diff before committing — look for meaningful content changes vs. markup noise. If BSA only changed nav chrome or styling, you may not need to commit everything.

```bash
git add data/
git diff --staged | head -100   # Sanity check before committing
git commit -m "chore(data): 2026.Q2 refresh"
git push
```

**After committing:** update any consumer repos that pin to a specific submodule commit:
```bash
# In each consumer repo (e.g., scoutsync):
cd packages/scouting-kb
git pull
cd ../..
git add packages/scouting-kb
git commit -m "chore(deps): update scouting-kb to 2026.Q2"
```

---

## Tier 3, resolved (2026-09-13)

**Roles are not this repo's work.** Position descriptions belong to `scouting-reference`, per its
ADR-006, Accepted 2026-09-13. The `fetch_roles.py` instructions that stood here from March 2026
until that date have been deleted rather than annotated – they described work this repo is not
doing, and a struck-through task list still reads as a task list.

**Manuals are unscheduled** – see below. Tier 3 as originally written (roles + manuals) no longer
exists. The reasoning is in `docs/PLAYBOOK.md`, "A scraped tier needs an external enumerating
authority"; what was known and argued beforehand is preserved in `docs/TIER-3-SCOPE-BRIEF.md`.

### Program manuals – unscheduled

Not deferred to a date. Deferred to a **condition**, because this repo has already had a backlog
item sit five months past a dead precondition. Three things must be true before this work starts:

1. **A named consumer** – a specific repo that will read the output.
2. **A named manual** – not "program manuals" as a category.
3. **The question it must answer** – this one is load-bearing. The question determines how the
   document is chunked, and chunking is the only real design decision in the project. Without it
   the first session produces a shape nobody can evaluate.

Until all three exist, this is not ready to pick up, and nothing here should be read as a next task.

**What a future scoping session needs to know.** Guide to Advancement (`33088.pdf`) is
**27,267,426 bytes** – measured 2026-09-13. It is also not named on the Annual Unit Charter
Agreement's RESOURCES list, and neither is any other manual, so manuals have no external warrant of
the kind that put the governance PDFs in Tier 2.

The extraction cost is the part that is easy to underestimate. A **15-page** rank PDF produced six
distinct failure classes in a single session, every one of which applies again at book scale:

- doubled glyphs from fake-bold printing, which corrupted a section-boundary regex and let one
  rank silently absorb another's entire content
- blank fill-in tables that consumed list numbering, rendering requirement 4 as "14."
- two-column lettered lists that interleave into unreadable merged lines under plain extraction
- footnote markers glued onto the words preceding them, and footnotes printed mid-document rather
  than in a trailing block
- table row counts invisible to text-based counting, because some rows are genuinely empty
- a missing blank line before a heading, merging a whole section into the preceding requirement

All six are written up in `docs/PLAYBOOK.md`. Two further design questions have no answer yet:
what constitutes one output *file*, and what a stable citation looks like given that page numbers
shift between editions – a page reference in frontmatter is wrong the first time BSA reflows the
document, and wrong silently.

If it is ever built: `scraper/fetch_manuals.py`, output to `data/manuals/{slug}.md`, wired into
`build_all.py` under `tier == 3`, with `CLAUDE.md`'s data-structure section updated to match.

---

## Troubleshooting

**Council data returns 0 records:**
The BSA council widget API endpoint may have changed. See the manual fallback in `fetch_councils.py` — open Chrome DevTools on the council finder page, watch Network requests, find the one returning 250+ records, copy the response JSON to `data/councils/councils.json` manually.

**Merit badge pages return empty content:**
Check `CONTENT_SELECTORS` in `utils.py`. Open a badge page in Chrome, inspect the content wrapper, update selectors to match current markup. Re-run `python fetch_merit_badges.py --force`.

**Playwright errors on launch:**
Run `playwright install chromium` to refresh the browser binary.
