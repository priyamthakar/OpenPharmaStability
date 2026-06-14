"""Limiting-attribute decision logic for v0.2.0 multi-attribute analysis.

This module owns one pure function, :func:`select_limiting`, which
takes the list of per-attribute :class:`AttributeResult` objects
produced by :func:`openpharmastability.shelf_life.multi_engine.analyze_many`
and assembles the overall :class:`MultiAttributeResult` — picking
the *limiting* attribute and copying the relevant per-attribute
fields up to the top level.

Rules (matching the spec):

* Only ``PRIMARY`` attributes whose per-attribute result has
  ``crossing.status == CROSSED`` and a positive
  ``supported_shelf_life_months`` are eligible to govern the
  overall decision.
* Non-eligible attributes are still present in the output list,
  but with ``included_in_limiting_decision=False`` and a short
  ``exclusion_reason`` string.
* Among the eligible attributes the limiting one is the one
  with the *smallest* ``supported_shelf_life_months``. Ties are
  broken by the *smallest* ``statistical_crossing_months`` (earlier
  in real time). A final alphabetical tiebreak on attribute name
  keeps the choice deterministic.
* The top-level ``metadata`` dict records how many attributes
  were considered (``n_attributes_total``), how many were
  eligible (``n_attributes_limiting``), and which tiebreak rule
  was actually applied (``"statistical_crossing"`` or ``None``).
"""
from __future__ import annotations

from openpharmastability.contracts import (
    AttributeResult,
    AttributeRole,
    CrossingStatus,
    MultiAttributeResult,
)


def _classify_exclusion(ar: AttributeResult) -> str:
    """Return a short exclusion reason for a non-eligible attribute.

    Order of checks matters: a SUPPORTIVE attribute whose fit also
    failed at baseline should still report ``"role"`` (the role
    decision is what kept it out of the limiting pool), not
    ``"fail_at_baseline"``.
    """
    role = ar.metadata.attribute_role
    if role is not AttributeRole.PRIMARY:
        return "role"

    status = ar.result.crossing.status
    if status is CrossingStatus.FAIL_AT_BASELINE:
        return "fail_at_baseline"
    if status is CrossingStatus.FLAT_OR_OPPOSITE:
        return "flat_or_opposite"
    if status is CrossingStatus.NO_CROSSING:
        return "no_crossing"

    shelf = ar.result.supported_shelf_life_months
    if shelf is None or shelf <= 0:
        return "no_shelf_life"

    # We should not reach this branch — every non-eligible attribute
    # is excluded for one of the reasons above. The fallback keeps
    # the field well-defined.
    return "no_shelf_life"


def _is_eligible(ar: AttributeResult) -> bool:
    role = ar.metadata.attribute_role
    status = ar.result.crossing.status
    shelf = ar.result.supported_shelf_life_months
    return (
        role is AttributeRole.PRIMARY
        and status is CrossingStatus.CROSSED
        and shelf is not None
        and shelf > 0
    )


def _dedupe_warnings(warnings: list[str]) -> list[str]:
    """Deduplicate a warnings list, preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def select_limiting(
    attribute_results: list[AttributeResult],
    deliverable_term: str,
    product_type: str,
    condition: str,
    observed_data_months: float,
) -> MultiAttributeResult:
    """Pick the limiting attribute and assemble the overall decision.

    Parameters
    ----------
    attribute_results:
        The list of per-attribute results, one per attribute that
        was analyzed. Each entry's ``included_in_limiting_decision``
        and ``exclusion_reason`` fields are ignored on input and
        recomputed here.
    deliverable_term:
        ``"shelf life"`` (product) or ``"retest period"``
        (substance) — propagated to the top-level result and into
        the metadata dict.
    product_type:
        ``"product"`` or ``"substance"`` — propagated to the
        top-level result and metadata.
    condition:
        The normalized storage condition string — propagated to
        the top-level result.
    observed_data_months:
        The longest time point across all attributes, used to
        populate ``MultiAttributeResult.observed_data_months``.

    Returns
    -------
    MultiAttributeResult
        The overall decision record. ``attributes`` carries the
        re-annotated per-attribute entries (eligible vs. excluded).
        ``limiting_attribute`` is the name of the chosen attribute
        or ``None`` if no attribute was eligible.
    """
    # 1) Re-annotate every input with the correct eligibility flag
    #    and exclusion reason.
    annotated: list[AttributeResult] = []
    for ar in attribute_results:
        if _is_eligible(ar):
            annotated.append(
                AttributeResult(
                    metadata=ar.metadata,
                    result=ar.result,
                    included_in_limiting_decision=True,
                    exclusion_reason=None,
                )
            )
        else:
            annotated.append(
                AttributeResult(
                    metadata=ar.metadata,
                    result=ar.result,
                    included_in_limiting_decision=False,
                    exclusion_reason=_classify_exclusion(ar),
                )
            )

    # 2) Sort the eligible list: min supported shelf life first;
    #    ties broken by earlier statistical crossing; final
    #    deterministic tiebreak on attribute name.
    eligible = [a for a in annotated if a.included_in_limiting_decision]

    def _sort_key(a: AttributeResult):
        shelf = a.result.supported_shelf_life_months
        cross = a.result.statistical_crossing_months
        return (
            shelf if shelf is not None else float("inf"),
            cross if cross is not None else float("inf"),
            a.metadata.attribute,
        )

    eligible.sort(key=_sort_key)

    # 3) Detect whether statistical_crossing was actually used as a
    #    tiebreak. We only flag it when at least two eligible
    #    attributes share the same supported shelf life.
    tie_break: str | None = None
    if eligible:
        min_shelf = eligible[0].result.supported_shelf_life_months
        shelf_ties = [
            a
            for a in eligible
            if a.result.supported_shelf_life_months == min_shelf
        ]
        if len(shelf_ties) > 1:
            tie_break = "statistical_crossing"

    # 4) Pick the winner (or None).
    if eligible:
        winner = eligible[0]
        limiting_attribute = winner.metadata.attribute
        supported = winner.result.supported_shelf_life_months
        statistical_crossing = winner.result.statistical_crossing_months
    else:
        limiting_attribute = None
        supported = None
        statistical_crossing = None

    # 5) Concatenate per-attribute warnings onto the top-level
    #    warnings list (deduped, preserving first-seen order).
    flat_warnings: list[str] = []
    for a in annotated:
        flat_warnings.extend(a.result.warnings)
    top_warnings = _dedupe_warnings(flat_warnings)

    if not eligible:
        top_warnings.append(
            "no eligible PRIMARY attribute had a positive supported shelf "
            "life; limiting decision could not be made"
        )

    # 6) Assemble the MultiAttributeResult. The top-level metadata
    #    dict is set here; the caller (analyze_many) is free to
    #    add file-hash and library-version fields on top.
    return MultiAttributeResult(
        condition=condition,
        product_type=product_type,
        deliverable_term=deliverable_term,
        attributes=annotated,
        limiting_attribute=limiting_attribute,
        supported_shelf_life_months=supported,
        statistical_crossing_months=statistical_crossing,
        observed_data_months=observed_data_months,
        warnings=top_warnings,
        metadata={
            "deliverable_term": deliverable_term,
            "product_type": product_type,
            "n_attributes_total": len(annotated),
            "n_attributes_limiting": len(eligible),
            "tie_break": tie_break,
        },
    )


__all__ = ["select_limiting"]
