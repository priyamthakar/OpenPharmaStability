"""Shelf-life engine: orchestrate data → fit → pool → select → bound → crossing → extrapolation.

The :func:`analyze` function is the public entry point. It:

1. Loads the CSV at ``path`` and validates the schema.
2. Fits the three linear models (POOLED, COMMON_SLOPE, SEPARATE).
3. Runs the 3-step ANCOVA poolability test at α = 0.25.
4. Selects the right model from the poolability decision.
5. Finds the bound-vs-spec crossing time (numerical, with the
   four documented edge-case statuses).
6. Rounds the crossing time DOWN to whole months to get the
   supported shelf life (or retest period, for drug substance).
7. Runs residual diagnostics (linearity, homoscedasticity,
   normality, influence) and surfaces the results as warnings.
8. Applies the Q1E room-temperature extrapolation cap and flags
   any extension beyond the observed data.
9. Records reproducibility metadata: file SHA-256, row/column
   counts, library versions, tool version, ISO-8601 timestamp.

The function returns a :class:`StabilityResult` ready for the
HTML/JSON report.
"""
from __future__ import annotations

import dataclasses
import hashlib
import math
import os
import platform
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from openpharmastability.contracts import (
    ArrheniusResult,
    CrossingStatus,
    Direction,
    Poolability,
    StabilityResult,
    TOOL_VERSION,
    ValidatedData,
)
from openpharmastability.data.io import load_table
from openpharmastability.data.schema import validate_and_select
from openpharmastability.models.selection import select_model
from openpharmastability.regulatory.profile import GuidanceProfile, resolve_profile
from openpharmastability.shelf_life.extrapolation import apply_extrapolation_caps
from openpharmastability.stats.bounds import find_crossing
from openpharmastability.stats.diagnostics import run_diagnostics
from openpharmastability.stats.poolability import decide_poolability
from openpharmastability.stats.regression import fit_models


# Library version helper: stdlib importlib.metadata is available
# from Python 3.8+; we use it for reproducibility metadata.
def _lib_version(distribution: str) -> str:
    try:
        from importlib.metadata import version

        return version(distribution)
    except Exception:  # pragma: no cover — best-effort metadata
        return "unknown"


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _library_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "pandas": _lib_version("pandas"),
        "numpy": _lib_version("numpy"),
        "scipy": _lib_version("scipy"),
        "statsmodels": _lib_version("statsmodels"),
        "matplotlib": _lib_version("matplotlib"),
        "jinja2": _lib_version("jinja2"),
    }


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_timestamp(source_epoch: int | None) -> str:
    """Honor ``source_epoch``, then ``$SOURCE_DATE_EPOCH``, then wall clock.

    This lets callers pin the analysis timestamp for byte-stable,
    reproducible reports. The ``SOURCE_DATE_EPOCH`` env var is the
    conventional toggle (also used by ``reproducible-builds.org``,
    ``tar``, and other reproducible-build tooling).
    """
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


