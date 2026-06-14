"""Golden-file test: end-to-end math on a frozen 3-batch assay dataset.

The expected values in ``examples/assay_3batch.expected.json`` were
computed **independently** with plain numpy + scipy.stats.t (no use of
this package's code). This test exercises the data layer, the stats
core, and the poolability test, and asserts they reproduce the frozen
values within a tight tolerance.

The engine integration test (``test_analyze_matches_expected``) is in
``test_engine.py`` and runs once the engine is built in Wave 2.
"""
from __future__ import annotations

import json
import math
import os
import pathlib

import pytest

from openpharmastability.contracts import (
    Direction,
    ModelKind,
)
from openpharmastability.data.io import load_csv
from openpharmastability.data.schema import validate_and_select
from openpharmastability.stats.bounds import confidence_bound, find_crossing
from openpharmastability.stats.poolability import decide_poolability
from openpharmastability.stats.regression import fit_models


ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "examples" / "assay_3batch.csv"
EXPECTED_PATH = ROOT / "examples" / "assay_3batch.expected.json"


@pytest.fixture(scope="module")
def expected():
    with open(EXPECTED_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def validated():
    df = load_csv(str(CSV_PATH))
    return validate_and_select(
        df, attribute="assay", condition="25C/60RH"
    )


# ---------------------------------------------------------------------------
# 1. Dataset shape matches the manifest
# ---------------------------------------------------------------------------


def test_dataset_shape(expected):
    df = load_csv(str(CSV_PATH))
    assert len(df) == expected["n_observations"]
    assert df["batch"].nunique() == expected["n_batches"]
    assert sorted(df["time_months"].unique().tolist()) == expected["time_points"]


# ---------------------------------------------------------------------------
# 2. Pooled OLS matches the independent reference
# ---------------------------------------------------------------------------


def test_pooled_fit_matches_expected(validated, expected):
    fits = fit_models(validated)
    pooled = fits[ModelKind.POOLED]
    ef = expected["pooled_fit"]
    assert math.isclose(pooled.params["b0"], ef["b0"], rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(pooled.params["b1"], ef["b1"], rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(pooled.s_resid, ef["s_resid"], rel_tol=1e-9, abs_tol=1e-9)
    assert pooled.df_resid == ef["df_resid"]
    assert math.isclose(pooled.design["tbar"], ef["tbar"], rel_tol=1e-12, abs_tol=1e-12)
    assert math.isclose(pooled.design["Sxx"], ef["Sxx"], rel_tol=1e-9, abs_tol=1e-9)
    assert pooled.design["n"] == ef["n"]


# ---------------------------------------------------------------------------
# 3. T-multiplier uses 0.95 (NOT 0.975) and the bound at tbar matches
# ---------------------------------------------------------------------------


def test_bound_uses_t_quantile_0_95(validated, expected):
    fits = fit_models(validated)
    pooled = fits[ModelKind.POOLED]
    ef = expected["pooled_fit"]
    # The bound at tbar is yhat(tbar) - t.ppf(0.95, df) * s / sqrt(n).
    tbar = pooled.design["tbar"]
    n = pooled.design["n"]
    s = pooled.s_resid
    yhat = pooled.fitted_fn(tbar)
    expected_lower = yhat - ef["t_multiplier_one_sided_95"] * s / math.sqrt(n)
    got_lower = confidence_bound(pooled, tbar, "lower")
    assert math.isclose(got_lower, expected_lower, rel_tol=1e-10, abs_tol=1e-10)
    # And the expected multiplier must be 0.95, not 0.975.
    from scipy.stats import t as student_t
    assert math.isclose(
        ef["t_multiplier_one_sided_95"],
        student_t.ppf(0.95, ef["df_resid"]),
        rel_tol=1e-12, abs_tol=1e-12,
    )
    assert not math.isclose(
        ef["t_multiplier_one_sided_95"],
        student_t.ppf(0.975, ef["df_resid"]),
        rel_tol=1e-3,
    )


# ---------------------------------------------------------------------------
# 4. Crossing time and shelf life match the independent reference
# ---------------------------------------------------------------------------


def test_crossing_matches_expected(validated, expected):
    """The POOLED model's crossing matches the POOLED section of the
    golden (NOT the shelf_life section, which is the COMMON_SLOPE
    crossing — that is checked in test_engine.py).
    """
    fits = fit_models(validated)
    pooled = fits[ModelKind.POOLED]
    res = find_crossing(pooled, validated, horizon=60.0)
    from openpharmastability.contracts import CrossingStatus
    assert res.status is CrossingStatus.CROSSED
    expected_pooled_crossing = expected["pooled_fit"]["crossing_lower_spec_90_months"]
    assert math.isclose(
        res.crossing_months,
        expected_pooled_crossing,
        rel_tol=1e-7, abs_tol=1e-6,
    )
    # The bound at the reported crossing time should be 90.0 (the spec).
    b = confidence_bound(pooled, res.crossing_months, "lower")
    assert math.isclose(b, validated.lower_spec, rel_tol=1e-6, abs_tol=1e-6)


def test_supported_shelf_life_is_floor_of_crossing(validated, expected):
    """The POOLED model's crossing rounds down to the POOLED shelf
    life in the golden (not the engine's COMMON_SLOPE shelf life,
    which is checked in test_engine.py).
    """
    fits = fit_models(validated)
    pooled = fits[ModelKind.POOLED]
    res = find_crossing(pooled, validated, horizon=60.0)
    expected_pooled_shelf = expected["pooled_fit"]["supported_shelf_life_rounded_down"]
    got_shelf = int(math.floor(res.crossing_months))
    assert got_shelf == expected_pooled_shelf
    # And the bound at the rounded-down month must still be at/past the spec.
    b_at_shelf = confidence_bound(pooled, float(expected_pooled_shelf), "lower")
    assert b_at_shelf >= validated.lower_spec - 1e-9


# ---------------------------------------------------------------------------
# 5. Poolability on this dataset should be PARTIAL (common slope, diff intercepts)
# ---------------------------------------------------------------------------


def test_poolability_decision_on_golden(validated):
    fits = fit_models(validated)
    pool = decide_poolability(fits, validated)
    from openpharmastability.contracts import Poolability
    # The data was generated with a common slope (-0.5) but different
    # intercepts (100/99/101). The slopes test should NOT reject, the
    # intercepts test SHOULD reject -> PARTIAL.
    assert pool.decision is Poolability.PARTIAL
    assert pool.p_slopes > pool.alpha
    assert pool.p_intercepts is not None and pool.p_intercepts < pool.alpha
