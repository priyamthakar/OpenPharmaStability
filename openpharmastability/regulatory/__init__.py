"""ICH Q1A(R2) regulatory decision-tree support for OpenPharmaStability v0.4.0.

This package contains the significant-change checklist evaluator and the
Q1E extrapolation allowance decision table. The engine wires these into
the long-term analysis; the rest of the toolkit is unaware of them.
"""
from __future__ import annotations

from openpharmastability.contracts import SignificantChange
from openpharmastability.regulatory.profile import (
    DEFAULT_PROFILE,
    GuidanceProfile,
    Q1AE,
)
from openpharmastability.regulatory.significant_change import (
    evaluate_significant_change,
    extrapolation_allowance,
    q1e_cap,
)


__all__ = [
    "SignificantChange",
    "evaluate_significant_change",
    "extrapolation_allowance",
    "q1e_cap",
    # v0.10.0 guidance-profile abstraction
    "GuidanceProfile",
    "Q1AE",
    "DEFAULT_PROFILE",
]
