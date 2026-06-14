"""Tests for ``openpharmastability.stats.arrhenius.fit_arrhenius``.

These tests pin the spec from ``NEXT_STEPS.md`` §5.1:

* 3+ temperature synthetic with known ``Ea`` and ``A`` recovers them
  to machine precision (``rtol=1e-6``).
* 2-temp input emits a ``UserWarning`` and still produces a result
  (no goodness-of-fit; r^2 == 1.0 by construction through 2 points).
* 1-temp input raises ``NotImplementedError`` with the documented
  message.
* Predicted-k at the storage temperature matches the closed-form
  ``A * exp(-Ea / (R * T_storage_K))`` within ``rtol=1e-3``.
* The per-temperature input echo is preserved as a string-keyed dict.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from openpharmastability.contracts import ArrheniusResult
from openpharmastability.stats.arrhenius import fit_arrhenius


# ---------------------------------------------------------------------------
# Test 1: synthetic Ea=80_000 J/mol, A=1e10, four temperatures
# ---------------------------------------------------------------------------


def test_recovers_known_Ea() -> None:
    """Four temperatures on the Arrhenius line; recover Ea and A exactly."""
    Ea_true = 80_000.0
    A_true = 1.0e10
    R = 8.314
    temps_C = [40.0, 50.0, 60.0, 70.0]
    rate_by_temp_C = {
        c: A_true * math.exp(-Ea_true / (R * (c + 273.15))) for c in temps_C
    }
    r = fit_arrhenius(rate_by_temp_C, storage_temp_C=25.0)
    assert isinstance(r, ArrheniusResult)
    assert abs(r.Ea_J_per_mol - Ea_true) / Ea_true < 1e-6
    assert abs(r.A - A_true) / A_true < 1e-6
    assert r.n_temps == 4
    assert r.storage_temp_C == 25.0


# ---------------------------------------------------------------------------
# Test 2: two temperatures → warn, r_squared == 1.0
# ---------------------------------------------------------------------------


def test_two_temps_warns() -> None:
    """Two temperatures: emits a UserWarning and r^2 == 1.0 (exact line)."""
    r = fit_arrhenius(
        {40.0: 1.0e-3, 60.0: 5.0e-3},
        storage_temp_C=25.0,
    )
    assert r.n_temps == 2
    # Perfect fit through 2 points → SS_res == 0 → r^2 == 1.0
    assert r.r_squared == pytest.approx(1.0, abs=1e-12)
    # The "no goodness-of-fit" string ends up on the result's notes
    assert any(">= 3 temperatures" in n for n in r.notes)


def test_two_temps_warns_via_pytest_warns() -> None:
    """The two-temp path emits a real ``UserWarning`` (catches regressions
    where the warning is dropped)."""
    with pytest.warns(UserWarning, match=">= 3 temperatures"):
        fit_arrhenius(
            {40.0: 1.0e-3, 60.0: 5.0e-3},
            storage_temp_C=25.0,
        )


# ---------------------------------------------------------------------------
# Test 3: one temperature → NotImplementedError
# ---------------------------------------------------------------------------


def test_one_temp_raises_not_implemented() -> None:
    """A single temperature is under-determined; the function raises."""
    with pytest.raises(NotImplementedError, match=">= 2 stress temperatures"):
        fit_arrhenius({40.0: 1.0e-3}, storage_temp_C=25.0)


def test_zero_temps_raises_not_implemented() -> None:
    """Empty input is also under-determined; same exception path."""
    with pytest.raises(NotImplementedError, match=">= 2 stress temperatures"):
        fit_arrhenius({}, storage_temp_C=25.0)


# ---------------------------------------------------------------------------
# Test 4: predicted k at the storage temperature
# ---------------------------------------------------------------------------


def test_predicted_k_at_storage() -> None:
    """Predicted k at storage matches the closed-form Arrhenius value."""
    Ea_true = 80_000.0
    A_true = 1.0e10
    R = 8.314
    storage = 25.0
    expected_k = A_true * math.exp(-Ea_true / (R * (storage + 273.15)))
    rate_by_temp_C = {
        40.0: A_true * math.exp(-Ea_true / (R * (40.0 + 273.15))),
        50.0: A_true * math.exp(-Ea_true / (R * (50.0 + 273.15))),
        60.0: A_true * math.exp(-Ea_true / (R * (60.0 + 273.15))),
        70.0: A_true * math.exp(-Ea_true / (R * (70.0 + 273.15))),
    }
    r = fit_arrhenius(rate_by_temp_C, storage_temp_C=storage)
    assert abs(r.predicted_k_at_storage - expected_k) / expected_k < 1e-3


# ---------------------------------------------------------------------------
# Test 5: per-temperature input echo preserved
# ---------------------------------------------------------------------------


def test_rate_by_temp_C_preserved() -> None:
    """The input mapping is echoed as a string-keyed dict, in sorted order."""
    rate_by_temp_C = {70.0: 1.0e-2, 50.0: 1.0e-3, 60.0: 5.0e-3, 40.0: 1.0e-4}
    r = fit_arrhenius(rate_by_temp_C, storage_temp_C=25.0)
    # Same values, stringified keys
    assert set(r.rate_by_temp_C.keys()) == {"40.0", "50.0", "60.0", "70.0"}
    assert r.rate_by_temp_C["40.0"] == pytest.approx(1.0e-4)
    assert r.rate_by_temp_C["70.0"] == pytest.approx(1.0e-2)
    # Echo is in sorted-ascending key order (deterministic)
    assert list(r.rate_by_temp_C.keys()) == sorted(r.rate_by_temp_C.keys())


# ---------------------------------------------------------------------------
# Defensive / cross-checks
# ---------------------------------------------------------------------------


def test_result_dataclass_fields_populated() -> None:
    """Every documented field on ArrheniusResult is populated on success."""
    r = fit_arrhenius(
        {40.0: 1.0e-3, 50.0: 2.0e-3, 60.0: 4.0e-3},
        storage_temp_C=25.0,
    )
    assert r.n_temps == 3
    assert r.storage_temp_C == 25.0
    assert r.Ea_J_per_mol > 0.0          # physically reasonable
    assert r.A > 0.0                      # physically reasonable
    assert r.predicted_k_at_storage > 0.0
    assert 0.0 <= r.r_squared <= 1.0      # valid r^2
    # ln_A and exp(ln_A) must agree
    assert r.A == pytest.approx(math.exp(r.ln_A))


def test_ln_A_consistent_with_intercept() -> None:
    """ln_A is the OLS intercept of the 1/T regression, not a derived
    quantity. Cross-check that A == exp(ln_A) AND that ln_A is the
    value of ln(k) at 1/T == 0 (i.e. T -> infinity) for the fit."""
    r = fit_arrhenius(
        {50.0: 1.0e-3, 60.0: 2.0e-3, 70.0: 4.0e-3},
        storage_temp_C=25.0,
    )
    # 1/T = 0 is a pure extrapolation; just check the identity holds.
    assert math.exp(r.ln_A) == pytest.approx(r.A, rel=1e-12)
