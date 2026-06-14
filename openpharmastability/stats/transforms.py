"""Transform-candidate evidence for OpenPharmaStability v0.3.0.

v0.3.0 keeps the official raw-scale linear model as the decision
model. This module computes independent candidate fits on the
supported candidate transforms ("none", "log", "sqrt") and records
metrics (AICc, residual SE, normality and homoscedasticity p-values)
for evidence only.

Math:
  - "none": fit y ~ t on the raw scale.
  - "log":  fit log(y) ~ t. Requires y > 0.
  - "sqrt": fit sqrt(y) ~ t. Requires y >= 0.

AICc (small-sample-corrected):
  n * ln(RSS / n) + 2k + (2k * (k + 1)) / (n - k - 1)
  where k = number of estimated parameters (2 for simple OLS).
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from statsmodels.stats.diagnostic import het_breuschpagan

from openpharmastability.contracts import (
    TransformAssessment,
    TransformCandidate,
)


_SUPPORTED = ("none", "log", "sqrt")


def _safe_log(y: np.ndarray) -> tuple[Optional[np.ndarray], Optional[str]]:
    if (y <= 0).any():
        return None, "log requires strictly positive values; data has zero or negative entries"
    return np.log(y), None


def _safe_sqrt(y: np.ndarray) -> tuple[Optional[np.ndarray], Optional[str]]:
    if (y < 0).any():
        return None, "sqrt requires non-negative values; data has negative entries"
    return np.sqrt(y), None


def _fit_one(t: np.ndarray, y: np.ndarray) -> dict:
    n = len(t)
    X = np.column_stack([np.ones(n), t])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    yhat = X @ beta
    resid = y - yhat
    p = 2
    df_resid = n - p
    if df_resid <= 0:
        return {"error": "df_resid <= 0; cannot fit"}
    sse = float((resid ** 2).sum())
    s_resid = float(np.sqrt(sse / df_resid))
    return {
        "beta0": float(beta[0]), "beta1": float(beta[1]),
        "s_resid": s_resid, "df_resid": int(df_resid), "sse": sse,
        "n": int(n), "resid": resid, "yhat": yhat,
    }


def _aicc(fit: dict, k: int = 2) -> Optional[float]:
    n = fit["n"]; sse = fit["sse"]
    if n <= k + 1 or sse <= 0:
        return None
    aic = n * math.log(sse / n) + 2 * k
    correction = (2 * k * (k + 1)) / (n - k - 1)
    return float(aic + correction)


def _normality_p(resid: np.ndarray) -> Optional[float]:
    n = len(resid)
    if n < 8:
        return None
    try:
        _, p = scipy_stats.shapiro(resid)
        return float(p)
    except Exception:
        return None


def _homoscedasticity_p(t: np.ndarray, resid: np.ndarray, yhat: np.ndarray) -> Optional[float]:
    n = len(resid)
    if n < 8:
        return None
    try:
        exog = np.column_stack([np.ones(n), yhat, t])
        if np.linalg.matrix_rank(exog) < exog.shape[1]:
            return None
        _, p_f, _, _ = het_breuschpagan(resid, exog)
        return float(p_f)
    except Exception:
        return None


def _assess_one(name: str, t: np.ndarray, y: np.ndarray) -> TransformCandidate:
    if name == "none":
        y_used, invalid = y, None
    elif name == "log":
        y_used, invalid = _safe_log(y)
    elif name == "sqrt":
        y_used, invalid = _safe_sqrt(y)
    else:
        return TransformCandidate(name=name, valid=False,
                                  invalid_reason=f"unknown transform {name!r}")
    if invalid is not None or y_used is None:
        return TransformCandidate(name=name, valid=False, invalid_reason=invalid)
    fit = _fit_one(t, y_used)
    if "error" in fit:
        return TransformCandidate(name=name, valid=False, invalid_reason=fit["error"])
    return TransformCandidate(
        name=name, valid=True, invalid_reason=None,
        aic=_aicc(fit), s_resid=fit["s_resid"],
        normality_p=_normality_p(fit["resid"]),
        homoscedasticity_p=_homoscedasticity_p(t, fit["resid"], fit["yhat"]),
    )


def assess_transforms(
    df: pd.DataFrame,
    attribute: Optional[str] = None,
    candidates: tuple[str, ...] = _SUPPORTED,
) -> TransformAssessment:
    """Assess candidate transforms for one attribute.

    Parameters
    ----------
    df:
        Data frame. If ``attribute`` is None, the frame is used as-is
        (assumes pre-filtered). If ``attribute`` is given, the frame is
        filtered to rows where ``df["attribute"] == attribute``.
    attribute:
        Optional filter.
    candidates:
        Tuple of candidate names. Default ("none", "log", "sqrt").

    Returns
    -------
    TransformAssessment. ``official_model_transform`` is always
    ``"none"`` in v0.3.0 — the official decision is raw-scale linear.
    ``recommendation`` is the valid candidate with the lowest AICc.
    """
    sub = df
    if attribute is not None and "attribute" in df.columns:
        sub = df[df["attribute"].astype(str) == str(attribute)]

    if {"batch", "time_months"}.issubset(sub.columns):
        sub = (sub.groupby(["batch", "time_months"], as_index=False)["value"]
               .mean())
    if "time_months" not in sub.columns or "value" not in sub.columns:
        return TransformAssessment(
            official_model_transform="none",
            candidates=[TransformCandidate(name=n, valid=False, invalid_reason="missing time_months/value")
                       for n in candidates],
            recommendation=None, recommendation_is_official=False,
        )

    t = sub["time_months"].to_numpy(dtype=float)
    y = sub["value"].to_numpy(dtype=float)
    mask = np.isfinite(t) & np.isfinite(y)
    t = t[mask]; y = y[mask]

    cand_results = [_assess_one(n, t, y) for n in candidates]
    valid_with_aic = [c for c in cand_results if c.valid and c.aic is not None]
    recommendation = min(valid_with_aic, key=lambda c: c.aic).name if valid_with_aic else None

    return TransformAssessment(
        official_model_transform="none",
        candidates=cand_results,
        recommendation=recommendation,
        recommendation_is_official=False,
    )


__all__ = ["assess_transforms", "_SUPPORTED"]
