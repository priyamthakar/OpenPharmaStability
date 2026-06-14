"""Tests for ``openpharmastability.data.metadata`` loaders.

The attribute-metadata loader is the v0.2.0 seam that lets a
separate CSV (or XLSX sheet) describe how each attribute should be
analyzed. The behaviors we lock down here:

1. A valid CSV with the required ``attribute`` column produces
   one ``AttributeMetadata`` per row, with optional columns
   (specs, role, etc.) populated when present.
2. Missing the required ``attribute`` column raises a clear
   ``ValueError`` (we never silently return an empty list).
3. Unknown ``direction`` strings are coerced to ``None`` and
   recorded as a warning on the entry, not a hard error.
4. Missing ``attribute_role`` defaults to ``PRIMARY``; missing
   ``spec_type`` defaults to ``None``.
5. Unsupported ``transform`` values (e.g. ``"log"`` in v0.2.0)
   fall back to ``"none"`` and record a warning.
6. ``report_order`` is optional and is ``None`` when missing.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from openpharmastability.contracts import (
    AttributeMetadata,
    AttributeRole,
    Direction,
)
from openpharmastability.data.metadata import (
    load_attribute_metadata_csv,
    load_attribute_metadata_from_dataframe,
)

# The repository ships a small fixture for the multi-attribute
# tests in examples/.
FIXTURE_PATH = Path(__file__).resolve().parents[1] / "examples" / "multi_attribute_metadata.csv"


def test_load_attribute_metadata_csv_basic() -> None:
    """The shipped fixture loads to two well-formed entries."""
    metadata = load_attribute_metadata_csv(str(FIXTURE_PATH))
    assert len(metadata) == 2
    assert [m.attribute for m in metadata] == ["assay", "impurity_a"]
    assay, impurity = metadata
    assert assay.unit == "%LC"
    assert assay.direction is Direction.DECREASING
    assert assay.lower_spec == 90.0
    assert assay.upper_spec == 110.0
    assert assay.spec_type == "shelf_life"
    assert assay.transform == "none"
    assert assay.attribute_role is AttributeRole.PRIMARY
    assert assay.report_order == 1
    assert impurity.unit == "%area"
    assert impurity.direction is Direction.INCREASING
    # Empty CSV cell -> None after coerce.
    assert impurity.lower_spec is None
    assert impurity.upper_spec == 0.50
    assert impurity.report_order == 2


def test_load_attribute_metadata_missing_attribute_column_raises() -> None:
    """A DataFrame without the required ``attribute`` column raises ValueError."""
    df = pd.DataFrame({
        "unit": ["%"],
        "direction": ["decreasing"],
    })
    with pytest.raises(ValueError, match="attribute"):
        load_attribute_metadata_from_dataframe(df)


def test_load_attribute_metadata_coerces_unknown_direction_to_none() -> None:
    """Unknown direction strings become None + a warning, not a hard error."""
    df = pd.DataFrame({
        "attribute": ["assay"],
        "direction": ["garbage"],
    })
    [meta] = load_attribute_metadata_from_dataframe(df)
    assert meta.direction is None
    # The bad value should be surfaced in the warnings list, not silently dropped.
    assert any("unrecognized direction" in w for w in meta.warnings)


def test_load_attribute_metadata_defaults_role_to_primary() -> None:
    """Missing ``attribute_role`` column -> PRIMARY for every entry."""
    df = pd.DataFrame({"attribute": ["assay", "impurity_a"]})
    metadata = load_attribute_metadata_from_dataframe(df)
    assert all(m.attribute_role is AttributeRole.PRIMARY for m in metadata)


def test_load_attribute_metadata_rejects_unsupported_transform() -> None:
    """Unsupported transform values (e.g. ``"bogus"``) fall back to 'none' with a warning."""
    df = pd.DataFrame({
        "attribute": ["assay"],
        "transform": ["bogus"],
    })
    [meta] = load_attribute_metadata_from_dataframe(df)
    assert meta.transform == "none"
    assert any("not supported" in w for w in meta.warnings)


def test_load_attribute_metadata_allows_log_transform() -> None:
    """v0.3 supports ``"log"`` as a real transform; it must NOT be downgraded."""
    df = pd.DataFrame({
        "attribute": ["assay"],
        "transform": ["log"],
    })
    [meta] = load_attribute_metadata_from_dataframe(df)
    assert meta.transform == "log"
    assert not any("falling back to 'none'" in w for w in meta.warnings)


def test_load_attribute_metadata_bogus_transform_falls_back() -> None:
    """A truly unsupported transform still warns and falls back to 'none'."""
    df = pd.DataFrame({
        "attribute": ["assay"],
        "transform": ["bogus"],
    })
    [meta] = load_attribute_metadata_from_dataframe(df)
    assert meta.transform == "none"
    assert any("not supported" in w and "falling back to 'none'" in w
               for w in meta.warnings)


def test_load_attribute_metadata_spec_type_optional() -> None:
    """Missing ``spec_type`` column -> None for every entry."""
    df = pd.DataFrame({"attribute": ["assay"]})
    [meta] = load_attribute_metadata_from_dataframe(df)
    assert meta.spec_type is None


def test_load_attribute_metadata_report_order_optional() -> None:
    """Missing ``report_order`` column -> None for every entry."""
    df = pd.DataFrame({"attribute": ["assay", "impurity_a"]})
    metadata = load_attribute_metadata_from_dataframe(df)
    assert all(m.report_order is None for m in metadata)
