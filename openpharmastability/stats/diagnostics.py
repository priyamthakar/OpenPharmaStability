"""Residual diagnostics for OpenPharmaStability v0.1.

This module is the implementation of the spec section
"Statistical Assumptions and Diagnostics". It runs four evidence checks
on a fitted linear model and returns a :class:`DiagnosticsResult`:

1. **Linearity** — does the response look linear in time?  When the
   design has replicates (multiple observations at the same
   ``(batch, time_months)`` point), a classical lack-of-fit F-test is
   the most powerful option.  When the design has no replicates, a
   quadratic-term test on the regression surface acts as a fallback
   detector of obvious curvature.  Failure -> nonlinearity warning,
   suggest transform.

2. **Homoscedasticity** — is the residual variance roughly constant
   across the design?  Implemented with the Breusch-Pagan LM test
   using the fitted values (and the time column) as the heteroscedasticity
   regressors.  Failure -> consider WLS / transform; warn.

3. **Normality of residuals** — the t-based confidence bound assumes
   normal residuals.  We use the Shapiro-Wilk test.  When the residual
   degrees of freedom are too few for Shapiro-Wilk to be meaningful,
   we skip the test and note "insufficient df".  Failure -> flag
   strong deviations (the user is told to look at the Q-Q plot
   implicitly via the report's ``details`` block).

4. **Influence** — single-point dominance.  Computed via Cook's
   distance.  Points with ``cooks_d > 4 / n`` are flagged.  The
   function never *removes* an influential point — it only records
   the index list, leaving the call/decision to the engine.

Diagnostics are EVIDENCE, not hard gates.  This function must never
raise on a fitted model; it returns a :class:`DiagnosticsResult` that
records every failure and the human-readable reason.  In degenerate
cases (tiny data, all-zero design, etc.) each check resolves to
"ok=True" with a "insufficient data" note, again per the spec.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.formula.api as smf
from statsmodels.stats.diagnostic import het_breuschpagan

from openpharmastability.contracts import (
    DiagnosticsResult,
    FitResult,
    ModelKind,
    ValidatedData,
)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

#: Significance level used for the formal tests.  Standard 0.05.
_ALPHA: float = 0.05

#: Shapiro-Wilk needs at least 3 observations (scipy's hard floor).  We
#: require a little more residual df than that because the test is known
#: to over-reject deviations in very small samples; below this threshold
#: the test is skipped and ``normal_resid_ok`` stays True with a note.
_SHAPIRO_MIN_RESID_DOF: int = 5

#: Cook's distance threshold: the textbook 4/n rule.
COOKS_THRESHOLD_FACTOR: float = 4.0

#: Minimum number of distinct time points before a quadratic-term test
#: is even meaningful.  With fewer than 3 unique times the regression
#: surface is saturated and we cannot test for curvature at all.
_QUADRATIC_MIN_UNIQUE_TIMES: int = 3


# ---------------------------------------------------------------------------
# Residual construction
# ---------------------------------------------------------------------------


def _compute_residuals(fit: FitResult, data: ValidatedData) -> np.ndarray:
    """Return ``y - yhat`` for the rows actually used in the fit.

    The residual vector is aligned with the data the diagnostics
    report should reference, which is ``data.df`` filtered to finite
    ``value`` and ``time_months`` — the same subset the regression
    module feeds to ``statsmodels``.  The returned positions match
    the original row order of ``data.df`` (i.e. the i-th element is
    the residual for the i-th row that survived the filter, NOT for
    every row of ``data.df`` if some were dropped).  Callers use the
    returned index list to map back to original data row indices.
    """
    df = data.df
    mask = (
        df["value"].notna()
        & df["time_months"].notna()
        & df["batch"].notna()
    )
    sub = df.loc[mask, ["batch", "time_months", "value"]].copy()
    t = sub["time_months"].to_numpy(dtype=float)
    y = sub["value"].to_numpy(dtype=float)
    b = sub["batch"].astype(str).to_numpy()

    fn = fit.fitted_fn
    if fit.kind is ModelKind.POOLED:
        yhat = np.asarray([fn(float(tv)) for tv in t], dtype=float)
    else:
        # COMMON_SLOPE and SEPARATE both expose a per-batch callable.
        yhat = np.empty_like(y, dtype=float)
        for i, (tv, batch) in enumerate(zip(t, b)):
            yhat[i] = fn(str(batch))(float(tv))

    return y - yhat, sub.index.to_numpy()


def _yhat_values(fit: FitResult, data: ValidatedData) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(t, yhat, used_index)`` for the rows used in the fit.

    Used by the heteroscedasticity test and the influence test, both
    of which need the *fitted* value, not just the residual.
    """
    df = data.df
    mask = (
        df["value"].notna()
        & df["time_months"].notna()
        & df["batch"].notna()
    )
    sub = df.loc[mask, ["batch", "time_months", "value"]].copy()
    t = sub["time_months"].to_numpy(dtype=float)
    b = sub["batch"].astype(str).to_numpy()

    fn = fit.fitted_fn
    if fit.kind is ModelKind.POOLED:
        yhat = np.asarray([fn(float(tv)) for tv in t], dtype=float)
    else:
        yhat = np.empty(t.shape, dtype=float)
        for i, (tv, batch) in enumerate(zip(t, b)):
            yhat[i] = fn(str(batch))(float(tv))
    return t, yhat, sub.index.to_numpy()


