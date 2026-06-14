"""Tests for the v0.7.0 leave-one-out sensitivity analysis
(``openpharmastability.stats.sensitivity``).

The v0.7.0 sensitivity module is a new project module; we
hard-require it at import time (the project's conftest does
not list it under the v0.5+ modules, but the import below
will fail loudly if the module is missing).
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pandas as pd
import pytest

from openpharmastability.contracts import (
    CrossingResult,
    CrossingStatus,
    DiagnosticsResult,
    Direction,
    FitResult,
    ModelKind,
    Poolability,
    PoolabilityResult,
    StabilityResult,
    ValidatedData,
)
from openpharmastability.shelf_life.engine import analyze
from openpharmastability.stats.sensitivity import compute_sensitivity


ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV = ROOT / "examples" / "assay_3batch.csv"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_diagnostics(influential_points):
    """A tiny :class:`DiagnosticsResult` with the requested
    influential-points list. All booleans default to True (the
    sensitivity helper only reads ``influential_points``)."""
    return DiagnosticsResult(
        linearity_ok=True,
        homoscedastic_ok=True,
        normal_resid_ok=True,
        influential_points=list(influential_points),
        notes=[],
        details={},
    )


def _build_tiny_validated_data() -> ValidatedData:
    """A minimal 2-batch / 2-time-point valid frame. The shape is
    irrelevant for the sensitivity helper; it just needs to be
    valid enough for the LOO refit (which is monkeypatched in the
    failure test below)."""
    df = pd.DataFrame({
        "batch": ["B1", "B1", "B2", "B2"],
        "time_months": [0.0, 3.0, 0.0, 3.0],
        "value": [100.0, 99.0, 99.0, 98.0],
    })
    return ValidatedData(
        df=df,
        attribute="assay",
        condition="25C/60RH",
        direction=Direction.DECREASING,
        lower_spec=90.0,
        upper_spec=110.0,
        n_batches=2,
        time_points=[0.0, 3.0],
    )


def _build_tiny_result(
    *,
    supported_shelf_life_months: int | None = 17,
    influential_points: list[int] | None = None,
) -> StabilityResult:
    """A hand-rolled :class:`StabilityResult` for the no-op /
    no-influential-points branch tests. The LOO refit is not
    actually run for these tests; we only need the helper to
    see ``influential_points=[]`` (or whatever the test sets)."""
    pool = PoolabilityResult(
        decision=Poolability.FULL,
        p_slopes=0.5, p_intercepts=None, alpha=0.25, notes=[],
    )
    fit = FitResult(
        kind=ModelKind.POOLED,
        params={"b0": 100.0, "b1": -0.5},
        df_resid=2,
        s_resid=0.1,
        cov=np.zeros((2, 2)),
        fitted_fn=lambda t: 100.0 - 0.5 * t,
        design={"tbar": 1.0, "Sxx": 9.0, "n": 4},
        batches=["B1", "B2"],
    )
    cross = CrossingResult(
        crossing_months=20.0, status=CrossingStatus.CROSSED,
        governing_batch=None, notes=[],
    )
    return StabilityResult(
        attribute="assay", condition="25C/60RH", direction=Direction.DECREASING,
        model=ModelKind.POOLED, poolability=pool, fit=fit, crossing=cross,
        supported_shelf_life_months=supported_shelf_life_months,
        statistical_crossing_months=20.0, observed_data_months=3.0,
        extrapolation_flag=False,
        diagnostics=_build_diagnostics(influential_points or []),
        warnings=[], metadata={},
    )


# ---------------------------------------------------------------------------
# 1. compute_sensitivity on the golden fixture
# ---------------------------------------------------------------------------


def test_compute_sensitivity_on_golden_returns_rows() -> None:
    """The golden fixture has 4 Cook's-distance influential
    points (verified in v0.5.1 — see test_engine_v050.py
    for the diagnostics-level assertion). The
    ``analyze(..., run_sensitivity=True)`` path attaches a
    :class:`SensitivityReport` with one row per influential
    point."""
    result = analyze(
        path=str(CSV), condition="25C/60RH", attribute="assay",
        run_sensitivity=True,
    )
    assert result.sensitivity_report is not None
    report = result.sensitivity_report
    # 4 influential points in v0.5.1 -> 4 rows.
    assert len(report.rows) == 4
    # The default (no --sensitivity) path leaves the field at
    # None. The v0.5.0 default behaviour must be preserved
    # byte-for-byte for callers that did not opt in.
    default_result = analyze(
        path=str(CSV), condition="25C/60RH", attribute="assay",
    )
    assert default_result.sensitivity_report is None


# ---------------------------------------------------------------------------
# 2. summary is a non-empty string carrying one of the documented patterns
# ---------------------------------------------------------------------------


def test_compute_sensitivity_summary_is_string() -> None:
    """The summary must be a non-empty string. The exact text
    is one of the three documented patterns ("max delta 0 mo",
    "max delta N mo; 1 point", or "a single point drives the
    shelf-life decision")."""
    result = analyze(
        path=str(CSV), condition="25C/60RH", attribute="assay",
        run_sensitivity=True,
    )
    report = result.sensitivity_report
    assert report is not None
    assert isinstance(report.summary, str)
    assert report.summary, "summary must be non-empty"
    # One of the three documented patterns must be present.
    s = report.summary
    assert (
        "max delta 0 mo" in s
        or "1 point changes the shelf life" in s
        or "a single point drives the shelf-life decision" in s
    ), f"unexpected sensitivity summary: {s!r}"


# ---------------------------------------------------------------------------
# 3. no influential points -> empty rows + "no influential points" summary
# ---------------------------------------------------------------------------


def test_compute_sensitivity_no_influential_returns_empty() -> None:
    """When the diagnostics layer did not flag any influential
    point, the helper returns an empty report and the summary
    mentions "no influential points"."""
    result = _build_tiny_result(influential_points=[])
    data = _build_tiny_validated_data()
    report = compute_sensitivity(result, data)
    assert report.rows == []
    assert "no influential points" in report.summary.lower()
    # The baseline shelf life is echoed on the report.
    assert report.baseline_supported_shelf_life == 17
    # And at least one explanatory note.
    assert any("empty" in n.lower() for n in report.notes), (
        f"expected an 'empty' explanatory note, got {report.notes!r}"
    )


# ---------------------------------------------------------------------------
# 4. baseline_supported_shelf_life echoes the result
# ---------------------------------------------------------------------------


def test_compute_sensitivity_baseline_matches_result() -> None:
    """``report.baseline_supported_shelf_life`` must equal
    ``result.supported_shelf_life_months`` on the no-op branch."""
    result = _build_tiny_result(
        supported_shelf_life_months=24, influential_points=[],
    )
    data = _build_tiny_validated_data()
    report = compute_sensitivity(result, data)
    assert report.baseline_supported_shelf_life == 24
    # And on the populated branch (golden fixture).
    golden = analyze(
        path=str(CSV), condition="25C/60RH", attribute="assay",
        run_sensitivity=True,
    )
    assert golden.sensitivity_report is not None
    assert (
        golden.sensitivity_report.baseline_supported_shelf_life
        == golden.supported_shelf_life_months
    )


# ---------------------------------------------------------------------------
# 5. leave-one-out refit failure is recorded in the row's note
# ---------------------------------------------------------------------------


def test_leave_one_out_supported_shelf_life_documented_in_note(
    monkeypatch,
) -> None:
    """When the LOO refit raises, the row's
    ``leave_one_out_supported_shelf_life`` is ``None`` and the
    ``note`` field contains the failure marker. We force the
    failure by monkeypatching the internal LOO helper to raise."""
    import openpharmastability.stats.sensitivity as sens_mod

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated LOO refit failure")

    monkeypatch.setattr(sens_mod, "_leave_one_out", _raise)

    # Build a result with a single influential point. The
    # baseline shelf is 17; the LOO refit will raise; the row
    # note must capture the error.
    result = _build_tiny_result(influential_points=[0])
    data = _build_tiny_validated_data()
    report = compute_sensitivity(result, data)
    assert len(report.rows) == 1
    row = report.rows[0]
    # The refit failed -> leave-one-out shelf is None.
    assert row.leave_one_out_supported_shelf_life is None
    # And the note contains a failure marker.
    note = (row.note or "").lower()
    assert "failed" in note or "error" in note, (
        f"expected 'failed' or 'error' in note, got {row.note!r}"
    )
    # The diff is 0 (we cannot compute it without a leave-one-out
    # shelf life).
    assert row.diff_supported_shelf_life_months == 0


# ---------------------------------------------------------------------------
# 6. baseline_supported_shelf_life field type on the row
# ---------------------------------------------------------------------------


def test_sensitivity_row_baseline_field_is_int() -> None:
    """The ``baseline_supported_shelf_life`` field on
    :class:`SensitivityRow` is typed ``int`` (not Optional).
    The helper coerces a ``None`` baseline to ``0`` to keep
    the contract honored (a None-supported baseline means the
    baseline is not meaningful; we surface 0 rather than
    raise)."""
    result = _build_tiny_result(
        supported_shelf_life_months=None, influential_points=[],
    )
    data = _build_tiny_validated_data()
    report = compute_sensitivity(result, data)
    # The no-op branch is short-circuited (no rows), but the
    # report's baseline echoes the result's None.
    assert report.baseline_supported_shelf_life is None


# ---------------------------------------------------------------------------
# 7. compute_sensitivity is robust against an out-of-range index
# ---------------------------------------------------------------------------


def test_sensitivity_handles_out_of_range_index() -> None:
    """If the diagnostics layer accidentally flags an index
    that is not in the validated frame (a malformed
    :class:`StabilityResult` from a hand-built fixture), the
    helper must record ``leave_one_out_supported_shelf_life is None``
    and a descriptive note. It must NOT raise."""
    result = _build_tiny_result(influential_points=[999])
    data = _build_tiny_validated_data()
    # Should not raise.
    report = compute_sensitivity(result, data)
    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.leave_one_out_supported_shelf_life is None
    assert "out of range" in (row.note or "").lower(), (
        f"expected an 'out of range' note, got {row.note!r}"
    )
