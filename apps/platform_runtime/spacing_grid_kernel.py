"""Wave U (v3.99.0 — 2026-05-27) — 8px geometric spacing grid kernel.

Pure-Python validators for the geometric spacing contract. Enforces that
every spacing value (margin / padding / gap) in template-side or kernel-side
configuration is a clean multiple of the base unit (8px by default).

Why: irregular paddings cause subtle layout-shift on RTL flips and at
40%-typography-expansion. Locking to a small multiplier set is the cheapest
durable defense and the standard SaaS UX convention (Material/Apple HIG).

This module is deliberately CSS-token-free: it validates *intent*, not the
final CSS output. The cascade still owns the actual values via
``static/css/rmc-spacing-grid.css``. Use this to guard structured data
(JSON manifests, registry entries, wizard defaults) where ad-hoc pixel
values can leak in.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# The base unit and the canonical allowed multipliers.
SPACING_BASE_PX = 8
ALLOWED_MULTIPLIERS = (0, 1, 2, 3, 4, 6, 8, 10, 12, 16)
# Materialized once for membership testing.
ALLOWED_VALUES_PX: frozenset[int] = frozenset(
    m * SPACING_BASE_PX for m in ALLOWED_MULTIPLIERS
)

_PX_VALUE_RE = re.compile(r"^(-?)(\d+(?:\.\d+)?)\s*px$", re.IGNORECASE)
_BARE_NUMBER_RE = re.compile(r"^(-?)(\d+(?:\.\d+)?)$")


@dataclass(frozen=True)
class SpacingValidationResult:
    ok: bool
    canonical_px: int | None
    reason: str = ""


def _coerce_to_px(value: str | int | float) -> int | None:
    """Accept ``"24px"``, ``24``, ``"24"`` — return the int px value or None.

    Floats are floored deliberately: design tokens never use fractional pixels.
    Negative values are rejected (spacing must be non-negative).
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value < 0:
            return None
        return int(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    m = _PX_VALUE_RE.match(text)
    if m:
        if m.group(1) == "-":
            return None
        return int(float(m.group(2)))
    m = _BARE_NUMBER_RE.match(text)
    if m:
        if m.group(1) == "-":
            return None
        return int(float(m.group(2)))
    return None


def validate_spacing_value(value: str | int | float) -> SpacingValidationResult:
    """Return whether ``value`` falls on the 8px grid.

    Examples::

        validate_spacing_value("16px").ok   # True
        validate_spacing_value(24).ok       # True
        validate_spacing_value("13px").ok   # False — not a multiple of 8
        validate_spacing_value("-8px").ok   # False — negative
        validate_spacing_value("auto").ok   # False — non-numeric
    """
    px = _coerce_to_px(value)
    if px is None:
        return SpacingValidationResult(
            ok=False,
            canonical_px=None,
            reason=f"could not parse {value!r} as a non-negative pixel value",
        )
    if px in ALLOWED_VALUES_PX:
        return SpacingValidationResult(ok=True, canonical_px=px)
    nearest = snap_to_grid(px)
    return SpacingValidationResult(
        ok=False,
        canonical_px=px,
        reason=(
            f"{px}px is not on the 8px grid; nearest allowed value is {nearest}px"
        ),
    )


def snap_to_grid(px: int) -> int:
    """Snap an integer px value to the nearest allowed multiplier.

    Ties round up to give the more generous spacing (better for touch
    targets and text-expansion safety).
    """
    if px < 0:
        return 0
    sorted_values = sorted(ALLOWED_VALUES_PX)
    if px <= sorted_values[0]:
        return sorted_values[0]
    if px >= sorted_values[-1]:
        return sorted_values[-1]
    best = sorted_values[0]
    best_distance = abs(px - best)
    for v in sorted_values:
        d = abs(px - v)
        if d < best_distance or (d == best_distance and v > best):
            best = v
            best_distance = d
    return best


def validate_many(values: Iterable[str | int | float]) -> list[SpacingValidationResult]:
    """Apply ``validate_spacing_value`` to a sequence."""
    return [validate_spacing_value(v) for v in values]


def list_allowed_pixel_values() -> list[int]:
    """Diagnostic — used by tests + the design-token doc emitter."""
    return sorted(ALLOWED_VALUES_PX)
