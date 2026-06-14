"""ICH Q1D reduced-design detection (bracketing and matrixing).

This module implements the v0.5.0 detector for two related
"reduced-design" patterns that ICH Q1D permits for stability
studies:

  * **Bracketing** — a factor (e.g. strength, container size) is
    tested at only the extreme levels (e.g. smallest and largest),
    and the intermediate levels are assumed to be bracketed by the
    extremes. Detected per factor column when the distinct values
    present in the data are <= 2 AND those values include the
    global min and max of the column on the full frame.
  * **Matrixing** — not every batch × time × condition cell is
    populated (sparse design). Detected when the count of distinct
    (batch, time, condition) tuples in the data is less than the
    cartesian product of the distinct batch × time × condition
    values (the "full-factorial" size).

The detector is intentionally defensive: a malformed or empty frame
returns a safe sentinel ``ReducedDesignReport`` and never raises.
The engine consumes the report and turns it into a warning string
on the ``StabilityResult``; it does not block analysis.

See ``NEXT_STEPS.md`` §5.2 for the spec.
"""
from __future__ import annotations

import pandas as pd

from openpharmastability.contracts import ReducedDesignReport


__all__ = ["detect_reduced_design"]


# Hard cap on the size of ``missing_cells`` so a wildly sparse
# frame cannot produce a multi-megabyte report payload.
_MAX_MISSING_CELLS_REPORTED: int = 100

# Columns required to evaluate matrixing. The detector returns a
# safe sentinel when any of these are missing.
_REQUIRED_KEY_COLUMNS: tuple[str, ...] = ("batch", "time_months", "condition")


def _safe_sentinel(reason: str) -> ReducedDesignReport:
    """Return a no-findings ``ReducedDesignReport`` with a short note."""
    return ReducedDesignReport(
        is_bracketed=False,
        is_matrixed=False,
        missing_cells=[],
        note=reason,
    )


def _is_factor_bracketed(series: pd.Series) -> bool:
    """Return True when ``series``'s distinct values are <= 2 AND
    include the global min and max of the column on the full frame.

    A bracketed factor exhibits the smallest AND largest possible
    levels (so intermediate levels are assumed covered). Constant
    columns (one distinct value, the min equals the max) are NOT
    bracketed by this rule because a single level is not a "bracket"
    in the Q1D sense — the user has not exercised the extremes, they
    have exercised only one.
    """
    # Coerce to numeric when possible; non-numeric factors are
    # matched by their distinct strings (e.g. container size labels).
    coerced = pd.to_numeric(series, errors="coerce")
    if coerced.notna().all():
        vals = coerced.dropna()
    else:
        vals = series.dropna().astype(str)

    distinct = vals.unique()
    if len(distinct) > 2:
        return False
    if len(distinct) < 2:
        # Single value: nothing bracketed (not a real bracket).
        return False
    # Two distinct values: bracketed iff they are the global min/max
    # of the (numeric or string-ordered) range on the full frame.
    g_min, g_max = vals.min(), vals.max()
    present = set(distinct.tolist())
    return (g_min in present) and (g_max in present)


def _missing_cartesian_cells(
    df: pd.DataFrame,
) -> list[tuple]:
    """Enumerate the absent (batch, time, condition) cells.

    The full-factorial cell count is the product of the distinct
    values in each of the three key columns. The reported missing
    cells are those in the cartesian product that do NOT appear as
    rows of the frame. The list is capped at
    ``_MAX_MISSING_CELLS_REPORTED`` to bound report size.
    """
    batches = sorted(df["batch"].dropna().unique().tolist())
    times = sorted(df["time_months"].dropna().unique().tolist())
    conditions = sorted(df["condition"].dropna().astype(str).unique().tolist())

    present: set[tuple] = set()
    for b, t, c in zip(
        df["batch"].tolist(),
        df["time_months"].tolist(),
        df["condition"].astype(str).tolist(),
    ):
        # NaN guard: drop rows with any NaN key from the "present" set
        # so they don't get reported as "absent" (they're malformed,
        # not deliberately missing).
        try:
            if pd.isna(b) or pd.isna(t) or pd.isna(c):
                continue
        except (TypeError, ValueError):
            # Non-scalar b/t/c — skip rather than crash.
            continue
        present.add((b, t, c))

    missing: list[tuple] = []
    for b in batches:
        for t in times:
            for c in conditions:
                if (b, t, c) not in present:
                    missing.append((b, t, c))
                    if len(missing) >= _MAX_MISSING_CELLS_REPORTED:
                        return missing
    return missing


