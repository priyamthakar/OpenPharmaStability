"""Command-line interface for OpenPharmaStability v0.6.0.

Usage:
    # v0.1 single-attribute (backwards compatible)
    openpharmastability analyze <csv> --condition "25C/60RH" --attribute assay --output report.html

    # v0.2 multi-attribute
    openpharmastability analyze <csv> --condition "25C/60RH" --all-attributes --output report.html
    openpharmastability analyze <csv> --condition "25C/60RH" --attributes assay,impurity_a --output report.html
    openpharmastability analyze <xlsx> --condition "25C/60RH" --all-attributes \\
        --metadata-sheet attributes --output report.html

    # v0.6.0 export knobs
    openpharmastability analyze <csv> --condition "25C/60RH" --attribute assay \\
        --output report.html --pdf report.pdf
    openpharmastability analyze <csv> --condition "25C/60RH" --attribute assay \\
        --output report.html --artifact-dir build/bundle
    openpharmastability analyze <csv> --condition "25C/60RH" --attribute assay \\
        --output report.json --no-html
    openpharmastability analyze <csv> --condition "25C/60RH" --attribute assay \\
        --output report.json --json-only
    openpharmastability analyze <csv> --condition "25C/60RH" --attribute assay \\
        --output report.html --quiet
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

import pandas as pd

from openpharmastability.contracts import (
    DISCLAIMER,
    REQUIRED_COLUMNS,
    TOOL_VERSION,
)
from openpharmastability.plots.confidence_plot import make_confidence_plot
from openpharmastability.reports.html import render_html
from openpharmastability.reports.multi_html import render_multi_html
from openpharmastability.reports.multi_record import to_multi_decision_record
from openpharmastability.reports.record import to_decision_record
from openpharmastability.shelf_life.engine import analyze as _analyze_single_engine
from openpharmastability.shelf_life.multi_engine import analyze_many


# ---------------------------------------------------------------------------
# Module-level helpers (also used by the tests)
# ---------------------------------------------------------------------------


def _eprint(msg: str) -> None:
    """Print ``msg`` to stderr."""
    print(msg, file=sys.stderr)


def _exit_error(msg: str, code: int = 1) -> None:
    """Print an error message to stderr and raise SystemExit."""
    _eprint(msg)
    raise SystemExit(code)


def _is_xlsx_path(path: str) -> bool:
    return str(path).lower().endswith((".xlsx", ".xlsm", ".xls"))


def _load_input_frame(path: str, data_sheet: Optional[str]) -> pd.DataFrame:
    """Load ``path`` (CSV or XLSX) into a raw ``DataFrame`` with friendly errors.

    Wraps the existing ``load_csv`` / ``load_xlsx`` so the CLI can surface
    a one-line ``ERROR:`` message and exit 1 on common failure modes
    (missing file, missing XLSX sheet) instead of letting a raw
    ``FileNotFoundError`` / ``ValueError`` reach the user.
    """
    if not os.path.exists(path):
        _exit_error(f"ERROR: input file not found: {path}")
    if os.path.isdir(path):
        _exit_error(f"ERROR: input path is a directory, not a file: {path}")
    if _is_xlsx_path(path):
        from openpharmastability.data.xlsx import load_xlsx
        try:
            return load_xlsx(path, sheet_name=data_sheet)
        except ValueError as exc:
            msg = str(exc)
            # The XLSX loader's "sheet 'X' not found; available: [...]"
            # message is already informative; surface it under our
            # one-line ERROR: prefix so the CLI's error style is
            # uniform.
            if "not found" in msg:
                # Try to recover available sheet names for the message.
                available: list[str] = []
                try:
                    with pd.ExcelFile(path) as xls:
                        available = list(xls.sheet_names)
                except Exception:  # pragma: no cover -- best-effort only
                    pass
                avail_repr = repr(available) if available else "[]"
                # Extract the requested sheet name from the loader
                # message: it is the first quoted token in the form
                # "sheet 'NAME' not found; available: [...]".
                requested = "?"
                if "sheet " in msg:
                    tail = msg.split("sheet ", 1)[1]
                    requested = tail.split("'", 1)[1].split("'", 1)[0] if "'" in tail else "?"
                _exit_error(
                    f"ERROR: XLSX sheet '{requested}' not found in workbook "
                    f"{path}; available sheets: {avail_repr}"
                )
            raise
    else:
        from openpharmastability.data.io import load_csv
        try:
            return load_csv(path)
        except FileNotFoundError:
            _exit_error(f"ERROR: input file not found: {path}")
    # Unreachable; the branches above always raise or return.
    raise AssertionError("unreachable")


def _check_required_columns(df: pd.DataFrame) -> None:
    """Verify every column in :data:`contracts.REQUIRED_COLUMNS` is present
    and at least one of ``lower_spec`` / ``upper_spec`` exists. Exits 1
    with a one-line ``ERROR:`` message on failure.
    """
    cols = set(df.columns)
    missing = [c for c in REQUIRED_COLUMNS if c not in cols]
    if missing:
        # Re-quote the canonical list (the engine's error already does
        # this, but a flat string is easier to grep in CI logs).
        spec_extra = "lower_spec, upper_spec"
        _exit_error(
            f"ERROR: missing required column(s): {missing!r}; "
            f"required columns are {REQUIRED_COLUMNS!r}, plus at least one of "
            f"{spec_extra}"
        )
    if "lower_spec" not in cols and "upper_spec" not in cols:
        _exit_error(
            "ERROR: input must include at least one of lower_spec, upper_spec"
        )


def _available_conditions(df: pd.DataFrame) -> list[str]:
    """Return the sorted unique condition values in ``df``, after
    stripping whitespace. Empty / non-string values are dropped.
    """
    if "condition" not in df.columns:
        return []
    vals = df["condition"].dropna().astype(str).str.strip()
    return sorted(v for v in vals.unique() if v)


def _available_attributes(df: pd.DataFrame) -> list[str]:
    """Return the sorted unique attribute values in ``df``."""
    if "attribute" not in df.columns:
        return []
    vals = df["attribute"].dropna().astype(str).str.strip()
    return sorted(v for v in vals.unique() if v)


def _validate_args_and_inputs(args: argparse.Namespace) -> pd.DataFrame:
    """Validate ``args`` and the raw input frame.

    - Mutual-exclusion: ``--no-html`` + ``--json-only`` is rejected
      with exit code 2 (the contract for usage errors).
    - Loads the CSV/XLSX once; surfaces a friendly ``ERROR:`` line
      for missing files, missing required columns, unknown
      conditions, and unknown attributes.

    Returns the raw input frame so callers do not have to reload it.
    """
    if bool(args.no_html) and bool(args.json_only):
        _exit_error(
            "ERROR: --no-html and --json-only are mutually exclusive.",
            code=2,
        )

    df = _load_input_frame(args.path, args.data_sheet)
    _check_required_columns(df)

    # --condition: normalize the user's input via parse_condition and
    # confirm a matching row exists. parse_condition raises ValueError
    # for garbage; we rewrite that into the canonical "not found"
    # message with the available conditions appended.
    from openpharmastability.data.conditions import parse_condition
    try:
        canonical_condition = parse_condition(args.condition)
    except (ValueError, TypeError):
        avail = _available_conditions(df)
        _exit_error(
            f"ERROR: condition '{args.condition}' not found in the input; "
            f"available conditions: {avail!r}"
        )

    if "condition" in df.columns:
        # The conditions in the input may be in any of the supported
        # spellings; normalize each value and compare.
        normalized = (
            df["condition"].astype(str).map(
                lambda s: parse_condition(s) if isinstance(s, str) and s.strip() else s
            )
        )
        if canonical_condition not in set(normalized):
            avail = _available_conditions(df)
            _exit_error(
                f"ERROR: condition '{args.condition}' not found in the input; "
                f"available conditions: {avail!r}"
            )

    # --attribute (single mode only — multi mode resolves attributes
    # per-entry; see _run_multi for the multi-path validation).
    if bool(args.attribute):
        avail_attrs = _available_attributes(df)
        if args.attribute not in avail_attrs:
            _exit_error(
                f"ERROR: attribute '{args.attribute}' not found in the input; "
                f"available attributes: {avail_attrs!r}"
            )

    return df


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="openpharmastability",
        description=(
            "ICH Q1E-inspired stability analysis and shelf-life "
            "reporting toolkit (decision-support / educational; not "
            "a validated GxP system)."
        ),
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {TOOL_VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="Run stability analysis on a CSV/XLSX.")
    a.add_argument("path", help="Path to the input CSV or XLSX file.")
    a.add_argument(
        "--condition", required=True,
        help="Long-term storage condition (e.g. '25C/60RH').",
    )
    # ---- v0.1 single-attribute (default, backwards compatible) ----
    a.add_argument(
        "--attribute", default=None,
        help="Single attribute to analyze (default: 'assay'). "
             "Mutually exclusive with --attributes / --all-attributes.",
    )
    # ---- v0.2 multi-attribute ----
    a.add_argument(
        "--attributes", default=None,
        help="Comma-separated list of attributes to analyze "
             "(v0.2 multi-attribute mode). Mutually exclusive with "
             "--attribute / --all-attributes.",
    )
    a.add_argument(
        "--all-attributes", action="store_true", default=False,
        help="Analyze every attribute present in the data "
             "(v0.2 multi-attribute mode).",
    )
    a.add_argument(
        "--metadata-csv", default=None,
        help="Optional path to a per-attribute metadata CSV "
             "(columns: attribute, unit, direction, lower_spec, "
             "upper_spec, spec_type, transform, attribute_role, "
             "report_order).",
    )
    a.add_argument(
        "--metadata-sheet", default=None,
        help="Sheet name for metadata in an XLSX workbook. "
             "Defaults: 'attributes', 'metadata', 'attribute_metadata'.",
    )
    a.add_argument(
        "--data-sheet", default=None,
        help="Sheet name for the data in an XLSX workbook. "
             "Defaults: 'results', 'data', 'stability'.",
    )
    a.add_argument(
        "--plots-dir", default=None,
        help="Directory for per-attribute plot PNGs (v0.2 multi-attr). "
             "Defaults to a sibling 'plots' directory next to --output.",
    )
    # ---- common ----
    a.add_argument(
        "--product-type", default="product", choices=["product", "substance"],
        help="Deliverable term: 'product' -> 'shelf life' (default); "
             "'substance' -> 'retest period'.",
    )
    a.add_argument(
        "--horizon", type=float, default=60.0,
        help="Maximum crossing-search time in months (default: 60).",
    )
    a.add_argument(
        "--replicate-policy", default="individual",
        choices=["individual", "mean_by_batch_time", "technical_replicates_average"],
        help="Replicate handling policy (default: individual).",
    )
    a.add_argument(
        "--bql-policy", default="exclude",
        choices=["exclude", "flag", "substitute_loq", "substitute_loq_half", "manual_review"],
        help="Below-quantitation-limit policy (default: exclude). "
             "Choices: exclude / flag / substitute_loq / substitute_loq_half / manual_review. "
             "substitute_loq and substitute_loq_half require a finite loq column; "
             "manual_review keeps rows but flags the attribute for human review.",
    )
    a.add_argument(
        "--seed", type=int, default=None,
        help="Random seed to record in the reproducibility metadata.",
    )
    a.add_argument(
        "--assess-transforms", action="store_true", default=False,
        help="Compute exploratory transform-candidate evidence "
             "(none/log/sqrt) for each attribute. The v0.3.0 official "
             "shelf-life decision is unchanged; this only adds evidence "
             "to the report.",
    )
    a.add_argument(
        "--source-epoch", type=int, default=None,
        help="Override the analysis timestamp (Unix seconds). "
             "Defaults to $SOURCE_DATE_EPOCH if set, else wall clock.",
    )
    # ---- v0.4.0 ICH Q1A significant-change gate ----
    a.add_argument(
        "--accelerated-condition", default="40C/75RH",
        help="Accelerated condition (default: '40C/75RH'). "
             "Pass the empty string to skip the gate for this run.",
    )
    a.add_argument(
        "--intermediate-condition", default="30C/65RH",
        help="Intermediate condition (default: '30C/65RH'). "
             "Pass the empty string to skip the gate for this run.",
    )
    a.add_argument(
        "--assay-change-threshold", type=float, default=5.0,
        help="Percent change in assay that counts as significant "
             "(default: 5.0).",
    )
    a.add_argument(
        "--no-significant-change-gate", action="store_true", default=False,
        help="Disable the ICH Q1A significant-change gate. "
             "v0.3.1 cap-only behavior is restored.",
    )
    # ---- v0.5.0 advanced-statistics opt-ins ----
    a.add_argument(
        "--arrhenius", action="store_true", default=False,
        help="Fit Arrhenius from multi-temperature rate data "
             "(exploratory; does not change the official model).",
    )
    a.add_argument(
        "--arrhenius-storage-temp", type=float, default=25.0,
        help="Storage temperature for Arrhenius extrapolation "
             "(default: 25.0 °C).",
    )
    a.add_argument(
        "--mkt", action="store_true", default=False,
        help="Compute MKT from input temperatures "
             "(exploratory; USP <1160> default Ea).",
    )
    a.add_argument(
        "--mkt-ea-kj-mol", type=float, default=83.144,
        help="Ea for MKT in kJ/mol (default: 83.144).",
    )
    a.add_argument(
        "--detect-reduced-design", action="store_true", default=False,
        help="Run ICH Q1D reduced-design detection "
             "(bracketing / matrixing).",
    )
    a.add_argument(
        "--random-effects", action="store_true", default=False,
        help="Use a mixed model (batch as random effect) "
             "instead of the Q1E default fixed-effect ANCOVA. "
             "Not the Q1E default. Exploration only.",
    )
    a.add_argument(
        "--output", "-o", required=True,
        help="Path to write the HTML report. A sibling .json "
             "decision record and plot PNGs are written next to it.",
    )

    # ---- v0.6.0 export knobs (additive) ----
    a.add_argument(
        "--pdf", default=None,
        help="Also write a PDF copy of the HTML report to PATH. "
             "Requires weasyprint or pdfkit + wkhtmltopdf; otherwise "
             "the CLI prints a warning and exits 0 without the PDF.",
    )
    a.add_argument(
        "--no-html", action="store_true", default=False,
        help="Skip the HTML render. The plot PNG and the JSON "
             "decision record are still written. Mutually exclusive "
             "with --json-only.",
    )
    a.add_argument(
        "--json-only", action="store_true", default=False,
        help="Skip both the HTML render and the plot PNG. Only the "
             "JSON decision record is written. Mutually exclusive "
             "with --no-html.",
    )
    a.add_argument(
        "--artifact-dir", default=None,
        help="Also write a self-contained report artifact bundle to "
             "DIR (HTML with the plot inlined, JSON, plot PNG, "
             "optionally a PDF).",
    )
    a.add_argument(
        "--quiet", "-q", action="store_true", default=False,
        help="Suppress the per-step / per-attribute summary on stdout. "
             "Exit code and the file artifacts are unchanged.",
    )

    # ---- v0.7.0 sensitivity + acceptance-criteria flags ----
    a.add_argument(
        "--sensitivity", action="store_true", default=False,
        help="Run the leave-one-out sensitivity analysis over "
             "Cook's-distance influential points and attach the "
             "report to the JSON decision record and the HTML "
             "report. Single-attribute mode only; the flag is a "
             "silent no-op in multi-attribute mode.",
    )
    a.add_argument(
        "--acceptance-csv", default=None, dest="acceptance_csv",
        help="Write a flat acceptance-criteria CSV to PATH. One "
             "row per analyzed attribute (single-attribute mode: "
             "1 row; multi-attribute mode: 1 row per attribute "
             "with the per-attribute metadata spec).",
    )

    return p


def _optstr_to_none(value: str | None) -> str | None:
    """Convert the empty string to ``None`` so the engine can
    distinguish "user did not pass a condition" from "user passed
    the empty string to skip this arm"."""
    if value is None:
        return None
    if not str(value).strip():
        return None
    return str(value)


