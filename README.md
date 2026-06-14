# OpenPharmaStability

ICH Q1E-inspired stability analysis and shelf-life reporting toolkit for
pharmaceutical development. **v0.7.0** is the current release. The v0.1
baseline (one attribute, one long-term condition, fixed-effect ANCOVA,
one-sided 95% bound, lower-spec crossing) has been extended with multi-
attribute analysis, XLSX input, data-quality auditing, real BQL policies,
transform-candidate evidence, ICH Q1A(R2) significant-change gating,
opt-in advanced statistics (Arrhenius, MKT, reduced-design detection,
random-effects mixed model), a Python API + report artifacts (PDF +
self-contained HTML bundles), and a v0.7.0 backend-features layer
(sensitivity analysis, acceptance-criteria CSV export, multi-attribute
metadata spec override, direct XLSX support in the engine, pure-numpy
regen). **No frontend** — the UI pass (Cloudflare Pages + Claude
Design) is deferred to a future release per the user's "features first,
website last" reshape.

- CSV or XLSX input (single or multi attribute, single long-term condition)
- N-batch fixed-effect ANCOVA poolability at alpha = 0.25
- Linear raw-scale regression (transform candidates available as evidence)
- One-sided 95% confidence bound on the mean response
- Lower- and upper-spec crossing, rounded-down supported shelf life
- ICH Q1A(R2) significant-change gating of room-temperature extrapolation
- Optional Arrhenius / MKT / reduced-design / random-effects opt-ins
- HTML report + machine-readable JSON decision record
- Confidence-bound plot with extrapolation shading

> **Decision-support / educational only.** This is not a regulatory-approval
> tool, not submission-ready, and not a validated GxP / 21 CFR Part 11 system.
> See `DISCLAIMER` in `openpharmastability/contracts.py`.

## Install

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## CLI

```bash
openpharmastability analyze examples/assay_3batch.csv \
    --condition "25C/60RH" \
    --attribute assay \
    --output build/report.html
```

## v0.7.0 quick start

### Single-attribute (v0.1 back-compat)

```bash
openpharmastability analyze examples/assay_3batch.csv \
    --condition "25C/60RH" --attribute assay \
    --output build/report.html
```

Result: model=`common_slope_batch_intercepts`, statistical
crossing 17.95 mo, supported shelf life **17 mo**. The JSON record
also carries a `model_convergence` block (always populated; the
OLS / fixed-effect path reports `converged=True, boundary=False`)
and the v0.7.0 `lower_spec` / `upper_spec` fields (the spec
limits the engine used).

### Direct XLSX (v0.7.0)

The single-attribute `engine.analyze()` now accepts `.xlsx` and
`.xlsm` directly via the `load_table` dispatcher in `data/io.py`:

```bash
openpharmastability analyze examples/assay_3batch.xlsx \
    --condition "25C/60RH" --attribute assay \
    --output build/xlsx_report.html
```

### Multi-attribute (v0.2+)

```bash
openpharmastability analyze examples/multi_attribute.csv \
    --condition "25C/60RH" --all-attributes \
    --metadata-csv examples/multi_attribute_metadata.csv \
    --output build/multi_report.html
```

Result: 2 attributes, limiting **impurity_a** at 7 mo, per-attribute
plots written to `build/plots/`. The v0.7.0 release honors the
multi-attribute metadata `lower_spec` / `upper_spec` override
end-to-end: the override is applied to the per-attribute analysis
(v0.2.1 CHANGELOG claim, finally true in v0.7.0).

### XLSX with same-workbook metadata (v0.2.1+)

Build an XLSX with `results` and `attributes` sheets, then:

```bash
openpharmastability analyze stability.xlsx \
    --condition "25C/60RH" --all-attributes \
    --metadata-sheet attributes \
    --output build/xlsx_report.html
```

### Real BQL policies (v0.3.0)

```bash
openpharmastability analyze examples/bql_attribute.csv \
    --condition "25C/60RH" --attribute assay \
    --bql-policy manual_review \
    --output build/bql_report.html
```

Choices: `exclude` (default) | `flag` | `substitute_loq` |
`substitute_half_loq` | `manual_review`. The first two operate
on rows directly. The `substitute_*` policies require a finite
`loq` column and preserve the pre-substitution value in
`original_value`. `manual_review` keeps rows and flags the
attribute for human review in the report.

### Transform-candidate evidence (v0.3.0, opt-in)

```bash
openpharmastability analyze examples/assay_3batch.csv \
    --condition "25C/60RH" --attribute assay \
    --assess-transforms \
    --output build/transforms_report.html
```

The official shelf-life decision is unchanged. The report
adds a "Transform Candidate Evidence" section listing AICc,
s_resid, normality p, and homoscedasticity p for `none`,
`log`, and `sqrt` candidates. The recommendation is the valid
candidate with the lowest AICc; `recommendation_is_official`
is always False.

### ICH Q1A significant-change gating (v0.4.0)

