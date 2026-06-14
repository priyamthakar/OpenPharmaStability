"""Tests for ``openpharmastability.data.schema.validate_and_select``.

These tests cover the contract-enforcing step between a raw CSV and
everything downstream. The two test groups are:

* **Happy path** — a small, realistic 3-batch x 4-time-point assay
  frame. Asserts the returned :class:`ValidatedData` has the shape the
  stats and reporting layers expect (12 rows, 3 batches, sorted time
  points, spec values carried over, the declared direction preserved).
* **Failure / inference rules** — missing required columns, missing
  spec limits, the four direction-inference outcomes, and the new
  direction-declaration vs. spec compatibility rules: a single-sided
  declaration with **both** spec limits present (the standard assay
  case) is normal and must NOT warn; only true incompatibilities
  (decreasing without lower_spec, increasing without upper_spec,
  bidirectional with one spec, or unknown) raise warnings.
"""
from __future__ import annotations

import pandas as pd
import pytest

from openpharmastability.contracts import Direction, ValidatedData
from openpharmastability.data.schema import validate_and_select


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _assay_3batch_4timepoint() -> pd.DataFrame:
    """Build a tidy 3-batch x 4-time-point assay frame for ``25C/60RH``.

    The fixture is the same shape the rest of Wave 1 will see from
    ``examples/assay_3batch.csv``: one row per ``(batch, time)`` cell,
    spec values constant across rows, an explicit ``direction`` column
    set to ``"decreasing"`` (assay's canonical direction). The
    ``direction`` column is present and the frame carries both spec
    limits; this is the standard assay case and must NOT trigger a
    direction warning (inference would say ``BIDIRECTIONAL`` but the
    user-declared trend takes precedence without complaint).
    """
    batches = ["B1", "B2", "B3"]
    time_points = [0, 3, 6, 12]
    rows = []
    for batch in batches:
        for t in time_points:
            rows.append(
                {
                    "batch": batch,
                    "condition": "25C/60RH",
                    "time_months": t,
                    "attribute": "assay",
                    "value": 100.0 - 0.2 * t,  # mild linear decay
                    "lower_spec": 90,
                    "upper_spec": 110,
                    "direction": "decreasing",
                    "temp_c": 25,
                    "rh": 60,
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_validate_and_select_happy_path_shape() -> None:
    df = _assay_3batch_4timepoint()
    result = validate_and_select(df, attribute="assay", condition="25C/60RH")

    # Return type is exactly the contract dataclass; the engine and
    # reporting layer will rely on duck typing, but a typo here would
    # silently break that.
    assert isinstance(result, ValidatedData)

    # 3 batches * 4 time points = 12 rows. With replicate_policy=
    # "individual" (the default) no aggregation happens.
    assert len(result.df) == 12
    assert result.n_batches == 3
    assert result.time_points == [0, 3, 6, 12]

    # Spec values and direction are carried over. Direction is the
    # declared value ("decreasing"), not the inferred BIDIRECTIONAL.
    # This is the standard assay case (decreasing declared with both
    # spec limits present) and must NOT trigger a direction warning —
    # see :func:`test_declared_decreasing_with_both_specs_no_warning`.
    assert result.lower_spec == 90.0
    assert result.upper_spec == 110.0
    assert result.direction is Direction.DECREASING
    assert result.attribute == "assay"
    assert result.condition == "25C/60RH"


def test_validate_and_select_sorts_by_batch_then_time() -> None:
    df = _assay_3batch_4timepoint()
    # Shuffle the rows to make sure sorting is the schema's job, not
    # the caller's.
    shuffled = df.sample(frac=1.0, random_state=0).reset_index(drop=True)
    result = validate_and_select(shuffled, attribute="assay", condition="25C/60RH")

    pairs = list(zip(result.df["batch"], result.df["time_months"]))
    assert pairs == sorted(pairs)


def test_validate_and_select_warns_on_direction_mismatch() -> None:
    """When the declared direction is INCOMPATIBLE with the available
    spec limits, a warning is recorded (not silently overridden).

    Note: the *compatible* case (e.g. ``decreasing`` declared with both
    spec limits present) is the standard assay shape and must NOT warn —
    see :func:`test_declared_decreasing_with_both_specs_no_warning` for
    that golden case. This test exercises a true incompatibility:
    ``decreasing`` declared with only ``upper_spec`` available.
    """
    # DECLARED "decreasing" but no lower_spec — decreasing cannot be
    # evaluated without a lower bound. The schema must record this
    # incompatibility in warnings.
    df = _frame_with_specs(lower=None, upper=110.0, has_direction=True)
    result = validate_and_select(df, attribute="assay", condition="25C/60RH")
    assert any("direction" in w and "decreasing" in w for w in result.warnings), (
        f"expected a direction-incompatibility warning, got: {result.warnings!r}"
    )


def test_validate_and_select_normalizes_condition_spelling() -> None:
    """Rows stored as ``"25°C/60%RH"`` should match a request for ``"25C/60RH"``."""
    df = _assay_3batch_4timepoint()
    df["condition"] = "25°C/60%RH"  # user-friendly spelling in the source file
    result = validate_and_select(df, attribute="assay", condition="25C 60% RH")
    # The canonical condition name is what the user expects in the report.
    assert result.condition == "25C/60RH"
    assert len(result.df) == 12


def test_validate_and_select_filters_out_other_attributes() -> None:
    df = _assay_3batch_4timepoint()
    # Add some impurity rows that must NOT show up in the result.
    extra = df.copy()
    extra["attribute"] = "impurity_a"
    extra["value"] = 0.1
    combined = pd.concat([df, extra], ignore_index=True)
    result = validate_and_select(combined, attribute="assay", condition="25C/60RH")
    assert (result.df["attribute"] == "assay").all()
    assert len(result.df) == 12


# ---------------------------------------------------------------------------
# Failure / inference rules
# ---------------------------------------------------------------------------


def test_validate_and_select_missing_required_column_raises() -> None:
    df = _assay_3batch_4timepoint().drop(columns=["batch"])
    with pytest.raises(ValueError) as excinfo:
        validate_and_select(df, attribute="assay", condition="25C/60RH")
    # The error message must name the missing column so the user can
    # fix the source file in one read.
    msg = str(excinfo.value)
    assert "batch" in msg
    assert "missing" in msg.lower()


def test_validate_and_select_missing_every_required_column_lists_all() -> None:
    df = pd.DataFrame({"foo": [1, 2, 3]})
    with pytest.raises(ValueError) as excinfo:
        validate_and_select(df, attribute="assay", condition="25C/60RH")
    msg = str(excinfo.value)
    # All required columns should be named in the error.
    for col in ("batch", "condition", "time_months", "attribute", "value"):
        assert col in msg


def test_validate_and_select_missing_both_spec_columns_raises() -> None:
    df = _assay_3batch_4timepoint().drop(columns=["lower_spec", "upper_spec"])
    with pytest.raises(ValueError) as excinfo:
        validate_and_select(df, attribute="assay", condition="25C/60RH")
    msg = str(excinfo.value)
    assert "lower_spec" in msg and "upper_spec" in msg


def test_validate_and_select_unknown_replicate_policy_raises() -> None:
    df = _assay_3batch_4timepoint()
    with pytest.raises(ValueError, match="replicate_policy"):
        validate_and_select(
            df, attribute="assay", condition="25C/60RH",
            replicate_policy="not_a_real_policy",
        )


def test_validate_and_select_unparseable_condition_raises() -> None:
    df = _assay_3batch_4timepoint()
    with pytest.raises(ValueError, match="could not parse condition"):
        validate_and_select(
            df, attribute="assay", condition="definitely not a condition"
        )


# ---------------------------------------------------------------------------
# Direction inference (the four cases from the spec)
# ---------------------------------------------------------------------------


def _frame_with_specs(lower, upper, has_direction=False) -> pd.DataFrame:
    """Tiny frame: 1 batch, 1 time point, with optional direction column."""
    row = {
        "batch": "B1",
        "condition": "25C/60RH",
        "time_months": 0,
        "attribute": "assay",
        "value": 100.0,
    }
    if lower is not None:
        row["lower_spec"] = lower
    if upper is not None:
        row["upper_spec"] = upper
    if has_direction:
        row["direction"] = "decreasing"
    return pd.DataFrame([row])


def test_direction_inference_upper_only_is_increasing() -> None:
    df = _frame_with_specs(lower=None, upper=1.0)
    result = validate_and_select(df, attribute="assay", condition="25C/60RH")
    assert result.direction is Direction.INCREASING
    assert result.lower_spec is None
    assert result.upper_spec == 1.0


def test_direction_inference_lower_only_is_decreasing() -> None:
    df = _frame_with_specs(lower=90.0, upper=None)
    result = validate_and_select(df, attribute="assay", condition="25C/60RH")
    assert result.direction is Direction.DECREASING
    assert result.lower_spec == 90.0
    assert result.upper_spec is None


def test_direction_inference_both_limits_is_bidirectional() -> None:
    df = _frame_with_specs(lower=90.0, upper=110.0)
    result = validate_and_select(df, attribute="assay", condition="25C/60RH")
    assert result.direction is Direction.BIDIRECTIONAL
    assert result.lower_spec == 90.0
    assert result.upper_spec == 110.0


def test_direction_inference_neither_limit_is_unknown() -> None:
    # If both columns are present but every row is NaN, there is no
    # finite spec limit to infer from. We model this by including only
    # the ``upper_spec`` column with an all-NaN value.
    df = pd.DataFrame(
        [
            {
                "batch": "B1",
                "condition": "25C/60RH",
                "time_months": 0,
                "attribute": "assay",
                "value": 100.0,
                "upper_spec": None,
                "lower_spec": None,
            }
        ]
    )
    result = validate_and_select(df, attribute="assay", condition="25C/60RH")
    assert result.direction is Direction.UNKNOWN
    assert result.lower_spec is None
    assert result.upper_spec is None


def test_declared_direction_overrides_inference_with_warning() -> None:
    """When ``direction`` is in the frame and is INCOMPATIBLE with the
    available spec limits, the declared value still wins, but a warning
    is recorded.

    The compatible case (``decreasing`` declared with both spec limits
    present) is asserted separately in
    :func:`test_declared_decreasing_with_both_specs_no_warning`. Here
    we exercise a true incompatibility: ``bidirectional`` declared
    with only one spec limit present.
    """
    # DECLARED "bidirectional" but only upper_spec present. The
    # inferred direction is INCREASING; the declared value is
    # BIDIRECTIONAL. The schema trusts the declared value but flags
    # the spec mismatch in warnings.
    df = _frame_with_specs(lower=None, upper=110.0, has_direction=False)
    df["direction"] = "bidirectional"
    result = validate_and_select(df, attribute="assay", condition="25C/60RH")
    # Declared wins.
    assert result.direction is Direction.BIDIRECTIONAL
    # But the incompatibility is recorded.
    assert any(
        "BIDIRECTIONAL" in w or "direction" in w
        for w in result.warnings
    ), f"expected a direction warning, got: {result.warnings!r}"


def test_empty_filter_emits_warning_and_returns_empty_validated_data() -> None:
    """Asking for a condition that no row matches must not crash; it
    returns an empty :class:`ValidatedData` with a clear warning."""
    df = _assay_3batch_4timepoint()
    result = validate_and_select(
        df, attribute="assay", condition="40C/75RH"  # not in the frame
    )
    assert result.n_batches == 0
    assert result.time_points == []
    assert result.df.empty
    assert any("no rows match" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Direction declaration vs. spec compatibility (v0.1.1)
#
# The schema used to warn any time the declared direction disagreed
# with the inferred one. That produced a false positive on the golden
# assay case (both spec limits present, single-sided direction
# declared). The new rule: warn only on true incompatibilities
# between the declaration and the available specs.
# ---------------------------------------------------------------------------


def test_declared_decreasing_with_both_specs_no_warning() -> None:
    """The golden assay case: both spec limits present, ``decreasing``
    declared. This is normal and must NOT warn.

    Regression guard for the v0.1.0→v0.1.1 fix that removed the
    false-positive ``differs from the inferred direction`` warning.
    """
    df = _frame_with_specs(lower=90.0, upper=110.0, has_direction=True)
    result = validate_and_select(df, attribute="assay", condition="25C/60RH")
    # No mismatch / incompatibility warning.
    assert not any(
        "differs from the inferred direction" in w for w in result.warnings
    ), f"unexpected mismatch warning, got: {result.warnings!r}"
    # No direction-declaration-related warning at all.
    assert not any(
        "DECREASING" in w or "BIDIRECTIONAL" in w or "UNKNOWN" in w
        for w in result.warnings
    ), f"unexpected direction warning, got: {result.warnings!r}"
    # Declared value is preserved.
    assert result.direction is Direction.DECREASING
    assert result.lower_spec == 90.0
    assert result.upper_spec == 110.0


def test_declared_increasing_with_both_specs_no_warning() -> None:
    """The degradant-like case: both spec limits present, ``increasing``
    declared. This is normal and must NOT warn.

    A degradant dataset can record an upper spec (the NMT limit) and
    a lower spec (e.g. a control / placebo baseline) while the trend
    itself is purely increasing — declared ``increasing`` with both
    specs present is the standard shape and must not be flagged.
    """
    df = _frame_with_specs(lower=0.0, upper=2.0, has_direction=False)
    df["direction"] = "increasing"
    result = validate_and_select(df, attribute="assay", condition="25C/60RH")
    assert not any(
        "differs from the inferred direction" in w for w in result.warnings
    ), f"unexpected mismatch warning, got: {result.warnings!r}"
    assert not any(
        "INCREASING" in w or "DECREASING" in w or "BIDIRECTIONAL" in w
        or "UNKNOWN" in w
        for w in result.warnings
    ), f"unexpected direction warning, got: {result.warnings!r}"
    assert result.direction is Direction.INCREASING
    assert result.lower_spec == 0.0
    assert result.upper_spec == 2.0


def test_declared_decreasing_without_lower_spec_warns() -> None:
    """Declared ``decreasing`` with no ``lower_spec`` is a true
    incompatibility — a decreasing trend cannot be evaluated without
    a lower bound. The schema must record a warning."""
    df = _frame_with_specs(lower=None, upper=110.0, has_direction=True)
    result = validate_and_select(df, attribute="assay", condition="25C/60RH")
    assert any(
        "DECREASING" in w and "lower_spec" in w for w in result.warnings
    ), f"expected a DECREASING/lower_spec warning, got: {result.warnings!r}"
    # The declared value still wins (no silent override).
    assert result.direction is Direction.DECREASING
    assert result.lower_spec is None
    assert result.upper_spec == 110.0


def test_declared_increasing_without_upper_spec_warns() -> None:
    """Declared ``increasing`` with no ``upper_spec`` is a true
    incompatibility — an increasing trend cannot be evaluated without
    an upper bound. The schema must record a warning."""
    df = _frame_with_specs(lower=90.0, upper=None, has_direction=False)
    df["direction"] = "increasing"
    result = validate_and_select(df, attribute="assay", condition="25C/60RH")
    assert any(
        "INCREASING" in w and "upper_spec" in w for w in result.warnings
    ), f"expected an INCREASING/upper_spec warning, got: {result.warnings!r}"
    # The declared value still wins (no silent override).
    assert result.direction is Direction.INCREASING
    assert result.lower_spec == 90.0
    assert result.upper_spec is None


def test_declared_bidirectional_with_only_one_spec_warns() -> None:
    """Declared ``bidirectional`` with only one spec limit present is
    a true incompatibility — the caller may have meant a single
    direction. The schema must record a warning."""
    df = _frame_with_specs(lower=90.0, upper=None, has_direction=False)
    df["direction"] = "bidirectional"
    result = validate_and_select(df, attribute="assay", condition="25C/60RH")
    assert any(
        "BIDIRECTIONAL" in w for w in result.warnings
    ), f"expected a BIDIRECTIONAL warning, got: {result.warnings!r}"
    # Declared value still wins.
    assert result.direction is Direction.BIDIRECTIONAL
    assert result.lower_spec == 90.0
    assert result.upper_spec is None


def test_declared_unknown_warns() -> None:
    """Declared ``unknown`` is a v0.1 weak path — the crossing math is
    heuristic for it. The schema must record a warning."""
    df = _frame_with_specs(lower=90.0, upper=110.0, has_direction=False)
    df["direction"] = "unknown"
    result = validate_and_select(df, attribute="assay", condition="25C/60RH")
    assert any(
        "UNKNOWN" in w for w in result.warnings
    ), f"expected an UNKNOWN warning, got: {result.warnings!r}"
    # Declared value is preserved (UNKNOWN is a valid Direction value).
    assert result.direction is Direction.UNKNOWN
    assert result.lower_spec == 90.0
    assert result.upper_spec == 110.0
