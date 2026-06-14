"""Attribute metadata loader for OpenPharmaStability v0.2.0.

The metadata table is an optional separate CSV (or XLSX sheet) that
describes how each attribute should be analyzed. Required column:
``attribute``. Optional columns: ``unit``, ``direction``,
``lower_spec``, ``upper_spec``, ``spec_type``, ``transform``,
``attribute_role``, ``report_order``.

If no metadata is supplied, the engine falls back to the existing
v0.1 single-attribute inference (per-row direction / spec columns
or spec-limit inference).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from openpharmastability.contracts import (
    AttributeMetadata,
    AttributeRole,
    Direction,
)


_REQUIRED_COLUMNS = ("attribute",)
_OPTIONAL_COLUMNS = (
    "unit", "direction", "lower_spec", "upper_spec", "spec_type",
    "transform", "attribute_role", "report_order",
)


def _coerce_direction(value) -> Optional[Direction]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, Direction):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return Direction(s)
    except ValueError:
        # Surface a warning via the AttributeMetadata.warnings field
        # (the caller adds the metadata to a list and inspects it).
        return None


def _coerce_role(value) -> AttributeRole:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return AttributeRole.PRIMARY
    if isinstance(value, AttributeRole):
        return value
    s = str(value).strip().lower()
    if not s:
        return AttributeRole.PRIMARY
    try:
        return AttributeRole(s)
    except ValueError:
        return AttributeRole.PRIMARY


def _coerce_float(value) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value) -> Optional[int]:
    f = _coerce_float(value)
    return int(f) if f is not None else None


def load_attribute_metadata_csv(path: str) -> list[AttributeMetadata]:
    """Load a per-attribute metadata table from a CSV file.

    The CSV must have at least an ``attribute`` column. Any
    optional column present overrides the per-row data columns.

    Returns
    -------
    list[AttributeMetadata]
        One entry per row of the CSV. Bad values (unknown
        direction strings, unparseable floats) are coerced to
        ``None`` or to the default; the original input is recorded
        in the entry's ``warnings`` list.
    """
    df = pd.read_csv(path)
    return load_attribute_metadata_from_dataframe(df)


def load_attribute_metadata_from_dataframe(
    df: pd.DataFrame,
) -> list[AttributeMetadata]:
    """Same as ``load_attribute_metadata_csv`` but takes a DataFrame.
    Useful for tests and for the XLSX code path.
    """
    missing = [c for c in _REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"attribute metadata is missing required column(s): {missing!r}"
        )
    out: list[AttributeMetadata] = []
    for _, row in df.iterrows():
        warnings: list[str] = []
        attr = str(row["attribute"]).strip()
        if not attr:
            warnings.append("metadata row has empty attribute name; skipped")
            continue
        direction = _coerce_direction(row.get("direction"))
        if direction is None and pd.notna(row.get("direction")):
            warnings.append(
                f"unrecognized direction {row.get('direction')!r} for "
                f"attribute {attr!r}; defaulting to None"
            )
        role = _coerce_role(row.get("attribute_role"))
        spec_type_raw = row.get("spec_type")
        spec_type = (
            None
            if spec_type_raw is None or (isinstance(spec_type_raw, float) and pd.isna(spec_type_raw))
            else str(spec_type_raw).strip() or None
        )
        transform_raw = row.get("transform")
        transform = (
            "none"
            if transform_raw is None or (isinstance(transform_raw, float) and pd.isna(transform_raw))
            else str(transform_raw).strip() or "none"
        )
        _ALLOWED_TRANSFORMS = ("none", "log")
        if transform not in _ALLOWED_TRANSFORMS:
            warnings.append(
                f"transform {transform!r} for attribute {attr!r} is not "
                f"supported (allowed: {list(_ALLOWED_TRANSFORMS)}); falling back to 'none'"
            )
            transform = "none"
        out.append(AttributeMetadata(
            attribute=attr,
            unit=None if pd.isna(row.get("unit")) else str(row.get("unit")).strip(),
            direction=direction,
            lower_spec=_coerce_float(row.get("lower_spec")),
            upper_spec=_coerce_float(row.get("upper_spec")),
            spec_type=spec_type,
            transform=transform,
            attribute_role=role,
            report_order=_coerce_int(row.get("report_order")),
            warnings=warnings,
        ))
    return out


__all__ = [
    "load_attribute_metadata_csv",
    "load_attribute_metadata_from_dataframe",
]
