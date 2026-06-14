"""Edge-case tests: no-crossing, fail-at-baseline, flat-or-opposite, plus
a few data-layer edge cases for the reportability of the engine.

These tests are *also* the integration proof that the data layer +
stats core + poolability + bounds + crossing chain works on the
hard cases the spec calls out.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from openpharmastability.contracts import (
    CrossingStatus,
    Direction,
    ModelKind,
    ValidatedData,
)
from openpharmastability.data.schema import validate_and_select
from openpharmastability.stats.bounds import confidence_bound, find_crossing
from openpharmastability.stats.poolability import decide_poolability
from openpharmastability.stats.regression import fit_models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_dataframe(rows):
    return pd.DataFrame(rows)


def _validate(df, **kwargs):
    return ValidatedData(
        df=df,
        attribute="assay",
        condition="25C/60RH",
        direction=kwargs.get("direction", Direction.DECREASING),
        lower_spec=kwargs.get("lower_spec", 90.0),
        upper_spec=kwargs.get("upper_spec", 110.0),
        n_batches=df["batch"].nunique(),
        time_points=sorted(df["time_months"].unique().tolist()),
    )


# ---------------------------------------------------------------------------
# 1. No crossing within horizon
# ---------------------------------------------------------------------------


def test_no_crossing_when_stable_above_lower_spec():
    """Stable assay well above the lower spec -> NO_CROSSING, no shelf life."""
    rows = []
    for batch, b0 in (("B1", 105.0), ("B2", 106.0), ("B3", 104.0)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": b0 - 0.05 * t,  # very slow decline
                "lower_spec": 70.0, "upper_spec": 120.0,
            })
    df = _build_dataframe(rows)
    data = _validate(df, lower_spec=70.0, upper_spec=120.0)
    fits = fit_models(data)
    res = find_crossing(fits[ModelKind.POOLED], data, horizon=60.0)
    assert res.status is CrossingStatus.NO_CROSSING
    assert res.crossing_months is None


# ---------------------------------------------------------------------------
# 2. Fail at baseline
# ---------------------------------------------------------------------------


def test_fail_at_baseline():
    """Bound at t=0 is already at/past the lower spec -> FAIL_AT_BASELINE."""
    rows = []
    for batch, b0 in (("B1", 89.0), ("B2", 88.0), ("B3", 90.0)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": b0 - 0.5 * t,  # no noise — bound will be below 90
                "lower_spec": 90.0, "upper_spec": 110.0,
            })
    df = _build_dataframe(rows)
    data = _validate(df)
    fits = fit_models(data)
    res = find_crossing(fits[ModelKind.POOLED], data, horizon=60.0)
    assert res.status is CrossingStatus.FAIL_AT_BASELINE
    assert res.crossing_months == 0.0


# ---------------------------------------------------------------------------
# 3. Flat / opposite slope
# ---------------------------------------------------------------------------


def test_flat_or_opposite_zero_slope():
    """Declared DECREASING but slope is exactly 0 -> FLAT_OR_OPPOSITE."""
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": 100.0,  # perfectly flat
                "lower_spec": 90.0, "upper_spec": 110.0,
            })
    df = _build_dataframe(rows)
    data = _validate(df)
    fits = fit_models(data)
    res = find_crossing(fits[ModelKind.POOLED], data, horizon=60.0)
    assert res.status is CrossingStatus.FLAT_OR_OPPOSITE
    assert res.crossing_months is None


def test_flat_or_opposite_positive_slope():
    """Declared DECREASING but slope is positive -> FLAT_OR_OPPOSITE."""
    rows = []
    for batch, b0 in (("B1", 95.0), ("B2", 96.0), ("B3", 94.0)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": b0 + 0.05 * t,  # positive slope
                "lower_spec": 90.0, "upper_spec": 110.0,
            })
    df = _build_dataframe(rows)
    data = _validate(df)
    fits = fit_models(data)
    res = find_crossing(fits[ModelKind.POOLED], data, horizon=60.0)
    assert res.status is CrossingStatus.FLAT_OR_OPPOSITE


# ---------------------------------------------------------------------------
# 4. Poolability edge cases
# ---------------------------------------------------------------------------


def test_poolability_full_when_batches_identical():
    """All batches with identical intercept and slope -> FULL.

    Add a tiny amount of noise (sd=0.05) so the F-test is numerically
    well-defined; on perfectly collinear data, the interaction F-test
    is 0/0 and statsmodels returns a fictitious p-value.
    """
    rng = np.random.default_rng(20260113)
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": 100.0 - 0.5 * t + float(rng.normal(0.0, 0.05)),
                "lower_spec": 90.0, "upper_spec": 110.0,
            })
    df = _build_dataframe(rows)
    data = _validate(df)
    fits = fit_models(data)
    pool = decide_poolability(fits, data)
    from openpharmastability.contracts import Poolability
    assert pool.decision is Poolability.FULL


def test_poolability_none_when_slopes_differ():
    """Clearly different slopes -> NONE (use per-batch fits)."""
    rows = []
    for batch, slope in (("B1", -0.5), ("B2", -1.0), ("B3", -0.3)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": 100.0 + slope * t,
                "lower_spec": 90.0, "upper_spec": 110.0,
            })
    df = _build_dataframe(rows)
    data = _validate(df)
    fits = fit_models(data)
    pool = decide_poolability(fits, data)
    from openpharmastability.contracts import Poolability
    assert pool.decision is Poolability.NONE
    assert pool.p_slopes < pool.alpha
