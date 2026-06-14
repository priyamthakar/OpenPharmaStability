"""Arrhenius fit: ``ln(k) = ln(A) - Ea / (R * T)``.

This module implements the v0.5.0 Arrhenius extrapolation helper. It
takes a mapping of stress temperature (°C) to first-order rate
(1/month) and fits the classic two-parameter log-linear Arrhenius
form. The fit is the canonical least-squares solution of

    ln(k_i) = ln(A) + ( -Ea / R ) * ( 1 / T_i )

where ``T_i`` is in Kelvin. The predicted rate at a user-supplied
storage temperature is then ``exp( ln(A) - Ea / (R * T_storage) )``.

The module is intentionally pure numpy / math / warnings. It does not
import any project machinery (engine, CLI, reports) so it can be
unit-tested in isolation against hand-crafted inputs and reused by
the engine or the CLI without a cycle.

See ``NEXT_STEPS.md`` §5.1 for the spec this module implements.
"""
from __future__ import annotations

import math
import warnings
from typing import TYPE_CHECKING

import numpy as np

from openpharmastability.contracts import ArrheniusResult

if TYPE_CHECKING:  # pragma: no cover — types only
    import pandas as pd


__all__ = ["fit_arrhenius", "_per_batch_rates"]


# Note carried on ArrheniusResult.notes when only 2 stress temperatures
# were supplied (no goodness-of-fit available; >= 3 recommended).
_TWO_TEMP_NOTE: str = (
    "Arrhenius fit with only 2 temperatures: no goodness-of-fit "
    "available. >= 3 temperatures recommended for a defensible Ea."
)


