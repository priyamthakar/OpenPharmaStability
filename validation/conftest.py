"""Shared pytest fixtures and import-time checks for the v0.5+ modules.

These modules are part of the v0.5.0 release; their tests hard-require
them. If any is missing, fail collection immediately so the failure
is obvious (rather than producing a "skipped" report that looks healthy).
"""
from __future__ import annotations

import pytest

_REQUIRED_V050_MODULES = (
    "openpharmastability.stats.arrhenius",
    "openpharmastability.stats.mkt",
    "openpharmastability.regulatory.reduced_design",
    "openpharmastability.regulatory.significant_change",
)


def pytest_configure(config):
    missing = []
    for mod_name in _REQUIRED_V050_MODULES:
        try:
            __import__(mod_name)
        except Exception as exc:  # noqa: BLE001 — surface any import-time failure
            missing.append((mod_name, repr(exc)))
    if missing:
        lines = "\n".join(f"  - {n}: {e}" for n, e in missing)
        pytest.exit(
            "Missing v0.5.0 modules (tests hard-require them):\n"
            + lines
            + "\nReinstall the package with `pip install -e .[dev]`.",
            returncode=2,
        )
