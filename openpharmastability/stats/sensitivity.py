"""Leave-one-out sensitivity analysis for OpenPharmaStability v0.7.0 / v0.8.0.

Given a :class:`~openpharmastability.contracts.StabilityResult` and the
:class:`~openpharmastability.contracts.ValidatedData` it was computed
from, re-run the full analysis end-to-end with each drop target
removed and record the resulting supported shelf life. The result is
a :class:`~openpharmastability.contracts.SensitivityReport` suitable
for the JSON decision record and the HTML report.

Two drop modes are supported (v0.8.0):

* ``mode="row"`` (v0.7.0 default) — leave-one-row-out over the
  Cook's-distance influential points flagged by the diagnostics
  layer. ``drop_key`` is the row index as a string;
  ``influential_row_index`` is the same value (kept for backward
  compat).
* ``mode="batch"`` (v0.8.0) — leave-one-batch-out. For every
  distinct batch in the data used for the fit, drop all its rows
  and re-fit. ``drop_key`` is the batch identifier;
  ``influential_row_index`` is the FIRST row index of the dropped
  batch (informational only — kept so consumers that read
  ``influential_row_index`` continue to see an int).

The trigger set for ``mode="row"`` is
``result.diagnostics.influential_points`` (a list of row indices in
the data used for the fit, produced by
:mod:`openpharmastability.stats.diagnostics`). When the diagnostics
layer did not flag any point, the row-mode report is empty and the
summary explains that the sensitivity analysis is a no-op.

The ``mode="batch"`` branch always runs (it does not depend on the
diagnostics-layer trigger set). When fewer than two distinct
batches survive the same NaN/value filter the regression layer
applies, the batch-mode report is empty and the summary notes
"need >= 2 distinct batches for leave-one-batch-out".
"""
from __future__ import annotations

import os
import tempfile
from typing import List, Optional, Tuple

import pandas as pd

from openpharmastability.contracts import (
    SensitivityReport,
    SensitivityRow,
    StabilityResult,
    ValidatedData,
)
from openpharmastability.regulatory.profile import GuidanceProfile


def compute_sensitivity(
    result: StabilityResult,
    data: ValidatedData,
    *,
    horizon: float = 60.0,
    mode: str = "row",
    profile: GuidanceProfile | None = None,
) -> SensitivityReport:
    """Leave-one-out sensitivity.

    v0.7.0: ``mode="row"`` (the default, preserved for back-compat)
    iterates over ``result.diagnostics.influential_points`` and
    records the supported shelf life that results from removing
    that single row from the fit.

    v0.8.0: ``mode="batch"`` iterates over every distinct batch in
    the validated data and records the supported shelf life that
    results from removing that batch entirely.

    The diff is the absolute change vs the baseline
    (``result.supported_shelf_life_months``).

    The summary string is short and human-readable; examples::

        "max delta 0 mo; shelf life robust to outliers"
        "max delta 0 mo; shelf life robust to dropping any single batch"
        "max delta 2 mo; 1 point changes the shelf life"
        "max delta 5 mo; a single point drives the shelf-life
         decision — sensitivity analysis recommended"
        "max delta 5 mo; a single batch drives the shelf-life
         decision — sensitivity analysis recommended"

    Parameters
    ----------
    result:
        The :class:`StabilityResult` produced by
        :func:`openpharmastability.shelf_life.engine.analyze`. The
        baseline supported shelf life and (for row mode) the
        trigger set of influential points are read from this
        object.
    data:
        The :class:`ValidatedData` the baseline fit was computed
        on. The leave-one-out refit uses ``data.df`` with the
        target row / batch removed.
    horizon:
        Maximum crossing-search time in months. Forwarded to the
        per-refit :func:`~openpharmastability.shelf_life.engine.analyze`
        call. Default ``60.0``.
    mode:
        ``"row"`` (v0.7.0, default) for leave-one-row-out over
        Cook's-distance influential points; ``"batch"`` (v0.8.0)
        for leave-one-batch-out. Unknown values raise ``ValueError``.
    """
    mode_norm = str(mode).strip().lower()
    if mode_norm == "row":
        return _compute_sensitivity_row(result, data, horizon=horizon, profile=profile)
    if mode_norm == "batch":
        return _compute_sensitivity_batch(result, data, horizon=horizon, profile=profile)
    raise ValueError(
        f"compute_sensitivity: unknown mode {mode!r}; expected 'row' or 'batch'."
    )


