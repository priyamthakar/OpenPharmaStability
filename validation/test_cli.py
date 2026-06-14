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
