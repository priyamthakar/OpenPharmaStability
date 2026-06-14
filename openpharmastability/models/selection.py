"""Model selection: pick the right FitResult given the poolability decision.

The :func:`select_model` function is a thin layer that maps the
:func:`~openpharmastability.stats.poolability.decide_poolability`
decision to the matching :class:`FitResult` from the dict returned by
:func:`~openpharmastability.stats.regression.fit_models`.

Mapping (ICH Q1E):

* :data:`~openpharmastability.contracts.Poolability.NONE` ->
  :data:`~openpharmastability.contracts.ModelKind.SEPARATE`
  (per-batch slopes and intercepts).
* :data:`~openpharmastability.contracts.Poolability.PARTIAL` ->
  :data:`~openpharmastability.contracts.ModelKind.COMMON_SLOPE`
  (one common slope, batch-specific intercepts).
* :data:`~openpharmastability.contracts.Poolability.FULL` ->
  :data:`~openpharmastability.contracts.ModelKind.POOLED`
  (one intercept and one slope across all batches).
"""
from __future__ import annotations

from openpharmastability.contracts import (
    FitResult,
    ModelKind,
    Poolability,
    PoolabilityResult,
)


_DECISION_TO_KIND: dict[Poolability, ModelKind] = {
    Poolability.NONE: ModelKind.SEPARATE,
    Poolability.PARTIAL: ModelKind.COMMON_SLOPE,
    Poolability.FULL: ModelKind.POOLED,
}


def select_model(
    pool: PoolabilityResult,
    fits: dict[ModelKind, FitResult],
) -> tuple[ModelKind, FitResult]:
    """Pick the model kind driven by the poolability decision.

    Parameters
    ----------
    pool:
        The :class:`PoolabilityResult` from
        :func:`openpharmastability.stats.poolability.decide_poolability`.
    fits:
        The dict of fitted models from
        :func:`openpharmastability.stats.regression.fit_models`.

    Returns
    -------
    (ModelKind, FitResult)
        The chosen kind and its :class:`FitResult`.

    Raises
    ------
    KeyError
        If the chosen model kind is not in ``fits`` (should not happen
        with the standard :func:`fit_models` output).
    """
    kind = _DECISION_TO_KIND[pool.decision]
    return kind, fits[kind]


__all__ = ["select_model"]
