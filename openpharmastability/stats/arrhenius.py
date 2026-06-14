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

import numpy as np

from openpharmastability.contracts import ArrheniusResult


__all__ = ["fit_arrhenius"]


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
