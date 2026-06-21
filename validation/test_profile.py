import pytest
from openpharmastability.regulatory import profile as P
from openpharmastability import contracts


def test_resolve_profile_default_is_q1ae():
    assert P.resolve_profile(None) is P.Q1AE
    assert P.resolve_profile("") is P.Q1AE


def test_resolve_profile_case_insensitive_known_keys():
    assert P.resolve_profile("q1ae") is P.Q1AE
    assert P.resolve_profile("Q1AE") is P.Q1AE
    assert P.resolve_profile("q1-consolidated-draft") is P.Q1_CONSOLIDATED_DRAFT


def test_resolve_profile_unknown_raises():
    with pytest.raises(ValueError, match="unknown guidance profile"):
        P.resolve_profile("nope")


def test_q1ae_constants_are_contracts_primitives():
    assert P.Q1AE.poolability_alpha is contracts.POOLABILITY_ALPHA
    assert P.Q1AE.confidence is contracts.CONFIDENCE
    assert P.Q1AE.one_sided_quantile is contracts.ONE_SIDED_T_QUANTILE
    assert P.Q1AE.two_sided_quantile is contracts.TWO_SIDED_T_QUANTILE
    assert P.Q1AE.extrapolation_max_factor is contracts.EXTRAPOLATION_MAX_FACTOR
    assert P.Q1AE.extrapolation_max_months_beyond is contracts.EXTRAPOLATION_MAX_MONTHS_BEYOND


def test_consolidated_draft_is_numerically_inert_vs_q1ae():
    inert = ("poolability_alpha", "confidence", "one_sided_quantile",
             "two_sided_quantile", "extrapolation_max_factor",
             "extrapolation_max_months_beyond", "assay_change_threshold_pct")
    for f in inert:
        assert getattr(P.Q1_CONSOLIDATED_DRAFT, f) == getattr(P.Q1AE, f)
    assert P.Q1_CONSOLIDATED_DRAFT.name != P.Q1AE.name


def test_profiles_registry_lists_both():
    assert set(P.PROFILES) == {"q1ae", "q1-consolidated-draft"}
