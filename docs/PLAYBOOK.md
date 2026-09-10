# PLAYBOOK — scouting-kb

Longer-form scraper patterns and incident writeups. See CLAUDE.md for short, stable operating rules; this file is for the detailed "here's what broke and why" record.

## Council list was a 200-zip sample, not a canvas — 91 councils missing (found 2026-08-02)

**How this started:** the user asked for a "quick pass" to verify council data was still correct, and mentioned finding a "council/district search" tool at `my.scouting.org/tools/manage-member-id` while logged into their own BSA account. That tool requires personal login — not something to access autonomously — but the user offered to log in themselves in a CDP-connected Chrome window and let the investigation proceed from there.

**What the public API actually offers:** confirmed via direct requests that every "list" or "by state" variant of `api.scouting.org/organizations/v2/...` returns `401 Missing JWT Token` — only the single-zip lookup (`/organizations/v2/zip/{zip}/council`) is public. `fetch_councils.py`'s ~200-zip sampling approach was already the practical ceiling for an unattended, unauthenticated script.

**What the authenticated session revealed:** once the user logged in, their session's JWT unlocked `api.scouting.org/organizations/councils` — the actual "list all councils" endpoint. **228 real local councils, vs. 137 in the committed data — a 91-council gap (40%).** Matching by the council number embedded in each name (e.g. "Abraham Lincoln Council 144" -> `144`) against the existing `id` field, 135 of 137 matched cleanly (confirming this is a reliable join key), but 2 existing entries had no match at all:
- **South Plains** (`694`, Lubbock, TX) — no successor council found nearby in the new list.
- **Black Hills Area** (`695`, Rapid City, SD) — South Dakota now shows only one council, "Sioux Council 733" (Sioux Falls). Real BSA council consolidation, not a data bug.

Also found via name comparison on the 135 matched IDs: at least 2 **renames** the old zip-sampling approach could never have caught (a zip code that used to resolve to the old name still resolves to *a* council after a rename — nothing about a resample would flag that the name changed):
- `047`: "Golden Empire" -> **"Greater California"**
- `303`: "Andrew Jackson" -> **"Mississippi Riverlands"**

**How to get this data:** the browser autocomplete on the "Council Name or Location" field (used when adding a Member ID) doesn't call a search-as-you-type API — it filters a list already loaded into the page's own JS state on load. Reloading the trigger page (`my.scouting.org/tools/manage-member-id`) with response-capture attached from the start caught the real call: `GET https://api.scouting.org/organizations/councils`, authorized via `Authorization: bearer <JWT>` — a header the app's own fetch wrapper attaches from JS-held state, not from cookies. A plain `fetch(url, {credentials: 'include'})` from the same authenticated page still got `401` — cookie-based `credentials: 'include'` doesn't replicate a bearer-token auth scheme; you have to either capture the real request's headers (what the fix does) or read the JWT out of wherever the app stores it.

**Two smaller wrinkles found while building the clean-name extraction** (`clean_council_name()` in `fetch_councils_authenticated.py`):
- Naming suffix isn't consistent: "Council 144", "Council-BSA 004", "Council, BSA 104", "Councils, BSA", or nothing at all (just a bare name + number). Handled with one regex for the trailing number and a separate, optional one for a trailing "Council(s)" + BSA variant.
- One record, `"Hoosier Trails Council #145 145"`, has a **doubled trailing number** — apparently a data-entry quirk in BSA's own system, not an extraction bug. A single strip-number-then-strip-Council pass leaves `"...Council #145"` dangling, because the redundant `#145` isn't at the string's end anymore once the outer `" 145"` is removed, so the "Council" suffix regex can't reach past it. Fixed by looping both strips to a fixed point (stop when a pass produces no change) instead of assuming one pass suffices.
- One entry, `id="000"`, name `"National"` — a BSA administrative placeholder in this API's response, not a real chartering council (never appeared in the old zip-sampled data, since a zip lookup can't map to something non-geographic). Explicitly excluded.
- Two real overseas councils have no US state: **Far East** (`803`) and **Transatlantic** (`802`, using the real USPS military-address code `AE`). Kept — these represent real Scouting for military families abroad, not data errors — `AE` was added to the state-code map.

**Decision point, resolved by the user:** the authenticated endpoint only returns `id`/`name`/`city`/`state` — no address/zip/phone/website/email, which the old zip-sampled data has. Asked the user whether to do a clean rebuild (drop those fields entirely, for a consistent dataset) or a merge (keep detail for the 135 matched councils, leave the 93 new/renamed ones bare). **User chose the clean rebuild** — all 228 records now have `address`/`zip`/`phone`/`website`/`email` uniformly `null`, rather than a confusing mix of detailed and bare records that could look like an implementation bug.

**Fix:** new `fetch_councils_authenticated.py`, deliberately **not** wired into `build_all.py`'s automated tier flow — it cannot run unattended, since the JWT only exists after a human logs in. Documented setup steps in its own module docstring (launch CDP Chrome, log in yourself, point the script at that session). `fetch_councils.py` (the original zip-sampling script, still used by `build_all.py`) now has an updated docstring pointing here for a more complete refresh whenever a human is available to log in.

**Verification method:** wrote the name-cleaning + comparison logic first as an ad-hoc scratch script against a one-off captured response, manually checked every edge case found (duplicate-number record, "National" placeholder, no-state overseas councils, unmapped state codes) — then built the *real* reusable script and re-ran it end-to-end against the live session, diffing its output against the scratch-verified data. Byte-identical, confirming the productized script actually does what the ad-hoc investigation validated, not just "probably the same logic."

**Lesson for future scraper work:** "the public API doesn't support X" doesn't always mean X is impossible — it can mean X requires auth the human already has via their own account, which is a legitimate (if not automatable) data source when the human is willing to drive it. Don't assume the unattended-scraping ceiling is the data ceiling.

## Root-relative links preserved verbatim, dead outside a browser (found 2026-08-02)

**Symptom:** user flagged `guide-to-safe-scouting.md`'s "VIEW THE ONLINE VERSION" link as broken — it pointed at `/health-and-safety/gss/toc`, a root-relative path with no domain. A repo-wide grep for `](/...)` (single leading slash, excluding `//` and `http(s)://`) found 13 such links across 3 files total: `guide-to-safe-scouting.md`, `youth-protection-training.md`, `annual-health-medical-record.md`. Merit badges and ranks had zero — this pattern only showed up on some policy pages' source HTML.

**Root cause:** `markdownify` preserves an `<a href>`/`<img src>` exactly as written in the source HTML. A root-relative href resolves fine in a live browser (against the page's own origin) but has no base URL to resolve against once it's sitting in a standalone markdown file — it's not actually a broken/moved page, just missing the domain.

**Verified, not assumed:** fetched all 10 distinct paths via the CDP-connected browser — every one resolved to a real `200` page once `https://www.scouting.org` was prepended, confirming this was purely an extraction gap, not actual dead links.

> **Amended 2026-09-10.** This entry used to add "(plain `curl` gets a 403 from Cloudflare, per this repo's usual pattern)". That was an undated claim about the *source*, and it is false as written. Re-tested 2026-09-10 from this machine: bare `curl`, no headers, returned `200` with real page bodies on `/health-and-safety/gss/gss01/`, `/about/faq/question10/` and `/about/governance/charter/`, 3/3 attempts each, and `/health-and-safety/gss/toc` `301`s to its trailing-slash form and then `200`s. The CDP browser was used on 2026-08-02 because it was already running, not because curl was proven blocked. See “An access failure is dated, client-specific, and here load-specific” below.

**Fix:** `absolutize_relative_links()` in `utils.py` — a small regex prepending the site's base URL to any `](/single-slash-path)` match — wired into both `fetch_policies.py` and `fetch_merit_badges.py` right after their markdownify + cleanup steps (merit badges had zero instances of this currently, but the same `markdownify`-preserves-hrefs-verbatim mechanism applies there too, so it's wired in defensively for whenever a future page does have one). Applied directly as a text post-process to the 3 already-fetched files rather than re-scraping, since it's pure string manipulation.

**Also checked and clean:** no empty links (`]()`), no bare anchor-only links (`](#)`) anywhere in `data/`.

## Policies pass never actually re-verified 4 of 7 files, and one had real junk (found 2026-08-02)

When the nav/script-leak bug (see below) was first fixed, all 7 policy files were re-fetched to a scratch directory and diffed against the committed versions — 3 were corrupted and got copied into `data/`, and the other 4 came back "byte-identical," so nothing was copied for them. That was true at the time, but it meant those 4 files' `fetched:` frontmatter stayed frozen at the original `2026-03-03` date and were never actually re-verified again after later fixes — they just happened not to need the nav/script fix specifically.

