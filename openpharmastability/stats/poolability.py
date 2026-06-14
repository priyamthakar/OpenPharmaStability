"""3-step ANCOVA poolability test (ICH Q1E-inspired, α = 0.25).

The :func:`decide_poolability` function runs a nested ANCOVA on the
batch effect:

1. **Equality of slopes** — fit ``value ~ time * C(batch)`` and test
   the ``time:batch`` interaction. If ``p < alpha``, the batches
   differ in slope and we report
   :data:`~openpharmastability.contracts.Poolability.NONE` (use
   per-batch fits).
2. **Equality of intercepts** — fit ``value ~ time + C(batch)`` and
   test the ``C(batch)`` term. If ``p < alpha``, batches share a
   slope but not an intercept, so we report
   :data:`~openpharmastability.contracts.Poolability.PARTIAL` (common
   slope, batch-specific intercepts).
3. **Full pooling** — if neither test rejects, we report
   :data:`~openpharmastability.contracts.Poolability.FULL`.

The :func:`statsmodels.stats.anova.anova_lm` function with
``typ=2`` reports the F-test for each term *using the pooled MSE
from the full model*. That matches ICH Q1E's nested-model reading
of the ANCOVA table: the F-statistic for "slopes are equal" is the
reduction in SSE between the additive model and the interaction
model, divided by the interaction model's MSE.

We deliberately use ``alpha = 0.25`` (per the Q1E example) and
expose the per-step p-values so the report can surface them.

Note: the public function is named ``decide_poolability`` (not
``test_poolability``) so that pytest does not auto-collect it as a
test function. The aliases ``test_poolability = decide_poolability``
at the bottom of this module keep backward-compatible call sites
working but are not pytest-collected because the alias assignment
does not start with ``def test_``.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.stats.anova import anova_lm

from openpharmastability.contracts import (
    FitResult,
    ModelKind,
    POOLABILITY_ALPHA,
    Poolability,
    PoolabilityResult,
    ValidatedData,
)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------


def _interaction_pvalue(anova_table: pd.DataFrame) -> float:
    """Return the p-value for the slopes-equality test.

    For a Type-II ANCOVA of ``value ~ time * C(batch)`` the relevant
    row is the interaction term ``time:C(batch)``. If the table
    does not contain such a row, we report ``p = 1.0`` so the test
    is automatically accepted.
    """
    for idx in anova_table.index:
        if "time:C(batch)" in str(idx) or "time_months:C(batch)" in str(idx):
            return float(anova_table.loc[idx, "PR(>F)"])
    return 1.0


def _batch_pvalue(anova_table: pd.DataFrame) -> float:
    """Return the p-value for the intercepts-equality test on the
    additive model ``value ~ time + C(batch)``.

    The relevant row is ``C(batch)`` (the categorical main effect).
    """
    for idx in anova_table.index:
        if str(idx).startswith("C(batch)"):
            return float(anova_table.loc[idx, "PR(>F)"])
    return 1.0


def _fit_table(df: pd.DataFrame) -> pd.DataFrame:
    """Return the fit frame the regression layer would use.

    The poolability test re-fits the additive and interaction models
    itself because the choice of model depends on the poolability
    result; this is the spec's expected pattern.
    """
    fit = df.loc[:, ["batch", "time_months", "value"]].dropna().copy()
    if fit.empty:
        raise ValueError(
            "Cannot run poolability test: ValidatedData.df is empty"
        )
    return fit


# -----------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------


def decide_poolability(
    fits: dict[ModelKind, FitResult],
    data: ValidatedData,
    alpha: float = POOLABILITY_ALPHA,
) -> PoolabilityResult:
    """Run the 3-step nested ANCOVA poolability test.

    Parameters
    ----------
    fits:
        The output of :func:`~openpharmastability.stats.regression.fit_models`.
        The function inspects this dict only to confirm that the
        relevant models have been fit; the F-tests themselves are
        re-run on the raw data so the test is self-contained.
    data:
        The :class:`ValidatedData` whose ``df`` carries ``batch``,
        ``time_months`` and ``value``.
    alpha:
        Significance level for both steps. Defaults to
        :data:`~openpharmastability.contracts.POOLABILITY_ALPHA`
        (0.25) per ICH Q1E.

    Returns
    -------
    PoolabilityResult
        The decision, the per-step p-values, the alpha used, and
        human-readable notes for the report.
    """
    # The fits are passed in for API symmetry with selection/bound
    # code. We do not consume their parameter estimates; the test
    # is its own pair of OLS fits.
    if ModelKind.SEPARATE not in fits or ModelKind.COMMON_SLOPE not in fits:
        raise ValueError(
            "test_poolability requires fits for both SEPARATE and "
            "COMMON_SLOPE; got: "
            f"{sorted(k.value for k in fits.keys())!r}"
        )

    df = _fit_table(data.df)
    notes: list[str] = []
    p_slopes: float
    p_intercepts: float | None = None

    # --- Step 1: equality of slopes -------------------------------
    interaction_model = smf.ols(
        "value ~ time_months * C(batch)", data=df
    ).fit()
    interaction_anova = anova_lm(interaction_model, typ=2)
    p_slopes = _interaction_pvalue(interaction_anova)
    notes.append(
        f"step1 slopes: F-test on time:C(batch), p={p_slopes:.4g} "
        f"(alpha={alpha:g})"
    )

    if p_slopes < alpha:
        return PoolabilityResult(
            decision=Poolability.NONE,
            p_slopes=p_slopes,
            p_intercepts=None,
            alpha=alpha,
            notes=notes,
        )

    # --- Step 2: equality of intercepts (given common slope) -----
    additive_model = smf.ols(
        "value ~ time_months + C(batch)", data=df
    ).fit()
    additive_anova = anova_lm(additive_model, typ=2)
    p_intercepts = _batch_pvalue(additive_anova)
    notes.append(
        f"step2 intercepts: F-test on C(batch), p={p_intercepts:.4g} "
        f"(alpha={alpha:g})"
    )

    if p_intercepts < alpha:
        return PoolabilityResult(
            decision=Poolability.PARTIAL,
            p_slopes=p_slopes,
            p_intercepts=p_intercepts,
            alpha=alpha,
            notes=notes,
        )

    # --- Step 3: full pooling ------------------------------------
    notes.append("step3: neither slopes nor intercepts rejected; FULL")
    return PoolabilityResult(
        decision=Poolability.FULL,
        p_slopes=p_slopes,
        p_intercepts=p_intercepts,
        alpha=alpha,
        notes=notes,
    )


__all__ = ["decide_poolability", "test_poolability"]

# Backward-compatible alias. The function is named
# ``decide_poolability`` to avoid pytest's auto-collection of any
# name starting with ``test_``. Older call sites and the spec's
# documentation reference ``test_poolability``; this alias keeps
# them working. The alias itself is a plain assignment, not a
# ``def test_*`` function, so pytest will not collect it.
test_poolability = decide_poolability
