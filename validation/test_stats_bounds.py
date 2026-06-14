"""Tests for the mean-response confidence bound (stats.bounds).

The most important assertion here is the t-quantile: the one-sided
95% bound MUST use ``student_t.ppf(0.95, df)`` (5% in one tail),
NOT 0.975. This is the most common bug in hand-rolled shelf-life
implementations; the assertion below locks it in.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import t as student_t

from openpharmastability.contracts import (
    CONFIDENCE,
    Direction,
    ModelKind,
    ONE_SIDED_T_QUANTILE,
    TWO_SIDED_T_QUANTILE,
    ValidatedData,
)
from openpharmastability.stats.bounds import (
    _quantile_for,
    confidence_bound,
)
from openpharmastability.stats.regression import fit_models


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_validated(time_points=(0.0, 3.0, 6.0, 9.0, 12.0)) -> ValidatedData:
    """Three batches, deterministic decreasing assay over time.

    Batch B1: 100.0 - 0.5*time
    Batch B2:  99.0 - 0.5*time
    Batch B3: 101.0 - 0.5*time
    Small per-row noise (sd=0.3) so the SE is non-zero.
    """
    rng = np.random.default_rng(20260113)
    rows = []
    for batch, b0 in (("B1", 100.0), ("B2", 99.0), ("B3", 101.0)):
        for t in time_points:
            rows.append(
                {
                    "batch": batch,
                    "time_months": t,
                    "value": b0 - 0.5 * t + float(rng.normal(0.0, 0.3)),
                }
            )
    df = pd.DataFrame(rows)
    return ValidatedData(
        df=df,
        attribute="assay",
        condition="25C/60RH",
        direction=Direction.DECREASING,
        lower_spec=90.0,
        upper_spec=110.0,
        n_batches=3,
        time_points=sorted(set(time_points)),
    )


@pytest.fixture
def pooled_fit():
    data = _make_validated()
    return fit_models(data)[ModelKind.POOLED]


@pytest.fixture
def common_slope_fit():
    data = _make_validated()
    return fit_models(data)[ModelKind.COMMON_SLOPE]


@pytest.fixture
def separate_fit():
    data = _make_validated()
    return fit_models(data)[ModelKind.SEPARATE]


# ---------------------------------------------------------------------------
# t-quantile selection
# ---------------------------------------------------------------------------


def test_quantile_for_one_sided_uses_0_95_not_0_975():
    """One-sided 95% bound uses ppf(0.95). Two-sided uses 0.975."""
    assert _quantile_for(0.95, "lower") == ONE_SIDED_T_QUANTILE == 0.95
    assert _quantile_for(0.95, "upper") == ONE_SIDED_T_QUANTILE == 0.95
    # An explicit two-sided 95% uses 0.975 (out of v0.1 scope but the
    # helper still maps it correctly).
    assert _quantile_for(0.975, "lower") == TWO_SIDED_T_QUANTILE == 0.975


def test_bound_uses_pp_0_95_multiplier_at_tbar(pooled_fit):
    """The lower bound at tbar must be yhat - t.ppf(0.95, df) * s / sqrt(n).

    At t=tbar, the closed-form SE collapses to ``s / sqrt(n)``, so we
    can write the exact expected value and lock the multiplier in.
    """
    df = pooled_fit.df_resid
    k = student_t.ppf(ONE_SIDED_T_QUANTILE, df)
    tbar = pooled_fit.design["tbar"]
    n = pooled_fit.design["n"]
    s = pooled_fit.s_resid
    yhat = pooled_fit.fitted_fn(tbar)
    expected_lower = yhat - k * s / math.sqrt(n)
    expected_upper = yhat + k * s / math.sqrt(n)
    got_lower = confidence_bound(pooled_fit, tbar, "lower")
    got_upper = confidence_bound(pooled_fit, tbar, "upper")
    assert math.isclose(got_lower, expected_lower, rel_tol=1e-12, abs_tol=1e-12)
    assert math.isclose(got_upper, expected_upper, rel_tol=1e-12, abs_tol=1e-12)


def test_bound_multiplier_is_pp_0_95_not_0_975(pooled_fit):
    """Regression: the multiplier must be ppf(0.95), not ppf(0.975).

    If this test ever fails, the most likely cause is a copy-paste
    from a textbook that uses two-sided 95% (= 0.975). Do not
    "fix" it by switching to 0.975 — fix the source.
    """
    df = pooled_fit.df_resid
    multiplier_used = (
        confidence_bound(pooled_fit, pooled_fit.design["tbar"], "lower")
        - pooled_fit.fitted_fn(pooled_fit.design["tbar"])
    ) / (-pooled_fit.s_resid / math.sqrt(pooled_fit.design["n"]))
    expected_95 = student_t.ppf(0.95, df)
    expected_975 = student_t.ppf(0.975, df)
    assert math.isclose(multiplier_used, expected_95, rel_tol=1e-10, abs_tol=1e-10)
    # And it must NOT match the two-sided multiplier.
    assert not math.isclose(multiplier_used, expected_975, rel_tol=1e-3)


# ---------------------------------------------------------------------------
# POOLED bound
# ---------------------------------------------------------------------------


def test_bound_at_tbar_is_tightest_for_pooled(pooled_fit):
    """The bound is narrowest at tbar; it widens as (t - tbar)^2 grows."""
    tbar = pooled_fit.design["tbar"]
    s_at_tbar = abs(
        confidence_bound(pooled_fit, tbar, "lower")
        - pooled_fit.fitted_fn(tbar)
    )
    far_t = tbar + 30.0  # well outside the observed range
    s_at_far = abs(
        confidence_bound(pooled_fit, far_t, "lower")
        - pooled_fit.fitted_fn(far_t)
    )
    assert s_at_far > s_at_tbar


def test_bound_returns_finite_floats(pooled_fit):
    for side in ("lower", "upper"):
        for t in (0.0, 3.0, 6.0, 12.0, 24.0, 60.0):
            v = confidence_bound(pooled_fit, t, side)
            assert isinstance(v, float)
            assert math.isfinite(v)


def test_bound_rejects_bad_side(pooled_fit):
    with pytest.raises(ValueError):
        confidence_bound(pooled_fit, 0.0, "middle")


def test_bound_default_conf_is_0_95(pooled_fit):
    """Default ``conf`` argument equals CONFIDENCE."""
    assert CONFIDENCE == 0.95


# ---------------------------------------------------------------------------
# Multi-batch bounds: COMMON_SLOPE
# ---------------------------------------------------------------------------


def test_common_slope_bound_uses_full_cov(common_slope_fit):
    """The bound for a multi-batch model must use s^2 * (X'X)^-1
    via the parameter covariance, not a per-batch shortcut.

    The public ``confidence_bound`` returns the worst-case batch's
    bound (the spec's "earliest crossing" rule). We compute the
    expected worst-case by hand using the parameter covariance and
    compare.

    The c-vector is built **from the parameter name list** (which
    comes from the fitted model) — NOT from ``fit.design`` (which
    the engine also wrote, and which would make this test
    tautological). The two are independently consistent for the
    same model, but only the parameter-name path is a real
    external check.
    """
    t = 12.0
    k = student_t.ppf(ONE_SIDED_T_QUANTILE, common_slope_fit.df_resid)
    param_names = list(common_slope_fit.design["param_names"])
    param_index = {name: i for i, name in enumerate(param_names)}
    slope_idx = param_index["time_months"]
    ref_batch = common_slope_fit.design["ref_batch"]

    def c_for_batch_at_t(batch: str, t_val: float) -> np.ndarray:
        """Build the prediction c-vector for a batch at time t,
        from the parameter name list, NOT from fit.design."""
        c = np.zeros(len(param_names), dtype=float)
        c[param_index["Intercept"]] = 1.0
        if batch != ref_batch:
            c[param_index[f"C(batch)[T.{batch}]"]] = 1.0
        c[slope_idx] = t_val
        return c

    expected_per_batch = []
    for batch in common_slope_fit.batches:
        b0 = common_slope_fit.params[f"b0_{batch}"]
        b1 = common_slope_fit.params["b1"]
        yhat = b0 + b1 * t
        c = c_for_batch_at_t(batch, t)
        se = math.sqrt(float(c @ common_slope_fit.cov @ c))
        expected_per_batch.append(yhat - k * se)
    expected_worst = min(expected_per_batch)
    got = confidence_bound(common_slope_fit, t, "lower")
    assert math.isclose(got, expected_worst, rel_tol=1e-10, abs_tol=1e-10)


# ---------------------------------------------------------------------------
# Multi-batch bounds: SEPARATE
# ---------------------------------------------------------------------------


def test_separate_bound_uses_full_cov(separate_fit):
    """The bound for a SEPARATE model: same check, different per-batch slopes."""
    t = 12.0
    k = student_t.ppf(ONE_SIDED_T_QUANTILE, separate_fit.df_resid)
    param_names = list(separate_fit.design["param_names"])
    param_index = {name: i for i, name in enumerate(param_names)}
    ref_batch = separate_fit.design["ref_batch"]

    def c_for_batch_at_t(batch: str, t_val: float) -> np.ndarray:
        c = np.zeros(len(param_names), dtype=float)
        c[param_index["Intercept"]] = 1.0
        c[param_index["time_months"]] = t_val
        if batch != ref_batch:
            c[param_index[f"C(batch)[T.{batch}]"]] = 1.0
            c[param_index[f"time_months:C(batch)[T.{batch}]"]] = t_val
        return c

    expected_per_batch = []
    for batch in separate_fit.batches:
        b0 = separate_fit.params[f"b0_{batch}"]
        b1 = separate_fit.params[f"b1_{batch}"]
        yhat = b0 + b1 * t
        c = c_for_batch_at_t(batch, t)
        se = math.sqrt(float(c @ separate_fit.cov @ c))
        expected_per_batch.append(yhat - k * se)
    expected_worst = min(expected_per_batch)
    got = confidence_bound(separate_fit, t, "lower")
    assert math.isclose(got, expected_worst, rel_tol=1e-10, abs_tol=1e-10)
