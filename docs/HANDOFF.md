# Handoff – scouting-kb

> **Owned by the Tactical Architect in this repo.** The Studio reads it at resume, before its own handoff file.
>
> **Two sections, handled differently.** Current State is **overwritten** every session so it is always true right now. The Session Log is **appended** so it stays historical. A pure log cannot answer "where are we" without reading everything and reconstructing it, which is the problem this file exists to solve.
>
> **On a merge conflict:** keep both Session Log entries, ordered **newest first**. For Current State, take the newer one **and re-verify it against the repo** rather than trusting either copy. That is cheap here – the counts and dates below are all readable from `data/` and `data/manifest.json` in a few seconds – and a state doc is exactly the kind of file that goes confidently stale.

---

## Current State

**As of:** 2026-09-13 \
**Corpus version:** 2026.Q3, `built: 2026-09-13`, `tier_built: 2`, `forced: true` – Tiers 1 and 2 both force-rebuilt today \
**Tier 1:** built – councils 228, ranks 7, merit badges **144** \
**Tier 2:** built – policies 16, all at `fetched: 2026-09-13` \
**Tier 3:** not implemented (roles, program manuals)

This is a data package, not an app. The scraper in `scraper/` produces versioned markdown and JSON in `data/`; consumers add the repo as a git submodule and read `data/` directly.

**Tier 2's scope is now externally defined.** Its coverage target is the RESOURCES list on the last page of the Annual Unit Charter Agreement (form 524-956, 2026 edition) – the document a chartered organization signs, which enumerates the publications governing a unit. This replaced an ad-hoc set that had no authority behind it and no signal for when it was complete. **Re-pull the form and diff its list against `POLICIES` at the start of each charter year.** The list is a floor, not a ceiling: the GSS operational chapters (aquatics, camping, AHMR) are not named in it and are deliberately kept.

**Two label checks guard the hand-maintained URL table** in `fetch_policies.py`, after two separate bugs shipped files whose bodies did not match their names. Check A is static (`python3 fetch_policies.py --check-labels`, exits non-zero) and runs at the start of every Tier 2 build; Check B is a post-fetch warning. Both currently pass. See `docs/PLAYBOOK.md` for what they do and, more usefully, what they do not cover.

**Access claims in this repo are dated, client-specific and load-specific — never properties of the source.** Corrected 2026-09-10 after the Studio found the "scouting.org is permanently Cloudflare-blocked" lesson false. Bare curl and headless Chromium both return 200 with real content on scouting.org pages, and bare curl downloads valid PDFs from `www.scouting.org` and `filestore.scouting.org` alike. **The scraper keeps `_goto_with_retry()` and the CDP path anyway** — that evidence is single fetches, a build issues hundreds of requests, and this host throttles under sustained load. Do not read the corrected claims as an argument for simplifying the client. See `docs/PLAYBOOK.md`, "An access failure is dated, client-specific, and here load-specific."

**A `data/` file can be a faithful scrape of a stale source.** Added 2026-09-13: Citizenship in Society was discontinued effective 2026-02-27 (Eagle-required set 14 → 13), but the rank requirements PDF this repo scrapes, the 2026 Scouts BSA Requirements book, and the badge's own page all still show the old program. `data/ranks/eagle-scout.md` and `data/merit-badges/citizenship-in-society.md` now carry a `note:` saying so. **Citizenship in the Community was not affected and is still Eagle-required** – it was the subject of the query that found this. The `eagle_required` flags were already correct; they are read from the live eagle-required index on every build. See `docs/PLAYBOOK.md`, "A program change can outrun BSA's own published source."

**Provenance lives in `docs/PLAYBOOK.md`, not in `manifest.json`.** As of 2026-09-05 the manifest's `notes` field is a fixed generated pointer. Every other manifest field is machine-generated and consumers read `bsa_version` from it.

### Open items

