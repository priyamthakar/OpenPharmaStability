# OpenPharmaStability

## One-Line Positioning

**OpenPharmaStability is an ICH Q1E-inspired stability analysis and shelf-life reporting toolkit for pharmaceutical development.**

It is not a simple calculator. The goal is to turn assay, degradant, and other CQA stability data into reproducible shelf-life estimates, confidence-bound plots, batch poolability decisions, and report-ready statistical justification.

## Product Concept

OpenPharmaStability helps users upload structured stability data and generate a defensible analysis report for pharmaceutical shelf-life or retest-period justification.

The toolkit should support:

- Stability plots by batch, condition, and attribute.
- ICH Q1E-style regression analysis.
- Batch poolability testing.
- Shelf-life estimation from confidence-bound/specification crossing.
- Worst-case batch logic when data are not poolable.
- Multi-attribute shelf-life selection.
- Report-ready methods, assumptions, plots, tables, limitations, and warnings.

## Example Input Schema

```csv
batch,condition,temp_c,rh,time_months,attribute,value,lower_spec,upper_spec
B1,25C/60RH,25,60,0,assay,100.2,90,110
B1,25C/60RH,25,60,3,assay,98.7,90,110
B1,25C/60RH,25,60,6,assay,97.9,90,110
B2,25C/60RH,25,60,0,assay,99.8,90,110
B2,25C/60RH,25,60,3,assay,98.5,90,110
```

Required columns for the first MVP:

- `batch`
- `condition`
- `time_months`
- `attribute`
- `value`
- At least one specification limit: `lower_spec` and/or `upper_spec`.

Specification limits are one-sided where appropriate. Assay typically has both
limits; impurities and degradants typically have only `upper_spec`; some
attributes only have `lower_spec`. Validation must accept a missing bound rather
than require both, and must reject a row that has neither.

Shelf-life evaluation must use the **shelf-life (end-of-expiry) acceptance
criteria**, which can differ from tighter **release** limits. If a `spec_type`
(release vs shelf-life) is provided, the tool should evaluate crossings against
the shelf-life limits and warn if only release limits are supplied.

Recommended additional columns:

- `direction` (one of `decreasing` / `increasing` / `bidirectional` /
  `unknown`). Declares the expected trend for shelf-life evaluation. If absent,
  direction is inferred from which spec limit is finite (upper-only ->
  increasing, lower-only -> decreasing, both bounds present -> bidirectional).
  A fitted trend opposite to the declared/inferred direction raises a warning
  rather than silently switching the spec limit used.
- `temp_c`
- `rh`
- `storage_type`
- `unit`
- `method`
- `replicate`

Future schema should separate raw data from attribute metadata. For example,
the uploaded results table can stay tidy, while an optional attribute metadata
table defines how each CQA is evaluated:

```csv
attribute,unit,direction,lower_spec,upper_spec,spec_type,transform,attribute_role
assay,%LC,decreasing,90,110,shelf_life,none,primary
impurity_a,%area,increasing,,1.0,shelf_life,none,degradant
pH,pH,bidirectional,5.5,7.5,shelf_life,none,physical
```

This avoids repeating specification and modeling metadata on every row and
makes multi-attribute reports easier to audit.

Replicate handling should be explicit because not all repeated values are
independent stability observations. The user should choose or confirm a
`replicate_policy`:

```text
individual:
  Fit each row as an independent result when rows represent independent
  stability observations.

mean_by_batch_time:
  Average values within each batch/time/attribute/condition cell before
  regression.

technical_replicates_average:
  Average analytical repeats from the same pull/sample before regression to
  avoid pseudo-replication.
```

If the data are pre-averaged to batch-time means, this must be stated
explicitly, as it changes the residual degrees of freedom and the width of the
confidence bounds.

Condition-string parsing should be robust. The following must all normalize to
the same condition:

```text
25C/60RH
25°C/60%RH
25 C / 60 %RH
25C 60% RH
```

Below-quantitation-limit (BQL) handling should follow a documented policy
rather than silently dropping or zero-filling values:

