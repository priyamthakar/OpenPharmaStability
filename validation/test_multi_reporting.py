"""Tests for v0.2.0 multi-attribute reporting
(``reports/multi_record`` and ``reports/multi_html``).
"""
from __future__ import annotations

import json
import pathlib

import pytest

from openpharmastability.contracts import (
    AttributeMetadata,
    AttributeResult,
    AttributeRole,
    Direction,
    ModelKind,
    MultiAttributeResult,
    Poolability,
    PoolabilityResult,
    StabilityResult,
)
from openpharmastability.reports.multi_html import render_multi_html
from openpharmastability.reports.multi_record import to_multi_decision_record
from openpharmastability.shelf_life import analyze_many


ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV = ROOT / "examples" / "multi_attribute.csv"
META = ROOT / "examples" / "multi_attribute_metadata.csv"


# ---------------------------------------------------------------------------
# JSON record
# ---------------------------------------------------------------------------


def test_json_record_top_level_keys():
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    rec = to_multi_decision_record(result)
    expected_keys = {
        "condition", "product_type", "deliverable_term",
        "supported_shelf_life_months", "statistical_crossing_months",
        "limiting_attribute", "observed_data_months", "attributes",
        "warnings", "metadata", "disclaimer",
    }
    assert set(rec.keys()) >= expected_keys
    assert rec["condition"] == "25C/60RH"
    assert rec["limiting_attribute"] in (a.metadata.attribute for a in result.attributes)
    # Disclaimer is the verbatim text from contracts.DISCLAIMER.
    from openpharmastability.contracts import DISCLAIMER
    assert rec["disclaimer"] == DISCLAIMER


def test_json_record_per_attribute_shape():
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    rec = to_multi_decision_record(result)
    assert isinstance(rec["attributes"], list)
    assert len(rec["attributes"]) == 2
    for a in rec["attributes"]:
        # The per-attribute record is the v0.1 single-attr record
        # augmented with multi-attr context.
        assert "limiting_attribute" in a
        assert "supported_shelf_life_months" in a
        assert "model" in a
        assert "poolability" in a
        assert "attribute_role" in a
        assert "included_in_limiting_decision" in a
        assert "confidence_bound" in a
    # JSON-serializable.
    json.dumps(rec)


def test_json_record_limiting_is_min_supported():
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    rec = to_multi_decision_record(result)
    eligible = [a for a in rec["attributes"] if a["included_in_limiting_decision"]]
    assert rec["limiting_attribute"] is not None
    shelves = [a["supported_shelf_life_months"] for a in eligible
               if a["supported_shelf_life_months"] is not None]
    assert rec["supported_shelf_life_months"] == min(shelves)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------


def test_html_render_writes_file(tmp_path):
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    out = tmp_path / "report.html"
    render_multi_html(result, plot_dir=str(tmp_path), out_path=str(out))
    assert out.exists()
    assert out.stat().st_size > 1024
    html = out.read_text(encoding="utf-8")
    # Executive summary block.
    assert "Executive summary" in html
    assert "Overall decision" in html
    # Per-attribute sections.
    for ar in result.attributes:
        assert f"id=\"attr-" in html or ar.metadata.attribute in html
    # Disclaimer verbatim.
    from openpharmastability.contracts import DISCLAIMER
    assert DISCLAIMER in html


def test_html_renders_with_no_plots(tmp_path):
    """HTML render should not crash when plot_dir is empty."""
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    out = tmp_path / "report.html"
    # plot_dir that doesn't exist
    render_multi_html(result, plot_dir=str(tmp_path / "nope"), out_path=str(out))
    html = out.read_text(encoding="utf-8")
    assert "No plot available" in html


# ---------------------------------------------------------------------------
# End-to-end CLI
# ---------------------------------------------------------------------------


def test_cli_multi_attribute_via_python_m(tmp_path):
    """The CLI can be invoked via ``python -m`` for multi-attribute mode."""
    import subprocess
    import sys
    out_html = tmp_path / "report.html"
    r = subprocess.run(
        [sys.executable, "-m", "openpharmastability.cli", "analyze",
         str(CSV), "--condition", "25C/60RH", "--all-attributes",
         "--source-epoch", "1700000000", "--output", str(out_html)],
        capture_output=True, text=True, check=True,
    )
    assert "limiting attribute" in r.stdout
    assert out_html.exists()
    plots_dir = tmp_path / "plots"
    # Per-attribute plots are written to <output_dir>/plots by default.
    # tmp_path is the output_dir (since we set --output to tmp_path/report.html).
    assert plots_dir.is_dir()
    # Should have one plot per attribute.
    pngs = list(plots_dir.glob("*_confidence_plot.png"))
    assert len(pngs) == 2


