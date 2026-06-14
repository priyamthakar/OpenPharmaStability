"""Leave-one-out sensitivity analysis for OpenPharmaStability v0.7.0.

Given a :class:`~openpharmastability.contracts.StabilityResult` and the
:class:`~openpharmastability.contracts.ValidatedData` it was computed
from, re-run the full analysis end-to-end with each Cook's-distance
influential point removed and record the resulting supported shelf
life. The result is a
:class:`~openpharmastability.contracts.SensitivityReport` suitable for
the JSON decision record and the HTML report.

The trigger set is ``result.diagnostics.influential_points`` (a list
of row indices in the data used for the fit), produced by
:mod:`openpharmastability.stats.diagnostics`. When the diagnostics
layer did not flag any point the report is empty and the summary
explains that the sensitivity analysis is a no-op.
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


def compute_sensitivity(
    result: StabilityResult,
    data: ValidatedData,
    *,
    horizon: float = 60.0,
) -> SensitivityReport:
    """Leave-one-out sensitivity for each influential point.

    For each row index in ``result.diagnostics.influential_points``,
    re-run the analysis (model selection, poolability, fit, crossing,
    shelf life) on ``data.df`` with that row removed, and record the
    new supported shelf life. The diff is the absolute change vs
    the baseline (``result.supported_shelf_life_months``).

    The summary string is short and human-readable; examples::

        "max delta 0 mo; shelf life robust to outliers"
        "max delta 2 mo; 1 point changes the shelf life"
        "max delta 5 mo; a single point drives the shelf-life
         decision — sensitivity analysis recommended"

    Parameters
    ----------
    result:
        The :class:`StabilityResult` produced by
        :func:`openpharmastability.shelf_life.engine.analyze`. The
        baseline supported shelf life and the trigger set of
        influential points are read from this object.
    data:
        The :class:`ValidatedData` the baseline fit was computed on.
        The leave-one-out refit uses ``data.df`` with one row
        removed.
    horizon:
        Maximum crossing-search time in months. Forwarded to the
        per-refit :func:`~openpharmastability.shelf_life.engine.analyze`
        call. Default ``60.0``.
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
            notes=["diagnostics.influential_points is empty"],
        )

    rows: List[SensitivityRow] = []
    diffs: List[int] = []
    for idx in influential:
        try:
            loo_shelf, loo_cross, loo_note = _leave_one_out(
                result, data, idx, horizon=horizon,
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
            )
        )

    max_delta = max(diffs) if diffs else 0
    if max_delta == 0:
        summary = "max delta 0 mo; shelf life robust to outliers"
    elif max_delta <= 1:
        summary = (
            f"max delta {max_delta} mo; 1 point changes the shelf life "
            f"by at most 1 month"
        )
    else:
        summary = (
            f"max delta {max_delta} mo; a single point drives the "
            f"shelf-life decision — sensitivity analysis recommended"
        )

    return SensitivityReport(
        rows=rows,
        summary=summary,
        baseline_supported_shelf_life=base_shelf,
        notes=[f"leave-one-out over {len(influential)} influential point(s)"],
    )


def _leave_one_out(
    base: StabilityResult,
    data: ValidatedData,
    drop_idx: int,
    *,
    horizon: float,
) -> Tuple[Optional[int], Optional[float], str]:
    """Drop one row, refit, re-cross, return ``(shelf, crossing, note)``.

    A ``note`` of ``""`` means the refit completed without a
    diagnostic problem. A non-empty ``note`` means the refit was
    skipped (e.g. the row index was out of range against the
    validated frame).
    """
    # Lazy imports to avoid a hard dep cycle at module load.
    from openpharmastability.shelf_life.engine import analyze

    df = data.df.reset_index(drop=True).copy()
    if drop_idx < 0 or drop_idx >= len(df):
        return None, None, f"row index {drop_idx} out of range (n_rows={len(df)})"
    df_loo = df.drop(index=drop_idx).reset_index(drop=True)

    # Write the LOO frame to a temp CSV so the engine can ingest it.
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8",
    )
    df_loo.to_csv(tmp.name, index=False)
    tmp.close()
    tmp_path = tmp.name
    try:
        loo_result = analyze(
            path=tmp_path,
            condition=data.condition,
            attribute=getattr(data, "attribute", "assay") or "assay",
            horizon=float(horizon),
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    cross = loo_result.statistical_crossing_months
    shelf = loo_result.supported_shelf_life_months
    return shelf, cross, ""


# Backwards-compat alias. The original prototype named the helper
# ``compute_sensitivity_with_summary``; keep the name available so
# any in-flight callers continue to work.
def compute_sensitivity_with_summary(*args, **kwargs) -> SensitivityReport:
    return compute_sensitivity(*args, **kwargs)


__all__ = [
    "compute_sensitivity",
    "compute_sensitivity_with_summary",
]
