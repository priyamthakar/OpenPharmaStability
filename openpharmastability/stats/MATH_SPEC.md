# Stats math spec (Wave 1 — Agent B)

This is the authoritative math for the v0.1 stats core. Read this BEFORE writing
any code. Then implement it exactly. The "Confidence-Bound and Crossing
Computation" section in `OpenPharmaStability.md` and §5 of `AGENTS.md` are the
spec; this file is the implementation checklist.

## 1. Models (3 kinds, all linear on the raw scale)

Use `statsmodels.formula.api.ols` (or `sm.OLS` with `patsy` design matrices).
Batch is a **fixed effect**. Use treatment coding with one reference batch; do
NOT use sum coding (it would change the test).

### POOLED — `value ~ time`
- One intercept, one slope, all batches combined.
- params: `{"b0": intercept, "b1": slope}`.
- `n = total observations`, `p = 2`, `df_resid = n - 2`.
- `tbar = mean(time)`, `Sxx = sum((time - tbar)^2)`, computed on the pooled data.
- `fitted_fn(t) = b0 + b1 * t`.

### COMMON_SLOPE — `value ~ time + C(batch)` (no interaction)
- One common slope, one intercept per batch.
- `params`: `{"b1": common_slope, "b0_<batch>": intercept_for_batch, ...}`.
  The reference batch's intercept is the model intercept; the other intercepts
  are `model_intercept + C(batch)[T.<other>]` coefficients. Store them all as
  `b0_<batch>` for downstream convenience (and record the offset from the
  fitted `params`).