```text
supported policies:
  - substitute LOQ/2 and flag the substitution
  - substitute LOQ and flag the substitution
  - exclude BQL points and flag the exclusion
  - require manual review for BQL-affected attributes

default behavior:
  Do not silently choose a BQL policy for report mode. Require the user to
  confirm the policy, record it in the report, and preserve raw BQL flags.
  Blanks must never be fed to the regression as zeros.
```

Recommended BQL-related columns:

- `is_bql`
- `loq`
- `lod`
- `reported_value`
- `numeric_value`

## Statistical Core

The first serious version should focus on linear stability regression.

For each attribute and condition:

1. Fit a simple model:

```text
value ~ time
```

2. Fit a batch interaction model:

```text
value ~ time * batch
```

3. Test batch poolability as a three-step nested sequence (ICH Q1E), all at alpha `0.25`:

```text
Step 1 - Equality of slopes:
  Test the time * batch interaction.
  If significant (p < 0.25): slopes differ -> stop, do not pool.

Step 2 - Equality of intercepts (only if slopes not rejected):
  Refit with a common slope and test the batch main effect.
  If significant (p < 0.25): intercepts differ -> common slope, batch-specific intercepts.

Step 3 - Full pooling (only if neither rejected):
  Slopes and intercepts common -> pool all batches.
```

Each test uses the pooled (ANCOVA) mean-square error from the relevant
nested model, not separate per-batch error terms. The slope test uses the
error from the full `value ~ time * batch` model; the intercept test uses
the error from the common-slope `value ~ time + batch` model.

Batch is treated as a **fixed effect**, consistent with ICH Q1E. The tool
must not silently switch to a random-effects/mixed model. If the batch count
is large enough that a random-effects treatment might be expected, raise a
warning and require the user to opt in explicitly rather than changing the
model automatically (changing it would alter the confidence bounds).

4. Choose the model:

```text
Different slopes (Step 1 rejected):
  Use batch-specific regression.
  Shelf life is governed by the shortest supported batch.

Same slopes, different intercepts (Step 2 rejected):
  Use common slope with batch-specific intercepts.
  Shelf life is governed by the shortest supported batch.

Same slopes, same intercepts (nothing rejected):
  Use pooled regression.
  Shelf life is estimated from the pooled model. Pooling can narrow the
  confidence bounds, but it does not by itself justify extrapolation beyond
  the period allowed by the Q1E decision-tree logic.
```

## Statistical Assumptions and Diagnostics

The linear-regression shelf-life model rests on four assumptions. The tool
should test each and turn failures into the warnings already listed, rather
than reporting an estimate silently.

```text
Linearity:
  The value-vs-time relationship is linear on the modeled scale.
  Check: lack-of-fit test where replicate/time structure allows, plus a
  residuals-vs-time plot. Failure -> nonlinearity warning, suggest transform.

Homoscedasticity (constant variance):
  Residual spread is roughly constant across time and fitted values.
  Check: Breusch-Pagan or White test; residuals-vs-fitted plot.
  Failure -> consider transform or weighted least squares; warn.

Normality of residuals:
  Residuals are approximately normal (the basis for the t-based bounds).
  Check: Q-Q plot, and Shapiro-Wilk only when enough residual degrees of
  freedom exist for the test to be meaningful. Mild deviation is usually
  tolerable; flag strong deviation.

Independence / influence:
  No single point dominates the fit.
  Check: Cook's distance and leverage. If one observation exceeds the
  influence threshold, raise the "single outlier controls the result" warning
  and provide a sensitivity estimate with and without that point. Do not
  automatically exclude the point.
```

Diagnostics belong in the report so the shelf-life number is interpretable,
not just asserted.

Small-sample caution:

```text
Formal diagnostic tests can have low power in typical stability datasets.
The report should present diagnostics as evidence and warnings, not as an
automatic pass/fail gate unless the issue makes the model mathematically
invalid or the shelf-life estimate non-interpretable.
```

## Data Transformation and Kinetics

