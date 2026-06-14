"""Tests for the Q1E room-temperature extrapolation cap logic
(``shelf_life/extrapolation.py``).

The cap rule (per OpenPharmaStability.md "Shelf-life logic"):

  The proposed shelf life should not exceed roughly **twice** and
  should not be **more than 12 months beyond** the period covered by
  long-term data. Anything past the applicable cap is hard-flagged.

The function :func:`apply_extrapolation_caps` sets
``extrapolation_flag``, appends a warning, and rounds the supported
shelf life down to the cap when the cap is the binding constraint.
"""
from __future__ import annotations

import copy

import pytest

from openpharmastability.contracts import (
    CONFIDENCE,
    EXTRAPOLATION_MAX_FACTOR,
    EXTRAPOLATION_MAX_MONTHS_BEYOND,
    CrossingResult,
    CrossingStatus,
    Direction,
    DiagnosticsResult,
    ModelKind,
    Poolability,
    PoolabilityResult,
    StabilityResult,
)
from openpharmastability.shelf_life.extrapolation import apply_extrapolation_caps
from openpharmastability.stats.regression import fit_models


# ---------------------------------------------------------------------------
# Fixture: a hand-rolled StabilityResult with a chosen shelf life and
# observed data length. Using a real (small) fit so the function under
# test sees a non-pathological FitResult, but the cap-relevant fields
# (supported_shelf_life_months, observed_data_months, crossing.status)
# are overridden after the fact.
# ---------------------------------------------------------------------------


def _make_result(
    *,
    shelf_life: int | None,
    observed: float,
    crossing_status: CrossingStatus = CrossingStatus.CROSSED,
    crossing_months: float | None = 19.5,
    statistical_crossing: float | None = 19.5,
) -> StabilityResult:
    """Build a minimal StabilityResult with the cap-relevant fields set.

    The rest of the FitResult / DiagnosticsResult is a small real fit
    on a 3-batch dataset; the cap logic only inspects the few fields
    we override.
    """
    import numpy as np
    import pandas as pd
    rows = []
    for batch, b0 in (("B1", 100.0), ("B2", 99.0), ("B3", 101.0)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": b0 - 0.5 * t,
                "lower_spec": 90.0, "upper_spec": 110.0,
                "direction": "decreasing",
            })
    df = pd.DataFrame(rows)
    from openpharmastability.contracts import ValidatedData
    data = ValidatedData(
        df=df, attribute="assay", condition="25C/60RH",
        direction=Direction.DECREASING, lower_spec=90., upper_spec=110.,
        n_batches=3, time_points=[0, 3, 6, 9, 12, 18, 24],
    )
    fit = fit_models(data)[ModelKind.COMMON_SLOPE]
    return StabilityResult(
        attribute="assay",
        condition="25C/60RH",
        direction=Direction.DECREASING,
        model=ModelKind.COMMON_SLOPE,
        poolability=PoolabilityResult(
            decision=Poolability.PARTIAL, p_slopes=0.9,
            p_intercepts=0.001, alpha=CONFIDENCE, notes=[],
        ),
        fit=fit,
        crossing=CrossingResult(
            crossing_months=crossing_months,
            status=crossing_status,
            governing_batch="B2",
            notes=[],
        ),
        supported_shelf_life_months=shelf_life,
        statistical_crossing_months=statistical_crossing,
        observed_data_months=observed,
        extrapolation_flag=False,
        diagnostics=DiagnosticsResult(
            linearity_ok=True, homoscedastic_ok=True, normal_resid_ok=True,
            influential_points=[], notes=[], details={},
        ),
        warnings=[],
        metadata={"tool_version": "0.1.0"},
        deliverable_term="shelf life",
        product_type="product",
    )


# ---------------------------------------------------------------------------
# 1. No-op when supported shelf life is within observed data
# ---------------------------------------------------------------------------


def test_no_op_when_shelf_life_within_observed():
    result = _make_result(shelf_life=18, observed=24.0)
    new = apply_extrapolation_caps(result)
    assert new.supported_shelf_life_months == 18
    assert new.extrapolation_flag is False
    # No new warnings.
    assert new.warnings == []


# ---------------------------------------------------------------------------
# 2. Extrapolation flag set when supported > observed
# ---------------------------------------------------------------------------


def test_flag_set_when_shelf_life_beyond_observed():
    result = _make_result(shelf_life=30, observed=24.0)
    new = apply_extrapolation_caps(result)
    assert new.extrapolation_flag is True
    # Within the cap (factor=2 -> 48, +12 -> 36, min=36, so 30 <= 36)
    # -> cap not triggered, but extrapolation flagged.
    assert any("extrapolation flagged" in w.lower() for w in new.warnings)


# ---------------------------------------------------------------------------
# 3. Cap not triggered when within the 2x and +12 limits
# ---------------------------------------------------------------------------


def test_cap_not_triggered_within_factor_and_plus12():
    result = _make_result(shelf_life=36, observed=24.0)
    new = apply_extrapolation_caps(result)
    # min(floor(2*24)=48, floor(24+12)=36) = 36; 36 <= 36 -> cap not triggered
    assert new.supported_shelf_life_months == 36
    assert not any(
        "exceeds the q1e extrapolation cap" in w.lower() for w in new.warnings
    )


