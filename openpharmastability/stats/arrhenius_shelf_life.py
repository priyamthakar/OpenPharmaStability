"""v0.8.0 Arrhenius-driven shelf-life prediction.

Given a :class:`~openpharmastability.contracts.ValidatedData` for ONE
attribute at ONE long-term condition, fit the Arrhenius equation
``ln(k) = ln(A) - Ea / (R * T)`` to per-temperature rates derived from
the data (the v0.5.0 / v0.7.0 step), then use the rate extrapolated to
the user-supplied storage temperature to predict a model-based
**statistical crossing time** and **supported shelf life** against the
attribute's spec.

The prediction is a **direct closed-form linear model**:

    predicted_value(t) = b0_estimate + slope * t

where ``slope = -rate`` for :data:`Direction.DECREASING` attributes
(e.g. ``assay``) and ``slope = +rate`` for
:data:`Direction.INCREASING` attributes (e.g. a degradant growing with
time). The crossing against the spec is a one-line root find (the
bound math is unnecessary: the model is a deterministic linear
prediction with a known slope). The result is rounded DOWN to whole
months, matching the Q1E rounding convention used by the rest of the
engine.

The y-intercept ``b0_estimate`` is the mean of the rows at
``time_months == 0`` (the baseline at the long-term condition); when
no baseline row exists it falls back to the mean of the first 10% of
rows by time. The Arrhenius extrapolation is a **model-based
prediction** of how fast the attribute degrades at the storage
temperature, NOT a re-fit of the long-term Q1E ANCOVA — see the
:class:`ArrheniusShelfLife` docstring and the engine's "Exploratory"
section in the HTML report for the distinction.
"""
from __future__ import annotations

import math
from typing import List, Optional

import pandas as pd

from openpharmastability.contracts import (
    ArrheniusResult,
    ArrheniusShelfLife,
    Direction,
    ValidatedData,
)


# Slope tolerance below which the prediction is treated as "flat" and
# no positive crossing is claimed. Mirrors the threshold used in
# ``stats/bounds.py::_FLAT_SLOPE_TOL`` so the two paths agree.
_FLAT_SLOPE_TOL: float = 1e-9

# Fraction of rows (by time, ascending) used as the baseline fallback
# when no ``time_months == 0`` row exists. 10% matches the v0.1
# "first 10% by time" convention used elsewhere in the engine.
_BASELINE_FALLBACK_FRACTION: float = 0.10


__all__ = ["predict_arrhenius_shelf_life"]


def _estimate_baseline(df: pd.DataFrame) -> Optional[float]:
    """Return the estimated y-intercept (b0) for the long-term baseline.

    Strategy
    --------
    1. If there is at least one row with ``time_months == 0``, return
       the mean of those rows' values. This is the "true" t=0
       baseline at the long-term condition.
    2. Otherwise, return the mean of the values in the first
       :data:`_BASELINE_FALLBACK_FRACTION` of rows (sorted ascending
       by time). This is a best-effort fallback for inputs that do
       not carry an explicit t=0 row (e.g. a stability arm that only
       sampled at t=1, 3, 6, ...).
    3. Returns ``None`` only when the frame has no usable rows.
    """
    if df is None or df.empty or "value" not in df.columns:
        return None
    work = df.dropna(subset=["value", "time_months"])
    if work.empty:
        return None
    baseline_rows = work[work["time_months"] == 0.0]
    if not baseline_rows.empty:
        return float(baseline_rows["value"].mean())
    # Fallback: first 10% by time.
    sorted_work = work.sort_values("time_months", kind="mergesort")
    n_take = max(1, int(math.ceil(len(sorted_work) * _BASELINE_FALLBACK_FRACTION)))
    head = sorted_work.head(n_take)
    if head.empty:
        return None
    return float(head["value"].mean())