- `p = 2 + (k - 1)` where `k = n_batches`. `df_resid = n - p`.
- For the bound SE, you need per-batch `tbar_b`, `Sxx_b`, `n_b` (computed on
  each batch's rows). For the **common** slope term, the SE on the slope is
  the same across batches. The SE for the *intercept* for batch `b` comes from
  the covariance of the linear combination that produces `b0_<b>`. Easiest
  correct approach: use `model.cov_params()` and build the linear combination
  vector that maps to `b0_<b>` and `b1` for batch `b`. Pre-compute and store
  in `design["per_batch"]` a dict `{batch: {"tbar": ..., "Sxx": ..., "n": ...,
  "intercept_lift": array for the linear combo of params, "slope_idx": int}}`
  so `confidence_bound` can use it without re-deriving.

  For v0.1, a simpler safe implementation is acceptable: compute the
  per-batch `tbar_b`, `Sxx_b`, `n_b`, and use the **common-slope** SE for the
  slope (s * sqrt(1/Sxx_pooled? no — for the slope coefficient, s * sqrt
  (X'X)^-1[1,1]). The bound at time t for batch b is:
  ```
  yhat_b(t) = b0_<b> + b1 * t
  SE_b(t)   = s * sqrt( var_b_intercept + 2 * t * cov(b0_b, b1) + t^2 * var(b1) )
  ```
  where `var_b_intercept`, `cov(b0_b, b1)`, and `var(b1)` come from the
  parameter covariance matrix of the fitted COMMON_SLOPE model, using the
  row that corresponds to `b0_<b>` (or the equivalent linear combination).

  **Simplification permitted for v0.1:** the slope variance and covariance
  terms are tiny compared to the intercept variance unless t is very large;
  compute the full expression anyway because correctness matters. Use
  `model.cov_params()` and a small helper `def linear_comb_se(cov, vec)` that
  returns `sqrt(vec @ cov @ vec)`.

### SEPARATE — `value ~ time * C(batch)` (full interaction)
- One slope and one intercept per batch. Fit with `ols("value ~ time * C(batch)", data=df)`.
- `params`: `{"b0_<batch>": ..., "b1_<batch>": ...}` for each batch.
- `p = 2 * k`. `df_resid = n - p`.
- For the bound SE for batch `b`, build the linear combination vector for
  `(b0_<b>, b1_<b>)` and apply the same `linear_comb_se` helper against
  `model.cov_params()`.
- `fitted_fn(batch) -> (t -> b0_<batch> + b1_<batch> * t)`.

## 2. Poolability (3-step nested ANCOVA at α = 0.25)

Use `statsmodels.stats.anova.anova_lm` with `typ=2` (Type II SS). Each test
uses the **pooled MSE from the relevant nested model**, not separate per-batch
errors.

### Step 1 — Equality of slopes
- Full model: `value ~ time * C(batch)`. Anova with `typ=2` (or compare to
  reduced `value ~ time + C(batch)` for the interaction term).
- The interaction row gives the F-test for `time:batch` (equality of slopes).
- If `p < alpha` -> Poolability.NONE (separate per batch). Stop.
- Record `p_slopes` in `PoolabilityResult`.

### Step 2 — Equality of intercepts (only if slopes not rejected)
- Reduced model: `value ~ time + C(batch)`.
- Anova; the `C(batch)` row gives the F-test for batch (equality of intercepts
  given common slope).
- If `p < alpha` -> Poolability.PARTIAL (common slope, batch-specific
  intercepts). Stop.
- Record `p_intercepts` in `PoolabilityResult`.

### Step 3 — Full pooling (only if neither rejected)
- Poolability.FULL (pooled regression). Stop.

Each test's reported MSE must come from the **reduced** model of that step
(common practice and what statsmodels gives with `typ=2`). `alpha` defaults to
`POOLABILITY_ALPHA = 0.25` from contracts.

## 3. Mean-response confidence bound

Given a fitted model and a time `t`, the **mean response** SE is:

```
SE_mean(t) = s * sqrt( c' * (X'X)^-1 * c )
```

where `c` is the linear combination vector for the prediction at `t`, and
`s = sqrt(SSE / df_resid)`. For a simple OLS this collapses to the closed
form in the spec:

```
SE_mean(t) = s * sqrt( 1/n + (t - tbar)^2 / Sxx )
```

But use the **general** `c' (X'X)^-1 c` form via `model.cov_params()` so it
works for COMMON_SLOPE and SEPARATE too. Build the `c` vector for the model's
parameter order.

### One-sided 95% bound — t-quantile 0.95 (NOT 0.975)

```
from scipy.stats import t as student_t
multiplier = student_t.ppf(0.95, df=df_resid)   # 5% in ONE tail
```

`L(t) = yhat(t) - multiplier * SE_mean(t)`
`U(t) = yhat(t) + multiplier * SE_mean(t)`

For two-sided 95% (BIDIRECTIONAL / UNKNOWN) use 0.975 — but this is OUT of
scope for v0.1. Default to one-sided 95% in the public function
`confidence_bound(fit, t, side, conf=0.95)`.

## 4. Crossing (numerical, not closed-form)

The bound is curved. Solve numerically.

For a decreasing attribute with a `lower_spec`:

```
def find_crossing(fit, data, horizon=60.0):
    """Return CrossingResult.
    If multi-batch model, find the earliest crossing across batches and
    report the governing batch.
    """
```

Use `scipy.optimize.brentq` on `f(t) = bound(t) - spec` over `[0, horizon]`,
where `bound` is `L(t)` for decreasing+lower, `U(t)` for increasing+upper.
If `f(0)` and `f(horizon)` have the same sign, the bound never crosses in
the horizon — return `CrossingResult(crossing_months=None, status="no_crossing",
...)`. If `f(0) <= 0` (i.e. bound already at/past spec at baseline), return
`CrossingResult(crossing_months=0, status="fail_at_baseline", ...)`. If the
fitted slope is near zero or opposite to the declared direction, return
`CrossingResult(crossing_months=None, status="flat_or_opposite", ...)`.

`find_crossing` must take a `ValidatedData` and a `FitResult`; for multi-batch
models, evaluate each batch and take the earliest crossing (worst case);
record the `governing_batch` name. Use the bound for the **governing** batch's
curve when reporting the crossing time.

## 5. Tests you MUST write

- `validation/test_stats_regression.py` — fit_models on a tiny in-memory
  ValidatedData fixture. Assert `params["b0"]` and `params["b1"]` match
  `numpy.polyfit(x, y, 1)` within `rtol=1e-9`. Assert `s_resid` matches
  `sqrt(SSE / df)`. Assert `cov` shape matches param count. Assert
  `fitted_fn` at known t matches `b0 + b1 * t`.
- `validation/test_stats_poolability.py` — 3 small fixtures:
    a) all batches with identical slope and intercept -> Poolability.FULL.
    b) identical slope, different intercepts -> Poolability.PARTIAL.
    c) clearly different slopes -> Poolability.NONE.
  Assert the decision for each.
- `validation/test_stats_bounds.py` — the critical one. Build a POOLED fit
  on a known dataset. Assert `confidence_bound(fit, tbar, "lower")` matches
  `yhat(tbar) - t.ppf(0.95, df) * s/sqrt(n)` exactly (the bound is tightest
  at `tbar` and the SE reduces to `s / sqrt(n)`). Also assert that
  `confidence_bound` uses the 0.95 quantile, NOT 0.975 — assert
  `abs(multiplier_used - student_t.ppf(0.95, df)) < 1e-12`.
- `validation/test_stats_crossing.py` — small decreasing-assay fixture.
  Assert the crossing time matches a hand-computed `brentq` call (within
  `rtol=1e-8`). Also test edge cases: no_crossing, fail_at_baseline,
  flat_or_opposite.

## 6. Imports

You may import from `openpharmastability.contracts` and standard third-party
(numpy, pandas, scipy, statsmodels). Do NOT import from `openpharmastability.data`
or any other agent's module (Wave 2 wires them together).

## 7. Rule

If you find yourself needing to change a contract, STOP and report. Do not
edit `contracts.py`.
