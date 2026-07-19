# ICH Q1 Step 4 final-guidance gap assessment

> **Status: NOT STARTED — do not complete or promote a profile until the ICH
> Q1 Step 4 final document is officially published.** This is a controlled
> working template, not a claim of compliance or a regulatory assessment.

## 1. Source record

| Field | Required evidence | Recorded value |
|---|---|---|
| Final guideline title | Official ICH title | _Pending_ |
| ICH adoption date | Step 4 publication record | _Pending_ |
| Official document URL | `ich.org` / `database.ich.org` direct document URL | _Pending_ |
| File SHA-256 | Downloaded official PDF | _Pending_ |
| Review date / reviewer | UTC date and named maintainer | _Pending_ |
| Superseded documents | Q1A–Q1F / Q5C applicability stated by final text | _Pending_ |

Do not use an industry summary, consultation copy, or the existing
`Q1_consolidated_draft` profile as evidence for any final value.

## 2. Controlled-constant mapping

For every row, cite the final document section/page and state whether the
existing implementation is unchanged, profile-only, or requires new analysis
logic. Blank fields block promotion of a final profile.

| Controlled item | Current Q1A(R2)+Q1E value | Final Q1 value | Final source locator | Delta / implementation decision |
|---|---:|---:|---|---|
| Poolability alpha | 0.25 | _Pending_ | _Pending_ | _Pending_ |
| Confidence level | 0.95 | _Pending_ | _Pending_ | _Pending_ |
| One-sided t quantile | 0.95 | _Pending_ | _Pending_ | _Pending_ |
| Two-sided t quantile | 0.975 | _Pending_ | _Pending_ | _Pending_ |
| Extrapolation maximum factor | 2.0 | _Pending_ | _Pending_ | _Pending_ |
| Extrapolation maximum months beyond data | 12 | _Pending_ | _Pending_ | _Pending_ |
| Assay significant-change threshold (%) | 5.0 | _Pending_ | _Pending_ | _Pending_ |
| Significant-change criteria | assay, degradant, physical, pH, dissolution | _Pending_ | _Pending_ | _Pending_ |
| Retest-period / shelf-life terminology | product=shelf life; substance=retest period | _Pending_ | _Pending_ | _Pending_ |
| Scope, study design, and data expectations | current supported features and exclusions | _Pending_ | _Pending_ | _Pending_ |
| Disclaimer / decision-support wording | Q1E-inspired, non-GxP disclaimer | _Pending_ | _Pending_ | _Pending_ |

## 3. Required decision record

- Classify the final-text outcome as one of: **no implementation change**,
  **new final profile only**, or **algorithm / scope change**.
- Preserve `Q1_consolidated_draft` unchanged for historical comparison.
- If approved, add a distinct final profile with `status="effective"`, an
  immutable final reference, and a selector separate from the draft selector.
- Do not switch `DEFAULT_PROFILE` merely because Step 4 is published. Record
  the rationale, approved version target, and migration notes here.
- A default-profile switch or changed numerical output is a major release
  (`v2.0.0` from the current v1 line). A hosted analysis backend is outside
  this assessment.

## 4. Verification evidence required before release

- [ ] Independent golden calculation reviewed against every changed controlled
  value; existing golden data remains unchanged only when justified above.
- [ ] New final-profile golden fixture and edge cases cover all changed
  numerical behavior.
- [ ] Single-, multi-attribute, no-data, sensitivity, JSON, HTML, CLI, and UI
  tests prove the final profile’s exact provenance and values.
- [ ] Public sample HTML/JSON/PDF and the synchronized `site/` copy carry the
  final profile only where deliberately selected.
- [ ] Full test suite, independent golden regeneration, installed-CLI smoke,
  and GitHub Quality workflow are green.
- [ ] `CHANGELOG.md`, `README.md`, `HANDOVER.md`, and `NEXT_STEPS.md` state
  the final reference and migration decision consistently.
- [ ] Major-version markers, annotated tag, and GitHub release are prepared
  only after every preceding item is evidenced.

## 5. Approval outcome

| Decision | Owner | Date | Evidence link / commit |
|---|---|---|---|
| Final profile approved for implementation | _Pending_ | _Pending_ | _Pending_ |
| Default profile change approved | _Pending_ | _Pending_ | _Pending_ |
| Major release approved | _Pending_ | _Pending_ | _Pending_ |

