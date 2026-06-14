"""Self-contained report artifact bundles for OpenPharmaStability v0.6.0.

A :class:`openpharmastability.contracts.ReportArtifact` is a portable
directory containing:

* the HTML report with the confidence-plot PNG inlined as a base64
  data URL (so the HTML is fully self-contained; no relative-path
  dependency on the plot file);
* the JSON decision record;
* the per-attribute plot PNGs (one for single, one per attribute
  for multi);
* optionally, a PDF rendering of the HTML (when a PDF backend is
  available and ``generate_pdf=True``).

SHA-256 digests and byte sizes are recorded on the returned
:class:`ReportArtifact` for audit-trail use.

This module is the v0.6.0 export layer. The CLI
(:mod:`openpharmastability.cli`) and the thin Python API
(:mod:`openpharmastability.api`) both delegate to
:func:`make_report_artifact` so the two paths produce byte-identical
bundles.
"""
from __future__ import annotations

import base64
import hashlib
import json as _json
import os
from pathlib import Path
from typing import Optional, Union

from openpharmastability.contracts import (
    MultiAttributeResult,
    ReportArtifact,
    StabilityResult,
)


_Single = Union[StabilityResult, MultiAttributeResult]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: str) -> tuple[str, int]:
    """Return ``(sha256_hex, size_bytes)`` for the file at ``path``.

    Returns ``("", 0)`` for a missing path so the helper never raises;
    callers that need a strict "must exist" check should pre-validate.
    """
    p = Path(path)
    if not p.exists() or not p.is_file():
        return "", 0
    data = p.read_bytes()
    return _sha256_bytes(data), len(data)


def _inline_plot_in_html(html: str, plot_path: str) -> str:
    """Replace ``<img src="...">`` references for ``plot_path`` with a
    base64 data URL.

    The standard HTML report has an ``<img src="<plot_filename>">`` tag
    where ``<plot_filename>`` is either the bare basename (single-attr
    default) or a sub-directory-relative path (multi-attr default,
    ``plots/<attribute>_confidence_plot.png``). This helper replaces
    BOTH the bare basename and the directory-prefixed form so the
    HTML is fully self-contained (no relative-path dependency on the
    plot file). Idempotent: if a tag is already a data URL, it is
    left alone.

    If no matching reference is found, a hidden data-URL ``<img>`` is
    injected just before ``</body>`` as a fallback.
    """
    if not plot_path or not Path(plot_path).exists():
        return html
    plot_bytes = Path(plot_path).read_bytes()
    b64 = base64.b64encode(plot_bytes).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"
    plot_basename = os.path.basename(plot_path)

    # Build the list of "src=..." forms we want to rewrite. The
    # single-attr template uses the bare basename; the multi-attr
    # template may use ``plots/<basename>`` (the CLI's default
    # --plots-dir is ``<out_dir>/plots``). We support both quoted
    # styles.
    candidates: list[str] = []
    seen: set[str] = set()
    for form in (
        f'src="{plot_basename}"',
        f"src='{plot_basename}'",
        # Common multi-attr sub-directory prefixes.
        f'src="plots/{plot_basename}"',
        f"src='plots/{plot_basename}'",
    ):
        if form in html and form not in seen:
            candidates.append(form)
            seen.add(form)

    if candidates:
        replacement = f'src="{data_url}"'
        for form in candidates:
            html = html.replace(form, replacement)
    else:
        # Fallback: inject a hidden data-URL <img> just before </body>.
        if "</body>" in html:
            html = html.replace(
                "</body>",
                f'<img alt="plot (data URL)" '
                f'style="display:none" '
                f'src="{data_url}">'
                f"</body>",
            )
    return html


