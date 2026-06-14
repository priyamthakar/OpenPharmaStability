"""Reproducibility tests for the ``source_epoch`` parameter and the
``SOURCE_DATE_EPOCH`` environment variable.

The HTML and JSON reports embed an analysis timestamp. For two CLI
runs against the same input to be byte-identical, the timestamp
must be pinned. This file pins it four ways:

1. Explicit ``source_epoch`` argument to :func:`analyze`.
2. No argument, no env var: falls back to wall clock.
3. ``SOURCE_DATE_EPOCH`` env var only: env var is honored.
4. Both env var and explicit argument: the explicit argument wins.

A fifth test asserts that the deterministic timestamp is what we
expect for the chosen epoch (1700000000 -> 2023-11-14T22:13:20Z).
"""
from __future__ import annotations

import pathlib
import re
from datetime import datetime, timezone

import pytest

from openpharmastability.shelf_life.engine import analyze


ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV = ROOT / "examples" / "assay_3batch.csv"

# 1700000000 -> 2023-11-14 22:13:20 UTC.
FIXED_EPOCH = 1700000000
FIXED_TS = "2023-11-14T22:13:20Z"


# ---------------------------------------------------------------------------
# 1. Explicit source_epoch is used verbatim.
# ---------------------------------------------------------------------------


def test_analyze_with_source_epoch_uses_it():
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
        source_epoch=FIXED_EPOCH,
    )
    assert result.metadata["timestamp"] == FIXED_TS


# ---------------------------------------------------------------------------
# 2. No source_epoch and no env var: wall-clock UTC ISO-8601.
# ---------------------------------------------------------------------------


def test_analyze_without_source_epoch_uses_wall_clock(monkeypatch):
    # Make sure no env var leaks in from the host shell.
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
    )
    ts = result.metadata["timestamp"]
    # Shape: "YYYY-MM-DDTHH:MM:SSZ".
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", ts), ts
    # Round-trip parses and is within the last hour of "now".
    parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    delta = abs((datetime.now(timezone.utc) - parsed).total_seconds())
    assert delta < 3600, f"timestamp {ts} not within 1h of now"


# ---------------------------------------------------------------------------
# 3. SOURCE_DATE_EPOCH env var is honored when source_epoch is None.
# ---------------------------------------------------------------------------


def test_analyze_source_epoch_env_var(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(FIXED_EPOCH))
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
    )
    assert result.metadata["timestamp"] == FIXED_TS


# ---------------------------------------------------------------------------
# 4. Explicit source_epoch wins over the env var.
# ---------------------------------------------------------------------------


def test_analyze_source_epoch_takes_precedence_over_env(monkeypatch):
    other_epoch = 1577836800  # 2020-01-01T00:00:00Z
    other_ts = "2020-01-01T00:00:00Z"
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(other_epoch))
    result = analyze(
        path=str(CSV),
        condition="25C/60RH",
        attribute="assay",
        source_epoch=FIXED_EPOCH,
    )
    # Explicit value wins.
    assert result.metadata["timestamp"] == FIXED_TS
    assert result.metadata["timestamp"] != other_ts


# ---------------------------------------------------------------------------
# 5. The fixed epoch maps to the expected UTC string (sanity check on
#    the helper itself; protects against silent timezone regressions).
# ---------------------------------------------------------------------------


def test_fixed_epoch_constant_is_correct():
    assert (
        datetime.fromtimestamp(FIXED_EPOCH, tz=timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
        == FIXED_TS
    )
