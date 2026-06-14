"""Regenerate ``examples/assay_3batch.expected.json`` from the dataset.

This script is the source of truth for the frozen expected values. It
uses plain numpy + scipy.stats.t + scipy.optimize.brentq and does
**not** import the project's own stats code — the point is that the
expected values can be regenerated independently by anyone with the
dataset and a Python interpreter, and any drift in the engine's
output against this file is a real regression.

Run from the project root:

    python tools/regen_expected.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.optimize import brentq
from scipy.stats import t as student_t

SEED = 20260113
TIME_POINTS = [0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0]


def _build_dataset() -> pd.DataFrame:
    """Regenerate the 3-batch dataset deterministically (must match the
    hand-written CSV in ``examples/assay_3batch.csv``)."""
    rng = np.random.default_rng(SEED)
    rows = []
    for batch, b0 in (("B1", 100.0), ("B2", 99.0), ("B3", 101.0)):
        for t in TIME_POINTS:
            for _rep in (1, 2):
                v = b0 - 0.5 * t + float(rng.normal(0.0, 0.3))
                rows.append({
                    "batch": batch, "condition": "25C/60RH",
                    "time_months": t, "attribute": "assay",
                    "value": round(v, 4),
                    "lower_spec": 90.0, "upper_spec": 110.0,
                    "direction": "decreasing",
                })
    return pd.DataFrame(rows)


def _pooled_expected(df: pd.DataFrame) -> dict:
    t = df["time_months"].to_numpy()
    y = df["value"].to_numpy()
    X = np.column_stack([np.ones_like(t), t])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    b0, b1 = float(beta[0]), float(beta[1])
    resid = y - X @ beta
    n, p = len(y), 2
    df_resid = n - p
    sse = float((resid ** 2).sum())
    s = float(np.sqrt(sse / df_resid))
    tbar = float(t.mean())
    sxx = float(((t - tbar) ** 2).sum())
    k_95 = float(student_t.ppf(0.95, df_resid))

    def bound(t_val: float) -> float:
        yh = b0 + b1 * t_val
        se = s * np.sqrt(1.0 / n + (t_val - tbar) ** 2 / sxx)
        return yh - k_95 * se

    cross = float(brentq(
        lambda x: bound(x) - 90.0, 0.0, 60.0, xtol=1e-10, rtol=1e-12,
    ))
    return {
        "b0": b0, "b1": b1, "s_resid": s, "df_resid": df_resid,
        "tbar": tbar, "Sxx": sxx, "n": n,
        "t_multiplier_one_sided_95": k_95,
        "yhat_at_tbar": b0 + b1 * tbar,
        "bound_at_tbar": float(bound(tbar)),
        "bound_at_t24": float(bound(24.0)),
        "crossing_lower_spec_90_months": cross,
        "supported_shelf_life_rounded_down": int(np.floor(cross)),
    }


def _common_slope_expected(df: pd.DataFrame) -> dict:
    """The model the engine actually selects on this dataset
    (poolability=PARTIAL). Uses per-batch c-vectors built from
    the parameter name list, NOT from the project's stats code."""
    m = smf.ols("value ~ time_months + C(batch)", data=df).fit()
    cov = m.cov_params().values
    param_names = list(m.params.index)
    pn_idx = {n: i for i, n in enumerate(param_names)}
    slope_idx = pn_idx["time_months"]
    k_95 = float(student_t.ppf(0.95, m.df_resid))
    batches = sorted(df["batch"].unique())
    ref = batches[0]

    # Per-batch b0 in user-facing form
    b0 = {ref: float(m.params["Intercept"])}
    for b in batches[1:]:
        b0[b] = float(m.params["Intercept"] + m.params[f"C(batch)[T.{b}]"])
    b1 = float(m.params["time_months"])

    def c_for(batch: str, t_val: float) -> np.ndarray:
        c = np.zeros(len(param_names), dtype=float)
        c[pn_idx["Intercept"]] = 1.0
        if batch != ref:
            c[pn_idx[f"C(batch)[T.{batch}]"]] = 1.0
        c[slope_idx] = t_val
        return c

    per_batch: dict[str, dict] = {}
    for b in batches:
        per_batch[b] = {
            "b0": b0[b],
            "b1_common": b1,
            "s_resid": float(np.sqrt(m.scale)),
            "df_resid": int(m.df_resid),
        }

    # Per-batch crossings of the one-sided 95% lower bound against 90.
    crossings: dict[str, float | None] = {}
    bound_at_t12: dict[str, float] = {}
    for b in batches:
        def bound_b(t_val: float, _b: str = b) -> float:
            yh = b0[_b] + b1 * t_val
            c = c_for(_b, t_val)
            se = float(np.sqrt(c @ cov @ c))
            return yh - k_95 * se
        bound_at_t12[b] = bound_b(12.0)
        f_lo, f_hi = bound_b(0.0) - 90.0, bound_b(60.0) - 90.0
        if f_lo * f_hi < 0:
            crossings[b] = float(brentq(
                lambda x, _b=b: bound_b(x) - 90.0, 0.0, 60.0, xtol=1e-10,
            ))
        else:
            crossings[b] = None

    worst = min((b for b, c in crossings.items() if c is not None),
                key=lambda b: crossings[b])
    return {
        "b1_common": b1,
        "s_resid": float(np.sqrt(m.scale)),
        "df_resid": int(m.df_resid),
        "param_names": param_names,
        "per_batch": per_batch,
        "bound_at_t12": bound_at_t12,
        "per_batch_crossings_lower_spec_90_months": crossings,
        "worst_case_batch": worst,
        "worst_case_crossing_months": crossings[worst],
        "supported_shelf_life_rounded_down":
            int(np.floor(crossings[worst])) if crossings[worst] is not None else None,
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if argv and argv[0] == "--check":
        # CI mode: regenerate, compare, exit non-zero on drift.
        here = pathlib.Path(__file__).resolve().parent
        csv = here.parent / "examples" / "assay_3batch.csv"
        target = here.parent / "examples" / "assay_3batch.expected.json"
        df = _build_dataset()
        # If the on-disk CSV is different from the regenerated one,
        # the expected.json refers to a different dataset — fail loudly.
        on_disk = pd.read_csv(csv)
        if not df.equals(on_disk):
            print(
                "ERROR: regenerated dataset differs from "
                f"{csv}. Run the script WITHOUT --check to rewrite "
                "examples/assay_3batch.csv, then re-run --check."
            )
            return 2
        new = _build_expected(df)
        with open(target) as f:
            old = json.load(f)
        if new == old:
            print(f"{target} matches regenerated values.")
            return 0
        print(f"{target} DIFFERS from regenerated values:")
        for k in sorted(set(new) | set(old)):
            if new.get(k) != old.get(k):
                print(f"  {k}:")
                print(f"    old: {old.get(k)!r}")
                print(f"    new: {new.get(k)!r}")
        return 1
    here = pathlib.Path(__file__).resolve().parent
    df = _build_dataset()
    new = _build_expected(df)
    csv = here.parent / "examples" / "assay_3batch.csv"
    target = here.parent / "examples" / "assay_3batch.expected.json"
    df.to_csv(csv, index=False)
    with open(target, "w") as f:
        json.dump(new, f, indent=2)
    print(f"Wrote {csv} ({len(df)} rows)")
    print(f"Wrote {target}")
    print(f"Worst-case crossing (COMMON_SLOPE): "
          f"{new['common_slope_fit']['worst_case_batch']} @ "
          f"{new['common_slope_fit']['worst_case_crossing_months']:.6f} months")
    print(f"Supported shelf life: "
          f"{new['common_slope_fit']['supported_shelf_life_rounded_down']} months")
    return 0


def _build_expected(df: pd.DataFrame) -> dict:
    pooled = _pooled_expected(df)
    cs = _common_slope_expected(df)
    return {
        "_comment": (
            "Independent expected values for examples/assay_3batch.csv. "
            "Computed with plain numpy + scipy.stats.t + scipy.optimize.brentq. "
            "Regenerate with: python tools/regen_expected.py. "
            "Verify with:    python tools/regen_expected.py --check."
        ),
        "regen_seed": SEED,
        "n_observations": int(len(df)),
        "n_batches": int(df["batch"].nunique()),
        "time_points": TIME_POINTS,
        "condition": "25C/60RH",
        "attribute": "assay",
        "direction": "decreasing",
        "lower_spec": 90.0,
        "upper_spec": 110.0,
        "poolability_alpha": 0.25,
        "pooled_fit": pooled,
        "common_slope_fit": cs,
        "shelf_life": {
            "statistical_crossing_months": cs["worst_case_crossing_months"],
            "supported_shelf_life_months_rounded_down":
                cs["supported_shelf_life_rounded_down"],
            "observed_data_months": 24.0,
            "extrapolation_flag":
                cs["supported_shelf_life_rounded_down"] is not None
                and cs["supported_shelf_life_rounded_down"] > 24.0,
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
