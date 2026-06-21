"""Guidance-profile abstraction (v0.10.0).

A :class:`GuidanceProfile` bundles every regulator-defined numeric
constant the decision engine consumes — the poolability significance
level, the mean-response confidence level, the one-sided / two-sided
t-quantiles, the room-temperature extrapolation caps, and the
significant-change assay threshold — into a single frozen object.

Why this exists
---------------
The ICH Q1A–Q1F + Q5C stability-guidance family may be revised or
consolidated over time. Until the project deliberately adopts a new
profile, this toolkit implements **Q1A(R2) + Q1E** and labels
everything "Q1E-inspired" (see ``NEXT_STEPS.md`` §10).

Threading an *active profile* through the engine now — instead of
reading module-level constants directly at each call site — means the
eventual switch is a data change, not an algorithm rewrite: define a
``Q1_CONSOLIDATED`` profile, pass ``profile=Q1_CONSOLIDATED`` (or wire
a ``--guidance q1`` CLI flag), regenerate the golden file, and bump
MAJOR. No conditional re-plumbing of the statistical core.

Design notes
------------
* The default profile :data:`Q1AE` is built **from** the canonical
  primitives in :mod:`openpharmastability.contracts`. Those constants
  remain the single source of truth for the default numbers, so the
  default ``analyze()`` path is byte-for-byte identical to v0.9.0
  (``Q1AE.poolability_alpha is contracts.POOLABILITY_ALPHA`` and so
  on). A regression test asserts this equality.
* The dependency direction is one-way: this module imports from
  ``contracts``; ``contracts`` never imports from here. That keeps
  ``contracts`` the stdlib-only import root (AGENTS.md §4) and avoids
  a circular import.
* ``GuidanceProfile`` is ``frozen=True`` so a profile cannot be
  mutated after construction — an active profile is an immutable
  audit fact for a given run.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from openpharmastability.contracts import (
    CONFIDENCE,
    DISCLAIMER,
    EXTRAPOLATION_MAX_FACTOR,
    EXTRAPOLATION_MAX_MONTHS_BEYOND,
    ONE_SIDED_T_QUANTILE,
    POOLABILITY_ALPHA,
    TWO_SIDED_T_QUANTILE,
)


@dataclass(frozen=True)
class GuidanceProfile:
    """An immutable bundle of regulator-defined numeric constants.

    Parameters
    ----------
    name:
        Human-readable identifier, e.g. ``"Q1A_R2+Q1E"`` or
        ``"Q1_consolidated"``. Recorded in reports / records so the
        active guidance is auditable.
    poolability_alpha:
        Significance level for the two-step ANCOVA poolability test
        (Q1E uses 0.25).
    confidence:
        Mean-response confidence level (Q1E uses 0.95).
    one_sided_quantile:
        t-quantile for a one-sided ``confidence`` bound (0.95 for a
        one-sided 95% bound — 5% in a single tail).
    two_sided_quantile:
        t-quantile for a two-sided ``confidence`` bound (0.975 for a
        two-sided 95% bound — 2.5% in each tail). Used by the
        bidirectional crossing path.
    extrapolation_max_factor:
        Room-temperature extrapolation cap as a multiple of the
        observed long-term duration (Q1E rule of thumb: 2x).
    extrapolation_max_months_beyond:
        Room-temperature extrapolation cap as an absolute number of
        months beyond the observed long-term duration (Q1E: +12).
    assay_change_threshold_pct:
        Significant-change assay threshold, in percent (Q1A(R2): 5%).
    significant_change_criteria:
        The attribute families the significant-change checklist
        considers. Informational metadata for the profile; the
        checklist evaluator keys off attribute roles, not this tuple.
    disclaimer:
        The verbatim regulatory disclaimer that applies under this
        profile. Defaults to :data:`contracts.DISCLAIMER`.
    """

    name: str
    poolability_alpha: float
    confidence: float
    one_sided_quantile: float
    two_sided_quantile: float
    extrapolation_max_factor: float
    extrapolation_max_months_beyond: float
    assay_change_threshold_pct: float = 5.0
    significant_change_criteria: tuple[str, ...] = field(
        default_factory=lambda: (
            "assay",
            "degradant",
            "physical",
            "ph",
            "dissolution",
        )
    )
    disclaimer: str = DISCLAIMER


# The default profile: ICH Q1A(R2) + Q1E, assembled from the canonical
# constants in ``contracts``. Keeping the values sourced from the
# contracts primitives guarantees the default ``analyze()`` path is
# byte-equivalent to v0.9.0.
Q1AE = GuidanceProfile(
    name="Q1A_R2+Q1E",
    poolability_alpha=POOLABILITY_ALPHA,
    confidence=CONFIDENCE,
    one_sided_quantile=ONE_SIDED_T_QUANTILE,
    two_sided_quantile=TWO_SIDED_T_QUANTILE,
    extrapolation_max_factor=EXTRAPOLATION_MAX_FACTOR,
    extrapolation_max_months_beyond=EXTRAPOLATION_MAX_MONTHS_BEYOND,
)

# The default active profile. When consolidated ICH Q1 reaches Step 4,
# add a ``Q1_CONSOLIDATED = GuidanceProfile(...)`` here and switch this
# alias (MAJOR bump + golden regeneration).
DEFAULT_PROFILE = Q1AE


# PROVISIONAL — pending the consolidated ICH Q1 reaching Step 4
# (NEXT_STEPS.md §10.1). Values MIRROR Q1AE so selecting this profile is
# numerically inert until the consolidated guideline's final numbers are
# confirmed. When Step 4 lands, edit the values below (keep the name),
# regenerate the golden file, and bump MAJOR. Do not change
# DEFAULT_PROFILE without that bump.
Q1_CONSOLIDATED_DRAFT = GuidanceProfile(
    name="Q1_consolidated_draft",
    poolability_alpha=POOLABILITY_ALPHA,
    confidence=CONFIDENCE,
    one_sided_quantile=ONE_SIDED_T_QUANTILE,
    two_sided_quantile=TWO_SIDED_T_QUANTILE,
    extrapolation_max_factor=EXTRAPOLATION_MAX_FACTOR,
    extrapolation_max_months_beyond=EXTRAPOLATION_MAX_MONTHS_BEYOND,
    assay_change_threshold_pct=5.0,
)

#: Registry of selectable guidance profiles, keyed by CLI ``--guidance`` name.
PROFILES: dict[str, GuidanceProfile] = {
    "q1ae": Q1AE,
    "q1-consolidated-draft": Q1_CONSOLIDATED_DRAFT,
}


def resolve_profile(name: str | None) -> GuidanceProfile:
    """Resolve a ``--guidance`` name to a :class:`GuidanceProfile`.

    ``None`` or the empty string returns :data:`DEFAULT_PROFILE`. Lookup is
    case-insensitive. Unknown names raise ``ValueError`` listing the
    available keys so the CLI can surface a one-line error.
    """
    if not name:
        return DEFAULT_PROFILE
    key = name.strip().lower()
    if key not in PROFILES:
        raise ValueError(
            f"unknown guidance profile {name!r}; available: {sorted(PROFILES)}"
        )
    return PROFILES[key]


__all__ = ["GuidanceProfile", "Q1AE", "Q1_CONSOLIDATED_DRAFT", "DEFAULT_PROFILE", "PROFILES", "resolve_profile"]
