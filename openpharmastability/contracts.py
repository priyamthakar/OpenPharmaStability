"""Frozen shared contracts for OpenPharmaStability v0.1.

This module is the authoritative seam between sub-agents (see AGENTS.md §4).
After Wave 0 it is READ-ONLY. Any sub-agent that believes a contract is wrong
must STOP and report to the orchestrator instead of editing this file.

The dataclasses here are the shape of the world. Function signatures
documented in this file (as `# Signature:` comments) are the public API that
downstream modules may rely on; each owning module re-exports them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:  # avoid runtime imports; keeps contracts stdlib-only
    import numpy as np
    import pandas as pd


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS: list[str] = [
    "batch",
    "condition",
    "time_months",
    "attribute",
    "value",
]
# Plus at least one of: lower_spec, upper_spec

POOLABILITY_ALPHA: float = 0.25
CONFIDENCE: float = 0.95

# One-sided 95% t-quantile target (5% in one tail). NOT 0.975.
ONE_SIDED_T_QUANTILE: float = 0.95
# Two-sided 95% t-quantile target (2.5% in each tail).
TWO_SIDED_T_QUANTILE: float = 0.975

# Default evaluation horizon (months) when caller does not provide one.
DEFAULT_HORIZON_MONTHS: float = 60.0

# RT extrapolation guardrails (Q1E rule of thumb).
EXTRAPOLATION_MAX_FACTOR: float = 2.0
EXTRAPOLATION_MAX_MONTHS_BEYOND: float = 12.0

# Tool version (mirrors __init__.__version__).
TOOL_VERSION: str = "1.0.1"

# Mandatory disclaimer (verbatim from the spec §"Regulatory Report Mode").
DISCLAIMER: str = (
    "This report is ICH Q1E-inspired and intended for educational, "
    "exploratory, and reproducible decision-support use. It is not a "
    "substitute for qualified regulatory, statistical, or quality review. "
    "The toolkit does not provide 21 CFR Part 11 audit trails, electronic "
    "signatures, or data integrity controls, and is not a validated GxP "
    "system."
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Direction(str, Enum):
    DECREASING = "decreasing"
    INCREASING = "increasing"
    BIDIRECTIONAL = "bidirectional"
    UNKNOWN = "unknown"


class ModelKind(str, Enum):
    POOLED = "pooled"
    COMMON_SLOPE = "common_slope_batch_intercepts"
    SEPARATE = "batch_specific"


class Poolability(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class CrossingStatus(str, Enum):
    CROSSED = "crossed"
    NO_CROSSING = "no_crossing"
    FAIL_AT_BASELINE = "fail_at_baseline"
    FLAT_OR_OPPOSITE = "flat_or_opposite"


class AttributeRole(str, Enum):
    """How an attribute participates in the multi-attribute limiting decision.

    PRIMARY: included in the limiting shelf-life decision (default).
    SUPPORTIVE: analyzed and reported, but does NOT govern the limiting decision.
    INFORMATIONAL: summarized only; no full analysis.
    EXCLUDED: skipped, with a reason.
    """
    PRIMARY = "primary"
    SUPPORTIVE = "supportive"
    INFORMATIONAL = "informational"
    EXCLUDED = "excluded"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ValidatedData:
    """One attribute, one condition, normalized DataFrame + spec context."""

    df: "pd.DataFrame"  # normalized: columns batch, condition, time_months, attribute, value
    attribute: str
    condition: str
    direction: Direction
    lower_spec: Optional[float]
    upper_spec: Optional[float]
    n_batches: int
    time_points: list[float]
    warnings: list[str] = field(default_factory=list)
    bql_summary: "BQLSummary" = field(default_factory=lambda: BQLSummary(
        policy="exclude", n_bql_rows=0, n_substituted=0, n_excluded=0,
    ))


@dataclass
class FitResult:
    """A fitted linear model on the raw scale.

    `params` keys (per model):
        POOLED:            {"b0": float, "b1": float}
        COMMON_SLOPE:      {"b0_<batch>": ..., "b1": float}
        SEPARATE:          {"b0_<batch>": ..., "b1_<batch>": float}
    `fitted_fn` is one of:
        POOLED:            t -> yhat
        COMMON_SLOPE:      batch -> (t -> yhat)
        SEPARATE:          batch -> (t -> yhat)
    `cov` is the parameter covariance s^2 * (X'X)^-1 in the parameter order
        implied by `params`.
    `design` holds the per-fit helpers (tbar, Sxx, n, per-batch tbar/Sxx/n)
        so that bound and crossing math can reuse the correct design.
    """

    kind: ModelKind
    params: dict[str, float]
    df_resid: int
    s_resid: float  # residual standard error
    cov: "np.ndarray"
    fitted_fn: Callable[..., Callable[[float], float]] | Callable[[float], float]
    design: dict[str, Any]
    batches: list[str] = field(default_factory=list)


@dataclass
class PoolabilityResult:
    decision: Poolability
    p_slopes: float
    p_intercepts: Optional[float]
    alpha: float
    # Diagnostic detail; the per-step OLS results, useful for the report.
    notes: list[str] = field(default_factory=list)
    # v0.9.0: Holm-Bonferroni corrected p-values for the two-step
    # poolability test. Two hypothesis tests are run (slopes +
    # intercepts); the Holm correction preserves the family-wise
    # error rate at `alpha` while gaining power over the
    # conservative Bonferroni correction. `None` until the
    # corresponding test is reached (e.g. p_intercepts_holm is
    # None if the slopes test already rejected). Both fields are
    # the corrected p-values; the original (uncorrected)
    # p_slopes and p_intercepts are unchanged.
    p_slopes_holm: Optional[float] = None
    p_intercepts_holm: Optional[float] = None


@dataclass
class CrossingResult:
    crossing_months: Optional[float]  # None if no crossing in horizon
    status: CrossingStatus
    governing_batch: Optional[str]
    notes: list[str] = field(default_factory=list)
    # v0.10.0: which spec limit governed the crossing for a
    # bidirectional (two-sided) analysis. ``"lower"`` or ``"upper"``
    # when the data's direction is BIDIRECTIONAL and a crossing was
    # found; ``None`` for the one-sided (DECREASING / INCREASING)
    # paths and for non-CROSSED statuses. Appended last so existing
    # positional constructions (``CrossingResult(months, status,
    # batch, notes)``) keep working unchanged.
    governing_side: Optional[str] = None


@dataclass
class DiagnosticsResult:
    linearity_ok: bool
    homoscedastic_ok: bool
    normal_resid_ok: bool
    influential_points: list[int]  # row indices in the data used for the fit
    notes: list[str] = field(default_factory=list)
    # Extra, optional diagnostics the report may surface. Optional in v0.1.
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class StabilityResult:
    """Top-level decision record returned by the engine."""

    attribute: str
    condition: str
    direction: Direction
    model: ModelKind
    poolability: PoolabilityResult
    fit: FitResult
    crossing: CrossingResult
    supported_shelf_life_months: Optional[int]  # rounded DOWN to whole months
    statistical_crossing_months: Optional[float]
    observed_data_months: float
    extrapolation_flag: bool
    diagnostics: DiagnosticsResult
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    # Human-readable deliverable term: "shelf life" (product) or
    # "retest period" (substance). Default = "shelf life".
    deliverable_term: str = "shelf life"
    # When True, deliverable is a retest period (drug substance). When False
    # (default), it's a shelf life (drug product). Engine sets this from
    # product_type.
    product_type: str = "product"
    # Pre-rendered plot filename (relative to build dir). Optional.
    plot_filename: str = "confidence_plot.png"
    # v0.3.1: per-attribute BQL handling summary. Carried on the result so
    # the JSON record and HTML report can surface the actual policy/counts.
    bql_summary: "BQLSummary" = field(default_factory=lambda: BQLSummary(
        policy="exclude", n_bql_rows=0, n_substituted=0, n_excluded=0,
    ))
    # v0.4.0: ICH Q1A significant-change gating of extrapolation. All
    # fields default to permissive values so v0.3.x callers (and tests
    # that build StabilityResult by hand) keep working unchanged when
    # the new gate is not exercised.
    significant_change_accelerated: Optional[bool] = None
    significant_change_intermediate: Optional[bool] = None
    extrapolation_allowed: bool = True
    extrapolation_rationale: str = ""
    significant_change_details: dict[str, Any] = field(default_factory=dict)
    # v0.5.0: advanced statistics. All defaults are None / empty / "fixed"
    # so v0.4.x callers and hand-built fixtures keep working unchanged
    # when the new opt-in features are not exercised.
    arrhenius_result: Optional["ArrheniusResult"] = None
    mkt_celsius: Optional[float] = None
    reduced_design_report: Optional["ReducedDesignReport"] = None
    # "fixed" (the ICH Q1E default — Q1E-style ANCOVA poolability) or
    # "random" (the opt-in mixed model; affects confidence bounds and
    # is NOT the Q1E default).
    model_effects: str = "fixed"
    # v0.5.1: mixed-model convergence / boundary status. Always a
    # dict; default {"converged": True, "boundary": False, "message": ""}
    # so v0.5.0 callers and hand-built fixtures keep working unchanged.
    # Populated by the regression layer (random-effects path) and
    # surfaced through warnings, the JSON record, and the HTML report.
    model_convergence: dict[str, Any] = field(default_factory=lambda: {
        "converged": True, "boundary": False, "message": "",
    })
    # v0.7.0: explicit lower / upper spec fields on the result so
    # callers can read the spec limits the engine used (data-derived
    # or metadata-overridden) without reaching into
    # `ValidatedData`. Always a float or None. The multi-attribute
    # metadata override (v0.2.1 CHANGELOG claim, finally honored in
    # v0.7.0) sets these to the metadata values when an override
    # is supplied; otherwise they are the data-derived spec limits.
    lower_spec: Optional[float] = None
    upper_spec: Optional[float] = None
    # v0.11.0: the active guidance profile's name (an immutable audit fact
    # for the run). Defaults to the Q1AE profile name so hand-built fixtures
    # and v0.10.x callers keep working unchanged. Set by the engine from
    # ``profile.name``; surfaced in the JSON record and HTML report.
    profile_name: str = "Q1A_R2+Q1E"
    # v0.7.0: optional sensitivity report. None when --sensitivity
    # is not requested; a `SensitivityReport` dataclass instance
    # otherwise. The report records, for each Cook's-distance
    # influential point flagged by the diagnostics layer, the
    # supported shelf life that results from removing that point
    # and re-running the analysis end-to-end.
    sensitivity_report: Optional["SensitivityReport"] = None
    # v0.8.0: Arrhenius-driven shelf-life prediction. None when
    # `--arrhenius-shelf-life` is not requested; an
    # `ArrheniusShelfLife` dataclass otherwise. Always additive.
    arrhenius_shelf_life: Optional["ArrheniusShelfLife"] = None


# ---------------------------------------------------------------------------
# v0.2.0 multi-attribute contracts (additive — do not modify existing shapes)
# ---------------------------------------------------------------------------


@dataclass
class AttributeMetadata:
    """Per-attribute metadata. Loaded from a separate CSV/XLSX table
    OR carried in repeated per-row data columns. Overrides anything
    the data layer infers.
    """
    attribute: str
    unit: Optional[str] = None
    direction: Optional["Direction"] = None  # forward ref — already imported
    lower_spec: Optional[float] = None
    upper_spec: Optional[float] = None
    spec_type: Optional[str] = None  # "release" | "shelf_life" | None
    transform: str = "none"  # "none" | "log" — v0.2 only honors "none"
    attribute_role: AttributeRole = AttributeRole.PRIMARY
    report_order: Optional[int] = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class AttributeResult:
    """The result of analyzing ONE attribute. Wraps the existing
    StabilityResult so v0.1 callers continue to work.
    """
    metadata: AttributeMetadata
    result: "StabilityResult"  # forward ref
    included_in_limiting_decision: bool
    exclusion_reason: Optional[str] = None


@dataclass
class MultiAttributeResult:
    """Top-level v0.2.0 result: one entry per analyzed attribute,
    plus the overall limiting decision.
    """
    condition: str
    product_type: str
    deliverable_term: str
    attributes: list[AttributeResult]
    limiting_attribute: Optional[str]
    supported_shelf_life_months: Optional[int]
    statistical_crossing_months: Optional[float]
    observed_data_months: float
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# v0.3.0 data-quality contracts (additive — do not modify existing shapes)
# ---------------------------------------------------------------------------


class IssueSeverity(str, Enum):
    """Severity of a :class:`DataQualityIssue`.

    - ``INFO``    : noteworthy but not actionable. Does not block analysis.
    - ``WARNING`` : likely a data problem the user should review. Does not
                    block analysis but is surfaced prominently in the report.
    - ``ERROR``   : a defect that would prevent the engine from producing a
                    meaningful :class:`StabilityResult`. Sets
                    ``DataQualityReport.can_analyze`` to ``False`` when any
                    ERROR-severity issue is present.
    """
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class DataQualityIssue:
    """A single data-quality finding. JSON-serializable.

    All fields default to ``None`` / empty so callers can construct a
    minimal issue with just ``code``, ``severity``, and ``message``.
    ``attribute`` / ``batch`` / ``row_index`` / ``column`` are populated
    when the issue is localisable to a specific slice of the input.
    ``details`` is an open dict for free-form metadata (counts, sample
    values, etc.) — anything not covered by the named fields.
    """
    code: str
    severity: IssueSeverity
    message: str
    attribute: Optional[str] = None
    batch: Optional[str] = None
    row_index: Optional[int] = None
    column: Optional[str] = None
    details: dict = field(default_factory=dict)


@dataclass
class DataQualityReport:
    """Aggregate result of an audit. JSON-serializable.

    ``can_analyze`` is True iff the audit did not raise any ERROR-severity
    issues. WARNING and INFO issues are recorded but do NOT block
    analysis — v0.3.0 reports issues, it does not gate the engine. The
    engine may still proceed even when ``can_analyze`` is False, and the
    caller is expected to surface the report to the user.
    """
    issues: list[DataQualityIssue]
    n_errors: int
    n_warnings: int
    n_info: int
    row_count: int
    column_count: int
    attributes: list[str]
    conditions: list[str]
    can_analyze: bool


# ---------------------------------------------------------------------------
# v0.3.0 BQL + transform-candidate contracts (additive)
# ---------------------------------------------------------------------------


@dataclass
class BQLSummary:
    """Per-attribute BQL handling summary. JSON-serializable.

    Recorded on :class:`ValidatedData` and on every :class:`StabilityResult`
    so the report can surface the actual policy and counts.
    """
    policy: str
    n_bql_rows: int
    n_substituted: int
    n_excluded: int
    value_column: str = "value"
    original_value_column: Optional[str] = None
    notes: list[str] = field(default_factory=list)


@dataclass
class TransformCandidate:
    """One candidate transform's fit metrics. JSON-serializable.

    v0.3.0 supports ``"none"``, ``"log"``, ``"sqrt"`` as candidates.
    The official v0.3.0 decision model is the raw-scale linear fit;
    this record is exploratory evidence only.
    """
    name: str  # "none" | "log" | "sqrt"
    valid: bool
    invalid_reason: Optional[str] = None
    aic: Optional[float] = None
    s_resid: Optional[float] = None
    normality_p: Optional[float] = None
    homoscedasticity_p: Optional[float] = None
    notes: list[str] = field(default_factory=list)


@dataclass
class TransformAssessment:
    """Aggregate transform-candidate evidence for one attribute."""
    official_model_transform: str = "none"
    candidates: list[TransformCandidate] = field(default_factory=list)
    recommendation: Optional[str] = None
    recommendation_is_official: bool = False


# ---------------------------------------------------------------------------
# v0.4.0 ICH Q1A significant-change contracts (additive)
# ---------------------------------------------------------------------------


@dataclass
class SignificantChange:
    """Result of evaluating the ICH Q1A(R2) §2.2.7 significant-change
    checklist for one condition.

    `occurred` is True when any criterion tripped.
    `first_change_month` is the earliest time (in months) any criterion
    tripped; None if no criterion tripped.
    `reasons` carries the per-criterion reason strings, for the report.
    `per_condition` keys are condition names (e.g. "40C/75RH",
    "30C/65RH") and values are the per-condition occurred flags.
    `details` is an open dict for per-criterion evidence (e.g.
    `{"assay": {"first_t": 3.0, "fired": True}}`).
    """
    occurred: bool
    first_change_month: Optional[float] = None
    reasons: list[str] = field(default_factory=list)
    per_condition: dict[str, bool] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# v0.5.0 advanced-statistics contracts (additive)
# ---------------------------------------------------------------------------


@dataclass
class ArrheniusResult:
    """Arrhenius fit `ln(k) = ln(A) - Ea / (R * T)`.

    `rate_by_temp_C` is the input mapping {temp_C: k (1/month)}; the
    Arrhenius fit requires >= 2 stress temperatures (>= 3 preferred
    for a defensible Ea; the `n_temps == 2` case emits a warning
    at the call site, not on this dataclass).
    `Ea_J_per_mol` and `A` are the fitted parameters; `ln_A` is
    kept for convenience (it is the fit's intercept in the
    `1/T` regression).
    `predicted_k_at_storage` is the rate extrapolated to
    `storage_temp_C` (the storage temperature the user is
    extrapolating TO, e.g. 25.0 for room-temperature).
    `r_squared` is the OLS r^2 on the `1/T` regression.
    """
    Ea_J_per_mol: float
    ln_A: float
    A: float
    r_squared: float
    predicted_k_at_storage: float
    storage_temp_C: float
    n_temps: int
    # Per-temperature input echo (helpful in reports and tests).
    rate_by_temp_C: dict[str, float] = field(default_factory=dict)
    # v0.9.0: per-batch rate echo. `per_batch_rate_by_temp` keys
    # are batch identifiers; values are {temp_C_str: k(1/month)}
    # for that batch at that temperature. Empty dict when the
    # per-batch rate diagnostic was not requested (--arrhenius-
    # per-batch). Used by the v0.9.0 outlier detection: any batch
    # whose rate is more than `outlier_z_threshold` robust z-scores
    # from the per-temperature median is flagged in
    # `outlier_batches`.
    per_batch_rate_by_temp: dict[str, dict[str, float]] = field(
        default_factory=dict
    )
    outlier_batches: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ReducedDesignReport:
    """Detection result for ICH Q1D reduced designs (bracketing
    and/or matrixing).

    `is_bracketed` is True when only extreme levels of a factor
    were tested (e.g. only the smallest and largest container sizes).
    `is_matrixed` is True when not every batch x time x condition
    cell is populated (sparse design).
    `missing_cells` lists the (batch, time, condition) tuples that
    are absent in the input frame; used by the report.
    `note` carries a human-readable summary.
    """
    is_bracketed: bool
    is_matrixed: bool
    missing_cells: list[tuple] = field(default_factory=list)
    note: str = ""


# ---------------------------------------------------------------------------
# v0.6.0 export + artifact contracts (additive)
# ---------------------------------------------------------------------------


@dataclass
class ReportArtifact:
    """A self-contained, portable bundle of a single analysis run.

    Produced by :func:`openpharmastability.reports.artifacts.make_report_artifact`.
    The bundle is a directory containing the HTML report (with the
    confidence-plot PNG inlined as a base64 data URL so the file is
    fully portable), the JSON decision record, the per-attribute plot
    PNGs (single: one plot; multi: one per attribute), and optionally
    a PDF rendering of the HTML.

    All paths are absolute. `html_sha256` / `json_sha256` /
    `plot_sha256` are the SHA-256 hex digests of the corresponding
    files at the moment the bundle was produced — useful for audit
    trails. `plot_inlined` is True when the plot was embedded as a
    data URL in the HTML (the default for portability). `pdf_path`
    is None when no PDF backend (weasyprint or pdfkit) is available.
    """
    out_dir: str
    html_path: str
    json_path: str
    plot_paths: list[str] = field(default_factory=list)
    pdf_path: Optional[str] = None
    html_sha256: str = ""
    json_sha256: str = ""
    plot_sha256: list[str] = field(default_factory=list)
    html_size_bytes: int = 0
    json_size_bytes: int = 0
    plot_size_bytes: list[int] = field(default_factory=list)
    pdf_size_bytes: Optional[int] = None
    plot_inlined: bool = True
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# v0.7.0 sensitivity + acceptance-criteria contracts (additive)
# ---------------------------------------------------------------------------


@dataclass
class SensitivityRow:
    """One row of the v0.7.0 sensitivity report.

    Records the supported shelf life that results from removing a
    single flagged influential point (a Cook's-distance outlier
    identified by the diagnostics layer) or an entire batch
    (v0.8.0 leave-one-batch-out mode) and re-running the
    analysis end-to-end. The diff columns are the absolute change
    versus the baseline (all-points) supported shelf life.

    `drop_key` is the row index for `mode == "row"`, or the batch
    identifier for `mode == "batch"`.
    """
    influential_row_index: int
    baseline_supported_shelf_life: int
    leave_one_out_supported_shelf_life: Optional[int]   # None when no crossing
    leave_one_out_statistical_crossing_months: Optional[float]
    diff_supported_shelf_life_months: int
    note: str = ""
    # v0.8.0: identify what was dropped. For row-level sensitivity
    # this is the same as `influential_row_index` (kept for
    # backward compat). For batch-level sensitivity this is the
    # batch identifier; `influential_row_index` is the FIRST row
    # index of that batch in the data (informational only).
    mode: str = "row"   # "row" | "batch"
    drop_key: str = ""  # row index as str (row mode) or batch name (batch mode)


@dataclass
class SensitivityReport:
    """Result of the v0.7.0 (row-level) and v0.8.0 (batch-level)
    sensitivity analysis.

    `rows` is one :class:`SensitivityRow` per drop target:
      - `mode == "row"`: per Cook's-distance influential point.
      - `mode == "batch"`: per batch (leave-one-batch-out).
    `summary` is a short human-readable string; `mode` records
    which variant produced the report. `baseline_supported_shelf_life`
    echoes the all-points number for convenience.
    """
    rows: list[SensitivityRow] = field(default_factory=list)
    summary: str = ""
    baseline_supported_shelf_life: Optional[int] = None
    mode: str = "row"   # "row" | "batch"
    notes: list[str] = field(default_factory=list)


@dataclass
class AcceptanceCriteriaRow:
    """One row of the v0.7.0 acceptance-criteria CSV.

    Emitted by the `--acceptance-csv PATH` CLI flag and the
    `to_acceptance_criteria` helper. One row per analyzed
    attribute (eligible attributes only; excluded attributes
    appear with `included_in_limiting_decision = False` and a
    non-null `exclusion_reason`).
    """
    attribute: str
    condition: str
    direction: str
    model: str
    poolability: str
    lower_spec: Optional[float] = None
    upper_spec: Optional[float] = None
    statistical_crossing_months: Optional[float] = None
    supported_shelf_life_months: Optional[int] = None
    observed_data_months: float = 0.0
    extrapolation_flag: bool = False
    included_in_limiting_decision: bool = True
    exclusion_reason: str = ""
    unit: Optional[str] = None
    governing_batch: Optional[str] = None


# ---------------------------------------------------------------------------
# v0.8.0 Arrhenius-shelf-life + sensitivity-mode contracts (additive)
# ---------------------------------------------------------------------------


@dataclass
class ArrheniusShelfLife:
    """Result of the v0.8.0 Arrhenius-driven shelf-life prediction.

    Built by :func:`openpharmastability.stats.arrhenius_shelf_life.predict_arrhenius_shelf_life`.
    The procedure:
      1. Group the input by `temp_c` and fit a log-linear OLS per
         temperature to get a per-temperature rate (k(T) per month).
      2. Fit `ln(k) = ln(A) − Ea / (R · T)` to the per-temperature
         rates (>= 2 temperatures required; < 2 -> skip with note).
      3. Predict `k(storage_temp_C)` and run the standard crossing
         logic against the spec to get a model-based statistical
         crossing and supported shelf life.

    `predicted_k_at_storage` is the Arrhenius-extrapolated rate at
    the storage temperature (1/month). `predicted_shelf_life_months`
    is the rounded-DOWN supported shelf life from the same model.
    `temperatures_used` and `rates_per_temp` echo the per-temp
    inputs (helpful in the report). `source_arrhenius` is the
    underlying :class:`ArrheniusResult` (for the JSON record /
    HTML report cross-link).
    """
    predicted_k_at_storage: float
    predicted_statistical_crossing_months: Optional[float]
    predicted_shelf_life_months: Optional[int]
    storage_temp_C: float
    temperatures_used: list[float] = field(default_factory=list)
    rates_per_temp: dict[str, float] = field(default_factory=dict)
    n_temps: int = 0
    source_arrhenius: Optional["ArrheniusResult"] = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public function signatures (documented here, implemented in owning modules)
# ---------------------------------------------------------------------------
#
# These are the seams Wave 1 sub-agents implement. They are listed here as a
# frozen reference; the actual definitions live in:
#
#   data/io.py
#     def load_csv(path: str) -> pd.DataFrame
#   data/schema.py
#     def validate_and_select(df, attribute: str, condition: str,
#                             replicate_policy: str = "individual") -> ValidatedData
#   data/conditions.py
#     def parse_condition(raw: str) -> str
#   data/bql.py
#     def apply_bql_policy(df, policy: str = "exclude", **opts) -> pd.DataFrame
#   data/replicates.py
#     def apply_replicate_policy(df, policy: str = "individual") -> pd.DataFrame
#
#   stats/regression.py
#     def fit_models(data: ValidatedData) -> dict[ModelKind, FitResult]
#   stats/poolability.py
#     def test_poolability(fits: dict[ModelKind, FitResult],
#                          data: ValidatedData) -> PoolabilityResult
#   stats/bounds.py
#     def confidence_bound(fit: FitResult, t: float, side: str,
#                          conf: float = CONFIDENCE) -> float
#     def find_crossing(fit: FitResult, data: ValidatedData,
#                       horizon: float = DEFAULT_HORIZON_MONTHS) -> CrossingResult
#   stats/diagnostics.py
#     def run_diagnostics(fit: FitResult, data: ValidatedData) -> DiagnosticsResult
#
#   models/selection.py
#     def select_model(pool: PoolabilityResult,
#                      fits: dict[ModelKind, FitResult]) -> tuple[ModelKind, FitResult]
#
#   shelf_life/engine.py
#     def analyze(path: str, condition: str, attribute: str = "assay",
#                 product_type: str = "product",
#                 horizon: float = DEFAULT_HORIZON_MONTHS) -> StabilityResult
#   shelf_life/extrapolation.py
#     def apply_extrapolation_caps(result: StabilityResult) -> StabilityResult
#
#   reports/html.py
#     def render_html(result: StabilityResult, plot_png_path: str,
#                     out_path: str) -> None
#   reports/record.py
#     def to_decision_record(result: StabilityResult) -> dict[str, Any]
#
#   plots/confidence_plot.py
#     def make_confidence_plot(result: StabilityResult,
#                              data: ValidatedData,
#                              out_path: str) -> str
# ---------------------------------------------------------------------------


__all__ = [
    "REQUIRED_COLUMNS",
    "POOLABILITY_ALPHA",
    "CONFIDENCE",
    "ONE_SIDED_T_QUANTILE",
    "TWO_SIDED_T_QUANTILE",
    "DEFAULT_HORIZON_MONTHS",
    "EXTRAPOLATION_MAX_FACTOR",
    "EXTRAPOLATION_MAX_MONTHS_BEYOND",
    "TOOL_VERSION",
    "DISCLAIMER",
    "Direction",
    "ModelKind",
    "Poolability",
    "CrossingStatus",
    "AttributeRole",
    "ValidatedData",
    "FitResult",
    "PoolabilityResult",
    "CrossingResult",
    "DiagnosticsResult",
    "StabilityResult",
    "AttributeMetadata",
    "AttributeResult",
    "MultiAttributeResult",
    # v0.3.0 data quality
    "IssueSeverity",
    "DataQualityIssue",
    "DataQualityReport",
    # v0.3.0 BQL + transforms
    "BQLSummary",
    "TransformCandidate",
    "TransformAssessment",
    # v0.4.0 ICH Q1A significant-change
    "SignificantChange",
    # v0.5.0 advanced statistics
    "ArrheniusResult",
    "ReducedDesignReport",
    # v0.6.0 export + artifacts
    "ReportArtifact",
    # v0.7.0 sensitivity + acceptance criteria
    "SensitivityRow",
    "SensitivityReport",
    "AcceptanceCriteriaRow",
    # v0.8.0 Arrhenius-shelf-life
    "ArrheniusShelfLife",
]
