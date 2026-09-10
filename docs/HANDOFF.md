# Handoff – scouting-kb

> **Owned by the Tactical Architect in this repo.** The Studio reads it at resume, before its own handoff file.
>
> **Two sections, handled differently.** Current State is **overwritten** every session so it is always true right now. The Session Log is **appended** so it stays historical. A pure log cannot answer "where are we" without reading everything and reconstructing it, which is the problem this file exists to solve.
>
> **On a merge conflict:** keep both Session Log entries, ordered **newest first**. For Current State, take the newer one **and re-verify it against the repo** rather than trusting either copy. That is cheap here – the counts and dates below are all readable from `data/` and `data/manifest.json` in a few seconds – and a state doc is exactly the kind of file that goes confidently stale.

---

## Current State

**As of:** 2026-09-07 \
**Corpus version:** 2026.Q3, `built: 2026-09-05`, `tier_built: 2` \
**Tier 1:** built – councils 228, ranks 7, merit badges 142 \
**Tier 2:** built – policies 16 \
**Tier 3:** not implemented (roles, program manuals)

This is a data package, not an app. The scraper in `scraper/` produces versioned markdown and JSON in `data/`; consumers add the repo as a git submodule and read `data/` directly.

**Tier 2's scope is now externally defined.** Its coverage target is the RESOURCES list on the last page of the Annual Unit Charter Agreement (form 524-956, 2026 edition) – the document a chartered organization signs, which enumerates the publications governing a unit. This replaced an ad-hoc set that had no authority behind it and no signal for when it was complete. **Re-pull the form and diff its list against `POLICIES` at the start of each charter year.** The list is a floor, not a ceiling: the GSS operational chapters (aquatics, camping, AHMR) are not named in it and are deliberately kept.

**Two label checks guard the hand-maintained URL table** in `fetch_policies.py`, after two separate bugs shipped files whose bodies did not match their names. Check A is static (`python3 fetch_policies.py --check-labels`, exits non-zero) and runs at the start of every Tier 2 build; Check B is a post-fetch warning. Both currently pass. See `docs/PLAYBOOK.md` for what they do and, more usefully, what they do not cover.

**Provenance lives in `docs/PLAYBOOK.md`, not in `manifest.json`.** As of 2026-09-05 the manifest's `notes` field is a fixed generated pointer. Every other manifest field is machine-generated and consumers read `bsa_version` from it.

### Open items

| Item | State | Blocks |
|---|---|---|
| Four policy files still at `fetched: 2026-03-03` | `two-deep-leadership`, `reporting-youth-protection`, `aquatics-safety`, `camping-permissions`. Content verified clean in August; only the dates are stale, because a non-`--force` build skips existing files | Nothing hard. Resolves on the next full `--force` refresh |
| ~~Consumer pointers behind~~ | **Resolved 2026-09-07**, in the consumer repos rather than here. `scoutsync` bumped in `0a43411`, `troop-452-scouting-tool` in `fbb05b9`; both now pin `e5fe343`, and troop-452 pins `scouting-reference` at `1a10d2f` | Nothing |
| Tier 3 not implemented | Roles and program manuals. No `fetch_roles.py` | Any consumer needing role/manual content |
| Council audit is not automatable | `fetch_councils_authenticated.py` needs a human logged into my.scouting.org; deliberately not wired into `build_all.py` | A true council refresh. The quarterly automated pass cannot catch renames or dissolutions |
| PDF policy entries get no Check B | `charter-and-bylaws`, `rules-and-regulations` are Check-A-only – no heading to compare against | Nothing. Known and accepted gap |
| `section_pattern` in `fetch_ranks.py` is dead config | Nothing reads it; `split_combined_pdf()` has its own dict, and the two disagree (`EAGLE SCOUT RANK` vs `EAGLE RANK`) | Nothing today. A trap for a maintainer who edits it in good faith |
| Next quarterly refresh | Due October 2026 | – |

### Do not re-litigate without escalating

