"""v0.5.0 engine integration tests for the advanced-statistics opt-ins.

These tests exercise the new opt-in features wired into
:func:`openpharmastability.shelf_life.engine.analyze`:

* ``run_arrhenius`` — Arrhenius fit from multi-temperature rate data.
* ``run_mkt`` — Haynes mean kinetic temperature (USP <1160>).
* ``detect_reduced_design`` — ICH Q1D reduced-design detection
  (bracketing / matrixing).
* ``random_effects`` — mixed-effects fit (batch as a random
  effect) instead of the Q1E default fixed-effect ANCOVA.

The v0.5 modules are a hard requirement: ``validation/conftest.py``
exits at collection time if any of ``stats.arrhenius``, ``stats.mkt``,
``regulatory.reduced_design``, or ``regulatory.significant_change``
is missing. Importing them at the top of this file is therefore safe;
the prior skip-if-missing fallback (which hid a partial build behind
a healthy-looking "skipped" report) has been removed.
"""
from __future__ import annotations

import math
import pathlib
import tempfile

import numpy as np
import pandas as pd
import pytest

from openpharmastability.contracts import (
    ArrheniusResult,
    Direction,
    ReducedDesignReport,
)
from openpharmastability.regulatory.reduced_design import detect_reduced_design
from openpharmastability.shelf_life.engine import analyze
from openpharmastability.stats.arrhenius import fit_arrhenius
from openpharmastability.stats.mkt import mean_kinetic_temperature


ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV = ROOT / "examples" / "assay_3batch.csv"


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------


def _write_three_temp_assay_csv(path: pathlib.Path) -> None:
    """Write a 3-batch / 3-temperature synthetic assay CSV.

    3 batches (B1, B2, B3) x 3 stress temperatures (40, 50, 60 °C)
    x time points (0, 1, 2, 3, 6 months). The slope is chosen to
    *increase* with temperature (faster degradation at higher
    temp), so the Arrhenius fit recovers a positive ``Ea``.

    v0.5.1 audit fix note: the rows all carry the SAME condition
    (``"25C/60RH"``) so that ``validate_and_select`` keeps every
    row at the user's requested condition. The stress
    temperature is carried in the ``temp_c`` column instead of
    in the condition string — this is the data shape the audit
    fix's per-attribute / per-condition filtering supports.
    Earlier versions of this fixture spread the stress
    temperatures across three different conditions, which the
    audit fix would now filter down to a single temperature.
    """
    rng = np.random.default_rng(20260113)
    rows = []
    for batch, b0 in (("B1", 100.0), ("B2", 99.0), ("B3", 101.0)):
        for temp_c in (40.0, 50.0, 60.0):
            # Slope in 1/month: faster degradation at higher temp.
            slope = 0.2 + 0.1 * (temp_c - 40.0) / 20.0
            for t in (0.0, 1.0, 2.0, 3.0, 6.0):
                v = b0 - slope * t + float(rng.normal(0.0, 0.3))
                rows.append({
                    "batch": batch,
                    "condition": "25C/60RH",
                    "time_months": t,
                    "attribute": "assay",
                    "value": round(v, 4),
                    "lower_spec": 90.0,
                    "upper_spec": 110.0,
                    "direction": "decreasing",
                    "temp_c": temp_c,
                })
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_golden_with_temp_c(path: pathlib.Path) -> None:
    """Copy the golden fixture and add a constant ``temp_c=25`` column.

    The golden fixture has only one condition (25C/60RH) and no
    ``temp_c`` column; the MKT path needs a ``temp_c`` column with
    at least one finite value, so we write a copy that adds one.
    The numeric values of the assay are NOT changed, so the
    v0.4.0 default-path results (and the regen check) are not
    affected — this is a side file used only by this test.
    """
    df = pd.read_csv(CSV)
    df["temp_c"] = 25.0
    df.to_csv(path, index=False)


# ---------------------------------------------------------------------------
# 1. Default path (no new flags) is byte-equivalent to v0.4.0
# ---------------------------------------------------------------------------


