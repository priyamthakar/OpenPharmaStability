"""Tests for ``openpharmastability.stats.mkt.mean_kinetic_temperature``.

These tests pin the spec from ``NEXT_STEPS.md`` §5.3:

* Constant temperature input collapses to that temperature exactly
  (within 1e-9 of degrees Celsius).
* A short hot excursion over a long stable period lifts MKT above the
  baseline but stays well below the peak (Haynes weighting).
* Custom ``Ea`` shifts the result (sanity check that the parameter
  is wired through).
* An empty input is handled gracefully (documented behavior: NaN).
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from openpharmastability.stats.mkt import (
    DEFAULT_EA_J_PER_MOL,
    mean_kinetic_temperature,
)


# ---------------------------------------------------------------------------
# Test 1: constant temperature → equals that temperature exactly
# ---------------------------------------------------------------------------


def test_constant_temperature_equals_input() -> None:
    """MKT of a constant-temperature series equals that temperature
    (within 1e-9 °C) regardless of how many points are supplied."""
    for temps_in in ([25.0], [25.0, 25.0, 25.0], [25.0] * 100):
        mkt = mean_kinetic_temperature(temps_in)
        assert mkt == pytest.approx(25.0, abs=1e-9)


def test_constant_temperature_at_other_value() -> None:
    """MKT of a non-25 °C constant series equals that value."""
    mkt = mean_kinetic_temperature([5.0, 5.0, 5.0])
    assert mkt == pytest.approx(5.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Test 2: short excursion over long stable period
# ---------------------------------------------------------------------------


def test_handles_excursion() -> None:
    """A long 25 °C baseline with a brief 35 °C excursion lifts MKT
    above 25 °C but well below 30 °C (Haynes weighting is sub-linear
    in temperature)."""
    temps = [25.0] * 1000 + [35.0] * 6
    mkt = mean_kinetic_temperature(temps)
    assert 25.0 < mkt < 30.0


def test_excursion_magnitude_increases_with_temperature() -> None:
    """A 40 °C excursion should lift MKT more than a 35 °C one."""
    mkt_35 = mean_kinetic_temperature([25.0] * 1000 + [35.0] * 6)
    mkt_40 = mean_kinetic_temperature([25.0] * 1000 + [40.0] * 6)
    assert mkt_40 > mkt_35 > 25.0


# ---------------------------------------------------------------------------
# Test 3: custom Ea changes the result
# ---------------------------------------------------------------------------


def test_custom_ea_changes_result() -> None:
    """Varying Ea moves the MKT (the default 83.144 kJ/mol is just
    a convention; the real result is Ea-dependent)."""
    temps = [25.0] * 1000 + [35.0] * 6
    mkt_default = mean_kinetic_temperature(temps)
    mkt_high_ea = mean_kinetic_temperature(temps, Ea_J_per_mol=200.0e3)
    mkt_low_ea = mean_kinetic_temperature(temps, Ea_J_per_mol=40.0e3)
    # Higher Ea → more weight on the high-temperature tail → higher MKT
    assert mkt_high_ea > mkt_default
    assert mkt_low_ea < mkt_default


def test_default_ea_constant_is_usp_value() -> None:
    """The default Ea constant matches the USP <1160> common value."""
    assert DEFAULT_EA_J_PER_MOL == pytest.approx(83.144e3, rel=1e-9)


# ---------------------------------------------------------------------------
# Test 4: empty input handled (documented NaN behavior, no raise)
# ---------------------------------------------------------------------------


def test_empty_input_handled() -> None:
    """An empty input reduces to ``-log(mean(empty))`` which is NaN.

    The function does NOT raise; callers that care about empty input
    should pre-check ``len(temps_C)`` or guard on the NaN return.
    The test pins the documented behavior so a future refactor
    doesn't silently start raising.
    """
    result = mean_kinetic_temperature([])
    # np.mean of an empty array raises a RuntimeWarning and returns NaN
    # with a RuntimeWarning, which we filter via np.errstate. The
    # key behavioral assertion is: no exception, and the result is
    # NaN (which is what np.mean returns for an empty axis).
    assert math.isnan(result)


def test_empty_input_does_not_raise() -> None:
    """A plain call on an empty list returns a finite or NaN float —
    it never raises an exception."""
    try:
        out = mean_kinetic_temperature([])
    except Exception as exc:  # noqa: BLE001 — must never raise upstream
        pytest.fail(f"mean_kinetic_temperature([]) raised {type(exc).__name__}: {exc}")
    # The result may be NaN; just confirm it is a float
    assert isinstance(out, float)
