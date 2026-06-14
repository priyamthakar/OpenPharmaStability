"""Thin programmatic API for OpenPharmaStability v0.6.0.

Wraps the existing engine and artifact modules into a small set of
callable functions. Pure Python, no subprocess, no CLI. Use this
from notebooks, scripts, and any future HTTP / RPC layer.

The CLI (``openpharmastability.cli``) is the authoritative end-user
entry point and is implemented in terms of these functions.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional, Union

from openpharmastability.contracts import (
    ArrheniusShelfLife,
    MultiAttributeResult,
    ReportArtifact,
    SensitivityReport,
    StabilityResult,
    ValidatedData,
)
from openpharmastability.data.io import load_csv
from openpharmastability.data.schema import validate_and_select
from openpharmastability.data.xlsx import load_xlsx
from openpharmastability.plots.confidence_plot import make_confidence_plot
from openpharmastability.shelf_life.engine import analyze as _analyze_single
from openpharmastability.shelf_life.multi_engine import analyze_many as _analyze_many
from openpharmastability.stats.sensitivity import compute_sensitivity


# `reports.artifacts` is owned by a parallel build stream and may not
# be present at import time. We do a defensive import so the rest of
# the package remains importable; the actual feature call below
# raises a clear RuntimeError if the module is missing.
try:
    from openpharmastability.reports.artifacts import (
        make_report_artifact as _make_report_artifact,
    )
    _MISSING_ARTIFACTS_MODULE: Optional[BaseException] = None
except Exception as _exc:  # noqa: BLE001 -- import-time, surface at call
    _make_report_artifact = None
    _MISSING_ARTIFACTS_MODULE = _exc


_SINGLE_RESULT = Union[StabilityResult, MultiAttributeResult]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_xlsx_path(path: str) -> bool:
    """True when ``path`` looks like an XLSX/XLSM/XLS file path."""
    return str(path).lower().endswith((".xlsx", ".xlsm", ".xls"))


def _write_temp_csv(df) -> str:
    """Write ``df`` to a temporary CSV file and return its path.

    Mirrors the pattern used by ``openpharmastability.shelf_life.multi_engine``
    so the XLSX dispatcher's temp-file lifecycle is consistent across the
    package. The caller is responsible for ``os.unlink`` on the returned
    path; the public API wrappers below do that in a ``finally`` block.
    """
    tmp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".csv",
        delete=False,
        encoding="utf-8",
    )
    df.to_csv(tmp.name, index=False)
    tmp.close()
    return tmp.name


def _safe_unlink(path: Optional[str]) -> None:
    """Best-effort unlink that swallows ``OSError`` (e.g. already-removed)."""
    if path is None:
        return
    try:
        os.unlink(path)
    except OSError:
        pass


def _load_raw_dataframe(path: str, data_sheet: Optional[str]):
    """Load the raw data frame (CSV or XLSX) for re-validation.

    For XLSX inputs, the in-memory frame is written to a temporary
    CSV (deleted on return) so downstream :func:`validate_and_select`
    calls share the same load path. For CSV inputs, the path is
    returned as-is.

    Returns
    -------
    (df, cleanup_callable)
        The :class:`pandas.DataFrame` and a no-arg callable that the
        caller MUST invoke (it removes the temp CSV if one was
        created). For CSV inputs the cleanup is a no-op.
    """
    if _is_xlsx_path(path):
        df = load_xlsx(path, sheet_name=data_sheet)
        tmp_csv = _write_temp_csv(df)

        def _cleanup() -> None:
            _safe_unlink(tmp_csv)

        return df, _cleanup
    df = load_csv(path)
    return df, lambda: None


def _render_single_plot(
    result: StabilityResult,
    path: str,
    condition: str,
    attribute: str,
    out_dir: str,
    data_sheet: Optional[str] = None,
    replicate_policy: str = "individual",
    bql_policy: str = "exclude",
) -> str:
    """Render the single-attribute confidence plot to
    ``<out_dir>/confidence_plot.png`` and return its path.

    The data is re-loaded and re-validated so we can call
    :func:`make_confidence_plot` (which needs a
    :class:`ValidatedData`, not a :class:`StabilityResult`).
    """
    df, cleanup = _load_raw_dataframe(path, data_sheet)
    try:
        data = validate_and_select(
            df,
            attribute=attribute,
            condition=condition,
            replicate_policy=replicate_policy,
            bql_policy=bql_policy,
        )
    finally:
        cleanup()
    os.makedirs(out_dir, exist_ok=True)
    plot_path = str(Path(out_dir) / "confidence_plot.png")
    make_confidence_plot(result, data, plot_path)
    return plot_path


def _render_multi_plots(
    result: MultiAttributeResult,
    path: str,
    condition: str,
    out_dir: str,
    data_sheet: Optional[str] = None,
    replicate_policy: str = "individual",
    bql_policy: str = "exclude",
) -> list[str]:
    """Render per-attribute confidence plots to
    ``<out_dir>/<attribute>_confidence_plot.png`` and return the list
    of paths actually written.

    Attributes whose :func:`validate_and_select` step raises
    (typically: no rows for that attribute) are skipped silently so
    the artifact bundle still contains the eligible plots.
    """
    df, cleanup = _load_raw_dataframe(path, data_sheet)
    try:
        os.makedirs(out_dir, exist_ok=True)
        plot_paths: list[str] = []
        for ar in result.attributes:
            attr_name = ar.metadata.attribute
            try:
                data = validate_and_select(
                    df,
                    attribute=attr_name,
                    condition=condition,
                    replicate_policy=replicate_policy,
                    bql_policy=bql_policy,
                )
            except Exception:
                continue
            plot_path = str(Path(out_dir) / f"{attr_name}_confidence_plot.png")
            try:
                make_confidence_plot(ar.result, data, plot_path)
                plot_paths.append(plot_path)
            except Exception:
                continue
        return plot_paths
    finally:
        cleanup()


# ---------------------------------------------------------------------------
# Public API: single-attribute
# ---------------------------------------------------------------------------


def analyze_csv(
    path: str,
    condition: str,
    attribute: str = "assay",
    **kwargs,
) -> StabilityResult:
    """Single-attribute analysis of a CSV file.

    ``kwargs`` are forwarded to :func:`openpharmastability.shelf_life.engine.analyze`.
    See that function for the full list of options (v0.5.1+ supports
    ``run_arrhenius``, ``run_mkt``, ``detect_reduced_design``,
    ``random_effects``, ``accelerated_condition``,
    ``intermediate_condition``, ``assay_change_threshold``,
    ``no_significant_change_gate``, ``replicate_policy``,
    ``bql_policy``, ``assess_transforms``, ``seed``, ``source_epoch``,
    ``product_type``, ``horizon``, etc.).
    """
    return _analyze_single(
        path=path, condition=condition, attribute=attribute, **kwargs,
    )


def analyze_xlsx(
    path: str,
    condition: str,
    attribute: str = "assay",
    data_sheet: Optional[str] = None,
    **kwargs,
) -> StabilityResult:
    """Single-attribute analysis of an XLSX workbook.

    Loads the chosen worksheet via
    :func:`openpharmastability.data.xlsx.load_xlsx`, writes the frame to
    a temporary CSV, and calls :func:`analyze` on that CSV. The temp
    file is unlinked on every code path (success / exception).

    ``data_sheet`` selects the worksheet (default: the first sheet that
    matches the project's default candidates — ``"results"``, ``"data"``,
    ``"stability"`` — or the first sheet).
    """
    df = load_xlsx(path, sheet_name=data_sheet)
    tmp_csv = _write_temp_csv(df)
    try:
        return _analyze_single(
            path=tmp_csv, condition=condition, attribute=attribute, **kwargs,
        )
    finally:
        _safe_unlink(tmp_csv)


def analyze_path(
    path: str,
    condition: str,
    attribute: str = "assay",
    data_sheet: Optional[str] = None,
    **kwargs,
) -> StabilityResult:
    """Auto-detect CSV vs XLSX from the file extension and dispatch.

    ``.xlsx`` / ``.xlsm`` / ``.xls`` go through :func:`analyze_xlsx`;
    everything else goes through :func:`analyze_csv`.
    """
    if _is_xlsx_path(path):
        return analyze_xlsx(path, condition, attribute, data_sheet, **kwargs)
    return analyze_csv(path, condition, attribute, **kwargs)


# ---------------------------------------------------------------------------
# Public API: multi-attribute
# ---------------------------------------------------------------------------


def analyze_multi(
    path: str,
    condition: str,
    attributes: Optional[list[str]] = None,
    all_attributes: bool = False,
    metadata_path: Optional[str] = None,
    data_sheet: Optional[str] = None,
    metadata_sheet: Optional[str] = None,
    **kwargs,
) -> MultiAttributeResult:
    """Multi-attribute analysis. Thin wrapper around
    :func:`openpharmastability.shelf_life.multi_engine.analyze_many`.

    ``kwargs`` are forwarded to ``analyze_many``, which forwards them
    per-attribute to :func:`analyze`. See that function for the full
    list of supported options.
    """
    return _analyze_many(
        path=path,
        condition=condition,
        attributes=attributes,
        all_attributes=all_attributes,
        metadata_path=metadata_path,
        data_sheet=data_sheet,
        metadata_sheet=metadata_sheet,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Public API: artifact + one-shot convenience
# ---------------------------------------------------------------------------


def make_artifact(
    result: _SINGLE_RESULT,
    out_dir: str,
    *,
    plot_paths: Optional[list[str]] = None,
    inline_plot: bool = True,
    generate_pdf: bool = False,
) -> ReportArtifact:
    """Build a self-contained :class:`ReportArtifact` bundle in ``out_dir``.

    Thin wrapper around
    :func:`openpharmastability.reports.artifacts.make_report_artifact`.
    ``plot_paths`` defaults to a sensible per-result layout (single:
    ``confidence_plot.png`` in ``out_dir``; multi: one
    ``<attribute>_confidence_plot.png`` per attribute in ``out_dir``).
    Set ``generate_pdf=True`` to also produce a PDF copy (requires a
    PDF backend; the artifact helper raises :class:`RuntimeError` if
    none is available).
    """
    if _make_report_artifact is None:
        raise RuntimeError(
            "openpharmastability.reports.artifacts is not importable; "
            "the report-artifact feature is unavailable in this build. "
            f"Original error: {_MISSING_ARTIFACTS_MODULE!r}"
        )
    return _make_report_artifact(
        result=result,
        out_dir=out_dir,
        plot_paths=plot_paths,
        inline_plot=inline_plot,
        generate_pdf=generate_pdf,
    )


def analyze_and_artifact(
    path: str,
    condition: str,
    out_dir: str,
    *,
    attribute: str = "assay",
    attributes: Optional[list[str]] = None,
    all_attributes: bool = False,
    metadata_path: Optional[str] = None,
    data_sheet: Optional[str] = None,
    metadata_sheet: Optional[str] = None,
    inline_plot: bool = True,
    generate_pdf: bool = False,
    **kwargs,
) -> tuple[_SINGLE_RESULT, ReportArtifact]:
    """One-shot: analyze + write a self-contained artifact bundle.

    Dispatches to :func:`analyze_multi` when ``all_attributes`` is set
    or when ``attributes`` is a list of more than one entry; otherwise
    dispatches to :func:`analyze_path` (CSV / XLSX auto-detect). Then
    renders the canonical confidence plot(s) into ``out_dir`` and
    builds the artifact via :func:`make_artifact`. Returns the result
    and the artifact.

    ``kwargs`` are forwarded to the underlying analyze call. The
    replicate / BQL policies (``replicate_policy``, ``bql_policy``)
    are also forwarded — they are used to re-validate the data for
    the plot rendering, in addition to their effect on the analysis.
    """
    replicate_policy = str(kwargs.pop("replicate_policy", "individual"))
    bql_policy = str(kwargs.pop("bql_policy", "exclude"))

    use_multi = all_attributes or (
        attributes is not None and len(attributes) > 1
    )
    if use_multi:
        result = analyze_multi(
            path, condition, attributes, all_attributes,
            metadata_path, data_sheet, metadata_sheet, **kwargs,
        )
        plot_paths = _render_multi_plots(
            result, path, condition, out_dir,
            data_sheet=data_sheet,
            replicate_policy=replicate_policy,
            bql_policy=bql_policy,
        )
    else:
        attr = attribute if attributes is None else attributes[0]
        result = analyze_path(path, condition, attr, data_sheet, **kwargs)
        # ``analyze_path`` may have routed through a temp CSV; we
        # always re-render from the original path so the plot is
        # written to the canonical location.
        plot_path = _render_single_plot(
            result, path, condition, attr, out_dir,
            data_sheet=data_sheet,
            replicate_policy=replicate_policy,
            bql_policy=bql_policy,
        )
        plot_paths = [plot_path]
    artifact = make_artifact(
        result, out_dir,
        plot_paths=plot_paths,
        inline_plot=inline_plot,
        generate_pdf=generate_pdf,
    )
    return result, artifact


# ---------------------------------------------------------------------------
# Public API: v0.7.0 sensitivity wrapper
# ---------------------------------------------------------------------------


def compute_sensitivity_for(
    result: StabilityResult,
    data: ValidatedData,
    *,
    horizon: float = 60.0,
    mode: str = "row",
) -> SensitivityReport:
    """Thin wrapper around :func:`openpharmastability.stats.sensitivity.compute_sensitivity`.

    Convenience helper that re-exports the v0.7.0 leave-one-out
    sensitivity analysis (and its v0.8.0 leave-one-batch-out
    variant) at the top-level API. The trigger set depends on
    ``mode``:

    * ``mode="row"`` (v0.7.0 default) — leave-one-out over
      ``result.diagnostics.influential_points`` (a list of row
      indices in the data used for the fit, populated by the
      diagnostics layer).
    * ``mode="batch"`` (v0.8.0) — leave-one-batch-out over the
      distinct batches in the data used for the fit.

    See the sensitivity module for the full contract.
    """
    return compute_sensitivity(result, data, horizon=horizon, mode=mode)


# ---------------------------------------------------------------------------
# Public API: v0.8.0 Arrhenius-shelf-life wrapper
# ---------------------------------------------------------------------------


def predict_arrhenius_shelf_life_for(
    data: ValidatedData,
    storage_temp_C: float = 25.0,
    horizon: float = 60.0,
) -> ArrheniusShelfLife:
    """Thin wrapper around
    :func:`openpharmastability.stats.arrhenius_shelf_life.predict_arrhenius_shelf_life`.

    Returns an :class:`ArrheniusShelfLife` carrying the model-based
    predicted rate at the storage temperature, the predicted
    statistical crossing time, and the rounded-DOWN supported
    shelf life. When the underlying Arrhenius fit is skipped
    (e.g. < 2 distinct temperatures or BIDIRECTIONAL/UNKNOWN
    direction), the predictive fields are ``None`` and the
    ``notes`` describe the skip. Exploratory only; the official
    Q1E shelf-life decision on :class:`StabilityResult` is
    unchanged.
    """
    from openpharmastability.stats.arrhenius_shelf_life import (
        predict_arrhenius_shelf_life as _impl,
    )
    return _impl(data, storage_temp_C=storage_temp_C, horizon=horizon)


__all__ = [
    "analyze_csv",
    "analyze_xlsx",
    "analyze_path",
    "analyze_multi",
    "make_artifact",
    "analyze_and_artifact",
    "compute_sensitivity_for",
    "predict_arrhenius_shelf_life_for",
]
