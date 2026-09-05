> # ⚠️ SUPERSEDED – historical record, do not follow the instructions below
>
> **Retired 2026-09-05.** This file was the working scratchpad for the original KB.1 build and was last updated **2026-03-03**. It froze mid-build: it still lists merit badges as "IN PROGRESS", policies as "not started", and offers crash-recovery steps for a build that finished six months ago. Following its resume instructions today would be actively misleading.
>
> **What replaced it, and where to look now:**
>
> | For | Go to |
> |---|---|
> | Where the project stands right now, and what is open | `docs/HANDOFF.md` |
> | What broke, why, and how it was fixed | `docs/PLAYBOOK.md` |
> | How to run the scraper, tier definitions, troubleshooting | `CLAUDE.md` |
> | Current corpus counts and version | `data/manifest.json` |
>
> **Kept rather than deleted, and left verbatim below,** because it is the contemporaneous record of the first build – the same treatment a dated research brief gets. Its value is that it says what was known on 2026-03-03.
>
> ---
>
> ## What in it is still accurate
>
> Stated explicitly so a future reader does not discard the whole file and lose these. Every item below was re-verified against the repo on 2026-09-05:
>
> - **Fix 1, the `DATA_DIR` fix.** `build_all.py` still writes to the repo-root `data/`, not `scraper/data/`.
> - **Fix 3, downloading PDFs with an in-page `fetch()`** rather than `context.request.get()`, to carry Cloudflare clearance. Still true and still the reason it works; the function has since moved to `utils.download_pdf()` and is shared by the ranks and policies fetchers.
> - **Fix 4, the Second Class PDF filename.** It is still `Second-Class-v2.pdf`, not `Second-Class.pdf`.
> - **Fix 5, the Eagle Scout section pattern.** The combined PDF really does use `EAGLE RANK REQUIREMENTS`, and `split_combined_pdf()` still matches on `^EAGLE RANK`.
> - **Fix 6, merit badge waits.** `fetch_merit_badges.py` still uses `networkidle` and still has the `_safe_evaluate()` retry wrapper.
> - **The CDP setup command**, as far as it goes. It is still the right approach for a full refresh, but it is **incomplete**: `--no-first-run` alone is not enough, and Chrome also needs `--user-data-dir` or it will not enable CDP at all. See `docs/PLAYBOOK.md`.
>
> ## What in it is wrong or superseded
>
> - **Every count.** Councils 137 is now 228 (zip sampling was a 40% undercount, not a rounding error). Merit badges 133 is now 142, and all 133 of the originals were later found corrupted. Policies 7 is now 16.
> - **The whole "Status (2026-03-03)" section.** Ranks, merit badges and policies are all long since complete.
> - **"BSA has ~250+ councils – need more representative zips."** The zip-sampling approach was the wrong tool, not an under-tuned one. Superseded by `fetch_councils_authenticated.py`.
> - **"The `(cid:22)` artifacts ... harmless but ugly."** They were **not** harmless. The related doubled-character bug corrupted section headers badly enough that `life.md` silently absorbed the entire Eagle Scout section.
> - **"`scraper/data/` is leftover junk – can be deleted."** Already done; that directory no longer exists.
> - **All resume and quality-check instructions**, including the thresholds ("policies: should be 5+ files").

# Session Log — scouting-kb KB.1 build
_Updated as fixes are applied. Reference this if session crashes._

## ✅ COMPLETE — committed 2026-03-03

## Final counts
- Councils: 137 | Ranks: 7/7 | Merit badges: 133 | Policies: 7/7

## Status (2026-03-03)

- **Councils**: ✅ 137 councils in `data/councils/` — complete, correct location
- **Ranks**: ⚠️ 6/7 in `data/ranks/` — Eagle Scout missing (see fix below)
- **Merit badges**: 🔄 IN PROGRESS — running in background (started ~03:45)
- **Policies (Tier 2)**: ⏳ not started

---

## Code fixes applied this session

### 1. DATA_DIR fix (already committed before crash)
`build_all.py`: `DATA_DIR = Path(__file__).parent.parent / "data"` — writes to repo root `data/` not `scraper/data/`

### 2. Councils: zip-based API (already done before crash)
`fetch_councils.py`: Queries `api.scouting.org/organizations/v2/zip/{zip}/council` per zip. Got 137 unique councils. May need more zips to reach 200+.

### 3. Ranks: PDF via in-page fetch() instead of context.request.get()
`fetch_ranks.py`: Changed `download_pdf(context, url)` → `download_pdf(page, url)` using `page.evaluate(fetch())` inside the browser. This passes Cloudflare clearance. Also navigates to advancement page first to warm up session.

### 4. Ranks: Second Class PDF URL added
`fetch_ranks.py`: Set `pdf_url = _BASE + "Second-Class-v2.pdf"` (was None).

### 5. Eagle Scout section pattern — ✅ FIXED
`fetch_ranks.py` `split_combined_pdf()`: The combined PDF uses `EAGLE RANK REQUIREMENTS` (not `EAGLE SCOUT RANK REQUIREMENTS`). Changed pattern from `r"^EAGLE SCOUT"` → `r"^EAGLE RANK"`.

### 6. Merit badges: networkidle instead of load
`fetch_merit_badges.py`: Changed `wait_until="load"` → `"networkidle"` for all `page.goto()` calls. Added `_safe_evaluate()` retry wrapper.

---

## Files changed this session
- `scraper/fetch_ranks.py` — download_pdf, Second Class URL, warm-up nav
- `scraper/fetch_merit_badges.py` — networkidle waits, _safe_evaluate retry

---

## Resume instructions if session crashes

1. Check if Chrome CDP is running: `curl -s http://localhost:9222/json/version`
   - If not: `pkill -x "Google Chrome" && open -a "Google Chrome" --args --remote-debugging-port=9222 --no-first-run` then navigate to scouting.org

2. Check merit badge progress: `ls data/merit-badges/ | wc -l` (target: 130+)

3. Apply Eagle Scout fix (if not already done):
   In `scraper/fetch_ranks.py` `split_combined_pdf()`, change:
   ```python
   "Eagle Scout": re.compile(r"^EAGLE SCOUT", re.MULTILINE),
   ```
   to:
   ```python
   "Eagle Scout": re.compile(r"^EAGLE RANK", re.MULTILINE),
   ```

4. Re-run to pick up Eagle Scout (councils/ranks/badges already done skip automatically):
   ```bash
   cd scraper
   python3 build_all.py --tier 1 --cdp-url http://localhost:9222
   ```

5. Run Tier 2 (policies):
   ```bash
   python3 build_all.py --tier 2 --cdp-url http://localhost:9222
   ```

6. Quality check:
   - `cat data/manifest.json` — verify counts
   - `ls data/merit-badges/ | wc -l` — should be 130+
   - `ls data/ranks/` — should be 8 files (index + 7 ranks)
   - `ls data/policies/` — should be 5+ files

7. Commit:
   ```bash
   git add data/ scraper/
   git commit -m "chore(data): 2026.Q1 initial knowledge base build"
   git push origin main
   ```

---

## Known issues / notes
- Councils: 137 found (BSA has ~250+ councils — need more representative zips or a different API endpoint to get full coverage)
- Eagle Scout not in scraper/data/ — only in data/ (correct location)
- `scraper/data/` is leftover junk from pre-fix runs — can be deleted after confirming `data/` is complete
- The `(cid:22)` artifacts in rank PDFs are checkbox icons from the rank tracking pages — harmless but ugly