def test_golden_v050_default_unchanged() -> None:
    """Golden fixture with no v0.5.0 flags: defaults are
    ``model_effects == "fixed"`` and the three new optional fields
    are ``None``. The supported shelf life is still 17 months
    (the v0.4.0 contract)."""
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
    )
    assert result.model_effects == "fixed"
    assert result.arrhenius_result is None
    assert result.mkt_celsius is None
    assert result.reduced_design_report is None
    assert result.supported_shelf_life_months == 17


# ---------------------------------------------------------------------------
# 2. Arrhenius runs on multi-temp synthetic data
# ---------------------------------------------------------------------------


def test_arrhenius_runs_with_multiple_temps(tmp_path) -> None:
    """A 3-batch / 3-temperature synthetic frame produces a
    populated :class:`ArrheniusResult` with positive ``Ea`` and
    ``n_temps >= 2``. The exact value is NOT pinned (the spec is
    exploratory) — only the structural invariants.

    v0.5.1 audit fix: the analyze call uses the same condition
    string as the fixture (``"25C/60RH"``); the three stress
    temperatures are carried in the ``temp_c`` column. The
    helper groups by ``temp_c`` and recovers a 3-point
    Arrhenius line."""
    csv_path = tmp_path / "multitemp.csv"
    _write_three_temp_assay_csv(csv_path)
    result = analyze(
        path=str(csv_path),
        condition="25C/60RH",
        attribute="assay",
        run_arrhenius=True,
    )
    assert result.arrhenius_result is not None
    assert result.arrhenius_result.n_temps >= 2
    # Physically reasonable Ea (positive; the spec is exploratory
    # so we only assert sign, not magnitude).
    assert result.arrhenius_result.Ea_J_per_mol > 0
    # model_effects stays "fixed" unless random_effects=True
    assert result.model_effects == "fixed"


# ---------------------------------------------------------------------------
# 3. Arrhenius is skipped on a single-temperature dataset
# ---------------------------------------------------------------------------


def test_arrhenius_skipped_with_one_temp() -> None:
    """Golden fixture has only one temperature (25 °C). With
    ``run_arrhenius=True`` the engine records a warning naming
    the skip reason and leaves ``arrhenius_result`` at ``None``."""
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
        run_arrhenius=True,
    )
    assert result.arrhenius_result is None
    assert any(
        "Arrhenius fit skipped" in w for w in result.warnings
    ), f"expected an Arrhenius-skip warning in {result.warnings!r}"


# ---------------------------------------------------------------------------
# 4. MKT runs when the input has a temp_c column
# ---------------------------------------------------------------------------


def test_mkt_runs_with_temp_c_column(tmp_path) -> None:
    """A copy of the golden fixture with an added ``temp_c=25``
    column yields ``mkt_celsius`` ≈ 25 (within 1 °C)."""
    csv_path = tmp_path / "golden_with_temp_c.csv"
    _write_golden_with_temp_c(csv_path)
    result = analyze(
        path=str(csv_path),
        condition="25C/60RH",
        attribute="assay",
        run_mkt=True,
    )
    assert result.mkt_celsius is not None
    # The constant temperature 25.0 collapses to MKT == 25.0
    # (within numerical tolerance). Allow a small window so the
    # test does not pin floating-point bits.
    assert 24.0 <= result.mkt_celsius <= 26.0
    assert isinstance(result.mkt_celsius, float)


# ---------------------------------------------------------------------------
# 5. Reduced-design detection runs (on a full-factorial frame)
# ---------------------------------------------------------------------------


def test_detect_reduced_design_runs() -> None:
    """Golden fixture is a full-factorial design (1 condition x
    3 batches x 7 times). ``detect_reduced_design=True`` produces
    a populated :class:`ReducedDesignReport`."""
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
        detect_reduced_design=True,
    )
    assert result.reduced_design_report is not None
    # The shipped golden is full-factorial: not reduced.
    assert result.reduced_design_report.is_bracketed is False
    assert result.reduced_design_report.is_matrixed is False


# ---------------------------------------------------------------------------
# 6. random_effects=True changes model_effects and warns
# ---------------------------------------------------------------------------


