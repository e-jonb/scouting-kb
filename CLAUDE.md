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

**Merit badge page returns no content:** BSA may have updated their CSS class names. Check `CONTENT_SELECTORS` in `utils.py` and update selectors as needed.

**Playwright browser errors:** Run `playwright install chromium` to reinstall the browser binary.

## Refresh Cadence

Run `python build_all.py --force` quarterly (January, April, July, October), or after BSA publishes updated requirements (typically at year-start and after national meetings). Merit badge requirements rarely change mid-year. Council data is very stable.

## Scope Boundaries

This repo only contains:
- The scraper Python scripts
- The compiled `data/` output
- Documentation

It does NOT contain app code, APIs, or UI. Those live in consumer repos.

When the Troop 452 Scoutmaster tool is built, it may warrant extracting a FastAPI layer here to serve data at runtime. That decision should go through the Studio (solution-architect-studio) before implementation.

## Copyright Note

All content in `data/` is sourced from publicly available materials at scouting.org. This repo is for internal use within authorized BSA unit applications. Do not redistribute publicly without legal review of BSA's content licensing terms.
