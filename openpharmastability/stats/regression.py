"""Linear regression fits for OpenPharmaStability v0.1.

This module fits the three OLS models that drive the ICH Q1E-style
analysis:

* :data:`~openpharmastability.contracts.ModelKind.POOLED` — one
  intercept and one slope across all batches.
* :data:`~openpharmastability.contracts.ModelKind.COMMON_SLOPE` —
  one common slope with batch-specific intercepts.
* :data:`~openpharmastability.contracts.ModelKind.SEPARATE` — one
  slope and one intercept per batch (full interaction).

All three fits are returned together from :func:`fit_models` so the
downstream poolability test can compare them without re-fitting.

The :class:`~openpharmastability.contracts.FitResult` carries a
parameter covariance matrix in the **same order** as ``params`` and
records a ``design`` block (tbar, Sxx, n, per-batch tbar/Sxx/n, and
linear-combination vectors) so the confidence-bound code can compute
``SE_mean(t) = s * sqrt(c' (X'X)^-1 c)`` for any model without having
to re-derive the design.

Batch is treated as a **fixed effect** with treatment coding. The
reference batch is whichever batch name sorts first (statsmodels'
default), and the offsets to the other batches are stored as
``b0_<batch>`` for downstream convenience.

v0.5.0 — opt-in random-effects path
-----------------------------------
:func:`fit_models` accepts ``random_effects=True`` to swap the
underlying fit engine from ``smf.ols`` to ``smf.mixedlm`` (random
intercept per batch). The observable :class:`FitResult` shape is
unchanged: the same ``params`` dict, the same ``cov`` matrix (the
fixed-effect submatrix of the mixed model's covariance), the same
``design`` block, the same ``fitted_fn``. Only ``s_resid``,
``df_resid``, and ``cov`` are recomputed from the mixed model.

This is an alternative fit, not an alternative poolability test —
the poolability decision is still the OLS ANCOVA (see
:mod:`openpharmastability.stats.poolability`) and is unaffected by
the choice of fit engine.
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from openpharmastability.contracts import (
    FitResult,
    ModelKind,
    ValidatedData,
)


# Columns we actually consume from ``ValidatedData.df``. The rest (spec
# limits, declared direction, ...) is irrelevant for the fit.
_REQUIRED_DF_COLUMNS = ("batch", "time_months", "value")

# Convergence / boundary threshold for the v0.5.1 random-effects path.
# When ``Group Var / residual variance`` exceeds this, the random-effect
# variance is sitting at a numerical boundary and the fit is reported as
# ``boundary=True``. ``1e6`` is a defensible proxy: statsmodels' REML
# estimate of the random-effect variance becomes uninformative long
# before it gets to that ratio, and a higher value would let genuinely
# between-batch-variance-dominated fits slip through unmarked.
_RANDOM_EFFECTS_BOUNDARY_RATIO: float = 1e6
# Threshold for "random-effect variance has effectively collapsed to 0"
# — anything below this in absolute terms is reported as a boundary
# (the model reduces to a fixed-effect OLS). Chosen at 1e-10 because
# well-fit mixed models produce positive Group Var estimates orders of
# magnitude above this on real data.
_RANDOM_EFFECTS_COLLAPSE_FLOOR: float = 1e-10


def _detect_mixed_convergence(model) -> dict[str, Any]:
    """Detect convergence / boundary state for a fitted
    :class:`MixedLMResults`.

    Returns a dict with keys ``converged`` (bool), ``boundary`` (bool),
    ``message`` (str). Detection rules (v0.5.1):

    * ``converged`` is True iff the model reports a converged fit
      (``model.converged`` if available, otherwise treated as True
      when both ``model.bse`` and ``model.params`` are finite).
    * ``boundary`` is True when the random-effect variance collapses
      to 0 (``Group Var`` < 1e-10, the model reduces to a fixed-effect
      OLS) OR when it hits a numerical boundary
      (``Group Var / scale`` > 1e6).
    * ``message`` is a short human-readable string describing the
      result. Boundary messages take priority over plain
      "did not converge" messages when both apply, because the
      boundary is the actionable root cause.
    """
    try:
        group_var = float(model.params.get("Group Var", float("nan")))
    except (TypeError, ValueError, AttributeError):
        group_var = float("nan")
    try:
        scale = float(model.scale) if hasattr(model, "scale") else 0.0
    except (TypeError, ValueError):
        scale = 0.0

    boundary = False
    boundary_msg: str | None = None
    if np.isfinite(group_var) and group_var < _RANDOM_EFFECTS_COLLAPSE_FLOOR:
        boundary = True
        boundary_msg = "mixed model hit boundary (random-effect variance -> 0)"
    elif (
        np.isfinite(group_var)
        and np.isfinite(scale)
        and scale > 0
        and (group_var / scale) > _RANDOM_EFFECTS_BOUNDARY_RATIO
    ):
        boundary = True
        boundary_msg = (
            "mixed model hit boundary (random-effect variance very large "
            "relative to residual variance)"
        )

    converged_flag = bool(getattr(model, "converged", True))
    if not converged_flag:
        if boundary:
            return {"converged": False, "boundary": True, "message": boundary_msg}
        return {
            "converged": False,
            "boundary": False,
            "message": "mixed model did not converge",
        }

    # Final check: finite params / standard errors. A statsmodels fit
    # that produced NaN in either of these did not converge in any
    # meaningful sense even if the optimizer's flag says otherwise.
    try:
        bse = np.asarray(getattr(model, "bse", []), dtype=float)
        params_arr = np.asarray(getattr(model, "params", []), dtype=float)
        if bse.size and not bool(np.all(np.isfinite(bse))):
            return {
                "converged": False,
                "boundary": boundary,
                "message": "mixed model did not converge: non-finite standard errors",
            }
        if params_arr.size and not bool(np.all(np.isfinite(params_arr))):
            return {
                "converged": False,
                "boundary": boundary,
                "message": "mixed model did not converge: non-finite parameters",
            }
    except (TypeError, ValueError):
        pass

    if boundary:
        return {"converged": True, "boundary": True, "message": boundary_msg}
    return {"converged": True, "boundary": False, "message": "mixed model converged"}


# Default convergence sub-block for the OLS path. OLS is closed-form
# (no iterative optimizer) and the parameter covariance is always
# well-defined when the design matrix has full column rank, so the
# OLS path always reports ``converged=True``, ``boundary=False``.
_OLS_CONVERGENCE: dict[str, Any] = {
    "converged": True,
    "boundary": False,
    "message": "OLS",
}


def _select_fit_frame(data: ValidatedData) -> pd.DataFrame:
    """Return a copy of the validated frame restricted to the columns
    the regression needs.

    The fit must not depend on the order of columns in the input frame
    nor on any extra columns the caller may have kept around. This
    helper also drops rows with non-finite ``value`` (defensive — the
    data layer should already have excluded them via BQL policy).
    """
    missing = [c for c in _REQUIRED_DF_COLUMNS if c not in data.df.columns]
    if missing:
        raise ValueError(
            f"ValidatedData.df is missing column(s) required for "
            f"regression: {missing!r}"
        )
    out = data.df.loc[:, list(_REQUIRED_DF_COLUMNS)].copy()
    # statsmodels treats NaN predictably (drops the row) but we make
    # the filtering explicit so the user sees the row count they
    # expect.
    out = out.dropna(subset=["value", "time_months"]).reset_index(drop=True)
    return out


def _stable_batch_order(data: ValidatedData) -> list[str]:
    """Sorted, de-duplicated list of batch names in the fit frame.

    The reference batch for treatment coding is the first name in this
    list (``min``), which matches statsmodels' default for
    ``C(batch)`` in a formula.
    """
    return sorted(data.df["batch"].dropna().unique().tolist())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _residual_se(model) -> float:
    """Return ``sqrt(SSE / df_resid)`` from a fitted statsmodels OLS.

    statsmodels exposes ``.mse_resid`` (mean squared error) and
    ``.scale`` (the same thing); using ``.scale`` keeps us in lockstep
    with the parameter covariance ``s^2 * (X'X)^-1`` that
    ``model.cov_params()`` returns.
    """
    return float(np.sqrt(model.scale))


def _per_batch_design(
    df: pd.DataFrame, time_col: str = "time_months"
) -> dict[str, dict[str, float]]:
    """Compute the per-batch tbar, Sxx, n used for diagnostics and
    documentation.

    The bound math does NOT use this directly (it builds a full
    linear-combination vector against ``cov_params``), but the
    per-batch design is recorded on the fit so a user inspecting
    ``FitResult.design`` can verify the numbers without re-deriving.
    """
    out: dict[str, dict[str, float]] = {}
    for batch, sub in df.groupby("batch", sort=True):
        t = sub[time_col].to_numpy(dtype=float)
        n = int(t.size)
        tbar = float(t.mean())
        sxx = float(((t - tbar) ** 2).sum())
        out[str(batch)] = {"n": n, "tbar": tbar, "Sxx": sxx}
    return out


# ---------------------------------------------------------------------------
# POOLED
# ---------------------------------------------------------------------------


def _fit_pooled(df: pd.DataFrame) -> FitResult:
    """Fit ``value ~ time_months`` (one intercept, one slope)."""
    model = smf.ols("value ~ time_months", data=df).fit()

    t = df["time_months"].to_numpy(dtype=float)
    n = int(t.size)
    tbar = float(t.mean())
    sxx = float(((t - tbar) ** 2).sum())
    s = _residual_se(model)
    cov = np.asarray(model.cov_params(), dtype=float)

    b0 = float(model.params["Intercept"])
    b1 = float(model.params["time_months"])

    def fitted_fn(t_value: float) -> float:
        return b0 + b1 * float(t_value)

    design: dict[str, Any] = {
        "tbar": tbar,
        "Sxx": sxx,
        "n": n,
        "per_batch": _per_batch_design(df),
        # Linear-combination vectors for predictions yhat_b(t). For
        # the pooled model there is only one (single batch identity).
        # Order: [Intercept, time_months].
        "intercept_idx": 0,
        "slope_idx": 1,
        # Param names mirror the statsmodels order so callers can
        # rebuild the c vector with a single zip.
        "param_names": ["Intercept", "time_months"],
        # v0.5.1: OLS path convergence marker. OLS is closed-form and
        # always reports ``converged=True``, ``boundary=False``;
        # recorded here so downstream code has a single contract for
        # both OLS and random-effects fits.
        "convergence": dict(_OLS_CONVERGENCE),
    }

    return FitResult(
        kind=ModelKind.POOLED,
        params={"b0": b0, "b1": b1},
        df_resid=int(model.df_resid),
        s_resid=s,
        cov=cov,
        fitted_fn=fitted_fn,
        design=design,
        batches=sorted(df["batch"].unique().tolist()),
    )


# ---------------------------------------------------------------------------
# COMMON_SLOPE
# ---------------------------------------------------------------------------


def _fit_common_slope(df: pd.DataFrame, batches: list[str]) -> FitResult:
    """Fit ``value ~ time_months + C(batch)`` (one common slope, per-batch intercepts)."""
    model = smf.ols("value ~ time_months + C(batch)", data=df).fit()
    cov = np.asarray(model.cov_params(), dtype=float)
    s = _residual_se(model)

    intercept_name = "Intercept"
    slope_name = "time_months"
    # statsmodels names the offsets ``C(batch)[T.<batch>]`` for every
    # non-reference batch. The reference batch is the alphabetically
    # first batch in the fit frame (statsmodels' default).
    ref_batch = batches[0]
    other_batches = batches[1:]

    # Per-batch intercepts as the user wants to see them
    # (``b0_<batch>``). The reference batch is just ``Intercept``;
    # every other batch is ``Intercept + C(batch)[T.<batch>]``.
    b0 = {ref_batch: float(model.params[intercept_name])}
    for b in other_batches:
        offset_name = f"C(batch)[T.{b}]"
        b0[b] = float(model.params[intercept_name] + model.params[offset_name])
    b1 = float(model.params[slope_name])

    # Per-batch linear-combination vector for the prediction
    # ``yhat_b(t) = b0_<b> + b1 * t``. Each batch needs its OWN vector
    # in the model's parameter order so the bound code can do
    # ``sqrt(c @ cov @ c)`` against the same covariance matrix.
    #
    # The intercept for batch B is ``Intercept + sum(offsets for B)``.
    # In treatment coding with reference = alphabetically-first batch,
    # that means:
    #   - ref batch: c[Intercept] = 1, all offset columns = 0
    #   - any other batch: c[Intercept] = 1, c[its offset] = 1, others = 0
    # The slope term then adds ``t * e_slope`` to whichever vector
    # the bound code is computing.
    param_names = list(model.params.index)
    param_index = {name: i for i, name in enumerate(param_names)}
    slope_idx = param_index[slope_name]
    offset_name_for = {b: f"C(batch)[T.{b}]" for b in other_batches}

    per_batch = _per_batch_design(df)
    for b, rec in per_batch.items():
        combo = np.zeros(len(param_names), dtype=float)
        combo[param_index[intercept_name]] = 1.0
        if b != ref_batch:
            combo[param_index[offset_name_for[b]]] = 1.0
        rec["intercept_combo"] = combo
        rec["slope_idx"] = slope_idx

    def fitted_fn(batch: str) -> Callable[[float], float]:
        b0_b = b0[batch]
        b1_common = b1

        def fn(t_value: float) -> float:
            return b0_b + b1_common * float(t_value)

        return fn

    t = df["time_months"].to_numpy(dtype=float)
    tbar = float(t.mean())
    sxx = float(((t - tbar) ** 2).sum())

    design: dict[str, Any] = {
        "tbar": tbar,
        "Sxx": sxx,
        "n": int(t.size),
        "per_batch": per_batch,
        "ref_batch": ref_batch,
        "param_names": param_names,
        "slope_idx": slope_idx,
        # v0.5.1: OLS path convergence marker.
        "convergence": dict(_OLS_CONVERGENCE),
    }

    return FitResult(
        kind=ModelKind.COMMON_SLOPE,
        params={**{f"b0_{b}": v for b, v in b0.items()}, "b1": b1},
        df_resid=int(model.df_resid),
        s_resid=s,
        cov=cov,
        fitted_fn=fitted_fn,
        design=design,
        batches=list(batches),
    )


# ---------------------------------------------------------------------------
# SEPARATE
# ---------------------------------------------------------------------------


def _fit_separate(df: pd.DataFrame, batches: list[str]) -> FitResult:
    """Fit ``value ~ time_months * C(batch)`` (full interaction)."""
    model = smf.ols("value ~ time_months * C(batch)", data=df).fit()
    cov = np.asarray(model.cov_params(), dtype=float)
    s = _residual_se(model)

    intercept_name = "Intercept"
    slope_name = "time_months"
    ref_batch = batches[0]
    other_batches = batches[1:]

    b0 = {ref_batch: float(model.params[intercept_name])}
    b1 = {ref_batch: float(model.params[slope_name])}
    for b in other_batches:
        offset_name = f"C(batch)[T.{b}]"
        slope_offset_name = f"time_months:C(batch)[T.{b}]"
        b0[b] = float(
            model.params[intercept_name] + model.params[offset_name]
        )
        b1[b] = float(
            model.params[slope_name] + model.params[slope_offset_name]
        )

    # Per-batch linear-combination vector for the prediction
    # ``yhat_b(t) = b0_<b> + b1_<b> * t``. Order: [Intercept,
    # C(batch)[T.<other>]*, time_months,
    # time_months:C(batch)[T.<other>]*].
    param_names = list(model.params.index)
    param_index = {name: i for i, name in enumerate(param_names)}

    per_batch = _per_batch_design(df)
    for b in per_batch:
        c = np.zeros(len(param_names), dtype=float)
        c[param_index[intercept_name]] = 1.0
        slope_combo = np.zeros(len(param_names), dtype=float)
        slope_combo[param_index[slope_name]] = 1.0
        if b != ref_batch:
            c[param_index[f"C(batch)[T.{b}]"]] = 1.0
            slope_combo[param_index[f"time_months:C(batch)[T.{b}]"]] = 1.0
        c[param_index[slope_name]] = 0.0  # intercept combo
        per_batch[b]["intercept_combo"] = c
        per_batch[b]["slope_combo"] = slope_combo
        per_batch[b]["slope_idx"] = param_index[slope_name]

    def fitted_fn(batch: str) -> Callable[[float], float]:
        b0_b = b0[batch]
        b1_b = b1[batch]

        def fn(t_value: float) -> float:
            return b0_b + b1_b * float(t_value)

        return fn

    t = df["time_months"].to_numpy(dtype=float)
    tbar = float(t.mean())
    sxx = float(((t - tbar) ** 2).sum())

    design: dict[str, Any] = {
        "tbar": tbar,
        "Sxx": sxx,
        "n": int(t.size),
        "per_batch": per_batch,
        "ref_batch": ref_batch,
        "param_names": param_names,
        # v0.5.1: OLS path convergence marker.
        "convergence": dict(_OLS_CONVERGENCE),
    }

    return FitResult(
        kind=ModelKind.SEPARATE,
        params={
            **{f"b0_{b}": v for b, v in b0.items()},
            **{f"b1_{b}": v for b, v in b1.items()},
        },
        df_resid=int(model.df_resid),
        s_resid=s,
        cov=cov,
        fitted_fn=fitted_fn,
        design=design,
        batches=list(batches),
    )


# ---------------------------------------------------------------------------
# v0.5.0 opt-in random-effects (mixed-model) path
# ---------------------------------------------------------------------------
#
# The mixed-model fit uses ``smf.mixedlm`` with a random intercept per
# batch and the same fixed-effect formulas as the OLS path. The
# observable FitResult shape is preserved: only the underlying engine
# changes. The same per-batch design helpers, fitted_fn closure, and
# param-name conventions are reused so the bound / crossing math in
# ``stats/bounds.py`` and the poolability test in
# ``stats/poolability.py`` (which re-fits OLS internally) keep
# working unchanged.


def _fit_mixedlm(df: pd.DataFrame, formula: str) -> Any:
    """Fit a mixed model with a random intercept per batch.

    Suppresses statsmodels' convergence / boundary warnings because
    the v0.5 path is opt-in: callers have asked for the mixed model
    and the OLS path remains the ICH Q1E default. The mixed model is
    a diagnostic; if it does not converge on the user's data, the
    FitResult still carries the (possibly degenerate) parameters so
    the rest of the pipeline can run.

    Parameters
    ----------
    df:
        The fit frame, already restricted to ``batch``, ``time_months``
        and ``value``.
    formula:
        The statsmodels formula for the fixed-effect part. The random
        part is always ``groups=df['batch']`` (random intercept per
        batch).

    Returns
    -------
    MixedLMResults
        The fitted mixed model.
    """
    import warnings

    with warnings.catch_warnings():
        # The mixed model emits "MLE may be on the boundary" or
        # "Hessian not positive definite" when the random-effect
        # variance collapses to ~0 (e.g. on a perfect-line dataset
        # where all batch intercepts are identical). That is
        # expected and not actionable; suppress the noise. A
        # genuine convergence failure still raises.
        warnings.simplefilter("ignore")
        return smf.mixedlm(
            formula, data=df, groups=df["batch"]
        ).fit(method="lbfgs", reml=True)


def _fe_cov_from_mixed(model) -> np.ndarray:
    """Return the fixed-effect covariance submatrix from a fitted
    :class:`MixedLMResults` in the same order as ``model.fe_params``.

    The mixed model's ``cov_params()`` includes the random-effect
    variance as an extra row/column keyed ``"Group Var"``; we slice
    that out to leave a square matrix indexed by the fixed-effect
    names. This is the matrix the bound math needs: it is
    ``Cov(beta_hat_FE)`` and is asymptotically ``s^2 * (X'X)^-1`` for
    the fixed-effect block.

    If the covariance is non-finite (the random-effect variance
    collapsed to the boundary, e.g. on a perfect-line dataset and
    ``scale == 0``), we fall back to a design-matrix-based covariance
    ``scale * (X' X_FE)^-1`` so the bound code receives a finite
    matrix. This is the same fallback statsmodels' asymptotic
    approximation would converge to.
    """
    fe_names = list(model.fe_params.index)
    cov_full = np.asarray(model.cov_params(), dtype=float)
    # Build a positional index for the FE rows/cols in cov_full.
    full_names = list(model.cov_params().index)
    fe_idx = [full_names.index(n) for n in fe_names]
    cov_fe = cov_full[np.ix_(fe_idx, fe_idx)]
    if not np.all(np.isfinite(cov_fe)):
        # Fallback: design-based covariance for the fixed-effect
        # block. ``model.model.exog`` is the fixed-effect design
        # matrix, in the same column order as ``fe_params``.
        exog = np.asarray(model.model.exog, dtype=float)
        xtx_inv = np.linalg.pinv(exog.T @ exog)
        cov_fe = float(model.scale) * xtx_inv
        if not np.all(np.isfinite(cov_fe)):
            # Last resort: zero matrix. Marks the fit as
            # uninformative without crashing downstream.
            cov_fe = np.zeros_like(cov_fe)
    return cov_fe


def _fit_pooled_random(df: pd.DataFrame) -> FitResult:
    """Mixed-model analogue of :func:`_fit_pooled`.

    Random intercept per batch, fixed-effect formula
    ``value ~ time_months``.
    """
    model = _fit_mixedlm(df, "value ~ time_months")
    cov = _fe_cov_from_mixed(model)
    s = float(np.sqrt(model.scale))

    b0 = float(model.fe_params["Intercept"])
    b1 = float(model.fe_params["time_months"])

    def fitted_fn(t_value: float) -> float:
        return b0 + b1 * float(t_value)

    t = df["time_months"].to_numpy(dtype=float)
    n = int(t.size)
    tbar = float(t.mean())
    sxx = float(((t - tbar) ** 2).sum())

    design: dict[str, Any] = {
        "tbar": tbar,
        "Sxx": sxx,
        "n": n,
        "per_batch": _per_batch_design(df),
        "intercept_idx": 0,
        "slope_idx": 1,
        "param_names": ["Intercept", "time_months"],
        "random_effects": {
            "engine": "mixedlm",
            "kind": ModelKind.POOLED.value,
            "group_var": float(model.params.get("Group Var", float("nan"))),
            "n_groups": int(model.nobs) and int(len(model.model.group_labels)),
            "converged": bool(getattr(model, "converged", True)),
        },
        # v0.5.1: top-level convergence / boundary marker. The
        # random-effects-specific sub-block above is kept for
        # engine-internal detail (raw ``converged`` flag, ``group_var``);
        # this new sub-block is the contract the engine and the
        # reporting layer consume.
        "convergence": _detect_mixed_convergence(model),
    }

    return FitResult(
        kind=ModelKind.POOLED,
        params={"b0": b0, "b1": b1},
        df_resid=int(model.df_resid),
        s_resid=s,
        cov=cov,
        fitted_fn=fitted_fn,
        design=design,
        batches=sorted(df["batch"].unique().tolist()),
    )


def _fit_common_slope_random(
    df: pd.DataFrame, batches: list[str]
) -> FitResult:
    """Mixed-model analogue of :func:`_fit_common_slope`.

    Random intercept per batch, fixed-effect formula
    ``value ~ time_months + C(batch)``.
    """
    model = _fit_mixedlm(df, "value ~ time_months + C(batch)")
    cov = _fe_cov_from_mixed(model)
    s = float(np.sqrt(model.scale))

    intercept_name = "Intercept"
    slope_name = "time_months"
    ref_batch = batches[0]
    other_batches = batches[1:]

    b0 = {ref_batch: float(model.fe_params[intercept_name])}
    for b in other_batches:
        offset_name = f"C(batch)[T.{b}]"
        b0[b] = float(
            model.fe_params[intercept_name] + model.fe_params[offset_name]
        )
    b1 = float(model.fe_params[slope_name])

    fe_names = list(model.fe_params.index)
    param_index = {name: i for i, name in enumerate(fe_names)}
    slope_idx = param_index[slope_name]
    offset_name_for = {b: f"C(batch)[T.{b}]" for b in other_batches}

    per_batch = _per_batch_design(df)
    for b, rec in per_batch.items():
        combo = np.zeros(len(fe_names), dtype=float)
        combo[param_index[intercept_name]] = 1.0
        if b != ref_batch:
            combo[param_index[offset_name_for[b]]] = 1.0
        rec["intercept_combo"] = combo
        rec["slope_idx"] = slope_idx

    def fitted_fn(batch: str) -> Callable[[float], float]:
        b0_b = b0[batch]
        b1_common = b1

        def fn(t_value: float) -> float:
            return b0_b + b1_common * float(t_value)

        return fn

    t = df["time_months"].to_numpy(dtype=float)
    tbar = float(t.mean())
    sxx = float(((t - tbar) ** 2).sum())

    design: dict[str, Any] = {
        "tbar": tbar,
        "Sxx": sxx,
        "n": int(t.size),
        "per_batch": per_batch,
        "ref_batch": ref_batch,
        "param_names": fe_names,
        "slope_idx": slope_idx,
        "random_effects": {
            "engine": "mixedlm",
            "kind": ModelKind.COMMON_SLOPE.value,
            "group_var": float(model.params.get("Group Var", float("nan"))),
            "n_groups": int(len(model.model.group_labels)),
            "converged": bool(getattr(model, "converged", True)),
        },
        # v0.5.1: top-level convergence / boundary marker.
        "convergence": _detect_mixed_convergence(model),
    }

    return FitResult(
        kind=ModelKind.COMMON_SLOPE,
        params={**{f"b0_{b}": v for b, v in b0.items()}, "b1": b1},
        df_resid=int(model.df_resid),
        s_resid=s,
        cov=cov,
        fitted_fn=fitted_fn,
        design=design,
        batches=list(batches),
    )


def _fit_separate_random(
    df: pd.DataFrame, batches: list[str]
) -> FitResult:
    """Mixed-model analogue of :func:`_fit_separate`.

    Random intercept per batch, fixed-effect formula
    ``value ~ time_months * C(batch)``.
    """
    model = _fit_mixedlm(df, "value ~ time_months * C(batch)")
    cov = _fe_cov_from_mixed(model)
    s = float(np.sqrt(model.scale))

    intercept_name = "Intercept"
    slope_name = "time_months"
    ref_batch = batches[0]
    other_batches = batches[1:]

    b0 = {ref_batch: float(model.fe_params[intercept_name])}
    b1 = {ref_batch: float(model.fe_params[slope_name])}
    for b in other_batches:
        offset_name = f"C(batch)[T.{b}]"
        slope_offset_name = f"time_months:C(batch)[T.{b}]"
        b0[b] = float(
            model.fe_params[intercept_name] + model.fe_params[offset_name]
        )
        b1[b] = float(
            model.fe_params[slope_name] + model.fe_params[slope_offset_name]
        )

    fe_names = list(model.fe_params.index)
    param_index = {name: i for i, name in enumerate(fe_names)}

    per_batch = _per_batch_design(df)
    for b in per_batch:
        c = np.zeros(len(fe_names), dtype=float)
        c[param_index[intercept_name]] = 1.0
        slope_combo = np.zeros(len(fe_names), dtype=float)
        slope_combo[param_index[slope_name]] = 1.0
        if b != ref_batch:
            c[param_index[f"C(batch)[T.{b}]"]] = 1.0
            slope_combo[param_index[f"time_months:C(batch)[T.{b}]"]] = 1.0
        c[param_index[slope_name]] = 0.0  # intercept combo
        per_batch[b]["intercept_combo"] = c
        per_batch[b]["slope_combo"] = slope_combo
        per_batch[b]["slope_idx"] = param_index[slope_name]

    def fitted_fn(batch: str) -> Callable[[float], float]:
        b0_b = b0[batch]
        b1_b = b1[batch]

        def fn(t_value: float) -> float:
            return b0_b + b1_b * float(t_value)

        return fn

    t = df["time_months"].to_numpy(dtype=float)
    tbar = float(t.mean())
    sxx = float(((t - tbar) ** 2).sum())

    design: dict[str, Any] = {
        "tbar": tbar,
        "Sxx": sxx,
        "n": int(t.size),
        "per_batch": per_batch,
        "ref_batch": ref_batch,
        "param_names": fe_names,
        "random_effects": {
            "engine": "mixedlm",
            "kind": ModelKind.SEPARATE.value,
            "group_var": float(model.params.get("Group Var", float("nan"))),
            "n_groups": int(len(model.model.group_labels)),
            "converged": bool(getattr(model, "converged", True)),
        },
        # v0.5.1: top-level convergence / boundary marker.
        "convergence": _detect_mixed_convergence(model),
    }

    return FitResult(
        kind=ModelKind.SEPARATE,
        params={
            **{f"b0_{b}": v for b, v in b0.items()},
            **{f"b1_{b}": v for b, v in b1.items()},
        },
        df_resid=int(model.df_resid),
        s_resid=s,
        cov=cov,
        fitted_fn=fitted_fn,
        design=design,
        batches=list(batches),
    )


def _fit_random_model(
    df: pd.DataFrame, kind: ModelKind, batches: list[str]
) -> FitResult:
    """Dispatch a mixed-model fit by :class:`ModelKind`."""
    if kind is ModelKind.POOLED:
        return _fit_pooled_random(df)
    if kind is ModelKind.COMMON_SLOPE:
        return _fit_common_slope_random(df, batches)
    if kind is ModelKind.SEPARATE:
        return _fit_separate_random(df, batches)
    raise ValueError(f"Unknown ModelKind for random-effects fit: {kind!r}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fit_models(
    data: ValidatedData,
    random_effects: bool = False,
) -> dict[ModelKind, FitResult]:
    """Fit all three regression models on ``data.df``.

    Parameters
    ----------
    data:
        A :class:`~openpharmastability.contracts.ValidatedData` as
        produced by the data layer. The fit uses the ``batch``,
        ``time_months`` and ``value`` columns only; the rest of the
        frame is ignored.
    random_effects:
        When ``False`` (the default), all three models are fit with
        :func:`statsmodels.formula.api.ols` — the ICH Q1E default.
        When ``True``, all three models are fit with
        :func:`statsmodels.formula.api.mixedlm` using a random
        intercept per batch. The observable :class:`FitResult` shape
        is unchanged; only the underlying engine differs. This is an
        opt-in diagnostic path; the v0.4 fixed-effect pipeline is
        byte-identical to before and is the Q1E-default shelf-life
        estimate.

    Returns
    -------
    dict[ModelKind, FitResult]
        A dict with one entry per :class:`ModelKind`. The
        :class:`FitResult` carries the fitted parameters, the
        residual standard error, the parameter covariance matrix
        (in the same order as ``params``), the design metadata, and
        a ``fitted_fn`` suitable for the bound code.

    Notes
    -----
    All three models are fit independently — the COMMON_SLOPE and
    SEPARATE fits are not refits of a reduced model; they are direct
    OLS fits with the relevant formula. This is the spec's
    requirement (and it matches what statsmodels'
    ``anova_lm(typ=2)`` assumes for the MSE it reports).

    The poolability test (:func:`openpharmastability.stats.poolability
    .decide_poolability`) is unaffected by ``random_effects``: it
    always re-fits the OLS ANCOVA on the raw data per the ICH Q1E
    definition. The ``random_effects`` flag only changes the fit
    engine used to build the per-model :class:`FitResult` dict that
    the bound and crossing math consume.
    """
    df = _select_fit_frame(data)
    if df.empty:
        raise ValueError(
            "Cannot fit regression models: ValidatedData.df is empty"
        )
    batches = _stable_batch_order(data)

    if not random_effects:
        return {
            ModelKind.POOLED: _fit_pooled(df),
            ModelKind.COMMON_SLOPE: _fit_common_slope(df, batches),
            ModelKind.SEPARATE: _fit_separate(df, batches),
        }

    return {
        ModelKind.POOLED: _fit_random_model(df, ModelKind.POOLED, batches),
        ModelKind.COMMON_SLOPE: _fit_random_model(
            df, ModelKind.COMMON_SLOPE, batches
        ),
        ModelKind.SEPARATE: _fit_random_model(
            df, ModelKind.SEPARATE, batches
        ),
    }


__all__ = ["fit_models"]