def test_random_effects_flag_changes_model_effects() -> None:
    """``random_effects=True`` sets ``model_effects="random"``,
    appends the documented warning, and still produces a finite
    integer supported shelf life (the value may differ from the
    fixed-effect path — that's the whole point of the opt-in)."""
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
        random_effects=True,
    )
    assert result.model_effects == "random"
    assert any(
        "Random-effects model selected" in w for w in result.warnings
    ), f"expected a random-effects warning in {result.warnings!r}"
    # The shelf life is still a finite int on this dataset (the
    # random-effects path is allowed to differ from the fixed path;
    # the test only asserts the result is well-formed).
    assert result.supported_shelf_life_months is not None
    assert isinstance(result.supported_shelf_life_months, int)


# ---------------------------------------------------------------------------
# 7. Default (no random_effects flag) remains "fixed"
# ---------------------------------------------------------------------------


def test_random_effects_default_remains_fixed() -> None:
    """Without the flag, ``model_effects`` is "fixed" and no
    random-effects warning is appended."""
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
    )
    assert result.model_effects == "fixed"
    assert not any(
        "Random-effects model selected" in w for w in result.warnings
    )


# ---------------------------------------------------------------------------
# v0.5.1 — audit-fix fixtures and tests
# ---------------------------------------------------------------------------


def _write_two_attr_two_temp_csv(path: pathlib.Path) -> None:
    """Two attributes (assay + impurity_a) at 2 stress temps
    within a SINGLE condition (``"25C/60RH"``).

    The condition is constant so ``validate_and_select`` keeps
    every row at the user's requested condition; the stress
    temperature is carried in the ``temp_c`` column.

    The impurity has a much LARGER log-linear slope magnitude
    than the assay (its values span a much wider range in
    log-space). If the helper's attribute filter were broken
    (the v0.5.0 bug), the recovered rate would be visibly
    off because the impurity rows would dominate the fit.
    """
    rng = np.random.default_rng(20260114)
    rows = []
    # assay: mild DECREASING values around 95-100; log-linear
    # slope magnitude is small (values change by ~1% per month).
    for batch, b0 in (("B1", 100.0), ("B2", 99.5)):
        for temp_c in (40.0, 60.0):
            # Mild slope: ~0.2 / month at 40 C, ~0.3 / month at 60 C.
            slope = 0.2 + 0.1 * (temp_c - 40.0) / 20.0
            for t in (0.0, 1.0, 2.0, 3.0):
                v = b0 - slope * t + float(rng.normal(0.0, 0.2))
                rows.append({
                    "batch": batch,
                    "condition": "25C/60RH",
                    "time_months": t,
                    "attribute": "assay",
                    "value": round(v, 4),
                    "lower_spec": 90.0,
                    "upper_spec": 110.0,
                    "direction": "decreasing",
                    "temp_c": temp_c,
                })
    # impurity_a: small baseline (0.05) that grows ~5x over 3 months
    # at 40 C and ~10x at 60 C. The log-linear slope magnitude is
    # an ORDER OF MAGNITUDE larger than the assay's, so any
    # contamination of the fit by impurity rows is unmistakable.
    for batch, b0 in (("B1", 0.05), ("B2", 0.05)):
        for temp_c in (40.0, 60.0):
            for t in (0.0, 1.0, 2.0, 3.0):
                v = b0 * (1.0 + (temp_c - 40.0) / 20.0) * (1.0 + t)
                v = max(v, 1e-6)
                rows.append({
                    "batch": batch,
                    "condition": "25C/60RH",
                    "time_months": t,
                    "attribute": "impurity_a",
                    "value": round(v, 6),
                    "lower_spec": None,
                    "upper_spec": 0.5,
                    "direction": "increasing",
                    "temp_c": temp_c,
                })
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_increasing_degradant_csv(path: pathlib.Path) -> None:
    """Single INCREASING attribute (``impurity_a``) at 2 stress
    temps within a single condition. Values grow with time, the
    growth rate scales with temperature. This exercises the
    ``sign = +1`` branch of the v0.5.1 audit fix."""
    rng = np.random.default_rng(20260115)
    rows = []
    for batch, b0 in (("B1", 0.05), ("B2", 0.05)):
        for temp_c in (40.0, 60.0):
            for t in (0.0, 1.0, 2.0, 3.0):
                v = b0 * (1.0 + 0.5 * (temp_c - 40.0) / 20.0) * (1.0 + 0.3 * t)
                v += float(rng.normal(0.0, 0.005))
                v = max(v, 1e-6)
                rows.append({
                    "batch": batch,
                    "condition": "25C/60RH",
                    "time_months": t,
                    "attribute": "impurity_a",
                    "value": round(v, 6),
                    "lower_spec": None,
                    "upper_spec": 0.5,
                    "direction": "increasing",
                    "temp_c": temp_c,
                })
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_bidirectional_csv(path: pathlib.Path) -> None:
    """Single BIDIRECTIONAL attribute at 1 condition (1 temp). The
    helper must refuse to fit regardless of how many temps the
    frame carries; we use 1 temp here because the directional
    skip fires BEFORE the < 2-temps skip in the helper."""
    rows = []
    for batch, b0 in (("B1", 50.0), ("B2", 51.0)):
        for t in (0.0, 1.0, 2.0, 3.0):
            v = b0 + 0.1 * t
            rows.append({
                "batch": batch,
                "condition": "25C/60RH",
                "time_months": t,
                "attribute": "weird_attr",
                "value": round(v, 4),
                "lower_spec": 40.0,
                "upper_spec": 60.0,
                "direction": "bidirectional",
                "temp_c": 25.0,
            })
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_golden_with_empty_temp_c(path: pathlib.Path) -> None:
    """Copy the golden fixture and add a ``temp_c`` column that is
    entirely NaN. Used to exercise the 'temp_c present but no
    finite values' branch of the MKT-without-temp_c warning."""
    df = pd.read_csv(CSV)
    df["temp_c"] = float("nan")
    df.to_csv(path, index=False)


