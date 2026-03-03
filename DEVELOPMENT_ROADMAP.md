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
pip install -r requirements.txt
playwright install chromium
```

**Starting prompt:**
```
I'm starting scouting-kb Phase KB.1: initial knowledge base build.

Read first:
- CLAUDE.md

Goal: Run the scraper and populate data/ with Tier 1 + Tier 2 content.

Run Tier 1 (councils, ranks, merit badges — ~40 min first run):
  cd scraper
  python build_all.py --tier 1

Then Tier 2 (policies — ~5 min):
  python build_all.py --tier 2

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
python build_all.py --force
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

## Adding Tier 3 Content (Roles + Program Manuals)

Tier 3 is not yet implemented. When ready:

1. Create `scraper/fetch_roles.py` — follow the pattern in `fetch_ranks.py`
   - Known BSA role pages: Scoutmaster, Assistant Scoutmaster, Committee Chair, Treasurer, etc.
   - Output: `data/roles/{slug}.md`

2. Create `scraper/fetch_manuals.py` for program manuals (PDFs)
   - These are large PDFs. Use `pdfplumber` to extract key sections by page range, not the full document.
   - Output: `data/manuals/{slug}.md` with source URL and page reference in frontmatter

3. Wire into `build_all.py` under `tier == 3`

4. Update `CLAUDE.md` data structure section with new directories

---

## Troubleshooting

**Council data returns 0 records:**
The BSA council widget API endpoint may have changed. See the manual fallback in `fetch_councils.py` — open Chrome DevTools on the council finder page, watch Network requests, find the one returning 250+ records, copy the response JSON to `data/councils/councils.json` manually.

**Merit badge pages return empty content:**
Check `CONTENT_SELECTORS` in `utils.py`. Open a badge page in Chrome, inspect the content wrapper, update selectors to match current markup. Re-run `python fetch_merit_badges.py --force`.

**Playwright errors on launch:**
Run `playwright install chromium` to refresh the browser binary.
