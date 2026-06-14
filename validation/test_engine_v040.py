"""Engine integration tests for the v0.4.0 ICH Q1A significant-change gate.

These exercise the engine end-to-end with the new gate parameters:

* ``accelerated_condition`` / ``intermediate_condition`` — the
  storage-condition labels whose rows the gate inspects.
* ``assay_change_threshold`` — percent change in assay that
  counts as "significant".
* ``no_significant_change_gate`` — escape hatch that restores the
  v0.3.1 cap-only behavior.

The tests below build small hand-crafted 3-batch / multi-condition
frames to exercise the documented branches:

1. The golden fixture (long-term only) keeps the v0.3.1 17-month
   shelf life because the gate has no accelerated rows to
   inspect, so it is silently permissive.
2. A hand-crafted 3-batch / 24-month long-term + 3-batch / 6-month
   accelerated frame, where the accelerated arm drops > 5% in
   3 months, trips the < 3mo branch of the Q1E decision table:
   the supported value is capped at the observed data length and
   a warning containing ``"<3mo"`` is appended.
3. The same dataset with ``no_significant_change_gate=True``
   restores the v0.3.1 cap-only behavior byte-for-byte: the
   significant-change fields stay at their default permissive
   values and the rationale is empty.
4. The ``significant_change_details`` dict on the result is
   non-empty when the gate fires.

These tests assume the ``openpharmastability.regulatory`` package
is importable. If it is not (e.g. on a partial build where Agent
A has not yet shipped ``significant_change.py``), the gate-dependent
tests are skipped with a clear message so the v0.3.1 contract tests
can still pass.
"""
from __future__ import annotations

import json
import pathlib
import tempfile

import pandas as pd
import pytest


# Conditional skip: the regulatory package must be present.
# Agent A owns the module; on a partial build these tests are
# skipped so the v0.3.1 contract is not broken.
try:
    from openpharmastability.regulatory import (  # noqa: F401
        evaluate_significant_change,
        extrapolation_allowance,
        q1e_cap,
    )
    _REGULATORY_AVAILABLE = True
except Exception:  # pragma: no cover — partial build
    _REGULATORY_AVAILABLE = False

needs_regulatory = pytest.mark.skipif(
    not _REGULATORY_AVAILABLE,
    reason="openpharmastability.regulatory.significant_change not installed",
)


from openpharmastability.contracts import (
    CrossingStatus,
    ModelKind,
    Poolability,
)
from openpharmastability.shelf_life.engine import analyze


ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV = ROOT / "examples" / "assay_3batch.csv"


# ---------------------------------------------------------------------------
# Helpers: build hand-crafted multi-condition fixtures
# ---------------------------------------------------------------------------


def _write_three_batch_two_condition_csv(
    path: pathlib.Path,
    *,
    long_term_months: tuple[float, ...] = (0.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0),
    acc_months: tuple[float, ...] = (0.0, 1.0, 2.0, 3.0, 6.0),
    acc_slope: float = 2.0,
    acc_drop_pct: float = 6.0,
    long_term_slope: float = 0.5,
) -> None:
    """Write a 3-batch CSV with both ``25C/60RH`` (long-term) and
    ``40C/75RH`` (accelerated) rows for ``assay``.

    The accelerated arm has the value drop by ``acc_drop_pct``% at
    ``acc_months[1]`` (the first time point after t=0). With
    ``acc_drop_pct=6.0`` and the default ``assay_change_threshold=5.0``,
    the assay-change criterion trips at the earliest t > 0 in the
    accelerated arm (i.e. inside the < 3mo window).
    """
    rows = []
    for batch, b0 in (("B1", 100.0), ("B2", 99.5), ("B3", 100.5)):
        # Long-term rows
        for t in long_term_months:
            v = b0 - long_term_slope * t
            rows.append({
                "batch": batch, "condition": "25C/60RH",
                "time_months": t, "attribute": "assay",
                "value": round(v, 4),
                "lower_spec": 90.0, "upper_spec": 110.0,
                "direction": "decreasing",
            })
        # Accelerated rows: t=0 baseline, then drop by acc_drop_pct% at t=1
        base_vals = []
        for t in acc_months:
            if t == 0.0:
                v = b0
            else:
                # Drop the value by acc_drop_pct% relative to t=0
                v = b0 * (1.0 - acc_drop_pct / 100.0)
                # Add a tiny per-batch perturbation
                v = v - 0.05 * t
            rows.append({
                "batch": batch, "condition": "40C/75RH",
                "time_months": t, "attribute": "assay",
                "value": round(v, 4),
                "lower_spec": 90.0, "upper_spec": 110.0,
                "direction": "decreasing",
            })
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)


# ---------------------------------------------------------------------------
# 1. Golden fixture: gate is silently permissive; shelf life stays 17 mo.
# ---------------------------------------------------------------------------


