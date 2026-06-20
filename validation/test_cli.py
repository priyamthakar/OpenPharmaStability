"""Smoke tests for the CLI (``openpharmastability.cli``).

These run the actual console script as a subprocess against the
golden CSV, then verify the HTML / JSON / PNG artifacts exist, the
numbers match the golden, and two consecutive runs produce
analytically identical results (only the timestamp differs).
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV = ROOT / "examples" / "assay_3batch.csv"
EXPECTED = ROOT / "examples" / "assay_3batch.expected.json"


def _resolve_cli() -> list[str]:
    """Return the command list to invoke the CLI as a subprocess.

    Prefers the console script (requires it on PATH, which is the
    case in an activated venv). Falls back to ``python -m
    openpharmastability.cli`` when the script is not on PATH
    (e.g. when running ``python -m pytest`` from a venv that has
    not been activated).
    """
    exe = shutil.which("openpharmastability")
    if exe is not None:
        return [exe, "analyze"]
    return [sys.executable, "-m", "openpharmastability.cli", "analyze"]


def _resolve_version_cli() -> list[str]:
    """Like ``_resolve_cli`` but for the top-level ``--version`` flag.

    ``--version`` is a top-level argparse action and does not require
    a subcommand, so we cannot reuse ``_resolve_cli`` (which hard-codes
    ``"analyze"``). Same on-PATH / off-PATH fallback rules apply.
    """
    exe = shutil.which("openpharmastability")
    if exe is not None:
        return [exe, "--version"]
    return [sys.executable, "-m", "openpharmastability.cli", "--version"]


def _run_cli(*args: str, output_dir: pathlib.Path) -> dict:
    """Invoke the CLI; return parsed JSON from the output."""
    output_html = output_dir / "report.html"
    cmd = _resolve_cli() + [str(CSV), "--condition", "25C/60RH",
                            "--attribute", "assay", "--output", str(output_html),
                            *args]
    r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "OpenPharmaStability" in r.stdout
    with open(output_dir / "report.json") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 1. CLI runs and produces HTML / JSON / PNG
# ---------------------------------------------------------------------------


def test_cli_produces_artifacts(tmp_path):
    data = _run_cli(output_dir=tmp_path)
    assert (tmp_path / "report.html").exists()
    assert (tmp_path / "report.html").stat().st_size > 1024
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "confidence_plot.png").exists()
    assert (tmp_path / "confidence_plot.png").stat().st_size > 1024
    # Sanity-check the JSON shape.
    assert data["limiting_attribute"] == "assay"
    assert data["condition"] == "25C/60RH"
    assert data["model"] == "common_slope_batch_intercepts"
    assert data["poolability"] == "partial"


# ---------------------------------------------------------------------------
# 2. CLI numbers match the golden
# ---------------------------------------------------------------------------


def test_cli_matches_golden(tmp_path):
    with open(EXPECTED) as f:
        golden = json.load(f)
    data = _run_cli(output_dir=tmp_path)
    cs = golden["common_slope_fit"]
    # Worst-case batch and crossing match.
    assert data["governing_batch"] == cs["worst_case_batch"]
    assert abs(
        data["statistical_crossing_months"] - cs["worst_case_crossing_months"]
    ) < 1e-6
    assert data["supported_shelf_life_months"] == cs["supported_shelf_life_rounded_down"]


# ---------------------------------------------------------------------------
# 3. CLI is deterministic (only timestamp differs between runs)
# ---------------------------------------------------------------------------


def test_cli_is_deterministic(tmp_path):
    a = _run_cli(output_dir=tmp_path / "a")
    b = _run_cli(output_dir=tmp_path / "b")
    # Drop the timestamp from both, then assert byte-identical.
    if "metadata" in a and "timestamp" in a["metadata"]:
        a["metadata"].pop("timestamp")
    if "metadata" in b and "timestamp" in b["metadata"]:
        b["metadata"].pop("timestamp")
    assert a == b, "CLI output differs beyond timestamp"


# ---------------------------------------------------------------------------
# 4. CLI --seed is recorded
# ---------------------------------------------------------------------------


def test_cli_records_seed(tmp_path):
    data = _run_cli("--seed", "42", output_dir=tmp_path)
    assert data["metadata"]["random_seed"] == 42


# ---------------------------------------------------------------------------
# 5. CLI without --seed: random_seed is null
# ---------------------------------------------------------------------------


def test_cli_no_seed(tmp_path):
    data = _run_cli(output_dir=tmp_path)
    assert data["metadata"]["random_seed"] is None


# ---------------------------------------------------------------------------
# 6. CLI --product-type substance -> retest period
# ---------------------------------------------------------------------------


def test_cli_substance(tmp_path):
    data = _run_cli("--product-type", "substance", output_dir=tmp_path)
    assert data["product_type"] == "substance"
    assert data["deliverable_term"] == "retest period"


# ---------------------------------------------------------------------------
# 7. CLI --version
# ---------------------------------------------------------------------------


def test_cli_version():
    r = subprocess.run(_resolve_version_cli(),
                       capture_output=True, text=True, check=True)
    assert re.match(r"openpharmastability 0\.\d+\.\d+", r.stdout.strip())


# ---------------------------------------------------------------------------
# 8. CLI missing required arg fails
# ---------------------------------------------------------------------------


def test_cli_missing_condition_fails(tmp_path):
    r = subprocess.run(
        _resolve_cli() + [str(CSV), "--attribute", "assay", "--output", str(tmp_path / "x.html")],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "--condition" in r.stderr or "required" in r.stderr.lower()


# ---------------------------------------------------------------------------
# 9. CLI --source-epoch makes two runs byte-identical (timestamp included)
# ---------------------------------------------------------------------------


def test_cli_source_epoch_makes_deterministic(tmp_path):
    a = _run_cli("--source-epoch", "1700000000", output_dir=tmp_path / "a")
    b = _run_cli("--source-epoch", "1700000000", output_dir=tmp_path / "b")
    # With --source-epoch the timestamp is pinned, so the two JSONs
    # should be byte-identical WITHOUT having to pop the timestamp.
    # The existing test_cli_is_deterministic does have to pop the
    # timestamp; this new one confirms that --source-epoch closes
    # that gap.
    assert a == b, "CLI output differs despite --source-epoch"
    # And the pinned timestamp is what we expect.
    assert a["metadata"]["timestamp"] == "2023-11-14T22:13:20Z"


# ---------------------------------------------------------------------------
# 10. CLI is invokable via ``python -m openpharmastability.cli`` (v0.1.1 fix)
# ---------------------------------------------------------------------------


def test_cli_runs_without_activated_path():
    """The CLI must be invokable both via the console script and
    via ``python -m openpharmastability.cli``. This guards against
    the v0.1.1 fix where the test runner had to be able to start
    the CLI without requiring the venv to be activated.
    """
    with tempfile.TemporaryDirectory() as td:
        output = pathlib.Path(td) / "report.html"
        r = subprocess.run(
            [sys.executable, "-m", "openpharmastability.cli", "analyze",
             str(CSV), "--condition", "25C/60RH",
             "--attribute", "assay", "--output", str(output)],
            capture_output=True, text=True, check=True,
        )
        assert "OpenPharmaStability" in r.stdout
        assert output.exists()
        json_path = pathlib.Path(td) / "report.json"
        assert json_path.exists()
        with open(json_path) as f:
            data = json.load(f)
        assert data["limiting_attribute"] == "assay"


# ---------------------------------------------------------------------------
# 11. v0.4.0 — ICH Q1A significant-change gate CLI flags
# ---------------------------------------------------------------------------


def test_cli_accepts_no_significant_change_gate_flag(tmp_path):
    """`--no-significant-change-gate` is accepted; the gate is
    skipped; the JSON decision record carries
    ``"significant_change_accelerated": null``."""
    output_html = tmp_path / "report.html"
    cmd = _resolve_cli() + [
        str(CSV), "--condition", "25C/60RH",
        "--attribute", "assay", "--output", str(output_html),
        "--no-significant-change-gate",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert r.returncode == 0
    with open(tmp_path / "report.json") as f:
        data = json.load(f)
    # Gate was disabled: no SignificantChange was evaluated.
    assert data["significant_change_accelerated"] is None
    assert data["significant_change_intermediate"] is None
    # Default permissive values on the new fields.
    assert data["extrapolation_allowed"] is True
    assert data["extrapolation_rationale"] == ""


def test_cli_accelerated_condition_flag(tmp_path):
    """`--accelerated-condition "25C/60RH"` is accepted; the CLI
    exits 0 and produces a well-formed JSON record. The golden
    fixture has rows for ``25C/60RH`` only, so the engine
    interprets the long-term rows as the accelerated arm too —
    the gate fires and the JSON record reflects that. The point
    of the test is the flag round-trip, not the data contents.
    """
    output_html = tmp_path / "report.html"
    cmd = _resolve_cli() + [
        str(CSV), "--condition", "25C/60RH",
        "--attribute", "assay", "--output", str(output_html),
        "--accelerated-condition", "25C/60RH",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert r.returncode == 0
    with open(tmp_path / "report.json") as f:
        data = json.load(f)
    # The decision record is well-formed and the new gate fields
    # are populated (we do not pin True/False here because the
    # golden fixture's 25C/60RH rows satisfy the >= 5% assay
    # change criterion over the 24-month span).
    assert "significant_change_accelerated" in data
    assert "extrapolation_allowed" in data
    assert "extrapolation_rationale" in data
    # The new fields are JSON-serializable.
    assert data["significant_change_accelerated"] in (True, False, None)
    assert isinstance(data["extrapolation_allowed"], bool)
    assert isinstance(data["extrapolation_rationale"], str)


# ---------------------------------------------------------------------------
# 12. v0.5.0 — advanced-statistics CLI flags
# ---------------------------------------------------------------------------


def test_cli_accepts_random_effects_flag(tmp_path):
    """`--random-effects` is accepted; the CLI exits 0 and the
    JSON record carries ``model_effects == "random"``."""
    output_html = tmp_path / "report.html"
    cmd = _resolve_cli() + [
        str(CSV), "--condition", "25C/60RH",
        "--attribute", "assay", "--output", str(output_html),
        "--random-effects",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert r.returncode == 0
    with open(tmp_path / "report.json") as f:
        data = json.load(f)
    assert data["model_effects"] == "random"


def test_cli_accepts_arrhenius_flag(tmp_path):
    """`--arrhenius` is accepted; the CLI exits 0. The Arrhenius
    fit may be skipped (the golden fixture has only one
    temperature) but the CLI must not reject the flag."""
    output_html = tmp_path / "report.html"
    cmd = _resolve_cli() + [
        str(CSV), "--condition", "25C/60RH",
        "--attribute", "assay", "--output", str(output_html),
        "--arrhenius",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0
    # Artifacts are written even when the fit is skipped.
    assert (tmp_path / "report.html").exists()
    assert (tmp_path / "report.json").exists()


# ---------------------------------------------------------------------------
# 13. v0.6.0 -- new export flags (--no-html, --json-only, --pdf,
#     --artifact-dir, --quiet) and improved error handling
# ---------------------------------------------------------------------------


def test_cli_no_html_skips_html(tmp_path):
    """`--no-html` skips the HTML render; the JSON and the plot
    PNG are still written. Regression test for the v0.6.0
    CLI export knob."""
    output_html = tmp_path / "report.html"
    cmd = _resolve_cli() + [
        str(CSV), "--condition", "25C/60RH",
        "--attribute", "assay", "--output", str(output_html),
        "--no-html",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # HTML is NOT written.
    assert not (tmp_path / "report.html").exists(), (
        "HTML was written but --no-html was passed"
    )
    # JSON and plot PNG ARE written.
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "confidence_plot.png").exists()


def test_cli_json_only_writes_only_json(tmp_path):
    """`--json-only` writes ONLY the JSON decision record. The HTML
    is not rendered and the plot PNG is not written. Regression
    test for the v0.6.0 CLI export knob."""
    output_path = tmp_path / "decision.json"
    cmd = _resolve_cli() + [
        str(CSV), "--condition", "25C/60RH",
        "--attribute", "assay", "--output", str(output_path),
        "--json-only",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # JSON is written at the user-specified --output path.
    assert output_path.exists()
    # HTML and the plot PNG are NOT written.
    # (No 'report.html' sibling was requested, and the single-attribute
    # confidence plot is suppressed under --json-only.)
    assert not (tmp_path / "report.html").exists()
    assert not (tmp_path / "confidence_plot.png").exists()
    # The JSON has the right content.
    with open(output_path) as f:
        data = json.load(f)
    assert data["supported_shelf_life_months"] == 17
    assert data["limiting_attribute"] == "assay"


def test_cli_quiet_suppresses_summary_lines(tmp_path):
    """`--quiet` suppresses the per-step / per-attribute summary
    on stdout. The JSON still carries the correct supported
    shelf-life value. Regression test for the v0.6.0 CLI quiet
    flag."""
    output_html = tmp_path / "report.html"
    cmd = _resolve_cli() + [
        str(CSV), "--condition", "25C/60RH",
        "--attribute", "assay", "--output", str(output_html),
        "--quiet",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # Stdout does NOT contain the standard "supported shelf life: 17 months"
    # summary line.
    assert "supported shelf life: 17 months" not in r.stdout
    # But the JSON on disk carries the correct value.
    with open(tmp_path / "report.json") as f:
        data = json.load(f)
    assert data["supported_shelf_life_months"] == 17


def test_cli_no_html_and_json_only_mutually_exclusive(tmp_path):
    """Passing both --no-html and --json-only is rejected with a
    one-line ``ERROR:`` message and exit code 2."""
    output_html = tmp_path / "report.html"
    cmd = _resolve_cli() + [
        str(CSV), "--condition", "25C/60RH",
        "--attribute", "assay", "--output", str(output_html),
        "--no-html", "--json-only",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 2
    # The error mentions the conflict.
    assert "mutually exclusive" in r.stderr.lower() or (
        "--no-html" in r.stderr and "--json-only" in r.stderr
    )


def test_cli_missing_file_exits_nonzero_with_clear_message(tmp_path):
    """Pointing the CLI at a non-existent CSV must exit with a
    non-zero code and a one-line ``ERROR:`` message that names
    the offending path."""
    bogus = tmp_path / "does_not_exist.csv"
    output_html = tmp_path / "report.html"
    cmd = _resolve_cli() + [
        str(bogus), "--condition", "25C/60RH",
        "--attribute", "assay", "--output", str(output_html),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode != 0
    # The error line must name the offending value and be
    # recognisably an error (substring of one of the documented
    # error fragments).
    err = r.stderr.lower()
    assert (
        "not found" in err
        or "no such file" in err
        or "does not exist" in err
    )
    # And the path itself appears in stderr so the user can see
    # which file was missing.
    assert "does_not_exist.csv" in r.stderr


def test_cli_artifact_dir_produces_bundle(tmp_path):
    """`--artifact-dir DIR` writes a self-contained ReportArtifact
    bundle to DIR. The bundle has report.html (with the plot
    inlined as a base64 data URL), report.json, and the plot PNG."""
    output_html = tmp_path / "report.html"
    bundle_dir = tmp_path / "bundle"
    cmd = _resolve_cli() + [
        str(CSV), "--condition", "25C/60RH",
        "--attribute", "assay", "--output", str(output_html),
        "--artifact-dir", str(bundle_dir),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # Bundle directory was created.
    assert bundle_dir.is_dir()
    # All three expected files are inside the bundle.
    assert (bundle_dir / "report.html").exists()
    assert (bundle_dir / "report.json").exists()
    assert (bundle_dir / "confidence_plot.png").exists()
    # The bundle HTML is fully self-contained: the plot is inlined
    # as a base64 data URL so the HTML can be opened standalone.
    html_body = (bundle_dir / "report.html").read_text(encoding="utf-8")
    assert "data:image/png;base64," in html_body


def test_cli_pdf_when_no_backend_warns_not_crashes(tmp_path):
    """`--pdf PATH` must NOT crash when no PDF backend (weasyprint
    or pdfkit) is installed. The CLI exits 0, prints a warning to
    stderr, and the rest of the artifacts (HTML / JSON / plot) are
    written as usual.

    On systems where a PDF backend IS available the test still
    passes (a PDF file is written); the warn-and-continue path is
    not exercised, but the test does not regress the happy path.
    """
    pytest.importorskip("os")  # sanity; real import below
    # We intentionally do NOT skip on the PDF backend being
    # available: the contract is "warn but do not crash", which is
    # the same code path in both cases (we always try and only
    # branch on success).
    output_html = tmp_path / "report.html"
    pdf_path = tmp_path / "out.pdf"
    cmd = _resolve_cli() + [
        str(CSV), "--condition", "25C/60RH",
        "--attribute", "assay", "--output", str(output_html),
        "--pdf", str(pdf_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    # Exit code 0 even if no backend is installed.
    assert r.returncode == 0, r.stderr
    # HTML / JSON / plot are still written.
    assert (tmp_path / "report.html").exists()
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "confidence_plot.png").exists()


# ---------------------------------------------------------------------------
# 14. v0.7.0 -- new CLI flags: --sensitivity, --acceptance-csv
# ---------------------------------------------------------------------------


def test_cli_accepts_sensitivity_flag(tmp_path):
    """`--sensitivity` is accepted; the CLI exits 0; the JSON
    decision record carries a populated ``sensitivity_report``
    with one row per Cook's-distance influential point."""
    import csv
    output_html = tmp_path / "report.html"
    cmd = _resolve_cli() + [
        str(CSV), "--condition", "25C/60RH",
        "--attribute", "assay", "--output", str(output_html),
        "--sensitivity",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    with open(tmp_path / "report.json") as f:
        data = json.load(f)
    # The new field is present and populated.
    assert "sensitivity_report" in data
    assert data["sensitivity_report"] is not None
    assert "rows" in data["sensitivity_report"]
    # The golden fixture has 4 influential points.
    assert len(data["sensitivity_report"]["rows"]) == 4
    # Each row has the documented fields.
    row = data["sensitivity_report"]["rows"][0]
    for key in (
        "influential_row_index",
        "baseline_supported_shelf_life",
        "leave_one_out_supported_shelf_life",
        "leave_one_out_statistical_crossing_months",
        "diff_supported_shelf_life_months",
        "note",
    ):
        assert key in row, f"missing {key!r} in sensitivity row {row!r}"


def test_cli_acceptance_csv_writes_csv(tmp_path):
    """`--acceptance-csv PATH` writes a flat acceptance-criteria
    CSV at PATH. Single-attribute mode produces 1 row. The CSV
    has the documented column names."""
    import csv
    output_html = tmp_path / "report.html"
    csv_path = tmp_path / "acceptance.csv"
    cmd = _resolve_cli() + [
        str(CSV), "--condition", "25C/60RH",
        "--attribute", "assay", "--output", str(output_html),
        "--acceptance-csv", str(csv_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # The CSV file was written.
    assert csv_path.exists()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    # Single-attribute mode: exactly 1 row.
    assert len(rows) == 1
    # The columns include the documented fields.
    expected_cols = {
        "attribute", "condition", "supported_shelf_life_months",
        "included_in_limiting_decision",
    }
    assert expected_cols.issubset(set(reader.fieldnames)), (
        f"missing columns: {expected_cols - set(reader.fieldnames)}"
    )
    # The single row's values are the expected golden ones.
    assert rows[0]["attribute"] == "assay"
    assert rows[0]["condition"] == "25C/60RH"
    assert rows[0]["included_in_limiting_decision"] in ("True", "true", "1")
    # And the CLI prints the one-line summary on stdout.
    assert "acceptance criteria: wrote 1 row(s)" in r.stdout


def test_cli_acceptance_csv_multi_attribute_writes_csv(tmp_path):
    """Multi-attribute mode: `--acceptance-csv` produces one row
    per analyzed attribute."""
    import csv
    output_html = tmp_path / "report.html"
    csv_path = tmp_path / "acceptance_multi.csv"
    multi_csv = ROOT / "examples" / "multi_attribute.csv"
    cmd = _resolve_cli() + [
        str(multi_csv), "--condition", "25C/60RH",
        "--all-attributes", "--output", str(output_html),
        "--acceptance-csv", str(csv_path),
        "--source-epoch", "1700000000",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert csv_path.exists()
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # The shipped multi_attribute fixture has 2 attributes.
    assert len(rows) == 2
    # The CLI prints a one-line summary with the row count.
    assert "acceptance criteria: wrote 2 row(s)" in r.stdout


# ---------------------------------------------------------------------------
# v0.11.0 — --guidance flag
# ---------------------------------------------------------------------------


def test_cli_guidance_unknown_exits_2(tmp_path):
    cmd = _resolve_cli() + [
        str(CSV), "--condition", "25C/60RH",
        "--attribute", "assay", "--output", str(tmp_path / "o.html"),
        "--guidance", "bogus",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 2
    assert "unknown guidance profile" in r.stderr


def test_cli_guidance_q1ae_matches_default(tmp_path):
    a = _run_cli("--source-epoch", "1700000000", output_dir=tmp_path / "a")
    b = _run_cli("--guidance", "q1ae", "--source-epoch", "1700000000",
                 output_dir=tmp_path / "b")
    assert a == b


def test_cli_guidance_draft_records_profile_name(tmp_path):
    data = _run_cli("--guidance", "q1-consolidated-draft",
                    "--source-epoch", "1700000000", output_dir=tmp_path)
    assert data["guidance_profile"] == "Q1_consolidated_draft"
