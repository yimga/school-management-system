"""Privacy-bounded layout telemetry shared by RUM ingest and aggregation."""

from __future__ import annotations

from typing import Any


LAYOUT_SCHEMA_VERSION = 1
_COUNT_FIELDS = (
    "observed_count",
    "overflow_count",
    "inline_overflow_count",
    "block_overflow_count",
)
_PIXEL_FIELDS = (
    "max_inline_overflow_px",
    "max_block_overflow_px",
    "visual_viewport_width",
    "visual_viewport_height",
)
_VIEWPORT_CLASSES = frozenset({"A", "B", "C", "U"})
_DIRECTIONS = frozenset({"ltr", "rtl"})


def _bounded_int(value: Any, *, maximum: int) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        return None
    if number < 0:
        return None
    return min(number, maximum)


def sanitize_layout_observation(raw: Any) -> dict[str, int | str]:
    """Return the versioned, content-free subset accepted from browsers."""
    if not isinstance(raw, dict):
        return {}

    raw_version = raw.get("version")
    if isinstance(raw_version, bool):
        return {}
    try:
        version = int(raw_version)
    except (TypeError, ValueError, OverflowError):
        return {}
    if version != LAYOUT_SCHEMA_VERSION:
        return {}

    out: dict[str, int | str] = {"version": LAYOUT_SCHEMA_VERSION}
    for field in _COUNT_FIELDS:
        value = _bounded_int(raw.get(field), maximum=10_000)
        if value is not None:
            out[field] = value
    for field in _PIXEL_FIELDS:
        value = _bounded_int(raw.get(field), maximum=100_000)
        if value is not None:
            out[field] = value

    viewport_class = str(raw.get("viewport_class") or "U").upper()
    out["viewport_class"] = (
        viewport_class if viewport_class in _VIEWPORT_CLASSES else "U"
    )
    direction = str(raw.get("direction") or "ltr").lower()
    out["direction"] = direction if direction in _DIRECTIONS else "ltr"

    observed = int(out.get("observed_count", 0))
    overflow = min(int(out.get("overflow_count", 0)), observed)
    inline = min(int(out.get("inline_overflow_count", 0)), overflow)
    block = min(int(out.get("block_overflow_count", 0)), overflow)
    out["overflow_count"] = overflow
    out["inline_overflow_count"] = inline
    out["block_overflow_count"] = block
    return out
