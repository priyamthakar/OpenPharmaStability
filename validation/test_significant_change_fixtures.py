"""Fixture-driven end-to-end tests for the v0.4.0 ICH Q1A(R2)
significant-change gate.

These tests exercise the engine :func:`analyze` end-to-end on the
new ``examples/`` fixtures and prove that the gate fires for each
of the documented branches:

* No accelerated/intermediate data in the input -> gate silent,
  defaults stay permissive (``extrapolation_allowed=True``,
  ``extrapolation_rationale="no accelerated data"``,
  ``significant_change_accelerated=None``).
* Accelerated change fires at ``t < 3`` months -> no
  extrapolation, ``supported_shelf_life_months`` capped at the
  observed long-term data length, rationale contains ``"<3mo"``.
* Accelerated change fires at ``3 <= t <= 6`` months with no
  intermediate data -> no extrapolation, rationale contains
  ``"intermediate data required"``.
* Same 3-6 month accelerated change with intermediate data that
  shows no change -> extrapolation permitted, rationale contains
  ``"intermediate OK"``.
* Same 3-6 month accelerated change with intermediate data that
  DOES show a change -> no extrapolation, rationale contains
  ``"intermediate sig change"``.
* ``no_significant_change_gate=True`` restores the v0.3.1 cap-only
  behavior: ``extrapolation_rationale=""``,
  ``significant_change_accelerated=None``, the v0.3.1 cap math still
  produces a numeric ``supported_shelf_life_months``.

The fixtures used:

* ``examples/assay_long_term.csv`` -- 3 batches x 5 time points
  (0, 3, 6, 9, 12) at 25C/60RH, assay baseline ~100, slope
  ~-0.30/mo. Statistical crossing ~32 mo, v0.3.1 cap
  ``min(2x, +12 mo) = 24 mo`` binds; supported_shelf_life = 24.
* ``examples/assay_accelerated_change_lt_3mo.csv`` -- 3 batches
  x 3 time points (0, 1, 3) at 40C/75RH, assay drops 6% at t=1
  (so ``first_change_month = 1 < 3``).
* ``examples/assay_accelerated_change_3_6mo.csv`` -- 3 batches
  x 5 time points (0, 1, 3, 4, 6) at 40C/75RH, minimal change
  until t=4, 6% drop at t=6 (so ``first_change_month = 6``,
  which is the boundary in the ``3 <= t <= 6`` branch).
* ``examples/assay_intermediate_no_change.csv`` -- 3 batches
  x 4 time points (0, 3, 6, 9) at 30C/65RH, <1% drift.
* ``examples/assay_intermediate_change.csv`` -- 3 batches
  x 4 time points (0, 1, 3, 6) at 30C/65RH, 6% drop at t=3.

The combined CSVs are built in ``tmp_path`` by concatenating the
relevant fixtures; the engine still filters on the requested
``condition`` and ignores the other arms for the long-term fit,
but the v0.4.0 gate inspects the non-filtered ``raw_df`` and
subsets on the accelerated/intermediate conditions itself.
"""
from __future__ import annotations

import pathlib

import pandas as pd
import pytest

from openpharmastability.shelf_life.engine import analyze


ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"

LONG_TERM = EXAMPLES / "assay_long_term.csv"
ACC_LT_3 = EXAMPLES / "assay_accelerated_change_lt_3mo.csv"
ACC_3_6 = EXAMPLES / "assay_accelerated_change_3_6mo.csv"
INTER_NONE = EXAMPLES / "assay_intermediate_no_change.csv"
INTER_CHANGE = EXAMPLES / "assay_intermediate_change.csv"


def _concat_csvs(parts: list[pathlib.Path], dest: pathlib.Path) -> pathlib.Path:
    """Concatenate ``parts`` (in order) and write the combined frame
    to ``dest``. Returns the destination path."""
    frames = [pd.read_csv(str(p)) for p in parts]
    combined = pd.concat(frames, ignore_index=True)
    combined.to_csv(dest, index=False)
    return dest


def test_long_term_only_gate_silent():
    """A long-term-only CSV carries no accelerated or intermediate
    rows, so the gate is silent: every new field keeps its
    permissive default and the v0.3.1 cap math is the only thing
    that governs ``supported_shelf_life_months``."""
    result = analyze(
        path=str(LONG_TERM),
        condition="25C/60RH",
        attribute="assay",
    )

    # The long-term fit crosses the lower spec, so the v0.3.1 cap
    # math (min(2x, +12 mo) of observed 12) yields 24.
    assert result.supported_shelf_life_months is not None
    assert result.observed_data_months == 12.0
    assert result.supported_shelf_life_months <= 24

    # Gate fields stay permissive.
    assert result.extrapolation_allowed is True
    assert result.extrapolation_rationale in {"", "no accelerated data"}
    assert result.significant_change_accelerated is None
    assert result.significant_change_intermediate is None
    # The details payload carries both per-arm blocks (the engine
    # always populates the structure so consumers don't have to
    # branch); with no data the per-arm ``occurred`` is None.
    details = result.significant_change_details
    assert "accelerated" in details
    assert "intermediate" in details
    assert details["accelerated"]["occurred"] is None
    assert details["accelerated"]["first_change_month"] is None
    assert details["intermediate"]["occurred"] is None
    assert details["intermediate"]["first_change_month"] is None