# ---------------------------------------------------------------------------
# Linearity
# ---------------------------------------------------------------------------


def _lack_of_fit_test(
    data: ValidatedData,
    fit: FitResult,
    t: np.ndarray,
    yhat: np.ndarray,
    used_index: np.ndarray,
) -> tuple[bool | None, dict[str, Any]]:
    """Pure-error / lack-of-fit F-test using ``(batch, time_months)``
    groups as the natural replicates.

    The test is a standard split of SSE into the pure-error component
    (within-group variance) and the lack-of-fit component (how much
    the group means deviate from the fitted line).

    Returns ``(ok, details)`` where ``ok`` is ``True``/``False`` if the
    test could be run, or ``None`` if the design has no replicates
    (the caller should fall back to a different linearity check).
    """
    sub = data.df.loc[used_index, ["batch", "time_months", "value"]].copy()
    sub["_resid"] = sub["value"].to_numpy(dtype=float) - yhat
    sub["_group"] = sub["batch"].astype(str) + "||" + sub["time_months"].astype(str)

    sizes = sub.groupby("_group").size()
    n_replicated = int((sizes > 1).sum())
    if n_replicated == 0:
        # No replicates -> can't run a proper lack-of-fit test.
        return None, {
            "method": "lack_of_fit",
            "skipped": True,
            "reason": "no_replicates",
        }

    p = len(fit.params)  # number of fitted parameters
    sse = float(((sub["value"] - yhat) ** 2).sum())
    group_stats = sub.groupby("_group").agg(
        n=("_resid", "size"),
        ybar=("value", "mean"),
        yhat=("value", lambda v: float(np.mean(v - sub.loc[v.index, "_resid"].values))),
    )
    # Note: the yhat aggregator above is just a placeholder; the
    # group-level fitted value is the mean of yhat at the group rows
    # (since the line is deterministic in (batch, time)).  Re-derive
    # correctly:
    sub["_yhat"] = yhat
    group_yhat = sub.groupby("_group")["_yhat"].mean()
    group_ybar = sub.groupby("_group")["value"].mean()
    group_n = sub.groupby("_group").size()

    # Pure error: within-group scatter around the group mean.
    sse_pe = 0.0
    for grp, rows in sub.groupby("_group"):
        ybar_g = group_ybar.loc[grp]
        sse_pe += float(((rows["value"] - ybar_g) ** 2).sum())
    n_groups = int(group_n.size)
    df_pe = int(sub.shape[0] - n_groups)
    if df_pe <= 0:
        return None, {
            "method": "lack_of_fit",
            "skipped": True,
            "reason": "df_pe_nonpositive",
        }

    # Lack of fit: how far the group means deviate from the fitted line.
    sse_lof = float(((group_n * (group_ybar - group_yhat) ** 2)).sum())
    df_lof = n_groups - p
    if df_lof <= 0:
        return None, {
            "method": "lack_of_fit",
            "skipped": True,
            "reason": "df_lof_nonpositive",
        }

    ms_lof = sse_lof / df_lof
    ms_pe = sse_pe / df_pe
    if ms_pe <= 0 or not np.isfinite(ms_pe):
        return None, {
            "method": "lack_of_fit",
            "skipped": True,
            "reason": "zero_pure_error",
        }

    f_stat = float(ms_lof / ms_pe)
    f_pvalue = float(1.0 - stats.f.cdf(f_stat, df_lof, df_pe))
    # Use the survival function directly for numerical safety:
    f_pvalue = float(stats.f.sf(f_stat, df_lof, df_pe))

    ok = bool(f_pvalue >= _ALPHA)
    return ok, {
        "method": "lack_of_fit",
        "skipped": False,
        "f_stat": f_stat,
        "f_pvalue": f_pvalue,
        "df_lof": int(df_lof),
        "df_pe": int(df_pe),
        "n_replicated_groups": n_replicated,
        "n_groups": n_groups,
        "sse": float(sse),
        "sse_lof": float(sse_lof),
        "sse_pe": float(sse_pe),
    }


