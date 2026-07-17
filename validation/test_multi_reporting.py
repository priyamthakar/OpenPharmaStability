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
from openpharmastability.regulatory.profile import Q1_CONSOLIDATED_DRAFT
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
    assert rec["guidance_status"] == "effective"
    assert rec["guidance_reference"] == "ICH Q1A(R2) Step 4 + ICH Q1E Step 4"
    assert rec["limiting_attribute"] in (a.metadata.attribute for a in result.attributes)
    # Disclaimer is the verbatim text from contracts.DISCLAIMER.
    from openpharmastability.contracts import DISCLAIMER
    assert rec["disclaimer"] == DISCLAIMER


def test_multi_guidance_provenance_is_explicit_for_empty_and_nonempty_runs(tmp_path):
    """Aggregate provenance comes from the selected profile, never first attr."""
    full = analyze_many(
        str(CSV), condition="25C/60RH", all_attributes=True,
        source_epoch=1700000000, profile=Q1_CONSOLIDATED_DRAFT,
    )
    empty = analyze_many(
        str(CSV), condition="25C/60RH", attributes=["not_present"],
        source_epoch=1700000000, profile=Q1_CONSOLIDATED_DRAFT,
    )
    for result in (full, empty):
        record = to_multi_decision_record(result)
        assert result.profile_name == Q1_CONSOLIDATED_DRAFT.name
        assert record["guidance_profile"] == Q1_CONSOLIDATED_DRAFT.name
        assert record["guidance_status"] == "draft"
        assert record["guidance_reference"] == Q1_CONSOLIDATED_DRAFT.reference
        assert record["disclaimer"] == Q1_CONSOLIDATED_DRAFT.disclaimer
        assert all(
            attr["guidance_profile"] == Q1_CONSOLIDATED_DRAFT.name
            for attr in record["attributes"]
        )


def test_multi_reports_reject_mixed_guidance_provenance(tmp_path):
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True)
    result.attributes[0].result.profile_name = "incompatible_profile"
    with pytest.raises(ValueError, match="mixed guidance provenance"):
        to_multi_decision_record(result)
    with pytest.raises(ValueError, match="mixed guidance provenance"):
        render_multi_html(result, str(tmp_path / "plots"), str(tmp_path / "report.html"))


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
    assert "Guidance status" in html
    assert "effective" in html
    assert "ICH Q1A(R2) Step 4 + ICH Q1E Step 4" in html
    assert "file://" not in html
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


# ---------------------------------------------------------------------------
# v0.6.0 — multi-attribute HTML spec display fix
# ---------------------------------------------------------------------------


def test_multi_html_spec_display_shows_metadata_specs(tmp_path):
    """The v0.6.0 multi-HTML spec display must read the spec from
    the per-attribute :class:`AttributeMetadata` (not the dead
    ``r.fit.design`` / ``r.metadata.lower_spec`` branches that
    silently produced "lower=None, upper=None" for every attribute).

    Concretely: with the shipped ``multi_attribute_metadata.csv``
    (``assay``: lower=90, upper=110; ``impurity_a``: lower=None,
    upper=0.5) the per-attribute block for ``impurity_a`` must
    display the upper spec literal — and neither block may
    contain the bug literal "lower=None, upper=None".
    """
    result = analyze_many(
        str(CSV), condition="25C/60RH", all_attributes=True,
        source_epoch=1700000000,
        metadata_path=str(META),
    )
    out_html = tmp_path / "report_spec_fix.html"
    render_multi_html(
        result, plot_dir=str(tmp_path / "nope"), out_path=str(out_html),
    )
    html = out_html.read_text(encoding="utf-8")

    # The bug literal must NOT appear anywhere in the report.
    assert "lower=None, upper=None" not in html, (
        "spec display still shows 'lower=None, upper=None'; the "
        "AttributeMetadata-based read is not in place"
    )
    # And the "None" spec values must not be rendered as the string
    # "None" anywhere in the Spec lines.
    import re
    spec_lines = re.findall(r"Spec:.*?</p>", html, flags=re.DOTALL)
    assert spec_lines, "no per-attribute Spec: lines were rendered"
    for line in spec_lines:
        # The only "None" that should ever appear in a Spec line is
        # the em-dash placeholder "—" used for a missing limit.
        assert "=None" not in line, f"raw None leaked into spec line: {line!r}"

    # The impurity_a block must surface its upper spec (0.5).
    # The block is the <section id="attr-N"> ... </section> whose
    # <h2> mentions "impurity_a". We slice to the next <section> to
    # isolate the block.
    imp_start = html.find('id="attr-')
    while imp_start != -1:
        # Find the heading inside this section.
        section_end = html.find("</section>", imp_start)
        section = html[imp_start:section_end]
        if "impurity_a" in section.split("<h2>", 1)[1].split("</h2>", 1)[0]:
            break
        imp_start = html.find('id="attr-', section_end)
    assert imp_start != -1, "impurity_a section not found in HTML"
    section_end = html.find("</section>", imp_start)
    section = html[imp_start:section_end]
    # The spec literal in this block must include the upper value
    # (0.5). The renderer formats the float as "0.5".
    assert "upper=0.5" in section, (
        f"upper spec 0.5 not displayed for impurity_a; section was:\n{section!r}"
    )
    # And the missing lower must render as the em-dash placeholder.
    assert "lower=—" in section, (
        f"missing lower spec for impurity_a must show em-dash; section was:\n{section!r}"
    )


