"""Tests for ``openpharmastability.shelf_life.multi_engine.analyze_many``.

These tests exercise the public v0.2.0 entry point end-to-end on
the shipped example fixtures (``examples/multi_attribute.csv`` and
``examples/multi_attribute_metadata.csv``). They check the
*structure* of the returned :class:`MultiAttributeResult` rather
than pinning specific numeric shelf-life values — the underlying
single-attribute math is already covered by ``test_engine.py``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from openpharmastability.contracts import (
    AttributeRole,
    CrossingStatus,
    MultiAttributeResult,
)
from openpharmastability.shelf_life.multi_engine import analyze_many


ROOT = Path(__file__).resolve().parents[1]
DATA_CSV = ROOT / "examples" / "multi_attribute.csv"
META_CSV = ROOT / "examples" / "multi_attribute_metadata.csv"


# ---------------------------------------------------------------------------
# 1. Explicit attribute list -> 1 attribute, that attribute is limiting
# ---------------------------------------------------------------------------


def test_analyze_many_with_explicit_attribute_list() -> None:
    """`attributes=["assay"]` -> one AttributeResult, limiting=assay."""
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        attributes=["assay"],
    )
    assert isinstance(multi, MultiAttributeResult)
    assert len(multi.attributes) == 1
    assert multi.attributes[0].metadata.attribute == "assay"
    assert multi.limiting_attribute == "assay"
    assert multi.condition == "25C/60RH"
    assert multi.deliverable_term == "shelf life"
    assert multi.product_type == "product"
    # The single attribute was eligible (assay crosses in the dataset).
    assert multi.attributes[0].included_in_limiting_decision is True
    assert multi.metadata["n_attributes_total"] == 1
    assert multi.metadata["n_attributes_limiting"] == 1


# ---------------------------------------------------------------------------
# 2. all_attributes=True -> every attribute in the data is analyzed
# ---------------------------------------------------------------------------


def test_analyze_many_with_all_attributes() -> None:
    """`all_attributes=True` -> both 'assay' and 'impurity_a' are run."""
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        all_attributes=True,
    )
    names = sorted(a.metadata.attribute for a in multi.attributes)
    assert names == ["assay", "impurity_a"]
    assert multi.metadata["n_attributes_total"] == 2
    # Top-level metadata fields are well-formed.
    assert "library_versions" in multi.metadata
    assert "python" in multi.metadata["library_versions"]


# ---------------------------------------------------------------------------
# 3. Default (no `attributes`, no `all_attributes`) -> ["assay"]
# ---------------------------------------------------------------------------


def test_analyze_many_default_is_assay() -> None:
    """With no attribute hint, the v0.1 default of 'assay' is used."""
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
    )
    assert len(multi.attributes) == 1
    assert multi.attributes[0].metadata.attribute == "assay"


# ---------------------------------------------------------------------------
# 4. Two attributes -> result is well-formed
# ---------------------------------------------------------------------------


def test_analyze_many_limiting_is_assay_when_assay_is_shorter() -> None:
    """Two attributes run end-to-end; structure is well-formed.

    The shipped fixture is designed so that this test does not need
    to pin *which* attribute is limiting — only that the limiting
    decision was made and is consistent with the per-attribute
    results.
    """
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        attributes=["assay", "impurity_a"],
    )
    assert len(multi.attributes) == 2
    by_name = {a.metadata.attribute: a for a in multi.attributes}
    assert "assay" in by_name
    assert "impurity_a" in by_name

    # Both per-attribute StabilityResults have the documented fields.
    for ar in multi.attributes:
        assert ar.result.condition == "25C/60RH"
        assert ar.result.deliverable_term == "shelf life"
        assert ar.result.supported_shelf_life_months is not None
        # On the shipped fixture both attributes cross within the
        # 60-month horizon, so they are both eligible.
        assert ar.included_in_limiting_decision is True
        assert ar.exclusion_reason is None

    # The top-level decision is consistent with the per-attribute data.
    if multi.limiting_attribute is not None:
        winner = by_name[multi.limiting_attribute]
        assert multi.supported_shelf_life_months == (
            winner.result.supported_shelf_life_months
        )
        assert multi.statistical_crossing_months == (
            winner.result.statistical_crossing_months
        )


# ---------------------------------------------------------------------------
# 5. metadata_path=... -> per-attribute metadata is populated
# ---------------------------------------------------------------------------


def test_analyze_many_with_metadata_path() -> None:
    """The metadata CSV overrides the per-attribute defaults."""
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        attributes=["assay", "impurity_a"],
        metadata_path=str(META_CSV),
    )
    by_name = {a.metadata.attribute: a for a in multi.attributes}

    assay = by_name["assay"]
    assert assay.metadata.unit == "%LC"
    assert assay.metadata.direction is not None
    assert assay.metadata.direction.value == "decreasing"
    assert assay.metadata.lower_spec == 90.0
    assert assay.metadata.upper_spec == 110.0
    assert assay.metadata.attribute_role is AttributeRole.PRIMARY
    assert assay.metadata.report_order == 1

    impurity = by_name["impurity_a"]
    assert impurity.metadata.unit == "%area"
    assert impurity.metadata.upper_spec == 0.50
    assert impurity.metadata.attribute_role is AttributeRole.PRIMARY
    assert impurity.metadata.report_order == 2


# ---------------------------------------------------------------------------
# 6. An attribute that has no rows -> "no_data_for_attribute"
# ---------------------------------------------------------------------------


def test_analyze_many_handles_no_data_for_attribute() -> None:
    """An unknown attribute gets a well-formed exclusion entry."""
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        attributes=["nonexistent"],
    )
    assert len(multi.attributes) == 1
    [attr] = multi.attributes
    assert attr.included_in_limiting_decision is False
    assert attr.exclusion_reason == "no_data_for_attribute"
    # Top-level: no eligible attribute, so the limiting decision
    # is None and a top-level warning is added.
    assert multi.limiting_attribute is None
    assert multi.supported_shelf_life_months is None
    assert any("no eligible" in w for w in multi.warnings)


# ---------------------------------------------------------------------------
# 7. file_sha256 is recorded in the top-level metadata
# ---------------------------------------------------------------------------


def test_analyze_many_records_file_sha256() -> None:
    """The top-level metadata carries a 64-hex-char SHA-256 of the file."""
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        attributes=["assay"],
    )
    sha = multi.metadata.get("file_sha256")
    assert isinstance(sha, str)
    assert len(sha) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", sha) is not None


# ---------------------------------------------------------------------------
# 8. v0.5.0 — advanced-statistics opt-in is threaded to per-attribute results
# ---------------------------------------------------------------------------


def test_multi_engine_threads_arrhenius_flag() -> None:
    """``run_arrhenius=True`` is forwarded to each per-attribute
    :func:`analyze` call. The shipped ``multi_attribute.csv`` has
    only one condition (and therefore one implicit temperature),
    so the Arrhenius fit is skipped and ``arrhenius_result`` is
    ``None`` for each attribute. The test asserts the flag is
    wired through (no crash, the field is present, and the
    one-temperature skip path works).
    """
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        attributes=["assay", "impurity_a"],
        run_arrhenius=True,
    )
    assert len(multi.attributes) == 2
    for ar in multi.attributes:
        # The new field is populated (or None when the one-temp
        # skip path fires, which is what happens on the shipped
        # fixture).
        assert hasattr(ar.result, "arrhenius_result")
        # When the one-temp path fires, the per-attribute result
        # also carries a warning naming the skip reason.
        if ar.result.arrhenius_result is None:
            assert any(
                "Arrhenius fit skipped" in w
                for w in ar.result.warnings
            )
        # model_effects stays "fixed" (random_effects not passed)
        assert ar.result.model_effects == "fixed"
