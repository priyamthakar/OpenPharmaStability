"""Multi-attribute JSON decision record (v0.2.0).

Mirrors :mod:`openpharmastability.reports.record` but for a
:class:`MultiAttributeResult` instead of a single
:class:`StabilityResult`. The top-level keys follow the v0.2
schema described in NEXT_STEPS.md §7.

Backwards compatible: the v0.1 ``analyze()`` path still calls
:func:`openpharmastability.reports.record.to_decision_record`.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from openpharmastability.contracts import MultiAttributeResult
from openpharmastability.reports.record import (
    to_acceptance_criteria,
    to_decision_record as _single_record,
)


def to_multi_decision_record(result: MultiAttributeResult) -> dict[str, Any]:
    """Convert a :class:`MultiAttributeResult` to a JSON-serializable dict.

    Top-level keys
    --------------
    - condition
    - product_type
    - deliverable_term
    - supported_shelf_life_months (overall; None if no eligible attr)
    - statistical_crossing_months (overall; None if no eligible attr)
    - limiting_attribute
    - observed_data_months
    - attributes: list of per-attribute dicts (each is the
      v0.1 single-attribute record with a few extras)
    - warnings (deduped top-level)
    - metadata
    - disclaimer (the verbatim text from contracts.DISCLAIMER)
    """
    from openpharmastability.contracts import DISCLAIMER

    per_attr: list[dict[str, Any]] = []
    for ar in result.attributes:
        rec = _single_record(ar.result)
        # Augment with multi-attribute context.
        rec["attribute_role"] = ar.metadata.attribute_role.value
        rec["included_in_limiting_decision"] = ar.included_in_limiting_decision
        if ar.exclusion_reason is not None:
            rec["exclusion_reason"] = ar.exclusion_reason
        rec["unit"] = ar.metadata.unit
        rec["spec_type"] = ar.metadata.spec_type
        rec["transform"] = ar.metadata.transform
        rec["report_order"] = ar.metadata.report_order
        if ar.metadata.warnings:
            rec["metadata_warnings"] = list(ar.metadata.warnings)
        # v0.7.0: per-attribute sensitivity report. The single-
        # attribute record already inherits the field (under
        # ``sensitivity_report``), but the multi-attribute record
        # also exposes a flat per-attribute list under
        # ``sensitivity_reports`` so downstream tooling can iterate
        # ``rec["sensitivity_reports"]`` without recursing into
        # ``rec["attributes"]``. ``getattr(..., default)`` keeps the
        # record forward-compatible with hand-built fixtures that
        # predate the v0.7.0 field.
        rec["sensitivity_report"] = rec.get(
            "sensitivity_report",
            getattr(ar.result, "sensitivity_report", None),
        )
        per_attr.append(rec)

    # v0.4.0: overall extrapolation gate verdict. All eligible attributes
    # must permit extrapolation for the overall decision to permit it.
    # If no attribute is eligible, default to True so the report does
    # not look like a failure.
    eligible = [ar for ar in result.attributes if ar.included_in_limiting_decision]
    overall_extrapolation_allowed: bool = (
        all(ar.result.extrapolation_allowed for ar in eligible) if eligible else True
    )
    extrapolation_rationale_per_attribute: dict[str, str] = {
        ar.metadata.attribute: str(ar.result.extrapolation_rationale or "")
        for ar in result.attributes
    }

    return {
        "condition": result.condition,
        "product_type": result.product_type,
        "deliverable_term": result.deliverable_term,
        "supported_shelf_life_months": result.supported_shelf_life_months,
        "statistical_crossing_months": result.statistical_crossing_months,
        "limiting_attribute": result.limiting_attribute,
        "observed_data_months": result.observed_data_months,
        "attributes": per_attr,
        "warnings": list(dict.fromkeys(result.warnings)),
        "metadata": dict(result.metadata),
        "disclaimer": DISCLAIMER,
        # v0.4.0: ICH Q1A significant-change gating of extrapolation.
        # The per-attribute entries already inherit the single-attribute
        # record (which includes the five new keys); these two top-level
        # keys summarize the overall decision across all attributes.
        "extrapolation_allowed": overall_extrapolation_allowed,
        "extrapolation_rationale_per_attribute": extrapolation_rationale_per_attribute,
        # v0.5.0: roll up the per-attribute ``model_effects`` into one
        # summary block at the top level. The per-attribute entries
        # already carry the value (via the single-attribute record);
        # these keys make it easy for a downstream consumer to decide
        # whether ANY attribute used random-effects / mixed model
        # without iterating ``attributes``. ``getattr(..., default)``
        # keeps this robust against hand-built fixtures that predate
        # the v0.5.0 field.
        "model_effects_per_attribute": {
            ar.metadata.attribute: str(
                getattr(ar.result, "model_effects", "fixed") or "fixed"
            )
            for ar in result.attributes
        },
        "any_random_effects_used": any(
            str(getattr(ar.result, "model_effects", "fixed") or "fixed") == "random"
            for ar in result.attributes
        ),
        # v0.5.1: roll up the per-attribute mixed-model convergence /
        # boundary status. The per-attribute entries already carry
        # ``model_convergence`` (via the single-attribute record);
        # this top-level flag is True iff at least one ELIGIBLE
        # attribute had a non-converged or boundary fit. Downstream
        # tooling can use it to decide whether to surface a banner
        # on the multi-attribute report without iterating
        # ``attributes``. ``included_in_limiting_decision`` keeps the
        # flag scoped to the attributes that drive the overall
        # decision; supportive / informational attributes do not
        # trip the banner.
        "any_convergence_issue": any(
            (not bool(
                (ar.result.model_convergence or {}).get("converged", True)
            ))
            or bool(
                (ar.result.model_convergence or {}).get("boundary", False)
            )
            for ar in result.attributes
            if ar.included_in_limiting_decision
        ),
        # v0.7.0: top-level acceptance-criteria summary. The same
        # ``to_acceptance_criteria`` helper the
        # ``--acceptance-csv PATH`` CLI flag also calls; the
        # per-attribute entries are flattened to a list of dicts
        # so the JSON record is self-describing without forcing
        # downstream tooling to re-import the dataclass.
        "acceptance_criteria": [
            asdict(row) for row in to_acceptance_criteria(result)
        ],
        # v0.7.0: per-attribute sensitivity reports. One entry per
        # analyzed attribute, mirroring the per-attribute shape.
        # ``None`` when ``--sensitivity`` was not requested for
        # that attribute (or when the diagnostics layer did not
        # flag any influential points). Using
        # ``getattr(..., default)`` keeps the record forward-
        # compatible with hand-built fixtures that predate the
        # v0.7.0 field.
        "sensitivity_reports": {
            ar.metadata.attribute: (
                asdict(ar.result.sensitivity_report)
                if getattr(ar.result, "sensitivity_report", None) is not None
                else None
            )
            for ar in result.attributes
        },
    }


__all__ = ["to_multi_decision_record"]
