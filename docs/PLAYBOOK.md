# PLAYBOOK — scouting-kb

Longer-form scraper patterns and incident writeups. See CLAUDE.md for short, stable operating rules; this file is for the detailed "here's what broke and why" record.

## markdownify's `strip=[...]` unwraps tags, it doesn't remove them (found 2026-08-01)

**Symptom:** Some scraped policy pages contained the site's mega-menu nav links and raw inline `<script>` JS (jQuery snippets like `$searchBtnMobile.on("click", ...)`) as literal text in the output markdown, instead of the actual page content.

**Root cause:** `fetch_policies.py` calls `markdownify.markdownify(content_html, strip=["script", "nav", "header", "footer", "form", "button"])`. `strip` in markdownify does **not** delete those tags — it unwraps them, discarding the tag but keeping their children/text. A `<script>` tag's text content is normal text as far as markdownify is concerned, so its JS body gets emitted verbatim into the markdown. Same for a `<nav>` full of `<a>` links — the links survive as markdown links.

This was masked for most pages because `extract_content()` (in `utils.py`) usually selects a real content container that doesn't itself contain a stray nav/script. But on pages where the real content container didn't win the best-match comparison (e.g. a slow-rendering Elementor widget, or a nav element that happened to have a lot of visible text at the moment of extraction), the selected "content" HTML was actually page chrome, and `strip=[...]` let all of it leak straight through.

**Confirmed impact (2026.Q1 build):** 3 of 7 Tier 2 policy files were corrupted — `chartered-organization.md`, `guide-to-safe-scouting.md`, and `annual-health-medical-record.md`. The AHMR file in particular had **zero** real content (no Sea Base / Philmont / Northern Tier / Summit form links) — it was 100% nav menu + jQuery. This had been sitting in the committed `data/` since the initial 2026.Q1 build without being caught.

**Fix:** `extract_content()` in `utils.py` now strips `script, style, noscript, nav, header, footer, form, button, iframe` out of the *entire document* (via `el.remove()` in the page.evaluate call) **before** scoring candidate selectors — not just at the markdownify step. This means a stray nav/header element can neither win the best-match comparison (it's gone) nor leak leftover text if some other selector's content happened to contain one.

**Lesson for future scraper work:** don't rely on markdownify's `strip=` for actually removing unwanted elements — it only unwraps. If you need an element gone, remove it from the DOM (or from a BeautifulSoup tree) before conversion. Keeping `strip=[...]` in the markdownify call itself is harmless defense-in-depth but was never sufficient on its own.

**How this was caught:** not by re-running the scraper — by a user asking a substantive Scouting policy question (COR succession) that led to reading `chartered-organization.md` and noticing it was 100% site-nav boilerplate with no actual body content.

**Verification method:** re-fetched all 7 Tier 2 policy pages via a CDP-connected Chrome session and diffed old vs. new. 4 of 7 (`camping-permissions`, `reporting-youth-protection`, `two-deep-leadership`, `youth-protection-training`) came back byte-identical (aside from frontmatter dates) — confirming the DOM-cleanup fix doesn't regress pages that were already extracting correctly.

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