# ---------------------------------------------------------------------------
# 8. v0.5.1 audit fix: Arrhenius filters to the selected attribute
# ---------------------------------------------------------------------------


def test_arrhenius_filters_to_selected_attribute(tmp_path) -> None:
    """A multi-attribute frame with two very different log-linear
    slopes. When the user asks for ``attribute="assay"`` the
    recovered Arrhenius rate must reflect the ASSAY rows alone —
    the steeper impurity rows must NOT contaminate the fit."""
    csv_path = tmp_path / "two_attr.csv"
    _write_two_attr_two_temp_csv(csv_path)
    result = analyze(
        path=str(csv_path),
        condition="25C/60RH",
        attribute="assay",
        run_arrhenius=True,
    )
    # The fit ran on >= 2 temps (otherwise the < 2-temps skip
    # would have set arrhenius_result to None).
    assert result.arrhenius_result is not None
    assert result.arrhenius_result.n_temps >= 2
    # The fit must be on the assay rows: the assay slope magnitude
    # is ~0.2-0.3 / month; the impurity slope magnitude is
    # ~0.5-1.0 / month (an order of magnitude larger). If the
    # helper had read the impurity rows the rate would be at
    # least 2-3x the assay rate. We assert an upper bound well
    # below the impurity's rate to flag any contamination.
    rates = list(result.arrhenius_result.rate_by_temp_C.values())
    assert all(0.0 < r < 0.6 for r in rates), (
        f"recovered per-temperature rates {rates!r} are not in the "
        f"assay-only range; possible contamination by impurity rows"
    )


# ---------------------------------------------------------------------------
# 9. v0.5.1 audit fix: INCREASING direction takes sign = +1
# ---------------------------------------------------------------------------


def test_arrhenius_increasing_degradant_direction(tmp_path) -> None:
    """An INCREASING attribute (degradant that grows with time) at
    2+ stress temps. The fit must run, the recovered predicted
    rate at the storage temperature must be positive."""
    csv_path = tmp_path / "inc.csv"
    _write_increasing_degradant_csv(csv_path)
    result = analyze(
        path=str(csv_path),
        condition="25C/60RH",
        attribute="impurity_a",
        run_arrhenius=True,
    )
    assert result.arrhenius_result is not None
    assert result.arrhenius_result.n_temps >= 2
    # For INCREASING, sign = +1, so the rate is +slope (positive).
    # The storage temperature (default 25 C) is BELOW the lowest
    # stress temperature (40 C) so the extrapolated rate is
    # smaller than either stress rate but still positive.
    assert result.arrhenius_result.predicted_k_at_storage > 0.0


# ---------------------------------------------------------------------------
# 10. v0.5.1 audit fix: BIDIRECTIONAL/UNKNOWN direction is skipped
# ---------------------------------------------------------------------------


