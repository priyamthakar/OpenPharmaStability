"""Tests for the v0.6.0 PDF export module."""
from __future__ import annotations

from pathlib import Path

import pytest

from openpharmastability.reports.pdf import has_pdf_backend, render_pdf


# A small, well-formed HTML document used by the render tests.
_HTML = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<title>t</title></head><body><h1>hello</h1>"
    "<p>test pdf render</p></body></html>"
)


def _write_html(tmp_path: Path) -> str:
    p = tmp_path / "in.html"
    p.write_text(_HTML, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# 1) has_pdf_backend returns one of the known names (or None)
# ---------------------------------------------------------------------------


def test_has_pdf_backend_returns_known_string_or_none():
    name = has_pdf_backend()
    assert name in {"weasyprint", "pdfkit", None}


# ---------------------------------------------------------------------------
# 2) render with weasyprint when available
# ---------------------------------------------------------------------------


def test_render_pdf_with_weasyprint_when_available(tmp_path):
    pytest.importorskip("weasyprint")
    html_path = _write_html(tmp_path)
    out_path = str(tmp_path / "out.pdf")
    result = render_pdf(html_path, out_path)
    assert result == out_path
    p = Path(out_path)
    assert p.exists()
    assert p.read_bytes()[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# 3) render with pdfkit when available (forced via the backend kwarg)
# ---------------------------------------------------------------------------


def test_render_pdf_with_pdfkit_when_available(tmp_path):
    pytest.importorskip("pdfkit")
    html_path = _write_html(tmp_path)
    out_path = str(tmp_path / "out.pdf")
    result = render_pdf(html_path, out_path, backend="pdfkit")
    assert result == out_path
    p = Path(out_path)
    assert p.exists()
    assert p.read_bytes()[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# 4) render falls back to pdfkit when weasyprint is unavailable
# ---------------------------------------------------------------------------


def test_render_pdf_falls_back_to_pdfkit(tmp_path, monkeypatch):
    pytest.importorskip("pdfkit")
    # Force the chain past weasyprint so we exercise the pdfkit path,
    # regardless of whether weasyprint happens to be importable in
    # this environment.
    monkeypatch.setattr(
        "openpharmastability.reports.pdf._try_weasyprint", lambda: None
    )
    html_path = _write_html(tmp_path)
    out_path = str(tmp_path / "out.pdf")
    result = render_pdf(html_path, out_path)
    assert result == out_path
    p = Path(out_path)
    assert p.exists()
    assert p.read_bytes()[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# 5) render raises RuntimeError with install hint when no backend is available
# ---------------------------------------------------------------------------


def test_render_pdf_raises_with_install_message_when_no_backend(tmp_path, monkeypatch):
    # Simulate "neither backend installed" without touching the real
    # import system. The internal import probes are module-level callables
    # in reports/pdf.py, so monkeypatch.setattr on those names is enough.
    monkeypatch.setattr(
        "openpharmastability.reports.pdf._try_weasyprint", lambda: None
    )
    monkeypatch.setattr(
        "openpharmastability.reports.pdf._try_pdfkit", lambda: None
    )

    html_path = _write_html(tmp_path)
    out_path = str(tmp_path / "out.pdf")
    with pytest.raises(RuntimeError) as excinfo:
        render_pdf(html_path, out_path)

    msg = str(excinfo.value)
    assert "pip install" in msg
    assert "pdf" in msg


# ---------------------------------------------------------------------------
# 6) explicit backend kwarg is accepted
# ---------------------------------------------------------------------------


def test_render_pdf_explicit_backend_kwarg(tmp_path):
    pytest.importorskip("weasyprint")
    html_path = _write_html(tmp_path)
    out_path = str(tmp_path / "out.pdf")
    # Should not raise ValueError for the explicit backend name, and
    # should not silently fall back to a different backend.
    result = render_pdf(html_path, out_path, backend="weasyprint")
    assert result == out_path
    assert Path(out_path).exists()
    assert Path(out_path).read_bytes()[:4] == b"%PDF"
