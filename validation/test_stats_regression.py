"""Tests for ``openpharmastability.stats.regression.fit_models``.

The regression layer is the foundation the rest of the stats core
sits on. These tests pin down the invariants Wave 2 (engine) and
Wave 1F (golden/edge fixtures) will rely on:

* For a POOLED fit, ``params['b0']`` and ``params['b1']`` match
  ``numpy.polyfit`` to the last bit (``rtol=1e-9``).
* ``s_resid`` matches ``sqrt(SSE / df_resid)`` exactly.
* ``cov`` has shape ``(p, p)`` for each model.
* ``fitted_fn`` at known t matches ``b0 + b1 * t`` (POOLED) and the
  analogous per-batch expression for the multi-batch models.
* The COMMON_SLOPE model shares ``b1`` across batches and gives each
  batch its own ``b0_<batch>``.
* The SEPARATE model gives every batch its own ``b0_<batch>`` and
  ``b1_<batch>``.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from openpharmastability.contracts import (
    Direction,
    FitResult,
    ModelKind,
    ValidatedData,
)
from openpharmastability.stats.poolability import decide_poolability
from openpharmastability.stats.regression import fit_models


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


def _decreasing_assay_2batch() -> ValidatedData:
    """Build a small, deterministic 2-batch x 4-time-point assay frame.

    The values are an exact linear pattern: ``value = 100 - 0.25 * t``,
    same for every batch. That makes the POOLED, COMMON_SLOPE, and
    SEPARATE fits produce identical parameter estimates within
    floating-point tolerance, so the tests can use one set of
    expected values across all three.
    """
    rows = []
    for batch in ("B1", "B2"):
        for t in (0.0, 3.0, 6.0, 12.0):
            rows.append(
                {
                    "batch": batch,
                    "condition": "25C/60RH",
                    "time_months": t,
                    "attribute": "assay",
                    "value": 100.0 - 0.25 * t,
                    "lower_spec": 90.0,
                    "upper_spec": 110.0,
                    "direction": "decreasing",
                }
            )
    df = pd.DataFrame(rows)
    return ValidatedData(
        df=df,
        attribute="assay",
        condition="25C/60RH",
        direction=Direction.DECREASING,
        lower_spec=90.0,
        upper_spec=110.0,
        n_batches=2,
        time_points=[0.0, 3.0, 6.0, 12.0],
        warnings=[],
    )


def _heteroscedastic_3batch() -> ValidatedData:
    """A 3-batch x 5-time-point frame with distinct intercepts and
    a tiny amount of noise — used to test that multi-batch fits
    surface per-batch estimates correctly.
    """
    rng = np.random.default_rng(seed=42)
    rows = []
    intercepts = {"B1": 100.0, "B2": 99.0, "B3": 101.0}
    slopes = {"B1": -0.20, "B2": -0.20, "B3": -0.20}
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0):
            noise = float(rng.normal(loc=0.0, scale=0.05))
            rows.append(
                {
                    "batch": batch,
                    "condition": "25C/60RH",
                    "time_months": t,
                    "attribute": "assay",
                    "value": intercepts[batch] + slopes[batch] * t + noise,
                    "lower_spec": 90.0,
                    "upper_spec": 110.0,
                    "direction": "decreasing",
                }
            )
    df = pd.DataFrame(rows)
    return ValidatedData(
        df=df,
        attribute="assay",
        condition="25C/60RH",
        direction=Direction.DECREASING,
        lower_spec=90.0,
        upper_spec=110.0,
        n_batches=3,
        time_points=[0.0, 3.0, 6.0, 9.0, 12.0],
        warnings=[],
    )


# ---------------------------------------------------------------------------
# POOLED
# ---------------------------------------------------------------------------


def test_fit_models_returns_all_three_kinds() -> None:
    v = _decreasing_assay_2batch()
    fits = fit_models(v)
    assert set(fits.keys()) == {
        ModelKind.POOLED,
        ModelKind.COMMON_SLOPE,
        ModelKind.SEPARATE,
    }
    for kind, fit in fits.items():
        assert isinstance(fit, FitResult)
        assert fit.kind is kind
        assert fit.batches == ["B1", "B2"]


def test_pooled_params_match_numpy_polyfit() -> None:
    """``params['b0']`` and ``params['b1']`` match ``polyfit(x, y, 1)``."""
    v = _decreasing_assay_2batch()
    fit = fit_models(v)[ModelKind.POOLED]

    x = v.df["time_months"].to_numpy(dtype=float)
    y = v.df["value"].to_numpy(dtype=float)
    expected_b1, expected_b0 = np.polyfit(x, y, 1)

    assert math.isclose(fit.params["b0"], float(expected_b0), rel_tol=1e-9, abs_tol=1e-12)
    assert math.isclose(fit.params["b1"], float(expected_b1), rel_tol=1e-9, abs_tol=1e-12)


def test_pooled_s_resid_matches_sqrt_sse_over_df() -> None:
    """``s_resid`` is the residual standard error, ``sqrt(SSE/df)``."""
    v = _decreasing_assay_2batch()
    fit = fit_models(v)[ModelKind.POOLED]

    x = v.df["time_months"].to_numpy(dtype=float)
    y = v.df["value"].to_numpy(dtype=float)
    b0, b1 = fit.params["b0"], fit.params["b1"]
    sse = float(((y - (b0 + b1 * x)) ** 2).sum())
    expected_s = math.sqrt(sse / fit.df_resid)
    assert math.isclose(fit.s_resid, expected_s, rel_tol=1e-12, abs_tol=1e-12)


def test_pooled_df_resid_matches_n_minus_two() -> None:
    v = _decreasing_assay_2batch()
    fit = fit_models(v)[ModelKind.POOLED]
    # 2 batches * 4 time points = 8 rows, p=2, so df = 6.
    assert fit.df_resid == 6


def test_pooled_cov_shape_and_psd() -> None:
    v = _decreasing_assay_2batch()
    fit = fit_models(v)[ModelKind.POOLED]
    assert fit.cov.shape == (2, 2)
    # The covariance matrix is symmetric and (theoretically)
    # positive semi-definite; assert symmetry and that the diagonal
    # is non-negative.
    assert np.allclose(fit.cov, fit.cov.T)
    assert np.all(np.diag(fit.cov) >= 0.0)


def test_pooled_fitted_fn_at_known_t() -> None:
    v = _decreasing_assay_2batch()
    fit = fit_models(v)[ModelKind.POOLED]
    b0, b1 = fit.params["b0"], fit.params["b1"]
    for t in (-3.0, 0.0, 5.5, 24.0):
        assert math.isclose(fit.fitted_fn(t), b0 + b1 * t, rel_tol=1e-12, abs_tol=1e-12)


def test_pooled_design_records_tbar_sxx_n() -> None:
    v = _decreasing_assay_2batch()
    fit = fit_models(v)[ModelKind.POOLED]
    x = v.df["time_months"].to_numpy(dtype=float)
    assert fit.design["n"] == int(x.size)
    assert math.isclose(fit.design["tbar"], float(x.mean()), rel_tol=1e-12)
    assert math.isclose(
        fit.design["Sxx"], float(((x - x.mean()) ** 2).sum()), rel_tol=1e-12
    )


# ---------------------------------------------------------------------------
# COMMON_SLOPE
# ---------------------------------------------------------------------------


def test_common_slope_has_one_slope_and_per_batch_intercepts() -> None:
    v = _decreasing_assay_2batch()
    fit = fit_models(v)[ModelKind.COMMON_SLOPE]
    # One common slope; one intercept per batch.
    assert "b1" in fit.params
    assert "b0_B1" in fit.params
    assert "b0_B2" in fit.params
    # 2 + (2 - 1) = 3 parameters
    assert fit.cov.shape == (3, 3)
    assert fit.df_resid == 8 - 3


def test_common_slope_fitted_fn_is_callable_per_batch() -> None:
    v = _decreasing_assay_2batch()
    fit = fit_models(v)[ModelKind.COMMON_SLOPE]
    fn_b1 = fit.fitted_fn("B1")
    fn_b2 = fit.fitted_fn("B2")
    # Each batch's function returns ``b0_<b> + b1 * t`` at any t.
    for t in (0.0, 6.0, 12.0):
        assert math.isclose(
            fn_b1(t), fit.params["b0_B1"] + fit.params["b1"] * t,
            rel_tol=1e-12, abs_tol=1e-12,
        )
        assert math.isclose(
            fn_b2(t), fit.params["b0_B2"] + fit.params["b1"] * t,
            rel_tol=1e-12, abs_tol=1e-12,
        )


def test_common_slope_agrees_with_pooled_when_intercepts_equal() -> None:
    """When every batch has the same data, the common-slope
    estimate of ``b1`` agrees with the POOLED estimate (within
    floating-point tolerance) and every batch's intercept equals
    the POOLED intercept.
    """
    v = _decreasing_assay_2batch()
    pooled = fit_models(v)[ModelKind.POOLED]
    common = fit_models(v)[ModelKind.COMMON_SLOPE]
    assert math.isclose(
        common.params["b1"], pooled.params["b1"],
        rel_tol=1e-9, abs_tol=1e-12,
    )
    for b in ("B1", "B2"):
        assert math.isclose(
            common.params[f"b0_{b}"], pooled.params["b0"],
            rel_tol=1e-9, abs_tol=1e-12,
        )


# ---------------------------------------------------------------------------
# SEPARATE
# ---------------------------------------------------------------------------


def test_separate_has_per_batch_slope_and_intercept() -> None:
    v = _decreasing_assay_2batch()
    fit = fit_models(v)[ModelKind.SEPARATE]
    for b in ("B1", "B2"):
        assert f"b0_{b}" in fit.params
        assert f"b1_{b}" in fit.params
    # 2 * 2 = 4 parameters
    assert fit.cov.shape == (4, 4)
    assert fit.df_resid == 8 - 4


def test_separate_fitted_fn_per_batch() -> None:
    v = _heteroscedastic_3batch()
    fit = fit_models(v)[ModelKind.SEPARATE]
    for batch in fit.batches:
        fn = fit.fitted_fn(batch)
        b0 = fit.params[f"b0_{batch}"]
        b1 = fit.params[f"b1_{batch}"]
        for t in (0.0, 3.0, 6.0, 12.0):
            assert math.isclose(
                fn(t), b0 + b1 * t, rel_tol=1e-12, abs_tol=1e-12,
            )


def test_separate_intercepts_differ_when_data_differ() -> None:
    """The 3-batch fixture has distinct intercepts; the SEPARATE
    fit should reflect that with three different ``b0_<batch>``
    values.
    """
    v = _heteroscedastic_3batch()
    fit = fit_models(v)[ModelKind.SEPARATE]
    intercepts = [fit.params[f"b0_{b}"] for b in fit.batches]
    # At least one pair must be measurably different.
    spread = max(intercepts) - min(intercepts)
    assert spread > 0.5, f"expected spread > 0.5, got {intercepts!r}"


def test_separate_residual_se_smaller_than_pooled() -> None:
    """Sanity check: with three batches on a shared slope, the
    SEPARATE fit cannot have a larger residual variance than the
    POOLED fit; in fact the SEPARATE residual SE equals the
    POOLED residual SE for this exact-linear fixture.
    """
    v = _decreasing_assay_2batch()
    fits = fit_models(v)
    # The data are on a perfect line, so the residual SE is ~0
    # for both models. Just make sure the SEPARATE fit's residual
    # SE is no bigger than the POOLED fit's.
    assert fits[ModelKind.SEPARATE].s_resid <= fits[ModelKind.POOLED].s_resid + 1e-12


# ---------------------------------------------------------------------------
# Defensive
# ---------------------------------------------------------------------------


def test_fit_models_raises_on_empty_frame() -> None:
    v = ValidatedData(
        df=pd.DataFrame(columns=["batch", "time_months", "value"]),
        attribute="assay",
        condition="25C/60RH",
        direction=Direction.DECREASING,
        lower_spec=90.0,
        upper_spec=110.0,
        n_batches=0,
        time_points=[],
        warnings=[],
    )
    with pytest.raises(ValueError, match="empty"):
        fit_models(v)


# ---------------------------------------------------------------------------
# v0.5.0 opt-in random-effects (mixed-model) path
# ---------------------------------------------------------------------------
#
# The default ``fit_models(data)`` call must remain byte-identical to
# the v0.4 fixed-effect path. The ``random_effects=True`` opt-in swaps
# the underlying engine to ``smf.mixedlm`` while keeping the
# FitResult shape unchanged. The poolability test is always OLS, so
# its p-values must be identical regardless of the fit-engine flag.


def test_fit_models_default_remains_fixed_effect() -> None:
    """``fit_models(data)`` with no ``random_effects`` flag must
    produce a POOLED ``s_resid`` and ``cov`` that match a
    hand-computed OLS reference to ``rtol=1e-12``.
    """
    v = _decreasing_assay_2batch()
    fit = fit_models(v)[ModelKind.POOLED]

    # Hand-computed OLS reference: np.polyfit for params, manual SSE
    # for s_resid, and the closed-form (X'X)^-1 * s^2 for cov.
    x = v.df["time_months"].to_numpy(dtype=float)
    y = v.df["value"].to_numpy(dtype=float)
    b1_hat, b0_hat = np.polyfit(x, y, 1)
    sse = float(((y - (b0_hat + b1_hat * x)) ** 2).sum())
    df_resid = int(x.size - 2)
    expected_s = math.sqrt(sse / df_resid)

    assert math.isclose(fit.s_resid, expected_s, rel_tol=1e-12, abs_tol=1e-12)

    # Closed-form OLS cov on a single-predictor regression with an
    # intercept column.
    n = int(x.size)
    xbar = float(x.mean())
    sxx = float(((x - xbar) ** 2).sum())
    sigma2 = sse / df_resid
    # Var(b0) = sigma2 * (1/n + xbar^2 / Sxx)
    # Var(b1) = sigma2 / Sxx
    # Cov(b0, b1) = -sigma2 * xbar / Sxx
    expected_cov = np.array(
        [
            [sigma2 * (1.0 / n + xbar * xbar / sxx),
             -sigma2 * xbar / sxx],
            [-sigma2 * xbar / sxx,
             sigma2 / sxx],
        ]
    )
    assert np.allclose(fit.cov, expected_cov, rtol=1e-12, atol=1e-12)


def test_fit_models_random_effects_opt_in_produces_mixed_fit() -> None:
    """``fit_models(data, random_effects=True)`` swaps the engine to
    ``smf.mixedlm``. The mixed model's residual SE must be no larger
    than the OLS one (random intercept absorbs some variance), the
    random-effect variance must be >= 0, and the FitResult must
    carry the ``random_effects`` sub-block on ``design``.
    """
    v = _heteroscedastic_3batch()
    ols_fits = fit_models(v)
    mixed_fits = fit_models(v, random_effects=True)

    mixed_pooled = mixed_fits[ModelKind.POOLED]
    ols_pooled = ols_fits[ModelKind.POOLED]

    # The random intercept absorbs between-batch variance, so the
    # residual SE on the same fixed-effect formula must drop or
    # stay the same. Use a relaxed tolerance (mixed is REML, OLS is
    # ML — the absolute scale is not 1:1 comparable, but the
    # "smaller or equal" inequality is the load-bearing invariant).
    assert mixed_pooled.s_resid <= ols_pooled.s_resid + 1e-9

    # The random-effect variance is stored on the design block and
    # is non-negative (covariance of a random effect).
    re_block = mixed_pooled.design.get("random_effects")
    assert re_block is not None
    assert re_block["engine"] == "mixedlm"
    assert re_block["kind"] == ModelKind.POOLED.value
    group_var = float(re_block["group_var"])
    assert group_var >= 0.0

    # The fixed-effect parameter estimates are close to OLS for a
    # POOLED formula on data that all share the same slope
    # (intercept is what the random effect absorbs, not the slope).
    assert math.isclose(
        mixed_pooled.params["b1"], ols_pooled.params["b1"],
        rel_tol=1e-3, abs_tol=1e-3,
    )

    # The cov matrix is finite and has the right shape.
    assert mixed_pooled.cov.shape == ols_pooled.cov.shape
    assert bool(np.isfinite(mixed_pooled.cov).all())


def test_fit_models_random_effects_runs_three_kinds() -> None:
    """All three model kinds run under ``random_effects=True`` and
    return valid :class:`FitResult` instances: non-None, with a
    positive residual df and a callable ``fitted_fn``.
    """
    v = _heteroscedastic_3batch()
    fits = fit_models(v, random_effects=True)
    assert set(fits.keys()) == {
        ModelKind.POOLED,
        ModelKind.COMMON_SLOPE,
        ModelKind.SEPARATE,
    }
    for kind, fit in fits.items():
        assert isinstance(fit, FitResult)
        assert fit.kind is kind
        assert fit.df_resid > 0
        # POOLED returns t -> yhat; multi-batch returns batch -> (t -> yhat).
        if kind is ModelKind.POOLED:
            assert callable(fit.fitted_fn)
            assert math.isfinite(float(fit.fitted_fn(0.0)))
        else:
            assert callable(fit.fitted_fn)
            for batch in fit.batches:
                fn = fit.fitted_fn(batch)
                assert callable(fn)
                assert math.isfinite(float(fn(0.0)))
        # Each kind also records the random-effects sub-block.
        re_block = fit.design.get("random_effects")
        assert re_block is not None
        assert re_block["kind"] == kind.value


def test_poolability_still_ols_under_random_effects() -> None:
    """The poolability test is always the OLS ANCOVA, so its
    p-values must be identical (``rtol=1e-6``) whether or not the
    fit engine was mixed.
    """
    v = _heteroscedastic_3batch()
    ols_pool = decide_poolability(fit_models(v), v)
    mixed_pool = decide_poolability(fit_models(v, random_effects=True), v)

    assert ols_pool.decision == mixed_pool.decision
    assert math.isclose(
        ols_pool.p_slopes, mixed_pool.p_slopes,
        rel_tol=1e-6, abs_tol=1e-12,
    )
    # p_intercepts is non-None for PARTIAL/FULL decisions and is the
    # same OLS F-test in both cases.
    if ols_pool.p_intercepts is not None and mixed_pool.p_intercepts is not None:
        assert math.isclose(
            ols_pool.p_intercepts, mixed_pool.p_intercepts,
            rel_tol=1e-6, abs_tol=1e-12,
        )


# ---------------------------------------------------------------------------
# v0.5.1 mixed-model convergence / boundary sub-block (additive)
# ---------------------------------------------------------------------------
#
# The regression layer is responsible for stamping a ``convergence``
# sub-block on every ``FitResult.design`` so the engine and the
# reporting layer have a single, well-typed contract for the
# fit-level convergence / boundary state. The OLS path is closed-form
# and always reports ``{"converged": True, "boundary": False,
# "message": "OLS"}``; the random-effects path runs the actual
# detection logic on the fitted MixedLMResults.


def test_ols_path_records_convergence_ok() -> None:
    """OLS fits carry ``design["convergence"] = {"converged": True,
    "boundary": False, "message": "OLS"}`` on every kind. The dict
    shape is the contract the engine and reporting layer consume."""
    v = _decreasing_assay_2batch()
    fits = fit_models(v)
    for kind, fit in fits.items():
        conv = fit.design.get("convergence")
        assert conv is not None, f"{kind.value}: missing convergence sub-block"
        assert conv == {
            "converged": True,
            "boundary": False,
            "message": "OLS",
        }, f"{kind.value}: unexpected convergence sub-block: {conv!r}"


def test_random_path_records_convergence_subblock() -> None:
    """Random-effects fits carry ``design["convergence"]`` with the
    three contract keys (``converged``, ``boundary``, ``message``).
    On a well-behaved 3-batch frame the POOLED model converges
    cleanly (no boundary, no convergence failure)."""
    v = _heteroscedastic_3batch()
    fits = fit_models(v, random_effects=True)
    for kind, fit in fits.items():
        conv = fit.design.get("convergence")
        assert conv is not None, f"{kind.value}: missing convergence sub-block"
        assert isinstance(conv, dict)
        assert set(conv.keys()) >= {"converged", "boundary", "message"}
        assert isinstance(conv["converged"], bool)
        assert isinstance(conv["boundary"], bool)
        assert isinstance(conv["message"], str)
    # The POOLED kind on a well-behaved 3-batch frame is the most
    # stable random-effects fit. It must report converged=True and
    # boundary=False. The COMMON_SLOPE / SEPARATE kinds can be
    # numerically marginal on this fixture (statsmodels can struggle
    # with the random-intercept estimate when the per-batch
    # intercepts are small) so we only assert on POOLED here.
    pooled_conv = fits[ModelKind.POOLED].design["convergence"]
    assert pooled_conv["converged"] is True
    assert pooled_conv["boundary"] is False
    assert "converged" in pooled_conv["message"].lower()


def test_random_path_detects_boundary_on_2_batch_frame() -> None:
    """With only 2 distinct batches and a near-perfect (identical)
    line, the random-effect variance may collapse or the
    residual-variance ratio may go to extremes; in any case the
    convergence sub-block must flag the fit as untrustworthy — either
    ``boundary=True`` or ``converged=False``.

    The 2-batch fixture in this test module uses IDENTICAL values
    for both batches (``value = 100.0 - 0.25 * t`` for every
    (batch, t) pair), so the random intercept is degenerate: the
    fit reduces to a fixed-effect OLS. Depending on the statsmodels
    version, the degenerate optimum is reported either as a boundary
    hit (``Group Var < 1e-10`` or ``Group Var / scale > 1e6``) or as
    an outright non-convergence. Both are valid "do not trust this
    random-effects fit" signals; what must NOT happen is a silent
    ``converged=True, boundary=False`` on a degenerate fixture.
    """
    v = _decreasing_assay_2batch()
    fits = fit_models(v, random_effects=True)
    pooled = fits[ModelKind.POOLED]
    conv = pooled.design.get("convergence")
    assert conv is not None
    # The POOLED model on a 2-batch identical-value fixture must be
    # flagged as problematic: boundary OR non-convergence.
    flagged = (conv["boundary"] is True) or (conv["converged"] is False)
    assert flagged, (
        f"expected boundary=True or converged=False on 2-batch "
        f"identical-value fixture; got conv={conv!r}; "
        f"random_effects={pooled.design.get('random_effects')!r}"
    )
    msg = conv["message"].lower()
    assert ("boundary" in msg) or ("converge" in msg), (
        f"message should mention 'boundary' or 'converge'; "
        f"got: {conv['message']!r}"
    )
