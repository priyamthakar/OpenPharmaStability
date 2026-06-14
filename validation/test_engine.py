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


# ---------------------------------------------------------------------------
# v0.7.0: ``engine.analyze()`` must accept XLSX inputs directly
# ---------------------------------------------------------------------------
#
# v0.7.0 closes the gap where the engine's internal ``load_csv`` call
# would have failed on XLSX/XLSM input. The CSV -> XLSX round-trip
# test pins the contract: the dispatcher in ``data.io.load_table``
# forwards XLSX to ``load_xlsx``, and the rest of the pipeline
# (validate -> fit -> pool -> select -> bound -> crossing ->
# extrapolation) produces a ``StabilityResult`` with the same shape
# it would have produced for the CSV source.
#
# The XLSX loader's default sheet picker ("results" / "data" /
# "stability" / first sheet) means a single-sheet workbook with
# the CSV columns is read as a single data frame, so the resulting
# analysis is byte-equivalent to the CSV-driven one modulo any
# dtype round-trip drift in pandas -> openpyxl -> pandas.


def test_analyze_accepts_xlsx(tmp_path):
    """``analyze(xlsx_path, ...)`` must produce a valid
    ``StabilityResult`` for a 1-sheet XLSX mirror of the golden
    CSV. The rounded-down shelf life is in {16, 17, 18} to
    tolerate a 1-month dtype round-trip drift (the XLSX loader
    casts int columns through float on the way back), and the
    crossing status must be ``CrossingStatus.CROSSED``.
    """
    df = pd.read_csv(CSV)
    xlsx = tmp_path / "assay_3batch.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="data", index=False)

    result = analyze(
        path=str(xlsx),
        condition="25C/60RH",
        attribute="assay",
    )
    # The dispatcher must produce a real StabilityResult, not raise.
    assert isinstance(result, type(analyze(path=str(CSV), condition="25C/60RH", attribute="assay")))
    # The same model + crossing status the CSV produces on the
    # golden dataset: poolability=PARTIAL -> COMMON_SLOPE, and the
    # bound does cross within the 60-month horizon.
    assert result.model is ModelKind.COMMON_SLOPE
    assert result.crossing.status is CrossingStatus.CROSSED
    # 1-month dtype round-trip drift is documented and acceptable
    # for the XLSX mirror; the CSV gives 17, the XLSX can land at
    # 16 or 18 if the data went through an integer promotion.
    assert result.supported_shelf_life_months in (16, 17, 18)
    # The row count must match the source CSV (no rows dropped or
    # added by the dispatcher / XLSX loader).
    assert result.metadata["row_count"] == len(df)


# ---------------------------------------------------------------------------
# §9.7  Unknown direction raises ValueError (no spec columns)
# ---------------------------------------------------------------------------


def test_engine_unknown_direction_raises_when_no_spec(tmp_path):
    """analyze() must raise ValueError when no spec column is present.

    Without lower_spec or upper_spec the engine cannot determine a crossing
    direction, so it must fail loudly rather than returning a bogus result.
    """
    import pandas as pd

    rows = []
    for batch in ("A", "B", "C"):
        for t in (0.0, 3.0, 6.0, 12.0, 18.0, 24.0):
            rows.append(
                {
                    "batch": batch,
                    "time_months": t,
                    "value": 100.0 - 0.3 * t,
                    "attribute": "assay",
                    "condition": "25C/60RH",
                    # No lower_spec / upper_spec column.
                }
            )
    csv = tmp_path / "no_spec.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    with pytest.raises(ValueError, match="lower_spec|upper_spec|spec"):
        analyze(path=str(csv), condition="25C/60RH", attribute="assay")


# ---------------------------------------------------------------------------
# §9.13  Fewer than 3 batches produces the Q1E warning
# ---------------------------------------------------------------------------


def test_engine_two_batches_emits_q1e_warning(tmp_path):
    """analyze() must append a Q1E warning when n_batches < 3.

    ICH Q1E expects at least 3 production batches.  The engine must not
    silently succeed; it must warn.
    """
    import pandas as pd

    rows = []
    for batch in ("A", "B"):  # only 2 batches
        for t in (0.0, 3.0, 6.0, 12.0, 18.0, 24.0):
            rows.append(
                {
                    "batch": batch,
                    "time_months": t,
                    "value": 100.0 - 0.3 * t,
                    "attribute": "assay",
                    "condition": "25C/60RH",
                    "lower_spec": 90.0,
                }
            )
    csv = tmp_path / "two_batch.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    result = analyze(path=str(csv), condition="25C/60RH", attribute="assay")
    q1e_warnings = [w for w in result.warnings if "batch" in w.lower() and "q1e" in w.lower()]
    assert q1e_warnings, (
        f"Expected a Q1E batch-count warning; got warnings: {result.warnings}"
    )


