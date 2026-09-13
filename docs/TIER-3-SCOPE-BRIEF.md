# Decision Brief – Tier 3 (Roles + Program Manuals)

**Status:** Decision requested \
**Date:** 2026-09-13 \
**Prepared by:** Tactical Architect, `scouting-kb` \
**Decision owner:** Chief Architect (Studio) \
**Repos affected:** `scouting-kb`, `scouting-reference` \
**Blocks:** any consumer needing role or manual content; `DEVELOPMENT_ROADMAP.md` §"Adding Tier 3 Content"

---

## Why this is on the table

`scouting-kb`'s tier table has listed Tier 3 as "Roles, program manuals – not yet implemented" since the repo was scaffolded. It has never been scoped, and in the meantime `scouting-reference` was created and **claimed one half of it**. Nobody has reconciled the two documents, so the open item reads like a backlog task when it is actually a boundary question plus a sizeable project.

This brief does not ask for Tier 3 to be built. It asks for the boundary to be settled so the roadmap line stops implying work that may not belong here.

---

## The conflict, stated plainly

| Document | Date | Claim |
|---|---|---|
| `scouting-kb/DEVELOPMENT_ROADMAP.md` §"Adding Tier 3 Content" | repo scaffold, 2026-03 | Tier 3 = roles + program manuals. "Create `scraper/fetch_roles.py`… Known BSA role pages: Scoutmaster, Assistant Scoutmaster, Committee Chair, Treasurer" |
| `scouting-reference/docs/decisions/ADR-001` | 2026-04-24, **Accepted, decided by the Studio** | Curated repo exists for content "that isn't centralized on scouting.org and therefore can't be scraped by `scouting-kb`" – and names **position descriptions** in the same sentence as ceremonies and handbook synthesis |
| `scouting-reference/docs/SCOPE.md` | current | In scope: "Position descriptions covering adult registered positions and youth leadership positions (PLC roles)". Out of scope: "**Scraped content** – that's `scouting-kb`" |

`scouting-reference` already has the folders, with coverage targets written out and no files yet: `data/positions/adult/index.md` lists SM, ASM, Crew Advisor, Skipper, Cubmaster, den leaders, CC, Treasurer, Secretary; `data/positions/youth-leadership/index.md` covers PLC roles.

**ADR-001 is the later document, it is Accepted, and the Studio decided it.** The roadmap line is the older claim and has never been revisited. The cheap half of Tier 3 may simply not be this repo's work.

---

## Half 1 – Roles

### What the sources actually look like (probed 2026-09-13, bare `curl`, single fetches, following redirects)

| URL | Result |
|---|---|
| `/training/adult/` | `200` – but **redirects to `/training/`**, a general training hub, not role descriptions |
| `/programs/scouts-bsa/leaders/` | `200` – **redirects to a Venturing awards page**, unrelated content |
| `/about/position-descriptions/` | `404` (styled "Page not found", ~1.46 MB of chrome) |

Two of three guesses redirect somewhere unrelated rather than failing, which is the more dangerous shape: a scraper pointed at either would fetch `200`, extract real prose, and write a well-formed file describing the wrong thing. That is precisely the failure mode `scouting-kb` has already shipped twice (`reporting-youth-protection`, `chartered-organization`) and now guards with Check A/Check B.

This is weak evidence about the whole corpus – three URLs, guessed, not enumerated. But it is consistent with ADR-001's premise: **BSA's position descriptions live in handbooks and PDFs, not as a centralized set of scrapeable pages.** If a canonical index exists, nobody has found it, and finding it is the first task of any estimate below.

### Effort, if it were in scope

**Low – roughly half a session.** `fetch_roles.py` is structurally `fetch_policies.py`: a hand-maintained URL table, `extract_content()`, `clean_markdown()`, `absolutize_relative_links()`, and both label checks, which would carry over unchanged and are exactly the guard this content needs given the redirect behaviour above. The cost is not the code. The cost is assembling and maintaining a URL table for pages that may not exist as such.

---

## Half 2 – Program manuals

### What the sources look like (probed 2026-09-13)

| Source | Result |
|---|---|
| Guide to Advancement, `filestore.scouting.org/filestore/pdf/33088.pdf` | `200`, **27,267,426 bytes** |
| Language of Scouting, `/resources/los/` | `200`, real page, "Revised February 2020" |
| Guide to Awards and Insignia at the guessed path | `404` |

### Effort: this is the real project

The roadmap's guidance – "use `pdfplumber` to extract key sections by page range, not the full document" – understates it. A **15-page** rank PDF produced, in one session, six distinct documented failure classes: doubled glyphs from fake-bold printing that corrupted a section-boundary regex and let one rank absorb another's content; blank fill-in tables that silently consumed list numbering; two-column lettered lists that interleave into garbage under plain text extraction; footnote markers glued onto words; table row counts invisible to text-based counting; and a missing blank line before a heading that merged a whole section into the preceding requirement. All of that is in `PLAYBOOK.md` and all of it applies again to a 500-page book, plus failure modes a leaflet does not have.

