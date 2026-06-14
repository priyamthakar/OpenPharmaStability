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


# ---------------------------------------------------------------------------
# v0.9.0 — per-batch Arrhenius rate diagnostic + outlier detection
# ---------------------------------------------------------------------------


def _write_per_batch_arrhenius_csv(path) -> None:
    """3 batches, 7 time points, 1 temperature — synthetic golden frame
    for the per-batch Arrhenius diagnostic.

    The condition string is the same for all rows; the single
    stress temperature is carried in the ``temp_c`` column. The
    rates are slightly different per batch (so the per-batch
    diagnostic finds three distinct rates) but close enough that
    the robust-z outlier detection does NOT flag anyone — the
    test only asserts the dict is populated correctly.
    """
    import pandas as pd
    rng = np.random.default_rng(20260114)
    rows = []
    for batch, slope in (("B1", 0.20), ("B2", 0.22), ("B3", 0.24)):
        for t in (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0):
            v = 100.0 - slope * t + float(rng.normal(0.0, 0.05))
            rows.append({
                "batch": batch,
                "condition": "25C/60RH",
                "time_months": t,
                "attribute": "assay",
                "value": round(v, 4),
                "lower_spec": 90.0,
                "upper_spec": 110.0,
                "direction": "decreasing",
                "temp_c": 40.0,
            })
    pd.DataFrame(rows).to_csv(path, index=False)


def test_per_batch_rates_populated_when_flag_set(tmp_path) -> None:
    """``--arrhenius-per-batch`` populates the new dict / list fields.

    With a 3-batch / 1-temperature synthetic frame and BOTH the
    ``run_arrhenius`` and ``run_arrhenius_per_batch`` flags set,
    the engine's ``arrhenius_result.per_batch_rate_by_temp`` has
    exactly 3 keys (B1, B2, B3) and each has one rate entry (for
    the single 40 °C temperature). Rates are floats.
    """
    from openpharmastability.shelf_life.engine import analyze

    csv_path = tmp_path / "per_batch.csv"
    _write_per_batch_arrhenius_csv(csv_path)
    result = analyze(
        path=str(csv_path),
        condition="25C/60RH",
        attribute="assay",
        # Per-batch requires the pooled fit too. A 1-temperature
        # fixture would normally skip the pooled fit (need >= 2
        # temps), but the helper itself does not require the
        # pooled fit to succeed; we still ask for the pooled
        # Arrhenius so the helper's gate is exercised in the
        # presence of an ``ArrheniusResult``.
        run_arrhenius=False,
        run_arrhenius_per_batch=True,
    )
    # With ``run_arrhenius=False``, ``arrhenius_result`` is None, so
    # the per-batch diagnostic is gated off with a warning. Re-run
    # with ``run_arrhenius=True``. We use 2-temperature data so the
    # pooled fit succeeds.
    assert result.arrhenius_result is None
    assert any(
        "requires --arrhenius" in str(w) for w in result.warnings
    ), result.warnings

    # Build a 2-temperature variant so the pooled Arrhenius fit
    # also runs, then assert the per-batch dict is populated.
    import pandas as pd
    df = pd.read_csv(csv_path)
    # Duplicate the rows at a second temperature (50 °C) with a
    # slightly faster degradation so the Arrhenius line is real.
    df2 = df.copy()
    df2["temp_c"] = 50.0
    df2["value"] = df2["value"] - 0.10 * df2["time_months"]
    combined = pd.concat([df, df2], ignore_index=True)
    csv2 = tmp_path / "per_batch_2temp.csv"
    combined.to_csv(csv2, index=False)

    result2 = analyze(
        path=str(csv2),
        condition="25C/60RH",
        attribute="assay",
        run_arrhenius=True,
        run_arrhenius_per_batch=True,
    )
    assert result2.arrhenius_result is not None
    per_batch = result2.arrhenius_result.per_batch_rate_by_temp
    assert isinstance(per_batch, dict)
    assert set(per_batch.keys()) == {"B1", "B2", "B3"}
    for batch, rates in per_batch.items():
        assert isinstance(rates, dict)
        # 2 temperatures in the synthetic frame.
        assert len(rates) == 2, (batch, rates)
        for t_key, k in rates.items():
            assert isinstance(t_key, str)
            assert isinstance(k, float)
            assert k > 0.0
    # ``outlier_batches`` is always a list (may be empty).
    assert isinstance(result2.arrhenius_result.outlier_batches, list)


