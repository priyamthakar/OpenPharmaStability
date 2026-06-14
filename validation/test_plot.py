"""Tests for the confidence-bound plot (plots.confidence_plot)."""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from openpharmastability.contracts import (
    CrossingResult,
    CrossingStatus,
    Direction,
    DiagnosticsResult,
    FitResult,
    ModelKind,
    Poolability,
    PoolabilityResult,
    StabilityResult,
    ValidatedData,
)
from openpharmastability.plots.confidence_plot import make_confidence_plot
from openpharmastability.stats.regression import fit_models


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_dataset(seed=20260113):
    rng = np.random.default_rng(seed)
    rows = []
    for batch, b0 in (("B1", 100.0), ("B2", 99.0), ("B3", 101.0)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0):
            rows.append(
                {
                    "batch": batch,
                    "time_months": t,
                    "value": b0 - 0.5 * t + float(rng.normal(0.0, 0.3)),
                }
            )
    df = pd.DataFrame(rows)
    data = ValidatedData(
        df=df,
        attribute="assay",
        condition="25C/60RH",
        direction=Direction.DECREASING,
        lower_spec=90.0,
        upper_spec=110.0,
        n_batches=3,
        time_points=[0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0],
    )
    return data


def _build_result(
    data: ValidatedData, model_kind: ModelKind, crossing: CrossingResult
) -> StabilityResult:
    fits = fit_models(data)
    fit = fits[model_kind]
    poolability = PoolabilityResult(
        decision=Poolability.FULL,
        p_slopes=0.7,
        p_intercepts=0.8,
        alpha=0.25,
        notes=["synthetic"],
    )
    diag = DiagnosticsResult(
        linearity_ok=True,
        homoscedastic_ok=True,
        normal_resid_ok=True,
        influential_points=[],
        notes=[],
        details={},
    )
    return StabilityResult(
        attribute="assay",
        condition="25C/60RH",
        direction=Direction.DECREASING,
        model=model_kind,
        poolability=poolability,
        fit=fit,
        crossing=crossing,
        supported_shelf_life_months=24,
        statistical_crossing_months=27.4,
        observed_data_months=24.0,
        extrapolation_flag=True,
        diagnostics=diag,
        warnings=[],
        metadata={"seed": 20260113, "tool_version": "0.1.0"},
        deliverable_term="shelf life",
        product_type="product",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_plot_writes_png(tmp_path):
    data = _build_dataset()
    crossing = CrossingResult(
        crossing_months=27.4, status=CrossingStatus.CROSSED, governing_batch=None,
        notes=[],
    )
    result = _build_result(data, ModelKind.POOLED, crossing)
    out = str(tmp_path / "plot.png")
    path = make_confidence_plot(result, data, out)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 1024  # at least 1KB
    assert path == os.path.abspath(out)


def test_plot_no_crossing_does_not_raise(tmp_path):
    data = _build_dataset()
    crossing = CrossingResult(
        crossing_months=None, status=CrossingStatus.NO_CROSSING,
        governing_batch=None, notes=[],
    )
    result = _build_result(data, ModelKind.POOLED, crossing)
    out = str(tmp_path / "plot_no_cross.png")
    path = make_confidence_plot(result, data, out)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 1024


def test_plot_fail_at_baseline_does_not_raise(tmp_path):
    data = _build_dataset()
    crossing = CrossingResult(
        crossing_months=0.0, status=CrossingStatus.FAIL_AT_BASELINE,
        governing_batch=None, notes=[],
    )
    result = _build_result(data, ModelKind.POOLED, crossing)
    out = str(tmp_path / "plot_fail.png")
    path = make_confidence_plot(result, data, out)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 1024


def test_plot_separate_model_does_not_raise(tmp_path):
    """Multi-batch SEPARATE model: per-batch fit lines + single
    worst-case band (regression test for the v0.3.0 bug where the
    same worst-case band was stacked once per batch in N colors)."""
    data = _build_dataset()
    crossing = CrossingResult(
        crossing_months=27.4, status=CrossingStatus.CROSSED, governing_batch="B2",
        notes=[],
    )
    result = _build_result(data, ModelKind.SEPARATE, crossing)
    out = str(tmp_path / "plot_sep.png")
    path = make_confidence_plot(result, data, out)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 1024


def test_plot_common_slope_does_not_raise(tmp_path):
    """Multi-batch COMMON_SLOPE model: per-batch fit lines + single
    worst-case band. Must not raise and must produce a non-empty PNG."""
    data = _build_dataset()
    crossing = CrossingResult(
        crossing_months=27.4, status=CrossingStatus.CROSSED, governing_batch="B1",
        notes=[],
    )
    result = _build_result(data, ModelKind.COMMON_SLOPE, crossing)
    out = str(tmp_path / "plot_cs.png")
    path = make_confidence_plot(result, data, out)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 1024


# ---------------------------------------------------------------------------
# v0.3.1: INCREASING-direction coverage
# ---------------------------------------------------------------------------


def _build_increasing_dataset(seed=20260114):
    """An INCREASING attribute (e.g. a degradant / impurity) with
    positive slope. ``upper_spec`` is the binding spec."""
    rng = np.random.default_rng(seed)
    rows = []
    for batch, b0 in (("B1", 0.05), ("B2", 0.08), ("B3", 0.06)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0):
            rows.append(
                {
                    "batch": batch,
                    "time_months": t,
                    "value": b0 + 0.02 * t + float(rng.normal(0.0, 0.01)),
                }
            )
    df = pd.DataFrame(rows)
    return ValidatedData(
        df=df,
        attribute="impurity",
        condition="25C/60RH",
        direction=Direction.INCREASING,
        lower_spec=0.0,
        upper_spec=1.0,
        n_batches=3,
        time_points=[0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0],
    )


def _build_increasing_result(data: ValidatedData) -> StabilityResult:
    fits = fit_models(data)
    fit = fits[ModelKind.POOLED]
    poolability = PoolabilityResult(
        decision=Poolability.FULL,
        p_slopes=0.7,
        p_intercepts=0.8,
        alpha=0.25,
        notes=["synthetic"],
    )
    diag = DiagnosticsResult(
        linearity_ok=True,
        homoscedastic_ok=True,
        normal_resid_ok=True,
        influential_points=[],
        notes=[],
        details={},
    )
    return StabilityResult(
        attribute="impurity",
        condition="25C/60RH",
        direction=Direction.INCREASING,
        model=ModelKind.POOLED,
        poolability=poolability,
        fit=fit,
        crossing=CrossingResult(
            crossing_months=None, status=CrossingStatus.NO_CROSSING,
            governing_batch=None, notes=[],
        ),
        supported_shelf_life_months=None,
        statistical_crossing_months=None,
        observed_data_months=24.0,
        extrapolation_flag=False,
        diagnostics=diag,
        warnings=[],
        metadata={"seed": 20260114, "tool_version": "0.3.1"},
        deliverable_term="shelf life",
        product_type="product",
    )


def test_plot_increasing_direction_does_not_raise(tmp_path):
    """INCREASING attributes (degradants, impurities) have the upper
    one-sided 95% bound as the binding one. The plot must render
    without error and produce a non-empty PNG — regression test for
    the v0.3.0 bug that hard-coded a 'lower' framing."""
    data = _build_increasing_dataset()
    result = _build_increasing_result(data)
    out = str(tmp_path / "plot_inc.png")
    path = make_confidence_plot(result, data, out)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 1024


def test_plot_increasing_separate_model_does_not_raise(tmp_path):
    """INCREASING + multi-batch SEPARATE: per-batch fit lines and a
    single worst-case band; the band label must reflect the upper
    critical bound. Must not raise."""
    data = _build_increasing_dataset()
    fits = fit_models(data)
    fit = fits[ModelKind.SEPARATE]
    poolability = PoolabilityResult(
        decision=Poolability.NONE,
        p_slopes=0.05,
        p_intercepts=0.3,
        alpha=0.25,
        notes=["synthetic"],
    )
    diag = DiagnosticsResult(
        linearity_ok=True, homoscedastic_ok=True, normal_resid_ok=True,
        influential_points=[], notes=[], details={},
    )
    result = StabilityResult(
        attribute="impurity",
        condition="25C/60RH",
        direction=Direction.INCREASING,
        model=ModelKind.SEPARATE,
        poolability=poolability,
        fit=fit,
        crossing=CrossingResult(
            crossing_months=None, status=CrossingStatus.NO_CROSSING,
            governing_batch=None, notes=[],
        ),
        supported_shelf_life_months=None,
        statistical_crossing_months=None,
        observed_data_months=24.0,
        extrapolation_flag=False,
        diagnostics=diag,
        warnings=[],
        metadata={"seed": 20260114, "tool_version": "0.3.1"},
        deliverable_term="shelf life",
        product_type="product",
    )
    out = str(tmp_path / "plot_inc_sep.png")
    path = make_confidence_plot(result, data, out)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 1024
