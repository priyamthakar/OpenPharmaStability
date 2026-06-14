"""Tests for ``openpharmastability.data.xlsx.load_xlsx``.

The XLSX reader is a thin wrapper around pandas+openpyxl. The
behaviors that actually matter (and that we want to lock down) are:

1. The default sheet picker prefers the well-known names
   ("results", "data", "stability"), and falls back to the first
   sheet only when none of those are present.
2. An explicit ``sheet_name`` wins over the default heuristic, and
   an unknown name raises a clear error.
3. Surrounding whitespace on column names is stripped (but data
   values are not mutated).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from openpharmastability.data.xlsx import load_xlsx


def _write_xlsx(
    path: Path,
    sheets: dict[str, pd.DataFrame],
) -> None:
    """Write a multi-sheet XLSX file from a name -> DataFrame mapping."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)


def test_load_xlsx_default_sheet_picks_results(tmp_path: Path) -> None:
    """When "results" exists, it wins over other sheets by default."""
    xlsx = tmp_path / "data.xlsx"
    _write_xlsx(
        xlsx,
        {
            "cover": pd.DataFrame({"note": ["hello"]}),
            "results": pd.DataFrame({"batch": ["B1"], "value": [1.0]}),
            "extra": pd.DataFrame({"foo": [42]}),
        },
    )
    df = load_xlsx(str(xlsx))
    assert list(df.columns) == ["batch", "value"]
    assert df["batch"].tolist() == ["B1"]


def test_load_xlsx_falls_back_to_first_sheet(tmp_path: Path) -> None:
    """If no candidate name matches, use the first sheet in the workbook."""
    xlsx = tmp_path / "data.xlsx"
    _write_xlsx(
        xlsx,
        {
            "my_special_sheet": pd.DataFrame({"batch": ["B1"], "value": [9.5]}),
            "another": pd.DataFrame({"x": [1]}),
        },
    )
    df = load_xlsx(str(xlsx))
    # The first sheet in the workbook is the one we wrote first.
    assert list(df.columns) == ["batch", "value"]
    assert df["value"].tolist() == [9.5]


def test_load_xlsx_explicit_sheet(tmp_path: Path) -> None:
    """An explicit sheet_name overrides the default heuristic."""
    xlsx = tmp_path / "data.xlsx"
    _write_xlsx(
        xlsx,
        {
            "results": pd.DataFrame({"batch": ["B1"], "value": [1.0]}),
            "foo": pd.DataFrame({"batch": ["B2"], "value": [2.0]}),
        },
    )
    df = load_xlsx(str(xlsx), sheet_name="foo")
    assert df["batch"].tolist() == ["B2"]
    assert df["value"].tolist() == [2.0]


def test_load_xlsx_missing_sheet_raises(tmp_path: Path) -> None:
    """An explicit but unknown sheet_name raises ValueError, not KeyError."""
    xlsx = tmp_path / "data.xlsx"
    _write_xlsx(
        xlsx,
        {
            "results": pd.DataFrame({"batch": ["B1"], "value": [1.0]}),
        },
    )
    with pytest.raises(ValueError, match="not found"):
        load_xlsx(str(xlsx), sheet_name="nope")


def test_load_xlsx_strips_column_whitespace(tmp_path: Path) -> None:
    """Column names with leading/trailing spaces get trimmed."""
    xlsx = tmp_path / "data.xlsx"
    # Build a frame whose columns literally have spaces around them.
    raw = pd.DataFrame({
        " batch ": ["B1"],
        " value ": [1.5],
        " attribute ": ["assay"],
    })
    _write_xlsx(xlsx, {"results": raw})

    df = load_xlsx(str(xlsx))
    assert list(df.columns) == ["batch", "value", "attribute"]
