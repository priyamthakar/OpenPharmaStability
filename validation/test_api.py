"""Tests for ``openpharmastability.api`` — the v0.6.0 thin programmatic
surface around the engine and the artifact bundle.

The fixture paths point at the shipped examples:

* ``examples/assay_3batch.csv`` (single-attribute golden)
* ``examples/multi_attribute.csv`` (multi-attribute, with
  ``impurity_a`` as the documented limiting attribute)

The artifact tests check the public surface contract:
``html_path`` / ``json_path`` exist, ``html_sha256`` matches the file
on disk, ``plot_inlined`` is True, and the multi-attribute bundle
carries one plot per attribute.

Tests 1–5 only require the engine, multi-engine, and the api module
itself. Tests 6–8 additionally require
``openpharmastability.reports.artifacts`` (Agent C) — they skip
cleanly when that module is not yet merged.
"""
from __future__ import annotations

import hashlib
import pathlib
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Fixtures: shipped example paths
# ---------------------------------------------------------------------------

ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "examples" / "assay_3batch.csv"
MULTI_CSV_PATH = ROOT / "examples" / "multi_attribute.csv"


# ---------------------------------------------------------------------------
# Module import: api must be importable for any test to run. The
# artifact module is a hard requirement for the artifact tests only.
# ---------------------------------------------------------------------------

pytest.importorskip(
    "openpharmastability.api",
    reason="api module not importable",
)

from openpharmastability.api import (  # noqa: E402  -- after importorskip
    analyze_and_artifact,
    analyze_csv,
    analyze_multi,
    analyze_path,
    analyze_xlsx,
    make_artifact,
)
from openpharmastability.contracts import (  # noqa: E402
    MultiAttributeResult,
    ReportArtifact,
    StabilityResult,
)


# ---------------------------------------------------------------------------
# 1) analyze_csv: returns a StabilityResult with the documented
#    supported shelf life on the golden fixture.
# ---------------------------------------------------------------------------


def test_analyze_csv_returns_stability_result():
    """analyze_csv on the golden CSV returns the v0.1 result shape."""
    result = analyze_csv(
        str(CSV_PATH), condition="25C/60RH", attribute="assay",
    )
    assert isinstance(result, StabilityResult)
    assert result.supported_shelf_life_months == 17
    assert result.condition == "25C/60RH"
    assert result.attribute == "assay"


# ---------------------------------------------------------------------------
# 2) analyze_xlsx: CSV → XLSX roundtrip yields the same result within
#    a tight tolerance (XLSX dtype can shift; the supported months
#    can land on either side of the floor).
# ---------------------------------------------------------------------------


def test_analyze_xlsx_roundtrip(tmp_path):
    """analyze_xlsx reads the chosen sheet, dispatches through a temp
    CSV, and reproduces the golden within the documented tolerance.
    """
    # Write the golden CSV out as XLSX.
    df = pd.read_csv(CSV_PATH)
    xlsx = tmp_path / "golden.xlsx"
    df.to_excel(xlsx, index=False, sheet_name="results")

    result = analyze_xlsx(
        str(xlsx), condition="25C/60RH", attribute="assay",
    )
    assert isinstance(result, StabilityResult)
    assert result.condition == "25C/60RH"
    assert result.attribute == "assay"
    # XLSX dtype round-trips can shift the rounded shelf life by 1
    # month. The golden is 17; the XLSX path may produce 16, 17, or
    # 18 depending on dtype coercion.
    assert result.supported_shelf_life_months in (16, 17, 18)
    # The statistical crossing should be close to the golden's
    # 17.955 +/- 0.5 months (any rounding shift is captured in the
    # integer above).
    if result.statistical_crossing_months is not None:
        assert result.statistical_crossing_months == pytest.approx(
            17.95, abs=0.5,
        )


# ---------------------------------------------------------------------------
# 3) analyze_path: dispatches to analyze_csv on a .csv file.
# ---------------------------------------------------------------------------


def test_analyze_path_csv_dispatches_to_csv():
    """analyze_path on a .csv dispatches to analyze_csv (same result)."""
    via_path = analyze_path(
        str(CSV_PATH), condition="25C/60RH", attribute="assay",
    )
    via_csv = analyze_csv(
        str(CSV_PATH), condition="25C/60RH", attribute="assay",
    )
    assert isinstance(via_path, StabilityResult)
    assert isinstance(via_csv, StabilityResult)
    assert via_path.supported_shelf_life_months == (
        via_csv.supported_shelf_life_months
    )
    assert via_path.statistical_crossing_months == (
        via_csv.statistical_crossing_months
    )
    # Equal up to the random_seed metadata key (the timestamp may
    # differ because the calls are not bit-for-bit simultaneous).
    assert via_path.supported_shelf_life_months == 17


# ---------------------------------------------------------------------------
# 4) analyze_path: dispatches to analyze_xlsx on an .xlsx file.
# ---------------------------------------------------------------------------


def test_analyze_path_xlsx_dispatches_to_xlsx(tmp_path):
    """analyze_path on a .xlsx dispatches to analyze_xlsx (same result)."""
    df = pd.read_csv(CSV_PATH)
    xlsx = tmp_path / "golden.xlsx"
    df.to_excel(xlsx, index=False, sheet_name="results")

    via_path = analyze_path(
        str(xlsx), condition="25C/60RH", attribute="assay",
    )
    via_xlsx = analyze_xlsx(
        str(xlsx), condition="25C/60RH", attribute="assay",
    )
    assert isinstance(via_path, StabilityResult)
    assert isinstance(via_xlsx, StabilityResult)
    assert via_path.supported_shelf_life_months == (
        via_xlsx.supported_shelf_life_months
    )