A manual re-check of all 7 found `youth-protection-training.md` had a different, previously-missed problem: the page embeds a "find your council" search widget — raw `window.onload`/jQuery JS plus a dozen empty result-form labels ("Council Number :", "Address :", "Search Result", etc.) — directly inside the article's own content column, not inside a `<nav>`/`<header>`/`<form>` element `extract_content()`'s DOM-cleanup already strips. Confirmed by checking `find_tables`-style DOM inspection: the widget's wrapping `<div>` has only an auto-generated Elementor ID, no stable class, so it can't be targeted generically the way header/nav/footer chrome can. Fixed with a targeted text-level regex (`_strip_council_locator_widget()` in `fetch_policies.py`) matching this specific widget's start/end text — this repo already has real council data in `data/councils/councils.json`, so the widget was never going to be interactive in a static markdown file anyway. The other 3 previously-unverified files (`camping-permissions.md`, `reporting-youth-protection.md`, `two-deep-leadership.md`) were re-fetched and confirmed byte-identical to what's committed — genuinely clean, not just previously-unlucky.

Also fixed in the same pass: this same page never reaches `networkidle` (the widget's JS keeps the network "active" indefinitely) — `fetch_policy_page()` in `fetch_policies.py` now falls back to `wait_until="load"` + a 2s pause, the same pattern already used elsewhere in this repo (merit badge pages, some rank PDFs) for pages that never settle.

**Lesson: "byte-identical when re-tested" only proves a file didn't need the *specific* fix being tested at the time — it's not the same as "this file has been fully audited."** A page-embedded widget with no removable DOM signature can coexist with an otherwise-correctly-selected content block indefinitely; only actually reading the rendered content (not diffing against a known-bad baseline) catches it.

## Rank PDF readability round 2: blank-line-before-heading, position-category lists, accurate table row counts (found 2026-08-02)

Found via the user manually reading the *rendered* output (not just the raw markdown) against the original PDF, page by page — several issues that only show up when actually rendering, not when eyeballing markdown source.

**1. Missing blank line before `## Notes` merged the whole Notes section into the last requirement.** The earlier fix (see the entry below) converted `Notes:` to a `## Notes` heading but didn't ensure a blank line preceded it. `pandoc -f gfm` is lenient enough to still parse it as a heading either way (confirmed: `<h2>` rendered as a sibling of `</ol>`, not nested inside the last `<li>`) — but the user's actual renderer was not that lenient, and showed the entire Notes section, footnotes and all, swallowed into the last requirement's list item. Fixed by prefixing the heading substitution with `\n`. **Lesson: pandoc's leniency isn't a stand-in for "renders correctly everywhere" — the blank-line-before-heading rule should just always be followed, regardless of whether the specific verification renderer complains.**

**2. "Positions of responsibility" category lists reformatted into a bulleted sub-list.** Star, Life, and Eagle Scout each have a requirement listing three fixed membership categories — always exactly "Scout troop.", "Venturing crew/Sea Scout ship.", "Lone Scout.", in that order, each followed by its own position list. The source PDF bolds each label; plain text extraction loses that, leaving three runs of prose with no visual break between them. `_reformat_position_categories()` matches this exact, stable BSA template (hardcoded, not generically detected — a generic "short label ending in period, then description" detector would be far more error-prone than matching known, unvarying text) and reformats it as `- **Label.** description`.

  **The gotcha that took three iterations to get right:** Eagle Scout's footnote 11 happens to print immediately after this exact block (a PDF footnote lands wherever it fits on the physical page, not necessarily right after its own reference). Three failed attempts, in order:
  - Leaving the boundary as "next top-level requirement only" let the footnote's raw, not-yet-bolded text get captured *inside* the "Lone Scout." bullet.
  - Extending the boundary to also stop at a footnote-marker line, but with no blank line before what followed, let the (by-then-bolded) footnote text get swallowed by lazy continuation into the last bullet's paragraph anyway.
  - Adding a blank line before it fixed *that*, but the blank line dedented it out of the requirement's own indentation, fracturing the surrounding ordered list into three separate `<ol>` blocks (same failure mode as the mid-body-footnote bug below).

  The fix that actually worked: capture the trailing footnote text (still raw/glued) as part of the same regex, and re-emit it with a blank line *and* matching 3-space indentation — a second paragraph of the same enclosing requirement, not another bullet and not a dedented sibling. This required `_FOOTNOTE_START_RE` (in `_reformat_footnotes()`) to also accept an optional leading indent and preserve it through the bolding substitution, so the two functions compose correctly regardless of which one a given footnote happens to need.

**3. Two-column list reformatted into a nested sub-list, not a flat run of top-level-looking lines.** The two-column reconstruction (see the entry below) originally emitted `a.`/`b.`/... as bare top-level lines, reading as an unrelated list rather than sub-items of the requirement they belong to. Now emitted as `   - a. ...` (3-space indent, matching the requirement's continuation indent) with blank lines around the whole block, so it nests inside the parent requirement's `<li>` instead of floating as a sibling.

**4. Merit badge table row counts were wrong for the "(Eagle-required)" table style — some rows are genuinely blank with zero extractable text.** Life/Star's requirement 3 table has 5 real rows (3 labeled "(Eagle-required)" + 2 completely blank, for scouts to name their own free-choice badges), but the earlier table-building fix (see below) only found 3, since a table cell with literally no text produces nothing for a text-based regex to count. Root cause confirmed by inspecting `page.find_tables()` output directly: `pdfplumber` extracted 15 structural rows for this page's whole tracking-grid, correctly including the 2 blank ones as real (if empty) table cells — the row *grid* exists in the PDF regardless of cell content, it's only `extract_text()` that silently drops empty cells.

  Fixed with `_find_merit_badge_table_row_count()`: uses `page.find_tables()` to locate the "NAME OF MERIT BADGE" header row, then counts forward while the requirement-number column (index 1) stays empty — that column is blank for every tracking row in both table styles seen (bare-number "1."-"10." and "(Eagle-required)"-labeled), and turns non-empty again exactly at the next real requirement. This accurate count gets injected into the per-page text as a hidden `<!--MB_TABLE_ROWS:N-->` marker (right before "NAME OF MERIT BADGE") during `extract_pdf_text()`'s page loop, which `_build_merit_badge_table()` reads and prefers over counting labeled rows, with a safety-net strip in `_clean_rank_pdf_text()` in case the marker ever survives un-consumed.

  **Lesson: when a page has real table structure, use `page.find_tables()`/`page.extract_tables()` instead of inferring row counts from `extract_text()` output — text extraction only sees what has text, not the underlying grid.** This also means `find_tables()` is worth trying earlier in future PDF-parsing work here, rather than defaulting straight to text-based extraction and patching around what it misses.

**Verification method, again: render with `pandoc -f gfm` and check the actual DOM nesting** (which `<li>`/`<ul>`/`<ol>` a given piece of text ends up inside), not just whether the visible text looks right — several of these bugs produced text that looked fine in isolation but was structurally attached to the wrong parent element.

## Rank PDF readability: fill-in table as a real table, two-column lists, glued footnotes (found 2026-08-02)

Three further readability fixes to `fetch_ranks.py`'s PDF extraction, found by manually reading the rendered output rather than grepping for junk patterns — none of these were "wrong data," just markdown structure that reads badly or renders incorrectly.

**1. Blank fill-in table, upgraded from an omission note to a real GFM table.** The earlier fix (see the entry below) replaced the blank "NAME OF MERIT BADGE / DATE EARNED" tracking rows with a descriptive note saying they'd been omitted. Better: rebuild them as an actual table (`_build_merit_badge_table()`), with the correct row count (3/4/10 depending on rank) and blank cells — preserves the "here's a blank form" semantic instead of just saying it existed. **Gotcha:** GFM pipe tables need a blank line before them or they get absorbed into the preceding paragraph as literal pipe characters instead of parsing as a table — easy to miss since the table *looks* right in the raw markdown either way; only rendering it (via `pandoc -f gfm`) revealed the bug.

**2. Two-column lettered sub-lists reconstructed from PDF word coordinates.** Life rank requirement 6 (and potentially other longer flat lists in future PDF revisions) prints as two side-by-side columns in the handbook to save vertical space — a-d on the left, e-h on the right. `pdfplumber`'s plain top-to-bottom `extract_text()` interleaves these into unreadable merged lines (`"a. Tenderfoot 4a and 4b (first aid) e. First Class 4a and 4b (navigation)"` on one line, followed by wrapped fragments in the wrong order). Fixed with `_find_two_column_block()` + `_reconstruct_two_column_block()` in `fetch_ranks.py`: uses `page.extract_words()` coordinates to detect a block (two lettered markers on the same line with a >40pt x-gap), find its true end (the next line whose leftmost word retreats to the outer margin — sub-items are always indented further right than their parent requirement number), find the real column gutter (the single largest gap in the block's merged x-coverage — *not* the gap between the marker words themselves, which undercounts since left-column content runs wider than just the marker), then reconstruct each column top-to-bottom and concatenate left-then-right (which is also correct letter order). Confirmed via `page.crop()`/`within_bbox()` splicing that only this one page needs it — no false positives anywhere else in the combined PDF.

  **Gotcha:** `within_bbox()` requires an object's *exact* (unrounded) bounding box to be fully inside the crop, but the block-boundary detection groups words into lines using `round(top)`. A word whose true top was 559.86 fell outside a crop starting at the rounded 560 and silently vanished from both the "before" and "after" splices — this dropped an entire requirement (Life's #7) on the first pass. Fixed with a small buffer (2pt) on both crop edges.

**3. Glued footnote markers made readable, without fully solving footnote boundaries.** Footnote references glue directly onto the body text with no space (`"...outdoor ethics guide.9"`), and their definitions glue a marker directly onto the definition's first word (`"9Assistant patrol leader..."`) — confusingly, right where a lettered/numbered sub-item marker would normally sit. `_reformat_footnotes()` converts `"Notes:"` into a `## Notes` heading, bolds each footnote's start (`**9.** Assistant patrol leader...`), and rewrites in-body references as a bracketed, spaced marker (`"...guide. [9]"`).

  **What this deliberately does NOT do:** precisely bound where a footnote's content *ends*. Most footnotes are one sentence, but Eagle Scout's footnote 12 ("APPEALS AND EXTENSIONS") runs several paragraphs with nothing to mark where it stops before footnote 13 begins — there's no reliable text-only signal to detect that boundary (a plain sentence-end period doesn't work either: Scout rank's footnote 1 is exactly one sentence, immediately followed by an unrelated, unmarked disclaimer sentence that must NOT be swallowed into footnote 1). Rather than guess and risk merging unrelated text into a footnote, this only marks the unambiguous *start* of each footnote and leaves the rest as normal flowing prose.

  **Gotcha (the one that mattered):** footnotes don't all live in the trailing `Notes:` block — a PDF footnote prints at the bottom of whichever physical page referenced it, so Eagle Scout's footnote 11 sits *mid-list*, between requirements 4 and 5, nowhere near the real `Notes:` section (which only holds footnotes 12 and 13). Applying the same blank-line-plus-bold treatment there split one continuous ordered list into three separate `<ol>` elements. The rendered numbers still happened to come out right (each fragment's first item carried an explicit start value that pandoc honored), but it was fragile and structurally wrong. Fixed by only giving the full blank-line treatment to footnote markers found at or after a `Notes:` occurrence; anything earlier just gets bolded in place with no blank line, so it can't fracture whatever list or paragraph it's embedded in.

  **Known remaining gap, not fixed:** (a) two footnotes on Eagle Scout's Palm Requirements sub-section use asterisk markers (`*`, `**`) instead of digits — left unlinked, same ambiguous-boundary problem as above but for only two low-stakes instances; (b) footnote "8" is referenced inline in Life rank (`"...for the Life rank.8"`) but its definition only exists in *Star* rank's own Notes section — footnotes are apparently shared across a print book's adjacent ranks, but this repo splits the combined PDF into independent per-rank files, so a footnote defined in one rank's section isn't visible when referenced from another. Not fixed since resolving it would mean carrying footnote definitions across section boundaries during the split, reintroducing exactly the kind of cross-section bleed risk fixed by the `dedupe_chars()` work above (life.md wrongly absorbing eagle-scout.md's content). Left as a plain unlinked glued digit rather than fabricating or guessing at a cross-reference.

**Verification method throughout: render with `pandoc -f gfm`, not just eyeball the raw markdown.** `python-markdown`'s default parser doesn't implement CommonMark's lazy-continuation list rules and gave a false negative early on (reported zero `<li>` elements where pandoc correctly found seven) — it isn't safe as a stand-in for how a real renderer will treat this content.

## PDF rank extraction: doubled characters, and one rank's file containing another's content (found 2026-08-02)

**Symptom:** `data/ranks/*.md` had cosmetic artifacts throughout — doubled characters ("LEADER" -> "LLEEAADER", "badges required" -> "baddges requiiredd", even in section headers: "SECOND CLASS RANK REQUIREMENTS" -> "SECOND CLASS RANK REQUIREMENTSS"), unmapped `(cid:22)` checkbox glyphs, and a recurring "LEADER / INITIAL & DATE" column-header block plus bare page-number lines repeating throughout every file. This had been known and accepted as "harmless" (see auto-memory, pre-2026-08-02). It wasn't harmless: `data/ranks/life.md` was 213 lines when it should have been 60 — the entire Eagle Scout rank section (including the Eagle Palm requirements checklist) was wrongly appended after Life's own content ended.

**Root cause — doubled characters:** the source PDF (`Scouts-BSA-Rank-Requirements.pdf`) fakes bold text by drawing the same glyphs twice at a near-identical (but not pixel-identical) position. `extract_pdf_text()` in `fetch_ranks.py` called `page.extract_text(x_tolerance=2, y_tolerance=2)` directly, and the overlapping duplicate glyphs fell just outside that merge tolerance, so both copies survived into the extracted text as doubled letters.

**Root cause — life.md containing eagle-scout.md's content:** `split_combined_pdf()` finds each rank's section by searching the extracted text for its header (e.g. `^EAGLE RANK` for Eagle Scout) and slicing between consecutive header positions; a rank whose header isn't found falls through to `len(full_text)`, silently absorbing everything after it — including subsequent ranks' sections. The doubled-character bug was corrupting "EAGLE RANK REQUIREMENTS" enough, somewhere in the pre-fix extraction, that the boundary regex failed to match it on that pass, so Life's section swallowed all the way to the end of the document. Confirmed by testing: after fixing the doubled-character bug (below), `split_combined_pdf()` reliably found `7/7` section headers and `life.md` correctly stopped at its own last requirement (60 lines).

**Fix:** `pdfplumber.Page.dedupe_chars()` — a built-in method purpose-built for exactly this "same text, same position, count once" case — called on each page before `.extract_text()`. Verified on the real PDF: removed exactly 20 characters out of 41,048 in the full combined document (0.05%), all confirmed to be the doubled-letter artifacts, nothing legitimate. Also added `_clean_rank_pdf_text()` to strip the `(cid:22)` checkbox glyph (an unmapped glyph with no text equivalent — not a dedup issue), the repeated "LEADER / INITIAL & DATE" and "RANK / REQUIREMENTS" page-furniture blocks (15 and 7 occurrences respectively across the combined PDF, both unambiguous and safe to strip), and bare 2-4 digit page-number lines.

**Known minor artifact, not fixed:** two instances of a footnote reference number glued directly to the following word with no space (`"12APPEALS AND EXTENSIONS"`, `"13AGE REQUIREMENT ELIGIBILITY"`) — a PDF superscript-footnote-marker extraction quirk. Only 2 occurrences in the whole document; not worth a regex risky enough to accidentally mangle a legitimate line starting with a number (e.g. a requirement's "(See page 24.)" citation). Left as-is.

**Second bug found verifying this fix (same day): a blank fill-in table broke requirement numbering.** `eagle-scout.md` renders its requirement "4. While a Life Scout..." as "**14.**" in most markdown viewers. Cause: the source PDF has a "NAME OF MERIT BADGE / DATE EARNED" table for the Scout to hand-write extra badges into, which extracts as 10 genuinely empty numbered lines (`1.`, `2.`, ... `10.`, nothing after the period). CommonMark ignores the literal digit text after a list's first item and just increments from there — so those 10 empty rows silently consume item numbers 4 through 13, pushing the real requirement 4 to display as 14. `star.md` and `life.md` have the same blank table but with `(Eagle-required)` placeholder rows instead of bare numbers, which don't collide with list numbering (not valid list-marker syntax) but are equally uninformative. Fixed by replacing the whole blank table (in `_clean_rank_pdf_text()`) with a single descriptive line — `_(blank "Name of Merit Badge / Date Earned" tracking rows in the original form, omitted)_` — instead of empty list markup. Verified with `pandoc -f gfm` (a real CommonMark/GFM renderer — python-markdown's default parser doesn't implement the same lazy-continuation rules and isn't a reliable proxy here) that all three files now render as clean, correctly-numbered 7-item and 3-item lists with no `start=` override needed. Scout/Tenderfoot/Second Class/First Class use letter-suffixed numbering (`1a.`, `1b.`, `2a.`...) for their requirements instead of bare top-level numbers, which isn't valid ordered-list syntax at all — so they were never at risk of this and needed no changes.

**How this was caught:** the user manually spot-checked `data/ranks/eagle-scout.md` after the merit-badge and policy fixes and noticed the same "looks scraped wrong" smell — asked whether it needed a re-scrape. It didn't need a re-scrape in the DOM-extraction sense (this pipeline downloads a PDF, not a web page), but did have a real, previously-undiagnosed bug once actually investigated.

**Lesson for future scraper work:** "harmless" quirks noted in passing are worth periodically re-examining with fresh eyes, especially ones affecting every file in a dataset — `(cid:22)` truly was harmless (an unmappable glyph), but it was sitting right next to a genuinely serious bug (life.md's content corruption) that nobody had actually diffed line counts to catch. When a PDF extraction produces suspicious doubled text, check for a purpose-built library method before writing a custom regex — `pdfplumber` already had `dedupe_chars()` for this exact scenario.

## Empty lazy-load placeholder images left in scraped content (found 2026-08-02)

**Symptom:** Merit badge files (137 of 142) and one policy file (`annual-health-medical-record.md`) ended with `![](data:image/svg+xml,%3Csvg%20xmlns=%22http://www.w3.org/2000/svg%22%20viewBox=%220%200%20640%20375%22%3E%3C/svg%3E)` — decodes to a completely empty `<svg viewBox="0 0 640 375"></svg>`, no shapes, no fill, no informational or visual content.

**Root cause:** these pages lazy-load their real images via JavaScript after the page settles (an IntersectionObserver swapping the real `src` in once the image scrolls into view). The scraper captures the DOM before that swap happens, so it only ever sees the blank sizing-placeholder that was there initially.

**Fix:** added a strip rule to the shared `clean_markdown()` in `utils.py` (used by every fetch script) for a *standalone* empty-SVG image line. Deliberately scoped to bare `![](...)` lines only — some instances on `annual-health-medical-record.md` are wrapped in a real outer link (`[![](data:...)](http://www.bsaseabase.org/)`, pointing to Sea Base's/Northern Tier's/Philmont's own site), and stripping those wholesale would have silently dropped a real external URL along with the empty image. Those link-wrapped instances were deliberately left alone.

**Lesson for future scraper work:** when stripping decorative junk, check whether it's ever wrapped in something with independent informational value before writing a blanket removal rule.

## markdownify's `strip=[...]` unwraps tags, it doesn't remove them (found 2026-08-01)

**Symptom:** Some scraped policy pages contained the site's mega-menu nav links and raw inline `<script>` JS (jQuery snippets like `$searchBtnMobile.on("click", ...)`) as literal text in the output markdown, instead of the actual page content.

**Root cause:** `fetch_policies.py` calls `markdownify.markdownify(content_html, strip=["script", "nav", "header", "footer", "form", "button"])`. `strip` in markdownify does **not** delete those tags — it unwraps them, discarding the tag but keeping their children/text. A `<script>` tag's text content is normal text as far as markdownify is concerned, so its JS body gets emitted verbatim into the markdown. Same for a `<nav>` full of `<a>` links — the links survive as markdown links.

This was masked for most pages because `extract_content()` (in `utils.py`) usually selects a real content container that doesn't itself contain a stray nav/script. But on pages where the real content container didn't win the best-match comparison (e.g. a slow-rendering Elementor widget, or a nav element that happened to have a lot of visible text at the moment of extraction), the selected "content" HTML was actually page chrome, and `strip=[...]` let all of it leak straight through.

**Confirmed impact (2026.Q1 build):** 3 of 7 Tier 2 policy files were corrupted — `chartered-organization.md`, `guide-to-safe-scouting.md`, and `annual-health-medical-record.md`. The AHMR file in particular had **zero** real content (no Sea Base / Philmont / Northern Tier / Summit form links) — it was 100% nav menu + jQuery. This had been sitting in the committed `data/` since the initial 2026.Q1 build without being caught.

**Fix:** `extract_content()` in `utils.py` now strips `script, style, noscript, nav, header, footer, form, button, iframe` out of the *entire document* (via `el.remove()` in the page.evaluate call) **before** scoring candidate selectors — not just at the markdownify step. This means a stray nav/header element can neither win the best-match comparison (it's gone) nor leak leftover text if some other selector's content happened to contain one.

**Lesson for future scraper work:** don't rely on markdownify's `strip=` for actually removing unwanted elements — it only unwraps. If you need an element gone, remove it from the DOM (or from a BeautifulSoup tree) before conversion. Keeping `strip=[...]` in the markdownify call itself is harmless defense-in-depth but was never sufficient on its own.

**How this was caught:** not by re-running the scraper — by a user asking a substantive Scouting policy question (COR succession) that led to reading `chartered-organization.md` and noticing it was 100% site-nav boilerplate with no actual body content.

**Verification method:** re-fetched all 7 Tier 2 policy pages via a CDP-connected Chrome session and diffed old vs. new. 4 of 7 (`camping-permissions`, `reporting-youth-protection`, `two-deep-leadership`, `youth-protection-training`) came back byte-identical (aside from frontmatter dates) — confirming the DOM-cleanup fix doesn't regress pages that were already extracting correctly.

## All 133 merit badge files were corrupted — wrong-widget extraction, not nav leakage (found 2026-08-02)

**Symptom:** Every single file in `data/merit-badges/` (133 of 133, including `camping.md` and `first-aid.md` — the two files this repo's own CLAUDE.md cited as working examples) contained something other than the badge's Purpose/Requirements text. Three distinct flavors of wrong content:
- Scout Shop product ads (`$15.99` / `$7.95` price + product link) — 25 files
- Scouting Magazine / blog / ScoutLife article teasers — 47 files
- A "related merit badges" carousel widget with raw, unrendered CSS background-image rules leaking in as text — ~60 files
- The nav/script leak from the bug above — 1 file (`skating.md`)

None of the three widget-content bugs are the markdownify `strip=` bug described above — they aren't nav/header/script tags at all. They're legitimate Elementor widgets that simply out-scored the real content in `extract_content()`'s "longest innerText wins" selector heuristic, because merit badge pages surround the actual Overview/Requirements text with several sibling promo widgets that render more visible text than the real content does.

**How this was caught:** a routine "make sure no other scraped files are corrupted" grep sweep after fixing the policy-file bug above. Byte-pattern checks (`jQuery(`, nav-menu link fragments) caught only 1 file; it took reading actual file contents (`camping.md` turned out to be a Nalgene bottle ad) to realize the scope, then a keyword sweep for "requirement"/"Purpose" showed **zero** of the 133 files had real content.

**Root cause, live-page investigation:** merit badge pages use Elementor's newer flexbox "Container" layout (`e-con`, `e-con-full`, `e-child` classes), not the classic `.elementor-section > .elementor-widget-wrap` structure `CONTENT_SELECTORS` was built around. The Requirements widget has a stable, purpose-named class — `.profile-card` — unique on the page and consistent across every badge tested. The Overview widget has no comparable class (only an autogenerated per-page Elementor ID), but is reliably locatable by finding the `<h2>` with text "Merit Badge Overview" and walking up exactly 3 ancestors to the flex-child container holding both the heading and the paragraph.

**Fix:** added `extract_merit_badge_content()` in `utils.py` — a merit-badge-specific extractor that targets `.profile-card` and the Overview heading directly instead of scoring candidates, with fallback to the generic `extract_content()` if neither is found (defends against any page that doesn't match this template). Wired into `fetch_merit_badges.py` in place of the generic extractor. Also added `clean_merit_badge_markdown()` to strip three cosmetic artifacts that ride along inside those two widgets: a duplicate badge-name mini-heading, the Scoutbook-requirements loading-placeholder line (with a stray trailing numeric ID), and "Show More"/"Show Less" toggle links.

**Two more bugs found verifying the fix, same session:**
1. **Badge-name collisions.** The badge index page (`/skills/merit-badges/all/`) lists some badges twice — once plain, once annotated with which requirement numbers were recently revised, e.g. `"Chess (1) (2) (3) (4) (5) (6) (7)"` — both linking to the same URL. The old dedup-by-URL logic kept whichever copy came first in DOM order, which was sometimes the annotated one, producing filenames like `chess-1-2-3-4-5-6-7.md`. Fixed with `_clean_badge_name()`, which strips trailing `(\d+)` annotation groups before dedup.
2. **A genuinely wrong label on BSA's own site.** The Genealogy badge's index-page anchor text reads **"Geology"** even though its `href` correctly points to `/merit-badges/genealogy/`. Since two different real badges (Geology and Genealogy) both display as "Geology," they collided onto the same name-derived output filename and one silently clobbered the other. Fixed two ways: (a) `_slug_from_url()` derives the output filename from the URL path instead of the display name — collision-proof since scouting.org's own URLs are unique and stable; (b) after navigating to each badge's own page, its `<title>` tag (e.g. "Genealogy Merit Badge | Scouting America") overrides the scraped index name for both the H1 heading and frontmatter, since the page's own title is more authoritative than index-page link text and was confirmed correct in both directions (Geology's own title says Geology, Genealogy's says Genealogy).

**Verification method:** re-fetched all badges 4 times over the course of the fix (each fix step surfaced the next bug), diffing file counts and re-running the same grep sweep each time. Final run: 142 unique files (up from 133 — genuine BSA catalog growth: chess, genealogy, indian-lore, competitive-gaming, law, music, pets, radio, and wildland-fire-management all now have real pages that either didn't exist or weren't reachable at 2026.Q1), 0 filename collisions, 0 remaining junk-pattern matches, all 142 files contain both `## Merit Badge Overview` and `## Merit Badge Requirements` with real prose and a real numbered requirements list.

**Known minor redundancy, not fixed:** `indian-lore.md` and `american-indian-culture.md` are both real, distinct URLs on scouting.org that appear to serve the same current content (BSA renamed the badge; the old URL still resolves rather than 404ing or redirecting). Left as two files since both are legitimate scrape targets — collapsing them would require asserting one URL is canonical, which is a product decision, not a corruption fix.

**Lesson for future scraper work:** the generic longest-innerText-wins selector heuristic in `extract_content()` is a discovery tool, not a guarantee — it will confidently return the wrong element on any page where promotional/related-content widgets are more verbose than the real content. When adding a new page type to the scraper, don't assume the generic extractor works; verify against a live page first (this session used a CDP-connected Chrome + `page.evaluate` to walk the DOM and find stable selectors before writing any fetch code). And don't trust a site's own link text as ground truth for either dedup keys or display names — URLs and the target page's own `<title>` are more reliable than an index page's anchor text.

## Chrome CDP setup needs `--user-data-dir`, not just `--no-first-run`

`open -a "Google Chrome" --args --remote-debugging-port=9222 --no-first-run` frequently does **not** actually open the debug port — `curl http://localhost:9222/json/version` connection-refused even after the process is confirmed running with that flag in `ps aux`. Root cause appears to be that without a dedicated `--user-data-dir`, macOS Chrome sometimes hands the launch off to an existing/default profile process that ignores the CLI flags for that invocation.

**Reliable version:**
```bash
pkill -x "Google Chrome"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-cdp-scraper \
  --no-first-run &
```
Launching the binary directly (not via `open -a`) plus a scratch `--user-data-dir` reliably brings up the CDP endpoint within a few seconds. This profile has no Cloudflare clearance cookies, so warm up by navigating to `https://www.scouting.org/` first (`wait_until="load"`, then a few seconds' pause) before hitting Cloudflare-protected pages — `wait_until="networkidle"` straight to a policy/PDF page on a cold profile can time out entirely.

This mirrors a previously-known gotcha for the counselor scraper's Scoutbook CDP session (same `--user-data-dir` requirement) — it's a general Chrome-on-this-machine behavior, not specific to one script.

## reporting-youth-protection wired to the wrong URL — a copy-paste error, not a scraper bug (found 2026-08-05)

**How this was found:** a live spot-check on beta.scoutsync.org (after the merit-badge/nav-script/council fixes from 2026-08-02 were finally deployed) showed `/help → BSA Reference → Reporting Youth Protection Concerns` displaying Aquatics Safety content. Not a corruption pattern — the file was internally consistent (real, cleanly-extracted Aquatics Safety content, correct frontmatter for that content) — it was just filed under the wrong slug.

**Root cause:** in `fetch_policies.py`'s `POLICIES` list, the "Aquatics Safety" entry (`name`, `url`, `description` all correctly about aquatics, source `gss02`) had `"slug": "reporting-youth-protection"` instead of its own slug — an apparent copy-paste error from when that entry was added, never caught because the scraper ran successfully and produced a well-formed file; nothing about the pipeline flags a slug/content mismatch.

**Where the real content lives:** BSA doesn't publish a standalone "how to report a YP concern" page. The actual "Reporting Requirements" section (mandatory abuse reporting, Scouts First Helpline, Youth Protection Policy Violations reporting) is a subsection of the same `gss01` page (*Youth Protection and Adult Leadership*) that `two-deep-leadership.md` already correctly fetches in full. `fetch_policy_page()` extracts the whole matched content container, not a topic-scoped slice — so `two-deep-leadership.md` and `reporting-youth-protection.md` now legitimately share the same full-page body content under different frontmatter/H1/description, matching how BSA itself bundles these topics on one page. This is intentional overlap, not a duplication bug.

**Fix:** split into two correct `POLICIES` entries — `aquatics-safety` (the content that was there) and `reporting-youth-protection` (now pointed at `gss01`).

**Re-fetch note:** this was a same-session fix with no CDP Chrome running and headless fetches were failing at the time, so the two affected files were reconstructed directly from the already-correct `two-deep-leadership.md` body (same URL, deterministic extraction) rather than re-scraped. Safe here because the source URL and extraction path were unchanged; wouldn't be a safe shortcut for a fix that changed *what* gets extracted.

> **Amended 2026-09-10.** This entry used to state that "headless Chromium is Cloudflare-blocked on scouting.org" as a standing fact. That is false as written, and it needed testing separately from the curl claim above because it is a different client. Re-tested 2026-09-10: headless Chromium (Playwright, default context, no CDP) returned `200` with full rendered body text on `/about/governance/charter/`, `/health-and-safety/gss/gss01/` and `/about/faq/question10/`, 3/3 attempts each — including `/about/governance/charter/`, the URL that 403'd four consecutive times headless on 2026-09-05. What survives from that day is the intermittency finding, not a permanent block.

## markdownify glues adjacent bold/italic spans with no space (found 2026-08-05)

**Symptom:** `two-deep-leadership.md` had text like `adult program participant.****Adult volunteers must register` (a bare 4-asterisk run) and `**must**be no more than two years` (bold text butted directly against the next word, no space) — reads as run-together text once rendered, even though `react-markdown` + `remark-gfm` (a real CommonMark parser) actually parses the 4-asterisk case into two valid, back-to-back `<strong>` elements with no error.

**Root cause:** the source HTML has two `<strong>` elements (or a `<strong>` immediately followed by a plain-text node) that are visually adjacent on the page but have no whitespace text node between them in the DOM. `markdownify` converts each element faithfully, which is correct per-element but produces glued output across the boundary — same root shape as other markdownify boundary-loss bugs in this scraper (see the nav/script-leak and lazy-load-image entries above), just manifesting as missing whitespace instead of leaked markup.

**Fix:** `_space_glued_emphasis()` in `utils.py`, called from `clean_markdown()` (so it applies to every content type, not just policies). Two passes:
1. A bare run of exactly 4 asterisks between two non-space characters is unambiguous — always "close one bold span, open the next" — split into `** **`.
2. A paired-delimiter regex (`(\*{2,3})([^*\n]+?)\1`, content class excludes `*` so open/close is unambiguous from the match itself, not a raw-delimiter guess) pads any complete emphasis span that's directly touching a letter/digit on either side.

**Verified against the full existing corpus before trusting it** (159 files: 133 merit badges, ranks, policies) — only 4 files changed, all confirmed genuine instances of the same bug (e.g. `**Note:**When` → `**Note:** When` in `archery.md`).

**Known gap, not handled:** chained/nested emphasis from source markup like `<strong><em>A</em> <em>B</em></strong>` markdownifies to alternating single- and triple-asterisk runs (e.g. `***Cub Scout* *Programs – Overnight* *Exception:***`). The content-class-excludes-`*` regex can't match across those internal boundaries, so this pattern is left untouched rather than risk a wrong edit — a real parser would be needed to handle it safely, which is disproportionate for how rarely it occurs.

## Tier 2 scope now comes from the Annual Unit Charter Agreement's RESOURCES list (set 2026-09-05)

**The problem with the old scope:** Tier 2's policy set was assembled ad hoc – a reasonable guess at "what a unit leader needs," but with no external authority behind it. Nothing said when the set was complete, and nothing said when to re-check it.

**The new definition:** the **RESOURCES section on the last page of the Annual Unit Charter Agreement** (form **524-956**, 2026 edition, PDF uploaded under `/wp-content/uploads/2026/04/`) is now the coverage target. This is the document a chartered organization actually signs, and it enumerates exactly which publications govern a unit. That makes it a defensible scope boundary rather than an editorial judgment call.

Source PDF: `https://www.scouting.org/wp-content/uploads/2026/04/524-95626-Annual-Charter-Agreement.pdf` – fetches fine with plain `curl` (it's on the WordPress CDN path, which is not gated the way the site's HTML pages are).

**On the effective date:** the form's own effective-date line is a *blank fill-in* (`Effective ______–______ 524-956`) completed per-unit at charter time, so the PDF does not state a printed date range. The edition is identified by the `26` suffix in the filename (`524-956` + `26`) and the `2026/04` upload path. Don't cite a printed effective range from this document – it doesn't have one.

**When to re-check:** BSA re-issues this form annually. Re-pull it at the start of each charter year and diff the RESOURCES list against `POLICIES` in `fetch_policies.py`.

**The list, and how each item maps to `data/policies/`:**

| RESOURCES item | Slug | Notes |
|---|---|---|
| (intro) membership standards URL | `membership-standards` | See URL artifact below |
| The Charter and Bylaws | `charter-and-bylaws` | PDF |
| The Mission of Scouting America | `mission-of-scouting-america` | Published in the About page's "Foundation of Scouting" block; no standalone `/about/mission/` page exists |
| The Rules and Regulations | `rules-and-regulations` | PDF |
| The Scout Oath and Scout Law, incl. Duty to God | `scout-oath-and-law` | `/about/faq/question10/` |
| Youth protection policies, incl. mandatory reporting | `two-deep-leadership`, `reporting-youth-protection`, `youth-protection-training` | Already covered by three files |
| Scouting Safely section | `scouting-safely` | The section landing page – the sub-pages were already covered, the index itself was not |
| The Guide to Safe Scouting | `guide-to-safe-scouting` | Already covered |
| The SAFE Scouting Checklist | `safe-checklist` | `/health-and-safety/safe/` |
| Scouter Code of Conduct | `scouter-code-of-conduct` | Already scraped, but shipped under the wrong label – see the next entry |
| Incident Reporting | `incident-reporting` | `/health-and-safety/incident-report/` |
| Scouting America Brand Center | *(not scraped)* | See "Brand Center" below |

`aquatics-safety`, `camping-permissions`, and `annual-health-medical-record` are **not** named individually in RESOURCES – they're GSS chapters that fall under "the Guide to Safe Scouting" / "Scouting Safely." They're kept. Tier 2 is therefore *RESOURCES ∪ the existing operational GSS chapters*, not RESOURCES alone; the charter list is a **floor, not a ceiling**.

**Two URL artifacts in the source document, both verified:**

1. **`membership- standards` is a line-break artifact, not the real URL.** The PDF wraps the URL mid-path, and naive extraction yields `https://www.scouting.org/about/membership- standards/`. The real URL has no space. Verified: the de-hyphenated form returns 200, the spaced form returns 403.

2. **The Brand Center URL in the charter is imprecise.** The document says the Brand Center "can be located at `https://www.scoutingwire.org`". That host resolves (200) but is **Scouting Wire – the movement's news blog**, not the Brand Center. The actual Brand Center is a link *from* that site, at `https://scouting.webdamdb.com/bp/#/` (page title: "BSA Brand Center"). Verified 2026-09-05 in a real browser.

## Brand Center is out of scope for the scraped tier (decided 2026-09-05)

`https://scouting.webdamdb.com/bp/#/` is a **WebDAM digital-asset-management portal** sitting behind a cookie-consent gate. It serves logos, images, and brand templates – binary assets – not policy prose. There is no markdown-able document here: scraping it would produce a consent banner and an empty SPA shell.

**Decision: not scraped.** It's recorded as a pointer only. Anything a unit leader needs from it (brand usage rules in plain language) is a curated synthesis and belongs in **scouting-reference**, not here. This is the "genuinely cannot be scraped" case the tier boundary exists for.

## `chartered-organization.md` shipped Scouter Code of Conduct content under the wrong label (found 2026-09-05)

**Symptom:** `data/policies/chartered-organization.md` was titled "Chartered Organization Relationship" and described as covering CO responsibilities, but its body was 100% the **Scouter Code of Conduct** – the numbered personal-conduct commitments an adult leader affirms. Nothing in the file was about the chartered organization relationship.

**Root cause – a URL substitution that never got relabeled.** Traced with `git log -S`. The entry originally pointed at `https://www.scouting.org/programs/scouts-bsa/resources-for-volunteers/chartered-organizations/`. That page 404'd. Commit `5bfc84e` ("fix all Tier 1+2 selectors for 2026.Q1") swapped in `gss/bsa-scouter-code-of-conduct/` – a real, working page, but **a different document** – and left `name` and `slug` untouched while only half-editing `description` (it prepended "The Scouter Code of Conduct and" but kept the trailing "COs own their units…" clause). The scraper then did exactly what it was told and produced a well-formed file with a truthful `source:` URL and a false title.

**Why nothing caught it:** same blind spot as the `reporting-youth-protection` bug (see above), and worth stating as a general rule – **the pipeline cannot detect a slug/label that disagrees with its own URL.** Every automated signal was green: the fetch succeeded, content extraction found real content, the frontmatter `source:` was accurate. Only reading the file against its own slug catches this class of bug.

Note the two bugs are *different* root causes despite the identical symptom:
- `reporting-youth-protection` – a **copy-paste error**: the wrong URL pasted into an otherwise-correct entry.
- `chartered-organization` – a **deliberate substitution for a dead link**, where the replacement document was never reconciled with the label.

**Fix:** relabeled the entry to `scouter-code-of-conduct` with a matching name and description, and regenerated the file. The URL was already correct – it was the label that was wrong. This also fills a real RESOURCES slot, since the Scouter Code of Conduct is a named item in the charter agreement.

**No file now claims to cover the chartered organization relationship.** That's deliberate: BSA has no standalone page for it, and the authoritative statement of the CO relationship *is* the Annual Unit Charter Agreement itself. A unit-facing explanation of it is a curated synthesis for **scouting-reference**.

**Check to run when adding or re-pointing any policy entry:** read the produced file's first ~20 lines and confirm the body actually matches the slug. A green build proves nothing here.

## Governance PDFs: scraped into Tier 2 rather than curated (decided 2026-09-05)

Two RESOURCES items are PDFs, not web pages: the **Charter and Bylaws** and the **Rules and Regulations**. The question was whether `fetch_policies.py` should grow PDF extraction, or whether these belong in **scouting-reference** as curated syntheses.

**Decision: scrape them into `data/policies/`.** Reasoning:

1. **They extract cleanly.** Verified before deciding, rather than assumed – Charter and Bylaws is 28 pages / ~80k chars, Rules and Regulations 24 pages / ~78k chars, both single-column running prose that `pdfplumber` handles without incident.
2. **The repo already does PDF extraction** (`fetch_ranks.py`), so this is not new capability, just a second caller.
3. **Tier 2 is the scraped tier and hand-authoring is destroyed on rebuild.** If these aren't scraped, the charter-derived checklist has permanent holes with no source of truth behind them.
4. **"Cannot be scraped" genuinely doesn't apply** – that exemption is for things like the Brand Center, and stretching it to cover "inconvenient" would hollow out the tier boundary.

**What this decision does NOT claim:** these are dense legal documents. A Scoutmaster asking "can our troop run a raffle?" wants a paragraph, not 24 pages of numbered sections. The right complement is a curated synthesis in **scouting-reference that cites these files** – a complement, not a substitute. Capturing authoritative source text here and writing readable guidance there are different jobs, and this decision only covers the first.

**The complement now exists** (2026-09-05, `scouting-reference` commit `1a10d2f`). Three unit-facing syntheses were written against these two files, in `scouting-reference/data/policies/`:
- `unit-funds-and-property.md` – who owns unit money and gear, and what happens to it on dissolution.
- `unit-fundraising-and-solicitation.md` – including the **October 2025 amendment that lifted the blanket ban on raffles and games of chance**, and the **12-week per-youth annual selling cap** that appears only in the Charter and Bylaws.
- `program-rules-a-unit-cannot-change.md` – no unit-added advancement requirements, the elected SPL rule, the uniform-alteration bar.

That work confirmed the decision was right on the merits: the unit-relevant provisions are scattered across both documents (the solicitation ban and selling cap live in the *Bylaws*, the fundraising and advancement rules in the *Rules and Regulations*), so a reader needs the full searchable source text here to find them at all. It also surfaced a citation practice worth repeating: **every verbatim quotation was checked programmatically against the scraped text before commit** – normalize whitespace and smart quotes, then assert each quoted string appears in the source. Cheap to run, and it catches paraphrase that has drifted into quotation marks.

**Implementation notes:**
- `extract_governance_pdf_text()` in `fetch_policies.py` is deliberately much simpler than `fetch_ranks.extract_pdf_text()`. None of the rank handbook's machinery applies: no fill-in tables, no two-column option lists, no fake-bold double-printing. Confirmed `dedupe_chars()` changes nothing on either document, so it isn't called.
- `_clean_governance_pdf_text()` strips the repeating footer (`©20XX Boy Scouts of America`, `BIN 100-491` / `100-492`, `October 2025 Revision`) and bare page-number lines in both arabic and lower-case roman. **Gotcha:** the footer often extracts *glued* to the adjacent line (`©2025 Boy Scouts of AmericaBIN 100-491`, `Oct 2025 RevisionOCTOBER 2025 CHANGES`) because it lives in a separate text object that pdfplumber merges into the nearest line – so the glued forms are split with targeted lookahead substitutions *first*, before the line-anchored patterns can match them.
- The page-number patterns are anchored to a whole line (`^\s*\d{1,3}\s*$`), so a numbered clause like `2. The corporation…` is never touched.
- `download_pdf()` moved from `fetch_ranks.py` to `utils.py` and is now shared by both callers. It runs `fetch()` **inside the browser page** – `context.request.get()` does not reliably carry Cloudflare clearance to the scouting.org CDN.

## scouting.org serves intermittent 403s to an automated browser – a 403 means "throttled", not "gone" (found 2026-09-05)

**Symptom:** while verifying candidate URLs headless, the same URL returned 200 and 403 on different attempts with no pattern. `/about/membership-standards/` returned 200 on a fresh session and 403 four times in a row later; `/about/faq/question10/` did the exact opposite. `/about/*` paths trip it far more readily than `/health-and-safety/*`.

**The trap:** this looks exactly like "the page doesn't exist" or "BSA moved it," and the tempting responses are both wrong – dropping the URL from `POLICIES`, or "fixing" it by switching the fetch to `requests`/`curl`. The 403 is throttling, as the rest of this entry establishes. It is not the page being gone, and it is not a browser check the scraper is failing.

> **Corrected 2026-09-10.** This paragraph used to continue: *"Switching to a plain HTTP client removes the browser session the site is gating on and guarantees a 403. The 403 is the symptom of bypassing the browser, not the cure."* **That mechanism was invented and is false.** Bare `curl` with no headers returns `200` with real page content on these URLs, 3/3 attempts, confirmed independently. The site was never gating on a browser session – it was throttling, which this entry already says correctly everywhere else. A right conclusion was resting on one sound premise and one made-up one. It stands on the sound premise alone: don't switch the scraper to a plain client, because the measured evidence is single fetches while a build issues hundreds of requests under exactly the load condition that produces these 403s. See "An access failure is dated, client-specific, and here load-specific" below. (The corresponding Studio entry was amended the same way, `40f105c`.)

**How it was actually settled:** loaded `/about/governance/charter/` – which had 403'd four consecutive times headless – in a real Chrome window. It returned the page normally, title "Boy Scouts of America Charter | Scouting America." That confirmed the pages exist and the 403 is throttling. **Verify a suspicious 403 in a real browser before concluding a page is gone.**

**Fix:** `_goto_with_retry()` in `fetch_policies.py` retries a 403 up to 5 times with escalating backoff (4s, 8s, 12s, 16s). For a full `--force` rebuild, prefer CDP mode against a real Chrome (`--cdp-url http://localhost:9222`) – see the CDP setup entry above. That preference is an observation, not a mechanism: CDP mode has completed full rebuilds where headless runs did not. *Why* it holds up better under bulk load has not been established, and the "it carries genuine Cloudflare clearance" wording this line used to carry was the same invented-mechanism shape as the trap paragraph above.

## An access failure is dated, client-specific, and here load-specific (rule, established 2026-09-10)

**The rule.** Never record an access result as a property of the source. Record it as an observation about **a client**, **a URL**, **a date** — and, for this repo uniquely, **a load condition**. "scouting.org blocks curl" is folklore: undated, unfalsifiable, and it stops anyone from ever retrying, so nothing contradicts it and it propagates. "Bare curl returned 200 on 3 URLs, single fetches, 2026-09-10; the scraper's bulk path still sees intermittent 403s under load and retries with backoff" is a claim someone can re-run.

Two entries above had drifted into folklore and are amended in place: "plain curl gets a 403 from Cloudflare" (the root-relative-links entry) and "headless Chromium is Cloudflare-blocked on scouting.org" (the `reporting-youth-protection` entry). Both were re-tested on 2026-09-10 and both are false as they were written. They were tested **separately**, because curl and headless Chromium are different clients and a result for one is not evidence about the other.

**What was measured, 2026-09-10, from this machine:**

| Client | URLs | Result |
|---|---|---|
| Bare `curl`, no headers | `/health-and-safety/gss/gss01/`, `/about/faq/question10/`, `/about/governance/charter/` | `200`, 3/3 each, real page titles and bodies |
| Bare `curl`, no headers | `/health-and-safety/gss/toc` | `301` → trailing-slash form → `200` |
| Headless Chromium (Playwright, no CDP) | the same three pages, plus `troopleader.scouting.org`, `troopresources.scouting.org` | `200`, 3/3 each, full rendered body text |
| `scripts/fetch-page.sh <url> --check` | `/about/governance/charter/` | bare and browser-header requests identical; User-Agent makes no difference |

Bodies were checked for real content, not just status codes — `/about/governance/charter/` contains the charter prose and zero Cloudflare-challenge markers, `gss01` renders ~14k characters of the actual Barriers to Abuse text. A bot challenge is served as a `200`, so a status code alone proves nothing.

**Pick the verification phrase from the page, not from memory.** The first `gss01` probe grepped for "two-deep leadership" — the phrase this repo's own filename and docs use — and got zero hits on a page that had fetched perfectly. BSA words it differently on the page itself. A remembered phrase that the real page does not contain produces a false negative indistinguishable from a block, which is precisely the failure this whole entry exists to prevent. Open the page (or its extracted text), take a distinctive string *from it*, then grep for that.

**Deliberately untested: sustained load.** Settling whether bulk runs still trip throttling means deliberately trying to trip a third-party edge from this machine's IP, which was declined rather than overlooked — a bad trade in general and a worse one before a quarterly refresh. Record it as *untested*, not as *unknown* and not as *fine*.

**The trap, and why this repo is the one most likely to fall into it.** The correct response to the above is to narrow the false claims — *not* to conclude the scraper should drop CDP and fetch with `curl`. That evidence is a handful of **single fetches of a few URLs**. A build issues hundreds of requests: 228 councils, 142 merit badges, the policy set. The observed failure mode of this host is **throttling under sustained load** (see the intermittent-403 entry above), and nothing measured on 2026-09-10 touches that. *"Curl works for one page"* and *"curl works for request 200 of a bulk run"* are different claims and only the first has been tested. Simplifying the client would remove the mechanism the system depends on and convert an intermittent failure into a deterministic one, while looking like a simplification. **`_goto_with_retry()` and the real-Chrome CDP path stay.**

A third correction went into the intermittent-403 entry above, and it is a different error class from the two amendments: not a stale observation, but an **invented mechanism**. That entry explained the 403s as the site "gating on a browser session," which a plain client "removes" — a tidy causal story that was never measured and is false. The throttling observation in the same entry was real, and the conclusion drawn from both was right, so nothing ever pressed on the invented half. **A conclusion that happens to be correct does not validate the premises it was rested on.** When an entry states a mechanism, check whether it was observed or assumed; if assumed, either test it or write the conclusion without it.

**Tooling.** `./scripts/fetch-page.sh <url> --check` runs bare and browser-header requests three times each and reports whether headers matter, whether the failure is intermittent, and whether the host soft-404s. Use it for one-off URL verification, before recording any source as unavailable. It is **not** a substitute for the scraper's browser path — it makes single requests, which is exactly the case that does not generalise here. Its caveat: it compares payload sizes and titles rather than status alone (because a challenge page is a `200`), and that is still a heuristic. For anything a decision rests on, grep the body for a phrase only the real page would contain.

## `build_all.py` used to wipe `manifest.json`'s `notes` field on every run (found 2026-09-05)

`data/manifest.json` carries a hand-maintained `notes` field – the running provenance record of what changed in the data and why. `build_all.py` rebuilt the manifest dict from scratch (`built`, `version`, `tier_built`, `forced`, `counts`) with no `notes` key, so **any build would have silently erased it.** It survived as long as it did only because nobody re-ran a build between the note being written and this session.

**Fix:** `build_all.py` now reads the existing `notes` and carries it forward, the same way it already merged `counts` so partial builds don't zero out other tiers. It is still meant to be updated deliberately after a build that changes what the data covers – carrying it forward preserves it, it doesn't keep it accurate.

## Two checks for a policy file whose body disagrees with its label (added 2026-09-05)

Two bugs have now shipped this same defect – a file whose content is not what its name says – through two *different* mechanisms. Both passed every automated signal the scraper had: the fetch succeeded, extraction found real content, and the frontmatter `source:` was accurate. Nothing compared what a file **claimed to be** against what it **was**.

- `reporting-youth-protection` (2026-08-05) – a copy-paste error. `name`, `description` and `url` all said "Aquatics Safety"; the slug was the odd one out. Three fields agreed with each other.
- `chartered-organization` (2026-09-05) – a dead-link substitution. Commit `5bfc84e` replaced a 404ing URL with a working page for a *different* document and left `name` and `slug` untouched. Here the **URL** was the odd one out, so every field in the entry still agreed with every other field.

Because the two mechanisms fail at different points, they need two checks. Both live in `fetch_policies.py`.

**Check A – static, no network.** Every significant token in an entry's `slug` must appear somewhere in that entry's own `name` + `description` + `note` (lowercased, punctuation stripped, hyphens split, stopwords dropped, light plural stemming; `label_tokens()` in `utils.py`). Run it standalone with `python3 fetch_policies.py --check-labels`, which exits non-zero; it also runs at the start of every Tier 2 build, before any network work.

**The critical design detail: the slug is compared against the whole entry, not against `name` alone.** `two-deep-leadership` is a completely legitimate entry whose name is "Youth Protection and Adult Leadership" – **zero** token overlap with its slug. Measured: a name-only rule flags 1 of 16 entries, and that one entry is the false positive. Its description contains "two-deep leadership", which supplies all three missing tokens. Including the description is the difference between a usable check and one that gets switched off.

**Check B – post-fetch.** Compares the entry's `name` against the document's own self-description. Compares NAME, not slug, because `name` is the field that claims to describe the document. Reported as a **warning with both strings printed**, never a build failure, since page titles drift upstream.

Two refinements were needed to make Check B usable, both driven by measurement against real pages rather than guessed:

1. **Score the `<h1>` and the `<title>`, take the best.** Either one naming the document correctly is sufficient evidence. This matters: `/about/` genuinely carries the mission statement, but its `<h1>` is the marketing tagline "Scouting invites every youth to a safe, fun place..." while its `<title>` is "About Scouting America". H1-only fires on a correct entry at 33%.
2. **Compare each candidate in both directions and take the better score.** A page heading is routinely a *shorter* phrasing of the entry name – gss03 is titled just "Camping" where the entry is "Camping and Activity Permissions", which scores 33% one way and 100% the other. Containment in either direction means the two strings describe the same document. A genuine mislabel scores 0.0 in both directions against both candidates.

### Proof that each check can actually fail

A check whose passing result is a negative ("no mismatches") is worthless until it has been shown capable of firing. Both historical entries were recovered verbatim via `git log -S` and replayed:

| Bug | Check A | Check B |
|---|---|---|
| `reporting-youth-protection` (slug is odd one out) | **fires** – nothing in the entry mentions `reporting`, `youth`, `protection` | silent – `name` agreed with the page it actually fetched |
| `chartered-organization` (URL is odd one out) | silent – every field agreed with every other field | **fires** – 0% overlap vs "Scouting America Scouter Code of Conduct" |

Each bug is caught by exactly one check, and neither check catches both. That is the whole argument for having two.

**This exercise earned its keep immediately.** Check B's heading parser used a `</h\1>` backreference, and writing the file programmatically turned the `\1` into a literal `\x01` – a pattern that can never match. Check B reported "ok" on all 16 entries while being structurally incapable of firing. Nothing caught this except running it against real fetched HTML, because the fixture tests passed heading strings in directly and never exercised the parser. The patterns are now written as two backreference-free regexes with a comment saying why. **A green check is not evidence until you have watched it go red.**

A second latent bug surfaced the same way: rich reads `[...]` as markup, so an unescaped `[{slug}]` in the warning was parsed as a style tag and rendered as **nothing**, silently deleting the one field the reader most needs. All interpolated values in both checks' output now go through `rich.markup.escape()`.

### The allowlist

`LABEL_CHECK_ALLOWLIST` in `fetch_policies.py` is keyed by `(slug, check)` with a written reason per entry. A check that cries wolf gets disabled, which is worse than no check.

It has exactly one entry: `("reporting-youth-protection", "B")`. That entry and `two-deep-leadership` deliberately share one source page, because BSA bundles youth protection and mandatory reporting onto gss01 and publishes no standalone reporting page, so this file's body is legitimately headed "Youth Protection and Adult Leadership".

Worth knowing: with the two refinements above it scores **exactly 50%**, passing on the threshold by the narrowest possible margin. The allowlist entry is therefore belt-and-braces rather than load-bearing – it exists so that a small upstream heading change or any future threshold increase does not start producing recurring noise on a known-good entry.

**A failing Check A is never an allowlist candidate.** If Check A fires on a legitimate entry, the token rule needs work.

### What these checks do NOT cover

More useful than what they do:

- **PDF-sourced entries get no Check B at all.** `fetch_policy_pdf()` has no heading to compare, and a PDF's first line of extracted text is not a reliable title. `charter-and-bylaws`, `rules-and-regulations`, and any future PDF entry are Check-A-only.
- **Neither check verifies that the content is correct** – only that the label and the document agree about what the document *is*. A page whose body is rewritten while keeping its title passes both checks unchanged.
- **Check A cannot see a wrong URL** when every field in the entry agrees with every other field. That is precisely the `chartered-organization` shape, and it is why Check B exists.
- **Check B cannot see a wrong slug** when `name` matches the page actually fetched. That is precisely the `reporting-youth-protection` shape, and it is why Check A exists.
- **The allowlisted entry is invisible to Check B.** A genuine future mislabel of `reporting-youth-protection` onto some other gss01-adjacent page would be masked. This is the accepted cost of not crying wolf.
- **Check A is vacuous for a slug with no significant tokens.** A slug that is entirely stopwords or digits has nothing to check.
- **Check A reports disagreement, not which side is wrong.** It cannot tell you whether the slug or the rest of the entry is the error – only that they do not match.

### Why `fetch_ranks.py` is not covered

Checked, and Check A does not apply. `fetch_ranks.py` derives its output filename from `slug(rank["name"])`, so the slug cannot drift from the name – the failure mode is structurally impossible.

The `RANKS` table does have a `section_pattern` field that *looks* like a comparable hand-maintained mapping, but **it is dead config: nothing reads it.** `split_combined_pdf()` carries its own hardcoded `patterns` dict, keyed by rank name, and that is what actually drives section splitting. Note the two disagree – the table says `EAGLE SCOUT RANK` while the live dict uses `EAGLE RANK` – which is exactly the sort of trap a maintainer could edit in good faith and have no effect. Left alone here rather than fixed, to keep a detector change from carrying an unrelated correction, but worth cleaning up.

## Corpus provenance, moved out of manifest.json (2026-09-05)

`data/manifest.json` used to carry this account in a hand-maintained `notes` field. `build_all.py` rebuilt the manifest from scratch on every run and silently erased it; it was then changed to carry the value forward, which stopped the deletion but not the drift.

**Studio decision (2026-09-05): hand-maintained narrative does not belong in a machine-regenerated artifact at all.** It will either be destroyed or go stale, and you do not get to choose which. Mitigating that is weaker than removing it. The manifest's `notes` field is now a fixed, generated one-line pointer back to this file, so there is nothing left to erase and nothing left to drift.

The text below is the field's final value, **moved verbatim and not rewritten**. It is the provenance trail for the March stale-pin incident, and its value is that it says what was known at the time. Later corrections live in the dated entries above and below it, not inside it.

> Tier 2 scope redefined 2026-09-05 — see docs/PLAYBOOK.md. The policy set was previously ad hoc; its coverage target is now the RESOURCES list on the last page of the Annual Unit Charter Agreement (form 524-956, 2026 edition), the document a chartered organization actually signs and which enumerates the publications governing a unit. Re-check the list annually at the start of each charter year. Policies went from 8 files to 16: added membership-standards, mission-of-scouting-america, scout-oath-and-law, scouting-safely, safe-checklist, incident-reporting, and the two governance PDFs charter-and-bylaws and rules-and-regulations (a deliberate decision to extract national governance PDFs into this scraped tier rather than curate them downstream — verified they extract cleanly before committing to it). chartered-organization.md was renamed to scouter-code-of-conduct.md: it had always held Scouter Code of Conduct content under a chartered-organization label, because commit 5bfc84e swapped its URL to replace a 404 without ever relabeling the entry — the pipeline cannot detect a slug that disagrees with its own URL, so only a slug-vs-content read catches this. No file now claims to cover the chartered organization relationship; BSA publishes no standalone page for it and the charter agreement is itself the authoritative statement. The Scouting America Brand Center is on the RESOURCES list but is deliberately NOT scraped — it is a WebDAM asset portal of logos and images behind a consent gate, with no policy prose to capture (and the charter's own URL for it, scoutingwire.org, points at the Scouting Wire news blog rather than the Brand Center itself, which lives at scouting.webdamdb.com/bp/). Unit-facing syntheses of the governance documents and brand rules belong in scouting-reference, the curated tier. The 8 pre-existing policy files were not re-fetched in this pass, so their fetched: dates are unchanged; this was a scope-expansion build, not a quarterly refresh.
