"""JSON decision record for OpenPharmaStability v0.1.

Turns a :class:`StabilityResult` into a JSON-serializable ``dict`` that
captures the key decisions (shelf life, model, poolability, bound, warnings)
and the reproducibility metadata required by the spec
(``OpenPharmaStability.md`` §"Decision Engine Outputs").

This module is *read* by ``reports/html.py`` (the HTML report embeds the
record's fields) and by downstream tooling that wants a machine-readable
audit trail.

Only depends on :mod:`openpharmastability.contracts`.
"""
from __future__ import annotations

import dataclasses
from dataclasses import asdict, is_dataclass
from typing import Any, Union

from openpharmastability import __version__ as _PKG_VERSION
from openpharmastability.contracts import (
    CONFIDENCE,
    DISCLAIMER,
    POOLABILITY_ALPHA,
    TOOL_VERSION,
    AcceptanceCriteriaRow,
    Direction,
    MultiAttributeResult,
    StabilityResult,
)


# ---------------------------------------------------------------------------
# Small label helpers
# ---------------------------------------------------------------------------


def _confidence_bound_label(direction: Direction) -> str:
    """Return a stable, machine-friendly confidence-bound identifier.

    Mirrors the spec example: ``lower_one_sided_95_mean``,
    ``upper_one_sided_95_mean``, ``two_sided_95_mean``.
    """
    if direction == Direction.DECREASING:
        return "lower_one_sided_95_mean"
    if direction == Direction.INCREASING:
        return "upper_one_sided_95_mean"
    # Bidirectional / unknown: stricter, two-sided.
    return "two_sided_95_mean"


def _extrapolation_status(flag: bool) -> str:
    """Map the boolean extrapolation flag to a stable string for the record.

    Matches the spec example: ``"flag_required"`` vs ``"none"``.
    """
    return "flag_required" if bool(flag) else "none"


def _as_python(value: Any) -> Any:
    """Coerce numpy / pandas scalars to native Python so json.dumps is happy."""
    # Avoid importing numpy/pandas here unless needed: isinstance checks are
    # cheap and the import-free path is more robust for tooling.
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _as_python(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_as_python(v) for v in value]
    # Dataclasses (e.g. ``ArrheniusResult``, ``ReducedDesignReport``,
    # ``BQLSummary``) need to be flattened into JSON-serializable
    # dicts rather than stringified via their repr. ``asdict``
    # recurses into nested dataclasses too, so the helper stays
    # simple. Additive v0.5.0 change: previously these values fell
    # through to ``str(value)`` and were emitted as their repr
    # string in the record, which is opaque to downstream tooling.
    if is_dataclass(value):
        return {str(k): _as_python(v) for k, v in asdict(value).items()}
    # numpy / pandas scalar fallback
    try:
        item = value.item()  # numpy scalar -> python scalar
        if isinstance(item, (int, float, str, bool)):
            return item
    except (AttributeError, ValueError, TypeError):
        pass
    # Last resort: stringify so the record is still JSON-serializable.
    return str(value)


def _sensitivity_mode(result: StabilityResult) -> str:
    """Return the v0.8.0 sensitivity mode (``"row"`` / ``"batch"``).

    Reads the mode from ``result.sensitivity_report.mode``; falls
    back to ``"row"`` when the report is ``None`` (the v0.7.0
    default) or when the field is missing for any reason
    (forward-compat against hand-built fixtures).
    """
    sr = getattr(result, "sensitivity_report", None)
    if sr is None:
        return "row"
    if isinstance(sr, dict):
        return str(sr.get("mode", "row") or "row")
    return str(getattr(sr, "mode", "row") or "row")


