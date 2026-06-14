"""Extrapolation caps and flags.

Q1E room-temperature rule of thumb (per OpenPharmaStability.md
"Shelf-life logic"):

  The proposed shelf life should not exceed roughly **twice** and
  should not be **more than 12 months beyond** the period covered by
  long-term data. Anything past the applicable cap is hard-flagged
  in the report.

The :func:`apply_extrapolation_caps` function:

1. Sets the ``extrapolation_flag`` on the result if the proposed
   shelf life extends beyond the observed data length.
2. Records a warning when the supported shelf life exceeds
   ``EXTRAPOLATION_MAX_FACTOR * observed`` or
   ``observed + EXTRAPOLATION_MAX_MONTHS_BEYOND``.
3. Returns a **new** :class:`StabilityResult` (the input is
   unchanged; dataclasses are immutable here because we copy).

The function never silently lowers the statistical estimate: it
just **flags** the cap exceedance and lets the user decide. The
supported shelf life is the engine's rounded-down value, capped
to the smaller of the statistical crossing and the cap-derived
limit when the cap is the binding constraint.

v0.4.0 — ICH Q1A significant-change allowance
---------------------------------------------

The function also accepts an optional ``allowance`` tuple
``(allowed, cap_months, rationale)`` returned by
:func:`openpharmastability.regulatory.extrapolation_allowance`.
When the allowance is supplied:

* ``result.extrapolation_allowed`` and ``result.extrapolation_rationale``
  are populated from the tuple.
* If the supported value exceeds the binding cap, the supported
  value is capped to ``cap_months`` and a warning is appended.
* If ``allowed is False``, the supported value is always capped
  to ``cap_months`` (even if it was within the cap) and the
  rationale is appended as a warning.

When ``allowance is None`` (the v0.3.1 default path), the function
behaves exactly as it did in v0.3.1: only the Q1E 2x/+12 cap math
runs and the new ``extrapolation_allowed`` /
``extrapolation_rationale`` fields are left at their permissive
defaults (``True`` / ``""``).
"""
from __future__ import annotations

import dataclasses
import math

from openpharmastability.contracts import (
    EXTRAPOLATION_MAX_FACTOR,
    EXTRAPOLATION_MAX_MONTHS_BEYOND,
    CrossingStatus,
    StabilityResult,
)