Linear regression on the raw scale is the default, but it is not always the
right model — especially for degradants.

```text
Default:
  Zero-order (linear) on the raw measured scale.

When linearity fails or kinetics warrant it:
  - Log-transform the response (first-order / exponential decay or growth).
  - Other justified transforms (e.g., square-root) where chemically sensible.

Rules:
  - The transform must be declared and recorded in the report.
  - Confidence bounds and spec crossings are computed on the modeled scale,
    then back-transformed for reporting.
  - Spec limits must be transformed onto the same scale as the fitted bound
    before crossing calculations are performed.
  - The tool must not auto-pick a transform silently; it proposes one when
    diagnostics fail and requires confirmation in report mode.
```

Transform guardrails:

```text
Log transforms require positive values and positive specification limits.
Zero, negative, missing, or BQL-heavy data require a documented preprocessing
choice before a log model can be fit. For degradants with many zeros or BQL
values, the report should warn that first-order/log-linear modeling may be
unstable.
```

## Shelf-Life Logic

All confidence bounds are one-sided 95% bounds on the **mean response** from
the fitted regression line (not a prediction interval for an individual future
result). This matches ICH Q1E.

For decreasing attributes such as assay:

```text
Shelf life = time where the lower one-sided 95% confidence bound on the mean
response crosses the lower specification.
```

For increasing attributes such as degradants or impurities:

```text
Shelf life = time where the upper one-sided 95% confidence bound on the mean
response crosses the upper specification.
```

For attributes that can increase or decrease, or where the direction is not
known:

```text
Shelf life = earliest time where either two-sided 95% confidence bound crosses
the relevant lower or upper specification.
```

Note: this is intentional, not an inconsistency. A two-sided 95% interval puts
2.5% in each tail, whereas the one-sided 95% bounds used for known-direction
attributes put 5% in a single tail. The unknown/bidirectional path is therefore
deliberately stricter per side, matching Q1E's treatment of attributes whose
direction of change is not known in advance.

### Confidence-Bound and Crossing Computation

The baseline calculation must be specified exactly so it can be validated.

For a fitted linear model `value = b0 + b1 * time`, the estimated mean response
and its standard error at time `t` are:

```text
yhat(t)   = b0 + b1 * t
SE_mean(t)= s * sqrt( 1/n + (t - tbar)^2 / Sxx )

where:
  s    = residual standard error = sqrt( SSE / df )
  df   = n - p   (p = number of estimated parameters in the chosen model)
  n    = number of observations used in the fit
  tbar = mean of the time values
  Sxx  = sum( (time_i - tbar)^2 )
```

One-sided 95% bounds (note: t-multiplier uses the 0.95 quantile, i.e. 5% in a
single tail — NOT 0.975):

```text
Lower bound L(t) = yhat(t) - t_(0.95, df) * SE_mean(t)
Upper bound U(t) = yhat(t) + t_(0.95, df) * SE_mean(t)
```

For the two-sided / unknown-direction case use the 0.975 quantile so each tail
carries 2.5%.

Crossing (decreasing attribute, lower spec as example):

```text
Find the smallest t > 0 such that L(t) = lower_spec.
Because SE_mean(t) grows as t moves away from tbar, the bound is curved;
solve numerically (bisection or Brent) over [0, evaluation_horizon], not by a
closed-form linear inverse.
```

Per model:

```text
Pooled model:
  Single curve; one crossing.

Common slope, batch-specific intercepts / batch-specific slopes:
  Evaluate each batch's own curve and take the WORST-CASE (earliest) crossing
  as the supported shelf life.
```