def _is_multi_mode(args: argparse.Namespace) -> bool:
    return bool(args.attributes) or bool(args.all_attributes)


def _parse_attributes(raw: str | None) -> list[str]:
    if raw is None:
        return []
    return [a.strip() for a in raw.split(",") if a.strip()]


# ---------------------------------------------------------------------------
# Engine kwargs
# ---------------------------------------------------------------------------


def _engine_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    """The kwargs common to both the single and multi analyze calls."""
    return dict(
        product_type=args.product_type,
        horizon=args.horizon,
        replicate_policy=args.replicate_policy,
        bql_policy=args.bql_policy,
        assess_transforms=bool(args.assess_transforms),
        seed=args.seed,
        source_epoch=args.source_epoch,
        accelerated_condition=_optstr_to_none(args.accelerated_condition),
        intermediate_condition=_optstr_to_none(args.intermediate_condition),
        assay_change_threshold=float(args.assay_change_threshold),
        no_significant_change_gate=bool(args.no_significant_change_gate),
        run_arrhenius=bool(args.arrhenius),
        arrhenius_storage_temp_C=float(args.arrhenius_storage_temp),
        run_mkt=bool(args.mkt),
        mkt_ea_kJ_per_mol=float(args.mkt_ea_kj_mol),
        detect_reduced_design=bool(args.detect_reduced_design),
        random_effects=bool(args.random_effects),
        # v0.7.0: leave-one-out sensitivity analysis. The single-
        # attribute ``analyze()`` path accepts this kwarg and
        # attaches the ``SensitivityReport`` to the result; the
        # multi-attribute ``analyze_many()`` does NOT (its
        # signature is owned by a parallel build stream and is
        # out of scope for v0.7.0), so the multi-mode runner
        # pops this kwarg out before forwarding. The flag is a
        # silent no-op in multi-attribute mode.
        run_sensitivity=bool(args.sensitivity),
    )