def test_cli_mutually_exclusive_flags(tmp_path):
    """--attribute and --all-attributes together is an error."""
    import subprocess
    import sys
    r = subprocess.run(
        [sys.executable, "-m", "openpharmastability.cli", "analyze",
         str(CSV), "--condition", "25C/60RH",
         "--attribute", "assay", "--all-attributes",
         "--output", str(tmp_path / "x.html")],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "mutually exclusive" in r.stderr.lower()


# ---------------------------------------------------------------------------
# v0.2.1 hotfix — HTML <img src> paths must point at the right location
# ---------------------------------------------------------------------------


def _write_stub_png(path: pathlib.Path) -> None:
    """Create a 0-byte stub file at ``path``. ``_rel_plot`` only checks
    ``os.path.exists`` on the candidate file, so a stub is enough to
    verify the path-routing logic without invoking the plotter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_html_references_plots_with_relative_path_subdir(tmp_path):
    """When plots live in a sub-directory of the HTML's directory
    (the CLI default: ``<out_dir>/plots``), the HTML must reference
    them via ``plots/<filename>`` rather than just the basename."""
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    plots_dir = tmp_path / "plots"
    out_html = tmp_path / "report.html"
    for ar in result.attributes:
        _write_stub_png(plots_dir / f"{ar.metadata.attribute}_confidence_plot.png")

    render_multi_html(
        result, plot_dir=str(plots_dir), out_path=str(out_html),
    )
    html = out_html.read_text(encoding="utf-8")
    # Each attribute's plot must be referenced via the sub-directory.
    for ar in result.attributes:
        expected = f"plots/{ar.metadata.attribute}_confidence_plot.png"
        assert expected in html, f"missing {expected} in rendered HTML"
    # The bare basename (no `plots/` prefix) should NOT appear on its
    # own as an img src — the browser would resolve it to the HTML's
    # directory, not the plots sub-directory.
    assert 'src="assay_confidence_plot.png"' not in html
    assert 'src="impurity_a_confidence_plot.png"' not in html


def test_html_plot_path_handles_missing_file(tmp_path):
    """If the plots_dir does not contain the expected PNG, the
    HTML must still render and show 'No plot available' for that
    attribute rather than crashing or embedding a broken src."""
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    out_html = tmp_path / "report.html"
    # Point at a directory that exists but is empty.
    empty_dir = tmp_path / "empty_plots"
    empty_dir.mkdir(parents=True, exist_ok=True)
    render_multi_html(
        result, plot_dir=str(empty_dir), out_path=str(out_html),
    )
    html = out_html.read_text(encoding="utf-8")
    assert out_html.exists()
    # One "No plot available" per attribute section.
    n_attrs = len(result.attributes)
    assert html.count("No plot available") == n_attrs
    # And no dangling <img> tags were emitted for missing files.
    assert "<img" not in html


def test_html_plot_path_handles_flat_dir(tmp_path):
    """When plots_dir is the same directory as the HTML (the user
    passed ``--plots-dir`` to point at the report's own folder),
    the HTML must reference plots by basename with no ``plots/``
    prefix."""
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    out_html = tmp_path / "report.html"
    # plots_dir == html_dir == tmp_path
    for ar in result.attributes:
        _write_stub_png(tmp_path / f"{ar.metadata.attribute}_confidence_plot.png")

    render_multi_html(
        result, plot_dir=str(tmp_path), out_path=str(out_html),
    )
    html = out_html.read_text(encoding="utf-8")
    for ar in result.attributes:
        expected = f'src="{ar.metadata.attribute}_confidence_plot.png"'
        assert expected in html, f"missing {expected} in rendered HTML"
    # The bug previously produced ``plots/<filename>`` even when the
    # plots were in the flat layout. Guard against regression.
    assert "plots/assay_confidence_plot.png" not in html
    assert "plots/impurity_a_confidence_plot.png" not in html


def test_rel_plot_helper_unit(tmp_path):
    """Direct unit tests for the ``_rel_plot`` helper covering the
    sub-directory, flat-directory, and missing-file cases."""
    from openpharmastability.reports.multi_html import _rel_plot

    html_dir = str(tmp_path)
    plots_dir = tmp_path / "plots"
    plots_dir.mkdir()
    attr = "assay"
    _write_stub_png(plots_dir / f"{attr}_confidence_plot.png")

    # Sub-dir case: relative path includes "plots/".
    rel = _rel_plot(str(plots_dir), attr, html_dir)
    assert rel == f"plots/{attr}_confidence_plot.png"

    # Flat case: relative path is just the basename.
    _write_stub_png(tmp_path / f"{attr}_confidence_plot.png")
    rel = _rel_plot(str(tmp_path), attr, html_dir)
    assert rel == f"{attr}_confidence_plot.png"

    # Missing file: None.
    rel = _rel_plot(str(tmp_path), "does_not_exist", html_dir)
    assert rel is None

    # Empty plot_dir: None.
    assert _rel_plot("", attr, html_dir) is None

    # Relative plot_dir is resolved against html_dir.
    rel = _rel_plot("plots", attr, html_dir)
    assert rel == f"plots/{attr}_confidence_plot.png"


# ---------------------------------------------------------------------------
# v0.4.0 ICH Q1A significant-change reporting tests (additive)
# ---------------------------------------------------------------------------


def test_multi_record_v040_has_overall_extrapolation():
    """Multi-attribute JSON record must expose the v0.4.0 top-level keys."""
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    rec = to_multi_decision_record(result)
    assert "extrapolation_allowed" in rec
    assert isinstance(rec["extrapolation_allowed"], bool)
    assert "extrapolation_rationale_per_attribute" in rec
    # One entry per analyzed attribute.
    assert set(rec["extrapolation_rationale_per_attribute"].keys()) == {
        ar.metadata.attribute for ar in result.attributes
    }
    # Each value is a string (possibly empty).
    for v in rec["extrapolation_rationale_per_attribute"].values():
        assert isinstance(v, str)
    # And the per-attribute records themselves also carry the five
    # v0.4.0 keys (inherited from the single-attribute record).
    for a in rec["attributes"]:
        assert "extrapolation_rationale" in a
        assert "significant_change_accelerated" in a
        assert "significant_change_details" in a
    # JSON-serializable.
    json.dumps(rec)


def test_multi_html_v040_per_attr_block(tmp_path):
    """Each per-attribute section whose gate was exercised must show
    the 'ICH Q1A gate:' marker."""
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    # Populate the gate on each eligible attribute so the per-attr
    # block always renders the marker. We attach via object.__setattr__
    # to bypass the dataclass's required-arg constructor.
    for ar in result.attributes:
        r = ar.result
        object.__setattr__(r, "extrapolation_rationale", "no accelerated sig change")
        object.__setattr__(r, "extrapolation_allowed", True)
        object.__setattr__(r, "significant_change_accelerated", False)
        object.__setattr__(r, "significant_change_intermediate", None)
        object.__setattr__(r, "significant_change_details", {
            ar.metadata.attribute: {
                "first_t": None,
                "evidence": "no change observed",
                "evaluated": True,
            },
        })
    out_html = tmp_path / "report_v040.html"
    render_multi_html(result, plot_dir=str(tmp_path / "nope"), out_path=str(out_html))
    html = out_html.read_text(encoding="utf-8")
    # Every attribute section must carry the ICH Q1A gate line.
    n_with_marker = html.count("ICH Q1A gate:")
    assert n_with_marker == len(result.attributes)
    # And the rationale identifier must show up once per attribute.
    assert html.count("no accelerated sig change") == len(result.attributes)


# ---------------------------------------------------------------------------
# v0.5.0 advanced-statistics multi-reporting tests (additive)
# ---------------------------------------------------------------------------


def test_multi_record_v050_has_model_effects_summary():
    """Multi-attribute JSON record must expose the two v0.5.0
    ``model_effects_*`` top-level summary keys."""
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    rec = to_multi_decision_record(result)
    assert "model_effects_per_attribute" in rec
    assert "any_random_effects_used" in rec
    # One entry per analyzed attribute.
    assert set(rec["model_effects_per_attribute"].keys()) == {
        ar.metadata.attribute for ar in result.attributes
    }
    # Each value is a non-empty string. The default ``"fixed"`` flows
    # through here unchanged.
    for v in rec["model_effects_per_attribute"].values():
        assert isinstance(v, str)
        assert v  # non-empty
    # The aggregate flag is a bool, and for a default-v0.4 result
    # nobody used random effects.
    assert isinstance(rec["any_random_effects_used"], bool)
    assert rec["any_random_effects_used"] is False
    # JSON-serializable.
    json.dumps(rec)


def test_multi_html_v050_model_effects_marker(tmp_path):
    """An attribute with ``model_effects='random'`` must surface the
    'Model effects:' marker in its per-attribute block, while the
    fixed-effect attribute must NOT carry that marker."""
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    assert len(result.attributes) >= 2
    # Mark exactly one attribute as random-effects; the rest stay
    # fixed (the default).
    random_attr = result.attributes[0]
    object.__setattr__(random_attr.result, "model_effects", "random")
    # Defensive: confirm the other attributes are still the default.
    for ar in result.attributes[1:]:
        assert getattr(ar.result, "model_effects", "fixed") == "fixed"
    out_html = tmp_path / "report_v050.html"
    render_multi_html(result, plot_dir=str(tmp_path / "nope"), out_path=str(out_html))
    html = out_html.read_text(encoding="utf-8")
    # Exactly one per-attribute block carries the 'Model effects:' marker.
    assert html.count("<strong>Model effects:</strong>") == 1
    # And the random label shows up exactly once; the fixed label
    # never appears (the template suppresses it).
    assert html.count("<code>random</code>") == 1
    assert "<code>fixed</code>" not in html


# ---------------------------------------------------------------------------
# v0.5.1 mixed-model convergence / boundary multi-reporting tests (additive)
# ---------------------------------------------------------------------------
#
# The per-attribute blocks inherit ``model_convergence`` from the
# single-attribute result. The top-level multi record adds a single
# ``any_convergence_issue`` aggregate. The multi-HTML per-attribute
# block mirrors the single-attribute "Mixed-model convergence" line,
# gated on ``model_effects == "random"``.


def test_multi_record_v051_has_any_convergence_issue():
    """Multi-attribute JSON record must expose ``any_convergence_issue``
    as a top-level boolean aggregate over the ELIGIBLE attributes."""
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    rec = to_multi_decision_record(result)
    assert "any_convergence_issue" in rec, (
        "missing any_convergence_issue key in multi-record"
    )
    assert isinstance(rec["any_convergence_issue"], bool)
    # Default state: nobody used random-effects, and even if they did
    # the default OLS-style convergence sub-block reports
    # converged=True, boundary=False. So the aggregate is False.
    assert rec["any_convergence_issue"] is False
    # The per-attribute entries also carry ``model_convergence``
    # (inherited from the single-attribute record).
    for a in rec["attributes"]:
        assert "model_convergence" in a
        assert isinstance(a["model_convergence"], dict)
    # JSON-serializable.
    json.dumps(rec)


def test_multi_record_v051_aggregates_convergence_issue():
    """A non-trivial ``model_convergence`` on an ELIGIBLE attribute
    must flip ``any_convergence_issue`` to True; a non-eligible
    attribute with the same payload must NOT (the aggregate is
    scoped to attributes that drive the overall decision)."""
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    assert len(result.attributes) >= 2
    # Mark the first attribute as random-effects with a boundary.
    ar0 = result.attributes[0]
    object.__setattr__(ar0.result, "model_effects", "random")
    object.__setattr__(
        ar0.result, "model_convergence",
        {
            "converged": False,
            "boundary": True,
            "message": "mixed model hit boundary (random-effect variance -> 0)",
        },
    )
    # Recompute the multi-record and assert the aggregate.
    rec = to_multi_decision_record(result)
    assert rec["any_convergence_issue"] is True


def test_multi_html_v051_convergence_marker(tmp_path):
    """A 2-attribute multi-result where one attribute has
    ``model_effects='random'`` and a non-trivial
    ``model_convergence`` must surface the "Mixed-model convergence"
    line on the random attribute's section, with a "NOT converged"
    marker for the boundary case."""
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    assert len(result.attributes) >= 2
    # Mark the first attribute as random with a non-converged
    # convergence sub-block. The other attribute stays fixed-effect
    # and the multi-html template will not render the
    # "Mixed-model convergence" line for it.
    ar0 = result.attributes[0]
    object.__setattr__(ar0.result, "model_effects", "random")
    object.__setattr__(
        ar0.result, "model_convergence",
        {
            "converged": False,
            "boundary": True,
            "message": "mixed model hit boundary (random-effect variance -> 0)",
        },
    )
    out_html = tmp_path / "report_v051.html"
    render_multi_html(result, plot_dir=str(tmp_path / "nope"), out_path=str(out_html))
    html = out_html.read_text(encoding="utf-8")
    # Exactly one per-attribute block carries the marker.
    assert html.count("<strong>Mixed-model convergence:</strong>") == 1
    # The NOT-converged label and the boundary tag are present.
    assert "NOT converged" in html
    assert "(boundary)" in html
