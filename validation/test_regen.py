"""Tests for the regeneration script
(``tools/regen_expected.py``).

The script is the source of truth for the frozen expected.json; it
must be reproducible, must agree with itself in --check mode, and
must NOT be tautological (i.e. it must compute values independently
of the package's own stats code).
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pandas as pd
import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "regen_expected.py"
EXPECTED = ROOT / "examples" / "assay_3batch.expected.json"
CSV = ROOT / "examples" / "assay_3batch.csv"


def _load_module():
    """Import tools.regen_expected as a module without running its
    ``__main__`` block. We use ``importlib.util`` so pytest collection
    doesn't accidentally execute the script.
    """
    spec = importlib.util.spec_from_file_location("regen_expected", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. --check mode returns 0 when the file matches
# ---------------------------------------------------------------------------


def test_check_mode_returns_zero_when_matches():
    mod = _load_module()
    rc = mod.main(["--check"])
    assert rc == 0, "regen --check should pass against the committed expected.json"


# ---------------------------------------------------------------------------
# 2. The script does NOT import the project's own stats code
# ---------------------------------------------------------------------------


def test_script_does_not_import_project_stats(tmp_path):
    """The script must use plain numpy/scipy; importing the project's
    stats modules would make the cross-check tautological."""
    src = SCRIPT.read_text()
    forbidden = (
        "from openpharmastability.stats",
        "from openpharmastability.shelf_life",
        "from openpharmastability.data",
        "from openpharmastability.plots",
        "from openpharmastability.reports",
        "from openpharmastability.models",
    )
    for f in forbidden:
        assert f not in src, f"{SCRIPT} imports project code: {f!r}"


# ---------------------------------------------------------------------------
# 3. Regenerating produces the same file
# ---------------------------------------------------------------------------


def test_regen_is_idempotent(tmp_path):
    mod = _load_module()
    # Snapshot the current file.
    before = EXPECTED.read_text()
    # Regenerate into a temp location (we don't want to mutate the
    # committed file from a test; that's the user's job).
    df = mod._build_dataset()
    new = mod._build_expected(df)
    new_path = tmp_path / "expected.json"
    with open(new_path, "w") as f:
        json.dump(new, f, indent=2)
    # The freshly regenerated file should match the committed one.
    with open(EXPECTED) as f:
        committed = json.load(f)
    assert new == committed, "regen output differs from committed expected.json"


# ---------------------------------------------------------------------------
# 4. The dataset regeneration is deterministic
# ---------------------------------------------------------------------------


def test_dataset_is_deterministic():
    mod = _load_module()
    a = mod._build_dataset()
    b = mod._build_dataset()
    pd.testing.assert_frame_equal(a, b)


# ---------------------------------------------------------------------------
# 5. The CSV on disk matches the regenerated dataset
# ---------------------------------------------------------------------------


def test_csv_matches_regenerated_dataset():
    mod = _load_module()
    regenerated = mod._build_dataset()
    on_disk = pd.read_csv(CSV)
    pd.testing.assert_frame_equal(regenerated, on_disk)
