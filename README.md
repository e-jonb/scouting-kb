# scouting-kb

A structured knowledge base of publicly available Scouting America content. This repo is a data artifact —
not a general-purpose library. Content is sourced from scouting.org and
refreshed quarterly.

Not intended for external contributions or general use.

## What's Included

| Content | Files | Source |
|---------|-------|--------|
| Merit Badges | 130+ `.md` files + index | scouting.org/skills/merit-badges/ |
| Ranks | 7 `.md` files + index (Scout → Eagle) | scouting.org/programs/scouts-bsa/ |
| Councils | `councils.json` + `councils.md` | BSA council finder |
| Policies | Key unit-leader policies (two-deep, SYT, health forms, GSS) | scouting.org/health-and-safety/ |
| Roles | Scoutmaster, ASM, Committee Chair, etc. | _Tier 3 — coming later_ |

Each file includes frontmatter with source URL, fetch date, and BSA version quarter.

## Using This as a Submodule

```bash
git submodule add <repo-url> packages/scouting-kb
git submodule update --init
```

Data is at `packages/scouting-kb/data/`. Read `manifest.json` for build date and version string.

## Running the Scraper

```bash
cd scraper
pip install -r requirements.txt
playwright install chromium

python build_all.py           # All tiers (~45 min first run)
python build_all.py --tier 1  # Core data only (councils, ranks, merit badges)
python build_all.py --tier 2  # Policies only
python build_all.py --force   # Force full rebuild
```

Refresh quarterly. After running:
```bash
git add data/ && git commit -m "chore(data): 2026.Q2 refresh"
```

## Counselor Scraper (separate tool)

`scraper/fetch_counselors.py` pulls Merit Badge Counselor lists from Scoutbook's
legacy results pages. It's a separate tool from the main KB build — output is
not part of `data/` (it contains PII and is gitignored).

Requires a logged-in Chrome with CDP enabled:

```bash
pkill -x "Google Chrome"
open -a "Google Chrome" --args --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-cdp
# Log in to scoutbook.scouting.org in that browser
```

Then run with the first-page URL from Scoutbook's counselor search:

```bash
cd scraper
python3 fetch_counselors.py --url "<first-page URL>" --output counselors.csv
```

**Tip — fetch all badges at once:** rather than running per-badge, leave
`MeritBadgeID` empty in the search URL. Scoutbook returns every counselor in
your proximity radius across all badges in a single paginated result. The CSV's
`merit_badges` column then lists each counselor's full badge set, which is
trivial to filter downstream.

URL parameters of interest: `UnitID`, `Proximity`, `zip`, `formCouncilID`,
`formDistrictID`, `Availability=Available`, `MeritBadgeID` (omit for all).

## Data Versioning

Each build stamps files with a `bsa_version` in `YYYY.QN` format (e.g., `2026.Q1`). The `data/manifest.json` tracks the full build metadata. Consumer apps can surface this version to users ("requirements as of Q1 2026").

## Copyright

All content sourced from publicly available materials at [scouting.org](https://www.scouting.org). Internal use within authorized BSA unit applications only.