def detect_reduced_design(
    df: pd.DataFrame,
    factor_columns: list[str] | None = None,
) -> ReducedDesignReport:
    """Detect bracketing and/or matrixing in a stability frame.

    Parameters
    ----------
    df:
        Input stability DataFrame. Must carry ``batch``,
        ``time_months``, and ``condition`` columns to evaluate
        matrixing. Per-factor columns (e.g. ``strength``,
        ``container_size``) are read from ``factor_columns`` when
        provided.
    factor_columns:
        Optional list of column names to check for bracketing. If
        ``None`` (the default) or empty, the function does not
        evaluate bracketing — matrixing is still evaluated as long
        as the required key columns are present.

    Returns
    -------
    ReducedDesignReport
        A populated report. Never raises on a malformed or empty
        frame — returns a safe sentinel instead.
    """
    # Defensive: bad input type
    if df is None or not isinstance(df, pd.DataFrame):
        return _safe_sentinel("insufficient data")

    # Defensive: empty frame
    if len(df) == 0:
        return _safe_sentinel("insufficient data")

    # Defensive: required key columns missing → can't evaluate matrixing
    missing_keys = [c for c in _REQUIRED_KEY_COLUMNS if c not in df.columns]
    if missing_keys:
        return _safe_sentinel("insufficient data")

    # --- Bracketing (per-factor) -------------------------------------
    bracketed_factors: list[str] = []
    if factor_columns:
        for col in factor_columns:
            if col not in df.columns:
                # Unknown factor column: skip silently — the caller
                # passed a list that doesn't match the frame, but
                # the spec is "never raise on a malformed frame".
                continue
            if _is_factor_bracketed(df[col]):
                bracketed_factors.append(col)
    is_bracketed = len(bracketed_factors) > 0

    # --- Matrixing (sparse cells) ------------------------------------
    n_batches = int(df["batch"].dropna().nunique())
    n_times = int(df["time_months"].dropna().nunique())
    n_conditions = int(df["condition"].dropna().astype(str).nunique())
    n_cells_possible = n_batches * n_times * n_conditions

    # Count distinct (batch, time, condition) tuples actually present.
    n_cells_actual = int(
        df.dropna(subset=list(_REQUIRED_KEY_COLUMNS))
        .drop_duplicates(subset=list(_REQUIRED_KEY_COLUMNS))
        .shape[0]
    )

    is_matrixed = n_cells_actual < n_cells_possible and n_cells_possible > 0
    missing_cells: list[tuple] = []
    if is_matrixed:
        missing_cells = _missing_cartesian_cells(df)

    # --- Note (human-readable summary) -------------------------------
    notes: list[str] = []
    if is_bracketed:
        notes.append(
            f"bracketed factor(s): {sorted(set(bracketed_factors))}"
        )
    if is_matrixed:
        notes.append(
            f"matrixed: {n_cells_actual} of {n_cells_possible} "
            f"batch×time×condition cells present "
            f"({len(missing_cells)} missing reported"
            f"{', capped' if len(missing_cells) >= _MAX_MISSING_CELLS_REPORTED else ''})"
        )
    if not notes:
        notes.append("full-factorial design; no reduced design detected")

    return ReducedDesignReport(
        is_bracketed=is_bracketed,
        is_matrixed=is_matrixed,
        missing_cells=missing_cells,
        note="; ".join(notes),
    )