def _arrhenius_field(result: StabilityResult, field_name: str) -> Any:
    """Return ``field_name`` from the result's ``arrhenius_result``.

    Returns the empty default (``{}`` for the per-batch dict,
    ``[]`` for the outlier list) when the result has no Arrhenius
    payload or when the payload is a dict that predates the v0.9.0
    field. ``getattr`` handles both shapes: a dataclass (live
    engine output) and a dict (hand-built fixtures, or output that
    has already been flattened by ``_as_python``).
    """
    arr = getattr(result, "arrhenius_result", None)
    if arr is None:
        # Pick the right empty default by field name.
        return [] if field_name == "outlier_batches" else {}
    if isinstance(arr, dict):
        # Hand-built fixture / pre-flattened payload.
        if field_name in arr:
            return arr[field_name]
        return [] if field_name == "outlier_batches" else {}
    return getattr(
        arr, field_name,
        [] if field_name == "outlier_batches" else {},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def to_acceptance_criteria(
    result: Union[StabilityResult, MultiAttributeResult],
) -> list[AcceptanceCriteriaRow]:
    """Build the list of :class:`AcceptanceCriteriaRow` from an analysis result.

    Single result -> 1 row. Multi result -> 1 row per analyzed
    attribute, carrying the :class:`AttributeMetadata`'s unit and
    spec overrides. The CSV emitted by the
    ``--acceptance-csv PATH`` CLI flag is built by
    :func:`csv.DictWriter`-ing this list directly; the field order
    is the dataclass's field order.
    """
    if isinstance(result, StabilityResult):
        return [_stability_result_to_acceptance_row(result)]
    if isinstance(result, MultiAttributeResult):
        rows: list[AcceptanceCriteriaRow] = []
        for ar in result.attributes:
            rows.append(_attribute_result_to_acceptance_row(ar))
        return rows
    raise TypeError(
        f"to_acceptance_criteria: unsupported result type {type(result).__name__!r}; "
        "expected StabilityResult or MultiAttributeResult"
    )


def _stability_result_to_acceptance_row(
    result: StabilityResult,
) -> AcceptanceCriteriaRow:
    """One :class:`AcceptanceCriteriaRow` for a single StabilityResult."""
    # The v0.7.0 lower_spec / upper_spec fields on the result are the
    # authoritative spec context (data-derived or metadata-overridden
    # depending on how the result was built). They default to None
    # so the row stays well-formed when the result has no spec context.
    lower_spec = getattr(result, "lower_spec", None)
    upper_spec = getattr(result, "upper_spec", None)
    return AcceptanceCriteriaRow(
        attribute=result.attribute,
        condition=result.condition,
        direction=result.direction.value,
        model=result.model.value,
        poolability=result.poolability.decision.value,
        lower_spec=lower_spec,
        upper_spec=upper_spec,
        statistical_crossing_months=result.statistical_crossing_months,
        supported_shelf_life_months=result.supported_shelf_life_months,
        observed_data_months=float(result.observed_data_months),
        extrapolation_flag=bool(result.extrapolation_flag),
        included_in_limiting_decision=True,
        exclusion_reason="",
        unit=None,
        governing_batch=result.crossing.governing_batch,
    )


def _attribute_result_to_acceptance_row(
    ar,
) -> AcceptanceCriteriaRow:
    """One :class:`AcceptanceCriteriaRow` for a multi-attribute entry."""
    r = ar.result
    return AcceptanceCriteriaRow(
        attribute=ar.metadata.attribute,
        condition=r.condition,
        direction=r.direction.value,
        model=r.model.value,
        poolability=r.poolability.decision.value,
        lower_spec=ar.metadata.lower_spec,
        upper_spec=ar.metadata.upper_spec,
        statistical_crossing_months=r.statistical_crossing_months,
        supported_shelf_life_months=r.supported_shelf_life_months,
        observed_data_months=float(r.observed_data_months),
        extrapolation_flag=bool(r.extrapolation_flag),
        included_in_limiting_decision=bool(ar.included_in_limiting_decision),
        exclusion_reason=str(ar.exclusion_reason or ""),
        unit=ar.metadata.unit,
        governing_batch=r.crossing.governing_batch,
    )


def to_decision_record(result: StabilityResult) -> dict[str, Any]:
    """Build the machine-readable decision record for a stability result.

    The returned dict is JSON-serializable (``json.dumps`` round-trips it
    losslessly). Required keys per the spec:

    - ``supported_shelf_life_months`` (int or None)
    - ``statistical_crossing_months`` (float or None)
    - ``limiting_attribute``
    - ``condition``
    - ``model``
    - ``poolability``  (decision string: "full" / "partial" / "none")
    - ``poolability_alpha``
    - ``confidence_bound``
    - ``observed_long_term_months``
    - ``extrapolation`` (string: "none" / "flag_required")
    - ``warnings``
    - ``deliverable_term``
    - ``product_type``
    - ``metadata`` (flattened; includes ``library_versions``, ``file_sha256``,
      ``tool_version``, ``timestamp``)
    """
    pool = result.poolability
    md = dict(result.metadata or {})  # shallow copy

    # Flatten / guarantee the reproducibility keys the spec requires.
    metadata: dict[str, Any] = {
        "file_sha256": md.get("file_sha256"),
        "row_count": md.get("row_count"),
        "column_count": md.get("column_count"),
        "random_seed": md.get("random_seed"),
        "library_versions": _as_python(md.get("library_versions", {})),
        "tool_version": md.get("tool_version") or TOOL_VERSION or _PKG_VERSION,
        "timestamp": md.get("timestamp"),
        # Preserve any extra metadata fields the engine / caller added.
        **{k: v for k, v in md.items() if k not in {
            "file_sha256", "row_count", "column_count", "random_seed",
            "library_versions", "tool_version", "timestamp",
        }},
    }

    # Diagnostics summary (booleans + counts) so the record is self-describing
    # without leaking numpy arrays / cov matrices.
    diag = result.diagnostics
    diagnostics_summary: dict[str, Any] = {
        "linearity_ok": bool(diag.linearity_ok),
        "homoscedastic_ok": bool(diag.homoscedastic_ok),
        "normal_resid_ok": bool(diag.normal_resid_ok),
        "n_influential_points": len(diag.influential_points or []),
        "notes": list(diag.notes or []),
    }

    record: dict[str, Any] = {
        # Core decision
        "supported_shelf_life_months": (
            int(result.supported_shelf_life_months)
            if result.supported_shelf_life_months is not None
            else None
        ),
        "statistical_crossing_months": (
            float(result.statistical_crossing_months)
            if result.statistical_crossing_months is not None
            else None
        ),
        "limiting_attribute": result.attribute,
        "condition": result.condition,
        "direction": result.direction.value,
        "model": result.model.value,
        "poolability": pool.decision.value,
        "poolability_alpha": float(pool.alpha),
        "p_value_slopes": float(pool.p_slopes) if pool.p_slopes is not None else None,
        "p_value_intercepts": (
            float(pool.p_intercepts) if pool.p_intercepts is not None else None
        ),
        # v0.9.0: Holm-Bonferroni corrected p-values for the two-step
        # poolability test. ``getattr(..., None)`` keeps the record
        # builder forward-compatible with hand-built PoolabilityResult
        # fixtures that predate the v0.9.0 fields (e.g. v0.8.x
        # callers).
        "p_value_slopes_holm": _as_python(
            getattr(pool, "p_slopes_holm", None)
        ),
        "p_value_intercepts_holm": _as_python(
            getattr(pool, "p_intercepts_holm", None)
        ),
        "confidence_bound": _confidence_bound_label(result.direction),
        "confidence_level": float(CONFIDENCE),
        "poolability_alpha_reference": float(POOLABILITY_ALPHA),
        # v0.11.0: the active guidance profile's name — an immutable
        # audit fact for the run. ``getattr`` keeps the record builder
        # forward-compatible with hand-built fixtures that predate the
        # ``profile_name`` field.
        "guidance_profile": getattr(result, "profile_name", "Q1A_R2+Q1E"),
        "guidance_status": getattr(result, "guidance_status", "effective"),
        "guidance_reference": getattr(
            result,
            "guidance_reference",
            "ICH Q1A(R2) Step 4 + ICH Q1E Step 4",
        ),
        "observed_long_term_months": float(result.observed_data_months),
        "extrapolation": _extrapolation_status(result.extrapolation_flag),
        "warnings": [str(w) for w in (result.warnings or [])],
        # v0.4.0: ICH Q1A significant-change gating of extrapolation.
        # These five keys surface the gate's per-attribute verdict on the
        # single-attribute JSON record. The rationale is a short
        # identifier (e.g. "no accelerated sig change", "3-6mo
        # accelerated change; intermediate OK"); the details dict
        # carries per-criterion evidence for downstream tooling.
        "significant_change_accelerated": _as_python(
            getattr(result, "significant_change_accelerated", None)
        ),
        "significant_change_intermediate": _as_python(
            getattr(result, "significant_change_intermediate", None)
        ),
        "extrapolation_allowed": bool(
            getattr(result, "extrapolation_allowed", True)
        ),
        "extrapolation_rationale": str(
            getattr(result, "extrapolation_rationale", "") or ""
        ),
        "significant_change_details": _as_python(
            getattr(result, "significant_change_details", {}) or {}
        ),
        "deliverable_term": result.deliverable_term,
        "product_type": result.product_type,
        "crossing_status": result.crossing.status.value,
        "governing_batch": result.crossing.governing_batch,
        # v0.10.0: which spec limit governed a bidirectional
        # (two-sided) crossing. "lower" / "upper" for a
        # BIDIRECTIONAL analysis; None for the one-sided paths.
        # ``getattr`` keeps the record forward-compatible with
        # hand-built CrossingResult fixtures predating the field.
        "governing_side": getattr(result.crossing, "governing_side", None),
        "diagnostics": diagnostics_summary,
        "metadata": _as_python(metadata),
        # v0.3.0 BQL + transforms: the per-attribute BQL summary and
        # (when --assess-transforms is enabled) the transform
        # candidate evidence. Both default to None when not set.
        "bql_summary": _as_python(getattr(result, "bql_summary", None)),
        "transform_assessment": _as_python(
            getattr(result, "transform_assessment", None)
        ),
        # Mandatory regulatory-style disclaimer (verbatim from
        # contracts.DISCLAIMER). The HTML report and the multi-attribute
        # record already carry it; the single-attribute record did not,
        # and the spec requires it on every record.
        "disclaimer": DISCLAIMER,
        # v0.5.0: advanced statistics opt-ins. All four default to
        # None / None / None / "fixed" so a v0.4.x result that never
        # ran the new modules looks identical in the record (no
        # populated payload surfaces). ``getattr(..., default)`` keeps
        # the record builder forward-compatible with hand-built
        # StabilityResult fixtures that predate the new attributes.
        "arrhenius": _as_python(getattr(result, "arrhenius_result", None)),
        "mkt_celsius": _as_python(getattr(result, "mkt_celsius", None)),
        "reduced_design": _as_python(getattr(result, "reduced_design_report", None)),
        "model_effects": str(getattr(result, "model_effects", "fixed") or "fixed"),
        # v0.5.1: mixed-model convergence / boundary status, lifted
        # from the fit-level ``design["convergence"]`` sub-block to a
        # top-level field on the StabilityResult. Always a dict with
        # keys ``converged`` (bool), ``boundary`` (bool), ``message``
        # (str). The OLS path defaults to ``{"converged": True,
        # "boundary": False, "message": "OLS"}``; the random-effects
        # path surfaces whatever the regression layer computed.
        # ``getattr(..., default)`` keeps the record forward-compatible
        # with hand-built fixtures that predate the v0.5.1 field.
        "model_convergence": _as_python(
            getattr(
                result, "model_convergence",
                {"converged": True, "boundary": False, "message": ""},
            )
        ),
        # v0.7.0: leave-one-out sensitivity report. ``None`` when
        # ``--sensitivity`` is not requested; a populated
        # ``SensitivityReport`` (with one row per Cook's-distance
        # influential point) when it is. ``getattr(..., default)``
        # keeps the record forward-compatible with hand-built
        # fixtures that predate the v0.7.0 field.
        "sensitivity_report": _as_python(
            getattr(result, "sensitivity_report", None)
        ),
        # v0.8.0: top-level convenience key carrying the
        # sensitivity drop mode (``"row"`` / ``"batch"``). The
        # same value is also embedded under
        # ``sensitivity_report.mode`` (because the
        # ``SensitivityReport`` dataclass carries it), but
        # surfacing it at the top level means downstream tooling
        # can branch on the mode without descending into the
        # nested report. Defaults to ``"row"`` when no report is
        # attached.
        "sensitivity_mode": _sensitivity_mode(result),
        # v0.8.0: Arrhenius-driven shelf-life prediction. ``None``
        # when ``--arrhenius-shelf-life`` is not requested; a
        # populated ``ArrheniusShelfLife`` (carrying the predicted
        # rate, statistical crossing, and rounded supported shelf
        # life) when it is. ``getattr(..., default)`` keeps the
        # record forward-compatible with hand-built fixtures that
        # predate the v0.8.0 field. Exploratory only; the official
        # Q1E shelf-life decision above is unchanged.
        "arrhenius_shelf_life": _as_python(
            getattr(result, "arrhenius_shelf_life", None)
        ),
        # v0.9.0: per-batch Arrhenius rate diagnostic. Two
        # additive top-level keys on the JSON record so downstream
        # tooling can read them without descending into the nested
        # ``arrhenius`` block. ``arrhenius_per_batch`` is a
        # ``{batch: {temp_C_str: k}}`` mapping;
        # ``arrhenius_outlier_batches`` is a list of batch
        # identifiers whose robust z-score exceeded the engine's
        # threshold (default 2.5) at one or more temperatures.
        # Both default to the empty container ({} / []) when
        # ``--arrhenius-per-batch`` was not set or when the
        # underlying ``ArrheniusResult`` predates the v0.9.0
        # fields. The helper ``_arrhenius_field`` handles both
        # dataclass and dict shapes for forward compatibility.
        "arrhenius_per_batch": _as_python(
            _arrhenius_field(result, "per_batch_rate_by_temp")
        ),
        "arrhenius_outlier_batches": _as_python(
            _arrhenius_field(result, "outlier_batches")
        ),
        # v0.7.0: one-row acceptance-criteria summary for the
        # single-attribute path. ``to_acceptance_criteria`` is the
        # shared helper the ``--acceptance-csv PATH`` CLI flag also
        # calls; the same dataclass (``AcceptanceCriteriaRow``) is
        # used here, in the multi-attribute record, and in the CSV.
        "acceptance_criteria": _as_python(
            [
                asdict(row)
                for row in to_acceptance_criteria(result)
            ]
        ),
    }

    return record
