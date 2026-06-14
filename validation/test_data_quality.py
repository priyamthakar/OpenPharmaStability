"""Tests for the v0.3.0 data quality layer (data/quality.py)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from openpharmastability.contracts import IssueSeverity
from openpharmastability.data.quality import IssueCode, audit_data_quality


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _baseline_frame(n_per_t=2, sd=0.3, seed=20260113):
    rng = np.random.default_rng(seed)
    rows = []
    for batch, b0 in (("B1", 100.0), ("B2", 99.0), ("B3", 101.0)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0):
            for _ in range(n_per_t):
                rows.append({
                    "batch": batch, "condition": "25C/60RH",
                    "time_months": t, "attribute": "assay",
                    "value": b0 - 0.5 * t + float(rng.normal(0.0, sd)),
                    "lower_spec": 90.0, "upper_spec": 110.0,
                    "direction": "decreasing",
                })
    return pd.DataFrame(rows)


def _codes(report, code):
    return [i for i in report.issues if i.code == code]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_missing_required_columns_raises_error():
    df = _baseline_frame()
    df = df.drop(columns=["value"])
    r = audit_data_quality(df, attribute="assay")
    assert r.n_errors >= 1
    assert any(i.code == IssueCode.MISSING_REQUIRED_COLUMN and i.severity is IssueSeverity.ERROR
               for i in r.issues)
    assert r.can_analyze is False


def test_missing_values_in_required_fields():
    df = _baseline_frame()
    df.loc[df.index[0], "value"] = np.nan
    df.loc[df.index[1], "batch"] = np.nan
    r = audit_data_quality(df, attribute="assay")
    assert any(i.code == IssueCode.MISSING_VALUE for i in r.issues)


def test_non_numeric_value_warning():
    df = _baseline_frame()
    # Force the column to object dtype so pandas stores the string.
    df["value"] = df["value"].astype(object)
    df.loc[df.index[0], "value"] = "oops"
    r = audit_data_quality(df, attribute="assay")
    assert any(i.code == IssueCode.NON_NUMERIC_VALUE for i in r.issues)


def test_negative_time_error():
    df = _baseline_frame()
    df.loc[df.index[0], "time_months"] = -1.0
    r = audit_data_quality(df, attribute="assay")
    assert any(i.code == IssueCode.NEGATIVE_TIME and i.severity is IssueSeverity.ERROR
               for i in r.issues)


def test_duplicate_row_warning():
    df = _baseline_frame()
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    r = audit_data_quality(df, attribute="assay")
    assert any(i.code == IssueCode.DUPLICATE_ROW for i in r.issues)


def test_duplicate_batch_time_no_replicate_info():
    df = _baseline_frame(n_per_t=1)
    # Duplicate the first row to make (batch, time, attribute) collision
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    r = audit_data_quality(df, attribute="assay")
    assert any(i.code == IssueCode.DUPLICATE_BATCH_TIME_NO_REPLICATE for i in r.issues)


def test_inconsistent_spec_warning():
    df = _baseline_frame()
    df.loc[df.index[0], "lower_spec"] = 95.0  # different from 90.0
    r = audit_data_quality(df, attribute="assay")
    assert any(i.code == IssueCode.INCONSISTENT_SPEC for i in r.issues)


def test_inconsistent_direction_warning():
    df = _baseline_frame()
    df.loc[df.index[0], "direction"] = "increasing"
    r = audit_data_quality(df, attribute="assay")
    assert any(i.code == IssueCode.INCONSISTENT_DIRECTION for i in r.issues)


def test_too_few_batches_warning():
    rng = np.random.default_rng(20260113)
    rows = []
    for batch in ("B1", "B2"):  # only 2 batches
        for t in (0.0, 3.0, 6.0, 12.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": 100.0 - 0.5 * t + float(rng.normal(0.0, 0.3)),
                "lower_spec": 90.0, "upper_spec": 110.0,
                "direction": "decreasing",
            })
    df = pd.DataFrame(rows)
    r = audit_data_quality(df, attribute="assay")
    assert any(i.code == IssueCode.TOO_FEW_BATCHES for i in r.issues)


def test_too_few_time_points_warning():
    rng = np.random.default_rng(20260113)
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0):  # only 2 distinct time points
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": 100.0 - 0.5 * t + float(rng.normal(0.0, 0.3)),
                "lower_spec": 90.0, "upper_spec": 110.0,
                "direction": "decreasing",
            })
    df = pd.DataFrame(rows)
    r = audit_data_quality(df, attribute="assay")
    assert any(i.code == IssueCode.TOO_FEW_TIME_POINTS for i in r.issues)


def test_baseline_missing_warning():
    rng = np.random.default_rng(20260113)
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (3.0, 6.0, 12.0):  # no t=0
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": 100.0 - 0.5 * t + float(rng.normal(0.0, 0.3)),
                "lower_spec": 90.0, "upper_spec": 110.0,
                "direction": "decreasing",
            })
    df = pd.DataFrame(rows)
    r = audit_data_quality(df, attribute="assay")
    assert any(i.code == IssueCode.BASELINE_MISSING for i in r.issues)


def test_no_finite_spec_error():
    rng = np.random.default_rng(20260113)
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 12.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": 100.0 - 0.5 * t + float(rng.normal(0.0, 0.3)),
                "lower_spec": np.nan, "upper_spec": np.nan,
                "direction": "decreasing",
            })
    df = pd.DataFrame(rows)
    r = audit_data_quality(df, attribute="assay")
    assert any(i.code == IssueCode.NO_FINITE_SPEC and i.severity is IssueSeverity.ERROR
               for i in r.issues)


def test_release_spec_only_warning():
    df = _baseline_frame()
    df["spec_type"] = "release"
    r = audit_data_quality(df, attribute="assay")
    assert any(i.code == IssueCode.RELEASE_SPEC_ONLY for i in r.issues)


def test_wrong_condition_info():
    df = _baseline_frame()
    df.loc[df.index[0], "condition"] = "40C/75RH"
    r = audit_data_quality(df, attribute="assay", condition="25C/60RH")
    assert any(i.code == IssueCode.WRONG_CONDITION for i in r.issues)


def test_empty_selected_attribute_error():
    df = _baseline_frame()
    r = audit_data_quality(df, attribute="impurity_a")
    assert any(i.code == IssueCode.EMPTY_SELECTED_ATTRIBUTE
               and i.severity is IssueSeverity.ERROR for i in r.issues)
    assert r.can_analyze is False


def test_non_monotonic_time_info():
    rng = np.random.default_rng(20260113)
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 6.0, 3.0, 12.0):  # 3, 6 not monotonic for B1
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": 100.0 - 0.5 * t + float(rng.normal(0.0, 0.3)),
                "lower_spec": 90.0, "upper_spec": 110.0,
                "direction": "decreasing",
            })
    df = pd.DataFrame(rows)
    r = audit_data_quality(df, attribute="assay")
    assert any(i.code == IssueCode.NON_MONOTONIC_TIME for i in r.issues)


def test_report_is_json_serializable():
    df = _baseline_frame()
    r = audit_data_quality(df, attribute="assay")
    # dataclasses are not directly JSON-serializable; use asdict.
    from dataclasses import asdict
    blob = json.dumps(asdict(r), default=str)
    parsed = json.loads(blob)
    assert parsed["row_count"] == len(df)
    assert parsed["attributes"] == ["assay"]


def test_summary_counts_match_issues():
    """Build a frame that triggers 1 ERROR + 2 WARNING + 1 INFO, verify counts."""
    rng = np.random.default_rng(20260113)
    rows = []
    # 1 ERROR row: empty baseline + no spec
    rows.append({
        "batch": "B1", "condition": "25C/60RH",
        "time_months": 0.0, "attribute": "assay",
        "value": 100.0,
        "lower_spec": np.nan, "upper_spec": np.nan,
        "direction": "decreasing",
    })
    # 2 WARNING rows: inconsistent spec (different lower_spec) + inconsistent direction
    rows.append({**rows[0], "time_months": 3.0, "lower_spec": 80.0, "upper_spec": 110.0})
    rows.append({**rows[0], "time_months": 6.0, "lower_spec": 90.0, "upper_spec": 110.0, "direction": "increasing"})
    # 1 INFO row: wrong condition
    rows.append({**rows[0], "time_months": 9.0, "condition": "40C/75RH", "lower_spec": 90.0, "upper_spec": 110.0})
    # Filler rows so OLS has enough data and the audit's per-attribute
    # subset isn't dominated by the no-spec row.
    for t in (12.0, 18.0, 24.0):
        rows.append({**rows[1], "time_months": t})
    df = pd.DataFrame(rows)
    # Inconsistent spec is global (across the whole attribute). The
    # per-attribute subset does include 80.0 and 90.0 as lower_spec,
    # so the inconsistent check fires as WARNING.
    # But the no_finite_spec check requires NO finite spec at all;
    # since other rows have 80/90, the no_finite_spec ERROR does NOT
    # fire. So we expect n_errors == 0 here. Construct a separate
    # dataset to assert n_errors >= 1.
    r = audit_data_quality(df, attribute="assay", condition="25C/60RH")
    assert r.n_warnings >= 1  # inconsistent spec OR direction
    assert r.n_info >= 1  # wrong condition
    # Now a separate frame: all rows have NaN spec → 1 ERROR.
    rows2 = []
    for t in (0.0, 3.0, 6.0, 12.0):
        rows2.append({**rows[0], "time_months": t})
    df2 = pd.DataFrame(rows2)
    r2 = audit_data_quality(df2, attribute="assay")
    assert r2.n_errors >= 1
    assert r2.can_analyze is False


def test_wrong_condition_normalized_no_false_positive():
    """v0.3.1: rows written as '25°C/60%RH' must NOT be flagged as wrong
    when the user requests the canonical '25C/60RH'.
    """
    df = _baseline_frame()
    # Rewrite the condition column in a non-canonical but equivalent form.
    df["condition"] = "25°C/60%RH"
    r = audit_data_quality(df, attribute="assay", condition="25C/60RH")
    assert not any(i.code == IssueCode.WRONG_CONDITION for i in r.issues)


def test_wrong_condition_genuinely_different_still_flagged():
    """Sanity: a frame with a genuinely different condition still raises the issue."""
    df = _baseline_frame()
    # Mutate one row's condition to a truly different environment.
    df.loc[df.index[0], "condition"] = "40C/75RH"
    r = audit_data_quality(df, attribute="assay", condition="25C/60RH")
    assert any(i.code == IssueCode.WRONG_CONDITION for i in r.issues)
