"""Tests for ``openpharmastability.shelf_life.limiting``.

These tests build minimal :class:`AttributeResult` /
:class:`StabilityResult` fixtures in-process — no CSV I/O, no
fitter, no schema validation. The point of the limiting module
is the decision rule, not the math; we keep the fixtures tiny so
the tests stay focused on that rule.
"""
from __future__ import annotations

import numpy as np
import pytest

from openpharmastability.contracts import (
    AttributeMetadata,
    AttributeResult,
    AttributeRole,
    CrossingResult,
    CrossingStatus,
    DiagnosticsResult,
    Direction,
    FitResult,
    ModelKind,
    Poolability,
    PoolabilityResult,
    StabilityResult,
)
from openpharmastability.shelf_life.limiting import select_limiting


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _noop_fit() -> FitResult:
    """A minimal FitResult good enough for the limiting-decision logic.

    The limiting module never invokes ``fitted_fn``; it only reads
    crossing status and shelf life. So a no-op callable and an
    empty covariance matrix are sufficient.
    """
    return FitResult(
        kind=ModelKind.POOLED,
        params={},
        df_resid=0,
        s_resid=0.0,
        cov=np.zeros((0, 0)),
        fitted_fn=lambda *a, **k: (lambda t: float("nan")),
        design={},
        batches=[],
    )


def _make_result(
    attribute: str,
    *,
    role: AttributeRole = AttributeRole.PRIMARY,
    shelf: int | None = 30,
    crossing: float | None = 31.5,
    status: CrossingStatus = CrossingStatus.CROSSED,
    warnings: list[str] | None = None,
) -> AttributeResult:
    """Build an :class:`AttributeResult` with the bits the limiter reads."""
    stability = StabilityResult(
        attribute=attribute,
        condition="25C/60RH",
        direction=Direction.DECREASING,
        model=ModelKind.COMMON_SLOPE,
        poolability=PoolabilityResult(
            decision=Poolability.PARTIAL,
            p_slopes=0.9,
            p_intercepts=0.5,
            alpha=0.25,
            notes=[],
        ),
        fit=_noop_fit(),
        crossing=CrossingResult(
            crossing_months=crossing,
            status=status,
            governing_batch="B1",
            notes=[],
        ),
        supported_shelf_life_months=shelf,
        statistical_crossing_months=crossing,
        observed_data_months=24.0,
        extrapolation_flag=False,
        diagnostics=DiagnosticsResult(
            linearity_ok=True,
            homoscedastic_ok=True,
            normal_resid_ok=True,
            influential_points=[],
            notes=[],
        ),
        warnings=list(warnings or []),
        metadata={},
        deliverable_term="shelf life",
        product_type="product",
    )
    return AttributeResult(
        metadata=AttributeMetadata(attribute=attribute, attribute_role=role),
        result=stability,
        included_in_limiting_decision=True,
        exclusion_reason=None,
    )


# ---------------------------------------------------------------------------
# 1. Min supported shelf life wins
# ---------------------------------------------------------------------------


def test_limiting_picks_min_shelf_life() -> None:
    """Three eligible PRIMARYs; the smallest shelf life governs."""
    results = [
        _make_result("assay", shelf=30, crossing=31.5),
        _make_result("impurity_a", shelf=24, crossing=25.0),
        _make_result("impurity_b", shelf=36, crossing=37.0),
    ]
    multi = select_limiting(
        results,
        deliverable_term="shelf life",
        product_type="product",
        condition="25C/60RH",
        observed_data_months=24.0,
    )
    assert multi.limiting_attribute == "impurity_a"
    assert multi.supported_shelf_life_months == 24
    assert multi.statistical_crossing_months == 25.0
    # All three were eligible; all carry included_in_limiting_decision=True.
    assert all(a.included_in_limiting_decision for a in multi.attributes)
    assert all(a.exclusion_reason is None for a in multi.attributes)
    # Top-level metadata reflects the count and the absence of a tie.
    assert multi.metadata["n_attributes_total"] == 3
    assert multi.metadata["n_attributes_limiting"] == 3
    assert multi.metadata["tie_break"] is None


# ---------------------------------------------------------------------------
# 2. Non-PRIMARY attributes are skipped
# ---------------------------------------------------------------------------


def test_limiting_skips_non_primary() -> None:
    """A SUPPORTIVE attribute with the smaller shelf life still loses."""
    results = [
        _make_result("assay", role=AttributeRole.PRIMARY, shelf=30, crossing=31.5),
        _make_result(
            "support_1",
            role=AttributeRole.SUPPORTIVE,
            shelf=12,
            crossing=12.5,
        ),
    ]
    multi = select_limiting(
        results,
        deliverable_term="shelf life",
        product_type="product",
        condition="25C/60RH",
        observed_data_months=24.0,
    )
    assert multi.limiting_attribute == "assay"
    assert multi.supported_shelf_life_months == 30
    # The supportive entry is still in the output, but excluded.
    by_name = {a.metadata.attribute: a for a in multi.attributes}
    assert by_name["support_1"].included_in_limiting_decision is False
    assert by_name["support_1"].exclusion_reason == "role"
    # n_attributes_limiting counts only the eligible PRIMARY entry.
    assert multi.metadata["n_attributes_limiting"] == 1