def test_arrhenius_bidirectional_skipped(tmp_path) -> None:
    """A BIDIRECTIONAL attribute cannot have a meaningful sign
    applied to its rate (the slope's sign is ambiguous in this
    case). The helper must skip with a warning naming
    BIDIRECTIONAL/UNKNOWN."""
    csv_path = tmp_path / "bidir.csv"
    _write_bidirectional_csv(csv_path)
    result = analyze(
        path=str(csv_path),
        condition="25C/60RH",
        attribute="weird_attr",
        run_arrhenius=True,
    )
    assert result.arrhenius_result is None
    assert any(
        "BIDIRECTIONAL" in w for w in result.warnings
    ), f"expected a BIDIRECTIONAL skip warning in {result.warnings!r}"


# ---------------------------------------------------------------------------
# 11. v0.5.1: MKT with no temp_c column emits an explicit warning
# ---------------------------------------------------------------------------


def test_mkt_without_temp_c_emits_warning() -> None:
    """The golden fixture has no ``temp_c`` column. With
    ``run_mkt=True`` the engine must (a) leave ``mkt_celsius`` at
    None and (b) record a warning naming the missing column so
    the user knows MKT was silently skipped."""
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
        run_mkt=True,
    )
    assert result.mkt_celsius is None
    assert any(
        "MKT requested but no temp_c" in w for w in result.warnings
    ), f"expected an MKT-missing-temp_c warning in {result.warnings!r}"


# ---------------------------------------------------------------------------
# 12. v0.5.1: MKT with all-NaN temp_c emits an explicit warning
# ---------------------------------------------------------------------------


def test_mkt_with_empty_temp_c_emits_warning(tmp_path) -> None:
    """A copy of the golden fixture with a ``temp_c`` column that
    is entirely NaN. The engine must (a) leave ``mkt_celsius`` at
    None and (b) record a warning naming the empty-temp_c
    condition (different text from the missing-column branch)."""
    csv_path = tmp_path / "golden_with_empty_temp_c.csv"
    _write_golden_with_empty_temp_c(csv_path)
    result = analyze(
        path=str(csv_path),
        condition="25C/60RH",
        attribute="assay",
        run_mkt=True,
    )
    assert result.mkt_celsius is None
    assert any(
        "no finite values" in w for w in result.warnings
    ), f"expected an MKT-empty-temp_c warning in {result.warnings!r}"


# ---------------------------------------------------------------------------
# 13. v0.7.0 — leave-one-out sensitivity analysis (regression test)
# ---------------------------------------------------------------------------


def test_golden_v070_sensitivity_attaches_report() -> None:
    """``run_sensitivity=True`` attaches a populated
    :class:`~openpharmastability.contracts.SensitivityReport` to
    the result. The default path (no flag) leaves the field at
    ``None`` so v0.6.x callers and hand-built fixtures continue
    to work unchanged.
    """
    # Default path: no flag -> sensitivity_report stays None.
    default_result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
    )
    assert default_result.sensitivity_report is None
    # Opt-in path: --sensitivity equivalent -> a populated
    # report is attached.
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
        run_sensitivity=True,
    )
    assert result.sensitivity_report is not None
    # The golden fixture has 4 Cook's-distance influential
    # points; the sensitivity helper produces one row per
    # influential point.
    assert len(result.sensitivity_report.rows) >= 1
    # And the baseline shelf life is echoed.
    assert (
        result.sensitivity_report.baseline_supported_shelf_life
        == result.supported_shelf_life_months
    )


# ---------------------------------------------------------------------------
# 14. v0.8.0 — sensitivity_mode defaults to row (v0.7.0 byte-equivalent)
# ---------------------------------------------------------------------------


def test_golden_v080_sensitivity_mode_default_row() -> None:
    """``analyze(..., run_sensitivity=True)`` with no
    ``sensitivity_mode`` kwarg produces a row-mode
    :class:`SensitivityReport` (``report.mode == "row"``).
    Regression test for the v0.7.0 → v0.8.0 default."""
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
        run_sensitivity=True,
    )
    assert result.sensitivity_report is not None
    assert result.sensitivity_report.mode == "row"
    # And the row-mode summary text does NOT use the batch-mode
    # wording (the precise row-mode text depends on the per-row
    # diffs: "outliers" / "1 point changes" / "a single point
    # drives"). The negative check is enough to catch an
    # accidental mode flip.
    s = result.sensitivity_report.summary.lower()
    assert "batch" not in s, (
        f"row-mode summary should not mention 'batch', got "
        f"{result.sensitivity_report.summary!r}"
    )


