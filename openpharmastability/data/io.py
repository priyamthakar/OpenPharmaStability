"""CSV I/O for OpenPharmaStability.

The I/O layer is intentionally thin. ``load_csv`` reads a CSV from disk into a
``pandas.DataFrame`` using sensible defaults for a stability dataset (UTF-8,
no index column, ``NaN`` for missing). It performs **no** schema validation,
**no** column renaming, and **no** type coercion. All of that lives in
``schema.py`` so that tests, in-memory fixtures, and CLI inputs all flow
through the same normalization pipeline.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_csv(path: str) -> pd.DataFrame:
    """Load a stability CSV from disk into a raw ``DataFrame``.

    Parameters
    ----------
    path:
        Filesystem path to a CSV file. The file must be readable as UTF-8
        text; binary or non-UTF-8 encodings are out of scope for v0.1.

    Returns
    -------
    pandas.DataFrame
        The CSV contents exactly as pandas reads them. No columns are dropped
        or renamed, no types are coerced, and no validation is performed —
        see :func:`openpharmastability.data.schema.validate_and_select` for
        the contract-enforcing step.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    PermissionError
        If the file exists but cannot be read.
    pd.errors.EmptyDataError
        If the file is empty.
    pd.errors.ParserError
        If the file is not valid CSV.
    """
    # ``Path`` lets us give a clean FileNotFoundError before pandas opens the
    # file, and accepts both POSIX and Windows-style paths.
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    if not p.is_file():
        raise IsADirectoryError(f"CSV path is not a file: {path}")

    # Default kwargs match the v0.1 dataset convention:
    #   - UTF-8 encoded text (spec example uses plain ASCII, but the
    #     degree/percent symbols in condition names are valid UTF-8)
    #   - no index column in the source file
    #   - empty strings -> NaN so downstream ``isna()`` checks are uniform
    return pd.read_csv(p, encoding="utf-8", index_col=False, na_values=[""])


def load_table(
    path: str,
    sheet: str | int | None = None,
) -> pd.DataFrame:
    """Load a stability data file (CSV, XLSX, or XLSM) into a DataFrame.

    Dispatches on the file extension:
      - .csv  -> load_csv(path)
      - .xlsx / .xlsm -> load_xlsx(path, sheet_name=sheet)
      - .xls  -> load_xlsx(path, sheet_name=sheet) (xlrd backend; documented
                 as legacy and out of scope; raises if not installed)

    This is the v0.7.0 convenience entry point that lets
    :func:`openpharmastability.shelf_life.engine.analyze` accept CSV and
    XLSX/XLSM inputs through a single ``path=`` argument. The numeric
    result is byte-equivalent for ``.csv`` inputs (it forwards to
    :func:`load_csv`).

    Parameters
    ----------
    path:
        Filesystem path to the input file. Extension determines the
        loader.
    sheet:
        Optional sheet name (str) or zero-based positional index (int)
        for XLSX/XLSM/XLS files. Forwarded to
        :func:`openpharmastability.data.xlsx.load_xlsx` as
        ``sheet_name``. Ignored for ``.csv`` files.

    Returns
    -------
    pandas.DataFrame
        The data, normalized to the same shape :func:`load_csv` would
        produce (no column renaming, no schema validation; see
        :func:`openpharmastability.data.schema.validate_and_select`).

    Raises
    ------
    ValueError
        If the file extension is not one of ``.csv``, ``.xlsx``,
        ``.xlsm``, ``.xls``.
    FileNotFoundError
        If ``path`` does not exist.
    """
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".csv":
        return load_csv(path)
    if ext in (".xlsx", ".xlsm", ".xls"):
        from openpharmastability.data.xlsx import load_xlsx
        return load_xlsx(path, sheet_name=sheet)
    raise ValueError(
        f"unsupported input extension {ext!r}; use .csv / .xlsx / .xlsm / .xls"
    )


__all__ = ["load_csv", "load_table"]