# ---------------------------------------------------------------------------
# 3. NO_CROSSING is not eligible, even if other attributes exist
# ---------------------------------------------------------------------------


def test_limiting_excludes_no_crossing() -> None:
    """An attribute with status=NO_CROSSING is not eligible."""
    results = [
        _make_result(
            "assay",
            shelf=None,
            crossing=None,
            status=CrossingStatus.NO_CROSSING,
        ),
        _make_result("impurity_a", shelf=30, crossing=31.0),
    ]
    multi = select_limiting(
        results,
        deliverable_term="shelf life",
        product_type="product",
        condition="25C/60RH",
        observed_data_months=24.0,
    )
    assert multi.limiting_attribute == "impurity_a"
    assert multi.supported_shelf_life_months == 30
    by_name = {a.metadata.attribute: a for a in multi.attributes}
    assert by_name["assay"].included_in_limiting_decision is False
    assert by_name["assay"].exclusion_reason == "no_crossing"


# ---------------------------------------------------------------------------
# 4. No eligible attribute -> limiting_attribute=None + warning
# ---------------------------------------------------------------------------


def test_limiting_no_eligible_returns_none() -> None:
    """All attributes excluded -> None limiting + a clear top-level warning."""
    results = [
        _make_result(
            "assay",
            role=AttributeRole.SUPPORTIVE,
            shelf=30,
            crossing=31.0,
        ),
        _make_result(
            "impurity_a",
            role=AttributeRole.INFORMATIONAL,
            shelf=24,
            crossing=25.0,
        ),
    ]
    multi = select_limiting(
        results,
        deliverable_term="shelf life",
        product_type="product",
        condition="25C/60RH",
        observed_data_months=24.0,
    )
    assert multi.limiting_attribute is None
    assert multi.supported_shelf_life_months is None
    assert multi.statistical_crossing_months is None
    assert any("no eligible" in w for w in multi.warnings)
    # No per-attribute entry should claim inclusion in the limiting decision.
    assert all(
        a.included_in_limiting_decision is False for a in multi.attributes
    )
    assert multi.metadata["n_attributes_limiting"] == 0


# ---------------------------------------------------------------------------
# 5. Tie on shelf life -> earlier statistical crossing wins
# ---------------------------------------------------------------------------


def test_limiting_tiebreak_by_statistical_crossing() -> None:
    """Two PRIMARYs with identical shelf life -> smaller crossing wins."""
    results = [
        _make_result("assay", shelf=30, crossing=35.0),
        _make_result("impurity_a", shelf=30, crossing=32.0),
    ]
    multi = select_limiting(
        results,
        deliverable_term="shelf life",
        product_type="product",
        condition="25C/60RH",
        observed_data_months=24.0,
    )
    assert multi.limiting_attribute == "impurity_a"
    assert multi.supported_shelf_life_months == 30
    assert multi.statistical_crossing_months == 32.0
    assert multi.metadata["tie_break"] == "statistical_crossing"


# ---------------------------------------------------------------------------
# 6. Per-attribute exclusion_reason is set on the output
# ---------------------------------------------------------------------------


def test_limiting_per_attribute_exclusion_reason_set() -> None:
    """SUPPORTIVE -> exclusion_reason='role' on the output entry."""
    results = [
        _make_result(
            "support_1",
            role=AttributeRole.SUPPORTIVE,
            shelf=10,
            crossing=11.0,
        ),
    ]
    multi = select_limiting(
        results,
        deliverable_term="shelf life",
        product_type="product",
        condition="25C/60RH",
        observed_data_months=12.0,
    )
    assert len(multi.attributes) == 1
    [attr] = multi.attributes
    assert attr.included_in_limiting_decision is False
    assert attr.exclusion_reason == "role"


# ---------------------------------------------------------------------------
# Bonus coverage: per-attribute warnings are surfaced at the top level
# ---------------------------------------------------------------------------


def test_limiting_concatenates_per_attribute_warnings() -> None:
    """Per-attribute warnings flow up to the top-level warnings list."""
    results = [
        _make_result(
            "assay",
            shelf=30,
            crossing=31.0,
            warnings=["only 2 batches; Q1E expects at least 3"],
        ),
        _make_result("impurity_a", shelf=24, crossing=25.0),
    ]
    multi = select_limiting(
        results,
        deliverable_term="shelf life",
        product_type="product",
        condition="25C/60RH",
        observed_data_months=24.0,
    )
    assert "only 2 batches; Q1E expects at least 3" in multi.warnings