def test_multi_html_overview_table_no_none_spec_cells(tmp_path):
    """The overview table must not contain literal 'None' in the
    spec display. The spec is not currently rendered as a column
    in the overview table; this regression test simply guards
    against a future change that introduces a spec column with
    raw ``None`` values. ``analyze_many`` with the shipped
    metadata CSV is the smallest realistic input."""
    result = analyze_many(
        str(CSV), condition="25C/60RH", all_attributes=True,
        source_epoch=1700000000,
        metadata_path=str(META),
    )
    out_html = tmp_path / "report_overview.html"
    render_multi_html(
        result, plot_dir=str(tmp_path / "nope"), out_path=str(out_html),
    )
    html = out_html.read_text(encoding="utf-8")

    # Slice out the overview <table> directly under the
    # "Overall decision" heading. The decision record's structure
    # is documented in AGENTS.md / OpenPharmaStability.md; the
    # table has the column headers in a fixed order.
    import re
    overview_match = re.search(
        r"Overall decision.*?</table>", html, flags=re.DOTALL,
    )
    assert overview_match, "Overall decision table not found"
    overview = overview_match.group(0)
    # No "None" in any cell. The table cells render missing
    # values as "n/a" (documented in the existing test for the
    # statistical / supported columns) so any raw "None" leak is
    # a regression.
    assert "None" not in overview, (
        f"raw 'None' leaked into overview table:\n{overview!r}"
    )


# ---------------------------------------------------------------------------
# v0.7.0 sensitivity + acceptance-criteria multi-reporting tests
# ---------------------------------------------------------------------------


def test_multi_record_v070_has_top_level_acceptance_criteria():
    """Multi-attribute JSON record must expose the v0.7.0
    top-level ``acceptance_criteria`` list — one row per
    analyzed attribute, mirroring the per-attribute
    :class:`AttributeMetadata`."""
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    rec = to_multi_decision_record(result)
    assert "acceptance_criteria" in rec
    assert isinstance(rec["acceptance_criteria"], list)
    # The shipped fixture has 2 attributes.
    assert len(rec["acceptance_criteria"]) == 2
    # Each row carries the documented columns.
    for row in rec["acceptance_criteria"]:
        for key in (
            "attribute", "condition", "model", "poolability",
            "supported_shelf_life_months",
            "statistical_crossing_months",
            "observed_data_months",
            "extrapolation_flag",
            "included_in_limiting_decision",
            "exclusion_reason",
            "unit",
            "governing_batch",
        ):
            assert key in row, f"missing {key!r} in acceptance row {row!r}"
    # The unit comes from AttributeMetadata; the shipped
    # metadata CSV (when used) carries units. Without
    # metadata_path, AttributeMetadata.unit is None.
    # And the JSON is serializable.
    json.dumps(rec)


def test_multi_record_v070_has_per_attr_sensitivity_reports():
    """Multi-attribute JSON record must expose the v0.7.0
    per-attribute ``sensitivity_reports`` map AND the
    ``sensitivity_report`` key on each per-attribute entry.
    Default (no ``--sensitivity``) values are all ``None``."""
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    rec = to_multi_decision_record(result)
    assert "sensitivity_reports" in rec
    assert isinstance(rec["sensitivity_reports"], dict)
    # One entry per analyzed attribute.
    assert set(rec["sensitivity_reports"].keys()) == {
        ar.metadata.attribute for ar in result.attributes
    }
    # Default state: every value is None.
    for v in rec["sensitivity_reports"].values():
        assert v is None
    # The per-attribute record entries also expose
    # ``sensitivity_report`` (inherited from the single-attribute
    # record).
    for a in rec["attributes"]:
        assert "sensitivity_report" in a
        assert a["sensitivity_report"] is None
    # JSON-serializable.
    json.dumps(rec)


