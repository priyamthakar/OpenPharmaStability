"""Tests for ``openpharmastability.stats.poolability.test_poolability``.

The 3-step nested ANCOVA must return one of the three decisions:

* :data:`Poolability.FULL` when every batch has the same slope **and**
  the same intercept (within sampling error).
* :data:`Poolability.PARTIAL` when batches share a common slope but
  have measurably different intercepts.
* :data:`Poolability.NONE` when batches have measurably different
  slopes.

Each fixture in this file targets one decision. The fixtures are
constructed so the decision is unambiguous at α = 0.25; we also
double-check the per-step p-values for sanity.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from openpharmastability.contracts import (
    Direction,
    Poolability,
    ValidatedData,
)
from openpharmastability.stats.poolability import test_poolability as run_poolability
from openpharmastability.stats.regression import fit_models


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _vd(rows: list[dict]) -> ValidatedData:
    """Wrap a list of dicts in a :class:`ValidatedData` with a
    standard 25C/60RH / assay / decreasing context.
    """
    df = pd.DataFrame(rows)
    return ValidatedData(
        df=df,
        attribute="assay",
        condition="25C/60RH",
        direction=Direction.DECREASING,
        lower_spec=90.0,
        upper_spec=110.0,
        n_batches=int(df["batch"].nunique()),
        time_points=sorted(df["time_months"].unique().tolist()),
        warnings=[],
    )


def _identical_slope_and_intercept() -> ValidatedData:
    """All batches have ``value = 100 - 0.25 * t``. Decision: FULL."""
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 12.0):
            rows.append(
                {
                    "batch": batch,
                    "condition": "25C/60RH",
                    "time_months": t,
                    "attribute": "assay",
                    "value": 100.0 - 0.25 * t,
                    "lower_spec": 90.0,
                    "upper_spec": 110.0,
                    "direction": "decreasing",
                }
            )
    return _vd(rows)


def _identical_slope_different_intercepts() -> ValidatedData:
    """All batches share slope -0.25 but intercepts differ by 1.0.
    Decision: PARTIAL.
    """
    rows = []
    intercepts = {"B1": 100.0, "B2": 101.0, "B3": 102.0}
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 12.0):
            rows.append(
                {
                    "batch": batch,
                    "condition": "25C/60RH",
                    "time_months": t,
                    "attribute": "assay",
                    "value": intercepts[batch] - 0.25 * t,
                    "lower_spec": 90.0,
                    "upper_spec": 110.0,
                    "direction": "decreasing",
                }
            )
    return _vd(rows)


def _clearly_different_slopes() -> ValidatedData:
    """Batches have slopes of -0.10, -0.40, -0.80. Decision: NONE."""
    rows = []
    intercepts = {"B1": 100.0, "B2": 100.0, "B3": 100.0}
    slopes = {"B1": -0.10, "B2": -0.40, "B3": -0.80}
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 12.0):
            rows.append(
                {
                    "batch": batch,
                    "condition": "25C/60RH",
                    "time_months": t,
                    "attribute": "assay",
                    "value": intercepts[batch] + slopes[batch] * t,
                    "lower_spec": 90.0,
                    "upper_spec": 110.0,
                    "direction": "decreasing",
                }
            )
    return _vd(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_poolability_full_when_all_batches_identical() -> None:
    v = _identical_slope_and_intercept()
    fits = fit_models(v)
    res = run_poolability(fits, v)
    assert res.decision is Poolability.FULL
    # Both steps must accept. p_slopes comes from the interaction
    # test; p_intercepts from the additive C(batch) test. With
    # identical data both are exactly 1.0 (degenerate ANOVA), but
    # we only require they are NOT significant.
    assert res.p_slopes > 0.25
    assert res.p_intercepts is not None and res.p_intercepts > 0.25
    assert res.alpha == pytest.approx(0.25)


def test_poolability_partial_when_intercepts_differ() -> None:
    v = _identical_slope_different_intercepts()
    fits = fit_models(v)
    res = run_poolability(fits, v)
    assert res.decision is Poolability.PARTIAL
    # Slopes must NOT be rejected (identical slopes), but
    # intercepts must be.
    assert res.p_slopes > 0.25
    assert res.p_intercepts is not None and res.p_intercepts < 0.25
    # The p_intercepts in this deterministic fixture is well
    # below the alpha; we don't pin the exact number (it depends
    # on the F-distribution implementation) but it should be tiny.
    assert res.p_intercepts < 0.001


def test_poolability_none_when_slopes_differ() -> None:
    v = _clearly_different_slopes()
    fits = fit_models(v)
    res = run_poolability(fits, v)
    assert res.decision is Poolability.NONE
    # The slopes test must reject, and p_intercepts must be None
    # (we never get to step 2 when step 1 rejects).
    assert res.p_slopes < 0.25
    assert res.p_intercepts is None


def test_poolability_custom_alpha_changes_decision_boundary() -> None:
    """The alpha is configurable; lowering it should NOT change the
    decision on these unambiguous fixtures.
    """
    v = _identical_slope_different_intercepts()
    fits = fit_models(v)
    res_default = run_poolability(fits, v)
    res_strict = run_poolability(fits, v, alpha=0.001)
    # Same decision (PARTIAL) regardless of alpha because the
    # p-values are either 1.0 or essentially 0 in this fixture.
    assert res_default.decision is Poolability.PARTIAL
    assert res_strict.decision is Poolability.PARTIAL
    # But the recorded alpha must differ.
    assert res_default.alpha == pytest.approx(0.25)
    assert res_strict.alpha == pytest.approx(0.001)


def test_poolability_records_notes_for_each_step() -> None:
    v = _identical_slope_and_intercept()
    fits = fit_models(v)
    res = run_poolability(fits, v)
    # Notes mention the slopes test (always) and the intercepts
    # test (since step 1 did not reject).
    joined = " | ".join(res.notes)
    assert "step1 slopes" in joined
    assert "step2 intercepts" in joined


def test_poolability_requires_separate_and_common_slope_fits() -> None:
    """If the caller passes an incomplete ``fits`` dict, the
    function must raise rather than silently mis-compute the test.
    """
    v = _identical_slope_and_intercept()
    # Hand-build a dict with only the POOLED fit to force the
    # validation branch.
    fits = fit_models(v)
    incomplete = {k: fits[k] for k in (next(iter(fits)),)}
    # Drop keys until only POOLED remains.
    incomplete = {k: v for k, v in fits.items() if k.value == "pooled"}
    assert incomplete  # sanity: the dict is non-empty
    with pytest.raises(ValueError, match="COMMON_SLOPE|SEPARATE"):
        run_poolability(incomplete, v)
