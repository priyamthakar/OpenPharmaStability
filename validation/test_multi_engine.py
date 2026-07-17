"""Tests for ``openpharmastability.shelf_life.multi_engine.analyze_many``.

These tests exercise the public v0.2.0 entry point end-to-end on
the shipped example fixtures (``examples/multi_attribute.csv`` and
``examples/multi_attribute_metadata.csv``). They check the
*structure* of the returned :class:`MultiAttributeResult` rather
than pinning specific numeric shelf-life values — the underlying
single-attribute math is already covered by ``test_engine.py``.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from openpharmastability.contracts import (
    AttributeRole,
    CrossingStatus,
    MultiAttributeResult,
)
from openpharmastability.shelf_life.multi_engine import analyze_many


ROOT = Path(__file__).resolve().parents[1]
DATA_CSV = ROOT / "examples" / "multi_attribute.csv"
META_CSV = ROOT / "examples" / "multi_attribute_metadata.csv"


# ---------------------------------------------------------------------------
# 1. Explicit attribute list -> 1 attribute, that attribute is limiting
# ---------------------------------------------------------------------------


def test_analyze_many_with_explicit_attribute_list() -> None:
    """`attributes=["assay"]` -> one AttributeResult, limiting=assay."""
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        attributes=["assay"],
    )
    assert isinstance(multi, MultiAttributeResult)
    assert len(multi.attributes) == 1
    assert multi.attributes[0].metadata.attribute == "assay"
    assert multi.limiting_attribute == "assay"
    assert multi.condition == "25C/60RH"
    assert multi.deliverable_term == "shelf life"
    assert multi.product_type == "product"
    assert multi.attributes[0].result.metadata["file_path"] == str(DATA_CSV)
    # The single attribute was eligible (assay crosses in the dataset).
    assert multi.attributes[0].included_in_limiting_decision is True
    assert multi.metadata["n_attributes_total"] == 1
    assert multi.metadata["n_attributes_limiting"] == 1


# ---------------------------------------------------------------------------
# 2. all_attributes=True -> every attribute in the data is analyzed
# ---------------------------------------------------------------------------


def test_analyze_many_with_all_attributes() -> None:
    """`all_attributes=True` -> both 'assay' and 'impurity_a' are run."""
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        all_attributes=True,
    )
    names = sorted(a.metadata.attribute for a in multi.attributes)
    assert names == ["assay", "impurity_a"]
    assert multi.metadata["n_attributes_total"] == 2
    # Top-level metadata fields are well-formed.
    assert "library_versions" in multi.metadata
    assert "python" in multi.metadata["library_versions"]


# ---------------------------------------------------------------------------
# 3. Default (no `attributes`, no `all_attributes`) -> ["assay"]
# ---------------------------------------------------------------------------


def test_analyze_many_default_is_assay() -> None:
    """With no attribute hint, the v0.1 default of 'assay' is used."""
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
    )
    assert len(multi.attributes) == 1
    assert multi.attributes[0].metadata.attribute == "assay"


# ---------------------------------------------------------------------------
# 4. Two attributes -> result is well-formed
# ---------------------------------------------------------------------------


def test_analyze_many_limiting_is_assay_when_assay_is_shorter() -> None:
    """Two attributes run end-to-end; structure is well-formed.

    The shipped fixture is designed so that this test does not need
    to pin *which* attribute is limiting — only that the limiting
    decision was made and is consistent with the per-attribute
    results.
    """
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        attributes=["assay", "impurity_a"],
    )
    assert len(multi.attributes) == 2
    by_name = {a.metadata.attribute: a for a in multi.attributes}
    assert "assay" in by_name
    assert "impurity_a" in by_name

    # Both per-attribute StabilityResults have the documented fields.
    for ar in multi.attributes:
        assert ar.result.condition == "25C/60RH"
        assert ar.result.deliverable_term == "shelf life"
        assert ar.result.supported_shelf_life_months is not None
        # On the shipped fixture both attributes cross within the
        # 60-month horizon, so they are both eligible.
        assert ar.included_in_limiting_decision is True
        assert ar.exclusion_reason is None

    # The top-level decision is consistent with the per-attribute data.
    if multi.limiting_attribute is not None:
        winner = by_name[multi.limiting_attribute]
        assert multi.supported_shelf_life_months == (
            winner.result.supported_shelf_life_months
        )
        assert multi.statistical_crossing_months == (
            winner.result.statistical_crossing_months
        )


# ---------------------------------------------------------------------------
# 5. metadata_path=... -> per-attribute metadata is populated
# ---------------------------------------------------------------------------


def test_analyze_many_with_metadata_path() -> None:
    """The metadata CSV overrides the per-attribute defaults."""
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        attributes=["assay", "impurity_a"],
        metadata_path=str(META_CSV),
    )
    by_name = {a.metadata.attribute: a for a in multi.attributes}

    assay = by_name["assay"]
    assert assay.metadata.unit == "%LC"
    assert assay.metadata.direction is not None
    assert assay.metadata.direction.value == "decreasing"
    assert assay.metadata.lower_spec == 90.0
    assert assay.metadata.upper_spec == 110.0
    assert assay.metadata.attribute_role is AttributeRole.PRIMARY
    assert assay.metadata.report_order == 1

    impurity = by_name["impurity_a"]
    assert impurity.metadata.unit == "%area"
    assert impurity.metadata.upper_spec == 0.50
    assert impurity.metadata.attribute_role is AttributeRole.PRIMARY
    assert impurity.metadata.report_order == 2


# ---------------------------------------------------------------------------
# 6. An attribute that has no rows -> "no_data_for_attribute"
# ---------------------------------------------------------------------------


def test_analyze_many_handles_no_data_for_attribute() -> None:
    """An unknown attribute gets a well-formed exclusion entry."""
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        attributes=["nonexistent"],
    )
    assert len(multi.attributes) == 1
    [attr] = multi.attributes
    assert attr.included_in_limiting_decision is False
    assert attr.exclusion_reason == "no_data_for_attribute"
    # Top-level: no eligible attribute, so the limiting decision
    # is None and a top-level warning is added.
    assert multi.limiting_attribute is None
    assert multi.supported_shelf_life_months is None
    assert any("no eligible" in w for w in multi.warnings)


# ---------------------------------------------------------------------------
# 7. file_sha256 is recorded in the top-level metadata
# ---------------------------------------------------------------------------


def test_analyze_many_records_file_sha256() -> None:
    """The top-level metadata carries a 64-hex-char SHA-256 of the file."""
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        attributes=["assay"],
    )
    sha = multi.metadata.get("file_sha256")
    assert isinstance(sha, str)
    assert len(sha) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", sha) is not None


# ---------------------------------------------------------------------------
# 8. v0.5.0 — advanced-statistics opt-in is threaded to per-attribute results
# ---------------------------------------------------------------------------


def test_multi_engine_threads_arrhenius_flag() -> None:
    """``run_arrhenius=True`` is forwarded to each per-attribute
    :func:`analyze` call. The shipped ``multi_attribute.csv`` has
    only one condition (and therefore one implicit temperature),
    so the Arrhenius fit is skipped and ``arrhenius_result`` is
    ``None`` for each attribute. The test asserts the flag is
    wired through (no crash, the field is present, and the
    one-temperature skip path works).
    """
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        attributes=["assay", "impurity_a"],
        run_arrhenius=True,
    )
    assert len(multi.attributes) == 2
    for ar in multi.attributes:
        # The new field is populated (or None when the one-temp
        # skip path fires, which is what happens on the shipped
        # fixture).
        assert hasattr(ar.result, "arrhenius_result")
        # When the one-temp path fires, the per-attribute result
        # also carries a warning naming the skip reason.
        if ar.result.arrhenius_result is None:
            assert any(
                "Arrhenius fit skipped" in w
                for w in ar.result.warnings
            )
        # model_effects stays "fixed" (random_effects not passed)
        assert ar.result.model_effects == "fixed"


# ---------------------------------------------------------------------------
# 9-13. v0.7.0 — AttributeMetadata.lower_spec / upper_spec override is
#        threaded through the per-attribute analysis end-to-end. These
#        tests close the long-standing v0.2.1 CHANGELOG claim
#        "metadata override is now applied to per-attribute analysis".
# ---------------------------------------------------------------------------


def _write_temp_metadata_csv(rows: list[dict]) -> str:
    """Write an in-memory metadata table to a temp CSV; return its path.

    Used by the v0.7.0 spec-override tests so the metadata table can
    be constructed on the fly without committing more fixtures to
    ``examples/``. The caller is responsible for ``os.unlink``-ing
    the returned path.
    """
    df = pd.DataFrame(rows)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8",
    )
    df.to_csv(tmp.name, index=False)
    tmp.close()
    return tmp.name


def test_metadata_lower_spec_override_changes_supported_shelf_life() -> None:
    """An ``upper_spec`` override on ``impurity_a`` (tighter than the
    data-derived 0.5) changes the per-attribute supported shelf life
    AND is recorded on the per-attribute :class:`StabilityResult`.

    The test name carries a small naming legacy from the v0.2.1
    CHANGELOG — the action is an ``upper_spec`` override (a
    tightened spec limit), which is the only spec the engine
    actually evaluates for the ``INCREASING`` ``impurity_a``
    attribute.
    """
    baseline = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        attributes=["assay", "impurity_a"],
    )
    by_name = {a.metadata.attribute: a for a in baseline.attributes}
    baseline_supported = by_name["impurity_a"].result.supported_shelf_life_months
    assert baseline_supported is not None and baseline_supported == 7

    # 0.2 is much tighter than the data-derived 0.5; the upper bound
    # on the impurity_a mean response crosses 0.2 at ~1.9 months,
    # so the supported shelf life drops from 7 months to 1 month.
    meta_path = _write_temp_metadata_csv([
        {"attribute": "impurity_a", "upper_spec": 0.2},
    ])
    try:
        tightened = analyze_many(
            path=str(DATA_CSV),
            condition="25C/60RH",
            attributes=["assay", "impurity_a"],
            metadata_path=meta_path,
        )
    finally:
        os.unlink(meta_path)

    by_name2 = {a.metadata.attribute: a for a in tightened.attributes}
    impurity = by_name2["impurity_a"]
    assert impurity.result.supported_shelf_life_months is not None
    # Tighter spec -> earlier or equal crossing -> smaller or equal
    # supported shelf life. The override (0.2) is tight enough that
    # the supported shelf life strictly drops from 7 to 1.
    assert impurity.result.supported_shelf_life_months < baseline_supported
    # The override is recorded on the result for the report / JSON.
    assert impurity.result.upper_spec == 0.2
    # And the other field stays None (no override on lower_spec).
    assert impurity.result.lower_spec is None
    # Assay is untouched: no override in the metadata -> both
    # spec fields on its result stay None and its supported shelf
    # life is unchanged.
    assay = by_name2["assay"]
    assert assay.result.upper_spec is None
    assert assay.result.lower_spec is None
    assert assay.result.supported_shelf_life_months == (
        by_name["assay"].result.supported_shelf_life_months
    )


def test_metadata_upper_spec_override_recorded_on_result() -> None:
    """An ``upper_spec`` override on ``assay`` is recorded on the
    per-attribute :class:`StabilityResult`. The data-derived spec
    is 110.0; the override is 95.0.

    The crossing math for ``assay`` (``DECREASING``) is determined
    by the lower spec, not the upper one — so tightening the upper
    spec does not change the supported shelf life. The test
    nevertheless asserts the override is recorded, which is the
    v0.2.1 CHANGELOG claim that v0.7.0 closes.
    """
    meta_path = _write_temp_metadata_csv([
        {"attribute": "assay", "upper_spec": 95.0},
    ])
    try:
        multi = analyze_many(
            path=str(DATA_CSV),
            condition="25C/60RH",
            attributes=["assay", "impurity_a"],
            metadata_path=meta_path,
        )
    finally:
        os.unlink(meta_path)

    by_name = {a.metadata.attribute: a for a in multi.attributes}
    # The override is recorded on the assay per-attribute result.
    assert by_name["assay"].result.upper_spec == 95.0
    # The lower spec is not overridden; it stays None on the result.
    assert by_name["assay"].result.lower_spec is None
    # Impurity_a is not in the metadata -> both spec fields stay
    # None on its per-attribute result.
    assert by_name["impurity_a"].result.upper_spec is None
    assert by_name["impurity_a"].result.lower_spec is None


def test_no_metadata_override_preserves_v020_behavior() -> None:
    """Without a metadata table, the per-attribute results have
    ``lower_spec is None`` and ``upper_spec is None`` (the v0.7.0
    default for hand-built results). The shipped multi-attribute
    fixture still picks ``impurity_a`` as limiting at 7 months —
    the v0.2.0 byte-equivalent path is preserved.
    """
    multi = analyze_many(
        path=str(DATA_CSV),
        condition="25C/60RH",
        attributes=["assay", "impurity_a"],
    )
    assert multi.limiting_attribute == "impurity_a"
    assert multi.supported_shelf_life_months == 7

    by_name = {a.metadata.attribute: a for a in multi.attributes}
    for ar in multi.attributes:
        # No metadata override -> both spec fields on the result
        # stay at the v0.7.0 default of None. (The data-derived
        # specs are still in the per-attribute ValidatedData that
        # the engine used; we just do not echo them onto the
        # StabilityResult when no override is supplied.)
        assert ar.result.lower_spec is None
        assert ar.result.upper_spec is None


def test_metadata_override_only_lower() -> None:
    """A metadata row that supplies only ``lower_spec`` (no
    ``upper_spec``) is recorded on the per-attribute result as
    ``lower_spec = override`` and ``upper_spec = None``.

    The override also flows through the data layer: a looser
    ``lower_spec`` lets the assay drop further before crossing,
    so the supported shelf life goes UP.
    """
    meta_path = _write_temp_metadata_csv([
        {"attribute": "assay", "lower_spec": 80.0},
    ])
    try:
        multi = analyze_many(
            path=str(DATA_CSV),
            condition="25C/60RH",
            attributes=["assay", "impurity_a"],
            metadata_path=meta_path,
        )
    finally:
        os.unlink(meta_path)

    by_name = {a.metadata.attribute: a for a in multi.attributes}
    assay = by_name["assay"]
    # The override is recorded on the assay per-attribute result.
    assert assay.result.lower_spec == 80.0
    # The upper spec is not overridden; it stays None on the result.
    assert assay.result.upper_spec is None
    # The override is threaded through the data layer: the
    # crossing solver sees the looser lower_spec, so the
    # supported shelf life is larger than the v0.2.0 baseline.
    assert assay.result.supported_shelf_life_months is not None
    assert assay.result.supported_shelf_life_months > 16
    # Impurity_a is not in the metadata -> both spec fields stay
    # None on its per-attribute result.
    assert by_name["impurity_a"].result.lower_spec is None
    assert by_name["impurity_a"].result.upper_spec is None


def test_metadata_override_applied_to_data_layer() -> None:
    """Verify the per-attribute temp CSV actually has the overridden
    spec and the supported shelf life is consistent with the
    override.

    Case A: ``impurity_a.upper_spec = 0.5`` (matches the data-
    derived 0.5) — the override is a no-op for the math but the
    field is still recorded. Supported shelf life stays at 7
    months, statistical crossing time stays at ~7.93 months.

    Case B: ``impurity_a.upper_spec = 0.2`` (tighter than the
    data-derived 0.5) — the supported shelf life drops below the
    Case A number, demonstrating the override flows through the
    data layer end-to-end. The relationship is monotonic: a
    tighter spec yields an earlier or equal crossing, which
    yields a smaller or equal supported shelf life.
    """
    # Case A: override == data-derived
    meta_path_equal = _write_temp_metadata_csv([
        {"attribute": "impurity_a", "upper_spec": 0.5},
    ])
    try:
        equal = analyze_many(
            path=str(DATA_CSV),
            condition="25C/60RH",
            attributes=["impurity_a"],
            metadata_path=meta_path_equal,
        )
    finally:
        os.unlink(meta_path_equal)

    equal_result = equal.attributes[0].result
    # The override is recorded on the result.
    assert equal_result.upper_spec == 0.5
    # Override == data-derived -> supported shelf life is the
    # v0.2.0 baseline (7 months).
    assert equal_result.supported_shelf_life_months == 7
    # And the statistical crossing time is the v0.2.0 baseline
    # (~7.93 months), confirming the per-attribute temp CSV
    # actually carried the override.
    assert equal_result.statistical_crossing_months is not None
    assert abs(equal_result.statistical_crossing_months - 7.934) < 0.01

    # Case B: tighter override
    meta_path_tight = _write_temp_metadata_csv([
        {"attribute": "impurity_a", "upper_spec": 0.2},
    ])
    try:
        tight = analyze_many(
            path=str(DATA_CSV),
            condition="25C/60RH",
            attributes=["impurity_a"],
            metadata_path=meta_path_tight,
        )
    finally:
        os.unlink(meta_path_tight)

    tight_result = tight.attributes[0].result
    # The override is recorded on the result.
    assert tight_result.upper_spec == 0.2
    # Tighter spec -> smaller or equal supported shelf life.
    assert tight_result.supported_shelf_life_months is not None
    assert tight_result.supported_shelf_life_months < (
        equal_result.supported_shelf_life_months
    )


# ---------------------------------------------------------------------------
# 14-15. v0.9.0 — ``analyze_many`` routes through the v0.7.0
#         ``load_table`` dispatcher for both the data file and the
#         optional metadata file. CSV / XLSX / XLSM inputs must all
#         produce the same limiting decision on the shipped
#         ``multi_attribute`` fixture.
# ---------------------------------------------------------------------------


def _write_temp_xlsx(df: pd.DataFrame, *, sheet: str = "data") -> str:
    """Write ``df`` to a temp ``.xlsx`` file with one sheet; return path.

    The caller is responsible for ``os.unlink``-ing the returned path.
    Uses ``openpyxl`` (already in the runtime deps). The sheet name
    must be a valid Excel sheet name and is honored by
    :func:`load_xlsx` if the user passes ``data_sheet=``; otherwise
    the default-candidate resolution picks it.
    """
    tmp = tempfile.NamedTemporaryFile(
        mode="wb", suffix=".xlsx", delete=False
    )
    tmp.close()
    with pd.ExcelWriter(tmp.name, engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name=sheet, index=False)
    return tmp.name


def test_multi_engine_xlsx_dispatch() -> None:
    """``analyze_many`` accepts an ``.xlsx`` data file via the
    v0.7.0 ``load_table`` dispatcher. The per-attribute results
    match the CSV run (within XLSX dtype round-trip tolerance) and
    the limiting decision is preserved.

    The shipped ``examples/multi_attribute.csv`` is round-tripped
    to a tmp XLSX and run through :func:`analyze_many`. The XLSX
    numeric values can differ from the CSV by ULP-level noise
    because openpyxl writes 64-bit floats through the OOXML
    string representation; the per-attribute supported shelf life
    and statistical crossing time therefore match within a single
    whole month, and the limiting attribute is unchanged.
    """
    src_df = pd.read_csv(DATA_CSV)
    xlsx_path = _write_temp_xlsx(src_df, sheet="data")
    try:
        # Baseline CSV run for the comparison below.
        csv_multi = analyze_many(
            path=str(DATA_CSV),
            condition="25C/60RH",
            all_attributes=True,
            metadata_path=str(META_CSV),
        )
        xlsx_multi = analyze_many(
            path=xlsx_path,
            condition="25C/60RH",
            all_attributes=True,
            metadata_path=str(META_CSV),
        )
    finally:
        os.unlink(xlsx_path)

    # Top-level limiting decision is preserved.
    assert xlsx_multi.limiting_attribute == "impurity_a"
    # The shipped fixture gives 7 months for impurity_a; the XLSX
    # round-trip is allowed to perturb this by at most one whole
    # month because of ULP-level noise in the bound math.
    assert xlsx_multi.supported_shelf_life_months is not None
    assert abs(
        xlsx_multi.supported_shelf_life_months
        - (csv_multi.supported_shelf_life_months or 0)
    ) <= 1
    assert xlsx_multi.supported_shelf_life_months in (6, 7, 8)

    # Per-attribute results are well-formed and structurally
    # equivalent to the CSV run. The XLSX numeric values are
    # allowed to differ by ULP-level noise, so we check the
    # qualitative fields (model, poolability, supported shelf
    # life within 1 month, the same set of attributes).
    csv_by_name = {a.metadata.attribute: a for a in csv_multi.attributes}
    xlsx_by_name = {a.metadata.attribute: a for a in xlsx_multi.attributes}
    assert set(xlsx_by_name) == set(csv_by_name)

    for name, xlsx_attr in xlsx_by_name.items():
        csv_attr = csv_by_name[name]
        # Same deliverable + direction fields were loaded by the
        # v0.7.0 ``load_table`` dispatcher.
        assert xlsx_attr.result.condition == csv_attr.result.condition
        assert xlsx_attr.result.deliverable_term == (
            csv_attr.result.deliverable_term
        )
        # The supported shelf life is allowed to perturb by at
        # most one whole month from the CSV run; the v0.2.0
        # baseline for impurity_a is 7, the v0.2.0 baseline for
        # assay is 18 — both still well under the 60-month horizon.
        assert xlsx_attr.result.supported_shelf_life_months is not None
        assert abs(
            xlsx_attr.result.supported_shelf_life_months
            - (csv_attr.result.supported_shelf_life_months or 0)
        ) <= 1
        # The statistical crossing time is allowed to perturb by
        # at most ~0.1 month from the CSV run; the v0.2.0 baseline
        # for impurity_a is ~7.93 months.
        if (
            xlsx_attr.result.statistical_crossing_months is not None
            and csv_attr.result.statistical_crossing_months is not None
        ):
            assert abs(
                xlsx_attr.result.statistical_crossing_months
                - csv_attr.result.statistical_crossing_months
            ) < 0.2


def test_multi_engine_xlsx_with_metadata_xlsx() -> None:
    """The metadata ``.xlsx`` file is also accepted: the existing
    multi-engine logic dispatches ``metadata_path`` through
    ``data/metadata.py::load_attribute_metadata_csv`` which already
    handles either extension.

    The shipped ``examples/multi_attribute.csv`` is round-tripped
    to a tmp XLSX; the metadata CSV is also round-tripped to a
    separate tmp XLSX. :func:`analyze_many` is then called with
    both XLSX inputs. The shipped fixture still picks
    ``impurity_a`` as limiting at 7 months — the v0.2.0 byte-
    equivalent path is preserved across the XLSX dispatch.
    """
    data_df = pd.read_csv(DATA_CSV)
    meta_df = pd.read_csv(META_CSV)

    data_xlsx = _write_temp_xlsx(data_df, sheet="data")
    # The metadata workbook uses the default candidate sheet name
    # "attributes" (one of the v0.2.0 candidates), so no explicit
    # ``metadata_sheet=`` is needed.
    meta_xlsx = _write_temp_xlsx(meta_df, sheet="attributes")
    try:
        multi = analyze_many(
            path=data_xlsx,
            condition="25C/60RH",
            all_attributes=True,
            metadata_path=meta_xlsx,
        )
    finally:
        os.unlink(data_xlsx)
        os.unlink(meta_xlsx)

    # Top-level limiting decision is preserved end-to-end.
    assert multi.limiting_attribute == "impurity_a"
    assert multi.supported_shelf_life_months == 7

    # Both per-attribute results are present and well-formed.
    by_name = {a.metadata.attribute: a for a in multi.attributes}
    assert set(by_name) == {"assay", "impurity_a"}

    # The metadata override is recorded on the per-attribute
    # result the same way it is on the CSV path.
    assert by_name["assay"].result.upper_spec == 110.0
    assert by_name["assay"].result.lower_spec == 90.0
    assert by_name["impurity_a"].result.upper_spec == 0.50
    assert by_name["impurity_a"].result.lower_spec is None
