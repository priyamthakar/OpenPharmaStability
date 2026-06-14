"""Schema validation and attribute/condition selection.

The :func:`validate_and_select` function is the single contract-enforcing
step between "raw CSV" and "everything downstream assumes the data look
exactly like this." It performs five jobs in order:

1. **Column check.** Every name in :data:`contracts.REQUIRED_COLUMNS` must
   be present, and at least one of ``lower_spec``/``upper_spec`` must
   appear (assay has both, degradants have only upper, some attributes
   have only lower — but never neither).
2. **Condition normalization.** Both the requested condition and every
   value in the dataframe's ``condition`` column are passed through
   :func:`openpharmastability.data.conditions.parse_condition` so the
   user can write ``"25°C/60%RH"`` and match rows that were saved as
   ``"25C/60RH"``.
3. **Filtering.** The frame is restricted to the requested ``attribute``
   and the normalized ``condition``.
4. **Direction.** If the dataframe carries a ``direction`` column we
   trust it (and warn if it disagrees with what the spec limits imply).
   If it does not, we infer from which spec limit is finite.
5. **Policies.** The replicate policy is applied first, then the BQL
   policy. Both are no-ops on the typical fixture (one row per
   ``(batch, time)`` cell, no BQL) but exercised by the test suite.

The output is a :class:`contracts.ValidatedData` with a sorted,
single-attribute, single-condition frame plus the spec context the stats
and reporting layers need.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from openpharmastability.contracts import (
    REQUIRED_COLUMNS,
    Direction,
    ValidatedData,
)
from openpharmastability.data.bql import apply_bql_policy, count_bql_rows
from openpharmastability.data.conditions import parse_condition
from openpharmastability.data.replicates import apply_replicate_policy


#: Spec limits are "finite" iff at least one row has a non-null value.
#: Used by direction inference and by the spec-value extraction in
#: :func:`validate_and_select`.
_SPEC_COLUMNS = ("lower_spec", "upper_spec")

#: Replicate policies accepted by the schema layer. Other strings raise
#: :class:`ValueError`. ``"individual"`` is the default; the aggregation
#: policies collapse to batch/time means at this stage.
_REPLICATE_POLICIES = frozenset(
    {"individual", "mean_by_batch_time", "technical_replicates_average"}
)


def validate_and_select(
    df: pd.DataFrame,
    attribute: str,
    condition: str,
    replicate_policy: str = "individual",
    bql_policy: str = "exclude",
) -> ValidatedData:
    """Validate the input frame and return a single-attribute subset.

    Parameters
    ----------
    df:
        A stability frame as read from CSV (or built in memory by a test).
        Must contain every column in :data:`contracts.REQUIRED_COLUMNS`
        and at least one of ``lower_spec`` / ``upper_spec``.
    attribute:
        The single attribute to analyze (e.g. ``"assay"``). Rows with any
        other ``attribute`` value are dropped.
    condition:
        The single long-term storage condition to analyze, in any
        supported spelling. Normalized via
        :func:`openpharmastability.data.conditions.parse_condition`.
    replicate_policy:
        One of ``"individual"`` (default), ``"mean_by_batch_time"``,
        ``"technical_replicates_average"``. See
        :func:`openpharmastability.data.replicates.apply_replicate_policy`.

    Returns
    -------
    ValidatedData
        A frozen-shape record with the filtered, policy-applied frame,
        spec values, batch count, sorted time points, and any warnings
        raised during validation (e.g. a direction mismatch, an empty
        filter result, or BQL rows that were dropped).

    Raises
    ------
    ValueError
        If a required column is missing, if no spec limit is present, if
        the replicate policy string is unknown, or if the requested
        condition cannot be parsed.
    """
    warnings: list[str] = []

    _check_required_columns(df)
    _check_at_least_one_spec(df)
    _check_replicate_policy(replicate_policy)

    target_condition = parse_condition(condition)

    # Normalize every condition in the frame. We do this BEFORE filtering
    # so that ``"25°C/60%RH"`` rows and ``"25C 60% RH"`` rows both surface
    # in the filter for ``target_condition = "25C/60RH"``.
    normalized = _normalize_condition_column(df, "condition", warnings)

    # Restrict to the requested attribute + condition. The frame at this
    # point still has all columns (lower_spec, upper_spec, direction, ...)
    # so we can read spec values and the declared direction.
    mask = (normalized == target_condition) & (df["attribute"] == attribute)
    filtered = df.loc[mask].copy()
    # Keep the normalized condition in the working frame so downstream
    # code (which is attribute+condition blind) does not have to redo it.
    filtered["condition"] = normalized.loc[mask].values

    if filtered.empty:
        warnings.append(
            f"no rows match attribute={attribute!r}, "
            f"condition={target_condition!r}"
        )
        return ValidatedData(
            df=filtered.reset_index(drop=True),
            attribute=attribute,
            condition=target_condition,
            direction=Direction.UNKNOWN,
            lower_spec=None,
            upper_spec=None,
            n_batches=0,
            time_points=[],
            warnings=warnings,
        )

    direction, declared_direction, inferred_direction = _resolve_direction(
        filtered, warnings
    )
    lower_spec, upper_spec = _extract_spec_values(filtered, warnings)

    # Apply replicate policy first, then BQL policy. The order matters
    # when ``mean_by_batch_time`` collapses several BQL rows in a single
    # cell: the ``is_bql`` aggregation max() preserves the BQL flag so
    # the subsequent BQL policy can still drop the cell.
    working = apply_replicate_policy(filtered, policy=replicate_policy)

    bql_rows_before = count_bql_rows(working)
    working, bql_summary = apply_bql_policy(working, policy=bql_policy)
    bql_rows_after_exclusion = bql_rows_before - count_bql_rows(working)

    if bql_rows_before > 0:
        warnings.append(
            f"bql_policy={bql_summary.policy!r}: "
            f"{bql_summary.n_excluded} excluded, "
            f"{bql_summary.n_substituted} substituted, "
            f"{bql_rows_before} BQL row(s) total"
        )

    # Deterministic ordering for the regression layer and any test that
    # asserts row order. ``sort=True`` is the default for groupby but we
    # also sort here so the result is stable even when replicate_policy
    # leaves the frame untouched.
    working = working.sort_values(
        by=["batch", "time_months"], kind="mergesort"
    ).reset_index(drop=True)

    n_batches = int(working["batch"].nunique()) if len(working) else 0
    time_points = sorted(working["time_months"].unique().tolist())

    return ValidatedData(
        df=working,
        attribute=attribute,
        condition=target_condition,
        direction=direction,
        lower_spec=lower_spec,
        upper_spec=upper_spec,
        n_batches=n_batches,
        time_points=time_points,
        warnings=warnings,
        bql_summary=bql_summary,
    )


# ---------------------------------------------------------------------------
# Helpers (private — not part of the public API)
# ---------------------------------------------------------------------------


def _check_required_columns(df: pd.DataFrame) -> None:
    """Raise ``ValueError`` with a complete list of missing columns."""
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            "input DataFrame is missing required column(s): "
            f"{missing}. Required columns are {list(REQUIRED_COLUMNS)}."
        )


def _check_at_least_one_spec(df: pd.DataFrame) -> None:
    """Raise ``ValueError`` if neither spec column is present.

    Note this is a column-presence check, not a "has a finite value"
    check. A frame with both columns present but every row NaN is a
    data-quality issue handled by direction inference (UNKNOWN), not a
    schema violation.
    """
    if not any(c in df.columns for c in _SPEC_COLUMNS):
        raise ValueError(
            "input DataFrame must include at least one of "
            f"{list(_SPEC_COLUMNS)}; neither was found."
        )


def _check_replicate_policy(policy: str) -> None:
    if policy not in _REPLICATE_POLICIES:
        raise ValueError(
            f"unknown replicate_policy: {policy!r}. Expected one of "
            f"{sorted(_REPLICATE_POLICIES)}."
        )


def _normalize_condition_column(
    df: pd.DataFrame, column: str, warnings: list[str]
) -> pd.Series:
    """Return a Series with every value in ``df[column]`` normalized.

    Empty/NaN values are passed through as-is so the filter step can
    safely drop them. Anything else that fails to parse raises
    :class:`ValueError` with a sample of the offending rows.
    """
    raw = df[column]
    normalized: list[Any] = [None] * len(raw)
    bad: list[Any] = []
    for i, value in enumerate(raw.tolist()):
        if value is None or (isinstance(value, float) and np.isnan(value)):
            normalized[i] = np.nan
            continue
        try:
            normalized[i] = parse_condition(str(value))
        except ValueError:
            bad.append((i, value))
    if bad:
        sample = [v for _, v in bad[:5]]
        raise ValueError(
            f"could not parse {len(bad)} value(s) in column {column!r}; "
            f"examples: {sample!r}"
        )
    return pd.Series(normalized, index=df.index, name=column)


def _resolve_direction(
    filtered: pd.DataFrame, warnings: list[str]
) -> tuple[Direction, Direction | None, Direction]:
    """Decide the final ``Direction`` and surface incompatibilities as warnings.

    Warnings are emitted only when the declaration is **incompatible**
    with the available spec limits — e.g. declared ``DECREASING`` with
    no ``lower_spec``, declared ``BIDIRECTIONAL`` with only one spec, or
    declared ``UNKNOWN`` (a v0.1 weak path). The common assay case —
    ``DECREASING`` declared and **both** spec limits present — is
    normal and produces no mismatch warning. Declaring a single-sided
    direction while the frame also carries the other spec limit is
    likewise normal (the user has declared the trend; the extra spec
    value just happens to be recorded) and is not flagged.

    Returns
    -------
    (direction, declared, inferred)
        ``direction`` is what goes into :class:`ValidatedData`. ``declared``
        is the value from the dataframe's ``direction`` column (or
        ``None`` if the column is absent). ``inferred`` is what the spec
        limits would have implied on their own; useful for warning text
        and for callers that want to audit the inference.
    """
    inferred = _infer_direction_from_spec(filtered)
    if "direction" not in filtered.columns:
        return inferred, None, inferred

    declared_values = filtered["direction"].dropna().unique().tolist()
    if not declared_values:
        return inferred, None, inferred
    if len(declared_values) > 1:
        warnings.append(
            "direction column contains multiple distinct values "
            f"({declared_values!r}); using the first ({declared_values[0]!r})"
        )
    declared = _coerce_direction(declared_values[0])
    _warn_on_incompatible_direction(declared, filtered, warnings)
    return declared, declared, inferred


def _warn_on_incompatible_direction(
    declared: Direction, filtered: pd.DataFrame, warnings: list[str]
) -> None:
    """Warn only on true incompatibilities between ``declared`` and the specs.

    The compatible cases — ``DECREASING``/``INCREASING`` declared with
    the required spec present (and the other spec optionally also
    present), and ``BIDIRECTIONAL`` declared with both specs present —
    produce no warning. ``BIDIRECTIONAL`` with both specs is the
    inferred-by-default case; we still trust the declaration.
    """
    has_lower = (
        "lower_spec" in filtered.columns and filtered["lower_spec"].notna().any()
    )
    has_upper = (
        "upper_spec" in filtered.columns and filtered["upper_spec"].notna().any()
    )

    if declared is Direction.DECREASING and not has_lower:
        warnings.append(
            "DECREASING direction declared but lower_spec is missing; "
            "a decreasing trend cannot be evaluated without a lower bound."
        )
        return
    if declared is Direction.INCREASING and not has_upper:
        warnings.append(
            "INCREASING direction declared but upper_spec is missing; "
            "an increasing trend cannot be evaluated without an upper bound."
        )
        return
    if declared is Direction.BIDIRECTIONAL and (not has_lower or not has_upper):
        warnings.append(
            "BIDIRECTIONAL direction declared but only one spec limit is "
            "present; behavior may be one-sided."
        )
        return
    if declared is Direction.UNKNOWN:
        warnings.append(
            "UNKNOWN direction is not fully supported in v0.1; "
            "results may be heuristic."
        )
        return
    # Compatible declaration: declared DECREASING/INCREASING with the
    # required spec present (other spec optional), or declared
    # BIDIRECTIONAL with both specs present. No warning.


def _infer_direction_from_spec(df: pd.DataFrame) -> Direction:
    """Infer :class:`Direction` from which spec limit has a finite value."""
    has_lower = (
        "lower_spec" in df.columns and df["lower_spec"].notna().any()
    )
    has_upper = (
        "upper_spec" in df.columns and df["upper_spec"].notna().any()
    )
    if has_lower and has_upper:
        return Direction.BIDIRECTIONAL
    if has_upper and not has_lower:
        return Direction.INCREASING
    if has_lower and not has_upper:
        return Direction.DECREASING
    return Direction.UNKNOWN


def _coerce_direction(value: Any) -> Direction:
    """Map a string cell value to a :class:`Direction` enum, or raise."""
    if isinstance(value, Direction):
        return value
    if isinstance(value, str):
        try:
            return Direction(value)
        except ValueError:
            pass
    raise ValueError(
        f"direction column has unsupported value: {value!r}. "
        f"Expected one of {[d.value for d in Direction]!r}."
    )


def _extract_spec_values(
    filtered: pd.DataFrame, warnings: list[str]
) -> tuple[float | None, float | None]:
    """Pick representative ``lower_spec`` and ``upper_spec`` from the frame.

    The spec limits are an attribute-level property, so a tidy dataset has
    one constant value across all rows. We take the first non-null value
    and warn (not error) if the column contains more than one distinct
    value — that mismatch will appear in the report and the user can
    decide whether to fix the source data.
    """
    return (
        _first_finite(filtered, "lower_spec", warnings),
        _first_finite(filtered, "upper_spec", warnings),
    )


def _first_finite(
    df: pd.DataFrame, column: str, warnings: list[str]
) -> float | None:
    if column not in df.columns:
        return None
    series = df[column].dropna()
    if series.empty:
        return None
    distinct = series.unique()
    if len(distinct) > 1:
        warnings.append(
            f"{column} has {len(distinct)} distinct values in the filtered "
            f"frame ({sorted(map(float, distinct))!r}); using the first "
            f"({float(distinct[0])!r})"
        )
    return float(distinct[0])


__all__ = ["validate_and_select"]
