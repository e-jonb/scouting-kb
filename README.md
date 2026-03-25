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

## Data Versioning

Each build stamps files with a `bsa_version` in `YYYY.QN` format (e.g., `2026.Q1`). The `data/manifest.json` tracks the full build metadata. Consumer apps can surface this version to users ("requirements as of Q1 2026").

## Copyright

All content sourced from publicly available materials at [scouting.org](https://www.scouting.org). Internal use within authorized BSA unit applications only.
