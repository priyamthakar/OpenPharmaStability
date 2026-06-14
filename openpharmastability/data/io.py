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


__all__ = ["load_csv"]