The standard errors must come from the chosen model's covariance matrix
( (X'X)^-1 scaled by s^2 ), so df and Sxx reflect the actual design, not a
single-batch shortcut.

Constraints on the reported shelf life:

```text
- The reported shelf life may not exceed the observed long-term data length
  unless extrapolation is explicitly justified and flagged.
- Round the final supported shelf life DOWN to the nearest whole month
  (or nearest scheduled test interval), never up.
- A pooled model may improve precision, but extrapolation still needs a
  separate Q1E-style justification based on long-term behavior, accelerated
  data, variability, and storage category.
- Hard extrapolation cap (Q1E rule of thumb, room-temperature storage):
  under applicable room-temperature Q1E scenarios, the proposed shelf life
  should not exceed roughly twice, and should not be more than 12 months
  beyond, the period covered by long-term data. The tool must hard-flag any
  estimate past the applicable cap, regardless of how far the statistical
  crossing extends.
```

Crossing edge cases the solver must handle explicitly:

```text
Bound never reaches the spec within the evaluation horizon:
  Report shelf life as "at least <horizon>, not limiting within the evaluated
  range" rather than a spurious extrapolated number.

Bound already beyond spec at t=0:
  The attribute fails at baseline. Report 0 / fail and warn; do not return a
  negative or zero-rounded shelf life silently.

Slope near zero or opposite to declared direction:
  Do not report a crossing as positive support. Warn that no meaningful trend
  toward the spec is detected; a flat profile within spec may support the full
  evaluated period but must be labeled as such.
```

Future Q1E decision-tree module:

```text
Room-temperature storage:
  If long-term and accelerated data show little/no change and little/no
  variability, extrapolation beyond long-term data may be supportable within
  Q1E limits.

Room-temperature storage with change/variability:
  Statistical analysis and relevant supporting data become important; if
  batches/factors cannot be combined, the proposed shelf life should not exceed
  the shortest period supported by any batch/factor combination.

Refrigerated storage:
  Extrapolation is more limited than for room-temperature storage.

Significant accelerated change:
  Extrapolation may be inappropriate or may require intermediate-condition
  data, depending on whether significant change appears within 3 months,
  between 3 and 6 months, or at the intermediate condition.

Intermediate condition:
  If accelerated data show significant change, intermediate-condition data
  can become the deciding evidence for whether any limited extrapolation is
  supportable.
```

For multiple attributes:

```text
Final supported shelf life = minimum supported shelf life across all assessed attributes.
```

Example:

| Attribute | Direction | Supported Time | Status |
|---|---:|---:|---|
| Assay | Decreasing | 30 months | Pass |
| Impurity A | Increasing | 24 months | Limiting |
| Dissolution | Decreasing | 36 months | Pass |

Final supported shelf life:

```text
24 months, limited by Impurity A.
```

## MVP Scope

The MVP should be narrow but polished.

Build one clean workflow:

1. Upload CSV or XLSX.
2. Validate required columns.
3. Auto-detect batches, conditions, and attributes.
4. Let the user choose the long-term condition.
5. Run Q1E-style regression for assay.
6. Run batch poolability test.
7. Estimate shelf life using confidence-bound/specification crossing.
8. Generate plots.
9. Export an HTML report.

## Baseline v0.1 Implementation Contract

The first build should intentionally be smaller than the full product spec.
The goal is to produce one correct, inspectable, end-to-end report before
adding every regulatory branch.

In scope:

```text
- CSV input.
- One long-term condition selected by the user.
- One quantitative attribute, initially assay.
- Three-batch fixed-effect Q1E-style ANCOVA poolability.
- Linear raw-scale model only.
- One-sided 95% confidence bound for known decreasing assay.
- Lower-spec crossing and rounded-down supported shelf life.
- Plot with points, fitted line, confidence bound, lower spec, crossing marker,
  and extrapolation shading.
- HTML report with assumptions, model choice, p-values, shelf-life estimate,
  warnings, and reproducibility metadata.
```

Out of scope for v0.1, but designed for later:

```text
- XLSX upload.
- Multiple attributes.
- Degradant upper-limit logic.
- Bidirectional/two-sided attributes.
- BQL-heavy datasets.
- Transform selection.
- Significant-change-gated extrapolation.
- Arrhenius modeling.
- Reduced designs, bracketing, and matrixing.
- PDF export.
```

This baseline should be treated as the first validation target. Once it is
working, every additional feature can be added without moving the statistical
foundation.

Definition of done (v0.1):

```text
- Deterministic: same input file -> byte-identical numeric results across runs
  (fixed library versions; no randomness in the core path).
- Validated: on a committed reference dataset, the computed slope, intercept,
  residual standard error, one-sided 95% bound, statistical crossing time, and
  rounded supported shelf life match pre-recorded expected values within a
  tight numeric tolerance. This is the first golden-file test.
- Cross-checked: the same dataset run through an independent statsmodels OLS
  fit reproduces slope/intercept/SE, confirming the bound math is correct.
- Inspectable: the HTML report renders end-to-end with the plot, the model
  choice, p-values, the shelf-life estimate, warnings, and reproducibility
  metadata, with no silent failures.
- Honest on edge cases: the no-crossing, fail-at-baseline, and flat-slope
  cases above produce the specified messages rather than crashing or emitting
  a misleading number.
```

Reaching this definition of done is the baseline. Everything in the broader
spec is layered on top of it without changing these core computations.

## MVP Report Sections

The generated report should include:

- Dataset summary.
- Required-column validation.
- Batch, time point, and condition summary.
- Model formula.
- Poolability test results.
- Selected model.
- Shelf-life estimate.
- Confidence-bound plot (see specification below).
- Warnings and limitations.
- Reproducibility metadata. This should be concrete and embedded in the
  report: input file SHA-256 hash, row/column counts, library versions
  (pandas, numpy, scipy, statsmodels), random seed if any, tool version, and
  an ISO-8601 analysis timestamp.

The report should also distinguish the deliverable type. A drug **substance**
is assigned a **retest period**; a drug **product** is assigned a **shelf
life**. The math is identical, but the report must use the correct term based
on a `product_type` input (substance vs product) and default to "shelf life"
with a warning if unspecified.

Example report summary (single-attribute assay scenario, 18 months of
observed data):

```text
Supported shelf life: 24 months
Statistical estimate: 27.4 months (bound crosses spec at 27.4 months)
Observed data length: 18 months
Limiting attribute: assay
Condition: 25C/60RH
Model selected: pooled regression
Poolability alpha: 0.25
Confidence bound: lower one-sided 95% on mean response
Extrapolation: yes, supported period (24 mo) extends beyond 18 months
  of observed data and is flagged accordingly
```

This is a separate scenario from the multi-attribute example above (where
Impurity A was limiting at 24 months); here only assay is assessed.

The confidence-bound plot must show, at minimum:

```text
- Observed data points, distinguished by batch.
- The fitted regression line(s) for the selected model.
- The one-sided (or two-sided) 95% confidence band on the mean response.
- The relevant specification limit(s) as a horizontal reference line.
- The shelf-life crossing point, marked and labeled.
- The extrapolation region beyond observed data, visually shaded/flagged.
```

## Regulatory Report Mode

The strongest feature should be a report engine that produces cautious, traceable, regulatorily literate language.

The report should clearly state:

- Poolable: yes/no/partial.
- Model used: pooled, common slope with batch-specific intercepts, or batch-specific.
- Shelf life supported by data.
- Limiting attribute.
- Extrapolation used: none, limited, or model-based.
- Data warnings.
- Statistical assumptions.
- Known limitations.

Suggested disclaimer:

```text
This report is ICH Q1E-inspired and intended for educational, exploratory,
and reproducible decision-support use. It is not a substitute for qualified
regulatory, statistical, or quality review. The toolkit does not provide
21 CFR Part 11 audit trails, electronic signatures, or data integrity
controls, and is not a validated GxP system.
```

## Decision Engine Outputs

The product should expose a structured decision record for each analysis, not
only plots and p-values. This makes the software easier to test, audit, and
turn into reports.

Example:

```text
Supported shelf life: 24 months
Statistical crossing: 27.4 months
Limiting attribute: Impurity A
Condition: 25C/60RH
Model: common slope with batch-specific intercepts
Poolability decision: partial pooling
Poolability alpha: 0.25
Confidence bound: upper one-sided 95% on mean response
Observed long-term data: 18 months
Extrapolation: yes, Q1E decision-tree flag required
Data adequacy: 3 batches, 7 time points, long-term condition present
Warnings: accelerated significant change not evaluated
```

Suggested machine-readable result shape:

```json
{
  "supported_shelf_life_months": 24,
  "statistical_crossing_months": 27.4,
  "limiting_attribute": "Impurity A",
  "condition": "25C/60RH",
  "model": "common_slope_batch_intercepts",
  "poolability": "partial",
  "poolability_alpha": 0.25,
  "confidence_bound": "upper_one_sided_95_mean",
  "observed_long_term_months": 18,
  "extrapolation": "flag_required",
  "warnings": ["accelerated_significant_change_not_evaluated"]
}
```

## Warnings To Detect

Concrete minimum-data thresholds (warn or block below these):

```text
- At least 3 batches recommended (Q1E primary-stability expectation); fewer
  is allowed for exploratory use but must be flagged.
- At least 3 distinct time points per batch including t=0, since a slope plus
  a meaningful residual term needs more than 2 points.
- A long-term condition must be identifiable.
- Each batch should have a baseline (t=0) value.
```

OpenPharmaStability should warn users when:

- Fewer than three batches are present.
- Fewer than three distinct time points (including baseline) are available for a batch.
- No long-term storage condition is detected.
- A batch has missing baseline data.
- Specifications are missing.
- The fitted trend is in the unexpected direction.
- The shelf-life estimate requires extrapolation.
- Residuals suggest nonlinearity.
- A single outlier strongly controls the result.
- Confidence intervals are too wide for a useful estimate.
- Different CQAs suggest conflicting shelf lives.

## Accelerated Significant-Change Evaluation

Whether extrapolation of long-term data is even permitted depends on the
behavior at accelerated conditions (ICH Q1A). The tool should evaluate the
accelerated condition (typically 40C/75RH) against significant-change criteria
and gate the extrapolation logic on the result.

The significant-change checklist differs by product type and dosage form. The
tool should treat the criteria below as configurable rules, not hard-coded
universal truth. Drug-product rules are broader; drug-substance evaluation may
be driven mainly by failure to meet the applicable specification.

Significant change at accelerated conditions typically means any of:

```text
- A 5% change in assay from the initial value (or failure to meet acceptance
  criteria for potency where biological/immunological methods apply).
- Any degradation product exceeding its acceptance criterion.
- Failure to meet acceptance criteria for appearance, physical attributes, or
  functionality (e.g., color, phase separation, resuspendability, caking,
  hardness, dose delivery).
- Failure to meet the acceptance criterion for pH.
- Failure to meet the acceptance criterion for dissolution for 12 dosage units.
```

Decision gating:

```text
No significant change at accelerated condition:
  Extrapolation of long-term data may be supportable within the Q1E caps.

Significant change within the first 3 months at accelerated condition:
  Extrapolation is generally not appropriate. Long-term data should govern,
  and additional discussion of excursions may be needed.

Significant change between 3 and 6 months at accelerated condition:
  Intermediate-condition data (e.g., 30C/65RH) may be required. If the
  intermediate condition does not show significant change, limited
  extrapolation may still be supportable within Q1E decision-tree limits.

Significant change at intermediate condition:
  Extrapolation is generally not appropriate; the supported shelf life should
  rely on long-term data and may need to be shorter than the long-term period
  if variability or failures indicate that.
```

This evaluation is presented as a gate/warning, not an automatic rejection,
since the appropriate response depends on storage category and study design.

## Arrhenius Module

Arrhenius analysis should be included as a supporting/exploratory module, not the primary shelf-life engine.

Model:

```text
ln(k) = ln(A) - Ea / (R*T)
```

Where:

- `k` is the degradation rate estimated at each temperature.
- `T` is absolute temperature in Kelvin.
- `R` is the gas constant.
- `Ea` is activation energy.

The activation energy is not identifiable from a single stressed temperature.
The module requires degradation rates from at least two stress temperatures
(three or more preferred) to estimate `Ea`; with fewer it must refuse to fit
and warn rather than report a spurious value.

Use cases:

- Stress-study interpretation.
- Formulation comparison.
- Teaching accelerated degradation behavior.
- Exploratory prediction of degradation rate at storage temperature.

Wording should remain conservative:

```text
Arrhenius analysis is presented as exploratory model-based support.
The primary shelf-life decision path remains long-term stability regression
unless a justified extrapolation basis is provided.
```

## Regulatory Watch

OpenPharmaStability should primarily target the established ICH Q1E/Q1A(R2)
framework until the newer consolidated ICH Q1 guideline is finalized.

The consolidated ICH Q1 reached Step 2b in April 2025, and EMA lists the
public consultation period as closed on 30 July 2025. As of this brief, the
current public materials still identify it as a draft rather than a Step 4
final guideline. Once final, it is intended to consolidate and supersede the
older Q1A-F and Q5C stability guidances. The project should track this draft,
but must not treat it as final guidance until it reaches Step 4 and regional
implementation status is clear.

## Suggested Tech Stack

Python core:

- `pandas` for data handling.
- `numpy` for numerical operations.
- `scipy` for statistical utilities.
- `statsmodels` for regression and ANCOVA.
- `plotly` or `matplotlib` for plots.
- `jinja2` for HTML report templates.
- `weasyprint` or browser print-to-PDF for PDF export.

Optional web app:

- Streamlit for fastest prototype.
- FastAPI plus React for a polished long-term app.

Suggested package layout:

```text
openpharmastability/
  data/
  models/
  stats/
  reports/
  plots/
  examples/
  validation/
  cli.py
```

## CLI Concept

```bash
openpharmastability analyze stability_data.csv \
  --condition "25C/60RH" \
  --attribute assay \
  --output report.html
```

Future:

```bash
openpharmastability analyze stability_data.xlsx \
  --all-attributes \
  --long-term "25C/60RH" \
  --report-mode regulatory \
  --output OpenPharmaStability_Report.html
```

## Portfolio Framing

Recommended description:

```text
OpenPharmaStability is an open-source ICH Q1E-inspired stability analysis
toolkit for pharmaceutical development, turning assay and degradant stability
data into reproducible shelf-life estimates, confidence-bound plots,
batch poolability decisions, and report-ready statistical workflows.
```

Avoid claiming:

- Regulatory approval tool.
- Submission-ready validation.
- Guaranteed compliance.
- Replacement for quality/statistical review.

Use instead:

- ICH Q1E-inspired.
- Decision support.
- Educational and exploratory.
- Report-ready.
- Traceable and reproducible.
- Audit-supporting (not an audit-trail/Part 11 system).
- Stability analysis toolkit.

## Build Order

Recommended first milestones:

1. Create sample stability dataset.
2. Implement schema validation.
3. Implement assay regression for one condition.
4. Implement poolability testing.
5. Implement confidence-bound shelf-life calculation.
6. Generate the first plot.
7. Generate the first HTML report.
8. Add degradant upper-limit logic.
9. Add multi-attribute limiting shelf-life logic.
10. Add example datasets and validation checks.

## Validation and Roadmap

Credibility for an open-source, regulatory-adjacent tool comes from validation:

```text
Golden-file suite:
  Reproduce available regulatory/statistical worked examples and assert the
  tool's shelf-life numbers, confidence bounds, and poolability decisions
  match. Treat any drift as a failing test.

Property/regression tests:
  Lock poolability decisions and shelf-life outputs on fixed example datasets
  so refactors cannot silently change results.
```

Phase 2 candidates (out of MVP scope, worth flagging in the data model now):

```text
Reduced designs (ICH Q1D):
  Detect datasets that look bracketed (e.g., only extreme strengths/pack sizes
  tested) or matrixed (subset of time points per batch) and warn that the
  linear-regression analysis assumes a full design.

Significant-change-gated extrapolation:
  Wire the accelerated significant-change evaluation into the extrapolation
  decision automatically.

Mean kinetic temperature (MKT):
  Support MKT computation for excursion/storage interpretation.
```