def _quadratic_term_test(
    data: ValidatedData,
    fit: FitResult,
    t: np.ndarray,
    yhat: np.ndarray,
    used_index: np.ndarray,
) -> tuple[bool | None, dict[str, Any]]:
    """Fallback linearity check: add a quadratic term and see whether
    it has explanatory power.

    This is the only test we can run when the data have no
    replicates.  We use a Wald test on the coefficient of
    ``time_months ** 2`` from an OLS that includes a batch main
    effect (to stay close to the common-slope model that most
    stability datasets will fit).  If the quadratic term is
    individually and jointly different from zero, the linear
    assumption looks wrong.
    """
    if len(fit.batches) > 1 and len(t) >= 2 * len(fit.batches) + 3:
        # Fit a model that mirrors the COMMON_SLOPE specification plus
        # a quadratic term.  This isolates "is there a quadratic
        # signal in time after accounting for batch intercepts?".
        sub = data.df.loc[used_index, ["batch", "time_months", "value"]].copy()
        sub["t2"] = sub["time_months"].astype(float) ** 2
        try:
            aug = smf.ols("value ~ time_months + t2 + C(batch)", data=sub).fit()
        except Exception as exc:  # pragma: no cover - defensive
            return None, {
                "method": "quadratic_term",
                "skipped": True,
                "reason": f"fit_failed:{exc!r}",
            }
    else:
        # Single batch or too few points: simple y ~ t + t^2.
        sub = data.df.loc[used_index, ["time_months", "value"]].copy()
        sub["t2"] = sub["time_months"].astype(float) ** 2
        try:
            aug = smf.ols("value ~ time_months + t2", data=sub).fit()
        except Exception as exc:  # pragma: no cover - defensive
            return None, {
                "method": "quadratic_term",
                "skipped": True,
                "reason": f"fit_failed:{exc!r}",
            }

    # The quadratic coefficient name is "t2".
    if "t2" not in aug.params.index:
        return None, {
            "method": "quadratic_term",
            "skipped": True,
            "reason": "no_quadratic_term",
        }
    t_pvalue = float(aug.pvalues["t2"])
    coef = float(aug.params["t2"])
    t_stat = float(aug.tvalues["t2"])
    ok = bool(t_pvalue >= _ALPHA)
    return ok, {
        "method": "quadratic_term",
        "skipped": False,
        "coef": coef,
        "t_stat": t_stat,
        "t_pvalue": t_pvalue,
    }


