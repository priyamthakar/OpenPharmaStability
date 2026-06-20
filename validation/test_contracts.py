import pytest
from openpharmastability.contracts import StabilityResult, CrossingResult, \
    PoolabilityResult, FitResult, DiagnosticsResult, Direction, ModelKind, Poolability


def _bare_result():
    import numpy as np
    return StabilityResult(
        attribute="assay", condition="25C/60RH", direction=Direction.DECREASING,
        model=ModelKind.COMMON_SLOPE,
        poolability=PoolabilityResult(Poolability.PARTIAL, 0.30, 0.10, 0.25),
        fit=FitResult(kind=ModelKind.COMMON_SLOPE, params={}, df_resid=36,
                      s_resid=0.5, cov=np.zeros((2, 2)),
                      fitted_fn=lambda b: (lambda t: t), design={}),
        crossing=CrossingResult(17.9, "crossed", "B2"),
        supported_shelf_life_months=17, statistical_crossing_months=17.9,
        observed_data_months=12.0, extrapolation_flag=False,
        diagnostics=DiagnosticsResult(True, True, True, []),
    )


def test_stability_result_default_profile_name():
    r = _bare_result()
    assert r.profile_name == "Q1A_R2+Q1E"


def test_stability_result_profile_name_settable():
    r = _bare_result()
    r.profile_name = "custom_test"
    assert r.profile_name == "custom_test"