# ---------------------------------------------------------------------------
# 4. Cap triggered when shelf life exceeds the binding limit
# ---------------------------------------------------------------------------


def test_cap_triggered_when_shelf_life_exceeds_binding_limit():
    result = _make_result(shelf_life=60, observed=24.0)
    new = apply_extrapolation_caps(result)
    # min(48, 36) = 36; 60 > 36 -> cap triggers, value is rounded down to 36
    assert new.supported_shelf_life_months == 36
    # And a hard cap warning was appended.
    assert any(
        "exceeds the q1e extrapolation cap" in w.lower() for w in new.warnings
    )
    assert any("hard-flagged" in w.lower() for w in new.warnings)


# ---------------------------------------------------------------------------
# 5. Cap triggered by factor (not +12) when observed is large
# ---------------------------------------------------------------------------


def test_cap_triggered_by_factor_when_observed_is_large():
    # observed = 18 months, proposed = 30 months
    # 2*18 = 36 (cap by factor)
    # 18 + 12 = 30 (cap by +12)
    # 30 is at the +12 boundary, so cap is min(36, 30) = 30 -> no cap
    # Now bump proposed to 31: cap = 30, triggers.
    result = _make_result(shelf_life=31, observed=18.0)
    new = apply_extrapolation_caps(result)
    assert new.supported_shelf_life_months == 30
    assert any("q1e extrapolation cap" in w.lower() for w in new.warnings)


# ---------------------------------------------------------------------------
# 6. NO_CROSSING status: extrapolation_flag NOT set, no warning
# ---------------------------------------------------------------------------


def test_no_crossing_does_not_set_extrapolation_flag():
    result = _make_result(
        shelf_life=None, observed=24.0,
        crossing_status=CrossingStatus.NO_CROSSING,
        crossing_months=None, statistical_crossing=None,
    )
    new = apply_extrapolation_caps(result)
    assert new.extrapolation_flag is False
    assert new.warnings == []


# ---------------------------------------------------------------------------
# 7. FLAT_OR_OPPOSITE: extrapolation_flag NOT set
# ---------------------------------------------------------------------------


def test_flat_or_opposite_does_not_set_extrapolation_flag():
    result = _make_result(
        shelf_life=None, observed=24.0,
        crossing_status=CrossingStatus.FLAT_OR_OPPOSITE,
        crossing_months=None, statistical_crossing=None,
    )
    new = apply_extrapolation_caps(result)
    assert new.extrapolation_flag is False


# ---------------------------------------------------------------------------
# 8. Input is not mutated (the function returns a new StabilityResult)
# ---------------------------------------------------------------------------


def test_input_not_mutated():
    result = _make_result(shelf_life=60, observed=24.0)
    before = copy.deepcopy(result)
    _ = apply_extrapolation_caps(result)
    assert result.supported_shelf_life_months == before.supported_shelf_life_months
    assert result.warnings == before.warnings
    assert result.extrapolation_flag == before.extrapolation_flag


# ---------------------------------------------------------------------------
# 9. The constants are reasonable
# ---------------------------------------------------------------------------


def test_cap_constants():
    assert EXTRAPOLATION_MAX_FACTOR == 2.0
    assert EXTRAPOLATION_MAX_MONTHS_BEYOND == 12.0


# ---------------------------------------------------------------------------
# 10. v0.4.0 — allowance-aware extrapolation caps
# ---------------------------------------------------------------------------


def test_extrapolation_allowance_arg_caps_supported_value():
    """When the ICH Q1A significant-change gate returns
    ``(allowed=False, cap_months=12.0, rationale="no extrapolation
    allowed")``, :func:`apply_extrapolation_caps` MUST cap the
    supported value to ``cap_months`` (even if the original value
    was smaller), record the allowance on the result, and append
    a warning naming the rationale."""
    result = _make_result(shelf_life=30, observed=12.0)
    new = apply_extrapolation_caps(
        result,
        allowance=(False, 12.0, "no extrapolation allowed"),
    )
    # The supported value is forced to the cap (12).
    assert new.supported_shelf_life_months == 12
    # The allowance fields are populated.
    assert new.extrapolation_allowed is False
    assert new.extrapolation_rationale == "no extrapolation allowed"
    # A warning referencing the rationale was appended.
    assert any(
        "no extrapolation allowed" in w for w in new.warnings
    ), f"expected rationale in warnings, got {new.warnings!r}"


def test_extrapolation_no_allowance_preserves_v031():
    """Calling :func:`apply_extrapolation_caps` with no ``allowance``
    argument MUST preserve the v0.3.1 default values on the new
    fields: ``extrapolation_allowed is True`` and
    ``extrapolation_rationale == ""``."""
    result = _make_result(shelf_life=30, observed=12.0)
    # No allowance argument -> the v0.3.1 path runs.
    new = apply_extrapolation_caps(result)
    # Default permissive values are preserved.
    assert new.extrapolation_allowed is True
    assert new.extrapolation_rationale == ""
    # The v0.3.1 Q1E cap math still runs: cap is min(2*12, 12+12) = 24,
    # so the 30-month value is capped to 24.
    assert new.supported_shelf_life_months == 24
    # And the Q1E-cap warning is the v0.3.1 one, not an allowance one.
    assert any(
        "exceeds the q1e extrapolation cap" in w.lower() for w in new.warnings
    )