def _resolve_plot_paths_for_result(
    result: _Single,
    out_dir: str,
    provided: Optional[list[str]],
) -> list[str]:
    """Decide the per-attribute plot PNG paths to bundle.

    If ``provided`` is supplied, use it (after validating that each
    file exists). Otherwise, default to:

    * single: ``<out_dir>/confidence_plot.png`` (only if that file
      already exists; the caller is responsible for having written
      it).
    * multi: every ``<out_dir>/*_confidence_plot.png`` that already
      exists. If none exist, return ``[]``.
    """
    if provided is not None:
        missing = [p for p in provided if not Path(p).exists()]
        if missing:
            raise FileNotFoundError(
                f"plot paths do not exist: {missing!r}"
            )
        return [str(p) for p in provided]

    out_p = Path(out_dir)
    if isinstance(result, StabilityResult):
        candidate = out_p / "confidence_plot.png"
        return [str(candidate)] if candidate.exists() else []

    # Multi: discover the <attribute>_confidence_plot.png files in
    # out_dir that were written by the CLI.
    if not out_p.exists():
        return []
    found = sorted(str(p) for p in out_p.glob("*_confidence_plot.png"))
    return found


def _disambiguate_html_filename(is_multi: bool) -> tuple[str, str]:
    """Return ``(html_basename, json_basename)`` for the bundle.

    Single- and multi-attribute bundles share filenames
    (``report.html`` / ``report.json``); the unified naming makes the
    CLI's per-mode dispatch trivial. The basenames are explicit and
    stable for downstream tooling.
    """
    return "report.html", "report.json"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def make_report_artifact(
    result: _Single,
    out_dir: str,
    *,
    plot_paths: Optional[list[str]] = None,
    inline_plot: bool = True,
    generate_pdf: bool = False,
) -> ReportArtifact:
    """Build a self-contained :class:`ReportArtifact` in ``out_dir``.

    Steps:

    1. Create ``out_dir`` if missing.
    2. Resolve the per-attribute plot PNG paths (validate existence
       when ``plot_paths`` is supplied; otherwise auto-discover).
    3. Render the HTML (single: via :func:`reports.html.render_html`
       and the in-tree plot at ``<out_dir>/confidence_plot.png``;
       multi: via :func:`reports.multi_html.render_multi_html` using
       the per-attribute plots in ``out_dir``).
    4. Write the JSON decision record.
    5. Optionally inline the primary plot as a base64 data URL in
       the HTML for portability.
    6. Optionally generate a PDF via
       :func:`openpharmastability.reports.pdf.render_pdf`.
    7. Compute SHA-256 digests and byte sizes; return the populated
       :class:`ReportArtifact`.

    Parameters
    ----------
    result:
        The :class:`StabilityResult` (single-attribute) or
        :class:`MultiAttributeResult` to bundle.
    out_dir:
        Destination directory. Created if missing.
    plot_paths:
        Optional explicit list of plot PNG paths. When supplied, the
        helper validates that every entry exists (raising
        :class:`FileNotFoundError` if not). When ``None``, the helper
        auto-discovers the canonical filenames under ``out_dir``.
    inline_plot:
        When True (default), the primary plot is inlined as a base64
        data URL in the HTML so the file is fully portable.
    generate_pdf:
        When True, also produce ``<out_dir>/report.pdf`` using
        :func:`openpharmastability.reports.pdf.render_pdf`. Raises
        :class:`RuntimeError` if no PDF backend is available.

    Returns
    -------
    ReportArtifact
        A populated :class:`ReportArtifact` with absolute paths,
        SHA-256 digests, byte sizes, and any user-facing notes.

    Raises
    ------
    FileNotFoundError
        If a single-attribute run is missing ``<out_dir>/confidence_plot.png``
        and no ``plot_paths`` was supplied.
    RuntimeError
        If ``generate_pdf=True`` and no PDF backend is installed.
    """
    out_p = Path(out_dir)
    out_p.mkdir(parents=True, exist_ok=True)

    is_multi = isinstance(result, MultiAttributeResult)
    html_basename, json_basename = _disambiguate_html_filename(is_multi)
    html_path = str(out_p / html_basename)
    json_path = str(out_p / json_basename)

    # 1) Resolve plot paths (validate existence for explicit lists).
    resolved_plots = _resolve_plot_paths_for_result(
        result, out_dir, plot_paths,
    )

    # 2) Render the HTML. We do this BEFORE writing the JSON so an
    #    error during HTML rendering surfaces immediately and the
    #    bundle stays consistent (the JSON is added only on success).
    from openpharmastability.reports.html import render_html
    from openpharmastability.reports.multi_html import render_multi_html

    if is_multi:
        # Multi-attribute: the per-attribute plot PNGs are expected
        # to be in ``out_dir`` (CLI default layout: ``<out_dir>/plots``).
        # The ``render_multi_html`` helper resolves relative paths
        # from the HTML's directory, so we point it at ``out_dir``;
        # if the CLI used a sub-directory, the caller is expected to
        # have written the per-attribute plots there or to pass
        # ``plot_paths=`` (which overrides discovery).
        render_multi_html(
            result,
            plot_dir=out_dir,
            out_path=html_path,
        )
    else:
        # Single-attribute: the existing renderer requires an
        # existing PNG at ``plot_png_path``. We delegate that
        # responsibility to the caller (CLI: writes it; tests: pass
        # ``plot_paths=``). If neither is true, raise — the helper
        # does not auto-render the plot from the CSV because the
        # engine's :class:`StabilityResult` does not carry the
        # original source path or the validated data.
        primary_plot = out_p / "confidence_plot.png"
        if not primary_plot.exists() and resolved_plots:
            # Copy from the explicit plot_paths entry into the
            # canonical location so ``render_html`` finds it.
            primary_plot.write_bytes(Path(resolved_plots[0]).read_bytes())
        if not primary_plot.exists():
            raise FileNotFoundError(
                f"no plot found at {primary_plot!s}; pass plot_paths= or "
                f"write the plot to {out_dir!s} before calling "
                f"make_report_artifact"
            )
        render_html(
            result,
            plot_png_path=str(primary_plot),
            out_path=html_path,
        )

    # 3) JSON decision record.
    from openpharmastability.reports.record import to_decision_record
    from openpharmastability.reports.multi_record import to_multi_decision_record
    rec = (
        to_multi_decision_record(result) if is_multi
        else to_decision_record(result)
    )
    Path(json_path).write_text(
        _json.dumps(rec, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # 4) Optionally inline the plot(s) into the HTML for portability.
    #    The HTML was rendered with a relative-path ``<img src="...">``;
    #    we rewrite it to a data URL. For multi-attribute bundles we
    #    inline EVERY plot, since each attribute has its own <img> tag.
    notes: list[str] = []
    if inline_plot and resolved_plots:
        html_text = Path(html_path).read_text(encoding="utf-8")
        inlined: list[str] = []
        for plot in resolved_plots:
            html_text = _inline_plot_in_html(html_text, plot)
            inlined.append(os.path.basename(plot))
        Path(html_path).write_text(html_text, encoding="utf-8")
        notes.append(
            f"plot(s) inlined: {', '.join(inlined)}"
        )

    # 5) Optional PDF generation. Strict-er behavior per the spec:
    #    raise ``RuntimeError`` when no backend is available so the
    #    caller learns the bundle is missing a PDF instead of
    #    silently writing a partial artifact.
    pdf_path: Optional[str] = None
    pdf_size: Optional[int] = None
    if generate_pdf:
        from openpharmastability.reports.pdf import render_pdf
        pdf_out = str(out_p / "report.pdf")
        render_pdf(html_path, pdf_out)
        pdf_path = pdf_out
        pdf_size = Path(pdf_out).stat().st_size
        notes.append("PDF generated")

    # 6) Compute digests and sizes for the audit trail.
    html_sha, html_size = _sha256_file(html_path)
    json_sha, json_size = _sha256_file(json_path)
    plot_shas: list[str] = []
    plot_sizes: list[int] = []
    for p in resolved_plots:
        s, n = _sha256_file(p)
        plot_shas.append(s)
        plot_sizes.append(n)

    return ReportArtifact(
        out_dir=str(out_p.resolve()),
        html_path=html_path,
        json_path=json_path,
        plot_paths=list(resolved_plots),
        pdf_path=pdf_path,
        html_sha256=html_sha,
        json_sha256=json_sha,
        plot_sha256=plot_shas,
        html_size_bytes=html_size,
        json_size_bytes=json_size,
        plot_size_bytes=plot_sizes,
        pdf_size_bytes=pdf_size,
        plot_inlined=bool(inline_plot and resolved_plots),
        notes=notes,
    )


__all__ = ["make_report_artifact"]