| Item | State | Blocks |
|---|---|---|
| ~~Four policy files at `fetched: 2026-03-03`~~ | **Resolved 2026-09-13** by the forced Tier 2 pass. All four came back byte-identical apart from `fetched:` and `bsa_version:`, which independently confirms August's manual verdict that their content was clean | Nothing |
| ~~Lazy-load placeholders in two policy files~~ | **Resolved 2026-09-13**, and the exemption is gone rather than widened: the real URL was in each element's `data-src` all along, so extraction now restores `src` instead of deleting the image. Merit badge files still have placeholders *dropped* and will gain real image URLs at the next Tier 1 rebuild | Nothing |
| ~~Consumer pointers behind~~ | **Resolved 2026-09-07**, in the consumer repos rather than here. `scoutsync` bumped in `0a43411`, `troop-452-scouting-tool` in `fbb05b9`; both now pin `e5fe343`, and troop-452 pins `scouting-reference` at `1a10d2f` | Nothing |
| Tier 3 not implemented | Roles and program manuals. No `fetch_roles.py` | Any consumer needing role/manual content |
| Council audit is not automatable | `fetch_councils_authenticated.py` needs a human logged into my.scouting.org; deliberately not wired into `build_all.py` | A true council refresh. The quarterly automated pass cannot catch renames or dissolutions |
| PDF policy entries get no Check B | `charter-and-bylaws`, `rules-and-regulations` are Check-A-only – no heading to compare against | Nothing. Known and accepted gap |
| `section_pattern` in `fetch_ranks.py` is dead config | Nothing reads it; `split_combined_pdf()` has its own dict, and the two disagree (`EAGLE SCOUT RANK` vs `EAGLE RANK`) | Nothing today. A trap for a maintainer who edits it in good faith |
| Sustained-load behaviour — **measured for CDP, still open for headless** | Forced Tier 1 rebuild 2026-09-13 over CDP/real Chrome: ~150 sequential requests (2 index pages, 1 combined rank PDF, 144 badge pages), **zero 403s, zero retries**. That is the path the scraper already uses, so it validates the status quo rather than the alternative — nobody has run a bulk pass with bare `curl` or headless Chromium, and this result says nothing about those | Nothing. The `_goto_with_retry()`/CDP defence is now backed by a measurement instead of an assumption |
| ~~Art and Golf missing from the corpus~~ | **Resolved 2026-09-13.** Cause: `_BADGE_LINK_JS` required an anchor name longer than 5 characters, so "Art" and "Golf" were never crawled. Bound removed (the `/skills/` rule already excluded the nav links it guarded against); incremental Tier 1 build fetched both. Corpus now 144 | Nothing |
| Two `note:` annotations are keyed to upstream staleness | The Eagle Scout `RANKS` note and `BADGE_NOTES["citizenship-in-society"]` both describe a lag in BSA's own documents. Drop each once upstream catches up – the rank PDF reissued with 13 badges, the badge pulled from the A-Z index | Nothing. Re-check at each refresh |
| Next quarterly refresh | Due October 2026. Both tiers were force-rebuilt 2026-09-13, so October is a routine pass. Expect a merit badge diff then from the lazy-image change alone | – |

### Do not re-litigate without escalating

- **The Brand Center is deliberately not scraped.** It is on the charter's RESOURCES list, but it is a WebDAM asset portal of logos and images behind a consent gate, with no policy prose to capture. Unit-facing brand guidance belongs in `scouting-reference`, the curated tier.
- **The governance PDFs are deliberately scraped into this tier** rather than curated downstream, after verifying they extract cleanly. Tier 2 is the scraped tier; hand-authored markdown in `data/` is destroyed on the next rebuild. The curated complement exists separately in `scouting-reference`.
- **A 403 from scouting.org means throttled, not gone.** Do not drop a URL from `POLICIES` on a 403 — verify it in a real browser, or with `./scripts/fetch-page.sh <url> --check`, first. And do not "fix" a 403 by switching the scraper's fetch to `requests`/`curl`. The reason is *not* that a plain client is blocked: re-tested 2026-09-10, bare curl and headless Chromium both return `200` with real content on scouting.org pages. The reason is load. Those are **single fetches**; a build issues hundreds of requests, and this host's observed failure mode is throttling under sustained load, which nothing has measured. `_goto_with_retry()` and the CDP path stay. Full data in `docs/PLAYBOOK.md`, "An access failure is dated, client-specific, and here load-specific."

---

## Session Log

### 2026-09-13 – Forced Tier 2 refresh; lazy-load placeholders resolved, not stripped

**Done:** `build_all.py --tier 2 --force --cdp-url`. 16/16 policies, no 403s, no retries. Both remaining open items closed. Added `_RESTORE_LAZY_IMAGES_JS` to `utils.py`, wired into `extract_content()` and `extract_merit_badge_content()`.

