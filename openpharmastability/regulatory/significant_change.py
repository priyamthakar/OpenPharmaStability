"""ICH Q1A(R2) §2.2.7 significant-change checklist + Q1E extrapolation gate.

This module implements the v0.4.0 regulatory decision-tree support for
OpenPharmaStability. It is intentionally stdlib + pandas only (no stats
machinery) so it can be unit-tested in isolation against hand-crafted
frames. The shelf_life engine wires the result into the long-term
``StabilityResult`` via ``StabilityResult.extrapolation_allowed`` /
``.extrapolation_rationale`` / ``.significant_change_*`` fields.

The five-criterion checklist follows ICH Q1A(R2) §2.2.7:
  1. Assay (5% change from t=0 default)
  2. Degradant (OOS column or upper_spec breach for increasing attributes)
  3. Physical (boolean `physical_fail` column)
  4. pH (range breach using ph_spec_low / ph_spec_high)
  5. Dissolution (boolean `dissolution_fail` column)

The Q1E extrapolation-allowance decision table implements
``NEXT_STEPS.md`` §4.3 verbatim.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from openpharmastability.contracts import (
    EXTRAPOLATION_MAX_MONTHS_BEYOND,
    SignificantChange,
)


__all__ = [
    "evaluate_significant_change",
    "extrapolation_allowance",
    "q1e_cap",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _has_truthy(series: pd.Series) -> bool:
    """Return True iff at least one non-null element is truthy."""
    if series is None or len(series) == 0:
        return False
    try:
        non_null = series.dropna()
    except (AttributeError, TypeError):
        return False
    if len(non_null) == 0:
        return False
    try:
        return bool(non_null.astype(bool).any())
    except (ValueError, TypeError):
        # Non-boolean-derivable series: treat as absent
        return False


def _first_truthy_month(series: pd.Series, times: pd.Series) -> Optional[float]:
    """Earliest t > 0 at which a non-null truthy element appears.

    Returns ``None`` if no such element exists.
    """
    if series is None or times is None or len(series) == 0:
        return None
    n = min(len(series), len(times))
    for i in range(n):
        v = series.iloc[i]
        t = times.iloc[i]
        if v is None or pd.isna(v) or t is None or pd.isna(t):
            continue
        try:
            if bool(v) and float(t) > 0.0:
                return float(t)
        except (TypeError, ValueError):
            continue
    return None


def _coerce_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(f):
        return None
    return f


def _baseline_value(grp: pd.DataFrame, value_col: str) -> Optional[float]:
    """Return the t=0 value for a batch, or None if absent / non-finite."""
    if "time_months" not in grp.columns or value_col not in grp.columns:
        return None
    t0 = grp[grp["time_months"] == 0.0]
    if len(t0) == 0:
        return None
    # If multiple t=0 rows, take the mean
    vals = [_coerce_float(v) for v in t0[value_col].tolist()]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return float(sum(vals) / len(vals))


# ---------------------------------------------------------------------------
# Per-criterion evaluators
# ---------------------------------------------------------------------------


def _eval_assay(
    df: pd.DataFrame,
    attribute_meta: dict[str, Any],
    threshold_pct: float,
    time_col: str,
    value_col: str,
) -> tuple[Optional[float], bool, str]:
    """Return (first_t, evaluated, evidence). evaluated=False means skipped."""
    # Skip for increasing attributes (assay rule does not apply to degradants)
    if bool(attribute_meta.get("is_increasing", False)):
        return (None, False, "skipped: rule does not apply to increasing attributes")

    if value_col not in df.columns or time_col not in df.columns:
        return (None, False, "skipped: required value/time columns missing")

    first_t: Optional[float] = None
    evidence_parts: list[str] = []
    for batch, grp in df.groupby("batch", sort=False):
        base = _baseline_value(grp, value_col)
        if base is None or base == 0.0:
            continue
        sub = grp[grp[time_col] > 0.0]
        for _, row in sub.iterrows():
            t = _coerce_float(row[time_col])
            v = _coerce_float(row[value_col])
            if t is None or v is None:
                continue
            pct = abs(v - base) / abs(base) * 100.0
            if pct >= threshold_pct:
                if first_t is None or t < first_t:
                    first_t = t
                evidence_parts.append(
                    f"batch={batch} t={t} pct={pct:.2f} (base={base:.2f})"
                )
                break  # earliest trip for this batch
    if first_t is None:
        return (None, True, f"no batch exceeded {threshold_pct:.1f}% change from t=0")
    return (first_t, True, f"{len(evidence_parts)} batch(es) exceeded "
            f"{threshold_pct:.1f}% change; earliest t={first_t}")


def _eval_degradant(
    df: pd.DataFrame,
    attribute_meta: dict[str, Any],
    time_col: str,
    value_col: str,
) -> tuple[Optional[float], bool, str]:
    """Two modes: (a) explicit OOS boolean column, (b) upper_spec breach."""
    oos_col = attribute_meta.get("degradant_oos_col", "degradant_oos")
    upper = _coerce_float(attribute_meta.get("upper_spec"))

    # (a) explicit OOS column path
    if oos_col in df.columns and _has_truthy(df[oos_col]):
        first_t = _first_truthy_month(df[oos_col], df[time_col])
        if first_t is not None:
            return (first_t, True, f"OOS column {oos_col!r} true at t={first_t}")
        # Has values but no t > 0 truthy → evaluated but no trigger
        return (None, True, f"OOS column {oos_col!r} present; no truthy t > 0")

    # (b) upper_spec breach for increasing attributes
    is_increasing = bool(attribute_meta.get("is_increasing", False))
    if is_increasing and upper is not None and value_col in df.columns:
        if time_col not in df.columns:
            return (None, False, "skipped: time column missing")
        sub = df[df[time_col] > 0.0]
        for _, row in sub.iterrows():
            t = _coerce_float(row[time_col])
            v = _coerce_float(row[value_col])
            if t is None or v is None:
                continue
            if v > upper:
                return (t, True, f"value {v} > upper_spec {upper} at t={t}")
        return (None, True, f"no value > upper_spec {upper} at t > 0")

    # Neither path applies → skip
    if oos_col in df.columns:
        return (None, True, f"OOS column {oos_col!r} present but all-null/False")
    if is_increasing and upper is not None:
        return (None, False, "skipped: no time column")
    return (None, False, "skipped: no OOS column and (no is_increasing or no upper_spec)")


def _eval_physical(
    df: pd.DataFrame,
    attribute_meta: dict[str, Any],
    time_col: str,
) -> tuple[Optional[float], bool, str]:
    col = attribute_meta.get("physical_fail_col", "physical_fail")
    if col not in df.columns:
        return (None, False, f"skipped: column {col!r} not in frame")
    if not _has_truthy(df[col]):
        # Column present but all-NaN / all-False → still "evaluated" but
        # the user provided the column; report that we looked at it.
        return (None, True, f"column {col!r} present; no truthy t > 0")
    first_t = _first_truthy_month(df[col], df[time_col])
    if first_t is not None:
        return (first_t, True, f"physical fail at t={first_t}")
    return (None, True, f"column {col!r} present; no truthy t > 0")


def _eval_ph(
    df: pd.DataFrame,
    attribute_meta: dict[str, Any],
    time_col: str,
    value_col: str,
) -> tuple[Optional[float], bool, str]:
    low = _coerce_float(attribute_meta.get("ph_spec_low"))
    high = _coerce_float(attribute_meta.get("ph_spec_high"))
    if low is None and high is None:
        return (None, False, "skipped: neither ph_spec_low nor ph_spec_high provided")
    if value_col not in df.columns or time_col not in df.columns:
        return (None, False, "skipped: required value/time columns missing")
    sub = df[df[time_col] > 0.0]
    for _, row in sub.iterrows():
        t = _coerce_float(row[time_col])
        v = _coerce_float(row[value_col])
        if t is None or v is None:
            continue
        if (low is not None and v < low) or (high is not None and v > high):
            return (t, True, f"pH {v} out of [{low}, {high}] at t={t}")
    return (None, True, f"no pH value out of [{low}, {high}] at t > 0")


def _eval_dissolution(
    df: pd.DataFrame,
    attribute_meta: dict[str, Any],
    time_col: str,
) -> tuple[Optional[float], bool, str]:
    col = attribute_meta.get("dissolution_fail_col", "dissolution_fail")
    if col not in df.columns:
        return (None, False, f"skipped: column {col!r} not in frame")
    if not _has_truthy(df[col]):
        return (None, True, f"column {col!r} present; no truthy t > 0")
    first_t = _first_truthy_month(df[col], df[time_col])
    if first_t is not None:
        return (first_t, True, f"dissolution fail at t={first_t}")
    return (None, True, f"column {col!r} present; no truthy t > 0")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_significant_change(
    df: pd.DataFrame,
    attribute_meta: dict[str, Any],
    condition_name: str,
    assay_change_threshold_pct: float = 5.0,
) -> SignificantChange:
    """Evaluate the ICH Q1A(R2) §2.2.7 checklist for one condition / attribute.

    Parameters
    ----------
    df:
        Rows for ONE condition, ONE attribute (any number of batches).
    attribute_meta:
        Dict carrying specs, thresholds, and column overrides. Recognized
        keys: ``lower_spec``, ``upper_spec``, ``is_increasing``,
        ``ph_spec_low``, ``ph_spec_high``, ``attribute``, ``batch``,
        ``time_col`` (default ``"time_months"``), ``value_col``
        (default ``"value"``), ``physical_fail_col`` (default
        ``"physical_fail"``), ``dissolution_fail_col`` (default
        ``"dissolution_fail"``), ``degradant_oos_col`` (default
        ``"degradant_oos"``).
    condition_name:
        Label written into ``per_condition`` so the engine can attribute
        the result to the correct condition bucket.
    assay_change_threshold_pct:
        Percent change from t=0 that trips the assay criterion.

    Returns
    -------
    SignificantChange
        A populated result. The function NEVER raises on a malformed
        frame; un-evaluable criteria are recorded with
        ``evaluated=False`` in ``details``.
    """
    time_col = attribute_meta.get("time_col", "time_months")
    value_col = attribute_meta.get("value_col", "value")

    # Empty-frame early return
    if df is None or len(df) == 0 or time_col not in df.columns:
        return SignificantChange(
            occurred=False,
            first_change_month=None,
            reasons=[],
            per_condition={condition_name: False},
            details={"evaluated": False, "reason": "empty_data"},
        )

    evaluators = [
        ("assay", _eval_assay, [assay_change_threshold_pct, time_col, value_col]),
        ("degradant", _eval_degradant, [time_col, value_col]),
        ("physical", _eval_physical, [time_col]),
        ("ph", _eval_ph, [time_col, value_col]),
        ("dissolution", _eval_dissolution, [time_col]),
    ]

    details: dict[str, Any] = {}
    reasons: list[str] = []
    first_change: Optional[float] = None

    for name, fn, extra in evaluators:
        try:
            t, evaluated, evidence = fn(df, attribute_meta, *extra)
        except Exception as exc:  # noqa: BLE001 — must never raise upstream
            details[name] = {
                "evaluated": False,
                "first_t": None,
                "evidence": f"error: {type(exc).__name__}: {exc}",
            }
            continue
        if not evaluated:
            details[name] = {
                "evaluated": False,
                "first_t": None,
                "evidence": evidence,
            }
            continue
        if t is not None:
            details[name] = {
                "evaluated": True,
                "first_t": t,
                "evidence": evidence,
            }
            reasons.append(f"{name} at t={t}: {evidence}")
            if first_change is None or t < first_change:
                first_change = t
        else:
            details[name] = {
                "evaluated": True,
                "first_t": None,
                "evidence": evidence,
            }

    return SignificantChange(
        occurred=first_change is not None,
        first_change_month=first_change,
        reasons=reasons,
        per_condition={condition_name: first_change is not None},
        details=details,
    )


def q1e_cap(observed: float) -> float:
    """Q1E rule of thumb: ``min(2 * observed, observed + 12)``."""
    return min(2.0 * float(observed), float(observed) + EXTRAPOLATION_MAX_MONTHS_BEYOND)


def extrapolation_allowance(
    acc: SignificantChange | None,
    inter: SignificantChange | None,
    observed_months: float,
) -> tuple[bool, float, str]:
    """Q1E extrapolation-allowance decision table.

    Implements ``NEXT_STEPS.md`` §4.3:

    - ``acc`` is None OR not ``acc.occurred`` → allowed, cap = q1e_cap,
      rationale ``"no accelerated sig change"`` (or ``"no accelerated
      data"`` if ``acc`` is None).
    - ``acc.occurred`` and ``first_change_month < 3`` → not allowed,
      cap = observed, rationale contains ``"<3mo"``.
    - ``acc.occurred`` and ``3 <= first_change_month <= 6``:
        * ``inter`` is None → not allowed, cap = observed, rationale
          contains ``"intermediate data required"``.
        * ``inter.occurred`` → not allowed, cap = observed, rationale
          ``"intermediate sig change"``.
        * else → allowed, cap = q1e_cap, rationale ``"intermediate OK"``.
    - ``acc.occurred`` and ``first_change_month > 6`` → allowed,
      cap = q1e_cap, rationale contains ``">6mo"``.

    Returns
    -------
    (allowed, cap_months, rationale)
    """
    cap = q1e_cap(observed_months)
    if acc is None or not acc.occurred:
        rationale = "no accelerated data" if acc is None else "no accelerated sig change"
        return (True, cap, rationale)
    first = acc.first_change_month
    if first is None:
        # Defensive: acc.occurred=True but no first_change_month recorded.
        return (True, cap, "no accelerated sig change")
    if first < 3.0:
        return (False, float(observed_months), "accelerated sig change <3mo")
    if first <= 6.0:
        if inter is None:
            return (
                False,
                float(observed_months),
                "3-6mo accelerated change; intermediate data required but absent",
            )
        if inter.occurred:
            return (False, float(observed_months), "intermediate sig change")
        return (True, cap, "3-6mo accelerated change; intermediate OK")
    return (True, cap, "accelerated change >6mo")
