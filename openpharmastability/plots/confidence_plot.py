"""Confidence-bound plot for OpenPharmaStability v0.3.1.

The plot is the centerpiece of the report. It shows the observed data
points, the fitted regression line(s), the one-sided 95% mean-response
confidence band, the relevant specification limit, the statistical
crossing point, and the extrapolation region beyond the observed data.

v0.3.1 hotfix vs v0.3.0
-----------------------
Two bugs in the multi-batch / direction-handling code path were fixed:

1. The multi-batch branch used to call
   ``confidence_bound(fit, t, "lower")`` inside its per-batch loop, but
   :func:`openpharmastability.stats.bounds.confidence_bound` ignores
   the ``batch`` argument and always returns the worst-case bound
   across batches. As a result, the same worst-case band was drawn N
   times with N different colors. The plot now keeps the per-batch
   **fit lines** (which are correct, because :func:`_yhat` is
   batch-aware) and draws a **single** neutral-colored worst-case
   band on top.

2. The plot hard-coded a "worst-case lower bound" emphasis and a
   "lower spec" framing. For :attr:`Direction.INCREASING` attributes
   (degradants, impurities) the binding bound is the **upper** one
   against ``upper_spec``. The plot now derives a ``critical_side``
   from :attr:`StabilityResult.direction` and surfaces it in the
   band legend label, so the reader can see which bound is binding
   without changing the band's symmetric shape.
"""
from __future__ import annotations

import os
from typing import Optional

import matplotlib

matplotlib.use("Agg")  # headless-safe; never call plt.show() in the report
import matplotlib.pyplot as plt
import numpy as np

from openpharmastability.contracts import (
    CrossingStatus,
    Direction,
    FitResult,
    ModelKind,
    StabilityResult,
    ValidatedData,
)
from openpharmastability.stats.bounds import confidence_bound


# Distinct colors for up to 6 batches; the spec only requires 3 but
# we allow headroom.
_BATCH_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _yhat(fit: FitResult, batch: Optional[str], t: np.ndarray) -> np.ndarray:
    """Return the fitted mean response at each t.

    POOLED: one curve. COMMON_SLOPE / SEPARATE: per-batch curves.
    """
    if fit.kind is ModelKind.POOLED:
        return np.array([fit.fitted_fn(float(ti)) for ti in t])
    # Multi-batch: caller is expected to iterate batches.
    if batch is None:
        raise ValueError("multi-batch model requires a batch argument")
    fn = fit.fitted_fn(batch)
    return np.array([fn(float(ti)) for ti in t])


def _bound_at(
    fit: FitResult,
    batch: Optional[str],
    t: np.ndarray,
    side: str,
) -> np.ndarray:
    """Bound values at each t.

    For multi-batch models the result is the worst-case across
    batches (smallest lower bound or largest upper bound in the
    requested direction) — see :func:`confidence_bound`. The
    ``batch`` argument is accepted for API stability but is ignored;
    callers that need a per-batch curve should use :func:`_yhat`.
    """
    return np.array([confidence_bound(fit, float(ti), side) for ti in t])


def _observed_max_time(data: ValidatedData) -> float:
    return float(max(data.time_points)) if data.time_points else 0.0


def _t_grid(
    data: ValidatedData,
    crossing: Optional[float],
    pad: float = 6.0,
) -> np.ndarray:
    """Time grid covering observed data and (if any) the crossing point."""
    t_max_obs = _observed_max_time(data)
    t_max = t_max_obs + pad
    if crossing is not None and crossing > t_max_obs:
        t_max = crossing + pad
    t_max = max(t_max, t_max_obs + 1.0)
    return np.linspace(0.0, float(t_max), 400)


def _batch_color(batch: str, all_batches: list[str]) -> str:
    try:
        idx = sorted(all_batches).index(batch) % len(_BATCH_COLORS)
    except ValueError:
        idx = 0
    return _BATCH_COLORS[idx]