# ---------------------------------------------------------------------------
# PDF + artifact helpers (v0.6.0)
# ---------------------------------------------------------------------------


def _try_render_pdf(html_path: str, pdf_path: str) -> Optional[str]:
    """Try to render ``html_path`` to ``pdf_path``. Return the absolute
    PDF path on success, ``None`` if no backend is available.

    All other failures (the PDF backend raised, the produced file is
    missing / not a real PDF) propagate as ``RuntimeError`` so the
    caller can decide whether to surface them. The CLI's behaviour is
    "warn but do not crash" — see ``_maybe_render_pdf`` below.
    """
    from openpharmastability.reports.pdf import has_pdf_backend, render_pdf
    if has_pdf_backend() is None:
        return None
    return render_pdf(html_path, pdf_path)


def _maybe_render_pdf(
    html_path: str,
    pdf_path: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Render ``html_path`` -> ``pdf_path`` if both are set and a backend
    is available. Return ``(pdf_path_returned, warning_message)``.

    The CLI's contract is "warn but do not crash" when no PDF backend
    is available, so the warning is returned for the caller to print
    and execution continues. Other ``RuntimeError``s from the PDF
    backend are also caught and surfaced as warnings.
    """
    if not pdf_path:
        return None, None
    try:
        written = _try_render_pdf(html_path, pdf_path)
    except RuntimeError as exc:
        return None, f"WARNING: could not render PDF {pdf_path}: {exc}"
    if written is None:
        return None, (
            f"WARNING: --pdf {pdf_path} requested but no PDF backend "
            "(weasyprint or pdfkit) is available; skipped."
        )
    return written, None


def _write_artifact(
    result: Any,
    out_dir: str,
    plot_paths: list[str],
    generate_pdf: bool,
) -> Optional[dict[str, Any]]:
    """Build a self-contained artifact bundle. Return a dict of paths
    on success, ``None`` on a hard failure (the warning is already
    printed).

    The ``make_report_artifact`` helper lives in
    ``openpharmastability.reports.artifacts`` (Agent C) and the
    ``make_artifact`` / ``analyze_and_artifact`` thin API lives in
    ``openpharmastability.api`` (Agent B). The CLI delegates to the
    artifact helper directly so it can stay aligned with the engine
    kwargs used by ``_run_single`` / ``_run_multi``.
    """
    try:
        from openpharmastability.reports.artifacts import make_report_artifact
    except Exception as exc:  # noqa: BLE001
        _eprint(
            f"WARNING: --artifact-dir {out_dir} requested but "
            f"openpharmastability.reports.artifacts is not importable: {exc!r}"
        )
        return None
    try:
        artifact = make_report_artifact(
            result, out_dir,
            plot_paths=plot_paths or None,
            inline_plot=True,
            generate_pdf=generate_pdf,
        )
    except Exception as exc:  # noqa: BLE001
        _eprint(
            f"WARNING: failed to build artifact bundle in {out_dir}: {exc!r}"
        )
        return None
    return {
        "out_dir": artifact.out_dir,
        "html_path": artifact.html_path,
        "json_path": artifact.json_path,
        "plot_paths": list(artifact.plot_paths),
        "pdf_path": artifact.pdf_path,
    }


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


def _write_acceptance_csv(
    result: Any,
    path: str,
) -> tuple[int, Optional[str]]:
    """Write the v0.7.0 acceptance-criteria CSV to ``path``.

    Single ``StabilityResult`` -> 1 row. ``MultiAttributeResult`` ->
    1 row per analyzed attribute. Returns ``(n_rows, warning)``;
    the warning is non-None on hard failure and is printed by the
    caller. On success the warning is None and the caller prints a
    one-line summary.

    The function never raises; any exception is caught and
    surfaced as a warning so the rest of the CLI flow continues
    normally. The CSV is ``newline=""`` (Python's csv module
    contract) and uses ``utf-8`` (the rest of the CLI uses utf-8
    too).
    """
    try:
        import csv as _csv
        import dataclasses as _dc
        from openpharmastability.contracts import AcceptanceCriteriaRow
        from openpharmastability.reports.record import to_acceptance_criteria
        rows = to_acceptance_criteria(result)
        fieldnames = [f.name for f in _dc.fields(AcceptanceCriteriaRow)]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = _csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for row in rows:
                w.writerow(_dc.asdict(row))
    except Exception as exc:  # noqa: BLE001
        return 0, (
            f"WARNING: --acceptance-csv {path} requested but writing "
            f"the CSV failed: {exc!r}"
        )
    return len(rows), None


def _run_single(args: argparse.Namespace, raw_df: pd.DataFrame) -> int:
    """v0.1 single-attribute path."""
    out_path = os.path.abspath(args.output)
    out_dir = os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)

    attribute = args.attribute or "assay"
    result = _analyze_single_engine(
        path=args.path,
        condition=args.condition,
        attribute=attribute,
        **_engine_kwargs(args),
    )

    # Plot needs the validated data; refit through the schema layer
    # on the already-loaded raw frame. We reuse ``raw_df`` so the CLI
    # does not pay for a second CSV read in the common case.
    from openpharmastability.data.schema import validate_and_select
    data = validate_and_select(
        raw_df, attribute=attribute, condition=args.condition,
        replicate_policy=args.replicate_policy,
        bql_policy=args.bql_policy,
    )

    # Plot
    plot_path = os.path.join(out_dir, "confidence_plot.png")
    if not bool(args.json_only):
        make_confidence_plot(result, data, plot_path)
    else:
        # --json-only: do NOT write the plot.
        plot_path = None

    # HTML
    if bool(args.json_only):
        # --json-only: --output is the JSON path; no HTML is written.
        html_path = None
        json_path = out_path
    else:
        html_path = out_path
        if not bool(args.no_html):
            render_html(
                result,
                plot_png_path=os.path.basename(plot_path) if plot_path else None,
                out_path=html_path,
            )
        json_path = os.path.splitext(out_path)[0] + ".json"

    # JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(to_decision_record(result), f, indent=2)

    # v0.7.0: acceptance-criteria CSV. Best-effort; never crashes
    # the CLI. The helper ``to_acceptance_criteria`` lives in
    # ``openpharmastability.reports.record`` and is shared with
    # the single-attribute JSON record (which embeds the same
    # list under the ``acceptance_criteria`` key).
    if args.acceptance_csv:
        n_rows, accept_warn = _write_acceptance_csv(
            result, args.acceptance_csv,
        )
        if accept_warn:
            _eprint(accept_warn)
        elif not bool(args.quiet):
            print(
                f"acceptance criteria: wrote {n_rows} row(s) to {args.acceptance_csv}"
            )

    # PDF (best-effort, never crashes)
    pdf_written, pdf_warn = _maybe_render_pdf(
        html_path if html_path else "",
        args.pdf,
    )
    if pdf_warn:
        _eprint(pdf_warn)

    # Artifact bundle (best-effort, never crashes)
    artifact_info = None
    if args.artifact_dir and html_path:
        artifact_info = _write_artifact(
            result, args.artifact_dir,
            plot_paths=[plot_path] if plot_path else [],
            generate_pdf=bool(args.pdf),
        )

    # Summary
    if not bool(args.quiet):
        # When --json-only is set the user's --output IS the JSON
        # path; there is no HTML to point at. Pass None so the
        # printer renders "(skipped)" instead of echoing the JSON
        # path as the HTML location (which was the old behavior).
        _print_single_summary(
            result,
            out_path=html_path,
            json_path=json_path,
            plot_path=plot_path,
            pdf_path=pdf_written, artifact=artifact_info,
        )
    return 0


def _print_single_summary(
    result,
    out_path: Optional[str],
    json_path: Optional[str],
    plot_path: Optional[str],
    *,
    pdf_path: Optional[str] = None,
    artifact: Optional[dict[str, Any]] = None,
) -> None:
    print(f"OpenPharmaStability {TOOL_VERSION}")
    print(f"  attribute:            {result.attribute}")
    print(f"  condition:            {result.condition}")
    print(f"  direction:            {result.direction.value}")
    print(f"  model:                {result.model.value}")
    print(f"  poolability:          {result.poolability.decision.value} "
          f"(p_slopes={result.poolability.p_slopes:.3g})")
    print(f"  crossing:             {result.crossing.status.value}")
    if result.statistical_crossing_months is not None:
        print(f"  statistical crossing: {result.statistical_crossing_months:.2f} months")
    if result.supported_shelf_life_months is not None:
        print(f"  supported {result.deliverable_term}: "
              f"{result.supported_shelf_life_months} months")
    else:
        print(f"  supported {result.deliverable_term}: not limiting within horizon")
    print(f"  observed data:        {result.observed_data_months:g} months")
    print(f"  extrapolation:        {'flagged' if result.extrapolation_flag else 'none'}")
    if out_path:
        print(f"  HTML report:          {out_path}")
    else:
        print(f"  HTML report:          (skipped)")
    print(f"  JSON decision record: {json_path}")
    if plot_path:
        print(f"  confidence plot PNG:  {plot_path}")
    else:
        print(f"  confidence plot PNG:  (skipped)")
    if pdf_path:
        print(f"  PDF report:           {pdf_path}")
    if artifact:
        print(f"  artifact bundle:      {artifact['out_dir']}")
        if artifact.get("pdf_path"):
            print(f"  artifact PDF:         {artifact['pdf_path']}")
    if result.warnings:
        print(f"  warnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"    - {w}")


def _run_multi(args: argparse.Namespace, raw_df: pd.DataFrame) -> int:
    """v0.2 multi-attribute path."""
    out_path = os.path.abspath(args.output)
    out_dir = os.path.dirname(out_path) or "."
    plots_dir = args.plots_dir or os.path.join(out_dir, "plots")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(plots_dir, exist_ok=True)

    attrs = _parse_attributes(args.attributes) if args.attributes else None
    # v0.7.0: ``analyze_many`` does not accept ``run_sensitivity``
    # (its signature is owned by a parallel build stream and is
    # out of scope for v0.7.0). Pop the kwarg out of the forwarded
    # dict so the call does not raise a TypeError on the unknown
    # keyword. The flag is a silent no-op in multi-attribute mode.
    multi_kwargs = _engine_kwargs(args)
    multi_kwargs.pop("run_sensitivity", None)
    result = analyze_many(
        path=args.path,
        condition=args.condition,
        attributes=attrs,
        all_attributes=bool(args.all_attributes),
        metadata_path=args.metadata_csv,
        data_sheet=args.data_sheet,
        metadata_sheet=args.metadata_sheet,
        **multi_kwargs,
    )

    # Per-attribute plots (skipped in --json-only).
    from openpharmastability.data.schema import validate_and_select
    written_plots: list[str] = []
    if not bool(args.json_only):
        for ar in result.attributes:
            try:
                data = validate_and_select(
                    raw_df, attribute=ar.metadata.attribute,
                    condition=args.condition,
                    replicate_policy=args.replicate_policy,
                    bql_policy=args.bql_policy,
                )
            except Exception:
                continue
            plot_path = os.path.join(
                plots_dir, f"{ar.metadata.attribute}_confidence_plot.png",
            )
            make_confidence_plot(ar.result, data, plot_path)
            written_plots.append(plot_path)
    else:
        plots_dir = None

    # HTML
    if bool(args.json_only):
        # --json-only: --output is the JSON path; no HTML is written.
        html_path = None
        json_path = out_path
    else:
        html_path = out_path
        if not bool(args.no_html):
            render_multi_html(
                result,
                plot_dir=plots_dir or out_dir,
                out_path=html_path,
            )
        json_path = os.path.splitext(out_path)[0] + ".json"

    # JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(to_multi_decision_record(result), f, indent=2)

    # v0.7.0: acceptance-criteria CSV. One row per analyzed
    # attribute (excluded attributes appear with
    # ``included_in_limiting_decision=False`` and a non-null
    # ``exclusion_reason``). Best-effort; never crashes the CLI.
    if args.acceptance_csv:
        n_rows, accept_warn = _write_acceptance_csv(
            result, args.acceptance_csv,
        )
        if accept_warn:
            _eprint(accept_warn)
        elif not bool(args.quiet):
            print(
                f"acceptance criteria: wrote {n_rows} row(s) to {args.acceptance_csv}"
            )

    # PDF (best-effort, never crashes)
    pdf_written, pdf_warn = _maybe_render_pdf(
        html_path if html_path else "",
        args.pdf,
    )
    if pdf_warn:
        _eprint(pdf_warn)

    # Artifact bundle (best-effort, never crashes). The multi-attribute
    # bundle uses the per-attribute plots we just wrote.
    artifact_info = None
    if args.artifact_dir and html_path:
        artifact_info = _write_artifact(
            result, args.artifact_dir,
            plot_paths=written_plots,
            generate_pdf=bool(args.pdf),
        )

    if not bool(args.quiet):
        _print_multi_summary(
            result, html_path, json_path, plots_dir,
            pdf_path=pdf_written, artifact=artifact_info,
        )
    return 0


def _print_multi_summary(
    result,
    out_path: Optional[str],
    json_path: Optional[str],
    plots_dir: Optional[str],
    *,
    pdf_path: Optional[str] = None,
    artifact: Optional[dict[str, Any]] = None,
) -> None:
    print(f"OpenPharmaStability {TOOL_VERSION} (multi-attribute)")
    print(f"  condition:            {result.condition}")
    print(f"  product type:         {result.product_type}")
    print(f"  attributes analyzed:  {len(result.attributes)}")
    for ar in result.attributes:
        line = f"    - {ar.metadata.attribute}"
        if ar.result.statistical_crossing_months is not None:
            line += f"  statistical={ar.result.statistical_crossing_months:.2f} mo"
        if ar.result.supported_shelf_life_months is not None:
            line += f"  supported={ar.result.supported_shelf_life_months} mo"
        line += f"  [{ar.result.crossing.status.value}]"
        if not ar.included_in_limiting_decision:
            line += f"  (excluded: {ar.exclusion_reason})"
        print(line)
    print(f"  limiting attribute:   {result.limiting_attribute}")
    if result.supported_shelf_life_months is not None:
        print(f"  overall supported {result.deliverable_term}: "
              f"{result.supported_shelf_life_months} months")
    else:
        print(f"  overall supported {result.deliverable_term}: "
              f"not limiting within horizon")
    if out_path:
        print(f"  HTML report:          {out_path}")
    else:
        print(f"  HTML report:          (skipped)")
    print(f"  JSON decision record: {json_path}")
    if plots_dir:
        print(f"  plots directory:      {plots_dir}")
    else:
        print(f"  plots directory:      (skipped)")
    if pdf_path:
        print(f"  PDF report:           {pdf_path}")
    if artifact:
        print(f"  artifact bundle:      {artifact['out_dir']}")
        if artifact.get("pdf_path"):
            print(f"  artifact PDF:         {artifact['pdf_path']}")
    if result.warnings:
        print(f"  warnings ({len(result.warnings)}):")
        for w in result.warnings[:10]:
            print(f"    - {w}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command != "analyze":
        _eprint(DISCLAIMER)
        return 2

    # Validate mutually exclusive attribute selectors.
    flags = sum([
        bool(args.attribute), bool(args.attributes), bool(args.all_attributes),
    ])
    if flags > 1:
        _eprint(
            "ERROR: --attribute, --attributes, and --all-attributes "
            "are mutually exclusive."
        )
        return 2

    # Validate CLI inputs (file, columns, condition, attribute). On
    # failure this raises SystemExit with a one-line ``ERROR:`` message
    # and exit code 1 (or 2 for mutual-exclusion of the export flags).
    raw_df = _validate_args_and_inputs(args)

    if _is_multi_mode(args):
        return _run_multi(args, raw_df)
    return _run_single(args, raw_df)


if __name__ == "__main__":
    raise SystemExit(main())
