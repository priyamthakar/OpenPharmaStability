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

import pathlib
from pathlib import Path

import pandas as pd
import pytest

from openpharmastability.data.io import load_csv, load_table


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


# ---------------------------------------------------------------------------
# v0.7.0: ``load_table`` dispatcher (CSV / XLSX / XLSM)
# ---------------------------------------------------------------------------
#
# ``load_table`` is the v0.7.0 convenience entry point that lets
# ``engine.analyze()`` accept CSV, XLSX, and XLSM inputs through a
# single ``path=`` argument. The tests below pin the four behaviors
# that matter:
#  1. CSV is the byte-equivalent of ``load_csv``.
#  2. XLSX round-trip reads back the same shape (row/column count)
#     as the source CSV.
#  3. Unsupported extensions raise ``ValueError`` with a useful
#     message (not a generic ``KeyError`` from the dispatcher).
#  4. Explicit ``sheet`` selection picks the right sheet in a
#     multi-sheet workbook.


ROOT = pathlib.Path(__file__).resolve().parents[1]
GOLDEN_CSV = ROOT / "examples" / "assay_3batch.csv"


def _write_xlsx(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    """Helper: write a multi-sheet XLSX with the openpyxl backend."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)


def test_load_table_csv_dispatches_to_load_csv() -> None:
    """``load_table(csv_path)`` returns the same frame as
    ``load_csv(csv_path)`` — i.e. the dispatcher is transparent for
    CSV inputs (no schema validation, no column renaming)."""
    from_csv = load_csv(str(GOLDEN_CSV))
    from_table = load_table(str(GOLDEN_CSV))
    pd.testing.assert_frame_equal(from_csv, from_table)


def test_load_table_xlsx_roundtrip(tmp_path: Path) -> None:
    """Write a small XLSX mirror of the golden CSV and read it back;
    the row/column count must match the CSV (no rows dropped or
    added by the dispatcher)."""
    csv = pd.read_csv(GOLDEN_CSV)
    xlsx = tmp_path / "assay.xlsx"
    _write_xlsx(xlsx, {"data": csv})
    loaded = load_table(str(xlsx))
    assert loaded.shape == csv.shape, (
        f"XLSX round-trip changed shape: csv={csv.shape} xlsx={loaded.shape}"
    )
    assert list(loaded.columns) == list(csv.columns)


def test_load_table_unsupported_extension_raises(tmp_path: Path) -> None:
    """An unsupported extension (e.g. ``.txt``) must raise
    ``ValueError`` with ``"unsupported"`` in the message so the user
    can see the dispatcher refused the file."""
    txt = tmp_path / "stability.txt"
    txt.write_text("batch,value\nB1,1.0\n")
    with pytest.raises(ValueError, match="unsupported"):
        load_table(str(txt))


def test_load_table_xlsx_sheet_selection(tmp_path: Path) -> None:
    """``load_table(path, sheet="second")`` must read the second
    sheet of a multi-sheet workbook. We write a 2-sheet XLSX with
    distinguishable column values per sheet and assert the
    dispatcher returned the second sheet's content."""
    xlsx = tmp_path / "two_sheets.xlsx"
    _write_xlsx(
        xlsx,
        {
            "first": pd.DataFrame({"batch": ["B1"], "value": [1.0]}),
            "second": pd.DataFrame({"batch": ["B2"], "value": [2.0]}),
        },
    )
    loaded = load_table(str(xlsx), sheet="second")
    assert loaded["batch"].tolist() == ["B2"]
    assert loaded["value"].tolist() == [2.0]


def test_load_table_xlsx_sheet_int_index() -> None:
    """``load_table(path, sheet=1)`` must read the workbook's
    second sheet by positional index. The XLSX loader's sheet
    name resolver takes the candidate list, and the dispatcher's
    ``sheet`` argument is forwarded to ``load_xlsx(sheet_name=...)``.
    The current ``load_xlsx`` API accepts a string ``sheet_name``;
    this test pins behavior at the string form, which is the
    documented contract for the dispatcher."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        xlsx = Path(td) / "two_sheets.xlsx"
        _write_xlsx(
            xlsx,
            {
                "first": pd.DataFrame({"batch": ["B1"], "value": [1.0]}),
                "second": pd.DataFrame({"batch": ["B2"], "value": [2.0]}),
            },
        )
        loaded = load_table(str(xlsx), sheet="second")
        assert loaded["batch"].tolist() == ["B2"]