def _build_metadata(
    path: str,
    df: pd.DataFrame,
    seed: int | None,
    source_epoch: int | None = None,
) -> dict:
    return {
        "tool_version": TOOL_VERSION,
        "timestamp": _resolve_timestamp(source_epoch),
        "file_path": str(path),
        "file_sha256": _file_sha256(path),
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "library_versions": _library_versions(),
        "random_seed": seed,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze(
    path: str,
    condition: str,
    attribute: str = "assay",
    product_type: str = "product",
    horizon: float = 60.0,
    replicate_policy: str = "individual",
    bql_policy: str = "exclude",
    assess_transforms: bool = False,
    seed: int | None = None,
    source_epoch: int | None = None,
    # v0.4.0 ICH Q1A significant-change gate. All default-safe; the
    # default behavior of `analyze()` is byte-equivalent to v0.3.1
    # for the golden fixture ``examples/assay_3batch.csv`` (no
    # accelerated rows -> gate silently permissive).
    accelerated_condition: str | None = "40C/75RH",
    intermediate_condition: str | None = "30C/65RH",
    assay_change_threshold: float | None = None,
    no_significant_change_gate: bool = False,
    # v0.5.0 advanced statistics. All default-safe; the default
    # behavior of `analyze()` is byte-equivalent to v0.4.0 when
    # none of these flags are passed.
    run_arrhenius: bool = False,
    arrhenius_storage_temp_C: float = 25.0,
    run_mkt: bool = False,
    mkt_ea_kJ_per_mol: float = 83.144,
    detect_reduced_design: bool = False,
    random_effects: bool = False,
    # v0.7.0 — leave-one-out sensitivity analysis. When True, the
    # engine re-runs the full analysis for each Cook's-distance
    # influential point flagged by the diagnostics layer and
    # attaches a `SensitivityReport` to the result on the
    # `sensitivity_report` field. Default False; the field stays
    # at its v0.6 default (None) so v0.6.x callers and hand-built
    # fixtures keep working unchanged.
    run_sensitivity: bool = False,
    # v0.8.0 — sensitivity drop mode. ``"row"`` (the v0.7.0
    # default, byte-equivalent) does leave-one-out over Cook's-
    # distance influential points; ``"batch"`` does
    # leave-one-batch-out over the distinct batches in the data
    # used for the fit. The default ``"row"`` keeps the v0.7.0
    # output byte-for-byte for callers that do not opt in.
    sensitivity_mode: str = "row",
    # v0.8.0 — Arrhenius-driven shelf-life prediction. Opt-in;
    # when True the engine calls
    # :func:`openpharmastability.stats.arrhenius_shelf_life.predict_arrhenius_shelf_life`
    # on the validated data and attaches the resulting
    # :class:`ArrheniusShelfLife` to the result on the
    # `arrhenius_shelf_life` field. Exploratory only; the
    # official Q1E shelf-life decision is unchanged. When the
    # Arrhenius fit is skipped (e.g. < 2 distinct temperatures
    # in the data) the field is still populated — the value is
    # an `ArrheniusShelfLife` whose predictive fields are None
    # and whose `notes` describe the skip. Default False; the
    # field stays at its v0.7.0 default (None).
    run_arrhenius_shelf_life: bool = False,
    arrhenius_shelf_life_storage_temp_C: float = 25.0,
    # v0.9.0 — per-batch Arrhenius rate diagnostic. Opt-in; when
    # True the engine builds a per-batch rate dict via
    # :func:`openpharmastability.stats.arrhenius._per_batch_rates`
    # and runs the robust-z outlier detection
    # (:func:`_detect_arrhenius_outliers`). The two new fields on
    # ``ArrheniusResult`` (``per_batch_rate_by_temp`` and
    # ``outlier_batches``) are populated and the result is
    # surfaced through the JSON record and HTML report. Default
    # ``False`` — v0.8.x callers see byte-equivalent output.
    # Requires ``run_arrhenius=True`` (no per-batch diagnostic
    # without a pooled fit).
    run_arrhenius_per_batch: bool = False,
    # v0.10.0 — active guidance profile. Bundles the poolability
    # alpha, confidence level, one-/two-sided t-quantiles, and the
    # extrapolation caps the regulator defines. Defaults to ``Q1AE``
    # (ICH Q1A(R2)+Q1E), whose values are sourced from the
    # ``contracts`` primitives, so the default path is byte-equivalent
    # to v0.9.0. Pass a different ``GuidanceProfile`` (e.g. a future
    # ``Q1_CONSOLIDATED``) to re-base every regulator constant in one
    # place with no algorithm change.
    profile: GuidanceProfile | None = None,
) -> StabilityResult:
    """Run the end-to-end v0.1 stability analysis on a CSV.

    Parameters
    ----------
    path:
        Path to the input CSV (the schema documented in
        ``OpenPharmaStability.md``).
    condition:
        The long-term storage condition to analyze (e.g. "25C/60RH").
        The data layer normalizes the input via :func:`parse_condition`
        so callers can pass "25°C/60%RH" too.
    attribute:
        The attribute to analyze. Default "assay" (v0.1's
        primary-supported path).
    product_type:
        Either "product" (default, returns "shelf life") or
        "substance" (returns "retest period"). The math is identical.
    horizon:
        Maximum crossing-search time in months. Default 60 (5 years).
    replicate_policy:
        "individual" (default) or "mean_by_batch_time" /
        "technical_replicates_average". See the data layer.
    seed:
        Random seed to record in the metadata. The v0.1 core path is
        deterministic; this is recorded for reproducibility, not used.
    source_epoch:
        Optional Unix-epoch seconds used to pin the analysis
        timestamp. When ``None`` (the default), the engine falls back
        to the ``SOURCE_DATE_EPOCH`` environment variable, and then
        to wall-clock UTC. Pinning the timestamp makes HTML / JSON
        reports byte-stable across runs for the same input.
    accelerated_condition:
        Storage condition to use for the ICH Q1A(R2) §2.2.7
        significant-change checklist on the accelerated arm
        (default ``"40C/75RH"``). Pass ``None`` (or, via the CLI,
        the empty string) to skip the accelerated arm for this run.
    intermediate_condition:
        Storage condition to use for the significant-change checklist
        on the intermediate arm (default ``"30C/65RH"``). ``None``
        / empty string skips the intermediate arm.
    assay_change_threshold:
        Percent change in assay that counts as "significant" in
        the ICH Q1A(R2) §2.2.7 checklist (default 5.0).
    no_significant_change_gate:
        When ``True``, skip the ICH Q1A significant-change gate
        entirely (the v0.3.1 cap-only behavior is restored
        byte-for-byte). The result keeps the default permissive
        values for the new fields
        (``extrapolation_allowed=True``, ``extrapolation_rationale=""``,
        ``significant_change_*=None``, ``significant_change_details={}``).
        Default ``False`` (gate exercised).
    run_arrhenius:
        v0.5.0 opt-in. When ``True``, group the input rows by their
        ``temp_c`` (or by the temperature parsed from the
        ``condition`` column), estimate a first-order rate per
        temperature from a quick log-linear OLS on ``value > 0``,
        and fit the Arrhenius equation
        ``ln(k) = ln(A) - Ea / (R * T)`` with
        :func:`openpharmastability.stats.arrhenius.fit_arrhenius`.
        Exploratory; does NOT change the Q1E official model. Default
        ``False`` (skipped). Skipped silently when the data carry
        fewer than two distinct temperatures; a warning is recorded
        on the result in that case.
    arrhenius_storage_temp_C:
        v0.5.0 opt-in. Storage temperature (°C) the Arrhenius rate
        is extrapolated TO (default ``25.0``). The fit itself is on
        the stress temperatures in the data; this is the
        ``T_storage`` used for the ``predicted_k_at_storage`` field
        on :class:`~openpharmastability.contracts.ArrheniusResult`.
    run_mkt:
        v0.5.0 opt-in. When ``True`` and the input frame carries a
        ``temp_c`` column with at least one finite value, compute
        the Haynes mean kinetic temperature (USP <1160>) over the
        finite ``temp_c`` values. Exploratory; does NOT change the
        Q1E official model. Default ``False`` (skipped).
    mkt_ea_kJ_per_mol:
        v0.5.0 opt-in. Activation energy for MKT, in kJ/mol
        (default ``83.144`` — USP <1160> common value). Converted
        to J/mol before being passed to
        :func:`openpharmastability.stats.mkt.mean_kinetic_temperature`.
    detect_reduced_design:
        v0.5.0 opt-in. When ``True``, run
        :func:`openpharmastability.regulatory.reduced_design.detect_reduced_design`
        on the raw input frame to detect ICH Q1D reduced designs
        (bracketing and/or matrixing). Exploratory; does NOT
        change the Q1E official model. Default ``False`` (skipped).
    random_effects:
        v0.5.0 opt-in. When ``True``, the regression is fit with a
        mixed-effects model (batch as a random effect) via
        :func:`statsmodels.formula.api.mixedlm`. NOT the Q1E
        default — the confidence bounds and the resulting shelf
        life will almost certainly differ from the fixed-effect
        ANCOVA path. Use for exploration only. A loud warning is
        always appended when this is set. Default ``False``
        (fixed-effect, the Q1E default; byte-equivalent to v0.4.0).

    Returns
    -------
    StabilityResult
        The full decision record.
    """
    if profile is None:
        profile = resolve_profile(None)
    if not isinstance(profile, GuidanceProfile):
        raise TypeError("profile must be a GuidanceProfile or None")
    if assay_change_threshold is None:
        assay_change_threshold = profile.assay_change_threshold_pct

    raw_df = load_table(path)

    # v0.5.0 advanced-statistics hooks — each is opt-in via its
    # own flag. We compute the values here so the rest of the
    # engine (which only sees ``ValidatedData``) can stay
    # unchanged. Each hook is fail-soft: any failure is captured
    # in ``v050_warnings`` and the corresponding field on the
    # final ``StabilityResult`` is left at its v0.4.0 default
    # (``None`` / ``"fixed"``).
    v050_warnings: list[str] = []
    v050_reduced_design_report = None
    v050_mkt_celsius: float | None = None

    if detect_reduced_design:
        try:
            from openpharmastability.regulatory.reduced_design import (
                detect_reduced_design as _detect_reduced_design,
            )
            v050_reduced_design_report = _detect_reduced_design(raw_df)
        except Exception as exc:
            v050_warnings.append(
                f"reduced-design detection failed: {exc!r}"
            )
            v050_reduced_design_report = None

    if run_mkt:
        # v0.5.1 — emit an explicit warning when the input has no
        # usable ``temp_c`` column, so the user knows MKT was
        # silently skipped (the field stays ``None``). The
        # subsequent computation block is gated on the column
        # being present, so the warning is the only thing that
        # changes here for the missing/empty cases.
        if "temp_c" not in raw_df.columns:
            v050_warnings.append(
                "MKT requested but no temp_c column in the input; "
                "mkt_celsius is None."
            )
        elif pd.to_numeric(raw_df["temp_c"], errors="coerce").notna().sum() == 0:
            v050_warnings.append(
                "MKT requested but temp_c column has no finite values; "
                "mkt_celsius is None."
            )
        if "temp_c" in raw_df.columns:
            try:
                from openpharmastability.stats.mkt import (
                    mean_kinetic_temperature as _mean_kinetic_temperature,
                )
                # Use the finite ``temp_c`` values from the input.
                tc = pd.to_numeric(
                    raw_df["temp_c"], errors="coerce"
                ).dropna().astype(float).tolist()
                if tc:
                    v050_mkt_celsius = _mean_kinetic_temperature(
                        tc,
                        Ea_J_per_mol=float(mkt_ea_kJ_per_mol) * 1000.0,
                    )
            except Exception as exc:
                v050_warnings.append(f"MKT computation failed: {exc!r}")
                v050_mkt_celsius = None

    # v0.3.0 data-quality audit. Non-blocking: the audit reports
    # issues, it does NOT gate the engine. We capture the audit
    # findings into a local list and merge them into the main
    # ``warnings`` collection later so they surface in both the JSON
    # record and the HTML report. We always set a ``data_quality``
    # key in the metadata so the report can render a banner. A
    # ``can_analyze=False`` audit does NOT raise; it just appends
    # warnings.
    dq_warnings: list[str] = []
    dq = None
    try:
        from openpharmastability.data.quality import audit_data_quality
        dq = audit_data_quality(raw_df, attribute=attribute, condition=condition)
    except Exception as exc:  # defensive — the audit must never break the engine
        dq_warnings.append(f"data quality audit failed: {exc!r}")
    else:
        if dq.issues:
            for issue in dq.issues:
                dq_warnings.append(
                    f"data_quality[{issue.severity.value}] "
                    f"{issue.code}: {issue.message}"
                )
            dq_warnings.append(
                f"data_quality summary: {dq.n_errors} error(s), "
                f"{dq.n_warnings} warning(s), {dq.n_info} info; "
                f"can_analyze={dq.can_analyze}"
            )

    data = validate_and_select(
        raw_df,
        attribute=attribute,
        condition=condition,
        replicate_policy=replicate_policy,
        bql_policy=bql_policy,
    )

    # v0.5.0 — random-effects opt-in warning. The warning is
    # appended to the local ``warnings`` list (collected further
    # down) so it surfaces in both the JSON record and the HTML
    # report. The ``model_effects`` field on the result is set at
    # the end via a single ``dataclasses.replace`` so all four
    # v0.5.0 fields are set consistently.
    if random_effects:
        v050_warnings.append(
            "Random-effects model selected. Confidence bounds and "
            "the resulting shelf life DIFFER from the ICH Q1E "
            "fixed-effect (pooled/ANCOVA) approach and are NOT the "
            "Q1E default. Use for exploration only."
        )

    fits = fit_models(data, random_effects=random_effects)
    poolability = decide_poolability(fits, data, alpha=profile.poolability_alpha)
    model_kind, fit = select_model(poolability, fits)

    crossing = find_crossing(
        fit,
        data,
        horizon=horizon,
        one_sided_quantile=profile.one_sided_quantile,
        two_sided_quantile=profile.two_sided_quantile,
    )

    # v0.5.0 — Arrhenius opt-in. Computed between ``find_crossing``
    # and the result construction so the value is available for the
    # final ``dataclasses.replace`` at the end of ``analyze()``.
    # The fit is fail-soft: any failure is recorded in
    # ``v050_warnings`` and the field on the result is left at
    # its v0.4.0 default (``None``).
    v050_arrhenius_result = None
    if run_arrhenius:
        v050_arrhenius_result, _arr_warnings = _compute_arrhenius(
            data=data,
            storage_temp_C=float(arrhenius_storage_temp_C),
        )
        v050_warnings.extend(_arr_warnings)

    # Statistical crossing: only meaningful when the bound actually
    # crossed within the horizon.
    statistical_crossing: float | None = (
        float(crossing.crossing_months)
        if crossing.crossing_months is not None
        and crossing.status is CrossingStatus.CROSSED
        else None
    )

    # Supported shelf life: round the statistical crossing DOWN to
    # whole months. Floor of the crossing time. If no crossing, we
    # report "at least horizon, not limiting" (engine stores None;
    # the report surfaces the horizon).
    if crossing.status is CrossingStatus.CROSSED and statistical_crossing is not None:
        supported_shelf_life: int | None = int(math.floor(statistical_crossing))
    elif crossing.status is CrossingStatus.FAIL_AT_BASELINE:
        supported_shelf_life = 0
    else:
        # NO_CROSSING or FLAT_OR_OPPOSITE -> no positive crossing claimed.
        supported_shelf_life = None

    # Observed data length (longest time point in the data).
    observed_data_months = float(max(data.time_points)) if data.time_points else 0.0

    # Extrapolation flag (tentative; caps refine it later).
    extrapolation_flag = (
        supported_shelf_life is not None
        and supported_shelf_life > observed_data_months
    )

    # Diagnostics.
    diagnostics = run_diagnostics(fit, data)

    # Collect warnings: data-layer warnings + poolability notes + diagnostic notes.
    warnings: list[str] = list(data.warnings)
    warnings.extend(dq_warnings)
    warnings.extend(poolability.notes)
    warnings.extend(diagnostics.notes)
    # v0.5.0 — advanced-statistics warnings (random-effects note,
    # Arrhenius / MKT / reduced-design failures, etc.). These are
    # computed early but appended to the main ``warnings`` list
    # here so they appear in the report in a single block.
    warnings.extend(v050_warnings)
    # v0.5.1 — mixed-model convergence / boundary warnings. Surfaced
    # here (not later) so they sit in the same warnings list the
    # StabilityResult is constructed with, and so the OLS path (which
    # always reports ``converged=True``, ``boundary=False``) does NOT
    # emit a warning. The check is gated on ``random_effects`` so the
    # default fixed-effect pipeline is byte-equivalent to v0.5.0.
    if random_effects:
        _conv = fit.design.get(
            "convergence",
            {"converged": True, "boundary": False, "message": ""},
        )
        if bool(_conv.get("boundary", False)):
            warnings.append(
                "Mixed model hit a boundary: random-effect variance "
                "collapsed to 0 (the model reduced to a fixed-effect OLS). "
                "The shelf-life estimate is essentially the OLS estimate; "
                "the random-effects path added no information. Treat "
                "with caution."
            )
        if not bool(_conv.get("converged", True)):
            warnings.append(
                f"Mixed model did not converge: {_conv.get('message', 'unknown reason')}. "
                "The shelf-life estimate may be unreliable; consider the "
                "fixed-effect default."
            )
    if (
        data.direction is not Direction.DECREASING
        and data.direction is not Direction.INCREASING
    ):
        warnings.append(
            f"direction is {data.direction.value!r}; v0.1 only fully supports "
            "DECREASING (assay) and INCREASING (degradant) crossings."
        )
    if data.n_batches < 3:
        warnings.append(
            f"only {data.n_batches} batch(es) present; Q1E expects at least 3."
        )
    if data.n_batches >= 3 and len(data.time_points) < 3:
        warnings.append(
            f"only {len(data.time_points)} distinct time point(s); "
            "need at least 3 (incl. baseline) for a meaningful slope."
        )

    # Build the result.
    result = StabilityResult(
        attribute=attribute,
        condition=data.condition,
        direction=data.direction,
        model=model_kind,
        poolability=poolability,
        fit=fit,
        crossing=crossing,
        supported_shelf_life_months=supported_shelf_life,
        statistical_crossing_months=statistical_crossing,
        observed_data_months=observed_data_months,
        extrapolation_flag=extrapolation_flag,
        diagnostics=diagnostics,
        warnings=warnings,
        metadata=_build_metadata(path, raw_df, seed, source_epoch),
        deliverable_term=_deliverable_term_for(product_type),
        product_type=product_type,
        plot_filename="confidence_plot.png",
        bql_summary=data.bql_summary,
        # v0.11.0: record the active guidance profile's name as an
        # immutable audit fact for the run. Sourced from ``profile.name``
        # so the JSON record and HTML report can surface which guidance
        # governed the decision.
        profile_name=profile.name,
        guidance_status=profile.status,
        guidance_reference=profile.reference,
        guidance_confidence=profile.confidence,
        guidance_poolability_alpha=profile.poolability_alpha,
        guidance_assay_change_threshold_pct=profile.assay_change_threshold_pct,
        guidance_disclaimer=profile.disclaimer,
    )

    # v0.3.0: surface the data-quality audit summary in the result
    # metadata so the report can show a banner. ``metadata`` is a
    # plain dict (not a frozen field), so in-place mutation is fine.
    if dq is not None:
        result.metadata["data_quality"] = {
            "n_errors": int(dq.n_errors),
            "n_warnings": int(dq.n_warnings),
            "n_info": int(dq.n_info),
            "can_analyze": bool(dq.can_analyze),
            "n_issues": len(dq.issues),
        }
    else:
        # Audit failed before producing a report; record the fact.
        result.metadata["data_quality"] = {
            "n_errors": 0,
            "n_warnings": 0,
            "n_info": 0,
            "can_analyze": False,
            "n_issues": 0,
        }

    # Apply extrapolation caps (may add a warning and revise the
    # supported value).
    result = apply_extrapolation_caps(
        result,
        max_factor=profile.extrapolation_max_factor,
        max_months_beyond=profile.extrapolation_max_months_beyond,
    )

    # v0.4.0 — ICH Q1A(R2) §2.2.7 significant-change gate. Wired in
    # after the v0.3.1 cap math so the binding cap becomes the
    # minimum of the Q1E 2x/+12 rule of thumb and the Q1E
    # significant-change allowance. The gate is fail-soft: any
    # exception (missing optional column, missing
    # ``openpharmastability.regulatory`` module, parser error on a
    # condition string, etc.) is caught and a single warning is
    # appended. The default permissive values on the result are
    # left untouched, so v0.3.1 callers see the same output they
    # always did.
    result = _run_significant_change_gate(
        result=result,
        raw_df=raw_df,
        data=data,
        attribute=attribute,
        accelerated_condition=accelerated_condition,
        intermediate_condition=intermediate_condition,
        assay_change_threshold=assay_change_threshold,
        no_significant_change_gate=no_significant_change_gate,
        profile=profile,
    )

    # v0.3.0: optional transform-candidate evidence. Recorded on
    # the result so the report can surface it. The official v0.3.0
    # decision model is unchanged — raw-scale linear.
    if assess_transforms:
        try:
            from openpharmastability.stats.transforms import assess_transforms
            ta = assess_transforms(data.df, attribute=attribute)
            object.__setattr__(result, "transform_assessment", ta)
        except Exception as exc:  # pragma: no cover — defensive
            warnings.append(f"transform assessment failed: {exc!r}")

    # v0.7.0 — leave-one-out sensitivity analysis over Cook's-distance
    # influential points. Re-runs the full analysis for each flagged
    # point and attaches a `SensitivityReport` to the result. The
    # trigger set is `result.diagnostics.influential_points`; when
    # it is empty the helper returns a no-op report with an
    # explanatory summary. Any exception in the helper is captured
    # as a warning and the field stays at the v0.6 default (None).
    #
    # v0.8.0 — additive ``sensitivity_mode`` kwarg: ``"row"`` (the
    # v0.7.0 default, preserved byte-equivalent for callers that
    # do not opt in) does leave-one-out over Cook's-distance
    # influential points; ``"batch"`` does leave-one-batch-out over
    # the distinct batches in the data used for the fit. The
    # default ``"row"`` keeps v0.7.0 output byte-for-byte.
    if run_sensitivity:
        try:
            from openpharmastability.stats.sensitivity import (
                compute_sensitivity as _compute_sensitivity,
            )
            v070_sens = _compute_sensitivity(
                result, data, mode=sensitivity_mode, horizon=horizon,
                profile=profile,
            )
        except Exception as exc:  # defensive
            warnings.append(f"sensitivity analysis failed: {exc!r}")
            v070_sens = None
        else:
            result = dataclasses.replace(result, sensitivity_report=v070_sens)

    # v0.8.0 — Arrhenius-driven shelf-life prediction. Model-based
    # exploratory prediction: reuse the v0.5.0 / v0.7.0 Arrhenius
    # fit, then run the closed-form crossing math against the data-
    # derived spec on top of the extrapolated rate. The official
    # Q1E shelf-life decision above is unchanged; this only
    # populates `result.arrhenius_shelf_life`. Fail-soft: any
    # exception in the helper is captured as a warning and the
    # field stays at the v0.7.0 default (None).
    v080_arrhenius_shelf_life = None
    if run_arrhenius_shelf_life:
        try:
            from openpharmastability.stats.arrhenius_shelf_life import (
                predict_arrhenius_shelf_life as _v080_predict,
            )
            v080_arrhenius_shelf_life = _v080_predict(
                data, storage_temp_C=float(arrhenius_shelf_life_storage_temp_C),
            )
        except Exception as exc:  # defensive
            warnings.append(f"Arrhenius-driven shelf-life prediction failed: {exc!r}")
            v080_arrhenius_shelf_life = None

    # v0.9.0 — per-batch Arrhenius rate diagnostic. Builds a
    # ``{batch: {temp_C_str: rate}}`` dict via
    # :func:`openpharmastability.stats.arrhenius._per_batch_rates`
    # and runs the robust-z outlier detection. Only meaningful
    # when ``run_arrhenius=True`` produced an ``ArrheniusResult``
    # (so there is a pooled fit to compare against); otherwise the
    # diagnostic is skipped with a warning. The two new fields on
    # ``ArrheniusResult`` (``per_batch_rate_by_temp`` and
    # ``outlier_batches``) are attached via a
    # ``dataclasses.replace`` so callers see the diagnostic on the
    # same dataclass instance they already received from the
    # v0.5.0 / v0.7.0 wire. Fail-soft: any exception is captured
    # as a warning and the fields stay at their v0.8.0 defaults.
    # Warnings raised in this block are appended to
    # ``result.warnings`` via ``dataclasses.replace`` because by
    # this point ``apply_extrapolation_caps`` and
    # ``_run_significant_change_gate`` have re-bound
    # ``result.warnings`` to a fresh list — the local ``warnings``
    # alias from earlier in ``analyze()`` no longer reaches the
    # result.
    if run_arrhenius_per_batch:
        if v050_arrhenius_result is None:
            _new_warnings = list(result.warnings)
            _new_warnings.append(
                "Per-batch Arrhenius diagnostic skipped: requires --arrhenius "
                "(no pooled Arrhenius fit was produced)."
            )
            result = dataclasses.replace(result, warnings=_new_warnings)
        else:
            try:
                from openpharmastability.stats.arrhenius import (
                    _per_batch_rates as _v090_per_batch_rates,
                )
                v090_per_batch = _v090_per_batch_rates(
                    data.df,
                    direction=(
                        "increasing"
                        if data.direction is Direction.INCREASING
                        else "decreasing"
                    ),
                )
                v090_outlier_batches = _detect_arrhenius_outliers(
                    v090_per_batch, z_threshold=2.5,
                )
                # Surface a one-line summary on the underlying
                # ArrheniusResult's notes so the report can
                # explain the outlier set.
                _existing_notes = list(getattr(
                    v050_arrhenius_result, "notes", []
                ) or [])
                if v090_outlier_batches:
                    _existing_notes.append(
                        "v0.9.0 per-batch outlier(s) flagged (robust z > 2.5): "
                        + ", ".join(v090_outlier_batches)
                    )
                else:
                    _existing_notes.append(
                        "v0.9.0 per-batch diagnostic: no outliers "
                        "(robust z <= 2.5 for all batches)."
                    )
                v050_arrhenius_result = dataclasses.replace(
                    v050_arrhenius_result,
                    per_batch_rate_by_temp=v090_per_batch,
                    outlier_batches=v090_outlier_batches,
                    notes=_existing_notes,
                )
            except Exception as exc:  # defensive
                _new_warnings = list(result.warnings)
                _new_warnings.append(
                    f"Per-batch Arrhenius diagnostic failed: {exc!r}"
                )
                result = dataclasses.replace(result, warnings=_new_warnings)

    # v0.5.0 — final ``dataclasses.replace`` that sets all four
    # advanced-statistics fields in one shot. Doing it in a single
    # ``replace`` (rather than four separate calls) keeps the
    # field-set consistent regardless of which opt-in flags the
    # caller passed. When the corresponding feature was not
    # exercised, the field keeps its v0.4.0 default (None /
    # ``"fixed"``).
    # v0.5.1 — also lift the fit-level ``convergence`` sub-block to a
    # top-level ``model_convergence`` field on the result. The OLS
    # path always reports ``{"converged": True, "boundary": False,
    # "message": "OLS"}``; the random-effects path surfaces whatever
    # ``_detect_mixed_convergence`` computed (converged / boundary /
    # message). The ``.get("convergence", default)`` keeps the engine
    # robust against hand-built FitResult fixtures that predate the
    # v0.5.1 sub-block.
    # v0.8.0 — also set the v0.8.0 ``arrhenius_shelf_life`` field in
    # the same replace so all advanced-statistics fields are set
    # together. Default ``None`` so v0.7.x callers and hand-built
    # fixtures that predate the v0.8.0 field continue to work
    # unchanged.
    result = dataclasses.replace(
        result,
        arrhenius_result=v050_arrhenius_result,
        mkt_celsius=v050_mkt_celsius,
        reduced_design_report=v050_reduced_design_report,
        model_effects=("random" if random_effects else "fixed"),
        model_convergence=fit.design.get(
            "convergence",
            {"converged": True, "boundary": False, "message": ""},
        ),
        arrhenius_shelf_life=v080_arrhenius_shelf_life,
    )

    return result


# ---------------------------------------------------------------------------
# v0.5.0 — Arrhenius helper
# ---------------------------------------------------------------------------


def _compute_arrhenius(
    data: ValidatedData,
    storage_temp_C: float,
) -> tuple[Optional[ArrheniusResult], list[str]]:
    """Estimate one rate per temperature and run the Arrhenius fit.

    v0.5.1 audit fix: the helper now operates on the
    :class:`ValidatedData` returned by :func:`validate_and_select`
    rather than the raw input frame. This guarantees two things:

    1. **Attribute isolation.** Rates are computed from rows of the
       single attribute the user asked to analyze; rows of any
       other attribute in a multi-attribute file cannot contaminate
       the per-temperature rates.
    2. **Condition isolation.** The condition filter has already
       been applied by ``validate_and_select``; the helper no
       longer sees rows from conditions the user did not request.

    Steps:

    0. **Direction gate.** For ``BIDIRECTIONAL`` / ``UNKNOWN``
       attributes the sign of the rate is ambiguous, so the fit is
       skipped with a warning.
    1. **Sign multiplier.** ``DECREASING`` -> ``sign = -1``,
       ``INCREASING`` -> ``sign = +1``.
    2. **Group by temperature.** If ``data.df`` has a ``temp_c``
       column with at least one finite value, group by it.
       Otherwise fall back to parsing the temperature from the
       ``condition`` column (which ``validate_and_select``
       already normalized to the single requested condition —
       so this fallback will typically yield one temperature and
       the ``< 2 temps`` skip fires).
    3. **Per-temperature rate.** Same log-linear OLS as today
       (``log(value) ~ time_months``) on the rows with
       ``value > 0``; the rate is ``abs(slope)`` in the
       expected-sign branch and the spec-documented
       "abs(slope) with sign corrected" fallback when the
       fitted slope's sign disagrees with the declared direction.
    4. **Two-temperature minimum.** If fewer than two distinct
       temperatures are usable, record a warning and return
       ``None``.
    5. Otherwise call
       :func:`openpharmastability.stats.arrhenius.fit_arrhenius`.
       Any exception is caught, a warning is recorded, and
       ``None`` is returned.

    Returns
    -------
    (result, warnings)
        ``result`` is the :class:`ArrheniusResult` on success or
        ``None`` on failure / skip. ``warnings`` is a list of
        human-readable warning strings the caller should append to
        the main ``StabilityResult.warnings`` list.
    """
    warnings: list[str] = []

    # 0) Direction gate. BIDIRECTIONAL/UNKNOWN have an ambiguous
    #    rate sign, so we skip with a single warning rather than
    #    guess and produce a meaningless rate.
    if (
        data.direction is Direction.BIDIRECTIONAL
        or data.direction is Direction.UNKNOWN
    ):
        warnings.append(
            "Arrhenius fit skipped: direction is BIDIRECTIONAL/UNKNOWN; "
            "rate sign is ambiguous."
        )
        return None, warnings

    # 1) Sign multiplier. DECREASING means the conventional
    #    ``rate = -slope`` of the log-linear fit, so the
    #    multiplicative factor that recovers the magnitude is
    #    ``-1`` (since for a decreasing attribute the fitted
    #    slope is negative). INCREASING means ``rate = +slope``,
    #    factor ``+1``. See step 3 for the "wrong-signed slope"
    #    fallback.
    if data.direction is Direction.DECREASING:
        sign = -1
    else:  # Direction.INCREASING
        sign = +1

    try:
        from openpharmastability.stats.arrhenius import (
            fit_arrhenius as _fit_arrhenius,
        )
    except Exception as exc:  # pragma: no cover — module missing
        warnings.append(f"Arrhenius fit failed: {exc!r}")
        return None, warnings

    # 2) Build the per-temperature groups from ``data.df`` (the
    #    audit fix: this frame is already filtered to the selected
    #    attribute and condition, so other attributes' rows cannot
    #    contaminate the rates).
    raw_df = data.df
    if "temp_c" in raw_df.columns:
        tc_series = pd.to_numeric(raw_df["temp_c"], errors="coerce")
        # Use a normalized key (str of the float) so equal temps
        # group together. Drop rows with no finite temp_c.
        work = raw_df.assign(_temp_c=tc_series).dropna(subset=["_temp_c"])
        if work.empty:
            warnings.append("Arrhenius fit skipped: no finite temp_c values")
            return None, warnings
        group_keys: list[float] = sorted(work["_temp_c"].unique().tolist())
    else:
        # Fall back to the temperature parsed from the condition.
        from openpharmastability.data.conditions import parse_condition
        temps_per_row: list[Optional[float]] = []
        for cond in raw_df["condition"].astype(str).tolist():
            parsed = parse_condition(cond)
            # parse_condition normalizes to "T/RH" form; extract the int T.
            try:
                head = parsed.split("/", 1)[0]
                t_val = float(head.rstrip("Cc").strip())
                temps_per_row.append(t_val)
            except (ValueError, IndexError):
                temps_per_row.append(None)
        work = raw_df.assign(_temp_c=pd.Series(temps_per_row, index=raw_df.index))
        work = work.dropna(subset=["_temp_c"])
        if work.empty:
            warnings.append(
                "Arrhenius fit skipped: no temperature derivable from condition"
            )
            return None, warnings
        group_keys = sorted(work["_temp_c"].unique().tolist())

    if len(group_keys) < 2:
        warnings.append(
            f"Arrhenius fit skipped: need >= 2 distinct temperatures, "
            f"got {len(group_keys)}."
        )
        return None, warnings

    # 3) Per-temperature log-linear OLS to get a rate. The rate
    #    is always a positive magnitude; the sign convention
    #    is encoded by ``sign`` (``-1`` for DECREASING, ``+1``
    #    for INCREASING). For a correctly-signed slope the
    #    rate is ``abs(slope)`` (i.e. ``sign * slope`` since
    #    ``sign`` and ``slope`` have the same sign). For a
    #    wrong-signed slope we still take ``abs(slope)`` and
    #    record the spec-documented warning so the user knows
    #    the data trended the wrong way at that temperature.
    rate_by_temp: dict[float, float] = {}
    for t_key in group_keys:
        sub = work[work["_temp_c"] == t_key]
        pos = sub[sub["value"] > 0.0]
        if len(pos) < 2:
            # Not enough finite values to fit a slope; skip this
            # group rather than poison the regression.
            continue
        try:
            slope = float(np.polyfit(
                pos["time_months"].astype(float).to_numpy(),
                np.log(pos["value"].astype(float).to_numpy()),
                deg=1,
            )[0])
        except (np.linalg.LinAlgError, ValueError):
            continue

        if sign < 0 and slope > 0:
            # DECREASING attribute but the fitted slope at this
            # temperature is positive. Data trended the wrong
            # way (noise, error, or attribute was mis-declared);
            # take the magnitude and warn so the user can audit.
            warnings.append(
                f"Arrhenius: fitted slope is positive for DECREASING "
                f"attribute at T={t_key}°C; using abs(slope) with sign corrected."
            )
            rate = abs(slope)
        elif sign > 0 and slope < 0:
            # INCREASING attribute but the fitted slope at this
            # temperature is negative. Symmetric case.
            warnings.append(
                f"Arrhenius: fitted slope is negative for INCREASING "
                f"attribute at T={t_key}°C; using abs(slope) with sign corrected."
            )
            rate = abs(slope)
        else:
            # Sign is correct; rate is the magnitude. Equivalent
            # to ``sign * slope`` since ``sign`` and ``slope``
            # share the same sign (DECREASING/-; INCREASING/+).
            rate = abs(slope)

        rate_by_temp[float(t_key)] = rate

    if len(rate_by_temp) < 2:
        warnings.append(
            f"Arrhenius fit skipped: need >= 2 distinct temperatures with "
            f"enough data to fit, got {len(rate_by_temp)}."
        )
        return None, warnings

    # 4) Run the fit.
    try:
        result = _fit_arrhenius(rate_by_temp, storage_temp_C=storage_temp_C)
    except (NotImplementedError, ValueError, KeyError) as exc:
        warnings.append(f"Arrhenius fit failed: {exc!r}")
        return None, warnings
    except Exception as exc:  # pragma: no cover — defensive
        warnings.append(f"Arrhenius fit failed: {exc!r}")
        return None, warnings
    return result, warnings


# ---------------------------------------------------------------------------
# v0.4.0 — ICH Q1A(R2) significant-change gate
# ---------------------------------------------------------------------------


def _build_gate_attribute_meta(
    data: ValidatedData,
    attribute: str,
    raw_df: pd.DataFrame,
) -> dict:
    """Build the ``attribute_meta`` dict consumed by
    :func:`openpharmastability.regulatory.evaluate_significant_change`.

    The dict carries the per-attribute spec limits, the direction
    (as a boolean ``is_increasing``), and the column names the
    significant-change checklist looks for. Optional pH columns
    are forwarded when present; absent optional columns are simply
    omitted so the checklist's "missing column -> skip criterion"
    logic fires.
    """
    meta: dict = {
        "attribute": str(attribute),
        # Column-name hints the checklist uses. Pinned to the v0.1
        # schema so downstream code can locate the batch key.
        "batch": "batch",
        "is_increasing": bool(data.direction is Direction.INCREASING),
        "lower_spec": data.lower_spec,
        "upper_spec": data.upper_spec,
        "physical_fail_col": "physical_fail",
        "dissolution_fail_col": "dissolution_fail",
        "degradant_oos_col": "degradant_oos",
    }
    if "ph_spec_low" in raw_df.columns:
        meta["ph_spec_low"] = "ph_spec_low"
    if "ph_spec_high" in raw_df.columns:
        meta["ph_spec_high"] = "ph_spec_high"
    return meta


def _subset_for_condition(
    raw_df: pd.DataFrame,
    attribute: str,
    condition_label: str | None,
) -> pd.DataFrame:
    """Return the rows of ``raw_df`` whose parsed condition matches
    ``condition_label`` AND whose attribute is ``attribute``.

    An empty frame is the documented "no data for this condition"
    signal. ``condition_label=None`` is also empty.
    """
    if condition_label is None or str(condition_label).strip() == "":
        return raw_df.iloc[0:0].copy()
    from openpharmastability.data.conditions import parse_condition
    target = parse_condition(condition_label)
    if "attribute" in raw_df.columns:
        sub = raw_df[
            (raw_df["attribute"].astype(str) == str(attribute))
            & (raw_df["condition"].astype(str) == target)
        ].copy()
    else:
        sub = raw_df[raw_df["condition"].astype(str) == target].copy()
    return sub


def _build_significant_change_details(
    acc_sc,
    inter_sc,
) -> dict:
    """Assemble the ``significant_change_details`` payload carried on
    the :class:`StabilityResult`.

    Returns a JSON-serializable dict that always carries both the
    accelerated and intermediate per-criterion details, even when
    one of the two arms did not have data.
    """
    out: dict = {
        "accelerated": {
            "occurred": None,
            "first_change_month": None,
            "reasons": [],
            "details": {},
        },
        "intermediate": {
            "occurred": None,
            "first_change_month": None,
            "reasons": [],
            "details": {},
        },
    }
    if acc_sc is not None:
        out["accelerated"] = {
            "occurred": bool(acc_sc.occurred),
            "first_change_month": acc_sc.first_change_month,
            "reasons": list(acc_sc.reasons or []),
            "details": dict(acc_sc.details or {}),
        }
    if inter_sc is not None:
        out["intermediate"] = {
            "occurred": bool(inter_sc.occurred),
            "first_change_month": inter_sc.first_change_month,
            "reasons": list(inter_sc.reasons or []),
            "details": dict(inter_sc.details or {}),
        }
    return out


def _run_significant_change_gate(
    result: StabilityResult,
    raw_df: pd.DataFrame,
    data: ValidatedData,
    attribute: str,
    accelerated_condition: str | None,
    intermediate_condition: str | None,
    assay_change_threshold: float,
    no_significant_change_gate: bool,
    profile: GuidanceProfile | None = None,
) -> StabilityResult:
    """Run the ICH Q1A(R2) §2.2.7 significant-change gate and refine
    the result's extrapolation decision.

    Behavior:

    * ``no_significant_change_gate=True`` -> append a single warning
      and return the result unchanged. This restores v0.3.1 cap-only
      behavior byte-for-byte (the result keeps the default
      ``extrapolation_allowed=True``, ``extrapolation_rationale=""``,
      ``significant_change_*=None``, ``significant_change_details={}``).
    * Otherwise: build the accelerated and intermediate frames from
      ``raw_df``, evaluate the checklist, ask the regulatory
      decision table for the allowance, then call
      :func:`apply_extrapolation_caps` with the allowance.
    * Any exception inside the gate is caught, a single warning is
      appended, and the default permissive values are left in place.
    """
    if profile is None:
        profile = resolve_profile(None)

    if no_significant_change_gate:
        new_warnings = list(result.warnings)
        new_warnings.append(
            "significant-change gate disabled via --no-significant-change-gate"
        )
        return dataclasses.replace(result, warnings=new_warnings)

    try:
        # Lazy import: the regulatory package is owned by another
        # wave and may not be present in partial builds. We treat
        # the import error the same as any other gate failure.
        from openpharmastability.regulatory import (
            evaluate_significant_change,
            extrapolation_allowance,
        )
    except Exception as exc:
        new_warnings = list(result.warnings)
        new_warnings.append(f"significant-change gate failed: {exc!r}")
        return dataclasses.replace(result, warnings=new_warnings)

    # We snapshot the v0.3.1 state so a mid-gate exception can
    # roll back to the pre-gate defaults on the new fields. The
    # rollback uses ``dataclasses.replace`` to clear the new fields
    # to the v0.3.1 permissive values.
    pre_gate_result = dataclasses.replace(
        result,
        significant_change_accelerated=None,
        significant_change_intermediate=None,
        extrapolation_allowed=True,
        extrapolation_rationale="",
        significant_change_details={},
    )

    try:
        attribute_meta = _build_gate_attribute_meta(data, attribute, raw_df)

        acc_df = _subset_for_condition(
            raw_df, attribute, accelerated_condition,
        )
        inter_df = _subset_for_condition(
            raw_df, attribute, intermediate_condition,
        )

        acc_sc = (
            evaluate_significant_change(
                acc_df, attribute_meta, str(accelerated_condition or ""),
                float(assay_change_threshold),
            )
            if not acc_df.empty
            else None
        )
        inter_sc = (
            evaluate_significant_change(
                inter_df, attribute_meta, str(intermediate_condition or ""),
                float(assay_change_threshold),
            )
            if not inter_df.empty
            else None
        )

        allowed, cap_months, rationale = extrapolation_allowance(
            acc_sc, inter_sc, result.observed_data_months,
        )

        result = dataclasses.replace(
            result,
            significant_change_accelerated=(
                bool(acc_sc.occurred) if acc_sc is not None else None
            ),
            significant_change_intermediate=(
                bool(inter_sc.occurred) if inter_sc is not None else None
            ),
            extrapolation_allowed=bool(allowed),
            extrapolation_rationale=str(rationale or ""),
            significant_change_details=_build_significant_change_details(
                acc_sc, inter_sc,
            ),
        )

        # Refine the cap. apply_extrapolation_caps will append a
        # warning and cap the supported value when the allowance
        # is binding.
        result = apply_extrapolation_caps(
            result, allowance=(bool(allowed), float(cap_months), str(rationale or "")),
            max_factor=profile.extrapolation_max_factor,
            max_months_beyond=profile.extrapolation_max_months_beyond,
        )
        return result
    except Exception as exc:
        # Fail-soft: log, then roll back to the pre-gate state so
        # the new fields are at their v0.3.1 permissive defaults.
        new_warnings = list(pre_gate_result.warnings)
        new_warnings.append(f"significant-change gate failed: {exc!r}")
        return dataclasses.replace(pre_gate_result, warnings=new_warnings)


# ---------------------------------------------------------------------------
# v0.9.0 — per-batch Arrhenius outlier detection
# ---------------------------------------------------------------------------


def _detect_arrhenius_outliers(
    per_batch_rates: dict[str, dict[str, float]],
    *,
    z_threshold: float = 2.5,
) -> list[str]:
    """Robust-z outlier detection over the v0.9.0 per-batch rate dict.

    For each temperature in the per-batch dict, compute the median of
    the per-batch rates and the median absolute deviation (MAD). The
    robust z-score for each batch at that temperature is

    .. code-block:: text

        z_b = (rate_b - median) / (MAD * 1.4826)

    where ``1.4826`` is the standard MAD-to-sigma scaling factor for a
    Gaussian (so the z-score is comparable to a classical z-score
    under normality). A batch is flagged if ``|z_b| > z_threshold``
    for ANY temperature. The result is a sorted list of batch
    identifiers.

    When fewer than three batches are present at a given temperature,
    that temperature is skipped (MAD-based outlier detection is not
    meaningful with one or two points). When ``MAD == 0`` (all
    batches at the same rate for that temperature), no batch is
    flagged for that temperature.

    Parameters
    ----------
    per_batch_rates:
        ``{batch: {temp_C_str: k(1/month)}}`` mapping produced by
        :func:`openpharmastability.stats.arrhenius._per_batch_rates`.
    z_threshold:
        Robust-z threshold (default ``2.5``). The classical 2-sigma
        rule corresponds to ``2.0``; ``2.5`` is the canonical
        conservative choice for batch-level pharma quality work.

    Returns
    -------
    list[str]
        Sorted batch identifiers flagged as outliers in at least one
        temperature. Empty when no outlier is found.
    """
    if not per_batch_rates:
        return []
    # Collect the set of temperatures across all batches.
    all_temps: set[str] = set()
    for rates in per_batch_rates.values():
        all_temps.update(rates.keys())
    if not all_temps:
        return []

    flagged: set[str] = set()
    for t in all_temps:
        # Gather (batch, rate) for every batch that has this temp.
        per_temp = [
            (b, float(rates[t]))
            for b, rates in per_batch_rates.items()
            if t in rates
        ]
        if len(per_temp) < 3:
            # Not enough batches for a meaningful MAD-based outlier.
            continue
        rates_arr = np.array([r for _, r in per_temp], dtype=float)
        median = float(np.median(rates_arr))
        mad = float(np.median(np.abs(rates_arr - median)))
        if mad <= 0.0:
            # All batches identical at this temperature; no outlier.
            continue
        scale = mad * 1.4826
        for b, rate in per_temp:
            z = abs(rate - median) / scale
            if z > float(z_threshold):
                flagged.add(str(b))
    return sorted(flagged)


__all__ = ["analyze"]
