"""Command-line interface for OpenPharmaStability v0.2.0.

Usage:
    # v0.1 single-attribute (backwards compatible)
    openpharmastability analyze <csv> --condition "25C/60RH" --attribute assay --output report.html

    # v0.2 multi-attribute
    openpharmastability analyze <csv> --condition "25C/60RH" --all-attributes --output report.html
    openpharmastability analyze <csv> --condition "25C/60RH" --attributes assay,impurity_a --output report.html
    openpharmastability analyze <xlsx> --condition "25C/60RH" --all-attributes \\
        --metadata-sheet attributes --output report.html
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from openpharmastability.contracts import DISCLAIMER, TOOL_VERSION
from openpharmastability.plots.confidence_plot import make_confidence_plot
from openpharmastability.reports.html import render_html
from openpharmastability.reports.multi_html import render_multi_html
from openpharmastability.reports.multi_record import to_multi_decision_record
from openpharmastability.reports.record import to_decision_record
from openpharmastability.shelf_life.engine import analyze
from openpharmastability.shelf_life.multi_engine import analyze_many


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


def _run_single(args: argparse.Namespace) -> int:
    """v0.1 single-attribute path."""
    out_path = os.path.abspath(args.output)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    attribute = args.attribute or "assay"
    result = analyze(
        path=args.path,
        condition=args.condition,
        attribute=attribute,
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
        # v0.5.0 advanced-statistics opt-ins.
        run_arrhenius=bool(args.arrhenius),
        arrhenius_storage_temp_C=float(args.arrhenius_storage_temp),
        run_mkt=bool(args.mkt),
        mkt_ea_kJ_per_mol=float(args.mkt_ea_kj_mol),
        detect_reduced_design=bool(args.detect_reduced_design),
        random_effects=bool(args.random_effects),
    )

    # Plot needs the validated data; refit through engine.
    from openpharmastability.data.io import load_csv
    from openpharmastability.data.schema import validate_and_select
    if args.path.lower().endswith((".xlsx", ".xlsm")):
        from openpharmastability.data.xlsx import load_xlsx
        raw_df = load_xlsx(args.path, sheet_name=args.data_sheet)
    else:
        raw_df = load_csv(args.path)
    data = validate_and_select(
        raw_df, attribute=attribute, condition=args.condition,
        replicate_policy=args.replicate_policy,
        bql_policy=args.bql_policy,
    )

    plot_path = os.path.join(out_dir or ".", "confidence_plot.png")
    make_confidence_plot(result, data, plot_path)

    render_html(result, plot_png_path=os.path.basename(plot_path), out_path=out_path)

    json_path = os.path.splitext(out_path)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(to_decision_record(result), f, indent=2)

    _print_single_summary(result, out_path, json_path, plot_path)
    return 0


def _print_single_summary(result, out_path, json_path, plot_path) -> None:
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
    print(f"  HTML report:          {out_path}")
    print(f"  JSON decision record: {json_path}")
    print(f"  confidence plot PNG:  {plot_path}")
    if result.warnings:
        print(f"  warnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"    - {w}")


def _run_multi(args: argparse.Namespace) -> int:
    """v0.2 multi-attribute path."""
    out_path = os.path.abspath(args.output)
    out_dir = os.path.dirname(out_path) or "."
    plots_dir = args.plots_dir or os.path.join(out_dir, "plots")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(plots_dir, exist_ok=True)

    attrs = _parse_attributes(args.attributes) if args.attributes else None
    result = analyze_many(
        path=args.path,
        condition=args.condition,
        attributes=attrs,
        all_attributes=bool(args.all_attributes),
        metadata_path=args.metadata_csv,
        data_sheet=args.data_sheet,
        metadata_sheet=args.metadata_sheet,
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
        # v0.5.0 advanced-statistics opt-ins.
        run_arrhenius=bool(args.arrhenius),
        arrhenius_storage_temp_C=float(args.arrhenius_storage_temp),
        run_mkt=bool(args.mkt),
        mkt_ea_kJ_per_mol=float(args.mkt_ea_kj_mol),
        detect_reduced_design=bool(args.detect_reduced_design),
        random_effects=bool(args.random_effects),
    )

    # Per-attribute plots
    from openpharmastability.data.io import load_csv
    from openpharmastability.data.schema import validate_and_select
    from openpharmastability.data.xlsx import load_xlsx
    if args.path.lower().endswith((".xlsx", ".xlsm")):
        raw_df = load_xlsx(args.path, sheet_name=args.data_sheet)
    else:
        raw_df = load_csv(args.path)
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
        plot_path = os.path.join(plots_dir, f"{ar.metadata.attribute}_confidence_plot.png")
        make_confidence_plot(ar.result, data, plot_path)

    # Reports
    render_multi_html(result, plot_dir=plots_dir, out_path=out_path)
    json_path = os.path.splitext(out_path)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(to_multi_decision_record(result), f, indent=2)

    _print_multi_summary(result, out_path, json_path, plots_dir)
    return 0


def _print_multi_summary(result, out_path, json_path, plots_dir) -> None:
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
    print(f"  HTML report:          {out_path}")
    print(f"  JSON decision record: {json_path}")
    print(f"  plots directory:      {plots_dir}")
    if result.warnings:
        print(f"  warnings ({len(result.warnings)}):")
        for w in result.warnings[:10]:
            print(f"    - {w}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "analyze":
        # Validate mutually exclusive attribute selectors.
        flags = sum([bool(args.attribute), bool(args.attributes), bool(args.all_attributes)])
        if flags > 1:
            print(
                "ERROR: --attribute, --attributes, and --all-attributes "
                "are mutually exclusive.", file=sys.stderr,
            )
            return 2
        if _is_multi_mode(args):
            return _run_multi(args)
        return _run_single(args)
    print(DISCLAIMER, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