def _compute_sensitivity_row(
    result: StabilityResult,
    data: ValidatedData,
    *,
    horizon: float,
    profile: GuidanceProfile | None,
) -> SensitivityReport:
    """Row-level leave-one-out sensitivity (v0.7.0 behavior).

    For each row index in ``result.diagnostics.influential_points``,
    re-run the analysis (model selection, poolability, fit, crossing,
    shelf life) on ``data.df`` with that row removed, and record the
    new supported shelf life.
    """
    base_shelf = result.supported_shelf_life_months
    influential = list(result.diagnostics.influential_points or [])
    if not influential:
        return SensitivityReport(
            rows=[],
            summary=(
                "no influential points flagged; sensitivity analysis is a no-op"
            ),
            baseline_supported_shelf_life=base_shelf,
            mode="row",
            notes=["diagnostics.influential_points is empty"],
        )

    rows: List[SensitivityRow] = []
    diffs: List[int] = []
    for idx in influential:
        try:
            loo_shelf, loo_cross, loo_note = _leave_one_out(
                result, data, idx, horizon=horizon, profile=profile,
            )
        except Exception as exc:  # defensive
            loo_shelf, loo_cross = None, None
            loo_note = f"leave-one-out fit failed: {exc!r}"
        diff = (
            (loo_shelf - base_shelf)
            if (loo_shelf is not None and base_shelf is not None)
            else 0
        )
        diffs.append(abs(int(diff)))
        rows.append(
            SensitivityRow(
                influential_row_index=int(idx),
                baseline_supported_shelf_life=(
                    int(base_shelf) if base_shelf is not None else 0
                ),
                leave_one_out_supported_shelf_life=loo_shelf,
                leave_one_out_statistical_crossing_months=loo_cross,
                diff_supported_shelf_life_months=int(diff),
                note=loo_note,
                mode="row",
                drop_key=str(int(idx)),
            )
        )

    max_delta = max(diffs) if diffs else 0
    summary = _row_summary(max_delta, len(influential))

    return SensitivityReport(
        rows=rows,
        summary=summary,
        baseline_supported_shelf_life=base_shelf,
        mode="row",
        notes=[f"leave-one-out over {len(influential)} influential point(s)"],
    )


def _compute_sensitivity_batch(
    result: StabilityResult,
    data: ValidatedData,
    *,
    horizon: float,
    profile: GuidanceProfile | None,
) -> SensitivityReport:
    """Batch-level leave-one-out sensitivity (v0.8.0).

    For every distinct batch in the data used for the fit (the same
    NaN/value filter the regression layer applies), re-run the
    full analysis with that batch's rows removed and record the
    new supported shelf life.
    """
    base_shelf = result.supported_shelf_life_months

    if "batch" not in data.df.columns:
        return SensitivityReport(
            rows=[],
            summary="need >= 2 distinct batches for leave-one-batch-out",
            baseline_supported_shelf_life=base_shelf,
            mode="batch",
            notes=["data has no 'batch' column"],
        )

    sub = data.df.loc[
        data.df["value"].notna()
        & data.df["time_months"].notna()
        & data.df["batch"].notna()
    ]
    batches_in_fit: list[str] = sorted(
        set(sub["batch"].astype(str).tolist())
    )
    if len(batches_in_fit) < 2:
        return SensitivityReport(
            rows=[],
            summary="need >= 2 distinct batches for leave-one-batch-out",
            baseline_supported_shelf_life=base_shelf,
            mode="batch",
            notes=[
                f"only {len(batches_in_fit)} distinct batch(es) "
                f"in fit; need >= 2 for leave-one-batch-out"
            ],
        )

    rows: List[SensitivityRow] = []
    diffs: List[int] = []
    for batch_name in batches_in_fit:
        try:
            loo_shelf, loo_cross, loo_note, first_row_idx = _leave_one_batch_out(
                result, data, batch_name, horizon=horizon, profile=profile,
            )
        except Exception as exc:  # defensive
            loo_shelf, loo_cross = None, None
            loo_note = f"leave-one-batch-out fit failed: {exc!r}"
            first_row_idx = None
        diff = (
            (loo_shelf - base_shelf)
            if (loo_shelf is not None and base_shelf is not None)
            else 0
        )
        diffs.append(abs(int(diff)))
        rows.append(
            SensitivityRow(
                influential_row_index=(
                    int(first_row_idx)
                    if first_row_idx is not None
                    else 0
                ),
                baseline_supported_shelf_life=(
                    int(base_shelf) if base_shelf is not None else 0
                ),
                leave_one_out_supported_shelf_life=loo_shelf,
                leave_one_out_statistical_crossing_months=loo_cross,
                diff_supported_shelf_life_months=int(diff),
                note=loo_note,
                mode="batch",
                drop_key=str(batch_name),
            )
        )

    max_delta = max(diffs) if diffs else 0
    summary = _batch_summary(max_delta, len(batches_in_fit))

    return SensitivityReport(
        rows=rows,
        summary=summary,
        baseline_supported_shelf_life=base_shelf,
        mode="batch",
        notes=[
            f"leave-one-batch-out over {len(batches_in_fit)} batch(es)"
        ],
    )


def _row_summary(max_delta: int, n_influential: int) -> str:
    """Build the row-mode summary string."""
    if max_delta == 0:
        return "max delta 0 mo; shelf life robust to outliers"
    if max_delta <= 1:
        return (
            f"max delta {max_delta} mo; 1 point changes the shelf life "
            f"by at most 1 month"
        )
    return (
        f"max delta {max_delta} mo; a single point drives the "
        f"shelf-life decision — sensitivity analysis recommended"
    )


