"""Replicate policy.

Replicate handling matters because not every repeated row is an independent
stability observation. The spec defines three policies; v0.1 implements them
as follows:

* ``"individual"`` — every row is a real observation. No aggregation.
* ``"mean_by_batch_time"`` — average within each
  ``(batch, time_months, attribute, condition)`` cell. This is the right
  policy when the data were not pre-averaged and each cell contains
  independent samples from the same pull.
* ``"technical_replicates_average"`` — same effect as
  ``mean_by_batch_time`` at this stage. The downstream engine treats the
  resulting frame differently (residual df changes); for v0.1 the v0.1
  contract is that both aggregation policies collapse to batch/time means.
  We keep them as distinct names so the engine can branch on the policy
  label later.

Any other policy string raises ``ValueError`` immediately. The function
returns a new ``DataFrame``; the input is not mutated.
"""
from __future__ import annotations

import pandas as pd

# Grouping key shared by every aggregation policy. Attribute and condition
# are part of the key so the function is safe to call on a multi-attribute
# frame; ``schema.validate_and_select`` filters to a single
# attribute/condition, so in normal use the group key degenerates to
# ``(batch, time_months)``.
_GROUP_KEY = ["batch", "time_months", "attribute", "condition"]

# Aggregate every numeric column in a way that is safe for the typical
# stability columns (value, is_bql-as-int, loq, lod). We do not aggregate
# the spec columns — those are properties of the attribute, not the
# observation.
_AGG_NUMERIC = {
    "value": "mean",
    "is_bql": "max",  # 1 if any replicate was BQL, else 0
    "loq": "mean",
    "lod": "mean",
    "temp_c": "mean",
    "rh": "mean",
}


def apply_replicate_policy(
    df: pd.DataFrame, policy: str = "individual"
) -> pd.DataFrame:
    """Collapse (or pass through) a stability frame by replicate policy.

    Parameters
    ----------
    df:
        Input frame. Expected to already be filtered to a single attribute
        and condition by ``validate_and_select``, but this function will
        also work on a raw multi-attribute frame — the group key includes
        ``attribute`` and ``condition``.
    policy:
        One of:

        * ``"individual"`` — pass through unchanged.
        * ``"mean_by_batch_time"`` — group by
          ``(batch, time_months, attribute, condition)`` and mean the
          numeric columns.
        * ``"technical_replicates_average"`` — same effect as
          ``mean_by_batch_time`` at v0.1 (documented seam for the engine).

    Returns
    -------
    pandas.DataFrame
        A new frame. For ``"individual"`` the input is returned unmodified.
        For the aggregation policies, the frame has one row per unique
        ``(batch, time_months, attribute, condition)`` tuple, with the
        value columns averaged.

    Raises
    ------
    ValueError
        If ``policy`` is not one of the supported strings.
    """
    if policy == "individual":
        return df.copy()

    if policy in ("mean_by_batch_time", "technical_replicates_average"):
        return _aggregate_to_batch_time_means(df)

    raise ValueError(
        f"unknown replicate_policy: {policy!r}. "
        "Expected one of: 'individual', 'mean_by_batch_time', "
        "'technical_replicates_average'."
    )


def _aggregate_to_batch_time_means(df: pd.DataFrame) -> pd.DataFrame:
    """Mean-aggregate a frame by ``(batch, time_months, attribute, condition)``.

    Only columns present in the input are aggregated; missing numeric
    columns are silently skipped (e.g. a frame without ``is_bql`` will
    still aggregate cleanly). Non-numeric columns that are part of the
    group key are kept; any other non-numeric column (e.g. ``unit``,
    ``method``, ``storage_type``) is dropped to keep the result tidy.
    """
    # Restrict the aggregation spec to columns actually present in df so
    # this works on minimal fixtures that only have ``value``.
    agg = {col: fn for col, fn in _AGG_NUMERIC.items() if col in df.columns}

    grouped = df.groupby(_GROUP_KEY, as_index=False, sort=True).agg(agg)

    # Restore a sensible column order: group keys first, then the rest.
    ordered = [c for c in _GROUP_KEY if c in grouped.columns] + [
        c for c in grouped.columns if c not in _GROUP_KEY
    ]
    return grouped[ordered].reset_index(drop=True)


__all__ = ["apply_replicate_policy"]
