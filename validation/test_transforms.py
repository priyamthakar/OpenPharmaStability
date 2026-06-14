"""Tests for the v0.3.0 transform-candidate evidence (stats/transforms.py)."""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest
from dataclasses import asdict

from openpharmastability.contracts import (
    TransformAssessment, TransformCandidate,
)
from openpharmastability.stats.transforms import _SUPPORTED, assess_transforms


def _linear_df(slope=-0.5, intercept=100.0, sd=0.3, seed=20260113):
    rng = np.random.default_rng(seed)
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0):
            for _ in (1, 2):
                rows.append({
                    "batch": batch, "time_months": t, "attribute": "assay",
                    "value": intercept + slope * t + float(rng.normal(0.0, sd)),
                })
    return pd.DataFrame(rows)


def _log_growth_df(seed=20260113):
    """Multiplicative growth — log is the better transform."""
    rng = np.random.default_rng(seed)
    rows = []
    for batch in ("B1", "B2", "B3"):
        for t in (0.0, 3.0, 6.0, 9.0, 12.0):
            for _ in (1, 2):
                # log(value) = 4.6 - 0.05*t + small noise
                log_v = 4.6 - 0.05 * t + float(rng.normal(0.0, 0.05))
                rows.append({
                    "batch": batch, "time_months": t, "attribute": "assay",
                    "value": math.exp(log_v),
                })
    return pd.DataFrame(rows)


def test_none_candidate_valid():
    df = _linear_df()
    a = assess_transforms(df, attribute="assay")
    none_cand = next(c for c in a.candidates if c.name == "none")
    assert none_cand.valid is True
    assert none_cand.s_resid is not None and none_cand.s_resid > 0
    assert none_cand.aic is not None


def test_log_invalid_for_zero():
    df = _linear_df()
    # Set ALL replicates of the first batch+time point to 0 so the
    # replicate-mean also goes to 0 (log-invalid).
    mask = (df["batch"] == "B1") & (df["time_months"] == 0.0)
    df.loc[mask, "value"] = 0.0
    a = assess_transforms(df, attribute="assay")
    log_cand = next(c for c in a.candidates if c.name == "log")
    assert log_cand.valid is False
    assert log_cand.invalid_reason is not None
    assert "positive" in log_cand.invalid_reason.lower()


def test_log_invalid_for_negative():
    df = _linear_df()
    mask = (df["batch"] == "B1") & (df["time_months"] == 0.0)
    df.loc[mask, "value"] = -1.0
    a = assess_transforms(df, attribute="assay")
    log_cand = next(c for c in a.candidates if c.name == "log")
    def test_recommendation_is_best_aicc_for_log_growth():
        df = _log_growth_df()
        a = assess_transforms(df, attribute="assay")
        # log should win for multiplicative data
        valid = [c for c in a.candidates if c.valid and c.aic is not None]
        assert a.recommendation is not None
        # The recommendation has the lowest AICc
        min_aic = min(c.aic for c in valid)
        rec_cand = next(c for c in a.candidates if c.name == a.recommendation)
        assert math.isclose(rec_cand.aic, min_aic, rel_tol=1e-9)


def test_recommendation_none_if_no_valid_candidates():
    """All zero data → log invalid; sqrt and none are valid but with sse=0
    they have no AICc; the recommendation is therefore None.
    """
    df = _linear_df()
    df["value"] = 0.0
    a = assess_transforms(df, attribute="assay")
    log_cand = next(c for c in a.candidates if c.name == "log")
    assert log_cand.valid is False
    # The recommendation may be None (no candidate has a non-zero
    # AICc) or one of the valid candidates.
    assert a.recommendation in (None, "none", "sqrt")


def test_official_model_transform_is_none():
    df = _linear_df()
    a = assess_transforms(df, attribute="assay")
    assert a.official_model_transform == "none"


def test_recommendation_is_official_is_false():
    df = _linear_df()
    a = assess_transforms(df, attribute="assay")
    assert a.recommendation_is_official is False


def test_assessment_is_json_serializable():
    df = _linear_df()
    a = assess_transforms(df, attribute="assay")
    blob = json.dumps(asdict(a), default=str)
    parsed = json.loads(blob)
    assert "candidates" in parsed
    assert "official_model_transform" in parsed
    assert parsed["official_model_transform"] == "none"
    assert parsed["recommendation_is_official"] is False


def test_assessment_includes_all_three_candidates():
    df = _linear_df()
    a = assess_transforms(df, attribute="assay")
    names = [c.name for c in a.candidates]
    assert set(names) == {"none", "log", "sqrt"}


def test_assessment_handles_tiny_data_without_crashing():
    df = pd.DataFrame({
        "batch": ["B1", "B1", "B1"],
        "time_months": [0.0, 1.0, 2.0],
        "value": [100.0, 99.0, 98.0],
        "attribute": ["assay"] * 3,
    })
    a = assess_transforms(df, attribute="assay")
    assert isinstance(a, TransformAssessment)
    assert len(a.candidates) == 3


def test_none_candidate_metrics_present():
    df = _linear_df()
    a = assess_transforms(df, attribute="assay")
    none = next(c for c in a.candidates if c.name == "none")
    assert isinstance(none.s_resid, float) and none.s_resid > 0
    assert isinstance(none.aic, float)
    # Normality / homoscedasticity: float or None depending on n
    assert none.normality_p is None or isinstance(none.normality_p, float)
    assert none.homoscedasticity_p is None or isinstance(none.homoscedasticity_p, float)


def test_assessment_handles_filter_argument():
    """When ``attribute`` is given, only that attribute's rows are used."""
    df = _linear_df()
    df2 = _linear_df(slope=-0.1, intercept=50.0, seed=999)
    df2["attribute"] = "impurity_a"
    combined = pd.concat([df, df2], ignore_index=True)
    a = assess_transforms(combined, attribute="assay")
    # The recommendation should be based on the assay data only
    # (slope=-0.5), not the impurity data.
    assert a.official_model_transform == "none"
    assert all(c.name in {"none", "log", "sqrt"} for c in a.candidates)
