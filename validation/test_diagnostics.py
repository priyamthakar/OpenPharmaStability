"""Tests for the diagnostics module (stats.diagnostics)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from openpharmastability.contracts import (
    Direction,
    ModelKind,
    ValidatedData,
)
from openpharmastability.stats.diagnostics import run_diagnostics
from openpharmastability.stats.regression import fit_models


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_data(rows):
    df = pd.DataFrame(rows)
    return ValidatedData(
        df=df,
        attribute="assay",
        condition="25C/60RH",
        direction=Direction.DECREASING,
        lower_spec=90.0,
        upper_spec=110.0,
        n_batches=df["batch"].nunique(),
        time_points=sorted(df["time_months"].unique().tolist()),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_diagnostics_clean_linear_pooled_all_pass():
    """A clean linear 3-batch dataset should pass all four checks."""
    rng = np.random.default_rng(20260113)
    rows = []
    for b, b0 in (("B1", 100.0), ("B2", 99.0), ("B3", 101.0)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0):
            rows.append(
                {
                    "batch": b,
                    "time_months": t,
                    "value": b0 - 0.5 * t + float(rng.normal(0.0, 0.3)),
                }
            )
    data = _make_data(rows)
    fit = fit_models(data)[ModelKind.POOLED]
    res = run_diagnostics(fit, data)
    # Linearity, homoscedasticity, normality all pass.
    assert res.linearity_ok is True
    assert res.homoscedastic_ok is True
    assert res.normal_resid_ok is True
    # No point should be wildly influential on a clean linear fit.
    # End-of-study points can have higher leverage, so allow a small
    # number of Cook's-distance flags but not many.
    assert len(res.influential_points) <= 3
    # And the max Cook's d should be small (< 1) for a clean fit.
    if "influence" in res.details:
        max_d = res.details["influence"].get("max_cooks_d", 0.0)
        assert max_d < 1.0


def test_diagnostics_heteroscedastic_flagged():
    """Variance growing with time -> homoscedastic_ok should be False."""
    rng = np.random.default_rng(20260113)
    rows = []
    for b, b0 in (("B1", 100.0), ("B2", 99.0), ("B3", 101.0)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0):
            # SD scales with t.
            sd = 0.05 + 0.1 * t
            rows.append(
                {
                    "batch": b,
                    "time_months": t,
                    "value": b0 - 0.5 * t + float(rng.normal(0.0, sd)),
                }
            )
    data = _make_data(rows)
    fit = fit_models(data)[ModelKind.POOLED]
    res = run_diagnostics(fit, data)
    # The homoscedasticity test should detect this.
    assert res.homoscedastic_ok is False
    # A note should be present.
    assert any("homoscedast" in n.lower() or "variance" in n.lower() for n in res.notes)


def test_diagnostics_nonlinear_flagged():
    """A quadratic trend should be flagged as nonlinear."""
    rng = np.random.default_rng(20260113)
    rows = []
    for b, b0 in (("B1", 100.0), ("B2", 99.0), ("B3", 101.0)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0):
            # Quadratic in t — not linear.
            v = b0 - 0.5 * t + 0.05 * t * t + float(rng.normal(0.0, 0.3))
            rows.append({"batch": b, "time_months": t, "value": v})
    data = _make_data(rows)
    fit = fit_models(data)[ModelKind.POOLED]
    res = run_diagnostics(fit, data)
    # Linearity check should fail.
    assert res.linearity_ok is False
    # A note should mention nonlinearity or transform.
    assert any(
        kw in n.lower()
        for n in res.notes
        for kw in ("linear", "nonlinear", "transform", "quadratic", "lack-of-fit")
    )


def test_diagnostics_influential_outlier_flagged():
    """A single high-leverage outlier that controls the fit should be flagged."""
    rng = np.random.default_rng(20260113)
    rows = []
    for b, b0 in (("B1", 100.0), ("B2", 99.0), ("B3", 101.0)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0):
            rows.append(
                {
                    "batch": b,
                    "time_months": t,
                    "value": b0 - 0.5 * t + float(rng.normal(0.0, 0.1)),
                }
            )
    # Plant a wild outlier: a B1 point that should be ~94 but is 70.
    # Find the right row to overwrite (B1, t=24 is index ...; just push a
    # bad value at one of the high-leverage end-of-study points).
    for i, row in enumerate(rows):
        if row["batch"] == "B1" and row["time_months"] == 24.0:
            rows[i]["value"] = 60.0
            break
    data = _make_data(rows)
    fit = fit_models(data)[ModelKind.POOLED]
    res = run_diagnostics(fit, data)
    # The planted outlier should be flagged as influential.
    assert len(res.influential_points) >= 1
    # A note should mention influence.
    assert any("influenc" in n.lower() or "cooks" in n.lower() for n in res.notes)


def test_diagnostics_never_raises_on_tiny_data():
    """Diagnostics must NEVER raise, even on tiny data with few rows."""
    # Only 6 rows total, 2 batches, 2 time points. Everything should be
    # marked "ok" with "insufficient" notes rather than crash.
    rows = [
        {"batch": "B1", "time_months": 0.0, "value": 100.0},
        {"batch": "B1", "time_months": 3.0, "value": 99.0},
        {"batch": "B2", "time_months": 0.0, "value": 99.0},
        {"batch": "B2", "time_months": 3.0, "value": 98.0},
        # Filler rows so OLS has at least n > p.
        {"batch": "B1", "time_months": 6.0, "value": 97.0},
        {"batch": "B2", "time_months": 6.0, "value": 96.0},
    ]
    data = _make_data(rows)
    fit = fit_models(data)[ModelKind.POOLED]
    # Must not raise.
    res = run_diagnostics(fit, data)
    assert isinstance(res.linearity_ok, bool)
    assert isinstance(res.homoscedastic_ok, bool)
    assert isinstance(res.normal_resid_ok, bool)
    assert isinstance(res.influential_points, list)
    assert isinstance(res.notes, list)