```bash
openpharmastability analyze examples/assay_long_term.csv \
    --condition "25C/60RH" --attribute assay \
    --accelerated-condition "40C/75RH" \
    --intermediate-condition "30C/65RH" \
    --output build/q1a_report.html
```

When the dataset contains accelerated (40C/75RH) and/or
intermediate (30C/65RH) rows, the engine evaluates the five-criterion
ICH Q1A(R2) significant-change checklist (assay 5%, degradant OOS,
physical, pH, dissolution) per condition and applies the Q1E
extrapolation decision tree: no accelerated change → extrapolation
permitted within Q1E caps; change at < 3 mo → no extrapolation;
3-6 mo change → intermediate data required; intermediate change →
no extrapolation; change at > 6 mo → extrapolation permitted.

Opt out with `--no-significant-change-gate` to restore the v0.3.x
cap-only behavior byte-for-byte.

### Advanced statistics (v0.5.0, all opt-in)

```bash
# Arrhenius fit from multi-temperature rate data
openpharmastability analyze multi_temp.csv \
    --condition "25C/60RH" --attribute assay \
    --arrhenius --arrhenius-storage-temp 25.0

# Mean kinetic temperature from a `temp_c` column
openpharmastability analyze stability.csv \
    --condition "25C/60RH" --attribute assay \
    --mkt --mkt-ea-kj-mol 83.144

# ICH Q1D bracketing / matrixing detection
openpharmastability analyze stability.csv \
    --condition "25C/60RH" --attribute assay \
    --detect-reduced-design

# Random-effects mixed model (NOT the Q1E default)
openpharmastability analyze stability.csv \
    --condition "25C/60RH" --attribute assay \
    --random-effects
```

All four flags are opt-in. The default analyze() path is unchanged
from v0.4.0: fixed-effect ANCOVA, one-sided 95% bound on the mean,
Q1A-gated extrapolation. The opt-ins add `arrhenius_result`,
`mkt_celsius`, `reduced_design_report`, and `model_effects` fields
to the result; the v0.5.1 hotfix also surfaces
`model_convergence` at the top level for the mixed-model path.

### Export + artifact + acceptance-criteria (v0.6.0 + v0.7.0)

```bash
# v0.6.0: PDF copy (requires `pip install openpharmastability[pdf]`
# OR `.[pdf-fallback]`)
openpharmastability analyze stability.csv \
    --condition "25C/60RH" --attribute assay \
    --output build/report.html --pdf build/report.pdf

# v0.6.0: self-contained report bundle (HTML with the plot inlined
# as a base64 data URL, JSON, plots, optional PDF) with SHA-256
# digests and byte sizes.
openpharmastability analyze stability.csv \
    --condition "25C/60RH" --attribute assay \
    --output build/report.html --artifact-dir build/bundle

# v0.7.0: leave-one-out sensitivity over Cook's-distance outliers
openpharmastability analyze stability.csv \
    --condition "25C/60RH" --attribute assay \
    --sensitivity --output build/report.html

# v0.7.0: flat acceptance-criteria CSV for LIMS / regulatory
# tracking ingestion.
openpharmastability analyze stability.csv \
    --condition "25C/60RH" --attribute assay \
    --acceptance-csv build/acceptance.csv
```

### Python API (v0.6.0, programmatic surface)

```python
from openpharmastability import analyze_csv, analyze_multi, make_artifact
result = analyze_csv("examples/assay_3batch.csv",
                    condition="25C/60RH", attribute="assay")
print(result.supported_shelf_life_months)   # 17

multi = analyze_multi("examples/multi_attribute.csv",
                      condition="25C/60RH", all_attributes=True,
                      metadata_path="examples/multi_attribute_metadata.csv")
print(multi.limiting_attribute, multi.supported_shelf_life_months)
# impurity_a 7

artifact = make_artifact(result, "build/bundle")
print(artifact.html_sha256)   # byte-portable HTML
```

### Reproducible reports (v0.1.1+)

```bash
openpharmastability analyze ... --source-epoch 1700000000
```

Or set `SOURCE_DATE_EPOCH=1700000000` in the environment. Two
CLI runs with the same `--source-epoch` produce byte-identical
JSON.

### Data quality audit (v0.3.0)

The audit runs automatically on the raw input frame. The
report's "Data Quality" section lists issues by severity
(INFO / WARNING / ERROR). The audit reports issues but does not
block analysis.

```bash
openpharmastability analyze examples/data_quality_messy.csv \
    --condition "25C/60RH" --attribute assay \
    --output build/quality_report.html
```

Expect warnings for inconsistent `lower_spec` and `direction`,
and an INFO entry for a row whose `condition` doesn't match the
requested one. The engine still runs (the audit reports, it does
not gate).

## What v0.7.0 adds over v0.6.0