def fit_arrhenius(
    rate_by_temp_C: dict[float, float],
    storage_temp_C: float,
    R: float = 8.314,
) -> ArrheniusResult:
    """Fit ``ln(k) = ln(A) - Ea/(R*T)`` to stress-temperature rate data.

    Parameters
    ----------
    rate_by_temp_C:
        Mapping ``{temp_C: k (1/month)}`` with at least 2 entries
        (>= 3 strongly preferred so a goodness-of-fit r^2 is
        meaningful). Keys need not be sorted.
    storage_temp_C:
        Storage temperature (°C) the rate is extrapolated TO (e.g.
        25.0 for room-temperature). Used in the predicted-k field
        only; the fit itself is on the stress temperatures in
        ``rate_by_temp_C``.
    R:
        Universal gas constant, J / (mol * K). The IUPAC value is
        8.314; only override for textbook problems.

    Returns
    -------
    ArrheniusResult
        The fitted ``Ea``, ``A``, ``ln_A``, the predicted ``k`` at
        ``storage_temp_C``, the r^2 of the 1/T regression, and the
        per-temperature input echo (in sorted order) plus a
        human-readable note.

    Raises
    ------
    NotImplementedError
        When ``len(rate_by_temp_C) < 2``. The Arrhenius model is
        under-determined with a single temperature; the user must
        supply more stress conditions.
    """
    temps_C = sorted(rate_by_temp_C)
    n_temps = len(temps_C)

    if n_temps < 2:
        raise NotImplementedError(
            "Arrhenius requires >= 2 stress temperatures (>= 3 preferred "
            "for a defensible Ea). Got %d. Supply more temperatures or "
            "use a single-temperature shelf-life path." % n_temps
        )

    notes: list[str] = []
    if n_temps == 2:
        warnings.warn(_TWO_TEMP_NOTE, stacklevel=2)
        notes.append(_TWO_TEMP_NOTE)

    # Build the log-linear design: ln(k) = ln(A) + (-Ea/R) * (1/T).
    T_K = np.array([c + 273.15 for c in temps_C], dtype=float)
    lnk = np.array([math.log(rate_by_temp_C[c]) for c in temps_C], dtype=float)
    X = np.column_stack([np.ones_like(T_K), 1.0 / T_K])

    # Closed-form OLS via lstsq (handles rank-deficient edge cases
    # more gracefully than np.linalg.solve).
    beta, *_ = np.linalg.lstsq(X, lnk, rcond=None)
    ln_A = float(beta[0])
    neg_Ea_over_R = float(beta[1])
    Ea = -neg_Ea_over_R * R

    # Predicted rate at the storage temperature (in Kelvin).
    T_storage_K = float(storage_temp_C) + 273.15
    predicted_k = math.exp(ln_A - Ea / (R * T_storage_K))

    # Goodness-of-fit: r^2 of the 1/T regression. With n_temps == 2
    # the line passes through both points exactly so ss_res == 0
    # and r^2 = 1.0 (provided the two points are not coincident).
    yhat = X @ beta
    ss_res = float(((lnk - yhat) ** 2).sum())
    ss_tot = float(((lnk - lnk.mean()) ** 2).sum())
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else 1.0

    # Echo the input mapping in sorted order with stringified keys
    # (matches the ArrheniusResult contract: dict[str, float]).
    rate_by_temp_echo: dict[str, float] = {
        str(c): float(rate_by_temp_C[c]) for c in temps_C
    }

    return ArrheniusResult(
        Ea_J_per_mol=float(Ea),
        ln_A=float(ln_A),
        A=float(math.exp(ln_A)),
        r_squared=float(r_squared),
        predicted_k_at_storage=float(predicted_k),
        storage_temp_C=float(storage_temp_C),
        n_temps=int(n_temps),
        rate_by_temp_C=rate_by_temp_echo,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# v0.9.0 — per-batch rate diagnostic
# ---------------------------------------------------------------------------


def _per_batch_rates(
    df: "pd.DataFrame",
    time_col: str = "time_months",
    value_col: str = "value",
    batch_col: str = "batch",
    temp_col: str = "temp_c",
    *,
    direction: str = "decreasing",
) -> dict[str, dict[str, float]]:
    """Build a ``{batch: {temp_C_str: rate}}`` dict from a stability frame.

    For each (batch, temp_c) cell, fit a quick log-linear OLS on the
    rows with ``value > 0`` and extract the per-batch rate. The rate
    is the magnitude ``abs(slope)`` of the ``log(value) ~ time`` fit;
    the sign convention is encoded by ``direction`` (``"decreasing"``
    -> the slope is expected negative; ``"increasing"`` -> expected
    positive). Cells with fewer than two finite positive values, or
    cells whose temperature is not finite, are skipped silently.

    Returns
    -------
    dict[str, dict[str, float]]
        Keys are batch identifiers (str). Values are
        ``{temp_C_str: k(1/month)}`` mappings (the temperature is
        stringified so the dict is JSON-friendly). Returns an empty
        dict when ``df`` is empty, when ``temp_col`` is missing, or
        when no (batch, temp_c) cell has enough finite positive
        values to fit a slope.

    Notes
    -----
    This helper is the v0.9.0 per-batch diagnostic building block.
    Outlier detection is the caller's responsibility (see
    :func:`openpharmastability.shelf_life.engine._detect_arrhenius_outliers`).
    Logs/warnings are NOT raised here.
    """
    import pandas as pd  # local import — keeps the module stdlib-only at top

    if df is None or len(df) == 0:
        return {}
    if temp_col not in df.columns:
        return {}
    if batch_col not in df.columns:
        return {}
    if time_col not in df.columns or value_col not in df.columns:
        return {}

    # Coerce numeric, drop rows with no finite temp / time / value.
    work = df.copy()
    work["_temp_c"] = pd.to_numeric(work[temp_col], errors="coerce")
    work["_time"] = pd.to_numeric(work[time_col], errors="coerce")
    work["_value"] = pd.to_numeric(work[value_col], errors="coerce")
    work = work.dropna(subset=["_temp_c", "_time", "_value"])
    if work.empty:
        return {}

    # `direction` is informational here; we always store the
    # magnitude. The caller (engine outlier detection) only cares
    # about relative magnitudes per temperature. Normalize to lower
    # case so callers can pass enum names or labels interchangeably.
    _ = str(direction).strip().lower()

    out: dict[str, dict[str, float]] = {}
    batches = sorted(work[batch_col].astype(str).unique().tolist())
    for batch in batches:
        sub_b = work[work[batch_col].astype(str) == batch]
        if sub_b.empty:
            continue
        temps = sorted(sub_b["_temp_c"].astype(float).unique().tolist())
        per_temp: dict[str, float] = {}
        for t_key in temps:
            cell = sub_b[sub_b["_temp_c"] == t_key]
            pos = cell[cell["_value"] > 0.0]
            if len(pos) < 2:
                continue
            try:
                slope = float(np.polyfit(
                    pos["_time"].astype(float).to_numpy(),
                    np.log(pos["_value"].astype(float).to_numpy()),
                    deg=1,
                )[0])
            except (np.linalg.LinAlgError, ValueError):
                continue
            rate = float(abs(slope))
            per_temp[str(float(t_key))] = rate
        if per_temp:
            out[str(batch)] = per_temp
    return out