def _check_linearity(
    data: ValidatedData,
    fit: FitResult,
    t: np.ndarray,
    yhat: np.ndarray,
    used_index: np.ndarray,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Run whichever linearity test is appropriate and return
    ``(ok, notes, details)``.

    Decision order:

    1. If the design has true replicates, prefer the lack-of-fit F
       test (most powerful).
    2. Otherwise fall back to the quadratic-term Wald test.
    3. If even the fallback cannot be run (degenerate time axis),
       return ``ok=True`` with an "insufficient data" note.
    """
    notes: list[str] = []
    details: dict[str, Any] = {}

    # 1) Lack-of-fit
    lof_ok, lof_details = _lack_of_fit_test(data, fit, t, yhat, used_index)
    details["lack_of_fit"] = lof_details

    if lof_ok is not None:
        # We got a verdict from the lack-of-fit test.
        details["primary"] = "lack_of_fit"
        if not lof_ok:
            notes.append(
                "Linearity check failed: lack-of-fit F-test "
                f"p = {lof_details['f_pvalue']:.4g} < {_ALPHA}. "
                "Consider a non-linear transform (log, sqrt) or a "
                "higher-order model."
            )
        return lof_ok, notes, details

    # 2) Quadratic-term fallback
    quad_ok, quad_details = _quadratic_term_test(data, fit, t, yhat, used_index)
    details["quadratic_term"] = quad_details

    if quad_ok is None:
        # Truly insufficient data: stay quiet (ok=True) and explain.
        notes.append(
            "Linearity check skipped: insufficient data "
            "(fewer than 3 unique times, no replicates, or fit "
            "could not be augmented). Inspect residuals-vs-time "
            "manually."
        )
        details["primary"] = "skipped"
        return True, notes, details

    details["primary"] = "quadratic_term"
    if not quad_ok:
        notes.append(
            "Linearity check failed: quadratic time term "
            f"p = {quad_details['t_pvalue']:.4g} < {_ALPHA}. "
            "Consider a non-linear transform (log, sqrt) or a "
            "higher-order model."
        )
    return quad_ok, notes, details


# ---------------------------------------------------------------------------
# Homoscedasticity (Breusch-Pagan)
# ---------------------------------------------------------------------------


def _check_homoscedasticity(
    resid: np.ndarray,
    t: np.ndarray,
    yhat: np.ndarray,
    n: int,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Run Breusch-Pagan on residuals against a design that
    contains the fitted values and the time column.

    statsmodels returns ``(LM, LM p-value, F, F p-value)``.  We use
    the F p-value for the inference because the LM version over-
    rejects in small samples (as noted in statsmodels' own docstring).

    If we don't have enough residual df to even attempt the test we
    return ok=True with a note, per the spec.
    """
    notes: list[str] = []
    details: dict[str, Any] = {}

    n_obs = int(resid.size)
    if n_obs < 4:
        notes.append(
            "Homoscedasticity check skipped: fewer than 4 observations. "
            "Inspect residuals-vs-fitted manually."
        )
        details["skipped"] = True
        return True, notes, details

    # Build the heteroscedasticity regressor matrix.  Include the
    # fitted values and the time column.  Add a constant so the test
    # matches its textbook definition.
    exog = np.column_stack([np.ones(n_obs), yhat, t])
    # Guard against a constant column that would make exog rank-
    # deficient (e.g. all-zero residuals, all-equal yhat/t).
    if np.linalg.matrix_rank(exog) < exog.shape[1]:
        # Drop the offending column.
        keep = []
        for j in range(exog.shape[1]):
            sub = np.delete(exog, j, axis=1)
            if np.linalg.matrix_rank(sub) == sub.shape[1]:
                keep.append(j)
        if not keep:
            notes.append(
                "Homoscedasticity check skipped: design matrix is "
                "rank-deficient. Inspect residuals-vs-fitted manually."
            )
            details["skipped"] = True
            return True, notes, details
        exog = exog[:, keep]

    try:
        lm_stat, lm_pvalue, f_stat, f_pvalue = het_breuschpagan(
            resid, exog, robust=True
        )
    except Exception as exc:  # pragma: no cover - defensive
        notes.append(
            f"Homoscedasticity check failed unexpectedly: {exc!r}. "
            "Treat as inconclusive."
        )
        details["skipped"] = True
        return True, notes, details

    details.update({
        "lm_stat": float(lm_stat),
        "lm_pvalue": float(lm_pvalue),
        "f_stat": float(f_stat),
        "f_pvalue": float(f_pvalue),
        "df": int(exog.shape[1] - 1),
    })
    ok = bool(f_pvalue >= _ALPHA)
    if not ok:
        notes.append(
            "Homoscedasticity check failed: Breusch-Pagan "
            f"p = {f_pvalue:.4g} < {_ALPHA}. Residual variance "
            "appears to depend on the fitted values or time. "
            "Consider weighted least squares or a variance-"
            "stabilising transform."
        )
    return ok, notes, details


# ---------------------------------------------------------------------------
# Normality (Shapiro-Wilk)
# ---------------------------------------------------------------------------


def _check_normality(resid: np.ndarray) -> tuple[bool, list[str], dict[str, Any]]:
    """Shapiro-Wilk on the residuals.

    We require at least :data:`_SHAPIRO_MIN_RESID_DOF` observations
    (scipy's hard floor is 3, but the test is not meaningful below ~5
    residual df).  Otherwise we record "insufficient df" and leave
    ``normal_resid_ok = True`` per the spec.
    """
    notes: list[str] = []
    details: dict[str, Any] = {}
    n = int(resid.size)
    if n < _SHAPIRO_MIN_RESID_DOF:
        notes.append(
            "Normality check skipped: insufficient residual df "
            f"({n} < {_SHAPIRO_MIN_RESID_DOF}). Inspect Q-Q plot "
            "manually."
        )
        details["skipped"] = True
        details["n_resid"] = n
        return True, notes, details

    # Shapiro-Wilk cannot handle a constant residual vector
    # (e.g. perfect linear fit); treat that as not-non-normal.
    if np.std(resid) <= 0 or not np.isfinite(np.std(resid)):
        notes.append(
            "Normality check skipped: residuals are constant "
            "(zero variance). Normality is not testable in this case."
        )
        details["skipped"] = True
        details["n_resid"] = n
        return True, notes, details

    try:
        w_stat, p_value = stats.shapiro(resid)
    except Exception as exc:  # pragma: no cover - defensive
        notes.append(
            f"Normality check failed unexpectedly: {exc!r}. "
            "Treat as inconclusive."
        )
        details["skipped"] = True
        return True, notes, details

    details.update({
        "W": float(w_stat),
        "p_value": float(p_value),
        "n_resid": n,
    })
    ok = bool(p_value >= _ALPHA)
    if not ok:
        notes.append(
            "Normality check failed: Shapiro-Wilk "
            f"p = {p_value:.4g} < {_ALPHA}. Residuals show strong "
            "deviation from normality. The t-based confidence bound "
            "may be unreliable for very small samples; consider a "
            "robust alternative or a variance-stabilising transform."
        )
    return ok, notes, details


# ---------------------------------------------------------------------------
# Influence (Cook's distance)
# ---------------------------------------------------------------------------


def _refit_ols_for_influence(
    data: ValidatedData,
    used_index: np.ndarray,
    fit: FitResult,
) -> Any:
    """Re-fit the same model statsmodels fit so we can call
    ``get_influence().cooks_distance``.

    We rebuild a model whose parameter count matches the supplied
    ``FitResult``.  POOLED -> ``value ~ time_months``;
    COMMON_SLOPE -> ``value ~ time_months + C(batch)``;
    SEPARATE -> ``value ~ time_months * C(batch)``.  The OLS
    fit is independent of the per-fit design in
    ``regression.py``; we only need the *influence* numbers, not
    the confidence bound.
    """
    sub = data.df.loc[used_index, ["batch", "time_months", "value"]].copy()
    sub["batch"] = sub["batch"].astype(str)
    if fit.kind is ModelKind.POOLED:
        return smf.ols("value ~ time_months", data=sub).fit()
    if fit.kind is ModelKind.COMMON_SLOPE:
        return smf.ols("value ~ time_months + C(batch)", data=sub).fit()
    # SEPARATE
    return smf.ols("value ~ time_months * C(batch)", data=sub).fit()


def _check_influence(
    data: ValidatedData,
    fit: FitResult,
    used_index: np.ndarray,
    resid: np.ndarray,
) -> tuple[list[int], list[str], dict[str, Any]]:
    """Compute Cook's distance and flag points above the 4/n threshold.

    Returns ``(influential_row_indices, notes, details)``.  The row
    indices are positions in ``data.df`` (the same coordinates the
    spec asks for: "row indices in the data used for the fit").

    Implementation note
    -------------------
    Cook's distance is defined as ``D_i = (e_i^2 / (p * s^2)) *
    h_ii / (1 - h_ii)``.  When ``s^2`` is essentially zero (a
    near-perfect fit on integer or hand-picked data) the
    internally-studentized form statsmodels returns can be wildly
    inflated by floating-point noise in the residuals.  In that
    regime there is no real signal to detect, so we short-circuit
    to "no influential points" rather than report phantom outliers.
    """
    notes: list[str] = []
    details: dict[str, Any] = {}
    n = int(used_index.size)
    if n < 2:
        notes.append("Influence check skipped: fewer than 2 observations.")
        details["skipped"] = True
        return [], notes, details

    # If the residual scale is effectively zero there is no noise in
    # the data; no observation can be flagged as influential.  This
    # is the standard interpretation in the literature: Cook's
    # distance is not meaningful for a perfect fit.
    s_resid = float(fit.s_resid)
    if not np.isfinite(s_resid) or s_resid <= 1e-10:
        details.update({
            "threshold": COOKS_THRESHOLD_FACTOR / float(n),
            "rule": f"cooks_d > {COOKS_THRESHOLD_FACTOR}/n",
            "n": n,
            "max_cooks_d": 0.0,
            "skipped": "s_resid_zero",
        })
        notes.append(
            "Influence check skipped: residual standard error is "
            "effectively zero (the data lie on the fitted line). "
            "Cook's distance is not meaningful in this regime."
        )
        return [], notes, details

    try:
        model = _refit_ols_for_influence(data, used_index, fit)
        cooks_d, _ = model.get_influence().cooks_distance
    except Exception as exc:  # pragma: no cover - defensive
        notes.append(
            f"Influence check failed unexpectedly: {exc!r}. "
            "Treat as inconclusive."
        )
        details["skipped"] = True
        return [], notes, details

    cooks_d = np.asarray(cooks_d, dtype=float)
    threshold = COOKS_THRESHOLD_FACTOR / float(n)
    flagged_local = np.where(cooks_d > threshold)[0]
    flagged_global = used_index[flagged_local].tolist()

    details.update({
        "threshold": float(threshold),
        "rule": f"cooks_d > {COOKS_THRESHOLD_FACTOR}/n",
        "n": n,
        "max_cooks_d": float(np.max(cooks_d)) if cooks_d.size else 0.0,
    })

    if flagged_global:
        notes.append(
            f"Influence check: {len(flagged_global)} observation(s) "
            f"have Cook's distance > {COOKS_THRESHOLD_FACTOR}/n = "
            f"{threshold:.4f} (row indices {flagged_global}). "
            "A single observation controls the fit. Consider a "
            "sensitivity analysis with and without these points; "
            "do not auto-exclude."
        )

    return [int(i) for i in flagged_global], notes, details


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_diagnostics(fit: FitResult, data: ValidatedData) -> DiagnosticsResult:
    """Run linearity, homoscedasticity, normality, and influence
    checks on the residuals of ``fit``.

    Parameters
    ----------
    fit:
        A :class:`~openpharmastability.contracts.FitResult` as
        produced by :mod:`openpharmastability.stats.regression`.
        All three model kinds (POOLED, COMMON_SLOPE, SEPARATE) are
        supported; the residuals are computed against the right
        per-batch predictions.
    data:
        A :class:`~openpharmastability.contracts.ValidatedData` for
        the same data the fit was built on.  Only the
        ``batch``/``time_months``/``value`` columns are consulted.

    Returns
    -------
    :class:`~openpharmastability.contracts.DiagnosticsResult`
        A record of every check's verdict, with enough detail
        (p-values, test statistics, Cook's distance threshold) to be
        surfaced in the report.  This function NEVER raises on a
        fitted model: any internal exception is caught, recorded in
        ``notes``, and the corresponding check is reported as
        "ok=True" with a "skipped" / "inconclusive" annotation.
    """
    notes: list[str] = []
    details: dict[str, Any] = {
        "model_kind": fit.kind.value,
        "df_resid": int(fit.df_resid),
    }

    # Residual construction.  Defensive: even if everything else
    # fails, return a non-throwing DiagnosticsResult.
    try:
        resid, used_index = _compute_residuals(fit, data)
        t, yhat, used_index2 = _yhat_values(fit, data)
        # The two index arrays must agree; if not, the data layer is
        # in a strange state.  Prefer the residual computation.
        if not np.array_equal(used_index, used_index2):
            used_index = used_index
    except Exception as exc:  # pragma: no cover - defensive
        notes.append(f"Diagnostics could not compute residuals: {exc!r}.")
        return DiagnosticsResult(
            linearity_ok=True,
            homoscedastic_ok=True,
            normal_resid_ok=True,
            influential_points=[],
            notes=notes,
            details={**details, "skipped": True},
        )

    n = int(resid.size)

    # 1) Linearity
    try:
        lin_ok, lin_notes, lin_details = _check_linearity(
            data, fit, t, yhat, used_index,
        )
    except Exception as exc:  # pragma: no cover - defensive
        lin_ok, lin_notes, lin_details = True, [f"Linearity check failed: {exc!r}."], {"skipped": True}
    notes.extend(lin_notes)
    details["linearity"] = lin_details

    # 2) Homoscedasticity
    try:
        homo_ok, homo_notes, homo_details = _check_homoscedasticity(
            resid, t, yhat, n,
        )
    except Exception as exc:  # pragma: no cover - defensive
        homo_ok, homo_notes, homo_details = True, [f"Homoscedasticity check failed: {exc!r}."], {"skipped": True}
    notes.extend(homo_notes)
    details["homoscedasticity"] = homo_details

    # 3) Normality
    try:
        norm_ok, norm_notes, norm_details = _check_normality(resid)
    except Exception as exc:  # pragma: no cover - defensive
        norm_ok, norm_notes, norm_details = True, [f"Normality check failed: {exc!r}."], {"skipped": True}
    notes.extend(norm_notes)
    details["normality"] = norm_details

    # 4) Influence
    try:
        influential, inf_notes, inf_details = _check_influence(
            data, fit, used_index, resid,
        )
    except Exception as exc:  # pragma: no cover - defensive
        influential, inf_notes, inf_details = [], [f"Influence check failed: {exc!r}."], {"skipped": True}
    notes.extend(inf_notes)
    details["influence"] = inf_details

    return DiagnosticsResult(
        linearity_ok=bool(lin_ok),
        homoscedastic_ok=bool(homo_ok),
        normal_resid_ok=bool(norm_ok),
        influential_points=list(influential),
        notes=notes,
        details=details,
    )


__all__ = ["run_diagnostics", "COOKS_THRESHOLD_FACTOR"]
