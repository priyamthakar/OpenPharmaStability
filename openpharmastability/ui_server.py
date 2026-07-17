"""Local v1 web UI server for OpenPharmaStability.

The server is a small stdlib-only adapter around :mod:`ui_service`. It is
intended for local analysis work and demos; it is not an authentication,
audit-trail, or production deployment layer.
"""
from __future__ import annotations

import argparse
import cgi
import json
import mimetypes
import os
import shutil
import tempfile
import traceback
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from openpharmastability.contracts import DISCLAIMER, TOOL_VERSION
from openpharmastability.ui_service import UIAnalysisOptions, analyze_for_ui


STATIC_DIR = Path(__file__).resolve().parent / "ui" / "static"
RUN_ROOT = Path(tempfile.gettempdir()) / "openpharmastability-ui-runs"


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start the local UI server and block forever."""

    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), _Handler)
    print(f"OpenPharmaStability UI {TOOL_VERSION}: http://{host}:{port}")
    server.serve_forever()


class _Handler(BaseHTTPRequestHandler):
    server_version = f"OpenPharmaStabilityUI/{TOOL_VERSION}"

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("", "/"):
            self._serve_static("index.html")
            return
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if path.startswith("/static/"):
            self._serve_static(path.removeprefix("/static/"))
            return
        if path.startswith("/runs/"):
            self._serve_run_file(path)
            return
        if path == "/api/config":
            self._send_json({
                "version": TOOL_VERSION,
                "disclaimer": DISCLAIMER,
                "guidance_profiles": ["q1ae"],
            })
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - stdlib hook
        parsed = urlparse(self.path)
        if parsed.path != "/api/analyze":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            manifest = self._handle_analyze()
            self._send_json(manifest)
        except Exception as exc:  # noqa: BLE001 - user-facing local server
            self._send_json(
                {
                    "status": "error",
                    "error": str(exc),
                    "traceback": traceback.format_exc(limit=4),
                    "disclaimer": DISCLAIMER,
                },
                status=500,
            )

    def _handle_analyze(self) -> dict[str, Any]:
        content_type = self.headers.get("content-type", "")
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
                "CONTENT_LENGTH": self.headers.get("content-length", "0"),
            },
        )
        upload = form["file"] if "file" in form else None
        if upload is None or not getattr(upload, "filename", ""):
            raise ValueError("input file is required")

        run_id = uuid.uuid4().hex
        run_dir = RUN_ROOT / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        filename = Path(str(upload.filename)).name
        input_path = run_dir / filename
        with input_path.open("wb") as f:
            shutil.copyfileobj(upload.file, f)

        options_raw = _field_text(form, "options") or "{}"
        options = _options_from_payload(json.loads(options_raw))
        manifest = analyze_for_ui(
            str(input_path),
            str(run_dir / "artifact"),
            options,
            url_prefix=f"/runs/{run_id}/artifact",
        ).to_dict()
        manifest["run_id"] = run_id
        return manifest

    def _serve_static(self, name: str) -> None:
        safe_name = name.replace("\\", "/").lstrip("/")
        path = (STATIC_DIR / safe_name).resolve()
        if STATIC_DIR.resolve() not in path.parents and path != STATIC_DIR.resolve():
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send_file(path)

    def _serve_run_file(self, request_path: str) -> None:
        rel = unquote(request_path.removeprefix("/runs/")).replace("\\", "/")
        path = (RUN_ROOT / rel).resolve()
        root = RUN_ROOT.resolve()
        if root not in path.parents and path != root:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send_file(path)

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _field_text(form: cgi.FieldStorage, name: str) -> str | None:
    if name not in form:
        return None
    value = form[name]
    if isinstance(value, list):
        value = value[0]
    if getattr(value, "file", None) is not None and not getattr(value, "filename", None):
        raw = value.file.read()
        return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    return str(value.value)


def _options_from_payload(payload: dict[str, Any]) -> UIAnalysisOptions:
    attributes = payload.get("attributes")
    if isinstance(attributes, str):
        attributes = [part.strip() for part in attributes.split(",") if part.strip()]
    if not attributes:
        attributes = None
    return UIAnalysisOptions(
        condition=str(payload.get("condition") or ""),
        attribute=str(payload.get("attribute") or "assay"),
        attributes=attributes,
        all_attributes=bool(payload.get("all_attributes", False)),
        metadata_path=payload.get("metadata_path") or None,
        data_sheet=payload.get("data_sheet") or None,
        metadata_sheet=payload.get("metadata_sheet") or None,
        product_type=str(payload.get("product_type") or "product"),
        horizon=float(payload.get("horizon") or 60.0),
        replicate_policy=str(payload.get("replicate_policy") or "individual"),
        bql_policy=str(payload.get("bql_policy") or "exclude"),
        guidance=str(payload.get("guidance") or "q1ae"),
        source_epoch=(
            int(payload["source_epoch"])
            if payload.get("source_epoch") not in (None, "")
            else None
        ),
        assess_transforms=bool(payload.get("assess_transforms", False)),
        run_arrhenius=bool(payload.get("run_arrhenius", False)),
        run_mkt=bool(payload.get("run_mkt", False)),
        detect_reduced_design=bool(payload.get("detect_reduced_design", False)),
        random_effects=bool(payload.get("random_effects", False)),
        run_sensitivity=bool(payload.get("run_sensitivity", False)),
        sensitivity_mode=str(payload.get("sensitivity_mode") or "row"),
        run_arrhenius_shelf_life=bool(payload.get("run_arrhenius_shelf_life", False)),
        run_arrhenius_per_batch=bool(payload.get("run_arrhenius_per_batch", False)),
        generate_pdf=bool(payload.get("generate_pdf", False)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local OpenPharmaStability v1 UI.")
    parser.add_argument("--host", default=os.environ.get("OPENPHARMASTABILITY_UI_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("OPENPHARMASTABILITY_UI_PORT", "8765")))
    args = parser.parse_args(argv)
    run(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
