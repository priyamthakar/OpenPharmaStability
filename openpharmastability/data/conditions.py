"""Condition-string normalization.

A condition like ``"25°C/60%RH"`` is a single storage environment, but the same
environment is written many ways. For join/select logic to work we must
collapse all variants to a canonical form. The spec fixes the canonical form
as ``"25C/60RH"`` and requires that the four common spellings all normalize to
the same string.

Strategy
--------
1. Strip leading/trailing whitespace.
2. Remove the degree (``°``) and percent (``%``) symbols.
3. Collapse all remaining whitespace (e.g. between number and unit letter).
4. Extract the temperature number (digits immediately before ``C``) and the
   relative-humidity number (digits immediately before ``RH``).
5. Re-emit as ``"{temp}C/{rh}RH"``.

Anything that does not match the expected shape raises ``ValueError`` with the
original input in the message — failures are loud, never silent.
"""
from __future__ import annotations

import re

# Anchored match: digits, then 'C' (case-insensitive), optional '/',
# digits, then 'RH' (case-insensitive). Whitespace between the pieces is
# tolerated by the pre-processing above, so by the time the regex runs the
# string looks like "25C/60RH" or "25C60RH".
_PATTERN = re.compile(
    r"^(\d+)\s*[Cc]\s*/?\s*(\d+)\s*[Rr][Hh]\s*$",
    flags=re.UNICODE,
)


def parse_condition(raw: str) -> str:
    """Normalize a free-form storage-condition string to ``"<T>C/<RH>RH"``.

    Parameters
    ----------
    raw:
        Any of the documented spellings (or a string already in canonical
        form). Examples that must all return ``"25C/60RH"``:

        * ``"25C/60RH"``
        * ``"25°C/60%RH"``
        * ``"25 C / 60 %RH"``
        * ``"25C 60% RH"``

    Returns
    -------
    str
        The canonical form, e.g. ``"25C/60RH"``.

    Raises
    ------
    ValueError
        If ``raw`` is not a string or cannot be parsed as a temperature/RH pair.
    """
    if not isinstance(raw, str):
        raise ValueError(
            f"condition must be a string, got {type(raw).__name__}: {raw!r}"
        )

    s = raw.strip()
    # Drop decorative symbols first; they are common to every supported form.
    s = s.replace("\u00b0", "").replace("%", "")
    # Then collapse ALL remaining whitespace. After this step
    # "25 C / 60 %RH" -> "25C/60RH" and "25C 60 RH" -> "25C60RH".
    s = re.sub(r"\s+", "", s)

    match = _PATTERN.match(s)
    if not match:
        raise ValueError(
            f"could not parse condition string: {raw!r} "
            "(expected something like '25C/60RH' or '25 C / 60 %RH')"
        )

    temp, rh = match.group(1), match.group(2)
    return f"{temp}C/{rh}RH"


__all__ = ["parse_condition"]