def _temperatures_from_source(source: ArrheniusResult) -> List[float]:
    """Extract the per-temperature float list from the Arrhenius
    fit's echoed input.

    The :class:`ArrheniusResult` stores the per-temperature rate echo
    in ``rate_by_temp_C`` with stringified keys (matches the v0.5.0
    contract). The ArrheniusShelfLife contract expects a
    ``list[float]`` of temperatures used; we reconstruct it from the
    echo dict, in ascending order.
    """
    out: List[float] = []
    for k in source.rate_by_temp_C.keys():
        try:
            out.append(float(k))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def predict_arrhenius_shelf_life(
    data: ValidatedData,
    storage_temp_C: float = 25.0,
    R: float = 8.314,
    horizon: float = 60.0,
) -> ArrheniusShelfLife:
    """Predict the long-term shelf life from Arrhenius kinetics.

    Procedure
    ---------
    1. **Arrhenius fit.** Reuse the v0.5.0 / v0.7.0
       :func:`openpharmastability.shelf_life.engine._compute_arrhenius`
       helper to build the per-temperature rate dict and fit the
       Arrhenius equation. When fewer than 2 distinct temperatures
       are available (or the direction is BIDIRECTIONAL/UNKNOWN, or
       the data have no spec), the helper returns ``None``; we mirror
       that with an :class:`ArrheniusShelfLife` whose predictive
       fields are all ``None`` and whose ``notes`` describe the skip.
    2. **Slope extraction.** The fitted
       ``predicted_k_at_storage`` is a positive rate (1/month). We
       convert it to the slope of the linear prediction model
       ``predicted_value(t) = b0 + slope * t`` by applying the sign
       of the declared direction (``-1`` for DECREASING, ``+1`` for
       INCREASING). When the direction is BIDIRECTIONAL/UNKNOWN the
       slope is ambiguous and the prediction is skipped.
    3. **Baseline (b0) estimate.** The y-intercept is the mean of
       the rows at ``time_months == 0`` in ``data.df`` (the long-term
       baseline at the user-requested condition). When no t=0 row
       exists the helper falls back to the mean of the first 10% of
       rows by time.
    4. **Spec + crossing.** For DECREASING attributes the spec is
       ``data.lower_spec``; for INCREASING it is ``data.upper_spec``.
       The crossing time is the closed-form root of
       ``b0 + slope * t == spec`` and is computed as
       ``t_cross = (spec - b0) / slope``. If the spec is missing
       (``None``) the prediction is skipped. If the slope is
       effectively zero (``abs(slope) < _FLAT_SLOPE_TOL``) or has the
       wrong sign for the declared direction, no positive crossing
       is claimed and a note is appended.
    5. **Rounding.** The supported shelf life is
       ``int(math.floor(t_cross))``, matching the Q1E rounding
       convention used by the rest of the engine. When the crossing
       time falls outside ``[0, horizon]`` (or the baseline is
       already at/past the spec), the function records the
       appropriate status and the supported shelf life is ``None``
       (or 0 for fail-at-baseline). The caller can read the
       ``predicted_statistical_crossing_months`` field for the raw
       crossing time regardless of the status.

    Parameters
    ----------
    data:
        The :class:`ValidatedData` produced by
        :func:`openpharmastability.data.schema.validate_and_select`
        for the single attribute + long-term condition the user
        asked to analyze.
    storage_temp_C:
        Storage temperature the rate is extrapolated TO (°C, default
        25.0). The fit itself is on the stress temperatures in the
        data; this is the ``T_storage`` used in the
        ``predicted_k_at_storage`` field on the
        :class:`ArrheniusResult`.
    R:
        Universal gas constant, J / (mol * K). IUPAC default 8.314.
        Only override for textbook problems.
    horizon:
        Upper bound of the crossing search, in months (default
        60.0 — the v0.1 / v0.5 / v0.7 default). When the model-based
        crossing time exceeds the horizon, the function records
        ``no_crossing`` and the supported shelf life is ``None``.

    Returns
    -------
    ArrheniusShelfLife
        The model-based prediction. The ``source_arrhenius`` field
        carries the underlying :class:`ArrheniusResult` (handy for
        the JSON record and HTML cross-links). All predictive fields
        (``predicted_k_at_storage``,
        ``predicted_statistical_crossing_months``,
        ``predicted_shelf_life_months``) are populated on the
        happy path; on a skip they are left at ``None`` and the
        ``notes`` describe why.
    """
    notes: list[str] = []

    # ---- 1) Direction gate. BIDIRECTIONAL/UNKNOWN have an
    #        ambiguous slope sign, so the prediction is skipped.
    if (
        data.direction is Direction.BIDIRECTIONAL
        or data.direction is Direction.UNKNOWN
    ):
        notes.append(
            "Arrhenius-driven shelf-life prediction skipped: "
            f"direction is {data.direction.value!r}; slope sign "
            "is ambiguous."
        )
        return ArrheniusShelfLife(
            predicted_k_at_storage=0.0,  # structural: not a real rate
            predicted_statistical_crossing_months=None,
            predicted_shelf_life_months=None,
            storage_temp_C=float(storage_temp_C),
            temperatures_used=[],
            rates_per_temp={},
            n_temps=0,
            source_arrhenius=None,
            notes=notes,
        )

    # ---- 2) Spec gate. Without a finite spec on the relevant side
    #        the closed-form crossing has no root.
    if data.direction is Direction.DECREASING and data.lower_spec is None:
        notes.append(
            "Arrhenius-driven shelf-life prediction skipped: "
            "DECREASING direction requires a finite lower_spec; "
            "got None."
        )
        return ArrheniusShelfLife(
            predicted_k_at_storage=0.0,
            predicted_statistical_crossing_months=None,
            predicted_shelf_life_months=None,
            storage_temp_C=float(storage_temp_C),
            temperatures_used=[],
            rates_per_temp={},
            n_temps=0,
            source_arrhenius=None,
            notes=notes,
        )
    if data.direction is Direction.INCREASING and data.upper_spec is None:
        notes.append(
            "Arrhenius-driven shelf-life prediction skipped: "
            "INCREASING direction requires a finite upper_spec; "
            "got None."
        )
        return ArrheniusShelfLife(
            predicted_k_at_storage=0.0,
            predicted_statistical_crossing_months=None,
            predicted_shelf_life_months=None,
            storage_temp_C=float(storage_temp_C),
            temperatures_used=[],
            rates_per_temp={},
            n_temps=0,
            source_arrhenius=None,
            notes=notes,
        )

    # ---- 3) Arrhenius fit. Reuse the v0.5.0 / v0.7.0 helper. The
    #        helper is private to ``shelf_life.engine`` but the spec
    #        for v0.8.0 explicitly authorizes this reuse so the
    #        per-temperature rate computation stays single-sourced.
    try:
        from openpharmastability.shelf_life.engine import (
            _compute_arrhenius as _engine_compute_arrhenius,
        )
    except Exception as exc:  # pragma: no cover -- module missing
        notes.append(
            f"Arrhenius-driven shelf-life prediction failed: could "
            f"not import _compute_arrhenius: {exc!r}"
        )
        return ArrheniusShelfLife(
            predicted_k_at_storage=0.0,
            predicted_statistical_crossing_months=None,
            predicted_shelf_life_months=None,
            storage_temp_C=float(storage_temp_C),
            temperatures_used=[],
            rates_per_temp={},
            n_temps=0,
            source_arrhenius=None,
            notes=notes,
        )

    source, arr_warnings = _engine_compute_arrhenius(
        data=data, storage_temp_C=float(storage_temp_C),
    )
    # Forward the per-temperature / direction warnings so the report
    # and the JSON record can surface them. The user-facing notes
    # block is built up below.
    notes.extend(arr_warnings)

    if source is None:
        # The helper skipped the fit. Annotate the skip reason with
        # a model-level summary line so the report clearly attributes
        # the v0.8.0 prediction to the same skip.
        notes.append(
            "Arrhenius-driven shelf-life prediction skipped: the "
            "underlying Arrhenius fit did not produce a rate "
            "(insufficient temperatures or direction gating)."
        )
        return ArrheniusShelfLife(
            predicted_k_at_storage=0.0,
            predicted_statistical_crossing_months=None,
            predicted_shelf_life_months=None,
            storage_temp_C=float(storage_temp_C),
            temperatures_used=[],
            rates_per_temp={},
            n_temps=0,
            source_arrhenius=None,
            notes=notes,
        )

    # ---- 4) Per-temp echo for the report.
    temperatures_used = _temperatures_from_source(source)
    rates_per_temp: dict[str, float] = {
        str(k): float(v) for k, v in source.rate_by_temp_C.items()
    }
    n_temps = int(source.n_temps)

    rate = float(abs(source.predicted_k_at_storage))
    # ``rate`` is always positive (the helper returns a positive
    # magnitude; sign is applied via ``slope`` below). If the rate is
    # effectively zero the model is flat and no positive crossing is
    # claimed.
    if rate < _FLAT_SLOPE_TOL:
        notes.append(
            "Arrhenius-driven shelf-life prediction skipped: the "
            "fitted rate is ~0 at the storage temperature "
            f"({storage_temp_C} °C); the model is effectively flat."
        )
        return ArrheniusShelfLife(
            predicted_k_at_storage=rate,
            predicted_statistical_crossing_months=None,
            predicted_shelf_life_months=None,
            storage_temp_C=float(storage_temp_C),
            temperatures_used=temperatures_used,
            rates_per_temp=rates_per_temp,
            n_temps=n_temps,
            source_arrhenius=source,
            notes=notes,
        )

    if data.direction is Direction.DECREASING:
        slope = -rate
    else:  # Direction.INCREASING (gated above)
        slope = +rate

    # ---- 5) Baseline (b0) estimate.
    b0 = _estimate_baseline(data.df)
    if b0 is None:
        notes.append(
            "Arrhenius-driven shelf-life prediction skipped: no "
            "finite rows in the validated data to estimate a "
            "baseline."
        )
        return ArrheniusShelfLife(
            predicted_k_at_storage=rate,
            predicted_statistical_crossing_months=None,
            predicted_shelf_life_months=None,
            storage_temp_C=float(storage_temp_C),
            temperatures_used=temperatures_used,
            rates_per_temp=rates_per_temp,
            n_temps=n_temps,
            source_arrhenius=source,
            notes=notes,
        )

    # ---- 6) Spec + crossing.
    if data.direction is Direction.DECREASING:
        spec = float(data.lower_spec)  # type: ignore[arg-type]
    else:
        spec = float(data.upper_spec)  # type: ignore[arg-type]

    # Direction consistency guard. The rate is positive, so:
    #   DECREASING -> slope < 0 and b0 > spec for a real crossing
    #   INCREASING -> slope > 0 and b0 < spec for a real crossing
    # If the baseline is on the wrong side of the spec the model
    # is "failing at baseline" (a t=0 issue) — surface that.
    if data.direction is Direction.DECREASING and b0 <= spec:
        notes.append(
            "Arrhenius-driven shelf-life prediction: baseline is "
            f"at or past the lower spec ({b0:.4g} <= {spec:.4g}); "
            "fail at baseline."
        )
        return ArrheniusShelfLife(
            predicted_k_at_storage=rate,
            predicted_statistical_crossing_months=0.0,
            predicted_shelf_life_months=0,
            storage_temp_C=float(storage_temp_C),
            temperatures_used=temperatures_used,
            rates_per_temp=rates_per_temp,
            n_temps=n_temps,
            source_arrhenius=source,
            notes=notes,
        )
    if data.direction is Direction.INCREASING and b0 >= spec:
        notes.append(
            "Arrhenius-driven shelf-life prediction: baseline is "
            f"at or past the upper spec ({b0:.4g} >= {spec:.4g}); "
            "fail at baseline."
        )
        return ArrheniusShelfLife(
            predicted_k_at_storage=rate,
            predicted_statistical_crossing_months=0.0,
            predicted_shelf_life_months=0,
            storage_temp_C=float(storage_temp_C),
            temperatures_used=temperatures_used,
            rates_per_temp=rates_per_temp,
            n_temps=n_temps,
            source_arrhenius=source,
            notes=notes,
        )

    # Closed-form crossing on the deterministic linear model.
    t_cross = (spec - b0) / slope  # slope has the right sign
    if not math.isfinite(t_cross) or t_cross > float(horizon):
        notes.append(
            f"Arrhenius-driven shelf-life prediction: model-based "
            f"crossing at t={t_cross!r} is outside the {horizon:g}-mo "
            "horizon; no positive crossing claimed."
        )
        return ArrheniusShelfLife(
            predicted_k_at_storage=rate,
            predicted_statistical_crossing_months=(
                float(t_cross) if math.isfinite(t_cross) else None
            ),
            predicted_shelf_life_months=None,
            storage_temp_C=float(storage_temp_C),
            temperatures_used=temperatures_used,
            rates_per_temp=rates_per_temp,
            n_temps=n_temps,
            source_arrhenius=source,
            notes=notes,
        )
    if t_cross <= 0.0:
        # The closed-form root is at or before t=0 — the baseline
        # is already at/past the spec. Should have been caught by
        # the fail-at-baseline check above; treat as a defensive
        # branch in case of numerical noise.
        notes.append(
            "Arrhenius-driven shelf-life prediction: closed-form "
            f"crossing at t={t_cross!r} is non-positive; fail at "
            "baseline."
        )
        return ArrheniusShelfLife(
            predicted_k_at_storage=rate,
            predicted_statistical_crossing_months=0.0,
            predicted_shelf_life_months=0,
            storage_temp_C=float(storage_temp_C),
            temperatures_used=temperatures_used,
            rates_per_temp=rates_per_temp,
            n_temps=n_temps,
            source_arrhenius=source,
            notes=notes,
        )

    # Happy path.
    predicted_shelf_life_months = int(math.floor(float(t_cross)))
    return ArrheniusShelfLife(
        predicted_k_at_storage=rate,
        predicted_statistical_crossing_months=float(t_cross),
        predicted_shelf_life_months=predicted_shelf_life_months,
        storage_temp_C=float(storage_temp_C),
        temperatures_used=temperatures_used,
        rates_per_temp=rates_per_temp,
        n_temps=n_temps,
        source_arrhenius=source,
        notes=notes,
    )
