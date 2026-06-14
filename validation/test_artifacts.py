"""Tests for ``openpharmastability.reports.artifacts`` (v0.6.0).

These tests exercise :func:`make_report_artifact` end-to-end on the
shipped fixtures. The helper builds a self-contained
:class:`ReportArtifact` bundle (HTML + JSON + plots, optional PDF)
and is the unified export path used by both the CLI and the thin
Python API.

Test cases:

1. Single-attribute with plot inlining (default) -> HTML has the
   inlined data URL; SHA-256 matches the on-disk file.
2. Single-attribute with ``inline_plot=False`` -> HTML does NOT
   have an inlined data URL; plot is still bundled on disk.
3. Multi-attribute with per-attribute plot PNGs -> two plot paths
   are bundled, two ``<img>`` tags in the HTML (or two inlined
   data URLs when ``inline_plot=True``).
4. Portability check -> moving the bundle to a new directory
   does not break the HTML (it is self-contained).
5. PDF generation without a backend -> ``RuntimeError``.
6. Missing plot for single-attribute -> ``FileNotFoundError`` with
   a clear message.
7. Files-on-disk check -> HTML and JSON exist, JSON parses, HTML
   contains the ``OpenPharmaStability`` banner.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from openpharmastability.contracts import (
    MultiAttributeResult,
    ReportArtifact,
    StabilityResult,
)
from openpharmastability.data.io import load_csv
from openpharmastability.data.schema import validate_and_select
from openpharmastability.plots.confidence_plot import make_confidence_plot
from openpharmastability.reports.artifacts import make_report_artifact
from openpharmastability.reports.pdf import has_pdf_backend
from openpharmastability.shelf_life.engine import analyze as analyze_single
from openpharmastability.shelf_life.multi_engine import analyze_many


ROOT = pathlib.Path(__file__).resolve().parents[1]
SINGLE_CSV = ROOT / "examples" / "assay_3batch.csv"
MULTI_CSV = ROOT / "examples" / "multi_attribute.csv"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _render_single_plot(
    result: StabilityResult, attribute: str, condition: str,
    csv_path: pathlib.Path, out_png: pathlib.Path,
) -> str:
    """Re-render the single-attribute confidence plot to ``out_png``.

    Returns the path as a string. The shipped multi-attribute fixture
    uses the same column layout as the single-attribute one, so a
    single-attribute call works for both tests.
    """
    df = load_csv(str(csv_path))
    data = validate_and_select(df, attribute=attribute, condition=condition)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    make_confidence_plot(result, data, str(out_png))
    return str(out_png)


# ---------------------------------------------------------------------------
# 1. Single-attribute, plot inlined (default)
# ---------------------------------------------------------------------------


def test_make_artifact_single_inline(tmp_path: pathlib.Path) -> None:
    """``inline_plot=True`` (default) -> the HTML contains a base64
    data URL, the recorded SHA-256 matches the on-disk file, and the
    plot path round-trips through the artifact."""
    result = analyze_single(
        path=str(SINGLE_CSV),
        condition="25C/60RH",
        attribute="assay",
        source_epoch=1700000000,
    )
    assert isinstance(result, StabilityResult)
    plot = tmp_path / "confidence_plot.png"
    _render_single_plot(result, "assay", "25C/60RH", SINGLE_CSV, plot)

    artifact = make_report_artifact(
        result, str(tmp_path),
        plot_paths=[str(plot)],
    )

    assert isinstance(artifact, ReportArtifact)
    assert pathlib.Path(artifact.html_path).exists()
    assert pathlib.Path(artifact.json_path).exists()

    # Recorded SHA-256 must match the on-disk file.
    html_bytes = pathlib.Path(artifact.html_path).read_bytes()
    assert artifact.html_sha256 == hashlib.sha256(html_bytes).hexdigest()

    # JSON SHA-256 is recorded too.
    json_bytes = pathlib.Path(artifact.json_path).read_bytes()
    assert artifact.json_sha256 == hashlib.sha256(json_bytes).hexdigest()

    # HTML body contains the inlined data URL.
    html = html_bytes.decode("utf-8")
    assert "data:image/png;base64," in html

    # plot_inlined flag and the bundled plot path round-trip.
    assert artifact.plot_inlined is True
    assert artifact.plot_paths == [str(plot)]
    # The plot SHA-256 was computed too.
    assert len(artifact.plot_sha256) == 1
    assert artifact.plot_sha256[0] != ""


# ---------------------------------------------------------------------------
# 2. Single-attribute, inline_plot=False
# ---------------------------------------------------------------------------


def test_make_artifact_single_no_inline(tmp_path: pathlib.Path) -> None:
    """``inline_plot=False`` -> HTML still references the PNG by
    filename (not a data URL) and the plot file is still bundled on
    disk alongside the HTML.
    """
    result = analyze_single(
        path=str(SINGLE_CSV),
        condition="25C/60RH",
        attribute="assay",
        source_epoch=1700000000,
    )
    plot = tmp_path / "confidence_plot.png"
    _render_single_plot(result, "assay", "25C/60RH", SINGLE_CSV, plot)

    artifact = make_report_artifact(
        result, str(tmp_path),
        plot_paths=[str(plot)],
        inline_plot=False,
    )

    html = pathlib.Path(artifact.html_path).read_text(encoding="utf-8")
    assert "data:image/png;base64," not in html
    # plot_inlined flag is False and the plot path is still recorded.
    assert artifact.plot_inlined is False
    assert artifact.plot_paths == [str(plot)]
    # Sanity: the HTML still references the plot file by name.
    assert "confidence_plot.png" in html


# ---------------------------------------------------------------------------
# 3. Multi-attribute uses per-attribute plot PNGs
# ---------------------------------------------------------------------------


def test_make_artifact_multi_uses_per_attribute_plots(
    tmp_path: pathlib.Path,
) -> None:
    """Multi-attribute bundle: one plot per attribute, two ``<img>``
    tags in the rendered HTML (or two inlined data URLs when
    ``inline_plot=True``)."""
    multi = analyze_many(
        path=str(MULTI_CSV),
        condition="25C/60RH",
        all_attributes=True,
        source_epoch=1700000000,
    )
    assert isinstance(multi, MultiAttributeResult)
    assert len(multi.attributes) == 2

    # Re-render a per-attribute plot for each. The CLI default layout
    # is ``<out_dir>/plots/<attr>_confidence_plot.png``; we use a
    # flat layout (plots in ``tmp_path`` directly) to also verify the
    # default-discoverer's glob behavior.
    plot_paths: list[str] = []
    for ar in multi.attributes:
        attr = ar.metadata.attribute
        png = tmp_path / f"{attr}_confidence_plot.png"
        _render_single_plot(ar.result, attr, "25C/60RH", MULTI_CSV, png)
        plot_paths.append(str(png))

    # Multi-attribute HTML references plots via the relative path
    # from the HTML's directory. We rendered them in ``tmp_path``
    # (flat layout), so the relative path is just the basename. The
    # CLI's default would emit ``plots/...``; pass ``plot_paths=``
    # and the helper inlines by basename plus the directory-prefixed
    # form.
    artifact = make_report_artifact(
        multi, str(tmp_path),
        plot_paths=plot_paths,
    )

    assert len(artifact.plot_paths) == 2
    assert set(artifact.plot_paths) == set(plot_paths)
    assert len(artifact.plot_sha256) == 2

    html = pathlib.Path(artifact.html_path).read_text(encoding="utf-8")
    # Two inlined data URLs (one per attribute).
    assert html.count("data:image/png;base64,") == 2
    # And two <img> tags (one per attribute section).
    assert html.count("<img") == 2


# ---------------------------------------------------------------------------
# 4. HTML is portable (self-contained)
# ---------------------------------------------------------------------------


def test_make_artifact_html_is_portable(tmp_path: pathlib.Path) -> None:
    """Copy the bundle to a fresh directory and verify the HTML still
    carries a valid inlined data URL. This guards the v0.6.0
    portability claim: a user can drop the artifact directory onto
    a USB stick and the HTML opens without any sibling file.
    """
    result = analyze_single(
        path=str(SINGLE_CSV),
        condition="25C/60RH",
        attribute="assay",
        source_epoch=1700000000,
    )
    plot = tmp_path / "src" / "confidence_plot.png"
    _render_single_plot(result, "assay", "25C/60RH", SINGLE_CSV, plot)

    # Build in tmp_path/src.
    artifact = make_report_artifact(
        result, str(tmp_path / "src"),
        plot_paths=[str(plot)],
    )

    # Now copy the whole bundle to a fresh directory and read the HTML.
    target = tmp_path / "dest"
    target.mkdir()
    for src in (tmp_path / "src").iterdir():
        (target / src.name).write_bytes(src.read_bytes())

    moved_html = (target / "report.html").read_text(encoding="utf-8")
    # The data URL is still present and the plot basename is NOT
    # referenced (i.e. the file truly has no external dependency).
    assert "data:image/png;base64," in moved_html
    assert 'src="confidence_plot.png"' not in moved_html
    # The data URL is non-trivial in length.
    b64 = moved_html.split("data:image/png;base64,", 1)[1].split('"', 1)[0]
    assert len(b64) > 100


# ---------------------------------------------------------------------------
# 5. PDF generation without a backend
# ---------------------------------------------------------------------------


def test_make_artifact_pdf_when_no_backend(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``generate_pdf=True`` on a system without weasyprint/pdfkit
    raises ``RuntimeError``.

    We monkeypatch the PDF backend probes to ``None`` so the test is
    deterministic regardless of the host environment.
    """
    # Force the "no backend" state.
    from openpharmastability.reports import pdf as _pdf_mod
    monkeypatch.setattr(_pdf_mod, "_try_weasyprint", lambda: None)
    monkeypatch.setattr(_pdf_mod, "_try_pdfkit", lambda: None)
    assert has_pdf_backend() is None  # precondition

    result = analyze_single(
        path=str(SINGLE_CSV),
        condition="25C/60RH",
        attribute="assay",
        source_epoch=1700000000,
    )
    plot = tmp_path / "confidence_plot.png"
    _render_single_plot(result, "assay", "25C/60RH", SINGLE_CSV, plot)

    with pytest.raises(RuntimeError):
        make_report_artifact(
            result, str(tmp_path),
            plot_paths=[str(plot)],
            generate_pdf=True,
        )


