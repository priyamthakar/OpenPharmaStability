"""XLSX input for OpenPharmaStability v0.2.0.

The reader is intentionally thin: openpyxl reads the workbook, we
return a pandas DataFrame. We do not evaluate formulas manually —
openpyxl/pandas reads cached values.

Sheet selection: by default, we look for a sheet named "results",
"data", or the first sheet (in that order). The user can override
with the ``sheet_name`` argument.

v0.2.1 hotfix: ``pd.ExcelFile`` is wrapped in a ``with`` block so
the underlying zip handle is released on every code path (success,
exception, and a subsequent re-open on Windows).
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

# Default data-sheet candidates, in priority order. The first
# matching sheet wins; otherwise the first sheet is used.
_DEFAULT_DATA_SHEETS: tuple[str, ...] = ("results", "data", "stability")


def _resolve_sheet_name(
    sheet_names: Iterable[str],
    requested: str | None,
    candidates: tuple[str, ...],
) -> str:
    """Pick a sheet name given a list of available names."""
    names = list(sheet_names)
    if requested is not None:
        if requested not in names:
            raise ValueError(
                f"sheet {requested!r} not found; available: {names!r}"
            )
        return requested
    for c in candidates:
        if c in names:
            return c
    if not names:
        raise ValueError("workbook has no sheets")
    return names[0]


def load_xlsx(
    path: str,
    sheet_name: str | None = None,
) -> pd.DataFrame:
    """Load a stability data sheet as a pandas DataFrame.

    Parameters
    ----------
    path:
        Path to the .xlsx file.
    sheet_name:
        Optional explicit sheet name. If None, defaults are tried
        ("results", "data", "stability") and the first match wins;
        if none match, the first sheet in the workbook is used.

    Returns
    -------
    pd.DataFrame
        The contents of the chosen sheet, with column names stripped
        of surrounding whitespace.
    """
    engine = "openpyxl"  # declared in pyproject.toml
    # v0.2.1: wrap in a context manager so the file handle is closed
    # even on exception. This prevents "file is already open" errors
    # on Windows when callers re-open the same workbook.
    with pd.ExcelFile(path, engine=engine) as xls:
        chosen = _resolve_sheet_name(xls.sheet_names, sheet_name, _DEFAULT_DATA_SHEETS)
        df = xls.parse(sheet_name=chosen)
    # Strip column-name whitespace; do not mutate the user's data values.
    df = df.rename(columns={c: c.strip() for c in df.columns})
    return df


def load_xlsx_sheet(
    path: str,
    sheet_name: str | None,
    candidates: tuple[str, ...],
) -> pd.DataFrame:
    """Load an arbitrary sheet from an XLSX workbook by candidate names.

    Like :func:`load_xlsx` but the caller supplies the candidate
    sheet names (e.g. the metadata-sheet candidates
    ``("attributes", "metadata", "attribute_metadata")``). The same
    context-managed ``pd.ExcelFile`` pattern is used so the file
    handle is always released.

    Parameters
    ----------
    path:
        Path to the .xlsx file.
    sheet_name:
        Optional explicit sheet name. If None, ``candidates`` is
        scanned in order and the first match wins; if none match,
        the first sheet in the workbook is used.
    candidates:
        Sheet names to try, in priority order, when ``sheet_name``
        is not provided.

    Returns
    -------
    pd.DataFrame
        The contents of the chosen sheet, with column names
        stripped of surrounding whitespace.
    """
    engine = "openpyxl"
    with pd.ExcelFile(path, engine=engine) as xls:
        chosen = _resolve_sheet_name(xls.sheet_names, sheet_name, candidates)
        df = xls.parse(sheet_name=chosen)
    df = df.rename(columns={c: c.strip() for c in df.columns})
    return df


__all__ = ["load_xlsx", "load_xlsx_sheet"]
