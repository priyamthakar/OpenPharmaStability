"""Tests for the reporting layer (HTML + JSON decision record)."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import numpy as np
import pytest

from openpharmastability.contracts import (
    CONFIDENCE,
    POOLABILITY_ALPHA,
    TOOL_VERSION,
    CrossingResult,
    CrossingStatus,
    DiagnosticsResult,
    Direction,
    FitResult,
    ModelKind,
    Poolability,
    PoolabilityResult,
    StabilityResult,
)
from openpharmastability.reports.html import render_html
from openpharmastability.reports.record import to_decision_record


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


ISO_TIMESTAMP = "2026-06-13T10:00:00+00:00"
FILE_SHA = "deadbeef" + "f" * 56  # 64 hex chars
LIB_VERSIONS = {
    "pandas": "2.2.0",
    "numpy": "1.26.4",
    "scipy": "1.12.0",
    "statsmodels": "0.14.1",
}


def _make_fit_result() -> FitResult:
    """A tiny but well-formed FitResult for the pooled model."""
    # Use a deterministic 2x2 covariance so JSON-serializability isn't
    # accidentally tested through the FitResult itself.
    cov = np.array([[0.5, -0.01], [-0.01, 0.001]])

    def _fitted(t: float) -> float:
        return 100.5 - 0.3 * float(t)

    return FitResult(
        kind=ModelKind.POOLED,
        params={"b0": 100.5, "b1": -0.3},
        df_resid=19,
        s_resid=0.4,
        cov=cov,
        fitted_fn=_fitted,
        design={"tbar": 9.0, "Sxx": 800.0, "n": 21},
        batches=["B1", "B2", "B3"],
    )


def _make_stability_result(
    *,
    product_type: str = "product",
    extrapolation_flag: bool = True,
    warnings: list[str] | None = None,
    supported_shelf_life_months: int | None = 24,
    statistical_crossing_months: float | None = 27.4,
    observed_data_months: float = 18.0,
    metadata: dict | None = None,
    direction: Direction = Direction.DECREASING,
    model: ModelKind = ModelKind.POOLED,
    poolability_decision: Poolability = Poolability.FULL,
    crossing_status: CrossingStatus = CrossingStatus.CROSSED,
    governing_batch: str | None = None,
) -> StabilityResult:
    """Build a hand-rolled StabilityResult fixture.

    The reporting layer is decoupled from the engine, so we do NOT call
    ``analyze()`` here (Wave 2 will do that). This fixture is just complete
    enough to exercise rendering and serialization.
    """
    pool = PoolabilityResult(
        decision=poolability_decision,
        p_slopes=0.42,
        p_intercepts=0.55,
        alpha=POOLABILITY_ALPHA,
        notes=["Slopes not rejected at alpha=0.25."],
    )
    crossing = CrossingResult(
        crossing_months=statistical_crossing_months,
        status=crossing_status,
        governing_batch=governing_batch,
        notes=[],
    )
    diagnostics = DiagnosticsResult(
        linearity_ok=True,
        homoscedastic_ok=True,
        normal_resid_ok=True,
        influential_points=[],
        notes=["Clean linear fit on the evaluated scale."],
        details={},
    )
    deliverable_term = "retest period" if product_type == "substance" else "shelf life"
    base_meta = {
        "file_sha256": FILE_SHA,
        "row_count": 21,
        "column_count": 9,
        "random_seed": None,
        "library_versions": LIB_VERSIONS,
        "tool_version": TOOL_VERSION,
        "timestamp": ISO_TIMESTAMP,
        "required_columns_valid": True,
        "n_batches": 3,
        "time_points": [0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0],
    }
    if metadata:
        base_meta.update(metadata)

    return StabilityResult(
        attribute="assay",
        condition="25C/60RH",
        direction=direction,
        model=model,
        poolability=pool,
        fit=_make_fit_result(),
        crossing=crossing,
        supported_shelf_life_months=supported_shelf_life_months,
        statistical_crossing_months=statistical_crossing_months,
        observed_data_months=observed_data_months,
        extrapolation_flag=extrapolation_flag,
        diagnostics=diagnostics,
        warnings=list(warnings or ["extrapolation flagged for review"]),
        metadata=base_meta,
        deliverable_term=deliverable_term,
        product_type=product_type,
        plot_filename="confidence_plot.png",
    )


# ---------------------------------------------------------------------------
# HTML report tests
# ---------------------------------------------------------------------------


def test_render_html_writes_file(tmp_path):
    result = _make_stability_result()
    out = tmp_path / "report.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    assert out.exists()
    # Non-empty.
    assert out.read_text(encoding="utf-8").strip() != ""


def test_render_html_contains_disclaimer(tmp_path):
    result = _make_stability_result()
    out = tmp_path / "report.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    # The verbatim disclaimer from contracts.DISCLAIMER must be present.
    from openpharmastability.contracts import DISCLAIMER
    assert DISCLAIMER in body


def test_render_html_contains_attribute_and_condition(tmp_path):
    result = _make_stability_result()
    out = tmp_path / "report.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert "assay" in body
    assert "25C/60RH" in body


def test_render_html_contains_selected_model(tmp_path):
    result = _make_stability_result(model=ModelKind.POOLED)
    out = tmp_path / "report.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    # Both the enum value and the human label.
    assert ModelKind.POOLED.value in body
    assert "Pooled regression" in body


def test_render_html_contains_poolability_decision(tmp_path):
    result = _make_stability_result(poolability_decision=Poolability.FULL)
    out = tmp_path / "report.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert Poolability.FULL.value in body
    assert "Full pooling" in body


def test_render_html_contains_shelf_life_and_observed_months(tmp_path):
    result = _make_stability_result(
        supported_shelf_life_months=24,
        statistical_crossing_months=27.4,
        observed_data_months=18.0,
    )
    out = tmp_path / "report.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert "24 months" in body
    assert "18" in body
    # The statistical crossing is also surfaced.
    assert "27.4" in body


def test_render_html_contains_iso_timestamp(tmp_path):
    result = _make_stability_result()
    out = tmp_path / "report.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert ISO_TIMESTAMP in body
    # Sanity check: the value is genuinely ISO-8601 parseable.
    parsed = datetime.fromisoformat(ISO_TIMESTAMP)
    assert parsed.tzinfo is not None or ISO_TIMESTAMP.endswith("Z") is False


def test_render_html_mentions_deliverable_term(tmp_path):
    result = _make_stability_result(product_type="product")
    out = tmp_path / "report.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    # Deliverable term is the v0.1 default for a drug product.
    assert "shelf life" in body.lower()

    # And the substance variant uses "retest period".
    result2 = _make_stability_result(product_type="substance")
    out2 = tmp_path / "report_substance.html"
    render_html(result2, plot_png_path=None, out_path=str(out2))
    body2 = out2.read_text(encoding="utf-8")
    assert "retest period" in body2.lower()


def test_render_html_escapes_user_supplied_strings(tmp_path):
    """A malicious attribute name must be HTML-escaped, not injected."""
    result = _make_stability_result()
    # Mutate the attribute to contain HTML, bypassing the dataclass's
    # type check by going through object.__setattr__.
    object.__setattr__(result, "attribute", '<script>alert("x")</script>')
    out = tmp_path / "report_escape.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body


def test_render_html_embeds_plot_src_when_provided(tmp_path):
    """When a plot path is passed, the report must embed an <img> tag."""
    result = _make_stability_result()
    plot_path = "confidence_plot.png"
    out = tmp_path / "report_plot.html"
    render_html(result, plot_png_path=plot_path, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert "<img" in body
    assert plot_path in body


def test_render_html_omits_plot_when_path_is_none(tmp_path):
    """When no plot path is provided, the report must not include an <img>."""
    result = _make_stability_result()
    out = tmp_path / "report_no_plot.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert "<img" not in body


def test_render_html_contains_reproducibility_block(tmp_path):
    result = _make_stability_result()
    out = tmp_path / "report_repro.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert FILE_SHA in body
    assert TOOL_VERSION in body
    # At least one library version surfaced.
    assert "pandas" in body
    assert "2.2.0" in body


def test_render_html_contains_pvalues_and_alpha(tmp_path):
    result = _make_stability_result()
    out = tmp_path / "report_pvals.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    # p-values for slopes and intercepts.
    assert "0.42" in body
    assert "0.55" in body
    # Alpha is rendered.
    assert "0.25" in body


def test_render_html_contains_warnings(tmp_path):
    result = _make_stability_result(
        warnings=["extrapolation flagged for review", "fewer than 3 batches"],
    )
    out = tmp_path / "report_warn.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert "extrapolation flagged for review" in body
    assert "fewer than 3 batches" in body


# ---------------------------------------------------------------------------
# JSON decision record tests
# ---------------------------------------------------------------------------


def test_record_is_dict_and_json_serializable():
    result = _make_stability_result()
    rec = to_decision_record(result)
    assert isinstance(rec, dict)
    # Must be JSON-serializable (no numpy types leaking).
    text = json.dumps(rec)
    # And round-trip.
    roundtrip = json.loads(text)
    assert roundtrip == rec


def test_record_has_required_keys():
    result = _make_stability_result()
    rec = to_decision_record(result)
    required = {
        "supported_shelf_life_months",
        "statistical_crossing_months",
        "limiting_attribute",
        "condition",
        "model",
        "poolability",
        "poolability_alpha",
        "confidence_bound",
        "observed_long_term_months",
        "extrapolation",
        "warnings",
        "deliverable_term",
        "product_type",
        "metadata",
    }
    assert required.issubset(rec.keys()), (
        f"Missing keys: {required - rec.keys()}"
    )


def test_record_supported_shelf_life_is_int_or_none():
    result_int = _make_stability_result(supported_shelf_life_months=24)
    rec_int = to_decision_record(result_int)
    assert rec_int["supported_shelf_life_months"] == 24
    assert isinstance(rec_int["supported_shelf_life_months"], int)

    result_none = _make_stability_result(supported_shelf_life_months=None)
    rec_none = to_decision_record(result_none)
    assert rec_none["supported_shelf_life_months"] is None


def test_record_confidence_bound_decreasing_is_lower_one_sided():
    result = _make_stability_result(direction=Direction.DECREASING)
    rec = to_decision_record(result)
    assert rec["confidence_bound"] == "lower_one_sided_95_mean"


def test_record_confidence_bound_increasing_is_upper_one_sided():
    result = _make_stability_result(direction=Direction.INCREASING)
    rec = to_decision_record(result)
    assert rec["confidence_bound"] == "upper_one_sided_95_mean"


def test_record_confidence_bound_unknown_is_two_sided():
    result = _make_stability_result(direction=Direction.UNKNOWN)
    rec = to_decision_record(result)
    assert rec["confidence_bound"] == "two_sided_95_mean"


def test_record_limiting_attribute_matches_result():
    result = _make_stability_result()
    rec = to_decision_record(result)
    assert rec["limiting_attribute"] == "assay"
    assert rec["condition"] == "25C/60RH"


def test_record_extrapolation_flag_maps_to_string():
    on = _make_stability_result(extrapolation_flag=True)
    off = _make_stability_result(extrapolation_flag=False)
    assert to_decision_record(on)["extrapolation"] == "flag_required"
    assert to_decision_record(off)["extrapolation"] == "none"


def test_record_poolability_decision_serialized_as_string():
    result = _make_stability_result(poolability_decision=Poolability.PARTIAL)
    rec = to_decision_record(result)
    assert rec["poolability"] == Poolability.PARTIAL.value
    assert rec["poolability_alpha"] == pytest.approx(POOLABILITY_ALPHA)
    # Both p-values surfaced.
    assert rec["p_value_slopes"] == pytest.approx(0.42)
    assert rec["p_value_intercepts"] == pytest.approx(0.55)


def test_record_metadata_is_flattened():
    result = _make_stability_result()
    rec = to_decision_record(result)
    md = rec["metadata"]
    # All four required reproducibility keys present.
    for key in ("file_sha256", "library_versions", "tool_version", "timestamp"):
        assert key in md, f"metadata missing {key}"
    assert md["file_sha256"] == FILE_SHA
    assert md["tool_version"] == TOOL_VERSION
    assert md["timestamp"] == ISO_TIMESTAMP
    assert md["library_versions"]["pandas"] == "2.2.0"
    # Extra fields the engine / caller may have added are preserved.
    assert md["row_count"] == 21
    assert md["column_count"] == 9
    assert md["required_columns_valid"] is True


def test_record_deliverable_term_and_product_type():
    p = _make_stability_result(product_type="product")
    s = _make_stability_result(product_type="substance")
    pr = to_decision_record(p)
    sr = to_decision_record(s)
    assert pr["deliverable_term"] == "shelf life"
    assert pr["product_type"] == "product"
    assert sr["deliverable_term"] == "retest period"
    assert sr["product_type"] == "substance"


def test_record_warnings_serialized_as_list_of_strings():
    result = _make_stability_result(
        warnings=["warn A", "warn B"],
    )
    rec = to_decision_record(result)
    assert rec["warnings"] == ["warn A", "warn B"]


def test_record_diagnostics_summary_present():
    result = _make_stability_result()
    rec = to_decision_record(result)
    diag = rec["diagnostics"]
    assert diag["linearity_ok"] is True
    assert diag["homoscedastic_ok"] is True
    assert diag["normal_resid_ok"] is True
    assert diag["n_influential_points"] == 0


def test_record_handles_missing_metadata_gracefully():
    """Even with sparse metadata, the record must still be valid JSON."""
    result = _make_stability_result()
    # Wipe metadata so the helper defaults do not leak through.
    result.metadata = {}
    rec = to_decision_record(result)
    text = json.dumps(rec)
    roundtrip = json.loads(text)
    assert roundtrip == rec
    # Defaults are filled in for the reproducibility keys.
    assert rec["metadata"]["tool_version"] == TOOL_VERSION
    assert rec["metadata"]["file_sha256"] is None
    assert rec["metadata"]["timestamp"] is None


def test_record_governing_batch_propagated():
    result = _make_stability_result(
        model=ModelKind.COMMON_SLOPE,
        poolability_decision=Poolability.PARTIAL,
        governing_batch="B2",
    )
    rec = to_decision_record(result)
    assert rec["governing_batch"] == "B2"
    assert rec["model"] == ModelKind.COMMON_SLOPE.value
    assert rec["poolability"] == Poolability.PARTIAL.value


# ---------------------------------------------------------------------------
# End-to-end: HTML contains the values that landed in the JSON record
# ---------------------------------------------------------------------------


def test_html_and_record_agree_on_headline_values(tmp_path):
    result = _make_stability_result(
        supported_shelf_life_months=24,
        statistical_crossing_months=27.4,
        observed_data_months=18.0,
        direction=Direction.DECREASING,
    )
    rec = to_decision_record(result)
    out = tmp_path / "report_e2e.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")

    # The HTML must surface the headline numbers that landed in the record.
    assert f"{rec['supported_shelf_life_months']} months" in body
    assert "27.4" in body
    assert "18" in body
    assert rec["condition"] in body
    assert rec["limiting_attribute"] in body
    assert rec["confidence_bound"].replace("_", " ")[:6].lower() in body.lower()


# ---------------------------------------------------------------------------
# v0.4.0 ICH Q1A significant-change reporting tests (additive)
# ---------------------------------------------------------------------------


def test_record_v040_has_extrapolation_fields():
    """Single-attribute JSON record must expose the five v0.4.0 keys."""
    result = _make_stability_result()
    rec = to_decision_record(result)
    expected_keys = {
        "significant_change_accelerated",
        "significant_change_intermediate",
        "extrapolation_allowed",
        "extrapolation_rationale",
        "significant_change_details",
    }
    assert expected_keys.issubset(rec.keys()), (
        f"Missing keys: {expected_keys - rec.keys()}"
    )
    # extrapolation_rationale is always a string (possibly empty) so
    # downstream tooling can rely on the type.
    assert isinstance(rec["extrapolation_rationale"], str)
    # Defaults from the contracts dataclass are surfaced as-is.
    assert rec["extrapolation_allowed"] is True
    assert rec["extrapolation_rationale"] == ""
    assert rec["significant_change_details"] == {}
    assert rec["significant_change_accelerated"] is None
    assert rec["significant_change_intermediate"] is None
    # And the record is still JSON-serializable.
    json.dumps(rec)


def test_record_v040_round_trips_populated_gate():
    """A populated gate round-trips losslessly through JSON."""
    result = _make_stability_result()
    # Populate the v0.4.0 fields via object.__setattr__ to bypass the
    # dataclass's required-arg check (we're just attaching fields, not
    # rebuilding the object).
    object.__setattr__(result, "significant_change_accelerated", False)
    object.__setattr__(result, "significant_change_intermediate", True)
    object.__setattr__(result, "extrapolation_allowed", False)
    object.__setattr__(
        result, "extrapolation_rationale", "3-6mo accelerated change; intermediate data required but absent",
    )
    object.__setattr__(result, "significant_change_details", {
        "assay": {"first_t": 3.0, "evidence": "assay dropped past 95% LCL at 3.0 mo", "evaluated": True},
    })
    rec = to_decision_record(result)
    assert rec["significant_change_accelerated"] is False
    assert rec["significant_change_intermediate"] is True
    assert rec["extrapolation_allowed"] is False
    assert rec["extrapolation_rationale"].startswith("3-6mo")
    assert rec["significant_change_details"]["assay"]["first_t"] == pytest.approx(3.0)
    # JSON round-trip.
    text = json.dumps(rec)
    roundtrip = json.loads(text)
    assert roundtrip == rec


def test_html_v040_has_significant_change_section(tmp_path):
    """When the gate fires, the HTML report includes the Q1A section."""
    result = _make_stability_result()
    object.__setattr__(
        result, "extrapolation_rationale", "no accelerated sig change",
    )
    object.__setattr__(result, "extrapolation_allowed", True)
    object.__setattr__(result, "significant_change_accelerated", False)
    object.__setattr__(result, "significant_change_intermediate", None)
    object.__setattr__(result, "significant_change_details", {
        "assay": {"first_t": None, "evidence": "no change observed", "evaluated": True},
    })
    out = tmp_path / "report_v040.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert "Significant-change assessment (ICH Q1A)" in body
    # The rationale identifier must appear in the rendered table.
    assert "no accelerated sig change" in body
    # And at least one criterion row (assay was evaluated).
    assert "Criteria fired" in body
    assert "no change observed" in body


def test_html_v040_no_section_when_gate_silent(tmp_path):
    """When the gate was never exercised, the Q1A section must NOT appear."""
    # Default StabilityResult has rationale == "" and details == {}.
    result = _make_stability_result()
    # Defensive: ensure the defaults the dataclass supplies are in fact
    # the silent state the test expects.
    assert result.extrapolation_rationale == ""
    assert not result.significant_change_details
    out = tmp_path / "report_v040_silent.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert "Significant-change assessment (ICH Q1A)" not in body
    assert "Criteria fired" not in body


# ---------------------------------------------------------------------------
# v0.5.0 advanced-statistics reporting tests (additive)
# ---------------------------------------------------------------------------


def test_record_v050_has_advanced_stats_fields():
    """Single-attribute JSON record must expose the four v0.5.0 keys
    and default them to None / None / None / "fixed"."""
    result = _make_stability_result()
    rec = to_decision_record(result)
    expected_keys = {
        "arrhenius",
        "mkt_celsius",
        "reduced_design",
        "model_effects",
    }
    assert expected_keys.issubset(rec.keys()), (
        f"Missing keys: {expected_keys - rec.keys()}"
    )
    # Defaults from the contracts dataclass are surfaced as-is so a
    # v0.4.x result looks identical in the record.
    assert rec["arrhenius"] is None
    assert rec["mkt_celsius"] is None
    assert rec["reduced_design"] is None
    assert rec["model_effects"] == "fixed"
    # And the record is still JSON-serializable.
    json.dumps(rec)


def test_record_v050_carries_arrhenius_when_present():
    """A populated ArrheniusResult round-trips through the JSON record
    with the right scalar fields visible (rate_by_temp_C keys are
    stringified by ``_as_python``)."""
    from openpharmastability.contracts import ArrheniusResult

    result = _make_stability_result()
    arr = ArrheniusResult(
        Ea_J_per_mol=80_000.0,
        ln_A=20.0,
        A=math.exp(20.0),
        r_squared=0.99,
        predicted_k_at_storage=0.01,
        storage_temp_C=25.0,
        n_temps=3,
        rate_by_temp_C={"40.0": 0.1, "50.0": 0.3, "60.0": 0.9},
        notes=["three stress temps, all in linear range"],
    )
    object.__setattr__(result, "arrhenius_result", arr)
    rec = to_decision_record(result)
    # The four v0.5 keys are present, and Arrhenius is now a dict.
    assert rec["arrhenius"] is not None
    assert isinstance(rec["arrhenius"], dict)
    assert rec["arrhenius"]["Ea_J_per_mol"] == pytest.approx(80_000.0)
    assert rec["arrhenius"]["n_temps"] == 3
    assert rec["arrhenius"]["predicted_k_at_storage"] == pytest.approx(0.01)
    assert rec["arrhenius"]["storage_temp_C"] == pytest.approx(25.0)
    # rate_by_temp_C keys are stringified by _as_python; values survive.
    assert rec["arrhenius"]["rate_by_temp_C"]["40.0"] == pytest.approx(0.1)
    # JSON round-trip is lossless.
    text = json.dumps(rec)
    roundtrip = json.loads(text)
    assert roundtrip == rec


def test_html_v050_has_model_effects_section(tmp_path):
    """When ``model_effects='random'`` the HTML must include the
    'Model effects' header and the 'not the ICH Q1E default' marker."""
    result = _make_stability_result()
    object.__setattr__(result, "model_effects", "random")
    out = tmp_path / "report_v050_random.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert "Model effects" in body
    assert "not the ICH Q1E default" in body
    # The random marker is the only ICH-marker; default reporting does
    # not include it. Defensive: the fixed-effect default text is NOT
    # also present (template branches are exclusive).
    assert "Q1E default — fixed-effect batch" not in body


def test_html_v050_no_v5_sections_when_default(tmp_path):
    """A v0.4.x default result must NOT include the v0.5 sections
    (Arrhenius / MKT / Reduced design) — only the model-effects
    section is unconditional, and the Arrhenius / MKT / Reduced design
    blocks are gated on their ``*_present`` flags."""
    result = _make_stability_result()
    # Defensive: confirm the fixtures really are in the default state.
    assert getattr(result, "arrhenius_result", None) is None
    assert getattr(result, "mkt_celsius", None) is None
    assert getattr(result, "reduced_design_report", None) is None
    out = tmp_path / "report_v050_silent.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    # The unconditional 'Model effects' header IS present.
    assert "Model effects" in body
    # The three gated v0.5 section headers are NOT present.
    assert "Arrhenius analysis" not in body
    assert "Mean kinetic temperature" not in body
    assert "Reduced design (ICH Q1D)" not in body


# ---------------------------------------------------------------------------
# v0.5.1 mixed-model convergence / boundary reporting tests (additive)
# ---------------------------------------------------------------------------
#
# The fit-level ``design["convergence"]`` sub-block is lifted to a
# top-level ``StabilityResult.model_convergence`` field by the engine
# and surfaced through:
#   - the JSON record (``model_convergence`` key),
#   - the HTML report ("Model convergence" row, gated on
#     ``model_effects == "random"``).
# These tests pin the round-trip and the gating.


def test_record_v051_has_model_convergence():
    """The single-attribute JSON record must expose
    ``model_convergence`` as a dict with ``converged``, ``boundary``,
    ``message`` keys. Default state (no random-effects run) is the
    OLS sentinel."""
    result = _make_stability_result()
    rec = to_decision_record(result)
    assert "model_convergence" in rec, (
        "missing model_convergence key in JSON record"
    )
    conv = rec["model_convergence"]
    assert isinstance(conv, dict)
    assert set(conv.keys()) >= {"converged", "boundary", "message"}
    # Defaults from the contracts dataclass: OLS path, so the record
    # is identical to what the v0.5.0 path produced.
    assert conv["converged"] is True
    assert conv["boundary"] is False
    # And the record is still JSON-serializable.
    json.dumps(rec)


def test_record_v051_carries_random_convergence_when_present():
    """A populated ``model_convergence`` (e.g. from a random-effects
    run that hit a boundary) round-trips through JSON losslessly."""
    result = _make_stability_result()
    object.__setattr__(result, "model_effects", "random")
    object.__setattr__(
        result, "model_convergence",
        {
            "converged": False,
            "boundary": True,
            "message": "mixed model hit boundary (random-effect variance -> 0)",
        },
    )
    rec = to_decision_record(result)
    conv = rec["model_convergence"]
    assert conv["converged"] is False
    assert conv["boundary"] is True
    assert "boundary" in conv["message"]
    # JSON round-trip.
    text = json.dumps(rec)
    roundtrip = json.loads(text)
    assert roundtrip["model_convergence"] == conv


def test_html_v051_random_model_shows_convergence_row(tmp_path):
    """When ``model_effects='random'`` and the convergence sub-block
    has a non-trivial payload, the HTML report must include the
    'Model convergence' row. The row's text reflects the
    converged/boundary state of the convergence sub-block."""
    result = _make_stability_result()
    object.__setattr__(result, "model_effects", "random")
    object.__setattr__(
        result, "model_convergence",
        {
            "converged": False,
            "boundary": True,
            "message": "mixed model hit boundary (random-effect variance -> 0)",
        },
    )
    out = tmp_path / "report_v051_random.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert "Model convergence" in body
    # The non-converged marker and the boundary marker are both
    # surfaced.
    assert "NOT converged" in body
    assert "(boundary)" in body
    # The raw convergence message is surfaced in a <code> block.
    assert "random-effect variance -&gt; 0" in body or "random-effect variance -> 0" in body


def test_html_v051_fixed_model_omits_convergence_row(tmp_path):
    """A default (``model_effects='fixed'``) result must NOT include
    the 'Model convergence' row — that row is gated on
    ``model_effects == "random"`` so the OLS / Q1E default pipeline
    stays quiet about a check it never ran."""
    result = _make_stability_result()
    # Defensive: confirm the fixture really is the default state.
    assert getattr(result, "model_effects", "fixed") == "fixed"
    out = tmp_path / "report_v051_fixed.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    # The 'Model effects' header is unconditional and is present.
    assert "Model effects" in body
    # The 'Model convergence' row is NOT present.
    assert "Model convergence" not in body


# ---------------------------------------------------------------------------
# v0.7.0 sensitivity + acceptance-criteria reporting tests (additive)
# ---------------------------------------------------------------------------


def _build_sensitivity_report(rows=None, summary="", baseline=17, notes=None):
    """Build a minimal SensitivityReport for the reporting tests."""
    from openpharmastability.contracts import (
        SensitivityReport,
        SensitivityRow,
    )
    if rows is None:
        rows = [
            SensitivityRow(
                influential_row_index=13,
                baseline_supported_shelf_life=17,
                leave_one_out_supported_shelf_life=18,
                leave_one_out_statistical_crossing_months=18.3,
                diff_supported_shelf_life_months=1,
                note="",
            ),
            SensitivityRow(
                influential_row_index=24,
                baseline_supported_shelf_life=17,
                leave_one_out_supported_shelf_life=17,
                leave_one_out_statistical_crossing_months=17.5,
                diff_supported_shelf_life_months=0,
                note="",
            ),
        ]
    return SensitivityReport(
        rows=rows, summary=summary, baseline_supported_shelf_life=baseline,
        notes=list(notes or []),
    )


def test_record_v070_has_sensitivity_report() -> None:
    """Single-attribute JSON record must expose the v0.7.0
    ``sensitivity_report`` and ``acceptance_criteria`` keys. The
    defaults (no ``--sensitivity``) leave the sensitivity key
    as ``None`` and the acceptance key as a one-element list
    mirroring the single result."""
    result = _make_stability_result()
    rec = to_decision_record(result)
    assert "sensitivity_report" in rec
    # Default (no --sensitivity): None.
    assert rec["sensitivity_report"] is None
    # The acceptance-criteria list is always present and has
    # exactly 1 row (the single-attribute result).
    assert "acceptance_criteria" in rec
    assert isinstance(rec["acceptance_criteria"], list)
    assert len(rec["acceptance_criteria"]) == 1
    row = rec["acceptance_criteria"][0]
    for key in (
        "attribute", "condition", "model", "poolability",
        "supported_shelf_life_months",
        "statistical_crossing_months",
        "observed_data_months",
        "extrapolation_flag",
        "included_in_limiting_decision",
    ):
        assert key in row, f"missing {key!r} in acceptance row {row!r}"
    # The single-attribute row is always marked as included
    # (the limiting decision at the single-attribute level
    # has no other attribute to compete with).
    assert row["included_in_limiting_decision"] is True
    # And the row mirrors the result's headline numbers.
    assert row["attribute"] == "assay"
    assert row["condition"] == "25C/60RH"
    assert row["supported_shelf_life_months"] == 24
    # JSON-serializable.
    json.dumps(rec)


def test_record_v070_round_trips_populated_sensitivity() -> None:
    """A populated :class:`SensitivityReport` round-trips through
    the JSON record losslessly."""
    result = _make_stability_result()
    object.__setattr__(
        result, "sensitivity_report", _build_sensitivity_report(),
    )
    rec = to_decision_record(result)
    assert rec["sensitivity_report"] is not None
    assert "rows" in rec["sensitivity_report"]
    assert len(rec["sensitivity_report"]["rows"]) == 2
    # Each row carries the documented fields.
    for r in rec["sensitivity_report"]["rows"]:
        for key in (
            "influential_row_index",
            "baseline_supported_shelf_life",
            "leave_one_out_supported_shelf_life",
            "leave_one_out_statistical_crossing_months",
            "diff_supported_shelf_life_months",
            "note",
        ):
            assert key in r, f"missing {key!r} in sensitivity row {r!r}"
    # And the JSON round-trips losslessly.
    text = json.dumps(rec)
    roundtrip = json.loads(text)
    assert roundtrip == rec


def test_html_v070_sensitivity_section_appears_when_present(tmp_path):
    """When the result carries a populated ``sensitivity_report``,
    the HTML report includes the 'Sensitivity analysis' section
    header AND the summary text."""
    result = _make_stability_result()
    object.__setattr__(
        result, "sensitivity_report",
        _build_sensitivity_report(
            summary="max delta 1 mo; 1 point changes the shelf life",
        ),
    )
    out = tmp_path / "report_v070.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    # The section header is present (gated on sensitivity_present).
    assert "Sensitivity analysis over Cook" in body
    # And the summary text appears.
    assert "max delta 1 mo" in body
    # And the column header for the row table appears.
    assert "Influential row" in body
    assert "Baseline shelf (mo)" in body
    assert "Leave-one-out shelf (mo)" in body


def test_html_v070_no_sensitivity_section_by_default(tmp_path):
    """A default result (``sensitivity_report is None``) must NOT
    include the 'Sensitivity analysis' section header. The
    section is gated on the v0.7.0 ``sensitivity_present`` flag."""
    result = _make_stability_result()
    # Defensive: confirm the fixture really is the default state.
    assert getattr(result, "sensitivity_report", None) is None
    out = tmp_path / "report_v070_silent.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    # The gated section header is NOT present.
    assert "Sensitivity analysis (leave-one-out" not in body
    assert "Influential row" not in body


# ---------------------------------------------------------------------------
# §9.2  JSON record determinism
# ---------------------------------------------------------------------------


def test_json_record_deterministic_with_fixed_epoch():
    """to_decision_record() must produce byte-identical JSON on two calls.

    The timestamp is embedded in the metadata fixture (ISO_TIMESTAMP), so
    there is no wall-clock non-determinism.  Two consecutive calls on the
    same StabilityResult must return identical dicts whose JSON
    serialisation is byte-equal.
    """
    result = _make_stability_result()
    rec1 = to_decision_record(result)
    rec2 = to_decision_record(result)
    assert rec1 == rec2, "to_decision_record() is not deterministic"
    assert json.dumps(rec1, sort_keys=True) == json.dumps(rec2, sort_keys=True)


# ---------------------------------------------------------------------------
# §9.3  Disclaimer verbatim in HTML  (supplements existing render test)
# §9.4  Disclaimer verbatim in JSON record
# ---------------------------------------------------------------------------


def test_disclaimer_verbatim_in_json():
    """The decision record must carry the verbatim DISCLAIMER string.

    This is a machine-readable compliance requirement: consumers parsing
    the JSON programmatically must see the regulatory-scope disclaimer
    without having to render the HTML report.
    """
    from openpharmastability.contracts import DISCLAIMER
    result = _make_stability_result()
    rec = to_decision_record(result)
    assert "disclaimer" in rec, "key 'disclaimer' missing from decision record"
    assert rec["disclaimer"] == DISCLAIMER, (
        "Decision record disclaimer does not match contracts.DISCLAIMER verbatim"
    )
    # Must survive a JSON round-trip without mutation.
    assert json.loads(json.dumps(rec))["disclaimer"] == DISCLAIMER


def test_disclaimer_verbatim_in_html(tmp_path):
    """The rendered HTML must contain contracts.DISCLAIMER verbatim.

    This test is the §9.3 companion to test_render_html_contains_disclaimer;
    it additionally verifies the *exact* string (not just a substring) to
    prevent truncation.
    """
    from openpharmastability.contracts import DISCLAIMER
    result = _make_stability_result()
    out = tmp_path / "report_disclaimer.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert DISCLAIMER in body, (
        "HTML report does not contain contracts.DISCLAIMER verbatim"
    )


# ---------------------------------------------------------------------------
# v0.11.0 — guidance_profile surfacing in JSON + HTML
# ---------------------------------------------------------------------------


def test_record_carries_guidance_profile():
    result = _make_stability_result()
    rec = to_decision_record(result)
    assert rec["guidance_profile"] == "Q1A_R2+Q1E"
    assert rec["guidance_status"] == "effective"
    assert rec["guidance_reference"] == "ICH Q1A(R2) Step 4 + ICH Q1E Step 4"
    # A custom profile_name flows through the record builder.
    result.profile_name = "custom_profile"
    assert to_decision_record(result)["guidance_profile"] == "custom_profile"


def test_render_html_contains_guidance_profile(tmp_path):
    result = _make_stability_result()
    out = tmp_path / "report.html"
    render_html(result, plot_png_path=None, out_path=str(out))
    body = out.read_text(encoding="utf-8")
    assert "Q1A_R2+Q1E" in body
    assert "effective" in body
    assert "ICH Q1A(R2) Step 4 + ICH Q1E Step 4" in body
    # A custom profile_name flows through to the rendered HTML.
    result.profile_name = "custom_profile"
    render_html(result, plot_png_path=None, out_path=str(out))
    assert "custom_profile" in out.read_text(encoding="utf-8")
