"""Tests for ``openpharmastability.data.conditions.parse_condition``.

The condition normalizer is small but critical: every downstream filter
(``df[condition == ...]``) relies on a single canonical spelling, and
users will inevitably write the four documented variants. These tests
pin all four down to ``"25C/60RH"`` and also exercise the obvious
failure modes (non-strings, gibberish input) so the error message stays
useful.
"""
from __future__ import annotations

import pytest

from openpharmastability.data.conditions import parse_condition


# The four spellings from the spec. Each must normalize to "25C/60RH".
SPEC_SPELLINGS = [
    "25C/60RH",
    "25°C/60%RH",
    "25 C / 60 %RH",
    "25C 60% RH",
]


@pytest.mark.parametrize("raw", SPEC_SPELLINGS)
def test_parse_condition_normalizes_to_canonical(raw: str) -> None:
    assert parse_condition(raw) == "25C/60RH"


@pytest.mark.parametrize("raw", SPEC_SPELLINGS)
def test_parse_condition_is_idempotent(raw: str) -> None:
    """Normalizing a canonical string returns it unchanged."""
    assert parse_condition(parse_condition(raw)) == "25C/60RH"


def test_parse_condition_handles_different_numbers() -> None:
    """The numeric values are not hard-coded to 25/60."""
    assert parse_condition("30C/65RH") == "30C/65RH"
    assert parse_condition("40°C/75%RH") == "40C/75RH"
    assert parse_condition("5 C / 75 % RH") == "5C/75RH"


def test_parse_condition_lowercase_units() -> None:
    """Lowercase ``c`` and ``rh`` should also be accepted."""
    assert parse_condition("25c/60rh") == "25C/60RH"
    assert parse_condition("25 c / 60 rh") == "25C/60RH"


def test_parse_condition_strips_outer_whitespace() -> None:
    assert parse_condition("   25C/60RH   ") == "25C/60RH"
    assert parse_condition("\t25C/60RH\n") == "25C/60RH"


def test_parse_condition_rejects_non_string() -> None:
    with pytest.raises(ValueError, match="must be a string"):
        parse_condition(25)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must be a string"):
        parse_condition(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "raw",
    [
        "",                       # empty
        "25C",                    # missing RH
        "60RH",                   # missing temp
        "twenty-five C / sixty",  # words, not numbers
        "25C/60",                 # missing RH letters
        "25/60RH",                # missing C
    ],
)
def test_parse_condition_rejects_unparseable(raw: str) -> None:
    with pytest.raises(ValueError, match="could not parse condition"):
        parse_condition(raw)
