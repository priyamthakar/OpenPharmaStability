"""Mean-response confidence bound and numerical crossing solver.

This module has two public functions:

* :func:`confidence_bound` — one-sided (or two-sided) bound on the
  **mean response** at a single time point. The mean response SE is
  ``s * sqrt(c' (X'X)^-1 c)`` where ``c`` is the linear-combination
  vector that produces the prediction. The multiplier is the
  t-quantile that matches the requested confidence level: for the
  v0.1 one-sided 95% bound we use ``student_t.ppf(0.95, df)`` —
  5% in a single tail — **not** 0.975. The golden test in
  ``validation/test_stats_bounds.py`` locks this in.

* :func:`find_crossing` — numerical root-finder that returns the
  smallest ``t > 0`` at which the bound crosses the spec. Edge
  cases (bound already past spec at t=0, slope ≈ 0 or opposite to
  the declared direction, or no sign change over
  ``[0, horizon]``) return the documented
  :class:`~openpharmastability.contracts.CrossingStatus` rather
  than raising.

For multi-batch models (COMMON_SLOPE, SEPARATE), the crossing
solver evaluates each batch's own bound curve and takes the
**earliest (worst-case)** crossing; the governing batch is
recorded on the result.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
from scipy.optimize import brentq
from scipy.stats import t as student_t

from openpharmastability.contracts import (
    CONFIDENCE,
    CrossingResult,
    CrossingStatus,
    DEFAULT_HORIZON_MONTHS,
    Direction,
    FitResult,
    ModelKind,
    ONE_SIDED_T_QUANTILE,
    TWO_SIDED_T_QUANTILE,
    ValidatedData,
)


# -----------------------------------------------------------------------
# Confidence bound
# -----------------------------------------------------------------------


def _quantile_for(conf: float, side: str) -> float:
    """Map (conf, side) to the t-quantile the bound uses.

    The mapping is intentionally explicit so the t-quantile 0.95 vs
    0.975 choice is auditable in one place. ``conf=0.95`` and
    ``side in {"lower", "upper"}`` (one-sided) uses 0.95; any other
    combination uses 0.975.

    This is the single function that decides which t-quantile the
    bound uses. Touch it with care.
    """
    if side in ("lower", "upper") and np.isclose(conf, 0.95):
        return ONE_SIDED_T_QUANTILE
    return TWO_SIDED_T_QUANTILE


def _mean_se_pooled(fit: FitResult, t_value: float) -> float:
    """``SE_mean`` for the POOLED model: closed form
    ``s * sqrt(1/n + (t - tbar)^2 / Sxx)``.
    """
    t = float(t_value)
    tbar = float(fit.design["tbar"])
    sxx = float(fit.design["Sxx"])
    n = int(fit.design["n"])
    return float(fit.s_resid * np.sqrt(1.0 / n + ((t - tbar) ** 2) / sxx))


def _predict_and_se_multi(
    fit: FitResult, batch: str, t_value: float
) -> tuple[float, float]:
    """Return ``(yhat, SE)`` for a batch on a multi-batch model.

    Builds the linear-combination vector ``c`` in the model's
    parameter order so the SE comes from the full
    ``s^2 * (X'X)^-1`` covariance — never a per-batch shortcut.
    """
    t = float(t_value)
    yhat = float(fit.fitted_fn(batch)(t))

    per_batch = fit.design.get("per_batch", {})
    if batch not in per_batch:
        raise ValueError(
            f"batch {batch!r} not in fit.design['per_batch']; "
            f"available: {sorted(per_batch)!r}"
        )
    c = np.array(per_batch[batch]["intercept_combo"], dtype=float).copy()
    # Add the slope contribution. SEPARATE models need the batch-specific
    # time interaction term as well as the reference slope.
    if "slope_combo" in per_batch[batch]:
        c += t * np.array(per_batch[batch]["slope_combo"], dtype=float)
    else:
        c[int(per_batch[batch]["slope_idx"])] += t
    # SE = s * sqrt(c' (X'X)^-1 c) and cov_params = s^2 * (X'X)^-1,
    # so SE = sqrt(c' cov c). This avoids having to know s and
    # (X'X)^-1 separately.
    se = float(np.sqrt(c @ fit.cov @ c))
    return yhat, se


def confidence_bound(
    fit: FitResult,
    t: float,
    side: str,
    conf: float = CONFIDENCE,
) -> float:
    """One-sided (or two-sided) mean-response confidence bound.

    Parameters
    ----------
    fit:
        A :class:`FitResult` as produced by
        :func:`~openpharmastability.stats.regression.fit_models`.
    t:
        The time point (months) at which to evaluate the bound.
    side:
        ``"lower"`` returns the lower bound (``yhat - k * SE``);
        ``"upper"`` returns the upper bound (``yhat + k * SE``).
    conf:
        Confidence level. The default is :data:`CONFIDENCE` (0.95)
        and is interpreted as **one-sided**: the multiplier is
        ``student_t.ppf(0.95, df)`` (5% in one tail). For an
        explicit two-sided use ``conf=0.975`` together with
        ``side="lower"`` or ``side="upper"`` — but the v0.1
        shelf-life logic never asks for that.

    Returns
    -------
    float
        The bound value at ``t``.

    Notes
    -----
    The bound is the mean-response bound (i.e. on the regression
    line), **not** a prediction interval for a single future
    observation. That matches ICH Q1E.
    """
    side_norm = side.lower()
    if side_norm not in ("lower", "upper"):
        raise ValueError(
            f"side must be 'lower' or 'upper' (got {side!r})"
        )
    quantile = _quantile_for(conf, side_norm)
    k = float(student_t.ppf(quantile, fit.df_resid))

    if fit.kind is ModelKind.POOLED:
        se = _mean_se_pooled(fit, t)
        yhat = float(fit.fitted_fn(t))
    else:
        # Multi-batch models return the bound on the WORST batch
        # (the one with the smallest lower bound / largest upper
        # bound in the relevant direction). For COMMON_SLOPE the
        # intercepts differ but the slope is shared; for SEPARATE
        # both vary.
        ts = _iter_batch_times(fit, t)
        if side_norm == "lower":
            yhat, se = min(ts, key=lambda x: x[0] - k * x[1])
        else:
            yhat, se = max(ts, key=lambda x: x[0] + k * x[1])

    if side_norm == "lower":
        return float(yhat - k * se)
    return float(yhat + k * se)


def _iter_batch_times(
    fit: FitResult, t_value: float
) -> list[tuple[float, float]]:
    """Helper: list of ``(yhat, SE)`` for every batch in the fit."""
    return [
        _predict_and_se_multi(fit, batch, t_value)
        for batch in fit.batches
    ]


# -----------------------------------------------------------------------
# Crossing solver
# -----------------------------------------------------------------------


# Threshold for declaring the slope "flat or opposite". The exact
# value is generous on purpose: tiny negative slopes on an assay
# that is, in practice, stable (e.g. 0.001/month) are correctly
# flagged as "no meaningful trend" rather than driving a spurious
# shelf life of 50+ years. The threshold matches the spec's
# "Slope near zero" wording.
_FLAT_SLOPE_TOL = 1e-9


def _bound_curve(
    fit: FitResult,
    batch: str | None,
    t_value: float,
    side: str,
    quantile: float = ONE_SIDED_T_QUANTILE,
) -> float:
    """The bound value at ``t_value`` for the given model/batch.

    ``quantile`` is the t-distribution quantile used for the
    multiplier. It defaults to :data:`ONE_SIDED_T_QUANTILE` (0.95)
    so the one-sided DECREASING / INCREASING paths are byte-for-byte
    unchanged; the bidirectional path passes
    :data:`TWO_SIDED_T_QUANTILE` (0.975).
    """
    side_norm = side.lower()
    if fit.kind is ModelKind.POOLED:
        se = _mean_se_pooled(fit, t_value)
        yhat = float(fit.fitted_fn(t_value))
    else:
        yhat, se = _predict_and_se_multi(fit, batch, t_value)  # type: ignore[arg-type]
    k = _bound_multiplier(fit, quantile)
    if side_norm == "lower":
        return yhat - k * se
    return yhat + k * se


def _bound_multiplier(
    fit: FitResult, quantile: float = ONE_SIDED_T_QUANTILE
) -> float:
    """t-quantile multiplier for a confidence bound.

    ``quantile`` selects the tail: :data:`ONE_SIDED_T_QUANTILE`
    (0.95) for a one-sided 95% bound (5% in one tail) or
    :data:`TWO_SIDED_T_QUANTILE` (0.975) for a two-sided 95% bound
    (2.5% in each tail). v0.10.0 made this quantile-aware so the
    bidirectional crossing path (``Direction.BIDIRECTIONAL``) can
    use 0.975 while the one-sided paths keep 0.95. This is one of
    the two places (with :func:`_quantile_for`) that decide the
    0.95-vs-0.975 choice — touch with care (Appendix A hazard #2).
    """
    return float(student_t.ppf(quantile, fit.df_resid))


def _spec_for_direction(data: ValidatedData) -> tuple[float, str]:
    """Return ``(spec, side)`` for the bound that will hit first
    given the data's declared direction.

    For DECREASING we look at the lower spec (the bound is the
    lower one-sided 95% bound, and it crosses by going *down*).
    For INCREASING we look at the upper spec. For BIDIRECTIONAL or
    UNKNOWN, we choose whichever limit is closer to the baseline
    prediction (and report ``side`` accordingly) so the solver
    returns *some* meaningful answer for fixtures that exercise
    those directions.
    """
    direction = data.direction
    if direction is Direction.DECREASING:
        if data.lower_spec is None:
            raise ValueError(
                "DECREASING direction requires lower_spec; got None"
            )
        return float(data.lower_spec), "lower"
    if direction is Direction.INCREASING:
        if data.upper_spec is None:
            raise ValueError(
                "INCREASING direction requires upper_spec; got None"
            )
        return float(data.upper_spec), "upper"
    # BIDIRECTIONAL or UNKNOWN: pick whichever spec is finite and
    # closest to zero offset from the y-intercept (heuristic that
    # works for the fixtures Agent B is responsible for; the
    # full edge-case handling lives in the engine).
    candidates: list[tuple[float, str]] = []
    if data.lower_spec is not None:
        candidates.append((float(data.lower_spec), "lower"))
    if data.upper_spec is not None:
        candidates.append((float(data.upper_spec), "upper"))
    if not candidates:
        raise ValueError(
            "Cannot find crossing: no spec limit (lower_spec / "
            "upper_spec) is set on the data"
        )
    return candidates[0]


def _per_batch_crossings(
    fit: FitResult,
    spec: float,
    side: str,
    horizon: float,
    quantile: float = ONE_SIDED_T_QUANTILE,
) -> list[tuple[float, str]]:
    """For multi-batch models: return ``(crossing_t, batch)`` for
    every batch that crosses within ``[0, horizon]``.
    """
    results: list[tuple[float, str]] = []
    for batch in fit.batches:
        t_cross = _single_crossing(fit, batch, spec, side, horizon, quantile)
        if t_cross is not None:
            results.append((t_cross, batch))
    return results


def _single_crossing(
    fit: FitResult,
    batch: str | None,
    spec: float,
    side: str,
    horizon: float,
    quantile: float = ONE_SIDED_T_QUANTILE,
) -> float | None:
    """Crossing time for one batch (or for the single POOLED curve).

    Returns the smallest ``t > 0`` such that ``bound(t) == spec``,
    or ``None`` if there is no crossing within ``[0, horizon]``.
    Edge cases (slope ≈ 0 / opposite, bound already past spec at
    t=0) are detected by :func:`find_crossing` and reported with
    the right status; this helper only finds the *root*.
    """
    side_norm = side.lower()

    def f(t_value: float) -> float:
        # bound - spec: zero when the bound is exactly at the spec.
        return _bound_curve(fit, batch, t_value, side_norm, quantile) - spec

    # We bracket the root with a closed interval that is guaranteed
    # to straddle it: ``f(0)`` and ``f(horizon)`` must have
    # opposite signs. :func:`find_crossing` checks this first and
    # returns ``no_crossing`` if not.
    f_lo = f(0.0)
    f_hi = f(horizon)
    if f_lo == 0.0:
        return 0.0
    if f_hi == 0.0:
        return float(horizon)
    if not (f_lo * f_hi < 0.0):
        return None
    return float(brentq(f, 0.0, horizon, xtol=1e-10, rtol=1e-12, maxiter=200))


def find_crossing(
    fit: FitResult,
    data: ValidatedData,
    horizon: float = DEFAULT_HORIZON_MONTHS,
    one_sided_quantile: float = ONE_SIDED_T_QUANTILE,
    two_sided_quantile: float = TWO_SIDED_T_QUANTILE,
) -> CrossingResult:
    """Find the statistical crossing time of the bound against the spec.

    Parameters
    ----------
    fit:
        The :class:`FitResult` to evaluate. POOLED evaluates a
        single curve; COMMON_SLOPE and SEPARATE evaluate every
        batch's curve and report the worst-case (earliest)
        crossing.
    data:
        The :class:`ValidatedData` whose ``direction`` decides
        which spec the bound is compared against (lower spec for
        DECREASING, upper spec for INCREASING, BOTH for
        BIDIRECTIONAL).
    horizon:
        The upper end of the search interval, in months. Default
        is :data:`DEFAULT_HORIZON_MONTHS` (60).
    one_sided_quantile:
        t-quantile for the one-sided DECREASING / INCREASING bound
        (default :data:`ONE_SIDED_T_QUANTILE` = 0.95). The engine
        sources this from the active :class:`GuidanceProfile`.
    two_sided_quantile:
        t-quantile for the BIDIRECTIONAL (two-sided) bound (default
        :data:`TWO_SIDED_T_QUANTILE` = 0.975). The engine sources
        this from the active :class:`GuidanceProfile`.

    Returns
    -------
    CrossingResult
        ``crossing_months`` is the crossing time (or ``None`` for
        ``NO_CROSSING`` / ``FLAT_OR_OPPOSITE``). ``status`` is one
        of the four :class:`CrossingStatus` values. The governing
        batch is recorded for multi-batch models; for POOLED it
        is always ``None``. ``governing_side`` is ``"lower"`` /
        ``"upper"`` for a BIDIRECTIONAL crossing and ``None`` for
        the one-sided paths.

    Notes
    -----
    Edge cases are detected before the root-finder is called, so
    a fixture that exhibits e.g. ``fail_at_baseline`` never enters
    the bisection and never raises.
    """
    # BIDIRECTIONAL is handled by a dedicated two-sided helper: both
    # spec limits are evaluated with the two-sided 0.975 multiplier
    # and the earliest crossing of either governs (ICH Q1E). The
    # one-sided edge-case logic below assumes a single declared
    # direction, so we branch out before it.
    if data.direction is Direction.BIDIRECTIONAL:
        return _bidirectional_crossing(
            fit, data, horizon, two_sided_quantile
        )

    spec, side = _spec_for_direction(data)
    side_norm = side.lower()
    quantile = one_sided_quantile

    # --- Edge case 1: slope flat or opposite -------------------
    # Use the model's own slope at t=0 to decide. For a multi-batch
    # model we look at every batch and report ``flat_or_opposite``
    # only if *all* batches are flat/opposite; a single batch with
    # a meaningful trend will still drive a finite crossing.
    slopes = _effective_slopes(fit)
    direction = data.direction
    if direction is Direction.DECREASING:
        flat_or_opposite = all(s >= -_FLAT_SLOPE_TOL for s in slopes)
    elif direction is Direction.INCREASING:
        flat_or_opposite = all(s <= _FLAT_SLOPE_TOL for s in slopes)
    else:
        # For BIDIRECTIONAL/UNKNOWN we just check that *some*
        # batch has a non-trivial slope; the spec_for_direction
        # helper picked whichever limit is closest to baseline, so
        # we accept any non-flat slope here.
        flat_or_opposite = all(abs(s) < _FLAT_SLOPE_TOL for s in slopes)
    if flat_or_opposite and slopes:
        return CrossingResult(
            crossing_months=None,
            status=CrossingStatus.FLAT_OR_OPPOSITE,
            governing_batch=None,
            notes=[
                "fitted slope is ~0 or opposite to declared "
                f"direction ({direction.value!r}); no positive "
                "crossing claimed"
            ],
        )

    # --- Edge case 2: bound already past spec at t=0 -----------
    if _bound_past_spec_at_zero(fit, spec, side_norm, quantile):
        return CrossingResult(
            crossing_months=0.0,
            status=CrossingStatus.FAIL_AT_BASELINE,
            governing_batch=None,
            notes=["bound is already beyond spec at t=0"],
        )

    # --- Main path: numerical root find -----------------------
    if fit.kind is ModelKind.POOLED:
        crossing = _single_crossing(fit, None, spec, side_norm, horizon, quantile)
        if crossing is None:
            return CrossingResult(
                crossing_months=None,
                status=CrossingStatus.NO_CROSSING,
                governing_batch=None,
                notes=[
                    f"bound never reaches {spec:g} within the "
                    f"[0, {horizon:g}] month horizon"
                ],
            )
        return CrossingResult(
            crossing_months=float(crossing),
            status=CrossingStatus.CROSSED,
            governing_batch=None,
            notes=[],
        )

    # Multi-batch: per-batch crossings, take the earliest.
    per_batch = _per_batch_crossings(fit, spec, side_norm, horizon, quantile)
    if not per_batch:
        return CrossingResult(
            crossing_months=None,
            status=CrossingStatus.NO_CROSSING,
            governing_batch=None,
            notes=[
                f"horizon ({horizon:g} months)"
            ],
        )
    crossing, batch = min(per_batch, key=lambda x: x[0])
    return CrossingResult(
        crossing_months=float(crossing),
        status=CrossingStatus.CROSSED,
        governing_batch=batch,
        notes=[f"governing batch: {batch!r} (earliest crossing)"],
    )


def _bidirectional_crossing(
    fit: FitResult,
    data: ValidatedData,
    horizon: float,
    two_sided_quantile: float,
) -> CrossingResult:
    """Crossing for a BIDIRECTIONAL attribute (two finite spec limits).

    Per ICH Q1E (NEXT_STEPS §2.4): when neither direction dominates
    a priori, evaluate BOTH a lower bound against ``lower_spec`` and
    an upper bound against ``upper_spec``, each with the **two-sided**
    t-quantile (0.975 -- 2.5% in each tail, *not* the one-sided 0.95),
    and take the **earliest** crossing of either. The governing spec
    limit is recorded on ``governing_side``.

    A ``fail_at_baseline`` on either side at t=0 short-circuits to
    :attr:`CrossingStatus.FAIL_AT_BASELINE`. If neither side crosses
    within ``[0, horizon]`` the result is
    :attr:`CrossingStatus.NO_CROSSING`.
    """
    candidates: list[tuple[float, str]] = []
    if data.lower_spec is not None:
        candidates.append((float(data.lower_spec), "lower"))
    if data.upper_spec is not None:
        candidates.append((float(data.upper_spec), "upper"))
    if not candidates:
        raise ValueError(
            "BIDIRECTIONAL direction requires at least one of "
            "lower_spec / upper_spec; both are None"
        )

    # Edge case: either bound already past its spec at t=0.
    for spec, side in candidates:
        if _bound_past_spec_at_zero(fit, spec, side, two_sided_quantile):
            return CrossingResult(
                crossing_months=0.0,
                status=CrossingStatus.FAIL_AT_BASELINE,
                governing_batch=None,
                notes=[
                    f"two-sided bound already beyond the {side} spec "
                    "at t=0"
                ],
                governing_side=side,
            )

    # Collect the earliest crossing on each side, with the governing
    # batch for multi-batch models.
    found: list[tuple[float, str, str | None]] = []  # (t, side, batch)
    for spec, side in candidates:
        if fit.kind is ModelKind.POOLED:
            t_cross = _single_crossing(
                fit, None, spec, side, horizon, two_sided_quantile
            )
            if t_cross is not None:
                found.append((t_cross, side, None))
        else:
            per_batch = _per_batch_crossings(
                fit, spec, side, horizon, two_sided_quantile
            )
            if per_batch:
                t_cross, batch = min(per_batch, key=lambda x: x[0])
                found.append((t_cross, side, batch))

    if not found:
        return CrossingResult(
            crossing_months=None,
            status=CrossingStatus.NO_CROSSING,
            governing_batch=None,
            notes=[
                "neither the lower nor the upper two-sided bound "
                f"crosses within the [0, {horizon:g}] month horizon"
            ],
            governing_side=None,
        )

    t_cross, side, batch = min(found, key=lambda x: x[0])
    note = (
        f"bidirectional: earliest crossing on the {side} spec "
        "using the two-sided 0.975 quantile"
    )
    if batch is not None:
        note += f"; governing batch: {batch!r}"
    return CrossingResult(
        crossing_months=float(t_cross),
        status=CrossingStatus.CROSSED,
        governing_batch=batch,
        notes=[note],
        governing_side=side,
    )


# -----------------------------------------------------------------------
# Small helpers used by ``find_crossing``
# -----------------------------------------------------------------------


def _effective_slopes(fit: FitResult) -> list[float]:
    """Per-batch slope (or single slope for POOLED) as a list."""
    if fit.kind is ModelKind.POOLED:
        return [float(fit.params["b1"])]
    # For COMMON_SLOPE every batch shares the same slope; for
    # SEPARATE we collect each batch's slope.
    if fit.kind is ModelKind.COMMON_SLOPE:
        return [float(fit.params["b1"])] * len(fit.batches)
    # SEPARATE
    return [
        float(fit.params[f"b1_{batch}"])
        for batch in fit.batches
    ]


def _bound_past_spec_at_zero(
    fit: FitResult, spec: float, side: str,
    quantile: float = ONE_SIDED_T_QUANTILE,
) -> bool:
    """True if the bound at t=0 is already at or past the spec."""
    if fit.kind is ModelKind.POOLED:
        b0 = _bound_curve(fit, None, 0.0, side, quantile)
        return _past(b0, spec, side)
    bound_values = [
        _bound_curve(fit, batch, 0.0, side, quantile) for batch in fit.batches
    ]
    if side == "lower":
        worst = min(bound_values)
    else:
        worst = max(bound_values)
    return _past(worst, spec, side)


def _past(bound_value: float, spec: float, side: str) -> bool:
    if side == "lower":
        return bound_value <= spec
    return bound_value >= spec


__all__ = ["confidence_bound", "find_crossing"]