def _critical_side(direction: Direction) -> Optional[str]:
    """The bound side that binds shelf life for the given direction.

    * DECREASING -> ``"lower"`` (assay-like attributes whose values
      fall toward a lower spec; the lower one-sided 95% bound is the
      binding one).
    * INCREASING -> ``"upper"`` (degradant / impurity attributes whose
      values rise toward an upper spec; the upper one-sided 95% bound
      is the binding one).
    * BIDIRECTIONAL / UNKNOWN -> ``None`` (no single critical side).
    """
    if direction is Direction.DECREASING:
        return "lower"
    if direction is Direction.INCREASING:
        return "upper"
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def make_confidence_plot(
    result: StabilityResult,
    data: ValidatedData,
    out_path: str,
) -> str:
    """Render the confidence-bound plot to ``out_path`` and return its path.

    Parameters
    ----------
    result:
        The :class:`StabilityResult` whose model, fit, and crossing
        drive the figure. The plot draws the **selected** model
        (``result.model``) and the corresponding fit (``result.fit``).
        :attr:`StabilityResult.direction` is used to label the
        critical bound: lower for DECREASING, upper for INCREASING,
        none for BIDIRECTIONAL / UNKNOWN.
    data:
        The :class:`ValidatedData` providing the observed points and
        the spec limits.
    out_path:
        Destination path. The directory is created if missing.

    Returns
    -------
    str
        The absolute path of the saved PNG.
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)

    fit = result.fit
    t_obs_max = _observed_max_time(data)
    crossing_t = result.crossing.crossing_months
    t = _t_grid(data, crossing_t)
    critical = _critical_side(result.direction)

    fig, ax = plt.subplots(figsize=(9.0, 5.5), dpi=120)

    # --- 1. Observed data points by batch -------------------------
    batches_in_data = sorted(data.df["batch"].dropna().unique().tolist())
    for batch in batches_in_data:
        sub = data.df[data.df["batch"] == batch]
        color = _batch_color(batch, batches_in_data)
        ax.scatter(
            sub["time_months"],
            sub["value"],
            s=42,
            color=color,
            edgecolor="white",
            linewidth=0.6,
            alpha=0.85,
            label=f"batch {batch}",
            zorder=3,
        )

    # --- 2. Fitted line(s) and 3. confidence band -----------------
    # The band is always symmetric (lower_worst, upper_worst). The
    # attribute's *direction* is reflected in the "critical bound"
    # annotation, NOT in the band's geometry: the band is a
    # two-sided mean envelope regardless of direction.
    if critical is not None:
        bound_label = (
            "one-sided 95% worst-case mean band "
            f"(critical bound: {critical})"
        )
    else:
        bound_label = (
            "one-sided 95% worst-case mean band "
            "(no single critical side)"
        )

    if fit.kind is ModelKind.POOLED:
        yhat = _yhat(fit, None, t)
        lower = _bound_at(fit, None, t, "lower")
        upper = _bound_at(fit, None, t, "upper")
        ax.plot(t, yhat, color="black", linewidth=1.6, label="fit (pooled)", zorder=4)
        ax.fill_between(
            t, lower, upper, color="#888888", alpha=0.20,
            label=bound_label, zorder=2,
        )
    else:
        # Multi-batch: per-batch fit lines + ONE worst-case band.
        # ``_yhat`` is batch-aware so the fit lines are correct per
        # batch. The band is the worst-case across batches (smallest
        # lower / largest upper), so we draw it ONCE in a neutral
        # color to avoid the v0.3.0 bug of stacking N identical
        # worst-case bands in N different colors.
        for batch in fit.batches:
            color = _batch_color(batch, fit.batches)
            yhat_b = _yhat(fit, batch, t)
            ax.plot(
                t, yhat_b, color=color, linewidth=1.4,
                label=f"fit ({batch})", zorder=4,
            )
        lower_worst = _bound_at(fit, None, t, "lower")
        upper_worst = _bound_at(fit, None, t, "upper")
        ax.fill_between(
            t, lower_worst, upper_worst, color="#888888", alpha=0.20,
            label=bound_label, zorder=2,
        )

    # --- 4. Specification limit line(s) ---------------------------
    if data.lower_spec is not None:
        ax.axhline(
            data.lower_spec, color="#d62728", linestyle="--", linewidth=1.2,
            label=f"lower spec = {data.lower_spec:g}", zorder=4,
        )
    if data.upper_spec is not None:
        ax.axhline(
            data.upper_spec, color="#2ca02c", linestyle="--", linewidth=1.2,
            label=f"upper spec = {data.upper_spec:g}", zorder=4,
        )

    # --- 5. Crossing marker (if any) ------------------------------
    if (
        result.crossing.status is CrossingStatus.CROSSED
        and crossing_t is not None
    ):
        ax.axvline(
            crossing_t, color="#9467bd", linestyle=":", linewidth=1.4,
            label=f"crossing ≈ {crossing_t:.1f} mo", zorder=4,
        )
        # Annotate with the crossing time at the top of the chart.
        ax.annotate(
            f"crossing: {crossing_t:.1f} mo",
            xy=(crossing_t, ax.get_ylim()[1] if ax.get_ylim()[1] != 0 else 100),
            xytext=(crossing_t + 0.5, ax.get_ylim()[1] * 0.97
                    if ax.get_ylim()[1] != 0 else 100),
            fontsize=9, color="#9467bd",
        )

    # --- 6. Extrapolation shading ---------------------------------
    if t_obs_max > 0 and t_obs_max < float(t.max()):
        ax.axvspan(
            t_obs_max, float(t.max()),
            color="#ffd166", alpha=0.18, label="extrapolation", zorder=1,
        )

    # --- Status-based captions ------------------------------------
    status = result.crossing.status
    if status is CrossingStatus.NO_CROSSING:
        ax.text(
            0.02, 0.97, "no crossing within horizon",
            transform=ax.transAxes, fontsize=10, color="#444",
            verticalalignment="top",
        )
    elif status is CrossingStatus.FAIL_AT_BASELINE:
        ax.text(
            0.02, 0.97, "FAIL at baseline (t = 0)",
            transform=ax.transAxes, fontsize=10, color="#d62728",
            verticalalignment="top", fontweight="bold",
        )
    elif status is CrossingStatus.FLAT_OR_OPPOSITE:
        ax.text(
            0.02, 0.97, "slope ≈ 0 or opposite to declared direction",
            transform=ax.transAxes, fontsize=10, color="#9467bd",
            verticalalignment="top",
        )

    # --- Cosmetics -------------------------------------------------
    ax.set_xlabel("time (months)")
    ax.set_ylabel(f"{result.attribute} value")
    title = (
        f"{result.attribute} @ {result.condition}  —  "
        f"model: {result.model.value}  —  "
        f"poolability: {result.poolability.decision.value}"
    )
    ax.set_title(title, fontsize=11)
    if result.supported_shelf_life_months is not None:
        ax.text(
            0.98, 0.02,
            f"supported {result.deliverable_term}: "
            f"{result.supported_shelf_life_months} mo",
            transform=ax.transAxes, fontsize=10, color="#222",
            horizontalalignment="right", verticalalignment="bottom",
        )
    ax.legend(loc="best", fontsize=8, framealpha=0.85)
    ax.grid(True, alpha=0.3, linestyle=":")

    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return os.path.abspath(out_path)


__all__ = ["make_confidence_plot"]
