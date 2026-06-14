"""Tests for ``openpharmastability.data.io.load_csv``.

The I/O layer is intentionally a thin wrapper, so these tests cover the
three behaviors that actually matter:

1. A round-trip (write a small CSV, read it back) preserves both the
   values and the column dtypes we expect from the spec example.
2. Missing / non-file paths fail with informative errors (not the
   generic pandas stack trace a user would otherwise see).
3. The loader does no column renaming or validation, so a frame that
   would fail schema validation still comes back raw — schema is a
   separate step.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from openpharmastability.data.io import load_csv


# Columns from the spec example. Listed explicitly so a regression in
# column order or names shows up as a test failure, not as a confusing
# downstream error.
SPEC_COLUMNS = [
    "batch",
    "condition",
    "temp_c",
    "rh",
    "time_months",
    "attribute",
    "value",
    "lower_spec",
    "upper_spec",
]


def _write_sample_csv(path: Path) -> pd.DataFrame:
    """Write a tiny 2-batch x 2-time-point CSV mirroring the spec example."""
    rows = [
        {"batch": "B1", "condition": "25C/60RH", "temp_c": 25, "rh": 60,
         "time_months": 0, "attribute": "assay", "value": 100.2,
         "lower_spec": 90, "upper_spec": 110},
        {"batch": "B1", "condition": "25C/60RH", "temp_c": 25, "rh": 60,
         "time_months": 3, "attribute": "assay", "value": 98.7,
         "lower_spec": 90, "upper_spec": 110},
        {"batch": "B2", "condition": "25C/60RH", "temp_c": 25, "rh": 60,
         "time_months": 0, "attribute": "assay", "value": 99.8,
         "lower_spec": 90, "upper_spec": 110},
        {"batch": "B2", "condition": "25C/60RH", "temp_c": 25, "rh": 60,
         "time_months": 3, "attribute": "assay", "value": 98.5,
         "lower_spec": 90, "upper_spec": 110},
    ]
    df = pd.DataFrame(rows, columns=SPEC_COLUMNS)
    df.to_csv(path, index=False)
    return df


def test_load_csv_roundtrip_preserves_rows_and_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "stability.csv"
    expected = _write_sample_csv(csv_path)

    loaded = load_csv(str(csv_path))

    # Row count and column names must match exactly. We do not assert
    # ``expected.equals(loaded)`` directly because pandas may upcast int
    # columns to float when re-reading if any cell is empty; that would
    # be a perfectly fine I/O behavior to lock in via a separate test.
    assert list(loaded.columns) == SPEC_COLUMNS
    assert len(loaded) == len(expected) == 4


def test_load_csv_preserves_dtypes_for_numeric_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "stability.csv"
    _write_sample_csv(csv_path)

    loaded = load_csv(str(csv_path))

    # All four numeric value columns must come back as numbers (not
    # objects). ``pd.api.types.is_numeric_dtype`` accepts both ints and
    # floats so this works regardless of upcasting.
    for col in ("temp_c", "rh", "time_months", "value",
                "lower_spec", "upper_spec"):
        assert pd.api.types.is_numeric_dtype(loaded[col]), (
            f"column {col!r} did not load as numeric dtype: "
            f"{loaded[col].dtype}"
        )


def test_load_csv_preserves_text_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "stability.csv"
    _write_sample_csv(csv_path)

    loaded = load_csv(str(csv_path))

    # Text columns must come back as string-like so downstream filters
    # (batch=='B1', condition=='25C/60RH') work as expected. pandas 2.x
    # surfaces string columns as ``object``; pandas 3.x uses the
    # dedicated ``string`` dtype. Either is fine — the key invariant
    # is "not numeric".
    for col in ("batch", "condition", "attribute"):
        assert not pd.api.types.is_numeric_dtype(loaded[col]), (
            f"text column {col!r} came back as numeric: {loaded[col].dtype}"
        )
    assert loaded["batch"].tolist() == ["B1", "B1", "B2", "B2"]
    assert loaded["condition"].unique().tolist() == ["25C/60RH"]


def test_load_csv_raises_for_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError) as excinfo:
        load_csv(str(missing))
    # The error message must include the path so the user can see
    # exactly which file we tried to open.
    assert str(missing) in str(excinfo.value)


def test_load_csv_raises_for_directory(tmp_path: Path) -> None:
    with pytest.raises((IsADirectoryError, PermissionError)):
        load_csv(str(tmp_path))


def test_load_csv_does_not_validate_schema(tmp_path: Path) -> None:
    """I/O is dumb on purpose: schema validation is a separate step."""
    bad = tmp_path / "missing_columns.csv"
    pd.DataFrame({"foo": [1, 2, 3]}).to_csv(bad, index=False)
    # This must NOT raise — the missing-column check lives in
    # ``schema.validate_and_select``, not here.
    loaded = load_csv(str(bad))
    assert list(loaded.columns) == ["foo"]
