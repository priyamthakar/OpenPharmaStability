# ICH Q1 September 2026 revised-draft delta worksheet

> **BANNER — READ BEFORE EDITING**
>
> This file is **NOT** the Step 4 gap assessment.
> It does **NOT** authorize any change to `GuidanceProfile` values,
> `DEFAULT_PROFILE`, analysis math, goldens, or claims.
> Leave `Q1_FINAL_GAP_ASSESSMENT_TEMPLATE.md` **unfilled** until the
> official ICH Q1 Step 4 final document is published.
>
> This worksheet exists only to capture deltas (if any) between the
> current `Q1AE` / April 2025 Step 2b spot-check and a future
> **September 2026 revised draft**, once that revised text is
> officially published. Filling September columns is a documentation
> exercise only — not an implementation trigger.

---

## 1. Source provenance (revised draft)

Fill only when the official September 2026 revised draft PDF is
available from ICH. Do not invent URLs, dates, or hashes.

| Field | Value |
|---|---|
| Document title | _Pending — revised draft not yet published_ |
| Official document URL | _Pending_ |
| Download date (UTC) | _Pending_ |
| PDF SHA-256 | _Pending_ |
| Reviewer / review date | _Pending_ |
| Related work-plan note | ICH Q1 EWG work plan (11 Feb 2026) targets September 2026 PWP engagement / revised text ahead of Step 3; see CHANGELOG Regulatory watch — 2026-07-24 |

Do not treat industry summaries, consultation copies, or the
`Q1_consolidated_draft` profile as evidence for any September value.

---

## 2. Controlled-constant delta table

Mirrors `Q1_FINAL_GAP_ASSESSMENT_TEMPLATE.md` §2 item set against
current Q1AE / Step 2b (Apr 2025) spot-check values from the
**2026-07-24** regulatory watch.

| Controlled item | Current Q1AE value | Step 2b (Apr 2025) note | Sept 2026 revised value | Delta / decision |
|---|---|---|---|---|
| Poolability alpha | 0.25 | Aligns (Annex 2 / §13.3 batch-related terms); no toolkit change | _Pending_ | _Pending_ |
| Confidence level | 0.95 | Aligns (§13.2.1 mean-response confidence); no toolkit change | _Pending_ | _Pending_ |
| One-sided t quantile | 0.95 | Aligns (one-sided 95% mean-response limit for single-sided attributes, §13.2.1) | _Pending_ | _Pending_ |
| Two-sided t quantile | 0.975 | Aligns (two-sided 95% for dual-sided attributes → 0.975 t-quantile, §13.2.1) | _Pending_ | _Pending_ |
| Extrapolation maximum factor | 2.0 | Aligns (up to twice long-term data when statistical analysis performed, §13.2.6.4) | _Pending_ | _Pending_ |
| Extrapolation maximum months beyond data | 12 | Aligns (not more than 12 months beyond long-term data, §13.2.6.4) | _Pending_ | _Pending_ |
| Assay significant-change threshold (%) | 5.0 | Aligns (5% change from initial); no toolkit change | _Pending_ | _Pending_ |
| Significant-change criteria | assay, degradant, physical, pH, dissolution | Retained in Step 2b spot-check; no toolkit change | _Pending_ | _Pending_ |
| Retest-period / shelf-life terminology | product = shelf life; substance = retest period | Terminology retained; no toolkit change | _Pending_ | _Pending_ |

**Pre-fill basis:** CHANGELOG.md — Regulatory watch — 2026-07-24 (Step 2b
spot-check vs controlled constants; no profile or math change warranted).

**September columns:** leave as `_Pending_` until the revised draft is
published and this worksheet’s provenance block is completed.

---

## 3. When to fill

Fill the **September** columns (and provenance block) only when **all**
of the following are true:

1. ICH (or an official regional channel linking the same PDF) publishes
   the September 2026 revised consolidated Q1 draft text.
2. You download the official PDF, record URL, download date, and
   SHA-256 in §1.
3. You compare each controlled item above to the revised text and cite
   section/page in notes or the Delta column.
4. You record a dated “Regulatory watch” entry in `CHANGELOG.md`
   summarizing findings (still no code/profile change from this file
   alone).

After Step 4 final publication (expected later; currently targeted
November 2026 on the 2026-07-24 watch), use
`Q1_FINAL_GAP_ASSESSMENT_TEMPLATE.md` — **not** this worksheet — for
the migration / profile decision.

---

## 4. What NOT to do

- Do **not** treat this worksheet as authorization to edit
  `openpharmastability/regulatory/profile.py`, `contracts.py`, goldens,
  or analysis math.
- Do **not** change `DEFAULT_PROFILE` or overwrite
  `Q1_CONSOLIDATED_DRAFT`.
- Do **not** fill or promote
  `Q1_FINAL_GAP_ASSESSMENT_TEMPLATE.md` based on a revised draft.
- Do **not** invent September values, URLs, or hashes before the
  revised draft is published.
- Do **not** claim regulatory compliance or that the toolkit
  implements final consolidated Q1.
- Do **not** bump major version or regenerate goldens from September
  draft deltas alone; Step 4 + gap assessment + explicit release
  decision are required for that path.
