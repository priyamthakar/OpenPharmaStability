"""HTML -> PDF export for OpenPharmaStability v0.6.0.

Renders a pre-built HTML report (typically produced by
:mod:`openpharmastability.reports.html`) to a PDF file.

The CLI / artifact bundle calls :func:`render_pdf` after the HTML
report has been written. The user picks (or implicitly enables) one of
two optional backends:

* ``weasyprint``  (preferred) -- pure-Python, modern CSS support.
                    Install via ``pip install openpharmastability[pdf]``.
* ``pdfkit``      (fallback)  -- thin wrapper over the ``wkhtmltopdf``
                    command-line binary, which must be installed
                    separately. Install via
                    ``pip install openpharmastability[pdf-fallback]``.

The fallback chain in ``backend='auto'`` mode is weasyprint -> pdfkit.
If neither backend is available, :func:`render_pdf` raises
:class:`RuntimeError` with install instructions; it never silently
writes a half-broken PDF.

This module depends only on the standard library and the two optional
backends. It does not import the engine, CLI, or other report
modules -- its only inputs are a path to an existing HTML file and a
path for the PDF to be written.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PDF_MAGIC: bytes = b"%PDF"

_INSTALL_HINT: str = (
    "OpenPharmaStability could not render a PDF because no backend is installed.\n"
    "Install one of the optional extras:\n"
    "  pip install openpharmastability[pdf]          # weasyprint (recommended)\n"
    "  pip install openpharmastability[pdf-fallback]  # pdfkit (needs wkhtmltopdf)\n"
)


# ---------------------------------------------------------------------------
# Backend import probes (patchable from tests)
# ---------------------------------------------------------------------------


def _try_weasyprint():
    """Return the ``weasyprint`` module if importable, else ``None``.

    Tests patch this function to simulate the "weasyprint not available"
    state without touching the real import system.
    """
    try:
        import weasyprint  # type: ignore
        return weasyprint
    except ImportError:
        return None
    except Exception:
        # weasyprint can raise non-ImportError at import time (for
        # example missing system GTK libraries on Windows). Treat that
        # as "not available" so the chain can fall through to pdfkit.
        return None


def _try_pdfkit():
    """Return the ``pdfkit`` module if importable, else ``None``."""
    try:
        import pdfkit  # type: ignore
        return pdfkit
    except ImportError:
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def has_pdf_backend() -> Optional[str]:
    """Return the name of the first available PDF backend, or ``None``.

    Order: ``'weasyprint'`` then ``'pdfkit'``. Use this before calling
    :func:`render_pdf` to surface a friendly error or skip in callers
    that prefer not to depend on either backend (for example the CLI
    before it has decided whether to attempt a PDF).
    """
    if _try_weasyprint() is not None:
        return "weasyprint"
    if _try_pdfkit() is not None:
        return "pdfkit"
    return None


def _validate_pdf(out_path: str) -> None:
    """Raise :class:`RuntimeError` if ``out_path`` is missing or does not
    look like a PDF (no ``%PDF`` magic header).
    """
    p = Path(out_path)
    if not p.exists():
        raise RuntimeError(
            f"PDF backend reported success but file is missing: {out_path}"
        )
    try:
        head = p.read_bytes()[:4]
    except OSError as exc:
        raise RuntimeError(
            f"PDF backend reported success but file is unreadable: {out_path} ({exc!r})"
        ) from exc
    if head != PDF_MAGIC:
        raise RuntimeError(
            f"PDF render produced a file without the PDF magic header: {out_path}"
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def render_pdf(
    html_path: str,
    out_path: str,
    backend: str = "auto",
) -> str:
    """Render an HTML file to PDF. Returns the path to the written PDF.

    Parameters
    ----------
    html_path:
        Path to the source HTML file. Must exist and be readable.
    out_path:
        Path to write the PDF to. Parent directory is created if needed.
    backend:
        One of ``'auto'`` (default -- try weasyprint, then pdfkit),
        ``'weasyprint'``, or ``'pdfkit'``. An explicit value forces that
        backend only and still raises on failure.

    Returns
    -------
    str
        The ``out_path`` argument, on success.

    Raises
    ------
    RuntimeError
        If no backend is available, the explicit backend fails, or the
        output file is missing / does not look like a PDF.
    ValueError
        If ``backend`` is not one of the recognised values.
    FileNotFoundError
        If ``html_path`` does not exist.
    """
    if backend not in ("auto", "weasyprint", "pdfkit"):
        raise ValueError(
            f"Unknown PDF backend: {backend!r}. "
            "Expected 'auto', 'weasyprint', or 'pdfkit'."
        )

    html_src = Path(html_path)
    if not html_src.exists():
        raise FileNotFoundError(f"HTML source not found: {html_path}")
    html = html_src.read_text(encoding="utf-8")

    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    last_error: Optional[BaseException] = None

    # 1) weasyprint -----------------------------------------------------
    if backend in ("auto", "weasyprint"):
        wp = _try_weasyprint()
        if wp is not None:
            try:
                wp.HTML(string=html).write_pdf(str(out_p))
                _validate_pdf(str(out_p))
                return str(out_p)
            except Exception as exc:  # noqa: BLE001 -- we chain through
                if backend == "weasyprint":
                    raise RuntimeError(
                        f"weasyprint failed to render PDF: {exc!r}"
                    ) from exc
                # In 'auto' mode, fall through to pdfkit.
                last_error = exc

    # 2) pdfkit fallback ------------------------------------------------
    if backend in ("auto", "pdfkit"):
        pk = _try_pdfkit()
        if pk is not None:
            try:
                pk.from_string(html, str(out_p))
                _validate_pdf(str(out_p))
                return str(out_p)
            except Exception as exc:  # noqa: BLE001 -- we chain through
                if backend == "pdfkit":
                    raise RuntimeError(
                        f"pdfkit failed to render PDF: {exc!r}"
                    ) from exc
                last_error = exc

    # 3) nothing worked -------------------------------------------------
    if last_error is not None:
        raise RuntimeError(
            f"All PDF backends failed. Last error: {last_error!r}\n"
            + _INSTALL_HINT
        )
    raise RuntimeError(_INSTALL_HINT)


__all__ = ["render_pdf", "has_pdf_backend"]
