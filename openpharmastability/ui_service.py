"""UI-facing analysis service for OpenPharmaStability v1.

This module is intentionally thin. It delegates all statistics, report
rendering, JSON generation, and artifact hashing to the existing Python API.
The local web UI and any future HTTP layer should consume this manifest
instead of reimplementing shelf-life logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from openpharmastability.api import analyze_and_artifact
from openpharmastability.contracts import (
    DISCLAIMER,
    MultiAttributeResult,
    ReportArtifact,
    StabilityResult,
    TOOL_VERSION,
)
from openpharmastability.regulatory.profile import resolve_profile
from openpharmastability.reports.multi_record import to_multi_decision_record
from openpharmastability.reports.record import to_decision_record


@dataclass
class UIAnalysisOptions:
    """Options accepted by the v1 local UI service."""

    condition: str
    attribute: str = "assay"
    attributes: Optional[list[str]] = None
    all_attributes: bool = False
    metadata_path: Optional[str] = None
    data_sheet: Optional[str] = None
    metadata_sheet: Optional[str] = None
    product_type: str = "product"
    horizon: float = 60.0
    replicate_policy: str = "individual"
    bql_policy: str = "exclude"
    guidance: str = "q1ae"
    source_epoch: Optional[int] = None
    assess_transforms: bool = False
    run_arrhenius: bool = False
    run_mkt: bool = False
    detect_reduced_design: bool = False
    random_effects: bool = False
    run_sensitivity: bool = False
    sensitivity_mode: str = "row"
    run_arrhenius_shelf_life: bool = False
    run_arrhenius_per_batch: bool = False
    generate_pdf: bool = False


@dataclass
class UIArtifactFile:
    """One file exposed to the local UI."""

    kind: str
    path: str
    name: str
    size_bytes: int
    sha256: str = ""
    url: Optional[str] = None


@dataclass
class UIAnalysisManifest:
    """Stable result shape consumed by the v1 UI."""

    status: str
    mode: str
    version: str
    guidance_profile: str
    disclaimer: str
    summary: dict[str, Any]
    warnings: list[str]
    artifacts: list[UIArtifactFile] = field(default_factory=list)
    record: dict[str, Any] = field(default_factory=dict)
    run_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "mode": self.mode,
            "version": self.version,
            "guidance_profile": self.guidance_profile,
            "disclaimer": self.disclaimer,
            "summary": self.summary,
            "warnings": self.warnings,
            "artifacts": [vars(item) for item in self.artifacts],
            "record": self.record,
            "run_dir": self.run_dir,
        }


def analyze_for_ui(
    input_path: str,
    output_dir: str,
    options: UIAnalysisOptions,
    *,
    url_prefix: str = "",
) -> UIAnalysisManifest:
    """Run an analysis and return a UI-friendly artifact manifest."""

    out_p = Path(output_dir)
    out_p.mkdir(parents=True, exist_ok=True)

    profile = resolve_profile(options.guidance)
    engine_kwargs: dict[str, Any] = {
        "product_type": options.product_type,
        "horizon": options.horizon,
        "replicate_policy": options.replicate_policy,
        "bql_policy": options.bql_policy,
        "profile": profile,
        "assess_transforms": options.assess_transforms,
        "run_arrhenius": options.run_arrhenius,
        "run_mkt": options.run_mkt,
        "detect_reduced_design": options.detect_reduced_design,
        "random_effects": options.random_effects,
        "run_sensitivity": options.run_sensitivity,
        "sensitivity_mode": options.sensitivity_mode,
        "run_arrhenius_shelf_life": options.run_arrhenius_shelf_life,
        "run_arrhenius_per_batch": options.run_arrhenius_per_batch,
    }
    if options.source_epoch is not None:
        engine_kwargs["source_epoch"] = options.source_epoch

    result, artifact = analyze_and_artifact(
        path=input_path,
        condition=options.condition,
        out_dir=str(out_p),
        attribute=options.attribute,
        attributes=options.attributes,
        all_attributes=options.all_attributes,
        metadata_path=options.metadata_path,
        data_sheet=options.data_sheet,
        metadata_sheet=options.metadata_sheet,
        generate_pdf=options.generate_pdf,
        **engine_kwargs,
    )
    record = (
        to_multi_decision_record(result)
        if isinstance(result, MultiAttributeResult)
        else to_decision_record(result)
    )
    return _build_manifest(result, artifact, record, str(out_p), url_prefix)


def _build_manifest(
    result: StabilityResult | MultiAttributeResult,
    artifact: ReportArtifact,
    record: dict[str, Any],
    run_dir: str,
    url_prefix: str,
) -> UIAnalysisManifest:
    mode = "multi" if isinstance(result, MultiAttributeResult) else "single"
    warnings = _dedupe(list(getattr(result, "warnings", []) or []))
    guidance_profile = str(record.get("guidance_profile") or "Q1A_R2+Q1E")
    summary: dict[str, Any] = {
        "condition": record.get("condition"),
        "product_type": record.get("product_type"),
        "deliverable_term": record.get("deliverable_term"),
        "supported_shelf_life_months": record.get("supported_shelf_life_months"),
        "statistical_crossing_months": record.get("statistical_crossing_months"),
        "observed_data_months": (
            record.get("observed_data_months")
            if record.get("observed_data_months") is not None
            else record.get("observed_long_term_months")
        ),
        "limiting_attribute": record.get("limiting_attribute"),
        "crossing_status": record.get("crossing_status"),
        "model": record.get("model"),
        "poolability": record.get("poolability"),
    }
    if mode == "multi":
        summary["attributes_analyzed"] = len(record.get("attributes", []) or [])
        summary["attribute_order"] = record.get("attribute_order", [])
    else:
        summary["attribute"] = record.get("attribute") or record.get("limiting_attribute")
        summary["direction"] = record.get("direction")

    return UIAnalysisManifest(
        status="ok",
        mode=mode,
        version=TOOL_VERSION,
        guidance_profile=guidance_profile,
        disclaimer=DISCLAIMER,
        summary=summary,
        warnings=warnings,
        artifacts=_artifact_files(artifact, url_prefix),
        record=record,
        run_dir=str(Path(run_dir).resolve()),
    )


def _artifact_files(
    artifact: ReportArtifact,
    url_prefix: str,
) -> list[UIArtifactFile]:
    files: list[UIArtifactFile] = [
        _file("html", artifact.html_path, artifact.html_size_bytes, artifact.html_sha256, url_prefix),
        _file("json", artifact.json_path, artifact.json_size_bytes, artifact.json_sha256, url_prefix),
    ]
    for index, path in enumerate(artifact.plot_paths):
        sha = artifact.plot_sha256[index] if index < len(artifact.plot_sha256) else ""
        size = artifact.plot_size_bytes[index] if index < len(artifact.plot_size_bytes) else 0
        files.append(_file("plot", path, size, sha, url_prefix))
    if artifact.pdf_path:
        files.append(
            _file("pdf", artifact.pdf_path, artifact.pdf_size_bytes or 0, "", url_prefix)
        )
    return files


def _file(
    kind: str,
    path: str,
    size: int,
    sha: str,
    url_prefix: str,
) -> UIArtifactFile:
    p = Path(path)
    return UIArtifactFile(
        kind=kind,
        path=str(p.resolve()),
        name=p.name,
        size_bytes=int(size or (p.stat().st_size if p.exists() else 0)),
        sha256=sha,
        url=f"{url_prefix.rstrip('/')}/{p.name}" if url_prefix else None,
    )


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item).strip()))


__all__ = [
    "UIAnalysisManifest",
    "UIAnalysisOptions",
    "UIArtifactFile",
    "analyze_for_ui",
]
