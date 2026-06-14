"""Tests for the v0.3.0 real BQL policies (data/bql.py)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from openpharmastability.data.bql import (
    POLICY_EXCLUDE, POLICY_FLAG, POLICY_MANUAL_REVIEW,
    POLICY_SUBSTITUTE_LOQ, POLICY_SUBSTITUTE_LOQ_HALF,
    SUPPORTED_POLICIES, apply_bql_policy, count_bql_rows,
)


def _df_with_bql(n_bql=2, loq_value=0.05, n_normal=10, seed=20260113):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_normal):
        rows.append({
            "batch": "B1", "time_months": float(i),
            "value": 100.0 - 0.5 * float(i) + float(rng.normal(0.0, 0.1)),
            "is_bql": False, "loq": np.nan,
        })
    for i in range(n_bql):
        rows.append({
            "batch": "B1", "time_months": 20.0 + float(i),
            "value": np.nan, "is_bql": True, "loq": loq_value,
        })
    return pd.DataFrame(rows)


def test_exclude_drops_bql_rows():
    df = _df_with_bql()
    out, summary = apply_bql_policy(df, policy=POLICY_EXCLUDE)
    assert len(out) == 10
    assert summary.policy == "exclude"
    assert summary.n_bql_rows == 2
    assert summary.n_excluded == 2
    assert summary.n_substituted == 0


def test_flag_keeps_rows_unchanged():
    df = _df_with_bql()
    out, summary = apply_bql_policy(df, policy=POLICY_FLAG)
    assert len(out) == 12
    assert summary.policy == "flag"
    assert summary.n_bql_rows == 2
    assert summary.n_excluded == 0
    # Values are not changed.
    np.testing.assert_array_equal(out["value"].to_numpy(), df["value"].to_numpy())


def test_substitute_loq_replaces_value():
    df = _df_with_bql(loq_value=0.05)
    out, summary = apply_bql_policy(df, policy=POLICY_SUBSTITUTE_LOQ)
    assert summary.policy == "substitute_loq"
    assert summary.n_substituted == 2
    # BQL rows now have value == loq
    bql_rows = out[out["is_bql"]]
    np.testing.assert_array_almost_equal(bql_rows["value"].to_numpy(), [0.05, 0.05])
    # original_value column has the pre-substitution values (NaN)
    assert "original_value" in out.columns
    assert bql_rows["original_value"].isna().all()


def test_substitute_loq_half_replaces_value_with_half():
    df = _df_with_bql(loq_value=0.10)
    out, summary = apply_bql_policy(df, policy=POLICY_SUBSTITUTE_LOQ_HALF)
    assert summary.policy == "substitute_loq_half"
    assert summary.n_substituted == 2
    bql_rows = out[out["is_bql"]]
    np.testing.assert_array_almost_equal(bql_rows["value"].to_numpy(), [0.05, 0.05])  # 0.10/2
    assert "original_value" in out.columns


def test_substitute_missing_loq_raises():
    df = _df_with_bql()
    df = df.drop(columns=["loq"])
    with pytest.raises(ValueError, match="loq"):
        apply_bql_policy(df, policy=POLICY_SUBSTITUTE_LOQ)


def test_substitute_non_finite_loq_raises():
    df = _df_with_bql()
    df.loc[df["is_bql"], "loq"] = np.nan
    with pytest.raises(ValueError, match="loq"):
        apply_bql_policy(df, policy=POLICY_SUBSTITUTE_LOQ)


def test_manual_review_keeps_rows_and_warns():
    df = _df_with_bql()
    out, summary = apply_bql_policy(df, policy=POLICY_MANUAL_REVIEW)
    assert len(out) == 12
    assert summary.policy == "manual_review"
    assert summary.n_bql_rows == 2
    assert summary.n_excluded == 0
    assert any("manual review" in n for n in summary.notes)


def test_substitution_preserves_original_value_with_existing_data():
    """When the BQL rows have non-NaN values, original_value should preserve them."""
    df = _df_with_bql()
    df.loc[df["is_bql"], "value"] = 0.001  # pre-substitution tiny values
    out, _ = apply_bql_policy(df, policy=POLICY_SUBSTITUTE_LOQ)
    bql_rows = out[out["is_bql"]]
    np.testing.assert_array_almost_equal(bql_rows["original_value"].to_numpy(), [0.001, 0.001])


def test_no_bql_column_returns_empty_summary():
    df = pd.DataFrame({"batch": ["B1"], "value": [100.0]})
    out, summary = apply_bql_policy(df, policy=POLICY_EXCLUDE)
    assert len(out) == 1
    assert summary.n_bql_rows == 0
    assert any("no is_bql" in n for n in summary.notes)


def test_unknown_policy_raises():
    df = _df_with_bql()
    with pytest.raises(ValueError, match="unknown BQL policy"):
        apply_bql_policy(df, policy="banana")


def test_supported_policies_contains_all_five():
    expected = {POLICY_EXCLUDE, POLICY_FLAG, POLICY_SUBSTITUTE_LOQ,
                POLICY_SUBSTITUTE_LOQ_HALF, POLICY_MANUAL_REVIEW}
    assert set(SUPPORTED_POLICIES) == expected


def test_count_bql_rows_helper():
    df = _df_with_bql(n_bql=3)
    assert count_bql_rows(df) == 3
    assert count_bql_rows(df.drop(columns=["is_bql"])) == 0


# ---------------------------------------------------------------------------
# §9.11  apply_replicate_policy raises ValueError for unknown policy
# ---------------------------------------------------------------------------


def test_replicate_unknown_policy_raises():
    """apply_replicate_policy must raise ValueError for an unrecognised policy.

    This locks the error path so a typo in the engine's replicate_policy
    argument surfaces loudly rather than silently using the wrong logic.
    """
    import pandas as pd
    from openpharmastability.data.replicates import apply_replicate_policy

    df = pd.DataFrame({
        "batch": ["A", "A"],
        "time_months": [0.0, 0.0],
        "value": [99.5, 100.5],
        "attribute": ["assay", "assay"],
        "condition": ["25C/60RH", "25C/60RH"],
    })
    with pytest.raises(ValueError, match="bogus"):
        apply_replicate_policy(df, "bogus")
