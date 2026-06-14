"""Multi-attribute stability analysis (v0.2.0).

Wraps the existing single-attribute :func:`analyze` for each
attribute and assembles a :class:`MultiAttributeResult`.

Workflow
--------

1. Load the data (CSV or XLSX).
2. Normalize the requested condition.
3. Resolve the attribute list — explicit ``attributes`` arg, the
   full set of attributes in the data if ``all_attributes=True``,
   or the v0.1 default of ``["assay"]`` when neither is given.
4. Optionally load a per-attribute metadata table (CSV or XLSX
   sheet) and merge it into the per-attribute :class:`AttributeMetadata`
   objects.
5. For each attribute, write a one-attribute temporary CSV and
   call :func:`openpharmastability.shelf_life.engine.analyze`.
6. Hand the per-attribute results to
   :func:`openpharmastability.shelf_life.limiting.select_limiting`
   to compute the overall decision.
7. Attach the top-level reproducibility metadata
   (file SHA-256, library versions, row/column counts, etc.).

The temporary-CSV round-trip in step 5 is a small I/O cost we
accept in v0.2.0; the in-memory path is a v0.2.1 cleanup.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
import platform
import tempfile
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from openpharmastability.contracts import (
    AttributeMetadata,
    AttributeResult,
    CrossingResult,
    CrossingStatus,
    DiagnosticsResult,
    Direction,
    FitResult,
    ModelKind,
    MultiAttributeResult,
    Poolability,
    PoolabilityResult,
    StabilityResult,
    TOOL_VERSION,
)
from openpharmastability.data.conditions import parse_condition
from openpharmastability.data.io import load_table
from openpharmastability.data.metadata import (
    load_attribute_metadata_csv,
    load_attribute_metadata_from_dataframe,
)
from openpharmastability.data.xlsx import load_xlsx_sheet
from openpharmastability.shelf_life.engine import analyze
from openpharmastability.shelf_life.limiting import select_limiting


# Sheet-name candidates for the metadata workbook. The first match
# wins; otherwise the first sheet is used. These mirror the
# conventions used by the data layer.
_DEFAULT_METADATA_SHEETS = ("attributes", "metadata", "attribute_metadata")


def _is_xlsx(path: str) -> bool:
    return str(path).lower().endswith((".xlsx", ".xlsm"))


def _file_sha256(path: str) -> str:
    """Return the SHA-256 hex digest of the file at ``path``.

    Returns an empty string if the file does not exist (the
    caller decides whether that's an error).
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _lib_version(distribution: str) -> str:
    try:
        from importlib.metadata import version

        return version(distribution)
    except Exception:  # pragma: no cover — best-effort metadata
        return "unknown"


def _iso_now_or_epoch(source_epoch: int | None) -> str:
    """Honor ``source_epoch``, then ``$SOURCE_DATE_EPOCH``, then wall clock."""
    if source_epoch is None:
        env_val = os.environ.get("SOURCE_DATE_EPOCH")
        if env_val is not None and env_val.strip().isdigit():
            source_epoch = int(env_val.strip())
    if source_epoch is not None:
        return (
            datetime.fromtimestamp(source_epoch, tz=timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _deliverable_term_for(product_type: str) -> str:
    pt = product_type.strip().lower()
    if pt in ("substance", "drug_substance", "api"):
        return "retest period"
    return "shelf life"


def _empty_stability_result(
    attribute: str,
    condition: str,
    product_type: str,
) -> StabilityResult:
    """Minimal :class:`StabilityResult` for an attribute with no data rows.

    :func:`select_limiting` will mark this entry's
    ``included_in_limiting_decision=False`` with an appropriate
    ``exclusion_reason``; this helper exists only to give the
    overall MultiAttributeResult a well-formed entry to carry.
    """
    # A no-op callable for ``fitted_fn``. Tests / downstream code
    # that actually invokes it is out of scope for a "no data"
    # result.
    noop_fit = FitResult(
        kind=ModelKind.POOLED,
        params={},
        df_resid=0,
        s_resid=0.0,
        cov=np.zeros((0, 0)),
        fitted_fn=lambda *a, **k: (lambda t: float("nan")),
        design={},
        batches=[],
    )
    return StabilityResult(
        attribute=attribute,
        condition=condition,
        direction=Direction.UNKNOWN,
        model=ModelKind.POOLED,
        poolability=PoolabilityResult(
            decision=Poolability.FULL,
            p_slopes=1.0,
            p_intercepts=1.0,
            alpha=0.25,
            notes=["no data; poolability test not run"],
        ),
        fit=noop_fit,
        crossing=CrossingResult(
            crossing_months=None,
            status=CrossingStatus.NO_CROSSING,
            governing_batch=None,
            notes=["no rows for this attribute"],
        ),
        supported_shelf_life_months=None,
        statistical_crossing_months=None,
        observed_data_months=0.0,
        extrapolation_flag=False,
        diagnostics=DiagnosticsResult(
            linearity_ok=True,
            homoscedastic_ok=True,
            normal_resid_ok=True,
            influential_points=[],
            notes=["no data; no diagnostics run"],
        ),
        warnings=["no data for this attribute"],
        metadata={},
        deliverable_term=_deliverable_term_for(product_type),
        product_type=product_type,
        plot_filename="confidence_plot.png",
    )


def _apply_metadata_spec_to_frame(
    sub: pd.DataFrame,
    meta: AttributeMetadata,
) -> pd.DataFrame:
    """Replace per-row ``lower_spec`` / ``upper_spec`` columns with the
    metadata override values, if any.

    The metadata override must win over the per-row data values for
    the per-attribute analysis. The cleanest seam is to write the
    override into the per-attribute temp CSV before it is handed to
    :func:`analyze`; the single-attribute engine reads the spec
    limits from the CSV columns, so an in-place override flows
    naturally through the crossing solver, the bound math, the
    JSON record, and the HTML report.

    No-op when both ``meta.lower_spec`` and ``meta.upper_spec`` are
    ``None`` — the caller's frame is returned unchanged (byte-
    equivalent to v0.2.0). When only one of the two is supplied,
    only that column is overwritten; the other side is left as
    the data-derived value so the per-attribute engine still has a
    usable spec for the unspecified bound.
    """
    if meta.lower_spec is None and meta.upper_spec is None:
        return sub
    if meta.lower_spec is not None and "lower_spec" in sub.columns:
        sub["lower_spec"] = float(meta.lower_spec)
    if meta.upper_spec is not None and "upper_spec" in sub.columns:
        sub["upper_spec"] = float(meta.upper_spec)
    return sub


def _write_temp_csv(df: pd.DataFrame) -> str:
    """Write a per-attribute subset to a temporary CSV file; return path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".csv",
        delete=False,
        encoding="utf-8",
    )
    df.to_csv(tmp.name, index=False)
    tmp.close()
    return tmp.name


def _apply_metadata_to_stability_result(
    single: StabilityResult,
    meta: AttributeMetadata,
) -> StabilityResult:
    """Overlay :class:`AttributeMetadata` overrides onto a per-attribute
    :class:`StabilityResult` and return a new instance.

    The single-attribute :func:`analyze` infers direction from the
    per-row data columns. The metadata table provides an explicit
    override. The metadata override must win.

    v0.7.0 update: ``lower_spec`` / ``upper_spec`` overrides are
    honored end-to-end. The per-row spec columns on the per-attribute
    temp CSV are overwritten with the override values before
    :func:`analyze` runs (see :func:`_apply_metadata_spec_to_frame`),
    so the crossing solver and the bound math see the override as
    the data-derived spec. This helper additionally records the
    override on the :class:`StabilityResult` itself so the JSON
    decision record and the HTML report carry the values the
    engine actually used. ``direction`` continues to be applied
    post-hoc the same way it was in v0.2.0 (the per-row direction
    column is unchanged; only the field on the result is patched).

    We always return a *new* :class:`StabilityResult` (via
    :func:`dataclasses.replace`) because downstream code treats the
    result as immutable. When the metadata supplies no override at
    all, the original result is returned untouched (byte-equivalent
    to v0.2.0 for the ``assay``/``impurity_a`` case).
    """
    updates: dict[str, object] = {}
    if meta.direction is not None:
        updates["direction"] = meta.direction
    if meta.lower_spec is not None:
        updates["lower_spec"] = meta.lower_spec
    if meta.upper_spec is not None:
        updates["upper_spec"] = meta.upper_spec
    if not updates:
        return single
    return dataclasses.replace(single, **updates)


def _load_metadata(
    data_path: str,
    metadata_path: Optional[str],
    metadata_sheet: Optional[str],
) -> dict[str, AttributeMetadata]:
    """Load the optional per-attribute metadata table.

    Resolves four cases in priority order:

    1. ``metadata_path`` is an XLSX file -> load the named
       ``metadata_sheet`` (or the default candidate) from it.
    2. ``metadata_path`` is a CSV file -> use
       :func:`load_attribute_metadata_csv`.
    3. ``data_path`` is an XLSX file AND ``metadata_sheet`` is
       provided (or a default sheet exists) AND ``metadata_path`` is
       not -> load the metadata sheet from the same workbook.
    4. None of the above -> empty dict (silent fallback).

    Returns a dict keyed by attribute name. Raises ``ValueError``
    when the caller explicitly asked for a metadata sheet and the
    sheet could not be resolved.
    """
    out: dict[str, AttributeMetadata] = {}

    if metadata_path is not None:
        # Separate file path was given.
        if _is_xlsx(metadata_path):
            df = load_xlsx_sheet(
                metadata_path, metadata_sheet, _DEFAULT_METADATA_SHEETS
            )
        else:
            df = pd.read_csv(metadata_path)
        items = load_attribute_metadata_from_dataframe(df)
        for m in items:
            out[m.attribute] = m
        return out

    if metadata_sheet is not None and _is_xlsx(data_path):
        # Metadata lives on a separate sheet of the data workbook.
        df = load_xlsx_sheet(
            data_path, metadata_sheet, _DEFAULT_METADATA_SHEETS
        )
        items = load_attribute_metadata_from_dataframe(df)
        for m in items:
            out[m.attribute] = m
        return out

    if _is_xlsx(data_path):
        # metadata_sheet is None; try the default candidate names
        # silently. If none match, fall back to no metadata.
        try:
            df = load_xlsx_sheet(data_path, None, _DEFAULT_METADATA_SHEETS)
        except (ValueError, KeyError):
            return out
        # The default candidate must produce a frame that looks like
        # an attribute-metadata table (must have an 'attribute'
        # column). Otherwise we silently treat it as no metadata.
        if "attribute" in df.columns:
            items = load_attribute_metadata_from_dataframe(df)
            for m in items:
                out[m.attribute] = m
        return out

    return out


def analyze_many(
    path: str,
    condition: str,
    attributes: Optional[list[str]] = None,
    all_attributes: bool = False,
    metadata_path: Optional[str] = None,
    data_sheet: Optional[str] = None,
    metadata_sheet: Optional[str] = None,
    product_type: str = "product",
    horizon: float = 60.0,
    replicate_policy: str = "individual",
    bql_policy: str = "exclude",
    assess_transforms: bool = False,
    seed: Optional[int] = None,
    source_epoch: Optional[int] = None,
    # v0.4.0 ICH Q1A significant-change gate. Threaded through to
    # the per-attribute single-attribute ``analyze()`` call. The
    # limiting-decision logic below is unchanged.
    accelerated_condition: Optional[str] = "40C/75RH",
    intermediate_condition: Optional[str] = "30C/65RH",
    assay_change_threshold: float = 5.0,
    no_significant_change_gate: bool = False,
    # v0.5.0 advanced-statistics opt-ins. Threaded through to the
    # per-attribute single-attribute ``analyze()`` call so each
    # ``StabilityResult`` carries the v0.5.0 fields
    # (``arrhenius_result``, ``mkt_celsius``,
    # ``reduced_design_report``, ``model_effects``). The
    # limiting-decision logic below is unchanged.
    run_arrhenius: bool = False,
    arrhenius_storage_temp_C: float = 25.0,
    run_mkt: bool = False,
    mkt_ea_kJ_per_mol: float = 83.144,
    detect_reduced_design: bool = False,
    random_effects: bool = False,
) -> MultiAttributeResult:
    """Run a multi-attribute stability analysis.

    Parameters
    ----------
    path:
        Path to the input data file (CSV or XLSX).
    condition:
        The storage condition to analyze. Will be normalized via
        :func:`parse_condition`.
    attributes:
        Explicit list of attribute names to analyze. Mutually
        exclusive in spirit with ``all_attributes``; if both are
        provided, the explicit list wins and ``all_attributes`` is
        ignored (no error).
    all_attributes:
        If True and ``attributes`` is not given, analyze every
        attribute that appears in the data.
    metadata_path:
        Optional path to a per-attribute metadata table (CSV or
        XLSX sheet).
    data_sheet / metadata_sheet:
        Sheet names for XLSX inputs.
    product_type:
        ``"product"`` (default) or ``"substance"``.
    horizon:
        Maximum crossing-search time, in months. Default 60.
    replicate_policy:
        Forwarded to the single-attribute :func:`analyze`.
    bql_policy:
        Accepted for v0.2.1 forward compatibility; not yet applied
        inside the v0.1 single-attribute path.
    seed:
        Recorded in the top-level metadata.
    source_epoch:
        Optional Unix-epoch seconds used to pin the timestamp.
    run_arrhenius, arrhenius_storage_temp_C, run_mkt, mkt_ea_kJ_per_mol,
    detect_reduced_design, random_effects:
        v0.5.0 advanced-statistics opt-ins. Forwarded as a block
        to the per-attribute single-attribute :func:`analyze` call.
        The limiting-decision logic above is unchanged; each
        per-attribute :class:`StabilityResult` carries the
        corresponding new fields (``arrhenius_result``,
        ``mkt_celsius``, ``reduced_design_report``,
        ``model_effects``). All default-safe — when none are
        passed, behavior is byte-equivalent to v0.4.0.

    Returns
    -------
    MultiAttributeResult
        The full per-attribute results plus the overall limiting
        decision.
    """
    # 1) Load data via the v0.7.0 dispatcher. ``load_table`` accepts
    #    ``.csv`` / ``.xlsx`` / ``.xlsm`` / ``.xls`` by extension and
    #    forwards ``sheet`` to the XLSX path. Mirrors the
    #    single-attribute :func:`engine.analyze` entry point.
    df = load_table(path, sheet=data_sheet)

    # 2) Normalize the condition
    condition_norm = parse_condition(condition)

    # 3) Resolve the attribute list
    if attributes is not None:
        # Explicit list wins over all_attributes if both were passed.
        attribute_names = [str(a) for a in attributes]
    elif all_attributes:
        if "attribute" in df.columns:
            present = df["attribute"].dropna().astype(str).unique().tolist()
            attribute_names = sorted(present)
        else:
            attribute_names = []
    else:
        # v0.1 default
        attribute_names = ["assay"]

    # 4) Optional metadata
    metadata_by_name = _load_metadata(path, metadata_path, metadata_sheet)

    # 5) Per-attribute analysis. We track which entries came from
    #    the "no data" path so analyze_many can surface a more
    #    specific ``exclusion_reason`` than ``select_limiting``'s
    #    generic classification.
    attribute_results: list[AttributeResult] = []
    no_data_indices: set[int] = set()
    for name in attribute_names:
        meta = metadata_by_name.get(name) or AttributeMetadata(attribute=name)

        if "attribute" in df.columns:
            sub = df[df["attribute"].astype(str) == str(name)].copy()
        else:
            sub = df.iloc[0:0].copy()

        if sub.empty:
            attribute_results.append(
                AttributeResult(
                    metadata=meta,
                    result=_empty_stability_result(
                        name, condition_norm, product_type
                    ),
                    included_in_limiting_decision=False,
                    exclusion_reason=None,  # refined below
                )
            )
            no_data_indices.add(len(attribute_results) - 1)
            continue

        # v0.7.0: honor AttributeMetadata.lower_spec / upper_spec
        # by writing the override into the per-row spec columns of
        # the per-attribute temp CSV. The single-attribute analyze()
        # reads the spec from those columns, so this seam is enough
        # to thread the override through the crossing solver, the
        # bound math, the JSON record, and the HTML report. No-op
        # when the metadata supplies no spec override for this
        # attribute, so existing v0.2.0 callers (and the v0.7.0
        # default-handling tests) are byte-equivalent.
        sub = _apply_metadata_spec_to_frame(sub, meta)

        tmp = _write_temp_csv(sub)
        try:
            single = analyze(
                path=tmp,
                condition=condition_norm,
                attribute=name,
                product_type=product_type,
                horizon=horizon,
                replicate_policy=replicate_policy,
                bql_policy=bql_policy,
                assess_transforms=assess_transforms,
                seed=seed,
                source_epoch=source_epoch,
                accelerated_condition=accelerated_condition,
                intermediate_condition=intermediate_condition,
                assay_change_threshold=assay_change_threshold,
                no_significant_change_gate=no_significant_change_gate,
                # v0.5.0 advanced-statistics opt-ins.
                run_arrhenius=run_arrhenius,
                arrhenius_storage_temp_C=arrhenius_storage_temp_C,
                run_mkt=run_mkt,
                mkt_ea_kJ_per_mol=mkt_ea_kJ_per_mol,
                detect_reduced_design=detect_reduced_design,
                random_effects=random_effects,
            )
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

        # FIX 1 (v0.2.1): overlay AttributeMetadata overrides onto
        # the per-attribute StabilityResult via dataclasses.replace.
        # The single-attribute analyze() infers direction from the
        # data; the metadata override must win.
        single = _apply_metadata_to_stability_result(single, meta)

        attribute_results.append(
            AttributeResult(
                metadata=meta,
                result=single,
                included_in_limiting_decision=True,  # refined by select_limiting
                exclusion_reason=None,
            )
        )

    # 6) Limiting decision
    deliverable_term = _deliverable_term_for(product_type)
    observed = max(
        (
            ar.result.observed_data_months
            for ar in attribute_results
            if ar.result.observed_data_months > 0
        ),
        default=0.0,
    )
    multi = select_limiting(
        attribute_results=attribute_results,
        deliverable_term=deliverable_term,
        product_type=product_type,
        condition=condition_norm,
        observed_data_months=observed,
    )

    # 5b) Post-process: surface "no_data_for_attribute" on the entries
    #     that came from the empty-path in step 5. ``select_limiting``
    #     only sees the per-attribute StabilityResult fields, so for
    #     an empty result it would otherwise classify the reason as
    #     "no_crossing" or "no_shelf_life" — less specific than
    #     "no_data_for_attribute", which the report (and the tests)
    #     rely on.
    if no_data_indices:
        for idx in no_data_indices:
            entry = multi.attributes[idx]
            if not entry.included_in_limiting_decision:
                multi.attributes[idx] = AttributeResult(
                    metadata=entry.metadata,
                    result=entry.result,
                    included_in_limiting_decision=False,
                    exclusion_reason="no_data_for_attribute",
                )

    # 7) Top-level metadata: file hash, library versions, etc.
    # FIX 6 (v0.2.1): MERGE into the dict that select_limiting
    # wrote, do NOT overwrite. select_limiting sets:
    #   deliverable_term, product_type, n_attributes_total,
    #   n_attributes_limiting, tie_break
    # We add the file/library reproducibility fields on top so
    # that none of select_limiting's keys are lost (especially
    # tie_break, which the report and downstream consumers rely
    # on).
    file_hash = _file_sha256(path) if os.path.exists(path) else ""
    merged = dict(multi.metadata)
    merged.update({
        "tool_version": TOOL_VERSION,
        "timestamp": _iso_now_or_epoch(source_epoch),
        "file_path": str(path),
        "file_sha256": file_hash,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "library_versions": {
            "python": platform.python_version(),
            "pandas": _lib_version("pandas"),
            "numpy": _lib_version("numpy"),
            "scipy": _lib_version("scipy"),
            "statsmodels": _lib_version("statsmodels"),
            "openpyxl": _lib_version("openpyxl"),
        },
        "random_seed": seed,
        "n_attributes_total": len(attribute_results),
        "n_attributes_limiting": sum(
            1 for a in attribute_results if a.included_in_limiting_decision
        ),
        "product_type": product_type,
        "deliverable_term": deliverable_term,
        "data_sheet": data_sheet,
        "metadata_sheet": metadata_sheet,
        "metadata_path": metadata_path,
    })
    multi.metadata = merged
    return multi


__all__ = ["analyze_many"]
