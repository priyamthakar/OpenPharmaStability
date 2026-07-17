# Changelog

All notable changes to OpenPharmaStability are documented here.
Versions follow [SemVer](https://semver.org/). v1.x releases keep the
Python statistics engine authoritative and treat UI/API additions as thin
surfaces over generated artifacts.

## [1.1.0] — 2026-07-17 — guidance provenance and release-quality gates

### Added

- Guidance profiles now carry explicit maturity and document-reference
  provenance. Reports, JSON records, public samples, and the local UI surface
  the selected profile; the provisional consolidated-Q1 draft remains opt-in
  and is never the default.
- A GitHub Quality workflow verifies Python 3.11/3.12, independently
  regenerated golden values, an installed-CLI report, and deploy-folder sync
  on pull requests and pushes to `main`.

### Fixed

- The active profile now controls every profile-dependent analysis path,
  including sensitivity refits and direct Python threshold defaults.
- Multi-attribute results hold an explicit aggregate provenance snapshot,
  preserve it for no-data attributes, and reject mixed-profile report objects
  instead of inferring guidance from the first attribute.

### Notes

- Default analysis constants and golden stability results are unchanged.
- The final consolidated ICH Q1 Step 4 guideline is not yet published; its
  migration remains a separately gated major-release assessment. A hosted
  analysis backend remains a separate product decision.

## Quality CI — 2026-07-17

No package version or analysis-math change.

- Added `.github/workflows/quality.yml` for pull requests, `main` pushes, and
  manual runs. It tests Python 3.11/3.12, independently checks the golden
  fixture, validates an installed-CLI report end to end, and verifies static
  site synchronization before deployment.

## Release and deployment truth sync — 2026-07-17

No package version or analysis-math change.

- Merged Graphite Dark PR #7 to `main` at commit `3f2b5bf`.
- Published the `v1.0.4` tag and GitHub Release.
- Configured the account-scoped Cloudflare Pages deployment secret without
  storing local Wrangler OAuth credentials.
- Verified unattended GitHub Actions deployment in run `29590938841`; preview
  `https://8fdcfa96.openpharmastability.pages.dev` and the canonical site return
  HTTP 200, with canonical HTML matching LF-normalized `site/index.html`.
- Synchronized `HANDOVER.md`, `NEXT_STEPS.md`, `README.md`, and the session
  summary to the post-release state.

## Public sample PDF — 2026-07-17

No package version or analysis-math change.

- Added a print-ready PDF of the canonical golden assay report at
  `site-sample/sample-report.pdf` and mirrored it into the deploy artifact.
- Verified all 9 pages for layout, plot rendering, decision values, governing
  batch, and the mandatory decision-support disclaimer.
- Linked the PDF from the public artifact ledger and added its PDF signature to
  automated website asset QA.

## Public-site Graphite Dark redesign — 2026-07-17

No package version or analysis-math change.

- Completed desktop/mobile production capture and interaction QA; navigation,
  truth copy, and sample HTML/JSON/plot links passed.
- Added `UI_UX_AUDIT.md` with screenshot-grounded findings and source-level
  accessibility risks.
- Replaced the old portfolio-showcase design guidance in `DESIGN.md` with an
  evidence-led anti-slop public-site contract.
- Updated `HANDOVER.md`, `NEXT_STEPS.md` §11, `README.md`, and
  `CMC_ANALYTICS_POSITIONING.md` to make the public redesign the active priority.
- Added `SESSION_SUMMARY_2026-07-17.md` with merged PRs, production deployment,
  Cloudflare state, verification evidence, guardrails, and exact continuation
  steps.
- Implemented the user-selected Graphite Dark direction in
  `OpenPharmaStability.dc.html` and synchronized `site/index.html`.
- Replaced the public App UI / Design System showcase with a single evidence-led
  page using the real confidence plot and exact golden decision record.
- Reworked website QA for desktop/mobile overflow, semantic landmarks, exact
  scientific copy, primary CTA, console state, and sample artifacts.
- Local and production QA plus side-by-side visual comparison passed. Wrangler
  deployment `268ac970-4f37-4ca9-b0db-4b3c8cc11deb` is live at the canonical
  Pages URL with an exact local/remote HTML hash match.

## Docs / portfolio — 2026-07-09

No code or version change. Portfolio and handover materials only.

- README: golden assay case study, CMC reviewer walkthrough, Local UI
  screenshot (`site-sample/ui-workspace.png`), multi-attribute limiting
  CQA section (assay 16 mo / impurity_a **7 mo** limiting).
- `site-sample/multi/`: multi-attribute HTML/JSON/plots with fixed
  `source_epoch=1717200000`; mirrored under `site/site-sample/multi/`.
- `CMC_ANALYTICS_POSITIONING.md`: CMC role mapping, resume bullets, pitch.
- `HANDOVER.md` / `NEXT_STEPS.md` §11: oriented to v1.0.4 + portfolio status.

## Regulatory watch — 2026-07-17

No analysis constants, default profile, claims, or version changed. Official
ICH planning expects a revised consolidated Q1 draft in September 2026 and
Step 4 adoption in November 2026; the guideline is not final as of this date.
Review the September text for deltas, then perform the profile/golden-file
assessment only after the Step 4 document is published. A hosted analysis
backend remains a separate product decision and is not implied by this work.

- Added non-numeric guidance provenance to each result and export: profile
  maturity (`effective` or `draft`) and the represented guidance reference.
  The local UI offers only effective profiles, while explicit CLI/Python draft
  selection remains available for comparison. Statistical outputs are unchanged.

## Regulatory watch — 2026-07-06

No code or version change. Recorded per `NEXT_STEPS.md` §10.1's quarterly
regulatory-watch instruction.

- The consolidated **ICH Q1** guideline (replacing Q1A–Q1F + Q5C) remains at
  **Step 2b**. The EMA public consultation on the Step 2b draft closed
  30 July 2025. **Step 4 (final) is expected no earlier than late 2026**;
  industry trackers as of mid-2026 still describe the document as subject to
  further revision and not yet citable as final.
  ([StabilityHub, Sep 2025](https://stabilityhub.com/2025/09/07/ich-q1-draft-guideline-marks-a-new-era-for-stability-testing/);
  [EMA Step 2b draft](https://www.ema.europa.eu/en/documents/scientific-guideline/draft-ich-q1-guideline-stability-testing-drug-substances-drug-products-step-2b_en.pdf))
- No change identified to the poolability alpha (0.25), the one-sided 95%
  mean-response bound, the 2x / +12-month extrapolation caps, or shelf-life
  vs. retest-period terminology.
- **Action: none required.** The toolkit continues to default to the
  `Q1A_R2+Q1E` guidance profile, labelled "Q1E-inspired." Given the "late
  2026 at the earliest" estimate for Step 4, the next re-check should happen
  in Q4 2026 (see `NEXT_STEPS.md` §10.2 for the migration path once Step 4
  lands).

## [1.0.4] — 2026-06-23 — Save as PDF button in local UI workspace

### Added
- **Save as PDF** button in the local web workspace report preview. After a
  successful analysis the button appears in the preview header and triggers
  `window.print()` on the embedded report iframe, letting users save the
  rendered HTML report as a PDF via the browser's native print-to-PDF dialog.
- Print CSS in `report.html.j2`: `print-color-adjust: exact` preserves chart
  and section colours; `@page` margin (`14mm 16mm`) gives clean A4 margins.
- `.pdf-download-btn` style rule (terracotta `#a6533b`, hover `#8f4530`,
  focus-visible ring) consistent with the DESIGN.md colour tokens.

### Changed
- Bumped package/tool version markers to `1.0.4`.

### Notes
- No statistics, report-generation, or CLI behavior changed. The PDF dialog
  is browser-native; no server-side rendering or new Python dependency is
  introduced. The button is hidden until a successful analysis result is
  loaded into the preview frame.

## [1.0.3] — 2026-06-22 — toolchain-robust golden/regen + mixed-model boundary checks

### Fixed
- `tools/regen_expected.py --check` now compares regenerated values to the
  committed `examples/assay_3batch.expected.json` with a relative + absolute
  tolerance (`rtol=1e-9`, `atol=1e-12`) instead of exact float equality. On a
  modern toolchain (numpy 2.4 / scipy 1.18 / BLAS variant) the independent
  recomputation drifts in the last floating-point digit
  (e.g. `0.3312058496592973` vs `...72`), which previously made
  `--check` exit non-zero and failed
  `validation/test_regen.py::test_check_mode_returns_zero_when_matches` and
  `::test_regen_is_idempotent` on a clean install. Integers (including the
  rounded-down shelf-life month) and all non-numeric values are still compared
  exactly, so a genuine regression is still caught.
- `validation/test_stats_regression.py::test_random_path_detects_boundary_on_2_batch_frame`
  now accepts either `boundary=True` **or** `converged=False` as a valid
  "degenerate random-effects fit" signal. Newer statsmodels (0.14.6) reports
  the identical-value 2-batch fixture as non-convergence rather than a boundary
  hit; both outcomes correctly flag the fit as untrustworthy. The test still
  forbids a silent `converged=True, boundary=False` on a degenerate fixture.

### Changed
- Bumped package/tool version markers to `1.0.3`.

### Notes
- No statistics, report-generation, CLI, or UI runtime behavior changed. These
  are test/validation robustness fixes so the suite is green on a fresh modern
  install (was 3 failed / 476 passed; now 479 passed / 4 host-dependent PDF
  skips). The analysis math, golden values, and the verified shelf life
  (17 months on the golden dataset) are unchanged.

## [1.0.2] — 2026-06-21 — handover and roadmap orientation sync

### Changed
- Bumped package/tool version markers to `1.0.2`.
- Updated HANDOVER and NEXT_STEPS current-version orientation from
  v1.0.0/v1.0.1 wording to the live v1.0.2 state.
- Marked the `apply_extrapolation_caps()` `dataclasses.replace` refactor
  as already shipped, matching the live implementation and regression test.

### Notes
- No statistics, report-generation, CLI behavior, or UI runtime behavior changed.

## [1.0.1] — 2026-06-20 — release documentation truth sync

### Changed
- Bumped package/tool version markers to `1.0.1`.
- Updated README, HANDOVER, and NEXT_STEPS to reflect the live v1.0.0+
  state: local UI shipped, hosted UI work remains future polish, and the
  current test collection count is 483.
- Removed stale handover language that still described the UI pass as future
  v0.7/v1.0 work.

### Notes
- No statistics, report-generation, CLI behavior, or UI runtime behavior changed.

## [1.0.0] — 2026-06-20 — v1 local UI workspace + UI service manifest

### Theme
First v1 usability release. The mature Python statistics/reporting engine
remains authoritative, and the UI is a thin local client over Python-generated
HTML, JSON, plots, and artifact bundles. No statistical logic was reimplemented
in JavaScript.

### Added
- **Local v1 UI server** (`openpharmastability.ui_server`) plus the
  `openpharmastability-ui` console script. It serves a stdlib-only local
  web workspace for uploading CSV/XLSX data, selecting condition/attributes,
  choosing product type and guidance profile, toggling advanced options, and
  previewing/downloading generated report artifacts.
- **UI-facing service manifest** (`openpharmastability.ui_service`):
  `UIAnalysisOptions`, `UIAnalysisManifest`, `UIArtifactFile`, and
  `analyze_for_ui()`. This wraps the existing Python API and standardizes
  HTML/JSON/plot/PDF artifact metadata, SHA-256 values, warnings, guidance
  profile, limiting attribute, and supported shelf-life/retest-period summary.
- **Static v1 workspace assets** under `openpharmastability/ui/static/`.
  The first screen is the usable analysis workflow, not a marketing page.
- **Tests** for the UI manifest single-attribute and multi-attribute paths.

### Changed
- `analyze_and_artifact()` now forwards `replicate_policy` and `bql_policy`
  into the actual analysis call as well as the plot-rendering validation path.
  Multi-attribute calls continue to treat single-attribute-only options
  (sensitivity, Arrhenius shelf-life prediction, per-batch Arrhenius) as
  no-ops, matching CLI behavior.
- `TOOL_VERSION` bumped to `1.0.0` (three locations).

### Notes
- The regulatory disclaimer remains unchanged. v1 is still
  decision-support / educational software, not a validated GxP or 21 CFR
  Part 11 system.
- `.hermes/` remains untracked local workspace state.

## [0.11.0] — 2026-06-20 — GuidanceProfile abstraction completed (CLI + audit + tests)

### Theme
Pure backend release, no UI changes. Completes the v0.10.0
GuidanceProfile seam: the active profile is now selectable from the
CLI, recorded as an audit fact on the result, surfaced in the JSON
and HTML reports, and proven to actually drive engine output via a
non-default-profile test. The default path is byte-identical to
v0.10.0; the golden file is unchanged.

### Added
- **Profile registry + `resolve_profile()`** (`regulatory/profile.py`).
  `PROFILES = {"q1ae": Q1AE, "q1-consolidated-draft": Q1_CONSOLIDATED_DRAFT}`;
  case-insensitive lookup; unknown names raise `ValueError` with the
  available keys. Exported from the package top level.
- **`Q1_CONSOLIDATED_DRAFT` profile** — a PROVISIONAL placeholder
  pending ICH Q1 consolidated Step 4. Its values mirror Q1AE so
  selecting it is numerically inert until the final numbers are
  confirmed; edit the values at Step 4 and bump MAJOR.
- **`--guidance` CLI flag** (`cli.py`). Default `q1ae`; choices
  `q1ae`, `q1-consolidated-draft`. Forwarded to both `analyze` and
  `analyze_many` via `_engine_kwargs`; unknown names exit 2 with a
  one-line ERROR.
- **`StabilityResult.profile_name`** (`contracts.py`) — additive
  field defaulting to `"Q1A_R2+Q1E"`; set by the engine from
  `profile.name`.
- **`guidance_profile` in the JSON decision record** (`record.py`,
  `multi_record.py`) and the **HTML report** (`html.py`,
  `report.html.j2` assumptions table).
- **Tests** (16 new): registry/resolver (6), `profile_name` field (2),
  engine `profile_name` recording + non-default-quantile threading
  proof (3), CLI `--guidance` (unknown→exit 2, q1ae==default,
  draft→profile_name) (3), JSON + HTML audit surfacing (2).

### Changed
- `--assay-change-threshold` default is now `None`, resolved from
  the active profile's `assay_change_threshold_pct` (5.0 for Q1AE)
  when not explicitly set. Default behavior unchanged.
- `TOOL_VERSION` bumped to `0.11.0` (three locations).

### Notes
- The golden file is unchanged — v0.11 only adds opt-in selection
  and audit; the default `analyze()` path is bit-identical to v0.10.0.
- `python tools/regen_expected.py --check` still exits 0.

## [0.10.0] — 2026-06-14 — GuidanceProfile abstraction + bidirectional quantile fix

### Theme
Pure backend release, no UI changes. Introduces the
`GuidanceProfile` abstraction that bundles every
regulator-defined numeric constant, implements the correct
two-sided 0.975 t-quantile for BIDIRECTIONAL crossings, and
adds the `governing_side` field to `CrossingResult`.  Also
ships fifteen additive §9 tests that were called for in
NEXT_STEPS but had not been written.  All changes are backward-
compatible: the default one-sided path is bit-identical to
v0.9.0 and the golden file is unchanged.

### Added
- **`GuidanceProfile` dataclass**
  (`openpharmastability/regulatory/profile.py`).  A frozen
  dataclass that bundles `poolability_alpha`, `confidence`,
  `one_sided_quantile`, `two_sided_quantile`,
  `extrapolation_max_factor`, `extrapolation_max_months_beyond`,
  and `assay_change_threshold_pct`.  The singleton `Q1AE` is
  defined as the default profile matching v0.9.0 constants.
  Both are exported from `openpharmastability` and
  `openpharmastability.regulatory`.
- **`profile=` keyword on `analyze()` and `analyze_many()`.**
  Accepts a `GuidanceProfile` (default `Q1AE`).  All hardcoded
  constants in the engine are now sourced from the active
  profile, enabling future alternative profiles (e.g. a
  forthcoming consolidated ICH Q1 profile) without algorithm
  rewrites.
- **Bidirectional two-sided quantile** (`stats/bounds.py`).
  `find_crossing()` now dispatches `Direction.BIDIRECTIONAL` to
  a dedicated `_bidirectional_crossing()` helper that evaluates
  both spec limits with the two-sided 0.975 t-quantile (per ICH
  Q1E), takes the earliest crossing, and records which spec
  limit governed via the new `governing_side` field.
- **`CrossingResult.governing_side`** (`contracts.py`).
  Optional `str` field (`"lower"` / `"upper"` / `None`).
  Populated by the bidirectional path; `None` on all one-sided
  paths.  Backward-compatible (appended with a default of
  `None`; existing positional constructions continue to work).
- **`governing_side` in JSON decision record**
  (`reports/record.py`).  The `to_decision_record()` output now
  includes `"governing_side"` at the top level alongside
  `"crossing_status"`.
- **§9 test additions** (15 new tests across 5 files):
  - `test_reporting.py`: `test_json_record_deterministic_with_fixed_epoch`
    (§9.2), `test_disclaimer_verbatim_in_json` (§9.4),
    `test_disclaimer_verbatim_in_html` (§9.3 companion).
  - `test_stats_crossing.py`: `test_bidirectional_uses_two_sided_quantile_and_is_tighter`
    (§9.8, new correct behavior), `test_bidirectional_no_crossing_when_wide_specs`,
    `test_all_four_crossing_statuses_covered` (§9.12 meta-guard).
  - `test_extrapolation.py`: `test_extrapolation_caps_preserves_all_result_fields`
    (§9.9 copy-block regression guard).
  - `test_data_bql.py`: `test_replicate_unknown_policy_raises` (§9.11).
  - `test_engine.py`: `test_engine_unknown_direction_raises_when_no_spec`
    (§9.7), `test_engine_two_batches_emits_q1e_warning` (§9.13),
    `test_engine_handles_single_time_point` (§9.14),
    `test_engine_handles_nan_value` (§9.15),
    `test_engine_handles_negative_time` (§9.16).

### Changed
- `find_crossing()` signature gains optional `one_sided_quantile`
  and `two_sided_quantile` keyword arguments (default to the
  same constants as v0.9.0; no numeric change on the default
  path).
- `apply_extrapolation_caps()` gains optional `max_factor` and
  `max_months_beyond` keyword arguments sourced from the active
  profile (defaults preserve v0.9.0 values exactly).
- `TOOL_VERSION` bumped to `"0.10.0"` (three locations:
  `contracts.py`, `__init__.py`, `pyproject.toml`).

### Fixed
- **Bidirectional quantile was incorrect.**  Before v0.10.0 the
  `BIDIRECTIONAL` path fell through to the one-sided 0.95
  quantile.  The two-sided 0.975 is now applied correctly, which
  changes numeric output for any `Direction.BIDIRECTIONAL` run.
  The default one-sided (DECREASING / INCREASING) path is
  unaffected and golden-file-identical to v0.9.0.

### Notes
- The `Q1AE` profile is intentionally singleton; do not mutate
  it.  Future alternative profiles should be defined as new
  `GuidanceProfile(...)` instances.
- The golden file (`examples/assay_3batch.expected.json`) is
  **unchanged** — the fix only affects BIDIRECTIONAL runs, which
  the golden dataset does not exercise.

## [0.9.0] — 2026-06-13 — Backend Features (no UI)

### Theme
More backend features, no UI. Per the user's "features first,
website last" reshape: the Cloudflare Pages + Claude Design
UI pass is deferred to v1.0. Python remains the authoritative
stats engine. This release ships four small but real additions:
Holm-corrected poolability p-values, multi-engine XLSX dispatch,
per-batch Arrhenius rate diagnostic, and multi-attribute
metadata `unit` + `report_order` surfacing.

### Added
- **Holm-Bonferroni corrected poolability p-values.** New
  additive `PoolabilityResult.p_slopes_holm` /
  `p_intercepts_holm` fields. The v0.1 3-step nested ANCOVA
  poolability test runs two hypothesis tests (slopes +
  intercepts); the new fields record the Holm-corrected
  p-values that preserve the family-wise error rate at `alpha`
  while gaining power over the conservative Bonferroni
  correction. The original (uncorrected) `p_slopes` /
  `p_intercepts` are unchanged. `None` until the corresponding
  test is reached (e.g. `p_intercepts_holm is None` if the
  slopes test already rejected). Reported in the JSON record
  and the HTML report.
- **Multi-engine `analyze_many` accepts XLSX / XLSM directly.**
  The single-attribute `engine.analyze()` was wired to
  `load_table` in v0.7.0; v0.9.0 does the same for the
  multi-attribute `analyze_many`. The symmetry fix removes the
  last remaining CSV-only path in the engine. New
  `data.xlsx.load_xlsx` callers in `multi_engine.py`; the
  multi CLI path accepts `.xlsx` / `.xlsm` exactly like the
  single path.
- **Per-batch Arrhenius rate diagnostic + outlier flag.**
  New `--arrhenius-per-batch` flag. When set, the engine
  builds a per-batch rate dict per temperature (one
  log-linear OLS per `(batch, temp_c)` cell) and surfaces it
  on `ArrheniusResult.per_batch_rate_by_temp`. Any batch whose
  median rate across temperatures is more than
  `outlier_z_threshold` (default 2.5) robust z-scores from the
  per-temperature median is recorded in
  `ArrheniusResult.outlier_batches` with a note. Reported in
  the JSON record and the HTML report.
- **Multi-attribute `unit` + `report_order` surfacing.** The
  `AttributeMetadata` dataclass already carried `unit` and
  `report_order` (v0.2.0 contract). v0.9.0 makes them visible
  in the multi-attribute JSON record (per attribute) and the
  multi HTML report (per-attribute block + sorted overview
  table when `report_order` is supplied). The
  `AcceptanceCriteriaRow` already included `unit` (v0.7.0);
  v0.9.0 closes the loop on the per-attribute HTML block and
  the per-row JSON layout.

### Tests
- `validation/test_stats_poolability.py` extended (~3 tests):
  Holm-corrected p-values are larger than or equal to the raw
  p-values, never smaller; when the slopes test rejects, the
  slopes Holm field equals the raw; when both tests run, the
  Holm ordering follows the canonical Holm step-up rule.
- `validation/test_multi_engine.py` extended (~2 tests):
  `analyze_many` accepts an XLSX mirror of the multi-attribute
  fixture and produces the same per-attribute results as the
  CSV path.
- `validation/test_arrhenius.py` extended (~3 tests):
  per-batch rate dict is populated when `--arrhenius-per-batch`
  is set; outlier detection flags a single batch whose rate is
  far from the others; the regular v0.5.0 / v0.8.0 path is
  unchanged when the flag is absent.
- `validation/test_multi_reporting.py` extended (~2 tests):
  the per-attribute HTML block carries `unit` when the
  metadata supplies it; the overview table is sorted by
  `report_order` when supplied.
- Total: ~465 tests passing (was 437 at v0.8.0; +28 new).

### Backward compatibility
- All v0.8.0 single-attribute and multi-attribute golden paths
  still pass. The default analyze path is byte-equivalent
  (new flags default to off / off; new fields default to
  permissive None / empty / defaults).
- v0.8.0 callers that don't import the new Holm / per-batch
  Arrhenius / unit / report_order features are unaffected;
  all new fields are additive with permissive defaults.

## [0.8.0] — 2026-06-13 — Backend Features (no UI)

### Theme
More backend features, no UI. Per the user's "features first,
website last" reshape: the Cloudflare Pages + Claude Design
UI pass is deferred to v0.9.0+ / v1.0. Python remains the
authoritative stats engine. This release ships Arrhenius-driven
shelf-life prediction (a genuine new analysis path), a
leave-one-batch-out sensitivity variant, and a cross-platform
Makefile.

### Added
- **Arrhenius-driven shelf-life prediction** (`--arrhenius-shelf-life`).
  New `openpharmastability.stats.arrhenius_shelf_life.predict_arrhenius_shelf_life`
  fits the v0.5.0 Arrhenius module on multi-temperature rate
  data and predicts the long-term rate at the storage
  temperature, then runs the standard crossing logic against the
  spec to produce a model-based statistical crossing and
  supported shelf life. New `StabilityResult.arrhenius_shelf_life:
  Optional[ArrheniusShelfLife]` field (additive, default None).
  New `ArrheniusShelfLife` dataclass. New CLI flag
  `--arrhenius-shelf-life` (and `--arrhenius-shelf-life-storage-temp FLOAT`,
  default 25.0 °C, the same default as the v0.5.0 Arrhenius
  module). The Arrhenius-shelf-life is "exploratory": the report
  says so, and the official shelf-life decision is unchanged.
- **Leave-one-batch-out sensitivity** (`--sensitivity-mode {row,batch}`,
  default `row`). The v0.7.0 sensitivity analysis removed
  individual Cook's-distance outliers; v0.8.0 adds a batch-level
  variant that answers "is any single batch driving the shelf-life
  number?" — a common Q1E concern. The same `compute_sensitivity`
  helper now accepts `mode: str = "row" | "batch"`. New
  `SensitivityRow.mode` and `SensitivityRow.drop_key` fields;
  `SensitivityReport.mode` field; all additive. New tests cover
  the batch-level path on the v0.5.x multi-batch fixtures.
- **Cross-platform Makefile.** New `Makefile` at the repo root
  with three targets:
  - `make fresh` — delete `__pycache__` / `.pyc` / `.pytest_cache`
    outside `.venv`, recompile source, reinstall, run tests.
  - `make test` — `pytest -q` (the canonical suite run).
  - `make regen-check` — `python tools/regen_expected.py --check`.
  Documented in the README dev section. Works on Linux / macOS /
  WSL / git-bash on Windows. The PowerShell script in
  `NEXT_STEPS.md` §7.1 still works for native PowerShell on
  Windows; the Makefile is the cross-platform complement.

### Tests
- `validation/test_arrhenius_shelf_life.py` (new, ~6 tests):
  the new module recovers a known `Ea` on synthetic data, handles
  the <2-temperatures skip, and produces a defensible
  predicted shelf life on a 3-temperature dataset.
- `validation/test_sensitivity.py` extended: 2-batch and
  3-batch leave-one-batch-out tests on the v0.5.x
  significant-change fixtures; max-delta summary
  correctness; `mode` field is recorded on the result and the
  per-row `drop_key` matches the batch name.
- `validation/test_engine_v050.py` extended: regression for
  the v0.8.0 engine wiring (new flag `run_arrhenius_shelf_life`
  + the new `sensitivity_mode` kwarg).
- Total: ~445 tests passing (was 421 at v0.7.0; +24 new across
  Arrhenius shelf-life, batch sensitivity, engine regression,
  and the Makefile's "no leftover stale state" guard).

### Backward compatibility
- All v0.7.0 single-attribute and multi-attribute golden paths
  still pass. The default analyze path is byte-equivalent
  (`--arrhenius-shelf-life` and `--sensitivity-mode` default to
  off / `row`, matching v0.7.0 behavior).
- v0.7.0 callers that don't import the new
  `stats.arrhenius_shelf_life` module or the new
  `ArrheniusShelfLife` dataclass are unaffected; all new fields
  are additive with permissive defaults.
- The `Makefile` is purely additive. Repos that prefer the
  PowerShell script in `NEXT_STEPS.md` §7.1 can ignore it.

## [0.7.0] — 2026-06-13 — Backend Features (no UI)

### Theme
Backend features only. **No UI, no Streamlit, no Cloudflare Pages**
— the UI pass remains deferred to v0.8.0+ (per the user's
"features first, website last" reshape). Python remains the
authoritative stats engine. This release closes four long-open
items and ships two genuinely new analytical capabilities.

### Added
- **Sensitivity analysis** (`--sensitivity`). New
  `openpharmastability.stats.sensitivity.compute_sensitivity` re-runs
  the analysis end-to-end with each Cook's-distance influential
  point removed and reports the resulting supported shelf life,
  the absolute change vs the baseline, and a human-readable
  summary ("max delta 2 mo; shelf life robust" vs "max delta 5
  mo; a single point drives the shelf-life decision"). Wired
  through the engine (auto-attached to the result when
  `--sensitivity` is set) and the JSON record / HTML report.
  New `StabilityResult.sensitivity_report: Optional[SensitivityReport]`
  field (additive, default None).
- **Acceptance-criteria CSV export** (`--acceptance-csv PATH`).
  New `to_acceptance_criteria` helper emits a flat CSV — one row
  per analyzed attribute — with the key decision fields
  (attribute, condition, direction, model, poolability, lower_spec,
  upper_spec, statistical crossing, supported shelf life, observed
  data, extrapolation flag, limiting-decision inclusion +
  exclusion reason, unit, governing batch). Designed for LIMS /
  regulatory-tracking ingestion. New
  `AcceptanceCriteriaRow` dataclass.
- **`StabilityResult.lower_spec` / `upper_spec` fields** (additive,
  default None). Records the spec limits the engine used —
  data-derived or metadata-overridden. Lets callers read the
  decision-driving limits without reaching into `ValidatedData`.
  Backed by the v0.7.0 metadata-override wire (see Fixed below).
- **`compute_sensitivity` in `openpharmastability.api`**. New
  high-level API helper that takes a `StabilityResult` +
  `ValidatedData` and returns a `SensitivityReport` (the same
  function the engine calls internally).

### Fixed
- **Multi-attribute metadata `lower_spec` / `upper_spec` override is
  now applied to the per-attribute decision.** The v0.2.1
  CHANGELOG claimed "metadata override is now applied to per-
  attribute analysis"; v0.7.0 makes that true. The override now
  replaces the data-derived spec for the crossing solver, the
  supported shelf life, the JSON record, and the HTML report. The
  v0.7.0 release closes a known discrepancy between the
  CHANGELOG and the code.
- **`tools/regen_expected.py` is now pure-numpy (no statsmodels).**
  The v0.1.1 known-open item ("regen uses statsmodels for
  COMMON_SLOPE — reduces independence") is finally closed. The
  COMMON_SLOPE fit is built from a hand-built treatment-coded
  design matrix and solved with `numpy.linalg.lstsq`; the bound is
  computed via `c @ cov @ c` directly. The independent validator
  no longer shares an OLS backend with the engine.
- **`engine.analyze()` now supports XLSX input directly.** The
  single-attribute path used to require CSV; XLSX had to be
  reloaded by the CLI for the plot. v0.7.0 adds a `load_table`
  dispatcher in `data/io.py` that handles `.csv`, `.xlsx`, and
  `.xlsm` by extension; the engine calls `load_table` instead of
  `load_csv`. The single-attribute CLI path now matches the multi-
  attribute path: any format the data layer supports is accepted.

### Tests
- `validation/test_regen.py` extended (new test): asserts the
  regen script does not import statsmodels. The existing
  `test_script_does_not_import_project_stats` tuple is extended
  to forbid `"statsmodels"` as well.
- `validation/test_data_io.py` extended: `load_table` CSV / XLSX
  dispatch, unsupported-extension error, XLSX sheet-selection
  round-trip.
- `validation/test_engine.py` extended: `analyze()` accepts an
  XLSX mirror of the golden fixture and produces the same numeric
  result.
- `validation/test_multi_engine.py` extended: metadata
  `lower_spec` / `upper_spec` override changes the per-attribute
  result; `result.lower_spec` / `result.upper_spec` record the
  override values; existing multi-attribute fixture (no override)
  still has `impurity_a` as the limiting attribute.
- `validation/test_sensitivity.py` (new, ~6 tests): golden fixture
  has 4 influential points; `compute_sensitivity` returns 4 rows;
  the per-row `leave_one_out_supported_shelf_life` differs from
  the baseline; the `summary` string is short and non-empty.
- `validation/test_cli.py` extended: `--sensitivity` flag is
  accepted; `--acceptance-csv PATH` writes a CSV with one row per
  eligible attribute; both flags compose with the existing
  single + multi paths.
- `validation/test_reporting.py` and
  `validation/test_multi_reporting.py` extended: the new fields
  are surfaced in the JSON record and the HTML report.
- Total: ~420 tests passing (was 390 at v0.6.0; +30 new across
  regen purity, XLSX dispatch, sensitivity, metadata override,
  acceptance CSV, and reporting).

### Backward compatibility
- All v0.6.0 single-attribute and multi-attribute golden paths
  still pass. The default analyze path is byte-equivalent
  (`engine.analyze` now calls `load_table` which is a thin
  wrapper around `load_csv` for `.csv` paths; the numeric result
  is identical).
- v0.6.0 callers that don't import the new `stats.sensitivity`
  module or the new API helper are unaffected; all new fields
  and helpers are additive with permissive defaults.
- `--sensitivity` and `--acceptance-csv` are opt-in; default
  behavior unchanged.
- The `StabilityResult.lower_spec` / `upper_spec` fields are
  `None` by default for callers that build `StabilityResult`
  by hand. v0.7.0 callers that use the engine get the
  data-derived specs recorded automatically.

## [0.6.0] — 2026-06-13 — Export + API Foundation

### Theme
Backend and tooling release. **No frontend, no Streamlit, no
Cloudflare Pages** — the UI pass is deferred to a later release
(v0.7.0+ or v1.0) once the feature surface stabilises. Python
remains the authoritative stats engine; Cloudflare Pages is a
future deployment target, not a v0.6 dependency.

### Added
- **PDF export.** New `openpharmastability.reports.pdf.render_pdf`
  converts an existing HTML report to PDF. Backend priority is
  `weasyprint` (preferred) with `pdfkit` (wkhtmltopdf) as the
  fallback. The function raises `RuntimeError` with install
  instructions when neither backend is importable. Optional
  install groups: `pip install openpharmastability[pdf]` (weasyprint)
  and `openpharmastability[pdf-fallback]` (pdfkit + wkhtmltopdf).
  New `--pdf PATH` CLI flag renders a PDF copy alongside the HTML.
- **Report artifacts.** New
  `openpharmastability.reports.artifacts.make_report_artifact` builds
  a self-contained, portable bundle in a target directory: the HTML
  report with the confidence-plot PNG inlined as a base64 data URL
  (no relative-path dependency on the plot file), the JSON decision
  record, the per-attribute plot PNGs (single: one; multi: one per
  attribute), and an optional PDF when a PDF backend is available.
  Returns a `contracts.ReportArtifact` with absolute paths, SHA-256
  digests, byte sizes, and the inlined-plot flag. The artifact is
  the recommended format for archival / hand-off / audit trails.
- **Python API.** New `openpharmastability.api` module exposes a
  thin programmatic surface around the engine:
  - `analyze_csv(path, condition, **kwargs) -> StabilityResult`
  - `analyze_xlsx(path, condition, **kwargs) -> StabilityResult`
  - `analyze_multi(path, condition, **kwargs) -> MultiAttributeResult`
  - `analyze_path(path, condition, **kwargs) -> StabilityResult | MultiAttributeResult`
    (auto-detects CSV vs XLSX)
  - `make_artifact(result, data, out_dir, **kwargs) -> ReportArtifact`
  - `analyze_and_artifact(path, condition, out_dir, **kwargs) -> tuple[StabilityResult | MultiAttributeResult, ReportArtifact]`
  These are pure-Python entry points; no HTTP server, no
  subprocess. The CLI wraps these. Re-exported from the top-level
  `openpharmastability` package.
- **New CLI flags.**
  - `--pdf PATH` — write a PDF copy to PATH.
  - `--no-html` — skip the HTML report (JSON + plot only).
  - `--json-only` — emit only the JSON decision record (no HTML,
    no plot).
  - `--artifact-dir DIR` — write a self-contained report bundle
    (HTML with inlined plot, JSON, plots, optional PDF) into DIR.
  - `--quiet` / `-q` — suppress the per-attribute summary on
    stdout; only print the artifact path / final shelf-life line.
  - Improved error messages: missing input file, missing required
    column, unparseable condition, XLSX missing sheet — each prints
    a one-line, actionable message and exits with a non-zero code.
- **New contract.** `contracts.ReportArtifact` dataclass with
  absolute paths, SHA-256 digests, byte sizes, `plot_inlined` flag,
  and optional `pdf_path`.

### Fixed
- **Multi-attribute HTML spec display.** `reports/multi_html.py`
  used to print `lower=None, upper=None` for the per-attribute spec
  limits because it read from `r.fit.design` (which never carried
  those keys). v0.6.0 reads from `ar.metadata` (the
  `AttributeMetadata` does carry `lower_spec` / `upper_spec`) so
  the rendered report shows the real values.

### Tests
- `validation/test_pdf.py` (new) — backend detection, fallback
  ordering, RuntimeError when neither backend, PDF magic bytes
  (`%PDF`) when a backend is available; tests skip cleanly with a
  documented reason when neither weasyprint nor pdfkit is
  importable (Windows / clean venvs).
- `validation/test_api.py` (new) — `analyze_csv` /
  `analyze_xlsx` / `analyze_path` / `analyze_multi` /
  `make_artifact` / `analyze_and_artifact` round-trips; the
  artifact bundle is byte-portable (inlined plot, sha256,
  sizes).
- `validation/test_artifacts.py` (new) — artifact helpers:
  HTML-with-inlined-plot is portable, SHA-256 matches the file,
  PDF path is None when no backend, multi-artifact bundles one
  plot per attribute.
- `validation/test_cli.py` extended — `--pdf`, `--no-html`,
  `--json-only`, `--artifact-dir`, improved error messages,
  non-zero exit codes for missing files.
- `validation/test_multi_reporting.py` extended — spec display
  fix regression test (the per-attribute lower/upper spec line is
  non-None on the multi-attribute fixture).
- Total: ~390 tests passing (was 365 at v0.5.1).

### Backward compatibility
- All v0.5.1 single-attribute and multi-attribute golden paths
  still pass. The default CLI invocation still produces
  "supported shelf life: 17 months" on the golden fixture.
- v0.5.1 callers that don't import the new `api` module or
  `ReportArtifact` are unaffected; both are additive.
- `--pdf` and `--artifact-dir` are opt-in; default behavior
  unchanged.

## [0.5.1] — 2026-06-13 — v0.5.0 audit patch

### Fixed
- **Arrhenius engine hook now filters to the selected attribute and
  respects the declared direction.** The v0.5.0 `_compute_arrhenius`
  helper read the raw DataFrame and assumed decreasing degradation
  (`rate = -slope`). On a mixed-attribute file the rates were
  contaminated by other attributes' rows, and for increasing
  degradants (`Direction.INCREASING`) the rate sign was wrong. The
  v0.5.1 helper accepts the `ValidatedData` (attribute + direction)
  and computes `rate = sign(direction) * (-slope)` per temperature
  on the per-attribute, per-direction-filtered rows. The
  exploration-only caveat in the report is unchanged; the fix
  prevents the silent contamination.
- **Mixed-model convergence / boundary status is now surfaced in
  warnings, the JSON record, and the HTML report.** The v0.5.0
  `random_effects` path stored a `convergence` sub-block inside
  `fit.design` only; v0.5.1 promotes it to a top-level
  `StabilityResult.model_convergence` field, emits a warning when
  the mixed model hits a boundary (random-effect variance → 0) or
  fails to converge, and renders a small status line in the
  single-attribute HTML report. The OLS path is byte-equivalent and
  always reports `converged=True, boundary=False`.

### Added
- **Explicit warning when `--mkt` is requested without a `temp_c`
  column.** Previously the engine silently set `mkt_celsius = None`
  with no surface signal. v0.5.1 appends
  `"MKT requested but no temp_c column in the input; mkt_celsius is None."`
  to the warnings list so the report is honest about why MKT is
  missing.
- **New `StabilityResult.model_convergence: dict` field** (additive,
  default `{"converged": True, "boundary": False, "message": ""}`).

### Documentation
- `README.md`, `HANDOVER.md`, and `NEXT_STEPS.md` updated to
  reflect the v0.5.0 + v0.5.1 state, the new test count
  (341 → ~350), and the v0.6.0 direction (PDF export + Cloudflare
  Pages UI; Python remains the authoritative stats engine).

### Tests
- v0.5 integration tests now **hard-require** the v0.5 modules
  (Arrhenius, MKT, reduced-design, regulatory) instead of the
  prior skip-if-missing fallback. A new `validation/conftest.py`
  fails collection if any of the v0.5 modules is missing.
- New tests: Arrhenius direction handling (decreasing vs
  increasing vs bidirectional), Arrhenius attribute filtering on
  a mixed-attribute frame, MKT-without-temp_c warning,
  mixed-model boundary / convergence surfacing, and the
  convergence fields on the JSON record and HTML report.
- Total: ~350 tests passing (was 341 at v0.5.0).

### Backward compatibility
- The v0.5.0 single-attribute golden still passes: assay_3batch.csv
  → `common_slope_batch_intercepts`, supported shelf life 17 months,
  `model_effects = "fixed"`, `model_convergence = {"converged": True,
  "boundary": False, "message": ""}`.
- The v0.4.0 / v0.5.0 multi-attribute fixture and CLI invocation
  still work; the new field is additive and defaults are permissive.
- v0.5.0 callers that ignore `model_convergence` are unaffected.

## [0.5.0] — 2026-06-13 — Advanced Statistics

### Added
- **Arrhenius module.** New `openpharmastability.stats.arrhenius`
  fits `ln(k) = ln(A) − Ea / (R · T)` to stress-temperature rate data.
  Requires >= 2 stress temperatures (>= 3 preferred); 1 temperature
  raises `NotImplementedError`; 2 temperatures emits a
  `UserWarning` ("no goodness-of-fit available") and proceeds.
  Synthetic 4-temperature recovery is exact (`rtol < 1e-6`).
- **Mean Kinetic Temperature (MKT).** New
  `openpharmastability.stats.mkt.mean_kinetic_temperature` implements
  the Haynes equation with the USP <1160> default
  `Ea = 83.144 kJ/mol` (configurable). Constant-temperature input
  returns the same temperature; a synthetic excursion profile lifts
  MKT above the mean.
- **Reduced-designs detection (ICH Q1D).** New
  `openpharmastability.regulatory.reduced_design.detect_reduced_design`
  detects bracketing (only extreme levels of a factor tested) and
  matrixing (sparse `batch × time` coverage). Returns a
  `ReducedDesignReport` with `is_bracketed`, `is_matrixed`,
  `missing_cells`, and a human-readable `note`.
- **Random-effects opt-in.** New `--random-effects` CLI flag and
  `random_effects: bool = False` parameter on `analyze()`. When set,
  the regression layer routes the fit through
  `statsmodels.formula.api.mixedlm` (batch as a random effect) and
  records `model_effects = "random"` on the result. A loud warning
  reminds the caller that the ICH Q1E default is fixed-effect and
  the resulting confidence bounds differ. The default is unchanged
  (`model_effects = "fixed"`).
- **New `StabilityResult` fields (additive, default-safe).**
  `arrhenius_result: Optional[ArrheniusResult] = None`,
  `mkt_celsius: Optional[float] = None`,
  `reduced_design_report: Optional[ReducedDesignReport] = None`,
  `model_effects: str = "fixed"`.
- **New CLI flags.**
  `--arrhenius` (fit Arrhenius from multi-temperature rate data),
  `--arrhenius-storage-temp 25.0` (default 25 °C),
  `--mkt` (compute MKT from input temperatures),
  `--mkt-ea-kj-mol 83.144` (USP <1160> default),
  `--detect-reduced-design` (run bracketing/matrixing detection),
  `--random-effects` (opt-in mixed model; not the Q1E default).
- **New contracts.** `ArrheniusResult` and `ReducedDesignReport`
  dataclasses in `openpharmastability.contracts`.
- **New modules.** `openpharmastability.stats.arrhenius`,
  `openpharmastability.stats.mkt`,
  `openpharmastability.regulatory.reduced_design`.
- **Reports surface the new fields.** The single-attribute JSON
  decision record emits `arrhenius`, `mkt_celsius`,
  `reduced_design`, `model_effects`. The HTML report renders new
  sections (Arrhenius, MKT, Reduced design, Model effects) that
  are present only when the corresponding feature was exercised.
  The multi-attribute record carries per-attribute Arrhenius / MKT
  / reduced-design / model-effects keys, and the multi HTML report
  surfaces the same fields per attribute.

### Math
The v0.4.0 shelf-life math is unchanged (linear, raw-scale, fixed-effect
batch, alpha = 0.25, one-sided 95% t-quantile, floor rounding, worst-case
earliest crossing, Q1A significant-change gating). v0.5.0 layers four
**opt-in, exploratory** analyses on top:
- Arrhenius: `ln(k) = ln(A) − Ea / (R · T)` with `R = 8.314 J·mol⁻¹·K⁻¹`,
  temperatures converted to Kelvin via `+273.15`. OLS on `1/T`; closed
  form via `numpy.linalg.lstsq`.
- MKT: `MKT_K = (Ea / R) / (−ln(mean(exp(−Ea / (R · Ti)))))`,
  temperatures in Kelvin.
- Reduced designs: empirical detection (no distribution assumptions).
- Random effects: opt-in `statsmodels.formula.api.mixedlm`; the existing
  Q1E default is `model_effects = "fixed"` and is unchanged.

### Backward compatibility
- v0.4.0 single-attribute golden still passes: assay_3batch.csv →
  common_slope_batch_intercepts, supported shelf life 17 months,
  no accelerated rows, no new flags, `model_effects = "fixed"`.
- v0.4.0 multi-attribute fixture still has impurity_a as limiting
  at 7 months.
- v0.4.0 CLI invocation (`--attribute assay`, no other flags) still
  works. New flags are opt-in. `model_effects` is always recorded;
  it defaults to `"fixed"`.
- `--random-effects` is opt-in: the ICH Q1E default remains
  fixed-effect. Calling it changes the confidence bounds (and the
  shelf-life number) and emits a warning; users opt in deliberately.

## [0.4.0] — 2026-06-13 — ICH Q1A Significant-Change Gating

### Added
- **Significant-change checklist (ICH Q1A(R2) §2.2.7).** New module
  `openpharmastability.regulatory.significant_change` evaluates the
  five default criteria (assay 5% change, degradant OOS, physical
  failure, pH, dissolution) on a per-condition DataFrame and returns
  a `contracts.SignificantChange` with `occurred`, `first_change_month`,
  `reasons`, and per-criterion `details`. Missing optional columns
  skip the corresponding criterion instead of crashing.
- **Q1E extrapolation allowance.** New `extrapolation_allowance(acc,
  inter, observed)` implements the ICH Q1E decision table: no
  accelerated change → extrapolation permitted within Q1E caps; change
  < 3 mo → no extrapolation; 3–6 mo change → extrapolation only if the
  intermediate condition shows no change (and data is present);
  intermediate change → no extrapolation; accelerated change > 6 mo
  → extrapolation permitted. New `q1e_cap(observed)` returns
  `min(2 * observed, observed + 12)` per the Q1E rule of thumb.
- **New `StabilityResult` fields (additive, default-safe).**
  `significant_change_accelerated`,
  `significant_change_intermediate`, `extrapolation_allowed`,
  `extrapolation_rationale`, `significant_change_details`. All default
  to permissive/empty so v0.3.x callers and hand-built fixtures keep
  working unchanged.
- **`analyze()` accepts the new gate.** New parameters:
  `accelerated_condition: str | None = "40C/75RH"`,
  `intermediate_condition: str | None = "30C/65RH"`,
  `assay_change_threshold: float = 5.0`,
  `no_significant_change_gate: bool = False`. When the gate is
  exercised, the engine subsets accelerated and intermediate rows
  from the input (via `parse_condition`) and threads the
  `SignificantChange` outcomes into the extrapolation decision. When
  `no_significant_change_gate` is True, the gate is skipped and the
  v0.3.x cap-only behavior is restored.
- **New CLI flags.**
  `--accelerated-condition "40C/75RH"`,
  `--intermediate-condition "30C/65RH"`,
  `--assay-change-threshold 5.0`,
  `--no-significant-change-gate`.
- **Reports surface the gate.** The JSON decision record (single
  and multi) carries `significant_change_accelerated`,
  `significant_change_intermediate`, `extrapolation_allowed`,
  `extrapolation_rationale`, and the full
  `significant_change_details` block. The HTML report (single and
  multi) renders a new "Significant-change assessment" section that
  reproduces the Q1E decision-table branch and the rationale.
- **New contract.** `contracts.SignificantChange` dataclass.
- **New package.** `openpharmastability.regulatory`.

### Tests
- New `validation/test_significant_change.py` (10+ tests): per-criterion
  firing (assay 5%, degradant OOS, physical, pH, dissolution),
  first-change-month, details payload, missing-column skip, and the
  full Q1E decision table (all six branches) parameterised on
  hand-built `SignificantChange` fixtures.
- New `validation/test_engine_v040.py` (4 tests): the engine
  populates the new `StabilityResult` fields on the golden dataset;
  `--no-significant-change-gate` restores the v0.3 cap; the
  accelerated-change < 3 mo branch caps `supported_shelf_life` at
  `observed_data_months`; the intermediate-required-but-absent
  branch emits the documented warning.
- `validation/test_cli.py` extended (2 tests): `--accelerated-condition`
  and `--no-significant-change-gate` are accepted; missing value
  fails with a clear error.
- `validation/test_reporting.py` extended (2 tests): verbatim
  rationale string appears in both JSON and HTML; `extrapolation_allowed`
  is `false` for the < 3 mo fixture.
- Total: 280+ tests passing (was 261 at v0.3.1).

### Math
The v0.3.x shelf-life math is unchanged (linear, raw-scale, fixed-effect
batch, alpha = 0.25, one-sided 95% t-quantile, floor rounding, worst-case
earliest crossing for multi-batch). v0.4.0 layers a Q1E-style
**decision tree on top of the extrapolation cap**: when accelerated
data show significant change within 3 months, the supported shelf life
is hard-capped at the observed long-term data length; when change
appears at 3–6 months, intermediate data is required; etc. The
cap math itself (`min(2x, +12 mo)`) is unchanged.

### Backward compatibility
- v0.3.1 single-attribute golden still passes: assay_3batch.csv →
  common_slope_batch_intercepts, supported shelf life 17 months,
  no accelerated rows in the dataset → gate silently passes, fields
  default to permissive values.
- v0.3.1 multi-attribute fixture still has impurity_a as limiting at
  7 months.
- v0.3.1 CLI invocation (`--attribute assay`, no other flags) still
  works. New flags are opt-in. Default `--accelerated-condition` is
  `40C/75RH`; if the dataset has no rows for that condition, the
  gate is silently treated as "no accelerated data" and extrapolation
  is allowed within the existing cap (this is the safe default for
  golden fixtures that contain only long-term data).
- `--no-significant-change-gate` restores v0.3.1 cap-only behavior
  byte-for-byte.

## [0.3.1] — 2026-06-13 — v0.3.1 hotfix

### Fixed
- `test_cli_version` now resolves the CLI via the same `python -m
  openpharmastability.cli --version` fallback the rest of the suite
  uses; the console-script PATH dependency is no longer required.
- CLI `--bql-policy` choice now correctly accepts `substitute_loq_half`
  (was `substitute_half_loq` in help text, causing the documented
  option to be rejected by the engine).
- `StabilityResult.bql_summary` is now a proper dataclass field
  (was hacked on via `object.__setattr__`).
- `apply_extrapolation_caps` was refactored to `dataclasses.replace`
  so any new `StabilityResult` field is automatically carried
  through (was a manual field-copy block that would have dropped
  future fields).
- Single-attribute JSON decision record now includes the verbatim
  `disclaimer` (was only in the multi-attribute record).
- `audit_data_quality` is now wired into `engine.analyze()` as a
  non-blocking pass; findings surface in the JSON record under
  `metadata.data_quality` and in the `warnings` list.
- `plots/confidence_plot.py` now draws a single worst-case band for
  multi-batch models (was drawing the same worst-case band once per
  batch with different colors), and respects `Direction.INCREASING`
  (was hard-coded to the lower bound).
- `data/quality.py` normalizes the condition column before the
  wrong-condition check (was comparing raw strings, causing
  `25°C/60%RH` vs `25C/60RH` to be falsely flagged).
- `data/metadata.py` now accepts `transform="log"` (was forcing it
  back to `"none"` with a warning; v0.3.0 transform evidence supports
  log).

### Tests
- New tests in `test_data_quality.py`, `test_data_metadata.py`,
  `test_plot.py`.
- Total: 261 tests passing (was 254 at v0.3.0).

## [0.3.0] — 2026-06-13 — Data Quality + BQL + Transform Evidence

### Added
- **Data quality layer.** New `data/quality.py::audit_data_quality` runs
  16 non-mutating checks on the raw input frame and returns a
  `DataQualityReport` with severity-tagged issues
  (INFO / WARNING / ERROR) and a `can_analyze` flag. JSON-serializable.
  New contracts: `IssueSeverity` enum, `DataQualityIssue`,
  `DataQualityReport`. v0.3.0 reports issues; it does NOT block analysis.
- **Real BQL policies.** All five policies are now real (no longer
  seams): `exclude`, `flag`, `substitute_loq`, `substitute_half_loq`,
  `manual_review`. The function `apply_bql_policy` now returns
  `tuple[pd.DataFrame, BQLSummary]`. Substitution preserves the
  pre-substitution value in a new `original_value` column. Missing
  LOQ for substitution raises `ValueError` (never silently zeros).
  New contract: `BQLSummary`. `ValidatedData.bql_summary` records the
  applied policy and counts.
- **Transform candidate evidence.** New `stats/transforms.py::assess_transforms`
  fits `none` / `log` / `sqrt` candidates independently and records
  AICc, residual SE, normality p-value, and homoscedasticity
  p-value. The official v0.3.0 decision model is unchanged
  (raw-scale linear). `recommendation_is_official` is always False;
  the report must say this is exploratory evidence. New contracts:
  `TransformCandidate`, `TransformAssessment`.
- **CLI flags.**
  - `--bql-policy` now accepts `manual_review` (in addition to
    `exclude` / `flag` / `substitute_loq` / `substitute_half_loq`).
  - `--assess-transforms` (default off): compute transform-candidate
    evidence for the report. Does not change the official model.
- **JSON record exposes new fields** (`reports/record.py`): per-attribute
  `bql_summary` and (when enabled) `transform_assessment`.
- **New fixtures:** `examples/bql_attribute.csv` (30 rows, 1 BQL row
  with loq=88.0), `examples/data_quality_messy.csv` (16 rows;
  1 ERROR no-spec + 2 WARNINGS + 1 INFO).

### Tests
- `validation/test_data_quality.py` (18 new) — full coverage of the
  16 audit checks plus JSON-serializability.
- `validation/test_data_bql.py` (12 new) — all five policies,
  missing-LOQ raises, original_value preservation, no-BQL-column
  no-op, unknown policy.
- `validation/test_transforms.py` (11 new) — log/sqrt invalid for
  zero/negative, AICc recommendation, JSON-serializable.
- Existing `test_cli_bql.py` extended: substitute_loq / substitute_loq_half
  no longer raise `NotImplementedError`; they now raise `ValueError`
  when the loq column is missing (the v0.3.0 contract). The warning
  text changed from `bql_excluded: N row(s) ...` to
  `bql_policy='...': N excluded, M substituted, ...`.
- Total: 254 tests passing (was 238 at v0.2.1).

### Math
The v0.3.0 official shelf-life model is unchanged: linear, raw-scale,
fixed-effect batch, alpha = 0.25, one-sided 95% t-quantile
(`student_t.ppf(0.95, df)`, NOT 0.975), floor rounding, worst-case
earliest crossing for multi-batch. The transform candidates are
**evidence only** and do not alter the official decision. The
`recommendation_is_official` field is always False.

### Backward compatibility
- v0.2.1 single-attribute golden still passes: assay_3batch.csv →
  common_slope_batch_intercepts, supported shelf life 17 months.
- v0.2.1 multi-attribute fixture still has impurity_a as limiting
  at 7 months.
- v0.2.1 CLI invocation (`--attribute assay`, no other flags) still
  works. New flags are opt-in.
- The warning-text change in `validate_and_select` (BQL policy
  wording) is the only user-visible behavior change. Tests that
  asserted the old `bql_excluded:` text have been updated to assert
  the new `bql_policy='...':` text.

## [0.2.1] — 2026-06-13 — v0.2.1 hotfix

### Fixed
- **Metadata override is now applied to per-attribute analysis.**
  `AttributeMetadata.direction`, `lower_spec`, `upper_spec` are
  recorded on the per-attribute `StabilityResult` (via
  `dataclasses.replace`) so the metadata actually controls the
  per-attribute decision instead of being only a wrapper field.
- **XLSX metadata sheet detection.** When the input is an XLSX
  workbook and `--metadata-sheet` is supplied (without
  `--metadata-csv`), the metadata is now loaded from the same
  workbook. A separate XLSX metadata file with `--metadata-sheet`
  also works.
- **Multi HTML plot paths are now correct.** The HTML
  `<img src=...>` references are computed as relative paths
  from the report's directory to the `plots/` subdirectory.
  Works whether `plots_dir` is the same as the HTML directory
  or a subdirectory.
- **XLSX file handle leak on Windows.** `data/xlsx.py::load_xlsx`
  now wraps `pd.ExcelFile` in a context manager so the file
  handle is released on read completion.
- **`--bql-policy` is now wired.** The flag is passed to
  `apply_bql_policy` via `validate_and_select` so "exclude",
  "flag", "substitute_loq", and "substitute_loq_half" actually
  do something (the first two are the v0.1 paths; the latter
  two still raise `NotImplementedError` per the spec seam).
- **Multi metadata merge order.** `analyze_many` now MERGES
  file/library metadata INTO the dict that `select_limiting`
  already wrote, instead of overwriting it. The
  `tie_break` field (set by `select_limiting`) and the
  per-attribute metadata warnings are preserved.

### Tests
- 7 new tests in `validation/test_multi_engine.py` (metadata
  override, XLSX metadata-sheet detection, metadata-sheet
  missing-error, file-handle closure, select_limiting metadata
  preservation, two more for completeness).
- 2 new tests in `validation/test_data_xlsx.py` (file handle
  closure, sheet helper with candidates).
- 3 new tests in `validation/test_multi_reporting.py` (HTML
  plot paths — subdir, missing file, flat dir).
- New `validation/test_cli_bql.py` (3 tests) covering the
  wired bql-policy path.
- Total: 234 tests passing (was 219 at v0.2.0).

### Backward compatibility
- v0.2.0 single-attribute golden still passes.
- v0.2.0 multi-attribute fixture still has `impurity_a` as the
  limiting attribute at 7 months, UNLESS the user supplies
  metadata that intentionally changes the analysis.

## [0.2.0] — 2026-06-13 — multi-attribute + XLSX

### Added
- **Multi-attribute analysis.** A single CSV/XLSX with multiple
  attributes (e.g. assay + impurity_a) can now be analyzed in one
  run via `--all-attributes` or `--attributes a1,a2,a3`. The
  engine reports per-attribute sections and an overall limiting
  decision (smallest supported shelf life among PRIMARY
  attributes; ties broken by earlier statistical crossing).
- **XLSX input.** New `data/xlsx.py::load_xlsx` reads `.xlsx`
  workbooks. `--data-sheet` overrides the default sheet picker
  (which tries `results`, `data`, `stability` then the first
  sheet). Requires `openpyxl>=3.1` (added to `pyproject.toml`).
- **Attribute metadata table.** A separate CSV (`--metadata-csv`)
  or XLSX sheet (`--metadata-sheet`) describing per-attribute
  spec limits, direction, unit, role, spec_type, transform, and
  report order. Loaded by `data/metadata.py`. Optional; v0.1
  behavior is preserved when omitted.
- **New CLI flags.** `--attributes`, `--all-attributes`,
  `--metadata-csv`, `--metadata-sheet`, `--data-sheet`,
  `--plots-dir`, `--bql-policy`. The v0.1 `--attribute` and all
  default behaviors are preserved.
- **Multi-attribute JSON decision record** at `<output>.json` and
  multi-attribute HTML report at `--output` (with one plot per
  attribute saved to `--plots-dir`).

### New contracts (`openpharmastability/contracts.py`)
- `AttributeRole` enum: PRIMARY / SUPPORTIVE / INFORMATIONAL /
  EXCLUDED.
- `AttributeMetadata` dataclass: per-attribute override fields.
- `AttributeResult` dataclass: wraps a `StabilityResult` with
  multi-attribute context (`included_in_limiting_decision`,
  `exclusion_reason`).
- `MultiAttributeResult` dataclass: top-level multi-attr result
  (limiting attribute, supported shelf life, observed data
  length, warnings, metadata).
- `select_limiting` and `analyze_many` exported from
  `openpharmastability.shelf_life`.

### New fixtures
- `examples/multi_attribute.csv` — 48 rows, 3 batches × 4 time
  points × 2 attributes × 2 replicates, deterministic seed
  `20260613`. Decreasing assay and increasing impurity_a.
- `examples/multi_attribute_metadata.csv` — 2-row metadata
  (assay %LC, impurity_a %area).

### New tests
- `validation/test_data_xlsx.py` (5) — XLSX loader, default
  sheet picker, missing-sheet error, column whitespace stripping.
- `validation/test_data_metadata.py` (7) — metadata loader,
  missing-attribute-column error, coercion behavior, optional
  fields, default role.
- `validation/test_limiting.py` (6) — limiting selection rules,
  PRIMARY-only eligibility, tie-break by statistical crossing,
  exclusion reasons.
- `validation/test_multi_engine.py` (7) — `analyze_many`
  end-to-end on the multi-attribute fixture (single attr,
  multi attr, default, metadata path, no-data attr, file SHA).

### Math
The v0.2.0 multi-attribute path reuses the v0.1 single-attribute
math unchanged. Per-attribute fits, poolability tests, bounds,
crossings, and diagnostics are computed by the existing
single-attribute `analyze()` for each attribute independently;
the only new logic is the limiting decision (min supported
shelf life among PRIMARY attributes, ties broken by earlier
statistical crossing). No math invariants change.

### Backward compatibility
The v0.1 single-attribute golden test still passes. The v0.1
CLI invocation (`--attribute assay`, no other flags) still
produces the same numbers and the same HTML report shape.
`--source-epoch` and `SOURCE_DATE_EPOCH` (v0.1.1) are honored
by the multi-attribute path too.

## [0.1.1] — 2026-06-13 — v0.1.1 stabilization patch

### Fixed
- **Reproducible timestamps via `--source-epoch` / `SOURCE_DATE_EPOCH`.**
  The HTML and JSON metadata now record a deterministic timestamp
  when an explicit epoch is provided. Two CLI runs with the same
  `--source-epoch` produce byte-identical JSON. (Without the flag,
  behavior is unchanged: wall-clock timestamp.)
- **Direction-vs-spec false-positive warning.** Declaring
  `direction="decreasing"` (or `"increasing"`) on a dataset with
  both `lower_spec` and `upper_spec` no longer triggers a
  mismatch warning. Warnings now fire only when the declared
  direction is INCOMPATIBLE with the available specs (e.g.
  decreasing without a lower_spec, or bidirectional with only
  one spec).
- **CLI test portability.** `validation/test_cli.py` now resolves
  the CLI invocation portably: prefers the console script on
  PATH, falls back to `python -m openpharmastability.cli`. Tests
  work whether or not the venv is activated.

### Tests
- New `validation/test_reproducibility.py` (4 tests for the
  `source_epoch` / `SOURCE_DATE_EPOCH` paths).
- `validation/test_data_schema.py` gets 6 new tests for the
  direction-compatibility warning logic.
- `validation/test_cli.py` gets 1 new test for
  `python -m openpharmastability.cli` invocation.
- Total: 184 tests passing (was 173).

### Backward compatibility
- All v0.1 single-attribute behavior is preserved. The existing
  golden test still passes. Default CLI invocation unchanged.

## [0.1.0] — initial v0.1 baseline

### Added
- CSV input via the `openpharmastability analyze` CLI.
- Three-batch fixed-effect ANCOVA poolability test at alpha = 0.25
  (slopes, intercepts, full pooling).
- Three linear regression models on the raw scale: POOLED,
  COMMON_SLOPE (one common slope + per-batch intercepts),
  SEPARATE (per-batch slopes and intercepts).
- One-sided 95% mean-response confidence bound. The t-quantile is
  `student_t.ppf(0.95, df)` (5% in one tail), not 0.975. The bound
  uses `s^2 * (X'X)^-1` via the chosen model's parameter
  covariance; per-batch SE for multi-batch models is built from a
  per-batch linear-combination vector against the same covariance.
- Numerical crossing solver (Brent's method) for the bound against
  the spec, with all four edge-case statuses: CROSSED,
  NO_CROSSING, FAIL_AT_BASELINE, FLAT_OR_OPPOSITE.
- Q1E room-temperature extrapolation cap (min(2x observed,
  observed + 12 months)), with a hard warning when the supported
  shelf life exceeds it.
- Confidence-bound plot (matplotlib, headless) with per-batch
  points, fit, CI band, spec line, crossing marker, and
  extrapolation shading.
- HTML report (jinja2) with dataset summary, model choice,
  p-values, shelf-life estimate, warnings, reproducibility
  metadata (file SHA-256, ISO-8601 timestamp, library versions,
  tool version, seed), product type → deliverable term
  (shelf life vs retest period), and the spec's verbatim
  disclaimer.
- Machine-readable JSON decision record matching the spec's
  example shape.
- Residual diagnostics (linearity / homoscedasticity / normality /
  influence) reported as evidence, not gates.

### Fixed in this baseline
- **COMMON_SLOPE per-batch linear-combination vector bug.**
  The fit was building one c-vector with `1.0` in every offset
  column and reusing it for every batch. Rewrote to build a
  per-batch c-vector from the parameter name list, so the SE for
  the i-th batch correctly excludes the offsets for the other
  batches. With the bug, the B2 lower bound at t=12 was 92.823
  instead of 92.932 (SE 0.154 instead of 0.089), and the worst-case
  crossing was 17.75 months instead of 17.95. The supported shelf
  life (rounded down) happened to be 17 either way, but every
  intermediate number (statistical crossing, bound values, CI
  band) was wrong.
- **Tautological COMMON_SLOPE bound test.** It was reading the
  c-vector from `fit.design` (the engine's own storage) and
  comparing the function to itself. Rewrote to build the c-vector
  from the parameter name list independently.
- **Missing COMMON_SLOPE cross-check.** `expected.json` only
  contained POOLED values. The engine selects COMMON_SLOPE on
  this dataset, so the golden test was not actually cross-checking
  the model the engine uses. Added a `common_slope_fit` section
  to `expected.json` with per-batch intercepts, b1_common,
  s_resid, per-batch crossings, and worst-case batch/crossing.
- **No independent regeneration script.** Wrote
  `tools/regen_expected.py` (plain numpy + scipy.stats.t +
  brentq; no project imports) with `--check` mode for CI. The
  `expected.json` is now regenerable from scratch by anyone with
  the dataset and a Python interpreter.
- **Schema direction-vs-bounds warning text was accusatory.**
  Reworded to neutral ("differs from the inferred direction…
  using the declared value per spec; the inferred value is
  recorded for audit").
- **Dead `__test__ = False` marker** in `poolability.py`. The
  `test_poolability` → `decide_poolability` rename made it
  unnecessary. Removed.
- **Brittle `column_count == 8` assertion** in `test_engine.py`.
  Replaced with a lower bound + match-the-CSV check.

### Tests in this baseline
- 173 pytest tests across 16 files (`validation/`).
- Golden-file test: `analyze(examples/assay_3batch.csv, ...)`
  reproduces the POOLED and COMMON_SLOPE slope, intercepts,
  residual SE, one-sided 95% bound, statistical crossing, and
  rounded shelf life to rtol = 1e-9 against
  `examples/assay_3batch.expected.json` (regenerated with
  `tools/regen_expected.py`).
- Cross-check test: an independent numpy + scipy.stats.t
  computation in `test_stats_bounds.py::test_common_slope_bound_uses_full_cov`
  builds the c-vector from the parameter name list and asserts
  the worst-case bound matches.
- Edge-case tests: no-crossing, fail-at-baseline, flat-slope,
  positive-slope (opposite to declared), full poolability on
  identical batches, no-poolability on distinct slopes, perfect-
  fit diagnostics short-circuit, tiny-data diagnostics no-raise,
  extrapolation cap under/over the binding limit, NO_CROSSING and
  FLAT_OR_OPPOSITE clearing the extrapolation flag, input
  immutability under `apply_extrapolation_caps`.
- CLI smoke tests: artifact production, numbers match the golden,
  analytics are deterministic (only the timestamp differs between
  two consecutive runs), `--seed` is recorded, `--product-type
  substance` returns retest period, `--version` works, missing
  required args fail with a non-zero exit.
- Regen tests: `--check` mode returns 0 against the committed
  file, the script does not import project code, regeneration is
  idempotent, the on-disk CSV matches the regenerated dataset.

### Known limitations (v0.1 out-of-scope, seam in place)
- XLSX upload (only CSV in v0.1).
- Multi-attribute analysis in a single run (one attribute per
  analyze() call).
- Degradant upper-limit logic as the primary path (the seam is
  there but the default v0.1 path is lower-limit / assay).
- BQL substitution (only "exclude" and "flag" policies; the other
  policies raise `NotImplementedError`).
- Transform selection (linear / raw-scale only).
- Two-sided / bidirectional attributes (`Direction.BIDIRECTIONAL`
  and `Direction.UNKNOWN` are inferred; a warning is recorded;
  the crossing math uses a heuristic that works for the spec's
  primary assay / degradant paths).
- Significant-change-gated extrapolation (the cap is hard-coded
  per Q1E; accelerated-condition evaluation is out of scope).
- Arrhenius, reduced designs (bracketing / matrixing), MKT, PDF
  export, web UI.

### Honest framing
This is a **decision-support / educational** tool. It is not a
regulatory-approval tool, not submission-ready, and not a
validated GxP / 21 CFR Part 11 system. The full disclaimer is in
`openpharmastability/contracts.py::DISCLAIMER` and is rendered
verbatim in every HTML report.


### Added
- **Data quality layer.** New `data/quality.py::audit_data_quality` runs
  16 non-mutating checks on the raw input frame and returns a
  `DataQualityReport` with severity-tagged issues
  (INFO / WARNING / ERROR) and a `can_analyze` flag. JSON-serializable.
  New contracts: `IssueSeverity` enum, `DataQualityIssue`,
  `DataQualityReport`. v0.3.0 reports issues; it does NOT block analysis.
- **Real BQL policies.** All five policies are now real (no longer
  seams): `exclude`, `flag`, `substitute_loq`, `substitute_half_loq`,
  `manual_review`. The function `apply_bql_policy` now returns
  `tuple[pd.DataFrame, BQLSummary]`. Substitution preserves the
  pre-substitution value in a new `original_value` column. Missing
  LOQ for substitution raises `ValueError` (never silently zeros).
  New contract: `BQLSummary`. `ValidatedData.bql_summary` records the
  applied policy and counts.
- **Transform candidate evidence.** New `stats/transforms.py::assess_transforms`
  fits `none` / `log` / `sqrt` candidates independently and records
  AICc, residual SE, normality p-value, and homoscedasticity
  p-value. The official v0.3.0 decision model is unchanged
  (raw-scale linear). `recommendation_is_official` is always False;
  the report must say this is exploratory evidence. New contracts:
  `TransformCandidate`, `TransformAssessment`.
- **CLI flags.**
  - `--bql-policy` now accepts `manual_review` (in addition to
    `exclude` / `flag` / `substitute_loq` / `substitute_half_loq`).
  - `--assess-transforms` (default off): compute transform-candidate
    evidence for the report. Does not change the official model.
- **JSON record exposes new fields** (`reports/record.py`): per-attribute
  `bql_summary` and (when enabled) `transform_assessment`.
- **New fixtures:** `examples/bql_attribute.csv` (30 rows, 1 BQL row
  with loq=88.0), `examples/data_quality_messy.csv` (16 rows;
  1 ERROR no-spec + 2 WARNINGS + 1 INFO).

### Tests
- `validation/test_data_quality.py` (18 new) — full coverage of the
  16 audit checks plus JSON-serializability.
- `validation/test_data_bql.py` (12 new) — all five policies,
  missing-LOQ raises, original_value preservation, no-BQL-column
  no-op, unknown policy.
- `validation/test_transforms.py` (11 new) — log/sqrt invalid for
  zero/negative, AICc recommendation, JSON-serializable.
- Existing `test_cli_bql.py` extended: substitute_loq / substitute_loq_half
  no longer raise `NotImplementedError`; they now raise `ValueError`
  when the loq column is missing (the v0.3.0 contract). The warning
  text changed from `bql_excluded: N row(s) ...` to
  `bql_policy='...': N excluded, M substituted, ...`.
- Total: 254 tests passing (was 238 at v0.2.1).

### Math
The v0.3.0 official shelf-life model is unchanged: linear, raw-scale,
fixed-effect batch, alpha = 0.25, one-sided 95% t-quantile
(`student_t.ppf(0.95, df)`, NOT 0.975), floor rounding, worst-case
earliest crossing for multi-batch. The transform candidates are
**evidence only** and do not alter the official decision. The
`recommendation_is_official` field is always False.

### Backward compatibility
- v0.2.1 single-attribute golden still passes: assay_3batch.csv →
  common_slope_batch_intercepts, supported shelf life 17 months.
- v0.2.1 multi-attribute fixture still has impurity_a as limiting
  at 7 months.
- v0.2.1 CLI invocation (`--attribute assay`, no other flags) still
  works. New flags are opt-in.
- The warning-text change in `validate_and_select` (BQL policy
  wording) is the only user-visible behavior change. Tests that
  asserted the old `bql_excluded:` text have been updated to assert
  the new `bql_policy='...':` text.

## [0.2.1] — 2026-06-13 — v0.2.1 hotfix

### Fixed
- **Metadata override is now applied to per-attribute analysis.**
  `AttributeMetadata.direction`, `lower_spec`, `upper_spec` are
  recorded on the per-attribute `StabilityResult` (via
  `dataclasses.replace`) so the metadata actually controls the
  per-attribute decision instead of being only a wrapper field.
- **XLSX metadata sheet detection.** When the input is an XLSX
  workbook and `--metadata-sheet` is supplied (without
  `--metadata-csv`), the metadata is now loaded from the same
  workbook. A separate XLSX metadata file with `--metadata-sheet`
  also works.
- **Multi HTML plot paths are now correct.** The HTML
  `<img src=...>` references are computed as relative paths
  from the report's directory to the `plots/` subdirectory.
  Works whether `plots_dir` is the same as the HTML directory
  or a subdirectory.
- **XLSX file handle leak on Windows.** `data/xlsx.py::load_xlsx`
  now wraps `pd.ExcelFile` in a context manager so the file
  handle is released on read completion.
- **`--bql-policy` is now wired.** The flag is passed to
  `apply_bql_policy` via `validate_and_select` so "exclude",
  "flag", "substitute_loq", and "substitute_loq_half" actually
  do something (the first two are the v0.1 paths; the latter
  two still raise `NotImplementedError` per the spec seam).
- **Multi metadata merge order.** `analyze_many` now MERGES
  file/library metadata INTO the dict that `select_limiting`
  already wrote, instead of overwriting it. The
  `tie_break` field (set by `select_limiting`) and the
  per-attribute metadata warnings are preserved.

### Tests
- 7 new tests in `validation/test_multi_engine.py` (metadata
  override, XLSX metadata-sheet detection, metadata-sheet
  missing-error, file-handle closure, select_limiting metadata
  preservation, two more for completeness).
- 2 new tests in `validation/test_data_xlsx.py` (file handle
  closure, sheet helper with candidates).
- 3 new tests in `validation/test_multi_reporting.py` (HTML
  plot paths — subdir, missing file, flat dir).
- New `validation/test_cli_bql.py` (3 tests) covering the
  wired bql-policy path.
- Total: 234 tests passing (was 219 at v0.2.0).

### Backward compatibility
- v0.2.0 single-attribute golden still passes.
- v0.2.0 multi-attribute fixture still has `impurity_a` as the
  limiting attribute at 7 months, UNLESS the user supplies
  metadata that intentionally changes the analysis.

## [0.2.0] — 2026-06-13 — multi-attribute + XLSX

### Added
- **Multi-attribute analysis.** A single CSV/XLSX with multiple
  attributes (e.g. assay + impurity_a) can now be analyzed in one
  run via `--all-attributes` or `--attributes a1,a2,a3`. The
  engine reports per-attribute sections and an overall limiting
  decision (smallest supported shelf life among PRIMARY
  attributes; ties broken by earlier statistical crossing).
- **XLSX input.** New `data/xlsx.py::load_xlsx` reads `.xlsx`
  workbooks. `--data-sheet` overrides the default sheet picker
  (which tries `results`, `data`, `stability` then the first
  sheet). Requires `openpyxl>=3.1` (added to `pyproject.toml`).
- **Attribute metadata table.** A separate CSV (`--metadata-csv`)
  or XLSX sheet (`--metadata-sheet`) describing per-attribute
  spec limits, direction, unit, role, spec_type, transform, and
  report order. Loaded by `data/metadata.py`. Optional; v0.1
  behavior is preserved when omitted.
- **New CLI flags.** `--attributes`, `--all-attributes`,
  `--metadata-csv`, `--metadata-sheet`, `--data-sheet`,
  `--plots-dir`, `--bql-policy`. The v0.1 `--attribute` and all
  default behaviors are preserved.
- **Multi-attribute JSON decision record** at `<output>.json` and
  multi-attribute HTML report at `--output` (with one plot per
  attribute saved to `--plots-dir`).

### New contracts (`openpharmastability/contracts.py`)
- `AttributeRole` enum: PRIMARY / SUPPORTIVE / INFORMATIONAL /
  EXCLUDED.
- `AttributeMetadata` dataclass: per-attribute override fields.
- `AttributeResult` dataclass: wraps a `StabilityResult` with
  multi-attribute context (`included_in_limiting_decision`,
  `exclusion_reason`).
- `MultiAttributeResult` dataclass: top-level multi-attr result
  (limiting attribute, supported shelf life, observed data
  length, warnings, metadata).
- `select_limiting` and `analyze_many` exported from
  `openpharmastability.shelf_life`.

### New fixtures
- `examples/multi_attribute.csv` — 48 rows, 3 batches × 4 time
  points × 2 attributes × 2 replicates, deterministic seed
  `20260613`. Decreasing assay and increasing impurity_a.
- `examples/multi_attribute_metadata.csv` — 2-row metadata
  (assay %LC, impurity_a %area).

### New tests
- `validation/test_data_xlsx.py` (5) — XLSX loader, default
  sheet picker, missing-sheet error, column whitespace stripping.
- `validation/test_data_metadata.py` (7) — metadata loader,
  missing-attribute-column error, coercion behavior, optional
  fields, default role.
- `validation/test_limiting.py` (6) — limiting selection rules,
  PRIMARY-only eligibility, tie-break by statistical crossing,
  exclusion reasons.
- `validation/test_multi_engine.py` (7) — `analyze_many`
  end-to-end on the multi-attribute fixture (single attr,
  multi attr, default, metadata path, no-data attr, file SHA).

### Math
The v0.2.0 multi-attribute path reuses the v0.1 single-attribute
math unchanged. Per-attribute fits, poolability tests, bounds,
crossings, and diagnostics are computed by the existing
single-attribute `analyze()` for each attribute independently;
the only new logic is the limiting decision (min supported
shelf life among PRIMARY attributes, ties broken by earlier
statistical crossing). No math invariants change.

### Backward compatibility
The v0.1 single-attribute golden test still passes. The v0.1
CLI invocation (`--attribute assay`, no other flags) still
produces the same numbers and the same HTML report shape.
`--source-epoch` and `SOURCE_DATE_EPOCH` (v0.1.1) are honored
by the multi-attribute path too.

## [0.1.1] — 2026-06-13 — v0.1.1 stabilization patch

### Fixed
- **Reproducible timestamps via `--source-epoch` / `SOURCE_DATE_EPOCH`.**
  The HTML and JSON metadata now record a deterministic timestamp
  when an explicit epoch is provided. Two CLI runs with the same
  `--source-epoch` produce byte-identical JSON. (Without the flag,
  behavior is unchanged: wall-clock timestamp.)
- **Direction-vs-spec false-positive warning.** Declaring
  `direction="decreasing"` (or `"increasing"`) on a dataset with
  both `lower_spec` and `upper_spec` no longer triggers a
  mismatch warning. Warnings now fire only when the declared
  direction is INCOMPATIBLE with the available specs (e.g.
  decreasing without a lower_spec, or bidirectional with only
  one spec).
- **CLI test portability.** `validation/test_cli.py` now resolves
  the CLI invocation portably: prefers the console script on
  PATH, falls back to `python -m openpharmastability.cli`. Tests
  work whether or not the venv is activated.

### Tests
- New `validation/test_reproducibility.py` (4 tests for the
  `source_epoch` / `SOURCE_DATE_EPOCH` paths).
- `validation/test_data_schema.py` gets 6 new tests for the
  direction-compatibility warning logic.
- `validation/test_cli.py` gets 1 new test for
  `python -m openpharmastability.cli` invocation.
- Total: 184 tests passing (was 173).

### Backward compatibility
- All v0.1 single-attribute behavior is preserved. The existing
  golden test still passes. Default CLI invocation unchanged.

## [0.1.0] — initial v0.1 baseline

### Added
- CSV input via the `openpharmastability analyze` CLI.
- Three-batch fixed-effect ANCOVA poolability test at alpha = 0.25
  (slopes, intercepts, full pooling).
- Three linear regression models on the raw scale: POOLED,
  COMMON_SLOPE (one common slope + per-batch intercepts),
  SEPARATE (per-batch slopes and intercepts).
- One-sided 95% mean-response confidence bound. The t-quantile is
  `student_t.ppf(0.95, df)` (5% in one tail), not 0.975. The bound
  uses `s^2 * (X'X)^-1` via the chosen model's parameter
  covariance; per-batch SE for multi-batch models is built from a
  per-batch linear-combination vector against the same covariance.
- Numerical crossing solver (Brent's method) for the bound against
  the spec, with all four edge-case statuses: CROSSED,
  NO_CROSSING, FAIL_AT_BASELINE, FLAT_OR_OPPOSITE.
- Q1E room-temperature extrapolation cap (min(2x observed,
  observed + 12 months)), with a hard warning when the supported
  shelf life exceeds it.
- Confidence-bound plot (matplotlib, headless) with per-batch
  points, fit, CI band, spec line, crossing marker, and
  extrapolation shading.
- HTML report (jinja2) with dataset summary, model choice,
  p-values, shelf-life estimate, warnings, reproducibility
  metadata (file SHA-256, ISO-8601 timestamp, library versions,
  tool version, seed), product type → deliverable term
  (shelf life vs retest period), and the spec's verbatim
  disclaimer.
- Machine-readable JSON decision record matching the spec's
  example shape.
- Residual diagnostics (linearity / homoscedasticity / normality /
  influence) reported as evidence, not gates.

### Fixed in this baseline
- **COMMON_SLOPE per-batch linear-combination vector bug.**
  The fit was building one c-vector with `1.0` in every offset
  column and reusing it for every batch. Rewrote to build a
  per-batch c-vector from the parameter name list, so the SE for
  the i-th batch correctly excludes the offsets for the other
  batches. With the bug, the B2 lower bound at t=12 was 92.823
  instead of 92.932 (SE 0.154 instead of 0.089), and the worst-case
  crossing was 17.75 months instead of 17.95. The supported shelf
  life (rounded down) happened to be 17 either way, but every
  intermediate number (statistical crossing, bound values, CI
  band) was wrong.
- **Tautological COMMON_SLOPE bound test.** It was reading the
  c-vector from `fit.design` (the engine's own storage) and
  comparing the function to itself. Rewrote to build the c-vector
  from the parameter name list independently.
- **Missing COMMON_SLOPE cross-check.** `expected.json` only
  contained POOLED values. The engine selects COMMON_SLOPE on
  this dataset, so the golden test was not actually cross-checking
  the model the engine uses. Added a `common_slope_fit` section
  to `expected.json` with per-batch intercepts, b1_common,
  s_resid, per-batch crossings, and worst-case batch/crossing.
- **No independent regeneration script.** Wrote
  `tools/regen_expected.py` (plain numpy + scipy.stats.t +
  brentq; no project imports) with `--check` mode for CI. The
  `expected.json` is now regenerable from scratch by anyone with
  the dataset and a Python interpreter.
- **Schema direction-vs-bounds warning text was accusatory.**
  Reworded to neutral ("differs from the inferred direction…
  using the declared value per spec; the inferred value is
  recorded for audit").
- **Dead `__test__ = False` marker** in `poolability.py`. The
  `test_poolability` → `decide_poolability` rename made it
  unnecessary. Removed.
- **Brittle `column_count == 8` assertion** in `test_engine.py`.
  Replaced with a lower bound + match-the-CSV check.

### Tests in this baseline
- 173 pytest tests across 16 files (`validation/`).
- Golden-file test: `analyze(examples/assay_3batch.csv, ...)`
  reproduces the POOLED and COMMON_SLOPE slope, intercepts,
  residual SE, one-sided 95% bound, statistical crossing, and
  rounded shelf life to rtol = 1e-9 against
  `examples/assay_3batch.expected.json` (regenerated with
  `tools/regen_expected.py`).
- Cross-check test: an independent numpy + scipy.stats.t
  computation in `test_stats_bounds.py::test_common_slope_bound_uses_full_cov`
  builds the c-vector from the parameter name list and asserts
  the worst-case bound matches.
- Edge-case tests: no-crossing, fail-at-baseline, flat-slope,
  positive-slope (opposite to declared), full poolability on
  identical batches, no-poolability on distinct slopes, perfect-
  fit diagnostics short-circuit, tiny-data diagnostics no-raise,
  extrapolation cap under/over the binding limit, NO_CROSSING and
  FLAT_OR_OPPOSITE clearing the extrapolation flag, input
  immutability under `apply_extrapolation_caps`.
- CLI smoke tests: artifact production, numbers match the golden,
  analytics are deterministic (only the timestamp differs between
  two consecutive runs), `--seed` is recorded, `--product-type
  substance` returns retest period, `--version` works, missing
  required args fail with a non-zero exit.
- Regen tests: `--check` mode returns 0 against the committed
  file, the script does not import project code, regeneration is
  idempotent, the on-disk CSV matches the regenerated dataset.

### Known limitations (v0.1 out-of-scope, seam in place)
- XLSX upload (only CSV in v0.1).
- Multi-attribute analysis in a single run (one attribute per
  analyze() call).
- Degradant upper-limit logic as the primary path (the seam is
  there but the default v0.1 path is lower-limit / assay).
- BQL substitution (only "exclude" and "flag" policies; the other
  policies raise `NotImplementedError`).
- Transform selection (linear / raw-scale only).
- Two-sided / bidirectional attributes (`Direction.BIDIRECTIONAL`
  and `Direction.UNKNOWN` are inferred; a warning is recorded;
  the crossing math uses a heuristic that works for the spec's
  primary assay / degradant paths).
- Significant-change-gated extrapolation (the cap is hard-coded
  per Q1E; accelerated-condition evaluation is out of scope).
- Arrhenius, reduced designs (bracketing / matrixing), MKT, PDF
  export, web UI.

### Honest framing
This is a **decision-support / educational** tool. It is not a
regulatory-approval tool, not submission-ready, and not a
validated GxP / 21 CFR Part 11 system. The full disclaimer is in
`openpharmastability/contracts.py::DISCLAIMER` and is rendered
verbatim in every HTML report.