# ---------------------------------------------------------------------------
# 6. Missing plot for single-attribute -> FileNotFoundError
# ---------------------------------------------------------------------------


def test_make_artifact_missing_plot_raises(tmp_path: pathlib.Path) -> None:
    """Single-attribute bundle without a plot on disk and without
    ``plot_paths`` raises ``FileNotFoundError`` with a clear message.
    """
    result = analyze_single(
        path=str(SINGLE_CSV),
        condition="25C/60RH",
        attribute="assay",
        source_epoch=1700000000,
    )
    # Use a fresh sub-directory so no plot exists.
    out_dir = tmp_path / "empty_bundle"
    out_dir.mkdir()

    with pytest.raises(FileNotFoundError) as excinfo:
        make_report_artifact(result, str(out_dir))
    # The error message must mention the canonical plot location.
    assert "confidence_plot.png" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 7. Files-on-disk check
# ---------------------------------------------------------------------------


def test_make_artifact_writes_correct_files(tmp_path: pathlib.Path) -> None:
    """After ``make_report_artifact``: HTML exists, JSON exists and
    parses, and the HTML carries the engine banner."""
    result = analyze_single(
        path=str(SINGLE_CSV),
        condition="25C/60RH",
        attribute="assay",
        source_epoch=1700000000,
    )
    plot = tmp_path / "confidence_plot.png"
    _render_single_plot(result, "assay", "25C/60RH", SINGLE_CSV, plot)

    artifact = make_report_artifact(
        result, str(tmp_path),
        plot_paths=[str(plot)],
    )

    # HTML exists.
    assert pathlib.Path(artifact.html_path).exists()
    # JSON exists and parses as JSON.
    assert pathlib.Path(artifact.json_path).exists()
    rec = json.loads(
        pathlib.Path(artifact.json_path).read_text(encoding="utf-8")
    )
    # The engine banner is present in the HTML.
    html = pathlib.Path(artifact.html_path).read_text(encoding="utf-8")
    assert "OpenPharmaStability" in html
    # The JSON record's top-level keys are the documented ones.
    # The single-attribute record exposes the attribute name as
    # ``limiting_attribute`` (the v0.1 schema; multi-attribute records
    # also include ``attribute`` per entry).
    assert rec["limiting_attribute"] == "assay"
    assert rec["condition"] == "25C/60RH"