There is also a design question the roadmap does not answer, and it is the one that decides whether this ages well:

- **What is a file?** One per chapter, per topic, or per page range?
- **Page references rot.** The roadmap proposes "page reference in frontmatter." Page numbers shift between editions, so that citation is wrong the first time BSA reflows the document – and wrong silently, which is this repo's recurring theme. Section or topic anchors are more stable but harder to extract.
- **Does the quarterly `--force` rebuild re-extract a 27 MB PDF every time**, and what does the diff look like when it does?

**Estimate: 2–3 sessions minimum**, the first spent entirely on chunking strategy plus one manual end-to-end before any second manual is attempted.

---

## Precedents the Studio has already set here

Three existing decisions frame this one, and they do not all point the same way – which is why this needs a call rather than an inference:

- **Brand Center – excluded** (2026-09-05). On the charter agreement's RESOURCES list, so nominally in scope, but it is an asset portal with no policy prose. *Scope list membership did not make it scrapeable.*
- **Governance PDFs – included** (2026-09-05). Charter and Bylaws, Rules and Regulations scraped into Tier 2 rather than curated downstream, after verifying they extract cleanly. *PDF-ness alone was not disqualifying; extraction quality decided it.*
- **ADR-001 – curated/scraped split by source availability** (2026-04-24). The dividing line is whether the content is centralized on scouting.org at all.

Applying all three consistently: manuals resemble the governance PDFs (real prose, extractable, one canonical source), while roles resemble the Brand Center (named in a plan, but the source does not exist in the form the plan assumed).

---

## Options

### Roles

1. **Cede to `scouting-reference`.** Delete the roles half from this repo's roadmap and tier table; the curated repo already claims it, has the folders, and ADR-001 already decided the principle. Cost: none here. Consumers wanting role content take the `scouting-reference` submodule, which `troop-452-scouting-tool` already pins and `scoutsync` lists as "Future".
2. **Build `fetch_roles.py` anyway**, for whatever subset does exist as pages. Cost: half a session plus ongoing URL-table maintenance, and it splits role content across two repos with different trust models – a consumer would have to check both and reconcile.
3. **Split by source shape**: scrape what is a page, curate what is not. Most faithful to ADR-001's wording, worst for a consumer, who now must know which half of a role's description lives where.

### Manuals

1. **Build Tier 3 manuals as a scoped project** – one manual end-to-end first (Guide to Advancement is the highest-value and the hardest; Language of Scouting is a *web page*, so it is nearly free and a poor proxy for the work).
2. **Defer until a consumer actually needs it.** No consumer does today. The roadmap line stays but is explicitly marked "not scheduled, needs scoping" so it stops reading as ready-to-pick-up.
3. **Drop manuals from this repo entirely** and treat handbook content as the curated repo's "handbook-references" territory, which already exists as a folder there.

---

## Recommendation

**Roles → Option 1 (cede).** ADR-001 is later, Accepted, Studio-decided, and the source probe is consistent with its premise. Two conflicting claims on the same content is the thing worth fixing today; which repo wins matters less than that only one does.

**Manuals → Option 2 (defer, explicitly).** Nothing is blocked on it – no consumer needs manual content – and a 27 MB PDF is not a "next task." Marking it unscheduled costs nothing and stops the roadmap implying otherwise. Revisit when a consumer names a specific manual and a specific need, because *that* determines chunking, which is the decision the work actually hinges on.

**Net effect if accepted:** Tier 3 as currently written ceases to exist. The tier table gets one honest line instead of a placeholder that has looked like pending work for six months.

---

## What changes if this is accepted

| File | Change |
|---|---|
| `scouting-kb/CLAUDE.md` | Tier table row 3 – replace "Roles, program manuals / Not yet implemented" with the decision and a pointer here |
| `scouting-kb/DEVELOPMENT_ROADMAP.md` | §"Adding Tier 3 Content" – replace the `fetch_roles.py` instructions with the outcome; keep the manuals sketch under an explicit "unscheduled" heading |
| `scouting-kb/README.md` | Roles row currently reads "_Tier 3 – coming later_"; point it at `scouting-reference` |
| `scouting-kb/docs/HANDOFF.md` | Close the "Tier 3 not implemented" open item |
| `scouting-reference/docs/decisions/` | New ADR, or an amendment to ADR-001, recording that roles are unambiguously its territory |
| `scouting-kb/docs/PLAYBOOK.md` | Dated entry, matching the Brand Center and governance-PDF entries |

---

## Known unknowns

- **The role-page probe is three guessed URLs, not an enumeration.** If a canonical position-description index exists on scouting.org, the roles recommendation weakens considerably. Anyone overturning this should start there.
- **No manual other than Guide to Advancement was located.** Two guessed filestore paths 404'd. The manual corpus size is therefore unknown – "program manuals" could be one document or fifteen.
- **Nobody has asked for either.** Both recommendations are partly arguments from absence of demand, which is a reason to defer, not a reason to conclude the content is unwanted.