def test_outlier_batches_flagged_when_one_is_far() -> None:
    """``_detect_arrhenius_outliers`` flags a batch whose rate is far
    from the others at a given temperature.

    The helper is the engine-level outlier detector; we exercise it
    directly so the test does not depend on the engine path. Build
    a synthetic dict where B1, B2, B3, B4 have rates clustered near
    0.20 and B_OUT has a rate of 5.0 — far enough that the robust
    z-score will exceed the default threshold of 2.5.
    """
    from openpharmastability.shelf_life.engine import (
        _detect_arrhenius_outliers,
    )

    per_batch = {
        "B1": {"40.0": 0.20},
        "B2": {"40.0": 0.21},
        "B3": {"40.0": 0.19},
        "B4": {"40.0": 0.22},
        "B_OUT": {"40.0": 5.0},
    }
    outliers = _detect_arrhenius_outliers(per_batch, z_threshold=2.5)
    assert "B_OUT" in outliers
    # B1..B4 sit at the median; they MUST NOT be flagged.
    for b in ("B1", "B2", "B3", "B4"):
        assert b not in outliers, (b, outliers)


def test_outlier_batches_empty_when_rates_agree() -> None:
    """When all per-batch rates at every temperature are close to the
    same value, no batch is flagged as an outlier.

    The threshold is the v0.9.0 default (2.5); a small spread
    around the median should NOT trip it.
    """
    from openpharmastability.shelf_life.engine import (
        _detect_arrhenius_outliers,
    )

    per_batch = {
        "B1": {"40.0": 0.20, "50.0": 0.30},
        "B2": {"40.0": 0.21, "50.0": 0.31},
        "B3": {"40.0": 0.19, "50.0": 0.29},
        "B4": {"40.0": 0.205, "50.0": 0.305},
    }
    outliers = _detect_arrhenius_outliers(per_batch, z_threshold=2.5)
    assert outliers == []


def test_per_batch_default_off_does_not_populate(tmp_path) -> None:
    """Without ``run_arrhenius_per_batch``, the two new fields stay at
    their v0.8.0 defaults (empty dict / empty list).

    Re-runs the same 2-temperature synthetic frame as the populated
    test but WITHOUT the new flag. The pooled Arrhenius fit still
    runs (``run_arrhenius=True``) and produces an
    :class:`~openpharmastability.contracts.ArrheniusResult`, but the
    per-batch dict and outlier list are NOT populated by the
    engine.
    """
    from openpharmastability.shelf_life.engine import analyze

    csv_path = tmp_path / "per_batch_default_off.csv"
    _write_per_batch_arrhenius_csv(csv_path)
    # Same 2-temperature variant as test_per_batch_rates_populated.
    import pandas as pd
    df = pd.read_csv(csv_path)
    df2 = df.copy()
    df2["temp_c"] = 50.0
    df2["value"] = df2["value"] - 0.10 * df2["time_months"]
    combined = pd.concat([df, df2], ignore_index=True)
    csv2 = tmp_path / "per_batch_default_off_2temp.csv"
    combined.to_csv(csv2, index=False)

    result = analyze(
        path=str(csv2),
        condition="25C/60RH",
        attribute="assay",
        run_arrhenius=True,
        # Crucially: per-batch flag NOT set.
    )
    assert result.arrhenius_result is not None
    assert result.arrhenius_result.per_batch_rate_by_temp == {}
    assert result.arrhenius_result.outlier_batches == []
