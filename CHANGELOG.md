# Changelog

All notable changes to OpenPharmaStability are documented here.
Versions follow [SemVer](https://semver.org/); the project is
pre-1.0 so breaking changes may appear in minor versions.

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