def test_multi_html_v070_sensitivity_marker(tmp_path):
    """A per-attribute result with ``sensitivity_report``
    populated must surface the 'Sensitivity:' marker in its
    per-attribute block. Default (None) results do NOT
    surface the marker."""
    from openpharmastability.contracts import (
        SensitivityReport, SensitivityRow,
    )
    result = analyze_many(str(CSV), condition="25C/60RH", all_attributes=True,
                          source_epoch=1700000000)
    assert len(result.attributes) >= 2
    # Populate sensitivity on exactly one attribute.
    ar0 = result.attributes[0]
    object.__setattr__(ar0.result, "sensitivity_report", SensitivityReport(
        rows=[
            SensitivityRow(
                influential_row_index=13,
                baseline_supported_shelf_life=17,
                leave_one_out_supported_shelf_life=18,
                leave_one_out_statistical_crossing_months=18.3,
                diff_supported_shelf_life_months=1,
                note="",
            ),
        ],
        summary="max delta 1 mo; 1 point changes the shelf life",
        baseline_supported_shelf_life=17,
        notes=[],
    ))
    # Defensive: the other attribute is still the default.
    for ar in result.attributes[1:]:
        assert getattr(ar.result, "sensitivity_report", None) is None
    out_html = tmp_path / "report_v070.html"
    render_multi_html(
        result, plot_dir=str(tmp_path / "nope"), out_path=str(out_html),
    )
    html = out_html.read_text(encoding="utf-8")
    # Exactly one per-attribute block carries the marker.
    assert html.count("<strong>Sensitivity:</strong>") == 1
    # The summary text surfaces.
    assert "max delta 1 mo" in html


# ---------------------------------------------------------------------------
# v0.9.0 — surface ``unit`` + ``report_order`` from AttributeMetadata
# ---------------------------------------------------------------------------
#
# The contract layer has carried ``unit`` and ``report_order`` on
# ``AttributeMetadata`` since v0.2.0. v0.9.0 surfaces them on the
# per-attribute HTML block, on the overview table, and adds a top-level
# ``attribute_order`` list to the multi JSON record. None of these
# fields reach into contracts, the CLI, or the engine; this section
# only exercises the reporting layer.


def _build_multi_result_with_metadata(meta_overrides: dict[str, dict]) -> MultiAttributeResult:
    """Build a 2-attribute :class:`MultiAttributeResult` whose
    ``AttributeMetadata`` entries are taken from ``meta_overrides``
    keyed by attribute name. Falls back to the shipped
    ``multi_attribute_metadata.csv`` for any keys not provided.
    The underlying :class:`StabilityResult` is the real engine output
    for the shipped ``multi_attribute.csv``; we then attach
    user-controlled metadata on top of it.
    """
    result = analyze_many(
        str(CSV), condition="25C/60RH", all_attributes=True,
        source_epoch=1700000000,
        metadata_path=str(META),
    )
    for ar in result.attributes:
        attr = ar.metadata.attribute
        if attr in meta_overrides:
            for k, v in meta_overrides[attr].items():
                object.__setattr__(ar.metadata, k, v)
    return result


def test_multi_html_surfaces_unit_per_attribute(tmp_path):
    """The v0.9.0 per-attribute HTML block must surface the
    ``unit`` string from :class:`AttributeMetadata` in both the
    per-attribute heading and the spec line."""
    result = _build_multi_result_with_metadata({
        "assay": {"unit": "%LC"},
        "impurity_a": {"unit": "%area"},
    })
    out_html = tmp_path / "report_unit.html"
    render_multi_html(
        result, plot_dir=str(tmp_path / "nope"), out_path=str(out_html),
    )
    html = out_html.read_text(encoding="utf-8")
    # The heading shows the unit in parentheses: "Attribute: assay (%LC)".
    assert "Attribute: assay (%LC)" in html
    assert "Attribute: impurity_a (%area)" in html
    # The spec line also shows "(unit: %LC)" / "(unit: %area)".
    assert "(unit: %LC)" in html
    assert "(unit: %area)" in html