def test_accelerated_change_lt_3mo_no_extrapolation(tmp_path):
    """Long-term + accelerated arm with a 6% drop at t=1
    (``first_change_month = 1 < 3``). The Q1E branch fires: no
    extrapolation, supported shelf life capped at observed data."""
    combined = _concat_csvs(
        [LONG_TERM, ACC_LT_3], tmp_path / "combined_lt_acc_lt3.csv",
    )
    result = analyze(
        path=str(combined),
        condition="25C/60RH",
        attribute="assay",
    )

    assert result.significant_change_accelerated is True
    assert result.extrapolation_allowed is False
    assert "<3mo" in result.extrapolation_rationale
    # Cap is binding: the cap-derived limit equals the observed
    # long-term data length, so the supported value cannot exceed
    # the observed months.
    assert (
        result.supported_shelf_life_months
        <= result.observed_data_months
    )
    # And the per-criterion details agree: first_change_month
    # really is below 3.
    assert (
        result.significant_change_details["accelerated"][
            "first_change_month"
        ]
        < 3.0
    )


def test_accelerated_change_3_6_no_intermediate(tmp_path):
    """Long-term + accelerated arm with the first significant change
    at t=6 (in the 3-6 month range), with no intermediate arm. The
    gate requires intermediate data and forbids extrapolation."""
    combined = _concat_csvs(
        [LONG_TERM, ACC_3_6], tmp_path / "combined_lt_acc_3to6.csv",
    )
    result = analyze(
        path=str(combined),
        condition="25C/60RH",
        attribute="assay",
    )

    assert result.significant_change_accelerated is True
    assert result.extrapolation_allowed is False
    assert "intermediate data required" in result.extrapolation_rationale
    # No intermediate rows in the input -> intermediate flag stays
    # None (the arm was absent, not "no change").
    assert result.significant_change_intermediate is None


def test_accelerated_change_3_6_intermediate_ok(tmp_path):
    """Long-term + accelerated arm (3-6 month change) + intermediate
    arm with no significant change. Extrapolation is permitted and
    the supported value follows the v0.3.1 cap math."""
    combined = _concat_csvs(
        [LONG_TERM, ACC_3_6, INTER_NONE],
        tmp_path / "combined_lt_acc_3to6_inter_ok.csv",
    )
    result = analyze(
        path=str(combined),
        condition="25C/60RH",
        attribute="assay",
    )

    assert result.significant_change_accelerated is True
    assert result.significant_change_intermediate is False
    assert result.extrapolation_allowed is True
    assert "intermediate OK" in result.extrapolation_rationale
    # Cap is not binding: extrapolation to the statistical crossing
    # is allowed within Q1E limits.
    assert result.supported_shelf_life_months is not None
    assert (
        result.supported_shelf_life_months
        >= result.observed_data_months
    )


def test_accelerated_change_3_6_intermediate_change(tmp_path):
    """Long-term + accelerated arm (3-6 month change) + intermediate
    arm that ALSO shows a significant change. No extrapolation."""
    combined = _concat_csvs(
        [LONG_TERM, ACC_3_6, INTER_CHANGE],
        tmp_path / "combined_lt_acc_3to6_inter_change.csv",
    )
    result = analyze(
        path=str(combined),
        condition="25C/60RH",
        attribute="assay",
    )

    assert result.significant_change_accelerated is True
    assert result.significant_change_intermediate is True
    assert result.extrapolation_allowed is False
    assert "intermediate sig change" in result.extrapolation_rationale
    # The cap is binding; supported <= observed.
    assert (
        result.supported_shelf_life_months
        <= result.observed_data_months
    )


def test_no_gate_flag_restores_v031_cap(tmp_path):
    """With ``no_significant_change_gate=True`` the v0.4.0 gate is
    skipped entirely: the v0.3.1 cap-only behavior is restored
    byte-for-byte. The new fields keep their permissive defaults
    and the cap math still produces a numeric supported value."""
    combined = _concat_csvs(
        [LONG_TERM, ACC_LT_3],
        tmp_path / "combined_lt_acc_lt3_no_gate.csv",
    )
    result = analyze(
        path=str(combined),
        condition="25C/60RH",
        attribute="assay",
        no_significant_change_gate=True,
    )

    # Gate disabled -> new fields keep permissive defaults.
    assert result.extrapolation_allowed is True
    assert result.extrapolation_rationale == ""
    assert result.significant_change_accelerated is None
    assert result.significant_change_intermediate is None
    # The v0.3.1 cap math (min(2x, +12 mo) of observed 12) still
    # produces a numeric supported value because the long-term
    # fit crosses the lower spec.
    assert result.supported_shelf_life_months is not None
    assert result.supported_shelf_life_months <= 24
    # The disabled-gate warning is appended for the report.
    assert any(
        "no-significant-change-gate" in w or "gate disabled" in w
        for w in result.warnings
    )