def _batch_summary(max_delta: int, n_batches: int) -> str:
    """Build the batch-mode summary string.

    Mirrors the row-mode wording but swaps "outliers" for
    "any single batch" and "a single point" for "a single batch".
    """
    if max_delta == 0:
        return (
            "max delta 0 mo; shelf life robust to dropping any single batch"
        )
    if max_delta <= 1:
        return (
            f"max delta {max_delta} mo; 1 batch changes the shelf life "
            f"by at most 1 month"
        )
    return (
        f"max delta {max_delta} mo; a single batch drives the "
        f"shelf-life decision — sensitivity analysis recommended"
    )


def _refit_and_cross(
    df: pd.DataFrame,
    *,
    condition: str,
    attribute: str,
    horizon: float,
    profile: GuidanceProfile | None,
) -> Tuple[Optional[int], Optional[float]]:
    """Write ``df`` to a temp CSV, run the engine, and return
    ``(supported_shelf_life_months, statistical_crossing_months)``.

    The minimal shared refit helper used by both
    :func:`_leave_one_out` (row mode) and
    :func:`_leave_one_batch_out` (batch mode). Exceptions
    propagate to the caller; both wrappers translate the
    exception into a failed-row report entry so the top-level
    helper can keep going.
    """
    from openpharmastability.shelf_life.engine import analyze

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8",
    )
    df.to_csv(tmp.name, index=False)
    tmp.close()
    tmp_path = tmp.name
    try:
        loo_result = analyze(
            path=tmp_path,
            condition=condition,
            attribute=attribute,
            horizon=float(horizon),
            profile=profile,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return (
        loo_result.supported_shelf_life_months,
        loo_result.statistical_crossing_months,
    )


def _leave_one_out(
    base: StabilityResult,
    data: ValidatedData,
    drop_idx: int,
    *,
    horizon: float,
    profile: GuidanceProfile | None,
) -> Tuple[Optional[int], Optional[float], str]:
    """Drop one row, refit, re-cross, return ``(shelf, crossing, note)``.

    A ``note`` of ``""`` means the refit completed without a
    diagnostic problem. A non-empty ``note`` means the refit was
    skipped (e.g. the row index was out of range against the
    validated frame).
    """
    df = data.df.reset_index(drop=True).copy()
    if drop_idx < 0 or drop_idx >= len(df):
        return None, None, f"row index {drop_idx} out of range (n_rows={len(df)})"
    df_loo = df.drop(index=drop_idx).reset_index(drop=True)
    try:
        shelf, cross = _refit_and_cross(
            df_loo,
            condition=data.condition,
            attribute=getattr(data, "attribute", "assay") or "assay",
            horizon=horizon,
            profile=profile,
        )
    except Exception as exc:  # defensive
        return None, None, f"leave-one-out refit failed: {exc!r}"
    return shelf, cross, ""


def _leave_one_batch_out(
    base: StabilityResult,
    data: ValidatedData,
    batch_name: str,
    *,
    horizon: float,
    profile: GuidanceProfile | None,
) -> Tuple[Optional[int], Optional[float], str, Optional[int]]:
    """Drop one batch, refit, re-cross.

    Returns ``(shelf, crossing, note, first_row_idx)`` where
    ``first_row_idx`` is the FIRST row index of ``batch_name`` in
    the data used for the fit (informational — the v0.8.0
    ``SensitivityRow.influential_row_index`` carries this so
    consumers that read that field see an int). A non-empty
    ``note`` means the refit was skipped.
    """
    sub = data.df.loc[
        data.df["value"].notna()
        & data.df["time_months"].notna()
        & data.df["batch"].notna()
        & (data.df["batch"].astype(str) == str(batch_name))
    ]
    first_row_idx: Optional[int] = (
        int(sub.index[0]) if not sub.empty else None
    )
    df = data.df.copy()
    df_loo = df.loc[
        df["batch"].astype(str) != str(batch_name)
    ].reset_index(drop=True)
    if df_loo.empty or df_loo["batch"].nunique() < 2:
        return (
            None, None,
            f"dropping batch {batch_name!r} left < 2 batches; "
            f"leave-one-batch-out refit skipped",
            first_row_idx,
        )
    try:
        shelf, cross = _refit_and_cross(
            df_loo,
            condition=data.condition,
            attribute=getattr(data, "attribute", "assay") or "assay",
            horizon=horizon,
            profile=profile,
        )
    except Exception as exc:  # defensive
        return (
            None, None,
            f"leave-one-batch-out refit failed: {exc!r}",
            first_row_idx,
        )
    return shelf, cross, "", first_row_idx


# Backwards-compat alias. The original prototype named the helper
# ``compute_sensitivity_with_summary``; keep the name available so
# any in-flight callers continue to work.
def compute_sensitivity_with_summary(*args, **kwargs) -> SensitivityReport:
    return compute_sensitivity(*args, **kwargs)


__all__ = [
    "compute_sensitivity",
    "compute_sensitivity_with_summary",
]