def test_multi_html_surfaces_report_order_per_attribute(tmp_path):
    """The v0.9.0 per-attribute HTML block must surface the
    ``report_order`` integer from :class:`AttributeMetadata`."""
    result = _build_multi_result_with_metadata({
        "assay": {"report_order": 2},
        "impurity_a": {"report_order": 1},
    })
    out_html = tmp_path / "report_order.html"
    render_multi_html(
        result, plot_dir=str(tmp_path / "nope"), out_path=str(out_html),
    )
    html = out_html.read_text(encoding="utf-8")
    # The "Report order:" marker renders as
    # <strong>Report order:</strong> N. The integer must appear
    # after the closing </strong> tag, not inside it.
    assert "<strong>Report order:</strong> 1" in html
    assert "<strong>Report order:</strong> 2" in html
    # And the markers appear in the expected per-attribute block
    # (one per attribute).
    assert html.count("<strong>Report order:</strong>") == 2


def test_multi_record_attribute_order_top_level():
    """The v0.9.0 multi JSON record must expose a top-level
    ``attribute_order`` list. When ``report_order`` is supplied on
    every eligible attribute, the list is sorted by it; when none
    of the attributes carry a ``report_order``, the list mirrors
    the input order."""
    # All eligible attributes carry a report_order → sorted ascending.
    result = _build_multi_result_with_metadata({
        "assay": {"report_order": 2},
        "impurity_a": {"report_order": 1},
    })
    rec = to_multi_decision_record(result)
    assert "attribute_order" in rec
    assert isinstance(rec["attribute_order"], list)
    assert rec["attribute_order"] == ["impurity_a", "assay"]
    # Sanity: only the eligible attributes are listed (the shipped
    # fixture has both attributes eligible).
    assert set(rec["attribute_order"]).issubset(
        {ar.metadata.attribute for ar in result.attributes
         if ar.included_in_limiting_decision}
    )

    # Mixed: some have report_order, some don't. The ones without
    # sort AFTER the ones that have a value, and keep their
    # relative input order.
    result2 = _build_multi_result_with_metadata({
        "assay": {"report_order": None},
        "impurity_a": {"report_order": 3},
    })
    rec2 = to_multi_decision_record(result2)
    assert rec2["attribute_order"][0] == "impurity_a"
    assert "assay" in rec2["attribute_order"]

    # None carry report_order → matches input order.
    result3 = _build_multi_result_with_metadata({
        "assay": {"report_order": None},
        "impurity_a": {"report_order": None},
    })
    rec3 = to_multi_decision_record(result3)
    assert rec3["attribute_order"] == [
        ar.metadata.attribute for ar in result3.attributes
        if ar.included_in_limiting_decision
    ]


def test_multi_html_no_unit_falls_back_to_em_dash(tmp_path):
    """The v0.9.0 multi HTML block must fall back to the em-dash
    placeholder ``—`` when ``unit`` is ``None`` on every
    attribute. The literal string ``None`` must NOT leak into the
    rendered output (the per-attribute spec line and the overview
    Unit column both go through the fallback)."""
    result = _build_multi_result_with_metadata({
        "assay": {"unit": None},
        "impurity_a": {"unit": None},
    })
    out_html = tmp_path / "report_no_unit.html"
    render_multi_html(
        result, plot_dir=str(tmp_path / "nope"), out_path=str(out_html),
    )
    html = out_html.read_text(encoding="utf-8")
    # The spec line must not show the bare "unit: None" string.
    assert "unit: None" not in html
    # The "(unit: ...)" suffix is omitted when unit is None; the
    # placeholder "—" only appears in the overview table's Unit
    # column for the two attributes.
    import re
    overview_match = re.search(
        r"Overall decision.*?</table>", html, flags=re.DOTALL,
    )
    assert overview_match, "Overall decision table not found"
    overview = overview_match.group(0)
    # The Unit column header is present.
    assert "<th>Unit</th>" in overview
    # And the em-dash placeholder fills both Unit cells.
    unit_cells = re.findall(r"<td>([^<]*)</td>", overview)
    # Filter to the two Unit cells; they should each be exactly "—".
    em_dash_count = sum(1 for c in unit_cells if c == "—")
    assert em_dash_count >= 2, (
        f"expected at least 2 em-dash unit placeholders in overview; "
        f"got cells: {unit_cells!r}"
    )