**Discovered:**
- **The exemption was a limit of the tool, not a property of the content.** `clean_markdown()` deleted bare placeholders and deliberately spared two shapes — one with alt text, one wrapped in a real link whose URL deletion would have taken with it. That reasoning was sound and it was also a signal nobody followed: the real image URL sits in `data-src` on every one of them (23/23 across two pages). Restoring the source fixes all three shapes and loses nothing. **Re-read a deliberate exemption when the area around it changes — the reason it was written is not the reason it persists.**
- **The four policy files stranded since March came back byte-identical** apart from `fetched:` and `bsa_version:` (they were still stamped `2026.Q1`). That is a second, independent confirmation of August's manual verdict on them.
- **The build log shows no label-check output, and the checks did run.** `fetch_policies()` calls `report_slug_check()` before any network work; both checks are silent on pass. Verified at the call site rather than inferred from the log — the absence of output from a guard is indistinguishable from a guard that stopped running until you read the code.

**Consumers bumped, same session:** `scoutsync` `e5fe343` → `c244e0d` (`7fdc431`) and `troop-452-scouting-tool` `e6e6e9c` → `c244e0d` (`cc7aa33`), both pushed. scoutsync's was five commits of drift that included the Eagle-required correction, so until the bump its `BsaPanel` served the old 14-badge picture to real users — the failure its own CLAUDE.md documents from 2026-08-05. Content verified in both rather than the pointer; `pnpm build:web` green, so every `contentPath` still resolves.

**Needs Studio review:** nothing.

### 2026-09-13 – Forced Tier 1 rebuild: 7 ranks, 144 badges, zero 403s

**Done:** `build_all.py --tier 1 --force --skip councils --cdp-url http://localhost:9222`, real Chrome over CDP. 7/7 ranks, 144/144 badges, 151 files changed, no errors. Added `--skip` to `build_all.py` so councils can be excluded by flag rather than by hand: a forced Tier 1 run otherwise puts the zip-sampling fetcher over the authoritative 228-council file, a silent 40% loss. Verified by checksum that `councils.json` is byte-identical after the run.

**Discovered / measured:**
- **Zero 403s and zero retries across ~150 sequential requests** over the CDP path. This closes the sustained-load question *for the path the scraper already uses* and for nothing else – no bulk pass has ever been run with bare `curl` or headless Chromium, so the 2026-09-10 single-fetch results still do not generalise. The defence is now backed by a measurement rather than an assumption; the assumption it replaces was that we would see throttling, and we did not.
- **All 7 rank files regenerate byte-identically apart from the `fetched:` date.** That is a free determinism check on the whole PDF pipeline – `dedupe_chars`, two-column reconstruction, footnote handling, the rebuilt merit badge table, and the new note injection all reproduce exactly.
- **The badge diff is entirely upstream copy editing by BSA**, not extraction drift: trailing periods dropped from requirement clauses, title-case fixes in resource link text, `?si=` tracking parameters stripped from YouTube URLs, one stray decorative placeholder image gone from `dog-care`. Read the largest diffs individually to confirm it.
- **Both `note:` annotations and the index `## Notes` section regenerate from the scraper**, which is the point of having put them there rather than hand-editing `data/`.

**Needs Studio review:** nothing.

### 2026-09-13 – Incremental Tier 1 build: Art and Golf added, three latent build bugs fixed

**Done:** Ran `build_all.py --tier 1` (incremental, headless, no CDP) to close the Art/Golf gap found earlier the same day. Corpus is now **144 merit badges**; `manifest.json` reads `built: 2026-09-13`, `tier_built: 1`. Councils and ranks were skipped as intended – the authoritative 228-council file was not touched, and ranks correctly refused to run without `--cdp-url`.

**Discovered:** the gap was a one-line filter – `_BADGE_LINK_JS` required an anchor name longer than 5 characters, so "Art" (3) and "Golf" (4) were never crawled. Removing the bound yields exactly 144 unique badge URLs and no junk; the short-named badges already present (Chess, Law, Music, Pets, Radio) were there only because a second anchor carried longer text. Getting the build to run also exposed **three latent bugs that only fire on the incremental path**, which this repo had never exercised: `manifest.json`'s `counts` were written from each fetcher's per-run fetch count and would have recorded `merit_badges: 2`; the badge index page never reaches `networkidle` headless and timed out the build one line above the `load` fallback the per-badge loop has always had; and `index.md` took display names from the day's anchor text for every skipped badge, which relabeled `genealogy.md` as "Geology" and appended "(numbers changed)" / "(new)" / "(formally Indian Lore)" to three others. All three fixed, with the index re-run diffing to exactly two added rows. **The forced path and the incremental path are different programs – run the one you don't normally run before trusting it, and diff `data/` rather than reading the summary table, which reported OK for the run that relabeled Genealogy.**

