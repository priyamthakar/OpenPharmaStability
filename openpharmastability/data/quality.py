"""Data quality audit for OpenPharmaStability v0.3.0.

The audit runs as a non-mutating pass over the raw input frame and
returns a :class:`DataQualityReport` listing every issue found.
v0.3.0 reports issues; it does NOT block analysis.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from openpharmastability.contracts import (
    DataQualityIssue,
    DataQualityReport,
    IssueSeverity,
    REQUIRED_COLUMNS,
)
from openpharmastability.data.conditions import parse_condition


def _norm_condition_series(s: pd.Series) -> pd.Series:
    """Normalize a condition series to the canonical ``<T>C/<RH>RH`` form.

    NaN and empty values pass through unchanged so they can be filtered
    out separately by the caller. Unparseable strings also pass through
    unchanged so the audit does not crash on weird input.
    """
    def _norm_one(v: str):
        if not v or v == "nan":
            return v
        try:
            return parse_condition(v)
        except ValueError:
            return v

    return s.astype(str).map(_norm_one)


class IssueCode:
    MISSING_REQUIRED_COLUMN = "missing_required_column"
    MISSING_VALUE = "missing_value"
    NON_NUMERIC_VALUE = "non_numeric_value"
    NEGATIVE_TIME = "negative_time"
    DUPLICATE_ROW = "duplicate_row"
    DUPLICATE_BATCH_TIME_NO_REPLICATE = "duplicate_batch_time_no_replicate"
    INCONSISTENT_SPEC = "inconsistent_spec"
    INCONSISTENT_DIRECTION = "inconsistent_direction"
    NON_MONOTONIC_TIME = "non_monotonic_time"
    TOO_FEW_BATCHES = "too_few_batches"
    TOO_FEW_TIME_POINTS = "too_few_time_points"
    BASELINE_MISSING = "baseline_missing"
    NO_FINITE_SPEC = "no_finite_spec"
    RELEASE_SPEC_ONLY = "release_spec_only"
    WRONG_CONDITION = "wrong_condition"
    EMPTY_SELECTED_ATTRIBUTE = "empty_selected_attribute"


def _issue(code, severity, message, **kw) -> DataQualityIssue:
    return DataQualityIssue(code=code, severity=severity, message=message, **kw)


def _is_finite_number(s) -> bool:
    try:
        v = float(s)
        return np.isfinite(v)
    except (TypeError, ValueError):
        return False


def _truthy(v) -> bool:
    """Series-aware: returns True if v is truthy AND not NaN/null."""
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


def audit_data_quality(
    df: pd.DataFrame,
    attribute: Optional[str] = None,
    condition: Optional[str] = None,
) -> DataQualityReport:
    """Run the data-quality audit on a raw input frame.

    Parameters
    ----------
    df:
        The raw, post-load DataFrame.
    attribute:
        If given, also runs per-attribute checks.
    condition:
        If given, warns on rows whose condition column does not match.

    Returns
    -------
    DataQualityReport. The report does NOT mutate ``df``.
    """
    issues: list[DataQualityIssue] = []

    # 1. Missing required columns
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    for c in missing_cols:
        issues.append(_issue(
            IssueCode.MISSING_REQUIRED_COLUMN, IssueSeverity.ERROR,
            f"required column {c!r} is missing", column=c,
        ))
    if missing_cols:
        return _summarize(issues, df, attribute=attribute, condition=condition)

    # 2. Missing values in required fields
    for c in REQUIRED_COLUMNS:
        n_missing = int(df[c].isna().sum())
        if n_missing > 0:
            issues.append(_issue(
                IssueCode.MISSING_VALUE, IssueSeverity.WARNING,
                f"column {c!r} has {n_missing} missing value(s)",
                column=c, details={"n_missing": n_missing},
            ))

    # 3. Non-numeric in time_months / value
    for c in ("time_months", "value"):
        if c in df.columns:
            non_numeric = []
            for i, v in enumerate(df[c].tolist()):
                if pd.isna(v):
                    continue
                if not _is_finite_number(v):
                    non_numeric.append(i)
            for i in non_numeric[:20]:
                issues.append(_issue(
                    IssueCode.NON_NUMERIC_VALUE, IssueSeverity.WARNING,
                    f"column {c!r} has non-numeric value at row {i}",
                    column=c, row_index=i,
                ))
            if len(non_numeric) > 20:
                issues.append(_issue(
                    IssueCode.NON_NUMERIC_VALUE, IssueSeverity.WARNING,
                    f"column {c!r} has {len(non_numeric) - 20} more non-numeric value(s) (truncated)",
                    column=c, details={"n_total": len(non_numeric), "truncated": True},
                ))

    # 4. Negative time
    if "time_months" in df.columns:
        for i, t in enumerate(df["time_months"].tolist()):
            if pd.isna(t):
                continue
            try:
                tv = float(t)
            except (TypeError, ValueError):
                continue
            if tv < 0:
                issues.append(_issue(
                    IssueCode.NEGATIVE_TIME, IssueSeverity.ERROR,
                    f"time_months < 0 at row {i}: {tv}",
                    column="time_months", row_index=i,
                    details={"value": tv},
                ))

    # 5. Duplicate exact rows
    if len(df) > 0:
        dup_mask = df.duplicated(keep=False)
        n_dup_groups = int(df[dup_mask].drop_duplicates().shape[0])
        if n_dup_groups > 0:
            issues.append(_issue(
                IssueCode.DUPLICATE_ROW, IssueSeverity.WARNING,
                f"{n_dup_groups} duplicate row group(s) found",
                details={"n_groups": n_dup_groups},
            ))

    # 6. Duplicate batch+time+attribute (no replicate column)
    if all(c in df.columns for c in ("batch", "time_months", "attribute")):
        if "replicate" not in df.columns:
            dup = df.duplicated(subset=["batch", "time_months", "attribute"], keep=False)
            n_dup = int(dup.sum())
            if n_dup > 0:
                issues.append(_issue(
                    IssueCode.DUPLICATE_BATCH_TIME_NO_REPLICATE, IssueSeverity.INFO,
                    f"{n_dup} rows share (batch, time, attribute) — no 'replicate' column",
                    details={"n_dup": n_dup},
                ))

    # 7-15. Per-attribute checks (only if attribute filter given)
    sub = df
    if attribute is not None and "attribute" in df.columns:
        sub = df[df["attribute"].astype(str) == str(attribute)]

    # 7. Inconsistent lower_spec / upper_spec
    if attribute is not None and "lower_spec" in sub.columns:
        lowers = sub["lower_spec"].dropna().unique().tolist()
        if len(lowers) > 1:
            issues.append(_issue(
                IssueCode.INCONSISTENT_SPEC, IssueSeverity.WARNING,
                f"attribute {attribute!r} has multiple distinct lower_spec values: {sorted(set(lowers))}",
                attribute=attribute, column="lower_spec",
                details={"values": sorted(set(lowers))},
            ))
    if attribute is not None and "upper_spec" in sub.columns:
        uppers = sub["upper_spec"].dropna().unique().tolist()
        if len(uppers) > 1:
            issues.append(_issue(
                IssueCode.INCONSISTENT_SPEC, IssueSeverity.WARNING,
                f"attribute {attribute!r} has multiple distinct upper_spec values: {sorted(set(uppers))}",
                attribute=attribute, column="upper_spec",
                details={"values": sorted(set(uppers))},
            ))

    # 8. Inconsistent direction
    if attribute is not None and "direction" in sub.columns:
        dirs = sub["direction"].dropna().astype(str).unique().tolist()
        if len(dirs) > 1:
            issues.append(_issue(
                IssueCode.INCONSISTENT_DIRECTION, IssueSeverity.WARNING,
                f"attribute {attribute!r} has multiple distinct direction values: {sorted(set(dirs))}",
                attribute=attribute, column="direction",
                details={"values": sorted(set(dirs))},
            ))

    # 9. Non-monotonic time per batch
    if all(c in sub.columns for c in ("batch", "time_months")):
        for batch, grp in sub.groupby("batch"):
            times = pd.to_numeric(grp["time_months"], errors="coerce").dropna().tolist()
            if len(times) < 2:
                continue
            if times != sorted(times):
                issues.append(_issue(
                    IssueCode.NON_MONOTONIC_TIME, IssueSeverity.INFO,
                    f"batch {batch!r} has non-monotonic time ordering",
                    batch=batch, attribute=attribute,
                ))

    # 10. Too few batches
    if "batch" in sub.columns:
        n_batches = sub["batch"].dropna().nunique()
        if 0 < n_batches < 3:
            issues.append(_issue(
                IssueCode.TOO_FEW_BATCHES, IssueSeverity.WARNING,
                f"only {n_batches} batch(es) present; Q1E expects at least 3",
                attribute=attribute, details={"n_batches": n_batches},
            ))

    # 11. Too few time points
    if "time_months" in sub.columns:
        n_tp = pd.to_numeric(sub["time_months"], errors="coerce").dropna().nunique()
        if 0 < n_tp < 3:
            issues.append(_issue(
                IssueCode.TOO_FEW_TIME_POINTS, IssueSeverity.WARNING,
                f"only {n_tp} distinct time point(s); need at least 3 (incl. baseline)",
                attribute=attribute, details={"n_time_points": n_tp},
            ))

    # 12. Baseline missing
    if "time_months" in sub.columns and len(sub) > 0:
        has_zero = (pd.to_numeric(sub["time_months"], errors="coerce") == 0).any()
        if not has_zero:
            issues.append(_issue(
                IssueCode.BASELINE_MISSING, IssueSeverity.WARNING,
                f"no t=0 (baseline) point for {f'attribute {attribute!r}' if attribute else 'the data'}",
                attribute=attribute,
            ))

    # 13. No finite spec
    if attribute is not None:
        has_lower = "lower_spec" in sub.columns and sub["lower_spec"].notna().any()
        has_upper = "upper_spec" in sub.columns and sub["upper_spec"].notna().any()
        if not has_lower and not has_upper:
            issues.append(_issue(
                IssueCode.NO_FINITE_SPEC, IssueSeverity.ERROR,
                f"attribute {attribute!r} has no finite spec (lower_spec or upper_spec)",
                attribute=attribute,
            ))

    # 14. Release-spec-only
    if attribute is not None and "spec_type" in sub.columns:
        stypes = sub["spec_type"].dropna().astype(str).unique().tolist()
        if stypes and all(s == "release" for s in stypes):
            issues.append(_issue(
                IssueCode.RELEASE_SPEC_ONLY, IssueSeverity.WARNING,
                f"attribute {attribute!r} has only 'release' spec_type; shelf-life analysis uses shelf-life specs",
                attribute=attribute, column="spec_type",
            ))

    # 15. Wrong condition
    if condition is not None and "condition" in df.columns:
        try:
            requested_norm = parse_condition(str(condition))
        except ValueError:
            requested_norm = str(condition)
        raw = df["condition"]
        non_empty = raw.notna() & (raw.astype(str).str.strip() != "")
        n_non_empty = int(non_empty.sum())
        if n_non_empty > 0:
            norm = _norm_condition_series(raw)
            wrong_mask = non_empty & (norm != requested_norm)
            n_wrong = int(wrong_mask.sum())
            if 0 < n_wrong < n_non_empty:
                issues.append(_issue(
                    IssueCode.WRONG_CONDITION, IssueSeverity.INFO,
                    f"{n_wrong} row(s) have a different condition than the requested {condition!r}",
                    column="condition", details={"n_wrong": n_wrong, "requested": condition},
                ))

    # 16. Empty selected attribute
    if attribute is not None and "attribute" in df.columns and len(sub) == 0:
        issues.append(_issue(
            IssueCode.EMPTY_SELECTED_ATTRIBUTE, IssueSeverity.ERROR,
            f"attribute {attribute!r} has no rows in the input",
            attribute=attribute,
        ))

    return _summarize(issues, df, attribute=attribute, condition=condition)


def _summarize(issues, df, *, attribute, condition) -> DataQualityReport:
    n_err = sum(1 for i in issues if i.severity is IssueSeverity.ERROR)
    n_warn = sum(1 for i in issues if i.severity is IssueSeverity.WARNING)
    n_info = sum(1 for i in issues if i.severity is IssueSeverity.INFO)
    attrs = sorted(df["attribute"].dropna().astype(str).unique().tolist()) if "attribute" in df.columns else []
    conds = sorted(df["condition"].dropna().astype(str).unique().tolist()) if "condition" in df.columns else []
    return DataQualityReport(
        issues=issues,
        n_errors=n_err, n_warnings=n_warn, n_info=n_info,
        row_count=int(len(df)), column_count=int(len(df.columns)),
        attributes=attrs, conditions=conds,
        can_analyze=(n_err == 0),
    )


__all__ = ["audit_data_quality", "IssueCode"]
