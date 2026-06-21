"""Tests for the v1 UI-facing service manifest."""
from __future__ import annotations

import json
import pathlib

import openpharmastability
from openpharmastability.ui_service import UIAnalysisOptions, analyze_for_ui


ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "examples" / "assay_3batch.csv"
MULTI_CSV_PATH = ROOT / "examples" / "multi_attribute.csv"


def test_analyze_for_ui_single_manifest(tmp_path):
    manifest = analyze_for_ui(
        str(CSV_PATH),
        str(tmp_path / "run"),
        UIAnalysisOptions(
            condition="25C/60RH",
            attribute="assay",
            guidance="q1ae",
            source_epoch=1700000000,
        ),
        url_prefix="/runs/test/artifact",
    )
    data = manifest.to_dict()

    assert data["status"] == "ok"
    assert data["mode"] == "single"
    assert data["version"] == openpharmastability.__version__
    assert data["guidance_profile"] == "Q1A_R2+Q1E"
    assert data["summary"]["supported_shelf_life_months"] == 17
    assert data["summary"]["limiting_attribute"] == "assay"
    assert "validated GxP" in data["disclaimer"]

    artifacts = {item["kind"]: item for item in data["artifacts"]}
    assert {"html", "json", "plot"} <= set(artifacts)
    assert artifacts["html"]["url"] == "/runs/test/artifact/report.html"
    assert pathlib.Path(artifacts["html"]["path"]).exists()
    assert pathlib.Path(artifacts["json"]["path"]).exists()
    json.loads(pathlib.Path(artifacts["json"]["path"]).read_text(encoding="utf-8"))
    assert artifacts["html"]["sha256"]
    assert artifacts["json"]["sha256"]


def test_analyze_for_ui_multi_manifest(tmp_path):
    manifest = analyze_for_ui(
        str(MULTI_CSV_PATH),
        str(tmp_path / "multi_run"),
        UIAnalysisOptions(
            condition="25C/60RH",
            all_attributes=True,
            guidance="q1-consolidated-draft",
            source_epoch=1700000000,
        ),
    )
    data = manifest.to_dict()

    assert data["status"] == "ok"
    assert data["mode"] == "multi"
    assert data["guidance_profile"] == "Q1_consolidated_draft"
    assert data["summary"]["limiting_attribute"] == "impurity_a"
    assert data["summary"]["attributes_analyzed"] >= 2
    assert data["record"]["guidance_profile"] == data["guidance_profile"]
    assert len([item for item in data["artifacts"] if item["kind"] == "plot"]) >= 2


def test_ui_service_re_exported():
    import openpharmastability as pkg

    assert callable(pkg.analyze_for_ui)
    assert "analyze_for_ui" in pkg.__all__