**Needs Studio review:** nothing.

### 2026-09-13 – Citizenship badge verification; `note:` extended to ranks and merit badges

**Done:** Verified a user claim that "Citizenship in the Community is no longer required." **The claim was wrong about that badge and right about its neighbour** – Citizenship in the Community is still Eagle-required (present on the live eagle-required index and as #2 on the 2026 Eagle Scout Rank Application). **Citizenship in Society** is the badge Scouting America discontinued, effective 2026-02-27: Eagle-required set 14 → 13, electives 7 → 8, total still 21, with a grandfathering window to 2026-12-31 for Scouts who had already started it. Added `inject_note()` to `utils.py` and wired a `note` key into `fetch_ranks.py` (`RANKS` entries) and `BADGE_NOTES` into `fetch_merit_badges.py`, then annotated `data/ranks/eagle-scout.md` and `data/merit-badges/citizenship-in-society.md`; `data/merit-badges/index.md` gained a generated `## Notes` section. No scraped text was edited and no `fetched:` date moved – nothing was re-fetched.

**Discovered:** scouting.org disagrees with itself, per-document. The eagle-required index and the current application form carry the change; the rank PDF (`last-modified: 2025-12-11`), the 2026 requirements book (uploaded 2026-02) and the badge's own live page do not. The repo had faithfully scraped the losing half. **An authoritative source is authoritative per-document and per-date, never site-wide.** Also: the eagle-required page lists 17 badges for 13 slots because three are either/or – not a contradiction. `inject_note()` was validated by round-tripping the three existing policy files that already carry a note (byte-identical), with a negative control proving a wrong note does not match; its idempotency check failed first time (a stacked blank line) and was fixed before use. Incidentally found the corpus is missing the **Art** and **Golf** badges – logged as an open item, not fixed here, since it needs a scrape run.

**Needs Studio review:** nothing. The Art/Golf gap and the two staleness-keyed notes are recorded as open items for the October refresh.

### 2026-09-10 – Access-failure claims narrowed, not reversed; folklore swept from the code

**Done:** Corrected four documented claims that had drifted into folklore, after the Studio found its own "permanently Cloudflare-blocked" lesson false. Re-tested each client separately: bare curl and headless Chromium both return 200 with real page bodies on scouting.org (3/3 each, including `/about/governance/charter/`, which 403'd four times headless on 2026-09-05), and bare curl downloads valid PDFs from both `www.scouting.org` (1,190,527 bytes / 15 pages) and `filestore.scouting.org` (431,902 bytes / 28 pages). Fixed `PLAYBOOK.md:41` and `:200`, `HANDOFF.md:43`, and `CLAUDE.md`'s 403 entry; added the standing rule to `CLAUDE.md` and `PLAYBOOK.md`. Then swept the surrounding sections and `scraper/`: nine strings corrected across `utils.py`, `fetch_ranks.py`, `fetch_policies.py` and `build_all.py`. **No behaviour changed** – `--cdp-url` is still required by `fetch_ranks` and still the right default for bulk runs, now justified by throttling rather than by a block. Commits `381dba7`, `30cbf79`, `ac264a7`.

**Discovered:** two distinct error classes, not one. A **stale observation** was true once and is false now (curl, headless). An **invented mechanism** was never true – the 403s explained as the site "gating on a browser session," and `download_pdf()` explained as "clearance doesn't reach the CDN," which bare curl actively contradicts. The second kind survives because a real premise sits beside it keeping the conclusion true, so nothing ever presses on the invented half. **A correct conclusion does not validate its premises.** One flagged line led to three more in the paragraphs around it and eight in `scraper/`, including a user-facing error message asserting Cloudflare "blocks all automated downloads" – **sweep executable artifacts first**, since folklore in an error string fires exactly when someone is deciding whether a source is reachable. Also: take a verification phrase from the page, not from memory – grepping `gss01` for "two-deep leadership", this repo's own wording, returned zero hits on a perfectly good fetch, a false negative indistinguishable from a block. `SESSION_LOG.md` was left uncorrected on purpose: correct live guidance, never the historical record, or the audit destroys the evidence for judging the decision later.

**Verified against the repo, not the previous write:** counts unchanged (228 / 7 / 142 / 16), manifest still `2026.Q3` / `built: 2026-09-05` / `tier_built: 2`, four policy files still at `fetched: 2026-03-03`.

**Needs Studio review:** nothing outstanding. The Studio drove this session and has amended its own entries (`40f105c`, `b82345b`, `b53ec79`).

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
