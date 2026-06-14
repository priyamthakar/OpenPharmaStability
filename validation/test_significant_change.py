"""Tests for the v0.4.0 ICH Q1A significant-change module
(``openpharmastability.regulatory.significant_change``)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from openpharmastability.contracts import SignificantChange
from openpharmastability.regulatory import (
    evaluate_significant_change,
    extrapolation_allowance,
    q1e_cap,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _baseline_meta(**overrides) -> dict:
    """Sensible defaults for an assay-style attribute."""
    base = {
        "lower_spec": 90.0,
        "upper_spec": 110.0,
        "is_increasing": False,
        "ph_spec_low": None,
        "ph_spec_high": None,
        "attribute": "assay",
        "batch": "B1",
    }
    base.update(overrides)
    return base


def _frame_with_optional_cols(rows: list[dict], optional_cols: list[str]) -> pd.DataFrame:
    """Build a DataFrame and pad missing optional columns with NaN/False."""
    df = pd.DataFrame(rows)
    for c in optional_cols:
        if c not in df.columns:
            # Booleans get NaN; columns named *_fail are NaN, degradant_oos NaN
            df[c] = np.nan
    return df


# ---------------------------------------------------------------------------
# evaluate_significant_change — assay
# ---------------------------------------------------------------------------


def test_assay_criterion_fires_at_5pct():
    """One batch drops 6% from t=0 at t=3 → first_change_month == 3.0."""
    rows = []
    # Three batches, 5 time points each, baseline at 100.0; B2 drops 6% at t=3
    for batch, drift in (("B1", 0.0), ("B2", -6.0), ("B3", -1.0)):
        for t in (0.0, 1.0, 3.0, 6.0, 12.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "value": 100.0 + drift * (t / 3.0 if t > 0 else 0.0),
            })
    df = pd.DataFrame(rows)
    res = evaluate_significant_change(
        df, _baseline_meta(), condition_name="25C/60RH",
    )
    assert res.occurred is True
    assert res.first_change_month == pytest.approx(3.0)
    assert res.details["assay"]["first_t"] == pytest.approx(3.0)
    assert res.details["assay"]["evaluated"] is True
    # t=1 is well under 5% for B2 (≈ 2% drop), t=3 hits ~6% → B2 trips first
    assert any("assay at t=3" in r for r in res.reasons)


def test_assay_criterion_ignores_degradant():
    """is_increasing=True → assay rule MUST NOT trip, even on big swings."""
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 1.0, 3.0, 6.0, 12.0):
            # 30% increase — would clearly trip the 5% rule, but degradant
            # mode disables the assay criterion entirely.
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "value": 100.0 + 30.0 * (t / 12.0),
            })
    df = pd.DataFrame(rows)
    res = evaluate_significant_change(
        df,
        _baseline_meta(is_increasing=True, upper_spec=0.5),
        condition_name="25C/60RH",
    )
    # No OOS column, but is_increasing + upper_spec=0.5 → at t=3 already 107.5
    # which is >> 0.5. The degradant (upper_spec breach) criterion fires.
    # Crucially, the ASSAY criterion was skipped (not evaluated).
    assert res.details["assay"]["evaluated"] is False
    assert "increasing" in res.details["assay"]["evidence"].lower() or \
        "does not apply" in res.details["assay"]["evidence"].lower()


# ---------------------------------------------------------------------------
# evaluate_significant_change — degradant
# ---------------------------------------------------------------------------


def test_degradant_oos_column_fires():
    """degradant_oos=True at t=6 only → trip at 6.0."""
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 1.0, 3.0, 6.0, 12.0):
            rows.append({
                "batch": batch, "condition": "40C/75RH",
                "time_months": t, "value": 0.05 + t * 0.001,
                "degradant_oos": (t == 6.0),
            })
    df = pd.DataFrame(rows)
    res = evaluate_significant_change(
        df,
        _baseline_meta(is_increasing=True, upper_spec=0.5),
        condition_name="40C/75RH",
    )
    assert res.occurred is True
    assert res.first_change_month == pytest.approx(6.0)
    assert res.details["degradant"]["first_t"] == pytest.approx(6.0)


# ---------------------------------------------------------------------------
# evaluate_significant_change — physical / pH / dissolution
# ---------------------------------------------------------------------------


def test_physical_fail_fires():
    """physical_fail=True at t=12 → trip at 12.0."""
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 1.0, 3.0, 6.0, 12.0):
            rows.append({
                "batch": batch, "condition": "40C/75RH",
                "time_months": t, "value": 100.0,
                "physical_fail": (t == 12.0),
            })
    df = pd.DataFrame(rows)
    res = evaluate_significant_change(
        df, _baseline_meta(), condition_name="40C/75RH",
    )
    assert res.occurred is True
    assert res.first_change_month == pytest.approx(12.0)
    assert res.details["physical"]["first_t"] == pytest.approx(12.0)


def test_ph_out_of_spec_fires():
    """pH 8.0 at t=3, spec [5.5, 7.5] → trip at 3.0."""
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 1.0, 3.0, 6.0, 12.0):
            # pH is 6.5 at baseline and t=1, then jumps to 8.0 at t=3
            ph = 8.0 if t == 3.0 else 6.5
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "value": ph,
            })
    df = pd.DataFrame(rows)
    res = evaluate_significant_change(
        df,
        _baseline_meta(ph_spec_low=5.5, ph_spec_high=7.5),
        condition_name="25C/60RH",
    )
    assert res.occurred is True
    assert res.first_change_month == pytest.approx(3.0)
    assert res.details["ph"]["first_t"] == pytest.approx(3.0)


def test_dissolution_fail_fires():
    """dissolution_fail=True at t=6 → trip at 6.0."""
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 1.0, 3.0, 6.0, 12.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "value": 85.0,
                "dissolution_fail": (t == 6.0),
            })
    df = pd.DataFrame(rows)
    res = evaluate_significant_change(
        df, _baseline_meta(), condition_name="25C/60RH",
    )
    assert res.occurred is True
    assert res.first_change_month == pytest.approx(6.0)
    assert res.details["dissolution"]["first_t"] == pytest.approx(6.0)


# ---------------------------------------------------------------------------
# evaluate_significant_change — robustness
# ---------------------------------------------------------------------------


def test_missing_columns_skip_not_crash():
    """Frame with only batch/time_months/value → no raises, all not-evaluated.

    is_increasing=True is set so the assay rule is skipped (per spec §4.2:
    "Skip if is_increasing is True (assay-only rule)"). With the optional
    columns also absent, ALL five criteria are un-evaluable.
    """
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 12.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "value": 100.0 - 0.1 * t,
            })
    df = pd.DataFrame(rows)
    res = evaluate_significant_change(
        df,
        _baseline_meta(is_increasing=True, upper_spec=None),
        condition_name="25C/60RH",
    )
    # Nothing trips because no optional columns are present AND the
    # assay rule is skipped via is_increasing=True.
    assert res.occurred is False
    assert res.first_change_month is None
    for name in ("assay", "degradant", "physical", "ph", "dissolution"):
        assert name in res.details
        assert res.details[name]["evaluated"] is False
    # per_condition always populated
    assert res.per_condition == {"25C/60RH": False}


def test_per_condition_uses_argument_name():
    """The condition_name argument shows up as the sole per_condition key."""
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 12.0):
            # Tiny drift so the 5% assay rule does not trip
            rows.append({
                "batch": batch, "condition": "40C/75RH",
                "time_months": t, "value": 100.0 - 0.1 * t,
            })
    df = pd.DataFrame(rows)
    res = evaluate_significant_change(
        df, _baseline_meta(), condition_name="40C/75RH",
    )
    assert res.per_condition == {"40C/75RH": False}


# ---------------------------------------------------------------------------
# q1e_cap
# ---------------------------------------------------------------------------


def test_q1e_cap_matches_spec():
    # min(2 * 24, 24 + 12) = min(48, 36) = 36
    assert q1e_cap(24.0) == 36.0
    # 0 → 0
    assert q1e_cap(0.0) == 0.0
    # 6 → min(12, 18) = 12
    assert q1e_cap(6.0) == 12.0
    # 12 → min(24, 24) = 24
    assert q1e_cap(12.0) == 24.0
    # 18 → min(36, 30) = 30
    assert q1e_cap(18.0) == 30.0


# ---------------------------------------------------------------------------
# extrapolation_allowance — decision table
# ---------------------------------------------------------------------------


def test_extrapolation_allowance_no_acc_change():
    acc = SignificantChange(occurred=False, first_change_month=None)
    allowed, cap, why = extrapolation_allowance(acc, inter=None, observed_months=24.0)
    assert allowed is True
    assert cap == 36.0
    assert why == "no accelerated sig change"


def test_extrapolation_allowance_change_lt_3mo():
    acc = SignificantChange(occurred=True, first_change_month=2.0)
    allowed, cap, why = extrapolation_allowance(acc, inter=None, observed_months=24.0)
    assert allowed is False
    assert cap == 24.0
    assert "<3mo" in why


def test_extrapolation_allowance_change_3_6_no_intermediate():
    acc = SignificantChange(occurred=True, first_change_month=4.0)
    allowed, cap, why = extrapolation_allowance(acc, inter=None, observed_months=24.0)
    assert allowed is False
    assert cap == 24.0
    assert "intermediate data required" in why


def test_extrapolation_allowance_change_3_6_inter_ok():
    acc = SignificantChange(occurred=True, first_change_month=4.0)
    inter = SignificantChange(occurred=False, first_change_month=None)
    allowed, cap, why = extrapolation_allowance(acc, inter=inter, observed_months=24.0)
    assert allowed is True
    assert cap == 36.0
    assert "intermediate OK" in why


def test_extrapolation_allowance_change_at_intermediate():
    acc = SignificantChange(occurred=True, first_change_month=4.0)
    inter = SignificantChange(occurred=True, first_change_month=5.0)
    allowed, cap, why = extrapolation_allowance(acc, inter=inter, observed_months=24.0)
    assert allowed is False
    assert cap == 24.0
    assert why == "intermediate sig change"


def test_extrapolation_allowance_change_gt_6mo():
    acc = SignificantChange(occurred=True, first_change_month=9.0)
    allowed, cap, why = extrapolation_allowance(acc, inter=None, observed_months=24.0)
    assert allowed is True
    assert cap == 36.0
    assert ">6mo" in why
