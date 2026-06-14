"""Tests for ``openpharmastability.regulatory.reduced_design.detect_reduced_design``.

These tests pin the spec from ``NEXT_STEPS.md`` §5.2:

* Full-factorial frame (every batch × time × condition cell present)
  reports neither bracketing nor matrixing.
* Sparse frame (some cells dropped) is flagged as matrixed with a
  non-empty ``missing_cells`` list.
* Frame with a factor column whose distinct values are the global
  min AND max only is flagged as bracketed.
* Frame with no ``factor_columns`` argument is not flagged for
  bracketing even on a sparse frame.
* Empty / malformed frame returns the safe sentinel without raising.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from openpharmastability.contracts import ReducedDesignReport
from openpharmastability.regulatory.reduced_design import detect_reduced_design


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _full_factorial_fixture() -> pd.DataFrame:
    """3 batches × 4 times × 2 conditions, one row per cell, no factor cols."""
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 12.0):
            for cond in ("25C/60RH", "40C/75RH"):
                rows.append({
                    "batch": batch,
                    "time_months": t,
                    "condition": cond,
                    "value": 100.0 - 0.1 * t,
                })
    return pd.DataFrame(rows)


def _matrixed_fixture() -> pd.DataFrame:
    """Same factorial space as ``_full_factorial_fixture`` but with
    half the cells dropped. We drop a deterministic selection of
    (batch, time, condition) cells that spans all three dimensions,
    so the remaining frame is a real sparse design (not just a
    sub-grid of one condition)."""
    full = _full_factorial_fixture()
    # 24 cells: drop every cell where the (batch, time, condition)
    # index tuple sums to an odd number. That gives a balanced
    # 12-cell subset spanning all batches, times, and conditions.
    keep_mask = np.array([
        # Original ordering: i = batch_idx*8 + time_idx*2 + cond_idx
        # Sum-of-indices trick keeps cells from every (batch, time).
        ((i // 8) + (i % 8) // 2 + (i % 2)) % 2 == 0
        for i in range(len(full))
    ])
    return full.loc[keep_mask].reset_index(drop=True)


def _bracketed_fixture() -> pd.DataFrame:
    """Full-factorial frame with a `strength` factor that takes only
    its global min and max values (10 and 100), with NO intermediate
    levels. This is the canonical ICH Q1D bracketing pattern."""
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 12.0):
            for cond in ("25C/60RH", "40C/75RH"):
                # Strength: min or max, alternating by batch to make
                # the "distinct values == 2" condition hold for the
                # whole frame.
                strength = 10.0 if batch in ("B1", "B2") else 100.0
                rows.append({
                    "batch": batch,
                    "time_months": t,
                    "condition": cond,
                    "strength": strength,
                    "value": 100.0 - 0.1 * t,
                })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test 1: full factorial → not reduced
# ---------------------------------------------------------------------------


def test_full_factorial_not_reduced() -> None:
    """A 3 × 4 × 2 frame with no factor columns reports no reduction."""
    df = _full_factorial_fixture()
    rep = detect_reduced_design(df)
    assert isinstance(rep, ReducedDesignReport)
    assert rep.is_bracketed is False
    assert rep.is_matrixed is False
    assert rep.missing_cells == []
    assert "no reduced design detected" in rep.note or "full-factorial" in rep.note


# ---------------------------------------------------------------------------
# Test 2: matrixed design → flagged, missing cells non-empty
# ---------------------------------------------------------------------------


def test_matrixed_design_detected() -> None:
    """A sparse (matrixed) frame is flagged; missing cells enumerated."""
    df = _matrixed_fixture()
    # Sanity check: the fixture is actually smaller than the full grid.
    full = _full_factorial_fixture()
    assert len(df) < len(full)
    rep = detect_reduced_design(df)
    assert rep.is_matrixed is True
    assert len(rep.missing_cells) > 0
    # Every reported missing cell is a (batch, time, condition) tuple.
    for cell in rep.missing_cells:
        assert len(cell) == 3
    # And those cells are genuinely absent from the frame.
    present = set(
        zip(df["batch"], df["time_months"], df["condition"].astype(str))
    )
    for cell in rep.missing_cells:
        assert cell not in present


def test_matrixed_missing_cells_capped_at_100() -> None:
    """A wildly sparse frame caps ``missing_cells`` at 100 entries.

    The frame declares presence across many batches, times, and
    conditions (so the detector's full-grid count is > 100) but
    populates only a handful of cells. The missing-cells list must
    be truncated at 100.
    """
    # Build a frame that spans 3 batches × 30 times × 4 conditions
    # (360 cells) but populate only 3 cells. The detector sees
    # n_batches=3, n_times=30, n_conditions=4, so n_cells_possible
    # = 360, and the 357 missing cells must be truncated to 100.
    cells = [
        ("B1", 0.0, "25C/60RH"),
        ("B2", 15.0, "40C/75RH"),
        ("B3", 29.0, "5C/ambient"),
    ]
    # Also need rows covering the other distinct values for each
    # dimension so the detector sees the full set of distinct
    # batches / times / conditions present (even if they only appear
    # in one cell each).
    rows = [
        {"batch": b, "time_months": t, "condition": c, "value": 100.0 - 0.1 * t}
        for b, t, c in cells
    ]
    # Add a row per distinct time to ensure n_times spans the full
    # 0..29 range (otherwise the detector sees fewer times and the
    # cap might not fire).
    extra_times = [
        t for t in range(30)
        if t not in {0.0, 15.0, 29.0}
    ]
    for t in extra_times:
        rows.append({
            "batch": "B1",
            "time_months": float(t),
            "condition": "25C/60RH",
            "value": 100.0 - 0.1 * float(t),
        })
    df = pd.DataFrame(rows)
    rep = detect_reduced_design(df)
    assert rep.is_matrixed is True
    # The cap must fire: cap is 100.
    assert len(rep.missing_cells) == 100
    # Every reported missing cell is a (batch, time, condition) tuple.
    for cell in rep.missing_cells:
        assert len(cell) == 3


# ---------------------------------------------------------------------------
# Test 3: bracketed factor → flagged
# ---------------------------------------------------------------------------


def test_bracketed_factor_detected() -> None:
    """A factor column with only the global min AND max is bracketed."""
    df = _bracketed_fixture()
    rep = detect_reduced_design(df, factor_columns=["strength"])
    assert rep.is_bracketed is True
    # With all cells present, matrixing is False even though
    # bracketing is True.
    assert rep.is_matrixed is False
    assert "strength" in rep.note


def test_bracketed_with_intermediate_levels_not_flagged() -> None:
    """A factor with intermediate levels is NOT bracketed (full range)."""
    df = _bracketed_fixture()
    # Add a third (intermediate) strength level on some rows so the
    # factor spans 10 / 55 / 100 instead of just 10 / 100.
    mask = (df["batch"] == "B3") & (df["time_months"] == 0.0)
    df.loc[mask, "strength"] = 55.0
    rep = detect_reduced_design(df, factor_columns=["strength"])
    assert rep.is_bracketed is False


def test_constant_factor_not_bracketed() -> None:
    """A factor with a single distinct value is NOT bracketed (no
    extremes were exercised — just one level)."""
    df = _full_factorial_fixture()
    df["strength"] = 50.0
    rep = detect_reduced_design(df, factor_columns=["strength"])
    assert rep.is_bracketed is False


# ---------------------------------------------------------------------------
# Test 4: no factor_columns → no bracketing check
# ---------------------------------------------------------------------------


def test_no_factors_columns_means_no_bracketing() -> None:
    """Without ``factor_columns``, bracketing is not evaluated — even
    on a sparse frame."""
    df = _matrixed_fixture()
    rep = detect_reduced_design(df)  # no factor_columns
    assert rep.is_bracketed is False
    # Matrixing is still evaluated (it's about cells, not factors).
    assert rep.is_matrixed is True


def test_empty_factor_columns_list_means_no_bracketing() -> None:
    """An empty ``factor_columns`` list behaves the same as None."""
    df = _bracketed_fixture()
    rep = detect_reduced_design(df, factor_columns=[])
    assert rep.is_bracketed is False


# ---------------------------------------------------------------------------
# Test 5: empty / malformed frame → safe sentinel
# ---------------------------------------------------------------------------


def test_empty_frame_safe_sentinel() -> None:
    """An empty frame returns the safe sentinel and does not raise."""
    df = pd.DataFrame(columns=["batch", "time_months", "condition", "value"])
    rep = detect_reduced_design(df)
    assert isinstance(rep, ReducedDesignReport)
    assert rep.is_bracketed is False
    assert rep.is_matrixed is False
    assert rep.missing_cells == []
    assert "insufficient data" in rep.note


def test_missing_required_columns_safe_sentinel() -> None:
    """A frame missing the required key columns returns the sentinel."""
    df = pd.DataFrame({"foo": [1, 2, 3], "bar": ["a", "b", "c"]})
    rep = detect_reduced_design(df)
    assert rep.is_bracketed is False
    assert rep.is_matrixed is False
    assert "insufficient data" in rep.note


def test_none_input_safe_sentinel() -> None:
    """A None input is treated as malformed; sentinel returned."""
    rep = detect_reduced_design(None)  # type: ignore[arg-type]
    assert rep.is_bracketed is False
    assert rep.is_matrixed is False
    assert "insufficient data" in rep.note


# ---------------------------------------------------------------------------
# Defensive: unknown factor column is silently skipped
# ---------------------------------------------------------------------------


def test_unknown_factor_column_skipped_silently() -> None:
    """A ``factor_columns`` entry that doesn't exist in the frame is
    skipped (no raise), per the "never raise on a malformed frame"
    spec rule."""
    df = _full_factorial_fixture()
    rep = detect_reduced_design(df, factor_columns=["nonexistent_factor"])
    assert rep.is_bracketed is False
    assert rep.is_matrixed is False
