# ICH Q1 consolidated guideline — watch checklist

Operational mirror of `NEXT_STEPS.md` §10.1. Revisit each quarter or on
any ICH news. This checklist is documentation-only: completing it does
not change analysis constants, profiles, or claims.

---

## Status context (as of last watch)

- Consolidated **ICH Q1** (replacing Q1A–Q1F + Q5C) reached **Step 2b
  in April 2025**; EMA consultation closed July 2025.
- **Step 4 (final) is not published.** Until Step 4, the toolkit
  implements **Q1A(R2) + Q1E** and labels outputs “Q1E-inspired.”
- Last formal re-check: **2026-07-24** (see `CHANGELOG.md` —
  Regulatory watch). Anticipated milestones from the ICH Q1 EWG work
  plan: **September 2026** revised text / PWP engagement; **November
  2026** Step 3 / Step 4 adoption (targets, not guarantees).

---

## Watch prompts (from NEXT_STEPS.md §10.1)

Answer each item with date, source URL, and a one-line finding:

- [ ] Has consolidated Q1 reached **Step 4**?
  - If **yes** → trigger `NEXT_STEPS.md` §10.2 migration path and
    complete `Q1_FINAL_GAP_ASSESSMENT_TEMPLATE.md` (Step 4 only).
  - If **no** → no final-profile work; continue Q1AE default.
- [ ] Did the **poolability α (0.25)** change?
- [ ] Did the **mean-response one-sided 95%** bound change?
- [ ] Did the **2× / +12-month** RT extrapolation caps change?
- [ ] Did the **significant-change checklist** change (including the
      assay 5% threshold and criteria set)?
- [ ] Any change to **retest-period vs shelf-life** terminology?

Optional companion (when September 2026 revised draft appears):

- [ ] Compare every controlled row in
      `Q1_SEPTEMBER_2026_REVISED_DRAFT_DELTA.md` and fill September
      columns + provenance (URL, download date, PDF SHA-256) only from
      the official PDF.

---

## Where to log findings

Record every watch pass in **`CHANGELOG.md`** under a dated heading:

```text
## Regulatory watch — YYYY-MM-DD
```

Include: Step 4 status, which constants were spot-checked, whether any
delta was found, and the explicit **Action** (usually “none —
keep DEFAULT_PROFILE = Q1AE”). Do not imply a package version bump
unless a separate release is intentionally made.

---

## Pointers

| Artifact | Role |
|---|---|
| `Q1_SEPTEMBER_2026_REVISED_DRAFT_DELTA.md` | Worksheet for September **revised draft** deltas only. Not an implementation gate. |
| `Q1_FINAL_GAP_ASSESSMENT_TEMPLATE.md` | **Step 4 only.** Leave unfilled until the official final Q1 document is published. |
| `NEXT_STEPS.md` §10.1 / §10.2 | Source watch prompts and migration structuring. |
| `openpharmastability/regulatory/profile.py` | Live profiles (`Q1AE`, `Q1_CONSOLIDATED_DRAFT`). Do not edit from a watch pass alone. |

---

## Hard constraints

1. **Never overwrite** `Q1_CONSOLIDATED_DRAFT` to “update” it from a
   revised draft or final text without a deliberate, separately
   approved release process (historical draft audit trail).
2. **Never switch** `DEFAULT_PROFILE` away from `Q1AE` because a draft
   or even Step 4 was published — default switch requires the gap
   assessment, major-release decision, and golden regeneration path.
3. **Never fill** `Q1_FINAL_GAP_ASSESSMENT_TEMPLATE.md` until Step 4
   final guidance is officially published.
4. **Never** treat September revised-draft notes as authorization to
   change `profile.py`, `contracts.py`, goldens, or claims.
5. Keep public and report wording **decision-support / Q1E-inspired**;
   never claim regulatory compliance or GxP validation.