| Area | v0.6.0 | v0.7.0 (backend features) |
|---|---|---|
| Engine input | CSV only (XLSX reloaded separately for the plot). | `engine.analyze()` now calls a new `load_table` dispatcher in `data/io.py`; accepts `.csv`, `.xlsx`, `.xlsm` directly. |
| Multi-attribute metadata override | `lower_spec` / `upper_spec` recorded on `AttributeMetadata` but NOT applied to the per-attribute decision (v0.2.1 CHANGELOG claim was a lie). | Override is now applied to the per-attribute temp CSV before `analyze()` runs; the per-attribute result reflects the override. New `StabilityResult.lower_spec` / `upper_spec` fields record the engine-used value. |
| Sensitivity analysis | Diagnostics flagged Cook's-distance outliers but the report only mentioned them. | New `stats.sensitivity.compute_sensitivity` re-runs the analysis with each influential point removed and reports the new supported shelf life. `--sensitivity` flag attaches a `SensitivityReport`. New `StabilityResult.sensitivity_report` field. |
| Acceptance criteria | The JSON record was the only machine-readable artifact. | New `--acceptance-csv PATH` flag emits a flat 15-column CSV (one row per analyzed attribute) for LIMS / regulatory-tracking ingestion. New `AcceptanceCriteriaRow` dataclass + `to_acceptance_criteria` helper. |
| Regen validator | Used statsmodels for COMMON_SLOPE — shared an OLS backend with the engine (v0.1.1 known-open). | `tools/regen_expected.py` is now pure-numpy: hand-built design matrix + `np.linalg.lstsq` + `np.linalg.inv` for the covariance. The validator is fully independent of the engine. |
| Documentation | — | README / HANDOVER / NEXT_STEPS / CHANGELOG all synced to v0.7.0. |
| Tests | 390 → ~410 at v0.6.0. | 390 → **421** at v0.7.0; new tests for regen purity, `load_table` dispatch, metadata spec override, sensitivity, acceptance-criteria CSV, and reporting. |

The v0.6.0 shelf-life math is **unchanged** (linear, raw-scale, fixed-effect
batch, alpha = 0.25, one-sided 95% t-quantile, floor rounding, worst-case
earliest crossing, Q1A significant-change gating, PDF + artifact
export). v0.7.0 layers opt-in sensitivity / acceptance-criteria on top
plus bug-fixes (regen purity, XLSX dispatch, metadata override); the
default path produces the same numbers as v0.6.0.

See `CHANGELOG.md` for the full per-release entries. Future work and
known limitations are tracked in `NEXT_STEPS.md`.

## Tests

```bash
pytest -q
```

The full suite is **421 passing** (plus 4 PDF-backend tests that
skip cleanly on hosts without weasyprint/pdfkit). The golden-file
test in `validation/test_golden.py` locks slope, intercept,
residual SE, one-sided 95% bound, statistical crossing, and rounded
shelf life against the frozen expected values in
`examples/assay_3batch.expected.json`. `validation/conftest.py`
fails collection (exit code 2) if any v0.5 module is missing —
the v0.5 tests are hard-required, not skip-if-missing.

The independent validator `tools/regen_expected.py --check` is
also part of CI: it recomputes the golden values from scratch
using a pure-numpy path and exits 0 if the engine still agrees.
v0.7.0 made the regen fully independent of the engine (no shared
statsmodels backend).

## Layout

```
openpharmastability/
  contracts.py         # frozen shared dataclasses / enums / constants
  data/                # CSV/XLSX I/O, schema, condition parser, BQL/replicate/quality
                       #   load_table (v0.7.0) auto-dispatches by extension
  stats/               # regression, poolability, bounds, diagnostics,
                       #   transforms (v0.3), arrhenius (v0.5), mkt (v0.5),
                       #   sensitivity (v0.7.0)
  models/              # model selection
  shelf_life/          # engine + extrapolation caps + multi-attribute engine
  regulatory/          # significant-change (v0.4), reduced-design (v0.5)
  reports/             # HTML + JSON decision record (single + multi)
                       #   + pdf (v0.6) + artifacts (v0.6)
  api.py               # v0.6.0 thin programmatic surface
  plots/               # confidence-bound plot
  cli.py               # console entry point
examples/              # sample CSV/XLSX fixtures + expected.json
validation/            # pytest suites (conftest + 421 tests)
```

## Limitations / out of scope (current and future)

v0.7.0 is the current release. The stats engine remains in Python
and ICH Q1E-style fixed-effect by default; the opt-in advanced
features (Arrhenius, MKT, reduced designs, random effects,
sensitivity, acceptance-criteria CSV) are clearly labelled
exploratory. **No frontend in v0.6 or v0.7** — the UI pass
(Cloudflare Pages + Claude Design) is deferred to a future
release (v0.8.0+ or v1.0) per the user's "features first, website
last" reshape. When it lands, the UI is a thin client over the
existing Python engine; the math and the JSON decision record
stay authoritative.

Out of scope for the current release: web UI, REST API,
multi-condition shelf-life selection (the engine reports per
long-term condition, not the limiting one), and any GxP / 21 CFR
Part 11 validation claim.

## Reproducibility metadata

Every report embeds the input file SHA-256, row/column counts, library
versions, tool version, ISO-8601 timestamp, and (if applicable) the random
seed used.