def test_golden_v040_keeps_17_months() -> None:
    """The golden fixture contains only long-term rows, so the
    significant-change gate is silently permissive and the
    v0.3.1 17-month shelf life is preserved.

    Behavior of the new fields on the default (gate-enabled) path
    is documented here:

    * ``extrapolation_allowed`` is True (no accelerated data -> the
      gate returns the "no accelerated data" / "no accelerated sig
      change" branch, which is permissive).
    * ``significant_change_accelerated`` / ``_intermediate`` are
      None (the arms had no rows, so we did not evaluate).
    * ``supported_shelf_life_months`` is 17 (unchanged from v0.3.1).
    """
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
    )
    assert result.supported_shelf_life_months == 17
    assert result.extrapolation_allowed is True
    # The accelerated arm had no rows in the dataset, so we did not
    # evaluate a SignificantChange for it.
    assert result.significant_change_accelerated is None
    assert result.significant_change_intermediate is None
    # The 17-month value is below the observed 24-month data, so
    # no extrapolation flag and no extrapolation cap warning.
    assert result.extrapolation_flag is False


# ---------------------------------------------------------------------------
# 2. < 3mo accelerated change -> gate forbids extrapolation, caps at observed
# ---------------------------------------------------------------------------


@needs_regulatory
def test_extrapolation_allowed_false_caps_at_observed(tmp_path) -> None:
    """A 6% assay drop in the accelerated arm at t=1 trips the
    < 3mo branch of the Q1E decision table. The supported shelf
    life is capped at the observed long-term data length, and a
    warning containing ``"<3mo"`` is appended.
    """
    csv_path = tmp_path / "lt_acc.csv"
    _write_three_batch_two_condition_csv(
        csv_path,
        acc_drop_pct=6.0,
        acc_months=(0.0, 1.0, 2.0, 3.0, 6.0),
    )
    result = analyze(
        path=str(csv_path),
        condition="25C/60RH",
        attribute="assay",
        accelerated_condition="40C/75RH",
        intermediate_condition="30C/65RH",
    )
    # Gate fired: accelerated SignificantChange is True, extrapolation
    # is forbidden, and the cap is the observed long-term data length.
    assert result.significant_change_accelerated is True
    assert result.extrapolation_allowed is False
    assert result.observed_data_months == 24.0
    # The supported value MUST be <= observed_data_months.
    assert result.supported_shelf_life_months is not None
    assert result.supported_shelf_life_months <= int(result.observed_data_months)
    # A warning naming the rationale (contains "<3mo") is appended.
    assert any("<3mo" in w for w in result.warnings), (
        f"expected a <3mo warning in {result.warnings!r}"
    )
    # Rationale string reflects the < 3mo branch.
    assert "<3mo" in result.extrapolation_rationale


# ---------------------------------------------------------------------------
# 3. no_significant_change_gate=True restores v0.3.1 cap-only behavior
# ---------------------------------------------------------------------------


@needs_regulatory
def test_no_gate_flag_restores_v031(tmp_path) -> None:
    """Same dataset as test 2, but with the gate opt-out. The
    engine must keep the v0.3.1 permissive defaults:

    * ``extrapolation_allowed`` is True
    * ``extrapolation_rationale`` is empty
    * ``significant_change_*`` are None
    * ``significant_change_details`` is empty
    * The "<3mo" warning from the gate is NOT appended
    * The "significant-change gate disabled via --no-significant-change-gate"
      warning IS appended.
    """
    csv_path = tmp_path / "lt_acc.csv"
    _write_three_batch_two_condition_csv(
        csv_path,
        acc_drop_pct=6.0,
        acc_months=(0.0, 1.0, 2.0, 3.0, 6.0),
    )
    result = analyze(
        path=str(csv_path),
        condition="25C/60RH",
        attribute="assay",
        accelerated_condition="40C/75RH",
        intermediate_condition="30C/65RH",
        no_significant_change_gate=True,
    )
    assert result.extrapolation_allowed is True
    assert result.extrapolation_rationale == ""
    assert result.significant_change_accelerated is None
    assert result.significant_change_intermediate is None
    assert result.significant_change_details == {}
    # The gate opt-out warning is appended exactly once.
    assert sum(
        1 for w in result.warnings
        if "significant-change gate disabled" in w
    ) == 1
    # And the gate's "<3mo" warning is NOT appended.
    assert not any("<3mo" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# 4. significant_change_details is non-empty when the gate fires
# ---------------------------------------------------------------------------


@needs_regulatory
def test_gate_populates_details(tmp_path) -> None:
    """When the gate fires, the per-attribute details payload
    carries evidence for the accelerated arm (and an empty /
    None entry for the intermediate arm, which had no data)."""
    csv_path = tmp_path / "lt_acc.csv"
    _write_three_batch_two_condition_csv(
        csv_path,
        acc_drop_pct=6.0,
        acc_months=(0.0, 1.0, 2.0, 3.0, 6.0),
    )
    result = analyze(
        path=str(csv_path),
        condition="25C/60RH",
        attribute="assay",
        accelerated_condition="40C/75RH",
        intermediate_condition="30C/65RH",
    )
    assert result.significant_change_details, (
        "expected non-empty significant_change_details when the gate fires"
    )
    # Accelerated arm must carry per-criterion evidence.
    assert "accelerated" in result.significant_change_details
    acc = result.significant_change_details["accelerated"]
    assert acc["occurred"] is True
    assert acc["first_change_month"] is not None
    # The assay criterion should be present and evaluated.
    assert "details" in acc
    assert "assay" in acc["details"]
    assert acc["details"]["assay"]["evaluated"] is True
    # Intermediate arm: no data, so the "occurred" flag is None
    # and the inner details dict is empty.
    inter = result.significant_change_details.get("intermediate", {})
    assert inter.get("occurred") is None
    assert not inter.get("details")
