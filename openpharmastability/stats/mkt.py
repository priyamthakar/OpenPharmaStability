"""Mean kinetic temperature (MKT) per the Haynes equation.

Implements the USP <1160> / Haynes MKT:

    MKT = (Ea / R) / ( -ln( mean_i ( exp( -Ea / (R * T_i) ) ) ) )

where ``T_i`` are absolute temperatures in Kelvin and ``Ea`` defaults
to the USP <1160> common value of 83.144 kJ/mol. MKT gives the
single equivalent isothermal temperature whose total thermal stress
over a period equals the cumulative stress of a varying-temperature
profile — useful for excursion analysis and storage-condition
labeling.

The module is pure numpy / math (no pandas, no scipy), so it can be
used from the engine, the CLI, or unit tests without a heavy import
footprint. See ``NEXT_STEPS.md`` §5.3 for the spec.
"""
from __future__ import annotations

import math

import numpy as np


__all__ = ["DEFAULT_EA_J_PER_MOL", "mean_kinetic_temperature"]


# USP <1160> common default. 83.144 kJ/mol = 83_144 J/mol.
DEFAULT_EA_J_PER_MOL: float = 83.144e3


def mean_kinetic_temperature(
    temps_C: list[float],
    Ea_J_per_mol: float = DEFAULT_EA_J_PER_MOL,
    R: float = 8.314,
) -> float:
    """Return the Haynes MKT in degrees Celsius.

    Parameters
    ----------
    temps_C:
        Time-series (or frequency-weighted) list of temperatures in
        degrees Celsius. The order is irrelevant — MKT is a
        symmetric function of the inputs.
    Ea_J_per_mol:
        Activation energy in J/mol. Defaults to the USP <1160>
        common value ``83_144`` J/mol (83.144 kJ/mol).
    R:
        Universal gas constant in J / (mol * K).

    Returns
    -------
    float
        MKT in degrees Celsius. With a single-value input the
        function returns that value exactly (the formula
        degenerates: the inner ``mean(exp(...))`` equals ``exp(...)``
        for a single sample, the outer ``-log`` cancels, and the
        Kelvin→Celsius offset returns the input).

    Notes
    -----
    With an empty input the arithmetic mean of an empty axis is
    NaN, so MKT is NaN as well. The function does not raise in
    that case — callers that care about empty inputs should
    pre-check ``len(temps_C)`` or guard on the NaN return.
    """
    T_K = np.array([c + 273.15 for c in temps_C], dtype=float)
    mkt_K = (Ea_J_per_mol / R) / (
        -np.log(np.mean(np.exp(-Ea_J_per_mol / (R * T_K))))
    )
    return float(mkt_K - 273.15)
