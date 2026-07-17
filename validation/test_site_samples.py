"""Regression guards for tracked public sample artifacts."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "site-sample"
DEPLOY = ROOT / "site" / "site-sample"


def _record(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_public_samples_capture_effective_guidance_provenance():
    single = _record(SOURCE / "sample-report.json")
    multi = _record(SOURCE / "multi" / "multi-report.json")

    for record in (single, multi):
        assert record["guidance_profile"] == "Q1A_R2+Q1E"
        assert record["guidance_status"] == "effective"
        assert record["guidance_reference"] == "ICH Q1A(R2) Step 4 + ICH Q1E Step 4"

    for attribute in multi["attributes"]:
        assert attribute["guidance_status"] == "effective"
        assert attribute["guidance_reference"] == multi["guidance_reference"]


def test_public_sample_html_is_portable_and_shows_guidance_provenance():
    single = (SOURCE / "sample-report.html").read_text(encoding="utf-8")
    multi = (SOURCE / "multi" / "multi-report.html").read_text(encoding="utf-8")

    assert "data:image/png;base64," in single
    assert "Guidance reference" in single
    assert "Guidance status" in multi
    assert "file://" not in multi


def test_deployment_samples_match_source_and_pdf_is_valid():
    relative_files = (
        Path("sample-report.html"),
        Path("sample-report.json"),
        Path("sample-report.pdf"),
        Path("multi") / "multi-report.html",
        Path("multi") / "multi-report.json",
    )
    for relative in relative_files:
        assert (DEPLOY / relative).read_bytes() == (SOURCE / relative).read_bytes()
    assert (SOURCE / "sample-report.pdf").read_bytes().startswith(b"%PDF-")