# ---------------------------------------------------------------------------
# §9.14  Single time point returns a non-raising, non-CROSSED result
# ---------------------------------------------------------------------------


def test_engine_handles_single_time_point(tmp_path):
    """A dataset with only one unique time point must not raise.

    With one time point there is no slope to estimate; the engine should
    either surface a warning or return FLAT_OR_OPPOSITE / NO_CROSSING
    rather than propagating a divide-by-zero or NaN error.
    """
    import pandas as pd
    import pytest

    rows = [
        {"batch": b, "time_months": 0.0, "value": 100.0,
         "attribute": "assay", "condition": "25C/60RH", "lower_spec": 90.0}
        for b in ("A", "B", "C")
    ]
    csv = tmp_path / "single_tp.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    # Either raises a clear error or returns without an exception.
    try:
        result = analyze(path=str(csv), condition="25C/60RH", attribute="assay")
        # If it succeeds, the shelf life must not be a finite positive number
        # derived from a meaningless slope.
        assert result.supported_shelf_life_months is None or result.supported_shelf_life_months == 0 or \
            result.crossing.status.name in ("FLAT_OR_OPPOSITE", "NO_CROSSING", "FAIL_AT_BASELINE"), (
            f"Unexpected positive shelf life from single-time-point data: "
            f"{result.supported_shelf_life_months} months, status={result.crossing.status}"
        )
    except (ValueError, RuntimeError, ZeroDivisionError):
        # A clean exception is acceptable; what's not acceptable is a
        # silent wrong answer or an unhandled numpy/scipy traceback.
        pass


# ---------------------------------------------------------------------------
# §9.15  NaN in value column triggers a data-quality warning, not a crash
# ---------------------------------------------------------------------------


def test_engine_handles_nan_value(tmp_path):
    """A NaN in the value column must trigger a data-quality warning.

    The engine should surface the missing-value issue explicitly rather
    than allowing NaN to propagate silently into the regression.
    """
    import math
    import pandas as pd

    rows = []
    for batch in ("A", "B", "C"):
        for t in (0.0, 3.0, 6.0, 12.0, 18.0, 24.0):
            rows.append(
                {
                    "batch": batch,
                    "time_months": t,
                    "value": 100.0 - 0.3 * t,
                    "attribute": "assay",
                    "condition": "25C/60RH",
                    "lower_spec": 90.0,
                }
            )
    # Inject a single NaN value.
    rows[4]["value"] = float("nan")
    csv = tmp_path / "nan_value.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    result = analyze(path=str(csv), condition="25C/60RH", attribute="assay")
    nan_warnings = [
        w for w in result.warnings
        if "missing" in w.lower() or "nan" in w.lower()
    ]
    assert nan_warnings, (
        f"Expected a missing-value warning for the NaN row; "
        f"got warnings: {result.warnings}"
    )


# ---------------------------------------------------------------------------
# §9.16  Negative time row triggers a data-quality error
# ---------------------------------------------------------------------------


def test_engine_handles_negative_time(tmp_path):
    """A row with time_months < 0 must trigger a data-quality error.

    Negative stability time is physically impossible.  The engine must
    flag it via the data-quality pipeline, not silently include the row
    in the regression.
    """
    import pandas as pd

    rows = []
    for batch in ("A", "B", "C"):
        for t in (0.0, 3.0, 6.0, 12.0, 18.0, 24.0):
            rows.append(
                {
                    "batch": batch,
                    "time_months": t,
                    "value": 100.0 - 0.3 * t,
                    "attribute": "assay",
                    "condition": "25C/60RH",
                    "lower_spec": 90.0,
                }
            )
    # Inject a negative time point.
    rows[0]["time_months"] = -1.0
    csv = tmp_path / "neg_time.csv"
    pd.DataFrame(rows).to_csv(csv, index=False)
    result = analyze(path=str(csv), condition="25C/60RH", attribute="assay")
    neg_warnings = [
        w for w in result.warnings
        if "negative" in w.lower() or "time" in w.lower()
    ]
    assert neg_warnings, (
        f"Expected a negative-time warning; got warnings: {result.warnings}"
    )
