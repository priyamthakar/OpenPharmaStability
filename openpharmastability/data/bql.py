"""Below-quantitation-limit (BQL) policies for OpenPharmaStability v0.3.0.

Policies:
  - exclude: drop rows where is_bql=True.
  - flag: keep rows; do not change values; record the count.
  - substitute_loq: replace value with loq column for BQL rows.
                    Requires a finite loq column. Records original_value.
  - substitute_loq_half: replace value with loq/2 for BQL rows.
                    Requires a finite loq column. Records original_value.
  - manual_review: keep rows; do not change values; record that the
                   attribute requires manual review (the report surfaces
                   this as a severity WARNING).

The function never silently substitutes without recording, and never
turns blanks into zero.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from openpharmastability.contracts import BQLSummary


POLICY_EXCLUDE = "exclude"
POLICY_FLAG = "flag"
POLICY_SUBSTITUTE_LOQ = "substitute_loq"
POLICY_SUBSTITUTE_LOQ_HALF = "substitute_loq_half"
POLICY_MANUAL_REVIEW = "manual_review"

SUPPORTED_POLICIES = frozenset({
    POLICY_EXCLUDE, POLICY_FLAG,
    POLICY_SUBSTITUTE_LOQ, POLICY_SUBSTITUTE_LOQ_HALF,
    POLICY_MANUAL_REVIEW,
})


def _bql_mask(df: pd.DataFrame) -> pd.Series:
    """Return a boolean Series marking BQL rows."""
    if "is_bql" not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    return df["is_bql"].apply(_is_bql_row_helper).astype(bool)


def _is_bql_row_helper(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, float):
        return not pd.isna(v)
    if isinstance(v, (int, np.integer)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "y", "t")
    return bool(v)


def apply_bql_policy(
    df: pd.DataFrame,
    policy: str = POLICY_EXCLUDE,
    loq_column: str = "loq",
) -> tuple[pd.DataFrame, BQLSummary]:
    """Apply the BQL policy. Returns ``(transformed_df, summary)``.

    The function NEVER turns blanks into zero and NEVER substitutes
    without recording. It always returns a BQLSummary so the report
    can surface the actual policy and counts.
    """
    if policy not in SUPPORTED_POLICIES:
        raise ValueError(
            f"unknown BQL policy: {policy!r}. "
            f"Expected one of {sorted(SUPPORTED_POLICIES)}."
        )

    bql_mask = _bql_mask(df)
    n_bql_rows = int(bql_mask.sum())

    # No is_bql column → nothing to do.
    if "is_bql" not in df.columns:
        return df.copy(), BQLSummary(
            policy=policy, n_bql_rows=0, n_substituted=0, n_excluded=0,
            notes=["no is_bql column; nothing to do"],
        )

    if policy == POLICY_EXCLUDE:
        out = df[~bql_mask].copy()
        return out, BQLSummary(
            policy=policy, n_bql_rows=n_bql_rows, n_substituted=0,
            n_excluded=n_bql_rows, notes=[],
        )

    if policy == POLICY_FLAG:
        out = df.copy()
        return out, BQLSummary(
            policy=policy, n_bql_rows=n_bql_rows, n_substituted=0, n_excluded=0,
            notes=(["flagged BQL rows; values not altered"]
                   if n_bql_rows else []),
        )

    if policy in (POLICY_SUBSTITUTE_LOQ, POLICY_SUBSTITUTE_LOQ_HALF):
        if loq_column not in df.columns:
            raise ValueError(
                f"bql_policy={policy!r} requires a {loq_column!r} column with finite values for BQL rows"
            )
        bad_loq = df.loc[bql_mask, loq_column]
        # Check both NaN and non-finite
        try:
            finite_mask = bad_loq.apply(lambda v: isinstance(v, (int, float, np.integer, np.floating)) and np.isfinite(float(v)))
        except Exception:
            finite_mask = bad_loq.apply(lambda v: isinstance(v, (int, float)) and np.isfinite(v))
        if not finite_mask.all():
            raise ValueError(
                f"bql_policy={policy!r}: BQL rows have missing or non-finite {loq_column} values; cannot substitute"
            )
        out = df.copy()
        if "original_value" not in out.columns:
            out["original_value"] = np.nan
        out.loc[bql_mask, "original_value"] = out.loc[bql_mask, "value"]
        if policy == POLICY_SUBSTITUTE_LOQ:
            out.loc[bql_mask, "value"] = out.loc[bql_mask, loq_column].astype(float)
            note = f"substituted {n_bql_rows} BQL row(s) with loq"
        else:
            out.loc[bql_mask, "value"] = out.loc[bql_mask, loq_column].astype(float) / 2.0
            note = f"substituted {n_bql_rows} BQL row(s) with loq/2"
        return out, BQLSummary(
            policy=policy, n_bql_rows=n_bql_rows, n_substituted=n_bql_rows,
            n_excluded=0, original_value_column="original_value",
            notes=[note],
        )

    if policy == POLICY_MANUAL_REVIEW:
        out = df.copy()
        return out, BQLSummary(
            policy=policy, n_bql_rows=n_bql_rows, n_substituted=0, n_excluded=0,
            notes=(
                [f"{n_bql_rows} BQL row(s) flagged for manual review; values not altered"]
                if n_bql_rows else []
            ),
        )

    raise ValueError(f"unhandled policy: {policy!r}")  # pragma: no cover


def count_bql_rows(df: pd.DataFrame) -> int:
    """Count rows with is_bql=True (or non-empty string)."""
    if "is_bql" not in df.columns:
        return 0
    return int(_bql_mask(df).sum())


__all__ = [
    "apply_bql_policy", "count_bql_rows",
    "POLICY_EXCLUDE", "POLICY_FLAG",
    "POLICY_SUBSTITUTE_LOQ", "POLICY_SUBSTITUTE_LOQ_HALF",
    "POLICY_MANUAL_REVIEW",
    "SUPPORTED_POLICIES",
]
