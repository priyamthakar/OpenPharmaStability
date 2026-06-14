"""Engine integration tests: end-to-end on the golden dataset and edge cases.

These exercise the full pipeline (load → validate → fit → pool →
select → bound → crossing → extrapolation) via
:func:`openpharmastability.shelf_life.engine.analyze`.
"""
from __future__ import annotations

import json
import math
import pathlib
import platform

import pandas as pd
import pytest

from openpharmastability.contracts import (
    CrossingStatus,
    ModelKind,
    Poolability,
    TOOL_VERSION,
)
from openpharmastability.shelf_life.engine import analyze


ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV = ROOT / "examples" / "assay_3batch.csv"
EXPECTED = ROOT / "examples" / "assay_3batch.expected.json"


@pytest.fixture(scope="module")
def expected():
    with open(EXPECTED) as f:
        return json.load(f)


def test_engine_runs_on_golden():
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
    )
    assert result.attribute == "assay"
    assert result.condition == "25C/60RH"
    assert result.deliverable_term == "shelf life"
    # Common slope, different intercepts -> PARTIAL.
    assert result.poolability.decision is Poolability.PARTIAL
    assert result.model is ModelKind.COMMON_SLOPE
    # Crossing.
    assert result.crossing.status is CrossingStatus.CROSSED
    assert result.statistical_crossing_months is not None
    # Shelf life is integer months.
    assert isinstance(result.supported_shelf_life_months, int)
    # Rounded down: floor of crossing.
    assert result.supported_shelf_life_months == int(
        math.floor(result.statistical_crossing_months)
    )
    # Observed data: 24 months (max time point in the dataset).
    assert result.observed_data_months == 24.0


def test_engine_metadata_has_required_keys():
    result = analyze(
        path=str(CSV), condition="25C/60RH", attribute="assay",
    )
    md = result.metadata
    for k in (
        "tool_version",
        "timestamp",
        "file_path",
        "file_sha256",
        "row_count",
        "column_count",
        "library_versions",
        "random_seed",
    ):
        assert k in md, f"missing metadata key: {k}"
    assert md["tool_version"] == TOOL_VERSION
    assert md["row_count"] == 42
    # The CSV has at least the required 5 columns + the direction column
    # is OPTIONAL. Pin a lower bound rather than an exact count so the
    # test survives users adding/removing optional columns.
    assert md["column_count"] >= 5
    # But the user IS supplying both spec columns and a direction here.
    assert md["column_count"] == len(pd.read_csv(str(CSV)).columns)
    # SHA-256 of the CSV.
    assert len(md["file_sha256"]) == 64
    # ISO-8601 UTC.
    assert "T" in md["timestamp"] and md["timestamp"].endswith("Z")
    # Library versions are recorded.
    for lib in ("pandas", "numpy", "scipy", "statsmodels", "matplotlib", "jinja2"):
        assert lib in md["library_versions"]


def test_engine_pooled_fit_matches_golden_within_tolerance(expected):
    """The engine selects COMMON_SLOPE on this dataset (poolability
    is PARTIAL). The expected.json now contains a hand-computed
    COMMON_SLOPE section; this test pins the engine's reported
    values to it within tight tolerance. The slope b1 is the same
    in POOLED and COMMON_SLOPE, so we also check it.
    """
    result = analyze(
        path=str(CSV), condition="25C/60RH", attribute="assay",
    )
    cs = expected["common_slope_fit"]
    # Engine selects COMMON_SLOPE.
    assert result.model is ModelKind.COMMON_SLOPE
    # Common slope b1 matches the golden to rtol=1e-9.
    assert math.isclose(result.fit.params["b1"], cs["b1_common"],
                        rel_tol=1e-9, abs_tol=1e-9)
    # Per-batch intercepts match the golden to rtol=1e-9.
    for batch, rec in cs["per_batch"].items():
        b0_engine = result.fit.params[f"b0_{batch}"]
        assert math.isclose(b0_engine, rec["b0"], rel_tol=1e-9, abs_tol=1e-9)
    # Worst-case batch and crossing match the golden exactly
    # (the engine and the regen script agree to ~1e-9).
    assert result.crossing.governing_batch == cs["worst_case_batch"]
    assert math.isclose(
        result.statistical_crossing_months,
        cs["worst_case_crossing_months"],
        rel_tol=1e-9, abs_tol=1e-6,
    )
    # And the supported shelf life matches.
    assert result.supported_shelf_life_months == cs["supported_shelf_life_rounded_down"]


def test_engine_is_deterministic(expected):
    """Two consecutive analyze() calls must produce identical results."""
    r1 = analyze(path=str(CSV), condition="25C/60RH", attribute="assay", seed=42)
    r2 = analyze(path=str(CSV), condition="25C/60RH", attribute="assay", seed=42)
    assert r1.supported_shelf_life_months == r2.supported_shelf_life_months
    assert r1.statistical_crossing_months == r2.statistical_crossing_months
    assert r1.crossing.crossing_months == r2.crossing.crossing_months
    assert r1.fit.params == r2.fit.params
    # File SHA-256 is the same (same input).
    assert r1.metadata["file_sha256"] == r2.metadata["file_sha256"]


def test_engine_substance_returns_retest_period():
    result = analyze(
        path=str(CSV), condition="25C/60RH", attribute="assay",
        product_type="substance",
    )
    assert result.product_type == "substance"
    assert result.deliverable_term == "retest period"


def test_engine_no_crossing_edge_case(tmp_path):
    """A stable dataset never crosses the (very low) spec -> NO_CROSSING."""
    import pandas as pd
    rows = []
    for batch, b0 in (("B1", 105.0), ("B2", 106.0), ("B3", 104.0)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": b0 - 0.05 * t,
                "lower_spec": 70.0, "upper_spec": 120.0,
                "direction": "decreasing",
            })
    csv = tmp_path / "stable.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    result = analyze(
        path=str(csv), condition="25C/60RH", attribute="assay",
    )
    assert result.crossing.status is CrossingStatus.NO_CROSSING
    assert result.supported_shelf_life_months is None
    assert result.statistical_crossing_months is None


def test_engine_fail_at_baseline(tmp_path):
    rows = []
    for batch, b0 in (("B1", 89.0), ("B2", 88.0), ("B3", 90.0)):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": b0 - 0.5 * t,
                "lower_spec": 90.0, "upper_spec": 110.0,
                "direction": "decreasing",
            })
    import pandas as pd
    csv = tmp_path / "fail.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    result = analyze(
        path=str(csv), condition="25C/60RH", attribute="assay",
    )
    assert result.crossing.status is CrossingStatus.FAIL_AT_BASELINE
    assert result.supported_shelf_life_months == 0


def test_engine_flat_or_opposite(tmp_path):
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0):
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": 100.0,
                "lower_spec": 90.0, "upper_spec": 110.0,
                "direction": "decreasing",
            })
    import pandas as pd
    csv = tmp_path / "flat.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    result = analyze(
        path=str(csv), condition="25C/60RH", attribute="assay",
    )
    assert result.crossing.status is CrossingStatus.FLAT_OR_OPPOSITE
    assert result.supported_shelf_life_months is None
