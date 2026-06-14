"""Tests for the numerical crossing solver (stats.bounds.find_crossing).

Covers the four documented statuses:
  - CROSSED
  - NO_CROSSING
  - FAIL_AT_BASELINE
  - FLAT_OR_OPPOSITE

For the CROSSED case we verify the solver agrees with a hand-rolled
``scipy.optimize.brentq`` call to tight tolerance.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import brentq
from scipy.stats import t as student_t

from openpharmastability.contracts import (
    CrossingStatus,
    Direction,
    ModelKind,
    ONE_SIDED_T_QUANTILE,
    ValidatedData,
)
from openpharmastability.stats.bounds import (
    confidence_bound,
    find_crossing,
)
from openpharmastability.stats.regression import fit_models


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_data(time_points, intercepts, slope=-0.5, sd=0.3, seed=20260113):
    """Synthetic decreasing assay over multiple batches."""
    rng = np.random.default_rng(seed)
    rows = []
    for batch, b0 in intercepts.items():
        for t in time_points:
            rows.append(
                {
                    "batch": batch,
                    "time_months": t,
                    "value": b0 + slope * t + float(rng.normal(0.0, sd)),
                }
            )
    return pd.DataFrame(rows)


def _validate(df, lower_spec=90.0, upper_spec=110.0, direction=Direction.DECREASING):
    return ValidatedData(
        df=df,
        attribute="assay",
        condition="25C/60RH",
        direction=direction,
        lower_spec=lower_spec,
        upper_spec=upper_spec,
        n_batches=df["batch"].nunique(),
        time_points=sorted(df["time_months"].unique().tolist()),
    )


# ---------------------------------------------------------------------------
# Hand-rolled reference solver
# ---------------------------------------------------------------------------


def _ref_crossing(fit, data, horizon, side="lower"):
    """Reproduce the math by hand: brentq on the bound curve.

    Used as the golden reference for the CROSSED case.
    """
    spec = data.lower_spec if side == "lower" else data.upper_spec

    def f(t):
        return confidence_bound(fit, t, side) - spec

    f_lo = f(0.0)
    f_hi = f(horizon)
    if f_lo * f_hi >= 0.0:
        return None
    return float(brentq(f, 0.0, horizon, xtol=1e-10, rtol=1e-12, maxiter=200))


# ---------------------------------------------------------------------------
# CROSSED
# ---------------------------------------------------------------------------


def test_crossing_crossed_pooled():
    """Standard decreasing assay crosses the lower spec in [0, 60]."""
    df = _make_data(
        time_points=(0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0),
        intercepts={"B1": 100.0, "B2": 99.0, "B3": 101.0},
        slope=-0.5,
        sd=0.3,
    )
    data = _validate(df)
    fit = fit_models(data)[ModelKind.POOLED]
    res = find_crossing(fit, data, horizon=120.0)
    assert res.status is CrossingStatus.CROSSED
    assert res.crossing_months is not None
    # Hand-rolled reference solver, tight tolerance.
    expected = _ref_crossing(fit, data, horizon=120.0, side="lower")
    assert expected is not None
    assert math.isclose(res.crossing_months, expected, rel_tol=1e-8, abs_tol=1e-6)


def test_crossing_crossed_common_slope_governing_batch_recorded():
    """Multi-batch model: governing batch is the worst (earliest)."""
    df = _make_data(
        time_points=(0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0),
        intercepts={"B1": 100.0, "B2": 96.0, "B3": 101.0},
        slope=-0.5,
        sd=0.3,
    )
    data = _validate(df)
    fit = fit_models(data)[ModelKind.COMMON_SLOPE]
    res = find_crossing(fit, data, horizon=120.0)
    assert res.status is CrossingStatus.CROSSED
    assert res.governing_batch is not None
    # B2 has the lowest intercept, so its curve is lowest; it should
    # be the governing batch.
    assert res.governing_batch == "B2"


# ---------------------------------------------------------------------------
# NO_CROSSING
# ---------------------------------------------------------------------------


def test_crossing_no_crossing_when_stable_too_high_lower_spec():
    """Stable assay well above the lower spec -> no crossing in horizon."""
    df = _make_data(
        time_points=(0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0),
        intercepts={"B1": 105.0, "B2": 106.0, "B3": 104.0},
        slope=-0.05,  # very slow decline
        sd=0.1,
    )
    # Spec is far below the curve.
    data = _validate(df, lower_spec=70.0)
    fit = fit_models(data)[ModelKind.POOLED]
    res = find_crossing(fit, data, horizon=120.0)
    assert res.status is CrossingStatus.NO_CROSSING
    assert res.crossing_months is None


# ---------------------------------------------------------------------------
# FAIL_AT_BASELINE
# ---------------------------------------------------------------------------


def test_crossing_fail_at_baseline():
    """The lower bound at t=0 is already at/past the lower spec."""
    df = _make_data(
        time_points=(0.0, 3.0, 6.0, 9.0, 12.0),
        intercepts={"B1": 89.0, "B2": 88.0, "B3": 90.0},  # below spec
        slope=-0.5,
        sd=0.05,
    )
    data = _validate(df, lower_spec=90.0)
    fit = fit_models(data)[ModelKind.POOLED]
    res = find_crossing(fit, data, horizon=120.0)
    assert res.status is CrossingStatus.FAIL_AT_BASELINE
    assert res.crossing_months == 0.0


# ---------------------------------------------------------------------------
# FLAT_OR_OPPOSITE
# ---------------------------------------------------------------------------


def test_crossing_flat_or_opposite_decreasing_with_zero_slope():
    """Declared DECREASING but the fitted slope is exactly 0 -> flat_or_opposite.

    Use noise-free data so the OLS slope is exactly 0, not ~0.
    """
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0):
            rows.append(
                {
                    "batch": batch,
                    "time_months": t,
                    "value": 100.0,  # perfectly flat
                }
            )
    df = pd.DataFrame(rows)
    data = _validate(df)
    fit = fit_models(data)[ModelKind.POOLED]
    res = find_crossing(fit, data, horizon=120.0)
    assert res.status is CrossingStatus.FLAT_OR_OPPOSITE
    assert res.crossing_months is None


def test_crossing_flat_or_opposite_decreasing_with_positive_slope():
    """Declared DECREASING but the fitted slope is positive -> flat_or_opposite.

    Use noise-free data so the slope is exactly +0.05, not +0.05 +/- noise.
    """
    rows = []
    for batch, b0 in (("B1", 95.0), ("B2", 96.0), ("B3", 94.0)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0):
            rows.append(
                {
                    "batch": batch,
                    "time_months": t,
                    "value": b0 + 0.05 * t,  # exact positive slope
                }
            )
    df = pd.DataFrame(rows)
    data = _validate(df)
    fit = fit_models(data)[ModelKind.POOLED]
    res = find_crossing(fit, data, horizon=120.0)
    assert res.status is CrossingStatus.FLAT_OR_OPPOSITE
