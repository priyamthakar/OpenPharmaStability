# OpenPharmaStability

ICH Q1E-inspired stability analysis and shelf-life reporting toolkit for
pharmaceutical development. **v0.5.1** is the current release. The v0.1
baseline (one attribute, one long-term condition, fixed-effect ANCOVA,
one-sided 95% bound, lower-spec crossing) has been extended with multi-
attribute analysis, XLSX input, data-quality auditing, real BQL policies,
transform-candidate evidence, ICH Q1A(R2) significant-change gating, and
opt-in advanced statistics (Arrhenius, MKT, reduced-design detection,
random-effects mixed model).

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

## v0.5.1 quick start

### Single-attribute (v0.1 back-compat)

```bash
openpharmastability analyze examples/assay_3batch.csv \
    --condition "25C/60RH" --attribute assay \
    --output build/report.html
```

Result: model=`common_slope_batch_intercepts`, statistical
crossing 17.95 mo, supported shelf life **17 mo**. The JSON record
also carries a `model_convergence` block (always populated; the
OLS / fixed-effect path reports `converged=True, boundary=False`).

### Multi-attribute (v0.2+)

```bash
openpharmastability analyze examples/multi_attribute.csv \
    --condition "25C/60RH" --all-attributes \
    --metadata-csv examples/multi_attribute_metadata.csv \
    --output build/multi_report.html
```

Result: 2 attributes, limiting **impurity_a** at 7 mo, per-attribute
plots written to `build/plots/`.

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
is always False through v0.5.1.

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

## What v0.5.1 adds over v0.4.0

| Area | v0.5.0 | v0.5.1 (audit patch) |
|---|---|---|
| Arrhenius | New module + `--arrhenius` flag; fits `ln(k) = ln(A) − Ea/(R·T)` from per-temperature OLS slopes. | Hook now filters to the selected attribute and respects the declared direction (decreasing vs increasing degradant). |
| MKT | New module + `--mkt` flag; Haynes equation with the USP <1160> default `Ea = 83.144 kJ/mol`. | Emits an explicit warning when `--mkt` is requested but the input has no `temp_c` column. |
| Reduced designs (ICH Q1D) | New module + `--detect-reduced-design` flag; flags bracketing and matrixing. | Unchanged. |
| Random effects | Opt-in `--random-effects` mixed model via statsmodels `mixedlm`. | Mixed-model convergence / boundary status is now a top-level `StabilityResult.model_convergence` field, surfaced in warnings, the JSON record, and the HTML report. |
| Documentation | — | README / HANDOVER / NEXT_STEPS synced to v0.5.1. |
| Tests | 341 → ~350 at v0.5.0. | New conftest hard-requires the v0.5 modules; new direction / convergence / MKT-warning tests; **360 total**. |

The v0.4.0 shelf-life math is **unchanged** (linear, raw-scale, fixed-effect
batch, alpha = 0.25, one-sided 95% t-quantile, floor rounding, worst-case
earliest crossing, Q1A significant-change gating). v0.5.x layers
opt-in exploratory analyses on top; the default path produces the
same numbers as v0.4.0.

See `CHANGELOG.md` for the full per-release entries. Future work and
known limitations are tracked in `NEXT_STEPS.md`.

## Tests

```bash
pytest -q
```

The golden-file test in `validation/test_golden.py` locks slope, intercept,
residual SE, one-sided 95% bound, statistical crossing, and rounded shelf
life against the frozen expected values in `examples/assay_3batch.expected.json`.
`validation/conftest.py` fails collection (exit code 2) if any v0.5 module
is missing — the v0.5 tests are hard-required, not skip-if-missing.

## Layout

```
openpharmastability/
  contracts.py         # frozen shared dataclasses / enums / constants
  data/                # CSV/XLSX I/O, schema, condition parser, BQL/replicate/quality
  stats/               # regression, poolability, bounds, diagnostics,
                       #   transforms (v0.3), arrhenius (v0.5), mkt (v0.5)
  models/              # model selection
  shelf_life/          # engine + extrapolation caps + multi-attribute engine
  regulatory/          # significant-change (v0.4), reduced-design (v0.5)
  reports/             # HTML + JSON decision record (single + multi)
  plots/               # confidence-bound plot
  cli.py               # console entry point
examples/              # sample CSV/XLSX fixtures + expected.json
validation/            # pytest suites (conftest + 360 tests)
```

## Limitations / out of scope (current and future)

v0.5.1 is the current release. The stats engine remains in Python and
ICH Q1E-style fixed-effect by default; the opt-in advanced features
above are clearly labelled exploratory. v0.6.0 will add PDF export and
a Cloudflare Pages UI as a thin client over the existing Python engine;
the math and the JSON decision record stay authoritative.

Out of scope for the current release: PDF export, web UI, REST API,
multi-condition shelf-life selection (the engine reports per long-term
condition, not the limiting one), and any GxP / 21 CFR Part 11
validation claim.

## Reproducibility metadata

Every report embeds the input file SHA-256, row/column counts, library
versions, tool version, ISO-8601 timestamp, and (if applicable) the random
seed used.