def test_golden_v080_sensitivity_mode_batch_attaches_batch_report() -> None:
    """``analyze(..., run_sensitivity=True, sensitivity_mode="batch")``
    on the 3-batch golden fixture attaches a batch-mode report
    with 3 rows (one per batch). The mode is "batch", every row
    carries the batch identifier in ``drop_key``, and the
    summary uses the batch-flavored wording."""
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
        run_sensitivity=True,
        sensitivity_mode="batch",
    )
    assert result.sensitivity_report is not None
    assert result.sensitivity_report.mode == "batch"
    assert len(result.sensitivity_report.rows) == 3
    # Every row is tagged mode="batch" and drop_key is one of
    # the three batch identifiers in the golden fixture.
    expected_batches = {"B1", "B2", "B3"}
    seen = set()
    for row in result.sensitivity_report.rows:
        assert row.mode == "batch"
        assert row.drop_key in expected_batches, (
            f"unexpected drop_key {row.drop_key!r}"
        )
        seen.add(row.drop_key)
    assert seen == expected_batches
    # The summary uses the batch-mode wording.
    s = result.sensitivity_report.summary.lower()
    assert (
        "dropping any single batch" in s
        or "a single batch drives" in s
    ), f"unexpected batch-mode summary: {result.sensitivity_report.summary!r}"


# ---------------------------------------------------------------------------
# 14. v0.8.0 — Arrhenius-driven shelf-life prediction (additive)
# ---------------------------------------------------------------------------


def test_golden_v080_arrhenius_shelf_life_attaches_field() -> None:
    """``run_arrhenius_shelf_life=True`` attaches a populated
    :class:`~openpharmastability.contracts.ArrheniusShelfLife`
    to the result on the ``arrhenius_shelf_life`` field. The
    golden fixture has only one temperature (25 °C, parsed from
    the condition string) so the underlying Arrhenius fit is
    skipped; the prediction layer mirrors that with all
    predictive fields ``None`` and a note about < 2 temps."""
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
        run_arrhenius_shelf_life=True,
    )
    # The field is attached (NOT left at the v0.7.0 default of
    # None); the prediction layer always returns an
    # ArrheniusShelfLife, with predictive fields None on the skip
    # path.
    assert result.arrhenius_shelf_life is not None
    assert result.arrhenius_shelf_life.predicted_shelf_life_months is None
    assert result.arrhenius_shelf_life.predicted_statistical_crossing_months is None
    # The note explicitly mentions < 2 distinct temperatures.
    notes = list(result.arrhenius_shelf_life.notes or [])
    assert any(
        "2 distinct temperatures" in n or "< 2" in n or ">= 2" in n
        for n in notes
    ), f"expected a <2-temp note in {notes!r}"
    # The official Q1E shelf-life decision is unchanged.
    assert result.supported_shelf_life_months == 17


def test_golden_v080_default_unchanged() -> None:
    """Default path (no ``run_arrhenius_shelf_life`` flag) leaves
    the new ``arrhenius_shelf_life`` field at ``None`` so v0.7.x
    callers and hand-built fixtures continue to work unchanged."""
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
    )
    assert result.arrhenius_shelf_life is None
    # And the v0.7.0 default shelf life is preserved byte-for-byte.
    assert result.supported_shelf_life_months == 17
    assert result.model_effects == "fixed"


def test_golden_v080_arrhenius_shelf_life_storage_temp_override() -> None:
    """The ``arrhenius_shelf_life_storage_temp_C`` kwarg is honored.
    With a different storage temperature the returned
    :class:`ArrheniusShelfLife` echoes the user-supplied value on
    the ``storage_temp_C`` field."""
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
        run_arrhenius_shelf_life=True,
        arrhenius_shelf_life_storage_temp_C=30.0,
    )
    assert result.arrhenius_shelf_life is not None
    assert result.arrhenius_shelf_life.storage_temp_C == 30.0