# ---------------------------------------------------------------------------
# 5) analyze_multi: multi-attribute run; impurity_a is the documented
#    limiting attribute on the shipped multi fixture.
# ---------------------------------------------------------------------------


def test_analyze_multi_limiting():
    """analyze_multi identifies the documented limiting attribute."""
    result = analyze_multi(
        str(MULTI_CSV_PATH), condition="25C/60RH", all_attributes=True,
    )
    assert isinstance(result, MultiAttributeResult)
    assert result.limiting_attribute == "impurity_a"
    # Both attributes crossed within the 60-month horizon on this
    # fixture, so the supported shelf life is a positive integer.
    assert result.supported_shelf_life_months is not None
    assert result.supported_shelf_life_months > 0
    # The per-attribute results are in the bundle.
    names = {ar.metadata.attribute for ar in result.attributes}
    assert {"assay", "impurity_a"} <= names


# ---------------------------------------------------------------------------
# 6) make_artifact / analyze_and_artifact: single-attribute bundle
#    contains a real HTML, JSON, plot, and a matching SHA-256.
#    Requires the v0.6.0 reports.artifacts module (Agent C).
# ---------------------------------------------------------------------------


def test_make_artifact_returns_report_artifact(tmp_path):
    """analyze_and_artifact builds a self-contained ReportArtifact."""
    pytest.importorskip(
        "openpharmastability.reports.artifacts",
        reason="reports.artifacts not importable (Agent C not merged yet)",
    )
    out_dir = tmp_path / "single_bundle"
    result, artifact = analyze_and_artifact(
        str(CSV_PATH),
        condition="25C/60RH",
        out_dir=str(out_dir),
        attribute="assay",
    )
    assert isinstance(result, StabilityResult)
    assert isinstance(artifact, ReportArtifact)
    # The two main files exist on disk.
    assert Path(artifact.html_path).exists()
    assert Path(artifact.json_path).exists()
    # html_sha256 matches the on-disk file.
    file_hash = hashlib.sha256(
        Path(artifact.html_path).read_bytes()
    ).hexdigest()
    assert artifact.html_sha256 == file_hash
    # plot_inlined is True by default.
    assert artifact.plot_inlined is True
    # The single-attribute bundle has exactly one plot path.
    assert len(artifact.plot_paths) == 1
    assert Path(artifact.plot_paths[0]).exists()
    # No PDF backend expected in the test env, so pdf_path is None.
    assert artifact.pdf_path is None


# ---------------------------------------------------------------------------
# 7) make_artifact: multi-attribute bundle has one plot per attribute.
#    Requires the v0.6.0 reports.artifacts module (Agent C).
# ---------------------------------------------------------------------------


def test_make_artifact_multi(tmp_path):
    """Multi-attribute artifact bundles one plot per analyzed attribute.

    Renders the per-attribute confidence plots into the bundle
    directory first (the canonical layout ``make_artifact`` discovers
    on its own) so the test exercises the artifact path itself, not
    the plot-rendering convenience in :func:`analyze_and_artifact`.
    """
    pytest.importorskip(
        "openpharmastability.reports.artifacts",
        reason="reports.artifacts not importable (Agent C not merged yet)",
    )
    out_dir = tmp_path / "multi_bundle"
    result = analyze_multi(
        str(MULTI_CSV_PATH), condition="25C/60RH", all_attributes=True,
    )

    # Render the per-attribute plots into the bundle directory using
    # the same path the artifact helper auto-discovers.
    from openpharmastability.data.io import load_csv
    from openpharmastability.data.schema import validate_and_select
    from openpharmastability.plots.confidence_plot import make_confidence_plot

    raw_df = load_csv(str(MULTI_CSV_PATH))
    out_dir.mkdir(parents=True, exist_ok=True)
    for ar in result.attributes:
        data = validate_and_select(
            raw_df, attribute=ar.metadata.attribute, condition="25C/60RH",
        )
        plot_path = str(out_dir / f"{ar.metadata.attribute}_confidence_plot.png")
        make_confidence_plot(ar.result, data, plot_path)

    artifact = make_artifact(result, str(out_dir))
    assert isinstance(artifact, ReportArtifact)
    # One plot per analyzed attribute.
    analyzed_names = {ar.metadata.attribute for ar in result.attributes}
    assert len(artifact.plot_paths) == len(analyzed_names)
    for p in artifact.plot_paths:
        assert Path(p).exists()


# ---------------------------------------------------------------------------
# 8) Top-level re-exports: the API callables are importable directly
#    from ``openpharmastability``.
# ---------------------------------------------------------------------------


def test_api_re_exports_from_top_level():
    """The api callables are re-exported from the top-level package."""
    import openpharmastability as pkg

    for name in (
        "analyze_csv", "analyze_xlsx", "analyze_path",
        "analyze_multi", "make_artifact", "analyze_and_artifact",
    ):
        assert hasattr(pkg, name), f"missing top-level re-export: {name}"
        # And each one is callable.
        assert callable(getattr(pkg, name))
    # And they are in __all__.
    for name in (
        "analyze_csv", "analyze_xlsx", "analyze_path",
        "analyze_multi", "make_artifact", "analyze_and_artifact",
    ):
        assert name in pkg.__all__, f"missing from __all__: {name}"