- **The Brand Center is deliberately not scraped.** It is on the charter's RESOURCES list, but it is a WebDAM asset portal of logos and images behind a consent gate, with no policy prose to capture. Unit-facing brand guidance belongs in `scouting-reference`, the curated tier.
- **The governance PDFs are deliberately scraped into this tier** rather than curated downstream, after verifying they extract cleanly. Tier 2 is the scraped tier; hand-authored markdown in `data/` is destroyed on the next rebuild. The curated complement exists separately in `scouting-reference`.
- **A 403 from scouting.org means throttled, not gone.** Do not drop a URL from `POLICIES` on a 403 — verify it in a real browser, or with `./scripts/fetch-page.sh <url> --check`, first. And do not "fix" a 403 by switching the scraper's fetch to `requests`/`curl`. The reason is *not* that a plain client is blocked: re-tested 2026-09-10, bare curl and headless Chromium both return `200` with real content on scouting.org pages. The reason is load. Those are **single fetches**; a build issues hundreds of requests, and this host's observed failure mode is throttling under sustained load, which nothing has measured. `_goto_with_retry()` and the CDP path stay. Full data in `docs/PLAYBOOK.md`, "An access failure is dated, client-specific, and here load-specific."

---

## Session Log

### 2026-09-07 – Session closed; consumer drift resolved elsewhere

**Done:** Session wrap-up. Re-verified Current State against the repo rather than trusting the previous write: counts unchanged (228 / 7 / 142 / 16), manifest still `2026.Q3` / `tier_built: 2`, Check A green on all 16 entries, four policy files still at `fetched: 2026-03-03`.

**Discovered:** the consumer pointer drift flagged on 2026-09-05 has been **resolved in the consumer repos by other sessions**, not here – `scoutsync` in `0a43411` and `troop-452-scouting-tool` in `fbb05b9`, both committed and pushed. The open-items row said "5 commits back" and "2 back"; it was already wrong by one commit when written, because the count was taken before the commit that carried it landed. Worth noting as a live example of why this file's own rule is to re-verify Current State rather than trust either copy.

**Needs Studio review:** nothing. The 2026-09-05 entry's outstanding item – consumer pointer bumps – is discharged.

### 2026-09-05 – Session lifecycle retrofitted; provenance moved out of the manifest

**Done:** Added this file. Moved `manifest.json`'s hand-maintained `notes` content verbatim into `docs/PLAYBOOK.md` as a dated entry and changed `build_all.py` to write a fixed generated pointer instead. Documented the optional `note:` frontmatter key in `CLAUDE.md`. Added a supersession header to `SESSION_LOG.md` naming which of its contents are still accurate.

**Discovered:** `note:` is carried by five files, not four – `data/councils/councils.md` has one as well as the four policy files. Both consumer repos are pinned behind and will show drift after this commit.

**Needs Studio review:** consumer pointer bumps for `scoutsync` and `troop-452-scouting-tool` – deliberately not done here.

### 2026-09-05 – Label checks for mislabeled policy files

**Done:** Added Check A (static slug-versus-entry) and Check B (post-fetch name-versus-document) to `fetch_policies.py`, with an allowlist keyed by `(slug, check)` and a written reason per entry. Both historical bugs replayed from git history to prove each check fires.

**Discovered:** proving the checks could fail caught two bugs in the checks themselves – a mangled `</h\1>` backreference that made Check B structurally incapable of matching while reporting "ok" on all 16 entries, and rich markup silently eating the slug from the warning output. `fetch_ranks.py` needs no equivalent check, and its `section_pattern` field turns out to be dead config.

**Needs Studio review:** nothing.

### 2026-09-05 – Tier 2 scope redefined from the charter agreement

**Done:** Adopted the Annual Unit Charter Agreement's RESOURCES list as Tier 2's coverage target. Policies went from 8 files to 16. Renamed `chartered-organization.md` to `scouter-code-of-conduct.md` and fixed the entry that produced it. Added PDF extraction, 403 retry with backoff, and a cross-origin fix for PDFs hosted off `www.scouting.org`. Wrote three curated syntheses of the governance documents in the sibling `scouting-reference` repo.

**Discovered:** scouting.org serves intermittent 403s to an automated browser, and `/about/*` paths trip it hardest – a 403 there means throttled, not missing. (Still holds. Amended 2026-09-10: the corollary this was written alongside — that plain curl and headless Chromium are permanently blocked — is false; both return `200` on single fetches. The intermittency-under-load finding is the part that survives.) `build_all.py` was silently erasing the manifest's `notes` field on every run, and `fetch_policies` was reporting files fetched rather than files present, understating the manifest count.

**Needs Studio review:** nothing outstanding; the scope decision came from the Studio.
