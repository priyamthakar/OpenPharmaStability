"""HTML report rendering for OpenPharmaStability v0.1.

Renders a :class:`StabilityResult` to a self-contained HTML file using
Jinja2 with autoescape. The report is the primary user-facing artifact: it
embeds the dataset summary, model choice, poolability p-values, the
shelf-life estimate, the confidence-bound plot (referenced by relative
path), warnings, reproducibility metadata, and the mandatory disclaimer
from the spec (``OpenPharmaStability.md`` §"Regulatory Report Mode").

This module only depends on :mod:`openpharmastability.contracts` and
:mod:`jinja2` (declared in ``pyproject.toml``).

The template lives next to this file at ``templates/report.html.j2``.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import jinja2

from openpharmastability import __version__ as _PKG_VERSION
from openpharmastability.contracts import (
    CONFIDENCE,
    DISCLAIMER,
    POOLABILITY_ALPHA,
    TOOL_VERSION,
    CrossingStatus,
    Direction,
    ModelKind,
    Poolability,
    StabilityResult,
)


# ---------------------------------------------------------------------------
# Helpers — pure functions, also used by the tests' golden fixtures.
# ---------------------------------------------------------------------------


def _model_formula(kind: ModelKind) -> str:
    """Human-readable model formula for the selected model kind."""
    if kind == ModelKind.POOLED:
        return "value ~ time  (pooled across batches)"
    if kind == ModelKind.COMMON_SLOPE:
        return "value ~ time + batch  (common slope, batch-specific intercepts)"
    if kind == ModelKind.SEPARATE:
        return "value ~ time * batch  (batch-specific slopes and intercepts)"
    return str(kind)


def _model_kind_human(kind: ModelKind) -> str:
    """Pretty label for the model kind used in summaries."""
    if kind == ModelKind.POOLED:
        return "Pooled regression"
    if kind == ModelKind.COMMON_SLOPE:
        return "Common slope, batch-specific intercepts"
    if kind == ModelKind.SEPARATE:
        return "Batch-specific regression"
    return str(kind)


def _poolability_human(decision: Poolability) -> str:
    """Pretty label for the poolability decision."""
    if decision == Poolability.FULL:
        return "Full pooling"
    if decision == Poolability.PARTIAL:
        return "Partial pooling (common slope, batch-specific intercepts)"
    if decision == Poolability.NONE:
        return "No pooling (batch-specific regression)"
    return str(decision)


def _confidence_bound_label(direction: Direction) -> tuple[str, str]:
    """Return (machine_id, human_label) for the chosen bound."""
    if direction == Direction.DECREASING:
        return "lower_one_sided_95_mean", (
            "Lower one-sided 95% confidence bound on the mean response"
        )
    if direction == Direction.INCREASING:
        return "upper_one_sided_95_mean", (
            "Upper one-sided 95% confidence bound on the mean response"
        )
    return "two_sided_95_mean", (
        "Two-sided 95% confidence band on the mean response "
        "(direction unknown / bidirectional)"
    )


def _crossing_status_human(status: CrossingStatus) -> str:
    if status == CrossingStatus.CROSSED:
        return "Crossed specification within the evaluated horizon"
    if status == CrossingStatus.NO_CROSSING:
        return "No crossing within the evaluated horizon"
    if status == CrossingStatus.FAIL_AT_BASELINE:
        return "Bound is past specification at t=0 (fails at baseline)"
    if status == CrossingStatus.FLAT_OR_OPPOSITE:
        return "Slope is near zero or opposite the declared direction"
    return str(status)


def _format_p(p: Optional[float]) -> str:
    """Render a p-value for the report; never raise on None."""
    if p is None:
        return "—"
    try:
        return f"{float(p):.4g}"
    except (TypeError, ValueError):
        return str(p)


def _format_months(value: Optional[float], digits: int = 1) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _format_int(value: Optional[int]) -> str:
    if value is None:
        return "—"
    return f"{int(value)}"


def _format_sc_criterion_notes(details: Optional[dict]) -> list[dict]:
    """Convert the raw ``significant_change_details`` dict into a list of
    human-friendly rows for the HTML table.

    One row per criterion that was evaluated. Criteria with
    ``evaluated: False`` are skipped. The returned list is JSON-safe
    (only str / float / None values) so the template can format it
    with ``{{ "%.2f"|format(row.first_t) }}`` without raising on
    non-numeric inputs.
    """
    if not details:
        return []
    rows: list[dict] = []
    for name, info in details.items():
        if not isinstance(info, dict):
            continue
        if not info.get("evaluated", True):
            continue
        rows.append({
            "criterion": str(name),
            "first_t": info.get("first_t"),
            "evidence": str(info.get("evidence", "")),
        })
    return rows


def _required_columns_status(result: StabilityResult) -> tuple[str, str]:
    """Resolve the required-column validation status for the report.

    The engine is expected to set ``metadata["required_columns_valid"]``
    (True / False) and/or emit a warning containing ``"required column"``.
    This helper makes a best-effort decision without raising.
    """
    md = result.metadata or {}
    if "required_columns_valid" in md:
        ok = bool(md["required_columns_valid"])
        return (
            "All required columns present" if ok else "Required columns missing",
            "ok" if ok else "fail",
        )
    for w in result.warnings or []:
        if "required column" in w.lower():
            return "Required columns missing", "fail"
    return "All required columns present (assumed)", "ok"


def _library_versions(result: StabilityResult) -> dict[str, str]:
    md = result.metadata or {}
    versions = md.get("library_versions") or {}
    if isinstance(versions, dict):
        return {str(k): str(v) for k, v in versions.items()}
    return {}


def _resolve_plot_src(plot_png_path: Optional[str]) -> Optional[str]:
    """Return the relative src for the plot ``<img>``, or None to skip it."""
    if not plot_png_path:
        return None
    # Just use the basename; the user controls where the HTML lives relative
    # to the plot file (e.g. the CLI writes both into build/).
    return os.path.basename(plot_png_path)


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def _build_context(result: StabilityResult, plot_png_path: Optional[str]) -> dict[str, Any]:
    pool = result.poolability
    diag = result.diagnostics
    md = result.metadata or {}

    bound_id, bound_label = _confidence_bound_label(result.direction)
    val_status, val_css = _required_columns_status(result)

    # Shelf-life summary table content.
    if result.supported_shelf_life_months is None:
        supported_text = "Not established (no crossing in evaluated horizon)"
    else:
        supported_text = f"{int(result.supported_shelf_life_months)} months"

    if result.extrapolation_flag:
        extrap_text = "Yes — supported period extends beyond observed data; flagged"
    else:
        extrap_text = "No — supported period is within observed data"

    governing = result.crossing.governing_batch or "—"

    # P-values: slopes always present, intercepts only if reached step 2.
    p_slopes_str = _format_p(pool.p_slopes)
    p_intercepts_str = _format_p(pool.p_intercepts)

    # Required-column / condition / batch / time summary. The engine may
    # surface these via metadata; otherwise we render what's available.
    n_batches = md.get("n_batches")
    time_points = md.get("time_points")
    row_count = md.get("row_count")

    return {
        # Headings / identity
        "title": "Stability Analysis Report",
        "attribute": result.attribute,
        "condition": result.condition,
        "direction": result.direction.value,
        "deliverable_term": result.deliverable_term,
        "product_type": result.product_type,
        # Dataset summary
        "n_batches": n_batches,
        "time_points": time_points,
        "row_count": row_count,
        "validation_status": val_status,
        "validation_status_css": val_css,
        # Model
        "model_kind_value": result.model.value,
        "model_kind_human": _model_kind_human(result.model),
        "model_formula": _model_formula(result.model),
        # Poolability
        "poolability_decision": pool.decision.value,
        "poolability_human": _poolability_human(pool.decision),
        "p_value_slopes": p_slopes_str,
        "p_value_intercepts": p_intercepts_str,
        "poolability_alpha": float(pool.alpha),
        "poolability_alpha_ref": float(POOLABILITY_ALPHA),
        "poolability_notes": list(pool.notes or []),
        # Fit summary
        "fit_params": result.fit.params,
        "fit_df_resid": result.fit.df_resid,
        "fit_s_resid": result.fit.s_resid,
        "fit_batches": list(result.fit.batches or []),
        # Crossing / shelf life
        "crossing_status_value": result.crossing.status.value,
        "crossing_status_human": _crossing_status_human(result.crossing.status),
        "statistical_crossing_months": _format_months(
            result.statistical_crossing_months
        ),
        "supported_shelf_life_text": supported_text,
        "supported_shelf_life_months_raw": result.supported_shelf_life_months,
        "observed_data_months": _format_months(result.observed_data_months, digits=1),
        "observed_data_months_raw": result.observed_data_months,
        "extrapolation_text": extrap_text,
        "extrapolation_flag": bool(result.extrapolation_flag),
        "governing_batch": governing,
        # Diagnostics
        "linearity_ok": bool(diag.linearity_ok),
        "homoscedastic_ok": bool(diag.homoscedastic_ok),
        "normal_resid_ok": bool(diag.normal_resid_ok),
        "n_influential_points": len(diag.influential_points or []),
        "diagnostics_notes": list(diag.notes or []),
        # Confidence bound
        "confidence_bound_id": bound_id,
        "confidence_bound_label": bound_label,
        "confidence_level": float(CONFIDENCE),
        # Plot
        "plot_src": _resolve_plot_src(plot_png_path),
        # Warnings
        "warnings": [str(w) for w in (result.warnings or [])],
        # v0.4.0: ICH Q1A significant-change gating of extrapolation.
        "significant_change_accelerated": getattr(
            result, "significant_change_accelerated", None
        ),
        "significant_change_intermediate": getattr(
            result, "significant_change_intermediate", None
        ),
        "extrapolation_allowed": bool(
            getattr(result, "extrapolation_allowed", True)
        ),
        "extrapolation_rationale": str(
            getattr(result, "extrapolation_rationale", "") or ""
        ),
        "significant_change_details": dict(
            getattr(result, "significant_change_details", {}) or {}
        ),
        "extrapolation_criterion_notes": _format_sc_criterion_notes(
            getattr(result, "significant_change_details", {}) or {}
        ),
        # v0.5.0: advanced-statistics opt-ins. Pass through the raw
        # values (or None) and pre-compute the booleans the template
        # gates on, so the template can stay declarative. ``getattr``
        # keeps the context builder forward-compatible with hand-built
        # StabilityResult fixtures that predate the v0.5 fields.
        "arrhenius_result": getattr(result, "arrhenius_result", None),
        "mkt_celsius": getattr(result, "mkt_celsius", None),
        "reduced_design_report": getattr(result, "reduced_design_report", None),
        "model_effects": str(getattr(result, "model_effects", "fixed") or "fixed"),
        "arrhenius_present": getattr(result, "arrhenius_result", None) is not None,
        "mkt_present": getattr(result, "mkt_celsius", None) is not None,
        "reduced_design_present": getattr(result, "reduced_design_report", None) is not None,
        "model_effects_is_random": str(
            getattr(result, "model_effects", "fixed") or "fixed"
        ) == "random",
        # v0.5.1: mixed-model convergence / boundary context. The
        # raw dict plus the three pre-computed scalars the template
        # gates on / displays. The ``getattr(..., default)`` keeps
        # the context builder forward-compatible with hand-built
        # StabilityResult fixtures that predate the v0.5.1 field.
        "model_convergence": getattr(
            result, "model_convergence",
            {"converged": True, "boundary": False, "message": ""},
        ),
        "model_convergence_converged": bool(
            (getattr(result, "model_convergence", {}) or {}).get(
                "converged", True
            )
        ),
        "model_convergence_boundary": bool(
            (getattr(result, "model_convergence", {}) or {}).get(
                "boundary", False
            )
        ),
        "model_convergence_message": str(
            (getattr(result, "model_convergence", {}) or {}).get(
                "message", ""
            )
        ),
        # v0.7.0: optional sensitivity report (leave-one-out over
        # Cook's-distance outliers). ``None`` when ``--sensitivity``
        # is not requested; a populated ``SensitivityReport``
        # otherwise. The template branches on ``sensitivity_present``
        # (a pre-computed bool) so the Jinja template stays
        # declarative. ``getattr(..., default)`` keeps the context
        # builder forward-compatible with hand-built StabilityResult
        # fixtures that predate the v0.7.0 field.
        "sensitivity_report": getattr(
            result, "sensitivity_report", None
        ),
        "sensitivity_present": getattr(
            result, "sensitivity_report", None
        ) is not None,
        # Reproducibility
        "tool_version": md.get("tool_version") or TOOL_VERSION or _PKG_VERSION,
        "timestamp": md.get("timestamp"),
        "file_sha256": md.get("file_sha256"),
        "random_seed": md.get("random_seed"),
        "library_versions": _library_versions(result),
        # Disclaimer (verbatim from contracts.DISCLAIMER)
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _template_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def _make_env() -> jinja2.Environment:
    # `autoescape=True` covers all template types — we only ever render HTML
    # here, and using the boolean form sidesteps the `select_autoescape`
    # extension-matching pitfall (e.g. `report.html.j2` does not *end* in
    # ".html", so file-extension-based autoescape would silently miss it).
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(_template_dir()),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def render_html(
    result: StabilityResult,
    plot_png_path: Optional[str],
    out_path: str,
) -> None:
    """Render ``result`` to an HTML report at ``out_path``.

    Parameters
    ----------
    result
        The full :class:`StabilityResult` produced by the engine.
    plot_png_path
        Path to a confidence-bound PNG to embed in the report. The path is
        used as the ``src`` of the plot ``<img>`` (typically the basename
        so the HTML works when the report is opened alongside the plot
        in the same directory). If ``None`` or empty, the plot section is
        omitted.
    out_path
        Filesystem path where the rendered HTML is written. Parent
        directories are created if needed.
    """
    env = _make_env()
    template = env.get_template("report.html.j2")
    context = _build_context(result, plot_png_path)
    html = template.render(**context)

    parent = os.path.dirname(os.path.abspath(out_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
