"""Tests for the v0.2.1 --bql-policy wiring (fix 5).

The CLI flag was accepted but ignored in v0.2.0; v0.2.1 threads it
through validate_and_select → apply_bql_policy.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from openpharmastability.data.bql import apply_bql_policy
from openpharmastability.data.schema import validate_and_select


def _make_bql_dataframe():
    """3 batches x 4 time points, one row per (batch, time) marked
    is_bql=True. Non-BQL rows are not included; the BQL policy will
    drop them and the result will be empty."""
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 12.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": 100.0 - 0.5 * t,
                "lower_spec": 90.0, "upper_spec": 110.0,
                "direction": "decreasing", "is_bql": True,
            })
    return pd.DataFrame(rows)


def _make_mixed_bql_dataframe():
    """3 batches x 4 time points, one is_bql=True per (batch, time)."""
    rows = []
    rng = np.random.default_rng(20260613)
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 12.0):
            is_bql = (batch == "B2" and t == 12.0)
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": 100.0 - 0.5 * t + float(rng.normal(0.0, 0.3)),
                "lower_spec": 90.0, "upper_spec": 110.0,
                "direction": "decreasing",
                "is_bql": is_bql,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Direct schema test
# ---------------------------------------------------------------------------


def test_validate_and_select_bql_policy_exclude_drops_bql_rows():
    df = _make_mixed_bql_dataframe()
    validated = validate_and_select(
        df, attribute="assay", condition="25C/60RH",
        bql_policy="exclude",
    )
    # 1 BQL row should be dropped.
    assert len(validated.df) == 11  # 12 - 1
    assert validated.bql_summary.policy == "exclude"
    assert validated.bql_summary.n_bql_rows == 1
    assert validated.bql_summary.n_excluded == 1
    # v0.3.0: warning text changed to "bql_policy='exclude': ...".
    assert any("bql_policy" in w for w in validated.warnings)


def test_validate_and_select_bql_policy_flag_keeps_rows():
    df = _make_mixed_bql_dataframe()
    validated = validate_and_select(
        df, attribute="assay", condition="25C/60RH",
        bql_policy="flag",
    )
    # "flag" is pass-through — all 12 rows kept.
    assert len(validated.df) == 12
    assert validated.bql_summary.policy == "flag"
    assert validated.bql_summary.n_bql_rows == 1
    assert validated.bql_summary.n_excluded == 0


def test_validate_and_select_bql_policy_substitute_loq_raises_without_loq():
    """v0.3.0: substitute_loq is real, but requires a finite loq column."""
    df = _make_mixed_bql_dataframe()
    with pytest.raises(ValueError, match="loq"):
        validate_and_select(
            df, attribute="assay", condition="25C/60RH",
            bql_policy="substitute_loq",
        )


def test_validate_and_select_bql_policy_substitute_loq_half_raises_without_loq():
    df = _make_mixed_bql_dataframe()
    with pytest.raises(ValueError, match="loq"):
        validate_and_select(
            df, attribute="assay", condition="25C/60RH",
            bql_policy="substitute_loq_half",
        )


# ---------------------------------------------------------------------------
# End-to-end CLI
# ---------------------------------------------------------------------------


def test_cli_bql_policy_exclude_runs(tmp_path):
    """The CLI's --bql-policy flag actually reaches the data layer."""
    df = _make_mixed_bql_dataframe()
    csv = tmp_path / "data.csv"
    df.to_csv(csv, index=False)
    out_html = tmp_path / "report.html"
    r = subprocess.run(
        [sys.executable, "-m", "openpharmastability.cli", "analyze",
         str(csv), "--condition", "25C/60RH", "--attribute", "assay",
         "--bql-policy", "exclude",
         "--source-epoch", "1700000000",
         "--output", str(out_html)],
        capture_output=True, text=True, check=True,
    )
    assert "OpenPharmaStability" in r.stdout
    assert out_html.exists()
    # The BQL row is dropped, so the analysis should still complete.
    json_path = tmp_path / "report.json"
    assert json_path.exists()
    import json
    with open(json_path) as f:
        data = json.load(f)
    assert data["limiting_attribute"] == "assay"


def test_cli_bql_policy_unknown_raises():
    df = _make_mixed_bql_dataframe()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        csv = pathlib.Path(td) / "data.csv"
        df.to_csv(csv, index=False)
        out_html = pathlib.Path(td) / "report.html"
        r = subprocess.run(
            [sys.executable, "-m", "openpharmastability.cli", "analyze",
             str(csv), "--condition", "25C/60RH", "--attribute", "assay",
             "--bql-policy", "this_is_not_a_real_policy",
             "--output", str(out_html)],
            capture_output=True, text=True,
        )
    # The argparse choices should reject it before the engine runs.
    assert r.returncode != 0
    assert "invalid choice" in r.stderr.lower() or "argument" in r.stderr.lower()