def apply_extrapolation_caps(
    result: StabilityResult,
    allowance: tuple[bool, float, str] | None = None,
) -> StabilityResult:
    """Apply Q1E room-temperature extrapolation guardrails.

    Returns a new :class:`StabilityResult` with the
    ``extrapolation_flag`` and ``warnings`` updated, and the
    ``supported_shelf_life_months`` capped when the cap is the
    binding constraint.

    The function is a no-op when the supported shelf life is within
    the observed data (no extrapolation needed) and no allowance is
    supplied.

    Parameters
    ----------
    result:
        The :class:`StabilityResult` to refine.
    allowance:
        Optional ``(allowed, cap_months, rationale)`` triple
        returned by
        :func:`openpharmastability.regulatory.extrapolation_allowance`.
        When supplied, the v0.4.0 ICH Q1A significant-change gate
        output is layered on top of the v0.3.1 cap math. When
        ``None`` (the default), the v0.3.1 behavior is preserved
        exactly.
    """
    # Copy to keep the input immutable. We track the fields we are
    # allowed to change (warnings, extrapolation_flag,
    # supported_shelf_life_months, extrapolation_allowed,
    # extrapolation_rationale) and emit a single
    # dataclasses.replace at the end. This avoids the silent-bug
    # class of "you forgot to forward a field when this function was
    # last touched" that the hand-rolled copy constructor invited.
    new_warnings: list[str] = list(result.warnings)
    new_extrapolation_flag: bool = bool(result.extrapolation_flag)
    new_supported_shelf_life_months: int | None = result.supported_shelf_life_months
    new_extrapolation_allowed: bool = bool(
        getattr(result, "extrapolation_allowed", True)
    )
    new_extrapolation_rationale: str = str(
        getattr(result, "extrapolation_rationale", "") or ""
    )

    # 1. Update extrapolation_flag.
    if (
        result.crossing.status is CrossingStatus.CROSSED
        and new_supported_shelf_life_months is not None
        and new_supported_shelf_life_months > result.observed_data_months
    ):
        new_extrapolation_flag = True
    elif result.crossing.status in (
        CrossingStatus.NO_CROSSING,
        CrossingStatus.FLAT_OR_OPPOSITE,
    ):
        # No crossing, or slope flat: shelf life is bounded by the
        # observed data, not extrapolated. Still record the
        # no-extrapolation fact.
        new_extrapolation_flag = False

    # 2. Hard-cap check. The cap is the minimum of:
    #    factor * observed_data_months
    #    observed_data_months + 12
    # Anything past the cap is hard-flagged.
    if (
        new_supported_shelf_life_months is not None
        and result.observed_data_months > 0
        and new_supported_shelf_life_months > result.observed_data_months
    ):
        factor_cap = math.floor(
            EXTRAPOLATION_MAX_FACTOR * result.observed_data_months
        )
        months_cap = math.floor(
            result.observed_data_months + EXTRAPOLATION_MAX_MONTHS_BEYOND
        )
        cap = min(factor_cap, months_cap)
        if new_supported_shelf_life_months > cap:
            cap_warning = (
                f"supported {result.deliverable_term} "
                f"({new_supported_shelf_life_months} mo) exceeds the Q1E "
                f"extrapolation cap ({cap} mo = min(2x and +12 mo of "
                f"observed {result.observed_data_months:g} mo)). Hard-flagged; "
                f"the statistical estimate is unchanged but the cap-derived "
                f"limit should govern the report."
            )
            new_warnings.append(cap_warning)
            # Cap the supported value to the cap (rounded down).
            new_supported_shelf_life_months = cap
        else:
            new_warnings.append(
                f"supported {result.deliverable_term} extends beyond observed "
                f"data ({result.observed_data_months:g} mo); extrapolation "
                f"flagged."
            )

    # 3. v0.4.0 ICH Q1A significant-change allowance. When the gate
    #    was exercised, the regulatory decision tree has produced
    #    (allowed, cap_months, rationale). We refine the result here.
    #
    #    No-op when allowance is None (v0.3.1 compatibility), or when
    #    the crossing status means there is nothing to cap (NO_CROSSING
    #    / FLAT_OR_OPPOSITE), or when the supported value is already
    #    None.
    if (
        allowance is not None
        and result.crossing.status is not CrossingStatus.NO_CROSSING
        and result.crossing.status is not CrossingStatus.FLAT_OR_OPPOSITE
        and new_supported_shelf_life_months is not None
    ):
        allowed, cap_months, rationale = allowance
        new_extrapolation_allowed = bool(allowed)
        new_extrapolation_rationale = str(rationale or "")
        # The binding cap is the allowance cap. We always apply it:
        # - when allowed is False, ALWAYS cap (even if the value
        #   was within it), because the gate has judged extrapolation
        #   to be unsupported;
        # - when allowed is True, only cap if the supported value
        #   exceeds the binding cap.
        cap_floor = int(math.floor(float(cap_months)))
        if (not allowed) or new_supported_shelf_life_months > cap_floor:
            if new_supported_shelf_life_months != cap_floor:
                cap_warning = (
                    f"supported {result.deliverable_term} "
                    f"({new_supported_shelf_life_months} mo) capped to "
                    f"{cap_floor} mo by the ICH Q1A significant-change "
                    f"gate ({new_extrapolation_rationale})."
                )
                new_warnings.append(cap_warning)
            else:
                # Value already at the cap, but the gate forbade
                # extrapolation — still surface the rationale.
                new_warnings.append(
                    f"extrapolation not permitted by the ICH Q1A "
                    f"significant-change gate "
                    f"({new_extrapolation_rationale})."
                )
            new_supported_shelf_life_months = cap_floor
            # If the gate forbids extrapolation, flip the
            # extrapolation flag accordingly.
            if not allowed:
                new_extrapolation_flag = True

    return dataclasses.replace(
        result,
        warnings=new_warnings,
        extrapolation_flag=new_extrapolation_flag,
        supported_shelf_life_months=new_supported_shelf_life_months,
        extrapolation_allowed=new_extrapolation_allowed,
        extrapolation_rationale=new_extrapolation_rationale,
    )


__all__ = ["apply_extrapolation_caps"]
